"""Wire format for tick frames.

Concept taught: choose your serialisation by payload shape. msgpack beats
JSON ~5x for dict-of-int payloads (which the Penumbra TickFrame is) and
matches JSON for nested strings. Schema-free is fine here because the
frontend type-checks the inbound shape via a TS schema (see
apps/web/src/streams/frames.ts).
"""

from __future__ import annotations

from typing import Any, cast

import msgpack
from penumbra_core.simulation import TickFrame


def encode_frame(frame: TickFrame) -> bytes:
    """Pack a `TickFrame` into msgpack bytes for the WebSocket."""
    payload: dict[str, Any] = {
        "tick": frame.tick,
        "match_id": frame.match_id,
        "match_status": frame.match_status.value,
        "agent_positions": dict(frame.agent_positions),
        "arena_edge_count": frame.arena_edge_count,
        "arena_goals": list(frame.arena_goals),
    }
    return cast(bytes, msgpack.packb(payload, use_bin_type=True))


def decode_frame(blob: bytes) -> dict[str, Any]:
    """Unpack msgpack bytes back to a plain dict.

    Returns a plain dict rather than a `TickFrame` because consumers
    (e.g. tests, the React WS client via pyodide in hypothetical
    scenarios) shouldn't have to import the domain dataclass.
    """
    return cast(dict[str, Any], msgpack.unpackb(blob, raw=False, strict_map_key=False))
