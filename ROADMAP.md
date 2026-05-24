# Penumbra — Roadmap

The build map, updated as we ship. Phases listed with their tag and
the deferred items spelled out honestly so it stays useful as a
navigation document even after the codebase walks away from the plan.

Sister document: `PROMPTING_GUIDE.md` has the per-module recipes.

## Project at a glance

Penumbra is a perpetual privacy-preserving multi-agent arena. N=20–50
agents compete on a procedurally dynamic graph; their state is
encrypted (CKKS), the spectator sees only aggregates, match outcomes
are anchored on a local PoS-VRF blockchain. The dashboard hosts a live
analytics stream, a 3D arena rendered with fuzzy agent halos, an
Attacker Console (`pna`), a Shell Coach with `psh`, and a Chain
Explorer — all on a single screen.

The project's purpose is **learning**: every package is a
self-contained entry point for a guided conversation with `@learner`
(math / crypto / stats / NN) or `@shell-coach` (Unix on macOS).

## Pillars and where they live

| Pillar | Primary packages | Status |
|---|---|---|
| Neural networks | `learning/` (MAPPO, GATv2) | done |
| Cryptography | `crypto/`, `chain/` | done (TFHE deferred) |
| Statistics & econometrics | `analytics/` | 12 of 13 modules done (topics deferred) |
| Linear algebra & topology | `analytics/linalg.py`, `analytics/topology.py`, `analytics/transport.py` | done |
| Adversarial intuition | `attacker/` | done |
| Unix/macOS shell | `shell_coach/` | done |
| Domain | `core/` (integration seam) | done |
| I/O | `transport/`, `apps/web/` | done |

## Shipped phases

Each phase ends with a tag — `git checkout phase-X-Y` rolls back.

### Phase 0 — Foundations · `phase-1-done` carries it

- `git init` on main, .gitignore / .gitattributes
- CLAUDE.md (project guardrails)
- 6 specialised agent files in `.claude/agents/`
- ROADMAP.md (this file) + PROMPTING_GUIDE.md
- Private GitHub repo `penumbra-arena` created and tracked

### Phase 1 — Skeleton + perpetual loop · `phase-1-done`

- uv + pnpm workspaces, docker-compose, justfile, pre-commit
- `core/{rng,arena,agent,match,simulation}.py` — perpetual loop, OU
  edge costs, migrating goals, weather events
- FastAPI + WebSocket transport with msgpack frames
- React 19 + Vite + r3f + zustand frontend shell
- 10 Hz tick rate verified via live smoke test

### Phase 2 — Crypto stack · `phase-2-live`

- **CKKS** via TenSEAL (OpenFHE-Python only ships Linux x86_64 wheels)
- **DP** Laplace mechanism + mandatory `PrivacyBudget` accountant
- **Post-quantum** ML-KEM-768 (Kyber) + ML-DSA-65 (Dilithium) via pqcrypto
- **BLS** aggregate signatures on BLS12-381 via py_ecc
- **Schnorr-VRF** in pure Python for leader election
- **Wesolowski VDF** for unbiasable randomness (`phase-2-6-vdf-snark`)
- **Groth16 verifier** + snarkjs loader (`phase-2-6-vdf-snark`)
- **Educational from-scratch** Shamir SS + Beaver triples + Pedersen
  commitments + Schnorr Σ-protocol with Fiat-Shamir
- **Wired into runtime**: CKKS-encrypted heatmap @ 1 Hz from
  per-agent positions → server only ever sees aggregates

### Phase 3 — Blockchain · `phase-3-wired`

- Block + Merkle tree (domain-separated SHA-256 hashes)
- PoS-VRF leader election + BLS aggregate finality (>2/3 quorum)
- Mempool + Node + match-outcome → block production loop
- `/chain/{latest,blocks,block/{hash}}` REST endpoints
- Frontend Chain Explorer panel

### Phase 4 — Learning · `phase-4-done`

- PettingZoo `ParallelEnv` wrapping `core.Simulation`
- MAPPO (CleanRL-style, MPS) — Actor + centralised Critic, PPO clip,
  GAE, gradient clipping
- GATv2 pathfinder *from scratch* (no PyTorch Geometric dep)
- Self-play trainer with checkpoint save/load
- `scripts/train_initial_checkpoint.py`

