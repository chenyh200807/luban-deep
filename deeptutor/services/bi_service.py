from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import re
from typing import Any

from deeptutor.services.bi_metrics import BI_METRICS, metric_by_id
from deeptutor.services.feedback_service import (
    SupabaseFeedbackStore,
    is_deeptutor_feedback_record,
    normalize_feedback_record,
)
from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.observability import (
    get_bailian_billing_client,
    get_bailian_telemetry_client,
    get_usage_ledger,
)
from deeptutor.services.session import get_sqlite_session_store

logger = logging.getLogger(__name__)
_BI_CONTEXT_ROW_LIMIT = 5000


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
class _CostSummaryRollup:
    measured_input_tokens: int = 0
    measured_output_tokens: int = 0
    measured_total_tokens: int = 0
    measured_total_cost: float = 0.0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_total_tokens: int = 0
    estimated_total_cost: float = 0.0

    @property
    def effective_input_tokens(self) -> int:
        return self.measured_input_tokens + self.estimated_input_tokens

    @property
    def effective_output_tokens(self) -> int:
        return self.measured_output_tokens + self.estimated_output_tokens

    @property
    def effective_total_tokens(self) -> int:
        return self.measured_total_tokens + self.estimated_total_tokens

    @property
    def effective_total_cost(self) -> float:
        return self.measured_total_cost + self.estimated_total_cost


@dataclass(slots=True)
class _BiContext:
    sessions: list[dict[str, Any]]
    turns: list[dict[str, Any]]
    result_events: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    notebook_entries: list[dict[str, Any]]
    truncated_collections: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class _BiFilters:
    capability: str = ""
    entrypoint: str = ""
    tier: str = ""


