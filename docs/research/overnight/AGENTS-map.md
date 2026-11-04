# 给后续编码 Agent 的阅读地图

> **层：** L3 草案，放在 `docs/research/overnight/`。默认不进系统提示，不当进度源，不覆盖根 [`AGENTS.md`](../../../AGENTS.md)。  
> **冲突序：** [`architecture-charter.md`](../../architecture-charter.md) > [`agent-window-roadmap.md`](../../agent-window-roadmap.md) > [`foundation-status.md`](../../foundation-status.md) > [`plans/`](../../plans/) > 本文件与其余 research / design / archive。  
> **日期：** 2026-11-04。对用户只称 **Loop Agent**。  
> 根 `AGENTS.md` 已读过（L0，约测试 / 提交 / 环境 / 模型防线）。本稿不改它。短增补提案见同目录 [`PROPOSAL-root-AGENTS.md`](PROPOSAL-root-AGENTS.md)。

仓库没有 `feature-maps/` 目录。下文「功能地图」就是点名的那几节：回答「这个行为挂在哪一层、哪个钩子」。

---

## 1. 先读哪里

按这个顺序。读完再改。本文只指路。

| 序 | 读 | 读到哪停 | 用它做什么 |
|----|----|----------|------------|
| 1 | **宪章** [`architecture-charter.md`](../../architecture-charter.md) | §0–§1（原则、Goal、Preset、四层、运行时三目录）；改行为再读 §3 原语、§4 现状表 | 架构与新建的唯一真源 |
| 2 | **功能地图** | 见 §2。先宪章 §4，再按改动点进手册对应节 | 能力落在哪一层 |
| 3 | **进度** [`foundation-status.md`](../../foundation-status.md) | 文首表、§1 A0–A4、§2 收编、§5 backlog | **唯一** Living。最后更新 2026-10-24：A0–A4 完成；C0–C5 已落地 |
| 4 | **方案** [`plans/`](../../plans/) | 只读和本次任务同题的一篇 | 施工切片与闸门。未完成前不升入 `design/` |
| 5 | **分层细则** [`layer-boundaries.md`](../../layer-boundaries.md) | 全文，短 | import 方向。改 `core/` 时跑 `backend/tests/test_layer_boundaries.py` |

路线图是交付阶段与验收口径。A0–A4 已完成。不要按路线图 §4.2 里「当前建议开工」的旧语气重开 A1。阶段定义要改时才改路线图。

索引在 [`docs/README.md`](../../README.md)。新调研进 `research/`，冻结方案进 `archive/`，狗粮进 `dogfood/`，定稿设计进 `design/`。不要在 `docs/` 根再堆长文。不要把 `archive/foundation-*` 当进度。

---

## 2. 功能地图（feature-maps）

三处一起用。进度勾选以 Living 为准；路线图表里的「迁移债」列可能停在收编之前。

| 问题 | 地图 | 层 |
|------|------|----|
| 目标态：钩子、双管道、模式矩阵、Registry、记忆四层 | 宪章 §3 | L1 |
| 今天这项能力在哪一层、收编了没有 | 宪章 §4「现状 vs 目标」 | L1 摘要；勾选细节以 Living §2 为准 |
| 环、树、压缩漏斗、工具、HTTP、读代码顺序 | [`design/loop-agent-manual.md`](../../design/loop-agent-manual.md) | L3，改到这块再读 |
| 旧 F1–F9 挂到哪个钩子 | 路线图 §3；Living §2 是收编状态 | L1 定义 / L2 勾选 |

手册 §12 的读代码顺序，在宪章 §0–§1 之后：

1. `backend/src/agent_window/core/loop_config.py`、`core/session_tree.py`
2. `agent/loop.py` 的 `_run_one_turn`（只看调度，不往里加策略）
3. `services/context_transform.py` → `compress.py` → `compaction_persist.py`
4. `services/session_transcript.py` → `session_search.py`
5. `api/routes.py` 的发送 / compact
6. 前端 `src/App.tsx`、`ChatInput.tsx`

**进行中的方案（有任务才打开）：**

| 文件 | 状态 |
|------|------|
| [`plans/context-loop-strengthen.md`](../../plans/context-loop-strengthen.md) | C0–C5 已落地。C6 起方案标成可选；产品决定见 §4，不要开工 C6/C7 |
| [`plans/session-model-profiles.md`](../../plans/session-model-profiles.md) | §4 手测已通过（2026-10-23）。协议仍是 `openai-completions` |

