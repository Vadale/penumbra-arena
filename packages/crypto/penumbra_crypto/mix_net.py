"""Loopix-style onion mix-net (in-process pedagogical implementation).

Concept taught: a single hop between Alice and Bob trivially reveals
who is talking to whom — even with end-to-end encryption, the network
metadata is fully exposed. A *mix network* breaks the link by routing
each message through N relays; each relay PEELS one encryption layer
and forwards. Combined with cover traffic + per-hop delays, this hides
the sender → receiver mapping from a global adversary.

Loopix (Piotrowska et al. 2017) is the modern academic mix-net design
underpinning Nym and several Tor-alternative experiments. Our
in-process module implements the *core invariant*: every relay sees
only one encryption layer, and only the final relay learns the payload.

Wire format per layer
---------------------
    onion_i = E_{K_i}(next_hop_id || delay_i || onion_{i+1})

where K_i is derived from a per-hop secret key shared with the sender
(in production: via Sphinx packets + ECDH; here: a pre-shared symmetric
key for pedagogy). The innermost onion ships the actual payload to the
receiver and a `RECEIVER` marker for next_hop_id.

Pedagogical simplifications
---------------------------
- No cover traffic / loop traffic. Real Loopix injects "drop messages"
  + "loop messages" to defeat traffic analysis.
- No per-packet replay tags. Production needs a Bloom filter per relay.
- The PRG is SHA-256-CTR for dependency-freeness, not AES-CTR.
- "Delay" is a recorded scalar; the in-process exec layer respects it
  by sorting outbound queues, no real sleeping.

References
----------
- Piotrowska et al. "The Loopix Anonymity System" (USENIX 2017).
- Danezis, Goldberg. "Sphincs: Compact and provably secure hybrid
  encryption" (S&P 2009) — the wire format Loopix builds on.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets as _secrets
from dataclasses import dataclass
from typing import Final

RECEIVER_MARKER: Final[bytes] = b"\xff\xff\xff\xffRECEIVER"


class MixNetError(RuntimeError):
    """Raised on tampered onions, unknown hops, or malformed payloads."""


@dataclass(frozen=True, slots=True)
class MixNode:
    """A relay node: a stable identifier + a pre-shared per-sender key."""

    node_id: bytes
    secret_key: bytes


@dataclass(frozen=True, slots=True)
class WrappedOnion:
    """A complete onion packet ready to ship to the first hop."""

    first_hop: bytes
    payload: bytes


@dataclass(frozen=True, slots=True)
class PeeledLayer:
    """Result of one relay's peel: next-hop info + the inner payload."""

    next_hop: bytes
    delay_ms: int
    inner: bytes
    is_final: bool


def _kdf(secret_key: bytes, *, length: int) -> bytes:
    """Derive a per-layer keystream from the relay secret key (SHA-256 CTR)."""
    blocks = (length + 31) // 32
    out = bytearray()
    for i in range(blocks):
        out.extend(
            hashlib.sha256(b"penumbra-mix-prg|" + secret_key + i.to_bytes(4, "big")).digest()
        )
    return bytes(out[:length])


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b, strict=True))


def _seal(secret_key: bytes, plaintext: bytes) -> bytes:
    """Encrypt one layer with an authenticated tag (PRG-XOR + HMAC-style MAC)."""
    keystream = _kdf(secret_key, length=len(plaintext))
    cipher = _xor(plaintext, keystream)
    tag = hashlib.sha256(b"penumbra-mix-mac|" + secret_key + cipher).digest()[:16]
    return cipher + tag


def _open(secret_key: bytes, blob: bytes) -> bytes:
    """Verify the tag and decrypt one layer. Raises on MAC mismatch."""
    if len(blob) < 16:
        raise MixNetError("ciphertext too short to contain a tag")
    cipher, tag = blob[:-16], blob[-16:]
    expected_tag = hashlib.sha256(b"penumbra-mix-mac|" + secret_key + cipher).digest()[:16]
    if not hmac.compare_digest(tag, expected_tag):
        raise MixNetError("layer MAC mismatch — onion tampered with")
    keystream = _kdf(secret_key, length=len(cipher))
    return _xor(cipher, keystream)


def _encode_header(next_hop: bytes, delay_ms: int) -> bytes:
    """Fixed-size layer header: 32-byte next_hop || 4-byte delay."""
    if len(next_hop) > 32:
        raise MixNetError("next_hop id must be ≤32 bytes")
    padded = next_hop.ljust(32, b"\x00")
    return padded + delay_ms.to_bytes(4, "big")


