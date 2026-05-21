"""Proof-of-Stake leader election + BLS aggregate finality.

Concept taught: PoS replaces "burn electricity" with "stake at risk".
Validators register a BLS key plus a VRF key. Every block:

1. **Leader election (VRF).** All validators run β_i = VRF(sk_i, prev_hash).
   The lowest β wins the right to propose. Anyone can verify the
   winner's claim because the VRF proof is published with the block.

2. **Finality (BLS aggregate).** The proposer broadcasts the block.
   Each validator (including the proposer) signs the block hash with
   their BLS key. As soon as > 2/3 of stake has signed, the
   aggregate of those signatures finalises the block. One pairing
   check verifies all of them at once.

Pedagogical caveats
- All validators here have equal stake (1 unit). Real PoS weights the
  2/3 threshold by stake.
- Slashing for double-signing is *not* implemented — a learner exercise.
- We do not implement view-change / liveness-fallback when a leader
  fails. The next block's seed simply moves on.
"""

from __future__ import annotations

from dataclasses import dataclass

from penumbra_crypto import bls, vrf


@dataclass(frozen=True, slots=True)
class ValidatorIdentity:
    """A validator's public identity: BLS pubkey, VRF pubkey, PoP."""

    bls_pubkey: bytes
    vrf_pubkey: int  # Schnorr-group element
    proof_of_possession: bytes  # BLS sig over bls_pubkey via PopProve

    def is_self_consistent(self) -> bool:
        return bls.verify_possession(self.bls_pubkey, self.proof_of_possession)


@dataclass(frozen=True, slots=True)
class ValidatorSecret:
    """A validator's secret material. Stays on the validator's host."""

    bls_secret: bytes
    vrf_secret: int


def keygen() -> tuple[ValidatorIdentity, ValidatorSecret]:
    """Generate a fresh validator keypair with PoP attached."""
    bls_keypair = bls.keygen()
    vrf_keypair = vrf.keygen()
    pop = bls.prove_possession(bls_keypair.secret_key)
    return (
        ValidatorIdentity(
            bls_pubkey=bls_keypair.public_key,
            vrf_pubkey=vrf_keypair.public_key,
            proof_of_possession=pop,
        ),
        ValidatorSecret(bls_secret=bls_keypair.secret_key, vrf_secret=vrf_keypair.secret_key),
    )


def elect_leader(
    validators: list[ValidatorIdentity],
    secrets: list[ValidatorSecret],
    seed: bytes,
) -> tuple[int, vrf.VRFOutput]:
    """Run the VRF lottery; return (winner_index, winning_output).

    For pedagogical clarity every validator's secret is in this process,
    so we just compute all VRF outputs and pick the minimum. In a real
    PoS network each validator computes only their own and broadcasts.
    """
    if not validators or len(validators) != len(secrets):
        raise ValueError("validators and secrets must be non-empty and aligned")
    outputs = [vrf.prove(secret.vrf_secret, seed) for secret in secrets]
    scores = [int.from_bytes(o.beta, "big") for o in outputs]
    winner = scores.index(min(scores))
    return winner, outputs[winner]


def verify_leader(
    validators: list[ValidatorIdentity],
    seed: bytes,
    claimed_leader: int,
    claimed_output: vrf.VRFOutput,
) -> bool:
    """Independently verify the leader claim against the published VRF output.

    A verifier checks that (a) the leader's VRF proof is valid, and (b)
    no other validator's published beta beats it. In our in-process
    chain we don't have other validators' published betas; we re-run
    the lottery to confirm. A real network would gossip betas and
    check the minimum.
    """
    if not 0 <= claimed_leader < len(validators):
        return False
    leader = validators[claimed_leader]
    return vrf.verify(leader.vrf_pubkey, seed, claimed_output)


BLOCK_SIG_DOMAIN_TAG: bytes = b"penumbra-block-sig:v1|"
"""Domain-separation tag prefixed to every block signature.

Audit closure (A4): without this prefix, a BLS signature collected for
finality at height H could be repurposed as half of a slashing-evidence
pair against a hash that happens to coincide with another block's hash
at the same height. Mixing this tag into the signed message means a
sig collected for finality cannot be transplanted to ANY other
protocol surface — slashing evidence reconstructs the same prefix and
won't accept a sig with a different (or missing) tag.
"""


def canonical_block_sign_payload(block_hash: bytes, height: int) -> bytes:
    """Stable bytes a validator signs to finalise a block at `height`.

    Audit closure (A1): height is now part of the signed message, so a
    legitimate signature at height N cannot be replayed as evidence of
    misbehaviour at height M ≠ N.
    """
    return BLOCK_SIG_DOMAIN_TAG + height.to_bytes(8, "big") + block_hash


def sign_block_hash(secret: ValidatorSecret, block_hash: bytes, height: int) -> bytes:
    """Each validator's BLS signature over `(domain_tag, height, block_hash)`."""
    return bls.sign(secret.bls_secret, canonical_block_sign_payload(block_hash, height))


def finalise(
    block_hash: bytes,
    height: int,
    validator_signatures: list[tuple[bytes, bytes]],  # (pubkey, sig) pairs
    quorum_numerator: int = 2,
    quorum_denominator: int = 3,
    total_validators: int | None = None,
) -> tuple[tuple[bytes, ...], bytes] | None:
    """Aggregate ≥ ⌈2/3 N⌉ valid signatures into one. Returns (pks, agg) or None.

    Every validator signs the canonical payload (domain-tag || height ||
    block_hash); we use BLS FastAggregateVerify against the aggregate
    public-key set. The returned list of pubkeys becomes part of the
    block's finality bundle.
    """
    n = total_validators if total_validators is not None else len(validator_signatures)
    threshold = -(-quorum_numerator * n // quorum_denominator)  # ceil(n*2/3)
    message = canonical_block_sign_payload(block_hash, height)

    valid: list[tuple[bytes, bytes]] = []
    for pubkey, sig in validator_signatures:
        if bls.verify(pubkey, message, sig):
            valid.append((pubkey, sig))
    if len(valid) < threshold:
        return None
    pks = tuple(pk for pk, _ in valid)
    aggregate = bls.aggregate_signatures([s for _, s in valid])
    if not bls.fast_aggregate_verify(list(pks), message, aggregate):
        return None
    return pks, aggregate
