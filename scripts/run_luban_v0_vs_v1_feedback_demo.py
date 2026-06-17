#!/usr/bin/env python
"""V0 vs V1 案例题批改话术对比 —— 让人亲眼看见学生在聊天里实际读到的文字差异。

同一道在库真题、同一份学生作答，分别走：
  V0：CaseGradingSkillKernel（线上现状，确定性关键词匹配，二值给分、无部分分、分不清答错/漏写）
  V1：grade_with_batch_judge_async（真实 DeepSeek，逐采分点语义判定）→ render_case_rubric_feedback

用法：
  python scripts/run_luban_v0_vs_v1_feedback_demo.py            # 默认题 + 默认学生作答
  python scripts/run_luban_v0_vs_v1_feedback_demo.py --qid <QID> --answer "<学生作答>"

需要 .env 中的 DEEPSEEK_API_KEY（脚本会自行读取）。这是只读演示：不写库、不写 learner_state，
official_score_allowed 始终为 False。
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_QID = "EXAM_1A413030_P0012_04::E3"
_DEFAULT_STEM = "某工程现浇混凝土施工，列出该工程可选用的混凝土水平运输设备、垂直运输设备和泵送设备。"
_DEFAULT_ANSWER = "水平运输用手推车和机动翻斗车；垂直运输用塔吊；混凝土泵送用汽车泵和布料机。"


def _load_deepseek_key() -> str:
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"]
    env = _ROOT / ".env"
    if env.exists():
        for line in env.read_text("utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ["DEEPSEEK_API_KEY"] = key
                return key
    raise SystemExit("DEEPSEEK_API_KEY 未配置（环境变量或 .env 均无）")


def _render_v0(result: dict) -> str:
    """渲染 V0 学生看到的话术（反映其真实行为：二值 full/miss，命中即满分，未中即'漏写'）。"""
    out = [f"【得分】{result['score_awarded']} / {result['max_score']} 分", "", "【点评】"]
    for it in result["rubric_items"]:
        if it["status"] == "full":
            out.append(f"  ✅ {it['criterion']}（{it['awarded_score']}/{it['max_score']}分）"
                       f"—— 命中关键词：{it['evidence_text']}")
        else:
            out.append(f"  ❌ {it['criterion']}（0/{it['max_score']}分）—— 漏写采分点")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qid", default=_DEFAULT_QID)
    parser.add_argument("--stem", default=_DEFAULT_STEM)
    parser.add_argument("--answer", default=_DEFAULT_ANSWER)
    args = parser.parse_args()

    key = _load_deepseek_key()

    from deeptutor.services.construction_grading import rubric_grader_v1 as G
    from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
    from deeptutor.services.llm.factory import complete

    points = G.load_rubric(args.qid)
    if not points:
        raise SystemExit(f"题 {args.qid} 不在已编译 rubric 库中")
    correct = "；".join(p["text"] for p in points)  # 参考答案 = 采分点拼回（V0 kernel 用）

    # V0：线上现状的确定性 kernel
    row = {"question_id": args.qid, "question_type": "case", "question_stem": args.stem,
           "stem": args.stem, "correct_answer": correct, "node_code": ""}
    v0 = CaseGradingSkillKernel().grade(question_row=row, user_answer=args.answer).to_dict()

    # V1：真实 DeepSeek 语义逐采分点
    event = asyncio.run(G.grade_with_batch_judge_async(
        qid=args.qid, student_answer=args.answer, rubric_points=points,
        complete_fn=complete, api_key=key, student_id="qa_demo"))
    v1_text = G.render_case_rubric_feedback(event, question_stem=args.stem)

    bar = "=" * 72
    print(bar)
    print("题目：", args.stem)
    print("参考答案：", correct)
    print("学生作答：", args.answer)
    print(bar)
    print("\n########## V0（线上现状：确定性关键词匹配）学生看到 ##########\n")
    print(_render_v0(v0))
    print("\n########## V1（语义逐采分点 + 真实 DeepSeek）学生看到 ##########\n")
    print(v1_text)
    print(bar)


if __name__ == "__main__":
    main()
