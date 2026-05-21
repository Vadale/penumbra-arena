"""FastAPI application factory.

Concept taught: FastAPI's `lifespan` context manager owns the background
tick loop. When the app starts, the loop starts; when uvicorn issues a
shutdown signal, the lifespan exits and the loop is cancelled cleanly.
No global state, no atexit hooks.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig

from penumbra_transport.coach import DisallowedCommandError, run_command
from penumbra_transport.framing import encode_frame
from penumbra_transport.hub import Hub
from penumbra_transport.loop import TickLoop
from penumbra_transport.orchestrator import Orchestrator

if TYPE_CHECKING:
    from penumbra_core.simulation import TickFrame

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppState:
    """Container for app-scoped singletons. Attached to `app.state.penumbra`."""

    simulation: Simulation
    hub: Hub
    loop: TickLoop
    orchestrator: Orchestrator


def build_app(
    simulation: Simulation | None = None,
    *,
    tick_hz: float = 10.0,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Construct a fresh FastAPI app.

    `simulation` lets tests inject a pre-built instance; in production
    the lifespan builds a fresh one seeded from the environment.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        sim = simulation or Simulation.build(SimulationConfig(), bootstrap())
        hub = Hub()
        orchestrator = Orchestrator.build(sim)

        async def push(frame: TickFrame) -> None:
            await hub.broadcast(encode_frame(frame))

        loop = TickLoop(sim, push, tick_hz=tick_hz)
        await loop.start()
        await orchestrator.start()
        app.state.penumbra = AppState(simulation=sim, hub=hub, loop=loop, orchestrator=orchestrator)
        try:
            yield
        finally:
            await orchestrator.stop()
            await loop.stop()

    app = FastAPI(
        title="Penumbra",
        version="0.1.0",
        description="Privacy-preserving perpetual multi-agent arena.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        state: AppState = app.state.penumbra
        return {
            "status": "ok",
            "uptime_seconds": round(state.loop.uptime_seconds(), 3),
            "tick": state.simulation.tick_counter,
            "subscribers": state.hub.subscriber_count,
            "match_id": state.simulation.current_match.id,
        }

    @app.get("/state")
    async def current_state() -> dict[str, object]:
        sim: Simulation = app.state.penumbra.simulation
        return {
            "tick": sim.tick_counter,
            "match_id": sim.current_match.id,
            "match_status": sim.current_match.status.value,
            "agent_positions": {str(a.id): a.position for a in sim.agents},
            "arena_goals": list(sim.arena.goals),
            "arena_edge_count": sim.arena.graph.number_of_edges(),
        }

    @app.post("/control/pause")
    async def pause() -> dict[str, str]:
        app.state.penumbra.simulation.pause()
        return {"state": "paused"}

    @app.post("/control/resume")
    async def resume() -> dict[str, str]:
        app.state.penumbra.simulation.resume()
        return {"state": "running"}

    @app.post("/control/step")
    async def step() -> dict[str, object]:
        sim: Simulation = app.state.penumbra.simulation
        sim.step_once()
        return {"tick": sim.tick_counter}

    @app.post("/control/time-warp/{multiplier}")
    async def set_time_warp(multiplier: int) -> dict[str, int]:
        if multiplier < 1 or multiplier > 100:
            raise HTTPException(status_code=400, detail="time_warp must be in [1, 100]")
        sim: Simulation = app.state.penumbra.simulation
        sim.config.time_warp = multiplier
        return {"time_warp": multiplier}

    @app.post("/coach/exec")
    async def coach_exec(payload: dict[str, str]) -> dict[str, object]:
        command_line = payload.get("command", "")
        try:
            result = await run_command(command_line)
        except DisallowedCommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
        }

    @app.get("/coach/presets")
    async def coach_presets() -> dict[str, list[dict[str, str]]]:
        """Curated set of commands the frontend exposes as one-click buttons."""
        return {
            "attacker": [
                {"label": "replay attack", "command": "pna replay-cmd"},
                {"label": "byzantine equivocation", "command": "pna byzantine-cmd"},
                {"label": "DP reconstruction", "command": "pna dp-reconstruct"},
                {"label": "linkability", "command": "pna linkability-cmd"},
            ],
            "shell": [
                {"label": "lessons", "command": "psh lessons"},
                {"label": "explain ls -la", "command": "psh explain 'ls -la'"},
                {"label": "suggest after ls", "command": "psh suggest ls"},
                {
                    "label": "interpret 'command not found'",
                    "command": "psh interpret 'zsh: command not found: rg'",
                },
            ],
        }

    @app.get("/dashboard")
    async def dashboard_snapshot() -> dict[str, object]:
        snap = app.state.penumbra.orchestrator.latest_dashboard_snapshot
        summary = snap.summary
        return {
            "tick": snap.tick,
            "summary": (
                None
                if summary is None
                else {
                    "n": summary.n,
                    "mean": summary.mean,
                    "std": summary.std,
                    "median": summary.median,
                    "iqr": summary.iqr,
                    "ci95_low": summary.ci95_low,
                    "ci95_high": summary.ci95_high,
                }
            ),
            "hdbscan_n_clusters": snap.hdbscan_n_clusters,
            "hdbscan_n_noise": snap.hdbscan_n_noise,
            "arima_next": snap.arima_next,
            "arima_std": snap.arima_std,
            "changepoints": list(snap.changepoints),
            "sinkhorn_cost": snap.sinkhorn_cost,
            "h0_total": snap.h0_total,
            "h1_total": snap.h1_total,
            "h0_bars": [list(bar) for bar in snap.h0_bars],
            "h1_bars": [list(bar) for bar in snap.h1_bars],
            "bayesian_theta": snap.bayesian_theta,
            "var95": snap.var95,
        }

    @app.get("/encrypted-heatmap")
    async def encrypted_heatmap() -> dict[str, object]:
        sample = app.state.penumbra.orchestrator.heatmap.latest
        if sample is None:
            return {"ready": False}
        return {
            "ready": True,
            "tick": sample.tick,
            "timestamp_ns": sample.timestamp_ns,
            "density": sample.density.tolist(),
            "decrypted_total": sample.decrypted_total,
        }

    @app.get("/chain/latest")
    async def chain_latest() -> dict[str, object]:
        node = app.state.penumbra.orchestrator.node
        if node.height == 0:
            return {"height": 0, "blocks": []}
        return {
            "height": node.height,
            "head_hash": node.head_hash.hex(),
            "blocks": [_block_view(b) for b in node.chain[-5:]],
        }

    @app.get("/chain/blocks")
    async def chain_blocks(limit: int = 20) -> dict[str, object]:
        node = app.state.penumbra.orchestrator.node
        limit = max(1, min(limit, 100))
        return {"blocks": [_block_view(b) for b in node.chain[-limit:]]}

    @app.get("/chain/block/{block_hash}")
    async def chain_block_by_hash(block_hash: str) -> dict[str, object]:
        node = app.state.penumbra.orchestrator.node
        for blk in node.chain:
            if blk.hash().hex() == block_hash:
                return _block_view(blk)
        raise HTTPException(status_code=404, detail=f"no block with hash {block_hash}")

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        hub: Hub = app.state.penumbra.hub
        sub = await hub.attach(websocket)
        try:
            await hub.pump(sub)
        except WebSocketDisconnect:
            pass
        finally:
            await hub.detach(sub)

    return app


def _block_view(blk: object) -> dict[str, object]:
    """Render a Block as a JSON-friendly dict for the explorer endpoints."""
    from penumbra_chain.block import Block

    if not isinstance(blk, Block):
        raise TypeError("_block_view expects a Block instance")
    return {
        "hash": blk.hash().hex(),
        "height": blk.header.height,
        "prev_hash": blk.header.prev_hash.hex(),
        "merkle_root": blk.header.merkle_root.hex(),
        "proposer_pubkey": blk.header.proposer_pubkey.hex(),
        "timestamp_ns": blk.header.timestamp_ns,
        "outcomes": [
            {
                "match_id": o.match_id,
                "winner_agent_id": o.winner_agent_id,
                "end_tick": o.end_tick,
                "end_reason": o.end_reason,
            }
            for o in blk.payload
        ],
        "validator_count": len(blk.validator_pubkeys),
    }


app = build_app()
