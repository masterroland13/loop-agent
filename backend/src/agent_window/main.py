"""FastAPI application entrypoint."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_window.api import router
from agent_window.models import init_db
from agent_window.services.memory import load_persisted_memories
from agent_window.services.patches import load_persisted_patches
from agent_window.services.shell import load_persisted_shells

logger = logging.getLogger(__name__)

app = FastAPI(title="Agent Window Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def startup():
    init_db()
    n_patches = load_persisted_patches()
    n_shells = load_persisted_shells()
    n_memories = load_persisted_memories()
    if n_patches or n_shells or n_memories:
        logger.info(
            "restored pending approvals: patches=%s shells=%s memories=%s",
            n_patches,
            n_shells,
            n_memories,
        )
