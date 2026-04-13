from __future__ import annotations

import json
import secrets
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from deeptutor.services.path_service import get_path_service
from deeptutor.services.session import get_sqlite_session_store

_TZ = timezone(timedelta(hours=8))


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
            "packages": [
                {"id": "starter", "points": 100, "price": "9.9", "badge": "", "per": ""},
                {"id": "standard", "points": 500, "price": "39", "badge": "热门", "per": "¥0.078/点"},
                {"id": "pro", "points": 1200, "price": "79", "badge": "", "per": "¥0.066/点"},
                {"id": "ultimate", "points": 3000, "price": "169", "badge": "SVIP", "per": "¥0.056/点"},
            ],
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
        }

    def _load(self) -> dict[str, Any]:
        with self._lock:
            if not self._data_path.exists():
                data = self._seed_data()
                self._save(data)
                return data
            return json.loads(self._data_path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._data_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _find_member(self, data: dict[str, Any], user_id: str) -> dict[str, Any]:
        for member in data["members"]:
            if member["user_id"] == user_id:
                return member
        raise KeyError(f"Unknown member: {user_id}")

    def _ensure_member(self, data: dict[str, Any], user_id: str) -> dict[str, Any]:
        try:
            return self._find_member(data, user_id)
        except KeyError:
            seed = deepcopy(data["members"][0])
            seed.update(
                {
                    "user_id": user_id,
                    "display_name": user_id,
                    "phone": _slugify_phone(user_id),
                    "status": "active",
                    "segment": "general",
                    "risk_level": "low",
                    "created_at": _iso(),
                    "last_active_at": _iso(),
                    "expire_at": _iso(_now() + timedelta(days=30)),
                    "notes": [],
                    "ledger": [],
                }
            )
            data["members"].append(seed)
            return seed

    def resolve_user_id(self, auth_header: str | None = None, user_id: str | None = None) -> str:
        if user_id:
            return user_id
        token = str(auth_header or "").replace("Bearer", "").strip()
        if token.startswith("demo-token-"):
            return token[len("demo-token-") :]
        return "student_demo"

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
        return member

    def get_notes(self, user_id: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        data = self._load()
        member = self._find_member(data, user_id)
        notes = list(member.get("notes", []))
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return {"items": notes[start:end], "total": len(notes), "page": page, "page_size": page_size}

    def add_note(self, user_id: str, content: str, channel: str = "manual", pinned: bool = False) -> dict[str, Any]:
        data = self._load()
        member = self._find_member(data, user_id)
        note = {
            "id": f"note_{uuid.uuid4().hex[:10]}",
            "content": content,
            "channel": channel,
            "pinned": pinned,
            "created_at": _iso(),
        }
        member.setdefault("notes", []).insert(0, note)
        self._append_audit(data, action="note", target_user=user_id, reason="note_created", after=note)
        self._save(data)
        return note

    def update_note(self, note_id: str, content: str | None = None, pinned: bool | None = None) -> dict[str, Any]:
        data = self._load()
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
                )
                self._save(data)
                return note
        raise KeyError(f"Unknown note: {note_id}")

    def delete_note(self, note_id: str) -> bool:
        data = self._load()
        for member in data["members"]:
            notes = member.get("notes", [])
            for index, note in enumerate(notes):
                if note["id"] != note_id:
                    continue
                removed = notes.pop(index)
                self._append_audit(data, action="note_delete", target_user=member["user_id"], reason="note_deleted", before=removed)
                self._save(data)
                return True
        return False

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

    def grant_subscription(self, user_id: str, days: int, tier: str = "vip", reason: str = "") -> dict[str, Any]:
        data = self._load()
        member = self._ensure_member(data, user_id)
        before = deepcopy(member)
        base = max(_parse_time(member["expire_at"]), _now())
        member["tier"] = tier
        member["status"] = "active"
        member["expire_at"] = _iso(base + timedelta(days=days))
        self._append_audit(data, action="grant", target_user=user_id, reason=reason or "manual_grant", before=before, after=member)
        self._save(data)
        return member

    def update_subscription(
        self,
        user_id: str,
        *,
        tier: str | None = None,
        days: int | None = None,
        expire_at: str | None = None,
        auto_renew: bool | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        data = self._load()
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
        self._append_audit(data, action="update", target_user=user_id, reason=reason or "manual_update", before=before, after=member)
        self._save(data)
        return member

    def revoke_subscription(self, user_id: str, reason: str = "") -> dict[str, Any]:
        data = self._load()
        member = self._find_member(data, user_id)
        before = deepcopy(member)
        member["status"] = "revoked"
        member["auto_renew"] = False
        member["expire_at"] = _iso(_now())
        self._append_audit(data, action="revoke", target_user=user_id, reason=reason or "manual_revoke", before=before, after=member)
        self._save(data)
        return member

    def get_wallet(self, user_id: str) -> dict[str, Any]:
        data = self._load()
        member = self._ensure_member(data, user_id)
        return {
            "balance": member["points_balance"],
            "tier": member["tier"],
            "expire_at": member["expire_at"],
            "packages": data["packages"],
        }

    def get_ledger(self, user_id: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        data = self._load()
        member = self._ensure_member(data, user_id)
        entries = member.get("ledger", [])
        page = entries[offset : offset + limit]
        return {"entries": page, "has_more": offset + limit < len(entries), "total": len(entries)}

    def get_profile(self, user_id: str) -> dict[str, Any]:
        data = self._load()
        member = self._ensure_member(data, user_id)
        return {
            "id": member["user_id"],
            "user_id": member["user_id"],
            "username": member["display_name"],
            "display_name": member["display_name"],
            "phone": member["phone"],
            "avatar_url": "",
            "level": member["level"],
            "xp": member["xp"],
            "points": member["points_balance"],
            "exam_date": member["exam_date"],
            "daily_target": member["daily_target"],
            "difficulty_preference": member["difficulty_preference"],
            "explanation_style": member["explanation_style"],
            "review_reminder": member["review_reminder"],
            "earned_badge_ids": member["earned_badge_ids"],
            "tier": member["tier"],
            "status": member["status"],
            "expire_at": member["expire_at"],
        }

    def update_profile(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
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
        }
        for src, dst in mapping.items():
            if src in patch:
                member[dst] = patch[src]
        self._append_audit(data, action="profile_update", target_user=user_id, reason="profile_patch", before=before, after=member)
        self._save(data)
        return self.get_profile(user_id)

    def get_today_progress(self, user_id: str) -> dict[str, Any]:
        data = self._load()
        member = self._ensure_member(data, user_id)
        done = min(member["daily_target"], max(0, member["points_balance"] // 18))
        return {
            "today_done": done,
            "daily_target": member["daily_target"],
            "streak_days": member["study_days"],
        }

    def get_chapter_progress(self, user_id: str) -> list[dict[str, Any]]:
        data = self._load()
        member = self._ensure_member(data, user_id)
        items = []
        for index, (key, value) in enumerate(member["chapter_mastery"].items(), start=1):
            mastery = int(value.get("mastery") or 0)
            total = 30
            done = round((mastery / 100) * total)
            items.append(
                {
                    "chapter_id": f"ch_{index}",
                    "chapter_name": value.get("name") or key,
                    "done": done,
                    "total": total,
                }
            )
        return items

    def get_home_dashboard(self, user_id: str) -> dict[str, Any]:
        data = self._load()
        member = self._ensure_member(data, user_id)
        weak_nodes = [
            {"name": value.get("name") or key, "mastery": value.get("mastery") or 0}
            for key, value in member["chapter_mastery"].items()
            if int(value.get("mastery") or 0) < 60
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
        data = self._load()
        member = self._ensure_member(data, user_id)
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
        data = self._load()
        member = self._ensure_member(data, user_id)
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
        data = self._load()
        member = self._ensure_member(data, user_id)
        dimensions = [
            {
                "key": key,
                "label": value.get("name") or key,
                "value": round(int(value.get("mastery") or 0) / 100, 2),
                "score": int(value.get("mastery") or 0),
            }
            for key, value in member["chapter_mastery"].items()
        ]
        return {"dimensions": dimensions}

    def get_mastery_dashboard(self, user_id: str) -> dict[str, Any]:
        data = self._load()
        member = self._ensure_member(data, user_id)
        chapters = [
            {
                "name": value.get("name") or key,
                "mastery": int(value.get("mastery") or 0),
            }
            for key, value in member["chapter_mastery"].items()
        ]
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
        data = self._load()
        member = self._ensure_member(data, user_id)
        chapter_mastery = member["chapter_mastery"]
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
        data = self._load()
        questions = []
        bank = _ASSESSMENT_BANK * max(1, (count + len(_ASSESSMENT_BANK) - 1) // len(_ASSESSMENT_BANK))
        for item in bank[:count]:
            questions.append(
                {
                    "question_id": item.id,
                    "question_stem": item.question,
                    "question_type": "single_choice",
                    "difficulty": "medium",
                    "chapter": item.chapter,
                    "options": [{"key": key, "text": value} for key, value in item.options.items()],
                }
            )
        quiz_id = f"quiz_{uuid.uuid4().hex[:10]}"
        data.setdefault("assessment_sessions", {})[quiz_id] = {
            "user_id": user_id,
            "questions": [
                {"question_id": item.id, "answer": item.answer, "chapter": item.chapter}
                for item in bank[:count]
            ],
            "created_at": _iso(),
        }
        self._save(data)
        return {"quiz_id": quiz_id, "questions": questions}

    def submit_assessment(self, user_id: str, quiz_id: str, answers: dict[str, str], time_spent_seconds: int) -> dict[str, Any]:
        data = self._load()
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
        self._save(data)
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

    def login_with_password(self, username: str) -> dict[str, Any]:
        data = self._load()
        target = None
        for member in data["members"]:
            if username in {member["phone"], member["display_name"], member["user_id"]}:
                target = member
                break
        if target is None:
            target = self._ensure_member(data, f"user_{_slugify_phone(username)}")
            target["display_name"] = username
            self._save(data)
        token = f"demo-token-{target['user_id']}"
        return {"token": token, "user": self.get_profile(target["user_id"])}

    def login_with_wechat_code(self, code: str) -> dict[str, Any]:
        normalized = str(code or "").strip()
        if not normalized:
            return self.verify_phone_code("13800000001")
        data = self._load()
        user_id = f"wx_{normalized[-12:]}".replace("-", "_")
        target = self._ensure_member(data, user_id)
        target["display_name"] = target.get("display_name") or f"微信用户{user_id[-4:]}"
        target["last_active_at"] = _iso()
        self._save(data)
        token = f"demo-token-{target['user_id']}"
        return {
            "token": token,
            "openid": user_id,
            "session_key": f"mock-session-{normalized[-8:]}",
            "user": self.get_profile(target["user_id"]),
        }

    def send_phone_code(self, phone: str) -> dict[str, Any]:
        return {"sent": True, "retry_after": 60, "phone": _slugify_phone(phone)}

    def verify_phone_code(self, phone: str) -> dict[str, Any]:
        data = self._load()
        normalized = _slugify_phone(phone)
        target = None
        for member in data["members"]:
            if _slugify_phone(member["phone"]) == normalized:
                target = member
                break
        if target is None:
            target = self._ensure_member(data, f"user_{normalized}")
            target["phone"] = normalized
            target["display_name"] = f"学员{normalized[-4:]}"
            self._save(data)
        token = f"demo-token-{target['user_id']}"
        return {"token": token, "user": self.get_profile(target["user_id"])}

    def create_demo_token(self, user_id: str) -> str:
        return f"demo-token-{user_id}-{secrets.token_hex(4)}"


_instance: MemberConsoleService | None = None


def get_member_console_service() -> MemberConsoleService:
    global _instance
    if _instance is None:
        _instance = MemberConsoleService()
    return _instance
