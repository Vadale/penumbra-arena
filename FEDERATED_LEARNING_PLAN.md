# Penumbra — Federated Learning Extension Plan

Add a federated-learning layer on top of the existing 50-agent
runtime. The unique value of this extension: Penumbra is the ONLY
OSS substrate that already integrates the four ingredients federated
learning needs to be demonstrated end-to-end — multi-agent identity
(Dilithium), homomorphic encryption (CKKS), differential privacy
with budget accounting, and Byzantine-fault-tolerant aggregation
(BLS / slashing primitives we already ship).

**Status**: planning, deferred to post-OSS-launch (per
[`OSS_LAUNCH_ROADMAP.md`](OSS_LAUNCH_ROADMAP.md) Phase L4 — month
4-6 release as v1.2 news angle).

Sister documents:
- [`LOGISTICS_PLAN.md`](LOGISTICS_PLAN.md) — companion extension
  (logistics layer)
- [`BENCHMARK_PLAN.md`](BENCHMARK_PLAN.md) — Penumbra-Bench, which
  this FL extension feeds tasks into
- [`SYNTHETIC_DATA_PLAN.md`](SYNTHETIC_DATA_PLAN.md) — Penumbra-Data,
  which uses FL trajectories as a use case

---

## 1. Why this extension is the most natural fit

| Federated Learning needs | Penumbra already has |
|---|---|
| N participants with stable identities | 50 agents with Dilithium keypairs (PQ-signed every move) |
| Local data on each participant | Per-agent observation history + wallet history |
| Secure aggregation channel | CKKS backend already runs the encrypted heatmap |
| Privacy budget tracking | DP mechanism + accountant already wired (`/dp/budget`) |
| Byzantine fault tolerance | BLS aggregate signature + slashing — the canonical defence |
| Multi-round training loop | LiveTrainer infrastructure already in `packages/learning/penumbra_learning/live_trainer.py` |
| Aggregation server | Orchestrator already wraps the network layer |

Nothing else in the FL OSS ecosystem (Flower, PySyft, FedML, NVFlare)
combines all seven natively. They simulate FL on artificial datasets;
Penumbra would simulate FL on a LIVE multi-agent system that already
runs.

## 2. What this teaches

The hierarchy of FL concepts a learner walks through Penumbra:

1. **FedAvg** (McMahan et al. 2017) — the simplest baseline. Each
   client trains locally, sends weights to a server, server averages,
   broadcasts back. Pedagogically: shows the bandwidth + privacy
   improvements over centralised SGD without obscuring the algorithm.

2. **Secure aggregation via HE** — instead of sending plain weights,
   each client encrypts gradients under CKKS, server SUMS in
   ciphertext space, decrypts only the aggregate. Pedagogically:
   shows why HE is interesting (the SERVER can't see individual
   gradients).

3. **DP-SGD** (Abadi et al. 2016) — add Gaussian noise to gradients
   before sending; clip per-sample contribution; track privacy budget
   per client. Pedagogically: makes the privacy/utility tradeoff
   tangible.

4. **Byzantine-robust aggregation** — Krum (Blanchard et al. 2017),
   Trimmed Mean, Median. Show that a single bad client can poison
   the model under FedAvg, and how the robust variants recover.

5. **Personalised FL** — each client maintains a slight variation
   on the global model (FedProx, PerFedAvg). Shows the spectrum
   from "one model for everyone" to "personalised per client".

6. **Communication-efficient FL** — top-k sparsification, gradient
   compression. Shows the bandwidth dimension.

## 3. Conceptual model — what we add

### 3.1 Local model heads per agent

Today the MAPPO actor is SHARED across all 50 agents (parameter
sharing). In FL we instead give each agent its own local actor head:

```python
@dataclass(slots=True)
class LocalActor:
    """Per-agent actor head + optimizer + local SGD state."""
    agent_id: int
    weights: dict[str, Tensor]
    optimizer_state: dict[str, Tensor]
    local_steps_since_aggregation: int = 0
    privacy_budget_used: float = 0.0
```

### 3.2 Federated round controller

```python
@dataclass(slots=True)
class FederatedRound:
    round_id: int
    started_tick: int
    n_participants: int
    aggregation_method: str  # "fedavg" | "krum" | "trimmed_mean" | "ckks_sum"
    encrypted: bool          # if True, gradients are CKKS-encrypted
    privacy_mechanism: str | None  # "dp-sgd" | None
    convergence_metric: float
    bandwidth_bytes: int     # total wire traffic this round
    aggregation_time_ms: float
```

