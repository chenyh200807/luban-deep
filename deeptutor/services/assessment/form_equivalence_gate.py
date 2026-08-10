"""§6.5 平行复测等值配对的表单构建闸（表单 v2 难度锚修正）。

判据修正（§6.2-v2 选型定稿 + 题源盘点 2026-08-06 §1.5 实证）：

- **不读 questions_bank 的难度列**——该列量纲混乱（概率值/1208/112.34 等
  混排、235 行 NULL），不可用作等值锚。本模块从设计上没有任何读它的入口。
- **新判据 = 同 leaf + 同采分点 + 变体 anchor（kc:leaf + 真题年份题号）**：
  1. 同 leaf：kc 锚的 taxonomy leaf（如 ``kc:1A413030_103_0196:0`` 的
     ``1A413030_103_0196``）一致；无 kc 锚时以 ``fact_id`` 为 leaf 代理
     （编译轻练 fact 即 leaf 级真值）。
  2. 同采分点：``scoring_point``（显式）或 ``fact_id``，再退 ``rule_group``。
  3. 真题锚：双方都必须携带真题年份+题号引用（``{2021,第8题}`` /
     ``exam:2021:第8题`` / ``2022第(四)题`` 任一形态），且引用集有交集——
     同一真题锚即同一考法带，"复测题比原题容易"在锚层面被结构性排除。

任一条不满足 → 配对不等值；``validate_form_retest_pairs`` 在表单构建期
fail the form（宁可不出卷，不出假等值的"这次拿到了"回执）。

消费方：表单 manifest 构建线（S2 编排脚本）与后续 v2 表单签发闸。
纯函数零写入,无网络、无时钟。
"""

from __future__ import annotations

import re
from typing import Any


class FormEquivalenceGateError(ValueError):
    """表单构建闸:存在不等值的复测配对,整表拒签。"""


# kc/ca/cc 锚:leaf + 可选 sub-index。leaf 形如 1A413030_103_0196。
_KC_REF_RE = re.compile(r"(?:kc|ca|cc):([A-Za-z0-9]+(?:_[A-Za-z0-9]+)*)(?::(\d+))?")
# 真题引用三形态:{2021,第8题} / exam:2021:第8题 / 2022第(四)题。
_BRACE_EXAM_RE = re.compile(r"\{(\d{4})[,，]\s*([^}]+)\}")
_COLON_EXAM_RE = re.compile(r"exam:(\d{4}):([^\s+/)）]+)")
_BARE_EXAM_RE = re.compile(r"(?<!\d)(\d{4})(第[^\s+/{}]+)")


def parse_equivalence_anchor(anchor: str) -> dict[str, Any]:
    """解析锚串 → kc leaf 集 + 真题引用集。未知片段忽略,不猜。"""

    text = str(anchor or "")
    kc_leaves: list[str] = []
    kc_refs: list[str] = []
    for match in _KC_REF_RE.finditer(text):
        leaf = match.group(1)
        if leaf not in kc_leaves:
            kc_leaves.append(leaf)
        ref = leaf if match.group(2) is None else f"{leaf}:{match.group(2)}"
        if ref not in kc_refs:
            kc_refs.append(ref)
    exam_refs: list[tuple[str, str]] = []
    for pattern in (_BRACE_EXAM_RE, _COLON_EXAM_RE, _BARE_EXAM_RE):
        for match in pattern.finditer(text):
            ref = (match.group(1), match.group(2).strip())
            if ref[1] and ref not in exam_refs:
                exam_refs.append(ref)
    return {
        "kc_leaves": tuple(kc_leaves),
        "kc_refs": tuple(kc_refs),
        "exam_refs": tuple(exam_refs),
    }


def _anchor_text(descriptor: dict[str, Any]) -> str:
    return " + ".join(
        str(descriptor.get(key) or "")
        for key in ("anchor", "source_anchor")
        if str(descriptor.get(key) or "").strip()
    )


