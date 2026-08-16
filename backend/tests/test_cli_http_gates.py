"""CLI status/approve/reject against real FastAPI routes — no LLM."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_window.cli.client import ApiError
from agent_window.cli.main import cmd_approve, cmd_reject, cmd_status
from agent_window.config import settings
from agent_window.models import init_db
from agent_window.services.patches import _patches, create_patch_from_content
from agent_window.services.shell import _shells
from agent_window.services.memory import _memories
from agent_window.services.workspace import set_workspace_root


class AsgiRuntimeClient:
    def __init__(self, client: TestClient) -> None:
        self._client = client

    def get(self, path: str, **_kwargs: Any) -> Any:
        response = self._client.get(path)
        if response.status_code >= 400:
            raise ApiError(
                f"GET {path} -> HTTP {response.status_code}: {response.text}",
                status=response.status_code,
                body=response.text,
            )
        if not response.content:
            return None
        return response.json()

    def post(self, path: str, body: Any = None, **_kwargs: Any) -> Any:
        response = self._client.post(path, json=body)
        if response.status_code >= 400:
            raise ApiError(
                f"POST {path} -> HTTP {response.status_code}: {response.text}",
                status=response.status_code,
                body=response.text,
            )
        if not response.content:
            return None
        return response.json()


@pytest.fixture
def gate_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    ws = tmp_path / "ws"
    data.mkdir()
    ws.mkdir()
    monkeypatch.setattr(settings, "app_data_dir", str(data))

    import agent_window.models as models

    models._engine = None
    models._SessionLocal = None
    init_db()
    _patches.clear()
    _shells.clear()
    _memories.clear()
    set_workspace_root(str(ws))

    from agent_window.main import app

    http = TestClient(app)
    yield SimpleNamespace(ws=ws, client=AsgiRuntimeClient(http), raw=http)


def test_status_empty_then_patch_approve(gate_env, capsys: pytest.CaptureFixture[str]) -> None:
    args = SimpleNamespace(session=None, json=False)
    assert cmd_status(gate_env.client, args) == 0
    assert "待审批: (无)" in capsys.readouterr().out

    patch = create_patch_from_content("cli-gate-test.txt", "hal-status-ok\n")
    assert cmd_status(gate_env.client, SimpleNamespace(session=None, json=True)) == 0
    out = capsys.readouterr().out
    assert patch.id in out
    assert "cli-gate-test.txt" in out

    code = cmd_approve(
        gate_env.client,
        SimpleNamespace(patch_ids=[patch.id], shell_ids=None, memory_ids=None, no_input=True),
    )
    assert code == 0
    written = (gate_env.ws / "cli-gate-test.txt").read_text(encoding="utf-8")
    assert "hal-status-ok" in written
    capsys.readouterr()
    assert cmd_status(gate_env.client, args) == 0
    assert "待审批: (无)" in capsys.readouterr().out


def test_reject_does_not_write_file(gate_env, capsys: pytest.CaptureFixture[str]) -> None:
    patch = create_patch_from_content("cli-gate-reject.txt", "should-not-exist\n")
    code = cmd_reject(
        gate_env.client,
        SimpleNamespace(patch_ids=[patch.id], shell_ids=None, memory_ids=None, no_input=True),
    )
    assert code == 0
    assert not (gate_env.ws / "cli-gate-reject.txt").exists()
    capsys.readouterr()
    # Rejected is history (visible in the session stream), not in the pending list.
    assert cmd_status(gate_env.client, SimpleNamespace(session=None, json=True)) == 0
    out = capsys.readouterr().out
    assert patch.id not in out
    assert '"awaiting_approval": false' in out


def test_approve_no_input_without_ids(gate_env) -> None:
    create_patch_from_content("need-id.txt", "x\n")
    code = cmd_approve(
        gate_env.client,
        SimpleNamespace(patch_ids=None, shell_ids=None, memory_ids=None, no_input=True),
    )
    assert code == 2
    assert not (gate_env.ws / "need-id.txt").exists()
