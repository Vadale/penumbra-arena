"""Federated learning on the live Penumbra arena.

Concept taught: how a federated-learning loop (FedAvg / Krum /
TrimmedMean / CKKS-encrypted aggregation) fits naturally on top of
Penumbra's primitives. Each of N agents trains a LOCAL copy of the
actor on its own (observation, action-label) buffer with real SGD;
periodically the server aggregates the per-agent weight deltas and
broadcasts the new global.

Real training (NOT synthetic gradients): each LocalActor maintains
- its own ``nn.Module`` clone of the global actor
- a bounded replay buffer of (obs, label) pairs the orchestrator
  ingests every analytics tick

On ``step()`` each LocalActor runs ``local_steps`` SGD passes
(cross-entropy against the heuristic label), the delta
``local_weights - global_baseline`` is computed, the server
aggregates deltas with the chosen ``method`` (``fedavg``,
``ckks_sum``, ``krum``, ``trimmed_mean``), and the result is added
to ``global_baseline`` + broadcast to every LocalActor.

Tier 2 detail (``_aggregate_ckks_sum``): flattens every agent's
delta into ONE float vector, slices into slot-count chunks
(poly_modulus_degree=8192 → 4096 slots), encrypts each chunk per
agent, sums homomorphically across agents (server never decrypts
individual chunks), decrypts the sum, divides by N, and unflattens.
``wire_bytes`` is measured from the actual serialised ciphertexts.

Tier 3 detail (DP-SGD knobs): ``dp_noise_sigma`` + ``dp_l2_clip``
inject PER-EXAMPLE gradient clipping + Gaussian noise into the local
SGD inner loop, following Abadi et al. 2016 — each sample's gradient
L2 is clipped to ≤ ``dp_l2_clip`` *individually* before the per-batch
sum, then Gaussian noise of std ``sigma * clip`` is added to the sum,
and the noised average is fed to the optimiser. Per-sample gradients
are computed inline via ``torch.func.vmap`` + ``torch.func.grad`` of
``torch.func.functional_call`` — no Opacus dependency. Batch selection
uses Poisson subsampling (bernoulli inclusion per example with
probability ``local_batch_size / buffer_size``), matching the RDP-SGM
assumption; empty batches are skipped. The toy ε accumulator
(``privacy_spent``) is documented as such; the real RDP accountant
lives in ``federated_dp.py``.

Tier 4 detail (Byzantine-robust): ``krum`` + ``trimmed_mean`` are
exposed both as standalone functions AND as ``method=`` choices on
the trainer, so the dashboard can flip aggregator live.

Tier 5 detail (FedProx + personalisation + compression):
- ``fedprox_mu`` adds a proximal term ``(mu/2) * ||w_local - w_global||^2``
  to each local SGD step's loss, anchoring drift to the global baseline.
- ``LocalActor.personal_head`` is a per-client residual ``nn.Linear``
  on top of the shared actor output. It NEVER enters aggregation
  (the server only averages the shared body) and survives broadcasts.
- ``topk_fraction`` sparsifies each delta tensor by keeping only the
  top-k% by absolute value (rest zeroed); ``quantize_bits=8`` quantises
  the surviving values to 8-bit and dequantises (lossy). Both feed
  into ``bandwidth_bytes`` so the dashboard reflects realised savings.

Spec: FEDERATED_LEARNING_PLAN.md at repo root.
"""

from __future__ import annotations

import copy
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Final

import numpy as np
import torch
from torch import Tensor, nn

from penumbra_learning.federated_dp import RDPAccountant

_DEFAULT_LOCAL_STEPS: Final[int] = 16
_DEFAULT_LOCAL_BATCH_SIZE: Final[int] = 32
_DEFAULT_LOCAL_LR: Final[float] = 1e-3
_DEFAULT_BUFFER_CAPACITY: Final[int] = 256
_DEFAULT_DP_NOISE_SIGMA: Final[float] = 0.5
_DEFAULT_DP_L2_CLIP: Final[float] = 1.0
_AGGREGATION_METHODS: Final[frozenset[str]] = frozenset(
    {"fedavg", "ckks_sum", "krum", "trimmed_mean"}
)


class DPBudgetExhaustedError(RuntimeError):
    """Raised when a DP-SGD round is started after the global DP budget
    is exhausted (Phase 6a Tier 3). The trainer's ``dp_blocked`` flag
    is flipped by the orchestrator on receipt of ``dp.budget.exhausted``;
    the operator must call :meth:`FederatedTrainer.unblock_dp` (after a
    deliberate budget refresh) to resume DP-SGD rounds. Non-DP rounds
    (``dp_noise_sigma == 0``) are NOT blocked.
    """


