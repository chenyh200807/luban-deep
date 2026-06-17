#!/usr/bin/env python3
"""Run shadow LLM deep compilation for RichLeaf packet work orders."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_PACKETS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_llm_deep_compile_packets_20260612/llm_deep_compile_packets.json"
)
DEFAULT_SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_llm_deep_compile_runner_20260612/llm_deep_compile_runner.json"
)
SCHEMA = "luban_rich_leaf_llm_deep_compile_runner.v1"
PACKETS_SCHEMA = "luban_rich_leaf_llm_deep_compile_packets.v1"
REQUIRED_FIELDS = [
    "concepts",
    "definitions",
    "rules",
    "procedures",
    "numeric_constraints",
    "common_mistakes",
    "exam_patterns",
    "source_refs",
    "negative_evidence",
    "teaching_cards",
    "grading_relevance",
    "learner_memory_event_templates",
]
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

ProviderCall = Callable[[str, list[dict[str, str]]], dict[str, Any]]


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
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


def _openai_compat_provider(*, provider: str, model: str | None, timeout_s: float, max_tokens: int) -> ProviderCall | None:
    _load_dotenv()
    spec = PROVIDER_DEFAULTS[provider]
    api_key = os.environ.get(spec["env_key"])
    if not api_key:
        return None
    base_url = (os.environ.get(spec["base_url_env"]) or spec["base_url"]).rstrip("/")
    selected_model = model or spec["model"]

    def call(_: str, messages: list[dict[str, str]], *, timeout_s: float = timeout_s) -> dict[str, Any]:
        started = time.monotonic()
        body = json.dumps(
            {
                "model": selected_model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{provider}_http_error:{exc.code}:{text[:240]}") from exc
        content = str(payload["choices"][0]["message"].get("content") or "")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return {
            "model": selected_model,
            "content": content,
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
        }

    return call


def _input_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != PACKETS_SCHEMA:
        blockers.append(f"packets_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "READY_FOR_LLM_DEEP_COMPILE_SHADOW":
        blockers.append(f"packets_not_ready:{payload.get('verdict')}")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if classification.get("runtime_install_allowed") is True:
        blockers.append("packets_runtime_install_allowed")
    if classification.get("release_truth_claimed") is True:
        blockers.append("packets_release_truth_claimed")
    if int(safety.get("production_write_count") or 0) != 0:
        blockers.append("packets_production_write_count")
    return blockers


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(text[start : end + 1])
                return payload if isinstance(payload, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def _source_text(path: Path, max_source_chars: int) -> str:
    raw = path.read_text("utf-8", errors="replace")
    if path.suffix == ".json":
        try:
            payload = json.loads(raw)
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except json.JSONDecodeError:
            pass
    return raw[:max_source_chars]


def _iter_work_orders(
    packet_payload: dict[str, Any],
    *,
    start_index: int,
    max_work_orders: int | None,
) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    seen = 0
    for packet in packet_payload.get("packets") or []:
        if not isinstance(packet, dict):
            continue
        packet_id = str(packet.get("packet_id") or "")
        for order in packet.get("work_orders") or []:
            if isinstance(order, dict):
                if seen < start_index:
                    seen += 1
                    continue
                rows.append((packet_id, order))
                seen += 1
                if max_work_orders is not None and len(rows) >= max_work_orders:
                    return rows
    return rows


def _messages(order: dict[str, Any], *, source_text: str) -> list[dict[str, str]]:
    user_payload = {
        "task": (
            "Compile this source file into a compact RichLeaf deep compile candidate. "
            "Return exactly one top-level JSON object with the required fields only. "
            "MAX_ITEMS_PER_FIELD=2. Keep every string concise."
        ),
        "work_order": {
            "work_order_id": order.get("work_order_id"),
            "relative_path": order.get("relative_path"),
            "source_lane": order.get("source_lane"),
            "sha256": order.get("sha256"),
        },
        "source_text": source_text,
        "required_fields": REQUIRED_FIELDS,
        "rules": [
            "Return exactly one top-level JSON object; do not wrap in artifact/compiled_blocks/chunks.",
            "MAX_ITEMS_PER_FIELD=2 for concepts, definitions, rules, procedures, mistakes, patterns, cards, and templates.",
            "source_refs may include at most 3 short spans copied from source_text.",
            "Do not edit taxonomy or invent source truth.",
            "Every claim must either cite a source span from source_text or be empty/unresolved.",
            "Question-bank evidence may show exam usage but must not become source truth.",
            "Keep candidate_only=true, runtime_install_allowed=false, release_truth_claimed=false.",
        ],
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a RichLeaf deep compiler. Produce compact, auditable JSON for a "
                "candidate-only artifact. Never claim release truth or write permissions."
            ),
        },
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def _compiled_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {field: payload.get(field) if field in payload else [] for field in REQUIRED_FIELDS}


def _candidate(
    *,
    packet_id: str,
    order: dict[str, Any],
    provider_result: dict[str, Any],
    parsed: dict[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_id": f"llm_deep_compile_candidate:{order.get('work_order_id')}",
        "candidate_status": "llm_shadow_candidate",
        "packet_id": packet_id,
        "work_order_id": order.get("work_order_id"),
        "relative_path": order.get("relative_path"),
        "source_lane": order.get("source_lane"),
        "sha256": order.get("sha256"),
        "compiled_fields": _compiled_fields(parsed),
        "provider": {
            "model": provider_result.get("model"),
            "prompt_tokens": int(provider_result.get("prompt_tokens") or 0),
            "completion_tokens": int(provider_result.get("completion_tokens") or 0),
            "latency_ms": float(provider_result.get("latency_ms") or 0.0),
        },
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "official_score_allowed": False,
    }


def run_llm_deep_compile_runner(
    *,
    llm_deep_compile_packets: dict[str, Any],
    source_root: Path,
    provider_call: ProviderCall | None,
    start_index: int = 0,
    max_work_orders: int | None,
    max_source_chars: int,
    dry_run: bool = False,
) -> dict[str, Any]:
    blockers = _input_blockers(llm_deep_compile_packets)
    rows = _iter_work_orders(llm_deep_compile_packets, start_index=max(start_index, 0), max_work_orders=max_work_orders)
    if dry_run:
        verdict = "DRY_RUN_READY_FOR_PROVIDER" if not blockers else "NO_GO_INPUT_SAFETY_INVARIANT"
        return _report(verdict=verdict, blockers=blockers, rows=rows, candidates=[], errors=[], provider_call_count=0)
    if provider_call is None:
        return _report(
            verdict="BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED",
            blockers=blockers + ["provider_call_not_configured"],
            rows=rows,
            candidates=[],
            errors=[],
            provider_call_count=0,
        )
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    provider_call_count = 0
    for packet_id, order in rows:
        relative_path = str(order.get("relative_path") or "")
        source_path = source_root / relative_path
        if not source_path.exists() or not source_path.is_file():
            errors.append({"work_order_id": order.get("work_order_id"), "error": f"source_file_missing:{relative_path}"})
            continue
        try:
            messages = _messages(order, source_text=_source_text(source_path, max_source_chars=max_source_chars))
            result = provider_call(str(order.get("work_order_id") or ""), messages)
            provider_call_count += 1
            raw_content = str(result.get("content") or "")
            parsed = _parse_json_object(raw_content)
            if not parsed:
                errors.append(
                    {
                        "work_order_id": order.get("work_order_id"),
                        "error": "provider_returned_non_json",
                        "raw_content_excerpt": raw_content[:500],
                        "model": result.get("model"),
                        "prompt_tokens": int(result.get("prompt_tokens") or 0),
                        "completion_tokens": int(result.get("completion_tokens") or 0),
                        "latency_ms": float(result.get("latency_ms") or 0.0),
                    }
                )
                continue
            candidates.append(_candidate(packet_id=packet_id, order=order, provider_result=result, parsed=parsed))
        except Exception as exc:  # noqa: BLE001 - preserved in artifact for review.
            errors.append({"work_order_id": order.get("work_order_id"), "error": str(exc)[:500]})
    if blockers:
        verdict = "NO_GO_INPUT_SAFETY_INVARIANT"
    elif errors and not candidates:
        verdict = "NO_GO_LLM_DEEP_COMPILE_FAILED"
    elif errors:
        verdict = "PARTIAL_LLM_DEEP_COMPILE_SHADOW_CANDIDATES"
    else:
        verdict = "PASS_LLM_DEEP_COMPILE_SHADOW_CANDIDATES"
    return _report(
        verdict=verdict,
        blockers=blockers,
        rows=rows,
        candidates=candidates,
        errors=errors,
        provider_call_count=provider_call_count,
    )


def _report(
    *,
    verdict: str,
    blockers: list[str],
    rows: list[tuple[str, dict[str, Any]]],
    candidates: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    provider_call_count: int,
) -> dict[str, Any]:
    prompt_tokens = sum(int(candidate["provider"].get("prompt_tokens") or 0) for candidate in candidates)
    completion_tokens = sum(int(candidate["provider"].get("completion_tokens") or 0) for candidate in candidates)
    return {
        "schema": SCHEMA,
        "input_schemas": {"llm_deep_compile_packets": PACKETS_SCHEMA},
        "verdict": verdict,
        "quality_claim_allowed": False,
        "execution_mode": "llm_shadow_candidate_compile",
        "summary": {
            "planned_work_order_count": len(rows),
            "provider_call_count": provider_call_count,
            "candidate_count": len(candidates),
            "error_count": len(errors),
            "blocker_count": len(blockers),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "production_write_count": 0,
            "runtime_install_count": 0,
        },
        "candidates": candidates,
        "errors": errors,
        "blockers": blockers,
        "not_exercised": [
            "semantic_review",
            "evidence_span_auditor",
            "prosecutor",
            "defense",
            "arbiter",
            "bucket_taxonomist",
            "runtime_default_install",
            "canonical_truth_write",
            "production_db_write",
            "release_truth_claim",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "llm_deep_compile_runner": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
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
    parser.add_argument("--packets", type=Path, default=DEFAULT_PACKETS)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--max-tokens", type=int, default=1400)
    parser.add_argument("--max-work-orders", type=int, default=1)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--max-source-chars", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    provider_call = None if args.dry_run else _openai_compat_provider(
        provider=args.provider,
        model=args.model,
        timeout_s=args.timeout_s,
        max_tokens=args.max_tokens,
    )
    report = run_llm_deep_compile_runner(
        llm_deep_compile_packets=_read_json(args.packets),
        source_root=args.source_root,
        provider_call=provider_call,
        start_index=args.start_index,
        max_work_orders=args.max_work_orders,
        max_source_chars=args.max_source_chars,
        dry_run=args.dry_run,
    )
    _write_json(args.output, report)
    print(
        json.dumps(
            {"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if report["verdict"].startswith("NO_GO") else 0


if __name__ == "__main__":
    raise SystemExit(main())
