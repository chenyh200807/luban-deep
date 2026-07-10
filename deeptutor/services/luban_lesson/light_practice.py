"""PRD v1.3 §0.0 头牌「2 分钟 per-考点 MCQ 轻练」——签发变体池 → 判断题投影 + 死判分 + 学情写入。

三段纯确定性、零 LLM：
1. **投影**（``build_light_practice_set``）：从**已签发变体池**（``_load_signed_bank``
   双 fail-closed 门，与 read_model 同一 loader，绝不第二个）确定性抽 n 条，投影成
   判断题 item。抽题只做**投影**（PRD §40 硬约束：不新造题、不 LLM）；无签发池 →
   空（fail-closed）。
2. **判分 + 诊断**（``score_light_practice``）：用户对/错答案 vs 签发池权威
   ``expected_ok`` → 命中/漏，死判定。漏的按 ``anchor`` 解析出采分点（kc）+ 教材章节
   （kc 内嵌 1A4XXXXX taxonomy chapter → ``taxonomy_label``）+ 真题出处。**判分只信
   服务端签发池的 expected_ok，绝不信客户端回传的答案键**（防篡改）。
3. **学情写入**（``record_light_practice_evidence``）：交卷结果走**既有 sink**
   ``learner_state_service.append_memory_event(memory_kind="learning_evidence")``——
   与 assessment/writeback、lesson_evidence 同一 sink、同一 learning_evidence 核心
   形态（event_type/question_id/is_correct/concept_id/error_codes/error_events），
   不新建第二个 sink、不发明新 payload 形态。锚 pack_id / 采分点(kc) / rule_group。

单一权威纪律（诚实边界，见模块尾注）：本模块把 MCQ 作答写进 learning_evidence 账本
并按 canonical 形态锚定，**但 source_feature ``luban_light_practice`` 是否进
``learning_synthesis.LEARNING_EVIDENCE_SOURCE_FEATURES`` 白名单（=是否 promote 掌握、
是否被 revalidation_queue 消费）是一个 owner 级 mastery-promotion 决定**，本变更
**不擅自翻**——与 lesson_evidence 的 ``luban_lesson`` 故意留在白名单外（M0 非
promoting）同构。复测调度权威仍归 revalidation_queue，本模块零调度逻辑。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from deeptutor.contracts.error_codes import check_emitted_error_codes
from deeptutor.services.luban_lesson.read_model import (
    _MANIFEST_PATH,
    _load_signed_bank,
    build_lesson_viewmodel,
)
from deeptutor.services.taxonomy.taxonomy_authority import (
    normalize_taxonomy_code,
    taxonomy_label,
)

# 判断题误判的确定性错因码（M 系 MCQ 判分，deeptutor/contracts/error_codes.py 已登记）。
# 死判定只知道「该规则判断没做对」；不臆断更细的 M03 概念混淆/M04 选项陷阱（需 LLM
# 归因，PRD §40 禁）——保守取 M01 知识点不熟（code_application）。
_MCQ_MISJUDGE_CODE = "M01"

# 采分点 token 前缀（签发池实测：kc=采分点 955、cc=考点卡点 64；两者都是采分点级
# 锚且内嵌 taxonomy chapter）。ca=母题锚（case anchor，单列），BARE=真题出处。
_SCORING_POINT_PREFIXES = ("kc:", "cc:")
# 采分点 id 内嵌 1A4XXXXX taxonomy chapter code（如 kc:1A433000_056_0085:1 → 1A433000）。
_KC_CHAPTER_RE = re.compile(r"(?:kc|cc):(1A4\d{4,5})")


def _split_anchor(anchor: str) -> list[str]:
    return [tok.strip() for tok in str(anchor or "").split("+") if tok.strip()]


def parse_anchor(anchor: str) -> dict[str, Any]:
    """anchor 串 → 采分点(kc) + 真题出处（纯字符串解析，零生成）。

    anchor 形如 ``kc:1A433000_056_0085:1 + {2015,案例1} + {2020,案例二问题2}``，
    ``+`` 分隔：
    - ``kc:...`` / ``cc:...`` token → 采分点（scoring point）；取全部，主采分点=第一个。
    - ``ca:...`` token → 母题锚（case anchor），既非采分点也非真题出处，单列。
    - 其余 BARE token（``{2015,案例1}`` / ``2022第(四)题`` 等）→ 真题出处（exam refs），
      原样透传（不改写、不猜年份）。
    每个采分点再解析内嵌 taxonomy chapter → 教材章节 label（能解析才给，否则留空）。
    注：签发池约 14% 变体只有真题出处 / ca 而无 kc/cc 采分点 → scoring_point="" 是
    诚实 fail-closed，诊断退到 exam_refs + rule_group（不臆造采分点）。
    """
    scoring_points: list[str] = []
    case_anchors: list[str] = []
    exam_refs: list[str] = []
    for tok in _split_anchor(anchor):
        if tok.startswith(_SCORING_POINT_PREFIXES):
            scoring_points.append(tok)
        elif tok.startswith("ca:"):
            case_anchors.append(tok)
        else:
            exam_refs.append(tok)
    return {
        "scoring_point": scoring_points[0] if scoring_points else "",
        "scoring_points": scoring_points,
        "case_anchors": case_anchors,
        "exam_refs": exam_refs,
        "textbook_chapters": [
            chapter
            for kc in scoring_points
            for chapter in (_chapter_for_kc(kc),)
            if chapter is not None
        ],
    }


def _chapter_for_kc(kc: str) -> dict[str, str] | None:
    """kc 内嵌 taxonomy chapter → {code,label} 教材章节定位（能解析才给，fail-closed）。"""
    match = _KC_CHAPTER_RE.search(str(kc or ""))
    if not match:
        return None
    code = normalize_taxonomy_code(match.group(1))
    label = taxonomy_label(code) if code else ""
    if not code or not label:
        return None
    return {"scoring_point": str(kc), "taxonomy_code": code, "chapter_label": label}


def _project_item(variant: dict[str, Any]) -> dict[str, Any]:
    """签发变体 → 判断题 item（纯投影，逐字透传，零生成）。"""
    parsed = parse_anchor(variant.get("anchor"))
    return {
        "variant_id": str(variant.get("variant_id") or ""),
        "rule_group": str(variant.get("rule_group") or ""),
        "statement": str(variant.get("surface") or ""),   # 说法（判断题题面）
        "answer": bool(variant.get("expected_ok")),       # 对/错=确定性答案
        "correct_statement": str(variant.get("correct_statement") or ""),
        "scoring_point": parsed["scoring_point"],
        "scoring_points": parsed["scoring_points"],
        "exam_refs": parsed["exam_refs"],
        "textbook_chapters": parsed["textbook_chapters"],
        "anchor": str(variant.get("anchor") or ""),
    }


def _signed_core_variants(
    pack_id: str, *, manifest_path: Path | None = None
) -> list[dict[str, Any]]:
    """签发池核心变体（extension=false）——过投影门 + 双 fail-closed 签发闸。

    非绿灯/不存在 pack → LessonNotAvailable（由 build_lesson_viewmodel 抛，端点转 404）。
    无签发池 / candidate / sha 漂移 / 无核心变体 → ``[]``（fail-closed，与缺失同形）。
    """
    vm = build_lesson_viewmodel(pack_id, manifest_path=manifest_path)
    if not vm["variant_retest"]["available"]:
        return []
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    bank = _load_signed_bank(vm["pack_id"], manifest_dir, vm["content_sha256"])
    if bank is None:
        return []
    return [
        v
        for v in bank.get("variants") or []
        if isinstance(v, dict) and not v.get("extension") and v.get("variant_id")
    ]


def _round_robin_by_rule_group(
    variants: list[dict[str, Any]], n: int
) -> list[dict[str, Any]]:
    """确定性抽 n 条，优先覆盖不同 rule_group（种子固定=文件序，无 RNG，全幂等）。

    按 rule_group 首见序分组（组内保持文件序），轮转每组各取一条直到取满 n；
    保证同一 pack 同一 n 每次返回完全相同的题面切片（多端幂等）。池小于 n → 全发。
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for v in variants:
        groups.setdefault(str(v.get("rule_group") or ""), []).append(v)
    ordered_groups = list(groups.values())
    picked: list[dict[str, Any]] = []
    idx = 0
    while len(picked) < n and any(idx < len(g) for g in ordered_groups):
        for g in ordered_groups:
            if idx < len(g):
                picked.append(g[idx])
                if len(picked) >= n:
                    break
        idx += 1
    return picked


