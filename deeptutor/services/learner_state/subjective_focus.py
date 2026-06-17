"""关注线 read-side 投影：学员主观关注 → concept 权重。

刻意 **不进** ``synthesize_learning_truth``（保住"编译严"/证据纯净）。只在
排序 / 首页 read 层被消费（merge 进 ``training_intent._intent_priority`` 的
``subjective_focus_weight``），且 **绝不** 产出掌握 / 弱点 claim。

权重 = 关注事件按 14 天指数衰减累加（÷3 归一、上限 1.0），再乘掌握阻尼
``(1 - mastery)``——越掌握的点，关注的边际权重越低。

事件提取对 dict 与真实 ``LearnerStateEvent``(payload_json) 均鲁棒：判据是
payload 里 ``learning_signal_type == "subjective_focus"``，concept 取
``concept_id``。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

_TZ = timezone(timedelta(hours=8))


def _parse(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=_TZ)).astimezone(_TZ)


def _field(ev: Any, name: str, default: Any = None) -> Any:
    if isinstance(ev, dict):
        return ev.get(name, default)
    return getattr(ev, name, default)


def _payload(ev: Any) -> dict[str, Any]:
    payload = _field(ev, "payload_json", None)
    if payload is None:
        payload = _field(ev, "payload", None)
    if isinstance(payload, dict):
        return payload
    return ev if isinstance(ev, dict) else {}


def subjective_focus_projection(
    events: Iterable[Any],
    *,
    now_iso: str = "",
    mastery_by_concept: dict[str, float] | None = None,
    half_life_days: float = 14.0,
) -> dict[str, float]:
    now = _parse(now_iso) or datetime.now(_TZ)
    mastery = mastery_by_concept or {}
    raw: dict[str, float] = {}
    for ev in events:
        payload = _payload(ev)
        if str(payload.get("learning_signal_type") or "").strip() != "subjective_focus":
            continue
        cid = str(payload.get("concept_id") or "").strip()
        if not cid:
            continue
        observed = _parse(str(_field(ev, "created_at", "") or payload.get("created_at") or ""))
        age_days = max((now - observed).total_seconds() / 86400, 0.0) if observed else 0.0
        decay = 0.5 ** (age_days / max(half_life_days, 0.1))
        raw[cid] = raw.get(cid, 0.0) + decay
    out: dict[str, float] = {}
    for cid, score in raw.items():
        weight = min(score / 3.0, 1.0)
        weight *= max(0.0, 1.0 - float(mastery.get(cid, 0.0) or 0.0))  # 掌握阻尼
        out[cid] = round(weight, 3)
    return out


__all__ = ["subjective_focus_projection"]
