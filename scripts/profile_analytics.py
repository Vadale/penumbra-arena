"""Synchronous profile of one analytics-loop iteration.

Concept taught: how to characterise the wall-time of a streaming
consumer by replicating the orchestrator's per-tick work synchronously
under cProfile. The async orchestrator is NOT used — we just rebuild
the pieces it touches (simulation + market + logistics + pipeline) and
drive them in a tight Python loop so cProfile captures Python-level
hot functions cleanly.
"""

from __future__ import annotations

import cProfile
import os
import pstats
import sys
import time
from io import StringIO
from pathlib import Path

import numpy as np

# Make sure we can import penumbra packages.
REPO = Path(__file__).resolve().parent.parent
for pkg in (
    "core",
    "crypto",
    "chain",
    "analytics",
    "learning",
    "attacker",
    "shell_coach",
    "transport",
):
    sys.path.insert(0, str(REPO / "packages" / pkg))

from penumbra_core.rng import bootstrap  # noqa: E402
from penumbra_core.simulation import Simulation, SimulationConfig  # noqa: E402


def main() -> None:
    seed = int(os.environ.get("PENUMBRA_SEED", "42"))
    seeded = bootstrap(seed)
    sim = Simulation.build(SimulationConfig(n_agents=50), seeded)

    from penumbra_transport.orchestrator import Orchestrator

    orch = Orchestrator.build(sim)
    # Wire the arena graph into the pipeline (spectral consumer).
    orch.pipeline.set_arena_graph(sim.arena.graph)
    # Warm the heatmap once.
    orch.heatmap.compute(sim)

    n_iters = int(os.environ.get("PROFILE_ITERS", "100"))
    n_warm = int(os.environ.get("PROFILE_WARMUP_TICKS", "30"))
    # Run the simulation forward a bit so buffers fill the >= 30 / >= 50
    # gates inside the pipeline (otherwise most consumers skip).
    for _ in range(n_warm):
        sim.tick()

    def one_analytics_iter() -> None:
        positions = np.asarray([a.position for a in sim.agents], dtype=np.float64)
        heatmap_density = orch.heatmap.latest.density if orch.heatmap.latest is not None else None
        utterances: list[str] = []
        orch.pipeline.observe(
            tick=sim.tick_counter,
            positions=positions,
            heatmap=heatmap_density,
            utterances=utterances,
        )
        if orch.market is not None:
            agent_positions = {a.id: a.position for a in sim.agents}
            rng = sim.seeded.numpy_for("economy")
            trades = orch.market.tick(  # type: ignore[attr-defined]
                tick=sim.tick_counter,
                agent_positions=agent_positions,
                rng=rng,
            )
            orch._step_logistics()
            orch._maybe_ingest_federated()
            orch._maybe_step_federated()
            orch.pipeline.record_trades(
                trades=trades,
                money_supply=orch.market.money_supply(),  # type: ignore[attr-defined]
                price_index=orch.market.price_index(),  # type: ignore[attr-defined]
                wealth=orch.market.wealth_distribution(),  # type: ignore[attr-defined]
                tick=sim.tick_counter,
            )
        orch.pipeline.recompute()
        orch.sign_and_verify_moves()

    # Prime once outside the profiler to populate caches / warm imports.
    one_analytics_iter()
    sim.tick()

    start = time.perf_counter()
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(n_iters):
        one_analytics_iter()
        # Drive the sim a few ticks between analytics ticks (mirrors
        # the 10 Hz tick / 1 Hz analytics ratio without sleeping).
        for _ in range(10):
            sim.tick()
    profiler.disable()
    wall = time.perf_counter() - start

    print(f"\nAnalytics iterations: {n_iters}")
    print(f"Wall time: {wall:.3f}s")
    print(f"Per-iter mean: {wall * 1000 / n_iters:.2f} ms")
    print()

    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream).strip_dirs()
    stats.sort_stats("cumulative")
    stats.print_stats(40)
    print(stream.getvalue())

    stream2 = StringIO()
    stats2 = pstats.Stats(profiler, stream=stream2).strip_dirs()
    stats2.sort_stats("tottime")
    stats2.print_stats(40)
    print(stream2.getvalue())

    out = REPO / "state" / "profile"
    out.mkdir(parents=True, exist_ok=True)
    profiler.dump_stats(str(out / "analytics.prof"))
    print(f"raw stats dumped to {out / 'analytics.prof'}")


if __name__ == "__main__":
    main()
