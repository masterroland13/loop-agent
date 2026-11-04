# 进程内 Seat 与进程外 CAO

> L3 调研，过夜对照。**不是施工方案，不改产品代码。**  
> 不改宪章、路线图、`foundation-status.md`。进度仍以那三份为准；本文与它们冲突时以它们为准。  
> 日期：2026-11-04。对象：Loop Agent 当前单进程环（A0–A4 已落地）。

## 问题

路线图把 **多 Agent** 和 **MCP** 都放在暂缓（[`agent-window-roadmap.md`](../../agent-window-roadmap.md) §4.6；B\* 在 A0–A4 之上才谈）。以后若要让一个宿主环分出帮手，有两条形状：

| 名字 | 一句话 |
|------|--------|
| **Seat（席位）** | 帮手是**同一次后端进程**里的嵌套 `run_agent_loop`。宿主用函数调用把任务交进去，拿回一份交接。 |
| **CAO（Coding Agent Orchestrator，编码代理编排器）** | 帮手是**另一个进程**里的完整 Loop Agent 运行时。编排器在进程外拆任务、拉起 worker、收回交接。worker 若在另一台机器上，编排器就是云端的，形状相同。 |

两条都不把 MCP 当通信层。MCP 解决的是「模型调用进程外的工具服务器」；Seat / CAO 解决的是「谁来跑另一段代理环」。混在一起会把已暂缓的协议塞进另一项暂缓能力。

## 名词

**Seat。** 一次有界的嵌套环：自己的消息列表、一段任务说明、一份工具白名单、一份轮次预算、一份 `LoopConfig` 副本。它和宿主共享工作区沙箱、用户数据目录、Preset 门、EventSink、取消信号。它不是第二个产品，也不是第二个安装目录。

**CAO。** 编排器不在 `run_agent_loop` 里面。它提交一份任务单，worker 用自己的进程跑完整的环，再交回交接。本机子进程和远端机器是同一种边界：没有共享的 Python 对象，没有共享的那一次 asyncio 循环。云只是 worker 的落点，不另起缩写。

**MCP。** Model Context Protocol：工具名单发现、JSON-RPC、stdio / SSE、resources。它是工具服务器协议。宪章 M01 把 MCP 放在默认不做的减法里；路线图 §4.6 与 `foundation-status.md` 的 backlog 仍写暂缓。本文不设计 MCP server，也不把 `propose_edit` / `propose_shell` 再暴露成远程工具。

## 本仓已经有的接缝

这些是对照时用得到的事实，不是待改清单。

| 事实 | 落点 | 对 Seat / CAO 的含义 |
|------|------|----------------------|
| 四层，箭头向上 | 宪章 §1；[`layer-boundaries.md`](../../layer-boundaries.md) | 嵌套环留在 core。coding 里的工具可以调用 core。core 不 import `api`。策略不写进 `routes.py`。 |
| 一次用户发送 = 一次 `run_agent_loop` | `backend/src/agent_window/agent/loop.py` | Seat 是这次调用里面的另一次调用，仍走同一函数。CAO 是另一次进程里的另一次调用。 |
| `LoopConfig` 已是策略插口 | `core/loop_config.py`：`before_tool_call` / `after_tool_call` / `transform_context` / Goal 开关 | 席位差异（白名单、Goal OFF、预算到了就停）走 Config 副本，不走第二套 `loop.py`。 |
| 工具注册表是进程单例 | `tools/registry.py` 的 `registry` | 席位不该 new 一个平行注册表。白名单是策略，不是第二份工具实现。 |
| 发给模型的工具列表会滤 `disabled_tools` | `run_agent_loop` 读的是**全局** agent settings | 这个开关是宿主设置。用它给席位藏工具，会连宿主一起改。席位白名单必须是这一次调用自己的。 |
| 分发不看那份过滤列表 | `agent/tool_dispatch.py` 的 `handle_function_call`：注册表里有这个名字就执行 | 只从 schema 里拿掉工具名，模型仍可能喊出 `propose_shell` 并执行成功。白名单要挡在执行前（`before_tool_call` 返回 block，或等价的管线拒绝）。 |
| Preset 已经在管线里 | YOLO / Trusted / Strict = `before_tool_call` | 席位里的写盘和 shell 仍走同一道门、同一个 `session_id`。P3 已按会话隔离开门；席位不另开一套审批 UI。 |
| 三目录 | 宪章 §1.4 | 安装目录只有一份程序。用户数据目录是这一份后端的。工作区是 coding 沙箱。Seat 不新增目录种类。CAO 若共写同一工作区，锁和门的归属宪章没有定义。 |
| CLI 已经是另一个进程 | [`v1-7-headless-cli-design.md`](../../design/v1-7-headless-cli-design.md)：CLI 经 HTTP 调后端 | 进程外的「客户端」已经有了。CAO 若再造一个编排守护进程，就是第三条进程故事。 |
| 事件有嵌套，管道 A 不等待 | EventSink：`agent_start` / `turn_*` / `tool_*` | 席位事件要能挂在宿主那一次 tool call 下面。管道 B（改写环）仍只有 Config 钩子，不另做扩展总线。 |
| 会话树是用户 leaf | `parent_id` / `leaf_id`；压缩上树 | 席位的内部消息不是用户 leaf。宿主 leaf 上只应留下那次工具的交接，否则压缩和切支会把帮手的草稿当成用户对话。 |
| 并发写同一文件未覆盖 | `foundation-status.md` §6 | 两个写席位同时 `propose_edit` 同一文件，今天没有行为保证。 |
| 密钥在能调模型的进程里就能被用 | [`api-key-storage.md`](../api-key-storage.md) | 多一个 worker 进程，就多一块密钥驻留面。 |

