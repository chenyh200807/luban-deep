#!/usr/bin/env python3
"""Stage 5 live qa/operator PGO traffic canary.

This runner drives authenticated remote `/api/v1/ws` traffic. It verifies that
server-authenticated `qa_` and `operator_` users receive the PGO rubric bank
slot, while a non-cohort control receives the explicit legacy slot. It writes a
sanitized artifact with live shadow delta, over-credit, and score distribution.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_learner_memory_lifecycle_test2_cohort_soak import (  # noqa: E402
    _remote_authenticate,
    _sanitize_auth_detail,
    _write_json,
)

ARTIFACT_ROOT = ROOT / "artifacts" / "luban_grading_artifacts"
DEFAULT_OUTPUT = ARTIFACT_ROOT / "pgo_stage5_live_traffic_canary_20260614"
SCHEMA = "luban_pgo_stage5_live_traffic_canary.v1"
CANARY_PREFIXES = ("qa_", "operator_")
PGO_SCORE_AUTHORITY = "official_total_x_verdict_coverage"
DEFAULT_QUESTION_ID = "2015::EXAM_XW2015_CASE_1::E0"
DEFAULT_QUESTION = "单位工程施工组织设计中，施工部署部分通常应列出哪些计划或资源平衡内容？"
DEFAULT_CORRECT_ANSWER = (
    "施工总进度计划表(图)；分期(分批)实施工程的开、竣工日期及工期一览表；"
    "资源需要量及供应平衡表；施工准备工作计划。"
)
DEFAULT_SAMPLES = (
    {
        "sample_id": "full",
        "answer": (
            "应包括施工总进度计划表图，分期分批实施工程的开工、竣工日期及工期一览表，"
            "资源需要量及供应平衡表，以及施工准备工作计划。"
        ),
    },
    {
        "sample_id": "partial",
        "answer": "包括施工总进度计划表和资源需要量及供应平衡表。",
    },
)


def _build_ws_url(api_base_url: str) -> str:
    parsed = urlparse(str(api_base_url or "").rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/") + "/api/v1/ws"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def _generated_credentials(prefix: str) -> tuple[str, str, str]:
    stamp = int(time.time())
    username = f"{prefix}_{stamp}"
    password = f"CanaryA{stamp % 1000000:06d}"
    phone = f"137{stamp % 100000000:08d}"
    return username, password, phone


def _has_auth_material(spec: dict[str, Any]) -> bool:
    if str(spec.get("auth_token") or "").strip():
        return True
    if bool(spec.get("register")):
        return True
    return bool(str(spec.get("username") or "").strip() and str(spec.get("password") or "").strip())


def _is_canary_user(user_id: str) -> bool:
    normalized = str(user_id or "").strip()
    return bool(normalized) and normalized.startswith(CANARY_PREFIXES)


def _expected_slot_for_user(user_id: str) -> str:
    return "pgo" if _is_canary_user(user_id) else "legacy"


def _ws_frame(*, sample: dict[str, str]) -> dict[str, Any]:
    answer = str(sample.get("answer") or "").strip()
    return {
        "type": "start_turn",
        "content": answer,
        "capability": "deep_question",
        "language": "zh",
        "config": {
            "followup_question_context": {
                "question_id": DEFAULT_QUESTION_ID,
                "question_type": "case",
                "question": DEFAULT_QUESTION,
                "correct_answer": DEFAULT_CORRECT_ANSWER,
                "user_answer": answer,
                "testing_focus": "PGO bank slot live canary",
            },
        },
    }


async def _run_remote_ws_turn(
    *,
    ws_url: str,
    token: str,
    sample: dict[str, str],
    timeout_seconds: float,
    connector_factory: Any | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    connect = connector_factory or websockets.connect
    frame = _ws_frame(sample=sample)
    events: list[dict[str, Any]] = []
    result_event: dict[str, Any] | None = None
    terminal_event: dict[str, Any] | None = None
    async with connect(ws_url, additional_headers=headers) as websocket:
        await websocket.send(json.dumps(frame, ensure_ascii=False))
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
            event = json.loads(raw)
            if not isinstance(event, dict):
                continue
            events.append(event)
            event_type = str(event.get("type") or "").strip()
            if event_type == "result":
                result_event = event
            if event_type in {"done", "error"}:
                terminal_event = event
                break
    return {
        "sample_id": str(sample.get("sample_id") or ""),
        "frame": frame,
        "events": events,
        "result_event": result_event or {},
        "terminal_event": terminal_event or {},
    }


def _case_event(result_event: dict[str, Any]) -> dict[str, Any]:
    metadata = result_event.get("metadata") if isinstance(result_event, dict) else {}
    if not isinstance(metadata, dict):
        return {}
    payload = metadata.get("luban_case_rubric_v1")
    if not isinstance(payload, dict):
        return {}
    event = payload.get("grading_event")
    return dict(event or {}) if isinstance(event, dict) else {}


def _round(value: float | int | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _distribution(records: list[dict[str, Any]], slot: str) -> dict[str, Any]:
    values: list[float] = []
    full_score_count = 0
    for record in records:
        if record.get("observed_slot") != slot:
            continue
        if record.get("awarded_score") is None:
            continue
        value = float(record["awarded_score"])
        values.append(value)
        maximum = record.get("max_score")
        if maximum is not None and value >= float(maximum):
            full_score_count += 1
    return {
        "count": len(values),
        "mean": _round(sum(values) / len(values)) if values else None,
        "median": _round(statistics.median(values)) if values else None,
        "min": _round(min(values)) if values else None,
        "max": _round(max(values)) if values else None,
        "zero_count": sum(1 for value in values if value == 0),
        "full_score_count": full_score_count,
    }


def _score_distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pgo": _distribution(records, "pgo"),
        "legacy": _distribution(records, "legacy"),
    }


def _mean(values: list[float]) -> float | None:
    return _round(sum(values) / len(values)) if values else None


def _shadow_delta(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_sample: dict[str, dict[str, list[float]]] = {}
    for record in records:
        sample_id = str(record.get("sample_id") or "")
        slot = str(record.get("observed_slot") or "")
        if sample_id and slot in {"pgo", "legacy"} and record.get("awarded_score") is not None:
            by_sample.setdefault(sample_id, {}).setdefault(slot, []).append(float(record["awarded_score"]))
    pairs: list[dict[str, Any]] = []
    for sample_id, grouped in sorted(by_sample.items()):
        pgo_scores = grouped.get("pgo") or []
        legacy_scores = grouped.get("legacy") or []
        if not pgo_scores or not legacy_scores:
            continue
        pgo_mean = sum(pgo_scores) / len(pgo_scores)
        legacy_mean = sum(legacy_scores) / len(legacy_scores)
        pairs.append(
            {
                "sample_id": sample_id,
                "pgo_mean": _round(pgo_mean),
                "legacy_mean": _round(legacy_mean),
                "pgo_minus_legacy": _round(pgo_mean - legacy_mean),
            }
        )
    deltas = [float(pair["pgo_minus_legacy"]) for pair in pairs if pair.get("pgo_minus_legacy") is not None]
    return {
        "sample_count": len(pairs),
        "mean_abs_pgo_legacy_delta": _mean([abs(delta) for delta in deltas]),
        "mean_signed_pgo_legacy_delta": _mean(deltas),
        "max_abs_pgo_legacy_delta": _round(max(abs(delta) for delta in deltas)) if deltas else None,
        "pairs": pairs,
    }


def _over_credit(records: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, dict[str, Any]] = {}
    for slot in ("pgo", "legacy"):
        scoped = [record for record in records if record.get("observed_slot") == slot]
        report[slot] = {
            "count": len(scoped),
            "awarded_gt_max_count": sum(
                1
                for record in scoped
                if record.get("awarded_score") is not None
                and record.get("max_score") is not None
                and float(record["awarded_score"]) > float(record["max_score"])
            ),
            "official_score_allowed_true_count": sum(1 for record in scoped if record.get("official_score_allowed") is True),
            "high_risk_review_count": sum(1 for record in scoped if record.get("high_risk_review") is True),
        }
    return report


def _record_from_turn(
    *,
    role: str,
    user_id: str,
    expected_slot: str,
    turn: dict[str, Any],
) -> dict[str, Any]:
    event = _case_event(dict(turn.get("result_event") or {}))
    observed_slot = str(event.get("rubric_bank_slot") or "").strip()
    grading_source = str(event.get("grading_source") or "").strip()
    score_authority = str(event.get("score_authority") or "").strip()
    official_score_allowed = event.get("official_score_allowed")
    awarded = event.get("awarded_score")
    maximum = event.get("max_score")
    terminal = turn.get("terminal_event") if isinstance(turn.get("terminal_event"), dict) else {}
    slot_ok = False
    if expected_slot == "pgo":
        slot_ok = (
            observed_slot == "pgo"
            and grading_source == "rubric_scored_pgo"
            and score_authority == PGO_SCORE_AUTHORITY
            and official_score_allowed is False
        )
    elif expected_slot == "legacy":
        slot_ok = (
            observed_slot == "legacy"
            and grading_source != "rubric_scored_pgo"
            and official_score_allowed is False
        )
    return {
        "role": role,
        "authenticated_user_id": user_id,
        "sample_id": str(turn.get("sample_id") or ""),
        "question_id": str(event.get("question_id") or DEFAULT_QUESTION_ID),
        "expected_slot": expected_slot,
        "observed_slot": observed_slot,
        "slot_ok": slot_ok,
        "grading_source": grading_source,
        "score_authority": score_authority,
        "official_score_allowed": official_score_allowed,
        "awarded_score": _round(float(awarded)) if awarded is not None else None,
        "max_score": _round(float(maximum)) if maximum is not None else None,
        "high_risk_review": event.get("high_risk_review"),
        "terminal_type": str(terminal.get("type") or ""),
        "terminal_status": str((terminal.get("metadata") or {}).get("status") or "") if isinstance(terminal, dict) else "",
        "case_event_present": bool(event),
    }


async def _authenticate_role(
    client: Any,
    *,
    role: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    if spec.get("register") and (not spec.get("username") or not spec.get("password") or not spec.get("phone")):
        username, password, phone = _generated_credentials(str(spec.get("username_prefix") or f"{role}_stage5_pgo_live"))
        spec["username"] = username
        spec["password"] = password
        spec["phone"] = phone
    auth = await _remote_authenticate(
        client,
        auth_token=str(spec.get("auth_token") or ""),
        username=str(spec.get("username") or ""),
        password=str(spec.get("password") or ""),
        phone=str(spec.get("phone") or ""),
        register=bool(spec.get("register")),
    )
    if auth.get("ok"):
        return auth
    return {"ok": False, "role": role, "detail": _sanitize_auth_detail(auth)}


async def run_live_traffic_canary(
    *,
    api_base_url: str = "https://test2.yousenjiaoyu.com",
    out_dir: Path | None = None,
    qa_auth_token: str = "",
    qa_username: str = "",
    qa_password: str = "",
    qa_phone: str = "",
    register_qa: bool = False,
    operator_auth_token: str = "",
    operator_username: str = "",
    operator_password: str = "",
    operator_phone: str = "",
    register_operator: bool = False,
    noncohort_auth_token: str = "",
    noncohort_username: str = "",
    noncohort_password: str = "",
    noncohort_phone: str = "",
    register_noncohort: bool = False,
    timeout_seconds: float = 90.0,
    client_factory: Any | None = None,
    connector_factory: Any | None = None,
) -> dict[str, Any]:
    run_id = f"pgo_stage5_live_traffic_canary_{int(time.time())}"
    out = out_dir or DEFAULT_OUTPUT
    out.mkdir(parents=True, exist_ok=True)
    normalized_base = str(api_base_url or "").rstrip("/")
    ws_url = _build_ws_url(normalized_base)
    specs = {
        "qa": {
            "auth_token": qa_auth_token,
            "username": qa_username,
            "password": qa_password,
            "phone": qa_phone,
            "register": register_qa,
            "username_prefix": "qa_stage5_pgo_live",
            "required": True,
        },
        "operator": {
            "auth_token": operator_auth_token,
            "username": operator_username,
            "password": operator_password,
            "phone": operator_phone,
            "register": register_operator,
            "username_prefix": "operator_stage5_pgo_live",
            "required": True,
        },
        "noncohort": {
            "auth_token": noncohort_auth_token,
            "username": noncohort_username,
            "password": noncohort_password,
            "phone": noncohort_phone,
            "register": register_noncohort,
            "username_prefix": "student_stage5_pgo_live",
            "required": True,
        },
    }
    blockers: list[str] = []
    auth_results: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    ws_events: dict[str, list[dict[str, Any]]] = {}
    client_builder = client_factory or httpx.AsyncClient

    async with client_builder(base_url=normalized_base, timeout=timeout_seconds, trust_env=False) as client:
        for role, spec in specs.items():
            if not _has_auth_material(spec):
                blockers.append(f"{role}_auth_material_missing")
                auth_results[role] = {"ok": False, "reason": "auth_material_missing"}
                continue
            auth = await _authenticate_role(client, role=role, spec=spec)
            if not auth.get("ok"):
                blockers.append(f"{role}_auth_failed")
                auth_results[role] = auth
                continue
            user_id = str(auth.get("user_id") or "").strip()
            expected_slot = _expected_slot_for_user(user_id)
            if role in {"qa", "operator"} and expected_slot != "pgo":
                blockers.append(f"{role}_authenticated_user_not_canary")
            if role == "noncohort" and expected_slot != "legacy":
                blockers.append("noncohort_authenticated_user_is_canary")
            auth_results[role] = {
                "ok": True,
                "authenticated_user_id": user_id,
                "expected_slot": expected_slot,
                "created_user": bool(auth.get("created_user")),
                "identity_candidates": list(auth.get("identity_candidates") or []),
            }
            role_events: list[dict[str, Any]] = []
            for sample in DEFAULT_SAMPLES:
                turn = await _run_remote_ws_turn(
                    ws_url=ws_url,
                    token=str(auth.get("token") or ""),
                    sample=sample,
                    timeout_seconds=timeout_seconds,
                    connector_factory=connector_factory,
                )
                role_events.append(turn)
                record = _record_from_turn(
                    role=role,
                    user_id=user_id,
                    expected_slot=expected_slot,
                    turn=turn,
                )
                records.append(record)
                if not record["case_event_present"]:
                    blockers.append(f"{role}_{record['sample_id']}_case_event_missing")
                elif not record["slot_ok"]:
                    blockers.append(f"{role}_{record['sample_id']}_slot_mismatch")
            ws_events[role] = role_events

    role_passed: dict[str, bool] = {}
    for role in ("qa", "operator"):
        scoped = [record for record in records if record.get("role") == role]
        role_passed[role] = bool(scoped) and all(record.get("slot_ok") is True for record in scoped)
    control_scoped = [record for record in records if record.get("role") == "noncohort"]
    noncohort_control_passed = bool(control_scoped) and all(record.get("slot_ok") is True for record in control_scoped)
    if not noncohort_control_passed:
        blockers.append("noncohort_control_not_verified")

    blockers = sorted(set(blockers))
    status = "LIVE_QA_OPERATOR_CANARY_GO" if not blockers else "LIVE_QA_OPERATOR_CANARY_BLOCKED"
    manifest = {
        "run_id": run_id,
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_base_url": normalized_base,
        "ws_url": ws_url,
        "entry": "remote /api/v1/ws authenticated qa/operator PGO bank-slot canary",
        "question_id": DEFAULT_QUESTION_ID,
        "canary_prefixes": list(CANARY_PREFIXES),
        "samples": [{"sample_id": item["sample_id"]} for item in DEFAULT_SAMPLES],
    }
    live_canary = {
        "status": status,
        "auth": auth_results,
        "required_roles_passed": role_passed,
        "noncohort_control_passed": noncohort_control_passed,
        "records": records,
    }
    report = {
        "schema": SCHEMA,
        "status": status,
        "blockers": blockers,
        "manifest": manifest,
        "live_canary": live_canary,
        "shadow_delta": _shadow_delta(records),
        "over_credit": _over_credit(records),
        "score_distribution": _score_distribution(records),
        "safety": {
            "official_score_allowed_true_count": sum(1 for record in records if record.get("official_score_allowed") is True),
            "canonical_write_allowed": False,
            "production_default_flip_allowed": False,
            "global_slot_flip_required": False,
        },
    }
    go_no_go = {
        "status": status,
        "blockers": blockers,
        "required_roles_passed": role_passed,
        "noncohort_control_passed": noncohort_control_passed,
        "shadow_delta_sample_count": report["shadow_delta"]["sample_count"],
        "pgo_record_count": report["score_distribution"]["pgo"]["count"],
        "legacy_record_count": report["score_distribution"]["legacy"]["count"],
    }
    _write_json(out / "manifest.json", manifest)
    _write_json(out / "live_ws_events.json", ws_events)
    _write_json(out / "live_canary_report.json", report)
    _write_json(out / "go_no_go.json", go_no_go)
    return {"out_dir": str(out), "manifest": manifest, "live_canary": live_canary, "go_no_go": go_no_go, **report}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default=os.getenv("TEST2_BASE_URL") or "https://test2.yousenjiaoyu.com")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qa-auth-token", default=os.getenv("DEEPTUTOR_TEST2_QA_AUTH_TOKEN") or os.getenv("DEEPTUTOR_TEST2_COHORT_AUTH_TOKEN") or "")
    parser.add_argument("--qa-username", default=os.getenv("DEEPTUTOR_TEST2_QA_USERNAME") or os.getenv("DEEPTUTOR_TEST2_COHORT_USERNAME") or "")
    parser.add_argument("--qa-password", default=os.getenv("DEEPTUTOR_TEST2_QA_PASSWORD") or os.getenv("DEEPTUTOR_TEST2_COHORT_PASSWORD") or "")
    parser.add_argument("--qa-phone", default=os.getenv("DEEPTUTOR_TEST2_QA_PHONE") or os.getenv("DEEPTUTOR_TEST2_COHORT_PHONE") or "")
    parser.add_argument("--register-qa", action="store_true")
    parser.add_argument("--operator-auth-token", default=os.getenv("DEEPTUTOR_TEST2_OPERATOR_AUTH_TOKEN") or "")
    parser.add_argument("--operator-username", default=os.getenv("DEEPTUTOR_TEST2_OPERATOR_USERNAME") or "")
    parser.add_argument("--operator-password", default=os.getenv("DEEPTUTOR_TEST2_OPERATOR_PASSWORD") or "")
    parser.add_argument("--operator-phone", default=os.getenv("DEEPTUTOR_TEST2_OPERATOR_PHONE") or "")
    parser.add_argument("--register-operator", action="store_true")
    parser.add_argument("--noncohort-auth-token", default=os.getenv("DEEPTUTOR_TEST2_NONCOHORT_AUTH_TOKEN") or "")
    parser.add_argument("--noncohort-username", default=os.getenv("DEEPTUTOR_TEST2_NONCOHORT_USERNAME") or "")
    parser.add_argument("--noncohort-password", default=os.getenv("DEEPTUTOR_TEST2_NONCOHORT_PASSWORD") or "")
    parser.add_argument("--noncohort-phone", default=os.getenv("DEEPTUTOR_TEST2_NONCOHORT_PHONE") or "")
    parser.add_argument("--register-noncohort", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args()

    result = asyncio.run(
        run_live_traffic_canary(
            api_base_url=args.api_base_url,
            out_dir=args.out_dir,
            qa_auth_token=args.qa_auth_token,
            qa_username=args.qa_username,
            qa_password=args.qa_password,
            qa_phone=args.qa_phone,
            register_qa=args.register_qa,
            operator_auth_token=args.operator_auth_token,
            operator_username=args.operator_username,
            operator_password=args.operator_password,
            operator_phone=args.operator_phone,
            register_operator=args.register_operator,
            noncohort_auth_token=args.noncohort_auth_token,
            noncohort_username=args.noncohort_username,
            noncohort_password=args.noncohort_password,
            noncohort_phone=args.noncohort_phone,
            register_noncohort=args.register_noncohort,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(json.dumps(result["go_no_go"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["go_no_go"]["status"] == "LIVE_QA_OPERATOR_CANARY_GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
