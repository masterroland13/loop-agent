# Skills 拉模式与 C8 `TASK.md` 路径提示

> L3 调研。对照**已经在树上的** Skills 拉模式，和 [`docs/plans/context-loop-strengthen.md`](../../plans/context-loop-strengthen.md) 里**还没做**的 C8。  
> **本文不施工。** 不改产品代码，不实现 C8，不改 `auto_compress`（默认仍关），不展开 C6、C7、N2。  
> 代码锚点对应当前树。函数名是准的；行号会漂，以符号为准。

## 1. 问题

两件事都是「系统提示里放轻的东西，正文等模型自己去读」：

| | 存什么 | 系统提示里有什么 |
|--|--------|------------------|
| **Skills（已落地）** | 可复用的做法：怎么审查、怎么跑某类流程 | 已激活技能的 id、名称、描述 |
| **C8（提议）** | 这一份工作区上的长任务单：做到哪、下一步、关键路径 | 一条路径，外加一句「长任务先读再改」 |

C8 方案原文只有一段。这里把那段收成**路径提示注入**：提示里出现路径和读取指令，`TASK.md` 正文留在工作区文件里，由现有 `read_file` 拉取。全文推进 system 是另一条路（本仓的 `AGENTS.md` / `SYSTEM.md` 已经这么做），不是 C8。

## 2. 已落地：Skills 拉模式

宪章 M08 把拉模式写成：system 只放清单，模型用 read 取全文。A4 清单把这件事标成完成（[`docs/foundation-status.md`](../../foundation-status.md) §4：「Skills catalog 进 system（非全文 SKILL.md）」）。下面是代码实际在做的事。

### 2.1 发现

实现：`backend/src/agent_window/services/skills.py`。

- 目录是工作区根下的 `skills/<skill_id>/`（`skill_dir()`）。没有绑定工作区，或 `skills/` 不存在，发现结果是空列表。
- 每个技能只认该目录**第一层**。文件名顺序写死在 `_SKILL_FILENAMES = ("SKILL.md", "README.md")`：有 `SKILL.md` 就用它，否则退到 `README.md`。
- 可选 frontmatter 是简单的 `key: value` 行（`_parse_frontmatter`），不是完整 YAML。`name`、`description` 会被读走。
- `discover_skills()` 给人和 API 用：id、name、description、相对路径、正文前 200 字 `preview`。样例在 `skills/code-review/SKILL.md`（name「Code Review」，描述是审查时要写安全、兼容和测试建议）。
- 正文上限常量 `MAX_SKILL_CHARS = 12_000` 只约束 `read_skill()` 和合并后的 `AGENTS.md`。它**不**出现在系统提示的技能清单上，因为清单本来就不带正文。

### 2.2 激活

- 持久化键是 `active_skills`，默认 `[]`（`backend/src/agent_window/services/agent_settings.py` 的 `DEFAULTS`）。空名单等于模型看不到任何技能。
- `set_active_skills()` 会保存尚不存在的 id，方便人先点激活、后补文件。注入时文件缺失会被跳过，不会因此造出一个 `SKILL.md`。
- HTTP：`GET /api/skills`、`PUT /api/skills/active`（`backend/src/agent_window/api/routes.py` 的 `list_skills_endpoint` / `set_active_skills_endpoint`）。激活写审计 `skill.activate`。
- 设置页开关在 `src/components/SettingsPanel.tsx`（skills 一节）和 `src/hooks/useSettings.ts` 的 `toggleActiveSkill`，经 `src/api/agent.ts` 打到上面的 PUT。人展开一条技能时看的是 description 加那 200 字预览。这是给人看的，不是进模型的通道。

### 2.3 清单怎么进系统提示

`skill_context_blocks()` 的注释写明了契约：`AGENTS.md` 全文注入；技能只注入 name + description；模型决定用的时候再去读 `SKILL.md`。

已激活且文件真实存在时，每一行是：

```text
- code-review: Code Review — Review code for quality (load via tools when needed)
```

