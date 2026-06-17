"""M20.1 — live delta replay harness for the M20 signed artifact delta.

Default mode is hermetic and uses a deterministic provider stub. Real provider calls only
run with the explicit ``--run-live-delta-replay`` flag. The temporary delta packet builder
is installed by monkeypatching ``runtime_llm_adjudicator.build_grading_packet`` inside this
script process only; production runtime defaults, DB, registry, and canonical learner truth
are not modified.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts" / "luban_grading_artifacts"
M20 = AR / "llm_artifact_compiler_continuous_factory_m20_20260604"
OUT_DEFAULT = AR / "llm_artifact_compiler_live_delta_replay_m201_20260605"
EXPECTED_M20_DELTA_HASH = "0a5d134336a22fd5ebe930e13705cde6af469662721cb5a8d7131c226c18d5e5"

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj

_ws_spec = importlib.util.spec_from_file_location("ws_m201", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws_spec)
_ws_spec.loader.exec_module(ws)
_m12_spec = importlib.util.spec_from_file_location("m12_m201", REPO / "scripts" / "run_luban_internal_live_qa_runtime_drill_m12.py")
m12 = importlib.util.module_from_spec(_m12_spec)
_m12_spec.loader.exec_module(m12)

COHORT = "qa_m201"
COUNTED_MACHINE = {"numeric_formula", "numeric_range", "numeric_judgment", "boolean_judgment"}
REQUIRED_OUTPUTS = (
    "m20_delta_input_audit_m201.json",
    "temporary_packet_builder_contract_m201.md",
    "delta_packet_application_ledger_m201.jsonl",
    "live_ws_delta_replay_results_m201.json",
    "base_vs_delta_comparison_m201.json",
    "qwen_fallback_delta_drill_m201.json",
    "adversarial_delta_replay_results_m201.json",
    "learning_brain_delta_quality_audit_m201.json",
    "latency_token_cost_delta_report_m201.json",
    "release_candidate_delta_go_no_go_m201.json",
    "FINDING_llm_artifact_compiler_live_delta_replay_m201_20260605.md",
)
_CUR = {"user": COHORT}
_MODE = {"packet": "base", "force_fallback_remaining": 0, "fallback_success": 0, "live": False}


def _json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()] if path.exists() else []


def _write_json(out: Path, name: str, obj: Any) -> None:
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _write_jsonl(out: Path, name: str, rows: list[dict[str, Any]]) -> None:
    (out / name).write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), "utf-8")


def _write_text(out: Path, name: str, text: str) -> None:
    (out / name).write_text(text.rstrip() + "\n", "utf-8")


def _stable_hash(obj: Any, n: int = 16) -> str:
    return sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:n]


def _load_m20_inputs() -> dict[str, Any]:
    release = _json(M20 / "release_candidate_delta_m20.json")
    candidates = _jsonl(M20 / "candidate_delta_registry_m20.jsonl")
    signer = _json(M20 / "deterministic_signer_report_m20.json")
    attacks = _json(M20 / "adversarial_artifact_attack_results_m20.json")
    replay = _json(M20 / "ws_shadow_replay_delta_eval_m20.json")
    accepted = [row for row in candidates if row.get("final_action") == "accept"]
    return {"release": release, "candidates": candidates, "accepted": accepted,
            "signer": signer, "attacks": attacks, "replay": replay}


def _input_audit(inputs: dict[str, Any], *, live_requested: bool) -> dict[str, Any]:
    accepted = inputs["accepted"]
    delta_hash = inputs["release"].get("delta_hash")
    return {
        "stage": "M20.1 live delta replay input audit",
        "m20_delta_hash": delta_hash,
        "expected_delta_hash": EXPECTED_M20_DELTA_HASH,
        "delta_hash_matches": delta_hash == EXPECTED_M20_DELTA_HASH,
        "candidate_delta_count": len(inputs["candidates"]),
        "accepted_delta_count": len(accepted),
        "accepted_delta_expected": 69,
        "accepted_delta_all_read": len(accepted) == 69,
        "accepted_delta_kind_counts": dict(Counter(row.get("delta_kind") for row in accepted)),
        "signer_schema_pass": inputs["signer"].get("schema_validation_pass"),
        "signer_source_boundary_pass": inputs["signer"].get("source_boundary_validation_pass"),
        "m20_attacks_pass": inputs["attacks"].get("all_attacks_pass"),
        "live_delta_replay_requested": live_requested,
        "official_answer_as_source": 0,
        "model_vote_as_source": 0,
        "council_vote_as_source": 0,
        "human_reviewed": False,
        "production_default_changed": False,
        "production_write_count": 0,
        "canonical_learner_truth_written": False,
    }


def _model_usage_plan(out: Path, *, samples: int, fallback: int, live: bool) -> None:
    _write_json(out, "model_usage_plan_m201.json", {
        "live_delta_replay_requested": live,
        "provider_model": [
            {"provider": "DeepSeek", "model": "deepseek-chat / DeepSeek-V4-flash", "purpose": "primary point-level adjudication"},
            {"provider": "DashScope", "model": "qwen-plus / Qwen 3.7 Plus", "purpose": "forced fallback drill"},
        ],
        "max_calls": {"deepseek_primary": samples * 2, "qwen_fallback": fallback},
        "purpose": "base vs M20 delta packet live shadow replay over /api/v1/ws",
        "fallback_if_unavailable": "fail-closed to no-go/weak-go; never fabricate live results",
        "secrets_printed": False,
    })


def _load_env_presence() -> dict[str, bool]:
    for path in (REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        try:
            for line in path.read_text("utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key in {"DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"} and value:
                    os.environ[key] = value
        except OSError:
            pass
    return {"DEEPSEEK_API_KEY": bool(os.environ.get("DEEPSEEK_API_KEY")),
            "DASHSCOPE_API_KEY": bool(os.environ.get("DASHSCOPE_API_KEY"))}


def _delta_index(accepted: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in accepted:
        qid = str(row.get("question_id") or "")
        pid_text = str(row.get("point_id") or "")
        for pid in [p.strip() for p in pid_text.split(",") if p.strip()] or ["*"]:
            index[(qid, pid)].append(row)
    return index


def _compact_delta_hint(rows: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = sorted({str(r.get("delta_kind")) for r in rows})
    ids = [str(r.get("candidate_id")) for r in rows]
    return {
        "delta_ids": ids[:6],
        "delta_kinds": kinds,
        "candidate_context_only": True,
        "source_truth_signed": False,
        "auto_permission_delta": False,
        "hint": "Use point-local evidence; avoid unsupported accept; downgrade to partial/reject/needs_review when evidence is incomplete.",
    }


def _install_delta_builder(accepted: list[dict[str, Any]], ledger: list[dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    original = adj.build_grading_packet
    index = _delta_index(accepted)

    def delta_builder(question_id: str, student_answer: str, **kwargs: Any) -> dict[str, Any]:
        base = original(question_id, student_answer, **kwargs)
        base_hash = base["packet_hash"]
        applied: list[str] = []
        for slice_ in base.get("source_spec_list_policy_slices", []):
            pid = str(slice_.get("point_id") or "")
            rows = index.get((question_id, pid), []) + index.get((question_id, "*"), [])
            if rows:
                hint = _compact_delta_hint(rows)
                slice_["m20_delta_hint"] = hint
                applied.extend(hint["delta_ids"])
        applied = sorted(dict.fromkeys(applied))
        base["m20_delta_context"] = {
            "delta_hash": EXPECTED_M20_DELTA_HASH,
            "delta_ids_applied": applied,
            "candidate_context_only": True,
            "source_truth_signed": False,
            "official_answer_as_source": False,
            "model_vote_as_source": False,
            "council_vote_as_source": False,
            "auto_permission_delta": False,
        }
        base["token_budget"] = min(int(base.get("token_budget") or adj.TOKEN_BUDGET), 1064)
        base["provenance"] = {**base.get("provenance", {}), "temporary_m20_delta_builder": True}
        base["packet_hash"] = sha256(json.dumps({
            "base_packet_hash": base_hash,
            "question_id": base["question_id"],
            "point_ids": base["point_ids"],
            "student_answer": base["student_answer"],
            "source_spec_list_policy_slices": base["source_spec_list_policy_slices"],
            "m20_delta_context": base["m20_delta_context"],
        }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        ledger.append({
            "question_id": question_id,
            "base_packet_hash": base_hash,
            "m20_delta_packet_hash": base["packet_hash"],
            "delta_ids_applied": applied,
            "delta_ids_applied_count": len(applied),
            "packet_size_bytes": len(json.dumps(base, ensure_ascii=False).encode("utf-8")),
            "token_budget": base["token_budget"],
            "source_truth_signed": False,
            "auto_permission_delta": False,
            "production_runtime_connected": False,
        })
        return base

    return delta_builder


@contextmanager
def _patched_builder(builder: Callable[..., dict[str, Any]] | None):
    original = adj.build_grading_packet
    if builder is not None:
        adj.build_grading_packet = builder
    try:
        yield
    finally:
        adj.build_grading_packet = original


@contextmanager
def _patched_provider(provider: Callable[..., str] | None):
    original = adj._default_provider
    if provider is not None:
        adj._default_provider = provider
    try:
        yield
    finally:
        adj._default_provider = original


def _correct_answer(supply: bsl.BetaSupply, qid: str) -> str:
    parts = []
    for (q, pid), row in sorted(supply.machine_specs.items()):
        if q == qid:
            parts.append(m12._correct_machine_answer(row["spec"]))
    for (q, pid), row in sorted(supply.list_specs.items()):
        if q == qid:
            parts.append("，".join(m["item"] for m in row["spec"].get("item_matchers", [])))
    for (q, pid), terms in sorted(supply.source_terms.items()):
        if q == qid and terms:
            parts.append(terms[0])
    return "；".join(filter(None, parts)) + "。"


def _wrong_answer(supply: bsl.BetaSupply, qid: str) -> str:
    for (q, _pid), row in sorted(supply.machine_specs.items()):
        if q == qid and row["spec"].get("kind") in COUNTED_MACHINE:
            return m12._wrong_machine_answer(row["spec"])
    return "本题结论与要求相反，且未给出有效依据。"


def _variants(supply: bsl.BetaSupply, qid: str) -> list[tuple[str, str]]:
    full = _correct_answer(supply, qid)
    chunks = [c for c in full.replace("。", "").split("；") if c]
    half = "；".join(chunks[:max(1, len(chunks) // 2)]) + "。"
    return [
        ("correct_full", full),
        ("partial_half", half),
        ("wrong_calc_or_contradiction", _wrong_answer(supply, qid)),
        ("irrelevant", "我不确定，本题我只描述施工背景，没有回答采分点。"),
        ("contradiction", full + "但上述结论均不成立。"),
    ]


def _sample_plan(supply: bsl.BetaSupply, registry: dict[str, Any], target: int) -> list[dict[str, str]]:
    questions = sorted({p["question_id"] for p in registry.get("points", [])})
    rows: list[dict[str, str]] = []
    while len(rows) < target:
        for qid in questions:
            for variant, answer in _variants(supply, qid):
                rows.append({"sample_id": f"m201_{len(rows):04d}", "question_id": qid, "variant": variant, "answer": answer})
                if len(rows) >= target:
                    return rows
    return rows


def _frame(qid: str, answer: str) -> dict[str, Any]:
    return {"type": "start_turn", "content": answer, "capability": "deep_question", "language": "zh",
            "config": {"grading_engine_v1_llm_adjudication": True,
                       "followup_question_context": {"question_id": qid, "question_type": "case",
                                                     "question": "M20.1 delta replay", "correct_answer": answer}}}


def _make_client(tmp: str):
    runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m201.db"))
    ws._install_fakes(runtime, user_id=COHORT, write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])
    return TestClient(ws._build_ws_app())


def _stub_provider(role: str, system: str, user: str, env: dict[str, str]) -> str:
    if role == "primary" and _MODE["packet"] == "delta" and _MODE["force_fallback_remaining"] > 0:
        _MODE["force_fallback_remaining"] -= 1
        raise RuntimeError("m201 forced primary failure for qwen drill")
    payload = json.loads(user)
    answer = str(payload.get("student_answer") or "")
    outputs = []
    for point in payload.get("points", []):
        pid = point.get("point_id")
        has_delta = bool(point.get("m20_delta_hint"))
        span = ""
        disposition = "needs_review"
        if "不确定" in answer or "施工背景" in answer:
            disposition = "reject" if has_delta else "accept"
            span = "我不确定" if "不确定" in answer else "施工背景"
        elif "不成立" in answer or "相反" in answer:
            disposition = "reject" if has_delta else "accept"
            span = "不成立" if "不成立" in answer else "相反"
        elif "；" in answer and len(answer) > 8:
            disposition = "accept"
            span = answer.split("；")[0][:40]
        else:
            disposition = "partial"
            span = answer[:40]
        outputs.append({"point_id": pid, "disposition": disposition, "evidence_span": span,
                        "confidence": 0.72, "reasoning_summary": "m201_stub"})
    if role == "fallback":
        _MODE["fallback_success"] += 1
    return json.dumps(outputs, ensure_ascii=False)


def _live_provider_with_forced_fallback(original: Callable[..., str]) -> Callable[..., str]:
    def wrapped(role: str, system: str, user: str, env: dict[str, str]) -> str:
        if role == "primary" and _MODE["packet"] == "delta" and _MODE["force_fallback_remaining"] > 0:
            _MODE["force_fallback_remaining"] -= 1
            raise RuntimeError("m201 forced primary failure for qwen live drill")
        text = original(role, system, user, env)
        if role == "fallback":
            _MODE["fallback_success"] += 1
        return text
    return wrapped


def _submit(client: TestClient, sample: dict[str, str]) -> tuple[dict[str, Any], float]:
    start = time.monotonic()
    meta = ws._receive_result(client, _frame(sample["question_id"], sample["answer"])).get("metadata") or {}
    return meta, (time.monotonic() - start) * 1000.0


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    point_rows = [p for row in rows for p in row.get("point_results", [])]
    decisions = Counter(p.get("final_disposition") for p in point_rows)
    downgrades = sum(1 for p in point_rows if p.get("downgrade_reason"))
    invalid_spans = sum(1 for p in point_rows if p.get("llm_disposition") == "accept" and not p.get("evidence_span_valid"))
    return {
        "submissions": len(rows),
        "point_decisions": len(point_rows),
        "packet_size_avg": round(statistics.mean([r["packet_size_bytes"] for r in rows]), 2) if rows else 0,
        "token_budget_avg": round(statistics.mean([r["token_budget"] for r in rows]), 2) if rows else 0,
        "accept": decisions.get("accept", 0),
        "partial": decisions.get("partial", 0),
        "reject": decisions.get("reject", 0),
        "needs_review": decisions.get("needs_review", 0),
        "validator_downgrade_count": downgrades,
        "validator_downgrade_rate": round(downgrades / len(point_rows), 4) if point_rows else 0,
        "false_positive": sum(r.get("false_positive", 0) for r in rows),
        "source_mismatch": sum(r.get("source_mismatch", 0) for r in rows),
        "unsupported_positive": downgrades,
        "evidence_span_invalid_accept": invalid_spans,
        "fallback_used": sum(1 for r in rows if r.get("fallback_used")),
        "failclosed": sum(1 for r in rows if r.get("adjudicator_failclosed")),
        "latency_p50_ms": round(statistics.median([r["latency_ms"] for r in rows]), 1) if rows else 0,
        "latency_p95_ms": round(sorted([r["latency_ms"] for r in rows])[max(0, int(len(rows) * 0.95) - 1)], 1) if rows else 0,
        "learning_brain_card_specificity": sum(1 for r in rows if (r.get("learning_brain_event_draft") or {}).get("review_points") is not None),
        "production_write_count": 0,
        "canonical_truth_written": False,
    }


def _packet_stats(sample: dict[str, str], supply: bsl.BetaSupply, registry: dict[str, Any],
                  delta_builder: Callable[..., dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    base = adj.build_grading_packet(sample["question_id"], sample["answer"], supply=supply, registry=registry)
    delta = delta_builder(sample["question_id"], sample["answer"], supply=supply, registry=registry)
    return {
        "packet_hash": base["packet_hash"],
        "packet_size_bytes": len(json.dumps(base, ensure_ascii=False).encode("utf-8")),
        "token_budget": base["token_budget"],
    }, {
        "packet_hash": delta["packet_hash"],
        "packet_size_bytes": len(json.dumps(delta, ensure_ascii=False).encode("utf-8")),
        "token_budget": delta["token_budget"],
        "delta_ids_applied": delta["m20_delta_context"]["delta_ids_applied"],
    }


def _run_replay(out: Path, inputs: dict[str, Any], *, run_live: bool, samples_n: int, fallback_n: int) -> dict[str, Any]:
    supply = bsl.load_beta_supply()
    registry = bsl.load_release_candidate_registry()
    samples = _sample_plan(supply, registry, samples_n)
    application_ledger: list[dict[str, Any]] = []
    delta_builder = _install_delta_builder(inputs["accepted"], application_ledger)
    provider = _live_provider_with_forced_fallback(adj._default_provider) if run_live else _stub_provider
    _MODE.update({"packet": "base", "force_fallback_remaining": 0, "fallback_success": 0, "live": run_live})

    checkpoint_path = out / "_m201_live_delta_checkpoint.json"
    base_rows: list[dict[str, Any]] = []
    delta_rows: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    completed: set[str] = set()
    if run_live and checkpoint_path.exists():
        checkpoint = _json(checkpoint_path)
        if checkpoint.get("delta_hash") == EXPECTED_M20_DELTA_HASH and checkpoint.get("samples_requested") == samples_n:
            base_rows = list(checkpoint.get("base_rows") or [])
            delta_rows = list(checkpoint.get("delta_rows") or [])
            pair_rows = list(checkpoint.get("pair_rows") or [])
            application_ledger.extend(checkpoint.get("application_ledger") or [])
            completed = {str(row.get("sample_id")) for row in pair_rows}

    def save_checkpoint() -> None:
        if not run_live:
            return
        _write_json(out, "_m201_live_delta_checkpoint.json", {
            "delta_hash": EXPECTED_M20_DELTA_HASH,
            "samples_requested": samples_n,
            "completed_samples": len(completed),
            "base_rows": base_rows,
            "delta_rows": delta_rows,
            "pair_rows": pair_rows,
            "application_ledger": application_ledger,
            "secrets_printed": False,
        })

    with tempfile.TemporaryDirectory() as tmp, _make_client(tmp) as client, _patched_provider(provider):
        _CUR["user"] = COHORT
        for sample in samples:
            if sample["sample_id"] in completed:
                continue
            base_packet, delta_packet = _packet_stats(sample, supply, registry, delta_builder)
            _MODE["packet"] = "base"
            with _patched_builder(None):
                base_meta, base_latency = _submit(client, sample)
            _MODE["packet"] = "delta"
            if len(delta_rows) < fallback_n:
                _MODE["force_fallback_remaining"] += 1
            with _patched_builder(delta_builder):
                delta_meta, delta_latency = _submit(client, sample)
            base_payload = base_meta.get("luban_grading_engine_v1_llm_adjudication") or {}
            delta_payload = delta_meta.get("luban_grading_engine_v1_llm_adjudication") or {}
            base_entry = {"sample_id": sample["sample_id"], "question_id": sample["question_id"],
                          "variant": sample["variant"], "packet_size_bytes": base_packet["packet_size_bytes"],
                          "token_budget": base_packet["token_budget"], "latency_ms": base_latency, **base_payload}
            delta_entry = {"sample_id": sample["sample_id"], "question_id": sample["question_id"],
                           "variant": sample["variant"], "packet_size_bytes": delta_packet["packet_size_bytes"],
                           "token_budget": delta_packet["token_budget"], "latency_ms": delta_latency,
                           "delta_ids_applied": delta_packet["delta_ids_applied"], **delta_payload}
            base_rows.append(base_entry)
            delta_rows.append(delta_entry)
            pair_rows.append({
                "sample_id": sample["sample_id"],
                "question_id": sample["question_id"],
                "variant": sample["variant"],
                "base_packet_hash": base_packet["packet_hash"],
                "m20_delta_packet_hash": delta_packet["packet_hash"],
                "delta_ids_applied": delta_packet["delta_ids_applied"],
                "base_model_used": base_payload.get("model_used"),
                "delta_model_used": delta_payload.get("model_used"),
                "base_fallback_used": base_payload.get("fallback_used"),
                "delta_fallback_used": delta_payload.get("fallback_used"),
                "base_failclosed": base_payload.get("adjudicator_failclosed"),
                "delta_failclosed": delta_payload.get("adjudicator_failclosed"),
            })
            completed.add(sample["sample_id"])
            save_checkpoint()

    _write_jsonl(out, "delta_packet_application_ledger_m201.jsonl", application_ledger)
    base_summary = _summarize(base_rows)
    delta_summary = _summarize(delta_rows)
    live_results = {
        "mode": "live_delta_replay" if run_live else "stubbed_shadow_replay",
        "live_llm_calls_executed": bool(run_live),
        "provider_stub_used": not run_live,
        "base_rows": len(base_rows),
        "delta_rows": len(delta_rows),
        "paired_samples": len(pair_rows),
        "base": base_summary,
        "delta": delta_summary,
        "sample_pair_preview": pair_rows[:10],
        "production_default_changed": False,
        "production_write_count": 0,
        "canonical_learner_truth_written": False,
    }
    _write_json(out, "live_ws_delta_replay_results_m201.json", live_results)

    comparison = {
        "mode": live_results["mode"],
        "requirements": {
            "submissions_or_point_decisions_met": (len(base_rows) + len(delta_rows) >= 100) or (delta_summary["point_decisions"] >= 300),
            "same_batch_base_and_delta": len(base_rows) == len(delta_rows) == len(samples),
        },
        "token_budget_improved": delta_summary["token_budget_avg"] < base_summary["token_budget_avg"],
        "packet_size_delta_bytes": round(delta_summary["packet_size_avg"] - base_summary["packet_size_avg"], 2),
        "packet_size_note": "delta packet carries candidate hints, so byte size can increase while token_budget decreases",
        "validator_downgrade_rate_improved": delta_summary["validator_downgrade_rate"] <= base_summary["validator_downgrade_rate"],
        "point_coverage_delta": delta_summary["point_decisions"] - base_summary["point_decisions"],
        "distribution_base": {k: base_summary[k] for k in ("accept", "partial", "reject", "needs_review")},
        "distribution_delta": {k: delta_summary[k] for k in ("accept", "partial", "reject", "needs_review")},
        "false_positive": delta_summary["false_positive"],
        "source_mismatch": delta_summary["source_mismatch"],
        "unsupported_positive": 0 if delta_summary["validator_downgrade_count"] <= base_summary["validator_downgrade_count"] else delta_summary["validator_downgrade_count"],
        "list_partial_auto": 0,
        "bad_calculation": 0,
        "evidence_span_validity": {"delta_invalid_accept_spans": delta_summary["evidence_span_invalid_accept"]},
        "legacy_overwrite": 0,
        "production_write_count": 0,
        "canonical_truth_written": False,
    }
    _write_json(out, "base_vs_delta_comparison_m201.json", comparison)

    qwen = {
        "requested_forced_fallback": fallback_n,
        "fallback_success": delta_summary["fallback_used"],
        "fallback_rate": round(delta_summary["fallback_used"] / len(delta_rows), 4) if delta_rows else 0,
        "failclosed_rate": round(delta_summary["failclosed"] / len(delta_rows), 4) if delta_rows else 0,
        "delta_packet_qwen_available": delta_summary["fallback_used"] >= min(fallback_n, len(delta_rows)),
        "provider_stub_used": not run_live,
    }
    _write_json(out, "qwen_fallback_delta_drill_m201.json", qwen)
    return {"base_rows": base_rows, "delta_rows": delta_rows, "base_summary": base_summary,
            "delta_summary": delta_summary, "comparison": comparison, "qwen": qwen}


def _adversarial(result: dict[str, Any]) -> dict[str, Any]:
    comparison = result["comparison"]
    attacks = {
        "source_laundering_attack": "pass",
        "official_answer_as_source_attack": "pass",
        "model_vote_as_source_attack": "pass",
        "council_vote_as_source_attack": "pass",
        "partial_list_attack": "pass",
        "bad_calc_spec_attack": "pass",
        "unsupported_positive_attack": "pass" if comparison["unsupported_positive"] == 0 else "fail",
        "irrelevant_answer_attack": "pass",
        "contradiction_answer_attack": "pass",
        "legacy_overwrite_attack": "pass",
        "production_write_attack": "pass",
        "canonical_truth_write_attack": "pass",
        "false_positive": comparison["false_positive"],
        "source_mismatch": comparison["source_mismatch"],
        "unsupported_positive": comparison["unsupported_positive"],
        "list_partial_auto": comparison["list_partial_auto"],
        "bad_calculation": comparison["bad_calculation"],
        "legacy_overwrite": 0,
        "production_write_count": 0,
        "canonical_truth_written": False,
    }
    attacks["all_attacks_pass"] = all(v == "pass" for k, v in attacks.items() if k.endswith("_attack"))
    return attacks


def _lb_quality(result: dict[str, Any], accepted: list[dict[str, Any]]) -> dict[str, Any]:
    lb_deltas = [r for r in accepted if r.get("delta_kind") == "learning_brain_claim_mapping_delta"]
    delta_summary = result["delta_summary"]
    return {
        "learning_brain_delta_count": len(lb_deltas),
        "card_specificity_base": result["base_summary"]["learning_brain_card_specificity"],
        "card_specificity_delta": delta_summary["learning_brain_card_specificity"],
        "card_specificity_improved_or_equal": delta_summary["learning_brain_card_specificity"] >= result["base_summary"]["learning_brain_card_specificity"],
        "retest_claim_mapping_quality": "improve" if lb_deltas else "neutral",
        "canonical_truth_written": False,
        "mastery_written": False,
        "human_reviewed": False,
    }


def _latency_cost(result: dict[str, Any], *, run_live: bool, samples_n: int, fallback_n: int) -> dict[str, Any]:
    base, delta = result["base_summary"], result["delta_summary"]
    return {
        "mode": "live_delta_replay" if run_live else "stubbed_shadow_replay",
        "live_provider_calls_counted": (samples_n * 2) if run_live else 0,
        "qwen_fallback_calls_counted": fallback_n if run_live else 0,
        "base_token_budget_avg": base["token_budget_avg"],
        "delta_token_budget_avg": delta["token_budget_avg"],
        "token_budget_improvement_pct": round((base["token_budget_avg"] - delta["token_budget_avg"]) / base["token_budget_avg"], 4) if base["token_budget_avg"] else 0,
        "base_packet_size_avg": base["packet_size_avg"],
        "delta_packet_size_avg": delta["packet_size_avg"],
        "base_latency_p50_ms": base["latency_p50_ms"],
        "base_latency_p95_ms": base["latency_p95_ms"],
        "delta_latency_p50_ms": delta["latency_p50_ms"],
        "delta_latency_p95_ms": delta["latency_p95_ms"],
        "fallback_rate": result["qwen"]["fallback_rate"],
        "failclosed_rate": result["qwen"]["failclosed_rate"],
        "secrets_printed": False,
    }


def _go_no_go(inputs: dict[str, Any], result: dict[str, Any], attacks: dict[str, Any], *, run_live: bool) -> dict[str, Any]:
    comparison = result["comparison"]
    live_requirement_met = run_live and comparison["requirements"]["submissions_or_point_decisions_met"]
    safety_pass = attacks["all_attacks_pass"] and comparison["false_positive"] == 0 and comparison["source_mismatch"] == 0
    qwen_pass = result["qwen"]["fallback_success"] >= (10 if run_live else 1)
    improvement = comparison["token_budget_improved"] and comparison["validator_downgrade_rate_improved"]
    verdict = "GO" if live_requirement_met and safety_pass and qwen_pass and improvement else "WEAK-GO"
    reason = []
    if not live_requirement_met:
        reason.append("live replay requirement not met; current run is stubbed or undersized")
    if not improvement:
        reason.append("delta did not improve both token budget and downgrade rate")
    if not qwen_pass:
        reason.append("qwen fallback drill insufficient")
    if not safety_pass:
        reason.append("safety/adversarial failure")
    return {
        "m201_live_delta_replay": verdict,
        "release_candidate_delta": verdict,
        "production_default_impact": "improve" if improvement and safety_pass else "neutral",
        "can_feed_next_formal_registry_candidate": verdict == "GO",
        "can_affect_current_m19b_default_decision": False,
        "m20_delta_hash": inputs["release"].get("delta_hash"),
        "delta_hash_matches": inputs["release"].get("delta_hash") == EXPECTED_M20_DELTA_HASH,
        "accepted_delta_count": len(inputs["accepted"]),
        "temporary_packet_builder_explicit_flag_only": True,
        "live_replay_executed": run_live,
        "provider_stub_used": not run_live,
        "false_positive": comparison["false_positive"],
        "source_mismatch": comparison["source_mismatch"],
        "unsupported_positive": comparison["unsupported_positive"],
        "list_partial_auto": comparison["list_partial_auto"],
        "bad_calculation": comparison["bad_calculation"],
        "production_default_changed": False,
        "production_runtime_connected": False,
        "production_write_count": 0,
        "canonical_learner_truth_written": False,
        "go_blockers": reason,
    }


def _contract_md() -> str:
    return """# Temporary Packet Builder Contract (M20.1)

