#!/usr/bin/env python3
"""Case-question (案例大题) clean-RAG vs Nexus-like typed artifact eval.

Cross-knowledge case questions are the known weak zone of every prior arm; the multi-leaf
rich supplement (``get_rich_leaf_contexts``) was built exactly for them. This runner samples
complete real-exam case questions (background + numbered sub-questions + gold answers),
grades each SUB-QUESTION independently with a scoring-point judge, and compares five fixed arms:

- ``kbv5_only``: clean kb_v5 top-3 retrieval only (default: standard+textbook, no exam);
- ``kbv5_plus_runtime_slim``: kb_v5 plus production-shaped 1200-char rich-leaf render;
- ``runtime_slim_only``: production-shaped rich-leaf render only.
- ``typed_runtime_slim_only``: typed rich-leaf artifact only;
- ``kbv5_plus_typed_runtime_slim``: kb_v5 plus typed rich-leaf artifact.

Full source spans are resolved only as compiler/evidence-validation input for typed artifacts;
they are not supplied to the solver as runtime context.

Candidate/review-only. No runtime install, no canonical truth writes, no DB writes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import random
import re
from statistics import mean
import time
from typing import Any, Callable
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[1]
SCHEMA = "luban_rich_leaf_case_question_typed_ab.v2"

ARM_KBV5_ONLY = "kbv5_only"
ARM_KBV5_PLUS_RUNTIME_SLIM = "kbv5_plus_runtime_slim"
ARM_RUNTIME_SLIM_ONLY = "runtime_slim_only"
ARM_TYPED_RUNTIME_SLIM_ONLY = "typed_runtime_slim_only"
ARM_KBV5_PLUS_TYPED_RUNTIME_SLIM = "kbv5_plus_typed_runtime_slim"
ARM_DEPLOYED = ARM_KBV5_PLUS_RUNTIME_SLIM
ARM_BASELINE = ARM_KBV5_ONLY
PLANNED_ARMS = [
    ARM_KBV5_ONLY,
    ARM_RUNTIME_SLIM_ONLY,
    ARM_TYPED_RUNTIME_SLIM_ONLY,
    ARM_KBV5_PLUS_RUNTIME_SLIM,
    ARM_KBV5_PLUS_TYPED_RUNTIME_SLIM,
]

VALID_VERDICTS = {"correct", "partial", "wrong"}
VERDICT_SCORE = {"correct": 1.0, "partial": 0.5, "wrong": 0.0}

DEFAULT_EXAM_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库")
DEFAULT_SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_EXAM_YEARS = (2021, 2022, 2023, 2024, 2025)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_case_question_typed_ab_20260613"
DEFAULT_KBV5_DOC_TYPES = ("standard", "textbook")

RICH_TOP_K = 3
RICH_RENDER_MAX_CHARS = 1200
FULL_SPAN_RENDER_MAX_CHARS = 6000
FULL_SPAN_RECORD_CLIP = 2200
CHUNK_CONTENT_CLIP = 450
BACKGROUND_PROMPT_CLIP = 800
JUDGE_BACKGROUND_CLIP = 300

PROVIDER_DEFAULTS = {
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
}

ProviderCall = Callable[..., dict[str, Any]]


# ---------------------------------------------------------------- io helpers


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_dotenv() -> None:
    for path in (REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        if not path.exists():
            continue
        for line in path.read_text("utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")


def _openai_compat_provider(*, provider: str, model: str | None, timeout_s: float) -> ProviderCall | None:
    _load_dotenv()
    spec = PROVIDER_DEFAULTS[provider]
    api_key = os.environ.get(spec["env_key"])
    if not api_key:
        return None
    base_url = (os.environ.get(spec["base_url_env"]) or spec["base_url"]).rstrip("/")
    selected_model = model or spec["model"]

    def call(messages: list[dict[str, str]], *, max_tokens: int = 800, timeout_s: float = timeout_s) -> dict[str, Any]:
        started = time.monotonic()
        body = json.dumps(
            {
                "model": selected_model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{provider}_http_error:{exc.code}:{text[:200]}") from exc
        content = str(payload["choices"][0]["message"].get("content") or "")
        finish_reason = str(payload["choices"][0].get("finish_reason") or "")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return {
            "model": selected_model,
            "content": content,
            "finish_reason": finish_reason,
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
        }

    return call


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(text[start : end + 1])
                return payload if isinstance(payload, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def _clip(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _parse_doc_types(value: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    else:
        parts = [str(part).strip() for part in value]
    doc_types = tuple(part for part in parts if part)
    if not doc_types:
        raise ValueError("at least one kbv5 doc_type is required")
    return doc_types


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _record_text(record: dict[str, Any]) -> str:
    for key in (
        "content_markdown",
        "content",
        "text",
        "markdown",
        "body",
        "answer",
        "analysis",
        "stem",
        "question",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("question_data", "source_meta", "metadata"):
        nested = record.get(key)
        if isinstance(nested, dict):
            text = _record_text(nested)
            if text:
                return text
    return ""


class FullSpanSourceResolver:
    """Read full source records referenced by a rich-leaf ``source_ref``.

    This is eval-only oracle supply: it resolves the original source record behind a selected
    compiled leaf. It never writes source files and never treats compiled_context as full span.
    """

    def __init__(self, source_root: Path):
        self.source_root = source_root
        self._cache: dict[Path, Any] = {}
        self.stats = {"resolved": 0, "source_missing": 0, "record_missing": 0, "empty_text": 0}

    def _path(self, source_ref: dict[str, Any]) -> Path | None:
        raw = str(source_ref.get("source_path") or source_ref.get("relative_path") or "").strip()
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_absolute() else self.source_root / path

    def _load(self, path: Path) -> Any | None:
        if path in self._cache:
            return self._cache[path]
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._cache[path] = payload
        return payload

    @staticmethod
    def _match_record(record: dict[str, Any], *, record_id: str, chunk_id: str) -> bool:
        rid = str(record.get("record_id") or "").strip()
        cid = str(record.get("chunk_id") or "").strip()
        if record_id and rid == record_id:
            return True
        if chunk_id and cid == chunk_id:
            return True
        if record_id and chunk_id and record_id.endswith(f"#chunk:{chunk_id}"):
            return cid == chunk_id
        return False

    def resolve(self, source_ref: dict[str, Any]) -> dict[str, Any]:
        for key in ("full_span", "source_span", "span", "excerpt", "source_excerpt"):
            value = source_ref.get(key)
            if isinstance(value, str) and value.strip():
                self.stats["resolved"] += 1
                return {"status": "resolved", "text": value.strip(), "source": "source_ref_inline"}

        path = self._path(source_ref)
        record_id = str(source_ref.get("record_id") or "").strip()
        chunk_id = str(source_ref.get("chunk_id") or "").strip()
        if path is None or not path.exists():
            self.stats["source_missing"] += 1
            return {"status": "source_missing", "text": "", "source_path": str(path) if path else None}

        payload = self._load(path)
        for record in _iter_dicts(payload):
            if self._match_record(record, record_id=record_id, chunk_id=chunk_id):
                text = _record_text(record)
                if not text:
                    self.stats["empty_text"] += 1
                    return {"status": "empty_text", "text": "", "source_path": str(path)}
                self.stats["resolved"] += 1
                return {"status": "resolved", "text": text, "source_path": str(path)}

        self.stats["record_missing"] += 1
        return {"status": "record_missing", "text": "", "source_path": str(path)}


# ---------------------------------------------------------------- case bank

_SUB_MARKER = re.compile(
    r"(?:【\s*问题\s*】\s*(\d+)\s*[\.、]?\s*|问题\s*(\d+)\s*[：:]\s*|问题\s*[：:]\s*(\d+)\s*[\.、]\s*)"
)
_PARA_NUMBERED = re.compile(r"\n\s*(\d+)\s*[\.、]\s*(?=[^\d])")
_QUESTION_HINTS = ("？", "?", "哪些", "指出", "写出", "改正", "答出", "列出", "判断", "计算", "分析", "绘制", "说明")
_BG_PREFIX = re.compile(r"^(?:#+\s*)?(?:【\s*背景资料\s*】|【\s*案例背景\s*】|案例背景|背景资料)\s*[：:]?\s*")
_KEY_CHARS = re.compile(r"[^0-9A-Za-z一-鿿]")


def _norm_key(text: str, *, limit: int) -> str:
    """Punctuation/whitespace-insensitive dedupe key (full-width variants collapse)."""
    return _KEY_CHARS.sub("", str(text or ""))[:limit]


def split_case_stem(stem: str) -> tuple[str, str, str] | None:
    """Split one case_study stem into (background, sub_no, sub_question_text), or None to drop."""
    text = str(stem or "")
    markers = list(_SUB_MARKER.finditer(text))
    if markers:
        match = markers[-1]
        sub_no = next((g for g in match.groups() if g), "")
        return text[: match.start()].strip(), sub_no, text[match.end() :].strip()
    numbered = list(_PARA_NUMBERED.finditer(text))
    if numbered:
        match = numbered[-1]
        tail = text[match.end() :].strip()
        if tail and len(tail) < 240 and any(hint in tail for hint in _QUESTION_HINTS):
            return text[: match.start()].strip(), match.group(1), tail
    return None


def _background_key(background: str) -> str:
    # 64 normalized chars: long enough to separate distinct cases, short enough to merge the
    # same case republished with appended background paragraphs (observed divergence at ~75).
    return _norm_key(_BG_PREFIX.sub("", background.strip()), limit=64)


def _case_id(year: int, key: str) -> str:
    import hashlib

    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:6]
    return f"{year}:{key[:16]}:{digest}"


def extract_case_groups(exam_payload: dict[str, Any], *, year: int) -> list[dict[str, Any]]:
    """Group case_study exercises of one exam into case大题 keyed by normalized background."""
    groups: dict[str, dict[str, Any]] = {}
    for chunk in exam_payload.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        node_code = str((chunk.get("taxonomy") or {}).get("node_code") or "")
        for exercise in chunk.get("exercises") or []:
            if not isinstance(exercise, dict) or str(exercise.get("type")) != "case_study":
                continue
            data = exercise.get("question_data") if isinstance(exercise.get("question_data"), dict) else {}
            gold = str(data.get("correct_answer") or "").strip()
            if not gold:
                continue
            parts = split_case_stem(str(data.get("stem") or ""))
            if parts is None:
                continue
            background, sub_no, sub_text = parts
            if not background or not sub_text:
                continue
            key = _background_key(background)
            if not key:
                continue
            group = groups.setdefault(
                key,
                {"year": year, "background_key": key, "background": background, "sub_questions": {}},
            )
            if len(background) > len(str(group["background"])):
                group["background"] = background
            sub_key = f"q{sub_no}" if sub_no else _norm_key(sub_text, limit=40)
            existing = group["sub_questions"].get(sub_key)
            candidate = {
                "sub_no": sub_no,
                "text": sub_text,
                "gold_answer": gold,
                "gold_analysis": str(data.get("analysis") or ""),
                "score": float(data.get("score") or 0.0),
                "node_code": node_code or str(exercise.get("predicted_node") or ""),
            }
            # On sub_no collision prefer the cleanly-split (shorter) sub text; among equals keep
            # the longer gold answer (glued multi-question stems lose to their split variants).
            if (
                existing is None
                or len(sub_text) < len(str(existing.get("text") or ""))
                or (sub_text == existing.get("text") and len(gold) > len(str(existing.get("gold_answer") or "")))
            ):
                group["sub_questions"][sub_key] = candidate
    results: list[dict[str, Any]] = []
    for key in sorted(groups):
        group = groups[key]
        subs = sorted(group["sub_questions"].values(), key=lambda s: (str(s["sub_no"]), str(s["text"])))
        results.append(
            {
                "case_id": _case_id(year, key),
                "year": year,
                "background": group["background"],
                "sub_questions": [
                    {**sub, "sub_id": f"{_case_id(year, key)}:q{sub['sub_no'] or index + 1}.{index}"}
                    for index, sub in enumerate(subs)
                ],
            }
        )
    return results


def load_case_bank(exam_dir: Path, years: tuple[int, ...]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for year in years:
        path = exam_dir / f"{year}年一级建造师《建筑实务》考试真题及答案解析" / f"FINAL_CLEANED_EXAM_V{year}.json"
        if not path.exists():
            continue
        cases.extend(extract_case_groups(_read_json(path), year=year))
    return cases


def sample_cases(cases: list[dict[str, Any]], *, seed: int, count: int, min_subs: int = 2) -> list[dict[str, Any]]:
    eligible = sorted((c for c in cases if len(c["sub_questions"]) >= min_subs), key=lambda c: c["case_id"])
    rng = random.Random(seed)
    picked = rng.sample(eligible, min(count, len(eligible)))
    return sorted(picked, key=lambda c: c["case_id"])


# ---------------------------------------------------------------- arm contexts


def _kbv5_retriever(top_k: int, *, doc_types: tuple[str, ...] = DEFAULT_KBV5_DOC_TYPES) -> Callable[[str], dict[str, Any]]:
    import sys

    sys.path.insert(0, str(REPO))
    _load_dotenv()
    from deeptutor.services.rag.pipelines.kbv5 import _KbV5Unavailable, _retrieve_chunks

    def retrieve(query: str) -> dict[str, Any]:
        try:
            result = _retrieve_chunks(
                query,
                top_k=top_k,
                doc_types=doc_types,
                data_version=int(os.getenv("KBV5_RAG_DATA_VERSION", "2026")),
            )
        except _KbV5Unavailable as exc:
            return {"status": "unavailable", "error": str(exc)[:200], "chunks": [], "latency_ms": 0.0}
        return {
            "status": "completed",
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_type": chunk.doc_type,
                    "score_final": chunk.score_final,
                    "content": chunk.content,
                }
                for chunk in result.chunks
            ],
            "latency_ms": result.latency_ms,
        }

    retrieve.config = {"top_k": int(top_k), "doc_types": list(doc_types)}  # type: ignore[attr-defined]
    return retrieve


def _pack_rich_index(pack_path: Path) -> dict[str, dict[str, Any]]:
    """Build an in-process rich-leaf index straight from a frozen runtime token pack file via the
    production bundle compiler (temporary supply bundle: schema pin + safety invariants validated,
    quarantined units excluded). The tracked ``runtime_supply/v_rich_leaf_context`` on disk is
    never touched — this is a candidate/review-only eval supply override."""
    import sys

    sys.path.insert(0, str(REPO))
    from deeptutor.services.construction_grading import rich_leaf_runtime as rich_runtime

    bundle, _pointer = rich_runtime.build_runtime_supply_bundle(_read_json(pack_path))
    return {
        str(record.get("leaf_id")): record
        for record in bundle.get("records") or []
        if isinstance(record, dict) and str(record.get("leaf_id") or "").strip()
    }


def _format_full_span_grounding_lines(
    contexts: list[dict[str, Any]],
    *,
    resolver: FullSpanSourceResolver | None,
    supply_index: dict[str, dict[str, Any]],
    max_chars: int,
) -> tuple[str, dict[str, Any]]:
    if resolver is None:
        return "", {"enabled": False}
    lines: list[str] = []
    for index, ctx in enumerate(contexts, start=1):
        leaf_id = str(ctx.get("leaf_id") or "").strip()
        leaf_name = str(ctx.get("leaf_name_path") or ctx.get("leaf_name") or "").strip()
        source_ref = ctx.get("source_ref") if isinstance(ctx.get("source_ref"), dict) else {}
        if not source_ref and leaf_id in supply_index:
            source_ref = supply_index[leaf_id].get("source_ref") if isinstance(supply_index[leaf_id].get("source_ref"), dict) else {}
        resolved = resolver.resolve(source_ref)
        source_path = str(source_ref.get("source_path") or resolved.get("source_path") or "").strip()
        record_id = str(source_ref.get("record_id") or source_ref.get("chunk_id") or "").strip()
        header = f"【全文证据 L{index}】({leaf_id}) {leaf_name}".strip()
        meta = "；".join(part for part in (source_path, record_id, f"status={resolved['status']}") if part)
        text = _clip(resolved.get("text") or "", limit=FULL_SPAN_RECORD_CLIP)
        if not text:
            text = f"[full-span unavailable: {resolved['status']}]"
        lines.append(f"{header}\n〔源:{meta}〕\n{text}")
    return _clip("\n\n".join(lines), limit=max_chars), {"enabled": True, **resolver.stats}


_FLAW_TERMS = ("不妥", "错误", "正确做法", "改正", "原因分析", "质量问题")
_EXCEPTION_TERMS = ("不得", "不应", "禁止", "严禁", "可不受限制", "不宜", "除", "不得超过")
_FORMULA_TERMS = ("计算", "公式", "造价", "成本", "费用", "费率", "合价", "价款", "万元", "亿元", "%", "×", "=")
_APPLICABILITY_TERMS = ("应", "宜", "可", "适用", "条件", "标准", "规定", "要求", "方法", "程序")


def _jsonish(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def _text_from_compiled_item(item: Any) -> str:
    item = _jsonish(item)
    if isinstance(item, dict):
        for key in ("statement", "description", "content", "title", "quote"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return _clip(json.dumps(item, ensure_ascii=False, sort_keys=True), limit=260)
    return str(item or "").strip()


def _source_refs_from_item(item: Any, fallback_leaf: str) -> list[str]:
    item = _jsonish(item)
    refs: list[str] = []
    if isinstance(item, dict):
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        for value in (
            provenance.get("chunk_id"),
            provenance.get("source_ref"),
            item.get("chunk_id"),
            item.get("source_ref"),
        ):
            if value:
                refs.append(str(value))
        for key in ("source_refs", "sources"):
            raw = item.get(key)
            if isinstance(raw, list):
                refs.extend(str(value) for value in raw if value)
    if not refs and fallback_leaf:
        refs.append(f"leaf:{fallback_leaf}")
    return list(dict.fromkeys(refs))[:4]


def _typed_entry(text: str, *, leaf_id: str, family: str, source_refs: list[str], required_terms: list[str] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "text": _clip(text, limit=220),
        "leaf_id": leaf_id,
        "family": family,
        "source_refs": source_refs,
    }
    terms = [str(term).strip() for term in (required_terms or []) if str(term).strip()]
    if terms:
        entry["required_terms"] = terms[:8]
    return entry


def _append_unique(target: list[dict[str, Any]], entry: dict[str, Any], *, max_items: int) -> None:
    text = str(entry.get("text") or "")
    if not text or any(str(item.get("text") or "") == text for item in target):
        return
    if len(target) < max_items:
        target.append(entry)


def _build_typed_artifact(contexts: list[dict[str, Any]], *, full_span_resolution: dict[str, Any]) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "artifact_schema": "rich_leaf_typed_artifact.v1",
        "shape": {
            "flaw_correction_points": "不妥/错误/原因/正确做法 candidates",
            "applicability_conditions": "适用条件、标准要求、方法程序",
            "exceptions": "禁止、不得、不应、例外、限制",
            "formula_steps": "计算公式、费用构成、数值步骤",
            "scoring_points": "compiled scoring-point candidates",
            "source_refs": "field-level source identifiers; no full source span text",
        },
        "leaf_ids": [str(ctx.get("leaf_id") or "") for ctx in contexts if str(ctx.get("leaf_id") or "").strip()],
        "flaw_correction_points": [],
        "applicability_conditions": [],
        "exceptions": [],
        "formula_steps": [],
        "scoring_points": [],
        "source_refs": [],
        "compiler_input_status": {"full_span_resolution": full_span_resolution},
    }
    all_refs: list[str] = []
    for ctx in contexts:
        leaf_id = str(ctx.get("leaf_id") or "").strip()
        compiled = ctx.get("compiled_context") if isinstance(ctx.get("compiled_context"), dict) else {}
        for family in ("scoring_points", "rules", "concepts", "exam_patterns", "teaching_cards"):
            raw_items = compiled.get(family) if isinstance(compiled.get(family), list) else []
            for raw_item in raw_items:
                item = _jsonish(raw_item)
                text = _text_from_compiled_item(item)
                if not text:
                    continue
                required_terms = []
                if isinstance(item, dict) and isinstance(item.get("required_terms"), list):
                    required_terms = [str(term) for term in item.get("required_terms") or []]
                refs = _source_refs_from_item(item, leaf_id)
                all_refs.extend(refs)
                entry = _typed_entry(text, leaf_id=leaf_id, family=family, source_refs=refs, required_terms=required_terms)
                if family == "scoring_points":
                    _append_unique(artifact["scoring_points"], entry, max_items=10)
                haystack = f"{text} {' '.join(required_terms)}"
                if any(term in haystack for term in _FLAW_TERMS):
                    _append_unique(artifact["flaw_correction_points"], entry, max_items=8)
                if any(term in haystack for term in _EXCEPTION_TERMS):
                    _append_unique(artifact["exceptions"], entry, max_items=8)
                if any(term in haystack for term in _FORMULA_TERMS):
                    _append_unique(artifact["formula_steps"], entry, max_items=8)
                if any(term in haystack for term in _APPLICABILITY_TERMS):
                    _append_unique(artifact["applicability_conditions"], entry, max_items=8)
    artifact["source_refs"] = list(dict.fromkeys(all_refs))[:20]
    return artifact


def _rich_resolver(
    *,
    pack_path: Path | None = None,
    grading: bool = False,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    full_span_max_chars: int = FULL_SPAN_RENDER_MAX_CHARS,
) -> Callable[[str, str], dict[str, Any]]:
    """Deployment-shaped two-layer multi-leaf rich resolver: the SUB-QUESTION text supplies the
    focus layer (full-weight terms + primary classified leaf — 小问主导选叶), the case background
    supplies the 0.3x background layer; -> ``get_rich_leaf_contexts`` (top_k=3) -> 1200-char-capped
    grounding render with citable 【教材要点 Ln】 block labels. The same selected leaves are also
    resolved back to their source records for the full-span oracle arms.

    ``pack_path`` swaps the tracked runtime supply for a pack-file-built index (process-local
    override of the runtime loader; see ``_pack_rich_index``). ``grading=True`` renders the
    ``scoring_points`` family first (grading-priority block layout)."""
    import sys

    sys.path.insert(0, str(REPO))
    from deeptutor.services.compiled_knowledge.general_knowledge import (
        build_general_knowledge_query_plan,
    )
    from deeptutor.services.construction_grading import rich_leaf_runtime as rich_runtime

    supply_source = "tracked_runtime_supply_v_rich_leaf_context"
    if pack_path is not None:
        index = _pack_rich_index(pack_path)
        cache_clear = getattr(rich_runtime._load_index, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()
        rich_runtime._load_index = lambda: index  # process-local eval override, never persisted
        supply_source = str(pack_path)
        supply_index = index
    else:
        supply_index = rich_runtime._load_index()

    def _first_candidate(plan: dict[str, Any]) -> str:
        for candidate in plan.get("candidates") or []:
            code = str((candidate or {}).get("node_code") or "").strip()
            if code:
                return code
        return ""

    source_resolver = FullSpanSourceResolver(source_root)

    def resolve(background: str, sub_text: str) -> dict[str, Any]:
        focus_plan = build_general_knowledge_query_plan(sub_text)
        background_plan = build_general_knowledge_query_plan(background)
        focus_terms = [str(term) for term in (focus_plan.get("query_terms") or [])]
        background_terms = [str(term) for term in (background_plan.get("query_terms") or [])]
        primary_code = _first_candidate(focus_plan) or _first_candidate(background_plan)
        primary = [primary_code] if primary_code else []
        contexts = rich_runtime.get_rich_leaf_contexts(
            background_terms, primary, focus_terms=focus_terms, top_k=RICH_TOP_K
        )
        lines = rich_runtime.format_rich_leaf_pack_grounding_lines(
            {"rich_leaf_contexts": contexts}, max_chars=RICH_RENDER_MAX_CHARS, grading=grading
        )
        full_span_grounding, full_span_resolution = _format_full_span_grounding_lines(
            contexts, resolver=source_resolver, supply_index=supply_index, max_chars=full_span_max_chars
        )
        typed_artifact = _build_typed_artifact(contexts, full_span_resolution=full_span_resolution)
        return {
            "leaf_ids": [str(ctx.get("leaf_id") or "") for ctx in contexts],
            "primary_leaf": primary_code or None,
            "focus_terms": focus_terms,
            "background_terms": background_terms,
            "grounding": "\n".join(lines),
            "full_span_grounding": full_span_grounding,
            "full_span_resolution": full_span_resolution,
            "typed_artifact": typed_artifact,
            "supply_source": supply_source,
        }

    resolve.supply_info = {  # type: ignore[attr-defined]
        "source": supply_source,
        "grading_render": bool(grading),
        "runtime_slim_render_max_chars": RICH_RENDER_MAX_CHARS,
        "full_span_source_root": str(source_root),
        "full_span_runtime_context": False,
        "full_span_role": "compiler_input_source_ref_validation_only",
        "typed_artifact_schema": "rich_leaf_typed_artifact.v1",
    }
    return resolve


def arm_context(arm: str, *, kbv5_chunks: list[dict[str, Any]], rich: dict[str, Any] | None) -> dict[str, Any]:
    use_kbv5 = arm in {ARM_KBV5_ONLY, ARM_KBV5_PLUS_RUNTIME_SLIM, ARM_KBV5_PLUS_TYPED_RUNTIME_SLIM}
    use_runtime_slim = arm in {ARM_KBV5_PLUS_RUNTIME_SLIM, ARM_RUNTIME_SLIM_ONLY}
    use_typed = arm in {ARM_TYPED_RUNTIME_SLIM_ONLY, ARM_KBV5_PLUS_TYPED_RUNTIME_SLIM}
    retrieved = (
        [
            {
                "chunk_id": chunk.get("chunk_id"),
                "doc_type": chunk.get("doc_type"),
                "content": _clip(chunk.get("content"), limit=CHUNK_CONTENT_CLIP),
            }
            for chunk in kbv5_chunks
        ]
        if use_kbv5
        else []
    )
    context: dict[str, Any] = {
        "mode": arm,
        "retrieval_channel": "kb_v5.search_chunks_v2" if use_kbv5 else "none",
        "retrieved_chunks": retrieved,
    }
    if use_runtime_slim:
        context["rich_leaf_grounding"] = (rich or {}).get("grounding") or ""
        context["rich_leaf_ids"] = (rich or {}).get("leaf_ids") or []
    if use_typed:
        context["typed_rich_leaf_artifact"] = (rich or {}).get("typed_artifact") or {}
        context["typed_leaf_ids"] = (rich or {}).get("leaf_ids") or []
    return context


# ---------------------------------------------------------------- prompts


def answer_messages(*, case: dict[str, Any], sub: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    payload = {
        "sub_question_id": sub.get("sub_id"),
        "background": _clip(case.get("background"), limit=BACKGROUND_PROMPT_CLIP),
        "sub_question": sub.get("text"),
        "context": context,
        "required_json": {
            "answer": "Chinese answer string for THIS sub-question only",
            "citations": "list of evidence ids actually used: chunk_id, rich:<leaf_id>, typed:<leaf_id>, source_refs, or 教材要点 Ln",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a Chinese construction-exam (一级建造师建筑实务) case-question (案例题) solver. "
                "Answer ONLY the given sub-question using the background, the provided context, and your "
                "own knowledge; prefer cited context evidence. Cover every asked point concisely (不妥之处+正确做法 / "
                "列举 / 计算 as required). `citations` must list ONLY evidence identifiers that actually appear "
                "in the context: retrieval chunk ids verbatim (e.g. 'CET_...'), 'rich:<leaf_id>' / "
                "'教材要点 Ln' for runtime-slim rich blocks, or 'typed:<leaf_id>' / source_refs from "
                "typed_rich_leaf_artifact; 如使用 typed artifact 请优先引用其 source_refs；empty list if none used. "
                "Return one JSON object only."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def judge_messages(
    *, case: dict[str, Any], sub: dict[str, Any], arm_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, str]], dict[str, str]]:
    mapping = {str(index + 1): str(row.get("arm")) for index, row in enumerate(arm_rows)}
    candidates = {str(index + 1): {"answer": row.get("answer")} for index, row in enumerate(arm_rows)}
    payload = {
        "sub_question_id": sub.get("sub_id"),
        "background_digest": _clip(case.get("background"), limit=JUDGE_BACKGROUND_CLIP),
        "sub_question": sub.get("text"),
        "gold_answer": sub.get("gold_answer"),
        "gold_analysis": _clip(sub.get("gold_analysis"), limit=400),
        "candidates": candidates,
        "required_json": {
            "scoring_points": "list of the gold answer's key scoring points (3-8 short Chinese strings)",
            "candidates": {
                key: {
                    "verdict": "correct | partial | wrong",
                    "point_hits": "list of booleans, SAME length and order as scoring_points",
                }
                for key in candidates
            },
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are an independent strict grader for Chinese construction-exam case sub-questions. "
                "First extract the gold answer's key scoring points (采分点) as a short ordered list. "
                "Then for EVERY candidate ordinal, judge: verdict (correct = covers gold; partial = covers "
                "some key points; wrong = contradicts or misses gold) and point_hits — a boolean per "
                "scoring point, true only when the candidate answer actually covers that point. "
                "point_hits MUST have exactly the same length and order as scoring_points. "
                "Cover EVERY candidate key. Return one JSON object only."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]
    return messages, mapping


def apply_case_judge(parsed: dict[str, Any], mapping: dict[str, str]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Validate the judge object. Non-full coverage degrades that arm to judge_failed (short-ordinal
    discipline: candidates keyed 1..n, scoring points aligned by array index)."""
    points = [str(p) for p in parsed.get("scoring_points") or [] if str(p).strip()]
    raw_candidates = parsed.get("candidates") if isinstance(parsed.get("candidates"), dict) else {}
    verdicts: dict[str, dict[str, Any]] = {}
    for ordinal, arm in mapping.items():
        entry = raw_candidates.get(ordinal) if isinstance(raw_candidates.get(ordinal), dict) else {}
        verdict = str(entry.get("verdict") or "").strip().lower()
        hits_raw = entry.get("point_hits")
        hits = [bool(h) for h in hits_raw] if isinstance(hits_raw, list) else []
        if verdict not in VALID_VERDICTS or not points or len(hits) != len(points):
            verdicts[arm] = {"judge_status": "judge_failed", "verdict": None, "point_hits": None, "point_coverage": None}
            continue
        verdicts[arm] = {
            "judge_status": "completed",
            "verdict": verdict,
            "point_hits": hits,
            "point_coverage": round(mean([1.0 if h else 0.0 for h in hits]), 4),
        }
    return points, verdicts


