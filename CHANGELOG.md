# Changelog

All notable changes to this project are documented here. The format
is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

(no unreleased changes)

## [1.0.0] - 2026-05-25 — feature freeze

Penumbra is **feature-complete as a single monorepo**. Future work
moves to focused mini-projects ("spin-offs") that reuse packages from
this repo rather than new features on `main`. Top spin-off candidate:
`penumbra-chain-sim` (~95% reuse of `packages/chain/`); free side-quest:
`penumbra-educational-crypto` extracted to PyPI from
`packages/crypto/penumbra_crypto/educational/`.

This release tags the post-Phase-6b post-polish state:
- 856 backend tests + 105 vitest, all green
- 11 packages, 99 dashboard tiles, 82 chart components, 4 React routes
- CI green on ubuntu-latest in ~14 min (Python + frontend jobs)
- 3 CLIs (`pna`, `psh`, `pno`) honour `PENUMBRA_API_URL`
- All security-audit findings from the crypto-auditor sweep are closed
- Cross-pillar EventBus with 5 handler tiers wired in the orchestrator
- Operator cyber-range mode + 12 starter scenarios + session replay

No new features will land on `main` other than security fixes. The
entry-experience polish (Makefile, examples/, CONCEPTS.md, package
READMEs as tutorials) ships as part of this release; see the
"Entry-experience polish" section below.

### Added — Entry-experience polish (2026-05-25)

- `Makefile` at repo root with discoverable targets: `make demo` runs
  the clone-to-browser one-shot (uv sync + pnpm install + boot backend
  + frontend + health-check + open browser); `make dev`, `make test`,
  `make lint`, `make clean`.
- `scripts/demo.sh` — the actual orchestrator the `make demo` target
  invokes. Idempotent, handles existing-process-on-port, prints clear
  status, waits for `/health` 200 OK before opening browser.
- `examples/` directory with 6 self-contained scripts (~100 LOC each)
  that exercise one Penumbra primitive WITHOUT booting the full
  runtime. `uv run python examples/XX.py` works on a fresh clone.
- `CONCEPTS.md` at repo root — alphabetical glossary of ~50 concepts
  with `file:line` pointers. Grep-friendly entry for anyone looking
  for "where is the X implementation".
- README reduced to a one-screen hook (was 188 lines). Status line
  now reads "v1.0 — feature frozen; future work in focused spin-offs".
- 3 package READMEs rewritten as standalone tutorials:
  `packages/crypto/README.md` (implementing CKKS + DP step by step),
  `packages/attacker/README.md` (the 12 attacks and what defends each),
  `packages/learning/README.md` (MAPPO + DP-SGD walkthrough).

### Added — Interactive lab + runtime tunables + chart PNG quality (2026-05-24)

After end-to-end user testing of the v3 dashboard, surfaced + fixed:

- **3 React routes -> 4 routes**: new `/config` for live runtime
  configuration (5 mutable + 3 restart-required fields). Plus:
  AgentDetailPanel (click on agent in arena), Lab Experiments
  (centralized inject + step + recent injections log), Branch Compare
  (A vs B side-by-side), TimeScrubber (500-tick replay buffer w/
  REPLAY MODE banner), NotificationSettings (browser notifications
  per event kind), AchievementsPanel (9 unlock rules + toast),
  brush-select on 5 time-series charts.
- **Export every chart**: 7 metrics -> ~25 metrics with server-side
  matplotlib (800x400 with titles + axes + R^2 + CI bands).
  Client-side DOM-to-PNG fallback fixed to scale viewBox to 800x400
  with background color (was producing transparent postage stamps).
- **5 new env vars** for "watchable at 2 Hz default" tuning:
  PENUMBRA_TICK_HZ (default 2.0), PENUMBRA_GOAL_WALK_PERIOD
  (default 20, recommend 80), PENUMBRA_WEATHER_PROB (default 0.02,
  recommend 0.005), PENUMBRA_MATCH_MAX_TICKS (default 1200, recommend
  3600), PENUMBRA_ENABLE_REPL (companion to ENABLE_PTY).
