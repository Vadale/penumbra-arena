# CLAUDE.md — Penumbra

Instructions for Claude Code working on this repository. Auto-loaded at session start.

## Project overview

**Penumbra** is a privacy-preserving perpetual multi-agent arena. N=20–50 agents
compete on a procedurally dynamic graph; their state is encrypted at rest and in
transit; a live dashboard streams encrypted aggregates, statistical inference,
linear-algebra/topology summaries, and on-chain match-outcome proofs. Two
embedded surfaces — the **Attacker Console** (CLI `pna` + in-app REPL) and the
**Shell Coach** (CLI `psh` + in-app `zsh` PTY with side-panel) — turn the
dashboard into a hands-on lab for adversarial crypto intuition and macOS/Unix
terminal fluency.

The codebase exists to teach. Every package directory is an entry point for
later "explain this" sessions with the user. Code quality matters as much as
feature count.

## Architecture map

Hexagonal (ports & adapters). Pure domain in `packages/core/`; adapters elsewhere.

```
packages/
  core/          domain — arena, agent, match, simulation tick (integration seam)
                 + economy (market, wallets, trades)
                 + logistics (cargo cap, demand, (s,S) reorder, KPIs)
                 + logistics_or (VRP solvers: greedy / 2-opt / OR-Tools)
                 + logistics_echelon (multi-echelon supplier → distributor → city
                                       w/ bullwhip)
  crypto/        CKKS / TFHE / DP / PQ (Kyber + Dilithium + SPHINCS+) / BLS / VRF
                 / VDF / Groth16 verifier / STARK verifier (FRI-based)
                 + FROST (threshold Schnorr) + threshold_ecdsa (GG18)
                 + Verkle (KZG-based, BLS12-381) + BBS+ (anonymous credentials)
                 + PSI (private set intersection via OPRF)
                 + mix_net (Loopix-style onion routing)
                 + defenses/ sub-package (data_poisoning, padding, k_anonymity,
                                          l_diversity, gan, request_obfuscation)
  crypto/educational/   from-scratch SMPC primitives (Shamir / Beaver / Pedersen
                 / Schnorr / TFHE-LWE / Yao garbled circuits) — offline-only
  chain/         block, Merkle (level-tagged + zero-leaf pad, CVE-2012-2459 closed),
                 PoS-VRF consensus, BLS aggregate, slashing, event hooks
  learning/      MAPPO (CleanRL-style) + GATv2 pathfinder
                 + federated (Tier 1-5: real local per-example DP-SGD with Poisson
                              subsampling + real CKKS encrypt-sum-decrypt aggregation
                              + Krum / TrimmedMean + FedProx + per-client heads
                              + top-k + 8-bit quantize)
                 + federated_dp (Rényi DP accountant, Sampled Gaussian Mechanism,
                                 dense 60+ order grid)
                 + logistics_shaper (reward weights: dispatch bonus/penalty,
                                     fill-rate bonus)
                 + supply_gnn (PyG GATv2Conv encoder over supply graph)
  analytics/     descriptive/inferential/econometrics/MC/causal/survival/Bayes/
                 clustering/linalg/topology/transport/topics + dashboard_pipeline
                 + DP-budget-aware cadence (Phase 6a Tier 3)
  attacker/      12 attacks (replay / byzantine / dp_reconstruction / linkability
                 / timing_sidechannel / snark_forgery + agent_fingerprint
                 / trajectory_fingerprint / membership_inference / model_inversion
                 / reward_poisoning / cache_sidechannel) + policy_sandbox
                 + pna CLI
  shell_coach/   19 lessons (11 base + 8 cross-pillar story tutorials)
                 + suggester + explain + error_helper + psh CLI
  transport/     FastAPI + WS + PTY bridge + REPL bridge + orchestrator
                 (drives logistics + multi-echelon + FL ingest + carrier dispatch
                  every analytics tick; owns EventBus for cross-pillar reactions)
                 + events.py (EventBus + 5 cross-pillar handler tiers wired:
                              Stats ↔ Logistics/Market; Security ↔ Market/FL;
                              DP-budget ↔ analytics cadence;
                              ML/RL ↔ Logistics reward loop;
                              Chain ↔ Market wallet credits)
                 + world.py (snapshot / load / branch + advance / compare —
                             session-replay foundation)
  operator/      cyber range package: operator agent (id N+1) + 20 actions
                 (8 core + 6 attack + 6 defense) + scenario engine + 12 starter
                 YAML scenarios + replay log (parquet) + pno CLI
  ctf/           Capture-the-flag mode: Challenge registry + 5 starter YAML
                 challenges + flag templating + per-challenge leaderboard
  notebook/      `%penumbra` IPython magics (connect / snapshot / %%attack)
                 for live attach to the running orchestrator from Jupyter
apps/web/        React + Vite + TS strict + r3f
                 + 91 clickable tiles / 96 chart components
                   (was ~57 pre-Phase 2.5)
                 + 3 routes: / (dashboard), /bench (leaderboard), /operator
                   (Console: Status / Action Builder / Log / Score)
infra/           docker compose + Dockerfiles
```

