from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
from datetime import datetime, timedelta
from typing import Any, Iterable
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator

from deeptutor.api.dependencies import (
    AuthContext,
    require_self_or_admin,
    resolve_auth_context,
    resolve_wallet_user_id,
    route_rate_limit,
)
from deeptutor.contracts.bot_runtime_defaults import CONSTRUCTION_EXAM_BOT_DEFAULTS
from deeptutor.contracts.unified_turn import UnifiedTurnStartResponse, build_turn_stream_bootstrap
from deeptutor.services.learner_state import LearnerStateService
from deeptutor.services.learner_state.attempt_detail_read_model import build_attempt_detail_read_model
from deeptutor.services.learner_state.learning_brain_read_model import build_learning_brain_read_model
from deeptutor.services.learner_state.learning_report_read_model import build_learning_report_read_model
from deeptutor.services.learner_state.mistake_book import MistakeBookConflict, MistakeBookService
from deeptutor.services.notebook_card.service import get_notebook_card_service
from deeptutor.services.internal_qa import (
    EVAL_BILLING_BYPASS_HEADER,
    eval_billing_bypass_signature_valid,
    internal_qa_billing_bypass_allowed,
    internal_qa_billing_bypass_enabled,
)
from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.member_usage_meter import get_member_usage_meter
from deeptutor.services.assessment import AssessmentBlueprintUnavailable
from deeptutor.services.assessment.session_repository import (
    AssessmentLeaseConflict,
    AssessmentSessionRateLimited,
    AssessmentSessionConflict,
    AssessmentSessionError,
    AssessmentSessionExpired,
    AssessmentSessionNotFound,
)
from deeptutor.services.query_intent import (
    build_grounding_decision,
)
from deeptutor.services.search import is_web_search_runtime_available
from deeptutor.services.feedback_service import (
    SupabaseFeedbackStore,
    build_mobile_feedback_row,
)
from deeptutor.logging.context import get_request_id
from deeptutor.services.render_presentation import build_canonical_presentation
from deeptutor.services.session import (
    build_user_owner_key,
    get_sqlite_session_store,
    get_turn_runtime_manager,
)
from deeptutor.services.storage import get_attachment_store
from deeptutor.tutorbot.utils.helpers import safe_filename
from deeptutor.services.session.turn_runtime import _MINI_PROGRAM_CAPTURE_COST
from deeptutor.services.wallet import (
    WalletLedgerEntry,
    WalletSnapshot,
    get_wallet_service,
    is_billing_enforcement_enabled,
)
from deeptutor.tutorbot.response_mode import normalize_requested_response_mode

router = APIRouter()
logger = logging.getLogger(__name__)
member_service = get_member_console_service()
learner_state_service = LearnerStateService()
mistake_book_service = MistakeBookService()
turn_runtime = get_turn_runtime_manager()
session_store = get_sqlite_session_store()
wallet_service = get_wallet_service()

_MOBILE_TUTORBOT_ID = CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0]
_MOBILE_TUTORBOT_NAME = "Construction Exam Coach"
_MOBILE_CHAT_START_TURN_DEPENDENCIES = [
    Depends(
        route_rate_limit(
            "mobile_chat_start_turn",
            default_max_requests=10,
            default_window_seconds=60.0,
        )
    ),
    # Per-user DAILY turn budget (economic-DoS guard), mirroring the /api/v1/ws
    # ws_start_turn_daily cap. Burst limit above stops spikes; this stops sustained
    # burn (10/min for 24h ≈ 14k paid LLM calls/day on one account).
    Depends(
        route_rate_limit(
            "mobile_chat_start_turn_daily",
            default_max_requests=500,
            default_window_seconds=86400.0,
        )
    ),
]
_MOBILE_TUTORBOT_DESCRIPTION = "微信小程序主聊天默认建筑实务 TutorBot"
_MOBILE_PLACEHOLDER_TITLES = {"", "new conversation", "新对话"}
_MOBILE_CONVERSATION_LOOKUP_PAGE_SIZE = 500
MobileFeedbackSupabaseClient = SupabaseFeedbackStore
_FEEDBACK_ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024

# H9: hard upper bound on the mobile HTTP /chat/start-turn query text, mirroring the
# F5 WS frame cap (unified_ws._MAX_WS_INBOUND_FRAME_CHARS). start-turn is the second
# inbound boundary that can launch an expensive turn; without a cap it reopens the
# same amplification surface F5 closed on the WS side. Over-limit -> 422 fail-fast.
_MAX_MOBILE_START_TURN_QUERY_CHARS = 128 * 1024

_BILLING_USAGE_TZ = ZoneInfo("Asia/Shanghai")
_BILLING_USAGE_LEDGER_WINDOW = 500
_BILLING_INCLUDE_LEGACY_LEDGER = "DEEPTUTOR_BILLING_INCLUDE_LEGACY_LEDGER"
_BILLING_SHADOW_COMPARE_LEGACY_WALLET = "DEEPTUTOR_BILLING_SHADOW_COMPARE_LEGACY_WALLET"
_LOCAL_WALLET_FALLBACK = "DEEPTUTOR_ALLOW_LOCAL_WALLET_FALLBACK"
_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK = "DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK"
_MISTAKE_BOOK_ENABLED = "DEEPTUTOR_MISTAKE_BOOK_ENABLED"
_MISTAKE_BOOK_WRITE_ENABLED = "DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED"
_BILLING_PLAN_REFERENCE_POINTS = {
    "vip": 9000,
    "svip": 28000,
    "supreme_svip": 50000,
}
_BILLING_PLAN_ALIASES = {
    "": "vip",
    "trial": "vip",
    "vip": "vip",
    "standard": "vip",
    "starter": "vip",
    "precision": "vip",
    "jingxue": "vip",
    "advance": "vip",
    "svip": "svip",
    "pro": "svip",
    "pass": "svip",
    "tongguan": "svip",
    "sprint": "svip",
    "supreme_svip": "supreme_svip",
    "ultimate": "supreme_svip",
    "至尊svip": "supreme_svip",
}
_BILLING_PAYMENT_CHANNELS = {"wechat", "alipay"}
_BILLING_PAYMENT_GATEWAY_URL = "DEEPTUTOR_PAYMENT_GATEWAY_URL"


class BillingCheckoutRequest(BaseModel):
    package_id: str = Field(min_length=1, max_length=64)
    channel: str = Field(default="wechat", min_length=1, max_length=32)


class MistakeBookSaveRequest(BaseModel):
    attempt_ref: str = Field(min_length=1)
    subject_id: str = Field(min_length=1, max_length=128)
    bot_id: str = Field(default="", max_length=128)
    title: str = Field(default="", max_length=300)
    concept_label: str = Field(default="", max_length=128)
    error_label: str = Field(default="", max_length=128)
    note: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list)