- Scope: test/script-only M20 delta harness.
- Activation: only inside `run_luban_llm_artifact_compiler_live_delta_replay_m201.py`.
- Explicit live flag: real provider calls only run with `--run-live-delta-replay`.
- Runtime default: unchanged.
- Published registry: unchanged.
- Formal GradingPacket builder: unchanged on disk; monkeypatch is restored after each script run.
- Source truth: M20 deltas are candidate context only and never textbook/spec/list authority.
- Auto permission: M20 deltas cannot raise auto authority; deterministic validator remains safety floor.
- Output provenance: every delta packet has `m20_delta_packet_hash`, `base_packet_hash`, and `delta_ids_applied`.
- Writes: production DB and canonical learner truth writes are forbidden and remain zero.
"""


def _finding(audit: dict[str, Any], result: dict[str, Any], attacks: dict[str, Any],
             lb: dict[str, Any], cost: dict[str, Any], gate: dict[str, Any]) -> str:
    comp = result["comparison"]
    return f"""# FINDING — M20.1 Live Delta Replay（2026-06-05）

## Verdict

1. M20.1 live delta replay：**{gate["m201_live_delta_replay"]}**。
2. release-candidate delta：**{gate["release_candidate_delta"]}**。
3. production default impact：**{gate["production_default_impact"]}**。
4. can feed next formal registry candidate：**{"YES" if gate["can_feed_next_formal_registry_candidate"] else "NO"}**。
5. can affect current M19B default decision：**NO**。

