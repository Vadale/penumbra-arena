"""Rényi DP accountant for DP-SGD — the (ε, δ) you can actually quote.

Concept taught: when you train a model with DP-SGD (Abadi et al. 2016),
each gradient step is a Sampled Gaussian Mechanism. You CAN'T add up
ε's linearly — that bound is loose. Rényi DP composes additively in
α, and at the end you convert the curve to (ε, δ) via the tightest
known bound (Canonne-Kamath-Steinke 2020).

Penumbra's accountant uses 118 Rényi orders for a tighter ε estimate
than the canonical 12-order Opacus-style grid; this script reproduces
that comparison.

Runs standalone:
    uv run python examples/05_rdp_dp_sgd_accountant.py

Exercises `packages/learning/penumbra_learning/federated_dp.py`
directly — no MAPPO, no trainer, just the accountant.
"""

from __future__ import annotations

from penumbra_learning.federated_dp import RDPAccountant


def main() -> None:
    print("=== DP-SGD scenario: σ=1.1, q=0.01, T=1000, δ=1e-5 ===\n")
    # Canonical DP-SGD numbers from the Abadi et al. paper.
    sigma = 1.1  # noise multiplier
    q = 0.01  # subsampling rate (batch / dataset)
    steps = 1000
    target_delta = 1e-5

    # --- Sparse 12-order grid (legacy Opacus-style) ---
    sparse_orders = [1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 16.0, 32.0, 64.0]
    sparse = RDPAccountant(orders=list(sparse_orders))
    for _ in range(steps):
        sparse.step(noise_multiplier=sigma, sample_rate=q)
    eps_sparse = sparse.epsilon(target_delta=target_delta)

    # --- Dense 118-order grid (Penumbra default) ---
    dense = RDPAccountant()  # uses the dense default
    for _ in range(steps):
        dense.step(noise_multiplier=sigma, sample_rate=q)
    eps_dense = dense.epsilon(target_delta=target_delta)

    print(f"sparse grid ({len(sparse.orders):>3} orders) → ε = {eps_sparse:.4f}")
    print(f"dense  grid ({len(dense.orders):>3} orders) → ε = {eps_dense:.4f}")
    print(f"tightening from denser grid: {eps_sparse - eps_dense:.4f}")
    assert eps_dense < eps_sparse, "denser grid must yield a tighter bound"

    # --- The σ ↔ ε tradeoff: louder noise → smaller ε (more privacy) ---
    print("\n=== The σ ↔ ε tradeoff (q=0.01, T=500, δ=1e-5) ===\n")
    print(f"{'σ':>6} {'ε':>10}")
    print("-" * 18)
    for sigma_try in (0.3, 0.5, 0.7, 1.0, 1.5, 3.0, 8.0):
        acc = RDPAccountant()
        for _ in range(500):
            acc.step(noise_multiplier=sigma_try, sample_rate=q)
        eps = acc.epsilon(target_delta=target_delta)
        print(f"{sigma_try:>6.2f} {eps:>10.4f}")

    print("\n=== How to read this ===")
    print("- ε is the DP budget — smaller = more private.")
    print("- σ = noise / sensitivity. Bigger σ = bigger noise = smaller ε.")
    print("- A model trained with σ=0.3 is barely private. σ=3.0 is solid.")
    print("- For more decimal precision on ε, use the dense grid (default).")
    print("\nSource: packages/learning/penumbra_learning/federated_dp.py")


if __name__ == "__main__":
    main()
