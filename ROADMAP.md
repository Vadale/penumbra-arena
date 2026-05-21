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

## Test + tag counts (current)

- **35 tags** on GitHub, every one a runnable repo state.
- **47+ commits**.
- **~298 backend tests** + **10 vitest** = ~308 total, all green.
- **CI**: 7 consecutive green runs.

## Deferred (intentional, with rationale)

| Item | Why deferred |
|---|---|
| `attacker/snark_forgery.py` | The Schnorr ZK module already pins the defence; the attack demo would be documentation |
| Production-grade TFHE (Concrete-ML) | `concrete-python` doesn't ship cp313 wheels; the educational module (`tfhe-educational`) captures the protocol shape |
| LLM-generated agent utterances | The templated corpus in `analytics/topics.py` produces enough topic-modelling signal without the GPU spend |
| Real EVM/Substrate chain | The custom local chain is the right scope for an educational project; an EVM-compatible implementation is a different project |
| Multi-machine distribution + KMS + dashboard auth | Single-host learning project by design |
| Mobile responsive | Explicitly out of scope per plan |
| GPU-accelerated FHE (FIDESlib) | Needs CUDA, not Metal — out of scope on M4 |

## Cadence reality

This was a multi-week project's worth of work, condensed into a
handful of days with the help of the agent system. The tags above
are all dispense-points: each is a runnable repo state where the
user can do `@learner` sessions or attack experiments. The deferred
items are real (not abandoned) — each has either a docstring caveat
in its closest neighbour module or an explicit out-of-scope note
in this document.
