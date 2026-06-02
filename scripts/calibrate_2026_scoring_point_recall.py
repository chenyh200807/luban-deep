#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from deeptutor.services.source_compiler.jsonl import write_jsonl
from deeptutor.services.source_compiler.scoring_point_recall_calibration import (
    build_backfill_assets,
    build_kb_term_index,
    build_parent_child_index,
    classify_miss_row,
    measure_case_recall,
    merge_backfill_assets,
    summarize_case_results,
)


DEFAULT_ASSET_DIR = Path("artifacts/knowledge_compiler/2026/scoring-point-assets-20260602")
DEFAULT_GOLDEN = Path("deeptutor/services/benchmark/fixtures/luban_case_grading_golden_no_human_v1_5.json")
DEFAULT_SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_OUTPUT_DIR = Path("artifacts/knowledge_compiler/2026/scoring-point-recall-calibration-v2-backfill-20260602")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_book_chunks(source_root: Path) -> list[dict[str, Any]]:
    book_dir = source_root / "2026教材" / "第二次加强"
    chunks: list[dict[str, Any]] = []
    for path in sorted(book_dir.glob("FINAL_CLEANED_BOOK2026-*_fixed.json")):
        payload = _load_json(path)
        blocks = payload.get("content_blocks") if isinstance(payload, dict) else payload if isinstance(payload, list) else []
        chunks.extend(block for block in blocks if isinstance(block, dict))
    return chunks


def _flatten_rows(case_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for result in case_results for row in result["rows"]]


def _node_gap_rows(case_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in case_results:
        alignment = result["alignment"]
        if alignment["status"].startswith("coverage_gap") or alignment["status"] == "expanded_parent":
            rows.append(
                {
                    "case_id": result["case_id"],
                    "question_node": result["question_node"],
                    "alignment_status": alignment["status"],
                    "asset_nodes": alignment["asset_nodes"],
                    "term_count": len(result["rows"]),
                    "excluded_na_terms": result["summary"]["excluded_na_terms"],
                }
            )
    return rows


def _miss_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": row["case_id"],
            "question_node": row["question_node"],
            "node_alignment_status": row["node_alignment_status"],
            "gold_point_id": row["gold_point_id"],
            "gold_point_type": row["gold_point_type"],
            "gold_term": row["gold_term"],
            "normalized_gold_term": row["normalized_gold_term"],
            "all_kb_hit": row.get("all_kb_hit"),
            "all_kb_matches": row.get("all_kb_matches") or [],
        }
        for row in rows
        if not row["hit"] and row["node_alignment_status"] != "coverage_gap_na"
    ]


