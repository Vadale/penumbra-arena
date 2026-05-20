"""Single-process Penumbra chain node.

Concept taught: a chain node loops:
  1. Wait for the next block window.
  2. Run leader election (VRF).
  3. Proposer drains the mempool, builds a block, signs it.
  4. Other validators verify + sign.
  5. Aggregate-finality bundle attaches; block appended.

In Penumbra there is only one process, but it hosts N=4-7 validators by
default. Each loop is straight-line code — no networking, no view
changes. This keeps the consensus dynamics fully inspectable in the
attacker console.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from penumbra_chain.block import GENESIS_PREV_HASH, Block, MatchOutcome
from penumbra_chain.consensus import (
    ValidatorIdentity,
    ValidatorSecret,
    elect_leader,
    finalise,
    keygen,
    sign_block_hash,
    verify_leader,
)
from penumbra_chain.mempool import Mempool


@dataclass(slots=True)
class Node:
    """In-process Penumbra chain node hosting N validators.

    Genesis is at construction; chain stores blocks in memory (a real
    node would persist to DuckDB; left as a follow-up).
    """

    validators: tuple[ValidatorIdentity, ...]
    secrets: tuple[ValidatorSecret, ...]
    mempool: Mempool = field(default_factory=Mempool)
    chain: list[Block] = field(default_factory=list)

    @classmethod
    def boot(cls, *, n_validators: int = 4) -> Node:
        """Generate `n_validators` validators and bootstrap a fresh node."""
        identities: list[ValidatorIdentity] = []
        secrets: list[ValidatorSecret] = []
        for _ in range(n_validators):
            ident, secret = keygen()
            if not ident.is_self_consistent():
                raise InvalidValidatorError("freshly-generated PoP failed self-check")
            identities.append(ident)
            secrets.append(secret)
        return cls(validators=tuple(identities), secrets=tuple(secrets))

    @property
    def height(self) -> int:
        return len(self.chain)

    @property
    def head_hash(self) -> bytes:
        return GENESIS_PREV_HASH if not self.chain else self.chain[-1].hash()

    def submit_outcome(self, outcome: MatchOutcome) -> None:
        """Stage a completed match for inclusion in the next block."""
        self.mempool.submit(outcome)

    def produce_block(self, *, max_payload: int = 64) -> Block | None:
        """Run one full block-production round. Returns the block, or None
        if there are no pending outcomes."""
        if not self.mempool:
            return None
        seed = self.head_hash + self.height.to_bytes(8, "big")
        leader_idx, vrf_output = elect_leader(list(self.validators), list(self.secrets), seed)
        if not verify_leader(list(self.validators), seed, leader_idx, vrf_output):
            raise InvalidLeaderError("internal: leader proof failed self-verification")

        payload = self.mempool.drain(max_payload)
        block = Block.assemble(
            height=self.height,
            prev_hash=self.head_hash,
            proposer_pubkey=self.validators[leader_idx].bls_pubkey,
            vrf_beta=vrf_output.beta,
            timestamp_ns=time.time_ns(),
            payload=payload,
        )

        # Collect BLS signatures from every validator. In a real network
        # this would be gossiped; here we sign in-process for everyone.
        sigs = [
            (v.bls_pubkey, sign_block_hash(s, block.hash()))
            for v, s in zip(self.validators, self.secrets, strict=True)
        ]
        result = finalise(block.hash(), sigs, total_validators=len(self.validators))
        if result is None:
            raise QuorumFailedError("could not finalise block: insufficient valid signatures")
        pubkeys, aggregate = result
        finalised = block.with_finality(pubkeys, aggregate)
        self.chain.append(finalised)
        return finalised


class InvalidValidatorError(RuntimeError):
    """A validator's identity failed its self-consistency (PoP) check."""


class InvalidLeaderError(RuntimeError):
    """The proposer's VRF proof did not verify."""


class QuorumFailedError(RuntimeError):
    """Fewer than ⌈2/3 N⌉ validator signatures were valid."""
