"""公开练习页零答案键防回归门。

病灶（2026-07-18 审计）：42/43 公开练习页内嵌 ``ok:true`` 答案键、43/43 携
``keycard`` 泄露 model answer、11 页用 ``q.opts[s].ok`` 客户端判分——查源码即可
看答案。收权后判分唯一权威 = 服务端 ``RetestWritebackService.complete()``，
公开页只允许零答案键投影 + 服务端判分桥。本门对全部托管 practice*.html 做
机械断言，任何重新引入答案真值的发布都在 CI 直接红。
"""
from __future__ import annotations

from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
PUBLIC = REPO / "web" / "public" / "luban-preview"

# 答案真值只可能以「字段: 字面量」形态回流；viewmodel 的属性读
# （如 ``tempt:o.tempt`` / ``lose:a.lose||""``）不带字面量、不泄露。
_LEAK_PATTERNS: dict[str, re.Pattern[str]] = {
    "boolean_answer_key": re.compile(r"\bok2?\s*:\s*(?:true|false)"),
    "keycard": re.compile(r"keycard"),
    "answer_prose_field": re.compile(r"\b(?:model|tempt|lose|fix|why)\s*:\s*[\"'`]"),
    "bank_correct_index": re.compile(r"\bc\s*:\s*\d"),
    "bank_analysis_payload": re.compile(r"\bana\s*:\s*\[\s*\{\s*[\"'`A-Za-z_$]"),
    "is_correct_literal": re.compile(r"\bis_correct\b\s*[\"']?\s*:"),
}

_REQUIRED_BRIDGE_MARKERS = (
    "__dtSubmitRound",           # 交卷唯一入口（收集 → 服务端）
    "__dtBaseRenderVals(){",     # 本地 renderVals 已被降权包裹
    "practice-submit",           # 服务端判分薄适配器端点
    "__dtOverlayResult",         # 判定与逐项解析只渲染服务端返回
)


def _practice_pages() -> list[Path]:
    return sorted(PUBLIC.glob("*/practice*.html"))


def test_public_practice_pages_exist_in_expected_volume() -> None:
    pages = _practice_pages()
    # 40 站 43 面（b02 双面、s01 三面）；页面消失同样是门禁事故。
    assert len(pages) >= 43, [str(p) for p in pages]


def test_public_practice_pages_carry_zero_answer_key() -> None:
    offenders: list[str] = []
    for page in _practice_pages():
        html = page.read_text(encoding="utf-8")
        for name, pattern in _LEAK_PATTERNS.items():
            hits = pattern.findall(html)
            if hits:
                offenders.append(
                    f"{page.parent.name}/{page.name}: {name} x{len(hits)}"
                )
    assert offenders == []


def test_public_practice_pages_carry_server_grading_bridge() -> None:
    offenders: list[str] = []
    for page in _practice_pages():
        html = page.read_text(encoding="utf-8")
        for marker in _REQUIRED_BRIDGE_MARKERS:
            if marker not in html:
                offenders.append(f"{page.parent.name}/{page.name}: missing {marker}")
    assert offenders == []
