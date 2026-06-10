"""Photo-answer orchestrator: quality → L0 → L1 → reconcile → paragraphs →
stem fold → suspicions → confirm payload.

Budget discipline: every provider call is wrapped reserve → call →
settle/refund through CostLedger — there is no spending path outside it.
Auto-L2 is deliberately absent (plan §3.3 v2: 起步期不存在自动 L2); the only
L2 path is the once-per-session user escalation.

Recovery: jobs are durable rows; process_job() is re-entrant — pages whose
(job, page, engine) result already exists are skipped, so a crash rerun
neither re-calls engines nor double-settles the ledger.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from deeptutor.services.photo_answer.cost_ledger import (
    AUTO,
    USER_ESCALATION,
    BudgetExceeded,
    CostLedger,
    EscalationLimitReached,
)
from deeptutor.services.photo_answer.engines.base import (
    EngineError,
    EngineNotConfigured,
    EngineResult,
)
from deeptutor.services.photo_answer.lexicon import suggest_shape_corrections
from deeptutor.services.photo_answer.models import PhotoAnswerError
from deeptutor.services.photo_answer.paragraphs import rebuild_paragraphs
from deeptutor.services.photo_answer.reconcile import reconcile
from deeptutor.services.photo_answer.stem_fold import fold_stem_paragraphs
from deeptutor.services.photo_answer.store import PhotoAnswerStore

logger = logging.getLogger(__name__)

# Reserve estimates per engine call (micros). Settles use actual provider
# cost; estimates only need to be the right order of magnitude for the
# budget gate to be meaningful.
L0_RESERVE_MICROS = 10_000   # 百度标准手写 0.01 元/次
L1_RESERVE_MICROS = 6_000    # qwen-vl-ocr 典型页上限（待 M0 账单回放校准）
L2_RESERVE_MICROS = 225_000  # 阿里起步档 0.225 元/次

DEFAULT_LEASE_SECONDS = 120.0

ENGINE_L0 = "baidu_handwriting"
ENGINE_L1 = "qwen_vl_ocr"
ENGINE_L2 = "aliyun_handwriting"

EngineFactory = Callable[[], Any]


class JobNotLeased(PhotoAnswerError):
    """Another worker holds the lease — caller should simply back off."""


def _result_from_row(row: dict[str, Any]) -> EngineResult:
    return EngineResult(
        engine=str(row["engine"]),
        raw_text=str(row["raw_text"]),
        line_boxes=json.loads(row.get("line_boxes_json") or "[]"),
        char_confidences=json.loads(row.get("char_confidences_json") or "[]"),
        alteration_marks=json.loads(row.get("alteration_marks_json") or "[]"),
    )


class PhotoAnswerService:
    def __init__(
        self,
        *,
        store: PhotoAnswerStore,
        ledger: CostLedger,
        l0_factory: EngineFactory,
        l1_factory: EngineFactory | None = None,
        l2_factory: EngineFactory | None = None,
        image_loader: Callable[[str], bytes],
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
    ) -> None:
        self._store = store
        self._ledger = ledger
        self._l0_factory = l0_factory
        self._l1_factory = l1_factory
        self._l2_factory = l2_factory
        self._image_loader = image_loader
        self._lease_seconds = lease_seconds

    # ---------- submit ----------

    def submit(self, session_id: str, *, idempotency_key: str = "submit") -> dict[str, Any]:
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session {session_id}")
        if session["status"] in ("pages_uploaded", "failed"):
            self._store.set_session_status(session_id, "processing")
        return self._store.create_job(session_id, idempotency_key=idempotency_key)

    # ---------- processing ----------

    def process_job(self, job_id: str) -> None:
        job = self._store.get_job(job_id)
        if job is None or job["status"] not in ("pending", "running"):
            return
        if not self._store.lease_job(job_id, lease_seconds=self._lease_seconds):
            return
        session_id = str(job["session_id"])
        try:
            self._run_pipeline(job)
            self._store.finish_job(job_id, "succeeded")
            session = self._store.get_session(session_id)
            if session and session["status"] == "processing":
                self._store.set_session_status(session_id, "awaiting_confirm")
        except Exception:
            logger.warning("photo_answer job %s failed", job_id, exc_info=True)
            self._store.finish_job(job_id, "failed")
            session = self._store.get_session(session_id)
            if session and session["status"] not in ("failed", "submitted"):
                try:
                    self._store.set_session_status(session_id, "failed")
                except PhotoAnswerError:
                    pass

    def _run_engine_for_page(
        self,
        *,
        job_id: str,
        session_id: str,
        page: dict[str, Any],
        engine: Any,
        reserve_micros: int,
        channel: str = AUTO,
        required: bool,
    ) -> bool:
        """Reserve → recognize → settle → persist. Returns True when a result
        exists (fresh or pre-existing). Optional engines degrade silently on
        budget exhaustion; required engines propagate failures."""
        page_index = int(page["page_index"])
        if self._store.has_ocr_result(job_id, page_index=page_index, engine=engine.name):
            return True
        try:
            entry_id = self._ledger.reserve(
                session_id,
                amount_micros=reserve_micros,
                channel=channel,
                note=f"{engine.name}:p{page_index}",
            )
        except BudgetExceeded:
            if required:
                raise
            logger.info(
                "photo_answer budget exhausted, skipping %s for page %s", engine.name, page_index
            )
            return False
        try:
            result = engine.recognize(self._image_loader(str(page["image_ref"])))
        except Exception:
            self._ledger.refund(entry_id)
            if required:
                raise
            logger.warning(
                "photo_answer optional engine %s failed on page %s", engine.name, page_index,
                exc_info=True,
            )
            return False
        self._ledger.settle(
            entry_id,
            actual_micros=int(result.cost_micros),
            provider_usage_id=result.provider_usage_id,
        )
        self._store.save_ocr_result(
            job_id,
            page_index=page_index,
            engine=engine.name,
            raw_text=result.raw_text,
            line_boxes=result.line_boxes,
            char_confidences=result.char_confidences,
            alteration_marks=result.alteration_marks,
            engine_model_version=result.engine_model_version,
            request_hash=result.request_hash,
            provider_usage_id=result.provider_usage_id,
            cost_micros=int(result.cost_micros),
        )
        return True

    def _run_pipeline(self, job: dict[str, Any]) -> None:
        job_id = str(job["id"])
        session_id = str(job["session_id"])
        pages = self._store.list_pages(session_id)
        if not pages:
            raise PhotoAnswerError("Session has no pages to process")

        l0 = self._l0_factory()
        if l0 is None:
            raise EngineNotConfigured("L0 engine unavailable")
        l1 = None
        if self._l1_factory is not None:
            try:
                l1 = self._l1_factory()
            except EngineNotConfigured:
                logger.info("photo_answer L1 not configured — degrading to L0 only")

        for page in pages:
            self._run_engine_for_page(
                job_id=job_id,
                session_id=session_id,
                page=page,
                engine=l0,
                reserve_micros=L0_RESERVE_MICROS,
                required=True,
            )
            if l1 is not None:
                self._run_engine_for_page(
                    job_id=job_id,
                    session_id=session_id,
                    page=page,
                    engine=l1,
                    reserve_micros=L1_RESERVE_MICROS,
                    required=False,
                )

        self._rebuild_suspicions(job_id=job_id, session_id=session_id)

    def _page_results(self, job_id: str) -> dict[int, dict[str, EngineResult]]:
        by_page: dict[int, dict[str, EngineResult]] = {}
        for row in self._store.list_ocr_results(job_id):
            by_page.setdefault(int(row["page_index"]), {})[str(row["engine"])] = _result_from_row(row)
        return by_page

    @staticmethod
    def _authoritative(results: dict[str, EngineResult]) -> EngineResult | None:
        # L2 (escalated re-recognition) takes over the page when present.
        return results.get(ENGINE_L2) or results.get(ENGINE_L0)

    def _rebuild_suspicions(self, *, job_id: str, session_id: str) -> None:
        suspicions: list[dict[str, Any]] = []
        for page_index, results in sorted(self._page_results(job_id).items()):
            primary = self._authoritative(results)
            if primary is None:
                continue
            out = reconcile(primary, results.get(ENGINE_L1))
            for item in out.suspicions:
                item["page_index"] = page_index
                suspicions.append(item)
            # 形近字建议：仅候选字证据支撑（lexicon 纪律见模块 docstring）
            chars_by_line: dict[int, list[dict[str, Any]]] = {}
            for ch in primary.char_confidences:
                chars_by_line.setdefault(int(ch.get("line_index") or 0), []).append(ch)
            for line in primary.line_boxes:
                line_chars = chars_by_line.get(int(line.get("line_index") or 0)) or []
                for sug in suggest_shape_corrections(str(line.get("text") or ""), line_chars):
                    suspicions.append(
                        {
                            "source": "lexicon",
                            "severity": "normal",
                            "page_index": page_index,
                            "span": {
                                "line_index": sug["line_index"],
                                "box": sug["box"],
                                "char": sug["char"],
                            },
                            "suggestion": sug["suggestion"],
                        }
                    )
        self._store.replace_suspicions(session_id, job_id=job_id, items=suspicions)

    # ---------- view / confirm / escalation ----------

    def get_view(self, session_id: str) -> dict[str, Any]:
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session {session_id}")
        job = self._store.get_latest_job(session_id)
        view: dict[str, Any] = {
            "session": session,
            "job": job,
            "paragraphs": [],
            "draft_text": "",
            "suspicions": [],
            "raw_text": "",
        }
        if job is None:
            return view
        paragraphs: list[dict[str, Any]] = []
        raw_parts: list[str] = []
        for page_index, results in sorted(self._page_results(str(job["id"])).items()):
            primary = self._authoritative(results)
            if primary is None:
                continue
            raw_parts.append(primary.raw_text)
            page_paras = rebuild_paragraphs(primary.line_boxes)
            for para in page_paras:
                para["page_index"] = page_index
            paragraphs.extend(page_paras)
        folded = fold_stem_paragraphs(paragraphs, question_stem=str(session.get("question_stem") or ""))
        view["paragraphs"] = folded
        view["draft_text"] = "\n".join(
            p["text"] for p in folded if not p.get("is_stem_suspect")
        )
        view["raw_text"] = "\n".join(raw_parts)
        view["suspicions"] = self._store.list_suspicions(session_id, job_id=str(job["id"]))
        return view

    def confirm(
        self,
        session_id: str,
        *,
        confirmed_text: str,
        job_version: int,
        ack_normal_suspicions: bool = False,
        resolved_span_ids: list[str] | None = None,
        diff: list[Any] | None = None,
        edited_char_count: int = 0,
    ) -> dict[str, Any]:
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session {session_id}")
        job = self._store.get_latest_job(session_id)
        if job is None:
            raise PhotoAnswerError("No OCR job for session")
        if int(job_version) != int(job["job_version"]):
            raise ValueError(
                f"Stale job_version {job_version}; latest is {job['job_version']}"
            )

        resolved_ids = set(resolved_span_ids or [])
        if resolved_ids:
            self._store.mark_suspicions_resolved(session_id, sorted(resolved_ids))
        suspicions = self._store.list_suspicions(session_id, job_id=str(job["id"]))
        unresolved = [
            s for s in suspicions if not s["resolved_by_user"] and s["id"] not in resolved_ids
        ]
        critical_unresolved = [s for s in unresolved if s["severity"] == "critical"]
        normal_unresolved = [s for s in unresolved if s["severity"] != "critical"]

        if normal_unresolved and not ack_normal_suspicions:
            return {
                "status": "needs_review_ack",
                "unresolved_normal": len(normal_unresolved),
                "unresolved_critical": len(critical_unresolved),
            }

        bad_pages = [
            p
            for p in self._store.list_pages(session_id)
            if not json.loads(p.get("quality_json") or "{}").get("ok", True)
        ]
        # C9 fail-closed: 关键疑点未解决或页质检差 → provisional 批改，不写长期学习证据。
        provisional = bool(critical_unresolved or bad_pages)

        ack_flags = {
            "needs_review_ack": bool(normal_unresolved),
            "critical_failclosed": provisional,
            "unresolved_critical": len(critical_unresolved),
            "bad_pages": [int(p["page_index"]) for p in bad_pages],
        }
        confirmation = self._store.save_confirmation(
            session_id,
            job_version=int(job_version),
            confirmed_text=confirmed_text,
            diff=diff,
            edited_char_count=int(edited_char_count),
            ack_flags=ack_flags,
        )
        self._store.set_session_status(session_id, "confirmed")

        view_raw = self.get_view(session_id)["raw_text"]
        payload = {
            "input_mode": "photo_ocr",
            "photo_session_id": session_id,
            "question_id": str(session["question_id"]),
            "confirmed_text": confirmed_text,
            "raw_ocr_text": view_raw,
            "image_refs": [str(p["image_ref"]) for p in self._store.list_pages(session_id)],
            "suspicion_spans": [
                {
                    "id": s["id"],
                    "page_index": s["page_index"],
                    "source": s["source"],
                    "severity": s["severity"],
                    "span": json.loads(s["span_json"] or "{}"),
                }
                for s in unresolved
            ],
            "grading_tier": "provisional" if provisional else "standard",
            # provenance schema 未过 contract 评审前，photo 路径不写长期学习证据
            # （plan §4 / M1 Task 0）。provisional 时同样禁止。
            "learning_evidence_allowed": not provisional,
        }
        return {"status": "confirmed", "confirmation": confirmation, "grader_payload": payload}

    def escalate_page(self, session_id: str, *, page_index: int) -> dict[str, Any]:
        if self._l2_factory is None:
            raise EngineNotConfigured("L2 engine not configured")
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session {session_id}")
        job = self._store.get_latest_job(session_id)
        if job is None:
            raise PhotoAnswerError("No OCR job for session")
        # 每 session 仅 1 次主动升级（plan §3.3）。显式前置检查而非依赖
        # reserve——已升级页的幂等跳过会绕过 reserve，必须在这里拦住。
        already = [
            e
            for e in self._ledger.list_entries(session_id)
            if e["channel"] == USER_ESCALATION and e["state"] in ("reserved", "settled")
        ]
        if already:
            raise EscalationLimitReached("user_escalation already used for this session")
        pages = {int(p["page_index"]): p for p in self._store.list_pages(session_id)}
        page = pages.get(int(page_index))
        if page is None:
            raise KeyError(f"Unknown page {page_index}")
        l2 = self._l2_factory()
        self._run_engine_for_page(
            job_id=str(job["id"]),
            session_id=session_id,
            page=page,
            engine=l2,
            reserve_micros=L2_RESERVE_MICROS,
            channel=USER_ESCALATION,
            required=True,
        )
        self._rebuild_suspicions(job_id=str(job["id"]), session_id=session_id)
        return self.get_view(session_id)
