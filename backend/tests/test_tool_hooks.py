"""F4 tool hooks — slim_for_working always on."""

from agent_window.core.tool_hooks import observe_for_working, slim_for_working


def test_slim_for_working_delegates_to_observation() -> None:
    raw = '{"status":"ok","content":"' + ("x" * 5000) + '"}'
    obs = observe_for_working("read_file", raw)
    slim = slim_for_working("read_file", raw)
    assert slim == obs.model_payload
    assert len(slim) < len(raw)
    assert obs.truncated is True
    assert obs.display_summary.endswith("(truncated)")
