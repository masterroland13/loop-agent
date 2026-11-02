**English** | [简体中文](README.zh-CN.md)

# Loop Agent

**A local coding agent you can take apart.**

Loop Agent is a window, a command-line client, and an optional desktop shell around a small agent runtime. You give it an OpenAI-compatible model and a workspace folder. The loop stays a tool cycle. Goal mode, approval strictness, and compaction hang on hooks around that cycle. When a session grows long, the runtime writes a six-section handoff onto the session tree, keeps the user’s own lines, and leaves the full transcript on disk so `search_session` can recover what the summary left out.

This checkout is a single-user local program: React, FastAPI, SQLite, and a WebKitGTK shell for Linux and WSL. Architecture stages A0–A4 and context slices C0–C5 are in the tree. Compress-after-a-tool-batch (C6) and regenerate branch summaries (C7) come later on purpose. `auto_compress` defaults off.

---

## Why it looks like this

Prompts, diffs, memory, and the HTTP stack live in layers and hooks. Tests keep the import arrows pointing one way.

- **Pi-shaped layers.** `loop-ai` → `loop-agent-core` → `loop-coding` → `loop-window`. Imports only go up. Core stays free of FastAPI and SQLAlchemy. The Python package name is still `agent_window`.
- **Session tree.** Every message has `parent_id`. The session has `leaf_id`. Regenerate adds a sibling and moves the leaf. Abandoned turns stay in SQLite. Compaction is a node on the path the model sees.
- **Funnel.** After reading Codex, Cursor, Claude Code, and Pi: the JSONL transcript is append-only → the leaf path can be compacted and the summary is persisted → durable context (system, memory, skills) stays in its own bucket → `search_session` reads the originals back.
- **Quiet defaults.** Goal mode is off. The preset is YOLO on a trusted local tree: writes run and are audited. Trusted and Strict are there when a turn should wait for confirmation.

Architecture source of truth: [`docs/architecture-charter.md`](docs/architecture-charter.md).

---

## Features

| Surface | What you get |
|---------|----------------|
| **Window** | Workspace and sessions, streaming chat, approval cards, Files tree, Settings, estimated context occupancy |
| **Loop** | Tool-calling cycle, write-claim guard, observation slimming. Mid-turn messages use `POST /api/sessions/{id}/steer`. The window has no insert control for that API |
| **Goal** | Optional quality ring: pinned goal, checkpoints, exploration nudge. Off by default |
| **Presets** | YOLO / Trusted / Strict. Policy sits in `before_tool_call`, outside the tool implementations |
| **Models** | Several OpenAI-compatible profiles, bound per session |
| **Memory** | Bounded `USER.md` / `MEMORY.md`, injected as frozen snapshots |
| **Skills** | Catalog in the system prompt; the body loads on demand |
| **Context** | Six-section handoff, kept user lines, `search_session`, manual compact with optional `focus` |
| **Desktop** | `loop install` / `loop shell` on WebKitGTK. Uninstall removes the program and leaves your data |
| **CLI** | `loop ask` · `status` · `approve` · `reject` · `run --wait` |

---

## Architecture

```text
loop-window     React · FastAPI · SQLite · CLI · WebKitGTK
      ↑
loop-coding     files · shell · patches · skills · memory · compress · search
      ↑
loop-agent-core LoopConfig · AgentLoop · session tree · Goal / Preset hooks
      ↑
loop-ai         model registry · OpenAI-compatible client · streaming
```

The arrows are import direction: each layer may use the one below it. Runtime directories are a separate axis. The loop does not resolve the install path.

| Directory | Default | Holds | Stays out |
|-----------|---------|-------|-----------|
| **Install** | `~/.local/lib/loop-agent` | Built UI, `loop-window` binary, backend venv. Launcher `~/.local/bin/loop`. Desktop entry `~/.local/share/applications/loop-agent.desktop` | Sessions, the git checkout, the workspace |
| **User data** | `~/.local/share/loop-agent`, or `APP_DATA_DIR` | SQLite, model profiles, memory, `transcript.jsonl`, spilled tool output | Program binaries and workspace files |
| **Workspace** | The folder you bind | Sandbox for file and shell tools | The install tree. An unbound session has no root, so tools cannot read the install directory |

`loop uninstall` deletes the install directory, the `loop` launcher, and the desktop entry. User data and the workspace remain. CLI settings in `~/.config/loop-agent` serve the CLI only and stay separate from user data.

