---
name: Good first issue
about: Bite-sized task suitable for new contributors (maintainer-curated)
title: '[GOOD-FIRST] '
labels: good first issue
assignees: ''
---

## Scope

(One-paragraph summary of what needs to be done. Should fit in
~2-4 hours of work for someone new to the codebase.)

## Files to touch

- `packages/...`
- `apps/web/src/...`

## Expected approach

(Brief sketch of the implementation. Point to existing patterns
in the codebase the contributor can mirror.)

## Acceptance criteria

- [ ] Tests added / updated
- [ ] `uv run pytest -q` passes
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check .` clean
- [ ] `pnpm --filter web typecheck` clean (if touching frontend)

## Helpful pointers

- Relevant docs: ...
- Similar existing code: ...
- Concepts to read first: ...
