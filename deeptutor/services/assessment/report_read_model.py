from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


REPORT_SCHEMA_VERSION = "p0a-v1"
PASS_READINESS_REPORT_SCHEMA_VERSION = "pass-readiness-v1"
# Persisted report schema versions admitted by the DB CHECK constraint
# (supabase/migrations/20260805000100_assessment_report_schema_pass_readiness.sql).
SUPPORTED_REPORT_SCHEMA_VERSIONS = (REPORT_SCHEMA_VERSION, PASS_READINESS_REPORT_SCHEMA_VERSION)


class AssessmentReportError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_result_report(
    *,
    quiz_id: str,
    assessment_type: str,
    subject_id: str,
    topic_ids: list[str],
    topic_label: str,
    blueprint_version: str,
    form_id: str,
    scored_result: dict[str, Any],
    writeback_refs: dict[str, Any] | None = None,
    degraded_reason: str | None = None,
) -> dict[str, Any]:
    items = [dict(item) for item in list(scored_result.get("items") or [])]
    score_summary = dict(scored_result.get("score_summary") or {})
    confidence = dict(scored_result.get("measurement_confidence") or {})
    wrong_items = [item for item in items if not item.get("is_correct")]
    knowledge_map = _knowledge_map(items)
    next_action = _session_local_next_action(wrong_items, knowledge_map)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "quiz_id": quiz_id,
        "assessment_type": assessment_type,
        "subject_id": subject_id,
        "topic_ids": list(topic_ids or []),
        "topic_label": topic_label,
        "blueprint_version": blueprint_version,
        "form_id": form_id,
        "score_title": "本次专题测评得分",
        "score_summary": score_summary,
        "measurement_confidence": confidence,
        "knowledge_map": knowledge_map,
        "wrong_items": [
            {
                "question_id": item.get("question_id"),
                "source_question_id": item.get("source_question_id"),
                "question_stem": item.get("question_stem"),
                "learner_answer": item.get("learner_answer"),
                "correct_answer": item.get("correct_answer"),
                "simple_explanation": item.get("simple_explanation"),
                "knowledge_points": list(item.get("knowledge_points") or []),
                "error_codes": list(item.get("error_codes") or []),
            }
            for item in wrong_items
        ],
        "items": [
            {
                "question_id": item.get("question_id"),
                "source_question_id": item.get("source_question_id"),
                "learner_answer": item.get("learner_answer"),
                "correct_answer": item.get("correct_answer"),
                "is_correct": bool(item.get("is_correct")),
                "simple_explanation": item.get("simple_explanation"),
                "knowledge_points": list(item.get("knowledge_points") or []),
                "error_codes": list(item.get("error_codes") or []),
            }
            for item in items
        ],
        "attempt_refs": list((writeback_refs or {}).get("learning_event_refs") or []),
        "session_local_next_action": next_action,
        "writeback_status": dict((writeback_refs or {}).get("writeback_status") or {}),
        "deep_explanation": {
            "available": False,
            "copy": "详细解析下个版本上线",
        },
        "degraded_reason": degraded_reason,
    }


_SELF_REPORTED_SCORE_BY_TAG: dict[str, int | None] = {
    # Representative mid-band values for the recent_score_band probe (自报未核验).
    "no_prior_score": None,
    "below_60": 50,
    "score_60_79": 70,
    "score_80_95": 88,
    "score_96_plus": 100,
}


def _probe_tags(
    session_questions: list[dict[str, Any]],
    answers: dict[str, Any],
) -> dict[str, str]:
    """Map profile-probe topics to the tag of the tapped option."""

    tags: dict[str, str] = {}
    for question in session_questions:
        if question.get("scored", True):
            continue
        topic = str(question.get("profile_topic") or "").strip()
        if not topic:
            continue
        letter = str(answers.get(str(question.get("question_id") or "")) or "").strip().upper()
        option_values = dict(question.get("option_values") or {})
        tag = str(option_values.get(letter) or "").strip()
        if tag:
            tags[topic] = tag
    return tags


