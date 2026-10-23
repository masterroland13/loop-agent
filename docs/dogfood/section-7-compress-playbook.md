# §7 压缩（Compaction）详细狗粮步骤

> 配套总表：[`cot-s1-product-checklist.md`](cot-s1-product-checklist.md) §7。  
> **目的：** 验证 `auto_compress` 真触发、摘要可读、会话可续聊；再核对「触发条件/摘要形态」与代码一致。  
> **预计：** 20–35 分钟（含准备）。跑完把结果勾回总表 7.1–7.3。

---

## 0. 压缩在本仓怎么工作（先读这 1 分钟）

代码：`backend/src/agent_window/services/compress.py` → `compress_messages_if_needed`。

| 条件 | 含义 |
|------|------|
| `auto_compress == true` | Settings 里必须**打开**；默认是关的 |
| `approx_tokens(messages) > context_limit - reserve_tokens` | 默认 `reserve_tokens=1024`，故阈值 ≈ `context_limit - 1024` |
| 触发后 | 把较旧消息折成一条 **compaction 摘要**（目标形态：**6 个 `##` 小节**），保留近端对话；可继续发消息 |

六小节名（英文标题）：

`Goal` · `Constraints` · `Progress` · `Key Decisions` · `Next Steps` · `Critical Context`

**不会触发的常见原因：**

1. `auto_compress` 仍是关  
2. `context_limit` 太大（如 8192），短会话永远到不了阈值  
3. 任务太短、工具太少，token 估不满  

---

## 1. 开跑前设置（必做）

| 步 | 操作 | 通过 |
|----|------|------|
| 1.1 | 重启后端（确保加载当前代码） | uvicorn 起来 |
| 1.2 | Settings → Agent / 治理相关：打开 **auto_compress** | 显示为开 |
| 1.3 | 把 **context_limit** 临时调到 **2048**（允许的最小值） | 保存成功；阈值 ≈ 2048−1024 = **1024** token |
| 1.4 | Settings → 模型生成参数：**max_tokens（单次回复最大长度）≥ 4096**（测完可恢复） | 避免长总结被输出上限截断，误判成「压缩坏了」 |
| 1.5 | Preset：**Trusted**；Goal：**OFF**（先测纯压缩；Goal pin 见 §3 可选） | — |
| 1.6 | 新建会话，绑好工作区 | — |
| 1.7 | 记下来：改之前的 `context_limit` / `auto_compress` / `max_tokens`，测完要**恢复** | — |

> UI 若只能看不能改某项：用 API/`agent_settings` 写盘亦可；测完恢复同样重要。

> **易混：** 回复在半句/半个反引号处戛然而止，多半是 **max_tokens**，不是压缩把答案砍断。压缩成功看 `turn_meta.compressed: true` / `compress_method` / `compress_preview`。

---

## 2. 强制触发压缩（对应总表 7.1）

目标：同一会话里堆够上下文，直到某一轮开始前/中出现压缩。

### 2.A 推荐剧本（复制发送）

> 灌上下文靠**多轮工具读盘**（tool 结果进 history），终稿用短结论文即可；不要逼「800/1500 字」长文，否则容易撞 max_tokens。

**回合 A1**（灌上下文，允许工具）：

```text
请只读、不要改文件。依次做：
1) list_dir 仓库根
2) read_file README.md（尽量多读）
3) grep 关键词 compress 或 auto_compress（docs 与 backend）
4) 用中文写一份短总结（约 200 字）：列出路径、函数名、触发条件要点即可。
```

**回合 A2**（继续灌）：

```text
继续只读：把 docs/architecture-charter.md、docs/foundation-status.md、docs/dogfood/cot-s1-product-checklist.md
能读的都读一段；再列 8～12 条要点（不要长文照抄）。
```

**回合 A3**（再灌 / 逼近阈值）：

```text
再读 backend/src/agent_window/services/compress.py 全文相关函数，
说明 compress_messages_if_needed / 六小节 / reserve_tokens（约 300 字）。仍不要改文件。
```

若 A3 后仍未压缩，再发 **A4**：

```text
再读 CHANGELOG.md 与 docs/README.md 各一段，然后用条目列出你读过的全部路径（不要长文）。
```

### 2.B 如何判断「已经压缩」

任选其一面即算 7.1 通过：

