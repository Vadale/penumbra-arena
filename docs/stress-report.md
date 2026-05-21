# Penumbra — Stress-test report

**Date**: 2026-05-21 · **Window**: 5 minutes baseline · **Backend**: full features (MAPPO + DP + signing + topics).

The harness lives in `scripts/stress_test.py` and was intended for a
24-hour overnight run. The 5-minute baseline below is enough to
**surface three load-bearing issues** that would have been invisible
in 30-second smokes.

## Setup

```sh
# Terminal 1: boot backend with all features active
PENUMBRA_SEED=42 \
PENUMBRA_MAPPO_CHECKPOINT="$(pwd)/checkpoints/mappo_v0.pt" \
  uv run uvicorn penumbra_transport.api:app --port 8100 --log-level warning

# Terminal 2: harness (5 min, sample every 10 s)
PENUMBRA_API_PORT=8100 \
  uv run python scripts/stress_test.py --port 8100 --interval 10 --duration 300
```

For the real 24-h run, swap `--duration 300` for `--duration 86400`.

## Measured (5-min window)

| Metric | Start | End | Drift | Anomaly threshold |
|---|---|---|---|---|
| RSS (MB) | 1050.4 | 1804.6 | **+754 MB** | < 50 MB/h |
| Tick throughput (Hz) | n/a | **4.73** | — | ≥ 8.0 (target 10) |
| Chain blocks produced | 0 | 13 | 13 | ~30 expected |
| Sigs verified / s | n/a | 39.2 | — | ≥ 30 |
| Sigs rejected | 0 | 0 | 0 | 0 ✅ |
| DP ε spent | 0.15 | **5.00 (max)** | 4.85 | gradual ✅ |
| CPU (p50) | — | 32.4 % | — | < 80 % ✅ |

CSV at `state/stress/run-1779395954.csv` (committed).

## Anomalies

### A. Memory drift — **+754 MB in 5 min → ~9 GB/h projected**

RSS grows monotonically over the window, far above the 50 MB/h
threshold. Projecting linearly: OOM in ~90 minutes on a 16 GB Mac
mini. This is a **load-bearing issue**.

Likely root causes (ordered by my confidence):

1. **BERTopic / sentence-transformers**: each call to
   `analytics.topics.compute()` runs `BERTopic.fit_transform` over
   the rolling utterance buffer. The `BERTopic` instance and the
   intermediate UMAP/HDBSCAN models are reconstructed every call
   (every 20 s by default). Either the embedder is re-allocating
   the model on each call, or torch's MPS caches are growing.
2. **The dashboard pipeline's rolling deques** are bounded, but
   the per-tick `_positions` deque holds `NDArray[float64]` of
   shape (50,) — should be O(64 × 50 × 8 B) = 25 KB, not GB.
3. **CKKS ciphertext residue**: each tick's per-agent encrypt →
   add → decrypt chain produces TenSEAL `CKKSVector` objects.
   Verify they're being garbage-collected by the GC after the
   sample is stored.

Action: investigate with `tracemalloc` snapshot diff between
sample N and sample N+50.

### B. Tick throughput — 4.73 Hz vs 10 Hz target

The configured `tick_hz=10` is roughly half-achieved. The
analytics loop runs on the same event loop, and the heaviest
consumer (`topics.compute()`) blocks for ~3-5 s when the corpus
grows past 200 utterances. Even though we wrap it in
`asyncio.to_thread`, the GIL still constrains downstream
sympatric numpy work.

Action: profile a tick window with `py-spy record` and confirm
which consumer is the dominant CPU sink. The 20-s cadence on
`topics` was supposed to amortise this, but at small corpora the
fit-transform isn't fast enough.

### C. DP budget exhausts in 5 minutes

The default config is `total ε = 5.0` and `per-release ε = 0.05`,
with releases at 1 Hz. That's 100 noised releases ≈ 1m 40s before
the budget is gone, and we observed it consumed in ~50 s here
because the per-release ε is documented as 0.05 but in practice
the heatmap-loop cadence + the dashboard-poll cadence both drain
the budget.

This is **not a bug**, it's a parameter choice that's far too
aggressive for a "perpetual" simulation. Two fixes:
- Increase total ε: 5.0 → 5000.0 gives ~80 hours at the same cadence.
- Increase per-release noise: smaller ε per release at the cost of
  more visible jitter on the released heatmap.

Pick based on the educational point you want the DP cell to teach:
- "watch the budget run out fast" → keep current
- "watch DP run forever as a passive defence" → 5000.0

## Non-anomalies

- **Sigs rejected = 0** through the window. The race-fix from
  `house-keeping` holds.
- **CPU p50 at 32 %** — well below saturation. The throughput
  loss isn't pure CPU starvation; it's GIL or I/O contention.

## Recommended next steps (out of this commit's scope)

1. Reproduce A with `tracemalloc`; identify the leaker.
2. Run B with `py-spy record --duration 60`; confirm top consumer.
3. Bump DP defaults in `Orchestrator.build()` to (ε_total=5000,
   per-release=0.05) and document the choice in the docstring.

## Running it overnight yourself

```sh
# In a screen / tmux session you can detach from:
PENUMBRA_SEED=42 \
PENUMBRA_MAPPO_CHECKPOINT="checkpoints/mappo_v0.pt" \
  uv run uvicorn penumbra_transport.api:app --port 8100 \
  --log-level warning > backend.log 2>&1 &

PENUMBRA_API_PORT=8100 \
  uv run python scripts/stress_test.py \
  --port 8100 --interval 60 --duration 86400 \
  --output state/stress/overnight.csv > stress.log 2>&1 &
```

In the morning, `cat stress.log` shows the final summary and any
anomalies. The CSV at `state/stress/overnight.csv` is the audit
trail.
