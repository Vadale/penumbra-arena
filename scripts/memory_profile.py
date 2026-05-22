"""Identify the actual memory leaker via tracemalloc snapshot diff.

Runs the full orchestrator loop in-process for ~90 seconds, takes a
tracemalloc snapshot at t≈20s and t≈80s, prints the top deltas by
file:line. This sidesteps the lsof/psutil indirection of stress_test.py
and gets the leak at the byte level.

Usage:
    PENUMBRA_SEED=42 uv run python scripts/memory_profile.py
"""

from __future__ import annotations

import asyncio
import gc
import tracemalloc
from contextlib import suppress

from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.orchestrator import Orchestrator


async def main() -> None:
    sim = Simulation.build(SimulationConfig(), bootstrap())
    orch = Orchestrator.build(sim)
    await orch.start()

    tracemalloc.start(25)

    # Let the loops run for 20s, then take baseline.
    await asyncio.sleep(20)
    gc.collect()
    baseline = tracemalloc.take_snapshot()
    print("=== baseline at t=20s ===")
    for stat in baseline.statistics("lineno")[:5]:
        print(f"  {stat}")

    # Run another 60s.
    await asyncio.sleep(60)
    gc.collect()
    after = tracemalloc.take_snapshot()

    diff = after.compare_to(baseline, "lineno")
    print("\n=== top 20 allocators by GROWTH (t=80s vs t=20s) ===")
    for stat in diff[:20]:
        print(f"  {stat}")

    print("\n=== top 10 by absolute traceback ===")
    for stat in after.statistics("traceback")[:10]:
        print(f"\n--- {stat} ---")
        for line in stat.traceback.format()[-4:]:
            print(f"  {line}")

    await orch.stop()


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
