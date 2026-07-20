"""home_next_step_projection——跨模式「下一步」呈现仲裁 read-model
（融合计划 §3，contracts/learner-state.md 已 register-before-use 登记）。

**这不是第二练习处方。** 组合规则只存在这一份，确定性优先级：

```
下一步 = 第一个非空项:
  1) 到期复: pack 级到期投影（luban_lesson/review_due.build_review_due_projection，
     调度真值仍归 revalidation_queue）有**可兑付** due 条目
     →「回炉：XX 再看一眼就稳了」
  2) 活跃练: training_intent 有 active intent
     且 target pack 可路由（绿灯 ∧ retest_available 供给真值）
     →「练：你漏的采分点，换个题面」
  3) 下一学: 路线上第一个 未学∧绿灯 的站，**优先 retest_available 供给真值**
     的站（保证「视频→练习」全程可走完）→「学：下一站 XX」
  4) fallback: registry 静态序第一个绿灯站，**同样优先 retest_available** 的站
     （群体理由，day-0 不白屏）
```

不可执行的 intent 不得在权威内遮蔽可执行臂（2026-07-16 QA 死证：F16/X03
停发后空 target 的 practice_active 胜出 → 前端对空 pack fail-closed →
任务卡永久隐藏）。解析不出可路由 target 的 practice intent 跳过、落到
下一优先级臂；被跳过的 intent 不静默丢——保留在 ``skipped_intents``
diagnostic 里（仅诊断，非第二处方）。供给真值 = caller 传入的
``green_lessons`` read-model 行（``retest_available``），本模块不造第二真值。

**到期复候选源单一化（2026-07-20 双权威病收权）**：``review_due_items`` 必须是
复习页同一投影（``build_review_due_projection``）经 ``list_redeemable_due_items``
（= ``resolve_due_review_probe`` exact-match 口径）过滤后的条目——首页发出的
``source_ref``（probe_id）必然能被复习入口原样兑付。弱点节点 queue
（``build_revalidation_queue_projection(learning_state=…)``）不再是本臂的
decider（QA 6a127781 死证：只有 fresh 到期、无弱点节点的用户复习页有货、
首页却出 learn_next；且弱点 probe 与 pack 级 probe 铸造不同源，前端
exact-match 永远兑付不了）。caller 侧投影不可用时传
``review_due_unavailable=True``：臂空、落 ``skipped_intents`` 诊断，
不遮蔽 learn_next（fail-closed 不 fail-open）。

**推荐起点一致性（2026-07-18，A01 冲突包 owner 阻塞事件治本）**：下一学/
fallback 两臂「推荐一个起点」时，必须偏好 ``retest_available``（= compiled
practice ``supply_ready`` 单一真值，与活跃练臂同源）的站——否则会像 A01 那样
「绿灯可看视频、练习却未签发」被荐为起点，用户看完视频走不进练习（断链）。
偏好规则复用同一供给真值，不设第二处方：未学站里优先第一个 supply_ready 的，
无一 supply_ready 时**仍回退到路线第一个未学站**（视频本身有价值，好过白屏），
被供给原因跳过的站保留在 ``skipped_stations`` diagnostic（仅诊断，非路由处方）。

铁律（§3）：纯函数、零副作用——禁写 ledger、禁生成/修改 training_intent、
禁改 revalidation 状态、禁前端/各 tab 再拼一次。它不产出任何「该练什么」
的内容判断：练的内容仍由 ``training_intent``、复由 ``revalidation_queue``、
学序由 registry+前置边说了算；本模块只做 display arbitration，输出必带
``mode / source_authority / source_ref / reason`` 四字段（可审计）。
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.learner_state.pack_lifecycle_projection import (
    LIFECYCLE_UNLEARNED,
)
from deeptutor.services.taxonomy.construction_learning_graph import (
    order_packs_with_prerequisites,
)

MODE_REVIEW = "review_due"
MODE_PRACTICE = "practice_active"
MODE_LEARN = "learn_next"
MODE_FALLBACK = "learn_fallback"
# 内部空态哨兵(病D-1:每个词汇一个 authority)。契约:unavailable 永不
# 外泄到 dashboard payload——上层见此 mode 一律不挂 next_step 字段。
MODE_UNAVAILABLE = "unavailable"


def unavailable_next_step(*, source_authority: str = "") -> dict[str, Any]:
    """空态工厂——「下一步不可用」四字段形状的唯一出处(禁手搓镜像 dict)。"""
    return {
        "mode": MODE_UNAVAILABLE,
        "source_authority": source_authority,
        "source_ref": "",
        "reason": "",
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_home_next_step_projection(
    *,
    review_due_items: list[dict[str, Any]] | None,
    active_training_intents: list[dict[str, Any]] | None,
    pack_lifecycle: dict[str, Any] | None,
    green_lessons: list[dict[str, Any]] | None,
    review_due_unavailable: bool = False,
) -> dict[str, Any]:
    """确定性仲裁；所有输入由 caller 提供（本模块不读任何存储）。"""
    green = [item for item in list(green_lessons or []) if isinstance(item, dict) and _text(item.get("pack_id"))]
    green_ids = {_text(item.get("pack_id")).upper() for item in green}
    green_by_id = {_text(item.get("pack_id")).upper(): item for item in green}

    # 被跳过的不可执行 practice intent（诊断保留，不静默丢）。
    skipped_intents: list[dict[str, Any]] = []
    # 被「供给未就绪」原因让位的推荐起点站（诊断保留，非第二处方）。
    skipped_stations: list[dict[str, Any]] = []

    def _supply_ready(pack_id: str) -> bool:
        """站的练习是否已签发可走完全程 = green read-model 的 retest_available
        （compiled practice supply_ready 单一真值，与活跃练臂同源，不造第二真值）。"""
        row = green_by_id.get(_text(pack_id).upper())
        return bool(row and row.get("retest_available"))

    def _with_diagnostics(step: dict[str, Any]) -> dict[str, Any]:
        if skipped_intents:
            step["skipped_intents"] = list(skipped_intents)
        if skipped_stations:
            step["skipped_stations"] = list(skipped_stations)
        return step

    # 投影不可用 ≠ 无到期（fail-closed 不 fail-open）：臂空落下一臂，且不静默
    # 丢——保留诊断（仅诊断，非第二处方）。
    if review_due_unavailable:
        skipped_intents.append(
            {
                "training_intent_id": "",
                "target_pack_id": "",
                "skip_reason": "review_projection_unavailable",
            }
        )
    else:
        for item in list(review_due_items or []):
            if not isinstance(item, dict):
                continue
            # 条目形状 = review_due 投影 due 行（pack_id/title/probe_id），caller
            # 已按 resolve_due_review_probe 口径过滤为可兑付；这里只做形状防御。
            pack_id = _text(item.get("pack_id")).upper()
            probe_id = _text(item.get("probe_id"))
            if not pack_id or not probe_id:
                continue
            label = _text(item.get("title")) or "薄弱点"
            return _with_diagnostics(
                {
                    "mode": MODE_REVIEW,
                    "source_authority": "revalidation_queue",
                    "source_ref": probe_id,
                    "target_pack_id": pack_id,
                    "reason": f"到期复验：{label} 再看一眼就稳了",
                }
            )

    for intent in list(active_training_intents or []):
        if not isinstance(intent, dict) or not intent:
            continue
        intent_id = _text(intent.get("training_intent_id"))
        if not intent_id:
            continue
        label = _text(intent.get("concept_label")) or _text(intent.get("error_label")) or "你漏的采分点"
        target_pack_id = _text(intent.get("target_pack_id")).upper()
        # 可路由 = 绿灯 ∧ 练供给真值（read model 的 retest_available，fail-closed:
        # 缺字段与停发同形）。解析不出可路由 target 的 intent 不得胜出——
        # 否则前端对空/死 pack fail-closed，可执行的 learn_next 被遮蔽。
        supply_row = green_by_id.get(target_pack_id) if target_pack_id else None
        if supply_row is None or not supply_row.get("retest_available"):
            if not target_pack_id:
                skip_reason = "intent_without_pack_binding"
            elif target_pack_id not in green_ids:
                skip_reason = "pack_not_green"
            else:
                skip_reason = "retest_supply_unavailable"
            skipped_intents.append(
                {
                    "training_intent_id": intent_id,
                    "target_pack_id": target_pack_id,
                    "skip_reason": skip_reason,
                }
            )
            continue
        return _with_diagnostics(
            {
                "mode": MODE_PRACTICE,
                "source_authority": "training_intent",
                "source_ref": intent_id,
                "target_pack_id": target_pack_id,
                "reason": f"继续练：{label}，换个题面",
            }
        )

    packs = (pack_lifecycle or {}).get("packs") if isinstance(pack_lifecycle, dict) else {}
    packs = packs if isinstance(packs, dict) else {}

    def _state(pack_id: str) -> str:
        entry = packs.get(pack_id) if isinstance(packs.get(pack_id), dict) else {}
        return _text(entry.get("lifecycle_state"))

    titles = {_text(item.get("pack_id")): _text(item.get("title")) for item in green}
    ordered_ids = [_text(item.get("pack_id")) for item in green]  # registry 静态序
    unlearned = {pack_id for pack_id in ordered_ids if _state(pack_id) in ("", LIFECYCLE_UNLEARNED)}
    # §4-2 前置过滤：未学前置 A 时不把后继 B 排到 A 前（学序=registry+前置边，
    # 规则归 construction_learning_graph 教研 authority；不设前置锁，可跳站不变）。
    ordered_ids = order_packs_with_prerequisites(ordered_ids, unlearned_pack_ids=unlearned)
    unlearned_ordered = [pack_id for pack_id in ordered_ids if pack_id in unlearned]
    # 推荐起点一致性：未学站里优先「练习已签发（supply_ready）」的站，保证荐出
    # 的起点能走完「视频→练习」全程（A01 型冲突包=绿灯可看视频、练习未签发 →
    # 若荐为起点会断链）。无一 supply_ready 时回退路线第一个未学站（视频仍有价值，
    # 好过白屏）。被供给让位的站入 skipped_stations 诊断（非第二处方）。
    learn_pick = next(
        (pack_id for pack_id in unlearned_ordered if _supply_ready(pack_id)),
        unlearned_ordered[0] if unlearned_ordered else None,
    )
    if learn_pick is not None:
        for pack_id in unlearned_ordered:
            if pack_id == learn_pick:
                break
            if not _supply_ready(pack_id):
                skipped_stations.append(
                    {"pack_id": pack_id, "skip_reason": "practice_supply_unavailable"}
                )
        title = titles.get(learn_pick) or learn_pick
        return _with_diagnostics(
            {
                "mode": MODE_LEARN,
                "source_authority": "pack_lifecycle_projection",
                "source_ref": learn_pick,
                "target_pack_id": learn_pick,
                "reason": f"下一站：{title}",
            }
        )

    if green:
        # fallback 同样优先 supply_ready 的绿灯站，保证冷启动/全学完后荐出的
        # 起点也能走完全程；无一 supply_ready 时回退 registry 第一个绿灯站。
        first = next(
            (item for item in green if _supply_ready(_text(item.get("pack_id")))),
            green[0],
        )
        for item in green:
            if item is first:
                break
            if not _supply_ready(_text(item.get("pack_id"))):
                skipped_stations.append(
                    {
                        "pack_id": _text(item.get("pack_id")),
                        "skip_reason": "practice_supply_unavailable",
                    }
                )
        title = _text(first.get("title")) or _text(first.get("pack_id"))
        return _with_diagnostics(
            {
                "mode": MODE_FALLBACK,
                "source_authority": "pack_manifest.registry_order",
                "source_ref": _text(first.get("pack_id")),
                "target_pack_id": _text(first.get("pack_id")),
                # 群体理由（诚实版）：不伪装个性化。
                "reason": f"从这里开始：{title}（多数考生的第一站）",
            }
        )

    # 供给面完全不可用（无绿灯站）——如实空态，交由上层降级文案。
    return _with_diagnostics(
        unavailable_next_step(source_authority="pack_manifest.registry_order")
    )


__all__ = [
    "MODE_FALLBACK",
    "MODE_LEARN",
    "MODE_PRACTICE",
    "MODE_REVIEW",
    "MODE_UNAVAILABLE",
    "build_home_next_step_projection",
    "unavailable_next_step",
]
