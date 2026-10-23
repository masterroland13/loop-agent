# 会话级模型档案 + 多网关预置（进行中）

> L2 实现方案。未完成前不升入 `design/`。  
> 宪章：[`architecture-charter.md`](../architecture-charter.md) §3.4（`api` 首版固定 `openai-completions`）。  
> 路线图：[`agent-window-roadmap.md`](../agent-window-roadmap.md) §4.3 后置项「会话级 `profile_id`」。

| 字段 | 值 |
|------|-----|
| 状态 | §4 手测已通过（2026-10-23） |
| 粗工期 | **2.5～3.5 人日**（三刀，可独立停） |
| 不做 | 原生 Anthropic / Google / Azure AD；每会话独立 temperature |

---

## 1. 现状（调研结论）

档案存在 `app_data_dir/model_profiles.json`。每张档案已有 `label`、`base_url`、`api_key`、`model_id`、`api`（写死 `openai-completions`）、`enabled`。

**能填什么：** 任意 `http(s)` Base URL + Key + 模型 id。Kimi（`https://api.moonshot.cn/v1`）、DeepSeek（`https://api.deepseek.com`）、OpenRouter、自建 router / LiteLLM **只要说 OpenAI Chat Completions 就能用**。设置里「添加档案」就是空白卡，没有厂商预填。

**实际请求不按档案走：**

- `LLMProvider` 是进程单例。`_sync_client()` 只 `resolve_credentials()` **全局 active**。
- 前端顶栏选的是一个 **模型名字符串**，存在浏览器 `localStorage`（全 App 一份），经 `MessageRequest.model` 发到后端。
- `provider.chat_stream` 用这个字符串当 `model`，**URL 和 Key 仍是 active 档案**。
- 所以 `kimi-k3`、`deepseek-v4-flash` 这类名字是 **你们 router 上的 id**，不是 Moonshot/DeepSeek 官网上的模型名。换 Base URL 不换 id 会 404。
- 两个会话并行（P3）若中途改 active，单例 client 会串密钥。会话级必须 **按请求取 client**，禁止改全局 `settings.llm_*` 来切换。

分层：Registry / Provider ∈ loop-ai；会话列与 HTTP ∈ loop-window。`core/` 不 import `models`。`profile_id` 在 routes 组装 `ChatRequest` 时传入，不进 `loop.py` 的策略分支。

SQLite 加列沿用 `models.init_db` 里 `PRAGMA table_info` + `ALTER TABLE`（与 `goal_mode` 相同）。

---

## 2. 产品决定（锁死，避免返工）

1. **协议不扩展。** 仍只有 OpenAI 兼容。`api` 字段保持 `openai-completions`。
2. **档案 = 一套网关**（URL + Key + 默认 `model_id` + 可选预置 id）。不是「一个模型一条档案」的强制形态；同一 OpenRouter Key 可以只建一张档案。
3. **会话存两列：**
   - `profile_id`：这轮用哪套 URL/Key。
   - `model_id`：这轮请求体的 model。空则用该档案的默认 `model_id`。
4. **旧会话两列为空：** 发送时解析为 **当时的全局 active**（行为与今天一致）。新会话在创建时 **抄一份当前 active 的 id + model**，之后改全局 active **不改写**已有会话。
5. **顶栏选择写当前会话，不写全局 active。** 设置里「设为当前档案」只影响 **之后新建的会话** 和旧的空列。
6. **选中项如何绑档案：**
   - 该 `model_id` 只属于一张启用档案 → 会话 `profile_id` 设为那张。
   - 多张档案 `model_id` 相同 → 用已有的「标签 · model_id」区分，选中带上 `profile_id`。
   - 手填 / 最近用过、对不上任何档案默认 id → **只改会话 `model_id`**，`profile_id` 不动（router 上临时换模型）。
