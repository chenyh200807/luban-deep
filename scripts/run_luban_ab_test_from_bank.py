#!/usr/bin/env python3
"""鲁班 V0 vs V1 案例评分 A/B —— 用真题库里真实学生作答，跨能力层对比。

数据源：docs/2026/题库/近三年案例题_按学生答卷排版.md（题目 + 150 份真实学生作答 + 能力层 + 预估得分区间）。
参考答案来自编译 rubric 库（治理过的采分点）。同一道题、不同水平学生：
  V0 = CaseGradingSkillKernel（确定性关键词，二值给分）
  V1 = grade_with_batch_judge_async（真实 DeepSeek，逐采分点语义 + 确定性求和 + 归一）
对照"预估得分区间"看谁的判分更贴近人工分层。

用法：
  python scripts/run_luban_ab_test_from_bank.py                       # 默认 Q2023-01 + 跨层学生
  python scripts/run_luban_ab_test_from_bank.py --question Q2023-02 --students S01,S05,S10
"""
from __future__ import annotations

import argparse
import asyncio
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BANK_MD = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库/"
               "近三年案例题_按学生答卷排版.md")
RUBRIC = REPO / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/case_rubric_scored.json"


def _load_deepseek_key() -> str:
    import os
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"]
    for line in (REPO / ".env").read_text("utf-8").splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            k = line.split("=", 1)[1].strip().strip('"').strip("'")
            os.environ["DEEPSEEK_API_KEY"] = k
            return k
    raise SystemExit("DEEPSEEK_API_KEY 未配置")


def _parse_samples(question: str) -> list[dict]:
    """Extract every student's answer block for one question id from the markdown."""
    text = BANK_MD.read_text("utf-8")
    blocks = re.split(r"\n### (Q\d{4}-\d{2})[｜|]", text)
    # re.split keeps captured ids: [pre, id1, body1, id2, body2, ...]
    out = []
    for i in range(1, len(blocks), 2):
        qid, body = blocks[i], blocks[i + 1]
        if qid != question:
            continue
        sample_id = (re.search(r"样本ID[：:]\s*`?([^`\n]+)`?", body) or [None, ""])[1].strip()
        ability = (re.search(r"ability_label[：:]\s*`?([^`\n]+)`?", body) or [None, ""])[1].strip()
        band = (re.search(r"预估得分区间[：:]\s*([^\n]+)", body) or [None, ""])[1].strip()
        chunk = (re.search(r"来源\s*chunk[：:]\s*`?(EXAM_[A-Z0-9_]+)`?", body) or [None, ""])[1].strip()
        ans_m = re.search(r"#### 回答\s*\n作答[：:]\s*\n(.+?)(?=\n#### |\Z)", body, re.S)
        answer = (ans_m.group(1).strip() if ans_m else "")
        sid_m = re.search(r"__(S\d+)", sample_id)
        out.append({"sample_id": sample_id, "student": sid_m.group(1) if sid_m else "",
                    "ability": ability, "band": band, "chunk": chunk, "answer": answer})
    return out


def _load_rubric_for_chunk(chunk: str):
    import json
    b = json.loads(RUBRIC.read_text("utf-8"))
    by_q = defaultdict(list)
    for r in b["records"]:
        if str(r["qid"]).startswith(chunk):
            by_q[str(r["qid"])].append({"point_id": r["point_id"], "text": r["text"],
                                        "score": r["score"], "policy": r["policy"],
                                        "required_terms": r.get("required_terms") or []})
    return dict(sorted(by_q.items()))  # {sub_question_qid: [points]} — grade per sub-question


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", default="Q2023-01")
    ap.add_argument("--students", default="S01,S03,S05,S08,S10")  # high→very_low spread
    args = ap.parse_args()
    key = _load_deepseek_key()

    from deeptutor.services.construction_grading import rubric_grader_v1 as G
    from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
    from deeptutor.services.llm.factory import complete

    samples = {s["student"]: s for s in _parse_samples(args.question)}
    if not samples:
        raise SystemExit(f"题 {args.question} 未在文件中找到")
    chunk = next(iter(samples.values()))["chunk"]
    by_e = _load_rubric_for_chunk(chunk)  # {sub_question_qid: [points]}
    if not by_e:
        raise SystemExit(f"chunk {chunk} 不在编译 rubric 库")
    all_points = [p for pts in by_e.values() for p in pts]
    correct = "；".join(p["text"] for p in all_points)
    max_score = round(sum(float(p["score"]) for p in all_points), 1)

    wanted = [s.strip() for s in args.students.split(",") if s.strip()]
    bar = "=" * 78
    print(bar)
    print(f"A/B 题目: {args.question}  chunk={chunk}  编译满分={max_score}"
          f"（{len(all_points)}采分点, {len(by_e)}子问, 逐子问判分）")
    print(bar)

    rows = []
    for sid in wanted:
        s = samples.get(sid)
        if not s or not s["answer"]:
            print(f"\n[{sid}] 无作答，跳过"); continue
        ans = s["answer"]
        # V0: deterministic kernel against the full reference
        row = {"question_id": chunk, "question_type": "case", "correct_answer": correct, "stem": ""}
        v0 = CaseGradingSkillKernel().grade(question_row=row, user_answer=ans).to_dict()
        v0_aw, v0_mx = float(v0.get("score_awarded") or 0), float(v0.get("max_score") or 0)
        v0_pct = round(v0_aw / v0_mx * 100) if v0_mx else 0
        # V1: grade EACH sub-question separately (avoid 40-point batch degradation), sum deterministically
        v1_aw = v1_mx = 0.0
        hits = partials = 0
        for q, pts in by_e.items():
            ev = asyncio.run(G.grade_with_batch_judge_async(
                qid=q, student_answer=ans, rubric_points=pts,
                complete_fn=complete, api_key=key, student_id=f"qa_ab_{sid}"))
            v1_aw += ev["awarded_score"]; v1_mx += ev["max_score"]
            hits += sum(1 for sp in ev["scoring_points"] if sp["hit"] == "hit")
            partials += sum(1 for sp in ev["scoring_points"] if sp["hit"] == "partial")
        v1_aw = round(v1_aw, 1); v1_mx = round(v1_mx, 1)
        v1_pct = round(v1_aw / v1_mx * 100) if v1_mx else 0
        rows.append((sid, s["ability"], s["band"], v0_pct, v1_pct, hits, partials, len(all_points)))
        print(f"\n[{sid}] 能力层={s['ability']}  人工预估={s['band']}  作答{len(ans)}字")
        print(f"   V0(确定性): {v0_aw}/{v0_mx} = {v0_pct}%")
        print(f"   V1(语义):   {v1_aw}/{v1_mx} = {v1_pct}%  (命中{hits} 部分{partials} 共{len(all_points)}点)")

    print("\n" + bar)
    print(f"{'学生':<6}{'能力层':<12}{'人工预估':<14}{'V0%':>6}{'V1%':>6}  V1命中/部分/总")
    print("-" * 78)
    for sid, ab, band, v0p, v1p, h, pa, tot in rows:
        print(f"{sid:<6}{ab:<12}{band:<14}{v0p:>5}%{v1p:>5}%  {h}/{pa}/{tot}")
    print(bar)
    print("看点：V1% 是否随能力层单调下降、是否落在人工预估区间内；V0 二值制是否虚高/不区分。")


if __name__ == "__main__":
    main()
