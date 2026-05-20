# Penumbra — Prompting Guide

Step-by-step recipes for building each module. Where `ROADMAP.md` gives the
*what* and *when*, this file gives the *how*: which tool, which file, which
command, which prompt to send to which agent.

Pair this with `@coder` (implementer), `@crypto-auditor` (mandatory for crypto/chain/attacker), `@reviewer` (post-implementation), and `@learner` (after each module is done).

## How to use this guide

1. Pick the next unbuilt module from `ROADMAP.md`.
2. Find its recipe below.
3. Copy the prompt template into your message to the relevant agent.
4. Verify with the listed `Done when` criteria.
5. Tag the milestone if it ends a phase.

Conventions used in the recipes:
- `[ ]` = action item
- `→` = command to run
- `📐` = design decision the recipe makes for you
- `🔒` = touches crypto/chain/attacker — `crypto-auditor` mandatory

---

## Phase 0 — Foundations

Already covered by the bootstrap commits. If you're reading this, Phase 0 is
mostly done. Verify with:

```sh
git log --oneline
gh repo view
ls -la .claude/agents/
```

---

## Phase 1 — Skeleton + perpetual loop

### 1.1 — Workspace bootstrap

📐 We pick **uv workspace** + **pnpm workspace** under one monorepo root.

[ ] Initialise `pyproject.toml` at root:

```sh
uv init --package penumbra
```

[ ] Edit `pyproject.toml` to declare the workspace and dev deps:

```toml
[tool.uv.workspace]
members = ["packages/*"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "PL", "RUF"]

[tool.pyright]
strict = ["packages/**"]
pythonVersion = "3.12"
```

[ ] Initialise pnpm workspace at root:

```yaml
# pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/web-*"
```

[ ] Add a `justfile` for common commands.

→ `uv sync && pnpm install`

**Done when:** `uv run python -c "print('ok')"` and `pnpm exec node -e "console.log('ok')"` both work.

**Prompt to `@coder`:**
> Bootstrap the uv + pnpm workspaces per `PROMPTING_GUIDE.md` §1.1. Add a `justfile` with targets: `setup`, `test`, `typecheck`, `lint`, `format`, `dev`, `up`.

### 1.2 — `core/rng.py` (write this first)

📐 Centralised RNG fan-out: one `PENUMBRA_SEED` env var seeds Python `random`, `numpy`, `torch`, `jax`.

[ ] Create `packages/core/penumbra_core/rng.py` with:
- A `Seeded` dataclass with the seed + per-domain sub-keys.
- A `bootstrap(seed: int | None) -> Seeded` function.
- A `run_record() -> dict` capturing seed + library versions.
- A `pytest` fixture in `packages/core/tests/conftest.py` that resets the RNG.

[ ] Property test: two `bootstrap(42)` runs produce identical numpy arrays after a fixed sequence of draws.

**Prompt to `@coder`:**
> Implement `packages/core/penumbra_core/rng.py` per the spec. Include strict types, module docstring with `Concept taught: deterministic reproducibility across multiple RNG-bearing libraries`. Add property tests. No external deps beyond stdlib + numpy + torch + jax.

### 1.3 — `core/arena.py`

📐 The arena is a graph (NetworkX) with stochastic, time-varying edge costs (Ornstein-Uhlenbeck) and migrating goals.

[ ] Create `packages/core/penumbra_core/arena.py`:
- `Arena` class wrapping `networkx.Graph`.
- Edge cost stored as a per-edge OU state; `step()` updates costs.
- Goals are nodes that random-walk every K ticks.
- A "weather" channel deletes and re-adds edges with low probability.

[ ] Property tests: arena stays connected after `step()`; goals reach all nodes eventually.

**Prompt to `@coder`:**
> Implement `arena.py` per spec. Use NetworkX. All randomness via `rng.py`. Docstring `Concept taught: graph topology + Ornstein-Uhlenbeck noise → no fixed shortest path`.

### 1.4 — `core/agent.py`, `core/match.py`, `core/simulation.py`

[ ] `agent.py`: `Agent` dataclass with id, position node, policy callback.
[ ] `match.py`: `Match` runs one episode until a goal is reached or a tick budget expires.
[ ] `simulation.py`: perpetual loop yielding ticks; respects pause/step/time-warp commands.

**Prompt to `@coder`:**
> Implement `agent.py`, `match.py`, `simulation.py`. The simulation must be pause-able, step-able, and time-warpable (faster ticks for offline experiments). All randomness via `rng.py`.

