# 跨轮上下文加固：调研、施工与对照审查（C0–C5）

> L3 档案。权威仍是宪章 > 路线图 > [`plans/context-loop-strengthen.md`](../plans/context-loop-strengthen.md)。  
> 日期：2026-10-24。C6 / C7 按产品决定缓做。

本文记录：对照 Codex / Cursor / Claude / Pi 的调研结论、C0–C5 怎么落地、事后按方案逐刀审查时找到的洞、就地修掉的小问题、以及明确放下的大问题。

---

## 1. 问题从哪来

狗粮 §7 已经能触发压缩，但摘要常把 Goal 复读进 Progress / Next / Critical，压完只记得指令里的第一个文件名。根因是「归档式复述」而不是「给下一模型写交接」。

2026-10-24 复审后又补了一层更硬的缺口：**压缩结果只活在当次 LLM 请求里**。摘要不上会话树，全文没有可检索落盘。下一轮从 `leaf` 重拼 SQLite 路径，等于没压。这和 Cursor / Pi「摘要进历史、原文另存」差一层。

约束（当时就钉死，后面审查也按这个判）：

- 后端行为必须有 pytest；断言写行为。
- 不把新算法焊进 `loop.py`。
- 冲突序：宪章 > 路线图 > foundation-status。
- 不做 MCP / keychain / Electron / 包重命名。
- 不默认打开 `auto_compress`（单独提交）。
- C6（工具批后中途压）、C7（regenerate 分支摘要）先不做。

---

## 2. 调研结论（漏斗，不按产品名抄）

调研真源：[`compaction-handoff-peers.md`](compaction-handoff-peers.md)。

| 产品 | 抄 | 不抄 |
|------|----|------|
| Codex CLI | 保留 user 原话；压后刷新 durable；多次压要可见 | 官方 4 节替换六节；加密 compact blob；绑死 OpenAI 服务端 |
| Cursor | 全文 JSONL 可搜；对话与 durable 分桶；最近 user；占用可见 | 关服摘要；文件 checkpoint（本仓已有审批/磁盘真源）；一上来就中途压 |
| Claude Code | 手动 compact + focus；压后重注 durable；有损要说清楚 | 服务端 compact API |
| Pi / 宪章 M09–M10 | CompactionEntry 上树；`transform_context`；摘要是路径上的视图 | 把策略焊回 `loop.py`；完整切支 UI |

漏斗四层（Pi 第 8 章）对照本仓：

| 层 | 当时已有 | 缺口 |
|----|----------|------|
| 单条体积 | F4 Observation + spill | 检索 spill 要走 blob，模型默认看不到 |
| 提示词加法 | system + Skills catalog + USER/MEMORY 冻结 | 压后不重读工作区规则文件 |
| 线性总长 | send 前 compress | 不上树、不留被折 user、环内不压、默认关 |
| 分支 | `parent_id` / `leaf_id` / regenerate=branch | 无 LCA 分支摘要 |

实施方案按漏斗切成必须按序的刀：C0 落盘 → C1 上树 → C2 留 user → C3 接线 → C4 检索 → C5 手动压 / 占用条。

---

## 3. 施工（C0–C5）

### C0 · 会话全文落盘

每个会话在 **用户数据目录** `session.data_path/transcript.jsonl` 只追加。事件：user / assistant / tool / gate / compact。密钥字段打码，附件只记 id 与文件名。不写工作区、不写安装目录、`loop uninstall` 不删。进模型的上下文不变。`loop.py` 零改。

钩子：`storage.add_message`、`TurnTraceWriter.note_sse` / `finalize`。

### C1 · Compaction 上树

压缩成功且方法是 `llm` / `extractive` 时，写 `entry_type=compaction_summary`。摘要挂在**被折区间原来的父节点**上（方案原文「接在被压区间末节点」按字面会把原文重新走回 leaf 路径，实现按排除原文的正确挂法）。`leaf_id` 不动。`build_path` 因此跳过被折原文，只带摘要 + 近端。旧消息留在 SQLite 和 JSONL。`tail_trim`、`auto_compress` 关、切点对不齐不写假摘要。

### C2 · 保留 user 原话

压缩输出 = durable system + 摘要 + 被折区间 user（近→远，默认 8K token）+ keep_recent。assistant / tool 不改成 user。persist 把留下的 user 挂在摘要和第一条 keep_recent 之间，下一轮 `build_path` 还在。元问题仍不进六节 Next Steps。

### C3 · `transform_context`

默认钩子在 `services/context_transform.py`（core 不能 import compress）。发送 / regenerate 与 `_run_one_turn`（两次 LLM 之间）进模型前调用同一函数。Goal OFF 不注入 Goal 块。`after_tool_batch` 不压（那是 C6）。`loop.py` 只有一行 `apply_transform_context`，没有第二份 `find_cut_index`。

### C4 · `search_session`

