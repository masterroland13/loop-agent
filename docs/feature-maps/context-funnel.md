# 跨轮上下文漏斗（C0–C5）

交接契约：原文留在用户数据里的 JSONL（和 SQLite），摘要上树，模型用检索把丢掉的细节拉回来。压缩是交接，不是删证据。

```text
C0  transcript.jsonl 只追加，密钥打码
C1  compaction_summary 上树，被折区间离开 leaf 路径
C2  被折的 user 原话按近→远、有帽地挂回
C3  transform_context：发送前与环内每次 LLM 前同一钩子，再压仍上树
C4  search_session 只搜本会话 JSONL 与 turns/ spill
C5  手动 compact + 占用条。auto_compress 默认仍关
```

算法在 `services/compress.py`，上树在 `services/compaction_persist.py`，钩子在 `services/context_transform.py`。`agent/loop.py` 只调用钩子，不复制切点或六节。

本图停在 C5。工具 batch 中途再压、对弃枝做摘要、以及 MCP client，都没有落点，这里不写步骤。

## C0 · 全文落盘

`services/session_transcript.py`。

| 符号 | 行为 |
|------|------|
| `TRANSCRIPT_NAME` | `transcript.jsonl` |
| `_resolved_transcript_path` | 只允许 `app_data_dir / session.data_path / transcript.jsonl`。逃逸则返回空，调用方不写 |
| `redact_value` | 键名像 api key / authorization / password / secret / token 的值换成打码；赋值形式与 `sk-` 长 token 同样打码 |
| `append_transcript_event` | 只追加一行 JSON |
| `append_message_event` | user / assistant / tool |
| `append_sse_event` | gate、tool_start（可带 arguments）等 |
| `append_compact_event` | **上树成功之后**才写 compact 行 |
| `read_transcript_events` / `iter_transcript_lines` | 坏行跳过 |

附件只记 id 与文件名，不把文件字节写进 JSONL。中断或出错的 assistant 也追加。进程被杀掉时，最后一条可能来不及写。不写工作区，不写安装目录。`loop uninstall` 不删这个文件。

进模型的上下文不因 C0 改变。C0 只是多一份可检索的原文。

## C1 · 摘要上树

`persist_compaction_on_tree`：

- 新行 `entry_type=compaction_summary`。
- `parent_id` 接被折第一段原来的父。
- 近端改挂到摘要链上。`update_leaf=False`，leaf 仍是当前 tip。
- relink 失败走 `_rollback_persist`：删掉半条摘要，已改的 parent 改回去。
- 树长度对不齐时不猜切点。

`persist_compaction_from_tree`：环内 working 比树长（多了本轮工具）时，在**当前 leaf 路径**上重算切点，摘要正文仍用刚压出来的那份。

下面这些**不**写摘要：`auto_compress` 关且不是 `force`；只做了 `tail_trim`；压缩失败。

## C2 · 留下 user 原话

`select_folded_user_originals`。被折区间里的真实 user，从近到远往前收，默认帽 `DEFAULT_KEEP_FOLDED_USER_TOKENS = 8192`。超帽就停，不再跳过中间去捞更早的短 user。assistant / tool 不会被改成 user。这些 user 挂在摘要和近端之间，下一次 leaf 路径还能看见。

上树使用同一次压缩算出的帽，避免内存里按小帽截了、树上又按 8K 多挂。

## C3 · transform_context

`install_context_transform` 把 `auto_compress`、`context_limit`、摘要函数、`on_compressed` 绑到 `LoopConfig.transform_context`。

`compress_messages_if_needed` 的判定：

