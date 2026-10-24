# Loop Agent

**A local coding agent you can take apart.**  
Thin loop. Optional Goal mode. Session tree that remembers what the model is no longer shown.

Loop Agent is a desktop-and-CLI shell around a small agent runtime: an OpenAI-compatible model, a workspace sandbox, and hooks instead of a 2 000-line `loop.py`. Compression does not delete history. It writes an append-only transcript, hangs a six-section handoff on the session tree, keeps the user’s own words, and gives the model a `search_session` tool when the summary is not enough.

中文：可拆的本地编码 Agent。窗口 + CLI + 可选桌面壳。环要薄，Goal 和审批都是模式，压缩是交接不是毁证据。

---

## Why it looks like this

Most agent UIs grow a single file that knows about prompts, diffs, memory, and the framework. This repo treats that as a bug.

- **Pi-shaped layers** — `loop-ai` → `loop-agent-core` → `loop-coding` → `loop-window`. Imports only go up. Core does not import FastAPI or SQLAlchemy.
- **Session tree, not a tape** — `parent_id` + `leaf_id`. Regenerate branches. Abandoned turns stay. Compaction is a node on the path, not a `DELETE`.
- **Funnel, not a slogan** — after reading Codex, Cursor, Claude Code, and Pi: JSONL never lost → path compressible and persisted → durable vs chat buckets → search recovers originals.
- **Defaults that do not nag** — Goal off. Preset YOLO on a trusted local tree. Strict and confirmation exist; they are not the product personality.

Architecture source of truth: [`docs/architecture-charter.md`](docs/architecture-charter.md).  
How to operate and extend: [`docs/design/loop-agent-manual.md`](docs/design/loop-agent-manual.md).  
How C0–C5 were researched, built, and audited: [`docs/research/context-loop-c0-c5-review.md`](docs/research/context-loop-c0-c5-review.md).

---

## Features

| Surface | What you get |
|---------|----------------|
| **Window** | Workspace + sessions, streaming chat, approval cards, Files tree, Settings, occupancy % |
| **Loop** | Tool-calling cycle, steering, write-claim guard, observation slimming |
| **Goal** | Optional quality ring: pin a goal, checkpoints, exploration nudge — off by default |
| **Presets** | YOLO / Trusted / Strict — policy in `before_tool_call`, not inside tools |
| **Models** | Multiple OpenAI-compatible profiles; per-session binding |
| **Memory** | Bounded `USER.md` / `MEMORY.md` with frozen snapshots |
| **Skills** | Catalog in the system prompt; body loaded on demand |
| **Context** | Six-section handoff, kept user lines, `search_session`, manual compact + focus |
| **Desktop** | `loop install` / `loop shell` on WebKitGTK; uninstall leaves your data |
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

Runtime directories (orthogonal to imports):

| | Default | Role |
|--|---------|------|
| Install | `~/.local/lib/loop-agent` | UI, window binary, venv |
| User data | `~/.local/share/loop-agent` | DB, transcripts, profiles |
| Workspace | folder you bind | sandbox for tools |

`loop uninstall` removes the program only.

---

## Quick start

### Develop

```bash
cd backend
PYTHONPATH=src .venv/bin/python -m uvicorn agent_window.main:app --host 0.0.0.0 --port 8000
```

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open [http://localhost:5173/](http://localhost:5173/). Put the gateway in `backend/.env` (`APP_DATA_DIR=./data` keeps the checkout database).

### Install (Linux / WSL)

```bash
loop install    # ~/.local/lib/loop-agent
loop shell      # window + backend on :8765, not :8000
loop uninstall  # program files only
```

First run: one model card (Base URL / API key / model id), then pick or create a workspace folder. Creating a folder does not bind until you confirm.

### Test

```bash
cd backend && PYTHONPATH=src python -m pytest tests/ -q
npx tsc -b
```

UI has no automated suite. Backend tests assert behavior, not private fields.

---

## Context funnel (shipped)

| Slice | Behavior |
|-------|----------|
| **C0** | Append-only `transcript.jsonl` under user data; secrets redacted |
| **C1** | `compaction_summary` on the tree; folded rows stay in SQLite |
| **C2** | Folded user originals kept (near → far, 8K token cap) |
| **C3** | `transform_context` before every LLM call; mid-loop uses the same hook |
| **C4** | `search_session` over this session’s JSONL + spill only |
| **C5** | `POST /compact` + occupancy; `auto_compress` still defaults **off** |

C6 (compress after a tool batch) and C7 (branch summary on regenerate) are intentionally later.

---

## HTTP (selected)

- `GET /health`
- `GET|POST /api/sessions` · `PATCH|DELETE /api/sessions/{id}`
- `GET /api/sessions/{id}/messages?view=all|active`
- `POST /api/sessions/{id}/messages` — SSE turn
- `POST /api/sessions/{id}/regenerate` · `/cancel` · `/steer` · `/compact`
- `GET /api/sessions/{id}/context`
- `GET|PUT /api/settings` · `/api/model-profiles`

---

## Repository map

```text
src/            window (React)
backend/src/   FastAPI + agent_window
docs/           charter, roadmap, manual, research  → docs/README.md
scripts/        dev, install helpers, smoke
shell/          loop-window (C)
```

Do not drop one-off scripts on the repo root. Paths with spaces must be quoted.

---

## Status

Architecture stages **A0–A4** are in. The context funnel **C0–C5** is in, then audited against the plan. Default auto-compress is a separate, reversible commit. See [`CHANGELOG.md`](CHANGELOG.md) and [`docs/foundation-status.md`](docs/foundation-status.md).

---

## License

See the repository license file if present; otherwise treat this checkout as the author’s source tree.
