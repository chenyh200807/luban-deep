"""Backfill textbook anchors for M2 draft audit packets.

This script reads the M2 draft packet copies, searches local textbook
``content_markdown`` with strict normalized verbatim matching, and writes a
separate backfill artifact directory. It never overwrites M2 inputs and never
emits a formal registry.
"""
from __future__ import annotations

import copy
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


M2_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_expansion_m2_20260604"
OUT_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_anchor_backfill_20260604"
BOOK_ROOT_CANDIDATES = (
    Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强"),
    Path("/Users/yehongchen/Developer/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强"),
)
NODE_ASSET_CANDIDATES = (
    REPO_ROOT / "artifacts/knowledge_compiler/2026/scoring-point-assets-20260602/scoring_point_assets_by_node.json",
    REPO_ROOT / "artifacts/knowledge_compiler/2026/pytest-scoring-point-assets/scoring_point_assets_by_node.json",
)
LOW_INFORMATION_TERMS = {
    "不妥一",
    "不妥二",
    "正确做法",
    "而非试验员",
    "解析",
    "根据",
    "包括",
    "内容包括",
}
AUTO_SELECT_TERM_SOURCES = {"label", "required_terms", "calculation_spec", "official_answer_span"}


@dataclass(frozen=True)
class TextbookChunk:
    chunk_id: str
    node_code: str
    content_markdown: str
    normalized_content: str
    source_file: str
    page_num: int | None


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
    text = text.translate(table).lower()
    return re.sub(r"[\s,.;:!?\"'`·、，。；：（）()\[\]{}<>《》【】_-]+", "", text)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _book_files(book_root: Path) -> list[Path]:
    return sorted(book_root.glob("FINAL_CLEANED_BOOK2026-*_fixed.json"))


def _load_textbook_chunks() -> list[TextbookChunk]:
    book_root = _first_existing(BOOK_ROOT_CANDIDATES)
    if not book_root:
        return []
    chunks: list[TextbookChunk] = []
    for source_path in _book_files(book_root):
        data = _read_json(source_path)
        for block in data.get("content_blocks") or []:
            taxonomy = block.get("taxonomy") or {}
            content = str(block.get("content_markdown") or "")
            chunk_id = str(block.get("chunk_id") or "")
            if not chunk_id or not content:
                continue
            chunks.append(
                TextbookChunk(
                    chunk_id=chunk_id,
                    node_code=str(taxonomy.get("node_code") or ""),
                    content_markdown=content,
                    normalized_content=_normalize(content),
                    source_file=str(source_path),
                    page_num=block.get("page_num") if isinstance(block.get("page_num"), int) else None,
                )
            )
    return chunks


def _load_node_assets() -> dict[str, list[str]]:
    path = _first_existing(NODE_ASSET_CANDIDATES)
    if not path:
        return {}
    data = _read_json(path)
    assets: dict[str, list[str]] = {}
    if not isinstance(data, dict):
        return assets
    for node_code, rows in data.items():
        terms: list[str] = []
        if not isinstance(rows, list):
            continue
        for row in rows[:40]:
            label = _clean_text(row.get("label") if isinstance(row, dict) else "")
            if _is_distinctive(label):
                terms.append(label)
            for term in (row.get("required_terms") or []) if isinstance(row, dict) else []:
                term = _clean_text(term)
                if _is_distinctive(term):
                    terms.append(term)
        assets[str(node_code)] = _dedupe_terms(terms)[:20]
    return assets


def _m2_packet_paths(m2_dir: Path = M2_DIR) -> list[Path]:
    return sorted((m2_dir / "audit_packets").glob("M2-*.json"))


def _m2_packets(m2_dir: Path = M2_DIR) -> list[dict[str, Any]]:
    packets = [_read_json(path) for path in _m2_packet_paths(m2_dir)]
    return [p for p in packets if str(p.get("question_id") or "").startswith("M2-")]


