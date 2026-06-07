from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import json
import re
import threading
from typing import Any, Callable

from deeptutor.services.taxonomy.taxonomy_authority import (
    normalize_taxonomy_code as _normalize_authority_taxonomy_code,
)
from deeptutor.services.taxonomy.taxonomy_authority import (
    taxonomy_index,
)

_CODE_RE = re.compile(r"1A\d{3,6}(?:-\d{2})?(?:-[a-z])?", re.IGNORECASE)
_DEICTIC_TOPIC_RE = re.compile(r"^(?:这|这道|这一|这个|本|该|此|当前)(?:道|个|类)?(?:题|题目|选择题|案例题|真题)$")
_GENERIC_TOPIC_LABELS = {
    "这题",
    "这道题",
    "这一题",
    "这个题",
    "这类题",
    "本题",
    "该题",
    "此题",
    "题目",
    "当前题目",
    "当前考点",
    "当前知识点",
    "本次错因",
    "薄弱点",
    "知识点",
    "学习主题",
    "综合能力",
    "今天先稳住基础节奏",
    "保持节奏，继续推进",
    "建筑实务入门导学",
    "建筑实务入门诊断",
    "入门摸底",
}

TopicInferer = Callable[[dict[str, Any], list[str]], str]


@dataclass(frozen=True)
class ResolvedLearningTopic:
    label: str
    source: str
    confidence: str
    taxonomy_code: str = ""
    taxonomy_id: str = ""
    topic_id: str = ""

    def intent_fields(self) -> dict[str, str]:
        return {
            "concept_label": self.label,
            "topic_source": self.source,
            "topic_confidence": self.confidence,
            "taxonomy_code": self.taxonomy_code,
            "taxonomy_id": self.taxonomy_id,
            "topic_id": self.topic_id,
        }


def compile_taxonomy_payload(
    payload: dict[str, Any],
    *,
    source_path: str,
    content_sha256: str,
    deprecated_codes: set[str] | None = None,
) -> dict[str, Any]:
    """Compile the canonical outline into the legacy taxonomy authority artifact.

    ``deprecated_codes`` (single-authority projection): codes the concept_registry (B) adjudicated as
    fabricated via Opus+Codex dual-model review are EXCLUDED here, so this artifact never serves a
    fabricated concept as a label — A stays a consistent projection of B's truth, not a divergent
    second authority. Empty/None preserves legacy behaviour."""
    deprecated = {str(c) for c in (deprecated_codes or set())}
    nodes: list[dict[str, Any]] = []

    def walk(items: list[Any], path_names: list[str]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or item.get("node_code") or "").strip()
            name = normalize_learning_topic_text(item.get("name") or item.get("title"))
            if not code or not name:
                continue
            if code in deprecated:  # B-adjudicated fabricated concept -> never serve it
                walk(list(item.get("children") or []), [*path_names, name])
                continue
            next_path = [*path_names, name]
            keywords = [
                normalize_learning_topic_text(value)
                for value in list(item.get("keywords") or [])
                if normalize_learning_topic_text(value)
            ]
            nodes.append(
                {
                    "code": code,
                    "name": name,
                    "level": int(item.get("level") or len(next_path)),
                    "parent_code": str(item.get("parent_code") or "").strip(),
                    "path_names": next_path,
                    "keywords": keywords,
                }
            )
            walk(list(item.get("children") or []), next_path)

    walk(list(payload.get("outline_structure") or []), [])
    code_counts = Counter(str(node.get("code") or "") for node in nodes)
    ambiguous_codes = {
        code
        for code, count in code_counts.items()
        if count > 1
        and len({_compact(node.get("name")) for node in nodes if str(node.get("code") or "") == code}) > 1
    }
    name_codes: dict[str, set[str]] = {}
    for node in nodes:
        name = _compact(node.get("name"))
        code = str(node.get("code") or "")
        if name and code:
            name_codes.setdefault(name, set()).add(code)
    ambiguous_names = {name for name, codes in name_codes.items() if len(codes) > 1}
    seen_codes: dict[str, int] = {}
    for node in nodes:
        code = str(node.get("code") or "")
        seen_codes[code] = seen_codes.get(code, 0) + 1
        node["id"] = code if code_counts[code] == 1 else f"{code}#{seen_codes[code]}"

    return {
        "schema_version": 1,
        "source": {
            "path": source_path,
            "sha256": content_sha256,
            "meta": dict(payload.get("meta") or {}),
            "stats": _outline_tree_stats(payload),
        },
        "nodes": nodes,
        "nodes_by_id": {node["id"]: node for node in nodes},
        "nodes_by_code": {
            node["code"]: node
            for node in nodes
            if str(node.get("code") or "") not in ambiguous_codes
        },
        "duplicate_codes": sorted(code for code, count in code_counts.items() if count > 1),
        "ambiguous_codes": sorted(ambiguous_codes),
        "ambiguous_names": sorted(ambiguous_names),
    }


