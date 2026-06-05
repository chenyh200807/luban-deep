#!/usr/bin/env python3
"""Stream B — write the teacher-review pilot artifacts (test-env / dry_run).

Thin wrapper: selects 5 golden eval_samples covering exact_required near-synonym,
list_rule incomplete, calculation error, a basically-correct case, and a penalty/
override case; runs each through the REUSED closed loop in
``teacher_review_pilot.run_pilot`` and writes:

    artifacts/luban_consensus_gold/teacher_review_pilot_20260604/
      ├── <case>__<student>.json        # draft + review_json + writeback per subject
      ├── learning_brain_synthesis.json  # aggregated read-back (weakness/mastery/next)
      └── FINDING_teacher_review_pilot_20260604.md

Red lines honored: dry_run only (no real user / production DB / RAG); teacher-final
is the write authority; high_risk-not-confirmed never becomes mastery; the QA
reviewer is explicitly synthetic (no impersonation). Nothing here adds a table or
touches the kernel / runtime.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.teacher_review_pilot import (  # noqa: E402
    confirm_ai,
    override_upgrade,
    reject_overcredit,
    run_pilot,
)

GOLDEN = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
OUT = REPO / "artifacts/luban_consensus_gold/teacher_review_pilot_20260604"


def _load_golden_cases() -> dict[str, dict[str, Any]]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return {c["case_id"]: c for c in data.get("cases", [])}


def build_subjects(cases: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The 5 quasi-real pilot subjects, covering the required policy coverage.

    The coverage rationale is recorded per-subject so the FINDING can explain why
    each one was chosen.
    """
    return [
        {
            "golden_case": cases["Q10-1A422000"],
            "student_id": "S2",
            "coverage": "exact_required 近义/半术语漏判（学生只命中前2点，其余近义不给分）",
            # teacher confirms the AI's strict踩字 judgement
        },
        {
            "golden_case": cases["Q1-NA"],
            "student_id": "S2",
            "coverage": "list_rule 列举不全（partial + high_risk）；教师复核判 AI 放水 -> reject",
            "policy_by_point": {"P1": reject_overcredit},
        },
        {
            "golden_case": cases["Q20-1A413000"],
            "student_id": "S2",
            "coverage": "calculation 计算错误（命中6点、3点算错）",
        },
        {
            "golden_case": cases["Q8-1A413030"],
            "student_id": "S1",
            "coverage": "基本正确（单采分点满分命中，进入 mastery）",
        },
        {
            "golden_case": cases["Q4-1A434000-罚则"],
            "student_id": "S4",
            "coverage": "penalty_rule + teacher override（教师把 AI 漏判的 P1 改判满分命中）",
            "policy_by_point": {"P1": override_upgrade},
        },
    ]


def _subject_filename(subject_result: dict[str, Any]) -> str:
    case_id = str(subject_result["case_id"]).replace("/", "_")
    return f"{case_id}__{subject_result['student_id']}.json"


def _write_finding(out_dir: Path, pilot: dict[str, Any], coverage: list[str]) -> Path:
    syn = pilot["synthesis"]
    lines: list[str] = []
    lines.append("# FINDING — 鲁班 teacher-review pilot（quasi-real, dry_run）2026-06-04")
    lines.append("")
    lines.append("> **准真实声明**：学生作答取自 golden fixture `eval_samples`（为基准曲线"
                 "整理的考试式作答）；教师判定由占位 QA 审核者作出，非真人，"
                 "review_json 内 `reviewer_is_synthetic=true`。")
    lines.append("")
    lines.append("## 闭环（全程复用，无第二套逻辑）")
    lines.append("")
    lines.append("Best-Quality 4-model draft → teacher review（confirm/reject/override）"
                 "→ writeback preview（dry_run）→ Learning-Brain 读回（weakness/mastery/suggestion）。")
    lines.append("")
    lines.append("- 评分裁决：`best_quality_ai_draft.best_quality_for_golden`（缓存 4 模型，缺则 fail-closed）")
    lines.append("- 写回换算：`teacher_review_writeback.build_teacher_review_writeback(dry_run=True)`")
    lines.append("- 学情合成：`learning_brain_synthesis.synthesize_learner_profile`（Stream D，未另造）")
    lines.append("")
    lines.append("## 红线核对")
    lines.append("")
    lines.append("- dry_run=True、learner_state_service=None：**未写任何真实用户/生产库**。")
    lines.append("- teacher-final 是写入权威：每个采分点都带显式 `review_action`，教师判定覆盖 AI。")
    lines.append("- high_risk 未被教师确认 → 不计 mastery（Q1 P1：partial+high_risk，教师 reject，"
                 "`mastery_eligible=false`）。")
    lines.append("- 不接 RAG、不接 production runtime、不改 kernel、不新增表。")
    lines.append("")
    lines.append("## 5 份准真实样本覆盖")
    lines.append("")
    for subject, cov in zip(pilot["subjects"], coverage):
        wb = subject["writeback"]
        mastery = wb["mastery_point_ids"]
        lines.append(f"- **{subject['case_id']} / {subject['student_id']}** — {cov}；"
                     f"mastery 采分点 {mastery or '无'}")
    lines.append("")
    lines.append("## Learning-Brain 读回（teacher-final 聚合）")
    lines.append("")
    lines.append(f"- 弱项信号 weaknesses: **{len(syn['weaknesses'])}** 条")
    for w in syn["weaknesses"]:
        lines.append(f"  - `{w['error_code']}` {w['label']}（{w['dimension']}）×{w['count']}")
    lines.append(f"- 掌握信号 mastered_points: **{len(syn['mastered_points'])}** 个")
    for m in syn["mastered_points"]:
        lines.append(f"  - `{m['point_id']}` {m['policy_type']} → {m['ability_dimension']}")
    lines.append(f"- 下一步建议 next_suggestions: **{len(syn['next_suggestions'])}** 条")
    for s in syn["next_suggestions"]:
        lines.append(f"  - {s['action']}：{s['reason']}")
    lines.append("")
    path = out_dir / "FINDING_teacher_review_pilot_20260604.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    cases = _load_golden_cases()
    subjects = build_subjects(cases)
    coverage = [s["coverage"] for s in subjects]
    pilot = run_pilot(subjects)

    OUT.mkdir(parents=True, exist_ok=True)
    for subject in pilot["subjects"]:
        path = OUT / _subject_filename(subject)
        path.write_text(json.dumps(subject, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}", flush=True)

    syn_path = OUT / "learning_brain_synthesis.json"
    syn_path.write_text(json.dumps(pilot["synthesis"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {syn_path.relative_to(REPO)}", flush=True)

    finding = _write_finding(OUT, pilot, coverage)
    print(f"wrote {finding.relative_to(REPO)}", flush=True)


if __name__ == "__main__":
    main()
