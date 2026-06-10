"""三引擎薄客户端测试（httpx MockTransport，零真实网络）。"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from deeptutor.services.photo_answer.engines.base import EngineError, EngineNotConfigured
from deeptutor.services.photo_answer.engines.aliyun_handwriting import AliyunHandwritingEngine
from deeptutor.services.photo_answer.engines.baidu_handwriting import BaiduHandwritingEngine
from deeptutor.services.photo_answer.engines.qwen_vl_ocr import QwenVlOcrEngine

IMG = b"\xff\xd8\xff\xe0fakejpegbytes"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------- 百度 L0 ----------


def _baidu_handler(request: httpx.Request) -> httpx.Response:
    if "oauth/2.0/token" in str(request.url):
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 2592000})
    assert "handwriting" in str(request.url)
    body = request.content.decode()
    assert "recognize_granularity=small" in body
    assert "probability=true" in body
    assert "detect_alteration=true" in body
    return httpx.Response(
        200,
        json={
            "log_id": 123,
            "words_result": [
                {
                    "words": "施工组织设计",
                    "location": {"left": 10, "top": 20, "width": 200, "height": 30},
                    "chars": [
                        {
                            "char": "施",
                            "location": {"left": 10, "top": 20, "width": 30, "height": 30},
                            "probability": {"average": 0.98},
                            "candidates": ["施", "拖"],
                        },
                        {
                            "char": "组",
                            "location": {"left": 40, "top": 20, "width": 30, "height": 30},
                            "probability": {"average": 0.41},
                            "candidates": ["组", "织"],
                        },
                    ],
                },
                {"words": "1）编制依据", "location": {"left": 10, "top": 60, "width": 180, "height": 28}},
            ],
        },
    )


def test_baidu_parses_lines_chars_and_confidence():
    eng = BaiduHandwritingEngine(api_key="ak", secret_key="sk", client=_client(_baidu_handler))
    result = eng.recognize(IMG)
    assert result.engine == "baidu_handwriting"
    assert "施工组织设计" in result.raw_text and "1）编制依据" in result.raw_text
    assert len(result.line_boxes) == 2
    assert result.line_boxes[0]["box"] == [10, 20, 200, 30]
    chars = result.char_confidences
    assert chars[0]["char"] == "施" and chars[0]["prob"] == pytest.approx(0.98)
    assert chars[1]["candidates"] == ["组", "织"]
    assert result.provider_usage_id == "123"


def test_baidu_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("BAIDU_OCR_API_KEY", raising=False)
    monkeypatch.delenv("BAIDU_OCR_SECRET_KEY", raising=False)
    with pytest.raises(EngineNotConfigured):
        BaiduHandwritingEngine.from_env()


def test_baidu_api_error_raises_engine_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth" in str(request.url):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 100})
        return httpx.Response(200, json={"error_code": 17, "error_msg": "daily limit reached"})

    eng = BaiduHandwritingEngine(api_key="ak", secret_key="sk", client=_client(handler))
    with pytest.raises(EngineError, match="daily limit"):
        eng.recognize(IMG)


# ---------- qwen-vl-ocr L1 ----------


def _qwen_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["authorization"] == "Bearer dash-key"
    payload = json.loads(request.content)
    assert payload["model"] == "qwen-vl-ocr"
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-9",
            "choices": [{"message": {"role": "assistant", "content": "施工组织设计\n1）编制依据"}}],
            "usage": {"prompt_tokens": 4000, "completion_tokens": 800},
        },
    )


def test_qwen_returns_text_and_token_based_cost():
    eng = QwenVlOcrEngine(api_key="dash-key", client=_client(_qwen_handler))
    result = eng.recognize(IMG)
    assert result.raw_text == "施工组织设计\n1）编制依据"
    assert result.line_boxes == []  # 生成式无坐标——这是它只能当 L1 的原因
    # 0.3元/M 输入 + 0.5元/M 输出：4000*0.3 + 800*0.5 = 1200+400 微元 = 1600 micros
    assert result.cost_micros == 1600
    assert result.provider_usage_id == "chatcmpl-9"


def test_qwen_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(EngineNotConfigured):
        QwenVlOcrEngine.from_env()


# ---------- 阿里 L2 ----------


def _aliyun_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers.get("authorization", "").startswith("ACS3-HMAC-SHA256")
    assert request.headers.get("x-acs-action") == "RecognizeHandwriting"
    url = str(request.url)
    assert "NeedRotate=true" in url and "Paragraph=true" in url and "OutputCharInfo=true" in url
    data = {
        "content": "施工组织设计 1）编制依据",
        "prism_wordsInfo": [
            {"word": "施工组织设计", "pos": [{"x": 10, "y": 20}, {"x": 210, "y": 20}, {"x": 210, "y": 50}, {"x": 10, "y": 50}]},
        ],
        "prism_paragraphsInfo": [{"paragraphContent": "施工组织设计"}],
    }
    return httpx.Response(200, json={"RequestId": "req-77", "Data": json.dumps(data, ensure_ascii=False)})


def test_aliyun_signs_and_parses_paragraphs():
    eng = AliyunHandwritingEngine(
        access_key_id="akid", access_key_secret="aksec", client=_client(_aliyun_handler)
    )
    result = eng.recognize(IMG)
    assert "施工组织设计" in result.raw_text
    assert result.line_boxes[0]["box"] == [10, 20, 200, 30]  # pos 四点 → x,y,w,h
    assert result.provider_usage_id == "req-77"


def test_aliyun_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("ALIBABA_CLOUD_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", raising=False)
    with pytest.raises(EngineNotConfigured):
        AliyunHandwritingEngine.from_env()
