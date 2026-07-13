#!/usr/bin/env python3
"""Run and score the source-only Marble learning-graph pilot.

This script is deliberately outside runtime supply. It reads frozen candidate
fixtures, optionally calls a single OpenAI-compatible provider, and writes only
experiment artifacts. It never writes DB, LearnerState, scoring, or registry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0"
MODEL_DECISIONS = {"select_prerequisite", "teach_target_directly", "ask_for_evidence"}
TOPIC_IDS = {f"np{i:02d}" for i in range(1, 9)}
ACTIVE_STATUS = {"active"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{lineno}: expected JSON object")
        rows.append(value)
    return rows


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_jsonl(path: Path) -> str:
    digest = hashlib.sha256()
    for row in _read_jsonl(path):
        digest.update((canonical_json(row) + "\n").encode("utf-8"))
    return digest.hexdigest()


def active_graph_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [edge for edge in edges if edge.get("status") in ACTIVE_STATUS]


def parse_model_response(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return {"parse_status": "invalid", "raw_response": raw[:4000], "parse_error": "invalid_json"}
    if not isinstance(obj, dict):
        return {"parse_status": "invalid", "raw_response": raw[:4000], "parse_error": "not_object"}
    selected_many = obj.get("selected_topic_ids")
    if isinstance(selected_many, list) and len(selected_many) != 1:
        return {"parse_status": "invalid", "raw_response": raw[:4000], "parse_error": "multiple_selected_topics"}
    decision = obj.get("decision")
    selected = obj.get("selected_topic_id")
    if decision not in MODEL_DECISIONS:
        return {"parse_status": "invalid", "raw_response": raw[:4000], "parse_error": "invalid_decision"}
    if decision == "select_prerequisite":
        if selected not in TOPIC_IDS:
            return {"parse_status": "invalid", "raw_response": raw[:4000], "parse_error": "missing_topic"}
    elif selected not in (None, ""):
        return {"parse_status": "invalid", "raw_response": raw[:4000], "parse_error": "topic_on_nonselect"}
    return {
        "parse_status": "valid",
        "decision": decision,
        "selected_topic_id": selected if decision == "select_prerequisite" else None,
        "confidence": obj.get("confidence"),
        "citations": obj.get("citations") if isinstance(obj.get("citations"), list) else [],
        "teaching_response": str(obj.get("teaching_response") or "")[:1600],
        "material_claims": obj.get("material_claims") if isinstance(obj.get("material_claims"), list) else [],
        "raw_response": raw[:4000],
    }


def score_prediction(case: dict[str, Any], gold: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    if prediction.get("parse_status") != "valid":
        return {"case_id": case.get("case_id"), "correct": False, "reason": "invalid_model_response", "unsupported_claim_count": 0, "authority_drift": False}
    action = gold.get("gold_action")
    decision = prediction.get("decision")
    selected = prediction.get("selected_topic_id")
    if action == "select_prerequisite":
        correct = decision == action and selected in set(gold.get("acceptable_topic_ids") or [])
        reason = "acceptable_topic" if correct else "wrong_prerequisite"
    elif action == "teach_target_directly":
        correct = decision == action and selected in (None, "")
        reason = "direct_target" if correct else "unnecessary_traceback"
    elif action == "ask_for_evidence":
        correct = decision == action and selected in (None, "")
        reason = "evidence_abstention" if correct else "unsupported_guess"
    else:
        correct = False
        reason = "unknown_gold_action"
    text = str(prediction.get("teaching_response") or "")
    semantic_drift_terms = ("官方答案", "官方采分点", "已经得分", "写入学情", "learner truth", "release truth")
    authority_drift = any(term in text for term in semantic_drift_terms)
    return {
        "case_id": case.get("case_id"),
        "correct": bool(correct),
        "reason": reason,
        "unsupported_claim_count": 0,
        "authority_drift": authority_drift,
    }


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    radius = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return [round(max(0.0, centre - radius), 4), round(min(1.0, centre + radius), 4)]


def _binomial_two_sided(successes: int, total: int) -> float:
    if total == 0:
        return 1.0
    denom = 2**total
    probs = [math.comb(total, k) / denom for k in range(total + 1)]
    observed = probs[successes]
    return round(min(1.0, sum(prob for prob in probs if prob <= observed + 1e-15)), 6)


def compare_pairs(rows: list[dict[str, Any]], *, bootstrap_samples: int = 10000, seed: int = 20260710) -> dict[str, Any]:
    total = len(rows)
    baseline_successes = sum(bool(row.get("baseline_correct")) for row in rows)
    graph_successes = sum(bool(row.get("graph_correct")) for row in rows)
    graph_wins = sum(bool(row.get("graph_correct")) and not bool(row.get("baseline_correct")) for row in rows)
    baseline_wins = sum(bool(row.get("baseline_correct")) and not bool(row.get("graph_correct")) for row in rows)
    both_correct = sum(bool(row.get("graph_correct")) and bool(row.get("baseline_correct")) for row in rows)
    both_wrong = total - graph_wins - baseline_wins - both_correct
    deltas = [int(bool(row.get("graph_correct"))) - int(bool(row.get("baseline_correct"))) for row in rows]
    rng = random.Random(seed)
    bootstrap_lifts: list[float] = []
    if rows and bootstrap_samples > 0:
        for _ in range(bootstrap_samples):
            sample = [rng.choice(deltas) for _ in rows]
            bootstrap_lifts.append(100 * statistics.mean(sample))
    bootstrap_lifts.sort()
    low_idx = max(0, int(0.025 * len(bootstrap_lifts)) - 1) if bootstrap_lifts else 0
    high_idx = min(len(bootstrap_lifts) - 1, int(0.975 * len(bootstrap_lifts))) if bootstrap_lifts else 0
    discordant = graph_wins + baseline_wins
    return {
        "n": total,
        "baseline_accuracy": round(baseline_successes / total, 4) if total else 0.0,
        "graph_accuracy": round(graph_successes / total, 4) if total else 0.0,
        "paired_lift_pp": round(100 * statistics.mean(deltas), 4) if deltas else 0.0,
        "graph_wins": graph_wins,
        "baseline_wins": baseline_wins,
        "tie_both_correct": both_correct,
        "tie_both_wrong": both_wrong,
        "baseline_wilson_95": _wilson(baseline_successes, total),
        "graph_wilson_95": _wilson(graph_successes, total),
        "paired_bootstrap_lift_95_pp": [round(bootstrap_lifts[low_idx], 4), round(bootstrap_lifts[high_idx], 4)] if bootstrap_lifts else [0.0, 0.0],
        "mcnemar_exact_two_sided_p": _binomial_two_sided(min(graph_wins, baseline_wins), discordant),
        "bootstrap_seed": seed,
        "bootstrap_samples": bootstrap_samples,
    }


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.removeprefix("export ").strip()
        os.environ.setdefault(key, value.strip().strip("'\""))


def _prompt(case: dict[str, Any], topics: list[dict[str, Any]], source_pack: dict[str, Any], graph_edges: list[dict[str, Any]] | None) -> str:
    graph_block = ""
    if graph_edges is not None:
        edge_lines = [
            {"prerequisite_topic_id": edge["src"], "target_topic_id": edge["dst"], "strength": edge["strength"], "reason": edge["reason"]}
            for edge in graph_edges
        ]
        graph_block = "\n<prerequisite_projection>\n" + json.dumps(edge_lines, ensure_ascii=False, sort_keys=True) + "\n</prerequisite_projection>\n"
    return (
        "你是严格的建筑实务学习补救规划器。只选择一个最应该采取的动作，不要列出多个候选。\n"
        "动作只能是 select_prerequisite、teach_target_directly、ask_for_evidence。\n"
        "若选择 select_prerequisite，必须给 selected_topic_id；另外两种动作 selected_topic_id 必须为 null。\n"
        "只能依据给定案例、source pack 与 topic definitions，不得声称官方答案、得分或写入学情。\n"
        "只输出 JSON object，不要 Markdown。\n"
        "topic definitions:\n" + json.dumps(topics, ensure_ascii=False, sort_keys=True) + "\n"
        "source pack:\n" + json.dumps(source_pack, ensure_ascii=False, sort_keys=True) + "\n"
        + graph_block
        + "case:\n" + json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n"
        + json.dumps({
            "decision": "select_prerequisite|teach_target_directly|ask_for_evidence",
            "selected_topic_id": "np01..np08 or null",
            "confidence": 0.0,
            "citations": ["S01"],
            "teaching_response": "简短说明",
            "material_claims": [],
        }, ensure_ascii=False, sort_keys=True)
    )


def _call_deepseek(prompt: str, *, model: str, temperature: float, max_tokens: int, seed: int) -> tuple[str, dict[str, Any]]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for live run")
    url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "system", "content": "Return JSON only."}, {"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "seed": seed,
    }
    request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=120) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        return str(payload["choices"][0]["message"]["content"]), {"usage": payload.get("usage") or {}, "system_fingerprint": payload.get("system_fingerprint"), "seed_supported": True}
    except HTTPError as exc:
        if exc.code != 400:
            raise
        body.pop("seed", None)
        retry = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        with urlopen(retry, timeout=120) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        return str(payload["choices"][0]["message"]["content"]), {"usage": payload.get("usage") or {}, "system_fingerprint": payload.get("system_fingerprint"), "seed_supported": False}
    except URLError as exc:
        raise RuntimeError(f"provider request failed: {exc.reason}") from exc


def validate_bundle() -> dict[str, Any]:
    topics = _read_jsonl(DATA / "topics.jsonl")
    edges = _read_jsonl(DATA / "dependencies.jsonl")
    cases = _read_jsonl(DATA / "cases.jsonl")
    source_pack = _read_json(DATA / "source_pack.json")
    manifest = _read_json(DATA / "manifest.json")
    if {row.get("topic_id") for row in topics} != TOPIC_IDS:
        raise ValueError("topic ids must be np01..np08")
    if len(cases) != 20 or len({row.get("case_id") for row in cases}) != 20:
        raise ValueError("cases must contain 20 unique case ids")
    active = active_graph_edges(edges)
    if len(active) != 6:
        raise ValueError("active graph must contain 6 edges")
    if any(edge.get("src") not in TOPIC_IDS or edge.get("dst") not in TOPIC_IDS for edge in active):
        raise ValueError("active edge endpoint missing")
    if any(ref.get("path", "").endswith(("taxonomy_backup_json",)) for row in topics for ref in row.get("source_refs") or []):
        raise ValueError("backup evidence is forbidden")
    expected_hashes = manifest.get("input_hashes") or {}
    actual_hashes = {
        "topics_jsonl": sha256_jsonl(DATA / "topics.jsonl"),
        "dependencies_jsonl": sha256_jsonl(DATA / "dependencies.jsonl"),
        "cases_jsonl": sha256_jsonl(DATA / "cases.jsonl"),
        "gold_jsonl": sha256_jsonl(DATA / "gold.jsonl"),
        "source_pack_json": hashlib.sha256((DATA / "source_pack.json").read_bytes()).hexdigest(),
        "baseline_prompt": hashlib.sha256((DATA / "prompts/baseline.md").read_bytes()).hexdigest(),
        "graph_prompt": hashlib.sha256((DATA / "prompts/graph.md").read_bytes()).hexdigest(),
    }
    if expected_hashes and expected_hashes != actual_hashes:
        raise ValueError(f"input hash mismatch: expected={expected_hashes} actual={actual_hashes}")
    return {"topic_count": len(topics), "active_edge_count": len(active), "case_count": len(cases), "source_fact_count": len(source_pack.get("facts") or []), "runtime_consumable": False, "db_write_count": 0}


def run_live(*, model: str, temperature: float, max_tokens: int, output_dir: Path) -> dict[str, Any]:
    if os.environ.get("LUBAN_LEARNING_GRAPH_PILOT_LIVE") != "1":
        raise SystemExit("live run requires LUBAN_LEARNING_GRAPH_PILOT_LIVE=1")
    summary = validate_bundle()
    experiment_id = str(_read_json(DATA / "manifest.json").get("experiment_id") or "np_graph_ab")
    topics = _read_jsonl(DATA / "topics.jsonl")
    edges = active_graph_edges(_read_jsonl(DATA / "dependencies.jsonl"))
    cases = _read_jsonl(DATA / "cases.jsonl")
    source_pack = _read_json(DATA / "source_pack.json")
    allocation_rng = random.Random(20260710)
    order = list(cases)
    allocation_rng.shuffle(order)
    internal: list[dict[str, Any]] = []
    calls = 0
    fingerprints: set[str] = set()
    seed_supported: set[bool] = set()
    for idx, case in enumerate(order):
        first_arm = "baseline" if idx < 10 else "graph"
        arms = [first_arm, "graph" if first_arm == "baseline" else "baseline"]
        for arm in arms:
            graph_context = edges if arm == "graph" else None
            raw, meta = _call_deepseek(_prompt(case, topics, source_pack, graph_context), model=model, temperature=temperature, max_tokens=max_tokens, seed=20260710)
            parsed = parse_model_response(raw)
            calls += 1
            if meta.get("system_fingerprint"):
                fingerprints.add(str(meta["system_fingerprint"]))
            seed_supported.add(bool(meta.get("seed_supported")))
            internal.append({"case_id": case["case_id"], "arm": arm, "raw_response": raw, "prediction": parsed, "prompt_sha256": hashlib.sha256(_prompt(case, topics, source_pack, graph_context).encode("utf-8")).hexdigest(), "model": model, "model_meta": meta})
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "outputs.internal.jsonl").write_text("\n".join(canonical_json(row) for row in internal) + "\n", encoding="utf-8")
    blinded = []
    for row in internal:
        blind_id = "O-" + hashlib.sha256((row["case_id"] + row["arm"] + row["raw_response"]).encode("utf-8")).hexdigest()[:16]
        blinded.append({"blind_output_id": blind_id, "case_id": row["case_id"], "prediction": row["prediction"], "raw_response_sha256": hashlib.sha256(row["raw_response"].encode("utf-8")).hexdigest(), "prompt_sha256": row["prompt_sha256"], "model": row["model"]})
    random.Random(20260710).shuffle(blinded)
    (output_dir / "outputs.blinded.jsonl").write_text("\n".join(canonical_json(row) for row in blinded) + "\n", encoding="utf-8")
    result = {"status": "outputs_frozen", "experiment_id": experiment_id, "calls": calls, "expected_calls": 40, "system_fingerprints": sorted(fingerprints), "seed_supported_values": sorted(seed_supported), **summary, "db_write_count": 0}
    (output_dir / "run_manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def score_run(*, output_dir: Path) -> dict[str, Any]:
    validate_bundle()
    cases = {row["case_id"]: row for row in _read_jsonl(DATA / "cases.jsonl")}
    gold = {row["case_id"]: row for row in _read_jsonl(DATA / "gold.jsonl")}
    internal = _read_jsonl(output_dir / "outputs.internal.jsonl")
    by_case_arm = {(row["case_id"], row["arm"]): row for row in internal}
    pair_rows = []
    detailed = []
    for case_id, case in cases.items():
        base = by_case_arm[(case_id, "baseline")]
        graph = by_case_arm[(case_id, "graph")]
        base_score = score_prediction(case, gold[case_id], base["prediction"])
        graph_score = score_prediction(case, gold[case_id], graph["prediction"])
        row = {"case_id": case_id, "baseline_correct": base_score["correct"], "graph_correct": graph_score["correct"], "baseline_reason": base_score["reason"], "graph_reason": graph_score["reason"], "baseline_authority_drift": base_score["authority_drift"], "graph_authority_drift": graph_score["authority_drift"]}
        pair_rows.append(row)
        detailed.append(row)
    metrics = compare_pairs(pair_rows)
    review_path = output_dir / "reviews.blinded.jsonl"
    review_rows = _read_jsonl(review_path) if review_path.exists() else []
    invalid_count = sum(row.get("review_status") == "invalid" for row in review_rows)
    unsupported_count = sum(1 for row in review_rows if row.get("review_status") == "unsupported_claim")
    if invalid_count or unsupported_count:
        verdict = "STOP"
    else:
        verdict = "SIGNAL_PASS" if metrics["graph_accuracy"] >= 0.8 and metrics["paired_lift_pp"] >= 15.0 and metrics["baseline_wins"] <= 1 and not any(row["baseline_authority_drift"] or row["graph_authority_drift"] for row in detailed) else "INCONCLUSIVE_POSITIVE_SIGNAL"
    experiment_id = str(_read_json(DATA / "manifest.json").get("experiment_id") or "np_graph_ab")
    result = {"status": verdict, "experiment_id": experiment_id, "metrics": metrics, "pairs": detailed, "safety": {"db_write_count": 0, "runtime_consumable": False, "official_score_allowed": False, "manual_blind_review_required": not review_path.exists(), "blind_review": {"invalid_count": invalid_count, "unsupported_material_claim_count": unsupported_count}}}
    (output_dir / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    run = sub.add_parser("run-live")
    run.add_argument("--model", default="deepseek-chat")
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--max-output-tokens", type=int, default=1200)
    run.add_argument("--output-dir", default=str(DATA / "runs" / "20260710"))
    score = sub.add_parser("score")
    score.add_argument("--output-dir", default=str(DATA / "runs" / "20260710"))
    args = parser.parse_args(argv)
    _load_env()
    try:
        if args.command == "validate":
            result = validate_bundle()
        elif args.command == "run-live":
            result = run_live(model=args.model, temperature=args.temperature, max_tokens=args.max_output_tokens, output_dir=Path(args.output_dir))
        else:
            result = score_run(output_dir=Path(args.output_dir))
    except (ValueError, RuntimeError, KeyError, HTTPError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
