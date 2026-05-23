# Crypto + Surveillance Attack/Defense Lab — Phase 5 Plan

**Status**: planning, deferred to post-OSS-launch (target v2.0,
month 3-4 after public release per `OSS_LAUNCH_ROADMAP.md`).

**Sister docs**: `LOGISTICS_PLAN.md`, `FEDERATED_LEARNING_PLAN.md`,
`BENCHMARK_PLAN.md`, `SYNTHETIC_DATA_PLAN.md`, `SECURITY_AUDIT.md`,
`INTER_SILO_INTEGRATION_PLAN.md` (Phase 6a — runs in parallel),
`OPERATOR_MODE_PLAN.md` (Phase 6b — consumes Phase 5 modules as
operator actions).

**Why Phase 5**: today Penumbra is a *passive* crypto demo — 10 tile
panels show CKKS, Dilithium, Groth16 etc. working correctly. Phase 5
makes it *interactive*: the user writes attack code, the system
defends, and the simulation is the lab.

---

## 1. Vision — what becomes possible

After Phase 5, a user opens the dashboard and can:

1. **Capture-the-flag mode**. The dashboard shows a "current
   challenge" — e.g. "you have 60 s to extract agent_12's position
   from these 1000 DP-noised aggregates with ε=0.1". The user writes
   a Python attack function in the in-browser REPL, hits **Try**,
   the system runs it against the live arena, and reports
   success/failure + leaderboard score.

2. **Custom policy injection**. Paste a Python function
   `def attack(agent_state, observations) -> action`. It gets
   sandboxed, registered as a "guest agent", and runs against the
   live arena alongside MAPPO. Useful for testing attack policies
   (adversarial inputs, reward poisoning, byzantine behaviour).

3. **Surveillance simulator**. Toggle a "tracker network" overlay:
   every agent leaks a configurable mix of fingerprintable signals
   (timing, action histogram, trajectory shape). A re-identification
   attacker tries to link de-anonymised traces back to identities.
   The user tunes countermeasures (request padding, decoy traffic,
   k-anonymity grouping, data poisoning) and watches the attack
   accuracy curve drop.

4. **Jupyter bridge**. `%load_ext penumbra` enables
   `%penumbra` magic commands in a notebook to attach to the
   running arena. Read live state, inject probes, run attacks
   from a familiar surface.

5. **Replay + branching**. Snapshot 100 ticks. Branch the
   simulation N times with different attack variants applied.
   Compare outcomes side-by-side.

---

## 2. New crypto primitives (cutting-edge 2026)

Penumbra already has CKKS, TFHE, Kyber, Dilithium, BLS, VRF, VDF,
Groth16, Shamir, Beaver, Pedersen, Schnorr. Phase 5 adds the
*missing* shelf:

### 2.1 ZK proof systems (post-Groth16)
- **STARK / Plonky3** — no trusted setup, post-quantum-secure
  proofs. Module: `packages/crypto/stark.py` (verifier only;
  proofs imported from `circom-stark` toolchain locally).
  *Tile*: "Plonky3 verifier — block proofs without a trusted
  ceremony".
- **Verkle trees** — replace Merkle for block payload commitments.
  Constant-size proofs via KZG (we already have py_ecc BN128
  pairings; we add BLS12-381 for KZG soundness).
  *Tile*: "Verkle: Merkle's modern cousin — proof size vs depth"
  with side-by-side comparison.
- **Lookup arguments (Lasso, Jolt)** — show how the cost of proving
  "this value is in a set" went from O(log n) to O(1) amortised in
  2024-25.

### 2.2 Threshold signatures (post-BLS)
- **FROST** — non-interactive threshold Schnorr signatures used
  in Bitcoin Lightning + Coinbase MPC custody.
  Module: `packages/crypto/frost.py`.
  Integration: chain validators can use FROST instead of BLS as a
  toggle; the user compares signature size + aggregation cost.
- **GG18 / GG20** — threshold ECDSA (the Fireblocks/MPC-wallet
  scheme).
  Module: `packages/crypto/threshold_ecdsa.py`.
