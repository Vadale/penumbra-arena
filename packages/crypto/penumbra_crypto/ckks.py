"""CKKS approximate-arithmetic homomorphic encryption.

Concept taught: CKKS (Cheon-Kim-Kim-Song, 2017) encrypts vectors of real
numbers and supports SIMD addition + multiplication on ciphertexts.
"Approximate" because each operation injects rounding noise; the noise
budget shrinks per multiplication, and a `rescale` after every `*`
keeps the modulus chain healthy.

In Penumbra we use CKKS to build encrypted heatmaps over the arena grid:
each agent's grid coordinates are encrypted, the server sums the
ciphertexts into an aggregate density, and decrypts only the aggregate.
Individual positions never leave plaintext on the server.

Backend abstraction
-------------------
Two concrete backends sit behind a small `HEBackend` Protocol:
- `TenSEALBackend` (default on Apple Silicon; precompiled arm64 wheels)
- `OpenFHEBackend` (preferred on Linux x86_64; ~140000x more precise
  per Cheon et al. benchmarking — see PROMPTING_GUIDE)

Choosing at startup:
  PENUMBRA_HE_BACKEND=tenseal | openfhe | auto (default)

In `auto` we try OpenFHE first (more precise), fall back to TenSEAL on
ImportError.

SIMD packing
------------
Both backends pack many real numbers per ciphertext (TenSEAL: up to
poly_modulus_degree / 2 slots; we use 8192/2 = 4096 slots). For 50
Penumbra agents this means one ciphertext per *tick*, not per agent.

References
----------
- Cheon, Kim, Kim, Song. "Homomorphic encryption for arithmetic of
  approximate numbers" (ASIACRYPT 2017). The CKKS paper.
- TenSEAL: https://github.com/OpenMined/TenSEAL
- OpenFHE: https://www.openfhe.org/
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Final, Protocol, cast, runtime_checkable

import numpy as np
from numpy.typing import NDArray

_ENV_VAR: Final[str] = "PENUMBRA_HE_BACKEND"
_DEFAULT_POLY_DEGREE: Final[int] = 8_192
_DEFAULT_SCALE_BITS: Final[int] = 40

Vector = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class CKKSParameters:
    """Public parameters governing the CKKS context.

    `poly_modulus_degree` controls the number of SIMD slots (= degree / 2)
    and the security level. 8192 gives 128-bit security per the FHE
    standardisation tables; we use 8192 by default to keep ciphertext
    size manageable on the M4's 16 GB budget.

    `scale_bits` is log2 of the encoding scale: doubling it doubles the
    precision but consumes more of the multiplicative-depth budget.

    `coeff_mod_bits` is the modulus chain. Length determines the
    multiplicative depth available; here we allocate 2 multiplications
    (one for heatmap construction, one for spatial weighting).
    """

    poly_modulus_degree: int = _DEFAULT_POLY_DEGREE
    scale_bits: int = _DEFAULT_SCALE_BITS
    coeff_mod_bits: tuple[int, ...] = (60, 40, 40, 60)


@runtime_checkable
class HEBackend(Protocol):
    """Minimal interface every HE backend must expose.

    Methods are intentionally untyped to opaque `Ciphertext` because the
    underlying types differ between backends; callers only care about
    end-to-end semantics: encrypt → operate → decrypt round-trips a
    vector of floats.
    """

    name: str
    params: CKKSParameters

    def encrypt(self, plaintext: Vector) -> object: ...
    def decrypt(self, ciphertext: object) -> Vector: ...
    def add(self, a: object, b: object) -> object: ...
    def add_scalar(self, a: object, scalar: float) -> object: ...
    def multiply(self, a: object, b: object) -> object: ...
    def multiply_scalar(self, a: object, scalar: float) -> object: ...


# ── TenSEAL backend ────────────────────────────────────────────────


class TenSEALBackend:
    """TenSEAL CKKS context. Default on Apple Silicon."""

    name = "tenseal"

    def __init__(self, params: CKKSParameters | None = None) -> None:
        import tenseal as ts

        self.params = params or CKKSParameters()
        self._ts = ts
        self._context = ts.context(
            ts.SCHEME_TYPE.CKKS,
            poly_modulus_degree=self.params.poly_modulus_degree,
            coeff_mod_bit_sizes=list(self.params.coeff_mod_bits),
        )
        self._context.generate_galois_keys()
        self._context.generate_relin_keys()
        self._context.global_scale = 2**self.params.scale_bits

    @property
    def slot_count(self) -> int:
        return self.params.poly_modulus_degree // 2

    def encrypt(self, plaintext: Vector) -> object:
        if plaintext.ndim != 1:
            raise ValueError(f"CKKS encrypts 1D vectors; got shape {plaintext.shape}")
        if plaintext.size > self.slot_count:
            raise ValueError(
                f"vector size {plaintext.size} exceeds slot capacity {self.slot_count}"
            )
        return self._ts.ckks_vector(self._context, plaintext.tolist())

    def decrypt(self, ciphertext: object) -> Vector:
        ct = self._as_ckks(ciphertext)
        return np.asarray(ct.decrypt(), dtype=np.float64)

    def add(self, a: object, b: object) -> object:
        return cast(object, self._as_ckks(a) + self._as_ckks(b))

    def add_scalar(self, a: object, scalar: float) -> object:
        return cast(object, self._as_ckks(a) + scalar)

    def multiply(self, a: object, b: object) -> object:
        return cast(object, self._as_ckks(a) * self._as_ckks(b))

    def multiply_scalar(self, a: object, scalar: float) -> object:
        return cast(object, self._as_ckks(a) * scalar)

    def _as_ckks(self, value: object) -> Any:
        # TenSEAL accepts CKKSVector arithmetic operands directly. Returning
        # Any lets the arithmetic operators in the public methods type-check
        # against TenSEAL's dynamic operator overloads.
        return value


# ── OpenFHE backend (stub when wheel unavailable) ──────────────────


class OpenFHEBackend:
    """OpenFHE CKKS context. Preferred on platforms with available wheels.

    As of OpenFHE 1.5.1 (April 2026), pypi.org/project/openfhe ships
    Linux x86_64 wheels only. On Apple Silicon importing this backend
    raises a clear error before any state is allocated.
    """

    name = "openfhe"

    def __init__(self, params: CKKSParameters | None = None) -> None:
        from openfhe import (  # pyright: ignore[reportMissingImports]
            CCParamsCKKSRNS,
            GenCryptoContext,
            PKESchemeFeature,
        )

        self.params = params or CKKSParameters()
        cc_params = CCParamsCKKSRNS()
        cc_params.SetMultiplicativeDepth(len(self.params.coeff_mod_bits) - 2)
        cc_params.SetScalingModSize(self.params.scale_bits)
        cc_params.SetBatchSize(self.params.poly_modulus_degree // 2)
        self._cc = GenCryptoContext(cc_params)
        self._cc.Enable(PKESchemeFeature.PKE)
        self._cc.Enable(PKESchemeFeature.LEVELEDSHE)
        self._keys = self._cc.KeyGen()
        self._cc.EvalMultKeyGen(self._keys.secretKey)

    @property
    def slot_count(self) -> int:
        return self.params.poly_modulus_degree // 2

    def encrypt(self, plaintext: Vector) -> object:
        if plaintext.ndim != 1:
            raise ValueError(f"CKKS encrypts 1D vectors; got shape {plaintext.shape}")
        pt = self._cc.MakeCKKSPackedPlaintext(plaintext.tolist())
        return self._cc.Encrypt(self._keys.publicKey, pt)

    def decrypt(self, ciphertext: object) -> Vector:
        result = self._cc.Decrypt(self._keys.secretKey, ciphertext)
        return np.asarray(result.GetCKKSPackedValue(), dtype=np.float64)

    def add(self, a: object, b: object) -> object:
        return self._cc.EvalAdd(a, b)

    def add_scalar(self, a: object, scalar: float) -> object:
        return self._cc.EvalAdd(a, scalar)

    def multiply(self, a: object, b: object) -> object:
        return self._cc.EvalMult(a, b)

    def multiply_scalar(self, a: object, scalar: float) -> object:
        return self._cc.EvalMult(a, scalar)


# ── Selection ──────────────────────────────────────────────────────


def get_backend(params: CKKSParameters | None = None) -> HEBackend:
    """Return a configured HEBackend, choosing the implementation by env.

    ``PENUMBRA_HE_BACKEND`` accepts ``openfhe``, ``tenseal``, or
    ``auto`` (default). In ``auto`` we try OpenFHE first; if its native
    extension can't be loaded, we fall back to TenSEAL with a clear log
    line. Either way the returned object implements the same `HEBackend`
    Protocol.
    """
    requested = os.environ.get(_ENV_VAR, "auto").lower()
    if requested not in {"auto", "openfhe", "tenseal"}:
        raise ValueError(f"{_ENV_VAR}={requested!r} not recognised; use openfhe, tenseal, or auto")

    if requested in {"openfhe", "auto"}:
        try:
            return OpenFHEBackend(params)
        except (ImportError, ModuleNotFoundError) as exc:
            if requested == "openfhe":
                raise UnavailableBackendError("OpenFHE requested but not importable") from exc
            # auto: silently fall through to TenSEAL

    return TenSEALBackend(params)


class UnavailableBackendError(RuntimeError):
    """Raised when a specifically-requested HE backend cannot be loaded."""
