"""Build M2 case-rubric expansion artifacts.

M2 is a data-production dry run: it collects gradeable case-question candidates
from local exam JSON, builds 3-5 draft audit packets, and simulates registry
impact. It does not call providers, emit a registry, or promote weak anchors.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.luban_case_rubric_schema import OFFICIAL_ANSWER, TEXTBOOK, validate_audit_packet

OUT_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_expansion_m2_20260604"
EXAM_ROOT_CANDIDATES = (
    Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库"),
    Path("/Users/yehongchen/Developer/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库"),
)
BOOK_ROOT_CANDIDATES = (
    Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强"),
    Path("/Users/yehongchen/Developer/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强"),
)
JURY_MODELS = ["gpt55", "opus48", "deepseek_v4", "qwen37"]
MCQ_TYPES = {"single_choice", "multi_choice", "multiple_choice", "true_false"}


@dataclass(frozen=True)
class TextbookChunk:
    chunk_id: str
    node_code: str
    content_markdown: str
    source_file: str


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _clean_json_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for old in path.glob("*.json"):
        old.unlink()


def _first_existing(paths: tuple[Path, ...]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _node_code_from(chunk: dict[str, Any], exercise: dict[str, Any]) -> str:
    taxonomy = chunk.get("taxonomy") or {}
    node = taxonomy.get("node_code")
    if node:
        return str(node)
    predicted = exercise.get("predicted_node") or {}
    if isinstance(predicted, dict):
        node = predicted.get("node_code") or predicted.get("code")
        if node:
            return str(node)
    return "unknown"


def _question_id(source_path: Path, chunk_id: str, index: int) -> str:
    year_match = re.search(r"V(20\d{2})", source_path.name) or re.search(r"(20\d{2})", source_path.parent.name)
    year = year_match.group(1) if year_match else "unknown"
    safe_chunk = re.sub(r"[^A-Za-z0-9_-]+", "-", chunk_id or f"CASE-{index}")
    return f"M2-{year}-{safe_chunk}-{index:02d}"


def _iter_exam_files(exam_root: Path) -> list[Path]:
    return sorted(exam_root.glob("**/FINAL_CLEANED*.json"))


def collect_candidate_questions(limit: int = 30) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    exam_root = _first_existing(EXAM_ROOT_CANDIDATES)
    if not exam_root:
        return [], [], {"exam_root": None, "exam_files": 0, "raw_case_study_count": 0, "excluded_mcq_count": 0}

    all_candidates: list[dict[str, Any]] = []
    excluded_mcq: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    raw_case_study_count = 0
    exam_files = _iter_exam_files(exam_root)

    for source_path in exam_files:
        data = _read_json(source_path)
        for chunk in data.get("chunks") or []:
            chunk_id = str(chunk.get("chunk_id") or "")
            for idx, exercise in enumerate(chunk.get("exercises") or [], start=1):
                source_type = str(exercise.get("type") or "")
                qd = exercise.get("question_data") or {}
                stem = _clean_text(qd.get("stem"))
                official_answer = _clean_text(qd.get("analysis") or qd.get("reference_answer") or qd.get("correct_answer") or qd.get("answer"))
                if source_type in MCQ_TYPES:
                    excluded_mcq.append(
                        {
                            "question_id": _question_id(source_path, chunk_id, idx),
                            "source_type": source_type,
                            "source_file": str(source_path),
                            "question_text": stem[:240],
                            "blocker_reason": "objective_question_not_case_rubric_candidate",
                        }
                    )
                    continue
                if source_type == "case_study":
                    raw_case_study_count += 1
                if source_type != "case_study" or not stem or not official_answer:
                    continue
                if len(stem) < 80:
                    continue
                dedupe_key = (str(source_path), chunk_id, official_answer[:120])
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                node_code = _node_code_from(chunk, exercise)
                all_candidates.append(
                    {
                        "question_id": _question_id(source_path, chunk_id, idx),
                        "question_text": stem,
                        "official_answer": official_answer,
                        "node_code": node_code,
                        "source_file": str(source_path),
                        "source_type": source_type,
                        "extraction_confidence": 0.82 if node_code != "unknown" else 0.68,
                        "is_gradeable_case_candidate": True,
                        "blocker_reason": "",
                    }
                )

    candidates = _round_robin_by_source(all_candidates, limit)
    return candidates, excluded_mcq, {
        "exam_root": str(exam_root),
        "exam_files": len(exam_files),
        "raw_case_study_count": raw_case_study_count,
        "excluded_mcq_count": len(excluded_mcq),
    }


def _round_robin_by_source(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    by_source: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_source.setdefault(candidate["source_file"], []).append(candidate)
    selected: list[dict[str, Any]] = []
    while len(selected) < limit:
        added = False
        for source_file in sorted(by_source):
            bucket = by_source[source_file]
            if bucket:
                selected.append(bucket.pop(0))
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
    return selected


def _load_textbook_chunks() -> tuple[list[TextbookChunk], dict[str, Any]]:
    book_root = _first_existing(BOOK_ROOT_CANDIDATES)
    if not book_root:
        return [], {"book_root": None, "book_files": 0, "textbook_chunks": 0}
    files = sorted(book_root.glob("FINAL_CLEANED_BOOK2026-*v3_fixed.json"))
    chunks: list[TextbookChunk] = []
    for source_path in files:
        data = _read_json(source_path)
        for block in data.get("content_blocks") or []:
            taxonomy = block.get("taxonomy") or {}
            content = str(block.get("content_markdown") or "")
            chunk_id = str(block.get("chunk_id") or "")
            if chunk_id and content:
                chunks.append(
                    TextbookChunk(
                        chunk_id=chunk_id,
                        node_code=str(taxonomy.get("node_code") or ""),
                        content_markdown=content,
                        source_file=str(source_path),
                    )
                )
    return chunks, {"book_root": str(book_root), "book_files": len(files), "textbook_chunks": len(chunks)}


def _candidate_terms(answer: str) -> list[str]:
    raw_parts = re.split(r"[，。；;、：（）()\[\]\n\r]+", answer)
    terms: list[str] = []
    for part in raw_parts:
        part = _clean_text(part).strip(" .")
        if 2 <= len(part) <= 28 and not re.fullmatch(r"[0-9.]+", part):
            terms.append(part)
    for numeric in re.findall(r"\d+(?:\.\d+)?\s*(?:%|m2|m²|㎡|m3|m³|mm|cm|m|d|天|月|个月|万元|元|℃)", answer):
        terms.append(_clean_text(numeric))
    deduped: list[str] = []
    for term in terms:
        if term not in deduped:
            deduped.append(term)
    return deduped[:8]


def _policy_for(candidate: dict[str, Any], point_index: int, term: str) -> str:
    answer = candidate["official_answer"]
    node = str(candidate.get("node_code") or "")
    if re.search(r"\d", term) or any(k in answer for k in ("计算", "工期", "费用", "索赔", "持续时间")):
        return "calculation"
    if any(k in answer for k in ("包括", "分别为", "有：", "如下", "内容包括")) and point_index <= 2:
        return "list_rule"
    if "1A436000" in node or any(k in answer for k in ("罚", "不得", "禁止", "限制", "责令")):
        return "penalty_rule" if point_index == 1 else "exact_required"
    return "exact_required"


def _find_verbatim_anchor(term: str, node_code: str, chunks: list[TextbookChunk]) -> dict[str, Any] | None:
    if len(term) < 3:
        return None
    preferred = [c for c in chunks if node_code != "unknown" and c.node_code.startswith(node_code[:5])]
    search_space = preferred or chunks
    for chunk in search_space:
        if term in chunk.content_markdown:
            return {
                "source_type": TEXTBOOK,
                "chunk_id": chunk.chunk_id,
                "textbook_quote": term,
                "verified": True,
                "match_method": "verbatim",
                "source_file": chunk.source_file,
            }
    return None


def _source_ref_for(term: str, candidate: dict[str, Any], chunks: list[TextbookChunk]) -> tuple[dict[str, Any], str]:
    anchor = _find_verbatim_anchor(term, str(candidate.get("node_code") or ""), chunks)
    if anchor:
        return anchor, "verified_textbook"
    return (
        {
            "source_type": OFFICIAL_ANSWER,
            "chunk_id": "",
            "textbook_quote": term,
            "verified": False,
            "match_method": "none",
            "source_file": candidate["source_file"],
        },
        "missing_or_weak",
    )


def _point_for(candidate: dict[str, Any], point_index: int, term: str, chunks: list[TextbookChunk]) -> dict[str, Any]:
    policy = _policy_for(candidate, point_index, term)
    source_ref, source_status = _source_ref_for(term, candidate, chunks)
    point: dict[str, Any] = {
        "point_id": f"P{point_index}",
        "label": term,
        "policy_type": policy,
        "max_score": 1.0,
        "source_refs": [source_ref],
        "source_status": source_status,
        "auto_certifiable": False,
        "review_required": True,
        "rationale": "M2 draft candidate; no auto-certification until published gate and human/source review.",
    }
    if policy == "exact_required":
        point["required_terms"] = [term]
    elif policy == "list_rule":
        terms = _candidate_terms(candidate["official_answer"])[:4] or [term]
        point["required_terms"] = terms
        point["list_spec"] = {"denominator": len(terms), "terms": terms, "partial_credit": True}
    elif policy == "calculation":
        point["calculation_spec"] = {
            "expected_expression_or_value": term,
            "tolerance": None,
            "unit": "",
            "requires_process": True,
        }
    elif policy == "penalty_rule":
        point["required_terms"] = [term]
        point["penalty_rule"] = {"required_condition": term, "penalty_if_missing": "manual_review_required"}
    return point


def _select_deep_audit_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selectors = (
        lambda c: "1A436000" in str(c.get("node_code") or "") or "罚" in c["official_answer"],
        lambda c: "1A433000" in str(c.get("node_code") or "") or "工期" in c["official_answer"],
        lambda c: "1A432000" in str(c.get("node_code") or "") or "温" in c["official_answer"],
        lambda c: "1A434000" in str(c.get("node_code") or "") or "验收" in c["official_answer"],
        lambda c: True,
    )
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for selector in selectors:
        for candidate in candidates:
            if candidate["question_id"] not in used and selector(candidate):
                selected.append(candidate)
                used.add(candidate["question_id"])
                break
        if len(selected) >= 5:
            break
    return selected[:5] if len(selected) >= 3 else candidates[: min(5, len(candidates))]


def _build_packet(candidate: dict[str, Any], chunks: list[TextbookChunk]) -> dict[str, Any]:
    terms = _candidate_terms(candidate["official_answer"])[:3]
    if not terms:
        terms = [_clean_text(candidate["official_answer"])[:20] or "manual_review_required"]
    points = [_point_for(candidate, i, term, chunks) for i, term in enumerate(terms, start=1)]
    anchors = [ref for point in points for ref in point["source_refs"]]
    verified_count = sum(1 for ref in anchors if ref.get("source_type") == TEXTBOOK and ref.get("verified"))
    return {
        "schema_version": "luban_case_rubric_audit_packet.v0",
        "question_id": candidate["question_id"],
        "question_text": candidate["question_text"],
        "official_answer": candidate["official_answer"],
        "node_code": candidate["node_code"],
        "source_exam": candidate["source_file"],
        "rubric_candidates": [
            {
                "candidate_source": "official_answer_extraction",
                "candidate_terms": terms,
                "authority": "candidate_only_not_textbook_authority",
            }
        ],
        "textbook_anchor_evidence": anchors,
        "teacher_review_status": "unreviewed",
        "artifact_status": "draft",
        "scoring_points": points,
        "quality_gate": {
            "auto_certifiable_point_count": 0,
            "verified_textbook_anchor_count": verified_count,
            "blocked_reasons": ["m2_draft_only", "llm_jury_unavailable", "needs_human_or_official_source_review"],
        },
        "provenance": {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "builder": "scripts/build_luban_case_rubric_expansion_m2.py",
            "source_type": "local_exam_json",
            "llm_jury_used_as": "candidate_review_only",
        },
    }


def _anchor_status(row: dict[str, Any]) -> str:
    if row.get("source_type") == TEXTBOOK and row.get("verified") and row.get("chunk_id") and row.get("textbook_quote"):
        return "verified"
    if row.get("source_type") == OFFICIAL_ANSWER:
        return "weak"
    return "missing"


def _build_textbook_anchor_audit(packets: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for packet in packets:
        for point in packet["scoring_points"]:
            ref = (point.get("source_refs") or [{}])[0]
            status = _anchor_status(ref)
            rows.append(
                {
                    "question_id": packet["question_id"],
                    "point_id": point["point_id"],
                    "policy_type": point["policy_type"],
                    "anchor_status": status,
                    "chunk_id": ref.get("chunk_id") or "",
                    "textbook_quote": ref.get("textbook_quote") or "",
                    "normalized_match": ref.get("textbook_quote") if status == "verified" else "",
                    "reason": (
                        "verbatim content_markdown match"
                        if status == "verified"
                        else "official_answer or missing anchor is weak and cannot auto-certify"
                    ),
                }
            )
    return {"point_anchor_audit": rows, "summary": dict(Counter(row["anchor_status"] for row in rows))}


def _build_llm_jury(packets: list[dict[str, Any]], model_vote_dir: Path) -> dict[str, Any]:
    model_vote_dir.mkdir(parents=True, exist_ok=True)
    per_packet: list[dict[str, Any]] = []
    for packet in packets:
        vote_record = {
            "question_id": packet["question_id"],
            "available_models": [],
            "unavailable_models": JURY_MODELS,
            "model_votes": [],
            "dissent": [],
            "consensus_level": "unavailable",
            "reason": "No live provider/cache was available for new-candidate rubric extraction in this environment; no vote fabricated.",
        }
        _write_json(model_vote_dir / f"{packet['question_id']}.json", vote_record)
        per_packet.append(vote_record)
    return {
        "review_source": "model_jury_rubric_review",
        "reviewer_type": "llm_jury",
        "jury_models": JURY_MODELS,
        "adjudication_protocol": "case_rubric_jury_v0",
        "available_models": [],
        "unavailable_models": JURY_MODELS,
        "model_votes": [],
        "packet_reviews": per_packet,
        "verdict": "needs_human_review",
        "reason": "LLM jury was requested but no eligible live/cache prediction source was available; packets remain draft candidates.",
        "dissent": [],
    }


def _build_registry_impact(packets: list[dict[str, Any]]) -> dict[str, Any]:
    point_rows = [point for packet in packets for point in packet["scoring_points"]]
    blocked = Counter(reason for packet in packets for reason in packet["quality_gate"].get("blocked_reasons", []))
    return {
        "simulation_only": True,
        "formal_registry_emitted": False,
        "new_draft_count": len(packets),
        "new_published_count": 0,
        "auto_certifiable_points": sum(1 for point in point_rows if point.get("auto_certifiable")),
        "total_candidate_points": len(point_rows),
        "blocked_reasons": dict(blocked),
        "needs_human_or_official_source": [packet["question_id"] for packet in packets],
    }


def _write_input_audit(out_dir: Path, candidate_meta: dict[str, Any], book_meta: dict[str, Any], candidates: list[dict[str, Any]], excluded_mcq: list[dict[str, Any]]) -> None:
    text = f"""# M2 Input Candidate Audit

