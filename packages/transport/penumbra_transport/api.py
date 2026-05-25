"""FastAPI application factory.

Concept taught: FastAPI's `lifespan` context manager owns the background
tick loop. When the app starts, the loop starts; when uvicorn issues a
shutdown signal, the lifespan exits and the loop is cancelled cleanly.
No global state, no atexit hooks.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from fastapi import Body, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
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
    second_mappo: object | None = None  # second checkpoint for A/B compare


def build_app(
    simulation: Simulation | None = None,
    *,
    tick_hz: float | None = None,
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

        effective_hz = (
            tick_hz if tick_hz is not None else float(os.environ.get("PENUMBRA_TICK_HZ", "2.0"))
        )
        loop = TickLoop(sim, push, tick_hz=effective_hz)
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

        # Warm the ZK verifier cache in the background so the first
        # /crypto/zk/legal-path call doesn't pay the 15s py_ecc cold
        # path. Fire-and-forget — if it fails (artifacts missing) the
        # endpoint will report it normally.
        async def _warm_zk_cache() -> None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(_zk_verify_sync)

        app.state.zk_warmup_task = asyncio.create_task(_warm_zk_cache(), name="penumbra-zk-warmup")

        # Same idea for the snark-forgery demo (3 verifies × ~5s).
        async def _warm_forge_cache() -> None:
            with contextlib.suppress(Exception):
                from penumbra_attacker.attacks import snark_forgery

                fr = await asyncio.to_thread(snark_forgery.demo)
                _snark_forge_cache.update(
                    {
                        "available": True,
                        "algorithm": "Groth16 (legal_path circuit)",
                        "honest_proof_accepted": bool(fr.honest_proof_accepted),
                        "random_forge_accepted": bool(fr.random_forge_accepted),
                        "replay_with_tampered_inputs_accepted": bool(
                            fr.replay_with_tampered_inputs_accepted
                        ),
                    }
                )

        app.state.forge_warmup_task = asyncio.create_task(
            _warm_forge_cache(), name="penumbra-forge-warmup"
        )

        live_trainer: object | None = None
        if mappo_runtime is not None:
            try:
                from penumbra_learning.live_trainer import build_live_trainer

                live_trainer = build_live_trainer(
                    mappo_runtime.agent_net,  # type: ignore[attr-defined]
                    orchestrator=orchestrator,
                )
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
        # Save-resume: surface (but do NOT auto-load) a resumable
        # session if one is on disk. The player chooses via the banner.
        try:
            import os as _os
            from pathlib import Path as _Path

            from penumbra_operator.save_resume import load_active

            _override = getattr(app.state, "operator_save_dir", None)
            _env_dir = _os.environ.get("PENUMBRA_OPERATOR_SAVE_DIR")
            _save_dir: object | None = None
            if _override is not None:
                _save_dir = _Path(str(_override))
            elif _env_dir:
                _save_dir = _Path(_env_dir)
            _resumable = load_active(_save_dir)  # type: ignore[arg-type]
            if _resumable is not None:
                logger.info(
                    "resumable session found: %s (scenario=%s, saved_at_tick=%d)",
                    _resumable.session_id,
                    _resumable.scenario_id,
                    _resumable.saved_at_tick,
                )
        except Exception:  # pragma: no cover - defensive
            logger.exception("failed to probe for resumable operator session")
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
    async def step(
        payload: dict[str, object] = Body(default_factory=dict),
    ) -> dict[str, object]:
        """Advance the simulation by ``n`` ticks (default 1) regardless of pause.

        Body: ``{"n": int}`` with ``n`` in ``[1, 100]``. Empty body or
        omitted ``n`` defaults to 1 for backward compatibility with the
        original no-body call.
        """
        sim: Simulation = app.state.penumbra.simulation
        raw_n = payload.get("n", 1) if isinstance(payload, dict) else 1
        try:
            n = int(raw_n)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid n: {raw_n!r}") from exc
        if n < 1 or n > 100:
            raise HTTPException(status_code=400, detail="n must be in [1, 100]")
        previous_tick = sim.tick_counter
        for _ in range(n):
            sim.step_once()
        return {
            "previous_tick": previous_tick,
            "new_tick": sim.tick_counter,
            "tick": sim.tick_counter,
        }

    @app.post("/control/time-warp/{multiplier}")
    async def set_time_warp(multiplier: int) -> dict[str, int]:
        if multiplier < 1 or multiplier > 100:
            raise HTTPException(status_code=400, detail="time_warp must be in [1, 100]")
        sim: Simulation = app.state.penumbra.simulation
        sim.config.time_warp = multiplier
        return {"time_warp": multiplier}

    # Allowed tick rates surfaced to the dashboard speed widget.
    # Picking the live value at boot from PENUMBRA_TICK_HZ lets a power
    # user run at, say, 0.1 Hz from the env without the UI rejecting it,
    # but the UI buttons stick to the curated ladder.
    _allowed_tick_hz: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0, 10.0)

    @app.get("/control/tick_hz")
    async def get_tick_hz() -> dict[str, object]:
        """Current tick rate + the curated ladder the UI exposes as buttons."""
        loop_ref: TickLoop = app.state.penumbra.loop
        return {
            "tick_hz": float(loop_ref.tick_hz),
            "allowed": list(_allowed_tick_hz),
        }

    @app.post("/control/tick_hz")
    async def post_tick_hz(payload: dict[str, float]) -> dict[str, object]:
        """Live-update the simulation tick rate.

        Body: ``{"tick_hz": <float>}``. The value must be one of the
        curated rates exposed by ``GET /control/tick_hz`` to avoid
        pathological values (e.g., 1000 Hz, which would saturate the
        thread pool) sneaking in from the browser.
        """
        raw = payload.get("tick_hz")
        if raw is None:
            raise HTTPException(status_code=400, detail="missing 'tick_hz' field")
        try:
            hz = float(raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid tick_hz: {raw!r}") from exc
        # Allow a tiny tolerance so 2 vs 2.0000001 doesn't 400.
        if not any(abs(hz - allowed) < 1e-6 for allowed in _allowed_tick_hz):
            raise HTTPException(
                status_code=400,
                detail=f"tick_hz must be one of {list(_allowed_tick_hz)}",
            )
        loop_ref: TickLoop = app.state.penumbra.loop
        loop_ref.set_tick_hz(hz)
        return {"tick_hz": float(loop_ref.tick_hz), "allowed": list(_allowed_tick_hz)}

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

    @app.get("/events/recent")
    async def events_recent(limit: int = 50) -> dict[str, object]:
        """Phase 6a — most recent cross-pillar events from the bus."""
        bus = app.state.penumbra.orchestrator.event_bus
        limit = max(1, min(int(limit), 500))
        events = bus.recent(limit=limit)
        return {
            "events": [{"kind": e.kind, "tick": e.tick, "payload": e.payload} for e in events],
        }

    @app.get("/security/blocked-agents")
    async def security_blocked_agents() -> dict[str, object]:
        """Phase 6a Tier 2 — live blocked-agent list + history counter.

        Returns the agents currently in an active security block, the
        lifetime count of block events fired (history_count), and the
        Market's gated-trade counter so the dashboard can show "this
        many trade attempts were stopped by an active block".
        """
        orchestrator = app.state.penumbra.orchestrator
        market = orchestrator.market
        pending = orchestrator._pending_unblocks  # type: ignore[attr-defined]
        blocked = [
            {
                "agent_id": int(agent_id),
                "reason": "signing_rejected",
                "until_tick": int(until_tick),
            }
            for agent_id, until_tick in pending.items()
        ]
        blocked.sort(key=lambda row: row["agent_id"])
        return {
            "blocked": blocked,
            "history_count": int(orchestrator._blocked_history_count),  # type: ignore[attr-defined]
            "blocked_trade_attempts": (
                int(market.blocked_trade_attempts) if market is not None else 0
            ),
        }

    @app.get("/events/stats")
    async def events_stats() -> dict[str, object]:
        """Phase 6a — bus stats for the EventBus tile."""
        return app.state.penumbra.orchestrator.event_bus.stats()

    @app.get("/events/policy-improvements")
    async def events_policy_improvements(limit: int = 50) -> dict[str, object]:
        """Phase 6a Tier 4 — history of policy.improved events.

        Emitted by the orchestrator's ``ml.policy.updated`` handler
        whenever the live MAPPO trainer's ``mean_reward`` jumps above
        1.5x the EMA baseline. Surfaces "live training is converging"
        on the Bench leaderboard tile.
        """
        orch = app.state.penumbra.orchestrator
        history = list(getattr(orch, "_policy_improvements", []))
        limit = max(1, min(int(limit), 500))
        out = [{"kind": e.kind, "tick": e.tick, "payload": e.payload} for e in history[-limit:]]
        return {
            "available": True,
            "n_total": len(history),
            "events": out,
            "baseline_reward": (
                float(orch._policy_reward_baseline)  # type: ignore[arg-type]
                if getattr(orch, "_policy_reward_baseline", None) is not None
                else None
            ),
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

    @app.get("/coach/stories")
    async def coach_stories() -> dict[str, object]:
        """Phase 5 Tier 5 — story-mode lesson index for the StoryMode tile.

        Static manifest of the 8 cross-pillar narrative lessons shipped under
        `packages/shell_coach/lessons/`. The frontend filters this list by
        `difficulty` and `pillars_touched`; each entry includes the
        `psh lesson <id>` command the operator-mode terminal will run.
        """
        stories: list[dict[str, object]] = [
            {
                "id": "story_bullwhip_leak",
                "title": "The bullwhip leak",
                "difficulty": "hard",
                "pillars": ["logistics", "statistics", "neural_networks", "rl", "crypto"],
                "prereqs": [],
                "command": "psh lesson story_bullwhip_leak",
                "blurb": "Supplier observes demand -> carrier fingerprint -> MI on MAPPO -> poison.",
            },
            {
                "id": "story_honest_validator",
                "title": "The honest validator",
                "difficulty": "hard",
                "pillars": ["crypto", "neural_networks", "statistics", "chain"],
                "prereqs": ["story_bullwhip_leak"],
                "command": "psh lesson story_honest_validator",
                "blurb": "BLS + Krum + DP + k-anonymity composed; measure each defense.",
            },
            {
                "id": "story_replay_chain",
                "title": "Replay -> equivocation -> SNARK forge",
                "difficulty": "medium",
                "pillars": ["crypto", "chain"],
                "prereqs": [],
                "command": "psh lesson story_replay_chain",
                "blurb": "Three chained attacks, three defense closures fire.",
            },
            {
                "id": "story_dp_starvation",
                "title": "DP starvation",
                "difficulty": "medium",
                "pillars": ["statistics", "crypto"],
                "prereqs": [],
                "command": "psh lesson story_dp_starvation",
                "blurb": "Burn the eps budget with QID queries -> re-identify.",
            },
            {
                "id": "story_fl_backdoor",
                "title": "FL backdoor -- Krum vs FedAvg",
                "difficulty": "medium",
                "pillars": ["neural_networks", "rl", "crypto"],
                "prereqs": [],
                "command": "psh lesson story_fl_backdoor",
                "blurb": "One malicious client; defense drops attack success rate.",
            },
            {
                "id": "story_carrier_extortion",
                "title": "Carrier extortion",
                "difficulty": "medium",
                "pillars": ["logistics", "rl", "statistics"],
                "prereqs": [],
                "command": "psh lesson story_carrier_extortion",
                "blurb": "Dispatch fingerprint -> re-id -> targeted reward poisoning.",
            },
            {
                "id": "story_mix_net_defense",
                "title": "Mix-net defense -- Loopix",
                "difficulty": "medium",
                "pillars": ["crypto", "logistics"],
                "prereqs": [],
                "command": "psh lesson story_mix_net_defense",
                "blurb": "Naive routing vs 3-hop mix-net; attacker accuracy drops.",
            },
            {
                "id": "story_ctf_speedrun",
                "title": "CTF speedrun",
                "difficulty": "easy",
                "pillars": ["crypto", "statistics", "chain"],
                "prereqs": ["story_dp_starvation", "story_replay_chain"],
                "command": "psh lesson story_ctf_speedrun",
                "blurb": "Operator-mode playthrough of 3 CTF challenges; beat your time.",
            },
        ]
        all_pillars = sorted({p for s in stories for p in s["pillars"]})  # type: ignore[union-attr]
        return {
            "available": True,
            "stories": stories,
            "pillars": all_pillars,
            "difficulties": ["easy", "medium", "hard"],
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
                {"label": "snark forgery", "command": "pna snark-forge"},
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
        """Snapshot of the DP accountant for the encrypted-heatmap mechanism.

        Phase 6a Tier 3 — payload extended with ``degraded`` +
        ``degradation_reason`` so the dashboard can surface the
        DP-fallback banner whenever the pipeline has been switched
        into degraded mode by the orchestrator event handler.
        """
        orchestrator = app.state.penumbra.orchestrator
        mechanism = orchestrator.heatmap.dp_mechanism
        pipeline = orchestrator.pipeline
        degraded = bool(getattr(pipeline, "_dp_degraded", False))
        degradation_reason = getattr(pipeline, "_dp_degradation_reason", None)
        if mechanism is None:
            return {
                "enabled": False,
                "degraded": degraded,
                "degradation_reason": degradation_reason,
            }
        budget = mechanism.budget
        return {
            "enabled": True,
            "epsilon_total": budget.epsilon,
            "epsilon_spent": budget.epsilon_spent,
            "epsilon_remaining": budget.remaining_epsilon,
            "delta_total": budget.delta,
            "delta_spent": budget.delta_spent,
            "degraded": degraded,
            "degradation_reason": degradation_reason,
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
            "logistics_dispatch_bonus": float(REWARD_WEIGHTS.logistics_dispatch_bonus),
            "logistics_dispatch_penalty": float(REWARD_WEIGHTS.logistics_dispatch_penalty),
            "fill_rate_bonus": float(REWARD_WEIGHTS.fill_rate_bonus),
        }

    @app.post("/learning/reward-weights")
    async def learning_set_reward_weights(payload: dict[str, float]) -> dict[str, object]:
        from penumbra_learning.env import REWARD_WEIGHTS

        for key in (
            "goal_reward",
            "step_penalty",
            "illegal_move_penalty",
            "crowding_penalty",
            "logistics_dispatch_bonus",
            "logistics_dispatch_penalty",
            "fill_rate_bonus",
        ):
            if key in payload:
                setattr(REWARD_WEIGHTS, key, float(payload[key]))
        return {
            "goal_reward": float(REWARD_WEIGHTS.goal_reward),
            "step_penalty": float(REWARD_WEIGHTS.step_penalty),
            "illegal_move_penalty": float(REWARD_WEIGHTS.illegal_move_penalty),
            "crowding_penalty": float(REWARD_WEIGHTS.crowding_penalty),
            "logistics_dispatch_bonus": float(REWARD_WEIGHTS.logistics_dispatch_bonus),
            "logistics_dispatch_penalty": float(REWARD_WEIGHTS.logistics_dispatch_penalty),
            "fill_rate_bonus": float(REWARD_WEIGHTS.fill_rate_bonus),
        }

    @app.post("/learning/reward-weights/logistics")
    async def learning_set_logistics_reward_weights(
        payload: dict[str, float],
    ) -> dict[str, object]:
        """Update the Tier-4 logistics reward components live.

        Accepts any subset of {dispatch_bonus, dispatch_penalty,
        fill_rate_bonus} and writes through to the shared
        REWARD_WEIGHTS singleton so the next training iteration
        picks the new values up.
        """
        from penumbra_learning.env import REWARD_WEIGHTS

        mapping = {
            "dispatch_bonus": "logistics_dispatch_bonus",
            "dispatch_penalty": "logistics_dispatch_penalty",
            "fill_rate_bonus": "fill_rate_bonus",
            "logistics_dispatch_bonus": "logistics_dispatch_bonus",
            "logistics_dispatch_penalty": "logistics_dispatch_penalty",
        }
        for key, attr in mapping.items():
            if key in payload:
                setattr(REWARD_WEIGHTS, attr, float(payload[key]))
        return {
            "available": True,
            "logistics_dispatch_bonus": float(REWARD_WEIGHTS.logistics_dispatch_bonus),
            "logistics_dispatch_penalty": float(REWARD_WEIGHTS.logistics_dispatch_penalty),
            "fill_rate_bonus": float(REWARD_WEIGHTS.fill_rate_bonus),
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

    @app.get("/learning/carrier-reward-stream")
    async def learning_carrier_reward_stream(limit: int = 100) -> dict[str, object]:
        """Phase 6a Tier 4 — last N real-carrier fulfilment rewards.

        Streams the orchestrator's ``LogisticsMempool.recent_carrier_rewards``
        deque, one entry per real (non-phantom) order fulfilment. Each
        entry carries the carrier agent_id, the order reward, and the
        ``last_fulfilment_tick`` snapshot so the dashboard can scale the
        sparkline against the sim clock.
        """
        orch = app.state.penumbra.orchestrator
        mempool = orch.logistics_mempool
        if mempool is None:
            return {"available": False, "rewards": []}
        limit = max(1, min(int(limit), 500))
        pairs = list(mempool.recent_carrier_rewards)[-limit:]
        last_tick = int(getattr(mempool, "last_fulfilment_tick", -1))
        rewards = [
            {"agent_id": int(aid), "reward": float(rwd), "tick": last_tick} for aid, rwd in pairs
        ]
        # Per-agent aggregates: total + count, sorted by total descending.
        per_agent_totals: dict[int, float] = {}
        per_agent_counts: dict[int, int] = {}
        for aid, rwd in pairs:
            per_agent_totals[int(aid)] = per_agent_totals.get(int(aid), 0.0) + float(rwd)
            per_agent_counts[int(aid)] = per_agent_counts.get(int(aid), 0) + 1
        per_agent = sorted(
            (
                {
                    "agent_id": aid,
                    "total_reward": tot,
                    "count": per_agent_counts[aid],
                }
                for aid, tot in per_agent_totals.items()
            ),
            key=lambda row: (-row["total_reward"], row["agent_id"]),
        )
        return {
            "available": True,
            "rewards": rewards,
            "per_agent": per_agent,
            "total_carrier_fulfilments": int(getattr(mempool, "total_carrier_fulfilments", 0)),
            "last_fulfilment_tick": last_tick,
        }

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
    _multiplier_cache: dict[str, object] = {}
    _snark_forge_cache: dict[str, object] = {}

    def _zk_verify_sync() -> dict[str, object]:
        """Pure-sync ZK verifier — also used by lifespan warm-up."""
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
        vk = load_verifying_key(json.loads(vk_path.read_text()))
        proof = load_proof(json.loads(proof_path.read_text()))
        public = [int(s) for s in json.loads(public_path.read_text())]
        honest_ok = verify(vk, proof, public)
        tampered = [*public[:-1], (public[-1] + 1) % 4]
        tampered_ok = verify(vk, proof, tampered)
        adj_tampered = list(public)
        adj_tampered[3] = 1 - adj_tampered[3]
        adj_ok = verify(vk, proof, adj_tampered)
        result: dict[str, object] = {
            "available": True,
            "circuit": "legal_path 2-hop",
            "n_public_inputs": len(public),
            "honest": {"inputs": public, "verified": bool(honest_ok)},
            "tamper_goal": {"inputs": tampered, "verified": bool(tampered_ok)},
            "tamper_adjacency": {"inputs": adj_tampered, "verified": bool(adj_ok)},
        }
        _zk_cache.update(result)
        return dict(_zk_cache)

    @app.get("/crypto/zk/legal-path")
    async def crypto_zk_verify() -> dict[str, object]:
        """Verify the shipped Groth16 legal-path proof.

        py_ecc Groth16 is slow (~15s for 3 verifies on M4); the cache
        is warmed at server startup, so this endpoint is essentially
        instant for the dashboard.
        """
        return await asyncio.to_thread(_zk_verify_sync)

    @app.get("/crypto/pedersen/demo")
    async def crypto_pedersen_demo(message: int = 0) -> dict[str, object]:
        """Commit to a value + verify; also show the homomorphic add property.

        Pedersen commitments are HIDING (blinding factor makes the
        commitment value uniformly random) and BINDING (changing the
        message without changing the commitment requires breaking
        discrete log). They're additively homomorphic:
            C(m1, r1) * C(m2, r2) = C(m1+m2, r1+r2).
        """
        import secrets as pysecrets

        from penumbra_crypto.educational import pedersen

        if message <= 0:
            message = int.from_bytes(pysecrets.token_bytes(4), "big") % 10**6 + 1
        msg_b = pysecrets.randbelow(10**6) + 1
        c_a, open_a = pedersen.commit(message)
        c_b, open_b = pedersen.commit(msg_b)
        honest_ok = pedersen.verify(c_a, open_a)
        wrong_open = type(open_a)(message=message + 1, blinding=open_a.blinding)
        tampered_ok = pedersen.verify(c_a, wrong_open)
        # Homomorphic add: c_a · c_b should equal a commitment to (a + b)
        # with blinding (r_a + r_b).
        p_mod, q_mod, _g, _h = pedersen.group_params()
        c_sum_val = (c_a.value * c_b.value) % p_mod
        combined_open = type(open_a)(
            message=(open_a.message + open_b.message) % q_mod,
            blinding=(open_a.blinding + open_b.blinding) % q_mod,
        )
        c_sum = type(c_a)(value=c_sum_val)
        homo_ok = pedersen.verify(c_sum, combined_open)
        return {
            "available": True,
            "algorithm": "Pedersen commitment over Schnorr group (RFC 3526 MODP-14)",
            "message_a": int(message),
            "message_b": int(msg_b),
            "commitment_a_short": format(c_a.value, "x")[:32],
            "commitment_b_short": format(c_b.value, "x")[:32],
            "commitment_sum_short": format(c_sum_val, "x")[:32],
            "honest_verifies": bool(honest_ok),
            "tampered_message_verifies": bool(tampered_ok),
            "homomorphic_add_verifies": bool(homo_ok),
        }

    @app.get("/crypto/beaver/demo")
    async def crypto_beaver_demo(n_parties: int = 3) -> dict[str, object]:
        """Beaver triple → secret multiplication via additive shares.

        Each party holds an additive share of x, y, and (a, b, c =
        a*b). They locally compute d = x - a, e = y - b, open d + e,
        then locally output z = c + d·b + e·a + d·e. Sum of z shares
        equals x·y, but no party ever learned x or y in the clear.
        """
        import secrets as pysecrets

        from penumbra_crypto.educational import beaver

        n_parties = max(2, min(int(n_parties), 8))
        x = pysecrets.randbelow(10**6) + 1
        y = pysecrets.randbelow(10**6) + 1
        x_shares = beaver._additive_shares(x, n_parties)
        y_shares = beaver._additive_shares(y, n_parties)
        triple = beaver.generate_triple(n_parties)
        z_shares = beaver.beaver_multiply(x_shares, y_shares, triple)
        reconstructed = beaver.reconstruct_sum(z_shares)
        expected = x * y
        from penumbra_crypto.educational.beaver import _PRIME

        return {
            "available": True,
            "algorithm": "Beaver triples (trusted-dealer additive sharing)",
            "n_parties": n_parties,
            "x": int(x),
            "y": int(y),
            "x_shares": [format(int(s), "x")[:16] for s in x_shares],
            "y_shares": [format(int(s), "x")[:16] for s in y_shares],
            "z_shares": [format(int(s), "x")[:16] for s in z_shares],
            "expected_product": int(expected),
            "reconstructed": int(reconstructed),
            "matches_modulo_p": bool(reconstructed == expected % _PRIME),
        }

    @app.get("/crypto/schnorr/demo")
    async def crypto_schnorr_demo() -> dict[str, object]:
        """Schnorr Σ-protocol + Fiat-Shamir: prove knowledge of x s.t. y = g^x."""
        from penumbra_crypto.educational import schnorr

        x, statement = schnorr.keygen()
        proof = schnorr.prove(x, statement, context=b"penumbra-dashboard-demo")
        honest_ok = schnorr.verify(statement, proof, context=b"penumbra-dashboard-demo")
        # Wrong context — verifier recomputes the challenge and rejects.
        wrong_context_ok = schnorr.verify(statement, proof, context=b"different-context")
        # Tampered response — flip a bit of s.
        from dataclasses import replace

        tampered_proof = replace(proof, s=(proof.s ^ 1))
        tampered_ok = schnorr.verify(statement, tampered_proof, context=b"penumbra-dashboard-demo")
        return {
            "available": True,
            "algorithm": "Schnorr Σ-protocol with Fiat-Shamir (RFC 3526 MODP-14)",
            "statement_y_short": format(statement.y, "x")[:32],
            "proof_t_short": format(proof.t, "x")[:32],
            "proof_s_short": format(proof.s, "x")[:24],
            "proof_c_short": format(proof.c, "x")[:24],
            "honest_verifies": bool(honest_ok),
            "wrong_context_verifies": bool(wrong_context_ok),
            "tampered_response_verifies": bool(tampered_ok),
        }

    @app.get("/crypto/zk/multiplier")
    async def crypto_zk_multiplier() -> dict[str, object]:
        """Verify the shipped multiplier circom proof (a × b = c).

        Pedagogically simpler than legal_path: a circom circuit with
        one constraint `a * b === c`. The shipped artifacts have
        c = 15 (e.g. a=3, b=5). Tampering c rejects.
        """
        if _multiplier_cache:
            return dict(_multiplier_cache)

        def _run() -> dict[str, object]:
            import json
            from pathlib import Path

            from penumbra_crypto.snark import load_proof, load_verifying_key, verify

            artifacts = Path(__file__).resolve().parents[3] / "circuits" / "artifacts"
            vk_path = artifacts / "vk.json"
            proof_path = artifacts / "proof.json"
            public_path = artifacts / "public.json"
            if not all(p.is_file() for p in (vk_path, proof_path, public_path)):
                return {"available": False, "reason": "multiplier artifacts missing"}
            vk = load_verifying_key(json.loads(vk_path.read_text()))
            proof = load_proof(json.loads(proof_path.read_text()))
            public = [int(s) for s in json.loads(public_path.read_text())]
            honest_ok = verify(vk, proof, public)
            tampered = [(public[0] + 1)]
            tampered_ok = verify(vk, proof, tampered)
            return {
                "available": True,
                "circuit": "multiplier (a * b === c)",
                "n_public_inputs": len(public),
                "honest": {"inputs": public, "verified": bool(honest_ok)},
                "tamper_output": {"inputs": tampered, "verified": bool(tampered_ok)},
            }

        result = await asyncio.to_thread(_run)
        if result.get("available"):
            _multiplier_cache.update(result)
        return result

    @app.get("/crypto/snark-forge/demo")
    async def crypto_snark_forge_demo() -> dict[str, object]:
        """Run the snark-forgery demo: honest accepts, two forgeries reject.

        Cached after first run (three Groth16 verifies on M4 ~ 15s).
        """
        if _snark_forge_cache:
            return dict(_snark_forge_cache)
        from penumbra_attacker.attacks import snark_forgery

        result = await asyncio.to_thread(snark_forgery.demo)
        payload: dict[str, object] = {
            "available": True,
            "algorithm": "Groth16 (legal_path circuit)",
            "honest_proof_accepted": bool(result.honest_proof_accepted),
            "random_forge_accepted": bool(result.random_forge_accepted),
            "replay_with_tampered_inputs_accepted": bool(
                result.replay_with_tampered_inputs_accepted
            ),
        }
        _snark_forge_cache.update(payload)
        return dict(_snark_forge_cache)

    @app.get("/crypto/vdf/demo")
    async def crypto_vdf_demo(delay: int = 50000) -> dict[str, object]:
        """Run a Wesolowski VDF round + verify + show timing.

        Delay defaults to 50k squarings (~50ms on M4). The point: VDF
        compute time scales LINEARLY (no parallelism speedup); verify
        is O(log delay). The asymmetry is what makes it useful for
        unbiasable randomness — proposers can't pre-compute the
        output significantly faster than wall-clock time.
        """
        import secrets
        import time

        from penumbra_crypto import vdf

        delay = max(1000, min(int(delay), 1_000_000))
        x = int.from_bytes(secrets.token_bytes(8), "big") % 10**18 + 1
        t0 = time.perf_counter()
        evaluation = await asyncio.to_thread(vdf.prove, x, delay)
        compute_ms = (time.perf_counter() - t0) * 1000
        t1 = time.perf_counter()
        honest_ok = vdf.verify(evaluation)
        verify_ms = (time.perf_counter() - t1) * 1000
        # Tamper: flip a bit of y and verify should reject.
        tampered = vdf.VDFEvaluation(
            x=evaluation.x,
            y=evaluation.y ^ 1,
            proof=evaluation.proof,
            delay=evaluation.delay,
        )
        tampered_ok = vdf.verify(tampered)
        return {
            "available": True,
            "algorithm": "Wesolowski VDF",
            "delay": delay,
            "x_short": format(evaluation.x, "x")[:24],
            "y_short": format(evaluation.y, "x")[:24],
            "proof_short": format(evaluation.proof, "x")[:24],
            "compute_ms": compute_ms,
            "verify_ms": verify_ms,
            "compute_to_verify_ratio": compute_ms / max(verify_ms, 1e-6),
            "honest_verifies": bool(honest_ok),
            "tampered_verifies": bool(tampered_ok),
        }

    @app.get("/crypto/stark/demo")
    async def crypto_stark_demo() -> dict[str, object]:
        """Educational FRI-STARK proof + verify + tamper rejections.

        Ships a transparent (no trusted setup) low-degree test for a
        degree-7 polynomial codeword, alongside two negative cases:
        flipped evaluation and flipped commitment. Mirrors the snark
        forgery panel for the verifier-only pattern.
        """
        from penumbra_crypto import stark as _stark

        return await asyncio.to_thread(_stark.demo)

    @app.get("/crypto/dilithium/inspect/{agent_id}")
    async def crypto_dilithium_inspect(agent_id: int) -> dict[str, object]:
        """Inspect a Dilithium agent signature for a sample message.

        Penumbra signs every agent move with Dilithium under the hood;
        here we expose ONE sign+verify + tampered-message rejection
        for any agent in the live keystore.
        """
        keystore = app.state.penumbra.orchestrator.keystore
        if agent_id < 0 or agent_id >= len(keystore.keypairs):
            raise HTTPException(status_code=404, detail=f"no agent {agent_id}")
        from penumbra_crypto.pq import sign, verify

        kp = keystore.keypairs[agent_id]
        message = b"penumbra-sample-message-for-inspection"
        sig = sign(kp.secret_key, message)
        honest_ok = verify(kp.public_key, message, sig)
        tampered_ok = verify(kp.public_key, message + b"!", sig)
        return {
            "available": True,
            "algorithm": "ML-DSA-65 (Dilithium-3)",
            "agent_id": int(agent_id),
            "public_key_size": len(kp.public_key),
            "secret_key_size": len(kp.secret_key),
            "signature_size": len(sig),
            "message_size": len(message),
            "public_key_short": kp.public_key.hex()[:32],
            "signature_short": sig.hex()[:48],
            "honest_verifies": bool(honest_ok),
            "tampered_verifies": bool(tampered_ok),
        }

    @app.get("/crypto/shamir/demo")
    async def crypto_shamir_demo(n: int = 5, t: int = 3, secret: int = 0) -> dict[str, object]:
        """Split a secret with Shamir (n, t) and reconstruct from various subsets.

        Pedagogically: any t shares recover the secret; any t-1 shares
        recover NOTHING (information-theoretic guarantee). We verify
        both: reconstruct from t-of-n succeeds; reconstruct from
        (t-1)-of-n returns garbage.
        """
        import secrets as pysecrets

        from penumbra_crypto.educational import shamir

        n = max(2, min(int(n), 12))
        t = max(2, min(int(t), n))
        if secret <= 0:
            secret = int.from_bytes(pysecrets.token_bytes(8), "big") % 10**12 + 1
        shares = shamir.split(secret, n=n, t=t)
        # Reconstruct from a t-subset.
        ok_recovered = shamir.reconstruct(shares[:t])
        # And from a (t-1) subset — should NOT match (still returns a value but it's noise).
        noise_recovered = shamir.reconstruct(shares[: t - 1]) if t >= 2 else -1
        return {
            "available": True,
            "algorithm": f"Shamir (n={n}, t={t})",
            "secret": int(secret),
            "n_shares": n,
            "threshold": t,
            "shares": [{"x": int(s.x), "y_short": format(int(s.y), "x")[:24]} for s in shares],
            "recovered_from_t": int(ok_recovered),
            "recovered_matches": bool(ok_recovered == secret),
            "recovered_from_t_minus_1": int(noise_recovered),
            "leaks_at_t_minus_1": bool(noise_recovered == secret),
        }

    @app.get("/crypto/tfhe/demo")
    async def crypto_tfhe_demo() -> dict[str, object]:
        """Show LWE encryption + a single homomorphic NOT gate.

        Pedagogical educational TFHE (LWE-based bit encryption). We
        encrypt two bits, NOT one of them, decrypt both — and the
        NOTted bit matches the expected boolean negation.
        """
        from penumbra_crypto.educational import tfhe_boolean as tfhe

        key = tfhe.LWEKey.generate()
        ct_a = tfhe.encrypt(key, 1)
        ct_b = tfhe.encrypt(key, 0)
        not_a = tfhe.homomorphic_not(ct_a)
        xor_ab = tfhe.homomorphic_xor(ct_a, ct_b)
        d_a = tfhe.decrypt(key, ct_a)
        d_b = tfhe.decrypt(key, ct_b)
        d_not_a = tfhe.decrypt(key, not_a)
        d_xor = tfhe.decrypt(key, xor_ab)
        return {
            "available": True,
            "algorithm": "LWE TFHE (educational)",
            "key_dim": len(key.s),
            "a_plain": 1,
            "b_plain": 0,
            "decrypt_a": int(d_a),
            "decrypt_b": int(d_b),
            "not_a_decrypts_to": int(d_not_a),
            "xor_decrypts_to": int(d_xor),
            "not_correct": bool(d_not_a == 0),
            "xor_correct": bool(d_xor == 1),
        }

    @app.get("/learning/gat-attention")
    async def learning_gat_attention() -> dict[str, object]:
        """Run a fresh GATv2 pathfinder over the live arena + return attention.

        Builds the dense adjacency + per-node features from the current
        arena, runs one forward pass through a randomly-initialised
        GATv2 pathfinder, and returns the per-node value + the layer-1
        attention matrix. Pedagogically: we use random weights because
        we don't have a trained checkpoint shipped — the focus here is
        WHAT graph attention is, not what the policy converged to.
        """
        sim_local: Simulation = app.state.penumbra.simulation
        import torch
        from penumbra_learning.gat_pathfinder import GATv2Pathfinder

        arena = sim_local.arena
        nodes = sorted(arena.graph.nodes())
        n = len(nodes)
        node_idx = {nid: i for i, nid in enumerate(nodes)}
        goals = set(arena.goals)
        x = torch.zeros((n, 2), dtype=torch.float32)
        for i, nid in enumerate(nodes):
            deg = arena.graph.degree(nid)
            x[i, 0] = 1.0 if nid in goals else 0.0
            x[i, 1] = float(deg) / 10.0
        adj = torch.zeros((n, n), dtype=torch.bool)
        edge_cost = torch.zeros((n, n), dtype=torch.float32)
        for u, v in arena.graph.edges():
            i, j = node_idx[u], node_idx[v]
            adj[i, j] = True
            adj[j, i] = True
            c = float(arena.cost_of(int(u), int(v)))
            edge_cost[i, j] = c
            edge_cost[j, i] = c
        for i in range(n):
            adj[i, i] = True  # self-loops as per GATv2 convention
        net = GATv2Pathfinder()
        with torch.no_grad():
            value, attn1, attn2 = net.attention_matrices(x, adj, edge_cost)
        return {
            "available": True,
            "n_nodes": n,
            "node_ids": [int(nid) for nid in nodes],
            "goals": [int(g) for g in arena.goals],
            "values": [float(v) for v in value.tolist()],
            "attention_layer1": [list(row) for row in attn1.tolist()],
            "attention_layer2": [list(row) for row in attn2.tolist()],
        }

    @app.get("/learning/saliency/{agent_id}")
    async def learning_saliency(agent_id: int) -> dict[str, object]:
        """Per-feature gradient of the chosen action's probability.

        Pedagogically: which feature in the observation moved the policy
        the most toward its chosen action? Computed via autograd on a
        single forward pass; works only when MAPPO is loaded.
        """
        runtime = app.state.penumbra.mappo_runtime
        sim_local: Simulation = app.state.penumbra.simulation
        if runtime is None:
            return {"available": False}
        if agent_id < 0 or agent_id >= len(sim_local.agents):
            raise HTTPException(status_code=404, detail=f"no agent {agent_id}")
        import torch
        from penumbra_learning.env import (
            NEIGHBOURS_K,
            OBS_PER_NEIGHBOUR,
            PAD_VALUE,
        )

        agent = sim_local.agents[agent_id]
        obs = agent.observe(sim_local.arena, tick=sim_local.tick_counter)
        neighbours = sorted(obs.neighbour_costs.keys())
        goals = set(obs.visible_goals)
        feats: list[float] = []
        for j in range(NEIGHBOURS_K):
            if j < len(neighbours):
                n_id = neighbours[j]
                feats.extend(
                    [
                        float(obs.neighbour_costs[n_id]),
                        1.0 if n_id in goals else 0.0,
                        1.0 if n_id in goals else 0.0,
                    ]
                )
            else:
                feats.extend([PAD_VALUE, PAD_VALUE, PAD_VALUE])
        del OBS_PER_NEIGHBOUR
        device = runtime.agent_net.device  # type: ignore[attr-defined]
        x = (
            torch.tensor(feats, dtype=torch.float32, device=device)
            .unsqueeze(0)
            .requires_grad_(True)
        )
        actor = runtime.agent_net.actor  # type: ignore[attr-defined]
        logits = actor.net(x) / float(runtime.temperature)  # type: ignore[attr-defined]
        probs = torch.softmax(logits, dim=-1)
        chosen = int(probs.argmax(dim=-1).item())
        # ∂p[chosen] / ∂x — magnitude per feature.
        scalar = probs[0, chosen]
        grads = torch.autograd.grad(scalar, x)[0]
        saliency = grads[0].abs().tolist()
        feat_labels = []
        for j in range(NEIGHBOURS_K):
            for slot in ("cost", "is_goal", "is_goal_dup"):
                feat_labels.append(f"neigh{j}.{slot}")
        return {
            "available": True,
            "agent_id": int(agent_id),
            "chosen_action": int(chosen),
            "features": [float(v) for v in feats],
            "feature_labels": feat_labels,
            "saliency": [float(s) for s in saliency],
        }

    @app.post("/learning/multi-checkpoint/{name}")
    async def learning_load_second_checkpoint(name: str) -> dict[str, object]:
        """Load a SECOND MAPPO checkpoint from /checkpoints into a side slot.

        The dashboard's A/B compare panel reads this side slot and the
        primary runtime to compute KL divergence between the two policies
        on a fresh batch of observations. `name` is a path relative to
        the `checkpoints/` directory.
        """
        from pathlib import Path

        runtime = app.state.penumbra.mappo_runtime
        if runtime is None:
            raise HTTPException(status_code=404, detail="no live MAPPO loaded")
        path = Path("checkpoints") / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"checkpoint {path} not found")
        from penumbra_learning.mappo import MAPPO, MAPPOConfig

        cfg = runtime.agent_net.config  # type: ignore[attr-defined]
        second = MAPPO(
            MAPPOConfig(obs_dim=cfg.obs_dim, n_actions=cfg.n_actions, n_agents=cfg.n_agents)
        )
        try:
            second.load(str(path), actor_only=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"load failed: {exc}") from exc
        app.state.penumbra.second_mappo = second
        return {"loaded": str(path), "path": str(path)}

    @app.get("/learning/ab-compare")
    async def learning_ab_compare() -> dict[str, object]:
        """Compare primary MAPPO vs the side-loaded second checkpoint.

        For each live agent, sample its current observation, compute the
        action distribution under BOTH policies, and report the KL
        divergence and top-action agreement.
        """
        runtime = app.state.penumbra.mappo_runtime
        second = getattr(app.state.penumbra, "second_mappo", None)
        sim_local: Simulation = app.state.penumbra.simulation
        if runtime is None or second is None:
            return {
                "available": False,
                "reason": "load a second checkpoint via /learning/multi-checkpoint/{name}",
            }
        import torch
        from penumbra_learning.env import NEIGHBOURS_K, PAD_VALUE

        feats_all: list[list[float]] = []
        for agent in sim_local.agents:
            obs = agent.observe(sim_local.arena, tick=sim_local.tick_counter)
            neighbours = sorted(obs.neighbour_costs.keys())
            goals = set(obs.visible_goals)
            f: list[float] = []
            for j in range(NEIGHBOURS_K):
                if j < len(neighbours):
                    n_id = neighbours[j]
                    f.extend(
                        [
                            float(obs.neighbour_costs[n_id]),
                            1.0 if n_id in goals else 0.0,
                            1.0 if n_id in goals else 0.0,
                        ]
                    )
                else:
                    f.extend([PAD_VALUE, PAD_VALUE, PAD_VALUE])
            feats_all.append(f)
        device = runtime.agent_net.device  # type: ignore[attr-defined]
        x = torch.tensor(feats_all, dtype=torch.float32, device=device)
        with torch.no_grad():
            logits_a = runtime.agent_net.actor.net(x) / float(runtime.temperature)  # type: ignore[attr-defined]
            logits_b = second.actor.net(x.to(second.device)) / float(runtime.temperature)  # type: ignore[attr-defined]
            logits_b = logits_b.to(device)
            probs_a = torch.softmax(logits_a, dim=-1)
            probs_b = torch.softmax(logits_b, dim=-1)
        eps = 1e-9
        kl_per_agent = (probs_a * (probs_a.add(eps).log() - probs_b.add(eps).log())).sum(dim=-1)
        agree = probs_a.argmax(dim=-1) == probs_b.argmax(dim=-1)
        return {
            "available": True,
            "n_agents": len(sim_local.agents),
            "agreement_rate": float(agree.float().mean().item()),
            "mean_kl": float(kl_per_agent.mean().item()),
            "max_kl": float(kl_per_agent.max().item()),
            "per_agent_kl": [float(v) for v in kl_per_agent.tolist()],
        }

    @app.get("/crypto/ckks/compare")
    async def crypto_ckks_compare() -> dict[str, object]:
        """Encrypt a small vector with CKKS, decrypt, return both sides.

        Pedagogically: the ciphertext is large + opaque (we show its
        byte size + first few hex bytes); decryption recovers the
        plaintext up to a small approximation error (CKKS is APPROXIMATE
        homomorphic encryption — that's the point).
        """
        from penumbra_crypto.ckks import get_backend

        backend = get_backend()
        plaintext_arr = np.asarray([1.0, 2.5, 3.14, -1.2, 7.7, 0.5, -3.3, 9.0], dtype=np.float64)
        plaintext = list(plaintext_arr.tolist())
        ct = backend.encrypt(plaintext_arr)
        decrypted = list(backend.decrypt(ct))[: len(plaintext)]
        # Get a byte preview if the backend exposes it.
        ct_bytes_preview: str | None = None
        ct_size: int | None = None
        try:
            serialize = getattr(backend, "serialize", None)
            if callable(serialize):
                raw: bytes = serialize(ct)  # type: ignore[no-untyped-call]
                ct_size = len(raw)
                ct_bytes_preview = raw[:32].hex()
        except Exception:
            logger.debug("CKKS ciphertext serialisation failed", exc_info=True)
        return {
            "available": True,
            "backend": type(backend).__name__,
            "plaintext": [float(v) for v in plaintext],
            "decrypted": [float(v) for v in decrypted],
            "absolute_error": [
                float(abs(a - b)) for a, b in zip(plaintext, decrypted, strict=False)
            ],
            "ciphertext_size_bytes": ct_size,
            "ciphertext_preview_hex": ct_bytes_preview,
        }

    @app.get("/crypto/kyber/demo")
    async def crypto_kyber_demo() -> dict[str, object]:
        """One full Kyber (ML-KEM-768) keygen + encaps + decaps round."""
        from penumbra_crypto import bls
        from penumbra_crypto.pq import (
            kem_decapsulate,
            kem_encapsulate,
            kem_keygen,
        )

        del bls  # only imported to keep static analysers happy in slim envs
        kp = kem_keygen()
        result = kem_encapsulate(kp.public_key)
        recovered = kem_decapsulate(kp.secret_key, result.ciphertext)
        match = recovered == result.shared_secret
        # Tamper one byte of the ciphertext.
        tampered_ct = bytearray(result.ciphertext)
        tampered_ct[0] ^= 0x01
        recovered_tampered = kem_decapsulate(kp.secret_key, bytes(tampered_ct))
        # Kyber uses implicit rejection — `recovered_tampered` will NOT
        # equal the original shared secret, but it WILL be deterministic.
        return {
            "available": True,
            "algorithm": "ML-KEM-768 (Kyber-3)",
            "public_key_size": len(kp.public_key),
            "secret_key_size": len(kp.secret_key),
            "ciphertext_size": len(result.ciphertext),
            "shared_secret_size": len(result.shared_secret),
            "public_key_short": kp.public_key.hex()[:32],
            "ciphertext_short": result.ciphertext.hex()[:32],
            "shared_secret_short": result.shared_secret.hex()[:32],
            "honest_match": bool(match),
            "tampered_match": bool(recovered_tampered == result.shared_secret),
        }

    # ── Phase 5 Tier 1 crypto primitives ──────────────────────────
    @app.get("/crypto/frost/demo")
    async def crypto_frost_demo(n: int = 5, t: int = 3) -> dict[str, object]:
        """FROST threshold Schnorr: t-of-n co-sign one Schnorr signature.

        The on-wire signature is plain Schnorr — no verifier can tell it
        came from a threshold of signers. Tamper-tests cover wrong
        message + corrupted response scalar.
        """
        from penumbra_crypto import frost as _frost

        return await asyncio.to_thread(_frost.demo, n=n, t=t)

    @app.get("/crypto/sphincs/demo")
    async def crypto_sphincs_demo() -> dict[str, object]:
        """SPHINCS+-128f-simple: hash-based PQ signature, NIST FIPS 205.

        Reports key + signature sizes alongside ML-DSA-65 (Dilithium-3)
        so the dashboard tile can visualise the size trade-off: SPHINCS+
        signatures are ~5x larger but rest on hash assumptions only.
        """
        from penumbra_crypto import sphincs as _sphincs

        return await asyncio.to_thread(_sphincs.demo)

    @app.get("/crypto/verkle/demo")
    async def crypto_verkle_demo(n_leaves: int = 1_000_000) -> dict[str, object]:
        """Verkle tree via KZG commits over BLS12-381 + Merkle proof-size compare.

        The educational SRS retains the toxic-waste secret so the
        prover side can run without an external ceremony; production
        deployments must DESTROY s after the ceremony.
        """
        from penumbra_crypto import verkle as _verkle

        n_leaves = max(2, min(int(n_leaves), 100_000_000))
        return await asyncio.to_thread(_verkle.demo, n_leaves=n_leaves)

    @app.get("/crypto/bbs-plus/demo")
    async def crypto_bbs_plus_demo(n_messages: int = 5) -> dict[str, object]:
        """BBS+ credentials: sign over a 5-attribute vector, selectively disclose 2."""
        from penumbra_crypto import bbs_plus as _bbs

        return await asyncio.to_thread(_bbs.demo, n_messages=n_messages)

    @app.get("/crypto/threshold-ecdsa/demo")
    async def crypto_threshold_ecdsa_demo(n: int = 3) -> dict[str, object]:
        """GG18-style threshold ECDSA (educational, n-of-n trusted-dealer)."""
        from penumbra_crypto import threshold_ecdsa as _tecdsa

        return await asyncio.to_thread(_tecdsa.demo, n=n)

    @app.get("/crypto/yao/demo")
    async def crypto_yao_demo() -> dict[str, object]:
        """Yao garbled circuits + millionaires comparator on two random integers."""
        from penumbra_crypto.educational import yao as _yao

        return await asyncio.to_thread(_yao.demo)

    @app.get("/crypto/psi/demo")
    async def crypto_psi_demo() -> dict[str, object]:
        """OPRF-based PSI: Alice + Bob find the intersection of their private sets."""
        from penumbra_crypto import psi as _psi

        return await asyncio.to_thread(_psi.demo)

    @app.get("/crypto/mix-net/demo")
    async def crypto_mix_net_demo(n_relays: int = 4) -> dict[str, object]:
        """Loopix-style onion mix-net: wrap, peel through N relays, deliver."""
        from penumbra_crypto import mix_net as _mix

        return await asyncio.to_thread(_mix.demo, n_relays=n_relays)

    # ── Logistics endpoints (Tier 1) ──────────────────────────────
    @app.get("/logistics/fill-rate")
    async def logistics_fill_rate() -> dict[str, object]:
        """End-customer demand fill rate: served / requested + per-product breakdown."""
        from penumbra_core.logistics import compute_fill_rate

        orch = app.state.penumbra.orchestrator
        if orch.demand is None:
            return {"available": False, "reason": "demand model not initialised"}
        report = compute_fill_rate(orch.demand)
        return {
            "available": True,
            "overall_fill_rate": report.overall_fill_rate,
            "total_served": report.total_served,
            "total_requested": report.total_requested,
            "total_backlog": report.total_backlog,
            "per_product": [list(p) for p in report.per_product],
        }

    @app.get("/logistics/inventory-health")
    async def logistics_inventory_health() -> dict[str, object]:
        """Per-city per-product inventory + holding/stockout cost."""
        from penumbra_core.logistics import compute_inventory_health

        orch = app.state.penumbra.orchestrator
        if orch.market is None:
            return {"available": False, "reason": "market not initialised"}
        report = compute_inventory_health(orch.market, demand=orch.demand)
        return {
            "available": True,
            "cells": [list(c) for c in report.cells[:200]],
            "holding_cost_total": report.holding_cost_total,
            "stockout_cost_total": report.stockout_cost_total,
            "n_stockouts": report.n_stockouts,
            "n_cells_total": len(report.cells),
        }

    @app.get("/logistics/orders")
    async def logistics_orders() -> dict[str, object]:
        """Pending + fulfilled order book + lead-time stats."""
        from penumbra_core.logistics import compute_order_book

        orch = app.state.penumbra.orchestrator
        if orch.logistics_mempool is None:
            return {"available": False, "reason": "mempool not initialised"}
        report = compute_order_book(orch.logistics_mempool)
        return {
            "available": True,
            "n_pending": report.n_pending,
            "n_fulfilled": report.n_fulfilled,
            "median_lead_time_ticks": report.median_lead_time_ticks,
            "p95_lead_time_ticks": report.p95_lead_time_ticks,
            "pending_sample": [list(p) for p in report.pending_sample],
        }

    @app.get("/logistics/reorder-policy")
    async def logistics_reorder_get() -> dict[str, object]:
        """Current (s, S) policy snapshot (sample of pairs)."""
        orch = app.state.penumbra.orchestrator
        if orch.reorder_policy is None:
            return {"available": False, "reason": "no reorder policy"}
        pairs = list(orch.reorder_policy.s.items())[:50]
        return {
            "available": True,
            "n_pairs_total": len(orch.reorder_policy.s),
            "sample": [
                {
                    "city": k[0],
                    "product": k[1],
                    "s": v,
                    "S": orch.reorder_policy.big_s.get(k, v + 1),
                }
                for k, v in pairs
            ],
            "lead_time_ticks": orch._logistics_lead_time_ticks,
        }

    @app.post("/logistics/reorder-policy")
    async def logistics_reorder_set(
        s_fraction: float,
        S_fraction: float,  # noqa: N803 — (s, S) is the OR convention
    ) -> dict[str, object]:
        """Reset (s, S) using fractions of each city's max_inventory."""
        from penumbra_core.logistics import ReorderPolicy

        orch = app.state.penumbra.orchestrator
        if orch.market is None:
            raise HTTPException(status_code=400, detail="market not initialised")
        if not (0.0 < s_fraction < S_fraction <= 1.0):
            raise HTTPException(
                status_code=400,
                detail="require 0 < s_fraction < S_fraction <= 1.0",
            )
        orch.reorder_policy = ReorderPolicy.fractional(
            orch.market, s_fraction=s_fraction, S_fraction=S_fraction
        )
        return {
            "ok": True,
            "s_fraction": s_fraction,
            "S_fraction": S_fraction,
            "n_pairs": len(orch.reorder_policy.s),
        }

    @app.get("/logistics/capacity")
    async def logistics_capacity() -> dict[str, object]:
        """Per-agent cargo utilization."""
        from penumbra_core.logistics import compute_cargo_utilization

        orch = app.state.penumbra.orchestrator
        if orch.cargo is None or orch.market is None:
            return {"available": False, "reason": "cargo not initialised"}
        report = compute_cargo_utilization(orch.cargo, orch.market)
        return {
            "available": True,
            "mean_utilization": report.mean_utilization,
            "per_agent": [list(p) for p in report.per_agent[:100]],
        }

    @app.get("/logistics/dispatch")
    async def logistics_dispatch() -> dict[str, object]:
        """Carrier-dispatch KPIs: assignments, earnings, fulfilment efficiency."""
        from penumbra_core.logistics import compute_dispatch_report

        orch = app.state.penumbra.orchestrator
        if orch.logistics_mempool is None or orch.market is None:
            return {"available": False, "reason": "logistics not initialised"}
        report = compute_dispatch_report(orch.market, orch.logistics_mempool)
        return {
            "available": True,
            "n_pending": report.n_pending,
            "n_assigned": report.n_assigned,
            "n_unassigned": report.n_unassigned,
            "n_fulfilled": report.n_fulfilled,
            "n_placed": report.n_placed,
            "n_phantom_fulfilled": report.n_phantom_fulfilled,
            "mean_carrier_revenue": report.mean_carrier_revenue,
            "fulfilment_efficiency": report.fulfilment_efficiency,
            "top_carriers": [list(p) for p in report.top_carriers],
            "agent_earnings": [list(p) for p in report.agent_earnings[:100]],
        }

    @app.get("/logistics/vrp-baseline")
    async def logistics_vrp_baseline(
        solver: str = "two_opt",
        max_orders: int = 32,
    ) -> dict[str, object]:
        """Snapshot VRP solve over current pending orders.

        Solvers: `greedy`, `two_opt` (default), `or_tools`. Returns the
        solver's total cost + per-agent route lengths plus a comparison
        against a naive baseline (sum of order quantities × mean edge
        cost) — the "actual_fulfilment_cost" the system would pay if it
        moved one unit per edge with no routing intelligence.
        """
        orch = app.state.penumbra.orchestrator
        if orch.logistics_mempool is None:
            return {"available": False, "reason": "mempool not initialised"}
        if solver not in ("greedy", "two_opt", "or_tools"):
            raise HTTPException(
                status_code=400, detail="solver must be one of greedy / two_opt / or_tools"
            )
        solution = await asyncio.to_thread(
            orch.compute_vrp_baseline, solver=solver, max_orders=int(max_orders)
        )
        if solution is None:
            return {"available": False, "reason": "no pending orders or no agents"}
        arena = orch.simulation.arena
        edge_costs = list(arena.edge_cost.values()) if arena.edge_cost else [1.0]
        mean_edge_cost = float(sum(edge_costs) / max(len(edge_costs), 1))
        total_quantity = sum(o.quantity for o in orch.logistics_mempool.pending[: int(max_orders)])
        actual_fulfilment_cost = float(total_quantity) * mean_edge_cost
        gap = 0.0
        if actual_fulfilment_cost > 0:
            gap = (actual_fulfilment_cost - solution.total_cost) / actual_fulfilment_cost
        per_agent_routes: list[dict[str, object]] = []
        for idx, route in enumerate(solution.routes):
            if not route:
                continue
            per_agent_routes.append(
                {
                    "agent_idx": idx,
                    "n_stops": len(route),
                    "cost": float(solution.per_agent_cost[idx]),
                }
            )
        return {
            "available": True,
            "solver": solution.solver,
            "solver_total_cost": float(solution.total_cost),
            "actual_fulfilment_cost": actual_fulfilment_cost,
            "gap_fraction": gap,
            "n_orders_served": len(solution.served_order_ids),
            "n_orders_unserved": len(solution.unserved_order_ids),
            "n_orders_considered": len(solution.served_order_ids)
            + len(solution.unserved_order_ids),
            "compute_time_ms": float(solution.compute_time_ms),
            "per_agent_routes": per_agent_routes[:50],
            "metadata": dict(solution.metadata),
        }

    @app.get("/logistics/echelon")
    async def logistics_echelon() -> dict[str, object]:
        """Tier 3: multi-echelon supply chain snapshot + bullwhip ratio."""
        from penumbra_core.logistics_echelon import compute_echelon_report

        orch = app.state.penumbra.orchestrator
        net = orch.echelon_network
        if net is None:
            return {"available": False, "reason": "echelon network not initialised"}
        report = compute_echelon_report(net)

        def _clean(value: float) -> float | None:
            if value != value:  # NaN check
                return None
            return float(value)

        return {
            "available": True,
            "tick": report.tick,
            "n_suppliers": report.n_suppliers,
            "n_distributors": report.n_distributors,
            "n_cities": report.n_cities,
            "inventory_by_tier": [list(row) for row in report.inventory_by_tier],
            "mean_inventory_by_tier": [
                [row[0], float(row[1])] for row in report.mean_inventory_by_tier
            ],
            "in_flight_count": report.in_flight_count,
            "in_flight_quantity": report.in_flight_quantity,
            "demand_variance": float(report.demand_variance),
            "bullwhip_per_tier": [[row[0], _clean(row[1])] for row in report.bullwhip_per_tier],
            "variance_per_tier": [[row[0], float(row[1])] for row in report.variance_per_tier],
            "edges": [list(e) for e in report.edges[:200]],
            "role_for_node": [list(r) for r in report.role_for_node[:200]],
        }

    # ── Federated Learning endpoints (Tier 1 + 2) ─────────────────
    @app.get("/federated/status")
    async def federated_status() -> dict[str, object]:
        """Snapshot of the FL trainer state."""
        orch = app.state.penumbra.orchestrator
        if orch.federated_trainer is None:
            return {"available": False, "reason": "FL trainer not initialised"}
        return {"available": True, **orch.federated_trainer.summary()}  # type: ignore[attr-defined]

    @app.post("/federated/start")
    async def federated_start(method: str = "fedavg") -> dict[str, object]:
        """Initialise the FederatedTrainer from the live MAPPO actor."""
        from penumbra_learning.federated import FederatedTrainer

        state: AppState = app.state.penumbra
        runtime = state.mappo_runtime
        if runtime is None:
            raise HTTPException(status_code=400, detail="MAPPO checkpoint not loaded")
        if method not in ("fedavg", "ckks_sum"):
            raise HTTPException(status_code=400, detail="method must be fedavg or ckks_sum")
        trainer = FederatedTrainer.from_mappo(
            runtime.agent_net,  # type: ignore[attr-defined]
            n_agents=len(state.simulation.agents),
            method=method,
        )
        trainer.start()
        state.orchestrator.federated_trainer = trainer
        return {"ok": True, "method": method, "n_participants": len(trainer.local_actors)}

    @app.post("/federated/stop")
    async def federated_stop() -> dict[str, object]:
        orch = app.state.penumbra.orchestrator
        if orch.federated_trainer is None:
            return {"ok": True, "was_running": False}
        orch.federated_trainer.stop()  # type: ignore[attr-defined]
        return {"ok": True, "was_running": True}

    @app.post("/federated/round")
    async def federated_round() -> dict[str, object]:
        """Run one FL round manually (local SGD → aggregate → broadcast)."""
        orch = app.state.penumbra.orchestrator
        if orch.federated_trainer is None:
            raise HTTPException(status_code=400, detail="FL not started")
        record = await asyncio.to_thread(orch.federated_trainer.step)  # type: ignore[attr-defined]
        return {
            "round_id": record.round_id,
            "method": record.aggregation_method,
            "encrypted": record.encrypted,
            "bandwidth_bytes": record.bandwidth_bytes,
            "aggregation_time_ms": record.aggregation_time_ms,
            "l2_change": record.parameter_l2_norm_change,
        }

    @app.post("/federated/dp")
    async def federated_dp(sigma: float, clip: float) -> dict[str, object]:
        """Set DP-SGD parameters (Tier 3 toggle)."""
        orch = app.state.penumbra.orchestrator
        if orch.federated_trainer is None:
            raise HTTPException(status_code=400, detail="FL not started")
        if sigma < 0 or clip < 0:
            raise HTTPException(status_code=400, detail="sigma and clip must be >= 0")
        orch.federated_trainer.dp_noise_sigma = float(sigma)  # type: ignore[attr-defined]
        orch.federated_trainer.dp_l2_clip = float(clip)  # type: ignore[attr-defined]
        return {"ok": True, "sigma": sigma, "clip": clip}

    @app.post("/federated/method/{method}")
    async def federated_set_method(method: str) -> dict[str, object]:
        """Switch the aggregation method (fedavg / ckks_sum / krum / trimmed_mean)."""
        orch = app.state.penumbra.orchestrator
        if orch.federated_trainer is None:
            raise HTTPException(status_code=400, detail="FL not started")
        try:
            orch.federated_trainer.set_method(method)  # type: ignore[attr-defined]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "method": method}

    @app.post("/federated/fedprox")
    async def federated_fedprox(mu: float) -> dict[str, object]:
        """Tier 5: set the FedProx proximal-term coefficient mu (>= 0)."""
        orch = app.state.penumbra.orchestrator
        if orch.federated_trainer is None:
            raise HTTPException(status_code=400, detail="FL not started")
        try:
            orch.federated_trainer.set_fedprox(mu)  # type: ignore[attr-defined]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "mu": float(mu)}

    @app.post("/federated/compress")
    async def federated_compress(topk: float = 1.0, quantize: int = 0) -> dict[str, object]:
        """Tier 5: set top-k sparsification + optional 8-bit quantisation."""
        orch = app.state.penumbra.orchestrator
        if orch.federated_trainer is None:
            raise HTTPException(status_code=400, detail="FL not started")
        try:
            orch.federated_trainer.set_compression(  # type: ignore[attr-defined]
                topk_fraction=topk,
                quantize_bits=quantize,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "topk_fraction": float(topk), "quantize_bits": int(quantize)}

    @app.get("/federated/privacy")
    async def federated_privacy(delta: float = 1e-5) -> dict[str, object]:
        """Tier 3: real Rényi DP (ε, δ) for the FL trainer's DP-SGD steps.

        Returns ``{epsilon, delta, n_steps_accounted, mode}`` where
        ``mode == "rdp"`` iff at least one DP-SGD step has been
        composed into the accountant. Without a trainer or before any
        noisy step, returns ``mode == "toy"`` with ε=0.
        """
        orch = app.state.penumbra.orchestrator
        if orch.federated_trainer is None:
            return {
                "available": False,
                "reason": "FL trainer not initialised",
                "epsilon": 0.0,
                "delta": float(delta),
                "n_steps_accounted": 0,
                "mode": "toy",
            }
        if not 0.0 < delta < 1.0:
            raise HTTPException(status_code=400, detail="delta must be in (0, 1)")
        trainer = orch.federated_trainer
        accountant = trainer.rdp_accountant  # type: ignore[attr-defined]
        if accountant is None or accountant.n_steps == 0:
            return {
                "available": True,
                "epsilon": 0.0,
                "delta": float(delta),
                "n_steps_accounted": 0,
                "mode": "toy",
            }
        eps = float(trainer.epsilon(delta=float(delta)))  # type: ignore[attr-defined]
        return {
            "available": True,
            "epsilon": eps,
            "delta": float(delta),
            "n_steps_accounted": int(accountant.n_steps),
            "mode": "rdp",
        }

    # ── Penumbra-Bench Tier 2: public leaderboard ─────────────────
    @app.get("/benchmark/leaderboard")
    async def benchmark_leaderboard(
        tier: str = "tiny",
        limit: int = 50,
    ) -> dict[str, object]:
        """Scan `state/bench/*.json` and return the leaderboard for a tier.

        Each entry's `tasks` list is collapsed into a `task_scores`
        mapping (task_id → score) so the frontend can render a
        sortable table without nested traversal. Sorted by
        `composite_score` descending.
        """
        valid_tiers = {"tiny", "small", "medium", "large"}
        if tier not in valid_tiers:
            raise HTTPException(
                status_code=400,
                detail=f"tier must be one of {sorted(valid_tiers)}",
            )
        limit = max(1, min(limit, 200))
        entries = _scan_bench_directory()
        filtered = [e for e in entries if e.get("tier") == tier]
        filtered.sort(
            key=lambda e: _as_float(e.get("composite_score", 0.0)),
            reverse=True,
        )
        truncated = filtered[:limit]
        return {
            "available": True,
            "tier": tier,
            "n_total": len(filtered),
            "entries": [_format_leaderboard_entry(i, e, tier) for i, e in enumerate(truncated)],
        }

    @app.get("/benchmark/submission/{filename}")
    def benchmark_submission(filename: str) -> dict[str, object]:
        """Return the full submission JSON for one file under state/bench/.

        Declared `def` (not `async def`) so FastAPI runs the file I/O on
        its threadpool — `pathlib` is blocking and would trigger
        ASYNC240 inside an async handler.
        """
        from pathlib import Path

        if "/" in filename or "\\" in filename or filename.startswith("."):
            raise HTTPException(status_code=400, detail="invalid filename")
        if not filename.endswith(".json"):
            raise HTTPException(status_code=400, detail="filename must end with .json")
        bench_dir = Path(__file__).resolve().parents[3] / "state" / "bench"
        path = bench_dir / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"no submission named {filename}")
        try:
            import json

            data = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"failed to read submission: {exc}",
            ) from exc
        if not isinstance(data, dict):
            raise HTTPException(status_code=500, detail="malformed submission file")
        data["filename"] = filename
        data["available"] = True
        return data

    # ── Phase 5 Tier 3: defense primitives (privacy-utility tradeoffs) ─
    @app.get("/defenses/data_poisoning/demo")
    async def defenses_data_poisoning_demo() -> dict[str, object]:
        """Sweep poisoning rate vs attacker max accuracy / utility shift.

        Each point is (rate, attacker_max_accuracy, utility_mean_shift,
        utility_std_shift). Pure-functional demo — no orchestrator
        state touched.
        """
        from penumbra_crypto.defenses import data_poisoning

        return await asyncio.to_thread(data_poisoning.demo)

    @app.get("/defenses/padding/demo")
    async def defenses_padding_demo() -> dict[str, object]:
        """Padding curve + Poisson cover-traffic schedule sample.

        Bandwidth overhead = target_size / mean(real size); a single
        bucket size collapses distinct sizes to 1.
        """
        from penumbra_crypto.defenses import padding

        return await asyncio.to_thread(padding.demo)

    @app.get("/defenses/k_anonymity/demo")
    async def defenses_k_anonymity_demo() -> dict[str, object]:
        """Sweep k vs suppression rate / adversary advantage = 1/k."""
        from penumbra_crypto.defenses import k_anonymity

        return await asyncio.to_thread(k_anonymity.demo)

    @app.get("/defenses/l_diversity/demo")
    async def defenses_l_diversity_demo() -> dict[str, object]:
        """Sweep ℓ at fixed k vs suppression / homogeneity safety."""
        from penumbra_crypto.defenses import l_diversity

        return await asyncio.to_thread(l_diversity.demo)

    @app.get("/defenses/gan/demo")
    async def defenses_gan_demo() -> dict[str, object]:
        """Sweep correlation-preserve vs mean L2 / covariance Frobenius gaps.

        Stub Gaussian release; CycleGAN deferred (same API).
        """
        from penumbra_crypto.defenses import gan_defenses

        return await asyncio.to_thread(gan_defenses.demo)

    @app.get("/defenses/request_obfuscation/demo")
    async def defenses_request_obfuscation_demo() -> dict[str, object]:
        """Sweep dummy count vs attacker budget inflation (Bonferroni)."""
        from penumbra_crypto.defenses import request_obfuscation

        return await asyncio.to_thread(request_obfuscation.demo)

    # ── Phase 5 Tier 2 — attack-suite demos ────────────────────────
    @app.get("/attacks/agent_fingerprint/demo")
    async def attacks_agent_fingerprint_demo() -> dict[str, object]:
        """1-NN behavioural fingerprint over observable agent traces."""
        from penumbra_attacker.attacks import agent_fingerprint

        return await asyncio.to_thread(agent_fingerprint.demo)

    @app.get("/attacks/trajectory_fingerprint/demo")
    async def attacks_trajectory_fingerprint_demo() -> dict[str, object]:
        """Per-agent HMM fitted via Baum-Welch then forward-likelihood classify."""
        from penumbra_attacker.attacks import trajectory_fingerprint

        return await asyncio.to_thread(trajectory_fingerprint.demo)

    @app.get("/attacks/membership_inference/demo")
    async def attacks_membership_inference_demo() -> dict[str, object]:
        """Shokri shadow-model membership inference on a tiny softmax policy."""
        from penumbra_attacker.attacks import membership_inference

        return await asyncio.to_thread(membership_inference.demo)

    @app.get("/attacks/model_inversion/demo")
    async def attacks_model_inversion_demo() -> dict[str, object]:
        """Deep-Leakage-from-Gradients reconstruction against a linear policy."""
        from penumbra_attacker.attacks import model_inversion

        return await asyncio.to_thread(model_inversion.demo)

    @app.get("/attacks/reward_poisoning/demo")
    async def attacks_reward_poisoning_demo() -> dict[str, object]:
        """Inject 5% poisoned rewards; measure policy drift on a 4-armed bandit."""
        from penumbra_attacker.attacks import reward_poisoning

        return await asyncio.to_thread(reward_poisoning.demo)

    @app.get("/attacks/cache_sidechannel/demo")
    async def attacks_cache_sidechannel_demo() -> dict[str, object]:
        """Flush+Reload-style timing test on TenSEAL CKKS add — should NOT leak."""
        from penumbra_attacker.attacks import cache_sidechannel

        return await asyncio.to_thread(cache_sidechannel.demo, n_samples=80, vector_size=32)

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

    # ── Phase 6b Tier 1 — operator endpoints ──────────────────────

    def _require_operator() -> tuple[object, object, object]:
        """Return (orchestrator, operator_queue, operator_context) or raise 409."""
        orch = app.state.penumbra.orchestrator
        if orch.operator is None or orch.operator_queue is None or orch.operator_context is None:
            raise HTTPException(
                status_code=409,
                detail="operator is not enabled; POST /operator/enable first",
            )
        return orch, orch.operator_queue, orch.operator_context

    def _serialise_result(result: object) -> dict[str, object]:
        # Convert OperatorActionResult dataclass into a plain JSON dict.
        return {
            "kind": getattr(result, "kind", ""),
            "success": bool(getattr(result, "success", False)),
            "data": dict(getattr(result, "data", {})),
            "error": getattr(result, "error", None),
            "skipped": bool(getattr(result, "skipped", False)),
            "elapsed_ms": float(getattr(result, "elapsed_ms", 0.0)),
            "applied_tick": int(getattr(result, "applied_tick", -1)),
        }

    def _submit_and_drain(kind: str, payload: dict[str, object]) -> dict[str, object]:
        """Enqueue an action, drain it immediately, return its result.

        Tier 1 endpoints synchronously drain after submit so the CLI
        gets a useful response. The same queue is also drained by the
        simulation's pre_tick_hook, which is what makes the action
        catalogue robust under concurrent CLI + dashboard submission.
        """
        from penumbra_operator.actions import OperatorAction, apply_action

        orch, queue, ctx = _require_operator()
        action = OperatorAction(
            kind=kind,
            payload=dict(payload),
            submit_tick=int(orch.simulation.tick_counter),  # type: ignore[attr-defined]
        )
        queue.submit(action)  # type: ignore[attr-defined]
        # Pop the action we just submitted (and any earlier-queued
        # actions still pending). Apply in deterministic order.
        from penumbra_operator.actions import coalesce_moves

        due = queue.pop_due(int(orch.simulation.tick_counter))  # type: ignore[attr-defined]
        due = coalesce_moves(due)
        results: list[object] = []
        session_logger = getattr(orch, "operator_session_logger", None)
        session_id = getattr(orch, "operator_session_id", None)
        for due_action in due:
            result = apply_action(ctx, due_action)  # type: ignore[arg-type]
            orch.operator_recent_results.append(result)  # type: ignore[attr-defined]
            results.append(result)
            # Phase 6b Tier 6 — record into the open session log.
            if session_logger is not None and session_id is not None:
                with contextlib.suppress(Exception):
                    session_logger.record(session_id, due_action, result)
        if len(orch.operator_recent_results) > 200:  # type: ignore[attr-defined]
            del orch.operator_recent_results[: len(orch.operator_recent_results) - 200]  # type: ignore[attr-defined]
        # Save-resume: snapshot AFTER the action drained so the save
        # reflects post-action wallet / inventory / arena state. Best-
        # effort — _save_current_scenario_state is a no-op when no
        # scenario is live.
        _save_current_scenario_state()
        # Return the result that matches our action kind, falling back
        # to the last result if coalescing dropped ours (e.g. earlier
        # move overwritten by a later one in the same tick).
        for r in reversed(results):
            if getattr(r, "kind", "") == kind:
                return _serialise_result(r)
        if results:
            return _serialise_result(results[-1])
        # Coalesced away (no result emitted): mirror an "ok, coalesced"
        # response so the caller knows the submission was accepted.
        return {
            "kind": kind,
            "success": True,
            "data": {"coalesced": True},
            "error": None,
            "skipped": False,
            "elapsed_ms": 0.0,
            "applied_tick": int(orch.simulation.tick_counter),  # type: ignore[attr-defined]
        }

    @app.post("/operator/enable")
    async def operator_enable() -> dict[str, object]:
        orch = app.state.penumbra.orchestrator
        info = orch.enable_operator()
        from penumbra_operator.actions import known_kinds

        info["known_kinds"] = list(known_kinds())
        return info

    @app.post("/operator/disable")
    async def operator_disable() -> dict[str, object]:
        orch = app.state.penumbra.orchestrator
        return orch.disable_operator()

    @app.post("/operator/move")
    async def operator_move(payload: dict[str, object]) -> dict[str, object]:
        return _submit_and_drain("move", payload)

    @app.post("/operator/buy")
    async def operator_buy(payload: dict[str, object]) -> dict[str, object]:
        return _submit_and_drain("buy", payload)

    @app.post("/operator/sell")
    async def operator_sell(payload: dict[str, object]) -> dict[str, object]:
        return _submit_and_drain("sell", payload)

    @app.post("/operator/dispatch_order")
    async def operator_dispatch_order(payload: dict[str, object]) -> dict[str, object]:
        return _submit_and_drain("dispatch_order", payload)

    @app.post("/operator/cancel_assignment")
    async def operator_cancel_assignment(payload: dict[str, object]) -> dict[str, object]:
        return _submit_and_drain("cancel_assignment", payload)

    @app.post("/operator/query_dp")
    async def operator_query_dp(payload: dict[str, object]) -> dict[str, object]:
        return _submit_and_drain("query_dp", payload)

    @app.post("/operator/sign")
    async def operator_sign(payload: dict[str, object]) -> dict[str, object]:
        return _submit_and_drain("sign", payload)

    @app.post("/operator/verify")
    async def operator_verify(payload: dict[str, object]) -> dict[str, object]:
        return _submit_and_drain("verify", payload)

    # ── Phase 6b Tier 3 + Tier 4 — attack + defense endpoints ──────
    #
    # Each kind below is wired through the same _submit_and_drain
    # plumbing as the Tier 1 actions. The closure dance is a factory
    # so we don't repeat 12 decorators with identical bodies.

    def _make_action_endpoint(kind: str) -> object:
        async def _endpoint(payload: dict[str, object]) -> dict[str, object]:
            return _submit_and_drain(kind, payload)

        _endpoint.__name__ = f"operator_{kind}"
        return _endpoint

    from penumbra_operator.actions import ATTACK_KINDS, DEFENSE_KINDS

    for _kind in (*ATTACK_KINDS, *DEFENSE_KINDS):
        app.post(f"/operator/{_kind}")(_make_action_endpoint(_kind))  # type: ignore[arg-type]

    @app.get("/operator/defense_status")
    async def operator_defense_status() -> dict[str, object]:
        """Round-trip view of the current Tier 4 defense configuration."""
        orch = app.state.penumbra.orchestrator
        if orch.operator_context is None:
            return {"enabled": False}
        ctx = orch.operator_context
        defenses = ctx.defenses  # type: ignore[attr-defined]
        return {
            "enabled": True,
            "k_anonymity": defenses.k_anonymity,
            "padding": defenses.padding,
            "gan_poison": defenses.gan_poison,
            "dp_paused": bool(defenses.dp_paused),
            "krum_f": defenses.krum_f,
            "key_rotations": int(defenses.key_rotations),
        }

    @app.get("/operator/status")
    async def operator_status() -> dict[str, object]:
        orch = app.state.penumbra.orchestrator
        if orch.operator is None or orch.operator_queue is None or orch.operator_context is None:
            return {
                "enabled": False,
                "hint": "POST /operator/enable to bootstrap the operator slot",
            }
        ctx = orch.operator_context
        agent = ctx.operator_agent  # type: ignore[attr-defined]
        wallet = ctx.market.wallets.get(ctx.operator_agent_id)  # type: ignore[attr-defined]
        dp_budget = ctx.dp_mechanism.budget  # type: ignore[attr-defined]
        from penumbra_operator.scoring import OperatorScoreCard

        scorecard = OperatorScoreCard.compute(
            coins_now=float(wallet.coins) if wallet is not None else 0.0,
            coins_start=float(ctx.initial_coins),  # type: ignore[attr-defined]
            epsilon_spent=float(dp_budget.epsilon_spent),
            epsilon_total=float(dp_budget.epsilon),
            attacks_survived=int(orch.operator_attacks_survived),
            chain_contribution=int(orch.operator_chain_contribution),
        )
        recent = orch.operator_recent_results[-50:]
        return {
            "enabled": True,
            "operator_id": int(ctx.operator_agent_id),  # type: ignore[attr-defined]
            "position": int(agent.position),
            "coins": float(wallet.coins) if wallet is not None else 0.0,
            "inventory": dict(wallet.inventory) if wallet is not None else {},
            "epsilon_total": float(dp_budget.epsilon),
            "epsilon_spent": float(dp_budget.epsilon_spent),
            "epsilon_remaining": float(dp_budget.remaining_epsilon),
            "queue": orch.operator_queue.stats(),  # type: ignore[attr-defined]
            "recent_results": [_serialise_result(r) for r in recent],
            "scorecard": {
                "profit": scorecard.profit,
                "privacy_preserved": scorecard.privacy_preserved,
                "attacks_survived": scorecard.attacks_survived,
                "chain_contribution": scorecard.chain_contribution,
                "composite": scorecard.composite,
            },
        }

    # ── Phase 5 Tier 4 — Custom policy injection ──────────────────
    @app.post("/attacker/policy")
    async def attacker_register_policy(payload: dict[str, str]) -> dict[str, object]:
        from penumbra_attacker.policy_sandbox import (
            PolicyParseError,
            PolicyRuntimeError,
            PolicyTimeoutError,
            register_policy,
            try_policy,
        )

        name = payload.get("name", "")
        code = payload.get("code", "")
        scope = payload.get("scope", "all")
        try:
            registered = register_policy(name, code, scope)
        except PolicyParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try_state: dict[str, object] = {}
        try:
            sample = try_policy(name, {}, {})
            try_state = {"ok": True, "result": repr(sample)}
        except (PolicyRuntimeError, PolicyTimeoutError) as exc:
            try_state = {"ok": False, "error": str(exc)}
        return {
            "name": registered.name,
            "scope": registered.scope,
            "source_chars": len(registered.source),
            "try": try_state,
        }

    @app.get("/attacker/policies")
    async def attacker_list_policies() -> dict[str, object]:
        from penumbra_attacker.policy_sandbox import list_registered

        return {"available": True, "policies": list_registered()}

    @app.delete("/attacker/policy/{name}")
    async def attacker_unregister_policy(name: str) -> dict[str, object]:
        from penumbra_attacker.policy_sandbox import unregister

        removed = unregister(name)
        if not removed:
            raise HTTPException(status_code=404, detail=f"no policy named {name!r}")
        return {"name": name, "removed": True}

    # ── Phase 5 Tier 4 — Capture-the-flag ─────────────────────────
    @app.get("/ctf/challenges")
    async def ctf_list_challenges() -> dict[str, object]:
        from penumbra_ctf import global_registry

        return {"available": True, "challenges": global_registry().list_summaries()}

    @app.post("/ctf/submit/{challenge_id}")
    async def ctf_submit(challenge_id: str, payload: dict[str, str]) -> dict[str, object]:
        from penumbra_ctf import ChallengeNotFoundError, global_registry

        flag = payload.get("flag", "")
        session_id = payload.get("session_id", "anonymous")
        try:
            return global_registry().submit(challenge_id, flag, session_id)
        except ChallengeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/ctf/leaderboard/{challenge_id}")
    async def ctf_leaderboard(challenge_id: str) -> dict[str, object]:
        from penumbra_ctf import ChallengeNotFoundError, global_registry

        try:
            return {
                "challenge_id": challenge_id,
                "leaderboard": global_registry().leaderboard(challenge_id),
            }
        except ChallengeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # ── Phase 5 Tier 4 — World branching ──────────────────────────
    @app.post("/world/branch")
    async def world_branch(payload: dict[str, object]) -> dict[str, object]:
        from penumbra_transport.world import global_branches

        name = str(payload.get("name", ""))
        raw_n = payload.get("n_branches", 5)
        n_branches = int(raw_n) if isinstance(raw_n, int | float | str) else 5
        try:
            ids = global_branches().branch(
                name, app.state.penumbra.simulation, n_branches=n_branches
            )
        except InvalidSnapshotNameError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"available": True, "name": name, "branch_ids": ids}

    @app.get("/world/branches")
    async def world_list_branches() -> dict[str, object]:
        from penumbra_transport.world import global_branches

        return {"available": True, "branches": global_branches().list_branches()}

    @app.post("/world/branch/{branch_id}/advance")
    async def world_branch_advance(branch_id: str, payload: dict[str, int]) -> dict[str, object]:
        from penumbra_transport.world import BranchNotFoundError, global_branches

        ticks = int(payload.get("ticks", 1))
        try:
            result = global_branches().advance(branch_id, ticks)
        except BranchNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return dict(result)

    @app.post("/world/branches/compare")
    async def world_branches_compare(payload: dict[str, object]) -> dict[str, object]:
        from penumbra_transport.world import BranchNotFoundError, global_branches

        raw = payload.get("branch_ids", [])
        if not isinstance(raw, list):
            raise HTTPException(status_code=400, detail="branch_ids must be a list")
        try:
            return global_branches().compare([str(b) for b in raw])
        except BranchNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # ── Phase 6b Tier 5 — scenario engine ─────────────────────────

    def _get_scenario_runner() -> object:
        """Lazy-build the scenario runner on first use; cache on app.state."""
        runner = getattr(app.state, "scenario_runner", None)
        if runner is None:
            from penumbra_operator.scenarios import ScenarioRunner

            runner = ScenarioRunner.from_directory()
            app.state.scenario_runner = runner
        return runner

    # Save-resume: per-app override path lets tests pin save_root to a
    # tmp_path without touching the global env. Falls back to the
    # ``PENUMBRA_OPERATOR_SAVE_DIR`` env var so the operator CLI / docker
    # compose stack can repoint storage too.
    def _save_resume_dir() -> object:
        import os as _os
        from pathlib import Path as _Path

        override = getattr(app.state, "operator_save_dir", None)
        if override is not None:
            return _Path(str(override))
        env = _os.environ.get("PENUMBRA_OPERATOR_SAVE_DIR")
        if env:
            return _Path(env)
        return None

    def _active_save_session_id(runner: object) -> tuple[str, object] | None:
        """Return (scenario_id, ScenarioSession) for the (single) live scenario, if any."""
        sessions = getattr(runner, "_sessions", {})  # type: ignore[attr-defined]
        if not sessions:
            return None
        # The runner only carries one active session per scenario id;
        # the dashboard happens to drive one scenario at a time, so we
        # take the most-recently-started entry by start_tick.
        items = list(sessions.items())
        items.sort(key=lambda kv: int(getattr(kv[1], "start_tick", 0)))
        scenario_id, session = items[-1]
        return str(scenario_id), session

    def _save_current_scenario_state() -> None:
        """Best-effort: snapshot world + scenario session if a scenario is live.

        Wired into start / per-action drain / status (on victory or
        failure). Swallows save errors so a transient FS hiccup never
        bricks the running orchestrator — the log line is the only
        observable trace.
        """
        try:
            orch = app.state.penumbra.orchestrator
            runner = getattr(app.state, "scenario_runner", None)
            if runner is None:
                return
            active = _active_save_session_id(runner)
            if active is None:
                return
            scenario_id, scn_session = active
            scenario = runner.get(scenario_id)  # type: ignore[attr-defined]
            session_id = getattr(orch, "operator_session_id", None) or scenario_id
            from penumbra_operator.save_resume import save_session

            save_session(
                session_id=str(session_id),
                scenario_id=scenario_id,
                scenario_label=str(getattr(scenario, "title", scenario_id)),
                scenario_session=scn_session,  # type: ignore[arg-type]
                simulation=orch.simulation,  # type: ignore[arg-type]
                node=orch.node,  # type: ignore[arg-type]
                directory=_save_resume_dir(),  # type: ignore[arg-type]
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("operator save-resume snapshot failed")

    @app.get("/operator/scenarios")
    async def operator_scenarios_list() -> dict[str, object]:
        runner = _get_scenario_runner()
        scenarios = runner.list_scenarios()  # type: ignore[attr-defined]
        session_scores = getattr(app.state, "scenario_session_scores", {})
        return {
            "available": True,
            "scenarios": scenarios,
            "session_scores": dict(session_scores),
        }

    @app.post("/operator/scenarios/{scenario_id}/start")
    async def operator_scenarios_start(scenario_id: str) -> dict[str, object]:
        from penumbra_operator.scenarios import ScenarioError

        from penumbra_transport.events import Event

        runner = _get_scenario_runner()
        orch, _queue, ctx = _require_operator()
        try:
            info = runner.start(scenario_id, ctx)  # type: ignore[attr-defined]
        except ScenarioError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        opening = info.get("opening_event", {})
        if isinstance(opening, dict):
            opening_kind = str(opening.get("kind", "operator.scenario.start"))
            payload_raw = opening.get("payload", {})
            opening_payload = dict(payload_raw) if isinstance(payload_raw, dict) else {}
        else:
            opening_kind = "operator.scenario.start"
            opening_payload = {}
        orch.event_bus.emit(  # type: ignore[attr-defined]
            Event(
                kind=opening_kind,
                tick=int(orch.simulation.tick_counter),  # type: ignore[attr-defined]
                payload=opening_payload,
            )
        )
        # Save-resume Tier 1 trigger: snapshot the just-started scenario
        # so closing the browser before any action still surfaces a
        # banner on next boot.
        _save_current_scenario_state()
        return info

    @app.post("/operator/scenarios/{scenario_id}/abandon")
    async def operator_scenarios_abandon(scenario_id: str) -> dict[str, object]:
        runner = _get_scenario_runner()
        result = runner.abandon(scenario_id)  # type: ignore[attr-defined]
        # Save-resume cleanup: drop active.json + the per-session
        # snapshot dir so a future "Resume?" banner doesn't offer an
        # abandoned scenario back to the player.
        try:
            from penumbra_operator.save_resume import discard_active

            orch = app.state.penumbra.orchestrator
            session_id = getattr(orch, "operator_session_id", None) or scenario_id
            discard_active(
                _save_resume_dir(),  # type: ignore[arg-type]
                session_id=str(session_id),
                drop_snapshot_dir=True,
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("save-resume discard on abandon failed")
        return result

    @app.get("/operator/scenarios/{scenario_id}/status")
    async def operator_scenarios_status(scenario_id: str) -> dict[str, object]:
        from penumbra_operator.scenarios import ScenarioError

        runner = _get_scenario_runner()
        _orch, _queue, ctx = _require_operator()
        try:
            status = runner.check_status(scenario_id, ctx)  # type: ignore[attr-defined]
        except ScenarioError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        # Save-resume: when the runner detects victory or failure on
        # this poll, drop the active.json so the banner stops offering
        # a finished session. The per-session snapshot dir stays for
        # post-mortem inspection.
        if status.get("victory_met") or status.get("failure_met"):
            try:
                from penumbra_operator.save_resume import discard_active

                discard_active(_save_resume_dir())  # type: ignore[arg-type]
            except Exception:  # pragma: no cover - defensive
                logger.exception("save-resume discard on terminal status failed")
        return status

    # ── Save-resume: banner / resume / discard endpoints ──────────
    #
    # NOTE registration order: these three sit BEFORE the Tier 6
    # ``/operator/sessions/{session_id}/replay`` block so the static
    # ``/resumable`` / ``/resume`` / ``/discard`` paths are matched
    # ahead of the parametric ``{session_id}`` slot.

    @app.get("/operator/sessions/resumable")
    async def operator_sessions_resumable() -> dict[str, object]:
        """Banner metadata for the Resume-Your-Last-Session UI."""
        from penumbra_operator.save_resume import SaveResumeError, load_active

        try:
            active = load_active(_save_resume_dir())  # type: ignore[arg-type]
        except SaveResumeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if active is None:
            return {"available": False}
        return {
            "available": True,
            "session_id": active.session_id,
            "scenario_id": active.scenario_id,
            "scenario_label": active.scenario_label,
            "saved_at_tick": active.saved_at_tick,
            "saved_at_wall_iso": active.saved_at_wall_iso,
        }

    @app.post("/operator/sessions/resume")
    async def operator_sessions_resume() -> dict[str, object]:
        """Hot-swap the orchestrator's chain + simulation from active.json.

        Mirrors the ``/world/load`` hot-swap policy: the chain has no
        in-flight state so a swap is safe; the simulation snapshot is
        loaded into the live orchestrator and the operator slot + the
        scenario runner are re-seeded so the player picks up exactly
        where they left off. The clock effectively pauses while the
        player was away — the sim resumes from the saved tick, not
        from wall-clock-now.
        """
        from penumbra_operator.save_resume import (
            SaveResumeError,
            load_active,
            load_scenario_session,
            load_world_for_session,
        )

        directory = _save_resume_dir()
        try:
            active = load_active(directory)  # type: ignore[arg-type]
        except SaveResumeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if active is None:
            raise HTTPException(status_code=404, detail="no resumable session on disk")
        try:
            node, simulation = load_world_for_session(
                active.session_id,
                directory,  # type: ignore[arg-type]
            )
            scn_session = load_scenario_session(
                active.session_id,
                directory,  # type: ignore[arg-type]
            )
        except SaveResumeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        state: AppState = app.state.penumbra
        orch = state.orchestrator
        # Hot-swap the chain + simulation references on the orchestrator.
        orch.node = node
        orch.simulation = simulation
        state.simulation = simulation
        # Rebuild the operator scenario runner so the runner's session
        # table contains the restored ScenarioSession (start_tick +
        # coins_start + custom counters); the dashboard's status poll
        # will then evaluate the victory / failure clauses against the
        # restored sim instead of an empty one.
        from penumbra_operator.scenarios import ScenarioRunner

        existing_runner = getattr(app.state, "scenario_runner", None)
        if existing_runner is None:
            existing_runner = ScenarioRunner.from_directory()
            app.state.scenario_runner = existing_runner
        existing_runner._sessions[active.scenario_id] = scn_session  # type: ignore[attr-defined]
        # Restore the orchestrator's session id so subsequent saves
        # land under the same per-session directory rather than minting
        # a fresh one (and orphaning the just-restored save).
        orch.operator_session_id = active.session_id
        return {
            "resumed": True,
            "session_id": active.session_id,
            "scenario_id": active.scenario_id,
            "scenario_label": active.scenario_label,
            "tick": int(simulation.tick_counter),
            "chain_height": int(node.height),
        }

    @app.post("/operator/sessions/discard")
    async def operator_sessions_discard() -> dict[str, object]:
        """Drop ``active.json`` so the banner stops surfacing the save."""
        from penumbra_operator.save_resume import discard_active, load_active

        directory = _save_resume_dir()
        active = None
        try:
            active = load_active(directory)  # type: ignore[arg-type]
        except Exception:  # pragma: no cover - defensive
            active = None
        session_id = active.session_id if active is not None else None
        result = discard_active(
            directory,  # type: ignore[arg-type]
            session_id=session_id,
            drop_snapshot_dir=True,
        )
        return {"discarded": True, **result}

    # ── Phase 6b Tier 6 — session replay + leaderboard ────────────

    def _get_session_logger() -> object:
        """Return the orchestrator's SessionLogger, bootstrapping if needed."""
        orch = app.state.penumbra.orchestrator
        if getattr(orch, "operator_session_logger", None) is None:
            from penumbra_operator.replay import SessionLogger

            orch.operator_session_logger = SessionLogger()
        return orch.operator_session_logger

    @app.get("/operator/sessions")
    async def operator_sessions_list() -> dict[str, object]:
        """List metadata for every closed operator session on disk."""
        slog = _get_session_logger()
        sessions = slog.list_sessions()  # type: ignore[attr-defined]
        return {"available": True, "sessions": sessions, "n": len(sessions)}

    @app.get("/operator/sessions/{session_id}/replay")
    async def operator_sessions_replay(session_id: str) -> dict[str, object]:
        """Re-run a recorded session against a fresh sim; return the determinism diff."""
        from penumbra_core.agent import Agent, random_walk_policy
        from penumbra_core.arena import ArenaConfig
        from penumbra_core.economy import Market, Wallet
        from penumbra_core.logistics import LogisticsMempool
        from penumbra_core.rng import bootstrap
        from penumbra_core.simulation import Simulation, SimulationConfig
        from penumbra_crypto.dp import DPMechanism, PrivacyBudget
        from penumbra_operator.actions import OperatorContext
        from penumbra_operator.replay import (
            SessionLogError,
            scorecard_diff,
        )
        from penumbra_operator.replay import (
            replay as _do_replay,
        )

        from penumbra_transport.agent_signing import AgentKeystore

        slog = _get_session_logger()
        try:
            meta = slog.load_meta(session_id)  # type: ignore[attr-defined]
        except SessionLogError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        orch = app.state.penumbra.orchestrator
        n_agents = int(getattr(orch.simulation.config, "n_agents", 4))
        sim = Simulation.build(
            SimulationConfig(n_agents=n_agents, arena=ArenaConfig(n_nodes=15)),
            bootstrap(42),
        )
        operator_id = n_agents
        nodes = list(sim.arena.graph.nodes())
        spawn = int(nodes[0])
        operator_agent = Agent(
            id=operator_id, position=spawn, policy=random_walk_policy, home=spawn
        )
        sim.operator_agent = operator_agent
        market = Market.build(nodes=nodes, n_agents=n_agents, seed=42)
        market.wallets[operator_id] = Wallet(agent_id=operator_id, coins=100.0)
        mempool = LogisticsMempool()
        dp = DPMechanism(PrivacyBudget(epsilon=10.0))
        keystore = AgentKeystore.for_n_agents(operator_id + 1)
        fresh_ctx = OperatorContext(
            simulation=sim,
            operator_agent=operator_agent,
            operator_agent_id=operator_id,
            market=market,
            mempool=mempool,
            dp_mechanism=dp,
            keystore=keystore,
            initial_coins=100.0,
        )
        try:
            replayed = _do_replay(session_id, fresh_ctx, logger=slog)  # type: ignore[arg-type]
        except SessionLogError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        original = meta.get("final_scorecard") or {}
        diff = scorecard_diff(original, replayed)
        diff["session_id"] = session_id
        diff["scenario_id"] = meta.get("scenario_id")
        diff["parquet_path"] = str(slog.parquet_path(session_id))  # type: ignore[attr-defined]
        return diff

    # ── Interactivity surfaces (agent inspect / step / inject / export / config)

    from penumbra_transport.interactivity import (
        SUPPORTED_FORMATS,
        SUPPORTED_METRICS,
        InteractivityError,
        UnsupportedMetricError,
        agent_name_for,
        build_export_notebook,
        chart_series,
        render_csv,
        render_json,
        render_png,
        short_fingerprint,
    )

    @app.get("/agents")
    async def agents_list() -> list[dict[str, object]]:
        """Compact summary of every live agent."""
        sim_local: Simulation = app.state.penumbra.simulation
        orchestrator = app.state.penumbra.orchestrator
        market = orchestrator.market
        out: list[dict[str, object]] = []
        for agent in sim_local.agents:
            wallet = None
            if market is not None:
                wallet = market.wallets.get(int(agent.id))  # type: ignore[attr-defined]
            position_node = int(agent.position)
            xy = _node_position(sim_local, position_node)
            out.append(
                {
                    "id": int(agent.id),
                    "position": [float(xy[0]), float(xy[1])],
                    "money": float(wallet.coins) if wallet is not None else 0.0,
                    "name": agent_name_for(int(agent.id)),
                }
            )
        return out

    @app.get("/agents/{agent_id}")
    async def agent_detail(agent_id: int) -> dict[str, object]:
        """Full inspection payload for one agent."""
        sim_local: Simulation = app.state.penumbra.simulation
        if agent_id < 0 or agent_id >= len(sim_local.agents):
            raise HTTPException(status_code=404, detail=f"no agent {agent_id}")
        orchestrator = app.state.penumbra.orchestrator
        agent = sim_local.agents[agent_id]
        market = orchestrator.market
        wallet = None
        if market is not None:
            wallet = market.wallets.get(int(agent.id))  # type: ignore[attr-defined]
        runtime = app.state.penumbra.mappo_runtime
        policy_label = "mappo" if runtime is not None else "random_walk"

        position_node = int(agent.position)
        xy = _node_position(sim_local, position_node)

        # MAPPO probability vector (best-effort).
        action_distribution: list[float] = []
        last_obs_summary: dict[str, float | int] = {"mean": 0.0, "std": 0.0, "dim": 0}
        if runtime is not None:
            try:
                feats, _neighbours, _ = _build_observation_for_agent(agent_id)
                agent_net = runtime.agent_net  # type: ignore[attr-defined]
                probs = agent_net.action_probabilities(  # type: ignore[attr-defined]
                    feats,
                    temperature=runtime.temperature,  # type: ignore[attr-defined]
                )
                action_distribution = [float(p) for p in probs[0]]
                if feats.size > 0:
                    last_obs_summary = {
                        "mean": float(np.mean(feats)),
                        "std": float(np.std(feats)),
                        "dim": int(feats.size),
                    }
            except Exception:  # pragma: no cover - defensive
                logger.exception("failed to compute action distribution for %d", agent_id)
                action_distribution = []

        # Recent actions from the runtime, if any.
        recent_actions: list[dict[str, object]] = []
        if runtime is not None:
            last_actions = getattr(runtime, "last_actions", None) or []
            if 0 <= agent_id < len(last_actions):
                recent_actions.append(
                    {
                        "tick": int(sim_local.tick_counter),
                        "action": _label_action(int(last_actions[agent_id])),
                    }
                )

        # Encrypted-state size: approximate via the latest heatmap
        # sample (one shared ciphertext for the whole heatmap; per-agent
        # CKKS isn't materialised this tick, so we report the heatmap
        # ciphertext size as a proxy).
        encrypted_state_bytes = 0
        heatmap_latest = orchestrator.heatmap.latest
        if heatmap_latest is not None:
            density = getattr(heatmap_latest, "density", None)
            if density is not None:
                encrypted_state_bytes = int(getattr(density, "nbytes", 0))

        keystore = orchestrator.keystore
        kyber_fp = ""
        dilithium_fp = ""
        if 0 <= agent_id < len(keystore.keypairs):
            kp = keystore.keypairs[agent_id]
            dilithium_fp = short_fingerprint(kp.public_key)
            # No separate Kyber key per agent in the current keystore;
            # derive a stable proxy from the Dilithium public key bytes
            # so the fingerprint is deterministic per agent.
            kyber_fp = short_fingerprint(kp.public_key + b"|kyber")

        return {
            "id": int(agent.id),
            "position": [float(xy[0]), float(xy[1])],
            "money": float(wallet.coins) if wallet is not None else 0.0,
            "name": agent_name_for(int(agent.id)),
            "current_policy": policy_label,
            "recent_actions": recent_actions,
            "action_distribution": action_distribution,
            "encrypted_state_bytes": encrypted_state_bytes,
            "kyber_pk_fingerprint": kyber_fp,
            "dilithium_pk_fingerprint": dilithium_fp,
            "last_obs_summary": last_obs_summary,
        }

    @app.post("/control/inject")
    async def control_inject(payload: dict[str, object]) -> dict[str, object]:
        """Inject a synthetic event onto the orchestrator's bus."""
        from penumbra_transport.events import Event

        kind_raw = payload.get("kind", "")
        if not isinstance(kind_raw, str) or not kind_raw:
            raise HTTPException(status_code=400, detail="missing 'kind' field")
        kind = kind_raw
        sub_payload_raw = payload.get("payload", {}) or {}
        sub_payload: dict[str, object] = (
            dict(sub_payload_raw) if isinstance(sub_payload_raw, dict) else {}
        )

        orchestrator = app.state.penumbra.orchestrator
        sim_local: Simulation = app.state.penumbra.simulation
        tick = int(sim_local.tick_counter)

        event_payload: dict[str, object]
        if kind == "cpi.shock":
            ratio = float(sub_payload.get("ratio", 1.4))  # type: ignore[arg-type]
            event_payload = {"ratio": ratio, **sub_payload}
        elif kind == "garch.spike":
            magnitude = float(sub_payload.get("magnitude", 2.0))  # type: ignore[arg-type]
            event_payload = {
                "magnitude": magnitude,
                "ratio": float(sub_payload.get("ratio", magnitude)),  # type: ignore[arg-type]
                **sub_payload,
            }
        elif kind == "agent.blocked":
            if "agent_id" not in sub_payload:
                raise HTTPException(status_code=400, detail="agent.blocked requires agent_id")
            event_payload = {
                "agent_id": int(sub_payload["agent_id"]),  # type: ignore[arg-type]
                "reason": str(sub_payload.get("reason", "synthetic")),
                "until_tick": int(sub_payload.get("until_tick", tick + 30)),  # type: ignore[arg-type]
            }
        elif kind == "validator.slashed":
            if "validator_id" not in sub_payload:
                raise HTTPException(
                    status_code=400, detail="validator.slashed requires validator_id"
                )
            event_payload = {
                "validator_id": int(sub_payload["validator_id"]),  # type: ignore[arg-type]
                **sub_payload,
            }
        else:
            raise HTTPException(status_code=400, detail=f"unknown event kind: {kind!r}")

        orchestrator.event_bus.emit(  # type: ignore[attr-defined]
            Event(kind=kind, tick=tick, payload=event_payload)
        )
        return {"ok": True, "kind": kind, "tick": tick, "payload": event_payload}

    @app.get("/export/chart/{metric}")
    async def export_chart(metric: str, format: str = "json") -> Response:
        """Export a dashboard series as CSV / JSON / PNG."""
        fmt = format.lower()
        if fmt not in SUPPORTED_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"format must be one of {list(SUPPORTED_FORMATS)}",
            )
        if metric not in SUPPORTED_METRICS:
            raise HTTPException(
                status_code=404,
                detail=f"unsupported metric: {metric!r}; supported = {list(SUPPORTED_METRICS)}",
            )
        orchestrator = app.state.penumbra.orchestrator
        snapshot = orchestrator.latest_dashboard_snapshot
        trainer = app.state.penumbra.live_trainer
        training_samples = (
            list(getattr(trainer, "history", []) or []) if trainer is not None else []
        )
        extra_context = await _build_export_context(metric, app)
        try:
            payload = chart_series(
                metric,
                dashboard_snapshot=snapshot,
                training_samples=training_samples,
                chain_height=int(orchestrator.node.height),
                mempool_size=len(orchestrator.node.mempool),
                extra_context=extra_context,
            )
        except UnsupportedMetricError as exc:  # pragma: no cover - guarded above
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        filename = f"{metric}.{fmt}"
        if fmt == "csv":
            body = render_csv(payload)
            return Response(
                content=body,
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        if fmt == "json":
            body = render_json(payload)
            return Response(
                content=body,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        # png
        try:
            body = render_png(payload)
        except InteractivityError as exc:
            return _png_unavailable_response(str(exc))
        return Response(
            content=body,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/export/notebook")
    async def export_notebook(metric: str) -> Response:
        """Return a minimal .ipynb that fetches + plots ``metric``."""
        if metric not in SUPPORTED_METRICS:
            raise HTTPException(
                status_code=404,
                detail=f"unsupported metric: {metric!r}; supported = {list(SUPPORTED_METRICS)}",
            )
        body = build_export_notebook(metric)
        return Response(
            content=body,
            media_type="application/x-ipynb+json",
            headers={"Content-Disposition": f'attachment; filename="{metric}.ipynb"'},
        )

    @app.get("/config")
    async def config_get() -> dict[str, object]:
        """Return the current effective runtime configuration."""
        sim_local: Simulation = app.state.penumbra.simulation
        loop_ref: TickLoop = app.state.penumbra.loop
        orchestrator = app.state.penumbra.orchestrator

        from penumbra_learning.env import REWARD_WEIGHTS

        dp_mechanism = orchestrator.heatmap.dp_mechanism
        dp_epsilon_budget = float(dp_mechanism.budget.epsilon) if dp_mechanism is not None else 0.0
        k_anonymity_k = 0
        if orchestrator.operator_context is not None:
            defenses = getattr(orchestrator.operator_context, "defenses", None)  # type: ignore[attr-defined]
            if defenses is not None:
                k_cfg = getattr(defenses, "k_anonymity", None) or {}
                if isinstance(k_cfg, dict):
                    k_anonymity_k = int(k_cfg.get("k", 0))

        return {
            "n_agents": int(sim_local.config.n_agents),
            "match_max_ticks": int(sim_local.config.match_max_ticks),
            "tick_hz": float(loop_ref.tick_hz),
            "reward_weights": {
                "dispatch_bonus": float(REWARD_WEIGHTS.logistics_dispatch_bonus),
                "dispatch_penalty": float(REWARD_WEIGHTS.logistics_dispatch_penalty),
                "fill_rate_bonus": float(REWARD_WEIGHTS.fill_rate_bonus),
            },
            "defenses": {
                "k_anonymity_k": k_anonymity_k,
                "dp_epsilon_budget": dp_epsilon_budget,
            },
            "pty_enabled": bool(pty_enabled()),
            "mappo_loaded": bool(app.state.penumbra.mappo_runtime is not None),
        }

    @app.post("/config")
    async def config_post(payload: dict[str, object]) -> dict[str, object]:
        """Apply a partial config update; report which keys took effect."""
        applied: list[str] = []
        restart_required: list[str] = []
        reasons: dict[str, str] = {}

        loop_ref: TickLoop = app.state.penumbra.loop
        orchestrator = app.state.penumbra.orchestrator

        if "tick_hz" in payload:
            try:
                hz = float(payload["tick_hz"])  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400, detail=f"invalid tick_hz: {payload['tick_hz']!r}"
                ) from exc
            if not any(abs(hz - allowed) < 1e-6 for allowed in _allowed_tick_hz):
                raise HTTPException(
                    status_code=400,
                    detail=f"tick_hz must be one of {list(_allowed_tick_hz)}",
                )
            loop_ref.set_tick_hz(hz)
            applied.append("tick_hz")

        reward_weights_raw = payload.get("reward_weights", {})
        reward_weights: dict[str, object] = (
            dict(reward_weights_raw) if isinstance(reward_weights_raw, dict) else {}
        )
        if reward_weights:
            from penumbra_learning.env import REWARD_WEIGHTS

            mapping = {
                "dispatch_bonus": "logistics_dispatch_bonus",
                "dispatch_penalty": "logistics_dispatch_penalty",
                "fill_rate_bonus": "fill_rate_bonus",
            }
            for key, attr in mapping.items():
                if key in reward_weights:
                    try:
                        setattr(REWARD_WEIGHTS, attr, float(reward_weights[key]))  # type: ignore[arg-type]
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            status_code=400,
                            detail=f"invalid reward_weights.{key}: {reward_weights[key]!r}",
                        ) from exc
                    applied.append(f"reward_weights.{key}")

        defenses_raw = payload.get("defenses", {})
        defenses_in: dict[str, object] = (
            dict(defenses_raw) if isinstance(defenses_raw, dict) else {}
        )
        if "dp_epsilon_budget" in defenses_in:
            mechanism = orchestrator.heatmap.dp_mechanism
            try:
                new_eps = float(defenses_in["dp_epsilon_budget"])  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"invalid defenses.dp_epsilon_budget: {defenses_in['dp_epsilon_budget']!r}"
                    ),
                ) from exc
            if mechanism is None:
                restart_required.append("defenses.dp_epsilon_budget")
                reasons["defenses.dp_epsilon_budget"] = "no DP mechanism on heatmap"
            else:
                mechanism.budget.epsilon = new_eps
                applied.append("defenses.dp_epsilon_budget")

        for key in ("n_agents", "match_max_ticks"):
            if key in payload:
                restart_required.append(key)
                reasons[key] = f"{key} fixed at simulation build time"
        if "k_anonymity_k" in defenses_in:
            restart_required.append("defenses.k_anonymity_k")
            reasons["defenses.k_anonymity_k"] = "set via operator action set_k_anonymity"

        return {
            "applied": applied,
            "restart_required": restart_required,
            "reasons": reasons,
        }

    def _png_unavailable_response(reason: str) -> Response:
        body = json.dumps({"error": "png export requires matplotlib", "reason": reason})
        return Response(
            content=body.encode("utf-8"),
            media_type="application/json",
            status_code=503,
        )

    async def _build_export_context(metric: str, app_ref: FastAPI) -> dict[str, object]:
        """Lazily collect auxiliary chart context for extended metrics.

        The legacy 7 metrics use only ``dashboard_snapshot`` +
        ``training_samples`` + chain/mempool counters. Phase-bonus
        metrics (VRF leader frequency, value map, GAT attention, ...)
        need extra payloads that aren't on the snapshot. We compute
        only what the requested metric needs so a CSV/PNG of a tabular
        metric stays cheap.
        """
        ctx: dict[str, object] = {}
        orch = app_ref.state.penumbra.orchestrator
        if metric == "dp_epsilon_spent":
            dp_mech = orch.heatmap.dp_mechanism
            if dp_mech is not None:
                ctx["dp_budget"] = {
                    "epsilon_total": float(dp_mech.budget.epsilon),
                    "epsilon_spent": float(dp_mech.budget.epsilon_spent),
                    "epsilon_remaining": float(dp_mech.budget.remaining_epsilon),
                }
        elif metric == "signing_verified":
            ks = orch.keystore
            ctx["signing_stats"] = {
                "verified": int(ks.stats.verified),
                "rejected": int(ks.stats.rejected),
                "n_agents": len(ks.keypairs),
            }
        elif metric == "vrf_leader":
            node = orch.node
            recent = []
            for blk in node.chain[-12:]:
                proposer = blk.header.proposer_pubkey
                leader_idx = next(
                    (i for i, v in enumerate(node.validators) if v.bls_pubkey == proposer),
                    -1,
                )
                recent.append({"height": int(blk.header.height), "leader_index": int(leader_idx)})
            ctx["vrf_leader"] = {"recent": recent}
        elif metric == "kyber_kem":
            try:
                from penumbra_crypto.pq import kem_encapsulate, kem_keygen
            except ImportError:
                ctx["kyber_demo"] = None
            else:
                kp = kem_keygen()
                result = kem_encapsulate(kp.public_key)
                ctx["kyber_demo"] = {
                    "public_key_size": len(kp.public_key),
                    "secret_key_size": len(kp.secret_key),
                    "ciphertext_size": len(result.ciphertext),
                    "shared_secret_size": len(result.shared_secret),
                }
        elif metric == "multi_checkpoint":
            runtime = app_ref.state.penumbra.mappo_runtime
            second = getattr(app_ref.state.penumbra, "second_mappo", None)
            if runtime is None or second is None:
                ctx["multi_checkpoint"] = {"available": False}
            else:
                try:
                    import torch
                    from penumbra_learning.env import NEIGHBOURS_K, PAD_VALUE

                    sim_local: Simulation = app_ref.state.penumbra.simulation
                    feats_all: list[list[float]] = []
                    for agent in sim_local.agents:
                        obs = agent.observe(sim_local.arena, tick=sim_local.tick_counter)
                        neighbours = sorted(obs.neighbour_costs.keys())
                        goals = set(obs.visible_goals)
                        f: list[float] = []
                        for j in range(NEIGHBOURS_K):
                            if j < len(neighbours):
                                n_id = neighbours[j]
                                f.extend(
                                    [
                                        float(obs.neighbour_costs[n_id]),
                                        1.0 if n_id in goals else 0.0,
                                        1.0 if n_id in goals else 0.0,
                                    ]
                                )
                            else:
                                f.extend([PAD_VALUE, PAD_VALUE, PAD_VALUE])
                        feats_all.append(f)
                    device = runtime.agent_net.device  # type: ignore[attr-defined]
                    x = torch.tensor(feats_all, dtype=torch.float32, device=device)
                    with torch.no_grad():
                        logits_a = runtime.agent_net.actor.net(x) / float(  # type: ignore[attr-defined]
                            runtime.temperature
                        )
                        logits_b = second.actor.net(x.to(second.device)) / float(  # type: ignore[attr-defined]
                            runtime.temperature
                        )
                        logits_b = logits_b.to(device)
                        probs_a = torch.softmax(logits_a, dim=-1)
                        probs_b = torch.softmax(logits_b, dim=-1)
                    eps = 1e-9
                    kl_per_agent = (
                        probs_a * (probs_a.add(eps).log() - probs_b.add(eps).log())
                    ).sum(dim=-1)
                    agree = probs_a.argmax(dim=-1) == probs_b.argmax(dim=-1)
                    ctx["multi_checkpoint"] = {
                        "available": True,
                        "agreement_rate": float(agree.float().mean().item()),
                        "mean_kl": float(kl_per_agent.mean().item()),
                        "max_kl": float(kl_per_agent.max().item()),
                        "per_agent_kl": [float(v) for v in kl_per_agent.tolist()],
                    }
                except Exception:
                    logger.debug("multi_checkpoint context build failed", exc_info=True)
                    ctx["multi_checkpoint"] = {"available": False}
        elif metric == "value_map":
            runtime = app_ref.state.penumbra.mappo_runtime
            if runtime is None:
                ctx["value_map"] = {"available": False}
            else:
                try:
                    sim_local = app_ref.state.penumbra.simulation
                    from penumbra_learning.env import NEIGHBOURS_K, PAD_VALUE

                    vm_feats: list[np.ndarray] = []
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
                        vm_feats.append(np.asarray(f, dtype=np.float32))
                    feats_arr = np.stack(vm_feats, axis=0)
                    probs = runtime.agent_net.action_probabilities(  # type: ignore[attr-defined]
                        feats_arr, temperature=runtime.temperature
                    )
                    with np.errstate(divide="ignore", invalid="ignore"):
                        entropies = -np.where(probs > 0, probs * np.log(probs), 0).sum(axis=1)
                    cfg = runtime.agent_net.config  # type: ignore[attr-defined]
                    expected = int(cfg.obs_dim * cfg.n_agents)
                    flat = feats_arr.reshape(-1).astype(np.float32, copy=False)
                    if flat.size < expected:
                        padded = np.full((expected,), PAD_VALUE, dtype=np.float32)
                        padded[: flat.size] = flat
                        flat = padded
                    else:
                        flat = flat[:expected]
                    v_state = runtime.agent_net.value_estimate(flat)  # type: ignore[attr-defined]
                    ctx["value_map"] = {
                        "available": True,
                        "v_state": float(v_state),
                        "per_agent": [
                            {
                                "agent_id": int(i),
                                "entropy": float(entropies[i]),
                                "top_prob": float(np.max(probs[i])),
                            }
                            for i in range(len(sim_local.agents))
                        ],
                    }
                except Exception:
                    logger.debug("value_map context build failed", exc_info=True)
                    ctx["value_map"] = {"available": False}
        elif metric == "gat_attention":
            try:
                import torch
                from penumbra_learning.gat_pathfinder import GATv2Pathfinder

                sim_local = app_ref.state.penumbra.simulation
                arena = sim_local.arena
                nodes = sorted(arena.graph.nodes())
                n = len(nodes)
                node_idx = {nid: i for i, nid in enumerate(nodes)}
                goals = set(arena.goals)
                x = torch.zeros((n, 2), dtype=torch.float32)
                for i, nid in enumerate(nodes):
                    deg = arena.graph.degree(nid)
                    x[i, 0] = 1.0 if nid in goals else 0.0
                    x[i, 1] = float(deg) / 10.0
                adj = torch.zeros((n, n), dtype=torch.bool)
                edge_cost = torch.zeros((n, n), dtype=torch.float32)
                for u, v in arena.graph.edges():
                    i, j = node_idx[u], node_idx[v]
                    adj[i, j] = True
                    adj[j, i] = True
                    c = float(arena.cost_of(int(u), int(v)))
                    edge_cost[i, j] = c
                    edge_cost[j, i] = c
                for i in range(n):
                    adj[i, i] = True
                net = GATv2Pathfinder()
                with torch.no_grad():
                    _value, attn1, _attn2 = net.attention_matrices(x, adj, edge_cost)
                ctx["gat_attention"] = {
                    "available": True,
                    "node_ids": [int(nid) for nid in nodes],
                    "attention_layer1": [list(row) for row in attn1.tolist()],
                }
            except Exception:
                logger.debug("gat_attention context build failed", exc_info=True)
                ctx["gat_attention"] = {"available": False}
        elif metric == "arena_graph":
            sim_local = app_ref.state.penumbra.simulation
            arena = sim_local.arena
            nodes = list(arena.graph.nodes())
            edges = [{"u": int(u), "v": int(v)} for u, v in arena.graph.edges()]
            ctx["arena_topology"] = {"nodes": nodes, "edges": edges}
        return ctx

    def _label_action(idx: int) -> str:
        if idx < 0:
            return "random"
        try:
            from penumbra_learning.env import NEIGHBOURS_K
        except ImportError:
            return f"action_{idx}"
        if idx == NEIGHBOURS_K:
            return "stay"
        return f"neigh_{idx}"

    return app


