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

## Deferred (intentional, with rationale)

| Item | Why deferred |
|---|---|
| `analytics/topics.py` (BERTopic) | Agent utterances don't exist yet; ~500 MB of HuggingFace deps would arrive with it |
| `crypto/tfhe.py` (Concrete-ML) | Heavy install; the CKKS aggregate flow already covers the main encrypted-aggregate use case |
| xterm.js full PTY terminal | Coach panel duplicates the functionality with simpler UX |
| Chain disk persistence | Restart loses the chain; the snapshot/restore primitive (`pna world save/load`) is sketched in the docs |
| Slashing transactions | Equivocation detection works (`pna byzantine-cmd`); on-chain consequence pending |
| Real Groth16 circuit for "legal moves" | Requires circom + snarkjs toolchain install; the verifier is wired and waits for a real proof |
| `attacker/snark_forgery.py` | The Schnorr ZK module already pins the defence; the attack demo is documentation |
| CI GitHub Actions | The workspace runs the same checks via `just check` + `pnpm --filter web {typecheck,lint,build}` |
| MAPPO long-training checkpoint | The shipped checkpoint is 5 iterations; rerunning the training script with 50+ iterations yields a much stronger policy |

## Cadence reality

This was a multi-day project's worth of work. The tags above are
all dispense-points: each is a runnable repo state where the user
can do `@learner` sessions or attack experiments. The deferred items
are real (not abandoned) and each has a TODO marker in its closest
neighbour module.