- **PENUMBRA_API_URL** honoured by `pna` / `psh` / `pno` CLIs so a
  single `export PENUMBRA_API_URL=http://localhost:8100` routes every
  subcommand (was per-subcommand `--api` flag only).
- **Coach allow-list extended to `pno`** (was {"pna","psh"} only ->
  rejected `pno enable` from the dashboard coach panel).
- **/operator route 404 fix**: Vite proxy `/operator` now bypasses on
  the bare path so the React SPA serves it (sub-paths still proxy).
- **USAGE.md** added: 509-line hands-on quickstart covering boot, the
  3 CLIs, 20+ REST endpoints, dashboard interactions, 6 cookbook
  workflows, troubleshooting.

### Added — Phase 6a + 5 + 6b (2026-05-24)

#### Phase 6a — Cross-pillar EventBus + 5 handler tiers
- `packages/transport/penumbra_transport/events.py` — synchronous
  in-process EventBus with subscribe/emit/recent/stats. Per-kind
  p99 handler latency tracked.
- Tier 1 — Stats↔Logistics/Market: GARCH spike → ReorderPolicy
  retune + Market.pricing_regime transition.
- Tier 2 — Security↔Market/Logistics/FL: `agent.blocked` event
  routes blocked agents through Market.skip + assign_carriers.skip +
  FL trainer.zero_delta. New `/security/blocked-agents` endpoint.
- Tier 3 — DP-budget-aware analytics cadence: ε warning halves
  GARCH/NumPyro/BERTopic; ε exhaustion enters un-noised fallback
  + blocks DP-SGD rounds.
- Tier 4 — ML/RL↔Logistics reward loop: LiveTrainer env reads live
  orchestrator mempool; `ml.policy.updated` event after each PPO iter.
- Tier 5 — Chain-as-event-source: block.finalised → Market wallet
  credits for winners; slashing → FL block_agent. EventGraphChart tile.

#### Phase 5 — Crypto + Surveillance Attack/Defense Lab
- Tier 1 — 8 new crypto primitives: FROST, SPHINCS+, Verkle,
  BBS+, threshold ECDSA (GG18), Yao garbled circuits, PSI, Loopix
  mix-net, STARK verifier (FRI-based).
- Tier 2 — 6 attack modules in `packages/attacker/penumbra_attacker/attacks/`:
  agent_fingerprint, trajectory_fingerprint, membership_inference,
  model_inversion, reward_poisoning, cache_sidechannel.
- Tier 3 — 6 defenses in new `packages/crypto/penumbra_crypto/defenses/`
  sub-package: data_poisoning, padding, k_anonymity, l_diversity,
  GAN (real CycleGAN-style), request_obfuscation.
- Tier 4 — 4 interactive surfaces:
  - Custom policy injection (AST-walk sandboxed Python).
  - CTF mode (`packages/ctf/`, 5 starter challenges + leaderboard).
  - Jupyter `%penumbra` magics (`packages/notebook/`).
  - World branching for replay/compare (`world.WorldBranchRegistry`).
- Tier 5 — 8 cross-pillar story tutorials in `shell_coach/lessons/`:
  bullwhip-leak, honest-validator, replay-chain, dp-starvation,
  fl-backdoor, carrier-extortion, mix-net-defense, ctf-speedrun.

#### Phase 6b — Operator Mode / Cyber Range
- New top-level `packages/operator/` package mirroring `attacker/`.
- 20 operator actions (8 core + 6 attack + 6 defense) callable via
  `/operator/{kind}` REST or `pno` CLI.
- 12 starter YAML scenarios + ScenarioRunner + per-scenario
  leaderboard (`packages/operator/scenarios/`).
- Session replay parquet (SessionLogger) with determinism guarantee.
- React `/operator` route with Console: Status / Action Builder /
  Log / Score Card.
