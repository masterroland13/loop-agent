# 编码工具

逻辑层 **loop-coding**：`backend/src/agent_window/tools/` 与 `services/{workspace,patches,shell,memory,skills,compress,session_search,session_transcript,attachments}.py`。注册发生在 import：`tools/__init__.py` 导入各模块，模块底部调用 `register_*`。中央表是 `tools/registry.py` 的 `registry`，`get_openai_tools()` 产出供应商的 tools 列表。

工具返回 JSON 字符串。写操作在 YOLO 下由管线直接执行；Trusted / Strict 返回等待标记，等 Apply。工具函数内部不写死「必须审批」。

## 已注册工具

| 名字 | 文件 | 做什么 | 不做什么 |
|------|------|--------|----------|
| `ping` | `tools/builtin.py` | 回声，验证工具调用 | |
| `get_weather` | 同文件 | 问 wttr.in | 不是编码主路径 |
| `list_dir` | `tools/fs_tools.py` → `workspace.list_directory` | 工作区相对路径。默认最多 200 条 | 跳过 `.git`、`node_modules`、`.venv`、`venv`、`__pycache__`、`dist`、`build`、`.next`、`.tox`、`.mypy_cache`、`.pytest_cache` |
| `read_file` | 同文件 → `workspace.read_file` | 带行号的文本窗。默认 200 行，上限 500 | 不写出 |
| `grep` | 同文件 → `workspace.grep_search` | 工作区内正则。单文件读上限 1_000_000 字节，最多 40 条，行截到 300 字 | 见下文「.env」 |
| `propose_edit` | `tools/edit_tools.py` | `old_string`+`new_string`，或整文件 `content`。先 `read_file` | 用户 Apply 前不写盘 |
| `propose_delete` | 同文件 | 工作区内普通文件 | 不走 shell `rm` |
| `propose_shell` | `tools/shell_tools.py` | `argv` 数组，无管道。`cwd` 相对工作区 | 不在提案时执行 |
| `propose_memory` | `tools/memory_tools.py` | `target=user` → USER.md；`target=memory` → MEMORY.md。`action=add/replace/remove`，条目用 `§` 分隔 | `mode=replace` 会整文件覆盖，提示禁止拿它当追加 |
| `read_attachment` | `tools/attachment_tools.py` | 本轮 `[附件]` 的文本。默认 200 行，上限 500 | 图片已作为视觉输入；PDF 返回不可当文本 |
| `search_session` | `tools/session_tools.py` | 本会话 JSONL + spill 短摘录 | 见 [`context-funnel.md`](context-funnel.md) |

没有单独的 skill 工具。system 只放 catalog（`services/skills.py` 的 `skill_context_blocks`）。要正文时用 `read_file` 读工作区 `skills/<id>/SKILL.md`。

`disabled_tools` 在治理设置里，发送前从名单去掉。

## 工作区沙箱

`services/workspace.py`：

- 根来自 `app_data_dir/workspace.json` 的 `root`。目录必须已存在。
- `require_root()`：没绑定则 `NO_WORKSPACE`，工具没有根。
- `resolve_in_workspace()`：相对路径拼到根上再 `resolve`。结果必须落在根内，否则 `PATH_ESCAPE`。
- 人用 Files API 与 Agent 读是同一套解析：列出、读、写、`mkdir`、`rename`、`copy`、`delete`（可 `recursive`）、`tree_stats`、`reveal_in_explorer`。
- 浏览新建：`create_browse_directory` 只在给定父目录下建子文件夹，名字拒绝 `.`、`..` 和斜杠。建完并不自动绑定。点「使用此文件夹」才 `set_workspace_root`。
- Agent `read_file` 上限 `MAX_READ_BYTES = 100_000`。人用编辑器 `MAX_EDITOR_BYTES = 2_000_000`。`.docx` 走 mammoth / htmldocx（`read_docx_file` / `write_docx_file`）。Excel / PPT 不在这条路径上。

工作区 `grep` / `list_dir` / `read_file` **按沙箱限制位置，不按文件名排除 `.env`**。会话检索才拒绝 `.env`。不要把这两件事写成同一条规则。