今天的工具面（注册名）：`list_dir`、`read_file`、`grep`、`search_session`、`read_attachment`、`propose_edit`、`propose_delete`、`propose_shell`、`propose_memory`、`ping`、`get_weather`。后两个是演示，席位白名单不包含它们。

## 对照

| | 进程内 Seat | CAO |
|--|-------------|-----|
| 跑在哪 | 宿主这次 `run_agent_loop` 所在的 uvicorn 进程 | 另一个 Python 进程，或另一台机器上的一份 Loop 后端 |
| 怎么把任务送进去 | 函数调用 | 任务单（HTTP、队列或磁盘上的一份说明） |
| 怎么拿结果 | 工具结果里的交接结构 | worker 退出或回调时的同一份交接 |
| 工具实现 | 同一份 `ToolSpec` 处理器 | worker 进程里的另一份同一套代码 |
| 工作区 | 宿主已绑定的那一个根 | 同一根（要自己加锁）或另一份检出 |
| 审批 | 宿主会话的 Preset 与 `session_id` | 要决定门画在哪一个窗口；CLI 今天没有 Diff 面板 |
| 取消 | 传播宿主的 `cancel_event` | 要有跨进程的取消，失败时 worker 可能继续写盘 |
| 轨迹 | 同一条 EventSink，带 `seat_id` 与父 tool call | 日志拆在两个进程；用户数据目录的会话库按单后端使用 |
| 上下文 | 席位有自己的消息列表；宿主只看见交接 | worker 有自己的会话；宿主只看见交接 |
| 冷启动 | 无 | 有：解释器、设置、工作区、模型档案 |
| 适合 | 一次对话里分出读、找、草拟，宿主仍是唯一对用户说话的环 | 任务必须比 UI 进程活得久，或必须在别的工作区 / 别的机器上跑 |
| MCP | 用不上 | 看起来像工具服务器，因而最容易被误接上；仍然用不上 |

## 进程内 Seat 的形状

宿主环在一次工具调用里同步等待席位结束。席位对模型来说就是一个工具结果，不是第二个聊天室。

示意（不是接口，不要按此实现）：

```text
用户 leaf 上的宿主环
  tool_call ask_seat { role, task, allow }
    嵌套 run_agent_loop
      自己的 messages
      LoopConfig 副本（Goal OFF，before_tool_call 强制白名单）
      轮次与取消从宿主传入
    返回 handoff
  宿主只把 handoff 放进 tool 结果，继续自己的环
```

交接里要有的行为，而不是一篇「我做完了」：

| 字段 | 行为 |
|------|------|
| `status` | `done` / `blocked` / `cancelled` / `budget`。预算用尽是 `budget`，不是成功。 |
| `facts` | 短句。没有工具结果支撑的完成声明，宿主应当成未验证。 |
| `paths` | 读过或改过的路径。空就空着。 |
| `blockers` | 门被拒、命令失败、找不到文件。 |
| `seat_id` | 这一次嵌套的标识，给事件和审计，不进用户 leaf。 |

