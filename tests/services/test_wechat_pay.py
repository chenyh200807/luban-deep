from __future__ import annotations

import asyncio
import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from deeptutor.services import wechat_pay


def _write_private_key(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "apiclient_key.pem"
    path.write_bytes(pem)
    return path


def _set_wechat_pay_env(monkeypatch, tmp_path, *, api_v3_key: str = "12345678901234567890123456789012"):
    key_path = _write_private_key(tmp_path)
    monkeypatch.setenv("WECHAT_PAY_MCH_ID", "1639299994")
    monkeypatch.setenv("WECHAT_PAY_APP_ID", "wx6d4fbd3776ea7d4d")
    monkeypatch.setenv("WECHAT_PAY_API_V3_KEY", api_v3_key)
    monkeypatch.setenv("WECHAT_PAY_CERT_SERIAL_NO", "CERTSERIAL-TEST-001")
    monkeypatch.setenv("WECHAT_PAY_PRIVATE_KEY_PATH", str(key_path))
    monkeypatch.setenv("WECHAT_PAY_NOTIFY_URL", "https://test2.yousenjiaoyu.com/api/v1/billing/wechat/notify")
    monkeypatch.delenv("WECHAT_PAY_API_BASE", raising=False)
    return key_path


def test_create_wechat_jsapi_order_posts_signed_prepay_request(monkeypatch, tmp_path) -> None:
    _set_wechat_pay_env(monkeypatch, tmp_path)
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        headers = {"Request-ID": "req_123"}

        def json(self):
            return {"prepay_id": "wx_prepay_123"}

    class FakeClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, content, headers):
            captured["url"] = url
            captured["body"] = json.loads(content.decode("utf-8"))
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(wechat_pay.httpx, "AsyncClient", FakeClient)
    checkout = {
        "order_id": "dt_wechat_local",
        "amount_fen": 19800,
        "currency": "CNY",
        "package": {"id": "vip", "label": "VIP"},
        "payment": {"type": "wechat_mp", "params": None, "qr_code_url": ""},
    }
    result = asyncio.run(
        wechat_pay.create_wechat_jsapi_order(
            checkout,
            openid="openid_123",
            attach='{"u":"student_demo","p":"vip","a":19800,"d":365}',
        )
    )

    assert result is not None
    assert captured["url"] == "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"
    body = captured["body"]
    assert body["appid"] == "wx6d4fbd3776ea7d4d"
    assert body["mchid"] == "1639299994"
    assert body["payer"] == {"openid": "openid_123"}
    assert body["amount"] == {"total": 19800, "currency": "CNY"}
    assert str(body["out_trade_no"]).startswith("dtw")
    assert len(str(body["out_trade_no"])) <= 32
    headers = captured["headers"]
    assert str(headers["Authorization"]).startswith("WECHATPAY2-SHA256-RSA2048 ")
    assert result["status"] == "pending_payment"
    assert result["payment"]["params"]["package"] == "prepay_id=wx_prepay_123"
    assert result["payment"]["params"]["signType"] == "RSA"


def test_decrypt_wechat_pay_notification_uses_api_v3_key(monkeypatch, tmp_path) -> None:
    api_v3_key = "12345678901234567890123456789012"
    _set_wechat_pay_env(monkeypatch, tmp_path, api_v3_key=api_v3_key)
    nonce = b"nonce-123456"
    associated_data = b"transaction"
    plaintext = {"trade_state": "SUCCESS", "transaction_id": "420000000000"}
    ciphertext = AESGCM(api_v3_key.encode("utf-8")).encrypt(
        nonce,
        json.dumps(plaintext).encode("utf-8"),
        associated_data,
    )
    payload = {
        "resource": {
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "nonce": nonce.decode("utf-8"),
            "associated_data": associated_data.decode("utf-8"),
        }
    }

    assert wechat_pay.decrypt_wechat_pay_notification(payload) == plaintext
