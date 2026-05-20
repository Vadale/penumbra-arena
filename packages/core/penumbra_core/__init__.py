"""Penumbra domain core.

Concept taught: hexagonal architecture — the domain holds no I/O and no
adapter logic; it exposes pure functions and dataclasses that every other
package depends on.
"""

from penumbra_core.rng import bootstrap, run_record

__all__ = ["bootstrap", "run_record"]
