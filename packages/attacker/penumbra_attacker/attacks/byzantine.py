"""Byzantine validator: signing two conflicting blocks at the same height.

How the attack works
--------------------
A malicious validator who controls one of the N keypairs can sign two
*different* blocks at the same height. If they propose conflicting
blocks to two halves of the network, both halves think their block
is "finalised" — a fork.

Why real PoS chains resist it
-----------------------------
Slashing. Validators stake collateral; if anyone produces a publicly-
verifiable proof that the same key signed two conflicting blocks at
the same height, their stake is burned (and the chain rolls back the
shorter fork). The proof is just (sig_a, block_a_hash, sig_b,
block_b_hash) — anyone can verify it.

Why Penumbra's chain doesn't yet
--------------------------------
Penumbra Phase 3 implements only the *detection* primitive (this
attack module). The slashing layer is a learner exercise — it's just
a single-block transaction that includes the equivocation proof.

Try it
------
>>> from penumbra_attacker.attacks import byzantine
>>> result = byzantine.demo()
>>> result.equivocation_detected
True
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from penumbra_crypto import bls


@dataclass(frozen=True, slots=True)
class ByzantineResult:
    """Outcome of one equivocation demo."""

    block_a_signed: bool
    block_b_signed: bool
    equivocation_detected: bool


def demo() -> ByzantineResult:
    """Produce two conflicting signatures and verify the detection check."""
    keypair = bls.keygen()

    # The validator signs block A at height 42.
    block_a = hashlib.sha256(b"penumbra-block-42:branch-A").digest()
    sig_a = bls.sign(keypair.secret_key, block_a)
    assert bls.verify(keypair.public_key, block_a, sig_a)

    # The SAME validator signs a DIFFERENT block at the SAME height.
    block_b = hashlib.sha256(b"penumbra-block-42:branch-B").digest()
    sig_b = bls.sign(keypair.secret_key, block_b)
    assert bls.verify(keypair.public_key, block_b, sig_b)

    # Detection: both sigs verify under the same pubkey for two distinct
    # messages at the same height. That IS the equivocation proof.
    detected = (
        bls.verify(keypair.public_key, block_a, sig_a)
        and bls.verify(keypair.public_key, block_b, sig_b)
        and block_a != block_b
    )

    return ByzantineResult(
        block_a_signed=True,
        block_b_signed=True,
        equivocation_detected=detected,
    )
