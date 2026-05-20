"""`pna` — Penumbra adversarial CLI.

Usage
-----
    pna --help
    pna replay
    pna linkability --agents 5 --matches 30
    pna dp-reconstruct --bits 64 --queries 400
    pna byzantine
    pna timing
"""

from __future__ import annotations

import typer

from penumbra_attacker.attacks import (
    byzantine,
    dp_reconstruction,
    linkability,
    replay,
    timing_sidechannel,
)

app = typer.Typer(help="Penumbra adversarial console — try each attack and see what defends.")


@app.command()
def replay_cmd() -> None:
    """Replay a Dilithium signature with and without tick-counter binding."""
    result = replay.demo()
    typer.echo(f"naive replay succeeded: {result.naive_succeeded}")
    typer.echo(f"with tick-counter binding, replay succeeded: {result.with_tick_counter_succeeded}")


@app.command()
def linkability_cmd(
    agents: int = typer.Option(5, "--agents", help="number of distinct agents"),
    matches: int = typer.Option(20, "--matches", help="matches per agent"),
) -> None:
    """De-anonymise an agent from movement patterns; show how noise breaks the link."""
    result = linkability.demo(n_agents=agents, n_matches=matches)
    typer.echo(f"naive accuracy: {result.naive_accuracy:.2%}")
    typer.echo(f"with noise accuracy: {result.with_noise_accuracy:.2%}")


@app.command(name="dp-reconstruct")
def dp_reconstruct_cmd(
    bits: int = typer.Option(32, "--bits"),
    queries: int = typer.Option(200, "--queries"),
    noise: float = typer.Option(0.1, "--noise"),
) -> None:
    """Dinur-Nissim row reconstruction against unaccounted DP releases."""
    result = dp_reconstruction.demo(n_bits=bits, n_queries=queries, noise_scale=noise)
    typer.echo(f"recovered bit accuracy: {result.recovered_bit_accuracy:.2%}")


@app.command()
def byzantine_cmd() -> None:
    """Sign two conflicting blocks at the same height and detect the equivocation."""
    result = byzantine.demo()
    typer.echo(f"equivocation proof verified: {result.equivocation_detected}")


@app.command(name="timing")
def timing_cmd(samples: int = typer.Option(20, "--samples")) -> None:
    """Time CKKS `add` over sparse vs dense ciphertexts; t-test the difference."""
    result = timing_sidechannel.demo(n_samples=samples)
    typer.echo(f"sparse median: {result.sparse_median_us:.1f} μs")
    typer.echo(f"dense  median: {result.dense_median_us:.1f} μs")
    typer.echo(f"Welch's t-statistic: {result.welch_t_statistic:.3f}")
    typer.echo(f"p-value: {result.p_value:.4f}")


# Re-export the typer app under the conventional name so the entry point works.
if __name__ == "__main__":
    app()
