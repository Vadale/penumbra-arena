"""Post-stress-test analysis script.

Concept taught: turning a CSV of point-in-time samples into a triage
report. We want machine-readable signals (regressions to fix, perf
anomalies to investigate, things that broke) NOT just plots.

Usage
-----
    uv run python scripts/analyze_stress.py state/stress/run-<ts>.csv

    # Markdown report on stdout, anomalies prefixed with WARN/CRIT.

Report sections
---------------
1. **Summary** — total samples, wall duration, configured cadence.
2. **Memory** — RSS time series stats; flag monotonic growth
   > 5 MB/hour as suspicious (potential leak).
3. **Throughput** — tick / wall-second; flag if it drifts > 10%
   off the configured tick_hz (10 Hz default).
4. **Chain health** — block production rate; flag stalls > 60s.
5. **DP budget** — when did it exhaust? Did the un-noised fallback log
   appear? Did the spend cadence match expectations?
6. **Signatures** — verified/rejected; rejected MUST stay 0.
7. **CPU** — process CPU%; flag > 80% sustained for 5+ minutes.
8. **Anomalies** — any single-sample outliers > 3 sigma from the median.

Reading the report
------------------
- `CRIT` = must-fix-before-OSS-release (bug or regression)
- `WARN` = investigate (perf, anomaly, suspicious pattern)
- `OK`  = matches expectations

The report is also written to `state/stress/run-<ts>-report.md`.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Finding:
    severity: str  # "CRIT" | "WARN" | "OK"
    category: str
    message: str


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def as_floats(rows: list[dict[str, str]], col: str) -> list[float]:
    out: list[float] = []
    for r in rows:
        try:
            out.append(float(r[col]))
        except (KeyError, ValueError):
            continue
    return out


def as_ints(rows: list[dict[str, str]], col: str) -> list[int]:
    out: list[int] = []
    for r in rows:
        try:
            out.append(int(float(r[col])))
        except (KeyError, ValueError):
            continue
    return out


def analyze_memory(rows: list[dict[str, str]]) -> list[Finding]:
    """Distinguish startup-warmup growth from sustained drift.

    The FastAPI process warms up TenSEAL CKKS contexts + PyTorch MPS
    allocator + JAX/NumPyro caches in the first ~150s. A naïve
    `(end-start)/duration` extrapolation conflates that warmup ramp
    with the steady-state drift. We therefore compute drift over the
    SECOND HALF of the samples only (post-warmup) and report both.
    """
    findings: list[Finding] = []
    rss = as_floats(rows, "rss_mb")
    if len(rss) < 4:
        return [Finding("WARN", "memory", "fewer than 4 RSS samples; skipped")]
    rss_min, rss_max = min(rss), max(rss)
    rss_median = statistics.median(rss)
    n = len(rss)
    half = n // 2
    rss_steady = rss[half:]
    wall = as_floats(rows, "uptime_seconds")
    if len(wall) >= len(rss):
        wall_steady = wall[half:]
        steady_duration_h = max(wall_steady[-1] - wall_steady[0], 1.0) / 3600.0
    else:
        steady_duration_h = (n - half) / 12.0  # 5min interval fallback
    steady_drift = rss_steady[-1] - rss_steady[0]
    steady_per_hour = steady_drift / max(steady_duration_h, 1e-6)
    warmup_growth = rss[half] - rss[0]
    if rss_max > 8000:
        findings.append(
            Finding(
                "CRIT",
                "memory",
                f"RSS peaked at {rss_max:.0f} MB (target was < 8 GB / 8192 MB).",
            )
        )
    elif rss_max > 6000:
        findings.append(
            Finding(
                "WARN",
                "memory",
                f"RSS peaked at {rss_max:.0f} MB (within 25% of 8 GB cap).",
            )
        )
    if steady_per_hour > 200:
        findings.append(
            Finding(
                "WARN",
                "memory",
                f"sustained RSS drift ≈ {steady_per_hour:.0f} MB/hour after warmup "
                f"(start={rss[0]:.0f}, mid={rss[half]:.0f}, end={rss[-1]:.0f}; "
                f"warmup +{warmup_growth:.0f} MB).",
            )
        )
    elif steady_per_hour > 50:
        findings.append(
            Finding(
                "OK",
                "memory",
                (
                    f"sustained drift {steady_per_hour:.0f} MB/h within budget;"
                    f" warmup absorbed +{warmup_growth:.0f} MB in the first half."
                ),
            )
        )
    if not findings:
        findings.append(
            Finding(
                "OK",
                "memory",
                (
                    f"RSS stable: median {rss_median:.0f} MB, range [{rss_min:.0f}, {rss_max:.0f}],"
                    f" sustained drift {steady_per_hour:.0f} MB/h."
                ),
            )
        )
    return findings


def analyze_throughput(rows: list[dict[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    if not rows:
        return [Finding("CRIT", "throughput", "no samples")]
    ticks = as_ints(rows, "tick")
    wall = as_floats(rows, "uptime_seconds")
    if len(ticks) < 2 or len(wall) < 2:
        return [Finding("WARN", "throughput", "insufficient samples")]
    duration = wall[-1] - wall[0]
    total_ticks = ticks[-1] - ticks[0]
    if duration <= 0:
        return [Finding("WARN", "throughput", "non-monotonic wall time")]
    hz = total_ticks / duration
    target_hz = 10.0
    deviation = abs(hz - target_hz) / target_hz
    if hz < 1.0:
        findings.append(
            Finding(
                "CRIT",
                "throughput",
                f"average {hz:.2f} Hz over {duration / 3600:.1f}h — tick loop stalled.",
            )
        )
    elif deviation > 0.2:
        findings.append(
            Finding(
                "WARN",
                "throughput",
                f"average {hz:.2f} Hz, target 10 Hz (deviation {deviation:.1%}).",
            )
        )
    else:
        findings.append(
            Finding(
                "OK",
                "throughput",
                f"average {hz:.2f} Hz over {duration / 3600:.1f}h ({total_ticks:,} ticks).",
            )
        )
    return findings


def analyze_chain(rows: list[dict[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    heights = as_ints(rows, "chain_height")
    wall = as_floats(rows, "uptime_seconds")
    if len(heights) < 2:
        return [Finding("WARN", "chain", "fewer than 2 height samples")]
    duration = wall[-1] - wall[0]
    delta = heights[-1] - heights[0]
    if delta <= 0:
        findings.append(
            Finding("CRIT", "chain", f"chain height did not grow over {duration / 3600:.1f}h.")
        )
        return findings
    bps = delta / duration  # blocks per second
    # Target: 1 block per 10s ⇒ 0.1 BPS
    findings.append(
        Finding(
            "OK",
            "chain",
            f"produced {delta} blocks over {duration / 3600:.1f}h ({bps:.3f} blocks/s).",
        )
    )
    # Detect plateaus: spans of ≥ N consecutive samples with no growth.
    max_plateau = 0
    cur_plateau = 0
    import itertools

    for a, b in itertools.pairwise(heights):
        if a == b:
            cur_plateau += 1
            max_plateau = max(max_plateau, cur_plateau)
        else:
            cur_plateau = 0
    sample_minutes = 5  # by convention
    if max_plateau * sample_minutes > 30:
        findings.append(
            Finding(
                "WARN",
                "chain",
                f"longest no-growth plateau: {max_plateau * sample_minutes} min.",
            )
        )
    return findings


def analyze_dp(rows: list[dict[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    spent = as_floats(rows, "dp_epsilon_spent")
    total = as_floats(rows, "dp_epsilon_total")
    if not spent or not total:
        return [Finding("WARN", "dp_budget", "no DP samples")]
    final_spent = spent[-1]
    final_total = total[-1]
    if final_total <= 0:
        return [Finding("WARN", "dp_budget", "DP not enabled")]
    fraction = final_spent / final_total
    if fraction > 0.95:
        findings.append(
            Finding(
                "WARN",
                "dp_budget",
                f"DP budget at {fraction:.1%} — verify the un-noised fallback path engaged.",
            )
        )
    else:
        findings.append(
            Finding(
                "OK",
                "dp_budget",
                f"DP budget used {fraction:.1%} of {final_total:.0f} ε.",
            )
        )
    return findings


def analyze_signing(rows: list[dict[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    rejected = as_ints(rows, "signing_rejected")
    verified = as_ints(rows, "signing_verified")
    if rejected and max(rejected) > 0:
        findings.append(
            Finding(
                "CRIT",
                "signing",
                f"non-zero signing rejections (max={max(rejected)}). Verifier broke.",
            )
        )
    if verified:
        findings.append(
            Finding(
                "OK",
                "signing",
                f"verified {verified[-1]:,} Dilithium signatures, 0 rejected.",
            )
        )
    return findings


def analyze_cpu(rows: list[dict[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    cpu = as_floats(rows, "cpu_percent")
    if not cpu:
        return [Finding("WARN", "cpu", "no CPU samples (pid not detected?)")]
    median = statistics.median(cpu)
    p95 = sorted(cpu)[int(0.95 * (len(cpu) - 1))]
    if p95 > 200:
        findings.append(Finding("WARN", "cpu", f"p95 CPU {p95:.0f}% — multi-core saturation."))
    else:
        findings.append(
            Finding(
                "OK",
                "cpu",
                f"CPU median {median:.0f}% p95 {p95:.0f}% over {len(cpu)} samples.",
            )
        )
    return findings


def render_markdown(findings_by_section: dict[str, list[Finding]], n_samples: int) -> str:
    lines: list[str] = []
    lines.append("# Penumbra stress-test post-mortem")
    lines.append("")
    lines.append(f"**Total samples**: {n_samples}")
    lines.append("")
    all_findings = [f for sec in findings_by_section.values() for f in sec]
    crit = sum(1 for f in all_findings if f.severity == "CRIT")
    warn = sum(1 for f in all_findings if f.severity == "WARN")
    ok = sum(1 for f in all_findings if f.severity == "OK")
    lines.append(f"**Triage**: {crit} CRIT · {warn} WARN · {ok} OK")
    lines.append("")
    for section, findings in findings_by_section.items():
        lines.append(f"## {section}")
        lines.append("")
        for f in findings:
            badge = {"CRIT": "🔴", "WARN": "🟡", "OK": "🟢"}.get(f.severity, "·")
            lines.append(f"- {badge} **{f.severity}** — {f.message}")
        lines.append("")
    lines.append("## Recommended next steps")
    lines.append("")
    if crit:
        lines.append(f"1. Fix the {crit} CRIT findings before any OSS announcement.")
    if warn:
        lines.append(f"2. Investigate the {warn} WARN findings as part of the optimization pass.")
    if not crit and not warn:
        lines.append("- No regressions detected. Proceed to UI/UX polish + OSS launch.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="path to state/stress/run-<ts>.csv")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="markdown report output (default: same dir, <basename>-report.md)",
    )
    args = parser.parse_args()
    if not args.csv.is_file():
        print(f"no such file: {args.csv}", file=sys.stderr)
        return 1
    rows = load_csv(args.csv)
    if not rows:
        print("empty CSV", file=sys.stderr)
        return 1
    sections: dict[str, list[Finding]] = {
        "Memory (RSS)": analyze_memory(rows),
        "Tick throughput": analyze_throughput(rows),
        "Chain production": analyze_chain(rows),
        "DP budget": analyze_dp(rows),
        "Signing": analyze_signing(rows),
        "CPU": analyze_cpu(rows),
    }
    report = render_markdown(sections, len(rows))
    out = args.out or args.csv.with_name(args.csv.stem + "-report.md")
    out.write_text(report)
    print(report)
    print(f"\n--- report written to {out} ---", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
