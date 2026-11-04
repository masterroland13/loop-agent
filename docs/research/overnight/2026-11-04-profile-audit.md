# 2026-11-04 过夜档案对照（安全与范围）

> 只读审查。基线 `47c18f98fc55f1faeaa9b2f967878323e4310520`。  
> 对照：用户档案（路径禁逃、密钥打码、`.env` 不进检索、卸载留用户数据、文档/JSONL/桌面 `.env` 不落密钥、禁止把新算法焊进 `loop.py`、`auto_compress` 默认关、不做 C6/C7/N2）以及过夜约束。  
> 冲突序仍是宪章 > 路线图 > foundation-status。本次**零产品改动**。小洞没有就地改代码，因为授权范围只有 `docs/research/overnight/`。

健康命令与退出码见同目录 [`2026-11-04-health.md`](2026-11-04-health.md)。下面每条「对齐」都指这 461 个测试所覆盖的行为，外加当场读到的源码。

## 对齐了什么

### 1. 用户数据路径禁逃（会话检索与 JSONL）

- `session_transcript._resolved_transcript_path`：`data_path` 为绝对路径，或解析后不在 `APP_DATA_DIR` 下，则拒绝写入。
- 测试 `test_escape_data_path_does_not_write_outside_app_data`：`data_path = ../<workspace>` 时，工作区里没有 `transcript.jsonl`，读回事件为空。
- 测试 `test_transcript_stays_out_of_workspace_and_install`：JSONL 在用户数据目录下，工作区与 `LOOP_INSTALL_DIR` 里没有 jsonl。
- `session_search._session_root`：会话根解析后必须落在 `app_data_dir` 内，否则 `PATH_FORBIDDEN`。
- `resolve_searchable_path`：拒绝绝对路径、`..`、以及路径段里的 `.env` / `credentials.json`。可搜范围只有 `transcript.jsonl` 与 `turns/`。
- `resolve_session_blob_path`：拒绝 `..`，并用 `resolve().relative_to(root)` 挡符号链接跳出。
- 附件 `resolve_file`：存储名含 `/`、`\`、`..` 直接拒绝，再对解析后的路径做 `relative_to`。
- 工作区 `resolve_in_workspace`：`expanduser` + `resolve` 后必须仍在已解析的工作区根下，错误码 `PATH_ESCAPE`。`get_workspace_root` 本身会 `resolve()`。测试见 `test_workspace_files_api.py`、`test_propose_delete.py`。

三目录默认值彼此分开（`test_install_dir_is_separate_from_user_data`）：

| 角色 | 默认路径 |
|------|----------|
| 安装目录 | `~/.local/lib/loop-agent` |
| 用户数据 | `~/.local/share/loop-agent` |
| `loop` 命令 | `~/.local/bin` |

### 2. 密钥打码（JSONL 与公开接口）

`redact_value`（`session_transcript.py`）在写入 JSONL 前处理载荷：

- 键名命中 `api_key` / `authorization` / `password` / `secret` / `token` 等：整值换成 `[redacted]`。
- 字符串里的 `key=...` / `bearer: ...` 赋值形态打码。
- 正文里的 `sk-` 后接 8 位以上 token 打码。

测试 `test_secrets_are_redacted_and_attachment_bodies_stay_out`：`sk-SUPERSECRETKEYVALUE99` 不出现在 JSONL；`api_key` 与 `authorization` 字段为 `[redacted]`。检索摘录再次走 `redact_value`。

公开配置只给 `api_key_configured`。`save_llm_config` 的返回值测试断言不含密钥字符串。审计日志记 `api_key_updated` 布尔，不记密钥本身。空字符串保存不擦已有 Key（`test_empty_api_key_does_not_wipe`）。

桌面子进程：`backend_env` 设置 `LOOP_SHELL=1`。`Settings` 因此不读 `backend/.env`。`save_llm_config` 在该环境下不写 `.env`（`test_shell_save_updates_profile_without_writing_env`、`test_spawned_settings_follow_shell_data_dir_not_dotenv`）。Key 进用户数据目录的 `model_profiles.json`。这与 [`../api-key-storage.md`](../api-key-storage.md) 的现状描述一致：明文 JSON、接口不回显、桌面不把 Key 写进开发用 `.env`。

### 3. `.env` 不进会话检索

`search_session` 的文件头写明：不读 SQLite 正文、不读其他会话、不读工作区、不读 `.env`。

- 名字等于、开头或结尾是 `.env`，或名为 `credentials.json`，扫描时跳过，点名路径则 `PATH_FORBIDDEN`。
- 测试 `test_search_does_not_read_other_session_or_env`：本会话 token 能命中；其他会话 token 与会话目录里的 `.env`（`API_KEY=sk-envleak12345678`）不出现；`path=".env"` 与 `path="../.env"` 都是 `PATH_FORBIDDEN`。
- 测试 `test_search_rejects_turns_env_and_bad_max_hits`：`turns/secret.env` 拒绝。
- 测试 `test_search_does_not_fall_back_to_sqlite`：不把 SQLite 当后备原文。
- 摘录预算：单条约 220 字，合计 `MAX_TOTAL_CHARS = 6000`，命中最多 12。测试要求整份 JSON `< 50000`。符合「不塞 50KB」。

### 4. 卸载保留用户数据

`uninstall_shell_assets` 只删安装目录（须长得像已安装的 Loop Agent）、带标记的 `bin/loop`、带标记的 `loop-agent.desktop`。注释与实现都写明留下用户数据目录和工作区。

拒绝条件：安装目录与用户数据目录是同一路径；安装目录是 `$HOME` 或 `$HOME/.local`；安装目录是 git checkout。

测试：

- `test_uninstall_removes_program_keeps_user_data`：程序目录、launcher、desktop 消失；`data/workspace.json` 与仓库里的 `backend/data/workspace.json` 都还在。
- `test_uninstall_leaves_transcript`：卸载后 JSONL 里仍有 `survive-uninstall`。
- `test_uninstall_leaves_a_foreign_loop_command`：没有 launcher 标记的 `loop` 命令保留；`data/keep.txt` 保留。
- `test_uninstall_refuses_a_checkout`：仓库路径卸载失败，源码还在。

### 5. 仓库里的密钥、JSONL、`.env`

`git ls-files` 里与 env/jsonl/档案相关的跟踪文件只有 `backend/.env.example`。

- 没有跟踪的 `*.jsonl`。
- 没有跟踪的 `backend/.env`（`.gitignore` 含 `backend/.env` 与 `backend/data/`）。
- 没有跟踪的 `model_profiles.json`。
- `.env.example` 的 `LLM_API_KEY=sk-your-litellm-key` 是占位符，旁边是文档用的 base URL `https://llm-cn.gameye.ai/v1`。全库（排除 venv / node_modules / lock）没有第二把 `sk-` 长密钥。测试里的 `sk-SUPERSECRETKEYVALUE99`、`sk-new-secret`、`sk-shell-only` 是断言夹具，只活在测试进程。
- 开发态（未设 `LOOP_SHELL`）保存模型仍会把 `LLM_API_KEY` 写入 `backend/.env`。该文件被忽略，桌面路径不走这条。

