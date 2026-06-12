#!/usr/bin/env python3
"""Before/after grounding contrast for the v3.2 scoring-point enrichment (review-only, no live calls).

Picks the case-eval-v2 sub-questions where the rich arm CITED a rich block but did not
score "correct" (the granularity-mismatch population), and renders for each one:

- BEFORE: the v3.1.1 units of the row's rich_leaf_ids, default (teaching) rendering;
- AFTER:  the v3.2 units of the same leaves, grading=True rendering (scoring_points first).

Output is a human-readable markdown contrast + a JSON sidecar. No LLM, no runtime writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.rich_leaf_runtime import (  # noqa: E402
    format_rich_leaf_pack_grounding_lines,
)

DEFAULT_EVAL = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_case_question_eval_v2_20260613"
    / "case_question_two_arm_eval_results.json"
)
DEFAULT_BEFORE_PACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v11_coverage_expansion_20260613"
    / "runtime_token_pack_v311_quarantine_annotated.json"
)
DEFAULT_AFTER_PACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_v32_scoring_point_compile_20260613"
    / "runtime_token_pack_v32_scoring_points.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_v32_scoring_point_compile_20260613"
RENDER_MAX_CHARS = 1200  # same cap as the case-question eval harness
SAMPLE_SIZE = 10


def _units_by_leaf(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(u.get("leaf_id")): u
        for u in pack.get("runtime_token_pack_units") or []
        if isinstance(u, dict) and u.get("leaf_id")
    }


def _render(units: dict[str, dict[str, Any]], leaf_ids: list[str], *, grading: bool) -> str:
    riches = [
        {
            "leaf_id": leaf,
            "leaf_name_path": units[leaf].get("leaf_name_path"),
            "compiled_context": units[leaf].get("compiled_context") or {},
        }
        for leaf in leaf_ids
        if leaf in units
    ]
    lines = format_rich_leaf_pack_grounding_lines(
        {"rich_leaf_contexts": riches}, max_chars=RENDER_MAX_CHARS, grading=grading
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-results", type=Path, default=DEFAULT_EVAL)
    parser.add_argument("--before-pack", type=Path, default=DEFAULT_BEFORE_PACK)
    parser.add_argument("--after-pack", type=Path, default=DEFAULT_AFTER_PACK)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_DIR / "before_after_contrast.md")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_DIR / "before_after_contrast.json")
    args = parser.parse_args(argv)

    results = json.loads(args.eval_results.read_text(encoding="utf-8"))
    before_units = _units_by_leaf(json.loads(args.before_pack.read_text(encoding="utf-8")))
    after_units = _units_by_leaf(json.loads(args.after_pack.read_text(encoding="utf-8")))

    candidates = [
        r
        for r in results.get("rows") or []
        if r.get("arm") == "kbv5_plus_rich_multi_leaf"
        and ((r.get("citation_audit") or {}).get("counts") or {}).get("rich_block", 0) > 0
        and r.get("verdict") != "correct"
    ][: args.sample_size]

    rows: list[dict[str, Any]] = []
    md: list[str] = [
        "# v3.2 采分点增补 before/after 上下文对照（review-only，未跑 live）",
        "",
        f"- 样本来源: 案例评测 v2，rich 块被引证但 verdict != correct 的小问，取前 {len(candidates)} 个。",
        "- BEFORE: v3.1.1 unit 默认渲染（教材要点形态）。",
        "- AFTER: v3.2 unit grading=True 渲染（采分点族优先，含必含术语 + 教材 chunk 溯源）。",
        f"- 渲染 cap 与评测一致（{RENDER_MAX_CHARS} 字符）。",
        "",
    ]
    points_gained = 0
    rows_with_sp = 0
    for r in candidates:
        leaf_ids = [str(x) for x in r.get("rich_leaf_ids") or []]
        before = _render(before_units, leaf_ids, grading=False)
        after = _render(after_units, leaf_ids, grading=True)
        sp_lines = [ln for ln in after.splitlines() if ln.startswith("- [采分点]")]
        m35_lines = [ln for ln in sp_lines if "m35" in ln or "必含术语" in ln]
        points_gained += len(sp_lines)
        rows_with_sp += 1 if sp_lines else 0
        rows.append(
            {
                "sub_id": r.get("sub_id"),
                "verdict": r.get("verdict"),
                "verdict_score": r.get("verdict_score"),
                "point_coverage": r.get("point_coverage"),
                "rich_leaf_ids": leaf_ids,
                "scoring_point_lines_after": len(sp_lines),
                "before": before,
                "after": after,
            }
        )
        md += [
            f"## {r.get('sub_id')}",
            f"- verdict: {r.get('verdict')} (score {r.get('verdict_score')}, point_coverage {r.get('point_coverage')})",
            f"- rich_leaf_ids: {', '.join(leaf_ids)}",
            f"- AFTER 新增采分点行数: {len(sp_lines)}（其中带必含术语: {len(m35_lines)}）",
            "",
            "### BEFORE (v3.1.1 默认渲染)",
            "```",
            before or "(无渲染输出)",
            "```",
            "### AFTER (v3.2 grading 渲染)",
            "```",
            after or "(无渲染输出)",
            "```",
            "",
        ]
    summary = {
        "sample_size": len(candidates),
        "rows_with_scoring_points_after": rows_with_sp,
        "scoring_point_lines_total_after": points_gained,
        "review_only": True,
        "live_eval_run": False,
        "quality_claim_allowed": False,
    }
    md.insert(7, f"**汇总**: {len(candidates)} 个小问中 {rows_with_sp} 个 AFTER 渲染含采分点行，共 {points_gained} 行。\n")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    args.output_json.write_text(
        json.dumps({"schema": "luban_rich_leaf_scoring_point_before_after.v1", "summary": summary, "rows": rows},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output_md": str(args.output_md), "output_json": str(args.output_json), "summary": summary},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
