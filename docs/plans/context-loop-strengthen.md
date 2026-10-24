# 上下文与 Loop 加固（进行中）

> L2 实施方案。权威：宪章 > 路线图 > 本文。调研真源：[`research/compaction-handoff-peers.md`](../research/compaction-handoff-peers.md)（2026-10-24 复审）。  
> **目标：** 跨轮交接达到「Cursor / Pi / Codex 本地压」同一量级，而不是把 `loop.py` 再焊厚。  
> **状态：** C0–C5 已落地。C0 已对照审查并补中断/gate/路径洞。`auto_compress` 默认开仍单独提交。可选 C6 起。

## 0. 一句话

把「上一次问答怎么进下一次」做成 **漏斗**：全文永不丢（落盘）→ 进模型的路径可压且压完上树 → durable 与对话分桶 → 模型能搜回原文。Loop 内核只负责在正确时机调用钩子。

## 1. 不追求、不返工

下列若先做，会冲掉已绿的六节狗粮或焊回 `loop.py`，**禁止作为本轮开工项**。

| 不做 | 原因 |
|------|------|
| 把六节改成 Codex 官方 4 条 | 狗粮 §7 与 `coerce_six_sections` 已按六节验收 |
| Codex 远程 `/responses/compact` + 加密 blob | 绑死 OpenAI；本仓协议是 openai-completions |
| 在 C1 之前做环内 / 中途压缩 | 压完无处落、下一轮从 DB 全量重拼，等于没压 |
| 在切支 UI 之前做完整 Branch UI | 宪章已搁置；再生时的 LCA 摘要可以后做 |
| followUp 外层无人值守环 | 钩子已有字段；先把 transform 接上再谈，避免双环 |
| Mem Provider / 外部记忆服务 | 宪章后置 |
| 把检索、落盘、UI 写进 `loop.py` | 分层：coding / window；core 只塑形 |
| 重命名 `agent_window`、core 全面经 Handle | 与本主题无关 |
| MCP / 多 Agent / 签名 / Electron | 桌面壳后置清单，不混进本计划 |

**水平对齐怎么说：** 对齐的是 **漏斗与交接契约**，不是像素级复刻 Cursor 关服。能说「压完还能搜回原文、user 原话还在、摘要在树上、durable 不被压掉」即达标。

## 2. 现状锚点（改之前先认这张图）

```
发送 → build_path(leaf) → system 现拼 → convert_to_llm
     → 本轮 user → compress_messages_if_needed（仅内存）
     → run_agent_loop
     → assistant 上树
```

`LoopConfig.transform_context` 与 `get_follow_up_messages` **有字段、发送路径未调用**。  
`auto_compress` **默认关**。压缩后的 `compaction_summary` **不写 DB**。

## 3. 切片（必须按序；每刀可独立合并）

每刀：**先写失败测试 → 改 → 全量 pytest 绿 → 狗粮勾选 → 再开下一刀**。  
禁止「C0–C5 一个 PR」。

### C0 · 会话全文落盘（约 1.5 日）

**做什么：** 每个会话在用户数据目录写 **只追加** JSONL（一条事件一行：user / assistant / tool / gate / compact）。不改 LLM 上下文。不删行。

**落点：** `loop-coding` 或 `services/`（session.data_path）；`routes` 在落库后 append。core / `loop.py` 零改。

**验收：**

- 发两轮后文件存在，行数 ≥ 消息数。
- 压缩开/关都不删 JSONL。
- 卸载程序不删这份数据（仍在用户数据目录）。
- **反向：** 不写工作区、不写仓库、不写安装目录；密钥不明文进 JSONL（已有附件/密钥字段打码或只存 id）。

**易返工：** 写进 workspace。必须进 `APP_DATA_DIR` / session 目录。

### C1 · CompactionEntry 上树（约 2.5 日）

**做什么：** 压缩成功后，把摘要存成 `entry_type=compaction_summary` 的消息，`parent_id` 接在被压区间的末节点；`leaf` 仍走当前 tip。`build_path` / `build_llm_messages` **跳过已折叠区间的原文**（或 `exclude_from_context`），只带摘要 + keep_recent。

**落点：** `core/session_tree.py` + `storage.add_message`；`compress.py` 返回要落库的摘要；`routes` 写库。`loop.py` 不写压缩算法。

