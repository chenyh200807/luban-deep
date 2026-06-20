"""Input matrix for the routing characterization harness (task #12 真闭包 safety net).

Each row freezes one (message shape × context state) routing decision. ``tier``:
  A = fully deterministic, NO LLM reached (asserted: neither mock fires).
  B = lifecycle LLM gated; scripted via ``lifecycle_script`` (or None → unavailable).
  C = followup-interpreter LLM dependent; scripted via ``followup_script``.

The matrix is the contract surface: every §硬约束24 gate should have ≥1 row. Add rows
when a 收口 step touches a gate. The golden is generated once on the pre-收口 baseline and
each migration PR must keep it byte-identical (or show the one intended row diff).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── message shapes ────────────────────────────────────────────────────────────
M_FULL_MCQ = (
    "某工程屋面为压型金属板，设计无要求时屋面坡度最小值是（）。"
    "A.5% B.2% C.3% D.1%。我选A，判对错。"
)
M_FULL_MCQ_REVEAL = (
    "某工程屋面为压型金属板，设计无要求时屋面坡度最小值是（）。"
    "A.5% B.2% C.3% D.1%。直接告诉我答案"
)
M_CASE_ANSWER = "背景资料：某项目……\n【问题】1.指出事件一中的不妥之处。\n回答：我认为共用开关箱不妥。"
M_BARE_ANSWER = "我选A"
M_NUMBERED_BATCH = "第1题我选A，第2题我选BD"
M_REFER_PAST_Q = "回到刚才那道屋面坡度的题，再帮我把考点讲透"
M_PRACTICE_REQ = "给我再出三道屋面防水相关的新选择题练练手"
M_SMALLTALK = "哈哈跟你聊得挺好，你喜欢看电影吗，随便扯扯"
M_LOWINFO_EXAM = "2025防水真题答案直接发我"

# ── context states ────────────────────────────────────────────────────────────
C_EMPTY: dict[str, Any] = {}


def _single_active() -> dict[str, Any]:
    q = {
        "question_id": "q1",
        "question": "压型金属板屋面坡度最小值",
        "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
        "question_type": "single_choice",
    }
    return {
        "question_followup_context": dict(q),
        "active_object": {
            "object_type": "question",
            "object_id": "q1",
            "state_snapshot": dict(q),
        },
    }


def _multi_active() -> dict[str, Any]:
    items = [
        {"question_id": "q1", "question": "平屋面防水道数",
         "options": {"A": "1道", "B": "2道", "C": "3道", "D": "4道"},
         "question_type": "single_choice"},
        {"question_id": "q2", "question": "结构找坡坡度",
         "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
         "question_type": "single_choice"},
    ]
    return {
        "question_followup_context": {"items": items},
        "active_object": {
            "object_type": "question_set",
            "object_id": "qset",
            "state_snapshot": {"items": items},
        },
    }


@dataclass(frozen=True)
class Row:
    id: str
    message: str
    context: dict[str, Any]
    tier: str  # "A" | "B" | "C"
    gate: str  # which §24 gate / boundary it exercises
    config_overrides: dict[str, Any] = field(default_factory=dict)
    lifecycle_script: dict[str, Any] | None = None
    followup_script: dict[str, Any] | None = None


# Production flag combination pinned per row so the golden is env-independent.
_PROD_FLAGS = {
    "question_lifecycle_decision_authority": True,
}

MATRIX: list[Row] = [
    Row("full_mcq_empty", M_FULL_MCQ, C_EMPTY, "A",
        "full free-text MCQ surface priority", dict(_PROD_FLAGS)),
    Row("full_mcq_reveal_empty", M_FULL_MCQ_REVEAL, C_EMPTY, "A",
        "free_text_mcq_answer_request", dict(_PROD_FLAGS)),
    Row("case_answer_empty", M_CASE_ANSWER, C_EMPTY, "C",
        "full case answer → case_grading", dict(_PROD_FLAGS)),
    Row("bare_answer_empty", M_BARE_ANSWER, C_EMPTY, "A",
        "unanchored submission → clarification", dict(_PROD_FLAGS)),
    Row("bare_answer_multi", M_BARE_ANSWER, _multi_active(), "A",
        "ambiguous multi submission → clarification (no LLM)", dict(_PROD_FLAGS)),
    Row("numbered_batch_multi", M_NUMBERED_BATCH, _multi_active(), "C",
        "numbered batch answers", dict(_PROD_FLAGS)),
    Row("smalltalk_empty", M_SMALLTALK, C_EMPTY, "A",
        "no scene → default chat", dict(_PROD_FLAGS)),
    Row("lowinfo_exam_empty", M_LOWINFO_EXAM, C_EMPTY, "C",
        "low-information exam query → clarification", dict(_PROD_FLAGS)),
    Row("practice_req_empty", M_PRACTICE_REQ, C_EMPTY, "A",
        "practice_generation deterministic", dict(_PROD_FLAGS)),
    Row("refer_past_q_multi", M_REFER_PAST_Q, _multi_active(), "C",
        "back-reference+explanation not misjudged as submission (task#11)", dict(_PROD_FLAGS)),
]
