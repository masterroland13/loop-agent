"""A4: default_convert_to_llm — pass-through + compaction_summary mapping."""

from __future__ import annotations

from agent_window.core.loop_config import LoopConfig
from agent_window.core.messages import AgentMessage, COMPACTION_SUMMARY_MARKER, default_convert_to_llm


def test_pass_through_user_assistant_system() -> None:
    msgs = [
        AgentMessage(role="system", content="sys"),
        AgentMessage(role="user", content="hi", id="u1"),
        AgentMessage(role="assistant", content="hello", id="a1"),
    ]
    out = default_convert_to_llm(msgs)
    assert out == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    assert not any(m.get("role") == "compaction_summary" for m in out)
    assert out[1]["role"] != "assistant"


def test_compaction_summary_maps_to_user_with_marker() -> None:
    body = "## Goal\nFix import\n## Constraints\nNone"
    msgs = [AgentMessage(role="compaction_summary", content=body)]
    out = default_convert_to_llm(msgs)
    assert len(out) == 1
    assert out[0]["role"] == "user"
    assert out[0]["role"] != "system"
    assert out[0]["role"] != "compaction_summary"
    assert out[0]["content"].startswith(COMPACTION_SUMMARY_MARKER)
    assert "Fix import" in out[0]["content"]
    assert not out[0]["content"].startswith("## Goal")


def test_compaction_summary_keeps_existing_marker() -> None:
    content = f"{COMPACTION_SUMMARY_MARKER}\nalready marked"
    out = default_convert_to_llm([AgentMessage(role="compaction_summary", content=content)])
    assert out[0]["content"].count(COMPACTION_SUMMARY_MARKER) == 1
    assert "already marked" in out[0]["content"]


def test_loop_config_defaults_convert_to_llm() -> None:
    cfg = LoopConfig.default()
    assert cfg.convert_to_llm is not None
    assert cfg.convert_to_llm is default_convert_to_llm or cfg.convert_to_llm == default_convert_to_llm
    mapped = cfg.convert_to_llm([AgentMessage(role="user", content="x")])
    assert mapped == [{"role": "user", "content": "x"}]
    assert mapped != [{"role": "assistant", "content": "x"}]

    cfg2 = LoopConfig(convert_to_llm=None)
    assert cfg2.convert_to_llm is not None
    out = cfg2.convert_to_llm([AgentMessage(role="compaction_summary", content="s")])
    assert out[0]["role"] == "user"
    assert COMPACTION_SUMMARY_MARKER in out[0]["content"]
