from __future__ import annotations

import json
import re
from typing import Any


def coerce_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith(("{", "[")) or raw in {"null", '""'}:
            try:
                return json.loads(raw)
            except Exception:
                return value
    return value


def is_meaningful(value: Any) -> bool:
    value = coerce_jsonish(value)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def normalize_options(value: Any) -> dict[str, str]:
    value = coerce_jsonish(value)
    if isinstance(value, dict):
        return {
            str(key).strip().upper(): str(option_value or "").strip()
            for key, option_value in value.items()
            if str(key).strip() and str(option_value or "").strip()
        }
    if isinstance(value, list):
        options: dict[str, str] = {}
        for item in value:
            if isinstance(item, dict):
                key = str(item.get("key") or item.get("label") or item.get("option") or "").strip().upper()
                text = str(item.get("value") or item.get("text") or item.get("content") or "").strip()
            else:
                match = re.match(r"\s*([A-EＡ-Ｅ])\s*[.、:：)]?\s*(.+)\s*$", str(item or ""), re.I)
                key = match.group(1).upper() if match else ""
                text = match.group(2).strip() if match else str(item or "").strip()
            key = normalize_choice_letters(key)
            if len(key) == 1 and text:
                options[key] = text
        return options
    return {}


def normalize_choice_letters(value: Any) -> str:
    value = coerce_jsonish(value)
    if isinstance(value, list):
        raw = "".join(str(item or "") for item in value)
    elif isinstance(value, dict):
        raw = "".join(str(item or "") for item in value.values())
    else:
        raw = str(value or "")
    raw = raw.translate(str.maketrans({"Ａ": "A", "Ｂ": "B", "Ｃ": "C", "Ｄ": "D", "Ｅ": "E"}))
    letters = re.findall(r"[A-E]", raw.upper())
    return "".join(dict.fromkeys(letters))


def normalize_keyword_list(value: Any) -> list[str]:
    value = coerce_jsonish(value)
    candidates: list[Any]
    if isinstance(value, list):
        candidates = value
    elif isinstance(value, dict):
        candidates = list(value.values())
    elif isinstance(value, str):
        candidates = re.split(r"[、,，;；\n]+", value)
    else:
        candidates = []

    keywords: list[str] = []
    for item in candidates:
        if isinstance(item, dict):
            item = item.get("keyword") or item.get("name") or item.get("value") or item.get("text")
        text = re.sub(r"\s+", "", str(item or "")).strip()
        if text and text not in keywords and not re.fullmatch(r"[A-E]", text, flags=re.I):
            keywords.append(text)
    return keywords


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