_EXAM_REF_RE = re.compile(r"^exam:(\d{4}):(.+)$")
_MACHINE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_:.\-]*$")
# 编译/判分锚共用「前缀:节点码_尾巴」语法(kc:/ca:/cc:/m35:),节点码可翻教材章节名。
_NODE_ANCHOR_RE = re.compile(r"^(?:kc|ca|cc):(1A\d{6})|^m35:Q\d+-(1A\d{6})")


def _learner_facing_source(source: str) -> str:
    """依据来源人话化(fail-closed,2026-08-07 owner 实拍「ca:1A413030_103_0196」)。

    ``exam:YYYY:第N题`` → 「YYYY 年真题·第N题」;带教材节点码的机器锚经
    taxonomy_authority(学员面章节名单一权威,永不露码)翻成「教材·章节名」;
    翻不出的纯 ASCII 机器锚一律留空,由前端整行不渲染——宁可无来源行,
    不给学员看内部机件。含中文的授权来源文本原样透出。
    """

    value = str(source or "").strip()
    if not value:
        return ""
    match = _EXAM_REF_RE.fullmatch(value)
    if match:
        return f"{match.group(1)} 年真题·{match.group(2).strip()}"
    node_match = _NODE_ANCHOR_RE.match(value)
    if node_match:
        from deeptutor.services.taxonomy.taxonomy_authority import taxonomy_label

        label = taxonomy_label(node_match.group(1) or node_match.group(2))
        if label:
            return f"教材·{label}"
    if _MACHINE_REF_RE.fullmatch(value):
        return ""
    return value


