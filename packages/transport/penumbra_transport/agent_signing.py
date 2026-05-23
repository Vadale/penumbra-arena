"""Per-agent Dilithium signing of moves.

Concept taught: post-quantum signatures are not just a primitive in
`crypto/pq.py` — every agent action in the running system is signed
and verified. This module hosts the per-agent keystore and a
verify-then-apply gate the orchestrator uses each tick.

Why this matters
----------------
If the simulation accepted unsigned moves, a malicious client (or a
network adversary) could inject "move agent 7 to node 3" packets the
server has no way to authenticate. With per-agent Dilithium keys at
boot, every move comes with a 3309-byte signature over the canonical
(tick, agent_id, target_node) tuple — replay and impersonation are
out of bounds.

Pedagogical caveats
- In our single-process setup the keys live in the same Python
  process as the moves they authenticate, so the threat model is
  purely demonstrative. The *protocol* is what's load-bearing: an
  out-of-process agent (Phase 8+) would keep its secret key on its
  own host and sign there.
- We track verify counters so the dashboard can surface aggregate
  stats — `/agents/signing-stats` is the inspection seam.

Phase 6a Tier 2: per-agent rejection counters drive an automatic
trade-block event. When agent X accumulates ``_TRADE_BLOCK_THRESHOLD``
rejections within ``_TRADE_BLOCK_WINDOW_TICKS``, the keystore invokes
the injected ``on_agent_blocked`` callback so the orchestrator can
emit ``agent.blocked`` and propagate the block to Market + logistics +
FL trainer. The cool-off window (``_BLOCK_COOLOFF_TICKS``) defines
``until_tick`` so the auto-unblock at the orchestrator can fire on the
right tick.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from penumbra_crypto import pq

_TRADE_BLOCK_THRESHOLD: Final[int] = 3
_TRADE_BLOCK_WINDOW_TICKS: Final[int] = 300  # 30s @ 10 Hz
_BLOCK_COOLOFF_TICKS: Final[int] = 600  # 60s @ 10 Hz
_REJECTION_HISTORY_CAP: Final[int] = 20


BlockCallback = Callable[[int, int], None]
"""Callback signature: (agent_id, until_tick) -> None.

Wired by the orchestrator to emit an ``agent.blocked`` event onto
the bus. Kept as a plain callable so the keystore stays independent
of the transport layer at import time.
"""


@dataclass(slots=True)
class SigningStats:
    """Counters for the dashboard."""

    verified: int = 0
    rejected: int = 0


@dataclass(slots=True)
class AgentKeystore:
    """Per-agent Dilithium keypairs + verification counters.

    `keypairs[i]` corresponds to agent id i. Use `sign_move()` /
    `verify_move()` as a pair on the orchestrator's hot path.
    """

    keypairs: list[pq.SigKeypair] = field(default_factory=list)
    stats: SigningStats = field(default_factory=SigningStats)
    on_agent_blocked: BlockCallback | None = None
    _recent_rejections: dict[int, deque[int]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=_REJECTION_HISTORY_CAP))
    )
    _blocked_until: dict[int, int] = field(default_factory=dict)

    @classmethod
    def for_n_agents(cls, n: int) -> AgentKeystore:
        return cls(keypairs=[pq.sig_keygen() for _ in range(n)])

    def sign_move(self, *, agent_id: int, tick: int, target_node: int) -> bytes:
        """Produce a Dilithium signature over the canonical move tuple."""
        keypair = self.keypairs[agent_id]
        message = canonical_move_bytes(tick=tick, agent_id=agent_id, target_node=target_node)
        return pq.sign(keypair.secret_key, message)

    def verify_move(
        self,
        *,
        agent_id: int,
        tick: int,
        target_node: int,
        signature: bytes,
    ) -> bool:
        """Check that `signature` is a valid Dilithium sig on the canonical bytes."""
        if not 0 <= agent_id < len(self.keypairs):
            self.stats.rejected += 1
            self._record_rejection(agent_id=agent_id, tick=tick)
            return False
        message = canonical_move_bytes(tick=tick, agent_id=agent_id, target_node=target_node)
        ok = pq.verify(self.keypairs[agent_id].public_key, message, signature)
        if ok:
            self.stats.verified += 1
        else:
            self.stats.rejected += 1
            self._record_rejection(agent_id=agent_id, tick=tick)
        return ok

    def _record_rejection(self, *, agent_id: int, tick: int) -> None:
        """Append a rejection tick and fire ``on_agent_blocked`` on threshold.

        The rolling window is bounded by ``_REJECTION_HISTORY_CAP``
        entries; only those within ``_TRADE_BLOCK_WINDOW_TICKS`` of the
        current tick count toward the threshold. While an agent is in
        an active cool-off (``until_tick`` not yet reached) we skip
        emitting to keep the callback idempotent under bursty rejects.
        """
        history = self._recent_rejections[agent_id]
        history.append(int(tick))
        cutoff = int(tick) - _TRADE_BLOCK_WINDOW_TICKS
        recent_in_window = sum(1 for t in history if t >= cutoff)
        if recent_in_window < _TRADE_BLOCK_THRESHOLD:
            return
        active_until = self._blocked_until.get(agent_id, -1)
        if active_until > int(tick):
            return
        until_tick = int(tick) + _BLOCK_COOLOFF_TICKS
        self._blocked_until[agent_id] = until_tick
        if self.on_agent_blocked is not None:
            self.on_agent_blocked(int(agent_id), until_tick)


def canonical_move_bytes(*, tick: int, agent_id: int, target_node: int) -> bytes:
    """Stable byte representation the prover and verifier both agree on.

    Layout: domain-tag || tick(16 BE) || agent_id(8 BE) || target_node(8 BE).
    """
    return (
        b"penumbra-move-v1|"
        + tick.to_bytes(16, "big")
        + agent_id.to_bytes(8, "big")
        + target_node.to_bytes(8, "big")
    )
