# 不做清单对齐：C6 / C7 / N2、auto_compress、Electron、MCP

> L3 对齐记录。给过夜与协作者看同一份「先不做」。  
> **不是开工单，不授权改产品默认，不含实现。**  
> 日期：2026-11-05（Asia/Shanghai）。  
> 冲突序：宪章 > 路线图 > [`foundation-status.md`](../../foundation-status.md) > 其余 docs。本文服从前三者。

产品名只称 **Loop Agent**。C0–C5 已在树里。下面六项维持现状，直到另行明示。

| 项 | 对齐 |
|----|------|
| **C6** | 缓做。工具批之后的中途压不开工 |
| **C7** | 缓做。regenerate 弃枝摘要不开工 |
| **N2** | 暂缓。MCP client 与环内 MCP 总线不开工 |
| **`auto_compress`** | 产品默认保持 **关** |
| **Electron** | 不做。桌面维持 `loop shell` / WebKitGTK |
| **MCP** | 现阶段不做。与路线图暂缓面放在一起 |

本文随 Draft PR 入库，标题含 **DO NOT MERGE**。入库只为能读到同一份对齐，不表示合并，也不表示可以开工。

---

## 1. 已经在树上的（对照）

漏斗主路径是 C0–C5，审查记录在 [`context-loop-c0-c5-review.md`](../context-loop-c0-c5-review.md)，方案在 [`plans/context-loop-strengthen.md`](../../plans/context-loop-strengthen.md)。

| 切片 | 行为 |
|------|------|
| C0 | 用户数据目录里只追加 `transcript.jsonl`；密钥打码 |
| C1 | `compaction_summary` 上树；原文留在 SQLite 与 JSONL，leaf 路径跳过 |
| C2 | 被折 user 近→远保留，默认 8K token 帽 |
| C3 | 进模型前走同一个 `transform_context`；两次 LLM 之间可再压并上树 |
| C4 | `search_session` 只搜本会话 JSONL 与 spill |
| C5 | `POST .../compact`（可带 `focus`）与 `GET .../context` 占用条 |

C3 的环内压发生在 **turn 之间**（下一次 LLM 之前）。`after_tool_batch` 只跑 Goal / 探索钩子，不在这里压。那一步是 C6。

手动 compact 在请求里把压缩调用标成强制执行，用来压当前路径。它不改 `agent_settings` 里的 `auto_compress`。设置默认仍是 `DEFAULTS["auto_compress"] = False`。

---

## 2. C6 · 工具批之后中途压（缓做）

方案原文（可选，约 2 日）：`after_tool_batch` 若 working 超阈值，调用**同一个** `transform_context`。纪律：不得插在 `assistant.tool_calls` 与未完成的 `tool` 结果之间。拆开会让网关 400。

缓做的原因：

- 切点必须落在完整 tool 对之后，要有专门回归，不能靠「文档里写一句」带过。
- 闸门是 C3 已绿，外加「批中压不拆 tool 对」的测试。C3 绿不等于 C6 可以夹进别的 PR。
- Cursor 有长工具轮中途压。本仓先守住 tool 对边界，再决定要不要抄这个时机。

过夜、文档刀、上下文小修都不带 C6 空脚手架，也不把 C6 写成默认里程碑或 CI 必过项。

---

## 3. C7 · regenerate 弃枝摘要（缓做）

方案原文（可选，约 2.5 日）：用户 regenerate 时，对旧 assistant 枝做 LCA，生成 **5 节**短摘要（无 Critical），经 `convert_to_llm` 变成 user，放在新枝开头。复用现有 summarize，**换 prompt**。不另写第三套 `coerce`。

现状：regenerate 已是分支。旧 assistant 留在同一 user 下，新 sibling 更新 `leaf`。leaf 路径不含旧枝。弃枝摘要未做。切支导航 UI 仍后置（宪章 §4）。

缓做的原因：

- 闸门是 C1，且只覆盖**已经存在的 regenerate**。完整切支 UI 仍后置。
- 摘要形态、长度帽、是否进六节狗粮，都还没有单独拍板。先做会和已验收的六节挤在一起。

本轮只保证 regenerate 沿 parent、不丢 leaf。C7 等明示再开。

---

## 4. N2 · MCP client 与环内总线（暂缓）

N2 **不是**上下文漏斗的下一刀。C8（工作区可选 `TASK.md`）、C9（followUp 外层）仍写在方案里，和 N2 不是同一条编号。