@dataclass(slots=True)
class LocalActor:
    """Per-agent actor module + replay buffer + privacy accumulator.

    The ``actor`` is an independent ``nn.Module`` (deep-copied from
    the global baseline at ``fresh()`` time). Local SGD mutates only
    this copy. The ``delta`` property returns the
    ``local_weights - global_baseline`` dict used by the aggregator.

    Tier 5: ``personal_head`` is an optional ``nn.Linear`` that lives
    purely on the client — it is NEVER averaged into the global
    baseline and survives ``load_weights`` broadcasts unchanged. It
    represents a residual ``(n_actions,) += linear(hidden_features)``
    layered on top of the shared body during evaluation only.
    """

    agent_id: int
    actor: nn.Module
    observations: deque[np.ndarray]
    labels: deque[int]
    local_steps_since_aggregation: int = 0
    privacy_spent: float = 0.0
    last_loss: float = 0.0
    personal_head: nn.Linear | None = None

    @classmethod
    def fresh(
        cls,
        agent_id: int,
        template: nn.Module,
        buffer_capacity: int = _DEFAULT_BUFFER_CAPACITY,
        with_personal_head: bool = False,
        hidden_dim: int | None = None,
        n_actions: int | None = None,
    ) -> LocalActor:
        """Build a local actor whose weights are a clone of `template`.

        When ``with_personal_head=True``, attach an ``nn.Linear(hidden_dim,
        n_actions)`` initialised to zero so that early-round behaviour
        is indistinguishable from the shared actor. The head stays
        local across all aggregation rounds (Tier 5 personalisation).
        """
        actor = copy.deepcopy(template).cpu()
        personal_head: nn.Linear | None = None
        if with_personal_head:
            if hidden_dim is None or n_actions is None:
                raise ValueError("with_personal_head=True requires hidden_dim and n_actions")
            personal_head = nn.Linear(hidden_dim, n_actions)
            with torch.no_grad():
                personal_head.weight.zero_()
                if personal_head.bias is not None:
                    personal_head.bias.zero_()
        return cls(
            agent_id=agent_id,
            actor=actor,
            observations=deque(maxlen=buffer_capacity),
            labels=deque(maxlen=buffer_capacity),
            personal_head=personal_head,
        )

    def forward(self, obs: Tensor) -> Tensor:
        """Run the shared body + optional personal residual.

        Returns raw logits (not a Categorical), suitable for both
        cross-entropy supervision and post-hoc softmaxing.
        Recomputes hidden features via the shared body up to (but
        not including) the final linear, then adds the personal head's
        contribution. Used in evaluation paths only — aggregation
        sees the shared body alone.
        """
        body: nn.Module = self.actor.net  # type: ignore[assignment]
        shared_logits = body(obs)
        if self.personal_head is None:
            return shared_logits
        # Penultimate layer activations: re-run the body up to the last linear.
        layers = list(body.children())
        head_in = obs
        for layer in layers[:-1]:
            head_in = layer(head_in)
        personal_logits = self.personal_head(head_in)
        return shared_logits + personal_logits

    def ingest(self, obs: np.ndarray, label: int) -> None:
        """Append one (obs, label) sample to the local buffer."""
        self.observations.append(obs.astype(np.float32))
        self.labels.append(int(label))

    @property
    def buffer_size(self) -> int:
        return len(self.observations)

    def weights(self) -> dict[str, Tensor]:
        return {name: p.detach().clone() for name, p in self.actor.named_parameters()}

    def load_weights(self, weights: dict[str, Tensor]) -> None:
        with torch.no_grad():
            for name, param in self.actor.named_parameters():
                if name in weights:
                    param.copy_(weights[name])

    def delta_against(self, baseline: dict[str, Tensor]) -> dict[str, Tensor]:
        """Return local_weights - baseline as a dict of tensors."""
        local = self.weights()
        return {name: local[name] - baseline[name] for name in baseline}


@dataclass(slots=True)
class FederatedRound:
    """Result of one aggregation round."""

    round_id: int
    n_participants: int
    aggregation_method: str
    encrypted: bool
    bandwidth_bytes: int
    aggregation_time_ms: float
    parameter_l2_norm_change: float
    mean_local_loss: float = 0.0


