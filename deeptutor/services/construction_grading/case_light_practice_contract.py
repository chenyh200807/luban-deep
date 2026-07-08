"""Case light-practice P-1 data contract — atomic scoring-point READ-VIEW + whitelist gate.

单一权威边界(读之前先读,别造第二套判分权威)
────────────────────────────────────────────────────────────────────────────
This module is the P-1 typed contract for the *case light-practice* capability
(runtime generation of a drill from an ALREADY-ATOMIZED case question). It does
exactly three jobs, all read-only / gate-only:

  1. Define the atomic scoring-point READ-VIEW schema ``luban_case_scoring_point.v1``
     — a projection over the compiled rubric library (``v_case_rubric_scored``) and
     the signed answer layer, enriched with the sub-question dimension (``sub_no``)
     and the light-practice metadata a generator needs.
  2. The code-level WHITELIST GATE (`assert_qid_allowed`) — a qid that has not been
     atomized (no sub-question qids, no per-point ``sub_no``, not channel-① sourced,
     not past the consistency screen) is REFUSED at the generation entrypoint. This
     is the §4 red line as *code*, not documentation.
  3. The generated-item → truth binding validators (RTG5/RTG8 seed) and the
     conjunction-group deterministic scorer (找错∧改正 must BOTH hit for full score).

THIS IS NOT A SECOND GRADING AUTHORITY.
  - Scoring authority stays with ``luban_grading_object.v1`` + ``rubric_grader_v1``.
  - This read-view grants NO official score, NO canonical/LearnerState write, NO
    runtime install. The claim-ceiling constants below are structurally False and the
    schema is registered as a T2 runtime-canonical (PINNED) contract — NOT a T1
    canonical grading object — precisely so it cannot compete with the grading spine.
  - The采分点 truth is the compiled grading pipeline; this contract only *reads*
    it into a shape the generator/gate can bind to.

Deterministic and pure: no LLM, no network, no DB.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

SCHEMA_ID = "luban_case_scoring_point.v1"

# ── Claim ceiling (structural constants — this projection grants no authority) ──
OFFICIAL_SCORE_ALLOWED = False
CANONICAL_WRITE_ALLOWED = False
RUNTIME_INSTALL_ALLOWED = False

# ── Authority-source domain (see AGENTS §5.7 / plan §2.5③) ─────────────────────
# 判分权威(计分通道①)只认 official_answer。溯源"这答案来自真题参考答案"是
# answer_key_authority 的合法取值(exam_reference_answer),两者不冲突、不混用。
CHANNEL_ONE_SCORING_AUTHORITY = "official_answer"
LEGIT_ANSWER_KEY_AUTHORITY = frozenset(
    {"official_answer", "exam_reference_answer", "textbook_cited"}
)

# Default location of the P-1 whitelist (register-before-use artifact).
WHITELIST_PATH = (
    Path(__file__).resolve().parent
    / "runtime_supply"
    / "case_light_practice"
    / "case_light_practice_whitelist.v0.json"
)


class PointType(str, Enum):
    """原子采分点类型(非平点结构靠 ordering_group/conjunction_group/list_cap 显式化)。"""

    PROCEDURE = "程序"
    CONDITION = "条件"
    RECORD = "记录"
    CONJUNCTION_MEMBER = "合取子"
    ENUMERATION_ITEM = "列举项"
    CALCULATION_STEP = "计算步"


class WhitelistError(RuntimeError):
    """Raised when a qid is not in the atomized-and-verified whitelist."""


class SourceBindingError(ValueError):
    """Raised when a generated item's option→scoring-point binding is invalid (RTG5)."""


class AuthoritySourceError(ValueError):
    """Raised when a scoring point does not carry the channel-① scoring authority."""


@dataclass(frozen=True)
class SourceRef:
    """教材/规范溯源锚(采分点与 acceptable_variant 都必须可溯源)。"""

    kind: str  # e.g. "textbook_cited" / "exam_reference_answer"
    ref: str  # human-locatable citation (教材页 / 规范条 / 真题年题号)


@dataclass(frozen=True)
class AcceptableVariant:
    """同义接受集条目——必带溯源,不许 LLM 自由扩表(plan §1.5C)。"""

    term: str
    source_ref: SourceRef


@dataclass(frozen=True)
class LubanCaseScoringPoint:
    """原子采分点只读视图。字段清单 == schema_registry ``luban_case_scoring_point.v1``
    的 canonical_fields(内省对账测试双向钉死,任一侧漂移即 FAIL)。"""

    point_id: str
    sub_no: str
    qid: str
    sub_qid: str
    statement: str
    authority_source: str
    point_type: PointType
    required_terms: tuple[str, ...]
    acceptable_variants: tuple[AcceptableVariant, ...]
    max_score: float
    textbook_source_refs: tuple[SourceRef, ...]
    answer_key_authority: str
    ordering_group: str | None = None
    conjunction_group: str | None = None
    list_cap: int | None = None

    def __post_init__(self) -> None:
        if self.authority_source != CHANNEL_ONE_SCORING_AUTHORITY:
            raise AuthoritySourceError(
                f"scoring point {self.point_id!r}: authority_source must be "
                f"{CHANNEL_ONE_SCORING_AUTHORITY!r} (channel-①), got {self.authority_source!r}"
            )
        if self.answer_key_authority not in LEGIT_ANSWER_KEY_AUTHORITY:
            raise AuthoritySourceError(
                f"scoring point {self.point_id!r}: answer_key_authority "
                f"{self.answer_key_authority!r} not in {sorted(LEGIT_ANSWER_KEY_AUTHORITY)}"
            )


