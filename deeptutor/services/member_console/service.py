from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import string
import threading
import time
import urllib.parse
import urllib.request
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None

from deeptutor.services.member_console.external_auth import (
    create_external_auth_user,
    ensure_external_auth_user_for_phone,
    get_external_auth_user,
    verify_external_auth_user,
)
from deeptutor.services.path_service import get_path_service
from deeptutor.services.runtime_env import env_flag, is_production_environment
from deeptutor.services.session import get_sqlite_session_store

_TZ = timezone(timedelta(hours=8))
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(_TZ)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _parse_time(value: str | None) -> datetime:
    if not value:
        return _now()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return _now()


def _slugify_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[-11:] if digits else "13800000000"


def _normalize_phone_input(value: str | None) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 11:
        return ""
    return digits[-11:]


def _date_key(value: datetime | None = None) -> str:
    return (value or _now()).strftime("%Y-%m-%d")


def _default_chapter_mastery() -> dict[str, dict[str, Any]]:
    chapters = []
    seen = set()
    for item in _ASSESSMENT_BANK:
        chapter = str(item.chapter or "").strip()
        if not chapter or chapter in seen:
            continue
        seen.add(chapter)
        chapters.append(chapter)
    return {chapter: {"name": chapter, "mastery": 0} for chapter in chapters}


@dataclass(slots=True)
class _AssessmentTemplate:
    id: str
    chapter: str
    question: str
    options: dict[str, str]
    answer: str


_ASSESSMENT_BANK: list[_AssessmentTemplate] = [
    _AssessmentTemplate(
        id="q_foundation_1",
        chapter="建筑构造",
        question="建筑构造设计中，围护结构最核心的目标是？",
        options={
            "A": "只强调美观表达",
            "B": "满足安全、功能与耐久性要求",
            "C": "尽量减少施工工序",
            "D": "优先降低材料等级",
        },
        answer="B",
    ),
    _AssessmentTemplate(
        id="q_foundation_2",
        chapter="地基基础",
        question="地基承载力验算的核心关注点是？",
        options={
            "A": "装饰面层色差",
            "B": "结构传力后土体是否稳定",
            "C": "模板拆除顺序",
            "D": "钢筋下料速度",
        },
        answer="B",
    ),
    _AssessmentTemplate(
        id="q_waterproof_1",
        chapter="防水工程",
        question="屋面防水卷材施工前，基层应满足哪项要求？",
        options={
            "A": "含水率适宜且表面平整",
            "B": "先刷面漆再找平",
            "C": "可带明水直接铺贴",
            "D": "只要天气晴朗即可施工",
        },
        answer="A",
    ),
    _AssessmentTemplate(
        id="q_structure_1",
        chapter="主体结构",
        question="混凝土结构施工质量控制中，坍落度主要反映？",
        options={
            "A": "钢筋强度",
            "B": "混凝土工作性",
            "C": "模板刚度",
            "D": "砂率上限",
        },
        answer="B",
    ),
    _AssessmentTemplate(
        id="q_manage_1",
        chapter="施工管理",
        question="施工组织设计中，进度计划编制首先应明确？",
        options={
            "A": "营销预算",
            "B": "施工部署与关键线路",
            "C": "办公区装饰风格",
            "D": "材料颜色搭配",
        },
        answer="B",
    ),
]