@dataclass(slots=True)
class FederatedTrainer:
    """Tier 1 + 2 FedAvg trainer wrapped around the shared MAPPO actor.

    The trainer maintains N LocalActor states (one per agent). On each
    `step()` call:
      1. Each local actor performs `local_steps` simulated SGD passes
         on randomly-drawn observations (Tier 1 uses synthetic
         per-agent gradients so the loop runs without dependence on a
         live environment; Tier 2 will replace this with real local
         rollouts).
      2. The server aggregates the per-agent deltas using `method`
         ('fedavg' or 'ckks_sum').
      3. The aggregated delta is applied to the global baseline.
    """

    global_baseline: dict[str, Tensor]
    local_actors: dict[int, LocalActor]
    template_actor: nn.Module
    aggregation_method: str = "fedavg"
    history: deque[FederatedRound] = field(default_factory=lambda: deque(maxlen=200))
    next_round_id: int = 0
    local_steps: int = _DEFAULT_LOCAL_STEPS
    local_batch_size: int = _DEFAULT_LOCAL_BATCH_SIZE
    local_lr: float = _DEFAULT_LOCAL_LR
    enabled: bool = False
    dp_noise_sigma: float = 0.0
    dp_l2_clip: float = 0.0
    krum_f: int = 1
    trimmed_mean_fraction: float = 0.2
    fedprox_mu: float = 0.0
    topk_fraction: float = 1.0
    quantize_bits: int = 0
    rdp_accountant: RDPAccountant | None = None
    # Phase 6a Tier 3 — flipped by the orchestrator when the global DP
    # mechanism signals ``dp.budget.exhausted``. While True, attempting
    # to start a DP-SGD round (``dp_noise_sigma > 0``) raises
    # :class:`DPBudgetExhaustedError`; non-DP rounds proceed normally.
    dp_blocked: bool = False
    blocked_agents: set[int] = field(default_factory=set)

    @classmethod
    def from_mappo(
        cls,
        agent_net: object,
        n_agents: int,
        method: str = "fedavg",
        with_personal_heads: bool = False,
    ) -> FederatedTrainer:
        """Build a federated trainer initialised from a MAPPO actor's params.

        ``with_personal_heads=True`` (Tier 5) attaches a per-client
        ``nn.Linear(hidden_dim, n_actions)`` to every LocalActor — the
        head is never aggregated.
        """
        actor = agent_net.actor  # type: ignore[attr-defined]
        template = copy.deepcopy(actor).cpu()
        baseline = {
            name: param.detach().clone().cpu() for name, param in template.named_parameters()
        }
        hidden_dim: int | None = None
        n_actions: int | None = None
        if with_personal_heads:
            body = template.net  # type: ignore[attr-defined]
            linear_layers = [layer for layer in body if isinstance(layer, nn.Linear)]
            if not linear_layers:
                raise ValueError("template actor has no nn.Linear layers")
            hidden_dim = int(linear_layers[-1].in_features)
            n_actions = int(linear_layers[-1].out_features)
        local_actors = {
            i: LocalActor.fresh(
                i,
                template,
                with_personal_head=with_personal_heads,
                hidden_dim=hidden_dim,
                n_actions=n_actions,
            )
            for i in range(n_agents)
        }
        if method not in _AGGREGATION_METHODS:
            raise ValueError(
                f"unknown method {method!r}; choose from {sorted(_AGGREGATION_METHODS)}"
            )
        return cls(
            global_baseline=baseline,
            local_actors=local_actors,
            template_actor=template,
            aggregation_method=method,
        )

    def ingest(self, agent_id: int, obs: np.ndarray, label: int) -> None:
        """Append one (obs, label) sample to agent_id's local buffer.

        Called by the orchestrator once per agent per analytics tick.
        ``label`` is the supervised target — typically the heuristic
        action a greedy-nearest-goal policy would pick.
        """
        actor_state = self.local_actors.get(agent_id)
        if actor_state is not None:
            actor_state.ingest(obs, label)

    def _train_local_actor(self, state: LocalActor) -> float:
        """Run `local_steps` real SGD passes on state's buffer.

        When ``fedprox_mu > 0`` the loss includes the FedProx
        proximal term ``(mu/2) * sum_p ||p_local - p_global||^2``
        (Li et al. 2020), which anchors the local copy to the broadcast
        global. Crucial under heterogeneous data: pure FedAvg drifts.

        Batch selection uses Poisson subsampling (Bernoulli inclusion
        per example with probability ``local_batch_size / n``) so the
        sampling distribution matches the RDP-SGM analysis used by the
        DP accountant. Empty batches are silently skipped.

        When ``dp_noise_sigma > 0`` and ``dp_l2_clip > 0`` the step
        switches to a PER-EXAMPLE clipping path (Abadi et al. 2016):
        compute g_i = ∇loss(x_i, y_i) for every i in the Poisson-
        subsampled batch, clip each ``||g_i||_2 ≤ dp_l2_clip``
        individually, sum, add Gaussian noise of std ``sigma * clip``,
        and assign ``sum / batch_size`` to ``param.grad`` before
        ``optimizer.step()``. Without DP the standard per-batch
        gradient path is used.
        """
        n = state.buffer_size
        if n < 2:
            return 0.0
        obs_arr = np.stack(list(state.observations), axis=0)
        label_arr = np.asarray(list(state.labels), dtype=np.int64)
        obs_t = torch.as_tensor(obs_arr, dtype=torch.float32)
        label_t = torch.as_tensor(label_arr, dtype=torch.long)
        optimizer = torch.optim.SGD(state.actor.parameters(), lr=self.local_lr)
        loss_fn = nn.CrossEntropyLoss()
        dp_enabled = self.dp_noise_sigma > 0.0 and self.dp_l2_clip > 0.0
        total_loss = 0.0
        batches = 0
        for _ in range(self.local_steps):
            idx = self._poisson_subsample_indices(n)
            batch_n = int(idx.numel())
            if batch_n == 0:
                continue
            if dp_enabled:
                step_loss = self._dp_step_per_example(
                    state=state,
                    optimizer=optimizer,
                    obs_t=obs_t,
                    label_t=label_t,
                    idx=idx,
                )
            else:
                optimizer.zero_grad()
                logits = state.actor.net(obs_t[idx])  # type: ignore[operator]
                loss = loss_fn(logits, label_t[idx])
                if self.fedprox_mu > 0.0:
                    prox = torch.zeros((), dtype=loss.dtype)
                    for name, param in state.actor.named_parameters():
                        global_p = self.global_baseline[name]
                        prox = prox + ((param - global_p) ** 2).sum()
                    loss = loss + (self.fedprox_mu / 2.0) * prox
                loss.backward()
                optimizer.step()
                step_loss = float(loss.item())
            total_loss += step_loss
            batches += 1
            state.local_steps_since_aggregation += 1
        if batches == 0:
            state.last_loss = 0.0
            return 0.0
        avg_loss = total_loss / batches
        state.last_loss = avg_loss
        return avg_loss

    def _poisson_subsample_indices(self, n: int) -> Tensor:
        """Return Bernoulli-included indices for one DP-SGD-style minibatch.

        Each of the ``n`` samples is independently included with
        probability ``min(1, local_batch_size / n)``. Returns a 1-D
        ``LongTensor`` of selected indices (possibly empty).
        """
        if n <= 0:
            return torch.empty(0, dtype=torch.long)
        p = min(1.0, float(self.local_batch_size) / float(n))
        include = torch.rand(n) < p
        return torch.nonzero(include, as_tuple=True)[0]

    def _dp_step_per_example(
        self,
        *,
        state: LocalActor,
        optimizer: torch.optim.Optimizer,
        obs_t: Tensor,
        label_t: Tensor,
        idx: Tensor,
    ) -> float:
        """One DP-SGD step with per-example clipping (Abadi et al. 2016).

        Computes the per-sample gradient g_i = ∇loss(x_i, y_i) for
        every i in ``idx`` using ``torch.func.vmap`` + ``torch.func.grad``
        of a functional CE loss called via ``torch.func.functional_call``
        on the actor's underlying ``nn.Sequential`` (``state.actor.net``).
        Each g_i is clipped to L2 ≤ ``dp_l2_clip`` individually, the
        clipped gradients are summed, Gaussian noise of std
        ``sigma * clip`` is added to the sum, the noised sum is divided
        by the batch size and assigned to ``param.grad``, and
        ``optimizer.step()`` is called.

        The FedProx proximal term, if enabled, is added per-parameter
        as a deterministic non-sample-dependent gradient AFTER the DP
        averaging — it depends only on the global baseline (public from
        every client's perspective) and so does not affect sensitivity.

        Composes one Sampled Gaussian Mechanism step into the
        ``rdp_accountant`` (lazily instantiated) with sample rate
        ``local_batch_size / buffer_size``.
        """
        from torch.func import functional_call, grad, vmap

        net: nn.Module = state.actor.net  # type: ignore[assignment]
        params: dict[str, Tensor] = dict(net.named_parameters())
        buffers: dict[str, Tensor] = dict(net.named_buffers())
        loss_fn = nn.CrossEntropyLoss()

        def _per_sample_loss(
            p: dict[str, Tensor],
            b: dict[str, Tensor],
            x: Tensor,
            y: Tensor,
        ) -> Tensor:
            logits = functional_call(net, (p, b), (x.unsqueeze(0),))
            return loss_fn(logits, y.unsqueeze(0))

        per_sample_grad = vmap(
            grad(_per_sample_loss),
            in_dims=(None, None, 0, 0),
        )

        batch_obs = obs_t[idx]
        batch_labels = label_t[idx]
        batch_n = int(idx.numel())

        grads = per_sample_grad(params, buffers, batch_obs, batch_labels)

        param_names = list(params.keys())
        per_sample_flat = torch.cat(
            [grads[name].reshape(batch_n, -1) for name in param_names], dim=1
        )
        per_sample_norms = per_sample_flat.norm(dim=1)
        clip_factor = (self.dp_l2_clip / (per_sample_norms + 1e-12)).clamp(max=1.0)

        summed_grads: dict[str, Tensor] = {}
        for name in param_names:
            g = grads[name]
            shape_tail = g.shape[1:]
            scaled = g * clip_factor.view(-1, *([1] * len(shape_tail)))
            summed_grads[name] = scaled.sum(dim=0)

        noise_std = self.dp_noise_sigma * self.dp_l2_clip
        with torch.no_grad():
            for name in param_names:
                noise = torch.randn_like(summed_grads[name]) * noise_std
                summed_grads[name] = (summed_grads[name] + noise) / float(batch_n)

        optimizer.zero_grad()
        named_params = dict(state.actor.named_parameters())
        for name in param_names:
            full_name = f"net.{name}"
            target = named_params.get(full_name)
            if target is None:
                continue
            target.grad = summed_grads[name].detach()

        if self.fedprox_mu > 0.0:
            with torch.no_grad():
                for full_name, param in state.actor.named_parameters():
                    global_p = self.global_baseline.get(full_name)
                    if global_p is None or param.grad is None:
                        continue
                    param.grad.add_(self.fedprox_mu * (param.data - global_p))

        optimizer.step()

        state.privacy_spent += float(self.dp_l2_clip / max(self.dp_noise_sigma, 1e-6))
        if self.rdp_accountant is None:
            self.rdp_accountant = RDPAccountant()
        buffer_size = max(state.buffer_size, 1)
        sample_rate = min(1.0, float(self.local_batch_size) / float(buffer_size))
        self.rdp_accountant.step(
            noise_multiplier=float(self.dp_noise_sigma), sample_rate=sample_rate
        )

        with torch.no_grad():
            logits = state.actor.net(batch_obs)  # type: ignore[operator]
            return float(loss_fn(logits, batch_labels).item())

    def epsilon(self, delta: float = 1e-5) -> float:
        """Return the (ε, δ)-DP guarantee from the RDP accountant.

        Returns 0.0 before any DP-SGD step has been composed (no
        accountant yet, no privacy spent) so the dashboard renders a
        sensible zero rather than +inf.
        """
        if self.rdp_accountant is None:
            return 0.0
        return self.rdp_accountant.epsilon(target_delta=delta)

    def _local_phase(self) -> float:
        """Run real SGD on every LocalActor; return mean loss."""
        losses: list[float] = []
        for state in self.local_actors.values():
            losses.append(self._train_local_actor(state))
        return float(np.mean(losses)) if losses else 0.0

    def _collect_deltas(self) -> tuple[list[dict[str, Tensor]], int]:
        """Compute (local - baseline) for every LocalActor; return + wire_bytes.

        Tier 5 compression (transparent to aggregation logic):
        - ``topk_fraction < 1.0``: per-tensor top-k sparsification.
          The k% largest |values| survive; the rest are zeroed.
          Wire cost is (kept indices + kept values) — pairs of
          (int32 index, float32 value) — instead of the dense tensor.
        - ``quantize_bits == 8``: surviving values are linearly
          quantised to int8 then dequantised, recording an int8 byte
          cost per kept value instead of float32. A per-tensor scalar
          scale is included (8 bytes).
        Defaults (1.0 / 0) preserve exact byte-for-byte behaviour.
        """
        deltas: list[dict[str, Tensor]] = []
        wire_bytes = 0
        topk_active = 0.0 < self.topk_fraction < 1.0
        quant_active = self.quantize_bits == 8
        for agent_id, state in self.local_actors.items():
            if agent_id in self.blocked_agents:
                # Tier 2 — security event has teeth on FL too. A blocked
                # client's delta is silently replaced by zeros so it can
                # neither poison the aggregate nor consume bandwidth-
                # accounting (still zero bytes for the zero tensors).
                zero_delta = {
                    name: torch.zeros_like(self.global_baseline[name])
                    for name in self.global_baseline
                }
                deltas.append(zero_delta)
                continue
            delta = state.delta_against(self.global_baseline)
            compressed: dict[str, Tensor] = {}
            for name, tensor in delta.items():
                t = tensor
                if topk_active:
                    t = _topk_sparsify(t, self.topk_fraction)
                if quant_active:
                    t = _quantize_dequantize_int8(t)
                compressed[name] = t
                wire_bytes += _delta_tensor_nbytes(
                    t,
                    topk_active=topk_active,
                    quant_active=quant_active,
                )
            deltas.append(compressed)
        return deltas, wire_bytes

    def _aggregate_fedavg(self) -> tuple[dict[str, Tensor], int]:
        """Plain FedAvg: per-parameter mean across actors."""
        deltas, wire_bytes = self._collect_deltas()
        return fedavg(deltas), wire_bytes

    def _aggregate_krum(self) -> tuple[dict[str, Tensor], int]:
        """Tier 4: Byzantine-robust Krum selection."""
        deltas, wire_bytes = self._collect_deltas()
        return krum(deltas, f=self.krum_f), wire_bytes

    def _aggregate_trimmed_mean(self) -> tuple[dict[str, Tensor], int]:
        """Tier 4: Byzantine-robust per-coordinate trimmed mean."""
        deltas, wire_bytes = self._collect_deltas()
        return trimmed_mean(deltas, trim_fraction=self.trimmed_mean_fraction), wire_bytes

    def _aggregate_ckks_sum(self) -> tuple[dict[str, Tensor], int]:
        """Tier 2: REAL CKKS-encrypted homomorphic SUM, then scalar /N decrypt.

        Pipeline:
          1. For each LocalActor, flatten the delta dict into ONE
             float64 vector (parameter order = insertion order of
             ``self.global_baseline``, which itself mirrors the actor's
             ``named_parameters`` order — stable per Python ≥3.7).
          2. Slice the vector into chunks of ``slot_count`` (CKKS at
             poly_modulus_degree=8192 gives 4096 SIMD slots; an actor
             with > 4096 parameters spills into multiple ciphertexts).
          3. Encrypt each chunk per agent → list[list[ciphertext]].
          4. Homomorphically SUM the ciphertexts across agents (per
             chunk index). The server never decrypts any individual
             chunk — only the sum.
          5. Decrypt the sum, divide by N (plain float), concatenate
             chunks, unflatten back into the parameter-dict shape.

        ``wire_bytes`` is measured from the serialised ciphertext
        bytes (TenSEAL exposes ``.serialize()`` on every CKKSVector;
        OpenFHE wraps ``Serialize``). If neither method is available
        we fall back to a conservative byte estimate
        (slot_count × 8 bytes × 2 polynomials × log2(coeff_modulus_bits)).

        Precision note: TenSEAL CKKS accumulates ~2^-30 noise per
        addition; summing 50 ciphertexts is well within budget.
        Decrypted values are clipped to a sane range (±1e3) to defend
        against the rare NaN that surfaces when the modulus chain is
        nearly exhausted.
        """
        from penumbra_crypto.ckks import get_backend

        backend = get_backend()
        slot_count = int(getattr(backend, "slot_count", 4096))

        param_names = list(self.global_baseline.keys())
        param_shapes = {name: self.global_baseline[name].shape for name in param_names}
        param_sizes = {name: int(self.global_baseline[name].numel()) for name in param_names}
        total_flat = sum(param_sizes.values())

        # Flatten every actor's delta in a stable parameter-name order.
        actor_flats: list[np.ndarray] = []
        for state in self.local_actors.values():
            delta = state.delta_against(self.global_baseline)
            pieces = [delta[name].detach().cpu().numpy().reshape(-1) for name in param_names]
            flat = np.concatenate(pieces).astype(np.float64) if pieces else np.zeros(0, np.float64)
            actor_flats.append(flat)

        n_actors = len(actor_flats)
        if n_actors == 0 or total_flat == 0:
            return {name: torch.zeros_like(self.global_baseline[name]) for name in param_names}, 0

        # Slice each flat vector into slot-count chunks.
        n_chunks = (total_flat + slot_count - 1) // slot_count
        wire_bytes = 0
        summed_chunks: list[np.ndarray] = []
        for chunk_idx in range(n_chunks):
            start = chunk_idx * slot_count
            end = min(start + slot_count, total_flat)
            accumulator: object | None = None
            for flat in actor_flats:
                piece = flat[start:end]
                ct = backend.encrypt(piece)
                wire_bytes += _ciphertext_nbytes(ct, slot_count=slot_count)
                if accumulator is None:
                    accumulator = ct
                else:
                    new_acc = backend.add(accumulator, ct)
                    del accumulator
                    del ct
                    accumulator = new_acc
            assert accumulator is not None  # n_actors > 0 guarantees this
            decrypted = backend.decrypt(accumulator)[: end - start]
            del accumulator
            summed_chunks.append(np.asarray(decrypted, dtype=np.float64))

        # Concatenate, divide by N, sanitise (CKKS approx-noise can drift).
        summed_flat = np.concatenate(summed_chunks) if summed_chunks else np.zeros(0, np.float64)
        averaged_flat = summed_flat / float(n_actors)
        averaged_flat = np.nan_to_num(averaged_flat, nan=0.0, posinf=0.0, neginf=0.0)
        averaged_flat = np.clip(averaged_flat, -1e3, 1e3)

        # Unflatten back into the per-parameter dict.
        aggregated: dict[str, Tensor] = {}
        cursor = 0
        for name in param_names:
            size = param_sizes[name]
            slice_ = averaged_flat[cursor : cursor + size]
            cursor += size
            template = self.global_baseline[name]
            aggregated[name] = (
                torch.from_numpy(slice_.astype(np.float32))
                .reshape(param_shapes[name])
                .to(template.dtype)
            )

        return aggregated, wire_bytes

    def step(self) -> FederatedRound:
        """One full round: real local SGD → aggregate → broadcast."""
        if self.dp_blocked and self.dp_noise_sigma > 0.0:
            msg = (
                "DP-SGD round refused: global DP budget exhausted. "
                + "Call unblock_dp() after a deliberate budget refresh to resume."
            )
            raise DPBudgetExhaustedError(msg)
        mean_loss = self._local_phase()
        t0 = time.perf_counter()
        method = self.aggregation_method
        if method == "ckks_sum":
            aggregated, wire_bytes = self._aggregate_ckks_sum()
            encrypted = True
        elif method == "krum":
            aggregated, wire_bytes = self._aggregate_krum()
            encrypted = False
        elif method == "trimmed_mean":
            aggregated, wire_bytes = self._aggregate_trimmed_mean()
            encrypted = False
        else:
            aggregated, wire_bytes = self._aggregate_fedavg()
            encrypted = False
        # Apply aggregated delta to baseline + broadcast new baseline to locals.
        l2_change = 0.0
        for name, delta in aggregated.items():
            self.global_baseline[name] = self.global_baseline[name] + delta
            l2_change += float(delta.norm()) ** 2
        l2_change = l2_change**0.5
        for state in self.local_actors.values():
            state.load_weights(self.global_baseline)
            state.local_steps_since_aggregation = 0
        round_id = self.next_round_id
        self.next_round_id += 1
        agg_ms = (time.perf_counter() - t0) * 1000
        record = FederatedRound(
            round_id=round_id,
            n_participants=len(self.local_actors),
            aggregation_method=method,
            encrypted=encrypted,
            bandwidth_bytes=wire_bytes,
            aggregation_time_ms=agg_ms,
            parameter_l2_norm_change=l2_change,
            mean_local_loss=mean_loss,
        )
        self.history.append(record)
        return record

    def start(self) -> None:
        self.enabled = True

    def stop(self) -> None:
        self.enabled = False

    def block_dp(self) -> None:
        """Refuse further DP-SGD rounds (Phase 6a Tier 3).

        Idempotent — re-blocking a blocked trainer is a no-op.
        """
        self.dp_blocked = True

    def unblock_dp(self) -> None:
        """Lift the DP-SGD block (Phase 6a Tier 3).

        Idempotent — unblocking an unblocked trainer is a no-op.
        Intended to be called by an operator AFTER deliberately
        refreshing the global ``PrivacyBudget``.
        """
        self.dp_blocked = False

    def set_method(self, method: str) -> None:
        if method not in _AGGREGATION_METHODS:
            raise ValueError(
                f"unknown method {method!r}; choose from {sorted(_AGGREGATION_METHODS)}"
            )
        self.aggregation_method = method

    def set_fedprox(self, mu: float) -> None:
        """Set the FedProx proximal-term coefficient (Tier 5).

        ``mu == 0`` disables the term and restores plain local SGD.
        """
        if mu < 0:
            raise ValueError("fedprox mu must be >= 0")
        self.fedprox_mu = float(mu)

    def block_agent(self, agent_id: int) -> None:
        """Phase 6a Tier 2: gate ``agent_id`` from contributing FL deltas.

        Idempotent. Blocked agents' deltas are zeroed in ``_collect_deltas``
        so a compromised client can neither poison the aggregate nor
        leak gradients via the wire.
        """
        self.blocked_agents.add(int(agent_id))

    def unblock_agent(self, agent_id: int) -> None:
        """Restore ``agent_id`` to active FL participation. No-op if absent."""
        self.blocked_agents.discard(int(agent_id))

    def set_compression(self, topk_fraction: float, quantize_bits: int) -> None:
        """Set Tier 5 communication compression knobs.

        ``topk_fraction == 1.0`` and ``quantize_bits == 0`` together
        restore the uncompressed dense delta format.
        """
        if not 0.0 <= topk_fraction <= 1.0:
            raise ValueError("topk_fraction must be in [0, 1]")
        if quantize_bits not in (0, 8):
            raise ValueError("quantize_bits must be 0 or 8")
        self.topk_fraction = float(topk_fraction)
        self.quantize_bits = int(quantize_bits)

    def summary(self) -> dict[str, object]:
        """Snapshot for /federated/status endpoint."""
        recent = list(self.history)[-30:]
        return {
            "enabled": bool(self.enabled),
            "method": self.aggregation_method,
            "n_participants": len(self.local_actors),
            "rounds_completed": self.next_round_id,
            "local_steps_per_round": self.local_steps,
            "local_batch_size": self.local_batch_size,
            "local_lr": self.local_lr,
            "dp_noise_sigma": self.dp_noise_sigma,
            "dp_l2_clip": self.dp_l2_clip,
            "dp_rdp_n_steps": (
                self.rdp_accountant.n_steps if self.rdp_accountant is not None else 0
            ),
            "fedprox_mu": self.fedprox_mu,
            "topk_fraction": self.topk_fraction,
            "quantize_bits": self.quantize_bits,
            "personalised": any(s.personal_head is not None for s in self.local_actors.values()),
            "mean_buffer_size": (
                float(np.mean([s.buffer_size for s in self.local_actors.values()]))
                if self.local_actors
                else 0.0
            ),
            "recent_rounds": [
                {
                    "round_id": r.round_id,
                    "encrypted": r.encrypted,
                    "method": r.aggregation_method,
                    "bandwidth_bytes": r.bandwidth_bytes,
                    "aggregation_time_ms": r.aggregation_time_ms,
                    "l2_change": r.parameter_l2_norm_change,
                    "mean_local_loss": r.mean_local_loss,
                }
                for r in recent
            ],
        }


