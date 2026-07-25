from __future__ import annotations

import base64
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from deeptutor.services.member_console.service import DEFAULT_MEMBERSHIP_DAYS


WECHAT_PAY_API_BASE = "https://api.mch.weixin.qq.com"
WECHAT_PAY_NOTIFY_PATH = "/api/v1/billing/wechat/notify"
WECHAT_PAY_ATTACH_MAX_CHARS = 127


class WechatPayConfigError(RuntimeError):
    """Raised when native WeChat Pay is partially or incorrectly configured."""


class WechatPayUpstreamError(RuntimeError):
    def __init__(self, *, status_code: int, request_id: str, message: str) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.request_id = request_id


class WechatPayNotificationError(RuntimeError):
    """Raised when a WeChat Pay notification cannot be decoded safely."""


@dataclass(frozen=True, slots=True)
class WechatPayConfig:
    mch_id: str
    app_id: str
    api_v3_key: str
    cert_serial_no: str
    private_key_path: str
    notify_url: str
    api_base: str = WECHAT_PAY_API_BASE


def get_wechat_pay_config() -> WechatPayConfig | None:
    values = {
        "mch_id": _env("WECHAT_PAY_MCH_ID"),
        "app_id": _env("WECHAT_PAY_APP_ID") or _env("WECHAT_MP_APP_ID") or _env("WECHAT_MP_APPID"),
        "api_v3_key": _env("WECHAT_PAY_API_V3_KEY"),
        "cert_serial_no": _env("WECHAT_PAY_CERT_SERIAL_NO")
        or _env("WECHAT_PAY_MCH_CERT_SERIAL_NO"),
        "private_key_path": _env("WECHAT_PAY_PRIVATE_KEY_PATH")
        or _env("WECHAT_PAY_MCH_PRIVATE_KEY_PATH"),
        "notify_url": _env("WECHAT_PAY_NOTIFY_URL"),
        "api_base": _env("WECHAT_PAY_API_BASE") or WECHAT_PAY_API_BASE,
    }
    required = ("mch_id", "app_id", "api_v3_key", "cert_serial_no", "private_key_path", "notify_url")
    payment_specific = ("mch_id", "api_v3_key", "cert_serial_no", "private_key_path", "notify_url")
    if not any(values.get(name) for name in payment_specific):
        return None
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise WechatPayConfigError("Missing WeChat Pay config: " + ", ".join(missing))
    if len(values["api_v3_key"].encode("utf-8")) != 32:
        raise WechatPayConfigError("WECHAT_PAY_API_V3_KEY must be 32 bytes")
    private_key = Path(values["private_key_path"])
    if not private_key.is_file():
        raise WechatPayConfigError("WECHAT_PAY_PRIVATE_KEY_PATH does not exist")
    return WechatPayConfig(**values)


def build_wechat_pay_attach(
    *,
    user_id: str,
    package_id: str,
    amount_fen: int,
    days: int = DEFAULT_MEMBERSHIP_DAYS,
) -> str:
    payload = {
        "u": str(user_id or "").strip(),
        "p": str(package_id or "").strip(),
        "a": int(amount_fen or 0),
        "d": max(1, int(days or DEFAULT_MEMBERSHIP_DAYS)),
    }
    attach = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(attach) > WECHAT_PAY_ATTACH_MAX_CHARS:
        raise WechatPayConfigError("WeChat Pay attach payload is too long")
    return attach


