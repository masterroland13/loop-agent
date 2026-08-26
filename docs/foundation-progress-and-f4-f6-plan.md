# Hal Agent 能力盘点与 F4/F6 中间路线

> 文档日期：2026-08-22（UTC+8）  
> 来源：Foundation 实施对话（F2 落地 → 测试修复 → UI 改造 → F4/F6 规划 → 全量能力对比）  
> 适用读者：继续在本仓库工作的 Agent / 开发者  
> 关联：`docs/agent-window-roadmap.md` §0 / §7 / §15

---

## 1. 文档目的

1. 记录截至 **2026-08-22** 已落地功能的**真实完成度**（相对路线图「完整版」）。  
2. 说明 **F4（观察瘦身）** 与 **F6（中间态落库可见）** 的定位、分档方案与用户已确认的 **中间路线**。  
3. 列出**未来改进清单**，避免重复讨论或误把 UI 壳当成 Foundation 完成。

---

## 2. 档位定义（全文通用）

| 标记 | 含义 | 约等于完整版能力 |
|------|------|------------------|
| **完整** | 路线图该条主验收基本满足 | **90%+** |
| **中间** | 核心链路有，持久化/配置/边角不全 | **60–75%** |
| **MVP** | 能演示，缺关键场景或不可持续 | **25–40%** |
| **未做** | 基本没有 | **0%** |

**「最小完整版」（本项目的实用标准）= 中间档**：能日常 dogfood，不依赖「演示时别刷新页面」。

---

## 3. 本轮已完成的开发工作

### 3.1 Foundation F2 — 进度检查点 ✅

**目标（路线图 §7.1 F2）：** 每 N 次工具或 gate 返回后，强制模型对照 Turn Goal 说明进度/阻塞/下一步。

**后端：**

| 文件 | 说明 |
|------|------|
| `backend/src/agent_window/agent/checkpoint.py` | `CHECKPOINT_MARKER`、`should_checkpoint()`、`format_checkpoint_user_message()`、间隔 clamp（默认 4，0=仅 gate，2–16） |
| `backend/src/agent_window/agent/loop.py` | 每批工具后：累计 `tools_since_checkpoint`；gate 成功/续环触发 gate 检查点；注入 user 消息；SSE `progress_checkpoint` |
| `backend/src/agent_window/agent/goal.py` | F1 依赖（曾缺失已补回）：Turn Goal 提取/注入 |
| `backend/src/agent_window/services/agent_settings.py` | `checkpoint_every_n_tools` |
| `backend/src/agent_window/schemas.py` | API 字段 |
| `backend/src/agent_window/api/routes.py` | 转发 `progress_checkpoint` SSE（message + regenerate 两路） |

**前端：**

| 文件 | 说明 |
|------|------|
| `src/hooks/useMessagePairs.ts` | 处理 `progress_checkpoint`，更新 `progressCheckpoint` |
| `src/types/index.ts` | `MessagePair.progressCheckpoint` |
| `src/components/MessagePairItem.tsx` | 「检查点」虚线条 |
| `src/components/SettingsPanel.tsx` | 进度检查点滑条（0–16） |
| `src/hooks/useSettings.ts` / `src/api/agent.ts` | 同步 `checkpoint_every_n_tools` |

**测试：**

| 文件 | 说明 |
|------|------|
| `backend/tests/test_checkpoint.py` | 单元 + loop mock 集成 |
| `backend/tests/test_turn_goal.py` | Goal 模块回归 |

**档位评估：** **中间 ~70%**（loop 内有检查点；用户看不到模型对照回答的正文；检查点不持久化）。

---

### 3.2 Foundation F1 / F3 / F5（对话前或同期已有）

