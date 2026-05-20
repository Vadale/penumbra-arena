# penumbra-transport

FastAPI + WebSocket transport layer. Drives the perpetual simulation tick
loop on a background asyncio task and broadcasts each frame to all
connected clients as msgpack.

## Concept taught

- **Lifespan-managed background tasks** — the tick loop is owned by
  FastAPI's `lifespan` context manager. When the app starts, the loop
  starts; when the app shuts down, the loop is cancelled cleanly.
- **WebSocket fan-out** — a thread-safe set of clients receives every
  frame; slow consumers are dropped to keep the loop honest.
- **msgpack on the wire** — binary, schema-free, ~5× smaller than JSON
  for the dict-of-int-positions payload typical of Penumbra.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | service status + uptime + tick count |
| GET | `/state` | current `TickFrame` snapshot |
| POST | `/control/pause` | pause the tick loop |
| POST | `/control/resume` | resume |
| POST | `/control/step` | execute exactly one tick |
| POST | `/control/time-warp/{n}` | set the time_warp multiplier |
| WS | `/ws` | stream every `TickFrame` as msgpack |

## Public API

```python
from penumbra_transport.api import build_app
from penumbra_transport.framing import encode_frame, decode_frame
```