## Build / test / lint commands

Python:
```sh
uv sync                                  # install deps in workspace
uv run pytest -q                         # tests (incl. property-based)
uv run pyright                           # types — strict
uv run ruff check .                      # lint
uv run ruff format .                     # format
```

Frontend:
```sh
pnpm install                             # workspace install
pnpm --filter web typecheck              # tsc --noEmit
pnpm --filter web lint                   # biome
pnpm --filter web dev                    # vite dev server
pnpm --filter web build                  # production build
```

Runtime:
```sh
docker compose up                        # full stack on localhost

# Recommended boot (slower watchable dynamics + PTY + REPL + MAPPO):
PENUMBRA_SEED=42 \
PENUMBRA_TICK_HZ=2.0 \
PENUMBRA_GOAL_WALK_PERIOD=80 \
PENUMBRA_WEATHER_PROB=0.005 \
PENUMBRA_MATCH_MAX_TICKS=3600 \
PENUMBRA_ENABLE_PTY=1 \
PENUMBRA_ENABLE_REPL=1 \
PENUMBRA_MAPPO_CHECKPOINT="$(pwd)/checkpoints/mappo_v0.pt" \
uv run uvicorn penumbra_transport.api:app --port 8100

PENUMBRA_API_PORT=8100 pnpm --filter web dev

uv tool install ./packages/attacker      # then: pna --help
uv tool install ./packages/shell_coach   # then: psh lessons
uv tool install ./packages/operator      # then: pno --help

# After install, set the API URL once for all three CLIs:
export PENUMBRA_API_URL=http://localhost:8100
```

See [`USAGE.md`](USAGE.md) for the full hands-on tour.

Profiling (M4):
```sh
/usr/bin/time -l uv run python -m penumbra.simulation     # peak RSS
uv run python -X tracemalloc=5 -m penumbra.simulation
```

## Coding conventions

**Python**:
- 3.12+. Strict typing — no untyped public function. Use `from __future__ import annotations` everywhere.
- Module docstring on every file must include a `Concept taught: ...` line.
- No comments unless they explain non-obvious *why*. Identifiers carry the *what*.
- Imports sorted by ruff. Absolute imports only.
- Errors via `Exception` subclasses in the same package, never bare `raise`.
- Async by default in `transport/` and `chain/`; sync in `core/`, `analytics/`, `learning/`.
- Prefer Polars over Pandas; Pandas only where a library demands it.

**TypeScript**:
- Strict mode, no `any`, no `as` casts outside type guards.
- React function components, hooks, no class components.
- Co-locate component + its test + its CSS module under one folder.
- State in zustand stores; never prop-drill more than two levels.

**File naming**: snake_case for Python modules; PascalCase for React components; kebab-case for YAML lessons.

## Runtime tunables (env vars)

The backend reads these at boot. See [`USAGE.md`](USAGE.md) §1 for the
full table.

| Var | Default | Recommended (2 Hz viewing) | Purpose |
|---|---|---|---|
| `PENUMBRA_SEED` | 42 | — | Seed fan-out |
| `PENUMBRA_TICK_HZ` | 2.0 | 2.0 | Simulation cadence |
| `PENUMBRA_GOAL_WALK_PERIOD` | 20 | 80 | Ticks between goal migration |
| `PENUMBRA_WEATHER_PROB` | 0.02 | 0.005 | Per-tick weather flip probability |
| `PENUMBRA_MATCH_MAX_TICKS` | 1200 | 3600 | Match length (30 min at 2 Hz) |
| `PENUMBRA_ENABLE_PTY` | unset | 1 | Real macOS zsh in bottom shell tab |
| `PENUMBRA_ENABLE_REPL` | unset | 1 | Sandbox Python REPL in bottom repl tab |
| `PENUMBRA_MAPPO_CHECKPOINT` | unset | `$(pwd)/checkpoints/mappo_v0.pt` | MAPPO policy; otherwise random walk |
| `PENUMBRA_HE_BACKEND` | `openfhe` | — | `openfhe` or `tenseal` |
| `PENUMBRA_API_PORT` | 8000 | 8100 (Vite dev) | Backend port |
| `PENUMBRA_API_URL` | http://localhost:8000 | http://localhost:8100 | Default for `pna` / `psh` / `pno` CLIs |

