"""Photo-answer OCR input layer REST endpoints (plan §7).

Thin wrapper discipline: this router only does flag gating, auth,
ownership checks, upload normalization (EXIF strip) and task scheduling.
All business behavior lives in PhotoAnswerService / CostLedger / store.

Feature flag DEEPTUTOR_PHOTO_ANSWER_ENABLED defaults OFF → endpoints 404.
Status polling doubles as crash recovery: a running job whose lease expired
gets re-enqueued on the next poll (no scheduler needed at this scale).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

from deeptutor.api.dependencies.auth import resolve_auth_context
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.services.path_service import get_path_service
from deeptutor.services.photo_answer.cost_ledger import (
    BudgetExceeded,
    CostLedger,
    EscalationLimitReached,
)
from deeptutor.services.photo_answer.engines.base import EngineNotConfigured
from deeptutor.services.photo_answer.models import (
    DailyQuotaExceeded,
    InvalidTransition,
    PhotoAnswerError,
)
from deeptutor.services.photo_answer.quality import assess_image_quality
from deeptutor.services.photo_answer.service import PhotoAnswerService
from deeptutor.services.photo_answer.store import PhotoAnswerStore

logger = logging.getLogger(__name__)

router = APIRouter()

_FLAG_ENV = "DEEPTUTOR_PHOTO_ANSWER_ENABLED"
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MAX_PAGES_PER_SESSION = 6
_JPEG_QUALITY = 88


def _enabled() -> bool:
    return os.environ.get(_FLAG_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _ensure_enabled() -> None:
    if not _enabled():
        # 404（而非 403）：flag off 时整个能力面不存在
        raise HTTPException(status_code=404, detail="Not found")


def _resolve_user_id(authorization: str | None) -> str:
    current = resolve_auth_context(authorization)
    if current is None or not str(current.user_id or "").strip():
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(current.user_id).strip()


# ---------- runtime wiring ----------


@dataclass
class PhotoAnswerRuntime:
    store: PhotoAnswerStore
    ledger: CostLedger
    images_root: Path
    l0_factory: Callable[[], Any]
    l1_factory: Callable[[], Any] | None
    l2_factory: Callable[[], Any] | None

    def image_loader(self, image_ref: str) -> bytes:
        ref = json.loads(image_ref)
        path = Path(ref["path"]).resolve()
        path.relative_to(self.images_root.resolve())  # raises on traversal
        return path.read_bytes()

    def service(self) -> PhotoAnswerService:
        return PhotoAnswerService(
            store=self.store,
            ledger=self.ledger,
            l0_factory=self.l0_factory,
            l1_factory=self.l1_factory,
            l2_factory=self.l2_factory,
            image_loader=self.image_loader,
        )


_runtime: PhotoAnswerRuntime | None = None


def _default_runtime() -> PhotoAnswerRuntime:
    from deeptutor.services.photo_answer.engines.aliyun_handwriting import AliyunHandwritingEngine
    from deeptutor.services.photo_answer.engines.baidu_handwriting import BaiduHandwritingEngine
    from deeptutor.services.photo_answer.engines.qwen_vl_ocr import QwenVlOcrEngine

    root = get_path_service().get_user_root() / "workspace" / "photo_answer"
    store = PhotoAnswerStore(root / "photo_answer.db")
    images_root = root / "images"
    images_root.mkdir(parents=True, exist_ok=True)
    return PhotoAnswerRuntime(
        store=store,
        ledger=CostLedger(store),
        images_root=images_root,
        l0_factory=BaiduHandwritingEngine.from_env,
        l1_factory=QwenVlOcrEngine.from_env,
        l2_factory=AliyunHandwritingEngine.from_env,
    )


def get_runtime() -> PhotoAnswerRuntime:
    global _runtime
    if _runtime is None:
        _runtime = _default_runtime()
    return _runtime


def set_runtime_for_tests(runtime: PhotoAnswerRuntime | None) -> None:
    global _runtime
    _runtime = runtime


# ---------- helpers ----------


def _owned_session(runtime: PhotoAnswerRuntime, session_id: str, user_id: str) -> dict[str, Any]:
    session = runtime.store.get_session(session_id)
    if session is None or str(session["user_id"]) != user_id:
        # 不区分"不存在"与"不属于你"——避免会话 ID 枚举
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _strip_exif_reencode(data: bytes) -> bytes:
    """Decode + re-save as plain JPEG: drops EXIF (incl. GPS) wholesale.

    Undecodable input (HEIC without codec, non-images) → 415 with a client
    hint; wx.chooseMedia with sizeType=compressed yields JPEG so this is the
    rare path.
    """
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image format; please upload JPEG/PNG (iOS 用户请在系统设置中将相机格式改为'兼容性最佳'，或使用小程序压缩上传)",
        ) from None
    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=_JPEG_QUALITY)
    return out.getvalue()


# ---------- request models ----------


class CreateSessionRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=256)
    # 题干 verbatim 落 SQLite 并进折叠/正则；4000 字够任何真实题干，超长即外部攻击/误用
    question_stem: str = Field(default="", max_length=4000)


class ConfirmRequest(BaseModel):
    # 确认稿 verbatim 落库并送批改器；20000 字够任何真实作答，超长即外部攻击/误用
    confirmed_text: str = Field(max_length=20000)
    job_version: int
    ack_normal_suspicions: bool = False
    resolved_span_ids: list[str] = Field(default_factory=list)
    diff: list[Any] = Field(default_factory=list)
    edited_char_count: int = 0


class RetryRequest(BaseModel):
    mode: str = Field(pattern="^(rerun|escalate)$")
    page_index: int | None = None


# ---------- endpoints ----------


@router.post(
    "/sessions",
    dependencies=[
        # 付费 OCR 入口：每 session 触发三家外部 API（上限 0.30 元）。每日配额挡不住
        # 短时爆发，叠加一层每用户/每 IP 短窗限流（沿用仓库统一的 route_rate_limit 姿势）。
        Depends(
            route_rate_limit(
                "photo_answer_create_session",
                default_max_requests=5,
                default_window_seconds=60.0,
            )
        )
    ],
)
async def create_session(
    body: CreateSessionRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _ensure_enabled()
    user_id = _resolve_user_id(authorization)
    runtime = get_runtime()
    try:
        session = runtime.store.create_session(
            user_id=user_id,
            question_id=body.question_id,
            question_stem=body.question_stem,
        )
    except DailyQuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {"session": session}


@router.post("/sessions/{session_id}/pages")
async def upload_page(
    session_id: str,
    file: bytes = File(...),
    page_index: int = Form(...),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _ensure_enabled()
    user_id = _resolve_user_id(authorization)
    runtime = get_runtime()
    session = _owned_session(runtime, session_id, user_id)
    if session["status"] not in ("created", "pages_uploaded"):
        raise HTTPException(status_code=409, detail=f"Cannot add pages in status {session['status']}")
    if len(runtime.store.list_pages(session_id)) >= _MAX_PAGES_PER_SESSION:
        raise HTTPException(status_code=409, detail="Page limit reached")
    if not file:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(file) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")

    clean = _strip_exif_reencode(file)
    quality = assess_image_quality(clean)
    content_hash = hashlib.sha256(clean).hexdigest()
    filename = f"{session_id}-p{int(page_index)}-{uuid.uuid4().hex[:8]}.jpg"
    dest = runtime.images_root / session_id
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / filename
    path.write_bytes(clean)

    try:
        page = runtime.store.add_page(
            session_id,
            page_index=int(page_index),
            image_ref=json.dumps({"path": str(path)}, ensure_ascii=False),
            content_hash=content_hash,
            quality=quality,
        )
        if session["status"] == "created":
            runtime.store.set_session_status(session_id, "pages_uploaded")
    except Exception as exc:
        path.unlink(missing_ok=True)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=409, detail=f"Page rejected: {exc}") from exc

    page_out = dict(page)
    page_out["quality"] = quality
    return {"page": page_out}


@router.post("/sessions/{session_id}/submit")
async def submit_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _ensure_enabled()
    user_id = _resolve_user_id(authorization)
    runtime = get_runtime()
    session = _owned_session(runtime, session_id, user_id)
    if not runtime.store.list_pages(session_id):
        raise HTTPException(status_code=409, detail="No pages uploaded")
    if session["status"] not in ("pages_uploaded", "failed", "processing"):
        raise HTTPException(status_code=409, detail=f"Cannot submit in status {session['status']}")
    svc = runtime.service()
    try:
        job = svc.submit(session_id)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(svc.process_job, str(job["id"]))
    return {"job": job}


@router.get("/sessions/{session_id}")
async def get_session_status(
    session_id: str,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _ensure_enabled()
    user_id = _resolve_user_id(authorization)
    runtime = get_runtime()
    session = _owned_session(runtime, session_id, user_id)
    svc = runtime.service()

    job = runtime.store.get_latest_job(session_id)
    # 轮询驱动恢复（plan §5 / Codex C3）：running 但 lease 过期 = 进程重启遗孤。
    # 恢复逻辑下沉到 store.recover_stale_job（WHERE status='running' 守卫，
    # 终态 job 永不被重置重派）；只有确实 reset 成功才重新派发。
    if (
        job is not None
        and job["status"] == "running"
        and float(job["lease_until"]) < time.time()
    ):
        if runtime.store.recover_stale_job(str(job["id"])):
            logger.info("photo_answer recovering stale job %s", job["id"])
            background_tasks.add_task(svc.process_job, str(job["id"]))

    out: dict[str, Any] = {"session": runtime.store.get_session(session_id), "job": job}
    if (out["session"] or {}).get("status") in ("awaiting_confirm", "confirmed", "submitted"):
        view = svc.get_view(session_id)
        out["view"] = {
            "draft_text": view["draft_text"],
            "raw_text": view["raw_text"],
            "paragraphs": view["paragraphs"],
            "suspicions": view["suspicions"],
        }
    return out


@router.post("/sessions/{session_id}/confirm")
async def confirm_session(
    session_id: str,
    body: ConfirmRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _ensure_enabled()
    user_id = _resolve_user_id(authorization)
    runtime = get_runtime()
    _owned_session(runtime, session_id, user_id)
    svc = runtime.service()
    try:
        result = svc.confirm(
            session_id,
            confirmed_text=body.confirmed_text,
            job_version=body.job_version,
            ack_normal_suspicions=body.ack_normal_suspicions,
            resolved_span_ids=body.resolved_span_ids,
            diff=body.diff,
            edited_char_count=body.edited_char_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PhotoAnswerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return result


@router.post("/sessions/{session_id}/retry")
async def retry_session(
    session_id: str,
    body: RetryRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _ensure_enabled()
    user_id = _resolve_user_id(authorization)
    runtime = get_runtime()
    session = _owned_session(runtime, session_id, user_id)
    svc = runtime.service()

    if body.mode == "escalate":
        if body.page_index is None:
            raise HTTPException(status_code=400, detail="page_index required for escalate")
        try:
            view = svc.escalate_page(session_id, page_index=int(body.page_index))
        except EscalationLimitReached as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except BudgetExceeded as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except EngineNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (KeyError, PhotoAnswerError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "view": {
                "draft_text": view["draft_text"],
                "raw_text": view["raw_text"],
                "paragraphs": view["paragraphs"],
                "suspicions": view["suspicions"],
            }
        }

    # mode == rerun：失败后整体重跑（新 job_version，旧 confirm 会被 409）
    if session["status"] not in ("failed", "awaiting_confirm"):
        raise HTTPException(status_code=409, detail=f"Cannot rerun in status {session['status']}")
    job = svc.submit(session_id, idempotency_key=f"retry-{uuid.uuid4().hex[:8]}")
    background_tasks.add_task(svc.process_job, str(job["id"]))
    return {"job": job}
