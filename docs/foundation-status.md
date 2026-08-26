# Foundation 实施状态（Living Document）

> **本文档会随开发频繁更新。** 占比、档位、 backlog 勾选以本文为准。  
> 稳定参考（F4/F6 定义、三档方案、决策、执行顺序原则）见 [`foundation-f4-f6-plan.md`](./foundation-f4-f6-plan.md)。  
> 裁判标准：[`agent-window-roadmap.md`](./agent-window-roadmap.md) §0 / §7。

| 字段 | 值 |
|------|-----|
| **最后更新** | 2026-08-25 |
| **Foundation 整体** | **~66–73%**（相对 §7 完整版） |
| **中间路线目标** | **~68%**（已达成） |
| **当前焦点** | P1 真·链接附件 ✅；下一步 P2 / F7 |

---

## 如何维护本文档

在以下时机**必须**更新本文（可与 `CHANGELOG.md` `[Unreleased]` 同 PR）：

1. 完成或启动任一条 **F1–F9 / M2–M10** 能力项  
2. 某能力 **档位**（MVP / 中间 / 完整）或 **≈完整版 %** 发生变化  
3. **backlog** 中某项开始 / 完成 / 取消  
4. **§0.4 六条** 验收状态变化  

**不要**改 [`foundation-f4-f6-plan.md`](./foundation-f4-f6-plan.md) 里的百分比（该文件为稳定方案说明）。  
**不要**改 [`agent-window-roadmap.md`](./agent-window-roadmap.md) 里的 §7 表格来追踪进度（路线图保持「要做什么」；进度只在本文）。

### 更新记录

| 日期 | 变更摘要 |
|------|----------|
| 2026-08-25 | **P1 真·链接附件**：multipart 上传、`messages.attachments`、`read_attachment`、FE upload-on-select + `attachment_ids` |
| 2026-08-25 | #8 M6 审计 UI：会话/类型筛选、详情展开、跳转回放、JSON 导出；`GET /api/audit/sessions` + session audit |
| 2026-08-25 | #9 F8 Goal 变更留痕：`previous_turn_goal_from_messages` + `goal.change` 审计；SSE/trace `previous_goal`；目标条「已变更」 |
| 2026-08-25 | #7 M2 压缩保留 Goal：`preserve_goal` 写入摘要并重新注入；send/regenerate 先抽 Goal 再压缩 |
| 2026-08-25 | #5 大输出落 `session.data_path`（`file:` full_ref）+ ToolTimeline 展开全量 API；同日 F2 可见检查点回复 |
| 2026-08-24 | F9 人工收口：重启后 API 狗粮确认 Turn2 Goal 继承；工具/结论/刷新 trace 此前已绿；记「改 goal 后须重启」 |
| 2026-08-23 | F9 狗粮：固定两轮剧本 + `f9_scenario` 断言 + mock loop pytest；F1 续写继承（「好的，…」前缀） |
| 2026-08-22 | F4 中间档：4 类 formatter + 全局上限 + gate 摘要；loop 回灌 slim |
| 2026-08-22 | F6 中间档：TurnEvent schema、占位 assistant、增量 trace 落库、刷新恢复 + 轮询 |
| 2026-08-22 | 初版：自对话整理拆出；F1/F2/F3/F5 已实现；F4/F6 未做；认可中间路线 |

---

## 1. 快照（Foundation F1–F9）

| 项 | 状态 | 档位 | ≈完整版 |
|----|------|------|---------|
| F1 Turn Goal | ✅ 已实现 | 中间偏上 | ~75% |
| F2 进度检查点 | ✅ 已实现 | 中间偏上 | **~80%** |
| F3 失败续环 | ✅ 已实现 | 中间偏上 | ~80% |
| F4 观察瘦身 | ✅ 中间偏上 | 中间偏上 | **~80%** |
| F5 环境默认 | ✅ 已实现 | 中间 | ~65% |
| F6 中间态落库 | ✅ 中间偏上 | 中间偏上 | **~80%** |
| F7 探索收敛 | ❌ 未做 | — | 0% |
| F8 Goal 留痕 | ✅ 中间档 | 中间 | ~60% |
| F9 狗粮剧本 | ✅ 已收口 | 中间 | **~80%** |

