"""Shared pytest fixtures for penumbra-core tests."""

from __future__ import annotations

import pytest
from penumbra_core.rng import Seeded, bootstrap


@pytest.fixture
def seeded() -> Seeded:
    """Bootstrap a fresh `Seeded` with the canonical test seed."""
    return bootstrap(42)