class MemberConsoleService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._path_service = get_path_service()
        self._store = get_sqlite_session_store()
        self._data_path = self._path_service.get_settings_file("member_console")
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        self._wechat_access_token: str = ""
        self._wechat_access_token_expires_at: float = 0.0

    def _get_learner_state_service(self):
        from deeptutor.services.learner_state import get_learner_state_service

        return get_learner_state_service()

    def _get_overlay_service(self):
        from deeptutor.services.learner_state import get_bot_learner_overlay_service

        return get_bot_learner_overlay_service()

    @staticmethod
    def _default_packages() -> list[dict[str, Any]]:
        return [
            {"id": "starter", "points": 100, "price": "9.9", "badge": "", "per": ""},
            {"id": "standard", "points": 500, "price": "39", "badge": "热门", "per": "¥0.078/点"},
            {"id": "pro", "points": 1200, "price": "79", "badge": "", "per": "¥0.066/点"},
            {"id": "ultimate", "points": 3000, "price": "169", "badge": "SVIP", "per": "¥0.056/点"},
        ]

    @staticmethod
    def _empty_data() -> dict[str, Any]:
        return {
            "members": [],
            "packages": MemberConsoleService._default_packages(),
            "audit_log": [],
            "assessment_sessions": {},
            "phone_codes": {},
        }

    @staticmethod
    def _build_default_member(user_id: str) -> dict[str, Any]:
        now = _now()
        return {
            "user_id": user_id,
            "display_name": user_id,
            "phone": _slugify_phone(user_id),
            "tier": "trial",
            "status": "active",
            "segment": "general",
            "risk_level": "low",
            "auto_renew": False,
            "created_at": _iso(now),
            "last_active_at": _iso(now),
            "expire_at": _iso(now + timedelta(days=30)),
            "avatar_url": "",
            "points_balance": 120,
            "level": 1,
            "xp": 0,
            "study_days": 0,
            "review_due": 0,
            "focus_topic": "入门摸底",
            "focus_query": "帮我做一次入门摸底测试",
            "exam_date": "",
            "daily_target": 30,
            "difficulty_preference": "medium",
            "explanation_style": "detailed",
            "review_reminder": True,
            "earned_badge_ids": [],
            "chapter_mastery": _default_chapter_mastery(),
            "notes": [],
            "ledger": [],
            "daily_practice_counts": {},
            "chapter_practice_stats": {},
            "last_study_date": "",
            "last_practice_at": "",
        }

    def _bootstrap_data(self) -> dict[str, Any]:
        if self._demo_seed_enabled():
            return self._seed_data()
        return self._empty_data()

    @staticmethod
    def _demo_seed_enabled() -> bool:
        if is_production_environment():
            return False
        return env_flag("DEEPTUTOR_MEMBER_CONSOLE_ENABLE_DEMO_SEED", default=False)

    @staticmethod
    def _serialize_learner_memory_event(event: Any) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "source_feature": event.source_feature,
            "source_id": event.source_id,
            "source_bot_id": event.source_bot_id,
            "memory_kind": event.memory_kind,
            "payload_json": dict(event.payload_json or {}),
            "created_at": event.created_at,
        }

    @staticmethod
    def _serialize_learner_snapshot(snapshot: Any) -> dict[str, Any]:
        return {
            "user_id": snapshot.user_id,
            "available": True,
            "profile": dict(snapshot.profile or {}),
            "summary": str(snapshot.summary or ""),
            "progress": dict(snapshot.progress or {}),
            "recent_memory_events": [
                MemberConsoleService._serialize_learner_memory_event(event)
                for event in list(snapshot.memory_events or [])
            ],
            "profile_updated_at": snapshot.profile_updated_at,
            "summary_updated_at": snapshot.summary_updated_at,
            "progress_updated_at": snapshot.progress_updated_at,
            "memory_events_updated_at": snapshot.memory_events_updated_at,
        }

    @staticmethod
    def _empty_learner_snapshot_payload(user_id: str) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "available": False,
            "profile": {},
            "summary": "",
            "progress": {},
            "recent_memory_events": [],
            "profile_updated_at": None,
            "summary_updated_at": None,
            "progress_updated_at": None,
            "memory_events_updated_at": None,
        }

    @staticmethod
    def _learner_state_updated_at(learner_state_service: Any, user_id: str, section: str) -> str | None:
        reader = getattr(learner_state_service, "_file_updated_at", None)
        if not callable(reader):
            return None
        try:
            return reader(user_id, section)
        except Exception:
            logger.warning(
                "Failed to read learner state updated_at for member 360: user_id=%s section=%s",
                user_id,
                section,
                exc_info=True,
            )
            return None

    def _load_partial_learner_snapshot_payload(
        self,
        learner_state_service: Any,
        user_id: str,
        *,
        event_limit: int,
    ) -> dict[str, Any]:
        payload = self._empty_learner_snapshot_payload(user_id)
        loaded_any = False
        try:
            payload["profile"] = dict(learner_state_service.read_profile(user_id) or {})
            payload["profile_updated_at"] = self._learner_state_updated_at(
                learner_state_service,
                user_id,
                "profile",
            )
            loaded_any = True
        except Exception:
            logger.warning("Failed to load learner profile for member 360: user_id=%s", user_id, exc_info=True)
        try:
            payload["summary"] = str(learner_state_service.read_summary(user_id) or "")
            payload["summary_updated_at"] = self._learner_state_updated_at(
                learner_state_service,
                user_id,
                "summary",
            )
            loaded_any = True
        except Exception:
            logger.warning("Failed to load learner summary for member 360: user_id=%s", user_id, exc_info=True)
        try:
            payload["progress"] = dict(learner_state_service.read_progress(user_id) or {})
            payload["progress_updated_at"] = self._learner_state_updated_at(
                learner_state_service,
                user_id,
                "progress",
            )
            loaded_any = True
        except Exception:
            logger.warning("Failed to load learner progress for member 360: user_id=%s", user_id, exc_info=True)
        try:
            payload["recent_memory_events"] = [
                self._serialize_learner_memory_event(event)
                for event in list(learner_state_service.list_memory_events(user_id, limit=event_limit) or [])
            ]
            payload["memory_events_updated_at"] = self._learner_state_updated_at(
                learner_state_service,
                user_id,
                "events",
            )
            loaded_any = True
        except Exception:
            logger.warning("Failed to load learner memory events for member 360: user_id=%s", user_id, exc_info=True)
        payload["available"] = loaded_any
        return payload

    @staticmethod
    def _serialize_heartbeat_job(job: Any) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "user_id": job.user_id,
            "bot_id": job.bot_id,
            "channel": job.channel,
            "policy_json": dict(job.policy_json or {}),
            "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
            "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
            "last_result_json": dict(job.last_result_json or {}) if job.last_result_json else None,
            "failure_count": int(job.failure_count or 0),
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }

    def _seed_data(self) -> dict[str, Any]:
        now = _now()
        members = [
            {
                "user_id": "student_demo",
                "display_name": "陈同学",
                "phone": "13800000001",
                "tier": "vip",
                "status": "active",
                "segment": "power_user",
                "risk_level": "low",
                "auto_renew": True,
                "expire_at": _iso(now + timedelta(days=98)),
                "created_at": _iso(now - timedelta(days=120)),
                "last_active_at": _iso(now - timedelta(hours=2)),
                "points_balance": 580,
                "level": 7,
                "xp": 3420,
                "study_days": 43,
                "review_due": 3,
                "focus_topic": "地基基础承载力",
                "focus_query": "帮我复习地基基础承载力相关知识点",
                "exam_date": "2026-09-19",
                "daily_target": 30,
                "difficulty_preference": "medium",
                "explanation_style": "detailed",
                "review_reminder": True,
                "earned_badge_ids": [1, 2, 5],
                "chapter_mastery": {
                    "建筑构造": {"name": "建筑构造", "mastery": 82},
                    "地基基础": {"name": "地基基础", "mastery": 58},
                    "防水工程": {"name": "防水工程", "mastery": 71},
                    "施工管理": {"name": "施工管理", "mastery": 64},
                    "主体结构": {"name": "主体结构", "mastery": 76},
                },
                "notes": [
                    {
                        "id": "note_demo_1",
                        "content": "最近 7 天连续活跃，适合推送 VIP 题单包。",
                        "channel": "manual",
                        "pinned": True,
                        "created_at": _iso(now - timedelta(days=1)),
                    }
                ],
                "ledger": [
                    {
                        "id": "ledger_demo_1",
                        "delta": 120,
                        "reason": "signup_bonus",
                        "created_at": _iso(now - timedelta(days=25)),
                    },
                    {
                        "id": "ledger_demo_2",
                        "delta": -20,
                        "reason": "capture",
                        "created_at": _iso(now - timedelta(days=1, hours=5)),
                    },
                    {
                        "id": "ledger_demo_3",
                        "delta": 500,
                        "reason": "purchase",
                        "created_at": _iso(now - timedelta(days=3)),
                    },
                ],
            },
            {
                "user_id": "student_risk",
                "display_name": "李工备考",
                "phone": "13800000002",
                "tier": "trial",
                "status": "expiring_soon",
                "segment": "at_risk",
                "risk_level": "high",
                "auto_renew": False,
                "expire_at": _iso(now + timedelta(days=4)),
                "created_at": _iso(now - timedelta(days=24)),
                "last_active_at": _iso(now - timedelta(days=3)),
                "points_balance": 66,
                "level": 2,
                "xp": 420,
                "study_days": 8,
                "review_due": 7,
                "focus_topic": "屋面防水卷材",
                "focus_query": "我想练习屋面防水卷材相关题目",
                "exam_date": "2026-08-15",
                "daily_target": 10,
                "difficulty_preference": "easy",
                "explanation_style": "brief",
                "review_reminder": False,
                "earned_badge_ids": [1],
                "chapter_mastery": {
                    "建筑构造": {"name": "建筑构造", "mastery": 43},
                    "地基基础": {"name": "地基基础", "mastery": 38},
                    "防水工程": {"name": "防水工程", "mastery": 22},
                    "施工管理": {"name": "施工管理", "mastery": 34},
                },
                "notes": [],
                "ledger": [
                    {
                        "id": "ledger_risk_1",
                        "delta": 30,
                        "reason": "grant",
                        "created_at": _iso(now - timedelta(days=4)),
                    },
                    {
                        "id": "ledger_risk_2",
                        "delta": -18,
                        "reason": "capture",
                        "created_at": _iso(now - timedelta(hours=18)),
                    },
                ],
            },
            {
                "user_id": "student_svip",
                "display_name": "王老师",
                "phone": "13800000003",
                "tier": "svip",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": True,
                "expire_at": _iso(now + timedelta(days=188)),
                "created_at": _iso(now - timedelta(days=220)),
                "last_active_at": _iso(now - timedelta(hours=12)),
                "points_balance": 1380,
                "level": 10,
                "xp": 6800,
                "study_days": 91,
                "review_due": 1,
                "focus_topic": "施工组织设计",
                "focus_query": "继续我的学习计划",
                "exam_date": "2026-11-08",
                "daily_target": 50,
                "difficulty_preference": "hard",
                "explanation_style": "socratic",
                "review_reminder": True,
                "earned_badge_ids": [1, 2, 3, 5, 8],
                "chapter_mastery": {
                    "建筑构造": {"name": "建筑构造", "mastery": 88},
                    "地基基础": {"name": "地基基础", "mastery": 74},
                    "防水工程": {"name": "防水工程", "mastery": 81},
                    "施工管理": {"name": "施工管理", "mastery": 90},
                    "主体结构": {"name": "主体结构", "mastery": 86},
                },
                "notes": [],
                "ledger": [
                    {
                        "id": "ledger_svip_1",
                        "delta": 1200,
                        "reason": "purchase",
                        "created_at": _iso(now - timedelta(days=18)),
                    }
                ],
            },
            {
                "user_id": "student_lapsed",
                "display_name": "周学员",
                "phone": "13800000004",
                "tier": "vip",
                "status": "expired",
                "segment": "new_user",
                "risk_level": "medium",
                "auto_renew": False,
                "expire_at": _iso(now - timedelta(days=9)),
                "created_at": _iso(now - timedelta(days=52)),
                "last_active_at": _iso(now - timedelta(days=6)),
                "points_balance": 12,
                "level": 1,
                "xp": 120,
                "study_days": 5,
                "review_due": 5,
                "focus_topic": "主体结构施工缝",
                "focus_query": "我想练习主体结构施工缝相关题目",
                "exam_date": "2026-10-12",
                "daily_target": 10,
                "difficulty_preference": "medium",
                "explanation_style": "detailed",
                "review_reminder": False,
                "earned_badge_ids": [],
                "chapter_mastery": {
                    "建筑构造": {"name": "建筑构造", "mastery": 28},
                    "主体结构": {"name": "主体结构", "mastery": 31},
                    "施工管理": {"name": "施工管理", "mastery": 35},
                },
                "notes": [],
                "ledger": [
                    {
                        "id": "ledger_lapsed_1",
                        "delta": 100,
                        "reason": "purchase",
                        "created_at": _iso(now - timedelta(days=35)),
                    },
                    {
                        "id": "ledger_lapsed_2",
                        "delta": -88,
                        "reason": "capture",
                        "created_at": _iso(now - timedelta(days=10)),
                    },
                ],
            },
        ]
        return {
            "members": members,
            "packages": self._default_packages(),
            "audit_log": [
                {
                    "id": "audit_seed_1",
                    "operator": "system",
                    "action": "seed",
                    "target_user": "student_demo",
                    "reason": "bootstrap",
                    "created_at": _iso(now - timedelta(days=30)),
                }
            ],
            "assessment_sessions": {},
            "phone_codes": {},
        }

    def _load(self) -> dict[str, Any]:
        with self._lock:
            with self._storage_lock():
                return self._load_unlocked()

    def _save(self, data: dict[str, Any]) -> None:
        with self._lock:
            with self._storage_lock():
                self._save_unlocked(data)

    def _lock_path(self) -> Path:
        return self._data_path.with_name(f"{self._data_path.name}.lock")

    @contextmanager
    def _storage_lock(self):
        lock_path = self._lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_handle:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def _load_unlocked(self) -> dict[str, Any]:
        if not self._data_path.exists():
            data = self._bootstrap_data()
            self._save_unlocked(data)
            return data
        data = json.loads(self._data_path.read_text(encoding="utf-8"))
        data.setdefault("members", [])
        data.setdefault("packages", self._default_packages())
        data.setdefault("audit_log", [])
        data.setdefault("assessment_sessions", {})
        data.setdefault("phone_codes", {})
        return data

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._data_path.with_name(
            f"{self._data_path.name}.{uuid.uuid4().hex}.tmp"
        )
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._data_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _mutate(self, mutator):
        with self._lock:
            with self._storage_lock():
                data = self._load_unlocked()
                result = mutator(data)
                self._save_unlocked(data)
                return result

    def _find_member(self, data: dict[str, Any], user_id: str) -> dict[str, Any]:
        for member in data["members"]:
            if member["user_id"] == user_id:
                return member
        raise KeyError(f"Unknown member: {user_id}")

    @staticmethod
    def _is_meaningful_phone(value: Any) -> bool:
        return len(_normalize_phone_input(str(value or ""))) == 11

    @staticmethod
    def _member_signal_score(member: dict[str, Any]) -> int:
        chapter_mastery = member.get("chapter_mastery") or {}
        chapter_stats = member.get("chapter_practice_stats") or {}
        daily_counts = member.get("daily_practice_counts") or {}
        score = 0
        score += sum(1 for item in chapter_mastery.values() if int((item or {}).get("mastery") or 0) > 0) * 2
        score += sum(int((item or {}).get("done") or 0) for item in chapter_stats.values())
        score += sum(int(value or 0) for value in daily_counts.values())
        score += len(member.get("ledger") or [])
        score += len(member.get("notes") or [])
        score += len(member.get("earned_badge_ids") or [])
        if int(member.get("study_days") or 0) > 0:
            score += 1
        if str(member.get("focus_topic") or "").strip() and str(member.get("focus_topic") or "").strip() != "入门摸底":
            score += 1
        if str(member.get("display_name") or "").strip() and str(member.get("display_name") or "").strip() != str(member.get("user_id") or "").strip():
            score += 1
        if MemberConsoleService._is_meaningful_phone(member.get("phone")):
            score += 1
        if str(member.get("auth_username") or "").strip():
            score += 1
        if str(member.get("external_auth_user_id") or "").strip():
            score += 1
        return score

    @staticmethod
    def _later_timestamp(*values: Any) -> str:
        candidates = [str(item or "").strip() for item in values if str(item or "").strip()]
        if not candidates:
            return ""
        return max(candidates, key=_parse_time)

    def _merge_member_identity_view(
        self,
        target: dict[str, Any],
        source: dict[str, Any],
    ) -> None:
        scalar_fields = (
            "display_name",
            "tier",
            "status",
            "segment",
            "risk_level",
            "auto_renew",
            "created_at",
            "expire_at",
            "avatar_url",
            "level",
            "xp",
            "study_days",
            "review_due",
            "focus_topic",
            "focus_query",
            "exam_date",
            "daily_target",
            "difficulty_preference",
            "explanation_style",
            "review_reminder",
            "auth_username",
            "external_auth_provider",
            "external_auth_user_id",
            "wx_openid",
            "wx_unionid",
            "wx_session_key",
            "wx_last_login_at",
        )
        if self._member_signal_score(source) >= self._member_signal_score(target):
            for key in scalar_fields:
                value = deepcopy(source.get(key))
                if value not in ("", None, [], {}):
                    target[key] = value
            if self._is_meaningful_phone(source.get("phone")):
                target["phone"] = str(source.get("phone") or "").strip()
            if int(source.get("points_balance") or 0) > 0:
                target["points_balance"] = int(source.get("points_balance") or 0)

        target["last_active_at"] = self._later_timestamp(
            target.get("last_active_at"),
            source.get("last_active_at"),
        )
        target["last_practice_at"] = self._later_timestamp(
            target.get("last_practice_at"),
            source.get("last_practice_at"),
        )
        target["last_study_date"] = self._later_timestamp(
            target.get("last_study_date"),
            source.get("last_study_date"),
        )

        target_mastery = target.setdefault("chapter_mastery", _default_chapter_mastery())
        for key, value in (source.get("chapter_mastery") or {}).items():
            source_name = str((value or {}).get("name") or key).strip() or key
            source_mastery = int((value or {}).get("mastery") or 0)
            current = target_mastery.get(key) or {"name": source_name, "mastery": 0}
            current_name = str(current.get("name") or key).strip() or key
            current_mastery = int(current.get("mastery") or 0)
            target_mastery[key] = {
                "name": source_name or current_name,
                "mastery": max(current_mastery, source_mastery),
            }

        target_learning = self._ensure_learning_profile(target)
        source_learning = self._ensure_learning_profile(source)
        for date_key, count in (source_learning["daily_counts"] or {}).items():
            target_learning["daily_counts"][date_key] = max(
                int(target_learning["daily_counts"].get(date_key) or 0),
                int(count or 0),
            )
        for chapter_name, stats in (source_learning["chapter_stats"] or {}).items():
            target_stats = target_learning["chapter_stats"].setdefault(
                chapter_name,
                {"done": 0, "correct": 0, "last_activity_at": ""},
            )
            target_stats["done"] = max(int(target_stats.get("done") or 0), int((stats or {}).get("done") or 0))
            target_stats["correct"] = max(
                int(target_stats.get("correct") or 0),
                int((stats or {}).get("correct") or 0),
            )
            target_stats["last_activity_at"] = self._later_timestamp(
                target_stats.get("last_activity_at"),
                (stats or {}).get("last_activity_at"),
            )

        target["earned_badge_ids"] = sorted(
            {
                *[int(item) for item in list(target.get("earned_badge_ids") or []) if str(item).strip()],
                *[int(item) for item in list(source.get("earned_badge_ids") or []) if str(item).strip()],
            }
        )

        merged_notes: dict[str, dict[str, Any]] = {}
        for row in list(target.get("notes") or []) + list(source.get("notes") or []):
            if not isinstance(row, dict):
                continue
            note_id = str(row.get("id") or uuid.uuid4().hex).strip()
            merged_notes.setdefault(note_id, deepcopy(row))
        target["notes"] = sorted(
            merged_notes.values(),
            key=lambda item: _parse_time(item.get("created_at")),
            reverse=True,
        )

        merged_ledger: dict[str, dict[str, Any]] = {}
        for row in list(target.get("ledger") or []) + list(source.get("ledger") or []):
            if not isinstance(row, dict):
                continue
            entry_id = str(row.get("id") or uuid.uuid4().hex).strip()
            merged_ledger.setdefault(entry_id, deepcopy(row))
        target["ledger"] = sorted(
            merged_ledger.values(),
            key=lambda item: _parse_time(item.get("created_at")),
            reverse=True,
        )

    def _reconcile_external_auth_member(self, data: dict[str, Any], user_id: str) -> dict[str, Any] | None:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            return None
        legacy_sources = [
            member
            for member in data["members"]
            if str(member.get("user_id") or "").strip() != normalized_user_id
            and str(member.get("external_auth_user_id") or "").strip() == normalized_user_id
            and str(member.get("merged_into") or "").strip() != normalized_user_id
        ]
        if not legacy_sources:
            return None
        try:
            target = self._find_member(data, normalized_user_id)
        except KeyError:
            target = self._build_default_member(normalized_user_id)
            self._ensure_learning_profile(target)
            data["members"].append(target)
        for source in sorted(legacy_sources, key=self._member_signal_score, reverse=True):
            self._merge_member_identity_view(target, source)
            source["merged_into"] = normalized_user_id
            source["last_active_at"] = self._later_timestamp(
                source.get("last_active_at"),
                target.get("last_active_at"),
            )
        return target

    def _ensure_member(self, data: dict[str, Any], user_id: str) -> dict[str, Any]:
        normalized_user_id = str(user_id or "").strip()
        reconciled = self._reconcile_external_auth_member(data, normalized_user_id)
        if reconciled is not None:
            self._ensure_learning_profile(reconciled)
            return reconciled
        try:
            member = self._find_member(data, normalized_user_id)
            merged_into = str(member.get("merged_into") or "").strip()
            if merged_into and merged_into != normalized_user_id:
                return self._ensure_member(data, merged_into)
            self._ensure_learning_profile(member)
            return member
        except KeyError:
            seed = self._build_default_member(normalized_user_id)
            self._ensure_learning_profile(seed)
            data["members"].append(seed)
            return seed

    def _load_member_snapshot(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            with self._storage_lock():
                data = self._load_unlocked()
                before = deepcopy(data)
                member = self._ensure_member(data, user_id)
                snapshot = {
                    "member": deepcopy(member),
                    "packages": deepcopy(data.get("packages") or self._default_packages()),
                }
                if data != before:
                    self._save_unlocked(data)
                return snapshot

    def _ensure_learning_profile(self, member: dict[str, Any]) -> dict[str, Any]:
        daily_counts = member.setdefault("daily_practice_counts", {})
        chapter_stats = member.setdefault("chapter_practice_stats", {})
        chapter_mastery = member.get("chapter_mastery") or {}
        for key, meta in chapter_mastery.items():
            name = meta.get("name") or key
            chapter_stats.setdefault(
                name,
                {
                    "done": 0,
                    "correct": 0,
                    "last_activity_at": "",
                },
            )
        member.setdefault("last_study_date", "")
        member.setdefault("last_practice_at", "")
        return {
            "daily_counts": daily_counts,
            "chapter_stats": chapter_stats,
        }

    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    @staticmethod
    def _b64url_decode(raw: str) -> bytes:
        padding = "=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode(raw + padding)

    def _auth_secret(self) -> str:
        secret = str(
            os.getenv("DEEPTUTOR_AUTH_SECRET")
            or os.getenv("MEMBER_CONSOLE_AUTH_SECRET")
            or os.getenv("WECHAT_MP_TOKEN_SECRET")
            or os.getenv("WECHAT_MP_APP_SECRET")
            or os.getenv("WECHAT_MP_APPSECRET")
            or "deeptutor-dev-member-secret"
        ).strip()
        if secret == "deeptutor-dev-member-secret" and is_production_environment():
            raise RuntimeError("DEEPTUTOR_AUTH_SECRET must be configured in production")
        return secret

    @staticmethod
    def _extract_access_token(auth_header: str | None) -> str:
        raw = str(auth_header or "").strip()
        if not raw:
            return ""
        if raw.lower().startswith("bearer "):
            return raw[7:].strip()
        return raw

    def _admin_user_ids(self) -> set[str]:
        raw = str(
            os.getenv("DEEPTUTOR_ADMIN_USER_IDS")
            or os.getenv("MEMBER_CONSOLE_ADMIN_USER_IDS")
            or ""
        ).strip()
        if not raw:
            return set()
        return {item.strip() for item in raw.split(",") if item.strip()}

    def _issue_access_token(
        self,
        *,
        user_id: str,
        canonical_uid: str = "",
        openid: str = "",
        unionid: str = "",
        ttl_seconds: int = 60 * 60 * 24 * 30,
    ) -> str:
        now = int(_now().timestamp())
        resolved_user_id = str(user_id or "").strip()
        canonical_user_id = str(canonical_uid or resolved_user_id).strip()
        payload = {
            "v": 1,
            "sub": canonical_user_id,
            "uid": canonical_user_id,
            "canonical_uid": canonical_user_id,
            "openid": openid,
            "unionid": unionid,
            "provider": "wechat_mp" if openid else "local",
            "iat": now,
            "exp": now + max(300, int(ttl_seconds)),
        }
        payload_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        payload_part = self._b64url_encode(payload_bytes)
        signature = hmac.new(
            self._auth_secret().encode("utf-8"),
            payload_part.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return f"dtm.{payload_part}.{self._b64url_encode(signature)}"

    def _verify_access_token(self, token: str) -> dict[str, Any] | None:
        raw = str(token or "").strip()
        if not raw:
            return None
        if raw.startswith("demo-token-"):
            if is_production_environment():
                return None
            value = raw[len("demo-token-") :]
            return {"uid": value.split("-", 1)[0], "provider": "demo"}
        parts = raw.split(".")
        if len(parts) != 3 or parts[0] != "dtm":
            return None
        _, payload_part, signature_part = parts
        expected = hmac.new(
            self._auth_secret().encode("utf-8"),
            payload_part.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        try:
            actual = self._b64url_decode(signature_part)
            if not hmac.compare_digest(expected, actual):
                return None
            payload = json.loads(self._b64url_decode(payload_part).decode("utf-8"))
        except Exception:
            return None
        exp = int(payload.get("exp") or 0)
        now = int(_now().timestamp())
        if exp and exp < now:
            return None
        return payload

    def verify_access_token(self, token: str) -> dict[str, Any] | None:
        return self._verify_access_token(token)

    def is_admin_user(self, user_id: str | None) -> bool:
        resolved = str(user_id or "").strip()
        return bool(resolved) and resolved in self._admin_user_ids()

    def _get_wechat_mp_credentials(self) -> tuple[str, str]:
        app_id = str(
            os.getenv("WECHAT_MP_APP_ID")
            or os.getenv("WECHAT_MP_APPID")
            or ""
        ).strip()
        app_secret = str(
            os.getenv("WECHAT_MP_APP_SECRET")
            or os.getenv("WECHAT_MP_APPSECRET")
            or ""
        ).strip()
        if not app_id or not app_secret:
            raise RuntimeError(
                "Missing WeChat Mini Program credentials. Set WECHAT_MP_APP_ID and WECHAT_MP_APP_SECRET."
            )
        return app_id, app_secret

    @staticmethod
    def _normalize_wechat_upstream_error(exc: Exception, action: str) -> RuntimeError:
        if isinstance(exc, httpx.TimeoutException):
            return RuntimeError(f"WeChat {action} request timed out. Please try again.")
        if isinstance(exc, httpx.HTTPError):
            return RuntimeError(f"WeChat {action} request failed. Please try again.")
        if isinstance(exc, RuntimeError):
            return exc
        return RuntimeError(f"WeChat {action} request failed. Please try again.")

    async def _exchange_wechat_code(self, code: str) -> dict[str, Any]:
        app_id, app_secret = self._get_wechat_mp_credentials()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": app_id,
                    "secret": app_secret,
                    "js_code": code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            payload = response.json()
        if int(payload.get("errcode") or 0):
            raise RuntimeError(
                f"WeChat code2Session failed: {payload.get('errcode')} {payload.get('errmsg')}"
            )
        if not str(payload.get("openid") or "").strip():
            raise RuntimeError("WeChat code2Session succeeded but openid is missing.")
        return payload

    async def _get_wechat_access_token(self) -> str:
        now_ts = _now().timestamp()
        if self._wechat_access_token and now_ts < self._wechat_access_token_expires_at:
            return self._wechat_access_token

        app_id, app_secret = self._get_wechat_mp_credentials()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.weixin.qq.com/cgi-bin/stable_token",
                json={
                    "grant_type": "client_credential",
                    "appid": app_id,
                    "secret": app_secret,
                    "force_refresh": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
        if int(payload.get("errcode") or 0):
            raise RuntimeError(
                f"WeChat stable_token failed: {payload.get('errcode')} {payload.get('errmsg')}"
            )
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise RuntimeError("WeChat stable_token succeeded but access_token is missing.")
        expires_in = max(300, int(payload.get("expires_in") or 7200))
        self._wechat_access_token = token
        self._wechat_access_token_expires_at = now_ts + expires_in - 120
        return token

    async def _exchange_wechat_phone_code(self, phone_code: str) -> str:
        access_token = await self._get_wechat_access_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.weixin.qq.com/wxa/business/getuserphonenumber",
                params={"access_token": access_token},
                json={"code": phone_code},
            )
            response.raise_for_status()
            payload = response.json()
        if int(payload.get("errcode") or 0):
            raise RuntimeError(
                f"WeChat getuserphonenumber failed: {payload.get('errcode')} {payload.get('errmsg')}"
            )
        phone_info = payload.get("phone_info") or {}
        phone = str(
            phone_info.get("purePhoneNumber")
            or phone_info.get("phoneNumber")
            or ""
        ).strip()
        normalized = _slugify_phone(phone)
        if len(normalized) != 11:
            raise RuntimeError("WeChat phone binding succeeded but phone number is invalid.")
        return normalized

    def _find_member_by_wechat_identity(
        self,
        data: dict[str, Any],
        *,
        openid: str,
        unionid: str = "",
    ) -> dict[str, Any] | None:
        normalized_openid = str(openid or "").strip()
        normalized_unionid = str(unionid or "").strip()
        for member in data["members"]:
            if normalized_unionid and str(member.get("wx_unionid") or "").strip() == normalized_unionid:
                return member
            if normalized_openid and str(member.get("wx_openid") or "").strip() == normalized_openid:
                return member
        return None

    def _find_member_by_phone(self, data: dict[str, Any], phone: str) -> dict[str, Any] | None:
        normalized = _slugify_phone(phone)
        for member in data["members"]:
            if _slugify_phone(member.get("phone", "")) == normalized:
                merged_into = str(member.get("merged_into") or "").strip()
                if merged_into and merged_into != str(member.get("user_id") or "").strip():
                    try:
                        return self._find_member(data, merged_into)
                    except KeyError:
                        return member
                return member
        return None

    def _supports_dev_wechat_login(self, code: str) -> bool:
        if is_production_environment():
            return False
        enabled = str(os.getenv("DEEPTUTOR_ALLOW_DEV_WECHAT_LOGIN") or "").strip().lower()
        if enabled in {"1", "true", "yes", "on"}:
            return True
        lowered = str(code or "").strip().lower()
        return lowered.startswith("dev-") or lowered.startswith("dev_") or lowered.startswith("mock-")

    def _mock_wechat_session(self, code: str) -> dict[str, str]:
        normalized = str(code or "dev-user").strip() or "dev-user"
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return {
            "openid": f"dev_openid_{digest[:18]}",
            "unionid": f"dev_unionid_{digest[18:34]}",
            "session_key": f"dev_session_{digest[34:50]}",
        }

    def _sms_access_key_id(self) -> str:
        return str(os.getenv("ALIYUN_SMS_ACCESS_KEY_ID") or "").strip()

    def _sms_access_key_secret(self) -> str:
        return str(os.getenv("ALIYUN_SMS_ACCESS_KEY_SECRET") or "").strip()

    def _sms_sign_name(self) -> str:
        return str(os.getenv("ALIYUN_SMS_SIGN_NAME") or "佑森教育").strip()

    def _sms_template_code(self) -> str:
        return str(os.getenv("ALIYUN_SMS_TEMPLATE_CODE") or "SMS_504760010").strip()

    def _sms_configured(self) -> bool:
        return bool(self._sms_access_key_id() and self._sms_access_key_secret())

    def _should_use_real_sms(self) -> bool:
        if env_flag("MEMBER_CONSOLE_USE_REAL_SMS", default=False):
            return self._sms_configured()
        explicit = str(os.getenv("MEMBER_CONSOLE_USE_REAL_SMS") or "").strip().lower()
        if explicit in {"0", "false", "no", "off"}:
            return False
        return self._sms_configured() and is_production_environment()

    @staticmethod
    def _generate_sms_code() -> str:
        return "".join(secrets.choice(string.digits) for _ in range(6))

    def _aliyun_sms_signature(self, params: dict[str, str]) -> str:
        sorted_params = sorted(params.items())
        query = urllib.parse.urlencode(sorted_params, quote_via=urllib.parse.quote)
        string_to_sign = "POST&%2F&" + urllib.parse.quote(query, safe="")
        digest = hmac.new(
            (self._sms_access_key_secret() + "&").encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _send_sms(self, phone: str, code: str) -> dict[str, Any]:
        if not self._sms_configured():
            return {"Code": "MissingConfig", "Message": "SMS not configured"}
        params = {
            "Action": "SendSms",
            "Format": "JSON",
            "Version": "2017-05-25",
            "AccessKeyId": self._sms_access_key_id(),
            "SignatureMethod": "HMAC-SHA1",
            "SignatureVersion": "1.0",
            "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "SignatureNonce": str(uuid.uuid4()),
            "PhoneNumbers": phone,
            "SignName": self._sms_sign_name(),
            "TemplateCode": self._sms_template_code(),
            "TemplateParam": json.dumps({"code": code}, ensure_ascii=False),
        }
        params["Signature"] = self._aliyun_sms_signature(params)
        body = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(
            "https://dysmsapi.aliyuncs.com/",
            data=body,
            method="POST",
        )
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            response = urllib.request.urlopen(request, timeout=10)
            return json.loads(response.read())
        except Exception as exc:
            return {"Code": "SendError", "Message": str(exc)}

    def _detect_question_count(self, text: str) -> int:
        raw = str(text or "")
        if not raw.strip():
            return 0
        patterns = [
            r"第\s*\d+\s*题",
            r"例题\s*\d+",
            r"题目\s*\d+",
        ]
        counts = [len(re.findall(pattern, raw, flags=re.IGNORECASE)) for pattern in patterns]
        count = max(counts) if counts else 0
        return max(1, count)

    def _guess_activity_chapter(
        self,
        member: dict[str, Any],
        *texts: str,
    ) -> str:
        chapter_mastery = member.get("chapter_mastery") or {}
        haystack = " ".join(str(item or "") for item in texts)
        for key, value in chapter_mastery.items():
            chapter_name = value.get("name") or key
            if chapter_name and chapter_name in haystack:
                return chapter_name
        focus_topic = str(member.get("focus_topic") or "").strip()
        for key, value in chapter_mastery.items():
            chapter_name = value.get("name") or key
            if chapter_name and chapter_name in focus_topic:
                return chapter_name
        if chapter_mastery:
            weakest = min(
                chapter_mastery.items(),
                key=lambda item: int(item[1].get("mastery") or 0),
            )
            return weakest[1].get("name") or weakest[0]
        return ""

    def record_learning_activity(
        self,
        user_id: str,
        *,
        count: int = 1,
        chapter: str = "",
        correct: int = 0,
        source: str = "practice",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            member = self._ensure_member(data, user_id)
            learning = self._ensure_learning_profile(member)
            today = _date_key()
            amount = max(0, int(count or 0))
            correct_count = max(0, int(correct or 0))
            normalized_chapter = str(chapter or "").strip()
            if amount <= 0:
                return {
                    "today_done": int(learning["daily_counts"].get(today) or 0),
                    "chapter": normalized_chapter,
                }

            learning["daily_counts"][today] = int(learning["daily_counts"].get(today) or 0) + amount
            if member.get("last_study_date") != today:
                member["study_days"] = int(member.get("study_days") or 0) + 1
                member["last_study_date"] = today
            member["last_active_at"] = _iso()
            member["last_practice_at"] = _iso()

            if normalized_chapter:
                chapter_stats = learning["chapter_stats"].setdefault(
                    normalized_chapter,
                    {"done": 0, "correct": 0, "last_activity_at": ""},
                )
                chapter_stats["done"] = int(chapter_stats.get("done") or 0) + amount
                chapter_stats["correct"] = int(chapter_stats.get("correct") or 0) + min(correct_count, amount)
                chapter_stats["last_activity_at"] = _iso()
                member["focus_topic"] = normalized_chapter
                member["focus_query"] = f"我想练习{normalized_chapter}相关的题目"

            self._append_audit(
                data,
                action="learning_activity",
                target_user=user_id,
                operator=source,
                reason="activity_tracked",
                after={
                    "count": amount,
                    "correct": min(correct_count, amount),
                    "chapter": normalized_chapter,
                    "metadata": metadata or {},
                },
            )
            return {
                "today_done": int(learning["daily_counts"].get(today) or 0),
                "chapter": normalized_chapter,
            }

        return self._mutate(_apply)

    def record_chat_learning(
        self,
        user_id: str,
        *,
        query: str,
        assistant_content: str,
    ) -> dict[str, Any]:
        data = self._load()
        member = self._ensure_member(data, user_id)
        chapter = self._guess_activity_chapter(member, query, assistant_content)
        count = self._detect_question_count(assistant_content if assistant_content else query)
        if count <= 0:
            count = 1
        return self.record_learning_activity(
            user_id,
            count=count,
            chapter=chapter,
            correct=0,
            source="chat",
            metadata={"query": str(query or "")[:120]},
        )

    def resolve_user_id(self, auth_header: str | None = None, user_id: str | None = None) -> str:
        token = self._extract_access_token(auth_header)
        verified = self.verify_access_token(token)
        if verified and str(verified.get("canonical_uid") or verified.get("uid") or "").strip():
            return str(verified.get("canonical_uid") or verified.get("uid") or "").strip()
        return ""

    def _build_auth_response(
        self,
        *,
        user_id: str,
        token: str,
        openid: str = "",
        unionid: str = "",
    ) -> dict[str, Any]:
        payload = {
            "user_id": user_id,
            "token": token,
            "token_type": "Bearer",
            "user": self.get_profile(user_id),
        }
        if openid:
            payload["openid"] = openid
        if unionid:
            payload["unionid"] = unionid
        return payload

    def _append_audit(
        self,
        data: dict[str, Any],
        *,
        action: str,
        target_user: str,
        operator: str = "admin",
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        data["audit_log"].insert(
            0,
            {
                "id": f"audit_{uuid.uuid4().hex[:10]}",
                "operator": operator,
                "action": action,
                "target_user": target_user,
                "reason": reason,
                "before": before or {},
                "after": after or {},
                "created_at": _iso(),
            },
        )

    def get_dashboard(self, days: int = 30) -> dict[str, Any]:
        data = self._load()
        members = data["members"]
        now = _now()
        active_count = sum(1 for item in members if item["status"] == "active")
        expiring_soon_count = sum(
            1
            for item in members
            if 0 <= (_parse_time(item["expire_at"]) - now).days <= 7
        )
        new_today_count = sum(
            1
            for item in members
            if (_now() - _parse_time(item["created_at"])) <= timedelta(days=1)
        )
        churn_risk_count = sum(1 for item in members if item["risk_level"] == "high")
        tiers: dict[str, int] = {}
        expiry_buckets: dict[str, int] = {}
        auto_renew_count = 0
        for item in members:
            tiers[item["tier"]] = tiers.get(item["tier"], 0) + 1
            expire_at = _parse_time(item["expire_at"])
            bucket = expire_at.strftime("%m-%d")
            expiry_buckets[bucket] = expiry_buckets.get(bucket, 0) + 1
            auto_renew_count += 1 if item.get("auto_renew") else 0
        recommendations = []
        if expiring_soon_count:
            recommendations.append(f"有 {expiring_soon_count} 名会员 7 天内到期，建议批量触达续费提醒。")
        if churn_risk_count:
            recommendations.append(f"当前高风险用户 {churn_risk_count} 名，建议安排 1 对 1 学习回访。")
        if not recommendations:
            recommendations.append("当前会员状态稳定，可继续推进高分用户的 SVIP 升级。")
        return {
            "total_count": len(members),
            "active_count": active_count,
            "expiring_soon_count": expiring_soon_count,
            "new_today_count": new_today_count,
            "churn_risk_count": churn_risk_count,
            "health_score": round((active_count / max(len(members), 1)) * 100),
            "auto_renew_coverage": round((auto_renew_count / max(len(members), 1)) * 100),
            "tier_breakdown": [
                {"tier": tier, "count": count}
                for tier, count in sorted(tiers.items(), key=lambda item: item[0])
            ],
            "expiry_breakdown": [
                {"label": label, "count": count}
                for label, count in sorted(expiry_buckets.items(), key=lambda item: item[0])
            ],
            "admin_ops": {
                "window_days": days,
                "total": len(data["audit_log"]),
                "by_action": self._aggregate_actions(data["audit_log"]),
            },
            "recommendations": recommendations,
        }

    def _aggregate_actions(self, audit_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for item in audit_log[:100]:
            action = str(item.get("action") or "unknown")
            counts[action] = counts.get(action, 0) + 1
        return [{"action": key, "count": counts[key]} for key in sorted(counts)]

    def list_members(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        sort: str = "expire_at",
        order: str = "asc",
        status: str | None = None,
        tier: str | None = None,
        search: str | None = None,
        segment: str | None = None,
        risk_level: str | None = None,
        auto_renew: bool | None = None,
    ) -> dict[str, Any]:
        data = self._load()
        members = [deepcopy(item) for item in data["members"]]
        search_text = str(search or "").strip().lower()
        filtered = []
        for item in members:
            if status and status != "all" and item["status"] != status:
                continue
            if tier and tier != "all" and item["tier"] != tier:
                continue
            if segment and segment != "all" and item["segment"] != segment:
                continue
            if risk_level and risk_level != "all" and item["risk_level"] != risk_level:
                continue
            if auto_renew is not None and bool(item.get("auto_renew")) != auto_renew:
                continue
            if search_text:
                haystack = " ".join(
                    [item["user_id"], item["display_name"], item["phone"]]
                ).lower()
                if search_text not in haystack:
                    continue
            filtered.append(item)
        reverse = str(order).lower() == "desc"
        if sort in {"expire_at", "created_at", "last_active_at"}:
            filtered.sort(key=lambda item: _parse_time(item.get(sort)).timestamp(), reverse=reverse)
        else:
            filtered.sort(key=lambda item: str(item.get(sort) or ""), reverse=reverse)
        total = len(filtered)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        items = []
        for item in filtered[start:end]:
            items.append(
                {
                    "user_id": item["user_id"],
                    "display_name": item["display_name"],
                    "phone": item["phone"],
                    "tier": item["tier"],
                    "status": item["status"],
                    "segment": item["segment"],
                    "risk_level": item["risk_level"],
                    "auto_renew": item["auto_renew"],
                    "expire_at": item["expire_at"],
                    "created_at": item["created_at"],
                    "last_active_at": item["last_active_at"],
                    "points_balance": item["points_balance"],
                    "review_due": item["review_due"],
                }
            )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    def get_member_360(self, user_id: str) -> dict[str, Any]:
        data = self._load()
        member = deepcopy(self._find_member(data, user_id))
        member["wallet"] = {
            "balance": member.pop("points_balance"),
            "packages": data["packages"],
        }
        member["recent_ledger"] = member["ledger"][:10]
        member["recent_notes"] = member["notes"][:10]
        member["learner_state"] = self._empty_learner_snapshot_payload(user_id)
        heartbeat_payload = {"jobs": [], "history": [], "arbitration_history": []}
        try:
            learner_state_service = self._get_learner_state_service()
            snapshot = learner_state_service.read_snapshot(user_id, event_limit=10)
            member["learner_state"] = self._serialize_learner_snapshot(snapshot)
        except Exception:
            logger.warning("Failed to load learner snapshot for member 360: user_id=%s", user_id, exc_info=True)
            member["learner_state"] = self._load_partial_learner_snapshot_payload(
                learner_state_service,
                user_id,
                event_limit=10,
            )
        try:
            learner_state_service = self._get_learner_state_service()
            heartbeat_payload["jobs"] = [
                self._serialize_heartbeat_job(job)
                for job in learner_state_service.list_heartbeat_jobs(user_id)
            ]
        except Exception:
            logger.warning("Failed to load heartbeat jobs for member 360: user_id=%s", user_id, exc_info=True)
        try:
            learner_state_service = self._get_learner_state_service()
            heartbeat_payload["history"] = learner_state_service.list_heartbeat_history(
                user_id,
                limit=10,
                include_arbitration=True,
            )
        except Exception:
            logger.warning(
                "Failed to load heartbeat history for member 360: user_id=%s",
                user_id,
                exc_info=True,
            )
        try:
            learner_state_service = self._get_learner_state_service()
            heartbeat_payload["arbitration_history"] = (
                learner_state_service.list_heartbeat_arbitration_history(
                    user_id,
                    limit=10,
                )
            )
        except Exception:
            logger.warning(
                "Failed to load heartbeat arbitration history for member 360: user_id=%s",
                user_id,
                exc_info=True,
            )
        member["heartbeat"] = heartbeat_payload
        try:
            member["bot_overlays"] = self._get_overlay_service().list_user_overlays(user_id, limit=20)
        except Exception:
            logger.warning("Failed to load bot overlays for member 360: user_id=%s", user_id, exc_info=True)
            member["bot_overlays"] = []
        return member

    def get_member_learner_state_panel(self, user_id: str, *, limit: int = 20) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        learner_state_service = self._get_learner_state_service()
        overlay_service = self._get_overlay_service()
        snapshot = learner_state_service.read_snapshot(user_id, event_limit=limit)
        heartbeat_jobs = [
            self._serialize_heartbeat_job(job)
            for job in learner_state_service.list_heartbeat_jobs(user_id)
        ]
        return {
            "user_id": user_id,
            "learner_state": self._serialize_learner_snapshot(snapshot),
            "heartbeat_jobs": heartbeat_jobs,
            "heartbeat_history": learner_state_service.list_heartbeat_history(
                user_id,
                limit=limit,
                include_arbitration=True,
            ),
            "heartbeat_arbitration_history": learner_state_service.list_heartbeat_arbitration_history(
                user_id,
                limit=limit,
            ),
            "bot_overlays": overlay_service.list_user_overlays(user_id, limit=limit),
        }

    def list_member_heartbeat_jobs(self, user_id: str) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        learner_state_service = self._get_learner_state_service()
        jobs = [
            self._serialize_heartbeat_job(job)
            for job in learner_state_service.list_heartbeat_jobs(user_id)
        ]
        return {"user_id": user_id, "items": jobs, "total": len(jobs)}

    def pause_member_heartbeat_job(
        self,
        user_id: str,
        job_id: str,
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        learner_state_service = self._get_learner_state_service()
        job = learner_state_service.pause_heartbeat_job(user_id, job_id)

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            self._find_member(data, user_id)
            serialized = self._serialize_heartbeat_job(job)
            self._append_audit(
                data,
                action="heartbeat_job_pause",
                target_user=user_id,
                operator=operator,
                reason="member_console_pause_heartbeat_job",
                after=serialized,
            )
            return serialized

        return self._mutate(_apply)

    def resume_member_heartbeat_job(
        self,
        user_id: str,
        job_id: str,
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        learner_state_service = self._get_learner_state_service()
        job = learner_state_service.resume_heartbeat_job(user_id, job_id)

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            self._find_member(data, user_id)
            serialized = self._serialize_heartbeat_job(job)
            self._append_audit(
                data,
                action="heartbeat_job_resume",
                target_user=user_id,
                operator=operator,
                reason="member_console_resume_heartbeat_job",
                after=serialized,
            )
            return serialized

        return self._mutate(_apply)

    def get_member_overlay(self, user_id: str, bot_id: str) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        return self._get_overlay_service().read_overlay(bot_id, user_id)

    def get_member_overlay_events(
        self,
        user_id: str,
        bot_id: str,
        *,
        limit: int = 20,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        items = self._get_overlay_service().list_overlay_events(
            bot_id,
            user_id,
            limit=limit,
            event_type=event_type,
        )
        return {
            "user_id": user_id,
            "bot_id": bot_id,
            "limit": limit,
            "event_type": event_type,
            "items": items,
        }

    def get_member_overlay_audit(
        self,
        user_id: str,
        bot_id: str,
        *,
        limit: int = 20,
    ) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        items = self._get_overlay_service().list_overlay_audit(bot_id, user_id, limit=limit)
        return {
            "user_id": user_id,
            "bot_id": bot_id,
            "limit": limit,
            "items": items,
        }

    def patch_member_overlay(
        self,
        user_id: str,
        bot_id: str,
        operations: list[dict[str, Any]],
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        overlay_service = self._get_overlay_service()
        patched = overlay_service.patch_overlay(
            bot_id,
            user_id,
            {"operations": list(operations or [])},
            source_feature="member_console_overlay",
            source_id=operator,
        )

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            self._find_member(data, user_id)
            self._append_audit(
                data,
                action="overlay_patch",
                target_user=user_id,
                operator=operator,
                reason=f"member_console_overlay:{bot_id}",
                after={
                    "bot_id": bot_id,
                    "operations": list(operations or []),
                    "overlay_version": patched.get("version"),
                },
            )
            return patched

        return self._mutate(_apply)

    def apply_member_overlay_promotions(
        self,
        user_id: str,
        bot_id: str,
        *,
        operator: str = "admin",
        min_confidence: float = 0.7,
        max_candidates: int = 10,
    ) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        overlay_service = self._get_overlay_service()
        result = overlay_service.apply_promotions(
            bot_id,
            user_id,
            learner_state_service=self._get_learner_state_service(),
            min_confidence=min_confidence,
            max_candidates=max_candidates,
        )

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            self._find_member(data, user_id)
            self._append_audit(
                data,
                action="overlay_promotion_apply",
                target_user=user_id,
                operator=operator,
                reason=f"member_console_overlay_promotion:{bot_id}",
                after={
                    "bot_id": bot_id,
                    "acked_ids": list(result.get("acked_ids") or []),
                    "dropped_ids": list(result.get("dropped_ids") or []),
                },
            )
            return result

        return self._mutate(_apply)

    def ack_member_overlay_promotions(
        self,
        user_id: str,
        bot_id: str,
        candidate_ids: list[str],
        *,
        operator: str = "admin",
        reason: str = "",
    ) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        overlay_service = self._get_overlay_service()
        result = overlay_service.ack_promotions(bot_id, user_id, candidate_ids, reason=reason)

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            self._find_member(data, user_id)
            self._append_audit(
                data,
                action="overlay_promotion_ack",
                target_user=user_id,
                operator=operator,
                reason=reason or f"member_console_overlay_ack:{bot_id}",
                after={"bot_id": bot_id, "candidate_ids": list(candidate_ids)},
            )
            return result

        return self._mutate(_apply)

    def drop_member_overlay_promotions(
        self,
        user_id: str,
        bot_id: str,
        candidate_ids: list[str],
        *,
        operator: str = "admin",
        reason: str = "",
    ) -> dict[str, Any]:
        self._find_member(self._load(), user_id)
        overlay_service = self._get_overlay_service()
        result = overlay_service.drop_promotions(bot_id, user_id, candidate_ids, reason=reason)

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            self._find_member(data, user_id)
            self._append_audit(
                data,
                action="overlay_promotion_drop",
                target_user=user_id,
                operator=operator,
                reason=reason or f"member_console_overlay_drop:{bot_id}",
                after={"bot_id": bot_id, "candidate_ids": list(candidate_ids)},
            )
            return result

        return self._mutate(_apply)

    def get_notes(self, user_id: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        data = self._load()
        member = self._find_member(data, user_id)
        notes = list(member.get("notes", []))
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return {"items": notes[start:end], "total": len(notes), "page": page, "page_size": page_size}

    def add_note(
        self,
        user_id: str,
        content: str,
        channel: str = "manual",
        pinned: bool = False,
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            member = self._find_member(data, user_id)
            note = {
                "id": f"note_{uuid.uuid4().hex[:10]}",
                "content": content,
                "channel": channel,
                "pinned": pinned,
                "created_at": _iso(),
            }
            member.setdefault("notes", []).insert(0, note)
            self._append_audit(
                data,
                action="note",
                target_user=user_id,
                reason="note_created",
                after=note,
                operator=operator,
            )
            return note

        return self._mutate(_apply)

    def update_note(
        self,
        note_id: str,
        content: str | None = None,
        pinned: bool | None = None,
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            for member in data["members"]:
                for note in member.get("notes", []):
                    if note["id"] != note_id:
                        continue
                    before = deepcopy(note)
                    if content is not None:
                        note["content"] = content
                    if pinned is not None:
                        note["pinned"] = pinned
                    self._append_audit(
                        data,
                        action="note_update",
                        target_user=member["user_id"],
                        reason="note_updated",
                        before=before,
                        after=note,
                        operator=operator,
                    )
                    return note
            raise KeyError(f"Unknown note: {note_id}")

        return self._mutate(_apply)

    def delete_note(self, note_id: str, *, operator: str = "admin") -> bool:
        def _apply(data: dict[str, Any]) -> bool:
            for member in data["members"]:
                notes = member.get("notes", [])
                for index, note in enumerate(notes):
                    if note["id"] != note_id:
                        continue
                    removed = notes.pop(index)
                    self._append_audit(
                        data,
                        action="note_delete",
                        target_user=member["user_id"],
                        reason="note_deleted",
                        before=removed,
                        operator=operator,
                    )
                    return True
            return False

        return self._mutate(_apply)

    def get_audit_log(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        target_user: str | None = None,
        operator: str | None = None,
        action: str | None = None,
    ) -> dict[str, Any]:
        data = self._load()
        items = []
        for entry in data["audit_log"]:
            if target_user and entry.get("target_user") != target_user:
                continue
            if operator and entry.get("operator") != operator:
                continue
            if action and entry.get("action") != action:
                continue
            items.append(entry)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return {"items": items[start:end], "total": len(items), "page": page, "page_size": page_size}

    def grant_subscription(
        self,
        user_id: str,
        days: int,
        tier: str = "vip",
        reason: str = "",
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            member = self._ensure_member(data, user_id)
            before = deepcopy(member)
            base = max(_parse_time(member["expire_at"]), _now())
            member["tier"] = tier
            member["status"] = "active"
            member["expire_at"] = _iso(base + timedelta(days=days))
            self._append_audit(
                data,
                action="grant",
                target_user=user_id,
                reason=reason or "manual_grant",
                before=before,
                after=member,
                operator=operator,
            )
            return member

        return self._mutate(_apply)

    def update_subscription(
        self,
        user_id: str,
        *,
        tier: str | None = None,
        days: int | None = None,
        expire_at: str | None = None,
        auto_renew: bool | None = None,
        reason: str = "",
        operator: str = "admin",
    ) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            member = self._find_member(data, user_id)
            before = deepcopy(member)
            if tier:
                member["tier"] = tier
            if days:
                member["expire_at"] = _iso(_parse_time(member["expire_at"]) + timedelta(days=days))
            if expire_at:
                member["expire_at"] = expire_at
            if auto_renew is not None:
                member["auto_renew"] = auto_renew
            member["status"] = "active" if _parse_time(member["expire_at"]) > _now() else "expired"
            self._append_audit(
                data,
                action="update",
                target_user=user_id,
                reason=reason or "manual_update",
                before=before,
                after=member,
                operator=operator,
            )
            return member

        return self._mutate(_apply)

    def revoke_subscription(
        self,
        user_id: str,
        reason: str = "",
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            member = self._find_member(data, user_id)
            before = deepcopy(member)
            member["status"] = "revoked"
            member["auto_renew"] = False
            member["expire_at"] = _iso(_now())
            self._append_audit(
                data,
                action="revoke",
                target_user=user_id,
                reason=reason or "manual_revoke",
                before=before,
                after=member,
                operator=operator,
            )
            return member

        return self._mutate(_apply)

    def get_wallet(self, user_id: str) -> dict[str, Any]:
        snapshot = self._load_member_snapshot(user_id)
        member = snapshot["member"]
        return {
            "balance": member["points_balance"],
            "tier": member["tier"],
            "expire_at": member["expire_at"],
            "packages": snapshot["packages"],
        }

    def get_ledger(self, user_id: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        entries = sorted(
            member.get("ledger", []),
            key=lambda item: _parse_time(item.get("created_at")),
            reverse=True,
        )
        page = entries[offset : offset + limit]
        return {"entries": page, "has_more": offset + limit < len(entries), "total": len(entries)}

    def capture_points(self, user_id: str, amount: int = 20, reason: str = "capture") -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            member = self._ensure_member(data, user_id)
            current_balance = max(0, int(member.get("points_balance") or 0))
            requested_amount = max(0, int(amount or 0))
            debit = min(current_balance, requested_amount)
            if debit <= 0:
                return {
                    "captured": 0,
                    "requested": requested_amount,
                    "balance": current_balance,
                    "entry": None,
                }

            entry = {
                "id": f"ledger_{uuid.uuid4().hex[:12]}",
                "delta": -debit,
                "reason": reason or "capture",
                "created_at": _iso(),
            }
            member.setdefault("ledger", []).insert(0, entry)
            member["points_balance"] = current_balance - debit
            member["last_active_at"] = _iso()
            return {
                "captured": debit,
                "requested": requested_amount,
                "balance": member["points_balance"],
                "entry": entry,
            }

        return self._mutate(_apply)

    def get_profile(self, user_id: str) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        return {
            "id": member["user_id"],
            "user_id": member["user_id"],
            "username": member["display_name"],
            "display_name": member["display_name"],
            "phone": member["phone"],
            "avatar_url": member.get("avatar_url", ""),
            "level": member["level"],
            "xp": member["xp"],
            "points": member["points_balance"],
            "exam_date": member["exam_date"],
            "daily_target": member["daily_target"],
            "difficulty_preference": member["difficulty_preference"],
            "explanation_style": member["explanation_style"],
            "focus_topic": member.get("focus_topic", ""),
            "focus_query": member.get("focus_query", ""),
            "review_reminder": member["review_reminder"],
            "earned_badge_ids": member["earned_badge_ids"],
            "tier": member["tier"],
            "status": member["status"],
            "expire_at": member["expire_at"],
        }

    def update_profile(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> None:
            member = self._ensure_member(data, user_id)
            before = deepcopy(member)
            mapping = {
                "display_name": "display_name",
                "username": "display_name",
                "exam_date": "exam_date",
                "daily_target": "daily_target",
                "difficulty_preference": "difficulty_preference",
                "explanation_style": "explanation_style",
                "review_reminder": "review_reminder",
                "avatar_url": "avatar_url",
            }
            for src, dst in mapping.items():
                if src in patch:
                    member[dst] = patch[src]
            self._append_audit(
                data,
                action="profile_update",
                target_user=user_id,
                reason="profile_patch",
                before=before,
                after=member,
            )

        self._mutate(_apply)
        return self.get_profile(user_id)

    def get_today_progress(self, user_id: str) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        learning = self._ensure_learning_profile(member)
        done = int(learning["daily_counts"].get(_date_key()) or 0)
        return {
            "today_done": done,
            "daily_target": member["daily_target"],
            "streak_days": member["study_days"],
        }

    @staticmethod
    def _chapter_mastery_items(member: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "name": value.get("name") or key,
                "mastery": int(value.get("mastery") or 0),
            }
            for key, value in (member.get("chapter_mastery") or {}).items()
        ]

    def _build_provisional_mastery_items(self, member: dict[str, Any]) -> list[dict[str, Any]]:
        learning = self._ensure_learning_profile(member)
        items: list[dict[str, Any]] = []
        has_signal = False
        for key, value in (member.get("chapter_mastery") or {}).items():
            chapter_name = value.get("name") or key
            stats = learning["chapter_stats"].get(chapter_name) or {}
            done = int(stats.get("done") or 0)
            total = max(30, done, 1)
            mastery = round((done / total) * 100) if done > 0 else 0
            if mastery > 0:
                has_signal = True
            items.append({"name": chapter_name, "mastery": mastery})
        return items if has_signal else []

    def _report_mastery_items(self, member: dict[str, Any]) -> list[dict[str, Any]]:
        mastery_items = self._chapter_mastery_items(member)
        if any(int(item.get("mastery") or 0) > 0 for item in mastery_items):
            return mastery_items
        return self._build_provisional_mastery_items(member)

    def get_chapter_progress(self, user_id: str) -> list[dict[str, Any]]:
        member = self._load_member_snapshot(user_id)["member"]
        learning = self._ensure_learning_profile(member)
        items = []
        for index, (key, value) in enumerate(member["chapter_mastery"].items(), start=1):
            mastery = int(value.get("mastery") or 0)
            chapter_name = value.get("name") or key
            stats = learning["chapter_stats"].get(chapter_name) or {}
            total = max(30, int(stats.get("done") or 0), 1)
            done = int(stats.get("done") or 0)
            if done <= 0:
                done = round((mastery / 100) * total)
            items.append(
                {
                    "chapter_id": f"ch_{index}",
                    "chapter_name": chapter_name,
                    "done": done,
                    "total": total,
                }
            )
        return items

    def get_home_dashboard(self, user_id: str) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        mastery_items = self._report_mastery_items(member)
        weak_nodes = [
            {"name": item["name"], "mastery": item["mastery"]}
            for item in mastery_items
            if int(item.get("mastery") or 0) < 60
        ]
        weak_nodes.sort(key=lambda item: item["mastery"])
        return {
            "review": {
                "overdue": max(0, member["review_due"] - 1),
                "due_today": 1 if member["review_due"] else 0,
            },
            "mastery": {"weak_nodes": weak_nodes[:3]},
            "today": {"hint": f"继续推进 {member['focus_topic']} 的专项训练"},
        }

    def get_badges(self, user_id: str) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        catalog = [
            {"id": 1, "icon": "🏆", "name": "首战告捷"},
            {"id": 2, "icon": "🎯", "name": "连胜达人"},
            {"id": 3, "icon": "📚", "name": "博览群书"},
            {"id": 4, "icon": "🔥", "name": "坚持之星"},
            {"id": 5, "icon": "💡", "name": "解题高手"},
            {"id": 6, "icon": "🌟", "name": "满分王者"},
            {"id": 7, "icon": "⚡", "name": "速战速决"},
            {"id": 8, "icon": "🎖️", "name": "精英学员"},
        ]
        earned = set(member.get("earned_badge_ids", []))
        return {
            "badges": [
                {
                    "id": item["id"],
                    "icon": item["icon"],
                    "name": item["name"],
                    "earned": item["id"] in earned,
                }
                for item in catalog
            ]
        }

    def get_daily_question(self, user_id: str) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        chapter_mastery = member["chapter_mastery"]
        weakest = min(
            chapter_mastery.items(),
            key=lambda item: int(item[1].get("mastery") or 0),
        )[0]
        question = next(
            (item for item in _ASSESSMENT_BANK if item.chapter == weakest),
            _ASSESSMENT_BANK[0],
        )
        return {
            "question_id": question.id,
            "chapter": question.chapter,
            "stem": question.question,
            "options": [{"key": key, "text": value} for key, value in question.options.items()],
            "recommended_reason": f"今日优先补强 {question.chapter}。",
        }

    def get_radar_data(self, user_id: str) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        mastery_items = self._report_mastery_items(member)
        dimensions = [
            {
                "key": item["name"],
                "label": item["name"],
                "value": round(int(item.get("mastery") or 0) / 100, 2),
                "score": int(item.get("mastery") or 0),
            }
            for item in mastery_items
        ]
        return {"dimensions": dimensions}

    def get_mastery_dashboard(self, user_id: str) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        chapters = self._report_mastery_items(member)
        if not chapters:
            return {
                "overall_mastery": 0,
                "groups": [],
                "hotspots": [],
                "review_summary": {
                    "total_due": member["review_due"],
                    "overdue_count": max(0, member["review_due"] - 1),
                },
            }
        weak = [item for item in chapters if item["mastery"] < 40]
        normal = [item for item in chapters if 40 <= item["mastery"] < 70]
        strong = [item for item in chapters if item["mastery"] >= 70]

        def _group(label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
            avg = round(sum(item["mastery"] for item in items) / max(len(items), 1))
            return {"name": label, "avg_mastery": avg, "chapters": items}

        groups = []
        if weak:
            groups.append(_group("需要加强", weak))
        if normal:
            groups.append(_group("基本掌握", normal))
        if strong:
            groups.append(_group("掌握较好", strong))

        overall = round(sum(item["mastery"] for item in chapters) / max(len(chapters), 1))
        hotspots = sorted(chapters, key=lambda item: item["mastery"])[:3]
        return {
            "overall_mastery": overall,
            "groups": groups,
            "hotspots": hotspots,
            "review_summary": {
                "total_due": member["review_due"],
                "overdue_count": max(0, member["review_due"] - 1),
            },
        }

    def get_assessment_profile(self, user_id: str) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        mastery_items = self._report_mastery_items(member)
        chapter_mastery = {
            item["name"]: {"name": item["name"], "mastery": item["mastery"]}
            for item in mastery_items
        }
        if not mastery_items:
            return {
                "score": 0,
                "level": "",
                "chapter_mastery": {},
                "diagnostic_profile": {
                    "learner_archetype": "",
                    "response_profile": "",
                    "calibration_label": "",
                },
                "diagnostic_feedback": {
                    "ability_overview": {
                        "score_pct": 0,
                        "chapter_mastery": {},
                        "error_pattern": "",
                    },
                    "cognitive_insight": {
                        "response_profile": "",
                        "calibration_label": "",
                    },
                    "learner_profile": {
                        "archetype": "",
                        "traits": [],
                        "study_tip": "完成一组练习或摸底测试后，系统会自动生成学习画像。",
                    },
                    "action_plan": {
                        "priority_chapters": [],
                        "plan_strategy": "先完成一组练习，再回来看学情变化。",
                    },
                },
            }

        avg_mastery = round(
            sum(int(item.get("mastery") or 0) for item in chapter_mastery.values())
            / max(len(chapter_mastery), 1)
        )
        level = "advanced" if avg_mastery >= 75 else "intermediate" if avg_mastery >= 50 else "beginner"
        return {
            "score": avg_mastery,
            "level": level,
            "chapter_mastery": chapter_mastery,
            "diagnostic_profile": {
                "learner_archetype": "strategist" if avg_mastery >= 70 else "builder",
                "response_profile": "fluent" if avg_mastery >= 70 else "deliberate",
                "calibration_label": "accurate",
            },
            "diagnostic_feedback": {
                "ability_overview": {
                    "score_pct": avg_mastery,
                    "chapter_mastery": chapter_mastery,
                    "error_pattern": "slip_dominant" if avg_mastery >= 60 else "gap_dominant",
                },
                "cognitive_insight": {
                    "response_profile": "fluent" if avg_mastery >= 70 else "deliberate",
                    "calibration_label": "accurate",
                },
                "learner_profile": {
                    "archetype": "strategist" if avg_mastery >= 70 else "builder",
                    "traits": ["目标导向", "重视复盘", "能持续推进"],
                    "study_tip": f"优先补强 {member['focus_topic']}，再扩展到相邻章节。",
                },
                "action_plan": {
                    "priority_chapters": [
                        {"name": item.get("name") or key}
                        for key, item in sorted(
                            chapter_mastery.items(),
                            key=lambda entry: int(entry[1].get("mastery") or 0),
                        )[:5]
                    ],
                    "plan_strategy": "先完成薄弱点速练，再做 1 轮综合题巩固。",
                },
            },
        }

    def create_assessment(self, user_id: str, count: int = 20) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            questions = []
            bank = _ASSESSMENT_BANK * max(1, (count + len(_ASSESSMENT_BANK) - 1) // len(_ASSESSMENT_BANK))
            session_questions = []
            for index, item in enumerate(bank[:count], start=1):
                question_id = f"{item.id}__{index:02d}_{uuid.uuid4().hex[:6]}"
                questions.append(
                    {
                        "question_id": question_id,
                        "question_stem": item.question,
                        "question_type": "single_choice",
                        "difficulty": "medium",
                        "chapter": item.chapter,
                        "options": [{"key": key, "text": value} for key, value in item.options.items()],
                    }
                )
                session_questions.append(
                    {
                        "question_id": question_id,
                        "source_question_id": item.id,
                        "answer": item.answer,
                        "chapter": item.chapter,
                    }
                )
            quiz_id = f"quiz_{uuid.uuid4().hex[:10]}"
            data.setdefault("assessment_sessions", {})[quiz_id] = {
                "user_id": user_id,
                "questions": session_questions,
                "created_at": _iso(),
            }
            return {"quiz_id": quiz_id, "questions": questions}

        return self._mutate(_apply)

    def submit_assessment(self, user_id: str, quiz_id: str, answers: dict[str, str], time_spent_seconds: int) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            session = data.get("assessment_sessions", {}).get(quiz_id)
            if not session:
                raise KeyError(f"Unknown quiz: {quiz_id}")
            questions = session.get("questions", [])
            correct = 0
            chapter_hits: dict[str, list[int]] = {}
            for question in questions:
                chapter = question["chapter"]
                chapter_hits.setdefault(chapter, [])
                is_correct = str(answers.get(question["question_id"], "")).upper() == question["answer"]
                chapter_hits[chapter].append(1 if is_correct else 0)
                correct += 1 if is_correct else 0
            score_pct = round((correct / max(len(questions), 1)) * 100)
            chapter_mastery = {
                chapter: {"name": chapter, "mastery": round(sum(values) / max(len(values), 1) * 100)}
                for chapter, values in chapter_hits.items()
            }
            level = "advanced" if score_pct >= 75 else "intermediate" if score_pct >= 50 else "beginner"
            feedback = {
                "ability_overview": {
                    "score_pct": score_pct,
                    "chapter_mastery": chapter_mastery,
                    "error_pattern": "slip_dominant" if score_pct >= 60 else "gap_dominant",
                },
                "cognitive_insight": {
                    "response_profile": "fluent" if time_spent_seconds / max(len(questions), 1) < 20 else "deliberate",
                    "calibration_label": "accurate",
                },
                "learner_profile": {
                    "archetype": "strategist" if score_pct >= 70 else "builder",
                    "traits": ["目标导向", "有复盘意识", "能持续投入"],
                    "study_tip": "建议把错题重新按章节回看一遍，再用 AI 追问不会的步骤。",
                },
                "action_plan": {
                    "priority_chapters": [
                        {"name": chapter}
                        for chapter, _ in sorted(
                            chapter_mastery.items(),
                            key=lambda item: int(item[1].get("mastery") or 0),
                        )[:5]
                    ],
                    "plan_strategy": "先补最弱章节，再做一次 10 题针对训练。",
                },
            }
            member = self._ensure_member(data, user_id)
            member["chapter_mastery"].update(chapter_mastery)
            learning = self._ensure_learning_profile(member)
            today = _date_key()
            learning["daily_counts"][today] = int(learning["daily_counts"].get(today) or 0) + len(questions)
            if member.get("last_study_date") != today:
                member["study_days"] = int(member.get("study_days") or 0) + 1
                member["last_study_date"] = today
            member["last_active_at"] = _iso()
            member["last_practice_at"] = _iso()
            for chapter, values in chapter_hits.items():
                chapter_name = chapter_mastery[chapter]["name"]
                stats = learning["chapter_stats"].setdefault(
                    chapter_name,
                    {"done": 0, "correct": 0, "last_activity_at": ""},
                )
                stats["done"] = int(stats.get("done") or 0) + len(values)
                stats["correct"] = int(stats.get("correct") or 0) + sum(values)
                stats["last_activity_at"] = _iso()
            return {
                "score": score_pct,
                "level": level,
                "chapter_mastery": chapter_mastery,
                "diagnostic_feedback": feedback,
                "diagnostic_profile": {
                    "learner_archetype": feedback["learner_profile"]["archetype"],
                    "response_profile": feedback["cognitive_insight"]["response_profile"],
                    "calibration_label": feedback["cognitive_insight"]["calibration_label"],
                },
            }

        return self._mutate(_apply)

    def _find_member_by_external_auth(
        self,
        data: dict[str, Any],
        *,
        username: str,
        phone: str = "",
        external_user_id: str = "",
    ) -> dict[str, Any] | None:
        normalized_username = str(username or "").strip()
        normalized_phone = _slugify_phone(phone) if phone else ""
        normalized_external_user_id = str(external_user_id or "").strip()
        for member in data["members"]:
            if str(member.get("auth_username") or "").strip() == normalized_username:
                return member
            if normalized_external_user_id and str(member.get("external_auth_user_id") or "").strip() == normalized_external_user_id:
                return member
            if normalized_phone and _slugify_phone(str(member.get("phone") or "")) == normalized_phone:
                return member
        return None

    def _ensure_member_for_external_auth(self, username: str, user_data: dict[str, Any]) -> dict[str, Any]:
        normalized_username = str(username or "").strip()
        external_user_id = str(user_data.get("id") or "").strip()
        external_phone = str(user_data.get("phone") or "").strip()

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            member = self._find_member_by_external_auth(
                data,
                username=normalized_username,
                phone=external_phone,
                external_user_id=external_user_id,
            )
            if member is None:
                fallback_id = hashlib.sha1(normalized_username.encode("utf-8")).hexdigest()[:24]
                member_user_id = f"auth_{(external_user_id or fallback_id).replace('-', '')[:24]}"
                member = self._ensure_member(data, member_user_id)
            else:
                merged_into = str(member.get("merged_into") or "").strip()
                if merged_into and merged_into != str(member.get("user_id") or "").strip():
                    member = self._ensure_member(data, merged_into)
            member["display_name"] = normalized_username or str(member.get("display_name") or "")
            member["auth_username"] = normalized_username
            member["external_auth_provider"] = "fastapi20251222_simple_auth"
            if external_user_id:
                member["external_auth_user_id"] = external_user_id
            if external_phone:
                member["phone"] = _slugify_phone(external_phone)
            member["last_active_at"] = _iso()
            self._ensure_learning_profile(member)
            return deepcopy(member)

        return self._mutate(_apply)

    def login_with_password(self, username: str, password: str) -> dict[str, Any]:
        if get_external_auth_user(username) is None:
            raise ValueError("用户名或密码错误")
        verified_external_user = verify_external_auth_user(username, password)
        if verified_external_user is None:
            raise ValueError("用户名或密码错误")
        member = self._ensure_member_for_external_auth(username, verified_external_user)
        token = self._issue_access_token(user_id=member["user_id"])
        return self._build_auth_response(user_id=member["user_id"], token=token)

    def register_with_external_auth(self, username: str, password: str, phone: str) -> dict[str, Any]:
        external_user = create_external_auth_user(username, password, phone=phone)
        member = self._ensure_member_for_external_auth(username, external_user)
        token = self._issue_access_token(user_id=member["user_id"])
        return self._build_auth_response(user_id=member["user_id"], token=token)

    async def login_with_wechat_code(self, code: str) -> dict[str, Any]:
        normalized = str(code or "").strip()
        if not normalized:
            raise ValueError("code is required")
        try:
            session_payload = await self._exchange_wechat_code(normalized)
        except (RuntimeError, httpx.HTTPError) as exc:
            normalized_exc = self._normalize_wechat_upstream_error(exc, "code2Session")
            if not self._supports_dev_wechat_login(normalized):
                raise normalized_exc
            session_payload = self._mock_wechat_session(normalized)
        openid = str(session_payload.get("openid") or "").strip()
        unionid = str(session_payload.get("unionid") or "").strip()
        session_key = str(session_payload.get("session_key") or "").strip()

        def _apply(data: dict[str, Any]) -> str:
            target = self._find_member_by_wechat_identity(
                data,
                openid=openid,
                unionid=unionid,
            )
            if target is None:
                user_id = f"wx_{openid[-12:]}".replace("-", "_")
                target = self._ensure_member(data, user_id)
            else:
                merged_into = str(target.get("merged_into") or "").strip()
                current_user_id = str(target.get("user_id") or "").strip()
                if merged_into and merged_into != current_user_id:
                    target = self._ensure_member(data, merged_into)
            target["display_name"] = target.get("display_name") or f"微信用户{target['user_id'][-4:]}"
            target["last_active_at"] = _iso()
            target["wx_openid"] = openid
            target["wx_unionid"] = unionid
            target["wx_session_key"] = session_key
            target["wx_last_login_at"] = _iso()
            return str(target["user_id"])

        target_user_id = self._mutate(_apply)
        token = self._issue_access_token(
            user_id=target_user_id,
            openid=openid,
            unionid=unionid,
        )
        return self._build_auth_response(
            user_id=target_user_id,
            token=token,
            openid=openid,
            unionid=unionid,
        )

    async def bind_phone_for_wechat(self, user_id: str, phone_code: str) -> dict[str, Any]:
        raw_code = str(phone_code or "").strip()
        if not raw_code:
            raise ValueError("valid phone_code is required")

        normalized = _normalize_phone_input(raw_code)
        if len(normalized) != 11:
            try:
                normalized = await self._exchange_wechat_phone_code(raw_code)
            except (RuntimeError, httpx.HTTPError) as exc:
                normalized_exc = self._normalize_wechat_upstream_error(exc, "getuserphonenumber")
                if not self._supports_dev_wechat_login(raw_code):
                    raise normalized_exc
                normalized = _normalize_phone_input("13800000000" + raw_code[-4:])
        if len(normalized) != 11:
            raise ValueError("valid phone_code is required")

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            current = self._ensure_member(data, user_id)
            target = self._find_member_by_phone(data, normalized)

            if target and target["user_id"] != current["user_id"]:
                before = deepcopy(target)
                for key in ("wx_openid", "wx_unionid", "wx_session_key", "wx_last_login_at"):
                    if current.get(key):
                        target[key] = current[key]
                        current[key] = ""
                target["phone"] = normalized
                target["last_active_at"] = _iso()
                current["merged_into"] = target["user_id"]
                current["last_active_at"] = _iso()
                self._append_audit(
                    data,
                    action="wechat_bind_phone",
                    target_user=target["user_id"],
                    operator="wechat_mp",
                    reason="bind_phone_merge",
                    before=before,
                    after=target,
                )
                return {
                    "bound": True,
                    "merged": True,
                    "phone": normalized,
                    "user_id": str(target["user_id"]),
                    "openid": str(target.get("wx_openid") or ""),
                    "unionid": str(target.get("wx_unionid") or ""),
                }

            before = deepcopy(current)
            current["phone"] = normalized
            current["last_active_at"] = _iso()
            if not str(current.get("display_name") or "").strip():
                current["display_name"] = f"学员{normalized[-4:]}"
            self._append_audit(
                data,
                action="wechat_bind_phone",
                target_user=current["user_id"],
                operator="wechat_mp",
                reason="bind_phone_direct",
                before=before,
                after=current,
            )
            return {
                "bound": True,
                "merged": False,
                "phone": normalized,
                "user_id": str(current["user_id"]),
                "openid": str(current.get("wx_openid") or ""),
                "unionid": str(current.get("wx_unionid") or ""),
            }

        result = self._mutate(_apply)
        token = self._issue_access_token(
            user_id=result["user_id"],
            openid=result["openid"],
            unionid=result["unionid"],
        )
        payload = self._build_auth_response(
            user_id=result["user_id"],
            token=token,
            openid=result["openid"],
            unionid=result["unionid"],
        )
        payload.update(
            {
                "bound": True,
                "merged": result["merged"],
                "phone": normalized,
            }
        )
        return payload

    def send_phone_code(self, phone: str) -> dict[str, Any]:
        normalized = _normalize_phone_input(phone)
        if not normalized:
            raise ValueError("手机号格式不正确")
        now = _now()
        retry_after = 60
        delivery = "debug"
        message = "当前环境未接入短信服务，已生成测试验证码。"
        debug_code = self._generate_sms_code()

        if self._should_use_real_sms():
            sms_result = self._send_sms(normalized, debug_code)
            sms_code = str(sms_result.get("Code") or "").strip()
            sms_msg = str(sms_result.get("Message") or "").strip()
            if sms_code != "OK":
                if "BUSINESS_LIMIT_CONTROL" in sms_code:
                    if "天级" in sms_msg:
                        message = "今日验证码已达上限，请明天再试"
                    elif "小时级" in sms_msg:
                        message = "验证码发送过于频繁，请1小时后再试"
                    else:
                        message = "验证码发送过于频繁，请稍后再试"
                elif "MOBILE_NUMBER_ILLEGAL" in sms_code:
                    message = "手机号格式不正确"
                elif "AMOUNT_NOT_ENOUGH" in sms_code:
                    message = "短信服务暂不可用，请联系客服"
                else:
                    message = sms_msg or "验证码发送失败，请稍后重试"
                return {
                    "sent": False,
                    "retry_after": retry_after,
                    "phone": normalized,
                    "message": message,
                }
            delivery = "sms"
            message = "验证码发送成功"
        elif is_production_environment():
            raise RuntimeError("短信服务未配置，生产环境已禁止调试验证码")

        expires_at = now + timedelta(minutes=10)

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            existing = (data.get("phone_codes") or {}).get(normalized) or {}
            created_at = _parse_time(existing.get("created_at"))
            elapsed = max(0, int((now - created_at).total_seconds()))
            if existing and elapsed < retry_after:
                return {
                    "sent": False,
                    "retry_after": retry_after - elapsed,
                    "phone": normalized,
                    "message": f"请等待{retry_after - elapsed}秒后再试",
                }
            data["phone_codes"][normalized] = {
                "code": debug_code,
                "created_at": _iso(now),
                "expires_at": _iso(expires_at),
                "retry_after": retry_after,
                "delivery": delivery,
            }
            result = {
                "sent": True,
                "retry_after": retry_after,
                "phone": normalized,
                "delivery": delivery,
                "message": message,
            }
            if delivery != "sms":
                result["debug_code"] = debug_code
            return result

        return self._mutate(_apply)

    def verify_phone_code(self, phone: str, code: str) -> dict[str, Any]:
        normalized = _normalize_phone_input(phone)
        if not normalized:
            raise ValueError("手机号格式不正确")
        provided_code = str(code or "").strip()

        def _apply(data: dict[str, Any]) -> str:
            record = (data.get("phone_codes") or {}).get(normalized) or {}
            expected_code = str(record.get("code") or "").strip()
            expires_at = _parse_time(record.get("expires_at"))
            if not expected_code:
                raise ValueError("验证码不存在，请先获取验证码")
            if expires_at < _now():
                raise ValueError("验证码已过期，请重新获取")
            if provided_code != expected_code:
                raise ValueError("验证码错误")
            data.get("phone_codes", {}).pop(normalized, None)
            return normalized

        verified_phone = self._mutate(_apply)
        external_user = ensure_external_auth_user_for_phone(verified_phone)
        external_username = str(external_user.get("username") or "").strip()
        member = self._ensure_member_for_external_auth(external_username, external_user)
        token = self._issue_access_token(user_id=member["user_id"])
        return self._build_auth_response(user_id=member["user_id"], token=token)

    def create_demo_token(self, user_id: str) -> str:
        return f"demo-token-{user_id}-{secrets.token_hex(4)}"


_instance: MemberConsoleService | None = None


def get_member_console_service() -> MemberConsoleService:
    global _instance
    if _instance is None:
        _instance = MemberConsoleService()
    return _instance
