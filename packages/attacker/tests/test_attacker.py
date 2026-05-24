"""Smoke tests: each attack runs and the defence's expected property holds."""

from __future__ import annotations

import pytest
from penumbra_attacker.attacks import (
    byzantine,
    dp_reconstruction,
    linkability,
    replay,
    timing_sidechannel,
)
from penumbra_attacker.cli import app
from typer.testing import CliRunner


def test_replay_naive_succeeds_hardened_fails() -> None:
    result = replay.demo()
    assert result.naive_succeeded is True
    assert result.with_tick_counter_succeeded is False


def test_linkability_attack_works_then_noise_defends() -> None:
    result = linkability.demo(n_agents=5, n_matches=30, seed=42)
    assert result.naive_accuracy > 0.5
    assert result.with_noise_accuracy < result.naive_accuracy


def test_dp_reconstruction_with_low_noise() -> None:
    result = dp_reconstruction.demo(n_bits=32, n_queries=300, noise_scale=0.1)
    assert result.recovered_bit_accuracy > 0.85


def test_dp_reconstruction_high_noise_fails() -> None:
    """Crank the noise way up; reconstruction should land at coin-flip accuracy."""
    result = dp_reconstruction.demo(n_bits=32, n_queries=300, noise_scale=20.0)
    assert result.recovered_bit_accuracy < 0.75


def test_byzantine_equivocation_detected() -> None:
    assert byzantine.demo().equivocation_detected


@pytest.mark.slow
def test_timing_sidechannel_constant_time() -> None:
    result = timing_sidechannel.demo(n_samples=10, vector_size=32)
    # Both libraries we use are constant-time on the add path; the t-stat
    # should be small even with only 10 samples. Crypto-audit closure:
    # threshold tightened from |t| < 100 to |t| < 5 per audit
    # recommendation — a real leak presents as |t| ≫ 2.
    assert abs(result.welch_t_statistic) < 5


# ── CLI ───────────────────────────────────────────────────────────


def test_cli_help_lists_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["replay-cmd", "linkability-cmd", "dp-reconstruct", "byzantine-cmd", "timing"]:
        assert cmd in result.output or cmd.replace("-cmd", "") in result.output


def test_cli_replay_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["replay-cmd"])
    assert result.exit_code == 0
    assert "naive replay succeeded" in result.output


def test_cli_byzantine_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["byzantine-cmd"])
    assert result.exit_code == 0
    assert "equivocation proof verified" in result.output