**验收：**

- 压一次后 DB 有一条 compaction_summary。
- 下一轮 `build_path` **不含**被折区间的 tool 原文，**含**摘要 + 近端。
- JSONL（C0）仍有原文。
- regenerate 仍沿 parent 链，不丢 leaf。
- **反向：** 未开 `auto_compress` 时树上没有假摘要；失败的 compress 不写半条。

**易返工：** 物理删除旧消息。旧消息必须留着给检索和回放。只从 **进模型的路径** 排除。

**闸门：** C0 绿才能开。否则「上树」之后原文无处找。

### C2 · 保留 user 原话（约 1.5 日）

**做什么：** 压缩输出 = durable system + 摘要 + **被压区间内的 user 原文（从近到远，token 帽，默认 8K，可设置）** + keep_recent。对齐 Codex「保留用户消息」、Cursor「最近 user 原话」。

**落点：** 只改 `compress.py` 组装；测 `test_compress*.py`。

**验收：**

- 被压掉的最近一条真实 user 请求仍以 `role=user` 出现在压缩后列表（不是只在 Goal 里复读）。
- 超帽时丢更早的 user，留近的。
- 元问题（狗粮「贴六节」）仍不进 Next Steps（已有 `_is_meta_followup`）。
- **反向：** 不把整段 assistant / 大 tool 当 user 塞回去。

**闸门：** C1 之后。否则保留的 user 只存在当次内存，下一轮又没了。

### C3 · `transform_context` 接线（约 2 日）

**做什么：** 发送路径与 `_run_one_turn` **进模型前** 调 `config.transform_context`（缺省 = 现有 compress + Goal pin）。环内若超阈值，**只调用同一函数**，禁止复制一份 compress。

**落点：** `core` 默认钩子；`routes` 去掉内联调用、改走 config；`loop.py` 只在 stream 前一行调用，**不**把 coerce/六节搬进 loop。

**验收：**

- Goal OFF / ON 各一条：压后 Goal 行为与现在一致（OFF 不注入质量条）。
- 环内第二次超限会再压（可用很小 `context_limit` 的单测模拟），且仍上树（走 C1 API）。
- **反向：** `loop.py` 行数不明显膨胀；没有第二份 `find_cut_index`。

**闸门：** C1。环内压没有上树会立刻返工。

**注意：** 第一次环内压先做「turn 之间」（两次 LLM 之间），**不要**做「一条 tool_result 刚回来就压」。那是 C6。

### C4 · 检索已折原文（约 2.5 日）

**做什么：** 工具 `search_session`（或复用/收窄现有附件读取）：按关键词搜 **本会话 JSONL + spill blobs**，返回短摘录 + 行号/事件 id。Skills 式拉模式：system 只说「可用工具找回压缩前细节」。

**落点：** coding 工具 + registry；window 无需先做 UI。

**验收：**

- 压过后问「刚才 grep 的文件名」，模型调检索能拿到路径。
- 只搜本 session_id；越权路径拒绝。
- **反向：** 不搜其它会话、不搜 `.env`、不把全文 50KB 一次塞回。

**闸门：** C0。没有 JSONL 就不要做假检索（去搜 SQLite 原文会和 C1「排除进模型」打架）。

### C5 · 手动 compact + 占用条（约 2 日）

**做什么：**

- API：`POST /api/sessions/{id}/compact`，可选 `focus` 字符串（Claude 的 `/compact keep …`）。
- Settings：`auto_compress` 在 C1+C2 狗粮绿后 **改为默认开**（单独提交，可关）。
- UI：输入区旁占用百分比（估算 token / context_limit）；审计里能看到 compact 事件。

**验收：**

- focus「只保留 auth」时 Critical / Next 偏向这些词（测 prompt 入参含 focus，行为测可用固定 summarize mock）。
- 占用条在未超限时 < 100%；压后下降。
- **反向：** 空会话 compact 返回 400；不改磁盘工作区文件。

**闸门：** C1+C2。手动压也必须上树 + 留 user。

### C6 · 工具批之后中途压（约 2 日，可选）

**做什么：** `after_tool_batch` 若 working 超阈值，调 **同一个** `transform_context`。纪律：不得插在 `assistant.tool_calls` 与未完成 `tool` 之间（F7 / 网关 400）。