L3 长文（C0–C5 审查、压缩对照、Pi 笔记、Files、打包）是档案。和宪章或 Living 不一致时，丢掉长文里的施工建议。

---

## 3. 分层与 import

物理包名仍是 `agent_window`。逻辑层与允许方向以宪章 §1、[`layer-boundaries.md`](../../layer-boundaries.md) 为准。禁止单独开「全文替换改名」PR。

```text
loop-window → loop-coding → loop-agent-core → loop-ai
                 ↘________________↗
```

箭头只向上。coding / core 可以使用 loop-ai 的原子类型。底层不 import 上层。

| 逻辑层 | 今日落点 | 可以 | 不可以 |
|--------|----------|------|--------|
| **loop-ai** | `services/provider.py`、`model_registry.py`、`llm_config.py`，`config.py` 里 llm_* | 被上层调用；OpenAI 兼容 Client | import `api` / `models` / FastAPI / SQLAlchemy / React；不知 core |
| **loop-agent-core** | `core/`（`LoopConfig`、`AgentMessage`、`session_tree`）、`agent/loop.py`、`goal.py`、`checkpoint.py`、`exploration.py`、`turn_event.py`、`observation.py` | 调 ai；被 window 调 `run_agent_loop` | import `agent_window.api`、`agent_window.models`、FastAPI、SQLAlchemy |
| **loop-coding** | `tools/*`，`services/` 里 patches、shell、memory、skills、workspace、compress、context_transform、落盘与检索 | 被 core 调度着执行 | 在工具内部写死「必须审批」（审批在 Preset / `before_tool_call`） |
| **loop-window** | `api/*`、`models.py`、`cli/*`、前端 `src/*`、`shell/loop-window.c` | 组装 system、调环、持久化、UI | 在 `routes.py` 里散落 `if goal` 改策略（走 `LoopConfig`） |

验收：`agent_window.core` 不 import `agent_window.api` / `agent_window.models`，由 `backend/tests/test_layer_boundaries.py` 守。core 不知 window；ai 不知 core。

运行时三个目录和 import 正交。环不拼安装路径。

| 目录 | 规则 |
|------|------|
| 安装目录 | `~/.local/lib/loop-agent`。界面、窗口程序、后端虚拟环境。入口 `~/.local/bin/loop`。`loop uninstall` 只删这里 |
| 用户数据 | `Settings.app_data_dir`。`APP_DATA_DIR` 优先，否则 `~/.local/share/loop-agent`。会话库、档案、记忆、`transcript.jsonl`。不是进程当前目录 |
| 工作区 | 用户选的文件夹，记在用户数据目录的 `workspace.json`。空则 coding 沙箱没有根 |

开发用 `APP_DATA_DIR=./data` 指向 `backend/data`。`loop shell` 不读 `backend/.env`。CLI 的 `~/.config/loop-agent` 不并进用户数据目录。

功能可以厚，厚在 coding / window 和可插钩子上。`LoopConfig` 工厂：`default()`（Goal OFF + YOLO）、`with_goal_mode`、`with_preset`。Goal OFF 时检查点与探索收敛不跑。

---

## 4. 禁止清单

下面五条在 Living 或方案改口之前都有效。改口只认宪章 / 路线图 / foundation-status，不认本草案。

### 4.1 MCP 暂缓

路线图 §4.6、Living §5、上下文方案 §1、宪章 M01：MCP 不做。同一暂缓桶还有网页 fetch/search、PDF 抽取、多 Agent、Project OS 全阶段、Cordis/换皮、原生 Anthropic/Google 翻译器。调用协议保持 OpenAI 兼容。不要加 MCP client、server 或工具桥。

### 4.2 不上 Electron

桌面壳已经是 `loop shell`：源码 `shell/loop-window.c`，开窗拉起安装目录里的后端，关窗停进程，页面由该后端托管。数据在用户数据目录。

[`research/app-packaging-gap.md`](../app-packaging-gap.md) 里「Electron 或 Tauri 首选」是更早的封装调研，停在双进程浏览器阶段。已落地的壳以宪章 §1.4、`layer-boundaries.md`、Living 2026-10-23 安装记录为准。不要新开 Electron 工程，也不要把桌面进程改回读 `backend/.env`。

### 4.3 不把新策略焊进 `loop.py`

`agent/loop.py` 调度环：`_run_one_turn` 在进模型前调用一次 `apply_transform_context`（`services/context_transform.py`）。切点、六节、`find_cut_index` 留在 `services/compress.py`。core 不 import compress。