def _is_distinctive(term: str) -> bool:
    term = _clean_text(term).strip("：:。.;；,，、")
    normalized = _normalize(term)
    if len(normalized) < 4:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?(?:%|m2|m3|mm|cm|m|d|天|月|个月|万元|元|℃)?", normalized):
        return False
    if term in LOW_INFORMATION_TERMS:
        return False
    if any(stop == term or term.endswith(stop) for stop in LOW_INFORMATION_TERMS):
        return False
    if "不妥" in term or "正确做法" in term or "而非" in term:
        return False
    return True


def _split_terms(text: str) -> list[str]:
    parts = re.split(r"[，。；;、：（）()\[\]\n\r]+", text)
    terms: list[str] = []
    for part in parts:
        part = _clean_text(part).strip(" .。；;：:")
        if 4 <= len(_normalize(part)) <= 42 and _is_distinctive(part):
            terms.append(part)
    numeric_patterns = re.findall(r"\d+(?:\.\d+)?\s*(?:%|m2|m²|㎡|m3|m³|mm|cm|m|d|天|月|个月|万元|元|℃)", text)
    terms.extend(_clean_text(term) for term in numeric_patterns if _is_distinctive(term))
    return _dedupe_terms(terms)


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        key = _normalize(term)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(term)
    return out


def _point_terms(packet: dict[str, Any], point: dict[str, Any], node_assets: dict[str, list[str]]) -> list[dict[str, str]]:
    terms: list[dict[str, str]] = []

    def add_many(values: list[str], source: str) -> None:
        for value in values:
            value = _clean_text(value)
            if _is_distinctive(value):
                terms.append({"term": value, "seed_source": source})

    add_many([point.get("label") or ""], "label")
    add_many([str(t) for t in point.get("required_terms") or []], "required_terms")
    calc = point.get("calculation_spec") or {}
    if isinstance(calc, dict):
        add_many([calc.get("expected_expression_or_value") or ""], "calculation_spec")
    for ref in point.get("source_refs") or []:
        if ref.get("source_type") == OFFICIAL_ANSWER:
            add_many([ref.get("textbook_quote") or ""], "official_answer_span")
    add_many(_split_terms(packet.get("official_answer") or ""), "official_answer_phrase")
    node_code = str(packet.get("node_code") or "")
    if node_code in node_assets:
        add_many(node_assets[node_code], "node_asset")
    return _dedupe_term_rows(terms)[:16]


