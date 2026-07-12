"""每考点（pack_id 主键）生命周期投影（融合计划 §1）——纯派生 read model。

```
未学 → 已学·待验证(exposed) → 练过(practiced) → 真懂(mastered) → 休眠·会忘(dormant)
```

单一权威边界（§8 红线）：
- **零写入**：本模块不碰 append-only 账本、不建第二状态表——「未学」在投影层
  派生 = pack 全集（``_pack_manifest.json`` 40 包）−有证据集合。
- 掌握判定只引用既有 claim（``learning_synthesis`` 产出的 evidence_level /
  decay_state），mastery 算子仍只有 ``mastery_estimator``；本模块不重算分数。
- M0：``exposed``（看动画）永远停在蓝环（接触轨），绝不进掌握轨；真懂
  （mastered）只认**显式正向信号** ``verified_concepts``（prescription_outcome
  verified 的 concept/taxonomy codes，由 caller 传入）——弱点 claim 的
  evidence_level 只说明「弱点有多可信」，复测确认弱点绝不能翻成已掌握
  （病G 语义反转防护）。正向信号尚未接线前 caller 传空，fail-closed 停在
  practiced，不虚标。dormant = 真懂过 + 记忆衰减（``stale``）；``improving``
  = 弱点仍在改善 ≠ 该休眠，不进 dormant。
- 练-evidence → pack 的 join 只走两条确定性路径（§2.4）：
  ① question_id ∈ 题→pack 编译映射（``_question_pack_map.v0.json``）；
  ② canonical_topic.taxonomy_code ∈ pack refs（``_pack_taxonomy_registry.v0.json``，
  歧义用 provisional primary_taxonomy_ref 消歧）。两条都失败 → 「未归位」桶
  如实报告，禁硬塞。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from deeptutor.services.learner_state.evidence_lifecycle import (
    is_signed_luban_retest_terminal,
)
from deeptutor.services.learner_state.lesson_evidence import is_lesson_view_event

_REPO = Path(__file__).resolve().parents[3]
_ARTIFACT_DIR = _REPO / "docs" / "原始数据" / "考点原料" / "成品"
_QUESTION_PACK_MAP_PATH = _ARTIFACT_DIR / "_question_pack_map.v0.json"
_PACK_TAXONOMY_REGISTRY_PATH = _ARTIFACT_DIR / "_pack_taxonomy_registry.v0.json"

LIFECYCLE_UNLEARNED = "unlearned"
LIFECYCLE_EXPOSED = "exposed"
LIFECYCLE_PRACTICED = "practiced"
LIFECYCLE_MASTERED = "mastered"
LIFECYCLE_DORMANT = "dormant"

# 编译产物的单一 loader 汇点（照 m35_artifact_query 的 (mtime_ns, size) 模式）：
# 失败（缺文件/损坏）**绝不写缓存**——修好文件后同进程下次调用即恢复；
# 成功才按 stat 键缓存，产物热更新（mtime 变）自动失效。降级必打 warning 可观测，
# 且 ok=False 上抛到投影输出的 ``degraded`` 标志——空映射绝不冒充健康。
_ARTIFACT_CACHE: dict[str, tuple[tuple[int, int], Any]] = {}


def _load_compiled_artifact(path: Path, project: Any) -> tuple[Any, bool]:
    """返回 (投影结果, ok)。ok=False = 产物缺失/损坏（降级，未缓存）。"""
    try:
        stat = path.stat()
        stat_key = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        logger.warning("pack lifecycle artifact missing (degraded, not cached): {}", path)
        return project(None), False
    cache_key = str(path)
    cached = _ARTIFACT_CACHE.get(cache_key)
    if cached is not None and cached[0] == stat_key:
        return cached[1], True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("pack lifecycle artifact unreadable (degraded, not cached): {}", path)
        return project(None), False
    projected = project(payload)
    _ARTIFACT_CACHE[cache_key] = (stat_key, projected)
    return projected, True


def _project_question_index(
    compiled: dict[str, Any] | None,
) -> tuple[dict[str, tuple[str, ...]], frozenset[str]]:
    """双键索引：qualified `year:chunk_id` 精确键 + 裸 chunk_id 键（合并跨年，
    仅唯一 pack 时才可 join——歧义由 resolver fail-closed 处理）。零碰撞：
    qualified 键恒有 `^\\d{4}:` 前缀，裸键不含 `:`（专家 B 实测 252/234 键验证）。

    第二返回值 = 跨年碰撞黑名单（病H-1 审计实测 14 个）：同一裸 chunk_id
    出现在 >1 个年份且各年 pack fan-out **不同**——裸键 join 对这些 id
    永远歧义，resolver 专用 reason="cross_year_ambiguous" fail-closed。"""
    if not isinstance(compiled, dict):
        return {}, frozenset()
    index: dict[str, set[str]] = {}
    year_sets: dict[str, dict[str, frozenset[str]]] = {}
    for qualified, packs in (compiled.get("reverse_index") or {}).items():
        index.setdefault(qualified, set()).update(packs)
        year, _, bare = qualified.partition(":")
        index.setdefault(bare, set()).update(packs)
        year_sets.setdefault(bare, {})[year] = frozenset(packs)
    cross_year_ambiguous = frozenset(
        bare
        for bare, by_year in year_sets.items()
        if len(by_year) > 1 and len(set(by_year.values())) > 1
    )
    return (
        {key: tuple(sorted(value)) for key, value in index.items()},
        cross_year_ambiguous,
    )


def _question_to_packs() -> tuple[tuple[dict[str, tuple[str, ...]], frozenset[str]], bool]:
    return _load_compiled_artifact(_QUESTION_PACK_MAP_PATH, _project_question_index)


def _project_taxonomy_index(
    compiled: dict[str, Any] | None,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    if not isinstance(compiled, dict):
        return {}, {}
    primary: dict[str, set[str]] = {}
    any_ref: dict[str, set[str]] = {}
    for pack_id, entry in (compiled.get("packs") or {}).items():
        primary_ref = str(entry.get("primary_taxonomy_ref") or "").strip()
        if primary_ref:
            primary.setdefault(primary_ref, set()).add(pack_id)
        for ref in (primary_ref, *(entry.get("supporting_taxonomy_refs") or [])):
            code = str(ref or "").strip()
            if code:
                any_ref.setdefault(code, set()).add(pack_id)
    return (
        {key: tuple(sorted(value)) for key, value in primary.items()},
        {key: tuple(sorted(value)) for key, value in any_ref.items()},
    )


def _taxonomy_to_packs() -> tuple[tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]], bool]:
    """返回 ((taxonomy_code → primary 命中 packs, → 任意 ref 命中 packs), ok)。"""
    return _load_compiled_artifact(_PACK_TAXONOMY_REGISTRY_PATH, _project_taxonomy_index)


def _resolve_pack_for_practice(payload: dict[str, Any]) -> tuple[str, str]:
    """返回 (pack_id, join_path)；无法唯一归位 → ("", 原因)。"""
    question_id = str(payload.get("question_id") or "").strip()
    (question_index, cross_year_ambiguous), _ = _question_to_packs()
    if question_id:
        packs = question_index.get(question_id) or ()
        if len(packs) == 1:
            return packs[0], "question_map"
    topic = payload.get("canonical_topic") if isinstance(payload.get("canonical_topic"), dict) else {}
    code = str(topic.get("taxonomy_code") or topic.get("taxonomy_id") or "").strip()
    if not code:
        code = str(payload.get("taxonomy_code") or payload.get("node_code") or "").strip()
    if code:
        (primary, any_ref), _ = _taxonomy_to_packs()
        primary_hits = primary.get(code) or ()
        if len(primary_hits) == 1:
            return primary_hits[0], "taxonomy_primary"
        ref_hits = any_ref.get(code) or ()
        if len(ref_hits) == 1:
            return ref_hits[0], "taxonomy_ref"
        if ref_hits:
            return "", "taxonomy_ambiguous"
    if question_id and question_id in cross_year_ambiguous:
        # 跨年 fan-out 碰撞(病H-1):裸 id join 永远歧义,专用 reason 可观测。
        return "", "cross_year_ambiguous"
    if question_id and question_index.get(question_id):
        return "", "question_ambiguous"
    return "", "unmapped"


def _is_practice_evidence(event: Any) -> bool:
    if str(getattr(event, "memory_kind", "") or "") != "learning_evidence":
        return False
    if is_lesson_view_event(event):
        return False
    payload = getattr(event, "payload_json", None) or {}
    if not isinstance(payload, dict):
        return False
    if str(payload.get("evidence_source") or "") == "conversation_synthesis":
        return False
    # 判分级白名单唯一 authority 在 learning_synthesis(病D-3),此处只引用。
    from deeptutor.services.learner_state.learning_synthesis import (
        PRACTICE_EVIDENCE_SOURCE_FEATURES,
    )

    return str(getattr(event, "source_feature", "") or "") in PRACTICE_EVIDENCE_SOURCE_FEATURES


def _claim_packs(claims: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """claim（concept_id=taxonomy code）→ pack 的最强掌握信号聚合。"""
    (primary, any_ref), _ = _taxonomy_to_packs()
    by_pack: dict[str, dict[str, Any]] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        code = str(claim.get("concept_id") or "").strip()
        if not code:
            continue
        hits = primary.get(code) or ()
        if len(hits) != 1:
            ref_hits = any_ref.get(code) or ()
            hits = ref_hits if len(ref_hits) == 1 else ()
        if not hits:
            continue
        pack_id = hits[0]
        slot = by_pack.setdefault(pack_id, {"decay_states": set(), "claim_count": 0})
        slot["claim_count"] += 1
        decay = str(claim.get("decay_state") or "").strip()
        if decay:
            slot["decay_states"].add(decay)
    return by_pack


def _pack_retest_facts(events: list[Any]) -> dict[str, dict[str, Any]]:
    """Project terminal-only signed retest facts per pack.

    Item rows and ``station_completed`` mirrors are intentionally ignored.  The
    canonical completion terminal already carries the server-rescored outcome;
    accepting a partial item append here would let an interrupted write promote
    lifecycle or move the review clock.
    """
    by_pack: dict[str, dict[str, Any]] = {}
    seen_completions: set[str] = set()
    ordered = sorted(
        list(events or []),
        key=lambda event: (
            str(getattr(event, "created_at", "") or ""),
            str(getattr(event, "event_id", "") or ""),
        ),
    )
    for event in ordered:
        payload = getattr(event, "payload_json", None) or {}
        if not isinstance(payload, dict) or not is_signed_luban_retest_terminal(event):
            continue
        completion_id = str(payload.get("retest_completion_id") or "").strip()
        pack_id = str(payload.get("pack_id") or payload.get("target_pack_id") or "").strip().upper()
        if completion_id in seen_completions:
            continue
        seen_completions.add(completion_id)
        mode = "review" if str(payload.get("practice_mode") or "").strip() == "review" else "forward"
        created_at = str(getattr(event, "created_at", "") or "").strip()
        event_id = str(getattr(event, "event_id", "") or "").strip()
        fact = by_pack.setdefault(
            pack_id,
            {
                "last_completion_at": "",
                "last_review_at": "",
                "last_review_status": "",
                "successful_review_streak": 0,
                "review_cycle_anchor": "",
                "terminal_evidence_refs": [],
            },
        )
        fact["last_completion_at"] = created_at
        fact["review_cycle_anchor"] = event_id or completion_id
        if event_id:
            fact["terminal_evidence_refs"].append(event_id)
        if mode != "review":
            # A new forward completion starts a fresh learning cycle.  Older
            # review success must not keep the new cycle on its old 7/14-day
            # clock.
            fact["last_review_at"] = ""
            fact["last_review_status"] = ""
            fact["successful_review_streak"] = 0
            continue
        result = payload.get("prescription_result")
        status = str(result.get("status") or "").strip() if isinstance(result, dict) else ""
        verified = status == "verified"
        fact["last_review_at"] = created_at
        fact["last_review_status"] = "verified" if verified else "not_verified"
        fact["successful_review_streak"] = (
            int(fact.get("successful_review_streak") or 0) + 1 if verified else 0
        )
    return by_pack


def project_pack_lifecycle(
    *,
    events: list[Any] | None,
    claims: list[dict[str, Any]] | None = None,
    pack_ids: list[str] | None = None,
    verified_concepts: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """派生每 pack 生命周期状态。``claims`` 传 compiled truth 的
    weak_points/claim 列表（含 concept_id/evidence_level/decay_state）——
    只用于 practiced 归位与 dormant 的衰减判定，**绝不**当正向掌握信号。
    ``verified_concepts`` = prescription_outcome verified 的 concept/taxonomy
    codes（显式正向信号）；pack refs ∩ verified_concepts 非空才 mastered。"""
    if pack_ids is None:
        from deeptutor.services.luban_lesson import list_all_pack_ids

        pack_ids = list_all_pack_ids()

    exposed_packs: dict[str, dict[str, int]] = {}
    practiced_packs: dict[str, int] = {}
    unassigned: list[dict[str, Any]] = []
    retest_by_pack = _pack_retest_facts(list(events or []))

    for event in list(events or []):
        payload = getattr(event, "payload_json", None) or {}
        if not isinstance(payload, dict):
            continue
        if is_lesson_view_event(event):
            pack_id = str(payload.get("pack_id") or "").strip()
            if pack_id:
                stage = str(payload.get("watched_stage") or "").strip() or "lesson"
                slot = exposed_packs.setdefault(pack_id, {})
                slot[stage] = slot.get(stage, 0) + 1
            continue
        if not _is_practice_evidence(event):
            continue
        pack_id, join_path = _resolve_pack_for_practice(payload)
        if pack_id:
            practiced_packs[pack_id] = practiced_packs.get(pack_id, 0) + 1
        else:
            unassigned.append(
                {
                    "event_id": str(getattr(event, "event_id", "") or ""),
                    "question_id": str(payload.get("question_id") or ""),
                    "reason": join_path,
                }
            )

    mastery_by_pack = _claim_packs(list(claims or []))

    # 显式正向信号 → pack（refs ∩ verified_concepts，join 走同一份注册表）。
    verified_packs: set[str] = set()
    verified_codes = {str(code or "").strip() for code in (verified_concepts or ()) if str(code or "").strip()}
    if verified_codes:
        (_, any_ref), _ = _taxonomy_to_packs()
        for code in verified_codes:
            verified_packs.update(any_ref.get(code) or ())

    # 病A 契约：编译产物加载失败（容器缺文件/损坏）必须显式降级——
    # 空映射会把所有练-evidence 打进未归位桶，绝不能看起来健康。
    _, question_map_ok = _question_to_packs()
    _, taxonomy_registry_ok = _taxonomy_to_packs()
    degraded = not (question_map_ok and taxonomy_registry_ok)

    packs: dict[str, dict[str, Any]] = {}
    for pack_id in pack_ids:
        mastery = mastery_by_pack.get(pack_id) or {}
        decay_states = mastery.get("decay_states") or set()
        retest = retest_by_pack.get(pack_id) or {}
        has_practice = pack_id in practiced_packs or bool(mastery) or bool(retest)
        has_exposure = pack_id in exposed_packs

        if pack_id in verified_packs:
            # dormant = 真懂过 + 记忆衰减（stale）。improving = 弱点仍在
            # 改善 ≠ 该休眠（病G 裁决：improving 移出 dormant 判定）。
            state = LIFECYCLE_DORMANT if "stale" in decay_states else LIFECYCLE_MASTERED
        elif has_practice:
            state = LIFECYCLE_PRACTICED
        elif has_exposure:
            state = LIFECYCLE_EXPOSED
        else:
            state = LIFECYCLE_UNLEARNED

        packs[pack_id] = {
            "lifecycle_state": state,
            # 蓝环（接触轨）与红黄绿（掌握轨）视觉拆开（§1.3）：
            # 蓝环只表达接触，绝不进红黄绿。
            "blue_ring": "exposed" if has_exposure else "empty",
            "exposure": exposed_packs.get(pack_id, {}),
            "practice_event_count": practiced_packs.get(pack_id, 0),
            "claim_count": int(mastery.get("claim_count", 0)),
            # Review cadence facts are terminal-only and remain pack-level
            # scheduling evidence.  Even a fully-correct pack retest does not
            # coarse-promote the whole pack to mastered or settle sibling errors.
            "last_completion_at": str(retest.get("last_completion_at") or ""),
            "last_review_at": str(retest.get("last_review_at") or ""),
            "last_review_status": str(retest.get("last_review_status") or ""),
            "successful_review_streak": int(retest.get("successful_review_streak") or 0),
            "review_cycle_anchor": str(retest.get("review_cycle_anchor") or ""),
            "terminal_evidence_refs": list(retest.get("terminal_evidence_refs") or []),
        }

    return {
        "authority": "pack_lifecycle_projection.read_model",
        "state_machine": [
            LIFECYCLE_UNLEARNED,
            LIFECYCLE_EXPOSED,
            LIFECYCLE_PRACTICED,
            LIFECYCLE_MASTERED,
            LIFECYCLE_DORMANT,
        ],
        "packs": packs,
        "unassigned_practice": unassigned,
        "degraded": degraded,
    }


__all__ = [
    "LIFECYCLE_DORMANT",
    "LIFECYCLE_EXPOSED",
    "LIFECYCLE_MASTERED",
    "LIFECYCLE_PRACTICED",
    "LIFECYCLE_UNLEARNED",
    "project_pack_lifecycle",
]