**摘要：** §7 必做六条中 **6 条有实现**；中间路线 **~68% 目标已达成**。

### 能力占比汇总

| 能力块 | 当前 | 中间路线目标 | 完整版 |
|--------|------|--------------|--------|
| F6 中间态 | **~80%** | 70% | 100% |
| F4 观察 | **~80%** | 65% | 100% |
| F1 Goal | ~75% | 85% | 100% |
| F2 检查点 | **~80%** | 80% | 100% |
| F3 续环 | ~80% | 85% | 100% |
| F5 环境 | ~65% | 75% | 100% |
| **Foundation 整体** | **~65%** | **~68%** | 100% |
| 机械环 + 审批 | ~85% | — | ~95% |

---

## 2. 全功能现状 vs 完整版对照

### 2.1 档位图例

| 标记 | 含义 | ≈完整版 |
|------|------|---------|
| **完整** | 路线图主验收基本满足 | 90%+ |
| **中间** | 核心有，边角不全 | 60–75% |
| **MVP** | 能演示，缺关键场景 | 25–40% |
| **未做** | 基本没有 | 0% |

### 2.2 Foundation（§7）明细

| 项 | 现状 | 档位 | ≈完整版 | 已有 | 缺少 / 待补 |
|----|------|------|---------|------|-------------|
| F1 Turn Goal | ✅ | 中间偏上 | ~75% | extract/inject；短回复继承；SSE；UI「目标」；turn_meta.goal；**压缩保留** | F8；手动改 Goal |
| F2 进度检查点 | ✅ | 中间偏上 | **~80%** | 每 N 工具 + gate；SSE；设置；UI「检查点」+ **模型回复正文**（可折叠）；trace 落库 | 无结构化 progress/blocker 字段；多检查点列表可再增强 |
| F3 失败续环 | ✅ | 中间偏上 | ~80% | Reject/partial 结束；timeout/failed 续 1 次；pytest | 统一阻塞事实；CLI 话术 |
| F4 观察瘦身 | ✅ | 中间偏上 | **~80%** | 四类 formatter；6k 上限；gate 摘要；失败结构；**>8KB 落 data_path** | UI 多事件批量预取可再增强 |
| F5 环境默认 | ✅ | 中间 | ~65% | 裸 python → venv/python3 | 仅 python |
| F6 中间态 | ✅ | 中间偏上 | **~80%** | TurnEvent；占位；增量 trace；刷新恢复；**blob API 展开 full** | 流中双端合并；CLI trace |
| F7 | ❌ | 未做 | 0% | — | 见路线图 §7.2 |
| F8 Goal 留痕 | ✅ | 中间 | ~60% | `goal.change` 审计；SSE/trace `previous_goal`；UI「目标 · 已变更」 | 手动改 Goal；更细 diff |
| F9 狗粮 | ✅ | 中间 | ~80% | 固定剧本；API/pytest 收口；续写 Goal 继承（改 `goal.py` 后须重启） | 浏览器停/败占位未强制跑；§0.4 边角仍缺 |

### 2.3 机械环 + 审批门

| 项 | 档位 | ≈完整版 | 缺少 |
|----|------|---------|------|
| 工具 loop | 完整 | ~95% | MCP；provider 边角 |
| Diff / Hunk 部分应用 | 完整 | ~90% | CRLF 等未测边界 |
| Shell / Memory 审批 | 中间～中间偏上 | ~70–80% | 沙箱；与 trace 协同 |
| max_tool_iters + 软着陆 | 中间 | ~80% | F4 slim 已减 loop token |
| 写盘诚实化 | 中间 | ~70% | 误判；无 audit 事件 |
| Regenerate / 重试 | MVP | ~40% | 与 UI 编辑 user 语义未统一 |

### 2.4 MVP 收尾（§8）