工具只搜本会话 JSONL + `turns/` spill，返回短摘录和行号。绑定当前 `session_id`；拒绝其它会话、绝对路径、`..`、`.env`。系统提示一句：摘要漏了细节就调工具，不要猜、不要整份倒。不搜 SQLite。

### C5 · 手动 compact + 占用条

`POST /api/sessions/{id}/compact` 可带 `focus`。`GET .../context` 给估算占用。输入区旁百分比，⋮ 可压。空会话 400。不改工作区。`auto_compress` 默认仍关。

---

## 4. 对照审查

方法：每一刀把方案验收条目和实现、测试对读。小问题就地改并补反向断言。大问题写清为什么这次不动。

### 4.1 C0

**对齐：** 位置、只追加、压缩不删行、卸载不删、密钥/附件打码、`loop.py` 未改。

**就地修：**

| 洞 | 处理 |
|----|------|
| `finalize_interrupted` 不写 JSONL，取消/报错的 assistant 整段缺 | 中断后也 `append_message_event` |
| YOLO 只发 `diff`/`shell`/`memory`，没有 `await_approval`，JSONL 无 gate | 这三类记 gate，不写 `unified_diff` |
| `tool_start` 只有 `arguments` 时丢入参 | 回退到 `arguments` |
| `data_path` 带 `..` 可能写到用户数据外 | 越界不写不读 |
| 一行坏 JSON 拖垮整文件读取 | 跳过坏行 |

**放下：**

- 进程被杀、来不及 finalize：token 只在 SQLite 每 8 片刷一次，JSONL 要等收尾。崩溃一致性要另开。
- 无 fsync / 文件锁。
- 会话目录缺失时静默不写（`create_session` 会建目录）。

### 4.2 C1

**对齐：** 摘要上树、leaf 不动、原文留盘、regenerate 换 sibling、未开压缩不写假摘要。方案「parent 接末节点」按实现（接被折区间原父节点）。

**就地修：**

| 洞 | 处理 |
|----|------|
| `add_message` 已提交，relink 失败留下孤儿摘要 | 回滚摘要和已改 parent |
| `rest_count` 对不齐仍用 working 的 cut 硬写树 | 对不齐不猜切点 |
| 上树失败也先写 JSONL compact | 上树成功后再追加 |

**放下：**

- `tail_trim`：当轮内存变短，树不改。禁止假摘要，不能随便落一条。
- 手动 compact 当时仍 `strict_align=False`（放到 C5）。
- 环内 working 比树长：需要对齐表，不是 C1 里一行能做完。

### 4.3 C2

**对齐：** 最近真实 user 仍是 `role=user`；超帽留近丢远；元问题不进 Next Steps；assistant/tool 不改成 user；persist 挂树。

**就地修：**

| 洞 | 处理 |
|----|------|
| 超帽后 `continue` 还会捞更早的短 user（背包） | 溢出即停（近→远前缀） |
| persist 总按默认 8K 再选，和当次压缩帽不一致 | `CompressMeta.keep_folded_user_tokens` 共用 |

**放下：**

- 「可设置」没接到 Settings UI（只有函数参数和 meta）。
- 最近一条 user 可单独超过 8K，整段留下可能顶满当轮。截断原话违背 C2。
- 只有图片、没有文本的 user 会被跳过。

### 4.4 C3

**对齐：** 发送与环内 LLM 前同一钩子；Goal OFF/ON 行为对；没有第二份切点；没有插在 tool 对中间压。钩子放 services 而不是 core，避免 core import compress。

**就地修（本刀里偏大的一条）：**

环内 working 带树上没有的 tool 结果，`rest_count` 对不齐。C1 收紧后生产路径不再猜切点，变成「内存压了、树没动」。补 `persist_compaction_from_tree`：用当前 leaf 路径重算 `find_cut_index`，摘要正文仍用刚压出来的那份。树够长才写；短树且全落在 keep_recent 则跳过。

**放下：**

- 发送路径压一次，进 loop 第一轮再调一次（通常已低于阈值）。
- 树很短、爆的是 working 里的 tool：当轮上下文会短，树不变。和 C6 同类。
- `on_compressed` 吞异常，persist 失败不挡生成。

### 4.5 C4

**对齐：** 只搜本会话 JSONL + spill；越权拒绝；输出有帽；不搜 SQLite；系统提示一句。

**就地修：**

| 洞 | 处理 |
|----|------|
| 命中在 `name`/`path`，摘录只看 `content` | 摘录拼 content/preview/name/path/command |
| 坏 `max_hits` 抛异常 | `INVALID_ARGS` |
| `data_path` 逃出 APP_DATA_DIR 仍可能当根扫 | 会话根必须在用户数据下 |
| `turns/foo.env` 能搜 | 后缀 `.env` 一并拒绝 |
| 缺「删 JSONL 不能改搜 SQLite」 | 补反向测试 |

**放下：**

