# 过夜文档索引（DRAFT，不要合并）

> **地位：** L3 导航页。把 2026-11-04 过夜并行草稿串起来，方便人/Agent 按需 `read`。  
> **不是** Living 进度（仍以 [`foundation-status.md`](../../foundation-status.md) 为准）。  
> **基线：** `47c18f98fc55f1faeaa9b2f967878323e4310520`（`main` = `origin/main`）。  
> **约束：** 只读文档；未改产品默认；**不**展开 C6 / C7 / N2；`auto_compress` 仍默认关。

## 速览

| 主题 | 入口 | 说明 |
|------|------|------|
| **健康检查** | [`2026-11-04-health.md`](2026-11-04-health.md) | 云端 Linux 上 pytest / tsc / oxlint 的命令、退出码、警告与 npm advisory；未起 8000/5173/8765 |
| **档案对照** | [`2026-11-04-profile-audit.md`](2026-11-04-profile-audit.md) | 路径禁逃、密钥打码、`.env` 检索边界、卸载、`loop.py` 单钩、`auto_compress` 默认与已知小洞 |
| **本目录说明** | [`README.md`](README.md) | 过夜审计目录约定（与 health-audit 草稿 PR 同批） |
| **功能地图** | [`../../feature-maps/README.md`](../../feature-maps/README.md) | 现有能力 → 源码路径；读序自下而上（目录 → 配置 → 环 → 工具 → C0–C5 → CLI/壳） |

功能地图各页摘要（详情见地图内文，此处不重复长列表）：

| 地图 | 一句话 |
|------|--------|
| [`runtime-dirs.md`](../../feature-maps/runtime-dirs.md) | 安装目录、用户数据、工作区与 CLI 配置目录 |
| [`config-hooks.md`](../../feature-maps/config-hooks.md) | `LoopConfig`、Preset、Goal 钩子、`agent_settings.json` |
| [`agent-core.md`](../../feature-maps/agent-core.md) | 会话树与 `run_agent_loop` |
| [`coding-tools.md`](../../feature-maps/coding-tools.md) | registry、沙箱、shell 白名单、记忆、Skills |
| [`context-funnel.md`](../../feature-maps/context-funnel.md) | C0–C5 漏斗（**不含** C6/C7、MCP client） |
| [`cli.md`](../../feature-maps/cli.md) | `loop` 子命令与 HTTP 对照 |
| [`shell.md`](../../feature-maps/shell.md) | `loop install` / `shell` / `uninstall`、8765 壳 |

## 并行草稿 PR（请勿合并）

| PR | 分支 | 内容 |
|----|------|------|
| [#3](https://github.com/masterroland13/loop-agent/pull/3) | `overnight/health-audit` | `docs/research/overnight/` 下健康 + 档案对照 + 本目录 `README.md` |
| [#4](https://github.com/masterroland13/loop-agent/pull/4) | `overnight/feature-maps` | `docs/feature-maps/*` 与 [`docs/README.md`](../../README.md) 中的 **feature-maps** 小节 |
| （本索引） | `overnight/docs-index` | 本文件 + [`docs/README.md`](../../README.md) **过夜** 小节（不重复 feature-maps 长列表） |

合并顺序由维护者定；在全部并入前，上表链接可能只在对应分支上存在。

## 与其它 docs 的关系

- **架构 / 进度：** [`architecture-charter.md`](../../architecture-charter.md)、[`agent-window-roadmap.md`](../../agent-window-roadmap.md)、[`foundation-status.md`](../../foundation-status.md)。  
- **C0–C5 长文审查：** [`../context-loop-c0-c5-review.md`](../context-loop-c0-c5-review.md)。  
- **施工方案：** [`../../plans/context-loop-strengthen.md`](../../plans/context-loop-strengthen.md)（C6/C7 仍标为可选，过夜未开工）。
