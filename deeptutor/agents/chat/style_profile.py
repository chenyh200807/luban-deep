from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path


_STYLE_DIR = Path(__file__).resolve().parent / "prompt_layers"
_DEFAULT_PROFILE = "default"
_LUBAN_PROFILE = "luban_zhikao"


def get_chat_style_profile() -> str:
    profile = str(os.getenv("CHAT_STYLE_PROFILE", _DEFAULT_PROFILE) or "").strip().lower()
    return profile or _DEFAULT_PROFILE


def is_luban_chat_style_enabled() -> bool:
    return get_chat_style_profile() == _LUBAN_PROFILE


@lru_cache(maxsize=16)
def _load_layer(language: str, name: str) -> str:
    lang = "zh" if str(language).lower().startswith("zh") else "en"
    candidates = [
        _STYLE_DIR / lang / f"{name}.md",
        _STYLE_DIR / "zh" / f"{name}.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return ""


def build_luban_responding_prompt(language: str, brand_name: str, tool_list: str) -> str:
    identity = _load_layer(language, "identity")
    policy = _load_layer(language, "teaching_policy")
    guard_rails = _load_layer(language, "guard_rails")
    if str(language).lower().startswith("zh"):
        parts = [
            f"你是 {brand_name} 的最终回答阶段，也是建筑实务备考场景中的私人导师。",
            "你只负责输出给学员看的正式回答，不暴露内部 pipeline、thinking、tool trace 或观察过程。",
            "当 observation、RAG 和工具结果已经提供证据时，把它们自然融入回答，不要机械复述来源块。",
            "如果证据不足，必须明确说清当前依据不足，但仍先给出最有帮助的结论、判断路径或备考建议。",
            "如果用户当前问题里给了具体案例锚点或对象原词（如楼层数、建筑类型、工程对象、题目设定），默认沿用该原词，不要自行缩写、泛化或换称呼。",
            "以下三层内容是本阶段的最高优先级风格与约束，请严格遵守。",
            "【身份层】",
            identity,
            "【教学策略层】",
            policy,
            "【输出护栏层】",
            guard_rails,
        ]
        if tool_list.strip():
            parts.extend(["【本轮工具背景】", tool_list])
        return "\n\n".join(part for part in parts if part)

    parts = [
        f"You are the final response stage for {brand_name} and a private tutor for the Construction Practice exam.",
        "Only produce the final user-facing answer. Do not expose internal pipeline stages, tool traces, or hidden reasoning.",
        "When observation, RAG, or tool outputs provide evidence, integrate them naturally instead of copying raw traces.",
        "If evidence is incomplete, say so explicitly while still giving the most useful current answer, judgment path, or exam advice.",
        "If the current user request includes a concrete case anchor or exact object wording such as floor count, building type, project object, or problem setup, preserve that wording instead of shortening or renaming it.",
        "The following layers define the required persona, teaching policy, and output constraints for this stage.",
        "[Identity Layer]",
        identity,
        "[Teaching Policy Layer]",
        policy,
        "[Guard Rails Layer]",
        guard_rails,
    ]
    if tool_list.strip():
        parts.extend(["[Tool Context]", tool_list])
    return "\n\n".join(part for part in parts if part)


def build_luban_thinking_prompt(language: str, brand_name: str, tool_list: str) -> str:
    identity = _load_layer(language, "identity")
    policy = _load_layer(language, "teaching_policy")
    if str(language).lower().startswith("zh"):
        parts = [
            f"你是 {brand_name} 的 thinking 阶段，服务于建筑实务备考场景。",
            "这里不是最终回答区，而是内部规划区。你要先判断用户真正想解决什么、应该先给什么结论、哪些证据必须补齐。",
            "优先遵守以下内部规划原则：",
            "- 默认以结论先行为目标来规划最终回答结构。",
            "- 遇到概念、规范、案例、做题类问题，优先提炼判断依据、得分点、易错点。",
            "- 如果用户问题发散，先把问题收敛成 2 到 4 个关键点。",
            "- 只有当信息缺口明显时，才为后续工具调用做规划。",
            "- 不要在 thinking 阶段写成长篇教学成品，只输出简洁的内部思路。",
            "【身份层参考】",
            identity,
            "【教学策略层参考】",
            policy,
        ]
        if tool_list.strip():
            parts.extend(["【当前启用工具】", tool_list])
        return "\n\n".join(part for part in parts if part)

    parts = [
        f"You are the thinking stage for {brand_name} in the Construction Practice exam setting.",
        "This is internal planning, not the final answer. Decide what the user truly needs, what conclusion should appear first, and what evidence is still missing.",
        "Follow these planning rules:",
        "- Plan toward a conclusion-first final answer by default.",
        "- For concept, standard, case, and exam questions, extract judgment basis, scoring points, and traps first.",
        "- If the user asks in a scattered way, compress the problem into a few key points before planning further.",
        "- Only plan tool use when there is a real information gap.",
        "- Keep the reasoning concise; do not draft the full teaching answer here.",
        "[Identity Layer Reference]",
        identity,
        "[Teaching Policy Layer Reference]",
        policy,
    ]
    if tool_list.strip():
        parts.extend(["[Enabled Tools]", tool_list])
    return "\n\n".join(part for part in parts if part)
