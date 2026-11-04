# Proposed `CHANGELOG.md` `[Unreleased]` fragment

> **Do not copy this into the real changelog yet. This PR must stay draft.**  
> Overnight PRs [#3](https://github.com/masterroland13/loop-agent/pull/3) and [#4](https://github.com/masterroland13/loop-agent/pull/4) are **open drafts**. They are **not merged**. They are **not** on `main`.  
> This file is L3 research. It is not Living progress (`docs/foundation-status.md` stays as-is).  
> No product code. `auto_compress` stays off. C6 / C7 / MCP client stay unstarted.  
> The real [`CHANGELOG.md`](../../../CHANGELOG.md) is **not** edited here.

Baseline: `47c18f98fc55f1faeaa9b2f967878323e4310520` (`main` = `origin/main` after `git fetch origin main`).

## Why this file exists

- **ZH：** 过夜两条草稿还没进 `main`。先把它们「含什么 / 不含什么」写成可粘贴的 `[Unreleased]` 片段，避免把未合并文档当成已发布行为，也避免 #4 自己改 CHANGELOG 时和后来的合并打架。
- **EN：** Keep `[Unreleased]` honest. The overnight docs exist only as drafts, so reviewers should not treat health reports or feature maps as shipped product behavior, and should not land two competing changelog edits.

## Overnight drafts (not on `main`)

| PR | Branch | Title | State | What it actually contains |
|----|--------|-------|-------|---------------------------|
| [#3](https://github.com/masterroland13/loop-agent/pull/3) | `overnight/health-audit` | docs: overnight health+audit (DO NOT MERGE) | **draft, not merged** | Read-only notes under `docs/research/overnight/`: health commands/exit codes, profile/security audit. Does **not** index `docs/README.md`. Does **not** change product code or defaults. |
| [#4](https://github.com/masterroland13/loop-agent/pull/4) | `overnight/feature-maps` | DRAFT DO NOT MERGE: 功能地图 `docs/feature-maps` | **draft, not merged** | L3 maps under `docs/feature-maps/` plus an index in `docs/README.md`. That draft **already edits** `CHANGELOG.md` with one Chinese `### Added` line. No Python / frontend / runtime change. |

Until those PRs merge, the real `[Unreleased]` on `main` stays as it is (Files rename/copy fix, C0–C5, shell, etc.). Do not replace that section with this file.

## What #3 contains (health reports)

Files (only on `overnight/health-audit`):

- `docs/research/overnight/README.md`
- `docs/research/overnight/2026-11-04-health.md`
- `docs/research/overnight/2026-11-04-profile-audit.md`

Recorded on cloud Linux (not the author’s WSL). Did not start 8000 / 5173 / 8765. Did not change the lockfile.

| Check | Result |
|-------|--------|
| `backend/.venv/bin/python -m pytest tests/ -q --tb=line` | exit 0; **461 passed**; 814 warnings; 0 failures |
| `npx tsc -b` | exit 0; no diagnostics |
| `npx oxlint -c config/oxlint.json src` | exit 0; 0 error; 14 warning |
| backend ruff / mypy | not run (`pyproject` has no such config) |
| `npm audit` | 3 high (nanoid 3.3.16, source-map-js 1.2.1, vite 8.1.5); lockfile left alone |
| product `TODO` / `FIXME` | 0 in `backend/src`, `src`, `docs` |

Profile audit (same PR): JSONL / session search stay inside the user data dir; `sk-` and sensitive keys redacted; `search_session` does not read `.env` / SQLite / other sessions; uninstall keeps user data; desktop `LOOP_SHELL=1` does not write the key into `.env`; `loop.py` only hooks `apply_transform_context`; `auto_compress` default remains `False`; no MCP client.

Left unfixed in #3 (intentionally, docs-only scope): workspace `grep` / `read_file` can still read a project `.env`; non-`sk-` secret shapes; `write_turn_blob` does not use the same escape check as JSONL; uninstall refuses equal install/data dirs but not nested ones.

## What #4 contains (feature maps)

Files (only on `overnight/feature-maps`):

- `docs/feature-maps/README.md` (read order)
- `runtime-dirs.md` — install dir / user data / workspace, CLI config, uninstall guards, desktop key not in `.env`
- `config-hooks.md` — `LoopConfig`, YOLO / Trusted / Strict, Goal hooks, `agent_settings.json`
- `agent-core.md` — session tree and `run_agent_loop`
- `coding-tools.md` — registry, sandbox, shell allowlist, memory, Skills
- `context-funnel.md` — C0–C5 only
- `cli.md` — `loop` subcommands
- `shell.md` — `loop install` / `shell` / `uninstall`, port 8765
- `docs/README.md` — new L3 index row + file list
- `CHANGELOG.md` — one proposed `### Added` line (do not land twice)

Does **not** implement C6, C7, or an MCP client. Does **not** turn `auto_compress` on.

## Proposed fragment (copy only after the matching PR merges)

Keep a Changelog groups. Insert under the existing `## [Unreleased]` → `### Added` on `main`. Do **not** delete current Unreleased bullets. If #4 merges first, replace that PR’s Chinese-only line with the bilingual bullet below instead of appending both.

```markdown
## [Unreleased]

### Added
- **过夜健康报告：** L3 只读记录 `docs/research/overnight/2026-11-04-health.md` 与 `2026-11-04-profile-audit.md`（对照 `47c18f9`：pytest 461 passed、`tsc -b`、oxlint、npm high 3 未改 lock；路径禁逃 / 打码 / `.env` 不进会话检索 / 卸载留用户数据 / `auto_compress` 仍关 / C6·C7·MCP 未开工）。不改运行时。
  - Why（ZH）：把过夜检查留在研究目录，健康数字和档案对照才有出处，又不把未修的洞伪装成产品修复。
  - Why（EN）：Keep the 2026-11-04 read-only health and profile notes findable without implying a product fix or a default change.
- **功能地图：** `docs/feature-maps/` 把壳、CLI、Agent 环、编码工具、C0–C5 漏斗、配置钩子、安装目录 / 用户数据 / 工作区指到当前源码路径；`docs/README.md` 收入 L3 索引。不含 C6 / C7 与 MCP client。`auto_compress` 默认仍关。
  - Why（ZH）：手册按分层讲行为，改代码时还是要自己找入口；地图只指路，不改默认、不开后置切片。
  - Why（EN）：Map current surfaces to source paths so a later edit starts at the right file, without treating the maps as a runtime or roadmap change.
```

## What not to do

- Do **not** merge this proposal PR into `main` as if Unreleased already contained those bullets.
- Do **not** edit the real `CHANGELOG.md` until #3 and/or #4 actually merge.
- Do **not** paste the health “461 passed / oxlint / npm high” numbers as `### Fixed` — nothing in product code was fixed.
- Do **not** list C6, C7, or MCP client. They are still unstarted.
- Do **not** say `auto_compress` was turned on.
- Do **not** treat `docs/research/overnight/` as Living progress.
