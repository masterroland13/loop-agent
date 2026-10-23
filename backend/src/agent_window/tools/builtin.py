"""Built-in tools — register on import."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from agent_window.tools.registry import registry


def _urlopen(url: str, timeout: float = 12):
    req = urllib.request.Request(url, headers={"User-Agent": "loop-agent/0.1"})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except (ssl.SSLError, urllib.error.URLError) as e:
        # Some WSL/minimal images lack CA roots; fall back for smoke-test tools only.
        msg = str(e).lower()
        if "certificate" not in msg and "ssl" not in msg:
            raise
        ctx = ssl._create_unverified_context()
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)


async def ping_tool(args: Dict[str, Any]) -> str:
    note = (args.get("note") or "").strip()
    return json.dumps({"ok": True, "echo": note or "pong"}, ensure_ascii=False)


async def get_weather_tool(args: Dict[str, Any]) -> str:
    city = (args.get("city") or "").strip()
    if not city:
        return json.dumps({"error": "city is required"}, ensure_ascii=False)

    # wttr.in — no API key; good enough for tool-loop smoke test
    url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
    try:
        with _urlopen(url) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
        current = (raw.get("current_condition") or [{}])[0]
        area = ((raw.get("nearest_area") or [{}])[0].get("areaName") or [{}])[0].get("value") or city
        result = {
            "city": area,
            "temp_c": current.get("temp_C"),
            "feels_like_c": current.get("FeelsLikeC"),
            "humidity": current.get("humidity"),
            "weather": ((current.get("weatherDesc") or [{}])[0].get("value")),
            "wind_kmph": current.get("windspeedKmph"),
            "source": "wttr.in",
        }
        return json.dumps(result, ensure_ascii=False)
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"http {e.code}", "city": city}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e), "city": city}, ensure_ascii=False)


def register_builtin_tools() -> None:
    if registry.get("ping"):
        return

    registry.register(
        name="ping",
        description="Health-check tool. Returns ok and optional echo note. Use to verify tool calling works.",
        parameters={
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "Optional note to echo back"},
            },
            "additionalProperties": False,
        },
        handler=ping_tool,
    )

    registry.register(
        name="get_weather",
        description="Get current weather for a city (temperature, humidity, conditions). Use when the user asks about weather.",
        parameters={
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g. 合肥, Hefei, Beijing",
                },
            },
            "required": ["city"],
            "additionalProperties": False,
        },
        handler=get_weather_tool,
    )


register_builtin_tools()