- exam_root: `{candidate_meta.get('exam_root')}`
- exam_files_scanned: {candidate_meta.get('exam_files')}
- raw_case_study_count: {candidate_meta.get('raw_case_study_count')}
- candidate_case_questions: {len(candidates)}
- excluded_mcq: {len(excluded_mcq)}
- textbook_root: `{book_meta.get('book_root')}`
- textbook_files_scanned: {book_meta.get('book_files')}
- textbook_chunks_scanned: {book_meta.get('textbook_chunks')}

## Source Policy

- Exam JSON `case_study` items are candidate question sources.
- MCQ types are excluded and written to `excluded_mcq.json`.
- `official_answer` is weak evidence only.
- Textbook `content_markdown` verbatim match is the only verified anchor path.
- 6134 node-level assets and mvp-rubric-20q are reference/search seeds only; they are not used as rubric authority in M2.
"""
    (out_dir / "input_candidate_audit.md").write_text(text, "utf-8")


def _write_finding(out_dir: Path, candidates: list[dict[str, Any]], excluded_mcq: list[dict[str, Any]], packets: list[dict[str, Any]], anchor_audit: dict[str, Any], impact: dict[str, Any]) -> None:
    anchor_summary = anchor_audit.get("summary") or {}
    top_blockers = Counter(impact.get("blocked_reasons") or {}).most_common(5)
    text = f"""# FINDING case rubric expansion M2 20260604

