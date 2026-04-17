from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from deeptutor.services.learner_state.outbox import LearnerStateOutbox
from deeptutor.services.path_service import PathService, get_path_service

_ALLOWED_FIELDS: tuple[str, ...] = (
    "local_focus",
    "active_plan_binding",
    "teaching_policy_override",
    "heartbeat_override",
    "working_memory_projection",
    "channel_presence_override",
    "local_notebook_scope_refs",
    "engagement_state",
    "promotion_candidates",
)
_FORBIDDEN_FIELDS: tuple[str, ...] = (
    "display_name",
    "timezone",
    "plan",
    "goals",
    "summary",
    "profile",
    "progress",
    "weak_points",
    "consent",
    "subscription_status",
)
_DICT_FIELDS = {
    "local_focus",
    "active_plan_binding",
    "teaching_policy_override",
    "heartbeat_override",
    "channel_presence_override",
    "engagement_state",
}
_LIST_FIELDS = {"local_notebook_scope_refs", "promotion_candidates"}
_TEXT_FIELDS = {"working_memory_projection"}
_EPHEMERAL_FIELDS = {
    "local_focus",
    "active_plan_binding",
    "teaching_policy_override",
    "heartbeat_override",
    "working_memory_projection",
    "channel_presence_override",
    "local_notebook_scope_refs",
    "engagement_state",
}
_DEFAULT_OVERLAY_MAX_AGE_HOURS = 72


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def _coerce_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value.astimezone()
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text).astimezone()
    except ValueError:
        return None


def _normalize_key(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return normalized.strip("._") or "unknown"


def _empty_overlay(bot_id: str, user_id: str) -> dict[str, Any]:
    return {
        "bot_id": bot_id,
        "user_id": user_id,
        "version": 1,
        "created_at": "",
        "updated_at": "",
        "overlay": {
            "local_focus": {},
            "active_plan_binding": {},
            "teaching_policy_override": {},
            "heartbeat_override": {},
            "working_memory_projection": "",
            "channel_presence_override": {},
            "local_notebook_scope_refs": [],
            "engagement_state": {},
            "promotion_candidates": [],
        },
    }


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged.get(key) or {}), value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _candidate_id(candidate: dict[str, Any]) -> str:
    raw = str(candidate.get("candidate_id") or "").strip()
    return raw or uuid.uuid4().hex


