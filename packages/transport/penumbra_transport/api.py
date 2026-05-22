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
    mappo_runtime: object | None = None  # MappoRuntime when MAPPO loaded
    live_trainer: object | None = None  # LiveTrainer when MAPPO loaded


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
        mappo_runtime: object | None = None
        if simulation is None:
            sim, mappo_runtime = _build_simulation_with_optional_mappo()
        else:
            sim = simulation
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
        live_trainer: object | None = None
        if mappo_runtime is not None:
            try:
                from penumbra_learning.live_trainer import build_live_trainer

                live_trainer = build_live_trainer(mappo_runtime.agent_net)  # type: ignore[attr-defined]
            except Exception:
                logger.exception("failed to build live trainer; continuing without it")
        app.state.penumbra = AppState(
            simulation=sim,
            hub=hub,
            loop=loop,
            orchestrator=orchestrator,
            mappo_runtime=mappo_runtime,
            live_trainer=live_trainer,
        )
        try:
            yield
        finally:
            if live_trainer is not None:
                live_trainer.stop()  # type: ignore[attr-defined]
                task = getattr(live_trainer, "_task", None)
                if task is not None and not task.done():
                    task.cancel()
                    with contextlib.suppress(Exception):
                        await task
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
    async def chain_demo_self_slash(validator_index: int | None = None) -> dict[str, object]:
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
        if validator_index is None:
            target_idx = min(node.active_indices)
        else:
            if validator_index not in node.active_indices:
                raise HTTPException(
                    status_code=400,
                    detail=f"validator {validator_index} is not active",
                )
            target_idx = int(validator_index)
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
            "validator_index": target_idx,
            "offender_short": pub.hex()[:16],
            "height": tx.height_observed,
            "slashed": len(node.slashed_pubkeys),
            "active_after": len(node.active_indices),
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
                {"label": "timing side-channel", "command": "pna timing --samples 30"},
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
            "residual_vs_fitted": [list(p) for p in snap.residual_vs_fitted],
            "anova": (
                None
                if snap.anova is None
                else {
                    "f_statistic": snap.anova.f_statistic,
                    "p_value": snap.anova.p_value,
                    "df_between": snap.anova.df_between,
                    "df_within": snap.anova.df_within,
                    "grouping": snap.anova.grouping,
                    "group_names": list(snap.anova.group_names),
                    "group_means": list(snap.anova.group_means),
                    "group_se": list(snap.anova.group_se),
                    "group_n": list(snap.anova.group_n),
                    "grand_mean": snap.anova.grand_mean,
                }
            ),
            "autocorrelation": (
                None
                if snap.autocorrelation is None
                else {
                    "n_obs": snap.autocorrelation.n_obs,
                    "max_lag": snap.autocorrelation.max_lag,
                    "acf": list(snap.autocorrelation.acf),
                    "pacf": list(snap.autocorrelation.pacf),
                    "conf_band": snap.autocorrelation.conf_band,
                }
            ),
            "roc": (
                None
                if snap.roc is None
                else {
                    "fpr": list(snap.roc.fpr),
                    "tpr": list(snap.roc.tpr),
                    "thresholds": list(snap.roc.thresholds),
                    "auc": snap.roc.auc,
                }
            ),
            "correlations": (
                None
                if snap.correlations is None
                else {
                    "series_names": list(snap.correlations.series_names),
                    "pearson": [list(row) for row in snap.correlations.pearson],
                    "spearman": [list(row) for row in snap.correlations.spearman],
                    "n_obs": snap.correlations.n_obs,
                }
            ),
            "permutation": (
                None
                if snap.permutation is None
                else {
                    "observed_ate": snap.permutation.observed_ate,
                    "null_samples": list(snap.permutation.null_samples),
                    "p_two_sided": snap.permutation.p_two_sided,
                    "n_permutations": snap.permutation.n_permutations,
                }
            ),
            "candles": [
                {
                    "product_id": cs.product_id,
                    "product_name": cs.product_name,
                    "category": cs.category,
                    "candles": [
                        {
                            "bucket": c.bucket,
                            "open": c.open,
                            "high": c.high,
                            "low": c.low,
                            "close": c.close,
                            "volume": c.volume,
                        }
                        for c in cs.candles
                    ],
                    "total_volume": cs.total_volume,
                    "bucket_ticks": cs.bucket_ticks,
                }
                for cs in snap.candles
            ],
            "inflation": (
                None
                if snap.inflation is None
                else {
                    "cpi": [list(p) for p in snap.inflation.cpi],
                    "money_supply": [list(p) for p in snap.inflation.money_supply],
                    "n_samples": snap.inflation.n_samples,
                }
            ),
            "wealth": (
                None
                if snap.wealth is None
                else {
                    "lorenz_x": list(snap.wealth.lorenz_x),
                    "lorenz_y": list(snap.wealth.lorenz_y),
                    "gini": snap.wealth.gini,
                    "p10": snap.wealth.p10,
                    "p50": snap.wealth.p50,
                    "p90": snap.wealth.p90,
                    "p99": snap.wealth.p99,
                    "total_wealth": snap.wealth.total_wealth,
                    "n_agents": snap.wealth.n_agents,
                }
            ),
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

    # ── Learning (MAPPO) inspection + control ─────────────────────

    def _build_observation_for_agent(agent_idx: int) -> tuple[np.ndarray, list[int], list[int]]:
        """Build the (obs_dim,) feature vector for one live agent.

        Returns (feature_vector, neighbour_node_ids, sorted_neighbour_node_ids).
        Mirrors `_build_feature_vector` from the policy loader without
        creating a dependency cycle.
        """
        sim_local = app.state.penumbra.simulation
        if agent_idx < 0 or agent_idx >= len(sim_local.agents):
            return np.zeros(15, dtype=np.float32), [], []
        agent = sim_local.agents[agent_idx]
        obs = agent.observe(sim_local.arena, tick=sim_local.tick_counter)
        from penumbra_learning.env import (
            NEIGHBOURS_K,
            OBS_PER_NEIGHBOUR,
            PAD_VALUE,
        )

        neighbours = sorted(obs.neighbour_costs.keys())
        goals = set(obs.visible_goals)
        feats: list[float] = []
        for j in range(NEIGHBOURS_K):
            if j < len(neighbours):
                n = neighbours[j]
                cost = float(obs.neighbour_costs[n])
                is_goal = 1.0 if n in goals else 0.0
                feats.extend([cost, is_goal, is_goal])
            else:
                feats.extend([PAD_VALUE, PAD_VALUE, PAD_VALUE])
        del OBS_PER_NEIGHBOUR  # only imported for clarity
        return np.asarray(feats, dtype=np.float32), neighbours, neighbours

    @app.get("/learning/policy/{agent_id}")
    async def learning_policy(agent_id: int) -> dict[str, object]:
        """Inspect the actor's distribution for one agent at the current tick."""
        runtime = app.state.penumbra.mappo_runtime
        sim_local: Simulation = app.state.penumbra.simulation
        if runtime is None:
            return {
                "available": False,
                "reason": "MAPPO not loaded (set PENUMBRA_MAPPO_CHECKPOINT)",
            }
        if agent_id < 0 or agent_id >= len(sim_local.agents):
            raise HTTPException(status_code=404, detail=f"no agent {agent_id}")
        feats, neighbours, _ = _build_observation_for_agent(agent_id)
        agent_net = runtime.agent_net  # type: ignore[attr-defined]
        probs = agent_net.action_probabilities(feats, temperature=runtime.temperature)  # type: ignore[attr-defined]
        prob_vector = [float(p) for p in probs[0]]
        chosen = int(np.argmax(prob_vector))
        agent = sim_local.agents[agent_id]
        # Action labels: K neighbours + "stay" (last index).
        labels: list[str] = []
        for n in neighbours[: len(prob_vector) - 1]:
            labels.append(f"→ #{n}")
        while len(labels) < len(prob_vector) - 1:
            labels.append("—")
        labels.append("stay")
        return {
            "available": True,
            "agent_id": agent_id,
            "current_node": int(agent.position),
            "observation": [float(v) for v in feats],
            "neighbour_nodes": [int(n) for n in neighbours],
            "action_labels": labels,
            "action_probabilities": prob_vector,
            "chosen_action": chosen,
            "temperature": float(runtime.temperature),  # type: ignore[attr-defined]
            "deterministic": bool(runtime.deterministic),  # type: ignore[attr-defined]
            "enabled": bool(runtime.enabled),  # type: ignore[attr-defined]
        }

    @app.get("/learning/runtime")
    async def learning_runtime() -> dict[str, object]:
        runtime = app.state.penumbra.mappo_runtime
        if runtime is None:
            return {"available": False}
        return {
            "available": True,
            "temperature": float(runtime.temperature),  # type: ignore[attr-defined]
            "deterministic": bool(runtime.deterministic),  # type: ignore[attr-defined]
            "enabled": bool(runtime.enabled),  # type: ignore[attr-defined]
        }

    @app.post("/learning/temperature/{value}")
    async def set_temperature(value: float) -> dict[str, object]:
        runtime = app.state.penumbra.mappo_runtime
        if runtime is None:
            raise HTTPException(status_code=404, detail="MAPPO not loaded")
        if not 0.05 <= value <= 50.0:
            raise HTTPException(status_code=400, detail="temperature must be in [0.05, 50.0]")
        runtime.temperature = float(value)  # type: ignore[attr-defined]
        return {"temperature": runtime.temperature}  # type: ignore[attr-defined]

    @app.post("/learning/enabled/{enabled}")
    async def set_enabled(enabled: bool) -> dict[str, object]:
        runtime = app.state.penumbra.mappo_runtime
        if runtime is None:
            raise HTTPException(status_code=404, detail="MAPPO not loaded")
        runtime.enabled = bool(enabled)  # type: ignore[attr-defined]
        return {"enabled": runtime.enabled}  # type: ignore[attr-defined]

    @app.get("/learning/reward-weights")
    async def learning_reward_weights() -> dict[str, object]:
        from penumbra_learning.env import REWARD_WEIGHTS

        return {
            "available": True,
            "goal_reward": float(REWARD_WEIGHTS.goal_reward),
            "step_penalty": float(REWARD_WEIGHTS.step_penalty),
            "illegal_move_penalty": float(REWARD_WEIGHTS.illegal_move_penalty),
            "crowding_penalty": float(REWARD_WEIGHTS.crowding_penalty),
        }

    @app.post("/learning/reward-weights")
    async def learning_set_reward_weights(payload: dict[str, float]) -> dict[str, object]:
        from penumbra_learning.env import REWARD_WEIGHTS

        for key in ("goal_reward", "step_penalty", "illegal_move_penalty", "crowding_penalty"):
            if key in payload:
                setattr(REWARD_WEIGHTS, key, float(payload[key]))
        return {
            "goal_reward": float(REWARD_WEIGHTS.goal_reward),
            "step_penalty": float(REWARD_WEIGHTS.step_penalty),
            "illegal_move_penalty": float(REWARD_WEIGHTS.illegal_move_penalty),
            "crowding_penalty": float(REWARD_WEIGHTS.crowding_penalty),
        }

    @app.get("/learning/value-map")
    async def learning_value_map() -> dict[str, object]:
        """Per-agent V(s) for the live policy + observation entropy.

        For each LIVE agent, compute the critic's V(state) at its
        current global observation, and the actor's distribution
        entropy at its local observation. The dashboard overlays
        these on the world map so the user can see where the policy
        thinks the swarm should be.
        """
        runtime = app.state.penumbra.mappo_runtime
        sim_local: Simulation = app.state.penumbra.simulation
        if runtime is None:
            return {"available": False}
        agent_net = runtime.agent_net  # type: ignore[attr-defined]
        from penumbra_learning.env import (
            NEIGHBOURS_K,
            OBS_PER_NEIGHBOUR,
            PAD_VALUE,
        )

        feats_all: list[np.ndarray] = []
        for ag in sim_local.agents:
            obs = ag.observe(sim_local.arena, tick=sim_local.tick_counter)
            neighbours = sorted(obs.neighbour_costs.keys())
            goals = set(obs.visible_goals)
            f: list[float] = []
            for j in range(NEIGHBOURS_K):
                if j < len(neighbours):
                    n = neighbours[j]
                    cost = float(obs.neighbour_costs[n])
                    is_goal = 1.0 if n in goals else 0.0
                    f.extend([cost, is_goal, is_goal])
                else:
                    f.extend([PAD_VALUE, PAD_VALUE, PAD_VALUE])
            feats_all.append(np.asarray(f, dtype=np.float32))
        del OBS_PER_NEIGHBOUR
        feats_arr = np.stack(feats_all, axis=0)
        # Actor entropy per agent (uses live temperature).
        probs = agent_net.action_probabilities(feats_arr, temperature=runtime.temperature)  # type: ignore[attr-defined]
        # H(p) = -Σ p log p
        with np.errstate(divide="ignore", invalid="ignore"):
            entropies = -np.where(probs > 0, probs * np.log(probs), 0).sum(axis=1)
        # Centralised critic: pad/truncate to expected dimension.
        cfg = agent_net.config  # type: ignore[attr-defined]
        expected = int(cfg.obs_dim * cfg.n_agents)
        flat = feats_arr.reshape(-1).astype(np.float32, copy=False)
        if flat.size < expected:
            padded = np.full((expected,), PAD_VALUE, dtype=np.float32)
            padded[: flat.size] = flat
            flat = padded
        else:
            flat = flat[:expected]
        v_state = agent_net.value_estimate(flat)  # type: ignore[attr-defined]
        return {
            "available": True,
            "v_state": float(v_state),
            "per_agent": [
                {
                    "agent_id": int(i),
                    "node": int(sim_local.agents[i].position),
                    "entropy": float(entropies[i]),
                    "top_prob": float(np.max(probs[i])),
                }
                for i in range(len(sim_local.agents))
            ],
            "temperature": float(runtime.temperature),  # type: ignore[attr-defined]
        }

    @app.get("/learning/training/status")
    async def learning_training_status() -> dict[str, object]:
        trainer = app.state.penumbra.live_trainer
        if trainer is None:
            return {"available": False}
        return {
            "available": True,
            "enabled": bool(trainer.enabled),  # type: ignore[attr-defined]
            "iteration": int(trainer.iteration),  # type: ignore[attr-defined]
            "n_env_agents": int(trainer.n_env_agents),  # type: ignore[attr-defined]
            "rollout_length": int(trainer.rollout_length),  # type: ignore[attr-defined]
        }

    @app.post("/learning/training/start")
    async def learning_training_start() -> dict[str, object]:
        trainer = app.state.penumbra.live_trainer
        if trainer is None:
            raise HTTPException(status_code=404, detail="live trainer unavailable")
        trainer.start()  # type: ignore[attr-defined]
        return {"enabled": True, "iteration": int(trainer.iteration)}  # type: ignore[attr-defined]

    @app.post("/learning/training/stop")
    async def learning_training_stop() -> dict[str, object]:
        trainer = app.state.penumbra.live_trainer
        if trainer is None:
            raise HTTPException(status_code=404, detail="live trainer unavailable")
        trainer.stop()  # type: ignore[attr-defined]
        return {"enabled": False, "iteration": int(trainer.iteration)}  # type: ignore[attr-defined]

    @app.get("/learning/training/curves")
    async def learning_training_curves() -> dict[str, object]:
        trainer = app.state.penumbra.live_trainer
        if trainer is None or not getattr(trainer, "history", None):
            return {"available": False, "samples": []}
        samples = [
            {
                "iteration": s.iteration,
                "actor_loss": s.actor_loss,
                "critic_loss": s.critic_loss,
                "entropy": s.entropy,
                "kl": s.kl,
                "mean_reward": s.mean_reward,
            }
            for s in list(trainer.history)  # type: ignore[attr-defined]
        ]
        return {
            "available": True,
            "samples": samples,
            "enabled": bool(trainer.enabled),  # type: ignore[attr-defined]
            "iteration": int(trainer.iteration),  # type: ignore[attr-defined]
        }

    @app.get("/learning/action-histogram")
    async def action_histogram() -> dict[str, object]:
        """Distribution of actions chosen this tick by the live policy."""
        runtime = app.state.penumbra.mappo_runtime
        if runtime is None or not getattr(runtime, "last_actions", None):
            return {"available": False, "histogram": []}
        from collections import Counter

        counts = Counter(runtime.last_actions)  # type: ignore[attr-defined]
        # Build action labels: K neighbours + stay; -1 = random walk override.
        from penumbra_learning.env import NEIGHBOURS_K

        out = []
        for i in range(NEIGHBOURS_K + 1):
            label = "stay" if i == NEIGHBOURS_K else f"neigh {i}"
            out.append({"action": label, "count": int(counts.get(i, 0))})
        if -1 in counts:
            out.append({"action": "random", "count": int(counts[-1])})
        return {
            "available": True,
            "histogram": out,
            "n_agents": sum(c["count"] for c in out),
            "temperature": float(runtime.temperature),  # type: ignore[attr-defined]
            "enabled": bool(runtime.enabled),  # type: ignore[attr-defined]
        }

    # ── DP comparison: clean vs noised heatmap ────────────────────

    @app.get("/dp/compare")
    async def dp_compare() -> dict[str, object]:
        """Return the latest CLEAN density alongside the DP-noised one.

        The encrypted heatmap stores both the post-DP density (what's
        normally released) and the pre-DP one (only the local server
        sees this — production wouldn't expose it, but for the
        pedagogy we make the noise visible).
        """
        sample = app.state.penumbra.orchestrator.heatmap.latest
        if sample is None:
            return {"ready": False}
        return {
            "ready": True,
            "clean": list(sample.clean_density.tolist()),
            "noised": list(sample.density.tolist()),
            "epsilon_spent": float(sample.epsilon_spent_total),
            "dp_applied": bool(sample.noise_applied),
            "tick": int(sample.tick),
        }

    # ── Chain explorer extras: VRF leader, mempool, BLS, ZK ───────

    @app.get("/chain/vrf-leader")
    async def chain_vrf_leader() -> dict[str, object]:
        """Recent VRF leaders + the validator panel + current head seed.

        Returns:
          validators: [{index, bls_short, vrf_short, slashed}]
          recent: last 12 blocks' [{height, leader_index, leader_short}]
          next_seed: hex preview of the seed the NEXT election will use
        """
        node = app.state.penumbra.orchestrator.node
        validators = [
            {
                "index": i,
                "bls_short": v.bls_pubkey.hex()[:16],
                "vrf_short": format(int(v.vrf_pubkey), "x")[:16],
                "slashed": v.bls_pubkey in node.slashed_pubkeys,
            }
            for i, v in enumerate(node.validators)
        ]
        recent: list[dict[str, object]] = []
        for blk in node.chain[-12:]:
            proposer = blk.header.proposer_pubkey
            leader_idx = next(
                (i for i, v in enumerate(node.validators) if v.bls_pubkey == proposer),
                -1,
            )
            recent.append(
                {
                    "height": int(blk.header.height),
                    "leader_index": leader_idx,
                    "leader_short": proposer.hex()[:16],
                    "vrf_beta_short": blk.header.vrf_beta.hex()[:16],
                    "timestamp_ns": int(blk.header.timestamp_ns),
                }
            )
        next_seed = (node.head_hash + node.height.to_bytes(8, "big")).hex()[:32]
        return {
            "validators": validators,
            "recent": recent,
            "next_seed": next_seed,
            "active": [int(i) for i in node.active_indices],
            "current_height": int(node.height),
        }

    @app.get("/chain/mempool")
    async def chain_mempool() -> dict[str, object]:
        """Pending outcomes + pending slashings that the next block will pick up."""
        node = app.state.penumbra.orchestrator.node
        pending = node.mempool.peek()
        return {
            "n_outcomes": len(node.mempool),
            "outcomes": [
                {
                    "match_id": int(o.match_id),
                    "winner": int(o.winner_agent_id) if o.winner_agent_id is not None else None,
                    "winning_goal": int(o.winning_goal) if o.winning_goal is not None else None,
                    "started_tick": int(o.started_tick),
                    "end_tick": int(o.end_tick),
                    "end_reason": o.end_reason,
                }
                for o in pending[:32]
            ],
            "n_slashings": len(node.pending_slashings),
            "slashings": [
                {
                    "offender_short": s.evidence.offender_pubkey.hex()[:16],
                    "height": int(s.evidence.height),
                }
                for s in node.pending_slashings[:16]
            ],
        }

    @app.get("/chain/bls/{block_hash}")
    async def chain_bls_inspect(block_hash: str) -> dict[str, object]:
        """Show the BLS aggregate signature of a specific block + verify it.

        The frontend can also tamper the public input and submit it
        back to /chain/bls/verify to demonstrate that the aggregate
        signature binds to the block hash.
        """
        node = app.state.penumbra.orchestrator.node
        target: object | None = None
        for blk in node.chain:
            if blk.hash().hex() == block_hash:
                target = blk
                break
        if target is None:
            raise HTTPException(status_code=404, detail=f"no block with hash {block_hash}")
        # Verify the aggregate against the published pubkeys.
        from penumbra_chain.consensus import canonical_block_sign_payload
        from penumbra_crypto.bls import fast_aggregate_verify

        ok = False
        try:
            payload_bytes = canonical_block_sign_payload(
                target.hash(),  # type: ignore[attr-defined]
                target.header.height,  # type: ignore[attr-defined]
            )
            ok = fast_aggregate_verify(
                list(target.validator_pubkeys),  # type: ignore[attr-defined]
                payload_bytes,
                target.aggregate_signature,  # type: ignore[attr-defined]
            )
        except Exception:
            ok = False
        return {
            "block_hash": block_hash,
            "block_height": int(target.header.height),  # type: ignore[attr-defined]
            "n_signers": len(target.validator_pubkeys),  # type: ignore[attr-defined]
            "aggregate_short": target.aggregate_signature.hex()[:32],  # type: ignore[attr-defined]
            "signers": [
                p.hex()[:16]
                for p in target.validator_pubkeys  # type: ignore[attr-defined]
            ],
            "verified": ok,
        }

    _zk_cache: dict[str, object] = {}

    @app.get("/crypto/zk/legal-path")
    async def crypto_zk_verify() -> dict[str, object]:
        """Verify the shipped Groth16 legal-path proof.

        py_ecc Groth16 is slow (~15s for 3 verifies on M4). We cache
        the result so the dashboard hits the cold path once per server
        boot. The artifacts are static and the verifier is
        deterministic, so caching is safe.
        """
        if _zk_cache:
            return dict(_zk_cache)
        import json
        from pathlib import Path

        from penumbra_crypto.snark import load_proof, load_verifying_key, verify

        artifacts = Path(__file__).resolve().parents[3] / "circuits" / "artifacts"
        vk_path = artifacts / "legal_path_vk.json"
        proof_path = artifacts / "legal_path_proof.json"
        public_path = artifacts / "legal_path_public.json"
        if not all(p.is_file() for p in (vk_path, proof_path, public_path)):
            return {"available": False, "reason": "circuits/artifacts missing"}

        def _run() -> dict[str, object]:
            vk = load_verifying_key(json.loads(vk_path.read_text()))
            proof = load_proof(json.loads(proof_path.read_text()))
            public = [int(s) for s in json.loads(public_path.read_text())]
            honest_ok = verify(vk, proof, public)
            tampered = [*public[:-1], (public[-1] + 1) % 4]
            tampered_ok = verify(vk, proof, tampered)
            adj_tampered = list(public)
            adj_tampered[3] = 1 - adj_tampered[3]
            adj_ok = verify(vk, proof, adj_tampered)
            return {
                "available": True,
                "circuit": "legal_path 2-hop",
                "n_public_inputs": len(public),
                "honest": {"inputs": public, "verified": bool(honest_ok)},
                "tamper_goal": {"inputs": tampered, "verified": bool(tampered_ok)},
                "tamper_adjacency": {"inputs": adj_tampered, "verified": bool(adj_ok)},
            }

        result = await asyncio.to_thread(_run)
        _zk_cache.update(result)
        return dict(_zk_cache)

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


def _build_simulation_with_optional_mappo() -> tuple[Simulation, object | None]:
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
        return load_simulation(Path(snapshot), policy_factory=factory), None  # type: ignore[arg-type]

    config = SimulationConfig()
    seeded = bootstrap()
    if not checkpoint:
        return Simulation.build(config, seeded), None
    try:
        from penumbra_learning.policy_loader import (
            mappo_batch_policy,
        )

        batch_policy, runtime = mappo_batch_policy(checkpoint, n_agents=config.n_agents)
        sim = Simulation.build(config, seeded, batch_policy=batch_policy)
        return sim, runtime
    except ImportError:
        logger.warning("penumbra_learning not importable; falling back to random walk")
        return Simulation.build(config, seeded), None


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
