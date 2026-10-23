"""EventSink Pipe A behaviour (A3)."""

from __future__ import annotations

from agent_window.core.event_sink import LIFECYCLE_TYPES, EventSink


def test_subscriber_receives_emit_copy() -> None:
    sink = EventSink()
    seen: list[dict] = []

    def sub(ev: dict) -> None:
        seen.append(ev)
        ev["mutated"] = True

    sink.subscribe(sub)
    original = {"type": "turn_start", "index": 0}
    sink.emit(original)

    assert len(seen) == 1
    assert seen[0]["type"] == "turn_start"
    assert seen[0]["index"] == 0
    # reverse: subscriber must not mutate the caller's dict
    assert "mutated" not in original
    assert original is not seen[0]


def test_broken_subscriber_does_not_block_others() -> None:
    sink = EventSink()
    ok: list[str] = []

    def bad(_ev: dict) -> None:
        raise RuntimeError("boom")

    def good(ev: dict) -> None:
        ok.append(str(ev.get("type")))

    sink.subscribe(bad)
    sink.subscribe(good)
    sink.emit({"type": "agent_start"})

    assert ok == ["agent_start"]
    # reverse
    assert "boom" not in ok
    assert len(ok) != 0


def test_unsubscribe_stops_delivery() -> None:
    sink = EventSink()
    hits: list[int] = []

    def sub(_ev: dict) -> None:
        hits.append(1)

    unsub = sink.subscribe(sub)
    sink.emit({"type": "token", "content": "a"})
    assert len(hits) == 1

    unsub()
    sink.emit({"type": "token", "content": "b"})
    assert len(hits) == 1
    # reverse: not still subscribed
    assert len(hits) != 2


def test_lifecycle_types_export() -> None:
    assert "agent_start" in LIFECYCLE_TYPES
    assert "turn_end" in LIFECYCLE_TYPES
    # reverse
    assert "token" not in LIFECYCLE_TYPES
    assert "tool_start" not in LIFECYCLE_TYPES
