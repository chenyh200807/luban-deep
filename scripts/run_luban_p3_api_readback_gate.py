#!/usr/bin/env python3
"""P3 API-surface readback gate for the grading-to-brain loop.

This gate reuses the P2 local LearnerStateService runtime and proves the same
learning evidence is readable through existing API read models:
  - GET /api/v1/learning-brain/projection
  - GET /api/v1/mobile/learning-report?schema_version=2

It uses FastAPI TestClient only. It does not start a dev server, write
production DB state, promote canonical truth, publish registries, or touch
remote state.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from scripts.run_luban_p2_live_readback_gate import (  # noqa: E402
    build_p2_live_readback_package,
    _local_service,
)
from scripts.run_luban_judge_grading_to_brain_trace import USER  # noqa: E402

DEFAULT_OUTPUT = ROOT / "artifacts/luban_grading_artifacts/p3_api_readback_20260611"
API_SURFACES = [
    "/api/v1/learning-brain/projection",
    "/api/v1/mobile/learning-report?schema_version=2",
]


class _LocalMemberService:
    def get_today_progress(self, _user_id: str) -> dict[str, Any]:
        return {"today_done": 0, "daily_target": 30, "streak_days": 0}

    def get_home_dashboard(self, _user_id: str) -> dict[str, Any]:
        return {
            "review": {"due_today": 0, "overdue": 0},
            "mastery": {"weak_nodes": []},
            "today": {"hint": "优先补强采分点遗漏"},
            "recommended_prompts": [],
        }

    def get_assessment_profile(self, _user_id: str) -> dict[str, Any]:
        return {"level": "qa", "chapter_mastery": {}}

    def get_mastery_dashboard(self, _user_id: str) -> dict[str, Any]:
        return {"overall_mastery": 0, "groups": [], "hotspots": [], "review_summary": {"total_due": 0}}


class _LocalNotebookCardService:
    def list_cards(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return []


class _LocalMistakeBookService:
    def bookmark_event_ids(self, *_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    def list_items(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return []


def _sha(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _artifact_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _output_projection_hash(payload: dict[str, Any]) -> str:
    synthesis_run = payload.get("synthesis_run") if isinstance(payload.get("synthesis_run"), dict) else {}
    return str(payload.get("output_projection_hash") or synthesis_run.get("output_projection_hash") or "").strip()


def _report_projection_hash(payload: dict[str, Any]) -> str:
    learning_brain = payload.get("learning_brain") if isinstance(payload.get("learning_brain"), dict) else {}
    return _output_projection_hash(learning_brain)


def _build_app(router: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@contextmanager
def _patched_mobile_module(
    *,
    mobile_module: Any,
    learner_state_service: Any,
    user_id: str,
) -> Iterator[None]:
    old_values = {
        "learner_state_service": mobile_module.learner_state_service,
        "member_service": mobile_module.member_service,
        "mistake_book_service": mobile_module.mistake_book_service,
        "get_notebook_card_service": mobile_module.get_notebook_card_service,
        "_resolve_authenticated_user_id": mobile_module._resolve_authenticated_user_id,
    }
    old_env = {
        "DEEPTUTOR_ENV": os.environ.get("DEEPTUTOR_ENV"),
        "DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA": os.environ.get("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA"),
        "DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK": os.environ.get(
            "DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK"
        ),
    }
    try:
        os.environ["DEEPTUTOR_ENV"] = "local"
        os.environ["DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA"] = "1"
        os.environ["DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK"] = "1"
        mobile_module.learner_state_service = learner_state_service
        mobile_module.member_service = _LocalMemberService()
        mobile_module.mistake_book_service = _LocalMistakeBookService()
        mobile_module.get_notebook_card_service = lambda: _LocalNotebookCardService()
        mobile_module._resolve_authenticated_user_id = lambda *_args, **_kwargs: user_id
        yield
    finally:
        for key, value in old_values.items():
            setattr(mobile_module, key, value)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def build_p3_api_readback_package(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT,
    include_mobile_report_readback: bool = True,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    p2_dir = out / "p2_live_readback_source"
    p2_package = build_p2_live_readback_package(output_dir=p2_dir)
    user_id = f"{USER}_p2_live_readback"
    learner_state_service = _local_service(p2_dir / "local_runtime" / "live")

    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")
    with _patched_mobile_module(
        mobile_module=mobile_module,
        learner_state_service=learner_state_service,
        user_id=user_id,
    ):
        with TestClient(_build_app(mobile_module.router)) as client:
            projection_response = client.get("/api/v1/learning-brain/projection?event_limit=25")
            report_response = (
                client.get("/api/v1/mobile/learning-report?event_limit=25&schema_version=2")
                if include_mobile_report_readback
                else None
            )

    projection_payload = projection_response.json() if projection_response.status_code == 200 else {}
    report_payload = (
        report_response.json()
        if report_response is not None and report_response.status_code == 200
        else {}
    )
    projection_hash = _output_projection_hash(projection_payload)
    report_hash = _report_projection_hash(report_payload)
    projection_ok = projection_response.status_code == 200 and bool(projection_hash)
    report_ok = report_response is not None and report_response.status_code == 200 and bool(report_hash)
    hash_match = bool(projection_hash and report_hash and projection_hash == report_hash)

    p2_readbacks = dict((p2_package.get("p2_live_readback") or {}).get("readback_ids") or {})
    api_surface_pair_id = (
        "api_pair_"
        + hashlib.sha256(
            json.dumps(
                {
                    "projection_hash": projection_hash,
                    "report_hash": report_hash,
                    "learner_memory_event_id": p2_readbacks.get("learner_memory_event_id"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]
        if projection_ok and report_ok
        else ""
    )
    readback_ids = {
        "learner_memory_event_id": str(p2_readbacks.get("learner_memory_event_id") or ""),
        "learning_brain_projection_hash": _sha(projection_payload) if projection_payload else "",
        "mobile_learning_report_hash": _sha(report_payload) if report_payload else "",
        "api_surface_pair_id": api_surface_pair_id,
    }
    blockers: list[str] = []
    if not projection_ok:
        blockers.append("learning_brain_projection_readback_missing")
    if not report_ok:
        blockers.append("mobile_learning_report_readback_missing")
    if projection_ok and report_ok and not hash_match:
        blockers.append("api_projection_hash_mismatch")

    package = {
        "schema_version": "luban_p3_api_readback_gate.v1",
        "generated_at": "2026-06-11",
        "p3_api_readback": {
            "verdict": "STRONG-GO" if not blockers else "NO-GO",
            "mode": "local_testclient_api_readback",
            "scope": "local_fastapi_router_not_real_wechat_not_release_truth",
            "api_readback_exercised": True,
            "required_readbacks_present": projection_ok and report_ok,
            "projection_hash_match": hash_match,
            "readback_ids": readback_ids,
            "blockers": blockers,
        },
        "api_readbacks": {
            "learning_brain_projection": {
                "path": "/api/v1/learning-brain/projection?event_limit=25",
                "status_code": projection_response.status_code,
                "output_projection_hash": projection_hash,
                "event_count": projection_payload.get("event_count"),
                "weak_point_count": len(list(projection_payload.get("weak_points") or []))
                if isinstance(projection_payload, dict)
                else 0,
            },
            "mobile_learning_report_v2": {
                "path": "/api/v1/mobile/learning-report?event_limit=25&schema_version=2",
                "status_code": report_response.status_code if report_response is not None else 0,
                "output_projection_hash": report_hash,
                "authority": dict(report_payload.get("authority") or {}) if isinstance(report_payload, dict) else {},
                "grading_to_brain_loop_present": bool(
                    isinstance(report_payload, dict) and report_payload.get("grading_to_brain_loop")
                ),
            },
        },
        "sources": {
            "memory_events_source": "LearnerStateService.MEMORY_EVENTS",
            "api_surfaces": API_SURFACES,
            "p2_artifact_path": _artifact_path(p2_dir / "p2_live_readback_package.json"),
        },
        "local_artifacts": {
            "p2_runtime_root": _artifact_path(p2_dir / "local_runtime"),
        },
        "not_exercised": [
            "production_db_write",
            "canonical_learner_truth_write",
            "published_registry_write",
            "remote_or_aliyun_write",
            "official_score_promotion",
            "real_wechat_package_readback",
            "real_ws_turn",
        ],
        "safety": {
            "production_write_count": 0,
            "db_write_count": 0,
            "remote_write_count": 0,
            "canonical_truth_written": False,
            "published_registry_written": False,
            "official_score_allowed": False,
            "is_release_truth": False,
        },
    }
    (out / "learning_brain_projection_api.json").write_text(
        json.dumps(projection_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "mobile_learning_report_v2_api.json").write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "p3_api_readback_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    package = build_p3_api_readback_package(output_dir=args.output_dir)
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