没有描述时，破折号后面是 `(load via tools when needed)`。整块标题是：

```text
## Available Skills (catalog; use skill tools / read_file to load full SKILL.md)
```

`backend/src/agent_window/api/routes.py` 的 `_system_prompt()` 每轮把块拼在末尾：`base` + `memory_block` + `skills_section`。技能块**不是**会话冻结快照。`USER.md` / `MEMORY.md` 在有 `session_id` 时走冻结副本；技能清单每次调用都重新读盘。

清单里**没有**路径。`discover_skills()` 算了相对路径，但 `skill_context_blocks()` 丢掉了。模型若要读全文，得自己把 id 对上 `skills/<id>/SKILL.md`（或退路 `README.md`）。

未激活的技能不会出现在这块里。发现得到、却没放进 `active_skills`，对模型等于不存在。

### 2.4 正文的拉取通道

模型侧的拉取工具是通用的 `read_file`，不是技能专用工具。

- 注册在 `backend/src/agent_window/tools/fs_tools.py` 的 `read_file_tool`：必填相对工作区的 `path`，`offset` 默认 1，`limit` 默认 200。
- 实现在 `backend/src/agent_window/services/workspace.py` 的 `read_file()`：行窗上限 500；字节先截到 `MAX_READ_BYTES`（100_000）；返回带行号的窗口和 `truncated`。长文件要翻页。
- `backend/src/agent_window/tools/__init__.py` 注册的是 fs / edit / shell / memory / session / attachment / builtin。没有 `skill_view`，也没有 `read_skill` 工具。
- `skills.py` 的 `read_skill(skill_id)` 会去掉 frontmatter、加上 Name/Description 头、并按 12_000 字截断。全仓库只有这一处定义，`routes` 和 `tools` 都没有调用它。标题里的 “skill tools” 是提示文案，工具表里没有对应名字。

所以现行拉模式是：**清单进 system，正文靠模型主动调用 `read_file`**。`read_skill()` 是一条未接线的服务函数，不能当成模型已经拥有的通道。

狗粮表把「模型会不会真的去加载 Skill」标成不可自动化（[`docs/dogfood/cot-s1-product-checklist.md`](../../dogfood/cot-s1-product-checklist.md) §9.4）。清单在不在提示里可以用测试锁；模型是否开口去读，不能。

### 2.5 同一次组装里的推模式

这些邻居会把**全文**放进 system。Skills 故意不跟它们走。

| 来源 | 行为 | 位置 |
|------|------|------|
| `AGENTS.md` | 分层合并后整段注入，标题是 `## AGENTS.md (project rules; read-only here)`。顺序：`~/.config/loop-agent/AGENTS.md`（否则 `~/.config/hal-agent/AGENTS.md`）→ 工作区祖先目录 → 工作区根。合并结果截到 `MAX_SKILL_CHARS`。 | `read_agents_md()` / `agents_md_paths()`，经 `skill_context_blocks()` |
| `SYSTEM.md` | 替换默认角色段（`base`）。记忆块和技能块仍接在后面。`_load_prompt_file()` 不设字数帽。 | `routes.py` `_system_prompt()` |
| `APPEND_SYSTEM.md` | 整段接在 `base` 后面，同样无字数帽。 | 同上 |
| `USER.md` / `MEMORY.md` | 有界全文，会话内冻结。 | `_system_prompt()` 的 `_curated_block` |

`SYSTEM.md` 只替换 `base`。它盖不住后面的记忆块和技能清单。

### 2.6 测试已经锁住的行为

`backend/tests/test_skills_layered.py`：

- `test_skills_inject_name_desc_only`：激活后的提示含 id、name、description，以及 “load via tools” / `read_file`；重复了 50 遍的正文句子不得出现。
- `test_skills_not_active_not_injected`：文件在盘上、未激活 → 没有 Available Skills 块。
- `test_agents_md_still_full_text`：同一函数对 `AGENTS.md` 仍注入全文。

