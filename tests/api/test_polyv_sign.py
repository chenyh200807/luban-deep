import hashlib

from fastapi.testclient import TestClient

from deeptutor.api.main import app


def test_polyv_sign_returns_valid_signature(monkeypatch):
    monkeypatch.setenv("POLYV_SECRET_KEY", "mnABa9XMn8")
    client = TestClient(app)
    resp = client.get("/api/v1/polyv/sign", params={"vid": "abc123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["vid"] == "abc123"
    assert isinstance(body["ts"], int) and body["ts"] > 0
    # 算法必须与 polyv 旧客户端一致: md5(secret + vid + ts)
    expected = hashlib.md5(f"mnABa9XMn8abc123{body['ts']}".encode()).hexdigest()
    assert body["sign"] == expected
    assert len(body["sign"]) == 32


def test_polyv_sign_honors_env_secret(monkeypatch):
    monkeypatch.setenv("POLYV_SECRET_KEY", "rotated_secret_xyz")
    client = TestClient(app)
    resp = client.get("/api/v1/polyv/sign", params={"vid": "v9"})
    body = resp.json()
    expected = hashlib.md5(f"rotated_secret_xyzv9{body['ts']}".encode()).hexdigest()
    assert body["sign"] == expected


def test_polyv_sign_fail_closed_without_secret(monkeypatch):
    # 未配 POLYV_SECRET_KEY → 503,绝不用硬编码默认密钥签名
    monkeypatch.delenv("POLYV_SECRET_KEY", raising=False)
    client = TestClient(app)
    resp = client.get("/api/v1/polyv/sign", params={"vid": "v1"})
    assert resp.status_code == 503
