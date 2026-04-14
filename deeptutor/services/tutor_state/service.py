from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from deeptutor.services.llm import stream as llm_stream
from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.path_service import PathService, get_path_service

TutorStateFile = Literal["profile", "persona", "memory"]
_NO_CHANGE = "NO_CHANGE"
_FILENAMES: dict[TutorStateFile, str] = {
    "profile": "PROFILE.md",
    "persona": "PERSONA.md",
    "memory": "MEMORY.md",
}


@dataclass
class TutorStateSnapshot:
    user_id: str
    profile: str
    persona: str
    memory: str
    profile_updated_at: str | None
    persona_updated_at: str | None
    memory_updated_at: str | None


@dataclass
class TutorStateUpdateResult:
    content: str
    changed: bool
    updated_at: str | None


class UserTutorStateService:
    """Persist per-user tutor state and lazily inject it into shared turns."""

    def __init__(
        self,
        path_service: PathService | None = None,
        member_service: Any | None = None,
    ) -> None:
        self._path_service = path_service or get_path_service()
        self._member_service = member_service or get_member_console_service()
        self._locks: dict[str, asyncio.Lock] = {}

    def _user_dir(self, user_id: str) -> Path:
        normalized = _normalize_user_id(user_id)
        return self._path_service.get_tutor_state_root() / normalized

    def _path(self, user_id: str, which: TutorStateFile) -> Path:
        return self._user_dir(user_id) / _FILENAMES[which]

    def _file_updated_at(self, user_id: str, which: TutorStateFile) -> str | None:
        path = self._path(user_id, which)
        if not path.exists():
            return None
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
        except Exception:
            return None

    def read_file(self, user_id: str, which: TutorStateFile) -> str:
        self._sync_static_state(user_id)
        path = self._path(user_id, which)
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def read_snapshot(self, user_id: str) -> TutorStateSnapshot:
        normalized = _normalize_user_id(user_id)
        self._sync_static_state(normalized)
        return TutorStateSnapshot(
            user_id=normalized,
            profile=self.read_file(normalized, "profile"),
            persona=self.read_file(normalized, "persona"),
            memory=self.read_file(normalized, "memory"),
            profile_updated_at=self._file_updated_at(normalized, "profile"),
            persona_updated_at=self._file_updated_at(normalized, "persona"),
            memory_updated_at=self._file_updated_at(normalized, "memory"),
        )

    def build_context(
        self,
        user_id: str,
        *,
        language: str = "zh",
        max_chars: int = 5000,
    ) -> str:
        snapshot = self.read_snapshot(user_id)
        parts: list[str] = []
        if snapshot.persona:
            parts.append(f"### Tutor Persona\n{snapshot.persona}")
        if snapshot.profile:
            parts.append(f"### Student Profile\n{snapshot.profile}")
        if snapshot.memory:
            parts.append(f"### Long-Term Tutor Memory\n{snapshot.memory}")
        if not parts:
            return ""
        combined = "\n\n".join(parts)
        if len(combined) > max_chars:
            combined = combined[:max_chars].rstrip() + "\n...[truncated]"
        if str(language).lower().startswith("zh"):
            return (
                "## 专属 Tutor 上下文\n"
                "以下内容属于当前学员的长期状态。仅在相关时使用，避免泄露或误用到其他学员。\n\n"
                f"{combined}"
            )
        return (
            "## Dedicated Tutor Context\n"
            "This state belongs to the current learner only. Use it only when relevant.\n\n"
            f"{combined}"
        )

    async def refresh_from_turn(
        self,
        *,
        user_id: str,
        user_message: str,
        assistant_message: str,
        session_id: str = "",
        capability: str = "",
        language: str = "zh",
        timestamp: str = "",
    ) -> TutorStateUpdateResult:
        normalized = _normalize_user_id(user_id)
        self._sync_static_state(normalized)
        snapshot = self.read_snapshot(normalized)
        if not user_message.strip() or not assistant_message.strip():
            return TutorStateUpdateResult(
                content=snapshot.memory,
                changed=False,
                updated_at=snapshot.memory_updated_at,
            )

        async with self._locks.setdefault(normalized, asyncio.Lock()):
            source = (
                f"[User Profile]\n{snapshot.profile or '(empty)'}\n\n"
                f"[Tutor Persona]\n{snapshot.persona or '(empty)'}\n\n"
                f"[Session] {session_id or '(unknown)'}\n"
                f"[Capability] {capability or 'chat'}\n"
                f"[Timestamp] {timestamp or datetime.now().isoformat()}\n\n"
                f"[User]\n{user_message.strip()}\n\n"
                f"[Assistant]\n{assistant_message.strip()}"
            )
            changed = await self._rewrite_memory(normalized, source, language)
            updated = self.read_snapshot(normalized)
            return TutorStateUpdateResult(
                content=updated.memory,
                changed=changed,
                updated_at=updated.memory_updated_at,
            )

    async def _rewrite_memory(self, user_id: str, source: str, language: str) -> bool:
        current = self.read_file(user_id, "memory")
        zh = str(language).lower().startswith("zh")
        sys_prompt, user_prompt = self._memory_prompts(current, source, zh)

        chunks: list[str] = []
        async for chunk in llm_stream(
            prompt=user_prompt,
            system_prompt=sys_prompt,
            temperature=0.2,
            max_tokens=900,
        ):
            chunks.append(chunk)

        rewritten = _strip_code_fence("".join(chunks)).strip()
        if not rewritten or rewritten == _NO_CHANGE or rewritten == current:
            return False

        self._write_file(user_id, "memory", rewritten)
        return True

    def _sync_static_state(self, user_id: str) -> None:
        profile = self._safe_member_profile(user_id)
        self._write_if_changed(user_id, "profile", self._render_profile(profile))
        self._write_if_changed(user_id, "persona", self._render_persona(profile))

        memory_path = self._path(user_id, "memory")
        if not memory_path.exists():
            seed = self._seed_memory(profile)
            if seed:
                self._write_file(user_id, "memory", seed)

    def _safe_member_profile(self, user_id: str) -> dict[str, Any]:
        try:
            profile = dict(self._member_service.get_profile(user_id) or {})
        except Exception:
            profile = {"user_id": user_id, "display_name": user_id}
        profile.setdefault("user_id", user_id)
        profile.setdefault("display_name", user_id)
        return profile

    def _write_if_changed(self, user_id: str, which: TutorStateFile, content: str) -> None:
        if self.read_file_raw(user_id, which) == content.strip():
            return
        self._write_file(user_id, which, content)

    def _write_file(self, user_id: str, which: TutorStateFile, content: str) -> None:
        path = self._path(user_id, which)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content or "").strip(), encoding="utf-8")

    def read_file_raw(self, user_id: str, which: TutorStateFile) -> str:
        path = self._path(user_id, which)
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    @staticmethod
    def _render_profile(profile: dict[str, Any]) -> str:
        display_name = _preferred_display_name(profile)
        nickname_status = "已确认专属称呼" if _has_stable_display_name(profile) else "称呼待进一步确认"
        urgency = _exam_urgency_hint(profile.get("exam_date"))
        level_hint = _level_hint(profile.get("level"))
        return "\n".join(
            [
                "## 学员识别",
                f"- 学员ID：{_display(profile.get('user_id'))}",
                f"- 当前称呼：{display_name}",
                f"- 称呼状态：{nickname_status}",
                (
                    f"- 称呼使用建议：回答开头可自然称呼“{display_name}”，"
                    "但不要在每段重复称呼。"
                    if _has_stable_display_name(profile)
                    else "- 称呼使用建议：当前先用自然中性称呼；若合适，后续可确认用户更希望被怎么称呼。"
                ),
                "",
                "## 备考主线",
                "- 默认场景：建筑工程类考试与《建筑工程管理与实务》学习",
                f"- 会员等级：{_display(profile.get('tier'))}",
                f"- 账号状态：{_display(profile.get('status'))}",
                f"- 考试日期：{_display(profile.get('exam_date'))}",
                f"- 备考紧迫度：{urgency}",
                f"- 当前聚焦：{_display(profile.get('focus_topic'))}",
                f"- 当前目标提问：{_display(profile.get('focus_query'))}",
                "",
                "## 学习偏好",
                f"- 难度偏好：{_difficulty_label(profile.get('difficulty_preference'))}",
                f"- 讲解风格：{_explanation_style_label(profile.get('explanation_style'))}",
                f"- 每日目标：{_display(profile.get('daily_target'), suffix='题/次')}",
                f"- 复习提醒：{_display_bool(profile.get('review_reminder'))}",
                "",
                "## 当前学习判断",
                f"- 当前等级：{_display(profile.get('level'))}",
                f"- 基础判断：{level_hint}",
                f"- 积分余额：{_display(profile.get('points'))}",
                (
                    "- 当前支持重点：先稳住节奏，再围绕当前聚焦专题持续推进。"
                    if str(profile.get("focus_topic") or "").strip()
                    else "- 当前支持重点：先帮助学员确认最近最值得投入的一个专题。"
                ),
            ]
        ).strip()

    @staticmethod
    def _render_persona(profile: dict[str, Any]) -> str:
        focus_topic = _display(profile.get("focus_topic"), fallback="当前主线知识点")
        display_name = _preferred_display_name(profile)
        difficulty = _difficulty_label(profile.get("difficulty_preference"))
        explanation_style = _explanation_style_label(profile.get("explanation_style"))
        level_hint = _level_hint(profile.get("level"))
        urgency = _exam_urgency_hint(profile.get("exam_date"))
        return "\n".join(
            [
                "## 角色定位",
                "- 你是该学员的专属 TutorBot，需要把长期陪学关系和当下这次答题同时兼顾。",
                "- 你是鲁班智考中的建筑实务备考导师，回答时保持专业教师风格，但不要自称具体真人姓名。",
                f"- 你要围绕 {focus_topic} 与考试目标持续陪学，优先帮助学员把题做对、把分拿稳、把同类题学会。",
                "- 你不是泛泛答疑助手，而是长期陪学型建筑实务导师。",
                "- 你不仅解决知识问题，也要提供稳定、克制、可信的心理支持。",
                "- 一个关键目标是让学员感到：你真的懂他现在卡在哪、怕什么、下一步最该做什么。",
                "",
                "## 核心原则",
                "- 结论先行：先给答案、判断或结论，再解释原因。",
                "- 面向拿分：讲知识时要落到考点、判定依据、踩分点、易错点。",
                "- 说人话：用通俗语言解释规范逻辑，不堆空泛定义。",
                "- 先帮做对，再帮学会：先解决当前问题，再补同类题抓手。",
                "- 先理解人，再处理题：若学员明显焦虑、挫败、拖延、自责，先接住状态，再推进学习动作。",
                "",
                "## 当前学员画像",
                f"- 当前称呼：{display_name}",
                (
                    f"- 默认可自然使用称呼“{display_name}”开场，建立被理解感，但不要高频重复。"
                    if _has_stable_display_name(profile)
                    else "- 当前还没有稳定专属称呼；合适时可自然确认“我之后怎么称呼你更顺手？”。"
                ),
                f"- 当前基础判断：{level_hint}",
                f"- 当前难度偏好：{difficulty}",
                f"- 当前讲解风格：{explanation_style}",
                f"- 当前备考紧迫度：{urgency}",
                "",
                "## 回答合同",
                "- 优先让学员感觉自己被看见，而不是只被答题。",
                "- 如果已知学员的目标、情绪、薄弱点、时间压力，要在回答中自然体现这些信息。",
                "- 不做模板化共情，不说空泛鸡汤，要用有识别感的话指出他真正卡住的点。",
                "- 默认回答顺序：先结论；必要时先接住情绪；再讲依据；再给易错边界或答题骨架；最后给一个最小可执行下一步。",
                "",
                "## 讲解策略",
                f"- 默认匹配该学员的难度偏好：{difficulty}。",
                f"- 默认匹配该学员的讲解风格：{explanation_style}。",
                "- 先判断用户是在学概念、做题、复盘错题，还是需要学习规划，再选择解释粒度和回答结构。",
                "- 如果学员只给出很短的回答，优先把它解释为学习任务中的追问或答题，而不是闲聊。",
                "- 案例题、实务题优先给作答骨架，再补教学说明。",
                "- 用户术语不准、表达很脏、只说半句时，优先结合上下文补全意图，不先挑术语错误。",
                "- 索赔、工期、责任、质量、安全、验收类问题默认不要答死，要把成立前提、边界和误判点说清。",
                "- 若学员反复在同类点出错，要主动指出“你不是全不会，而是卡在这个判定点”。",
                "- 若学员时间紧、压力大，要主动帮他做取舍，而不是把整套知识都摊给他。",
                "",
                "## 心理支持策略",
                "- 心理支持不是喊口号，而是理解处境、降低负担、给出下一步。",
                "- 学员慌乱时，先缩小问题；学员自责时，先拆出具体卡点；学员拖延时，先给最小动作。",
                "- 安慰要少而准，重点是让学员感到被理解、被接住、被带着往前走。",
                "",
                "## 专业约束",
                "- 涉及规范数值、时限、比例、强度、间距、程序门槛等具体事实时，优先依赖知识库、检索或已有证据。",
                "- 证据不足时，不编造规范编号，不伪造精确条文，不捏造参数。",
                "- 可以给通用判断逻辑，但不要把经验说成已核实事实。",
                "",
                "## 沟通边界",
                "- 语气专业、直接、稳，默认用陈述句收尾，不强行追问。",
                "- 记忆只属于当前学员，不要引用其他学员信息。",
                "- 长期记忆只保留稳定偏好、学习进展、典型误区和下一次可接续的上下文。",
                "- 不说“作为 AI”“根据提示词”“我被设计成”，不暴露内部工具、检索链路和系统机制。",
            ]
        ).strip()

    @staticmethod
    def _seed_memory(profile: dict[str, Any]) -> str:
        focus_topic = _display(profile.get("focus_topic"), fallback="待确认")
        return "\n".join(
            [
                "## 当前主线",
                f"- 当前聚焦：{focus_topic}",
                f"- 考试日期：{_display(profile.get('exam_date'))}",
                f"- 每日目标：{_display(profile.get('daily_target'), suffix='题/次')}",
                "",
                "## 已知偏好",
                f"- 难度：{_display(profile.get('difficulty_preference'))}",
                f"- 讲解方式：{_display(profile.get('explanation_style'))}",
                "",
                "## 待持续观察",
                "- 常错点、易混点、已经掌握的题型、下次建议跟进的练习。",
            ]
        ).strip()

    @staticmethod
    def _memory_prompts(current: str, source: str, zh: bool) -> tuple[str, str]:
        if zh:
            return (
                "你负责维护当前学员专属 Tutor 的长期记忆。"
                "只保留跨回合仍有价值的学习状态、稳定偏好、典型误区、进展和下次跟进建议。"
                f"如果无需修改，请只返回 {_NO_CHANGE}。",
                "如果需要更新，请重写长期记忆，可使用以下标题：\n"
                "## Current Focus\n## Progress Signals\n## Misconceptions To Watch\n## Next Follow-Up\n\n"
                "规则：保持简短；删除寒暄、一次性回答和过时信息；不要泄露其他学员信息。\n\n"
                f"[当前长期记忆]\n{current or '(empty)'}\n\n"
                f"[新增材料]\n{source}"
            )
        return (
            "You maintain the dedicated tutor memory for one learner. "
            "Keep only durable learning state, stable preferences, misconceptions, progress, "
            f"and the next useful follow-up. If nothing should change, return exactly {_NO_CHANGE}.",
            "Rewrite the long-term tutor memory if needed. Suggested sections:\n"
            "## Current Focus\n## Progress Signals\n## Misconceptions To Watch\n## Next Follow-Up\n\n"
            "Rules: keep it short, remove stale or transient chatter, never mix other learners.\n\n"
            f"[Current memory]\n{current or '(empty)'}\n\n"
            f"[New material]\n{source}"
        )