def _log_safe_id(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= 14:
        return text
    return f"{text[:8]}...{text[-4:]}"


def _ts_to_iso(timestamp: float | int | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(float(timestamp)).isoformat()


def _ts_to_ms(timestamp: float | int | None) -> int:
    if not timestamp:
        return 0
    return int(round(float(timestamp) * 1000))


def _resolve_authenticated_user_id(authorization: str | None) -> str:
    current_user = resolve_auth_context(authorization)
    if current_user is None or not str(current_user.user_id or "").strip():
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(current_user.user_id).strip()


def feedback_attachment_session_id(user_id: str) -> str:
    normalized = safe_filename(str(user_id or "").strip())
    if not normalized:
        raise HTTPException(status_code=401, detail="Authentication required")
    return f"feedback-{normalized}"


def _resolve_wallet_lookup_user_id(authorization: str | None) -> str:
    return str(resolve_wallet_user_id(authorization) or "").strip()


def _micros_to_points(value: int | float | None) -> int:
    try:
        micros = int(value or 0)
    except (TypeError, ValueError):
        micros = 0
    return int(round(micros / 1_000_000))


def _points_to_micros(value: int | float | None) -> int:
    try:
        points = int(value or 0)
    except (TypeError, ValueError):
        points = 0
    return points * 1_000_000


def _wallet_packages() -> list[dict[str, Any]]:
    getter = getattr(member_service, "_default_packages", None)
    if callable(getter):
        try:
            return list(getter() or [])
        except Exception:
            return []
    return []


def _billing_package_by_id(package_id: str) -> dict[str, Any] | None:
    normalized_package_id = str(package_id or "").strip()
    if not normalized_package_id:
        return None
    for package in _wallet_packages():
        if str(package.get("id") or "").strip() == normalized_package_id:
            return dict(package)
    return None


def _price_to_fen(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return int(round(float(text) * 100))
    except (TypeError, ValueError):
        return 0


def _payment_gateway_url() -> str:
    return str(os.getenv(_BILLING_PAYMENT_GATEWAY_URL, "") or "").strip().rstrip("/")


def _env_flag_enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _learning_brain_local_projection_fallback_enabled() -> bool:
    return (
        str(os.getenv("DEEPTUTOR_ENV", "") or "").strip().lower() == "local"
        and _env_flag_enabled("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA")
        and _env_flag_enabled(_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK)
    )


def _require_mistake_book_read_enabled() -> None:
    if not _env_flag_enabled(_MISTAKE_BOOK_ENABLED):
        raise HTTPException(status_code=404, detail="mistake_book_disabled")


def _require_mistake_book_write_enabled() -> None:
    if not _env_flag_enabled(_MISTAKE_BOOK_WRITE_ENABLED):
        raise HTTPException(status_code=404, detail="mistake_book_write_disabled")


def _shadow_compare_wallet_read(user_id: str, *, balance_points: int, source: str) -> None:
    if not _env_flag_enabled(_BILLING_SHADOW_COMPARE_LEGACY_WALLET):
        return
    try:
        legacy_wallet = member_service.get_wallet(user_id)
    except Exception:
        return
    legacy_balance = int((legacy_wallet or {}).get("balance") or 0)
    if legacy_balance != int(balance_points):
        logger.warning(
            "wallet shadow diff detected: source=%s user_id=%s legacy_balance=%s wallet_balance=%s",
            source,
            user_id,
            legacy_balance,
            balance_points,
        )


def _internal_qa_wallet_snapshot_or_none(
    user_id: str,
    *,
    identity_candidates: Iterable[Any] = (),
    fallback_points: int = 0,
) -> WalletSnapshot | None:
    candidates = [
        user_id,
        *identity_candidates,
        *_internal_qa_member_identity_candidates(user_id),
    ]
    if not internal_qa_billing_bypass_allowed(*candidates):
        return None
    points = max(int(fallback_points or 0), 0)
    return WalletSnapshot(
        user_id=str(user_id or "").strip(),
        balance_micros=points * 1_000_000,
        frozen_micros=0,
        plan_id="internal_qa",
        version=0,
        created_at="",
    )


def _wallet_snapshot_or_zero(
    user_id: str,
    *,
    identity_candidates: Iterable[Any] = (),
    fallback_points: int = 0,
) -> WalletSnapshot:
    internal_qa_snapshot = _internal_qa_wallet_snapshot_or_none(
        user_id,
        identity_candidates=identity_candidates,
        fallback_points=fallback_points,
    )
    if internal_qa_snapshot is not None:
        return internal_qa_snapshot
    if not getattr(wallet_service, "is_configured", False):
        if _env_flag_enabled(_LOCAL_WALLET_FALLBACK):
            return WalletSnapshot(
                user_id=str(user_id or "").strip(),
                balance_micros=0,
                frozen_micros=0,
                plan_id="local",
                version=0,
                created_at="",
            )
        raise HTTPException(status_code=503, detail="Wallet service unavailable")
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return WalletSnapshot(
            user_id="",
            balance_micros=0,
            frozen_micros=0,
            plan_id="",
            version=0,
            created_at="",
        )
    try:
        snapshot = wallet_service.get_wallet(normalized_user_id)
    except Exception as exc:
        logger.warning("wallet lookup failed for user_id=%s: %s", normalized_user_id, exc)
        raise HTTPException(status_code=503, detail="Wallet service unavailable") from exc
    if snapshot is not None:
        return snapshot
    return WalletSnapshot(
        user_id=user_id,
        balance_micros=0,
        frozen_micros=0,
        plan_id="",
        version=0,
        created_at="",
    )


def _serialize_wallet_snapshot(snapshot: WalletSnapshot) -> dict[str, Any]:
    balance_points = _micros_to_points(snapshot.balance_micros)
    frozen_points = _micros_to_points(snapshot.frozen_micros)
    return {
        "user_id": snapshot.user_id,
        "balance": balance_points,
        "points": balance_points,
        "display_balance": balance_points,
        "balance_micros": int(snapshot.balance_micros),
        "frozen": frozen_points,
        "frozen_micros": int(snapshot.frozen_micros),
        "plan_id": snapshot.plan_id,
        "tier": snapshot.plan_id or "",
        "version": int(snapshot.version),
        "created_at": snapshot.created_at,
        "packages": _wallet_packages(),
    }


def _ledger_reason(entry: WalletLedgerEntry) -> str:
    metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
    explicit_reason = str(metadata.get("reason") or "").strip()
    if explicit_reason:
        return explicit_reason
    if entry.event_type == "debit" and entry.reference_type == "ai_usage":
        return "capture"
    if entry.event_type == "grant" and entry.reference_type == "order":
        return "purchase"
    if entry.event_type == "grant" and entry.reference_type in {"signup", "signup_bonus"}:
        return "signup_bonus"
    if entry.event_type == "admin_adjust" and entry.delta_micros >= 0:
        return "admin_grant"
    if entry.event_type == "refund":
        return "refund"
    return entry.event_type


def _serialize_wallet_ledger_entry(entry: WalletLedgerEntry) -> dict[str, Any]:
    delta_points = _micros_to_points(entry.delta_micros)
    balance_after_points = _micros_to_points(entry.balance_after_micros)
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "event_type": entry.event_type,
        "reason": _ledger_reason(entry),
        "delta": delta_points,
        "delta_micros": int(entry.delta_micros),
        "balance_after": balance_after_points,
        "balance_after_micros": int(entry.balance_after_micros),
        "frozen_after_micros": int(entry.frozen_after_micros),
        "reference_type": entry.reference_type,
        "reference_id": entry.reference_id,
        "idempotency_key": entry.idempotency_key,
        "metadata": dict(entry.metadata or {}),
        "created_at": entry.created_at,
    }


def _normalize_billing_plan_id(plan_id: str | None) -> str:
    raw = str(plan_id or "").strip().lower()
    return _BILLING_PLAN_ALIASES.get(raw, "vip")


def _billing_usage_reference_points_for_plan(plan_id: str | None) -> int:
    normalized = _normalize_billing_plan_id(plan_id)
    return int(_BILLING_PLAN_REFERENCE_POINTS.get(normalized) or _BILLING_PLAN_REFERENCE_POINTS["vip"])


def _parse_ledger_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_BILLING_USAGE_TZ)
    return parsed.astimezone(_BILLING_USAGE_TZ)


def _is_ai_usage_debit(entry: WalletLedgerEntry) -> bool:
    if int(entry.delta_micros or 0) >= 0:
        return False
    reason = _ledger_reason(entry)
    return entry.event_type == "debit" or entry.reference_type == "ai_usage" or reason == "capture"


def _build_billing_usage_payload(
    entries: list[WalletLedgerEntry],
    *,
    now: datetime | None = None,
    plan_id: str | None = None,
    limit_points_by_window: dict[str, int] | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(_BILLING_USAGE_TZ)).astimezone(_BILLING_USAGE_TZ)
    _ = limit_points_by_window
    total_used_micros = 0
    total_credit_micros = 0
    latest_balance_micros = 0
    latest_created_at: datetime | None = None

    for entry in entries:
        created_at = _parse_ledger_datetime(entry.created_at)
        if created_at is None:
            created_at = current
        if latest_created_at is None or created_at >= latest_created_at:
            latest_created_at = created_at
            latest_balance_micros = max(0, int(entry.balance_after_micros or 0))
        amount = abs(int(entry.delta_micros or 0))
        if _is_ai_usage_debit(entry):
            total_used_micros += amount
        elif int(entry.delta_micros or 0) > 0:
            total_credit_micros += int(entry.delta_micros or 0)

    observed_reference_micros = max(
        1,
        total_credit_micros,
        latest_balance_micros + total_used_micros,
        latest_balance_micros,
    )
    package_reference_micros = int(_billing_usage_reference_points_for_plan(plan_id)) * 1_000_000
    reference_micros = (
        observed_reference_micros
        if observed_reference_micros > total_used_micros
        else max(1, package_reference_micros)
    )
    remaining_basis_micros = (
        latest_balance_micros
        if latest_balance_micros > 0 or total_credit_micros > 0
        else max(0, reference_micros - total_used_micros)
    )
    remaining_percent = int(round((remaining_basis_micros / reference_micros) * 100)) if entries else 100
    remaining_percent = max(0, min(100, remaining_percent))
    return {
        "status": "ok",
        "display": {
            "primary_label": f"剩余 {remaining_percent}%",
            "primary_percent": remaining_percent,
            "limited_by": "membership_balance",
            "plan_id": _normalize_billing_plan_id(plan_id),
        },
        "quota": {
            "rows": [],
        },
    }


def _load_billing_usage_entries(
    authorization: str | None,
    *,
    wallet_user_id: str,
    limit: int,
) -> list[WalletLedgerEntry]:
    wallet_rows = wallet_service.list_wallet_ledger(
        wallet_user_id,
        limit=limit,
        offset=0,
    )
    legacy_rows = (
        _load_legacy_wallet_ledger_entries(
            authorization,
            wallet_user_id=wallet_user_id,
            limit=limit,
        )
        if _env_flag_enabled(_BILLING_INCLUDE_LEGACY_LEDGER)
        else []
    )
    return _merge_wallet_ledger_entries(wallet_rows, legacy_rows)


def _usage_meter_event_created_at_iso(event: Any) -> str:
    created_at = getattr(event, "created_at", None)
    if isinstance(created_at, (int, float)):
        return datetime.fromtimestamp(float(created_at), tz=_BILLING_USAGE_TZ).isoformat()
    parsed = _parse_ledger_datetime(str(created_at or ""))
    return parsed.isoformat() if parsed else datetime.now(_BILLING_USAGE_TZ).isoformat()


def _usage_meter_events_as_ledger_entries(
    events: Iterable[Any],
    *,
    amount_points_per_event: int | None = None,
) -> list[WalletLedgerEntry]:
    entries: list[WalletLedgerEntry] = []
    for event in events:
        amount_points = max(
            0,
            int(
                amount_points_per_event
                if amount_points_per_event is not None
                else getattr(event, "amount_points", 0)
                or 0
            ),
        )
        if amount_points <= 0:
            continue
        wallet_user_id = str(getattr(event, "wallet_user_id", "") or "").strip()
        event_id = str(getattr(event, "event_id", "") or "").strip()
        turn_id = str(getattr(event, "turn_id", "") or "").strip()
        metadata = getattr(event, "metadata", {}) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        entries.append(
            WalletLedgerEntry(
                id=f"usage_meter:{event_id or turn_id}",
                user_id=wallet_user_id,
                event_type="debit",
                delta_micros=-(amount_points * 1_000_000),
                balance_after_micros=0,
                frozen_after_micros=0,
                reference_type="ai_usage",
                reference_id=turn_id,
                idempotency_key=f"usage_meter:{event_id or turn_id}",
                metadata={
                    "reason": "capture",
                    "usage_meter_status": str(getattr(event, "status", "") or ""),
                    **metadata,
                },
                created_at=_usage_meter_event_created_at_iso(event),
            )
        )
    return entries


def _load_member_usage_meter_events(
    *,
    wallet_user_id: str,
    limit: int,
) -> list[Any]:
    return get_member_usage_meter().list_usage_events(
        wallet_user_id,
        limit=limit,
        offset=0,
    )


def _build_internal_beta_usage_payload(
    events: list[Any],
    *,
    plan_id: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(_BILLING_USAGE_TZ)).astimezone(_BILLING_USAGE_TZ)
    unit_points = int(_MINI_PROGRAM_CAPTURE_COST)
    entries = _usage_meter_events_as_ledger_entries(
        events,
        amount_points_per_event=unit_points,
    )
    payload = _build_billing_usage_payload(
        entries,
        now=current,
        plan_id=plan_id,
    )
    return payload


def _billing_storage_unavailable(exc: Exception, *, source: str) -> HTTPException:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    logger.warning("billing storage unavailable: source=%s status=%s error=%s", source, status_code, exc)
    return HTTPException(status_code=503, detail="Billing storage unavailable")


def _degraded_billing_usage_payload(*, plan_id: str | None = None) -> dict[str, Any]:
    return {
        "status": "degraded",
        "reason": "billing_storage_unavailable",
        "display": {
            "primary_label": "权益暂不可用",
            "primary_percent": 100,
            "limited_by": "membership_balance",
            "plan_id": _normalize_billing_plan_id(plan_id),
        },
        "quota": {
            "rows": [],
        },
    }


def _build_local_checkout_payload(
    *,
    user_id: str,
    wallet_user_id: str,
    package: dict[str, Any],
    channel: str,
) -> dict[str, Any]:
    package_id = str(package.get("id") or "").strip()
    price = str(package.get("price") or "").strip()
    amount_fen = _price_to_fen(price)
    order_id = f"dt_{channel}_{uuid4().hex}"
    payment_type = "wechat_mp" if channel == "wechat" else "alipay_qr"
    return {
        "status": "payment_config_missing",
        "order_id": order_id,
        "channel": channel,
        "user_id": user_id,
        "wallet_user_id": wallet_user_id,
        "package": {
            "id": package_id,
            "label": str(package.get("label") or ""),
            "price": price,
            "points": int(package.get("points") or 0),
            "turns": int(package.get("turns") or 0),
            "original_price": str(package.get("original_price") or ""),
        },
        "amount_fen": amount_fen,
        "currency": "CNY",
        "payment": {
            "type": payment_type,
            "params": None,
            "qr_code_url": "",
        },
        "message": (
            "Missing payment gateway config. Set DEEPTUTOR_PAYMENT_GATEWAY_URL "
            "or connect WeChat Pay / Alipay provider credentials."
        ),
    }


async def _create_payment_gateway_order(payload: dict[str, Any]) -> dict[str, Any] | None:
    gateway_url = _payment_gateway_url()
    if not gateway_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(f"{gateway_url}/orders", json=payload)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("payment gateway order creation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Payment gateway unavailable") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Payment gateway returned invalid payload")
    return data


def _assert_wallet_balance_available(wallet_user_id: str) -> None:
    """Hard balance gate run before start-turn when enforcement is ON.

    Reads the canonical wallet snapshot and fails closed (429
    billing_quota_exceeded) when the available balance cannot cover this
    turn's minimum charge. Per contracts/turn.md:69 this runs before
    turn_runtime.start_turn, so no pending turn is created and no answer is
    delivered. Explicit internal-beta OFF override keeps this a no-op.
    """
    if not is_billing_enforcement_enabled():
        return
    snapshot = wallet_service.get_wallet(wallet_user_id)
    if snapshot is None:
        available_micros = 0
    else:
        available_micros = int(snapshot.balance_micros) - int(snapshot.frozen_micros)
    minimum_charge_micros = int(_MINI_PROGRAM_CAPTURE_COST) * 1_000_000
    if available_micros >= minimum_charge_micros:
        return
    raise HTTPException(
        status_code=429,
        detail={
            "code": "billing_quota_exceeded",
            "message": "Insufficient wallet balance for this turn.",
            "limited_by": "balance",
            "available_micros": max(available_micros, 0),
            "required_micros": minimum_charge_micros,
        },
    )


def _eval_bypass_identity_candidates(*user_ids: str) -> list[str]:
    """Resolve identities (incl. usernames) for the eval-bypass cohort check.

    Unlike _internal_qa_member_identity_candidates this is not gated on the
    non-production QA flag: eval bypass is production-capable, so the username
    must be resolvable in production to enforce the qa_/test_/operator_ cohort
    scope. Profile reads are best-effort; the uuid is always included.
    """

    candidates: list[str] = []

    def _append(value: Any) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    for user_id in user_ids:
        _append(user_id)
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            continue
        try:
            profile = member_service.get_profile(normalized_user_id)
        except Exception:
            continue
        if not isinstance(profile, dict):
            continue
        for key in ("user_id", "username", "auth_username", "external_auth_user_id"):
            _append(profile.get(key))
    return candidates


def _internal_qa_member_identity_candidates(*user_ids: str) -> list[str]:
    if not internal_qa_billing_bypass_enabled():
        return []
    candidates: list[str] = []

    def _append(value: Any) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    for user_id in user_ids:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            continue
        try:
            profile = member_service.get_profile(normalized_user_id)
        except Exception:
            continue
        if not isinstance(profile, dict):
            continue
        for key in ("user_id", "username", "auth_username", "external_auth_user_id"):
            _append(profile.get(key))
    return candidates


def _assert_billing_quota_available(
    authorization: str | None,
    *,
    wallet_user_id: str,
    authenticated_user_id: str = "",
    eval_bypass_verified: bool = False,
) -> None:
    if not is_billing_enforcement_enabled():
        return
    if eval_bypass_verified:
        # Key-gated eval bypass already verified at the request boundary against a
        # QA-cohort identity. Audit every grant so abuse of a leaked key is visible.
        logger.warning(
            "eval billing bypass granted at start-turn gate: user_id=%s wallet_user_id=%s",
            _log_safe_id(authenticated_user_id),
            _log_safe_id(wallet_user_id),
        )
        return
    identity_candidates = [
        authenticated_user_id,
        wallet_user_id,
        *_resolve_legacy_ledger_candidate_user_ids(authorization),
    ]
    identity_candidates.extend(_internal_qa_member_identity_candidates(*identity_candidates))
    if internal_qa_billing_bypass_allowed(
        *identity_candidates,
    ):
        return
    normalized_user_id = str(wallet_user_id or "").strip()
    if not normalized_user_id or not getattr(wallet_service, "is_configured", False):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "billing_wallet_unavailable",
                "message": "Billing wallet service is unavailable.",
                "limited_by": "wallet_service",
            },
        )
    _assert_wallet_balance_available(normalized_user_id)
    try:
        usage_payload = _build_billing_usage_payload(
            _load_billing_usage_entries(
                authorization,
                wallet_user_id=normalized_user_id,
                limit=_BILLING_USAGE_LEDGER_WINDOW,
            ),
            plan_id=_wallet_snapshot_or_zero(normalized_user_id).plan_id,
        )
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning(
            "billing quota gate skipped: wallet_user_id=%s status=%s error=%s",
            _log_safe_id(normalized_user_id),
            status_code,
            exc,
        )
        return
    rows = ((usage_payload.get("quota") or {}).get("rows") or []) if isinstance(usage_payload, dict) else []
    exhausted = [
        row
        for row in rows
        if isinstance(row, dict) and int(row.get("remaining_percent") or 0) <= 0
    ]
    if not exhausted:
        return
    primary = min(exhausted, key=lambda row: int(row.get("remaining_percent") or 0))
    raise HTTPException(
        status_code=429,
        detail={
            "code": "billing_quota_exceeded",
            "message": "Usage quota exceeded.",
            "limited_by": str(primary.get("key") or ""),
            "reset_at": str(primary.get("reset_at") or ""),
            "quota": rows,
        },
    )