| 项 | 关键路径 | 档位 |
|----|----------|------|
| **F1 Turn Goal** | `goal.py`；`extract_turn_goal`；SSE `meta`/`turn_goal`/`turn_meta.goal`；UI「目标」条 | 中间偏上 ~75% |
| **F3 失败续环** | `loop.py` gate 策略；Reject/partial 结束；timeout/failed 最多续 1 次；`test_gate_continue.py` | 中间偏上 ~80% |
| **F5 环境默认** | `shell.py` `normalize_shell_argv`；裸 `python` → venv/`python3`；`test_shell_python.py` | 中间 ~65% |

---

### 3.3 测试修复（2026-08-22）

**现象：** `69 passed` 中有 2 失败。

| 失败 | 原因 | 修复 |
|------|------|------|
| `test_loop_emits_checkpoint_after_n_tools` | `@pytest.mark.asyncio` 未启用；monkeypatch 路径 `provider.provider` 误指向字符串 | 改为 `asyncio.run()`；patch `agent_window.agent.loop.provider.chat_complete` |
| `test_low_info_followup_detection` | 正则未含英文 `continue` | `goal.py` 的 `_AFFIRMATION_RE` 增加 `continue` |

修复后全量：**69 passed**。

---

### 3.4 运维：前后端重启

**问题：** WSL 下 `nohup npm run dev` 启动的 Vite 在脚本退出后进程消失，5173 不可用。

**修复：** `restart-hal.sh` 改用 `setsid` 启动 backend（uvicorn :8000）与 frontend（vite :5173）。

**Windows 访问：** 使用 `http://127.0.0.1:5173/` 或 `http://localhost:5173/`，不要用 WSL 内网 IP。

---

### 3.5 Bug 修复：New Agent 输入框草稿串 session

**现象：** New Agent 输入未发送 → 删除 session → 再 New Agent，输入框仍保留旧内容。

**原因：** `App.tsx` 中 `inputValue` 为全局状态，未与 `activeSessionId` 绑定。

**修复：** `draftBySessionRef` 按 session 存草稿；切换 session 加载/保存；删除 session 时 `delete` 草稿；发送后清除。

**文件：** `src/App.tsx`

---

### 3.6 UI：User 消息卡片（Cursor 风，非路线图编号）

**需求（用户确认）：**

| 决策项 | 选择 |
|--------|------|
| 压缩对象 | **仅 user 消息**（非 Agent 回复） |
| 默认 | 最多 **4 行** + `line-clamp` |
| 点击展开 | 可编辑 + ChatInput 工具栏（发送/模型/+附件/This PC） |
| 发送语义 | **B：编辑内容作为新追问接在会话末尾**（不改历史 user 消息） |
| 展开时底部输入框 | **灰色禁用**（`dimmed` + `disabled`） |
| 收起 | 去掉「收起」按钮；**点击页面其它区域**自动收起；Esc 仍可收起 |
| Sticky | user 消息 `sticky top-0`，上滑悬停直至下一条顶走 |

**文件：**

| 文件 | 说明 |
|------|------|
| `src/components/UserMessageCard.tsx` | 新建：压缩/展开/sticky |
| `src/components/MessagePairItem.tsx` | 接入 UserMessageCard |
| `src/components/MessageList.tsx` | 传递展开态 props |
| `src/components/ChatInput.tsx` | 新增 `variant="card"`、`dimmed` |
| `src/App.tsx` | `expandedUser` 状态、点击外部收起、附件路由 |

**档位：** 交互中间档 ~55%；**后端无 edit-branch**，仅为追加新轮。

---

### 3.7 其它 UI / 产品壳（对话前已有，CHANGELOG [Unreleased]）

- Workspaces 侧栏（Cursor 风项目树、Open Workspace、New Chat）
- 设置抽屉 Agent/模型/外观 polish
- 消息对高亮 `--pair-highlight`
- ChatInput 统一 32px 工具栏
- Diff/Shell 审批区折叠 + 限高滚动
- `max_tool_iters` 默认 24、可配置

---

## 4. F4 / F6 说明（完整版定义）

### 4.1 F4 — 观察结构化 / 截断

**问题：** 工具原始 JSON / shell 输出原样 `working.append`，token 膨胀、乱探。

