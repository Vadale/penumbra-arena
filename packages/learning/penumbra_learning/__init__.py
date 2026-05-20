"""Penumbra learning stack.

Concept taught: multi-agent reinforcement learning on Apple MPS, with a
graph attention network supplying spatial features. The whole stack
runs in <2.5 GB of memory and yields a trained policy that the
simulation can load in <5s.
"""

from penumbra_learning.device import best_device

__all__ = ["best_device"]