### Phase 5 — Analytics · `phase-5-wired` + `phase-5-causal`

- 12 modules (see analytics README)
- `DashboardPipeline` streams snapshots at the per-consumer cadence
- `/dashboard` REST endpoint + frontend `AnalyticsPanel`
- Persistence barcode visualisation (`phase-7-barcode`)

### Phase 6 — Attacker + Shell Coach · `phase-6-done`

- `pna` CLI: 5 attacks (replay, linkability, dp_reconstruct,
  byzantine, timing_sidechannel)
- `psh` CLI: 11 lesson tracks + explain + suggest + interpret
- In-dashboard Coach panel (`phase-7-spine`) — runs pna/psh via
  POST /coach/exec with allow-list restriction

### Phase 7 — Frontend polish · `phase-7-clouds`

- Fuzzy agent halos (radius + alpha ∝ recent position variance)
- Persistence barcode SVG visualisation
- Per-package READMEs with concept-taught + micro-experiments

### Phase 8 — Production rounding · `ci-actions`, `dp-runtime`, `house-keeping`

After the main pillars landed, a sweep of "make-it-actually-work"
fixes graduated several pieces of state from libraries-in-a-folder
to live properties of the running system:

- **`ci-actions`** — `.github/workflows/check.yml`: backend + frontend
  jobs on every push/PR. Five consecutive runs verified green.
- **`dp-runtime`** — encrypted heatmap noised via Laplace, budget
  spent visible at `/dp/budget`. The DP claim is now a property,
  not a library.
- **`house-keeping`** — race fix on `/encrypted-heatmap` warm-start,
  per-agent Dilithium signing-stats endpoint, 5 missing shell-coach
  lesson tracks (now 11/11 bundled), per-package READMEs, Vitest
  smoke setup, MAPPO retrained at 50 iterations.

### Phase 9 — Chain hardening · `chain-slashing`, `slashing-in-block`, `chain-persistence`, `world-snapshots`, `world-full`, `chain-slashing-ui`, `chain-slash-endpoint`

- **`chain-slashing`** — `Node.slash(evidence)` removes a validator
  from the active set; quorum scales down as the set shrinks.
- **`slashing-in-block`** — slashings are now committed by the
  block's Merkle root, not just the in-memory state.
- **`chain-persistence`** — Parquet + JSON snapshot/restore of the
  entire Node state; secrets chmod 0o600.
- **`world-snapshots`** + **`world-full`** — `POST /world/save`
  captures chain + simulation + CKKS keys + DP budget; `pna world
  {save,load,list}` CLI subcommand. Simulation snapshot consumable
  on restart via `PENUMBRA_SIM_SNAPSHOT`.
- **`chain-slashing-ui`** — ChainExplorer renders red-tinted
  slashing rows under each block.
- **`chain-slash-endpoint`** — `POST /chain/slash` accepts evidence;
  `POST /chain/_demo/self-slash` (gated by env var) makes the loop
  end-to-end observable for the `pna byzantine-cmd --submit-self-slash`
  workflow.

### Phase 10 — Runtime polish · `mappo-live`, `dashboard-dp-signing`, `sim-snapshot-boot`, `crypto-persistence`, `tour-mode`

- **`mappo-live`** — the MAPPO checkpoint is loaded and active in
  the running simulation (default `checkpoints/mappo_v0.pt`).
  `MAPPO.load(actor_only=True)` decouples the inference-time
  population size from the training-time one.
- **`dashboard-dp-signing`** — DP budget + Dilithium sigs verified
  surfaced as tiles in the AnalyticsPanel.
- **`sim-snapshot-boot`** — lifespan honours `PENUMBRA_SIM_SNAPSHOT`
  to restore the simulation from a saved world.
- **`crypto-persistence`** — CKKS keys (TenSEAL serialize_context) +
  DP budget (JSON) survive across restarts.
- **`tour-mode`** — first-run overlay walks new visitors through
  Arena → Coach → Analytics → Chain, persisted in localStorage.

### Phase 11 — Real ZK + real crypto + real shell · `groth16-real`, `tfhe-educational`, `bertopic-live`, `xterm-pty`

- **`groth16-real`** — `circuits/multiplier.circom` compiled via
  circom 2.2 + snarkjs 0.7. Local powers-of-tau ceremony, sample
  proof committed under `circuits/artifacts/`. Penumbra's pure-
  Python verifier accepts the snarkjs-generated proof and rejects
  tampered public inputs.
