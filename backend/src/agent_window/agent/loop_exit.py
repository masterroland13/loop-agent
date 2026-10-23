"""Loop exit helpers: honest empty replies + edit-intent nudge (not soft-land).

Keeps ``loop.py`` thinner. Intent heuristics are deliberately conservative:
force ``propose_edit`` only when the user clearly asked to change the repo —
never for pure explore / Q&A / soft-land budget exhaustion.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from agent_window.agent.exploration import EXPLORATION_TOOLS

# Strong edit/delete signals only (avoid matching「看看 SettingsPanel 干什么」).
_EDIT_INTENT_RE = re.compile(
    r"("
    r"propose_edit|propose_delete|"
    r"用\s*propose_edit|"
    r"必须调用\s*propose_edit|"
    r"禁止只读收工|"
    r"不要只声称完成|"
    r"只改前端|只改后端|"
    r"(请|要|务必|必须).{0,16}(改|修改|编辑|实现|修复|添加|增加|保存|写入|落盘).{0,40}"
    r"(文件|代码|组件|面板|页面|前端|后端|仓库|工作区|workspace|附件)?|"
    r"(把|将).{0,24}(附件|attachment).{0,24}(保存|写入|落盘|存到|放到).{0,40}"
    r"(工作区|workspace|仓库|文件)|"
    r"(保存|写入|落盘).{0,24}(附件|attachment).{0,40}"
    r"(工作区|workspace|仓库|文件)|"
    r"(改|修改|编辑|实现|修复|落地).{0,40}"
    r"(SettingsPanel|MemoryPanel|[\w./-]+\.(?:tsx?|jsx?|py|css))|"
    r"\b(implement|patch)\b|"
    r"\b(fix|edit|change|modify|update)\s+(the\s+)?(file|code|component|ui|settings)\b|"
    r"\b(save|write|persist)\s+(the\s+)?(attachment|file)\b|"
    r"\bedit\s+[\w./-]+\.(?:tsx?|jsx?|py)\b"
    r")",
    re.IGNORECASE | re.DOTALL,
)

# Pure look-up / explain — weakens edit intent when no propose_edit literal.
_EXPLORE_ONLY_RE = re.compile(
    r"("
    r"^(列出|看看|看下|查看|解释|说明|是什么|干什么|怎么工作)"
    r"|^(what|where|why|how|explain|show|list)\b"
    r"|只(读|看|查)|不要改|别改|先不要改|不用改文件"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

EDIT_NUDGE_MARKER = "【收工检查】"

EMPTY_RESPONSE_MESSAGE = (
    "模型既未调用工具也未返回任何文字（EMPTY_RESPONSE）。"
    "常见原因：网关空包、模型异常、或上下文过长。"
    "请重试；若反复出现，请换模型档案或新开会话。"
)


def last_user_texts(working: Sequence[Dict[str, Any]], *, limit: int = 6) -> List[str]:
    out: List[str] = []
    for msg in reversed(list(working or [])):
        if msg.get("role") != "user":
            continue
        text = msg.get("content")
        if text is None:
            continue
        s = str(text).strip()
        if s:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def collect_intent_corpus(
    working: Sequence[Dict[str, Any]],
    turn_goal: Optional[str] = None,
) -> str:
    parts: List[str] = []
    g = (turn_goal or "").strip()
    if g:
        parts.append(g)
    parts.extend(last_user_texts(working, limit=5))
    return "\n".join(parts)


def user_requests_repo_edit(
    text: str,
    *,
    turn_goal: Optional[str] = None,
) -> bool:
    """True when the user clearly asked to change repository files."""
    blob = "\n".join(p for p in [(turn_goal or "").strip(), (text or "").strip()] if p)
    if not blob:
        return False
    if "propose_edit" in blob.lower() or "propose_delete" in blob.lower():
        return True
    if _EDIT_INTENT_RE.search(blob):
        # 「看看 X 文件」alone should not force edit when matched weakly via path —
        # require explore-only soft veto only when no strong tool name.
        if _EXPLORE_ONLY_RE.search(blob) and not re.search(
            r"propose_edit|propose_delete|落地|实现|修复|修改文件|改前端|改后端|"
            r"保存.{0,12}附件|附件.{0,12}保存|写入.{0,12}工作区|保存.{0,12}workspace",
            blob,
            re.IGNORECASE,
        ):
            return False
        return True
    return False


def working_requests_repo_edit(
    working: Sequence[Dict[str, Any]],
    turn_goal: Optional[str] = None,
) -> bool:
    return user_requests_repo_edit(
        collect_intent_corpus(working, turn_goal),
        turn_goal=turn_goal,
    )


def format_missing_edit_nudge(*, turn_goal: Optional[str] = None) -> str:
    goal_line = f"\n本轮目标：{turn_goal.strip()}" if turn_goal and turn_goal.strip() else ""
    return (
        f"{EDIT_NUDGE_MARKER}{goal_line}\n"
        "本轮用户意图包含**修改仓库文件**，但尚未调用 `propose_edit` / `propose_delete`。"
        "禁止以空回复结束。下一次必须二选一：\n"
        "1) 调用 `propose_edit`（或 `propose_delete`）提出具体改动；或\n"
        "2) 用**非空文字**说明阻塞（路径不明 / 范围过大 / 缺信息等）。\n"
        "禁止仅继续 `list_dir` / `read_file` / `grep` 空转。"
    )


def synthesize_tools_only_reply(
    turn_goal: Optional[str] = None,
    *,
    write_gate_seen: bool = False,
    edit_intent: bool = False,
    edit_nudge_used: bool = False,
) -> str:
    """Honest fallback when the model stops with tools but empty narration."""
    goal_line = f"本轮目标：{turn_goal.strip()}。" if turn_goal and turn_goal.strip() else ""
    if edit_intent and not write_gate_seen:
        nudged = (
            "已自动催促过一次仍未提出文件修改。"
            if edit_nudge_used
            else ""
        )
        return (
            "本轮工具轨迹里**没有** `propose_edit` / `propose_delete`，仓库文件未改，任务未完成。"
            + ((" " + nudged) if nudged else "")
            + ((" " + goal_line) if goal_line else "")
            + " 请继续要求模型调用 `propose_edit` 落地，或说明是否改为只读任务。"
        )
    if write_gate_seen:
        return (
            "工具（含文件/命令审批）已跑过，但模型未给出文字说明。"
            + ((" " + goal_line) if goal_line else "")
            + " 请说明你希望下一步怎么做，或是否对照目标收工。"
        )
    return (
        "本轮只做了查阅类工具，模型未给出文字说明。"
        + ((" " + goal_line) if goal_line else "")
        + " 若你本来只要看代码，可据此结束；若要改文件，请明确要求并等待 `propose_edit`。"
    )


def should_nudge_missing_edit(
    *,
    edit_intent: bool,
    write_gate_seen: bool,
    edit_nudge_used: bool,
    tools_ran: int,
    has_content: bool,
) -> bool:
    """One-shot continue when edit was requested but the model exits empty without a patch gate."""
    if has_content:
        return False
    if not edit_intent or write_gate_seen or edit_nudge_used:
        return False
    return tools_ran > 0


def exploration_tool_names() -> frozenset[str]:
    return EXPLORATION_TOOLS
