from __future__ import annotations

import re
from typing import Any


_HARD_SCORE_RE = re.compile(
    r"(预计得分|满分\s*\d+(?:\.\d+)?\s*分|\d+(?:\.\d+)?\s*分\s*/|"
    r"/\s*(?:满分)?\s*\d+(?:\.\d+)?\s*分|给\s*\d+(?:\.\d+)?\s*分|"
    r"扣\s*\d+(?:\.\d+)?\s*分)"
)
_OFFICIAL_GRADING_RE = re.compile(
    r"(采分点批改|采分点拆解|命中采分点|漏分点|漏采分点|缺一个采分点|"
    r"判错|阅卷|给分|扣分|满分)"
)
_DIAGNOSTIC_ONLY_MARKER = "本次不硬估标准分"

# 案例作答标记族的单一权威（OD-001/002 取证裁决 2026-07-31）：此前切割侧
# （question_lifecycle_skills）与标题抽取侧（rubric_grader_v1）各持一张标记
# 名单——切割侧缺【我的作答】括号形，一个缺口让整套倒诬防线（身份闸+数字
# 变体闸+覆盖对账）同时解除武装（假命中 17315 的答案钥匙判学生正确作答为零）。
# 两侧现共用本模式；增标记只改这里。
CASE_ANSWER_MARKER_PATTERN: str = (
    r"(?:(?:^|[\r\n]|[ \t。；;!！?？])(?:回答[ \t]*)?"
    r"(?:作答|我的作答|学生作答|我的答案|答案)[ \t]*[:：][ \t]*"
    r"|【我的作答】[ \t]*|【作答】[ \t]*|【我的答案】[ \t]*"
    r"|(?:^|[\r\n])[ \t]*我的(?:答案|作答)[ \t]*(?:[:：][ \t]*)?(?=[\r\n]|$))"
)
_CASE_SCORE_AUTHORITY_KINDS = {"case", "case_study", "case_bundle", "written", "subjective"}

# 判分权威导出键的单一权威（倾向四收权，2026-07-30 owner 拍板根治）。
# 此前同一组键散落三张互不同步的白名单（turn_runtime summarizer lift /
# 本文件 TURN_METADATA_KEYS / turn_runtime 终态事件白名单），live 实证漏一张
# 名单=该 sink 永久 0 命中。三处现全部消费本常量：增键改这里一处即全链生效。
# 注意：exact_question_blocked_reason / case_reference_blocked_reason 是跨场景
# 通用 marker（mcq/澄清路径也写），不得收进任何 case 专属清单——strip 语义会在
# 非 case 轮把它们剥掉（CI 实证 low_information_exam_query 断言被破坏）。
CASE_GRADING_AUTHORITY_EXPORT_KEYS: tuple[str, ...] = (
    "score_authority",
    "grading_rubric_provenance",
    "grading_official_score_allowed",
    "v1_case_graded",
    "case_grading_prefetch_gate",
    "case_grading_direct_fell_through",
    "case_grading_direct_attempt_qid",
    "case_grading_composite_qid_candidate",
    "case_grading_outer_seam_reentry",
    "case_rubric_score_total_mismatch",
    # 护栏③（2026-07-30）：活动 bank slot 身份逐轮上全 sink——slot 未授权漂移
    # 六周无人知的洞，用导出封死。形如 "legacy:authorized:174"。
    "case_rubric_bank_slot",
    # A1 真口诀（拍A 2026-07-30）：口诀来源发声——lecture_pack:<unit_ids> 或
    # fallback_template。挂载率/回落率的观测基础。
    "case_mnemonic_source",
    # OD-004（2026-08-01）：判分基座兜底发声——scene 抖动导致题面缺位时，
    # 以学生原文为 tier3 推导基座（"判分行为在场必须有判分基座"）。
    "case_stem_fallback",
    # P0 兜底满分根治（2026-08-01）：参考只覆盖部分小问时的判分范围声明，
    # 形如 "1/4"——分数只代表该范围，且不得声称官方分。
    "case_grading_partial_scope",
    # 逐跳 surface 对账插桩（2026-08-01，只 hash/长度不落全文）：定位通道漂移
    # 与幽灵小问的分叉跳。
    "case_probe_stem_hash",
    "case_probe_stem_len",
    "case_probe_answer_len",
    "case_probe_marker_count",
    "case_user_stem_hash",
    "case_user_stem_len",
    # L1 瘦身检索（2026-08-01）：直通轮实际生效的检索深度 —— "lean" | "full"。
    # live 验收判据（exact 命中/分母与 full 轮一致、RAG 跳 <2s、rerank 0 次）
    # 全靠这个 marker 分组；kill switch LUBAN_CASE_DIRECT_LEAN_RAG 关掉即回 "full"。
    "case_direct_rag_profile",
    # 踩点封顶观测（裁决② 2026-07-30，observe-only）：Σ点分池超小题满分的超额量。
    # 真题判分=min(Σ命中,满分)且池≥满分是常态；V1 无封顶→先量化在服发生率，
    # 确定性封顶=canonical bank 上服硬前置。
    "point_pool_exceeds_max",
    # 覆盖对账（2026-07-30）：判分实际覆盖的小问数/题面小问数 + 未覆盖清单。
    # live 事故=学生答 2/4 问被判整题满分——部分覆盖必须发声且分数只代表已覆盖部分。
    "case_subq_coverage",
    "case_subq_uncovered",
)