def parse_wechat_pay_attach(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        source = value
    else:
        text = str(value or "").strip()
        if not text:
            raise WechatPayNotificationError("missing attach")
        try:
            source = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WechatPayNotificationError("invalid attach") from exc
    user_id = str(source.get("u") or source.get("user_id") or "").strip()
    package_id = str(source.get("p") or source.get("package_id") or "").strip()
    if not user_id or not package_id:
        raise WechatPayNotificationError("attach missing user/package")
    return {
        "user_id": user_id,
        "package_id": package_id,
        "amount_fen": int(source.get("a") or source.get("amount_fen") or 0),
        "days": max(1, int(source.get("d") or source.get("days") or DEFAULT_MEMBERSHIP_DAYS)),
    }


async def create_wechat_jsapi_order(
    checkout_payload: dict[str, Any],
    *,
    openid: str,
    attach: str,
) -> dict[str, Any] | None:
    config = get_wechat_pay_config()
    if config is None:
        return None
    payer_openid = str(openid or "").strip()
    if not payer_openid:
        raise WechatPayConfigError("WeChat openid is required for JSAPI payment")

    path = "/v3/pay/transactions/jsapi"
    out_trade_no = _new_out_trade_no()
    amount_fen = int(checkout_payload.get("amount_fen") or 0)
    body_payload = {
        "appid": config.app_id,
        "mchid": config.mch_id,
        "description": _payment_description(checkout_payload),
        "out_trade_no": out_trade_no,
        "notify_url": config.notify_url,
        "amount": {
            "total": amount_fen,
            "currency": str(checkout_payload.get("currency") or "CNY"),
        },
        "payer": {
            "openid": payer_openid,
        },
        "attach": attach,
    }
    body = json.dumps(body_payload, ensure_ascii=False, separators=(",", ":"))
    headers = {
        "Authorization": _authorization_header(config, method="POST", url_path=path, body=body),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "DeepTutor-WeChatPay/1.0",
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(f"{config.api_base}{path}", content=body.encode("utf-8"), headers=headers)
    request_id = str(response.headers.get("Request-ID") or response.headers.get("Wechatpay-Request-Id") or "")
    if response.status_code >= 400:
        raise WechatPayUpstreamError(
            status_code=response.status_code,
            request_id=request_id,
            message=_safe_upstream_message(response),
        )
    data = response.json()
    prepay_id = str(data.get("prepay_id") or "").strip()
    if not prepay_id:
        raise WechatPayUpstreamError(
            status_code=response.status_code,
            request_id=request_id,
            message="WeChat Pay response missing prepay_id",
        )

    payment_params = build_jsapi_payment_params(config, prepay_id=prepay_id)
    return {
        **checkout_payload,
        "status": "pending_payment",
        "payment": {
            "type": "wechat_mp",
            "params": payment_params,
            "qr_code_url": "",
        },
        "wechat_pay": {
            "out_trade_no": out_trade_no,
            "prepay_id": prepay_id,
            "request_id": request_id,
        },
        "message": "WeChat Pay order created.",
    }


def build_jsapi_payment_params(config: WechatPayConfig, *, prepay_id: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = _nonce()
    package = f"prepay_id={str(prepay_id or '').strip()}"
    message = f"{config.app_id}\n{timestamp}\n{nonce}\n{package}\n"
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce,
        "package": package,
        "signType": "RSA",
        "paySign": _sign(config, message),
    }


def decrypt_wechat_pay_notification(payload: dict[str, Any]) -> dict[str, Any]:
    config = get_wechat_pay_config()
    if config is None:
        raise WechatPayNotificationError("WeChat Pay is not configured")
    resource = payload.get("resource") if isinstance(payload, dict) else None
    if not isinstance(resource, dict):
        raise WechatPayNotificationError("missing resource")
    try:
        ciphertext = base64.b64decode(str(resource.get("ciphertext") or ""))
        nonce = str(resource.get("nonce") or "").encode("utf-8")
        associated_data = str(resource.get("associated_data") or "").encode("utf-8")
        plaintext = AESGCM(config.api_v3_key.encode("utf-8")).decrypt(nonce, ciphertext, associated_data)
        data = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise WechatPayNotificationError("invalid encrypted resource") from exc
    if not isinstance(data, dict):
        raise WechatPayNotificationError("invalid notification payload")
    return data


def _env(name: str) -> str:
    return str(os.getenv(name, "") or "").strip()


def _new_out_trade_no() -> str:
    return "dtw" + secrets.token_hex(14)


def _nonce() -> str:
    return secrets.token_hex(16)


def _payment_description(checkout_payload: dict[str, Any]) -> str:
    package = checkout_payload.get("package") if isinstance(checkout_payload.get("package"), dict) else {}
    label = str(package.get("label") or package.get("id") or "学习权益").strip()
    description = f"鲁班智考{label}套餐"
    return description[:127]


def _authorization_header(config: WechatPayConfig, *, method: str, url_path: str, body: str) -> str:
    timestamp = str(int(time.time()))
    nonce = _nonce()
    message = f"{method.upper()}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n"
    signature = _sign(config, message)
    return (
        'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{config.mch_id}",'
        f'nonce_str="{nonce}",'
        f'signature="{signature}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{config.cert_serial_no}"'
    )


def _sign(config: WechatPayConfig, message: str) -> str:
    private_key = serialization.load_pem_private_key(
        Path(config.private_key_path).read_bytes(),
        password=None,
    )
    signature = private_key.sign(
        message.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("ascii")


def _safe_upstream_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return "WeChat Pay upstream error"
    if isinstance(data, dict):
        code = str(data.get("code") or "").strip()
        message = str(data.get("message") or "").strip()
        return " ".join(part for part in (code, message) if part) or "WeChat Pay upstream error"
    return "WeChat Pay upstream error"
