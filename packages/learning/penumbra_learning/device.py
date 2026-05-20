"""Device selection: MPS > CUDA > CPU.

Concept taught: portable device selection. On the M4 we want MPS; on a
Linux CI box with CUDA we want CUDA; everywhere else (and as a safe
default) CPU. The same model code runs on all three.
"""

from __future__ import annotations

import torch


def best_device() -> torch.device:
    """Return the best available `torch.device` for training/inference."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")