新行为放在对应层：Goal / 检查点 / 探索收敛 → `GoalModeHooks`；审批 → `before_tool_call` 与 Preset；观察瘦身 → `core/tool_hooks`；失败续环 → `agent/gate_policy.py`；压缩与落盘 → coding `services/`；HTTP / 上树写库 → window `routes`。

禁止按旧 F1–F9 再开一条旁路焊进 `loop.py`。禁止在 `loop.py` 或 `routes.py` 里用散落的 `if goal` 分叉。禁止复制第二份切点或六节 coerce。禁止在 `assistant` 的 `tool_calls` 和未完成的 `tool` 消息之间插入 `user`。

### 4.4 `auto_compress` 保持默认关

`services/agent_settings.py` 的 `DEFAULTS["auto_compress"]` 是 `False`。超限自动压只在开关打开时发生。C5 方案里「狗粮绿后改为默认开」是单独提交，Living 与 `CHANGELOG.md` 都写明尚未改。不要在别的改动里把默认值改成 `True`，也不要在文档里写成已经默认开。

要验证压缩触发时，按 [`dogfood/section-7-compress-playbook.md`](../../dogfood/section-7-compress-playbook.md) 临时打开，并记下原 `context_limit`，测完恢复。手动压走 `POST /api/sessions/{id}/compact`，占用走 `GET .../context`。

### 4.5 不做 C6、不做 C7

C0–C5 已落地（全文 JSONL、摘要上树、保留 user、`transform_context`、本会话检索、手动 compact + 占用条）。审查文 [`research/context-loop-c0-c5-review.md`](../context-loop-c0-c5-review.md) 写明 C6/C7 缓做。

| 切片 | 是什么 | 为什么先不动 |
|------|--------|----------------|
| **C6** | `after_tool_batch` 里对 working 再压，必须走同一个 `transform_context` | 要插在完整 tool 对之后。现在环内压只发生在两次 LLM 之间。Living 仍写「可选 C6」，那不是开工令 |
| **C7** | regenerate 时对弃枝做 LCA，五节短摘要注入新枝 | 切支导航 UI 仍搁置。再生今天只保证沿 parent、不丢 leaf |

C8 工作区 `TASK.md`、C9 `get_follow_up_messages` 外环同样不要顺手接上。软着陆「继续」已经覆盖续跑。

### 4.6 相邻已收口的口子

- Steering 产品 UI 已撤回。`POST .../steer` 与队列留着。不要把插队按钮加回界面。
- 切支导航 UI 搁置。
- `get_follow_up_messages` 保持空。
- 包名保持 `agent_window`。core 全面改经 `ModelHandle` 调 ai 仍后置，不要在无关 PR 里收紧。
- Goal OFF 不注入 Turn Goal，不跑检查点，不跑探索收敛。

---

## 5. 和根 `AGENTS.md` 的关系

根文件是 L0，进系统提示，管测试、提交、模型防线、环境。本目录两份都是 L3：

- 本文件：阅读顺序、功能地图、import、禁止项的长说明。
- [`PROPOSAL-root-AGENTS.md`](PROPOSAL-root-AGENTS.md)：建议插进根文件的短段。**未合并。** 根 `AGENTS.md` 字节未改。

禁止项要进 Loop Agent 自己的运行时，必须写进根 `AGENTS.md`。research 默认不注入。在提案被接受之前，编码 Agent 以本节 §4 和宪章为准，不要假设根文件里已经有 MCP / Electron / C6 这几条。

---

## 6. 改代码时仍然要守的

本文件不放产品代码。真改行为时仍按根 `AGENTS.md`：

- 后端逻辑带 `backend/tests/test_*.py`。断言写输出里有什么、没有什么。先写失败复现，再修，回归留下。
- 全量：`PYTHONPATH=src python -m pytest tests/ -q`（在 `backend/`，用 `backend/.venv`）。前端 `npx tsc -b`。前端无自动化测试。
- `CHANGELOG.md` 的 `[Unreleased]` 加条目。动 A0–A4、Goal、Preset、收编行为时改 `foundation-status.md`。分层或原语变更改宪章。阶段定义变更改路线图。
- 创建 / 修改 / 运行要走 `propose_edit` / `propose_shell`。模型口头声称完成且本轮无 gate 时，环会挂未验证警告。被拒绝后重试必须再调工具。
- 提交前不要把 `*-test.py`、`dogfood_*.txt` 等残留入库。commit 用英文短句写 why。仓库未配身份时：`git -c user.name=caapap -c user.email=caapap@localhost`。
- 路径含空格时 shell 加引号。开发端口：后端 8000，前端 5173。`loop shell` 用 8765。
