from __future__ import annotations

import json
import math
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.session import get_sqlite_session_store


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _date_bucket(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def _round(value: float, digits: int = 2) -> float:
    return round(value, digits)


@dataclass(slots=True)
class _BiContext:
    sessions: list[dict[str, Any]]
    turns: list[dict[str, Any]]
    result_events: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    notebook_entries: list[dict[str, Any]]


@dataclass(slots=True)
class _BiFilters:
    capability: str = ""
    entrypoint: str = ""
    tier: str = ""


class BIService:
    def __init__(self, session_store=None, member_service=None) -> None:
        self._store = session_store or get_sqlite_session_store()
        self._member_service = member_service or get_member_console_service()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._store.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _window_start(days: int) -> float:
        safe_days = max(1, min(int(days or 30), 365))
        return time.time() - (safe_days * 86400)

    @staticmethod
    def _resolve_entrypoint(preferences: dict[str, Any]) -> str:
        source = str(preferences.get("source") or "").strip().lower()
        if source:
            return source
        language = str(preferences.get("language") or "").strip().lower()
        if language:
            return "web"
        return "local"

    @staticmethod
    def _resolve_actor_id(session_id: str, preferences: dict[str, Any]) -> str:
        user_id = str(preferences.get("user_id") or "").strip()
        return user_id or f"anon:{session_id}"

    @staticmethod
    def _extract_cost_summary(metadata_json: str | None) -> dict[str, Any] | None:
        metadata = _json_loads(metadata_json, {})
        if not isinstance(metadata, dict):
            return None
        nested = metadata.get("metadata")
        if isinstance(nested, dict) and isinstance(nested.get("cost_summary"), dict):
            return nested.get("cost_summary")
        if isinstance(metadata.get("cost_summary"), dict):
            return metadata.get("cost_summary")
        return None

    @staticmethod
    def _average(values: list[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def _normalize_filters(
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> _BiFilters:
        return _BiFilters(
            capability=str(capability or "").strip().lower(),
            entrypoint=str(entrypoint or "").strip().lower(),
            tier=str(tier or "").strip().lower(),
        )

    def _load_member_tier_map(self) -> dict[str, str]:
        try:
            members = self._load_all_members()
        except Exception:
            return {}
        return {
            str(item.get("user_id") or "").strip(): str(item.get("tier") or "").strip().lower()
            for item in members
            if str(item.get("user_id") or "").strip()
        }

    def _apply_filters(self, context: _BiContext, filters: _BiFilters) -> _BiContext:
        if not filters.capability and not filters.entrypoint and not filters.tier:
            return context

        tier_map = self._load_member_tier_map() if filters.tier else {}

        def session_allowed(session: dict[str, Any]) -> bool:
            if filters.capability:
                if str(session.get("capability") or "chat").strip().lower() != filters.capability:
                    return False
            if filters.entrypoint:
                if self._resolve_entrypoint(session.get("preferences") or {}) != filters.entrypoint:
                    return False
            if filters.tier:
                user_id = str((session.get("preferences") or {}).get("user_id") or "").strip()
                if not user_id or tier_map.get(user_id, "") != filters.tier:
                    return False
            return True

        sessions = [session for session in context.sessions if session_allowed(session)]
        session_ids = {session["session_id"] for session in sessions}
        turn_ids = {
            turn["id"]
            for turn in context.turns
            if turn["session_id"] in session_ids
            and (not filters.capability or str(turn.get("capability") or "chat").strip().lower() == filters.capability)
        }
        turns = [turn for turn in context.turns if turn["id"] in turn_ids]
        result_events = [event for event in context.result_events if event["turn_id"] in turn_ids]
        tool_events = [event for event in context.tool_events if event["turn_id"] in turn_ids]
        notebook_entries = [
            entry
            for entry in context.notebook_entries
            if str(entry.get("session_id") or "") in session_ids
        ]
        return _BiContext(
            sessions=sessions,
            turns=turns,
            result_events=result_events,
            tool_events=tool_events,
            notebook_entries=notebook_entries,
        )

    async def _load_context(self, days: int) -> _BiContext:
        window_start = self._window_start(days)
        with self._connect() as conn:
            session_rows = conn.execute(
                """
                SELECT
                    s.id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    s.preferences_json,
                    COUNT(m.id) AS message_count,
                    COALESCE(
                        (
                            SELECT t.status
                            FROM turns t
                            WHERE t.session_id = s.id
                            ORDER BY t.updated_at DESC
                            LIMIT 1
                        ),
                        'idle'
                    ) AS status,
                    COALESCE(
                        (
                            SELECT t.capability
                            FROM turns t
                            WHERE t.session_id = s.id
                            ORDER BY t.updated_at DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS capability
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                WHERE s.updated_at >= ?
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                """,
                (window_start,),
            ).fetchall()

            turn_rows = conn.execute(
                """
                SELECT
                    t.id,
                    t.session_id,
                    t.capability,
                    t.status,
                    t.error,
                    t.created_at,
                    t.updated_at,
                    t.finished_at,
                    s.title AS session_title,
                    s.preferences_json
                FROM turns t
                INNER JOIN sessions s ON s.id = t.session_id
                WHERE t.updated_at >= ?
                ORDER BY t.updated_at DESC
                """,
                (window_start,),
            ).fetchall()

            result_rows = conn.execute(
                """
                SELECT
                    te.turn_id,
                    te.created_at,
                    te.metadata_json,
                    t.session_id,
                    t.capability,
                    t.status,
                    t.error,
                    s.title AS session_title,
                    s.preferences_json
                FROM turn_events te
                INNER JOIN turns t ON t.id = te.turn_id
                INNER JOIN sessions s ON s.id = t.session_id
                WHERE te.created_at >= ?
                  AND te.type = 'result'
                ORDER BY te.created_at DESC
                """,
                (window_start,),
            ).fetchall()

            tool_rows = conn.execute(
                """
                SELECT
                    te.turn_id,
                    te.type,
                    te.content,
                    te.metadata_json,
                    te.created_at,
                    t.session_id,
                    t.capability,
                    t.status,
                    s.preferences_json
                FROM turn_events te
                INNER JOIN turns t ON t.id = te.turn_id
                INNER JOIN sessions s ON s.id = t.session_id
                WHERE te.created_at >= ?
                  AND te.type IN ('tool_call', 'tool_result')
                ORDER BY te.created_at DESC
                """,
                (window_start,),
            ).fetchall()

            notebook_rows = conn.execute(
                """
                SELECT
                    n.id,
                    n.session_id,
                    n.question_type,
                    n.difficulty,
                    n.is_correct,
                    n.bookmarked,
                    n.created_at,
                    n.updated_at,
                    s.title AS session_title
                FROM notebook_entries n
                LEFT JOIN sessions s ON s.id = n.session_id
                WHERE n.created_at >= ?
                ORDER BY n.created_at DESC
                """,
                (window_start,),
            ).fetchall()

        sessions = []
        for row in session_rows:
            payload = dict(row)
            payload["session_id"] = payload["id"]
            payload["preferences"] = _json_loads(payload.pop("preferences_json", ""), {})
            sessions.append(payload)

        turns = []
        for row in turn_rows:
            payload = dict(row)
            payload["preferences"] = _json_loads(payload.pop("preferences_json", ""), {})
            turns.append(payload)

        result_events = []
        for row in result_rows:
            payload = dict(row)
            payload["preferences"] = _json_loads(payload.pop("preferences_json", ""), {})
            payload["cost_summary"] = self._extract_cost_summary(payload.get("metadata_json"))
            result_events.append(payload)

        tool_events = []
        for row in tool_rows:
            payload = dict(row)
            payload["preferences"] = _json_loads(payload.pop("preferences_json", ""), {})
            payload["metadata"] = _json_loads(payload.get("metadata_json"), {})
            tool_events.append(payload)

        notebook_entries = [dict(row) for row in notebook_rows]
        return _BiContext(
            sessions=sessions,
            turns=turns,
            result_events=result_events,
            tool_events=tool_events,
            notebook_entries=notebook_entries,
        )

    def _load_all_members(self) -> list[dict[str, Any]]:
        first_page = self._member_service.list_members(page=1, page_size=200)
        items = list(first_page["items"])
        for page in range(2, int(first_page.get("pages") or 1) + 1):
            current = self._member_service.list_members(page=page, page_size=200)
            items.extend(current["items"])
        return items

    async def get_overview(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        context = self._apply_filters(
            await self._load_context(days),
            self._normalize_filters(capability, entrypoint, tier),
        )
        member_dashboard = self._member_service.get_dashboard(days=days)

        active_actors = {
            self._resolve_actor_id(session["session_id"], session["preferences"])
            for session in context.sessions
        }
        capability_counter = Counter(
            (session.get("capability") or "chat") for session in context.sessions
        )
        entrypoint_counter = Counter(
            self._resolve_entrypoint(session["preferences"]) for session in context.sessions
        )

        total_tokens = sum(
            _safe_int((event.get("cost_summary") or {}).get("total_tokens"))
            for event in context.result_events
        )
        total_cost = sum(
            _safe_float((event.get("cost_summary") or {}).get("total_cost_usd"))
            for event in context.result_events
        )
        success_turns = sum(1 for turn in context.turns if turn.get("status") == "completed")
        avg_depth = self._average([_safe_int(session.get("message_count")) for session in context.sessions])
        notebook_save_count = len(context.notebook_entries)

        top_capabilities = [
            {
                "capability": capability,
                "label": capability,
                "value": count,
                "sessions": count,
                "share": _round(count / max(len(context.sessions), 1) * 100, 1),
            }
            for capability, count in capability_counter.most_common(6)
        ]
        entrypoints = [
            {"entrypoint": name, "sessions": count, "label": name, "value": count}
            for name, count in entrypoint_counter.most_common()
        ]

        risk_alerts = []
        if member_dashboard.get("expiring_soon_count"):
            risk_alerts.append(
                f"{member_dashboard['expiring_soon_count']} 名会员 7 天内到期，建议跟进续费。"
            )
        failed_turns = sum(1 for turn in context.turns if turn.get("status") == "failed")
        if failed_turns:
            risk_alerts.append(f"最近 {days} 天共有 {failed_turns} 个失败回合，建议排查错误分布。")
        if not risk_alerts:
            risk_alerts.append("当前活跃、会员和回合状态整体平稳。")

        summary = {
            "total_sessions": len(context.sessions),
            "active_learners": len(active_actors),
            "total_turns": len(context.turns),
            "success_turn_rate": _round(success_turns / max(len(context.turns), 1) * 100, 1),
            "avg_session_depth": _round(avg_depth, 1),
            "notebook_saves": notebook_save_count,
            "total_tokens": total_tokens,
            "total_cost_usd": _round(total_cost, 4),
            "active_members": member_dashboard.get("active_count", 0),
            "expiring_soon_count": member_dashboard.get("expiring_soon_count", 0),
        }

        return {
            "window_days": days,
            "applied_filters": {
                "capability": capability or "",
                "entrypoint": entrypoint or "",
                "tier": tier or "",
            },
            "generated_at": time.time(),
            "title": "DeepTutor BI 工作台",
            "subtitle": f"最近 {days} 天的经营、学习、能力、知识库与会员统一视图。",
            "summary": summary,
            "cards": [
                {"label": "活跃学习会话", "value": summary["total_sessions"], "hint": f"{days} 天窗口内更新过的会话"},
                {"label": "活跃学习者", "value": summary["active_learners"], "hint": "按用户或匿名会话去重"},
                {"label": "回合成功率", "value": f"{summary['success_turn_rate']}%", "hint": f"总回合 {summary['total_turns']}"},
                {"label": "平均会话深度", "value": summary["avg_session_depth"], "hint": "每个会话平均消息数"},
                {"label": "Notebook 保存", "value": summary["notebook_saves"], "hint": "问题笔记沉淀量"},
                {"label": "总成本", "value": summary["total_cost_usd"], "hint": f"总 Token {summary['total_tokens']}"},
            ],
            "entrypoints": entrypoints,
            "top_capabilities": top_capabilities,
            "highlights": [
                *member_dashboard.get("recommendations", [])[:2],
                *risk_alerts[:2],
            ],
            "member_snapshot": {
                "health_score": member_dashboard.get("health_score", 0),
                "auto_renew_coverage": member_dashboard.get("auto_renew_coverage", 0),
                "churn_risk_count": member_dashboard.get("churn_risk_count", 0),
                "recommendations": member_dashboard.get("recommendations", []),
            },
            "risk_alerts": risk_alerts,
            "alerts": [
                {
                    "level": "warning" if "到期" in text or "失败回合" in text else "info",
                    "title": text,
                    "detail": "来自 BI 总览聚合建议",
                }
                for text in risk_alerts
            ],
        }

    async def get_active_trend(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        context = self._apply_filters(
            await self._load_context(days),
            self._normalize_filters(capability, entrypoint, tier),
        )
        bucket_map: dict[str, dict[str, Any]] = {}

        def ensure_bucket(key: str) -> dict[str, Any]:
            return bucket_map.setdefault(
                key,
                {
                    "date": key,
                    "sessions": 0,
                    "turns": 0,
                    "learners": set(),
                    "notebook_saves": 0,
                    "cost_usd": 0.0,
                    "successful": 0,
                },
            )

        for session in context.sessions:
            bucket = ensure_bucket(_date_bucket(_safe_float(session.get("updated_at"))))
            bucket["sessions"] += 1
            bucket["learners"].add(self._resolve_actor_id(session["session_id"], session["preferences"]))

        for turn in context.turns:
            bucket = ensure_bucket(_date_bucket(_safe_float(turn.get("updated_at"))))
            bucket["turns"] += 1
            if turn.get("status") == "completed":
                bucket["successful"] += 1

        for entry in context.notebook_entries:
            bucket = ensure_bucket(_date_bucket(_safe_float(entry.get("created_at"))))
            bucket["notebook_saves"] += 1

        for event in context.result_events:
            bucket = ensure_bucket(_date_bucket(_safe_float(event.get("created_at"))))
            bucket["cost_usd"] += _safe_float((event.get("cost_summary") or {}).get("total_cost_usd"))

        points = []
        for key in sorted(bucket_map):
            bucket = bucket_map[key]
            points.append(
                {
                    "date": key,
                    "label": key,
                    "sessions": bucket["sessions"],
                    "turns": bucket["turns"],
                    "learners": len(bucket["learners"]),
                    "active": len(bucket["learners"]),
                    "notebook_saves": bucket["notebook_saves"],
                    "cost_usd": _round(bucket["cost_usd"], 4),
                    "cost": _round(bucket["cost_usd"], 4),
                    "successful": bucket["successful"],
                }
            )

        return {"window_days": days, "points": points}

    async def get_retention(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        context = self._apply_filters(
            await self._load_context(days),
            self._normalize_filters(capability, entrypoint, tier),
        )
        activity_by_actor: dict[str, set[str]] = defaultdict(set)
        first_seen: dict[str, str] = {}

        for session in context.sessions:
            actor_id = self._resolve_actor_id(session["session_id"], session["preferences"])
            bucket = _date_bucket(_safe_float(session.get("updated_at")))
            activity_by_actor[actor_id].add(bucket)
            current = first_seen.get(actor_id)
            if current is None or bucket < current:
                first_seen[actor_id] = bucket

        cohort_members: dict[str, list[str]] = defaultdict(list)
        for actor_id, bucket in first_seen.items():
            cohort_members[bucket].append(actor_id)

        labels = ["D0", "D1", "D7", "D30"]
        offsets = [0, 1, 7, 30]
        cohorts = []
        for bucket, actor_ids in sorted(cohort_members.items()):
            base = datetime.strptime(bucket, "%Y-%m-%d")
            values = []
            for offset in offsets:
                target = datetime.fromtimestamp(base.timestamp() + offset * 86400).strftime("%Y-%m-%d")
                active_count = sum(1 for actor_id in actor_ids if target in activity_by_actor[actor_id])
                values.append(_round(active_count / max(len(actor_ids), 1) * 100, 1))
            cohorts.append({"label": bucket, "values": values})

        return {"window_days": days, "labels": labels, "cohorts": cohorts}

    async def get_capability_stats(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        context = self._apply_filters(
            await self._load_context(days),
            self._normalize_filters(capability, entrypoint, tier),
        )
        event_by_turn = {event["turn_id"]: event for event in context.result_events}
        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "capability": "",
                "turns": 0,
                "completed_turns": 0,
                "failed_turns": 0,
                "running_turns": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "latency_ms_samples": [],
                "entrypoints": Counter(),
            }
        )

        for turn in context.turns:
            capability = str(turn.get("capability") or "chat")
            group = grouped[capability]
            group["capability"] = capability
            group["turns"] += 1
            status = str(turn.get("status") or "idle")
            if status == "completed":
                group["completed_turns"] += 1
            elif status == "failed":
                group["failed_turns"] += 1
            elif status == "running":
                group["running_turns"] += 1

            created_at = _safe_float(turn.get("created_at"))
            finished_at = _safe_float(turn.get("finished_at"))
            if finished_at > 0 and finished_at >= created_at:
                group["latency_ms_samples"].append((finished_at - created_at) * 1000)

            group["entrypoints"][self._resolve_entrypoint(turn["preferences"])] += 1
            cost_summary = (event_by_turn.get(turn["id"]) or {}).get("cost_summary") or {}
            group["total_tokens"] += _safe_int(cost_summary.get("total_tokens"))
            group["total_cost_usd"] += _safe_float(cost_summary.get("total_cost_usd"))

        items = []
        for capability, group in grouped.items():
            items.append(
                {
                    "capability": capability,
                    "label": capability,
                    "value": group["turns"],
                    "turns": group["turns"],
                    "completed_turns": group["completed_turns"],
                    "failed_turns": group["failed_turns"],
                    "running_turns": group["running_turns"],
                    "success_rate": _round(group["completed_turns"] / max(group["turns"], 1) * 100, 1),
                    "avg_latency_ms": _round(self._average(group["latency_ms_samples"]), 1),
                    "total_tokens": group["total_tokens"],
                    "total_cost_usd": _round(group["total_cost_usd"], 4),
                    "hint": f"成功率 {_round(group['completed_turns'] / max(group['turns'], 1) * 100, 1)}% · 均耗时 {_round(self._average(group['latency_ms_samples']), 1)}ms",
                    "secondary": f"成本 ${_round(group['total_cost_usd'], 4)}",
                    "entrypoints": [
                        {"entrypoint": name, "count": count}
                        for name, count in group["entrypoints"].most_common()
                    ],
                }
            )
        items.sort(key=lambda item: (-item["turns"], item["capability"]))
        upgrade_paths = [
            {"label": "chat → deep_solve", "value": sum(1 for item in items if item["capability"] == "deep_solve")},
            {"label": "chat → deep_question", "value": sum(1 for item in items if item["capability"] == "deep_question")},
            {"label": "chat → deep_research", "value": sum(1 for item in items if item["capability"] == "deep_research")},
        ]
        return {"window_days": days, "items": items, "upgrade_paths": upgrade_paths}

    async def get_tool_stats(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        context = self._apply_filters(
            await self._load_context(days),
            self._normalize_filters(capability, entrypoint, tier),
        )
        result_by_turn = {event["turn_id"]: event for event in context.result_events}
        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "tool_name": "",
                "calls": 0,
                "result_events": 0,
                "turn_ids": set(),
                "capabilities": Counter(),
                "entrypoints": Counter(),
                "total_cost_usd": 0.0,
                "total_tokens": 0,
            }
        )

        for event in context.tool_events:
            if event.get("type") == "tool_call":
                tool_name = str(event.get("content") or "").strip() or "tool"
            else:
                tool_name = str((event.get("metadata") or {}).get("tool") or "").strip() or "tool"
            group = grouped[tool_name]
            group["tool_name"] = tool_name
            if event.get("type") == "tool_call":
                group["calls"] += 1
            if event.get("type") == "tool_result":
                group["result_events"] += 1
            group["turn_ids"].add(event["turn_id"])
            group["capabilities"][str(event.get("capability") or "chat")] += 1
            group["entrypoints"][self._resolve_entrypoint(event["preferences"])] += 1

        for tool_name, group in grouped.items():
            for turn_id in group["turn_ids"]:
                cost_summary = (result_by_turn.get(turn_id) or {}).get("cost_summary") or {}
                group["total_cost_usd"] += _safe_float(cost_summary.get("total_cost_usd"))
                group["total_tokens"] += _safe_int(cost_summary.get("total_tokens"))

        items = []
        for _, group in grouped.items():
            turn_count = len(group["turn_ids"])
            items.append(
                {
                    "tool_name": group["tool_name"],
                    "label": group["tool_name"],
                    "value": group["calls"],
                    "calls": group["calls"],
                    "result_events": group["result_events"],
                    "turns_with_tool": turn_count,
                    "success_rate": _round(group["result_events"] / max(group["calls"], 1) * 100, 1),
                    "avg_cost_per_turn_usd": _round(group["total_cost_usd"] / max(turn_count, 1), 4),
                    "avg_tokens_per_turn": _round(group["total_tokens"] / max(turn_count, 1), 1),
                    "hint": f"成功率 {_round(group['result_events'] / max(group['calls'], 1) * 100, 1)}%",
                    "secondary": f"均成本 ${_round(group['total_cost_usd'] / max(turn_count, 1), 4)}",
                    "capabilities": [
                        {"capability": name, "count": count}
                        for name, count in group["capabilities"].most_common()
                    ],
                    "entrypoints": [
                        {"entrypoint": name, "count": count}
                        for name, count in group["entrypoints"].most_common()
                    ],
                }
            )
        items.sort(key=lambda item: (-item["calls"], item["tool_name"]))
        efficiency = [
            {
                "label": item["tool_name"],
                "value": item["calls"],
                "rate": item["success_rate"],
                "secondary": item["secondary"],
            }
            for item in items[:6]
        ]
        return {"window_days": days, "items": items, "efficiency": efficiency}

    async def get_knowledge_stats(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        context = self._apply_filters(
            await self._load_context(days),
            self._normalize_filters(capability, entrypoint, tier),
        )
        rag_turn_ids = {
            event["turn_id"]
            for event in context.tool_events
            if event.get("type") == "tool_call" and str(event.get("content") or "").strip() == "rag"
        }
        top_queries = Counter()
        for event in context.tool_events:
            if event.get("type") != "tool_call":
                continue
            if str(event.get("content") or "").strip() != "rag":
                continue
            args = (event.get("metadata") or {}).get("args")
            if not isinstance(args, dict):
                continue
            query_text = str(args.get("query") or "").strip()
            if query_text:
                top_queries[query_text] += 1
        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "kb_name": "",
                "session_ids": set(),
                "rag_turns": 0,
                "entrypoints": Counter(),
                "capabilities": Counter(),
                "notebook_entries": 0,
            }
        )
        session_to_kbs: dict[str, list[str]] = {}
        for session in context.sessions:
            kb_names = [
                str(name).strip()
                for name in (session["preferences"].get("knowledge_bases") or [])
                if str(name).strip()
            ]
            if not kb_names:
                continue
            session_to_kbs[session["session_id"]] = kb_names
            for kb_name in kb_names:
                group = grouped[kb_name]
                group["kb_name"] = kb_name
                group["session_ids"].add(session["session_id"])
                group["entrypoints"][self._resolve_entrypoint(session["preferences"])] += 1
                group["capabilities"][str(session.get("capability") or "chat")] += 1

        for turn in context.turns:
            kb_names = session_to_kbs.get(turn["session_id"], [])
            if not kb_names:
                continue
            if turn["id"] in rag_turn_ids:
                for kb_name in kb_names:
                    grouped[kb_name]["rag_turns"] += 1

        for entry in context.notebook_entries:
            kb_names = session_to_kbs.get(str(entry.get("session_id") or ""), [])
            for kb_name in kb_names:
                grouped[kb_name]["notebook_entries"] += 1

        items = []
        for _, group in grouped.items():
            items.append(
                {
                    "kb_name": group["kb_name"],
                    "label": group["kb_name"],
                    "value": len(group["session_ids"]),
                    "session_count": len(group["session_ids"]),
                    "rag_turns": group["rag_turns"],
                    "notebook_entries": group["notebook_entries"],
                    "hint": f"RAG 回合 {group['rag_turns']} · 笔记沉淀 {group['notebook_entries']}",
                    "entrypoints": [
                        {"entrypoint": name, "count": count}
                        for name, count in group["entrypoints"].most_common()
                    ],
                    "capabilities": [
                        {"capability": name, "count": count}
                        for name, count in group["capabilities"].most_common()
                    ],
                }
            )
        items.sort(key=lambda item: (-item["session_count"], item["kb_name"]))
        return {
            "window_days": days,
            "items": items,
            "top_queries": [{"label": query, "value": count} for query, count in top_queries.most_common(8)],
            "zero_hit_rate": 0.0,
        }

    async def get_member_stats(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        dashboard = self._member_service.get_dashboard(days=days)
        members = self._load_all_members()
        tier_filter = str(tier or "").strip().lower()
        if tier_filter:
            members = [
                item for item in members if str(item.get("tier") or "").strip().lower() == tier_filter
            ]
        tier_counter = Counter(member.get("tier") or "unknown" for member in members)
        risk_counter = Counter(member.get("risk_level") or "unknown" for member in members)
        status_counter = Counter(member.get("status") or "unknown" for member in members)

        expiring = sorted(
            members,
            key=lambda item: item.get("expire_at") or "",
        )[:5]

        return {
            "window_days": days,
            "dashboard": dashboard,
            "cards": [
                {"label": "活跃会员", "value": dashboard.get("active_count", 0), "hint": f"总会员 {dashboard.get('total_count', 0)}"},
                {"label": "7 天内到期", "value": dashboard.get("expiring_soon_count", 0), "hint": "建议跟进续费"},
                {"label": "流失预警", "value": dashboard.get("churn_risk_count", 0), "hint": f"健康分 {dashboard.get('health_score', 0)}"},
            ],
            "tiers": [{"tier": key, "count": value, "label": key, "value": value} for key, value in tier_counter.most_common()],
            "risks": [{"risk_level": key, "count": value, "label": key, "value": value} for key, value in risk_counter.most_common()],
            "statuses": [{"status": key, "count": value} for key, value in status_counter.most_common()],
            "expiring_members": expiring,
            "samples": [
                {
                    "user_id": item.get("user_id", ""),
                    "display_name": item.get("display_name", ""),
                    "tier": item.get("tier", ""),
                    "status": item.get("status", ""),
                    "risk_level": item.get("risk_level", ""),
                    "last_active_at": item.get("last_active_at", ""),
                    "detail": f"到期时间 {item.get('expire_at', '--')}",
                }
                for item in expiring
            ],
        }

    async def get_learner_detail(self, user_id: str, days: int = 30) -> dict[str, Any]:
        context = await self._load_context(days)
        get_member_360 = getattr(self._member_service, "get_member_360", None)
        try:
            profile = get_member_360(user_id) if callable(get_member_360) else None
        except KeyError:
            profile = None
        if not isinstance(profile, dict):
            profile = {
                "user_id": user_id,
                "display_name": user_id,
                "tier": "unknown",
                "status": "unknown",
                "segment": "",
                "risk_level": "",
                "auto_renew": False,
                "wallet": {"balance": 0, "packages": []},
                "study_days": 0,
                "review_due": 0,
                "chapter_mastery": {},
                "recent_notes": [],
                "recent_ledger": [],
            }

        learner_sessions = [
            session
            for session in context.sessions
            if str(session["preferences"].get("user_id") or "").strip() == user_id
        ]
        learner_session_ids = {session["session_id"] for session in learner_sessions}
        learner_turns = [
            turn
            for turn in context.turns
            if turn["session_id"] in learner_session_ids
        ]
        learner_notebook_entries = [
            entry
            for entry in context.notebook_entries
            if str(entry.get("session_id") or "") in learner_session_ids
        ]

        capability_counter = Counter(
            str(session.get("capability") or "chat")
            for session in learner_sessions
        )
        mastery_items = [
            {
                "chapter_id": key,
                "name": value.get("name") or key,
                "mastery": _safe_int(value.get("mastery")),
                "hint": "章节掌握度",
            }
            for key, value in (profile.get("chapter_mastery") or {}).items()
            if isinstance(value, dict)
        ]
        mastery_items.sort(key=lambda item: item["mastery"])

        recent_sessions = [
            {
                "session_id": session["session_id"],
                "title": session.get("title") or "Untitled",
                "created_at": session.get("created_at"),
                "updated_at": session.get("updated_at"),
                "started_at": session.get("created_at"),
                "ended_at": session.get("updated_at"),
                "duration_minutes": _round(max(_safe_float(session.get("updated_at")) - _safe_float(session.get("created_at")), 0) / 60, 1),
                "message_count": _safe_int(session.get("message_count")),
                "status": session.get("status") or "idle",
                "capability": session.get("capability") or "chat",
                "summary": f"消息数 { _safe_int(session.get('message_count')) }",
            }
            for session in sorted(
                learner_sessions,
                key=lambda item: _safe_float(item.get("updated_at")),
                reverse=True,
            )[:8]
        ]
        recent_notes = [
            {
                "id": item.get("id"),
                "content": item.get("content", ""),
                "channel": item.get("channel", ""),
                "pinned": bool(item.get("pinned")),
                "created_at": item.get("created_at", ""),
            }
            for item in (profile.get("recent_notes") or [])[:6]
        ]
        ledger = [
            {
                "id": item.get("id"),
                "delta": item.get("delta", 0),
                "reason": item.get("reason", ""),
                "created_at": item.get("created_at", ""),
            }
            for item in (profile.get("recent_ledger") or [])[:8]
        ]

        success_turns = sum(1 for turn in learner_turns if turn.get("status") == "completed")
        failed_turns = sum(1 for turn in learner_turns if turn.get("status") == "failed")
        summary_cards = [
            {"label": "学习天数", "value": _safe_int(profile.get("study_days")), "hint": "累计学习活跃天数"},
            {"label": "最近会话", "value": len(learner_sessions), "hint": f"{days} 天窗口"},
            {"label": "回合成功率", "value": _round(success_turns / max(len(learner_turns), 1) * 100, 1), "hint": f"失败 {failed_turns}"},
            {"label": "待复习", "value": _safe_int(profile.get("review_due")), "hint": "当前复习待办"},
            {"label": "钱包余额", "value": _safe_int(((profile.get("wallet") or {}).get("balance"))), "hint": "当前积分/点数"},
            {"label": "关注主题", "value": str(profile.get("focus_topic", "") or "--"), "hint": "当前学习焦点"},
        ]

        notes_summary = {
            "notes_count": len(recent_notes),
            "pinned_notes_count": sum(1 for item in recent_notes if item.get("pinned")),
            "recent_note": recent_notes[0]["content"] if recent_notes else "",
            "recent_ledger": f"{ledger[0]['reason']} {ledger[0]['delta']}" if ledger else "",
            "wallet_balance": _safe_int(((profile.get("wallet") or {}).get("balance"))),
            "ledger_delta": _safe_int(ledger[0]["delta"]) if ledger else 0,
            "summary": f"最近 {days} 天会话 {len(learner_sessions)}，笔记 {len(learner_notebook_entries)}。",
        }

        return {
            "window_days": days,
            "profile": {
                "user_id": profile.get("user_id", user_id),
                "display_name": profile.get("display_name", user_id),
                "phone": profile.get("phone", ""),
                "tier": profile.get("tier", ""),
                "status": profile.get("status", ""),
                "segment": profile.get("segment", ""),
                "risk_level": profile.get("risk_level", ""),
                "auto_renew": bool(profile.get("auto_renew")),
                "expire_at": profile.get("expire_at", ""),
                "wallet_balance": _safe_int(((profile.get("wallet") or {}).get("balance"))),
                "focus_topic": profile.get("focus_topic", ""),
                "exam_date": profile.get("exam_date", ""),
                "daily_target": _safe_int(profile.get("daily_target")),
            },
            "cards": summary_cards,
            "summary_cards": summary_cards,
            "capabilities": [{"label": key, "value": value} for key, value in capability_counter.most_common()],
            "recent_sessions": recent_sessions,
            "mastery": mastery_items,
            "chapter_mastery": mastery_items,
            "recent_notes": recent_notes,
            "ledger": ledger,
            "notes_summary": notes_summary,
            "notebook_summary": {
                "count": len(learner_notebook_entries),
                "bookmarked_count": sum(1 for item in learner_notebook_entries if item.get("bookmarked")),
            },
        }

    async def get_tutorbot_stats(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        from deeptutor.services.tutorbot import get_tutorbot_manager

        manager = get_tutorbot_manager()
        filters = self._normalize_filters(capability, entrypoint, tier)
        tier_map = self._load_member_tier_map() if filters.tier else {}
        bots = manager.list_bots()
        recent = manager.get_recent_active_bots(limit=10)
        recent_by_id = {item.get("bot_id"): item for item in recent}
        channel_counter = Counter()
        status_counter = Counter()
        running_count = 0
        items: list[dict[str, Any]] = []

        for bot in bots:
            bot_id = str(bot.get("bot_id") or "")
            channels = bot.get("channels") or []
            channel_names = [str(channel).strip() for channel in channels if str(channel).strip()]
            entrypoint_values = {channel.lower() for channel in channel_names}
            tier_values: set[str] = set()

            if hasattr(manager, "_bot_workspace") and hasattr(manager, "_load_session_file"):
                try:
                    sessions_dir = manager._bot_workspace(bot_id) / "sessions"
                except Exception:
                    sessions_dir = None
                if sessions_dir and sessions_dir.exists():
                    for path in sorted(
                        sessions_dir.glob("*.jsonl"),
                        key=lambda item: item.stat().st_mtime,
                        reverse=True,
                    )[:20]:
                        try:
                            loaded = manager._load_session_file(path)
                        except Exception:
                            loaded = None
                        if not loaded:
                            continue
                        metadata_line, _messages = loaded
                        metadata = metadata_line.get("metadata") or {}
                        source = str(metadata.get("source") or "").strip().lower()
                        if source:
                            entrypoint_values.add(source)
                        user_id = str(metadata.get("user_id") or "").strip()
                        if user_id and tier_map.get(user_id):
                            tier_values.add(tier_map[user_id])

            if filters.entrypoint and filters.entrypoint not in entrypoint_values:
                continue
            if filters.tier and filters.tier not in tier_values:
                continue

            for channel in channel_names:
                channel_counter[channel] += 1

            status = "running" if bot.get("running") else "idle"
            status_counter[status] += 1
            if bot.get("running"):
                running_count += 1
            recent_item = recent_by_id.get(bot_id, {})
            history = manager.get_bot_history(bot_id, limit=50)
            primary_entrypoint = channel_names[0] if channel_names else (sorted(entrypoint_values)[0] if entrypoint_values else "")
            primary_tier = sorted(tier_values)[0] if tier_values else ""
            display_name = str(bot.get("name") or bot_id)
            recent_message = str(recent_item.get("last_message") or "")
            updated_at = recent_item.get("updated_at") or bot.get("started_at")
            items.append(
                {
                    "bot_id": bot_id,
                    "name": display_name,
                    "label": display_name,
                    "value": len(history),
                    "runs": len(history),
                    "running": bool(bot.get("running")),
                    "status": status,
                    "capability": "tutorbot",
                    "entrypoint": primary_entrypoint,
                    "tier": primary_tier,
                    "model": bot.get("model"),
                    "channels": channel_names,
                    "updated_at": updated_at,
                    "last_active_at": updated_at,
                    "last_message": recent_message,
                    "recent_message": recent_message,
                    "hint": f"渠道 {len(channel_names)} · {'运行中' if bot.get('running') else '未运行'}",
                    "secondary": str(bot.get("model") or ""),
                    "detail": f"入口 {primary_entrypoint or '--'} · 层级 {primary_tier or '--'}",
                }
            )

        items.sort(
            key=lambda item: (
                0 if item.get("running") else 1,
                -_safe_int(item.get("value")),
                str(item.get("label") or ""),
            )
        )

        cards = [
            {"label": "TutorBot 总数", "value": len(items), "hint": f"{days} 天视图内的筛选结果"},
            {"label": "运行中", "value": running_count, "hint": "当前在线 bot 数量"},
            {"label": "近期待活跃", "value": len([item for item in items if item.get('recent_message')]), "hint": "有最近消息预览的 bot"},
        ]
        channels = [{"label": key, "value": value} for key, value in channel_counter.most_common()]
        status_breakdown = [{"label": key, "value": value} for key, value in status_counter.most_common()]
        recent_active = sorted(
            [
                {
                    "bot_id": item["bot_id"],
                    "name": item["name"],
                    "capability": item["capability"],
                    "entrypoint": item["entrypoint"],
                    "tier": item["tier"],
                    "status": item["status"],
                    "last_active_at": item["last_active_at"],
                    "recent_message": item["recent_message"],
                    "detail": item["detail"],
                }
                for item in items
            ],
            key=lambda item: str(item.get("last_active_at") or ""),
            reverse=True,
        )[:10]
        recent_messages = sorted(
            {
                item["bot_id"]: {
                    "bot_id": item["bot_id"],
                    "name": item["name"],
                    "capability": item["capability"],
                    "entrypoint": item["entrypoint"],
                    "tier": item["tier"],
                    "status": item["status"],
                    "last_active_at": item["last_active_at"],
                    "recent_message": item["recent_message"],
                    "detail": item["detail"],
                }
                for item in items
                if item.get("recent_message")
            }
            .values(),
            key=lambda item: str(item.get("last_active_at") or ""),
            reverse=True,
        )[:10]
        return {
            "window_days": days,
            "applied_filters": {
                "capability": capability or "",
                "entrypoint": entrypoint or "",
                "tier": tier or "",
            },
            "cards": cards,
            "items": items,
            "ranking": items,
            "status_breakdown": status_breakdown,
            "channels": channels,
            "recent": recent_active,
            "recent_active": recent_active,
            "recent_messages": recent_messages,
        }

    async def get_cost_stats(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        context = self._apply_filters(
            await self._load_context(days),
            self._normalize_filters(capability, entrypoint, tier),
        )
        model_counter = Counter()
        provider_counter = Counter()
        total_input = 0
        total_output = 0
        total_tokens = 0
        total_cost = 0.0

        for event in context.result_events:
            cost_summary = event.get("cost_summary") or {}
            total_input += _safe_int(cost_summary.get("total_input_tokens"))
            total_output += _safe_int(cost_summary.get("total_output_tokens"))
            total_tokens += _safe_int(cost_summary.get("total_tokens"))
            total_cost += _safe_float(cost_summary.get("total_cost_usd"))
            for name, count in (cost_summary.get("models") or {}).items():
                model_counter[str(name)] += _safe_int(count)
            for name, count in (cost_summary.get("usage_sources") or {}).items():
                provider_counter[str(name)] += _safe_int(count)

        cards = [
            {"label": "总成本", "value": _round(total_cost, 4), "hint": f"最近 {days} 天"},
            {"label": "总 Token", "value": total_tokens, "hint": f"输入 {total_input} / 输出 {total_output}"},
            {"label": "平均回合成本", "value": _round(total_cost / max(len(context.turns), 1), 4), "hint": f"回合数 {len(context.turns)}"},
        ]
        models = [{"label": key, "value": value} for key, value in model_counter.most_common()]
        providers = [{"label": key, "value": value} for key, value in provider_counter.most_common()]
        return {
            "window_days": days,
            "cards": cards,
            "models": models,
            "providers": providers,
        }

    async def get_anomalies(
        self,
        days: int = 30,
        limit: int = 20,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        context = self._apply_filters(
            await self._load_context(days),
            self._normalize_filters(capability, entrypoint, tier),
        )
        high_cost_turns = []
        result_by_turn = {event["turn_id"]: event for event in context.result_events}
        for turn in context.turns:
            cost_summary = (result_by_turn.get(turn["id"]) or {}).get("cost_summary") or {}
            total_cost = _safe_float(cost_summary.get("total_cost_usd"))
            if total_cost <= 0:
                continue
            high_cost_turns.append(
                {
                    "kind": "high_cost_turn",
                    "level": "warning" if total_cost < 0.05 else "critical",
                    "title": f"{turn.get('capability') or 'chat'} 成本偏高",
                    "detail": f"{turn.get('session_title') or 'Untitled'} · ${_round(total_cost, 4)}",
                    "session_id": turn["session_id"],
                    "session_title": turn.get("session_title") or "Untitled",
                    "turn_id": turn["id"],
                    "capability": turn.get("capability") or "chat",
                    "status": turn.get("status") or "idle",
                    "error": turn.get("error") or "",
                    "value": _round(total_cost, 4),
                    "updated_at": turn.get("updated_at"),
                }
            )

        failed_turns = [
            {
                "kind": "failed_turn",
                "level": "critical",
                "title": f"{turn.get('capability') or 'chat'} 失败",
                "detail": f"{turn.get('session_title') or 'Untitled'} · {turn.get('error') or 'Unknown error'}",
                "session_id": turn["session_id"],
                "session_title": turn.get("session_title") or "Untitled",
                "turn_id": turn["id"],
                "capability": turn.get("capability") or "chat",
                "status": turn.get("status") or "idle",
                "error": turn.get("error") or "Unknown error",
                "value": 0,
                "updated_at": turn.get("updated_at"),
            }
            for turn in context.turns
            if turn.get("status") == "failed"
        ]
        running_turns = [
            {
                "kind": "running_turn",
                "level": "info",
                "title": f"{turn.get('capability') or 'chat'} 正在运行",
                "detail": f"{turn.get('session_title') or 'Untitled'} · 已运行 {_round((_safe_float(turn.get('updated_at')) - _safe_float(turn.get('created_at'))) * 1000, 1)}ms",
                "session_id": turn["session_id"],
                "session_title": turn.get("session_title") or "Untitled",
                "turn_id": turn["id"],
                "capability": turn.get("capability") or "chat",
                "status": turn.get("status") or "running",
                "error": "",
                "value": _round((_safe_float(turn.get("updated_at")) - _safe_float(turn.get("created_at"))) * 1000, 1),
                "updated_at": turn.get("updated_at"),
            }
            for turn in context.turns
            if turn.get("status") == "running"
        ]

        anomalies = sorted(
            failed_turns + running_turns + sorted(high_cost_turns, key=lambda item: item["value"], reverse=True),
            key=lambda item: (_safe_float(item.get("updated_at")), _safe_float(item.get("value"))),
            reverse=True,
        )[: max(1, min(limit, 100))]

        return {"window_days": days, "items": anomalies}


_bi_service: BIService | None = None


def get_bi_service() -> BIService:
    global _bi_service
    if _bi_service is None:
        _bi_service = BIService()
    return _bi_service
