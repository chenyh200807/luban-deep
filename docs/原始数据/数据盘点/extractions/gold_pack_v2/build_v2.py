#!/usr/bin/env python3
"""Build the v2 pilot grading gold pack + its 4-gram leakage report.

Pure data assembly. Reads:
  - scratchpad/gold_pack/student_army_grading_gold.v1.json  (stem + official_answer)
  - docs/原始数据/数据盘点/extractions/{year}_jianzhu_case_rubric.jsonl (采分点骨架)
  - ./_draft_Q*.json  (hand-authored v2 answers + expected_failures)

Writes (incrementally, one question at a time):
  - student_army_gold.v2.pilot.json
  - leakage_check.json

The 4-gram metric is byte-for-byte the same one used by
scratchpad/eval_army/01_cohort_select.py so v1 and v2 numbers are comparable.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("DEEPTUTOR_REPO", "/Users/yehongchen/orca/workspaces/deeptutor/gar"))
RUBRIC_DIR = REPO / "docs/原始数据/数据盘点/extractions"  # 仓库内，稳定
# v1 金标不在仓库内（上一棒生成在会话 scratchpad）。换机/换会话时用 GOLD_V1 环境变量覆盖。
GOLD_V1 = Path(
    os.environ.get(
        "GOLD_V1",
        "/private/tmp/claude-501/-Users-yehongchen-orca-workspaces-deeptutor-gar/"
        "40e1ec6d-a9a2-4eed-8a30-9e2df19c1493/scratchpad/gold_pack/"
        "student_army_grading_gold.v1.json",
    )
)

PILOT_QUESTIONS = ["Q2023-03", "Q2024-03", "Q2025-03"]
CASE_NO = {"Q2023-03": 3, "Q2024-03": 3, "Q2025-03": 3}
LEAK_THRESHOLD = 0.60

_PUNCT = re.compile(
    r"[\s　_、，。；：？！“”‘’（）()《》〈〉【】\[\]{}<>,.;:?!\"'`~@#$%^&*+=|\\/-]+"
)


def norm(text: str) -> str:
    return _PUNCT.sub("", str(text or ""))


def ngrams(text: str, n: int = 4) -> Counter:
    s = norm(text)
    return Counter(s[i : i + n] for i in range(len(s) - n + 1)) if len(s) >= n else Counter()


def multiset_pr(a: Counter, b: Counter) -> tuple[float, float, float]:
    """precision/recall/jaccard of student n-grams (a) against official n-grams (b)."""
    if not a or not b:
        return 0.0, 0.0, 0.0
    inter = sum((a & b).values())
    union = sum((a | b).values())
    return inter / sum(a.values()), inter / sum(b.values()), inter / union


def load_rubric(year: int, case_no: int) -> list[dict]:
    pts = []
    path = RUBRIC_DIR / f"{year}_jianzhu_case_rubric.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if "_meta" in rec:
            continue
        if rec.get("case_no") != case_no:
            continue
        pts.append(
            {
                "point_id": f"{rec['sub_q_no']}.{rec['point_seq']}",
                "sub_q_no": str(rec["sub_q_no"]),
                "point_seq": rec["point_seq"],
                "point_score": rec["point_score"],
                "point_type": rec["point_type"],
                "point_text": rec["point_text"],
                "sub_q_total_score": rec["sub_q_total_score"],
            }
        )
    return pts


def main() -> None:
    v1 = json.loads(GOLD_V1.read_text(encoding="utf-8"))
    v1_by_qid = {q["question_id"]: q for q in v1["questions"]}

    pack = {
        "schema": "student_army_gold.v2.pilot",
        "generated_at": "2026-07-31",
        "gold_definition": (
            "金标 = (a) 官方采分点骨架（point_id / point_text / point_score，取自佑森解析视觉抽取的 "
            "case rubric）+ (b) 每份作答刻意植入的 expected_failures（该卷必须拿不到的采分点及其失分机理）。"
            "未列入 expected_failures 的采分点，一律应当被判为命中。作答文本本身不是金标，"
            "answer_text 只是承载失分形态的载体。"
        ),
        "why_v2": (
            "v1 的 10 份“学生答卷”实为官方答案的逐字截断（S03=全文+尾巴，S06=前缀），4-gram 泄漏实测 "
            "P/R 部分题 ≥0.97，因此 v1 只能测“漏没漏”，排序全对是恒等式而非能力证据。v2 用改写表达正确内容，"
            "并按四类失分形态注入可客观判定的错误，使金标能测“答错/术语不准/数值记错”。"
        ),
        "failure_types": {
            "omission": "少答小问或少答采分点（用自己的话写对的部分，绝不靠截断官方答案实现）",
            "wrong": "给出与官方采分点相矛盾的做法/结论，含张冠李戴（把成立项判为不妥）",
            "imprecise_term": "意思接近但用词不规范：口语化、近义替换、规范名称写错",
            "numeric": "数字、天数、比例、根数、规范限值记错",
        },
        "leakage_gate": {
            "metric": "character 4-gram multiset, punctuation/whitespace stripped",
            "reference": "scratchpad/eval_army/01_cohort_select.py (identical functions)",
            "threshold": LEAK_THRESHOLD,
            "rule": "precision / recall / jaccard 三项全部 < 0.60 才准入；超标即重写",
        },
        "honest_boundaries": [
            "作答由 LLM（Claude Opus 5）按采分点骨架撰写，不是真实考生语料；缺少真人答卷特有的书写混乱、跳题、错别字与半截句。",
            "采分点来自佑森教育解析的视觉抽取（NOT_official=true），本身有转录误差；v2 只对齐它，不对齐官方评分标准。",
            "expected_failures 的判定规则是人写的，仍是单一作者判断，未经第二人复核。",
        ],
        "questions": [],
    }

    leak_report = {
        "schema": "gold_pack_v2.leakage_check",
        "metric": "character 4-gram multiset precision/recall/jaccard vs the question's official_answer",
        "threshold": LEAK_THRESHOLD,
        "rows": [],
        "v1_baseline_same_questions": [],
        "v1_comparison_note": (
            "v1_baseline_same_questions 是同样三道题下 v1 十份“学生答卷”对 official_answer 的同一指标，"
            "用作对照：v1 的高分档答卷是官方答案的逐字截断，precision 逼近 1.0。"
        ),
    }

    for qid in PILOT_QUESTIONS:
        src = v1_by_qid[qid]
        off_ng = ngrams(src["official_answer"])
        for st in src["students"]:
            text = st.get("answer_text") or st.get("answer") or ""
            p, r, j = multiset_pr(ngrams(text), off_ng)
            leak_report["v1_baseline_same_questions"].append(
                {
                    "question_id": qid,
                    "student_id": st.get("student_id") or st.get("id"),
                    "precision": round(p, 4),
                    "recall": round(r, 4),
                    "jaccard": round(j, 4),
                    "would_pass_v2_gate": max(p, r, j) < LEAK_THRESHOLD,
                }
            )

    for qid in PILOT_QUESTIONS:
        draft = json.loads((HERE / f"_draft_{qid}.json").read_text(encoding="utf-8"))
        src = v1_by_qid[qid]
        year = src["year"]
        rubric = load_rubric(year, CASE_NO[qid])
        rubric_ids = {p["point_id"] for p in rubric}
        official = src["official_answer"]
        off_ng = ngrams(official)

        q_out = {
            "question_id": qid,
            "year": year,
            "title": src["title"],
            "source_chunk": src["source_chunk"],
            "stem": src["stem"],
            "official_answer": official,
            "rubric_points": rubric,
            "rubric_point_count": len(rubric),
            "rubric_total_score": round(sum(p["point_score"] for p in rubric), 2),
            "answers": [],
        }

        for ans in draft["answers"]:
            # --- validate expected_failures point ids ---
            seen = set()
            for f in ans["expected_failures"]:
                tp = f["target_point"]
                assert tp in rubric_ids, f"{ans['answer_id']}: unknown point {tp}"
                assert tp not in seen, f"{ans['answer_id']}: duplicate point {tp}"
                seen.add(tp)
                assert f["type"] in pack["failure_types"], f"bad type {f['type']}"
                assert f["expected_credit"] in ("none", "partial")
                if f["expected_credit"] == "partial":
                    assert f["expected_items_hit"] < f["expected_items_total"]

            # --- leakage ---
            p, r, j = multiset_pr(ngrams(ans["answer_text"]), off_ng)
            passed = max(p, r, j) < LEAK_THRESHOLD
            ans_out = dict(ans)
            ans_out["expected_full_credit_points"] = sorted(
                rubric_ids - seen, key=lambda x: (x.split(".")[0], int(x.split(".")[1]))
            )
            ans_out["failure_type_counts"] = dict(
                Counter(f["type"] for f in ans["expected_failures"])
            )
            # --- derived expected score (踩点累加, 不封顶; 仅作一致性自检信号) ---
            by_id = {p["point_id"]: p for p in rubric}
            fail_by_id = {f["target_point"]: f for f in ans["expected_failures"]}
            earned = 0.0
            for pid, pt in by_id.items():
                f = fail_by_id.get(pid)
                if f is None:
                    earned += pt["point_score"]
                elif f["expected_credit"] == "partial":
                    earned += pt["point_score"] * f["expected_items_hit"] / f["expected_items_total"]
            ans_out["expected_point_score"] = round(earned, 3)
            ans_out["rubric_total_score"] = q_out["rubric_total_score"]
            ans_out["expected_score_ratio"] = round(earned / q_out["rubric_total_score"], 4)
            ans_out["leakage_4gram"] = {
                "precision": round(p, 4),
                "recall": round(r, 4),
                "jaccard": round(j, 4),
                "pass": passed,
            }
            q_out["answers"].append(ans_out)
            leak_report["rows"].append(
                {
                    "question_id": qid,
                    "answer_id": ans["answer_id"],
                    "ability_label": ans["ability_label"],
                    "answer_chars": len(norm(ans["answer_text"])),
                    "official_chars": len(norm(official)),
                    "precision": round(p, 4),
                    "recall": round(r, 4),
                    "jaccard": round(j, 4),
                    "threshold": LEAK_THRESHOLD,
                    "pass": passed,
                }
            )
            assert passed, f"LEAKAGE FAIL {ans['answer_id']}: p={p:.3f} r={r:.3f} j={j:.3f}"

        pack["questions"].append(q_out)

        # incremental flush after each question
        pack["counts"] = {
            "questions": len(pack["questions"]),
            "answers": sum(len(q["answers"]) for q in pack["questions"]),
            "rubric_points": sum(q["rubric_point_count"] for q in pack["questions"]),
            "expected_failures": sum(
                len(a["expected_failures"]) for q in pack["questions"] for a in q["answers"]
            ),
            "expected_failures_by_type": dict(
                Counter(
                    f["type"]
                    for q in pack["questions"]
                    for a in q["answers"]
                    for f in a["expected_failures"]
                )
            ),
        }
        (HERE / "student_army_gold.v2.pilot.json").write_text(
            json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        leak_report["counts"] = {
            "rows": len(leak_report["rows"]),
            "passed": sum(1 for r in leak_report["rows"] if r["pass"]),
            "max_precision": max(r["precision"] for r in leak_report["rows"]),
            "max_recall": max(r["recall"] for r in leak_report["rows"]),
            "max_jaccard": max(r["jaccard"] for r in leak_report["rows"]),
        }
        (HERE / "leakage_check.json").write_text(
            json.dumps(leak_report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"[flush] {qid}: {len(q_out['answers'])} answers, {len(rubric)} rubric points")
        for row in leak_report["rows"]:
            if row["question_id"] == qid:
                print(
                    f"   {row['answer_id']:<22} P={row['precision']:.3f} "
                    f"R={row['recall']:.3f} J={row['jaccard']:.3f} pass={row['pass']}"
                )

    print("\ncounts:", json.dumps(pack["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
