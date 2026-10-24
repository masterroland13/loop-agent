"""Context compression helpers (A4 / M09 Compaction upgrade).

Primary path: Pi-style 6-section LLM summary with cut-point + keepRecent.
Fallback: extractive 6-section built from older turns (never placeholder-only).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from agent_window.core.messages import COMPACTION_SUMMARY_MARKER

logger = logging.getLogger(__name__)

SummarizeFn = Callable[[str], Awaitable[str]]

# Leave headroom under the hard context limit before triggering compress.
DEFAULT_TOKEN_RESERVE = 1024
DEFAULT_KEEP_RECENT_TOKENS = 2048
# Folded-span user originals kept after the summary (near → far, token cap).
DEFAULT_KEEP_FOLDED_USER_TOKENS = 8192

SIX_SECTIONS = (
    "Goal",
    "Constraints",
    "Progress",
    "Key Decisions",
    "Next Steps",
    "Critical Context",
)

# Codex-style framing for the model that resumes after compaction.
COMPACTION_HANDOFF_PREFIX = (
    "此前另一段对话已被压缩。请依据下列结构化摘要续作，勿重复已完成的探索；"
    "需要细节时优先用工具重读 Critical Context 中的路径。"
)

_SIX_SECTION_PROMPT = """你正在做 CONTEXT CHECKPOINT / 交接摘要：给将要续作的另一模型写结构化交接包（不是复述任务单）。
必须且只输出这六个小节（标题保持英文）：
## Goal
## Constraints
## Progress
## Key Decisions
## Next Steps
## Critical Context

硬性规则：
- Goal：一句话写清用户要达成什么；不要把整段用户原话粘贴多遍。
- Constraints：只写硬约束短句（如「只读」「不要改文件」）；禁止粘贴完整任务步骤或与 Goal 同文；没有则写「（无）」。
- Progress：已执行的工具与结论（含路径）。若本段输入里**没有** tool 结果，写「摘要窗口内未见工具结果」并列出用户点名路径；**禁止**写「尚未开始 / 尚无已执行工具」这类全称否定（近端可能还有未压入的工具轮）。禁止只复述用户原话；禁止与 Goal 同文；不要粘贴长篇「短总结」正文。
- Key Decisions：仅已拍板的技术选择（短句）；不要把总结/报告当决策；没有则写「（无）」。
- Next Steps：尚未完成的具体动作。仅当本段已有工具结果且已覆盖最近请求时，才写「（无未完成项；等待用户下一指令）」；禁止在未见工具时写等待。禁止与 Goal / 用户原话同句复读。
- Critical Context：必须列出对话中已读/已提及的文件路径（每行一条 `- path`）。没有路径则写「（无路径）」。可附极短错误信息或关键结论。
- 不要编造未出现的事实。
- 若提供了「上一轮压缩摘要」，请增量合并：保留仍有效的 Constraints；更新 Progress；Critical Context 路径取并集；刷新 Next Steps。
"""

# Path-like tokens for Critical Context / Progress (deterministic extractive).
_PATH_RE = re.compile(
    r"(?:"
    r"(?:[\w.-]+/)+\.?[\w.-]+\.(?:py|md|ts|tsx|js|jsx|json|yml|yaml|toml|txt|rs|go|java|css|html|sh|ps1)"
    r"|"
    r"(?:README|CHANGELOG|AGENTS|LICENSE)(?:\.\w+)?"
    r"|"
    r"(?:docs|backend|frontend|src|tests?)/[\w./-]+"
    r")",
    re.IGNORECASE,
)

_TOOL_PROGRESS_NAMES = frozenset(
    {
        "list_dir",
        "read_file",
        "grep",
        "search_files",
        "glob",
        "propose_edit",
        "propose_shell",
        "read_attachment",
        "propose_memory",
    }
)

# Short hard-constraint labels (never paste full multi-step user asks).
_HARD_CONSTRAINT_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"只读|read[\s-]?only", re.I), "只读"),
    (
        re.compile(
            r"不要改(?:任何)?文件|不得修改|禁止改(?:文件)?|勿改文件|do\s*not\s+modify|don't\s+modify",
            re.I,
        ),
        "不要改文件",
    ),
    (re.compile(r"禁止写|不要写盘|不得写", re.I), "禁止写盘"),
    (re.compile(r"必须用\s*PYTHONPATH", re.I), "必须用 PYTHONPATH=src"),
]

_NEXT_WAITING = "（无未完成项；等待用户下一指令）"
_DECISION_NONE = "（无）"
_PROGRESS_NO_TOOLS_IN_WINDOW = "摘要窗口内未见工具结果（近端可能仍有未压入的工具轮）"

# Dogfood / UI follow-ups that must not become Next Steps targets.
_META_FOLLOWUP_RE = re.compile(
    r"("
    r"原样贴出|按六节|六节原样|压缩摘要|对话压缩摘要|"
    r"列出压缩前|读过的主要文件|turn_meta|compress_preview|"
    r"不要改写|本会话摘要|看看本回话|看看本会话"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CompressMeta:
    """Observability for audit / turn_meta (not fed back to the model)."""

    method: str = "none"  # none | llm | extractive | tail_trim
    summary_preview: str = ""
    older_count: int = 0
    used_previous_summary: bool = False
    cut_index: int = 0
    rest_count: int = 0
    summary_content: str = ""
    kept_folded_user_count: int = 0
    keep_folded_user_tokens: int = DEFAULT_KEEP_FOLDED_USER_TOKENS


def approx_tokens(text: str) -> int:
    return max(1, (len(text or "") + 3) // 4)


def approx_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += approx_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    total += approx_tokens(str(part.get("text") or ""))
                elif part.get("type") == "image_url":
                    # Rough fixed cost for a vision tile (gateway-dependent).
                    total += 1024
        total += 4  # role overhead
    return total


def _is_goal_system_message(msg: Dict[str, Any]) -> bool:
    from agent_window.agent.goal import GOAL_MARKER

    content = msg.get("content")
    return msg.get("role") == "system" and isinstance(content, str) and content.startswith(GOAL_MARKER)


def _split_system_messages(
    messages: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (other_system, goal_system, non_system)."""
    other_system: List[Dict[str, Any]] = []
    goal_system: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for m in messages:
        if _is_goal_system_message(m):
            goal_system.append(m)
        elif m.get("role") == "system":
            other_system.append(m)
        else:
            rest.append(m)
    return other_system, goal_system, rest


