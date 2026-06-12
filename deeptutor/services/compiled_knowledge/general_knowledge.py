"""General-knowledge compiled teaching context for M34.

This composes existing authorities only:
canonical text resolution -> canonical knowledge runtime. It never mints an
answer key, never writes learner truth, and falls open on low-signal input.
"""
from __future__ import annotations

import re
from typing import Any

from deeptutor.services.construction_grading import canonical_resolution as _CR
from deeptutor.services.construction_grading import canonical_knowledge_runtime as _CKR
from deeptutor.services.construction_grading import rich_leaf_runtime as _RLR

AUTHORITY = "luban_general_knowledge_context"
SOURCE_KEYS = ("textbook", "standard", "lecture", "question")
CONFIDENCE_POLICY = "query_path_source_alignment_v1"
QUERY_PLAN_POLICY = "compiled_query_plan_v1"
DEFAULT_TOP_K = 8

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]{1,}")
_CJK_SPAN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

_DOMAIN_PHRASES = tuple(
    sorted(
        {
            "建筑高度",
            "高层住宅",
            "高层建筑",
            "超高层",
            "防火分区",
            "耐火等级",
            "疏散楼梯",
            "混凝土强度",
            "强度等级",
            "施工缝",
            "大体积混凝土",
            "屋面防水",
            "防水等级",
            "地下防水",
            "临时用电",
            "三级配电",
            "开关箱",
            "临边防护",
            "洞口防护",
            "脚手架",
            "连墙件",
            "模板起拱",
            "基坑支护",
            "土方回填",
            "压实系数",
            "灌注桩",
            "泥浆护壁",
            "钢结构",
            "高强螺栓",
            "砌体结构",
            "拉结筋",
            "抹灰空鼓",
            "外墙保温",
            "施工组织设计",
            "网络计划",
            "双代号",
            "总时差",
            "分部工程",
            "质量验收",
            "施工合同",
            "合同索赔",
            "凝结时间",
            "水泥代号",
        },
        key=len,
        reverse=True,
    )
)
_PHRASE_ALIASES = {
    "高层住宅": ("高层", "住宅"),
    "建筑高度": ("高度",),
    "防火分区": ("防火", "分区"),
    "耐火等级": ("耐火",),
    "屋面防水": ("屋面", "防水"),
    "防水等级": ("防水",),
    "临时用电": ("用电",),
    "三级配电": ("配电",),
    "土方回填": ("回填",),
    "砌体结构": ("砌体",),
    "合同索赔": ("索赔",),
    "施工合同": ("合同",),
}
_PATH_COMPATIBILITY = (
    ("建筑高度", "按建筑层数分类", "建筑高度->按建筑层数分类"),
    ("高层住宅", "按建筑层数分类", "高层住宅->按建筑层数分类"),
    ("高层建筑", "按建筑层数分类", "高层建筑->按建筑层数分类"),
)
_CRITICAL_PATH_TERMS = {
    "防火分区": ("防火分区", "分区"),
    "耐火等级": ("耐火等级", "耐火"),
    "施工合同": (),
    "合同索赔": ("索赔",),
    "砌体结构": (),
    "拉结筋": ("拉结筋",),
    "网络计划": ("网络计划",),
    "双代号": ("双代号",),
    "总时差": ("总时差", "时差"),
    "屋面防水": ("屋面防水", "屋面"),
    "脚手架": ("脚手架",),
    "连墙件": ("连墙件",),
    "模板起拱": ("模板起拱", "起拱"),
    "分部工程": ("分部工程",),
}
_STRICT_PATH_TERMS = frozenset(
    {
        "分部工程",
        "防火分区",
        "耐火等级",
        "网络计划",
        "双代号",
        "总时差",
    }
)
_LOW_SIGNAL_TERMS = {
    "一个",
    "一下",
    "什么",
    "哪些",
    "可以",
    "应该",
    "怎么",
    "理解",
    "建筑",
    "施工",
    "工程",
    "现场",
    "管理",
    "要求",
    "规定",
    "分类",
    "特点",
    "材料",
    "结构",
    "等级",
}
_INTENT_MARKERS = {
    "calculation": ("计算", "怎么算", "多少", "公式", "总时差", "工期", "费用", "台班"),
    "standard_clause": ("规范", "条文", "规定", "gb", "jgj", "应当", "不得", "严禁"),
    "construction_method": ("施工", "工艺", "做法", "留置", "设置", "控制", "处理", "安装", "浇筑", "回填", "搭设"),
    "acceptance": ("验收", "检验", "合格", "组织验收", "主控项目", "一般项目"),
    "case_judgment": ("案例", "事件", "是否", "能否", "成立", "判断", "责任", "理由"),
}


