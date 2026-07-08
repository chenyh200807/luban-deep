#!/usr/bin/env python3
"""Emit per-qid segmentation REVIEW SKELETONS for the double-教研 acceptance gate.

块 A 的确定性半自动脚手架(教研-independent 部分)。把教研从"写切分"降为"审切分":
从 published 编译库 `v_case_rubric_scored` 抽出每道优先题的**当前采分点**,产出一份
`docs/原始数据/考点原料/segmentation_gold/<qid>.review.json` 骨架,预填当前点 + 空
verdict 槽(proposed_sub_no / is_atomic / anchor_ok / conjunction_group / ordering_group),
两名教研独立填、不一致→arbitration。

**边界诚实**:本脚本只做确定性抽取(纯读,无 LLM)。真正的"LLM 辅助按小问/官方答案
分段切"那半——生成 proposed_sub_no 候选——需 DeepSeek 凭据/阿里云只读实测,未做;
留 `proposed_sub_no: null` 待 LLM 补 + 教研定。**不写真值、不填白名单**——教研 consensus
过后由另一步(§2.5① 填 whitelist)接手。official_score_allowed=false。

Usage: python scripts/build_case_segmentation_review_skeletons.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_RUBRIC = _ROOT / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/case_rubric_scored.json"
_OUT_DIR = _ROOT / "docs/原始数据/考点原料/segmentation_gold"

# owner 已确认的首批 5 道(2026-07-09,§2.7 提案「照提案 5 道」)。
PRIORITY_QIDS = [
    "EXAM_1A434000_P0011_01::E0",  # 起鼓割补,已 live 验证锚
    "EXAM_1A434000_P0010_02::E0",  # 纯列举·高分
    "EXAM_1A434000_P0014_02::E0",  # 欠切分最重
    "EXAM_1A434000_P0013_01::E0",  # 判断改正·合取门样板
    "EXAM_1A434000_P0017_01::E1",  # 判断改正·合取门泛化
]


def _load_by_qid() -> dict[str, list[dict]]:
    data = json.loads(_RUBRIC.read_text(encoding="utf-8"))
    g: dict[str, list[dict]] = collections.defaultdict(list)
    for r in data["records"]:
        g[r["qid"]].append(r)
    return g


def _skeleton(qid: str, pts: list[dict]) -> dict:
    return {
        "artifact": "segmentation_review",
        "version": "v0",
        "status": "pending_dual_review",
        "official_score_allowed": False,
        "qid": qid,
        "current_point_count": len(pts),
        "current_total_score": pts[0].get("total_score") if pts else None,
        "instructions": (
            "两名教研**独立**填每点的 proposed_sub_no(小问号)+ is_atomic(独立可判/互斥/可证伪)"
            "+ anchor_ok(锚到教材或真题原文)+ 非平点结构(conjunction_group 找错∧改正 / "
            "ordering_group 顺序敏感 / list_cap 答N给M)。审而非写:当前点已列出,你只标切分。"
            "不一致→arbitration→consensus。consensus 过后才由填白名单步接手。"
        ),
        "points": [
            {
                "point_id": p.get("point_id"),
                "statement": p.get("text"),
                "current_score": p.get("score"),
                "policy": p.get("policy"),
                "required_terms": p.get("required_terms") or [],
                "proposed_sub_no": None,
                "is_atomic": None,
                "anchor_ok": None,
                "conjunction_group": None,
                "ordering_group": None,
                "list_cap": None,
                "notes": "",
            }
            for p in pts
        ],
        "reviewers": [],
        "consensus": None,
        "arbitration": None,
    }


def main() -> int:
    by_qid = _load_by_qid()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for qid in PRIORITY_QIDS:
        pts = by_qid.get(qid)
        if not pts:
            print(f"WARN: {qid} not in compiled rubric — skipped", file=sys.stderr)
            continue
        safe = qid.replace("::", "__")
        out = _OUT_DIR / f"{safe}.review.json"
        out.write_text(json.dumps(_skeleton(qid, pts), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append((qid, len(pts)))
    print(f"wrote {len(written)} review skeletons to {_OUT_DIR}:")
    for qid, n in written:
        print(f"  {qid}  ({n} 点,待教研切分)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
