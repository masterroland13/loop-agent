"""Temporary DB inspection: message sizes per session + recent audit events."""
import json
import sqlite3
from collections import defaultdict

DB = "backend/data/agent_window.db"
con = sqlite3.connect(DB)
cur = con.cursor()

print("== tables ==")
for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print(r[0])

print("\n== sessions + message volume ==")
# 粗略 token 估算:中文约 1 字 ~= 0.7 token,英文约 4 字符 ~= 1 token,混合按 3 字符/token 近似
CHARS_PER_TOKEN = 3.0
try:
    rows = cur.execute(
        """
        SELECT s.id, COUNT(m.id), COALESCE(SUM(LENGTH(m.content)), 0)
        FROM sessions s LEFT JOIN messages m ON m.session_id = s.id
        GROUP BY s.id ORDER BY 3 DESC
        """
    ).fetchall()
    for sid, cnt, total in rows:
        est = int(total / CHARS_PER_TOKEN)
        flag = "  <-- 可能超 262k 上限" if est > 200_000 else ""
        print(f"session={sid} msgs={cnt} total_chars={total} est_tokens~={est}{flag}")
except Exception as e:
    print("ERR", e)

print("\n== largest messages (top 8) ==")
try:
    rows = cur.execute(
        """
        SELECT session_id, role, LENGTH(content), substr(content, 1, 80)
        FROM messages ORDER BY LENGTH(content) DESC LIMIT 8
        """
    ).fetchall()
    for sid, role, ln, head in rows:
        print(f"session={sid} role={role} len={ln} head={head!r}")
except Exception as e:
    print("ERR", e)

print("\n== recent audit events (top 30) ==")
try:
    rows = cur.execute(
        "SELECT created_at, session_id, event_type, payload FROM audit_events ORDER BY created_at DESC LIMIT 30"
    ).fetchall()
    for ts, sid, etype, payload in rows:
        try:
            p = json.loads(payload or "{}")
            extra = ""
            if etype == "turn_meta":
                extra = f" prompt_tokens={p.get('approx_prompt_tokens')} model={p.get('model')}"
            elif etype == "context.compress":
                extra = f" {p.get('session_id')}"
        except Exception:
            extra = ""
        print(f"{ts} {sid} {etype}{extra}")
except Exception as e:
    print("ERR", e)

con.close()
