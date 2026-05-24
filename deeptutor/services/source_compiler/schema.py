from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def stable_hash(seed: str, *, prefix: str, length: int = 20) -> str:
    return prefix + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:length]


def content_hash(value: Any) -> str:
    if isinstance(value, str):
        normalized = normalize_text(value)
    else:
        normalized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()