| 信号 | 看哪里 |
|------|--------|
| 会话里出现**摘要气泡/摘要消息**（或明显「压缩摘要」块） | 聊天区 |
| 之后发短问仍能答、不丢「当前工作区/任务」 | 行为 |
| `turn_meta`：`compressed: true`（常伴 `compress_method` / `compress_preview`） | **最硬证据** |

**不算 7.1 失败：**

- 某轮助手回复半截截断，但同轮或后续 meta 已有 `compressed: true`
- `compress_preview` 末尾带 `…`（预览故意截断，不是摘要坏了）

**记录：**

```
[7.1] 第几轮触发：A?
compressed / compress_method：
现象：
session：
```

**失败排查：**

- 仍不触发 → 确认 auto_compress；再确认 context_limit=2048；再多发一轮带大量 read_file 的回合  
- 半句截断 + 文末「max_tokens」黄字 → 提高单次回复最大长度；**不**据此判压缩失败  
- 触发后会话挂掉/空白 → 记阻断，附 session id  

---

## 3. 触发后抽查摘要形态（对应总表 7.3）

在已经出现压缩的会话里：

| 步 | 操作 | 期望 |
|----|------|------|
| 3.1 | 打开那条摘要（或导出/复制摘要正文） | 能看到多个 `## …` 标题 |
| 3.2 | 对照六节名 | 尽量齐：Goal / Constraints / Progress / Key Decisions / Next Steps / Critical Context（允许个别「（无）」） |
| 3.3 | 发：`用几句话列出压缩前读过的主要文件` | 应能答出 README、docs 至少一篇、compress.py 等（或摘要 Critical 中可见这些路径） |
| 3.4 | （可选）Goal ON 再跑一轮短压缩 | 摘要 Goal 节或后续仍带目标；总表写「Goal pin：是/否」 |

**记录：**

```
[7.3] 六节是否齐全：
抽查续聊是否记得关键文件：
```

---

## 4. 知识核对（对应总表 7.2，可与压缩同会话或新会话）

**不必**再强制触发压缩；验证模型+仓库事实：

```text
压缩何时触发？摘要长什么样？
请用仓库代码/文档回答：指出 compress_messages_if_needed 的条件
（auto_compress、context_limit、reserve_tokens），以及六小节标题。
只读，不要改文件。
```

| 核对点 | 期望（与代码一致） |
|--------|-------------------|
| 开关 | 必须 `auto_compress` |
| 阈值 | `tokens > context_limit - reserve`（默认 reserve=1024） |
| 摘要 | 6-section markdown |
| Activity | 可有 Explored；不应假装 Edited |

**记录：**

```
[7.2] 模型说的阈值是否提到 auto_compress + limit−reserve：是/否
六节名是否基本对：是/否
错在哪里：
```

---

## 5. 测完恢复（必做）

| 步 | 操作 |
|----|------|
| 5.1 | `auto_compress` 恢复你的日常值（常用：关，或你原本的开） |
| 5.2 | `context_limit` 恢复（常见 8192） |
| 5.3 | `max_tokens` 若为测 §7 临时调高，恢复原值 |
| 5.4 | 总表 §7.1–7.3 打勾 + 短备注 |

---

## 6. 与 §6.2 软着陆的区别（避免测混）

| | 压缩 §7 | 软着陆 §6.2 |
|--|---------|-------------|
| 开关/旋钮 | `auto_compress` + `context_limit` | `max_tool_iters`（下限 8） |
| 触发物 | **上下文 token** | **工具轮次** |
| 结果 | 摘要消息 + 续聊 | 分节「未完成/建议下一步」 |

测 §7 时主要靠**多轮 read/grep 把 tool 结果堆进 history + 低 context_limit**；不要靠「逼模型写超长终稿」。

---

## 7. 结果模板（可贴回总表或聊天）

```
日期：2026-09-09
context_limit 测试值：2048（测完已恢复：请确认）
auto_compress：开（测完已恢复：请确认）
max_tokens 测试值：曾建议 ≥4096（测完已恢复：请确认）

7.1 触发：通过 — 约 A3；compressed=true / method=llm；compress_preview 含六节
7.2 知识核对：通过 — 探索轮已对齐 auto_compress + limit−reserve + 六节名
7.3 摘要形态 + 续聊：通过 — 六节齐；Critical 路径清单；续聊能列 README / compress.py / docs
      备注：初测 Constraints/Key Decisions/Next 有复读；已做 handoff + 小节分工代码收紧

阻断：无
非阻断：A1/A3 曾 max_tokens 半句截断（非压缩失败）；摘要小节分工建议新会话 smoke
```