### 6. `loop.py` 没有焊上压缩 / 检索 / 落盘

`backend/src/agent_window/agent/loop.py` 858 行。与漏斗相关的接入是一行钩子：`_run_one_turn` 开头 `apply_transform_context`。`find_cut_index`、六节摘要在 `services/compress.py`。检索在 `tools/session_tools.py` + `services/session_search.py`。JSONL 在 `services/session_transcript.py`。`after_tool_batch` 接到的是 Goal 批末钩子（`goal_hooks._after_tool_batch` → `flush_goal_after_batch`），Goal OFF 时这个钩子被清掉。

环里仍有既有的 soft-land、未验证写入提示、工具批编排。那是环本身，不是把压缩算法或检索再抄一份进 `loop.py`。

### 7. `auto_compress` 默认关

`agent_settings.DEFAULTS["auto_compress"] = False`。读盘时 `bool(...)`，缺省仍是关。`compress_messages_if_needed`：`auto_compress` 为假且 `force` 为假时原样返回。

测试 `test_auto_compress_off_returns_messages_untouched`：超限、并带 `preserve_goal`，仍然 `compressed is False`、消息不变、没有摘要块、没有目标块。对照测试在 `auto_compress=True` 时同一输入会压。

`POST /api/sessions/{id}/compact` 调用时传入 `auto_compress=True` 且 `force=True`。这是 C5 手动压缩，不是把默认开关打开。发送路径经 `install_context_transform`，未显式传入时读设置，默认关。

本次没有改这个默认，也没有改 `CHANGELOG` / `foundation-status`（那些文件只在真正改默认或改 A0–A4 行为时动）。

### 8. C6 / C7 / N2 未开工

| 项 | 档案里的含义 | 树里的状态 |
|----|----------------|------------|
| C6 | 一批工具完成后再压（不是「一条 tool_result 刚回来就压」，也不是本已存在的两次 LLM 之间） | `after_tool_batch` 不调用压缩。压缩只发生在下一次 `_run_one_turn` 进入模型之前。路线图与 README 写明后做 |
| C7 | regenerate 时给弃枝一份摘要 | `regenerate_endpoint` 保留旧 assistant、新 sibling、更新 leaf。没有弃枝摘要写入 |
| N2 | 过夜约束所指的 MCP client | 产品源码（排除 venv）没有 `mcp` import，没有 MCP client。宪章与路线图把 MCP 列在暂缓。仓库里没有名为 N2 的切片 |

