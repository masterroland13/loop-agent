"""Hal Agent CLI — headless runtime, same API as the web UI."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, TextIO

from agent_window.cli.client import ApiError, RuntimeClient
from agent_window.cli.config import load_cli_config


_CLI_CONFIG = load_cli_config()
DEFAULT_BASE = os.environ.get("AGENT_BASE_URL") or _CLI_CONFIG.get("base_url") or "http://127.0.0.1:8000"


def _eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, file=sys.stderr, **kwargs)


def _confirm(prompt: str, *, yes: bool, no_input: bool) -> bool:
    if yes:
        return True
    if no_input or not sys.stdin.isatty():
        _eprint(f"{prompt} [auto-reject: non-interactive without -y]")
        return False
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def cmd_health(client: RuntimeClient, _args: argparse.Namespace) -> int:
    data = client.get("/health")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if data.get("status") == "ok" else 1


def cmd_assets(client: RuntimeClient, _args: argparse.Namespace) -> int:
    data = client.get("/api/assets")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_sessions(client: RuntimeClient, args: argparse.Namespace) -> int:
    sessions = client.get("/api/sessions")
    if args.json:
        print(json.dumps(sessions, ensure_ascii=False, indent=2))
        return 0
    if not sessions:
        _eprint("(no sessions)")
        return 0
    for s in sessions:
        print(f"{s['id']}\t{s.get('updated_at', '')}\t{s.get('title', '')}")
    return 0


def cmd_workspace(client: RuntimeClient, args: argparse.Namespace) -> int:
    if args.root:
        data = client.put("/api/workspace", {"root": args.root})
    elif args.clear:
        data = client.delete("/api/workspace")
    else:
        data = client.get("/api/workspace")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def _fetch_pending(client: RuntimeClient) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "patches": list(client.get("/api/workspace/patches") or []),
        "shells": list(client.get("/api/workspace/shells") or []),
        "memories": list(client.get("/api/memory/proposals") or []),
    }


def _preview(text: str, limit: int = 80) -> str:
    one = " ".join((text or "").split())
    if len(one) <= limit:
        return one
    return one[: limit - 1] + "…"


def _status_payload(client: RuntimeClient, session_id: Optional[str]) -> Dict[str, Any]:
    pending = _fetch_pending(client)
    runtime = client.get("/api/runtime") or {}
    active = list(runtime.get("active_sessions") or [])
    payload: Dict[str, Any] = {
        "patches": pending["patches"],
        "shells": pending["shells"],
        "memories": pending["memories"],
        "awaiting_approval": bool(
            pending["patches"] or pending["shells"] or pending["memories"]
        ),
        "active_sessions": active,
        "pending_scope": "workspace",
    }
    if not session_id:
        return payload

    sessions = client.get("/api/sessions") or []
    sess = next((s for s in sessions if s.get("id") == session_id), None)
    if not sess:
        raise ApiError(f"session not found: {session_id}", status=404)
    messages = client.get(f"/api/sessions/{session_id}/messages") or []
    last = messages[-1] if messages else None
    last_public = None
    if last:
        last_public = {
            "id": last.get("id"),
            "role": last.get("role"),
            "content": _preview(str(last.get("content") or ""), 200),
        }
    payload["session"] = {
        "id": session_id,
        "title": sess.get("title"),
        "is_running": session_id in active,
        "last_message": last_public,
    }
    return payload


def _print_status(payload: Dict[str, Any]) -> None:
    session = payload.get("session")
    if session:
        running = "是" if session.get("is_running") else "否"
        print(f"会话: {session.get('title') or ''} ({session.get('id')})")
        print(f"运行中: {running}")
        last = session.get("last_message")
        if last:
            print(f"最近消息: [{last.get('role')}] {_preview(str(last.get('content') or ''))}")
    else:
        active = payload.get("active_sessions") or []
        print(f"运行中会话: {', '.join(active) if active else '(无)'}")

    patches = payload.get("patches") or []
    shells = payload.get("shells") or []
    memories = payload.get("memories") or []
    if not (patches or shells or memories):
        print("待审批: (无)")
        return

    print("待审批（工作区全局）:")
    for p in patches:
        print(f"  [patch]  {p.get('id')}  path={p.get('path')}  status={p.get('status')}")
        print(f"           hal approve --patch-id {p.get('id')}")
    for s in shells:
        print(f"  [shell]  {s.get('id')}  cmd={s.get('command')}  status={s.get('status')}")
        print(f"           hal approve --shell-id {s.get('id')}")
    for m in memories:
        preview = _preview(str(m.get("preview") or m.get("content") or ""), 60)
        print(f"  [memory] {m.get('id')}  mode={m.get('mode')}  status={m.get('status')}  {preview}")
        print(f"           hal approve --memory-id {m.get('id')}")


def cmd_status(client: RuntimeClient, args: argparse.Namespace) -> int:
    payload = _status_payload(client, args.session)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    _print_status(payload)
    return 0


def _explicit_targets(args: argparse.Namespace) -> List[tuple[str, str]]:
    targets: List[tuple[str, str]] = []
    for pid in args.patch_ids or []:
        targets.append(("patch", pid))
    for sid in args.shell_ids or []:
        targets.append(("shell", sid))
    for mid in args.memory_ids or []:
        targets.append(("memory", mid))
    return targets


def _gate_paths(kind: str, item_id: str) -> tuple[str, str]:
    if kind == "patch":
        base = f"/api/workspace/patches/{item_id}"
    elif kind == "shell":
        base = f"/api/workspace/shells/{item_id}"
    elif kind == "memory":
        base = f"/api/memory/proposals/{item_id}"
    else:
        raise ApiError(f"unknown kind: {kind}")
    return f"{base}/apply", f"{base}/reject"


def _label_item(kind: str, item: Dict[str, Any]) -> str:
    if kind == "patch":
        return f"patch {item.get('id')} path={item.get('path')}"
    if kind == "shell":
        return f"shell {item.get('id')} cmd={item.get('command')}"
    return f"memory {item.get('id')} mode={item.get('mode')}"


def _decide_one(client: RuntimeClient, kind: str, item_id: str, action: str) -> Dict[str, Any]:
    apply_path, reject_path = _gate_paths(kind, item_id)
    path = apply_path if action == "apply" else reject_path
    result = client.post(path)
    return result if isinstance(result, dict) else {"id": item_id, "status": action}


def _print_decision(kind: str, action: str, result: Dict[str, Any]) -> None:
    status = result.get("status") or action
    item_id = result.get("id") or ""
    extra = result.get("path") or result.get("command") or result.get("mode") or ""
    verb = "已批准" if action == "apply" else "已拒绝"
    print(f"{verb} [{kind}] {item_id}  status={status}  {extra}".rstrip())
    if result.get("error"):
        _eprint(f"  error: {result['error']}")


def _interactive_pending(
    client: RuntimeClient,
    action: str,
    *,
    no_input: bool,
) -> int:
    pending = _fetch_pending(client)
    items: List[tuple[str, Dict[str, Any]]] = []
    for p in pending["patches"]:
        items.append(("patch", p))
    for s in pending["shells"]:
        items.append(("shell", s))
    for m in pending["memories"]:
        items.append(("memory", m))
    if not items:
        print("待审批: (无)")
        return 0
    if no_input or not sys.stdin.isatty():
        _eprint("非交互模式请指定 --patch-id / --shell-id / --memory-id")
        _print_status(
            {
                "patches": pending["patches"],
                "shells": pending["shells"],
                "memories": pending["memories"],
                "active_sessions": [],
            }
        )
        return 2

    prompt = "批准这项？" if action == "apply" else "拒绝这项？"
    n = 0
    for kind, item in items:
        item_id = str(item.get("id") or "")
        _eprint(_label_item(kind, item))
        if not _confirm(prompt, yes=False, no_input=False):
            _eprint("  跳过")
            continue
        result = _decide_one(client, kind, item_id, action)
        _print_decision(kind, action, result)
        n += 1
    if n == 0:
        print("未更改")
    return 0


def cmd_approve(client: RuntimeClient, args: argparse.Namespace) -> int:
    targets = _explicit_targets(args)
    if not targets:
        return _interactive_pending(client, "apply", no_input=args.no_input)
    for kind, item_id in targets:
        result = _decide_one(client, kind, item_id, "apply")
        _print_decision(kind, "apply", result)
    return 0


def cmd_reject(client: RuntimeClient, args: argparse.Namespace) -> int:
    targets = _explicit_targets(args)
    if not targets:
        return _interactive_pending(client, "reject", no_input=args.no_input)
    for kind, item_id in targets:
        result = _decide_one(client, kind, item_id, "reject")
        _print_decision(kind, "reject", result)
    return 0


def _handle_approval(client: RuntimeClient, event: Dict[str, Any], args: argparse.Namespace) -> None:
    kind = event.get("kind")
    if kind == "patch":
        patch_id = event.get("patch_id")
        path = event.get("path") or ""
        _eprint(f"\n[approval] patch {patch_id} path={path}")
        if _confirm("Apply patch?", yes=args.yes, no_input=args.no_input):
            client.post(f"/api/workspace/patches/{patch_id}/apply")
            _eprint("[approval] applied")
        else:
            client.post(f"/api/workspace/patches/{patch_id}/reject")
            _eprint("[approval] rejected")
    elif kind == "shell":
        shell_id = event.get("shell_id")
        command = event.get("command") or ""
        _eprint(f"\n[approval] shell {shell_id}: {command}")
        if _confirm("Run command?", yes=args.yes, no_input=args.no_input):
            client.post(f"/api/workspace/shells/{shell_id}/apply")
            _eprint("[approval] ran")
        else:
            client.post(f"/api/workspace/shells/{shell_id}/reject")
            _eprint("[approval] rejected")
    elif kind == "memory":
        memory_id = event.get("memory_id")
        _eprint(f"\n[approval] memory {memory_id}")
        if _confirm("Write USER.md?", yes=args.yes, no_input=args.no_input):
            client.post(f"/api/memory/proposals/{memory_id}/apply")
            _eprint("[approval] memory written")
        else:
            client.post(f"/api/memory/proposals/{memory_id}/reject")
            _eprint("[approval] memory rejected")
    else:
        _eprint(f"\n[approval] unknown kind={kind}: {event}")


def _has_pending(client: RuntimeClient) -> bool:
    pending = _fetch_pending(client)
    return bool(pending["patches"] or pending["shells"] or pending["memories"])


def _wait_pending(client: RuntimeClient, timeout_sec: float) -> int:
    """Poll until all pending approvals clear or timeout. Returns exit code."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not _has_pending(client):
            return 0
        time.sleep(1.5)
    _eprint(f"等待审批超时（{timeout_sec:.0f}s）")
    return 3


