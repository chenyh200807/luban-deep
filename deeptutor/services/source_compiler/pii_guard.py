from __future__ import annotations

import re


PII_PATTERNS = [
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{17}[\dXx]\b"),
    re.compile(r"\b(?:openid|unionid)[_:=-]?[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
]


def assert_no_pii(text: str) -> None:
    for pattern in PII_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"Source payload appears to contain PII: {pattern.pattern}")

