# Loop 逻辑分层边界（A0）

> 服从 [`architecture-charter.md`](architecture-charter.md) §1。  
> **物理包名**仍为 `agent_window`；本文件约定 **逻辑层** 与允许的 import 方向。改名随 A0–A4 绞杀推进，禁止单独「全文替换 PR」。

## 逻辑层 ↔ 今日代码

| 逻辑层 | 今日落点（A0） | 职责 |
|--------|----------------|------|
| **loop-ai** | `services/provider.py`, `services/model_registry.py`, `services/llm_config.py`（adapter）, `config.py` 中 llm_* | Model Registry 多档案；OpenAI 兼容 Client；错误归一 |
| **loop-agent-core** | `core/`（`LoopConfig`、`AgentMessage`、`session_tree`）、`agent/loop.py`、`goal.py`、`checkpoint.py`、`exploration.py`、`turn_event.py`、`observation.py` | Agent 环、Turn、钩子、会话策略、树路径 |
| **loop-coding** | `tools/*`, `services/{patches,shell,memory,skills,workspace,compress}.py` | 文件系统/Shell/编辑/记忆/Skills |
| **loop-window** | `api/*`, `models.py`, `cli/*`, 前端 `src/*` | HTTP/SSE、持久化、CLI、UI |

## 依赖规则（箭头只向上）

```text
window → coding → agent-core → ai
         ↘______________↗  （coding/core 可用 ai 的原子类型）
```

| 允许 | 禁止 |
|------|------|
| core 调用 ai（chat_complete） | core / ai import `api`、`models`、FastAPI、SQLAlchemy |
| coding 被 core 调度（tools） | tools 内部硬编码「必须审批」（审批 ∈ Preset / beforeToolCall） |
| window 组装 system、调 `run_agent_loop` | window 在 routes 里散落 `if goal` 分叉策略（应走 LoopConfig） |

## 运行时三个目录

与上面的 import 方向正交。真源是宪章 §1.4。

| 目录 | 规则 |
|------|------|
| 安装目录 | 壳的事。`agent/` 环不拼这条路径 |
| 用户数据目录 | `Settings.app_data_dir`。`APP_DATA_DIR` 优先；否则 `~/.local/share/loop-agent`。不是进程当前目录 |
| 工作区 | `workspace.json` 记在用户数据目录里。空则 coding 沙箱没有根 |

CLI 的 `~/.config/loop-agent` 不放入上表。开发用 `APP_DATA_DIR=./data` 指向 `backend/data`。

`loop shell` 是桌面宿主，和浏览器、CLI 并列，不进 `agent/` 环。它开窗前把 `APP_DATA_DIR` 设成用户数据目录并拉起后端和界面，关窗后停掉这两个进程。窗口程序源码在 `shell/loop-window.c`。用户数据目录里还没有工作区时，窗口先走首次向导：填一个模型，再选或新建文件夹。新建只在当前浏览目录下建子文件夹，绑定仍走原来的工作区接口。桌面进程不读 `backend/.env`。

## A0 验收（import）

- [x] `agent_window.core` 存在且不 import `agent_window.api` / `agent_window.models`
- [x] `LoopConfig` 可被 `run_agent_loop` 接收（钩子暂未改行为）
- [ ] 全量物理搬迁（留给后续阶段）

人工复查：改 core 时跑 `tests/test_layer_boundaries.py`。
