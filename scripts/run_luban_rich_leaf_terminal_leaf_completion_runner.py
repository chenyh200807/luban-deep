#!/usr/bin/env python3
"""Complete remaining RuntimeTokenPack v2 units into terminal-leaf shadow candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_WORK_ORDERS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_terminal_leaf_completion_work_orders_20260612/terminal_leaf_completion_work_orders.json"
)
DEFAULT_TAXONOMY_INDEX = (
    REPO / "deeptutor/services/construction_grading/runtime_supply/v_canonical_taxonomy_index/canonical_taxonomy_index.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_terminal_leaf_completion_20260612/terminal_leaf_completion.json"
)
SCHEMA = "luban_rich_leaf_terminal_leaf_completion.v1"
WORK_ORDERS_SCHEMA = "luban_rich_leaf_terminal_leaf_completion_work_orders.v1"
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


def _dedupe_taxonomy(taxonomy_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    leaves: dict[str, dict[str, Any]] = {}
    for leaf in taxonomy_index.get("leaves") or []:
        if not isinstance(leaf, dict) or not leaf.get("code"):
            continue
        code = str(leaf["code"])
        current = leaves.setdefault(code, {"leaf_id": code, "name_path": leaf.get("name_path"), "keywords": []})
        if not current.get("name_path") and leaf.get("name_path"):
            current["name_path"] = leaf.get("name_path")
        keywords = current["keywords"]
        for keyword in leaf.get("keywords") or []:
            text = str(keyword).strip()
            if text and text not in keywords:
                keywords.append(text)
    return leaves


def _segments(text: str) -> list[str]:
    return [part for part in re.split(r"[>\s/、，,。；;：:（）()\[\]【】《》\"'“”]+", text) if len(part) >= 2]


def _fallback_candidates(order: dict[str, Any], taxonomy_by_id: dict[str, dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    unit = order.get("unit") if isinstance(order.get("unit"), dict) else {}
    compiled_context = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    terms: list[str] = [str(unit.get("relative_path") or ""), str(source_ref.get("excerpt") or "")]
    for values in compiled_context.values():
        if isinstance(values, list):
            terms.extend(str(value) for value in values)
    haystack = "\n".join(terms)
    rows: list[dict[str, Any]] = []
    for leaf in taxonomy_by_id.values():
        score = 0
        reasons: list[str] = []
        for keyword in leaf.get("keywords") or []:
            if len(str(keyword)) >= 2 and str(keyword) in haystack:
                score += 5
                reasons.append(f"keyword:{keyword}")
        for segment in _segments(str(leaf.get("name_path") or ""))[-4:]:
            if segment in haystack:
                score += 3
                reasons.append(f"name_path:{segment}")
        if score > 0:
            rows.append({"leaf_id": leaf["leaf_id"], "name_path": leaf.get("name_path"), "score": score, "match_reasons": reasons[:8]})
    rows.sort(key=lambda item: (-int(item["score"]), str(item["leaf_id"])))
    return rows[:top_k]


def _candidate_leaf_pool(order: dict[str, Any], taxonomy_by_id: dict[str, dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    pool: list[dict[str, Any]] = []
    link = order.get("taxonomy_link") if isinstance(order.get("taxonomy_link"), dict) else {}
    for candidate in link.get("candidate_leaf_links") or []:
        if not isinstance(candidate, dict) or not candidate.get("leaf_id"):
            continue
        leaf_id = str(candidate["leaf_id"])
        if leaf_id in seen or leaf_id not in taxonomy_by_id:
            continue
        seen.add(leaf_id)
        leaf = taxonomy_by_id[leaf_id]
        pool.append({"leaf_id": leaf_id, "name_path": leaf.get("name_path"), "score": candidate.get("score"), "match_reasons": candidate.get("match_reasons")})
    for candidate in _fallback_candidates(order, taxonomy_by_id, top_k * 2):
        leaf_id = str(candidate["leaf_id"])
        if leaf_id in seen:
            continue
        seen.add(leaf_id)
        pool.append(candidate)
        if len(pool) >= top_k:
            break
    return pool[:top_k]


def _messages(order: dict[str, Any], candidate_leaf_pool: list[dict[str, Any]]) -> list[dict[str, str]]:
    unit = order.get("unit") if isinstance(order.get("unit"), dict) else {}
    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    payload = {
        "task": "Complete this broad source-file RuntimeTokenPack unit into terminal-leaf shadow candidates.",
        "reason": order.get("reason"),
        "rules": [
            "Select only leaf_id values from candidate_leaf_pool.",
            "For split work, return 1 to 3 terminal_leaf_units if evidence supports them.",
            "For rejected work, return a unit only if candidate_leaf_pool contains a clearly better canonical leaf.",
            "If uncertain, return unresolved_reason instead of forcing a leaf.",
            "Do not invent taxonomy, source truth, official score, or runtime default.",
        ],
        "unit": {
            "unit_id": unit.get("unit_id"),
            "candidate_id": unit.get("candidate_id"),
            "relative_path": unit.get("relative_path"),
            "source_lane": unit.get("source_lane"),
            "compiled_context": unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {},
            "source_ref": {
                "source_lane": source_ref.get("source_lane"),
                "source_path": source_ref.get("source_path"),
                "record_id": source_ref.get("record_id"),
                "span_hash": source_ref.get("span_hash"),
                "excerpt": source_ref.get("excerpt"),
            },
        },
        "shadow_review": order.get("shadow_review"),
        "candidate_leaf_pool": candidate_leaf_pool,
        "required_output_schema": {
            "terminal_leaf_units": [
                {
                    "leaf_id": "candidate leaf id",
                    "confidence": "high|medium|low",
                    "support_rationale": "short Chinese text",
                    "selected_context_fields": {"concepts": [], "rules": [], "procedures": [], "numeric_constraints": [], "exam_patterns": []},
                }
            ],
            "unresolved_reason": "null or short text",
        },
    }
    return [
        {"role": "system", "content": "You are a strict terminal-leaf compiler. Use only provided canonical leaf candidates."},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def _completion_from_provider(
    order: dict[str, Any],
    taxonomy_by_id: dict[str, dict[str, Any]],
    provider_call: ProviderCall,
    model: str,
    timeout_s: float,
    top_k: int,
) -> dict[str, Any]:
    candidate_pool = _candidate_leaf_pool(order, taxonomy_by_id, top_k)
    result = provider_call(model, _messages(order, candidate_pool), timeout_s=timeout_s)
    parsed = _parse_json_object(str(result.get("content") or ""))
    allowed_ids = {str(candidate["leaf_id"]) for candidate in candidate_pool}
    unit = order.get("unit") if isinstance(order.get("unit"), dict) else {}
    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    terminal_units: list[dict[str, Any]] = []
    for child in parsed.get("terminal_leaf_units") or []:
        if not isinstance(child, dict) or str(child.get("leaf_id")) not in allowed_ids:
            continue
        leaf = taxonomy_by_id[str(child["leaf_id"])]
        key = f"{unit.get('unit_id')}:{child.get('leaf_id')}:{source_ref.get('span_hash')}:{len(terminal_units)}"
        selected_context = child.get("selected_context_fields") if isinstance(child.get("selected_context_fields"), dict) else {}
        terminal_units.append(
            {
                "unit_id": f"rtp22_{hashlib.sha256(key.encode()).hexdigest()[:16]}",
                "parent_unit_id": unit.get("unit_id"),
                "completion_work_order_id": order.get("work_order_id"),
                "leaf_id": child.get("leaf_id"),
                "leaf_name_path": leaf.get("name_path"),
                "source_lane": unit.get("source_lane"),
                "relative_path": unit.get("relative_path"),
                "compiled_context": {k: v[:2] for k, v in selected_context.items() if isinstance(v, list) and v},
                "source_ref": {
                    "source_lane": source_ref.get("source_lane"),
                    "source_path": source_ref.get("source_path"),
                    "record_id": source_ref.get("record_id"),
                    "span_hash": source_ref.get("span_hash"),
                    "file_sha256": source_ref.get("file_sha256"),
                },
                "review_source": "terminal_leaf_completion_ai_shadow",
                "confidence": child.get("confidence") or "low",
                "support_rationale": str(child.get("support_rationale") or "")[:500],
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "production_default": False,
            }
        )
        if len(terminal_units) >= 3:
            break
    return {
        "work_order_id": order.get("work_order_id"),
        "parent_unit_id": unit.get("unit_id"),
        "reason": order.get("reason"),
        "status": "completed" if terminal_units else "unresolved",
        "terminal_leaf_units": terminal_units,
        "unresolved_reason": None if terminal_units else str(parsed.get("unresolved_reason") or "no_valid_canonical_leaf_selected")[:500],
        "candidate_leaf_pool": candidate_pool,
        "provider": {
            "model": result.get("model"),
            "prompt_tokens": int(result.get("prompt_tokens") or 0),
            "completion_tokens": int(result.get("completion_tokens") or 0),
            "latency_ms": float(result.get("latency_ms") or 0.0),
        },
    }


def _input_blockers(work_orders: dict[str, Any], taxonomy_index: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if work_orders.get("schema") != WORK_ORDERS_SCHEMA:
        blockers.append(f"work_orders_schema_mismatch:{work_orders.get('schema')}")
    if work_orders.get("verdict") != "READY_FOR_TERMINAL_LEAF_COMPLETION_SHADOW":
        blockers.append(f"work_orders_not_ready:{work_orders.get('verdict')}")
    manifest = taxonomy_index.get("manifest") if isinstance(taxonomy_index.get("manifest"), dict) else {}
    if manifest.get("schema_version") != "luban_canonical_taxonomy_index.v1":
        blockers.append(f"taxonomy_schema_mismatch:{manifest.get('schema_version')}")
    for name, payload in (("work_orders", work_orders),):
        safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
        classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
        if classification.get("runtime_install_allowed") is not False:
            blockers.append(f"{name}_runtime_install_allowed")
        if safety.get("production_write_count", 0) not in (0, None):
            blockers.append(f"{name}_production_write_count_nonzero")
    return blockers


def run_terminal_leaf_completion(
    *,
    work_orders: dict[str, Any],
    taxonomy_index: dict[str, Any],
    provider_call: ProviderCall | None,
    model: str,
    start_index: int,
    max_work_orders: int | None,
    max_workers: int,
    progress_every: int,
    timeout_s: float,
    top_k: int,
) -> dict[str, Any]:
    blockers = _input_blockers(work_orders, taxonomy_index)
    if provider_call is None:
        blockers.append("provider_call_not_configured")
    taxonomy_by_id = _dedupe_taxonomy(taxonomy_index)
    orders = [order for order in work_orders.get("work_orders") or [] if isinstance(order, dict)]
    selected = orders[max(0, start_index) :]
    if max_work_orders is not None:
        selected = selected[: max(0, max_work_orders)]
    completions: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    if not blockers and provider_call is not None:
        def run_one(order: dict[str, Any]) -> dict[str, Any]:
            return _completion_from_provider(order, taxonomy_by_id, provider_call, model, timeout_s, top_k)

        completed = 0
        if max_workers <= 1:
            for order in selected:
                try:
                    completions.append(run_one(order))
                except Exception as exc:  # pragma: no cover
                    errors.append({"work_order_id": order.get("work_order_id"), "error": str(exc)[:240]})
                completed += 1
                if progress_every and completed % progress_every == 0:
                    print(f"terminal_leaf_completion_progress completed={completed}/{len(selected)}", file=sys.stderr, flush=True)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(run_one, order): order for order in selected}
                for future in as_completed(futures):
                    order = futures[future]
                    try:
                        completions.append(future.result())
                    except Exception as exc:  # pragma: no cover
                        errors.append({"work_order_id": order.get("work_order_id"), "error": str(exc)[:240]})
                    completed += 1
                    if progress_every and completed % progress_every == 0:
                        print(f"terminal_leaf_completion_progress completed={completed}/{len(selected)}", file=sys.stderr, flush=True)

    completed_count = sum(1 for completion in completions if completion.get("status") == "completed")
    terminal_unit_count = sum(len(completion.get("terminal_leaf_units") or []) for completion in completions)
    prompt_tokens = sum(int(completion.get("provider", {}).get("prompt_tokens") or 0) for completion in completions)
    completion_tokens = sum(int(completion.get("provider", {}).get("completion_tokens") or 0) for completion in completions)
    verdict = "PASS_TERMINAL_LEAF_COMPLETION_SHADOW" if not blockers and not errors else "NO_GO_TERMINAL_LEAF_COMPLETION_INCOMPLETE"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "summary": {
            "blocker_count": len(blockers),
            "input_work_order_count": len(orders),
            "selected_work_order_count": len(selected),
            "completion_count": len(completions),
            "completed_work_order_count": completed_count,
            "unresolved_work_order_count": len(completions) - completed_count,
            "terminal_leaf_unit_count": terminal_unit_count,
            "error_count": len(errors),
            "provider_call_count": len(completions),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        "completions": sorted(completions, key=lambda item: str(item.get("work_order_id"))),
        "errors": errors,
        "blockers": blockers,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "terminal_leaf_completion": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
        "not_exercised": [
            "manual_terminal_leaf_review",
            "canonical_truth_write",
            "runtime_default_install",
            "production_db_write",
            "release_truth_claim",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-orders", type=Path, default=DEFAULT_WORK_ORDERS)
    parser.add_argument("--taxonomy-index", type=Path, default=DEFAULT_TAXONOMY_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--max-work-orders", type=int, default=None)
    parser.add_argument("--max-workers", type=int, default=6)
    parser.add_argument("--progress-every", type=int, default=20)
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--max-tokens", type=int, default=450)
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--no-provider-call", action="store_true")
    args = parser.parse_args(argv)
    model = args.model or PROVIDER_DEFAULTS[args.provider]["model"]
    provider_call = None if args.no_provider_call else _openai_compat_provider(
        provider=args.provider,
        model=model,
        timeout_s=args.timeout_s,
        max_tokens=args.max_tokens,
    )
    report = run_terminal_leaf_completion(
        work_orders=_read_json(args.work_orders),
        taxonomy_index=_read_json(args.taxonomy_index),
        provider_call=provider_call,
        model=model,
        start_index=args.start_index,
        max_work_orders=args.max_work_orders,
        max_workers=args.max_workers,
        progress_every=args.progress_every,
        timeout_s=args.timeout_s,
        top_k=max(1, args.top_k),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS_TERMINAL_LEAF_COMPLETION_SHADOW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