def _option_text_by_key(question: dict[str, Any]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for option in list(question.get("options") or []):
        if not isinstance(option, dict):
            continue
        key = str(option.get("key") or "").strip().upper()
        text = str(option.get("text") or "").strip()
        if key and text:
            texts[key] = text
    return texts


def _joined_option_text(question: dict[str, Any], letters: str) -> str:
    """字母串 → 「C. 选项原文」;多选逐项拼接。快照缺选项文本时返回空,
    由前端退回只显示字母(不编造)。"""

    texts = _option_text_by_key(question)
    picked = [f"{letter}. {texts[letter]}" for letter in letters if letter in texts]
    return "；".join(picked)


# 编题内部速记段(2026-08-07 盘点 578 种 rule_group 实证):出题维度分类
# (「××维」)与创作工序词。它们是机器面词汇,直出=敷衍学员。
_INTERNAL_LABEL_SEGMENTS = {
    "末题",
    "上集",
    "下集",
    "判断纠错",
    "案例辨析",
    "采分点遗漏",
    "采分句输出",
    "采分诊断",
}


def _learner_facing_scoring_point(label: str) -> str:
    """采分点标签人话化(owner 2026-08-07:「判型·条件维」这类内部速记=敷衍)。

    按「·」分段,剥掉内部维度段(「××维」)与创作工序段;剥完不足 3 字
    (如「判型」)说明剩下的仍是速记,fail-closed 留空——宁可无此行,
    不给学员看编题黑话。真人话标签(「施工缝·处理工序」)原样保留。
    """

    segments = [seg.strip() for seg in str(label or "").split("·") if seg.strip()]
    kept = [
        seg
        for seg in segments
        if not seg.endswith("维") and seg not in _INTERNAL_LABEL_SEGMENTS
    ]
    cleaned = "·".join(kept)
    return cleaned if len(cleaned) >= 3 else ""


# 2026-08-07 设计反转实录:曾按「与正确选项相近即复读」压掉 model_answer,
# owner 实拍裁决推翻——正确答案行是「该点哪个选项」(对照角色),采分点位的
# 规则句是「该记住什么」(记忆角色),文本相近也必须各自在位。签发 model_answer
# 一律透出,不做相似度压制。


def _issued_option_reviews(
    question: dict[str, Any],
    learner_answer: str,
    correct_answer: str,
) -> list[dict[str, Any]]:
    """逐选项点评投影(owner 2026-08-07:「按鲁班答题的形式展现」)。

    签发权威三条车道都带全量逐选项诊断(编译:temptation/loss_reason/fix;
    题库:option_reasoning;案例:逐选项 cause)——此前只投学员实选项,浪费了
    权威。这里按选项顺序全量投影:错误选项 review=为什么错,正确选项
    review=得分要点(fix)。全部只读签发内容,零现编;整卡无任何点评内容
    时返回空列表,前端整块不渲染。"""

    diagnosis = dict(question.get("answer_diagnosis") or {})
    per_option = dict(diagnosis.get("options") or {})
    reviews: list[dict[str, Any]] = []
    has_content = False
    for option in list(question.get("options") or []):
        if not isinstance(option, dict):
            continue
        key = str(option.get("key") or "").strip().upper()
        text = str(option.get("text") or "").strip()
        if not key:
            continue
        entry = dict(per_option.get(key) or {})
        is_correct = key in correct_answer
        review = str(entry.get("why_missed") or "").strip()
        if is_correct and not review:
            review = str(entry.get("fix") or "").strip()
        pitfall = str(entry.get("pitfall") or "").strip()
        if review or pitfall:
            has_content = True
        reviews.append(
            {
                "key": key,
                "text": text,
                "is_correct": is_correct,
                "is_learner": key in learner_answer,
                "review": review,
                "pitfall": pitfall,
            }
        )
    return reviews if has_content else []


def build_evidence_items(
    items: list[dict[str, Any]],
    session_questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """失分题 → 证据卡(§7.3):诊断只从私有会话快照的 ``answer_diagnosis`` 读。

    单一权威:诊断文本由供给车道在组卷时从各自签发权威(编译 authority 逐选项
    temptation/loss_reason/fix、questions_bank.analysis、manifest 案例逐选项
    cause/source)只读投影而来。本函数不生成任何解释文本——**权威没有的字段一律
    留空**,由前端整行不渲染(omitted-rather-than-faked),绝不用通用套话冒充。
    """

    by_question_id = {
        str(question.get("question_id") or ""): question
        for question in list(session_questions or [])
        if str(question.get("question_id") or "")
    }
    evidence: list[dict[str, Any]] = []
    for item in list(items or []):
        if item.get("is_correct"):
            continue
        question = dict(by_question_id.get(str(item.get("question_id") or "")) or {})
        diagnosis = dict(question.get("answer_diagnosis") or {})
        learner_answer = str(item.get("learner_answer") or "").strip().upper()
        per_option = dict(diagnosis.get("options") or {})
        # 正确答案唯一权威=签发快照的 answer;scored 转录只作缺快照时的兜底。
        correct_answer = (
            str(question.get("answer") or item.get("correct_answer") or "").strip().upper()
        )
        # 错因必须对准「错在哪」(2026-08-07 owner 实拍卡18回归):多选漏选时,
        # 学员实选的往往是"对的那几个",拿它们的解读当丢分原因=答非所问。
        # 诊断锚定错误字母集:错选(实选却不该选)优先,再漏选(该选却没选);
        # 单选沿用实选项(实选即错选)。
        is_multi = str(question.get("question_type") or "") == "multi_choice"
        if is_multi and correct_answer:
            extra_letters = [l for l in learner_answer if l not in correct_answer]
            missed_letters = [l for l in correct_answer if l not in learner_answer]
            error_letters = extra_letters + missed_letters
        else:
            extra_letters, missed_letters = list(learner_answer), []
            error_letters = list(learner_answer)
        chosen: dict[str, Any] = {}
        for letter in error_letters:
            candidate = dict(per_option.get(letter) or {})
            if candidate:
                chosen = candidate
                break
        why_missed = ""
        if is_multi and (extra_letters or missed_letters):
            option_texts = _option_text_by_key(question)
            parts: list[str] = []
            for letter in extra_letters:
                reason = str(dict(per_option.get(letter) or {}).get("why_missed") or "").strip()
                parts.append(
                    f"错选 {letter}：{reason}"
                    if reason
                    else (f"错选 {letter}（{option_texts[letter]}）" if letter in option_texts else f"错选 {letter}")
                )
            for letter in missed_letters:
                reason = str(dict(per_option.get(letter) or {}).get("why_missed") or "").strip()
                parts.append(
                    f"漏选 {letter}：{reason}"
                    if reason
                    else (f"漏选 {letter}（{option_texts[letter]}）" if letter in option_texts else f"漏选 {letter}")
                )
            why_missed = "；".join(parts)
        if not why_missed:
            why_missed = str(chosen.get("why_missed") or "").strip() or str(
                diagnosis.get("explanation") or ""
            ).strip()
        raw_source = str(chosen.get("source") or diagnosis.get("source") or "").strip()
        evidence.append(
            {
                "question_id": item.get("question_id"),
                "source_question_id": item.get("source_question_id"),
                "question_stem": item.get("question_stem"),
                "learner_answer": item.get("learner_answer"),
                "learner_option_text": _joined_option_text(question, learner_answer),
                "correct_answer": correct_answer,
                "correct_option_text": _joined_option_text(question, correct_answer),
                # 采分点只认签发诊断(禁章节级 knowledge_points 凑数),且必须
                # 过人话闸——内部速记(「判型·条件维」)剥净或留白。
                "scoring_point": _learner_facing_scoring_point(
                    str(diagnosis.get("scoring_point") or "")
                ),
                # 能得分的确切表述(§7.3-3):签发 model_answer 一律透出(见上方
                # 设计反转注),没有即留空。
                "scoring_wording": str(diagnosis.get("model_answer") or "").strip(),
                "pitfall": str(chosen.get("pitfall") or "").strip(),
                "why_missed": why_missed,
                "fix": str(chosen.get("fix") or "").strip(),
                "option_reviews": _issued_option_reviews(
                    question, learner_answer, correct_answer
                ),
                "source": _learner_facing_source(raw_source),
                "source_ref": raw_source,
                "error_codes": list(item.get("error_codes") or []),
                "knowledge_points": list(item.get("knowledge_points") or []),
            }
        )
    return evidence


def build_pass_readiness_report(
    *,
    quiz_id: str,
    assessment_type: str,
    subject_id: str,
    topic_label: str,
    blueprint_version: str,
    form_id: str,
    scored_result: dict[str, Any],
    session_questions: list[dict[str, Any]],
    answers: dict[str, Any],
    writeback_refs: dict[str, Any] | None = None,
    degraded_reason: str | None = None,
    now_iso: str = "",
) -> dict[str, Any]:
    """Assemble the pass-readiness-v1 report envelope (§7.2).

    Keeps the base p0a report fields (items/wrong_items/score_summary/…) so the
    existing client rendering chain still works, overrides the persisted
    ``schema_version`` to ``pass-readiness-v1``, and adds the deterministic
    ``pass_readiness`` §7.2 block. The p0a-v1 builder is untouched.
    """

    from deeptutor.services.assessment.blueprint import ability_dimensions_by_section
    from deeptutor.services.assessment.pass_readiness_scoring import (
        AbilityEvidence,
        DimensionEvidence,
        PrepContext,
        build_pass_readiness_result,
        build_pass_readiness_result_v2,
    )

    # 表单 v2 → band-v2/model-v2 阶梯；v1 blueprint 走原函数（回滚锚，行为不动）。
    # 持久化信封 schema_version 保持 pass-readiness-v1（DB CHECK 白名单），
    # 版本差异由块内 band_policy_version/model_version 承载。
    result_builder = (
        build_pass_readiness_result_v2
        if str(blueprint_version or "").strip() == "pass_readiness_architecture_v2"
        else build_pass_readiness_result
    )

    base = build_result_report(
        quiz_id=quiz_id,
        assessment_type=assessment_type,
        subject_id=subject_id,
        topic_ids=[],
        topic_label=topic_label,
        blueprint_version=blueprint_version,
        form_id=form_id,
        scored_result=scored_result,
        writeback_refs=writeback_refs,
        degraded_reason=degraded_reason,
    )
    dimension_by_section = ability_dimensions_by_section(blueprint_version)
    counts: dict[str, dict[str, float]] = {}
    items = [dict(item) for item in list(scored_result.get("items") or [])]
    answered_count = 0
    for item in items:
        answered = bool(str(item.get("learner_answer") or "").strip())
        if answered:
            answered_count += 1
        dimension = dimension_by_section.get(str(item.get("section_id") or ""), "")
        if not dimension or not answered:
            continue
        bucket = counts.setdefault(dimension, {"correct": 0.0, "observations": 0})
        bucket["observations"] += 1
        if item.get("is_correct"):
            bucket["correct"] += 1

    def _evidence(dimension: str) -> DimensionEvidence:
        bucket = counts.get(dimension) or {"correct": 0.0, "observations": 0}
        return DimensionEvidence(correct=bucket["correct"], observations=int(bucket["observations"]))

    tags = _probe_tags(session_questions, dict(answers or {}))
    expression = counts.get("answer_expression")
    evidence = AbilityEvidence(
        core_knowledge=_evidence("core_knowledge"),
        construction_logic=_evidence("construction_logic"),
        case_scoring_point_recognition=_evidence("case_scoring_point_recognition"),
        answer_expression=(
            DimensionEvidence(correct=expression["correct"], observations=int(expression["observations"]))
            if expression
            else None
        ),
        self_reported_score=_SELF_REPORTED_SCORE_BY_TAG.get(tags.get("recent_score_band", ""), None),
    )
    prep_context = PrepContext(
        weekly_hours_band=tags.get("weekly_study_hours", ""),
        remaining_weeks=None,
        attempt_history=tags.get("attempt_history", ""),
    )
    pass_readiness = result_builder(
        evidence,
        prep_context,
        scored_task_count=len(items),
        answered_count=answered_count,
        form_version=form_id,
        item_pool_version=blueprint_version,
        now_iso=str(now_iso or base["generated_at"]),
    )
    base["schema_version"] = PASS_READINESS_REPORT_SCHEMA_VERSION
    base["score_title"] = "一建过线体检结果"
    pass_readiness["evidence_items"] = build_evidence_items(items, list(session_questions or []))
    base["pass_readiness"] = pass_readiness
    return base


# 过线体检（pass_readiness）收敛条字段。诊断线报告在 result_report_json 的
# ``pass_readiness`` 块携带这些字段（build_pass_readiness_report 的 §7.2 envelope）；
# 旧专题报告没有该块 → 非体检报告，提取返回 None（前端显示体检引导）。
# 本函数是纯提取器：不推算带子、不改口径——带子真值只来自报告本身（诚实红线：
# 计划页收敛条只显示报告值，禁日级重估）。
PASS_READINESS_FIELDS = ("estimated_score_band", "pass_line", "risk_band")


def extract_pass_readiness_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    data = dict(report or {})
    block = data.get("pass_readiness")
    source = dict(block) if isinstance(block, dict) else data
    if not any(source.get(field) not in (None, "", {}) for field in PASS_READINESS_FIELDS):
        return None
    return {
        "estimated_score_band": source.get("estimated_score_band"),
        "pass_line": source.get("pass_line"),
        "risk_band": source.get("risk_band"),
        "generated_at": source.get("generated_at") or data.get("generated_at"),
    }


def assert_supported_report(report: dict[str, Any]) -> None:
    version = str(dict(report or {}).get("schema_version") or "").strip()
    if version not in SUPPORTED_REPORT_SCHEMA_VERSIONS:
        raise AssessmentReportError(f"unsupported_assessment_report_schema_version:{version or 'missing'}")


def _knowledge_map(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"attempted": 0, "correct": 0})
    for item in items:
        points = list(item.get("knowledge_points") or []) or ["综合能力"]
        for point in points:
            label = str(point or "").strip()
            if not label:
                continue
            totals[label]["attempted"] += 1
            totals[label]["correct"] += 1 if item.get("is_correct") else 0
    result: list[dict[str, Any]] = []
    for label, stats in sorted(totals.items()):
        attempted = max(stats["attempted"], 1)
        result.append(
            {
                "knowledge_point": label,
                "attempted": stats["attempted"],
                "correct": stats["correct"],
                "score_pct": round(stats["correct"] / attempted * 100),
            }
        )
    return result


def _session_local_next_action(wrong_items: list[dict[str, Any]], knowledge_map: list[dict[str, Any]]) -> dict[str, Any]:
    weak = sorted(knowledge_map, key=lambda item: (int(item.get("score_pct") or 0), -int(item.get("attempted") or 0)))
    if wrong_items and weak:
        target = weak[0]["knowledge_point"]
        return {
            "authority": "session_local_deterministic",
            "copy": f"建议先复盘{target}相关错题，再做 3 道同类专项练习。",
            "topic": target,
        }
    return {
        "authority": "session_local_deterministic",
        "copy": "建议保持节奏，后续用同专题短练巩固。",
        "topic": "",
    }