### 3.3 Aggregation methods

Each is a function `tuple[GradientUpdate, ...] -> GradientUpdate`:

- `fedavg(updates)` — weighted mean by sample count
- `krum(updates)` — pick the update closest to (n-f-2) neighbours
- `trimmed_mean(updates)` — discard top/bottom 10%, average the rest
- `median(updates)` — per-coordinate median
- `ckks_sum(encrypted_updates)` — homomorphic sum + scalar decrypt by
  legitimate aggregator

### 3.4 Byzantine clients

For the attacker tie-in: an "attacker chip" `pna federated-attack`
that turns N agents into Byzantine clients sending malicious
gradients (random noise, sign-flipping, label flipping). The
demo shows:
- FedAvg's accuracy DROPS catastrophically
- Krum / Trimmed Mean maintain accuracy

This becomes the 7th adversarial attack in the catalogue.

## 4. Tier-by-tier implementation

### Tier 1 — FedAvg baseline (~5-6h) — **SHIPPED 2026-05-23**
### Tier 2 — CKKS-encrypted aggregation skeleton — **SHIPPED 2026-05-23**
### Tier 3 — DP-SGD wiring — **partial (DP knobs exposed, accountant is toy)**
### Tier 4 — Byzantine-robust functions (`krum`, `trimmed_mean`) — **shipped as library functions**

Implementation:
- `packages/learning/penumbra_learning/federated.py` — `LocalActor`,
  `FederatedRound`, `FederatedTrainer` (`from_mappo` + `step`),
  `fedavg`, `krum`, `trimmed_mean`, optional DP-SGD clip/noise.
- `packages/transport/penumbra_transport/orchestrator.py` — owns
  `federated_trainer`; `_maybe_step_federated()` fires one FL round
  every 30 ticks when `trainer.enabled`.
- `packages/transport/penumbra_transport/api.py` — `/federated/status`,
  `/federated/start?method={fedavg,ckks_sum}`, `/federated/stop`,
  `/federated/round`, `/federated/dp?sigma=..&clip=..`.
- `apps/web/src/charts/FederatedStatusChart.tsx` — start/stop/run-
  round + DP-SGD controls + recent-round table.

Caveats:
- Tier 1 LocalActor updates are SYNTHETIC gradients (per-agent
  Gaussian noise) — adequate to exercise the round-trip + the
  encrypted-aggregation visual; Tier 2-3 will swap in real local
  SGD over each agent's observation history.
- Tier 2 keeps `ckks_sum` semantics (server never sees individuals)
  but uses a numerical equivalent of FedAvg — actual CKKS sum is
  available in the standalone `/crypto/federated-ckks/demo` for
  inspection.
- DP-SGD privacy accountant is a TOY (epsilon ≈ clip/sigma per step);
  production needs RDP / Gaussian moment accountant.

Tests: 11 unit tests in `packages/learning/tests/test_federated.py`
(FedAvg means, Krum on outliers, TrimmedMean robustness, CKKS-sum
round trips, DP-SGD privacy spend recording, etc.) — all green.

**New file**: `packages/learning/penumbra_learning/federated.py`

Implements:
- `LocalActor` + `FederatedRound` dataclasses (above)
- `fedavg(updates)` aggregation
- `FederatedTrainer` orchestrator that runs N agents' local SGD
  for K rounds, aggregates, broadcasts

**Modify** `live_trainer.py`:
- Add a `mode: "central" | "federated"` toggle
- In federated mode, instead of one centralised PPO update, run K
  local steps per agent + one aggregation step

**Endpoints**:
- `GET /federated/status` — current round, participants, last
  aggregation method, convergence
- `POST /federated/start?method=fedavg&rounds=10` — kick off N rounds
- `POST /federated/stop`
- `GET /federated/history` — last 50 rounds (id, participants,
  bandwidth, time, convergence)
- `GET /federated/per-agent` — local accuracy / loss / privacy spent
  per agent

**Frontend tiles** (`apps/web/src/charts/`):
- `FederatedRoundChart.tsx` — live round, participant grid, per-agent
  status
- `FederatedConvergenceChart.tsx` — accuracy + loss over rounds
- `FederatedBandwidthChart.tsx` — bytes-per-round time series
- `FederatedAggregationCompareChart.tsx` — A/B compare two
  aggregation methods running in parallel slots

