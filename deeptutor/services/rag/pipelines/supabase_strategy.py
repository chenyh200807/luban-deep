"""Legacy-style Supabase retrieval helpers for DeepTutor.

This module ports the core ideas of the older FastAPI retrieval stack into a
small, self-contained form suitable for DeepTutor:

- lightweight query expansion for contrast / question / standard queries
- second-pass decomposition when the first retrieval is weak
- optional DashScope rerank for fused results
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from http import HTTPStatus
import os
import re
from typing import Any


_FILLER_PATTERNS = (
    "请问",
    "帮我",
    "你说",
    "能否",
    "可以",
    "一下",
    "一下子",
    "这个",
    "这个题",
    "这道题",
    "我想问",
    "什么是",
    "什么叫",
)

_QUESTION_SUFFIXES = ("是什么", "有什么", "有哪些", "怎么做", "如何", "为什么", "区别", "关系")
_EXACT_QUESTION_ENDINGS = (
    "什么",
    "哪些",
    "哪项",
    "哪种",
    "哪个",
    "何者",
    "不正确的是",
    "正确的是",
    "错误的是",
)
_STANDARD_HINTS = (
    "规范",
    "标准",
    "条文",
    "要求",
    "依据",
    "规定",
    "第",
    "gb",
    "jgj",
    "cjj",
)
_QUESTION_HINTS = (
    "真题",
    "做题",
    "刷题",
    "案例题",
    "选择题",
    "多选",
    "单选",
    "题目",
    "题干",
    "答案",
    "解析",
    "下列",
    "哪项",
    "哪个",
    "不属于",
    "正确的是",
)
_CONTRAST_MARKERS = ("区别", "不同", "差异", "联系", "关系", "对比")
_TOKEN_RE = re.compile(r"[A-Za-z0-9./_-]+|[\u4e00-\u9fff]{2,12}")
_NODE_CODE_RE = re.compile(r"\b\d+(?:\.\d+){1,3}\b")
_STANDARD_CODE_RE = re.compile(r"(?:GB|JGJ|CJJ|GB/T|JGJ/T)\s*\d", re.IGNORECASE)
_STANDARD_CODE_EXTRACT_RE = re.compile(
    r"((?:GB|JGJ|CJJ|DBJ|DB)(?:/T)?)\s*(\d{2,5})(?:[-—](\d{4}))?",
    re.IGNORECASE,
)
_EXAM_OPTION_RE = re.compile(r"(?:^|\n|\s)[A-E][\.．、\)]\s*\S")
_EXAM_SPLIT_RE = re.compile(r"(?:^|\n|\s)[A-E][\.．、\)]\s*")
_EXAM_STRONG_KEYWORDS = ("选择题", "单选", "多选", "选项", "刷题", "真题", "做题")
_EXAM_WEAK_KEYWORDS = ("考点", "考试", "解析", "答案", "题目")
_MCQ_STEM_RE = re.compile(
    r"正确的[是有]|错误的[是有]|不正确的[是有]|不属于|属于|可计入|不可计入"
    r"|说法正确|说法错误|做法正确|做法错误|符合要求|不符合"
    r"|应[为是]|不应|可以|不可以|不得|应当"
    r"|（\s*）|（　）|\(\s*\)|\(　\)",
)
_CASE_BACKGROUND_MARKERS = ("【背景资料】", "背景资料")
_CASE_QUESTION_MARKERS = ("【问题】", "\n问题：", "\n问题:", "\n问题\n", "问题：", "问题:")
_CASE_SUBQUESTION_RE = re.compile(r"(?:^|\n)\s*(\d+)[\.、]\s*")
_STATIC_SYNONYMS: dict[str, tuple[str, ...]] = {
    "防水等级": ("一级防水", "二级防水", "三级防水"),
    "设防要求": ("防水设防", "设防层数", "防水层数"),
    "设防层数": ("设防要求", "防水层数", "防水做法"),
    "防水层数": ("设防层数", "设防要求"),
    "屋面工程": ("屋面防水", "屋面防水工程"),
    "地下工程": ("地下防水", "地下防水工程"),
    "重要程度": ("建筑物性质", "使用功能"),
    "使用功能": ("重要程度", "建筑物性质"),
    "验收": ("质量验收", "检验"),
}
_DOMAIN_KEYWORDS = (
    "混凝土",
    "钢筋",
    "模板",
    "养护",
    "浇筑",
    "振捣",
    "质量验收",
    "分项工程",
    "检验批",
    "主控项目",
    "一般项目",
    "屋面工程",
    "防水等级",
    "设防要求",
    "地下工程",
)


@dataclass(slots=True)
class SourceSelectionPlan:
    search_questions_bank: bool = True
    search_textbook_chunks: bool = True
    search_standard_chunks: bool = True
    search_exam_chunks: bool = True
    query_shape: str = "concept_like"
    query_form_complete: bool = True
    pruning_applied: bool = False
    pruning_reason: str | None = None
    selection_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QueryRewriteResult:
    original_query: str
    normalized_query: str
    primary_query: str
    variants: list[str]
    keywords: list[str] = field(default_factory=list)
    standard_codes: list[str] = field(default_factory=list)
    query_shape: str = "concept_like"
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExactQuestionProbe:
    query: str
    allowed_question_types: list[str] = field(default_factory=list)
    option_validation_required: bool = False
    stripped_from_full_query: bool = False
    reason: str = ""


def normalize_query(query: str) -> str:
    text = str(query or "").strip()
    if not text:
        return ""
    for pattern in _FILLER_PATTERNS:
        text = text.replace(pattern, " ")
    text = re.sub(r"[？?。！!；;，,：:（）()\[\]【】]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_standard_codes(query: str) -> list[str]:
    codes: list[str] = []
    for match in _STANDARD_CODE_EXTRACT_RE.finditer(str(query or "").strip()):
        prefix = match.group(1).upper().replace(" ", "")
        number = match.group(2)
        year = match.group(3)
        code = f"{prefix}{number}-{year}" if year else f"{prefix}{number}"
        if code not in codes:
            codes.append(code)
    return codes


def _split_mcq_stem_options(query: str) -> tuple[str, list[str]]:
    text = str(query or "").strip()
    if not text:
        return "", []
    if not _EXAM_SPLIT_RE.search(text):
        return text, []
    parts = [part.strip() for part in _EXAM_SPLIT_RE.split(text) if part.strip()]
    if not parts:
        return text, []
    return parts[0], parts[1:]


def extract_domain_keywords(text: str) -> list[str]:
    content = str(text or "").strip()
    if not content:
        return []
    norm_refs = re.findall(r"《([^》]+)》", content)
    found_terms = [term for term in _DOMAIN_KEYWORDS if term in content]
    if "屋面" in content and "工程" in content and "屋面工程" not in found_terms:
        found_terms.append("屋面工程")
    if "地下" in content and "工程" in content and "地下工程" not in found_terms:
        found_terms.append("地下工程")
    seen: set[str] = set()
    keywords: list[str] = []
    for term in [*norm_refs, *found_terms]:
        cleaned = str(term or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        keywords.append(cleaned)
    return keywords


def _expand_static_synonyms(text: str) -> list[str]:
    expansions: list[str] = []
    for canonical, synonyms in _STATIC_SYNONYMS.items():
        if canonical in text:
            for synonym in synonyms:
                if synonym not in expansions:
                    expansions.append(synonym)
            continue
        if any(synonym in text for synonym in synonyms):
            if canonical not in expansions:
                expansions.append(canonical)
    return expansions


def rewrite_query(query: str, *, max_variants: int = 6) -> QueryRewriteResult:
    original = str(query or "").strip()
    normalized = normalize_query(original)
    query_shape = classify_query_shape(original)
    standard_codes = extract_standard_codes(original)
    reasons: list[str] = [f"query_shape={query_shape}"]

    stem, options = _split_mcq_stem_options(original)
    primary_query = stem or original
    if query_shape == "case_like":
        primary_query = _build_case_focus_query(original) or primary_query
    keywords = extract_domain_keywords(primary_query)
    if query_shape == "mcq_like" and keywords:
        primary_query = f"{primary_query} {' '.join(keywords)}".strip()
        reasons.append("mcq_keyword_enhanced")

    variants: list[str] = []
    candidates = [primary_query, original]
    if normalized and normalized not in candidates:
        candidates.append(normalized)

    for code in standard_codes:
        candidates.append(code)
        spaced = re.sub(r"^([A-Z/]+)(\d+)", r"\1 \2", code)
        if spaced not in candidates:
            candidates.append(spaced)
        compact = code.split("-", 1)[0]
        if compact not in candidates:
            candidates.append(compact)
        reasons.append("standard_code_normalized")

    synonym_expansions = [] if standard_codes else _expand_static_synonyms(primary_query)
    for item in synonym_expansions:
        if item not in candidates:
            candidates.append(item)
    if synonym_expansions:
        reasons.append("static_synonyms")

    if options:
        option_keywords = extract_domain_keywords(" ".join(options))
        for keyword in option_keywords[:3]:
            if keyword not in keywords:
                keywords.append(keyword)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        clean = re.sub(r"\s+", " ", str(item or "").strip())
        if not clean or clean in seen:
            continue
        deduped.append(clean)
        seen.add(clean)
        if len(deduped) >= max_variants:
            break

    return QueryRewriteResult(
        original_query=original,
        normalized_query=normalized,
        primary_query=primary_query,
        variants=deduped or ([original] if original else []),
        keywords=keywords,
        standard_codes=standard_codes,
        query_shape=query_shape,
        reasons=reasons,
    )


def _looks_like_case_study(text: str) -> bool:
    content = str(text or "").strip()
    if len(content) < 80:
        return False
    has_background = any(marker in content for marker in _CASE_BACKGROUND_MARKERS)
    has_question_marker = any(marker in content for marker in _CASE_QUESTION_MARKERS)
    has_numbered_questions = len(_CASE_SUBQUESTION_RE.findall(content)) >= 2
    return has_background and (has_question_marker or has_numbered_questions)


def _extract_case_question_part(text: str) -> str:
    content = str(text or "").strip()
    if not content:
        return ""

    for marker in _CASE_QUESTION_MARKERS:
        if marker in content:
            return content.split(marker, 1)[1].strip()

    if any(marker in content for marker in _CASE_BACKGROUND_MARKERS):
        match = _CASE_SUBQUESTION_RE.search(content)
        if match:
            return content[match.start() :].strip()

    return content[-240:] if len(content) > 240 else content


def _extract_case_subquestions(text: str, *, max_items: int = 3) -> list[str]:
    question_part = _extract_case_question_part(text)
    if not question_part:
        return []

    matches = list(_CASE_SUBQUESTION_RE.finditer(question_part))
    if not matches:
        cleaned = normalize_query(question_part)
        return [cleaned] if cleaned else []

    items: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(question_part)
        chunk = question_part[start:end].strip()
        chunk = normalize_query(chunk)
        if chunk and chunk not in items:
            items.append(chunk[:120].strip())
        if len(items) >= max_items:
            break
    return items


def _build_case_focus_query(text: str) -> str:
    items = _extract_case_subquestions(text, max_items=2)
    if items:
        return "；".join(items)
    return normalize_query(_extract_case_question_part(text))[:160].strip()


def prepare_exact_question_probe(query: str) -> ExactQuestionProbe | None:
    original = str(query or "").strip()
    if not original:
        return None

    query_shape = classify_query_shape(original)
    exam_like = is_exam_like_query(original) or is_question_like_query(original)
    if query_shape not in {"mcq_like", "case_like"} and not exam_like:
        return None

    stem, options = _split_mcq_stem_options(original)
    has_options = bool(options)
    stage_query = original
    stripped_from_full_query = False
    allowed_types: list[str] = []
    reason_parts: list[str] = [f"query_shape={query_shape}"]

    if query_shape == "mcq_like":
        allowed_types = ["single", "multi"]
        reason_parts.append("mcq_allowed_types")
    elif query_shape == "case_like":
        allowed_types = ["case", "case_study", "case_background", "calculation"]
        stage_query = _build_case_focus_query(original) or original
        if stage_query != original:
            stripped_from_full_query = True
            reason_parts.append("case_question_focus")
        reason_parts.append("case_allowed_types")

    if has_options and len(stem.strip()) >= 10:
        stage_query = stem.strip()
        stripped_from_full_query = stage_query != original
        reason_parts.append("stem_only_for_exact_match")

    stage_query = re.sub(r"^(?:单选题|多选题|选择题|真题|题目)\s*[：:]\s*", "", stage_query).strip()
    cleaned = stage_query.replace("（", "").replace("）", "").split("\n")[0].strip()
    cleaned = re.sub(r"[。？：:]$", "", cleaned)
    if len(cleaned) < 6:
        cleaned = stage_query

    return ExactQuestionProbe(
        query=cleaned,
        allowed_question_types=allowed_types,
        option_validation_required=has_options and stripped_from_full_query,
        stripped_from_full_query=stripped_from_full_query,
        reason=",".join(reason_parts),
    )


def build_exact_question_text_candidates(query: str, *, max_candidates: int = 6) -> list[str]:
    original = str(query or "").strip()
    if not original:
        return []

    candidates: list[str] = []

    def _push(value: str) -> None:
        clean = str(value or "").strip()
        clean = re.sub(r"\s+", " ", clean)
        clean = re.sub(r"[。？：:]$", "", clean)
        if clean and clean not in candidates:
            candidates.append(clean)

    _push(original)

    stripped = re.sub(r"^(?:单选题|多选题|选择题|真题|题目)\s*[：:]\s*", "", original).strip()
    _push(stripped)

    if classify_query_shape(stripped) == "case_like":
        _push(_build_case_focus_query(stripped))
        question_part = _extract_case_question_part(stripped)
        _push(question_part[:120])
        for item in _extract_case_subquestions(stripped, max_items=3):
            _push(item)

    for ending in _EXACT_QUESTION_ENDINGS:
        if stripped.endswith(ending):
            prefix = stripped[: -len(ending)].strip()
            if len(prefix) >= 8:
                _push(prefix)
                _push(f"{prefix}（  ）")
                _push(f"{prefix}( )")

    normalized = normalize_query(stripped)
    _push(normalized)

    keywords = extract_domain_keywords(stripped)
    if keywords:
        keyword_query = " ".join([stripped, *keywords[:2]]).strip()
        _push(keyword_query)

    return candidates[:max_candidates]


def build_exact_question_keyword_terms(query: str, *, max_terms: int = 3) -> list[str]:
    focus_query = _extract_case_question_part(query) if classify_query_shape(query) == "case_like" else query
    text = normalize_query(focus_query)
    if not text:
        return []

    deduped: list[str] = []
    for keyword in extract_domain_keywords(focus_query):
        if keyword not in deduped:
            deduped.append(keyword)
        if len(deduped) >= max_terms:
            return deduped

    tokens = [
        token
        for token in _TOKEN_RE.findall(text)
        if token
        and len(token) >= 2
        and token not in _QUESTION_SUFFIXES
        and token not in {"单选题", "多选题", "选择题", "真题", "题目"}
    ]
    ranked = sorted(tokens, key=len, reverse=True)
    for token in ranked:
        if token not in deduped:
            deduped.append(token)
        if len(deduped) >= max_terms:
            break
    return deduped


def matches_allowed_question_type(
    question_type: str | None,
    allowed_question_types: list[str] | None,
) -> bool:
    if not allowed_question_types:
        return True
    normalized = str(question_type or "").strip().lower()
    if not normalized:
        return False
    return any(
        allowed in normalized or normalized in allowed
        for allowed in [str(item or "").strip().lower() for item in allowed_question_types]
        if allowed
    )


def validate_exact_question_options(
    *,
    original_query: str,
    options: Any,
    option_validation_required: bool,
) -> bool:
    if not option_validation_required:
        return True
    if not options:
        return False

    query_lower = _normalize_option_surface(original_query)
    option_values: list[str] = []
    if isinstance(options, dict):
        option_values = [value for value in options.values() if isinstance(value, str)]
    elif isinstance(options, list):
        for item in options:
            if isinstance(item, str):
                option_values.append(item)
            elif isinstance(item, dict):
                value = item.get("value")
                if isinstance(value, str):
                    option_values.append(value)

    for value in option_values:
        clean = _normalize_option_surface(value)
        if len(clean) >= 4 and clean[:12] in query_lower:
            return True
    return False


def _normalize_option_surface(text: str) -> str:
    clean = re.sub(r"^[A-E][\.、．\)]\s*", "", str(text or "").strip())
    clean = re.sub(r"^(?:单选题|多选题|选择题|真题|题目)\s*[：:]\s*", "", clean)
    clean = re.sub(r"[\s\W_]+", "", clean, flags=re.UNICODE)
    return clean.replace("的", "")


def is_question_like_query(query: str) -> bool:
    lowered = str(query or "").strip().lower()
    return any(token in lowered for token in _QUESTION_HINTS)


def is_standard_like_query(query: str) -> bool:
    lowered = str(query or "").strip().lower()
    return bool(_STANDARD_CODE_RE.search(lowered)) or any(token in lowered for token in _STANDARD_HINTS)


def is_exam_like_query(query: str) -> bool:
    text = str(query or "").strip()
    if not text:
        return False
    if _EXAM_OPTION_RE.search(text):
        return True
    if any(keyword in text for keyword in _EXAM_STRONG_KEYWORDS):
        return True
    return sum(1 for keyword in _EXAM_WEAK_KEYWORDS if keyword in text) >= 2


def classify_query_shape(query: str) -> str:
    text = str(query or "").strip()
    if not text:
        return "concept_like"
    if _EXAM_OPTION_RE.search(text):
        return "mcq_like"
    if any(keyword in text for keyword in _EXAM_STRONG_KEYWORDS):
        return "mcq_like"
    if _MCQ_STEM_RE.search(text):
        return "mcq_like"
    if _looks_like_case_study(text):
        return "case_like"
    if is_standard_like_query(text):
        return "standard_like"
    if re.search(r"计算|求|算一[下算]|工程量|面积|体积|造价|索赔", text):
        return "calc_like"
    return "concept_like"


def select_sources(query: str, *, include_questions_default: bool = True) -> SourceSelectionPlan:
    text = str(query or "").strip()
    plan = SourceSelectionPlan(search_questions_bank=include_questions_default)
    reasons: list[str] = []
    plan.query_shape = classify_query_shape(text)
    reasons.append(f"query_shape={plan.query_shape}")

    has_options = bool(_EXAM_OPTION_RE.search(text))
    if plan.query_shape == "mcq_like" and not has_options:
        plan.query_form_complete = False
        reasons.append("query_form_incomplete")

    exam_like = is_exam_like_query(text) or is_question_like_query(text)
    standard_like = is_standard_like_query(text)
    short_ambiguous = len(text) < 24 and plan.query_shape == "concept_like"

    if plan.query_shape == "case_like":
        plan.search_questions_bank = True
        plan.search_exam_chunks = True
        reasons.append("force_case_sources")
        plan.selection_reasons = reasons
        return plan

    if plan.query_shape == "mcq_like" or exam_like:
        plan.search_questions_bank = True
        reasons.append("force_qbank")

    if standard_like and not exam_like and plan.query_shape != "mcq_like":
        plan.search_questions_bank = False
        plan.search_exam_chunks = False
        plan.pruning_applied = True
        plan.pruning_reason = "standard_like_no_exam_signal"
        reasons.append("pruned_to_standard_textbook")
    elif (
        plan.query_shape == "concept_like"
        and not exam_like
        and plan.query_form_complete
        and not short_ambiguous
    ):
        plan.search_questions_bank = False
        plan.search_exam_chunks = False
        plan.pruning_applied = True
        plan.pruning_reason = "pure_concept_query"
        reasons.append("pruned_question_noise")
    else:
        reasons.append("no_pruning")

    plan.selection_reasons = reasons
    return plan


def resolve_group_weights(
    query: str,
    *,
    base_source_weights: dict[str, float],
    base_question_weights: dict[str, float],
) -> dict[str, float]:
    plan = select_sources(query)
    weights = dict(base_question_weights if plan.query_shape == "mcq_like" or is_exam_like_query(query) else base_source_weights)

    if plan.query_shape == "standard_like":
        weights["standard"] = max(weights.get("standard", 1.0), 1.8)
        weights["standard_precision"] = max(weights.get("standard_precision", 1.0), 2.4)
        weights["questions_bank"] = min(weights.get("questions_bank", 0.4), 0.2)
        weights["exam"] = min(weights.get("exam", 0.7), 0.3)
    elif plan.query_shape == "mcq_like":
        weights["questions_bank"] = max(weights.get("questions_bank", 1.0), 1.8)
        weights["exam"] = max(weights.get("exam", 1.0), 1.15)
        weights["standard"] = max(weights.get("standard", 1.0), 0.9)
    elif plan.query_shape == "case_like":
        weights["exam"] = max(weights.get("exam", 1.0), 1.6)
        weights["questions_bank"] = max(weights.get("questions_bank", 1.0), 1.2)
        weights["textbook"] = max(weights.get("textbook", 1.0), 1.05)
        weights["standard"] = min(weights.get("standard", 1.0), 0.8)
    elif is_contrast_query(query):
        weights["textbook"] = max(weights.get("textbook", 1.0), 1.2)
        weights["standard"] = max(weights.get("standard", 1.0), 1.35)
        weights["questions_bank"] = min(weights.get("questions_bank", 0.4), 0.35)
        weights["exam"] = min(weights.get("exam", 0.7), 0.45)
    elif plan.query_shape == "concept_like":
        weights["textbook"] = max(weights.get("textbook", 1.0), 1.1)
        weights["standard"] = max(weights.get("standard", 1.0), 1.25)
        weights["questions_bank"] = min(weights.get("questions_bank", 0.4), 0.25)
        weights["exam"] = min(weights.get("exam", 0.7), 0.35)

    return weights


def dedupe_ranked_results(
    results: list[dict[str, Any]],
    *,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_signatures: set[str] = set()

    for item in results:
        doc_id = str(item.get("chunk_id") or item.get("id") or "").strip()
        if doc_id and doc_id in seen_ids:
            continue
        title = re.sub(r"\s+", " ", str(item.get("card_title") or item.get("title") or "").strip().lower())
        content = re.sub(
            r"\s+",
            " ",
            str(item.get("rag_content") or item.get("content") or "").strip().lower(),
        )[:220]
        signature = f"{title}|{content}"
        if title and content and signature in seen_signatures:
            continue
        if doc_id:
            seen_ids.add(doc_id)
        if title and content:
            seen_signatures.add(signature)
        deduped.append(item)
        if max_items is not None and len(deduped) >= max_items:
            break

    return deduped


def is_contrast_query(query: str) -> bool:
    text = str(query or "").strip()
    return any(marker in text for marker in _CONTRAST_MARKERS)


def extract_node_code_prefix(query: str) -> str | None:
    match = _NODE_CODE_RE.search(str(query or "").strip())
    return match.group(0) if match else None


def _extract_entities_for_contrast(query: str) -> tuple[str, str] | None:
    text = normalize_query(query)
    if not text or not is_contrast_query(text):
        return None

    patterns = (
        r"(.{1,24}?)[和与及跟](.{1,24}?)(?:有?什么)?(?:区别|不同|差异|联系|关系)",
        r"(.{1,24}?)与(.{1,24}?)(?:的)?(?:区别|不同|差异|联系|关系)",
        r"(.{1,24}?)和(.{1,24}?)(?:的)?(?:区别|不同|差异|联系|关系)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        left = match.group(1).strip(" 的")
        right = match.group(2).strip(" 的")
        if left and right and left != right:
            return left, right
    return None


def expand_query_variants(query: str, *, max_variants: int = 6) -> list[str]:
    original = str(query or "").strip()
    if not original:
        return []

    rewritten = rewrite_query(original, max_variants=max_variants)
    normalized = normalize_query(original)
    candidates: list[str] = list(rewritten.variants[:2])
    if normalized and normalized not in candidates:
        candidates.append(normalized)

    if classify_query_shape(original) == "case_like":
        focus_query = _build_case_focus_query(original)
        if focus_query and focus_query not in candidates:
            candidates.append(focus_query)
        for item in _extract_case_subquestions(original, max_items=3):
            if item not in candidates:
                candidates.append(item)

    entities = _extract_entities_for_contrast(original)
    if entities:
        left, right = entities
        candidates.extend(
            [
                f"{left} 定义 要求",
                f"{right} 定义 要求",
                f"{left} {right} 区别 关系",
            ]
        )
    for item in rewritten.variants[2:]:
        if item not in candidates:
            candidates.append(item)

    node_code = extract_node_code_prefix(original)
    if node_code:
        candidates.append(node_code)
        candidates.append(f"{node_code} 规范 条文 要求")

    if is_standard_like_query(original):
        candidates.append(f"{normalized or original} 规范 条文")

    if is_question_like_query(original):
        candidates.append(f"{normalized or original} 真题 解析")

    tokens = [
        token
        for token in _TOKEN_RE.findall(normalized or original)
        if token and len(token) >= 2 and token not in _QUESTION_SUFFIXES
    ]
    if 2 <= len(tokens) <= 6:
        candidates.append(" ".join(tokens[:4]))

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        clean = re.sub(r"\s+", " ", str(item or "").strip())
        if not clean or clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)
        if len(deduped) >= max_variants:
            break
    return deduped


def build_second_pass_queries(query: str, *, max_queries: int = 2) -> list[str]:
    original = str(query or "").strip()
    if not original:
        return []

    candidates: list[str] = []
    if classify_query_shape(original) == "case_like":
        for item in _extract_case_subquestions(original, max_items=max_queries + 1):
            if item not in candidates:
                candidates.append(item)
        focus_query = _build_case_focus_query(original)
        if focus_query and focus_query not in candidates:
            candidates.append(focus_query)
    entities = _extract_entities_for_contrast(original)
    if entities:
        left, right = entities
        candidates.extend(
            [
                f"{left} 定义 适用范围",
                f"{right} 定义 适用范围",
                f"{left} {right} 对比 易错点",
            ]
        )
    else:
        normalized = normalize_query(original)
        clauses = [part.strip() for part in re.split(r"[，,；;。]", normalized) if part.strip()]
        for clause in clauses[:max_queries]:
            candidates.append(clause)
        if not candidates and normalized:
            tokens = [token for token in _TOKEN_RE.findall(normalized) if len(token) >= 2]
            if len(tokens) >= 2:
                candidates.append(" ".join(tokens[:3]))

    deduped: list[str] = []
    seen = {original}
    for item in candidates:
        clean = re.sub(r"\s+", " ", str(item or "").strip())
        if not clean or clean in seen:
            continue
        deduped.append(clean)
        seen.add(clean)
        if len(deduped) >= max_queries:
            break
    return deduped


def should_run_second_pass(
    *,
    query: str,
    results: list[dict[str, Any]],
    top_k: int,
    min_hits: int = 2,
    max_dup_ratio: float = 0.5,
) -> bool:
    if is_contrast_query(query):
        return True

    if len(results) < max(1, min_hits, min(3, top_k)):
        return True

    ids = [
        str(item.get("source") or item.get("source_doc") or item.get("chunk_id") or "").strip()
        for item in results
        if str(item.get("source") or item.get("source_doc") or item.get("chunk_id") or "").strip()
    ]
    if not ids:
        return False

    most_common = Counter(ids).most_common(1)[0][1]
    dup_ratio = most_common / max(len(ids), 1)
    return dup_ratio >= max_dup_ratio


async def rerank_documents(
    query: str,
    documents: list[str],
    *,
    top_n: int,
    timeout_s: float = 6.0,
) -> list[dict[str, Any]]:
    if not query or not documents:
        return []

    api_key = str(os.getenv("DASHSCOPE_API_KEY", "") or "").strip()
    model_name = str(os.getenv("SUPABASE_RAG_RERANK_MODEL", "gte-rerank") or "gte-rerank").strip()
    if not api_key:
        return []

    try:
        import dashscope
    except Exception:
        return []

    cleaned_docs = [str(item or "").strip() for item in documents if str(item or "").strip()]
    if not cleaned_docs:
        return []

    def _sync_call() -> list[dict[str, Any]]:
        response = dashscope.TextReRank.call(
            model=model_name,
            query=query,
            documents=cleaned_docs,
            top_n=top_n,
            return_documents=False,
            api_key=api_key,
        )
        if response.status_code != HTTPStatus.OK:
            return []
        results = response.output.get("results", [])
        return results if isinstance(results, list) else []

    try:
        return await asyncio.wait_for(asyncio.to_thread(_sync_call), timeout=timeout_s)
    except Exception:
        return []
