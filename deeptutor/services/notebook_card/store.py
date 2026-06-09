from __future__ import annotations

import os
from typing import Any, Protocol

import httpx


class OptimisticConcurrencyError(RuntimeError):
    """expected_version 与当前行 version 不一致。"""


class NotebookCardStore(Protocol):
    def upsert_card(self, row: dict[str, Any]) -> dict[str, Any]: ...
    def get_card(self, user_id: str, note_id: str) -> dict[str, Any] | None: ...
    def update_card(self, user_id: str, note_id: str, patch: dict[str, Any], *, expected_version: int) -> dict[str, Any] | None: ...
    def list_cards(self, user_id: str, *, subject_id: str = "", card_type: str = "") -> list[dict[str, Any]]: ...


class InMemoryNotebookCardStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}

    def upsert_card(self, row: dict[str, Any]) -> dict[str, Any]:
        key = (str(row.get("user_id") or ""), str(row.get("note_id") or ""))
        current = dict(self._rows.get(key) or {})
        current.update(dict(row or {}))
        current.setdefault("version", 1)
        self._rows[key] = current
        return dict(current)

    def get_card(self, user_id: str, note_id: str) -> dict[str, Any] | None:
        row = self._rows.get((str(user_id or ""), str(note_id or "")))
        return dict(row) if row is not None else None

    def update_card(self, user_id: str, note_id: str, patch: dict[str, Any], *, expected_version: int) -> dict[str, Any] | None:
        key = (str(user_id or ""), str(note_id or ""))
        current = self._rows.get(key)
        if current is None:
            return None
        if int(current.get("version") or 1) != int(expected_version):
            raise OptimisticConcurrencyError(f"stale version: have {current.get('version')}, expected {expected_version}")
        updated = {**current, **dict(patch or {}), "version": int(current.get("version") or 1) + 1}
        self._rows[key] = updated
        return dict(updated)

    def list_cards(self, user_id: str, *, subject_id: str = "", card_type: str = "") -> list[dict[str, Any]]:
        norm_u, norm_s, norm_c = str(user_id or ""), str(subject_id or "").strip(), str(card_type or "").strip()
        out = []
        for (row_u, _), row in self._rows.items():
            if row_u != norm_u or row.get("archived_at"):
                continue
            if norm_s and str(row.get("subject_id") or "") != norm_s:
                continue
            if norm_c and str(row.get("card_type") or "") != norm_c:
                continue
            out.append(dict(row))
        return sorted(out, key=lambda r: str(r.get("updated_at") or ""), reverse=True)


class UnavailableNotebookCardStore:
    def _fail(self, *_a, **_k):
        raise RuntimeError("notebook_card_store_unavailable")
    upsert_card = get_card = update_card = list_cards = _fail


class SupabaseNotebookCardStore:
    """同步 httpx PostgREST 客户端，乐观并发用 version 过滤 patch（仿 SupabaseMistakeBookStore）。"""

    _TABLE = "learner_notebook_cards"

    def __init__(self, *, base_url: str | None = None, service_key: str | None = None,
                 client: httpx.Client | None = None, timeout_s: float = 10.0) -> None:
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

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_s)
        return self._client

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        h = {"apikey": self._service_key, "Authorization": f"Bearer {self._service_key}", "Content-Type": "application/json"}
        if prefer:
            h["Prefer"] = prefer
        return h

    def upsert_card(self, row: dict[str, Any]) -> dict[str, Any]:
        resp = self._http().post(
            f"{self._base_url}/rest/v1/{self._TABLE}",
            headers=self._headers(prefer="resolution=merge-duplicates,return=representation"),
            params={"on_conflict": "user_id,note_id"}, json=[row])
        resp.raise_for_status()
        payload = resp.json()
        return dict(payload[0]) if isinstance(payload, list) and payload else dict(row)

    def get_card(self, user_id: str, note_id: str) -> dict[str, Any] | None:
        resp = self._http().get(
            f"{self._base_url}/rest/v1/{self._TABLE}",
            headers=self._headers(),
            params={"select": "*", "user_id": f"eq.{user_id}", "note_id": f"eq.{note_id}", "limit": 1})
        resp.raise_for_status()
        payload = resp.json()
        return dict(payload[0]) if isinstance(payload, list) and payload else None

    def update_card(self, user_id: str, note_id: str, patch: dict[str, Any], *, expected_version: int) -> dict[str, Any] | None:
        body = {**dict(patch or {}), "version": int(expected_version) + 1}
        resp = self._http().patch(
            f"{self._base_url}/rest/v1/{self._TABLE}",
            headers=self._headers(prefer="return=representation"),
            params={"user_id": f"eq.{user_id}", "note_id": f"eq.{note_id}", "version": f"eq.{int(expected_version)}"},
            json=body)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list) and payload:
            return dict(payload[0])
        raise OptimisticConcurrencyError(f"no row matched version={expected_version} for {user_id}/{note_id}")

    def list_cards(self, user_id: str, *, subject_id: str = "", card_type: str = "") -> list[dict[str, Any]]:
        params = {"select": "*", "user_id": f"eq.{user_id}", "archived_at": "is.null", "order": "updated_at.desc"}
        if str(subject_id or "").strip():
            params["subject_id"] = f"eq.{subject_id}"
        if str(card_type or "").strip():
            params["card_type"] = f"eq.{card_type}"
        resp = self._http().get(f"{self._base_url}/rest/v1/{self._TABLE}", headers=self._headers(), params=params)
        resp.raise_for_status()
        payload = resp.json()
        return [dict(i) for i in payload if isinstance(i, dict)]