def _topk_sparsify(tensor: Tensor, fraction: float) -> Tensor:
    """Zero out all but the top ``fraction`` entries by absolute value.

    Tier 5 communication compression. ``fraction >= 1`` returns the
    input unchanged; ``fraction <= 0`` returns a zero tensor. For any
    non-empty input at least one entry survives.
    """
    if fraction >= 1.0:
        return tensor
    if tensor.numel() == 0:
        return tensor
    if fraction <= 0.0:
        return torch.zeros_like(tensor)
    flat = tensor.flatten()
    k = max(1, round(flat.numel() * fraction))
    k = min(k, flat.numel())
    _, idx = torch.topk(flat.abs(), k=k)
    mask = torch.zeros_like(flat)
    mask[idx] = 1.0
    return (flat * mask).reshape(tensor.shape)


def _quantize_dequantize_int8(tensor: Tensor) -> Tensor:
    """Round-trip a tensor through symmetric 8-bit quantisation.

    Per-tensor scale is ``max(|x|) / 127``; values map to int8 then
    back to float32. Tensors with no non-zero entries are returned
    unchanged.
    """
    if tensor.numel() == 0:
        return tensor
    max_abs = float(tensor.abs().max().item())
    if max_abs == 0.0:
        return tensor.clone()
    scale = max_abs / 127.0
    q = torch.clamp(torch.round(tensor / scale), -127, 127)
    return (q * scale).to(tensor.dtype)


