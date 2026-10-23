# GitHub 需规管理（Spec Kit）使用说明与对本项目的优化报告

| 字段 | 值 |
|------|-----|
| **主题** | GitHub Spec Kit / Spec-Driven Development（规范驱动开发） |
| **官方仓库** | [github/spec-kit](https://github.com/github/spec-kit)（MIT） |
| **文档站** | [github.github.io/spec-kit](https://github.github.io/spec-kit/) |
| **中文 README** | [README.zh-CN.md](https://github.com/github/spec-kit/blob/main/README.zh-CN.md) |
| **本报告日期** | 2026-08-29 |
| **适用仓库** | Loop Agent（原 Hal Agent） |

> **一句话：** GitHub Spec Kit 把「需求规格」做成仓库里可版本化、可被 Agent 执行的制品（spec → plan → tasks → implement），再用 Issues/Projects 跟踪。对本项目最大的价值是：**把路线图/宪章/聊天决策，收成按功能编号的可验收规格**，减少 vibe coding 与文档漂移。

---

## 1. 它是什么

### 1.1 概念

**规范驱动开发（Spec-Driven Development, SDD）** 颠倒传统顺序：

| 传统 | SDD |
|------|-----|
| 代码是真源；规范写完就丢 | **规范是真源**；计划、任务、实现从规范派生 |
| 人写 PRD → 人拆任务 → 人/Agent 写码 | Agent 按固定阶段：constitution → specify → plan → tasks → implement |
| 「先写再说」易跑偏 | 阶段边界人工审阅；验收标准先于代码 |

GitHub 官方工具包 **Spec Kit**（CLI 名 `specify` / 包名 `specify-cli`）提供：

- 项目模板与 `.specify/` 目录结构  
- 面向各 AI 助手的斜杠命令（`/speckit.*`）  
- 可选：把 `tasks.md` 转成 **GitHub Issues**，社区扩展可同步 **GitHub Projects v2**

相近生态（了解即可，本报告以 Spec Kit 为主）：

| 工具 | 特点 | 对本项目 |
|------|------|----------|
| **GitHub Spec Kit** | 全流程、多 Agent 集成、Issues 桥 | 主推候选 |
| **OpenSpec** | 更轻；用「变更 delta」演进存量规格 | 棕地友好，可作轻量备选 |
| **AWS Kiro** | IDE 内建 SDD | 绑 AWS 生态，不优先 |

### 1.2 解决什么问题

1. **需求只在脑中 / 聊天里**：跨会话、跨 Agent 无法复用。  
2. **实现偏离意图**：Agent 直接写码，缺「做什么 / 为何做」的冻结文档。  
3. **任务不可追溯**：没有 Issue/勾选清单，难回答「做到哪了、还剩什么」。  
4. **规范与代码双轨漂移**：路线图很厚，但单次改动没有对应规格切片。

### 1.3 实际交付物长什么样

每个功能通常一个目录（示意）：

```text
specs/
  001-session-tree-regenerate-ui/
    spec.md      # 做什么、为何做、用户故事、验收（尽量技术无关）
    plan.md      # 怎么做：栈、模块、数据、风险（对齐 constitution）
    tasks.md     # 可勾选任务，按故事/依赖排序
.specify/
  memory/constitution.md   # 项目级硬约束（测规、分层、Preset…）
  templates/               # 规格/方案/任务模板
```

可选：`/speckit.taskstoissues` → 仓库 Issues；扩展 → Projects 看板。

---

## 2. 使用说明（操作手册）

### 2.1 环境要求

- Linux / macOS / Windows（PowerShell 脚本已支持，不必依赖 WSL）  
- Python 3.11+  
- [uv](https://docs.astral.sh/uv/)（推荐）或 pipx  
- 任一支持的 AI 编码助手（Cursor / Copilot / Claude Code / Pi 等；完整列表见官方 integrations）  
- Git（启用 git 扩展或需要 Issues 时）

### 2.2 安装 Specify CLI

**推荐：锁定 Release 标签从源安装**

```bash
# 将 vX.Y.Z 换成 https://github.com/github/spec-kit/releases 最新 tag（保留前缀 v）
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@vX.Y.Z
specify version
specify self check   # 只读：是否有新版本
```

**或从 PyPI：**

```bash
uv tool install specify-cli
# 或：pipx install specify-cli
```

### 2.3 初始化（存量仓库用「当前目录」）

绿地：

```bash
specify init my-project --integration copilot
cd my-project
```

**本仓库（已有 Loop Agent）建议：**

```bash
cd "/home/caapap/agent window"   # 或你的实际仓库根
specify init . --integration cursor --script sh
# 若 CLI 对 Cursor 的 integration 名不同，用：
# specify integration list
# specify init . --integration <列出的名称> --ignore-agent-tools
```

初始化后常见结构：

- `.specify/` — 模板、脚本、constitution 记忆  
- 助手侧斜杠命令或 skills（如 `.cursor/` / `.github/` 等，视 integration）  
- 之后功能落在 `specs/NNN-name/`

> **与现有文档并存：** 不要用 Spec Kit 覆盖 `docs/architecture-charter.md`、`AGENTS.md`。应把宪章/AGENTS **浓缩进 constitution**，Specs 只描述**增量功能**。

### 2.4 标准工作流（必走阶段）

```text
constitution → specify → clarify（可选）→ plan → tasks
        → analyze（可选）→ checklist（可选）→ implement
        → taskstoissues（可选）→ converge（收尾对照）
```

| 步骤 | 命令 | 你该审什么 | 不要做什么 |
|------|------|------------|------------|
| 1. 准则 | `/speckit.constitution` | 测规、分层、Preset、提交纪律是否写进 | 不要与 AGENTS/宪章矛盾 |
| 2. 规格 | `/speckit.specify` | **做什么/为何做**、用户故事、验收 | 不要在此锁死框架细节 |
| 3. 澄清 | `/speckit.clarify` | 歧义问答是否写回 spec | 跳过会导致 plan 瞎猜 |
| 4. 方案 | `/speckit.plan` | 模块落点、API、测试策略 | 勿违背分层/宪章 |
| 5. 任务 | `/speckit.tasks` | 粒度、依赖、可否独立验收 | 巨型「一坨任务」 |
| 6. 分析 | `/speckit.analyze` | spec/plan/tasks/constitution 一致性 | 有冲突别硬 implement |
| 7. 清单 | `/speckit.checklist` | 安全/可观测/回归等预检 | 当形式主义走过场 |
| 8. 实现 | `/speckit.implement` | 每任务对照验收；pytest/tsc | 跳过门禁乱改 loop |
| 9. Issues | `/speckit.taskstoissues` | Issue 标题/标签是否可跟踪 | 无 GitHub remote 时跳过 |
| 10. 收敛 | `/speckit.converge` | 代码 vs 规格缺口是否追加任务 | 假装 100% 完成 |

**人工纪律（官方也强调）：在阶段边界审阅，禁止 spec 直接跳到写码。**

### 2.5 与 GitHub Issues / Projects

| 能力 | 做法 |
|------|------|
| Issues | `/speckit.taskstoissues` 把 `tasks.md` 拆成 Issue |
| Projects v2 | 社区扩展 [spec-kit-tasks-to-project](https://github.com/mancioshell/spec-kit-tasks-to-project)：publish / sync 看板 |
| 追溯 | Issue ↔ `specs/NNN-...` ↔ PR；分支名可带编号如 `spec/012-...` |

本仓库若暂无 GitHub remote，可只保留 `specs/` + `tasks.md` 勾选，效果仍在；有 remote 后再开 Issues。

### 2.6 棕地（已有大仓）注意点

1. **先 constitution，对齐现有权威文档**，再开第一个小规格（勿一上来全仓重写）。  
2. **一个功能一个 `specs/NNN-...`**，不要把整份路线图塞进一个 spec。  
3. 行为变更时更新对应 `spec.md`（或开新 delta），避免「代码已改、规格仍旧」。  
4. Spec Kit 自身升级与功能制品演进分开（官方 evolving-specs 指南）。

### 2.7 验收标准写法建议（EARS）

规格里每条验收尽量可测，例如：

- **When** 用户在 YOLO Preset 下提出改文件，**the system shall** 不弹出 Diff 等待卡且文件已写入。  
- **When** Goal 模式 OFF，**the system shall not** 注入 Turn Goal 条带。  
- **If** `propose_memory` 将使 USER.md 超过硬上限，**then** 返回 `MEMORY_FULL` 且不静默截断。

这与本仓库「断言行为、不测内部变量」的 pytest 纪律一致。

---

## 3. 调研报告：能力边界与风险

### 3.1 优点

| 优点 | 说明 |
|------|------|
| Agent 中立 | Cursor / Copilot / Claude / Pi 等可共用同一套规格 |
| 版本化真源 | `specs/` 进 Git，可 review、可 blame |
| 阶段闸门 | 降低「一句话直接改 loop」的失控率 |
| Issues 桥 | 产品跟踪与实现任务对齐 |
| 可扩展 | extensions / presets / bundles 适配组织流程 |

### 3.2 局限与风险（批判性）

| 风险 | 说明 | 缓解 |
|------|------|------|
| **仪式过重** | 小修小补也跑全流程会拖慢 | 仅「中型以上功能 / 架构向改动」启用；hotfix 仍走现有 AGENTS 纪律 |
| **Markdown 膨胀** | 一次生成大量文档，审阅成本转给人 | 强制阶段审；`/analyze`；拒绝空话验收 |
| **与现文档双源** | charter / roadmap / foundation-status / specs 四处写 | constitution 只引用宪章；roadmap 管阶段；specs 管增量 |
| **假完成** | Agent 勾完 tasks 但行为未测 | 坚持失败复现测试 + 人工狗粮步骤 |
| **工具预览态** | Spec Kit 仍快速迭代，命令名可能变 | pin CLI 版本；跟官方 changelog |
| **不等于项目管理** | 不能替代路线图战略决策 | 继续用 `agent-window-roadmap` + `foundation-status` |

### 3.3 和「GitHub Issues 管需求」的区别

| | 仅 Issues | Spec Kit +（可选）Issues |
|--|-----------|-------------------------|
| 需求深度 | 标题+描述，易碎 | 完整 spec/plan/tasks 制品 |
| Agent 可执行性 | 弱（上下文靠粘贴） | 强（仓库内固定路径） |
| 技术/产品分离 | 常混在 Issue 里 | specify（产品）与 plan（技术）分阶 |
| 看板 | Projects 原生 | 需 taskstoissues / 扩展 |

**结论：** Issues 适合跟踪与指派；**规格本体应在 `specs/`**。两者叠加最好。

---

## 4. 结合本项目：能带来哪些优化与提升

### 4.1 现状痛点（对照仓库真实状态）

| 现状 | 表现 | Spec 能补什么 |
|------|------|----------------|
| 权威文档多 | 宪章、路线图、foundation-status、多份 foundation 计划、AGENTS | 增量改动有独立 `spec.md`，避免只改聊天不改文档 |
| A0–A4 已完成 | 焦点转向 UI/收编/产品层 | 每项「下一项」用规格冻结验收，再实现 |
| Agent 日写代码 | Cursor/本 Window 都在改仓 | 同一 `specs/` 约束不同会话/不同 Agent |
| 进度靠 Living 表 | `foundation-status` 勾选好，但缺「本功能用户故事」 | tasks ↔ status 条目可交叉引用 |
| 测试纪律强 | pytest 行为断言 | 验收标准直接映射测试名/用例 |
| Project OS 远期 | 路线图 B* / §愿景 | 阶段出口产物 ≈ 规格里的 exit criteria |

### 4.2 映射：Spec Kit 概念 ↔ Loop Agent 文档

| Spec Kit | 本仓库应对 |
|----------|------------|
| `constitution.md` | **浓缩** `AGENTS.md` + 宪章硬约束（分层、Goal 默认 OFF、Preset、测规、禁止焊 loop） |
| `specs/NNN/spec.md` | 单功能需规（如「regenerate sibling 切支 UI」） |
| `plan.md` | 落点：`src/` / `backend/src/...`、API、是否动 loop |
| `tasks.md` | 可执行勾选；可与 foundation-status「下一步」对齐 |
| `/taskstoissues` | 可选公开跟踪 |
| `/converge` | 大功能收尾：对照规格扫缺口 |

**不要替换：**

- `architecture-charter.md` — 架构真源  
- `agent-window-roadmap.md` — 阶段与愿景  
- `foundation-status.md` — Living 进度  

**关系式：**

```text
宪章 / 路线图（战略与边界）
    ↓ 写入
constitution（给 Agent 的硬约束摘要）
    ↓ 每次增量
specs/NNN（本功能需规 + 方案 + 任务）
    ↓ 实现后
CHANGELOG + foundation-status（进度与发布说明）
```

### 4.3 预期收益（量级估计，非 KPI 承诺）

| 维度 | 预期提升 | 理由 |
|------|----------|------|
| **返工 / 跑偏** | 中大型功能返工约 **减 30–50%** | 先澄清验收再写码；analyze 挡不一致 |
| **跨会话连续性** | 上下文重建时间约 **减半** | 规格在仓，不靠聊天摘要 |
| **验收清晰度** | 狗粮步骤可从规格直接勾选 | 与「行为断言」同构 |
| **多 Agent 一致性** | 明显提升 | Cursor / Loop / CLI 读同一 `specs/` |
| **可审计叙事** | 「凭什么改」可指向 spec+PR | 对齐企业 Demo→生产、审计叙事 |
| **小改动吞吐** | **可能下降 10–20%** 若滥用全流程 | 故必须设启用门槛（见 §5） |

### 4.4 对本项目「特别有价值」的用例（建议优先规格化）

按 `foundation-status` 当前焦点与路线图，优先：

1. **Regenerate sibling 切支 UI**（当前焦点）— 用户故事、树可视化验收、非目标（不做完整 git UI）  
2. **收编债**（F3/F4/F6/Gate 等未完全收编项）— 每项一个小 spec，防再次焊回 `loop.py`  
3. **MEMORY.md / Provider 记忆层**（宪章 §3.5 后置）— 边界与 Preset 写入规则先写清  
4. **会话级 model profile**（A2 后置）— API/UI/默认值验收  
5. **B* Task / Project OS 试点** — 严禁无规格直接开表；用 spec 定义最小闭环  

### 4.5 对本产品本身的启发（可选远期）

Loop Agent 路线图里的 **Skill + Harness + 出口产物**，与 SDD 同构：

| SDD | Loop 产品概念 |
|-----|----------------|
| spec | 阶段/工作项的出口定义 |
| checklist | Harness 门禁 |
| tasks | Agent 可执行步骤 |
| converge | 对照目标收工（Goal ON） |

短期不必在产品里「内嵌 Spec Kit」；先 **用 Spec Kit 管好本仓开发**，跑通后再考虑「项目内 specs/ 作为工作区一等公民」。

---

## 5. 采纳建议（怎么做、做到哪）

### 5.1 推荐策略：**轻量接入，非全盘宗教**

| 做法 | 建议 |
|------|------|
| 是否立刻全仓 Spec Kit 化 | **否** |
| 是否建立 constitution + 首个试点 spec | **是** |
| 启用门槛 | 预估 **≥0.5 人日**、或动 loop/分层/API 契约、或需狗粮验收的功能 |
| 不启用 | 文案、纯样式、单测补强、明确 hotfix |
| Issues | 有 GitHub remote 再建；本地先 `tasks.md` |
| OpenSpec | 若嫌 Spec Kit 重，可用其「变更 delta」思路，仍保持 `specs/` 真源 |

### 5.2 两周试点切片

| 日 | 动作 |
|----|------|
| D1 | 安装 `specify-cli`（pin 版本）；`specify init .`（不覆盖 AGENTS/宪章） |
| D1–D2 | `/speckit.constitution`：粘贴/精炼 AGENTS+宪章硬约束；人工审 |
| D2–D3 | 为「regenerate sibling 切支 UI」跑 specify → clarify → plan → tasks → analyze |
| D4–D8 | implement + pytest/tsc + 人工狗粮；更新 CHANGELOG + foundation-status |
| D9–D10 | 回顾：仪式是否过重、模板是否要 overrides；决定是否 `/taskstoissues` |

### 5.3 明确不做（防走偏）

- 不删除或降级宪章/路线图，改由 spec「一家独大」  
- 不把 constitution 写成与 YOLO/Goal OFF 产品原则相反的「强审批教条」  
- 不要求每个 5 分钟改动都走 `/implement` 全流程  
- 不在 A0–A4 已完成的情况下，用 SDD 名义重开「大重构周」而无验收  

### 5.4 成功标准（试点结束可回答）

1. 至少 **1** 个合并功能带有完整 `specs/NNN/{spec,plan,tasks}.md`  
2. 该功能的 pytest/人工步骤能在 spec 验收节打勾  
3. constitution 与 `AGENTS.md` **无冲突**（冲突以宪章为准并回写 constitution）  
4. 团队主观：返工感下降，且小改动未被明显拖慢  

---

## 6. 快速命令速查

```bash
# 安装与自检
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@vX.Y.Z
specify version
specify self check

# 存量仓初始化（integration 以 specify integration list 为准）
specify init . --integration cursor --script sh

# 助手内（名称以安装结果为准）
/speckit.constitution
/speckit.specify ...
/speckit.clarify
/speckit.plan ...
/speckit.tasks
/speckit.analyze
/speckit.checklist
/speckit.implement
/speckit.taskstoissues
/speckit.converge
```

升级：

```bash
specify self upgrade --dry-run
specify self upgrade
# 或锁定：specify self upgrade --tag vX.Y.Z
```

---

## 7. 参考链接

- 仓库：https://github.com/github/spec-kit  
- 中文说明：https://github.com/github/spec-kit/blob/main/README.zh-CN.md  
- 安装：https://github.github.com/spec-kit/installation.html  
- Microsoft 介绍：https://developer.microsoft.com/blog/spec-driven-development-spec-kit/  
- Projects 扩展：https://github.com/mancioshell/spec-kit-tasks-to-project  
- 本仓权威：`docs/architecture-charter.md`、`docs/agent-window-roadmap.md`、`docs/foundation-status.md`、`AGENTS.md`

---

## 8. 结论

GitHub 上的「需规管理」在 2026 年的主流落地形态，就是 **Spec-Driven Development + Spec Kit（规格进仓库）+ 可选 Issues/Projects（跟踪）**。

对 **Loop Agent** 而言：

- **值得做**：用 constitution 对齐现有纪律，用 `specs/NNN` 管增量功能——尤其当前 UI/收编/记忆后置项。  
- **收益最大处**：跨会话一致性、验收可测、减少焊 loop 式跑偏、为 Project OS 预演「出口=规格」。  
- **代价**：仪式成本；必须设启用门槛，并坚持「宪章/路线图仍是战略真源」。  

**建议下一步：** 不改产品架构，先完成 §5.2 试点（切支 UI 一条规格闭环）；试点成功后再写进 `AGENTS.md` 一句「中型功能先有 specs/ 再实现」。
