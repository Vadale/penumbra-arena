# Contributing to Penumbra

Thanks for considering a contribution. Penumbra is built to teach;
clear, small, well-tested contributions are the most valuable.

## Setup

Penumbra runs on Mac (Apple Silicon, MPS) and Linux. Requirements:
Python 3.12+, Node 22+, pnpm 9+, uv 0.4+.

```sh
uv sync                          # Python deps (workspace)
pnpm install                     # JS deps (workspace)
docker compose up                # full stack on localhost
```

## Local checks (must pass before opening a PR)

```sh
uv run pytest -q                 # backend tests + property-based tests
uv run pyright                   # strict type checking
uv run ruff check . && uv run ruff format --check .
pnpm --filter web typecheck
pnpm --filter web lint
```

## Coding conventions

- **Python**: 3.12+, strict typing, `from __future__ import annotations`
  in every module, module docstring must include a `Concept taught: …`
  line, absolute imports only.
- **TypeScript**: strict mode, no `any`, no `as` casts outside type
  guards. React function components only.
- **Comments**: write none unless the *why* is non-obvious. Identifiers
  carry the *what*.
- **Files**: snake_case Python, PascalCase React components, kebab-case
  YAML lessons.

See `CLAUDE.md` for the full convention spec.

## Reproducibility

All randomness must go through `core/rng.py`. Never call `random`,
`np.random`, `torch.manual_seed`, or `jax.random.PRNGKey` directly.
Tests log the seed via `core/rng.run_record()`.

## Commit messages

Conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`,
`chore:`) with a one-line subject and an optional body. Sign-offs are
not required.

## Pull request flow

1. Open an issue first for non-trivial changes — alignment beats
   surprise. For small bug fixes, a PR direct is fine.
2. Branch from `main`. One change per PR.
3. Run the local checks above; CI re-runs them on every push.
4. Fill in the PR template (summary / what / why / how tested).
5. Crypto, chain, or attacker code requires a `crypto-auditor`
   review before merge (run `@crypto-auditor` if you use Claude
   Code; otherwise tag a maintainer with crypto background).

## Where to start

Look for the `good first issue` label. Other entry points:
- Documentation improvements in any `packages/*/README.md`.
- New analytics modules — follow the 5-step recipe in `CLAUDE.md`.
- New dashboard tiles — follow the 5-step pattern in `CLAUDE.md`.
- Shell Coach lessons (YAML in `packages/shell_coach/lessons/`).
- Benchmark submissions — see `BENCHMARK_PLAN.md`.

## Code of conduct

Participation is governed by `CODE_OF_CONDUCT.md` (Contributor
Covenant v2.1). Report incidents to the maintainer email listed
there.

## License

Contributions are licensed under MIT (code) and CC-BY-4.0 (data,
under `state/datasets/**`).
