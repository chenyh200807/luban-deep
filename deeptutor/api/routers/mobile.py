from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

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
from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.query_intent import (
    build_grounding_decision,
)
from deeptutor.services.feedback_service import (
    SupabaseFeedbackStore,
    build_mobile_feedback_row,
)
from deeptutor.services.render_presentation import build_canonical_presentation
from deeptutor.services.session import (
    build_user_owner_key,
    get_sqlite_session_store,
    get_turn_runtime_manager,
)
from deeptutor.services.wallet import WalletLedgerEntry, WalletSnapshot, get_wallet_service
from deeptutor.tutorbot.response_mode import normalize_requested_response_mode

router = APIRouter()
logger = logging.getLogger(__name__)
member_service = get_member_console_service()
learner_state_service = LearnerStateService()
turn_runtime = get_turn_runtime_manager()
session_store = get_sqlite_session_store()
wallet_service = get_wallet_service()

_MOBILE_TUTORBOT_ID = CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0]
_MOBILE_TUTORBOT_NAME = "Construction Exam Coach"
_MOBILE_TUTORBOT_DESCRIPTION = "微信小程序主聊天默认建筑实务 TutorBot"
_MOBILE_PLACEHOLDER_TITLES = {"", "new conversation", "新对话"}
_MOBILE_CONVERSATION_LOOKUP_PAGE_SIZE = 500
MobileFeedbackSupabaseClient = SupabaseFeedbackStore


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


def _shadow_compare_wallet_read(user_id: str, *, balance_points: int, source: str) -> None:
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


def _wallet_snapshot_or_zero(user_id: str) -> WalletSnapshot:
    if not getattr(wallet_service, "is_configured", False):
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
        "frozen_delta_micros": int(entry.frozen_after_micros),
        "reference_type": entry.reference_type,
        "reference_id": entry.reference_id,
        "idempotency_key": entry.idempotency_key,
        "metadata": dict(entry.metadata or {}),
        "created_at": entry.created_at,
    }


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
            if not current_prefs.get("conversation_id") and row_prefs.get("conversation_id"):
                current["preferences"] = dict(row_prefs)

    result = [merged[item_id] for item_id in order]
    result.sort(key=lambda item: float(item.get("updated_at") or 0.0), reverse=True)
    return result


