from __future__ import annotations

import re
from typing import Any


_REDACTED_PLACEHOLDER = "[INTERNAL_OUTPUT_REDACTED]"
_SAFE_FALLBACK = "暂时未生成适合直接展示的答案，请重试一次。"

_INTERNAL_OUTPUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\s*\|?\s*DSML\s*\|?", re.IGNORECASE),
    re.compile(r"\bDSML\b.{0,80}\b(?:toolcalls?|invoke|parameter)\b", re.IGNORECASE),
    re.compile(r"\binvoke\s+name=[\"']?(?:readfile|read_file|writefile|write_file|listdir|list_dir)", re.IGNORECASE),
    re.compile(r"\bparameter\s+name=[\"']?filepath[\"']?", re.IGNORECASE),
    re.compile(r"/app/data/tutorbot/.{0,240}/workspace/skills/(?:memory|references)/", re.IGNORECASE),
    re.compile(r"```(?:bash|sh|python|py|json)?\s*(?:read_file|toolcall|web_search|python|bash)\b", re.IGNORECASE),
    re.compile(r"\b(?:read_file|readfile|toolcall|web_search)\s+(?:path|query|args)=", re.IGNORECASE),
    re.compile(r"(?:HEARTBEAT\.md|\bread_file\b|\bwrite_file\b|\blist_dir\b)", re.IGNORECASE),
    re.compile(r"\b(?:AGENTS\.md|SOUL\.md|TOOLS\.md|BOOTSTRAP_FILES)\b", re.IGNORECASE),
    re.compile(r"</?(?:rags|toolcall|tool_call|tool_result|observation)\b", re.IGNORECASE),
    re.compile(r"\"(?:tool_calls|function_call)\"\s*:|\"arguments\"\s*:\s*\{", re.IGNORECASE),
    re.compile(r"<!doctype\s+html\b|<html\b[^>]*>.*?</html>", re.IGNORECASE | re.DOTALL),
    re.compile(r"(?:\.env\b|api[_ -]?key\s*=|secret\s*=|password\s*=|token\s*=|密钥\s*[:=]|密码\s*[:=]|凭证\s*[:=])", re.IGNORECASE),
    re.compile(r"(?:InternalError\.Algo\.DataInspectionFailed|DataInspectionFailed|Request timed out)", re.IGNORECASE),
    re.compile(r"(?:provider error|raw provider|HTTP_?40[04]|HTTP_?50[023])", re.IGNORECASE),
    re.compile(
        r"(?:Authentication Fails|authentication_error|invalid_request_error|api key.{0,40}invalid|Error code:\s*401)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:现在)?(?:让我|我来)(?:读取|查看|检查|分析|打开|浏览).{0,40}(?:技能文件|references|目录结构|技能系统|参考文件)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:好的|好|可以)?(?:，|,)?(?:我来|我先|先|正在|准备).{0,80}(?:读取|加载|查看|展开|调取).{0,80}\b(?:skill|reference)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:现在)?(?:让我|我来)(?:读取|查看|检查|分析|打开|浏览).{0,60}(?:文件|目录|路径|workspace|HEARTBEAT)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:现在)?(?:让我|我来).{0,40}(?:这些技能文件|第二个技能文件|第三个技能文件)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:这里输出的是|这是).{0,20}(?:内部思路|内部观察|内部总结)", re.IGNORECASE),
    re.compile(r"(?:internal reasoning|internal synthesis|do not answer the student directly)", re.IGNORECASE),
    re.compile(r"(?:thinking stage|observing stage|final response stage)", re.IGNORECASE),
    re.compile(r"(?:不要直接回答学生|不要暴露内部链路|不要暴露内部思考过程)", re.IGNORECASE),
    re.compile(r"(?:本轮可用工具背景|当前启用工具|tool context for this turn)", re.IGNORECASE),
)


def looks_like_internal_output(text: str | None) -> bool:
    source = str(text or "").strip()
    if not source:
        return False
    normalized = re.sub(r"\s+", " ", source)
    for pattern in _INTERNAL_OUTPUT_PATTERNS:
        if pattern.search(normalized):
            return True
    return False


def _script_name(char: str) -> str | None:
    if not char.isalpha():
        return None
    codepoint = ord(char)
    if 0x4E00 <= codepoint <= 0x9FFF or 0x3400 <= codepoint <= 0x4DBF:
        return "cjk"
    if 0x3040 <= codepoint <= 0x30FF:
        return "kana"
    if 0xAC00 <= codepoint <= 0xD7AF or 0x1100 <= codepoint <= 0x11FF:
        return "hangul"
    if 0x0400 <= codepoint <= 0x04FF:
        return "cyrillic"
    if 0x0600 <= codepoint <= 0x06FF:
        return "arabic"
    if 0x0590 <= codepoint <= 0x05FF:
        return "hebrew"
    if 0x0370 <= codepoint <= 0x03FF:
        return "greek"
    if 0x0900 <= codepoint <= 0x097F:
        return "devanagari"
    if 0x0980 <= codepoint <= 0x09FF:
        return "bengali"
    if 0x0D80 <= codepoint <= 0x0DFF:
        return "sinhala"
    if 0x0530 <= codepoint <= 0x058F:
        return "armenian"
    if char.isascii():
        return "latin"
    return None


def looks_like_malformed_model_output(text: str | None) -> bool:
    source = str(text or "").strip()
    if len(source) < 80:
        return False

    script_counts: dict[str, int] = {}
    letter_count = 0
    for char in source:
        script = _script_name(char)
        if script is None:
            continue
        letter_count += 1
        script_counts[script] = script_counts.get(script, 0) + 1

    if letter_count < 60:
        return False
    active_scripts = {script for script, count in script_counts.items() if count >= 2}
    if len(active_scripts) < 4:
        return False
    if not {"cjk", "latin"}.issubset(active_scripts):
        return False

    long_ascii_fragments = re.findall(r"[A-Za-z_][A-Za-z0-9_]{7,}", source)
    if len(long_ascii_fragments) < 3:
        return False

    dominant_share = max(script_counts.values()) / max(letter_count, 1)
    return dominant_share < 0.82


def looks_like_unsafe_visible_output(text: str | None) -> bool:
    return looks_like_internal_output(text) or looks_like_malformed_model_output(text)


def coerce_user_visible_answer(
    text: str | None,
    *,
    fallback: str = _SAFE_FALLBACK,
) -> str:
    source = str(text or "").strip()
    if not source:
        return ""
    if looks_like_unsafe_visible_output(source):
        return fallback
    return source


def redact_internal_output(value: Any) -> Any:
    if isinstance(value, str):
        return _REDACTED_PLACEHOLDER if looks_like_unsafe_visible_output(value) else value
    if isinstance(value, list):
        return [redact_internal_output(item) for item in value]
    if isinstance(value, tuple):
        return [redact_internal_output(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_internal_output(item) for key, item in value.items()}
    return value


__all__ = [
    "coerce_user_visible_answer",
    "looks_like_malformed_model_output",
    "looks_like_internal_output",
    "looks_like_unsafe_visible_output",
    "redact_internal_output",
]