CASE_GRADING_TURN_METADATA_KEYS: tuple[str, ...] = (
    "grading_engine_version",
    *CASE_GRADING_AUTHORITY_EXPORT_KEYS,
    "grading_to_brain_loop",
    "learning_evidence_event_id",
    "learning_training_intent",
    "grading_to_brain_projection",
    "case_grading_stream_mode",
    "case_grading_adjudication_strategy",
    "case_grading_adjudication_group_count",
    "case_grading_adjudication_point_count",
)
# An explicit case-style score *verdict* (not a bare 采分点 teaching label, a
# rubric like "满分100分", or a unit price like "5分/平米"). Used only as the
# safety net for unclassified turns that escaped case_grading scene derivation;
# matches "不得分", "得 4 分", "4分/满分5分", "0分/5分", "**0分。**", "0 个采分点",
# "预计得分". The bolded ``**N分**`` arm catches a forced-score verdict like
# R3-16 ("**0分。**") while leaving unbolded rubric/unit-price text alone.
_NO_AUTHORITY_CASE_SCORE_RE = re.compile(
    r"(不得分"
    r"|得\s*\d+(?:\.\d+)?\s*分"
    r"|\d+(?:\.\d+)?\s*分\s*[/／]\s*(?:满分\s*)?\d"
    r"|\*\*\s*\d+(?:\.\d+)?\s*分\s*[。.！!]"
    r"|\d+\s*个?\s*采分点"
    r"|得分\s*[:：]\s*\d"
    r"|预计得分)"
)


def case_grading_score_authority_available(runtime_metadata: dict[str, Any] | None) -> bool:
    """Return True only when the current case turn owns score authority."""

    metadata = runtime_metadata if isinstance(runtime_metadata, dict) else {}
    if str(metadata.get("question_lifecycle_scene") or "").strip() != "case_grading":
        return False
    for key in ("_prefetched_exact_question", "exact_question"):
        exact_question = metadata.get(key)
        if not isinstance(exact_question, dict) or not exact_question:
            continue
        if _exact_question_has_case_score_authority(exact_question):
            return True
    return False


