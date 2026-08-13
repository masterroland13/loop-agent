"""Hal Agent CLI — headless runtime, same API as the web UI."""

from __future__ import annotations

import argparse
import json
import os
import sys
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


def cmd_ask(client: RuntimeClient, args: argparse.Namespace) -> int:
    prompt = args.prompt
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            file_text = f.read()
        prompt = f"{prompt}\n\n{file_text}".strip() if prompt else file_text.strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
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

    return _stream_turn(
        client,
        session_id,
        content=prompt,
        model=args.model,
        regenerate=False,
        args=args,
        out=sys.stdout,
    )


def cmd_run(client: RuntimeClient, args: argparse.Namespace) -> int:
    """Alias for ask — reserved for future task-oriented runs."""
    return cmd_ask(client, args)


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

    p_run = sub.add_parser("run", help="Same as ask (task-oriented alias)")
    add_ask_flags(p_run)
    p_run.set_defaults(func=cmd_run)

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