- **`tfhe-educational`** — `crypto/educational/tfhe_boolean.py`:
  150-LOC from-scratch LWE-based homomorphic XOR/NOT/NAND/AND/OR
  with the "encrypted faction overlap" use case. concrete-python
  doesn't ship cp313 wheels; the educational module aligns better
  with the project's existing `educational/` ethos anyway.
- **`bertopic-live`** — `analytics/topics.py` runs BERTopic +
  bge-small-en-v1.5 over a templated agent-utterance corpus.
  Streaming consumer at 20s cadence in the dashboard pipeline; new
  "BERTopic topics" tile in the AnalyticsPanel. Closes analytics
  13/13.
- **`xterm-pty`** — `/ws/pty` bridges xterm.js to a real macOS zsh.
  Gated by `PENUMBRA_ENABLE_PTY=1`. Dashboard has a Coach/Terminal
  tab toggle.

## Phase 8 — Dashboard expansion · `bugs-plus-missing-panels`

Built **after** the original phases above. Every panel is a clickable
tile on the analytics grid that opens a modal with educational
description + live interaction.

### Stats / econometrics tiles (Tier 2 + Tier 3)

`tier3-stat-charts`:
- ANOVA F-test on HDBSCAN cluster labels
- ACF/PACF correlograms with ±1.96/√n bands
- ROC curve + AUC for the logit propensity
- Pearson + Spearman correlation heatmap
- Permutation test on causal ATE
- Q-Q plot + residual-vs-fitted inline in the regression chart

### Closed-system market economy · `market-economy`

- Per-agent wallets (coins + inventory) + per-city markets
  (stocked products, inventory, dynamic ask price, treasury).
- BUY + SELL flow on city arrival (sell first to free coins).
- Money is conserved; inflation emerges from supply/demand pressure
  on a fixed money base.
- Charts: CandlestickChart (OHLC + volume), InflationChart (CPI +
  money supply), WealthChart (Lorenz + Gini).

### ML interaction · `ml-interaction`

- PolicyInspector: live actor-prob bars for any agent + observation
  features + chosen action.
- ActionHistogramChart: swarm-wide action mix per tick.
- StatusBar MAPPO/RANDOM toggle + temperature slider (mutates
  inference live).
- DpCompareChart: clean vs noised heatmap + δ + L1/L2 magnitudes.

### Chain & crypto panels · `chain-crypto-panels`

- VRFLeaderChart: validator panel + leader-frequency bars.
- MempoolChart: pending outcomes + slashing evidence.
- ZKVerifyChart: Groth16 legal-path verifier (cached after first run).
- BLSChart: aggregate sig for any block + signers + verify.
- SlashingChart: pick validator + forge equivocation evidence.

### Live training + value map + reward shaping · `ml-interaction`

- LiveTrainer background asyncio task — PPO updates against the
  LIVE actor; start/stop from the dashboard.
- ValueMapChart: critic V(s) + per-node policy entropy histogram.
- RewardShapingChart: 4 sliders mutating the shared RewardWeights
  singleton at runtime.

### Advanced ML + remaining crypto · `advanced-batch5` + `bugs-plus-missing-panels`

- GATAttentionChart: layer-1 / layer-2 attention rows per source node.
- SaliencyChart: ∂p(chosen)/∂x per observation feature.
- CKKSCompareChart: encrypt → decrypt round-trip + per-slot error.
- KyberKEMChart: ML-KEM-768 keygen + encaps + decaps + tampered.
- MultiCheckpointChart: load second checkpoint + KL + agreement.
- VDFChart: Wesolowski compute vs verify timing.
- DilithiumChart: per-agent ML-DSA-65 sig inspect.
- ShamirChart: (n, t) split + reconstruct + (t-1) garbage check.
- TFHEChart: LWE encrypt + homomorphic NOT/XOR correctness.
- WorldSnapshotChart: UI for the world/save + world/load endpoints.
- ArenaGraphChart: Fruchterman-Reingold 2D force-directed view.

### Bug fixes baked in along the way

- `np.trapz` → `np.trapezoid` for numpy 2.x compatibility (Gini was
  silently None before).