_FAILED_VERDICT = {"judge_status": "judge_failed", "verdict": None, "point_hits": None, "point_coverage": None}


def merge_dual_judgments(
    primary: dict[str, dict[str, Any]], swapped: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Merge two judge passes (second pass saw the candidates in swapped order) per arm.

    Both completed: verdict mismatch -> ``judge_disagreement`` True; ``verdict_score`` is the
    MEAN of the two verdict scores and ``point_coverage`` the mean of the two coverages (de-noised
    position-bias estimate); the primary-pass verdict is retained for correct/partial rate metrics.
    Exactly one completed: use it (``judge_disagreement`` None — nothing to compare).
    Neither: judge_failed."""
    merged: dict[str, dict[str, Any]] = {}
    for arm in {**primary, **swapped}:
        a = primary.get(arm) or dict(_FAILED_VERDICT)
        b = swapped.get(arm) or dict(_FAILED_VERDICT)
        a_ok = a.get("judge_status") == "completed"
        b_ok = b.get("judge_status") == "completed"
        if not a_ok and not b_ok:
            merged[arm] = {**_FAILED_VERDICT, "verdict_score": None, "judge_disagreement": None}
            continue
        if a_ok and b_ok:
            coverages = [float(v) for v in (a.get("point_coverage"), b.get("point_coverage")) if v is not None]
            merged[arm] = {
                "judge_status": "completed",
                "verdict": a.get("verdict"),
                "verdict_swapped": b.get("verdict"),
                "verdict_score": round(
                    (VERDICT_SCORE.get(str(a.get("verdict")), 0.0) + VERDICT_SCORE.get(str(b.get("verdict")), 0.0)) / 2, 4
                ),
                "point_hits": a.get("point_hits"),
                "point_coverage": round(mean(coverages), 4) if coverages else None,
                "judge_disagreement": str(a.get("verdict")) != str(b.get("verdict")),
            }
            continue
        survivor = a if a_ok else b
        merged[arm] = {
            **survivor,
            "verdict_score": VERDICT_SCORE.get(str(survivor.get("verdict")), 0.0),
            "judge_disagreement": None,
        }
    return merged


# ---------------------------------------------------------------- citations


_TEXTBOOK_POINT_LABEL_RE = re.compile(r"教材要点\s*L\s*(\d+)")
_FULL_SPAN_LABEL_RE = re.compile(r"全文证据\s*L\s*(\d+)")


def classify_citations(
    citations: list[str],
    *,
    chunk_ids: list[str],
    rich_leaf_ids: list[str],
    full_span_leaf_ids: list[str] | None = None,
    typed_leaf_ids: list[str] | None = None,
    typed_source_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Programmatic citation source split: retrieval chunk / rich block / typed artifact / full span / unknown.

    Rich-block citations are recognized either by leaf id ('rich:<leaf_id>') or by the citable
    block label 【教材要点 Ln】 (ordinal must resolve to an actually-rendered rich block). Full-span
    citations are recognized by 'full:<leaf_id>' or 【全文证据 Ln】. Typed citations are recognized
    by 'typed:<leaf_id>' or by source_refs exposed in typed_rich_leaf_artifact."""
    chunk_set = [c for c in (str(c).strip() for c in chunk_ids) if c]
    leaf_set = [leaf for leaf in (str(item).strip() for item in rich_leaf_ids) if leaf]
    full_leaf_set = [leaf for leaf in (str(item).strip() for item in (full_span_leaf_ids or [])) if leaf]
    typed_leaf_set = [leaf for leaf in (str(item).strip() for item in (typed_leaf_ids or [])) if leaf]
    typed_ref_set = [ref for ref in (str(item).strip() for item in (typed_source_refs or [])) if ref]
    counts = {"retrieval_chunk": 0, "rich_block": 0, "typed_artifact": 0, "full_span": 0, "unknown": 0}
    detailed: list[dict[str, str]] = []
    for raw in citations:
        cite = str(raw or "").strip()
        if not cite:
            continue
        label_match = _TEXTBOOK_POINT_LABEL_RE.search(cite)
        full_label_match = _FULL_SPAN_LABEL_RE.search(cite)
        if any(chunk and (chunk in cite or cite in chunk) for chunk in chunk_set):
            source = "retrieval_chunk"
        elif cite.startswith("typed:") and any(leaf and leaf in cite for leaf in typed_leaf_set):
            source = "typed_artifact"
        elif any(ref and (ref in cite or cite in ref) for ref in typed_ref_set):
            source = "typed_artifact"
        elif cite.startswith("full:") and any(leaf and leaf in cite for leaf in full_leaf_set):
            source = "full_span"
        elif full_label_match and 1 <= int(full_label_match.group(1)) <= len(full_leaf_set):
            source = "full_span"
        elif cite.startswith("rich:") and any(leaf and leaf in cite for leaf in leaf_set):
            source = "rich_block"
        elif any(leaf and leaf in cite for leaf in leaf_set):
            source = "rich_block"
        elif label_match and 1 <= int(label_match.group(1)) <= len(leaf_set):
            source = "rich_block"
        else:
            source = "unknown"
        counts[source] += 1
        detailed.append({"citation": cite[:120], "source": source})
    total = sum(counts.values())
    return {
        "counts": counts,
        "total": total,
        "grounded_rate": (
            round((counts["retrieval_chunk"] + counts["rich_block"] + counts["typed_artifact"] + counts["full_span"]) / total, 4)
            if total
            else None
        ),
        "detail": detailed[:10],
    }


# ---------------------------------------------------------------- scoring


def _row_verdict_score(row: dict[str, Any]) -> float:
    """Dual-judge rows carry a mean ``verdict_score``; single-judge rows derive it from verdict."""
    score = row.get("verdict_score")
    if score is not None:
        return float(score)
    return VERDICT_SCORE.get(str(row.get("verdict")), 0.0)


def arm_summary(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    judged = [row for row in completed if row.get("judge_status") == "completed"]
    coverages = [float(row["point_coverage"]) for row in judged if row.get("point_coverage") is not None]
    cited = [row for row in completed if (row.get("citation_audit") or {}).get("total")]
    grounded = [float((row["citation_audit"] or {}).get("grounded_rate") or 0.0) for row in cited]
    dual_compared = [row for row in judged if row.get("judge_disagreement") is not None]
    return {
        "arm": arm,
        "sub_question_count": len(rows),
        "completed_count": len(completed),
        "judged_count": len(judged),
        "fail_rate": round((len(rows) - len(completed)) / len(rows), 4) if rows else 0.0,
        "correct_rate": round(mean([1.0 if row.get("verdict") == "correct" else 0.0 for row in judged]), 4) if judged else 0.0,
        "partial_rate": round(mean([1.0 if row.get("verdict") == "partial" else 0.0 for row in judged]), 4) if judged else 0.0,
        "semantic_score": round(mean([_row_verdict_score(row) for row in judged]), 4) if judged else 0.0,
        "scoring_point_coverage": round(mean(coverages), 4) if coverages else 0.0,
        "judge_disagreement_rate": (
            round(mean([1.0 if row.get("judge_disagreement") else 0.0 for row in dual_compared]), 4)
            if dual_compared
            else None
        ),
        "citation_grounded_rate": round(mean(grounded), 4) if grounded else None,
        "citation_source_counts": {
            source: sum(int((row.get("citation_audit") or {}).get("counts", {}).get(source) or 0) for row in completed)
            for source in ("retrieval_chunk", "rich_block", "typed_artifact", "full_span", "unknown")
        },
        "rows_with_citations": len(cited),
        "mean_prompt_tokens": round(mean([int(row.get("prompt_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_completion_tokens": round(mean([int(row.get("completion_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_total_tokens": round(mean([int(row.get("total_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_latency_ms": round(mean([float(row.get("latency_ms") or 0.0) for row in completed]), 2) if completed else 0.0,
    }


def case_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_case: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_case[str(row.get("case_id"))][str(row.get("arm"))].append(row)
    summaries: list[dict[str, Any]] = []
    for case_id in sorted(by_case):
        entry: dict[str, Any] = {"case_id": case_id}
        for arm in PLANNED_ARMS:
            judged = [r for r in by_case[case_id].get(arm, []) if r.get("judge_status") == "completed"]
            coverages = [float(r["point_coverage"]) for r in judged if r.get("point_coverage") is not None]
            entry[arm] = {
                "judged_count": len(judged),
                "semantic_score": round(mean([_row_verdict_score(r) for r in judged]), 4) if judged else None,
                "scoring_point_coverage": round(mean(coverages), 4) if coverages else None,
            }
        summaries.append(entry)
    return summaries


def build_report(
    *,
    cases: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    judge_rows: list[dict[str, Any]],
    model: str,
    seed: int,
    provider_configured: bool,
    kbv5_status: dict[str, Any],
    dual_judge: bool = False,
    rich_supply: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if not provider_configured:
        blockers.append("provider_call_not_configured")
    if not cases:
        blockers.append("no_cases_sampled")
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_arm[str(row.get("arm"))].append(row)
    arms = [arm_summary(arm, by_arm.get(arm, [])) for arm in PLANNED_ARMS]
    prompt_tokens = sum(int(row.get("prompt_tokens") or 0) for row in rows + judge_rows)
    completion_tokens = sum(int(row.get("completion_tokens") or 0) for row in rows + judge_rows)
    runtime_exercised = bool(rows) and not blockers
    dual_compared = [row for row in rows if row.get("judge_disagreement") is not None]
    return {
        "dual_judge": {
            "enabled": dual_judge,
            "compared_count": len(dual_compared),
            "disagreed_count": sum(1 for row in dual_compared if row.get("judge_disagreement")),
            "disagreement_rate": (
                round(mean([1.0 if row.get("judge_disagreement") else 0.0 for row in dual_compared]), 4)
                if dual_compared
                else None
            ),
        },
        "schema": SCHEMA,
        "execution_authority": "authorized_live_case_question_eval" if runtime_exercised else "not_exercised",
        "runtime_exercised": runtime_exercised,
        "seed": seed,
        "models": [model] if runtime_exercised else [],
        "kbv5_retrieval": kbv5_status,
        "rich_supply": rich_supply,
        "case_sample": {
            "case_count": len(cases),
            "sub_question_count": sum(len(c["sub_questions"]) for c in cases),
            "years": sorted({c["year"] for c in cases}),
            "case_ids": [c["case_id"] for c in cases],
        },
        "provider_usage": {
            "answer_call_count": len([r for r in rows if r.get("status") == "completed"]),
            "judge_call_count": len([r for r in judge_rows if r.get("status") == "completed"]),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "arms": arms,
        "case_summaries": case_summaries(rows),
        "rows": rows,
        "judge_rows": judge_rows,
        "blockers": blockers,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "case_question_typed_artifact_ab": True,
            "fixed_arms": PLANNED_ARMS,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


# ---------------------------------------------------------------- live loop


def _resume_index(previous: dict[str, Any] | None) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    answer_rows: dict[tuple[str, str], dict[str, Any]] = {}
    judge_rows: dict[str, dict[str, Any]] = {}
    if isinstance(previous, dict):
        for row in previous.get("rows") or []:
            if isinstance(row, dict) and row.get("status") == "completed" and row.get("judge_status") == "completed":
                answer_rows[(str(row.get("sub_id")), str(row.get("arm")))] = row
        for row in previous.get("judge_rows") or []:
            if isinstance(row, dict) and row.get("status") == "completed" and row.get("pass") != "swapped":
                judge_rows[str(row.get("sub_id"))] = row
    return answer_rows, judge_rows


def run_eval(
    *,
    cases: list[dict[str, Any]],
    provider_call: ProviderCall | None,
    retriever: Callable[[str], dict[str, Any]] | None,
    rich_resolver: Callable[[str, str], dict[str, Any]] | None,
    model: str,
    seed: int,
    token_budget: int,
    dual_judge: bool = False,
    previous: dict[str, Any] | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    rich_supply = getattr(rich_resolver, "supply_info", None)
    resumed_answers, resumed_judges = _resume_index(previous)
    rows: list[dict[str, Any]] = []
    judge_rows: list[dict[str, Any]] = []
    kbv5_status: dict[str, Any] = {
        "channel": "kb_v5.search_chunks_v2",
        "degraded": False,
        "unavailable_count": 0,
        "config": getattr(retriever, "config", None),
    }
    spent_tokens = 0
    budget_stop = False

    def _checkpoint() -> dict[str, Any]:
        report = build_report(
            cases=cases,
            rows=rows,
            judge_rows=judge_rows,
            model=model,
            seed=seed,
            provider_configured=provider_call is not None,
            kbv5_status=kbv5_status,
            dual_judge=dual_judge,
            rich_supply=rich_supply,
        )
        if output_path is not None:
            _write_json(output_path, report)
        return report

    if provider_call is None:
        return _checkpoint()

    for case in cases:
        if budget_stop:
            break
        for sub in case["sub_questions"]:
            sub_id = str(sub["sub_id"])
            resumed = [resumed_answers.get((sub_id, arm)) for arm in PLANNED_ARMS]
            if all(resumed) and sub_id in resumed_judges:
                rows.extend(resumed)  # type: ignore[arg-type]
                judge_rows.append(resumed_judges[sub_id])
                continue
            if spent_tokens > token_budget:
                kbv5_status["budget_exhausted_at"] = sub_id
                budget_stop = True
                break

            query = f"{case['background']}\n{sub['text']}"
            retrieval = retriever(query) if retriever else {"status": "skipped", "chunks": [], "latency_ms": 0.0}
            if retrieval["status"] != "completed":
                kbv5_status["unavailable_count"] = int(kbv5_status.get("unavailable_count") or 0) + 1
                kbv5_status["degraded"] = True
            # two-layer rich query: sub-question text = focus layer, case background = background layer
            rich = rich_resolver(str(case["background"]), str(sub["text"])) if rich_resolver else None

            sub_rows: list[dict[str, Any]] = []
            for arm in PLANNED_ARMS:
                context = arm_context(arm, kbv5_chunks=retrieval["chunks"], rich=rich)
                chunk_ids = [str(chunk.get("chunk_id") or "") for chunk in retrieval["chunks"]]
                rich_ids = context.get("rich_leaf_ids") or []
                typed_ids = context.get("typed_leaf_ids") or []
                typed_artifact = context.get("typed_rich_leaf_artifact") if isinstance(context.get("typed_rich_leaf_artifact"), dict) else {}
                typed_source_refs = [str(ref) for ref in (typed_artifact.get("source_refs") or []) if str(ref).strip()]
                row: dict[str, Any] = {
                    "arm": arm,
                    "case_id": case["case_id"],
                    "sub_id": sub_id,
                    "sub_no": sub.get("sub_no"),
                    "year": case["year"],
                    "node_code": sub.get("node_code"),
                    "rich_leaf_ids": rich_ids if rich_ids else None,
                    "typed_leaf_ids": typed_ids if typed_ids else None,
                    "typed_artifact_schema": typed_artifact.get("artifact_schema") if typed_artifact else None,
                    "typed_source_ref_count": len(typed_source_refs) if typed_source_refs else None,
                    "rich_primary_leaf": (rich or {}).get("primary_leaf") if (rich_ids or typed_ids) else None,
                    "full_span_resolution": (rich or {}).get("full_span_resolution") if typed_ids else None,
                    "retrieval_status": retrieval["status"],
                    "retrieval_latency_ms": retrieval["latency_ms"] if context.get("retrieved_chunks") else None,
                }
                try:
                    response = provider_call(answer_messages(case=case, sub=sub, context=context), max_tokens=800)
                    parsed = _parse_json_object(str(response.get("content") or ""))
                    answer = str(parsed.get("answer") or "").strip()
                    citations = [str(item) for item in parsed.get("citations") or []][:10]
                    row.update(
                        {
                            "status": "completed",
                            "answer": answer[:1500],
                            "citations": citations,
                            "citation_audit": classify_citations(
                                citations,
                                chunk_ids=chunk_ids if context.get("retrieved_chunks") else [],
                                rich_leaf_ids=list(rich_ids),
                                full_span_leaf_ids=[],
                                typed_leaf_ids=list(typed_ids),
                                typed_source_refs=typed_source_refs,
                            ),
                            "prompt_tokens": int(response.get("prompt_tokens") or 0),
                            "completion_tokens": int(response.get("completion_tokens") or 0),
                            "total_tokens": int(response.get("prompt_tokens") or 0) + int(response.get("completion_tokens") or 0),
                            "latency_ms": float(response.get("latency_ms") or 0.0),
                        }
                    )
                except Exception as exc:  # pragma: no cover - live failure path
                    row.update(
                        {
                            "status": "failed",
                            "error": str(exc)[:240],
                            "answer": "",
                            "citations": [],
                            "citation_audit": None,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "latency_ms": 0.0,
                        }
                    )
                spent_tokens += int(row.get("total_tokens") or 0)
                sub_rows.append(row)

            completed_rows = [row for row in sub_rows if row.get("status") == "completed"]
            verdicts: dict[str, dict[str, Any]] = {}
            sub_judge_rows: list[dict[str, Any]] = []

            def _judge_pass(arm_rows: list[dict[str, Any]], pass_name: str) -> dict[str, dict[str, Any]]:
                nonlocal spent_tokens
                messages, mapping = judge_messages(case=case, sub=sub, arm_rows=arm_rows)
                try:
                    response = provider_call(messages, max_tokens=900)
                    pass_points, pass_verdicts = apply_case_judge(
                        _parse_json_object(str(response.get("content") or "")), mapping
                    )
                    sub_judge_rows.append(
                        {
                            "sub_id": sub_id,
                            "case_id": case["case_id"],
                            "status": "completed",
                            "pass": pass_name,
                            "mapping": mapping,
                            "scoring_points": pass_points,
                            "prompt_tokens": int(response.get("prompt_tokens") or 0),
                            "completion_tokens": int(response.get("completion_tokens") or 0),
                            "latency_ms": float(response.get("latency_ms") or 0.0),
                        }
                    )
                    spent_tokens += int(response.get("prompt_tokens") or 0) + int(response.get("completion_tokens") or 0)
                    return pass_verdicts
                except Exception as exc:  # pragma: no cover - live failure path
                    sub_judge_rows.append(
                        {
                            "sub_id": sub_id,
                            "case_id": case["case_id"],
                            "status": "failed",
                            "pass": pass_name,
                            "error": str(exc)[:240],
                        }
                    )
                    return {}

            if completed_rows:
                verdicts = _judge_pass(completed_rows, "primary")
                if dual_judge:
                    # second judge pass with the two arms' positions swapped (position-bias de-noise)
                    swapped_verdicts = _judge_pass(list(reversed(completed_rows)), "swapped")
                    verdicts = merge_dual_judgments(verdicts, swapped_verdicts)
            else:
                sub_judge_rows.append({"sub_id": sub_id, "case_id": case["case_id"], "status": "skipped"})
            for row in sub_rows:
                verdict = verdicts.get(str(row["arm"]))
                if verdict is None:
                    row.update({"judge_status": "judge_failed", "verdict": None, "point_hits": None, "point_coverage": None})
                else:
                    row.update(verdict)
            rows.extend(sub_rows)
            judge_rows.extend(sub_judge_rows)
            _checkpoint()

    return _checkpoint()


# ---------------------------------------------------------------- entrypoint


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-dir", type=Path, default=DEFAULT_EXAM_DIR)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "case_question_typed_ab_results.json")
    parser.add_argument("--seed", type=int, default=20260613)
    parser.add_argument("--case-count", type=int, default=13)
    parser.add_argument("--kbv5-top-k", type=int, default=3)
    parser.add_argument(
        "--kbv5-doc-types",
        default=",".join(DEFAULT_KBV5_DOC_TYPES),
        help="comma-separated kb_v5 doc_types for the clean RAG baseline; default excludes exam",
    )
    parser.add_argument("--token-budget", type=int, default=250_000)
    parser.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--no-provider-call", action="store_true")
    parser.add_argument("--resume-from", type=Path, default=None)
    parser.add_argument(
        "--rich-pack",
        type=Path,
        default=None,
        help="frozen runtime token pack file to use as the D-arm rich supply instead of the "
        "tracked runtime_supply bundle (temporary in-process supply; quarantine excluded)",
    )
    parser.add_argument(
        "--rich-grading-render",
        action="store_true",
        help="render runtime-slim rich blocks with grading=True (scoring_points family first)",
    )
    parser.add_argument("--full-span-max-chars", type=int, default=FULL_SPAN_RENDER_MAX_CHARS, help=argparse.SUPPRESS)
    parser.add_argument(
        "--dual-judge",
        action="store_true",
        help="judge every sub-question twice (second pass reverses arm positions); "
        "disagreements take the mean score and are flagged judge_disagreement",
    )
    args = parser.parse_args(argv)

    model = args.model or PROVIDER_DEFAULTS[args.provider]["model"]
    provider_call = None if args.no_provider_call else _openai_compat_provider(provider=args.provider, model=model, timeout_s=args.timeout_s)
    kbv5_doc_types = _parse_doc_types(args.kbv5_doc_types)
    cases = sample_cases(load_case_bank(args.exam_dir, DEFAULT_EXAM_YEARS), seed=args.seed, count=args.case_count)
    previous = _read_json(args.resume_from) if args.resume_from and args.resume_from.exists() else None
    report = run_eval(
        cases=cases,
        provider_call=provider_call,
        retriever=_kbv5_retriever(args.kbv5_top_k, doc_types=kbv5_doc_types) if provider_call is not None else None,
        rich_resolver=(
            _rich_resolver(
                pack_path=args.rich_pack,
                grading=args.rich_grading_render,
                source_root=args.source_root,
                full_span_max_chars=args.full_span_max_chars,
            )
            if provider_call is not None
            else None
        ),
        model=model,
        seed=args.seed,
        token_budget=args.token_budget,
        dual_judge=args.dual_judge,
        previous=previous,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "runtime_exercised": report["runtime_exercised"],
                "provider_usage": report["provider_usage"],
                "dual_judge": report["dual_judge"],
                "arms": [
                    {
                        k: arm[k]
                        for k in (
                            "arm",
                            "sub_question_count",
                            "fail_rate",
                            "semantic_score",
                            "scoring_point_coverage",
                            "judge_disagreement_rate",
                            "citation_grounded_rate",
                            "mean_total_tokens",
                        )
                    }
                    for arm in report["arms"]
                ],
                "blockers": report["blockers"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["runtime_exercised"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