### 1.5 — Transport: FastAPI + WS

[ ] `packages/transport/penumbra_transport/api.py`: FastAPI app with `/health`, `/state`.
[ ] `packages/transport/penumbra_transport/ws.py`: WebSocket at `/ws` streaming msgpack frames.

→ `uv run uvicorn penumbra_transport.api:app --reload`

**Prompt to `@coder`:**
> Wire FastAPI + WS streaming. Frames are msgpack. Add a `/health` and a `/state` endpoint. The WS at `/ws` pushes a frame per tick.

### 1.6 — Frontend shell

[ ] `apps/web/` via Vite, React 19, TS strict, tailwind v4, shadcn/ui.
[ ] `apps/web/src/three/Arena.tsx`: react-three-fiber scene with dots for agents.
[ ] `apps/web/src/streams/ws.ts`: WebSocket client + zustand store.
[ ] `apps/web/src/routes/Dashboard.tsx`: single-page layout.

→ `pnpm --filter web dev`

**Prompt to `@coder`:**
> Bootstrap the React shell. Wire WS to a zustand store; render agents as dots in r3f. TS strict. No `any`.

### 1.7 — Docker compose

[ ] `infra/docker-compose.yml`: two services (`api`, `web`).
[ ] `infra/Dockerfile.api` (uv-based), `infra/Dockerfile.web` (pnpm-based).

→ `docker compose up`

**Done when:** browser at `http://localhost:5173` shows 50 agents moving on the graph at 10 Hz with memory < 1 GB.

**Phase 1 tag:** `git tag phase-1-done`

**Learning session:** ask `@learner` "spiegami `core/rng.py` e `core/arena.py`".

---

## Phase 2 — Crypto stack 🔒

> **All commits in this phase require `@crypto-auditor` sign-off.**

### 2.1 — OpenFHE install (with TenSEAL fallback)

📐 OpenFHE on M4 builds from source via CMake; flaky in ~20% of environments. We support both backends behind one adapter.

[ ] Attempt OpenFHE-Python install:

```sh
brew install cmake
uv add openfhe
```

If the build fails (CMake or pybind11 error), do **not** spend more than 30
minutes debugging. Fall back:

```sh
uv add tenseal
export PENUMBRA_HE_BACKEND=tenseal
```

[ ] `packages/crypto/penumbra_crypto/ckks.py` defines an adapter interface
`HEBackend` with two implementations: `OpenFHEBackend`, `TenSEALBackend`.
Selected at import time by `PENUMBRA_HE_BACKEND`.

**Prompt to `@coder` (before invoking `@crypto-auditor`):**
> Implement `crypto/ckks.py` with adapter pattern. Read the OpenFHE-Python and TenSEAL docs. Default to OpenFHE; fall back via `PENUMBRA_HE_BACKEND=tenseal`. Provide `encrypt(plain: np.ndarray)`, `decrypt(ct) -> np.ndarray`, `add(a, b)`, `mul(a, b)`, `rescale(ct)`. SIMD-pack 32-64 floats per ctxt. Docstring with `Concept taught: CKKS approximate arithmetic on packed real vectors`.

🔒 **After implementation, invoke `@crypto-auditor`:**
> Audit `packages/crypto/ckks.py` per the checklist. Pay special attention to rescale placement for the TenSEAL backend (which defers rescales by default).

### 2.2 — TFHE (Concrete-ML)

📐 Used for boolean / comparison ops over encrypted state ("is agent in region X?").

[ ] `crypto/tfhe.py`: thin adapter around Concrete-ML compiled function.

**Prompt to `@coder`:**
> Implement `crypto/tfhe.py` as a thin Concrete-ML adapter for the `in_region(x, region) -> bool` predicate, encrypted. Compile-once, evaluate many.

🔒 **`@crypto-auditor`** — same audit, with focus on input bit-precision.

### 2.3 — DP (`diffprivlib` + `opendp`)

[ ] `crypto/dp.py`: `dp_mean`, `dp_variance`, `dp_count` with a global budget accountant via `opendp`.

**Prompt to `@coder`:**
> Implement `crypto/dp.py` with a privacy accountant. Every release deducts from a project-wide ε/δ budget. Raise `BudgetExceeded` when the budget would go negative.

🔒 **`@crypto-auditor`** — focus on noise scale = global sensitivity / ε.

