#!/usr/bin/env python3
"""Build an M35 shadow fixture from FastAPI case-question markdown.

This converts student-arranged markdown into the fixture shape consumed by the
M35 shadow A/B runner. It intentionally does not mint official labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


QUESTION_HEADING_RE = re.compile(r"^###\s+(Q\d{4}-\d{2})｜(.+?)\s*$")
META_RE = re.compile(r"^-\s*([^：]+)：`?(.+?)`?\s*$")
SOURCE_CHUNK_RE = re.compile(r"来源 chunk：(.+)$")
BACKTICK_RE = re.compile(r"`([^`]+)`")
QUESTION_ITEM_RE = re.compile(r"(?m)^\s*(\d+)[.．、]\s*(.+?)(?=^\s*\d+[.．、]\s*|\Z)", re.S)
ANSWER_PART_RE = re.compile(r"问题\s*([一二三四五六七八九十\d]+)\s*[：:]")
CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _section_after(lines: list[str], title: str) -> list[str]:
    marker = f"#### {title}"
    for index, line in enumerate(lines):
        if line.strip() == marker:
            start = index + 1
            end = len(lines)
            for cursor in range(start, len(lines)):
                if lines[cursor].startswith("#### "):
                    end = cursor
                    break
            return lines[start:end]
    return []


def _parse_metadata(lines: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in lines:
        match = META_RE.match(line.strip())
        if match:
            metadata[match.group(1).strip()] = match.group(2).strip().strip("`")
    return metadata


def _clean_body(lines: list[str]) -> str:
    text = "\n".join(line.rstrip() for line in lines).strip()
    return re.sub(r"^作答：\s*", "", text).strip()


def _source_refs(question_text: str) -> list[dict[str, Any]]:
    refs = []
    for line in question_text.splitlines():
        match = SOURCE_CHUNK_RE.search(line)
        if not match:
            continue
        chunks = BACKTICK_RE.findall(match.group(1)) or [match.group(1).strip()]
        for chunk in chunks:
            refs.append(
                {
                    "source_type": "fastapi_case_markdown_chunk",
                    "chunk_id": chunk.strip(),
                    "verified": False,
                }
            )
    return refs


def _number_value(raw: str) -> int | None:
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    return CHINESE_NUMBERS.get(raw)


def _split_question_items(question_text: str) -> tuple[str, list[tuple[int, str]]]:
    marker = question_text.find("【问题】")
    if marker < 0:
        return question_text, []
    background = question_text[:marker].strip()
    tail = question_text[marker + len("【问题】") :].strip()
    tail = re.sub(r"(?<!^)(?=\d+[.．、])", "\n", tail)
    items = []
    for match in QUESTION_ITEM_RE.finditer(tail):
        index = int(match.group(1))
        body = " ".join(match.group(2).strip().split())
        if body:
            items.append((index, body))
    return background, items


def _split_answer_parts(answer_text: str) -> dict[int, str]:
    matches = list(ANSWER_PART_RE.finditer(answer_text))
    if not matches:
        return {}
    parts: dict[int, str] = {}
    for offset, match in enumerate(matches):
        index = _number_value(match.group(1))
        if index is None:
            continue
        start = match.end()
        end = matches[offset + 1].start() if offset + 1 < len(matches) else len(answer_text)
        body = answer_text[start:end].strip()
        if body:
            parts[index] = body
    return parts


def _iter_question_blocks(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    starts: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        match = QUESTION_HEADING_RE.match(line)
        if match:
            starts.append((index, match))

    blocks = []
    for offset, (start, match) in enumerate(starts):
        end = starts[offset + 1][0] if offset + 1 < len(starts) else len(lines)
        body = lines[start + 1 : end]
        metadata = _parse_metadata(_section_after(body, "样本元数据"))
        question_lines = _section_after(body, "题目")
        answer_lines = _section_after(body, "回答")
        answer_id = metadata.get("样本ID") or f"{match.group(1)}__{metadata.get('学生ID', 'UNKNOWN')}"
        blocks.append(
            {
                "question_id": match.group(1),
                "title": match.group(2).strip(),
                "metadata": metadata,
                "question_text": _clean_body(question_lines),
                "student_answer": _clean_body(answer_lines),
                "answer_id": answer_id,
            }
        )
    return blocks


def _expand_subquestion_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded = []
    for block in blocks:
        background, question_items = _split_question_items(block["question_text"])
        answer_parts = _split_answer_parts(block["student_answer"])
        for index, question_item in question_items:
            answer = answer_parts.get(index)
            if not answer:
                continue
            sub_id = f"{block['question_id']}__P{index:02d}"
            expanded.append(
                {
                    **block,
                    "parent_question_id": block["question_id"],
                    "question_id": sub_id,
                    "title": f"{block['title']} / 问题{index}",
                    "question_text": f"{background}\n\n【问题】{index}. {question_item}".strip(),
                    "student_answer": answer,
                    "answer_id": f"{sub_id}__{block['metadata'].get('学生ID', 'UNKNOWN')}",
                    "subquestion_index": index,
                }
            )
    return expanded


def build_fixture(
    *,
    source: Path,
    output_dir: Path,
    target_question_count: int,
    target_answer_count: int,
    split_subquestions: bool = False,
) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8")
    blocks = _iter_question_blocks(text)
    if split_subquestions:
        blocks = _expand_subquestion_blocks(blocks)

    questions_by_id: dict[str, dict[str, Any]] = {}
    question_order: list[str] = []
    rows = []
    for block in blocks:
        question_id = block["question_id"]
        if question_id not in questions_by_id:
            question_order.append(question_id)
            content_hash = hashlib.sha256(block["question_text"].encode("utf-8")).hexdigest()
            questions_by_id[question_id] = {
                "question_id": question_id,
                "title": block["title"],
                "stem": block["question_text"],
                "total_score": None,
                "source_refs": _source_refs(block["question_text"]),
                "question_authority_ref": {
                    "module": "FastAPI20251222.docs.2026.case_markdown",
                    "source_path": str(source),
                    "content_hash": content_hash,
                },
            }
        metadata = block["metadata"]
        rows.append(
            {
                "answer_id": block["answer_id"],
                "question_id": question_id,
                "parent_question_id": block.get("parent_question_id"),
                "subquestion_index": block.get("subquestion_index"),
                "student_id": metadata.get("学生ID"),
                "student_answer": block["student_answer"],
                "ability_label": metadata.get("ability_label"),
                "answer_quality_label": metadata.get("answer_quality_label"),
                "estimated_score_range": metadata.get("预估得分区间"),
                "gold_score": None,
                "gold_point_matches": [],
                "label_authority": "estimated_metadata_only",
                "label_scope": "score_range_not_gold",
                "directionality_flag": "source_markdown_student_simulation",
            }
        )

    actual_question_count = len(questions_by_id)
    actual_answer_count = len(rows)
    source_status = (
        "OK"
        if actual_question_count >= target_question_count
        and actual_answer_count >= target_answer_count
        else "SOURCE_LIMIT"
    )
    manifest = {
        "schema_version": "luban_m35_fastapi_case_fixture.v1",
        "source": str(source),
        "source_status": source_status,
        "requested_question_count": target_question_count,
        "requested_answer_count": target_answer_count,
        "actual_question_count": actual_question_count,
        "actual_answer_count": actual_answer_count,
        "label_authority": "estimated_metadata_only",
        "fixture_grain": "subquestion" if split_subquestions else "case_question",
        "quality_claim_allowed": False,
        "official_score_allowed": False,
        "questions": [questions_by_id[question_id] for question_id in question_order],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "student_answers.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-question-count", type=int, default=20)
    parser.add_argument("--target-answer-count", type=int, default=100)
    parser.add_argument("--split-subquestions", action="store_true")
    args = parser.parse_args()

    manifest = build_fixture(
        source=args.source,
        output_dir=args.output_dir,
        target_question_count=max(0, args.target_question_count),
        target_answer_count=max(0, args.target_answer_count),
        split_subquestions=args.split_subquestions,
    )
    print(
        json.dumps(
            {
                "source_status": manifest["source_status"],
                "actual_question_count": manifest["actual_question_count"],
                "actual_answer_count": manifest["actual_answer_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