- Pre-commit got biome inside the hook system so frontend reformats
  don't silently drop from the commit (the silent-rollback bug).
- ZK verifier cache warm-up at server boot (was 15s cold path on
  first modal open).
- Sinkhorn divide-by-zero + ripser cols>rows warning suppressed at
  call site (cosmetic but log-spamming).

## Test + tag counts (current — post-Phase-6b)

- **40+ tags** on GitHub, every one a runnable repo state.
- **75+ commits**.
- **832 backend tests** + **~30 vitest** = **860+ total**, all green.
- **CI**: green (Python + Web workflows in `.github/workflows/ci.yml`).
- **91 clickable dashboard tiles / 96 chart components** (was ~57 pre-Phase-2.5).
- **3 React routes**: `/` (dashboard), `/bench` (leaderboard), `/operator`
  (cyber range Console).
- **11 packages**: core, crypto, chain, learning, analytics, attacker,
  shell_coach, transport (base 8) + operator, ctf, notebook (Phase 5+6b).
- **9 Penumbra-Bench baselines** at tier=tiny (greedy 0.8166 →
  stay-put 0.3025).
- **4 dataset tiers** generated (mini/standard/large/mega).
- **12 cyber-range scenarios** + **5 CTF challenges** + **19 shell-coach
  lessons** (11 base + 8 cross-pillar story tutorials).

## Phase 2.5 — Logistics + Federated Learning + Benchmark Tier 2-3 (shipped 2026-05-23)

Major expansion that turns Penumbra from a teaching demo into a
3-in-1 artefact (teaching + benchmark + dataset):

- **Logistics (Tier 1-4)** — cargo-cap on Market.BUY, (s,S) reorder,
  carrier dispatch (greedy nearest-agent + Dijkstra over arena),
  VRP solver (greedy / 2-opt / OR-Tools), multi-echelon supply chain
  (supplier → distributor → city w/ bullwhip metric), RL reward
  shaping + GNN encoder over the supply graph (`SupplyGraphEncoder`
  using PyG GATv2Conv).
- **Federated Learning (Tier 1-5)** — REAL local SGD on per-agent
  (obs, greedy-label) buffers (no synthetic gradients); real CKKS
  encrypted aggregation w/ slot batching; Rényi DP accountant
  (Sampled Gaussian Mechanism); Krum + TrimmedMean Byzantine-robust
  aggregators wired into `FederatedTrainer.step()` as live `method=`
  choices; FedProx proximal term, per-client personalisation heads
  (never aggregated), top-k sparsification + 8-bit quantization w/
  realised wire-byte savings on the dashboard.
- **Penumbra-Bench (Tier 1-3)** — formal 5-task suite (PA1/AR1/MC1/
  PB1/LR1) with composite scoring, 9 reference baselines, web
  leaderboard at `/bench`, stdlib-only submission validator + GitHub
  Actions CI workflow for external PRs.
- **Penumbra-Data** — generated 4 tiers (mini=500, standard=36k,
  large=864k, mega=5M ticks) across 7 modalities (positions, trades,
  inventory, prices, heatmaps, matches, attacks); generator now
  writes parquet incrementally in 100k-tick shards so mega fits in
  M4 16 GB RAM budget.

## Phase 3 — Post-Phase-2.5 stress test (shipped 2026-05-23)

10-minute clean stress test, 0 CRIT findings:
- Memory: sustained drift 69 MB/h after warmup (warmup +481 MB);
  well within 8 GB budget.
- Chain: 53 blocks / 10 min (0.088 blocks/s).
- Signing: 20 550 Dilithium signatures verified, 0 rejected.
- DP budget: healthy (1.06 / 1000 ε spent).
- Single WARN: tick throughput 7.40 Hz vs 10 Hz target — the true
  cost of the Phase 2.5 stack; profiling + targeted optimization
  recovered to ≥ 9 Hz in a follow-up pass (see commit history).

## Phase 4 — OSS launch materials (shipped 2026-05-23)

LICENSE (MIT) + LICENSE-DATA (CC-BY-4.0) + CONTRIBUTING + SECURITY +
CODE_OF_CONDUCT + FUNDING.yml + 3 issue templates + PR template +
CITATION.cff + CHANGELOG + PAPER.md (arXiv-ready) + ci.yml workflow.
Hero + OG image SPECS in `docs/` (image capture is a maintainer
task — see `USER_TODO.md`).

