[English](README.md) | **简体中文**

# Loop Agent

**可以拆开看的本地编码 Agent。**

Loop Agent 是窗口、命令行，以及可选的桌面壳，包着一个很小的 Agent 运行时。你给它一个 OpenAI 兼容的模型，再绑一个工作区文件夹。环本身只做工具循环。Goal 模式、审批松紧和压缩都挂在周围的钩子上。会话变长时，运行时把六节交接写上会话树，留下用户原话，并把全文留在磁盘上，摘要不够时用 `search_session` 找回。

这份仓库是单用户的本地程序：React、FastAPI、SQLite，以及面向 Linux / WSL 的 WebKitGTK 壳。架构阶段 A0–A4 和上下文切片 C0–C5 已经在树里。工具批完成后再压（C6）和 regenerate 时给弃枝写摘要（C7）按计划后做。`auto_compress` 默认关闭。

---

## 为什么长这样

提示词、diff、记忆和 HTTP 栈放在分层和钩子里。测试守住 import 只朝一个方向。

- **Pi 式分层。** `loop-ai` → `loop-agent-core` → `loop-coding` → `loop-window`。依赖只向上。core 不引用 FastAPI 和 SQLAlchemy。Python 包名仍是 `agent_window`。
- **会话树。** 每条消息有 `parent_id`，会话有 `leaf_id`。regenerate 在同一条 user 下增加 sibling，并把 leaf 移过去。弃掉的回合留在 SQLite。压缩是模型所见路径上的一个节点。
- **漏斗。** 读过 Codex、Cursor、Claude Code 和 Pi 之后收成这条：JSONL 只追加 → leaf 路径可以压，且摘要会落在树上 → 耐久上下文（system、记忆、Skills）单独成桶 → `search_session` 把原文读回来。
- **安静的默认。** Goal 模式关闭。Preset 默认是 YOLO：在可信的本地树上直接写，并留下审计。Trusted 和 Strict 留给需要确认的回合。

架构真源：[`docs/architecture-charter.md`](docs/architecture-charter.md)。

---

## 功能

| 表面 | 你得到什么 |
|------|------------|
| **窗口** | 工作区与会话、流式对话、审批卡、Files 树、设置、估算的上下文占用 |
| **环** | 工具调用循环、写盘声明核对、观察瘦身。中途消息走 `POST /api/sessions/{id}/steer`。窗口里没有对应的插入控件 |
| **Goal** | 可选的质量环：钉住目标、检查点、探索收敛。默认关闭 |
| **Preset** | YOLO / Trusted / Strict。策略在 `before_tool_call`，不写进工具实现 |
| **模型** | 多份 OpenAI 兼容档案，按会话绑定 |
| **记忆** | 有上限的 `USER.md` / `MEMORY.md`，以冻结快照注入 |
| **Skills** | 系统提示里只有目录；正文按需加载 |
| **上下文** | 六节交接、保留的 user 原话、`search_session`、可带 `focus` 的手动 compact |
| **桌面** | WebKitGTK 上的 `loop install` / `loop shell`。卸载只删程序，留下你的数据 |
| **CLI** | `loop ask` · `status` · `approve` · `reject` · `run --wait` |

---

## 架构

```text
loop-window     React · FastAPI · SQLite · CLI · WebKitGTK
      ↑
loop-coding     files · shell · patches · skills · memory · compress · search
      ↑
loop-agent-core LoopConfig · AgentLoop · session tree · Goal / Preset hooks
      ↑
loop-ai         model registry · OpenAI-compatible client · streaming
```

箭头是 import 方向：上一层可以使用下一层。运行时目录是另一条轴。环不解析安装路径。

| 目录 | 默认位置 | 放什么 | 不放什么 |
|------|----------|--------|----------|
| **安装目录** | `~/.local/lib/loop-agent` | 构建好的界面、`loop-window` 二进制、后端 venv。启动器 `~/.local/bin/loop`。桌面项 `~/.local/share/applications/loop-agent.desktop` | 会话、git 检出、工作区 |
| **用户数据** | `~/.local/share/loop-agent`，或 `APP_DATA_DIR` | SQLite、模型档案、记忆、`transcript.jsonl`、溢出的工具输出 | 程序二进制和工作区文件 |
| **工作区** | 你绑定的文件夹 | 文件和 shell 工具的沙箱 | 安装树。未绑定的会话没有根，工具读不到安装目录 |

`loop uninstall` 删除安装目录、`loop` 启动器和桌面项。用户数据和工作区留下。`~/.config/loop-agent` 里的 CLI 设置只服务命令行，不并进用户数据。

开发时在 `backend/.env` 写 `APP_DATA_DIR=./data`，数据库留在 `backend/data`。`loop shell` 不读这个文件。它用安装目录里的后端在 **8765** 上托管界面，开发用的 8000 和 5173 保持不动。

