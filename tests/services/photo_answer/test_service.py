"""编排层行为测试：处理管线 / 恢复不双扣 / 预算降级 / 确认分级拦截 / 主动升级。"""

from __future__ import annotations

import pytest

from deeptutor.services.photo_answer.cost_ledger import CostLedger, EscalationLimitReached
from deeptutor.services.photo_answer.engines.base import EngineError, EngineResult
from deeptutor.services.photo_answer.service import PhotoAnswerService
from deeptutor.services.photo_answer.store import PhotoAnswerStore


class FakeEngine:
    def __init__(self, name: str, text: str = "施工组织设计\n1）编制依据", *, cost: int = 10_000, fail: bool = False, chars=None):
        self.name = name
        self.text = text
        self.cost = cost
        self.fail = fail
        self.chars = chars or []
        self.calls = 0

    def recognize(self, image_bytes: bytes) -> EngineResult:
        self.calls += 1
        if self.fail:
            raise EngineError(f"{self.name} provider down")
        lines = [
            {"line_index": i, "text": t, "box": [10, 20 + 40 * i, 300, 30]}
            for i, t in enumerate(self.text.splitlines())
        ]
        return EngineResult(
            engine=self.name,
            raw_text=self.text,
            line_boxes=lines,
            char_confidences=list(self.chars),
            provider_usage_id=f"{self.name}-usage-{self.calls}",
            cost_micros=self.cost,
        )


@pytest.fixture()
def store(tmp_path):
    return PhotoAnswerStore(tmp_path / "pa.db")


def _make_service(store, *, l0=None, l1=None, l2=None):
    images = {}
    svc = PhotoAnswerService(
        store=store,
        ledger=CostLedger(store),
        l0_factory=lambda: l0,
        l1_factory=(lambda: l1) if l1 is not None else None,
        l2_factory=(lambda: l2) if l2 is not None else None,
        image_loader=lambda ref: images[ref],
    )
    return svc, images


def _prep_session(store, images, *, pages=2, stem=""):
    s = store.create_session(user_id="u1", question_id="Q1", question_stem=stem)
    for i in range(pages):
        ref = f"img-{i}"
        images[ref] = b"\xff\xd8\xff\xe0 fake page " + str(i).encode()
        store.add_page(s["id"], page_index=i, image_ref=ref, content_hash=f"h{i}")
    store.set_session_status(s["id"], "pages_uploaded")
    return s


def test_process_job_happy_path_runs_l0_l1_and_persists(store):
    l0 = FakeEngine("baidu_handwriting")
    l1 = FakeEngine("qwen_vl_ocr", cost=1_600)
    svc, images = _make_service(store, l0=l0, l1=l1)
    s = _prep_session(store, images, pages=2)

    job = svc.submit(s["id"])
    svc.process_job(job["id"])

    assert l0.calls == 2 and l1.calls == 2
    assert store.get_session(s["id"])["status"] == "awaiting_confirm"
    assert store.get_job(job["id"])["status"] == "succeeded"
    results = store.list_ocr_results(job["id"])
    assert len(results) == 4  # 2 页 × 2 引擎
    ledger = CostLedger(store)
    assert ledger.spent_micros(s["id"]) == 2 * 10_000 + 2 * 1_600
    assert ledger.reserved_micros(s["id"]) == 0  # 无悬挂预留


def test_crash_recovery_skips_done_pages_and_never_double_charges(store):
    l0 = FakeEngine("baidu_handwriting")
    l1 = FakeEngine("qwen_vl_ocr", cost=1_600)
    svc, images = _make_service(store, l0=l0, l1=l1)
    s = _prep_session(store, images, pages=2)
    job = svc.submit(s["id"])
    svc.process_job(job["id"])
    spent_first = CostLedger(store).spent_micros(s["id"])

    # 模拟崩溃后重放：job 已 succeeded → 直接 no-op；强行重置为 pending 再跑也不双扣
    with store.connect() as conn:
        conn.execute("update photo_answer_jobs set status='pending', lease_until=0 where id=?", (job["id"],))
        conn.execute("update photo_answer_sessions set status='processing' where id=?", (s["id"],))
    svc.process_job(job["id"])

    assert l0.calls == 2 and l1.calls == 2  # 引擎没有被再次调用
    assert CostLedger(store).spent_micros(s["id"]) == spent_first
    assert store.get_session(s["id"])["status"] == "awaiting_confirm"


def test_l1_budget_exhausted_degrades_to_l0_only(store):
    l0 = FakeEngine("baidu_handwriting", cost=49_000)  # 2 页 = 98_000，软顶只剩 2_000
    l1 = FakeEngine("qwen_vl_ocr", cost=1_600)
    svc, images = _make_service(store, l0=l0, l1=l1)
    s = _prep_session(store, images, pages=2)
    job = svc.submit(s["id"])
    svc.process_job(job["id"])

    assert l0.calls == 2
    assert l1.calls < 2  # 预算耗尽后 L1 被跳过（降级，不失败）
    assert store.get_job(job["id"])["status"] == "succeeded"


