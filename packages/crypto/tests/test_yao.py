"""Tests for Yao garbled circuits + millionaires comparator."""

from __future__ import annotations

import pytest
from penumbra_crypto.educational import yao


@pytest.mark.parametrize(
    ("kind", "a", "b", "expected"),
    [
        ("AND", 0, 0, 0),
        ("AND", 1, 0, 0),
        ("AND", 1, 1, 1),
        ("OR", 0, 0, 0),
        ("OR", 0, 1, 1),
        ("OR", 1, 1, 1),
        ("XOR", 0, 0, 0),
        ("XOR", 0, 1, 1),
        ("XOR", 1, 1, 0),
    ],
)
def test_garbled_gate_truth_table(kind: yao.GateKind, a: int, b: int, expected: int) -> None:
    w_a = yao.WireLabels(yao._random_label(), yao._random_label())
    w_b = yao.WireLabels(yao._random_label(), yao._random_label())
    gate = yao.garble_gate(kind, w_a, w_b)
    label = yao.evaluate_gate(
        gate,
        w_a.one if a else w_a.zero,
        w_b.one if b else w_b.zero,
        a_bit_hint=a,
        b_bit_hint=b,
    )
    assert yao.decode_output(gate.output_pair, label) == expected


def test_garbled_gate_wrong_label_rejected() -> None:
    w_a = yao.WireLabels(yao._random_label(), yao._random_label())
    w_b = yao.WireLabels(yao._random_label(), yao._random_label())
    gate = yao.garble_gate("AND", w_a, w_b)
    with pytest.raises(ValueError, match="MAC mismatch"):
        yao.evaluate_gate(gate, yao._random_label(), w_b.one, a_bit_hint=1, b_bit_hint=1)


@pytest.mark.parametrize(
    ("a", "b"),
    [(0, 0), (3, 5), (100, 99), (12345, 12345), (65535, 0), (0, 65535)],
)
def test_millionaires_returns_correct_relation(a: int, b: int) -> None:
    result = yao.compare_millionaires(a, b)
    if a < b:
        assert result["relation"] == "a_less"
    elif a > b:
        assert result["relation"] == "b_less"
    else:
        assert result["relation"] == "equal"


def test_millionaires_rejects_negative_or_oversize() -> None:
    with pytest.raises(ValueError, match=r"-?[0-9]"):
        yao.compare_millionaires(-1, 0)
    with pytest.raises(ValueError, match=r"-?[0-9]"):
        yao.compare_millionaires(2**16, 0)


def test_yao_demo() -> None:
    d = yao.demo()
    assert d["available"] is True
    assert d["honest_comparator_correct"] is True
    assert d["tampered_label_decodes_to_valid_output"] is False
