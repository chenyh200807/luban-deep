#!/usr/bin/env python3
"""AI shadow-review weak RuntimeTokenPack v2 taxonomy leaf links."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v2_20260612/runtime_token_pack_v2.json"
)
DEFAULT_TAXONOMY_LINKING = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v2_taxonomy_leaf_linking_20260612/taxonomy_leaf_linking_dedup.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v2_taxonomy_shadow_review_20260612/taxonomy_shadow_review.json"
)
SCHEMA = "luban_rich_leaf_v2_taxonomy_shadow_review.v1"
LINKING_SCHEMA = "luban_rich_leaf_v2_taxonomy_leaf_linking.v1"
TOKEN_PACK_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2"
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


def _units_by_id(runtime_token_pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(unit.get("unit_id")): unit
        for unit in runtime_token_pack.get("runtime_token_pack_units") or []
        if isinstance(unit, dict) and unit.get("unit_id")
    }


def _messages(link: dict[str, Any], unit: dict[str, Any]) -> list[dict[str, str]]:
    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    compiled_context = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
    candidates = [
        {
            "leaf_id": candidate.get("leaf_id"),
            "name_path": candidate.get("name_path"),
            "score": candidate.get("score"),
            "match_reasons": candidate.get("match_reasons"),
        }
        for candidate in link.get("candidate_leaf_links") or []
        if isinstance(candidate, dict)
    ]
    user_payload = {
        "task": "Review whether this source-file context unit should be linked to one canonical terminal taxonomy leaf.",
        "allowed_decisions": [
            "accept_shadow_leaf_link",
            "needs_terminal_leaf_split",
            "reject_no_matching_leaf",
        ],
        "rules": [
            "Choose only from candidate_leaf_links; never invent a leaf_id.",
            "Accept only if source excerpt and compiled context primarily support one terminal leaf.",
            "Use needs_terminal_leaf_split when the source file covers multiple leaves or the evidence is broad chapter/index material.",
            "Use reject_no_matching_leaf when all candidate leaves are off-path.",
            "Return JSON only.",
        ],
        "unit": {
            "unit_id": unit.get("unit_id"),
            "candidate_id": unit.get("candidate_id"),
            "relative_path": unit.get("relative_path"),
            "source_lane": unit.get("source_lane"),
            "compiled_context": compiled_context,
            "source_ref": {
                "source_lane": source_ref.get("source_lane"),
                "source_path": source_ref.get("source_path"),
                "record_id": source_ref.get("record_id"),
                "span_hash": source_ref.get("span_hash"),
                "excerpt": source_ref.get("excerpt"),
            },
        },
        "candidate_leaf_links": candidates,
        "required_output_schema": {
            "decision": "accept_shadow_leaf_link|needs_terminal_leaf_split|reject_no_matching_leaf",
            "accepted_leaf_id": "one candidate leaf_id or null",
            "confidence": "high|medium|low",
            "rationale": "short Chinese text",
            "risk_codes": ["broad_source_file|wrong_path|multi_leaf|weak_evidence|none"],
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a strict taxonomy shadow reviewer. You may only select from provided canonical "
                "leaf candidates. You cannot create taxonomy, runtime defaults, release truth, or official scores."
            ),
        },
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True)},
    ]


def _input_blockers(runtime_token_pack: dict[str, Any], taxonomy_linking: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if runtime_token_pack.get("schema") != TOKEN_PACK_SCHEMA:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    if taxonomy_linking.get("schema") != LINKING_SCHEMA:
        blockers.append(f"taxonomy_linking_schema_mismatch:{taxonomy_linking.get('schema')}")
    if taxonomy_linking.get("verdict") != "PASS_TAXONOMY_LEAF_LINKING_SHADOW_CANDIDATES":
        blockers.append(f"taxonomy_linking_not_pass:{taxonomy_linking.get('verdict')}")
    for name, payload in (("runtime_token_pack", runtime_token_pack), ("taxonomy_linking", taxonomy_linking)):
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


def _decision_from_provider(
    *,
    link: dict[str, Any],
    unit: dict[str, Any],
    provider_call: ProviderCall,
    model: str,
    timeout_s: float,
) -> dict[str, Any]:
    result = provider_call(model, _messages(link, unit), timeout_s=timeout_s)
    parsed = _parse_json_object(str(result.get("content") or ""))
    candidate_ids = {str(candidate.get("leaf_id")) for candidate in link.get("candidate_leaf_links") or [] if isinstance(candidate, dict)}
    decision = str(parsed.get("decision") or "")
    accepted_leaf_id = parsed.get("accepted_leaf_id")
    if accepted_leaf_id is not None:
        accepted_leaf_id = str(accepted_leaf_id)
    valid = decision in {"accept_shadow_leaf_link", "needs_terminal_leaf_split", "reject_no_matching_leaf"}
    if decision == "accept_shadow_leaf_link" and accepted_leaf_id not in candidate_ids:
        valid = False
        decision = "needs_terminal_leaf_split"
        accepted_leaf_id = None
    return {
        "review_id": f"taxonomy_shadow_review:{link.get('link_id')}",
        "link_id": link.get("link_id"),
        "unit_id": link.get("unit_id"),
        "decision": decision if valid else "needs_terminal_leaf_split",
        "accepted_leaf_id": accepted_leaf_id if decision == "accept_shadow_leaf_link" else None,
        "confidence": str(parsed.get("confidence") or "low"),
        "rationale": str(parsed.get("rationale") or "")[:500],
        "risk_codes": parsed.get("risk_codes") if isinstance(parsed.get("risk_codes"), list) else ["weak_evidence"],
        "provider": {
            "model": result.get("model"),
            "prompt_tokens": int(result.get("prompt_tokens") or 0),
            "completion_tokens": int(result.get("completion_tokens") or 0),
            "latency_ms": float(result.get("latency_ms") or 0.0),
        },
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "production_default": False,
    }


def run_taxonomy_shadow_review(
    *,
    runtime_token_pack: dict[str, Any],
    taxonomy_linking: dict[str, Any],
    provider_call: ProviderCall | None,
    model: str,
    start_index: int,
    max_links: int | None,
    max_workers: int,
    progress_every: int,
    timeout_s: float,
) -> dict[str, Any]:
    blockers = _input_blockers(runtime_token_pack, taxonomy_linking)
    if provider_call is None:
        blockers.append("provider_call_not_configured")
    units = _units_by_id(runtime_token_pack)
    weak_links = [
        link
        for link in taxonomy_linking.get("taxonomy_leaf_links") or []
        if isinstance(link, dict) and link.get("status") == "weak_link_candidate" and str(link.get("unit_id")) in units
    ]
    selected = weak_links[max(0, start_index) :]
    if max_links is not None:
        selected = selected[: max(0, max_links)]
    decisions: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    if not blockers and provider_call is not None:
        def run_one(link: dict[str, Any]) -> dict[str, Any]:
            return _decision_from_provider(
                link=link,
                unit=units[str(link.get("unit_id"))],
                provider_call=provider_call,
                model=model,
                timeout_s=timeout_s,
            )

        completed = 0
        if max_workers <= 1:
            for link in selected:
                try:
                    decisions.append(run_one(link))
                except Exception as exc:  # pragma: no cover
                    errors.append({"link_id": link.get("link_id"), "unit_id": link.get("unit_id"), "error": str(exc)[:240]})
                completed += 1
                if progress_every and completed % progress_every == 0:
                    print(f"taxonomy_shadow_review_progress completed={completed}/{len(selected)}", file=sys.stderr, flush=True)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(run_one, link): link for link in selected}
                for future in as_completed(futures):
                    link = futures[future]
                    try:
                        decisions.append(future.result())
                    except Exception as exc:  # pragma: no cover
                        errors.append({"link_id": link.get("link_id"), "unit_id": link.get("unit_id"), "error": str(exc)[:240]})
                    completed += 1
                    if progress_every and completed % progress_every == 0:
                        print(f"taxonomy_shadow_review_progress completed={completed}/{len(selected)}", file=sys.stderr, flush=True)

    decision_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    for decision in decisions:
        decision_counts[str(decision.get("decision"))] = decision_counts.get(str(decision.get("decision")), 0) + 1
        confidence_counts[str(decision.get("confidence"))] = confidence_counts.get(str(decision.get("confidence")), 0) + 1
    provider_calls = len(decisions)
    prompt_tokens = sum(int(decision.get("provider", {}).get("prompt_tokens") or 0) for decision in decisions)
    completion_tokens = sum(int(decision.get("provider", {}).get("completion_tokens") or 0) for decision in decisions)
    verdict = "PASS_TAXONOMY_SHADOW_REVIEW" if not blockers and not errors else "NO_GO_TAXONOMY_SHADOW_REVIEW_INCOMPLETE"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "summary": {
            "blocker_count": len(blockers),
            "input_weak_link_count": len(weak_links),
            "selected_link_count": len(selected),
            "decision_count": len(decisions),
            "error_count": len(errors),
            "decision_counts": decision_counts,
            "confidence_counts": confidence_counts,
            "provider_call_count": provider_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        "decisions": sorted(decisions, key=lambda item: str(item.get("link_id"))),
        "errors": errors,
        "blockers": blockers,
        "not_exercised": [
            "manual_taxonomy_review",
            "canonical_leaf_pointer_write",
            "runtime_default_install",
            "production_db_write",
            "release_truth_governance",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "taxonomy_shadow_review": True,
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
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--taxonomy-linking", type=Path, default=DEFAULT_TAXONOMY_LINKING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--max-links", type=int, default=None)
    parser.add_argument("--max-workers", type=int, default=6)
    parser.add_argument("--progress-every", type=int, default=20)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    parser.add_argument("--max-tokens", type=int, default=220)
    parser.add_argument("--no-provider-call", action="store_true")
    args = parser.parse_args(argv)
    model = args.model or PROVIDER_DEFAULTS[args.provider]["model"]
    provider_call = None if args.no_provider_call else _openai_compat_provider(
        provider=args.provider,
        model=model,
        timeout_s=args.timeout_s,
        max_tokens=args.max_tokens,
    )
    report = run_taxonomy_shadow_review(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        taxonomy_linking=_read_json(args.taxonomy_linking),
        provider_call=provider_call,
        model=model,
        start_index=args.start_index,
        max_links=args.max_links,
        max_workers=args.max_workers,
        progress_every=args.progress_every,
        timeout_s=args.timeout_s,
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS_TAXONOMY_SHADOW_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
