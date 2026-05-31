from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from deeptutor.services.notebook_card.store import NotebookCardStore

_CARD_TYPES = {"scoring_card", "error_pattern_note", "review_note", "manual_note"}


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat()


class NotebookCardService:
    """学习卡片的唯一 authority：写/读/删卡片 + 仅轻量 learner-state 事件回写。
    禁止调用 refresh_from_turn / patch_overlay（写回收权）。"""

    def __init__(self, *, store: NotebookCardStore, learner_state_service: Any) -> None:
        self._store = store
        self._learner = learner_state_service

    async def save_card(self, *, user_id: str, subject_id: str, source_bot_id: str,
                        card_type: str, source_type: str, source_ref: dict[str, Any],
                        evidence_event_ids: list[str], title: str, raw_user_content: str,
                        ai_enhanced_content: dict[str, Any], mastery_effect: str = "none") -> dict[str, Any]:
        norm_user = str(user_id or "").strip()
        if not norm_user:
            raise ValueError("user_id required")
        ct = card_type if card_type in _CARD_TYPES else "manual_note"
        note_id = "note_" + uuid.uuid4().hex[:12]
        now = _iso_now()
        row = {
            "user_id": norm_user, "note_id": note_id, "subject_id": str(subject_id or ""),
            "source_bot_id": str(source_bot_id or ""), "card_type": ct, "source_type": str(source_type or "manual"),
            "source_ref": dict(source_ref or {}), "evidence_event_ids": list(evidence_event_ids or []),
            "title": str(title or ""), "raw_user_content": str(raw_user_content or ""),
            "ai_enhanced_content": dict(ai_enhanced_content or {}),
            "user_control_status": "confirmed", "use_for_personalization": True,
            "mastery_effect": "none",  # 永久固定，忽略调用方
            "version": 1, "created_at": now, "updated_at": now,
        }
        saved = self._store.upsert_card(row)
        await self._emit_light_event(saved, operation="add")
        return saved

    async def update_card(self, *, user_id: str, note_id: str, expected_version: int,
                         patch: dict[str, Any]) -> dict[str, Any]:
        safe_patch = {k: v for k, v in dict(patch or {}).items()
                      if k not in {"user_id", "note_id", "mastery_effect", "version"}}
        safe_patch["updated_at"] = _iso_now()
        updated = self._store.update_card(user_id, note_id, safe_patch, expected_version=expected_version)
        if updated is None:
            raise KeyError(f"card not found: {user_id}/{note_id}")
        return updated

    async def delete_card(self, *, user_id: str, note_id: str, expected_version: int) -> dict[str, Any]:
        return await self.update_card(user_id=user_id, note_id=note_id, expected_version=expected_version,
                                      patch={"archived_at": _iso_now()})

    def list_cards(self, user_id: str, *, subject_id: str = "", card_type: str = "") -> list[dict[str, Any]]:
        return self._store.list_cards(user_id, subject_id=subject_id, card_type=card_type)

    async def _emit_light_event(self, card: dict[str, Any], *, operation: str) -> None:
        # 仅轻路径：append 一条 notebook_* 事件，绝不 refresh_from_turn / patch_overlay。
        await self._learner.record_notebook_writeback(
            user_id=card["user_id"], notebook_id=card["note_id"], record_id=card["note_id"],
            operation=f"card_{operation}", title=card.get("title", ""),
            summary=str(card.get("ai_enhanced_content", {}).get("summary", "")),
            user_query=card.get("raw_user_content", ""), record_type=card.get("card_type", "manual_note"),
            kb_name=None, metadata={"source_label": "student_note", "card_type": card.get("card_type"),
                                    "mastery_effect": "none"},
            source_bot_id=card.get("source_bot_id") or None,
        )


_singleton: NotebookCardService | None = None


def get_notebook_card_service() -> NotebookCardService:
    """进程级单例：生产用 Supabase store（配置齐全时），否则 InMemory（dev/test）。"""
    global _singleton
    if _singleton is None:
        from deeptutor.services.learner_state.service import get_learner_state_service
        from deeptutor.services.notebook_card.store import (
            InMemoryNotebookCardStore,
            SupabaseNotebookCardStore,
        )

        supabase_store = SupabaseNotebookCardStore()
        store = supabase_store if supabase_store.is_configured else InMemoryNotebookCardStore()
        _singleton = NotebookCardService(store=store, learner_state_service=get_learner_state_service())
    return _singleton


__all__ = ["NotebookCardService", "get_notebook_card_service"]