**完整版应包含：**

- 统一管道 `slim_tool_result(tool, raw) → { model_payload, display_summary, full_ref }`
- 分工具策略：list_dir / read_file / grep / shell / gate（patch/shell/memory）
- **双份数据：** slim 给模型；full 给 F6/UI 展开
- `agent_settings` 分工具上限 + debug 开关
- pytest 夹具 + ToolTimeline「展开全量」（依赖 F6）

**验收：** 同任务 token↓；loop 内无整页 ls/stdout；失败 JSON 结构化。

---

### 4.2 F6 — 中间态落库可见

**问题：** SSE 实时 `toolTrace` 仅在内存；刷新丢失；turn 中 assistant 空白像「Agent 死了」。

**完整版应包含：**

- `TurnTrace` / `TurnEvent[]` 真源
- **turn 开始** assistant 占位 + **流式增量写**（summary JSON 或 `session.data_path/turns/*.json`）
- API 返回 trace；前端灌回 `toolTrace`、检查点、审批态
- **刷新中途**可恢复 running / 等待审批
- 大输出落文件；CLI trace；审计对齐

**验收：** §0.4 第 6 条；不再「多轮好的无 assistant」。

---

### 4.3 F4 与 F6 关系

```text
工具执行 → [F4 slim] → 喂给模型（loop 内部）
         ↘ [F6 落库] → 展示给人（UI / 刷新可恢复）
```

理想：**库中存 full + trace，给模型喂 slim**。

---

## 5. 三档方案对比（F4 / F6）

### 5.1 F4

| 档位 | 内容 | 人天 | ≈完整版 |
|------|------|------|---------|
| **MVP** | loop 统一截断（2–4KB）；shell 只留 exit + stdout 头 | 1–1.5 | **~25%** |
| **中间 ★** | `observation.py` + 4 类工具 formatter + 结构化错误 + 1 个全局上限 | ~3 累计 | **~65%** |
| **完整** | 全覆盖 + 分工具上限 + slim/full 分流 + UI 展开 + 大量测试 | ~5 累计 | **100%** |

### 5.2 F6

| 档位 | 内容 | 人天 | ≈完整版 |
|------|------|------|---------|
| **MVP** | 仅 `done` 时把 events 写入 `assistant.summary`；刷新后整轮结束才可见 | 1.5–2 | **~30%** |
| **中间 ★** | turn 开始占位 + 增量写 trace + API + 前端灌回 + 刷新恢复 ToolTimeline/检查点 | ~4–5 累计 | **~70%** |
| **完整** | 大输出落文件 + 流式半段 assistant + SSE/DB 合并 + CLI + 审计 | ~6–7 累计 | **100%** |

### 5.3 组合总览

| 组合 | 总人天（估） | 相对完整版体验 | 建议 |
|------|-------------|----------------|------|
| 双 MVP | ~3–3.5 | **~28%** | 不推荐当终点 |
| **双中间 ★** | **~7–8** | **~68%** | **用户已认可** |
| 双完整 | ~11–12 | **100%** | Foundation 收口后再补增量 |

---

## 6. 用户已确认的决策

1. **认可中间路线**（非双 MVP，非一次双完整）。  
2. **实施顺序：** 共用 `TurnEvent` schema → **F6 中间** → **F4 中间** → **F9 狗粮剧本**。  
3. **F6 中间完成后**再按需补：full 落文件、分工具配置、CLI trace 等（+10–15% 即达 ~85–90%）。  
4. **不要做：** v1 Steer/时间线、Task 看板、换 favicon（除非用户另选）作为 Foundation 前置。

---

## 7. 共用设计（F6/F4 开工前半天）

建议统一事件结构，避免两套各写各的：