def copy_current_case_grading_turn_metadata(
    source_metadata: dict[str, Any] | None,
    target_metadata: dict[str, Any] | None,
) -> None:
    """Project case-grading receipt fields only for the current case-grading turn."""

    if not isinstance(target_metadata, dict):
        return
    if (
        not isinstance(source_metadata, dict)
        or str(source_metadata.get("question_lifecycle_scene") or "").strip() != "case_grading"
    ):
        strip_case_grading_turn_metadata(target_metadata)
        return
    for key in CASE_GRADING_TURN_METADATA_KEYS:
        if key in source_metadata:
            target_metadata[key] = source_metadata[key]


def strip_case_grading_turn_metadata(metadata: dict[str, Any] | None) -> None:
    if not isinstance(metadata, dict):
        return
    for key in CASE_GRADING_TURN_METADATA_KEYS:
        metadata.pop(key, None)


def _exact_question_has_case_score_authority(exact_question: dict[str, Any]) -> bool:
    answer_kind = str(exact_question.get("answer_kind") or "").strip().lower()
    if _has_case_score_evidence(exact_question.get("case_bundle")):
        return True
    if _has_case_score_evidence(exact_question.get("grading_key")):
        return True
    if _has_case_score_evidence(exact_question.get("covered_subquestions")):
        return True
    if answer_kind not in _CASE_SCORE_AUTHORITY_KINDS:
        return False
    return bool(exact_question.get("correct_answer") or exact_question.get("authoritative_answer"))


def _has_case_score_evidence(value: Any) -> bool:
    if isinstance(value, list):
        return any(_has_case_score_evidence(item) for item in value)
    if not isinstance(value, dict) or not value:
        return False

    for key in ("authoritative_answer", "correct_answer", "standard_answer", "reference_answer"):
        if str(value.get(key) or "").strip():
            return True

    for key in ("scoring_points", "grading_points", "score_points"):
        if _has_non_empty_collection(value.get(key)):
            return True

    for key in ("rubric", "grading_rubric", "grading_key", "covered_subquestions", "case_bundle"):
        if _has_case_score_evidence(value.get(key)):
            return True

    return False


def _has_non_empty_collection(value: Any) -> bool:
    if isinstance(value, list):
        return any(item not in (None, "", [], {}) for item in value)
    if isinstance(value, dict):
        return bool(value)
    return False


def _has_any_grading_authority(metadata: dict[str, Any]) -> bool:
    """True when the turn owns a real graded-question authority of any kind.

    Protects legitimate MCQ/active-object grading (which carries an authoritative
    exact question or a single-question active object) from the unclassified-turn
    safety net below.
    """

    if metadata.get("authority_applied") is True:
        return True
    for key in ("_prefetched_exact_question", "exact_question"):
        exact_question = metadata.get(key)
        if isinstance(exact_question, dict) and exact_question:
            return True
    active_object = metadata.get("active_object")
    if isinstance(active_object, dict) and str(active_object.get("object_type") or "").strip() == "single_question":
        return True
    return False


def should_demote_case_grading_hard_score(
    response: str | None,
    *,
    runtime_metadata: dict[str, Any] | None,
) -> bool:
    """Detect a case-grading official-score claim produced without authority."""

    metadata = runtime_metadata if isinstance(runtime_metadata, dict) else {}
    text = str(response or "")
    if _DIAGNOSTIC_ONLY_MARKER in text:
        return False

    scene = str(metadata.get("question_lifecycle_scene") or "").strip()
    if scene == "case_grading":
        if case_grading_score_authority_available(metadata):
            return False
        return _HARD_SCORE_RE.search(text) is not None or _OFFICIAL_GRADING_RE.search(text) is not None

    # Safety net for the P1-A leak: an unclassified turn (no lifecycle scene) that
    # still asserts an official case-style score verdict while owning no grading
    # authority of any kind — e.g. an out-of-bank pasted case the lifecycle did
    # not tag as case_grading. Recognized non-case scenes (mcq_grading, …) are
    # handled by their own guards and are intentionally excluded here.
    if not scene and not _has_any_grading_authority(metadata):
        return _NO_AUTHORITY_CASE_SCORE_RE.search(text) is not None
    return False