`/config` exposes the live values via `GET /config` and accepts partial
updates via `POST /config` (runtime-mutable keys: `tick_hz`,
`reward_weights.*`, `defenses.dp_epsilon_budget`).

## Reproducibility rules

- All randomness goes through `core/rng.py`. Never call `random`, `np.random`,
  `torch.manual_seed`, or `jax.random.PRNGKey` directly.
- Every experiment logs its seed via `core/rng.run_record()`.
- Seed source: `PENUMBRA_SEED` env var. Default is a fixed value documented in the file.

## Memory budgets (M4 / 16 GB)

| Component | Budget |
|---|---|
| FastAPI process | < 1.5 GB |
| PyTorch (MPS) | < 2.5 GB |
| Analytics workers | < 1 GB |
| Blockchain node | < 300 MB |
| Browser | < 2 GB |
| **Total** | **< 8 GB** |

Levers when over budget:
- CKKS poly degree → 8192; SIMD-pack 32–64 agents per ciphertext; aggregate at 1 Hz not per tick
- MAPPO nets: 2-layer MLP, hidden 128
- NumPyro SVI, never MCMC, on the live path
- Polars lazy frames; never materialise full history

## MPS specifics

- `torch.device("mps")`. Some ops fall back to CPU silently — verify with
  `torch.set_default_device("mps")` and a sanity forward pass on import.
- Avoid `float64` on MPS (slow); prefer `float32`.
- BERTopic embedding model: `bge-small-en-v1.5` (small footprint, MPS-friendly).

## Crypto rules (mandatory)

- **Never** call `numpy.random` or `random` for key material. Use `secrets.token_bytes`.
- Constant-time comparisons via `hmac.compare_digest`, **never** `==` on secrets.
- Nonces from `secrets.token_bytes`; never reuse a nonce across Schnorr signatures.
- CKKS: rescale after every multiplication unless you've explicitly accounted for the level budget.
- All changes to `packages/crypto/`, `packages/chain/`, or `packages/attacker/` **must** be reviewed by the `crypto-auditor` agent before commit.
- HE backend toggle: `PENUMBRA_HE_BACKEND={openfhe,tenseal}`. Default `openfhe`; fallback documented.

## Dashboard tile pattern (post Phase 8) — 5 steps

Every new "thing the user can click" on the analytics grid follows
the same shape. See `apps/web/src/charts/*Chart.tsx` for ~30 examples.

1. **Backend endpoint** — add one `@app.get` (or POST) under
   `packages/transport/penumbra_transport/api.py`. Return a flat
   JSON dict with `available: bool` so the frontend can render an
   empty state cleanly.
2. **Chart component** — `apps/web/src/charts/FooChart.tsx`. Fetch
   the endpoint on mount + a small interval for live ones; render
   an SVG or grid of Stat cells. Look at `VDFChart` for a minimal
   one-shot panel and `TrainingCurves` for a polling one.
3. **Modal route** — extend `MetricKind` in `DetailModal.tsx` with
   the new id, add the META entry (label + description) and one
   `if (metric === "...") return <FooChart />` branch.
4. **Tile** — add a `<Cell label="..." onClick={() => open("...")}/>`
   in `AnalyticsPanel.tsx`; remember to add the new id to both the
   `mapMetricToHistoryKey` exclusion list and the openMetric switch.
5. **Proxy** — if the endpoint is on a NEW path prefix (e.g.
   `/foo/...`), add `"/foo": API_HTTP` to `apps/web/vite.config.ts`
   (we burned half a session debugging "loading…" panels because of
   this one).

## Live MAPPO training (background task)

The actor is shared between inference and the background trainer.
`MappoRuntime` in `packages/learning/penumbra_learning/policy_loader.py`
holds the live `agent_net` + mutable `temperature` + `enabled` flag;
`LiveTrainer` in `live_trainer.py` runs one PPO iteration at a time
against the same actor. To drive it:

