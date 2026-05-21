"""Tests for the /chain/slash auth gate (audit closure A5)."""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from penumbra_chain.consensus import canonical_block_sign_payload
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_crypto import bls
from penumbra_transport.api import build_app


def _build_evidence_payload(client: TestClient, validator_idx: int = 1) -> dict[str, object]:
    """Build a real evidence payload by reaching into the orchestrator's keys.

    Tests only — a real attacker would NOT have node.secrets.
    """
    # `.app` is an ASGI wrapper; the actual FastAPI app sits behind .app.app
    # in older versions and .app directly in newer; we go through the
    # public-ish `app` attribute on the wrapper.
    app = client.app
    while not hasattr(app, "state") and hasattr(app, "app"):
        app = app.app  # type: ignore[assignment]
    node = app.state.penumbra.orchestrator.node  # type: ignore[attr-defined]
    secret = node.secrets[validator_idx]
    pub = node.validators[validator_idx].bls_pubkey
    height = 7
    h_a = hashlib.sha256(b"branch-a").digest()
    h_b = hashlib.sha256(b"branch-b").digest()
    return {
        "offender_pubkey": pub.hex(),
        "height": height,
        "block_a_hash": h_a.hex(),
        "sig_a": bls.sign(secret.bls_secret, canonical_block_sign_payload(h_a, height)).hex(),
        "block_b_hash": h_b.hex(),
        "sig_b": bls.sign(secret.bls_secret, canonical_block_sign_payload(h_b, height)).hex(),
    }


def _client(snapshots_dir: str) -> TestClient:
    os.environ["PENUMBRA_SNAPSHOTS_DIR"] = snapshots_dir
    sim = Simulation.build(SimulationConfig(n_agents=4, match_max_ticks=50), bootstrap(seed=5))
    return TestClient(build_app(simulation=sim, tick_hz=200.0))


def test_chain_slash_returns_403_when_admin_token_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PENUMBRA_SLASHING_ADMIN_TOKEN", raising=False)
    with tempfile.TemporaryDirectory() as tmp:
        client = _client(tmp)
        with client:
            evidence = _build_evidence_payload(client)
            r = client.post("/chain/slash", json=evidence)
        assert r.status_code == 403
        assert "PENUMBRA_SLASHING_ADMIN_TOKEN" in r.text


def test_chain_slash_returns_401_without_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENUMBRA_SLASHING_ADMIN_TOKEN", "topsecret")
    with tempfile.TemporaryDirectory() as tmp:
        client = _client(tmp)
        with client:
            evidence = _build_evidence_payload(client)
            r = client.post("/chain/slash", json=evidence)
        assert r.status_code == 401


def test_chain_slash_returns_401_with_wrong_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENUMBRA_SLASHING_ADMIN_TOKEN", "topsecret")
    with tempfile.TemporaryDirectory() as tmp:
        client = _client(tmp)
        with client:
            evidence = _build_evidence_payload(client)
            r = client.post(
                "/chain/slash",
                json=evidence,
                headers={"Authorization": "Bearer wrong"},
            )
        assert r.status_code == 401


def test_chain_slash_accepts_correct_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENUMBRA_SLASHING_ADMIN_TOKEN", "topsecret")
    with tempfile.TemporaryDirectory() as tmp:
        client = _client(tmp)
        with client:
            evidence = _build_evidence_payload(client)
            r = client.post(
                "/chain/slash",
                json=evidence,
                headers={"Authorization": "Bearer topsecret"},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["active_validators"] < body["total_validators"]
