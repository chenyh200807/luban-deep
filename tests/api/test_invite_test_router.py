from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.routers import invite_test as invite_test_router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(invite_test_router.router, prefix="/api/v1/invite-test")
    return app


def _valid_payload() -> dict[str, object]:
    return {
        "name": "张同学",
        "phone": "13800138000",
        "email": "qa@example.com",
        "wechatId": "wx_luban",
        "province": "江苏",
        "ageRange": "26-35 岁",
        "education": "本科",
        "occupation": "施工员",
        "examType": "二建建筑实务",
        "examStage": "正在冲刺刷题",
        "preparationYears": "第 2 次备考",
        "knowledgeFoundation": "基础薄弱",
        "painPoint": "错题原因不清楚",
        "weeklyTime": "10-30 分钟",
        "dailyStudyTime": "30-60 分钟",
        "studyDifficulties": "案例题不会组织语言。",
        "consent": True,
        "sourcePage": "invite-test",
        "utmSource": "intro",
        "utmCampaign": "landing_page",
    }


def test_invite_test_application_public_post_writes_visible_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invite_test_router._RATE_LIMIT_BUCKETS.clear()
    jsonl_path = tmp_path / "invite-test-applications.jsonl"
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("INVITE_TEST_APPLICATIONS_PATH", str(jsonl_path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.delenv("INVITE_TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DB_URL", raising=False)

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/invite-test/applications", json=_valid_payload())

    assert response.status_code == 201
    assert response.json()["ok"] is True
    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["phone"] == "13800138000"
    assert rows[0]["wechat_id"] == "wx_luban"
    assert rows[0]["utm_campaign"] == "landing_page"
    assert rows[0]["raw_payload"]["province"] == "江苏"
    assert rows[0]["raw_payload"]["dailyStudyTime"] == "30-60 分钟"


def test_invite_test_application_public_post_rejects_invalid_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invite_test_router._RATE_LIMIT_BUCKETS.clear()
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")

    payload = _valid_payload()
    payload["phone"] = "123"
    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/invite-test/applications", json=payload)

    assert response.status_code == 400
    assert "手机号格式不正确" in response.json()["detail"]


def test_invite_test_application_public_post_requires_wechat_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invite_test_router._RATE_LIMIT_BUCKETS.clear()
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")

    payload = _valid_payload()
    payload["wechatId"] = ""
    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/invite-test/applications", json=payload)

    assert response.status_code == 400
    assert "缺少必填字段：wechatId" in response.json()["detail"]
