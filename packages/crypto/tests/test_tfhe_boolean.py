"""Tests for the educational TFHE-style boolean homomorphic module."""

from __future__ import annotations

import pytest
from penumbra_crypto.educational.tfhe_boolean import (
    LWEKey,
    decrypt,
    encrypt,
    homomorphic_and,
    homomorphic_faction_overlap,
    homomorphic_nand,
    homomorphic_not,
    homomorphic_or,
    homomorphic_xor,
)


@pytest.fixture
def key() -> LWEKey:
    return LWEKey.generate()


@pytest.mark.parametrize("bit", [0, 1])
def test_encrypt_decrypt_roundtrip(key: LWEKey, bit: int) -> None:
    cipher = encrypt(key, bit)
    assert decrypt(key, cipher) == bit


def test_encrypt_rejects_bad_bit(key: LWEKey) -> None:
    with pytest.raises(ValueError, match="bit must be 0 or 1"):
        encrypt(key, 2)


def test_roundtrip_stability_over_many_encryptions(key: LWEKey) -> None:
    """Noise distribution: 200 encryptions of bit=1 must all decrypt to 1."""
    for _ in range(200):
        assert decrypt(key, encrypt(key, 1)) == 1
        assert decrypt(key, encrypt(key, 0)) == 0


@pytest.mark.parametrize(
    ("a_bit", "b_bit", "expected"),
    [(0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 0)],
)
def test_homomorphic_xor_truth_table(key: LWEKey, a_bit: int, b_bit: int, expected: int) -> None:
    a = encrypt(key, a_bit)
    b = encrypt(key, b_bit)
    result = homomorphic_xor(a, b)
    assert decrypt(key, result) == expected


@pytest.mark.parametrize(("bit", "expected"), [(0, 1), (1, 0)])
def test_homomorphic_not(key: LWEKey, bit: int, expected: int) -> None:
    cipher = encrypt(key, bit)
    result = homomorphic_not(cipher)
    assert decrypt(key, result) == expected


@pytest.mark.parametrize(
    ("a_bit", "b_bit", "expected"),
    [(0, 0, 1), (0, 1, 1), (1, 0, 1), (1, 1, 0)],
)
def test_homomorphic_nand_truth_table(key: LWEKey, a_bit: int, b_bit: int, expected: int) -> None:
    a = encrypt(key, a_bit)
    b = encrypt(key, b_bit)
    result = homomorphic_nand(key, a, b)
    assert decrypt(key, result) == expected


@pytest.mark.parametrize(
    ("a_bit", "b_bit", "expected"),
    [(0, 0, 0), (0, 1, 0), (1, 0, 0), (1, 1, 1)],
)
def test_homomorphic_and_truth_table(key: LWEKey, a_bit: int, b_bit: int, expected: int) -> None:
    a = encrypt(key, a_bit)
    b = encrypt(key, b_bit)
    result = homomorphic_and(key, a, b)
    assert decrypt(key, result) == expected


@pytest.mark.parametrize(
    ("a_bit", "b_bit", "expected"),
    [(0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 1)],
)
def test_homomorphic_or_truth_table(key: LWEKey, a_bit: int, b_bit: int, expected: int) -> None:
    a = encrypt(key, a_bit)
    b = encrypt(key, b_bit)
    result = homomorphic_or(key, a, b)
    assert decrypt(key, result) == expected


@pytest.mark.parametrize(
    ("region_a", "region_b", "same"),
    [(0, 0, 1), (1, 1, 1), (0, 1, 0), (1, 0, 0)],
)
def test_faction_overlap_returns_same_region_bit(
    key: LWEKey, region_a: int, region_b: int, same: int
) -> None:
    enc_a = encrypt(key, region_a)
    enc_b = encrypt(key, region_b)
    result = homomorphic_faction_overlap(key, enc_a, enc_b)
    assert decrypt(key, result) == same


def test_two_independent_keys_cannot_decrypt_each_other(key: LWEKey) -> None:
    """A ciphertext under key_A almost never decrypts to the same bit under key_B."""
    other = LWEKey.generate()
    # 50 trials: at least 40 should give the WRONG bit when decrypted under
    # the wrong key (some collisions exist by chance for a 1-bit message,
    # but they should be < 60% of trials).
    correct = 0
    for _ in range(50):
        cipher = encrypt(key, 1)
        if decrypt(other, cipher) == 1:
            correct += 1
    # Strict: should be near 50% (random) — at most 60%.
    assert correct < 35, f"key separation seems broken: {correct}/50 decrypted correctly"