def _stream_turn(
    client: RuntimeClient,
    session_id: str,
    *,
    content: Optional[str],
    model: Optional[str],
    regenerate: bool,
    args: argparse.Namespace,
    out: TextIO,
) -> int:
    if regenerate:
        path = f"/api/sessions/{session_id}/regenerate"
        body: Dict[str, Any] = {}
        if model:
            body["model"] = model
    else:
        path = f"/api/sessions/{session_id}/messages"
        body = {"content": content or ""}
        if model:
            body["model"] = model

    saw_done = False
    exit_code = 0
    for event in client.stream_post(path, body):
        etype = event.get("type")
        if etype == "token" and event.get("content"):
            out.write(event["content"])
            out.flush()
        elif etype == "tool_start":
            if args.verbose:
                _eprint(f"\n[tool] {event.get('name')} …")
        elif etype == "tool_result":
            if args.verbose:
                snippet = (event.get("content") or "")[:200]
                _eprint(f"[tool-result] {event.get('name')}: {snippet}")
        elif etype == "diff":
            if args.verbose or event.get("status") == "pending":
                _eprint(
                    f"\n[diff] {event.get('path')} status={event.get('status')} "
                    f"id={event.get('patch_id')}"
                )
        elif etype == "shell":
            if args.verbose or event.get("status") == "pending":
                _eprint(
                    f"\n[shell] {event.get('command')} status={event.get('status')} "
                    f"id={event.get('shell_id')}"
                )
        elif etype == "memory":
            if args.verbose or event.get("status") == "pending":
                _eprint(f"\n[memory] status={event.get('status')} id={event.get('memory_id')}")
        elif etype == "await_approval":
            _handle_approval(client, event, args)
        elif etype == "turn_meta":
            if args.meta or args.verbose:
                meta = {
                    k: event.get(k)
                    for k in (
                        "model",
                        "elapsed_ms",
                        "approx_prompt_tokens",
                        "approx_completion_tokens",
                        "compressed",
                        "memory_injected",
                        "message_id",
                    )
                }
                _eprint(f"\n[meta] {json.dumps(meta, ensure_ascii=False)}")
        elif etype == "done":
            saw_done = True
            out.write("\n")
            out.flush()
        elif etype == "error":
            error_doc = {
                "code": event.get("code") or "LLM_ERROR",
                "message": event.get("message") or "未知错误",
                "session_id": session_id,
            }
            _eprint(f"\n[error] {error_doc['code']}: {error_doc['message']}")
            if args.json:
                _eprint(json.dumps({"error": error_doc}, ensure_ascii=False))
            exit_code = 2
            break

    if not saw_done and exit_code == 0:
        error_doc = {
            "code": "STREAM_TRUNCATED",
            "message": "stream ended without done",
            "session_id": session_id,
        }
        _eprint(f"\n[error] {error_doc['code']}: {error_doc['message']}")
        if args.json:
            _eprint(json.dumps({"error": error_doc}, ensure_ascii=False))
        exit_code = 2
    return exit_code