def _legacy_ledger_event_type(reason: str, delta_points: int) -> str:
    normalized_reason = str(reason or "").strip().lower()
    if normalized_reason == "refund":
        return "refund"
    if delta_points < 0:
        return "debit"
    if normalized_reason in {"purchase", "signup_bonus", "grant", "admin_grant"}:
        return "grant"
    return "admin_adjust"


def _resolve_legacy_ledger_candidate_user_ids(authorization: str | None) -> list[str]:
    current_user = resolve_auth_context(authorization)
    candidates: list[str] = []

    def _append(value: Any) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    if current_user is None:
        return candidates
    _append(current_user.user_id)
    claims = current_user.claims if isinstance(current_user.claims, dict) else {}
    _append(claims.get("uid"))
    _append(claims.get("sub"))
    _append(claims.get("canonical_uid"))
    return candidates


def _load_legacy_wallet_ledger_entries(
    authorization: str | None,
    *,
    wallet_user_id: str,
    limit: int,
) -> list[WalletLedgerEntry]:
    if limit <= 0:
        return []
    candidates = _resolve_legacy_ledger_candidate_user_ids(authorization)
    if not candidates:
        return []

    merged: list[WalletLedgerEntry] = []
    seen_keys: set[tuple[str, str, int, str]] = set()
    for candidate_user_id in candidates:
        try:
            profile = member_service.get_profile(candidate_user_id)
            ledger_payload = member_service.get_ledger(candidate_user_id, limit=limit, offset=0)
        except Exception:
            continue
        raw_entries = ledger_payload.get("entries") if isinstance(ledger_payload, dict) else []
        if not isinstance(raw_entries, list) or not raw_entries:
            continue
        running_balance_points = int((profile or {}).get("points") or 0)
        sorted_entries = sorted(
            [dict(item) for item in raw_entries if isinstance(item, dict)],
            key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")),
            reverse=True,
        )
        for item in sorted_entries:
            delta_points = int(item.get("delta") or 0)
            reason = str(item.get("reason") or "").strip()
            created_at = str(item.get("created_at") or "").strip()
            legacy_id = str(item.get("id") or "").strip()
            dedupe_key = (created_at, reason, delta_points, legacy_id)
            if dedupe_key in seen_keys:
                running_balance_points -= delta_points
                continue
            seen_keys.add(dedupe_key)
            merged.append(
                WalletLedgerEntry(
                    id=f"legacy:{candidate_user_id}:{legacy_id or created_at}",
                    user_id=wallet_user_id or candidate_user_id,
                    event_type=_legacy_ledger_event_type(reason, delta_points),
                    delta_micros=_points_to_micros(delta_points),
                    balance_after_micros=_points_to_micros(running_balance_points),
                    frozen_after_micros=0,
                    reference_type="legacy_member_console",
                    reference_id=legacy_id,
                    idempotency_key=f"legacy:{candidate_user_id}:{legacy_id or created_at}",
                    metadata={
                        "reason": reason,
                        "source": "legacy_member_console",
                        "legacy_user_id": candidate_user_id,
                        "legacy_entry_id": legacy_id,
                    },
                    created_at=created_at,
                )
            )
            running_balance_points -= delta_points
    merged.sort(key=lambda item: (item.created_at, item.id), reverse=True)
    return merged[:limit]


def _merge_wallet_ledger_entries(
    wallet_entries: list[WalletLedgerEntry],
    legacy_entries: list[WalletLedgerEntry],
) -> list[WalletLedgerEntry]:
    merged: list[WalletLedgerEntry] = []
    seen_keys: set[tuple[str, str, int, str]] = set()
    for entry in [*wallet_entries, *legacy_entries]:
        reason = _ledger_reason(entry)
        dedupe_key = (entry.created_at, reason, int(entry.delta_micros), str(entry.reference_id or ""))
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        merged.append(entry)
    merged.sort(key=lambda item: (item.created_at, item.id), reverse=True)
    return merged


async def _assert_mobile_conversation_access(conversation_id: str, user_id: str) -> None:
    resolved_conversation_id = str(conversation_id or "").strip()
    if not resolved_conversation_id:
        return
    variants = await _load_mobile_conversation_variants(resolved_conversation_id, user_id)
    if variants:
        return
    raise HTTPException(status_code=404, detail="Conversation not found")


async def _resolve_mobile_runtime_session_id(
    conversation_id: str,
    user_id: str,
) -> tuple[str | None, str | None]:
    resolved_conversation_id = str(conversation_id or "").strip()
    if not resolved_conversation_id:
        return None, None

    variants = await _load_mobile_conversation_variants(resolved_conversation_id, user_id)
    if not variants:
        raise HTTPException(status_code=404, detail="Conversation not found")

    def session_id_for(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("session_id") or "").strip()

    def public_id_for(row: dict[str, Any]) -> str:
        return _normalize_mobile_conversation_id(row) or resolved_conversation_id

    def is_synthetic_direct(row: dict[str, Any]) -> bool:
        return set(row.keys()) <= {"id"} and session_id_for(row) == resolved_conversation_id

    for row in variants:
        if not isinstance(row, dict):
            continue
        session_id = session_id_for(row)
        if session_id == resolved_conversation_id:
            return session_id, public_id_for(row)

    rich_variants = [row for row in variants if isinstance(row, dict) and not is_synthetic_direct(row)]
    for row in rich_variants:
        session_id = session_id_for(row)
        if session_id:
            return session_id, public_id_for(row)
    for row in variants:
        if not isinstance(row, dict):
            continue
        session_id = session_id_for(row)
        if session_id:
            return session_id, public_id_for(row)
    raise HTTPException(status_code=404, detail="Conversation not found")


def _new_mobile_conversation_id() -> str:
    return f"tb_{uuid4().hex[:24]}"


def _infer_mobile_conversation_title(text: str) -> str:
    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        return "新对话"
    return normalized[:32] + ("..." if len(normalized) > 32 else "")


def _normalize_mobile_conversation_id(session: dict[str, Any]) -> str:
    session_id = str(session.get("id") or session.get("session_id") or "").strip()
    preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
    conversation_id = str(preferences.get("conversation_id") or "").strip()
    if session_id.startswith("tutorbot:") and conversation_id:
        return conversation_id
    return session_id


def _merge_mobile_conversation_preferences(
    current_preferences: dict[str, Any],
    row_preferences: dict[str, Any],
    *,
    prefer_row: bool,
) -> dict[str, Any]:
    merged = dict(current_preferences or {})
    row_prefs = dict(row_preferences or {})

    for key, value in row_prefs.items():
        if key == "interaction_hints" or value in (None, ""):
            continue
        if prefer_row or key not in merged or merged.get(key) in (None, ""):
            merged[key] = value

    current_hints = (
        merged.get("interaction_hints")
        if isinstance(merged.get("interaction_hints"), dict)
        else {}
    )
    row_hints = (
        row_prefs.get("interaction_hints")
        if isinstance(row_prefs.get("interaction_hints"), dict)
        else {}
    )
    if row_hints:
        merged_hints = dict(current_hints)
        for key, value in row_hints.items():
            if value in (None, ""):
                continue
            if prefer_row or key not in merged_hints or merged_hints.get(key) in (None, ""):
                merged_hints[key] = value
        merged["interaction_hints"] = merged_hints

    return merged


