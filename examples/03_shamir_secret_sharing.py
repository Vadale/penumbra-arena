"""Shamir secret sharing — t-of-n threshold reconstruction.

Concept taught: any threshold-t scheme is just polynomial interpolation
over a finite field. You hide the secret as p(0) of a random degree-(t-1)
polynomial; any t evaluation points reconstruct it exactly; any (t-1)
reveal NOTHING (information-theoretic, not computational).

Runs standalone:
    uv run python examples/03_shamir_secret_sharing.py

This is the educational pure-Python implementation in
`packages/crypto/penumbra_crypto/educational/shamir.py`. Every step
is visible in source; nothing is delegated to a black-box library.
"""

from __future__ import annotations

import random

from penumbra_crypto.educational import shamir


def main() -> None:
    print("=== (n=5, t=3) Shamir secret sharing demo ===\n")

    secret = 0xCAFEBABE  # any int < field modulus
    n, t = 5, 3
    print(f"secret  = 0x{secret:08X}")
    print(f"n shares: {n}")
    print(f"t needed: {t}\n")

    # Step 1: dealer splits.
    shares = shamir.split(secret, n=n, t=t)
    print("share i → (x, y)  [y looks random]")
    for s in shares:
        print(f"  share {s.x}: y = {s.y}")

    # Step 2: any t shares reconstruct the secret exactly.
    print(f"\n--- reconstruct from t={t} shares (any 3 of 5) ---")
    recovered = shamir.reconstruct(shares[:t])
    print(f"reconstructed: 0x{recovered:08X}")
    assert recovered == secret, "Shamir reconstruction must be exact"
    print("OK — t-of-n recovers the secret.")

    # Step 3: t-1 shares reveal nothing. We can compute "a value" but
    # it's just a random field element, no relation to the real secret.
    print(f"\n--- reconstruct from t-1={t - 1} shares (this MUST be garbage) ---")
    fake = shamir.reconstruct(shares[: t - 1])
    print(f"(t-1) attempt: 0x{fake:08X}")
    assert fake != secret, "(t-1)-of-n MUST be statistically independent of the secret"
    print("OK — (t-1) recovery is unrelated to the true secret.")

    # Step 4: pick a different random subset of t shares — same answer.
    rng = random.Random(7)
    subset = rng.sample(shares, t)
    recovered_alt = shamir.reconstruct(subset)
    assert recovered_alt == secret
    print("\n--- any random subset of size t reconstructs the same secret ---")
    print(f"subset xs: {[s.x for s in subset]}")
    print(f"reconstructed: 0x{recovered_alt:08X}  (matches secret ✓)")

    # Step 5: bonus — degree-2 polynomial sketch for the visual learner.
    # (We can't easily eyeball the actual polynomial because the field
    # is 256-bit, but the shape is the same as in textbook examples.)
    print("\n=== What's happening underneath ===")
    print(f"- The dealer picks a random degree-{t - 1} polynomial p(x)")
    print("  with p(0) = secret. Coefficients are random in the field.")
    print("- Share i is (i, p(i)).")
    print("- Lagrange interpolation over t shares recovers p(0).")
    print("- The field modulus is a 256-bit prime — see shamir.field_modulus().")

    print("\n=== Try this ===")
    print("- Increase to (n=10, t=7) — same code, larger party set.")
    print("- Read the impl: ~95 LOC, every step is plain Python arithmetic.")
    print("- Source: packages/crypto/penumbra_crypto/educational/shamir.py")


if __name__ == "__main__":
    main()
