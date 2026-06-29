"""② content-truth review loop — L2 透传 + L3 离线评审纠错管道.

owner 三层里：runtime 只把核不到的规范编号 flag 进单一事件 sink(TurnEventLog)，**离线**评审
agent 再读队列、用 authority-ladder(教材原文仲裁 + 异源)判 accurate/fabricated/uncertain，
攒成 PII-safe 纠错数据集喂内容升级。本测试钉死确定性骨架(eval-design：确定性断言作主)：

- 透传：``_build_terminal_turn_observation_event`` 必须把 ``content_truth_low_confidence_claims``
  从 trace_metadata 原样带进事件 metadata(否则离线评审读不到 → 链路断)。
- 队列：``build_content_truth_review_queue`` 读 TurnEventLog → 按归一化 claim 去重计数；
  排除 test-only 合成 turn(不污染纠错数据)。
- redact：committed 纠错数据集 PII-safe(只留 claim/计数/信号，丢链接标识与原文上下文)——
  与 failed_turn_promotion 同纪律。
- authority-ladder：教材原文仲裁 > 异源；教材有=accurate；教材搜了没有且异源判死=fabricated；
  教材没有但异源没判死=uncertain(不冤判)；没搜教材=uncertain。
- verdict merge：把评审 verdict 合进纠错数据集，统计 accurate/fabricated/uncertain。
"""

from __future__ import annotations

from deeptutor.services.observability.turn_event_log import TurnEventLog
from deeptutor.services.session.turn_runtime import (
    _build_terminal_turn_observation_event,
)
from deeptutor.services.observability.content_truth_review_queue import (
    apply_review_verdicts,
    build_content_truth_review_queue,
    build_redacted_correction_seed,
    combine_authority_ladder_verdict,
    redacted_correction_seeds,
)

_CLAIMS = [
    {
        "claim": "GB50500-2013",
        "claim_kind": "standard_code",
        "confidence_signal": "rag_miss",
        "context_excerpt": "工期索赔依据 GB 50500-2013 §8.11.8",
    }
]


# ---- L2 透传: emitter carries the low-confidence claims into the event sink ----

def test_terminal_event_passes_through_content_truth_low_confidence_claims():
    event = _build_terminal_turn_observation_event(
        session_id="s-1",
        turn_id="t-1",
        status="completed",
        capability_name="deep_question",
        duration_ms=12.0,
        trace_metadata={
            "context_route": "question_followup",
            "content_truth_guard_applied": True,
            "content_truth_low_confidence_claims": _CLAIMS,
        },
        usage_summary={"total_tokens": 1},
    )
    assert event["metadata"]["content_truth_low_confidence_claims"] == _CLAIMS
    assert event["metadata"]["content_truth_guard_applied"] is True


def test_terminal_event_omits_content_truth_when_absent():
    event = _build_terminal_turn_observation_event(
        session_id="s-1",
        turn_id="t-1",
        status="completed",
        capability_name="chat",
        duration_ms=12.0,
        trace_metadata={"context_route": "chat"},
        usage_summary={"total_tokens": 1},
    )
    assert "content_truth_low_confidence_claims" not in event["metadata"]


# ---- L3 队列: read TurnEventLog, dedupe by normalized claim, count ----

def _append_turn(log: TurnEventLog, *, claims, session="s", turn="t", synthetic=False):
    metadata = {"content_truth_low_confidence_claims": claims}
    if synthetic:
        metadata["smoke_test"] = True
    log.append(
        {
            "type": "turn_observation",
            "status": "completed",
            "session_id": session,
            "turn_id": turn,
            "capability": "deep_question",
            "metadata": metadata,
        }
    )


def test_queue_dedupes_and_counts_claims(tmp_path):
    log = TurnEventLog(events_dir=tmp_path)
    _append_turn(log, claims=_CLAIMS, turn="t1")
    _append_turn(
        log,
        claims=[{"claim": "GB 50500-2013", "confidence_signal": "rag_miss"}],
        turn="t2",
    )  # same claim, different spacing → dedupe after normalization
    _append_turn(
        log,
        claims=[{"claim": "JGJ999-2099", "confidence_signal": "rag_degraded"}],
        turn="t3",
    )
    queue = build_content_truth_review_queue(event_log=log, days=1)
    by_claim = {item["claim"]: item for item in queue["items"]}
    assert by_claim["GB50500-2013"]["occurrences"] == 2
    assert by_claim["JGJ999-2099"]["occurrences"] == 1
    assert by_claim["GB50500-2013"]["confidence_signals"]["rag_miss"] == 2
    # most-frequent first
    assert queue["items"][0]["claim"] == "GB50500-2013"
    assert queue["queue_size"] == 2