约束：

1. **深度 1。** 席位不再打开席位。宿主是唯一呼叫者。
2. **默认 Goal OFF。** 宿主的目标写成任务字符串交进去。不把 `goal_mode=True` 继承进嵌套环，避免检查点和探索收敛在帮手里再跑一遍。
3. **白名单在执行前生效。** 读席位：`list_dir`、`read_file`、`grep`、`search_session`、`read_attachment`。写席位再加 `propose_edit`、`propose_delete`。shell 席位再加 `propose_shell`。`propose_memory` 留在宿主，避免帮手改 USER.md。`ping` / `get_weather` 不进任何席位。
4. **写与 shell 仍走宿主 Preset。** YOLO 直通、Trusted 等门、Strict 全门控，跟宿主这次会话同一 `session_id`。席位不发明第四档。
5. **模型档案用会话已有的那份。** 不给席位另开密钥存放。
6. **内部消息不挂上用户 leaf。** 若以后要留底，放在用户数据目录里该会话之下，与 transcript / spill 同一规矩：不写工作区，不写安装目录，密钥打码。本文不规定文件名。
7. **事件挂在父 tool call 上。** `agent_start` 带 `seat_id`。管道 A 只观察。UI 没有席位之前，这些事件可以只进审计。
8. **取消一起停。** 用户停宿主，席位的 shell 与环也停。席位不能在宿主已停之后继续 `propose_edit`。
9. **同一文件的写席位同时只跑一个。** 在并发 `propose_edit` 有测试之前，第二个写请求应直接 `blocked`，而不是靠碰运气。

分层落点（仍是概念）：

| 层 | 席位相关的职责 |
|----|----------------|
| loop-agent-core | 嵌套 `run_agent_loop`；Config 副本；白名单拒绝；预算与取消；交接结构 |
| loop-coding | 一个工具的 `execute`：组任务、调 core、把交接收成工具结果。工具内部不写「必须审批」 |
| loop-window | 若要给人看，只渲染已经发出的嵌套事件和同一会话的门。`routes.py` 里不出现席位策略分支 |
| loop-ai | 无新供应商，无第二套客户端 |

这遵守「功能可以厚，厚在钩子和 coding，不厚在 `loop.py` 单文件」。嵌套调用可以包一层小函数，策略仍从 Config 进去。

## CAO 的形状

编排器持有任务图。每个 worker 是一份完整的 Loop Agent：自己的进程、自己的 `run_agent_loop`、自己看到的工具面。编排器与 worker 之间只有任务单和交接，字段与上一节相同，这样两条路的「做完了什么」可以对照。

worker 的三种落点，边界相同：

| 落点 | 何时才值得 |
|------|------------|
| 本机子进程 | 要崩溃隔离，或 shell 不可信到不能跟 UI 同一进程 |
| 同一用户数据目录上的第二个后端 | 今天没有多写者约定。会话库、门、`session_id` 会撞车。先有明确的库锁设计之前，不要这样部署 |
| 另一台机器 / 另一份检出 | 任务必须离开这台机器，或必须改一份隔离的工作区 |

进程外已经有的入口是 CLI：独立进程，HTTP 调后端（设计文档里的结论）。CAO 若要做，worker 应是现成的无头 `loop run` 一类入口，编排器提交任务并读取交接。再写一个常驻编排守护进程，会和 `loop shell`（拉起/停掉一份后端）、CLI（调这份后端）叠成三种宿主。

CAO 仍然不把 worker 包成 MCP server。worker 是代理环，不是工具名单。编排器不远程调用 `propose_edit`；它只描述任务。写盘发生在 worker 内部，并在那一份运行时里走 Preset。结果以交接和 diff 回来。

审批在 CAO 里没有自然的面板。无头 worker 上的 Trusted / Strict 要么退化成 YOLO，要么把「等待批准」挂回用户正在看的那一个窗口。后者等于又做回进程内的门，只是多了一次进程跳转。

密钥：worker 进程能调模型，就能用到档案里的 key。这跟 [`api-key-storage.md`](../api-key-storage.md) 的边界一致，多进程会放大这块面。云端 worker 还要把 key 带出本机，那是另一项产品决定，不属于这份对照。

## 为什么两条都不走 MCP

