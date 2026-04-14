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
        return "\n".join(
            [
                "## 身份信息",
                f"- 学员ID：{_display(profile.get('user_id'))}",
                f"- 昵称：{_display(profile.get('display_name') or profile.get('username'))}",
                f"- 会员等级：{_display(profile.get('tier'))}",
                f"- 账号状态：{_display(profile.get('status'))}",
                "",
                "## 学习偏好",
                f"- 难度偏好：{_display(profile.get('difficulty_preference'))}",
                f"- 讲解风格：{_display(profile.get('explanation_style'))}",
                f"- 每日目标：{_display(profile.get('daily_target'), suffix='题/次')}",
                f"- 复习提醒：{_display_bool(profile.get('review_reminder'))}",
                "",
                "## 当前学习基线",
                f"- 当前等级：{_display(profile.get('level'))}",
                f"- 积分余额：{_display(profile.get('points'))}",
                f"- 考试日期：{_display(profile.get('exam_date'))}",
                f"- 当前聚焦：{_display(profile.get('focus_topic'))}",
            ]
        ).strip()

    @staticmethod
    def _render_persona(profile: dict[str, Any]) -> str:
        focus_topic = _display(profile.get("focus_topic"), fallback="当前主线知识点")
        return "\n".join(
            [
                "## 角色定位",
                f"- 你是该学员的专属 TutorBot，要围绕 {focus_topic} 与考试目标持续陪学。",
                "- 语气专业、耐心、直接，优先给出能马上执行的下一步。",
                "",
                "## 讲解策略",
                f"- 默认匹配该学员的难度偏好：{_display(profile.get('difficulty_preference'))}。",
                f"- 默认匹配该学员的讲解风格：{_display(profile.get('explanation_style'))}。",
                "- 先判断用户是在学概念、做题、复盘错题，还是需要学习规划，再选择解释粒度。",
                "- 如果学员只给出很短的回答，优先把它解释为学习任务中的追问或答题，而不是闲聊。",
                "",
                "## 教学边界",
                "- 记忆只属于当前学员，不要引用其他学员信息。",
                "- 长期记忆只保留稳定偏好、学习进展、典型误区和下一次可接续的上下文。",
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