def equivalence_identity(descriptor: dict[str, Any]) -> dict[str, Any]:
    """把一道题的配对描述子归一为 {leaf, scoring_point, exam_refs}。

    描述子字段(manifest 构建线提供,元数据即编译轻练/变体池透传面):
    ``leaf``(显式 canonical leaf,可选) / ``anchor`` / ``source_anchor`` /
    ``fact_id`` / ``rule_group`` / ``scoring_point``(显式采分点,可选)。
    """

    parsed = parse_equivalence_anchor(_anchor_text(descriptor))
    explicit_leaf = str(descriptor.get("leaf") or "").strip()
    fact_id = str(descriptor.get("fact_id") or "").strip()
    if explicit_leaf:
        leaf = explicit_leaf
    elif parsed["kc_leaves"]:
        leaf = parsed["kc_leaves"][0]
    elif fact_id:
        leaf = f"fact:{fact_id}"
    else:
        leaf = ""
    scoring_point = (
        str(descriptor.get("scoring_point") or "").strip()
        or fact_id
        or str(descriptor.get("rule_group") or "").strip()
    )
    return {
        "leaf": leaf,
        "scoring_point": scoring_point,
        "exam_refs": parsed["exam_refs"],
    }


def retest_pair_verdict(
    original: dict[str, Any], retest: dict[str, Any]
) -> dict[str, Any]:
    """单对配对裁决;reasons 逐条给出不等值原因(空 = 等值)。"""

    left = equivalence_identity(original)
    right = equivalence_identity(retest)
    reasons: list[str] = []
    if not left["leaf"] or not right["leaf"]:
        reasons.append("leaf_missing")
    elif left["leaf"] != right["leaf"]:
        reasons.append(f"leaf_mismatch:{left['leaf']}≠{right['leaf']}")
    if not left["scoring_point"] or not right["scoring_point"]:
        reasons.append("scoring_point_missing")
    elif left["scoring_point"] != right["scoring_point"]:
        reasons.append(
            f"scoring_point_mismatch:{left['scoring_point']}≠{right['scoring_point']}"
        )
    if not left["exam_refs"]:
        reasons.append("real_exam_anchor_missing:original")
    if not right["exam_refs"]:
        reasons.append("real_exam_anchor_missing:retest")
    if (
        left["exam_refs"]
        and right["exam_refs"]
        and not (set(left["exam_refs"]) & set(right["exam_refs"]))
    ):
        reasons.append("real_exam_anchor_mismatch")
    return {
        "equivalent": not reasons,
        "reasons": tuple(reasons),
        "original": left,
        "retest": right,
    }


def validate_form_retest_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """表单构建闸:全部配对必须等值,否则 fail the form。

    ``pairs`` 逐条形如 ``{"pair_id": str, "original": {...}, "retest": {...}}``。
    返回 summary(全过时);任一对不等值 → :class:`FormEquivalenceGateError`,
    错误信息逐对带原因——绝不静默降级。空配对表也拒:没有配对证据的表单
    不得声称有平行复测供给。
    """

    if not pairs:
        raise FormEquivalenceGateError("no_retest_pairs_declared")
    failures: list[dict[str, Any]] = []
    for index, pair in enumerate(pairs):
        pair_id = str(pair.get("pair_id") or f"pair_{index + 1}")
        verdict = retest_pair_verdict(
            dict(pair.get("original") or {}), dict(pair.get("retest") or {})
        )
        if not verdict["equivalent"]:
            failures.append({"pair_id": pair_id, "reasons": list(verdict["reasons"])})
    if failures:
        detail = "; ".join(
            f"{item['pair_id']}[{','.join(item['reasons'])}]" for item in failures
        )
        raise FormEquivalenceGateError(f"retest_pairs_not_equivalent: {detail}")
    return {"pairs": len(pairs), "passed": len(pairs), "failures": []}


__all__ = [
    "FormEquivalenceGateError",
    "equivalence_identity",
    "parse_equivalence_anchor",
    "retest_pair_verdict",
    "validate_form_retest_pairs",
]