def _normalize_user_id(user_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(user_id or "").strip())
    if not cleaned:
        raise ValueError("user_id is required")
    return cleaned[:120]


def _strip_code_fence(content: str) -> str:
    cleaned = str(content or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _display(value: Any, *, fallback: str = "未设置", suffix: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return f"{text}{suffix}" if suffix else text


def _display_bool(value: Any) -> str:
    return "开启" if bool(value) else "关闭"


def _preferred_display_name(profile: dict[str, Any]) -> str:
    display_name = str(profile.get("display_name") or profile.get("username") or "").strip()
    if display_name:
        return display_name
    return "这位学员"


def _has_stable_display_name(profile: dict[str, Any]) -> bool:
    display_name = str(profile.get("display_name") or profile.get("username") or "").strip()
    user_id = str(profile.get("user_id") or "").strip()
    if not display_name:
        return False
    generic_prefixes = ("用户", "学员", "微信用户")
    if user_id and display_name == user_id:
        return False
    if display_name in {"用户", "同学", "学员"}:
        return False
    return not any(display_name.startswith(prefix) and len(display_name) <= 8 for prefix in generic_prefixes)


def _difficulty_label(value: Any) -> str:
    mapping = {
        "easy": "简单，先求做对与建立信心",
        "medium": "适中，兼顾做对与理解",
        "hard": "挑战，允许更强推理与迁移",
    }
    key = str(value or "").strip().lower()
    return mapping.get(key, _display(value))


def _explanation_style_label(value: Any) -> str:
    mapping = {
        "brief": "简洁，先给抓手和结论",
        "detailed": "详细，把逻辑讲透",
        "socratic": "启发式，引导学员自己推出关键判断",
    }
    key = str(value or "").strip().lower()
    return mapping.get(key, _display(value))


def _level_hint(value: Any) -> str:
    try:
        level = int(value or 0)
    except (TypeError, ValueError):
        return "基础待进一步观察"
    if level <= 3:
        return "基础偏弱，先稳住做题正确率与核心判断框架"
    if level <= 6:
        return "基础中等，重点补齐易错点并建立同类题迁移"
    if level <= 8:
        return "基础较好，可以在做对基础上强化案例题表达与综合判断"
    return "基础较强，可适当提高综合题与变式题训练强度"


def _exam_urgency_hint(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "考试时间未明确，默认按稳步推进处理"
    try:
        exam_date = datetime.fromisoformat(text).date()
    except ValueError:
        return "考试时间已设置，建议结合日期动态安排节奏"
    today = datetime.now().date()
    days = (exam_date - today).days
    if days < 0:
        return "考试日期已过，建议先确认新的备考节点"
    if days <= 30:
        return "考前冲刺期，优先稳住高频考点、案例题与错题复盘"
    if days <= 90:
        return "中短期备考期，重点建立专题框架并提高做题稳定性"
    return "长期备考期，可系统推进知识框架与专题训练"


_user_tutor_state_service: UserTutorStateService | None = None


def get_user_tutor_state_service() -> UserTutorStateService:
    global _user_tutor_state_service
    if _user_tutor_state_service is None:
        _user_tutor_state_service = UserTutorStateService()
    return _user_tutor_state_service


__all__ = [
    "TutorStateFile",
    "TutorStateSnapshot",
    "TutorStateUpdateResult",
    "UserTutorStateService",
    "get_user_tutor_state_service",
]