- **ROAST** — robust FROST against adversarial signers.

### 2.3 Hash-based PQ signatures (sibling of Dilithium)
- **SPHINCS+** — stateless hash-based PQ signature, NIST-
  standardised as ML-DSA's stateless complement.
  Module: `packages/crypto/sphincs.py` (wrap pqcrypto library).
  *Tile*: "SPHINCS+ vs Dilithium: which post-quantum signature
  pays the smaller bill, when?"
- **XMSS / LMS** — stateful hash-based, RFC 8391 / NIST SP 800-208.
  Used in firmware signing today.

### 2.4 Anonymous credentials
- **BBS+ signatures** — selective disclosure credentials (you can
  prove you have a credential without revealing it). Powers
  EU Digital Identity Wallet 2026.
  Module: `packages/crypto/bbs_plus.py`.
  Integration: agents prove they're authorised carriers without
  revealing their identity to suppliers.
- **Coconut** — distributed-issuance variant.

### 2.5 Garbled circuits (Yao)
- **Garbled Boolean circuits** — the missing SMPC primitive.
  Module: `packages/crypto/educational/yao.py`.
  *Tile*: "Yao's millionaires problem: agent A and agent B compare
  inventory values without revealing them".

### 2.6 Private set intersection (PSI)
- **PSI from OPRF** — agents find common nodes / common products
  without revealing their full inventory.
  Module: `packages/crypto/psi.py`.
  *Tile*: "PSI: where do these two carriers want to trade?
  (without leaking the rest of their routes)".

### 2.7 Mix nets
- **Loopix-style mix** — agents route messages through cover
  traffic so the chain observer can't link sender→receiver.
  Module: `packages/crypto/mix_net.py` (educational, in-process).
  Integration: dispatcher routes orders through a mix net; the
  arena heatmap is what the *adversary* sees; the real flow is
  hidden.

### 2.8 Functional encryption (taste)
- **Inner-product encryption (IPE)** — server computes
  `inner_product(client_vec, encrypted_db_vec)` without learning
  either. *Tile only* (proof-of-concept; not on hot path).

---

## 3. New attack modules

Add to `packages/attacker/attacks/`:

### 3.1 Re-identification / linkability (extends current)
- `linkability_advanced.py` — beyond 1-NN: train a small classifier
  on historical trajectories (XGBoost / GNN), measure top-1 / top-5
  accuracy. The current `linkability.py` is the toy version.
- `trajectory_fingerprint.py` — Hidden Markov Model over agent
  action sequences; even *with* per-action DP noise, the HMM may
  still pin agents to factions.

### 3.2 Browser-style fingerprinting (new vertical)
- `agent_fingerprint.py` — extract from each agent's observable
  behaviour:
  - **Timing fingerprint** — micro-latencies in their actions
  - **Action histogram fingerprint** — preferred action distribution
  - **Trajectory shape** — characteristic curvature / dwell times
  - **Trade pattern** — buy/sell ratio, product preferences
  An adversary fuses these signals; the user tunes the
  countermeasures.

### 3.3 Side-channel taxonomy
- `cache_sidechannel.py` — Flush+Reload-style timing measurements
  against CKKS operations (educational only — modern CKKS
  implementations are constant-time, the point is to *show* the
  attack methodology).
- `power_sidechannel_sim.py` — simulated power trace + DPA-style
  analysis on a toy AES.

### 3.4 ML attacks
- `membership_inference.py` — does this observation appear in the
  MAPPO training set? Standard Shokri et al. 2017 shadow-model
  technique.
- `model_inversion.py` — reconstruct training observations from
  policy gradient leakage (FL Tier 2-3 ties in directly).
- `reward_poisoning.py` — inject perturbed rewards in 5% of training
  episodes; measure the policy degradation.
- `backdoor_fl.py` — malicious FL client injects a trigger pattern;
  measure that Krum/TrimmedMean (already in
  `packages/learning/federated.py`) filter it correctly.
- `adversarial_examples.py` — gradient-based perturbations on
  agent observations to flip the MAPPO action.

