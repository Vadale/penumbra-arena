# Penumbra — Roadmap

The map for the build. Read this once for orientation; consult per phase.
Sister document: `PROMPTING_GUIDE.md` has the step-by-step recipes.

## Project at a glance

Penumbra is a perpetual privacy-preserving multi-agent arena. N=20–50 agents
compete on a procedurally dynamic graph; their state is encrypted (CKKS+TFHE),
the spectator sees only aggregates, match outcomes are anchored on a local
PoS-VRF blockchain with zk-SNARK validity proofs. The dashboard hosts a live
analytics stream, a 3D arena rendered with probabilistic agent clouds, an
Attacker Console (`pna`), and a Shell Coach with `zsh` PTY + curated lessons
(`psh`).

The project's purpose is **learning**: every package is a self-contained entry
point for a guided conversation with the `learner` agent (math / crypto /
stats / NN) or `shell-coach` (Unix on macOS).

## Pillars and where they live

| Pillar | Primary packages |
|---|---|
| Neural networks | `learning/` (MAPPO, GATv2) |
| Cryptography | `crypto/`, `chain/` |
| Statistics | `analytics/` |
| Linear algebra & topology | `analytics/linalg.py`, `analytics/topology.py`, `analytics/transport.py` |
| Adversarial intuition | `attacker/` |
| Unix/macOS shell | `shell_coach/` |
| Domain | `core/` (integration seam) |
| I/O | `transport/`, `apps/web/` |

## Phases

Each phase ends with the repo in a runnable state. Use `git tag phase-N-done`
when each phase passes its checklist.

### Phase 0 — Foundations (½–1 day)
**Goal:** the navigation layer is in place; the repo exists; agents are wired.

- [x] `git init` on `main`
- [x] `.gitignore`, `.gitattributes`, provisional `README.md`
- [x] `CLAUDE.md`
- [x] `.claude/agents/{coder,reviewer,crypto-auditor,doc-writer,learner,shell-coach}.md`
- [x] `ROADMAP.md` (this file)
- [ ] `PROMPTING_GUIDE.md`
- [ ] Conventional commits (one per artefact)
- [ ] Private GitHub repo `penumbra-arena`, first push

**Done when:** `gh repo view` shows the repo and `git log --oneline` shows a
clean conventional-commit history.

### Phase 1 — Skeleton + perpetual loop (1.5 days)
**Goal:** a perpetual simulation streams agent positions in clear to a 3D viewer.

- uv workspace (`pyproject.toml`), pnpm workspace (`pnpm-workspace.yaml`)
- `infra/docker-compose.yml`, `Dockerfile.api`, `Dockerfile.web`
- `packages/core/rng.py` — central seeded RNG (first file)
- `packages/core/arena.py` — procedural dynamic graph (OU edge costs, random-walk goals, weather)
- `packages/core/agent.py`, `packages/core/match.py`, `packages/core/simulation.py`
- `packages/transport/api.py`, `packages/transport/ws.py`
- `apps/web/` Vite + React 19 + TS strict + tailwind v4 + shadcn/ui shell
- `apps/web/src/three/Arena.tsx` (initial: crisp dots)
- Pre-commit (ruff, ruff-format, biome) + a `Makefile` or `justfile`
- Property tests for arena invariants and RNG reproducibility

**Done when:** `docker compose up` shows 50 random-walk agents moving on the
graph in the browser, ticks at 10 Hz, memory < 1 GB.

**Learning checkpoint:** invoke `@learner` to walk you through `core/rng.py`
(why centralised RNG matters) and `core/arena.py` (Ornstein-Uhlenbeck noise,
why the path can never be solved once).

### Phase 2 — Crypto stack (2 days)
**Goal:** agent state is encrypted end-to-end; the server never sees plaintext.

Order — write & audit each before moving to the next:
1. `packages/crypto/ckks.py` — OpenFHE-Python adapter; fallback to TenSEAL via `PENUMBRA_HE_BACKEND` env
2. `packages/crypto/tfhe.py` — Concrete-ML adapter
3. `packages/crypto/dp.py` — diffprivlib + opendp accountant
4. `packages/crypto/pq.py` — Kyber768 KEM, Dilithium3 signatures
5. `packages/crypto/bls.py` — py_ecc BLS aggregate signatures
6. `packages/crypto/vrf.py` — Schnorr-VRF
7. `packages/crypto/vdf.py` — Wesolowski VDF
8. `packages/crypto/snark.py` — Groth16 verifier
9. `packages/crypto/educational/{shamir,beaver,pedersen,schnorr}.py` — from scratch, **isolated from hot path**

Each crypto module **must** be reviewed by `crypto-auditor` before commit. Sign-off SHA recorded in commit body.

**Done when:** simulation broadcasts encrypted positions, server holds only ciphertexts and DP-noised aggregates, encrypted heatmap streams to frontend.

**Learning checkpoints:** with `@learner`, walk `ckks.py` (rescale, level budget, SIMD packing), `educational/schnorr.py` (Fiat-Shamir transformation), `bls.py` (rogue-key attack defence).

### Phase 3 — Blockchain (1 day)
**Goal:** match outcomes append to a local chain with verifiable validity.

- `packages/chain/block.py`, `merkle.py`
- `packages/chain/consensus.py` — PoS-VRF leader, BLS aggregate
- `packages/chain/mempool.py`, `node.py`
- `packages/chain/explorer_api.py`
- Match-end hook in `core/match.py` builds the zk-SNARK and submits the block

