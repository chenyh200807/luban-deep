#!/usr/bin/env python3
"""Generate Qwen shadow few-shot policy examples + prompt from the policy queue.

Teaches the production-shadow Qwen how to handle the held-out boundary cases
conservatively (k/n, no near-synonym auto-hit, flag high_risk/needs_policy_review).
Does NOT fabricate final hit/miss truth — unresolved stay needs_policy_review.
shadow_only asset; NOT wired into runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_AXIS = {
    "list_rule_denominator": {
        "rule": "list_rule_denominator_v1",
        "wrong_tendency": "把近乎答全的列举题凑整成 hit;或自行拆/并项改变分母 n。",
        "correct_decision": "needs_policy_review",
        "correct_rationale": "分母 n=采分点 label 的标准列举项数;k=学生逐字命中的标准项数;partial=k/n×max。命中项数有争议时标 needs_policy_review,不凑整成 hit。",
        "evidence_span_requirement": "每个计入的命中项必须有学生答案 span 逐字支撑,近义不算。",
        "why_this_matters": "list_rule 凑整是当前 Qwen 与陪审唯一的系统性分歧来源;k/n 守住才不会虚高。",
    },
    "exact_required_near_synonym": {
        "rule": "exact_required_near_synonym_v1",
        "wrong_tendency": "学生缺官方术语原文/写近义/缺修饰语时仍判 hit。",
        "correct_decision": "needs_policy_review",
        "correct_rationale": "exact_required 默认 high_risk_review,不自动 hit;只有官方答案明示'须含X/等'且学生逐字写出核心术语,才转 semantic_allowed,否则保守。",
        "evidence_span_requirement": "核心官方术语原文必须在 span 中逐字出现;泛称/大白话不支撑。",
        "why_this_matters": "踩字纪律的底线;近义放水会教坏学生(真考不给分)。",
    },
}


def build(cases: list[dict]) -> list[dict]:
    out = []
    for i, c in enumerate(cases):
        axis = c.get("conflict_axis", "")
        tmpl = _AXIS.get(axis, _AXIS["exact_required_near_synonym"])
        out.append({
            "example_id": f"pq-{i:02d}",
            "policy_rule_id": tmpl["rule"],
            "case_id": c["case_id"], "student_id": c["student_id"], "point_id": c["point_id"],
            "scoring_point": c.get("scoring_point"),
            "student_answer_excerpt": (c.get("student_answer") or "")[:120],
            "wrong_tendency": tmpl["wrong_tendency"],
            "correct_decision": tmpl["correct_decision"],
            "correct_rationale": tmpl["correct_rationale"],
            "evidence_span_requirement": tmpl["evidence_span_requirement"],
            "why_this_matters": tmpl["why_this_matters"],
        })
    return out


PROMPT = """# Qwen shadow few-shot policy prompt（held-out 12 unresolved 蒸馏)

> shadow_only。仅作 production-shadow Qwen prompt 资产,**不自动接入线上配置 / 不进 runtime**。

## 总原则
1. **官方答案 / 采分点优先**:得分以官方标准答案与采分点 label 为准。
2. **学生答案 span 必须支撑**:任何 hit/partial 必须引用学生答案精确原文 span;无 span 不给分(unsupported=true)。
3. **大白话/近义不自动给 exact_required**:exact_required 必须逐字写出官方术语原文,缺则默认 high_risk_review。
4. **list_rule 必须 k/n**:分母 n=采分点列举项数,k=逐字命中项数,partial=k/n×max;不凑整、不自拆项。
5. **吃不准标 high_risk / needs_policy_review**,不机械判。

## 反例(从 held-out 边界点提炼)
- **partial(score=0) vs miss(score=0)**:hit-label 差异但 score 相同 → 不是重大错误,按 score。
- **list_rule 分母争议**(Q18 质量管理记录/外墙复试项目):命中项数口径不一致 → 按 label 列举项 k/n,缺项 partial,不凑整。
- **exact_required 近义边界**(Q10 '施工升降机' 缺'人货两用';'LED灯' of 'LED灯/节能灯等'):缺修饰语/开放列举 → needs_policy_review,不自动 hit。
- **泛称不等于具体术语**(Q13 '相关参建单位' 未逐字列建设/监理/施工/设计):泛称/口号 span 不支撑 exact_required hit。

## 输出 schema（每点一对象）
`{hit, score, confidence, evidence_span, rationale, policy_type, high_risk, needs_policy_review, review_reason}`
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    base = Path("artifacts/luban_consensus_gold/policy_queue_20260603")
    ap.add_argument("--cases", default=str(base / "policy_queue_cases.json"))
    ap.add_argument("--out-dir", default=str(base))
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    examples = build(cases)
    out = Path(args.out_dir)
    (out / "qwen_fewshot_policy_examples.json").write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "qwen_fewshot_policy_prompt.md").write_text(PROMPT, encoding="utf-8")
    print(f"few-shot examples: {len(examples)} -> {out}/qwen_fewshot_policy_examples.json")
    print(f"prompt -> {out}/qwen_fewshot_policy_prompt.md")
    # invariant: no example claims a fabricated hit/miss gold
    bad = [e for e in examples if e["correct_decision"] not in ("needs_policy_review",)]
    print("examples asserting non-review gold:", len(bad), "(must be 0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
