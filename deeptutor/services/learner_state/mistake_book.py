from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol

import httpx

from deeptutor.services.learner_state.attempt_refs import verify_attempt_ref
from deeptutor.services.learner_state.revalidation_queue import derive_review_due_at
from deeptutor.services.path_service import get_path_service
from deeptutor.services.runtime_env import env_flag, is_production_environment

_TZ = timezone(timedelta(hours=8))
_MISTAKE_BOOK_ENABLED = "DEEPTUTOR_MISTAKE_BOOK_ENABLED"
_MISTAKE_BOOK_WRITE_ENABLED = "DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED"
_MISTAKE_BOOK_LOCAL_FALLBACK = "DEEPTUTOR_MISTAKE_BOOK_LOCAL_FALLBACK"
# 复习模块灰度旗标(register-before-use): 开 = 列表读侧把 review_due_at 从
# revalidation_queue 的派生函数投影出来(零写入); 关 = 维持收权后现状(恒 None)。
_REVIEW_MODULE_FLAG = "LUBAN_REVIEW_MODULE_ENABLED"
_LOCAL_FALLBACK_FILENAME = "MISTAKE_BOOK.json"


class MistakeBookConflict(Exception):
    def __init__(self, latest: dict[str, Any]) -> None:
        super().__init__("mistake_book_etag_conflict")
        self.latest = dict(latest or {})


class MistakeBookStore(Protocol):
    def upsert_item(self, row: dict[str, Any]) -> dict[str, Any]: ...

    def get_item(self, user_id: str, event_id: str) -> dict[str, Any] | None: ...

    def update_item(self, user_id: str, event_id: str, patch: dict[str, Any]) -> dict[str, Any] | None: ...

    def list_items(
        self,
        user_id: str,
        *,
        subject_id: str = "",
        include_mastered: bool = False,
    ) -> list[dict[str, Any]]: ...


class InMemoryMistakeBookStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}

    def upsert_item(self, row: dict[str, Any]) -> dict[str, Any]:
        key = (str(row.get("user_id") or ""), str(row.get("event_id") or ""))
        current = dict(self._rows.get(key) or {})
        current.update(dict(row or {}))
        self._rows[key] = current
        return dict(current)

    def get_item(self, user_id: str, event_id: str) -> dict[str, Any] | None:
        row = self._rows.get((str(user_id or ""), str(event_id or "")))
        return dict(row) if row is not None else None

    def update_item(self, user_id: str, event_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        key = (str(user_id or ""), str(event_id or ""))
        current = self._rows.get(key)
        if current is None:
            return None
        current = {**current, **dict(patch or {})}
        self._rows[key] = current
        return dict(current)

    def list_items(
        self,
        user_id: str,
        *,
        subject_id: str = "",
        include_mastered: bool = False,
    ) -> list[dict[str, Any]]:
        normalized = str(user_id or "")
        normalized_subject = str(subject_id or "").strip()
        rows = []
        for (row_user, _), row in self._rows.items():
            if row_user != normalized:
                continue
            if row.get("archived_at"):
                continue
            if normalized_subject and str(row.get("subject_id") or "") != normalized_subject:
                continue
            if not include_mastered and row.get("mastered_at"):
                continue
            rows.append(dict(row))
        return sorted(rows, key=lambda row: str(row.get("saved_at") or ""), reverse=True)


class LocalFileMistakeBookStore:
    def __init__(self) -> None:
        self._path_service = get_path_service()

    def upsert_item(self, row: dict[str, Any]) -> dict[str, Any]:
        user_id = str(row.get("user_id") or "")
        event_id = str(row.get("event_id") or "")
        rows = self._read_rows(user_id)
        replaced = False
        for index, current in enumerate(rows):
            if str(current.get("event_id") or "") != event_id:
                continue
            rows[index] = {**current, **dict(row or {})}
            replaced = True
            break
        if not replaced:
            rows.append(dict(row or {}))
        self._write_rows(user_id, rows)
        return self.get_item(user_id, event_id) or dict(row or {})

    def get_item(self, user_id: str, event_id: str) -> dict[str, Any] | None:
        for row in self._read_rows(user_id):
            if str(row.get("event_id") or "") == str(event_id or ""):
                return dict(row)
        return None

    def update_item(self, user_id: str, event_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        rows = self._read_rows(user_id)
        for index, current in enumerate(rows):
            if str(current.get("event_id") or "") != str(event_id or ""):
                continue
            rows[index] = {**current, **dict(patch or {})}
            self._write_rows(user_id, rows)
            return dict(rows[index])
        return None

    def list_items(
        self,
        user_id: str,
        *,
        subject_id: str = "",
        include_mastered: bool = False,
    ) -> list[dict[str, Any]]:
        normalized_subject = str(subject_id or "").strip()
        rows = []
        for row in self._read_rows(user_id):
            if row.get("archived_at"):
                continue
            if normalized_subject and str(row.get("subject_id") or "") != normalized_subject:
                continue
            if not include_mastered and row.get("mastered_at"):
                continue
            rows.append(dict(row))
        return sorted(rows, key=lambda row: str(row.get("saved_at") or ""), reverse=True)

    def _user_dir(self, user_id: str) -> Path:
        return self._path_service.get_learner_state_root() / str(user_id or "").strip()

    def _path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / _LOCAL_FALLBACK_FILENAME

    def _read_rows(self, user_id: str) -> list[dict[str, Any]]:
        path = self._path(user_id)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        return [dict(item) for item in payload if isinstance(item, dict)]

    def _write_rows(self, user_id: str, rows: list[dict[str, Any]]) -> None:
        path = self._path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(f"{path.suffix}.tmp")
        temp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)


class UnavailableMistakeBookStore:
    def upsert_item(self, row: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("mistake_book_store_unavailable")

    def get_item(self, user_id: str, event_id: str) -> dict[str, Any] | None:
        raise RuntimeError("mistake_book_store_unavailable")

    def update_item(self, user_id: str, event_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        raise RuntimeError("mistake_book_store_unavailable")

    def list_items(
        self,
        user_id: str,
        *,
        subject_id: str = "",
        include_mastered: bool = False,
    ) -> list[dict[str, Any]]:
        raise RuntimeError("mistake_book_store_unavailable")


class SupabaseMistakeBookStore:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        client: httpx.Client | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._base_url = str(base_url or os.getenv("SUPABASE_URL", "") or "").strip().rstrip("/")
        self._service_key = str(
            service_key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
            or os.getenv("SUPABASE_KEY", "")
            or ""
        ).strip()
        self._client = client
        self._timeout_s = float(timeout_s)

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._service_key)

    def upsert_item(self, row: dict[str, Any]) -> dict[str, Any]:
        self._ensure_configured()
        response = self._client_or_create().post(
            f"{self._base_url}/rest/v1/learner_mistake_book_items",
            headers=self._headers(prefer="resolution=merge-duplicates,return=representation"),
            params={"on_conflict": "user_id,event_id"},
            json=[row],
        )
        response.raise_for_status()
        payload = response.json()
        return dict(payload[0]) if isinstance(payload, list) and payload else dict(row)

    def get_item(self, user_id: str, event_id: str) -> dict[str, Any] | None:
        self._ensure_configured()
        rows = self._select({"user_id": f"eq.{user_id}", "event_id": f"eq.{event_id}"}, limit=1)
        return rows[0] if rows else None

    def update_item(self, user_id: str, event_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        self._ensure_configured()
        response = self._client_or_create().patch(
            f"{self._base_url}/rest/v1/learner_mistake_book_items",
            headers=self._headers(prefer="return=representation"),
            params={"user_id": f"eq.{user_id}", "event_id": f"eq.{event_id}"},
            json=dict(patch or {}),
        )
        response.raise_for_status()
        payload = response.json()
        return dict(payload[0]) if isinstance(payload, list) and payload else None

    def list_items(
        self,
        user_id: str,
        *,
        subject_id: str = "",
        include_mastered: bool = False,
    ) -> list[dict[str, Any]]:
        self._ensure_configured()
        filters = {"user_id": f"eq.{user_id}", "archived_at": "is.null"}
        normalized_subject = str(subject_id or "").strip()
        if normalized_subject:
            filters["subject_id"] = f"eq.{normalized_subject}"
        if not include_mastered:
            filters["mastered_at"] = "is.null"
        return self._select(filters, order="saved_at.desc")

    def _select(self, filters: dict[str, str], *, limit: int | None = None, order: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": "*", **dict(filters or {})}
        if limit is not None:
            params["limit"] = int(limit)
        if order:
            params["order"] = order
        response = self._client_or_create().get(
            f"{self._base_url}/rest/v1/learner_mistake_book_items",
            headers=self._headers(),
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
        return [dict(item) for item in payload if isinstance(item, dict)]

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self._service_key,
            "Authorization": f"Bearer {self._service_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _ensure_configured(self) -> None:
        if not self.is_configured:
            raise RuntimeError("mistake_book_store_unavailable")

    def _client_or_create(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_s)
        return self._client


class MistakeBookService:
    def __init__(self, *, store: MistakeBookStore | None = None) -> None:
        if store is not None:
            self._store = store
        else:
            supabase_store = SupabaseMistakeBookStore()
            if _local_fallback_enabled():
                self._store = LocalFileMistakeBookStore()
            elif supabase_store.is_configured:
                self._store = supabase_store
            else:
                self._store = UnavailableMistakeBookStore()

    def save_item(
        self,
        *,
        user_id: str,
        attempt_ref: str,
        subject_id: str,
        bot_id: str = "",
        title: str = "",
        concept_label: str = "",
        error_label: str = "",
        note: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        _require_write_enabled()
        normalized_user = _require_text(user_id, "user_id")
        normalized_subject = _require_text(subject_id, "subject_id")
        ref = _verify_ref(attempt_ref, user_id=normalized_user)
        now = _now()
        row = {
            "user_id": normalized_user,
            "subject_id": normalized_subject,
            "bot_id": str(bot_id or "").strip(),
            "event_id": ref["event_id"],
            "question_id": ref.get("question_id", ""),
            "attempt_ref": str(attempt_ref or ""),
            "title": str(title or "").strip(),
            "concept_label": str(concept_label or "").strip(),
            "error_label": str(error_label or "").strip(),
            "saved_at": now,
            "archived_at": None,
            "mastered_at": None,
            "last_reviewed_at": None,
            "review_due_at": None,
            "note": str(note or "").strip(),
            "tags": list(tags or []),
            "created_at": now,
            "updated_at": now,
        }
        current = self._store.get_item(normalized_user, ref["event_id"])
        if current:
            row["created_at"] = current.get("created_at") or now
        saved = self._store.upsert_item(row)
        return _public_item(saved)

    def remove_item(self, *, user_id: str, attempt_ref: str, if_match: str | None = None) -> dict[str, Any]:
        _require_write_enabled()
        normalized_user = _require_text(user_id, "user_id")
        ref = _verify_ref(attempt_ref, user_id=normalized_user)
        current = self._require_current(normalized_user, ref["event_id"], if_match=if_match)
        updated = self._store.update_item(
            normalized_user,
            ref["event_id"],
            {"archived_at": _now(), "updated_at": _now()},
        ) or current
        item = _public_item(updated)
        item["is_bookmarked"] = False
        return item

    def mark_mastered(self, *, user_id: str, attempt_ref: str, if_match: str | None = None) -> dict[str, Any]:
        """写呈现层的用户隐藏旗标(mastered_at), 不是学情掌握真值。

        掌握结论只能由客观复测证据经 learner truth 链路派生(M0 reality-lock);
        本旗标仅用于错题列表的默认过滤/徽章展示, 禁止回流任何学情推断。
        """
        _require_write_enabled()
        normalized_user = _require_text(user_id, "user_id")
        ref = _verify_ref(attempt_ref, user_id=normalized_user)
        self._require_current(normalized_user, ref["event_id"], if_match=if_match)
        updated = self._store.update_item(
            normalized_user,
            ref["event_id"],
            {"mastered_at": _now(), "updated_at": _now()},
        )
        return _public_item(updated or {})

    def record_review(self, *, user_id: str, attempt_ref: str, if_match: str | None = None) -> dict[str, Any]:
        """记录一次复习观测(last_reviewed_at), 不产生任何调度结论。

        到期/复习调度真值唯一归 revalidation_queue 投影(双轮设计 v3 §10-①);
        本方法显式清空 review_due_at——既不新增伪日期, 也顺带清掉收权前
        存量行里的历史硬编码日期(原实现固定 now+3d, 属第二调度权威)。
        """
        _require_write_enabled()
        normalized_user = _require_text(user_id, "user_id")
        ref = _verify_ref(attempt_ref, user_id=normalized_user)
        self._require_current(normalized_user, ref["event_id"], if_match=if_match)
        reviewed_at = _now()
        updated = self._store.update_item(
            normalized_user,
            ref["event_id"],
            {"last_reviewed_at": reviewed_at, "review_due_at": None, "updated_at": reviewed_at},
        )
        return _public_item(updated or {})

    def list_items(
        self,
        *,
        user_id: str,
        subject_id: str = "",
        include_mastered: bool = False,
        exam_date_iso: str = "",
    ) -> dict[str, Any]:
        _require_read_enabled()
        normalized_user = _require_text(user_id, "user_id")
        normalized_subject = str(subject_id or "").strip()
        rows = [
            _public_item(row)
            for row in self._store.list_items(
                normalized_user,
                subject_id=normalized_subject,
                include_mastered=include_mastered,
            )
        ]
        if _flag_enabled(_REVIEW_MODULE_FLAG):
            rows = [_with_projected_review_due(row, exam_date_iso=exam_date_iso) for row in rows]
        generated_at = _now()
        return {
            "ok": True,
            "generated_at": generated_at,
            "etag": _collection_etag(rows),
            "count": len(rows),
            "items": rows,
        }

    def bookmark_event_ids(self, *, user_id: str, include_mastered: bool = True) -> set[str]:
        try:
            result = self.list_items(user_id=user_id, include_mastered=include_mastered)
        except Exception:
            return set()
        return {str(item.get("event_id") or "") for item in result.get("items", []) if item.get("is_bookmarked")}

    def _require_current(self, user_id: str, event_id: str, *, if_match: str | None) -> dict[str, Any]:
        current = self._store.get_item(user_id, event_id)
        if not current:
            raise ValueError("mistake_book_item_not_found")
        latest = _public_item(current)
        if if_match and str(if_match).strip() != latest["etag"]:
            raise MistakeBookConflict(latest)
        return current


def _verify_ref(attempt_ref: str, *, user_id: str) -> dict[str, str]:
    ref = verify_attempt_ref(attempt_ref, user_id=user_id)
    if ref is None:
        raise ValueError("invalid_attempt_ref")
    return {"event_id": ref["event_id"], "question_id": ref.get("question_id", "")}


def _flag_enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _local_fallback_enabled() -> bool:
    return not is_production_environment() and env_flag(_MISTAKE_BOOK_LOCAL_FALLBACK, default=False)


def _require_read_enabled() -> None:
    if not _flag_enabled(_MISTAKE_BOOK_ENABLED):
        raise RuntimeError("mistake_book_disabled")


def _require_write_enabled() -> None:
    if not _flag_enabled(_MISTAKE_BOOK_WRITE_ENABLED):
        raise RuntimeError("mistake_book_write_disabled")


def _require_text(value: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field}_required")
    return text


def _now() -> str:
    return datetime.now(_TZ).replace(microsecond=0).isoformat()


def _etag(row: dict[str, Any]) -> str:
    raw = "|".join(
        str(row.get(key) or "")
        for key in ("user_id", "event_id", "saved_at", "updated_at", "archived_at", "mastered_at", "last_reviewed_at")
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _collection_etag(rows: list[dict[str, Any]]) -> str:
    raw = "|".join(str(row.get("etag") or "") for row in rows)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _with_projected_review_due(item: dict[str, Any], *, exam_date_iso: str = "") -> dict[str, Any]:
    """读侧投影 review_due_at——间隔真值唯一归 revalidation_queue.derive_review_due_at
    （双轮 v3 §10-①/v3.2 §6.1）。本模块零间隔常量、零落库：错题=lapse 走 weak 相
    （首跳 3 天, 受 cap ≤14 / exam_date 地平线压缩），观测锚 = 最近一次复习，缺则收藏时刻。
    已标掌握（呈现层旗标）不再排期。"""
    result = dict(item or {})
    if result.get("mastered_at") or result.get("archived_at"):
        return result
    observed = str(result.get("last_reviewed_at") or result.get("saved_at") or "").strip()
    due_at = derive_review_due_at(
        last_observed_at=observed, state="weak", exam_date_iso=exam_date_iso
    )
    if due_at:
        result["review_due_at"] = due_at
    return result


def _public_item(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    item["is_bookmarked"] = not bool(item.get("archived_at"))
    item["bookmark_label"] = "已加入错题" if item["is_bookmarked"] else "已移出错题"
    item["generated_at"] = _now()
    item["etag"] = _etag(item)
    return item


__all__ = [
    "InMemoryMistakeBookStore",
    "MistakeBookConflict",
    "MistakeBookService",
    "MistakeBookStore",
    "SupabaseMistakeBookStore",
    "UnavailableMistakeBookStore",
]