### 3.5 Network attacks (mix-net adversary)
- `mix_traffic_analysis.py` — observe the encrypted flow,
  reconstruct the routing graph despite mixing.
- `cookie_replay.py` — replay session tokens; verify the chain
  rejects them (extends existing `replay.py`).

---

## 4. New defense modules

Add to `packages/crypto/defenses/` (new sub-package):

- `data_poisoning.py` — *defender-side*: inject decoy traces in
  released aggregates so the linkability attacker fits a wrong
  model. Tuneable poisoning rate; measures the cost (utility
  loss) vs benefit (attack accuracy drop).
- `padding.py` — request padding to a fixed size; cover traffic
  schedules.
- `k_anonymity.py` — release per-(city, product) trades only when
  at least k agents share that bucket.
- `l_diversity.py` — k-anonymity + diversity on the sensitive
  attribute (product category).
- `gan_defenses.py` — train a small CycleGAN on the trajectory
  feature distribution; release the *generated* trace instead of
  the real one. Privacy-utility tradeoff measured.
- `request_obfuscation.py` — bonferroni-correct the DP queries the
  adversary issues, so they exhaust the budget faster.

---

## 5. Interactive surfaces

### 5.1 Custom policy injection
**New endpoint**: `POST /attacker/policy` with body
`{name: str, code: str, scope: "agent_X" | "all"}`.

Backend (`packages/attacker/policy_sandbox.py`):
- Parse the code; check it defines a `policy(state, observation)`
  function.
- Run it in a `RestrictedPython` sandbox with import whitelist
  (numpy, custom helpers, NO file/network/subprocess).
- Time-budget per call: 50 ms.
- On every tick the orchestrator calls the registered sandboxed
  policy in place of MAPPO for the scoped agent(s).

**Tile**: "Custom Agent Policy" — Monaco editor in-browser, a
**Try** button, an **Adopt** button (promotes to permanent guest
agent), a **Diff vs MAPPO** view.

### 5.2 Capture-the-flag mode
**New module**: `packages/ctf/challenges/` — each challenge a YAML
spec:
```yaml
id: ctf-dp-recon-001
title: "Reconstruct positions from DP-noised aggregates"
setup:
  dp_epsilon: 0.1
  n_aggregates: 1000
  target_agent: 12
acceptance:
  predict_position_within: 2     # nodes
  in_seconds: 60
flag_template: "PEN{{position_hash}}"
```

**New endpoint**: `GET /ctf/challenges` and
`POST /ctf/submit/{id}` with body `{flag: str}`.

**Tile**: leaderboard per challenge; total CTF score per user
(session-based first, OAuth later).

### 5.3 Jupyter bridge
**New package**: `packages/notebook/penumbra_notebook/__init__.py`
that registers IPython magics:
- `%penumbra connect` — attach to running arena via WS
- `%penumbra snapshot` — capture state to a notebook cell
- `%%penumbra attack` — cell-as-attack body; eval against live
  state

### 5.4 Replay + branching
**Extend** `packages/transport/penumbra_transport/world.py`:
- `world.save(name)` already exists.
- Add `world.branch(name, n_branches=5)` that snapshots the
  current state to N copies; each branch can be advanced
  independently for `--ticks` ticks and the dashboard shows them
  side-by-side.

---

## 6. Integration with existing pillars — REAL ties

This is the user's question: "does it integrate with logistics +
statistics + NN + ML?" Answer: yes, *organically*. Each pillar
becomes attackable AND defensible. No pillar is left as a passive
spectator.

### 6.1 Logistics ↔ Crypto

