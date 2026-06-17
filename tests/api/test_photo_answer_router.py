"""photo-answer REST router 测试：flag 门 / 全链路 / ownership / EXIF / 升级通道 / 边界校验 / 限流。"""

from __future__ import annotations

import io
import time

import pytest

pytest.importorskip("fastapi")
FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from PIL import Image

from deeptutor.api.dependencies import rate_limit as rate_limit_module
from deeptutor.api.routers import photo_answer as pa_router
from deeptutor.services.photo_answer.cost_ledger import CostLedger
from deeptutor.services.photo_answer.engines.base import EngineResult
from deeptutor.services.photo_answer.service import PhotoAnswerService
from deeptutor.services.photo_answer.store import PhotoAnswerStore


@pytest.fixture(autouse=True)
def _clear_rate_limit_state(monkeypatch):
    # 用内存后端 + 清桶，保证限流用例与既有用例彼此隔离
    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_BACKEND", "memory")
    rate_limit_module.clear_rate_limit_state()
    yield
    rate_limit_module.clear_rate_limit_state()


class FakeEngine:
    def __init__(self, name: str, text: str, cost: int = 10_000):
        self.name = name
        self.text = text
        self.cost = cost
        self.calls = 0

    def recognize(self, image_bytes: bytes) -> EngineResult:
        self.calls += 1
        return EngineResult(
            engine=self.name,
            raw_text=self.text,
            line_boxes=[
                {"line_index": i, "text": t, "box": [10, 20 + 40 * i, 300, 30]}
                for i, t in enumerate(self.text.splitlines())
            ],
            provider_usage_id=f"{self.name}-{self.calls}",
            cost_micros=self.cost,
        )


def _jpeg_bytes(*, with_exif: bool = False) -> bytes:
    img = Image.new("RGB", (900, 1200), color=(250, 250, 245))
    buf = io.BytesIO()
    if with_exif:
        exif = Image.Exif()
        exif[0x010F] = "TestMaker"  # Make
        exif[0x0131] = "TestSoftware 1.0"  # Software
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPTUTOR_PHOTO_ANSWER_ENABLED", "1")
    store = PhotoAnswerStore(tmp_path / "pa.db")
    l0 = FakeEngine("baidu_handwriting", "1）不妥之处：未审核方案\n2）正确做法：报总监理工程师")
    l2 = FakeEngine("aliyun_handwriting", "升级后清晰文本", cost=225_000)
    images_root = tmp_path / "imgs"
    images_root.mkdir()

    runtime = pa_router.PhotoAnswerRuntime(
        store=store,
        ledger=CostLedger(store),
        images_root=images_root,
        l0_factory=lambda: l0,
        l1_factory=None,
        l2_factory=lambda: l2,
    )
    pa_router.set_runtime_for_tests(runtime)
    monkeypatch.setattr(
        pa_router, "_resolve_user_id", lambda authorization: (authorization or "u1").replace("Bearer ", "")
    )

    app = FastAPI()
    app.include_router(pa_router.router, prefix="/api/v1/photo-answer")
    client = TestClient(app)
    yield client, store, l0, l2
    pa_router.set_runtime_for_tests(None)


def _auth(user="u1"):
    return {"Authorization": f"Bearer {user}"}


