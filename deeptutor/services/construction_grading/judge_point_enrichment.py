"""judge_point_enrichment — 为 artifact_first_llm_judge 编译结构化判定字段。

Nexus 精髓的本地化：把运行时反复 prompt 推理前移到编译层。本模块产出：

- ``list_spec``：list/list_rule 策略的结构化分母（deterministic partial-score 依据）。
- ``calculation_spec``：计算点的 expected_value（artifact 直传优先，criterion 数字解析兜底）。
- ``compile_judge_aliases``：LLM 编译 semantic alias / negative evidence，仅用于 judge
  理解上下文，**不是官方可得分项**（``official_scoring_authority=False``）。

每个派生字段都带 provenance（source / confidence / field_hash），失败 fail-closed。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_LIST_POLICIES = {"list", "list_rule"}
_CALC_POLICIES = {"calc", "calculation"}

_DENOMINATOR_RE = re.compile(r"应得分项为\s*(\d+)\s*项")
_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")

# llm_compile_fn(points) -> {point_id: {"aliases": [...], "negative_evidence": [...]}}
AliasCompileFn = Callable[[list[dict[str, Any]]], dict[str, dict[str, Any]]]


def _field_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _provenance(source: str, confidence: float, value: Any) -> dict[str, Any]:
    return {
        "source": source,
        "confidence": round(float(confidence), 4),
        "field_hash": _field_hash(value),
    }


def derive_list_spec(point: dict[str, Any]) -> dict[str, Any] | None:
    """list/list_rule 策略 → 结构化 {denominator, provenance}；其余策略返回 None。"""
    policy = str(point.get("policy_type") or point.get("policy") or "").strip()
    if policy not in _LIST_POLICIES:
        return None
    list_rule = str(point.get("list_rule") or "")
    match = _DENOMINATOR_RE.search(list_rule)
    if match:
        denominator = int(match.group(1))
        return {
            "denominator": denominator,
            "provenance": _provenance("list_rule_text", 0.95, {"denominator": denominator,
                                                               "list_rule": list_rule}),
        }
    terms = [str(t) for t in list(point.get("required_terms") or []) if str(t).strip()]
    if terms:
        return {
            "denominator": len(terms),
            "provenance": _provenance("required_terms", 0.8, terms),
        }
    return None


def derive_calculation_spec(point: dict[str, Any]) -> dict[str, Any] | None:
    """calculation 策略 → {expected_value, provenance}；artifact 直传优先。"""
    policy = str(point.get("policy_type") or point.get("policy") or "").strip()
    if policy not in _CALC_POLICIES:
        return None
    existing = point.get("calculation_spec")
    if isinstance(existing, dict) and str(existing.get("expected_value") or "").strip():
        expected = str(existing["expected_value"]).strip()
        return {
            "expected_value": expected,
            "provenance": _provenance("artifact_calculation_spec", 1.0, expected),
        }
    criterion = str(point.get("criterion") or point.get("text") or "")
    numbers = _NUMBER_RE.findall(criterion)
    if numbers:
        # 取最后一个数字：计算点的 criterion 通常以结果值收尾（如 "总工期=31.5天"）
        expected = numbers[-1]
        return {
            "expected_value": expected,
            "provenance": _provenance("criterion_number_parse", 0.6, expected),
        }
    return None


def enrich_scoring_point(point: dict[str, Any]) -> dict[str, Any]:
    """不可变增强：返回带 list_spec / calculation_spec 的新 point，原 point 不被修改。"""
    enriched = dict(point)
    list_spec = derive_list_spec(point)
    if list_spec:
        enriched["list_spec"] = list_spec
    calc_spec = derive_calculation_spec(point)
    if calc_spec:
        enriched["calculation_spec"] = {
            "expected_value": calc_spec["expected_value"],
            "provenance": calc_spec["provenance"],
        }
    return enriched


def compile_judge_aliases(
    points: list[dict[str, Any]],
    *,
    llm_compile_fn: AliasCompileFn,
) -> dict[str, dict[str, Any]]:
    """LLM 编译 semantic alias / negative evidence（judge 理解用，非官方得分项）。

    fail-closed：LLM 失败返回 {}，judge 在无 alias 上下文时照常工作。
    """
    valid_ids = {str(p.get("point_id") or "") for p in points if str(p.get("point_id") or "")}
    try:
        raw = llm_compile_fn(points) or {}
    except Exception:  # noqa: BLE001 — alias 编译失败不得阻塞判分主链
        logger.warning("judge_point_enrichment: alias compile failed; returning empty", exc_info=True)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for point_id, entry in raw.items():
        pid = str(point_id)
        if pid not in valid_ids or not isinstance(entry, dict):
            continue
        aliases = [str(a).strip() for a in list(entry.get("aliases") or []) if str(a).strip()]
        negative = [str(n).strip() for n in list(entry.get("negative_evidence") or []) if str(n).strip()]
        out[pid] = {
            "aliases": aliases,
            "negative_evidence": negative,
            "official_scoring_authority": False,
            "provenance": _provenance("llm_alias_compiler", 0.5,
                                      {"aliases": aliases, "negative_evidence": negative}),
        }
    return out


__all__ = [
    "compile_judge_aliases",
    "derive_calculation_spec",
    "derive_list_spec",
    "enrich_scoring_point",
]