def _dedupe_term_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        key = _normalize(row.get("term") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def build_weak_anchor_worklist(m2_dir: Path = M2_DIR) -> list[dict[str, Any]]:
    node_assets = _load_node_assets()
    worklist: list[dict[str, Any]] = []
    for packet in _m2_packets(m2_dir):
        node_code = str(packet.get("node_code") or "")
        for point in packet.get("scoring_points") or []:
            refs = point.get("source_refs") or []
            already_verified = any(
                ref.get("source_type") == TEXTBOOK
                and ref.get("chunk_id")
                and ref.get("textbook_quote")
                and ref.get("verified")
                and ref.get("match_method") == "verbatim"
                for ref in refs
            )
            if already_verified:
                continue
            worklist.append(
                {
                    "question_id": packet["question_id"],
                    "point_id": point["point_id"],
                    "node_code": node_code,
                    "label": point.get("label") or "",
                    "required_terms": point.get("required_terms") or [],
                    "official_answer_span": (refs[0].get("textbook_quote") if refs else "") or "",
                    "current_anchor_status": "weak",
                    "search_terms": _point_terms(packet, point, node_assets),
                }
            )
    return worklist


def _chunks_for_scope(chunks: list[TextbookChunk], node_code: str, scope: str) -> list[TextbookChunk]:
    if scope == "node" and node_code and node_code != "unknown":
        return [c for c in chunks if c.node_code == node_code]
    if scope == "parent" and node_code and node_code != "unknown":
        parent = node_code[:5]
        return [c for c in chunks if c.node_code != node_code and c.node_code.startswith(parent)]
    if scope == "full_kb":
        return chunks
    return []


def _hit_for_term(term: str, term_source: str, chunk: TextbookChunk, scope: str) -> dict[str, Any] | None:
    if not _is_distinctive(term):
        return None
    normalized_term = _normalize(term)
    if not normalized_term or normalized_term not in chunk.normalized_content:
        return None
    return {
        "chunk_id": chunk.chunk_id,
        "page_num": chunk.page_num,
        "quote": term,
        "matched_term": term,
        "term_seed_source": term_source,
        "source_file": chunk.source_file,
        "match_type": "verbatim_normalized",
        "normalized_match": True,
        "search_scope": scope,
        "confidence": 1.0,
    }


def _search_point(item: dict[str, Any], chunks: list[TextbookChunk]) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    selected_scope = "full_kb"
    for scope in ("node", "parent", "full_kb"):
        scoped_chunks = _chunks_for_scope(chunks, item.get("node_code") or "", scope)
        if not scoped_chunks:
            continue
        for term_row in item.get("search_terms") or []:
            term = term_row.get("term") or ""
            seed_source = term_row.get("seed_source") or "unknown"
            for chunk in scoped_chunks:
                hit = _hit_for_term(term, seed_source, chunk, scope)
                if not hit:
                    continue
                hits.append(hit)
                if selected is None and seed_source in AUTO_SELECT_TERM_SOURCES:
                    selected = hit
                    selected_scope = scope
                    break
            if selected is not None:
                break
        if selected is not None:
            break
    decision = "verified" if selected else "still_weak"
    reason = (
        "strict normalized content_markdown match"
        if selected
        else "no distinctive term matched textbook content_markdown verbatim"
    )
    return {
        "question_id": item["question_id"],
        "point_id": item["point_id"],
        "node_code": item["node_code"],
        "search_scope": selected_scope,
        "hits": hits[:20],
        "selected_hit": selected,
        "decision": decision,
        "reason": reason,
    }


def build_textbook_anchor_search_results(worklist: list[dict[str, Any]], chunks: list[TextbookChunk] | None = None) -> list[dict[str, Any]]:
    chunks = chunks if chunks is not None else _load_textbook_chunks()
    return [_search_point(item, chunks) for item in worklist]


def _source_ref_from_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": TEXTBOOK,
        "chunk_id": hit["chunk_id"],
        "textbook_quote": hit["quote"],
        "verified": True,
        "match_method": "verbatim",
        "normalized_match": True,
        "source_file": hit.get("source_file") or "",
    }


def _backfill_packets(packets: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(row["question_id"], row["point_id"]): row for row in results}
    backfilled: list[dict[str, Any]] = []
    for packet in packets:
        packet_copy = copy.deepcopy(packet)
        auto_count = 0
        verified_anchor_count = 0
        for point in packet_copy.get("scoring_points") or []:
            result = by_key.get((packet_copy["question_id"], point["point_id"]))
            if result and result["decision"] == "verified" and result.get("selected_hit"):
                point["source_refs"] = [_source_ref_from_hit(result["selected_hit"])]
                point["source_status"] = "verified_textbook"
                point["auto_certifiable"] = True
                point["review_required"] = False
                point["anchor_backfill"] = {
                    "status": "verified",
                    "source": "content_markdown",
                    "selected_scope": result["selected_hit"]["search_scope"],
                    "published_candidate_not_final": True,
                }
                auto_count += 1
                verified_anchor_count += 1
            else:
                point["auto_certifiable"] = False
                point["review_required"] = True
                point["anchor_backfill"] = {
                    "status": "still_weak",
                    "source": "none",
                    "published_candidate_not_final": False,
                }
        if auto_count:
            packet_copy["artifact_status"] = "published"
            packet_copy["artifact_candidate_status"] = "published_candidate_not_final"
        else:
            packet_copy["artifact_status"] = "draft"
            packet_copy["artifact_candidate_status"] = "draft_candidate"
        packet_copy["textbook_anchor_evidence"] = [
            ref for point in packet_copy.get("scoring_points") or [] for ref in point.get("source_refs") or []
        ]
        packet_copy["quality_gate"] = {
            **(packet_copy.get("quality_gate") or {}),
            "auto_certifiable_point_count": auto_count,
            "verified_textbook_anchor_count": verified_anchor_count,
            "published_candidate_not_final": bool(auto_count),
            "blocked_reasons": (
                ["formal_registry_not_emitted", "needs_po_or_human_review_before_registry_v1"]
                if auto_count
                else ["still_weak_anchors", "formal_registry_not_emitted", "needs_textbook_or_human_review"]
            ),
        }
        packet_copy.setdefault("provenance", {})["anchor_backfilled_at"] = datetime.now(timezone.utc).isoformat()
        packet_copy["provenance"]["anchor_backfill_builder"] = "scripts/build_luban_case_rubric_anchor_backfill.py"
        violations = validate_audit_packet(packet_copy)
        if violations:
            raise ValueError(f"invalid backfilled packet {packet_copy['question_id']}: {violations}")
        backfilled.append(packet_copy)
    return backfilled


