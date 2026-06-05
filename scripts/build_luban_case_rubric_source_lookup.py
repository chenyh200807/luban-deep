"""Source lookup package for M2 still-weak anchors.

This stage searches textbook, standard files, and official answer/explanation
sources for the 10 still-weak points after anchor backfill. It writes a separate
simulation package and does not emit a formal registry.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.luban_case_rubric_schema import TEXTBOOK, validate_audit_packet


BACKFILL_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_anchor_backfill_20260604"
OUT_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_source_lookup_20260604"
BOOK_ROOT_CANDIDATES = (
    Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强"),
    Path("/Users/yehongchen/Developer/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强"),
)
STANDARD_ROOT_CANDIDATES = (
    Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/标准文件"),
    Path("/Users/yehongchen/Developer/CYH_2/Markzuo/FastAPI20251222/docs/2026/标准文件"),
)
LOOKUP_SOURCE_TYPES = ["textbook", "standard", "official_answer"]
STRONG_SELECT_SEED_SOURCES = {"label_or_official_span", "required_terms", "calculation_spec"}


@dataclass(frozen=True)
class SearchDocument:
    source_type: str
    source_file: str
    chunk_id: str
    page_num: int | None
    content: str
    normalized_content: str


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


def _normalize(value: Any) -> str:
    text = str(value or "")
    table = str.maketrans(
        {
            "（": "(",
            "）": ")",
            "，": ",",
            "。": ".",
            "；": ";",
            "：": ":",
            "、": ",",
            "“": '"',
            "”": '"',
            "‘": "'",
            "’": "'",
            "—": "-",
            "～": "~",
            "×": "x",
            "㎡": "m2",
            "ｍ": "m",
        }
    )
    return re.sub(r"[\s,.;:!?\"'`·、，。；：（）()\[\]{}<>《》【】_-]+", "", text.translate(table).lower())


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_distinctive(term: str) -> bool:
    normalized = _normalize(term)
    if len(normalized) < 4:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?(?:%|m2|m3|mm|cm|m|d|天|月|个月|万元|元|℃)?", normalized):
        return False
    low_info = {"不妥一", "不妥二", "正确做法", "而非试验员", "解析", "根据", "内容包括"}
    if term in low_info or any(term.endswith(x) for x in low_info):
        return False
    return True


def _dedupe_terms(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        key = _normalize(row.get("term") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _split_distinctive(text: str, source: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for part in re.split(r"[，。；;、：（）()\[\]\n\r]+", str(text or "")):
        term = _clean_text(part).strip(" .。；;：:")
        if _is_distinctive(term):
            rows.append({"term": term, "seed_source": source})
    return rows


def _load_backfill_packets(backfill_dir: Path = BACKFILL_DIR) -> list[dict[str, Any]]:
    return [
        _read_json(path)
        for path in sorted((backfill_dir / "audit_packets_backfilled").glob("M2-*.json"))
        if path.name.startswith("M2-")
    ]


def _load_still_weak_rows(backfill_dir: Path = BACKFILL_DIR) -> list[dict[str, Any]]:
    rows = _read_json(backfill_dir / "textbook_anchor_search_results.json")
    return [row for row in rows if row.get("decision") != "verified" and str(row.get("question_id") or "").startswith("M2-")]


def build_still_weak_worklist(backfill_dir: Path = BACKFILL_DIR) -> list[dict[str, Any]]:
    packets = {packet["question_id"]: packet for packet in _load_backfill_packets(backfill_dir)}
    still_weak_rows = _load_still_weak_rows(backfill_dir)
    worklist: list[dict[str, Any]] = []
    for row in still_weak_rows:
        packet = packets[row["question_id"]]
        point = next(sp for sp in packet["scoring_points"] if sp["point_id"] == row["point_id"])
        refs = point.get("source_refs") or []
        official_answer_span = (refs[0].get("textbook_quote") if refs else "") or point.get("label") or ""
        search_terms: list[dict[str, str]] = []
        for value in [point.get("label") or "", official_answer_span]:
            if _is_distinctive(value):
                search_terms.append({"term": value, "seed_source": "label_or_official_span"})
        for term in point.get("required_terms") or []:
            if _is_distinctive(term):
                search_terms.append({"term": str(term), "seed_source": "required_terms"})
        calc = point.get("calculation_spec") or {}
        if isinstance(calc, dict) and _is_distinctive(calc.get("expected_expression_or_value") or ""):
            search_terms.append({"term": calc["expected_expression_or_value"], "seed_source": "calculation_spec"})
        search_terms.extend(_split_distinctive(packet.get("official_answer") or "", "official_answer_phrase"))
        for term_row in row.get("hits") or []:
            term = term_row.get("matched_term") or term_row.get("quote") or ""
            if _is_distinctive(term):
                search_terms.append({"term": term, "seed_source": "previous_textbook_hit"})
        worklist.append(
            {
                "question_id": packet["question_id"],
                "point_id": point["point_id"],
                "label": point.get("label") or "",
                "required_terms": point.get("required_terms") or [],
                "official_answer_span": official_answer_span,
                "current_reason": row.get("reason") or "",
                "search_terms": _dedupe_terms(search_terms)[:18],
                "candidate_source_types": LOOKUP_SOURCE_TYPES,
            }
        )
    return worklist


def _book_files(root: Path) -> list[Path]:
    return sorted(root.glob("FINAL_CLEANED_BOOK2026-*_fixed.json"))


@lru_cache(maxsize=1)
def _load_textbook_documents() -> tuple[SearchDocument, ...]:
    root = _first_existing(BOOK_ROOT_CANDIDATES)
    if not root:
        return tuple()
    docs: list[SearchDocument] = []
    for source_path in _book_files(root):
        data = _read_json(source_path)
        for block in data.get("content_blocks") or []:
            content = str(block.get("content_markdown") or "")
            chunk_id = str(block.get("chunk_id") or "")
            if not content or not chunk_id:
                continue
            docs.append(
                SearchDocument(
                    source_type="textbook",
                    source_file=str(source_path),
                    chunk_id=chunk_id,
                    page_num=block.get("page_num") if isinstance(block.get("page_num"), int) else None,
                    content=content,
                    normalized_content=_normalize(content),
                )
            )
    return tuple(docs)


def _iter_standard_strings(value: Any, path: str = "") -> list[tuple[str, str, int | None]]:
    rows: list[tuple[str, str, int | None]] = []
    if isinstance(value, dict):
        page_num = value.get("page_num") if isinstance(value.get("page_num"), int) else None
        chunk_id = str(value.get("id") or value.get("chunk_id") or value.get("node_id") or path)
        for key, child in value.items():
            if isinstance(child, str) and key in {"content", "content_markdown", "text", "article_text", "title", "original_text"}:
                rows.append((chunk_id, child, page_num))
            elif isinstance(child, (dict, list)):
                rows.extend(_iter_standard_strings(child, f"{path}/{key}"))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            rows.extend(_iter_standard_strings(item, f"{path}/{idx}"))
    return rows


@lru_cache(maxsize=1)
def _load_standard_documents() -> tuple[SearchDocument, ...]:
    root = _first_existing(STANDARD_ROOT_CANDIDATES)
    if not root:
        return tuple()
    docs: list[SearchDocument] = []
    for source_path in sorted(root.glob("*.json")):
        data = _read_json(source_path)
        for idx, (chunk_id, content, page_num) in enumerate(_iter_standard_strings(data), start=1):
            content = str(content or "")
            if len(_normalize(content)) < 4:
                continue
            docs.append(
                SearchDocument(
                    source_type="standard",
                    source_file=str(source_path),
                    chunk_id=chunk_id or f"standard_text_{idx}",
                    page_num=page_num,
                    content=content,
                    normalized_content=_normalize(content),
                )
            )
    return tuple(docs)


def _official_document_for_packet(packet: dict[str, Any]) -> SearchDocument:
    content = "\n".join(
        [
            str(packet.get("official_answer") or ""),
            str(packet.get("question_text") or ""),
        ]
    )
    return SearchDocument(
        source_type="official_answer",
        source_file=str(packet.get("source_exam") or ""),
        chunk_id=packet["question_id"],
        page_num=None,
        content=content,
        normalized_content=_normalize(content),
    )


def _hit(term: str, doc: SearchDocument, match_type: str, verified: bool) -> dict[str, Any] | None:
    if not _is_distinctive(term):
        return None
    if _normalize(term) not in doc.normalized_content:
        return None
    return {
        "source_type": doc.source_type,
        "source_file": doc.source_file,
        "chunk_id": doc.chunk_id,
        "page_num": doc.page_num,
        "quote": term,
        "matched_term": term,
        "match_type": match_type,
        "verified": verified,
    }


def _search_docs(terms: list[dict[str, str]], docs: list[SearchDocument] | tuple[SearchDocument, ...], source_type: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for term_row in terms:
        term = term_row.get("term") or ""
        for doc in docs:
            hit = _hit(
                term,
                doc,
                "verbatim_normalized" if source_type in {"textbook", "standard"} else "official_weak",
                source_type in {"textbook", "standard"},
            )
            if hit:
                hit["term_seed_source"] = term_row.get("seed_source") or ""
                hits.append(hit)
                break
    return hits


def _auto_certifiable_for_decision(decision: str) -> bool:
    return decision == "verified_textbook"


def _lookup_one(item: dict[str, Any], packet: dict[str, Any], textbook_docs: tuple[SearchDocument, ...], standard_docs: tuple[SearchDocument, ...]) -> dict[str, Any]:
    terms = item.get("search_terms") or []
    textbook_hits = _search_docs(terms, textbook_docs, "textbook")
    standard_hits = _search_docs(terms, standard_docs, "standard")
    official_hits = _search_docs(terms, [_official_document_for_packet(packet)], "official_answer")
    lookup_results = [*textbook_hits[:10], *standard_hits[:10], *official_hits[:10]]
    strong_textbook_hits = [hit for hit in textbook_hits if hit.get("term_seed_source") in STRONG_SELECT_SEED_SOURCES]
    strong_standard_hits = [hit for hit in standard_hits if hit.get("term_seed_source") in STRONG_SELECT_SEED_SOURCES]
    selected = None
    decision = "source_gap"
    reason = "no textbook, standard, or official verbatim match"
    if strong_textbook_hits:
        selected = strong_textbook_hits[0]
        decision = "verified_textbook"
        reason = "textbook content_markdown verbatim normalized match"
    elif strong_standard_hits:
        selected = strong_standard_hits[0]
        decision = "verified_standard"
        reason = "standard file verbatim normalized match; PO/expert review required before publish"
    elif official_hits:
        selected = official_hits[0]
        decision = "official_weak"
        reason = "official answer/exam explanation match only; weak source"
    return {
        "question_id": item["question_id"],
        "point_id": item["point_id"],
        "lookup_results": lookup_results,
        "selected_source": selected,
        "decision": decision,
        "standard_verified_candidate": decision == "verified_standard",
        "auto_certifiable": _auto_certifiable_for_decision(decision),
        "reason": reason,
    }


def build_source_lookup_results(worklist: list[dict[str, Any]], backfill_dir: Path = BACKFILL_DIR) -> list[dict[str, Any]]:
    packets = {packet["question_id"]: packet for packet in _load_backfill_packets(backfill_dir)}
    textbook_docs = _load_textbook_documents()
    standard_docs = _load_standard_documents()
    return [_lookup_one(item, packets[item["question_id"]], textbook_docs, standard_docs) for item in worklist]


def _source_ref_from_lookup(selected: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": TEXTBOOK,
        "chunk_id": selected["chunk_id"],
        "textbook_quote": selected["quote"],
        "verified": True,
        "match_method": "verbatim",
        "normalized_match": True,
        "source_file": selected["source_file"],
    }


def _apply_lookup_to_packets(packets: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(row["question_id"], row["point_id"]): row for row in results}
    output: list[dict[str, Any]] = []
    for packet in packets:
        packet_copy = copy.deepcopy(packet)
        for point in packet_copy.get("scoring_points") or []:
            result = by_key.get((packet_copy["question_id"], point["point_id"]))
            if not result:
                continue
            point["source_lookup"] = {
                "decision": result["decision"],
                "selected_source": result["selected_source"],
                "auto_certifiable": result["auto_certifiable"],
                "reason": result["reason"],
            }
            if result["decision"] == "verified_textbook" and result["selected_source"]:
                point["source_refs"] = [_source_ref_from_lookup(result["selected_source"])]
                point["source_status"] = "verified_textbook"
                point["auto_certifiable"] = True
                point["review_required"] = False
            else:
                point["auto_certifiable"] = bool(point.get("auto_certifiable")) and result["decision"] != "verified_standard"
        auto_count = sum(1 for point in packet_copy.get("scoring_points") or [] if point.get("auto_certifiable"))
        packet_copy["artifact_status"] = "published" if auto_count else "draft"
        packet_copy["artifact_candidate_status"] = "published_candidate_not_final" if auto_count else "draft_candidate"
        packet_copy["textbook_anchor_evidence"] = [
            ref for point in packet_copy.get("scoring_points") or [] for ref in point.get("source_refs") or []
        ]
        packet_copy["quality_gate"] = {
            **(packet_copy.get("quality_gate") or {}),
            "auto_certifiable_point_count": auto_count,
            "source_lookup_at": datetime.now(timezone.utc).isoformat(),
            "formal_registry_emitted": False,
        }
        packet_copy.setdefault("provenance", {})["source_lookup_builder"] = "scripts/build_luban_case_rubric_source_lookup.py"
        violations = validate_audit_packet(packet_copy)
        if violations:
            raise ValueError(f"invalid source lookup packet {packet_copy['question_id']}: {violations}")
        output.append(packet_copy)
    return output


def _source_lookup_audit(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": dict(Counter(row["decision"] for row in results)),
        "rows": results,
    }


def _registry_impact(results: list[dict[str, Any]], packets: list[dict[str, Any]], backfill_impact: dict[str, Any]) -> dict[str, Any]:
    decisions = Counter(row["decision"] for row in results)
    cumulative_auto = sum(1 for packet in packets for point in packet.get("scoring_points") or [] if point.get("auto_certifiable"))
    return {
        "simulation_only": True,
        "formal_registry_emitted": False,
        "input_still_weak_count": len(results),
        "textbook_verified_new": decisions.get("verified_textbook", 0),
        "standard_verified_candidate": decisions.get("verified_standard", 0),
        "official_weak": decisions.get("official_weak", 0),
        "source_gap": decisions.get("source_gap", 0),
        "new_auto_certifiable_points": decisions.get("verified_textbook", 0),
        "cumulative_auto_certifiable_points": cumulative_auto,
        "backfill_auto_certifiable_points": backfill_impact.get("new_auto_certifiable_points", 0),
        "published_candidate_not_final_count": sum(1 for p in packets if p.get("artifact_candidate_status") == "published_candidate_not_final"),
        "unpublishable_reasons": [
            "official_weak_not_strong_source",
            "standard_candidate_requires_po_or_expert_review",
            "source_gap_requires_source_lookup_or_drop_point",
            "formal_registry_not_emitted",
        ],
    }


def _write_source_ref_policy(path: Path) -> None:
    text = """# Source Ref Policy