class BIService:
    def __init__(
        self,
        session_store=None,
        member_service=None,
        feedback_store=None,
        bailian_telemetry_client=None,
        bailian_billing_client=None,
        usage_ledger=None,
    ) -> None:
        self._store = session_store or get_sqlite_session_store()
        self._member_service = member_service or get_member_console_service()
        self._feedback_store = feedback_store or SupabaseFeedbackStore()
        self._bailian_telemetry_client = bailian_telemetry_client or get_bailian_telemetry_client()
        self._bailian_billing_client = bailian_billing_client or get_bailian_billing_client()
        self._usage_ledger = usage_ledger or get_usage_ledger()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._store.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _window_start(days: int) -> float:
        safe_days = max(1, min(int(days or 30), 365))
        return time.time() - (safe_days * 86400)

    @staticmethod
    def _normalize_billing_cycle(value: str | None) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            return ""
        if not re.fullmatch(r"\d{4}-\d{2}", normalized):
            raise ValueError("billing_cycle must be in YYYY-MM format")
        return normalized

    @staticmethod
    def _iter_billing_cycles(start_ts: float, end_ts: float) -> list[str]:
        start_dt = datetime.fromtimestamp(start_ts)
        end_dt = datetime.fromtimestamp(end_ts)
        year = start_dt.year
        month = start_dt.month
        cycles: list[str] = []
        while (year, month) <= (end_dt.year, end_dt.month):
            cycles.append(f"{year:04d}-{month:02d}")
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
        return cycles

    @staticmethod
    def _billing_cycle_bounds(billing_cycle: str) -> tuple[float, float]:
        cycle = BIService._normalize_billing_cycle(billing_cycle)
        start_dt = datetime.strptime(f"{cycle}-01", "%Y-%m-%d")
        year = start_dt.year
        month = start_dt.month
        if month == 12:
            end_dt = datetime(year + 1, 1, 1)
        else:
            end_dt = datetime(year, month + 1, 1)
        return start_dt.timestamp(), end_dt.timestamp()

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
        registered_actor_id = str(preferences.get("_bi_registered_actor_id") or "").strip()
        if registered_actor_id:
            return registered_actor_id
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
    def _rollup_cost_summary(cost_summary: dict[str, Any] | None) -> _CostSummaryRollup:
        summary = cost_summary if isinstance(cost_summary, dict) else {}
        return _CostSummaryRollup(
            measured_input_tokens=_safe_int(summary.get("total_input_tokens")),
            measured_output_tokens=_safe_int(summary.get("total_output_tokens")),
            measured_total_tokens=_safe_int(summary.get("total_tokens")),
            measured_total_cost=_safe_float(summary.get("total_cost_usd")),
            estimated_input_tokens=_safe_int(summary.get("estimated_input_tokens")),
            estimated_output_tokens=_safe_int(summary.get("estimated_output_tokens")),
            estimated_total_tokens=_safe_int(summary.get("estimated_total_tokens")),
            estimated_total_cost=_safe_float(summary.get("estimated_total_cost_usd")),
        )

    @staticmethod
    def _pick_backfill_model(cost_summary: dict[str, Any] | None) -> str:
        models = cost_summary.get("models") if isinstance(cost_summary, dict) else {}
        if not isinstance(models, dict) or len(models) != 1:
            return ""
        model_name = next(iter(models.keys()), "")
        return str(model_name or "").strip()

    @staticmethod
    def _average(values: list[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def _delta_ratio(system_value: int, external_value: int) -> float | None:
        if external_value > 0:
            return _round((system_value - external_value) / external_value, 6)
        if system_value > 0:
            return 1.0
        return None

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
        tier_map: dict[str, str] = {}
        for item in members:
            tier = str(item.get("tier") or "").strip().lower()
            for identity in self._member_identity_values(item):
                tier_map[identity] = tier
        return tier_map

    @staticmethod
    def _normalize_member_phone(value: Any) -> str:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        if len(digits) < 11:
            return ""
        return digits[-11:]

    @classmethod
    def _normalize_member_identity(cls, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        phone = cls._normalize_member_phone(raw)
        if phone and (raw == phone or raw.startswith("+86") or raw.startswith("86")):
            return phone
        return raw

    @classmethod
    def _member_identity_values(cls, member: dict[str, Any]) -> set[str]:
        values: set[str] = set()
        for key in (
            "user_id",
            "canonical_user_id",
            "external_auth_user_id",
            "phone",
            "wx_openid",
            "wx_unionid",
        ):
            normalized = cls._normalize_member_identity(member.get(key))
            if normalized:
                values.add(normalized)
        for alias in list(member.get("alias_user_ids") or []):
            normalized = cls._normalize_member_identity(alias)
            if normalized:
                values.add(normalized)
        return values

    @classmethod
    def _is_registered_member(cls, member: dict[str, Any]) -> bool:
        return bool(cls._normalize_member_phone(member.get("phone")))

    @classmethod
    def _session_identity_values(cls, preferences: dict[str, Any]) -> set[str]:
        values: set[str] = set()
        for key in (
            "user_id",
            "uid",
            "canonical_uid",
            "canonical_user_id",
            "member_id",
            "phone",
            "openid",
            "wx_openid",
            "unionid",
            "wx_unionid",
        ):
            normalized = cls._normalize_member_identity(preferences.get(key))
            if normalized:
                values.add(normalized)
        return values

    def _registered_member_identity_index(self) -> dict[str, str]:
        try:
            members = self._load_all_members()
        except Exception:
            logger.warning("Failed to load member identities for BI activity scope", exc_info=True)
            return {}
        identity_index: dict[str, str] = {}
        for member in members:
            if not self._normalize_member_phone(member.get("phone")):
                continue
            canonical = (
                str(member.get("canonical_user_id") or "").strip()
                or str(member.get("user_id") or "").strip()
            )
            if not canonical:
                continue
            for identity in self._member_identity_values(member):
                identity_index[identity] = canonical
        return identity_index

    def _resolve_registered_actor_id(
        self,
        preferences: dict[str, Any],
        identity_index: dict[str, str],
    ) -> str:
        for identity in self._session_identity_values(preferences):
            canonical = identity_index.get(identity)
            if canonical:
                return canonical
        return ""

    def _scope_context_to_registered_members(self, context: _BiContext) -> _BiContext:
        identity_index = self._registered_member_identity_index()
        if not identity_index:
            return _BiContext(
                sessions=[],
                turns=[],
                result_events=[],
                tool_events=[],
                notebook_entries=[],
                truncated_collections=context.truncated_collections,
            )

        sessions: list[dict[str, Any]] = []
        session_ids: set[str] = set()
        for session in context.sessions:
            canonical = self._resolve_registered_actor_id(session.get("preferences") or {}, identity_index)
            if not canonical:
                continue
            payload = dict(session)
            preferences = dict(payload.get("preferences") or {})
            preferences["_bi_registered_actor_id"] = canonical
            payload["preferences"] = preferences
            sessions.append(payload)
            session_ids.add(str(payload.get("session_id") or payload.get("id") or ""))

        turn_ids: set[str] = set()
        turns: list[dict[str, Any]] = []
        for turn in context.turns:
            if str(turn.get("session_id") or "") not in session_ids:
                continue
            canonical = self._resolve_registered_actor_id(turn.get("preferences") or {}, identity_index)
            payload = dict(turn)
            preferences = dict(payload.get("preferences") or {})
            if canonical:
                preferences["_bi_registered_actor_id"] = canonical
            payload["preferences"] = preferences
            turns.append(payload)
            turn_ids.add(str(turn.get("id") or ""))

        result_events = [event for event in context.result_events if str(event.get("turn_id") or "") in turn_ids]
        tool_events = [event for event in context.tool_events if str(event.get("turn_id") or "") in turn_ids]
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
            truncated_collections=context.truncated_collections,
        )

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
                preferences = session.get("preferences") or {}
                identities = self._session_identity_values(preferences)
                registered_actor_id = self._normalize_member_identity(preferences.get("_bi_registered_actor_id"))
                if registered_actor_id:
                    identities.add(registered_actor_id)
                if not identities or not any(tier_map.get(identity, "") == filters.tier for identity in identities):
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
            truncated_collections=context.truncated_collections,
        )

    @staticmethod
    def _build_daily_cost_payload(context: _BiContext, *, days: int) -> dict[str, Any]:
        window_days = max(1, int(days or 1))
        today = datetime.fromtimestamp(time.time())
        start_date = today.date() - timedelta(days=window_days - 1)
        buckets: dict[str, dict[str, Any]] = {}
        for offset in range(window_days):
            day = start_date + timedelta(days=offset)
            key = day.isoformat()
            buckets[key] = {
                "date": key,
                "label": day.strftime("%m-%d"),
                "cost_usd": 0.0,
                "tokens": 0,
                "turns": 0,
            }

        for event in context.result_events:
            cost_summary = event.get("cost_summary") or {}
            cost = _safe_float(cost_summary.get("total_cost_usd"))
            tokens = _safe_int(cost_summary.get("total_tokens"))
            if cost <= 0 and tokens <= 0:
                continue
            key = _date_bucket(_safe_float(event.get("created_at")))
            if key not in buckets:
                continue
            buckets[key]["cost_usd"] += cost
            buckets[key]["tokens"] += tokens
            buckets[key]["turns"] += 1

        series = [
            {
                "date": item["date"],
                "label": item["label"],
                "cost_usd": _round(item["cost_usd"], 4),
                "tokens": item["tokens"],
                "turns": item["turns"],
            }
            for item in buckets.values()
        ]
        today_key = today.date().isoformat()
        window_total = sum(item["cost_usd"] for item in series)
        return {
            "today_usd": _round(buckets.get(today_key, {}).get("cost_usd", 0.0), 4),
            "window_total_usd": _round(window_total, 4),
            "average_daily_usd": _round(window_total / window_days, 4),
            "series": series,
            "source": "turn_result_cost_summary",
        }

    @staticmethod
    def _build_boss_workbench_payload(
        *,
        overview_cards: list[dict[str, Any]],
        member_dashboard: dict[str, Any],
        member_stats: dict[str, Any],
        risk_alerts: list[str],
        daily_cost: dict[str, Any],
    ) -> dict[str, Any]:
        average_daily_cost = _safe_float(daily_cost.get("average_daily_usd"))
        today_cost = _safe_float(daily_cost.get("today_usd"))
        cost_tone = "warning" if average_daily_cost > 0 and today_cost > average_daily_cost * 1.5 else "neutral"
        cost_kpi = {
            "label": "今日成本",
            "value": _round(today_cost, 4),
            "hint": f"窗口合计 ${_round(_safe_float(daily_cost.get('window_total_usd')), 4)} · 日均 ${_round(average_daily_cost, 4)}",
            "tone": cost_tone,
            "source": "cost",
        }
        risk_queue = [
            {
                "bucket": "expiring_soon",
                "label": "即将到期会员",
                "count": _safe_int(member_dashboard.get("expiring_soon_count")),
                "detail": "建议优先进入会员运营页处理续费窗口。",
                "handoff_filters": {"expire_within_days": 7},
            },
            {
                "bucket": "high_risk",
                "label": "高风险会员",
                "count": _safe_int(member_dashboard.get("churn_risk_count")),
                "detail": "建议优先查看高风险与沉默用户。",
                "handoff_filters": {"risk_level": "high"},
            },
        ]
        if cost_tone == "warning":
            risk_queue.append(
                {
                    "bucket": "daily_cost",
                    "label": "今日成本偏高",
                    "count": _round(today_cost, 4),
                    "detail": "建议查看成本模块，确认 Langfuse usage 采集里的模型与 token 波动。",
                    "handoff_filters": {},
                }
            )
        return {
            "kpis": [cost_kpi, *[card for card in overview_cards if card.get("label") != "今日成本"][:5]],
            "risk_queue": risk_queue,
            "watchlist": list(member_stats.get("samples") or [])[:6],
            "hero_issue": risk_alerts[0] if risk_alerts else "",
            "daily_cost": daily_cost,
        }

    @staticmethod
    def _metric_definition_payload(metric_id: str) -> dict[str, Any]:
        metric = metric_by_id(metric_id)
        return asdict(metric)

    def _effective_learning_actor_ids(self, context: _BiContext) -> set[str]:
        sessions_by_id = {
            str(session.get("session_id") or session.get("id") or ""): session
            for session in context.sessions
        }
        turn_session_ids = {
            str(turn.get("id") or ""): str(turn.get("session_id") or "")
            for turn in context.turns
        }
        effective_session_ids = {
            str(turn.get("session_id") or "")
            for turn in context.turns
            if str(turn.get("status") or "").strip().lower() == "completed"
        }
        effective_session_ids.update(
            turn_session_ids.get(str(event.get("turn_id") or ""), "")
            for event in context.result_events
        )
        effective_session_ids.update(
            str(entry.get("session_id") or "")
            for entry in context.notebook_entries
        )

        actor_ids: set[str] = set()
        for session_id in effective_session_ids:
            session = sessions_by_id.get(session_id)
            if not session:
                continue
            actor_id = self._resolve_actor_id(session_id, session.get("preferences") or {})
            if actor_id:
                actor_ids.add(actor_id)
        return actor_ids

    @classmethod
    def _build_north_star_payload(
        cls,
        *,
        summary: dict[str, Any],
        member_dashboard: dict[str, Any],
        days: int,
    ) -> dict[str, Any]:
        metric = cls._metric_definition_payload("effective_learning_members")
        value = _safe_int(summary.get("active_learners"))
        return {
            **metric,
            "value": value,
            "window_days": days,
            "calculation": "真实手机号会员范围内，窗口内至少产生一次有效学习会话的去重会员数。",
            "inputs": [
                {
                    **cls._metric_definition_payload("registered_members"),
                    "value": _safe_int(member_dashboard.get("total_count")),
                },
                {
                    **cls._metric_definition_payload("activated_members"),
                    "value": value,
                },
                {
                    **cls._metric_definition_payload("cost_per_effective_learning"),
                    "value": None,
                },
            ],
        }

    @classmethod
    def _build_growth_funnel_payload(
        cls,
        *,
        summary: dict[str, Any],
        member_dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        registered = _safe_int(member_dashboard.get("total_count"))
        activated = _safe_int(summary.get("active_learners"))
        effective = activated

        def step(metric_id: str, value: int, previous: int | None, label_override: str | None = None) -> dict[str, Any]:
            metric = cls._metric_definition_payload(metric_id)
            denominator = previous if previous is not None else value
            conversion = _round(value / max(denominator, 1) * 100, 1)
            return {
                "id": metric_id,
                "label": label_override or metric["label"],
                "value": value,
                "conversion_rate": conversion,
                "trust_level": metric["trust_level"],
                "authority": metric["authority"],
                "drilldown": metric["drilldown"],
            }

        return {
            "title": "增长漏斗",
            "summary": "第一阶段使用真实会员和有效学习会话做保守漏斗，收入/付费 authority 未确认前不展示利润式转化。",
            "steps": [
                step("registered_members", registered, None),
                step("activated_members", activated, registered),
                step("effective_learning_members", effective, activated),
            ],
            "pending_steps": [
                {
                    "id": "paid_or_entitled_members",
                    "label": "付费/权益会员",
                    "status": "pending_authority",
                    "detail": "收入、权益和钱包 authority 未确认前不进入正式漏斗。",
                }
            ],
        }

    @classmethod
    def _build_member_health_payload(
        cls,
        *,
        member_dashboard: dict[str, Any],
        member_stats: dict[str, Any],
    ) -> dict[str, Any]:
        metric = cls._metric_definition_payload("member_health_score")
        health_score = _safe_int(member_dashboard.get("health_score"))
        churn_risk = _safe_int(member_dashboard.get("churn_risk_count"))
        expiring_soon = _safe_int(member_dashboard.get("expiring_soon_count"))
        return {
            "score": {
                **metric,
                "value": health_score,
                "note": "第一阶段为透明规则评分；样本不足时按风险标签和原因解释，不作为黑箱预测。",
            },
            "distribution": [
                {"bucket": "healthy", "label": "健康", "count": _safe_int(member_dashboard.get("active_count"))},
                {"bucket": "risk", "label": "风险", "count": churn_risk},
                {"bucket": "critical", "label": "即将到期", "count": expiring_soon},
            ],
            "reasons": list(member_dashboard.get("recommendations") or [])[:4],
            "samples": list(member_stats.get("samples") or [])[:6],
        }

    @staticmethod
    def _extract_chapter_mastery(member: dict[str, Any]) -> dict[str, Any]:
        mastery = member.get("chapter_mastery")
        return mastery if isinstance(mastery, dict) else {}

    @classmethod
    def _build_chapter_progress_payload(cls, members: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for member in members:
            for key, value in cls._extract_chapter_mastery(member).items():
                if not isinstance(value, dict):
                    continue
                name = str(value.get("name") or key or "").strip()
                if not name:
                    continue
                mastery = max(0, min(100, _safe_int(value.get("mastery"))))
                bucket = grouped.setdefault(
                    name,
                    {
                        "chapter_id": str(key or name),
                        "name": name,
                        "masteries": [],
                    },
                )
                bucket["masteries"].append(mastery)

        progress = []
        for bucket in grouped.values():
            masteries = list(bucket["masteries"])
            if not masteries:
                continue
            average_mastery = round(sum(masteries) / len(masteries))
            progress.append(
                {
                    "chapter_id": bucket["chapter_id"],
                    "name": bucket["name"],
                    "mastery": average_mastery,
                    "member_count": len(masteries),
                    "status": "weak" if average_mastery < 60 else "stable",
                    "evidence": f"{len(masteries)} 名真实会员样本平均掌握度 {average_mastery}%",
                }
            )
        progress.sort(key=lambda item: (item["mastery"], item["name"]))
        return progress[:8]

    @staticmethod
    def _build_operating_rhythm_payload(risk_alerts: list[str]) -> dict[str, Any]:
        top_actions: list[dict[str, Any]] = []
        for text in risk_alerts[:3]:
            if "到期" in text:
                target = "member_ops"
            elif "失败回合" in text:
                target = "ai_quality"
            elif "数据" in text:
                target = "data_trust"
            else:
                target = "member_ops"
            top_actions.append(
                {
                    "title": text,
                    "target": target,
                    "status": "open",
                    "reason": "来自 BI 聚合风险队列",
                }
            )
        if not top_actions:
            top_actions.append(
                {
                    "title": "查看真实会员、成本和 AI 质量是否稳定",
                    "target": "data_trust",
                    "status": "open",
                    "reason": "每日晨会默认检查项",
                }
            )
        return {
            "cadences": [
                {"id": "daily", "label": "每日晨会", "focus": "新增真实会员、有效学习、成本、失败回合、待办"},
                {"id": "weekly", "label": "每周复盘", "focus": "漏斗掉点、会员健康、教学效果、AI 质量样本"},
                {"id": "release", "label": "发布后观察", "focus": "按 release/version 对比成本、失败率、质量、留存"},
            ],
            "top_actions": top_actions[:3],
        }

    @classmethod
    def _build_teaching_effect_payload(
        cls,
        *,
        summary: dict[str, Any],
        member_stats: dict[str, Any],
    ) -> dict[str, Any]:
        metric = cls._metric_definition_payload("mastery_improvement")
        chapter_progress = list(member_stats.get("chapter_progress") or [])
        return {
            "status": "partial" if chapter_progress else "degraded",
            "summary": "学习成果 authority 尚未完整核验；第一阶段先使用真实会员章节掌握度、有效学习会话和 Notebook/错题沉淀做保守展示。",
            "metrics": [
                {
                    **metric,
                    "value": chapter_progress[0]["mastery"] if chapter_progress else None,
                    "status": "chapter_progress_available" if chapter_progress else "pending_source_validation",
                },
                {
                    "metric_id": "notebook_saves",
                    "label": "Notebook 保存",
                    "value": _safe_int(summary.get("notebook_saves")),
                    "trust_level": "B",
                    "authority": "sqlite_session_store",
                    "drilldown": "student_360",
                },
            ],
            "chapter_progress": chapter_progress,
        }

    @classmethod
    def _build_ai_quality_payload(
        cls,
        *,
        summary: dict[str, Any],
        context: _BiContext,
    ) -> dict[str, Any]:
        metric = cls._metric_definition_payload("ai_quality_score")
        failed_turns = sum(1 for turn in context.turns if turn.get("status") == "failed")
        return {
            **metric,
            "engineering_success_rate": _safe_float(summary.get("success_turn_rate")),
            "failed_turns": failed_turns,
            "total_turns": _safe_int(summary.get("total_turns")),
            "teaching_success_status": "sample_required",
            "note": "工程成功率不等于教学质量；需要继续接入反馈、纠错和人工抽检样本。",
            "samples": [
                {
                    "turn_id": turn.get("turn_id") or turn.get("id"),
                    "session_id": turn.get("session_id"),
                    "status": turn.get("status"),
                }
                for turn in context.turns
                if turn.get("status") == "failed"
            ][:5],
        }

    @classmethod
    def _build_unit_economics_payload(
        cls,
        *,
        summary: dict[str, Any],
        daily_cost: dict[str, Any],
    ) -> dict[str, Any]:
        metric = cls._metric_definition_payload("cost_per_effective_learning")
        effective_members = _safe_int(summary.get("active_learners"))
        window_cost = _safe_float(daily_cost.get("window_total_usd"))
        cost_per_effective = window_cost / effective_members if effective_members else 0.0
        return {
            **metric,
            "revenue_status": "pending",
            "summary": "收入事实未接入，当前只展示成本侧单位经济模型。",
            "window_total_cost_usd": _round(window_cost, 4),
            "cost_per_effective_learning_usd": _round(cost_per_effective, 4),
            "source": daily_cost.get("source") or "turn_result_cost_summary",
        }

    @classmethod
    def _build_data_trust_payload(cls, *, context: _BiContext) -> dict[str, Any]:
        degraded_modules = [
            {
                "id": "revenue",
                "label": "收入 authority",
                "status": "pending",
                "detail": "支付、钱包和手工开通记录尚未确认单一 revenue authority。",
            },
            {
                "id": "learning_outcome",
                "label": "学习成果 authority",
                "status": "partial",
                "detail": "练题、复习、错题和章节掌握度需要继续做样本核验。",
            },
        ]
        if context.truncated_collections:
            degraded_modules.append(
                {
                    "id": "collection_limits",
                    "label": "BI 聚合行数截断",
                    "status": "degraded",
                    "detail": ",".join(context.truncated_collections),
                }
            )
        return {
            "status": "ready",
            "trust_model": "A/B 可用于首页决策；C/D 必须降级或待接入展示。",
            "degraded_modules": degraded_modules,
            "metric_definitions": [asdict(metric) for metric in BI_METRICS],
        }

    @staticmethod
    def _load_limited_rows(
        conn: sqlite3.Connection,
        query: str,
        params: tuple[Any, ...],
        *,
        limit: int,
        label: str,
    ) -> tuple[list[sqlite3.Row], bool]:
        rows = conn.execute(f"{query}\nLIMIT ?", (*params, limit + 1)).fetchall()
        truncated = len(rows) > limit
        if truncated:
            logger.warning(
                "BI context truncated for %s at %s rows; narrow filters or shorten window",
                label,
                limit,
            )
            rows = rows[:limit]
        return list(rows), truncated

    async def _load_context_since(self, window_start: float) -> _BiContext:
        row_limit = max(1, int(_BI_CONTEXT_ROW_LIMIT))
        with self._connect() as conn:
            session_rows, sessions_truncated = self._load_limited_rows(
                conn,
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
                limit=row_limit,
                label="sessions",
            )

            turn_rows, turns_truncated = self._load_limited_rows(
                conn,
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
                limit=row_limit,
                label="turns",
            )

            result_rows, results_truncated = self._load_limited_rows(
                conn,
                """
                SELECT
                    te.turn_id,
                    te.seq,
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
                limit=row_limit,
                label="result_events",
            )

            tool_rows, tools_truncated = self._load_limited_rows(
                conn,
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
                limit=row_limit,
                label="tool_events",
            )

            notebook_rows, notebook_truncated = self._load_limited_rows(
                conn,
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
                limit=row_limit,
                label="notebook_entries",
            )

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
        truncated_collections = tuple(
            label
            for label, truncated in (
                ("sessions", sessions_truncated),
                ("turns", turns_truncated),
                ("result_events", results_truncated),
                ("tool_events", tools_truncated),
                ("notebook_entries", notebook_truncated),
            )
            if truncated
        )
        return _BiContext(
            sessions=sessions,
            turns=turns,
            result_events=result_events,
            tool_events=tool_events,
            notebook_entries=notebook_entries,
            truncated_collections=truncated_collections,
        )

    async def _load_context(self, days: int) -> _BiContext:
        return await self._load_context_since(self._window_start(days))

    def _load_all_members(self) -> list[dict[str, Any]]:
        list_members_for_bi = getattr(self._member_service, "list_members_for_bi", None)
        if callable(list_members_for_bi):
            return list(list_members_for_bi())
        first_page = self._member_service.list_members(page=1, page_size=200)
        items = list(first_page["items"])
        for page in range(2, int(first_page.get("pages") or 1) + 1):
            current = self._member_service.list_members(page=page, page_size=200)
            items.extend(current["items"])
        return items

    @staticmethod
    def _build_member_dashboard_from_items(
        members: list[dict[str, Any]],
        *,
        days: int,
    ) -> dict[str, Any]:
        now = datetime.now().astimezone()
        active_count = sum(1 for item in members if item.get("status") == "active")
        expiring_soon_count = 0
        new_today_count = 0
        churn_risk_count = 0
        tiers: Counter[str] = Counter()
        expiry_buckets: Counter[str] = Counter()
        auto_renew_count = 0

        for item in members:
            expire_at_raw = str(item.get("expire_at") or "").strip()
            created_at_raw = str(item.get("created_at") or "").strip()
            risk_level = str(item.get("risk_level") or "")
            tier = str(item.get("tier") or "unknown")
            auto_renew_count += 1 if item.get("auto_renew") else 0
            tiers[tier] += 1
            if risk_level == "high":
                churn_risk_count += 1
            if expire_at_raw:
                try:
                    expire_at = datetime.fromisoformat(expire_at_raw.replace("Z", "+00:00"))
                    # Use calendar-day distance for member ops dashboards.
                    # `timedelta.days` floors partial days and can incorrectly
                    # pull nearly-8-day expiries into the "7 days" queue.
                    expire_in_days = (expire_at.date() - now.date()).days
                    if 0 <= expire_in_days <= 7:
                        expiring_soon_count += 1
                    expiry_buckets[expire_at.strftime("%m-%d")] += 1
                except ValueError:
                    pass
            if created_at_raw:
                try:
                    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                    if (now - created_at).days <= 1:
                        new_today_count += 1
                except ValueError:
                    pass

        recommendations: list[str] = []
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
            "admin_ops": {"window_days": days, "total": 0, "by_action": []},
            "recommendations": recommendations,
        }

    async def _load_feedback_records(self, days: int) -> tuple[str, list[dict[str, Any]]]:
        if not self._feedback_store.is_configured:
            return "unconfigured", []
        created_after = datetime.fromtimestamp(self._window_start(days)).astimezone().isoformat()
        rows: list[dict[str, Any]] = []
        page_size = 200
        max_records = 2000
        offset = 0
        try:
            while len(rows) < max_records:
                batch = await self._feedback_store.list_feedback(
                    created_after=created_after,
                    limit=min(page_size, max_records - len(rows)),
                    offset=offset,
                )
                if not batch:
                    break
                rows.extend(batch)
                if len(batch) < page_size:
                    break
                offset += len(batch)
        except Exception:
            logger.exception("Failed to load feedback records from Supabase")
            return "error", []
        return "ok", [
            normalize_feedback_record(row)
            for row in rows
            if is_deeptutor_feedback_record(row)
        ]

    async def get_overview(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        context = self._apply_filters(
            self._scope_context_to_registered_members(await self._load_context(days)),
            self._normalize_filters(capability, entrypoint, tier),
        )

        active_actors = self._effective_learning_actor_ids(context)
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

        member_stats = await self.get_member_stats(
            days=days,
            capability=capability,
            entrypoint=entrypoint,
            tier=tier,
        )
        member_dashboard = member_stats.get("dashboard", {})
        daily_cost = self._build_daily_cost_payload(context, days=days)

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
        cards = [
            {"label": "活跃学习会话", "value": summary["total_sessions"], "hint": f"{days} 天窗口内更新过的会话"},
            {"label": "活跃学习者", "value": summary["active_learners"], "hint": "按用户或匿名会话去重"},
            {"label": "回合成功率", "value": f"{summary['success_turn_rate']}%", "hint": f"总回合 {summary['total_turns']}"},
            {"label": "平均会话深度", "value": summary["avg_session_depth"], "hint": "每个会话平均消息数"},
            {"label": "Notebook 保存", "value": summary["notebook_saves"], "hint": "问题笔记沉淀量"},
            {"label": "总成本", "value": summary["total_cost_usd"], "hint": f"总 Token {summary['total_tokens']}"},
        ]

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
            "cards": cards,
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
            "boss_workbench": self._build_boss_workbench_payload(
                overview_cards=cards,
                member_dashboard=member_dashboard,
                member_stats=member_stats,
                risk_alerts=risk_alerts,
                daily_cost=daily_cost,
            ),
            "north_star": self._build_north_star_payload(
                summary=summary,
                member_dashboard=member_dashboard,
                days=days,
            ),
            "growth_funnel": self._build_growth_funnel_payload(
                summary=summary,
                member_dashboard=member_dashboard,
            ),
            "member_health": self._build_member_health_payload(
                member_dashboard=member_dashboard,
                member_stats=member_stats,
            ),
            "operating_rhythm": self._build_operating_rhythm_payload(risk_alerts),
            "teaching_effect": self._build_teaching_effect_payload(
                summary=summary,
                member_stats=member_stats,
            ),
            "ai_quality": self._build_ai_quality_payload(summary=summary, context=context),
            "unit_economics": self._build_unit_economics_payload(summary=summary, daily_cost=daily_cost),
            "data_trust": self._build_data_trust_payload(context=context),
        }

    async def get_active_trend(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        context = self._apply_filters(
            self._scope_context_to_registered_members(await self._load_context(days)),
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
            self._scope_context_to_registered_members(await self._load_context(days)),
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
        members = [
            item
            for item in self._load_all_members()
            if self._is_registered_member(item)
        ]
        tier_filter = str(tier or "").strip().lower()
        if tier_filter:
            members = [
                item for item in members if str(item.get("tier") or "").strip().lower() == tier_filter
            ]
        dashboard = self._build_member_dashboard_from_items(members, days=days)
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
            "chapter_progress": self._build_chapter_progress_payload(members),
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

    async def backfill_usage_ledger(
        self,
        *,
        days: int = 3650,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
        provider_name: str = "dashscope",
    ) -> dict[str, Any]:
        window_start = self._window_start(days)
        now_ts = time.time()
        context = self._apply_filters(
            await self._load_context_since(window_start),
            self._normalize_filters(capability, entrypoint, tier),
        )
        provider_label = str(provider_name or "").strip()
        scanned = 0
        inserted = 0
        measured_inserted = 0
        estimated_inserted = 0
        skipped_existing_turns = 0

        for event in context.result_events:
            scanned += 1
            if self._usage_ledger.has_usage_for_turn(str(event.get("turn_id") or "")):
                skipped_existing_turns += 1
                continue
            cost_summary = event.get("cost_summary") or {}
            rollup = self._rollup_cost_summary(cost_summary)
            scope_id = str(
                cost_summary.get("scope_id") or f"turn:{str(event.get('turn_id') or '').strip()}"
            ).strip()
            event_identity = (
                f"{str(event.get('turn_id') or '').strip()}:"
                f"{_safe_int(event.get('seq'))}:"
                f"{int(round(_safe_float(event.get('created_at')) * 1000))}"
            )
            model_name = self._pick_backfill_model(cost_summary)
            common_metadata = {
                "provider_name": provider_label,
                "backfill_source": "turn_result_cost_summary",
                "backfill_event_identity": event_identity,
                "backfill_usage_accuracy": str(cost_summary.get("usage_accuracy") or "").strip(),
                "backfill_models": cost_summary.get("models") or {},
                "backfill_usage_sources": cost_summary.get("usage_sources") or {},
            }

            if rollup.measured_total_tokens > 0 or rollup.measured_total_cost > 0:
                inserted_now = self._usage_ledger.record_usage_event(
                    usage_source="provider",
                    usage_details={
                        "input": float(rollup.measured_input_tokens),
                        "output": float(rollup.measured_output_tokens),
                        "total": float(rollup.measured_total_tokens),
                    },
                    cost_details={"total": float(rollup.measured_total_cost)},
                    model=model_name,
                    metadata=common_metadata,
                    session_id=str(event.get("session_id") or ""),
                    turn_id=str(event.get("turn_id") or ""),
                    capability=str(event.get("capability") or ""),
                    scope_id=scope_id,
                    dedupe_key=f"turn-result-backfill:{event_identity}:measured",
                    created_at=_safe_float(event.get("created_at")),
                )
                if inserted_now:
                    inserted += 1
                    measured_inserted += 1

            if rollup.estimated_total_tokens > 0 or rollup.estimated_total_cost > 0:
                inserted_now = self._usage_ledger.record_usage_event(
                    usage_source="tiktoken",
                    usage_details={
                        "input": float(rollup.estimated_input_tokens),
                        "output": float(rollup.estimated_output_tokens),
                        "total": float(rollup.estimated_total_tokens),
                    },
                    cost_details={"total": float(rollup.estimated_total_cost)},
                    model=model_name,
                    metadata=common_metadata,
                    session_id=str(event.get("session_id") or ""),
                    turn_id=str(event.get("turn_id") or ""),
                    capability=str(event.get("capability") or ""),
                    scope_id=scope_id,
                    dedupe_key=f"turn-result-backfill:{event_identity}:estimated",
                    created_at=_safe_float(event.get("created_at")),
                )
                if inserted_now:
                    inserted += 1
                    estimated_inserted += 1

        return {
            "status": "ok",
            "window_days": days,
            "time_range": {"start_ts": window_start, "end_ts": now_ts},
            "filters": {
                "capability": str(capability or "").strip().lower(),
                "entrypoint": str(entrypoint or "").strip().lower(),
                "tier": str(tier or "").strip().lower(),
                "provider_name": provider_label,
            },
            "scanned_result_events": scanned,
            "inserted_ledger_events": inserted,
            "inserted_measured_events": measured_inserted,
            "inserted_estimated_events": estimated_inserted,
            "skipped_existing_turns": skipped_existing_turns,
        }

    async def get_cost_reconciliation(
        self,
        days: int = 30,
        capability: str | None = None,
        entrypoint: str | None = None,
        tier: str | None = None,
        workspace_id: str | None = None,
        apikey_id: str | None = None,
        model: str | None = None,
        billing_cycle: str | None = None,
    ) -> dict[str, Any]:
        window_start = self._window_start(days)
        now_ts = time.time()
        filters = self._normalize_filters(capability, entrypoint, tier)
        explicit_billing_cycle = self._normalize_billing_cycle(billing_cycle)
        billing_cycles = (
            [explicit_billing_cycle]
            if explicit_billing_cycle
            else self._iter_billing_cycles(window_start, now_ts)
        )

        context = self._apply_filters(await self._load_context(days), filters)

        system_measured_input = 0
        system_measured_output = 0
        system_measured_total = 0
        system_measured_cost = 0.0
        system_estimated_input = 0
        system_estimated_output = 0
        system_estimated_total = 0
        system_estimated_cost = 0.0
        system_models = Counter()
        system_sources = Counter()
        for event in context.result_events:
            cost_summary = event.get("cost_summary") or {}
            rollup = self._rollup_cost_summary(cost_summary)
            system_measured_input += rollup.measured_input_tokens
            system_measured_output += rollup.measured_output_tokens
            system_measured_total += rollup.measured_total_tokens
            system_measured_cost += rollup.measured_total_cost
            system_estimated_input += rollup.estimated_input_tokens
            system_estimated_output += rollup.estimated_output_tokens
            system_estimated_total += rollup.estimated_total_tokens
            system_estimated_cost += rollup.estimated_total_cost
            for name, count in (cost_summary.get("models") or {}).items():
                system_models[str(name)] += _safe_int(count)
            for name, count in (cost_summary.get("usage_sources") or {}).items():
                system_sources[str(name)] += _safe_int(count)

        system_input = system_measured_input + system_estimated_input
        system_output = system_measured_output + system_estimated_output
        system_total = system_measured_total + system_estimated_total
        system_cost = system_measured_cost + system_estimated_cost

        telemetry_status = "unconfigured"
        bailian_payload: dict[str, Any] = {
            "status": telemetry_status,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "models": {},
        }
        billing_status = "unconfigured"
        bailian_billing_payload: dict[str, Any] = {
            "status": billing_status,
            "billing_cycles": billing_cycles,
            "pretax_amount": 0.0,
            "after_discount_amount": 0.0,
            "items_count": 0,
            "currency": "CNY",
            "model_amounts": {},
            "usage_kind_amounts": {},
        }
        system_global_payload: dict[str, Any] = {
            "status": "ok",
            "provider_name": "dashscope",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "measured_input_tokens": 0,
            "measured_output_tokens": 0,
            "measured_total_tokens": 0,
            "measured_total_cost_usd": 0.0,
            "estimated_input_tokens": 0,
            "estimated_output_tokens": 0,
            "estimated_total_tokens": 0,
            "estimated_total_cost_usd": 0.0,
            "events": 0,
            "coverage_start_ts": None,
            "coverage_end_ts": None,
        }
        warnings: list[str] = []
        try:
            system_global_totals = self._usage_ledger.get_totals(
                start_ts=window_start,
                end_ts=now_ts,
                provider_name="dashscope",
                model=model,
            )
            system_global_totals_dict = (
                system_global_totals.to_dict()
                if hasattr(system_global_totals, "to_dict")
                else dict(system_global_totals or {})
            )
            system_global_payload = {
                "status": "ok",
                "provider_name": "dashscope",
                **system_global_totals_dict,
            }
            coverage_start_ts = system_global_totals_dict.get(
                "coverage_start_ts",
                getattr(system_global_totals, "coverage_start_ts", None),
            )
            if (
                coverage_start_ts is None
                or float(coverage_start_ts) > float(window_start)
            ):
                warnings.append("全量 LLM usage ledger 尚未覆盖整个查询窗口；system_global_bailian 仅代表新账期/新部署后的调用。")
        except Exception as exc:
            logger.exception("Failed to query usage ledger")
            system_global_payload = {
                "status": "error",
                "provider_name": "dashscope",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "measured_input_tokens": 0,
                "measured_output_tokens": 0,
                "measured_total_tokens": 0,
                "measured_total_cost_usd": 0.0,
                "estimated_input_tokens": 0,
                "estimated_output_tokens": 0,
                "estimated_total_tokens": 0,
                "estimated_total_cost_usd": 0.0,
                "events": 0,
                "coverage_start_ts": None,
                "coverage_end_ts": None,
                "error": str(exc),
            }
            warnings.append("全量 LLM usage ledger 查询失败，system_global_bailian 不可用。")
        telemetry_config = getattr(self._bailian_telemetry_client, "config", None)
        billing_config = getattr(self._bailian_billing_client, "config", None)
        effective_workspace_id = str(
            workspace_id
            or getattr(telemetry_config, "workspace_id", "")
            or getattr(billing_config, "workspace_id", "")
            or ""
        ).strip()
        effective_apikey_id = str(
            apikey_id
            or getattr(telemetry_config, "apikey_id", "")
            or getattr(billing_config, "apikey_id", "")
            or ""
        ).strip()
        if not self._bailian_telemetry_client.is_configured():
            warnings.append("百炼 Prometheus 监控未配置，无法查询外部账。")
        else:
            try:
                bailian_totals = await self._bailian_telemetry_client.get_usage_totals(
                    start_ts=window_start,
                    end_ts=now_ts,
                    workspace_id=effective_workspace_id,
                    apikey_id=effective_apikey_id,
                    model=model,
                )
                telemetry_status = "ok"
                bailian_payload = {
                    "status": telemetry_status,
                    **bailian_totals.to_dict(),
                }
            except Exception as exc:
                logger.exception("Failed to query Bailian telemetry")
                telemetry_status = "error"
                bailian_payload = {
                    "status": telemetry_status,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "models": {},
                    "error": str(exc),
                }
                warnings.append("百炼 Prometheus 查询失败，请检查地址、AK/SK 和实例权限。")

        if not self._bailian_billing_client.is_configured():
            warnings.append("百炼官方账单接口未配置，无法查询金额账。")
        else:
            try:
                bailian_billing_totals = await self._bailian_billing_client.get_totals(
                    billing_cycles=billing_cycles,
                    workspace_id=effective_workspace_id,
                    apikey_id=effective_apikey_id,
                    model=model,
                )
                billing_status = "ok"
                bailian_billing_payload = {
                    "status": billing_status,
                    **bailian_billing_totals.to_dict(),
                }
            except Exception as exc:
                logger.exception("Failed to query Bailian billing")
                billing_status = "error"
                bailian_billing_payload = {
                    "status": billing_status,
                    "billing_cycles": billing_cycles,
                    "pretax_amount": 0.0,
                    "after_discount_amount": 0.0,
                    "items_count": 0,
                    "currency": "CNY",
                    "model_amounts": {},
                    "usage_kind_amounts": {},
                    "error": str(exc),
                }
                warnings.append("百炼官方账单查询失败，请检查 AK/SK、BssOpenApi 依赖和权限。")

        token_delta = system_total - _safe_int(bailian_payload.get("total_tokens"))
        input_delta = system_input - _safe_int(bailian_payload.get("input_tokens"))
        output_delta = system_output - _safe_int(bailian_payload.get("output_tokens"))
        cost_delta = _round(
            system_cost - _safe_float(bailian_payload.get("estimated_total_cost_usd")),
            8,
        )
        if telemetry_status == "ok" and not effective_apikey_id:
            warnings.append("当前未按 apikey_id 过滤百炼外部账，结果可能包含控制台或其他调用。")
        if billing_status == "ok" and not effective_apikey_id:
            warnings.append("当前未按 apikey_id 过滤百炼官方账单，金额可能包含其他 API Key 的调用。")
        if telemetry_status == "ok" and model:
            warnings.append("系统内账当前只有回合级总 token，model 过滤主要作用于百炼外部账。")
        if billing_status == "ok" and not explicit_billing_cycle:
            warnings.append("百炼官方账单按账期（月）聚合；若要做精确金额对账，请显式传入 billing_cycle=YYYY-MM。")
        if billing_status == "ok" and (filters.capability or filters.entrypoint or filters.tier):
            warnings.append("百炼官方账单不支持 capability/entrypoint/tier 维度过滤；金额对账以 workspace_id/apikey_id/model 为准。")
        if billing_status == "ok" and explicit_billing_cycle:
            current_cycle = datetime.fromtimestamp(now_ts).strftime("%Y-%m")
            if explicit_billing_cycle == current_cycle:
                warnings.append("当前账期官方账单存在结算延迟，月内数据仅供参考；精确金额请以下月已结账数据为准。")

        billing_scope_system_cost = None
        billing_cost_delta = None
        billing_cost_delta_ratio = None
        if explicit_billing_cycle:
            cycle_start_ts, cycle_end_ts = self._billing_cycle_bounds(explicit_billing_cycle)
            cycle_context = context
            if cycle_start_ts < window_start:
                cycle_context = self._apply_filters(await self._load_context_since(cycle_start_ts), filters)

            billing_scope_system_cost = 0.0
            for event in cycle_context.result_events:
                event_ts = _safe_float(event.get("created_at"))
                if event_ts < cycle_start_ts or event_ts >= cycle_end_ts:
                    continue
                rollup = self._rollup_cost_summary(event.get("cost_summary") or {})
                billing_scope_system_cost += rollup.effective_total_cost

            if billing_status == "ok":
                billing_cost_delta = _round(
                    billing_scope_system_cost - _safe_float(bailian_billing_payload.get("pretax_amount")),
                    8,
                )
                if _safe_float(bailian_billing_payload.get("pretax_amount")) > 0:
                    billing_cost_delta_ratio = _round(
                        billing_cost_delta / _safe_float(bailian_billing_payload.get("pretax_amount")),
                        6,
                    )

        return {
            "window_days": days,
            "time_range": {
                "start_ts": window_start,
                "end_ts": now_ts,
            },
            "filters": {
                "capability": str(capability or "").strip().lower(),
                "entrypoint": str(entrypoint or "").strip().lower(),
                "tier": str(tier or "").strip().lower(),
                "workspace_id": effective_workspace_id,
                "apikey_id": effective_apikey_id,
                "model": str(model or "").strip(),
                "billing_cycle": explicit_billing_cycle,
            },
            "system": {
                "status": "ok",
                "input_tokens": system_input,
                "output_tokens": system_output,
                "total_tokens": system_total,
                "total_cost_usd": _round(system_cost, 8),
                "measured_input_tokens": system_measured_input,
                "measured_output_tokens": system_measured_output,
                "measured_total_tokens": system_measured_total,
                "measured_total_cost_usd": _round(system_measured_cost, 8),
                "estimated_input_tokens": system_estimated_input,
                "estimated_output_tokens": system_estimated_output,
                "estimated_total_tokens": system_estimated_total,
                "estimated_total_cost_usd": _round(system_estimated_cost, 8),
                "result_events": len(context.result_events),
                "turns": len(context.turns),
                "models": {key: value for key, value in system_models.most_common()},
                "usage_sources": {key: value for key, value in system_sources.most_common()},
            },
            "bailian": bailian_payload,
            "bailian_billing": bailian_billing_payload,
            "system_global_bailian": system_global_payload,
            "reconciliation": {
                "status": "ok" if telemetry_status == "ok" else telemetry_status,
                "token_delta": token_delta,
                "input_token_delta": input_delta,
                "output_token_delta": output_delta,
                "cost_delta_usd": cost_delta,
                "token_delta_ratio": self._delta_ratio(
                    system_total,
                    _safe_int(bailian_payload.get("total_tokens")),
                ),
                "input_token_delta_ratio": self._delta_ratio(
                    system_input,
                    _safe_int(bailian_payload.get("input_tokens")),
                ),
                "output_token_delta_ratio": self._delta_ratio(
                    system_output,
                    _safe_int(bailian_payload.get("output_tokens")),
                ),
                "cost_delta_ratio": (
                    _round(
                        (
                            system_cost - _safe_float(bailian_payload.get("estimated_total_cost_usd"))
                        )
                        / _safe_float(bailian_payload.get("estimated_total_cost_usd")),
                        6,
                    )
                    if _safe_float(bailian_payload.get("estimated_total_cost_usd")) > 0
                    else None
                ),
                "billing_cycle": explicit_billing_cycle,
                "billing_scope_system_cost_usd": (
                    _round(float(billing_scope_system_cost), 8)
                    if billing_scope_system_cost is not None
                    else None
                ),
                "billing_cost_delta_usd": billing_cost_delta,
                "billing_cost_delta_ratio": billing_cost_delta_ratio,
            },
            "warnings": warnings,
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

    async def get_feedback(self, days: int = 30, limit: int = 20) -> dict[str, Any]:
        storage_status, records = await self._load_feedback_records(days)
        records.sort(key=lambda item: item.get("created_at") or "", reverse=True)

        rating_counter = Counter(item["rating"] for item in records)
        reason_counter = Counter(
            tag
            for item in records
            for tag in item.get("reason_tags") or []
        )
        answer_mode_counter = Counter(
            str(item.get("answer_mode") or "").strip().upper() or "UNKNOWN"
            for item in records
        )
        session_ids = {
            str(item.get("session_id") or "").strip()
            for item in records
            if str(item.get("session_id") or "").strip()
        }
        message_ids = {
            str(item.get("message_id") or "").strip()
            for item in records
            if str(item.get("message_id") or "").strip()
        }
        user_ids = {
            str(item.get("user_id") or "").strip()
            for item in records
            if str(item.get("user_id") or "").strip()
        }

        return {
            "window_days": days,
            "storage_status": storage_status,
            "summary": {
                "total_feedback": len(records),
                "thumbs_up": rating_counter.get(1, 0),
                "thumbs_down": rating_counter.get(-1, 0),
                "neutral": rating_counter.get(0, 0),
                "commented": sum(1 for item in records if item.get("comment")),
                "unique_users": len(user_ids),
                "unique_sessions": len(session_ids),
                "unique_messages": len(message_ids),
            },
            "rating_breakdown": [
                {"rating": 1, "label": "thumbs_up", "count": rating_counter.get(1, 0)},
                {"rating": -1, "label": "thumbs_down", "count": rating_counter.get(-1, 0)},
                {"rating": 0, "label": "neutral", "count": rating_counter.get(0, 0)},
            ],
            "top_reason_tags": [
                {"tag": tag, "count": count}
                for tag, count in reason_counter.most_common(10)
            ],
            "answer_modes": [
                {"answer_mode": mode, "count": count}
                for mode, count in answer_mode_counter.most_common()
            ],
            "recent": records[: max(1, min(limit, 100))],
        }


_bi_service: BIService | None = None


def get_bi_service() -> BIService:
    global _bi_service
    if _bi_service is None:
        _bi_service = BIService()
    return _bi_service