7. **档案被删或禁用：** 该会话下一轮回落全局 active（或第一个仍启用的），toast 说明，不静默用空 Key。
8. **厂商预置是数据，不是新协议。** 添加档案时可从预置填 Base URL 和建议模型；Key 永远手填。预置至少：Moonshot/Kimi、DeepSeek、OpenRouter、OpenAI、Groq、Together、SiliconFlow、智谱、通义（DashScope 兼容端点）、空白「OpenAI 兼容 / Router」。模型 id 用各家当前文档里的例子。`deepseek-v4-flash` 不写入 DeepSeek 预置（官方现用 `deepseek-flash`）。

   2026-10-20 复核：原先把 `kimi-k3` 当成只存在于 router 的别名。Moonshot 官方快速开始现在的 Chat Completions 示例就是 `base_url=https://api.moonshot.cn/v1`、`model=kimi-k3`。官方面预置改用这个 id，并用厂商 URL 与空白档案区分；空白档案仍继承当前网关 URL，模型仍是 `kimi-k3`。

---

## 3. 工作安排

| 刀 | 内容 | 工期 | 停手标准 |
|----|------|------|----------|
| **S1** | 预置目录（前后端同一份 id）+ 设置「添加档案」从预置开卡。不改发送路径 | 0.5 日 | 选 Moonshot 预填 URL；空白档案行为与现在相同 |
| **S2** | `sessions.profile_id` / `sessions.model_id` 迁移；PATCH；创建时抄 active。`LLMProvider` 按 `profile_id` 缓存 `AsyncOpenAI`，`chat_stream` / `chat_complete` / 压缩摘要都传入。禁止为切换去写 `settings.llm_*` | 1～1.5 日 | pytest：A/B 两套假 URL 不会串 client；空列走 active |
| **S3** | 顶栏：切会话显示该会话模型；选择写 PATCH 会话。`localStorage` 只作「上次手填」缓存，不再当全局当前模型 | 0.5～1 日 | 手测 §4 |
| 手测 | 下面 6 条 | 0.5 日 | 全绿再改 Living / 路线图勾选 |

S1 可单独合并。S2 不与 Files/i18n 混改。S3 依赖 S2 的 API。

2026-10-20 S3 对照：启动时不再用网关 `/models` 改写顶栏；旧会话空 `model_id` 发送时不带模型名，由服务端按当时的默认档案解析。手填若只命中一张档案会带上 `profile_id`。档案回落的 SSE meta 带上新的 `profile_id`，后台会话也会写回。§4 仍未手测。

2026-10-23：§4 六步手测通过。

**明确不做：** `/models` 自动拉全量目录（预置 + 手填 + 现有 gateway 列表够用）；每会话 temperature；非 OpenAI 翻译器（宪章后置，另开才会返工）。

---

## 4. 手测（S3 之后）

1. 两张档案，Base URL 不同（可用一家真网关 + 一张故意错误 URL 的停用档案，或两家真网关）。
2. 会话 A 绑档案 1，会话 B 绑档案 2；顶栏随切换变化。
3. A、B 各发一条（可同时 busy）。回合 Meta 的 model 对得上；错误 URL 的那侧应失败且 **不** 把另一侧打到错误网关。
4. 刷新后绑定仍在。
5. 改全局 active，已有 A/B 不变；新建 C 用新 active。
6. 在 A 手填一个档案默认 id 之外的模型名：A 的 `model_id` 变，B 不变，A 的 `profile_id` 不变。删掉 A 的档案后再发：回落并有提示。

---

## 5. 主要落点

| 处 | 改动 |
|----|------|
| `backend/.../models.py` | 两列 + `_migrate_sessions_model_profile` |
| `schemas.py` / session PATCH / `SessionResponse` | 读写两列 |
| `services/model_registry.py` | `resolve_handle(profile_id)`；预置表可放此处或 `provider_presets.py` |
| `services/provider.py` | client 缓存；请求带 profile |
| `api/routes.py` 发消息 / regenerate / compress | 解析会话档案再调 provider |
| `src/components/SettingsPanel.tsx` | 从预置添加 |
| `src/components/ModelPicker.tsx` + `App.tsx` | 选项带 `profile_id`；写入当前会话 |
| `backend/tests/test_model_registry.py` 等 | 先写失败用例再改（AGENTS 测试纪律） |

前端无自动化：S3 靠 `tsc` + §4 手测。
