#!/usr/bin/env python3
"""L1 live shadow A/B for PGO KnowQL performance.

The runner compares the existing `/api/v1/ws` deep_question grading path (arm A)
with the same path plus PGO shadow enabled (arm B). It measures latency, result
payload size, success rate, PGO fail-open rate, and safety invariants.

It never flips remote config, never writes official scores, and treats canonical
truth writes as a hard NO-GO signal.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlparse, urlunparse

import httpx
import websockets


REPO = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO / "artifacts" / "luban_grading_artifacts"
REMOTE_COHORT_PREFIXES = ("qa_", "operator_")


class Sample(NamedTuple):
    sample_id: str
    question_id: str
    question: str
    correct_answer: str
    student_answer: str


class RunItem(NamedTuple):
    pair_index: int
    arm: str


DEFAULT_SAMPLES: tuple[Sample, ...] = (
    Sample(
        sample_id="pgo_known_xw2015_e0",
        question_id="2015::EXAM_XW2015_CASE_1::E0",
        question="施工总进度计划还缺少哪些内容？",
        correct_answer="施工总进度计划表，开竣工日期及工期一览表。",
        student_answer="施工总进度计划表，开竣工日期及工期一览表。",
    ),
)


def build_run_schedule(*, pairs: int, order_mode: str = "alternating", seed: int | None = None) -> list[RunItem]:
    schedule: list[RunItem] = []
    normalized = str(order_mode or "alternating").strip().lower()
    rng = random.Random(seed)
    for pair_index in range(1, max(1, int(pairs or 1)) + 1):
        if normalized == "ab":
            order = ["A", "B"]
        elif normalized == "ba":
            order = ["B", "A"]
        elif normalized == "randomized":
            order = ["A", "B"]
            rng.shuffle(order)
        else:
            order = ["A", "B"] if pair_index % 2 == 1 else ["B", "A"]
        schedule.extend(RunItem(pair_index=pair_index, arm=arm) for arm in order)
    return schedule


def build_ws_url(api_base_url: str) -> str:
    parsed = urlparse(str(api_base_url or "").rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/") + "/api/v1/ws"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def build_ws_frame(sample: Sample, *, arm: str, run_id: str, pair_index: int) -> dict[str, Any]:
    normalized_arm = str(arm or "").strip().upper()
    client_turn_id = f"{run_id}:p{pair_index:02d}:{normalized_arm}"
    config: dict[str, Any] = {
        "client_turn_id": client_turn_id,
        "followup_question_context": {
            "question_id": sample.question_id,
            "question_type": "case",
            "question": sample.question,
            "correct_answer": sample.correct_answer,
        },
    }
    if normalized_arm == "B":
        config["grading_engine_pgo_shadow"] = True
    return {
        "type": "start_turn",
        "content": sample.student_answer,
        "capability": "deep_question",
        "language": "zh",
        "config": config,
    }


def summarize_ab_rows(
    rows: list[dict[str, Any]],
    *,
    latency_degradation_threshold: float = 0.25,
    max_b_fail_open_rate: float = 0.05,
    min_b_shadow_rate: float = 1.0,
    min_pairs: int = 1,
) -> dict[str, Any]:
    arms = {arm: _arm_stats([row for row in rows if row.get("arm") == arm]) for arm in ("A", "B")}
    a = arms["A"]
    b = arms["B"]
    a_p95 = float(a.get("p95_latency_ms") or 0.0)
    b_p95 = float(b.get("p95_latency_ms") or 0.0)
    latency_delta_pct = round((b_p95 - a_p95) / a_p95, 6) if a_p95 > 0 else None
    payload_delta = int((b.get("avg_payload_bytes") or 0) - (a.get("avg_payload_bytes") or 0))
    safety = _safety_summary(rows)
    b_total = max(1, int(b.get("count") or 0))
    b_fail_open_rate = safety["b_fail_open_count"] / b_total
    b_shadow_rate = safety["b_pgo_shadow_present_count"] / b_total
    b_effective_shadow_rate = safety["b_pgo_shadow_effective_count"] / b_total
    b_knowql_runtime_rate = safety["b_knowql_runtime_consumed_count"] / b_total
    completed_pairs = _completed_pairs(rows)

    reasons: list[str] = []
    if safety["canonical_truth_write_count"]:
        reasons.append("canonical_truth_write_detected")
    if safety["official_score_write_count"]:
        reasons.append("official_score_write_detected")
    if safety["unsafe_write_signal_count"]:
        reasons.append("unsafe_write_signal_detected")
    if safety["a_pgo_shadow_present_count"]:
        reasons.append("a_pgo_shadow_present")
    if latency_delta_pct is None:
        reasons.append("missing_latency_baseline")
    elif latency_delta_pct > float(latency_degradation_threshold):
        reasons.append("p95_latency_regression")
    if int(a.get("count") or 0) > 0 and float(a.get("success_rate") or 0.0) <= 0.0:
        reasons.append("a_success_rate_zero")
    if int(b.get("count") or 0) > 0 and float(b.get("success_rate") or 0.0) <= 0.0:
        reasons.append("b_success_rate_zero")
    if b_fail_open_rate > float(max_b_fail_open_rate):
        reasons.append("b_fail_open_rate_too_high")
    if b_shadow_rate < float(min_b_shadow_rate):
        reasons.append("b_pgo_shadow_absent")
    if b_effective_shadow_rate < float(min_b_shadow_rate):
        reasons.append("b_pgo_shadow_not_effective")
    if b_knowql_runtime_rate < float(min_b_shadow_rate):
        reasons.append("b_knowql_not_runtime_consumed")
    if completed_pairs < int(min_pairs or 0):
        reasons.append("insufficient_pair_count")
    if b.get("success_rate", 0.0) < a.get("success_rate", 0.0) - 0.05:
        reasons.append("b_success_rate_regression")

    return {
        "arms": arms,
        "comparison": {
            "p95_latency_delta_ms": round(b_p95 - a_p95, 3),
            "p95_latency_delta_pct": latency_delta_pct,
            "payload_bytes_delta": payload_delta,
            "completed_pairs": completed_pairs,
            "min_pairs": int(min_pairs or 0),
            "b_fail_open_rate": round(b_fail_open_rate, 6),
            "b_pgo_shadow_present_rate": round(b_shadow_rate, 6),
            "b_pgo_shadow_effective_rate": round(b_effective_shadow_rate, 6),
            "b_knowql_runtime_consumed_rate": round(b_knowql_runtime_rate, 6),
        },
        "safety": safety,
        "decision": {
            "status": "L1_SHADOW_AB_NO_GO" if reasons else "L1_SHADOW_AB_GO",
            "reasons": reasons,
            "latency_degradation_threshold": latency_degradation_threshold,
            "max_b_fail_open_rate": max_b_fail_open_rate,
            "min_b_shadow_rate": min_b_shadow_rate,
            "canonical_truth_written": safety["canonical_truth_write_count"] > 0,
            "official_score_written": safety["official_score_write_count"] > 0,
        },
    }


def summarize_activation_probe(rows: list[dict[str, Any]]) -> dict[str, Any]:
    arms = {arm: _arm_stats([row for row in rows if row.get("arm") == arm]) for arm in ("A", "B")}
    safety = _safety_summary(rows)
    b_total = max(1, int(arms["B"].get("count") or 0))
    b_effective_shadow_rate = safety["b_pgo_shadow_effective_count"] / b_total
    b_knowql_runtime_rate = safety["b_knowql_runtime_consumed_count"] / b_total

    reasons: list[str] = []
    if int(arms["B"].get("count") or 0) <= 0:
        reasons.append("b_probe_missing")
    if float(arms["B"].get("success_rate") or 0.0) <= 0.0:
        reasons.append("b_success_rate_zero")
    if safety["canonical_truth_write_count"]:
        reasons.append("canonical_truth_write_detected")
    if safety["official_score_write_count"]:
        reasons.append("official_score_write_detected")
    if safety["unsafe_write_signal_count"]:
        reasons.append("unsafe_write_signal_detected")
    if b_effective_shadow_rate < 1.0:
        reasons.append("b_pgo_shadow_not_effective")
    if b_knowql_runtime_rate < 1.0:
        reasons.append("b_knowql_not_runtime_consumed")

    return {
        "arms": arms,
        "comparison": {
            "b_pgo_shadow_effective_rate": round(b_effective_shadow_rate, 6),
            "b_knowql_runtime_consumed_rate": round(b_knowql_runtime_rate, 6),
        },
        "safety": safety,
        "decision": {
            "status": "L1_ACTIVATION_BLOCKED" if reasons else "L1_ACTIVATION_READY",
            "reasons": reasons,
            "canonical_truth_written": safety["canonical_truth_write_count"] > 0,
            "official_score_written": safety["official_score_write_count"] > 0,
        },
    }


def _arm_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [float(row.get("duration_ms") or 0.0) for row in rows if row.get("duration_ms") is not None]
    payloads = [int(row.get("payload_bytes") or 0) for row in rows if row.get("payload_bytes") is not None]
    ok_count = sum(1 for row in rows if row.get("ok") is True)
    count = len(rows)
    return {
        "count": count,
        "ok_count": ok_count,
        "error_count": count - ok_count,
        "success_rate": round(ok_count / count, 6) if count else 0.0,
        "avg_latency_ms": round(statistics.fmean(durations), 3) if durations else 0.0,
        "p50_latency_ms": _percentile(durations, 0.50),
        "p95_latency_ms": _percentile(durations, 0.95),
        "avg_payload_bytes": int(statistics.fmean(payloads)) if payloads else 0,
        "p95_payload_bytes": int(_percentile(payloads, 0.95)) if payloads else 0,
    }


def _percentile(values: list[float] | list[int], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.999999)))
    return round(ordered[index], 3)


def _completed_pairs(rows: list[dict[str, Any]]) -> int:
    pairs: dict[int, set[str]] = {}
    fallback_counts = {"A": 0, "B": 0}
    for row in rows:
        arm = str(row.get("arm") or "").upper()
        if arm in fallback_counts:
            fallback_counts[arm] += 1
        try:
            pair_index = int(row.get("pair_index"))
        except (TypeError, ValueError):
            continue
        pairs.setdefault(pair_index, set()).add(arm)
    if pairs:
        return sum(1 for arms in pairs.values() if {"A", "B"}.issubset(arms))
    return min(fallback_counts["A"], fallback_counts["B"])


def _safety_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    canonical = 0
    official = 0
    unsafe_write = 0
    fail_open = 0
    a_shadow_present = 0
    shadow_present = 0
    shadow_effective = 0
    knowql_runtime_consumed = 0
    g3_present = 0
    for row in rows:
        arm = str(row.get("arm") or "").upper()
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if _recursive_true(metadata, "canonical_truth_written") or _recursive_true(metadata, "canonical_write_allowed"):
            canonical += 1
        if _recursive_true(metadata, "official_score_allowed"):
            official += 1
        unsafe_write += _unsafe_write_signal_count(metadata)
        shadow = metadata.get("luban_case_rubric_pgo_shadow") if isinstance(metadata, dict) else {}
        if isinstance(shadow, dict) and shadow:
            if arm == "A":
                a_shadow_present += 1
                continue
            if arm != "B":
                continue
            shadow_present += 1
            status = str(shadow.get("shadow_status") or "").strip()
            query = shadow.get("knowql_query") if isinstance(shadow.get("knowql_query"), dict) else {}
            if bool(query.get("runtime_consumed")):
                knowql_runtime_consumed += 1
            if status == "ok" and bool(query.get("runtime_consumed")):
                shadow_effective += 1
            if bool(query.get("fail_open")):
                fail_open += 1
        if isinstance(metadata.get("pgo_grading_to_brain"), dict):
            g3_present += 1
    return {
        "canonical_truth_write_count": canonical,
        "official_score_write_count": official,
        "unsafe_write_signal_count": unsafe_write,
        "a_pgo_shadow_present_count": a_shadow_present,
        "b_fail_open_count": fail_open,
        "b_pgo_shadow_present_count": shadow_present,
        "b_pgo_shadow_effective_count": shadow_effective,
        "b_knowql_runtime_consumed_count": knowql_runtime_consumed,
        "pgo_g3_preview_readback_count": g3_present,
    }


def _unsafe_write_signal_count(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "canonical_write_allowed",
                "writeback_performed",
                "claim_promotion_allowed",
                "canonical_truth_written",
                "official_score_written",
                "production_write_performed",
            } and item is True:
                count += 1
            if key in {"db_write_count", "remote_write_count", "production_write_count"}:
                try:
                    if int(item or 0) > 0:
                        count += 1
                except (TypeError, ValueError):
                    pass
            count += _unsafe_write_signal_count(item)
    elif isinstance(value, list):
        count += sum(_unsafe_write_signal_count(item) for item in value)
    return count


def _recursive_true(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key and item_value is True:
                return True
            if _recursive_true(item_value, key):
                return True
    if isinstance(value, list):
        return any(_recursive_true(item, key) for item in value)
    return False


async def run_live_shadow_ab(
    *,
    api_base_url: str,
    token: str,
    pairs: int,
    timeout_seconds: float,
    out_dir: Path,
    latency_degradation_threshold: float,
    max_b_fail_open_rate: float,
    min_b_shadow_rate: float,
    min_pairs: int,
    order_mode: str,
    seed: int | None,
    activation_probe_status: str = "not_run",
    connection_mode: str = "single",
    inter_turn_delay_seconds: float = 0.0,
) -> dict[str, Any]:
    run_id = f"pgo_l1_live_shadow_ab_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    ws_url = build_ws_url(api_base_url)
    rows: list[dict[str, Any]] = []
    schedule = build_run_schedule(pairs=pairs, order_mode=order_mode, seed=seed)
    normalized_connection_mode = (
        "per-turn" if str(connection_mode or "").strip().lower() == "per-turn" else "single"
    )
    delay_seconds = max(0.0, float(inter_turn_delay_seconds or 0.0))

    async def _run_scheduled_item(
        *,
        item: RunItem,
        order_index: int,
        websocket: Any | None = None,
    ) -> dict[str, Any]:
        sample = DEFAULT_SAMPLES[(item.pair_index - 1) % len(DEFAULT_SAMPLES)]
        frame = build_ws_frame(sample, arm=item.arm, run_id=run_id, pair_index=item.pair_index)
        if websocket is not None:
            return await _run_one_ws_turn_on_connection(
                websocket=websocket,
                frame=frame,
                arm=item.arm,
                order_index=order_index,
                pair_index=item.pair_index,
                sample=sample,
                timeout_seconds=timeout_seconds,
            )
        return await _run_one_ws_turn(
            ws_url=ws_url,
            token=token,
            frame=frame,
            arm=item.arm,
            order_index=order_index,
            pair_index=item.pair_index,
            sample=sample,
            timeout_seconds=timeout_seconds,
        )

    if normalized_connection_mode == "single":
        async with _connect_ws(ws_url, token=token) as websocket:
            for order_index, item in enumerate(schedule, start=1):
                rows.append(await _run_scheduled_item(
                    item=item,
                    order_index=order_index,
                    websocket=websocket,
                ))
                if delay_seconds and order_index < len(schedule):
                    await asyncio.sleep(delay_seconds)
    else:
        for order_index, item in enumerate(schedule, start=1):
            rows.append(await _run_scheduled_item(item=item, order_index=order_index))
            if delay_seconds and order_index < len(schedule):
                await asyncio.sleep(delay_seconds)
    summary = summarize_ab_rows(
        rows,
        latency_degradation_threshold=latency_degradation_threshold,
        max_b_fail_open_rate=max_b_fail_open_rate,
        min_b_shadow_rate=min_b_shadow_rate,
        min_pairs=min_pairs,
    )
    manifest = {
        "run_id": run_id,
        "mode": "live-shadow-ab",
        "entry": "remote /api/v1/ws paired A/B",
        "api_base_url": str(api_base_url or "").rstrip("/"),
        "ws_url": ws_url,
        "pairs": pairs,
        "min_pairs": min_pairs,
        "order_mode": order_mode,
        "seed": seed,
        "connection_mode": normalized_connection_mode,
        "inter_turn_delay_seconds": delay_seconds,
        "sample_ids": sorted({sample.sample_id for sample in DEFAULT_SAMPLES}),
        "activation_probe_status": activation_probe_status,
        "exit_code_intent": {"go": 0, "no_go": 1, "auth_blocked": 2, "activation_blocked": 3},
        "arms": {
            "A": "legacy deep_question grading path",
            "B": "legacy path + grading_engine_pgo_shadow=true",
        },
        "remote_write_requested": False,
        "production_default_flip_requested": False,
        "canonical_truth_write_allowed": False,
        "official_score_write_allowed": False,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "manifest.json", manifest)
    _write_jsonl(out_dir / "raw_rows.jsonl", rows)
    _write_json(out_dir / "summary.json", summary)
    _write_markdown(out_dir / "FINDING_pgo_l1_live_shadow_ab.md", manifest=manifest, summary=summary)
    return {"out_dir": str(out_dir), "manifest": manifest, "summary": summary}


async def run_activation_probe(
    *,
    api_base_url: str,
    token: str,
    timeout_seconds: float,
    out_dir: Path,
) -> dict[str, Any]:
    run_id = f"pgo_l1_activation_probe_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    ws_url = build_ws_url(api_base_url)
    sample = DEFAULT_SAMPLES[0]
    frame = build_ws_frame(sample, arm="B", run_id=run_id, pair_index=1)
    row = await _run_one_ws_turn(
        ws_url=ws_url,
        token=token,
        frame=frame,
        arm="B",
        order_index=1,
        pair_index=1,
        sample=sample,
        timeout_seconds=timeout_seconds,
    )
    summary = summarize_activation_probe([row])
    manifest = {
        "run_id": run_id,
        "mode": "activation-probe",
        "entry": "remote /api/v1/ws B-arm activation probe",
        "api_base_url": str(api_base_url or "").rstrip("/"),
        "ws_url": ws_url,
        "canonical_truth_write_allowed": False,
        "official_score_write_allowed": False,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"manifest": manifest, "rows": [row], "summary": summary}
    _write_json(out_dir / "activation_probe.json", payload)
    return {"out_dir": str(out_dir), "manifest": manifest, "summary": summary}


async def _run_one_ws_turn(
    *,
    ws_url: str,
    token: str,
    frame: dict[str, Any],
    arm: str,
    order_index: int,
    pair_index: int,
    sample: Sample,
    timeout_seconds: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    result_event: dict[str, Any] = {}
    terminal_event: dict[str, Any] = {}
    error = ""
    event_count = 0
    try:
        async with _connect_ws(ws_url, token=token) as websocket:
            return await _run_one_ws_turn_on_connection(
                websocket=websocket,
                frame=frame,
                arm=arm,
                order_index=order_index,
                pair_index=pair_index,
                sample=sample,
                timeout_seconds=timeout_seconds,
            )
    except Exception as exc:  # noqa: BLE001 - row-level failure must be captured
        error = str(exc)[:500]
    duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
    metadata = result_event.get("metadata") if isinstance(result_event.get("metadata"), dict) else {}
    return {
        "pair_index": pair_index,
        "order_index": order_index,
        "sample_id": sample.sample_id,
        "question_id": sample.question_id,
        "arm": arm,
        "ok": bool(result_event) and not error and terminal_event.get("type") != "error",
        "duration_ms": duration_ms,
        "payload_bytes": len(json.dumps(result_event or terminal_event, ensure_ascii=False).encode("utf-8")),
        "event_count": event_count,
        "terminal_type": terminal_event.get("type") or "",
        "error": error,
        "terminal_event": _safe_terminal_event(terminal_event),
        "metadata": metadata,
        "shadow_status": ((metadata.get("luban_case_rubric_pgo_shadow") or {}).get("shadow_status") if isinstance(metadata, dict) else ""),
        "has_pgo_g3_readback": isinstance(metadata.get("pgo_grading_to_brain"), dict) if isinstance(metadata, dict) else False,
    }


async def _run_one_ws_turn_on_connection(
    *,
    websocket: Any,
    frame: dict[str, Any],
    arm: str,
    order_index: int,
    pair_index: int,
    sample: Sample,
    timeout_seconds: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    result_event: dict[str, Any] = {}
    terminal_event: dict[str, Any] = {}
    error = ""
    event_count = 0
    try:
        await websocket.send(json.dumps(frame, ensure_ascii=False))
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
            event_count += 1
            event = json.loads(raw)
            if not isinstance(event, dict):
                continue
            if event.get("type") == "result":
                result_event = event
            if event.get("type") in {"done", "error"}:
                terminal_event = event
                break
    except Exception as exc:  # noqa: BLE001 - row-level failure must be captured
        error = str(exc)[:500]
    duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
    metadata = result_event.get("metadata") if isinstance(result_event.get("metadata"), dict) else {}
    return {
        "pair_index": pair_index,
        "order_index": order_index,
        "sample_id": sample.sample_id,
        "question_id": sample.question_id,
        "arm": arm,
        "ok": bool(result_event) and not error and terminal_event.get("type") != "error",
        "duration_ms": duration_ms,
        "payload_bytes": len(json.dumps(result_event or terminal_event, ensure_ascii=False).encode("utf-8")),
        "event_count": event_count,
        "terminal_type": terminal_event.get("type") or "",
        "error": error,
        "terminal_event": _safe_terminal_event(terminal_event),
        "metadata": metadata,
        "shadow_status": ((metadata.get("luban_case_rubric_pgo_shadow") or {}).get("shadow_status") if isinstance(metadata, dict) else ""),
        "has_pgo_g3_readback": isinstance(metadata.get("pgo_grading_to_brain"), dict) if isinstance(metadata, dict) else False,
    }


def _safe_terminal_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {}
    allowed = {}
    for key in ("type", "code", "message", "content", "error", "reason", "detail", "data", "payload"):
        value = event.get(key)
        if value not in (None, ""):
            allowed[key] = str(value)[:500] if not isinstance(value, (dict, list)) else value
    return allowed


def _connect_ws(ws_url: str, *, token: str) -> Any:
    headers = {"Authorization": f"Bearer {token}"}
    try:
        return websockets.connect(ws_url, additional_headers=headers)
    except TypeError:
        return websockets.connect(ws_url, extra_headers=headers)


async def resolve_token(
    *,
    api_base_url: str,
    auth_token: str,
    username: str,
    password: str,
    phone: str,
    register: bool,
) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    if token:
        return {"ok": True, "token": token, "auth_mode": "provided_token"}
    if not username or not password:
        return {"ok": False, "reason": "missing_auth", "auth_mode": "none"}
    async with httpx.AsyncClient(base_url=str(api_base_url or "").rstrip("/"), timeout=30.0, trust_env=False) as client:
        if register:
            await client.post(
                "/api/v1/auth/register",
                json={"username": username, "password": password, "phone": phone},
            )
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        if response.status_code != 200:
            return {"ok": False, "reason": "login_failed", "status_code": response.status_code}
        payload = response.json()
        token = str(payload.get("token") or "").strip()
        if not token:
            return {"ok": False, "reason": "login_token_missing"}
        return {"ok": True, "token": token, "auth_mode": "login"}


def _default_out_dir() -> Path:
    return ARTIFACT_ROOT / f"pgo_l1_live_shadow_ab_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _generated_credentials(prefix: str) -> tuple[str, str, str]:
    stamp = int(time.time())
    username = f"{prefix}_{stamp}"
    password = f"L1Ab{stamp % 1000000:06d}"
    phone = f"139{stamp % 100000000:08d}"
    return username, password, phone


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_markdown(path: Path, *, manifest: dict[str, Any], summary: dict[str, Any]) -> None:
    lines = [
        "# PGO L1 Live Shadow A/B",
        "",
        f"- status: `{summary['decision']['status']}`",
        f"- api_base_url: `{manifest['api_base_url']}`",
        f"- pairs: `{manifest['pairs']}`",
        f"- min pairs: `{manifest.get('min_pairs')}`",
        f"- completed pairs: `{summary['comparison'].get('completed_pairs')}`",
        f"- order mode: `{manifest.get('order_mode')}`",
        f"- connection mode: `{manifest.get('connection_mode')}`",
        f"- inter-turn delay seconds: `{manifest.get('inter_turn_delay_seconds')}`",
        f"- schedule seed: `{manifest.get('seed')}`",
        f"- sample ids: `{', '.join(manifest.get('sample_ids') or [])}`",
        f"- activation probe status: `{manifest.get('activation_probe_status', 'not_recorded')}`",
        f"- p95 latency delta pct: `{summary['comparison']['p95_latency_delta_pct']}`",
        f"- payload bytes delta: `{summary['comparison']['payload_bytes_delta']}`",
        f"- B fail-open rate: `{summary['comparison'].get('b_fail_open_rate')}`",
        f"- B PGO shadow effective rate: `{summary['comparison'].get('b_pgo_shadow_effective_rate')}`",
        f"- B KnowQL runtime consumed rate: `{summary['comparison'].get('b_knowql_runtime_consumed_rate')}`",
        f"- canonical truth writes: `{summary['safety']['canonical_truth_write_count']}`",
        f"- official score writes: `{summary['safety']['official_score_write_count']}`",
        f"- unsafe write signal count: `{summary['safety'].get('unsafe_write_signal_count')}`",
        f"- A PGO shadow present count: `{summary['safety'].get('a_pgo_shadow_present_count')}`",
        f"- B fail-open count: `{summary['safety']['b_fail_open_count']}`",
        f"- B PGO shadow present count: `{summary['safety']['b_pgo_shadow_present_count']}`",
        f"- B PGO shadow effective count: `{summary['safety']['b_pgo_shadow_effective_count']}`",
        f"- B KnowQL runtime consumed count: `{summary['safety'].get('b_knowql_runtime_consumed_count')}`",
        f"- PGO G3 preview readback count: `{summary['safety']['pgo_g3_preview_readback_count']}`",
        f"- exit code intent: `{json.dumps(manifest.get('exit_code_intent', {}), ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Decision Reasons",
        "",
    ]
    reasons = list(summary["decision"].get("reasons") or [])
    lines.extend([f"- `{reason}`" for reason in reasons] or ["- none"])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


async def _main_async(args: argparse.Namespace) -> int:
    username = args.username
    password = args.password
    phone = args.phone
    if args.register and (not username or not password or not phone):
        username, password, phone = _generated_credentials(args.username_prefix)
    auth = await resolve_token(
        api_base_url=args.api_base_url,
        auth_token=args.auth_token or os.environ.get("DEEPTUTOR_L1_AB_AUTH_TOKEN", ""),
        username=username,
        password=password,
        phone=phone,
        register=args.register,
    )
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    if not auth.get("ok"):
        out_dir.mkdir(parents=True, exist_ok=True)
        blocked = {
            "status": "L1_AUTH_BLOCKED",
            "reason": auth.get("reason"),
            "api_base_url": args.api_base_url,
            "remote_write_requested": False,
            "canonical_truth_write_allowed": False,
        }
        _write_json(out_dir / "summary.json", {"decision": blocked})
        print(json.dumps({"out_dir": str(out_dir), "summary": {"decision": blocked}}, ensure_ascii=False, indent=2))
        return 2
    activation_probe_status = "skipped"
    if not args.skip_activation_probe:
        activation = await run_activation_probe(
            api_base_url=args.api_base_url,
            token=str(auth["token"]),
            timeout_seconds=args.timeout_seconds,
            out_dir=out_dir,
        )
        activation_probe_status = str(activation["summary"]["decision"]["status"])
        if activation["summary"]["decision"]["status"] != "L1_ACTIVATION_READY":
            print(json.dumps(activation, ensure_ascii=False, indent=2))
            return 3
    min_pairs = int(args.min_pairs or args.pairs)
    result = await run_live_shadow_ab(
        api_base_url=args.api_base_url,
        token=str(auth["token"]),
        pairs=args.pairs,
        timeout_seconds=args.timeout_seconds,
        out_dir=out_dir,
        latency_degradation_threshold=args.latency_degradation_threshold,
        max_b_fail_open_rate=args.max_b_fail_open_rate,
        min_b_shadow_rate=args.min_b_shadow_rate,
        min_pairs=min_pairs,
        order_mode=args.order_mode,
        seed=args.seed,
        activation_probe_status=activation_probe_status,
        connection_mode=args.connection_mode,
        inter_turn_delay_seconds=args.inter_turn_delay_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["summary"]["decision"]["status"] == "L1_SHADOW_AB_GO" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default=os.environ.get("DEEPTUTOR_L1_AB_API_BASE_URL", "https://test2.yousenjiaoyu.com"))
    parser.add_argument("--auth-token", default="")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--phone", default="")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--username-prefix", default="qa_pgo_l1_ab")
    parser.add_argument("--pairs", type=int, default=30)
    parser.add_argument("--min-pairs", type=int, default=0)
    parser.add_argument("--order-mode", choices=("alternating", "ab", "ba", "randomized"), default="alternating")
    parser.add_argument("--seed", type=int, default=20260615)
    parser.add_argument("--connection-mode", choices=("single", "per-turn"), default="per-turn")
    parser.add_argument("--inter-turn-delay-seconds", type=float, default=8.0)
    parser.add_argument("--skip-activation-probe", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--latency-degradation-threshold", type=float, default=0.25)
    parser.add_argument("--max-b-fail-open-rate", type=float, default=0.05)
    parser.add_argument("--min-b-shadow-rate", type=float, default=1.0)
    parser.add_argument("--out-dir", default="")
    return parser


def main() -> int:
    return asyncio.run(_main_async(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