class BotLearnerOverlayService:
    """Minimal phase-2 overlay service for bot-local learner differences."""

    def __init__(self, path_service: PathService | None = None) -> None:
        self._path_service = path_service or get_path_service()
        self._outbox: LearnerStateOutbox | None = self._build_outbox()

    def _build_outbox(self) -> LearnerStateOutbox | None:
        try:
            return LearnerStateOutbox(path_service=self._path_service)
        except Exception:
            return None

    @property
    def _overlay_root(self) -> Path:
        root = self._path_service.get_learner_state_root() / "bot_overlays"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _path(self, bot_id: str, user_id: str) -> Path:
        return self._overlay_root / f"{_normalize_key(user_id)}__{_normalize_key(bot_id)}.json"

    def _events_path(self, bot_id: str, user_id: str) -> Path:
        return self._overlay_root / f"{_normalize_key(user_id)}__{_normalize_key(bot_id)}.events.jsonl"

    def _read_events_raw(
        self,
        bot_id: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        path = self._events_path(bot_id, user_id)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    if isinstance(payload, dict):
                        events.append(dict(payload))
        except Exception:
            return []
        return events

    def _read_raw(self, bot_id: str, user_id: str) -> dict[str, Any]:
        path = self._path(bot_id, user_id)
        if not path.exists():
            return _empty_overlay(bot_id, user_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return _empty_overlay(bot_id, user_id)
        base = _empty_overlay(bot_id, user_id)
        base["version"] = int(payload.get("version", 1) or 1)
        base["created_at"] = str(payload.get("created_at", "") or "")
        base["updated_at"] = str(payload.get("updated_at", "") or "")
        overlay = dict(payload.get("overlay") or {})
        for field in _ALLOWED_FIELDS:
            if field in overlay:
                base["overlay"][field] = self._normalize_field_value(field, overlay[field])
        return base

    def _write_raw(self, payload: dict[str, Any]) -> None:
        path = self._path(str(payload["bot_id"]), str(payload["user_id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_event(
        self,
        bot_id: str,
        user_id: str,
        *,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        path = self._events_path(bot_id, user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "event_id": uuid.uuid4().hex,
            "event_type": str(event_type or "").strip() or "overlay_event",
            "bot_id": bot_id,
            "user_id": user_id,
            "created_at": _iso_now(),
            **dict(payload or {}),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _enqueue_outbox_sync(
        self,
        bot_id: str,
        user_id: str,
        *,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        if self._outbox is None:
            return
        dedupe_key = (
            f"overlay-sync:{event_type}:{_normalize_key(user_id)}:{_normalize_key(bot_id)}:"
            f"{payload.get('overlay_version') or payload.get('created_at') or uuid.uuid4().hex}"
        )
        self._outbox.enqueue(
            user_id=user_id,
            event_type=event_type,
            payload_json={
                "bot_id": bot_id,
                "user_id": user_id,
                **dict(payload or {}),
            },
            dedupe_key=dedupe_key,
        )

    def _normalize_field_value(self, field: str, value: Any) -> Any:
        if field in _DICT_FIELDS:
            return dict(value or {}) if isinstance(value, dict) else {}
        if field in _LIST_FIELDS:
            if not isinstance(value, list):
                return []
            normalized: list[Any] = []
            for item in value:
                if isinstance(item, dict):
                    normalized.append(dict(item))
                elif isinstance(item, str):
                    text = item.strip()
                    if text:
                        normalized.append(text)
            return normalized
        if field in _TEXT_FIELDS:
            return str(value or "").strip()
        return deepcopy(value)

    def _validate_field(self, field: str) -> None:
        if field in _FORBIDDEN_FIELDS:
            raise ValueError(f"overlay field is forbidden: {field}")
        if field not in _ALLOWED_FIELDS:
            raise ValueError(f"overlay field is not allowed: {field}")

    def _filtered_overlay(
        self,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
        max_age_hours: int = _DEFAULT_OVERLAY_MAX_AGE_HOURS,
    ) -> tuple[dict[str, Any], list[str]]:
        overlay = deepcopy(dict(payload.get("overlay") or {}))
        updated_at = _coerce_datetime(payload.get("updated_at"))
        reference = now or datetime.now().astimezone()
        if updated_at is None:
            return overlay, []
        cutoff = updated_at + timedelta(hours=max(1, int(max_age_hours or _DEFAULT_OVERLAY_MAX_AGE_HOURS)))
        if reference <= cutoff:
            return overlay, []
        expired_fields: list[str] = []
        for field in _EPHEMERAL_FIELDS:
            normalized_empty = self._normalize_field_value(field, None)
            if overlay.get(field) not in ({}, [], "", None):
                overlay[field] = normalized_empty
                expired_fields.append(field)
        return overlay, expired_fields

    def read_overlay(self, bot_id: str, user_id: str) -> dict[str, Any]:
        payload = self._read_raw(bot_id, user_id)
        effective_overlay, expired_fields = self._filtered_overlay(payload)
        return {
            "bot_id": bot_id,
            "user_id": user_id,
            "exists": bool(payload.get("created_at")),
            "version": int(payload.get("version", 1) or 1),
            "effective_overlay": effective_overlay,
            "suppressed_fields": [],
            "expired_fields": expired_fields,
            "promotion_candidates": list(effective_overlay.get("promotion_candidates") or []),
            "heartbeat_override_candidate": dict(effective_overlay.get("heartbeat_override") or {}),
        }

    def list_overlay_events(
        self,
        bot_id: str,
        user_id: str,
        *,
        limit: int | None = 20,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        events = self._read_events_raw(bot_id, user_id)
        normalized_type = str(event_type or "").strip()
        if normalized_type:
            events = [
                item for item in events
                if str(item.get("event_type") or "").strip() == normalized_type
            ]
        if limit is None or limit < 0:
            return events
        return events[-int(limit):]

    def list_overlay_audit(
        self,
        bot_id: str,
        user_id: str,
        *,
        limit: int | None = 20,
    ) -> list[dict[str, Any]]:
        audit_event_types = {
            "overlay_patch",
            "overlay_promotion_queue_update",
            "overlay_promotion_apply",
            "overlay_decay",
        }
        events = [
            item
            for item in self._read_events_raw(bot_id, user_id)
            if str(item.get("event_type") or "").strip() in audit_event_types
        ]
        if limit is None or limit < 0:
            return events
        return events[-int(limit):]

    def list_user_overlays(
        self,
        user_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        normalized_user = _normalize_key(user_id)
        items: list[dict[str, Any]] = []
        for path in self._overlay_root.glob(f"{normalized_user}__*.json"):
            if path.name.endswith(".events.jsonl"):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            bot_id = str(raw.get("bot_id") or "").strip()
            if not bot_id:
                stem = str(path.stem or "")
                if "__" in stem:
                    bot_id = stem.split("__", 1)[1]
            if not bot_id:
                continue
            overlay = self.read_overlay(bot_id, user_id)
            overlay["created_at"] = str(raw.get("created_at") or "")
            overlay["updated_at"] = str(raw.get("updated_at") or "")
            overlay["event_count"] = len(self._read_events_raw(bot_id, user_id))
            items.append(overlay)
        items.sort(
            key=lambda item: (
                str(item.get("updated_at") or ""),
                str(item.get("created_at") or ""),
                str(item.get("bot_id") or ""),
            ),
            reverse=True,
        )
        if limit is None or limit < 0:
            return items
        return items[: int(limit)]

    def patch_overlay(
        self,
        bot_id: str,
        user_id: str,
        patch: dict[str, Any],
        *,
        source_feature: str,
        source_id: str,
    ) -> dict[str, Any]:
        payload = self._read_raw(bot_id, user_id)
        operations = list(patch.get("operations") or [])
        if not operations:
            operations = [patch]
        now = _iso_now()
        if not payload["created_at"]:
            payload["created_at"] = now
        payload["updated_at"] = now
        payload["version"] = int(payload.get("version", 1) or 1) + 1

        for operation in operations:
            op = str(operation.get("op", "") or "").strip()
            field = str(operation.get("field", "") or "").strip()
            self._validate_field(field)
            if op == "set":
                payload["overlay"][field] = self._normalize_field_value(field, operation.get("value"))
            elif op == "merge":
                if field not in _DICT_FIELDS:
                    raise ValueError(f"merge is only supported for dict fields: {field}")
                payload["overlay"][field] = _deep_merge(
                    dict(payload["overlay"].get(field) or {}),
                    dict(operation.get("value") or {}),
                )
            elif op == "clear":
                payload["overlay"][field] = self._normalize_field_value(field, None)
            elif op == "append_candidate":
                if field != "promotion_candidates":
                    raise ValueError("append_candidate is only supported for promotion_candidates")
                candidate = dict(operation.get("value") or {})
                candidate["candidate_id"] = _candidate_id(candidate)
                candidate.setdefault("source_feature", source_feature)
                candidate.setdefault("source_id", source_id)
                candidate.setdefault("created_at", now)
                payload["overlay"][field] = list(payload["overlay"].get(field) or []) + [candidate]
            else:
                raise ValueError(f"unsupported overlay patch operation: {op}")

        self._write_raw(payload)
        outbox_payload = {
            "overlay_version": int(payload.get("version", 1) or 1),
            "overlay_write_type": "patch",
            "overlay_write_reason": source_feature,
            "source_feature": source_feature,
            "source_id": source_id,
            "overlay_fields": [
                str(dict(item).get("field") or "").strip()
                for item in operations
                if str(dict(item).get("field") or "").strip()
            ],
            "promotion_candidate_count": len(list(payload["overlay"].get("promotion_candidates") or [])),
            "overlay_snapshot": deepcopy(payload["overlay"]),
            "created_at": now,
        }
        self._append_event(
            bot_id,
            user_id,
            event_type="overlay_patch",
            payload=outbox_payload,
        )
        self._enqueue_outbox_sync(
            bot_id,
            user_id,
            event_type="overlay_patch",
            payload=outbox_payload,
        )
        return self.read_overlay(bot_id, user_id)

    def build_context_fragment(
        self,
        bot_id: str,
        user_id: str,
        *,
        language: str = "zh",
        max_chars: int = 2000,
    ) -> str:
        overlay = self.read_overlay(bot_id, user_id)["effective_overlay"]
        sections: list[str] = []
        if overlay.get("local_focus"):
            sections.append(f"### Local Focus\n{json.dumps(overlay['local_focus'], ensure_ascii=False, indent=2)}")
        if overlay.get("active_plan_binding"):
            sections.append(
                f"### Active Plan Binding\n{json.dumps(overlay['active_plan_binding'], ensure_ascii=False, indent=2)}"
            )
        if overlay.get("teaching_policy_override"):
            sections.append(
                "### Teaching Policy Override\n"
                f"{json.dumps(overlay['teaching_policy_override'], ensure_ascii=False, indent=2)}"
            )
        if overlay.get("heartbeat_override"):
            sections.append(
                f"### Heartbeat Override\n{json.dumps(overlay['heartbeat_override'], ensure_ascii=False, indent=2)}"
            )
        if overlay.get("working_memory_projection"):
            sections.append(f"### Working Memory Projection\n{overlay['working_memory_projection']}")
        if overlay.get("local_notebook_scope_refs"):
            sections.append(
                f"### Local Notebook Scope\n{json.dumps(overlay['local_notebook_scope_refs'], ensure_ascii=False, indent=2)}"
            )
        if overlay.get("engagement_state"):
            sections.append(
                f"### Engagement State\n{json.dumps(overlay['engagement_state'], ensure_ascii=False, indent=2)}"
            )
        if not sections:
            return ""
        header = (
            "## Bot-Learner Overlay\n以下内容只表示当前 Bot 对当前学员的局部差异，不得覆盖全局 learner truth。"
            if str(language).lower().startswith("zh")
            else "## Bot-Learner Overlay\nThis fragment contains bot-local learner differences only."
        )
        fragment = header + "\n\n" + "\n\n".join(sections)
        if len(fragment) > max_chars:
            fragment = fragment[:max_chars].rstrip() + "\n...[truncated]"
        return fragment

    def promote_candidate(
        self,
        bot_id: str,
        user_id: str,
        candidate_kind: str,
        payload: dict[str, Any],
        *,
        source_feature: str,
        source_id: str,
    ) -> dict[str, Any]:
        return self.patch_overlay(
            bot_id,
            user_id,
            {
                "op": "append_candidate",
                "field": "promotion_candidates",
                "value": {
                    "candidate_kind": str(candidate_kind or "").strip(),
                    "payload": dict(payload or {}),
                },
            },
            source_feature=source_feature,
            source_id=source_id,
        )

    def collect_promotion_candidates(
        self,
        bot_id: str,
        user_id: str,
        *,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        overlay = self.read_overlay(bot_id, user_id)
        candidates = list(overlay.get("promotion_candidates") or [])
        threshold = float(min_confidence or 0.0)
        eligible: list[dict[str, Any]] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            try:
                confidence = float(item.get("confidence", 1.0))
            except Exception:
                confidence = 1.0
            if confidence < threshold:
                continue
            eligible.append(dict(item))
        return eligible

    def _rewrite_candidates(
        self,
        bot_id: str,
        user_id: str,
        *,
        candidate_ids: list[str] | tuple[str, ...],
        action: str,
        reason: str = "",
    ) -> dict[str, Any]:
        payload = self._read_raw(bot_id, user_id)
        existing = list(payload["overlay"].get("promotion_candidates") or [])
        wanted = {str(item or "").strip() for item in candidate_ids if str(item or "").strip()}
        kept: list[dict[str, Any]] = []
        affected: list[dict[str, Any]] = []
        for item in existing:
            candidate = dict(item) if isinstance(item, dict) else {}
            if str(candidate.get("candidate_id") or "").strip() in wanted:
                candidate["promotion_action"] = action
                if reason:
                    candidate["promotion_reason"] = reason
                affected.append(candidate)
                continue
            kept.append(candidate)
        payload["overlay"]["promotion_candidates"] = kept
        if affected:
            payload["updated_at"] = _iso_now()
            payload["version"] = int(payload.get("version", 1) or 1) + 1
            self._write_raw(payload)
            outbox_payload = {
                "overlay_version": int(payload.get("version", 1) or 1),
                "overlay_write_type": action,
                "overlay_write_reason": reason,
                "affected_candidate_ids": list(wanted),
                "affected_count": len(affected),
                "overlay_snapshot": deepcopy(payload["overlay"]),
                "created_at": payload["updated_at"],
            }
            self._append_event(
                bot_id,
                user_id,
                event_type="overlay_promotion_queue_update",
                payload=outbox_payload,
            )
            self._enqueue_outbox_sync(
                bot_id,
                user_id,
                event_type="overlay_promotion_queue_update",
                payload=outbox_payload,
            )
        result = self.read_overlay(bot_id, user_id)
        result["affected_candidates"] = affected
        result["affected_count"] = len(affected)
        return result

    def ack_promotions(
        self,
        bot_id: str,
        user_id: str,
        candidate_ids: list[str] | tuple[str, ...],
        *,
        reason: str = "",
    ) -> dict[str, Any]:
        return self._rewrite_candidates(
            bot_id,
            user_id,
            candidate_ids=candidate_ids,
            action="ack",
            reason=reason,
        )

    def drop_promotions(
        self,
        bot_id: str,
        user_id: str,
        candidate_ids: list[str] | tuple[str, ...],
        *,
        reason: str = "",
    ) -> dict[str, Any]:
        return self._rewrite_candidates(
            bot_id,
            user_id,
            candidate_ids=candidate_ids,
            action="drop",
            reason=reason,
        )

    def resolve_heartbeat_inputs(self, bot_id: str, user_id: str) -> dict[str, Any]:
        overlay = self.read_overlay(bot_id, user_id)
        effective_overlay = dict(overlay.get("effective_overlay") or {})
        heartbeat_override = dict(effective_overlay.get("heartbeat_override") or {})
        return {
            "bot_id": bot_id,
            "user_id": user_id,
            "heartbeat_override_candidate": heartbeat_override,
            "heartbeat_override_present": bool(heartbeat_override),
            "local_focus": dict(effective_overlay.get("local_focus") or {}),
            "active_plan_binding": dict(effective_overlay.get("active_plan_binding") or {}),
            "engagement_state": dict(effective_overlay.get("engagement_state") or {}),
            "expired_fields": list(overlay.get("expired_fields") or []),
            "overlay_version": int(overlay.get("version", 1) or 1),
        }

    def apply_promotions(
        self,
        bot_id: str,
        user_id: str,
        *,
        learner_state_service: Any,
        min_confidence: float = 0.7,
        max_candidates: int = 10,
    ) -> dict[str, Any]:
        eligible = self.collect_promotion_candidates(
            bot_id,
            user_id,
            min_confidence=min_confidence,
        )[: max(0, int(max_candidates or 10))]
        if not eligible:
            return {
                "applied": [],
                "dropped": [],
                "acked_ids": [],
                "dropped_ids": [],
            }

        ack_ids: list[str] = []
        drop_ids: list[str] = []
        applied: list[dict[str, Any]] = []
        dropped: list[dict[str, Any]] = []

        for candidate in eligible:
            candidate_id = str(candidate.get("candidate_id") or "").strip()
            candidate_kind = str(candidate.get("candidate_kind") or "").strip()
            payload = dict(candidate.get("payload") or {})
            source_feature = str(candidate.get("source_feature") or "overlay").strip() or "overlay"
            source_id = str(candidate.get("source_id") or candidate_id or "overlay-candidate").strip()
            applied_kind = ""

            if candidate_kind in {"stable_goal_signal", "explicit_goal"}:
                goal_title = str(
                    payload.get("title")
                    or payload.get("goal")
                    or payload.get("topic")
                    or ""
                ).strip()
                if goal_title and hasattr(learner_state_service, "upsert_goal"):
                    goal_payload = {
                        "goal_type": str(payload.get("goal_type") or "study").strip() or "study",
                        "title": goal_title,
                        "progress": payload.get("progress", 0),
                        "deadline": payload.get("deadline"),
                        "source_bot_id": bot_id,
                    }
                    learner_state_service.upsert_goal(user_id, goal_payload)
                    applied_kind = "goal"

            elif candidate_kind in {"stable_preference", "explicit_preference"}:
                preference_patch = {
                    key: value
                    for key, value in payload.items()
                    if key in {"difficulty_preference", "explanation_style", "focus_topic", "focus_query"}
                    and value not in {"", None}
                }
                if preference_patch and hasattr(learner_state_service, "merge_profile"):
                    learner_state_service.merge_profile(user_id, preference_patch)
                    applied_kind = "profile"

            elif candidate_kind in {"possible_weak_point", "weak_point_signal"}:
                weak_point = str(
                    payload.get("topic")
                    or payload.get("weak_point")
                    or payload.get("title")
                    or ""
                ).strip()
                if weak_point and hasattr(learner_state_service, "merge_progress"):
                    current_progress = {}
                    if hasattr(learner_state_service, "read_progress"):
                        current_progress = dict(learner_state_service.read_progress(user_id) or {})
                    knowledge_map = dict(current_progress.get("knowledge_map") or {})
                    existing = [
                        str(item).strip()
                        for item in list(knowledge_map.get("weak_points") or [])
                        if str(item).strip()
                    ]
                    if weak_point not in existing:
                        existing.append(weak_point)
                    learner_state_service.merge_progress(
                        user_id,
                        {
                            "knowledge_map": {
                                **knowledge_map,
                                "weak_points": existing[:8],
                            }
                        },
                    )
                    applied_kind = "progress"

            if applied_kind:
                if hasattr(learner_state_service, "append_memory_event"):
                    learner_state_service.append_memory_event(
                        user_id,
                        source_feature=source_feature,
                        source_id=source_id,
                        source_bot_id=bot_id,
                        memory_kind="overlay_promotion",
                        payload_json={
                            "candidate_id": candidate_id,
                            "candidate_kind": candidate_kind,
                            "applied_kind": applied_kind,
                            "payload": payload,
                            "bot_id": bot_id,
                        },
                    )
                ack_ids.append(candidate_id)
                applied.append(
                    {
                        "candidate_id": candidate_id,
                        "candidate_kind": candidate_kind,
                        "applied_kind": applied_kind,
                    }
                )
            else:
                drop_ids.append(candidate_id)
                dropped.append(
                    {
                        "candidate_id": candidate_id,
                        "candidate_kind": candidate_kind,
                    }
                )

        if ack_ids:
            self.ack_promotions(
                bot_id,
                user_id,
                ack_ids,
                reason="promoted_to_global_core",
            )
        if drop_ids:
            self.drop_promotions(
                bot_id,
                user_id,
                drop_ids,
                reason="not_promotion_eligible",
            )
        outbox_payload = {
            "overlay_write_type": "promotion_apply",
            "promotion_applied": len(applied),
            "promotion_dropped": len(dropped),
            "acked_ids": ack_ids,
            "dropped_ids": drop_ids,
            "created_at": _iso_now(),
        }
        self._append_event(
            bot_id,
            user_id,
            event_type="overlay_promotion_apply",
            payload=outbox_payload,
        )
        self._enqueue_outbox_sync(
            bot_id,
            user_id,
            event_type="overlay_promotion_apply",
            payload=outbox_payload,
        )
        return {
            "applied": applied,
            "dropped": dropped,
            "acked_ids": ack_ids,
            "dropped_ids": drop_ids,
        }

    def decay_overlay(
        self,
        bot_id: str,
        user_id: str,
        *,
        now: datetime | str | None = None,
        max_age_hours: int = _DEFAULT_OVERLAY_MAX_AGE_HOURS,
    ) -> dict[str, Any]:
        payload = self._read_raw(bot_id, user_id)
        reference = _coerce_datetime(now) or datetime.now().astimezone()
        filtered_overlay, expired_fields = self._filtered_overlay(
            payload,
            now=reference,
            max_age_hours=max_age_hours,
        )
        if expired_fields:
            payload["overlay"] = filtered_overlay
            payload["updated_at"] = reference.isoformat()
            payload["version"] = int(payload.get("version", 1) or 1) + 1
            self._write_raw(payload)
            outbox_payload = {
                "overlay_version": int(payload.get("version", 1) or 1),
                "overlay_decay_applied": True,
                "expired_fields": expired_fields,
                "overlay_snapshot": deepcopy(payload["overlay"]),
                "created_at": payload["updated_at"],
            }
            self._append_event(
                bot_id,
                user_id,
                event_type="overlay_decay",
                payload=outbox_payload,
            )
            self._enqueue_outbox_sync(
                bot_id,
                user_id,
                event_type="overlay_decay",
                payload=outbox_payload,
            )
        result = self.read_overlay(bot_id, user_id)
        result["overlay_decay_applied"] = bool(expired_fields)
        result["expired_fields"] = expired_fields
        return result


_bot_learner_overlay_service: BotLearnerOverlayService | None = None


def get_bot_learner_overlay_service() -> BotLearnerOverlayService:
    global _bot_learner_overlay_service
    if _bot_learner_overlay_service is None:
        _bot_learner_overlay_service = BotLearnerOverlayService()
    return _bot_learner_overlay_service


__all__ = [
    "BotLearnerOverlayService",
    "get_bot_learner_overlay_service",
]