# ── Whitelist gate (§2.5① — code-level, not documentary) ───────────────────────


def load_whitelist(path: Path | str = WHITELIST_PATH) -> frozenset[str]:
    """Load the set of qids allowed to enter runtime generation.

    Only entries with ``status == "allowed"`` count; anything else (pending, rejected,
    or absent) is refused. A missing/empty file yields an empty allow-set — fail
    CLOSED, never fail open.
    """
    p = Path(path)
    if not p.exists():
        return frozenset()
    data = json.loads(p.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    return frozenset(
        str(e["qid"]) for e in entries if e.get("status") == "allowed" and e.get("qid")
    )


def assert_qid_allowed(qid: str, whitelist: Iterable[str] | None = None) -> None:
    """Hard gate: refuse to generate a drill for a qid that is not atomized+verified.

    Raises :class:`WhitelistError` (never degrades, never "best effort") when ``qid``
    is not in the whitelist. This is the code-level enforcement of the §4 red line
    "未原子化的 qid 不许出轻练".
    """
    allowed = frozenset(whitelist) if whitelist is not None else load_whitelist()
    if qid not in allowed:
        raise WhitelistError(
            f"qid {qid!r} is not in the case-light-practice whitelist "
            f"(需已切小问 + 每采分点带 sub_no + authority_source==official_answer + 过一致性闸). "
            f"Refusing to generate — no degrade, no best-effort."
        )


# ── Generated-item → truth binding (RTG5 seed) ─────────────────────────────────


def validate_source_scoring_point_id(
    item: Mapping[str, object], points: Sequence[LubanCaseScoringPoint]
) -> None:
    """RTG5: every correct option binds a REAL scoring point of this (sub)question;
    every distractor carries NO scoring-point binding but DOES carry an error_code.

    Raises :class:`SourceBindingError` on any violation. This is the seed of the
    "生成忠实采分点硬门" — a generated item whose options do not bind the真采分点
    集合 must never be served.
    """
    point_ids = {p.point_id for p in points}
    if not point_ids:
        raise SourceBindingError("no scoring points supplied — cannot bind options")

    correct = item.get("correct_options") or []
    if not correct:
        raise SourceBindingError("item has no correct_options")
    for opt in correct:
        sid = (opt or {}).get("source_scoring_point_id")
        if sid not in point_ids:
            raise SourceBindingError(
                f"correct option source_scoring_point_id {sid!r} does not bind a real "
                f"scoring point of this question {sorted(point_ids)}"
            )

    for dis in item.get("distractors") or []:
        dis = dis or {}
        if dis.get("source_scoring_point_id"):
            raise SourceBindingError(
                "distractor must NOT bind a real scoring point (it is a wrong option)"
            )
        if not dis.get("error_code"):
            raise SourceBindingError(
                "distractor must carry an error_code (∈ ERROR_CODE_REGISTRY / NEEDS_REVIEW)"
            )


# ── Conjunction-group deterministic scorer (§4 red line: 找错∧改正) ─────────────


def score_conjunction_group(
    points: Sequence[LubanCaseScoringPoint], hit_point_ids: Iterable[str]
) -> float:
    """判断改正题的合取门判分:同一 ``conjunction_group`` 的成员必须**全部命中**
    才给该组满分(找错∧改正);缺任一成员则该组得 0 —— 决不"找错不改正"给满分。

    非合取采分点(``conjunction_group is None``)按各自 max_score 独立命中计分。
    Returns the total awarded score. Deterministic, no LLM.
    """
    hits = set(hit_point_ids)

    groups: dict[str, list[LubanCaseScoringPoint]] = {}
    flat: list[LubanCaseScoringPoint] = []
    for p in points:
        if p.conjunction_group is None:
            flat.append(p)
        else:
            groups.setdefault(p.conjunction_group, []).append(p)

    awarded = 0.0
    for p in flat:
        if p.point_id in hits:
            awarded += p.max_score

    for members in groups.values():
        if all(m.point_id in hits for m in members):
            awarded += sum(m.max_score for m in members)
        # else: 合取门未满足 → 该组 0 分(找错不改正不得分)
    return awarded


__all__ = [
    "SCHEMA_ID",
    "OFFICIAL_SCORE_ALLOWED",
    "CANONICAL_WRITE_ALLOWED",
    "RUNTIME_INSTALL_ALLOWED",
    "CHANNEL_ONE_SCORING_AUTHORITY",
    "LEGIT_ANSWER_KEY_AUTHORITY",
    "WHITELIST_PATH",
    "PointType",
    "WhitelistError",
    "SourceBindingError",
    "AuthoritySourceError",
    "SourceRef",
    "AcceptableVariant",
    "LubanCaseScoringPoint",
    "load_whitelist",
    "assert_qid_allowed",
    "validate_source_scoring_point_id",
    "score_conjunction_group",
]