def _delta_tensor_nbytes(
    tensor: Tensor,
    *,
    topk_active: bool,
    quant_active: bool,
) -> int:
    """Wire-byte cost of a (possibly compressed) delta tensor.

    - Dense uncompressed: ``element_size * numel``.
    - Top-k only: 4-byte index + 4-byte float per non-zero.
    - Quantised only: 1 byte/element + 8-byte per-tensor scale.
    - Top-k + quantised: 4-byte index + 1-byte int8 per non-zero, plus
      8 bytes for the per-tensor scale.
    """
    numel = tensor.numel()
    if numel == 0:
        return 0
    if topk_active:
        nnz = int(torch.count_nonzero(tensor).item())
        index_bytes = 4 * nnz
        value_bytes = nnz if quant_active else 4 * nnz
        scale_bytes = 8 if quant_active else 0
        return index_bytes + value_bytes + scale_bytes
    if quant_active:
        return numel + 8
    return int(tensor.element_size() * numel)


def _ciphertext_nbytes(ct: object, *, slot_count: int) -> int:
    """Best-effort size estimate for a CKKS ciphertext on the wire.

    TenSEAL exposes ``.serialize() -> bytes``; OpenFHE exposes
    ``Serialize(stream, mode)`` via its Python bindings. When neither
    is reachable we fall back to a conservative analytic estimate:
    two NTT polynomials of degree ``2 * slot_count`` with 60-bit
    coefficients ≈ ``2 * slot_count * 8 * 2`` bytes (per ciphertext
    in a fresh modulus level). This keeps the bandwidth number
    REALISTIC even on the fallback path.
    """
    serialize = getattr(ct, "serialize", None)
    if callable(serialize):
        try:
            raw = serialize()
        except Exception:
            # Fall through to the analytic estimate below.
            raw = None
        if isinstance(raw, bytes | bytearray):
            return len(raw)
    # Fallback estimate: 2 polynomials × (2*slot_count) coeffs × 8 bytes.
    return int(2 * (2 * slot_count) * 8)