`foundation-status` 当前焦点仍是「C0–C5 已落地；可选 C6」。与代码一致。本次没有把 C6 标成进行中。

预设仍是 `loop_preset` 默认 `yolo`，Goal 不是默认模式。与档案一致，本次未改。

## 就地修了什么

无。授权只允许写 `docs/research/overnight/`。下面两条没有改产品代码。

## 放下的问题（不在本刀修）

### A. 工作区 `grep` / `read_file` 会读工作区里的 `.env`

会话检索 `search_session` 拒绝 `.env`。工作区工具是另一条路：`grep_search` 只跳过 `.git`、`node_modules`、`.venv` 等目录名，**不按文件名跳过 `.env`**。`read_file` 同样只要路径还在工作区根里就读。

因此：用户把项目 `.env` 放进已绑定工作区时，模型可以通过 `grep` / `read_file` 读到，工具结果再经 `redact_value` 写入 JSONL。`sk-` 与 `api_key=` 会被打码；不长得像这两种形态的密钥会进 JSONL 正文（见下条）。

这是编码工具对工作区的读，和 C4「不搜会话目录里的 `.env`」是两件事。若产品要把「`.env` 不进检索」扩到工作区工具，需要单独一刀：行为测试先写「工作区 `.env` 的内容不出现在 grep 结果里」，再改 `grep_search`（以及是否连 `read_file` 一起拒）。本报告不改这个默认能力。

### B. 打码覆盖不到非 `sk-` 形态

JSONL 打码覆盖：敏感键名、`key=value` 文本、`sk-` token。不覆盖 `AIza…`、`ghp_…`、无前缀的裸密钥，除非它们刚好坐在敏感键名下。SQLite 消息正文保持原样（检索不读 SQLite）。`model_profiles.json` 仍是用户数据目录里的明文 Key，档案调研已记录，钥匙串仍在「不做」清单里。本次不引入加密，也不改存储默认。

### C. `get_session_path` / `write_turn_blob` 信任库里的 `data_path`

正常 `create_session` 只写入 `APP_DATA_DIR` 下的相对路径，没有 API 让调用方自选 `data_path`。JSONL 追加对 `../` 有测试。`write_turn_blob` 直接 `APP_DATA_DIR / data_path`，库行若被改成带 `..` 的 `data_path`，spill 可以写出用户数据根。同一 OS 用户本来就能改 SQLite。若要收紧，应在 `get_session_path` 与 JSONL 用同一条「解析后必须位于 `APP_DATA_DIR`」检查，并补一条 spill 的反向测试。本刀不改。

### D. `uninstall` 只拒绝「安装目录 == 用户数据目录」

默认路径不相等，也不互相包含，测试锁住了这个布局。若有人把 `LOOP_INSTALL_DIR` 指到用户数据的父目录，且该目录「看起来像安装」（含 `dist/index.html` 等），`shutil.rmtree(install)` 会连带删掉里面的用户数据。`$HOME` 与 `$HOME/.local` 已被拒绝，挡不住更深的嵌套。收紧方式是：解析后若 `data_dir` 在 `install_dir` 之内或反过来包含，拒绝卸载。需要新测试，本刀不改。

### E. 弃用警告与 npm high

见健康报告。不在本刀修：Pydantic `ConfigDict`、FastAPI lifespan、`datetime.now(UTC)` 是行为等价的清理，但面宽；npm 三条要动 lockfile，且 vite 公告主要在 Windows 开发服务器。

## 对照仍成立

- 分层：`loop-ai` 概念上仍是钩子与配置；物理包名仍是 `agent_window`。core 不 import api/models（分层测试通过）。
- 压缩是交接：JSONL 不因压缩被删（`test_compress_does_not_delete_or_rewrite_jsonl`）；`auto_compress` 关时 JSONL 也不被假摘要改写。
- 手动 compact 把 `force=True` 与设置里的默认开关分开。
- C0–C5 在树上；C6、C7、MCP client 不在树上。
- 文档索引 [`docs/README.md`](../../README.md) **没有**加入本目录。过夜约束只允许写 `docs/research/overnight/`。索引补一行要另一次确认。

## 下一刀建议（停在建议，未开工）

1. 若要收「工作区 `.env`」：先写失败测试，再决定只拦 `grep` 还是连 `read_file` 一起拦。这会改变编码助手读项目密钥文件的能力，先确认。
2. 若要收卸载嵌套：`data_dir` 与 `install_dir` 互为祖先则拒绝，并加反向测试（子目录里的 `keep.txt` 在拒绝后仍在）。
3. `get_session_path` 与 JSONL 共用禁逃，给 `write_turn_blob` 一条 `../` 反向测试。
4. 弃用警告与 npm advisory 单独提交，不跟功能刀混在一起。
5. C6 / C7 / MCP 继续不动，直到点名开工。`auto_compress` 默认仍关，打开必须单独提交。
