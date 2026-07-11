"""实务闯关「全量作答」档（档位③）—— 自由默写文本接既有判分内核链路。

复习核心 gap 的 Layer 1：让 gauntlet ③全量作答档产生真实
``construction_grading`` promoting 证据，全程复用既有 authority，零第二套。

设计边界（AGENTS §0 Thin Wrappers Fat Skills / §5.7 Single Authority）：
- ``question_row`` 唯一来源 = 已签发变体池（``read_model._load_signed_bank``，与
  retest 同一签发闸）。本模块不新造题库、不新造供给。
- ``grading_key.scoring_points`` 经既有 ``compiled_registry_resolver`` 从已签发
  case-rubric supply 解析——**不新造 resolver**。当前 node 型变体包在该签发
  bundle 的 ``question_index`` 无命中 → 返回 ``None``。此时内核**不是**落进
  curated_rubric：有签发 ``correct_statement`` 时落 ``projected_rubric``（从
  参考答案投影关键词），无任何答案侧权威时才落 ``open_skill``——两者都
  ``L0_observed`` / ``stable_truth_eligible=False``（如实封顶，被 certified-grading
  闸正确挡，非 bug；见 PRD 红线5）。只有签发 ``grading_key.scoring_points`` 接线后
  才是 curated_rubric。绝不为演示 promotion 指向未签发（published:False）采分点供给。
- 判分唯一内核 = ``CaseGradingSkillKernel.grade``；写路径唯一 =
  ``write_grading_error_events``（``source_feature="construction_grading"``，
  在 ``learning_synthesis.PRACTICE_EVIDENCE_SOURCE_FEATURES`` 白名单 = promoting）。
  本模块零 payload builder、零第二 sink、零二次 LLM 归因。
- 错因码只来自 ``grade()`` 的 ``GradingErrorEvent`` + ``ERROR_CODE_REGISTRY``。
- 复测归 ``revalidation_queue``（由 auto-synthesis 派生），本模块不自排期。
- 对外投影剥离 ``keywords`` / ``required_terms``（防客户端再认泄漏，PRD 红线）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from deeptutor.services.luban_lesson.read_model import (
    LessonNotAvailable,
    _load_manifest,
    _load_signed_bank,
    _MANIFEST_PATH,
    build_lesson_viewmodel,
)

# 既有已签发 case-rubric 打分 supply（rubric_grader_v1 生产同源），作为
# grading_key 解析的唯一 signed 供给面。绝不指向 v_case_rubric_scored_pgo
# （published:False 的 PGO 供给），避免为 promotion 演示指向未签发供给。
_CASE_RUBRIC_SUPPLY_DIR = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "construction_grading"
    / "runtime_supply"
    / "v_case_rubric_scored"
)


class FullAnswerNotAvailable(Exception):
    """pack/变体不存在或未过签发闸——对外 404 同形（fail-closed，不泄漏存在性）。"""


def _node_from_anchor(anchor: Any) -> str:
    """从变体 anchor（``kc:1A413030_090_0165:0``）取前导规范节点码，作为
    error_events 的 ``concept_tag``。取不到留空——不臆造概念（开放世界记忆）。"""
    text = str(anchor or "").strip()
    if not text:
        return ""
    body = text.split(":", 1)[1] if text.lower().startswith("kc:") else text
    head = body.split("_", 1)[0].strip()
    # 规范节点码形如 1A413030；非此形状不猜测
    return head if head[:2].isalnum() and len(head) >= 6 else ""


def _find_variant(bank: dict[str, Any], variant_id: str) -> dict[str, Any] | None:
    target = str(variant_id or "").strip()
    if not target:
        return None
    for variant in bank.get("variants") or []:
        if str((variant or {}).get("variant_id") or "").strip() == target:
            return dict(variant)
    return None


def resolve_full_answer_inputs(
    pack_id: str,
    variant_id: str,
    *,
    manifest_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    """解析 (question_row, grading_key, evidence_rows)。仅从已签发变体池取题面权威。

    ``evidence_rows`` = 变体 anchor 指向的已签发知识 chunk（kb_chunk）—— 判分的
    RAG 事实接地（同一 chunk 授权了 correct_statement），非臆造。

    raise ``FullAnswerNotAvailable`` when the pack is not green / bank unsigned /
    sha drift / variant absent（与 retest 同一 fail-closed 闸）。
    """
    vm = build_lesson_viewmodel(pack_id, manifest_path=manifest_path)  # 非绿灯 → LessonNotAvailable
    if not vm["variant_retest"]["available"]:
        raise FullAnswerNotAvailable(pack_id)
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    bank = _load_signed_bank(vm["pack_id"], manifest_dir, vm["content_sha256"])
    if bank is None:
        raise FullAnswerNotAvailable(pack_id)
    variant = _find_variant(bank, variant_id)
    if variant is None:
        raise FullAnswerNotAvailable(f"{pack_id}:{variant_id}")

    row: dict[str, Any] = {
        "id": str(variant.get("variant_id") or "").strip(),
        "question_id": str(variant.get("variant_id") or "").strip(),
        "node_code": _node_from_anchor(variant.get("anchor")),
        "testing_focus": str(variant.get("rule_group") or "").strip(),
        "question_stem": str(variant.get("surface") or "").strip(),
        # correct_statement = 参考答案权威；内核 open_skill 从此投影采分关键词。
        "correct_answer": str(variant.get("correct_statement") or "").strip(),
    }
    grading_key = _resolve_grading_key(row["question_id"])

    # 判分 RAG 接地：变体 anchor 即授权 correct_statement 的已签发知识 chunk。
    evidence_rows: list[dict[str, Any]] = []
    anchor = str(variant.get("anchor") or "").strip()
    if anchor and row["correct_answer"]:
        evidence_rows.append(
            {"source": "kb_chunk", "field": anchor, "text": row["correct_answer"]}
        )
    return row, grading_key, evidence_rows


def _resolve_grading_key(question_id: str) -> dict[str, Any] | None:
    """既有 resolver 缝：从已签发 case-rubric bundle 解析该题采分点 → grading_key。

    不新造 resolver——直接走 ``compiled_registry_resolver``。当前 node 型变体包在
    该 bundle 的 ``question_index`` 无命中（cheap dict 预检，避免无谓 verify 日志）
    → 返回 ``None`` → 内核 open_skill 封顶（如实 L0，见模块头注红线5）。
    """
    qid = str(question_id or "").strip()
    if not qid:
        return None
    try:
        from deeptutor.services.construction_grading import compiled_registry_resolver as _R

        loaded = _R.load_supply(_CASE_RUBRIC_SUPPLY_DIR, bundle_name="case_rubric_scored.json")
        if not loaded:
            return None
        bundle, pointer = loaded
        question_index = (bundle.get("manifest") or {}).get("question_index") or {}
        if qid not in question_index:
            return None  # 无签发采分点供给命中 → open_skill 封顶（honest）
        resolution = _R.resolve_question(qid, bundle=bundle, pointer=pointer)
    except Exception:  # noqa: BLE001 — resolver 永不把异常抛进 runtime
        return None
    if not resolution:
        return None
    points = (resolution.get("rubric") or {}).get("points") or []
    scoring_points: list[dict[str, Any]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        criterion = str(point.get("text") or point.get("point_id") or "").strip()
        if not criterion:
            continue
        scoring_points.append(
            {
                "criterion": criterion,
                "keywords": [str(t).strip() for t in (point.get("required_terms") or []) if str(t).strip()]
                or [criterion],
                "score": float(point.get("score") or 1),
            }
        )
    return {"scoring_points": scoring_points} if scoring_points else None


def grade_full_answer(
    *,
    pack_id: str,
    variant_id: str,
    answer_text: str,
    user_id: str,
    learner_state_service: Any,
    mistake_book_service: Any | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """档位③全量作答：resolve → 内核判分 → 唯一 sink 写回 → 逐采分点投影。

    Returns the client-facing verdict（剥离 keywords/required_terms，防再认泄漏）。
    """
    from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
    from deeptutor.services.construction_grading.learning_evidence import (
        build_learning_evidence_payload,
    )
    from deeptutor.services.construction_grading.writeback import write_grading_error_events

    row, grading_key, evidence_rows = resolve_full_answer_inputs(
        pack_id, variant_id, manifest_path=manifest_path
    )
    answer = str(answer_text or "").strip()

    result = CaseGradingSkillKernel().grade(
        question_row=row,
        user_answer=answer,
        evidence_rows=evidence_rows,
        grading_key=grading_key,
    )

    source_id = f"luban-gauntlet-full-answer-{uuid4().hex[:12]}"
    write_count = write_grading_error_events(
        learner_state_service=learner_state_service,
        user_id=user_id,
        grading_result=result,
        source_id=source_id,
        source_bot_id="construction-exam",
        mistake_book_service=mistake_book_service,
    )

    # 诚实披露 evidence 封顶：读同一 producer（build_learning_evidence_payload）
    # 的 quality dict，不另算——单一 authority，零漂移。
    quality = build_learning_evidence_payload(grading_result=result).get("quality") or {}

    return _project_verdict(
        pack_id=row.get("question_id", "").split(":", 1)[0] or str(pack_id).upper(),
        variant_id=str(variant_id or "").strip(),
        result=result,
        quality=quality,
        write_count=write_count,
        source_id=source_id,
    )


def _project_verdict(
    *,
    pack_id: str,
    variant_id: str,
    result: Any,
    quality: dict[str, Any],
    write_count: int,
    source_id: str,
) -> dict[str, Any]:
    """逐采分点对外投影。**剥离** keywords / evidence_text / required_terms
    （防客户端把采分关键词当再认候选词，PRD 红线）。"""
    signal = dict(getattr(result, "next_training_signal", {}) or {})
    points = [
        {
            "criterion": str(item.criterion or "").strip(),
            "status": str(item.status or "").strip(),  # full | partial | miss
            "awarded_score": float(item.awarded_score or 0),
            "max_score": float(item.max_score or 0),
        }
        for item in list(getattr(result, "rubric_items", []) or [])
    ]
    return {
        "enabled": True,
        "pack_id": str(pack_id or "").upper(),
        "variant_id": variant_id,
        "grading_mode": str(getattr(result, "grading_mode", "") or ""),
        "grading_source": str(signal.get("grading_source") or ""),
        "score_awarded": float(getattr(result, "score_awarded", 0) or 0),
        "max_score": float(getattr(result, "max_score", 0) or 0),
        "scoring_points": points,
        # 诚实封顶披露：open_skill/无签发采分点 → L0_observed / 不进稳定掌握
        "evidence_level": str(quality.get("evidence_level") or "L0_observed"),
        "stable_truth_eligible": bool(quality.get("stable_truth_eligible")),
        "writeback_count": int(write_count or 0),
        "rewrite_answer": str(getattr(result, "rewrite_answer", "") or ""),
        "source_id": source_id,
    }