N2 在过夜对齐里指：**MCP client，以及把 MCP（含把外部 MCP server 当成环内总线）接进 Agent 环**。路线图 §4.6 把 MCP 与网页 fetch/search、PDF 抽取、多 Agent、Project OS、Cordis/换皮、原生 Anthropic/Google 翻译器放在同一张暂缓表。宪章 M01 的减法是：MCP / 计划 / 子 Agent / 审批弹窗默认不做。

和 N2 绑在一起的边界：

- 不接 MCP client。
- 不用 MCP 服务器当 seat / worker 的环内总线。若以后做 seat，通信留在进程内队列，worker 仍走同一个 `run_agent_loop`。那是另一份设计，本文不批准开工。
- 不把 tmux 舰队、跨 CLI 编排和 N2 捆成「顺手的底座」。

N2 开工条件：点名 N2，并单独开范围。上下文 PR、狗粮、文档审查都不夹带 MCP 依赖或空客户端。

---

## 5. `auto_compress` 保持关闭

| 项 | 对齐 |
|----|------|
| 存储默认 | `auto_compress: False`（`services/agent_settings.py` 的 `DEFAULTS`） |
| 超限自动压 | 只有设置里打开之后，`compress_messages_if_needed` 才在未 `force` 时折叠 |
| 手动压 | C5：`POST /api/sessions/{id}/compact`，占用条照常工作 |
| 改默认 | 单独提交，写 CHANGELOG 与 `foundation-status`。方案里「C5 狗粮之后默认开」**不**被本文执行 |

过夜材料、狗粮剧本、设置说明都按 **关** 来写。需要压某次长对话时走手动 compact，不把默认改成开。Settings 或配置样例里把默认写成 `true`，算越界。

占用条是 `chars/4` 估算，不是网关账单。默认关时占用条仍然可读。

---

## 6. 不做 Electron；现阶段不做 MCP

桌面路径已经定在 **`loop install` / `loop shell` + WebKitGTK**（Linux / WSL）。关窗停掉该壳拉起的后端。用户数据在 `~/.local/share/loop-agent`。开发服务仍是 8000 / 5173，壳用 8765。

Electron 不进入本阶段：

- 不开 Electron 工程、不开双壳对照实现。
- [`app-packaging-gap.md`](../app-packaging-gap.md) 写于桌面壳落地之前，曾把 Electron 或 Tauri 列为候选。那是早期差距笔记。当前桌面以 `loop shell` 为准，该笔记不授权再开一条 Electron 路线。
- 物理包名仍是 `agent_window`。全仓改名不跟这篇对齐一起做。

MCP 与 Electron 分开写，是因为仓库里已经有人把二者放进同一句「后置」。对齐时两句都算数：

- **Electron：** 不做。
- **MCP：** 现阶段不做（即 N2）。路线图暂缓表里的网页 fetch/search、PDF、多 Agent 同样不混进这次上下文守成。

---

## 7. 相邻项（同一张禁区，避免夹带）

这些在宪章、方案或 C0–C5 审查里已经写过。列在这里，避免「只禁了 C6」时从旁边绕进去：

| 项 | 对齐 |
|----|------|
| 六节改成 Codex 四条 | 维持六节。狗粮与 `coerce_six_sections` 按六节验收 |
| 加密 compact blob / 服务端 compact API | 不接。协议保持 OpenAI 兼容 |
| 策略焊进 `loop.py` | 压缩、检索、落盘留在 services / coding / window |
| keychain 或密钥托管大改 | 不跟本对齐走。密钥说明仍以 [`api-key-storage.md`](../api-key-storage.md) 为调研 |
| C6/C7/N2 空脚手架 | 不提交「方便以后」的钩子、标志位或依赖 |
| 产品默认 | Goal 默认 OFF、Preset 默认 YOLO、`auto_compress` 默认关。本文不改其中任何一项 |

---

## 8. 这篇本身不做什么

- 不改产品代码、测试、设置默认、前端文案。
- 不改仓库根 `README.md` / `README.zh-CN.md`。
- 不改 Living 进度的勾选：没有新交付，[`foundation-status.md`](../../foundation-status.md) 仍以 C0–C5 已落地为准。
- 不把本文升成 L1/L2。开工仍以宪章和路线图为准；要做 C6、C7 或 N2，另写方案并等明示。

一句话：守成 C0–C5；C6、C7、N2 缓做；`auto_compress` 保持关；桌面走 `loop shell`；MCP 保持暂缓。
