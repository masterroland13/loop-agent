# Agent 环

逻辑层 **loop-agent-core**：`backend/src/agent_window/core/` 与 `backend/src/agent_window/agent/`。不 import `agent_window.api`、`agent_window.models`、FastAPI、SQLAlchemy。窗口负责组 system、落库、SSE；环负责一轮里的模型与工具。

## 会话树

文件：`backend/src/agent_window/core/session_tree.py`。消息认 `parent_id`，会话认 `leaf_id`。回退和 regenerate 移动 leaf，不删旧枝。

| 函数 | 行为 |
|------|------|
| `walk_to_root` | 从 leaf 走到根 |
| `build_path_from_session` | leaf → root 再反转，得到当前路径 |
| `persistable_path_messages` | 可上树、可进占用计数的路径消息 |
| `messages_to_agent_messages` | ORM 行 → `AgentMessage` |
| `build_llm_messages` | 路径 + `convert_to_llm` → 发给模型的 dict |
| `last_user_on_path` / `path_ending_at` | 路径上的切点辅助 |

HTTP：

- `GET /api/sessions/{id}/messages?view=all`：全部行，含被折、被弃 sibling。
- `view=active`：只走 leaf 路径。其它 view 400，`INVALID_VIEW`。
- `GET /api/sessions/{id}`：单会话，含 `leaf_id`、`goal_mode`、`workspace_root`。

`entry_type=compaction_summary` 是树上的视图节点。原文仍在 SQLite 与 `transcript.jsonl`，只从 leaf 路径排除。

## 环

入口：`run_agent_loop`（`agent/loop.py`）。一轮：`_run_one_turn`。

```text
run_agent_loop
  在 max_tool_iters 内：
    抽 steering
    on_turn_start（Goal 开才注入目标）
    apply_transform_context(working)     # 钩子；切点与六节不在本文件
    provider.chat_complete
    无 tool_calls → 终态
    否则 run_tool_steps 按序跑完这一批（先凑齐 tool 对）
    after_tool_batch
  触顶 → soft_land_*
```

停止看有没有 tool call。模型用文字说「已经写好 / 测试通过」而本轮没有对应 gate 事件时，`_looks_like_write_claim` 给回复挂未验证说明（`_append_note`）。被拒绝后重试必须再调工具。

软着陆：`soft_land_user_prompt`、`soft_land_banner`、`synthesize_soft_land_reply`、`soft_land_continue_user_message`。上限来自 `max_tool_iters`。继续按钮的文案拼装在 `src/utils/softLandContinue.ts`。

工具执行：`agent/tool_pipeline.py` 的 `run_tool_steps`，分发 `agent/tool_dispatch.py`。观察瘦身：`agent/observation.py`，经 `core/tool_hooks.slim_for_working`。SSE 与 trace 留全文，working 里是瘦身后的结果。过大全文经 `observe_spill` 进 `turns/`。

取消：`TurnCancelled` → SSE `error` / `TURN_CANCELLED`。供应商失败：`LLM_PROVIDER_ERROR`，文案经 `services/provider.humanize_provider_error`。模型不支持 tools schema 时发 `tools_disabled`，本轮不能 `propose_edit` / shell / memory。

思考文本：`services/reasoning.py` 的 `extract_reasoning_text`。环只在供应商真的给了 reasoning 时发 `thought`，空的不编造。

状态类型：`core/turn.py` 的 `AgentLoopState`、`TurnOutcome`。事件形状：`agent/turn_event.py`。trace 落在占位 assistant 上：`services/turn_trace.py` 的 `TurnTraceWriter`，由 `api/routes.py` 的 `_agent_turn_event_stream` 创建。

## 窗口里的一轮

`api/routes.py`（发送与 regenerate）：

1. `build_path_from_session` 取 leaf 路径。
2. 拼 system：`build_system_prompt` 一带。含工具名、`search_session` 一句、工作区提示、冻结的 USER.md / MEMORY.md、Skills catalog。产品自称只许 Loop Agent。
3. `LoopConfig.from_settings` + `install_context_transform`。
4. 先 `apply_transform_context`（发送前一次），再进 `run_agent_loop`（环内每次 LLM 前再一次）。
5. SSE：`meta`（Goal 关时不带 `goal` 键）、token、工具、`turn_meta`（含 `compress_method` / `compress_preview`）。
6. `finalize` 或中断路径 `finalize_interrupted` 落库，并 `append_message_event` 追加 JSONL。中断的 assistant 也写。

Goal 关：不注入目标块，不跑检查点 / 探索收敛。Goal 开：目标条与质量环只走钩子。

`get_follow_up_messages` 未接成无人值守外环。软着陆「继续」是用户再发一轮。

## 相关测试

`backend/tests/test_run_one_turn.py`、`test_loop_exit.py`、`test_loop_thought.py`、`test_write_claim.py`、`test_soft_land.py`、`test_session_tree.py`、`test_observation.py`、`test_empty_response.py`、`test_layer_boundaries.py`、`test_turn_trace.py`、`test_sse_detach.py`。

模型会不会主动调工具，单测不能证明。改提示或工具描述后要手测一轮真实对话。
