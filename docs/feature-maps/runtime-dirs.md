# 运行时目录

和 import 分层正交。`agent/loop.py` 不拼安装路径。谁写文件，由下面这张表决定。

| 目录 | 默认 | 覆盖 | 谁读写 | 卸载时 |
|------|------|------|--------|--------|
| **安装目录** | `~/.local/lib/loop-agent` | `LOOP_INSTALL_DIR` | `loop install` 写入，`loop shell` 读取 | `loop uninstall` 整棵删掉（见守卫） |
| **命令入口** | `~/.local/bin/loop` | `LOOP_BIN_DIR` | `install_loop_command` | 只删带 `# loop-agent launcher` 标记的文件 |
| **桌面启动项** | `~/.local/share/applications/loop-agent.desktop` | `LOOP_APPLICATIONS_DIR` | `install_desktop_entry` | 只删带 `# loop-agent desktop` 标记的文件 |
| **用户数据** | `~/.local/share/loop-agent` | `APP_DATA_DIR`；桌面还可设 `LOOP_SHELL_DATA_DIR` | `Settings.app_data_dir` | **留下** |
| **工作区** | 无。记在用户数据的 `workspace.json` | 用户绑定的文件夹 | `services/workspace.py` | **留下** |
| **CLI 配置** | `~/.config/loop-agent/config.json` | 环境变量 `AGENT_BASE_URL` 优先 | 只服务 CLI，不并进用户数据 | 不碰 |

真源函数：

- `default_user_data_dir()`：`backend/src/agent_window/config.py`。空的 `APP_DATA_DIR` 也回到这个默认，不使用进程当前目录。
- `default_install_dir()` / `shell_data_dir()` / `shell_bin_dir()` / `shell_applications_dir()`：`backend/src/agent_window/host/session.py`。
- CLI 路径：`backend/src/agent_window/cli/config.py` 的 `CONFIG_PATH`。新文件不存在时，只读回退到旧目录 `~/.config/hal-agent/config.json`。产品名仍是 Loop Agent。

开发进程在 `backend/.env` 里写 `APP_DATA_DIR=./data`，继续用仓库狗粮库 `backend/data`。`loop shell` 把子进程的 `LOOP_SHELL=1`，`Settings` 因此不读 `backend/.env`（`config.py` 的 `env_file`）。

## 安装目录里有什么

`install_shell_assets()` 从仓库拷入，不把运行时指回源码树：

| 安装后路径 | 来源 |
|------------|------|
| `dist/` | 仓库根 `dist/`（须先 `npm run build`，要有 `dist/index.html`） |
| `loop-window` | `shell/loop-window`；不是 ELF 时 `ensure_window_binary()` 用 `gcc` + `webkit2gtk-4.1` 编 `shell/loop-window.c` |
| `venv/` | `backend/.venv` 的拷贝；删掉 `_editable_impl_*.pth`，再把 `backend/src/agent_window` 实体拷进 site-packages |
| 图标 | `public/ouroboros-logo.png` 或 `.svg`，有才拷 |

`~/.local/bin/loop` 的正文是：

```sh
# loop-agent launcher
exec "<安装目录>/venv/bin/python" -m agent_window.cli "$@"
```

桌面项 `Exec` 写这条命令的绝对路径加 `shell`，不依赖当前 `PATH`。入口声明在 `backend/pyproject.toml` 的 `[project.scripts] loop`。

`loop install` 必须从含 `backend/src/agent_window/__init__.py` 的检出树运行。已经装好的那份 `loop` 再执行 `install` 会停（`checkout_root` / `is_checkout_tree`）。目标 `loop` 或 `.desktop` 已存在且没有本产品标记时拒绝覆盖。

## 用户数据里有什么

根是 `Settings.app_data_dir`。常见文件（相对该根）：

| 路径 | 写入者 |
|------|--------|
| `agent_window.db` | `models.get_engine()`，SQLite |
| `agent_settings.json` | `services/agent_settings.py` |
| `model_profiles.json` | `services/model_registry.py`。对外列表只有 `api_key_configured`，不回密钥原文 |
| `workspace.json` | `services/workspace.py` 的 `_config_path()`。字段 `root` |
| `pending_patches.json` | `services/patches.py` |
| `pending_shells.json` | `services/shell.py` |
| `pending_memories.json` | `services/memory.py` |
| `users/local-user/USER.md` | `user_md_path()` |
| `users/local-user/MEMORY.md` | `memory_md_path()` |
| `users/local-user/sessions/<id>/` | `storage.create_session()`。`Session.data_path` 是相对 `app_data_dir` 的路径 |
| `…/transcript.jsonl` | `services/session_transcript.py` |
| `…/turns/<assistant>/e<n>.txt` | `storage.write_turn_blob()`，过大工具结果 spill |
| `…/attachments/` | `services/attachments.py` |

会话 id 形如 `YYYYMMDD-HHMMSS`。没绑定工作区时 `workspace.json` 不存在或 `root` 为空，coding 沙箱没有根，工具读不到安装树，也读不到这份用户数据目录（除非用户把工作区指到那里，那是用户自己的绑定）。

## 路径守卫

| 动作 | 函数 | 拒绝什么 |
|------|------|----------|
| JSONL 落盘 | `_resolved_transcript_path` | `data_path` 为空、绝对路径、或解析后不在 `app_data_dir` 下。此时不写 |
| spill 读取 | `resolve_session_blob_path` | `..`、绝对拼接逃出 `session.data_path` |
| 会话检索 | `session_search._session_root` / `resolve_searchable_path` | 会话根逃出用户数据；用户给的 path 逃出该会话；`.env` 与凭证文件名 |
| 工作区工具 | `resolve_in_workspace` | 解析后不在工作区根下，错误码 `PATH_ESCAPE` |
| 卸载 | `uninstall_shell_assets` | 安装目录与用户数据相同、是家目录、是 `~/.local`、或看起来是仓库检出。这些情况整次不删 |

`loop uninstall` 的删除列表只有：安装目录（确认像一份安装）、带标记的 `loop` 命令、带标记的桌面项。用户数据目录、工作区、`~/.config/loop-agent` 不在删除列表里。

## 桌面进程与密钥文件

`services/llm_config.py` 的 `save_llm_config()` 在开发进程里会把 `LLM_*` 写进 `backend/.env`（`_env_path()` 指到包上三级，即 `backend/.env`），并 `chmod 0o600`。`LOOP_SHELL=1` 时这段不写。桌面保存模型只进 `model_profiles.json`。

## 相关测试

`backend/tests/test_app_data_dir.py`、`test_shell_session.py`、`test_shell_python.py`、`test_session_transcript.py`、`test_session_search.py`、`test_llm_config.py`、`test_model_registry.py`。