def _decode_header(blob: bytes) -> tuple[bytes, int, bytes]:
    if len(blob) < 36:
        raise MixNetError("layer too short to contain a header")
    next_hop_padded = blob[:32]
    next_hop = next_hop_padded.rstrip(b"\x00")
    delay_ms = int.from_bytes(blob[32:36], "big")
    inner = blob[36:]
    return next_hop, delay_ms, inner


def wrap(
    payload: bytes,
    route: list[MixNode],
    *,
    receiver_id: bytes,
    delays_ms: list[int] | None = None,
) -> WrappedOnion:
    """Wrap ``payload`` for delivery via ``route`` ending at ``receiver_id``.

    Builds the onion inside-out: start from the receiver payload and
    layer encryption keys in reverse order.
    """
    if not route:
        raise MixNetError("route must contain at least one mix node")
    if delays_ms is None:
        delays_ms = [_secrets.randbelow(50) + 10 for _ in route]
    if len(delays_ms) != len(route):
        raise MixNetError("delays_ms length must match route length")

    # Innermost layer: final-hop header pointing to RECEIVER_MARKER.
    inner = _encode_header(RECEIVER_MARKER, 0) + payload
    inner = _seal(route[-1].secret_key, inner)

    # Wrap successive layers from second-to-last back to first.
    for i in range(len(route) - 2, -1, -1):
        header = _encode_header(route[i + 1].node_id, delays_ms[i + 1])
        inner = _seal(route[i].secret_key, header + inner)

    return WrappedOnion(first_hop=route[0].node_id, payload=inner)


def peel(node: MixNode, blob: bytes) -> PeeledLayer:
    """Relay-side peel: verify + decrypt + parse one onion layer."""
    decrypted = _open(node.secret_key, blob)
    next_hop, delay_ms, inner = _decode_header(decrypted)
    is_final = hmac.compare_digest(next_hop, RECEIVER_MARKER)
    return PeeledLayer(next_hop=next_hop, delay_ms=delay_ms, inner=inner, is_final=is_final)


def route_message(
    payload: bytes, route: list[MixNode], *, receiver_id: bytes
) -> tuple[bytes, list[int]]:
    """End-to-end driver: wrap, peel through every relay, return final payload + delays."""
    onion = wrap(payload, route, receiver_id=receiver_id)
    current_blob = onion.payload
    delays_traversed: list[int] = []
    for i, node in enumerate(route):
        peeled = peel(node, current_blob)
        delays_traversed.append(peeled.delay_ms)
        if peeled.is_final:
            if i != len(route) - 1:
                raise MixNetError("hit RECEIVER before final hop")
            return peeled.inner, delays_traversed
        current_blob = peeled.inner
    raise MixNetError("route exhausted without reaching receiver")


# ── demo ──────────────────────────────────────────────────────────


def demo(*, n_relays: int = 4) -> dict[str, object]:
    """Build a 4-hop mix route, ship a message, then tamper-test."""
    n_relays = max(2, min(int(n_relays), 8))
    relays = [
        MixNode(node_id=f"relay-{i}".encode(), secret_key=_secrets.token_bytes(32))
        for i in range(n_relays)
    ]
    msg = b"penumbra: the dispatcher knows nothing"
    delivered, delays = route_message(msg, relays, receiver_id=b"receiver")
    honest_ok = delivered == msg

    # Tamper test: flip a byte in the onion before it enters the route.
    onion = wrap(msg, relays, receiver_id=b"receiver")
    tampered_blob = bytearray(onion.payload)
    tampered_blob[0] ^= 0xFF
    tampered_caught = False
    try:
        peel(relays[0], bytes(tampered_blob))
    except MixNetError:
        tampered_caught = True

    # Wrong-key test: a relay holds a different key than the sender used.
    impostor = MixNode(node_id=relays[0].node_id, secret_key=_secrets.token_bytes(32))
    impostor_caught = False
    try:
        peel(impostor, onion.payload)
    except MixNetError:
        impostor_caught = True

    return {
        "available": True,
        "algorithm": "Loopix-style onion mix-net (educational)",
        "n_relays": n_relays,
        "payload_bytes": len(msg),
        "onion_bytes": len(onion.payload),
        "per_hop_overhead_bytes": (len(onion.payload) - len(msg)) // max(1, n_relays),
        "honest_delivers": bool(honest_ok),
        "delays_ms": delays,
        "tampered_layer_rejected": tampered_caught,
        "impostor_relay_rejected": impostor_caught,
        "notes": (
            "Pre-shared symmetric keys for pedagogy; production "
            "Loopix uses Sphinx-style ECDH key derivation per packet."
        ),
    }
