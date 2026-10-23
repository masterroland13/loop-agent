import json, urllib.request, sys

BASE = "http://127.0.0.1:8000"

req = urllib.request.Request(
    BASE + "/api/sessions",
    data=json.dumps({"title": "sse-smoke"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    sess = json.loads(r.read().decode())
sid = sess["id"]
print("session", sid)

body = json.dumps({"content": "\u5408\u80a5\u5929\u6c14"}).encode()
req = urllib.request.Request(
    BASE + "/api/sessions/%s/messages" % sid,
    data=body,
    headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    method="POST",
)
tool_results = []
tokens = []
with urllib.request.urlopen(req, timeout=90) as r:
    buf = ""
    while True:
        chunk = r.read(256)
        if not chunk:
            break
        buf += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buf:
            block, buf = buf.split("\n\n", 1)
            ev, data = None, None
            for line in block.split("\n"):
                if line.startswith("event:"):
                    ev = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
            if not ev or data is None:
                continue
            try:
                payload = json.loads(data)
            except Exception:
                payload = data
            if ev == "tool_result":
                tool_results.append(payload)
                print("tool_result:", json.dumps(payload, ensure_ascii=False)[:800])
            elif ev == "token":
                content = payload.get("content", "") if isinstance(payload, dict) else ""
                tokens.append(content)
            elif ev in ("done", "error"):
                print(ev + ":", json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload)
                if ev == "error":
                    sys.exit(1)

final = "".join(tokens)
preview = final[0:200]
print("final_token_preview:", preview)
print("token_chars:", len(final))
print("tool_result_count:", len(tool_results))