def find_cut_index(
    rest: List[Dict[str, Any]],
    *,
    keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS,
) -> int:
    """Index where recent messages begin (older = rest[:cut], recent = rest[cut:]).

    Accumulates token weight from the end. Cut only at role in {user, assistant}
    so we never leave an orphaned mid-turn fragment as the first recent message.
    """
    if not rest:
        return 0
    if keep_recent_tokens <= 0:
        # Keep a minimal recent tail at a valid boundary
        for i in range(len(rest) - 1, -1, -1):
            if rest[i].get("role") in ("user", "assistant"):
                return i
        return max(0, len(rest) - 1)

    accumulated = 0
    candidate = 0
    for i in range(len(rest) - 1, -1, -1):
        accumulated += approx_messages_tokens([rest[i]])
        candidate = i
        if accumulated >= keep_recent_tokens:
            break
    else:
        # Entire rest fits in keep_recent — nothing to summarize
        return 0

    # Snap cut forward to a user/assistant boundary (never start recent on other roles)
    for j in range(candidate, len(rest)):
        if rest[j].get("role") in ("user", "assistant"):
            return j
    return candidate


def _msg_role(msg: Any) -> str:
    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
    if hasattr(role, "value"):
        return str(role.value)
    return str(role or "")


def _msg_as_dict(msg: Any) -> Dict[str, Any]:
    if isinstance(msg, dict):
        return msg
    return {
        "role": _msg_role(msg),
        "content": getattr(msg, "content", None) or "",
        "entry_type": getattr(msg, "entry_type", None) or "message",
    }