def _resolve_prompt(args: argparse.Namespace) -> str:
    prompt = args.prompt
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            file_text = f.read()
        prompt = f"{prompt}\n\n{file_text}".strip() if prompt else file_text.strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    return prompt


def cmd_ask(client: RuntimeClient, args: argparse.Namespace) -> int:
    prompt = _resolve_prompt(args)
    if not prompt:
        _eprint("empty prompt: pass text, --file, or stdin")
        return 2

    session_id = args.session
    if not session_id:
        title = (prompt[:40] + "…") if len(prompt) > 40 else prompt
        title = title.replace("\n", " ").strip() or "CLI"
        created = client.post("/api/sessions", {"title": f"cli: {title}"})
        session_id = created["id"]
        _eprint(f"[session] {session_id}")

    code = _stream_turn(
        client,
        session_id,
        content=prompt,
        model=args.model,
        regenerate=False,
        args=args,
        out=sys.stdout,
    )
    try:
        leftover = _fetch_pending(client)
    except ApiError:
        return code
    if leftover["patches"] or leftover["shells"] or leftover["memories"]:
        _eprint("仍有待审批，查看: hal status")
        _eprint("批准: hal approve --patch-id|--shell-id|--memory-id <id>")
    return code


def cmd_run(client: RuntimeClient, args: argparse.Namespace) -> int:
    """Task-oriented run: stream the reply, optionally wait for approvals."""
    prompt = _resolve_prompt(args)
    if not prompt:
        _eprint("empty prompt: pass text, --file, or stdin")
        return 2

    session_id = args.session
    if not session_id:
        title = (prompt[:40] + "…") if len(prompt) > 40 else prompt
        title = title.replace("\n", " ").strip() or "CLI"
        created = client.post("/api/sessions", {"title": f"cli: {title}"})
        session_id = created["id"]
        _eprint(f"[session] {session_id}")

    code = _stream_turn(
        client,
        session_id,
        content=prompt,
        model=args.model,
        regenerate=False,
        args=args,
        out=sys.stdout,
    )
    if code != 0:
        return code

    if not args.wait:
        try:
            if _has_pending(client):
                _eprint("仍有待审批，查看: hal status")
                _eprint("批准: hal approve --patch-id|--shell-id|--memory-id <id>")
        except ApiError:
            pass
        return 0

    # --wait: block until pending approvals are resolved elsewhere.
    timeout = args.wait_timeout if args.wait_timeout is not None else 300.0
    _eprint(f"[wait] 等待审批完成（上限 {timeout:.0f}s）…")
    return _wait_pending(client, timeout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hal",
        description="Hal Agent CLI — headless runtime, same API as the web UI",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE,
        help=(
            "Runtime base URL "
            "(env AGENT_BASE_URL > ~/.config/hal-agent/config.json > default "
            f"{DEFAULT_BASE})"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=_CLI_CONFIG.get("timeout", 120.0),
        help="HTTP timeout seconds",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health", help="GET /health")
    p_health.set_defaults(func=cmd_health)

    p_assets = sub.add_parser("assets", help="GET /api/assets")
    p_assets.set_defaults(func=cmd_assets)

    p_sessions = sub.add_parser("sessions", help="List sessions")
    p_sessions.add_argument("--json", action="store_true")
    p_sessions.set_defaults(func=cmd_sessions)

    p_ws = sub.add_parser("workspace", help="Show / set / clear workspace")
    p_ws.add_argument("--root", help="Bind workspace root path")
    p_ws.add_argument("--clear", action="store_true", help="Clear workspace binding")
    p_ws.set_defaults(func=cmd_workspace)

    def add_ask_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("prompt", nargs="?", default="", help="User message (or stdin)")
        p.add_argument("-f", "--file", help="Append file contents to the prompt")
        p.add_argument("-s", "--session", help="Reuse session id (else create new)")
        p.add_argument(
            "-m",
            "--model",
            default=_CLI_CONFIG.get("default_model"),
            help="Model alias override",
        )
        p.add_argument(
            "-y",
            "--yes",
            action="store_true",
            default=_CLI_CONFIG.get("auto_approve", False),
            help="Auto-approve patch/shell/memory",
        )
        p.add_argument(
            "--no-input",
            action="store_true",
            help="Never prompt; reject approvals unless -y",
        )
        p.add_argument("--meta", action="store_true", help="Print turn_meta on stderr")
        p.add_argument("-v", "--verbose", action="store_true", help="Print tools/diffs on stderr")
        p.add_argument("--json", action="store_true", help="Also emit error JSON on stderr for scripts")

    p_ask = sub.add_parser("ask", help="Send a message and stream the reply")
    add_ask_flags(p_ask)
    p_ask.set_defaults(func=cmd_ask)

    p_run = sub.add_parser("run", help="Run a task, optionally waiting for approvals")
    add_ask_flags(p_run)
    p_run.add_argument(
        "--wait",
        action="store_true",
        help="Block until pending approvals are resolved (default timeout 300s)",
    )
    p_run.add_argument(
        "--wait-timeout",
        type=float,
        default=None,
        help="Max seconds to wait for approvals (default 300)",
    )
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="Show pending patch/shell/memory approvals")
    p_status.add_argument(
        "-s",
        "--session",
        "--session-id",
        dest="session",
        help="Optional session id (running/last message); pending lists are workspace-global",
    )
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    def add_gate_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--patch-id", action="append", dest="patch_ids", help="Patch id (repeatable)")
        p.add_argument("--shell-id", action="append", dest="shell_ids", help="Shell id (repeatable)")
        p.add_argument("--memory-id", action="append", dest="memory_ids", help="Memory proposal id")
        p.add_argument(
            "--no-input",
            action="store_true",
            help="Do not prompt; require explicit --patch-id / --shell-id / --memory-id",
        )

    p_approve = sub.add_parser("approve", help="Approve pending patch/shell/memory")
    add_gate_flags(p_approve)
    p_approve.set_defaults(func=cmd_approve)

    p_reject = sub.add_parser("reject", help="Reject pending patch/shell/memory")
    add_gate_flags(p_reject)
    p_reject.set_defaults(func=cmd_reject)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = RuntimeClient(args.base_url, timeout=args.timeout)
    try:
        return int(args.func(client, args))
    except ApiError as e:
        _eprint(f"error: {e}")
        return 1
    except KeyboardInterrupt:
        _eprint("\ninterrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
