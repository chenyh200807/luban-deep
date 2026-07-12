#!/usr/bin/env python3
"""
Battle2 S2-T3 — mcq 判分反馈输出减半差分质量门（legacy 7 段 vs compact 4+1 段）。

用法：
  # 0) 门自证（零 LLM 零成本，必须先跑；喂"答案字母改错的合成输出"断言门必红）
  python scripts/run_mcq_feedback_output_ab.py --self-red-test

  # 1) open_world 臂内抖动基线（单臂 legacy n=5，指挥官改判：先测基线再定门口径，禁事后放水）
  python scripts/run_mcq_feedback_output_ab.py --openworld-baseline --n 5

  # 2) 双臂差分（billable：~24例×2臂×3次；跑前过 eval-design 排雷单）
  python scripts/run_mcq_feedback_output_ab.py --run --n 3 --out artifacts/mcq_feedback_ab_report.json

门设计（指挥官裁决后口径）：
  blocking 只留四件硬事：
    B1 正确答案字母在场（从"正确答案/阅卷结论"段确定性 regex 抽取==gold，非 LLM judge）
    B2 套话黑名单零命中（deterministic 六句原文 + 多刷题/注意审题）
    B3 必备段非空（raw 输出 4 必备段齐；比 runtime 的 repair+模板兜底链更严）
    B4 corpus 级：compact 臂输出 tok p50 ≤ --p50-target(700) 且较 legacy 降幅 ≥ --min-reduction(45%)
       + repair 触发率(=B3 缺段率) compact ≤ legacy
  advisory（降级断言，不阻断）：
    A1 每个错选字母出现且所在句含该选项文本关键词
    A2 grounding 带【教材要点 Ln】时输出至少引用 1 处
  停手红线（任何一例违反=立即 FAIL 全局）：
    R1 判分裁决字段结构性不变——process 前后 question_context 的
       is_correct/score/correct_answer（含 items）深比较必须一致
  open_world 用例：两臂各 n 次多数票，新臂==旧臂==gold（--openworld-gate strict）；
    若基线抖动不稳，改 --openworld-gate stability（新臂稳定性≥旧臂，抖动单独立案）。

臂公平：同模型同温度（不借战役改温度），graded_context+grounding 冻结进 fixture。
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

FIXTURES = REPO_ROOT / "eval" / "fixtures" / "mcq_feedback_ab" / "cases.jsonl"

# deterministic 路径旧六条套话原文（deep_question.py 旧 1456-1463 行）+ prompt 明令禁止的空话。
BOILERPLATE_BLACKLIST: tuple[str, ...] = (
    "抓住题干限定词，先判断它问的是对象、顺序、数值、范围还是做法是否妥当",
    "对照正确选项中的规范关键词，不用相近概念替代标准表述",
    "排除与题干对象不一致、顺序颠倒、数值范围错误或绝对化的干扰项",
    "看到熟悉词就选，忽略题干真正限定的工程部位或构造要求",
    "把“可以/应当/不得”“同时/顺序”“不小于/不大于”等关键词看反",
    "多选或判断类题容易漏选一个正确约束，或把相关但不属于本题问法的选项带入",
    "多刷题",
    "注意审题",
)

# 文案铁律（记忆 luban-copy-tone-no-see-through-words）。
FORBIDDEN_TONE_WORDS: tuple[str, ...] = ("看穿", "识破", "揭穿", "露馅")

_REQUIRED_KEYS = ("verdict", "correct_answer", "why_wrong", "next_practice")

_ANSWER_SECTION_RE = re.compile(
    r"#+\s*(?:正确答案|阅卷结论)[^\n]*\n(.*?)(?=\n\s*#+\s|\Z)", re.DOTALL
)
_LETTER_RE = re.compile(r"[A-E]")
_ANSWER_DECL_RE = re.compile(
    r"(?:正确答案|答案)(?:是|为|应为|应该是|：|:)?\s*(?:\*\*)?\s*([A-E](?:\s*[、，,/\s]\s*[A-E])*)"
)


def count_tokens(text: str) -> int:
    import tiktoken

    return len(tiktoken.get_encoding("cl100k_base").encode(str(text or "")))


def extract_adjudicated_letters(output_text: str) -> list[str]:
    """确定性抽取输出宣告的正确答案字母（非 LLM judge，防循环度量）。

    先在"正确答案/阅卷结论"heading 段内找"正确答案是/为 X"式声明；
    段内无显式声明时回退取该段前 80 字符内的裸字母序列。
    """
    text = str(output_text or "")
    for section in _ANSWER_SECTION_RE.finditer(text):
        body = section.group(1)
        decl = _ANSWER_DECL_RE.search(body)
        if decl:
            return sorted(set(_LETTER_RE.findall(decl.group(1).upper())))
    decl = _ANSWER_DECL_RE.search(text)
    if decl:
        return sorted(set(_LETTER_RE.findall(decl.group(1).upper())))
    for section in _ANSWER_SECTION_RE.finditer(text):
        head = section.group(1).strip()[:80]
        letters = sorted(set(_LETTER_RE.findall(head.upper())))
        if letters:
            return letters
    return []


def check_case_blocking(output_text: str, case: dict[str, Any]) -> list[str]:
    """单例 blocking 检查，返回失败项名单（空=过门）。"""
    failures: list[str] = []
    text = str(output_text or "")
    gold_letters = list(case.get("gold", {}).get("correct_letters") or [])

    # B1 正确答案字母在场（batch 用 per_item 并集；open_world 的 gold 走多数票在 corpus 层判）
    if gold_letters and case.get("scenario") != "open_world":
        adjudicated = extract_adjudicated_letters(text)
        if case.get("scenario") == "batch_4":
            missing = [l for l in gold_letters if l not in text]
            if missing:
                failures.append(f"B1_correct_letter_missing:{','.join(missing)}")
        elif adjudicated != gold_letters:
            failures.append(
                f"B1_correct_letter_mismatch:got={','.join(adjudicated) or '(none)'}:want={','.join(gold_letters)}"
            )

    # B2 套话黑名单零命中
    for sentence in BOILERPLATE_BLACKLIST:
        if sentence in text:
            failures.append(f"B2_boilerplate_hit:{sentence[:12]}")
    for word in FORBIDDEN_TONE_WORDS:
        if word in text:
            failures.append(f"B2_forbidden_tone:{word}")

    # B3 必备段非空（raw 输出即须齐 4 必备段；runtime 还有 repair+模板兜底二道防线）
    from deeptutor.agents.question.agents.submission_grader_schema import (
        parse_explanation_sections,
    )

    context = case.get("arm_input", {}).get("question_context", {})
    parsed = parse_explanation_sections(
        text,
        question_type=str(context.get("question_type") or ""),
        is_correct=context.get("is_correct") if isinstance(context.get("is_correct"), bool) else None,
    )
    for key in _REQUIRED_KEYS:
        if not str(parsed.sections.get(key, "")).strip():
            failures.append(f"B3_required_section_empty:{key}")
    return failures


def check_case_advisory(output_text: str, case: dict[str, Any]) -> list[str]:
    """advisory 检查（指挥官改判：脆断言降级，不阻断，只记名单）。"""
    notes: list[str] = []
    text = str(output_text or "")
    context = case.get("arm_input", {}).get("question_context", {})
    options = context.get("options") or {}
    for letter in case.get("gold", {}).get("wrong_selected") or []:
        if letter not in text:
            notes.append(f"A1_wrong_letter_absent:{letter}")
            continue
        option_text = str(options.get(letter) or "").strip()
        keyword = option_text[:4]
        if keyword:
            hit = any(
                letter in sentence and keyword in sentence
                for sentence in re.split(r"[。\n；;]", text)
            )
            if not hit:
                notes.append(f"A1_wrong_letter_sentence_lacks_option_text:{letter}")
    grounding = str(case.get("arm_input", {}).get("grounding_context") or "")
    if "【教材要点" in grounding and "【教材要点" not in text:
        notes.append("A2_grounding_citation_missing")
    return notes


def check_authority_immutable(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """R1 停手红线：判分裁决字段结构性不变（含 items 逐条）。"""
    violations: list[str] = []

    def _cmp(prefix: str, lhs: dict[str, Any], rhs: dict[str, Any]) -> None:
        for key in ("is_correct", "score", "correct_answer"):
            if lhs.get(key) != rhs.get(key):
                violations.append(f"R1_authority_mutated:{prefix}{key}")

    _cmp("", before, after)
    before_items = before.get("items") or []
    after_items = after.get("items") or []
    if len(before_items) != len(after_items):
        violations.append("R1_authority_mutated:items_length")
    else:
        for index, (lhs, rhs) in enumerate(zip(before_items, after_items)):
            if isinstance(lhs, dict) and isinstance(rhs, dict):
                _cmp(f"items[{index}].", lhs, rhs)
    return violations


@dataclass
class CorpusVerdict:
    blocking_failures: dict[str, list[str]] = field(default_factory=dict)
    advisory_notes: dict[str, list[str]] = field(default_factory=dict)
    legacy_p50: float = 0.0
    compact_p50: float = 0.0
    reduction: float = 0.0
    legacy_miss_rate: float = 0.0
    compact_miss_rate: float = 0.0
    openworld: dict[str, Any] = field(default_factory=dict)
    passed: bool = False


def evaluate_corpus(
    cases: list[dict[str, Any]],
    legacy_outputs: dict[str, list[str]],
    compact_outputs: dict[str, list[str]],
    *,
    p50_target: int = 700,
    min_reduction: float = 0.45,
    openworld_gate: str = "strict",
) -> CorpusVerdict:
    verdict = CorpusVerdict()
    case_by_id = {case["case_id"]: case for case in cases}

    def _miss_rate(outputs: dict[str, list[str]]) -> float:
        total, missed = 0, 0
        for case_id, texts in outputs.items():
            for text in texts:
                total += 1
                if any(
                    f.startswith("B3_") for f in check_case_blocking(text, case_by_id[case_id])
                ):
                    missed += 1
        return missed / total if total else 0.0

    # per-case blocking（compact 臂全量；legacy 臂只跑 B2/B3 语义之外的回归不设新门）
    for case_id, texts in compact_outputs.items():
        case = case_by_id[case_id]
        for run_index, text in enumerate(texts):
            failures = check_case_blocking(text, case)
            if failures:
                verdict.blocking_failures.setdefault(f"{case_id}#r{run_index}", []).extend(failures)
            notes = check_case_advisory(text, case)
            if notes:
                verdict.advisory_notes.setdefault(f"{case_id}#r{run_index}", []).extend(notes)

    # B4 token 降幅（corpus 级 p50）
    legacy_tokens = [
        count_tokens(text) for texts in legacy_outputs.values() for text in texts
    ]
    compact_tokens = [
        count_tokens(text) for texts in compact_outputs.values() for text in texts
    ]
    if legacy_tokens and compact_tokens:
        verdict.legacy_p50 = statistics.median(legacy_tokens)
        verdict.compact_p50 = statistics.median(compact_tokens)
        verdict.reduction = (
            1 - verdict.compact_p50 / verdict.legacy_p50 if verdict.legacy_p50 else 0.0
        )
        if verdict.compact_p50 > p50_target:
            verdict.blocking_failures.setdefault("_corpus", []).append(
                f"B4_p50_above_target:{verdict.compact_p50:.0f}>{p50_target}"
            )
        if verdict.reduction < min_reduction:
            verdict.blocking_failures.setdefault("_corpus", []).append(
                f"B4_reduction_below_floor:{verdict.reduction:.2%}<{min_reduction:.0%}"
            )
    verdict.legacy_miss_rate = _miss_rate(legacy_outputs)
    verdict.compact_miss_rate = _miss_rate(compact_outputs)
    if verdict.compact_miss_rate > verdict.legacy_miss_rate:
        verdict.blocking_failures.setdefault("_corpus", []).append(
            f"B4_repair_rate_regressed:{verdict.compact_miss_rate:.2%}>{verdict.legacy_miss_rate:.2%}"
        )

    # open_world 多数票裁决一致性
    for case in cases:
        if case.get("scenario") != "open_world":
            continue
        case_id = case["case_id"]
        gold = list(case.get("gold", {}).get("correct_letters") or [])

        def _majority(texts: list[str]) -> tuple[list[str], float]:
            votes = [tuple(extract_adjudicated_letters(t)) for t in texts]
            if not votes:
                return [], 0.0
            top, top_count = Counter(votes).most_common(1)[0]
            return list(top), top_count / len(votes)

        legacy_major, legacy_stability = _majority(legacy_outputs.get(case_id, []))
        compact_major, compact_stability = _majority(compact_outputs.get(case_id, []))
        entry = {
            "gold": gold,
            "legacy_majority": legacy_major,
            "legacy_stability": legacy_stability,
            "compact_majority": compact_major,
            "compact_stability": compact_stability,
        }
        verdict.openworld[case_id] = entry
        if openworld_gate == "strict":
            if not (compact_major == legacy_major and (not gold or compact_major == gold)):
                verdict.blocking_failures.setdefault(case_id, []).append(
                    f"OW_majority_mismatch:{entry}"
                )
        else:  # stability：抖动是存量病单独立案，门口径=新臂稳定性不劣于旧臂且多数票一致
            if compact_stability < legacy_stability or compact_major != legacy_major:
                verdict.blocking_failures.setdefault(case_id, []).append(
                    f"OW_stability_regressed:{entry}"
                )

    verdict.passed = not verdict.blocking_failures
    return verdict


# ─────────────────────────────────────────────────────────────────────────────
# 自证红测（可证伪性自检，零 LLM）
# ─────────────────────────────────────────────────────────────────────────────

def _synthesize_valid_output(case: dict[str, Any]) -> str:
    context = case["arm_input"]["question_context"]
    gold = case["gold"]
    letters = "、".join(gold.get("correct_letters") or ["B"])
    options = context.get("options") or {}
    option_text = str(options.get((gold.get("correct_letters") or ["B"])[0], "")).strip()
    wrong = (gold.get("wrong_selected") or [""])[0]
    wrong_text = str(options.get(wrong, "")).strip()
    grounding_cite = "【教材要点 L1】" if "【教材要点" in str(case["arm_input"].get("grounding_context") or "") else ""
    return (
        f"### 阅卷结论\n本题答错，你答了 {wrong or 'X'}、正确答案是 {letters}。\n\n"
        f"### 正确答案\n正确答案是 {letters}（{option_text}）。依据教材规定{grounding_cite}，考点：本题规范口径。\n\n"
        f"### 为什么错\n你选的 {wrong}（{wrong_text}）把相近口径当成了规范要求，属概念混淆。\n\n"
        f"### 下一步\n现在把正确口径抄写 1 遍，再做 1 道同考点题。\n\n"
        f"### 逐项解析\n你选的 {wrong}（{wrong_text}）错：不符合规范表述；{letters}（{option_text}）正确：直接对应教材口径；其余干扰项一句话带过：均与本题口径不一致。\n"
    )


def run_self_red_test() -> int:
    cases = load_cases()
    sample = [c for c in cases if c["scenario"] == "single_wrong"][:3]
    failures: list[str] = []

    for case in sample:
        valid = _synthesize_valid_output(case)
        if check_case_blocking(valid, case):
            failures.append(
                f"green-baseline broken: {case['case_id']} {check_case_blocking(valid, case)}"
            )

        # 红测 1：答案字母改错（指挥官指定的自证）
        gold_letter = case["gold"]["correct_letters"][0]
        wrong_letter = next(l for l in "ABCDE" if l != gold_letter and l in (case["arm_input"]["question_context"].get("options") or {}))
        corrupted = valid.replace(f"正确答案是 {gold_letter}", f"正确答案是 {wrong_letter}")
        if not any(f.startswith("B1_") for f in check_case_blocking(corrupted, case)):
            failures.append(f"RED-TEST FAILED (B1 not triggered): {case['case_id']}")

        # 红测 2：注入套话
        polluted = valid + "\n### 易错点\n- 看到熟悉词就选，忽略题干真正限定的工程部位或构造要求。\n"
        if not any(f.startswith("B2_") for f in check_case_blocking(polluted, case)):
            failures.append(f"RED-TEST FAILED (B2 not triggered): {case['case_id']}")

        # 红测 3：删掉必备段（下一步）
        truncated = valid.split("### 下一步")[0]
        if not any(f.startswith("B3_") for f in check_case_blocking(truncated, case)):
            failures.append(f"RED-TEST FAILED (B3 not triggered): {case['case_id']}")

    # 红测 4：B4 降幅门——compact 比 legacy 更长必须红
    two = {c["case_id"]: [_synthesize_valid_output(c)] for c in sample}
    longer = {cid: [texts[0] * 3] for cid, texts in two.items()}
    verdict = evaluate_corpus(sample, legacy_outputs=two, compact_outputs=longer)
    if not any(
        f.startswith("B4_") for f in verdict.blocking_failures.get("_corpus", [])
    ):
        failures.append("RED-TEST FAILED (B4 not triggered on longer compact arm)")

    # 红测 5：R1 authority 红线
    before = {"is_correct": False, "score": 0.0, "correct_answer": "B", "items": []}
    after = dict(before, is_correct=True)
    if not check_authority_immutable(before, after):
        failures.append("RED-TEST FAILED (R1 not triggered on mutated is_correct)")

    if failures:
        print("SELF-RED-TEST FAIL")
        for line in failures:
            print("  -", line)
        return 1
    print("SELF-RED-TEST PASS: 门可证伪（B1/B2/B3/B4/R1 全部能红，合法样例全绿）")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# live 双臂 / 单臂基线
# ─────────────────────────────────────────────────────────────────────────────

def load_cases() -> list[dict[str, Any]]:
    cases = [
        json.loads(line)
        for line in FIXTURES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(cases) < 24:
        raise SystemExit(f"fixture corpus too small: {len(cases)} < 24")
    return cases


async def _run_arm(
    cases: list[dict[str, Any]], *, compact: bool, n: int
) -> tuple[dict[str, list[str]], list[str]]:
    """跑一臂。返回 (case_id -> outputs, 红线违规名单)。"""
    import deeptutor.agents.question.agents.submission_grader_agent as agent_module
    from deeptutor.services.llm.config import get_llm_config

    # 单一 decider 的输入端钉死（不写 .env、不留残留）
    agent_module.env_flag = (  # type: ignore[assignment]
        lambda name, *, default=False: compact
        if name == "DEEPTUTOR_MCQ_FEEDBACK_COMPACT"
        else default
    )
    llm_config = get_llm_config()
    outputs: dict[str, list[str]] = {}
    redline: list[str] = []
    for case in cases:
        agent = agent_module.SubmissionGraderAgent(
            language="zh",
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            api_version=getattr(llm_config, "api_version", None),
        )
        for _ in range(n):
            context = copy.deepcopy(case["arm_input"]["question_context"])
            before = copy.deepcopy(context)
            text = await agent.process(
                user_message=case["arm_input"]["user_message"],
                question_context=context,
                history_context=case["arm_input"].get("history_context", ""),
                grounding_context=case["arm_input"].get("grounding_context", ""),
                trace_collector={},
            )
            violations = check_authority_immutable(before, context)
            if violations:
                redline.extend(f"{case['case_id']}:{v}" for v in violations)
            outputs.setdefault(case["case_id"], []).append(text)
    return outputs, redline


def run_live(args: argparse.Namespace) -> int:
    cases = load_cases()
    if args.openworld_baseline:
        ow_cases = [c for c in cases if c["scenario"] == "open_world"]
        outputs, redline = asyncio.run(_run_arm(ow_cases, compact=False, n=args.n))
        report: dict[str, Any] = {"mode": "openworld_baseline", "n": args.n, "cases": {}}
        for case in ow_cases:
            votes = [extract_adjudicated_letters(t) for t in outputs.get(case["case_id"], [])]
            top, top_count = Counter(tuple(v) for v in votes).most_common(1)[0]
            report["cases"][case["case_id"]] = {
                "gold": case["gold"]["correct_letters"],
                "votes": votes,
                "majority": list(top),
                "stability": top_count / len(votes) if votes else 0.0,
            }
        report["redline"] = redline
        print(json.dumps(report, ensure_ascii=False, indent=2))
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1 if redline else 0

    legacy_outputs, redline_a = asyncio.run(_run_arm(cases, compact=False, n=args.n))
    compact_outputs, redline_b = asyncio.run(_run_arm(cases, compact=True, n=args.n))
    redline = redline_a + redline_b
    verdict = evaluate_corpus(
        cases,
        legacy_outputs,
        compact_outputs,
        p50_target=args.p50_target,
        min_reduction=args.min_reduction,
        openworld_gate=args.openworld_gate,
    )
    report = {
        "mode": "dual_arm",
        "n": args.n,
        "passed": verdict.passed and not redline,
        "redline_violations": redline,
        "legacy_p50_tokens": verdict.legacy_p50,
        "compact_p50_tokens": verdict.compact_p50,
        "reduction": verdict.reduction,
        "legacy_section_miss_rate": verdict.legacy_miss_rate,
        "compact_section_miss_rate": verdict.compact_miss_rate,
        "openworld": verdict.openworld,
        "blocking_failures": verdict.blocking_failures,
        "advisory_notes": verdict.advisory_notes,
        "outputs": {
            "legacy": legacy_outputs,
            "compact": compact_outputs,
        },
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "outputs"}, ensure_ascii=False, indent=2
        )
    )
    if redline:
        print("停手红线触发：判分裁决字段被改写。禁止合并，立即上报。")
        return 2
    return 0 if verdict.passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-red-test", action="store_true")
    parser.add_argument("--openworld-baseline", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--p50-target", type=int, default=700)
    parser.add_argument("--min-reduction", type=float, default=0.45)
    parser.add_argument("--openworld-gate", choices=("strict", "stability"), default="strict")
    parser.add_argument("--out", default="artifacts/mcq_feedback_ab_report.json")
    args = parser.parse_args()
    if args.self_red_test:
        return run_self_red_test()
    if args.openworld_baseline or args.run:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        return run_live(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
