# Compaction 摘要质量：大厂对照与本仓取舍

> L3 调研。配套实现：`backend/src/agent_window/services/compress.py`（handoff 六节 + 路径清单 + 反 Goal 回声）。  
> **实施方案：** [`docs/plans/context-loop-strengthen.md`](../plans/context-loop-strengthen.md)  
> **复审日期：** 2026-10-24（对照 Codex 开源仓、Cursor 公开文档、Claude Code 文档、Pi 第 8 章）。

## 问题

狗粮 §7 显示：压缩**能触发**，但摘要常把 Goal 复读进 Progress / Next / Critical；压后续聊只记得指令里的第一个文件名。根因是「归档式复述」而非「续作交接」。

2026-10-24 复审后，还要加上：**压缩结果只活在当次 LLM 请求里，没有上会话树，也没有可检索全文**。下一轮会从 leaf 路径重新拼全文再压一次。这和 Cursor / Pi 的「摘要进历史、原文另存」差一层。

## 对照（2026-10-24）

| 产品 | 2026 公开做法 | 本仓现状 | 本仓该抄 / 不抄 |
|------|----------------|----------|-----------------|
| **Codex CLI** | 官方本地 prompt 是 **4 条手递清单**（进度与决策 / 约束偏好 / 剩余工作 / 关键引用），不是六节模板。摘要当前缀 user 消息。**保留用户原话**（约 20K token，从近到远）。压后**拆掉旧 system 再注入新鲜初始上下文**。OpenAI 路径另有服务端 `/responses/compact` + 加密 blob，可在推理中途压。多次压缩会警告精度下降。 | 六节 + handoff 前缀 + Goal pin。**不保留被压掉的 user 原文**。system 会留下 `other_system`，Goal 会重注。只在 **send / regenerate 前**压，环内不压。 | **抄：** 保留 user 原话、压后刷新 durable 上下文、多次压缩可见。**不抄：** 加密 blob、服务端中途压、改成 4 节（会冲掉已测过的六节与 coerce）。 |
| **Cursor Agent** | 窗口将满时自动摘要，**长工具轮中途也会压**。`/summarize`（别名 `/compress` `/compact`）**不能写 focus**。规则 / Skills / 工具定义不进「对话」桶，压对话时它们还在。2026-09 起**最近一条 user 原话保留**。todos / plans 存在对话摘要外。全文 JSONL 在 `agent-transcripts/`，`store.db` 里有摘要档案。社区做法是工作区 `TASK.md` 当 durable 任务单。文件 Checkpoints 与对话压缩是两件事。 | 无上下文占用条。无手动 compact。无 transcript 文件。todos 不单独存活。压缩默认关。 | **抄：** 全文落盘可搜、对话与 durable 分桶、最近 user 保留、占用可见。**不抄：** 关服端摘要、文件 checkpoint（已有审批/磁盘真源）、强制中途压（放到后段）。 |
| **Claude Code** | `/compact [instructions]` **可带 focus**；接近上限自动压。压后**重读 CLAUDE.md** 注入。压是有损的；无关话题用 `/clear`。部分路径走服务端 compact API。 | system / USER.md / MEMORY 冻结快照每轮组装，压后 Goal 会重注；**没有**「压后重读工作区规则文件」这一步。无 `/compact`。 | **抄：** 手动 compact + focus、压后重注 durable、有损要说清楚。**不抄：** 服务端 compact API。 |
| **Pi / 宪章 M09–M10** | 六节 Compaction + `CompactionEntry` **写入 Session Tree**。`transformContext` 在进模型前塑形。分支跳转用 LCA 做 **5 节 Branch Summary**（无 Critical，maxTokens 2048）。工具结果在入口截断。Skills 拉模式。 | 六节 + extractive coerce **已有**。`LoopConfig.transform_context` **字段在、未接线**。压缩**不上树**。分支摘要 **未做**（切支 UI 搁置）。F4 slim / spill **已有**。Skills catalog **已有**。 | **抄：** CompactionEntry 上树、transform_context 接线、分支摘要（等切支或至少 regenerate）。**不抄：** 把所有策略焊回 `loop.py`。 |

不抄：Codex 加密 blob、Composer RL self-summarize、Cursor 关服摘要、把六节改成 Codex 官方 4 条。

## 本仓行为（A4 已落地，仍有效）

1. Summarize 按 CONTEXT CHECKPOINT 写六节；禁止 Goal 复读进其它节。
2. Extractive 抽 `collect_touched_paths` / `collect_tool_progress`，Critical 以路径为主。
3. `coerce_six_sections` 检测 Goal 回声 / 任务单粘贴 / 长总结，并用 extractive 替换；Critical 无路径时强制灌入 extractive 路径。
4. 摘要消息在 `【对话压缩摘要】` 后追加 handoff 前缀。
5. **小节分工（狗粮复测后）：** Constraints → 短标签（只读/不要改文件）；Key Decisions → 拒收「短总结」；已覆盖时 Next Steps →「等待用户下一指令」。
6. **Progress 诚实：** 摘要窗口无 tool 时写「未见工具结果（近端可能仍有未压入）」；禁止「尚未开始」；无工具时禁止 Next Steps「等待」。
7. 触发：`auto_compress` **默认关**；阈值 `context_limit - reserve_tokens`（默认 reserve 1024）；`keep_recent` 默认 2048 token。
8. 切点：`find_cut_index` 从尾累加，只切在 user/assistant，避免半轮孤儿。
9. 失败：LLM 摘要异常 → extractive；过短无法切 → `tail_trim`。

## 2026-10-24 实现缺口（按漏斗，不是按产品名）

漏斗四层（Pi 第 8 章）：单条体积 → 提示词加法 → 线性总长 → 分支遗忘。本仓对应：

| 层 | 本仓 | 缺口 |
|----|------|------|
| 单条 | F4 `ObservationResult` + head/tail + `file:` spill | 够用；检索 spill 要走 blobs，模型默认看不到 |
| 加法 | system + Skills catalog + USER/MEMORY 冻结 | 压后不重读工作区规则；冻结快照跨会话才更新 |
| 线性总长 | send 前 `compress_messages_if_needed` | 不上树；不保留被压 user；环内不压；默认关 |
| 分支 | `parent_id` / `leaf_id` / regenerate=branch | 无 LCA 分支摘要；切支 UI 搁置 |

## 下一阶段（已排进 plan，勿在调研里另开旁路）

见 [`docs/plans/context-loop-strengthen.md`](../plans/context-loop-strengthen.md)：C0 全文落盘 → C1 上树 → C2 保留 user → C3 `transform_context` → C4 检索 → C5 手动 compact / 占用条 → 其后才是中途压与分支摘要。