- `pno` CLI mirroring the HTTP surface.

#### Security audit follow-up (6 LOW findings closed)
- Groth16 G2 subgroup membership check.
- Chain finality threshold can be stake-weighted.
- Atomic `tmp+rename` writes for secrets/budget files.
- RDP order grid densified (12 → 60+ orders).
- Key zeroization helper + applied where secret keys leave scope.
- VRF + timing-sidechannel: `==` → `hmac.compare_digest`.

#### Operator Save & Resume (videogame-style)
- `packages/operator/penumbra_operator/save_resume.py` — save / load /
  discard helpers + `ActiveSave` pointer record. Persists ScenarioRunner
  state + full world snapshot under
  `state/operator_sessions/<session_id>/`. Pointer at
  `state/operator_sessions/active.json`.
- `packages/core/penumbra_core/persistence.py` — new shared
  `atomic_write(path, data, mode=0o644)` (tmp + os.replace);
  `save_simulation` now routes through it.
- `packages/transport/penumbra_transport/api.py` — 3 endpoints:
  `GET /operator/sessions/resumable`, `POST /operator/sessions/resume`,
  `POST /operator/sessions/discard`. Save hooks on scenario start,
  per-action drain, status (terminal), abandon.
- `apps/web/src/pages/Operator.tsx` — resume banner with `[Resume]` /
  `[Discard]` buttons; probes `/operator/sessions/resumable` on mount.
- Time semantics: sim-tick based (not wall-clock). The clock pauses
  while the player is away; failure clauses resume from the saved
  tick. All 12 starter scenarios already use elapsed-tick predicates;
  a parametrised test asserts no wall-clock predicate sneaks in.
- 9 backend tests + 19 endpoint tests + 2 vitests, all green.

#### Post-audit visibility + organicity fixes
- Wired 8 Phase 5 crypto tiles into `AnalyticsPanel.tsx` (FROST,
  SPHINCS+, Verkle, BBS+, threshold ECDSA, Yao, PSI, mix-net) —
  endpoints + charts + DetailModal entries had shipped but no
  `<Cell>` existed; from a user POV these 8 features were invisible.
- `apps/web/vite.config.ts` — `/ctf` and `/attacker` added to dev
  proxy (CTFChart + CustomPolicyChart no longer 404 in `pnpm dev`).
- `dashboard_pipeline.py` — `cpi.shock` event now actually emits
  (was a dormant subscriber). Mirrors the `garch.spike` pattern;
  EMA baseline + 30% threshold; 4 emit-tests.
- Doc count refresh: 91 clickable tiles / 96 chart components
  (was claimed "~98"); 832 backend tests (was claimed "~786").

### Added — earlier this release

#### Logistics layer (Tier 1 + 2)
- `packages/core/penumbra_core/logistics.py`: `CargoConstraints`,
  `DemandModel`, `Order`, `LogisticsMempool`, `ReorderPolicy` ((s, S)
  policy) + 4 KPI reports (`FillRate`, `InventoryHealth`,
  `OrderBook`, `CargoUtilization`).
- `packages/core/penumbra_core/logistics_or.py`: OR Tier 2 solvers —
  `solve_greedy_nearest_neighbor`, `solve_two_opt`, optional OR-Tools
  VRP wrapper, plus `build_arena_distance_matrix`.
- `orchestrator.py`: drives demand consumption + (s, S) reorder
  evaluation + 5-tick-lead-time fulfilment once per analytics tick.
- API: `/logistics/{fill-rate,inventory-health,orders,reorder-policy,
  capacity,vrp-baseline}` (6 endpoints).
- Frontend: 6 dashboard tiles wired into AnalyticsPanel + DetailModal.

