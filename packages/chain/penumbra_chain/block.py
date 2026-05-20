"""Block primitives.

Concept taught: a blockchain block carries (a) a previous-block hash that
gives the chain its name, (b) a Merkle root committing to the block's
payload, (c) consensus metadata (validator set, aggregate signature).
The block hash is the SHA-256 of a canonical encoding — any change
anywhere flips the hash.

The Penumbra block payload is a list of "match outcomes": one per match
completed since the previous block.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from penumbra_chain.merkle import build_root


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    """One settled match. Becomes a leaf in the block's Merkle tree."""

    match_id: int
    winner_agent_id: int | None
    winning_goal: int | None
    started_tick: int
    end_tick: int
    end_reason: str
    arena_signature: bytes  # hash of the arena topology at settlement

    def encode(self) -> bytes:
        return json.dumps(
            {
                "match_id": self.match_id,
                "winner_agent_id": self.winner_agent_id,
                "winning_goal": self.winning_goal,
                "started_tick": self.started_tick,
                "end_tick": self.end_tick,
                "end_reason": self.end_reason,
                "arena_signature": self.arena_signature.hex(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class BlockHeader:
    """Everything outside the payload. The header alone is enough for light clients."""

    height: int
    prev_hash: bytes
    merkle_root: bytes
    proposer_pubkey: bytes
    vrf_beta: bytes
    timestamp_ns: int

    def encode(self) -> bytes:
        return (
            self.height.to_bytes(8, "big")
            + self.prev_hash
            + self.merkle_root
            + self.proposer_pubkey
            + self.vrf_beta
            + self.timestamp_ns.to_bytes(16, "big")
        )

    def hash(self) -> bytes:
        return hashlib.sha256(b"penumbra-block-header:" + self.encode()).digest()


@dataclass(frozen=True, slots=True)
class Block:
    """A full block: header + payload + aggregate-sig finality bundle."""

    header: BlockHeader
    payload: tuple[MatchOutcome, ...]
    validator_pubkeys: tuple[bytes, ...] = field(default_factory=tuple)
    aggregate_signature: bytes = b""

    def hash(self) -> bytes:
        return self.header.hash()

    @classmethod
    def assemble(
        cls,
        height: int,
        prev_hash: bytes,
        proposer_pubkey: bytes,
        vrf_beta: bytes,
        timestamp_ns: int,
        payload: tuple[MatchOutcome, ...],
    ) -> Block:
        """Build a block with the Merkle root computed from the payload."""
        leaves = [outcome.encode() for outcome in payload]
        merkle_root = build_root(leaves)
        header = BlockHeader(
            height=height,
            prev_hash=prev_hash,
            merkle_root=merkle_root,
            proposer_pubkey=proposer_pubkey,
            vrf_beta=vrf_beta,
            timestamp_ns=timestamp_ns,
        )
        return cls(header=header, payload=payload)

    def with_finality(self, validator_pubkeys: tuple[bytes, ...], aggregate_sig: bytes) -> Block:
        return Block(
            header=self.header,
            payload=self.payload,
            validator_pubkeys=validator_pubkeys,
            aggregate_signature=aggregate_sig,
        )


GENESIS_PREV_HASH: bytes = bytes(32)
