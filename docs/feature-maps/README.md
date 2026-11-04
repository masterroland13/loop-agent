# Loop Agent 功能地图

> **地位：** L3 对照地图。把现有能力指到真实路径，方便改代码前先找到落点。  
> **不是**架构真源，**不是** Living 进度，**不是**施工计划。  
> **冲突序：** [`architecture-charter.md`](../architecture-charter.md) > [`agent-window-roadmap.md`](../agent-window-roadmap.md) > [`foundation-status.md`](../foundation-status.md) > 本目录。  
> 产品名只称 **Loop Agent**。物理包名仍是 `agent_window`。逻辑层箭头只向上：`loop-ai` → `loop-agent-core` → `loop-coding` → `loop-window`。

本稿按依赖从下往上读：先三个运行时目录，再配置与钩子，再 Agent 环，再编码工具，再 C0–C5 漏斗，最后 CLI 与桌面壳。

## 范围

| 地图 | 覆盖 |
|------|------|
| [`runtime-dirs.md`](runtime-dirs.md) | 安装目录、用户数据目录、工作区，以及与它们正交的 CLI 配置目录 |
| [`config-hooks.md`](config-hooks.md) | `LoopConfig`、Preset、Goal 钩子、`agent_settings.json` |
| [`agent-core.md`](agent-core.md) | 会话树、`run_agent_loop`、一轮发送 |
| [`coding-tools.md`](coding-tools.md) | registry 工具、沙箱、shell 白名单、记忆、Skills |
| [`context-funnel.md`](context-funnel.md) | 跨轮交接 C0–C5：JSONL、上树、留 user、`transform_context`、`search_session`、手动 compact / 占用条 |
| [`cli.md`](cli.md) | `loop` 子命令与对应 HTTP |
| [`shell.md`](shell.md) | `loop install` / `loop shell` / `loop uninstall` 与 WebKitGTK 窗口 |

## 本目录不写的东西

- **C6**（工具 batch 中途再压）和 **C7**（对弃枝做摘要）没有实现，这里不展开方案。
- **MCP client** 没有实现，这里不展开接入步骤。
- `auto_compress` 默认仍是关。地图只记录这个默认，不把它改成开。
- Goal 默认关，Preset 默认 YOLO。门控是策略，不是产品人格。

## 读代码时先认的入口

| 要找什么 | 先打开 |
|----------|--------|
| 三目录默认路径 | `backend/src/agent_window/config.py` 的 `default_user_data_dir`；`backend/src/agent_window/host/session.py` 的 `default_install_dir` |
| 环 | `backend/src/agent_window/agent/loop.py` 的 `run_agent_loop` / `_run_one_turn` |
| 钩子装配 | `backend/src/agent_window/core/loop_config.py` |
| 压缩算法 | `backend/src/agent_window/services/compress.py` |
| 上树 | `backend/src/agent_window/services/compaction_persist.py` |
| 全文落盘 | `backend/src/agent_window/services/session_transcript.py` |
| 检索 | `backend/src/agent_window/services/session_search.py` |
| HTTP | `backend/src/agent_window/api/routes.py` |
| CLI | `backend/src/agent_window/cli/main.py` |
| 桌面宿主 | `backend/src/agent_window/host/session.py`、`shell/loop-window.c` |

分层边界的回归测试是 `backend/tests/test_layer_boundaries.py`。更完整的叙述见 [`docs/design/loop-agent-manual.md`](../design/loop-agent-manual.md)。
