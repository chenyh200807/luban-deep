"""photo_answer store + cost ledger 行为测试。

计划锚点：docs/plan/2026-06-10-luban-photo-answer-ocr-input-layer-implementation-plan.md
§3.3 cost_ledger 规格（micros / reserve→settle/refund / 软硬双顶 / user-day 限额）
§6 数据模型（durable job / 幂等键 / lease / 审计字段）
"""

from __future__ import annotations

import pytest

from deeptutor.services.photo_answer.cost_ledger import (
    BudgetExceeded,
    CostLedger,
    EscalationLimitReached,
)
from deeptutor.services.photo_answer.models import (
    HARD_CAP_MICROS,
    SOFT_CAP_MICROS,
    InvalidTransition,
    DailyQuotaExceeded,
)
from deeptutor.services.photo_answer.store import PhotoAnswerStore


@pytest.fixture()
def store(tmp_path):
    return PhotoAnswerStore(tmp_path / "photo_answer.db")


@pytest.fixture()
def ledger(store):
    return CostLedger(store)


def _session(store, user_id="u1", question_id="Q2023-01"):
    return store.create_session(user_id=user_id, question_id=question_id, question_stem="背景：某工程…")


# ---------- sessions ----------


def test_create_session_defaults(store):
    s = _session(store)
    assert s["status"] == "created"
    assert s["cost_budget_soft_micros"] == SOFT_CAP_MICROS == 100_000
    assert s["cost_budget_hard_micros"] == HARD_CAP_MICROS == 300_000
    assert s["question_id"] == "Q2023-01"
    assert store.get_session(s["id"])["user_id"] == "u1"


def test_daily_session_quota_enforced(store):
    for _ in range(3):
        store.create_session(user_id="u9", question_id="Q1", daily_session_limit=3)
    with pytest.raises(DailyQuotaExceeded):
        store.create_session(user_id="u9", question_id="Q1", daily_session_limit=3)
    # 不影响其他用户
    store.create_session(user_id="u10", question_id="Q1", daily_session_limit=3)


def test_status_transition_guard(store):
    s = _session(store)
    store.set_session_status(s["id"], "pages_uploaded")
    store.set_session_status(s["id"], "processing")
    with pytest.raises(InvalidTransition):
        store.set_session_status(s["id"], "submitted")  # processing 不能直接 submitted
    store.set_session_status(s["id"], "awaiting_confirm")
    store.set_session_status(s["id"], "confirmed")
    store.set_session_status(s["id"], "submitted")


# ---------- pages ----------


def test_add_page_and_duplicate_detection(store):
    s = _session(store)
    p1 = store.add_page(s["id"], page_index=0, image_ref="/a/0.jpg", content_hash="h1")
    assert p1["is_duplicate"] is False
    p2 = store.add_page(s["id"], page_index=1, image_ref="/a/1.jpg", content_hash="h1")
    assert p2["is_duplicate"] is True  # 同 session 同 hash → 重复页标记
    assert len(store.list_pages(s["id"])) == 2


# ---------- durable jobs ----------


def test_job_idempotency_key_returns_same_job(store):
    s = _session(store)
    j1 = store.create_job(s["id"], idempotency_key="k1")
    j2 = store.create_job(s["id"], idempotency_key="k1")
    assert j1["id"] == j2["id"]
    assert j1["job_version"] == 1
    j3 = store.create_job(s["id"], idempotency_key="k2")
    assert j3["id"] != j1["id"]
    assert j3["job_version"] == 2


def test_job_lease_and_recovery(store):
    s = _session(store)
    j = store.create_job(s["id"], idempotency_key="k1")
    assert store.lease_job(j["id"], lease_seconds=60, now=1000.0) is True
    # 未过期不可重租（防双跑）
    assert store.lease_job(j["id"], lease_seconds=60, now=1030.0) is False
    # 过期可恢复（进程重启场景），attempt_count 递增
    assert store.lease_job(j["id"], lease_seconds=60, now=1100.0) is True
    assert store.get_job(j["id"])["attempt_count"] == 2
    store.finish_job(j["id"], "succeeded")
    assert store.lease_job(j["id"], lease_seconds=60, now=2000.0) is False


def test_ocr_result_idempotent_per_page_engine(store):
    s = _session(store)
    j = store.create_job(s["id"], idempotency_key="k1")
    store.save_ocr_result(j["id"], page_index=0, engine="baidu_handwriting", raw_text="甲", cost_micros=10_000)
    store.save_ocr_result(j["id"], page_index=0, engine="baidu_handwriting", raw_text="乙", cost_micros=10_000)
    rows = store.list_ocr_results(j["id"])
    assert len(rows) == 1  # 恢复重跑不产生第二行（不双扣的前提）
    assert rows[0]["raw_text"] == "甲"  # 首次结果是权威
    assert store.has_ocr_result(j["id"], page_index=0, engine="baidu_handwriting") is True


# ---------- cost ledger ----------


def test_reserve_within_soft_cap_then_settle_frees_budget(store, ledger):
    s = _session(store)
    r = ledger.reserve(s["id"], amount_micros=90_000, channel="auto")
    ledger.settle(r, actual_micros=10_000, provider_usage_id="bill-1")
    # settle 后实际只占 10_000，余额应允许再预留 80_000
    ledger.reserve(s["id"], amount_micros=80_000, channel="auto")
    assert ledger.spent_micros(s["id"]) == 10_000
    assert ledger.reserved_micros(s["id"]) == 80_000


def test_auto_channel_rejects_over_soft_cap(store, ledger):
    s = _session(store)
    ledger.reserve(s["id"], amount_micros=90_000, channel="auto")
    with pytest.raises(BudgetExceeded):
        ledger.reserve(s["id"], amount_micros=20_000, channel="auto")


def test_refund_frees_reservation(store, ledger):
    s = _session(store)
    r = ledger.reserve(s["id"], amount_micros=90_000, channel="auto")
    ledger.refund(r)
    ledger.reserve(s["id"], amount_micros=90_000, channel="auto")  # 不应抛
    assert ledger.spent_micros(s["id"]) == 0


def test_user_escalation_breaks_soft_cap_within_hard_cap_once(store, ledger):
    s = _session(store)
    r0 = ledger.reserve(s["id"], amount_micros=30_000, channel="auto")
    ledger.settle(r0, actual_micros=30_000)
    # 主动重识别：超软顶但在硬顶内 → 允许
    r1 = ledger.reserve(s["id"], amount_micros=225_000, channel="user_escalation")
    ledger.settle(r1, actual_micros=225_000)
    assert ledger.spent_micros(s["id"]) == 255_000
    # 每 session 只允许 1 次
    with pytest.raises(EscalationLimitReached):
        ledger.reserve(s["id"], amount_micros=10_000, channel="user_escalation")


def test_user_escalation_rejects_over_hard_cap(store, ledger):
    s = _session(store)
    r0 = ledger.reserve(s["id"], amount_micros=90_000, channel="auto")
    ledger.settle(r0, actual_micros=90_000)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(s["id"], amount_micros=225_000, channel="user_escalation")  # 90k+225k > 300k


def test_settle_records_provider_usage_for_reconciliation(store, ledger):
    s = _session(store)
    r = ledger.reserve(s["id"], amount_micros=10_000, channel="auto")
    ledger.settle(r, actual_micros=8_000, provider_usage_id="aliyun-req-123")
    entries = ledger.list_entries(s["id"])
    assert entries[0]["provider_usage_id"] == "aliyun-req-123"
    assert entries[0]["state"] == "settled"
    assert entries[0]["actual_micros"] == 8_000