def _node_position(simulation: Simulation, node_id: int) -> tuple[float, float]:
    """Best-effort 2D embedding for a graph node.

    The arena's graph carries no canonical coordinates, so we project
    the node id onto a stable ring so the dashboard has *something*
    to draw. Pure + deterministic.
    """
    arena = simulation.arena
    n_nodes = max(int(arena.graph.number_of_nodes()), 1)
    angle = 2.0 * np.pi * (int(node_id) % n_nodes) / float(n_nodes)
    return float(np.cos(angle)), float(np.sin(angle))


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

    from penumbra_core.arena import ArenaConfig

    # Env-tunable simulation dynamics for "watchability" at 2 Hz default.
    # Defaults are calibrated for the original 10 Hz; at 2 Hz the world
    # feels chaotic (goal migrates every 10 s, match resets every 10 min).
    # Override to slow things down for visual study.
    goal_walk_period = int(os.environ.get("PENUMBRA_GOAL_WALK_PERIOD", "20"))
    weather_prob = float(os.environ.get("PENUMBRA_WEATHER_PROB", "0.02"))
    match_max_ticks = int(os.environ.get("PENUMBRA_MATCH_MAX_TICKS", "1200"))
    config = SimulationConfig(
        arena=ArenaConfig(goal_walk_period=goal_walk_period, weather_prob=weather_prob),
        match_max_ticks=match_max_ticks,
    )
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