def _outline_tree_stats(payload: dict[str, Any]) -> dict[str, int]:
    total_nodes = 0
    leaf_nodes = 0
    code_counts: Counter[str] = Counter()

    def walk(items: list[Any]) -> None:
        nonlocal total_nodes, leaf_nodes
        for item in items:
            if not isinstance(item, dict):
                continue
            total_nodes += 1
            code = _normalize_authority_taxonomy_code(item.get("code") or item.get("node_code"))
            if code:
                code_counts[code] += 1
            children = list(item.get("children") or [])
            if children:
                walk(children)
            else:
                leaf_nodes += 1

    walk(list(payload.get("outline_structure") or []))
    return {
        "total_nodes": total_nodes,
        "coded_nodes": sum(code_counts.values()),
        "leaf_nodes": leaf_nodes,
        "unique_codes": len(code_counts),
        "duplicate_code_rows": sum(count - 1 for count in code_counts.values() if count > 1),
    }


def resolve_learning_topic_from_payload(
    payload: dict[str, Any],
    *,
    llm_topic_inferer: TopicInferer | None = None,
) -> ResolvedLearningTopic | None:
    index = _load_topic_index()
    evidence_candidates = _topic_text_candidates(payload)
    for topic_id in _taxonomy_id_candidates(payload):
        node = index["nodes_by_id"].get(topic_id)
        if node:
            return ResolvedLearningTopic(
                label=str(node.get("name") or topic_id),
                source="taxonomy_id",
                confidence="high",
                taxonomy_code=str(node.get("code") or ""),
                taxonomy_id=topic_id,
            )

    specific_focus_candidates = _specific_focus_candidates(payload)
    for label in specific_focus_candidates:
        topic = _resolve_confirmed_label(label, index)
        if topic:
            return topic

    if (
        specific_focus_candidates
        and llm_topic_inferer is not None
        and _has_topic_evidence(payload, evidence_candidates)
    ):
        inferred = normalize_learning_topic_text(llm_topic_inferer(payload, evidence_candidates))
        if inferred:
            return ResolvedLearningTopic(label=inferred, source="llm_inferred", confidence="low")
        fallback = _personalized_focus_from_candidates(specific_focus_candidates)
        if fallback:
            return fallback
        return None

    for code in _taxonomy_code_candidates(payload, evidence_candidates):
        node = index["nodes_by_code"].get(code)
        if node:
            return ResolvedLearningTopic(
                label=str(node.get("name") or code),
                source="taxonomy_code",
                confidence="high",
                taxonomy_code=code,
                taxonomy_id=str(node.get("id") or ""),
            )

    for label in evidence_candidates:
        topic = _resolve_confirmed_label(label, index)
        if topic:
            return topic

    if llm_topic_inferer is not None and _has_topic_evidence(payload, evidence_candidates):
        inferred = normalize_learning_topic_text(llm_topic_inferer(payload, evidence_candidates))
        if inferred:
            return ResolvedLearningTopic(label=inferred, source="llm_inferred", confidence="low")
        return _personalized_focus_from_candidates(evidence_candidates)
    return None


def _resolve_confirmed_label(label: str, index: dict[str, dict[str, dict[str, Any]]]) -> ResolvedLearningTopic | None:
    node = index["nodes_by_name"].get(_compact(label))
    if node:
        return ResolvedLearningTopic(
            label=str(node.get("name") or label),
            source="taxonomy_label",
            confidence="high",
            taxonomy_code=str(node.get("code") or ""),
            taxonomy_id=str(node.get("id") or ""),
        )
    return None