def _anchor_candidates(leaf_code: str) -> list[str]:
    """Return a leaf code followed by prefix ancestors, longest first."""
    code = str(leaf_code or "").strip()
    if not code:
        return []
    parts = code.split("-")
    return ["-".join(parts[:idx]) for idx in range(len(parts), 0, -1)]


def _clip_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _extract_query_terms(text: str) -> list[str]:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return []

    terms: list[str] = []
    for phrase in _DOMAIN_PHRASES:
        if phrase.lower() in normalized:
            terms.append(phrase)
            terms.extend(_PHRASE_ALIASES.get(phrase, ()))
    terms.extend(_ASCII_TOKEN_RE.findall(normalized))

    if len(terms) < 2:
        for span in _CJK_SPAN_RE.findall(normalized):
            for size in (4, 3, 2):
                for idx in range(0, max(0, len(span) - size + 1)):
                    gram = span[idx : idx + size]
                    if gram in _LOW_SIGNAL_TERMS:
                        continue
                    terms.append(gram)
                    if len(terms) >= 8:
                        break
                if len(terms) >= 8:
                    break
            if len(terms) >= 8:
                break

    seen: set[str] = set()
    unique: list[str] = []
    for raw in terms:
        term = str(raw or "").strip()
        key = term.lower()
        if not term or key in seen or term in _LOW_SIGNAL_TERMS:
            continue
        seen.add(key)
        unique.append(term)
    return unique[:12]


def _extract_primary_terms(text: str) -> list[str]:
    normalized = str(text or "").strip().lower()
    terms = [phrase for phrase in _DOMAIN_PHRASES if phrase.lower() in normalized]
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            out.append(term)
    return out[:8]


def _critical_path_terms(primary_terms: list[str]) -> list[str]:
    terms: list[str] = []
    for term in primary_terms:
        if term in _CRITICAL_PATH_TERMS:
            terms.extend(_CRITICAL_PATH_TERMS[term])
        else:
            terms.append(term)
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            out.append(term)
    return out


def _classify_query_intent(text: str) -> str:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return "concept"
    for intent in ("calculation", "acceptance", "case_judgment", "standard_clause", "construction_method"):
        if any(marker in normalized for marker in _INTENT_MARKERS[intent]):
            return intent
    return "concept"


def _canonical_leaves() -> list[dict[str, Any]]:
    index = _CR._index() if hasattr(_CR, "_index") else None
    leaves = (index or {}).get("leaves") or []
    return [dict(item) for item in leaves if isinstance(item, dict)]


def _source_item_text(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item or "")
    parts: list[str] = []
    for key in (
        "text_preview",
        "content_preview",
        "public_quote",
        "content",
        "text",
        "title",
        "source",
        "source_id",
    ):
        value = item.get(key)
        if value:
            parts.append(str(value))
    provenance = item.get("provenance")
    if isinstance(provenance, dict):
        parts.extend(str(value) for value in provenance.values() if value)
    elif provenance:
        parts.append(str(provenance))
    return "\n".join(parts)


def _source_alignment_detached(node_code: str) -> bool:
    return (
        hasattr(_CKR, "is_general_compiled_context_detached")
        and _CKR.is_general_compiled_context_detached(str(node_code or ""))
    )