---

## 快速开始

### 开发

Python ≥ 3.10。本仓库和 `loop install` 使用的解释器是 `backend/.venv`。

```bash
cd backend
PYTHONPATH=src .venv/bin/python -m uvicorn agent_window.main:app --host 0.0.0.0 --port 8000
```

另一个终端，在仓库根目录：

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

打开 [http://localhost:5173/](http://localhost:5173/)。Vite 把 `/api` 和 `/health` 代理到 8000。

把 [`backend/.env.example`](backend/.env.example) 复制为 `backend/.env`。保留 `APP_DATA_DIR=./data`，会话就留在检出目录里。填上 OpenAI 兼容的 Base URL、API Key 和模型 id。不设 `APP_DATA_DIR` 时，数据进 `~/.local/share/loop-agent`，并且不绑定工作区。

### 安装（Linux / WSL）

安装必须从这份 git 检出运行。已经放在 `~/.local` 下的 `loop` 会拒绝再次安装。命令需要 `dist/index.html`、`backend/.venv`，以及 Linux 可执行文件 `shell/loop-window`。二进制缺失或比 `shell/loop-window.c` 旧时，安装会用 `gcc` 和 `pkg-config`（`webkit2gtk-4.1`）编译它。

```bash
npm run build
cd backend
PYTHONPATH=src .venv/bin/python -m agent_window.cli install
```

这会写入 `~/.local/lib/loop-agent`、`~/.local/bin/loop` 和桌面项。把 `~/.local/bin` 放进 `PATH` 之后：

```bash
loop shell       # 开窗；后端在 8765，不是 8000
loop uninstall   # 只删程序文件
```

8765 已被占用时，`loop shell` 会停下来，不去接另一份后端。关掉窗口会停掉它拉起的后端。

第一次还没有工作区：先填一张模型卡（Base URL、API Key、模型 id），再选一个文件夹，或在当前浏览的目录下新建。新建只建文件夹，确认之后才绑定。

`loop ask`、`loop status`、`loop approve`、`loop reject`、`loop run --wait` 默认访问 `http://127.0.0.1:8000`，除非设置了 `AGENT_BASE_URL`，或在 `~/.config/loop-agent/config.json` 里写了 `base_url`。桌面壳才是你要连的后端时，把地址指到 `http://127.0.0.1:8765`。

### 测试

在 `backend/` 下：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

在仓库根目录：

```bash
npx tsc -b
```

界面没有自动化测试。后端测试断言接口返回什么。路径里有空格时请加引号。

---

## 上下文漏斗（已落地）

C0–C5 已在树里，并对照方案审查过。交接是六节：Goal、Constraints、Progress、Key Decisions、Next Steps、Critical Context。

| 切片 | 行为 |
|------|------|
| **C0** | 用户数据目录下只追加的 `transcript.jsonl`。密钥字段打码。附件只记 id 和文件名 |
| **C1** | 树上的 `compaction_summary` 节点。被折行留在 SQLite 和 JSONL 里；leaf 路径跳过它们 |
| **C2** | 被折的 user 原话按从近到远保留，8K token 帽 |
| **C3** | 每次进模型前走 `transform_context`，包括环内两次工具回合之间 |
| **C4** | `search_session` 只读本会话的 JSONL 和 spill |
| **C5** | `POST /api/sessions/{id}/compact`（可选 `focus`），占用估算来自 `GET /api/sessions/{id}/context` |

C6（一批工具完成后再压）和 C7（regenerate 时给弃枝一份短摘要）有意后做。`auto_compress` 默认仍然**关闭**。把它打开是另一次可撤回的改动。默认关闭时，手动 compact 和占用显示仍然可用。

---

## 文档

| 从这里进入 | |
|------------|--|
| [`docs/architecture-charter.md`](docs/architecture-charter.md) | 架构真源：分层、Goal、Preset、运行时目录 |
| [`docs/design/loop-agent-manual.md`](docs/design/loop-agent-manual.md) | 运维与扩展手册：树、环、漏斗、HTTP |
| [`docs/research/context-loop-c0-c5-review.md`](docs/research/context-loop-c0-c5-review.md) | C0–C5 的调研、施工与审查，含简历表述 |
| [`docs/README.md`](docs/README.md) | `docs/` 其余文档的地图 |

---

## 状态

架构阶段 **A0–A4** 已完成。上下文漏斗 **C0–C5** 已落地并经过审查。进行中的进度：[`docs/foundation-status.md`](docs/foundation-status.md)。变更记录：[`CHANGELOG.md`](CHANGELOG.md)。

---

## 许可证

本仓库没有 `LICENSE` 文件。这里没有授予复制、修改或再分发的许可。在补上许可证之前，把这份检出当作作者的源码树。