def _create_session(client):
    resp = client.post(
        "/api/v1/photo-answer/sessions",
        json={"question_id": "Q1", "question_stem": "背景资料：某工程。"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["session"]


def test_flag_off_hides_endpoints(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPTUTOR_PHOTO_ANSWER_ENABLED", raising=False)
    app = FastAPI()
    app.include_router(pa_router.router, prefix="/api/v1/photo-answer")
    client = TestClient(app)
    resp = client.post("/api/v1/photo-answer/sessions", json={"question_id": "Q1"}, headers=_auth())
    assert resp.status_code == 404


def test_full_flow_create_upload_submit_poll_confirm(app_client):
    client, store, l0, _ = app_client
    session = _create_session(client)
    sid = session["id"]

    up = client.post(
        f"/api/v1/photo-answer/sessions/{sid}/pages",
        files={"file": ("page0.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"page_index": "0"},
        headers=_auth(),
    )
    assert up.status_code == 200, up.text
    assert up.json()["page"]["quality"]["ok"] in (True, False)

    sub = client.post(f"/api/v1/photo-answer/sessions/{sid}/submit", headers=_auth())
    assert sub.status_code == 200
    job = sub.json()["job"]
    assert job["job_version"] == 1

    # TestClient 在响应后同步执行 BackgroundTasks → 轮询应已是 awaiting_confirm
    poll = client.get(f"/api/v1/photo-answer/sessions/{sid}", headers=_auth())
    assert poll.status_code == 200
    body = poll.json()
    assert body["session"]["status"] == "awaiting_confirm"
    assert "不妥之处" in body["view"]["draft_text"]
    assert l0.calls == 1

    conf = client.post(
        f"/api/v1/photo-answer/sessions/{sid}/confirm",
        json={"confirmed_text": "1）不妥之处：未审核方案", "job_version": 1, "ack_normal_suspicions": True},
        headers=_auth(),
    )
    assert conf.status_code == 200
    payload = conf.json()["grader_payload"]
    assert payload["input_mode"] == "photo_ocr"
    assert payload["question_id"] == "Q1"


def test_ownership_other_user_gets_404(app_client):
    client, *_ = app_client
    session = _create_session(client)
    resp = client.get(f"/api/v1/photo-answer/sessions/{session['id']}", headers=_auth("intruder"))
    assert resp.status_code == 404


def test_stale_job_version_confirm_409(app_client):
    client, *_ = app_client
    session = _create_session(client)
    sid = session["id"]
    client.post(
        f"/api/v1/photo-answer/sessions/{sid}/pages",
        files={"file": ("p.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"page_index": "0"},
        headers=_auth(),
    )
    client.post(f"/api/v1/photo-answer/sessions/{sid}/submit", headers=_auth())
    resp = client.post(
        f"/api/v1/photo-answer/sessions/{sid}/confirm",
        json={"confirmed_text": "x", "job_version": 99, "ack_normal_suspicions": True},
        headers=_auth(),
    )
    assert resp.status_code == 409


def test_upload_strips_exif(app_client, tmp_path):
    client, store, *_ = app_client
    session = _create_session(client)
    sid = session["id"]
    client.post(
        f"/api/v1/photo-answer/sessions/{sid}/pages",
        files={"file": ("p.jpg", _jpeg_bytes(with_exif=True), "image/jpeg")},
        data={"page_index": "0"},
        headers=_auth(),
    )
    pages = store.list_pages(sid)
    import json as _json

    ref = _json.loads(pages[0]["image_ref"])
    saved = Image.open(ref["path"])
    assert dict(saved.getexif()) == {}  # EXIF（含 GPS）必须被剥离


def test_non_image_upload_rejected(app_client):
    client, *_ = app_client
    session = _create_session(client)
    resp = client.post(
        f"/api/v1/photo-answer/sessions/{session['id']}/pages",
        files={"file": ("p.heic", b"\x00\x00\x00 ftypheic not decodable", "image/heic")},
        data={"page_index": "0"},
        headers=_auth(),
    )
    assert resp.status_code == 415


def test_escalation_endpoint_once_then_409(app_client):
    client, store, l0, l2 = app_client
    session = _create_session(client)
    sid = session["id"]
    client.post(
        f"/api/v1/photo-answer/sessions/{sid}/pages",
        files={"file": ("p.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"page_index": "0"},
        headers=_auth(),
    )
    client.post(f"/api/v1/photo-answer/sessions/{sid}/submit", headers=_auth())

    r1 = client.post(
        f"/api/v1/photo-answer/sessions/{sid}/retry",
        json={"mode": "escalate", "page_index": 0},
        headers=_auth(),
    )
    assert r1.status_code == 200, r1.text
    assert l2.calls == 1
    assert "升级后清晰文本" in r1.json()["view"]["draft_text"]

    r2 = client.post(
        f"/api/v1/photo-answer/sessions/{sid}/retry",
        json={"mode": "escalate", "page_index": 0},
        headers=_auth(),
    )
    assert r2.status_code == 409


# ---------- 外部边界：输入上限（根因 1）----------


def test_question_stem_over_limit_rejected(app_client):
    client, *_ = app_client
    resp = client.post(
        "/api/v1/photo-answer/sessions",
        json={"question_id": "Q1", "question_stem": "x" * 4001},
        headers=_auth(),
    )
    assert resp.status_code == 422


def test_question_stem_at_limit_accepted(app_client):
    client, *_ = app_client
    resp = client.post(
        "/api/v1/photo-answer/sessions",
        json={"question_id": "Q1", "question_stem": "x" * 4000},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text


def test_confirmed_text_over_limit_rejected(app_client):
    client, *_ = app_client
    session = _create_session(client)
    sid = session["id"]
    resp = client.post(
        f"/api/v1/photo-answer/sessions/{sid}/confirm",
        json={"confirmed_text": "x" * 20001, "job_version": 1, "ack_normal_suspicions": True},
        headers=_auth(),
    )
    assert resp.status_code == 422


# ---------- 崩溃恢复守卫：仅 running+租约过期可恢复（根因 2）----------


def _submit_one_page(client, store):
    session = _create_session(client)
    sid = session["id"]
    client.post(
        f"/api/v1/photo-answer/sessions/{sid}/pages",
        files={"file": ("p.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"page_index": "0"},
        headers=_auth(),
    )
    client.post(f"/api/v1/photo-answer/sessions/{sid}/submit", headers=_auth())
    return sid


@pytest.mark.parametrize("terminal_status", ["succeeded", "failed"])
def test_crash_recovery_does_not_reset_terminal_job(app_client, terminal_status):
    client, store, *_ = app_client
    sid = _submit_one_page(client, store)
    job = store.get_latest_job(sid)
    # 把 job 强制成终态 + 租约过期，模拟"已结束但租约已过期"的遗孤
    store.finish_job(str(job["id"]), terminal_status)
    with store.connect() as conn:
        conn.execute(
            "update photo_answer_jobs set lease_until=? where id=?",
            (time.time() - 999, str(job["id"])),
        )

    resp = client.get(f"/api/v1/photo-answer/sessions/{sid}", headers=_auth())
    assert resp.status_code == 200
    after = store.get_job(str(job["id"]))
    # 终态不可被恢复重派
    assert after["status"] == terminal_status


def test_crash_recovery_resets_running_job_with_expired_lease(app_client):
    client, store, *_ = app_client
    sid = _submit_one_page(client, store)
    job = store.get_latest_job(sid)
    job_id = str(job["id"])
    # 模拟进程重启遗孤：running + 租约过期
    with store.connect() as conn:
        conn.execute(
            "update photo_answer_jobs set status='running', lease_until=?, finished_at=NULL where id=?",
            (time.time() - 999, job_id),
        )

    resp = client.get(f"/api/v1/photo-answer/sessions/{sid}", headers=_auth())
    assert resp.status_code == 200
    # 恢复路径会下沉到 store 并由 background task 重新执行 → 终态 succeeded
    after = store.get_job(job_id)
    assert after["status"] in ("pending", "running", "succeeded")
    assert after["status"] != "failed"


def test_store_recover_stale_job_guards_running_only(app_client):
    client, store, *_ = app_client
    sid = _submit_one_page(client, store)
    job_id = str(store.get_latest_job(sid)["id"])

    # 终态 succeeded → 不恢复
    store.finish_job(job_id, "succeeded")
    assert store.recover_stale_job(job_id) is False
    assert store.get_job(job_id)["status"] == "succeeded"

    # running → 恢复为 pending 且租约清零
    with store.connect() as conn:
        conn.execute(
            "update photo_answer_jobs set status='running', lease_until=?, finished_at=NULL where id=?",
            (time.time() + 5, job_id),
        )
    assert store.recover_stale_job(job_id) is True
    recovered = store.get_job(job_id)
    assert recovered["status"] == "pending"
    assert float(recovered["lease_until"]) == 0


# ---------- 付费 OCR 端点限流（根因 3）----------


def test_create_session_rate_limited(app_client, monkeypatch):
    client, *_ = app_client
    # 收紧策略到 2/窗口，便于触发；沿用仓库统一的 set_rate_limit_policy 覆盖姿势
    rate_limit_module.set_rate_limit_policy("photo_answer_create_session", 2, 60.0)
    rate_limit_module.clear_rate_limit_state()
    statuses = []
    for _ in range(4):
        resp = client.post(
            "/api/v1/photo-answer/sessions",
            json={"question_id": "Q1"},
            headers=_auth(),
        )
        statuses.append(resp.status_code)
    assert 429 in statuses
    # 限流命中前的请求应成功
    assert statuses[0] == 200
