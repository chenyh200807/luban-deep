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
    # 单一公开输出 sink(task #25,2026-06-22,总指挥官"单一公开 sink"裁决):
    # coerce_user_visible_answer 是所有学生可见答案文本的唯一汇聚函数——result.response
    # 投影、live event.content、持久 assistant 消息、terminal 都经它。在此一处剥离漏给
    # 学生的孤儿数字脚注 〔N〕(主 LLM 输出但解析不到来源的内部引用噪声),替代各 emit
    # 路径(判分/讲解/出题)分别 strip 的 per-path 补丁(阶段1 只覆盖了引用路径,判分路径漏)。
    # 按"这段文本里 〔N〕 有没有 backing footer"判,与全局 citation flag 无关:
    # 实证(2026-06-23)test2 上 flag=True 但判分 LLM 吐的 〔N〕 没 footer 仍是孤儿。
    # strip_orphan_reference_markers 内部 footer-aware:有合法 footer 整段不动,否则剥孤儿。
    try:
        from deeptutor.services.citations.assembler import strip_orphan_reference_markers

        stripped = strip_orphan_reference_markers(source)
        if stripped:
            source = stripped
    except Exception:
        pass
    return source


# content_truth ② 法规条文数值断言的确定性 hedge 守卫(2026-07-01):
# 业务事实——终态答案把"具名规范/法规 + 具体条款或数值"当事实直出、却全程无 hedge
# 免责时,必须补一句标准免责:法规具体值随规范修订/考试大纲变化,以现行官方规范为准,
# 不得以绝对真相呈现。这是把 hedge 从"LLM 概率产出(~2/3,非确定)"降级为"确定性终态
# 守卫兜底"。仅在终态全文一次性应用(见 turn_runtime 终态投影),绝不碰 token 级 delta。
# 幂等:已带 hedge(含本 NOTICE 自身)不重复贴。内容级触发、capability 无关。
_REG_SOURCE_CLAIM = re.compile(
    r"(《[^》]{2,40}》|\b(?:GB|JGJ|JG|CJJ|CECS|DBJ|DB|TB|JTG)\b\s*/?\s*T?\s*\d)"
)
_REG_VALUE_CLAIM = re.compile(
    r"(第\s*\d+\s*条|\d+\s*(?:年|个月|月|日|天|周|小时|米|mm|MPa|kN|kg|%|‰|级|度))"
)
# 既有 hedge 检测:命中即不追加(避免双重免责 + 保证幂等)。刻意保持"强显式 hedge"口径,
# 宁可多贴一句也不漏贴——漏贴才是本次要修的失败方向。
_EXISTING_HEDGE = re.compile(
    r"(以(现行)?(教材|规范|标准|官方|大纲).{0,10}为准"
    r"|请(以|参考).{0,24}(规范|标准|教材|大纲).{0,10}(为准|核对|核实)"
    r"|AI\s*生成|不保证(100%|完全|绝对)?(准确|正确)|仅供参考"
    r"|最终以.{0,14}为准|如有出入|具体(以|请以).{0,14}(规范|标准|文件|大纲))"
)
HEDGE_NOTICE = (
    "\n\n> 📌 以上具体条文与数值依据常见教材/规范整理，"
    "可能随规范修订或考试大纲更新而变化，请以现行有效的官方规范和最新考试大纲为准。"
)


def ensure_regulatory_hedge(text: str | None) -> str:
    """终态答案含"具名规范/法规 + 具体条款/数值"断言却无 hedge 时,补标准免责。

    幂等 + 内容级自限:仅当(具名规范源 且 具体条款/数值)同时命中、且全程无既有 hedge
    时追加 HEDGE_NOTICE;HEDGE_NOTICE 自身命中 _EXISTING_HEDGE,重复调用不会二次追加。
    只应在终态全文上调用(非 token delta)。
    """
    source = str(text or "")
    if not source.strip():
        return source
    if not (_REG_SOURCE_CLAIM.search(source) and _REG_VALUE_CLAIM.search(source)):
        return source
    if _EXISTING_HEDGE.search(source):
        return source
    return source.rstrip() + HEDGE_NOTICE


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
    "ensure_regulatory_hedge",
    "looks_like_malformed_model_output",
    "looks_like_internal_output",
    "looks_like_unsafe_visible_output",
    "redact_internal_output",
]
