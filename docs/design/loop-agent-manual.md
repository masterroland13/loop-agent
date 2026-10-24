# Loop Agent 技术手册

> 给要读懂、改装或运维本仓库的人。产品名只称 **Loop Agent**。  
> 架构冲突以 [`architecture-charter.md`](../architecture-charter.md) 为准。  
> 进度以 [`foundation-status.md`](../foundation-status.md) 为准。  
> 上下文加固过程见 [`research/context-loop-c0-c5-review.md`](../research/context-loop-c0-c5-review.md)。

本手册按**依赖从下往上**写：先运行时目录，再逻辑分层，再会话树与 Agent 环，再压缩漏斗，再窗口 / CLI / 桌面。这和 Pi Agent「ai → core → coding → tui」同一方向，也是本仓 `tests/test_layer_boundaries.py` 守的边界。

---

## 1. 它是什么

Loop Agent 是一台**可拆开的本地编码 Agent**：

- 薄的 Agent 环（模型 ↔ 工具，钩子可插）。
- 编码工具层（读改文件、shell、记忆、Skills）。
- 窗口 + CLI + 可选桌面壳（WebKitGTK）。

默认要好用：Goal 模式和审批都是可选的。默认 Preset 是 YOLO（本地可信工作区直接执行，仍审计）。点 Goal 才进入「死抱目标」的质量环。

对标关系（学结构，不抄整车）：

| 来源 | 学什么 |
|------|--------|
| Pi Agent | 分层、Session Tree、Compaction 上树、`transformContext` |
| Hermes | 有界 USER.md / MEMORY.md、冻结快照 |
| 本仓 Foundation | Goal 质量环（仅 Goal ON） |
| Codex / Cursor / Claude | 交接漏斗：落盘、留 user、手动 compact、focus、占用 |

不作为首页叙事：把「强审批弹窗」当核心差异。门控留着，但是 Preset，不是人格。

---

## 2. 运行时三个目录

和 import 分层正交。环不解析安装路径。

| 目录 | 默认位置 | 职责 |
|------|----------|------|
| **安装目录** | `~/.local/lib/loop-agent` | 界面、`loop-window`、后端 venv。入口 `~/.local/bin/loop`。桌面项 `~/.local/share/applications/loop-agent.desktop` |
| **用户数据** | `APP_DATA_DIR` 或 `~/.local/share/loop-agent` | SQLite、模型档案、记忆、`transcript.jsonl`、spill。**不是** cwd |
| **工作区** | 用户选的文件夹 | coding 沙箱。没绑定则工具没有根 |

`loop uninstall` 只删安装目录和入口，不删用户数据和工作区。开发时 `backend/.env` 的 `APP_DATA_DIR=./data` 指向仓库狗粮库；`loop shell` **不读** `backend/.env`，端口 8765，避开开发用的 8000 / 5173。

---

## 3. 逻辑分层（箭头只向上）

物理包名仍是 `agent_window`。逻辑层如下。

```text
loop-window     React · FastAPI · SQLite · CLI · 桌面壳
      ↑
loop-coding     fs / shell / edit / patch / skills / 记忆 / 压缩 / 检索 / 落盘
      ↑
loop-agent-core LoopConfig · AgentLoop · Session Tree · Goal/Preset 钩子
      ↑
loop-ai         Model Registry · OpenAI 兼容 Client · 流式 · 错误归一
```

| 层 | 今日落点 | 一句话 |
|----|----------|--------|
| loop-ai | `services/provider.py`, `model_registry.py` | 多档案、按会话选网关 |
| loop-agent-core | `core/`, `agent/loop.py`, `goal.py`, `checkpoint.py` | 环、树、钩子；**不** import FastAPI / SQLAlchemy |
| loop-coding | `tools/*`, `services/compress.py`, `patches.py`, `memory.py` | 做事；审批不写在工具内部 |
| loop-window | `api/`, `models.py`, `cli/`, `src/` | HTTP/SSE、持久化、UI |

禁止：core / ai import `api` 或 `models`。允许 coding / core 使用 ai 的原子类型。功能可以厚，厚在 coding / window 和钩子，不厚在 `loop.py`。

---

