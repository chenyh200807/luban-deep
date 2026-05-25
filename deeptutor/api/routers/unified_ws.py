"""
Unified WebSocket Endpoint
==========================

Single ``/api/v1/ws`` endpoint for turn-based execution and replayable streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from deeptutor.api._secure_router import secure_ws_endpoint
from deeptutor.api.dependencies import AuthContext, enforce_websocket_rate_limit
from deeptutor.api.runtime_metrics import get_turn_runtime_metrics
from deeptutor.runtime.safety import spawn_task
from deeptutor.services.question_followup import redact_question_followup_context_for_public
from deeptutor.contracts.unified_turn import (
    UnifiedTurnCancelMessage,
    UnifiedTurnResumeMessage,
    UnifiedTurnStartMessage,
    UnifiedTurnSubscribeMessage,
    UnifiedTurnSubscribeSessionMessage,
    UnifiedTurnUnsubscribeMessage,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_LEGACY_INTERACTION_HINT_KEYS = (
    "profile",
    "scene",
    "product_surface",
    "entry_role",
    "subject_domain",
    "requested_response_mode",
    "teaching_mode",
    "effective_response_mode",
    "response_mode_degrade_reason",
    "preferred_question_type",
    "allow_general_chat_fallback",
    "priorities",
    "suppress_answer_reveal_on_generate",
    "prefer_question_context_grading",
    "prefer_concept_teaching_slots",
    "current_info_required",
    "grounding_reasons",
    "textbook_delta_query",
)


def _build_error_event(
    *,
    content: str,
    session_id: str = "",
    turn_id: str = "",
) -> dict[str, Any]:
    return {
        "type": "error",
        "source": "unified_ws",
        "stage": "",
        "content": content,
        "metadata": {"turn_terminal": True, "status": "rejected"},
        "session_id": session_id,
        "turn_id": turn_id,
        "seq": 0,
    }


def _public_ws_failure_message(action: str) -> str:
    return f"Unable to {action}. Please try again later."


def _public_validation_message(message_type: str) -> str:
    return f"Invalid {message_type} payload."


async def _authorize_session_access(
    session_id: str,
    current_user: AuthContext,
) -> None:
    """SR1 PR-1b: strict mode — A2 owner_key bypass removed.

    `current_user` is guaranteed non-None by `secure_ws_endpoint` at the WS
    handshake; the previous "owner_key 缺失 + anon 放行" branch is dead code
    and removed. Real legacy sessions with empty owner_key are backfilled by
    PR-α (`scripts/migrations/pr_alpha_session_owner_key_backfill.py`).
    """
    from deeptutor.services.session import build_user_owner_key, get_sqlite_session_store

    if current_user.is_admin:
        return
    store = get_sqlite_session_store()
    owner_key = await store.get_session_owner_key(session_id)
    if not owner_key:
        # Pre-PR-α legacy session — strict: deny. Admin override above.
        raise PermissionError("Session not found")
    if owner_key != build_user_owner_key(current_user.user_id):
        raise PermissionError("Session not found")


async def _authorize_turn_access(
    turn_id: str,
    current_user: AuthContext,
) -> str:
    """SR1 PR-1b: current_user must be non-None (enforced at WS handshake)."""
    from deeptutor.services.session import get_sqlite_session_store

    store = get_sqlite_session_store()
    turn = await store.get_turn(turn_id)
    if turn is None:
        raise LookupError("Turn not found")
    session_id = str(turn.get("session_id") or "").strip()
    await _authorize_session_access(session_id, current_user)
    return session_id


async def _get_active_turn_id_for_session(session_id: str) -> str:
    from deeptutor.services.session import get_sqlite_session_store

    store = get_sqlite_session_store()
    active_turn = await store.get_active_turn(session_id)
    if active_turn is None:
        raise LookupError("Turn not found")
    return str(active_turn.get("id") or "").strip()


def _bind_authenticated_user(
    payload: dict[str, Any],
    current_user: AuthContext | None,
) -> dict[str, Any]:
    from deeptutor.tutorbot.response_mode import normalize_requested_response_mode

    config = dict(payload.get("config", {}) or {})
    interaction_hints = config.get("interaction_hints")
    if not isinstance(interaction_hints, dict):
        interaction_hints = {}

    legacy_interaction_hints = {
        key: config.pop(key)
        for key in _LEGACY_INTERACTION_HINT_KEYS
        if key in config
    }
    if legacy_interaction_hints:
        config["interaction_hints"] = {
            **legacy_interaction_hints,
            **interaction_hints,
        }
    elif isinstance(config.get("interaction_hints"), dict):
        config["interaction_hints"] = interaction_hints

    normalized_hints = config.get("interaction_hints")
    if isinstance(normalized_hints, dict):
        requested_response_mode = normalize_requested_response_mode(
            normalized_hints.get("requested_response_mode") or normalized_hints.get("teaching_mode")
        )
        if requested_response_mode:
            normalized_hints["requested_response_mode"] = requested_response_mode
        normalized_hints.pop("teaching_mode", None)

    if current_user is None:
        return {**payload, "config": config}

    billing_context = config.get("billing_context")
    if not isinstance(billing_context, dict):
        billing_context = {}

    requested_user_id = str(billing_context.get("user_id") or "").strip()
    if requested_user_id and requested_user_id != current_user.user_id and not current_user.is_admin:
        raise PermissionError("Forbidden billing_context user_id")

    config["billing_context"] = {
        **billing_context,
        "source": str(billing_context.get("source") or "authenticated_ws").strip() or "authenticated_ws",
        "user_id": requested_user_id or current_user.user_id,
    }
    return {**payload, "config": config}


# plan §Phase 3 Step 3.2 / Batch C Gap 3 — public payload redaction at the
# /api/v1/ws boundary. Hidden grading authority (grading_key, correct_answer,
# scoring_points, explanation) must never leave the server through this stream,
# regardless of nesting depth or visibility=internal/public.
_HIDDEN_PAYLOAD_KEYS: tuple[str, ...] = (
    "grading_key",
    "scoring_points",
    "correct_answer",
    "explanation",
)

# plan §Phase 3 Step 3.2 — evidence-style entries describe which source field
# produced the evidence value. If the named field references a hidden authority,
# the sibling ``value`` / ``content`` slot leaks the hidden value. Drop the
# whole entry. Mirrors question_followup._EVIDENCE_FIELD_KEYS so both public
# boundaries share the same rule.
_EVIDENCE_FIELD_KEYS: tuple[str, ...] = ("field", "source_field", "source_key", "name")


def _is_hidden_evidence_entry(value: dict[str, Any]) -> bool:
    for key in _EVIDENCE_FIELD_KEYS:
        sibling = value.get(key)
        if isinstance(sibling, str) and sibling in _HIDDEN_PAYLOAD_KEYS:
            return True
    return False


def _redact_value_for_public(value: Any) -> Any:
    """Recursively drop hidden authority from nested dicts/lists.

    Three rules (plan §Phase 3 Step 3.2), aligned with
    ``deeptutor.services.question_followup._drop_hidden_value``:

      1. Drop dict keys in ``_HIDDEN_PAYLOAD_KEYS``.
      2. Drop the whole dict when it is an evidence-style entry whose
         field-name slot points at a hidden authority.
      3. Filter ``source_fields`` lists to non-hidden entries; drop slot if
         emptied.

    Scalars pass through untouched. A ``None`` return value from
    ``_redact_dict_for_public`` signals "drop me" — list iteration and dict
    slot iteration both honour that signal.
    """
    if isinstance(value, dict):
        return _redact_dict_for_public(value)
    if isinstance(value, list):
        out: list[Any] = []
        for item in value:
            cleaned = _redact_value_for_public(item)
            if cleaned is None and isinstance(item, dict):
                continue
            out.append(cleaned)
        return out
    return value


def _redact_dict_for_public(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Drop hidden keys at this level and recurse into nested values.

    Returns ``None`` when the dict itself is a hidden evidence entry; caller
    treats that as "drop this slot/list item".

    ``question_followup_context`` and ``active_object`` keep their canonical
    redactors so existing question_followup public-payload semantics are
    preserved exactly.
    """
    if _is_hidden_evidence_entry(payload):
        return None
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _HIDDEN_PAYLOAD_KEYS:
            continue
        if key == "source_fields" and isinstance(value, list):
            kept = [
                item
                for item in value
                if not (isinstance(item, str) and item in _HIDDEN_PAYLOAD_KEYS)
            ]
            if not kept:
                continue
            clean[key] = kept
            continue
        if key == "question_followup_context" and isinstance(value, dict):
            redacted = redact_question_followup_context_for_public(value)
            clean[key] = redacted if redacted is not None else None
            continue
        if key == "active_object" and isinstance(value, dict):
            clean[key] = _redact_active_object_for_public(value)
            continue
        cleaned = _redact_value_for_public(value)
        if cleaned is None and isinstance(value, dict):
            continue
        clean[key] = cleaned
    return clean


