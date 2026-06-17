"""Hermetic e2e：拍照→上传→OCR→确认→grader_payload 直接喂 CaseGradingSkillKernel。

证明 photo_answer 输出与既有批改内核的接缝成立（plan M1 验收），同时验证
C9 fail-closed：关键疑点未解决 → provisional + learning_evidence_allowed=False。
批改内核零修改——它只看到一个普通的 user_answer 字符串。
"""

from __future__ import annotations

import io

import pytest

pytest.importorskip("fastapi")
FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from PIL import Image

from deeptutor.api.routers import photo_answer as pa_router
from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.photo_answer.cost_ledger import CostLedger
from deeptutor.services.photo_answer.engines.base import EngineResult
from deeptutor.services.photo_answer.store import PhotoAnswerStore

STEM = "背景资料：某新建办公楼工程。问题：指出总承包单位做法的不妥之处并写出正确做法。"
ANSWER_TEXT = "1）不妥之处：总承包单位未将专项施工方案报送监理审核\n2）正确做法：应报送总监理工程师审查批准后实施"


class FakeEngine:
    def __init__(self, name: str, text: str, *, chars=None, cost: int = 10_000):
        self.name = name
        self.text = text
        self.chars = chars or []
        self.cost = cost

    def recognize(self, image_bytes: bytes) -> EngineResult:
        return EngineResult(
            engine=self.name,
            raw_text=self.text,
            line_boxes=[
                {"line_index": i, "text": t, "box": [10, 20 + 40 * i, 300, 30]}
                for i, t in enumerate(self.text.splitlines())
            ],
            char_confidences=list(self.chars),
            cost_micros=self.cost,
        )


def _jpeg() -> bytes:
    # 带笔画的清晰图——纯色图会被质检判 blurry，正确地触发 C9 provisional
    from PIL import ImageDraw

    img = Image.new("L", (900, 1200), color=245)
    draw = ImageDraw.Draw(img)
    for row in range(10):
        y = 60 + row * 110
        draw.line([(50, y), (850, y)], fill=20, width=4)
        for x in range(70, 820, 80):
            draw.rectangle([x, y - 36, x + 36, y - 4], outline=10, width=3)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _client(tmp_path, monkeypatch, *, l0_chars=None):
    monkeypatch.setenv("DEEPTUTOR_PHOTO_ANSWER_ENABLED", "1")
    store = PhotoAnswerStore(tmp_path / "pa.db")
    images_root = tmp_path / "imgs"
    images_root.mkdir()
    runtime = pa_router.PhotoAnswerRuntime(
        store=store,
        ledger=CostLedger(store),
        images_root=images_root,
        l0_factory=lambda: FakeEngine("baidu_handwriting", ANSWER_TEXT, chars=l0_chars),
        l1_factory=None,
        l2_factory=None,
    )
    pa_router.set_runtime_for_tests(runtime)
    monkeypatch.setattr(
        pa_router, "_resolve_user_id", lambda authorization: "stu-1"
    )
    app = FastAPI()
    app.include_router(pa_router.router, prefix="/api/v1/photo-answer")
    return TestClient(app)


def _run_flow(client, *, confirm_kwargs=None):
    session = client.post(
        "/api/v1/photo-answer/sessions",
        json={"question_id": "QE2E-1", "question_stem": STEM},
        headers={"Authorization": "Bearer t"},
    ).json()["session"]
    sid = session["id"]
    assert (
        client.post(
            f"/api/v1/photo-answer/sessions/{sid}/pages",
            files={"file": ("p0.jpg", _jpeg(), "image/jpeg")},
            data={"page_index": "0"},
            headers={"Authorization": "Bearer t"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/photo-answer/sessions/{sid}/submit", headers={"Authorization": "Bearer t"}
        ).status_code
        == 200
    )
    poll = client.get(f"/api/v1/photo-answer/sessions/{sid}", headers={"Authorization": "Bearer t"}).json()
    assert poll["session"]["status"] == "awaiting_confirm"
    body = {
        "confirmed_text": poll["view"]["draft_text"],
        "job_version": 1,
        "ack_normal_suspicions": True,
    }
    body.update(confirm_kwargs or {})
    conf = client.post(
        f"/api/v1/photo-answer/sessions/{sid}/confirm",
        json=body,
        headers={"Authorization": "Bearer t"},
    )
    assert conf.status_code == 200, conf.text
    return conf.json()


def test_confirmed_payload_grades_through_existing_kernel(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    out = _run_flow(client)
    payload = out["grader_payload"]
    assert payload["grading_tier"] == "standard"
    assert payload["learning_evidence_allowed"] is True

    # 接缝证明：payload 直接喂既有批改内核（内核零修改、零感知 photo 来源）
    question_row = {
        "question_id": payload["question_id"],
        "question_type": "case",
        "question_stem": STEM,
        "stem": STEM,
        "correct_answer": "总承包单位应将专项施工方案报送总监理工程师审查批准后实施",
        "node_code": "",
    }
    result = CaseGradingSkillKernel().grade(
        question_row=question_row, user_answer=payload["confirmed_text"]
    )
    graded = result.to_dict()
    assert graded  # 内核产出结构化批改结果
    assert "监理" in payload["confirmed_text"]


def test_critical_suspicion_failcloses_seam_to_provisional(tmp_path, monkeypatch):
    # 数字低置信 → critical 疑点；用户没解决 → provisional + 不写学习证据
    chars = [
        {"line_index": 0, "char": "1", "box": [12, 20, 20, 30], "prob": 0.2, "candidates": ["7"]}
    ]
    client = _client(tmp_path, monkeypatch, l0_chars=chars)
    out = _run_flow(client)
    payload = out["grader_payload"]
    assert payload["grading_tier"] == "provisional"
    assert payload["learning_evidence_allowed"] is False
    assert any(s["severity"] == "critical" for s in payload["suspicion_spans"])
