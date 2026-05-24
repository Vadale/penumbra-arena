"""Request padding + cover-traffic scheduling.

Concept taught: a passive network adversary cannot read TLS payloads
but it CAN see packet sizes and timing. Two messages of size 17 and 4096
are trivially distinguishable. Padding every request to a fixed bucket
size collapses the visible size to a single value; cover traffic emits
indistinguishable dummy packets on a schedule so the inter-arrival
distribution leaks nothing about the real traffic.

The defender pays bandwidth — a factor of ``target_size / mean(msg_size)``
in the worst case — for an information-theoretic privacy gain: the
size + arrival channel becomes uninformative (or as close to it as the
chosen padding strategy allows).

API is pure-functional. ``pad_request`` / ``pad_response`` take a
``bytes`` and return a padded ``bytes`` with the length and a small
header capturing the original size so the receiver can unpad.
``cover_traffic_schedule`` returns the tick offsets at which the
defender should emit decoy packets to match a Poisson rate.

References
----------
- Sun et al. "Statistical Identification of Encrypted Web Browsing
  Traffic" (S&P 2002) — the foundational packet-size fingerprinting paper.
- Wang & Goldberg "On Realistically Attacking Tor with Website
  Fingerprinting" (PETS 2016) — defender survey.
- Loopix (USENIX Sec 2017) — Poisson cover-traffic argument.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import numpy as np

_LENGTH_HEADER_BYTES: int = 4
PAD_BYTE: bytes = b"\x00"


@dataclass(slots=True, frozen=True)
class PaddingReport:
    """Privacy-utility tradeoff snapshot for a padding configuration."""

    n_messages: int
    mean_original_size: float
    target_size: int
    bandwidth_overhead_ratio: float
    n_distinct_sizes_after: int
    n_distinct_sizes_before: int


def _secure_rng() -> np.random.Generator:
    seed = int.from_bytes(secrets.token_bytes(8), "big")
    return np.random.default_rng(seed)


def pad_request(msg: bytes, target_size: int) -> bytes:
    """Pad ``msg`` to exactly ``target_size`` bytes using a length prefix.

    Wire layout: ``[u32 big-endian original-length][payload][zero pad]``.
    A receiver reads the 4-byte header to recover ``len(msg)`` and slices
    the payload back out. Padding never silently drops data — if
    ``len(msg) + 4 > target_size`` we raise instead of truncating.
    """
    if target_size <= _LENGTH_HEADER_BYTES:
        raise PaddingError(
            f"target_size {target_size} must exceed header ({_LENGTH_HEADER_BYTES} bytes)"
        )
    if len(msg) + _LENGTH_HEADER_BYTES > target_size:
        msg_size = len(msg)
        raise PaddingError(
            f"message ({msg_size} bytes) does not fit in target {target_size}; raise target_size or split"
        )
    header = len(msg).to_bytes(_LENGTH_HEADER_BYTES, "big")
    pad_len = target_size - len(msg) - _LENGTH_HEADER_BYTES
    return header + msg + (PAD_BYTE * pad_len)


def pad_response(msg: bytes, target_size: int) -> bytes:
    """Pad a response payload. Same wire format as :func:`pad_request`.

    Kept as a distinct function because some deployments use different
    response-side buckets (e.g. larger because responses carry analytics
    payloads) — having two names makes the choice explicit at call sites.
    """
    return pad_request(msg, target_size)


def unpad(padded: bytes) -> bytes:
    """Recover the original payload from a padded message.

    Validates that the header length is within the buffer; raises on
    truncated or malformed inputs rather than returning best-effort
    garbage (silent corruption is a worse failure mode than rejection).
    """
    if len(padded) < _LENGTH_HEADER_BYTES:
        raise PaddingError("padded message is shorter than the length header")
    original_len = int.from_bytes(padded[:_LENGTH_HEADER_BYTES], "big")
    if original_len + _LENGTH_HEADER_BYTES > len(padded):
        raise PaddingError(f"declared length {original_len} exceeds buffer ({len(padded)})")
    return bytes(padded[_LENGTH_HEADER_BYTES : _LENGTH_HEADER_BYTES + original_len])


def cover_traffic_schedule(
    rate: float,
    duration_ticks: int,
    *,
    rng: np.random.Generator | None = None,
) -> list[int]:
    """Return tick offsets at which a defender should emit decoy packets.

    Inter-arrival times are drawn from ``Exp(rate)`` (Poisson process)
    so the visible packet stream looks indistinguishable from any other
    Poisson source — the standard mix-net analysis (Loopix) requires
    Poisson arrivals to bound the linkability advantage.

    ``rate`` is in packets per tick (e.g. ``rate=0.1`` ≈ 10 ticks
    between decoys on average). Offsets are clipped to ``duration_ticks``
    and returned strictly increasing.
    """
    if rate < 0:
        raise PaddingError(f"rate must be >= 0, got {rate}")
    if duration_ticks <= 0:
        raise PaddingError(f"duration_ticks must be > 0, got {duration_ticks}")
    if rate == 0.0:
        return []
    rng = rng if rng is not None else _secure_rng()
    offsets: list[int] = []
    t = 0.0
    while True:
        gap = float(rng.exponential(scale=1.0 / rate))
        t += gap
        if t >= duration_ticks:
            break
        offsets.append(int(t))
    return offsets


def evaluate_tradeoff(
    sizes: list[int],
    target_size: int,
) -> PaddingReport:
    """Quantify the privacy-utility tradeoff of padding to ``target_size``.

    Privacy: number of distinct visible sizes after padding (always 1
    if every message fits the bucket). Utility cost: bandwidth overhead
    ratio = ``target_size / mean(sizes)`` — how many bytes the defender
    paid per real byte released.
    """
    if not sizes:
        raise PaddingError("sizes must be non-empty for evaluation")
    if any(s < 0 for s in sizes):
        raise PaddingError("sizes must be non-negative")
    mean_original = float(np.mean(sizes))
    distinct_before = len(set(sizes))
    fits = [s + _LENGTH_HEADER_BYTES <= target_size for s in sizes]
    distinct_after = 1 if all(fits) else 1 + sum(1 for f in fits if not f)
    overhead = float(target_size) / max(mean_original, 1.0)
    return PaddingReport(
        n_messages=len(sizes),
        mean_original_size=mean_original,
        target_size=target_size,
        bandwidth_overhead_ratio=overhead,
        n_distinct_sizes_after=distinct_after,
        n_distinct_sizes_before=distinct_before,
    )


def demo() -> dict[str, object]:
    """Self-contained demo: padding curve + a Poisson schedule sample."""
    rng = np.random.default_rng(seed=20260523)
    sizes = [int(s) for s in rng.integers(50, 800, size=100)]
    curve: list[dict[str, float]] = []
    for target in (256, 512, 1024, 2048, 4096):
        report = evaluate_tradeoff(sizes, target)
        curve.append(
            {
                "target_size": float(target),
                "bandwidth_overhead_ratio": report.bandwidth_overhead_ratio,
                "n_distinct_sizes_after": float(report.n_distinct_sizes_after),
                "n_distinct_sizes_before": float(report.n_distinct_sizes_before),
            }
        )
    schedule = cover_traffic_schedule(
        rate=0.05, duration_ticks=200, rng=np.random.default_rng(seed=1)
    )
    return {
        "available": True,
        "algorithm": "request padding + Poisson cover traffic",
        "n_messages": len(sizes),
        "mean_original_size": float(np.mean(sizes)),
        "curve": curve,
        "cover_schedule_preview": schedule[:20],
        "cover_schedule_size": len(schedule),
    }


class PaddingError(ValueError):
    """Raised on invalid padding parameters or malformed buffers."""
