"""Single-process Penumbra chain node.

Concept taught: a chain node loops:
  1. Wait for the next block window.
  2. Run leader election (VRF) over the **active** validator set.
  3. Proposer drains the mempool, builds a block, signs it.
  4. Active validators verify + sign.
  5. Aggregate-finality bundle attaches; block appended.

The active set is initially the full validator set; slashing
(`Node.slash()`) removes validators after verifiable byzantine
behaviour, and subsequent rounds skip them in elections + finality
quorum.

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
from penumbra_chain.persistence import NodeSnapshot, load_snapshot, save_snapshot
from penumbra_chain.slashing import (
    SlashingError,
    SlashingEvidence,
    SlashingTx,
    verify_evidence,
)


@dataclass(slots=True)
class Node:
    """In-process Penumbra chain node hosting N validators with an active set."""

    validators: tuple[ValidatorIdentity, ...]
    secrets: tuple[ValidatorSecret, ...]
    mempool: Mempool = field(default_factory=Mempool)
    chain: list[Block] = field(default_factory=list)
    active_indices: set[int] = field(default_factory=set)
    pending_slashings: list[SlashingTx] = field(default_factory=list)
    slashed_pubkeys: set[bytes] = field(default_factory=set)

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
        return cls(
            validators=tuple(identities),
            secrets=tuple(secrets),
            active_indices=set(range(n_validators)),
        )

    @property
    def height(self) -> int:
        return len(self.chain)

    @property
    def head_hash(self) -> bytes:
        return GENESIS_PREV_HASH if not self.chain else self.chain[-1].hash()

    @property
    def active_validators(self) -> list[ValidatorIdentity]:
        return [self.validators[i] for i in sorted(self.active_indices)]

    @property
    def active_secrets(self) -> list[ValidatorSecret]:
        return [self.secrets[i] for i in sorted(self.active_indices)]

    def submit_outcome(self, outcome: MatchOutcome) -> None:
        """Stage a completed match for inclusion in the next block."""
        self.mempool.submit(outcome)

    def slash(self, evidence: SlashingEvidence) -> SlashingTx:
        """Verify evidence and remove the offender from the active set.

        The slashing transaction is queued for inclusion in the next
        block's payload so the chain has a public record of the event.
        Re-submitting evidence against an already-slashed validator is
        idempotent — the function returns the existing tx.
        """
        if not verify_evidence(evidence):
            raise SlashingError("slashing evidence failed cryptographic verification")

        offender_idx: int | None = None
        for idx, validator in enumerate(self.validators):
            if validator.bls_pubkey == evidence.offender_pubkey:
                offender_idx = idx
                break
        if offender_idx is None:
            raise SlashingError("offender pubkey is not in our validator set")

        if evidence.offender_pubkey in self.slashed_pubkeys:
            # Crypto-audit A2/A3: previously we silently treated repeated
            # evidence as a no-op and even fabricated a fresh SlashingTx
            # with caller-supplied data, which the HTTP layer echoed back
            # as if it were canonical chain state. Refuse instead.
            raise SlashingError("validator is already slashed")
        if offender_idx not in self.active_indices:
            # Belt-and-braces: a validator not in active_indices but also
            # not in slashed_pubkeys shouldn't happen, but if it does we
            # refuse to mutate state.
            raise SlashingError("offender is not in the active validator set")

        self.active_indices.discard(offender_idx)
        self.slashed_pubkeys.add(evidence.offender_pubkey)
        tx = SlashingTx(evidence=evidence, height_observed=self.height)
        self.pending_slashings.append(tx)
        return tx

    def produce_block(self, *, max_payload: int = 64) -> Block | None:
        """Run one full block-production round. Returns the block, or None
        if there are no pending outcomes AND no pending slashings."""
        if not self.mempool and not self.pending_slashings:
            return None
        if len(self.active_indices) < 1:
            raise QuorumFailedError("no active validators left")

        active_validators = self.active_validators
        active_secrets = self.active_secrets

        seed = self.head_hash + self.height.to_bytes(8, "big")
        leader_active_idx, vrf_output = elect_leader(active_validators, active_secrets, seed)
        if not verify_leader(active_validators, seed, leader_active_idx, vrf_output):
            raise InvalidLeaderError("internal: leader proof failed self-verification")

        payload = self.mempool.drain(max_payload)
        # Snapshot pending slashings to include in this block. We do NOT
        # clear them yet — they're only cleared once the block is
        # successfully appended, mirroring the mempool's drain-and-keep
        # semantics for crash safety.
        slashings_to_include: tuple[SlashingTx, ...] = tuple(self.pending_slashings)
        block = Block.assemble(
            height=self.height,
            prev_hash=self.head_hash,
            proposer_pubkey=active_validators[leader_active_idx].bls_pubkey,
            vrf_beta=vrf_output.beta,
            timestamp_ns=time.time_ns(),
            payload=payload,
            slashings=slashings_to_include,
        )

        sigs = [
            (v.bls_pubkey, sign_block_hash(s, block.hash()))
            for v, s in zip(active_validators, active_secrets, strict=True)
        ]
        result = finalise(block.hash(), sigs, total_validators=len(active_validators))
        if result is None:
            raise QuorumFailedError("could not finalise block: insufficient valid signatures")
        pubkeys, aggregate = result
        finalised = block.with_finality(pubkeys, aggregate)
        self.chain.append(finalised)

        # Slashings are now durable in the block's payload AND in our
        # in-memory active_indices / slashed_pubkeys; safe to clear.
        self.pending_slashings.clear()

        return finalised

    # ── persistence ─────────────────────────────────────────────────

    def save_to(self, directory: object) -> None:
        """Persist the node's full state to `directory`.

        Layout:
          validators.json, secrets.json, state.json,
          blocks.parquet, mempool.parquet, pending_slashings.json
        See `penumbra_chain.persistence` for the security caveats —
        validator secret keys are written in clear at the moment.
        """
        from pathlib import Path

        snapshot = NodeSnapshot(
            validators=self.validators,
            secrets=self.secrets,
            chain=list(self.chain),
            mempool=self.mempool,
            active_indices=set(self.active_indices),
            slashed_pubkeys=set(self.slashed_pubkeys),
            pending_slashings=list(self.pending_slashings),
        )
        save_snapshot(snapshot, Path(str(directory)))

    @classmethod
    def restore_from(cls, directory: object) -> Node:
        """Reverse `save_to`. Returns a freshly-built Node with the loaded state."""
        from pathlib import Path

        snap = load_snapshot(Path(str(directory)))
        return cls(
            validators=snap.validators,
            secrets=snap.secrets,
            mempool=snap.mempool,
            chain=snap.chain,
            active_indices=snap.active_indices,
            slashed_pubkeys=snap.slashed_pubkeys,
            pending_slashings=snap.pending_slashings,
        )


class InvalidValidatorError(RuntimeError):
    """A validator's identity failed its self-consistency (PoP) check."""


class InvalidLeaderError(RuntimeError):
    """The proposer's VRF proof did not verify."""


class QuorumFailedError(RuntimeError):
    """Fewer than ⌈2/3 N⌉ validator signatures were valid."""
