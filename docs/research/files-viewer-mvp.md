# Files 浏览 / 编辑 / 保存 MVP（调研）

> L3 research。进度以 `foundation-status.md` 为准；实现按宪章分层，不改 Agent 门控管线。

## 为什么要单独 API

前端无法直读本机磁盘。Agent 的 `list_dir` / `read_file` / `propose_edit` 是 **模型工具通道**（观察瘦身、行号窗口、审批门）。人用 Files 面板需要 **给人用的 HTTP**：裸文本、整文件编辑、直接保存。

二者共用沙盒（`resolve_in_workspace`），入口分离。

## 沙盒干什么

`loop-coding` 的 workspace 沙盒：路径限制在 workspace 根内；拒逃逸；list 跳过噪音目录；读拒二进制；有大小上限。Files API **必须**走同一闸门。勿与 `/api/workspace/browse`（This PC 绝对路径选目录）混淆。

## 方案 A（已定）

| 角色 | 写盘路径 |
|------|----------|
| 人（FilesPanel） | `PUT .../files/write` → 直接写盘 |
| Agent | 仍只走 `propose_edit` → Diff 门控 |

不把用户保存塞进审批心智。

## 分层

```text
loop-window：routes + FilesPanel / SurfaceHost
loop-coding：workspace.list_directory + read_text_file + write_text_file（新建；不改 Agent read_file）
loop-agent-core / loop-ai：零改动
```

## 风险

1. Agent `read_file` 带 `N|` 行号 — 人用读必须另函数，禁止改工具返回形态。  
2. CRLF / 无末尾换行 — 尽量按缓冲原样写回。  
3. 与 pending `propose_edit` 同文件 — MVP：后写覆盖 + UI toast；不自动拒。  
4. 大文件 — 超限只读或拒绝编辑并提示。

## 扩展

SurfaceHost：`surface: 'none' | 'files'`，类型上预留 `terminal` / `browser`，本里程碑不实现。

## 非目标

真 Terminal PTY、Browser、全文搜索、图片编辑、用户保存走 Diff 审批。
