#!/usr/bin/env python3
"""A/B evaluate raw lecture JSON context vs compiled Luban answer skill pack.

This is an offline, deterministic eval. It does not claim live model quality.
It answers a narrower but critical question: does the compiled answer-method
pack provide better answerable context than raw lecture chunks for exam QA?
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_PACK_ROOT = (
    REPO
    / "deeptutor/services/construction_grading/runtime_supply/v_lecture_answer_skill_pack_all8"
)
DEFAULT_OUT_DIR = REPO / "artifacts" / "luban_grading_artifacts" / (
    "lecture_answer_skill_pack_ab_eval_" + date.today().strftime("%Y%m%d")
)

AD_TERMS = ("小佑题库", "佑森在线", "官方企微", "扫码关注", "免费听课", "在线刷题", "售后反馈")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)]


def _contains(answer: str, phrase: str) -> bool:
    phrase = str(phrase or "").strip()
    if not phrase:
        return True
    if phrase in answer:
        return True
    compact_answer = re.sub(r"\s+", "", answer)
    compact_phrase = re.sub(r"\s+", "", phrase)
    return compact_phrase in compact_answer


def runtime_supply_root(pack_root: Path) -> Path:
    root = Path(pack_root)
    nested = root / "runtime_supply"
    if (nested / "manifest.json").exists():
        return nested
    return root


def load_answer_units(pack_root: Path) -> list[dict[str, Any]]:
    supply_root = runtime_supply_root(pack_root)
    manifest_path = supply_root / "manifest.json"
    manifest = _load_json(manifest_path)
    units: list[dict[str, Any]] = []
    for shard in manifest.get("shards") or []:
        shard_path = supply_root / str(shard["path"])
        doc = _load_json(shard_path)
        units.extend(doc.get("answer_units") or [])
    return units


def render_raw_answer(unit: dict[str, Any]) -> str:
    """Arm A: raw JSON style. It uses only source excerpt + source ref."""
    source = str(unit.get("source_excerpt") or "").strip()
    source_ref = unit.get("source_ref") or {}
    return (
        "【raw_json_baseline】\n"
        f"答题依据：{source[:500]}\n"
        f"来源：json_page_num={source_ref.get('json_page_num')}；"
        f"chunk_id={source_ref.get('source_chunk_id')}。\n"
        "答法：根据上面讲义原文直接作答。"
    )


def render_skill_pack_answer(unit: dict[str, Any]) -> str:
    """Arm B: compiled answer-method pack style."""
    method = unit.get("answer_method") or {}
    source_ref = unit.get("source_ref") or {}
    lines = [
        "【answer_skill_pack】",
        f"答题方式：{method.get('answer_style') or '先给结论，再列采分点。'}",
    ]
    must = _as_list(method.get("must_mentions"))
    thresholds = _as_list(method.get("formula_or_thresholds"))
    traps = _as_list(method.get("trap_alerts"))
    red_lines = _as_list(method.get("red_lines"))
    mnemonics = _as_list(method.get("mnemonics"))
    if must:
        lines.append("采分关键词：" + "；".join(must))
    if thresholds:
        lines.append("公式/阈值/适用条件：" + "；".join(thresholds))
    if traps:
        lines.append("陷阱提醒：" + "；".join(traps))
    if red_lines:
        lines.append("红线：" + "；".join(red_lines))
    if mnemonics:
        lines.append("口诀：" + "；".join(mnemonics))
    lines.append(
        f"来源：json_page_num={source_ref.get('json_page_num')}；"
        f"chunk_id={source_ref.get('source_chunk_id')}。"
    )
    return "\n".join(lines)


def score_answer(unit: dict[str, Any], answer: str) -> dict[str, Any]:
    method = unit.get("answer_method") or {}
    source_ref = unit.get("source_ref") or {}
    must = _as_list(method.get("must_mentions"))
    thresholds = _as_list(method.get("formula_or_thresholds"))
    traps = _as_list(method.get("trap_alerts"))
    red_lines = _as_list(method.get("red_lines"))
    mnemonics = _as_list(method.get("mnemonics"))

    citation_hits = int(str(source_ref.get("source_chunk_id")) in answer) + int(str(source_ref.get("json_page_num")) in answer)
    must_hits = sum(1 for x in must if _contains(answer, x))
    threshold_hits = sum(1 for x in thresholds if _contains(answer, x))
    trap_hits = sum(1 for x in traps if _contains(answer, x))
    red_hits = sum(1 for x in red_lines if _contains(answer, x))
    mnemonic_hits = sum(1 for x in mnemonics if _contains(answer, x))
    ad_pollution = int(any(term in answer for term in AD_TERMS))

    weights = {
        "citation": 2.0,
        "must": 3.0 if must else 0.0,
        "threshold": 1.5 if thresholds else 0.0,
        "trap": 1.5 if traps else 0.0,
        "red": 1.5 if red_lines else 0.0,
        "mnemonic": 1.0 if mnemonics else 0.0,
        "ad_clean": 1.0,
    }
    earned = 0.0
    earned += weights["citation"] * (citation_hits / 2)
    earned += weights["must"] * (must_hits / len(must)) if must else 0.0
    earned += weights["threshold"] * (threshold_hits / len(thresholds)) if thresholds else 0.0
    earned += weights["trap"] * (trap_hits / len(traps)) if traps else 0.0
    earned += weights["red"] * (red_hits / len(red_lines)) if red_lines else 0.0
    earned += weights["mnemonic"] * (mnemonic_hits / len(mnemonics)) if mnemonics else 0.0
    earned += weights["ad_clean"] * (0 if ad_pollution else 1)
    possible = sum(weights.values())
    score = round(earned / possible, 4) if possible else 0.0
    return {
        "score": score,
        "citation_hits": citation_hits,
        "must_hits": must_hits,
        "must_total": len(must),
        "threshold_hits": threshold_hits,
        "threshold_total": len(thresholds),
        "trap_hits": trap_hits,
        "trap_total": len(traps),
        "red_line_hits": red_hits,
        "red_line_total": len(red_lines),
        "mnemonic_hits": mnemonic_hits,
        "mnemonic_total": len(mnemonics),
        "ad_pollution": ad_pollution,
    }


def _eligible_units(units: list[dict[str, Any]], max_cases: int) -> list[dict[str, Any]]:
    useful = []
    for unit in units:
        method = unit.get("answer_method") or {}
        signals = (
            _as_list(method.get("must_mentions"))
            + _as_list(method.get("trap_alerts"))
            + _as_list(method.get("red_lines"))
            + _as_list(method.get("mnemonics"))
            + _as_list(method.get("formula_or_thresholds"))
        )
        label = (unit.get("question_patterns") or [unit.get("topic") or ""])[0]
        if signals and label and len(str(label)) >= 2:
            useful.append(unit)
    # Stable, lecture-balanced-ish order: take up to max_cases after existing shard order.
    return useful[:max_cases]


def _arm_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    scores = [r[arm]["score"] for r in rows]
    return {
        "avg_score": round(mean(scores), 4) if scores else 0.0,
        "min_score": round(min(scores), 4) if scores else 0.0,
        "max_score": round(max(scores), 4) if scores else 0.0,
        "citation_rate": round(mean([r[arm]["citation_hits"] / 2 for r in rows]), 4) if rows else 0.0,
        "trap_recall": _field_recall(rows, arm, "trap_hits", "trap_total"),
        "red_line_recall": _field_recall(rows, arm, "red_line_hits", "red_line_total"),
        "mnemonic_recall": _field_recall(rows, arm, "mnemonic_hits", "mnemonic_total"),
        "threshold_recall": _field_recall(rows, arm, "threshold_hits", "threshold_total"),
        "ad_pollution_count": sum(r[arm]["ad_pollution"] for r in rows),
    }


def _field_recall(rows: list[dict[str, Any]], arm: str, hit_key: str, total_key: str) -> float:
    total = sum(r[arm][total_key] for r in rows)
    if total == 0:
        return 1.0
    return round(sum(r[arm][hit_key] for r in rows) / total, 4)


def _write_markdown(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# Lecture Answer Skill Pack A/B Eval",
        "",
        f"- winner: {result['winner']}",
        f"- case_count: {result['case_count']}",
        f"- avg_score_delta: {result['delta']['avg_score']}",
        "",
        "| arm | avg | citation | trap | red line | mnemonic | threshold | ad pollution |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, summary in result["arms"].items():
        lines.append(
            f"| {arm} | {summary['avg_score']} | {summary['citation_rate']} | "
            f"{summary['trap_recall']} | {summary['red_line_recall']} | "
            f"{summary['mnemonic_recall']} | {summary['threshold_recall']} | "
            f"{summary['ad_pollution_count']} |"
        )
    lines.extend(["", "## Interpretation", ""])
    lines.append(
        "This offline eval measures context quality, not live model behavior. "
        "A live LLM A/B should reuse the same cases and judge rubric before production claims."
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_eval(*, pack_root: Path, out_dir: Path, max_cases: int = 40) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    units = _eligible_units(load_answer_units(pack_root), max_cases=max_cases)
    rows: list[dict[str, Any]] = []
    wins: defaultdict[str, int] = defaultdict(int)
    for unit in units:
        raw_answer = render_raw_answer(unit)
        skill_answer = render_skill_pack_answer(unit)
        raw_score = score_answer(unit, raw_answer)
        skill_score = score_answer(unit, skill_answer)
        if skill_score["score"] > raw_score["score"]:
            wins["answer_skill_pack"] += 1
        elif raw_score["score"] > skill_score["score"]:
            wins["raw_json_baseline"] += 1
        else:
            wins["tie"] += 1
        rows.append(
            {
                "unit_id": unit["unit_id"],
                "lecture": unit.get("lecture"),
                "topic": unit.get("topic"),
                "question": f"{(unit.get('question_patterns') or [unit.get('topic')])[0]}怎么按考试答？",
                "raw_json_baseline": raw_score,
                "answer_skill_pack": skill_score,
                "raw_answer": raw_answer,
                "skill_answer": skill_answer,
            }
        )

    raw_summary = _arm_summary(rows, "raw_json_baseline")
    skill_summary = _arm_summary(rows, "answer_skill_pack")
    delta = {
        "avg_score": round(skill_summary["avg_score"] - raw_summary["avg_score"], 4),
        "trap_recall": round(skill_summary["trap_recall"] - raw_summary["trap_recall"], 4),
        "red_line_recall": round(skill_summary["red_line_recall"] - raw_summary["red_line_recall"], 4),
        "mnemonic_recall": round(skill_summary["mnemonic_recall"] - raw_summary["mnemonic_recall"], 4),
        "threshold_recall": round(skill_summary["threshold_recall"] - raw_summary["threshold_recall"], 4),
    }
    winner = "answer_skill_pack" if delta["avg_score"] > 0 else "tie" if delta["avg_score"] == 0 else "raw_json_baseline"
    result = {
        "schema_version": "luban_lecture_answer_skill_pack_ab_eval.v1",
        "pack_root": str(pack_root),
        "case_count": len(rows),
        "winner": winner,
        "arms": {
            "raw_json_baseline": raw_summary,
            "answer_skill_pack": skill_summary,
        },
        "delta": delta,
        "wins": dict(wins),
        "rows": rows,
        "limitations": [
            "offline deterministic context-quality eval; not a live model-output eval",
            "baseline uses raw source excerpt plus citation, not every possible RAG prompt optimization",
            "judge is rule-based and should be complemented with blind model/human review before production claims",
        ],
    }
    (out_dir / "ab_eval_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out_dir / "ab_eval_rows.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    _write_markdown(out_dir / "AB_FINDING.md", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=DEFAULT_PACK_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-cases", type=int, default=40)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_eval(pack_root=args.pack_root, out_dir=args.out_dir, max_cases=args.max_cases)
    printable = {k: v for k, v in result.items() if k != "rows"}
    print(json.dumps(printable, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
