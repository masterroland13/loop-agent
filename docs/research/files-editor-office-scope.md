# Files 编辑器范围调研（Office / 保存体验）

> L3 research。Excel / PPT **暂缓**；当前交付焦点：**Markdown + Word（.docx）** 的展示、编辑、保存体感。  
> 进度 Living 见 [`foundation-status.md`](../foundation-status.md)；人用写盘方案 A 见 [`files-viewer-mvp.md`](files-viewer-mvp.md)。

## 1. 背景

- Files 面板走 **方案 A**：`PUT /api/workspace/files/write` 直接写盘；Agent 仍只 `propose_edit`。
- 现状（调研时）：仅 **UTF-8 文本**；前 4KB 含 `\0` 判为 `BINARY`（**xlsx / pptx / docx 等 ZIP 容器无法当文本打开**）。
- 保存：**乐观锁**（`mtime_ns` 字符串 + `base_content`）；入口以 **Ctrl+S** 与关标签对话框为主，无显式保存按钮与自动保存。

## 2. Office 格式结论（暂缓项）

| 格式 | 暂缓原因 | 若未来要做 |
|------|----------|------------|
| **Excel (.xlsx)** | 需二进制 API + 表格模型；公式/样式/图表保真成本高 | SheetJS / Luckysheet + `raw` 读写；MVP 2–3 周 |
| **PPT (.pptx)** | 真编辑≈幻灯片产品；应用内保真编辑宜 OnlyOffice 或外链打开 | 只读：LibreOffice→PDF 或缩略图，1–2 周 |
| **老格式 (.xls / .ppt)** | 需转换链 | 与 xlsx/pptx 分期，不建议与 docx 同期 |

**决策：Excel / PPT 本期不做**，避免与「文本类文档体感」争抢带宽。

## 3. Word（.docx）可行路径

| 方案 | 优点 | 缺点 |
|------|------|------|
| **docx ↔ HTML（mammoth + htmldocx）** | 纯 Python 依赖、可嵌预览 | 复杂版式/页眉页脚/批注易丢 |
| **docx ↔ Markdown（pandoc）** | 作者友好 | 依赖系统 pandoc，部署重 |
| **仅预览 + 系统打开** | 保真 | 无法在面板内改 |

**本期选型：HTML 中间表示**

- 读：`mammoth` → HTML，`encoding: docx-html`。
- 写：`htmldocx` + `python-docx` 回写 `.docx`。
- 编辑：源码（HTML）+ 预览（渲染）；与 Markdown 的 Source/Preview 心智一致。
- **非目标**：`.doc`、宏、修订、嵌入 OLE。

## 4. Markdown

- 已有 Source / Preview + `react-markdown`。
- 缺口：保存入口不明显、无自动保存、磁盘被外部修改无提示、预览态不可编辑（需引导回源码）。

## 5. 保存与冲突（文本 / HTML 共性）

| 能力 | 说明 | 优先级 |
|------|------|--------|
| 工具栏保存 + Ctrl+S 提示 | 降低「找不到保存」 | P0 |
| 标签脏标记 | 圆点/星号 | P0 |
| 自动保存 | `off` / 失焦 / 定时；默认失焦或关 | P1 |
| 外部变更 | 活动标签轮询 `mtime` + `focus` 检查 | P1 |
| 冲突 | 已有 `base_content`；对话框 + 顶栏「重新加载」 | 已有，补强文案 |
| Save All | 多标签 | P2 |
| 与 pending `propose_edit` | 后写覆盖 + toast（MVP 已定） | P2 提示 |

## 6. 工作量粗算（Markdown + docx 本期）

| 块 | 人日 |
|----|------|
| 调研报告 + 索引 | 0.5 |
| 后端 docx 读/写 + pytest | 2–3 |
| Files 工具栏 / 自动保存 / 外部变更 | 2–3 |
| docx 双视图编辑器 UI | 1–2 |
| MD 文案与预览引导 | 0.5 |
| **合计** | **约 6–9 人日** |

## 7. 风险

1. **docx 往返保真**：需在 UI 标明「简单文档」；复杂 Word 建议外部编辑。  
2. **HTML 冲突比对**：磁盘再转 HTML 可能与内存空白规范化不一致 → 以 mtime + 尽力比对为主。  
3. **包体积**：mammoth 仅后端；前端不增 Office 大包。  
4. **大文件**：仍受 `MAX_EDITOR_BYTES`（约 2MB）限制。

## 8. 实施顺序（已采纳）

1. 报告入 `research/`（本文）。  
2. 后端 `.docx` 读写 + `encoding` 字段。  
3. FilesPanel：保存栏、脏标记、自动保存、外部变更、MD/docx 视图统一。  
4. CHANGELOG + `foundation-status` 一行。
