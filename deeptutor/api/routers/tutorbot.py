"""
TutorBot management API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel

from deeptutor.api.dependencies import require_admin
from deeptutor.services.tutorbot import get_tutorbot_manager
from deeptutor.services.tutorbot.manager import BotConfig
from deeptutor.utils.error_utils import public_error_detail

router = APIRouter(dependencies=[Depends(require_admin)])


class CreateBotRequest(BaseModel):
    bot_id: str
    name: str | None = None
    description: str = ""
    persona: str = ""
    channels: dict = {}
    model: str | None = None


class UpdateBotRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    persona: str | None = None
    channels: dict | None = None
    model: str | None = None


class FileUpdateRequest(BaseModel):
    content: str


class SoulCreateRequest(BaseModel):
    id: str
    name: str
    content: str


class SoulUpdateRequest(BaseModel):
    name: str | None = None
    content: str | None = None


# ── Soul template library (must be before /{bot_id} routes) ───

@router.get("/souls")
async def list_souls():
    return get_tutorbot_manager().list_souls()


@router.post("/souls")
async def create_soul(payload: SoulCreateRequest):
    mgr = get_tutorbot_manager()
    if mgr.get_soul(payload.id):
        raise HTTPException(status_code=409, detail=f"Soul '{payload.id}' already exists")
    return mgr.create_soul(payload.id, payload.name, payload.content)


@router.get("/souls/{soul_id}")
async def get_soul(soul_id: str):
    soul = get_tutorbot_manager().get_soul(soul_id)
    if not soul:
        raise HTTPException(status_code=404, detail="Soul not found")
    return soul


@router.put("/souls/{soul_id}")
async def update_soul(soul_id: str, payload: SoulUpdateRequest):
    result = get_tutorbot_manager().update_soul(soul_id, payload.name, payload.content)
    if not result:
        raise HTTPException(status_code=404, detail="Soul not found")
    return result


@router.delete("/souls/{soul_id}")
async def delete_soul(soul_id: str):
    if not get_tutorbot_manager().delete_soul(soul_id):
        raise HTTPException(status_code=404, detail="Soul not found")
    return {"id": soul_id, "deleted": True}


# ── Bot management (static paths before /{bot_id} parameterized routes) ──

@router.get("")
async def list_bots():
    return get_tutorbot_manager().list_bots()


@router.get("/recent")
async def recent_bots(limit: int = 3):
    """Return the most recently active bots with their last message preview."""
    return get_tutorbot_manager().get_recent_active_bots(limit=limit)


@router.post("")
async def create_and_start_bot(payload: CreateBotRequest):
    mgr = get_tutorbot_manager()
    config = None
    if any(
        [
            payload.name,
            payload.description,
            payload.persona,
            payload.channels,
            payload.model,
        ]
    ):
        config = BotConfig(
            name=payload.name or payload.bot_id,
            description=payload.description,
            persona=payload.persona,
            channels=payload.channels,
            model=payload.model,
        )
    try:
        instance = await mgr.start_bot(payload.bot_id, config)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=public_error_detail("TutorBot operation"))
    return instance.to_dict()


@router.get("/{bot_id}")
async def get_bot(bot_id: str):
    mgr = get_tutorbot_manager()
    instance = mgr.get_bot(bot_id)
    if instance:
        return instance.to_dict()
    cfg = mgr._load_bot_config(bot_id)
    if cfg:
        return {
            "bot_id": bot_id, "name": cfg.name, "description": cfg.description,
            "persona": cfg.persona, "channels": list(cfg.channels.keys()),
            "model": cfg.model, "running": False, "started_at": None,
        }
    raise HTTPException(status_code=404, detail="Bot not found")


@router.delete("/{bot_id}")
async def stop_bot(bot_id: str):
    stopped = await get_tutorbot_manager().stop_bot(bot_id)
    if not stopped:
        raise HTTPException(status_code=404, detail="Bot not found or not running")
    return {"bot_id": bot_id, "stopped": True}


@router.delete("/{bot_id}/destroy")
async def destroy_bot(bot_id: str):
    destroyed = await get_tutorbot_manager().destroy_bot(bot_id)
    if not destroyed:
        raise HTTPException(status_code=404, detail="Bot not found")
    return {"bot_id": bot_id, "destroyed": True}


@router.patch("/{bot_id}")
async def update_bot(bot_id: str, payload: UpdateBotRequest):
    mgr = get_tutorbot_manager()
    instance = mgr.get_bot(bot_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot not found")

    if payload.name is not None:
        instance.config.name = payload.name
    if payload.description is not None:
        instance.config.description = payload.description
    if payload.persona is not None:
        instance.config.persona = payload.persona
    if payload.channels is not None:
        instance.config.channels = payload.channels
    if payload.model is not None:
        instance.config.model = payload.model

    mgr._save_bot_config(bot_id, instance.config)
    return instance.to_dict()


# ── Workspace file endpoints ──────────────────────────────────

@router.get("/{bot_id}/files")
async def list_bot_files(bot_id: str):
    return get_tutorbot_manager().read_all_bot_files(bot_id)


@router.get("/{bot_id}/files/{filename}")
async def read_bot_file(bot_id: str, filename: str):
    content = get_tutorbot_manager().read_bot_file(bot_id, filename)
    if content is None:
        raise HTTPException(status_code=400, detail=f"Not an editable file: {filename}")
    return {"filename": filename, "content": content}


@router.put("/{bot_id}/files/{filename}")
async def write_bot_file(bot_id: str, filename: str, payload: FileUpdateRequest):
    ok = get_tutorbot_manager().write_bot_file(bot_id, filename, payload.content)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Not an editable file: {filename}")
    return {"filename": filename, "saved": True}


# ── Chat history & WebSocket ──────────────────────────────────

@router.get("/{bot_id}/history")
async def get_bot_history(bot_id: str, limit: int = 100):
    """Read chat history from the bot's unified SQLite-backed sessions."""
    return get_tutorbot_manager().get_bot_history(bot_id, limit=limit)
