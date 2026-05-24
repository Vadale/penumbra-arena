"""Entry point so `python -m penumbra_operator` invokes the `pno` CLI."""

from __future__ import annotations

from penumbra_operator.cli import app

if __name__ == "__main__":
    app()
