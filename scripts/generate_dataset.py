"""Penumbra-Data — generate a multi-modal synthetic dataset.

Concept taught: an open synthetic-data pipeline. Every record traces
back to (seed, config, commit_sha). Seven correlated streams across
positions, trades, inventory, prices, heatmap densities, match
outcomes, attack events — published as parquet for downstream
consumption. Output is written INCREMENTALLY in shards so the
generator's RAM footprint stays bounded regardless of tier size.

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
- mega      ~5M ticks; sharded output (~10 GB+)

Output (per tier directory): a sub-directory per modality, each
containing one or more `part-XXX.parquet` shards. With the default
chunk size, the `mini` tier yields exactly one shard per modality
(equivalent to the prior single-file layout).

    positions/part-NNN.parquet    (tick, agent_id, node_id, match_id)
    trades/part-NNN.parquet       (tick, agent_id, node_id, product, category, side, quantity, unit_price, total_value)
    inventory/part-NNN.parquet    (tick, agent_id, product, quantity)
    prices/part-NNN.parquet       (tick, city, product, ask_price)
    heatmaps/part-NNN.parquet     (tick, density_vector, epsilon_spent, dp_noise_applied)
    matches/part-NNN.parquet      (match_id, started_tick, ended_tick, winner_agent_id, end_reason)
    attacks/part-NNN.parquet      (tick, attack_type, target_agent_id, outcome, notes)
    provenance.json               metadata: seed, tier, commit_sha, schema_version, chunk_ticks, n_shards_per_modality, etc.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np
import polars as pl

SCHEMA_VERSION: Final[str] = "1.1"
CHUNK_TICKS: Final[int] = 100_000

_TIER_DURATIONS: Final[dict[str, int]] = {
    "mini": 500,  # ticks; ~5s wall
    "standard": 36000,  # ~30s wall (~1h sim @ 10 Hz)
    "large": 864000,  # ~12min wall (~24h sim @ 10 Hz)
    "mega": 5_000_000,  # ~spec target; sharded output keeps RAM bounded
}

_MODALITIES: Final[tuple[str, ...]] = (
    "positions",
    "trades",
    "inventory",
    "prices",
    "heatmaps",
    "matches",
    "attacks",
)

_SCHEMAS: Final[dict[str, list[str]]] = {
    "positions": ["tick", "agent_id", "node_id", "match_id"],
    "trades": [
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
    "inventory": ["tick", "agent_id", "product_id", "quantity"],
    "prices": ["tick", "city", "product_id", "ask_price"],
    "matches": ["match_id", "started_tick", "ended_tick", "winner_agent_id", "end_reason"],
    "attacks": ["tick", "attack_type", "target_agent_id", "outcome", "notes"],
}


@dataclass(slots=True)
class GenStats:
    n_ticks: int
    n_matches: int
    n_trades: int
    n_attack_events: int
    n_chain_blocks: int
    wall_seconds: float
    n_shards_per_modality: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class _MatchState:
    started_tick: int
    ended_tick: int | None = None
    winner: int | None = None
    end_reason: str | None = None


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


class _ShardWriter:
    """Accumulate rows for one modality and flush them as numbered shards."""

    def __init__(self, root: Path, modality: str, schema: list[str] | None) -> None:
        self.dir = root / modality
        self.dir.mkdir(parents=True, exist_ok=True)
        self.modality = modality
        self.schema = schema
        self.rows: list[Any] = []
        self.n_shards = 0
        self.n_rows_total = 0

    def append(self, row: Any) -> None:
        self.rows.append(row)

    def extend(self, rows: list[Any]) -> None:
        self.rows.extend(rows)

    def flush(self) -> None:
        if not self.rows:
            return
        path = self.dir / f"part-{self.n_shards:04d}.parquet"
        if self.schema is None:
            df = pl.DataFrame(self.rows)
        else:
            df = pl.DataFrame(self.rows, schema=self.schema, orient="row")
        df.write_parquet(path, compression="zstd")
        self.n_rows_total += len(self.rows)
        self.n_shards += 1
        self.rows.clear()

    def close(self) -> None:
        self.flush()


def generate(
    tier: str,
    output_dir: Path,
    seed: int = 42,
    n_agents: int = 50,
    arena_nodes: int = 50,
    chunk_ticks: int = CHUNK_TICKS,
) -> GenStats:
    """Run a Penumbra simulation and dump 7 sharded parquet modalities + provenance."""
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

    writers: dict[str, _ShardWriter] = {
        m: _ShardWriter(output_dir, m, _SCHEMAS.get(m)) for m in _MODALITIES
    }

    seen_matches: dict[int, _MatchState] = {}
    n_matches_finalized = 0
    rng = np.random.default_rng(seed)
    attack_rng = np.random.default_rng(seed + 1)

    n_trades_total = 0
    n_attack_events_total = 0

    for _ in range(n_ticks):
        sim.tick()
        tick = sim.tick_counter

        # Positions: every agent every tick.
        for ag in sim.agents:
            writers["positions"].append((tick, ag.id, ag.position, sim.current_match.id))

        # Market tick — drives trades.
        agent_positions = {a.id: a.position for a in sim.agents}
        trades = market.tick(tick, agent_positions, rng)
        for t in trades:
            writers["trades"].append(
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
            n_trades_total += 1

        # Snapshot inventory + prices every 10 ticks (1s) — full snapshots
        # would be costly to record.
        if tick % 10 == 0:
            for wallet in market.wallets.values():
                for product_id, qty in wallet.inventory.items():
                    writers["inventory"].append((tick, wallet.agent_id, int(product_id), int(qty)))
            for city_id, ms in market.markets.items():
                for product_id, price in ms.ask_price.items():
                    writers["prices"].append((tick, int(city_id), int(product_id), float(price)))

        # Heatmap snapshot every 50 ticks (5s). Real arena would have
        # CKKS-encrypted density, but to keep the dataset light we
        # store the plaintext density here.
        if tick % 50 == 0:
            density = np.zeros(arena_nodes, dtype=np.float64)
            for ag in sim.agents:
                if 0 <= ag.position < arena_nodes:
                    density[ag.position] += 1.0
            writers["heatmaps"].append(
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
            _MatchState(started_tick=int(m.started_tick)),
        )
        if m.is_over and match_state.ended_tick is None:
            match_state.ended_tick = int(tick)
            match_state.winner = int(m.winner_agent_id) if m.winner_agent_id is not None else -1
            match_state.end_reason = m.status.value

        # Synthetic attack events: every ~500 ticks, fire a labelled
        # attack. The "outcome" reflects what a real adversarial
        # console would report.
        if attack_rng.random() < 1.0 / 500.0:
            attack_type = str(attack_rng.choice(["replay", "linkability", "dp_recon", "byzantine"]))
            target = int(attack_rng.integers(0, n_agents))
            outcome = "rejected"  # all real Penumbra defences reject
            writers["attacks"].append((tick, attack_type, target, outcome, ""))
            n_attack_events_total += 1

        # Periodic flush: drop the per-tick row buffers to disk so RAM
        # doesn't grow unboundedly across tiers. Matches are emitted
        # only when they finalise, so they're flushed alongside.
        if tick % chunk_ticks == 0:
            for mid in list(seen_matches.keys()):
                st = seen_matches[mid]
                if st.ended_tick is None:
                    continue
                writers["matches"].append(
                    (
                        int(mid),
                        st.started_tick,
                        st.ended_tick,
                        st.winner if st.winner is not None else -1,
                        st.end_reason if st.end_reason is not None else "ongoing",
                    )
                )
                del seen_matches[mid]
                n_matches_finalized += 1
            for w in writers.values():
                w.flush()

    # Final pass: emit any matches we haven't recorded yet (including
    # the trailing in-flight match, which gets ended_tick=-1).
    for mid, st in seen_matches.items():
        writers["matches"].append(
            (
                int(mid),
                st.started_tick,
                st.ended_tick if st.ended_tick is not None else -1,
                st.winner if st.winner is not None else -1,
                st.end_reason if st.end_reason is not None else "ongoing",
            )
        )
        n_matches_finalized += 1
    seen_matches.clear()

    for w in writers.values():
        w.close()

    wall = time.perf_counter() - t0
    n_shards_per_modality = {m: writers[m].n_shards for m in _MODALITIES}
    n_matches_total = writers["matches"].n_rows_total

    stats = GenStats(
        n_ticks=n_ticks,
        n_matches=n_matches_total,
        n_trades=n_trades_total,
        n_attack_events=n_attack_events_total,
        n_chain_blocks=0,
        wall_seconds=wall,
        n_shards_per_modality=n_shards_per_modality,
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
        "chunk_ticks": chunk_ticks,
        "n_shards_per_modality": n_shards_per_modality,
        "modalities": list(_MODALITIES),
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
        "--output",
        type=Path,
        default=None,
        help="output directory (default: state/datasets/<tier>)",
    )
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    parser.add_argument("--n-agents", type=int, default=50)
    parser.add_argument("--arena-nodes", type=int, default=50)
    parser.add_argument(
        "--chunk-ticks",
        type=int,
        default=CHUNK_TICKS,
        help="ticks per shard flush (controls RAM vs. file count)",
    )
    args = parser.parse_args()
    if args.output is None:
        args.output = Path(f"state/datasets/{args.tier}")

    stats = generate(
        tier=args.tier,
        output_dir=args.output,
        seed=args.seed,
        n_agents=args.n_agents,
        arena_nodes=args.arena_nodes,
        chunk_ticks=args.chunk_ticks,
    )

    print(f"Penumbra-Data {args.tier} tier generated in {stats.wall_seconds:.1f}s")
    print(f"  ticks:         {stats.n_ticks:,}")
    print(f"  matches:       {stats.n_matches:,}")
    print(f"  trades:        {stats.n_trades:,}")
    print(f"  attack events: {stats.n_attack_events:,}")
    print(f"  output:        {args.output}")
    for modality in _MODALITIES:
        sub = args.output / modality
        if not sub.is_dir():
            continue
        shards = sorted(sub.glob("part-*.parquet"))
        total_bytes = sum(s.stat().st_size for s in shards)
        print(f"    {modality}/: {len(shards)} shard(s), {total_bytes / 1024:.1f} KB")
    print("    provenance.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