## Deferred (intentional, with rationale)

| Item | Why deferred |
|---|---|
| `attacker/snark_forgery.py` | The Schnorr ZK module already pins the defence; the attack demo would be documentation |
| Production-grade TFHE (Concrete-ML) | `concrete-python` doesn't ship cp313 wheels; the educational module + the TFHEChart panel capture the protocol shape |
| LLM-generated agent utterances | The templated corpus in `analytics/topics.py` produces enough topic-modelling signal without the GPU spend |
| Real EVM/Substrate chain | The custom local chain is the right scope for an educational project; an EVM-compatible implementation is a different project |
| Multi-machine distribution + KMS + dashboard auth | Single-host learning project by design |
| Mobile responsive | Explicitly out of scope per plan |
| GPU-accelerated FHE (FIDESlib) | Needs CUDA, not Metal — out of scope on M4 |

## Phase 9 — OSS launch (planned, weeks 1-12 from 2026-05-23)

The repo will be made public following the plan in
[`OSS_LAUNCH_ROADMAP.md`](OSS_LAUNCH_ROADMAP.md). Summary:

- **L0 (weeks 1-4)** — readiness: stress-test triage, code
  consolidation (extract shared chart primitives, drop ~600 LOC),
  LICENSE / CONTRIBUTING / SECURITY / CODE_OF_CONDUCT, hero
  screenshot + 90-second demo, arXiv preprint submission.
- **L1 (week 5)** — launch day: Show HN, Reddit, LinkedIn, X/Twitter,
  dev.to. Tuesday or Wednesday at 9 AM EST. Tight 6-hour artefact
  window for the 48-hour algorithm advantage.
- **L2 (week 5 days 2-7)** — sustainment: < 24h issue response,
  fast-merge first PRs, follow-up blog post.
- **L3 (months 2-3)** — newsletter outreach, "Awesome" list
  submissions, conference workshop submissions (NeurIPS D&B,
  USENIX CSET, ICML AutoRL, PyCon, RWC), talks / podcasts /
  YouTube tutorials.
- **L4 (months 4-6)** — Discussions categories, hackathon,
  university outreach, Tier 1 logistics layer release as v1.1 news.
- **L5 (month 6)** — decision: continue OSS / layer B2B services
  (open core) / pivot.

**KPI targets**:
| Metric | Week 5 | Week 12 | Month 12 |
|---|---|---|---|
| GitHub stars | 100 | 500 | 1500 |
| External contributors | 0 | 5 | 30 |
| Conference talks | 0 | 0 | 3 |

Detailed promotion playbook (HN/Reddit/LinkedIn/Twitter tactics,
anti-patterns, second-wave rule) in `OSS_LAUNCH_ROADMAP.md`.

The B2B Edu pitch (`EDU_B2B_PITCH.md`) is intentionally deferred —
to be activated only if Phase 9 generates the demand signals
(stars, invites, consulting requests) listed in the roadmap.

## Phase 10 — 3-in-1 expansion (planned, post-OSS-launch)

After the OSS launch (Phase 9), Penumbra repositions as a 3-in-1
artefact: teaching platform + benchmark + dataset.

- **Penumbra-Bench** (`BENCHMARK_PLAN.md`) — 5-task benchmark suite
  (Privacy-Aware Coordination, Adversarial Resilience, Multi-agent
  Cooperation under Encryption, Privacy-Budget Management,
  Linkability Resistance) with composite scoring, 4 difficulty
  tiers, 7 baseline policies, and a public leaderboard on GitHub
  Pages. Target release: month 2-3 post-launch as v1.1.

- **Penumbra-Data** (`SYNTHETIC_DATA_PLAN.md`) — multi-modal
  synthetic dataset on Hugging Face Hub. Seven correlated streams
  (positions, trades, inventory, prices, heatmaps, matches, attack
  labels, chain blocks) with full generative provenance and
  ground-truth adversarial labels. Four size tiers: Mini (5 MB) →
  Mega (20 GB). Target release: month 1-2 post-launch as v1.1
  asset on HF Hub.

