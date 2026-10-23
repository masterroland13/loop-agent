# Compaction 摘要质量：大厂对照与本仓取舍

> L3 调研。配套实现：`backend/src/agent_window/services/compress.py`（handoff 六节 + 路径清单 + 反 Goal 回声）。

## 问题

狗粮 §7 显示：压缩**能触发**，但摘要常把 Goal 复读进 Progress / Next / Critical；压后续聊只记得指令里的第一个文件名。根因是「归档式复述」而非「续作交接」。

## 对照

| 产品 | 核心做法 | 本仓采纳 |
|------|----------|----------|
| **Codex** | 摘要 = 给下一模型的 handoff；注入 handoff 前缀（据此续作、避免重复）；强制 progress / next / critical refs | 是：`COMPACTION_HANDOFF_PREFIX` + 交接向 `_SIX_SECTION_PROMPT` |
| **Cursor** | 结构化含 touched files / remaining tasks；摘要丢失后可搜 history 文件 | 本轮：Critical 路径清单。history-as-file **未做** |
| **Claude Code** | 压后重注 durable 规则；`/compact` + focus | system 拆分已保留；manual/focus 后置 |
| **Pi / 宪章 M09** | 6-section + read/modified files 累积 | Critical 用 markdown 路径列表（确定性 extractive + coerce 合并） |

不抄：Codex 加密 blob、Composer RL self-summarize。

## 本仓行为（升级后）

1. Summarize 按 CONTEXT CHECKPOINT 写六节；禁止 Goal 复读进其它节。
2. Extractive 抽 `collect_touched_paths` / `collect_tool_progress`，Critical 以路径为主。
3. `coerce_six_sections` 检测 Goal 回声 / 任务单粘贴 / 长总结，并用 extractive 替换；Critical 无路径时强制灌入 extractive 路径。
4. 摘要消息在 `【对话压缩摘要】` 后追加 handoff 前缀。
5. **小节分工（狗粮复测后）：** Constraints → 短标签（只读/不要改文件）；Key Decisions → 拒收「短总结」；已覆盖时 Next Steps →「等待用户下一指令」。
6. **Progress 诚实：** 摘要窗口无 tool 时写「未见工具结果（近端可能仍有未压入）」；禁止「尚未开始」；无工具时禁止 Next Steps「等待」。

## 下一阶段（未做）

- Cursor 式 transcript 落盘 + 可检索工具
- `/compact` + focus 指令
- CompactionEntry 上树 / transform_context 触发