- `auto_compress` 与 `force` 都没有 → 原样返回。
- 否则阈值是 `context_limit - reserve`。`DEFAULT_TOKEN_RESERVE = 1024`。`context_limit` 缺省 8192，所以自动压的线大约是 7168（估算 token）。
- 未超阈值且不是 `force` → 不压。
- `find_cut_index` 从尾部累加，只在 user/assistant 边界切。近端保留默认 `DEFAULT_KEEP_RECENT_TOKENS = 2048`。
- 六节标题：Goal、Constraints、Progress、Key Decisions、Next Steps、Critical Context。前缀说明这是交接。
- 摘要优先走 LLM；失败用 `build_extractive_summary`。`coerce_six_sections` 挡住把 Goal 原文回声进摘要。
- `preserve_goal` 把目标钉进摘要头，并在压缩后再放回独立 system 块。
- token 估算是 `approx_tokens`（约 chars/4），不是供应商账单。

发送前和环内第二次超限走同一个钩子。环内压完仍调用 C1 的 persist。Goal 关不注入目标块。

## C4 · 检索

`services/session_search.py` 与 `tools/session_tools.py`。

| 限制 | 值 |
|------|----|
| 默认命中 | 8 |
| 硬帽 `MAX_HITS` | 12 |
| 单条摘录 `MAX_EXCERPT` | 220 |
| 总字数 `MAX_TOTAL_CHARS` | 6000 |
| 单文件读入 `MAX_BLOB_READ` | 120_000 |

检索范围只有本会话的 `transcript.jsonl` 和 `turns/` 下的 spill。查询词全部要命中。摘录带行号，以及 name/path。

明确不做：

- 不读 SQLite 消息正文，也不在 JSONL 缺失时用数据库顶上。
- 不搜其它会话。工具若收到不同的 `session_id`，`SESSION_FORBIDDEN`。
- 不搜工作区。
- 不搜 `.env`、`.env.local`、`.env.production`、`credentials.json`，以及文件名以 `.env` 开头或结尾的路径。错误码 `PATH_FORBIDDEN`。
- 会话根不在用户数据目录内则拒绝。
- 不把整份日志塞回模型。到帽之后 `truncated: true`。

system 提示只说明：摘要漏了路径、引文或工具细节时，调用 `search_session(query=...)`，不要猜，也不要倒出全文（`api/routes.py` 里拼 system 的那一段）。

## C5 · 手动 compact 与占用

| 入口 | 落点 |
|------|------|
| `POST /api/sessions/{id}/compact` | `compact_session_endpoint`。body 可带 `focus`。内部以 `force` 调用压缩，不依赖 `auto_compress` |
| `GET /api/sessions/{id}/context` | `_session_context_usage`。`tokens`、`context_limit`、`percent`、`message_count` |
| 输入区百分比 | `src/App.tsx` 的 `occupancyPercent`，`src/components/ChatInput.tsx` 显示。≥85 用警告色 |
| ⋮「压缩上下文」 | `ChatInput` 的 `compact` 项，`src/api/agent.ts` 的 `compactSession` |

手动压的顺序与自动压相同：先压，再严格对齐上树，对不齐则 `persist_compaction_from_tree`。上树失败不再返回成功。JSONL 的 compact 事件只在上树成功后追加。Goal 开时 `resolve_session_goal(..., audit_source="compact")` 把目标钉进这次摘要。

可压历史少于 2 条：400，`EMPTY_SESSION`，不改工作区。`percent` 用 `min(999, round(100 * tokens / limit))`。

`auto_compress` 的缺省仍是 `agent_settings.DEFAULTS` 里的 `False`。打开它是另一次产品决定，不在本图里改。

## 相关测试

`backend/tests/test_session_transcript.py`、`test_compaction_persist.py`、`test_compress.py`、`test_compress_auto_off.py`、`test_context_transform.py`、`test_session_search.py`、`test_compact_api.py`。

方案与审查长文：[`docs/plans/context-loop-strengthen.md`](../plans/context-loop-strengthen.md)、[`docs/research/context-loop-c0-c5-review.md`](../research/context-loop-c0-c5-review.md)。狗粮剧本：[`docs/dogfood/section-7-compress-playbook.md`](../dogfood/section-7-compress-playbook.md)。