def build_light_practice_set(
    pack_id: str, *, n: int = 5, manifest_path: Path | None = None
) -> list[dict[str, Any]]:
    """签发变体池 → n 条判断题轻练集（确定性、幂等、零 LLM、纯投影）。

    PRD §0.0 头牌数据源 = 已签发母题集变体池；本函数只**投影**（不生成、不新造题）。
    ``n`` 钳到 [1,10]。无签发池 → ``[]``（fail-closed，PRD §40）。
    """
    n = max(1, min(int(n), 10))
    core = _signed_core_variants(pack_id, manifest_path=manifest_path)
    if not core:
        return []
    return [_project_item(v) for v in _round_robin_by_rule_group(core, n)]


def score_light_practice(
    pack_id: str,
    user_answers: dict[str, bool],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """死判分 + 诊断——用户判断 vs 签发池权威 expected_ok（零 LLM，确定性）。

    ``user_answers`` = ``{variant_id: bool}``（用户对该说法判「对/True 或 错/False」）。
    **判分只信服务端签发池的 expected_ok**：客户端从不回传答案键，未在签发池的
    variant_id 一律忽略（fail-closed，不给分不诊断）。漏题（判错）诊断 = 采分点(kc)
    + 教材章节（kc 内嵌 chapter → label）+ 真题出处 + 误判错因码（M01）。
    """
    by_id = {
        v["variant_id"]: v
        for v in _signed_core_variants(pack_id, manifest_path=manifest_path)
    }
    items: list[dict[str, Any]] = []
    correct_count = 0
    for variant_id, raw_answer in (user_answers or {}).items():
        variant = by_id.get(str(variant_id))
        if variant is None:
            continue  # 不在签发池 → 不判（fail-closed，防伪题/陈旧题混入）
        projected = _project_item(variant)
        user_answer = bool(raw_answer)
        expected = projected["answer"]
        is_correct = user_answer == expected
        if is_correct:
            correct_count += 1
        item = {
            "variant_id": projected["variant_id"],
            "rule_group": projected["rule_group"],
            "user_answer": user_answer,
            "expected": expected,
            "is_correct": is_correct,
            "scoring_point": projected["scoring_point"],
            "scoring_points": projected["scoring_points"],
            "exam_refs": projected["exam_refs"],
            "textbook_chapters": projected["textbook_chapters"],
            "correct_statement": projected["correct_statement"],
        }
        if not is_correct:
            # 误判诊断：mistake_tag(错因码,已登记) + 采分点 + 教材章节 + 真题出处。
            item["error_code"] = _MCQ_MISJUDGE_CODE
        items.append(item)
    total = len(items)
    return {
        "pack_id": str(pack_id).upper(),
        "total": total,
        "correct_count": correct_count,
        "missed": [it for it in items if not it["is_correct"]],
        "items": items,
    }


def record_light_practice_evidence(
    learner_state_service: Any,
    *,
    user_id: str,
    scored: dict[str, Any],
) -> list[dict[str, Any]]:
    """交卷结果 → learning_evidence（既有 sink，不新建第二个 sink / 第四个 builder）。

    每道题一条 learning_evidence，形态与 assessment/writeback 的 learning_evidence
    核心键对齐（event_type/question_id/learner_answer/correct_answer/is_correct/
    concept_id/knowledge_points/error_codes/error_events）。锚 pack_id / 采分点(kc)
    / rule_group。写前 ``check_emitted_error_codes`` 守住只发已登记错因码。

    source_feature=``luban_light_practice``（register-before-use 语义：**未进
    learning_synthesis 白名单前 = M0 非 promoting**，见模块 docstring 诚实边界）。
    返回写入事件的 ref 列表。
    """
    normalized_user = str(user_id or "").strip()
    if not normalized_user:
        raise ValueError("user_id is required")
    pack_id = str(scored.get("pack_id") or "").strip().upper()
    if not pack_id:
        raise ValueError("scored.pack_id is required")

    all_codes = [
        str(it.get("error_code") or "").strip()
        for it in list(scored.get("items") or [])
        if str(it.get("error_code") or "").strip()
    ]
    check_emitted_error_codes(all_codes)  # fail-closed：未登记错因码不许落账本

    refs: list[dict[str, Any]] = []
    for item in list(scored.get("items") or []):
        variant_id = str(item.get("variant_id") or "").strip()
        if not variant_id:
            continue
        scoring_point = str(item.get("scoring_point") or "").strip()
        error_codes = [c for c in [str(item.get("error_code") or "").strip()] if c]
        is_correct = bool(item.get("is_correct"))
        payload_json = {
            "event_type": "learning_evidence",
            "learning_signal_type": "light_practice_answered",
            "pack_id": pack_id,
            "question_id": variant_id,
            "rule_group": str(item.get("rule_group") or ""),
            "learner_answer": bool(item.get("user_answer")),
            "correct_answer": bool(item.get("expected")),
            "is_correct": is_correct,
            "concept_id": scoring_point,
            "knowledge_points": [scoring_point] if scoring_point else [],
            "scoring_points": list(item.get("scoring_points") or []),
            "exam_refs": list(item.get("exam_refs") or []),
            "textbook_chapters": list(item.get("textbook_chapters") or []),
            "error_codes": error_codes,
            "error_events": [
                {"error_code": code, "concept_tag": scoring_point}
                for code in error_codes
            ],
        }
        event = learner_state_service.append_memory_event(
            normalized_user,
            source_feature="luban_light_practice",
            source_id=f"light_practice:{pack_id}:{variant_id}",
            memory_kind="learning_evidence",
            payload_json=payload_json,
            dedupe_key=f"light_practice:{normalized_user}:{pack_id}:{variant_id}",
        )
        refs.append(
            {
                "event_id": str(event.event_id),
                "question_id": variant_id,
                "is_correct": is_correct,
                "kind": "learning_evidence",
            }
        )
    return refs


__all__ = [
    "build_light_practice_set",
    "parse_anchor",
    "record_light_practice_evidence",
    "score_light_practice",
]
