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
  crypto/        CKKS, TFHE, DP, PQ (Kyber/Dilithium), BLS, VRF, VDF, Groth16
  crypto/educational/   from-scratch SMPC + ZK primitives (offline-only)
  chain/         block, Merkle, PoS-VRF consensus, BLS aggregation, explorer API
  learning/      MAPPO (CleanRL-style) + GATv2 pathfinder
  analytics/     descriptive/inferential/econometrics/MC/causal/survival/Bayes/
                 clustering/linalg/topology/transport/topics + dashboard_pipeline
  attacker/      console + attacks + pna CLI
  shell_coach/   lessons (YAML) + suggester + explain + error_helper + psh CLI
  transport/     FastAPI + WS + PTY bridge + REPL bridge
apps/web/        React + Vite + TS strict + r3f
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
PENUMBRA_SEED=42 uv run python -m penumbra.simulation
uv tool install ./packages/attacker      # then: pna --help
uv tool install ./packages/shell_coach   # then: psh lessons
```

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
