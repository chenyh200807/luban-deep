from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

from deeptutor.services.taxonomy.taxonomy_authority import normalize_taxonomy_code

TEXTBOOK_CHAPTERS: tuple[dict[str, Any], ...] = (
    {
        "no": 1,
        "name": "建筑工程设计技术",
        "sections": (
            "建筑物的构成与设计要求",
            "建筑构造设计的基本要求",
            "建筑结构体系和设计作用（荷载）",
            "建筑结构设计构造基本要求",
            "装配式建筑设计基本要求",
        ),
        "code_prefixes": ("1A411",),
        "aliases": ("建筑设计与构造", "建筑设计", "建筑物分类与构成", "建筑构造设计要求"),
        "section_aliases": {"建筑构造": "建筑构造设计的基本要求"},
    },
    {
        "no": 2,
        "name": "主要建筑工程材料的性能与应用",
        "sections": ("结构工程材料", "装饰装修工程材料", "建筑功能材料"),
        "code_prefixes": ("1A412",),
        "aliases": ("建筑工程材料",),
    },
    {
        "no": 3,
        "name": "建筑工程施工技术",
        "sections": (
            "施工测量",
            "土石方工程施工",
            "地基与基础工程施工",
            "主体结构工程施工",
            "屋面与防水工程施工",
            "装饰装修工程施工",
            "智能建造新技术",
            "季节性施工技术",
        ),
        "code_prefixes": ("1A413",),
        "aliases": ("建筑工程施工技术",),
        "section_aliases": {
            "防水工程": "屋面与防水工程施工",
            "地下防水": "屋面与防水工程施工",
            "装饰装修": "装饰装修工程施工",
            "地基基础": "地基与基础工程施工",
            "主体结构": "主体结构工程施工",
        },
    },
    {
        "no": 4,
        "name": "相关法规",
        "sections": ("建筑工程建设相关规定", "安全生产及施工现场管理相关规定"),
        "code_prefixes": ("1A421", "1A422"),
        "aliases": (),
    },
    {
        "no": 5,
        "name": "相关标准",
        "sections": (
            "建筑设计及质量控制相关规定",
            "地基基础工程相关规定",
            "主体结构工程相关规定",
            "装饰装修与屋面工程相关规定",
            "绿色建造的相关规定",
        ),
        "code_prefixes": ("1A425",),
        "aliases": (),
    },
    {
        "no": 6,
        "name": "建筑工程企业资质与施工组织",
        "sections": (
            "建筑工程企业资质",
            "施工项目管理机构",
            "施工组织设计",
            "施工平面布置",
            "施工临时用电",
            "施工临时用水",
            "施工检验与试验",
            "工程施工资料",
        ),
        "code_prefixes": ("1A431",),
        "aliases": (),
    },
    {
        "no": 7,
        "name": "工程招标投标与合同管理",
        "sections": ("工程招标投标", "工程合同管理"),
        "code_prefixes": ("1A432",),
        "aliases": ("招投标与合同", "合同索赔", "合同管理", "索赔"),
    },
    {
        "no": 8,
        "name": "施工进度管理",
        "sections": ("施工进度控制方法应用", "施工进度计划编制与控制"),
        "code_prefixes": ("1A433",),
        "aliases": ("进度计划", "流水施工", "网络计划"),
    },
    {
        "no": 9,
        "name": "施工质量管理",
        "sections": (
            "项目质量计划管理",
            "项目施工质量检查与检验",
            "工程质量通病防治",
            "工程质量验收管理",
        ),
        "code_prefixes": ("1A434",),
        "aliases": ("质量验收",),
    },
    {
        "no": 10,
        "name": "施工成本管理",
        "sections": ("施工成本计划及分解", "施工成本分析与控制", "施工成本管理绩效评价与考核"),
        "code_prefixes": ("1A435",),
        "aliases": (),
    },
    {
        "no": 11,
        "name": "施工安全管理",
        "sections": (
            "施工安全生产管理计划",
            "施工安全生产检查",
            "施工安全生产管理要点",
            "常见施工生产安全事故及预防",
        ),
        "code_prefixes": ("1A436",),
        "aliases": (),
    },
    {
        "no": 12,
        "name": "绿色建造及施工现场环境管理",
        "sections": ("绿色建造及信息化技术应用管理", "绿色施工及环境保护", "施工现场消防"),
        "code_prefixes": ("1A437",),
        "aliases": (),
    },
    {
        "no": 13,
        "name": "施工资源管理",
        "sections": ("材料与半成品管理", "机械设备管理", "劳动用工管理"),
        "code_prefixes": ("1A438",),
        "aliases": (),
    },
)

