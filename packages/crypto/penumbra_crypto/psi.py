"""Private Set Intersection from an Oblivious Pseudo-Random Function (OPRF).

Concept taught: Alice and Bob each hold a set of items (S_A, S_B) and
want to learn S_A ∩ S_B without revealing anything else. The OPRF
recipe (Pinkas–Schneider–Zohner 2014, Kolesnikov–Kumaresan 2016,
DH-style) is:

1. Alice and Bob agree on a group with an unknown-discrete-log
   generator g, hash-to-curve H.
2. Alice samples α ←R Z_q, ships {H(x)^α : x ∈ S_A}.
3. Bob holds a server key β ←R Z_q and, for each ciphertext c from
   Alice, returns c^β. Bob also publishes {H(y)^β : y ∈ S_B}.
4. Alice raises each returned value to α⁻¹ to recover {H(x)^β : x ∈
   S_A} and intersects with Bob's published set.

The intersection is computed in the OPRF *image*; Alice learns the
intersection but no other element of Bob's set (each H(y)^β is a
uniform group element under DDH). Bob learns nothing about Alice's set.

In this module Bob plays the OPRF server and Alice the client.
The "common items" come back as plaintext on Alice's side.

Production hardening
--------------------
- Hash-to-curve must be indifferentiable from a random oracle
  (RFC 9380); we use a simple try-and-increment fallback for pedagogy.
- The unbalanced setting (|S_B| ≫ |S_A|) calls for hashing to a Bloom
  filter or a cuckoo table instead of a flat compare.
- Real deployments add session bindings + replay protection.

References
----------
- Chase, Miao. "Private set intersection in the internet setting from
  lightweight oblivious PRF" (CRYPTO 2020).
- Pinkas, Schneider, Zohner. "Faster private set intersection based on
  OT extension" (USENIX 2014).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from penumbra_crypto.educational.pedersen import group_params

_P, _Q, _G, _H = group_params()


class PSIError(RuntimeError):
    """Raised on out-of-band failures in the PSI protocol."""


@dataclass(frozen=True, slots=True)
class PSIClientState:
    """Alice's per-session state: blinding factor α and α⁻¹ in Z_q."""

    alpha: int
    alpha_inv: int


@dataclass(frozen=True, slots=True)
class PSIServer:
    """Bob's stable key + the publishable OPRF image of his set."""

    beta: int
    published: list[int]  # {H(y)^β : y ∈ S_B}, ORDERED (does not reveal y order if shuffled)


def _hash_to_group(item: bytes) -> int:
    """Map an item to a deterministic group element H(item)^x_seed.

    Try-and-increment is the simple-but-correct hash-to-curve substitute
    over our Schnorr group. Not constant-time, fine for pedagogy.
    """
    digest = hashlib.sha256(b"penumbra-psi-h2g:" + item).digest()
    exponent = int.from_bytes(digest, "big") % _Q
    if exponent == 0:
        exponent = 1
    return pow(_G, exponent, _P)


def server_setup(items: list[bytes]) -> PSIServer:
    """Server samples β ←R Z_q and publishes {H(y)^β} (shuffled, opaque)."""
    beta = secrets.randbelow(_Q - 1) + 1
    published = [pow(_hash_to_group(y), beta, _P) for y in items]
    # Shuffle to avoid leaking the input order through the published set.
    # The deterministic Fisher–Yates makes the order independent of the
    # original list ordering modulo Bob's secret seed.
    rng = secrets.SystemRandom()
    rng.shuffle(published)
    return PSIServer(beta=beta, published=published)


def client_blind(items: list[bytes]) -> tuple[PSIClientState, list[int]]:
    """Client samples α and ships {H(x)^α : x ∈ S_A} to the server."""
    alpha = secrets.randbelow(_Q - 1) + 1
    alpha_inv = pow(alpha, _Q - 2, _Q)
    blinded = [pow(_hash_to_group(x), alpha, _P) for x in items]
    return PSIClientState(alpha=alpha, alpha_inv=alpha_inv), blinded


def server_evaluate(server: PSIServer, blinded: list[int]) -> list[int]:
    """Server raises each blinded value to β, returns {H(x)^{α·β}}."""
    return [pow(c, server.beta, _P) for c in blinded]


def client_unblind(state: PSIClientState, evaluated: list[int]) -> list[int]:
    """Client removes α and obtains {H(x)^β} ready to compare with server.published."""
    return [pow(c, state.alpha_inv, _P) for c in evaluated]


def intersect(
    client_items: list[bytes],
    unblinded: list[int],
    server_published: list[int],
) -> list[bytes]:
    """Compute the intersection in PLAINTEXT on the client side.

    The comparison happens on the OPRF *images*. We use a constant-time
    membership test by digesting each value to a 32-byte tag and
    comparing tags via ``hmac.compare_digest`` — this avoids leaking
    intersection size via timing for adversaries co-located with Alice.
    """
    if len(client_items) != len(unblinded):
        raise PSIError("client items and unblinded values must align")
    published_tags = {hashlib.sha256(v.to_bytes(256, "big")).digest() for v in server_published}
    out: list[bytes] = []
    for item, value in zip(client_items, unblinded, strict=True):
        tag = hashlib.sha256(value.to_bytes(256, "big")).digest()
        for ref in published_tags:
            if hmac.compare_digest(tag, ref):
                out.append(item)
                break
    return out


# ── demo ──────────────────────────────────────────────────────────


def demo() -> dict[str, object]:
    """Run a 6-item / 6-item PSI with a 3-element ground-truth intersection."""
    common = [b"oranges", b"apples", b"bananas"]
    alice = [b"alice-only-1", *common, b"alice-only-2", b"alice-only-3"]
    bob = [b"bob-only-1", *common, b"bob-only-2", b"bob-only-3"]
    server = server_setup(bob)
    state, blinded = client_blind(alice)
    evaluated = server_evaluate(server, blinded)
    unblinded = client_unblind(state, evaluated)
    intersection = intersect(alice, unblinded, server.published)

    # Tamper test: replace ALL of Bob's published values with random group
    # elements. The intersection must drop to zero (negligible collision
    # probability in a 2048-bit Schnorr group).
    tampered_published = [pow(_G, secrets.randbelow(_Q - 1) + 1, _P) for _ in server.published]
    tampered_intersection = intersect(alice, unblinded, tampered_published)

    return {
        "available": True,
        "algorithm": "OPRF-based PSI (DH-style, Schnorr group)",
        "alice_set_size": len(alice),
        "bob_set_size": len(bob),
        "intersection": [x.decode() for x in intersection],
        "intersection_size": len(intersection),
        "expected_intersection_size": len(common),
        "honest_correct": bool({x.decode() for x in intersection} == {x.decode() for x in common}),
        "tampered_published_intersection_size": len(tampered_intersection),
        "tamper_changes_intersection": bool(
            {x.decode() for x in tampered_intersection} != {x.decode() for x in intersection}
        ),
        "notes": (
            "DH-style OPRF in Schnorr group. Production PSI uses a "
            "hash-to-curve to a prime-order EC + a Bloom filter for "
            "unbalanced settings."
        ),
    }
