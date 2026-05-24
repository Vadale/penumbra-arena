"""Tests for the Loopix-style onion mix-net."""

from __future__ import annotations

import secrets

import pytest
from penumbra_crypto import mix_net


def _build_relays(n: int) -> list[mix_net.MixNode]:
    return [
        mix_net.MixNode(node_id=f"r{i}".encode(), secret_key=secrets.token_bytes(32))
        for i in range(n)
    ]


def test_mix_net_delivers_through_multiple_hops() -> None:
    relays = _build_relays(5)
    msg = b"hello from alice"
    delivered, delays = mix_net.route_message(msg, relays, receiver_id=b"bob")
    assert delivered == msg
    assert len(delays) == 5


def test_mix_net_tampered_layer_rejected() -> None:
    relays = _build_relays(3)
    onion = mix_net.wrap(b"x", relays, receiver_id=b"r")
    tampered = bytearray(onion.payload)
    tampered[5] ^= 0xFF
    with pytest.raises(mix_net.MixNetError):
        mix_net.peel(relays[0], bytes(tampered))


def test_mix_net_impostor_relay_rejected() -> None:
    relays = _build_relays(3)
    onion = mix_net.wrap(b"x", relays, receiver_id=b"r")
    impostor = mix_net.MixNode(node_id=relays[0].node_id, secret_key=secrets.token_bytes(32))
    with pytest.raises(mix_net.MixNetError):
        mix_net.peel(impostor, onion.payload)


def test_mix_net_each_layer_peels_one() -> None:
    relays = _build_relays(4)
    onion = mix_net.wrap(b"payload", relays, receiver_id=b"final")
    current = onion.payload
    for i, node in enumerate(relays):
        peeled = mix_net.peel(node, current)
        if i < len(relays) - 1:
            assert not peeled.is_final
            current = peeled.inner
        else:
            assert peeled.is_final
            assert peeled.inner == b"payload"


def test_mix_net_demo() -> None:
    d = mix_net.demo()
    assert d["available"] is True
    assert d["honest_delivers"] is True
    assert d["tampered_layer_rejected"] is True
    assert d["impostor_relay_rejected"] is True