**Tests** in `packages/learning/tests/test_federated.py`:
- `test_fedavg_matches_centralised_when_no_data_heterogeneity`
- `test_fedavg_recovers_global_optimum_on_iid_data`
- `test_federated_round_records_bandwidth`
- `test_local_actor_serialisation_roundtrip`

### Tier 2 — CKKS-encrypted aggregation (~4-5h)

**Modify** `federated.py`:
- Add `EncryptedUpdate` dataclass wrapping a list of CKKS ciphertexts
- Add `ckks_aggregate(encrypted_updates)` that performs homomorphic
  sum + scalar decrypt of the aggregate

**Pedagogical demo**:
- Server NEVER sees individual gradients (only encrypted ones)
- Aggregate decryption requires the legitimate aggregator's secret key
- Tampering with one ciphertext propagates to the aggregate but
  doesn't reveal the others (no auxiliary leak)

**Frontend**:
- `FederatedEncryptionChart.tsx` — ciphertext byte sizes per round +
  serialisation hex preview + decryption error magnitude

**Tests**:
- `test_ckks_aggregate_matches_plain_fedavg_within_tolerance` —
  approximation error must be < 1e-4 per parameter
- `test_ckks_aggregate_hides_individual_gradients` — verify the
  server only ever holds ciphertexts

### Tier 3 — DP-SGD privacy mechanism (~3-4h)

**Modify** `federated.py`:
- Add `DPSGDClipper` that clips per-sample gradient l2 norm
- Add Gaussian noise to clipped gradients before sending
- Track privacy spent using the existing `PrivacyBudget` accountant

**Frontend**:
- `FederatedDPSGDChart.tsx` — per-agent privacy spent over rounds +
  global privacy budget bar + utility-vs-privacy curve

**Tests**:
- `test_dpsgd_gradient_l2_bounded_after_clip`
- `test_dpsgd_privacy_spent_matches_RDP_accountant`
- `test_dpsgd_utility_degrades_gracefully_with_noise_scale`

### Tier 4 — Byzantine-robust aggregation (~4-5h)

**Modify** `federated.py`:
- Add `krum(updates, f)` — Krum aggregator (f = number of Byzantine)
- Add `trimmed_mean(updates, trim_fraction)`
- Add `median_aggregate(updates)` per-coordinate

**New attack**: `packages/attacker/penumbra_attacker/attacks/federated_byzantine.py`

```python
def demo(n_byzantine: int = 5, attack: str = "noise") -> ByzantineFedResult:
    """Run FedAvg vs Krum vs Trimmed Mean under N Byzantine clients.

    Attack variants:
    - "noise": random Gaussian noise
    - "sign_flip": flip the sign of true gradient
    - "label_flip": flip the labels of local data (data poisoning)
    """
```

**New CLI command**: `pna federated-attack --byzantine 5 --attack sign_flip`

**Frontend**:
- `FederatedByzantineChart.tsx` — accuracy curves for each
  aggregation method under attack; the divergence is the visual
  payoff

**Tests**:
- `test_krum_resists_n_byzantine_under_threshold`
- `test_fedavg_breaks_under_one_byzantine` (the canonical failure)
- `test_trimmed_mean_recovers_from_outliers`

### Tier 5 — Personalised + communication-efficient FL (~6-8h)

**Optional**. Adds:
- FedProx (regularised local objective)
- PerFedAvg (meta-learning approach)
- Top-k gradient sparsification
- Quantised gradient transmission (8-bit, 4-bit)

This is graduate-school-level content; mark as "research extension"
for the academic audience.

## 5. New configuration

```python
# packages/learning/penumbra_learning/federated.py
_DEFAULT_LOCAL_STEPS_PER_ROUND: Final[int] = 16
_DEFAULT_DP_NOISE_SIGMA: Final[float] = 0.5
_DEFAULT_DP_L2_CLIP: Final[float] = 1.0
_DEFAULT_KRUM_F: Final[int] = 5
_DEFAULT_TRIMMED_FRACTION: Final[float] = 0.2
```

Environment variables:
- `PENUMBRA_FEDERATED_ENABLED={0,1}`
- `PENUMBRA_FEDERATED_DEFAULT_METHOD={fedavg,ckks_sum,krum,trimmed_mean}`
- `PENUMBRA_FEDERATED_DP_NOISE=0.5`