MCP 适合的问题：宿主进程里没有这个工具的实现，模型需要发现并调用一个外部服务器（浏览器、第三方 SaaS、另一语言写的 linter）。

Seat 对不上：工具实现已经在进程里，五步管线、slim、Preset、沙箱都包着它们。再用 MCP 转一圈，等于把 `list_dir` 从函数调用改成 JSON-RPC，管线要接两次，真源变成两份。

CAO 对不上：编排器要的是「跑完这段任务，带回交接」，不是「请调用工具 `propose_edit`」。把 worker 的工具面用 MCP 暴露给编排器，编排器就退化成一个远程工具客户端，Preset 和沙箱会在协议两侧各写一遍。

以后若单独做网页或第三方工具，那是路线图 §4.6 里 MCP 自己的决定。它可以在 Seat / CAO 都没有的时候发生，也可以永远不做。它不应当作多 Agent 的前置条件，也不应当作多 Agent 的附带物。

Pi 的减法（宪章 M01）把 MCP、计划模式、子 Agent、审批弹窗都放在默认不做。Loop 已经把审批收成 Preset。子 Agent 若要做，用席位这一小步即可，不必把 MCP 一并打开。

## 取舍

当前产品是：一个用户、一个已绑定工作区、一份后端进程、一份用户数据目录。对这个形状，**进程内 Seat 是多 Agent 的那一格；CAO 先不做。**

理由：

- 嵌套环能复用 `LoopConfig`、管线、EventSink、会话门和沙箱，不新加层。
- 用户仍只面对一个 leaf、一块 Diff、一次取消。
- CAO 解决的是「进程要分开」：UI 死了任务还在、工作区必须隔离、机器不是这一台。这三件事今天都不是已排期的产品目标。真到那一步，优先复用无头 CLI，而不是新编排器。
- 两条路的交接可以长成同一种结构。先做席位，不会把以后的进程外 worker 焊死。

排期仍服从路线图：B\* 多 Agent **禁止**在这条调研之后直接开干。A0–A4 已完成，并不等于多 Agent 自动解禁；解禁要另有产品决定，并另写 `docs/plans/`。本文放在 `research/overnight/`，就是为了避免被当成施工单。

若以后写计划，第一刀只应是：**深度 1 的只读席位**（白名单停在读工具），宿主把交接当工具结果。写席位、shell 席位、CAO、MCP 都还在后面，而且后两者默认仍不开。

## 风险与未决

| 点 | 说明 |
|----|------|
| 单线程事件循环 | 席位在宿主的 tool call 里被 await。shell 或长读会挡住这一轮的后续 token。这是工具调用的既有语义；预算和取消是缓解，不是并行运行时。 |
| 全局注册表 | 藏 schema 挡不住执行。白名单不做在 `before_tool_call`（或管线里同等位置）就会漏。 |
| 全局 `disabled_tools` | 不能当席位开关。 |
| 上下文体积 | 把席位全文追加进宿主消息，会直接打进 C0–C5 的压缩与上树。宿主只收交接。 |
| Goal 继承 | 继承 `goal_mode` 会让嵌套环跑检查点。默认 OFF。 |
| 诚实 | 宿主口头说「席位已改完」而本轮没有门事件，仍应触发未验证警告。席位不绕过这条防线。 |
| 同一文件并发写 | 已知未覆盖。多写席位在有测试前应拒绝并发。 |
| 记忆 | `propose_memory` 放进席位会让帮手改冻结快照的来源。留在宿主。 |
| CAO 与桌面壳 | `loop shell` 已经负责一份后端的生死。第二个后端共写同一 SQLite，行为未定义。 |
| 模型是否肯调用席位 | 不可测。真做时要附人工步骤，与 Skills 按需加载同一类。 |

未决、而且本文不替产品拍板的事：席位工具的名字、交接的 JSON 字段是否进 `ToolSpec`、嵌套事件要不要上 SSE、只读席位的默认轮次预算数字。这些属于将来的 plan，不属于过夜对照。

## 本文不授权

- 不新增工具、不改 `loop.py`、不改 `LoopConfig`、不加依赖。
- 不把本文升格进宪章或路线图。
- 不在 `docs/plans/` 开多 Agent 施工。
- 不引入 MCP server、MCP client，或任何「用 MCP 模拟席位」的桥。
- 不把 CAO 做成守护进程、云端编排器或第二份后端。