```typescript
// 概念 schema（Python/TS 对齐）
TurnEvent {
  type: 'tool_start' | 'tool_result' | 'progress_checkpoint' | 'gate' | 'error' | ...
  ts: number | ISO string
  tool?: string
  status?: string
  summary: string      // 短摘要 → UI + F4 slim 输入
  full_ref?: string    // 中间档可 inline ≤8KB；完整版 → data_path 文件
}
```

- **F6** 负责写入 `events[]`（assistant 占位 + 增量更新）。  
- **F4** 负责从 raw 生成 `summary`（给模型）与可选 `full_ref`。

---

## 8. 全量能力对比（当前 vs 完整版）

### 8.1 Foundation §7 必做

| # | 能力 | 现状 | 档位 | ≈完整版 | 主要缺口 |
|---|------|------|------|---------|----------|
| F1 | Turn Goal | ✅ | 中间偏上 | 75% | F8 留痕；压缩保 Goal |
| F2 | 进度检查点 | ✅ | 中间 | 70% | 不持久化；用户不见模型对照文 |
| F3 | 失败续环 | ✅ | 中间偏上 | 80% | 阻塞事实未结构化 |
| F4 | 观察瘦身 | ❌ | 未做 | 0% | 全部 |
| F5 | 环境默认 | ✅ | 中间 | 65% | 仅 python；无多运行时 |
| F6 | 中间态可见 | ❌ | MVP 级前端 | 15% | 刷新全丢；无落库 |
| F7 | 探索收敛 | ❌ | 未做 | 0% | — |
| F8 | Goal 留痕 | ❌ | 未做 | 0% | — |
| F9 | 狗粮剧本 | ❌ | 未做 | 0% | — |

**Foundation 六条必做整体（含 F4/F6 未做）：约 40–45%。**

---

### 8.2 机械环 + 审批门（Pre-Foundation）

| 项 | 档位 | ≈完整版 | 主要缺口 |
|----|------|---------|----------|
| 工具 loop | 完整 | 95% | MCP 等 |
| Diff 全量应用 | 完整 | 90% | — |
| Hunk 部分应用 | 完整 | 90% | CRLF 等未测边界 |
| Shell 审批 | 中间偏上 | 80% | 沙箱 v1 |
| Memory 审批 | 中间 | 70% | 与 Goal/压缩协同 |
| max_tool_iters + 软着陆 | 中间 | 75% | 与 F4 无关的 token 问题仍在 |
| 写盘诚实化 | 中间 | 70% | 误判/audit |
| Turn 取消 | 中间 | 75% | — |
| Regenerate / 重试 | MVP | 40% | 与 User 卡片 B 方案未统一后端语义 |

**结论：机械环 + 审批 = 项目最成熟区域，算「最小完整可用」。**

---

### 8.3 MVP 收尾 §8

| 项 | 档位 | ≈完整版 | 主要缺口 |
|----|------|---------|----------|
| M2 压缩质量 | MVP | 35% | 不压 tool；不保 Goal |
| M3 轨迹 Meta | 中间 | 65% | 无 per-tool；无 trace |
| M5 诚实 Settings | 中间 | 60% | 无能力盘点页 |
| M6 审计绑 session | 中间 | 55% | 无回放 UI/导出 |
| M7 资产盘点 | MVP | 30% | — |
| M10 错误可恢复 | 中间 | 70% | 非全路径 |

---

### 8.4 前端 / 产品壳

| 项 | 档位 | ≈完整版 | 备注 |
|----|------|---------|------|
| Workspaces 侧栏 | 中间 | 60% | 非真实 monorepo 同步 |
| This PC / 工作区 | 中间 | 65% | |
| User 消息卡片 | 中间 | 55% | B 方案仅前端 |
| 会话输入草稿 | 中间 | 70% | 已修串 session bug |
| ChatInput 工具栏 | 中间偏上 | 75% | |
| Settings 抽屉 | 中间 | 65% | 含 F2 间隔 |
| ToolTimeline | MVP+ | 45% | **依赖 F6** |
| Diff/Shell 折叠 | 中间偏上 | 80% | |
| 收藏 / 搜索 / 模型 | 中间 | 60–70% | |