#### Federated learning (Tier 1 + 2 + 4)
- `packages/learning/penumbra_learning/federated.py`: REAL local SGD
  (no synthetic gradients) with per-agent observation+label buffers
  (greedy-nearest-goal heuristic labels), `FederatedTrainer`,
  `LocalActor`, functional aggregators `fedavg`, `krum`,
  `trimmed_mean`, real CKKS encrypt-sum-decrypt with slot batching
  (TenSEAL backend, ~4096 slots/ciphertext).
- DP-SGD knobs (`dp_noise_sigma`, `dp_l2_clip`) with toy ε accountant
  (real RDP accountant in `federated_dp.py`).
- Orchestrator ingests per-agent observations + greedy labels every
  analytics tick when FL is enabled; auto-runs one FL round every
  30 ticks.
- API: `/federated/{status,start,stop,round,dp,method/{name}}`
  (6 endpoints, accepts `method ∈ {fedavg, ckks_sum, krum,
  trimmed_mean}`).
- Frontend: `FederatedStatusChart` with live method-switch dropdown.

#### Penumbra-Bench (Tier 1 + 2 + 3)
- 5 reference baselines at tier=tiny in `state/bench/*.json`:
  greedy-nearest-goal (0.8166), random-walk (0.4676),
  mappo-v0-high-temp (0.4455), min-cost (0.3709), stay-put (0.3025).
- `scripts/generate_baselines.py` produces all 5 in one run.
- Web leaderboard at `/bench`: tier selector, sortable composite
  table, click-to-expand detail. Powered by
  `GET /benchmark/leaderboard?tier=...&limit=...`.
- `scripts/validate_submission.py` — stdlib-only submission validator
  used by CI; checks schema, score bounds, composite recomputation.
- `.github/workflows/bench-validate.yml` — PR-triggered CI that runs
  the validator on every changed file under
  `state/bench/submissions/`.
- `state/bench/SCHEMA.json` — JSON Schema for the BenchSubmission
  payload.

#### Penumbra-Data
- `scripts/generate_dataset.py` now defaults the output directory to
  `state/datasets/<tier>` per the requested tier.
- Datasets generated: mini (500 ticks), standard (10k ticks); large
  (100k) + mega (1M) in progress.

#### Shared chart primitives
- Extracted Stat / Verdict / Block into `apps/web/src/charts/_shared/`.
  Stat supports `digits` ("adaptive" | number) + `suffix`; Verdict
  supports `okWord` / `rejectWord`.
- ~40/45 chart files migrated; ~787 LOC removed.