## Shell 白名单

`services/shell.py`。提案先校验，通过才进 `pending_shells.json`。

允许的二进制：`python`、`python3`、`pytest`、`npm`、`npx`、`node`、`pnpm`、`yarn`、`uv`、`cargo`、`go`、`make`、`ls`、`pwd`、`cat`、`head`、`tail`、`rg`、`echo`、`uname`、`which`、`git`、`tsc`、`oxlint`。

拒绝的 token：`sudo`、`su`、`rm`、`dd`、`mkfs`、`shutdown`、`reboot`、`chmod`、`chown`、`curl`、`wget`、`scp`、`ssh`。

`git` 只允许：`status`、`diff`、`log`、`show`、`branch`、`rev-parse`、`remote`、`describe`、`shortlog`、`blame`、`ls-files`。子命令前的 flag 不行。

`python` / `python3` / `node` 拒绝 `-c`、`--command`、`-e`、`--eval`、`-p`、`--print`。超时 `CMD_TIMEOUT_SEC = 60`。输出帽 `MAX_OUTPUT_BYTES = 32_000`。

HTTP：`GET /api/workspace/shells`，`POST .../shells/{id}/apply|reject`。

## 补丁

`services/patches.py`。`create_patch_from_replace` / `create_patch_from_content` / `create_patch_for_delete` 生成 unified diff，状态先进 `pending_patches.json`。`parse_hunks` + `apply_hunks_to_content` 支持只应用选中的 hunk。`apply_patch_to_disk` 才写工作区。

HTTP：`GET /api/workspace/patches`，`POST .../patches/{id}/apply|reject`。部分应用走 hunk 选择（前端 Diff 面板）。

已知未覆盖：CRLF diff、文件末尾无换行、同一文件并发 `propose_edit`。

## 记忆

`services/memory.py`。文件在用户数据，不在工作区：

- `users/local-user/USER.md`，默认 1375 字。
- `users/local-user/MEMORY.md`，默认 2200 字。
- 钳制 500–8000。超限抛 `WorkspaceError`，码 `MEMORY_FULL`（`_raise_memory_full`）。
- 重复条目拒绝。
- `freeze_user_md_for_session` / `freeze_memory_md_for_session`：会话内用快照。中途 Apply 立刻写盘，本会话 system 仍用冻结文本，下一会话才看到新快照。

待审批：`pending_memories.json`。HTTP：`GET /api/memory/proposals`，`POST .../proposals/{id}/apply|reject`。

## Skills 与 AGENTS.md

`services/skills.py`：

- 发现目录是**工作区** `skills/<id>/`，优先 `SKILL.md`，否则 `README.md`。单份正文帽 `MAX_SKILL_CHARS = 12_000`。
- 激活名单在 `agent_settings.json` 的 `active_skills`。
- `AGENTS.md` 分层：`~/.config/loop-agent/AGENTS.md`（否则旧目录 `~/.config/hal-agent/AGENTS.md`）→ 工作区父目录向上 → 工作区根。后者更具体。
- system 注入 catalog 与分层规则正文（`skill_context_blocks`），不把每份 SKILL 全文塞进每轮。

HTTP：`GET /api/skills`，`PUT /api/skills/active`。

仓库自带一份 `skills/code-review/SKILL.md`，只有工作区指到本仓库时才会被发现。

## 附件

`services/attachments.py` 与 `attachment_context.py`。文件在会话数据目录 `attachments/`，不在工作区。`use_attachment_session` 把当前会话 id 放进上下文，`read_attachment` 只读这一份。`search_session` 同样用这个绑定：请求里的 `session_id` 若与绑定不同，返回 `SESSION_FORBIDDEN`。

## 相关测试

`backend/tests/test_propose_delete.py`、`test_hunk_apply.py`、`test_workspace_files_api.py`、`test_workspace_mkdir.py`、`test_memory_bounds.py`、`test_memory_entries_m1.py`、`test_memory_md_m0.py`、`test_skills_layered.py`、`test_attachments.py`、`test_session_search.py`、`test_session_workspace_bind.py`。