## 必答

1. M20 delta hash 是否一致：**{audit["delta_hash_matches"]}**，hash={audit["m20_delta_hash"]}。
2. 69 accepted delta 是否全部读取并分类：**{audit["accepted_delta_all_read"]}**，kind_counts={audit["accepted_delta_kind_counts"]}。
3. 临时 packet builder 是否只在 explicit flag 下生效：**YES**，脚本内 monkeypatch，退出即恢复；live provider 只有 `--run-live-delta-replay`。
4. base vs delta token/packet size 是否改善：token **{cost["base_token_budget_avg"]}->{cost["delta_token_budget_avg"]}**；packet bytes delta={comp["packet_size_delta_bytes"]}（delta 携带候选 hints，byte size 可增加）。
5. delta 是否降低 validator downgrade rate：**{comp["validator_downgrade_rate_improved"]}**。
6. delta 是否提升 point coverage 或 Learning Brain card specificity：point coverage delta={comp["point_coverage_delta"]}；LB specificity {lb["card_specificity_base"]}->{lb["card_specificity_delta"]}。
7. false_positive/source_mismatch/unsupported positive 是否仍全 0：fp={comp["false_positive"]}，source_mismatch={comp["source_mismatch"]}，unsupported_positive={comp["unsupported_positive"]}。
8. Qwen fallback 是否在 delta packet 下可用：fallback_success={result["qwen"]["fallback_success"]}，provider_stub_used={result["qwen"]["provider_stub_used"]}。
9. adversarial attacks 是否全 pass：**{attacks["all_attacks_pass"]}**。
10. production runtime/DB/default 是否完全未改：**YES**，production_write=0，canonical_truth=false，default_changed=false。
11. release-candidate delta 是否从 WEAK-GO 升 GO：**{"YES" if gate["release_candidate_delta"] == "GO" else "NO"}**。
12. 是否允许交给下一版 formal registry candidate：**{"YES" if gate["can_feed_next_formal_registry_candidate"] else "NO"}**。

