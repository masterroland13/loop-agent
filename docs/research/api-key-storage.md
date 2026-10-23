# API Key 存放、泄露面，以及网页 / 桌面封装

> L3 调研。收 2026-10 关于密钥的问答，供会话级档案与以后的桌面壳对照。  
> **不**把「绝对安全」写成目标。能调用模型的进程，只要和攻击者同一用户，密钥就能被用走。  
> 实现方案仍见 [`../plans/session-model-profiles.md`](../plans/session-model-profiles.md)。会话上只存 `profile_id`，不复制 Key。

## 现在存在哪里

| 位置 | 有没有 Key |
|------|------------|
| `app_data_dir/model_profiles.json`（默认 `backend/data/`） | **有**，字段 `api_key`，明文 |
| 进程内 `settings.llm_api_key` | 当前 active 档案的副本，供现有调用 |
| `backend/.env` 的 `LLM_API_KEY` | 仅第一次种进 JSON；之后以 JSON 为准 |
| 浏览器 `localStorage`、设置导出、会话 SQLite | **没有** |
| git | `backend/data/` 与 `backend/.env` 已在 `.gitignore` |

公开接口只返回 `api_key_configured`。测试锁了「公开 JSON 里不能出现密钥字符串」。界面保存后清空输入，再打开只显示已保存占位。空字符串保存不会擦掉已有 Key。审计只记是否更新过 Key。写文件时尝试 `chmod 0600`。界面报错改写成短句，不把 Key 贴回聊天。

## 现在没挡住的

- 文件没有加密。宪章写过本地加密存储，代码还没做。把加密密钥和密文放在同一目录，拷走目录就一起失效。
- 同一系统用户、备份、网盘、从 Windows 侧打开 WSL 里的 `data/`，都能读到明文。`chmod` 在部分 Windows 挂载上会静默失败。
- 本机 8000 没有登录。别人连上端口读不走 Key，但可以让 Agent 用这把 Key 发请求。端口不要暴露到本机以外。

## 做成网页或 App 之后

**桌面安装包（本仓该走的）**  
Key 留在用户电脑。会话库只存档案 id。Cline 在 VS Code 里用系统密钥库（macOS 钥匙串、Windows 凭据管理器、Linux Secret Service），不把 Key 放进普通 JSON。它的独立版曾经写明文 `secrets.json`，随后改成系统钥匙串，不可用才退回文件。Cursor 桌面的「自带 API Key」也只留在本机；[官方说明](https://cursor.com/help/models-and-usage/api-keys)写明不会把 Key 存到 Cursor 的服务器上。

不要照抄 Cursor 的传输方式：他们的自带 Key 每次仍会送到 Cursor 后端，因为提示词在那边拼装。云端 Agent 和手机版因此不能用自带 Key——云上没有客户端把 Key 塞进请求（[论坛说明](https://forum.cursor.com/t/byok-models-doesnt-work-on-mobile-web/169324)）。本仓是本机 Agent，应由本机后端直接打供应商，Key 不出这台机器。

封装时：Key 进系统钥匙串；安装包和仓库不带 Key；后端只听 `127.0.0.1`；日志、导出、审计继续不写 Key。

**我们托管的网页**  
消费产品（Cursor 默认模型、ChatGPT、Claude.ai）不让用户保管供应商 Key。Key 在服务商自己的密钥系统里，浏览器只有登录态。  
若网页上也要用户自己的 Key：要么存在我们的服务器并用密钥管理系统加密，并明确说我们保管着它；要么不存。不要放进 `localStorage`，页面脚本能读走。Cursor 对网页 / 手机选择了不存。

## 值得借鉴的

1. 本机产品用系统钥匙串，而不是再加密一层仍放在 `data/` 里的 JSON。放进桌面壳，不塞进会话级档案这一刀。
2. 托管网页用我们的 Key 加用户登录，不把用户的供应商 Key 放进浏览器。
3. 自带 Key 默认不出本机，除非以后单独做云端代拼提示词并写明。
4. 保持现状已经做对的：接口不回显、导出不含 Key、空保存不覆盖、审计只记「更新过」。

## 参考

- Cursor：[Bring your own API key](https://cursor.com/help/models-and-usage/api-keys)；[Data use](https://cursor.com/data-use)（即使用自己的 Key，请求仍经 Cursor 后端拼装）。
- Cline：VS Code `SecretStorage`；独立版由明文 JSON 迁到系统钥匙串（[keytar PR](https://github.com/cline/cline/pull/5993)）。`keytar` 本身已少维护，封装时优先各平台当前的钥匙串 API，而不是照搬这个包。
- Continue 曾因把 Key 明文放在用户目录 JSON 被提出问题：[continuedev/continue#1729](https://github.com/continuedev/continue/issues/1729)。本仓 `model_profiles.json` 与那种形态同类。
