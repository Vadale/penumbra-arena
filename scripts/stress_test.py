"""Long-running stress harness for the Penumbra backend.

Concept taught: a system that PASSES on a 30-second smoke can still
leak memory, drift in throughput, or silently fall out of its
intended-cadence consumers over a real-life run. The point of this
harness is to make those drifts visible.

Layout
------
- The harness expects the backend to ALREADY be running (set
  PENUMBRA_API_PORT, default 8000). It does NOT spawn uvicorn; that
  separation makes it easy to attach to any deployment you already
  have up — local dev, docker compose, a long-running session.
- Every `--interval` seconds it polls:
    /health, /chain/latest, /dp/budget, /agents/signing-stats
  …plus `psutil` measurements of the backend process's RSS + CPU%
  if `--pid` is supplied (or auto-detected via `lsof`).
- One CSV row per poll under `state/stress/run-<timestamp>.csv`.
- On exit (Ctrl-C, deadline reached, or `--duration` elapsed) it
  prints a summary + anomaly list to stdout.

Reading the output
------------------
Memory drift:   `rss_mb` should be near-flat after warm-up. Any
                 monotonic increase > ~5 MB/hour is suspicious.
Tick throughput: `tick / wall_seconds` should stay near the
                 configured tick_hz (10 Hz default).
DP budget:      `dp_epsilon_spent` should saturate at the
                 configured total quickly (the heatmap loop
                 spends 0.05 ε per second at default config),
                 then `dp_noise_applied` should turn OFF; check
                 the warning log for the fallback message.
Sigs:           `signing_verified` should grow ~linearly at
                 n_agents * tick_hz = 50 * 10 = 500/s; rejected
                 should stay at 0.

Usage
-----
    # 24h run, default cadence (every 30s):
    uv run python scripts/stress_test.py --duration 86400

    # 5-minute smoke window with finer sampling:
    uv run python scripts/stress_test.py --duration 300 --interval 5
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


@dataclass
class Sample:
    timestamp: float
    tick: int
    match_id: int
    uptime_seconds: float
    chain_height: int
    dp_epsilon_spent: float
    dp_epsilon_remaining: float
    dp_noise_applied: bool
    signing_verified: int
    signing_rejected: int
    rss_mb: float | None
    cpu_percent: float | None


def fetch_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=5) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def detect_pid(port: int) -> int | None:
    """Find the PID listening on `port` via lsof. Returns None if not found."""
    try:
        # `lsof` is the standard macOS/Linux tool for "what process owns
        # this socket". Hardcoding the binary name (not the full path)
        # because users may have it under /usr/sbin, /usr/bin, or
        # brew-managed /opt/homebrew/bin — let $PATH win.
        result = subprocess.run(  # noqa: S603
            ["lsof", "-ti", f":{port}"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except FileNotFoundError:
        return None
    pids = [int(line) for line in result.stdout.split() if line.strip().isdigit()]
    return pids[0] if pids else None


def sample_once(base_url: str, proc: psutil.Process | None) -> Sample | None:
    """One sampling pass. Returns None if the backend is unreachable."""
    try:
        health = fetch_json(f"{base_url}/health")
        chain = fetch_json(f"{base_url}/chain/latest")
        dp = fetch_json(f"{base_url}/dp/budget")
        sigs = fetch_json(f"{base_url}/agents/signing-stats")
    except URLError:
        return None

    rss_mb: float | None = None
    cpu_percent: float | None = None
    if proc is not None:
        try:
            rss_mb = proc.memory_info().rss / (1024 * 1024)
            cpu_percent = proc.cpu_percent(interval=0.1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            rss_mb = None
            cpu_percent = None

    return Sample(
        timestamp=time.time(),
        tick=int(health.get("tick", 0)),
        match_id=int(health.get("match_id", 0)),
        uptime_seconds=float(health.get("uptime_seconds", 0.0)),
        chain_height=int(chain.get("height", 0)),
        dp_epsilon_spent=float(dp.get("epsilon_spent", 0.0)) if dp.get("enabled") else 0.0,
        dp_epsilon_remaining=(
            float(dp.get("epsilon_remaining", 0.0)) if dp.get("enabled") else 0.0
        ),
        dp_noise_applied=False,  # filled at higher cadence if needed
        signing_verified=int(sigs.get("verified", 0)),
        signing_rejected=int(sigs.get("rejected", 0)),
        rss_mb=rss_mb,
        cpu_percent=cpu_percent,
    )


def write_csv(path: Path, samples: Iterable[Sample]) -> None:
    rows = list(samples)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].__dict__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def summarise(samples: list[Sample]) -> dict[str, Any]:
    if len(samples) < 2:
        return {"samples": len(samples), "note": "not enough samples to summarise"}

    span = samples[-1].timestamp - samples[0].timestamp
    tick_throughput = (samples[-1].tick - samples[0].tick) / max(span, 1.0)
    chain_growth = samples[-1].chain_height - samples[0].chain_height

    rss_values = [s.rss_mb for s in samples if s.rss_mb is not None]
    rss_drift = (rss_values[-1] - rss_values[0]) if len(rss_values) >= 2 else None

    sigs_throughput = (samples[-1].signing_verified - samples[0].signing_verified) / max(span, 1.0)
    sigs_rejected_growth = samples[-1].signing_rejected - samples[0].signing_rejected

    return {
        "samples": len(samples),
        "wall_seconds": round(span, 1),
        "tick_throughput_hz": round(tick_throughput, 2),
        "chain_blocks_in_run": chain_growth,
        "rss_mb_start": round(rss_values[0], 1) if rss_values else None,
        "rss_mb_end": round(rss_values[-1], 1) if rss_values else None,
        "rss_drift_mb": round(rss_drift, 1) if rss_drift is not None else None,
        "rss_per_hour_mb": (
            round(rss_drift / span * 3600, 1) if rss_drift is not None and span > 0 else None
        ),
        "sigs_throughput_hz": round(sigs_throughput, 1),
        "sigs_rejected_growth": sigs_rejected_growth,
        "dp_epsilon_spent_end": round(samples[-1].dp_epsilon_spent, 3),
        "dp_epsilon_remaining_end": round(samples[-1].dp_epsilon_remaining, 3),
        "cpu_p50_percent": round(
            statistics.median(s.cpu_percent for s in samples if s.cpu_percent is not None),
            1,
        )
        if any(s.cpu_percent is not None for s in samples)
        else None,
    }


def detect_anomalies(samples: list[Sample], summary: dict[str, Any]) -> list[str]:
    """Return a list of warning strings; empty list means clean."""
    out: list[str] = []
    span_s = summary.get("wall_seconds", 0)
    if not isinstance(span_s, int | float) or span_s < 30:
        return out

    tick_hz = summary.get("tick_throughput_hz")
    if isinstance(tick_hz, int | float) and tick_hz < 8.0:
        out.append(
            f"tick throughput {tick_hz} Hz is below 8.0 Hz target "
            "(expected ~10 Hz; possible event loop saturation)"
        )

    sigs_hz = summary.get("sigs_throughput_hz")
    if isinstance(sigs_hz, int | float) and sigs_hz < 30:
        out.append(
            f"sig verification throughput {sigs_hz}/s is unusually low "
            "(expected ~50 verifies/second at default config)"
        )

    sigs_rej = summary.get("sigs_rejected_growth")
    if isinstance(sigs_rej, int) and sigs_rej > 0:
        out.append(f"{sigs_rej} sig verifications were REJECTED — investigate")

    rss_per_h = summary.get("rss_per_hour_mb")
    if isinstance(rss_per_h, int | float) and rss_per_h > 50.0:
        out.append(f"RSS drift {rss_per_h} MB/h is above 50 MB/h threshold (possible memory leak)")

    chain_growth = summary.get("chain_blocks_in_run")
    expected_blocks = span_s / 10  # block produced every ~10 s by default
    if (
        isinstance(chain_growth, int)
        and isinstance(expected_blocks, int | float)
        and chain_growth < 0.5 * expected_blocks
    ):
        out.append(
            f"chain produced {chain_growth} blocks vs ~{int(expected_blocks)} expected "
            "(consensus may be stalled)"
        )

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PENUMBRA_API_PORT", "8000"))
    )
    parser.add_argument("--interval", type=int, default=30, help="seconds between samples")
    parser.add_argument(
        "--duration",
        type=int,
        default=86400,
        help="total seconds to run (default 24h = 86400)",
    )
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output CSV path (default: state/stress/run-<timestamp>.csv)",
    )
    args = parser.parse_args()

    base_url = f"http://localhost:{args.port}"
    output_path = args.output or (Path("state") / "stress" / f"run-{int(time.time())}.csv")

    pid = args.pid or detect_pid(args.port)
    proc: psutil.Process | None = None
    if pid is not None and HAS_PSUTIL:
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            proc = None
    elif not HAS_PSUTIL:
        print(
            "[stress] psutil not installed — memory/CPU sampling disabled",
            file=sys.stderr,
        )

    print(
        f"[stress] backend={base_url} pid={pid} interval={args.interval}s "
        f"duration={args.duration}s output={output_path}",
        file=sys.stderr,
    )

    samples: list[Sample] = []
    stop = False

    def on_sigint(*_: object) -> None:
        nonlocal stop
        stop = True
        print("\n[stress] caught SIGINT — flushing and summarising", file=sys.stderr)

    signal.signal(signal.SIGINT, on_sigint)

    deadline = time.time() + args.duration
    while time.time() < deadline and not stop:
        sample = sample_once(base_url, proc)
        if sample is not None:
            samples.append(sample)
            # Every 20 samples, flush + print a one-line progress.
            if len(samples) % 20 == 0:
                write_csv(output_path, samples)
                print(
                    f"[stress] {len(samples)} samples · tick={sample.tick} · "
                    f"chain=#{sample.chain_height} · rss="
                    f"{f'{sample.rss_mb:.1f} MB' if sample.rss_mb is not None else '—'} · "
                    f"ε spent={sample.dp_epsilon_spent:.2f}",
                    file=sys.stderr,
                )
        else:
            print("[stress] backend unreachable", file=sys.stderr)
        # Sleep — but check stop flag periodically so SIGINT lands fast.
        end_sleep = time.time() + args.interval
        while time.time() < end_sleep and not stop:
            time.sleep(0.5)

    write_csv(output_path, samples)
    summary = summarise(samples)
    anomalies = detect_anomalies(samples, summary)

    print(
        f"\n[stress] === summary === ({len(samples)} samples, output={output_path})",
        file=sys.stderr,
    )
    for key, value in summary.items():
        print(f"  {key:>26}: {value}", file=sys.stderr)
    if anomalies:
        print("\n[stress] ⚠ anomalies:", file=sys.stderr)
        for a in anomalies:
            print(f"  - {a}", file=sys.stderr)
    else:
        print("\n[stress] no anomalies detected.", file=sys.stderr)

    return 0 if not anomalies else 1


if __name__ == "__main__":
    sys.exit(main())