| 项 | 档位 | ≈完整版 | 缺少 |
|----|------|---------|------|
| M2 压缩 | 中间 | ~70% | 超限折叠；**保留 Goal**（摘要钉住 + 系统块重注） |
| M3 Meta | 中间 | ~65% | 无 trace；无 per-tool |
| M5 诚实 Settings | 中间 | ~60% | 无能力盘点页 |
| M6 审计 | 中间偏上 | ~75% | 设置→审计可筛选/展开/导出；无时间轴可视化 |
| M7 资产盘点 | MVP | ~30% | 无健康面板 |
| M10 错误恢复 | 中间 | ~70% | 非全路径 |

### 2.5 前端 / 产品壳

| 项 | 档位 | ≈完整版 | 备注 |
|----|------|---------|------|
| Workspaces / This PC | 中间 | ~60–65% | Cursor 风侧栏 |
| User 消息卡片 | 中间 | ~55% | 4 行/sticky/展开；发送方案 B |
| 会话输入草稿 | 中间 | ~70% | 按 session |
| ToolTimeline | 中间 | ~65% | 依赖 F6 真源；刷新可恢复 |
| Diff/Shell 折叠 | 中间偏上 | ~80% | |
| Settings / ChatInput | 中间 | ~65–75% | F2 间隔已接；**P1 真·链接附件**（上传引用 + read_attachment，2026-08-25） |

### 2.6 CLI

| 项 | 档位 | ≈完整版 |
|----|------|---------|
| ask / status / gates | 中间 | ~65% |
| run --wait | 中间 | ~60% |
| Goal / trace 展示 | MVP | ~25% |

### 2.7 v1+（刻意未做）

Steering、事件流时间线、Preset、Task、Project OS、多 Agent 等 — **0%**。

---

## 3. 哪些算「最小完整版」

| 分类 | 是否算中间档「最小完整」 | 说明 |
|------|--------------------------|------|
| 审批门 + hunk + 工具 loop | **是** | 可日常改代码、跑命令 |
| F1 / F3 / F5 | **基本是** | 不挡 dogfood |
| F2 | **是** | loop + 可见对照进度正文（中间偏上） |
| **F4 / F6** | **是（中间档）** | 中间路线 ~68% 目标已达成 |
| Workspaces / User 卡片 | 产品壳 | 不替代 Foundation |
| 压缩 / 审计 | **基本是** | Goal 已保留；设置→审计可按会话回放 |

**§0.4「Foundation 能用」六条全满：尚未达到**（见 §5）。

---

## 4. Backlog 与进度

