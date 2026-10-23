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

## A0 验收（import）

- [x] `agent_window.core` 存在且不 import `agent_window.api` / `agent_window.models`
- [x] `LoopConfig` 可被 `run_agent_loop` 接收（钩子暂未改行为）
- [ ] 全量物理搬迁（留给后续阶段）

人工复查：改 core 时跑 `tests/test_layer_boundaries.py`。
