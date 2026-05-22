"""FastAPI application factory.

Concept taught: FastAPI's `lifespan` context manager owns the background
tick loop. When the app starts, the loop starts; when uvicorn issues a
shutdown signal, the lifespan exits and the loop is cancelled cleanly.
No global state, no atexit hooks.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig

from penumbra_transport.coach import DisallowedCommandError, run_command
from penumbra_transport.framing import encode_frame
from penumbra_transport.hub import Hub
from penumbra_transport.loop import TickLoop
from penumbra_transport.orchestrator import Orchestrator
from penumbra_transport.pty_bridge import (
    PtySession,
    pty_enabled,
    read_pty,
    spawn_shell,
)
from penumbra_transport.repl_bridge import (
    ReplSession,
    repl_enabled,
)
from penumbra_transport.repl_bridge import (
    execute as repl_execute,
)
from penumbra_transport.world import (
    InvalidSnapshotNameError,
    SnapshotNotFoundError,
    list_worlds,
    load_world,
    save_world,
)

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
        sim = simulation or _build_simulation_with_optional_mappo()
        hub = Hub()
        orchestrator = Orchestrator.build(sim)

        async def push(frame: TickFrame) -> None:
            await hub.broadcast(encode_frame(frame))

        loop = TickLoop(sim, push, tick_hz=tick_hz)
        await loop.start()
        # Warm-start the encrypted heatmap synchronously so the first
        # /encrypted-heatmap and /dashboard polls don't return
        # {"ready": false} / null fields just because the analytics tasks
        # haven't yet had time to run their first iteration.
        await asyncio.to_thread(orchestrator.heatmap.compute, sim)
        positions = np.asarray([a.position for a in sim.agents], dtype=np.float64)
        orchestrator.pipeline.observe(
            tick=sim.tick_counter,
            positions=positions,
            heatmap=orchestrator.heatmap.latest.density
            if orchestrator.heatmap.latest is not None
            else None,
        )
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

    @app.get("/arena/topology")
    async def arena_topology() -> dict[str, object]:
        """Full graph + current edge costs + goals.

        Polled by the frontend ~every 5s to redraw the force-directed
        2D arena view. Returns:
          nodes:   [int, ...]
          edges:   [{u, v, cost}, ...]
          goals:   [int, ...]
          tick:    int  (so the client knows how stale the snapshot is)
        """
        sim: Simulation = app.state.penumbra.simulation
        arena = sim.arena
        nodes = list(arena.graph.nodes())
        edges = []
        for u, v in arena.graph.edges():
            edges.append(
                {
                    "u": int(u),
                    "v": int(v),
                    "cost": float(arena.cost_of(int(u), int(v))),
                }
            )
        return {
            "nodes": nodes,
            "edges": edges,
            "goals": list(arena.goals),
            "tick": sim.tick_counter,
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

    @app.post("/chain/slash")
    async def chain_slash(payload: dict[str, object], request: Request) -> dict[str, object]:
        """Submit slashing evidence against a validator.

        Body: hex-encoded SlashingEvidence
          {offender_pubkey, height, block_a_hash, sig_a, block_b_hash, sig_b}
        Each sig must be over `domain_tag || height || block_hash` (see
        `consensus.canonical_block_sign_payload`).

        Audit closure A5: this endpoint is gated by a shared bearer
        token in the `PENUMBRA_SLASHING_ADMIN_TOKEN` env var. If unset,
        all calls return 403 (the demo path
        `/chain/_demo/self-slash` is what an interactive learner uses).
        """
        import hmac as _hmac
        import os as _os

        from penumbra_chain.slashing import SlashingError, SlashingEvidence

        admin_token = _os.environ.get("PENUMBRA_SLASHING_ADMIN_TOKEN")
        if not admin_token:
            raise HTTPException(
                status_code=403,
                detail=(
                    "POST /chain/slash is disabled: set PENUMBRA_SLASHING_ADMIN_TOKEN "
                    "in the backend env and pass `Authorization: Bearer <token>`"
                ),
            )
        provided = request.headers.get("authorization", "")
        scheme, _, given_token = provided.partition(" ")
        if scheme.lower() != "bearer" or not _hmac.compare_digest(given_token, admin_token):
            raise HTTPException(status_code=401, detail="invalid or missing bearer token")

        try:
            evidence = SlashingEvidence(
                offender_pubkey=bytes.fromhex(str(payload["offender_pubkey"])),
                height=int(payload["height"]),  # type: ignore[arg-type]
                block_a_hash=bytes.fromhex(str(payload["block_a_hash"])),
                sig_a=bytes.fromhex(str(payload["sig_a"])),
                block_b_hash=bytes.fromhex(str(payload["block_b_hash"])),
                sig_b=bytes.fromhex(str(payload["sig_b"])),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"bad evidence payload: {exc}") from exc

        node = app.state.penumbra.orchestrator.node
        try:
            tx = node.slash(evidence)
        except SlashingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {
            "slashed": evidence.offender_pubkey.hex()[:16] + "…",
            "height_observed": tx.height_observed,
            "active_validators": len(node.active_indices),
            "total_validators": len(node.validators),
        }

    @app.post("/chain/_demo/self-slash")
    async def chain_demo_self_slash() -> dict[str, object]:
        """Pedagogical only: have the node 'betray' its own validator 0.

        Generates two BLS sigs over two different fake block hashes
        using validator 0's secret key, then submits the resulting
        equivocation proof. After the call, validator 0 is removed
        from active_indices. Gated behind PENUMBRA_DEMO_SELF_SLASH=1
        so production-shaped runs can't accidentally enable it.
        """
        import hashlib
        import os

        from penumbra_chain.slashing import SlashingEvidence
        from penumbra_crypto import bls

        if os.environ.get("PENUMBRA_DEMO_SELF_SLASH") != "1":
            raise HTTPException(
                status_code=403,
                detail="self-slash demo disabled; set PENUMBRA_DEMO_SELF_SLASH=1 to enable",
            )

        node = app.state.penumbra.orchestrator.node
        # Pick the first currently-active validator so re-running stays
        # observable (not idempotent against the same index forever).
        if not node.active_indices:
            raise HTTPException(status_code=409, detail="no active validators left to slash")
        target_idx = min(node.active_indices)
        secret = node.secrets[target_idx]
        pub = node.validators[target_idx].bls_pubkey
        # Use a plausible "block height the offender double-signed at"
        # for the canonical sign payload. node.height + 1 mimics "at
        # the very next block they were going to propose".
        from penumbra_chain.consensus import canonical_block_sign_payload

        evidence_height = node.height + 1
        h_a = hashlib.sha256(b"demo-self-slash:branch-a").digest()
        h_b = hashlib.sha256(b"demo-self-slash:branch-b").digest()
        evidence = SlashingEvidence(
            offender_pubkey=pub,
            height=evidence_height,
            block_a_hash=h_a,
            sig_a=bls.sign(secret.bls_secret, canonical_block_sign_payload(h_a, evidence_height)),
            block_b_hash=h_b,
            sig_b=bls.sign(secret.bls_secret, canonical_block_sign_payload(h_b, evidence_height)),
        )
        tx = node.slash(evidence)
        return {
            "slashed": pub.hex()[:16] + "…",
            "height_observed": tx.height_observed,
            "active_validators": len(node.active_indices),
            "total_validators": len(node.validators),
        }

    @app.get("/agents/signing-stats")
    async def agents_signing_stats() -> dict[str, int]:
        """Aggregate Dilithium sign/verify counts since boot."""
        keystore = app.state.penumbra.orchestrator.keystore
        return {
            "verified": keystore.stats.verified,
            "rejected": keystore.stats.rejected,
            "n_agents": len(keystore.keypairs),
        }

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
        orchestrator = app.state.penumbra.orchestrator
        snap = orchestrator.latest_dashboard_snapshot
        summary = snap.summary
        dp_mechanism = orchestrator.heatmap.dp_mechanism
        dp_budget = (
            None
            if dp_mechanism is None
            else {
                "epsilon_total": dp_mechanism.budget.epsilon,
                "epsilon_spent": dp_mechanism.budget.epsilon_spent,
                "epsilon_remaining": dp_mechanism.budget.remaining_epsilon,
            }
        )
        signing_stats = {
            "verified": orchestrator.keystore.stats.verified,
            "rejected": orchestrator.keystore.stats.rejected,
            "n_agents": len(orchestrator.keystore.keypairs),
        }
        return {
            "tick": snap.tick,
            "dp_budget": dp_budget,
            "signing_stats": signing_stats,
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
            "n_topics": snap.n_topics,
            "topic_sizes": {str(k): v for k, v in snap.topic_sizes.items()},
            "topic_top_words": {str(k): list(v) for k, v in snap.topic_top_words.items()},
            "regression": (
                None
                if snap.regression is None
                else {
                    "slope": snap.regression.slope,
                    "intercept": snap.regression.intercept,
                    "r_squared": snap.regression.r_squared,
                    "n": snap.regression.n,
                    "sigma": snap.regression.sigma,
                    "points": [list(p) for p in snap.regression.points],
                }
            ),
            "cluster_scatter": (
                None
                if snap.cluster_scatter is None
                else {
                    "points": [list(p) for p in snap.cluster_scatter.points],
                    "n_clusters": snap.cluster_scatter.n_clusters,
                    "n_noise": snap.cluster_scatter.n_noise,
                }
            ),
            "monte_carlo": (
                None
                if snap.monte_carlo is None
                else {
                    "percentiles": {str(k): v for k, v in snap.monte_carlo.percentiles.items()},
                    "var": snap.monte_carlo.var,
                    "cvar": snap.monte_carlo.cvar,
                    "n_samples": snap.monte_carlo.n_samples,
                }
            ),
            "pca": (
                None
                if snap.pca is None
                else {
                    "eigenvalues": list(snap.pca.eigenvalues),
                    "explained_variance_ratio": list(snap.pca.explained_variance_ratio),
                    "top2_loadings": [list(p) for p in snap.pca.top2_loadings],
                }
            ),
            "arima_forecast": (
                None
                if snap.arima_forecast is None
                else {
                    "history": list(snap.arima_forecast.history),
                    "next_value": snap.arima_forecast.next_value,
                    "next_std": snap.arima_forecast.next_std,
                }
            ),
            "logit": (
                None
                if snap.logit is None
                else {
                    "intercept": snap.logit.intercept,
                    "slope": snap.logit.slope,
                    "curve": [list(p) for p in snap.logit.curve],
                    "points": [list(p) for p in snap.logit.points],
                    "n": snap.logit.n,
                    "pseudo_r2": snap.logit.pseudo_r2,
                }
            ),
            "bayesian_posterior": (
                None
                if snap.bayesian_posterior is None
                else {
                    "alpha": snap.bayesian_posterior.alpha,
                    "beta": snap.bayesian_posterior.beta,
                    "mean": snap.bayesian_posterior.mean,
                    "std": snap.bayesian_posterior.std,
                    "credible_low": snap.bayesian_posterior.credible_low,
                    "credible_high": snap.bayesian_posterior.credible_high,
                    "curve": [list(p) for p in snap.bayesian_posterior.curve],
                }
            ),
            "granger": (
                None
                if snap.granger is None
                else {
                    "series_names": list(snap.granger.series_names),
                    "p_values": [list(row) for row in snap.granger.p_values],
                    "max_lag": snap.granger.max_lag,
                    "n_obs": snap.granger.n_obs,
                }
            ),
            "economy": (
                None
                if snap.economy is None
                else {
                    "total_purchases": snap.economy.total_purchases,
                    "total_revenue": snap.economy.total_revenue,
                    "category_counts": dict(snap.economy.category_counts),
                    "top_products": [list(p) for p in snap.economy.top_products],
                    "basket_histogram": [list(p) for p in snap.economy.basket_histogram],
                }
            ),
            "survival": (
                None
                if snap.survival is None
                else {
                    "times": list(snap.survival.times),
                    "survival": list(snap.survival.survival),
                    "confidence_low": list(snap.survival.confidence_low),
                    "confidence_high": list(snap.survival.confidence_high),
                    "n_events": snap.survival.n_events,
                    "n_censored": snap.survival.n_censored,
                    "median_time": snap.survival.median_time,
                }
            ),
            "spectral": (
                None
                if snap.spectral is None
                else {
                    "eigenvalues": list(snap.spectral.eigenvalues),
                    "fiedler_value": snap.spectral.fiedler_value,
                    "n_nodes": snap.spectral.n_nodes,
                    "n_edges": snap.spectral.n_edges,
                    "fiedler_vector": list(snap.spectral.fiedler_vector),
                }
            ),
            "causal": (
                None
                if snap.causal is None
                else {
                    "n_treated": snap.causal.n_treated,
                    "n_control": snap.causal.n_control,
                    "ipw_ate": snap.causal.ipw_ate,
                    "ipw_se": snap.causal.ipw_se,
                    "aipw_ate": snap.causal.aipw_ate,
                    "aipw_se": snap.causal.aipw_se,
                    "propensity_treated": list(snap.causal.propensity_treated),
                    "propensity_control": list(snap.causal.propensity_control),
                }
            ),
            "var_irf": (
                None
                if snap.var_irf is None
                else {
                    "series_names": list(snap.var_irf.series_names),
                    "horizon": snap.var_irf.horizon,
                    "lag_order": snap.var_irf.lag_order,
                    "irf": [[list(row) for row in step] for step in snap.var_irf.irf],
                }
            ),
            "garch": (
                None
                if snap.garch is None
                else {
                    "omega": snap.garch.omega,
                    "alpha": snap.garch.alpha,
                    "beta": snap.garch.beta,
                    "persistence": snap.garch.persistence,
                    "log_returns": list(snap.garch.log_returns),
                    "conditional_volatility": list(snap.garch.conditional_volatility),
                }
            ),
            "qq_points": [list(p) for p in snap.qq_points],
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
            "noise_applied": sample.noise_applied,
            "epsilon_spent_total": sample.epsilon_spent_total,
        }

    @app.get("/dp/budget")
    async def dp_budget() -> dict[str, object]:
        """Snapshot of the DP accountant for the encrypted-heatmap mechanism."""
        mechanism = app.state.penumbra.orchestrator.heatmap.dp_mechanism
        if mechanism is None:
            return {"enabled": False}
        budget = mechanism.budget
        return {
            "enabled": True,
            "epsilon_total": budget.epsilon,
            "epsilon_spent": budget.epsilon_spent,
            "epsilon_remaining": budget.remaining_epsilon,
            "delta_total": budget.delta,
            "delta_spent": budget.delta_spent,
        }

    @app.post("/world/save")
    async def world_save(payload: dict[str, str]) -> dict[str, object]:
        name = payload.get("name", "")
        state = app.state.penumbra
        orchestrator = state.orchestrator
        dp_mechanism = orchestrator.heatmap.dp_mechanism
        ckks_backend = orchestrator.heatmap.backend
        try:
            path = save_world(
                name,
                orchestrator.node,
                state.simulation,
                ckks_backend=ckks_backend,
                dp_budget=dp_mechanism.budget if dp_mechanism is not None else None,
            )
        except InvalidSnapshotNameError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "name": name,
            "path": str(path),
            "height": orchestrator.node.height,
            "simulation_tick": state.simulation.tick_counter,
            "ckks_saved": True,
            "dp_budget_saved": dp_mechanism is not None,
        }

    @app.post("/world/load")
    async def world_load(payload: dict[str, str]) -> dict[str, object]:
        name = payload.get("name", "")
        try:
            new_node = load_world(name)
        except InvalidSnapshotNameError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SnapshotNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        orchestrator = app.state.penumbra.orchestrator
        orchestrator.node = new_node
        return {
            "name": name,
            "height": new_node.height,
            "active_validators": len(new_node.active_indices),
            "slashed": len(new_node.slashed_pubkeys),
        }

    @app.get("/world/list")
    async def world_list() -> dict[str, object]:
        entries = list_worlds()
        return {
            "snapshots": [
                {
                    "name": e.name,
                    "path": e.path,
                    "chain_height": e.chain_height,
                    "has_simulation": e.has_simulation,
                }
                for e in entries
            ]
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

    @app.get("/pty/status")
    async def pty_status() -> dict[str, object]:
        """Returns whether the PTY bridge is enabled for this process."""
        return {"enabled": pty_enabled()}

    @app.get("/repl/status")
    async def repl_status() -> dict[str, object]:
        """Returns whether the sandboxed Python REPL is enabled."""
        return {"enabled": repl_enabled()}

    @app.websocket("/ws/repl")
    async def ws_repl(websocket: WebSocket) -> None:
        """Bidirectional bridge to the sandboxed Penumbra REPL.

        Wire format (JSON text frames):
          → {"type": "submit", "source": "<one-liner>"}
          ← {"type": "result", "stdout": "...", "stderr": "..."}

        Gated by PENUMBRA_ENABLE_REPL=1.
        """
        if not repl_enabled():
            await websocket.close(code=4403)
            return

        await websocket.accept()
        import json

        orchestrator = app.state.penumbra.orchestrator
        session = ReplSession.for_orchestrator(orchestrator)
        welcome = session.api.help() + "\n"
        await websocket.send_text(json.dumps({"type": "result", "stdout": welcome, "stderr": ""}))
        try:
            while True:
                msg = await websocket.receive_text()
                try:
                    parsed = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                if parsed.get("type") != "submit":
                    continue
                source = parsed.get("source", "")
                stdout, stderr = await asyncio.to_thread(repl_execute, session, source)
                await websocket.send_text(
                    json.dumps({"type": "result", "stdout": stdout, "stderr": stderr})
                )
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/pty")
    async def ws_pty(websocket: WebSocket) -> None:
        """Bidirectional bridge between an xterm.js client and a fresh zsh PTY.

        Wire format (JSON text frames from the client):
          {"type": "input", "data": "<keystrokes>"}
          {"type": "resize", "rows": int, "cols": int}
        Frames TO the client are binary — raw PTY bytes including
        terminal escape sequences. xterm.js handles them natively.
        """
        if not pty_enabled():
            await websocket.close(code=4403)
            return

        await websocket.accept()
        session: PtySession = await asyncio.to_thread(spawn_shell)
        logger.info("PTY session pid=%d attached", session.pid)

        async def pump_pty_to_ws() -> None:
            async for chunk in read_pty(session):
                with contextlib.suppress(Exception):
                    await websocket.send_bytes(chunk)

        async def pump_ws_to_pty() -> None:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    return
                text = msg.get("text")
                if text is None:
                    continue
                import json

                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue
                kind = parsed.get("type")
                if kind == "input":
                    await session.write(parsed.get("data", "").encode("utf-8"))
                elif kind == "resize":
                    rows = int(parsed.get("rows", 24))
                    cols = int(parsed.get("cols", 80))
                    session.resize(rows=rows, cols=cols)

        pump_to = asyncio.create_task(pump_pty_to_ws())
        pump_from = asyncio.create_task(pump_ws_to_pty())
        try:
            await asyncio.wait({pump_to, pump_from}, return_when=asyncio.FIRST_COMPLETED)
        except WebSocketDisconnect:
            pass
        finally:
            for task in (pump_to, pump_from):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            await asyncio.to_thread(session.close)
            logger.info("PTY session pid=%d closed", session.pid)

    return app


def _build_simulation_with_optional_mappo() -> Simulation:
    """Build a Simulation, optionally restoring from snapshot and/or attaching MAPPO.

    Precedence
    ----------
    1. PENUMBRA_SIM_SNAPSHOT — if set and the file exists, restore the
       simulation from that snapshot (arena + agents + RNG state) and
       reattach policies via the MAPPO factory (or random walk if MAPPO
       missing).
    2. Otherwise build a fresh Simulation from seed.

    Both paths honour PENUMBRA_MAPPO_CHECKPOINT for the policy factory.
    """
    import os
    from pathlib import Path

    checkpoint = os.environ.get("PENUMBRA_MAPPO_CHECKPOINT", "checkpoints/mappo_v0.pt")
    snapshot = os.environ.get("PENUMBRA_SIM_SNAPSHOT", "")

    # Resolve the policy factory once; both branches use it.
    def _resolve_factory(n_agents: int) -> object | None:
        if not checkpoint:
            return None
        try:
            from penumbra_learning.policy_loader import mappo_policy_factory

            return mappo_policy_factory(checkpoint, n_agents=n_agents)
        except ImportError:
            logger.warning("penumbra_learning not importable; falling back to random walk")
            return None

    if snapshot and Path(snapshot).is_file():
        from penumbra_core.persistence import load_simulation

        factory = _resolve_factory(SimulationConfig().n_agents)
        logger.info("restoring simulation from %s", snapshot)
        return load_simulation(Path(snapshot), policy_factory=factory)  # type: ignore[arg-type]

    config = SimulationConfig()
    seeded = bootstrap()
    if not checkpoint:
        return Simulation.build(config, seeded)
    try:
        from penumbra_learning.policy_loader import (
            mappo_batch_policy,
        )

        batch_policy = mappo_batch_policy(checkpoint, n_agents=config.n_agents)
        # Batched policy path: ~50× faster on MPS than the per-agent
        # closure factory because we run ONE matmul over the (50,
        # obs_dim) stack instead of 50 sequential single-row passes.
        return Simulation.build(config, seeded, batch_policy=batch_policy)
    except ImportError:
        # penumbra-learning isn't installed (e.g. a slim deployment) — fall back.
        logger.warning("penumbra_learning not importable; falling back to random walk")
        return Simulation.build(config, seeded)


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
        "slashings": [
            {
                "offender_pubkey": s.evidence.offender_pubkey.hex()[:16] + "…",
                "height_observed": s.height_observed,
            }
            for s in blk.slashings
        ],
        "validator_count": len(blk.validator_pubkeys),
    }


app = build_app()