- `verified_textbook`: may become `auto_certifiable=true` only when `chunk_id` and `quote` are non-empty and the normalized quote matches textbook `content_markdown` verbatim.
- `verified_standard`: recorded as `standard_verified_candidate`; it is not directly published and remains pending PO/expert review before registry use.
- `official_weak`: official answer or exam explanation only; it cannot become `auto_certifiable`.
- `source_gap`: no auditable strong source found; it cannot become `auto_certifiable`.
- `llm_suggestion`: search assistance only; never written as `source_ref`.
"""
    path.write_text(text, "utf-8")


def _write_source_evidence_table(path: Path, worklist: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
    labels = {(row["question_id"], row["point_id"]): row.get("label", "") for row in worklist}
    lines = [
        "# Source Evidence Table",
        "",
        "| question_id | point_id | label | decision | selected source_type | source_file | quote | auto_certifiable reason |",
        "|---|---:|---|---|---|---|---|---|",
    ]
    for row in results:
        selected = row.get("selected_source") or {}
        auto_reason = "yes: verified textbook" if row["auto_certifiable"] else f"no: {row['reason']}"
        lines.append(
            "| {question_id} | {point_id} | {label} | {decision} | {source_type} | {source_file} | {quote} | {auto_reason} |".format(
                question_id=row["question_id"],
                point_id=row["point_id"],
                label=labels[(row["question_id"], row["point_id"])].replace("|", "\\|"),
                decision=row["decision"],
                source_type=selected.get("source_type", ""),
                source_file=Path(selected.get("source_file", "")).name.replace("|", "\\|"),
                quote=str(selected.get("quote", "")).replace("|", "\\|"),
                auto_reason=auto_reason.replace("|", "\\|"),
            )
        )
    path.write_text("\n".join(lines) + "\n", "utf-8")


def _write_finding(path: Path, impact: dict[str, Any]) -> None:
    text = f"""# FINDING case rubric source lookup 20260604