**Done when:** every ~10s a new block is added; the explorer at `/chain` shows
blocks with verified Groth16 proofs; tampered transactions are rejected.

**Learning checkpoint:** `@learner` on `consensus.py` (why VRF, why BLS), and
on `snark.py` (Groth16 verification equation).

### Phase 4 — Learning (1.5 days)
**Goal:** agents act with trained MAPPO policies; a GATv2 pathfinder advises them.

- `packages/learning/mappo.py` — CleanRL template, adapted; MPS device
- `packages/learning/gat_pathfinder.py` — PyTorch Geometric GATv2
- `packages/learning/training.py` — self-play loop, checkpoints
- Ship a pre-trained checkpoint so `docker compose up` works without training first

**Done when:** agents exhibit non-trivial behaviour (cooperation/competition) in
`docker compose up`; MAPPO policy loads from checkpoint in < 5 s on MPS.

**Learning checkpoint:** `@learner` on MAPPO's CTDE, GAT attention vs GCN, MPS pragmatics.

### Phase 5 — Analytics (2 days)
**Goal:** the dashboard streams every statistical / topological / linalg / OT artefact in real time.

Modules (all in `packages/analytics/`):
- `descriptive.py`, `inferential.py`
- `econometrics.py` (OLS / IV / panel / GMM / VAR / GARCH / cointegration / Granger)
- `time_series.py` (ARIMA / Kalman / change-point)
- `monte_carlo.py` (Sobol QMC, bootstrap, VaR/CVaR)
- `causal.py` (DoubleML / EconML / dowhy)
- `survival.py` (lifelines)
- `bayesian.py` (NumPyro SVI)
- `clustering.py` (HDBSCAN + spectral)
- `linalg.py` (Laplacian, spectral embedding)
- `topology.py` (ripser on coalition graph)
- `transport.py` (POT Sinkhorn)
- `topics.py` (BERTopic on pre-seeded utterances)
- `dashboard_pipeline.py` — orchestrates at correct cadences (1 s, 5 s, per-match)

**Done when:** every panel on the dashboard updates on its cadence; memory stays in budget.

**Learning checkpoints:** one `@learner` session per module is the rhythm. Each module has a `Concept taught:` line that becomes the conversation starter.

### Phase 6 — Attacker Console + Shell Coach (1.5 days)
**Goal:** two interactive surfaces inside the dashboard and as CLIs.

Attacker:
- `packages/attacker/console.py` — sandboxed Python REPL (asyncio subprocess, restricted imports, resource caps)
- `packages/attacker/attacks/{replay,linkability,dp_reconstruction,timing_sidechannel,byzantine,snark_forgery}.py`
- Each attack file's docstring includes: how the attack works, why Penumbra resists it (or doesn't), mitigation if relevant
- `packages/attacker/cli.py` — `pna` (typer)
- `packages/transport/repl_bridge.py` — xterm.js ↔ REPL

Shell Coach:
- `packages/shell_coach/lessons/*.yaml` — 11 starter lessons
- `packages/shell_coach/{suggester,explain,error_helper}.py`
- `packages/shell_coach/cli.py` — `psh` (typer)
- `packages/transport/pty_bridge.py` — xterm.js ↔ macOS `zsh` PTY

Frontend:
- `apps/web/src/terminal/Console.tsx` with PTY/REPL toggle
- `apps/web/src/coach/{Suggester,LessonStepper,ErrorHelper,History}.tsx`

**Done when:** terminal toggles cleanly between modes; `pna api.help()` works in REPL mode; `psh lessons` works as standalone CLI; lesson 5 (`curl`) hits `localhost:8000/health` and validates output.

**Learning checkpoint:** the Attacker Console itself is the lesson. Try `replay.py` then `linkability.py` and let `@learner` (or the attack docstring) explain *why* the defence works.

### Phase 7 — Frontend integration & polish (1.5 days)
**Goal:** the dashboard renders the full system, fuzzy clouds and all.

- `Arena.tsx` final: agents as fuzzy clouds with alpha ∝ posterior σ
- `charts/Barcode.tsx`, `Sinkhorn.tsx`, `FactionGraph.tsx`, `EconometricsPanel.tsx`, `MonteCarloFan.tsx`, `BayesPosteriors.tsx`, `TopicDrift.tsx`
- `chain/Explorer.tsx`
- `routes/Dashboard.tsx` — final layout
- Per-package `packages/*/README.md` with "Concept taught" and micro-experiments
- Tour mode (first-run) optional
- Smoke E2E (Playwright) covering: app loads, simulation runs, attacker console responds, lesson stepper advances

**Done when:** all 11 dashboard verification points (see `CLAUDE.md`) pass; memory under 8 GB total under load.

## Cross-phase work

- **Reviews**: after each phase, run `@reviewer` (and `@crypto-auditor` for phases 2, 3, 6) before tagging.
- **Docs**: `@doc-writer` keeps `README.md`, `ROADMAP.md`, `PROMPTING_GUIDE.md`, and per-package READMEs in sync at the end of each phase.
- **Learning sessions**: after each phase the user has a conversation with `@learner` covering that phase's concepts before the next phase begins. The repo state is the curriculum.

## Cadence reality

This is 8–12 focused days of build work, distributed across multiple
sessions. Crypto + chain are the densest phases and deserve extra care. Tag
each phase as you finish (`git tag phase-N-done`) so the user can roll back
cheaply if they want to revisit.
