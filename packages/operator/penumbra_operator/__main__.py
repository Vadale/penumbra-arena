"""Entry point so `python -m penumbra_operator` invokes the `pno` CLI.

Concept taught: the `__main__.py` convention — how Python's module
execution protocol lets a package double as a CLI without exposing
an additional `scripts/` entry point, keeping installation and
introspection symmetric.
"""

from __future__ import annotations

from penumbra_operator.cli import app

if __name__ == "__main__":
    app()
