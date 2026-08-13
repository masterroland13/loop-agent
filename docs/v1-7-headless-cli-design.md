# V1-7 无头 CLI / Runtime 设计文档

> 版本：0.1（草案）  
> 范围：后端 API + CLI 入口 + 审批联动  
> 目标：让同一套 Agent Runtime 可被命令行/脚本/CI 调用，Window 仅作为监督面

---

## 1. 背景与目标

### 1.1 为什么做

当前 Hal Agent 只有浏览器 UI 能触发对话。要进入日常工作流，必须保留 CLI 可组合性：

- 工程师可以在终端直接问一个仓库问题
- CI / 自动化脚本可以调用 Agent 执行固定任务
- Window 变成“监督 + 审批”面，而不是唯一入口

### 1.2 核心原则

| 原则 | 说明 |
|------|------|
| **同源后端** | CLI 与 Window 共用 `/api/sessions/{id}/messages`、loop、patches、shells、memories |
| **审批不绕开** | 写文件、跑命令、写记忆仍需用户在前端或 CLI 交互式确认 |
| **无头≠无监督** | CLI 可以发起，但危险操作仍走相同的 gate |
| **产物一致** | 会话、审计、diff、shell 输出全部落在同一 SQLite + 文件产物里 |

---

## 2. 总体架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Web Browser   │     │   CLI / Script  │     │   CI / Cron     │
│   (Window UI)   │     │   agent ask     │     │   python -m ... │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                         │                         │
         │      HTTP/SSE           │      HTTP/SSE           │
         └─────────────────────────┴─────────────────────────┘
                                   │
                         ┌─────────▼─────────┐
                         │  FastAPI Backend  │
                         │  sessions API     │
                         │  patches/shells   │
                         │  agent loop       │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │  Workspace + DB   │
                         │  SQLite / files   │
                         └───────────────────┘
```

---

## 3. 用户故事

### 3.1 故事 A：终端快速提问

```bash
agent ask "这个仓库的入口文件在哪？"
```

期望：
- 创建一个新 session
- 运行 agent loop
- 终端输出模型回复（非流式或流式可选）
- 如果涉及读文件工具，自动执行；如果涉及写文件，进入 pending 状态并提示用户去 Window 审批

### 3.2 故事 B：脚本自动化

```bash
agent run --session "refactor-task" --file task.md --wait
```

期望：
- 在指定 session 里执行 task.md 的内容
- `--wait` 模式下阻塞，等待所有 pending 审批完成后再返回
- 返回最终输出、exit code、是否有未审批项

### 3.3 故事 C：Window 审批 CLI 发起的任务

- CLI 发起“重构 utils.py”
- 用户在前端看到新的 Diff 卡片
- 用户 Apply/Reject 后，CLI 收到结果并继续/结束

---

## 4. API 设计

### 4.1 新增端点

#### `POST /api/sessions/{session_id}/run`

同步运行一轮用户消息。支持流式或非流式。

请求体：
```json
{
  "content": "创建一个文件 hello.txt，内容写 world",
  "model": "kimi-for-coding",
  "stream": false,
  "timeout_sec": 300
}
```

响应（非流式）：
```json
{
  "session_id": "...",
  "turn_id": "...",
  "status": "awaiting_approval",
  "assistant_content": "我提议创建文件 hello.txt，请审批。",
  "pending": {
    "patches": [{"id": "...", "path": "hello.txt", "status": "pending"}],
    "shells": [],
    "memories": []
  },
  "next_action": "Open the web UI or call PATCH /api/workspace/patches/{id}/apply"
}
```

#### `POST /api/sessions/{session_id}/run-stream`

SSE 流式，事件格式与现有 `/api/sessions/{id}/messages` 的 SSE 一致。

#### `GET /api/sessions/{session_id}/state`

轮询用。返回当前 session 的 pending 列表、最后一条 assistant 消息、是否仍在运行。

```json
{
  "session_id": "...",
  "is_running": false,
  "awaiting_approval": true,
  "patches": [...],
  "shells": [...],
  "memories": [...],
  "last_message": {"role": "assistant", "content": "..."}
}
```

### 4.2 复用现有端点

| 能力 | 端点 | 说明 |
|------|------|------|
| 创建 session | `POST /api/sessions` | 已存在 |
| 列出会话 | `GET /api/sessions` | 已存在 |
| 审批 patch | `POST /api/workspace/patches/{id}/apply` | 已存在 |
| 审批 shell | `POST /api/workspace/shells/{id}/apply` | 已存在 |
| 审批 memory | `POST /api/memory/proposals/{id}/apply` | 已存在 |
| 审计日志 | `GET /api/audit` | 已存在 |

---

## 5. CLI 设计

### 5.1 命令结构

```
hal-agent-cli
├── ask       快速提问，可自动创建 session
├── run       在指定 session 运行一条消息
├── sessions  列出/创建会话
├── status    查看 session 当前 pending 状态
└── approve   命令行审批 patch/shell/memory（交互式/脚本式）
```

### 5.2 命令详情

#### `hal ask <message>`

```bash
# 创建新 session 并发问
hal ask "解释这个项目"

