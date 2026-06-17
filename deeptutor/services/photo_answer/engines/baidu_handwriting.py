"""百度手写文字识别（标准版）— L0 主识别引擎.

API: https://ai.baidu.com/ai-doc/OCR/hk3h7y2qq
- recognize_granularity=small → per-char boxes + candidates + probability
- detect_alteration=true → 涂改痕迹 (returned as '☰' chars)
Pricing anchor (plan §3.2, 2026-06-10): 0.01 元/次起 → estimate 10_000 micros;
the ledger settles with this estimate until provider billing data lands.
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
from typing import Any

import httpx

from deeptutor.services.photo_answer.engines.base import (
    EngineError,
    EngineNotConfigured,
    EngineResult,
)

_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
_OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/handwriting"

PRICE_MICROS = 10_000  # 0.01 元/次（后付费起价，plan §3.2）


def _loc_to_box(loc: dict[str, Any] | None) -> list[int]:
    loc = loc or {}
    return [int(loc.get("left", 0)), int(loc.get("top", 0)), int(loc.get("width", 0)), int(loc.get("height", 0))]


class BaiduHandwritingEngine:
    name = "baidu_handwriting"

    def __init__(self, *, api_key: str, secret_key: str, client: httpx.Client | None = None) -> None:
        if not api_key or not secret_key:
            raise EngineNotConfigured("Baidu OCR requires BAIDU_OCR_API_KEY and BAIDU_OCR_SECRET_KEY")
        self._api_key = api_key
        self._secret_key = secret_key
        self._client = client or httpx.Client(timeout=15.0)
        self._token: str = ""
        self._token_expiry: float = 0.0

    @classmethod
    def from_env(cls) -> "BaiduHandwritingEngine":
        api_key = os.environ.get("BAIDU_OCR_API_KEY", "").strip()
        secret_key = os.environ.get("BAIDU_OCR_SECRET_KEY", "").strip()
        if not api_key or not secret_key:
            raise EngineNotConfigured("Baidu OCR requires BAIDU_OCR_API_KEY and BAIDU_OCR_SECRET_KEY")
        return cls(api_key=api_key, secret_key=secret_key)

    def _access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expiry - 60:
            return self._token
        resp = self._client.post(
            _TOKEN_URL,
            params={
                "grant_type": "client_credentials",
                "client_id": self._api_key,
                "client_secret": self._secret_key,
            },
        )
        if resp.status_code != 200:
            raise EngineError(f"Baidu token endpoint HTTP {resp.status_code}")
        payload = resp.json()
        token = str(payload.get("access_token") or "")
        if not token:
            raise EngineError(f"Baidu token error: {payload}")
        self._token = token
        self._token_expiry = now + float(payload.get("expires_in") or 0)
        return token

    def recognize(self, image_bytes: bytes) -> EngineResult:
        token = self._access_token()
        request_hash = hashlib.sha256(image_bytes).hexdigest()
        resp = self._client.post(
            _OCR_URL,
            params={"access_token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "image": base64.b64encode(image_bytes).decode(),
                "recognize_granularity": "small",
                "probability": "true",
                "detect_alteration": "true",
                "detect_direction": "true",
            },
        )
        if resp.status_code != 200:
            raise EngineError(f"Baidu OCR HTTP {resp.status_code}")
        payload = resp.json()
        if payload.get("error_code"):
            raise EngineError(
                f"Baidu OCR error {payload.get('error_code')}: {payload.get('error_msg')}"
            )

        lines: list[dict[str, Any]] = []
        chars: list[dict[str, Any]] = []
        alterations: list[dict[str, Any]] = []
        texts: list[str] = []
        for line_index, item in enumerate(payload.get("words_result") or []):
            words = str(item.get("words") or "")
            texts.append(words)
            lines.append(
                {
                    "line_index": line_index,
                    "text": words,
                    "box": _loc_to_box(item.get("location")),
                }
            )
            for ch in item.get("chars") or []:
                prob_payload = ch.get("probability") or {}
                entry = {
                    "line_index": line_index,
                    "char": str(ch.get("char") or ""),
                    "box": _loc_to_box(ch.get("location")),
                    "prob": float(prob_payload.get("average") or 0.0),
                    "candidates": list(ch.get("candidates") or []),
                }
                chars.append(entry)
                if entry["char"] == "☰":  # detect_alteration marker
                    alterations.append({"line_index": line_index, "box": entry["box"]})

        return EngineResult(
            engine=self.name,
            raw_text="\n".join(texts),
            line_boxes=lines,
            char_confidences=chars,
            alteration_marks=alterations,
            engine_model_version="handwriting-v1",
            provider_usage_id=str(payload.get("log_id") or ""),
            request_hash=request_hash,
            cost_micros=PRICE_MICROS,
        )
