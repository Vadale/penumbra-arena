# Penumbra

> A privacy-preserving perpetual multi-agent arena built to teach
> statistics, linear algebra, modern neural networks, and cutting-edge
> cryptography in one integrated runtime — with a hands-on adversarial
> console and a real macOS/Unix shell coach baked in.

**Status**: post-Phase-8, preparing OSS launch. 326 tests green
(302 backend + 24 frontend), strict typing across the stack,
~33.6k LOC, 66+ git tags. See [`ROADMAP.md`](ROADMAP.md) for the
build history and [`OSS_LAUNCH_ROADMAP.md`](OSS_LAUNCH_ROADMAP.md)
for the public-release plan.

## Concept

50 autonomous agents compete on a procedurally dynamic graph ("arena").
Each agent's true state is encrypted (CKKS); the spectator sees only
DP-noised aggregates. Every pillar fires on every tick:

- **Neural networks** — MAPPO multi-agent RL on Apple MPS, GATv2 path-
  finder, live PPO training that mutates the inference policy in real
  time
- **Cryptography** — CKKS + TFHE homomorphic encryption, differential
  privacy with budget accounting, post-quantum (Kyber + Dilithium),
  BLS aggregate signatures, VRF leader election, Wesolowski VDF,
  Groth16 zk-SNARK verifier, educational SMPC primitives (Shamir +
  Beaver + Pedersen + Schnorr + LWE TFHE)
- **Statistics** — descriptive + inferential + econometrics (OLS / IV /
  GMM / VAR / GARCH / Granger / ARIMA) + Monte Carlo (Sobol QMC) +
  causal (IPW / AIPW) + survival (Kaplan-Meier) + Bayesian (NumPyro
  SVI) + ANOVA / permutation / Pearson + Spearman + ACF/PACF + ROC
- **Linear algebra & topology** — graph Laplacians + spectral clustering
  + persistent homology (ripser) + optimal transport (Sinkhorn)
- **Economy** — closed-system market with wallets, dynamic ask prices,
  production, OHLC candles, CPI inflation index, Gini wealth
  distribution
- **Blockchain** — local PoS-VRF chain with BLS-aggregated finality,
  mempool, slashing-by-equivocation
- **Adversarial console** — 6 attacks (`pna` CLI + dashboard chips):
  replay, byzantine, DP reconstruction, linkability, timing
  side-channel, SNARK forgery
- **Shell coach** — 11 curated macOS/Unix lessons (YAML), command
  explainer, error helper (`psh` CLI + sidebar)

Every concept above has a **clickable dashboard tile** that opens an
educational modal — ~57 tiles in total.

## Run

```sh
# Backend
PENUMBRA_SEED=42 \
PENUMBRA_MAPPO_CHECKPOINT="$(pwd)/checkpoints/mappo_v0.pt" \
uv run uvicorn penumbra_transport.api:app --port 8100

# Frontend (separate terminal)
PENUMBRA_API_PORT=8100 pnpm --filter web dev

# Or everything together
docker compose up
```

Then open <http://localhost:5173>.

Install the CLIs system-wide:

```sh
uv tool install ./packages/attacker     # pna --help
uv tool install ./packages/shell_coach  # psh lessons
```

## Architecture

Hexagonal. Pure domain in `packages/core/`, adapters elsewhere:

```
packages/
  core/         arena + agent + match + simulation + market economy
  crypto/       CKKS, TFHE, DP, Kyber, Dilithium, BLS, VRF, VDF, Groth16,
                educational SMPC (Shamir, Beaver, Pedersen, Schnorr, LWE)
  chain/        block + Merkle + PoS-VRF consensus + mempool + slashing
  learning/     MAPPO (CleanRL-style) + GATv2 + LiveTrainer + RewardWeights
  analytics/    13 streaming consumers + dashboard pipeline orchestrator
  attacker/     6 attacks + pna CLI
  shell_coach/  11 YAML lessons + suggester + explain + psh CLI
  transport/    FastAPI + WebSocket + PTY bridge + REPL bridge + orchestrator
apps/web/       React 19 + Vite + TS strict + r3f + tailwind v4 + biome
infra/          docker compose + Dockerfiles
circuits/       circom + snarkjs (multiplier + legal_path Groth16)
scripts/        training, memory profile, stress test, post-stress analysis
```

## Develop

```sh
uv sync                                  # install Python workspace
uv run pytest -q                         # 302 backend tests
uv run pyright                           # strict
uv run ruff check . && uv run ruff format --check .

pnpm install                             # install frontend
pnpm --filter web typecheck              # tsc --noEmit
pnpm --filter web test                   # 24 vitest
pnpm --filter web build                  # production bundle
pnpm --filter web exec biome check src   # lint
```

The full per-package contracts + endpoint table live in
[`packages/*/README.md`](packages/) (one per package) and
[`CLAUDE.md`](CLAUDE.md) at the repo root.

## Documents

| File | What it has |
|---|---|
| [`README.md`](README.md) | This file — orientation. |
| [`ROADMAP.md`](ROADMAP.md) | Build phases, what shipped where, tag-by-tag. |
| [`PROMPTING_GUIDE.md`](PROMPTING_GUIDE.md) | Step-by-step recipes for adding features. |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code instructions: conventions, agent guide, M4 budget. |
| [`OSS_LAUNCH_ROADMAP.md`](OSS_LAUNCH_ROADMAP.md) | The 12-week plan to take Penumbra public + the OSS promotion playbook. |
| [`OSS_PAPER_DRAFT.md`](OSS_PAPER_DRAFT.md) | Working draft of the academic preprint for the OSS launch. |
| [`LOGISTICS_PLAN.md`](LOGISTICS_PLAN.md) | Proposed Tier-1-to-4 logistics extension (post-launch). |
| [`EDU_B2B_PITCH.md`](EDU_B2B_PITCH.md) | Enterprise training — secondary commercial direction layered on top of OSS if demand validates. |
| [`REVIEW_PLAN.md`](REVIEW_PLAN.md) | Operating script for the post-stress review pass. |
| `packages/<name>/README.md` | Per-package "concept taught" + endpoints + experiments. |

## Hardware target

Mac mini M4, 16 GB RAM. Tested green; the build holds under 8 GB total
with browser + all subsystems active. CPU/MPS budgets and tuning levers
are documented in [`CLAUDE.md`](CLAUDE.md).

## License

MIT (planned for the public release; see
[`OSS_LAUNCH_ROADMAP.md`](OSS_LAUNCH_ROADMAP.md) week 2). Sole
author: **Vadale**.

## Contributing

Pre-launch the repo is private; once public, contribution guidelines
will live in `CONTRIBUTING.md` and the security policy in
`SECURITY.md`. Both are tracked in the OSS launch roadmap.