def test_l0_failure_refunds_and_fails_job(store):
    l0 = FakeEngine("baidu_handwriting", fail=True)
    svc, images = _make_service(store, l0=l0)
    s = _prep_session(store, images, pages=1)
    job = svc.submit(s["id"])
    svc.process_job(job["id"])

    assert store.get_job(job["id"])["status"] == "failed"
    assert store.get_session(s["id"])["status"] == "failed"
    ledger = CostLedger(store)
    assert ledger.spent_micros(s["id"]) == 0
    assert ledger.reserved_micros(s["id"]) == 0  # 失败必退预留


def test_view_contains_paragraphs_stem_fold_and_draft(store):
    stem = "背景资料：某新建办公楼工程，总承包单位与专业分包单位签订了合同。"
    l0 = FakeEngine("baidu_handwriting", text="背景资料：某新建办公楼工程，总承包单位与专业分包单位签订了合同。\n1）不妥之处：未审核方案")
    svc, images = _make_service(store, l0=l0)
    s = _prep_session(store, images, pages=1, stem=stem)
    job = svc.submit(s["id"])
    svc.process_job(job["id"])

    view = svc.get_view(s["id"])
    stem_paras = [p for p in view["paragraphs"] if p["is_stem_suspect"]]
    assert len(stem_paras) == 1
    assert "不妥之处" in view["draft_text"]
    assert stem_paras[0]["text"] not in view["draft_text"]  # 默认不计入草稿但保留展示


def test_confirm_requires_ack_for_unresolved_normal_suspicions(store):
    chars = [{"line_index": 0, "char": "组", "box": [40, 20, 30, 30], "prob": 0.3, "candidates": ["织"]}]
    l0 = FakeEngine("baidu_handwriting", chars=chars)
    svc, images = _make_service(store, l0=l0)
    s = _prep_session(store, images, pages=1)
    job = svc.submit(s["id"])
    svc.process_job(job["id"])

    out = svc.confirm(s["id"], confirmed_text="施工组织设计", job_version=1)
    assert out["status"] == "needs_review_ack"

    out2 = svc.confirm(s["id"], confirmed_text="施工组织设计", job_version=1, ack_normal_suspicions=True)
    assert out2["status"] == "confirmed"
    payload = out2["grader_payload"]
    assert payload["input_mode"] == "photo_ocr"
    assert payload["confirmed_text"] == "施工组织设计"
    assert payload["grading_tier"] == "standard"
    assert payload["learning_evidence_allowed"] is True


def test_confirm_critical_unresolved_failcloses_to_provisional(store):
    chars = [{"line_index": 0, "char": "8", "box": [40, 20, 30, 30], "prob": 0.2, "candidates": ["3"]}]
    l0 = FakeEngine("baidu_handwriting", text="工期为8天", chars=chars)
    svc, images = _make_service(store, l0=l0)
    s = _prep_session(store, images, pages=1)
    job = svc.submit(s["id"])
    svc.process_job(job["id"])

    out = svc.confirm(s["id"], confirmed_text="工期为8天", job_version=1, ack_normal_suspicions=True)
    assert out["status"] == "confirmed"
    payload = out["grader_payload"]
    assert payload["grading_tier"] == "provisional"  # 关键疑点未解决 → 降级
    assert payload["learning_evidence_allowed"] is False  # 不写长期学习证据（C9）


def test_confirm_wrong_job_version_rejected(store):
    l0 = FakeEngine("baidu_handwriting")
    svc, images = _make_service(store, l0=l0)
    s = _prep_session(store, images, pages=1)
    job = svc.submit(s["id"])
    svc.process_job(job["id"])
    with pytest.raises(ValueError, match="job_version"):
        svc.confirm(s["id"], confirmed_text="x", job_version=99, ack_normal_suspicions=True)


def test_user_escalation_runs_l2_once_and_prefers_it_in_view(store):
    l0 = FakeEngine("baidu_handwriting", text="模糊错误文本")
    l2 = FakeEngine("aliyun_handwriting", text="清晰正确文本", cost=225_000)
    svc, images = _make_service(store, l0=l0, l2=l2)
    s = _prep_session(store, images, pages=1)
    job = svc.submit(s["id"])
    svc.process_job(job["id"])

    svc.escalate_page(s["id"], page_index=0)
    assert l2.calls == 1
    view = svc.get_view(s["id"])
    assert "清晰正确文本" in view["draft_text"]  # L2 结果接管该页

    with pytest.raises(EscalationLimitReached):
        svc.escalate_page(s["id"], page_index=0)