def infer_learning_topic_with_llm(payload: dict[str, Any], candidates: list[str]) -> str:
    prompt = {
        "task": "infer_one_construction_exam_learning_topic",
        "rules": [
            "Return only one concise Chinese learning topic.",
            "Do not return pronouns such as 这题、本题、当前考点.",
            "Do not invent a taxonomy code.",
            "Use the user's evidence text only.",
        ],
        "candidates": candidates[:8],
        "evidence": {
            "question_stem": str(payload.get("question_stem") or "")[:800],
            "simple_explanation": str(payload.get("simple_explanation") or "")[:800],
            "explanation": str(payload.get("explanation") or "")[:800],
        },
    }
    try:
        from deeptutor.services.llm.factory import complete

        async def call_llm() -> str:
            return await complete(
                json.dumps(prompt, ensure_ascii=False),
                system_prompt="你是一级建造师建筑实务学习主题归纳器。只输出一个短主题，不要解释。",
                max_retries=0,
                temperature=0,
                max_tokens=32,
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(call_llm())
        else:
            result_holder: dict[str, str] = {}
            error_holder: dict[str, BaseException] = {}

            def runner() -> None:
                try:
                    result_holder["value"] = asyncio.run(call_llm())
                except BaseException as exc:
                    error_holder["error"] = exc

            thread = threading.Thread(target=runner, name="learning-topic-llm", daemon=True)
            thread.start()
            thread.join()
            if error_holder:
                return ""
            result = result_holder.get("value", "")
    except Exception:
        return ""
    return normalize_learning_topic_text(result.splitlines()[0] if result else "")


def normalize_learning_topic_text(value: Any) -> str:
    text = str(value or "").strip().strip("“”\"'。；;，,")
    for prefix in ("今日焦点：", "今日焦点:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    compact = _compact(text)
    if not compact:
        return ""
    if compact in _GENERIC_TOPIC_LABELS:
        return ""
    if _DEICTIC_TOPIC_RE.fullmatch(compact):
        return ""
    return text


@lru_cache(maxsize=1)
def _load_topic_index() -> dict[str, dict[str, dict[str, Any]]]:
    return taxonomy_index()


def _taxonomy_id_candidates(payload: dict[str, Any]) -> list[str]:
    raw_values: list[Any] = [
        payload.get("taxonomy_id"),
        payload.get("topic_taxonomy_id"),
    ]
    for source in (payload.get("concept"), payload.get("next_training_signal")):
        if isinstance(source, dict):
            raw_values.extend([source.get("taxonomy_id"), source.get("topic_taxonomy_id")])
    ids: list[str] = []
    for value in raw_values:
        topic_id = str(value or "").strip()
        if topic_id and topic_id not in ids:
            ids.append(topic_id)
    return ids


def _specific_focus_candidates(payload: dict[str, Any]) -> list[str]:
    signal = payload.get("next_training_signal") if isinstance(payload.get("next_training_signal"), dict) else {}
    values = [
        signal.get("focus"),
        signal.get("topic"),
    ]
    candidates: list[str] = []
    for value in values:
        text = normalize_learning_topic_text(value)
        if text and not _CODE_RE.fullmatch(text) and text not in candidates:
            candidates.append(text)
    return candidates


def _taxonomy_code_candidates(payload: dict[str, Any], text_candidates: list[str]) -> list[str]:
    raw_values: list[Any] = [
        payload.get("taxonomy_code"),
        payload.get("node_code"),
        payload.get("learning_state_ref"),
    ]
    for source in (payload.get("concept"), payload.get("next_training_signal")):
        if isinstance(source, dict):
            raw_values.extend([source.get("id"), source.get("code"), source.get("taxonomy_code"), source.get("node_code")])
    raw_values.extend(text_candidates)
    codes: list[str] = []
    for value in raw_values:
        for match in _CODE_RE.findall(str(value or "")):
            code = _normalize_taxonomy_code(match)
            if code not in codes:
                codes.append(code)
    return codes


def _normalize_taxonomy_code(value: str) -> str:
    return _normalize_authority_taxonomy_code(value)


def _topic_text_candidates(payload: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    signal = payload.get("next_training_signal") if isinstance(payload.get("next_training_signal"), dict) else {}
    concept = payload.get("concept") if isinstance(payload.get("concept"), dict) else {}
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    values.extend([signal.get("focus"), signal.get("concept"), concept.get("label"), concept.get("name")])
    values.extend(list(payload.get("knowledge_points") or []))
    values.extend([error.get("concept_tag")])
    candidates: list[str] = []
    for value in values:
        text = normalize_learning_topic_text(value)
        if text and text not in candidates:
            candidates.append(text)
    return candidates


def _has_topic_evidence(payload: dict[str, Any], candidates: list[str]) -> bool:
    if candidates:
        return True
    return any(str(payload.get(key) or "").strip() for key in ("question_stem", "simple_explanation", "explanation"))


def _personalized_focus_from_candidates(candidates: list[str]) -> ResolvedLearningTopic | None:
    for label in candidates:
        text = normalize_learning_topic_text(label)
        if text and not _CODE_RE.fullmatch(text):
            return ResolvedLearningTopic(label=text, source="evidence_inferred", confidence="low")
    return None


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


__all__ = [
    "ResolvedLearningTopic",
    "TopicInferer",
    "compile_taxonomy_payload",
    "infer_learning_topic_with_llm",
    "normalize_learning_topic_text",
    "resolve_learning_topic_from_payload",
]