**闸门：** C3 绿 + 专门回归「batch 中途压不拆 tool 对」。Cursor 有中途压，但本仓先保证边界。

### C7 · regenerate 分支摘要（约 2.5 日，可选）

**做什么：** 用户 regenerate 时，对旧 assistant 枝做 LCA，生成 **5 节** 摘要（无 Critical，上限短），`role` 走 convert 成 user，注入新枝开头。复用 summarize 管道，**换 prompt**，不要第三套 coerce。

**闸门：** C1。完整切支 UI 仍可后置；本刀只覆盖 **已有 regenerate**。

### C8 · 工作区任务单（约 1 日，可选）

工作区可选 `TASK.md`（或 Settings 指定路径），system 加一句「长任务先读再改」。**不**自动创建、不进安装树。对齐 Cursor 社区 TASK.md，不是关服功能。

### C9 · followUp 外层（暂缓）

`get_follow_up_messages` 保持空。软着陆「继续」已够用。C3 稳定且有明确无人值守场景再开。

## 4. 工期

按一人、含测试与狗粮，不含桌面光标/安装。

| 切片 | 日 | 累计 | 必须 |
|------|----|------|------|
| C0 | 1.5 | 1.5 | 是 |
| C1 | 2.5 | 4 | 是 |
| C2 | 1.5 | 5.5 | 是 |
| C3 | 2 | 7.5 | 是 |
| C4 | 2.5 | 10 | 是（「大厂感」的检索） |
| C5 | 2 | 12 | 建议 |
| C6 | 2 | 14 | 可选 |
| C7 | 2.5 | 16.5 | 可选 |
| C8 | 1 | 17.5 | 可选 |

**主路径 C0–C5：约 12 个工作日。** 不要压成一周；C1 切错树会全盘返工。

## 5. 工作流程（防返工）

1. **开刀前**读本文 §1 与宪章 §1.2。新文件只放 `core/` `services/` `tools/` `api/` `tests/`；禁止新旁路进 `loop.py`。
2. **先测：** `backend/tests/test_*.py`，断言进模型的 messages **含/不含** 什么，不断言私有变量。每个正向断言配反向。
3. **复现顺序：** 压缩相关先扩 `test_compress*.py` / `test_session_tree.py`，再改实现。
4. **全量：** `PYTHONPATH=src python -m pytest tests/ -q`。已知 4 条 workspace-files 失败仍不修。passed 数应随新用例上涨。
5. **前端：** 仅 C5 改 UI；`npx tsc -b`。占用条手测。
6. **狗粮：** 每刀用 [`dogfood/section-7-compress-playbook.md`](../dogfood/section-7-compress-playbook.md) 缩一版（C0 只查文件；C1 起查 DB + 续聊）。C4 加「压后问路径、须调检索」。
7. **提交：** 一刀一 commit；英文 why。同步 `CHANGELOG` `[Unreleased]` 与 `foundation-status` 更新记录。
8. **默认开 auto_compress：** 单独 commit，写在 C5 狗粮通过之后。

## 6. 风险与回滚

| 风险 | 对策 |
|------|------|
| 上树后旧客户端只认线性 messages | `entry_type` 对未知客户端当普通 user；UI 先当折叠卡片 |
| token 估算与网关不一致 | 继续用现有 `approx_tokens`；阈值偏低比偏高安全 |
| 环内压导致 tool_call 缺 tool | C3 只在 turn 边界压；C6 单独测序 |
| JSONL 涨盘 | 只追加、按会话；不在本计划做 GC |
| 检索把密钥搜出来 | 落盘时打码；检索跳过 `api_key` / `authorization` 字段 |

回滚：C0 可停写文件；C1 可用设置「compress_persist=off」回退到仅内存压（该开关只为回滚，不进默认 UI）。

## 7. 完成定义（主路径）

- 长对话开 `auto_compress`：压后仍能对准 Critical 路径；问已折细节时能检索，而不是只记得第一个文件名。
- 刷新页面再发：模型仍看到摘要 + 近端 + 保留的 user，而不是「仿佛没压过的全文」或「空白失忆」。
- `loop.py` 没有新增压缩算法。
- 六节狗粮 §7.1–7.3 仍绿。
