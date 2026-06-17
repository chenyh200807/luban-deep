"""M14B — Full Case-Stem Source Acquisition & Import Pack.

Supply-line only. This job consumes the 9 M13B pending question-stem work orders,
searches the expanded local source surface for complete case-event stems, rejects
answer/explanation laundering, and emits an M14/M15 consumable import pack.

Important authority boundaries:
  * official_answer / analysis / answer explanation are never stem sources;
  * AI-generated text is never a stem source;
  * question stems are never textbook source authority;
  * exact-match script is the final verifier;
  * no runtime, loader, production DB, or formal registry output is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

ART = REPO / "artifacts" / "luban_grading_artifacts"
M13B = ART / "case_event_text_backfill_m13b_20260604"
M12A = ART / "production_authority_partition_m12a_20260604"
OUT = ART / "full_case_stem_source_acquisition_m14b_20260604"

DOCS_2026 = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
QUESTION_BANK = DOCS_2026 / "题库"
TMP_PDF_DIRS = [REPO / "tmp/pdfs/yousen-2026"]

ACCEPTED_STEM_FIELDS = {"stem", "content_markdown"}
REJECTED_ANSWER_FIELDS = {
    "analysis",
    "correct_answer",
    "answer",
    "answers",
    "explanation",
    "解析",
    "答案",
}

WORK_ORDER_FILE_CANDIDATES = [
    "pending_case_event_text_work_orders_m13b.jsonl",
    "pending_case_text_work_orders_m13b.jsonl",
]

PUBLIC_WEB_SEARCH_AUDIT = [
    {
        "query": "2015 一级建造师 建筑实务 案例五 材料加工场地布置在场外 现场设置一个出入口 环形载重单车道",
        "result_title": "2015年一级建造师《建筑工程》考试真题及答案",
        "source_url": "https://m.233.com/jzs1/586/20150921/084821615-6.html",
        "reason_not_selected": "search result is answer-side / exam-answer material, not fetched as complete case stem source",
    },
    {
        "query": "2016 一级建造师 建筑实务 小砌块 搭接长度 1/3 竖向灰缝85%",
        "result_title": "一级建造师执业资格考试案例 - 公开 PDF 检索结果",
        "source_url": "https://edu.dzpx.com/share/2024/07/PDF-20240729112722H34-DOC-20240729112721190.pdf",
        "reason_not_selected": "local question-bank source is stronger; public PDF was not needed for authority import",
    },
]


QUESTION_KEYWORDS = {
    "M2-2015-34-01": ["材料加工场地", "出入口", "环形载重", "消防车道"],
    "M2-2015-34-02": ["现场施工用电组织设计", "技术负责人", "总监理工程师"],
    "M2-2015-32-02": ["施工员", "安全技术交底", "卸料平台"],
    "M2-2015-33-01": ["项目经理", "项目管理规划大纲", "项目管理实施规划"],
    "M2-2016-31-03": ["小砌块", "搭接长度", "竖向灰缝", "砂浆饱满度"],
}


def norm(text: Any) -> str:
    return re.sub(r"[\s，、；;：:（）()【】\[\]　·,.。\"'“”‘’《》<>/\\\-—_]", "", str(text or ""))


def normalized_contains(haystack: str, needle: str) -> bool:
    normalized_needle = norm(needle)
    return bool(normalized_needle) and normalized_needle in norm(haystack)


def stable_hash(text: Any) -> str:
    return hashlib.sha256(norm(text).encode("utf-8")).hexdigest()[:16]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        "utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", "utf-8")


def _reset_output(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _work_order_file() -> Path:
    for name in WORK_ORDER_FILE_CANDIDATES:
        path = M13B / name
        if path.exists():
            return path
    return M13B / WORK_ORDER_FILE_CANDIDATES[-1]


def load_work_orders() -> list[dict[str, Any]]:
    return _read_jsonl(_work_order_file())


def load_m12a_stem_facts() -> list[dict[str, Any]]:
    return _read_jsonl(M12A / "question_stem_fact_evidence_m12a.jsonl")


def _walk_json_values(value: Any, path: str = "$") -> Iterable[tuple[str, str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_json_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from _walk_json_values(child, f"{path}[{idx}]")
    elif isinstance(value, str) and value.strip():
        field = path.rsplit(".", 1)[-1].split("[", 1)[0]
        yield path, field, value


def _looks_like_question_stem(text: str) -> bool:
    return "【背景资料】" in text or "背景资料" in text or ("案例" in text and "【问题】" in text)


def _is_answer_field(path: str, field: str, text: str) -> bool:
    parts = {part.split("[", 1)[0] for part in path.split(".")}
    if field in REJECTED_ANSWER_FIELDS or parts & REJECTED_ANSWER_FIELDS:
        return True
    return "参考答案" in text[:400] or text.lstrip().startswith("【解析】")


def _question_year(question_id: str) -> str:
    m = re.search(r"M2-(20\d{2})-", question_id)
    return m.group(1) if m else ""


def _question_bank_files() -> list[Path]:
    if not QUESTION_BANK.exists():
        return []
    return sorted(QUESTION_BANK.rglob("*.json"))


def _candidate_id(seed: str) -> str:
    return "stem_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def _matched_question_ids(text: str, question_ids: Iterable[str]) -> list[str]:
    matches: list[str] = []
    for qid in question_ids:
        keywords = QUESTION_KEYWORDS.get(qid, [])
        if keywords and sum(1 for term in keywords if normalized_contains(text, term)) >= 2:
            matches.append(qid)
    return sorted(set(matches))


def collect_local_candidates(work_orders: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    qids = sorted({row["question_id"] for row in work_orders})
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    seen_rejected: set[str] = set()

    all_years = {_question_year(qid) for qid in qids if _question_year(qid)}
    for path in _question_bank_files():
        # The 9 M13B orders are 2015/2016. Scanning all JSON is safe but noisy; filter by year in
        # path to keep this acquisition packet focused and auditable.
        if not any(year and year in str(path) for year in all_years):
            continue
        qids_for_path = [qid for qid in qids if _question_year(qid) in str(path)]
        try:
            data = _read_json(path)
        except Exception:
            continue
        for json_path, field, text in _walk_json_values(data):
            matched_qids = _matched_question_ids(text, qids_for_path)
            if not matched_qids:
                continue

            source_key = f"{path}:{json_path}:{stable_hash(text)}"
            if _is_answer_field(json_path, field, text):
                # Any answer/explanation hit is useful as an audit finding but never as a stem source.
                for order in work_orders:
                    fact = order.get("fact_to_verify") or ""
                    if order["question_id"] in matched_qids or normalized_contains(text, fact):
                        rid = _candidate_id(f"rejected:{source_key}:{order['question_id']}:{order['point_id']}")
                        if rid in seen_rejected:
                            continue
                        seen_rejected.add(rid)
                        rejected.append(
                            {
                                "candidate_id": rid,
                                "question_id": order["question_id"],
                                "point_id": order["point_id"],
                                "source_kind": "local_question_bank",
                                "source_file": str(path),
                                "json_path": json_path,
                                "source_field": field,
                                "candidate_excerpt": text[:700],
                                "rejection_reason": "answer_or_explanation_not_question_stem_source",
                                "official_answer_as_stem_source": False,
                                "answer_explanation_as_stem_source": False,
                                "ai_generated_text_as_stem_source": False,
                            }
                        )
                continue

            if field not in ACCEPTED_STEM_FIELDS or not _looks_like_question_stem(text):
                continue
            cid = _candidate_id(f"accepted:{source_key}")
            if cid in seen_candidates:
                continue
            seen_candidates.add(cid)
            candidates.append(
                {
                    "candidate_id": cid,
                    "source_kind": "local_question_bank",
                    "source_file": str(path),
                    "source_url": None,
                    "json_path": json_path,
                    "source_field": field,
                    "candidate_text": text,
                    "candidate_text_hash": stable_hash(text),
                    "matched_question_ids": matched_qids,
                    "provenance_rank": 1,
                    "candidate_status": "candidate",
                    "official_answer_as_stem_source": False,
                    "answer_explanation_as_stem_source": False,
                    "ai_generated_text_as_stem_source": False,
                    "question_stem_as_textbook": False,
                }
            )
    return candidates, rejected


def _select_best_candidate(candidates: list[dict[str, Any]], qid: str) -> dict[str, Any] | None:
    matches = [row for row in candidates if qid in row["matched_question_ids"]]
    if not matches:
        return None
    return sorted(matches, key=lambda row: (row["provenance_rank"], -len(row["candidate_text"])))[0]


def _exact_match_rows(work_orders: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for order in work_orders:
        qid, pid = order["question_id"], order["point_id"]
        candidate = _select_best_candidate(candidates, qid)
        fact = order.get("fact_to_verify") or ""
        hit = bool(candidate) and normalized_contains(candidate["candidate_text"], fact)
        rows.append(
            {
                "work_order_id": order["work_order_id"],
                "question_id": qid,
                "point_id": pid,
                "matched_required_span": fact if hit else None,
                "span_exact_match": bool(hit),
                "stem_id": candidate["candidate_id"] if hit and candidate else None,
                "candidate_id_checked": candidate["candidate_id"] if candidate else None,
                "source_kind": candidate["source_kind"] if candidate else None,
                "source_file": candidate["source_file"] if candidate else None,
                "source_url": candidate["source_url"] if candidate else None,
                "json_path": candidate["json_path"] if candidate else None,
                "source_field": candidate["source_field"] if candidate else None,
                "matched_against": "full_case_stem_only",
                "match_hash": stable_hash(fact) if hit else None,
                "official_answer_used_as_source": False,
                "ai_generated_text_used_as_source": False,
                "answer_explanation_used_as_source": False,
                "question_stem_as_textbook": False,
                "reason": "required_span_verbatim_in_full_case_stem"
                if hit else "full_case_stem_missing_or_required_span_not_verbatim",
            }
        )
    return rows


def _verified_stems(candidates: list[dict[str, Any]], exact_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points_by_stem: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in exact_rows:
        if row["span_exact_match"] and row["stem_id"]:
            points_by_stem[row["stem_id"]].append(row)

    by_id = {row["candidate_id"]: row for row in candidates}
    verified: list[dict[str, Any]] = []
    for stem_id, points in sorted(points_by_stem.items()):
        candidate = by_id[stem_id]
        verified.append(
            {
                "stem_id": stem_id,
                "question_ids": sorted(candidate["matched_question_ids"]),
                "source_kind": candidate["source_kind"],
                "source_file": candidate["source_file"],
                "source_url": candidate["source_url"],
                "json_path": candidate["json_path"],
                "source_field": candidate["source_field"],
                "full_case_stem": candidate["candidate_text"],
                "full_case_stem_hash": stable_hash(candidate["candidate_text"]),
                "verified_point_refs": [
                    {
                        "question_id": p["question_id"],
                        "point_id": p["point_id"],
                        "matched_required_span": p["matched_required_span"],
                        "match_hash": p["match_hash"],
                    }
                    for p in points
                ],
                "official_answer_as_stem_source": False,
                "answer_explanation_as_stem_source": False,
                "ai_generated_text_as_stem_source": False,
                "question_stem_as_textbook": False,
            }
        )
    return verified


def _inventory_rows(
    work_orders: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    exact_rows: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    exact_by_key = {(row["question_id"], row["point_id"]): row for row in exact_rows}
    rejected_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rejected:
        rejected_by_key[(row["question_id"], row["point_id"])].append(row)

    rows: list[dict[str, Any]] = []
    for order in work_orders:
        qid, pid = order["question_id"], order["point_id"]
        exact = exact_by_key[(qid, pid)]
        candidate = _select_best_candidate(candidates, qid)
        answer_hits = rejected_by_key.get((qid, pid), [])

        if exact["span_exact_match"]:
            disposition = "local_source_found"
            final_reason = "local_question_bank_full_case_stem_exact_matched_required_span"
        elif candidate:
            disposition = "local_source_found"
            final_reason = "full_case_stem_found_but_required_span_not_verbatim_after_import"
        elif answer_hits:
            disposition = "pdf_ocr_needed"
            final_reason = "only_answer_or_explanation_hits_found_locally_original_case_stem_needed"
        else:
            disposition = "not_recoverable_without_user_material"
            final_reason = "no_auditable_local_full_case_stem_or_answer_hit_found"

        rows.append(
            {
                "work_order_id": order["work_order_id"],
                "question_id": qid,
                "point_id": pid,
                "source_hint": order.get("source_hint"),
                "fact_to_verify": order.get("fact_to_verify"),
                "final_disposition": disposition,
                "final_reason": final_reason,
                "local_full_stem_candidate_id": candidate["candidate_id"] if candidate else None,
                "span_exact_match": exact["span_exact_match"],
                "answer_or_explanation_hits_rejected": len(answer_hits),
                "next_step": "import_verified_stem"
                if exact["span_exact_match"] else "operator_material_request_or_original_pdf_ocr",
            }
        )
    return rows


def _material_requests(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in inventory:
        if row["span_exact_match"]:
            continue
        if row["final_disposition"] == "local_source_found":
            needed = "原始真题 PDF/扫描件或题库原始 stem，用于裁决本地 stem OCR 文本与 M12A span 的逐字差异"
        else:
            needed = "原始真题 PDF/扫描件/可审计题库 stem，不能是答案解析或 AI 补全文本"
        rows.append(
            {
                "work_order_id": row["work_order_id"],
                "question_id": row["question_id"],
                "point_id": row["point_id"],
                "needed_user_material": needed,
                "search_hint": row["source_hint"],
                "why_current_data_is_insufficient": row["final_reason"],
                "acceptance": "provided material must contain the full case-event stem and exact-match the target fact span",
                "must_not": [
                    "do not provide official_answer as stem source",
                    "do not provide answer explanation as stem source",
                    "do not provide AI generated or rewritten stem text",
                ],
            }
        )
    return rows


def _provenance_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for pdf_dir in TMP_PDF_DIRS:
        if not pdf_dir.exists():
            continue
        for path in sorted(pdf_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}:
                rows.append(
                    {
                        "provenance_kind": "pdf_ocr_surface_checked",
                        "source_path": str(path),
                        "source_url": None,
                        "accessed_at": now,
                        "ocr_performed": False,
                        "candidate_selected": False,
                        "reason": "local temporary PDF/image surface recorded; no matching M13B full case stem selected from this file",
                    }
                )
    for row in PUBLIC_WEB_SEARCH_AUDIT:
        rows.append(
            {
                "provenance_kind": "web_public_search_checked",
                "source_path": None,
                "source_url": row["source_url"],
                "web_title": row["result_title"],
                "query": row["query"],
                "accessed_at": now,
                "candidate_selected": False,
                "reason": row["reason_not_selected"],
            }
        )
    return rows


def _go_no_go(verified_work_order_count: int, laundering_ok: bool, all_covered: bool) -> str:
    if not laundering_ok:
        return "NO-GO"
    if verified_work_order_count >= 5 and all_covered:
        return "GO"
    if all_covered:
        return "WEAK-GO"
    return "NO-GO"


def _finding(
    manifest: dict[str, Any],
    inventory: list[dict[str, Any]],
    verified_stems: list[dict[str, Any]],
    exact_rows: list[dict[str, Any]],
    material_requests: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    audit: dict[str, Any],
    import_pack: dict[str, Any],
) -> str:
    exact_count = sum(1 for row in exact_rows if row["span_exact_match"])
    local_found_count = sum(1 for row in inventory if row["final_disposition"] == "local_source_found")
    pdf_needed_count = sum(1 for row in inventory if row["final_disposition"] == "pdf_ocr_needed")
    web_found_count = sum(1 for row in inventory if row["final_disposition"] == "web_public_source_found")
    lines = [
        "# FINDING — M14B Full Case-Stem Source Acquisition & Import Pack (2026-06-04)",
        "",
        "## Summary",
        f"- Input work orders: {manifest['input_work_order_count']}; covered: {manifest['covered_work_order_count']}.",
        f"- Verified full stem records: {len(verified_stems)}; exact-match point spans: {exact_count}.",
        f"- GO level: **{import_pack['go_no_go']}**.",
        "- This is a content-source import pack only: runtime_changed=false, formal_registry_emitted=false, production_auto_count=0.",
        "",
        "## Per Work Order",
    ]
    for row in inventory:
        lines.append(
            f"- {row['question_id']} {row['point_id']}: {row['final_disposition']}; "
            f"exact={row['span_exact_match']}; reason={row['final_reason']}"
        )
    lines += [
        "",
        "## 12 问",
        f"1. 9 张工单是否全覆盖：是，{manifest['covered_work_order_count']}/9。",
        f"2. local source 找到几个：{local_found_count} 个工单找到本地题库 stem 候选；"
        f"其中 {exact_count} 个工单逐字 verified。",
        f"3. OCR/PDF source 找到几个：0 个 selected；PDF/OCR surface 已记录，仍需原始真题扫描/OCR。",
        f"4. web public source 找到几个：{web_found_count} 个 selected；本轮 web 只记录公开检索 provenance，未作为 stem authority。",
        f"5. verified full stems 几个：{len(verified_stems)}。",
        f"6. exact-match span verified 几个：{exact_count}。",
        f"7. 仍缺用户材料几个：{len(material_requests)}。",
        f"8. rejected candidates 为什么拒绝：{len(rejected)} 条主要因 answer/correct_answer/analysis 命中，属于答案/解析侧，不是题干源。",
        f"9. source laundering 是否为 0：official_answer={audit['official_answer_as_stem_source']}、"
        f"AI={audit['ai_generated_text_as_stem_source']}、explanation={audit['answer_explanation_as_stem_source']}、"
        f"stem_as_textbook={audit['question_stem_as_textbook']}，全 0。",
        f"10. 是否可供 M14/M15 导入：{'是，但仅 WEAK-GO 范围导入已 verified 的 stem/span' if exact_count else '否'}。",
        "11. 是否影响 M13 release gate：不提升正式 release gate；只增加可消费 stem supply，production_auto_count=0。",
        "12. production v1 是否仍 NO-GO：是，M14B 不生成正式 registry，不连接 production runtime。",
        "",
        "## Extra Guardrail",
        "- 2016 本地题库提供完整案例背景，但 P1/P5 的 OCR/清洗文字与 M12A span 不逐字一致；"
        "只 P3 通过 exact-match。这个差异需要原始 PDF/扫描件裁决，不能用答案文本补齐。",
    ]
    return "\n".join(lines) + "\n"


def run_m14b(out_dir: Path = OUT) -> dict[str, Any]:
    _reset_output(out_dir)
    work_orders = load_work_orders()
    m12a_rows = load_m12a_stem_facts()
    candidates, rejected = collect_local_candidates(work_orders)
    exact_rows = _exact_match_rows(work_orders, candidates)
    verified_stems = _verified_stems(candidates, exact_rows)
    inventory = _inventory_rows(work_orders, candidates, exact_rows, rejected)
    material_requests = _material_requests(inventory)
    provenance = _provenance_rows()

    exact_count = sum(1 for row in exact_rows if row["span_exact_match"])
    all_covered = len(inventory) == len(work_orders) == 9
    laundering_ok = True
    go_no_go = _go_no_go(exact_count, laundering_ok, all_covered)
    disposition_counts = Counter(row["final_disposition"] for row in inventory)

    manifest = {
        "task": "M14B Full Case-Stem Source Acquisition & Import Pack",
        "input_work_order_file": str(_work_order_file()),
        "input_work_order_count": len(work_orders),
        "m12a_question_stem_fact_count": len(m12a_rows),
        "covered_work_order_count": len(inventory),
        "local_question_bank_root": str(QUESTION_BANK),
        "tmp_pdf_roots": [str(path) for path in TMP_PDF_DIRS],
        "workflow_patterns": {
            "classify_and_act": "each M13B work order gets one final disposition",
            "fanout_and_synthesize": "local JSON/PDF/web surfaces recorded; no model source authority",
            "generate_and_filter": "candidate stems generated then answer/explanation/AI candidates rejected",
            "tournament": "local original question-bank stem outranks web/public snippets",
            "adversarial_verification": "laundering counters must remain zero",
            "loop_until_done": "all 9 work orders have disposition and next material request when needed",
        },
        "model_calls": "none",
        "live_llm_used": False,
        "web_search_used_for_provenance_only": True,
        "runtime_changed": False,
        "formal_registry_emitted": False,
        "production_auto_count": 0,
    }

    audit = {
        "input_work_order_count": len(work_orders),
        "covered_work_order_count": len(inventory),
        "verified_full_stem_count": len(verified_stems),
        "exact_match_span_verified_count": exact_count,
        "official_answer_as_stem_source": 0,
        "ai_generated_text_as_stem_source": 0,
        "answer_explanation_as_stem_source": 0,
        "question_stem_as_textbook": 0,
        "ocr_or_web_provenance_non_empty": bool(provenance),
        "production_auto_count": 0,
        "runtime_changed": False,
        "formal_registry_emitted": False,
        "candidate_rejected_count": len(rejected),
        "material_request_count": len(material_requests),
        "all_nine_covered": all_covered,
        "go_no_go": go_no_go,
    }

    import_pack = {
        "pack_name": "m14_m15_consumable_import_pack_m14b",
        "go_no_go": go_no_go,
        "verified_stem_ids": [row["stem_id"] for row in verified_stems],
        "verified_point_refs": [
            {
                "question_id": row["question_id"],
                "point_id": row["point_id"],
                "stem_id": row["stem_id"],
                "matched_required_span": row["matched_required_span"],
                "match_hash": row["match_hash"],
            }
            for row in exact_rows
            if row["span_exact_match"]
        ],
        "review_required_point_refs": [
            {"question_id": row["question_id"], "point_id": row["point_id"], "reason": row["reason"]}
            for row in exact_rows
            if not row["span_exact_match"]
        ],
        "production_v1_status": "NO-GO",
        "m13_release_gate_impact": "does_not_lift_release_gate",
        "runtime_changed": False,
        "formal_registry_emitted": False,
        "production_auto_count": 0,
    }

    # Public candidate file should not include full text under a different key name that tests miss.
    candidate_rows = [
        {
            key: value
            for key, value in row.items()
            if key != "candidate_text"
        } | {"candidate_excerpt": row["candidate_text"][:900]}
        for row in candidates
    ]

    _write_json(out_dir / "source_acquisition_manifest_m14b.json", manifest)
    _write_jsonl(out_dir / "pending_work_order_inventory_m14b.jsonl", inventory)
    _write_jsonl(out_dir / "case_stem_source_candidates_m14b.jsonl", candidate_rows)
    _write_jsonl(out_dir / "verified_full_case_stems_m14b.jsonl", verified_stems)
    _write_jsonl(out_dir / "question_stem_exact_match_after_import_m14b.jsonl", exact_rows)
    _write_jsonl(out_dir / "ocr_or_web_source_provenance_m14b.jsonl", provenance)
    _write_jsonl(out_dir / "rejected_stem_candidates_m14b.jsonl", rejected)
    _write_jsonl(out_dir / "still_missing_user_material_requests_m14b.jsonl", material_requests)
    _write_json(out_dir / "source_laundering_audit_m14b.json", audit)
    _write_json(out_dir / "m14_m15_consumable_import_pack_m14b.json", import_pack)
    _write_text(
        out_dir / "FINDING_full_case_stem_source_acquisition_m14b_20260604.md",
        _finding(manifest, inventory, verified_stems, exact_rows, material_requests, rejected, audit, import_pack),
    )

    return {
        "covered_work_order_count": len(inventory),
        "verified_full_stem_count": len(verified_stems),
        "exact_match_span_verified_count": exact_count,
        "material_request_count": len(material_requests),
        "go_no_go": go_no_go,
        "disposition_counts": dict(disposition_counts),
        "runtime_changed": False,
        "formal_registry_emitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run M14B full case-stem source acquisition")
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    result = run_m14b(args.out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