def fedavg(updates: list[dict[str, Tensor]]) -> dict[str, Tensor]:
    """Functional FedAvg aggregator over a list of update dicts.

    Public API used by tests + the dashboard's standalone FL demo.
    """
    if not updates:
        return {}
    result: dict[str, Tensor] = {}
    for name in updates[0]:
        stacked = torch.stack([u[name] for u in updates], dim=0)
        result[name] = stacked.mean(dim=0)
    return result


def krum(updates: list[dict[str, Tensor]], f: int = 1) -> dict[str, Tensor]:
    """Krum aggregator (Blanchard et al. 2017).

    Pick the update whose sum of distances to the (n-f-2) closest
    other updates is minimum. Tolerates up to f Byzantine clients.
    Tier 4 export.
    """
    n = len(updates)
    if n < 2 * f + 3:
        # Krum requires n >= 2f + 3; fall back to FedAvg.
        return fedavg(updates)
    flat = [torch.cat([t.flatten() for t in u.values()]) for u in updates]
    # Pairwise L2 distances.
    distances = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            d = float((flat[i] - flat[j]).norm() ** 2)
            distances[i, j] = d
            distances[j, i] = d
    # Score = sum of n-f-2 smallest distances to others.
    k = n - f - 2
    scores = np.array([float(np.sort(distances[i, :])[1 : k + 1].sum()) for i in range(n)])
    winner = int(np.argmin(scores))
    return updates[winner]


def trimmed_mean(updates: list[dict[str, Tensor]], trim_fraction: float = 0.2) -> dict[str, Tensor]:
    """Per-coordinate trimmed mean. Drop top + bottom `trim_fraction`."""
    if not updates:
        return {}
    n = len(updates)
    k = int(n * trim_fraction)
    result: dict[str, Tensor] = {}
    for name in updates[0]:
        stacked = torch.stack([u[name] for u in updates], dim=0)
        sorted_vals, _ = torch.sort(stacked, dim=0)
        trimmed = sorted_vals[k : n - k] if k > 0 else sorted_vals
        result[name] = trimmed.mean(dim=0)
    return result
