#!/usr/bin/env python3
"""Generate the Qwen list_rule-ONLY shadow few-shot prompt for the A/B round.

Background: the full few-shot A/B was NO-GO — list_rule guidance helped (16→14)
but exact_required/近义/全局 review guidance destabilized Qwen's already-perfect
exact_required (0→2, 1 major violation). This round keeps ONLY the list_rule口径
guidance and drops everything exact_required / 近义 / 全局 review related.

ALLOWED in the prompt:
  - list_rule_denominator_v1: n=标准列举项数, k=逐字命中项数, partial=k/n×max
  - list_rule_label_vs_score_v1: partial(score=0) vs miss(score=0) label-only 差异单独记录, 不当重大错误
  - evidence span 必须来自学生答案
  - 不凑整 / 不自拆并项 / 不把泛称当具体列举项
PROHIBITED in the prompt:
  - exact_required_near_synonym_v1 / 任何 exact_required 新规则
  - 近义默认 review / 吃不准标 review / 任何全局 review 指令
  - held-out gold / human / ledger / artifact-first 结果泄漏
  - 12 unresolved 的最终答案或 consensus gold 标签

shadow_only asset; NOT wired into runtime. directional/shadow.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Leak-safe: ONLY abstract list_rule scoring policy. No held-out case ids,
# no student text, no hit/score gold, no exact_required guidance, no global review.
PROMPT = """# Qwen list_rule-only shadow 政策 prompt（A/B 注入版）

> shadow_only。**抽象 list_rule 评分政策,无任何 held-out 具体题号/学生/点的 hit/score**——避免目标 gold 泄漏。
> 仅在 A/B shadow 注入 Qwen prompt,不接 production runtime / 不接 RAG。
> 本 prompt **只规范 list_rule(列举型采分点)口径**;其余采分点按官方答案常规阅卷,不额外加规则。

## list_rule 评分政策原则（只针对列举型采分点）
1. **官方答案 / 采分点 label 优先**:list_rule 的标准列举项以官方标准答案与采分点 label 为唯一依据。
2. **学生答案 span 必须支撑**:任何计入命中的列举项,必须引用学生答案精确原文 span;无可引用原文 → 该项不计命中。
3. **按 k/n 给分**:分母 n = 采分点 label 的标准列举项数;k = 学生逐字命中的标准项数;partial 分 = k/n × max_score。
4. **不凑整、不自拆并项、不把泛称当列举项**:不把近乎答全凑整成满分 hit;不自行拆分或合并标准项改变分母 n;"相关单位""专门工具"等泛称 span 可支撑 rationale,但不替代具体标准列举项计入 k。
5. **label vs score 分开看**:同一 list_rule 点,partial(score=0) 与 miss(score=0) 只是 hit-label 不同、score 相同;这种 label-only 差异单独记录,**不当作重大评分错误**,以 score 为准。

## 输出 schema（每点一对象,只输出 JSON 数组）
`{point_id, hit(hit|partial|miss), score, confidence, evidence_span, rationale, policy_type, high_risk, needs_policy_review, review_reason, unsupported}`
"""

# Abstract list_rule-only worked examples (no held-out leakage: synthetic shapes only).
_EXAMPLES = [
    {
        "example_id": "lr-00",
        "policy_rule_id": "list_rule_denominator_v1",
        "shape": "学生答出标准 4 项中的 3 项,逐字命中。",
        "wrong_tendency": "凑整成满分 hit。",
        "correct_decision": "partial, score = 3/4 × max。",
        "rationale": "n=4 标准列举项,k=3 逐字命中 → partial=3/4×max,不凑整。",
    },
    {
        "example_id": "lr-01",
        "policy_rule_id": "list_rule_denominator_v1",
        "shape": "学生用泛称('相关单位')覆盖一个本应逐项列举的标准项。",
        "wrong_tendency": "把泛称算作命中该标准项。",
        "correct_decision": "该项不计入 k。",
        "rationale": "泛称不替代具体标准列举项;span 仅支撑 rationale,不计命中。",
    },
    {
        "example_id": "lr-02",
        "policy_rule_id": "list_rule_label_vs_score_v1",
        "shape": "同一 list_rule 点,一方标 partial(score=0),一方标 miss(score=0)。",
        "wrong_tendency": "把 label 差异当作重大评分错误。",
        "correct_decision": "单独记录 label-only 差异,以 score(均=0)为准。",
        "rationale": "partial(0) 与 miss(0) score 相同,非重大错误。",
    },
]


def build_prompt() -> str:
    return PROMPT


def build_examples() -> list[dict]:
    return list(_EXAMPLES)


_FORBIDDEN_SUBSTRINGS = (
    "exact_required_near_synonym",
    "近义",
    "吃不准",
    "human_hit",
    "human_score",
    "ground_truth_ledger",
    "ledger_point_rows",
    "consensus_gold_v1",
)


def leak_check(text: str) -> list[str]:
    """Return list of leak/forbidden findings in the prompt text (must be empty)."""
    findings = []
    for tok in _FORBIDDEN_SUBSTRINGS:
        if tok in text:
            findings.append(f"forbidden token: {tok}")
    # held-out case ids like Q18-1A2, Q10-NA
    if re.search(r"Q\d+-1A\d+|Q\d+-NA", text):
        findings.append("held-out case id leak")
    # any global review directive
    if re.search(r"默认\s*review|标\s*review|review\b.*默认", text):
        findings.append("global review directive")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out-dir",
        default="artifacts/luban_consensus_gold/qwen_list_rule_only_ab_20260603",
    )
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    prompt = build_prompt()
    examples = build_examples()

    findings = leak_check(prompt)
    (out / "qwen_list_rule_only_run_prompt.md").write_text(prompt, encoding="utf-8")
    (out / "qwen_list_rule_only_examples.json").write_text(
        json.dumps(examples, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"prompt -> {out}/qwen_list_rule_only_run_prompt.md")
    print(f"examples: {len(examples)} -> {out}/qwen_list_rule_only_examples.json")
    print(f"leak_check findings: {len(findings)} (must be 0): {findings}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