# 指定模型
hal ask --model kimi-k3 "解释这个项目"

# 指定已有 session
hal ask --session-id <id> "继续改"

# 流式输出
hal ask --stream "解释这个项目"
```

#### `hal run`

```bash
# 从文件读取任务
hal run --session-id <id> --file task.md

# 等待所有审批完成
hal run --session-id <id> --file task.md --wait --timeout 600

# 直接传内容
hal run --session-id <id> --content "运行 pytest"
```

#### `hal status`

```bash
hal status --session-id <id>
```

输出：
```
Session: refactor-task (id: ...)
Running: false
Pending approval:
  [patch] hello.txt  (status: pending)
```

#### `hal approve`

```bash
# 交互式列出并审批
hal approve --session-id <id>

# 脚本式直接审批
hal approve --patch-id <id>
hal approve --shell-id <id>
hal approve --memory-id <id>

# 拒绝
hal reject --patch-id <id>
```

---

## 6. 关键流程

### 6.1 创建 session + 运行一轮

```python
# cli/commands/ask.py
def ask(message, model=None, stream=False):
    session = api.create_session(title=message[:40])
    if stream:
        for event in api.run_stream(session.id, message, model=model):
            handle_event(event)
    else:
        result = api.run_sync(session.id, message, model=model)
        print(result.assistant_content)
        if result.awaiting_approval:
            print("等待审批，打开 Window 或运行：")
            for p in result.pending.patches:
                print(f"  hal approve --patch-id {p.id}")
```

### 6.2 审批等待循环

```python
# cli/commands/run.py
async def run_and_wait(session_id, message, timeout=300):
    api.send_message(session_id, message)
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = api.get_session_state(session_id)
        if not state.is_running and not state.awaiting_approval:
            return state.last_message
        if state.awaiting_approval and auto_approve:
            for p in state.pending.patches:
                api.approve_patch(p.id)
        await asyncio.sleep(1)
    raise TimeoutError("等待审批超时")
```

### 6.3 CLI 与 Window 并发安全

- 后端 `try_begin_turn(session_id)` 已防止同 session 并发运行
- CLI 发起后，Window 侧会看到 409 SESSION_BUSY，直到 CLI 这轮结束
- pending patches/shells/memories 是全局状态，Window 和 CLI 都能审批

---

## 7. 数据模型

复用现有模型，无需新增核心表。仅在审计 payload 里增加 `source: cli|web` 字段。

新增可选表 `session_metadata`（如需要）：

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | FK | 关联 sessions |
| source | str | `cli`、`web` |
| cli_command | str | 发起时的命令快照 |

建议第一期不做新增表，用 `audit_events` 记录 source 即可。

---

## 8. 实现阶段

### Phase 1：API 非流式 run（1 天内）

- 新增 `POST /api/sessions/{id}/run` 同步端点
- 复用现有 `run_agent_loop` 和 SSE 事件处理逻辑
- 返回 assistant_content + pending 状态
- 输出设计文档 + 端点单测

### Phase 2：CLI ask / status / approve（1 天内）

- 新增 `agent_window/cli/__init__.py`
- `hal ask`、`hal status`、`hal approve`
- 配置文件 `~/.config/hal-agent/config.json` 保存 `base_url`

### Phase 3：流式与等待模式（1-2 天）

- `POST /api/sessions/{id}/run-stream`
- `agent run --wait`
- 信号/中断处理（Ctrl+C 取消当前 turn）

### Phase 4：CI / 脚本增强（可选）

- `--json` 输出
- `--exit-code` 策略
- `--auto-approve` 危险开关（默认关闭）

---

## 9. 安全与边界

| 风险 | 处理 |
|------|------|
| CLI 绕过审批 | 所有写/命令/记忆仍走 patches/shells/memories gate；CLI 只提供交互式/显式 `approve` |
| 并发冲突 | 后端 session turn lock 已覆盖 |
| 脚本长期 hang | `--timeout` 必填或默认值；`--wait` 明确声明 |
| 凭证泄露 | CLI 配置文件权限 600；支持 `AGENT_API_KEY` 环境变量 |

---

## 10. 待决策事项

1. **是否默认自动审批只读工具？**  
   读文件/搜索/list_dir 本身无风险，应自动执行；当前后端已经如此。

2. **CLI 输出语言？**  
   跟随模型返回；状态提示用中文，便于和国内团队对齐。

3. **是否支持 stdin 管道？**  
   Phase 3 支持 `echo "..." | hal ask -`。  

4. **CLI 与后端是否同进程？**  
   否。CLI 是独立 Python 进程，通过 HTTP 调用后端。这样后端可独立部署。

---

## 11. 参考

- 现有 SSE 端点：`/api/sessions/{id}/messages`（`src/api/agent.ts`）
- Agent loop：`backend/src/agent_window/agent/loop.py`
- Patches / shells / memories 服务：`backend/src/agent_window/services/`
- 审计：`backend/src/agent_window/services/audit.py`