- `POST /learning/training/start` — kicks off the background task
- `POST /learning/training/stop` — pauses
- `GET /learning/training/curves` — last 200 (iter, losses, KL, reward)

When extending the trainer, KEEP the rollout env's `n_agents` equal
to the checkpoint's `MAPPOConfig.n_agents` — the critic dim has to
match, otherwise the first PPO step crashes (we built `build_live_trainer`
explicitly to enforce this).

## Pre-commit hygiene

Biome is INSIDE pre-commit (added 2026-05-22 to fix a class of silent
commit-rollback bugs). When pre-commit reformats a file, the hook
fails, you re-stage with `git add -A`, re-commit, and the formatted
file is included. **After every commit, run `git log --oneline -1`
and confirm HEAD matches the new message** — if it doesn't, the
commit was silently rolled back and you need to re-stage.

## Adding a new analytics module — 5 steps

1. Create `packages/analytics/<name>.py` with module docstring including `Concept taught: ...`.
2. Expose a single public function `compute(state: SimulationState) -> <name>Result`.
3. Register it in `packages/analytics/dashboard_pipeline.py` with its cadence (1s, 5s, per-match).
4. Add a property-based test under `tests/analytics/test_<name>.py`.
5. Update the corresponding `packages/analytics/README.md` section.

## Agent dispatch guide

| Want to … | Invoke |
|---|---|
| Implement a feature | `@coder` |
| Code review on a diff | `@reviewer` |
| Crypto / chain / attacker change | `@crypto-auditor` (mandatory) then `@reviewer` |
| Write or update docs / READMEs / ROADMAP / PROMPTING_GUIDE | `@doc-writer` |
| Have a concept explained (in Italian) | `@learner` |
| Learn a Unix/macOS command or work through a lesson | `@shell-coach` |

## Definition of done (any change)

A change is "done" only when:

- [ ] `uv run pytest -q` passes (incl. property tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check .` and `ruff format --check .` clean
- [ ] If touching `apps/web/`: `pnpm --filter web typecheck` and `lint` clean
- [ ] If touching `crypto/`, `chain/`, or `attacker/`: `crypto-auditor` sign-off recorded in commit body
- [ ] Module docstring has a `Concept taught:` line
- [ ] Public functions are typed and have a one-line docstring
- [ ] Memory budget unaffected (or impact documented)
- [ ] Conventional commit message
- [ ] If user-visible: relevant `README.md` updated

## Communication preferences

- **Code, identifiers, file names, commit messages**: English.
- **Comments in code**: English.
- **Module docstrings**: English (with the `Concept taught:` line).
- **Explanations to the user when they ask**: Italian (this is when the `learner` agent shines).
- **Default response length**: tight. Match the question.

## Operating principles

- Trust the user to redirect; don't over-confirm.
- For destructive operations (delete, force-push, drop tables), confirm first.
- Crypto changes are not destructive but are high-risk; route through `crypto-auditor`.
- When you discover unexpected state (files, branches, locks), investigate before deleting.
- Prefer editing existing files to creating new ones. New files require justification.

## Repo visibility policy (mandatory — applies to every future session)

The GitHub repo `Vadale/penumbra-arena` is **PRIVATE on purpose**.

**DO NOT flip visibility to public** unless the user has just told you
to in this very session, AND the [REPO VISIBILITY GATE](USER_TODO.md)
items 1-3 are confirmed closed:

1. `vadale93@gmail.com` replaced with a dedicated alias in
   `SECURITY.md` + `CODE_OF_CONDUCT.md` + `USER_TODO.md`.
2. `docs/hero.png` exists.
3. `docs/og.png` exists.

These are blockers because public visibility is hard-to-undo
(Google indexing + bot forks + cache copies make rollback partial).

If the user asks you to flip without these closed, FLAG the gate,
ask for re-confirmation, and only proceed after the user explicitly
overrides ("I know, do it anyway"). Don't infer authorization from
adjacent requests like "push to GitHub" — those are NOT visibility
changes.

Same caution applies to:
- `gh repo edit --delete` (irreversible).
- Force-pushes to `main` on a public repo (rewrites visible history).
- Publishing to Hugging Face Hub from `state/datasets/` (CC-BY-4.0
  means once it's out there, attribution is irrevocable).
- Submitting to arXiv (preprint ID is permanent).
