# Hero image spec (docs/hero.png)

The hero image is the first visual a visitor sees in the README on
GitHub. It must convince a viewer in <3 seconds that Penumbra is
real software running.

## Required content

A live screenshot of the running dashboard at `localhost:5173`,
with the following panels visible:

1. **3D arena view** (top-left) — fuzzy agent clouds on the
   procedurally-dynamic graph. Capture at a moment when the cluster
   structure is visible (e.g. agents grouped near goals).
2. **Encrypted heatmap tile** (any quadrant) — the DP-noised
   density visualisation. Should look like a noisy heatmap.
3. **Persistence barcode** (lower strip) — H₀ and H₁ bars.
4. **Chain explorer** (right side) — at least 3 blocks visible
   with their `(height, hash-prefix, validator)` triples.
5. **Analytics tiles strip** — show at least 6 tiles with live
   values (trajectory mean, σ, Sinkhorn, var.95, ε, etc.).
6. **Terminal panel** (bottom or right) — `pna` or `psh` prompt
   with one example command and its output.

## Capture settings

- **Resolution**: 2560 × 1440 (retina). README displays it at 50%
  width, so detail must survive 1280 × 720.
- **Browser**: Chrome or Safari, full screen, dark mode.
- **No window chrome** — crop the screenshot to the dashboard area
  only. macOS: `Cmd+Shift+5` → select area.
- **Mouse cursor**: hidden.
- **File format**: PNG, optimised with `pngquant --quality=85-95
  --speed 1`.
- **Target size**: < 500 KB.

## Pre-capture checklist

```sh
docker compose up                                # full stack
PENUMBRA_SEED=2026 uv run python -m penumbra.simulation  # consistent layout
# Wait ~5 min so all tiles have non-empty values and the chain has > 5 blocks
# Activate FL: POST /federated/start, run a few rounds
# Activate logistics: ensure stockouts > 0 and orders pending
```

## File path

Save as `docs/hero.png`. The README already references it as
`![hero](docs/hero.png)`.

## Status

(Maintainer: complete before the OSS launch announcement. Track in
OSS_LAUNCH_ROADMAP.md week 3 deliverables.)
