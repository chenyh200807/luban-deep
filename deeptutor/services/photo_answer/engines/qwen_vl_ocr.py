"""qwen-vl-ocr (百炼) — L1 交叉校验引擎.

DashScope OpenAI-compatible endpoint. Generative: no coordinates, no char
confidence — therefore it only ever produces suspicion signals, never the
authoritative text (plan §2 红线 / §5 reconcile).

Cost: token-billed — 0.3 元/M input + 0.5 元/M output (plan §3.2,
pending M0 账单回放实证). Computed from the response usage block so every
settle carries the real token bill, not the estimate.
"""

from __future__ import annotations

import base64
import hashlib
import os

import httpx

from deeptutor.services.photo_answer.engines.base import (
    EngineError,
    EngineNotConfigured,
    EngineResult,
)

_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
_MODEL = "qwen-vl-ocr"

_INPUT_MICROS_PER_TOKEN = 0.3  # 0.3 元/1M tokens = 0.3 micros/token
_OUTPUT_MICROS_PER_TOKEN = 0.5

# Plain transcription instruction. Deliberately forbids "fixing" the text —
# generative rewrite of student errors is the exact failure mode the plan
# guards against; the prompt is one mitigation layer (the structural one is
# that L1 output never becomes authoritative text).
_PROMPT = (
    "请逐字转写图片中的全部手写文字。保持原文，不要纠正错别字，"
    "不要补全内容，不要解释。按行输出。"
)


class QwenVlOcrEngine:
    name = "qwen_vl_ocr"

    def __init__(self, *, api_key: str, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise EngineNotConfigured("qwen-vl-ocr requires DASHSCOPE_API_KEY")
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=30.0)

    @classmethod
    def from_env(cls) -> "QwenVlOcrEngine":
        api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            raise EngineNotConfigured("qwen-vl-ocr requires DASHSCOPE_API_KEY")
        return cls(api_key=api_key)

    def recognize(self, image_bytes: bytes) -> EngineResult:
        request_hash = hashlib.sha256(image_bytes).hexdigest()
        data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()
        resp = self._client.post(
            _URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": _MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {"type": "text", "text": _PROMPT},
                        ],
                    }
                ],
            },
        )
        if resp.status_code != 200:
            raise EngineError(f"qwen-vl-ocr HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        choices = payload.get("choices") or []
        if not choices:
            raise EngineError(f"qwen-vl-ocr empty choices: {payload}")
        text = str((choices[0].get("message") or {}).get("content") or "")
        usage = payload.get("usage") or {}
        cost = int(
            round(
                float(usage.get("prompt_tokens") or 0) * _INPUT_MICROS_PER_TOKEN
                + float(usage.get("completion_tokens") or 0) * _OUTPUT_MICROS_PER_TOKEN
            )
        )
        return EngineResult(
            engine=self.name,
            raw_text=text,
            line_boxes=[],  # generative — no coordinates by design
            engine_model_version=_MODEL,
            provider_usage_id=str(payload.get("id") or ""),
            request_hash=request_hash,
            cost_micros=cost,
        )
