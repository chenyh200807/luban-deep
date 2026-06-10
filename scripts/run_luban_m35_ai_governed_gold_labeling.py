#!/usr/bin/env python3
"""R2 skeleton: multi-model AI-governed gold labeling pipeline (hermetic).

Per (student answer x scoring point):
  1. blind panel (>=3 models) judges independently (no cross-visibility);
  2. deterministic reconciliation: unanimous -> candidate; strict majority ->
     escalated to the arbiter model for blind review; split -> the arbiter
     (which never sat on the blind panel) adjudicates and its rationale lands
     in ``point_label_provenance``;
  3. an adversarial prosecutor (a model distinct from the blind panel) attacks
     each candidate row; an unresolved objection downgrades the whole row so it
     can never claim ``ai_governed_gold``;
  4. >=5 hard-coded deterministic mutations of the student answer are re-judged
     to verify label stability before a row may claim gold.

Rows that fail any gate are downgraded to the existing
``ai_council_directional`` level (never a new label-authority name). Gold rows
carry the canonical ``ai_governed_gold`` protocol block and are self-checked
against ``validate_ai_governed_gold_protocol`` before being written.

This skeleton never performs live LLM or network calls. Judges are injected as
``judge_fns: dict[model_id, fn(point, student_answer, official_anchor)]``; the
live adapter is an intentionally unimplemented double-opt-in factory stub.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.m35_ai_governed_gold import (  # noqa: E402
    LABEL_AUTHORITY,
    PROTOCOL_VERSION,
    validate_ai_governed_gold_protocol,
)

JudgeFn = Callable[[dict[str, Any], str, dict[str, Any]], dict[str, Any]]

SCHEMA_VERSION = "luban_m35_ai_governed_gold_labeling.v1"
DEFAULT_FIXTURE_DIR = REPO / "tests/fixtures/luban_m35_fastapi_case_subquestions_20q_100a"
DOWNGRADE_LABEL_AUTHORITY = "ai_council_directional"
MIN_JUDGE_MODELS = 5
MIN_INDEPENDENT_ACCEPTS = 3
KAPPA_STOP_THRESHOLD = 0.6
MUTATION_PASS_RATE_STOP_THRESHOLD = 0.8
PARTIAL_CREDIT_RATIO = 0.5
_CREDIT_RANK = {"miss": 0, "partial": 1, "hit": 2}
LIVE_ENV_FLAG = "LUBAN_M35_GOLD_LABELING_LIVE"
LIVE_API_KEY_ENVS = (
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)

# Deterministic, hard-coded mutation rules (reproducible by construction).
_TABLE_MUTATIONS: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "synonym_swap",
        "meaning_preserving",
        (("不妥", "欠妥"), ("做法", "作法"), ("情况", "状况"), ("要求", "规定")),
    ),
    (
        "subject_swap",
        "adversarial",
        (
            ("建设单位", "施工单位"),
            ("监理工程师", "监理员"),
            ("试验员", "施工员"),
            ("总包项目部", "分包项目部"),
        ),
    ),
    (
        "generalization",
        "adversarial",
        (("混凝土", "建筑材料"), ("检测机构", "第三方机构"), ("检测费用", "相关费用")),
    ),
    ("punctuation_normalize", "meaning_preserving", (("；", "，"), ("！", "。"))),
)

_REPLACED_ROW_FIELDS = {
    "label_authority",
    "label_scope",
    "directionality_flag",
    "gold_score",
    "gold_point_matches",
    "point_label_provenance",
    "ai_governed_gold",
    "downgrade_reasons",
    "adversarial_review",
    "mutation_test",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def assign_roles(judge_fns: Mapping[str, JudgeFn]) -> dict[str, Any]:
    model_ids = sorted(str(model_id).strip() for model_id in judge_fns)
    if any(not model_id for model_id in model_ids) or len(model_ids) != len(set(model_ids)):
        raise ValueError("judge_fns requires unique non-empty model ids")
    if len(model_ids) < MIN_JUDGE_MODELS:
        raise ValueError(
            f"ai-governed gold labeling requires >={MIN_JUDGE_MODELS} judge models "
            "(>=3 blind panel + arbiter + adversarial prosecutor)"
        )
    return {
        "blind_panel": model_ids[:-2],
        "arbiter": model_ids[-2],
        "adversarial_prosecutor": model_ids[-1],
    }


def _judge(fn: JudgeFn, point: dict[str, Any], student_answer: str, anchor: dict[str, Any]) -> dict[str, Any]:
    raw = fn(point, student_answer, anchor)
    if not isinstance(raw, dict):
        raise ValueError("judge functions must return a dict")
    verdict = str(raw.get("verdict") or "")
    if verdict not in _CREDIT_RANK:
        raise ValueError(f"judge returned invalid verdict: {verdict!r}")
    return {
        "verdict": verdict,
        "evidence_span": str(raw.get("evidence_span") or ""),
        "confidence": float(raw.get("confidence") or 0.0),
    }


def _official_anchor(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_id": str(question.get("question_id") or ""),
        "stem": question.get("stem"),
        "total_score": question.get("total_score"),
        "source_refs": question.get("source_refs") or [],
        "question_authority_ref": question.get("question_authority_ref"),
    }


def _reconcile_point(
    point: dict[str, Any],
    student_answer: str,
    anchor: dict[str, Any],
    judge_fns: Mapping[str, JudgeFn],
    roles: dict[str, Any],
) -> dict[str, Any]:
    panel_ids: list[str] = roles["blind_panel"]
    blind_votes = {
        model_id: _judge(judge_fns[model_id], point, student_answer, anchor)
        for model_id in panel_ids
    }
    counts = Counter(vote["verdict"] for vote in blind_votes.values())
    top_verdict, top_count = counts.most_common(1)[0]
    panel_size = len(panel_ids)

    arbiter_vote: dict[str, Any] | None = None
    if top_count == panel_size:
        route = "unanimous"
        consolidated = top_verdict
    else:
        arbiter_vote = _judge(judge_fns[roles["arbiter"]], point, student_answer, anchor)
        if top_count * 2 > panel_size:
            consolidated = top_verdict
            route = (
                "majority_review_confirmed"
                if arbiter_vote["verdict"] == top_verdict
                else "majority_review_unconfirmed"
            )
        else:
            route = "arbitration"
            consolidated = arbiter_vote["verdict"]

    supporting = [
        model_id for model_id in panel_ids if blind_votes[model_id]["verdict"] == consolidated
    ]
    if arbiter_vote is not None and arbiter_vote["verdict"] == consolidated:
        supporting.append(roles["arbiter"])
    return {
        "point": point,
        "blind_votes": blind_votes,
        "arbiter_vote": arbiter_vote,
        "route": route,
        "consolidated_verdict": consolidated,
        "supporting_model_ids": supporting,
    }


def _row_blind_model_votes(
    point_results: list[dict[str, Any]], roles: dict[str, Any]
) -> list[dict[str, Any]]:
    votes: list[dict[str, Any]] = []
    for model_id in roles["blind_panel"]:
        accepted = all(
            result["blind_votes"][model_id]["verdict"] == result["consolidated_verdict"]
            for result in point_results
        )
        votes.append(
            {
                "model_id": model_id,
                "independent": True,
                "verdict": "accept" if accepted else "dissent",
            }
        )
    arbited = [result for result in point_results if result["arbiter_vote"] is not None]
    if arbited:
        accepted = all(
            result["arbiter_vote"]["verdict"] == result["consolidated_verdict"]
            for result in arbited
        )
        votes.append(
            {
                "model_id": roles["arbiter"],
                "independent": True,
                "verdict": "accept" if accepted else "dissent",
            }
        )
    return votes


def _source_anchor(points: list[dict[str, Any]]) -> dict[str, Any]:
    refs = {
        json.dumps(ref, ensure_ascii=False, sort_keys=True)
        for point in points
        for ref in (point.get("source_refs") or [])
    }
    field_level = all(point.get("source_refs") for point in points)
    return {"source_ref_count": len(refs), "field_level_citations": field_level}


def _prosecute(
    point_results: list[dict[str, Any]],
    student_answer: str,
    anchor: dict[str, Any],
    judge_fns: Mapping[str, JudgeFn],
    roles: dict[str, Any],
) -> dict[str, Any]:
    prosecutor_id = roles["adversarial_prosecutor"]
    objections: list[dict[str, Any]] = []
    for result in point_results:
        vote = _judge(judge_fns[prosecutor_id], result["point"], student_answer, anchor)
        consolidated_rank = _CREDIT_RANK[result["consolidated_verdict"]]
        prosecutor_rank = _CREDIT_RANK[vote["verdict"]]
        if prosecutor_rank >= consolidated_rank:
            continue
        # A one-level disagreement is outvoted by >=3 independent blind
        # accepts; a two-level gap (hit vs miss) cannot be auto-resolved.
        resolved = consolidated_rank - prosecutor_rank == 1
        objections.append(
            {
                "point_id": str(result["point"].get("point_id") or ""),
                "consolidated_verdict": result["consolidated_verdict"],
                "prosecutor_verdict": vote["verdict"],
                "evidence_span": vote["evidence_span"],
                "resolved": resolved,
            }
        )
    unresolved = sum(1 for objection in objections if not objection["resolved"])
    return {
        "model_id": prosecutor_id,
        "role": "adversarial_prosecutor",
        "objection_count": len(objections),
        "resolved_objection_count": len(objections) - unresolved,
        "unresolved_objection_count": unresolved,
        "objections": objections,
    }


def mutate_student_answer(text: str) -> list[dict[str, str]]:
    """Apply the hard-coded deterministic mutation rules (>=5 cases)."""
    cases: list[dict[str, str]] = []
    for mutation_id, mutation_type, pairs in _TABLE_MUTATIONS:
        mutated = text
        for old, new in pairs:
            mutated = mutated.replace(old, new)
        cases.append({"mutation_id": mutation_id, "mutation_type": mutation_type, "text": mutated})
    cases.append(
        {
            "mutation_id": "restatement_prefix",
            "mutation_type": "meaning_preserving",
            "text": f"答：{text}",
        }
    )
    cases.append(
        {
            "mutation_id": "whitespace_squeeze",
            "mutation_type": "meaning_preserving",
            "text": " ".join(text.split()),
        }
    )
    return cases


def _panel_majority_verdict(
    point: dict[str, Any],
    text: str,
    anchor: dict[str, Any],
    judge_fns: Mapping[str, JudgeFn],
    panel_ids: list[str],
) -> str:
    counts = Counter(
        _judge(judge_fns[model_id], point, text, anchor)["verdict"] for model_id in panel_ids
    )
    top_verdict, top_count = counts.most_common(1)[0]
    if top_count * 2 > len(panel_ids):
        return top_verdict
    return "no_consensus"


def _mutation_test(
    point_results: list[dict[str, Any]],
    student_answer: str,
    anchor: dict[str, Any],
    judge_fns: Mapping[str, JudgeFn],
    roles: dict[str, Any],
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for mutation in mutate_student_answer(student_answer):
        stable = all(
            _panel_majority_verdict(
                result["point"], mutation["text"], anchor, judge_fns, roles["blind_panel"]
            )
            == result["consolidated_verdict"]
            for result in point_results
        )
        cases.append(
            {
                "mutation_id": mutation["mutation_id"],
                "mutation_type": mutation["mutation_type"],
                "stable": stable,
            }
        )
    stable_count = sum(1 for case in cases if case["stable"])
    return {
        "passed": stable_count == len(cases),
        "case_count": len(cases),
        "stable_case_count": stable_count,
        "cases": cases,
    }


def _awarded_score(verdict: str, max_score: float) -> float:
    if verdict == "hit":
        return max_score
    if verdict == "partial":
        return round(max_score * PARTIAL_CREDIT_RATIO, 4)
    return 0.0


def _evidence_span(result: dict[str, Any]) -> str:
    for model_id in result["supporting_model_ids"]:
        vote = result["blind_votes"].get(model_id) or result["arbiter_vote"]
        if vote and vote["evidence_span"]:
            return vote["evidence_span"]
    return ""


def _reproducibility_hash(
    row: dict[str, Any], point_results: list[dict[str, Any]], roles: dict[str, Any]
) -> str:
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "answer_id": str(row.get("answer_id") or ""),
        "question_id": str(row.get("question_id") or ""),
        "student_answer_sha256": hashlib.sha256(
            str(row.get("student_answer") or "").encode("utf-8")
        ).hexdigest(),
        "consolidated_verdicts": {
            str(result["point"].get("point_id") or ""): result["consolidated_verdict"]
            for result in point_results
        },
        "model_roles": roles,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _label_single_row(
    row: dict[str, Any],
    question: dict[str, Any],
    judge_fns: Mapping[str, JudgeFn],
    roles: dict[str, Any],
    kappa_items: list[Counter],
    mutation_totals: dict[str, int],
) -> dict[str, Any]:
    student_answer = str(row.get("student_answer") or "")
    anchor = _official_anchor(question)
    points = list(question.get("scoring_points") or [])

    point_results = [
        _reconcile_point(point, student_answer, anchor, judge_fns, roles) for point in points
    ]
    for result in point_results:
        kappa_items.append(Counter(vote["verdict"] for vote in result["blind_votes"].values()))

    blind_model_votes = _row_blind_model_votes(point_results, roles)
    accept_count = sum(1 for vote in blind_model_votes if vote["verdict"] == "accept")
    source_anchor = _source_anchor(points)

    downgrade_reasons: list[str] = []
    if accept_count < MIN_INDEPENDENT_ACCEPTS:
        downgrade_reasons.append("insufficient_independent_blind_accepts")
    if source_anchor["source_ref_count"] <= 0 or not source_anchor["field_level_citations"]:
        downgrade_reasons.append("missing_field_level_source_anchor")

    adversarial_review: dict[str, Any] | None = None
    if not downgrade_reasons:
        adversarial_review = _prosecute(point_results, student_answer, anchor, judge_fns, roles)
        if adversarial_review["unresolved_objection_count"] > 0:
            downgrade_reasons.append("unresolved_adversarial_objection")

    mutation_test: dict[str, Any] | None = None
    if not downgrade_reasons:
        mutation_test = _mutation_test(point_results, student_answer, anchor, judge_fns, roles)
        mutation_totals["cases"] += mutation_test["case_count"]
        mutation_totals["stable"] += mutation_test["stable_case_count"]
        if not mutation_test["passed"]:
            downgrade_reasons.append("mutation_test_failed")

    label_authority = LABEL_AUTHORITY if not downgrade_reasons else DOWNGRADE_LABEL_AUTHORITY
    gold_score = round(
        sum(
            _awarded_score(
                result["consolidated_verdict"], float(result["point"].get("max_score") or 0.0)
            )
            for result in point_results
        ),
        4,
    )
    gold_point_matches = [
        {
            "point_id": str(result["point"].get("point_id") or ""),
            "status": result["consolidated_verdict"],
            "evidence_span": _evidence_span(result),
            "max_score": float(result["point"].get("max_score") or 0.0),
            "awarded_score": _awarded_score(
                result["consolidated_verdict"], float(result["point"].get("max_score") or 0.0)
            ),
        }
        for result in point_results
    ]
    point_label_provenance = [
        {
            "point_id": str(result["point"].get("point_id") or ""),
            "authority": label_authority,
            "route": result["route"],
            "consolidated_verdict": result["consolidated_verdict"],
            "blind_votes": {
                model_id: vote["verdict"] for model_id, vote in result["blind_votes"].items()
            },
            "supporting_model_ids": result["supporting_model_ids"],
            **(
                {
                    "arbiter_model_id": roles["arbiter"],
                    "arbiter_verdict": result["arbiter_vote"]["verdict"],
                    "arbiter_rationale": result["arbiter_vote"]["evidence_span"],
                }
                if result["arbiter_vote"] is not None
                else {}
            ),
        }
        for result in point_results
    ]

    out_row = {key: value for key, value in row.items() if key not in _REPLACED_ROW_FIELDS}
    out_row.update(
        {
            "label_authority": label_authority,
            "label_scope": "point_and_score",
            "directionality_flag": label_authority,
            "gold_score": gold_score,
            "gold_point_matches": gold_point_matches,
            "point_label_provenance": point_label_provenance,
        }
    )

    if downgrade_reasons:
        out_row["downgrade_reasons"] = downgrade_reasons
        if adversarial_review is not None:
            out_row["adversarial_review"] = adversarial_review
        if mutation_test is not None:
            out_row["mutation_test"] = mutation_test
        return out_row

    protocol = {
        "protocol_version": PROTOCOL_VERSION,
        "blind_model_votes": blind_model_votes,
        "source_anchor": source_anchor,
        "adversarial_review": adversarial_review,
        "mutation_test": {
            "passed": mutation_test["passed"],
            "case_count": mutation_test["case_count"],
            "stable_case_count": mutation_test["stable_case_count"],
        },
        "reproducibility_hash": _reproducibility_hash(row, point_results, roles),
        "deterministic_gate": {
            "passed": True,
            "checks": {
                "reconciliation_by_deterministic_code": True,
                "independent_accept_count": accept_count,
                "score_sum_consistent": True,
            },
        },
    }
    check = validate_ai_governed_gold_protocol(protocol)
    if check["valid"] is not True:
        raise RuntimeError(
            f"internal protocol bug for answer {row.get('answer_id')!r}: "
            f"{check['blocking_reasons']}"
        )
    out_row["ai_governed_gold"] = protocol
    return out_row


def _fleiss_kappa(items: list[Counter]) -> float | None:
    if not items:
        return None
    rater_count = sum(items[0].values())
    if rater_count < 2:
        return None
    item_count = len(items)
    categories = sorted({category for item in items for category in item})
    category_share = {
        category: sum(item.get(category, 0) for item in items) / (item_count * rater_count)
        for category in categories
    }
    mean_agreement = sum(
        (sum(count**2 for count in item.values()) - rater_count)
        / (rater_count * (rater_count - 1))
        for item in items
    ) / item_count
    expected_agreement = sum(share**2 for share in category_share.values())
    if 1 - expected_agreement == 0:
        return 1.0
    return round((mean_agreement - expected_agreement) / (1 - expected_agreement), 6)


def _stop_condition(kappa: float | None, mutation_pass_rate: float | None) -> dict[str, Any]:
    reasons: list[str] = []
    if kappa is not None and kappa < KAPPA_STOP_THRESHOLD:
        reasons.append("fleiss_kappa_below_threshold")
    if mutation_pass_rate is not None and mutation_pass_rate < MUTATION_PASS_RATE_STOP_THRESHOLD:
        reasons.append("mutation_pass_rate_below_threshold")
    return {
        "triggered": bool(reasons),
        "reasons": reasons,
        "fleiss_kappa_threshold": KAPPA_STOP_THRESHOLD,
        "mutation_pass_rate_threshold": MUTATION_PASS_RATE_STOP_THRESHOLD,
    }


def run_labeling(
    *,
    answers_path: Path,
    manifest_path: Path,
    judge_fns: Mapping[str, JudgeFn],
    output_dir: Path,
    limit: int = 0,
) -> dict[str, Any]:
    roles = assign_roles(judge_fns)
    rows = _read_jsonl(Path(answers_path))
    if limit > 0:
        rows = rows[:limit]
    source_manifest = _read_json(Path(manifest_path))
    questions_by_id = {
        str(question.get("question_id") or ""): question
        for question in source_manifest.get("questions") or []
    }

    kappa_items: list[Counter] = []
    mutation_totals = {"cases": 0, "stable": 0}
    out_rows: list[dict[str, Any]] = []
    skipped_no_scoring_points: list[str] = []
    for row in rows:
        question = questions_by_id.get(str(row.get("question_id") or ""))
        if not question or not question.get("scoring_points"):
            skipped_no_scoring_points.append(str(row.get("answer_id") or ""))
            continue
        out_rows.append(
            _label_single_row(row, question, judge_fns, roles, kappa_items, mutation_totals)
        )

    kappa = _fleiss_kappa(kappa_items)
    mutation_pass_rate = (
        round(mutation_totals["stable"] / mutation_totals["cases"], 6)
        if mutation_totals["cases"]
        else None
    )
    stop_condition = _stop_condition(kappa, mutation_pass_rate)
    label_authority_counts = Counter(row["label_authority"] for row in out_rows)
    downgrade_reason_counts = Counter(
        reason for row in out_rows for reason in row.get("downgrade_reasons") or []
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "label_authority": LABEL_AUTHORITY,
        "source_answers_path": str(answers_path),
        "source_manifest_path": str(manifest_path),
        "model_roles": roles,
        "row_count": len(out_rows),
        "gold_row_count": label_authority_counts.get(LABEL_AUTHORITY, 0),
        "downgraded_row_count": label_authority_counts.get(DOWNGRADE_LABEL_AUTHORITY, 0),
        "skipped_no_scoring_points": skipped_no_scoring_points,
        "label_authority_counts": dict(label_authority_counts),
        "downgrade_reason_counts": dict(downgrade_reason_counts),
        "fleiss_kappa": kappa,
        "mutation_pass_rate": mutation_pass_rate,
        "mutation_case_count": mutation_totals["cases"],
        "stop_condition_triggered": stop_condition["triggered"],
        "stop_condition": stop_condition,
        "official_score_allowed": False,
        "is_release_truth": False,
        "safety": {
            "db_write_count": 0,
            "remote_write_count": 0,
            "provider_call_count": 0,
        },
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "student_answers.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in out_rows) + "\n",
        encoding="utf-8",
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"rows": out_rows, "manifest": manifest, "output_dir": str(out_dir)}


def live_api_key_envs_present(env: Mapping[str, str] | None = None) -> list[str]:
    env = os.environ if env is None else env
    return [name for name in LIVE_API_KEY_ENVS if str(env.get(name) or "").strip()]


def build_live_judge_fns(
    *, cli_live_flag: bool, env: Mapping[str, str] | None = None
) -> dict[str, JudgeFn]:
    """Factory stub for live provider judges (intentionally unimplemented).

    Live labeling requires the double opt-in (``--live`` CLI flag AND
    ``LUBAN_M35_GOLD_LABELING_LIVE=1``). Even then, this R2 skeleton never
    performs provider calls: it raises ``NotImplementedError`` so callers can
    only ever report the live arm as not exercised.
    """
    env = os.environ if env is None else env
    if not cli_live_flag or str(env.get(LIVE_ENV_FLAG) or "") != "1":
        raise PermissionError(
            f"live labeling requires both --live and {LIVE_ENV_FLAG}=1 (double opt-in)"
        )
    present = live_api_key_envs_present(env)
    raise NotImplementedError(
        "live judge adapters are not implemented in the R2 skeleton; "
        f"api_key_envs_present={present}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", type=Path, default=DEFAULT_FIXTURE_DIR / "student_answers.jsonl")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_FIXTURE_DIR / "manifest.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    env_enabled = str(os.environ.get(LIVE_ENV_FLAG) or "") == "1"
    if not (args.live and env_enabled):
        status = "blocked_live_double_opt_in_required"
    else:
        try:
            build_live_judge_fns(cli_live_flag=args.live)
            status = "unreachable"
        except NotImplementedError:
            status = "not_exercised_live_adapter_not_implemented"

    report = {
        "schema_version": SCHEMA_VERSION,
        "labeling_run": False,
        "live": {
            "cli_flag": bool(args.live),
            "env_flag": env_enabled,
            "api_key_envs_present": live_api_key_envs_present(),
            "status": status,
        },
        "answers_path": str(args.answers),
        "manifest_path": str(args.manifest),
        "note": (
            "hermetic skeleton: labeling runs only with injected judge_fns via "
            "run_labeling(); no provider/network calls are implemented"
        ),
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "live_gate_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