`backend/tests/test_system_prompt.py` 锁的是 `SYSTEM.md` / `APPEND_SYSTEM.md` 的替换和追加，与技能清单无关。

### 2.7 读宪章时的一句过时缺口

宪章 §2.8 的缺口表仍写着「Skills 偏推/激活列表，非清单+按需 read」（`docs/architecture-charter.md`）。那一行是写宪章时的缺口。现行代码和 foundation-status 的 A4 清单已经是 catalog。以 `skill_context_blocks()` 和 `test_skills_inject_name_desc_only` 为准。

宪章后面的分工仍然有效（同文件「四层分工」）：流程进 skills；偏好和环境进 memory；短期进度、PR 号进 `search_session` 或 Goal 检查点。宪章写的工具名是 `session_search` / `skill_view`；树上的检索工具名是 `search_session`，技能正文没有 `skill_view`。

## 3. 提议：C8 路径提示

### 3.1 方案里已有的句子

[`docs/plans/context-loop-strengthen.md`](../../plans/context-loop-strengthen.md) §C8：

> 工作区可选 `TASK.md`（或 Settings 指定路径），system 加一句「长任务先读再改」。**不**自动创建、不进安装树。对齐 Cursor 社区 TASK.md，不是关服功能。

同文工期表把 C8 标成可选。C0–C5 已落地；这一段没有对应的设置键、没有注入代码、没有测试。

[`docs/research/compaction-handoff-peers.md`](../compaction-handoff-peers.md) 把 Cursor 社区的 `TASK.md` 记成对话摘要之外的 durable 任务单：压缩打的是对话桶，任务单留在文件里。本仓抄的是「对话与 durable 分桶」，不是去实现关服摘要。

### 3.2 路径提示注入指什么

跟 Skills 的清单同一契约，对象换成**一份**任务文件：

1. 默认候选是工作区根的 `TASK.md`。方案允许 Settings 再指定一条路径。`agent_settings.json` 的 `DEFAULTS` 里今天没有这个键。
2. 文件存在：system 增加路径（相对工作区）和一句「长任务先读再改」。正文不进 system。
3. 文件不存在，或指定路径落空：什么都不加。不创建文件，不写安装目录（`loop install` 的程序树与这份任务单无关）。
4. 模型要内容时走已经存在的 `read_file`。不为 C8 新造读取工具。`read_skill()` 那条未接线函数也不要借这个题目接上。
5. 人要改任务单，走现有的 `propose_edit` 审批，而不是系统提示在背后写盘。

提示跟技能清单一样，放在 `_system_prompt()` 每轮重拼的尾部，单独一块。块里只有路径和那一句，路径不变时前缀是稳的。`TASK.md` 会随进度改。记忆层为了 prefix cache，把 `USER.md` / `MEMORY.md` 冻在会话开始（宪章「双态模型」）。任务单改得勤，正文留在文件里，系统前缀才不会跟着每次编辑一起换。

模型可能忽略这句提示，直接改代码。这和 §9.4 的技能加载一样，不能靠单测证明模型会读。能锁住的是提示里**有路径、没有正文**，以及缺文件时**既不注入也不落盘**。

### 3.3 它补的是哪一格记忆

Skills 回答「这类事怎么做」。任务单回答「这一次做到哪了」。压缩摘要、`search_session` 回答「对话里曾经说过什么」。三格都在，职责不同：

- 技能清单跟着 system 走，压对话时还在。正文在 `skills/` 里，也不在对话桶里。
- 六节摘要会丢掉细节；C4 的 `search_session` 从本会话 `transcript.jsonl` 把摘录拉回来。那是对话原文，不是一份人可编辑的当前任务单。
- Goal 检查点挂在会话上。工作区 `TASK.md` 跨会话，换一个会话还能读到同一份文件。

C8 把「当前长任务」从对话桶里拿出来，放到工作区文件，再用一行路径告诉模型它在哪。这和 Skills 的拉模式同构，写入的槽位不同。

## 4. 对照