_NON_TOPIC_LABELS = {
    "这题",
    "那题",
    "本题",
    "该题",
    "此题",
    "题目",
    "当前题",
    "当前题目",
    "这个题",
    "那个题",
    "这道题",
    "那道题",
    "这一题",
    "那一题",
    "这道题目",
    "那道题目",
    "当前考点",
    "当前知识点",
    "考卷",
    "试卷",
    "卷子",
    "综合练习",
    "练习证据",
}

_NON_TOPIC_PATTERNS = (
    re.compile(r"(讲义|资料|教材).{0,8}(封面|封底|页眉|页脚)"),
    re.compile(r"(免费|领取|扫码|二维码|公众号|听课|课程|网课|资料包|加微信)"),
    re.compile(r"(一级建造师|一建|建筑实务).{0,12}(主题归纳|知识点归纳|思维导图|考点汇总|复习资料)"),
)


# Distinctive non-textbook substrings (book front/back matter + marketing/lead-gen). Substring match on
# the compacted label. Kept high-precision on purpose: every marker below would be absurd inside a real
# 一建《建筑实务》knowledge-point name, so this cannot drop a legitimate topic. Do NOT add generic words
# like 资源/课程/资料/管理/技术 — those DO occur in real topics (e.g. 建设工程项目资源管理).
_NON_TEXTBOOK_NOISE_MARKERS = (
    "讲义", "封底", "封面", "扉页", "版权", "前言", "序言", "后记", "目录页",
    "免费", "听课", "试听", "试看", "扫码", "二维码", "公众号", "关注", "客服",
    "报名", "网址", "直播", "回放", "押题", "赠送", "领取", "增值服务", "课程咨询",
    "微信号", "qq群", "vip", "优惠", "促销", "广告",
    # meta / book-title / non-knowledge-point phrasings (e.g. "一级建造师建筑实务学习主题归纳")
    "建造师", "主题归纳", "学习主题", "知识点归纳", "考点汇总", "思维导图", "学习方法",
)


def canonical_topic_options() -> list[dict[str, Any]]:
    """The FIXED canonical option set a topic recommendation may be classified into: every chapter and
    section of the 一建《建筑实务》 outline, each carrying its chapter code prefix. Small (~13 chapters +
    ~60 sections) so an LLM classifier can pick reliably, and every option is canonical by construction."""
    options: list[dict[str, Any]] = []
    for chapter in TEXTBOOK_CHAPTERS:
        code = str((chapter.get("code_prefixes") or ("",))[0])
        options.append({"name": str(chapter["name"]), "code": code,
                        "kind": "chapter", "chapter_no": int(chapter["no"])})
        for section in chapter.get("sections") or ():
            options.append({"name": str(section), "code": code,
                            "kind": "section", "chapter_no": int(chapter["no"])})
    return options


@lru_cache(maxsize=1)
def _canonical_option_index() -> dict[str, dict[str, Any]]:
    """compact(name/alias) -> option, for EXACT validation of a classifier's pick (no fuzzy)."""
    index: dict[str, dict[str, Any]] = {}
    for opt in canonical_topic_options():
        index.setdefault(_compact(opt["name"]), opt)
    for chapter in TEXTBOOK_CHAPTERS:
        code = str((chapter.get("code_prefixes") or ("",))[0])
        for alias in chapter.get("aliases") or ():
            index.setdefault(_compact(alias),
                             {"name": str(chapter["name"]), "code": code,
                              "kind": "chapter", "chapter_no": int(chapter["no"])})
        section_aliases = chapter.get("section_aliases") or {}
        if isinstance(section_aliases, dict):
            sections = {str(section) for section in chapter.get("sections") or ()}
            for alias, section in section_aliases.items():
                section_name = str(section or "")
                if section_name in sections:
                    index.setdefault(
                        _compact(alias),
                        {
                            "name": section_name,
                            "code": code,
                            "kind": "section",
                            "chapter_no": int(chapter["no"]),
                        },
                    )
    return index


