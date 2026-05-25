"""Differential privacy with a hard budget.

Concept taught: differential privacy is *only* privacy when the total
ε you ever spend is bounded. The mechanism here refuses to noise after
the budget runs out — that's the line between "we say it's DP" and
"it actually is".

Runs standalone:
    uv run python examples/01_dp_budget_walkthrough.py

No backend, no dashboard. Just `packages/crypto/penumbra_crypto/dp.py`
exercised against a stream of toy queries.
"""

from __future__ import annotations

import numpy as np
from penumbra_crypto.dp import BudgetExceededError, DPMechanism, PrivacyBudget


def main() -> None:
    # A tiny ε_total = 1.0 budget so we exhaust it fast and see the
    # over-the-line behaviour. In Penumbra's live stack the default is
    # ε_total = 1000.0 to give the dashboard hours of headroom.
    budget = PrivacyBudget(epsilon=1.0)
    rng = np.random.default_rng(seed=42)  # deterministic for this demo
    dp = DPMechanism(budget=budget, rng=rng)

    # Toy underlying value: the true (private) revenue we want to release.
    true_revenue = 1_234_567.89

    print("=== Releasing the revenue with shrinking ε ===\n")
    print(f"true value (never shown to the client): {true_revenue:,.2f}\n")
    print(f"{'release':>8} {'ε spent':>9} {'ε left':>9} {'noised value':>15}")
    print("-" * 48)

    epsilon_per_release = 0.1
    sensitivity = 1.0  # how much one customer's data can move the total
    release = 0
    while True:
        release += 1
        try:
            noised = dp.laplace(true_revenue, sensitivity=sensitivity, epsilon=epsilon_per_release)
        except BudgetExceededError:
            print(f"{release:>8} {'—':>9} {'0.000':>9} {'REFUSED (budget exhausted)':>27}")
            break
        print(
            f"{release:>8} "
            f"{budget.epsilon - budget.remaining_epsilon:>9.3f} "
            f"{budget.remaining_epsilon:>9.3f} "
            f"{noised:>15,.2f}"
        )

    print("\n=== What this means ===")
    print(
        f"- Each release added Laplace noise scaled by sensitivity/ε = {sensitivity / epsilon_per_release}."
    )
    print("- After ε_total ran out, the mechanism *refuses* further releases.")
    print("- An attacker who hammered us with queries can't get a denoised mean")
    print("  by averaging — the mechanism stopped giving them data.")
    print("\n=== Try this ===")
    print("- Re-run with epsilon_per_release = 0.5 → fewer releases, more noise per release.")
    print("- Re-run with sensitivity = 100.0 → more noise (release looks like garbage).")
    print("- The class lives at packages/crypto/penumbra_crypto/dp.py:100.")


if __name__ == "__main__":
    main()
