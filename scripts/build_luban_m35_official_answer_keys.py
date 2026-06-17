#!/usr/bin/env python3
"""Compile official exam reference answers into M35 fixture scoring points (R1).

Answer-key authority = exam_reference_answer: the FINAL_CLEANED_EXAM_V{year}.json
question-bank chunks carry the official answers (per-subquestion exercises and/or
"N. （本小题X分）" markdown answer blocks with 【评分标准】 lines). This script is
purely deterministic — regex parsing only, no LLM and no network. Anything
ambiguous (missing/conflicting official scores, combined answers without
per-subquestion scores, infeasible splits) is routed to ``work_orders`` instead
of being guessed; those questions get no ``scoring_points``.

Every emitted scoring point carries a verified source_ref whose ``quote_hash``
is sha256 over a verbatim fragment of the official source text, so provenance
can be re-checked against the corpus at any time. Per-question rubrics are
re-validated through ``rubric_compiler.validate_rubric`` (score-sum hard gate).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.rubric_compiler import POLICIES, validate_rubric
from scripts.build_luban_m35_fastapi_case_fixture import _split_question_items

DEFAULT_EXAM_ROOT = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库"
)
DEFAULT_MANIFESTS = (
    Path("tests/fixtures/luban_m35_fastapi_case_scoring_2026/manifest.json"),
    Path("tests/fixtures/luban_m35_fastapi_case_subquestions_20q_100a/manifest.json"),
)
BUILD_SCRIPT_NAME = "scripts/build_luban_m35_official_answer_keys.py"
ANSWER_KEY_AUTHORITY = "exam_reference_answer"

QUESTION_ID_YEAR_RE = re.compile(r"^Q(\d{4})-")
SUBQUESTION_SUFFIX_RE = re.compile(r"^(?P<parent>.+?)__P(?P<sub>\d{2})$")
ANSWER_BLOCK_HEADER_RE = re.compile(
    r"(?m)^(?P<index>\d{1,2})[.．、]\s*[（(]本小题\s*(?P<score>\d+(?:\.\d+)?)\s*分[）)]"
)
PAREN_MARKER_RE = re.compile(r"[（(](\d{1,2})[）)]")
CIRCLED_MARKERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
BUTUO_MARKER_RE = re.compile(r"不妥之([一二三四五六七八九十])")
CHINESE_NUMBERS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                   "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
SCORING_NOTE_RE = re.compile(r"【评分标准[^】]*】?")
QUESTION_MARKER = "【问题】"
OPTION_ANALYSIS_MARKER = "【选项分析】"
EXERCISE_INLINE_INDEX_RE = re.compile(r"\s*(\d{1,2})\s*[.．、]")
LINE_START_ITEM_RE = re.compile(r"(?m)^\s*\d{1,2}[.．、]")
CALC_HINT_RE = re.compile(r"\d\s*[=＝]|[=＝]\s*\d|\d+(?:\.\d+)?\s*[×x*+]\s*[（(]?\d")
BOOLEAN_LEAD_RE = re.compile(r"^[（(]?\d{0,2}[）)]?\s*(不妥当|妥当|不正确|正确|不成立|成立|是|否|不需要|需要)[。；，、\s]")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_answer_blocks(markdown: str) -> list[dict[str, Any]]:
    """Split "N. （本小题X分）" official answer blocks out of chunk markdown.

    Each block's ``fragment`` is the verbatim substring of the source markdown
    (header included) so its hash is re-checkable against the corpus.
    """
    headers = list(ANSWER_BLOCK_HEADER_RE.finditer(markdown))
    blocks: list[dict[str, Any]] = []
    expected = 1
    for offset, match in enumerate(headers):
        index = int(match.group("index"))
        if index != expected:
            continue
        expected += 1
        end = headers[offset + 1].start() if offset + 1 < len(headers) else len(markdown)
        blocks.append(
            {
                "sub_index": index,
                "score": float(match.group("score")),
                "body": markdown[match.end():end].strip(),
                "fragment": markdown[match.start():end].strip(),
            }
        )
    return blocks


def _ascending_marker_segments(
    text: str, positions: list[tuple[int, int]]
) -> list[str] | None:
    """Cut ``text`` at marker positions whose ordinals ascend from 1."""
    starts: list[int] = []
    expected = 1
    for position, number in positions:
        if number == expected:
            starts.append(position)
            expected += 1
    if len(starts) < 2:
        return None
    segments: list[str] = []
    preamble = text[: starts[0]].strip()
    if len(preamble) >= 2:
        segments.append(preamble)
    for offset, start in enumerate(starts):
        end = starts[offset + 1] if offset + 1 < len(starts) else len(text)
        segment = text[start:end].strip()
        if segment:
            segments.append(segment)
    return segments


def split_scoring_segments(body: str) -> tuple[list[str], str | None]:
    """Split one subquestion's official answer into scoring-point segments.

    Strategies in order: （1）（2）… markers, ①②… markers, 不妥之一/之二…
    markers, else the whole answer as a single point. Every segment stays a
    verbatim (stripped) substring of the official answer text. The 【评分标准】
    line is returned separately as a policy note, never as a criterion.
    """
    note_match = SCORING_NOTE_RE.search(body)
    policy_note = note_match.group(0) if note_match else None
    text = body[: note_match.start()] if note_match else body
    text = text.rstrip()

    # quoted markers (“（2）”不正确) are references inside an answer, not list markers.
    paren_positions = [
        (m.start(), int(m.group(1)))
        for m in PAREN_MARKER_RE.finditer(text)
        if (m.start() == 0 or text[m.start() - 1] not in "“”\"'「『")
        and (m.end() >= len(text) or text[m.end()] not in "“”\"'」』")
    ]
    segments = _ascending_marker_segments(text, paren_positions)
    if segments is None:
        # circled numerals count only at line start — mid-line ones are network-node
        # notation (①→②) or inline references (事件①、②), not point markers.
        circled_positions = [
            (m.start(1), CIRCLED_MARKERS.index(m.group(1)) + 1)
            for m in re.finditer(rf"(?m)^[ \t]*([{CIRCLED_MARKERS}])", text)
        ]
        segments = _ascending_marker_segments(text, circled_positions)
    if segments is None:
        butuo_positions = [
            (m.start(), CHINESE_NUMBERS.get(m.group(1), 0))
            for m in BUTUO_MARKER_RE.finditer(text)
        ]
        segments = _ascending_marker_segments(text, butuo_positions)
    if segments is None:
        stripped = text.strip()
        segments = [stripped] if stripped else []
    return segments, policy_note


def classify_policy(segment: str, policy_note: str | None) -> str:
    """Deterministic policy hint within rubric_compiler.POLICIES."""
    if policy_note and re.search(r"写出\s*\d+\s*项", policy_note):
        return "list"
    if BOOLEAN_LEAD_RE.match(segment):
        return "boolean_judgment"
    if CALC_HINT_RE.search(segment):
        return "calc"
    return "qualitative"


def allocate_scores(total: float, count: int) -> tuple[list[float], str] | None:
    """Allocate ``total`` over ``count`` points in 0.5 steps; None if infeasible."""
    if count <= 0:
        return None
    if count == 1:
        return [total], "single_point_full_score"
    half_points = total * 2
    if abs(half_points - round(half_points)) > 1e-9:
        return None
    half_points = int(round(half_points))
    if half_points < count:
        return None
    base, remainder = divmod(half_points, count)
    scores = [(base + (1 if i < remainder else 0)) / 2.0 for i in range(count)]
    rule = "equal_half_point_split" if remainder == 0 else "front_loaded_half_point_remainder"
    return scores, rule


@lru_cache(maxsize=None)
def _load_exam_chunks(exam_root: str, year: int) -> dict[str, dict[str, Any]]:
    path = (
        Path(exam_root)
        / f"{year}年一级建造师《建筑实务》考试真题及答案解析"
        / f"FINAL_CLEANED_EXAM_V{year}.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    return {chunk["chunk_id"]: chunk for chunk in data.get("chunks", [])}


def _exercise_subquestion_entries(
    chunk: dict[str, Any], exam_year: int
) -> tuple[dict[int, dict[str, Any]], set[int]]:
    """Extract per-subquestion official answers from a chunk's exercises.

    Returns (entries by sub_index, combined-exercise indices encountered).
    A combined exercise (one stem listing >=2 numbered subquestions) carries no
    per-subquestion scores and is never used as an answer key.
    """
    entries: dict[int, dict[str, Any]] = {}
    combined = False
    for position, exercise in enumerate(chunk.get("exercises") or []):
        if exercise.get("type") != "case_study":
            continue
        question_data = exercise.get("question_data") or {}
        stem = str(question_data.get("stem") or "")
        marker = stem.rfind(QUESTION_MARKER)
        if marker < 0:
            continue
        tail = stem[marker + len(QUESTION_MARKER):]
        if len(LINE_START_ITEM_RE.findall(tail)) >= 2:
            combined = True
            continue
        inline = EXERCISE_INLINE_INDEX_RE.match(tail)
        if not inline:
            continue
        sub_index = int(inline.group(1))
        score = question_data.get("score")
        answer = str(question_data.get("correct_answer") or "")
        cut = answer.find(OPTION_ANALYSIS_MARKER)
        if cut >= 0:
            answer = answer[:cut]
        answer = answer.strip()
        if sub_index in entries:
            continue
        entries[sub_index] = {
            "sub_index": sub_index,
            "score": float(score) if isinstance(score, (int, float)) else None,
            "answer_text": answer,
            "fragment": answer,
            "chunk_id": chunk["chunk_id"],
            "source_year": exam_year,
            "source_field": f"exercises[{position}].question_data.correct_answer",
        }
    return entries, {1} if combined else set()


def _markdown_answer_entries(
    chunks: dict[str, dict[str, Any]],
    referenced_chunk_ids: list[str],
    exam_year: int,
    expected_indices: set[int],
) -> dict[int, dict[str, Any]]:
    """Find the unique same-taxonomy markdown answer chunk, if any.

    The answer chunk (e.g. EXAM_1A436000_P0018_02) is associated only when its
    taxonomy prefix matches a referenced question chunk, it is the single such
    candidate in the year, and its block indices equal the expected set.
    """
    prefixes = {cid.split("_")[1] for cid in referenced_chunk_ids if "_" in cid}
    candidates: list[tuple[str, list[dict[str, Any]]]] = []
    for chunk_id, chunk in chunks.items():
        if chunk_id in referenced_chunk_ids:
            continue
        if chunk_id.split("_")[1] not in prefixes:
            continue
        blocks = split_answer_blocks(str(chunk.get("content_markdown") or ""))
        if blocks:
            candidates.append((chunk_id, blocks))
    if len(candidates) != 1:
        return {}
    chunk_id, blocks = candidates[0]
    if {block["sub_index"] for block in blocks} != expected_indices:
        return {}
    return {
        block["sub_index"]: {
            "sub_index": block["sub_index"],
            "score": block["score"],
            "answer_text": block["body"],
            "fragment": block["fragment"],
            "chunk_id": chunk_id,
            "source_year": exam_year,
            "source_field": "content_markdown",
        }
        for block in blocks
    }


def _compile_subquestion_points(
    question_id: str,
    entry: dict[str, Any],
    point_id_prefix: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]] | str:
    """Turn one official subquestion answer into scoring points; str = work-order reason."""
    segments, policy_note = split_scoring_segments(entry["answer_text"])
    if not segments:
        return "empty_official_answer"
    allocation = allocate_scores(entry["score"], len(segments))
    if allocation is None:
        return "score_split_infeasible"
    scores, allocation_rule = allocation
    points: list[dict[str, Any]] = []
    for position, (segment, score) in enumerate(zip(segments, scores), start=1):
        points.append(
            {
                "point_id": f"{question_id}::{point_id_prefix}SP{position:02d}",
                "criterion": segment,
                "max_score": score,
                "policy_type": classify_policy(segment, policy_note),
                "required_terms": [],
                "negative_evidence": [],
                "source_refs": [
                    {
                        "source_type": ANSWER_KEY_AUTHORITY,
                        "source_id": entry["chunk_id"],
                        "source_year": entry["source_year"],
                        "source_field": entry["source_field"],
                        "quote_hash": _sha256(segment),
                        "verified": True,
                    }
                ],
            }
        )
    provenance = {
        "subquestion_index": entry["sub_index"],
        "chunk_id": entry["chunk_id"],
        "source_year": entry["source_year"],
        "source_field": entry["source_field"],
        "official_score": entry["score"],
        "fragment_quote_hash": _sha256(entry["fragment"]),
        "allocation_rule": allocation_rule,
        "point_count": len(points),
        "scoring_policy_note": policy_note,
    }
    return points, provenance


def _question_year(question_id: str) -> int | None:
    match = QUESTION_ID_YEAR_RE.match(question_id)
    return int(match.group(1)) if match else None


def _referenced_chunk_ids(question: dict[str, Any]) -> list[str]:
    return [
        str(ref.get("chunk_id") or "")
        for ref in (question.get("source_refs") or [])
        if ref.get("chunk_id")
    ]


def _gather_official_entries(
    question: dict[str, Any],
    expected_indices: set[int],
    exam_root: Path,
) -> tuple[dict[int, dict[str, Any]], str | None]:
    """Collect per-subquestion official entries for a question; str = blocking reason."""
    question_id = str(question["question_id"])
    year = _question_year(question_id)
    if year is None:
        return {}, "unparseable_question_year"
    chunk_ids = _referenced_chunk_ids(question)
    if not chunk_ids:
        return {}, "no_source_chunk_ref"
    chunks = _load_exam_chunks(str(exam_root), year)
    entries: dict[int, dict[str, Any]] = {}
    combined_seen = False
    for chunk_id in chunk_ids:
        chunk = chunks.get(chunk_id)
        if chunk is None:
            return {}, "source_chunk_not_found"
        chunk_entries, combined = _exercise_subquestion_entries(chunk, year)
        combined_seen = combined_seen or bool(combined)
        for sub_index, entry in chunk_entries.items():
            existing = entries.get(sub_index)
            if existing is None:
                entries[sub_index] = entry
            elif (
                existing["score"] is not None
                and entry["score"] is not None
                and abs(existing["score"] - entry["score"]) > 0.01
            ):
                return {}, "conflicting_official_scores"
    missing = expected_indices - set(entries)
    if missing:
        markdown_entries = _markdown_answer_entries(chunks, chunk_ids, year, expected_indices)
        for sub_index in sorted(missing):
            if sub_index in markdown_entries:
                entries[sub_index] = markdown_entries[sub_index]
    still_missing = expected_indices - set(entries)
    if still_missing:
        if combined_seen:
            return {}, "combined_exercise_without_per_subquestion_scores"
        return {}, "official_answer_not_found_for_subquestions"
    return entries, None


def _expected_indices(question: dict[str, Any]) -> tuple[set[int], int | None]:
    """Expected subquestion indices and (for subquestion grain) the single index."""
    question_id = str(question["question_id"])
    sub_match = SUBQUESTION_SUFFIX_RE.match(question_id)
    if sub_match:
        index = int(sub_match.group("sub"))
        return {index}, index
    _, items = _split_question_items(str(question.get("stem") or ""))
    return {index for index, _ in items}, None


def _validate_with_rubric_compiler(
    question_id: str, total_score: float, points: list[dict[str, Any]]
) -> bool:
    rubric = {
        "qid": question_id,
        "total_score": total_score,
        "scoring_points": [
            {
                "point_id": point["point_id"],
                "text": point["criterion"],
                "score": point["max_score"],
                "policy": point["policy_type"],
                "required_terms": point["required_terms"],
                "negative_evidence": point["negative_evidence"],
            }
            for point in points
        ],
    }
    return bool(validate_rubric(rubric)["ok"])


def _compile_question(
    question: dict[str, Any], exam_root: Path
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Returns (enriched question fields, work order). Exactly one is non-None."""
    question_id = str(question["question_id"])
    expected, single_index = _expected_indices(question)

    def work_order(reason: str, detail: str) -> tuple[None, dict[str, Any]]:
        return None, {
            "question_id": question_id,
            "reason": reason,
            "detail": detail,
            "source_chunk_ids": _referenced_chunk_ids(question),
            "source_year": _question_year(question_id),
        }

    if not _referenced_chunk_ids(question):
        return work_order("no_source_chunk_ref", "fixture question carries no source chunk reference")
    if not expected:
        # No parseable 【问题】 items in the fixture stem: probe the referenced chunks
        # only to classify the gap precisely — never to guess a key.
        year = _question_year(question_id)
        combined_seen = False
        if year is not None:
            chunks = _load_exam_chunks(str(exam_root), year)
            for chunk_id in _referenced_chunk_ids(question):
                chunk = chunks.get(chunk_id)
                if chunk is not None:
                    _, combined = _exercise_subquestion_entries(chunk, year)
                    combined_seen = combined_seen or bool(combined)
        if combined_seen:
            return work_order(
                "combined_exercise_without_per_subquestion_scores",
                "stem lacks 【问题】 items and the official chunk only carries a "
                "combined multi-subquestion exercise without per-subquestion scores",
            )
        return work_order("no_subquestion_items_in_stem", "stem has no parseable 【问题】 items")
    entries, blocking_reason = _gather_official_entries(question, expected, exam_root)
    if blocking_reason:
        return work_order(
            blocking_reason,
            f"official answer key unresolved for subquestions {sorted(expected)}",
        )
    missing_scores = [i for i in sorted(expected) if entries[i]["score"] is None]
    if missing_scores:
        return work_order(
            "missing_official_subquestion_score",
            f"official score is null for subquestion(s) {missing_scores}",
        )

    all_points: list[dict[str, Any]] = []
    subquestion_provenance: list[dict[str, Any]] = []
    for sub_index in sorted(expected):
        prefix = "" if single_index is not None else f"S{sub_index:02d}-"
        compiled = _compile_subquestion_points(question_id, entries[sub_index], prefix)
        if isinstance(compiled, str):
            return work_order(compiled, f"subquestion {sub_index} could not be compiled")
        points, provenance = compiled
        all_points.extend(points)
        subquestion_provenance.append(provenance)

    total_score = round(sum(p["official_score"] for p in subquestion_provenance), 2)
    if not _validate_with_rubric_compiler(question_id, total_score, all_points):
        return work_order("rubric_validation_failed", "rubric_compiler.validate_rubric rejected")
    return (
        {
            "total_score": total_score,
            "scoring_points": all_points,
            "answer_key_provenance": {
                "answer_key_authority": ANSWER_KEY_AUTHORITY,
                "extraction": "deterministic_regex_no_llm",
                "validated_by": "rubric_compiler.validate_rubric",
                "subquestions": subquestion_provenance,
            },
        },
        None,
    )