- **Federated Learning extension** (`FEDERATED_LEARNING_PLAN.md`) —
  FedAvg + CKKS-encrypted aggregation + DP-SGD + Byzantine-robust
  variants (Krum, Trimmed Mean, Median). Tied to Penumbra-Bench
  as the FL benchmark task. Target release: month 4-6 as v1.2.

- **Logistics extension** (`LOGISTICS_PLAN.md`) — SHIPPED in
  Phase 2.5 (2026-05-23). OR layer with VRP solvers (greedy /
  2-opt / OR-Tools), multi-echelon supplier→distributor→city,
  carrier dispatch, bullwhip metric. Originally planned for
  month 4-6 as v1.2; landed pre-launch.

## Phase 5 — Crypto + Surveillance Attack/Defense Lab (SHIPPED 2026-05-24)

Spec: `CRYPTO_ATTACK_DEFENSE_PLAN.md`. 5 tier across 50+h of agent
work, shipped in 4 waves.

- **Tier 1** — 8 foundation primitives: FROST (threshold Schnorr),
  SPHINCS+ (hash-based PQ), Verkle (BLS12-381 KZG), BBS+ (anonymous
  credentials), threshold ECDSA (GG18), Yao garbled circuits, PSI
  (OPRF-based), Loopix mix-net, STARK verifier (FRI-based).
- **Tier 2** — 6 attack modules: agent_fingerprint, trajectory_fingerprint,
  membership_inference (Shokri 2017 shadow-models), model_inversion,
  reward_poisoning, cache_sidechannel. Each ships with defense docstring.
- **Tier 3** — 6 defense modules in `packages/crypto/penumbra_crypto/defenses/`:
  data_poisoning, padding, k_anonymity, l_diversity, GAN, request_obfuscation.
- **Tier 4** — 4 interactive surfaces: custom Python policy injection
  (sandbox), CTF mode (5 starter challenges), Jupyter `%penumbra`
  magics, world branching for replay/compare.
- **Tier 5** — 8 cross-pillar story tutorials (bullwhip-leak, honest-
  validator, replay-chain, dp-starvation, fl-backdoor, carrier-extortion,
  mix-net-defense, ctf-speedrun).

## Phase 6 — Cyber Range (Operator Mode + Inter-Silo Integration)

### Phase 6a — Inter-silo deep integration (SHIPPED 2026-05-23)

Spec: `INTER_SILO_INTEGRATION_PLAN.md`. ~50h, 5 tier.
In-process EventBus in `transport/events.py` + 5 cross-pillar handler
tiers: Stats↔Logistics/Market (garch.spike → reorder retune), Security↔
Market/Logistics/FL (agent.blocked event), DP-budget-aware analytics
cadence, ML/RL↔Logistics reward loop, Chain↔Market wallet credits.
End-to-end story: GARCH spike → reorder → dispatch → MAPPO action
shift propagates through 5 pillars in one tick.

### Phase 6b — Operator Mode / Cyber Range (SHIPPED 2026-05-24)

Spec: `OPERATOR_MODE_PLAN.md`. ~60h, 6 tier.
- New top-level `packages/operator/` mirror of `attacker/`.
- Operator agent (id N+1) controllable via `/operator/*` endpoints +
  `pno` CLI: 20 actions (8 core + 6 attack + 6 defense).
- 12 starter YAML scenarios spanning 4 difficulty tiers; victory/
  failure clauses + per-scenario leaderboard.
- Session replay parquet (state/operator/sessions/) with determinism
  guarantee + `pno replay <id>` CLI.
- Operator Console at `/operator` (Status / Action Builder / Log / Score).

Phase 6 turned Penumbra from "OSS teaching + bench + dataset" into
the OSS counterpart of commercial cyber ranges (Cyberbit / Immersive
Labs / RangeForce / TryHackMe). Target was v3.0; commercialisation
window per `OSS_LAUNCH_ROADMAP.md` Phase L4.

Each extension is a fresh news angle that maintains the OSS
launch momentum (per `OSS_LAUNCH_ROADMAP.md` Phase L3-L4 sustainment).

## Cadence reality

This was a multi-week project's worth of work, condensed into a
handful of days with the help of the agent system. The tags above
are all dispense-points: each is a runnable repo state where the
user can do `@learner` sessions or attack experiments. The deferred
items are real (not abandoned) — each has either a docstring caveat
in its closest neighbour module or an explicit out-of-scope note
in this document.
