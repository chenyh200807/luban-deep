"""Canonical TutorBot security policy used by thin runtime guardrail wrappers."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from deeptutor.services.user_visible_output import (
    coerce_user_visible_answer,
    looks_like_unsafe_visible_output,
)

INTERNAL_INFO_REFUSAL_ZH = (
    "这类内容我不展开。"
    "你可以把要解决的建筑实务题目、错题或复习困惑发给我，我会帮你拆成答案、判定依据、踩分点和易错点。"
)

PRODUCT_IDENTITY_RESPONSE_ZH = (
    "我是鲁班AI智考里的建筑实务备考导师，由鲁班AI智考产品团队为建筑实务备考场景设计。"
    "你可以直接把题目、答案或复习困惑发给我，我会帮你拆判断依据、踩分点和易错点。"
)


@dataclass(frozen=True)
class TutorBotSecurityDecision:
    blocked: bool
    level: str
    signals: tuple[str, ...] = ()
    content: str | None = None


@dataclass(frozen=True)
class SecurityPatternGroup:
    signal: str
    patterns: tuple[str, ...]


class TutorBotSecuritySkill:
    """Fat security skill: one policy authority for TutorBot visible boundaries."""

    _ZERO_WIDTH_TRANSLATION = str.maketrans(
        {
            "\u200b": "",
            "\u200c": "",
            "\u200d": "",
            "\ufeff": "",
        }
    )

    _USER_INPUT_GROUPS: tuple[SecurityPatternGroup, ...] = (
        SecurityPatternGroup(
            "prompt_extraction",
            (
                r"(系统|system|developer|开发者).{0,12}(提示词|prompt|message|消息|指令|instruction)",
                r"(提示词|prompt|instructions?|指令).{0,16}(给我|发我|输出|打印|展示|复述|改写|总结|reveal|show|print|display|dump)",
            ),
        ),
        SecurityPatternGroup(
            "internal_design",
            (
                r"(你|你们|系统|产品|平台|模型|agent|tutorbot|鲁班ai智考).{0,16}(内部|internal).{0,12}(设计|机制|架构|链路|实现|规则|配置|design|architecture|mechanism|rules?)",
                r"(内部|internal).{0,12}(prompt|system prompt|developer message|源码|配置|guardrails?)",
                r"(项目|project).{0,12}(prompt|提示词|system prompt|developer message|源码|配置|内部(?:设计|机制|架构|实现|规则)|guardrails?)",
                r"(三层|多层).{0,8}(防护|保护|安全|guardrail|guardrails?)",
                r"(guardrail|guardrails?|安全策略|防护规则|防护机制).{0,16}(规则|机制|配置|列出来|说明|解释|show|print|display|dump)",
            ),
        ),
        SecurityPatternGroup(
            "toolchain",
            (
                r"(你的|你们|系统|内部).{0,20}(工具|tool|function|函数|rag|检索|调用).{0,12}(链路|参数|schema|清单|列表|配置|内部|调用过程)",
                r"(rag|tool|function).{0,16}(参数|schema|配置|调用过程)",
                r"(列出|展示|输出).{0,12}(你的|你们的|系统|内部|所有).{0,12}(工具|tool|function|函数)",
                r"(show|list|dump).{0,12}(tools?|functions?)",
            ),
        ),
        SecurityPatternGroup(
            "internal_evidence_extraction",
            (
                r"(?:输出|打印|展示|列出|复述|原样|逐条|给我|告诉我|show|print|display|dump|reveal|list).{0,40}(?:内部)?(?:参考证据|证据来源|引用来源|检索来源|citation\s+source|source\s+title|source\s+titles?|evidence).{0,24}(?:标题|主题|来源|title|titles?)",
                r"(?:内部)?(?:参考证据|证据来源|引用来源|检索来源|citation\s+source|source\s+title|source\s+titles?|evidence).{0,24}(?:标题|主题|来源|title|titles?).{0,40}(?:输出|打印|展示|列出|复述|原样|逐条|给我|告诉我|show|print|display|dump|reveal|list)",
                r"(?:turn_semantic_decision|citation\s+source\s+title|source\s+title).{0,32}(?:原文|输出|展示|列出|show|print|display|dump)",
            ),
        ),
        SecurityPatternGroup(
            "internal_learner_memory_extraction",
            (
                r"(?:总结|输出|打印|展示|列出|复述|原样|逐条|给我|告诉我|show|print|display|dump|reveal|list|summari[sz]e).{0,48}(?:learner[_ -]?summary|working[_ -]?memory|long[- ]term learner profile|长期画像提示|局部工作记忆投影|内部(?:学习|用户)?画像)",
                r"(?:learner[_ -]?summary|working[_ -]?memory|long[- ]term learner profile|长期画像提示|局部工作记忆投影|内部(?:学习|用户)?画像).{0,48}(?:总结|输出|打印|展示|列出|复述|原样|逐条|给我|告诉我|show|print|display|dump|reveal|list|summari[sz]e)",
                r"(?:qa[_ -]?persona|身份标签).{0,32}(?:输出|展示|列出|show|print|display|dump|reveal|list)",
                r"(?:输出|展示|列出|show|print|display|dump|reveal|list).{0,32}(?:qa[_ -]?persona|身份标签)",
            ),
        ),
        SecurityPatternGroup(
            "secret_exfiltration",
            (
                r"(\.env|api[_ -]?key|secret)",
                r"(show|print|display|dump|reveal|输出|展示|打印|给我|泄露|读取|列出).{0,20}(password|token|密钥|密码|凭证|环境变量)",
                r"(password|token|密钥|密码|凭证|环境变量).{0,20}(show|print|display|dump|reveal|输出|展示|打印|给我|泄露|读取|列出|secret|api)",
            ),
        ),
        SecurityPatternGroup(
            "role_override",
            (
                r"(忽略|无视|忘记|放弃|覆盖).{0,12}(之前|以上|所有|系统|开发者).{0,8}(指令|规则|设定|instructions?)",
                r"(ignore|disregard|forget|override).{0,20}(previous|prior|above|system|developer).{0,12}(instruction|message|rules?)",
                r"(现在|从现在起).{0,8}(你是|扮演|切换成|进入).{0,16}(无限制|开发者模式|系统|admin|root)",
                r"(developer mode|jailbreak|dan mode|admin mode|root mode)",
            ),
        ),
        SecurityPatternGroup(
            "format_injection",
            (
                r"(<\|im_start\|>|<\|system\|>|\[inst\]|```system|role\s*:\s*system|\"role\"\s*:\s*\"system\")",
                r"(tool_calls?|function_call|arguments).{0,16}(输出|打印|展示|show|print|display)",
            ),
        ),
    )

    # Derived from FINAL_CLEANED_TAXONOMY2026.json. These terms are normal
    # construction-exam concepts that overlap with security vocabulary.
    _CONSTRUCTION_TAXONOMY_CONTEXT_TERMS = (
        "建筑内部装饰装修防火施工要求",
        "建筑内部装饰装修防火施工与验收有关规定",
        "内部设排水措施",
        "内部管理体系",
        "项目管理信息系统",
        "项目管理信息系统子系统",
        "施工现场监管信息系统",
        "项目办公自动化系统",
        "项目施工管理信息化系统应用",
        "绿色施工信息化系统应用",
        "业务应用子系统",
        "建筑设计",
        "施工图设计",
        "专项设计",
        "施工组织设计",
        "临时用电组织设计",
        "施工总平面布置图设计",
        "混凝土配合比设计",
        "基坑支护设计原则",
        "监测项目",
        "项目部管理",
        "项目质量计划",
        "施工项目管理机构",
        "项目对外宣传网站",
        "巡视检查工具",
        "检测工具",
        "特殊工具",
        "工具式栏板",
        "工具式定型化临时设施技术",
        "流水施工参数",
        "井点管参数",
        "搭设参数",
        "技术参数",
        "参数控制",
        "施工机械设备的配置",
        "灭火器配置",
        "消防器材配置标准",
        "劳动力配置计划",
        "抗压强度计算规则",
        "应急响应机制",
        "考核与评估机制",
        "机制砂",
        "撤离指令",
    )

    _CONSTRUCTION_TAXONOMY_SAFE_SIGNALS = frozenset({"internal_design", "toolchain"})

    _META_SYSTEM_INTENT_PATTERNS = (
        r"(你的|你们的|你们|tutorbot|agent|模型|大模型).{0,24}(内部|工具|tool|function|函数|rag|检索|调用|链路|参数|schema|配置|机制|规则|设计)",
        r"(系统提示词|developer message|system prompt|提示词|开发者消息|内部指令|源码|guardrails?)",
        r"(\.env|api[_ -]?key|secret|password|token|密钥|密码|凭证|环境变量)",
    )

    _PRODUCT_IDENTITY_GROUP = SecurityPatternGroup(
        "product_identity",
        (
            r"(谁|哪[个家位]?|什么人|哪个公司|哪个团队).{0,8}(开发|研发|训练|创造|制作|做出|做了).{0,8}(你|出来)",
            r"(你).{0,8}(谁|哪[个家位]?|什么人|哪个公司|哪个团队).{0,8}(开发|研发|训练|创造|制作|做出|做了)",
            r"(开发|研发|训练|创造|制作|做出|做了).{0,8}(你).{0,8}(的是谁|是谁|哪个团队|哪个公司)",
            r"(你的|你).{0,6}(训练数据|训练语料|数据来源).{0,12}(是什么|来自哪里|哪里来|列出来|给我|告诉我)",
            r"(开发团队|研发团队|训练团队).{0,12}(列出来|名单|是谁|哪些人|信息|告诉我|给我)",
        ),
    )

    _TOOL_CONTENT_GROUPS: tuple[SecurityPatternGroup, ...] = (
        SecurityPatternGroup(
            "embedded_override",
            (
                r"(?im)^\s*(ignore|disregard|forget|override)\b.*(instruction|rules?|system|developer)",
                r"(?im)^\s*(忽略|无视|忘记|覆盖).*(指令|规则|系统|开发者)",
            ),
        ),
        SecurityPatternGroup(
            "embedded_extraction",
            (
                r"(reveal|show|print|display|dump).{0,16}(system prompt|developer message|instructions?)",
                r"(输出|打印|展示|复述).{0,16}(系统提示词|开发者消息|内部指令|提示词)",
            ),
        ),
        SecurityPatternGroup(
            "embedded_role",
            (
                r"(<\|im_start\|>|```system|role\s*:\s*system|\"role\"\s*:\s*\"system\")",
            ),
        ),
        SecurityPatternGroup(
            "embedded_format_hijack",
            (
                r"\"tool_calls\"\s*:|\"function_call\"\s*:|\"arguments\"\s*:\s*\{",
                r"</?(?:toolcall|tool_call|function_call)\b",
            ),
        ),
    )

    _OUTPUT_LEAK_GROUPS: tuple[SecurityPatternGroup, ...] = (
        SecurityPatternGroup(
            "bootstrap_file",
            (
                r"(?im)^#\s*(agent instructions|soul|tools|user)\b",
                r"\b(AGENTS\.md|SOUL\.md|TOOLS\.md|BOOTSTRAP_FILES)\b",
            ),
        ),
        SecurityPatternGroup(
            "runtime_path",
            (
                r"\bYour workspace is at\b|\b/Users/[^ \n]+/(deeptutor|FastAPI20251222)\b",
            ),
        ),
        SecurityPatternGroup(
            "role_dump",
            (
                r"(<\|im_start\|>system|```system|\"role\"\s*:\s*\"system\")",
            ),
        ),
        SecurityPatternGroup(
            "tool_call_dump",
            (
                r"\"tool_calls\"\s*:|\"function_call\"\s*:|\"arguments\"\s*:\s*\{",
            ),
        ),
        SecurityPatternGroup(
            "prompt_dump",
            (
                r"(系统提示词|developer message|system prompt).{0,12}(如下|是|:|：)",
            ),
        ),
        SecurityPatternGroup(
            "secret_dump",
            (
                r"(\.env\b|api[_ -]?key\s*=|secret\s*=|password\s*=|token\s*=|密钥\s*[:=]|密码\s*[:=]|凭证\s*[:=])",
            ),
        ),
        SecurityPatternGroup(
            "internal_evidence_title_leak",
            (
                r"(?:内部)?(?:参考证据|证据来源|引用来源|检索来源).{0,24}(?:标题|主题|source\s+titles?|titles?).{0,16}(?:如下|列表|包括|[:：])",
                r"(?:citation\s+source\s+title|source\s+titles?).{0,24}(?:如下|列表|包括|[:：])",
            ),
        ),
        SecurityPatternGroup(
            "internal_learner_memory_leak",
            (
                r"(?:根据我看到的|我看到的|内部).{0,20}(?:内部)?(?:记忆上下文|学习画像|用户画像|画像提示|learner profile|working memory)",
                r"(?:身份标签|账号标签).{0,16}qa[_ -]?persona[_ -]?\d+",
                r"\bqa[_ -]?persona[_ -]?\d+\b",
            ),
        ),
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

    @classmethod
    def normalize_text(cls, text: str | None) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKC", text).translate(cls._ZERO_WIDTH_TRANSLATION)
        return re.sub(r"\s+", " ", normalized).strip().lower()

    @staticmethod
    def _matches_group(text: str, group: SecurityPatternGroup) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in group.patterns)

    @classmethod
    def _has_construction_taxonomy_context(cls, text: str) -> bool:
        return any(term.lower() in text for term in cls._CONSTRUCTION_TAXONOMY_CONTEXT_TERMS)

    @classmethod
    def _has_meta_system_intent(cls, text: str) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in cls._META_SYSTEM_INTENT_PATTERNS)

    @classmethod
    def _taxonomy_context_can_clear_medium_signals(cls, text: str, signals: tuple[str, ...]) -> bool:
        if not signals or not set(signals).issubset(cls._CONSTRUCTION_TAXONOMY_SAFE_SIGNALS):
            return False
        return cls._has_construction_taxonomy_context(text) and not cls._has_meta_system_intent(text)

    @classmethod
    def classify_user_input(cls, text: str | None) -> TutorBotSecurityDecision:
        normalized = cls.normalize_text(text)
        if not normalized:
            return TutorBotSecurityDecision(blocked=False, level="safe")

        signals = [
            group.signal
            for group in cls._USER_INPUT_GROUPS
            if cls._matches_group(normalized, group)
        ]
        if not signals and cls._matches_group(normalized, cls._PRODUCT_IDENTITY_GROUP):
            return TutorBotSecurityDecision(
                blocked=True,
                level="boundary",
                signals=(cls._PRODUCT_IDENTITY_GROUP.signal,),
                content=PRODUCT_IDENTITY_RESPONSE_ZH,
            )
        if not signals:
            return TutorBotSecurityDecision(blocked=False, level="safe")

        unique_signals = tuple(dict.fromkeys(signals))
        if cls._taxonomy_context_can_clear_medium_signals(normalized, unique_signals):
            return TutorBotSecurityDecision(blocked=False, level="safe")

        high_signals = {"secret_exfiltration", "prompt_extraction"}
        return TutorBotSecurityDecision(
            blocked=True,
            level="high" if high_signals & set(unique_signals) else "medium",
            signals=unique_signals,
            content=INTERNAL_INFO_REFUSAL_ZH,
        )

    @classmethod
    def sanitize_untrusted_context(
        cls,
        text: str | None,
        *,
        source: str = "tool",
    ) -> TutorBotSecurityDecision:
        if not text:
            return TutorBotSecurityDecision(blocked=False, level="safe", content=text or "")

        sanitized = str(text)
        signals: list[str] = []
        for group in cls._TOOL_CONTENT_GROUPS:
            for pattern in group.patterns:
                updated = re.sub(pattern, "[filtered embedded instruction]", sanitized, flags=re.IGNORECASE)
                if updated != sanitized:
                    signals.append(f"{source}:{group.signal}")
                    sanitized = updated

        return TutorBotSecurityDecision(
            blocked=False,
            level="sanitized" if signals else "safe",
            signals=tuple(dict.fromkeys(signals)),
            content=sanitized,
        )

    @classmethod
    def guard_output(cls, text: str | None) -> TutorBotSecurityDecision:
        content = "" if text is None else str(text)
        if not content:
            return TutorBotSecurityDecision(blocked=False, level="safe", content=content)

        signals = [
            group.signal
            for group in cls._OUTPUT_LEAK_GROUPS
            if cls._matches_group(content, group)
        ]
        if signals:
            return TutorBotSecurityDecision(
                blocked=True,
                level="high",
                signals=tuple(dict.fromkeys(signals)),
                content=INTERNAL_INFO_REFUSAL_ZH,
            )

        if looks_like_unsafe_visible_output(content):
            return TutorBotSecurityDecision(
                blocked=True,
                level="high",
                signals=("unsafe_visible_output",),
                content=coerce_user_visible_answer(content),
            )

        if any(marker in content for marker in cls._REFUSAL_MARKERS):
            return TutorBotSecurityDecision(blocked=False, level="safe", content=content)

        return TutorBotSecurityDecision(blocked=False, level="safe", content=content)