> 勾选状态随实施更新。顺序见 [`foundation-f4-f6-plan.md` §9](./foundation-f4-f6-plan.md#9-推荐执行顺序)。

### 4.1 近期 — 中间路线（已认可，~7–8 人天）

- [x] **Day 0** — 共用 `TurnEvent` schema（F4/F6 分流）
- [x] **F6 中间档** — 占位 assistant + 增量 events + API + 刷新恢复 ToolTimeline/检查点
- [x] **F4 中间档** — 4 类工具 formatter + loop + 全局上限 + pytest
- [x] **F9 狗粮** — 固定剧本 + 自动化断言（见 [`f9-dogfood-script.md`](./f9-dogfood-script.md)）

### 4.2 中期 — 中间 → 完整（+3–4 人天，按需）

| # | 内容 | 触发条件 | 状态 |
|---|------|----------|------|
| 5 | 大输出落 `data_path` + UI 展开 full | 常看长 log | ✅ |
| 6 | F2 展示模型检查点回复 | 需可见对照进度 | ✅ |
| 7 | M2 压缩保留 Goal | auto_compress 冲掉 Goal | ✅ |
| 8 | M6 审计 UI / 会话回放 | 运维需要 | ✅ |
| 9 | F8 Goal 变更留痕 | 频繁改意图 | ✅ |

### 4.3 远期 — v1+

- Steer / 事件流时间线（依赖 F6 真源）
- Preset 档位
- Task / Project OS / 多 Agent
- CLI trace、沙箱、审计导出

### 4.4 产品壳 backlog（非 Foundation）

> UI / 输入 / 侧栏等，与 F1–F9 分开排期。现状对照见 §2.5。

| # | 内容 | 现状 | 目标 / 验收 |
|---|------|------|-------------|
| P1 | **真·链接附件** ✅ | ~~内联全文~~ → 上传引用 | `POST/GET .../attachments`；消息 `attachments` JSON + `[附件]` 引用块；工具 `read_attachment`；FE 选文件即上传 chip + `attachment_ids` 发送；气泡可点下载 |
| P2 | 附件类型扩展 | 仅客户端识别文本后缀 | pdf/图片等 MIME + 大小上限；二进制走上传引用，可选 OCR/摘要 pipeline |
| P3 | 消息气泡内附件 UI | 发送后与普通文本混排 | 用户消息卡片区分「正文」与「附件块」（图标 + 文件名 + 链接） |

**真·链接附件 — 实施备忘（防忘）：** ✅ 已落地（2026-08-25）

- 后端：`multipart` 上传 → `session.data_path/attachments/`；`messages.attachments` JSON；`read_attachment` + ContextVar
- 前端：选文件 → 上传 → chip pending/ready/error；发送 `attachment_ids`；气泡附件卡片可下载
- 安全：大小 2MiB、扩展名白名单、路径隔离；virus scan 可后置
- **仅附件约束（2026-08-26）**：默认系统提示要求「（见附件）」且无明确写文件指令时只读 + 口头摘要，禁止自行落盘/写提取脚本
- 相关：`services/attachments.py`、`tools/attachment_tools.py`、`src/utils/chatAttachment.ts`、`src/App.tsx`

---

## 5. 路线图 §0.4 六条验收

| # | 标准 | 状态 |
|---|------|------|
| 1 | 显式 Goal 可展示、可注入 | ✅ 基本满足 |
| 2 | 多轮后能答进度/阻塞 | ✅ F2 检查点条展示模型进度说明（可折叠） |
| 3 | 成功有产物；失败有阻塞+事实 | ✅ F3 + F4；长 log 可经 data_path 展开 |
| 4 | Reject/失败作观察续环 | ✅ F3 |
| 5 | 触顶软着陆对照 Goal | ✅ |
| 6 | 过程可监督、观察进轨迹 | ✅ F6 + slim 回灌 + blob 全量 |

**未达标主路径：** §4.2 余项（F7 等）；#9 F8 中间档已落地。

---

## 附录：相关代码路径

| 领域 | 路径 |
|------|------|
| Loop | `backend/src/agent_window/agent/loop.py` |
| Goal / Checkpoint | `backend/src/agent_window/agent/goal.py`, `checkpoint.py` |
| 压缩 | `backend/src/agent_window/services/compress.py` |
| F4 观察瘦身 | `backend/src/agent_window/agent/observation.py` |
| TurnEvent / trace | `backend/src/agent_window/agent/turn_event.py`, `services/turn_trace.py`, `services/storage.py` (`write_turn_blob`) |
| SSE / 落库 / blob | `backend/src/agent_window/api/routes.py`（含 `GET .../blobs`） |
| 前端 trace | `src/hooks/useMessagePairs.ts`, `src/utils/turnTrace.ts`, `src/components/ToolTimeline.tsx` |
| 附件 P1 | `services/attachments.py`, `tools/attachment_tools.py`, `src/utils/chatAttachment.ts`, `src/App.tsx` |
| User 卡片 | `src/components/UserMessageCard.tsx` |
| 测试 | `backend/tests/test_turn_goal.py`, `test_checkpoint.py`, `test_gate_continue.py`, `test_shell_python.py`, `test_turn_trace.py`, `test_observation.py`, `test_f4_f6_integration.py`, `test_f9_dogfood.py`, `test_audit.py` |
| F9 狗粮 | `backend/src/agent_window/dogfood/f9_scenario.py`, [`docs/f9-dogfood-script.md`](./f9-dogfood-script.md) |
| 审计 UI | `src/components/AuditPanel.tsx`, `backend/src/agent_window/services/audit.py`, Settings → 审计 |
