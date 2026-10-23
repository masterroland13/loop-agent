# docs/ 地图（人 + Agent）

> 归位规则见仓库根 [`AGENTS.md`](../AGENTS.md)「文档分层」。  
> **冲突裁决：** 宪章 > 路线图 > foundation-status > 其余 docs。

## 本层（权威 / Living，可常看）

| 文件 | 层 | 职责 |
|------|----|------|
| [`architecture-charter.md`](architecture-charter.md) | L1 | **架构真源** |
| [`layer-boundaries.md`](layer-boundaries.md) | L1 | 逻辑层与 import 方向 |
| [`agent-window-roadmap.md`](agent-window-roadmap.md) | L1 | 交付阶段与验收 |
| [`foundation-status.md`](foundation-status.md) | L2 | **唯一** Living 进度 / 收编表 |

## 子目录

| 目录 | 层 | 放什么 | 默认进 Agent 上下文？ |
|------|----|--------|----------------------|
| [`design/`](design/) | L3 | 定稿设计（未完成方案勿放这里） | 否，按需 read |
| [`archive/`](archive/) | L3 | **冻结**方案与考古；勿当进度源 | 否 |
| [`research/`](research/) | L3 | 竞品/笔记/调研报告 | 否 |
| [`dogfood/`](dogfood/) | L3 | 人工狗粮清单 | 否 |
| [`plans/`](plans/) | L2 | **进行中** 实现方案 | 否，任务相关再读 |
| `adr/`（可选，暂无） | L2 | 单条架构决策记录 | 否 |

### plans/

- [`session-model-profiles.md`](plans/session-model-profiles.md) — 会话级档案 + OpenAI 兼容预置（§4 手测已通过）

### design/

- [`v1-7-headless-cli-design.md`](design/v1-7-headless-cli-design.md) — 无头 CLI / Runtime

### archive/

- [`foundation-f4-f6-plan.md`](archive/foundation-f4-f6-plan.md)
- [`foundation-inventory-and-f4-f6-plan.md`](archive/foundation-inventory-and-f4-f6-plan.md)
- [`foundation-progress-and-f4-f6-plan.md`](archive/foundation-progress-and-f4-f6-plan.md)

### research/

- [`files-viewer-mvp.md`](research/files-viewer-mvp.md) — Files 浏览/编辑/保存 MVP：人用 API、沙盒、方案 A、分层与风险
- [`files-editor-office-scope.md`](research/files-editor-office-scope.md) — Office 范围调研（Excel/PPT 暂缓；Word/Markdown 体感与 docx 技术路线）
- [`app-packaging-gap.md`](research/app-packaging-gap.md) — 桌面 App 封装路径与现状差距
- [`api-key-storage.md`](research/api-key-storage.md) — API Key 存放、泄露面、网页/桌面与 Cursor·Cline 对照
- [`compaction-handoff-peers.md`](research/compaction-handoff-peers.md) — Codex/Cursor/Claude/Pi 压缩对照与本仓 handoff 取舍
- [`cursor-cot-activity-timeline.md`](research/cursor-cot-activity-timeline.md) — Cursor 式 CoT / Explored·Edited 调研与修订计划
- [`github-spec-kit-report.md`](research/github-spec-kit-report.md) — Spec Kit 参考（非开发主轴）
- [`pi-agent-ch06-messages.md`](research/pi-agent-ch06-messages.md)
- [`pi-agent-ch08-context-engineering.md`](research/pi-agent-ch08-context-engineering.md)

### dogfood/

- [`cot-s1-product-checklist.md`](dogfood/cot-s1-product-checklist.md) — **现行**产品狗粮全表（CoT S0–S1 / Goal OFF 主路径）
- [`section-7-compress-playbook.md`](dogfood/section-7-compress-playbook.md) — §7 压缩强制触发逐步剧本
- [`f9-dogfood-script.md`](dogfood/f9-dogfood-script.md) — Goal ON 旧 F9 剧本
- [`p2-f7-dogfood-script.md`](dogfood/p2-f7-dogfood-script.md) — P2/F7 专项

## 不要放在 docs/ 根的

- 调研长文 → `research/`
- 已完成/冻结计划 → `archive/`
- 狗粮剧本 → `dogfood/`
- 临时脚本与报告 → 仓库根禁止堆积；用 `scripts/` / `scripts/debug/`