---

### 8.5 CLI（hal）

| 项 | 档位 | ≈完整版 |
|----|------|---------|
| ask / status / approve / reject | 中间 | 65% |
| run --wait | 中间 | 60% |
| Goal / checkpoint / trace | MVP | 25% |

---

### 8.6 明确未做（v1+）

Steering、事件流时间线、Preset 档位、Task 看板、Project OS、多 Agent、审计包导出、沙箱加固等 — **0%**，符合路线图阶段划分。

---

## 9. 哪些算「最小完整版」？

| 分类 | 是否算最小完整 | 说明 |
|------|----------------|------|
| 审批门 + hunk + 工具 loop | **是** | 可日常改代码、跑命令 |
| F1 / F3 / F5 | **基本是** | 可 dogfood |
| F2 | **勉强** | loop 内有；用户侧弱 |
| F4 / F6 | **否** | 最大缺口 |
| Workspaces / User 卡片 | 产品壳中间档 | 不替代 Foundation |
| 压缩 / 审计 | **否** | MVP～中间 |

---

## 10. 未来改进清单（优先级）

### P0 — 中间路线（用户已认可，~7–8 人天）

1. **共用 TurnEvent schema**（半天）  
2. **F6 中间档**（4–5 天）  
   - turn 开始 assistant 占位  
   - 增量写 `events[]`（summary 或 `data_path` 文件）  
   - `getMessages` 带回 trace  
   - 前端灌回 ToolTimeline + 检查点 + 审批态  
   - 刷新可恢复  
3. **F4 中间档**（+3 天）  
   - `observation.py` + list_dir / read_file / grep / shell  
   - loop 接入 + 全局上限 + pytest  
4. **F9 狗粮剧本**（0.5–1 天）  
   - 「解释报错 → 同意深挖 → 有 Goal 对照结论」  

### P1 — 中间 → 完整增量（~3–4 人天）

5. 大输出落 `session.data_path` + UI 展开全量  
6. F2 展示模型检查点回复（可选折叠）  
7. M2 压缩保留 Goal  
8. M6 审计按会话回放 / 导出  
9. F8 Goal 变更留痕  

### P2 — v1 及以后

10. Steer / 事件流时间线（依赖 F6 真源）  
11. Preset 档位（非零散 disabled_tools）  
12. Task / Project OS  
13. CLI trace、沙箱、多 Agent  

---

## 11. F6 中间档实施清单（待开工 spec）

> 下节为下一 Agent 可直接执行的粗粒度任务分解（尚未编码）。

### 11.1 数据模型

**方案 A（推荐中间档）：** 扩展 `assistant.summary` JSON：

```json
{
  "type": "turn_meta",
  "model": "...",
  "goal": "...",
  "events": [
    { "type": "tool_start", "ts": "...", "tool": "list_dir", "summary": "..." },
    { "type": "tool_result", "ts": "...", "tool": "list_dir", "status": "done", "summary": "12 entries" },
    { "type": "progress_checkpoint", "reason": "interval", "tools_since_last": 4 }
  ],
  "status": "running | done | error"
}
```

- **turn 开始：** 创建 assistant 占位消息（content 可为空），`status: running`。  
- **每个 SSE 事件：** append/update events，commit 或批量写。  
- **done：** 写入最终 content + `status: done` + turn_meta 统计。

**方案 B（完整版增量）：** 大 payload 写 `{data_path}/turns/{user_message_id}.jsonl`。

### 11.2 后端改动点

| 文件 | 改动 |
|------|------|
| `api/routes.py` | send/regenerate 流：turn 初建 placeholder；每 event 更新 summary |
| `services/storage.py` | 可选 `update_message_summary()` |
| `schemas.py` | `MessageResponse` 增加 `turn_trace` 或解析 summary 中的 events |
| `hooks/useMessagePairs.ts` | `buildMessagePairs` 从 summary 灌 `toolTrace`、`progressCheckpoint` |

