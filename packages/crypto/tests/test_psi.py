"""Tests for OPRF-based private set intersection."""

from __future__ import annotations

from penumbra_crypto import psi


def test_psi_recovers_full_intersection() -> None:
    alice = [b"a", b"b", b"c", b"d"]
    bob = [b"c", b"d", b"e", b"f"]
    server = psi.server_setup(bob)
    state, blinded = psi.client_blind(alice)
    evaluated = psi.server_evaluate(server, blinded)
    unblinded = psi.client_unblind(state, evaluated)
    intersection = psi.intersect(alice, unblinded, server.published)
    assert set(intersection) == {b"c", b"d"}


def test_psi_empty_intersection() -> None:
    alice = [b"x", b"y"]
    bob = [b"p", b"q"]
    server = psi.server_setup(bob)
    state, blinded = psi.client_blind(alice)
    evaluated = psi.server_evaluate(server, blinded)
    unblinded = psi.client_unblind(state, evaluated)
    assert psi.intersect(alice, unblinded, server.published) == []


def test_psi_full_intersection() -> None:
    items = [f"item-{i}".encode() for i in range(10)]
    server = psi.server_setup(items)
    state, blinded = psi.client_blind(items)
    evaluated = psi.server_evaluate(server, blinded)
    unblinded = psi.client_unblind(state, evaluated)
    intersection = psi.intersect(items, unblinded, server.published)
    assert set(intersection) == set(items)


def test_psi_demo() -> None:
    d = psi.demo()
    assert d["available"] is True
    assert d["honest_correct"] is True
    assert d["intersection_size"] == d["expected_intersection_size"]
    assert d["tampered_published_intersection_size"] == 0