### 2.4 — Post-quantum (`pqcrypto`)

[ ] `crypto/pq.py`: Kyber768 KEM, Dilithium3 signatures. Wrap, do not reimplement.

**Prompt to `@coder`:**
> Implement `crypto/pq.py` wrapping `pqcrypto.kem.kyber768` and `pqcrypto.sign.dilithium3`. Provide `kem_encapsulate`, `kem_decapsulate`, `sign`, `verify`.

🔒 **`@crypto-auditor`** — check rejection of malformed ciphertexts/signatures.

### 2.5 — BLS aggregate signatures (`py_ecc`)

[ ] `crypto/bls.py`: BLS keypair, sign, verify, aggregate. Implement proof-of-possession.

**Prompt to `@coder`:**
> Implement `crypto/bls.py` using `py_ecc.bn128`. Provide `keygen`, `sign`, `verify`, `aggregate_sigs`, `verify_aggregate`, `proof_of_possession`, `verify_pop`. Document the rogue-key defence.

🔒 **`@crypto-auditor`** — verify the rogue-key defence (PoP) is enforced at registration.

### 2.6 — VRF (Schnorr-VRF)

[ ] `crypto/vrf.py`: Schnorr-VRF over Curve25519 or BN254.

🔒 **`@crypto-auditor`** — verify proof binds to input via Fiat-Shamir.

### 2.7 — VDF (Wesolowski)

[ ] `crypto/vdf.py`: Wesolowski VDF in a class group of imaginary quadratic order. Slow-by-design; only used per-match for arena randomness.

🔒 **`@crypto-auditor`** — verify the proof is succinctly verifiable.

### 2.8 — Groth16 verifier

[ ] `crypto/snark.py`: pure-Python Groth16 verifier using `py_ecc` pairings. Circuits compiled offline via `circom` + `snarkjs` (Node, installed locally).

→ `brew install circom` (or `npm i -g snarkjs circom`)

**Prompt to `@coder`:**
> Implement `crypto/snark.py` as a Groth16 verifier in Python. Verification key + proof loaded from JSON produced by snarkjs. Verify the canonical pairing equation. Add a sample circuit `circuits/legal_move.circom` and pre-generated verifying key.

🔒 **`@crypto-auditor`** — verify pairing equation by reference; check public input handling.

### 2.9 — Educational SMPC/ZK (offline-only)

[ ] `crypto/educational/shamir.py`, `beaver.py`, `pedersen.py`, `schnorr.py`. Each ~150 LOC with dense math docstrings.

📐 These are **never** on the hot path. They're exercised by tests and by lessons.

**Prompt to `@coder`:**
> Implement each from scratch with dense math comments. Each file teaches one concept. Add property tests proving the security guarantee experimentally (e.g. Schnorr: replay a stale proof and verify rejection).

🔒 **`@crypto-auditor`** — pedagogical implementations still need correctness review.

### Phase 2 tag

→ `git tag phase-2-done`

**Learning sessions:** with `@learner`, walk `ckks.py`, `bls.py`, `educational/schnorr.py`, `educational/pedersen.py`. Each is a 20-30 minute conversation.

---

## Phase 3 — Blockchain 🔒

### 3.1 — `chain/block.py`, `chain/merkle.py`
[ ] Block dataclass: prev_hash, height, timestamp (VDF-bound), merkle_root, payload, validator_sigs.
[ ] Merkle tree: SHA-256, sibling proofs.

### 3.2 — `chain/consensus.py`
[ ] PoS-VRF leader election: each validator's VRF output on the prev block determines proposer rank.
[ ] BLS aggregate signature from > 2/3 validators required to finalise.

