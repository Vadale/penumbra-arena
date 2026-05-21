# penumbra-transport

The async edge of the system: FastAPI app, WebSocket fan-out, and
the runtime orchestrator that wires the simulation to the chain,
the encrypted heatmap, and the analytics pipeline.

## Concept taught

- **`api.py`** — FastAPI lifespan owns every background task. When
  uvicorn starts the app, the lifespan starts the tick loop + the
  block-production loop + the encrypted-heatmap loop + the analytics
  pipeline. When uvicorn shuts down, the lifespan cancels them
  cleanly. No global state, no atexit hooks.
- **`hub.py`** — WebSocket fan-out with **bounded back-pressure**.
  Each subscriber has a 16-deep msgpack queue; if it overflows the
  client is dropped so the producer never blocks. This is the most
  common production-grade pattern for streaming systems.
- **`loop.py`** — wraps the synchronous `Simulation.tick()` in an
  asyncio task at a fixed cadence (10 Hz). Each frame fans out
  through the hub.
- **`orchestrator.py`** — the integration seam. Connects:
   - `Simulation.on_match_end` → mempool submit → chain block
   - 1 Hz CKKS encryption of agent positions → encrypted aggregate
   - 1 Hz analytics pipeline observation → consumer recompute
- **`encrypted_heatmap.py`** — load-bearing demo of CKKS in
  production. Each tick: per-agent one-hot encryption → ciphertext
  sum → decrypt aggregate. Per-agent positions never appear in
  plaintext server-side.
- **`coach.py`** — allow-list-restricted subprocess runner for the
  in-dashboard Coach panel. Only `pna` and `psh` first tokens
  accepted; 30s hard timeout; shlex tokenisation (never `shell=True`).
- **`framing.py`** — msgpack wire format for WS frames. ~5x smaller
  than equivalent JSON for the dict-of-int-positions payload.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | service status |
| GET | `/state` | current TickFrame snapshot |
| POST | `/control/{pause,resume,step,time-warp/N}` | lifecycle |
| GET | `/chain/{latest,blocks,block/{hash}}` | chain explorer |
| GET | `/encrypted-heatmap` | latest CKKS-decrypted density |
| GET | `/dashboard` | streaming-analytics snapshot |
| POST | `/coach/exec` | run pna/psh from the browser (allow-list) |
| GET | `/coach/presets` | curated button payload |
| WS | `/ws` | per-tick msgpack frame stream |

## Micro-experiments

1. Watch the integration seam at work:
   ```sh
   PENUMBRA_SEED=42 uv run uvicorn penumbra_transport.api:app --port 8100
   # in another terminal:
   curl localhost:8100/chain/latest         # blocks accumulate every ~10s
   curl localhost:8100/encrypted-heatmap    # density updates every 1s
   curl localhost:8100/dashboard            # consumers fill in over ~50s
   ```
2. Drop a slow client:
   ```sh
   # connect to /ws but never consume — watch the back-pressure log
   # message after the queue fills (16 frames).
   ```
