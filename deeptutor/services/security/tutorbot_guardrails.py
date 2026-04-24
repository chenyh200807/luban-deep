"""TutorBot guardrails for prompt-injection and internal-info leakage."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


INTERNAL_INFO_REFUSAL_ZH = (
    "这类内容我不展开。"
    "你可以把要解决的建筑实务题目、错题或复习困惑发给我，我会帮你拆成答案、判定依据、踩分点和易错点。"
)


@dataclass(frozen=True)
class TutorBotGuardrailResult:
    blocked: bool
    level: str
    signals: tuple[str, ...] = ()
    content: str | None = None


_ZERO_WIDTH_TRANSLATION = str.maketrans(
    {
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\ufeff": "",
    }
)

_INPUT_BLOCK_PATTERNS: tuple[tuple[str, str], ...] = (
    ("prompt_extraction", r"(系统|system|developer|开发者).{0,12}(提示词|prompt|message|消息|指令|instruction)"),
    ("prompt_extraction", r"(提示词|prompt|instructions?|指令).{0,16}(给我|发我|输出|打印|展示|复述|改写|总结|reveal|show|print|display|dump)"),
    ("internal_design", r"(内部|internal).{0,12}(设计|机制|架构|链路|实现|规则|配置|design|architecture|mechanism|rules?)"),
    ("internal_design", r"(项目|project).{0,12}(prompt|提示词|设计|内部|源码|配置|机制)"),
    ("internal_design", r"(三层|多层).{0,8}(防护|保护|安全|guardrail|guardrails?)"),
    ("internal_design", r"(guardrail|guardrails?|安全策略|防护规则|防护机制).{0,16}(规则|机制|配置|列出来|说明|解释|show|print|display|dump)"),
    ("toolchain", r"(工具|tool|function|函数|rag|检索|调用).{0,12}(链路|参数|schema|清单|配置|内部|调用过程)"),
    ("secret_exfiltration", r"(\.env|api[_ -]?key|secret|password|token|密钥|密码|凭证|环境变量)"),
    ("role_override", r"(忽略|无视|忘记|放弃|覆盖).{0,12}(之前|以上|所有|系统|开发者).{0,8}(指令|规则|设定|instructions?)"),
    ("role_override", r"(ignore|disregard|forget|override).{0,20}(previous|prior|above|system|developer).{0,12}(instruction|message|rules?)"),
    ("role_override", r"(现在|从现在起).{0,8}(你是|扮演|切换成|进入).{0,16}(无限制|开发者模式|系统|admin|root)"),
    ("role_override", r"(developer mode|jailbreak|dan mode|admin mode|root mode)"),
    ("format_injection", r"(<\|im_start\|>|<\|system\|>|\[inst\]|```system|role\s*:\s*system|\"role\"\s*:\s*\"system\")"),
    ("format_injection", r"(tool_calls?|function_call|arguments).{0,16}(输出|打印|展示|show|print|display)"),
)

_TOOL_CONTENT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("embedded_override", r"(?im)^\s*(ignore|disregard|forget|override)\b.*(instruction|rules?|system|developer)"),
    ("embedded_override", r"(?im)^\s*(忽略|无视|忘记|覆盖).*(指令|规则|系统|开发者)"),
    ("embedded_extraction", r"(reveal|show|print|display|dump).{0,16}(system prompt|developer message|instructions?)"),
    ("embedded_extraction", r"(输出|打印|展示|复述).{0,16}(系统提示词|开发者消息|内部指令|提示词)"),
    ("embedded_role", r"(<\|im_start\|>|```system|role\s*:\s*system|\"role\"\s*:\s*\"system\")"),
)

_OUTPUT_LEAK_PATTERNS: tuple[tuple[str, str], ...] = (
    ("bootstrap_file", r"(?im)^#\s*(agent instructions|soul|tools|user)\b"),
    ("bootstrap_file", r"\b(AGENTS\.md|SOUL\.md|TOOLS\.md|BOOTSTRAP_FILES)\b"),
    ("runtime_path", r"\bYour workspace is at\b|\b/Users/[^ \n]+/(deeptutor|FastAPI20251222)\b"),
    ("role_dump", r"(<\|im_start\|>system|```system|\"role\"\s*:\s*\"system\")"),
    ("tool_call_dump", r"\"tool_calls\"\s*:|\"function_call\"\s*:|\"arguments\"\s*:\s*\{"),
    ("prompt_dump", r"(系统提示词|developer message|system prompt).{0,12}(如下|是|:|：)"),
)

_REFUSAL_MARKERS = (
    "不能提供",
    "不能复述",
    "不能透露",
    "不会提供",
    "无法提供",
    "属于内部系统信息",
    "不展开",
)


def normalize_guardrail_text(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH_TRANSLATION)
    return re.sub(r"\s+", " ", normalized).strip().lower()


def classify_tutorbot_user_input(text: str | None) -> TutorBotGuardrailResult:
    normalized = normalize_guardrail_text(text)
    if not normalized:
        return TutorBotGuardrailResult(blocked=False, level="safe")

    signals: list[str] = []
    for signal, pattern in _INPUT_BLOCK_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            signals.append(signal)

    if not signals:
        return TutorBotGuardrailResult(blocked=False, level="safe")

    unique_signals = tuple(dict.fromkeys(signals))
    return TutorBotGuardrailResult(
        blocked=True,
        level="high" if {"secret_exfiltration", "prompt_extraction"} & set(unique_signals) else "medium",
        signals=unique_signals,
        content=INTERNAL_INFO_REFUSAL_ZH,
    )


def sanitize_untrusted_context(text: str | None, *, source: str = "tool") -> TutorBotGuardrailResult:
    if not text:
        return TutorBotGuardrailResult(blocked=False, level="safe", content=text or "")

    sanitized = str(text)
    signals: list[str] = []
    for signal, pattern in _TOOL_CONTENT_PATTERNS:
        updated = re.sub(pattern, "[filtered embedded instruction]", sanitized, flags=re.IGNORECASE)
        if updated != sanitized:
            signals.append(f"{source}:{signal}")
            sanitized = updated

    return TutorBotGuardrailResult(
        blocked=False,
        level="sanitized" if signals else "safe",
        signals=tuple(dict.fromkeys(signals)),
        content=sanitized,
    )


def guard_tutorbot_output(text: str | None) -> TutorBotGuardrailResult:
    content = "" if text is None else str(text)
    if not content:
        return TutorBotGuardrailResult(blocked=False, level="safe", content=content)
    if any(marker in content for marker in _REFUSAL_MARKERS):
        return TutorBotGuardrailResult(blocked=False, level="safe", content=content)

    signals: list[str] = []
    for signal, pattern in _OUTPUT_LEAK_PATTERNS:
        if re.search(pattern, content, flags=re.IGNORECASE):
            signals.append(signal)

    if not signals:
        return TutorBotGuardrailResult(blocked=False, level="safe", content=content)

    return TutorBotGuardrailResult(
        blocked=True,
        level="high",
        signals=tuple(dict.fromkeys(signals)),
        content=INTERNAL_INFO_REFUSAL_ZH,
    )