def _redact_active_object_for_public(active_object: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(active_object, dict):
        return active_object
    redacted: dict[str, Any] = {}
    for key, value in active_object.items():
        if key in _HIDDEN_PAYLOAD_KEYS:
            continue
        if key == "state_snapshot" and isinstance(value, dict):
            redacted[key] = redact_question_followup_context_for_public(value) or {}
            continue
        redacted[key] = _redact_value_for_public(value)
    return redacted


def _redact_metadata_for_public(metadata: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy metadata dict and drop hidden authority fields.

    plan §Phase 3 Step 3.2 — hidden grading_key/correct_answer/scoring_points/explanation
    must not leak through any stream event metadata to the client, at any
    nesting depth (e.g. ``metadata.question.correct_answer`` on progress
    events, or ``construction_grading_result.evidence_refs[i]`` where
    ``field='correct_answer'`` leaks the standard answer via ``value``).
    String values are NOT rewritten — only dictionary keys are dropped, so
    user-visible markdown bodies stay intact.
    """
    if not isinstance(metadata, dict):
        return metadata
    return _redact_dict_for_public(metadata) or {}


def _redact_event_for_public(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        return event
    if "metadata" not in event or not isinstance(event["metadata"], dict):
        return event
    clean = dict(event)
    clean["metadata"] = _redact_metadata_for_public(event["metadata"])
    return clean


@router.websocket("/ws")
async def unified_websocket(ws: WebSocket) -> None:
    # SR1 PR-1b: A2 closed — anonymous WS connections now reject 4401 (was: pass-through).
    current_user = await secure_ws_endpoint(
        ws,
        rate_limit_scope="unified_ws_connect",
        rate_limit_max=60,
        rate_limit_window_seconds=60.0,
    )
    if current_user is None:
        return  # ws already closed (4401 or 1013)
    get_turn_runtime_metrics().record_ws_open()
    closed = False
    subscription_tasks: dict[str, asyncio.Task[None]] = {}

    async def safe_send(data: dict[str, Any]) -> None:
        nonlocal closed
        if closed:
            return
        try:
            await ws.send_json(data)
        except Exception:
            closed = True

    async def stop_subscription(key: str) -> None:
        task = subscription_tasks.pop(key, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def subscribe_turn(turn_id: str, after_seq: int = 0) -> None:
        from deeptutor.services.session import get_turn_runtime_manager

        async def _forward() -> None:
            runtime = get_turn_runtime_manager()
            async for event in runtime.subscribe_turn(turn_id, after_seq=after_seq):
                await safe_send(_redact_event_for_public(event))

        await stop_subscription(turn_id)
        subscription_tasks[turn_id] = spawn_task(
            _forward(),
            name=f"ws.subscribe_turn:{turn_id}",
            on_error=lambda _exc: subscription_tasks.pop(turn_id, None),
        )

    async def subscribe_session(session_id: str, after_seq: int = 0) -> None:
        from deeptutor.services.session import get_turn_runtime_manager

        async def _forward() -> None:
            runtime = get_turn_runtime_manager()
            async for event in runtime.subscribe_session(session_id, after_seq=after_seq):
                await safe_send(_redact_event_for_public(event))

        key = f"session:{session_id}"
        await stop_subscription(key)
        subscription_tasks[key] = spawn_task(
            _forward(),
            name=f"ws.subscribe_session:{session_id}",
            on_error=lambda _exc: subscription_tasks.pop(key, None),
        )

    try:
        while not closed:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await safe_send({"type": "error", "content": "Invalid JSON."})
                continue

            msg_type = msg.get("type")

            if msg_type in {"message", "start_turn"}:
                # SR3 PR-3: per-connection start_turn rate limit (v2.1 P1-S3 promoted to P0).
                # Stops a single authenticated client from flooding LLM with start_turn spam.
                if not await enforce_websocket_rate_limit(
                    ws,
                    "ws_start_turn",
                    default_max_requests=10,
                    default_window_seconds=60.0,
                ):
                    # ws.close(1013) already called; main loop must end.
                    closed = True
                    return

                from deeptutor.services.session import get_turn_runtime_manager

                runtime = get_turn_runtime_manager()
                try:
                    start_message = UnifiedTurnStartMessage.model_validate(msg)
                    payload = start_message.model_dump(exclude_none=True)
                    session_id = str(payload.get("session_id") or "").strip()
                    if session_id:
                        await _authorize_session_access(session_id, current_user)
                    payload = _bind_authenticated_user(payload, current_user)
                    _, turn = await runtime.start_turn(payload)
                except PermissionError:
                    await safe_send(
                        _build_error_event(
                            content="Unauthorized request.",
                            session_id=str(msg.get("session_id") or ""),
                        )
                    )
                    continue
                except RuntimeError:
                    logger.exception("Unified WS start_turn failed")
                    await safe_send(
                        _build_error_event(
                            content=_public_ws_failure_message("start turn"),
                            session_id=str(msg.get("session_id") or ""),
                        )
                    )
                    continue
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("start_turn")})
                    continue
                await subscribe_turn(turn["id"], after_seq=0)
                continue

            if not msg_type:
                legacy_session_id = str(msg.get("chat_id") or "").strip()
                legacy_content = str(msg.get("content") or "").strip()
                if legacy_session_id and legacy_content:
                    try:
                        await _authorize_session_access(legacy_session_id, current_user)
                        active_turn_id = await _get_active_turn_id_for_session(legacy_session_id)
                    except LookupError:
                        await safe_send(
                            _build_error_event(
                                content="Turn not found",
                                session_id=legacy_session_id,
                            )
                        )
                        continue
                    except PermissionError:
                        await safe_send(
                            _build_error_event(
                                content="Session not found",
                                session_id=legacy_session_id,
                            )
                        )
                        continue
                    await subscribe_turn(active_turn_id, after_seq=0)
                    continue

            if msg_type == "subscribe_turn":
                try:
                    sub_message = UnifiedTurnSubscribeMessage.model_validate(msg)
                    await _authorize_turn_access(sub_message.turn_id, current_user)
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("subscribe_turn")})
                    continue
                except LookupError:
                    await safe_send(
                        _build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or ""))
                    )
                    continue
                except PermissionError:
                    await safe_send(_build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or "")))
                    continue
                await subscribe_turn(sub_message.turn_id, after_seq=sub_message.after_seq)
                continue

            if msg_type == "subscribe_session":
                try:
                    sub_session_message = UnifiedTurnSubscribeSessionMessage.model_validate(msg)
                    await _authorize_session_access(sub_session_message.session_id, current_user)
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("subscribe_session")})
                    continue
                except PermissionError:
                    await safe_send(
                        _build_error_event(
                            content="Session not found",
                            session_id=str(msg.get("session_id") or ""),
                        )
                    )
                    continue
                await subscribe_session(
                    sub_session_message.session_id,
                    after_seq=sub_session_message.after_seq,
                )
                continue

            if msg_type == "resume_from":
                try:
                    resume_message = UnifiedTurnResumeMessage.model_validate(msg)
                    await _authorize_turn_access(resume_message.turn_id, current_user)
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("resume_from")})
                    continue
                except LookupError:
                    await safe_send(
                        _build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or ""))
                    )
                    continue
                except PermissionError:
                    await safe_send(_build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or "")))
                    continue
                await subscribe_turn(resume_message.turn_id, after_seq=resume_message.seq)
                continue

            if msg_type == "unsubscribe":
                try:
                    unsubscribe_message = UnifiedTurnUnsubscribeMessage.model_validate(msg)
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("unsubscribe")})
                    continue
                if unsubscribe_message.turn_id:
                    await stop_subscription(unsubscribe_message.turn_id)
                if unsubscribe_message.session_id:
                    await stop_subscription(f"session:{unsubscribe_message.session_id}")
                continue

            if msg_type == "cancel_turn":
                try:
                    cancel_message = UnifiedTurnCancelMessage.model_validate(msg)
                    await _authorize_turn_access(cancel_message.turn_id, current_user)
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("cancel_turn")})
                    continue
                except LookupError:
                    await safe_send(
                        _build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or ""))
                    )
                    continue
                except PermissionError:
                    await safe_send(_build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or "")))
                    continue
                from deeptutor.services.session import get_turn_runtime_manager

                runtime = get_turn_runtime_manager()
                cancelled = await runtime.cancel_turn(cancel_message.turn_id)
                if not cancelled:
                    await safe_send(_build_error_event(content="Turn not found", turn_id=cancel_message.turn_id))
                continue

            await safe_send({"type": "error", "content": f"Unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.debug("Client disconnected from /ws")
    except Exception:
        logger.exception("Unified WS error")
        await safe_send(
            _build_error_event(content=_public_ws_failure_message("process the websocket request"))
        )
    finally:
        closed = True
        for key in list(subscription_tasks.keys()):
            await stop_subscription(key)
        get_turn_runtime_metrics().record_ws_close()
