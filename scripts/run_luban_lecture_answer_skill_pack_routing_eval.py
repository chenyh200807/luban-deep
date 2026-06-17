#!/usr/bin/env python3
"""Evaluate when Luban lecture answer skills should activate.

This is not a runtime router. It is a deterministic offline fit test for the
compiled lecture answer-method runtime_supply bundle. It answers:

* Which query scenarios should activate the lecture skills?
* When is the expected answer quality high?
* When may the skill suggest related knowledge points, and where must it stop?
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
from collections import Counter, defaultdict
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
    "lecture_answer_skill_pack_routing_eval_" + date.today().strftime("%Y%m%d")
)

AB_SPEC = importlib.util.spec_from_file_location(
    "lecture_ab",
    Path(__file__).with_name("run_luban_lecture_answer_skill_pack_ab_eval.py"),
)
lecture_ab = importlib.util.module_from_spec(AB_SPEC)
AB_SPEC.loader.exec_module(lecture_ab)

AD_TERMS = lecture_ab.AD_TERMS
ASSOCIATION_TERMS = ("联想", "相关", "一起记", "对比", "区分", "关联", "串联", "相近")
EXAM_TERMS = ("考试", "一建", "实务", "怎么答", "答题", "采分", "案例", "考点", "口诀")
TRAP_TERMS = ("陷阱", "红线", "易错", "不得分", "错误")
FORMULA_TERMS = ("公式", "计算", "阈值", "适用条件", "取大差", "工期", "费用")
MNEMONIC_TERMS = ("口诀", "怎么记", "记忆", "背诵")
OFF_SYLLABUS_TERMS = ("天气", "股票", "电影", "菜谱", "旅游", "彩票", "八卦")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: Any) -> str:
    return re.sub(r"[\s，。、；;：:（）()【】\[\]　·,.//\"'“”‘’《》<>]+", "", str(text or "")).lower()


def _as_list(value: Any) -> list[str]:
    return lecture_ab._as_list(value)


def _contains_any(query: str, terms: tuple[str, ...]) -> bool:
    return any(term in query for term in terms)


def _tokenize_unit(unit: dict[str, Any]) -> list[str]:
    taxonomy = unit.get("taxonomy") or {}
    method = unit.get("answer_method") or {}
    values: list[str] = [
        unit.get("lecture"),
        unit.get("lecture_slug"),
        unit.get("topic"),
        taxonomy.get("node_code"),
        taxonomy.get("node_name"),
        taxonomy.get("topic"),
    ]
    values.extend(unit.get("question_patterns") or [])
    values.extend(_as_list(method.get("must_mentions")))
    values.extend(_as_list(method.get("formula_or_thresholds"))[:3])
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _norm(value)
        if len(clean) >= 2 and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def build_routing_index(pack_root: Path) -> dict[str, Any]:
    supply_root = lecture_ab.runtime_supply_root(pack_root)
    manifest = _load_json(supply_root / "manifest.json")
    units: list[dict[str, Any]] = []
    for shard in manifest.get("shards") or []:
        doc = _load_json(supply_root / shard["path"])
        for unit in doc.get("answer_units") or []:
            unit = dict(unit)
            source = unit.get("source_ref") or {}
            unit["_routing_tokens"] = _tokenize_unit(unit)
            unit["_capabilities"] = _capabilities(unit)
            unit["_source_ref_compact"] = {
                "chunk_id": source.get("source_chunk_id"),
                "json_page_num": source.get("json_page_num"),
            }
            units.append(unit)
    return {
        "pack_root": str(pack_root),
        "runtime_supply_root": str(supply_root),
        "manifest": manifest,
        "units": units,
        "lecture_counts": dict(Counter(str(u.get("lecture")) for u in units)),
    }


def _capabilities(unit: dict[str, Any]) -> dict[str, bool]:
    method = unit.get("answer_method") or {}
    return {
        "must_mentions": bool(_as_list(method.get("must_mentions"))),
        "trap_red_line": bool(_as_list(method.get("trap_alerts")) or _as_list(method.get("red_lines"))),
        "mnemonic": bool(_as_list(method.get("mnemonics"))),
        "formula_condition": bool(_as_list(method.get("formula_or_thresholds"))),
        "citation": bool((unit.get("source_ref") or {}).get("source_chunk_id")),
    }


def _query_intents(query: str) -> dict[str, bool]:
    return {
        "exam_answer": _contains_any(query, EXAM_TERMS),
        "trap_red_line": _contains_any(query, TRAP_TERMS),
        "formula_condition": _contains_any(query, FORMULA_TERMS),
        "mnemonic": _contains_any(query, MNEMONIC_TERMS),
        "association": _contains_any(query, ASSOCIATION_TERMS),
        "off_syllabus": _contains_any(query, OFF_SYLLABUS_TERMS),
    }


def _unit_score(query_norm: str, unit: dict[str, Any], intents: dict[str, bool]) -> float:
    if not query_norm:
        return 0.0
    score = 0.0
    lecture_token = _norm(unit.get("lecture"))
    for token in unit.get("_routing_tokens") or []:
        if token and token in query_norm:
            score += min(0.42, 0.14 + len(token) / 80)
            if token != lecture_token and len(token) >= 4:
                score += 0.24
        elif token and query_norm in token and len(query_norm) >= 4:
            score += 0.18
    caps = unit.get("_capabilities") or {}
    if intents["exam_answer"] and caps.get("must_mentions"):
        score += 0.08
    if intents["trap_red_line"] and caps.get("trap_red_line"):
        score += 0.16
    if intents["formula_condition"] and caps.get("formula_condition"):
        score += 0.14
    if intents["association"]:
        score += 0.04
    if intents["off_syllabus"]:
        score -= 0.55
    return max(0.0, min(1.0, score))


def _activation_band(score: float) -> str:
    if score >= 0.50:
        return "high"
    if score >= 0.34:
        return "medium"
    if score >= 0.20:
        return "low"
    return "none"


def _quality_band(top_units: list[dict[str, Any]], intents: dict[str, bool], activation_band: str) -> str:
    if activation_band == "none":
        return "not_applicable"
    if not top_units:
        return "not_applicable"
    top = top_units[0]
    caps = top.get("_capabilities") or {}
    expected: list[str] = ["citation", "must_mentions"]
    if intents["trap_red_line"]:
        expected.append("trap_red_line")
    if intents["formula_condition"]:
        expected.append("formula_condition")
    if intents.get("mnemonic"):
        expected.append("mnemonic")
    hits = sum(1 for key in expected if caps.get(key))
    ratio = hits / len(expected)
    if activation_band == "high" and ratio >= 0.75:
        return "high"
    if activation_band in {"high", "medium"} and ratio >= 0.5:
        return "medium"
    return "low"


def _related_units(units: list[dict[str, Any]], seed: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    lecture = seed.get("lecture")
    taxonomy = seed.get("taxonomy") or {}
    topic = taxonomy.get("topic") or seed.get("topic")
    rows: list[tuple[float, dict[str, Any]]] = []
    for unit in units:
        if unit["unit_id"] == seed["unit_id"]:
            continue
        if unit.get("lecture") != lecture:
            continue
        candidate_taxonomy = unit.get("taxonomy") or {}
        score = 0.45
        if topic and topic in {candidate_taxonomy.get("topic"), unit.get("topic"), candidate_taxonomy.get("node_name")}:
            score += 0.25
        if (unit.get("_capabilities") or {}).get("trap_red_line"):
            score += 0.08
        if (unit.get("_capabilities") or {}).get("formula_condition"):
            score += 0.05
        rows.append((score, unit))
    rows.sort(key=lambda item: (-item[0], item[1]["unit_id"]))
    return [_public_unit(unit, score=score) for score, unit in rows[:limit]]


def _public_unit(unit: dict[str, Any], *, score: float) -> dict[str, Any]:
    return {
        "unit_id": unit["unit_id"],
        "lecture": unit.get("lecture"),
        "topic": unit.get("topic"),
        "score": round(score, 4),
        "capabilities": unit.get("_capabilities") or {},
        "source_ref": unit.get("_source_ref_compact") or {},
    }


def evaluate_query(index: dict[str, Any], query: str, *, top_k: int = 5) -> dict[str, Any]:
    query_norm = _norm(query)
    intents = _query_intents(str(query or ""))
    scored = [(_unit_score(query_norm, unit, intents), unit) for unit in index["units"]]
    scored.sort(key=lambda item: (-item[0], item[1]["unit_id"]))
    positive = [(score, unit) for score, unit in scored if score > 0]
    top_score = positive[0][0] if positive else 0.0
    top_units = [_public_unit(unit, score=score) for score, unit in positive[:top_k]]
    band = _activation_band(top_score)
    should_activate = band in {"high", "medium"}
    if intents["off_syllabus"] and top_score < 0.58:
        should_activate = False
        band = "none"
    quality = _quality_band([unit for _score, unit in positive[:top_k]], intents, band)
    capability_hits = {
        key: any((unit.get("_capabilities") or {}).get(key) for _score, unit in positive[:top_k])
        for key in ("must_mentions", "trap_red_line", "mnemonic", "formula_condition", "citation")
    }
    association_allowed = bool(
        should_activate
        and intents["association"]
        and positive
        and not intents["off_syllabus"]
    )
    related = _related_units(index["units"], positive[0][1]) if association_allowed else []
    return {
        "query": query,
        "intents": intents,
        "activation_score": round(top_score, 4),
        "activation_band": band,
        "should_activate": should_activate,
        "quality_band": quality,
        "source_grounded": bool(top_units and top_units[0]["source_ref"].get("chunk_id")),
        "capability_hits": capability_hits,
        "association_allowed": association_allowed,
        "association_policy": (
            "same_lecture_or_same_taxonomy_only_with_chunk_citations"
            if association_allowed
            else "no_association_without_source_grounded_activation"
        ),
        "top_units": top_units,
        "related_units": related,
    }


def _probe_queries(index: dict[str, Any], max_per_lecture: int) -> list[dict[str, str]]:
    by_lecture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in index["units"]:
        by_lecture[str(unit.get("lecture"))].append(unit)
    probes: list[dict[str, str]] = []
    for lecture, units in sorted(by_lecture.items()):
        selected = units[:max_per_lecture]
        for unit in selected:
            label = (unit.get("question_patterns") or [unit.get("topic") or unit["unit_id"]])[0]
            probes.append({"scenario": "exam_answer", "query": f"{label}怎么按一建建筑实务考试答？"})
            if (unit.get("_capabilities") or {}).get("trap_red_line"):
                probes.append({"scenario": "trap_red_line", "query": f"{label}有哪些陷阱、红线和易错点？"})
            if (unit.get("_capabilities") or {}).get("formula_condition"):
                probes.append({"scenario": "formula_condition", "query": f"{label}的公式、阈值和适用条件是什么？"})
            if (unit.get("_capabilities") or {}).get("mnemonic"):
                probes.append({"scenario": "mnemonic", "query": f"{label}有什么口诀，怎么展开成采分点？"})
            probes.append({"scenario": "association", "query": f"学{label}时应该联想到哪些相关考点？"})
    probes.extend(
        [
            {"scenario": "off_syllabus", "query": "今天天气和股票行情怎么样？"},
            {"scenario": "broad_review", "query": "主体结构这一章应该怎么复习，重点有哪些？"},
            {"scenario": "ambiguous_short", "query": "这个怎么算？"},
        ]
    )
    return probes


def _scenario_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["scenario"]].append(row)
    out: dict[str, Any] = {}
    for scenario, items in grouped.items():
        out[scenario] = {
            "count": len(items),
            "activation_rate": round(mean([1.0 if item["should_activate"] else 0.0 for item in items]), 4),
            "high_activation_rate": round(mean([1.0 if item["activation_band"] == "high" else 0.0 for item in items]), 4),
            "high_quality_rate": round(mean([1.0 if item["quality_band"] == "high" else 0.0 for item in items]), 4),
            "avg_activation_score": round(mean([item["activation_score"] for item in items]), 4),
            "association_allowed_rate": round(mean([1.0 if item["association_allowed"] else 0.0 for item in items]), 4),
        }
    return out


def _write_markdown(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# Lecture Answer Skill Pack Routing / Association Eval",
        "",
        f"- pack_root: `{result['pack_root']}`",
        f"- unit_count: {result['unit_count']}",
        f"- probe_count: {result['probe_count']}",
        "",
        "## Scenario Fit",
        "",
        "| scenario | count | activation | high activation | high quality | avg score | association |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario, summary in sorted(result["scenario_summary"].items()):
        lines.append(
            f"| {scenario} | {summary['count']} | {summary['activation_rate']} | "
            f"{summary['high_activation_rate']} | {summary['high_quality_rate']} | "
            f"{summary['avg_activation_score']} | {summary['association_allowed_rate']} |"
        )
    lines.extend(
        [
            "",
            "## Practical Interpretation",
            "",
            "- Highest-fit scenarios: direct exam-answer, trap/red-line, formula/condition, mnemonic, and source-bounded association questions.",
            "- Medium-fit scenarios: broad chapter review questions; answer should first ask/choose narrower topic or return an outline with citations.",
            "- Do-not-activate scenarios: off-syllabus chat, very short deictic follow-ups without active question context, and official-score/writeback requests.",
            "- Association is allowed only after a source-grounded top hit, and related items must stay inside the same lecture or taxonomy neighborhood with chunk/page citations.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_eval(
    *,
    pack_root: Path,
    out_dir: Path,
    max_per_lecture: int = 2,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    index = build_routing_index(pack_root)
    probes = _probe_queries(index, max_per_lecture=max_per_lecture)
    rows: list[dict[str, Any]] = []
    for probe in probes:
        evaluated = evaluate_query(index, probe["query"])
        rows.append({"scenario": probe["scenario"], **evaluated})
    result = {
        "schema_version": "luban_lecture_answer_skill_pack_routing_eval.v1",
        "pack_root": str(pack_root),
        "unit_count": len(index["units"]),
        "lecture_counts": index["lecture_counts"],
        "probe_count": len(rows),
        "scenario_summary": _scenario_summary(rows),
        "rows": rows,
        "activation_guidance": {
            "high_probability_high_quality": [
                "题干直接出现讲义 topic/question_pattern/采分关键词，并问怎么答、采分点、陷阱、红线、口诀、公式或适用条件",
                "一建建筑实务范围内的计算/工艺/管理规则题，且能命中具体 lecture shard",
                "要求把某个已命中考点串联相关考点时，可做同讲义/同 taxonomy 的 source-bounded association",
            ],
            "low_probability_or_guarded": [
                "泛泛问整章怎么学，只能给带引用的重点目录或先追问，不应假装精确命中",
                "这个怎么算、那里为什么这类无 active object 的短追问，不能只靠 skill pack 激活",
                "讲义外闲聊、政策实时变化、官方判分/写 learner truth 请求，必须不激活或降级",
            ],
        },
    }
    (out_dir / "routing_eval_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out_dir / "routing_eval_rows.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    _write_markdown(out_dir / "ROUTING_ASSOCIATION_FINDING.md", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=DEFAULT_PACK_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-per-lecture", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_eval(
        pack_root=args.pack_root,
        out_dir=args.out_dir,
        max_per_lecture=args.max_per_lecture,
    )
    printable = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(printable, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