## 6. Memory + performance impact

- Per-agent local actor: ~80 KB per agent × 50 = 4 MB additional RSS
- Per-round aggregation work: O(n_agents × n_params)
- CKKS aggregation: ~1.5× slower than plain aggregation but
  encryption work dominates already-existing heatmap cost (no new
  peak)
- Estimated overhead: ~10-15% additional CPU during active FL
  training rounds

Compatible with the 8 GB M4 budget.

## 7. Tests we'd add

| Tier | Tests | Count |
|---|---|---|
| 1 | FedAvg correctness + bandwidth tracking | 4 |
| 2 | CKKS aggregation correctness + privacy properties | 2 |
| 3 | DP-SGD clipping + accountant alignment | 3 |
| 4 | Byzantine robustness under three attack vectors | 4 |
| 5 | FedProx + sparsification | 3 |
| **Tier 1-4 total** | | **13** |

Property-based tests:
- Aggregation commutativity: order of clients doesn't change
  FedAvg result
- Privacy budget monotonicity: per-client spent never decreases
- Krum invariance: same N clients with same updates produce same
  Krum winner across runs

## 8. Acceptance criteria

Tier 1 done when:
- [ ] 4 FL tests pass
- [ ] 3 new dashboard tiles populate live
- [ ] FedAvg matches centralised PPO on a 2-agent toy task within
  1 round
- [ ] Backend regression: existing 302/302 tests + 13 new = 315
- [ ] One PR / one tag `federated-tier-1`

Tier 2-4 done when (each):
- Independent PR + tests + tiles + docs
- Pedagogical signal demonstrably visible

## 9. Out of scope (explicit)

- Cross-silo FL (only cross-device modelled)
- Heterogeneous client architectures (all clients share NN topology)
- Vertical FL (only horizontal: same features, different samples)
- Real-network bandwidth simulation (we record bytes but don't
  inject network delay; can be a later extension)
- FedML / Flower API compatibility (custom Penumbra API for
  pedagogical clarity)

## 10. Pedagogical audience map

| Tier | Audience | Concepts taught |
|---|---|---|
| 1 | Undergraduate ML | FedAvg, client-server, parameter sharing |
| 2 | Grad-level crypto + ML | HE-based secure aggregation, CKKS in production |
| 3 | Privacy researchers + compliance | DP-SGD, accountant, utility-privacy tradeoff |
| 4 | Adversarial ML + safety | Byzantine robustness, model poisoning, robust statistics |
| 5 | Researchers | Personalisation, communication efficiency |

## 11. References

For implementers + `concept_taught` docstrings:
- McMahan, Moore, Ramage, Hampson, Arcas. "Communication-Efficient
  Learning of Deep Networks from Decentralized Data." AISTATS 2017
  (FedAvg).
- Bonawitz et al. "Practical Secure Aggregation for Privacy-
  Preserving Machine Learning." CCS 2017.
- Abadi et al. "Deep Learning with Differential Privacy." CCS 2016
  (DP-SGD).
- Blanchard, El Mhamdi, Guerraoui, Stainer. "Machine Learning with
  Adversaries: Byzantine Tolerant Gradient Descent." NeurIPS 2017
  (Krum).
- Kairouz et al. "Advances and Open Problems in Federated
  Learning." Foundations and Trends in ML, 2021 (the survey).
- Mironov. "Rényi Differential Privacy." CSF 2017 (the accountant
  Penumbra uses).

## 12. Implementation order (recommended)

1. Read this document end-to-end.
2. Refresh memory of:
   - `packages/learning/penumbra_learning/mappo.py`
   - `packages/learning/penumbra_learning/live_trainer.py`
   - `packages/crypto/penumbra_crypto/ckks.py`
   - `packages/crypto/penumbra_crypto/dp.py`
3. Implement Tier 1 (FedAvg) in this order:
   1. `federated.py` module + unit tests
   2. `live_trainer.py` mode toggle
   3. Endpoints
   4. Frontend charts
   5. AnalyticsPanel tiles
   6. ROADMAP + CLAUDE.md update
4. Verify full gate.
5. Tag `federated-tier-1`.
6. Tier 2 + 3 + 4 as independent follow-ups.

---

**End of plan.** This extension positions Penumbra as the ONE OSS
substrate where federated learning teaching and research can happen
end-to-end on a single Mac mini.
