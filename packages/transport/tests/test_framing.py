"""Framing roundtrip tests."""

from __future__ import annotations

from penumbra_core.match import MatchStatus
from penumbra_core.simulation import TickFrame
from penumbra_transport.framing import decode_frame, encode_frame


def _frame() -> TickFrame:
    return TickFrame(
        tick=42,
        match_id=3,
        match_status=MatchStatus.RUNNING,
        agent_positions={1: 7, 2: 12},
        arena_edge_count=130,
        arena_goals=[4, 9, 17],
    )


def test_roundtrip_preserves_payload() -> None:
    decoded = decode_frame(encode_frame(_frame()))
    assert decoded["tick"] == 42
    assert decoded["match_id"] == 3
    assert decoded["match_status"] == "running"
    assert decoded["agent_positions"] == {1: 7, 2: 12}
    assert decoded["arena_edge_count"] == 130
    assert decoded["arena_goals"] == [4, 9, 17]


def test_payload_is_compact() -> None:
    """msgpack should be smaller than the equivalent JSON representation."""
    import json

    blob = encode_frame(_frame())
    json_blob = json.dumps(
        {
            "tick": 42,
            "match_id": 3,
            "match_status": "running",
            "agent_positions": {"1": 7, "2": 12},
            "arena_edge_count": 130,
            "arena_goals": [4, 9, 17],
        }
    ).encode()
    assert len(blob) < len(json_blob)