def _is_placeholder_mobile_title(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in _MOBILE_PLACEHOLDER_TITLES


def _merge_mobile_conversation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        canonical_id = _normalize_mobile_conversation_id(row)
        if not canonical_id:
            continue
        current = merged.get(canonical_id)
        if current is None:
            current = dict(row)
            current["id"] = canonical_id
            current["session_id"] = canonical_id
            merged[canonical_id] = current
            order.append(canonical_id)
        else:
            current_updated = float(current.get("updated_at") or 0.0)
            row_updated = float(row.get("updated_at") or 0.0)
            prefer_row = row_updated > current_updated
            if row_updated > current_updated:
                for key in ("updated_at", "created_at", "status", "active_turn_id", "capability", "cost_summary"):
                    if key in row:
                        current[key] = row.get(key)
            current["message_count"] = max(
                int(current.get("message_count") or 0),
                int(row.get("message_count") or 0),
            )
            if _is_placeholder_mobile_title(current.get("title")) and not _is_placeholder_mobile_title(row.get("title")):
                current["title"] = row.get("title")
            if not str(current.get("last_message") or "").strip() and str(row.get("last_message") or "").strip():
                current["last_message"] = row.get("last_message")
            current_prefs = current.get("preferences") if isinstance(current.get("preferences"), dict) else {}
            row_prefs = row.get("preferences") if isinstance(row.get("preferences"), dict) else {}
            current["preferences"] = _merge_mobile_conversation_preferences(
                current_prefs,
                row_prefs,
                prefer_row=prefer_row,
            )

    result = [merged[item_id] for item_id in order]
    result.sort(key=lambda item: float(item.get("updated_at") or 0.0), reverse=True)
    return result


def _serialize_mobile_conversation(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    if _looks_like_internal_mobile_user_content(str(payload.get("title") or "")):
        payload["title"] = _extract_mobile_user_question_section(str(payload.get("title") or "")) or "新对话"
    for key in ("last_message", "preview"):
        if _looks_like_internal_mobile_user_content(str(payload.get(key) or "")):
            payload[key] = _extract_mobile_user_question_section(str(payload.get(key) or ""))
    created_at = payload.get("created_at")
    updated_at = payload.get("updated_at")
    payload["created_at"] = _ts_to_iso(created_at)
    payload["updated_at"] = _ts_to_iso(updated_at)
    payload["created_at_ms"] = _ts_to_ms(created_at)
    payload["updated_at_ms"] = _ts_to_ms(updated_at)
    return payload


async def _load_mobile_conversation_variants(
    conversation_id: str,
    user_id: str,
) -> list[dict[str, Any]]:
    normalized_conversation_id = str(conversation_id or "").strip()
    if not normalized_conversation_id:
        return []
    owner_key = build_user_owner_key(user_id)
    matches: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def add_match(row: dict[str, Any]) -> None:
        session_id = str(row.get("id") or row.get("session_id") or "").strip()
        if not session_id or session_id in seen_ids:
            return
        seen_ids.add(session_id)
        matches.append(row)

    direct_owner_lookup = getattr(session_store, "get_session_owner_key", None)
    if callable(direct_owner_lookup):
        direct_owner_key = str(await direct_owner_lookup(normalized_conversation_id) or "").strip()
        if direct_owner_key == owner_key:
            add_match({"id": normalized_conversation_id})

    exact_lookup = getattr(session_store, "list_sessions_by_owner_and_conversation", None)
    if callable(exact_lookup):
        for row in list(
            await exact_lookup(
                owner_key,
                normalized_conversation_id,
                source="wx_miniprogram",
                archived=None,
                limit=50,
            )
            or []
        ):
            if isinstance(row, dict):
                add_match(row)
        return matches

    list_by_owner = getattr(session_store, "list_sessions_by_owner", None)
    if not callable(list_by_owner):
        return matches

    offset = 0
    while True:
        rows = await list_by_owner(
            owner_key,
            source="wx_miniprogram",
            archived=None,
            limit=_MOBILE_CONVERSATION_LOOKUP_PAGE_SIZE,
            offset=offset,
        )
        batch = list(rows or [])
        if not batch:
            break
        for row in batch:
            if isinstance(row, dict) and _normalize_mobile_conversation_id(row) == normalized_conversation_id:
                add_match(row)
        if len(batch) < _MOBILE_CONVERSATION_LOOKUP_PAGE_SIZE:
            break
        offset += _MOBILE_CONVERSATION_LOOKUP_PAGE_SIZE
    return matches


_INTERNAL_MOBILE_USER_MARKERS = (
    "## 参考证据",
    "## Supporting Evidence",
    "以下内容是辅助证据",
    "[Question Follow-up Context]",
    "[Attached Documents]",
    "[Notebook Context]",
    "[History Context]",
)

_MOBILE_USER_QUESTION_SECTION_MARKERS = (
    "## 当前用户问题",
    "## Current User Question",
    "[User Question]",
)


def _looks_like_internal_mobile_user_content(content: str) -> bool:
    text = str(content or "").strip()
    if not text:
        return False
    if "[Question Follow-up Context]" in text:
        return True
    if "不得覆盖当前用户问题" in text:
        return True
    if any(text.startswith(marker) for marker in _INTERNAL_MOBILE_USER_MARKERS):
        return True
    return any(marker in text for marker in _MOBILE_USER_QUESTION_SECTION_MARKERS) and any(
        marker in text for marker in _INTERNAL_MOBILE_USER_MARKERS
    )


def _iter_mobile_message_metadata(message: dict[str, Any]) -> Iterable[dict[str, Any]]:
    metadata = message.get("metadata")
    if isinstance(metadata, dict):
        yield metadata
        request_snapshot = metadata.get("request_snapshot")
        if isinstance(request_snapshot, dict):
            yield request_snapshot
        nested_metadata = metadata.get("metadata")
        if isinstance(nested_metadata, dict):
            yield nested_metadata
    events = message.get("events") if isinstance(message.get("events"), list) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_metadata = event.get("metadata")
        if isinstance(event_metadata, dict):
            yield event_metadata
            nested_event_metadata = event_metadata.get("metadata")
            if isinstance(nested_event_metadata, dict):
                yield nested_event_metadata


def _trim_mobile_internal_user_section_tail(content: str) -> str:
    text = str(content or "").strip()
    if not text:
        return ""
    stop_markers = (
        "\n## 参考证据",
        "\n## Supporting Evidence",
        "\n[Question Follow-up Context]",
        "\n[Attached Documents]",
        "\n[Notebook Context]",
        "\n[History Context]",
    )
    cut_at = len(text)
    for marker in stop_markers:
        index = text.find(marker)
        if index >= 0:
            cut_at = min(cut_at, index)
    return text[:cut_at].strip()


def _extract_mobile_user_question_section(content: str) -> str:
    text = str(content or "")
    for marker in _MOBILE_USER_QUESTION_SECTION_MARKERS:
        index = text.find(marker)
        if index < 0:
            continue
        remainder = text[index + len(marker) :]
        if remainder.startswith("\n"):
            remainder = remainder[1:]
        candidate = _trim_mobile_internal_user_section_tail(remainder)
        if candidate and not _looks_like_internal_mobile_user_content(candidate):
            return candidate
    return ""


def _resolve_mobile_user_visible_content(message: dict[str, Any]) -> str:
    content = str(message.get("content") or "").strip()
    if not _looks_like_internal_mobile_user_content(content):
        return content

    candidate_keys = (
        "user_visible_content",
        "user_visible_query",
        "surface_content",
        "surface_query",
        "original_query",
        "original_content",
        "query",
        "content",
    )
    for metadata in _iter_mobile_message_metadata(message):
        for key in candidate_keys:
            candidate = str(metadata.get(key) or "").strip()
            if candidate and not _looks_like_internal_mobile_user_content(candidate):
                return candidate

    return _extract_mobile_user_question_section(content)


def _normalize_mobile_history_message_row(message: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    if str(message.get("role") or "") != "user":
        return message
    visible_content = _resolve_mobile_user_visible_content(message)
    if not visible_content:
        return None
    if visible_content == str(message.get("content") or ""):
        return message
    normalized = dict(message)
    normalized["content"] = visible_content
    normalized["_history_content_normalized"] = True
    return normalized


def _mobile_history_rows_have_mirror_provenance(
    candidate: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    candidate_session_id = str(
        candidate.get("_history_session_id") or candidate.get("session_id") or ""
    ).strip()
    current_session_id = str(
        current.get("_history_session_id") or current.get("session_id") or ""
    ).strip()
    if not candidate_session_id or not current_session_id:
        return False
    if candidate_session_id == current_session_id:
        return False
    return candidate_session_id.startswith("tutorbot:") or current_session_id.startswith("tutorbot:")


def _normalize_mobile_question_projection_text(content: str) -> str:
    text = re.sub(r"\s+", "", str(content or ""))
    if not text:
        return ""
    text = re.sub(r"^\*\*第[0-9一二两三四五六七八九十]+题\*\*", "", text)
    text = re.sub(r"^第[0-9一二两三四五六七八九十]+题", "", text)
    return text


def _mobile_option_lines(content: str) -> set[str]:
    options: set[str] = set()
    for line in str(content or "").splitlines():
        match = re.match(r"\s*([A-E])\s*[.、:：]\s*(.+?)\s*$", line, re.IGNORECASE)
        if not match:
            continue
        option_text = re.sub(r"\s+", "", match.group(2))
        if option_text:
            options.add(f"{match.group(1).upper()}:{option_text}")
    return options


def _strip_mobile_answer_sections(content: str) -> str:
    raw = str(content or "").strip()
    if not raw:
        return ""
    marker_re = re.compile(
        r"^\s*(?:\*\*)?(?:answer|explanation|标准答案|参考答案|正确答案|答案|解析)(?:\*\*)?\s*[:：]",
        re.IGNORECASE,
    )
    kept: list[str] = []
    for line in raw.splitlines():
        if marker_re.match(line):
            break
        kept.append(line)
    return "\n".join(kept).rstrip()


def _select_richer_mobile_assistant_projection(
    candidate: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any] | None:
    if str(candidate.get("role") or "") != "assistant" or str(current.get("role") or "") != "assistant":
        return None
    if not _mobile_history_rows_have_mirror_provenance(candidate, current):
        return None
    candidate_content = _strip_mobile_answer_sections(candidate.get("content") or "")
    current_content = _strip_mobile_answer_sections(current.get("content") or "")
    if len(candidate_content) <= len(current_content):
        return None
    if len(candidate_content) < len(current_content) + 40:
        return None

    candidate_normalized = _normalize_mobile_question_projection_text(candidate_content)
    current_normalized = _normalize_mobile_question_projection_text(current_content)
    if not current_normalized or current_normalized not in candidate_normalized:
        return None

    candidate_options = _mobile_option_lines(candidate_content)
    current_options = _mobile_option_lines(current_content)
    if current_options and not current_options.issubset(candidate_options):
        return None

    selected = dict(candidate)
    selected["content"] = candidate_content
    return selected


def _is_richer_mobile_assistant_projection(
    candidate: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    return _select_richer_mobile_assistant_projection(candidate, current) is not None


def _merge_mobile_message_rows(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        [
            normalized
            for item in messages
            if isinstance(item, dict)
            for normalized in [_normalize_mobile_history_message_row(item)]
            if normalized is not None
        ],
        key=lambda item: (
            float(item.get("created_at") or 0.0),
            int(item.get("id") or 0),
        ),
    )
    merged: list[dict[str, Any]] = []
    for item in ordered:
        presentation = _build_presentation_payload(item)
        signature = (
            str(item.get("role") or ""),
            str(item.get("content") or ""),
            json.dumps(presentation, ensure_ascii=False, sort_keys=True) if presentation else "",
        )
        created_at = float(item.get("created_at") or 0.0)
        if merged:
            previous = merged[-1]
            previous_presentation = _build_presentation_payload(previous)
            previous_signature = (
                str(previous.get("role") or ""),
                str(previous.get("content") or ""),
                json.dumps(previous_presentation, ensure_ascii=False, sort_keys=True)
                if previous_presentation
                else "",
            )
            previous_created_at = float(previous.get("created_at") or 0.0)
            normalized_user_pair = bool(
                item.get("_history_content_normalized")
                or previous.get("_history_content_normalized")
            )
            if signature == previous_signature and (
                normalized_user_pair or abs(created_at - previous_created_at) <= 2.0
            ):
                continue
            if abs(created_at - previous_created_at) <= 2.0:
                selected_previous = _select_richer_mobile_assistant_projection(previous, item)
                if selected_previous is not None:
                    merged[-1] = selected_previous
                    continue
                selected_item = _select_richer_mobile_assistant_projection(item, previous)
                if selected_item is not None:
                    merged[-1] = selected_item
                    continue
        merged.append(item)
    return merged


async def _persist_mobile_feedback(
    *,
    body: "ChatFeedbackRequest",
    authorization: str | None,
    session_id: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    normalized_session_id = str(session_id or body.conversation_id or "").strip()
    normalized_message_id = str(message_id or body.message_id or "").strip()
    if normalized_session_id:
        await _assert_mobile_conversation_access(normalized_session_id, user_id)
    feedback_context = await _load_feedback_response_mode_metadata(
        session_id=normalized_session_id,
        message_id=normalized_message_id,
        turn_id=str(body.turn_id or "").strip(),
    )

    writer = MobileFeedbackSupabaseClient()
    if not writer.is_configured:
        raise HTTPException(status_code=503, detail="Feedback storage unavailable")

    canonical_message_id = str(
        feedback_context.get("canonical_message_id") or normalized_message_id
    ).strip()
    resolved_turn_id = str(feedback_context.get("turn_id") or body.turn_id or "").strip()
    resolved_trace_id = str(feedback_context.get("trace_id") or body.trace_id or "").strip()
    request_id = get_request_id()
    row = build_mobile_feedback_row(
        user_id=user_id,
        session_id=normalized_session_id,
        message_id=canonical_message_id,
        surface_message_id=normalized_message_id,
        turn_id=resolved_turn_id,
        trace_id=resolved_trace_id,
        request_id=request_id,
        rating=body.rating,
        reason_tags=body.reason_tags,
        comment=body.comment,
        answer_mode=body.answer_mode,
        feedback_source=body.feedback_source,
        problem_type=body.problem_type,
        symptom_tags=body.symptom_tags,
        attachments=body.attachments,
        context_snapshot=body.context_snapshot,
        requested_response_mode=str(feedback_context.get("requested_response_mode") or ""),
        effective_response_mode=str(feedback_context.get("effective_response_mode") or ""),
        response_mode_degrade_reason=str(
            feedback_context.get("response_mode_degrade_reason") or ""
        ),
        actual_tool_rounds=(
            int(feedback_context.get("actual_tool_rounds"))
            if feedback_context.get("actual_tool_rounds") is not None
            else None
        ),
    )
    try:
        persisted = await writer.insert_feedback(row)
    except httpx.HTTPStatusError as exc:
        logger.warning("Mobile feedback write failed: status=%s body=%s", exc.response.status_code, exc.response.text)
        raise HTTPException(status_code=502, detail="Failed to persist feedback") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected mobile feedback write failure")
        raise HTTPException(status_code=500, detail="Failed to persist feedback") from exc
    finally:
        await writer.aclose()

    logger.warning(
        "Mobile feedback persisted: feedback_id=%s request_id=%s user_id=%s session_id=%s "
        "message_id=%s surface_message_id=%s turn_id=%s trace_id=%s rating=%s tags=%s",
        _log_safe_id((persisted or row).get("id")),
        _log_safe_id(request_id),
        _log_safe_id(user_id),
        _log_safe_id(normalized_session_id),
        _log_safe_id(canonical_message_id),
        _log_safe_id(normalized_message_id),
        _log_safe_id(resolved_turn_id),
        _log_safe_id(resolved_trace_id),
        row.get("rating"),
        ",".join(row.get("reason_tags") or []),
    )
    return {"ok": True}


def _normalize_tutorbot_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "auto":
        return "smart"
    return normalize_requested_response_mode(normalized)


def _resolve_mobile_requested_response_mode(
    body: "MobileStartTurnRequest",
    interaction_hints: dict[str, Any],
) -> str:
    if "mode" in getattr(body, "model_fields_set", set()):
        return _normalize_tutorbot_mode(body.mode)
    legacy_requested_mode = str(
        interaction_hints.get("requested_response_mode") or interaction_hints.get("teaching_mode") or ""
    ).strip()
    if legacy_requested_mode:
        return normalize_requested_response_mode(legacy_requested_mode)
    return _normalize_tutorbot_mode(body.mode)


def _assistant_message_by_id(
    messages: list[dict[str, Any]] | None,
    *,
    message_id: str,
) -> dict[str, Any] | None:
    normalized_message_id = str(message_id or "").strip()
    assistant_messages = [
        item
        for item in (messages or [])
        if isinstance(item, dict) and str(item.get("role") or "").strip() == "assistant"
    ]
    if normalized_message_id:
        for item in assistant_messages:
            if str(item.get("id") or "").strip() == normalized_message_id:
                return item
    return assistant_messages[-1] if assistant_messages else None


def _message_events(message: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(message, dict):
        return []
    events = message.get("events")
    return [item for item in (events or []) if isinstance(item, dict)] if isinstance(events, list) else []


def _event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _event_identity(event: dict[str, Any], key: str) -> str:
    direct = str(event.get(key) or "").strip()
    if direct:
        return direct
    metadata = _event_metadata(event)
    value = str(metadata.get(key) or "").strip()
    if value:
        return value
    nested = metadata.get("metadata")
    if isinstance(nested, dict):
        return str(nested.get(key) or "").strip()
    return ""


def _is_public_result_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("type") or "").strip().lower().split(".")[-1]
    if event_type != "result":
        return False
    visibility = str(event.get("visibility") or "public").strip().lower()
    return visibility == "public"


def _assistant_message_turn_id(message: dict[str, Any] | None) -> str:
    if isinstance(message, dict):
        for key in ("engine_turn_id", "turn_id"):
            direct = str(message.get(key) or "").strip()
            if direct:
                return direct
        for metadata in _iter_mobile_message_metadata(message):
            for key in ("engine_turn_id", "turn_id"):
                candidate = str(metadata.get(key) or "").strip()
                if candidate:
                    return candidate
    for event in reversed(_message_events(message)):
        turn_id = _event_identity(event, "turn_id")
        if turn_id:
            return turn_id
    return ""


def _mobile_message_identity(message: dict[str, Any] | None, keys: tuple[str, ...]) -> str:
    if isinstance(message, dict):
        for key in keys:
            direct = str(message.get(key) or "").strip()
            if direct:
                return direct
        for metadata in _iter_mobile_message_metadata(message):
            for key in keys:
                candidate = str(metadata.get(key) or "").strip()
                if candidate:
                    return candidate
    for event in reversed(_message_events(message)):
        for key in keys:
            candidate = _event_identity(event, key)
            if candidate:
                return candidate
    return ""


def _iter_mobile_message_answer_metadata(message: dict[str, Any]) -> Iterable[dict[str, Any]]:
    metadata = message.get("metadata")
    if isinstance(metadata, dict):
        yield metadata
        nested_metadata = metadata.get("metadata")
        if isinstance(nested_metadata, dict):
            yield nested_metadata
    for event in _message_events(message):
        if not _is_public_result_event(event):
            continue
        event_metadata = event.get("metadata")
        if isinstance(event_metadata, dict):
            yield event_metadata
            nested_event_metadata = event_metadata.get("metadata")
            if isinstance(nested_event_metadata, dict):
                yield nested_event_metadata


def _assistant_message_display_content(message: dict[str, Any]) -> str:
    content = str(message.get("content") or "")
    if content.strip() or str(message.get("role") or "") != "assistant":
        return content
    for key in ("response", "assistant_content"):
        direct = str(message.get(key) or "").strip()
        if direct:
            return str(message.get(key) or "")
    for metadata in _iter_mobile_message_answer_metadata(message):
        for key in ("response", "assistant_content"):
            candidate = str(metadata.get(key) or "").strip()
            if candidate:
                return str(metadata.get(key) or "")
    return content


def _assistant_message_trace_id(message: dict[str, Any] | None) -> str:
    for event in reversed(_message_events(message)):
        for key in ("trace_id", "langfuse_trace_id"):
            trace_id = _event_identity(event, key)
            if trace_id:
                return trace_id
    return ""


def _assistant_message_matches_turn(message: dict[str, Any], turn_id: str) -> bool:
    normalized_turn_id = str(turn_id or "").strip()
    if not normalized_turn_id:
        return False
    return _assistant_message_turn_id(message) == normalized_turn_id


def _assistant_message_by_turn_id(
    messages: list[dict[str, Any]] | None,
    *,
    turn_id: str,
) -> dict[str, Any] | None:
    assistant_messages = [
        item
        for item in (messages or [])
        if isinstance(item, dict) and str(item.get("role") or "").strip() == "assistant"
    ]
    for item in reversed(assistant_messages):
        if _assistant_message_matches_turn(item, turn_id):
            return item
    return None


async def _load_feedback_response_mode_metadata(
    *,
    session_id: str,
    message_id: str,
    turn_id: str = "",
) -> dict[str, Any]:
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        return {}
    loader = getattr(session_store, "get_session_with_messages", None)
    if not callable(loader):
        return {}
    session = await loader(normalized_session_id)
    if not isinstance(session, dict):
        return {}
    preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
    interaction_hints = (
        preferences.get("interaction_hints")
        if isinstance(preferences.get("interaction_hints"), dict)
        else {}
    )
    requested_response_mode = normalize_requested_response_mode(
        str(
            interaction_hints.get("requested_response_mode")
            or interaction_hints.get("teaching_mode")
            or preferences.get("chat_mode")
            or ""
        ).strip()
    )
    effective_response_mode = normalize_requested_response_mode(
        str(
            interaction_hints.get("effective_response_mode")
            or preferences.get("chat_mode")
            or requested_response_mode
            or ""
        ).strip()
    )
    messages = session.get("messages") if isinstance(session.get("messages"), list) else []
    assistant_message = (
        _assistant_message_by_turn_id(messages, turn_id=turn_id)
        or _assistant_message_by_id(messages, message_id=message_id)
    )
    events = assistant_message.get("events") if isinstance(assistant_message, dict) else []
    actual_tool_rounds = sum(
        1
        for item in (events or [])
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "tool_call"
    )
    return {
        "canonical_message_id": str(
            assistant_message.get("id") if isinstance(assistant_message, dict) else ""
        ).strip(),
        "turn_id": str(turn_id or _assistant_message_turn_id(assistant_message)).strip(),
        "trace_id": _assistant_message_trace_id(assistant_message),
        "requested_response_mode": requested_response_mode,
        "effective_response_mode": effective_response_mode,
        "response_mode_degrade_reason": str(
            interaction_hints.get("response_mode_degrade_reason") or ""
        ).strip(),
        "actual_tool_rounds": actual_tool_rounds,
    }


def _extract_goal_patches(patch: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(patch, dict):
        return []
    raw_goals = patch.get("goals")
    if isinstance(raw_goals, list):
        return [dict(item) for item in raw_goals if isinstance(item, dict)]
    raw_goal = patch.get("goal")
    if isinstance(raw_goal, dict):
        return [dict(raw_goal)]
    goal_fields = {
        "id",
        "goal_type",
        "title",
        "target_node_codes",
        "target_question_count",
        "progress",
        "deadline",
        "completed_at",
    }
    if goal_fields.intersection(patch.keys()):
        return [{key: value for key, value in patch.items() if key in goal_fields}]
    return []


def _build_learner_profile_payload(profile: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(profile or {})
    for key in (
        "points",
        "balance",
        "display_balance",
        "balance_micros",
        "frozen",
        "frozen_micros",
        "wallet",
    ):
        merged.pop(key, None)
    passthrough_fields = {
        "timezone",
        "source",
        "plan",
        "exam_target",
        "knowledge_level",
        "communication_style",
    }
    passthrough_objects = {
        "learning_preferences",
        "support_preferences",
        "heartbeat_preferences",
        "consent",
    }
    for key in passthrough_fields:
        if key in patch:
            merged[key] = patch[key]
    for key in passthrough_objects:
        if isinstance(patch.get(key), dict):
            merged[key] = dict(patch[key])
    return merged


def _build_member_profile_rollback_patch(profile: dict[str, Any]) -> dict[str, Any]:
    rollback_fields = (
        "display_name",
        "exam_date",
        "daily_target",
        "time_budget",
        "difficulty_preference",
        "explanation_style",
        "review_reminder",
        "avatar_url",
    )
    return {
        key: profile[key]
        for key in rollback_fields
        if isinstance(profile, dict) and key in profile
    }


def _merge_interaction_hints(
    profile: str,
    hints: dict[str, Any] | None,
    *,
    current_info_required: bool,
) -> dict[str, Any]:
    merged = dict(hints or {})
    normalized_profile = str(profile or "").strip().lower()
    if normalized_profile == "":
        normalized_profile = "tutorbot"
    merged["profile"] = normalized_profile
    merged.setdefault("product_surface", "wechat_miniprogram")
    merged.setdefault("entry_role", "tutorbot")
    merged.setdefault("subject_domain", "construction_exam")
    merged.setdefault("suppress_answer_reveal_on_generate", True)
    if current_info_required:
        merged["current_info_required"] = True
    return merged


def _build_mobile_turn_payload(
    *,
    body: MobileStartTurnRequest,
    authenticated_user_id: str,
    wallet_user_id: str,
    query: str,
    eval_bypass_verified: bool = False,
) -> dict[str, Any]:
    requested_tools = [
        str(item).strip()
        for item in (body.tools or [])
        if str(item).strip() and str(item).strip() != "web_search"
    ]
    grounding_decision = build_grounding_decision(
        query=query,
        knowledge_bases=body.knowledge_bases,
        rag_enabled=True,
        tutorbot_context=True,
    )
    current_info_required = (
        grounding_decision.current_info_required
        or grounding_decision.textbook_delta_query
    )
    if current_info_required and is_web_search_runtime_available():
        requested_tools.append("web_search")
    interaction_profile = str(body.interaction_profile or "tutorbot").strip() or "tutorbot"
    interaction_hints = _merge_interaction_hints(
        interaction_profile,
        body.interaction_hints,
        current_info_required=current_info_required,
    )
    requested_response_mode = _resolve_mobile_requested_response_mode(body, interaction_hints)
    interaction_hints["requested_response_mode"] = requested_response_mode
    interaction_hints.pop("teaching_mode", None)
    if grounding_decision.reasons:
        interaction_hints["grounding_reasons"] = list(grounding_decision.reasons)
    capability = str(body.capability or "").strip() or None
    if capability == "tutorbot":
        capability = None
    config: dict[str, Any] = {
        "interaction_hints": interaction_hints,
        "billing_context": {
            "source": "wx_miniprogram",
            "user_id": authenticated_user_id,
            "wallet_user_id": wallet_user_id or authenticated_user_id,
            "learning_user_id": authenticated_user_id,
            # Server-authored only; the client cannot inject billing_context, so
            # this verified marker safely carries the eval-bypass decision to the
            # post-turn capture path.
            **({"eval_bypass": "verified"} if eval_bypass_verified else {}),
        },
        "interaction_profile": interaction_profile,
    }
    if capability in (None, "chat"):
        config["chat_mode"] = requested_response_mode
        config["bot_id"] = _MOBILE_TUTORBOT_ID
    if body.followup_question_context:
        config["followup_question_context"] = dict(body.followup_question_context)
    if body.grading_engine_runtime_shadow:
        config["grading_engine_runtime_shadow"] = True
        config["grading_engine_runtime_shadow_engine"] = (
            str(body.grading_engine_runtime_shadow_engine or "deepseek_fast").strip()
            or "deepseek_fast"
        )
    request_config = body.config if isinstance(body.config, dict) else {}
    config_general_knowledge_context = request_config.get("general_knowledge_context")
    if body.general_knowledge_context is not None:
        config["general_knowledge_context"] = bool(body.general_knowledge_context)
    elif isinstance(config_general_knowledge_context, bool):
        config["general_knowledge_context"] = config_general_knowledge_context
    if body.prompt_intent:
        intent_key = "learning_training_intent" if capability == "deep_question" else "learning_prompt_intent"
        config[intent_key] = dict(body.prompt_intent)
    if body.persist_user_message is False:
        config["_persist_user_message"] = False
    client_turn_id = str(body.client_turn_id or "").strip()
    if client_turn_id:
        config["client_turn_id"] = client_turn_id

    return {
        "session_id": str(body.conversation_id or "").strip() or None,
        "content": query,
        "capability": capability,
        "language": str(body.language or "zh").strip() or "zh",
        "tools": requested_tools,
        "knowledge_bases": list(body.knowledge_bases or []),
        "attachments": list(body.attachments or []),
        "config": config,
    }


def _build_presentation_payload(message: dict[str, Any]) -> dict[str, Any] | None:
    events = message.get("events") if isinstance(message.get("events"), list) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        if metadata.get("authority_applied") is True:
            return None
    for event in events:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        presentation = metadata.get("presentation")
        if isinstance(presentation, dict):
            blocks = presentation.get("blocks") if isinstance(presentation.get("blocks"), list) else []
            review_mode = any(
                isinstance(block, dict) and bool(block.get("review_mode") or block.get("reviewMode"))
                for block in blocks
            )
            return build_canonical_presentation(
                content=str(message.get("content") or presentation.get("fallback_text") or ""),
                blocks=blocks,
                reveal_answers=bool(metadata.get("reveal_answers") or review_mode),
                reveal_explanations=bool(metadata.get("reveal_explanations") or review_mode),
            )
    return None


def _serialize_mobile_message(message: dict[str, Any]) -> dict[str, Any]:
    presentation = _build_presentation_payload(message)
    turn_id = _mobile_message_identity(
        message,
        ("turn_id", "engine_turn_id", "turnId", "engineTurnId"),
    )
    client_turn_id = _mobile_message_identity(
        message,
        ("client_turn_id", "clientTurnId"),
    )
    serialized = {
        "id": str(message.get("id") or ""),
        "role": str(message.get("role") or ""),
        "content": _assistant_message_display_content(message),
        "created_at": _ts_to_iso(message.get("created_at")),
        "engine_turn_id": _assistant_message_turn_id(message),
        "presentation": presentation,
    }
    if turn_id:
        serialized["turn_id"] = turn_id
    if client_turn_id:
        serialized["client_turn_id"] = client_turn_id
    return serialized


def _build_tutorbot_start_response(
    *,
    conversation_id: str,
    query: str,
    turn_id: str,
    capability: str,
) -> dict[str, Any]:
    response = UnifiedTurnStartResponse(
        conversation={
            "id": conversation_id,
            "title": _infer_mobile_conversation_title(query),
            "created_at": datetime.now().isoformat(),
        },
        turn={
            "id": turn_id,
            "capability": capability,
            "status": "running",
        },
        bot={
            "id": _MOBILE_TUTORBOT_ID,
            "name": _MOBILE_TUTORBOT_NAME,
        },
        stream=build_turn_stream_bootstrap(session_id=conversation_id, turn_id=turn_id),
    )
    return response.model_dump(exclude_none=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class PhoneRequest(BaseModel):
    phone: str
    username: str = ""


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str


class PasswordResetRequest(BaseModel):
    phone: str
    code: str
    password: str
    username: str = ""


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    phone: str


class WechatLoginRequest(BaseModel):
    code: str = ""
    phone_code: str = ""


class WechatBindPhoneRequest(BaseModel):
    phone_code: str = ""


class MobileStartTurnRequest(BaseModel):
    query: str = Field(max_length=_MAX_MOBILE_START_TURN_QUERY_CHARS)
    conversation_id: str = ""
    client_turn_id: str = ""
    capability: str = ""
    mode: str = "AUTO"
    language: str = "zh"
    interaction_profile: str = "tutorbot"
    interaction_hints: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    tools: list[str] = Field(default_factory=list)
    knowledge_bases: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    followup_question_context: dict[str, Any] | None = None
    prompt_intent: dict[str, Any] | None = None
    persist_user_message: bool = True
    grading_engine_runtime_shadow: bool = False
    grading_engine_runtime_shadow_engine: str = "deepseek_fast"
    general_knowledge_context: bool | None = None


class ChatFeedbackRequest(BaseModel):
    message_id: str = ""
    conversation_id: str = ""
    turn_id: str = ""
    trace_id: str = ""
    rating: int = 0
    reason_tags: list[str] = Field(default_factory=list)
    comment: str = ""
    answer_mode: str = "AUTO"
    feedback_source: str = "wx_miniprogram_message_actions"
    problem_type: str = ""
    symptom_tags: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    context_snapshot: dict[str, Any] = Field(default_factory=dict)


class AssessmentCreateRequest(BaseModel):
    assessment_type: str = "diagnostic"
    subject_id: str = "construction_exam"
    topic_ids: list[str] = Field(default_factory=list)
    count: int = Field(default=20, ge=1, le=50)
    duration_policy: dict[str, Any] = Field(default_factory=dict)
    device_id: str = Field(default="", max_length=128)


class AssessmentSubmitRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    time_spent_seconds: int = Field(default=0, ge=0, le=86400)
    device_id: str = Field(default="", max_length=128)

    @field_validator("answers")
    @classmethod
    def _validate_answers(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, raw_answer in dict(value or {}).items():
            question_id = str(key or "").strip()
            answer = str(raw_answer or "").strip()
            if not question_id:
                raise ValueError("answer_question_id_required")
            if len(question_id) > 128:
                raise ValueError("answer_question_id_too_long")
            if len(answer) > 64:
                raise ValueError("answer_value_too_long")
            normalized[question_id] = answer
        if len(normalized) > 50:
            raise ValueError("answer_count_exceeds_assessment_limit")
        return normalized


class BatchConversationRequest(BaseModel):
    action: str
    conversation_ids: list[str] = Field(default_factory=list)


@router.post(
    "/auth/login",
    dependencies=[Depends(route_rate_limit("mobile_auth_login", default_max_requests=10, default_window_seconds=60.0))],
)
async def auth_login(body: LoginRequest) -> dict[str, Any]:
    try:
        # bcrypt verify + a deliberate >=100ms constant-time floor (timing-attack
        # guard) — must run in the threadpool, not on the event loop.
        return await run_in_threadpool(
            member_service.login_with_password, body.username, body.password
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post(
    "/auth/register",
    dependencies=[
        Depends(route_rate_limit("mobile_auth_register", default_max_requests=3, default_window_seconds=60.0))
    ],
)
async def auth_register(body: RegisterRequest) -> dict[str, Any]:
    try:
        # bcrypt hash — threadpool, same rationale as auth_login.
        result = await run_in_threadpool(
            member_service.register_with_external_auth, body.username, body.password, body.phone
        )
        user = result.get("user") if isinstance(result.get("user"), dict) else {}
        user_id = str(
            result.get("user_id")
            or result.get("id")
            or user.get("user_id")
            or user.get("id")
            or ""
        ).strip()
        if user_id:
            try:
                learner_state_service.read_snapshot(user_id)
            except Exception:
                pass
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/auth/send-code",
    dependencies=[
        Depends(route_rate_limit("mobile_auth_send_code", default_max_requests=3, default_window_seconds=60.0))
    ],
)
async def auth_send_code(body: PhoneRequest) -> dict[str, Any]:
    try:
        if body.username.strip():
            return member_service.send_password_reset_code(body.username, body.phone)
        return member_service.send_phone_code(body.phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/auth/verify-code",
    dependencies=[
        Depends(route_rate_limit("mobile_auth_verify_code", default_max_requests=6, default_window_seconds=60.0))
    ],
)
async def auth_verify_code(body: VerifyCodeRequest) -> dict[str, Any]:
    try:
        return member_service.verify_phone_code(body.phone, body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/auth/reset-password",
    dependencies=[
        Depends(route_rate_limit("mobile_auth_reset_password", default_max_requests=5, default_window_seconds=60.0))
    ],
)
async def auth_reset_password(body: PasswordResetRequest) -> dict[str, Any]:
    try:
        # bcrypt re-hash — threadpool, same rationale as auth_login.
        return await run_in_threadpool(
            member_service.reset_password_with_phone_code,
            body.username,
            body.phone,
            body.code,
            body.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/auth/change-password",
    dependencies=[
        Depends(route_rate_limit("mobile_auth_change_password", default_max_requests=5, default_window_seconds=60.0))
    ],
)
async def auth_change_password(
    body: ChangePasswordRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    try:
        # bcrypt verify + re-hash — threadpool, same rationale as auth_login.
        return await run_in_threadpool(
            member_service.change_password,
            user_id,
            body.old_password,
            body.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@router.get("/auth/profile")
async def auth_profile(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    current_user = resolve_auth_context(authorization)
    profile = member_service.get_profile(user_id)
    wallet_user_id = _resolve_wallet_lookup_user_id(authorization)
    legacy_points = int(profile.get("points") or profile.get("points_balance") or 0)
    snapshot = _wallet_snapshot_or_zero(
        wallet_user_id,
        identity_candidates=(
            user_id,
            profile.get("user_id"),
            profile.get("username"),
            profile.get("auth_username"),
            profile.get("external_auth_user_id"),
        ),
        fallback_points=legacy_points,
    )
    wallet_payload = _serialize_wallet_snapshot(snapshot)
    wallet_payload["user_id"] = user_id
    profile["id"] = user_id
    profile["user_id"] = user_id
    profile["points"] = wallet_payload["points"]
    profile["balance"] = wallet_payload["balance"]
    profile["balance_micros"] = wallet_payload["balance_micros"]
    profile["frozen_micros"] = wallet_payload["frozen_micros"]
    profile["is_admin"] = bool(current_user.is_admin) if current_user is not None else False
    profile["wallet"] = wallet_payload
    if wallet_user_id:
        _shadow_compare_wallet_read(user_id, balance_points=wallet_payload["points"], source="auth_profile")
    return profile


@router.post(
    "/auth/refresh",
    dependencies=[Depends(route_rate_limit("mobile_auth_refresh", default_max_requests=30, default_window_seconds=60.0))],
)
async def auth_refresh(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    try:
        return member_service.refresh_access_token(authorization)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/auth/profile/settings")
async def auth_profile_settings(
    patch: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    previous_profile = member_service.get_profile(user_id)
    previous_learner_profile = learner_state_service.read_profile(user_id)
    goal_patches = _extract_goal_patches(patch)
    previous_goals = learner_state_service.read_goals(user_id) if goal_patches else []
    try:
        profile = member_service.update_profile(user_id, patch)
    except ValueError as exc:
        # fail-closed 校验拒绝（如非法 exam_date）：什么都没写，直接 400。
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    learner_profile = _build_learner_profile_payload(profile, patch)
    try:
        learner_state_service.write_profile_strict(user_id, learner_profile)
        if goal_patches:
            learner_state_service.sync_goals_strict(user_id, goal_patches)
    except Exception as exc:
        rollback_errors: list[str] = []
        try:
            member_service.update_profile(user_id, _build_member_profile_rollback_patch(previous_profile))
        except Exception as rollback_exc:
            rollback_errors.append(f"member profile rollback failed: {rollback_exc}")
        try:
            learner_state_service.write_profile_strict(user_id, previous_learner_profile)
        except Exception as rollback_exc:
            rollback_errors.append(f"learner profile rollback failed: {rollback_exc}")
        if goal_patches:
            try:
                learner_state_service.sync_goals_strict(user_id, previous_goals)
            except Exception as rollback_exc:
                rollback_errors.append(f"learner goals rollback failed: {rollback_exc}")
        detail = f"Failed to sync learner state: {exc}"
        if rollback_errors:
            detail = f"{detail}; rollback failed: {'; '.join(rollback_errors)}"
        raise HTTPException(status_code=503, detail=detail) from exc
    return profile


@router.post(
    "/wechat/mp/login",
    dependencies=[
        Depends(route_rate_limit("mobile_wechat_login", default_max_requests=10, default_window_seconds=60.0))
    ],
)
async def wechat_login(body: WechatLoginRequest) -> dict[str, Any]:
    try:
        if not str(body.phone_code or "").strip():
            raise ValueError("phone_code is required")
        return await member_service.login_with_wechat_phone(body.code, body.phone_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/wechat/mp/bind-phone",
    dependencies=[
        Depends(route_rate_limit("mobile_wechat_bind_phone", default_max_requests=6, default_window_seconds=60.0))
    ],
)
async def wechat_bind_phone(
    body: WechatBindPhoneRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return await member_service.bind_phone_for_wechat(
            _resolve_authenticated_user_id(authorization),
            body.phone_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/practice/today-progress")
async def practice_today_progress(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_today_progress(_resolve_authenticated_user_id(authorization))


@router.get("/practice/chapter-progress")
async def practice_chapter_progress(authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    return member_service.get_chapter_progress(_resolve_authenticated_user_id(authorization))


@router.get("/practice/daily-question")
async def practice_daily_question(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_daily_question(_resolve_authenticated_user_id(authorization))


@router.get("/billing/points")
async def billing_points(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    wallet_user_id = _resolve_wallet_lookup_user_id(authorization)
    snapshot = _wallet_snapshot_or_zero(wallet_user_id)
    wallet_payload = _serialize_wallet_snapshot(snapshot)
    if wallet_user_id:
        _shadow_compare_wallet_read(user_id, balance_points=wallet_payload["points"], source="billing_points")
    return {
        "user_id": user_id,
        "points": wallet_payload["points"],
        "balance": wallet_payload["balance"],
        "display_balance": wallet_payload["display_balance"],
        "balance_micros": wallet_payload["balance_micros"],
        "frozen_micros": wallet_payload["frozen_micros"],
    }


@router.get("/billing/wallet")
async def billing_wallet(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    wallet_user_id = _resolve_wallet_lookup_user_id(authorization)
    snapshot = _wallet_snapshot_or_zero(wallet_user_id)
    wallet_payload = _serialize_wallet_snapshot(snapshot)
    wallet_payload["user_id"] = user_id
    if wallet_user_id:
        _shadow_compare_wallet_read(user_id, balance_points=wallet_payload["points"], source="billing_wallet")
    return wallet_payload


@router.get("/billing/usage")
async def billing_usage(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _resolve_authenticated_user_id(authorization)
    wallet_user_id = _resolve_wallet_lookup_user_id(authorization)
    if not getattr(wallet_service, "is_configured", False):
        raise HTTPException(status_code=503, detail="Wallet service unavailable")
    try:
        snapshot = _wallet_snapshot_or_zero(wallet_user_id)
    except Exception as exc:
        _billing_storage_unavailable(exc, source="billing_usage_wallet")
        return _degraded_billing_usage_payload()
    if not is_billing_enforcement_enabled():
        try:
            events = _load_member_usage_meter_events(
                wallet_user_id=wallet_user_id,
                limit=_BILLING_USAGE_LEDGER_WINDOW,
            )
        except Exception as exc:
            _billing_storage_unavailable(exc, source="billing_usage_member_meter")
            events = []
        payload = _build_internal_beta_usage_payload(
            events,
            plan_id=snapshot.plan_id,
        )
        payload["usage_source"] = "member_usage_meter"
        payload["charging_status"] = "metered_not_charged"
        return payload
    try:
        entries = _load_billing_usage_entries(
            authorization,
            wallet_user_id=wallet_user_id,
            limit=_BILLING_USAGE_LEDGER_WINDOW,
        )
    except Exception as exc:
        _billing_storage_unavailable(exc, source="billing_usage_ledger")
        entries = []
    return _build_billing_usage_payload(
        entries,
        plan_id=snapshot.plan_id,
    )


@router.get("/billing/ledger")
async def billing_ledger(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    _resolve_authenticated_user_id(authorization)
    wallet_user_id = _resolve_wallet_lookup_user_id(authorization)
    if not getattr(wallet_service, "is_configured", False):
        raise HTTPException(status_code=503, detail="Wallet service unavailable")
    merge_window = offset + limit + 1
    try:
        wallet_rows = wallet_service.list_wallet_ledger(wallet_user_id, limit=merge_window, offset=0)
        legacy_rows = (
            _load_legacy_wallet_ledger_entries(
                authorization,
                wallet_user_id=wallet_user_id,
                limit=merge_window,
            )
            if _env_flag_enabled(_BILLING_INCLUDE_LEGACY_LEDGER)
            else []
        )
    except Exception as exc:
        _billing_storage_unavailable(exc, source="billing_ledger")
        return {
            "entries": [],
            "has_more": False,
            "total": 0,
            "degraded": True,
            "reason": "billing_storage_unavailable",
        }
    merged_rows = _merge_wallet_ledger_entries(wallet_rows, legacy_rows)
    page = merged_rows[offset : offset + limit]
    has_more = offset + limit < len(merged_rows)
    return {
        "entries": [_serialize_wallet_ledger_entry(item) for item in page],
        "has_more": has_more,
        "total": len(merged_rows),
    }


@router.post("/billing/checkout")
async def billing_checkout(
    payload: BillingCheckoutRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    wallet_user_id = _resolve_wallet_lookup_user_id(authorization) or user_id
    channel = str(payload.channel or "").strip().lower()
    if channel not in _BILLING_PAYMENT_CHANNELS:
        raise HTTPException(status_code=400, detail="Unsupported payment channel")
    package = _billing_package_by_id(payload.package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Billing package not found")
    checkout_payload = _build_local_checkout_payload(
        user_id=user_id,
        wallet_user_id=wallet_user_id,
        package=package,
        channel=channel,
    )
    gateway_payload = await _create_payment_gateway_order(checkout_payload)
    if gateway_payload is not None:
        return gateway_payload
    return checkout_payload


@router.get("/homepage/dashboard")
async def homepage_dashboard(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_home_dashboard(_resolve_authenticated_user_id(authorization))


@router.get("/profile/badges")
async def profile_badges(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_badges(_resolve_authenticated_user_id(authorization))


@router.get("/bi/radar/{user_id}")
async def bi_radar(
    user_id: str,
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    resolved = current_user.user_id if not current_user.is_admin else user_id
    return member_service.get_radar_data(resolved)


@router.get("/plan/mastery-dashboard")
async def mastery_dashboard(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_mastery_dashboard(_resolve_authenticated_user_id(authorization))


@router.get(
    "/learning-brain/projection",
    # Heavy synthesis pass over the learner's memory events — not free to recompute.
    dependencies=[
        Depends(
            route_rate_limit(
                "mobile_learning_brain_projection",
                default_max_requests=20,
                default_window_seconds=60.0,
            )
        )
    ],
)
async def learning_brain_projection(
    authorization: str | None = Header(default=None),
    event_limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    projection = learner_state_service.read_compiled_learning_truth(user_id)
    projection = dict(projection) if isinstance(projection, dict) else {}
    if not projection and _learning_brain_local_projection_fallback_enabled():
        synthesis = learner_state_service.synthesize_learning_truth(
            user_id,
            dry_run=True,
            event_limit=event_limit,
        )
        projection = dict(synthesis.get("projection") or {})
    return build_learning_brain_read_model(user_id=user_id, projection=projection, surface="mobile")


@router.get("/mobile/learning-report")
async def mobile_learning_report(
    authorization: str | None = Header(default=None),
    accept: str | None = Header(default=None),
    event_limit: int = Query(default=100, ge=1, le=500),
    schema_version: int = Query(default=1, ge=1, le=2),
) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    requested_schema_version = _learning_report_schema_version(
        schema_version=schema_version,
        accept=accept,
    )
    return await run_in_threadpool(
        _build_mobile_learning_report_read_model,
        user_id=user_id,
        event_limit=event_limit,
        schema_version=requested_schema_version,
    )


def _build_mobile_learning_report_read_model(
    *,
    user_id: str,
    event_limit: int,
    schema_version: int,
) -> dict[str, Any]:
    return build_learning_report_read_model(
        user_id=user_id,
        member_service=member_service,
        learner_state_service=learner_state_service,
        mistake_book_service=mistake_book_service,
        notebook_card_service=get_notebook_card_service(),
        event_limit=event_limit,
        schema_version=schema_version,
    )


def _learning_report_schema_version(*, schema_version: int, accept: str | None) -> int:
    for media_range in str(accept or "").lower().split(","):
        parts = [part.strip() for part in media_range.split(";") if part.strip()]
        if not parts or parts[0] != "application/vnd.deeptutor.learning-report+json":
            continue
        params = {
            key.strip(): value.strip()
            for item in parts[1:]
            if "=" in item
            for key, value in [item.split("=", 1)]
        }
        if params.get("v") == "2":
            return 2
    return 2 if int(schema_version or 1) == 2 else 1


@router.get("/mobile/learning-attempts/{attempt_ref}")
async def mobile_learning_attempt_detail(
    attempt_ref: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    detail = await run_in_threadpool(
        build_attempt_detail_read_model,
        user_id=user_id,
        learner_state_service=learner_state_service,
        attempt_ref=attempt_ref,
        session_store=session_store,
    )
    if not detail.get("ok"):
        raise HTTPException(status_code=404, detail=detail.get("error") or "attempt_not_found")
    return detail


@router.get("/mobile/mistake-book")
async def mobile_mistake_book(
    authorization: str | None = Header(default=None),
    subject_id: str = Query(default=""),
    include_mastered: bool = Query(default=False),
) -> dict[str, Any]:
    _require_mistake_book_read_enabled()
    user_id = _resolve_authenticated_user_id(authorization)
    try:
        return await run_in_threadpool(
            mistake_book_service.list_items,
            user_id=user_id,
            subject_id=subject_id,
            include_mastered=include_mastered,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/mobile/mistake-book/items")
async def mobile_save_mistake_book_item(
    payload: MistakeBookSaveRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_mistake_book_write_enabled()
    user_id = _resolve_authenticated_user_id(authorization)
    try:
        return await run_in_threadpool(
            mistake_book_service.save_item,
            user_id=user_id,
            attempt_ref=payload.attempt_ref,
            subject_id=payload.subject_id,
            bot_id=payload.bot_id,
            title=payload.title,
            concept_label=payload.concept_label,
            error_label=payload.error_label,
            note=payload.note,
            tags=payload.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/mobile/mistake-book/items/{attempt_ref}")
async def mobile_remove_mistake_book_item(
    attempt_ref: str,
    authorization: str | None = Header(default=None),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    _require_mistake_book_write_enabled()
    user_id = _resolve_authenticated_user_id(authorization)
    try:
        return await run_in_threadpool(
            mistake_book_service.remove_item,
            user_id=user_id,
            attempt_ref=attempt_ref,
            if_match=if_match,
        )
    except MistakeBookConflict as exc:
        raise HTTPException(status_code=409, detail={"error": "etag_conflict", "latest": exc.latest}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/mobile/mistake-book/items/{attempt_ref}/mastered")
async def mobile_mark_mistake_book_item_mastered(
    attempt_ref: str,
    authorization: str | None = Header(default=None),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    _require_mistake_book_write_enabled()
    user_id = _resolve_authenticated_user_id(authorization)
    try:
        return await run_in_threadpool(
            mistake_book_service.mark_mastered,
            user_id=user_id,
            attempt_ref=attempt_ref,
            if_match=if_match,
        )
    except MistakeBookConflict as exc:
        raise HTTPException(status_code=409, detail={"error": "etag_conflict", "latest": exc.latest}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/mobile/mistake-book/items/{attempt_ref}/review")
async def mobile_record_mistake_book_item_review(
    attempt_ref: str,
    authorization: str | None = Header(default=None),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    _require_mistake_book_write_enabled()
    user_id = _resolve_authenticated_user_id(authorization)
    try:
        return await run_in_threadpool(
            mistake_book_service.record_review,
            user_id=user_id,
            attempt_ref=attempt_ref,
            if_match=if_match,
        )
    except MistakeBookConflict as exc:
        raise HTTPException(status_code=409, detail={"error": "etag_conflict", "latest": exc.latest}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/assessment/profile")
async def assessment_profile(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_assessment_profile(_resolve_authenticated_user_id(authorization))


@router.get("/assessment/topics")
async def assessment_topics(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    return await run_in_threadpool(member_service.get_assessment_topic_catalog, user_id)


def _assessment_session_http_error(exc: AssessmentSessionError) -> HTTPException:
    detail = str(exc)
    if isinstance(exc, AssessmentSessionNotFound):
        return HTTPException(status_code=404, detail="assessment_session_not_found")
    if isinstance(exc, AssessmentSessionExpired):
        return HTTPException(status_code=409, detail={"error": "assessment_session_expired"})
    if isinstance(exc, AssessmentLeaseConflict):
        return HTTPException(status_code=409, detail={"error": "assessment_lease_conflict"})
    if isinstance(exc, AssessmentSessionConflict):
        return HTTPException(status_code=409, detail={"error": detail or "assessment_session_conflict"})
    if isinstance(exc, AssessmentSessionRateLimited):
        return HTTPException(status_code=429, detail={"error": detail or "assessment_session_rate_limited"})
    return HTTPException(
        status_code=503,
        detail={
            "error": "assessment_sessions_unavailable",
            "message": "题库服务暂时不可用，请稍后重试。",
        },
    )


@router.post(
    "/assessment/create",
    # LLM-backed quiz assembly — burst + daily budget (economic-DoS guard), same
    # pattern as _MOBILE_CHAT_START_TURN_DEPENDENCIES.
    dependencies=[
        Depends(
            route_rate_limit(
                "mobile_assessment_create",
                default_max_requests=6,
                default_window_seconds=60.0,
            )
        ),
        Depends(
            route_rate_limit(
                "mobile_assessment_create_daily",
                default_max_requests=60,
                default_window_seconds=86400.0,
            )
        ),
    ],
)
async def assessment_create(
    body: AssessmentCreateRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            member_service.create_assessment,
            _resolve_authenticated_user_id(authorization),
            assessment_type=body.assessment_type,
            subject_id=body.subject_id,
            topic_ids=body.topic_ids,
            count=body.count,
            duration_policy=body.duration_policy,
            device_id=body.device_id,
        )
    except AssessmentBlueprintUnavailable as exc:
        logger.warning("Assessment blueprint unavailable for mobile create: %s", exc)
        raise HTTPException(
            status_code=409,
            detail={
                "error": "assessment_blueprint_unavailable",
                "message": "当前题库暂不足以生成本次专题测评，请稍后再试。",
            },
        ) from exc
    except AssessmentSessionError as exc:
        logger.warning("Assessment session unavailable for mobile create: %s", exc)
        raise _assessment_session_http_error(exc) from exc


@router.get("/assessment/{quiz_id}")
async def assessment_resume(
    quiz_id: str,
    device_id: str = Query(default="", max_length=128),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            member_service.get_assessment_session,
            _resolve_authenticated_user_id(authorization),
            quiz_id,
            device_id=device_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssessmentSessionError as exc:
        raise _assessment_session_http_error(exc) from exc


@router.get("/assessment/{quiz_id}/report")
async def assessment_report(
    quiz_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            member_service.get_assessment_report,
            _resolve_authenticated_user_id(authorization),
            quiz_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssessmentSessionError as exc:
        raise _assessment_session_http_error(exc) from exc


@router.post(
    "/assessment/{quiz_id}/items/{question_id}/explain",
    # Direct LLM generation per call; the balance gate is a no-op while billing
    # enforcement is off, so the rate limit is the only sustained-burn guard.
    dependencies=[
        Depends(
            route_rate_limit(
                "mobile_assessment_explain",
                default_max_requests=10,
                default_window_seconds=60.0,
            )
        ),
        Depends(
            route_rate_limit(
                "mobile_assessment_explain_daily",
                default_max_requests=200,
                default_window_seconds=86400.0,
            )
        ),
    ],
)
async def assessment_deep_explanation(
    quiz_id: str,
    question_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return await member_service.get_assessment_deep_explanation(
            _resolve_authenticated_user_id(authorization),
            quiz_id,
            question_id,
        )
    except RuntimeError as exc:
        detail = str(exc)
        status_code = 402 if "billing" in detail or "wallet" in detail or "balance" in detail else 429
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/assessment/{quiz_id}/submit",
    dependencies=[
        Depends(
            route_rate_limit(
                "mobile_assessment_submit",
                default_max_requests=10,
                default_window_seconds=60.0,
            )
        ),
        Depends(
            route_rate_limit(
                "mobile_assessment_submit_daily",
                default_max_requests=100,
                default_window_seconds=86400.0,
            )
        ),
    ],
)
async def assessment_submit(
    quiz_id: str,
    body: AssessmentSubmitRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            member_service.submit_assessment,
            _resolve_authenticated_user_id(authorization),
            quiz_id,
            answers=body.answers,
            time_spent_seconds=body.time_spent_seconds,
            device_id=body.device_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssessmentSessionError as exc:
        raise _assessment_session_http_error(exc) from exc


@router.post(
    "/conversations",
    dependencies=[
        Depends(
            route_rate_limit(
                "mobile_create_conversation",
                default_max_requests=20,
                default_window_seconds=60.0,
            )
        )
    ],
)
async def create_conversation(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    resolved_user_id = _resolve_authenticated_user_id(authorization)
    session = await session_store.ensure_session(
        _new_mobile_conversation_id(),
        owner_key=build_user_owner_key(resolved_user_id),
    )
    await session_store.update_session_title(session["id"], "新对话")
    await session_store.update_session_preferences(
        session["id"],
        {
            "source": "wx_miniprogram",
            "user_id": resolved_user_id,
            "archived": False,
            "bot_id": _MOBILE_TUTORBOT_ID,
        },
    )
    return {
        "conversation": {
            "id": session["id"],
            "title": "新对话",
            "created_at": _ts_to_iso(session.get("created_at")),
            "created_at_ms": _ts_to_ms(session.get("created_at")),
        }
    }


@router.get("/conversations")
async def list_conversations(
    archived: bool = False,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_authenticated_user_id(authorization)
    sessions = await session_store.list_sessions_by_owner(
        build_user_owner_key(resolved_user_id),
        source="wx_miniprogram",
        archived=archived,
        limit=200,
        offset=0,
    )
    return {
        "conversations": [
            _serialize_mobile_conversation(item)
            for item in _merge_mobile_conversation_rows(list(sessions or []))
        ]
    }


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_authenticated_user_id(authorization)
    sessions = await _load_mobile_conversation_variants(conversation_id, resolved_user_id)
    if not sessions:
        raise HTTPException(status_code=404, detail="Conversation not found")
    merged_messages: list[dict[str, Any]] = []
    hydrated_rows: list[dict[str, Any]] = []
    found_mobile_session = False
    for session_row in sessions:
        session = await session_store.get_session_with_messages(str(session_row.get("id") or ""))
        if session is None:
            continue
        preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
        if preferences.get("source") != "wx_miniprogram":
            continue
        found_mobile_session = True
        row_preferences = (
            session_row.get("preferences") if isinstance(session_row.get("preferences"), dict) else {}
        )
        merged_preferences = _merge_mobile_conversation_preferences(
            row_preferences,
            preferences,
            prefer_row=True,
        )
        hydrated_row = dict(session_row or {})
        hydrated_row.update(
            {
                "id": session.get("id") or session_row.get("id"),
                "session_id": session.get("id") or session_row.get("session_id"),
                "preferences": merged_preferences,
                "created_at": session.get("created_at", session_row.get("created_at")),
                "updated_at": session.get("updated_at", session_row.get("updated_at")),
                "title": session.get("title", session_row.get("title")),
                "status": session.get("status", session_row.get("status")),
                "capability": session.get("capability", session_row.get("capability")),
                "message_count": len(session.get("messages") or []),
            }
        )
        hydrated_rows.append(hydrated_row)
        for message in list(session.get("messages") or []):
            if not isinstance(message, dict):
                continue
            message_with_provenance = dict(message)
            message_with_provenance["_history_session_id"] = str(session.get("id") or session_row.get("id") or "")
            merged_messages.append(message_with_provenance)
    if not found_mobile_session:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation_rows = _merge_mobile_conversation_rows(hydrated_rows)
    conversation = conversation_rows[0] if conversation_rows else {"id": conversation_id}
    return {
        "conversation": _serialize_mobile_conversation(conversation),
        "messages": [
            _serialize_mobile_message(item)
            for item in _merge_mobile_message_rows(merged_messages)
        ]
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_authenticated_user_id(authorization)
    sessions = await _load_mobile_conversation_variants(conversation_id, resolved_user_id)
    if not sessions:
        raise HTTPException(status_code=404, detail="Conversation not found")
    deleted = False
    for session in sessions:
        session_id = str(session.get("id") or "").strip()
        if not session_id:
            continue
        deleted = await session_store.delete_session(session_id) or deleted
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@router.post(
    "/conversations/batch",
    dependencies=[
        Depends(
            route_rate_limit(
                "mobile_conversations_batch",
                default_max_requests=10,
                default_window_seconds=60.0,
            )
        )
    ],
)
async def batch_conversations(
    body: BatchConversationRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_authenticated_user_id(authorization)
    updated = 0
    for conversation_id in body.conversation_ids:
        sessions = await _load_mobile_conversation_variants(conversation_id, resolved_user_id)
        if not sessions:
            continue
        if body.action == "delete":
            for session in sessions:
                updated += 1 if await session_store.delete_session(str(session.get("id") or "")) else 0
            continue
        for session in sessions:
            updated += 1 if await session_store.update_session_preferences(
                str(session.get("id") or ""),
                {"archived": body.action == "archive"},
            ) else 0
    return {"updated": updated, "action": body.action}


@router.post("/sessions/{session_id}/messages/{message_id}/feedback")
async def submit_message_feedback(
    session_id: str,
    message_id: str,
    body: ChatFeedbackRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _persist_mobile_feedback(
        body=body,
        authorization=authorization,
        session_id=session_id,
        message_id=message_id,
    )


@router.post("/chat/feedback")
async def chat_feedback(body: ChatFeedbackRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    # Backward-compatible alias for older mini program builds.
    return await _persist_mobile_feedback(
        body=body,
        authorization=authorization,
    )


@router.post("/chat/feedback/attachments")
async def upload_chat_feedback_attachment(
    file: UploadFile = File(...),
    kind: str = Form(default=""),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    data = await file.read(_FEEDBACK_ATTACHMENT_MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Attachment file is empty")
    if len(data) > _FEEDBACK_ATTACHMENT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Attachment file is too large",
        )

    filename = safe_filename(file.filename or "")
    if not filename:
        ext = ".mp4" if str(kind or "").lower() == "video" else ".jpg"
        filename = f"feedback{ext}"
    mime_type = str(file.content_type or "").strip()
    guessed_mime, _ = mimetypes.guess_type(filename)
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in {"image", "video"}:
        normalized_kind = "video" if (mime_type or guessed_mime or "").startswith("video/") else "image"
    attachment_id = f"fb-{uuid4().hex}"
    session_id = feedback_attachment_session_id(user_id)
    try:
        url = await get_attachment_store().put(
            session_id=session_id,
            attachment_id=attachment_id,
            filename=filename,
            data=data,
            mime_type=mime_type or guessed_mime or "",
        )
    except Exception as exc:
        logger.warning("Feedback attachment upload failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to persist attachment") from exc
    return {
        "attachment": {
            "id": attachment_id,
            "kind": normalized_kind,
            "filename": filename,
            "mime_type": mime_type or guessed_mime or "",
            "size": len(data),
            "url": url,
        }
    }


@router.post(
    "/mobile/chat/start",
    dependencies=_MOBILE_CHAT_START_TURN_DEPENDENCIES,
    include_in_schema=False,
)
@router.post(
    "/mobile/chat/start-turn",
    dependencies=_MOBILE_CHAT_START_TURN_DEPENDENCIES,
    include_in_schema=False,
)
@router.post(
    "/chat/start-turn",
    dependencies=_MOBILE_CHAT_START_TURN_DEPENDENCIES,
)
async def mobile_chat_start_turn(
    body: MobileStartTurnRequest,
    authorization: str | None = Header(default=None),
    eval_bypass: str | None = Header(default=None, alias=EVAL_BILLING_BYPASS_HEADER),
) -> dict[str, Any]:
    query = str(body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    resolved_user_id = _resolve_authenticated_user_id(authorization)
    resolved_wallet_user_id = _resolve_wallet_lookup_user_id(authorization)
    eval_bypass_verified = False
    if eval_bypass:
        # Always run the validator when a header is present; it fast-returns False
        # when no key is configured, so this does not leak key-presence via timing.
        eval_bypass_verified = eval_billing_bypass_signature_valid(
            eval_bypass,
            *_eval_bypass_identity_candidates(resolved_user_id, resolved_wallet_user_id),
        )
    _assert_billing_quota_available(
        authorization,
        wallet_user_id=resolved_wallet_user_id,
        authenticated_user_id=resolved_user_id,
        eval_bypass_verified=eval_bypass_verified,
    )
    runtime_session_id, public_conversation_id = await _resolve_mobile_runtime_session_id(
        body.conversation_id,
        resolved_user_id,
    )
    payload = _build_mobile_turn_payload(
        body=body,
        authenticated_user_id=resolved_user_id,
        wallet_user_id=resolved_wallet_user_id,
        query=query,
        eval_bypass_verified=eval_bypass_verified,
    )
    if runtime_session_id:
        payload["session_id"] = runtime_session_id
    session, turn = await turn_runtime.start_turn(payload)
    response_conversation_id = (
        public_conversation_id
        or _normalize_mobile_conversation_id(session)
        or str(session.get("id") or "")
    )
    return _build_tutorbot_start_response(
        conversation_id=response_conversation_id,
        query=query,
        turn_id=str(turn.get("id") or ""),
        capability=str(turn.get("capability") or "chat") or "chat",
    )
