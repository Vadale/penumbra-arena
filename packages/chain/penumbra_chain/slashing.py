"""On-chain slashing for byzantine validators.

Concept taught: a slashable offence in PoS is one that is **publicly
verifiable** — anyone with the protocol-defined evidence can produce a
proof, and any honest node will accept it. The canonical offence is
*equivocation*: the same validator signing two distinct blocks at the
same height. The evidence is the (pubkey, height, hash_a, sig_a,
hash_b, sig_b) tuple; the cryptographic fact alone is the proof.

Audit closures
--------------
- **A1 — height binding**: the signed message includes the height (via
  `consensus.canonical_block_sign_payload`). A stale signature from
  height N cannot be replayed as "equivocation at height M ≠ N".
- **A4 — domain separation**: the signed message also carries the
  protocol-wide tag `penumbra-block-sig:v1|`. A sig collected for
  finality cannot be repurposed for any other protocol surface (e.g.
  cross-protocol message confusion).
- **A2/A3 — already-slashed**: `Node.slash()` raises rather than
  silently no-op-ing or fabricating fresh `SlashingTx` from caller
  data.

The on-chain consequence the `pna byzantine-cmd` demo has been
pointing at — without slashing, the equivocation detection is a
curiosity.
"""

from __future__ import annotations

from dataclasses import dataclass

from penumbra_crypto import bls

from penumbra_chain.consensus import canonical_block_sign_payload


@dataclass(frozen=True, slots=True)
class SlashingEvidence:
    """Two BLS sigs by the same validator on distinct block hashes at the same height."""

    offender_pubkey: bytes
    height: int  # the height both sigs were cast at
    block_a_hash: bytes
    sig_a: bytes
    block_b_hash: bytes
    sig_b: bytes


@dataclass(frozen=True, slots=True)
class SlashingTx:
    """A slashing transaction as carried in a block's payload."""

    evidence: SlashingEvidence
    height_observed: int  # the chain height at which we observed the offence


def is_valid_evidence(evidence: SlashingEvidence) -> bool:
    """Reject obviously-malformed evidence before going to crypto."""
    return (
        evidence.block_a_hash != evidence.block_b_hash
        and evidence.height >= 0
        and len(evidence.offender_pubkey) == bls.PUBLIC_KEY_BYTES
        and len(evidence.sig_a) == bls.SIGNATURE_BYTES
        and len(evidence.sig_b) == bls.SIGNATURE_BYTES
    )


def verify_evidence(evidence: SlashingEvidence) -> bool:
    """Cryptographically verify both sigs over the canonical block-sign payload.

    Each sig is checked against the same message a validator would have
    cast during finality at `evidence.height`: domain-tag || height ||
    block_hash. A sig that omits the tag or uses a different height
    will not verify.
    """
    if not is_valid_evidence(evidence):
        return False
    payload_a = canonical_block_sign_payload(evidence.block_a_hash, evidence.height)
    payload_b = canonical_block_sign_payload(evidence.block_b_hash, evidence.height)
    return bls.verify(evidence.offender_pubkey, payload_a, evidence.sig_a) and bls.verify(
        evidence.offender_pubkey, payload_b, evidence.sig_b
    )


class SlashingError(RuntimeError):
    """Raised when slashing evidence is malformed or unverifiable."""