| | Skills（现行） | C8 `TASK.md`（提议，未做） |
|--|----------------|---------------------------|
| 槽位 | 流程 / 怎么做 | 这份工作区上的当前长任务 |
| 份数 | `skills/<id>/` 下多份，靠 `active_skills` 挑选 | 一份：默认 `TASK.md`，或设置里的一条路径 |
| 进 system 的内容 | id、name、description、加载提示 | 相对路径 + 「长任务先读再改」 |
| 正文 | 留在 `SKILL.md` / `README.md` | 留在该文件 |
| 拉取 | `read_file` 行窗（默认 200，最多 500） | 同一只 `read_file` |
| 缺席时 | 未激活或不存在 → 清单里没有这一条，不造文件 | 文件不存在 → 不加提示，不造文件，不进安装树 |
| 谁维护正文 | 人写技能文件；激活名单在设置里 | 人写任务单；改动走 `propose_edit` |
| 和压缩的关系 | 清单在 system，每轮重读；正文不在对话消息里 | 提示在 system；正文在工作区，压对话时文件还在 |
| 设置默认 | `active_skills: []` | 无键；不做则保持没有 |
| 测试现状 | `test_skills_layered.py` 锁「有清单、无正文」 | 无 |

Skills 清单今天不带路径，模型要猜 `skills/<id>/SKILL.md`。C8 的价值正好是把路径写进提示。补技能清单的路径是 Skills 自己的缺口，不必绑在 C8 上一起做。

## 5. 全文注入和路径提示怎么分开

C8 若做成「把 `TASK.md` 全文接进 system」，就和 `read_agents_md()`、`_load_prompt_file("APPEND_SYSTEM.md")` 变成第三份无差别全文。方案写的是加一句，并明确不自动创建。路径提示保持这个形状：

- 做法、审查步骤、命令习惯留在 `skills/<id>/SKILL.md`，用激活名单控制是否出现在清单里。
- 项目级规矩留在分层 `AGENTS.md`（已经全文注入，有 12_000 字帽）。
- 偏好和环境留在冻结的 `USER.md` / `MEMORY.md`。宪章要求祈使句不要写成 USER 里的「User prefers…」。
- 被压掉的对话细节留在 JSONL，用 `search_session` 拉短摘录。
- 当前长任务的进度和下一步留在可选的 `TASK.md`，system 只留路径。

`auto_compress` 继续默认关（`DEFAULTS["auto_compress"] = False`）。任务单是为了压了之后文件还在，不是为了把自动压缩打开。打开默认压缩仍是方案里的单独提交，和 C8 无关。

## 6. 以后真做 C8 时可以锁的行为

下面是行为，不是本笔记的补丁，也没有测试文件跟着落地。

- 工作区没有 `TASK.md`，也没有一条指向现存文件的设置：系统提示里不出现该路径，不出现「先读再改」，磁盘上不新增这个文件。
- 根上有 `TASK.md`：系统提示含相对路径 `TASK.md` 和先读再改的那一句；文件里独有的句子不出现在系统提示里。
- 设置指向一条不存在的路径：不注入，不创建，不回落到偷偷读别的文件。
- 提示不替代技能清单。两边可以同时存在：清单是多行技能，任务单是另外一行路径。
- `active_skills` 的默认空列表、`auto_compress` 的默认关，都保持原样。
- 安装目录不出现 `TASK.md`。

断言方式跟 `test_skills_inject_name_desc_only` 相同：看进模型的系统文本含什么、不含什么，不断言私有变量。

## 7. 本文不覆盖

- **C6** 工具批之后的中途压缩。
- **C7** regenerate 时给弃枝写摘要。
- **N2**。本仓库文档和代码里没有 N2 这一项；本文不另开。
- 把 `auto_compress` 改成默认开。
- 给 Skills 补路径、接上 `read_skill()`、或新增 `skill_view`。这些是技能通道自己的缺口，写在 §2.3 和 §2.4，留给以后的单独改动。
- 任何产品代码、设置键、API、测试。
