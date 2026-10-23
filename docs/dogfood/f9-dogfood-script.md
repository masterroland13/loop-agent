# F9 Foundation 狗粮剧本

> **目的：** 证明 F1–F6 中间档在真实两轮对话里可用——「解释报错 → 用户同意深挖 → 有 Goal 对照的结论」，无空白 assistant、无目标丢失。  
> **自动化：** `backend/tests/test_f9_dogfood.py`（mock LLM，CI 可跑）  
> **代码：** `backend/src/agent_window/dogfood/f9_scenario.py`

---

## 剧本（固定台词）

| 步 | 角色 | 内容 |
|----|------|------|
| 1 | User | 见 `F9_USER_TURN1`（ImportError / pytest / 先不改文件） |
| 2 | Agent | 文字解释可能原因 + 排查方向（可无工具） |
| 3 | User | 见 `F9_USER_TURN2`（「好的」+ 要求工具深挖 + 对照目标收工） |
| 4 | Agent | **必须：** 继承 Turn-1 Goal；至少 1 次工具；最终回复对照 Goal 收工 |
| 5 | UI | ToolTimeline 有步骤；刷新后会话仍可恢复 trace（F6） |

常量定义在 `f9_scenario.py`，勿改字面除非同步改测试。

---

## 自动化断言（pytest）

```bash
cd backend
PYTHONPATH=src .venv/bin/python -m pytest tests/test_f9_dogfood.py -q
```

| 用例 | 验证 |
|------|------|
| `test_f9_turn2_goal_inherits_turn1` | F1：「好的」继承 Turn-1 实质目标 |
| `test_f9_scripted_turn2_loop` | F1+F2+F4+F6：mock loop 出 turn_goal、tool_result、对照收工 |
| `test_f9_no_blank_assistant_on_done` | F6：done 时 assistant 非空 |

全量回归：

```bash
cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
cd .. && npx tsc -b
```

---

## 人工 UI 狗粮（可选，需 LLM + 工作区）

1. 启动：`bash scripts/restart-loop.sh`，打开 http://localhost:5173  
2. **This PC** 绑定本仓库根目录  
3. 新建会话，发送 **Turn 1** 全文  
4. 等 Agent 文字回复（不必有工具）  
5. 发送 **Turn 2** 全文  
6. **检查清单：**
   - [x] 消息旁 **目标** 条仍含 ImportError / pytest / PYTHONPATH 等 Turn-1 关键词（不是只有「好的」）— 2026-08-24 API 复验（**须先 `scripts/restart-loop.sh`**，旧 uvicorn 不会加载续写继承）
   - [x] **ToolTimeline** 至少 1 步工具 — 同日 API 狗粮（18× tool_result）
   - [x] 最终 assistant 段落像结论（含「对照目标」「收工」或明确原因/建议）
   - [x] **刷新页面** 后 ToolTimeline 仍在（F6）— API re-GET messages 仍有 trace
   - [ ] 停止/失败时仍有占位或 failed+重试，无整页空白（F6-TC 系列；本剧本未强制跑）

---

## 与 §0.4 六条的关系

| §0.4 | F9 覆盖 |
|------|---------|
| 1 显式 Goal | ✅ Turn-2 继承断言 |
| 2 多轮进度/阻塞 | ✅ F2 检查点条展示模型进度说明 |
| 3 成功产物/失败事实 | ◐ mock 路径覆盖；真人需目视 |
| 4 Reject/失败续环 | — 不在本剧本（见 `test_gate_continue.py`） |
| 5 触顶软着陆 | — 不在本剧本 |
| 6 过程可监督 | ✅ tool trace + 非空 assistant |

F9 绿 **不等于** §0.4 全绿；全绿还需 §4.2 边角（F2 可见进度、长 log 展开等）。

---

## 维护

- 改台词 → 同步 `f9_scenario.py` + `test_f9_dogfood.py` + 本文  
- F9 完成 → 勾选 [`../foundation-status.md`](../foundation-status.md) §4.1