class PostgresNotebookCardStore:
    """Direct app-DB store for environments where learner tables live behind DB_URL."""

    _TABLE = "public.learner_notebook_cards"
    _COLUMNS = (
        "user_id",
        "note_id",
        "subject_id",
        "source_bot_id",
        "card_type",
        "source_type",
        "source_ref",
        "evidence_event_ids",
        "title",
        "raw_user_content",
        "ai_enhanced_content",
        "user_control_status",
        "use_for_personalization",
        "mastery_effect",
        "version",
        "created_at",
        "updated_at",
        "archived_at",
    )
    _JSON_COLUMNS = {"source_ref", "evidence_event_ids", "ai_enhanced_content"}

    def __init__(self, *, database_url: str | None = None, timeout_s: float = 10.0) -> None:
        self._database_url = str(
            database_url
            or os.getenv("NOTEBOOK_CARD_DATABASE_URL", "")
            or os.getenv("DB_URL", "")
            or os.getenv("DATABASE_URL", "")
            or ""
        ).strip()
        self._timeout_s = float(timeout_s)

    @property
    def is_configured(self) -> bool:
        return bool(self._database_url)

    def _connect(self):
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except Exception as exc:  # pragma: no cover - depends on optional runtime package.
            raise RuntimeError("psycopg2 is required for notebook_card DB_URL store") from exc
        return psycopg2.connect(
            self._database_url,
            connect_timeout=max(1, int(self._timeout_s)),
            cursor_factory=RealDictCursor,
        )

    def _adapt(self, column: str, value: Any) -> Any:
        if column in self._JSON_COLUMNS:
            from psycopg2.extras import Json

            return Json(value if value is not None else ({} if column != "evidence_event_ids" else []))
        return value

    def _normalize(self, row: Any) -> dict[str, Any]:
        return dict(row or {}) if row is not None else {}

    def upsert_card(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = {column: dict(row or {}).get(column) for column in self._COLUMNS if column in dict(row or {})}
        columns = [column for column in self._COLUMNS if column in payload]
        placeholders = ", ".join(["%s"] * len(columns))
        insert_columns = ", ".join(columns)
        update_columns = [column for column in columns if column not in {"user_id", "note_id", "created_at"}]
        update_clause = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
        values = [self._adapt(column, payload.get(column)) for column in columns]
        sql = (
            f"insert into {self._TABLE} ({insert_columns}) values ({placeholders}) "
            f"on conflict (user_id, note_id) do update set {update_clause} returning *"
        )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
                return self._normalize(cur.fetchone())

    def get_card(self, user_id: str, note_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"select * from {self._TABLE} where user_id=%s and note_id=%s limit 1",
                    (str(user_id or ""), str(note_id or "")),
                )
                row = cur.fetchone()
        return self._normalize(row) if row else None

    def update_card(self, user_id: str, note_id: str, patch: dict[str, Any], *, expected_version: int) -> dict[str, Any] | None:
        safe_patch = {
            key: value
            for key, value in dict(patch or {}).items()
            if key in self._COLUMNS and key not in {"user_id", "note_id", "version", "created_at"}
        }
        body = {**safe_patch, "version": int(expected_version) + 1}
        assignments = ", ".join(f"{column}=%s" for column in body)
        values = [self._adapt(column, value) for column, value in body.items()]
        values.extend([str(user_id or ""), str(note_id or ""), int(expected_version)])
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"update {self._TABLE} set {assignments} "
                    "where user_id=%s and note_id=%s and version=%s returning *",
                    values,
                )
                row = cur.fetchone()
        if row:
            return self._normalize(row)
        if self.get_card(user_id, note_id) is not None:
            raise OptimisticConcurrencyError(f"no row matched version={expected_version} for {user_id}/{note_id}")
        return None

    def list_cards(self, user_id: str, *, subject_id: str = "", card_type: str = "") -> list[dict[str, Any]]:
        clauses = ["user_id=%s", "archived_at is null"]
        values: list[Any] = [str(user_id or "")]
        if str(subject_id or "").strip():
            clauses.append("subject_id=%s")
            values.append(str(subject_id or "").strip())
        if str(card_type or "").strip():
            clauses.append("card_type=%s")
            values.append(str(card_type or "").strip())
        sql = f"select * from {self._TABLE} where {' and '.join(clauses)} order by updated_at desc"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
                rows = cur.fetchall()
        return [self._normalize(row) for row in rows or []]


__all__ = [
    "OptimisticConcurrencyError",
    "NotebookCardStore",
    "InMemoryNotebookCardStore",
    "UnavailableNotebookCardStore",
    "PostgresNotebookCardStore",
    "SupabaseNotebookCardStore",
]
