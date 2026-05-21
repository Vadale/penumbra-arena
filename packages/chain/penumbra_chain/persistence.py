"""Disk persistence for the in-process chain node.

Concept taught: the chain is in-memory at runtime — fast and simple —
but a real node must survive a restart. We snapshot to a directory of
Parquet (heavy data: blocks, mempool) + JSON (small data: validator
state). Restoration reverses the process.

Why this matters
----------------
Without persistence, every `docker compose down` resets the
blockchain. With persistence, the chain becomes infrastructure: the
match-outcome history accumulates across runs, and a learner can
inspect "what happened in block 47 two weeks ago" via `pna world
load <snapshot>`.

Pedagogical security caveat
---------------------------
The on-disk format includes the validator *secret keys* in clear in
`secrets.json`. In a real deployment those keys would be wrapped in
an HSM or sealed with an OS keystore (macOS Keychain, Linux SecretService).
For Penumbra the keys live on the same host as the node anyway, so
the on-disk plaintext only matters once the host is shared — which
this single-machine project never does.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from penumbra_chain.block import Block, BlockHeader, MatchOutcome
from penumbra_chain.consensus import ValidatorIdentity, ValidatorSecret
from penumbra_chain.mempool import Mempool
from penumbra_chain.slashing import SlashingEvidence, SlashingTx


@dataclass(frozen=True, slots=True)
class NodeSnapshot:
    """In-memory representation of everything Node.save_to writes to disk."""

    validators: tuple[ValidatorIdentity, ...]
    secrets: tuple[ValidatorSecret, ...]
    chain: list[Block]
    mempool: Mempool
    active_indices: set[int]
    slashed_pubkeys: set[bytes]
    pending_slashings: list[SlashingTx]


def save_snapshot(snapshot: NodeSnapshot, directory: Path) -> None:
    """Write all node state under `directory/`."""
    directory.mkdir(parents=True, exist_ok=True)

    _write_validators(snapshot, directory / "validators.json")
    _write_secrets(snapshot, directory / "secrets.json")
    _write_state(snapshot, directory / "state.json")
    _write_blocks(snapshot.chain, directory / "blocks.parquet")
    _write_mempool(snapshot.mempool, directory / "mempool.parquet")
    _write_pending_slashings(snapshot.pending_slashings, directory / "pending_slashings.json")


def load_snapshot(directory: Path) -> NodeSnapshot:
    """Reverse `save_snapshot`."""
    if not directory.is_dir():
        raise FileNotFoundError(f"snapshot directory not found: {directory}")
    validators = _read_validators(directory / "validators.json")
    secrets = _read_secrets(directory / "secrets.json")
    state = _read_state(directory / "state.json")
    chain = _read_blocks(directory / "blocks.parquet")
    mempool = _read_mempool(directory / "mempool.parquet")
    pending = _read_pending_slashings(directory / "pending_slashings.json")
    active_indices: list[int] = state["active_indices"]  # type: ignore[assignment]
    slashed_hex: list[str] = state["slashed_pubkeys"]  # type: ignore[assignment]
    return NodeSnapshot(
        validators=validators,
        secrets=secrets,
        chain=chain,
        mempool=mempool,
        active_indices=set(active_indices),
        slashed_pubkeys={bytes.fromhex(h) for h in slashed_hex},
        pending_slashings=pending,
    )


# ── validators ────────────────────────────────────────────────────


def _write_validators(snapshot: NodeSnapshot, path: Path) -> None:
    payload = [
        {
            "bls_pubkey": v.bls_pubkey.hex(),
            "vrf_pubkey": str(v.vrf_pubkey),
            "proof_of_possession": v.proof_of_possession.hex(),
        }
        for v in snapshot.validators
    ]
    path.write_text(json.dumps(payload, indent=2))


def _read_validators(path: Path) -> tuple[ValidatorIdentity, ...]:
    payload = json.loads(path.read_text())
    return tuple(
        ValidatorIdentity(
            bls_pubkey=bytes.fromhex(item["bls_pubkey"]),
            vrf_pubkey=int(item["vrf_pubkey"]),
            proof_of_possession=bytes.fromhex(item["proof_of_possession"]),
        )
        for item in payload
    )


# ── secrets ───────────────────────────────────────────────────────


def _write_secrets(snapshot: NodeSnapshot, path: Path) -> None:
    payload = [
        {"bls_secret": s.bls_secret.hex(), "vrf_secret": str(s.vrf_secret)}
        for s in snapshot.secrets
    ]
    path.write_text(json.dumps(payload, indent=2))
    # 0o600 = only owner can read. Defence in depth even though the
    # whole project runs as the user anyway.
    path.chmod(0o600)


def _read_secrets(path: Path) -> tuple[ValidatorSecret, ...]:
    payload = json.loads(path.read_text())
    return tuple(
        ValidatorSecret(
            bls_secret=bytes.fromhex(item["bls_secret"]),
            vrf_secret=int(item["vrf_secret"]),
        )
        for item in payload
    )


# ── state (active set + slashings + height) ───────────────────────


def _write_state(snapshot: NodeSnapshot, path: Path) -> None:
    state = {
        "active_indices": sorted(snapshot.active_indices),
        "slashed_pubkeys": sorted(pk.hex() for pk in snapshot.slashed_pubkeys),
        "height": len(snapshot.chain),
    }
    path.write_text(json.dumps(state, indent=2))


def _read_state(path: Path) -> dict[str, list[int]] | dict[str, list[str]] | dict[str, int]:
    """Loads {active_indices: list[int], slashed_pubkeys: list[str], height: int}.

    Typed loosely with a union return so static checkers don't choke on
    the heterogeneous JSON payload — the callers index by known key.
    """
    payload: dict[str, object] = json.loads(path.read_text())
    return payload  # type: ignore[return-value]


# ── blocks (Parquet) ──────────────────────────────────────────────


def _write_blocks(chain: list[Block], path: Path) -> None:
    if not chain:
        # Polars requires at least one row to write parquet; write an
        # explicit empty marker file so restore knows the chain is empty.
        path.write_bytes(b"")
        return
    # We serialise the payload (list of MatchOutcomes) and the finality
    # bundle (validator_pubkeys + aggregate sig) as pickled bytes per row.
    # Parquet handles binary columns natively and keeps everything in
    # one file the user can `parquet-tools head` against for inspection.
    rows = []
    for block in chain:
        rows.append(
            {
                "height": block.header.height,
                "prev_hash": block.header.prev_hash.hex(),
                "merkle_root": block.header.merkle_root.hex(),
                "proposer_pubkey": block.header.proposer_pubkey.hex(),
                "vrf_beta": block.header.vrf_beta.hex(),
                "timestamp_ns": block.header.timestamp_ns,
                "payload_blob": pickle.dumps(block.payload),
                "slashings_blob": pickle.dumps(block.slashings),
                "validator_pubkeys_blob": pickle.dumps(block.validator_pubkeys),
                "aggregate_signature": block.aggregate_signature.hex(),
            }
        )
    frame = pl.DataFrame(rows)
    frame.write_parquet(path)


def _read_blocks(path: Path) -> list[Block]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    frame = pl.read_parquet(path)
    blocks: list[Block] = []
    for row in frame.iter_rows(named=True):
        header = BlockHeader(
            height=int(row["height"]),
            prev_hash=bytes.fromhex(row["prev_hash"]),
            merkle_root=bytes.fromhex(row["merkle_root"]),
            proposer_pubkey=bytes.fromhex(row["proposer_pubkey"]),
            vrf_beta=bytes.fromhex(row["vrf_beta"]),
            timestamp_ns=int(row["timestamp_ns"]),
        )
        # `slashings_blob` is new — pre-existing parquet files won't have
        # it. Fall back to an empty tuple to keep old snapshots loadable.
        raw_slashings = row.get("slashings_blob") if isinstance(row, dict) else None
        slashings_tuple: tuple[object, ...] = (
            tuple(pickle.loads(raw_slashings))  # noqa: S301
            if raw_slashings is not None
            else ()
        )
        block = Block(
            header=header,
            payload=tuple(pickle.loads(row["payload_blob"])),  # noqa: S301
            slashings=slashings_tuple,  # type: ignore[arg-type]
            validator_pubkeys=tuple(pickle.loads(row["validator_pubkeys_blob"])),  # noqa: S301
            aggregate_signature=bytes.fromhex(row["aggregate_signature"]),
        )
        blocks.append(block)
    return blocks


# ── mempool ───────────────────────────────────────────────────────


def _write_mempool(mempool: Mempool, path: Path) -> None:
    pending = mempool.peek()
    if not pending:
        path.write_bytes(b"")
        return
    rows = [
        {
            "match_id": o.match_id,
            "winner_agent_id": o.winner_agent_id,
            "winning_goal": o.winning_goal,
            "started_tick": o.started_tick,
            "end_tick": o.end_tick,
            "end_reason": o.end_reason,
            "arena_signature": o.arena_signature.hex(),
        }
        for o in pending
    ]
    pl.DataFrame(rows).write_parquet(path)


def _read_mempool(path: Path) -> Mempool:
    mempool = Mempool()
    if not path.exists() or path.stat().st_size == 0:
        return mempool
    frame = pl.read_parquet(path)
    for row in frame.iter_rows(named=True):
        outcome = MatchOutcome(
            match_id=int(row["match_id"]),
            winner_agent_id=row["winner_agent_id"],
            winning_goal=row["winning_goal"],
            started_tick=int(row["started_tick"]),
            end_tick=int(row["end_tick"]),
            end_reason=str(row["end_reason"]),
            arena_signature=bytes.fromhex(row["arena_signature"]),
        )
        mempool.submit(outcome)
    return mempool


# ── pending slashings ─────────────────────────────────────────────


def _write_pending_slashings(slashings: list[SlashingTx], path: Path) -> None:
    payload = [
        {
            "evidence": {
                "offender_pubkey": tx.evidence.offender_pubkey.hex(),
                "block_a_hash": tx.evidence.block_a_hash.hex(),
                "sig_a": tx.evidence.sig_a.hex(),
                "block_b_hash": tx.evidence.block_b_hash.hex(),
                "sig_b": tx.evidence.sig_b.hex(),
            },
            "height_observed": tx.height_observed,
        }
        for tx in slashings
    ]
    path.write_text(json.dumps(payload, indent=2))


def _read_pending_slashings(path: Path) -> list[SlashingTx]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    return [
        SlashingTx(
            evidence=SlashingEvidence(
                offender_pubkey=bytes.fromhex(item["evidence"]["offender_pubkey"]),
                block_a_hash=bytes.fromhex(item["evidence"]["block_a_hash"]),
                sig_a=bytes.fromhex(item["evidence"]["sig_a"]),
                block_b_hash=bytes.fromhex(item["evidence"]["block_b_hash"]),
                sig_b=bytes.fromhex(item["evidence"]["sig_b"]),
            ),
            height_observed=int(item["height_observed"]),
        )
        for item in payload
    ]