def _as_float(value: object) -> float:
    """Coerce an arbitrary JSON value to float, defaulting to 0.0."""
    try:
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            return float(value)
    except (TypeError, ValueError):
        pass
    return 0.0


def _as_int(value: object) -> int:
    """Coerce an arbitrary JSON value to int, defaulting to 0."""
    try:
        if isinstance(value, int | float):
            return int(value)
        if isinstance(value, str):
            return int(value)
    except (TypeError, ValueError):
        pass
    return 0


def _as_str(value: object, default: str = "") -> str:
    """Coerce an arbitrary JSON value to str."""
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _format_leaderboard_entry(
    rank_index: int,
    entry: dict[str, object],
    tier: str,
) -> dict[str, object]:
    """Flatten one bench submission for the leaderboard payload."""
    tasks_raw = entry.get("tasks", [])
    task_scores: dict[str, float] = {}
    if isinstance(tasks_raw, list):
        for t in tasks_raw:
            if isinstance(t, dict):
                task_scores[_as_str(t.get("task_id"), "")] = _as_float(t.get("score"))
    return {
        "rank": rank_index + 1,
        "filename": _as_str(entry.get("__filename")),
        "submitter": _as_str(entry.get("submitter"), "anonymous"),
        "method": _as_str(entry.get("method"), "untitled"),
        "tier": _as_str(entry.get("tier"), tier),
        "composite_score": _as_float(entry.get("composite_score")),
        "task_scores": task_scores,
        "hardware": _as_str(entry.get("hardware")),
        "pytorch_version": _as_str(entry.get("pytorch_version")),
        "penumbra_commit": _as_str(entry.get("penumbra_commit")),
        "submission_timestamp_ns": _as_int(entry.get("submission_timestamp_ns")),
    }


def _scan_bench_directory() -> list[dict[str, object]]:
    """Read every `state/bench/*.json` submission into a list of dicts.

    Each entry gains a `__filename` key for downstream linking. Files
    that fail to parse are skipped silently so a corrupted submission
    can't take down the whole leaderboard endpoint.
    """
    import json
    from pathlib import Path

    bench_dir = Path(__file__).resolve().parents[3] / "state" / "bench"
    if not bench_dir.is_dir():
        return []
    entries: list[dict[str, object]] = []
    for path in sorted(bench_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            logger.warning("could not parse bench submission %s", path.name)
            continue
        if not isinstance(data, dict):
            continue
        data["__filename"] = path.name
        entries.append(data)
    return entries


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