def _node_source_text(node_code: str, *, limit_per_source: int = 4) -> str:
    bundle = _CKR._load() if hasattr(_CKR, "_load") else None
    if not bundle:
        return ""
    parts: list[str] = []
    for source_key in SOURCE_KEYS:
        if hasattr(_CKR, "source_items_for_node"):
            items = _CKR.source_items_for_node(bundle, str(node_code or ""), source_key)[:limit_per_source]
        else:
            node = ((bundle.get("nodes") or {}).get(str(node_code or "")) or {})
            items = ((node.get("sources") or {}).get(source_key) or [])[:limit_per_source]
        parts.extend(_source_item_text(item) for item in items)
    return "\n".join(parts)


def _sources_text_and_counts(sources: dict[str, Any]) -> tuple[str, int, int]:
    texts: list[str] = []
    category_count = 0
    item_count = 0
    for source_key in SOURCE_KEYS:
        raw_items = sources.get(source_key) or []
        if not isinstance(raw_items, list) or not raw_items:
            continue
        category_count += 1
        item_count += len(raw_items)
        texts.extend(_source_item_text(item) for item in raw_items)
    return "\n".join(texts).lower(), category_count, item_count


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    lowered = str(text or "").lower()
    return [term for term in terms if term.lower() in lowered]


def _path_compatible_hits(path_text: str, terms: list[str]) -> list[str]:
    lowered_path = str(path_text or "").lower()
    lowered_terms = {term.lower() for term in terms}
    hits: list[str] = []
    for query_term, path_marker, label in _PATH_COMPATIBILITY:
        if query_term.lower() in lowered_terms and path_marker.lower() in lowered_path:
            hits.append(label)
    return hits


