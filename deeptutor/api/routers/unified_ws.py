"""
Unified WebSocket Endpoint
==========================

Single ``/api/v1/ws`` endpoint for turn-based execution and replayable streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from deeptutor.api._secure_router import secure_ws_endpoint, secure_ws_router
from deeptutor.api.dependencies import AuthContext, enforce_websocket_rate_limit
from deeptutor.api.runtime_metrics import get_turn_runtime_metrics
from deeptutor.runtime.safety import spawn_task
from deeptutor.services.question_followup import (
    PUBLIC_HIDDEN_PAYLOAD_KEYS,
    redact_question_followup_context_for_public,
)
from deeptutor.contracts.unified_turn import (
    UnifiedTurnCancelMessage,
    UnifiedTurnResumeMessage,
    UnifiedTurnStartMessage,
    UnifiedTurnSubscribeMessage,
    UnifiedTurnSubscribeSessionMessage,
    UnifiedTurnUnsubscribeMessage,
)

router = secure_ws_router()
logger = logging.getLogger(__name__)

# F5: hard cap on a single inbound WS text frame (character length). The handler
# json.loads() the frame before schema validation, so without a boundary cap an
# authenticated client could send a ~16MiB frame and force a large parse + memory
# spike on every start_turn (only soft-bounded by the 10/60s start_turn rate limit).
# 128K chars comfortably fits a long tutoring message + attachment metadata + config
# while killing the amplification vector. Applies to every message type at the entry.
_MAX_WS_INBOUND_FRAME_CHARS = 128 * 1024

# Per-user concurrent WS connection cap (anti fd/memory-exhaustion DoS). The connect
# rate limit (60/60s) bounds reconnect *rate*, not the number of simultaneously OPEN
# connections — one account could hold hundreds open, each carrying subscription tasks.
# Shared across workers via Redis (valkey) so the cap is a true per-user limit, not
# per-process (with W workers a per-process counter would allow W × cap). Admins exempt.
_MAX_WS_CONNECTIONS_PER_USER = 8
# Redis ZSET members older than this are purged on the next acquire. This self-heals a
# crashed worker's never-released entries (no permanent lock-out), and makes the limit
# fail-OPEN (a very-long-idle connection may stop being counted) rather than fail-closed.
_WS_CONN_TTL_SECONDS = 3600
_active_ws_connections: dict[str, int] = {}
_active_ws_connections_lock = asyncio.Lock()
_ws_conn_redis: "object | None" = None
_ws_conn_redis_resolved = False


def _get_ws_conn_redis() -> "object | None":
    """Reuse the rate-limit Redis (valkey) config for a shared connection counter.
    Returns None when Redis isn't configured/available — callers fall back to the
    per-process counter."""
    global _ws_conn_redis, _ws_conn_redis_resolved
    if _ws_conn_redis_resolved:
        return _ws_conn_redis
    _ws_conn_redis_resolved = True
    backend = str(os.getenv("DEEPTUTOR_RATE_LIMIT_BACKEND", "sqlite")).strip().lower()
    url = str(os.getenv("DEEPTUTOR_RATE_LIMIT_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    if backend != "redis" or not url:
        return None
    try:
        import redis

        # Sync client used on the event-loop thread — short socket timeouts so a
        # half-dead valkey degrades to the per-process counter instead of stalling
        # every WS connect/disconnect indefinitely.
        _ws_conn_redis = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
    except Exception:  # noqa: BLE001 — any failure → fall back to per-process
        logger.warning("WS conn cap: Redis client init failed; using per-process counter", exc_info=True)
        _ws_conn_redis = None
    return _ws_conn_redis


async def _try_acquire_ws_slot(user_id: str) -> str | None:
    """Reserve a per-user connection slot. Returns an opaque token (pass to release) or
    None if the cap is hit. Shared across workers via a self-healing Redis ZSET; falls
    back to a per-process counter (fail-open) when Redis is unavailable."""
    token = uuid.uuid4().hex
    client = _get_ws_conn_redis()
    if client is not None:
        key = f"deeptutor:ws-conn:{user_id}"
        now = time.time()
        try:
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, now - _WS_CONN_TTL_SECONDS)  # purge crashed-worker leftovers
            pipe.zadd(key, {token: now})
            pipe.zcard(key)
            pipe.expire(key, _WS_CONN_TTL_SECONDS)
            results = pipe.execute()
            count = int(results[2])
            if count > _MAX_WS_CONNECTIONS_PER_USER:
                client.zrem(key, token)  # over cap — undo our reservation
                return None
            return f"redis:{token}"
        except Exception:  # noqa: BLE001 — Redis hiccup → fall through to per-process
            logger.warning("WS conn cap: Redis acquire failed; using per-process counter", exc_info=True)
    async with _active_ws_connections_lock:
        current = _active_ws_connections.get(user_id, 0)
        if current >= _MAX_WS_CONNECTIONS_PER_USER:
            return None
        _active_ws_connections[user_id] = current + 1
    return "local"


async def _release_ws_slot(user_id: str, token: str) -> None:
    if token.startswith("redis:"):
        client = _get_ws_conn_redis()
        if client is not None:
            try:
                client.zrem(f"deeptutor:ws-conn:{user_id}", token[len("redis:"):])
            except Exception:  # noqa: BLE001 — entry self-heals via TTL purge
                logger.warning("WS conn cap: Redis release failed; entry will TTL-expire", exc_info=True)
        return
    async with _active_ws_connections_lock:
        remaining = _active_ws_connections.get(user_id, 0) - 1
        if remaining > 0:
            _active_ws_connections[user_id] = remaining
        else:
            _active_ws_connections.pop(user_id, None)


def _discard_current_subscription_task(
    subscription_tasks: dict[str, asyncio.Task[None]],
    key: str,
    task: asyncio.Task[None],
) -> None:
    if subscription_tasks.get(key) is task:
        subscription_tasks.pop(key, None)


async def _await_stopped_subscription_task(key: str, task: asyncio.Task[None]) -> None:
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Unified WS subscription task failed during cleanup: %s", key)

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

    # Defence-in-depth: the eval-bypass marker is server-authored only (set by the
    # mobile start-turn endpoint after signature verification). A client must never
    # be able to smuggle it through a WS-supplied billing_context, so scrub it here
    # regardless of the source guard downstream.
    billing_context = {k: v for k, v in billing_context.items() if k != "eval_bypass"}

    requested_user_id = str(billing_context.get("user_id") or "").strip()
    if requested_user_id and requested_user_id != current_user.user_id and not current_user.is_admin:
        raise PermissionError("Forbidden billing_context user_id")

    config["billing_context"] = {
        **billing_context,
        "source": str(billing_context.get("source") or "authenticated_ws").strip() or "authenticated_ws",
        "user_id": requested_user_id or current_user.user_id,
    }
    return {**payload, "config": config, "_authenticated_user_id": current_user.user_id}


# plan §Phase 3 Step 3.2 / Batch C Gap 3 — public payload redaction at the
# /api/v1/ws boundary. Hidden grading authority (grading_key, correct_answer,
# scoring_points, explanation) must never leave the server through this stream,
# regardless of nesting depth or visibility=internal/public.
_HIDDEN_PAYLOAD_KEYS: tuple[str, ...] = PUBLIC_HIDDEN_PAYLOAD_KEYS

# plan §Phase 3 Step 3.2 — evidence-style entries describe which source field
# produced the evidence value. If the named field references a hidden authority,
# the sibling ``value`` / ``content`` slot leaks the hidden value. Drop the
# whole entry. Mirrors question_followup._EVIDENCE_FIELD_KEYS so both public
# boundaries share the same rule.
_EVIDENCE_FIELD_KEYS: tuple[str, ...] = ("field", "source_field", "source_key", "name")


def _is_hidden_payload_key(value: str) -> bool:
    return any(part in _HIDDEN_PAYLOAD_KEYS for part in value.split("."))


def _is_hidden_evidence_entry(value: dict[str, Any]) -> bool:
    for key in _EVIDENCE_FIELD_KEYS:
        sibling = value.get(key)
        if isinstance(sibling, str) and _is_hidden_payload_key(sibling):
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
                if not (isinstance(item, str) and _is_hidden_payload_key(item))
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


# Backport item: bound the size of the event copy sent to clients over
# /api/v1/ws so one pathological event (a huge tool dump, a base64 blob in
# metadata) cannot blow up the WS frame or the client. Like
# _redact_event_for_public this runs ONLY on the outbound public copy — the
# persisted turn_events row and the canonical final answer
# (result.metadata.response materialised into messages.content) are never
# touched (turn.md §13 copy-only contract, §96 canonical answer authority).
_MAX_PUBLIC_CONTENT_CHARS = 16000
_MAX_PUBLIC_METADATA_STR_CHARS = 8000
_PUBLIC_TRUNCATION_MARKER = "…[truncated]"


def _clamp_str_for_public(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + _PUBLIC_TRUNCATION_MARKER


def _clamp_value_for_public(value: Any) -> Any:
    if isinstance(value, str):
        return _clamp_str_for_public(value, _MAX_PUBLIC_METADATA_STR_CHARS)
    if isinstance(value, dict):
        return {key: _clamp_value_for_public(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clamp_value_for_public(item) for item in value]
    return value


def _clamp_event_for_public(event: dict[str, Any]) -> dict[str, Any]:
    """Bound the outbound public event size; structure and small fields stay intact.

    Oversized top-level ``content`` and oversized string values inside
    ``metadata`` are truncated with a marker. Realistic oversized payloads are a
    single huge string (image base64, giant tool dump), which per-string
    clamping bounds directly while preserving keys and small values the client
    needs to render. Returns a new dict and never mutates the input.
    """
    if not isinstance(event, dict):
        return event
    clamped = dict(event)
    content = clamped.get("content")
    if isinstance(content, str):
        clamped["content"] = _clamp_str_for_public(content, _MAX_PUBLIC_CONTENT_CHARS)
    metadata = clamped.get("metadata")
    if isinstance(metadata, dict):
        clamped["metadata"] = _clamp_value_for_public(metadata)
    return clamped


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

    # Per-user concurrent connection cap (admins exempt). Acquire before doing any work;
    # release in the finally below. Over-cap → 1013 and return.
    ws_slot_user = None if current_user.is_admin else str(current_user.user_id)
    ws_slot_token: str | None = None
    if ws_slot_user is not None:
        ws_slot_token = await _try_acquire_ws_slot(ws_slot_user)
        if ws_slot_token is None:
            logger.warning("Unified WS connection cap hit for user=%s", ws_slot_user)
            await ws.close(code=1013, reason="Too many concurrent connections")
            return

    get_turn_runtime_metrics().record_ws_open()
    closed = False
    subscription_tasks: dict[str, asyncio.Task[None]] = {}
    send_lock = asyncio.Lock()

    async def safe_send(data: dict[str, Any]) -> None:
        nonlocal closed
        if closed:
            return
        async with send_lock:
            if closed:
                return
            try:
                await ws.send_json(data)
            except Exception:
                # Transport send failed: the peer is gone. Mark closed so the rest
                # of the loop stops touching the socket — but log it (never silent),
                # so a flapping client / send-side bug is observable.
                logger.warning(
                    "Unified WS send failed; marking connection closed (event_type=%s)",
                    data.get("type") if isinstance(data, dict) else None,
                )
                closed = True

    async def stop_subscription(key: str) -> None:
        task = subscription_tasks.pop(key, None)
        if task is None:
            return
        await _await_stopped_subscription_task(key, task)

    async def subscribe_turn(turn_id: str, after_seq: int = 0) -> None:
        from deeptutor.services.session import get_turn_runtime_manager

        async def _forward() -> None:
            runtime = get_turn_runtime_manager()
            async for event in runtime.subscribe_turn(turn_id, after_seq=after_seq):
                await safe_send(_clamp_event_for_public(_redact_event_for_public(event)))

        await stop_subscription(turn_id)
        task: asyncio.Task[None] | None = None

        async def _run_subscription() -> None:
            try:
                await _forward()
            finally:
                if task is not None:
                    _discard_current_subscription_task(subscription_tasks, turn_id, task)

        task = spawn_task(_run_subscription(), name=f"ws.subscribe_turn:{turn_id}")
        subscription_tasks[turn_id] = task

    async def subscribe_session(session_id: str, after_seq: int = 0) -> None:
        from deeptutor.services.session import get_turn_runtime_manager

        async def _forward() -> None:
            runtime = get_turn_runtime_manager()
            async for event in runtime.subscribe_session(session_id, after_seq=after_seq):
                await safe_send(_clamp_event_for_public(_redact_event_for_public(event)))

        key = f"session:{session_id}"
        await stop_subscription(key)
        task: asyncio.Task[None] | None = None

        async def _run_subscription() -> None:
            try:
                await _forward()
            finally:
                if task is not None:
                    _discard_current_subscription_task(subscription_tasks, key, task)

        task = spawn_task(_run_subscription(), name=f"ws.subscribe_session:{session_id}")
        subscription_tasks[key] = task

    try:
        while not closed:
            raw = await ws.receive_text()
            if len(raw) > _MAX_WS_INBOUND_FRAME_CHARS:
                await safe_send(
                    {
                        "type": "error",
                        "content": (
                            f"Message too large ({len(raw)} chars; "
                            f"limit {_MAX_WS_INBOUND_FRAME_CHARS})."
                        ),
                    }
                )
                continue
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

                # Per-user DAILY turn budget. The burst limit above (10/60s) stops spikes
                # but not sustained burn: 10/min for 24h = ~14k turns/day, each a paid LLM
                # call — an economic DoS on one account. This caps total turns/user/day so a
                # single account cannot drain the API budget. Generous headroom for real
                # study; tune via set_rate_limit_policy("ws_start_turn_daily", max, window).
                if not await enforce_websocket_rate_limit(
                    ws,
                    "ws_start_turn_daily",
                    default_max_requests=500,
                    default_window_seconds=86400.0,
                ):
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
                except asyncio.CancelledError:
                    # Cancellation is control flow, not a turn failure — never swallow it.
                    raise
                except Exception:
                    # Boundary contract: a single-turn execution error must NOT tear
                    # down the receive loop. Emit a turn-level error event and keep
                    # serving the connection; only transport/protocol errors disconnect.
                    logger.exception("Unified WS start_turn failed (unhandled)")
                    await safe_send(
                        _build_error_event(
                            content=_public_ws_failure_message("start turn"),
                            session_id=str(msg.get("session_id") or ""),
                        )
                    )
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
                try:
                    cancelled = await runtime.cancel_turn(cancel_message.turn_id)
                except asyncio.CancelledError:
                    # Cancellation is control flow, not a turn failure — never swallow it.
                    raise
                except Exception:
                    # Same boundary contract as start_turn: a single cancel operation
                    # error must not disconnect the client. Emit a turn-level error
                    # event and keep serving the connection.
                    logger.exception("Unified WS cancel_turn failed (unhandled)")
                    await safe_send(
                        _build_error_event(
                            content=_public_ws_failure_message("cancel turn"),
                            turn_id=cancel_message.turn_id,
                        )
                    )
                    continue
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
        try:
            for key in list(subscription_tasks.keys()):
                await stop_subscription(key)
        finally:
            get_turn_runtime_metrics().record_ws_close()
            if ws_slot_user is not None and ws_slot_token is not None:
                await _release_ws_slot(ws_slot_user, ws_slot_token)
