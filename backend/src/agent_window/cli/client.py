"""HTTP client for Hal Agent Runtime (stdlib only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Iterator, List, Optional


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class RuntimeClient:
    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        timeout: float | None = None,
    ) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self._url(path), data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise ApiError(f"{method} {path} -> HTTP {e.code}: {detail}", status=e.code, body=detail) from e
        except urllib.error.URLError as e:
            raise ApiError(f"Cannot reach {self.base_url}: {e.reason}") from e

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, body: Any = None, **kwargs: Any) -> Any:
        return self.request("POST", path, body=body, **kwargs)

    def put(self, path: str, body: Any = None, **kwargs: Any) -> Any:
        return self.request("PUT", path, body=body, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    def stream_post(
        self,
        path: str,
        body: Dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield SSE events as {type, ...payload}."""
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self._url(path),
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=timeout or max(self.timeout, 600.0))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise ApiError(f"POST {path} -> HTTP {e.code}: {detail}", status=e.code, body=detail) from e
        except urllib.error.URLError as e:
            raise ApiError(f"Cannot reach {self.base_url}: {e.reason}") from e

        event_type = ""
        data_lines: List[str] = []
        try:
            while True:
                line_b = resp.readline()
                if not line_b:
                    break
                line = line_b.decode("utf-8", errors="replace").rstrip("\r\n")
                if line == "":
                    if event_type:
                        payload_raw = "\n".join(data_lines)
                        event: Dict[str, Any] = {"type": event_type}
                        if payload_raw:
                            try:
                                parsed = json.loads(payload_raw)
                                if isinstance(parsed, dict):
                                    event.update(parsed)
                                else:
                                    event["content"] = payload_raw
                            except json.JSONDecodeError:
                                event["content"] = payload_raw
                        yield event
                    event_type = ""
                    data_lines = []
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
        finally:
            resp.close()


def qs(path: str, **params: Any) -> str:
    filtered = {k: v for k, v in params.items() if v is not None}
    if not filtered:
        return path
    return f"{path}?{urllib.parse.urlencode(filtered)}"