def _serialize_mobile_conversation(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
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


def _merge_mobile_message_rows(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        [item for item in messages if isinstance(item, dict)],
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
            if signature == previous_signature and abs(created_at - previous_created_at) <= 2.0:
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
    response_mode_metadata = await _load_feedback_response_mode_metadata(
        session_id=normalized_session_id,
        message_id=normalized_message_id,
    )

    writer = MobileFeedbackSupabaseClient()
    if not writer.is_configured:
        raise HTTPException(status_code=503, detail="Feedback storage unavailable")

    row = build_mobile_feedback_row(
        user_id=user_id,
        session_id=normalized_session_id,
        message_id=normalized_message_id,
        rating=body.rating,
        reason_tags=body.reason_tags,
        comment=body.comment,
        answer_mode=body.answer_mode,
        requested_response_mode=str(response_mode_metadata.get("requested_response_mode") or ""),
        effective_response_mode=str(response_mode_metadata.get("effective_response_mode") or ""),
        response_mode_degrade_reason=str(
            response_mode_metadata.get("response_mode_degrade_reason") or ""
        ),
        actual_tool_rounds=(
            int(response_mode_metadata.get("actual_tool_rounds"))
            if response_mode_metadata.get("actual_tool_rounds") is not None
            else None
        ),
    )
    try:
        await writer.insert_feedback(row)
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


async def _load_feedback_response_mode_metadata(
    *,
    session_id: str,
    message_id: str,
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
    assistant_message = _assistant_message_by_id(
        session.get("messages") if isinstance(session.get("messages"), list) else [],
        message_id=message_id,
    )
    events = assistant_message.get("events") if isinstance(assistant_message, dict) else []
    actual_tool_rounds = sum(
        1
        for item in (events or [])
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "tool_call"
    )
    return {
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
) -> dict[str, Any]:
    requested_tools = [str(item).strip() for item in (body.tools or []) if str(item).strip()]
    grounding_decision = build_grounding_decision(
        query=query,
        knowledge_bases=body.knowledge_bases,
        rag_enabled=True,
        tutorbot_context=True,
    )
    current_info_required = grounding_decision.current_info_required or grounding_decision.textbook_delta_query
    if current_info_required and "web_search" not in requested_tools:
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
    config: dict[str, Any] = {
        "chat_mode": requested_response_mode,
        "interaction_hints": interaction_hints,
        "billing_context": {
            "source": "wx_miniprogram",
            "user_id": authenticated_user_id,
            "wallet_user_id": wallet_user_id or authenticated_user_id,
            "learning_user_id": authenticated_user_id,
        },
        "interaction_profile": interaction_profile,
    }
    if body.followup_question_context:
        config["followup_question_context"] = dict(body.followup_question_context)

    capability = str(body.capability or "").strip() or None
    if capability == "tutorbot":
        capability = None
    config["bot_id"] = _MOBILE_TUTORBOT_ID
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
    return {
        "role": str(message.get("role") or ""),
        "content": str(message.get("content") or ""),
        "created_at": _ts_to_iso(message.get("created_at")),
        "presentation": presentation,
    }


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


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    phone: str


class WechatLoginRequest(BaseModel):
    code: str = ""


class WechatBindPhoneRequest(BaseModel):
    phone_code: str = ""


class MobileStartTurnRequest(BaseModel):
    query: str
    conversation_id: str = ""
    capability: str = ""
    mode: str = "AUTO"
    language: str = "zh"
    interaction_profile: str = "tutorbot"
    interaction_hints: dict[str, Any] | None = None
    tools: list[str] = Field(default_factory=list)
    knowledge_bases: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    followup_question_context: dict[str, Any] | None = None


class ChatFeedbackRequest(BaseModel):
    message_id: str = ""
    conversation_id: str = ""
    rating: int = 0
    reason_tags: list[str] = Field(default_factory=list)
    comment: str = ""
    answer_mode: str = "AUTO"


class AssessmentCreateRequest(BaseModel):
    assessment_type: str = "diagnostic"
    count: int = Field(default=20, ge=1, le=50)


class AssessmentSubmitRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    time_spent_seconds: int = 0


class BatchConversationRequest(BaseModel):
    action: str
    conversation_ids: list[str] = Field(default_factory=list)


@router.post(
    "/auth/login",
    dependencies=[Depends(route_rate_limit("mobile_auth_login", default_max_requests=10, default_window_seconds=60.0))],
)
async def auth_login(body: LoginRequest) -> dict[str, Any]:
    try:
        return member_service.login_with_password(body.username, body.password)
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
        result = member_service.register_with_external_auth(body.username, body.password, body.phone)
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


@router.get("/auth/profile")
async def auth_profile(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    current_user = resolve_auth_context(authorization)
    profile = member_service.get_profile(user_id)
    wallet_user_id = _resolve_wallet_lookup_user_id(authorization)
    snapshot = _wallet_snapshot_or_zero(wallet_user_id)
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
    profile = member_service.update_profile(user_id, patch)
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
        return await member_service.login_with_wechat_code(body.code)
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


@router.get("/billing/ledger")
async def billing_ledger(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    wallet_user_id = _resolve_wallet_lookup_user_id(authorization)
    if not getattr(wallet_service, "is_configured", False):
        raise HTTPException(status_code=503, detail="Wallet service unavailable")
    if not str(wallet_user_id or "").strip():
        return {
            "entries": [],
            "has_more": False,
            "total": 0,
        }
    merge_window = offset + limit + 1
    wallet_rows = wallet_service.list_wallet_ledger(wallet_user_id, limit=merge_window, offset=0)
    legacy_rows = _load_legacy_wallet_ledger_entries(
        authorization,
        wallet_user_id=wallet_user_id,
        limit=merge_window,
    )
    merged_rows = _merge_wallet_ledger_entries(wallet_rows, legacy_rows)
    page = merged_rows[offset : offset + limit]
    has_more = offset + limit < len(merged_rows)
    return {
        "entries": [_serialize_wallet_ledger_entry(item) for item in page],
        "has_more": has_more,
        "total": len(merged_rows),
    }


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


@router.get("/assessment/profile")
async def assessment_profile(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_assessment_profile(_resolve_authenticated_user_id(authorization))


@router.post("/assessment/create")
async def assessment_create(
    body: AssessmentCreateRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return member_service.create_assessment(_resolve_authenticated_user_id(authorization), count=body.count)


@router.post("/assessment/{quiz_id}/submit")
async def assessment_submit(
    quiz_id: str,
    body: AssessmentSubmitRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return member_service.submit_assessment(
            _resolve_authenticated_user_id(authorization),
            quiz_id,
            answers=body.answers,
            time_spent_seconds=body.time_spent_seconds,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/conversations")
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
    for session_row in sessions:
        session = await session_store.get_session_with_messages(str(session_row.get("id") or ""))
        if session is None:
            continue
        preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
        if preferences.get("source") != "wx_miniprogram":
            continue
        merged_messages.extend(list(session.get("messages") or []))
    if not merged_messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
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


@router.post("/conversations/batch")
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


@router.post("/chat/start-turn")
async def mobile_chat_start_turn(
    body: MobileStartTurnRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    query = str(body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    resolved_user_id = _resolve_authenticated_user_id(authorization)
    resolved_wallet_user_id = _resolve_wallet_lookup_user_id(authorization)
    await _assert_mobile_conversation_access(body.conversation_id, resolved_user_id)
    payload = _build_mobile_turn_payload(
        body=body,
        authenticated_user_id=resolved_user_id,
        wallet_user_id=resolved_wallet_user_id,
        query=query,
    )
    session, turn = await turn_runtime.start_turn(payload)
    return _build_tutorbot_start_response(
        conversation_id=str(session.get("id") or ""),
        query=query,
        turn_id=str(turn.get("id") or ""),
        capability=str(turn.get("capability") or "chat") or "chat",
    )
