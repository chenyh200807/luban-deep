#!/usr/bin/env python3
"""Run a streaming TTFT A/B for RuntimeTokenPack versus full-span supply."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean
from typing import Any, Callable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v1_20260612/runtime_token_pack.json"
)
DEFAULT_RUNTIME_SUPPLY_CANDIDATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_supply_candidate_materialized_20260612/rich_leaf_runtime_supply_candidate.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_streaming_ab_20260612/streaming_ab.json"
)
SCHEMA = "luban_rich_leaf_runtime_token_pack_streaming_ab.v1"
TOKEN_PACK_SCHEMA = "luban_rich_leaf_runtime_token_pack.v1"
TOKEN_PACK_SCHEMA_V2 = "luban_rich_leaf_runtime_token_pack.v2"
TOKEN_PACK_SCHEMA_V21 = "luban_rich_leaf_runtime_token_pack.v2.1"
TOKEN_PACK_SCHEMA_V22 = "luban_rich_leaf_runtime_token_pack.v2.2"
TOKEN_PACK_SCHEMA_V23 = "luban_rich_leaf_runtime_token_pack.v2.3"
RUNTIME_SUPPLY_SCHEMA = "luban_rich_leaf_runtime_supply_candidate_bundle.v1"
ARMS_V1 = ("runtime_token_pack_thin", "runtime_supply_full_span")
ARMS_V2 = ("rich_leaf_promoted_context_v2", "source_excerpt_only_v2")
ARMS_V21 = ("leaf_scoped_context_v21", "source_pointer_only_v21")
PROVIDER_DEFAULTS = {
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "dashscope": {
        "env_key": "DASHSCOPE_API_KEY",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
}


ProviderCall = Callable[[str, list[dict[str, str]], float], dict[str, Any]]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_dotenv() -> None:
    for path in (REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        if not path.exists():
            continue
        for line in path.read_text("utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


def _openai_compat_stream_provider(*, provider: str, model: str | None, timeout_s: float) -> ProviderCall | None:
    _load_dotenv()
    spec = PROVIDER_DEFAULTS[provider]
    api_key = os.environ.get(spec["env_key"])
    if not api_key:
        return None
    base_url = (os.environ.get(spec["base_url_env"]) or spec["base_url"]).rstrip("/")
    selected_model = model or spec["model"]

    def call(_: str, messages: list[dict[str, str]], timeout_s: float = timeout_s) -> dict[str, Any]:
        started = time.monotonic()
        prompt_chars = sum(len(message.get("content") or "") for message in messages)
        body = json.dumps(
            {
                "model": selected_model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": 80,
                "stream": True,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        content_parts: list[str] = []
        first_byte_ms: float | None = None
        ttft_ms: float | None = None
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                while True:
                    raw_line = response.readline()
                    if not raw_line:
                        break
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if first_byte_ms is None:
                        first_byte_ms = (time.monotonic() - started) * 1000
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = ((payload.get("choices") or [{}])[0].get("delta") or {})
                    text = str(delta.get("content") or "")
                    if text:
                        if ttft_ms is None:
                            ttft_ms = (time.monotonic() - started) * 1000
                        content_parts.append(text)
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{provider}_http_error:{exc.code}:{text[:200]}") from exc
        full_latency_ms = (time.monotonic() - started) * 1000
        return {
            "model": selected_model,
            "content": "".join(content_parts),
            "first_byte_ms": round(first_byte_ms if first_byte_ms is not None else full_latency_ms, 2),
            "ttft_ms": round(ttft_ms if ttft_ms is not None else full_latency_ms, 2),
            "full_latency_ms": round(full_latency_ms, 2),
            "prompt_char_count": prompt_chars,
            "completion_char_count": len("".join(content_parts)),
        }

    return call


def _input_blockers(runtime_token_pack: dict[str, Any], runtime_supply_candidate: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    token_pack_schema = runtime_token_pack.get("schema")
    if token_pack_schema not in {TOKEN_PACK_SCHEMA, TOKEN_PACK_SCHEMA_V2, TOKEN_PACK_SCHEMA_V21, TOKEN_PACK_SCHEMA_V22, TOKEN_PACK_SCHEMA_V23}:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    if token_pack_schema == TOKEN_PACK_SCHEMA and runtime_supply_candidate.get("schema") != RUNTIME_SUPPLY_SCHEMA:
        blockers.append(f"runtime_supply_schema_mismatch:{runtime_supply_candidate.get('schema')}")
    payloads = [("runtime_token_pack", runtime_token_pack)]
    if token_pack_schema == TOKEN_PACK_SCHEMA:
        payloads.append(("runtime_supply", runtime_supply_candidate))
    for name, payload in payloads:
        classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
        safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
        if classification.get("runtime_install_allowed") is not False:
            blockers.append(f"{name}_runtime_install_allowed")
        if classification.get("production_default") is not False:
            blockers.append(f"{name}_production_default")
        if safety.get("production_write_count", 0) not in (0, None):
            blockers.append(f"{name}_production_write_count_nonzero")
        if safety.get("release_truth_claimed") is not False:
            blockers.append(f"{name}_release_truth_claimed")
    return blockers


def _supply_by_unit_id(runtime_supply_candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(unit.get("unit_id")): unit
        for unit in runtime_supply_candidate.get("supply_units") or []
        if isinstance(unit, dict) and unit.get("unit_id")
    }


def _messages(arm: str, token_unit: dict[str, Any], supply_unit: dict[str, Any]) -> tuple[list[dict[str, str]], int]:
    if arm == "runtime_token_pack_thin":
        source_ref = token_unit.get("source_ref") if isinstance(token_unit.get("source_ref"), dict) else {}
        context = {
            "mode": "runtime_token_pack_thin",
            "leaf_id": token_unit.get("leaf_id"),
            "artifact_id": token_unit.get("artifact_id"),
            "source_ref": source_ref,
            "authority_pointer": token_unit.get("authority_pointer"),
        }
    elif arm == "runtime_supply_full_span":
        source_ref = supply_unit.get("source_ref") if isinstance(supply_unit.get("source_ref"), dict) else {}
        context = {
            "mode": "runtime_supply_full_span",
            "leaf_id": supply_unit.get("leaf_id"),
            "artifact_id": supply_unit.get("artifact_id"),
            "source_ref": source_ref,
        }
    elif arm == "rich_leaf_promoted_context_v2":
        source_ref = token_unit.get("source_ref") if isinstance(token_unit.get("source_ref"), dict) else {}
        context = {
            "mode": "rich_leaf_promoted_context_v2",
            "unit_id": token_unit.get("unit_id"),
            "candidate_id": token_unit.get("candidate_id"),
            "source_lane": token_unit.get("source_lane"),
            "relative_path": token_unit.get("relative_path"),
            "compiled_context": token_unit.get("compiled_context") if isinstance(token_unit.get("compiled_context"), dict) else {},
            "source_ref": {
                "source_lane": source_ref.get("source_lane"),
                "source_path": source_ref.get("source_path"),
                "record_id": source_ref.get("record_id"),
                "span_hash": source_ref.get("span_hash"),
            },
        }
    elif arm == "source_excerpt_only_v2":
        source_ref = token_unit.get("source_ref") if isinstance(token_unit.get("source_ref"), dict) else {}
        context = {
            "mode": "source_excerpt_only_v2",
            "unit_id": token_unit.get("unit_id"),
            "candidate_id": token_unit.get("candidate_id"),
            "source_lane": token_unit.get("source_lane"),
            "relative_path": token_unit.get("relative_path"),
            "source_ref": {
                "source_lane": source_ref.get("source_lane"),
                "source_path": source_ref.get("source_path"),
                "record_id": source_ref.get("record_id"),
                "span_hash": source_ref.get("span_hash"),
                "excerpt": source_ref.get("excerpt"),
            },
        }
    elif arm == "leaf_scoped_context_v21":
        source_ref = token_unit.get("source_ref") if isinstance(token_unit.get("source_ref"), dict) else {}
        context = {
            "mode": "leaf_scoped_context_v21",
            "unit_id": token_unit.get("unit_id"),
            "leaf_id": token_unit.get("leaf_id"),
            "leaf_name_path": token_unit.get("leaf_name_path"),
            "source_lane": token_unit.get("source_lane"),
            "compiled_context": token_unit.get("compiled_context") if isinstance(token_unit.get("compiled_context"), dict) else {},
            "source_ref": {
                "source_lane": source_ref.get("source_lane"),
                "source_path": source_ref.get("source_path"),
                "record_id": source_ref.get("record_id"),
                "span_hash": source_ref.get("span_hash"),
            },
        }
    elif arm == "source_pointer_only_v21":
        source_ref = token_unit.get("source_ref") if isinstance(token_unit.get("source_ref"), dict) else {}
        context = {
            "mode": "source_pointer_only_v21",
            "unit_id": token_unit.get("unit_id"),
            "leaf_id": token_unit.get("leaf_id"),
            "leaf_name_path": token_unit.get("leaf_name_path"),
            "source_ref": {
                "source_lane": source_ref.get("source_lane"),
                "source_path": source_ref.get("source_path"),
                "record_id": source_ref.get("record_id"),
                "span_hash": source_ref.get("span_hash"),
            },
        }
    else:
        raise ValueError(f"unknown_arm:{arm}")
    user_content = json.dumps(
        {
            "task": "Answer with one concise Chinese sentence using only the provided source evidence.",
            "context": context,
            "required_output": "one_sentence",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return (
        [
            {"role": "system", "content": "You are a strict source-grounded runtime renderer. Do not invent evidence."},
            {"role": "user", "content": user_content},
        ],
        len(user_content),
    )


def _arm_summary(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    return {
        "arm": arm,
        "status": "completed" if rows and len(completed) == len(rows) else "failed",
        "sample_count": len(rows),
        "provider_call_count": len(completed),
        "mean_context_char_count": round(mean([int(row.get("context_char_count") or 0) for row in completed]), 2)
        if completed
        else 0.0,
        "mean_first_byte_ms": round(mean([float(row.get("first_byte_ms") or 0.0) for row in completed]), 2)
        if completed
        else 0.0,
        "mean_ttft_ms": round(mean([float(row.get("ttft_ms") or 0.0) for row in completed]), 2)
        if completed
        else 0.0,
        "mean_full_latency_ms": round(mean([float(row.get("full_latency_ms") or 0.0) for row in completed]), 2)
        if completed
        else 0.0,
        "mean_prompt_char_count": round(mean([int(row.get("prompt_char_count") or 0) for row in completed]), 2)
        if completed
        else 0.0,
        "mean_completion_char_count": round(mean([int(row.get("completion_char_count") or 0) for row in completed]), 2)
        if completed
        else 0.0,
    }


def build_runtime_token_pack_streaming_ab(
    *,
    runtime_token_pack: dict[str, Any],
    runtime_supply_candidate: dict[str, Any],
    start_index: int = 0,
    sample_limit: int,
    provider_call: ProviderCall | None,
    model: str,
    timeout_s: float = 45.0,
    max_workers: int = 1,
    progress_every: int = 0,
) -> dict[str, Any]:
    blockers = _input_blockers(runtime_token_pack, runtime_supply_candidate)
    if provider_call is None:
        blockers.append("provider_call_not_configured")
    token_pack_schema = runtime_token_pack.get("schema")
    if token_pack_schema in {TOKEN_PACK_SCHEMA_V21, TOKEN_PACK_SCHEMA_V22, TOKEN_PACK_SCHEMA_V23}:
        arms = ARMS_V21
    elif token_pack_schema == TOKEN_PACK_SCHEMA_V2:
        arms = ARMS_V2
    else:
        arms = ARMS_V1
    supply_by_id = _supply_by_unit_id(runtime_supply_candidate) if token_pack_schema == TOKEN_PACK_SCHEMA else {}
    if token_pack_schema in {TOKEN_PACK_SCHEMA_V2, TOKEN_PACK_SCHEMA_V21, TOKEN_PACK_SCHEMA_V22, TOKEN_PACK_SCHEMA_V23}:
        all_token_units = [
            unit
            for unit in runtime_token_pack.get("runtime_token_pack_units") or []
            if isinstance(unit, dict) and unit.get("unit_id")
        ]
    else:
        all_token_units = [
            unit
            for unit in runtime_token_pack.get("runtime_token_pack_units") or []
            if isinstance(unit, dict) and str(unit.get("unit_id")) in supply_by_id
        ]
    token_units = all_token_units[max(0, start_index) : max(0, start_index) + max(0, sample_limit)]
    if not token_units:
        blockers.append("no_joined_token_pack_units")

    rows: list[dict[str, Any]] = []
    if not blockers and provider_call is not None:
        def run_one(token_unit: dict[str, Any], arm: str) -> dict[str, Any]:
            supply_unit = supply_by_id.get(str(token_unit.get("unit_id")), token_unit)
            messages, context_chars = _messages(arm, token_unit, supply_unit)
            try:
                response = provider_call(model, messages, timeout_s)
                return {
                    "arm": arm,
                    "unit_id": token_unit.get("unit_id"),
                    "leaf_id": token_unit.get("leaf_id"),
                    "artifact_id": token_unit.get("artifact_id"),
                    "status": "completed",
                    "context_char_count": context_chars,
                    "first_byte_ms": float(response.get("first_byte_ms") or 0.0),
                    "ttft_ms": float(response.get("ttft_ms") or 0.0),
                    "full_latency_ms": float(response.get("full_latency_ms") or 0.0),
                    "prompt_char_count": int(response.get("prompt_char_count") or 0),
                    "completion_char_count": int(response.get("completion_char_count") or 0),
                }
            except Exception as exc:  # pragma: no cover - live provider failure path
                return {
                    "arm": arm,
                    "unit_id": token_unit.get("unit_id"),
                    "leaf_id": token_unit.get("leaf_id"),
                    "artifact_id": token_unit.get("artifact_id"),
                    "status": "failed",
                    "error": str(exc)[:240],
                    "context_char_count": context_chars,
                    "first_byte_ms": 0.0,
                    "ttft_ms": 0.0,
                    "full_latency_ms": 0.0,
                    "prompt_char_count": 0,
                    "completion_char_count": 0,
                }

        work = [(unit, arm) for unit in token_units for arm in arms]
        completed = 0
        if max_workers <= 1:
            for token_unit, arm in work:
                rows.append(run_one(token_unit, arm))
                completed += 1
                if progress_every and completed % progress_every == 0:
                    print(f"streaming_ab_progress completed={completed}/{len(work)}", file=sys.stderr, flush=True)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(run_one, token_unit, arm) for token_unit, arm in work]
                for future in as_completed(futures):
                    rows.append(future.result())
                    completed += 1
                    if progress_every and completed % progress_every == 0:
                        print(f"streaming_ab_progress completed={completed}/{len(work)}", file=sys.stderr, flush=True)

    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_arm[str(row.get("arm"))].append(row)
    arm_summaries = [_arm_summary(arm, by_arm.get(arm, [])) for arm in arms]
    runtime_exercised = bool(rows) and all(arm["status"] == "completed" for arm in arm_summaries)
    return {
        "schema": SCHEMA,
        "input_schema": token_pack_schema,
        "runtime_exercised": runtime_exercised,
        "execution_authority": "authorized_streaming_shadow" if runtime_exercised else "not_exercised",
        "model": model if runtime_exercised else None,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_token_pack_streaming_ab": True,
            "runtime_token_pack_v2": token_pack_schema == TOKEN_PACK_SCHEMA_V2,
            "runtime_token_pack_v21": token_pack_schema == TOKEN_PACK_SCHEMA_V21,
            "runtime_token_pack_v22": token_pack_schema == TOKEN_PACK_SCHEMA_V22,
            "runtime_token_pack_v23": token_pack_schema == TOKEN_PACK_SCHEMA_V23,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "sample_count": len(token_units),
            "start_index": max(0, start_index),
            "planned_arm_count": len(arms),
            "provider_call_count": sum(int(arm["provider_call_count"]) for arm in arm_summaries),
            "blocker_count": len(blockers),
        },
        "arms": arm_summaries,
        "rows": rows,
        "blockers": blockers,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--runtime-supply-candidate", type=Path, default=DEFAULT_RUNTIME_SUPPLY_CANDIDATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--sample-limit", type=int, default=16)
    parser.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--progress-every", type=int, default=0)
    parser.add_argument("--no-provider-call", action="store_true")
    args = parser.parse_args(argv)
    model = args.model or PROVIDER_DEFAULTS[args.provider]["model"]
    provider_call = None if args.no_provider_call else _openai_compat_stream_provider(provider=args.provider, model=model, timeout_s=args.timeout_s)
    report = build_runtime_token_pack_streaming_ab(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        runtime_supply_candidate=_read_json(args.runtime_supply_candidate),
        start_index=args.start_index,
        sample_limit=args.sample_limit,
        provider_call=provider_call,
        model=model,
        timeout_s=args.timeout_s,
        max_workers=args.max_workers,
        progress_every=args.progress_every,
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "runtime_exercised": report["runtime_exercised"], "summary": report["summary"], "blockers": report["blockers"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["runtime_exercised"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
