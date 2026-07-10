#!/usr/bin/env python3
"""Fill the case light-practice whitelist from双教研-passed review records.

人门后一键接续:两名教研在 `segmentation_gold/<qid>.review.json` 填完 verdict 且主控
写下 `consensus.status == "passed"` 后,跑此脚本把该 qid 灌进
`case_light_practice_whitelist.v0.json`(status="allowed")→ 才允许对学员出轻练。

红线:**只灌 consensus 已 passed 的 qid**。未 passed / consensus 为空 → 不灌(fail-closed)。
现在跑 = 0 条(没有任何题过验收),白名单保持空、门保持关。纯确定性,无 LLM。

Usage: python scripts/fill_case_whitelist_from_review.py [--write]
       (不带 --write 只 dry-run 打印将灌哪些;带 --write 才落盘)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deeptutor.services.construction_grading.case_segmentation_quality_gate import (
    passes_quality_gate,
)

_ROOT = Path(__file__).resolve().parents[1]
_REVIEW_DIR = _ROOT / "docs/原始数据/考点原料/segmentation_gold"
_WHITELIST = (
    _ROOT
    / "deeptutor/services/construction_grading/runtime_supply/case_light_practice/case_light_practice_whitelist.v0.json"
)


def _passed_entries(review_dir: Path = _REVIEW_DIR) -> list[dict]:
    """Return whitelist entries for every review whose consensus.status == 'passed'."""
    entries: list[dict] = []
    for f in sorted(review_dir.glob("*.review.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        consensus = d.get("consensus") or {}
        if consensus.get("status") != "passed":
            continue  # fail-closed: only教研-consensus-passed qids enter
        if not passes_quality_gate(d):
            continue  # §1限制② 切分质量闸:结构不过关(缺sub_no/合取组坏…)不进白名单
        qid = d["qid"]
        subs = sorted(
            {p.get("proposed_sub_no") for p in d.get("points") or [] if p.get("proposed_sub_no") is not None}
        )
        try:
            ref = str(f.relative_to(_ROOT))
        except ValueError:
            ref = str(f)  # review outside repo root (e.g. a test tmpdir)
        entries.append(
            {
                "qid": qid,
                "status": "allowed",
                "sub_qids": [f"{qid}::sub{n}" for n in subs],
                "segmentation_gold_ref": ref,
                "approved_by": [r.get("name") for r in d.get("reviewers") or [] if r.get("name")],
            }
        )
    return entries


def fill(write: bool = False) -> list[dict]:
    entries = _passed_entries()
    if write:
        wl = json.loads(_WHITELIST.read_text(encoding="utf-8"))
        wl["entries"] = entries
        _WHITELIST.write_text(json.dumps(wl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entries


def main() -> int:
    write = "--write" in sys.argv[1:]
    entries = fill(write=write)
    if not entries:
        print("0 qid 过验收(consensus!=passed)→ 白名单保持空,门保持关(fail-closed)。")
    else:
        for e in entries:
            print(f"  allow {e['qid']}  ({len(e['sub_qids'])} 小问,approved_by={e['approved_by']})")
    print(f"{'WROTE' if write else 'DRY-RUN'}: {len(entries)} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
