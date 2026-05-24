"""Async wrapper around the synchronous `Simulation.tick()`.

Concept taught: keeping I/O at the edge. The simulation itself is pure
Python and synchronous — easy to property-test. Here we wrap it in an
asyncio task that ticks at a fixed wall-clock cadence and broadcasts each
frame to subscribers. The wrapper is the *only* place asyncio touches
the domain.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

from penumbra_core.simulation import Simulation, TickFrame

logger = logging.getLogger(__name__)

FrameConsumer = Callable[[TickFrame], Awaitable[None]]


class TickLoop:
    """Drives a `Simulation` at a fixed cadence and pushes frames to consumers.

    The loop respects the simulation's pause/resume state. While paused
    the loop continues to sleep, so resuming is immediate.
    """

    def __init__(
        self,
        simulation: Simulation,
        consumer: FrameConsumer,
        *,
        tick_hz: float = 10.0,
    ) -> None:
        self._simulation = simulation
        self._consumer = consumer
        self._tick_hz = float(tick_hz)
        self._period = 1.0 / tick_hz
        self._task: asyncio.Task[None] | None = None
        self._started_at: float | None = None

    @property
    def simulation(self) -> Simulation:
        return self._simulation

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def tick_hz(self) -> float:
        """Current tick rate in hertz."""
        return self._tick_hz

    def set_tick_hz(self, hz: float) -> None:
        """Update the tick rate live.

        Thread-safe by virtue of CPython's GIL: assigning a float is atomic
        and the next ``await asyncio.sleep(self._period)`` in ``_run`` picks
        the new value up on its next iteration.
        """
        if not hz > 0:
            raise ValueError(f"tick_hz must be positive, got {hz}")
        self._tick_hz = float(hz)
        self._period = 1.0 / float(hz)

    def uptime_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.monotonic() - self._started_at

    async def start(self) -> None:
        if self.is_running:
            return
        self._started_at = time.monotonic()
        self._task = asyncio.create_task(self._run(), name="penumbra-tick-loop")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        # Periodic gc inside the hot tick loop. MAPPO inference on MPS
        # allocates temporaries the autograd-disabled forward path
        # still holds via the C++ caching allocator until the next
        # generation collect. Without this, RSS climbs ~400 MB/h.
        import gc

        tick_count = 0
        try:
            while True:
                frame = self._simulation.tick()
                if frame is not None:
                    try:
                        await self._consumer(frame)
                    except Exception:
                        logger.exception("frame consumer raised; continuing")
                tick_count += 1
                if tick_count % 100 == 0:  # every 10s at 10 Hz
                    gc.collect()
                await asyncio.sleep(self._period)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("tick loop crashed")
            raise