def _plain_content(msg: Any) -> str:
    msg = _msg_as_dict(msg) if not isinstance(msg, dict) else msg
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
        return "\n".join(p for p in parts if p).strip()
    return ""


def _is_compaction_message(msg: Any) -> bool:
    as_dict = _msg_as_dict(msg)
    text = _plain_content(as_dict)
    return COMPACTION_SUMMARY_MARKER in text or as_dict.get("entry_type") == "compaction_summary"


def select_folded_user_originals(
    older: List[Any],
    *,
    token_budget: int = DEFAULT_KEEP_FOLDED_USER_TOKENS,
) -> List[Any]:
    """User originals from the folded span, nearest first, then farther if they fit.

    Always keeps the nearest real user when one exists. Skips compaction
    summaries, empty users, assistants, and tool rows.
    """
    candidates: List[Any] = []
    for msg in older:
        if _msg_role(msg) != "user":
            continue
        if _is_compaction_message(msg):
            continue
        if not _plain_content(msg):
            continue
        candidates.append(msg)
    if not candidates:
        return []

    selected: List[Any] = []
    used = 0
    budget = max(0, int(token_budget))
    for msg in reversed(candidates):
        cost = approx_messages_tokens([_msg_as_dict(msg)])
        if not selected:
            selected.append(msg)
            used += cost
            continue
        if used + cost > budget:
            # Near → far prefix: once an older user overflows, drop the rest.
            break
        selected.append(msg)
        used += cost
    selected.reverse()
    return selected


def find_previous_summary(messages: List[Dict[str, Any]]) -> Optional[str]:
    """Most recent compaction summary body in ``messages`` (for incremental merge)."""
    for m in reversed(messages):
        if not _is_compaction_message(m):
            continue
        text = _plain_content(m)
        if text:
            return text
    return None


