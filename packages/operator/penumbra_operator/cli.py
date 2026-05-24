"""`pno` — Penumbra Operator CLI.

Concept taught: the CLI is a thin wrapper around the server-side
``/operator/*`` endpoints. Every command POSTs JSON to the running
backend and prints the structured response. Validation happens
server-side; the CLI's only job is ergonomics + transport.

Usage
-----
    pno --help
    pno enable
    pno move 12
    pno buy 0 3
    pno sell 0 1
    pno dispatch 5 0 4 1.5
    pno cancel 17
    pno query-dp money_supply 0.05
    pno sign deadbeef
    pno verify <msg_hex> <sig_hex> <pk_hex>
    pno status
    pno disable
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

import typer

app = typer.Typer(
    help="Penumbra Operator console — drive the external operator agent.",
    no_args_is_help=True,
)

_DEFAULT_API = os.environ.get("PENUMBRA_API_URL", "http://localhost:8000")


def _api_url(base: str, path: str) -> str:
    return base.rstrip("/") + path


def _http_post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 - localhost only
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _http_get(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _print_result(result: dict[str, Any]) -> None:
    """Pretty-print a server response as compact JSON."""
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


def _post_or_die(api: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return _http_post(_api_url(api, path), payload)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        typer.echo(f"backend rejected {path}: {body}", err=True)
        raise typer.Exit(code=1) from exc
    except urllib.error.URLError as exc:
        typer.echo(
            f"could not reach {api} ({exc}); is the Penumbra backend running?"
            "  Hint: start it with `uv run python -m penumbra_transport`",
            err=True,
        )
        raise typer.Exit(code=1) from exc


def _get_or_die(api: str, path: str) -> dict[str, Any]:
    try:
        return _http_get(_api_url(api, path))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        typer.echo(f"backend rejected {path}: {body}", err=True)
        raise typer.Exit(code=1) from exc
    except urllib.error.URLError as exc:
        typer.echo(
            f"could not reach {api} ({exc}); is the Penumbra backend running?",
            err=True,
        )
        raise typer.Exit(code=1) from exc


# ── lifecycle ──────────────────────────────────────────────────────


@app.command()
def enable(api: str = typer.Option(_DEFAULT_API, "--api")) -> None:
    """Bootstrap the operator slot (or no-op if already enabled)."""
    _print_result(_post_or_die(api, "/operator/enable", {}))


@app.command()
def disable(api: str = typer.Option(_DEFAULT_API, "--api")) -> None:
    """Tear down the operator slot."""
    _print_result(_post_or_die(api, "/operator/disable", {}))


@app.command()
def status(api: str = typer.Option(_DEFAULT_API, "--api")) -> None:
    """Mirror of the operator's state (position, coins, ε, queue, score)."""
    payload = _get_or_die(api, "/operator/status")
    if not payload.get("enabled", False):
        typer.echo("operator is not enabled. Run `pno enable` first.")
    _print_result(payload)


# ── core actions ──────────────────────────────────────────────────


@app.command()
def move(
    target_node: int = typer.Argument(..., help="neighbouring node id"),
    api: str = typer.Option(_DEFAULT_API, "--api"),
) -> None:
    """Move the operator to a neighbour (cost is deducted from wallet)."""
    _print_result(_post_or_die(api, "/operator/move", {"target_node": int(target_node)}))


@app.command()
def buy(
    product: int = typer.Argument(..., help="product id"),
    qty: int = typer.Argument(..., help="quantity to buy"),
    api: str = typer.Option(_DEFAULT_API, "--api"),
) -> None:
    """Buy ``qty`` units of ``product`` at the current city."""
    _print_result(
        _post_or_die(
            api,
            "/operator/buy",
            {"product": int(product), "qty": int(qty)},
        )
    )


@app.command()
def sell(
    product: int = typer.Argument(..., help="product id"),
    qty: int = typer.Argument(..., help="quantity to sell"),
    api: str = typer.Option(_DEFAULT_API, "--api"),
) -> None:
    """Sell ``qty`` units of ``product`` at the current city."""
    _print_result(
        _post_or_die(
            api,
            "/operator/sell",
            {"product": int(product), "qty": int(qty)},
        )
    )


@app.command()
def dispatch(
    city: int = typer.Argument(..., help="destination city id"),
    product: int = typer.Argument(..., help="product id"),
    qty: int = typer.Argument(..., help="quantity"),
    reward: float = typer.Argument(..., help="reward coins"),
    api: str = typer.Option(_DEFAULT_API, "--api"),
) -> None:
    """Place an order in the logistics mempool, pre-assigned to the operator."""
    _print_result(
        _post_or_die(
            api,
            "/operator/dispatch_order",
            {
                "city": int(city),
                "product": int(product),
                "qty": int(qty),
                "reward": float(reward),
            },
        )
    )


@app.command()
def cancel(
    order_id: int = typer.Argument(..., help="pending order id"),
    api: str = typer.Option(_DEFAULT_API, "--api"),
) -> None:
    """Release an assigned order back to the unassigned pool."""
    _print_result(_post_or_die(api, "/operator/cancel_assignment", {"order_id": int(order_id)}))


@app.command("query-dp")
def query_dp(
    statistic: str = typer.Argument(..., help="one of money_supply / price_index / ..."),
    epsilon: float = typer.Argument(..., help="ε to deduct from the operator's budget"),
    api: str = typer.Option(_DEFAULT_API, "--api"),
) -> None:
    """Issue a DP-noised query against ``statistic`` for ``epsilon`` budget."""
    _print_result(
        _post_or_die(
            api,
            "/operator/query_dp",
            {"statistic": statistic, "epsilon": float(epsilon)},
        )
    )


@app.command()
def sign(
    message: str = typer.Argument(..., help="hex-encoded message to sign"),
    api: str = typer.Option(_DEFAULT_API, "--api"),
) -> None:
    """Return a Dilithium signature over ``message`` (hex)."""
    _print_result(_post_or_die(api, "/operator/sign", {"message": message}))


@app.command()
def verify(
    message: str = typer.Argument(..., help="hex-encoded message"),
    sig: str = typer.Argument(..., help="hex-encoded signature"),
    public_key: str = typer.Argument(..., help="hex-encoded public key"),
    api: str = typer.Option(_DEFAULT_API, "--api"),
) -> None:
    """Verify a Dilithium signature against a message + public key."""
    _print_result(
        _post_or_die(
            api,
            "/operator/verify",
            {"message": message, "sig": sig, "public_key": public_key},
        )
    )


@app.command()
def sessions(api: str = typer.Option(_DEFAULT_API, "--api")) -> None:
    """List recorded operator sessions (id, scenario, composite, action count)."""
    _print_result(_get_or_die(api, "/operator/sessions"))


@app.command()
def replay(
    session_id: str = typer.Argument(..., help="session id returned by `pno sessions`"),
    api: str = typer.Option(_DEFAULT_API, "--api"),
) -> None:
    """Re-run a recorded session + print the original vs replayed scorecard diff."""
    diff = _get_or_die(api, f"/operator/sessions/{session_id}/replay")
    if diff.get("deterministic", False):
        typer.echo(f"determinism OK (max delta < {diff.get('tolerance', 0.0)})", err=False)
    else:
        typer.echo(
            f"determinism FAIL — deltas exceed tolerance {diff.get('tolerance', 0.0)}",
            err=True,
        )
    _print_result(diff)


if __name__ == "__main__":
    app()
