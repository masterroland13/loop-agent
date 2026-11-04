# 提案：根 `AGENTS.md` 增补两节

> **状态：PROPOSAL。未合并。不要用本文件覆盖仓库根 `AGENTS.md`。**  
> 2026-11-04 已读根 [`AGENTS.md`](../../../AGENTS.md)（L0，测试纪律、提交纪律、模型防线、环境都在）。根文件本次未改。  
> 长说明在同目录 [`AGENTS-map.md`](AGENTS-map.md)。本提案只给可粘贴的短段。

## 为什么要动根文件

`docs/research/` 默认不注入。MCP 暂缓、不上 Electron、不焊 `loop.py`、`auto_compress` 默认关、不做 C6/C7，这五条要约束运行中的 Agent，就得出现在根 `AGENTS.md` 里。地图负责展开，根文件只留命令。

## 插在哪里

插在根文件「架构与文档权威」整节之后、「文档分层（L0–L3）」之前。测试、提交、模型防线、环境四节保持原文。已有的「勿按旧 F1–F9 清单开新旁路焊进 `loop.py`」留在权威节，下面这节把它写成可执行禁令。

## 建议粘贴的正文

```markdown
## 开工前读什么

1. 宪章 [`docs/architecture-charter.md`](docs/architecture-charter.md) §0–§1，以及 §4 功能落点。
2. 进度只看 [`docs/foundation-status.md`](docs/foundation-status.md)。
3. 只读和任务同题的 [`docs/plans/`](docs/plans/) 一篇。import 看 [`docs/layer-boundaries.md`](docs/layer-boundaries.md)。
4. 长地图（L3，不注入）：[`docs/research/overnight/AGENTS-map.md`](docs/research/overnight/AGENTS-map.md)。

## 禁止

- MCP、网页 fetch/search、PDF、多 Agent、Project OS、原生 Anthropic/Google 翻译器：路线图 §4.6 暂缓。
- 桌面壳是 `loop shell`（`shell/loop-window.c`）。不要引入 Electron。
- 新策略进 `LoopConfig` 钩子或对应层。不要焊进 `agent/loop.py`，不要按旧 F 编号开旁路。
- `auto_compress` 默认关（`agent_settings.DEFAULTS`）。不要改成默认开。
- 不要做 C6（工具批之后中途压）和 C7（regenerate 弃枝摘要）。
```

## 接受提案时

1. 把上面两节贴进根 `AGENTS.md`，不要整文件换成这份提案。
2. 在 `CHANGELOG.md` `[Unreleased]` 记一笔：根指令补上阅读顺序与五条禁止。
3. 本文件留在 `research/overnight/`，顶上状态改成「已合并，见根 AGENTS.md」，或随归档挪进 `archive/`。不要在 `docs/` 根再留一份副本。