def _classify_misses(misses: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kb_index = build_kb_term_index(chunks)
    return [classify_miss_row(row, kb_index) for row in misses]


def _classification_counts(classified: list[dict[str, Any]]) -> dict[str, Any]:
    by_class = Counter(row["class"] for row in classified)
    by_class_and_type: dict[str, dict[str, int]] = {}
    for row in classified:
        class_name = str(row["class"])
        point_type = str(row.get("gold_point_type") or "unknown")
        by_class_and_type.setdefault(class_name, {})
        by_class_and_type[class_name][point_type] = by_class_and_type[class_name].get(point_type, 0) + 1
    return {
        "total": len(classified),
        "by_class": dict(sorted(by_class.items())),
        "by_class_and_point_type": {key: dict(sorted(value.items())) for key, value in sorted(by_class_and_type.items())},
    }


def _backfill_candidates(classified: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in classified:
        if row.get("class") != "asset_absent_but_in_kb":
            continue
        evidence = row.get("evidence") or []
        first = evidence[0] if evidence else {}
        candidates.append(
            {
                "case_id": row.get("case_id"),
                "question_node": row.get("question_node"),
                "gold_point_id": row.get("gold_point_id"),
                "gold_point_type": row.get("gold_point_type"),
                "gold_term": row.get("gold_term"),
                "normalized_gold_term": row.get("normalized_gold_term"),
                "candidate_node_code": first.get("node_code"),
                "candidate_chunk_id": first.get("chunk_id"),
                "candidate_page_num": first.get("page_num"),
                "candidate_quote": first.get("quote"),
                "compiler_action": "recall_candidate_only_no_backfill_in_this_round",
                "precision_guard": "must pass verify-on-write exact content_markdown match and no loose-anchor guard before asset promotion",
            }
        )
    return candidates


def _backfill_verify_audit(backfill_assets: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    chunks_by_id = {
        str(chunk.get("chunk_id") or chunk.get("id") or ""): str(chunk.get("content_markdown") or "")
        for chunk in chunks
    }
    rows: list[dict[str, Any]] = []
    for asset in backfill_assets:
        required_terms = asset.get("required_terms") or []
        required_term = str(required_terms[0] if required_terms else "")
        content = chunks_by_id.get(str(asset.get("chunk_id") or ""), "")
        row = {
            "point_id": asset.get("point_id"),
            "backfill_source": asset.get("backfill_source"),
            "backfill_gold_term": asset.get("backfill_gold_term"),
            "node_code": asset.get("node_code"),
            "chunk_id": asset.get("chunk_id"),
            "page_num": asset.get("page_num"),
            "required_term": required_term,
            "required_term_in_content_markdown": required_term in content,
            "quote_in_content_markdown": str(asset.get("provenance", {}).get("quote") or "") in content,
            "bare_gold_term_only": required_terms == [asset.get("backfill_gold_term")],
            "anchor_source": asset.get("anchor_source"),
        }
        rows.append(row)
    return {
        "asset_count": len(backfill_assets),
        "verify_on_write_failures": [row for row in rows if not row["required_term_in_content_markdown"]],
        "quote_failures": [row for row in rows if not row["quote_in_content_markdown"]],
        "bare_gold_term_only_count": sum(1 for row in rows if row["bare_gold_term_only"]),
        "rows": rows,
    }


def _raw_required_terms(case_results: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    extracted = [row for result in case_results for row in result["rows"]]
    extracted_keys = {
        (
            str(row.get("case_id")),
            str(row.get("gold_point_id")),
            str(row.get("normalized_gold_term")),
        )
        for row in extracted
    }
    raw_total = 0
    kept_raw = 0
    filtered: list[dict[str, Any]] = []
    for case in cases:
        for point in case.get("gold_scoring_points") or []:
            terms = point.get("required_terms_v1_5")
            if not isinstance(terms, list):
                continue
            for term in terms:
                raw_total += 1
                from deeptutor.services.source_compiler.scoring_point_asset_compiler import normalize_for_match

                key = (str(case.get("case_id")), str(point.get("point_id")), normalize_for_match(str(term)))
                if key in extracted_keys:
                    kept_raw += 1
                else:
                    filtered.append(
                        {
                            "case_id": case.get("case_id"),
                            "gold_point_id": point.get("point_id"),
                            "gold_point_type": point.get("point_type"),
                            "raw_term": term,
                            "reason": "filtered_as_stop_or_generic_fragment_or_empty",
                        }
                    )
    return {"raw_required_terms": raw_total, "kept_after_cleaning": kept_raw, "filtered_count": len(filtered), "filtered_terms": filtered}


def _write_markdown(
    output_dir: Path,
    *,
    strict_summary: dict[str, Any],
    expanded_summary: dict[str, Any],
    with_backfill_summary: dict[str, Any],
    with_backfill_expanded_summary: dict[str, Any],
    node_gaps: list[dict[str, Any]],
    misses: list[dict[str, Any]],
    classified: list[dict[str, Any]],
    backfill_candidates: list[dict[str, Any]],
    backfill_assets: list[dict[str, Any]],
    backfill_audit: dict[str, Any],
    seed_note: dict[str, Any],
    denominator_audit: dict[str, Any],
) -> None:
    classification = _classification_counts(classified)
    text = strict_summary.get("by_point_type", {}).get("text_term", {})
    expanded_text = expanded_summary.get("by_point_type", {}).get("text_term", {})
    backfill_text = with_backfill_summary.get("by_point_type", {}).get("text_term", {})
    backfill_expanded_text = with_backfill_expanded_summary.get("by_point_type", {}).get("text_term", {})
    strict_text_hit = int(text.get("term_hit") or 0)
    expanded_text_hit = int(expanded_text.get("term_hit") or 0)
    backfill_text_hit = int(backfill_text.get("term_hit") or 0)
    backfill_expanded_text_hit = int(backfill_expanded_text.get("term_hit") or 0)
    node_lift = expanded_text_hit - strict_text_hit
    backfill_lift = backfill_text_hit - strict_text_hit
    backfill_node_lift = backfill_expanded_text_hit - backfill_text_hit
    lines = [
        "# 2026 采分点资产库 vs 20题 Golden per-term Recall 校准 v2 backfill",
        "",
        "状态：directional / shadow；不进生产门；不接 RAG；不碰 `CaseGradingSkillKernel` runtime authority。",
        "",
        "## 1. 总览",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| cases | {strict_summary['case_count']} |",
        f"| cleaned all-type terms | {strict_summary['term_total']} |",
        f"| cleaned all-type term recall(strict node) | {strict_summary['term_recall']:.4f} |" if strict_summary.get("term_recall") is not None else "| cleaned all-type term recall(strict node) | NA |",
        f"| cleaned text_term terms | {text.get('term_total', 0)} |",
        f"| ① natural text_term recall(strict node) | {text.get('term_recall', 0):.4f} |" if text.get("term_recall") is not None else "| ① natural text_term recall(strict node) | NA |",
        f"| ② natural+backfill text_term recall(strict node) | {backfill_text.get('term_recall', 0):.4f} |" if backfill_text.get("term_recall") is not None else "| ② natural+backfill text_term recall(strict node) | NA |",
        f"| ③ natural+backfill+node-align text_term recall | {backfill_expanded_text.get('term_recall', 0):.4f} |" if backfill_expanded_text.get("term_recall") is not None else "| ③ natural+backfill+node-align text_term recall | NA |",
        f"| natural text_term point recall(all terms hit) | {text.get('point_all_terms_recall', 0):.4f} |" if text.get("point_all_terms_recall") is not None else "| natural text_term point recall(all terms hit) | NA |",
        f"| natural+backfill text_term point recall(all terms hit) | {backfill_text.get('point_all_terms_recall', 0):.4f} |" if backfill_text.get("point_all_terms_recall") is not None else "| natural+backfill text_term point recall(all terms hit) | NA |",
        f"| natural+backfill+node-align point recall(all terms hit) | {backfill_expanded_text.get('point_all_terms_recall', 0):.4f} |" if backfill_expanded_text.get("point_all_terms_recall") is not None else "| natural+backfill+node-align point recall(all terms hit) | NA |",
        f"| node remapping recovered natural text hits | {node_lift} |",
        f"| backfill recovered strict text hits | {backfill_lift} |",
        f"| node-align recovered after backfill text hits | {backfill_node_lift} |",
        f"| excluded NA terms | {strict_summary['excluded_na_terms']} |",
        f"| raw required_terms_v1_5 filtered | {denominator_audit.get('filtered_count')} / {denominator_audit.get('raw_required_terms')} |",
        f"| backfill assets | {len(backfill_assets)} |",
        f"| backfill verify failures | {len(backfill_audit.get('verify_on_write_failures') or [])} |",
        f"| backfill bare-gold-term-only | {backfill_audit.get('bare_gold_term_only_count')} |",
        "",
        "结论：**继续停在 calibration gate**。① 是自然抽取层的泛化诊断；②③ 含 golden-driven backfill，只证明已定位缺口可被教材原文覆盖，不能作为泛化成绩或生产门。",
        "",
        "与 pilot point-level 约 70% 的差异来自三类口径：term 级比 point 级更严、旧分母混入 calculation/figure/non_textbook、strict node scope 不含 parent/sibling 重映射。详见 `truth_metric_comparison.md`。",
        "",
        "## 2. Node 对齐",
        "",
        "strict node scope:",
        "",
        json.dumps(strict_summary.get("alignment_counts"), ensure_ascii=False, indent=2),
        "",
        "parent/sibling offline scope:",
        "",
        json.dumps(expanded_summary.get("alignment_counts"), ensure_ascii=False, indent=2),
        "",
        f"离线 node 重映射在自然层可挽回 text_term hits：{node_lift}；在含 backfill 后还可挽回：{backfill_node_lift}。这只是 alignment 诊断，不是正式 production recall。",
        "",
        "## 3. 三层 recall 分解",
        "",
        "① natural original 6134:",
        "",
        json.dumps(strict_summary.get("by_point_type"), ensure_ascii=False, indent=2),
        "",
        "② natural + golden-driven backfill:",
        "",
        json.dumps(with_backfill_summary.get("by_point_type"), ensure_ascii=False, indent=2),
        "",
        "③ natural + golden-driven backfill + parent/sibling node alignment:",
        "",
        json.dumps(with_backfill_expanded_summary.get("by_point_type"), ensure_ascii=False, indent=2),
        "",
        "NA、父节点展开、缺失 node 详见 `node_alignment_gaps.json`。",
        "",
        "## 4. Miss 三分类",
        "",
        f"未覆盖 gold terms：{len(misses)}。三分类详见 `miss_classification.json`。",
        "",
        json.dumps(classification, ensure_ascii=False, indent=2),
        "",
        "解释：",
        "",
        "- `node_remappable`：term 已在资产库其它 node 中，说明主要是 question_node / taxonomy scope 问题。",
        "- `asset_absent_but_in_kb`：term 在 KB `content_markdown` 原文中，但资产库未抽出，是后续 recall-oriented 补采候选。",
        "- `gold_non_textbook`：KB 原文也没有，疑似官方答案撮写、跨科目、计算、图识别或非教材来源；不能靠教材 text assets 解决。",
        "",
        "## 5. 定向补采层",
        "",
        f"`asset_absent_but_in_kb` 候选数：{len(backfill_candidates)}；生成 backfill assets：{len(backfill_assets)}。详见 `scoring_point_assets_backfill.jsonl`。",
        "",
        "每条 backfill 均为独立层，`anchor_source=textbook_backfill`、`backfill_source=golden_driven_<case_id>_<point_id>`，不覆盖原始 6134 自然抽取层，不改 compiler。",
        "",
        f"verify-on-write failures：{len(backfill_audit.get('verify_on_write_failures') or [])}；bare-gold-term-only：{backfill_audit.get('bare_gold_term_only_count')}。详见 `backfill_verify_audit.json`。",
        "",
        "## 6. seed_total 口径订正",
        "",
        f"- `quality_report.json` seed_total：{seed_note.get('quality_report_seed_total')}，只统计进入非 calculation candidate_terms 路径的 seed。",
        f"- `seed_miss_summary.json` seed_total：{seed_note.get('full_kb_seed_total')}，统计 650 chunk 全部 grading_keywords，包括 rule_numeric 等计算类 chunk。",
        "- 两者都正确，但分母不同；后续报告应显式写成 `seed_total_non_calculation_candidate_path` 与 `seed_total_all_chunks`。",
        "",
        "## 7. Gate",
        "",
        "本结果只回答资产库对 v0 golden 术语的模型内覆盖，不与人类一致性混算，也不代表生产级准确率。",
        "",
        "下一步建议：",
        "",
        "1. Claude 抽样复核 `asset_absent_but_in_kb_terms.json`，重点看 chunk/page 证据是否真在 KB 原文。",
        "2. Claude 抽样复核 `node_remappable_terms.json`，判断 parent/sibling scope 是否可以形成离线对齐规则。",
        "3. 复核通过后，再单独审批是否执行补采；本 harness 到此停 gate。",
    ]
    (output_dir / "FINDING.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_backfill_proposal(output_dir: Path, candidates: list[dict[str, Any]], classification: dict[str, Any]) -> None:
    lines = [
        "# Recall-oriented 补采候选提案",
        "",
        "状态：proposal only；本轮不补采、不改 compiler。",
        "",
        "## 为什么会漏抽",
        "",
        "`asset_absent_but_in_kb` 表示 gold term 已逐字存在于 KB `content_markdown`，但 6134 条资产库未覆盖。可能原因包括：",
        "",
        "- chunk 的 `content_type` 或 seed 未触发该条款进入 candidate path；",
        "- 条款在长句、表格或列举结构中，当前 compiler 未拆成 atomic scoring item；",
        "- term 是 golden 人工精炼后的 distinctive 短语，和 compiler seed 边界不同。",
        "",
        "## 为什么不会破坏 precision guard",
        "",
        "候选不能直接入库。真正补采前必须仍通过：",
        "",
        "- verify-on-write：required term 逐字存在于 `content_markdown`；",
        "- no loose anchor：不允许 ≤3 字高频通用词作为单术语锚；",
        "- provenance：必须写入 chunk_id / page_num / quote / content_hash；",
        "- shadow eval：补采后只重跑 recall calibration，不进 production runtime。",
        "",
        "## 候选规模",
        "",
        json.dumps({"candidate_count": len(candidates), "miss_classification": classification}, ensure_ascii=False, indent=2),
    ]
    (output_dir / "recall_oriented_backfill_proposal.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_truth_metric_comparison(output_dir: Path, strict_summary: dict[str, Any], expanded_summary: dict[str, Any]) -> None:
    text = strict_summary.get("by_point_type", {}).get("text_term", {})
    expanded_text = expanded_summary.get("by_point_type", {}).get("text_term", {})
    lines = [
        "# Term recall vs pilot point recall 口径对照",
        "",
        "pilot 的约 70% 是 point-level 体感基准；本 harness 的主指标是 term-level exact coverage。两者不能直接相乘或混算。",
        "",
        "| 口径 | 数值 | 说明 |",
        "| --- | ---: | --- |",
        f"| text_term term recall(strict node) | {text.get('term_recall', 0):.4f} | 每个 distinctive term 单独计分，最严格 |" if text.get("term_recall") is not None else "| text_term term recall(strict node) | NA | 每个 distinctive term 单独计分，最严格 |",
        f"| text_term point recall(all terms hit) | {text.get('point_all_terms_recall', 0):.4f} | 一个采分点所有 term 都命中才算覆盖 |" if text.get("point_all_terms_recall") is not None else "| text_term point recall(all terms hit) | NA | 一个采分点所有 term 都命中才算覆盖 |",
        f"| text_term point recall(any term hit) | {text.get('point_any_term_recall', 0):.4f} | 一个采分点任一 term 命中即算候选覆盖，接近宽松 point 口径 |" if text.get("point_any_term_recall") is not None else "| text_term point recall(any term hit) | NA | 一个采分点任一 term 命中即算候选覆盖 |",
        f"| text_term term recall(parent/sibling offline) | {expanded_text.get('term_recall', 0):.4f} | 只用于衡量 node 对齐可挽回空间 |" if expanded_text.get("term_recall") is not None else "| text_term term recall(parent/sibling offline) | NA | 只用于衡量 node 对齐可挽回空间 |",
        "",
        "差异来源：",
        "",
        "1. term 级把一个采分点拆成多个必答术语，任何一个漏抽都会降低 term recall。",
        "2. 旧分母混入 calculation / figure_label / non_textbook，会压低教材 text recall；v2 已单列。",
        "3. strict node 只看 question_node；parent/sibling scope 可解释一部分 miss，但仍是离线候选口径。",
    ]
    (output_dir / "truth_metric_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    try:
        assets_by_node = _load_json(args.asset_dir / "scoring_point_assets_by_node.json")
        golden = _load_json(args.golden)
        chunks = _load_book_chunks(args.source_root)
        parent_child = build_parent_child_index(chunks)
        cases = golden.get("cases") or []
        strict_case_results = [
            measure_case_recall(case, assets_by_node=assets_by_node, parent_child=parent_child)
            for case in cases
        ]
        expanded_case_results = [
            measure_case_recall(case, assets_by_node=assets_by_node, parent_child=parent_child, use_expanded_scope=True)
            for case in cases
        ]
        rows = _flatten_rows(strict_case_results)
        expanded_rows = _flatten_rows(expanded_case_results)
        node_gaps = _node_gap_rows(strict_case_results)
        misses = _miss_rows(rows)
        classified = _classify_misses(misses, chunks)
        backfill_candidates = _backfill_candidates(classified)
        backfill_assets = build_backfill_assets(backfill_candidates, chunks)
        backfill_audit = _backfill_verify_audit(backfill_assets, chunks)
        assets_with_backfill = merge_backfill_assets(assets_by_node, backfill_assets)
        with_backfill_case_results = [
            measure_case_recall(case, assets_by_node=assets_with_backfill, parent_child=parent_child)
            for case in cases
        ]
        with_backfill_expanded_case_results = [
            measure_case_recall(case, assets_by_node=assets_with_backfill, parent_child=parent_child, use_expanded_scope=True)
            for case in cases
        ]
        strict_summary = summarize_case_results(strict_case_results)
        expanded_summary = summarize_case_results(expanded_case_results)
        with_backfill_summary = summarize_case_results(with_backfill_case_results)
        with_backfill_expanded_summary = summarize_case_results(with_backfill_expanded_case_results)
        denominator_audit = _raw_required_terms(strict_case_results, cases)

        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(output_dir / "term_coverage_rows.jsonl", rows)
        write_jsonl(output_dir / "expanded_scope_term_coverage_rows.jsonl", expanded_rows)
        write_jsonl(output_dir / "scoring_point_assets_backfill.jsonl", backfill_assets)
        write_jsonl(output_dir / "with_backfill_term_coverage_rows.jsonl", _flatten_rows(with_backfill_case_results))
        write_jsonl(output_dir / "with_backfill_expanded_scope_term_coverage_rows.jsonl", _flatten_rows(with_backfill_expanded_case_results))
        (output_dir / "case_results.json").write_text(json.dumps(strict_case_results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "expanded_scope_case_results.json").write_text(json.dumps(expanded_case_results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "with_backfill_case_results.json").write_text(json.dumps(with_backfill_case_results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "with_backfill_expanded_scope_case_results.json").write_text(json.dumps(with_backfill_expanded_case_results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "summary.json").write_text(json.dumps(strict_summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "expanded_scope_summary.json").write_text(json.dumps(expanded_summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "with_backfill_summary.json").write_text(json.dumps(with_backfill_summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "with_backfill_expanded_scope_summary.json").write_text(json.dumps(with_backfill_expanded_summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "node_alignment_gaps.json").write_text(json.dumps(node_gaps, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "uncovered_gold_terms.json").write_text(json.dumps(misses, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "miss_classification.json").write_text(json.dumps(classified, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "node_remappable_terms.json").write_text(
            json.dumps([row for row in classified if row.get("class") == "node_remappable"], ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (output_dir / "asset_absent_but_in_kb_terms.json").write_text(
            json.dumps([row for row in classified if row.get("class") == "asset_absent_but_in_kb"], ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (output_dir / "gold_non_textbook_terms.json").write_text(
            json.dumps([row for row in classified if row.get("class") == "gold_non_textbook"], ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (output_dir / "recall_oriented_backfill_candidates.json").write_text(
            json.dumps(backfill_candidates, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (output_dir / "backfill_verify_audit.json").write_text(
            json.dumps(backfill_audit, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (output_dir / "clean_denominator_audit.json").write_text(json.dumps(denominator_audit, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

        quality_report = _load_json(args.asset_dir / "quality_report.json") if (args.asset_dir / "quality_report.json").exists() else {}
        seed_summary_path = args.asset_dir / "seed_miss_summary.json"
        seed_summary = _load_json(seed_summary_path).get("summary", {}) if seed_summary_path.exists() else {}
        seed_note = {
            "quality_report_seed_total": quality_report.get("seed_total"),
            "full_kb_seed_total": seed_summary.get("seed_total"),
            "quality_report_seed_hit": quality_report.get("seed_hit"),
            "full_kb_seed_hit": seed_summary.get("seed_hit"),
        }
        (output_dir / "seed_total_reconciliation.json").write_text(json.dumps(seed_note, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        classification = _classification_counts(classified)
        _write_backfill_proposal(output_dir, backfill_candidates, classification)
        _write_truth_metric_comparison(output_dir, strict_summary, expanded_summary)
        _write_markdown(
            output_dir,
            strict_summary=strict_summary,
            expanded_summary=expanded_summary,
            with_backfill_summary=with_backfill_summary,
            with_backfill_expanded_summary=with_backfill_expanded_summary,
            node_gaps=node_gaps,
            misses=misses,
            classified=classified,
            backfill_candidates=backfill_candidates,
            backfill_assets=backfill_assets,
            backfill_audit=backfill_audit,
            seed_note=seed_note,
            denominator_audit=denominator_audit,
        )

        alignment_counts = Counter(result["alignment"]["status"] for result in strict_case_results)
        text = strict_summary.get("by_point_type", {}).get("text_term", {})
        expanded_text = expanded_summary.get("by_point_type", {}).get("text_term", {})
        backfill_text = with_backfill_summary.get("by_point_type", {}).get("text_term", {})
        backfill_expanded_text = with_backfill_expanded_summary.get("by_point_type", {}).get("text_term", {})
        print(
            " ".join(
                [
                    f"cases={strict_summary['case_count']}",
                    f"terms={strict_summary['term_total']}",
                    f"hits={strict_summary['term_hit']}",
                    f"misses={strict_summary['term_miss']}",
                    f"term_recall={strict_summary['term_recall']:.4f}" if strict_summary["term_recall"] is not None else "term_recall=NA",
                    f"text_term_recall={text.get('term_recall'):.4f}" if text.get("term_recall") is not None else "text_term_recall=NA",
                    f"expanded_text_term_recall={expanded_text.get('term_recall'):.4f}" if expanded_text.get("term_recall") is not None else "expanded_text_term_recall=NA",
                    f"with_backfill_text_term_recall={backfill_text.get('term_recall'):.4f}" if backfill_text.get("term_recall") is not None else "with_backfill_text_term_recall=NA",
                    f"with_backfill_expanded_text_term_recall={backfill_expanded_text.get('term_recall'):.4f}" if backfill_expanded_text.get("term_recall") is not None else "with_backfill_expanded_text_term_recall=NA",
                    f"backfill_assets={len(backfill_assets)}",
                    f"excluded_na={strict_summary['excluded_na_terms']}",
                    f"miss_classes={classification['by_class']}",
                    f"alignments={dict(sorted(alignment_counts.items()))}",
                    f"output_dir={output_dir}",
                ]
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
