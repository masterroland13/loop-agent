"""Serve the installed frontend from the shell backend."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_shell_frontend(app: FastAPI, static_dir: Path | None = None) -> bool:
    """Mount dist/ when this process is the desktop shell. Dev stays API-only."""
    directory = static_dir
    if directory is None:
        if os.environ.get("LOOP_SHELL") != "1":
            return False
        raw = os.environ.get("LOOP_STATIC_DIR", "").strip()
        if not raw:
            return False
        directory = Path(raw)
    index = directory / "index.html"
    if not index.is_file():
        return False
    assets = directory / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="shell-assets")
    favicon = directory / "favicon.svg"

    if favicon.is_file():

        @app.get("/favicon.svg")
        def shell_favicon() -> FileResponse:
            return FileResponse(favicon)

    @app.get("/")
    def shell_index() -> FileResponse:
        return FileResponse(index)

    @app.post("/api/shell-boot")
    async def shell_boot(request: Request) -> dict[str, bool]:
        Path("/tmp/loop-shell-boot.log").write_bytes((await request.body())[:4000])
        return {"ok": True}

    return True
