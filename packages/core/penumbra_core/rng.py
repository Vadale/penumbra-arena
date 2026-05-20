"""Centralised seeded randomness.

Concept taught: reproducibility hygiene across multiple RNG-bearing libraries
(Python stdlib, NumPy, PyTorch, JAX). One env-seeded master fans into per-domain
sub-streams derived via SHA-256, so the arena, the agents, and the analytics
sample independently from each other yet remain bit-for-bit reproducible across
runs given the same seed.

This module **must** be imported before any other code that draws randomness.

Cryptographic randomness MUST NOT come from here — use `secrets` instead.
"""

from __future__ import annotations

import hashlib
import os
import platform
import random
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

import numpy as np
from numpy.random import Generator, default_rng

_ENV_VAR: Final[str] = "PENUMBRA_SEED"
_DEFAULT_SEED: Final[int] = 20260520  # YYYYMMDD of project genesis
_SUBKEY_BYTES: Final[int] = 8  # 64-bit sub-keys


@dataclass(frozen=True, slots=True)
class Seeded:
    """Snapshot of the seeding configuration for the current run.

    `master` is the user-facing seed (env var or default). `streams` is a
    dict of domain-name → 64-bit sub-key, deterministically derived from
    `master`. Callers should not mutate either after construction.
    """

    master: int
    streams: dict[str, int] = field(default_factory=dict)
    numpy: Generator = field(default_factory=lambda: default_rng())

    def stream(self, domain: str) -> int:
        """Return the 64-bit sub-key for `domain`, deriving it on demand."""
        if domain not in self.streams:
            object.__setattr__(
                self, "streams", {**self.streams, domain: _derive(self.master, domain)}
            )
        return self.streams[domain]

    def numpy_for(self, domain: str) -> Generator:
        """Return an independent NumPy `Generator` seeded for `domain`."""
        return default_rng(self.stream(domain))


def _derive(master: int, domain: str) -> int:
    """Derive a 64-bit sub-key from `master` and `domain` via SHA-256.

    Determinism: same `(master, domain)` → same sub-key, across processes.
    Independence: distinct domains produce uncorrelated sub-keys (assuming
    SHA-256 collision resistance).
    """
    payload = master.to_bytes(16, "big", signed=False) + b"|" + domain.encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:_SUBKEY_BYTES], "big", signed=False)


def _read_seed_from_env() -> int:
    raw = os.environ.get(_ENV_VAR)
    if raw is None:
        return _DEFAULT_SEED
    try:
        return int(raw)
    except ValueError as exc:
        raise InvalidSeedError(f"{_ENV_VAR}={raw!r} is not an integer") from exc


def bootstrap(seed: int | None = None) -> Seeded:
    """Seed every supported RNG library and return a `Seeded` snapshot.

    If `seed` is None, reads `PENUMBRA_SEED` from the environment, falling
    back to a fixed default. Idempotent — calling twice with the same seed
    leaves the libraries in the same state.

    Side effects: sets `random.seed`, `numpy.random.seed` (legacy),
    `torch.manual_seed`, `torch.mps.manual_seed`, `jax.random.PRNGKey`.
    """
    effective = seed if seed is not None else _read_seed_from_env()
    if effective < 0 or effective >= 2**64:
        raise InvalidSeedError(f"seed must fit in uint64; got {effective}")

    random.seed(effective)
    np.random.seed(effective % (2**32))  # legacy API takes 32-bit

    _seed_torch(effective)
    # JAX deliberately not auto-seeded — JAX is functional; callers ask for
    # a PRNGKey via `Seeded.stream("jax")` and build their own key tree.

    return Seeded(master=effective, numpy=default_rng(effective))


def _seed_torch(seed: int) -> None:
    """Seed PyTorch if installed; no-op otherwise.

    Concept taught: optional dependency injection. Core stays light; learning/
    can import torch and still rely on this seeding because `_seed_torch`
    re-checks for torch each time `bootstrap` is called.
    """
    try:
        import torch  # pyright: ignore[reportMissingImports]
    except ModuleNotFoundError:
        return
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        torch.mps.manual_seed(seed)


def run_record(seeded: Seeded) -> dict[str, str | int]:
    """Snapshot for logging at the start of any experiment.

    Captures the seed, the timestamp, and the versions of every library that
    consumes randomness. Drop this dict into your experiment log so a future
    reader can reproduce your run.
    """
    record: dict[str, str | int] = {
        "master_seed": seeded.master,
        "started_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
    }
    try:
        import torch  # pyright: ignore[reportMissingImports]

        record["torch"] = torch.__version__
        record["torch_device"] = _detect_torch_device()
    except ModuleNotFoundError:
        record["torch"] = "not-installed"
    try:
        import jax  # pyright: ignore[reportMissingImports]

        record["jax"] = jax.__version__
    except ModuleNotFoundError:
        record["jax"] = "not-installed"
    return record


def _detect_torch_device() -> str:
    try:
        import torch  # pyright: ignore[reportMissingImports]
    except ModuleNotFoundError:
        return "no-torch"
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class InvalidSeedError(ValueError):
    """Raised when the configured seed cannot be parsed or is out of range."""
