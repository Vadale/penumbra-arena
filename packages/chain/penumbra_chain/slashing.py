"""On-chain slashing for byzantine validators.

Concept taught: a slashable offence in PoS is one that is **publicly
verifiable** — anyone with the protocol-defined evidence can produce a
proof, and any honest node will accept it. The canonical offence is
*equivocation*: the same validator signing two distinct blocks at the
same height. The (validator_pubkey, sig_a, hash_a, sig_b, hash_b)
tuple IS the proof. There's no need for a trial — the cryptographic
fact is enough.

Penumbra's slashing is the minimal version:
- The evidence is verified (both sigs are valid; the hashes differ;
  conceptually both came from the same height — we don't track per-
  block height in the evidence because it's implicit in the consensus
  context, so we just require hash_a != hash_b).
- The offending validator is removed from the *active set*.
- The slashing event is recorded in the next block's payload so it's
  visible to future readers of the chain.

This is the on-chain consequence the `pna byzantine-cmd` demo has
been pointing at — without the slashing, the equivocation detection
is just a curiosity.
"""

from __future__ import annotations

from dataclasses import dataclass

from penumbra_crypto import bls


@dataclass(frozen=True, slots=True)
class SlashingEvidence:
    """Two BLS sigs by the same validator on distinct block hashes."""

    offender_pubkey: bytes
    block_a_hash: bytes
    sig_a: bytes
    block_b_hash: bytes
    sig_b: bytes


@dataclass(frozen=True, slots=True)
class SlashingTx:
    """A slashing transaction as carried in a block's payload."""

    evidence: SlashingEvidence
    height_observed: int  # the block height at which we observed the offence


def is_valid_evidence(evidence: SlashingEvidence) -> bool:
    """Reject obviously-malformed evidence before going to crypto."""
    return (
        evidence.block_a_hash != evidence.block_b_hash
        and len(evidence.offender_pubkey) == bls.PUBLIC_KEY_BYTES
        and len(evidence.sig_a) == bls.SIGNATURE_BYTES
        and len(evidence.sig_b) == bls.SIGNATURE_BYTES
    )


def verify_evidence(evidence: SlashingEvidence) -> bool:
    """Cryptographically verify both sigs under the offender's pubkey."""
    if not is_valid_evidence(evidence):
        return False
    return bls.verify(
        evidence.offender_pubkey, evidence.block_a_hash, evidence.sig_a
    ) and bls.verify(evidence.offender_pubkey, evidence.block_b_hash, evidence.sig_b)


class SlashingError(RuntimeError):
    """Raised when slashing evidence is malformed or unverifiable."""
