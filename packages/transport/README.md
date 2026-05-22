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

### Core

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | service status |
| GET | `/state` | current TickFrame snapshot |
| GET | `/arena/topology` | nodes + edges + goals |
| POST | `/control/{pause,resume,step,time-warp/N}` | lifecycle |
| GET | `/chain/{latest,blocks,block/{hash}}` | chain explorer |
| GET | `/encrypted-heatmap` | latest CKKS-decrypted density |
| GET | `/dashboard` | streaming-analytics snapshot |
| POST | `/coach/exec` | run pna/psh from the browser (allow-list) |
| GET | `/coach/presets` | curated button payload |
| GET | `/dp/budget` | DP accountant state |
| WS | `/ws` | per-tick msgpack frame stream |

### Phase 8 dashboard panels

| Method | Path | Purpose |
|---|---|---|
| GET | `/dp/compare` | clean vs DP-noised heatmap + δ |
| GET | `/chain/vrf-leader` | validator set + recent leaders |
| GET | `/chain/mempool` | pending outcomes + slashings |
| GET | `/chain/bls/{hash}` | BLS aggregate sig + verify |
| POST | `/chain/_demo/self-slash[?validator_index=N]` | forge equivocation |
| GET | `/crypto/zk/legal-path` | Groth16 verify (cached) |
| GET | `/crypto/ckks/compare` | encrypt/decrypt round-trip |
| GET | `/crypto/kyber/demo` | ML-KEM-768 keygen/encaps/decaps |
| GET | `/crypto/vdf/demo[?delay=N]` | Wesolowski VDF timing |
| GET | `/crypto/dilithium/inspect/{id}` | per-agent sig demo |
| GET | `/crypto/shamir/demo[?n=N&t=T]` | secret sharing demo |
| GET | `/crypto/tfhe/demo` | LWE bit gates demo |
| GET | `/learning/policy/{id}` | actor probs + chosen action |
| GET | `/learning/runtime` | temp/deterministic/enabled |
| POST | `/learning/temperature/{value}` | mutate sampling temp |
| POST | `/learning/enabled/{bool}` | A/B MAPPO ↔ random |
| GET | `/learning/action-histogram` | swarm action mix |
| GET | `/learning/value-map` | V(s) + per-agent entropy |
| GET | `/learning/saliency/{id}` | ∂p/∂x per feature |
| GET | `/learning/gat-attention` | GATv2 attention rows |
| POST | `/learning/multi-checkpoint/{name}` | load second actor |
| GET | `/learning/ab-compare` | KL + agreement vs second |
| GET/POST | `/learning/reward-weights` | live reward shaping |
| GET/POST | `/learning/training/{status,start,stop,curves}` | live PPO |
| GET | `/world/list` · POST `/world/{save,load}` | snapshots |

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
