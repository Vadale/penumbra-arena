# Changelog

All notable changes to this project are documented here. The format
is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/Vadale/penumbra-arena/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Vadale/penumbra-arena/releases/tag/v0.1.0