## 4. 会话树（历史长什么样）

消息不是「按 sequence 一条直线进模型」。每条有 `parent_id`，会话有 `leaf_id`。

- **认父不认子。** 回退 / regenerate = 移动 leaf，旧枝不删。
- **`build_path_from_session`：** leaf → root 再反转，得到当前进模型的路径。
- **`view=all`：** 列出全部行（含被折、被弃 sibling），给回放。
- **`view=active`：** 只走 leaf 路径。
- **`entry_type=compaction_summary`：** 树上的视图节点。`convert_to_llm` 把它变成带 `【对话压缩摘要】` 的 user，模型看不到内部 role 名。

regenerate：旧 assistant 留着，新 sibling 挂在同一 user 下，leaf 指向新助手。C7（对弃枝做 LCA 五节摘要）未做。

---

## 5. Agent 环（心脏）

入口：`run_agent_loop`（`agent/loop.py`）。概念上：

```text
agent_start
  for turn in max_tool_iters:
      抽 steering（插队 user）
      turn_start
      transform_context(working)          # 进模型前塑形
      chat_complete(working, tools)
      若无 tool_calls → 终态 token / done
      否则按序跑完这一批工具（先凑齐 tool 对）
      after_tool_batch                    # Goal/探索，不在这里压（C6）
      turn_end
  agent_end
```

停止看**有没有 tool call**，不看模型「说做完了」。声称写盘 / 测试通过但本轮无 gate 事件时，环会挂未验证警告。

### 5.1 LoopConfig 钩子

| 钩子 | 做什么 |
|------|--------|
| `convert_to_llm` | `AgentMessage` → OpenAI dict；摘要变 user |
| `transform_context` | 默认 = compress + Goal pin（services 安装） |
| `before_tool_call` | Preset：allow / wait / block |
| `after_tool_call` / `after_tool_batch` | 观察、Goal 检查点、探索收敛 |
| `on_turn_start` | Goal ON 时注入目标 |
| `get_steering_messages` | 用户中途 `POST .../steer` |
| `get_follow_up_messages` | 字段在，无人值守外环未接 |

Goal OFF 时 Goal 相关钩子被清空，loop 里没有散落的 `if goal`。

### 5.2 一轮发送在 window 里怎么走

1. `build_path_from_session` 取 leaf 路径。  
2. 拼 system（Skills catalog、工作区提示、`search_session` 一句）。  
3. 冻结 USER.md / MEMORY.md 快照可注入。  
4. `install_context_transform` + `apply_transform_context`。  
5. SSE：`TurnTraceWriter` 占位 assistant，增量写 trace，token 攒内容。  
6. 工具经 Preset；YOLO 直接执行，Trusted/Strict 出审批卡。  
7. `finalize` 或 `finalize_interrupted` 落库并追加 JSONL。

---

## 6. 压缩漏斗（C0–C5）

目标：跨轮交接达到「Cursor / Pi / Codex 本地压」同一量级，而不是把 `loop.py` 焊厚。

```text
全文永不丢（JSONL）
    → 进模型的路径可压且压完上树
        → durable（system / 记忆 / Skills）与对话分桶
            → 模型用 search_session 拉回原文
```

### 6.1 算法（coding，不在 loop）

`compress_messages_if_needed`：

- 阈值：`context_limit - reserve`（reserve 默认 1024）。  
- `find_cut_index`：从尾累加 token，只切在 user/assistant。  
- 六节：Goal / Constraints / Progress / Key Decisions / Next Steps / Critical Context。handoff 前缀说明这是交接不是复述。  
- LLM 失败 → extractive；`coerce_six_sections` 挡 Goal 回声。  
- 被折 user：近→远前缀，默认 8K，溢出即停。  
- `tail_trim` 不算可上树摘要。  
- `force` + `focus`：手动 compact。

### 6.2 上树

`persist_compaction_on_tree`：摘要 `parent_id` = 被折第一段原来的父；留下的 user 再挂上去；第一条 keep_recent 改挂到链尾。`update_leaf=False`。relink 失败回滚，不留半条。

环内 working 比树长时：`persist_compaction_from_tree` 在**当前树上**重算切点，摘要正文仍用刚压的那份。

