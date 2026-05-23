# Summary

(1-3 sentences. What changed and why.)

## What

(Bullet points listing concrete changes.)

-
-

## Why

(Context, motivation, links to issues if relevant.)

## How tested

- [ ] `uv run pytest -q`
- [ ] `uv run pyright`
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `pnpm --filter web typecheck` (if touching `apps/web/`)
- [ ] `pnpm --filter web lint` (if touching `apps/web/`)
- [ ] Manually exercised in browser (if user-visible)

## Checklist

- [ ] Module docstring on every new Python file includes
      `Concept taught: …`
- [ ] Public functions are typed + have a one-line docstring
- [ ] Memory budget unaffected (or impact documented)
- [ ] User-visible? Updated relevant `README.md`
- [ ] Touches `crypto/` or `chain/` or `attacker/`? Routed through
      `crypto-auditor` and noted in commit body
- [ ] Conventional commit message

## Notes for reviewer

(Anything specific to look at. Edge cases, performance trade-offs,
intentional skips, etc.)
