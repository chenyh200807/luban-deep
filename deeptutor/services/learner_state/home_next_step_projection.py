"""home_next_step_projection——跨模式「下一步」呈现仲裁 read-model
（融合计划 §3，contracts/learner-state.md 已 register-before-use 登记）。

**这不是第二练习处方。** 组合规则只存在这一份，确定性优先级：

```
下一步 = 第一个非空项:
  1) 到期复: revalidation_queue 有 due probe   →「回炉：XX 再看一眼就稳了」
  2) 活跃练: training_intent 有 active intent  →「练：你漏的采分点，换个题面」
  3) 下一学: 路线上第一个 未学∧绿灯签发 的站    →「学：下一站 XX」
  4) fallback: registry 静态序第一个绿灯站（群体理由，day-0 不白屏）
```

铁律（§3）：纯函数、零副作用——禁写 ledger、禁生成/修改 training_intent、
禁改 revalidation 状态、禁前端/各 tab 再拼一次。它不产出任何「该练什么」
的内容判断：练的内容仍由 ``training_intent``、复由 ``revalidation_queue``、
学序由 registry+前置边说了算；本模块只做 display arbitration，输出必带
``mode / source_authority / source_ref / reason`` 四字段（可审计）。
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.taxonomy.construction_learning_graph import (
    order_packs_with_prerequisites,
)

MODE_REVIEW = "review_due"
MODE_PRACTICE = "practice_active"
MODE_LEARN = "learn_next"
MODE_FALLBACK = "learn_fallback"


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_home_next_step_projection(
    *,
    revalidation_items: list[dict[str, Any]] | None,
    active_training_intents: list[dict[str, Any]] | None,
    pack_lifecycle: dict[str, Any] | None,
    green_lessons: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """确定性仲裁；所有输入由 caller 提供（本模块不读任何存储）。"""
    for item in list(revalidation_items or []):
        if not isinstance(item, dict):
            continue
        intent = item.get("intent") if isinstance(item.get("intent"), dict) else {}
        label = _text(intent.get("concept_label")) or _text(intent.get("error_label")) or "薄弱点"
        return {
            "mode": MODE_REVIEW,
            "source_authority": "revalidation_queue",
            "source_ref": _text(item.get("probe_id")),
            "reason": f"到期复验：{label} 再看一眼就稳了",
        }

    for intent in list(active_training_intents or []):
        if not isinstance(intent, dict) or not intent:
            continue
        intent_id = _text(intent.get("training_intent_id"))
        if not intent_id:
            continue
        label = _text(intent.get("concept_label")) or _text(intent.get("error_label")) or "你漏的采分点"
        return {
            "mode": MODE_PRACTICE,
            "source_authority": "training_intent",
            "source_ref": intent_id,
            "reason": f"继续练：{label}，换个题面",
        }

    green = [item for item in list(green_lessons or []) if isinstance(item, dict) and _text(item.get("pack_id"))]
    packs = (pack_lifecycle or {}).get("packs") if isinstance(pack_lifecycle, dict) else {}
    packs = packs if isinstance(packs, dict) else {}

    def _state(pack_id: str) -> str:
        entry = packs.get(pack_id) if isinstance(packs.get(pack_id), dict) else {}
        return _text(entry.get("lifecycle_state"))

    titles = {_text(item.get("pack_id")): _text(item.get("title")) for item in green}
    ordered_ids = [_text(item.get("pack_id")) for item in green]  # registry 静态序
    unlearned = {pack_id for pack_id in ordered_ids if _state(pack_id) in ("", "unlearned")}
    # §4-2 前置过滤：未学前置 A 时不把后继 B 排到 A 前（学序=registry+前置边，
    # 规则归 construction_learning_graph 教研 authority；不设前置锁，可跳站不变）。
    ordered_ids = order_packs_with_prerequisites(ordered_ids, unlearned_pack_ids=unlearned)
    for pack_id in ordered_ids:
        if pack_id in unlearned:
            title = titles.get(pack_id) or pack_id
            return {
                "mode": MODE_LEARN,
                "source_authority": "pack_lifecycle_projection",
                "source_ref": pack_id,
                "reason": f"下一站：{title}",
            }

    if green:
        first = green[0]
        title = _text(first.get("title")) or _text(first.get("pack_id"))
        return {
            "mode": MODE_FALLBACK,
            "source_authority": "pack_manifest.registry_order",
            "source_ref": _text(first.get("pack_id")),
            # 群体理由（诚实版）：不伪装个性化。
            "reason": f"从这里开始：{title}（多数考生的第一站）",
        }

    # 供给面完全不可用（无绿灯站）——如实空态，交由上层降级文案。
    return {
        "mode": "unavailable",
        "source_authority": "pack_manifest.registry_order",
        "source_ref": "",
        "reason": "",
    }


__all__ = [
    "MODE_FALLBACK",
    "MODE_LEARN",
    "MODE_PRACTICE",
    "MODE_REVIEW",
    "build_home_next_step_projection",
]