### 3.3 — `chain/mempool.py`, `chain/node.py`
[ ] Mempool: pending match-outcome transactions.
[ ] Node: single in-process node (we're local-only) running propose/verify/finalise.

### 3.4 — `chain/explorer_api.py`
[ ] REST + WS endpoints: `/chain/blocks?limit=N`, `/chain/block/{hash}`, `/ws/chain` (new-block stream).

🔒 **`@crypto-auditor`** — full pass on all of `chain/`.

→ `git tag phase-3-done`

**Learning session:** `@learner` on `consensus.py` and `snark.py` together (how a block proves match validity).

---

## Phase 4 — Learning

### 4.1 — PettingZoo wrapper

[ ] `packages/learning/penumbra_learning/env.py`: wrap `core/simulation` as a `pettingzoo.ParallelEnv`.

### 4.2 — MAPPO

[ ] `learning/mappo.py`: adapt CleanRL's `ppo_pettingzoo` to MAPPO style (centralised critic, decentralised actors). Device: `mps`.

**Prompt to `@coder`:**
> Implement `learning/mappo.py` based on CleanRL's ppo_pettingzoo template. CTDE (centralised critic, decentralised actor). Actor + critic each ≤ 2-layer MLP, hidden 128. Device `torch.device("mps")` with a CPU-fallback path. Checkpoint every K updates.

### 4.3 — GATv2 pathfinder

[ ] `learning/gat_pathfinder.py`: PyTorch Geometric GATv2 estimator of shortest distance node → goal given current edge costs.

### 4.4 — Self-play training

[ ] `learning/training.py`: train, evaluate, checkpoint. Ship one pre-trained checkpoint at `checkpoints/mappo_v0.pt`.

→ `git tag phase-4-done`

**Learning session:** `@learner` on CTDE and on GAT attention.

---

## Phase 5 — Analytics

One recipe pattern per module. Files in `packages/analytics/penumbra_analytics/`:

### 5.1 — `descriptive.py`
Summary stats via Polars + pingouin. `Concept taught: effect sizes vs p-values`.

### 5.2 — `inferential.py`
Mann-Whitney, permutation, χ². `Concept taught: nonparametric inference under non-Gaussian outcomes`.

### 5.3 — `econometrics.py`
OLS, IV (`linearmodels.IV2SLS`), panel (`PanelOLS`), GMM, VAR (`statsmodels.tsa.api.VAR`), GARCH (`arch.arch_model`), cointegration (Johansen), Granger causality. One function per model. `Concept taught: each model in turn — see per-function docstrings`.

### 5.4 — `time_series.py`
ARIMA (`pmdarima.auto_arima`), Kalman (`filterpy`), Bayesian change-point. `Concept taught: state-space modelling`.

### 5.5 — `monte_carlo.py`
Sobol QMC (`scipy.stats.qmc.Sobol`), bootstrap (`arch.bootstrap`), VaR/CVaR via empirical quantile. `Concept taught: variance reduction via quasi-MC`.

### 5.6 — `causal.py`
DoubleML, EconML CATE, dowhy. `Concept taught: identification under unconfoundedness`.

### 5.7 — `survival.py`
Kaplan-Meier + Cox via lifelines. `Concept taught: censoring and hazard ratios`.

### 5.8 — `bayesian.py`
NumPyro SVI posterior over a tracked agent's region given DP-noised observations. `Concept taught: variational inference`.

### 5.9 — `clustering.py`
HDBSCAN + sklearn spectral. `Concept taught: density-based vs spectral cuts`.

### 5.10 — `linalg.py`
Laplacian (SciPy sparse), spectral embedding. `Concept taught: Fiedler vector for graph partitioning`.

### 5.11 — `topology.py`
Ripser on the coalition graph filtered by encrypted proximity. `Concept taught: persistent homology births/deaths`.

### 5.12 — `transport.py`
POT Sinkhorn between successive encrypted heatmaps. `Concept taught: entropic optimal transport`.

### 5.13 — `topics.py`
BERTopic on a pre-seeded utterance corpus tied to agent action types. `Concept taught: topic drift over time`.

### 5.14 — `dashboard_pipeline.py`
Orchestrates everything on the right cadence (1 s, 5 s, per-match). asyncio queues.

**Prompt to `@coder` for each module:**
> Implement `analytics/<name>.py` per §5.<i>. Public function: `compute(state: SimulationState) -> <name>Result`. Property tests. Docstring with `Concept taught:` line. Register in `dashboard_pipeline.py` at cadence <X>.

→ `git tag phase-5-done`

**Learning sessions:** one per module with `@learner`. Pace yourself; don't rush.

---

## Phase 6 — Attacker Console + Shell Coach

### 6.1 — Attacker REPL backend 🔒

[ ] `packages/attacker/penumbra_attacker/console.py`: sandboxed REPL.
[ ] `packages/transport/repl_bridge.py`: WS ↔ REPL.

🔒 **`@crypto-auditor`** must verify the sandbox actually limits filesystem and network.

### 6.2 — Attacks 🔒

For each of `replay.py`, `linkability.py`, `dp_reconstruction.py`, `timing_sidechannel.py`, `byzantine.py`, `snark_forgery.py`:

**Prompt to `@coder`:**
> Implement `attacker/attacks/<name>.py`. The docstring documents (1) how the attack works, (2) why Penumbra resists it (or, if it doesn't, what mitigation would), (3) a "try it" recipe the user can paste in the REPL. Add an integration test that runs the attack against a freshly seeded simulation.

🔒 **`@crypto-auditor`** — every attack reviewed for correctness of the *attack* (so the user learns the right lesson) AND for the *defence* claim (so the docstring isn't misleading).

### 6.3 — `pna` CLI

[ ] `packages/attacker/penumbra_attacker/cli.py`: typer.

### 6.4 — Shell Coach lessons

[ ] `packages/shell_coach/lessons/01_filesystem.yaml` … `11_scripting.yaml`. Each is a sequence of `{step, instruction, validate_cmd, expected_pattern, hint}`.

### 6.5 — Suggester / explain / error helper

[ ] `packages/shell_coach/penumbra_shell_coach/suggester.py`: rule-based next-command suggester (no LLM call needed).
[ ] `.../explain.py`: parses argv for ~50 common commands, returns labelled flags.
[ ] `.../error_helper.py`: regex-driven interpretation of common stderr.

### 6.6 — `psh` CLI

[ ] `packages/shell_coach/penumbra_shell_coach/cli.py`: typer with `lessons`, `lesson <id>`, `explain <command>`, `suggest`.

### 6.7 — PTY bridge

[ ] `packages/transport/pty_bridge.py`: spawns `zsh` PTY, multiplexes IO over WS.

### 6.8 — Frontend terminal panel

[ ] `apps/web/src/terminal/Console.tsx` with PTY/REPL mode toggle, xterm.js.
[ ] `apps/web/src/coach/{Suggester,LessonStepper,ErrorHelper,History}.tsx`.

→ `git tag phase-6-done`

---

## Phase 7 — Frontend integration & polish

### 7.1 — Fuzzy agent clouds

[ ] In `Arena.tsx`, render each agent as a `<sprite>` with alpha derived from `bayesian.py` posterior σ; positions sampled from the posterior.

### 7.2 — Custom charts

[ ] `charts/Barcode.tsx` — D3 persistence diagram.
[ ] `charts/Sinkhorn.tsx` — animated transport plan.
[ ] `charts/FactionGraph.tsx` — cytoscape.js force layout.
[ ] `charts/EconometricsPanel.tsx`, `MonteCarloFan.tsx`, `BayesPosteriors.tsx`, `TopicDrift.tsx`.

### 7.3 — Blockchain explorer

[ ] `chain/Explorer.tsx`: block list + block detail + verified-proof badge.

### 7.4 — Dashboard layout

[ ] `routes/Dashboard.tsx`: final responsive grid (desktop-only).

### 7.5 — READMEs per package

[ ] Each `packages/*/README.md` summarises purpose + concept taught + a couple of suggested micro-experiments + link to `PROMPTING_GUIDE.md` section.

Invoke `@doc-writer`.

### 7.6 — E2E smoke (optional)

[ ] Playwright: app loads, simulation runs, attacker REPL responds, lesson 1 advances.

→ `git tag phase-7-done`

---

## After Phase 7 — Learning loop

The project is now your curriculum. Recommended order of "explain this" sessions with `@learner`:

1. `core/rng.py` + `core/arena.py` — RNG hygiene and the perpetual loop.
2. `crypto/ckks.py` + `crypto/educational/schnorr.py` — HE and ZK foundations.
3. `crypto/bls.py` + `chain/consensus.py` + `crypto/snark.py` — chain trio.
4. `analytics/linalg.py` + `analytics/topology.py` + `analytics/transport.py` — geometry trio.
5. `analytics/econometrics.py` — one model per session.
6. `learning/mappo.py` + `learning/gat_pathfinder.py` — NN trio.
7. `attacker/attacks/*` — adversarial intuition by trying each attack.
8. Shell Coach lessons 1–11 in order.

Each step is anchored by code that runs. No slides.

## Reference: agent quick-dispatch

| Want to … | Invoke |
|---|---|
| Build something new | `@coder` |
| Crypto / chain / attacker change | `@crypto-auditor` (mandatory), then `@coder`, then `@reviewer` |
| Review a diff | `@reviewer` |
| Doc / README / roadmap update | `@doc-writer` |
| Understand a concept (Italian) | `@learner` |
| Learn / practice a shell command | `@shell-coach` |
