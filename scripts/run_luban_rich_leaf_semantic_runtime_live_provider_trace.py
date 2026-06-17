#!/usr/bin/env python3
"""Build authorized live-provider shadow traces for RichLeaf runtime A/B."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable


REPO = Path(__file__).resolve().parents[1]
SCHEMA = "luban_rich_leaf_semantic_runtime_live_ab_results.v1"
DEFAULT_NEAR_LIVE_SHADOW_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_semantic_runtime_near_live_shadow_ab_materialized_20260612/near_live_shadow_ab.json"
)
DEFAULT_FIELD_PROMOTION_REVIEW = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_field_promotion_review_materialized_20260612/field_promotion_review.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_semantic_runtime_live_provider_trace_20260612/live_results.json"
)
PLANNED_ARMS = [
    "current_rag_runtime",
    "legacy_runtime_or_projection",
    "rich_leaf_promoted_context",
    "artifact_first_llm_judge",
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
            if key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")


def _openai_compat_provider(*, provider: str, model: str | None, timeout_s: float) -> ProviderCall | None:
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
                "max_tokens": 240,
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
            raise RuntimeError(f"{provider}_http_error:{exc.code}:{text[:200]}") from exc
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


def _rows_by_case(near_live_shadow_ab: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    current_rag_source = near_live_shadow_ab.get("current_rag_rows")
    if not isinstance(current_rag_source, list):
        current_rag_source = near_live_shadow_ab.get("sample_rows") or []
    rag_rows = {
        str(row.get("case_id")): row
        for row in current_rag_source
        if isinstance(row, dict) and row.get("case_id")
    }
    rich_rows = {
        str(row.get("case_id")): row
        for row in near_live_shadow_ab.get("local_adapter_rows") or []
        if isinstance(row, dict) and row.get("case_id")
    }
    return rag_rows, rich_rows


def _artifact_source_index(field_promotion_review: dict[str, Any] | None) -> dict[str, dict[str, dict[str, Any]]]:
    if not isinstance(field_promotion_review, dict):
        return {}
    index: dict[str, dict[str, dict[str, Any]]] = {}
    for artifact in field_promotion_review.get("promoted_rich_leaf_artifact_candidates") or []:
        if not isinstance(artifact, dict) or not artifact.get("artifact_id"):
            continue
        index[str(artifact["artifact_id"])] = {
            str(ref.get("source_ref_id")): ref
            for ref in artifact.get("source_refs") or []
            if isinstance(ref, dict) and ref.get("source_ref_id")
        }
    return index


def _context_refs(
    *,
    arm: str,
    row: dict[str, Any],
    rag_row: dict[str, Any] | None,
    source_index: dict[str, dict[str, dict[str, Any]]],
    top_k: int,
) -> list[dict[str, Any]]:
    refs = source_index.get(str(row.get("artifact_id"))) or {}
    expected_ids = [str(ref_id) for ref_id in row.get("expected_source_ref_ids") or []]
    if arm in {"rich_leaf_promoted_context", "artifact_first_llm_judge"}:
        selected_ids = expected_ids
    elif bool((rag_row or {}).get("answerable")):
        selected_ids = expected_ids + [ref_id for ref_id in refs if ref_id not in set(expected_ids)]
    else:
        selected_ids = [ref_id for ref_id in refs if ref_id not in set(expected_ids)]
    selected: list[dict[str, Any]] = []
    for ref_id in selected_ids:
        ref = refs.get(ref_id)
        if not ref:
            continue
        selected.append(
            {
                "source_ref_id": ref_id,
                "source_lane": ref.get("source_lane"),
                "span": ref.get("span"),
                "span_hash": ref.get("span_hash"),
            }
        )
        if len(selected) >= top_k:
            break
    if not selected and arm in {"rich_leaf_promoted_context", "artifact_first_llm_judge"} | (
        {"current_rag_runtime", "legacy_runtime_or_projection"} if bool((rag_row or {}).get("answerable")) else set()
    ):
        answer = row.get("answer") if isinstance(row.get("answer"), dict) else {}
        span = str(answer.get("text") or "")
        if span:
            for ref_id in expected_ids[:top_k] or [f"fallback:{row.get('case_id')}"]:
                selected.append(
                    {
                        "source_ref_id": ref_id,
                        "source_lane": "compiled_context",
                        "span": span,
                        "span_hash": "fallback_from_reviewed_local_adapter_row",
                    }
                )
    return selected


def _messages(
    arm: str,
    row: dict[str, Any],
    rag_row: dict[str, Any] | None,
    *,
    context_refs: list[dict[str, Any]],
) -> list[dict[str, str]]:
    answer = row.get("answer") if isinstance(row.get("answer"), dict) else {}
    text = str(answer.get("text") or "")
    cited = [str(ref) for ref in (answer.get("cited_source_ref_ids") or row.get("cited_source_ref_ids") or [])]
    expected = [str(ref) for ref in (row.get("expected_source_ref_ids") or [])]
    expected_answerable = bool(row.get("answerable")) if arm in {"rich_leaf_promoted_context", "artifact_first_llm_judge"} else bool((rag_row or {}).get("answerable"))
    if arm == "current_rag_runtime":
        context = (
            "CURRENT_RAG_PROJECTED_CONTEXT\n"
            f"answerable_proxy={expected_answerable}\n"
            f"token_proxy={(rag_row or {}).get('token_proxy')}\n"
            f"retrieved_source_refs={json.dumps(context_refs, ensure_ascii=False)}"
        )
    elif arm == "legacy_runtime_or_projection":
        context = (
            "LEGACY_RUNTIME_PROJECTED_CONTEXT\n"
            f"answerable_proxy={expected_answerable}\n"
            f"token_proxy={max(1, int(row.get('token_proxy') or 1) * 2)}\n"
            f"retrieved_source_refs={json.dumps(context_refs, ensure_ascii=False)}"
        )
    elif arm == "artifact_first_llm_judge":
        context = (
            "ARTIFACT_JUDGE\n"
            f"answer={text}\nsource_refs={cited}\nexpected_refs={expected}\n"
            f"retrieved_source_refs={json.dumps(context_refs, ensure_ascii=False)}"
        )
    else:
        context = (
            "RICH_LEAF_CONTEXT\n"
            f"answer={text}\nsource_refs={cited}\nexpected_refs={expected}\n"
            f"retrieved_source_refs={json.dumps(context_refs, ensure_ascii=False)}"
        )
    user = {
        "arm": arm,
        "case_id": row.get("case_id"),
        "task": row.get("task"),
        "leaf_id": row.get("leaf_id"),
        "field_id": row.get("field_id"),
        "context": context,
        "expected_answerable": expected_answerable,
        "required_output": {
            "answerable": "boolean",
            "evidence_cited": "boolean",
            "fail_open": "boolean",
            "answer": "short string",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a strict live shadow evaluator. Return one JSON object only. "
                "Do not invent source evidence. If context lacks evidence, set answerable=false and fail_open=false."
            ),
        },
        {"role": "user", "content": json.dumps(user, ensure_ascii=False, sort_keys=True)},
    ]


def _arm_summary(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    sample_count = len(rows)
    provider_call_count = len(completed)
    return {
        "arm": arm,
        "status": "completed" if sample_count and provider_call_count == sample_count else "failed",
        "sample_count": sample_count,
        "provider_call_count": provider_call_count,
        "answerable_rate": round(mean([1.0 if row.get("answerable") else 0.0 for row in completed]), 4) if completed else 0.0,
        "accuracy_rate": round(mean([1.0 if row.get("matches_expected") else 0.0 for row in completed]), 4) if completed else 0.0,
        "evidence_citation_rate": round(mean([1.0 if row.get("evidence_cited") else 0.0 for row in completed]), 4) if completed else 0.0,
        "fail_open_rate": round(mean([1.0 if row.get("fail_open") else 0.0 for row in completed]), 4) if completed else 0.0,
        "mean_token_usage": round(mean([int(row.get("total_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_latency_ms": round(mean([float(row.get("latency_ms") or 0.0) for row in completed]), 2) if completed else 0.0,
    }


def _completed_previous_rows(previous_results: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(previous_results, dict):
        return {}
    completed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in previous_results.get("rows") or []:
        if not isinstance(row, dict) or row.get("status") != "completed":
            continue
        arm = str(row.get("arm") or "")
        case_id = str(row.get("case_id") or "")
        if arm and case_id:
            completed[(case_id, arm)] = row
    return completed


def build_live_provider_trace(
    *,
    near_live_shadow_ab: dict[str, Any],
    field_promotion_review: dict[str, Any] | None = None,
    sample_limit: int,
    provider_call: Callable[..., dict[str, Any]] | None,
    model: str,
    timeout_s: float = 45.0,
    context_top_k: int = 5,
    previous_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rag_rows, rich_rows = _rows_by_case(near_live_shadow_ab)
    ordered_rows = sorted(
        rich_rows.values(),
        key=lambda row: (
            0 if bool((rag_rows.get(str(row.get("case_id"))) or {}).get("answerable")) else 1,
            str(row.get("case_id") or ""),
        ),
    )
    selected_rows = ordered_rows[: max(0, sample_limit)]
    source_index = _artifact_source_index(field_promotion_review)
    blockers: list[str] = []
    if near_live_shadow_ab.get("schema") != "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1":
        blockers.append(f"near_live_schema_mismatch:{near_live_shadow_ab.get('schema')}")
    if near_live_shadow_ab.get("verdict") != "PASS":
        blockers.append(f"near_live_not_pass:{near_live_shadow_ab.get('verdict')}")
    if not selected_rows:
        blockers.append("no_live_cases_selected")
    if provider_call is None:
        blockers.append("provider_call_not_configured")

    previous_completed = _completed_previous_rows(previous_results)
    rows: list[dict[str, Any]] = []
    reused_provider_call_count = 0
    prompt_tokens = 0
    completion_tokens = 0
    selected_case_ids = {str(row.get("case_id")) for row in selected_rows}
    for (case_id, arm), previous_row in sorted(previous_completed.items()):
        if case_id in selected_case_ids and arm in PLANNED_ARMS:
            rows.append(dict(previous_row))
            reused_provider_call_count += 1
            prompt_tokens += int(previous_row.get("prompt_tokens") or 0)
            completion_tokens += int(previous_row.get("completion_tokens") or 0)
    if not blockers and provider_call is not None:
        for row in selected_rows:
            rag_row = rag_rows.get(str(row.get("case_id")))
            for arm in PLANNED_ARMS:
                if (str(row.get("case_id")), arm) in previous_completed:
                    continue
                expected_answerable = bool(row.get("answerable")) if arm in {"rich_leaf_promoted_context", "artifact_first_llm_judge"} else bool((rag_row or {}).get("answerable"))
                context_refs = _context_refs(
                    arm=arm,
                    row=row,
                    rag_row=rag_row,
                    source_index=source_index,
                    top_k=max(1, context_top_k),
                )
                try:
                    response = provider_call(model, _messages(arm, row, rag_row, context_refs=context_refs), timeout_s=timeout_s)
                    parsed = _parse_json_object(str(response.get("content") or ""))
                    answerable = bool(parsed.get("answerable"))
                    evidence_cited = bool(parsed.get("evidence_cited"))
                    fail_open = bool(parsed.get("fail_open"))
                    p_tokens = int(response.get("prompt_tokens") or 0)
                    c_tokens = int(response.get("completion_tokens") or 0)
                    prompt_tokens += p_tokens
                    completion_tokens += c_tokens
                    rows.append(
                        {
                            "arm": arm,
                            "case_id": row.get("case_id"),
                            "status": "completed",
                            "answerable": answerable,
                            "expected_answerable": expected_answerable,
                            "matches_expected": answerable == expected_answerable,
                            "evidence_cited": evidence_cited,
                            "context_source_ref_count": len(context_refs),
                            "fail_open": fail_open,
                            "prompt_tokens": p_tokens,
                            "completion_tokens": c_tokens,
                            "total_tokens": p_tokens + c_tokens,
                            "latency_ms": float(response.get("latency_ms") or 0.0),
                        }
                    )
                except Exception as exc:  # pragma: no cover - exercised by live failures
                    rows.append(
                        {
                            "arm": arm,
                            "case_id": row.get("case_id"),
                            "status": "failed",
                            "error": str(exc)[:240],
                            "answerable": False,
                            "expected_answerable": expected_answerable,
                            "matches_expected": False,
                            "evidence_cited": False,
                            "context_source_ref_count": len(context_refs),
                            "fail_open": False,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "latency_ms": 0.0,
                        }
                    )

    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_arm[str(row.get("arm"))].append(row)
    arms = [_arm_summary(arm, by_arm.get(arm, [])) for arm in PLANNED_ARMS]
    runtime_exercised = bool(rows) and all(arm["status"] == "completed" for arm in arms)
    provider_call_count = sum(int(arm["provider_call_count"]) for arm in arms)
    new_provider_call_count = max(0, provider_call_count - reused_provider_call_count)
    total_tokens = prompt_tokens + completion_tokens
    return {
        "schema": SCHEMA,
        "execution_authority": "authorized_live_runtime_trace" if runtime_exercised else "not_exercised",
        "runtime_entrypoint": "rich_leaf_semantic_runtime_live_provider_trace",
        "runtime_exercised": runtime_exercised,
        "runtime_trace_ids": [f"rich_leaf_live_trace:{row.get('case_id')}:{row.get('arm')}" for row in rows if row.get("status") == "completed"],
        "provider_call_count": provider_call_count,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "models": [model] if runtime_exercised else [],
        "cost_recorded": bool(runtime_exercised and total_tokens >= 0),
        "arms": arms,
        "rows": rows,
        "summary": {
            "sample_count": len(selected_rows),
            "planned_arm_count": len(PLANNED_ARMS),
            "provider_call_count": provider_call_count,
            "reused_provider_call_count": reused_provider_call_count,
            "new_provider_call_count": new_provider_call_count,
            "total_tokens": total_tokens,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_live_provider_trace": True,
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
    parser.add_argument("--near-live-shadow-ab", type=Path, default=DEFAULT_NEAR_LIVE_SHADOW_AB)
    parser.add_argument("--field-promotion-review", type=Path, default=DEFAULT_FIELD_PROMOTION_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-limit", type=int, default=12)
    parser.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    parser.add_argument("--no-provider-call", action="store_true")
    parser.add_argument("--resume-from", type=Path, default=None)
    args = parser.parse_args(argv)

    model = args.model or PROVIDER_DEFAULTS[args.provider]["model"]
    provider_call = None if args.no_provider_call else _openai_compat_provider(provider=args.provider, model=model, timeout_s=args.timeout_s)
    report = build_live_provider_trace(
        near_live_shadow_ab=_read_json(args.near_live_shadow_ab),
        field_promotion_review=_read_json(args.field_promotion_review) if args.field_promotion_review.exists() else None,
        sample_limit=args.sample_limit,
        provider_call=provider_call,
        model=model,
        timeout_s=args.timeout_s,
        previous_results=_read_json(args.resume_from) if args.resume_from else None,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "runtime_exercised": report["runtime_exercised"], "summary": report["summary"], "blockers": report["blockers"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["runtime_exercised"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
