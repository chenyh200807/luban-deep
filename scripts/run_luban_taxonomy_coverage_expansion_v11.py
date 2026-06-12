#!/usr/bin/env python3
"""Coverage-expansion candidates + apply for taxonomy-frozen-v1.1 (first weekly window).

The frozen v1 real-world eval (rich_leaf_frozen_v1_real_world_eval_20260613) showed the
v3.0.1 pack covers 43 node prefixes while 2021-2025 real exam questions are tagged over
77 node prefixes. This tool implements the TAXONOMY_FREEZE.md change policy
(candidate -> review -> batch migration):

``derive``
    Programmatically re-derives the gap prefix list (exam taxonomy.node_code set minus
    pack leaf prefixes), groups exam concepts per gap prefix, searches evidence with
    lane priority textbook > lecture > standard (bigram overlap vs the exam chunks'
    knowledge text), proposes a canonical placement parent, runs strict-path-term and
    duplicate-leaf checks, and writes a reviewable candidates JSON. Read-only.

``apply``
    After review, backs up the canonical taxonomy (aborts if the backup already
    exists), mints ``{anchor}-E{NN}`` expansion leaves with full keywords +
    source_evidence, bumps ``meta.frozen`` to the new freeze tag, records unfilled
    work orders in meta, validates zero duplicate codes, and rewrites canonical.

Semantics note (honest finding): exam node codes are NOT the canonical code axis.
Several gap prefixes exist in canonical with different meanings (e.g. exam 1A412011 =
建筑物分类 in 2021 vs canonical 1A412011 = 建筑钢材). Expansion leaves therefore carry the
EXAM concept (that is the runtime demand signal) and are placed under the canonical
parent that semantically matches the evidence, even when that parent's code differs
from the leaf prefix. Placement is recorded per candidate for review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCHEMA = "luban_taxonomy_coverage_expansion.v1"
REVISION = "coverage_expansion_20260613"
NEW_FROZEN_TAG = "taxonomy-frozen-v1.1-20260613"
EXPECTED_OLD_FROZEN_TAG = "taxonomy-frozen-v1-20260612"

SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_TAXONOMY = SOURCE_ROOT / "taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
DEFAULT_BACKUP = SOURCE_ROOT / "taxonomy/FINAL_CLEANED_TAXONOMY2026_pre_coverage_expansion_backup_20260613.json"
DEFAULT_EXAM_DIR = SOURCE_ROOT / "题库"
DEFAULT_BOOK_FILES = [
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-9-166v3_fixed.json",
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-167-221v3_fixed.json",
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-222-382_fixed.json",
]
LECTURE_DIR = SOURCE_ROOT / "讲义"
STANDARD_DIR = SOURCE_ROOT / "标准文件"
DEFAULT_PACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_full_compile_20260613/runtime_token_pack_v301_quarantine_annotated.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v11_coverage_expansion_20260613"
EXAM_YEARS = (2021, 2022, 2023, 2024, 2025)

# evidence acceptance thresholds (bigram intersection with the prefix's exam knowledge text)
MIN_LANE_SCORE = {"textbook": 12.0, "lecture": 12.0, "standard": 12.0}
NAME_HIT_BONUS = 10.0

STRICT_PATH_TERMS = ("分部工程", "防火分区", "耐火等级", "网络计划", "双代号", "总时差")

# generic construction-domain words whose bigrams carry no placement signal
_GENERIC_WORDS = ("建筑", "施工", "工程", "设计", "管理", "结构", "材料", "技术", "要求", "质量", "规定", "构造")

_CJK = re.compile(r"[一-鿿]")

# Reviewed evidence overrides (2026-06-13 review pass): cases where the bigram scorer
# picked a topically wrong chunk and the correct source was located by hand.
# key = (gap node_code, merged concept name) -> evidence spec or {"unfilled": reason}.
REVIEW_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("1A431020", "基坑支护——地下连续墙"): {"lane": "textbook", "chunk_id": "1A422000_032_0054"},
    ("1A413003", "装配式装饰装修模块化设计"): {"lane": "textbook", "chunk_id": "1A411011_037_0065"},
    ("1A434001", "装修工程——涂饰"): {"lane": "textbook", "chunk_id": "1A412010_060_0118"},
    ("1A414020", "建筑装饰装修材料"): {"lane": "textbook", "chunk_id": "1A412010_055_0110"},
    ("1A432012", "建筑材料分类和分级"): {"lane": "lecture", "chunk_id": "LEC_1A413060_P0035_001"},
    # 2021 风险应对措施（规避/减轻/转移/自留）：教材/讲义/标准三个语料都没有该知识实体
    ("1A432051", "建设工程项目管理"): {
        "unfilled": "risk_response_measures_absent_from_all_three_corpora"
    },
}


# ---------------------------------------------------------------- generic helpers


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bigrams(text: str) -> set[str]:
    chars = [ch for ch in text if _CJK.match(ch)]
    return {a + b for a, b in zip(chars, chars[1:])}


def clean_concept_name(node_name: str) -> str:
    """Normalize an exam node_name into a leaf name (keep the full qualified name)."""
    name = unicodedata.normalize("NFKC", str(node_name or "")).strip()
    name = re.sub(r"\s+", "", name)
    return name


def merge_key(name: str) -> str:
    """Concepts whose names differ only by a 规定-style suffix are the same concept."""
    return re.sub(r"(的有关规定|有关规定|的相关规定|相关规定|的规定)$", "", name)


_GENERIC_GRAMS: set[str] = set()
for _word in _GENERIC_WORDS:
    _GENERIC_GRAMS |= {a + b for a, b in zip(_word, _word[1:])}


def signal_bigrams(text: str) -> set[str]:
    return bigrams(text) - _GENERIC_GRAMS


def strict_term_hits(name: str) -> list[str]:
    return [term for term in STRICT_PATH_TERMS if term in name]


def refine_keywords(concept: dict[str, Any], evidence_text: str) -> list[str]:
    """Build leaf keywords that are both exam-derived and verbatim-anchored in the evidence.

    Candidates: exam key_parameter names, concept-name segments, and evidence heading
    segments. Terms verbatim present in the evidence text come first so the downstream
    semantic audit's keyword-overlap check measures true leaf<->context alignment.
    """
    segments: list[str] = []
    for raw in [concept["name"], *concept["keywords"]]:
        segments.extend(s for s in re.split(r"[^一-鿿]+", str(raw)) if len(s) >= 2)
    for line in evidence_text.splitlines():
        if line.lstrip().startswith("#"):
            segments.extend(s for s in re.split(r"[^一-鿿]+", line) if len(s) >= 2)
    seen: set[str] = set()
    present: list[str] = []
    absent: list[str] = []
    for segment in segments:
        if segment in seen:
            continue
        seen.add(segment)
        (present if segment in evidence_text else absent).append(segment)
    keywords = present[:6] + absent[: max(0, 8 - min(len(present), 6))]
    return keywords[:8]


# ---------------------------------------------------------------- exam side


def load_exam_concepts(exam_dir: Path, years: tuple[int, ...] = EXAM_YEARS) -> dict[str, list[dict[str, Any]]]:
    """Group exam chunks by node_code, one concept per distinct cleaned node_name."""
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for year in years:
        path = exam_dir / f"{year}年一级建造师《建筑实务》考试真题及答案解析" / f"FINAL_CLEANED_EXAM_V{year}.json"
        if not path.exists():
            continue
        for chunk in _read_json(path).get("chunks") or []:
            if not isinstance(chunk, dict):
                continue
            taxonomy = chunk.get("taxonomy") or {}
            code = str(taxonomy.get("node_code") or "")
            name = clean_concept_name(str(taxonomy.get("node_name") or ""))
            if not code or not name:
                continue
            text_parts = [str(chunk.get("content_markdown") or "")]
            layers = chunk.get("_layers") if isinstance(chunk.get("_layers"), dict) else {}
            index = layers.get("index") if isinstance(layers.get("index"), dict) else {}
            text_parts.append(str(index.get("rag_content") or ""))
            keywords: list[str] = []
            for param in chunk.get("key_parameters") or []:
                if isinstance(param, dict) and param.get("param_name"):
                    keywords.append(str(param["param_name"]))
            question_count = 0
            for exercise in chunk.get("exercises") or []:
                data = exercise.get("question_data") if isinstance(exercise.get("question_data"), dict) else {}
                if str(data.get("stem") or "").strip() and str(data.get("correct_answer") or "").strip():
                    question_count += 1
            concept = grouped[code].setdefault(
                merge_key(name),
                {"node_code": code, "name": merge_key(name), "exam_text": [], "keywords": [], "years": set(), "question_count": 0},
            )
            concept["exam_text"].extend(text_parts)
            concept["keywords"].extend(keywords)
            concept["years"].add(year)
            concept["question_count"] += question_count
    result: dict[str, list[dict[str, Any]]] = {}
    for code, by_name in grouped.items():
        concepts = []
        for concept in by_name.values():
            seen: set[str] = set()
            keywords = [k for k in concept["keywords"] if not (k in seen or seen.add(k))][:8]
            concepts.append(
                {
                    "node_code": code,
                    "name": concept["name"],
                    "exam_text": "\n".join(concept["exam_text"]),
                    "keywords": keywords,
                    "years": sorted(concept["years"]),
                    "question_count": concept["question_count"],
                }
            )
        result[code] = sorted(concepts, key=lambda c: c["name"])
    return result


def derive_gap_prefixes(exam_codes: set[str], pack: dict[str, Any]) -> tuple[list[str], list[str]]:
    pack_prefixes = {
        str(unit.get("leaf_id") or "").split("-")[0]
        for unit in pack.get("runtime_token_pack_units") or []
        if isinstance(unit, dict)
    }
    pack_prefixes.discard("")
    gap = sorted(exam_codes - pack_prefixes)
    return gap, sorted(pack_prefixes)


# ---------------------------------------------------------------- corpora


def load_book_corpus(book_files: list[Path]) -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = []
    for path in book_files:
        payload = _read_json(path)
        for block in payload.get("content_blocks") or []:
            if not isinstance(block, dict) or not block.get("chunk_id"):
                continue
            text = str(block.get("content_markdown") or "")
            corpus.append(
                {
                    "lane": "textbook",
                    "chunk_id": str(block["chunk_id"]),
                    "source_file": path.name,
                    "page_num": (block.get("source_meta") or {}).get("page_num"),
                    "text": text,
                    "grams": bigrams(text),
                }
            )
    return corpus


def load_lecture_corpus(lecture_dir: Path) -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = []
    if not lecture_dir.is_dir():
        return corpus
    for page_file in sorted(lecture_dir.glob("*/page_*.json")):
        try:
            payload = _read_json(page_file)
        except (OSError, ValueError):
            continue
        blocks = payload if isinstance(payload, list) else payload.get("content_blocks") or []
        for block in blocks:
            if not isinstance(block, dict) or not block.get("chunk_id"):
                continue
            text = str(block.get("content_markdown") or "")
            corpus.append(
                {
                    "lane": "lecture",
                    "chunk_id": str(block["chunk_id"]),
                    "source_file": f"讲义/{page_file.parent.name}/{page_file.name}",
                    "page_num": (block.get("source_meta") or {}).get("page_num"),
                    "text": text,
                    "grams": bigrams(text),
                }
            )
    return corpus


def load_standard_corpus(standard_dir: Path) -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = []
    if not standard_dir.is_dir():
        return corpus
    for path in sorted(standard_dir.glob("*.json")):
        try:
            payload = _read_json(path)
        except (OSError, ValueError):
            continue
        seen: set[str] = set()
        for key in ("content_blocks", "nodes"):
            for block in payload.get(key) or []:
                if not isinstance(block, dict):
                    continue
                context = block.get("source_context") or {}
                text = str(context.get("origin_text") or "").strip()
                if len(text) < 6:
                    continue
                block_id = str(block.get("chunk_id") or block.get("id") or "")
                article = str(context.get("article_id") or "")
                dedup = f"{article}|{hashlib.sha256(text.encode()).hexdigest()[:12]}"
                if not block_id or dedup in seen:
                    continue
                seen.add(dedup)
                corpus.append(
                    {
                        "lane": "standard",
                        "chunk_id": block_id,
                        "source_file": f"标准文件/{path.name}",
                        "page_num": context.get("page"),
                        "standard_code": str(context.get("standard_code") or ""),
                        "article_id": article,
                        "text": text,
                        "grams": bigrams(text),
                    }
                )
    return corpus


# ---------------------------------------------------------------- evidence search


def best_evidence(
    concept: dict[str, Any],
    corpora: dict[str, list[dict[str, Any]]],
    *,
    min_lane_score: dict[str, float] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Pick evidence with lane priority textbook > lecture > standard.

    Score = |exam-text bigrams ∩ chunk bigrams| + 3*|concept-name bigrams ∩ chunk bigrams|
    + 2*keyword hits + name-hit bonus. A lane is accepted when its best score clears the
    lane threshold AND is not dwarfed by a lower-priority lane (>= 0.5 * overall best),
    so a much stronger lecture/standard hit can outrank a weak textbook hit.
    """
    thresholds = min_lane_score or MIN_LANE_SCORE
    exam_grams = bigrams(concept["exam_text"])
    short_name = concept["name"].split("——")[-1]
    name_grams = signal_bigrams(concept["name"]) | signal_bigrams(short_name)

    def _score(item: dict[str, Any]) -> float:
        score = float(len(exam_grams & item["grams"]))
        score += 3.0 * len(name_grams & item["grams"])
        score += 2.0 * sum(1.0 for kw in concept["keywords"] if kw and kw in item["text"])
        if short_name and short_name in item["text"]:
            score += NAME_HIT_BONUS
        return score

    lane_best: dict[str, Any] = {}
    best_by_lane: dict[str, dict[str, Any] | None] = {}
    for lane in ("textbook", "lecture", "standard"):
        best, best_score = None, 0.0
        for item in corpora.get(lane) or []:
            score = _score(item)
            if score > best_score:
                best, best_score = item, score
        best_by_lane[lane] = best
        lane_best[lane] = {"score": best_score, "chunk_id": best["chunk_id"] if best else None}
    overall_best = max(entry["score"] for entry in lane_best.values()) if lane_best else 0.0
    for lane in ("textbook", "lecture", "standard"):
        best = best_by_lane[lane]
        score = lane_best[lane]["score"]
        if best is not None and score >= thresholds[lane] and score >= 0.5 * overall_best:
            chosen = {k: v for k, v in best.items() if k not in ("grams", "text")}
            chosen["score"] = score
            chosen["name_in_evidence"] = bool(short_name and short_name in best["text"])
            chosen["excerpt"] = best["text"][:120].replace("\n", " ")
            return chosen, lane_best
    return None, lane_best