- 多词 AND 且必须同行；改 OR / 跨行要防一次捞太多。
- 模型会不会调工具测不了，只能手测。
- 可被 `disabled_tools` 关掉。

### 4.6 C5

**对齐：** compact API + focus；占用百分比；空会话 400；不改工作区；默认 auto_compress 仍关；active 路径有摘要并留 user。

**就地修：**

| 洞 | 处理 |
|----|------|
| 压成功、树没写仍 200 | 先严格对齐，再 `persist_from_tree`；都失败 `400 COMPACT_NOT_PERSISTED` |
| Goal ON 手动压不钉目标 | 走 `resolve_session_goal` |

**放下：**

- UI 没有 focus 输入（一键压缩）。
- 压完不重拉对话气泡（占用会更新；`view=all` 仍列出被折行）。
- `auto_compress` 默认开仍单独提交。

---

## 5. 明确不做（本轮）

| 项 | 原因 |
|----|------|
| C6 工具批之后中途压 | 必须插在完整 tool 对之后；要专门回归，避免网关 400 |
| C7 regenerate LCA 五节摘要 | 切支 UI 仍搁置；本轮只保证 regenerate 沿 parent、不丢 leaf |
| 六节改成 Codex 4 条 | 狗粮与 `coerce_six_sections` 已按六节验收 |
| 把检索/落盘/UI 写进 `loop.py` | 分层：coding / window；core 只塑形 |

---

## 6. 简历怎么写（可直接改数字后用）

下面按「能答辩」来写：每条都对应仓库里的宪章、方案、pytest 和审查记录。把「独立完成」改成你的真实比例。

### 6.1 中文（项目经历）

**Loop Agent｜本地编码 Agent（桌面窗口 + FastAPI + 会话树）｜核心开发**

- 从零做到可安装的本地 Agent：React/Vite 窗口、FastAPI/SQLite 后端、WebKitGTK 桌面壳、`loop` CLI；运行时拆成安装目录 / 用户数据 / 工作区，卸载不删用户数据。
- 把 Agent 环收成可插钩子的薄循环（`LoopConfig`）：Goal 模式、YOLO/Trusted/Strict 审批、Steering、观察瘦身与写盘诚实化；禁止把策略焊进 `loop.py`。
- 对照 Codex / Cursor / Claude / Pi 做上下文交接调研，按漏斗落地 C0–C5：只追加 JSONL、Compaction 上会话树、保留被折 user、`transform_context` 接线、会话内检索、手动 compact 与占用条。压缩不删原文，下一轮只从 leaf 路径排除。
- 对照方案逐刀审查并补洞：中断轮次落盘、relink 失败回滚、环内压按树重算切点、检索不越权不回退 SQLite。行为用 pytest 锁住（断言输出，不断言内部变量）。

### 6.2 英文（一页简历）

**Loop Agent — Local coding agent (desktop + FastAPI + session tree)**

- Shipped an installable local agent: React/Vite UI, FastAPI/SQLite, WebKitGTK shell, `loop` CLI. Runtime dirs are install / user-data / workspace; uninstall never deletes user data.
- Extracted a thin, hook-driven agent loop (`LoopConfig`): optional Goal mode, YOLO/Trusted/Strict gates, steering, observation slimming, honest write claims. New policy does not land in `loop.py`.
- After a Codex/Cursor/Claude/Pi handoff study, implemented a compaction funnel (C0–C5): append-only JSONL, compaction nodes on the session tree, kept user originals, `transform_context`, in-session search, manual compact + occupancy. Folded text stays on disk; only the leaf path omits it.
- Audited each slice against the plan; fixed persist rollback, mid-loop tree realignment, and search confinement. Backend behavior locked with pytest.

### 6.3 面试时三句

1. **不是又一个 Chat UI。** 产品是可拆的 Agent 外壳：窗口、CLI、环、工具层分开，依赖只向上。
2. **压缩不是删历史。** 全文在 JSONL，摘要在树上，模型默认走 leaf；要细节就 `search_session`。
3. **环要薄。** 六节、切点、检索、落盘都不进 `loop.py`；环只在正确时机调钩子。

---

## 7. 相关路径

| 角色 | 路径 |
|------|------|
| 调研 | `docs/research/compaction-handoff-peers.md` |
| 方案 | `docs/plans/context-loop-strengthen.md` |
| 进度 | `docs/foundation-status.md` |
| 落盘 | `backend/src/agent_window/services/session_transcript.py` |
| 上树 | `backend/src/agent_window/services/compaction_persist.py` |
| 压缩 | `backend/src/agent_window/services/compress.py` |
| 接线 | `backend/src/agent_window/services/context_transform.py` |
| 检索 | `backend/src/agent_window/services/session_search.py`、`tools/session_tools.py` |
| 环 | `backend/src/agent_window/agent/loop.py` |
| 树 | `backend/src/agent_window/core/session_tree.py` |
