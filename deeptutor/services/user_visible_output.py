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
    re.compile(r"</?(?:rags|toolcall|tool_call|tool_result|observation)\b", re.IGNORECASE),
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


def coerce_user_visible_answer(
    text: str | None,
    *,
    fallback: str = _SAFE_FALLBACK,
) -> str:
    source = str(text or "").strip()
    if not source:
        return ""
    if looks_like_internal_output(source):
        return fallback
    return source


def redact_internal_output(value: Any) -> Any:
    if isinstance(value, str):
        return _REDACTED_PLACEHOLDER if looks_like_internal_output(value) else value
    if isinstance(value, list):
        return [redact_internal_output(item) for item in value]
    if isinstance(value, tuple):
        return [redact_internal_output(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_internal_output(item) for key, item in value.items()}
    return value


__all__ = [
    "coerce_user_visible_answer",
    "looks_like_internal_output",
    "redact_internal_output",
]
