"""阿里云 RecognizeHandwriting — L2 疑难升级引擎.

API: ocr-api.cn-hangzhou.aliyuncs.com, version 2021-07-07, ACS3-HMAC-SHA256
signature (Alibaba Cloud API signature v3). Body is the raw image binary;
NeedRotate/Paragraph/OutputCharInfo enabled per plan §3.2.

Pricing anchor (plan §3.2): 0.225 元/次 starter tier → 225_000 micros
estimate; tier drops are a billing-reconciliation concern, not runtime's.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any

import httpx

from deeptutor.services.photo_answer.engines.base import (
    EngineError,
    EngineNotConfigured,
    EngineResult,
)

_HOST = "ocr-api.cn-hangzhou.aliyuncs.com"
_ACTION = "RecognizeHandwriting"
_VERSION = "2021-07-07"
_ALGO = "ACS3-HMAC-SHA256"

PRICE_MICROS = 225_000  # 0.225 元/次 starter tier（plan §3.2）


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _pos_to_box(pos: list[dict[str, Any]] | None) -> list[int]:
    points = pos or []
    xs = [int(p.get("x", 0)) for p in points] or [0]
    ys = [int(p.get("y", 0)) for p in points] or [0]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


class AliyunHandwritingEngine:
    name = "aliyun_handwriting"

    def __init__(
        self,
        *,
        access_key_id: str,
        access_key_secret: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not access_key_id or not access_key_secret:
            raise EngineNotConfigured(
                "Aliyun OCR requires ALIBABA_CLOUD_ACCESS_KEY_ID and ALIBABA_CLOUD_ACCESS_KEY_SECRET"
            )
        self._ak_id = access_key_id
        self._ak_secret = access_key_secret
        self._client = client or httpx.Client(timeout=20.0)

    @classmethod
    def from_env(cls) -> "AliyunHandwritingEngine":
        ak_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "").strip()
        ak_secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "").strip()
        if not ak_id or not ak_secret:
            raise EngineNotConfigured(
                "Aliyun OCR requires ALIBABA_CLOUD_ACCESS_KEY_ID and ALIBABA_CLOUD_ACCESS_KEY_SECRET"
            )
        return cls(access_key_id=ak_id, access_key_secret=ak_secret)

    def _signed_headers(self, *, query: str, body: bytes) -> dict[str, str]:
        """Build ACS3-HMAC-SHA256 headers for a POST with binary body."""
        body_hash = _sha256_hex(body)
        headers = {
            "host": _HOST,
            "x-acs-action": _ACTION,
            "x-acs-version": _VERSION,
            "x-acs-date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "x-acs-signature-nonce": uuid.uuid4().hex,
            "x-acs-content-sha256": body_hash,
        }
        signed_header_names = ";".join(sorted(headers))
        canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
        canonical_request = "\n".join(
            ["POST", "/", query, canonical_headers, signed_header_names, body_hash]
        )
        string_to_sign = f"{_ALGO}\n{_sha256_hex(canonical_request.encode())}"
        signature = hmac.new(
            self._ak_secret.encode(), string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        headers["authorization"] = (
            f"{_ALGO} Credential={self._ak_id},"
            f"SignedHeaders={signed_header_names},Signature={signature}"
        )
        return headers

    def recognize(self, image_bytes: bytes) -> EngineResult:
        request_hash = _sha256_hex(image_bytes)
        query_pairs = [
            ("NeedRotate", "true"),
            ("NeedSortPage", "true"),
            ("OutputCharInfo", "true"),
            ("OutputTable", "true"),
            ("Paragraph", "true"),
        ]
        query = "&".join(f"{k}={v}" for k, v in query_pairs)
        headers = self._signed_headers(query=query, body=image_bytes)
        resp = self._client.post(
            f"https://{_HOST}/?{query}",
            headers={**headers, "content-type": "application/octet-stream"},
            content=image_bytes,
        )
        if resp.status_code != 200:
            raise EngineError(f"Aliyun OCR HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        if payload.get("Code"):
            raise EngineError(f"Aliyun OCR error {payload.get('Code')}: {payload.get('Message')}")
        data_raw = payload.get("Data")
        data = json.loads(data_raw) if isinstance(data_raw, str) else (data_raw or {})

        lines: list[dict[str, Any]] = []
        chars: list[dict[str, Any]] = []
        for line_index, info in enumerate(data.get("prism_wordsInfo") or []):
            lines.append(
                {
                    "line_index": line_index,
                    "text": str(info.get("word") or ""),
                    "box": _pos_to_box(info.get("pos")),
                }
            )
            for ch in info.get("charInfo") or []:
                chars.append(
                    {
                        "line_index": line_index,
                        "char": str(ch.get("word") or ""),
                        "box": [int(ch.get("x", 0)), int(ch.get("y", 0)), int(ch.get("w", 0)), int(ch.get("h", 0))],
                        "prob": float(ch.get("prob") or 0.0) / (100.0 if float(ch.get("prob") or 0.0) > 1 else 1.0),
                        "candidates": [],
                    }
                )

        paragraphs = [
            str(p.get("paragraphContent") or "")
            for p in data.get("prism_paragraphsInfo") or []
        ]
        raw_text = "\n".join(paragraphs) if paragraphs else str(data.get("content") or "")

        return EngineResult(
            engine=self.name,
            raw_text=raw_text,
            line_boxes=lines,
            char_confidences=chars,
            engine_model_version=f"{_ACTION}-{_VERSION}",
            provider_usage_id=str(payload.get("RequestId") or ""),
            request_hash=request_hash,
            cost_micros=PRICE_MICROS,
        )