| Existing logistics feature | Phase 5 crypto attack | Phase 5 crypto defense |
|---|---|---|
| Carrier dispatch (`assign_carriers`) | Adversary observes dispatch and *re-identifies* which agent is the most productive carrier from the agent_earnings KPI | Mix-net routing of dispatch messages; PSI for "who carries what" without leaking the full assignment |
| Order book (`LogisticsMempool`) | Order timing fingerprint links carriers to suppliers | BBS+ anonymous credentials: carrier proves "I'm authorised" without revealing identity |
| Multi-echelon supply chain (`logistics_echelon`) | Bullwhip-amplified leakage: upstream tier sees aggregated downstream demand, can infer city-level patterns | k-anonymity on the demand release; threshold ECDSA on supplier signatures |
| VRP solver (`logistics_or`) | Solving the VRP reveals the optimal route → de-anonymises which carrier serves which sector | Garbled-circuit VRP: compute route privately |
| Cargo capacity | Inventory-level fingerprint identifies high-volume carriers | Pedersen commits to cargo levels; reveal only via ZK proof of compliance |

### 6.2 Statistics ↔ Crypto

| Existing analytics feature | Phase 5 crypto attack | Phase 5 crypto defense |
|---|---|---|
| Per-product OHLC candles | Trade-timing fingerprint (Netflix-prize style re-identification) | DP-noised candles; release with k-anonymity bucketing |
| CPI / inflation index | Adversary infers individual agent's purchase patterns from CPI residuals | Functional encryption: server computes CPI without seeing per-agent trades |
| Wealth distribution / Gini | Top-1 wealthy agent trivially de-anonymised | Differentially-private top-k release |
| GARCH volatility forecasting | Data poisoning: inject fake trades to skew volatility models | Robust statistics (Huber, MAD-based estimators) |
| Bayesian posterior over hidden positions (NumPyro SVI) | Membership inference on the posterior | DP-SGD on the SVI inference itself |
| HDBSCAN clustering | Cluster membership leakage | k-anonymity on cluster labels |

### 6.3 Neural networks ↔ Crypto

| Existing NN feature | Phase 5 crypto attack | Phase 5 crypto defense |
|---|---|---|
| MAPPO actor (shared policy) | Membership inference: which trajectories trained me? | DP-SGD with REAL per-example clipping (already shipped post-audit) |
| MAPPO checkpoint distribution | Model extraction: query the policy enough times to clone it | Watermarking via DAWN or PRADA; signed checkpoints (Dilithium) |
| GATv2 pathfinder | Adversarial-perturbation on edge costs flips the path | Adversarial training; certified robust GNN (Smoothing) |
| Live PPO training (LiveTrainer) | Reward poisoning during live training | Robust aggregator; reward smoothing; baseline subtraction |
| Saliency / GAT-attention introspection | Model inversion via gradient leakage | Gradient quantization; FedProx proximal term (already in Tier 5) |
| Federated learning (Tier 1-5) | Backdoor injection from malicious clients | Krum / TrimmedMean (already in Tier 4) + Byzantine-Aware secure aggregation |
| Penumbra-Bench tasks (PA1/AR1/MC1/PB1/LR1) | New CTF challenges target each axis explicitly | Each defense becomes a benchmark submission |

### 6.4 RL / ML ↔ Crypto

| Existing RL feature | Phase 5 crypto attack | Phase 5 crypto defense |
|---|---|---|
| Self-play environment (PenumbraEnv) | Adversarial policy injection (custom guest agent) | Sandbox limits + behavioural anomaly detection |
| Reward weights (RewardWeights singleton) | Inflate `logistics_dispatch_bonus` to incentivise stalker behaviour | Multi-objective reward shaping with bounded perturbation |
| Per-agent observation history (FL buffer) | Behavioural fingerprint from action histograms | Action obfuscation: occasional random actions; temperature schedule |
| Bench composite score | Game the composite by sacrificing low-weight tasks | Composite weight re-tuning + new tasks |
| Action histogram | Reveals policy preferences across population | Action padding (always emit a "stay" channel); per-class noise |

### 6.5 Cross-pillar emergent stories

Phase 5 unlocks *narrative* lessons that span all pillars:

- **"The bullwhip leak"**: upstream supplier observes aggregated
  demand → infers city-level event → fingerprints which carrier
  was dispatched → de-anonymises the agent → reads its MAPPO
  policy via membership inference → predicts its next trade →
  inserts a poisoning trade → corrupts GARCH → mis-predicts
  volatility → mis-prices ask → cascades into wallet wealth shift.
  ONE STORY THAT TOUCHES EVERY PILLAR.

