#!/usr/bin/env python3
"""L3 QA/operator cohort A/B for the Nexus/KnowQL/GBrain loop.

This runner upgrades L2's same-user scripted experiment into a cohort-shaped
test2 run: each subject is a distinct QA/operator user, randomized to A0/B1/B2,
and measured through the real `/api/v1/ws` entry. It still does not claim real
production learner efficacy unless a separate human/production cohort source is
provided and authorized.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

import httpx


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import run_luban_knowql_nexus_l2_learning_ab as l2


ARTIFACT_ROOT = REPO / "artifacts" / "luban_grading_artifacts"


class CohortSubject(NamedTuple):
    subject_index: int
    subject_id: str
    arm: str
    scenario_index: int
    username: str
    password: str
    phone: str


def build_cohort_schedule(
    *,
    subjects_per_arm: int,
    seed: int | None = None,
    username_prefix: str = "qa_pgo_l3_ab",
    run_stamp: str = "",
) -> list[CohortSubject]:
    total_per_arm = max(1, int(subjects_per_arm or 1))
    stamp = _safe_slug(run_stamp or str(seed or "local"))
    subjects: list[CohortSubject] = []
    subject_index = 0
    for arm in l2.LEARNING_ARMS:
        for offset in range(total_per_arm):
            subject_index += 1
            scenario_index = (subject_index - 1) % len(l2.DEFAULT_SCENARIOS)
            username = f"{username_prefix}_{stamp}_{subject_index:03d}_{arm.lower()}"
            subjects.append(
                CohortSubject(
                    subject_index=subject_index,
                    subject_id=f"l3s{subject_index:03d}_{arm.lower()}_{scenario_index + 1}",
                    arm=arm,
                    scenario_index=scenario_index,
                    username=username,
                    password=f"L3Ab{subject_index:03d}{abs(hash(username)) % 1000:03d}",
                    phone=_phone_for_username(username),
                )
            )
    rng = random.Random(seed)
    rng.shuffle(subjects)
    return subjects


def build_l3_preregistration(
    *,
    scenario_count: int,
    subjects_per_arm: int,
    min_subjects_per_arm: int,
    cohort_mode: str,
    min_b2_outcome_miss_reduction_lift: float,
    max_b2_p95_latency_delta_pct: float,
    max_b2_payload_delta_pct: float,
    max_b3_p95_ms: float = 50.0,
) -> dict[str, Any]:
    normalized_mode = str(cohort_mode or "authorized_qa_operator").strip().lower()
    population = (
        "production_learner_cohort"
        if normalized_mode == "production_learner"
        else "authorized_qa_operator_test2_cohort"
    )
    return {
        "schema_version": "knowql_nexus_l3_cohort_preregistration.v1",
        "experiment": "Nexus/KnowQL/GBrain real-entry cohort learning A/B",
        "analysis_unit": "distinct_learner_subject_initial_retest_pair",
        "population": population,
        "cohort_mode": normalized_mode,
        "minimum_preregistered_scenarios": int(scenario_count or 0),
        "subjects_per_arm": int(subjects_per_arm or 0),
        "minimum_subjects_per_arm": int(min_subjects_per_arm or subjects_per_arm or 0),
        "sample_manifest_hash": l2.sample_manifest_hash(),
        "primary_effect_metric": "b2_real_cohort_outcome_miss_reduction_lift_vs_b1",
        "secondary_effect_metrics": [
            "b2_delta_lift_vs_a0",
            "b2_delta_lift_vs_b1",
            "b2_p95_latency_delta_pct_vs_b1",
            "b2_payload_delta_pct_vs_b1",
        ],
        "safety_guardrails": [
            "distinct_learner_per_subject == true",
            "canonical_truth_write_count == 0",
            "official_score_write_count == 0",
            "unsafe_write_signal_count == 0",
            "a0_pgo_shadow_present_count == 0",
            "b1_pgo_shadow_present_count == 0",
            "b2_pgo_shadow_effective_count == B2 turn_count",
            "b2_knowql_runtime_consumed_count == B2 turn_count",
            "b2_g3_preview_readback_count == B2 turn_count",
            "b2_nba_intervention_applied_count == B2 completed_subjects",
            f"b2_p95_latency_delta_pct_vs_b1 <= {float(max_b2_p95_latency_delta_pct)}",
            f"b2_payload_delta_pct_vs_b1 <= {float(max_b2_payload_delta_pct)}",
            f"B3 p95 latency <= {float(max_b3_p95_ms)} ms",
        ],
        "minimum_effect_thresholds": {
            "b2_real_cohort_outcome_miss_reduction_lift_vs_b1": float(min_b2_outcome_miss_reduction_lift),
        },
        "human_learner_claim_allowed": normalized_mode == "production_learner",
        "production_learner_claim_allowed": normalized_mode == "production_learner",
        "canonical_truth_write_allowed": False,
        "official_score_write_allowed": False,
        "decision_rule": {
            "go_requires": ["L3_SAFETY_GO", "L3_EFFECT_POSITIVE"],
            "no_go_if": [
                "duplicate learner identity appears across subjects",
                "any safety guardrail fails",
                "any arm has subjects < minimum_subjects_per_arm",
                "B2 PGO/KnowQL/G3/NBA readback is missing",
            ],
        },
    }


def summarize_l3_rows(
    rows: list[dict[str, Any]],
    *,
    b3_rows: list[dict[str, Any]],
    min_subjects_per_arm: int,
    min_b2_outcome_miss_reduction_lift: float,
    max_b2_p95_latency_delta_pct: float = 250.0,
    max_b2_payload_delta_pct: float = 50.0,
    max_b3_p95_ms: float = 50.0,
    cohort_mode: str = "authorized_qa_operator",
) -> dict[str, Any]:
    l2_summary = l2.summarize_l2_rows(
        rows,
        b3_rows=b3_rows,
        min_loops=min_subjects_per_arm,
        min_b2_delta_lift=0.0,
        min_b2_outcome_miss_reduction_lift=min_b2_outcome_miss_reduction_lift,
        max_b2_p95_latency_delta_pct=max_b2_p95_latency_delta_pct,
        max_b2_payload_delta_pct=max_b2_payload_delta_pct,
        max_b3_p95_ms=max_b3_p95_ms,
    )
    subjects_by_arm = {
        arm: len({str(row.get("subject_id") or "") for row in rows if row.get("arm") == arm and row.get("subject_id")})
        for arm in l2.LEARNING_ARMS
    }
    subject_to_learners: dict[str, set[str]] = {}
    learner_to_subjects: dict[str, set[str]] = {}
    for row in rows:
        subject_id = str(row.get("subject_id") or "").strip()
        username = str(row.get("learner_username") or "").strip()
        if not subject_id or not username:
            continue
        subject_to_learners.setdefault(subject_id, set()).add(username)
        learner_to_subjects.setdefault(username, set()).add(subject_id)
    duplicate_learner_count = sum(1 for subjects in learner_to_subjects.values() if len(subjects) > 1)
    subject_identity_split_count = sum(1 for learners in subject_to_learners.values() if len(learners) > 1)
    distinct_learner_per_subject = duplicate_learner_count == 0 and subject_identity_split_count == 0
    l3_reasons = list(l2_summary["decision"].get("reasons") or [])
    if not distinct_learner_per_subject:
        l3_reasons.append("duplicate_learner_detected")
    for arm, count in subjects_by_arm.items():
        if count < int(min_subjects_per_arm or 0):
            l3_reasons.append(f"{arm.lower()}_insufficient_subject_count")
    b2_lift = float(l2_summary["comparison"].get("b2_outcome_miss_reduction_lift_vs_b1") or 0.0)
    if float(l2_summary["comparison"].get("b2_p95_latency_delta_pct_vs_b1") or 0.0) > float(max_b2_p95_latency_delta_pct):
        l3_reasons.append("b2_p95_latency_delta_exceeded")
    if float(l2_summary["comparison"].get("b2_payload_delta_pct_vs_b1") or 0.0) > float(max_b2_payload_delta_pct):
        l3_reasons.append("b2_payload_delta_exceeded")

    safety_status = "L3_SAFETY_NO_GO" if l3_reasons else "L3_SAFETY_GO"
    effect_status = (
        "L3_EFFECT_POSITIVE"
        if safety_status == "L3_SAFETY_GO" and b2_lift >= float(min_b2_outcome_miss_reduction_lift)
        else ("L3_EFFECT_NOT_EVALUABLE" if safety_status != "L3_SAFETY_GO" else "L3_EFFECT_NEUTRAL_OR_NEGATIVE")
    )
    status = "L3_COHORT_AB_GO" if safety_status == "L3_SAFETY_GO" and effect_status == "L3_EFFECT_POSITIVE" else "L3_COHORT_AB_NO_GO"
    l2_summary["cohort"] = {
        "cohort_mode": str(cohort_mode or "authorized_qa_operator").strip().lower(),
        "subjects_by_arm": subjects_by_arm,
        "subject_count": len(subject_to_learners),
        "learner_count": len(learner_to_subjects),
        "distinct_learner_per_subject": distinct_learner_per_subject,
        "duplicate_learner_count": duplicate_learner_count,
        "subject_identity_split_count": subject_identity_split_count,
        "human_learner_claim_allowed": False,
        "production_learner_claim_allowed": False,
    }
    l2_summary["comparison"]["b2_real_cohort_outcome_miss_reduction_lift_vs_b1"] = b2_lift
    l2_summary["comparison"]["min_subjects_per_arm"] = int(min_subjects_per_arm or 0)
    l2_summary["decision"] = {
        "status": status,
        "safety_status": safety_status,
        "effect_status": effect_status,
        "reasons": l3_reasons,
        "canonical_truth_written": l2_summary["safety"]["canonical_truth_write_count"] > 0,
        "official_score_written": l2_summary["safety"]["official_score_write_count"] > 0,
        "human_learner_claim_allowed": False,
        "production_learner_claim_allowed": False,
    }
    return l2_summary


async def run_l3_cohort_ab(
    *,
    api_base_url: str,
    subjects_per_arm: int,
    min_subjects_per_arm: int,
    timeout_seconds: float,
    out_dir: Path,
    seed: int | None,
    b3_iterations: int,
    inter_turn_delay_seconds: float,
    username_prefix: str,
    cohort_mode: str,
    min_b2_outcome_miss_reduction_lift: float,
    max_b2_p95_latency_delta_pct: float,
    max_b2_payload_delta_pct: float,
    max_b3_p95_ms: float,
    auth_retries: int = 3,
    auth_retry_delay_seconds: float = 2.0,
) -> dict[str, Any]:
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"knowql_nexus_l3_cohort_ab_{run_stamp}"
    ws_url = l2.build_ws_url(api_base_url)
    schedule = build_cohort_schedule(
        subjects_per_arm=subjects_per_arm,
        seed=seed,
        username_prefix=username_prefix,
        run_stamp=run_stamp,
    )
    rows: list[dict[str, Any]] = []
    delay_seconds = max(0.0, float(inter_turn_delay_seconds or 0.0))
    for order_index, subject in enumerate(schedule, start=1):
        auth = await resolve_subject_token(
            api_base_url=api_base_url,
            subject=subject,
            retries=auth_retries,
            retry_delay_seconds=auth_retry_delay_seconds,
        )
        if not auth.get("ok"):
            rows.append(_auth_blocked_row(subject, auth, order_index=order_index, cohort_mode=cohort_mode))
            if delay_seconds and order_index < len(schedule):
                await asyncio.sleep(delay_seconds)
            continue
        await _run_subject(
            subject=subject,
            order_index=order_index,
            run_id=run_id,
            ws_url=ws_url,
            auth=auth,
            timeout_seconds=timeout_seconds,
            rows=rows,
            inter_turn_delay_seconds=delay_seconds,
            cohort_mode=cohort_mode,
        )
        if delay_seconds and order_index < len(schedule):
            await asyncio.sleep(delay_seconds)

    b3_rows = l2.run_b3_microbenchmark(iterations=b3_iterations)
    summary = summarize_l3_rows(
        rows,
        b3_rows=b3_rows,
        min_subjects_per_arm=min_subjects_per_arm,
        min_b2_outcome_miss_reduction_lift=min_b2_outcome_miss_reduction_lift,
        max_b2_p95_latency_delta_pct=max_b2_p95_latency_delta_pct,
        max_b2_payload_delta_pct=max_b2_payload_delta_pct,
        max_b3_p95_ms=max_b3_p95_ms,
        cohort_mode=cohort_mode,
    )
    preregistration = build_l3_preregistration(
        scenario_count=len(l2.DEFAULT_SCENARIOS),
        subjects_per_arm=subjects_per_arm,
        min_subjects_per_arm=min_subjects_per_arm,
        cohort_mode=cohort_mode,
        min_b2_outcome_miss_reduction_lift=min_b2_outcome_miss_reduction_lift,
        max_b2_p95_latency_delta_pct=max_b2_p95_latency_delta_pct,
        max_b2_payload_delta_pct=max_b2_payload_delta_pct,
        max_b3_p95_ms=max_b3_p95_ms,
    )
    manifest = {
        "run_id": run_id,
        "mode": "live-cohort-learning-ab",
        "entry": "remote /api/v1/ws with distinct QA/operator learner per subject",
        "api_base_url": str(api_base_url or "").rstrip("/"),
        "ws_url": ws_url,
        "subjects_per_arm": subjects_per_arm,
        "min_subjects_per_arm": min_subjects_per_arm,
        "seed": seed,
        "cohort_mode": cohort_mode,
        "inter_turn_delay_seconds": delay_seconds,
        "auth_retries": int(auth_retries or 0),
        "auth_retry_delay_seconds": max(0.0, float(auth_retry_delay_seconds or 0.0)),
        "sample_manifest_hash": l2.sample_manifest_hash(),
        "sample_manifest_public": l2.scenario_manifest(include_answers=False),
        "preregistration": preregistration,
        "arms": {
            **{arm: dict(definition) for arm, definition in l2.ARM_DEFINITIONS.items()},
            "B3": {
                "runtime_mode": "knowql_microbenchmark",
                "label": "KnowQL retrieve_rubric microbenchmark only; excluded from learning effect",
                "learning_effect_eligible": False,
            },
        },
        "remote_write_requested": False,
        "production_default_flip_requested": False,
        "canonical_truth_write_allowed": False,
        "official_score_write_allowed": False,
        "human_learner_claim_allowed": False,
        "production_learner_claim_allowed": False,
        "exit_code_intent": {"go": 0, "no_go": 1, "auth_blocked": 2},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    l2._write_json(out_dir / "manifest.json", manifest)
    l2._write_jsonl(out_dir / "raw_learning_rows.jsonl", rows)
    l2._write_jsonl(out_dir / "raw_b3_microbenchmark_rows.jsonl", b3_rows)
    l2._write_json(out_dir / "summary.json", summary)
    _write_markdown(out_dir / "FINDING_knowql_nexus_l3_cohort_ab.md", manifest=manifest, summary=summary)
    return {"out_dir": str(out_dir), "manifest": manifest, "summary": summary}


def extract_token_from_auth_payload(payload: dict[str, Any]) -> str:
    for key in ("token", "access_token"):
        token = str(payload.get(key) or "").strip() if isinstance(payload, dict) else ""
        if token:
            return token
    return ""


def extract_user_id_from_auth_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("user_id", "uid", "sub"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    user = payload.get("user")
    if isinstance(user, dict):
        for key in ("user_id", "uid", "sub", "id"):
            value = str(user.get(key) or "").strip()
            if value:
                return value
    return ""


async def resolve_subject_token(
    *,
    api_base_url: str,
    subject: CohortSubject,
    retries: int,
    retry_delay_seconds: float,
) -> dict[str, Any]:
    attempts = max(1, int(retries or 1))
    last: dict[str, Any] = {"ok": False, "reason": "auth_not_attempted"}
    async with httpx.AsyncClient(base_url=str(api_base_url or "").rstrip("/"), timeout=30.0, trust_env=False) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = await client.post(
                    "/api/v1/auth/register",
                    json={
                        "username": subject.username,
                        "password": subject.password,
                        "phone": subject.phone,
                    },
                )
                payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                token = extract_token_from_auth_payload(payload)
                auth_user_id = extract_user_id_from_auth_payload(payload)
                if response.status_code in {200, 201} and token:
                    return {
                        "ok": True,
                        "token": token,
                        "auth_mode": "register_token",
                        "auth_user_id": auth_user_id,
                        "register_status_code": response.status_code,
                        "attempt": attempt,
                    }
                login = await client.post(
                    "/api/v1/auth/login",
                    json={"username": subject.username, "password": subject.password},
                )
                login_payload = login.json() if login.headers.get("content-type", "").startswith("application/json") else {}
                token = extract_token_from_auth_payload(login_payload)
                login_user_id = extract_user_id_from_auth_payload(login_payload)
                if login.status_code == 200 and token:
                    return {
                        "ok": True,
                        "token": token,
                        "auth_mode": "login",
                        "auth_user_id": login_user_id or auth_user_id,
                        "register_status_code": response.status_code,
                        "login_status_code": login.status_code,
                        "attempt": attempt,
                    }
                last = {
                    "ok": False,
                    "reason": "login_failed",
                    "auth_user_id": login_user_id or auth_user_id,
                    "register_status_code": response.status_code,
                    "login_status_code": login.status_code,
                    "attempt": attempt,
                }
            except Exception as exc:  # noqa: BLE001 - auth failure is row-level evidence
                last = {"ok": False, "reason": "auth_exception", "error": str(exc)[:300], "attempt": attempt}
            if attempt < attempts and retry_delay_seconds:
                await asyncio.sleep(max(0.0, float(retry_delay_seconds or 0.0)))
    return last


async def _run_subject(
    *,
    subject: CohortSubject,
    order_index: int,
    run_id: str,
    ws_url: str,
    auth: dict[str, Any],
    timeout_seconds: float,
    rows: list[dict[str, Any]],
    inter_turn_delay_seconds: float,
    cohort_mode: str,
) -> None:
    token = str(auth.get("token") or "")
    scenario = l2.DEFAULT_SCENARIOS[subject.scenario_index]
    initial_frame = l2.build_ws_frame(
        scenario,
        arm=subject.arm,
        run_id=run_id,
        loop_index=subject.subject_index,
        phase="initial",
        content=scenario.initial_answer,
    )
    initial = await l2._run_one_ws_turn(
        ws_url=ws_url,
        token=token,
        frame=initial_frame,
        arm=subject.arm,
        loop_index=subject.subject_index,
        turn_phase="initial",
        scenario=scenario,
        timeout_seconds=timeout_seconds,
        nba_intervention_applied=False,
    )
    _attach_subject_fields(initial, subject, order_index=order_index, auth=auth, cohort_mode=cohort_mode)
    rows.append(initial)
    metadata = initial.get("metadata") if isinstance(initial.get("metadata"), dict) else {}
    g3 = metadata.get("pgo_grading_to_brain") if isinstance(metadata.get("pgo_grading_to_brain"), dict) else {}
    nba_applied = subject.arm == "B2" and isinstance(g3.get("next_best_action"), dict)
    retest_answer = scenario.targeted_retest_answer if nba_applied else scenario.baseline_retest_answer
    if inter_turn_delay_seconds:
        await asyncio.sleep(max(0.0, float(inter_turn_delay_seconds or 0.0)))
    retest_frame = l2.build_ws_frame(
        scenario,
        arm=subject.arm,
        run_id=run_id,
        loop_index=subject.subject_index,
        phase="retest",
        content=retest_answer,
    )
    retest = await l2._run_one_ws_turn(
        ws_url=ws_url,
        token=token,
        frame=retest_frame,
        arm=subject.arm,
        loop_index=subject.subject_index,
        turn_phase="retest",
        scenario=scenario,
        timeout_seconds=timeout_seconds,
        nba_intervention_applied=bool(nba_applied),
    )
    _attach_subject_fields(retest, subject, order_index=order_index, auth=auth, cohort_mode=cohort_mode)
    retest["nba_intervention_applied"] = bool(nba_applied)
    rows.append(retest)


def _attach_subject_fields(
    row: dict[str, Any],
    subject: CohortSubject,
    *,
    order_index: int,
    auth: dict[str, Any],
    cohort_mode: str,
) -> None:
    row["subject_id"] = subject.subject_id
    row["subject_index"] = subject.subject_index
    row["learner_username"] = subject.username
    row["order_index"] = order_index
    row["cohort_mode"] = str(cohort_mode or "authorized_qa_operator").strip().lower()
    row["auth_mode"] = str(auth.get("auth_mode") or "").strip()
    row["auth_attempt"] = auth.get("attempt")
    row["auth_user_id"] = str(auth.get("auth_user_id") or "").strip()


def _auth_blocked_row(
    subject: CohortSubject,
    auth: dict[str, Any],
    *,
    order_index: int,
    cohort_mode: str,
) -> dict[str, Any]:
    return {
        "arm": subject.arm,
        "turn_phase": "auth",
        "loop_index": subject.subject_index,
        "scenario_id": l2.DEFAULT_SCENARIOS[subject.scenario_index].scenario_id,
        "question_id": l2.DEFAULT_SCENARIOS[subject.scenario_index].question_id,
        "subject_id": subject.subject_id,
        "subject_index": subject.subject_index,
        "learner_username": subject.username,
        "order_index": order_index,
        "cohort_mode": str(cohort_mode or "authorized_qa_operator").strip().lower(),
        "auth_mode": str(auth.get("auth_mode") or "").strip(),
        "auth_attempt": auth.get("attempt"),
        "auth_user_id": str(auth.get("auth_user_id") or "").strip(),
        "register_status_code": auth.get("register_status_code"),
        "login_status_code": auth.get("login_status_code"),
        "ok": False,
        "error": str(auth.get("reason") or "auth_blocked"),
        "metadata": {},
        "nba_intervention_applied": False,
        "outcome_score_ratio": None,
        "outcome_miss_count": None,
    }


def _write_markdown(path: Path, *, manifest: dict[str, Any], summary: dict[str, Any]) -> None:
    decision = summary["decision"]
    comparison = summary["comparison"]
    cohort = summary["cohort"]
    lines = [
        "# KnowQL Nexus L3 Cohort A/B",
        "",
        f"- status: `{decision['status']}`",
        f"- safety status: `{decision['safety_status']}`",
        f"- effect status: `{decision['effect_status']}`",
        f"- api_base_url: `{manifest['api_base_url']}`",
        f"- cohort mode: `{manifest['cohort_mode']}`",
        f"- subjects per arm: `{manifest['subjects_per_arm']}`",
        f"- min subjects per arm: `{manifest['min_subjects_per_arm']}`",
        f"- subjects by arm: `{json.dumps(cohort['subjects_by_arm'], ensure_ascii=False, sort_keys=True)}`",
        f"- distinct learner per subject: `{cohort['distinct_learner_per_subject']}`",
        f"- B2 real-cohort outcome miss reduction lift vs B1: `{comparison['b2_real_cohort_outcome_miss_reduction_lift_vs_b1']}`",
        f"- B2 delta lift vs B1: `{comparison['b2_delta_lift_vs_b1']}`",
        f"- B2 p95 latency delta vs B1: `{comparison['b2_p95_latency_delta_pct_vs_b1']}`",
        f"- B2 payload delta vs B1: `{comparison['b2_payload_delta_pct_vs_b1']}`",
        f"- B3 p95 latency ms: `{summary['b3_microbenchmark']['p95_latency_ms']}`",
        f"- canonical truth writes: `{summary['safety']['canonical_truth_write_count']}`",
        f"- official score writes: `{summary['safety']['official_score_write_count']}`",
        f"- production learner claim allowed: `{decision['production_learner_claim_allowed']}`",
        "",
        "## Decision Reasons",
        "",
    ]
    reasons = list(decision.get("reasons") or [])
    lines.extend([f"- `{reason}`" for reason in reasons] or ["- none"])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _phone_for_username(username: str) -> str:
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return "137" + str(int(digest[:8], 16) % 100000000).zfill(8)


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value or "").strip())[:32] or "local"


def _default_out_dir() -> Path:
    return ARTIFACT_ROOT / f"knowql_nexus_l3_cohort_ab_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


async def _main_async(args: argparse.Namespace) -> int:
    result = await run_l3_cohort_ab(
        api_base_url=args.api_base_url,
        subjects_per_arm=args.subjects_per_arm,
        min_subjects_per_arm=args.min_subjects_per_arm or args.subjects_per_arm,
        timeout_seconds=args.timeout_seconds,
        out_dir=Path(args.out_dir) if args.out_dir else _default_out_dir(),
        seed=args.seed,
        b3_iterations=args.b3_iterations,
        inter_turn_delay_seconds=args.inter_turn_delay_seconds,
        username_prefix=args.username_prefix,
        cohort_mode=args.cohort_mode,
        min_b2_outcome_miss_reduction_lift=args.min_b2_outcome_miss_reduction_lift,
        max_b2_p95_latency_delta_pct=args.max_b2_p95_latency_delta_pct,
        max_b2_payload_delta_pct=args.max_b2_payload_delta_pct,
        max_b3_p95_ms=args.max_b3_p95_ms,
        auth_retries=args.auth_retries,
        auth_retry_delay_seconds=args.auth_retry_delay_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["summary"]["decision"]["status"] == "L3_COHORT_AB_GO" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default=os.environ.get("DEEPTUTOR_L3_AB_API_BASE_URL", "https://test2.yousenjiaoyu.com"))
    parser.add_argument("--subjects-per-arm", type=int, default=5)
    parser.add_argument("--min-subjects-per-arm", type=int, default=0)
    parser.add_argument("--username-prefix", default="qa_pgo_l3_ab")
    parser.add_argument("--cohort-mode", choices=("authorized_qa_operator", "production_learner"), default="authorized_qa_operator")
    parser.add_argument("--seed", type=int, default=20260615)
    parser.add_argument("--inter-turn-delay-seconds", type=float, default=8.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--min-b2-outcome-miss-reduction-lift", type=float, default=1.0)
    parser.add_argument("--max-b2-p95-latency-delta-pct", type=float, default=250.0)
    parser.add_argument("--max-b2-payload-delta-pct", type=float, default=50.0)
    parser.add_argument("--max-b3-p95-ms", type=float, default=50.0)
    parser.add_argument("--b3-iterations", type=int, default=30)
    parser.add_argument("--auth-retries", type=int, default=3)
    parser.add_argument("--auth-retry-delay-seconds", type=float, default=2.0)
    parser.add_argument("--out-dir", default="")
    return parser


def main() -> int:
    return asyncio.run(_main_async(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