1. 找到 case-like 候选：{len(candidates)} 道，来源为本地历年案例题 JSON。
2. 排除 MCQ：{len(excluded_mcq)} 条，未进入 case registry 候选。
3. deep audit packet：{len(packets)} 道，全部为 `draft`，均通过 A1 schema validator。
4. 四模型可用性：本环境未发现可用于新候选 rubric extraction 的 live/cache provider；不可用模型为 {', '.join(JURY_MODELS)}，未伪造 vote。
5. textbook verified anchors：{anchor_summary.get('verified', 0)} 个。
6. weak/missing anchors：weak={anchor_summary.get('weak', 0)}，missing={anchor_summary.get('missing', 0)}，blocked={anchor_summary.get('blocked', 0)}。
7. 新增 published 预估：{impact['new_published_count']}。
8. 新增 draft 预估：{impact['new_draft_count']}。
9. blocked Top 5：{top_blockers}。
10. 是否伪造 source_ref：NO。official_answer 只作 weak，textbook verified 只接受 content_markdown verbatim。
11. 是否把 LLM 当真人：NO。reviewer_type=`llm_jury`，不是 `manual_qa_teacher`。
12. 是否能解锁 registry v1：不能。还差可用 LLM jury/live cache 或人工/官方来源复核，以及足够 verified textbook anchors 后的发布 gate。
13. 下一批建议：先补 20-50 道候选的教材逐字锚点，再单独跑真实 LLM jury/cache；不要为了 published 数字放宽 source_ref。