def build_case_grading_score_disclaimer() -> str:
    """Score-scope disclaimer appended to a SUBSTANTIVE no-authority diagnosis.

    P0 2026-07-29（权力/证据相称律）: the static template below keeps its birth
    mission — refusing to fabricate an OFFICIAL score — but loses the whole-text
    replacement power it had usurped. When the generation path produced real
    per-subquestion diagnosis, only the score CLAIM gets demoted, via this
    appended disclaimer; the diagnosis itself must reach the learner.
    """

    return (
        "\n\n---\n"
        "**评分口径说明**：本轮未命中题库原题/标准采分点，以上是教学诊断反馈，"
        "不构成官方阅卷得分；官方分数以真题标准答案与采分点为准。"
        "如需按标准采分点逐条批改，可以把题卡或标准答案一起发来。"
    )


def build_case_grading_diagnostic_only_response(user_message: str) -> str:
    """Student-facing fail-open answer when case score authority is missing."""

    answer = _extract_user_answer(user_message)
    answer_line = f"\n\n你当前作答：{answer}" if answer else ""
    return (
        "## 评分口径\n"
        "提分诊断（本轮没有命中题库原题、标准答案或结构化采分点）\n\n"
        "## 预计得分\n"
        "未命中评分真相层，本轮不硬估分。\n"
        "本次不硬估标准分。"
        f"{answer_line}\n\n"
        "## 先看你的作答\n"
        "- 可以先保留你已经写出的判断和关键参数。\n"
        "- 但案例题是否给分，必须以原题标准答案、分值和采分点为准；本轮没有这份 authority，不能把诊断包装成官方阅卷。\n\n"
        "## 下一步\n"
        "把题卡、题号、标准答案或采分点一起发来，我再按标准采分点逐条批改；如果只有题面和你的作答，我可以继续帮你改成更像考试得分表达。"
    )


def _extract_user_answer(user_message: str) -> str:
    text = str(user_message or "").strip()
    if not text:
        return ""
    match = re.search(r"(?:我的答案|我答|答案)\s*[：:]\s*(.*)", text, flags=re.S)
    if not match:
        return ""
    answer = match.group(1).strip()
    answer = re.split(r"(?:请|帮我|麻烦)?(?:按|帮|给|批改|估分|打分|判分)", answer, maxsplit=1)[0]
    return answer.strip(" \n\t，。；;")[:160]

def case_submission_stem_candidate(text: str, *, min_len: int = 120) -> str:
    """判分基座候选（OD-004 终修 2026-08-01）：「判分行为在场」的语义判据。

    live 10 轮源码级取证：上一版兜底锚写成形状正则（【背景资料】/【问题】），
    而真实考卷粘贴（#583 原文「某办公楼工程…」+ 半角「问题:」）三锚全不命中
    → 兜底十轮零触发 → 与未修时同一条路。判据必须回到语义：**学生提交了
    可判分的案例作答**——痕迹是提交标记（CASE_ANSWER_MARKER_PATTERN，与切割
    侧同一权威）或多小问结构，而不是题面用不用括号。

    返回可作 tier3 推导基座的文本（空串=判据不成立，不得制造假判分面）。
    """
    raw = str(text or "").strip()
    if len(raw) < min_len:
        return ""
    has_submission_marker = re.search(CASE_ANSWER_MARKER_PATTERN, raw, flags=re.IGNORECASE) is not None
    # 多小问结构：全/半角「问题N」「第N问」或行首编号问句 ≥2 处
    subquestion_hits = len(
        re.findall(r"(?:问题\s*[:：]?\s*\d|第\s*\d+\s*问|(?:^|\n)\s*\d+\s*[.．、)）]\s*\S)", raw)
    )
    case_shape = bool(re.search(r"【背景资料】|背景资料|【问题】|工程概况", raw))
    if has_submission_marker or subquestion_hits >= 2 or case_shape:
        return raw[:4000]
    return ""
