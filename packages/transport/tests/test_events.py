"""EventBus core tests (Phase 6a Tier 1)."""

from __future__ import annotations

from penumbra_transport.events import Event, EventBus


def test_subscribe_then_emit_calls_handler() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe("foo", seen.append)
    bus.emit(Event(kind="foo", tick=1, payload={"x": 1}))
    assert len(seen) == 1
    assert seen[0].payload == {"x": 1}


def test_subscribe_is_idempotent() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe("foo", seen.append)
    bus.subscribe("foo", seen.append)  # re-subscribe
    bus.emit(Event(kind="foo", tick=1))
    assert len(seen) == 1  # handler called once, not twice


def test_unsubscribe_removes_handler() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe("foo", seen.append)
    bus.unsubscribe("foo", seen.append)
    bus.emit(Event(kind="foo", tick=1))
    assert seen == []


def test_emit_unknown_kind_is_noop() -> None:
    bus = EventBus()
    bus.emit(Event(kind="nothing-subscribed", tick=1))  # no exception
    assert len(bus.recent()) == 1  # still recorded in history


def test_handler_exception_does_not_kill_bus() -> None:
    bus = EventBus()

    def bad_handler(_: Event) -> None:
        raise RuntimeError("boom")

    seen: list[Event] = []
    bus.subscribe("foo", bad_handler)
    bus.subscribe("foo", seen.append)
    bus.emit(Event(kind="foo", tick=1))
    assert len(seen) == 1  # the good handler still ran
    handler_stats: dict[str, dict[str, object]] = bus.stats()["handler_stats"]  # type: ignore[assignment]
    assert handler_stats["foo"]["n_errors"] == 1


def test_handler_emit_inside_handler_is_deferred() -> None:
    """Recursive emit must be queued for next drain, not loop forever."""
    bus = EventBus()
    seen_b: list[Event] = []

    def handler_a(_: Event) -> None:
        bus.emit(Event(kind="b", tick=1))

    bus.subscribe("a", handler_a)
    bus.subscribe("b", seen_b.append)
    bus.emit(Event(kind="a", tick=1))
    # The recursive emit drains AFTER handler_a returns, in the same
    # outer emit() call. Verify the b handler ran.
    assert len(seen_b) == 1


def test_history_bounded() -> None:
    bus = EventBus()
    for i in range(2000):
        bus.emit(Event(kind="ping", tick=i))
    assert len(bus.recent(limit=10_000)) <= 1024


def test_stats_records_emit_counts_and_latency() -> None:
    bus = EventBus()
    bus.subscribe("foo", lambda _e: None)
    for i in range(50):
        bus.emit(Event(kind="foo", tick=i))
    stats: dict[str, object] = bus.stats()
    emit_counts: dict[str, int] = stats["emit_counts"]  # type: ignore[assignment]
    handler_stats: dict[str, dict[str, object]] = stats["handler_stats"]  # type: ignore[assignment]
    assert emit_counts["foo"] == 50
    assert handler_stats["foo"]["n_calls"] == 50
    assert float(handler_stats["foo"]["p99_us"]) >= 0.0  # type: ignore[arg-type]


def test_clear_resets_all_state() -> None:
    bus = EventBus()
    bus.subscribe("foo", lambda _e: None)
    bus.emit(Event(kind="foo", tick=1))
    bus.clear()
    stats: dict[str, object] = bus.stats()
    assert stats["history_size"] == 0
    assert stats["emit_counts"] == {}