def resolve_canonical_option(label: Any) -> dict[str, Any] | None:
    """EXACT-match a label to a canonical chapter/section option (or chapter alias). Returns the option
    {name, code, kind, chapter_no} or None. No fuzzy matching — used to validate that an LLM classifier
    picked a real option from the fixed list, so a recommendation is provably on-canonical."""
    return _canonical_option_index().get(_compact(label))


def textbook_chapter_display_name(chapter: dict[str, Any]) -> str:
    return f"第{int(chapter['no'])}章 {chapter['name']}"


def textbook_directory() -> tuple[dict[str, Any], ...]:
    return TEXTBOOK_CHAPTERS


def is_non_topic_label(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    compact = _compact(text)
    if compact in _NON_TOPIC_LABELS:
        return True
    # textbook OCR front/back-matter + marketing noise (讲义封底 / 免费听课 / 扫码二维码 ...) is NOT a
    # knowledge point and must never surface as a learner topic. Distinctive markers only — none appear in
    # a real 一建 knowledge-point name (deliberately excludes 资源/课程/资料/管理 which DO appear in topics).
    if any(marker in compact.lower() for marker in _NON_TEXTBOOK_NOISE_MARKERS):
        return True
    if any(pattern.search(compact) for pattern in _NON_TOPIC_PATTERNS):
        return True
    if "/" in text or "／" in text:
        return True
    code = normalize_taxonomy_code(text)
    return _looks_like_taxonomy_code(code) and _chapter_by_code(code) is None


def textbook_topic_meta(
    *,
    raw_value: Any = "",
    label: Any = "",
    path_names: list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    code = normalize_taxonomy_code(raw_value)
    label_text = str(label or "").strip()
    path = [str(item or "").strip() for item in list(path_names or []) if str(item or "").strip()]
    if is_non_topic_label(label_text):
        return {}
    if code and _looks_like_taxonomy_code(code) and _chapter_by_code(code) is None:
        return {}

    chapter = _chapter_by_code(code) if code else None
    section = _section_for_label(label_text, chapter)
    if chapter is None:
        for candidate in [label_text, *path]:
            chapter = _chapter_by_label(candidate)
            if chapter:
                section = _section_for_label(candidate, chapter) or section
                break
    if chapter is None:
        return {}

    chapter_name = textbook_chapter_display_name(chapter)
    result: dict[str, Any] = {
        "textbook_chapter_no": int(chapter["no"]),
        "textbook_chapter_name": chapter_name,
    }
    if section:
        result["textbook_section_name"] = section
    return result


def _chapter_by_code(code: str) -> dict[str, Any] | None:
    normalized = normalize_taxonomy_code(code)
    if not normalized:
        return None
    for chapter in TEXTBOOK_CHAPTERS:
        if any(normalized.startswith(prefix) for prefix in chapter["code_prefixes"]):
            return chapter
    return None


def _chapter_by_label(value: Any) -> dict[str, Any] | None:
    compact = _strip_number_prefix(_compact(value))
    if not compact:
        return None
    for chapter in TEXTBOOK_CHAPTERS:
        names = [chapter["name"], textbook_chapter_display_name(chapter), *chapter["sections"], *chapter["aliases"]]
        if compact in {_strip_number_prefix(_compact(name)) for name in names}:
            return chapter
    return None


def _section_for_label(value: Any, chapter: dict[str, Any] | None) -> str:
    if not chapter:
        return ""
    compact = _strip_number_prefix(_compact(value))
    for section in chapter["sections"]:
        if compact == _strip_number_prefix(_compact(section)):
            return str(section)
    return ""


def _looks_like_taxonomy_code(value: str) -> bool:
    return bool(re.fullmatch(r"1A\d{3,6}(?:-\d+)?(?:-[a-z]+)?", str(value or ""), flags=re.IGNORECASE))


def _compact(value: Any) -> str:
    return re.sub(r"[\s　，,。.!！?？:：;；“”\"'‘’（）()【】\[\]<>《》]+", "", str(value or "").strip())


def _strip_number_prefix(value: str) -> str:
    return re.sub(r"^(?:第?\d+章)?\d+(?:\.\d+)?", "", value)


__all__ = [
    "TEXTBOOK_CHAPTERS",
    "canonical_topic_options",
    "is_non_topic_label",
    "resolve_canonical_option",
    "textbook_chapter_display_name",
    "textbook_directory",
    "textbook_topic_meta",
]