1. 输入 still_weak：{impact['input_still_weak_count']} 点。
2. textbook verified 新增：{impact['textbook_verified_new']} 点。
3. standard verified candidate：{impact['standard_verified_candidate']} 点。
4. official weak：{impact['official_weak']} 点。
5. source_gap：{impact['source_gap']} 点。
6. 新增 auto_certifiable：{impact['new_auto_certifiable_points']} 点。
7. backfill+source_lookup 累计 auto_certifiable：{impact['cumulative_auto_certifiable_points']} 点。
8. 是否让更多题进入 published_candidate_not_final：{impact['published_candidate_not_final_count']} 题保持/进入 candidate；本轮没有正式 publish。
9. 是否生成正式 registry：NO。
10. 是否伪造 source_ref：NO。
11. 是否把 official_answer 当强锚：NO。
12. 下一步建议：继续 source lookup/官方条文补源；若仍只有 official weak，则进入 PO/专家复核或放弃这些 auto 点，再跑 LLM Jury extraction。

## Scope Guard

- 未新增 DB 表。
- 未生成正式 registry。
- 未接 production runtime。
- 未改 CaseGradingSkillKernel。
- 未让 RAG 进入评分 authority。
"""
    path.write_text(text, "utf-8")


def build_source_lookup_artifacts(out_dir: Path = OUT_DIR, backfill_dir: Path = BACKFILL_DIR) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    _clean_json_dir(out_dir / "audit_packets_source_lookup")
    worklist = build_still_weak_worklist(backfill_dir)
    results = build_source_lookup_results(worklist, backfill_dir)
    packets = _apply_lookup_to_packets(_load_backfill_packets(backfill_dir), results)
    backfill_impact = _read_json(backfill_dir / "registry_impact_after_backfill.json")
    impact = _registry_impact(results, packets, backfill_impact)

    for packet in packets:
        _write_json(out_dir / "audit_packets_source_lookup" / f"{packet['question_id']}.json", packet)
    _write_json(out_dir / "still_weak_source_worklist.json", worklist)
    _write_json(out_dir / "source_lookup_results.json", results)
    _write_json(out_dir / "source_lookup_audit.json", _source_lookup_audit(results))
    _write_json(out_dir / "registry_impact_after_source_lookup.json", impact)
    _write_source_ref_policy(out_dir / "source_ref_policy.md")
    _write_source_evidence_table(out_dir / "source_evidence_table.md", worklist, results)
    _write_finding(out_dir / "FINDING_case_rubric_source_lookup_20260604.md", impact)
    return {
        "out_dir": str(out_dir),
        "input_still_weak_count": len(worklist),
        "impact": impact,
    }


if __name__ == "__main__":
    print(json.dumps(build_source_lookup_artifacts(), ensure_ascii=False, indent=2))
