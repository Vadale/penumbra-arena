"""WebSocket fan-out hub.

Concept taught: bounded back-pressure. A slow WebSocket client must not
slow the tick loop. Each client gets a small bounded queue; if the queue
overflows the client is dropped (the frontend can reconnect). This keeps
the loop honest at the cost of frame drops for unhealthy clients.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_QUEUE_DEPTH = 16


@dataclass(slots=True, eq=False)
class _Subscriber:
    websocket: WebSocket
    queue: asyncio.Queue[bytes]


class Hub:
    """Broadcasts opaque payloads to subscribed WebSocket clients."""

    def __init__(self) -> None:
        self._subscribers: set[_Subscriber] = set()
        self._lock = asyncio.Lock()

    async def attach(self, websocket: WebSocket) -> _Subscriber:
        sub = _Subscriber(websocket=websocket, queue=asyncio.Queue(maxsize=_QUEUE_DEPTH))
        async with self._lock:
            self._subscribers.add(sub)
        return sub

    async def detach(self, sub: _Subscriber) -> None:
        async with self._lock:
            self._subscribers.discard(sub)

    async def broadcast(self, payload: bytes) -> None:
        """Push `payload` into every subscriber's queue, dropping any that overflow."""
        async with self._lock:
            subs = list(self._subscribers)
        casualties: list[_Subscriber] = []
        for sub in subs:
            try:
                sub.queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("subscriber queue full; dropping client")
                casualties.append(sub)
        for sub in casualties:
            await self.detach(sub)
            with contextlib.suppress(RuntimeError):
                await sub.websocket.close(code=1011, reason="back-pressure")

    async def pump(self, sub: _Subscriber) -> None:
        """Drain `sub.queue` into the WebSocket; raises on disconnect."""
        while True:
            payload = await sub.queue.get()
            await sub.websocket.send_bytes(payload)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