def _anchor_audit(backfilled_packets: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    by_key = {(row["question_id"], row["point_id"]): row for row in results}
    rows: list[dict[str, Any]] = []
    for packet in backfilled_packets:
        for point in packet.get("scoring_points") or []:
            result = by_key[(packet["question_id"], point["point_id"])]
            hit = result.get("selected_hit")
            status = "verified" if hit else "still_weak"
            rows.append(
                {
                    "question_id": packet["question_id"],
                    "point_id": point["point_id"],
                    "node_code": packet.get("node_code") or "",
                    "policy_type": point.get("policy_type") or "",
                    "anchor_status": status,
                    "chunk_id": hit["chunk_id"] if hit else "",
                    "textbook_quote": hit["quote"] if hit else "",
                    "normalized_match": bool(hit),
                    "auto_certifiable": bool(point.get("auto_certifiable")),
                    "search_scope": hit["search_scope"] if hit else result.get("search_scope"),
                    "reason": result["reason"],
                }
            )
    return {"point_anchor_audit": rows, "summary": dict(Counter(row["anchor_status"] for row in rows))}


def _registry_impact(backfilled_packets: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    point_rows = [point for packet in backfilled_packets for point in packet.get("scoring_points") or []]
    scope_counter = Counter(
        (row.get("selected_hit") or {}).get("search_scope")
        for row in results
        if row.get("decision") == "verified" and row.get("selected_hit")
    )
    return {
        "simulation_only": True,
        "formal_registry_emitted": False,
        "weak_worklist_count": len(results),
        "verified_count": sum(1 for row in results if row["decision"] == "verified"),
        "still_weak_count": sum(1 for row in results if row["decision"] == "still_weak"),
        "blocked_count": sum(1 for row in results if row["decision"] == "blocked"),
        "verified_by_scope": dict(scope_counter),
        "new_auto_certifiable_points": sum(1 for point in point_rows if point.get("auto_certifiable")),
        "published_candidate_not_final_count": sum(
            1 for packet in backfilled_packets if packet.get("artifact_candidate_status") == "published_candidate_not_final"
        ),
        "draft_candidate_count": sum(1 for packet in backfilled_packets if packet.get("artifact_candidate_status") == "draft_candidate"),
    }


def _write_evidence_samples(path: Path, results: list[dict[str, Any]]) -> None:
    lines = [
        "# Anchor Evidence Samples",
        "",
        "| question_id | point_id | node_code | search_term | selected chunk_id | textbook_quote | normalized_match | decision |",
        "|---|---:|---|---|---|---|---:|---|",
    ]
    sample_rows = sorted(results, key=lambda row: (row["decision"] != "verified", row["question_id"], row["point_id"]))[:8]
    for row in sample_rows:
        hit = row.get("selected_hit")
        first_term = ""
        if hit:
            first_term = hit.get("matched_term") or ""
        elif row.get("hits"):
            first_term = row["hits"][0].get("matched_term") or ""
        lines.append(
            "| {question_id} | {point_id} | {node_code} | {term} | {chunk_id} | {quote} | {match} | {decision} |".format(
                question_id=row["question_id"],
                point_id=row["point_id"],
                node_code=row.get("node_code") or "",
                term=first_term.replace("|", "\\|"),
                chunk_id=(hit or {}).get("chunk_id", ""),
                quote=(hit or {}).get("quote", "").replace("|", "\\|"),
                match=str(bool(hit)).lower(),
                decision=row["decision"],
            )
        )
    path.write_text("\n".join(lines) + "\n", "utf-8")


def _write_finding(path: Path, impact: dict[str, Any]) -> None:
    text = f"""# FINDING case rubric anchor backfill 20260604

1. weak worklist：{impact['weak_worklist_count']} 点。
2. verified 成功：{impact['verified_count']} 点。
3. still_weak：{impact['still_weak_count']} 点。
4. blocked：{impact['blocked_count']} 点。
5. verified scope：node={impact['verified_by_scope'].get('node', 0)}，parent={impact['verified_by_scope'].get('parent', 0)}，full_kb={impact['verified_by_scope'].get('full_kb', 0)}。
6. 是否使用 official_answer 冒充教材：NO。official_answer 只生成 search_terms 和 weak fallback，不写 verified source_ref。
7. 是否使用 node asset 冒充题目 rubric：NO。node asset 只作 search seed，verified source_ref 只来自 textbook content_markdown。
8. backfill 后新增 auto_certifiable points：{impact['new_auto_certifiable_points']}。
9. backfill 后 published_candidate_not_final：{impact['published_candidate_not_final_count']} 题。
10. 是否能解锁 registry v1：不能直接解锁。本轮只生成 backfilled draft/published candidates 和 simulation；正式 registry v1 仍需 PO/人工或 LLM Jury 复核、source_ref 审计、registry builder gate。
11. 下一步建议：先对 still_weak 点做人工 source lookup/官方条文补源，再跑 LLM Jury rubric extraction；不要先采更多题稀释 blocker。

## Scope Guard

- 未新增 DB 表。
- 未生成正式 registry v1。
- 未改 CaseGradingSkillKernel。
- 未让 RAG 进入评分 authority。
- 未覆盖原 M2 audit packet。
"""
    path.write_text(text, "utf-8")


def build_anchor_backfill_artifacts(out_dir: Path = OUT_DIR, m2_dir: Path = M2_DIR) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    _clean_json_dir(out_dir / "audit_packets_backfilled")

    packets = _m2_packets(m2_dir)
    worklist = build_weak_anchor_worklist(m2_dir)
    chunks = _load_textbook_chunks()
    results = build_textbook_anchor_search_results(worklist, chunks)
    backfilled_packets = _backfill_packets(packets, results)
    anchor_audit = _anchor_audit(backfilled_packets, results)
    impact = _registry_impact(backfilled_packets, results)

    for packet in backfilled_packets:
        _write_json(out_dir / "audit_packets_backfilled" / f"{packet['question_id']}.json", packet)
    _write_json(out_dir / "weak_anchor_worklist.json", worklist)
    _write_json(out_dir / "textbook_anchor_search_results.json", results)
    _write_json(out_dir / "textbook_anchor_audit_backfilled.json", anchor_audit)
    _write_json(out_dir / "registry_impact_after_backfill.json", impact)
    _write_evidence_samples(out_dir / "anchor_evidence_samples.md", results)
    _write_finding(out_dir / "FINDING_case_rubric_anchor_backfill_20260604.md", impact)
    return {
        "out_dir": str(out_dir),
        "weak_worklist_count": len(worklist),
        "verified_count": impact["verified_count"],
        "still_weak_count": impact["still_weak_count"],
        "published_candidate_not_final_count": impact["published_candidate_not_final_count"],
    }


if __name__ == "__main__":
    print(json.dumps(build_anchor_backfill_artifacts(), ensure_ascii=False, indent=2))
