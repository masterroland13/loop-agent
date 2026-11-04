# CLI

无头客户端，打的是和网页同一套 HTTP。实现：`backend/src/agent_window/cli/main.py`，HTTP 封装 `cli/client.py`，配置 `cli/config.py`。`python -m agent_window.cli` 由 `cli/__main__.py` 进入。安装后的命令是 `loop`。

默认基址解析顺序：环境变量 `AGENT_BASE_URL`，然后 `~/.config/loop-agent/config.json` 的 `base_url`，然后 `http://127.0.0.1:8000`。文件缺失时只读旧路径 `~/.config/hal-agent/config.json`。产品名仍是 Loop Agent。`--base-url` 覆盖当次。超时默认 120 秒，来自配置键 `timeout`。

开发时后端在 8000。桌面壳的后端在 8765，CLI 不会自动改去 8765；要对着窗口后端时显式给 `--base-url http://127.0.0.1:8765`。

`install` / `shell` / `uninstall` 不调用 HTTP。其余子命令都走 `RuntimeClient`。

## 子命令

| 命令 | 函数 | HTTP |
|------|------|------|
| `loop health` | `cmd_health` | `GET /health`。`status != ok` 时退出码 1 |
| `loop assets` | `cmd_assets` | `GET /api/assets` |
| `loop sessions [--json]` | `cmd_sessions` | `GET /api/sessions`。表格式：`id`、`updated_at`、`title` |
| `loop workspace [--root PATH \| --clear]` | `cmd_workspace` | `GET` / `PUT` / `DELETE /api/workspace` |
| `loop ask [prompt]` | `cmd_ask` | 创建或复用会话，`POST /api/sessions/{id}/messages`，流式打印回复 |
| `loop run [prompt] [--wait]` | `cmd_run` | 同 ask。`--wait` 在审批未决时阻塞，默认 300 秒，`--wait-timeout` 可改 |
| `loop status [-s ID] [--json]` | `cmd_status` | 待审批 + `GET /api/runtime`。待审批是工作区全局，不是会话私有 |
| `loop approve` | `cmd_approve` | `POST .../apply` |
| `loop reject` | `cmd_reject` | `POST .../reject` |
| `loop install` | `cmd_install` | 无。见 [`shell.md`](shell.md) |
| `loop shell` | `cmd_shell` | 无。见 [`shell.md`](shell.md) |
| `loop uninstall` | `cmd_uninstall` | 无。见 [`runtime-dirs.md`](runtime-dirs.md) |

`ask` / `run` 共用的旗标：

| 旗标 | 作用 |
|------|------|
| `-f/--file` | 把文件内容附在提示后 |
| `-s/--session` | 复用会话；省略则新建 |
| `-m/--model` | 模型别名。缺省可来自配置 `default_model` |
| `-y/--yes` | 自动批准 patch / shell / memory。配置 `auto_approve: true` 时默认打开 |
| `--no-input` | 不提问。没有 `-y` 时审批按拒绝处理 |
| `--meta` | stderr 打 `turn_meta` |
| `-v/--verbose` | stderr 打工具与 diff |
| `--json` | 出错时 stderr 再打一份 JSON |

非 TTY 且没有 `-y`：`_confirm` 打印 `auto-reject` 并拒绝。不要在脚本里指望隐式同意。

`approve` / `reject` 用可重复的 `--patch-id`、`--shell-id`、`--memory-id`。不给 id 且是 TTY 时，会按 `status` 列出的待办逐个问。`--no-input` 时必须显式给 id。路径：

| 种类 | apply | reject |
|------|-------|--------|
| patch | `/api/workspace/patches/{id}/apply` | `.../reject` |
| shell | `/api/workspace/shells/{id}/apply` | `.../reject` |
| memory | `/api/memory/proposals/{id}/apply` | `.../reject` |

`status` 的人类可读输出会印出对应的 `loop approve --patch-id …` 命令。`--session` 只附加该会话是否在跑、以及最后一条消息的预览（截到约 200 字）。会话不存在则 `ApiError` 404。

`ApiError` 退出码 1。`KeyboardInterrupt` 退出码 130。

配置文件键（`load_cli_config`）：`base_url`、`timeout`、`default_model`、`auto_approve`。坏 JSON 或非对象当空配置。这个文件不放 API key，也不和 `model_profiles.json` 合并。

## 相关测试

`backend/tests/test_cli_config.py`、`test_cli_gates.py`、`test_cli_http_gates.py`。
