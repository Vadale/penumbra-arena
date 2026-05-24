# Penumbra

> A privacy-preserving perpetual multi-agent arena built to teach
> statistics, linear algebra, modern neural networks, and cutting-edge
> cryptography in one integrated runtime — with a hands-on adversarial
> console and a real macOS/Unix shell coach baked in.
>
> Ships as a **3-in-1 artefact**: a **teaching platform** (~57
> concept tiles), a **benchmark suite** (Penumbra-Bench), and a
> **synthetic dataset** on Hugging Face Hub (Penumbra-Data).

**Status**: post-Phase-6b + interactive lab. **965+ tests** green
(~860 backend + 105 frontend), strict typing across the stack,
~85k LOC across 11 packages. See [`USAGE.md`](USAGE.md) for the
hands-on quickstart, [`ROADMAP.md`](ROADMAP.md) for the build
history, [`CHANGELOG.md`](CHANGELOG.md) for recent additions,
[`SECURITY_AUDIT.md`](SECURITY_AUDIT.md) for the crypto/chain/
attacker audit, and [`USER_TODO.md`](USER_TODO.md) for the
maintainer checklist before the public launch.

**4 React routes**: `/` (dashboard with 97 clickable tiles / 102
chart components — Lab + Achievements + AgentDetail + BranchCompare
+ TimeScrubber + Notifications), `/bench` (Penumbra-Bench
leaderboard), `/operator` (cyber-range Console with Save & Resume),
`/config` (live runtime configuration). Three CLIs: `pna` (attacker),
`psh` (shell coach), `pno` (operator) — all honour
`PENUMBRA_API_URL`.

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
| [`USAGE.md`](USAGE.md) | **Hands-on quickstart** — boot, dashboard interactions, all three CLIs (`pna` / `psh` / `pno`), REST endpoints, common workflows, troubleshooting. |
| [`ROADMAP.md`](ROADMAP.md) | Build phases, what shipped where, tag-by-tag. |
| [`PROMPTING_GUIDE.md`](PROMPTING_GUIDE.md) | Step-by-step recipes for adding features. |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code instructions: conventions, agent guide, M4 budget. |
| [`OSS_LAUNCH_ROADMAP.md`](OSS_LAUNCH_ROADMAP.md) | The 12-week timeline to take Penumbra public. |
| [`OSS_GROWTH_PLAYBOOK.md`](OSS_GROWTH_PLAYBOOK.md) | Deep tactical manual: free + organic stars and visibility (pre-launch SEO, channel etiquette, anti-patterns, KPI dashboard). |
| [`OSS_PAPER_DRAFT.md`](OSS_PAPER_DRAFT.md) | Working draft of the academic preprint for the OSS launch. |
| [`LOGISTICS_PLAN.md`](LOGISTICS_PLAN.md) | Proposed Tier-1-to-4 logistics extension (post-launch). |
| [`FEDERATED_LEARNING_PLAN.md`](FEDERATED_LEARNING_PLAN.md) | Federated learning extension — FedAvg + CKKS-encrypted aggregation + DP-SGD + Byzantine-robust variants (post-launch v1.2). |
| [`BENCHMARK_PLAN.md`](BENCHMARK_PLAN.md) | **Penumbra-Bench** — 5-task benchmark suite + leaderboard for privacy-aware, adversarially-robust, multi-agent RL. |
| [`SYNTHETIC_DATA_PLAN.md`](SYNTHETIC_DATA_PLAN.md) | **Penumbra-Data** — multi-modal synthetic dataset on Hugging Face Hub (Mini → Mega tiers) with full generative provenance. |
| [`EDU_B2B_PITCH.md`](EDU_B2B_PITCH.md) | Enterprise training — secondary commercial direction layered on top of OSS if demand validates. |
| [`REVIEW_PLAN.md`](REVIEW_PLAN.md) | Operating script for the post-stress review pass. |
| `packages/<name>/README.md` | Per-package "concept taught" + endpoints + experiments. |

## Hardware target

Mac mini M4, 16 GB RAM. Tested green; the build holds under 8 GB total
with browser + all subsystems active. CPU/MPS budgets and tuning levers
are documented in [`CLAUDE.md`](CLAUDE.md).

## License

- Code: **MIT** — see [`LICENSE`](LICENSE).
- Data: **CC-BY-4.0** — applies to `state/datasets/**` and Hugging
  Face dataset publications. See [`LICENSE-DATA`](LICENSE-DATA).

Sole author: **Vadale**.

## Citation

If you use Penumbra in research or teaching, please cite via the
[`CITATION.cff`](CITATION.cff) at the repo root, or use:

```bibtex
@software{vadale2026penumbra,
  author = {Vadale},
  title  = {Penumbra: a privacy-preserving perpetual multi-agent arena},
  year   = {2026},
  url    = {https://github.com/Vadale/penumbra-arena},
  note   = {MIT-licensed code + CC-BY-4.0 dataset}
}
```

Paper draft: [`PAPER.md`](PAPER.md) (arXiv-ready).

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, coding
conventions, and how to open a PR. Security disclosures go through
[`SECURITY.md`](SECURITY.md). Community conduct in
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Recent changes in
[`CHANGELOG.md`](CHANGELOG.md).