### 11.3 前端改动点

| 文件 | 改动 |
|------|------|
| `useMessagePairs.ts` | 加载历史时还原 trace；流式与 DB 合并去重 |
| `MessagePairItem.tsx` | running turn 无 content 时仍显示 trace |
| `ToolTimeline.tsx` | 可选：从 summary 恢复时展示完整 detail |

### 11.4 验收用例（人工 + pytest）

1. 发任务触发 ≥2 次只读工具 → **刷新页面** → ToolTimeline 仍在。  
2. 流式过程中 assistant 区显示工具链，而非空白「思考中」-only。  
3. gate 等待审批时刷新 → 审批卡片状态可恢复（或至少 trace 显示 pending）。  
4. turn 完成后 events 仍在，Meta 芯片正常。  
5. 并发：同一 session 不应写乱两 turn 的 trace（已有 `SESSION_BUSY` 可依赖）。

---

## 12. F4 中间档实施清单（F6 之后）

| 文件 | 改动 |
|------|------|
| `agent/observation.py` | `slim_tool_result(name, raw_json) -> str` |
| `agent/loop.py` | `working.append` 前 slim；保留 raw 供 F6 写入 events.full |
| `services/agent_settings.py` | `observation_max_chars` 或类似 |
| `tests/test_observation.py` | list_dir/grep/read_file/shell 样例 |

**验收：** 固定剧本 loop 内 tool message 字符数上限；行为不劣化（狗粮剧本仍绿）。

---

## 13. 关键文件索引

```
backend/src/agent_window/
  agent/goal.py              # F1
  agent/checkpoint.py        # F2
  agent/loop.py              # F2/F3/loop
  services/shell.py          # F5
  services/agent_settings.py
  api/routes.py

backend/tests/
  test_turn_goal.py
  test_checkpoint.py
  test_gate_continue.py
  test_shell_python.py

src/
  App.tsx                    # 草稿、expandedUser、input dimmed
  components/UserMessageCard.tsx
  components/MessagePairItem.tsx
  components/ChatInput.tsx
  hooks/useMessagePairs.ts
  hooks/useWorkspaces.ts

restart-hal.sh               # setsid 重启脚本
docs/agent-window-roadmap.md # 路线图真源
CHANGELOG.md                 # [Unreleased] 条目
```

---

## 14. 路线图 §0.4 六条 — 当前满足情况

| # | 标准 | 状态 |
|---|------|------|
| 1 | 显式 Goal | ✅ 基本满足 |
| 2 | 多轮后能对照 Goal 说进度/阻塞 | ◐ F2 loop 内有；用户侧弱 |
| 3 | 成功/失败有结论或阻塞 | ◐ F3 有；F4 未做影响质量 |
| 4 | Reject/失败续环 | ✅ F3 |
| 5 | 轮次触顶软着陆对照 Goal | ✅ |
| 6 | 过程可监督、关键观察进轨迹 | ❌ **F6 未做** |

**§0.4 整体：约 4/6，未达 Foundation 成功标准（§7.4）。**

---

## 15. 结论（给下一棒 Agent）

1. **已完成：** F1/F2/F3/F5 + 机械环 + 大量 UI 壳 + User 卡片 + 草稿修复；**无 Foundation 完整版单项**。  
2. **最大缺口：** F6（信任/刷新）> F4（token/乱探）。  
3. **用户决策：** 做 **F6 中间 + F4 中间**（~7–8 人天，~68% 完整版体验）。  
4. **下一动作：** 按 §11 实施 F6 中间档；开工前可读 `TurnEvent` schema 与 placeholder 时机；完成后跑 F9 狗粮 + 全量 pytest + `npx tsc -b`。  
5. **纪律：** Window 与 CLI 共用后端；禁止只存在于前端的假能力（`AGENTS.md`）。

---

## 16. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-08-22 | 初版：汇总 F2 落地至 F4/F6 规划与全量能力对比对话 |