def compile_manifest(
    manifest: dict[str, Any], *, exam_root: Path = DEFAULT_EXAM_ROOT
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compile official answer keys into a fixture manifest (pure; no I/O writes)."""
    compiled = dict(manifest)
    work_orders: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    source_years: set[int] = set()
    for question in manifest.get("questions", []):
        enriched = dict(question)
        enriched.pop("scoring_points", None)
        enriched.pop("answer_key_provenance", None)
        fields, work_order = _compile_question(question, exam_root)
        if fields is not None:
            enriched.update(fields)
            year = _question_year(str(question["question_id"]))
            if year is not None:
                source_years.add(year)
        else:
            work_orders.append(work_order)
        questions.append(enriched)
    compiled["questions"] = questions
    compiled["answer_key_authority"] = ANSWER_KEY_AUTHORITY
    compiled["answer_key_build_script"] = BUILD_SCRIPT_NAME
    compiled["answer_key_source_files"] = {
        str(year): str(
            exam_root
            / f"{year}年一级建造师《建筑实务》考试真题及答案解析"
            / f"FINAL_CLEANED_EXAM_V{year}.json"
        )
        for year in sorted(source_years)
    }
    compiled["work_orders"] = work_orders
    return compiled, work_orders


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-root", type=Path, default=DEFAULT_EXAM_ROOT)
    parser.add_argument(
        "--manifest",
        dest="manifests",
        type=Path,
        action="append",
        help="manifest.json to enrich in place (repeatable)",
    )
    args = parser.parse_args()
    manifests = args.manifests or [Path(p) for p in DEFAULT_MANIFESTS]

    summary: dict[str, Any] = {}
    for path in manifests:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        compiled, work_orders = compile_manifest(manifest, exam_root=args.exam_root)
        path.write_text(
            json.dumps(compiled, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        resolved = [q for q in compiled["questions"] if q.get("scoring_points")]
        point_count = sum(len(q["scoring_points"]) for q in resolved)
        verified = sum(
            1
            for q in resolved
            for p in q["scoring_points"]
            for ref in p["source_refs"]
            if ref.get("verified") is True
        )
        summary[str(path)] = {
            "questions": len(compiled["questions"]),
            "resolved": len(resolved),
            "work_orders": len(work_orders),
            "scoring_points": point_count,
            "verified_source_refs": verified,
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