### 6.3 落盘与检索

- `transcript.jsonl`：只追加；密钥打码；中断轮次也写 assistant。  
- `turns/`：过大工具结果 spill。  
- `search_session`：只搜这两处；摘录有条数和总字数帽；不搜 SQLite、其它会话、工作区、`.env`。

### 6.4 开关

| 项 | 现状 |
|----|------|
| `auto_compress` | 默认 **关**。开了才在超限时自动压 |
| 手动 compact | ⋮ 或 `POST .../compact` |
| 占用 | `GET .../context`，输入区百分比 |

---

## 7. 工具、门控、记忆、Skills

**工具**经 registry。写盘走 `propose_edit` / `propose_delete` / `propose_shell`，等 Apply；模型不得用文字声称已写入。

**Preset**

| | 写盘 / shell / memory |
|--|------------------------|
| YOLO | 直接执行（审计） |
| Trusted | 写要确认，读自动 |
| Strict | 全门控 + hunk |

**记忆：** USER.md / MEMORY.md 有硬上限；跨会话；每轮用冻结快照，不把整份记忆推进压缩对话桶。

**Skills：** system 只给 catalog，按需再读正文（拉模式）。

---

## 8. 窗口、CLI、桌面

**开发**

```bash
# 后端 8000
cd backend && PYTHONPATH=src .venv/bin/python -m uvicorn agent_window.main:app --port 8000
# 前端 5173
npm run dev -- --host 0.0.0.0 --port 5173
```

**安装后**

```bash
loop install          # 写入 ~/.local/lib/loop-agent
loop shell            # 开窗，后端 8765
loop ask|status|approve|reject|run --wait
loop uninstall        # 只删程序
```

首次无工作区：向导先填模型（Base URL / API Key / Model ID），再选或新建文件夹。新建只建子文件夹，点「使用此文件夹」才绑定。

前端无自动化测试：UI 改动 `npx tsc -b` + 手点。后端：`PYTHONPATH=src python -m pytest tests/ -q`。

---

## 9. 主要 HTTP

| | |
|--|--|
| `GET /health` | 探活 |
| `GET/POST /api/sessions` | 会话 |
| `GET /api/sessions/{id}/messages?view=all\|active` | 消息 |
| `POST /api/sessions/{id}/messages` | SSE 一轮 |
| `POST /api/sessions/{id}/regenerate` | 分支再生 |
| `POST /api/sessions/{id}/cancel` · `/steer` | 停 / 插队 |
| `POST /api/sessions/{id}/compact` | 手动压，可选 `focus` |
| `GET /api/sessions/{id}/context` | 占用 |
| `GET/PUT /api/settings` | 含 `auto_compress`、`context_limit`、Preset |
| `/api/model-profiles` | 多档案 |

---

## 10. 测试纪律（改环时必守）

- 改后端逻辑：`backend/tests/test_*.py`，断言「有/没有什么」，不断言内部变量。  
- 修 bug：先写失败复现 → 再修 → 留下回归。  
- 模型「会不会调工具」不可测，必须写手测步骤。  
- 分层：`tests/test_layer_boundaries.py`。

---

## 11. 已知边界

- 前端无 E2E。  
- CRLF diff、文件末无换行、并发 `propose_edit` 同一文件：未覆盖。  
- C6 / C7 未做。  
- 进程被杀时 JSONL 可能少最后一条 assistant。  
- 占用是 `chars/4` 估算，不是网关账单。  
- 手动 compact 的 focus 目前主要走 API。

---

## 12. 读代码的顺序

1. `docs/architecture-charter.md` §0–§1  
2. `core/loop_config.py` · `core/session_tree.py`  
3. `agent/loop.py` 里 `_run_one_turn`  
4. `services/context_transform.py` → `compress.py` → `compaction_persist.py`  
5. `services/session_transcript.py` → `session_search.py`  
6. `api/routes.py` 发送 / compact  
7. `src/App.tsx` · `ChatInput.tsx`  

改行为时同步 `CHANGELOG.md` `[Unreleased]` 和（若动 A0–A4 / Goal / 压缩漏斗）`foundation-status.md`。