- **"The honest validator"**: BLS-aggregated finality + Krum FL
  aggregator + DP queries + k-anonymity releases all stacked
  together let an honest validator survive 20% Byzantine peers
  AND 30% data poisoning AND 5% membership-inference budget.
  The user *measures* each defense's contribution in isolation
  and combined.

---

## 7. Tier-by-tier implementation

### Tier 1 — Foundation primitives (~8-10h)
- `frost.py`, `sphincs.py`, `verkle.py` (verifier), `psi.py`,
  `yao.py` minimal implementations.
- Property tests for each.
- 5 new dashboard tiles (one per primitive).

### Tier 2 — Attack vertical (~10-12h)
- 6 new attack modules: `agent_fingerprint`, `trajectory_fingerprint`,
  `membership_inference`, `model_inversion`, `reward_poisoning`,
  `cache_sidechannel`.
- Each with a defense docstring + a CTF challenge YAML.
- `pna` CLI subcommands for each.

### Tier 3 — Defense vertical (~8-10h)
- `defenses/` sub-package: `data_poisoning`, `padding`,
  `k_anonymity`, `l_diversity`, `gan_defenses`.
- Each with a dashboard tile showing the privacy-utility curve.

### Tier 4 — Interactive surfaces (~12-14h)
- Custom policy injection backend + Monaco editor tile.
- CTF backend + leaderboard tile + 10 starter challenges.
- Jupyter `%penumbra` magics.
- Replay + branching backend extension.

### Tier 5 — Cross-pillar narrative content (~10-12h)
- 8-10 "story mode" tutorials that walk through cross-pillar
  attacks (e.g. "the bullwhip leak" above).
- Each is a YAML lesson under `packages/shell_coach/lessons/`
  reused for the storytelling but rendered in a new "Story Mode"
  UI in the dashboard.

**Total Phase 5 effort**: ~50-60h of work — roughly the same as
the entire Phase 2.5 we just shipped.

---

## 8. Constraints + acceptance criteria

- All primitives **must** integrate via the existing 5-step
  dashboard pattern (endpoint + chart + DetailModal + Cell +
  vite proxy if new prefix).
- All new attacks **must** include a defense in the docstring AND
  a measurable mitigation in `defenses/`.
- The Jupyter bridge **must not** open a hole into the FastAPI
  process — read-only WS access + sandboxed eval cells only.
- CTF challenge YAML schema **must** be JSON-Schema-validatable
  (re-use the bench validator pattern).
- Crypto-auditor sign-off required for every primitive in §2 and
  every defense in §4.

---

## 9. Pedagogical / business positioning

Phase 5 turns Penumbra from "interesting demo" into "the place
where you actually learn this". The four target communities:

1. **CS / security students** doing crypto courses — get an
   end-to-end working lab.
2. **Privacy engineers** at banks / wallets / health-tech needing
   FROST + threshold-ECDSA + DP intuition.
3. **ML safety researchers** wanting to measure adversarial
   robustness + privacy leakage on a shared benchmark.
4. **EU AI Act compliance teams** needing tooling for adversarial-
   robustness evaluation (Article 15) + privacy-by-design (Article
   10).

Risks:
- Scope creep — the v1.0 OSS launch could get diluted. Mitigation:
  PHASE 5 is post-launch. Don't ship anything in §1-§8 until v1.0
  has 500+ stars OR 10+ benchmark submissions.
- Crypto correctness — each primitive is a footgun. Mitigation:
  every PR routes through `crypto-auditor` agent; every primitive
  has an attack demo proving the defense actually works.

---

## 10. Out of scope (for Phase 5)

- Real KMS / HSM integration
- Real multi-machine MPC (single-host pedagogy only)
- Mobile responsive
- Production-grade STARK proving (verifier only; provers run via
  external toolchain locally)
- Fully homomorphic encryption beyond CKKS/TFHE (TFHE-rs for
  arbitrary boolean circuits)
- Hardware side-channels (no actual EM/power measurement; we
  simulate the traces in software for pedagogy)
