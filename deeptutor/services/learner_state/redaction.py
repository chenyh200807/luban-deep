from __future__ import annotations

import re
from typing import Any

_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_OPENID_RE = re.compile(r"openid[_A-Za-z0-9-]*")
_MENTION_RE = re.compile(r"@[A-Za-z0-9_\-\u4e00-\u9fff]+")
_COMMON_NAME_RE = re.compile(r"(?:我是|姓名[:：]?|学生[:：]?|学员[:：]?)([\u4e00-\u9fff]{2,4})")
_ADDRESS_RE = re.compile(r"[\u4e00-\u9fff]{2,}(?:省|市|区|县|镇|街道|路|号)[\u4e00-\u9fff0-9A-Za-z-]*")


def redact_chat_text(text: Any) -> str:
    value = str(text or "")
    value = _ADDRESS_RE.sub("[地址]", value)
    value = _PHONE_RE.sub("[手机号]", value)
    value = _EMAIL_RE.sub("[邮箱]", value)
    value = _ID_RE.sub("[身份证]", value)
    value = _OPENID_RE.sub("[用户标识]", value)
    value = _MENTION_RE.sub("[提及]", value)
    value = _COMMON_NAME_RE.sub(lambda match: match.group(0).replace(match.group(1), "[姓名]"), value)
    return value


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact_payload(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        return redact_chat_text(value)
    return value


__all__ = ["redact_chat_text", "redact_payload"]
