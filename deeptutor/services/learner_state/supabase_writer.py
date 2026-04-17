from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from deeptutor.services.learner_state.heartbeat.store import LearnerHeartbeatJobStore
from deeptutor.services.learning_plan import LearningPlanService
from deeptutor.services.learner_state.outbox import LearnerStateOutboxItem
from deeptutor.services.path_service import PathService, get_path_service


@dataclass(frozen=True)
class LearnerStateSupabaseWriteResult:
    ok: bool
    event_type: str
    written_tables: tuple[str, ...] = ()
    reason: str | None = None


class LearnerStateSupabaseWriter:
    """Minimal Supabase writer for learner-state outbox items."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 10.0,
        path_service: PathService | None = None,
    ) -> None:
        self._base_url = str(base_url or os.getenv("SUPABASE_URL", "") or "").strip()
        self._service_key = str(
            service_key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
            or os.getenv("SUPABASE_KEY", "")
            or ""
        ).strip()
        self._client = client
        self._timeout_s = float(timeout_s)
        self._owns_client = client is None
        self._path_service = path_service or get_path_service()
        self._learning_plan_service = LearningPlanService(path_service=self._path_service)
        self._heartbeat_job_store = LearnerHeartbeatJobStore(
            self._path_service.project_root / "data" / "runtime" / "learner_state" / "heartbeat_jobs.json"
        )

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._service_key)

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def write(self, item: LearnerStateOutboxItem) -> LearnerStateSupabaseWriteResult:
        return await self.write_item(item)

    async def write_item(self, item: LearnerStateOutboxItem) -> LearnerStateSupabaseWriteResult:
        event_type = str(item.event_type or "").strip()
        if not event_type:
            return LearnerStateSupabaseWriteResult(False, event_type, reason="event_type is required")
        if not self._base_url:
            return LearnerStateSupabaseWriteResult(False, event_type, reason="SUPABASE_URL is missing")
        if not self._service_key:
            return LearnerStateSupabaseWriteResult(
                False,
                event_type,
                reason="SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY is missing",
            )
        if not self._supports_event_type(event_type):
            return LearnerStateSupabaseWriteResult(
                False,
                event_type,
                reason=f"unsupported event_type: {event_type}",
            )

        client = await self._get_client()
        payload = self._unpack_payload(item)
        inner_payload = dict(payload.get("payload_json") or {})
        guide_rows: tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]] | None = None
        heartbeat_job_row: dict[str, Any] | None = None
        summary_row: dict[str, Any] | None = None
        memory_event_row: dict[str, Any] | None = None
        overlay_rows: tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]] | None = None

        if event_type == "summary_refresh":
            summary_row = self._build_summary_refresh_row(item, payload)
            if summary_row is None:
                return LearnerStateSupabaseWriteResult(
                    False,
                    event_type,
                    reason="summary_refresh payload is missing summary_md",
                )
        elif event_type not in {"heartbeat_job", "learning_plan_page"}:
            memory_event_row = self._build_memory_event_row(item, payload)
            if event_type.startswith("overlay_"):
                overlay_rows = self._build_overlay_sync_rows(item, payload, event_type=event_type)

        if event_type == "guide_completion":
            guide_rows = self._build_guide_completion_rows(item, payload, inner_payload)
            if guide_rows is None:
                return LearnerStateSupabaseWriteResult(
                    False,
                    event_type,
                    reason="guide_completion payload is missing guide_id or summary",
                )

        if event_type == "heartbeat_job":
            heartbeat_job_row = self._build_heartbeat_job_row(item, payload)
            if heartbeat_job_row is None:
                return LearnerStateSupabaseWriteResult(
                    False,
                    event_type,
                    reason="heartbeat_job payload is missing job_id",
                )

        learning_plan_page_rows: tuple[dict[str, Any], dict[str, Any]] | None = None
        if event_type == "learning_plan_page":
            learning_plan_page_rows = self._build_learning_plan_page_sync_rows(
                item,
                payload,
                inner_payload,
            )
            if learning_plan_page_rows is None:
                return LearnerStateSupabaseWriteResult(
                    False,
                    event_type,
                    reason="learning_plan_page payload is missing plan_id or page_index",
                )

        try:
            written_tables: list[str] = []
            if memory_event_row is not None:
                await self._upsert(
                    client,
                    table="learner_memory_events",
                    rows=[memory_event_row],
                    on_conflict="dedupe_key",
                )
                written_tables.append("learner_memory_events")

            if overlay_rows is not None:
                overlay_row, overlay_event_row, overlay_audit_row = overlay_rows
                if overlay_row is not None:
                    await self._upsert(
                        client,
                        table="bot_learner_overlays",
                        rows=[overlay_row],
                        on_conflict="bot_id,user_id",
                    )
                    written_tables.append("bot_learner_overlays")
                await self._upsert(
                    client,
                    table="bot_learner_overlay_events",
                    rows=[overlay_event_row],
                    on_conflict="dedupe_key",
                )
                written_tables.append("bot_learner_overlay_events")
                await self._upsert(
                    client,
                    table="bot_learner_overlay_audit",
                    rows=[overlay_audit_row],
                    on_conflict="audit_id",
                )
                written_tables.append("bot_learner_overlay_audit")

            if summary_row is not None:
                await self._upsert(
                    client,
                    table="learner_summaries",
                    rows=[summary_row],
                    on_conflict="user_id",
                )
                written_tables.append("learner_summaries")

            if guide_rows is not None:
                guide_summary_row, plan_row, page_rows = guide_rows
                await self._upsert(
                    client,
                    table="learner_summaries",
                    rows=[guide_summary_row],
                    on_conflict="user_id",
                )
                written_tables.append("learner_summaries")
                await self._upsert(
                    client,
                    table="learning_plans",
                    rows=[plan_row],
                    on_conflict="plan_id",
                )
                written_tables.append("learning_plans")
                if page_rows:
                    await self._upsert(
                        client,
                        table="learning_plan_pages",
                        rows=page_rows,
                        on_conflict="plan_id,page_index",
                    )
                    written_tables.append("learning_plan_pages")

            if heartbeat_job_row is not None:
                await self._upsert(
                    client,
                    table="heartbeat_jobs",
                    rows=[heartbeat_job_row],
                    on_conflict="job_id",
                )
                written_tables.append("heartbeat_jobs")

            if learning_plan_page_rows is not None:
                plan_row, page_row = learning_plan_page_rows
                await self._upsert(
                    client,
                    table="learning_plans",
                    rows=[plan_row],
                    on_conflict="plan_id",
                )
                written_tables.append("learning_plans")
                await self._upsert(
                    client,
                    table="learning_plan_pages",
                    rows=[page_row],
                    on_conflict="plan_id,page_index",
                )
                written_tables.append("learning_plan_pages")

            return LearnerStateSupabaseWriteResult(True, event_type, tuple(written_tables))
        except httpx.HTTPStatusError as exc:
            return LearnerStateSupabaseWriteResult(
                False,
                event_type,
                tuple(written_tables),
                reason=self._format_http_error(exc.response),
            )
        except Exception as exc:
            return LearnerStateSupabaseWriteResult(
                False,
                event_type,
                tuple(written_tables),
                reason=str(exc).strip() or exc.__class__.__name__,
            )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(timeout=self._timeout_s)
        self._owns_client = True
        return self._client

    async def _upsert(
        self,
        client: httpx.AsyncClient,
        *,
        table: str,
        rows: list[dict[str, Any]],
        on_conflict: str,
    ) -> None:
        url = f"{self._base_url.rstrip('/')}/rest/v1/{table}"
        response = await client.post(
            url,
            headers=self._headers(),
            params={"on_conflict": on_conflict},
            json=rows,
        )
        response.raise_for_status()

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._service_key,
            "Authorization": f"Bearer {self._service_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }

    @staticmethod
    def _unpack_payload(item: LearnerStateOutboxItem) -> dict[str, Any]:
        payload = dict(item.payload_json or {})
        nested = payload.get("payload_json")
        if isinstance(nested, dict):
            payload["payload_json"] = dict(nested)
        return payload

    @staticmethod
    def _supports_event_type(event_type: str) -> bool:
        return event_type in {
            "turn",
            "guide_completion",
            "progress",
            "summary_refresh",
            "heartbeat_job",
            "heartbeat_delivery",
            "learning_plan_page",
            "overlay_patch",
            "overlay_promotion_queue_update",
            "overlay_promotion_apply",
            "overlay_decay",
        } or event_type.startswith(
            "notebook_"
        )

    def _build_memory_event_row(
        self,
        item: LearnerStateOutboxItem,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        inner_payload = dict(payload.get("payload_json") or {})
        return {
            "event_id": str(payload.get("event_id") or item.id).strip(),
            "user_id": str(item.user_id).strip(),
            "source_feature": str(payload.get("source_feature") or item.event_type).strip(),
            "source_id": str(payload.get("source_id") or item.id).strip(),
            "source_bot_id": self._null_if_blank(payload.get("source_bot_id")),
            "memory_kind": str(payload.get("memory_kind") or item.event_type).strip(),
            "payload_json": inner_payload,
            "dedupe_key": str(item.dedupe_key).strip(),
            "created_at": str(payload.get("created_at") or item.created_at).strip(),
        }

    def _build_summary_refresh_row(
        self,
        item: LearnerStateOutboxItem,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        summary_md = str(payload.get("summary_md") or "").strip()
        if not summary_md:
            return None
        return {
            "user_id": str(item.user_id).strip(),
            "summary_md": summary_md,
            "summary_structured_json": {
                "source_feature": str(payload.get("source_feature") or "").strip(),
                "source_id": str(payload.get("source_id") or "").strip(),
                "source_bot_id": self._null_if_blank(payload.get("source_bot_id")),
            },
            "last_refreshed_from_turn_id": str(payload.get("source_id") or "").strip() or None,
            "last_refreshed_from_feature": str(payload.get("source_feature") or "summary_refresh").strip(),
            "updated_at": str(payload.get("updated_at") or item.created_at).strip(),
        }

    def _build_heartbeat_job_row(
        self,
        item: LearnerStateOutboxItem,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        job_id = str(payload.get("job_id") or item.id).strip()
        if not job_id:
            return None
        job = self._heartbeat_job_store.get_by_id(job_id)
        if job is None:
            return None
        job_payload = job.to_dict()
        return {
            "job_id": job_payload["job_id"],
            "user_id": job_payload["user_id"],
            "bot_id": job_payload["bot_id"],
            "channel": job_payload["channel"],
            "policy_json": job_payload["policy_json"],
            "next_run_at": job_payload["next_run_at"],
            "last_run_at": job_payload["last_run_at"],
            "last_result_json": job_payload["last_result_json"],
            "failure_count": int(job_payload["failure_count"]),
            "status": self._normalize_heartbeat_status(str(job_payload["status"] or "")),
            "created_at": job_payload["created_at"],
            "updated_at": job_payload["updated_at"],
        }

    def _build_overlay_sync_rows(
        self,
        item: LearnerStateOutboxItem,
        payload: dict[str, Any],
        *,
        event_type: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
        bot_id = str(payload.get("bot_id") or "").strip()
        user_id = str(payload.get("user_id") or item.user_id).strip()
        overlay_snapshot = dict(payload.get("overlay_snapshot") or {})
        active_plan_binding = dict(overlay_snapshot.get("active_plan_binding") or {})
        overlay_row: dict[str, Any] | None = None
        if bot_id and user_id and overlay_snapshot:
            overlay_row = {
                "bot_id": bot_id,
                "user_id": user_id,
                "local_focus_json": dict(overlay_snapshot.get("local_focus") or {}),
                "active_plan_id": self._null_if_blank(active_plan_binding.get("plan_id")),
                "teaching_policy_override_json": dict(overlay_snapshot.get("teaching_policy_override") or {}),
                "heartbeat_override_json": dict(overlay_snapshot.get("heartbeat_override") or {}),
                "channel_presence_override_json": dict(overlay_snapshot.get("channel_presence_override") or {}),
                "local_notebook_scope_refs_json": list(overlay_snapshot.get("local_notebook_scope_refs") or []),
                "engagement_state_json": dict(overlay_snapshot.get("engagement_state") or {}),
                "promotion_candidates_json": list(overlay_snapshot.get("promotion_candidates") or []),
                "working_memory_projection_md": str(overlay_snapshot.get("working_memory_projection") or "").strip(),
                "version": int(payload.get("overlay_version") or 1),
                "created_at": str(payload.get("created_at") or item.created_at).strip(),
                "updated_at": str(payload.get("created_at") or item.created_at).strip(),
            }

        overlay_event_row = {
            "event_id": str(payload.get("event_id") or item.id).strip(),
            "bot_id": bot_id,
            "user_id": user_id,
            "source_feature": str(payload.get("source_feature") or "overlay").strip() or "overlay",
            "source_id": str(payload.get("source_id") or item.id).strip(),
            "patch_kind": event_type,
            "payload_json": dict(payload),
            "dedupe_key": str(item.dedupe_key).strip(),
            "created_at": str(payload.get("created_at") or item.created_at).strip(),
        }
        overlay_audit_row = {
            "audit_id": str(payload.get("audit_id") or item.id).strip(),
            "bot_id": bot_id,
            "user_id": user_id,
            "actor": self._null_if_blank(payload.get("actor")),
            "action": event_type,
            "fields_json": list(payload.get("overlay_fields") or []),
            "metadata_json": {
                key: value
                for key, value in dict(payload).items()
                if key != "overlay_snapshot"
            },
            "created_at": str(payload.get("created_at") or item.created_at).strip(),
        }
        return overlay_row, overlay_event_row, overlay_audit_row

    def _build_learning_plan_page_sync_rows(
        self,
        item: LearnerStateOutboxItem,
        payload: dict[str, Any],
        inner_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        plan_id = str(inner_payload.get("plan_id") or payload.get("source_id") or "").strip()
        page_index_value = inner_payload.get("page_index")
        if page_index_value is None:
            page_index_value = payload.get("page_index")
        try:
            page_index = int(page_index_value)
        except (TypeError, ValueError):
            return None
        if not plan_id:
            return None

        plan_view = self._learning_plan_service.read_guided_session_view(plan_id) or {}
        plan_pages = [dict(page) for page in list(plan_view.get("pages") or []) if isinstance(page, dict)]
        page_view = next(
            (
                page
                for page in plan_pages
                if int(page.get("page_index", -1) or -1) == page_index
            ),
            None,
        )
        page_status = str(
            inner_payload.get("page_status")
            or payload.get("page_status")
            or (page_view or {}).get("page_status")
            or "pending"
        ).strip() or "pending"
        html_content = str(
            inner_payload.get("html_content")
            or (page_view or {}).get("html")
            or ""
        ).strip()
        error_message = str(
            inner_payload.get("error_message")
            or (page_view or {}).get("page_error")
            or ""
        ).strip()
        generated_at = str(
            inner_payload.get("generated_at")
            or payload.get("generated_at")
            or (page_view or {}).get("updated_at")
            or (page_view or {}).get("created_at")
            or item.created_at
        ).strip()

        plan_row = {
            "plan_id": plan_id,
            "user_id": str(item.user_id).strip(),
            "source_bot_id": self._null_if_blank(
                inner_payload.get("source_bot_id") or payload.get("source_bot_id") or plan_view.get("source_bot_id")
            ),
            "source_material_refs_json": list(
                plan_view.get("source_material_refs_json")
                or inner_payload.get("source_material_refs_json")
                or []
            ),
            "knowledge_points_json": [
                {
                    "knowledge_title": str(point.get("knowledge_title") or "").strip(),
                    "knowledge_summary": str(point.get("knowledge_summary") or "").strip(),
                    "user_difficulty": str(point.get("user_difficulty") or "").strip(),
                }
                for point in list(plan_view.get("knowledge_points") or [])
                if isinstance(point, dict)
            ],
            "status": str(plan_view.get("status") or "initialized").strip() or "initialized",
            "current_index": int(plan_view.get("current_index")) if plan_view.get("current_index") is not None else -1,
            "completion_summary_md": str(plan_view.get("summary") or "").strip(),
            "created_at": str(plan_view.get("created_at") or item.created_at).strip(),
            "updated_at": str(plan_view.get("updated_at") or item.created_at).strip(),
        }
        page_row = {
            "plan_id": plan_id,
            "page_index": page_index,
            "page_status": page_status,
            "html_content": html_content,
            "error_message": error_message,
            "generated_at": generated_at,
        }
        return plan_row, page_row

    def _build_guide_completion_rows(
        self,
        item: LearnerStateOutboxItem,
        payload: dict[str, Any],
        inner_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]] | None:
        guide_id = str(inner_payload.get("guide_id") or payload.get("source_id") or item.id).strip()
        summary = str(inner_payload.get("summary") or "").strip()
        if not guide_id or not summary:
            return None

        knowledge_points = [
            {
                "knowledge_title": str(point.get("knowledge_title") or "").strip(),
                "knowledge_summary": str(point.get("knowledge_summary") or "").strip(),
                "user_difficulty": str(point.get("user_difficulty") or "").strip(),
            }
            for point in list(inner_payload.get("knowledge_points") or [])
            if isinstance(point, dict)
        ]
        plan_view = self._learning_plan_service.read_guided_session_view(guide_id) or {}
        plan_pages = [dict(page) for page in list(plan_view.get("pages") or []) if isinstance(page, dict)]
        page_rows = self._build_learning_plan_page_rows(
            item,
            guide_id,
            inner_payload,
            knowledge_points,
            plan_pages=plan_pages,
        )
        summary_row = {
            "user_id": str(item.user_id).strip(),
            "summary_md": summary,
            "summary_structured_json": {
                "guide_id": guide_id,
                "notebook_name": str(inner_payload.get("notebook_name") or "").strip(),
                "total_points": int(inner_payload.get("total_points") or len(knowledge_points) or 0),
                "knowledge_points": knowledge_points,
            },
            "last_refreshed_from_turn_id": guide_id,
            "last_refreshed_from_feature": "guide_completion",
            "updated_at": str(payload.get("created_at") or item.created_at).strip(),
        }
        plan_row = {
            "plan_id": guide_id,
            "user_id": str(item.user_id).strip(),
            "source_bot_id": self._null_if_blank(payload.get("source_bot_id")),
            "source_material_refs_json": list(
                plan_view.get("source_material_refs_json")
                or inner_payload.get("source_material_refs_json")
                or []
            ),
            "knowledge_points_json": knowledge_points,
            "status": str(plan_view.get("status") or "completed").strip() or "completed",
            "current_index": max(
                int(
                    plan_view.get("current_index")
                    if plan_view.get("current_index") is not None
                    else int(inner_payload.get("total_points") or len(knowledge_points) or 0) - 1
                ),
                0,
            ),
            "completion_summary_md": summary,
            "created_at": str(plan_view.get("created_at") or payload.get("created_at") or item.created_at).strip(),
            "updated_at": str(payload.get("created_at") or item.created_at).strip(),
        }
        return summary_row, plan_row, page_rows

    def _build_learning_plan_page_rows(
        self,
        item: LearnerStateOutboxItem,
        plan_id: str,
        inner_payload: dict[str, Any],
        knowledge_points: list[dict[str, Any]],
        *,
        plan_pages: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if plan_pages:
            rows: list[dict[str, Any]] = []
            for page in plan_pages:
                rows.append(
                    {
                        "plan_id": plan_id,
                        "page_index": int(page.get("page_index", 0)),
                        "page_status": str(page.get("page_status") or "pending").strip() or "pending",
                        "html_content": str(page.get("html") or "").strip(),
                        "error_message": str(page.get("page_error") or "").strip(),
                        "generated_at": str(
                            page.get("updated_at")
                            or page.get("created_at")
                            or item.created_at
                        ).strip(),
                    }
                )
            rows.sort(key=lambda row: int(row.get("page_index", 0)))
            return rows

        raw_pages = inner_payload.get("learning_plan_pages")
        if not isinstance(raw_pages, list) or not raw_pages:
            raw_pages = inner_payload.get("pages")
        source_pages = list(raw_pages or [])
        if source_pages:
            rows: list[dict[str, Any]] = []
            for index, page in enumerate(source_pages):
                if not isinstance(page, dict):
                    continue
                page_index = int(page.get("page_index", index) or index)
                page_status = str(page.get("page_status") or "pending").strip() or "pending"
                html_content = str(
                    page.get("html_content")
                    or page.get("html")
                    or page.get("page_html")
                    or ""
                ).strip()
                error_message = str(page.get("error_message") or page.get("page_error") or "").strip()
                rows.append(
                    {
                        "plan_id": plan_id,
                        "page_index": page_index,
                        "page_status": page_status,
                        "html_content": html_content,
                        "error_message": error_message,
                        "generated_at": str(page.get("generated_at") or item.created_at).strip()
                        if page_status != "pending" or html_content or error_message
                        else None,
                    }
                )
            rows.sort(key=lambda row: int(row.get("page_index", 0)))
            return rows

        rows = []
        for index, _point in enumerate(knowledge_points):
            rows.append(
                {
                    "plan_id": plan_id,
                    "page_index": index,
                    "page_status": "pending",
                    "html_content": "",
                    "error_message": "",
                    "generated_at": None,
                }
            )
        return rows

    @staticmethod
    def _null_if_blank(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _normalize_heartbeat_status(status: str) -> str:
        normalized = str(status or "").strip()
        if normalized == "stopped":
            return "disabled"
        if normalized in {"active", "paused", "disabled", "failed"}:
            return normalized
        return "active"

    @staticmethod
    def _format_http_error(response: httpx.Response) -> str:
        detail = response.text.strip()
        if detail:
            return f"HTTP {response.status_code}: {detail}"
        return f"HTTP {response.status_code}"


__all__ = [
    "LearnerStateSupabaseWriteResult",
    "LearnerStateSupabaseWriter",
]
