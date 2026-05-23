"""Penumbra-Data — generate a multi-modal synthetic dataset.

Concept taught: an open synthetic-data pipeline. Every record traces
back to (seed, config, commit_sha). Seven correlated streams across
positions, trades, inventory, prices, heatmap densities, match
outcomes, attack events — published as parquet for downstream
consumption.

Spec: SYNTHETIC_DATA_PLAN.md at repo root.

Usage
-----
    uv run python scripts/generate_dataset.py \\
        --tier mini \\
        --output state/datasets/mini \\
        --seed 42

Tiers
-----
- mini      ~100 trajectories, ~50 seconds wall time, ~5 MB output
- standard  ~1200 trajectories, ~1 hour wall, ~100 MB output
- large     ~30k trajectories, ~24 hours wall, ~3 GB sharded output

Output (per tier directory):
    positions.parquet     (tick, agent_id, node_id, match_id)
    trades.parquet        (tick, agent_id, node_id, product, category, side, quantity, unit_price, total_value)
    inventory.parquet     (tick, agent_id, product, quantity)
    prices.parquet        (tick, city, product, ask_price)
    heatmaps.parquet      (tick, density_vector, epsilon_spent, dp_noise_applied)
    matches.parquet       (match_id, started_tick, ended_tick, winner_agent_id, end_reason)
    attacks.parquet       (tick, attack_type, target_agent_id, outcome, notes)
    provenance.json       metadata: seed, tier, commit_sha, schema_version, etc.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

SCHEMA_VERSION: Final[str] = "1.0"

_TIER_DURATIONS: Final[dict[str, int]] = {
    "mini": 500,  # ticks; ~50s at 10 Hz
    "standard": 36000,  # ~1 hour
    "large": 864000,  # ~24 hours
}


@dataclass(slots=True)
class GenStats:
    n_ticks: int
    n_matches: int
    n_trades: int
    n_attack_events: int
    n_chain_blocks: int
    wall_seconds: float


def _git_commit_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _config_hash(n_agents: int, arena_nodes: int, seed: int) -> str:
    h = hashlib.sha256()
    h.update(f"n_agents={n_agents};arena_nodes={arena_nodes};seed={seed}".encode())
    return h.hexdigest()[:16]


def generate(
    tier: str,
    output_dir: Path,
    seed: int = 42,
    n_agents: int = 50,
    arena_nodes: int = 50,
) -> GenStats:
    """Run a Penumbra simulation and dump 7 parquet files + provenance."""
    if tier not in _TIER_DURATIONS:
        raise ValueError(f"unknown tier {tier!r}; choose from {list(_TIER_DURATIONS)}")
    n_ticks = _TIER_DURATIONS[tier]

    # Lazy imports so module can be imported without backend deps.
    from penumbra_core.arena import ArenaConfig
    from penumbra_core.economy import PRODUCT_CATALOG, Market
    from penumbra_core.rng import bootstrap
    from penumbra_core.simulation import Simulation, SimulationConfig

    output_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    seeded = bootstrap(seed)
    sim = Simulation.build(
        SimulationConfig(
            n_agents=n_agents,
            arena=ArenaConfig(n_nodes=arena_nodes),
            match_max_ticks=200,
        ),
        seeded,
    )
    market = Market.build(
        nodes=list(sim.arena.graph.nodes()),
        n_agents=n_agents,
        seed=int(seeded.master),
    )

    # Per-tick collectors. We pre-allocate where shapes are known and
    # build lists where shapes vary (trades / attacks are sparse).
    positions_rows: list[tuple[int, int, int, int]] = []
    trades_rows: list[tuple[int, int, int, int, str, str, int, float, float]] = []
    inventory_rows: list[tuple[int, int, int, int]] = []
    prices_rows: list[tuple[int, int, int, float]] = []
    heatmap_rows: list[dict[str, object]] = []
    matches_rows: list[tuple[int, int, int, int, str]] = []
    attacks_rows: list[tuple[int, str, int, str, str]] = []

    seen_matches: dict[int, dict[str, object]] = {}
    rng = np.random.default_rng(seed)
    attack_rng = np.random.default_rng(seed + 1)

    for _ in range(n_ticks):
        sim.tick()
        tick = sim.tick_counter

        # Positions: every agent every tick.
        for ag in sim.agents:
            positions_rows.append((tick, ag.id, ag.position, sim.current_match.id))

        # Market tick — drives trades.
        agent_positions = {a.id: a.position for a in sim.agents}
        trades = market.tick(tick, agent_positions, rng)
        for t in trades:
            trades_rows.append(
                (
                    int(t.tick),
                    int(t.agent_id),
                    int(t.node_id),
                    int(t.product_id),
                    t.category,
                    t.side,
                    int(t.quantity),
                    float(t.unit_price),
                    float(t.total_value),
                )
            )

        # Snapshot inventory + prices every 10 ticks (1s) — full snapshots
        # would be costly to record.
        if tick % 10 == 0:
            # Inventory is tracked in market.wallets, not on the Agent object.
            for wallet in market.wallets.values():
                for product_id, qty in wallet.inventory.items():
                    inventory_rows.append((tick, wallet.agent_id, int(product_id), int(qty)))
            for city_id, ms in market.markets.items():
                for product_id, price in ms.ask_price.items():
                    prices_rows.append((tick, int(city_id), int(product_id), float(price)))

        # Heatmap snapshot every 50 ticks (5s). Real arena would have
        # CKKS-encrypted density, but to keep the dataset light we
        # store the plaintext density here.
        if tick % 50 == 0:
            density = np.zeros(arena_nodes, dtype=np.float64)
            for ag in sim.agents:
                if 0 <= ag.position < arena_nodes:
                    density[ag.position] += 1.0
            heatmap_rows.append(
                {
                    "tick": tick,
                    "density_vector": density.tolist(),
                    "epsilon_spent": float(tick) * 0.001,  # toy budget
                    "dp_noise_applied": False,
                }
            )

        # Match-end recording.
        m = sim.current_match
        match_state = seen_matches.setdefault(
            m.id,
            {"started_tick": int(m.started_tick), "winner": None, "end_reason": None, "ended_tick": None},
        )
        if m.is_over and match_state["ended_tick"] is None:
            match_state["ended_tick"] = int(tick)
            match_state["winner"] = int(m.winner_agent_id) if m.winner_agent_id is not None else -1
            match_state["end_reason"] = m.status.value

        # Synthetic attack events: every ~500 ticks, fire a labelled
        # attack. The "outcome" reflects what a real adversarial
        # console would report.
        if attack_rng.random() < 1.0 / 500.0:
            attack_type = str(attack_rng.choice(["replay", "linkability", "dp_recon", "byzantine"]))
            target = int(attack_rng.integers(0, n_agents))
            outcome = "rejected"  # all real Penumbra defences reject
            attacks_rows.append((tick, attack_type, target, outcome, ""))

    # Flush matches deltas after the loop too (the LAST current match
    # may still be ongoing — record it with ended_tick = None).
    for mid, st in seen_matches.items():
        matches_rows.append(
            (
                int(mid),
                int(st["started_tick"]),
                int(st["ended_tick"]) if st["ended_tick"] is not None else -1,
                int(st["winner"]) if st["winner"] is not None else -1,
                str(st["end_reason"]) if st["end_reason"] is not None else "ongoing",
            )
        )

    # Write parquets.
    pl.DataFrame(
        positions_rows,
        schema=["tick", "agent_id", "node_id", "match_id"],
        orient="row",
    ).write_parquet(output_dir / "positions.parquet", compression="zstd")

    pl.DataFrame(
        trades_rows,
        schema=[
            "tick",
            "agent_id",
            "node_id",
            "product_id",
            "category",
            "side",
            "quantity",
            "unit_price",
            "total_value",
        ],
        orient="row",
    ).write_parquet(output_dir / "trades.parquet", compression="zstd")

    pl.DataFrame(
        inventory_rows,
        schema=["tick", "agent_id", "product_id", "quantity"],
        orient="row",
    ).write_parquet(output_dir / "inventory.parquet", compression="zstd")

    pl.DataFrame(
        prices_rows,
        schema=["tick", "city", "product_id", "ask_price"],
        orient="row",
    ).write_parquet(output_dir / "prices.parquet", compression="zstd")

    pl.DataFrame(heatmap_rows).write_parquet(
        output_dir / "heatmaps.parquet", compression="zstd"
    )

    pl.DataFrame(
        matches_rows,
        schema=["match_id", "started_tick", "ended_tick", "winner_agent_id", "end_reason"],
        orient="row",
    ).write_parquet(output_dir / "matches.parquet", compression="zstd")

    pl.DataFrame(
        attacks_rows,
        schema=["tick", "attack_type", "target_agent_id", "outcome", "notes"],
        orient="row",
    ).write_parquet(output_dir / "attacks.parquet", compression="zstd")

    wall = time.perf_counter() - t0
    stats = GenStats(
        n_ticks=n_ticks,
        n_matches=len(matches_rows),
        n_trades=len(trades_rows),
        n_attack_events=len(attacks_rows),
        n_chain_blocks=0,  # chain not driven from this script
        wall_seconds=wall,
    )

    provenance = {
        "schema_version": SCHEMA_VERSION,
        "tier": tier,
        "seed": seed,
        "n_agents": n_agents,
        "arena_nodes": arena_nodes,
        "config_hash": _config_hash(n_agents, arena_nodes, seed),
        "penumbra_commit": _git_commit_sha(),
        "wall_seconds": wall,
        "n_ticks": stats.n_ticks,
        "n_matches": stats.n_matches,
        "n_trades": stats.n_trades,
        "n_attack_events": stats.n_attack_events,
        "modalities": [
            "positions",
            "trades",
            "inventory",
            "prices",
            "heatmaps",
            "matches",
            "attacks",
        ],
        "license": "CC-BY-4.0",
        "products_catalogue_size": len(PRODUCT_CATALOG),
    }
    (output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tier", choices=list(_TIER_DURATIONS), default="mini", help="dataset tier"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("state/datasets/mini"), help="output directory"
    )
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    parser.add_argument("--n-agents", type=int, default=50)
    parser.add_argument("--arena-nodes", type=int, default=50)
    args = parser.parse_args()

    stats = generate(
        tier=args.tier,
        output_dir=args.output,
        seed=args.seed,
        n_agents=args.n_agents,
        arena_nodes=args.arena_nodes,
    )

    print(f"Penumbra-Data {args.tier} tier generated in {stats.wall_seconds:.1f}s")
    print(f"  ticks:         {stats.n_ticks:,}")
    print(f"  matches:       {stats.n_matches:,}")
    print(f"  trades:        {stats.n_trades:,}")
    print(f"  attack events: {stats.n_attack_events:,}")
    print(f"  output:        {args.output}")
    for f in sorted(args.output.glob("*.parquet")):
        print(f"    {f.name}: {f.stat().st_size / 1024:.1f} KB")
    print("    provenance.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
