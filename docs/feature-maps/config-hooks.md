# 配置与钩子

策略走 `LoopConfig`，不在 `loop.py` 或 `routes.py` 里散落 `if goal`。审批也不写进工具实现内部。

## LoopConfig

文件：`backend/src/agent_window/core/loop_config.py`。

| 工厂 | 结果 |
|------|------|
| `LoopConfig.default()` | Goal 关 + YOLO。先 `install_base_tool_hooks`，再 `install_preset_hooks` |
| `from_settings(goal_mode, preset)` | 在 default 上 `with_goal_mode` + `with_preset`。非法 preset 字符串回到 YOLO |
| `with_goal_mode(True/False)` | `core/goal_hooks.install_goal_hooks` |
| `with_preset` | `core/preset_hooks.install_preset_hooks` |

`convert_to_llm` 为空时 `__post_init__` 装上 `core/messages.default_convert_to_llm`。`compaction_summary` 变成带摘要标记的 user，模型看不到内部 entry 名。

钩子槽：

| 字段 | 谁装 | 环里干什么 |
|------|------|------------|
| `convert_to_llm` | 默认转换 | `AgentMessage` → OpenAI dict |
| `transform_context` | `services/context_transform.install_context_transform` | 进模型前压缩 + Goal pin。算法在 coding，不在 core |
| `before_tool_call` | `before_tool_call_preset` | 返回 allow / wait / block |
| `after_tool_call` | Goal 开时由 goal hooks | 观察之后的检查点笔记；Goal 关则清空 |
| `after_tool_batch` | Goal 开时 | 探索收敛等，**不在这里做压缩** |
| `on_turn_start` | Goal 开时 | 注入 Turn Goal |
| `should_stop_after_turn` | 预留 | |
| `get_steering_messages` | `core/steering.bind_steering` | 用户 `POST .../steer` 的插队 |
| `get_follow_up_messages` | 字段在 | 无人值守外环未接，保持空 |
| `on_final_reply` | 预留 | |
| `extra` | `observe_spill`、`tool_hooks`、`context_transform` 标记 | `with_observe_spill` 把过大观察写到会话 `turns/` |

`install_context_transform` 未传入开关时，读 `load_agent_settings()`。压缩成功且给了 `on_compressed` 时回调上树；回调抛错只记日志，不把半次失败伪装成环崩溃。`apply_transform_context` 在钩子为空时原样返回，`compressed=False`。

发送路径在 `api/routes.py`：`_bind_turn_transform` 末尾 `install_context_transform(...)`，以及 `_agent_turn_event_stream` 里若还没有 `loop_cfg` 再装一次。环内每次 LLM 前由 `loop.py` 的 `_run_one_turn` 调用 `apply_transform_context`。

## Preset

文件：`backend/src/agent_window/core/preset_hooks.py`。`decide_gate_preset`：

| Preset | `action` | `auto_apply` | 记忆 |
|--------|----------|--------------|------|
| YOLO | allow | 是 | 不强制确认 |
| Trusted | wait | 否 | 再看 `confirm_memory` |
| Strict | wait | 否 | `force_confirm_memory`，忽略 `confirm_memory=False` |

`memory_will_auto_apply`：block 绝不自动写；Strict 绝不自动写；其余在 auto_apply 或 `confirm_memory` 为假时可以自动写。

`resolve_gate_decision` 优先调 `before_tool_call`，再 `normalize_gate_decision`。工具管线顺序写在 `agent/gate_hooks.py`：prepare → before(pre) → settle(await_gate) → execute。等待发生在 `agent/tool_pipeline.py` 的 `run_tool_steps`，窗口或 CLI 决定 Apply / Reject。

## Goal 钩子

文件：`backend/src/agent_window/core/goal_hooks.py`。只在 `with_goal_mode(True)` 时装上。

| 函数 | 旧编号 | 行为 |
|------|--------|------|
| `resolve_session_goal` | F1+F8 | 抽取或钉住目标；变更审计由 routes 发，不在环中途分叉 |
| `apply_goal_start` | F1 | 注入一次 Turn Goal |
| `note_exploration_tool` | F7 | 只更新连续探索计数，不在 batch 中途插入提示 |
| `flush_goal_after_batch` | F2/F7 | batch 结束后的检查点 / 收敛 |
| `install_goal_hooks` | | Goal 关时清掉上述槽 |

实现仍在 `agent/goal.py`、`agent/checkpoint.py`、`agent/exploration.py`。`core/tool_hooks.py` 的观察瘦身（F4）每次都跑，包括 Goal 关。`exploration_note_after_tool` 在 Goal 关时直接返回空。

## 治理文件

`backend/src/agent_window/services/agent_settings.py`，路径 `app_data_dir/agent_settings.json`。缺省（代码里的 `DEFAULTS`，不是把产品默认改掉）：

| 键 | 缺省 | 含义 |
|----|------|------|
| `auto_compress` | `False` | 超限才自动压。关着时只有 `force`（手动 compact）会压 |
| `confirm_memory` | `True` | Trusted 下记忆是否还要确认 |
| `context_limit` | `8192` | 占用与压缩阈值的分母 |
| `loop_preset` | `yolo` | 非法值归一成 yolo |
| `active_skills` | `[]` | 激活的 skill id |
| `approval_timeout_sec` | `300` | 审批等待 |
| `disabled_tools` | `[]` | |
| `max_tool_iters` | `24` | 一轮里 LLM↔工具的上限，触顶软着陆 |
| `checkpoint_every_n_tools` | `4` | Goal 检查点间隔；0 表示按间隔关掉 |
| `exploration_repeat_threshold` | `6` | 同一探索工具连续次数；0 表示关 |
| `vision_model` | `""` | 空则用 `Settings.llm_vision_model` |
| `user_md_char_limit` | `1375` | 钳在 500–8000 |
| `memory_md_char_limit` | `2200` | 钳在 500–8000 |

HTTP：`GET/PUT /api/settings`。前端 `src/hooks/useSettings.ts` 把 `auto_compress` 映成 `autoCompress`。设置面板展示开关，不把缺省改成开。

模型档案是另一份文件，见 [`runtime-dirs.md`](runtime-dirs.md)。会话新建时 `storage._snapshot_active_model` 把当前档案抄到 `profile_id` + `model_id`；之后各会话用自己的网关。解析在 `services/model_registry.py` 的 `resolve_turn_binding` / `resolve_handle`。`ModelHandle` 不含密钥。

## 插队

`backend/src/agent_window/core/steering.py`：`push_steering` / `drain_steering` / `bind_steering`。队列在内存，按 `session_id`。环在 turn 开头抽走，插进 working。

## 相关测试

`backend/tests/test_loop_config.py`、`test_preset_hooks.py`、`test_preset_yolo.py`、`test_goal_hooks.py`、`test_goal_mode.py`、`test_tool_hooks.py`、`test_agent_settings.py`、`test_steering.py`、`test_context_transform.py`、`test_convert_to_llm.py`、`test_yolo_gate_no_pending.py`。
