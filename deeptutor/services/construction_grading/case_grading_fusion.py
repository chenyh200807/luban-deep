"""Fused case grading: V1 deterministic score (authority) + RAG/LLM teaching (pedagogy).

Design (Nexus-like, three principles):
- Score authority stays 100% with the V1 GradingEvent (compiled rubric, deterministic sum). The
  teaching layer NEVER changes the score — it only explains missed/partial points.
- RAG supplies textbook/standard evidence for the missed concepts (pluggable ``rag_fn``); when RAG is
  unavailable the teaching is still grounded in the compiled scoring-point texts (themselves sourced
  from exam reference answers / textbook).
- Thin wrapper: scoring is rubric_grader_v1 (fat skill), this module only adds the teaching layer and
  composes the render. official_score_allowed / writeback unchanged.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from deeptutor.services.construction_grading.rubric_grader_v1 import (
    HIT,
    render_case_rubric_feedback,
)

logger = logging.getLogger(__name__)

_TEACH_SYSTEM = "你是一建案例题资深阅卷+辅导老师,只做教学讲解,不改分数,输出简洁中文。"


def _weak_points(event: dict[str, Any]) -> list[dict[str, Any]]:
    return [sp for sp in (event.get("scoring_points") or []) if sp.get("hit") != HIT]


def _teach_prompt(question_stem: str, weak: list[dict[str, Any]], student_answer: str,
                  evidence: str) -> str:
    lines = []
    for i, sp in enumerate(weak, 1):
        why = "答错/不符" if sp.get("mistake_type") == "wrong_content" else (
            "未答全" if sp.get("hit") == "partial" else "漏写")
        lines.append(f'  {i}. 采分点「{sp.get("knowledge_point")}」（{why}）')
    ev = f"\n【教材/规范依据(RAG)】\n{evidence[:1500]}\n" if evidence else ""
    return (
        "学生这道案例题有下面这些采分点没拿到分。请逐条给出教学讲解,帮学生下次得分。"
        "不要打分、不要改分数,只讲怎么答对。\n\n"
        f"【题目】{str(question_stem)[:600]}\n"
        f"【学生作答】{str(student_answer)[:1000]}\n"
        f"【没拿到分的采分点】\n" + "\n".join(lines) + "\n" + ev +
        "\n对每条输出: 正确答案 + 为什么这么答 + 易错点(一句)。可给记忆口诀。简洁,别重复题面。"
    )


async def _generate_teaching(
    question_stem: str, weak: list[dict[str, Any]], student_answer: str, evidence: str,
    complete_fn: Callable[..., Awaitable[Any]], api_key: str, model: str,
) -> str:
    if not weak:
        return ""
    try:
        raw = await complete_fn(prompt=_teach_prompt(question_stem, weak, student_answer, evidence),
                                system_prompt=_TEACH_SYSTEM, model=model, api_key=api_key, max_retries=1)
        return str(raw).strip()
    except Exception:  # noqa: BLE001 — teaching is best-effort; never breaks the authoritative score
        logger.warning("case_grading_fusion: teaching generation failed", exc_info=True)
        return ""


async def build_fused_case_feedback(
    event: dict[str, Any], *, question_stem: str, student_answer: str,
    complete_fn: Callable[..., Awaitable[Any]], api_key: str,
    rag_fn: Callable[..., Awaitable[Any]] | None = None, model: str = "deepseek-chat",
) -> dict[str, Any]:
    """Compose V1 score (authoritative) + RAG/LLM teaching. Returns {render, score_block, teaching,
    evidence_used, awarded_score, max_score, official_score_allowed=False}."""
    weak = _weak_points(event)
    evidence = ""
    if rag_fn and weak:
        try:
            q = (str(question_stem) + " " + " ".join(str(sp.get("knowledge_point")) for sp in weak[:6]))[:200]
            evidence = str(await rag_fn(q))[:1500]
        except Exception:  # noqa: BLE001 — RAG optional; fall back to scoring-point-grounded teaching
            logger.info("case_grading_fusion: RAG evidence unavailable; teaching from scoring points",
                        exc_info=True)
            evidence = ""
    teaching = await _generate_teaching(question_stem, weak, student_answer, evidence,
                                        complete_fn, api_key, model)
    score_block = render_case_rubric_feedback(event, question_stem=question_stem)
    render = score_block
    if teaching:
        tag = "（含教材依据）" if evidence else ""
        render += f"\n\n## 老师讲解 · 怎么把丢的分拿回来{tag}\n{teaching}"
    return {
        "render": render,
        "score_block": score_block,
        "teaching": teaching,
        "evidence_used": bool(evidence),
        "awarded_score": event.get("awarded_score"),
        "max_score": event.get("max_score"),
        "official_score_allowed": False,  # score authority is V1; teaching never promotes it
    }


__all__ = ["build_fused_case_feedback"]
