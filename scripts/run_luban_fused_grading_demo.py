#!/usr/bin/env python3
"""融合判分原型演示：V1 出权威分（确定、逐采分点）+ RAG/LLM 出教学（针对漏掉的采分点）。

设计：分数权威 100% 归 V1（编译采分点 + 确定性求和），教学层绝不改分；RAG 为漏点补教材依据
（rag_fn 可插拔，本地 RAG 未配时教学仍锚定采分点=教材溯源参考）。official_score_allowed 恒 False。

用法：
  python scripts/run_luban_fused_grading_demo.py                       # 默认 Q2023-01 S05
  python scripts/run_luban_fused_grading_demo.py --question Q2023-01 --student S01
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_key() -> str:
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"]
    for line in (REPO / ".env").read_text("utf-8").splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            k = line.split("=", 1)[1].strip().strip('"').strip("'")
            os.environ["DEEPSEEK_API_KEY"] = k
            return k
    raise SystemExit("DEEPSEEK_API_KEY 未配置")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", default="Q2023-01")
    ap.add_argument("--student", default="S05")
    ap.add_argument("--use-rag", action="store_true", help="尝试用 RAG 召回教材依据(本地需 KB 配好)")
    args = ap.parse_args()
    key = _load_key()

    spec = importlib.util.spec_from_file_location("ab", str(REPO / "scripts/run_luban_ab_test_from_bank.py"))
    ab = importlib.util.module_from_spec(spec); spec.loader.exec_module(ab)
    from deeptutor.services.construction_grading import rubric_grader_v1 as G
    from deeptutor.services.construction_grading.case_grading_fusion import build_fused_case_feedback
    from deeptutor.services.llm.factory import complete

    samples = {s["student"]: s for s in ab._parse_samples(args.question)}
    s = samples.get(args.student)
    if not s or not s["answer"]:
        raise SystemExit(f"{args.question} {args.student} 无作答")
    ans, chunk = s["answer"], s["chunk"]
    by_e = ab._load_rubric_for_chunk(chunk)
    if not by_e:
        raise SystemExit(f"chunk {chunk} 不在编译 rubric 库")

    # V1: grade per sub-question, merge to one event (deterministic sums)
    sub = [asyncio.run(G.grade_with_batch_judge_async(
        qid=q, student_answer=ans, rubric_points=by_e[q],
        complete_fn=complete, api_key=key, student_id=f"qa_{args.student}")) for q in sorted(by_e)]
    merged = {
        "event_type": "case_grading_completed",
        "scoring_points": [sp for e in sub for sp in e["scoring_points"]],
        "awarded_score": round(sum(e["awarded_score"] for e in sub), 2),
        "max_score": round(sum(e["max_score"] for e in sub), 1),
        "high_risk_review": any(e["high_risk_review"] for e in sub),
        "official_score_allowed": False,
    }

    rag_fn = None
    if args.use_rag:
        # Call the KB v5 pipeline DIRECTLY — it's a KB-independent direct-Postgres provider; rag_search
        # resolves the provider per-KB-config and would fall back to llamaindex (no local kbv5 KB).
        from deeptutor.services.rag.factory import get_pipeline

        _kbv5 = get_pipeline("kbv5")

        async def rag_fn(q):  # noqa: E306
            r = await _kbv5.search(q, kb_name="kb_v5")
            return (r.get("content") or r.get("answer") or "") if isinstance(r, dict) else str(r)

    out = asyncio.run(build_fused_case_feedback(
        merged, question_stem=f"{args.question} 案例题（{chunk}）", student_answer=ans,
        complete_fn=complete, api_key=key, rag_fn=rag_fn))

    print("=" * 76)
    print(f"融合判分 {args.question} {args.student}（{s['ability']} 人工预估{s['band']}）")
    print("=" * 76)
    print(out["render"])
    print("\n" + "-" * 76)
    print(f"分数权威=V1  得分={out['awarded_score']}/{out['max_score']}  "
          f"用了RAG教材依据={out['evidence_used']}  official_score_allowed={out['official_score_allowed']}")


if __name__ == "__main__":
    main()