#### OSS launch materials
- `LICENSE` (MIT) + `LICENSE-DATA` (CC-BY-4.0).
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`,
  `CITATION.cff`.
- `.github/FUNDING.yml`, `.github/PULL_REQUEST_TEMPLATE.md`,
  `.github/ISSUE_TEMPLATE/{bug_report,feature_request,
  good_first_issue}.md`.
- `.github/workflows/ci.yml` — Python (uv + ruff + pyright + pytest)
  and Web (pnpm + tsc + biome + build) jobs.
- This `CHANGELOG.md`.
- Plan / spec docs:  `LOGISTICS_PLAN.md`,
  `FEDERATED_LEARNING_PLAN.md`, `BENCHMARK_PLAN.md`,
  `SYNTHETIC_DATA_PLAN.md`, `OSS_LAUNCH_ROADMAP.md`,
  `OSS_GROWTH_PLAYBOOK.md`, `REVIEW_PLAN.md`, `PAPER.md`.

### Changed

- `economy.py:Market`: `cargo` field added; BUY path caps quantity by
  `cargo.available(agent_id, inventory)`.
- `apps/web/src/charts/_shared/Stat.tsx`: now formats numeric values
  according to `digits` / `suffix`; adaptive ladder for "LineChart
  style" formatting.
- `apps/web/src/App.tsx`: minimal popstate-aware path router for the
  two top-level pages (`/`, `/bench*`).
- `scripts/generate_dataset.py`: `--output` defaults to
  `state/datasets/<tier>` instead of hardcoded `state/datasets/mini`.

### Fixed

#### Security (post-audit, 2026-05-23)
- **DP-SGD per-batch → per-example clipping** (`federated.py`). The
  RDP accountant in `federated_dp.py` is mathematically correct;
  the trainer previously clipped the AGGREGATED gradient after
  `loss.backward()`. Fixed via `torch.func.vmap(grad(...))` over
  `functional_call`, clipping each sample's gradient individually
  before summing + adding Gaussian noise. The (ε, δ) numbers the
  dashboard reports are now real DP-SGD guarantees per Abadi et
  al. 2016.
- **Poisson subsampling for DP-SGD** (`federated.py`). Replaced
  `torch.randint(0, n, ...)` (with-replacement) with Bernoulli
  per-example inclusion at rate `batch/n`. Matches the RDP-SGM
  analysis (Mironov-Talwar-Zhang 2019).
- **Merkle leaf-duplication malleability** (CVE-2012-2459 in
  `chain/merkle.py`). `build_root([a,b,c]) == build_root([a,b,c,c])`
  was true. Fixed with level-tagged internal hashes + fixed
  zero-leaf sentinel pad instead of duplicating the last leaf.
  *Breaking*: any persisted chain.parquet must be regenerated;
  in-memory chain unaffected.
- **DP noise PRNG → CSPRNG-seeded** (`crypto/dp.py`). Default
  `np.random.default_rng()` (PCG64 with non-cryptographic seed)
  replaced by a `secure_rng()` helper seeded from
  `secrets.token_bytes(8)`. Adversarial DP guarantees no longer
  require the user to also seed the noise generator.

#### Performance
- **Tick throughput optimization** (~22% CPU saved per analytics
  iter). `assign_carriers` now pre-computes one Dijkstra per
  destination instead of one per (order, agent). `EchelonNetwork`
  uses dict caches for `upstream_of` and role lookups. Dashboard
  pipeline cadences retuned: GARCH 10s → 30s, NumPyro SVI 10s →
  30s, regression 4s → 10s, monte_carlo 8s → 12s. QQ + residual
  computations moved inside the regression cadence branch.
- **`LogisticsMempool.fulfilled` cap** — was unbounded `list`, now
  `deque(maxlen=4096)`. Prevents unbounded growth on long-running
  orchestrators.
- **Orchestrator GC cadence tightened** — `gc.collect` every 2s
  (was 5s), `torch.mps.empty_cache` every 20s (was 60s) in the
  analytics loop. Stress-test measured 32-69 MB/h sustained drift
  (warmup-discounted) on the post-Phase-2.5 stack.

#### Misc
- `scripts/analyze_stress.py` now distinguishes warmup ramp from
  steady-state drift (previously linear-extrapolated `(end-start)/h`
  reported ~3 GB/h when actual sustained was ~70 MB/h).
- `scripts/generate_dataset.py` rewritten with `_ShardWriter` to
  write parquet incrementally every 100k ticks; mega tier @ 5M ticks
  now succeeds in 50min wall / 82 MB output.
- `SupplyGraphEncoder` swapped from in-tree `GATv2Layer` to
  canonical `torch_geometric.nn.GATv2Conv` (added `torch-geometric
  >=2.6` to `packages/learning/pyproject.toml`).
- `tests/test_submission_validator.py` now in the main pytest
  testpath (`pyproject.toml [tool.pytest.ini_options].testpaths`).
- Pre-existing biome-ignore stale suppressions left untouched (12
  warnings). New code adds none.
- Empty markdown table cell formatting in `BENCHMARK_PLAN.md`.

## [0.1.0] - 2026-05-XX

Initial pre-public release. See `ROADMAP.md` for the Phase 0-8 build
history.

[Unreleased]: https://github.com/Vadale/penumbra-arena/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Vadale/penumbra-arena/releases/tag/v1.0.0
[0.1.0]: https://github.com/Vadale/penumbra-arena/releases/tag/v0.1.0