# ---------------------------------------------------------------- canonical side


def index_canonical(taxonomy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """code -> {node, parent_code, is_leaf, name_path}."""
    index: dict[str, dict[str, Any]] = {}

    def walk(node: dict[str, Any], parent: str | None, names: list[str]) -> None:
        code = str(node.get("code") or "")
        name = str(node.get("name") or "")
        path = names + ([name] if name else [])
        children = [c for c in node.get("children") or [] if isinstance(c, dict)]
        if code:
            index[code] = {
                "node": node,
                "parent_code": parent,
                "is_leaf": not children,
                "name": name,
                "name_path": " > ".join(path),
            }
        for child in children:
            walk(child, code or parent, path)

    for root in taxonomy.get("outline_structure") or []:
        if isinstance(root, dict):
            walk(root, None, [])
    return index


def propose_placement(
    concept: dict[str, Any],
    evidence: dict[str, Any] | None,
    canonical_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Choose the canonical parent node for the new expansion leaf."""
    code = concept["node_code"]
    entry = canonical_index.get(code)
    short_name = concept["name"].split("——")[-1]
    # 1) same-code skeleton node whose name semantically matches the exam concept
    # (generic bigrams like 施工/工程 are excluded — they caused false same-code matches)
    if entry is not None and not entry["is_leaf"]:
        overlap = signal_bigrams(entry["name"]) & (signal_bigrams(concept["name"]) | signal_bigrams(short_name))
        if overlap or entry["name"] == concept["name"] or short_name == entry["name"]:
            return {"parent_code": code, "parent_name": entry["name"], "method": "same_code_name_match"}
    # 2) textbook evidence: place next to the evidence chunk's anchor family
    if evidence is not None and evidence.get("lane") == "textbook":
        family = str(evidence["chunk_id"]).split("_")[0]
        family_entry = canonical_index.get(family)
        if family_entry is not None and not family_entry["is_leaf"]:
            return {"parent_code": family, "parent_name": family_entry["name"], "method": "evidence_chunk_family"}
    # 3) best name-overlap internal node
    best_code, best_name, best_score = None, None, 0.0
    concept_grams = bigrams(concept["name"]) | bigrams(short_name) | bigrams(concept["exam_text"][:300])
    for cand_code, cand in canonical_index.items():
        if cand["is_leaf"] or not cand["name"]:
            continue
        score = float(len(concept_grams & bigrams(cand["name"])))
        if score > best_score:
            best_code, best_name, best_score = cand_code, cand["name"], score
    if best_code is not None and best_score >= 2:
        return {"parent_code": best_code, "parent_name": best_name, "method": "best_name_overlap"}
    # 4) same-code skeleton even without name match (last structural resort)
    if entry is not None and not entry["is_leaf"]:
        return {"parent_code": code, "parent_name": entry["name"], "method": "same_code_no_name_match"}
    return {"parent_code": None, "parent_name": None, "method": "unplaced"}


def duplicate_leaf_check(concept: dict[str, Any], canonical_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    short_name = concept["name"].split("——")[-1]
    grams = bigrams(concept["name"]) | bigrams(short_name)
    best_code, best_name, best = None, None, 0.0
    for code, entry in canonical_index.items():
        if not entry["is_leaf"] or not entry["name"]:
            continue
        leaf_grams = bigrams(entry["name"])
        if not leaf_grams:
            continue
        overlap = len(grams & leaf_grams) / len(leaf_grams)
        if overlap > best:
            best_code, best_name, best = code, entry["name"], overlap
    return {"closest_leaf_code": best_code, "closest_leaf_name": best_name, "overlap": round(best, 3)}


# ---------------------------------------------------------------- derive


def build_candidates(
    *,
    taxonomy: dict[str, Any],
    pack: dict[str, Any],
    exam_dir: Path,
    book_files: list[Path],
    lecture_dir: Path,
    standard_dir: Path,
) -> dict[str, Any]:
    exam_concepts = load_exam_concepts(exam_dir)
    gap_prefixes, pack_prefixes = derive_gap_prefixes(set(exam_concepts), pack)
    canonical_index = index_canonical(taxonomy)
    corpora = {
        "textbook": load_book_corpus(book_files),
        "lecture": load_lecture_corpus(lecture_dir),
        "standard": load_standard_corpus(standard_dir),
    }

    corpus_by_id = {
        (item["lane"], item["chunk_id"]): item for lane_items in corpora.values() for item in lane_items
    }

    candidates: list[dict[str, Any]] = []
    unfilled: list[dict[str, Any]] = []
    counters: dict[str, int] = defaultdict(int)
    for prefix in gap_prefixes:
        for concept in exam_concepts[prefix]:
            override = REVIEW_OVERRIDES.get((prefix, concept["name"]))
            if override and override.get("unfilled"):
                unfilled.append(
                    {
                        "node_code": prefix,
                        "name": concept["name"],
                        "years": concept["years"],
                        "question_count": concept["question_count"],
                        "lane_scores": {},
                        "reason": str(override["unfilled"]),
                    }
                )
                continue
            if override:
                item = corpus_by_id[(str(override["lane"]), str(override["chunk_id"]))]
                short_name = concept["name"].split("——")[-1]
                evidence = {k: v for k, v in item.items() if k not in ("grams", "text")}
                evidence["score"] = None
                evidence["name_in_evidence"] = bool(short_name and short_name in item["text"])
                evidence["excerpt"] = item["text"][:120].replace("\n", " ")
                evidence["review_override"] = True
                lane_scores = {"review_override": True}
            else:
                evidence, lane_scores = best_evidence(concept, corpora)
            if evidence is None:
                unfilled.append(
                    {
                        "node_code": prefix,
                        "name": concept["name"],
                        "years": concept["years"],
                        "question_count": concept["question_count"],
                        "lane_scores": lane_scores,
                        "reason": "no_lane_cleared_threshold",
                    }
                )
                continue
            counters[prefix] += 1
            leaf_code = f"{prefix}-E{counters[prefix]:02d}"
            placement = propose_placement(concept, evidence, canonical_index)
            evidence_text = corpus_by_id[(str(evidence["lane"]), str(evidence["chunk_id"]))]["text"]
            candidates.append(
                {
                    "leaf_code": leaf_code,
                    "node_code": prefix,
                    "name": concept["name"],
                    "keywords": refine_keywords(concept, evidence_text),
                    "years": concept["years"],
                    "question_count": concept["question_count"],
                    "lane": evidence["lane"],
                    "evidence": evidence,
                    "lane_scores": lane_scores,
                    "placement": placement,
                    "strict_term_hits": strict_term_hits(concept["name"]),
                    "duplicate_check": duplicate_leaf_check(concept, canonical_index),
                }
            )
    return {
        "schema": SCHEMA,
        "revision": REVISION,
        "classification": {"candidate_only": True, "review_only": True, "canonical_written": False},
        "gap_prefixes": gap_prefixes,
        "pack_prefix_count": len(pack_prefixes),
        "exam_prefix_count": len(exam_concepts),
        "candidates": candidates,
        "unfilled": unfilled,
        "summary": {
            "gap_prefix_count": len(gap_prefixes),
            "candidate_count": len(candidates),
            "unfilled_count": len(unfilled),
            "lane_counts": {
                lane: sum(1 for c in candidates if c["lane"] == lane) for lane in ("textbook", "lecture", "standard")
            },
            "strict_term_flagged": sum(1 for c in candidates if c["strict_term_hits"]),
            "covered_gap_prefixes": len({c["node_code"] for c in candidates}),
        },
    }


# ---------------------------------------------------------------- apply


def mint_leaf(candidate: dict[str, Any], parent_entry: dict[str, Any]) -> dict[str, Any]:
    evidence = candidate["evidence"]
    record: dict[str, Any] = {
        "chunk_id": evidence["chunk_id"],
        "page_num": evidence.get("page_num"),
        "source_file": evidence["source_file"],
    }
    lane = evidence["lane"]
    if lane != "textbook":
        record["source_lane"] = lane
    if lane == "standard":
        record["standard_code"] = evidence.get("standard_code")
        record["article_id"] = evidence.get("article_id")
    parent_node = parent_entry["node"]
    level = int(parent_node.get("level") or 0) + 1 if parent_node.get("level") is not None else None
    leaf: dict[str, Any] = {
        "children": [],
        "code": candidate["leaf_code"],
        "name": candidate["name"],
        "parent_code": str(parent_node.get("code") or ""),
        "keywords": candidate["keywords"],
        "source_evidence": [record],
        "source_lane": lane if lane != "textbook" else "textbook",
        "gap_fill": {
            "revision": REVISION,
            "gap_item": f"real_world_eval_coverage:{candidate['node_code']}",
            "exam_years": candidate["years"],
        },
    }
    if level is not None:
        leaf["level"] = level
    return leaf


def validate_tree(taxonomy: dict[str, Any]) -> dict[str, Any]:
    codes: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        code = str(node.get("code") or "")
        if code:
            codes.append(code)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    for root in taxonomy.get("outline_structure") or []:
        if isinstance(root, dict):
            walk(root)
    duplicates = sorted({c for c in codes if codes.count(c) > 1}) if len(codes) != len(set(codes)) else []
    return {"total_codes": len(codes), "unique_codes": len(set(codes)), "duplicates": duplicates}


def apply_candidates(
    *,
    taxonomy: dict[str, Any],
    candidates_payload: dict[str, Any],
) -> dict[str, Any]:
    canonical_index = index_canonical(taxonomy)
    minted: list[str] = []
    errors: list[str] = []
    for candidate in candidates_payload.get("candidates") or []:
        parent_code = (candidate.get("placement") or {}).get("parent_code")
        entry = canonical_index.get(str(parent_code or ""))
        if entry is None or entry["is_leaf"]:
            errors.append(f"{candidate['leaf_code']}: parent {parent_code!r} missing or is a leaf")
            continue
        if candidate["leaf_code"] in canonical_index:
            errors.append(f"{candidate['leaf_code']}: code already exists in canonical")
            continue
        leaf = mint_leaf(candidate, entry)
        entry["node"].setdefault("children", []).append(leaf)
        minted.append(candidate["leaf_code"])
    if errors:
        return {"minted": minted, "errors": errors, "validation": None}

    meta = taxonomy.setdefault("meta", {})
    meta["frozen"] = NEW_FROZEN_TAG
    meta["coverage_expansion"] = REVISION
    meta["coverage_expansion_backup_file"] = DEFAULT_BACKUP.name
    meta["coverage_expansion_unfilled"] = [
        {"node_code": u["node_code"], "name": u["name"], "reason": u["reason"]}
        for u in candidates_payload.get("unfilled") or []
    ]
    stats = taxonomy.get("stats")
    if isinstance(stats, dict):
        validation_pre = validate_tree(taxonomy)
        stats["total_node_count"] = validation_pre["total_codes"]
        leaf_count = 0

        def count_leaves(node: dict[str, Any]) -> None:
            nonlocal leaf_count
            children = [c for c in node.get("children") or [] if isinstance(c, dict)]
            if not children:
                leaf_count += 1
            for child in children:
                count_leaves(child)

        for root in taxonomy.get("outline_structure") or []:
            if isinstance(root, dict):
                count_leaves(root)
        stats["leaf_count"] = leaf_count
    validation = validate_tree(taxonomy)
    return {"minted": minted, "errors": errors, "validation": validation}


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("derive", "apply"))
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--exam-dir", type=Path, default=DEFAULT_EXAM_DIR)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_OUTPUT_DIR / "coverage_expansion_candidates.json")
    parser.add_argument("--apply-report", type=Path, default=DEFAULT_OUTPUT_DIR / "coverage_expansion_apply_report.json")
    args = parser.parse_args(argv)

    if args.command == "derive":
        payload = build_candidates(
            taxonomy=_read_json(args.taxonomy),
            pack=_read_json(args.pack),
            exam_dir=args.exam_dir,
            book_files=DEFAULT_BOOK_FILES,
            lecture_dir=LECTURE_DIR,
            standard_dir=STANDARD_DIR,
        )
        _write_json(args.candidates, payload)
        print(json.dumps({"candidates": str(args.candidates), "summary": payload["summary"]}, ensure_ascii=False))
        return 0

    # apply
    taxonomy = _read_json(args.taxonomy)
    meta = taxonomy.get("meta") or {}
    if str(meta.get("frozen") or "") != EXPECTED_OLD_FROZEN_TAG:
        print(f"ABORT: canonical frozen tag is {meta.get('frozen')!r}, expected {EXPECTED_OLD_FROZEN_TAG!r}")
        return 1
    if args.backup.exists():
        print(f"ABORT: backup already exists: {args.backup}")
        return 1
    candidates_payload = _read_json(args.candidates)
    shutil.copy2(args.taxonomy, args.backup)
    result = apply_candidates(taxonomy=taxonomy, candidates_payload=candidates_payload)
    if result["errors"] or (result["validation"] and result["validation"]["duplicates"]):
        print(json.dumps({"verdict": "BLOCKED", **result}, ensure_ascii=False))
        return 1
    # match the existing canonical serialization convention (sorted keys, no trailing newline)
    args.taxonomy.write_text(
        json.dumps(taxonomy, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    report = {
        "schema": SCHEMA,
        "revision": REVISION,
        "new_frozen_tag": NEW_FROZEN_TAG,
        "backup": str(args.backup),
        "minted_count": len(result["minted"]),
        "minted": result["minted"],
        "validation": result["validation"],
        "unfilled_count": len(candidates_payload.get("unfilled") or []),
    }
    _write_json(args.apply_report, report)
    print(json.dumps({"verdict": "APPLIED", **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
