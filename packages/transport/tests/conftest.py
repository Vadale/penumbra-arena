"""Auto-mark every transport test as `slow`.

Every test in this package boots the FastAPI lifespan — which loads the
MAPPO checkpoint, initialises CKKS keys, hydrates the chain, and warms
the analytics pipeline. That fixed cost is ~25 s per test on CPU and
dominates the runtime: 23 test files × multiple cases × ~25 s would
exceed a free-CI runner's budget even before the assertions run.

Marking the whole package `slow` lets the standard CI invocation
(`pytest -k "not slow"`) skip these integration-style tests while
keeping them runnable locally with `pytest packages/transport`.

Pedagogical note: this is the *standard* hexagonal-architecture
contract — the `transport/` adapter is exactly where end-to-end tests
live, so being able to opt out of them in CI is by design.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply `@pytest.mark.slow` to tests collected from THIS directory only.

    `pytest_collection_modifyitems` is a *global* hook — pytest fires it for
    every item collected in the run, regardless of which conftest defined
    it. Without the path filter below we would silently mark the entire
    cross-package suite as `slow` and `-k "not slow"` would skip everything.
    """
    del config  # unused
    for item in items:
        if _HERE in Path(item.fspath).resolve().parents:
            item.add_marker(pytest.mark.slow)