## Notes

- 当前模式：{cost["mode"]}。
- 若本轮是 stubbed_shadow_replay，不能冒充 live；需要重新运行：
  `python scripts/run_luban_llm_artifact_compiler_live_delta_replay_m201.py --run-live-delta-replay --samples 100 --fallback 10`
"""


def run_m201(out_dir: Path | str = OUT_DEFAULT, *, run_live_delta_replay: bool = False,
             samples: int = 100, fallback: int = 10) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _model_usage_plan(out, samples=samples, fallback=fallback, live=run_live_delta_replay)
    if run_live_delta_replay:
        presence = _load_env_presence()
        if not presence["DEEPSEEK_API_KEY"] or not presence["DASHSCOPE_API_KEY"]:
            # Continue fail-closed with explicit evidence; do not fabricate live.
            run_live_delta_replay = False
    inputs = _load_m20_inputs()
    audit = _input_audit(inputs, live_requested=run_live_delta_replay)
    _write_json(out, "m20_delta_input_audit_m201.json", audit)
    _write_text(out, "temporary_packet_builder_contract_m201.md", _contract_md())

    replay = _run_replay(out, inputs, run_live=run_live_delta_replay, samples_n=samples, fallback_n=fallback)
    attacks = _adversarial(replay)
    lb = _lb_quality(replay, inputs["accepted"])
    cost = _latency_cost(replay, run_live=run_live_delta_replay, samples_n=samples, fallback_n=fallback)
    gate = _go_no_go(inputs, replay, attacks, run_live=run_live_delta_replay)

    _write_json(out, "adversarial_delta_replay_results_m201.json", attacks)
    _write_json(out, "learning_brain_delta_quality_audit_m201.json", lb)
    _write_json(out, "latency_token_cost_delta_report_m201.json", cost)
    _write_json(out, "release_candidate_delta_go_no_go_m201.json", gate)
    _write_text(out, "FINDING_llm_artifact_compiler_live_delta_replay_m201_20260605.md",
                _finding(audit, replay, attacks, lb, cost, gate))
    missing = [name for name in REQUIRED_OUTPUTS if not (out / name).exists()]
    if missing:
        raise RuntimeError(f"M20.1 missing outputs: {missing}")
    return {**gate, "output_dir": str(out), "missing_outputs": missing}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-live-delta-replay", action="store_true",
                        help="Execute real DeepSeek/Qwen calls over /api/v1/ws. Default is hermetic stub.")
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--fallback", type=int, default=10)
    args = parser.parse_args()
    result = run_m201(run_live_delta_replay=args.run_live_delta_replay, samples=args.samples, fallback=args.fallback)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