def _taxonomy_candidates(query_terms: list[str], *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for leaf in _canonical_leaves():
        code = str(leaf.get("code") or "").strip()
        if not code:
            continue
        name_path = str(leaf.get("name_path") or _CR.name_path(code) or code)
        keywords = [str(item or "") for item in (leaf.get("keywords") or []) if str(item or "").strip()]
        path_hits = _matched_terms(name_path, query_terms)
        path_hits.extend(_path_compatible_hits(name_path, query_terms))
        keyword_hits = _matched_terms(" ".join(keywords), query_terms)
        if not path_hits and not keyword_hits:
            continue
        preliminary_score = len(set(path_hits)) * 3.0 + len(set(keyword_hits)) * 1.5
        rows.append(
            {
                "node_code": code,
                "leaf_name_path": name_path,
                "origin": "taxonomy",
                "path_hits": sorted(set(path_hits)),
                "keyword_hits": sorted(set(keyword_hits)),
                "source_hits": [],
                "preliminary_score": round(preliminary_score, 4),
                "negative_evidence": ["compiler_source_alignment_detached"] if _source_alignment_detached(code) else [],
                "source_alignment_detached": _source_alignment_detached(code),
            }
        )
    rows.sort(key=lambda row: (-float(row["preliminary_score"]), str(row["node_code"])))
    return rows[:limit]


def _source_candidates(query_terms: list[str], *, limit: int) -> list[dict[str, Any]]:
    bundle = _CKR._load() if hasattr(_CKR, "_load") else None
    nodes = (bundle or {}).get("nodes") or {}
    rows: list[dict[str, Any]] = []
    for code, node in nodes.items():
        node_code = str(code or "").strip()
        if not node_code:
            continue
        name_path = _CR.name_path(node_code)
        source_text = _node_source_text(node_code)
        source_hits = _matched_terms(source_text, query_terms)
        if not source_hits:
            continue
        path_hits = _matched_terms(name_path, query_terms)
        path_hits.extend(_path_compatible_hits(name_path, query_terms))
        negative = [] if path_hits else ["source_path_conflict"]
        preliminary_score = len(set(source_hits)) * 1.25 + len(set(path_hits)) * 3.0
        rows.append(
            {
                "node_code": node_code,
                "leaf_name_path": name_path,
                "origin": "source",
                "path_hits": sorted(set(path_hits)),
                "keyword_hits": [],
                "source_hits": sorted(set(source_hits))[:8],
                "preliminary_score": round(preliminary_score, 4),
                "negative_evidence": sorted(
                    set(negative + (["compiler_source_alignment_detached"] if _source_alignment_detached(node_code) else []))
                ),
                "source_alignment_detached": _source_alignment_detached(node_code),
            }
        )
    rows.sort(key=lambda row: (-float(row["preliminary_score"]), str(row["node_code"])))
    return rows[:limit]


def _merge_candidates(*candidate_groups: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in candidate_groups:
        for candidate in group:
            code = str(candidate.get("node_code") or "").strip()
            if not code:
                continue
            existing = merged.get(code)
            if existing is None:
                merged[code] = dict(candidate)
                continue
            existing["origin"] = "+".join(sorted(set(str(existing.get("origin", "")).split("+") + [str(candidate.get("origin"))])))
            for key in ("path_hits", "critical_path_hits", "keyword_hits", "source_hits", "negative_evidence"):
                existing[key] = sorted(set((existing.get(key) or []) + (candidate.get(key) or [])))
            existing["source_alignment_detached"] = bool(
                existing.get("source_alignment_detached") or candidate.get("source_alignment_detached")
            )
            existing["preliminary_score"] = max(
                float(existing.get("preliminary_score") or 0.0),
                float(candidate.get("preliminary_score") or 0.0),
            )
    rows = list(merged.values())
    rows.sort(
        key=lambda row: (
            -float(row.get("preliminary_score") or 0.0),
            "source_path_conflict" in (row.get("negative_evidence") or []),
            str(row.get("node_code") or ""),
        )
    )
    return rows[:limit]


def _detached_stop_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate for candidate in candidates
        if candidate.get("source_alignment_detached") and bool(candidate.get("path_hits"))
    ]


def build_general_knowledge_query_plan(question_text: str, *, top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
    text = str(question_text or "").strip()
    query_terms = _extract_query_terms(text)
    primary_terms = _extract_primary_terms(text)
    critical_path_terms = _critical_path_terms(primary_terms)
    intent = _classify_query_intent(text)
    initial_leaf = _CR.to_canonical(text)
    initial_candidate: list[dict[str, Any]] = []
    if initial_leaf:
        name_path = _CR.name_path(initial_leaf)
        path_hits = _matched_terms(name_path, query_terms)
        path_hits.extend(_path_compatible_hits(name_path, query_terms))
        critical_hits = _matched_terms(name_path, critical_path_terms)
        initial_negative = [] if critical_hits or not critical_path_terms else ["single_winner_path_mismatch"]
        if _source_alignment_detached(initial_leaf):
            initial_negative.append("compiler_source_alignment_detached")
        initial_candidate.append(
            {
                "node_code": initial_leaf,
                "leaf_name_path": name_path,
                "origin": "single_winner",
                "path_hits": sorted(set(path_hits)),
                "critical_path_hits": sorted(set(critical_hits)),
                "keyword_hits": [],
                "source_hits": [],
                "preliminary_score": 2.0 + len(set(path_hits)) * 3.0 + len(set(critical_hits)) * 6.0,
                "negative_evidence": sorted(set(initial_negative)),
                "source_alignment_detached": _source_alignment_detached(initial_leaf),
            }
        )

    taxonomy = _taxonomy_candidates(query_terms, limit=max(top_k * 3, 12))
    source = _source_candidates(query_terms, limit=max(top_k * 3, 12))
    # a strict term only has veto power if at least one candidate can satisfy it
    # (path or keywords): a term absent from the whole compiled axis cannot
    # discriminate between candidates and must not veto the correct path.
    satisfiable_strict_terms = {
        term
        for term in critical_path_terms
        if term in _STRICT_PATH_TERMS
        and any(
            term in _matched_terms(str(c.get("leaf_name_path") or ""), [term])
            or term in (c.get("keyword_hits") or [])
            for c in [*taxonomy, *source]
        )
    }
    for candidate in [*taxonomy, *source]:
        critical_hits = _matched_terms(str(candidate.get("leaf_name_path") or ""), critical_path_terms)
        candidate["critical_path_hits"] = sorted(set(critical_hits))
        missing_strict_terms = sorted(
            term
            for term in critical_path_terms
            if term in satisfiable_strict_terms
            and term not in critical_hits
            and term not in (candidate.get("keyword_hits") or [])
        )
        if missing_strict_terms:
            negative = list(candidate.get("negative_evidence") or [])
            negative.append("primary_path_mismatch")
            candidate["negative_evidence"] = sorted(set(negative))
            candidate["preliminary_score"] = max(0.0, float(candidate.get("preliminary_score") or 0.0) - 2.5)
        elif critical_path_terms and not critical_hits:
            negative = list(candidate.get("negative_evidence") or [])
            negative.append("primary_path_mismatch")
            candidate["negative_evidence"] = sorted(set(negative))
            candidate["preliminary_score"] = max(0.0, float(candidate.get("preliminary_score") or 0.0) - 2.5)
        else:
            candidate["preliminary_score"] = float(candidate.get("preliminary_score") or 0.0) + len(set(critical_hits)) * 6.0

    merged = _merge_candidates(
        initial_candidate,
        taxonomy,
        source,
        limit=max(top_k * 3, top_k),
    )
    detached_candidates = [candidate for candidate in merged if candidate.get("source_alignment_detached")]
    detached_stop_candidates = _detached_stop_candidates(detached_candidates)
    candidates = [
        candidate for candidate in merged
        if not candidate.get("source_alignment_detached")
    ][:top_k]
    return {
        "authority": AUTHORITY,
        "policy": QUERY_PLAN_POLICY,
        "intent": intent,
        "query_terms": query_terms,
        "primary_terms": primary_terms,
        "critical_path_terms": critical_path_terms,
        "initial_leaf": initial_leaf,
        "candidate_count": len(candidates),
        "detached_candidate_count": len(detached_candidates),
        "detached_stop_candidate_count": len(detached_stop_candidates),
        "detached_candidates": detached_candidates[:top_k],
        "candidates": candidates,
        "fallback_contract": "low_confidence_returns_none_so_tutorbot_rag_remains_authority",
    }


def _confidence_gate(
    *,
    question_text: str,
    leaf_name_path: str,
    sources: dict[str, Any],
    candidate: dict[str, Any] | None = None,
    intent: str = "concept",
) -> dict[str, Any]:
    query_terms = _extract_query_terms(question_text)
    source_text, source_category_count, source_item_count = _sources_text_and_counts(sources)
    path_hits = _matched_terms(leaf_name_path, query_terms)
    path_hits.extend(_path_compatible_hits(leaf_name_path, query_terms))
    if isinstance(candidate, dict):
        path_hits.extend(str(item) for item in (candidate.get("path_hits") or []) if item)
        path_hits.extend(str(item) for item in (candidate.get("critical_path_hits") or []) if item)
    source_hits = _matched_terms(source_text, query_terms)
    if isinstance(candidate, dict):
        source_hits.extend(str(item) for item in (candidate.get("source_hits") or []) if item)
    path_hits = sorted(set(path_hits))
    source_hits = sorted(set(source_hits))
    negative_evidence = list(candidate.get("negative_evidence") or []) if isinstance(candidate, dict) else []
    if source_hits and not path_hits:
        negative_evidence.append("source_path_conflict")

    confidence: dict[str, Any] = {
        "status": "low",
        "policy": CONFIDENCE_POLICY,
        "intent": intent,
        "query_terms": query_terms,
        "path_hits": path_hits,
        "source_hits": source_hits[:8],
        "source_category_count": source_category_count,
        "source_item_count": source_item_count,
        "negative_evidence": sorted(set(negative_evidence)),
    }
    if not query_terms:
        confidence["reason"] = "no_query_terms"
        return confidence
    if source_category_count < 2:
        confidence["reason"] = "source_coverage_too_thin"
        return confidence
    if not source_hits:
        confidence["reason"] = "no_source_overlap"
        return confidence

    if any(
        marker in confidence["negative_evidence"]
        for marker in ("source_path_conflict", "primary_path_mismatch", "single_winner_path_mismatch")
    ):
        confidence["reason"] = "path_negative_evidence"
        confidence["score"] = 0.39
        return confidence

    if path_hits and (source_category_count >= 2 or source_item_count >= 4):
        source_score = min(0.2, 0.05 * len(set(source_hits))) + min(0.2, source_category_count * 0.05)
        path_score = min(0.5, 0.18 * len(set(path_hits)))
        intent_bonus = 0.06 if intent in {"case_judgment", "calculation", "construction_method", "acceptance"} else 0.03
        score = min(0.96, 0.25 + path_score + source_score + intent_bonus)
        if score < 0.72:
            confidence["reason"] = "below_calibrated_threshold"
            confidence["score"] = round(score, 4)
            return confidence
        confidence["status"] = "high"
        confidence["reason"] = "query_plan_path_source_rerank"
        confidence["score"] = round(score, 4)
        return confidence

    confidence["reason"] = "canonical_path_mismatch"
    confidence["score"] = 0.49 if path_hits else 0.35
    return confidence


def format_general_knowledge_grounding(pack: dict[str, Any] | None) -> str:
    """Render a high-confidence compiled TEACHING pack into LLM grounding text."""
    if not isinstance(pack, dict):
        return ""
    confidence = pack.get("confidence") if isinstance(pack.get("confidence"), dict) else {}
    if confidence.get("status") != "high":
        return ""
    sources = pack.get("sources") if isinstance(pack.get("sources"), dict) else {}
    if not any(sources.get(key) for key in SOURCE_KEYS):
        return ""

    labels = {
        "textbook": "教材",
        "standard": "规范",
        "lecture": "讲义",
        "question": "真题",
    }
    lines = [
        "【编译教学上下文 - 仅供讲解，非官方答案，不得作为官方判分依据】",
        f"知识点路径：{pack.get('leaf_name_path') or pack.get('resolved_anchor') or ''}",
        f"置信策略：{confidence.get('policy') or CONFIDENCE_POLICY} / {confidence.get('reason') or 'high'}",
    ]
    # rich-leaf compiled context renders FIRST when present (flag-gated upstream; absent keys ->
    # byte-identical legacy rendering). Rendering policy lives in rich_leaf_runtime (single place):
    # multi-leaf "rich_leaf_contexts" (primary first, char-capped) or legacy single key.
    lines.extend(_RLR.format_rich_leaf_pack_grounding_lines(pack))
    for source_key in SOURCE_KEYS:
        raw_items = sources.get(source_key) or []
        if not isinstance(raw_items, list):
            continue
        for raw_item in raw_items[:6]:
            item = raw_item if isinstance(raw_item, dict) else {}
            preview = str(
                item.get("text_preview")
                or item.get("content_preview")
                or item.get("public_quote")
                or item.get("content")
                or item.get("text")
                or ""
            ).strip()
            if not preview:
                continue
            provenance = item.get("provenance")
            if isinstance(provenance, dict):
                provenance_label = " / ".join(
                    str(provenance.get(key) or "").strip()
                    for key in ("title", "source", "source_id", "stable_source_id", "span")
                    if str(provenance.get(key) or "").strip()
                )
            else:
                provenance_label = str(provenance or "").strip()
            if not provenance_label:
                provenance_label = str(
                    item.get("title")
                    or item.get("source")
                    or item.get("source_id")
                    or labels[source_key]
                ).strip()
            lines.append(f"- [{labels[source_key]}·{provenance_label}] {_clip_text(preview, limit=700)}")
    return "\n".join(lines).strip()


def resolve_general_knowledge_context(
    question_text: str,
    *,
    learner_context: dict[str, Any] | None = None,
    per_source: int = 6,
) -> dict[str, Any] | None:
    """Resolve free text into a teaching-tier four-source pack, or None to fall open."""
    text = str(question_text or "").strip()
    if not text:
        return None

    focused_context = dict(learner_context or {})
    focused_context.setdefault("question_text", text)
    query_plan = build_general_knowledge_query_plan(text)
    if query_plan.get("detached_stop_candidate_count"):
        return None
    for candidate in query_plan.get("candidates") or []:
        candidate_code = str(candidate.get("node_code") or "").strip()
        if not candidate_code:
            continue
        if _source_alignment_detached(candidate_code):
            continue
        for anchor in _anchor_candidates(candidate_code):
            pack = _CKR.resolve_canonical_knowledge(
                anchor,
                learner_context=focused_context,
                per_source=per_source,
            )
            if pack:
                sources = pack.get("sources") if isinstance(pack.get("sources"), dict) else {}
                leaf_name_path = _CR.name_path(candidate_code)
                confidence = _confidence_gate(
                    question_text=text,
                    leaf_name_path=leaf_name_path,
                    sources=sources,
                    candidate=candidate,
                    intent=str(query_plan.get("intent") or "concept"),
                )
                if confidence.get("status") != "high":
                    candidate["confidence"] = confidence
                    continue
                resolved_pack: dict[str, Any] = {
                    "authority": AUTHORITY,
                    "mode": "general_knowledge_teaching_context",
                    "classified_leaf": candidate_code,
                    "leaf_name_path": leaf_name_path,
                    "resolved_anchor": anchor,
                    "tier": pack.get("tier", "teaching_context_not_answer_key"),
                    "official_score_allowed": False,
                    "llm_may_decide_correctness": False,
                    "confidence": confidence,
                    "query_plan": {
                        key: query_plan[key]
                        for key in ("authority", "policy", "intent", "query_terms", "initial_leaf", "fallback_contract")
                    } | {
                        "selected_candidate": candidate,
                    },
                    "canonical_taxonomy_version": pack.get("canonical_taxonomy_version"),
                    "selected_counts": pack.get("selected_counts"),
                    "sources": sources,
                    "graph_neighbors": pack.get("graph_neighbors") or {},
                    "remediation": pack.get("remediation"),
                    "writeback_performed": False,
                }
                # Rich-leaf compiled context overlay (frozen v3.0.1 pack, external release pointer).
                # ADDITIVE only and flag-gated (default OFF -> the pack above is byte-identical to
                # legacy); a miss / unavailable supply falls open to the legacy four-source chain.
                # The existing confidence gate above stays the routing authority — rich leaf only
                # supplies richer compiled CONTENT: the classified primary leaf first, plus
                # deterministic query-term supplement leaves for cross-knowledge case questions.
                # This caller only has ONE text (the current question) — its terms go to the
                # focus layer (full weight) and the background layer stays empty; callers that
                # split 背景/小问 (e.g. case-question runners) pass the background separately.
                if _RLR.rich_leaf_runtime_enabled():
                    riches = _RLR.get_rich_leaf_contexts(
                        [],
                        [candidate_code],
                        focus_terms=[str(term) for term in (query_plan.get("query_terms") or [])],
                    )
                    if riches:
                        resolved_pack["rich_leaf_contexts"] = riches
                return resolved_pack
    return None


__all__ = [
    "AUTHORITY",
    "CONFIDENCE_POLICY",
    "QUERY_PLAN_POLICY",
    "build_general_knowledge_query_plan",
    "format_general_knowledge_grounding",
    "resolve_general_knowledge_context",
]