def _clip_line(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _format_blob_line(msg: Dict[str, Any], *, limit: int = 800) -> str:
    role = str(msg.get("role") or "?")
    name = msg.get("name")
    text = _plain_content(msg)
    if not text:
        return ""
    if _is_compaction_message(msg):
        # Keep a short pointer; full previous summary is attached separately.
        return f"{role}: [previous compaction · {len(text)} chars]"
    prefix = f"{role}:{name}" if isinstance(name, str) and name else role
    return f"{prefix}: {text[:limit]}"


def serialize_messages_for_summary(messages: List[Dict[str, Any]], *, max_chars: int = 12000) -> str:
    lines: List[str] = []
    for m in messages:
        line = _format_blob_line(m)
        if line:
            lines.append(line)
    blob = "\n".join(lines)
    if len(blob) > max_chars:
        return blob[: max_chars - 1] + "…"
    return blob


def collect_touched_paths(messages: List[Dict[str, Any]]) -> List[str]:
    """Deterministic path inventory from message text (order-preserving, deduped)."""
    seen: set[str] = set()
    out: List[str] = []
    for m in messages:
        text = _plain_content(m)
        if not text:
            continue
        for match in _PATH_RE.finditer(text):
            path = match.group(0).strip().rstrip(".,;:)")
            if not path:
                continue
            key = path.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
    return out


def collect_tool_progress(messages: List[Dict[str, Any]]) -> List[str]:
    """Short tool progress lines for Progress section."""
    lines: List[str] = []
    for m in messages:
        if _is_compaction_message(m):
            continue
        if m.get("role") != "tool":
            continue
        name = str(m.get("name") or "tool")
        text = _plain_content(m)
        paths = collect_touched_paths([{"role": "tool", "content": text}])
        path_hint = f" → {', '.join(paths[:4])}" if paths else ""
        if name in _TOOL_PROGRESS_NAMES or name:
            lines.append(f"{name}: {_clip_line(text, 120)}{path_hint}")
    return lines


def _normalize_overlap(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _section_echoes_goal(section_body: str, goal_body: str, *, min_goal_len: int = 24) -> bool:
    """True when section is mostly a restatement of Goal (Codex anti-echo)."""
    sec = _normalize_overlap(section_body)
    goal = _normalize_overlap(goal_body)
    if not sec or not goal:
        return False
    if len(goal) < min_goal_len:
        # Short goals: require near-equality
        return sec == goal or (len(sec) >= 8 and (sec in goal or goal in sec))
    if sec == goal:
        return True
    # Section contains most of goal, or goal contains most of section
    if goal in sec and len(goal) >= min_goal_len:
        return True
    if sec in goal and len(sec) >= min_goal_len:
        return True
    # High character overlap ratio on the shorter string
    shorter, longer = (sec, goal) if len(sec) <= len(goal) else (goal, sec)
    if len(shorter) < min_goal_len:
        return False
    hits = sum(1 for i in range(0, len(shorter), 4) if shorter[i : i + 8] in longer)
    samples = max(1, len(shorter) // 4)
    return (hits / samples) >= 0.72


def _section_has_path(body: str) -> bool:
    return bool(_PATH_RE.search(body or ""))


def extract_hard_constraints(users: List[str]) -> List[str]:
    """Short constraint labels only — never full multi-step task pastes."""
    found: List[str] = []
    seen: set[str] = set()
    for u in users:
        for pat, label in _HARD_CONSTRAINT_RULES:
            if not pat.search(u or ""):
                continue
            if label in seen:
                continue
            seen.add(label)
            found.append(label)
    return found


def _looks_like_task_paste(text: str) -> bool:
    """True for long multi-step user asks dumped into Constraints/Next."""
    t = (text or "").strip()
    if len(t) < 80:
        return False
    step_hits = len(re.findall(r"(?:^|\n)\s*(?:\d+[.)、]|[-*])\s*", t)) + len(
        re.findall(r"依次|步骤|list_dir|read_file|grep", t, re.I)
    )
    return step_hits >= 2 or len(t) > 160


def _looks_like_decision(text: str) -> bool:
    """Short decision-like lines only — reject summary dumps."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t or t in ("（无）", "无", "（尚无明确决策句）"):
        return False
    if len(t) > 100:
        return False
    if "##" in t or "短总结" in t or t.count("。") >= 3:
        return False
    cues = (
        "决定",
        "采用",
        "选择",
        "改为",
        "不用",
        "改用",
        "settled",
        "decided",
        "use ",
        "won't",
        "instead",
    )
    low = t.lower()
    return any(c in low for c in cues)


def _looks_like_summary_dump(text: str) -> bool:
    t = (text or "").strip()
    if len(t) > 140:
        return True
    if "##" in t or "短总结" in t:
        return True
    if t.count("。") >= 3:
        return True
    return False


def _looks_like_false_idle_progress(text: str) -> bool:
    """LLM claims 'nothing started' — often wrong when tools live in keep_recent."""
    t = (text or "").strip()
    if not t:
        return False
    cues = (
        "尚未开始",
        "还未开始",
        "尚无已执行",
        "尚未执行",
        "仅收到指令",
        "任务仅收到",
        "无任何进度",
        "还没有执行",
        "未开始任何",
    )
    return any(c in t for c in cues)


def _is_meta_followup(text: str) -> bool:
    """True for verification asks (paste summary / list files) — not task Next Steps."""
    t = (text or "").strip()
    if not t or len(t) > 220:
        return False
    return bool(_META_FOLLOWUP_RE.search(t))


def _latest_task_user(users: List[str]) -> Optional[str]:
    """Most recent user message that looks like real work, skipping meta checks."""
    for u in reversed(users):
        if not _is_meta_followup(u):
            return u
    return None


def _user_request_mostly_covered(
    user_text: str,
    *,
    paths: List[str],
    tool_lines: List[str],
    assistants: List[str],
) -> bool:
    """Heuristic: latest user ask is largely satisfied — requires tool evidence in window."""
    if not user_text.strip():
        return False
    # Path overlap alone is insufficient: user text often names the same paths it asks to read.
    if not tool_lines:
        return False
    user_paths = collect_touched_paths([{"role": "user", "content": user_text}])
    path_set = [p.lower() for p in paths]
    if user_paths:
        hits = 0
        for up in user_paths:
            ul = up.lower()
            if any(ul in q or q in ul for q in path_set):
                hits += 1
        if hits >= max(1, (len(user_paths) + 1) // 2):
            return True
    done_cues = ("已完成", "任务完成", "短总结", "以上就是", "未改任何文件", "done")
    return any(any(c in a for c in done_cues) for a in assistants[-3:])


def _focus_terms(focus: Optional[str]) -> List[str]:
    skip = {"只保留", "保留", "keep", "only", "focus"}
    return [
        part
        for part in (focus or "").replace("：", " ").replace(":", " ").split()
        if part.strip() and part.lower() not in skip
    ]


def _text_hits_focus(text: str, terms: List[str]) -> bool:
    if not terms or not text:
        return False
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def build_extractive_summary(
    older: List[Dict[str, Any]],
    *,
    goal_text: Optional[str] = None,
    focus: Optional[str] = None,
) -> str:
    """Deterministic 6-section fallback — paths + tool progress, never placeholder-only."""
    users: List[str] = []
    assistants: List[str] = []
    tool_msgs: List[Dict[str, Any]] = []
    for m in older:
        if _is_compaction_message(m):
            continue
        text = _plain_content(m)
        if not text:
            continue
        role = m.get("role")
        if role == "user":
            users.append(text)
        elif role == "assistant":
            assistants.append(text)
        elif role == "tool":
            tool_msgs.append(m)
        else:
            assistants.append(text)

    goal = (goal_text or "").strip() or (users[0] if users else "（对话中未写明单一目标）")
    constraints_bits = extract_hard_constraints(users)

    tool_lines = collect_tool_progress(older)
    paths_from_tools = collect_touched_paths(tool_msgs)
    paths_from_users = collect_touched_paths(
        [{"role": "user", "content": u} for u in users]
    )
    # Prefer tool-derived paths for "work done"; fall back to all for Critical inventory
    paths = paths_from_tools or collect_touched_paths(older)

    progress_bits: List[str] = []
    if tool_lines:
        progress_bits.extend(f"- {line}" for line in tool_lines[-8:])
        if paths_from_tools:
            progress_bits.append("触及路径：" + "；".join(paths_from_tools[:12]))
    else:
        # Honest about early cut: do NOT claim the whole task never started
        progress_bits.append(_PROGRESS_NO_TOOLS_IN_WINDOW)
        if paths_from_users:
            progress_bits.append("用户已点名路径：" + "；".join(paths_from_users[:12]))
        # Skip long assistant essays (they pollute Progress when cut is early)
        short_assts = [
            a
            for a in assistants[-2:]
            if a.strip() and len(a) <= 100 and not _looks_like_summary_dump(a)
        ]
        if short_assts:
            progress_bits.append("助手：" + " → ".join(_clip_line(a, 80) for a in short_assts))
        if users and len(progress_bits) == 1:
            progress_bits.append("用户请求：" + _clip_line(users[-1], 120))

    decisions = [
        _clip_line(a, 100) for a in assistants[-6:] if _looks_like_decision(a)
    ]
    if not decisions:
        decisions = [_DECISION_NONE]

    task_user = _latest_task_user(users)
    if task_user and _user_request_mostly_covered(
        task_user,
        paths=paths_from_tools or paths,
        tool_lines=tool_lines,
        assistants=assistants,
    ):
        next_steps = [_NEXT_WAITING]
    elif task_user:
        if _looks_like_task_paste(task_user):
            next_steps = ["继续推进最近用户请求中尚未完成的部分（见 Goal）"]
        else:
            next_steps = [f"继续完成用户未完成项：{_clip_line(task_user, 100)}"]
    elif users:
        next_steps = ["（从最近用户请求继续）"]
    else:
        next_steps = ["（从最近用户请求继续）"]

    critical_paths: List[str] = []
    seen_crit: set[str] = set()
    for p in paths_from_tools + paths_from_users:
        key = p.lower()
        if key in seen_crit:
            continue
        seen_crit.add(key)
        critical_paths.append(p)
    if not critical_paths:
        critical_paths = paths

    focus_terms = _focus_terms(focus)
    if focus_terms:
        focused_users = [u for u in users if _text_hits_focus(u, focus_terms)]
        focused_paths = [p for p in critical_paths if _text_hits_focus(p, focus_terms)]
        if focused_paths:
            critical_paths = focused_paths + [p for p in critical_paths if p not in focused_paths]
        if focused_users:
            next_steps = [f"优先保留：{focus_terms[0]}"] + [
                _clip_line(u, 100) for u in focused_users[-2:]
            ] + next_steps

    if critical_paths:
        critical = [f"- {p}" for p in critical_paths[:20]]
    else:
        critical = ["（无路径）"]
        crumbs = tool_lines[-2:]
        for c in crumbs:
            critical.append(f"- {_clip_line(c, 140)}")
        if focus_terms:
            critical.insert(0, f"- focus: {', '.join(focus_terms)}")

    return "\n".join(
        [
            "## Goal",
            _clip_line(goal, 400),
            "## Constraints",
            "\n".join(f"- {c}" for c in constraints_bits) if constraints_bits else "（无）",
            "## Progress",
            "\n".join(progress_bits) if progress_bits else "（无足够进度摘录）",
            "## Key Decisions",
            "\n".join(f"- {d}" for d in decisions),
            "## Next Steps",
            "\n".join(f"- {n}" for n in next_steps),
            "## Critical Context",
            "\n".join(critical),
        ]
    )


def parse_six_sections(text: str) -> Dict[str, str]:
    """Split a 6-section markdown body into {section_name: body}."""
    found: Dict[str, str] = {}
    if not text:
        return found
    pattern = re.compile(
        r"^##\s*(Goal|Constraints|Progress|Key Decisions|Next Steps|Critical Context)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    for i, match in enumerate(matches):
        name = match.group(1)
        # Normalize casing to canonical
        for canon in SIX_SECTIONS:
            if canon.lower() == name.lower():
                name = canon
                break
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        found[name] = body
    return found


def coerce_six_sections(llm_text: str, *, extractive: str) -> str:
    """Prefer LLM body when structured; fill holes / replace Goal-echo with extractive."""
    raw = (llm_text or "").strip()
    if not raw:
        return extractive

    # Reject classic useless fallback if somehow still present as majority content
    if raw.count("（见原文）") >= 3:
        return extractive

    llm_sections = parse_six_sections(raw)
    ext_sections = parse_six_sections(extractive)
    if len(llm_sections) < 3:
        # Free-form or broken — keep LLM prose under Progress, structure from extractive
        lines = [
            f"## {name}\n{(ext_sections.get(name) or '（无）').strip()}"
            for name in SIX_SECTIONS
        ]
        if raw and "## Progress" not in raw:
            # Attach free-form under Progress if extractive Progress is thin
            prog = (ext_sections.get("Progress") or "").strip()
            merged_prog = f"{prog}\n\n（模型原文摘要）\n{raw[:1200]}".strip() if prog else raw[:1500]
            lines[2] = f"## Progress\n{merged_prog}"
        return "\n".join(lines)

    goal_body = (llm_sections.get("Goal") or ext_sections.get("Goal") or "").strip()
    echo_targets = {
        "Constraints",
        "Progress",
        "Next Steps",
        "Critical Context",
        "Key Decisions",
    }

    out_parts: List[str] = []
    for name in SIX_SECTIONS:
        body = (llm_sections.get(name) or "").strip()
        ext_body = (ext_sections.get(name) or "（无）").strip()
        if not body or body == "（见原文）" or body == "无":
            body = ext_body
        elif name in echo_targets and _section_echoes_goal(body, goal_body):
            body = ext_body
        elif name == "Constraints" and (
            _looks_like_task_paste(body) or _section_echoes_goal(body, goal_body)
        ):
            body = ext_body
        elif name == "Key Decisions" and (
            _looks_like_summary_dump(body) or _section_echoes_goal(body, goal_body)
        ):
            body = ext_body
        elif name == "Next Steps" and (
            _looks_like_task_paste(body)
            or _section_echoes_goal(body, goal_body)
            or ("继续完成用户未完成项" in body and _NEXT_WAITING in ext_body)
            or (_NEXT_WAITING in body and _NEXT_WAITING not in ext_body)
        ):
            body = ext_body
        elif name == "Progress" and (
            (
                _looks_like_false_idle_progress(body)
                and (
                    "触及路径" in ext_body
                    or "read_file" in ext_body
                    or "list_dir" in ext_body
                    or _PROGRESS_NO_TOOLS_IN_WINDOW in ext_body
                    or ext_body.startswith("- ")
                )
            )
            or (
                _looks_like_summary_dump(body)
                and ("触及路径" in ext_body or ext_body.startswith("- ") or _PROGRESS_NO_TOOLS_IN_WINDOW in ext_body)
            )
        ):
            # Prefer deterministic progress; kill false "尚未开始" claims
            body = ext_body
        elif name == "Critical Context":
            # Prefer extractive path list when LLM Critical has no paths
            if not _section_has_path(body) and _section_has_path(ext_body):
                body = ext_body
            elif _section_has_path(ext_body) and _section_has_path(body):
                # Merge: keep LLM prose, append missing extractive paths
                body_lower = body.lower()
                missing = [
                    p
                    for p in collect_touched_paths([{"role": "user", "content": ext_body}])
                    if p.lower() not in body_lower
                ]
                if missing:
                    body = body.rstrip() + "\n" + "\n".join(f"- {p}" for p in missing)
        out_parts.append(f"## {name}\n{body}")
    return "\n".join(out_parts)


def _summary_message(summary_text: str, *, preserve_goal: Optional[str]) -> Dict[str, Any]:
    from agent_window.agent.goal import clip_goal

    lines = [COMPACTION_SUMMARY_MARKER, COMPACTION_HANDOFF_PREFIX]
    goal = (preserve_goal or "").strip()
    if goal:
        lines.append(f"本轮目标（压缩保留）：{clip_goal(goal)}")
    lines.append(summary_text)
    return {
        "role": "user",
        "content": "\n".join(lines),
        "entry_type": "compaction_summary",
    }


def _build_summarize_input(
    blob: str,
    *,
    goal_text: Optional[str],
    previous_summary: Optional[str],
    focus: Optional[str] = None,
) -> str:
    parts = [_SIX_SECTION_PROMPT]
    focus_text = (focus or "").strip()
    if focus_text:
        parts.append(
            f"【Focus】用户要求优先保留：{focus_text}。"
            "Critical Context 与 Next Steps 必须偏向这些词及相关路径，其它细节从简。"
        )
    if goal_text:
        from agent_window.agent.goal import clip_goal

        parts.append(f"【必须保留的本轮目标】{clip_goal(goal_text)}")
        parts.append("摘要时不得丢失或改写该目标；其余内容按六小节交接归纳，禁止把目标原文复读进其它小节。")
    if previous_summary:
        parts.append("【上一轮压缩摘要，请增量合并勿丢失】")
        parts.append(previous_summary[:4000])
    parts.append(blob)
    return "\n\n".join(parts)


def _preview(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


async def compress_messages_if_needed(
    messages: List[Dict[str, Any]],
    *,
    auto_compress: bool,
    context_limit: int,
    summarize: Optional[SummarizeFn] = None,
    preserve_goal: Optional[str] = None,
    reserve_tokens: int = DEFAULT_TOKEN_RESERVE,
    keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS,
    keep_folded_user_tokens: int = DEFAULT_KEEP_FOLDED_USER_TOKENS,
    force: bool = False,
    focus: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], bool, CompressMeta]:
    """
    If over (context_limit - reserve) and auto_compress, fold older turns into
    one compaction_summary user message (6-section prompt when summarizing).

    When ``preserve_goal`` is set, the Goal is pinned into the summary header and
    re-injected as a dedicated system block after compression so auto_compress
    cannot wash out Turn Goal.

    Returns (messages, compressed_flag, meta).
    """
    empty_meta = CompressMeta()
    if not auto_compress and not force:
        return messages, False, empty_meta

    threshold = max(1, int(context_limit) - max(0, int(reserve_tokens)))
    tokens = approx_messages_tokens(messages)
    if tokens <= threshold and not force:
        return messages, False, empty_meta

    other_system, _existing_goal_blocks, rest = _split_system_messages(messages)
    goal_text = (preserve_goal or "").strip() or None

    cut = find_cut_index(rest, keep_recent_tokens=keep_recent_tokens)
    if force and cut <= 0 and len(rest) > 2:
        cut = max(1, len(rest) - 2)
        for j in range(cut, len(rest)):
            if rest[j].get("role") in ("user", "assistant"):
                cut = j
                break
    if cut <= 0:
        if len(rest) <= 4:
            keep = rest[-4:]
            out = other_system + keep
            if goal_text:
                from agent_window.agent.goal import inject_goal_into_messages

                out = inject_goal_into_messages(out, goal_text)
            return out, True, CompressMeta(
                method="tail_trim",
                older_count=max(0, len(rest) - len(keep)),
                rest_count=len(rest),
            )
        # Over keep budget but find_cut stayed at 0 — leave a small recent tail
        cut = max(1, len(rest) - 4)
        for j in range(cut, len(rest)):
            if rest[j].get("role") in ("user", "assistant"):
                cut = j
                break

    older = rest[:cut]
    recent = rest[cut:]
    if not older:
        out = other_system + recent
        if goal_text:
            from agent_window.agent.goal import inject_goal_into_messages

            out = inject_goal_into_messages(out, goal_text)
        return out, True, CompressMeta(method="tail_trim", older_count=0, rest_count=len(rest))

    previous_summary = find_previous_summary(older)
    blob = serialize_messages_for_summary(older)
    extractive = build_extractive_summary(older, goal_text=goal_text, focus=focus)

    summary_text = ""
    method = "extractive"
    if summarize is not None:
        try:
            summarize_input = _build_summarize_input(
                blob,
                goal_text=goal_text,
                previous_summary=previous_summary,
                focus=focus,
            )
            llm_raw = (await summarize(summarize_input)).strip()
            if llm_raw:
                summary_text = coerce_six_sections(llm_raw, extractive=extractive)
                method = "llm"
        except Exception:
            logger.exception("LLM summarize failed; using extractive fallback")

    if not summary_text:
        summary_text = extractive
        method = "extractive"

    summary_msg = _summary_message(summary_text, preserve_goal=goal_text)
    kept_users = [
        _msg_as_dict(m)
        for m in select_folded_user_originals(
            older,
            token_budget=keep_folded_user_tokens,
        )
    ]
    out = other_system + [summary_msg] + kept_users + recent
    if goal_text:
        from agent_window.agent.goal import inject_goal_into_messages

        out = inject_goal_into_messages(out, goal_text)

    meta = CompressMeta(
        method=method,
        summary_preview=_preview(summary_text),
        older_count=len(older),
        used_previous_summary=bool(previous_summary),
        cut_index=cut,
        rest_count=len(rest),
        summary_content=str(summary_msg.get("content") or ""),
        kept_folded_user_count=len(kept_users),
        keep_folded_user_tokens=int(keep_folded_user_tokens),
    )
    logger.info(
        "context compressed method=%s older=%s preview=%s",
        meta.method,
        meta.older_count,
        meta.summary_preview[:120],
    )
    return out, True, meta


def messages_contain_goal(messages: List[Dict[str, Any]], goal: str) -> bool:
    """Behavior helper for tests: Goal marker + goal substance present."""
    from agent_window.agent.goal import GOAL_MARKER, clip_goal

    needle = clip_goal(goal)
    for m in messages:
        content = m.get("content")
        if not isinstance(content, str):
            continue
        role = m.get("role")
        if role == "system" and GOAL_MARKER in content and needle[:24] in content:
            return True
        if "本轮目标（压缩保留）" in content and needle[:24] in content:
            return True
        if COMPACTION_SUMMARY_MARKER in content and needle[:24] in content:
            return True
    return False