def test_queue_excludes_test_only_turns(tmp_path):
    log = TurnEventLog(events_dir=tmp_path)
    _append_turn(log, claims=_CLAIMS, turn="real")
    _append_turn(log, claims=[{"claim": "TB10001-2099"}], turn="synthetic", synthetic=True)
    queue = build_content_truth_review_queue(event_log=log, days=1)
    claims = {item["claim"] for item in queue["items"]}
    assert "GB50500-2013" in claims
    assert "TB10001-2099" not in claims  # synthetic turn must not pollute corrections


# ---- L3 redact: committed correction dataset is PII-safe ----

def test_redacted_seed_drops_linkable_ids_and_raw_context():
    item = {
        "claim": "GB50500-2013",
        "claim_kind": "standard_code",
        "occurrences": 3,
        "confidence_signals": {"rag_miss": 3},
        "sample_context": "工期索赔依据 GB 50500-2013 ...",
    }
    seed = build_redacted_correction_seed(item)
    assert seed["claim"] == "GB50500-2013"
    assert seed["occurrences"] == 3
    assert seed["redacted"] is True
    # raw bot/user context and any linkable id must NOT survive into committed data
    assert "sample_context" not in seed
    assert all(k not in seed for k in ("session_id", "turn_id", "trace_id"))


def test_redacted_correction_seeds_maps_whole_queue():
    queue = {"items": [{"claim": "X", "occurrences": 1, "confidence_signals": {}}]}
    seeds = redacted_correction_seeds(queue)
    assert len(seeds) == 1 and seeds[0]["redacted"] is True


# ---- L3 authority-ladder: textbook arbitrates above cross-model ----

def test_authority_ladder_textbook_present_is_accurate():
    assert combine_authority_ladder_verdict(
        textbook_present=True, textbook_searched=True, cross_model_verdict="fabricated"
    ) == "accurate"  # textbook 原文压过异源


def test_authority_ladder_textbook_absent_and_cross_model_fabricated():
    assert combine_authority_ladder_verdict(
        textbook_present=False, textbook_searched=True, cross_model_verdict="fabricated"
    ) == "fabricated"


def test_authority_ladder_textbook_absent_but_cross_model_not_dead_is_uncertain():
    assert combine_authority_ladder_verdict(
        textbook_present=False, textbook_searched=True, cross_model_verdict="accurate"
    ) == "uncertain"  # 教材没收录≠编造，不冤判


def test_authority_ladder_no_textbook_search_is_uncertain():
    assert combine_authority_ladder_verdict(
        textbook_present=False, textbook_searched=False, cross_model_verdict=None
    ) == "uncertain"


# ---- L3 verdict merge: produce the correction dataset ----

def test_apply_review_verdicts_builds_correction_dataset():
    queue = {
        "items": [
            {"claim": "GB50500-2013", "occurrences": 2, "confidence_signals": {"rag_miss": 2}},
            {"claim": "JGJ999-2099", "occurrences": 1, "confidence_signals": {"rag_miss": 1}},
        ]
    }
    verdicts = {
        "GB50500-2013": {"verdict": "accurate", "authority": "textbook", "citation": "讲义p12"},
        "JGJ999-2099": {"verdict": "fabricated", "authority": "textbook+deepseek", "citation": ""},
    }
    dataset = apply_review_verdicts(queue, verdicts)
    assert dataset["dataset_size"] == 2
    assert dataset["verdict_counts"]["accurate"] == 1
    assert dataset["verdict_counts"]["fabricated"] == 1
    rows = {r["claim"]: r for r in dataset["rows"]}
    assert rows["GB50500-2013"]["verdict"] == "accurate"
    assert rows["GB50500-2013"]["citation"] == "讲义p12"
    assert rows["GB50500-2013"]["redacted"] is True  # rows are PII-safe
    # unjudged claims default to uncertain, never silently dropped
    assert apply_review_verdicts(queue, {})["verdict_counts"]["uncertain"] == 2