## Scope Guard

- 未新增 DB 表。
- 未接 production runtime。
- 未改 CaseGradingSkillKernel。
- 未让 RAG 进入评分 authority。
- 未生成正式 registry。
"""
    (out_dir / "FINDING_case_rubric_expansion_m2_20260604.md").write_text(text, "utf-8")


def build_m2_artifacts(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    _clean_json_dir(out_dir / "audit_packets")
    _clean_json_dir(out_dir / "model_votes")

    candidates, excluded_mcq, candidate_meta = collect_candidate_questions()
    chunks, book_meta = _load_textbook_chunks()
    selected = _select_deep_audit_candidates(candidates)
    packets = [_build_packet(candidate, chunks) for candidate in selected]

    for packet in packets:
        violations = validate_audit_packet(packet)
        if violations:
            raise ValueError(f"invalid audit packet {packet['question_id']}: {violations}")
        _write_json(out_dir / "audit_packets" / f"{packet['question_id']}.json", packet)

    jury = _build_llm_jury(packets, out_dir / "model_votes")
    anchor_audit = _build_textbook_anchor_audit(packets)
    impact = _build_registry_impact(packets)

    _write_input_audit(out_dir, candidate_meta, book_meta, candidates, excluded_mcq)
    _write_json(out_dir / "candidate_case_questions.json", candidates)
    _write_json(out_dir / "excluded_mcq.json", excluded_mcq)
    _write_json(out_dir / "llm_jury_rubric_candidates.json", jury)
    _write_json(out_dir / "textbook_anchor_audit.json", anchor_audit)
    _write_json(out_dir / "registry_impact_simulation.json", impact)
    _write_finding(out_dir, candidates, excluded_mcq, packets, anchor_audit, impact)
    return {
        "out_dir": str(out_dir),
        "candidate_count": len(candidates),
        "excluded_mcq_count": len(excluded_mcq),
        "audit_packet_count": len(packets),
        "registry_impact": impact,
    }


if __name__ == "__main__":
    print(json.dumps(build_m2_artifacts(), ensure_ascii=False, indent=2))
