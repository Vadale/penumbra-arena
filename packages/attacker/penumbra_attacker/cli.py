"""`pna` — Penumbra adversarial CLI.

Concept taught: how to expose a catalogue of attacks behind one
discoverable verb-style CLI — so a learner can run an attack, read
its docstring, and see the defence in the same shell session
without context-switching to documentation.

Usage
-----
    pna --help
    pna replay-cmd
    pna linkability-cmd --agents 5 --matches 30
    pna dp-reconstruct --bits 64 --queries 400
    pna byzantine-cmd
    pna timing
    pna world save <name> | load <name> | list
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import typer

from penumbra_attacker.attacks import (
    byzantine,
    dp_reconstruction,
    linkability,
    replay,
    snark_forgery,
    timing_sidechannel,
)

app = typer.Typer(help="Penumbra adversarial console — try each attack and see what defends.")
world_app = typer.Typer(help="Snapshot the running chain to disk and back.")
app.add_typer(world_app, name="world")

_DEFAULT_API = os.environ.get("PENUMBRA_API_URL", "http://localhost:8000")


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
def byzantine_cmd(
    submit_self_slash: bool = typer.Option(
        False,
        "--submit-self-slash",
        help=(
            "Also call POST /chain/_demo/self-slash on the live node to "
            "remove validator 0 from the active set via real on-chain slashing."
        ),
    ),
    api: str = typer.Option(_DEFAULT_API, "--api", help="backend base URL"),
) -> None:
    """Sign two conflicting blocks at the same height and detect the equivocation.

    With --submit-self-slash, ALSO submit a self-slash demo to the live
    node (gated server-side by PENUMBRA_DEMO_SELF_SLASH=1) so you see
    the on-chain consequence: the validator drops out of the active set.
    """
    result = byzantine.demo()
    typer.echo(f"equivocation proof verified: {result.equivocation_detected}")
    if not submit_self_slash:
        return
    try:
        outcome = _http_post(_api_url(api, "/chain/_demo/self-slash"), {})
    except urllib.error.HTTPError as exc:
        typer.echo(
            f"slash submission rejected: {exc.read().decode('utf-8', errors='replace')}",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except urllib.error.URLError as exc:
        typer.echo(f"could not reach {api}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"slashed validator: {outcome['slashed']}")
    typer.echo(f"observed at chain height: {outcome['height_observed']}")
    typer.echo(f"active validators: {outcome['active_validators']} / {outcome['total_validators']}")


@app.command(name="timing")
def timing_cmd(samples: int = typer.Option(20, "--samples")) -> None:
    """Time CKKS `add` over sparse vs dense ciphertexts; t-test the difference."""
    result = timing_sidechannel.demo(n_samples=samples)
    typer.echo(f"sparse median: {result.sparse_median_us:.1f} μs")
    typer.echo(f"dense  median: {result.dense_median_us:.1f} μs")
    typer.echo(f"Welch's t-statistic: {result.welch_t_statistic:.3f}")
    typer.echo(f"p-value: {result.p_value:.4f}")


@app.command(name="snark-forge")
def snark_forge_cmd() -> None:
    """Try to forge a Groth16 proof; verifier should reject the forgery."""
    result = snark_forgery.demo()
    typer.echo(f"honest proof accepted: {result.honest_proof_accepted}")
    typer.echo(f"random-bytes forgery accepted: {result.random_forge_accepted}")
    typer.echo(
        f"replay with tampered inputs accepted: {result.replay_with_tampered_inputs_accepted}"
    )


# ── world snapshot subcommands ────────────────────────────────────


def _api_url(base: str, path: str) -> str:
    return base.rstrip("/") + path


def _http_post(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 — only localhost api
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _http_get(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


@world_app.command("save")
def world_save(
    name: str = typer.Argument(..., help="snapshot name (alphanumerics, -, _)"),
    api: str = typer.Option(_DEFAULT_API, "--api", help="backend base URL"),
) -> None:
    """Snapshot the running chain to state/snapshots/<name>/chain/."""
    try:
        result = _http_post(_api_url(api, "/world/save"), {"name": name})
    except urllib.error.URLError as exc:
        typer.echo(f"could not reach {api}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"saved snapshot '{result['name']}' at {result['path']}")
    typer.echo(f"chain height: {result['height']}")


@world_app.command("load")
def world_load(
    name: str = typer.Argument(..., help="snapshot name"),
    api: str = typer.Option(_DEFAULT_API, "--api"),
) -> None:
    """Replace the running chain with snapshot <name>'s chain."""
    try:
        result = _http_post(_api_url(api, "/world/load"), {"name": name})
    except urllib.error.HTTPError as exc:
        typer.echo(
            f"backend rejected load: {exc.read().decode('utf-8', errors='replace')}", err=True
        )
        raise typer.Exit(code=1) from exc
    except urllib.error.URLError as exc:
        typer.echo(f"could not reach {api}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"loaded snapshot '{result['name']}'")
    typer.echo(f"chain height: {result['height']}")
    typer.echo(f"active validators: {result['active_validators']}")
    typer.echo(f"slashed: {result['slashed']}")


@world_app.command("list")
def world_list(api: str = typer.Option(_DEFAULT_API, "--api")) -> None:
    """List every available snapshot under state/snapshots/."""
    try:
        result = _http_get(_api_url(api, "/world/list"))
    except urllib.error.URLError as exc:
        typer.echo(f"could not reach {api}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    snapshots = result.get("snapshots", [])
    if not snapshots:
        typer.echo("(no snapshots)")
        return
    for entry in snapshots:  # type: ignore[union-attr]
        typer.echo(f"  {entry['name']:<24} height={entry['chain_height']:<6}  {entry['path']}")


# Re-export the typer app under the conventional name so the entry point works.
if __name__ == "__main__":
    app()
