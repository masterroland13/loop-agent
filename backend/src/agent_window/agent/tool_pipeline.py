"""Five-step tool pipeline (charter M05 / Gate 深拆 Step 3).

Conceptual steps:
  1. prepare — normalize; for propose_* create pending (AWAIT_* intent only)
  2. validate — non-empty name; gate prepare must look like a proposal or error
  3. before_tool_call (phase=pre) — allow | wait | block
  4. settle (phase=await_gate) — for gate tools only: pending SSE + wait/auto-apply
     (this is Pipe B; apply happens here via decide_* / wait_for_*)
  5. execute — non-gate tools only (``handle_function_call``)
  6. after_tool_call

Gate tools never re-enter execute after prepare; loop only consumes SSE + results.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Optional

from agent_window.agent.gate_policy import GATE_TOOL_NAMES
from agent_window.core.loop_config import LoopConfig


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _blocked_result(reason: str) -> str:
    return json.dumps(
        {"status": "blocked", "error": reason, "blocked": True},
        ensure_ascii=False,
    )


async def run_tool_steps(
    name: str,
    raw_args: Any,
    *,
    config: LoopConfig,
    cancel_event: Optional[Any] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Run prepare → validate → before → settle|execute → after; yield events.

    Yields:
      - SSE from gate settle (diff / shell / memory / await_approval)
      - ``{"type": "_gate_meta", "kind": ...}`` when a gate tool was settled
      - ``{"type": "_tool_result", "content": <str>}`` final tool JSON
    """
    from agent_window.agent.gate_hooks import (
        abandon_await_proposal,
        await_marker_kind,
        resolve_await_marker,
        still_has_await_marker,
    )
    from agent_window.core.preset_hooks import resolve_gate_decision

    # 1. prepare
    tool_name = (name or "").strip() if isinstance(name, str) else str(name or "").strip()
    args = raw_args
    is_gate = tool_name in GATE_TOOL_NAMES
    prepared_raw: Optional[str] = None
    prepared_gate: Optional[Dict[str, Any]] = None

    # 2. validate
    if not tool_name:
        yield {
            "type": "_tool_result",
            "content": json.dumps(
                {"status": "failed", "error": "tool name is required"},
                ensure_ascii=False,
            ),
        }
        return

    from agent_window.agent import loop as loop_mod

    if is_gate:
        # prepare = propose_* only (create pending + AWAIT intent)
        prepared_raw = await loop_mod.handle_function_call(tool_name, args)
        prepared_gate = _try_parse_json(prepared_raw) if isinstance(prepared_raw, str) else None
        gate_kind = await_marker_kind(prepared_gate)
        if gate_kind is None:
            # Prepare failed (validation / workspace error) — no settle
            content = prepared_raw or json.dumps(
                {"status": "failed", "error": "gate prepare produced no result"},
                ensure_ascii=False,
            )
            if config.after_tool_call is not None:
                await config.after_tool_call(
                    name=tool_name,
                    arguments=args,
                    result=content,
                    config=config,
                )
            yield {"type": "_tool_result", "content": content}
            return
    else:
        gate_kind = None

    # 3. before_tool_call (phase=pre) — may block before settle/execute
    decision = await resolve_gate_decision(
        config,
        name=tool_name,
        arguments=args,
        phase="pre",
        await_payload=prepared_gate,
        cancel_event=cancel_event,
    )
    if decision.action == "block":
        reason = decision.reason or "blocked by before_tool_call"
        if prepared_gate is not None:
            await abandon_await_proposal(prepared_gate)
        content = _blocked_result(reason)
        if config.after_tool_call is not None:
            await config.after_tool_call(
                name=tool_name,
                arguments=args,
                result=content,
                config=config,
            )
        yield {"type": "_tool_result", "content": content}
        return

    # 4. settle gate (before execute) OR 5. execute non-gate
    if prepared_gate is not None and gate_kind is not None:
        await_decision = await resolve_gate_decision(
            config,
            name=tool_name,
            arguments=args,
            phase="await_gate",
            await_payload=prepared_gate,
            cancel_event=cancel_event,
        )
        if await_decision.action == "block":
            reason = await_decision.reason or "blocked by before_tool_call"
            await abandon_await_proposal(prepared_gate)
            content = _blocked_result(reason)
        else:
            auto_apply = bool(
                await_decision.auto_apply or await_decision.action == "allow"
            )
            content = prepared_raw or ""
            async for event, maybe_result in resolve_await_marker(
                prepared_gate,
                cancel_event,
                auto_apply=auto_apply,
                force_confirm_memory=await_decision.force_confirm_memory,
            ):
                if event.get("type") == "_result":
                    content = maybe_result or content
                else:
                    yield event
        yield {"type": "_gate_meta", "kind": gate_kind}

        if still_has_await_marker(_try_parse_json(content if isinstance(content, str) else "")):
            content = json.dumps(
                {
                    "status": "failed",
                    "error": "approval gate did not complete; edit/command was not applied",
                },
                ensure_ascii=False,
            )
    else:
        # 5. execute — read-only / non-gate tools
        content = await loop_mod.handle_function_call(tool_name, args)

    # 6. after_tool_call
    if config.after_tool_call is not None:
        await config.after_tool_call(
            name=tool_name,
            arguments=args,
            result=content,
            config=config,
        )

    yield {"type": "_tool_result", "content": content}
