"""② content-truth review loop — L3 离线评审纠错管道(owner 三层的最后一层).

runtime(L1/L2)只**永远输出 + 大方 hedge + flag**：bot 写出但本轮 standard 召回核不到的规范
编号，被静默记进单一事件 sink ``TurnEventLog``(键 ``content_truth_low_confidence_claims``)。

本模块是**离线**消费者(不在请求路径、不裁决学员当下体验)，镜像 ``failed_turn_promotion``：

  read TurnEventLog → 按归一化 claim 去重计数(排除合成 turn) → authority-ladder 仲裁
  (教材原文 > 异源) → PII-safe 纠错数据集，喂内容升级(产品飞轮燃料)。

owner 原则：准确性靠"后台审 + 持续纠"收敛，不在输出端抑制。评审 agent 离线，**不是** runtime
门，不新增 runtime decider，不破单一权威(真值仍是教材原文，异源只是信号)。
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from deeptutor.services.observability.turn_event_log import (
    TurnEventLog,
    event_is_test_only,
    get_turn_event_log,
)
from deeptutor.tutorbot.teaching_modes import _normalize_standard_code


def _iter_low_confidence_claims(event: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    claims = metadata.get("content_truth_low_confidence_claims")
    return [c for c in claims if isinstance(c, dict)] if isinstance(claims, list) else []


def build_content_truth_review_queue(
    *,
    event_log: TurnEventLog | None = None,
    days: int = 7,
    limit: int = 500,
) -> dict[str, Any]:
    """从 TurnEventLog 聚合低置信规范编号 → 去重计数的离线评审队列。

    - 按**归一化** claim 去重(``GB 50500-2013`` 与 ``GB50500-2013`` 合并)。
    - 排除 test-only / 合成 turn(``event_is_test_only``)，纠错数据只来自真实生产 turn。
    - 按出现次数降序(优先评审高频编造)，截断到 ``limit``。
    单一真值源(已接检索的召回证据上游决定何为"核不到")，本模块只聚合，不重判。"""

    turn_log = event_log or get_turn_event_log()
    events = turn_log.load_events_range(days=max(int(days or 1), 1))
    by_claim: dict[str, dict[str, Any]] = {}
    for event in events:
        if event_is_test_only(event):
            continue
        for record in _iter_low_confidence_claims(event):
            claim = _normalize_standard_code(str(record.get("claim") or ""))
            if not claim:
                continue
            agg = by_claim.setdefault(
                claim,
                {
                    "claim": claim,
                    "claim_kind": str(record.get("claim_kind") or "standard_code"),
                    "occurrences": 0,
                    "confidence_signals": {},
                    "sample_context": "",
                },
            )
            agg["occurrences"] += 1
            signal = str(record.get("confidence_signal") or "rag_miss")
            agg["confidence_signals"][signal] = agg["confidence_signals"].get(signal, 0) + 1
            if not agg["sample_context"]:
                agg["sample_context"] = str(record.get("context_excerpt") or "")
    items = sorted(by_claim.values(), key=lambda x: (-x["occurrences"], x["claim"]))
    items = items[: max(int(limit or 500), 1)]
    return {
        "run_manifest": {
            "run_id": f"content-truth-review-queue-{int(time.time())}",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "turn_event_log",
            "window_days": max(int(days or 1), 1),
            "candidate_limit": max(int(limit or 500), 1),
        },
        "queue_size": len(items),
        "items": items,
    }


def build_redacted_correction_seed(item: dict[str, Any]) -> dict[str, Any]:
    """把队列项降成 PII-safe 纠错数据种子：只留结构信号，**丢**原文上下文与任何链接标识。

    与 ``failed_turn_promotion.build_redacted_harness_case_candidate`` 同纪律——生产 turn 携带
    真实用户内容，绝不进 committed 纠错语料；纠错靠 claim(规范编号，非 PII)+ 评审 citation。"""

    return {
        "claim": str(item.get("claim") or ""),
        "claim_kind": str(item.get("claim_kind") or "standard_code"),
        "occurrences": int(item.get("occurrences") or 0),
        "confidence_signals": dict(item.get("confidence_signals") or {}),
        "redacted": True,
    }


def redacted_correction_seeds(queue: dict[str, Any]) -> list[dict[str, Any]]:
    return [build_redacted_correction_seed(i) for i in queue.get("items") or [] if isinstance(i, dict)]


def combine_authority_ladder_verdict(
    *,
    textbook_present: bool,
    textbook_searched: bool,
    cross_model_verdict: str | None,
) -> str:
    """authority-ladder 仲裁(教材原文 > 异源)：把两路信号合成单一 verdict。

    - 教材原文有该规范/条文 → ``accurate``(最高权威，压过异源；异源误判不冤判 bot)。
    - 教材搜过但没有，且异源判 ``fabricated`` → ``fabricated``(两路一致判死)。
    - 教材没有但异源没判死(accurate/uncertain/缺) → ``uncertain``(教材未收录≠编造，存疑待人工)。
    - 没搜教材 → ``uncertain``(证据不足，永不硬判)。
    见 memory ``authority-ladder-textbook-adjudicates-llm-panels``。"""

    if textbook_present:
        return "accurate"
    if textbook_searched and str(cross_model_verdict or "").strip().lower() == "fabricated":
        return "fabricated"
    return "uncertain"


def apply_review_verdicts(
    queue: dict[str, Any],
    verdicts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """把离线评审产出的 verdict 合进 PII-safe 纠错数据集。

    ``verdicts`` 按归一化 claim 索引，每条 = {verdict, authority, citation}。未被评审到的 claim
    默认 ``uncertain``(永不静默丢弃)。返回 {dataset_size, verdict_counts, rows[]}。"""

    rows: list[dict[str, Any]] = []
    for item in queue.get("items") or []:
        if not isinstance(item, dict):
            continue
        seed = build_redacted_correction_seed(item)
        verdict_meta = verdicts.get(seed["claim"]) or {}
        seed["verdict"] = str(verdict_meta.get("verdict") or "uncertain")
        seed["authority"] = str(verdict_meta.get("authority") or "")
        seed["citation"] = str(verdict_meta.get("citation") or "")
        rows.append(seed)
    counts = Counter(row["verdict"] for row in rows)
    return {
        "dataset_size": len(rows),
        "verdict_counts": dict(counts),
        "rows": rows,
    }
