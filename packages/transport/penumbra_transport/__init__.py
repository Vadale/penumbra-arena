"""Penumbra HTTP + WebSocket transport layer.

Concept taught: lifespan-managed background tasks and WebSocket fan-out.
The tick loop lives here (not in core), so the domain stays pure and
testable without an event loop.
"""

from penumbra_transport.api import build_app
from penumbra_transport.framing import decode_frame, encode_frame

__all__ = ["build_app", "decode_frame", "encode_frame"]