During development, `APP_DATA_DIR=./data` in `backend/.env` keeps the database at `backend/data`. `loop shell` ignores that file. It serves the installed UI from its own backend on port **8765** and leaves the dev servers on 8000 and 5173 alone.

---

## Quick start

### Develop

Python ≥ 3.10. The interpreter this repo and `loop install` expect is `backend/.venv`.

```bash
cd backend
PYTHONPATH=src .venv/bin/python -m uvicorn agent_window.main:app --host 0.0.0.0 --port 8000
```

From the repository root, in another terminal:

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open [http://localhost:5173/](http://localhost:5173/). Vite proxies `/api` and `/health` to port 8000.

Copy [`backend/.env.example`](backend/.env.example) to `backend/.env`. Keep `APP_DATA_DIR=./data` so sessions stay in the checkout. Set the OpenAI-compatible base URL, API key, and model id. With `APP_DATA_DIR` unset, data goes to `~/.local/share/loop-agent` and no workspace is bound.

### Install (Linux / WSL)

Install runs from this git checkout. A `loop` command that already lives under `~/.local` refuses to reinstall. The command needs `dist/index.html`, `backend/.venv`, and a Linux executable at `shell/loop-window`. If that binary is missing or older than `shell/loop-window.c`, install compiles it with `gcc` and `pkg-config` for `webkit2gtk-4.1`.

```bash
npm run build
cd backend
PYTHONPATH=src .venv/bin/python -m agent_window.cli install
```

That writes `~/.local/lib/loop-agent`, `~/.local/bin/loop`, and the desktop entry. With `~/.local/bin` on `PATH`:

```bash
loop shell       # window; backend on 8765, not 8000
loop uninstall   # program files only
```

If port 8765 is already in use, `loop shell` stops instead of attaching to another process. Closing the window stops the backend it started.

First launch with no workspace: fill one model card (base URL, API key, model id), then pick a folder or create one in the directory you are browsing. Creating a folder leaves it unbound until you confirm.

`loop ask`, `loop status`, `loop approve`, `loop reject`, and `loop run --wait` talk to `http://127.0.0.1:8000` unless `AGENT_BASE_URL` or `base_url` in `~/.config/loop-agent/config.json` says otherwise. Point that at `http://127.0.0.1:8765` when the desktop shell is the backend you want.

### Test

From `backend/`:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

From the repository root:

```bash
npx tsc -b
```

The UI has no automated suite. Backend tests assert what the API returns. Quote any path that contains spaces.

---

## Context funnel (shipped)

C0–C5 are in the tree and were audited against the plan. The handoff has six sections: Goal, Constraints, Progress, Key Decisions, Next Steps, Critical Context.

| Slice | Behavior |
|-------|----------|
| **C0** | Append-only `transcript.jsonl` under user data. Secret fields are redacted. Attachments store an id and a file name |
| **C1** | A `compaction_summary` node on the tree. Folded rows stay in SQLite and in the JSONL; the leaf path skips them |
| **C2** | Folded user originals kept, near to far, under an 8K token cap |
| **C3** | `transform_context` before every model call, including between tool turns inside the loop |
| **C4** | `search_session` reads this session’s JSONL and spill files only |
| **C5** | `POST /api/sessions/{id}/compact` (optional `focus`) and estimated occupancy from `GET /api/sessions/{id}/context` |

C6 (compress after a finished tool batch) and C7 (a short summary of the abandoned branch on regenerate) are intentionally later. `auto_compress` still defaults **off**. Turning it on is a separate, reversible change. Manual compact and the occupancy readout work with the default.

---

## Docs

| Start here | |
|------------|--|
| [`docs/architecture-charter.md`](docs/architecture-charter.md) | Architecture source of truth: layers, Goal, presets, runtime directories |
| [`docs/design/loop-agent-manual.md`](docs/design/loop-agent-manual.md) | Operating and extension manual: tree, loop, funnel, HTTP |
| [`docs/research/context-loop-c0-c5-review.md`](docs/research/context-loop-c0-c5-review.md) | How C0–C5 were researched, built, and audited, including resume wording |
| [`docs/README.md`](docs/README.md) | Map of the rest of `docs/` |

---

## Status

Architecture stages **A0–A4** are complete. The context funnel **C0–C5** is in, then audited. Living progress: [`docs/foundation-status.md`](docs/foundation-status.md). History of changes: [`CHANGELOG.md`](CHANGELOG.md).

---

## License

This repository has no `LICENSE` file. No grant to copy, modify, or redistribute is stated here. Treat the checkout as the author’s source tree until a license is added.
