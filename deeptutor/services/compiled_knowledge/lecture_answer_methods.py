"""Lecture-derived answer-method teaching overlay for Luban TutorBot.

This module consumes the signed all-lecture runtime_supply bundle as a read-only
teaching overlay. It is not a RAG replacement, not an answer key, and never
writes learner truth. Low-confidence or off-syllabus queries return ``None`` so
the caller falls open to the existing TutorBot/RAG path.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Any


AUTHORITY = "luban_lecture_answer_method_context"
TIER = "teaching_answer_method_not_answer_key"
DEFAULT_SUPPLY_ROOT = (
    Path(__file__).resolve().parents[1]
    / "construction_grading"
    / "runtime_supply"
    / "v_lecture_answer_skill_pack_all8"
)
AD_TERMS = ("小佑题库", "佑森在线", "官方企微", "扫码关注", "免费听课", "在线刷题", "售后反馈")
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
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _contains_any(query: str, terms: tuple[str, ...]) -> bool:
    return any(term in query for term in terms)


def _clip(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _capabilities(unit: dict[str, Any]) -> dict[str, bool]:
    method = unit.get("answer_method") if isinstance(unit.get("answer_method"), dict) else {}
    return {
        "must_mentions": bool(_as_list(method.get("must_mentions"))),
        "trap_red_line": bool(_as_list(method.get("trap_alerts")) or _as_list(method.get("red_lines"))),
        "mnemonic": bool(_as_list(method.get("mnemonics"))),
        "formula_condition": bool(_as_list(method.get("formula_or_thresholds"))),
        "citation": bool((unit.get("source_ref") or {}).get("source_chunk_id")),
    }


def _tokenize_unit(unit: dict[str, Any]) -> list[str]:
    taxonomy = unit.get("taxonomy") if isinstance(unit.get("taxonomy"), dict) else {}
    method = unit.get("answer_method") if isinstance(unit.get("answer_method"), dict) else {}
    values: list[Any] = [
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
    tokens: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _norm(value)
        if len(token) >= 2 and token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


@lru_cache(maxsize=8)
def _load_index_cached(pack_root_text: str) -> dict[str, Any]:
    pack_root = Path(pack_root_text)
    manifest = _load_json(pack_root / "manifest.json")
    units: list[dict[str, Any]] = []
    for shard in manifest.get("shards") or []:
        shard_path = pack_root / str(shard.get("path") or "")
        doc = _load_json(shard_path)
        for raw in doc.get("answer_units") or []:
            if not isinstance(raw, dict):
                continue
            unit = dict(raw)
            rendered = json.dumps(unit, ensure_ascii=False)
            if any(term in rendered for term in AD_TERMS):
                continue
            source = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
            unit["_routing_tokens"] = _tokenize_unit(unit)
            unit["_capabilities"] = _capabilities(unit)
            unit["_source_ref_compact"] = {
                "chunk_id": source.get("source_chunk_id"),
                "json_page_num": source.get("json_page_num"),
            }
            units.append(unit)
    return {
        "pack_root": str(pack_root),
        "manifest": manifest,
        "units": units,
    }


def _load_index(pack_root: Path | None = None) -> dict[str, Any] | None:
    root = pack_root or DEFAULT_SUPPLY_ROOT
    try:
        return _load_index_cached(str(root))
    except OSError:
        return None


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
            elif token != lecture_token and len(token) >= 2 and any(
                intents[key]
                for key in (
                    "exam_answer",
                    "trap_red_line",
                    "formula_condition",
                    "mnemonic",
                    "association",
                )
            ):
                score += 0.18
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
    if activation_band == "none" or not top_units:
        return "not_applicable"
    top = top_units[0]
    caps = top.get("_capabilities") or {}
    expected: list[str] = ["citation", "must_mentions"]
    if intents["trap_red_line"]:
        expected.append("trap_red_line")
    if intents["formula_condition"]:
        expected.append("formula_condition")
    if intents["mnemonic"]:
        expected.append("mnemonic")
    hits = sum(1 for key in expected if caps.get(key))
    ratio = hits / len(expected)
    if activation_band == "high" and ratio >= 0.75:
        return "high"
    if activation_band in {"high", "medium"} and ratio >= 0.5:
        return "medium"
    return "low"


def _public_unit(unit: dict[str, Any], *, score: float, include_answer_method: bool = True) -> dict[str, Any]:
    method = unit.get("answer_method") if isinstance(unit.get("answer_method"), dict) else {}
    row = {
        "unit_id": unit.get("unit_id"),
        "lecture": unit.get("lecture"),
        "topic": unit.get("topic"),
        "score": round(score, 4),
        "capabilities": unit.get("_capabilities") or {},
        "source_ref": unit.get("_source_ref_compact") or {},
    }
    if include_answer_method:
        row["answer_method"] = {
            "answer_style": method.get("answer_style"),
            "must_mentions": _as_list(method.get("must_mentions")),
            "red_lines": _as_list(method.get("red_lines")),
            "trap_alerts": _as_list(method.get("trap_alerts")),
            "mnemonics": _as_list(method.get("mnemonics")),
            "formula_or_thresholds": _as_list(method.get("formula_or_thresholds")),
        }
        row["source_excerpt"] = _clip(unit.get("source_excerpt"), limit=420)
    return row


def _related_units(units: list[dict[str, Any]], seed: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    lecture = seed.get("lecture")
    taxonomy = seed.get("taxonomy") if isinstance(seed.get("taxonomy"), dict) else {}
    topic = taxonomy.get("topic") or seed.get("topic")
    rows: list[tuple[float, dict[str, Any]]] = []
    for unit in units:
        if unit.get("unit_id") == seed.get("unit_id"):
            continue
        if unit.get("lecture") != lecture:
            continue
        candidate_taxonomy = unit.get("taxonomy") if isinstance(unit.get("taxonomy"), dict) else {}
        score = 0.45
        if topic and topic in {candidate_taxonomy.get("topic"), unit.get("topic"), candidate_taxonomy.get("node_name")}:
            score += 0.25
        if (unit.get("_capabilities") or {}).get("trap_red_line"):
            score += 0.08
        if (unit.get("_capabilities") or {}).get("formula_condition"):
            score += 0.05
        rows.append((score, unit))
    rows.sort(key=lambda item: (-item[0], str(item[1].get("unit_id") or "")))
    return [_public_unit(unit, score=score, include_answer_method=False) for score, unit in rows[:limit]]


def resolve_lecture_answer_method_context(
    question_text: str,
    *,
    learner_context: dict[str, Any] | None = None,
    pack_root: Path | None = None,
    max_units: int = 3,
) -> dict[str, Any] | None:
    """Resolve a student question into all8 lecture answer-method context."""
    text = str(question_text or "").strip()
    if not text:
        return None
    index = _load_index(pack_root)
    if not index:
        return None
    intents = _query_intents(text)
    query_norm = _norm(text)
    scored = [(_unit_score(query_norm, unit, intents), unit) for unit in index["units"]]
    scored.sort(key=lambda item: (-item[0], str(item[1].get("unit_id") or "")))
    positive = [(score, unit) for score, unit in scored if score > 0]
    top_score = positive[0][0] if positive else 0.0
    band = _activation_band(top_score)
    if intents["off_syllabus"] and top_score < 0.58:
        return None
    if band not in {"high", "medium"}:
        return None
    context_candidates = [(score, unit) for score, unit in positive if score >= 0.34]
    if not context_candidates and positive:
        context_candidates = [positive[0]]
    top_units = [unit for _score, unit in context_candidates[:max_units]]
    quality = _quality_band(top_units, intents, band)
    if quality == "low":
        return None
    selected = [
        _public_unit(unit, score=score)
        for score, unit in context_candidates[:max_units]
    ]
    association_allowed = bool(intents["association"] and positive)
    related = _related_units(index["units"], positive[0][1]) if association_allowed else []
    scores = [row["score"] for row in selected]
    return {
        "authority": AUTHORITY,
        "mode": "lecture_answer_method_context",
        "tier": TIER,
        "official_score_allowed": False,
        "llm_may_decide_correctness": False,
        "writeback_performed": False,
        "source_pack": "v_lecture_answer_skill_pack_all8",
        "pack_scope": (index.get("manifest") or {}).get("scope"),
        "question_text": text,
        "learner_context_present": bool(learner_context),
        "activation": {
            "score": round(top_score, 4),
            "band": band,
            "quality_band": quality,
            "avg_selected_score": round(mean(scores), 4) if scores else 0.0,
            "policy": "lecture_answer_method_routing_v1",
        },
        "intents": intents,
        "selected_units": selected,
        "association": {
            "allowed": association_allowed,
            "policy": "same_lecture_or_same_taxonomy_only_with_chunk_citations",
            "related_units": related,
        },
        "fallback_contract": "low_confidence_returns_none_so_existing_tutorbot_rag_remains_authority",
    }


def _method_lines(unit: dict[str, Any]) -> list[str]:
    method = unit.get("answer_method") if isinstance(unit.get("answer_method"), dict) else {}
    ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    lines = [
        f"- 考点：{unit.get('lecture') or ''} / {unit.get('topic') or ''}",
        f"  出处：json_page_num={ref.get('json_page_num')}；chunk_id={ref.get('chunk_id')}",
    ]
    fields = [
        ("答题方式", [method.get("answer_style")] if method.get("answer_style") else []),
        ("采分关键词", _as_list(method.get("must_mentions"))),
        ("公式/阈值/适用条件", _as_list(method.get("formula_or_thresholds"))[:5]),
        ("陷阱提醒", _as_list(method.get("trap_alerts"))),
        ("红线", _as_list(method.get("red_lines"))),
        ("口诀", _as_list(method.get("mnemonics"))),
    ]
    for label, values in fields:
        if values:
            lines.append(f"  {label}：" + "；".join(_clip(item, limit=140) for item in values))
    excerpt = _clip(unit.get("source_excerpt"), limit=260)
    if excerpt:
        lines.append(f"  讲义摘录：{excerpt}")
    return lines


def format_lecture_answer_method_grounding(pack: dict[str, Any] | None) -> str:
    if not isinstance(pack, dict):
        return ""
    if pack.get("authority") != AUTHORITY:
        return ""
    units = pack.get("selected_units") if isinstance(pack.get("selected_units"), list) else []
    if not units:
        return ""
    lines = [
        "【讲义答题方法 - 仅供考试答法/讲解，非官方答案，不得作为官方判分依据】",
        f"激活策略：{(pack.get('activation') or {}).get('policy')} / {(pack.get('activation') or {}).get('band')} / {(pack.get('activation') or {}).get('quality_band')}",
        "答题要求：只使用下列讲义出处组织采分点；材料没有的内容写“材料未提供”；不要混入讲义外知识。",
    ]
    for unit in units[:3]:
        lines.extend(_method_lines(unit))
    association = pack.get("association") if isinstance(pack.get("association"), dict) else {}
    related = association.get("related_units") if isinstance(association.get("related_units"), list) else []
    if related:
        lines.append("联想边界：只可联想到下列同讲义/同 taxonomy 近邻，并必须引用其 chunk/page。")
        for unit in related[:5]:
            ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
            lines.append(
                f"- 相关考点：{unit.get('lecture') or ''} / {unit.get('topic') or ''}"
                f"；json_page_num={ref.get('json_page_num')}；chunk_id={ref.get('chunk_id')}"
            )
    rendered = "\n".join(lines).strip()
    if any(term in rendered for term in AD_TERMS):
        return ""
    return rendered


__all__ = [
    "AUTHORITY",
    "DEFAULT_SUPPLY_ROOT",
    "TIER",
    "format_lecture_answer_method_grounding",
    "resolve_lecture_answer_method_context",
]
