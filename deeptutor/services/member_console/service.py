from __future__ import annotations

import base64
from contextlib import contextmanager
import csv
import hashlib
import hmac
import io
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

from deeptutor.contracts.bot_runtime_defaults import CONSTRUCTION_EXAM_BOT_DEFAULTS
from deeptutor.services.assessment import (
    AssessmentBlueprintService,
    AssessmentBlueprintUnavailable,
    QuestionCandidate,
    StaticAssessmentQuestionProvider,
    SupabaseAssessmentQuestionProvider,
)
from deeptutor.services.assessment.teaching_policy import build_teaching_policy_seed
from deeptutor.services.learner_state.progress_feedback import (
    build_progress_feedback,
    build_progress_feedback_from_learner_snapshot,
)
from deeptutor.services.learner_state.study_plan import (
    build_study_plan,
    build_study_plan_from_learner_snapshot,
)
from deeptutor.services.member_console.external_auth import (
    create_external_auth_user,
    ensure_external_auth_user_for_phone,
    get_external_auth_user,
    load_external_auth_users,
    verify_external_auth_user,
)
from deeptutor.services.path_service import get_path_service
from deeptutor.services.runtime_env import env_flag, is_production_environment
from deeptutor.services.session import build_user_owner_key, get_sqlite_session_store
from deeptutor.services.wallet.identity import is_uuid_like

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


def _date_key_from_iso(value: str | None) -> str:
    return _parse_time(value).strftime("%Y-%m-%d")


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
    _AssessmentTemplate(
        id="q_material_1",
        chapter="建筑材料",
        question="水泥进场复验时，最应重点核查哪组指标？",
        options={
            "A": "包装颜色、运输距离、堆放高度",
            "B": "强度、安定性、凝结时间",
            "C": "厂家宣传资料、采购折扣",
            "D": "砂浆试块编号、抹灰厚度",
        },
        answer="B",
    ),
    _AssessmentTemplate(
        id="q_survey_1",
        chapter="施工测量",
        question="建筑物定位放线完成后，下一步最关键的控制工作是？",
        options={
            "A": "直接组织装饰施工",
            "B": "复核轴线、标高和控制点",
            "C": "优先采购成品家具",
            "D": "只记录天气情况",
        },
        answer="B",
    ),
    _AssessmentTemplate(
        id="q_formwork_1",
        chapter="模板脚手架",
        question="模板支架搭设完成后，浇筑混凝土前必须重点完成哪项工作？",
        options={
            "A": "验收支架承载、构造和稳定性",
            "B": "提前拆除剪刀撑方便通行",
            "C": "只检查混凝土颜色",
            "D": "把验收留到拆模后再做",
        },
        answer="A",
    ),
    _AssessmentTemplate(
        id="q_decoration_1",
        chapter="装饰装修",
        question="抹灰工程大面积施工前，最能降低返工风险的做法是？",
        options={
            "A": "跳过基层处理直接施工",
            "B": "先做样板并验收基层质量",
            "C": "只增加面层涂料遍数",
            "D": "等竣工验收时统一修补",
        },
        answer="B",
    ),
    _AssessmentTemplate(
        id="q_mep_1",
        chapter="机电安装",
        question="管线综合排布中，最应优先协调的是？",
        options={
            "A": "各专业管线标高、交叉和检修空间",
            "B": "办公室座椅颜色",
            "C": "材料采购付款方式",
            "D": "竣工宣传照片角度",
        },
        answer="A",
    ),
    _AssessmentTemplate(
        id="q_safety_1",
        chapter="安全管理",
        question="高处作业安全管理的底线要求是？",
        options={
            "A": "只要工人经验丰富即可不设防护",
            "B": "先施工，发现危险再补措施",
            "C": "落实临边洞口防护和安全带等措施",
            "D": "用口头提醒代替安全交底",
        },
        answer="C",
    ),
    _AssessmentTemplate(
        id="q_quality_1",
        chapter="质量验收",
        question="隐蔽工程在被后续工序覆盖前，应完成哪项程序？",
        options={
            "A": "隐蔽验收并形成记录",
            "B": "直接覆盖以节省工期",
            "C": "只由班组口头确认",
            "D": "竣工后再补拍照片",
        },
        answer="A",
    ),
    _AssessmentTemplate(
        id="q_claim_1",
        chapter="合同索赔",
        question="工期索赔是否成立，除责任归属外还必须判断什么？",
        options={
            "A": "事件是否影响关键线路或总工期",
            "B": "施工单位是否更换了项目经理",
            "C": "材料品牌是否更高端",
            "D": "会议纪要页数是否足够",
        },
        answer="A",
    ),
    _AssessmentTemplate(
        id="q_green_1",
        chapter="绿色施工",
        question="绿色施工中控制扬尘最直接有效的现场措施是？",
        options={
            "A": "裸土覆盖、道路硬化和洒水降尘",
            "B": "只在围挡外张贴标语",
            "C": "夜间集中清运不做覆盖",
            "D": "减少质量检查频次",
        },
        answer="A",
    ),
    _AssessmentTemplate(
        id="q_structure_2",
        chapter="主体结构",
        question="钢筋隐蔽验收时，最应核对的是？",
        options={
            "A": "钢筋品种、规格、数量、位置和连接锚固",
            "B": "模板外侧广告画面",
            "C": "混凝土运输车辆颜色",
            "D": "施工日志字体大小",
        },
        answer="A",
    ),
    _AssessmentTemplate(
        id="q_foundation_3",
        chapter="地基基础",
        question="基坑开挖过程中发现实际土质与勘察报告明显不符时，应优先采取哪项措施？",
        options={
            "A": "继续按原方案施工避免停工",
            "B": "立即反馈并组织复核、必要时调整方案",
            "C": "只增加现场照明",
            "D": "等基础施工完成后再记录",
        },
        answer="B",
    ),
    _AssessmentTemplate(
        id="q_waterproof_2",
        chapter="防水工程",
        question="地下防水工程质量控制中，施工缝和后浇带最需要关注的是？",
        options={
            "A": "节点构造和止水措施是否可靠",
            "B": "表面颜色是否一致",
            "C": "运输路线是否最短",
            "D": "材料包装是否美观",
        },
        answer="A",
    ),
    _AssessmentTemplate(
        id="q_schedule_1",
        chapter="施工管理",
        question="网络计划中，判断某项工作延误是否影响总工期，关键看什么？",
        options={
            "A": "该工作的总时差和关键线路关系",
            "B": "该工作名称是否较长",
            "C": "施工队人数是否为偶数",
            "D": "计划表颜色是否醒目",
        },
        answer="A",
    ),
    _AssessmentTemplate(
        id="q_material_2",
        chapter="建筑材料",
        question="混凝土试件强度评定的基本目的是什么？",
        options={
            "A": "判断混凝土是否达到设计和验收要求",
            "B": "统计运输车辆数量",
            "C": "确认模板周转次数",
            "D": "决定装饰风格",
        },
        answer="A",
    ),
    _AssessmentTemplate(
        id="q_safety_2",
        chapter="安全管理",
        question="专项施工方案需要专家论证时，项目管理上最正确的做法是？",
        options={
            "A": "先按经验施工，资料以后补齐",
            "B": "完成编审和专家论证后按批准方案实施",
            "C": "只让班组长口头同意",
            "D": "把方案拆成多个小文件规避论证",
        },
        answer="B",
    ),
]


def _assessment_bank_candidates() -> list[QuestionCandidate]:
    return [
        QuestionCandidate(
            source_question_id=item.id,
            question_stem=item.question,
            question_type="single_choice",
            chapter=item.chapter,
            options=tuple((key, value) for key, value in item.options.items()),
            answer=item.answer,
            source_type="DEV_FALLBACK",
        )
        for item in _ASSESSMENT_BANK
    ]


def _provenance_summary(questions: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [item for item in questions if item.get("scored", True)]
    with_question_id = sum(1 for item in scored if dict(item.get("provenance") or {}).get("question_id"))
    with_source_chunk_id = sum(1 for item in scored if dict(item.get("provenance") or {}).get("source_chunk_id"))
    source_tables = sorted({str(dict(item.get("provenance") or {}).get("source_table") or "") for item in questions})
    return {
        "scored_count": len(scored),
        "with_question_id": with_question_id,
        "with_source_chunk_id": with_source_chunk_id,
        "source_tables": [item for item in source_tables if item],
    }


def _section_empty_counts(session: dict[str, Any], answers: dict[str, str]) -> dict[str, int]:
    questions_by_id = {item.get("question_id"): item for item in list(session.get("questions") or [])}
    empty: dict[str, int] = {}
    for section in list(session.get("sections") or []):
        section_id = str(section.get("section_id") or "")
        count = 0
        for question_id in list(section.get("question_ids") or []):
            question = questions_by_id.get(question_id)
            if question and not str(answers.get(question_id, "")).strip():
                count += 1
        if section_id:
            empty[section_id] = count
    return empty


def _profile_traits_from_seed(seed: dict[str, Any]) -> list[str]:
    traits = ["按测评结果动态调整"]
    if seed.get("pace") in {"pace_recovery", "slow_down_checkpoints"}:
        traits.append("需要节奏支持")
    if seed.get("scaffold_level") in {"high", "stepwise"}:
        traits.append("适合分步提示")
    if seed.get("review_rhythm"):
        traits.append("适合固定复盘节奏")
    return traits


def _study_tip_from_seed(seed: dict[str, Any]) -> str:
    action = str(seed.get("recommended_action") or "")
    if action == "worked_example":
        return "建议先看一道同类例题，再做薄弱章节微练。"
    if action == "minimal_scaffold":
        return "建议把题目拆成步骤，每一步确认后再推进。"
    if action == "pace_recovery":
        return "建议先降低节奏，用短复盘恢复稳定作答。"
    return "建议先补最弱章节，再做一次短组针对训练。"


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

    def _get_wallet_service(self):
        from deeptutor.services.wallet.service import get_wallet_service

        return get_wallet_service()

    def _build_assessment_blueprint_service(self) -> AssessmentBlueprintService:
        allow_dev_fallback = (not is_production_environment()) or env_flag(
            "ASSESSMENT_ALLOW_DEV_FALLBACK",
            default=False,
        )
        fallback_provider = StaticAssessmentQuestionProvider(_assessment_bank_candidates())
        use_supabase = is_production_environment() or env_flag(
            "ASSESSMENT_USE_SUPABASE",
            default=False,
        )
        return AssessmentBlueprintService(
            provider=SupabaseAssessmentQuestionProvider() if use_supabase else fallback_provider,
            fallback_provider=fallback_provider,
            allow_dev_fallback=allow_dev_fallback,
        )

    def _write_assessment_learning_signals(
        self,
        user_id: str,
        quiz_id: str,
        result: dict[str, Any],
    ) -> None:
        seed = dict(result.get("teaching_policy_seed") or {})
        payload = {
            "quiz_id": quiz_id,
            "blueprint_version": result.get("blueprint_version"),
            "knowledge_score": result.get("knowledge_score"),
            "measurement_confidence": result.get("measurement_confidence"),
            "teaching_policy_seed": seed,
            "assessment_observability": dict(result.get("assessment_observability") or {}),
        }
        bot_id = CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0]
        try:
            self._get_learner_state_service().append_memory_event(
                user_id,
                source_feature="assessment",
                source_id=quiz_id,
                source_bot_id=bot_id,
                memory_kind="assessment",
                payload_json=payload,
                dedupe_key=f"assessment:{user_id}:{quiz_id}",
            )
        except Exception:
            logger.warning("Failed to write assessment learner-state event: user_id=%s quiz_id=%s", user_id, quiz_id, exc_info=True)
        try:
            self._get_overlay_service().patch_overlay(
                bot_id,
                user_id,
                {
                    "operations": [
                        {
                            "op": "merge",
                            "field": "teaching_policy_override",
                            "value": seed,
                        }
                    ]
                },
                source_feature="assessment",
                source_id=quiz_id,
            )
        except Exception:
            logger.warning("Failed to write assessment teaching-policy overlay: user_id=%s quiz_id=%s", user_id, quiz_id, exc_info=True)

    @staticmethod
    def _default_packages() -> list[dict[str, Any]]:
        return [
            {
                "id": "trial",
                "label": "轻量体验",
                "points": 100,
                "price": "9",
                "badge": "尝鲜",
                "per": "约 10 次标准问答",
                "desc": "适合先体验答疑、解析和日常提问",
            },
            {
                "id": "advance",
                "label": "进阶主力",
                "points": 1200,
                "price": "99",
                "badge": "推荐",
                "per": "约 120 次标准问答",
                "desc": "适合大多数备考阶段，高频问答和复盘更从容",
            },
            {
                "id": "sprint",
                "label": "冲刺强化",
                "points": 2600,
                "price": "199",
                "badge": "冲刺",
                "per": "约 260 次标准问答",
                "desc": "适合考前冲刺、密集刷题和深度推理",
            },
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
            "last_assessment": {},
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

    @staticmethod
    def _session_time_to_iso(value: Any) -> str:
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return str(value or "")
        return datetime.fromtimestamp(timestamp, _TZ).isoformat()

    @staticmethod
    def _preview_chat_content(value: Any, *, limit: int = 3000) -> str:
        content = str(value or "").strip()
        if len(content) <= limit:
            return content
        return f"{content[:limit]}..."

    def _member_session_identity_values(self, member: dict[str, Any], requested_user_id: str) -> list[str]:
        identities: list[str] = []

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in identities:
                identities.append(text)

        add(requested_user_id)
        for field in (
            "user_id",
            "canonical_user_id",
            "external_auth_user_id",
            "auth_username",
            "wx_openid",
            "wx_unionid",
            "phone",
        ):
            add(member.get(field))
        for value in member.get("alias_user_ids") or []:
            add(value)
        return identities

    @staticmethod
    def _conversation_group_key(row: dict[str, Any]) -> str:
        session_id = str(row.get("session_id") or row.get("id") or "").strip()
        preferences = row.get("preferences")
        if isinstance(preferences, dict):
            conversation_id = str(preferences.get("conversation_id") or "").strip()
            if conversation_id:
                return conversation_id
        if ":chat:" in session_id:
            return session_id.rsplit(":chat:", 1)[-1]
        return session_id

    @staticmethod
    def _conversation_row_score(row: dict[str, Any]) -> tuple[int, float, int]:
        session_id = str(row.get("session_id") or row.get("id") or "").strip()
        try:
            updated_at = float(row.get("updated_at") or 0)
        except (TypeError, ValueError):
            updated_at = 0.0
        return (
            int(row.get("message_count") or 0),
            updated_at,
            0 if session_id.startswith("tutorbot:") else 1,
        )

    def _load_recent_conversations_for_member(
        self,
        member: dict[str, Any],
        requested_user_id: str,
        *,
        session_limit: int = 5,
        message_limit: int = 12,
    ) -> list[dict[str, Any]]:
        identity_values = self._member_session_identity_values(member, requested_user_id)
        if not identity_values:
            return []

        rows_by_conversation_key: dict[str, dict[str, Any]] = {}
        for identity in identity_values:
            owner_key = build_user_owner_key(identity)
            if not owner_key:
                continue
            try:
                rows = self._store._list_sessions_by_owner_sync(  # noqa: SLF001 - member 360 is sync.
                    owner_key,
                    archived=False,
                    limit=session_limit,
                )
            except Exception:
                logger.warning(
                    "Failed to load member conversations: user_id=%s owner_key=%s",
                    requested_user_id,
                    owner_key,
                    exc_info=True,
                )
                continue
            for row in rows:
                session_id = str(row.get("session_id") or row.get("id") or "").strip()
                if not session_id:
                    continue
                conversation_key = self._conversation_group_key(row)
                current = rows_by_conversation_key.get(conversation_key)
                if current is None or self._conversation_row_score(row) > self._conversation_row_score(current):
                    rows_by_conversation_key[conversation_key] = row

        sorted_rows = sorted(
            rows_by_conversation_key.values(),
            key=lambda item: float(item.get("updated_at") or 0),
            reverse=True,
        )[:session_limit]
        conversations: list[dict[str, Any]] = []
        for row in sorted_rows:
            session_id = str(row.get("session_id") or row.get("id") or "").strip()
            if not session_id:
                continue
            try:
                raw_messages = self._store._get_messages_sync(session_id)  # noqa: SLF001 - member 360 is sync.
            except Exception:
                logger.warning(
                    "Failed to load member conversation messages: user_id=%s session_id=%s",
                    requested_user_id,
                    session_id,
                    exc_info=True,
                )
                raw_messages = []

            visible_messages = [
                message
                for message in raw_messages
                if str(message.get("role") or "").strip() in {"user", "assistant"}
                and str(message.get("content") or "").strip()
            ][-message_limit:]
            messages = [
                {
                    "id": str(message.get("id") or ""),
                    "role": str(message.get("role") or ""),
                    "content": self._preview_chat_content(message.get("content")),
                    "created_at": self._session_time_to_iso(message.get("created_at")),
                    "capability": str(message.get("capability") or ""),
                }
                for message in visible_messages
            ]
            if not messages:
                continue
            conversations.append(
                {
                    "session_id": session_id,
                    "title": str(row.get("title") or "未命名会话"),
                    "created_at": self._session_time_to_iso(row.get("created_at")),
                    "updated_at": self._session_time_to_iso(row.get("updated_at")),
                    "capability": str(row.get("capability") or "chat"),
                    "message_count": int(row.get("message_count") or len(raw_messages)),
                    "last_message": self._preview_chat_content(row.get("last_message")),
                    "messages": messages,
                }
            )
        return conversations

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
        data["packages"] = self._default_packages()
        data.setdefault("audit_log", [])
        data.setdefault("assessment_sessions", {})
        data.setdefault("phone_codes", {})
        if self._apply_legacy_chat_learning_migration(data):
            self._save_unlocked(data)
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
    def _is_cn_mainland_mobile(value: Any) -> bool:
        phone = _normalize_phone_input(str(value or ""))
        return bool(re.fullmatch(r"1[3-9]\d{9}", phone)) and phone not in {
            "13800000000",
            "13900000000",
            "18888888888",
            "19999999999",
        } and not re.fullmatch(r"1380000000\d", phone)

    @staticmethod
    def _looks_like_test_member(member: dict[str, Any]) -> bool:
        haystack = " ".join(
            str(member.get(key) or "").lower()
            for key in (
                "user_id",
                "display_name",
                "auth_username",
                "external_auth_provider",
                "wx_openid",
                "wx_unionid",
            )
        )
        test_markers = (
            "test",
            "casefix",
            "codex",
            "probe",
            "audit",
            "prelaunch",
            "prelaunchsmoke",
            "preflight",
            "smoke",
            "debug",
            "mock",
            "dummy",
            "fake",
            "测试",
        )
        demo_member_ids = {
            "student_demo",
            "student_risk",
            "student_svip",
            "student_lapsed",
        }
        user_id = str(member.get("user_id") or "").strip().lower()
        return user_id in demo_member_ids or any(marker in haystack for marker in test_markers)

    def _registered_phone_for_bi(self, member: dict[str, Any]) -> str:
        phone = _normalize_phone_input(str(member.get("phone") or ""))
        if self._is_cn_mainland_mobile(phone):
            return phone
        external_user_id = str(member.get("external_auth_user_id") or "").strip()
        if not external_user_id:
            return ""
        try:
            for user_data in load_external_auth_users().values():
                if str(user_data.get("id") or "").strip() != external_user_id:
                    continue
                external_phone = _normalize_phone_input(str(user_data.get("phone") or ""))
                if self._is_cn_mainland_mobile(external_phone):
                    return external_phone
        except Exception:
            logger.warning("Failed to load external auth users for BI member projection", exc_info=True)
        return ""

    def _canonical_member_keys_for_bi(self, member: dict[str, Any]) -> list[str]:
        keys: list[str] = []
        external_user_id = str(member.get("external_auth_user_id") or "").strip()
        if is_uuid_like(external_user_id):
            keys.append(f"external:{external_user_id}")
        phone = self._registered_phone_for_bi(member)
        if phone:
            keys.append(f"phone:{phone}")
        for field in ("wx_unionid", "wx_openid"):
            value = str(member.get(field) or "").strip()
            if value:
                keys.append(f"{field}:{value}")
        return keys

    def _is_registered_member_for_bi(self, member: dict[str, Any]) -> bool:
        return bool(self._registered_phone_for_bi(member)) and not self._looks_like_test_member(member)

    def _is_better_canonical_member_base(self, source: dict[str, Any], target: dict[str, Any]) -> bool:
        def score(member: dict[str, Any]) -> tuple[int, int, float, int]:
            user_id = str(member.get("user_id") or "").strip()
            external_user_id = str(member.get("external_auth_user_id") or "").strip()
            canonical_identity = 1 if is_uuid_like(user_id) or is_uuid_like(external_user_id) else 0
            signal_score = self._member_signal_score(member)
            last_active = _parse_time(member.get("last_active_at")).timestamp()
            points = int(member.get("points_balance") or 0)
            return (canonical_identity, signal_score, last_active, points)

        return score(source) > score(target)

    def _merge_canonical_member_for_bi(self, target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        alias_user_ids = {
            str(item).strip()
            for item in list(target.get("alias_user_ids") or []) + list(source.get("alias_user_ids") or [])
            if str(item).strip()
        }
        for item in (target.get("user_id"), source.get("user_id")):
            if str(item or "").strip():
                alias_user_ids.add(str(item).strip())

        if self._is_better_canonical_member_base(source, target):
            previous = deepcopy(target)
            target.clear()
            target.update(deepcopy(source))
            self._merge_member_identity_view(target, previous)
        else:
            self._merge_member_identity_view(target, source)

        target["alias_user_ids"] = sorted(alias_user_ids)
        phone = self._registered_phone_for_bi(target) or self._registered_phone_for_bi(source)
        if phone:
            target["phone"] = phone
        external_user_id = str(target.get("external_auth_user_id") or source.get("external_auth_user_id") or "").strip()
        target["canonical_user_id"] = external_user_id if is_uuid_like(external_user_id) else str(target.get("user_id") or "").strip()
        return target

    def _members_for_bi(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        key_to_index: dict[str, int] = {}

        for raw_member in data.get("members") or []:
            if not isinstance(raw_member, dict) or not self._is_registered_member_for_bi(raw_member):
                continue
            member = deepcopy(raw_member)
            keys = self._canonical_member_keys_for_bi(member)
            if not keys:
                continue
            matched_indexes = sorted({key_to_index[key] for key in keys if key in key_to_index})
            if not matched_indexes:
                index = len(members)
                member["alias_user_ids"] = [str(member.get("user_id") or "").strip()]
                member["canonical_user_id"] = (
                    str(member.get("external_auth_user_id") or "").strip()
                    if is_uuid_like(str(member.get("external_auth_user_id") or "").strip())
                    else str(member.get("user_id") or "").strip()
                )
                phone = self._registered_phone_for_bi(member)
                if phone:
                    member["phone"] = phone
                members.append(member)
            else:
                index = matched_indexes[0]
                members[index] = self._merge_canonical_member_for_bi(members[index], member)
                for duplicate_index in reversed(matched_indexes[1:]):
                    members[index] = self._merge_canonical_member_for_bi(members[index], members[duplicate_index])
                    del members[duplicate_index]
                    key_to_index = {
                        key: existing_index - 1 if existing_index > duplicate_index else existing_index
                        for key, existing_index in key_to_index.items()
                        if existing_index != duplicate_index
                    }
            for key in self._canonical_member_keys_for_bi(members[index]):
                key_to_index[key] = index

        return members

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

    def _sync_phone_backed_external_identity(self, member: dict[str, Any]) -> None:
        raw_phone = str(member.get("phone") or "").strip()
        phone = _normalize_phone_input(raw_phone)
        current_external_user_id = str(member.get("external_auth_user_id") or "").strip()
        synthetic_default_phone = _slugify_phone(str(member.get("user_id") or ""))
        if (
            not phone
            or phone == synthetic_default_phone
            or is_uuid_like(current_external_user_id)
        ):
            return
        try:
            external_user = ensure_external_auth_user_for_phone(phone)
        except ValueError as exc:
            logger.warning(
                "phone-backed external identity skipped for user_id=%s phone=%s: %s",
                member.get("user_id"),
                phone,
                exc,
            )
            return
        except Exception as exc:
            logger.warning(
                "phone-backed external identity bootstrap skipped for user_id=%s phone=%s: %s",
                member.get("user_id"),
                phone,
                exc,
            )
            if is_production_environment():
                raise RuntimeError("Phone-backed identity bootstrap failed") from exc
            return
        external_user_id = str(external_user.get("id") or "").strip()
        if not is_uuid_like(external_user_id):
            return
        member["auth_username"] = str(external_user.get("username") or member.get("auth_username") or "").strip()
        member["external_auth_provider"] = "fastapi20251222_simple_auth"
        member["external_auth_user_id"] = external_user_id

    def _auth_identity_for_member(self, user_id: str) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            member = self._ensure_member(data, user_id)
            self._sync_phone_backed_external_identity(member)
            return deepcopy(member)

        member = self._mutate(_apply)
        canonical_uid = ""
        external_auth_user_id = str(member.get("external_auth_user_id") or "").strip()
        if is_uuid_like(external_auth_user_id):
            canonical_uid = external_auth_user_id
        else:
            from deeptutor.services.wallet.identity import get_wallet_identity_store

            store = get_wallet_identity_store()
            if getattr(store, "is_configured", False):
                candidates: list[str] = []

                def _append_candidate(alias_type: str, alias_value: Any) -> None:
                    normalized = str(alias_value or "").strip()
                    if not normalized:
                        return
                    try:
                        row = store.resolve_alias(alias_type=alias_type, alias_value=normalized)
                    except Exception as exc:
                        logger.warning(
                            "alias lookup failed for user_id=%s alias_type=%s alias_value=%s: %s",
                            member.get("user_id"),
                            alias_type,
                            normalized,
                            exc,
                        )
                        return
                    if not isinstance(row, dict):
                        return
                    alias_user_id = str(row.get("user_id") or "").strip()
                    if alias_user_id and alias_user_id not in candidates:
                        candidates.append(alias_user_id)

                _append_candidate("legacy_user_id", member.get("user_id"))
                _append_candidate("auth_username", member.get("auth_username"))
                _append_candidate("phone", member.get("phone"))
                _append_candidate("wx_openid", member.get("wx_openid"))
                _append_candidate("wx_unionid", member.get("wx_unionid"))
                if len(candidates) == 1:
                    canonical_uid = candidates[0]
        if (
            is_uuid_like(canonical_uid)
            and canonical_uid != str(member.get("user_id") or "").strip()
            and not is_uuid_like(external_auth_user_id)
        ):
            def _persist_alias_backed_canonical(data: dict[str, Any]) -> None:
                target = self._ensure_member(data, str(member.get("user_id") or "").strip())
                target["external_auth_user_id"] = canonical_uid
                if not str(target.get("external_auth_provider") or "").strip():
                    target["external_auth_provider"] = "wallet_alias"

            self._mutate(_persist_alias_backed_canonical)
            member["external_auth_user_id"] = canonical_uid
            member["external_auth_provider"] = str(member.get("external_auth_provider") or "wallet_alias").strip()
        if not canonical_uid:
            canonical_uid = str(member.get("user_id") or "").strip()
        if is_uuid_like(canonical_uid):
            wallet_service = self._get_wallet_service()
            if getattr(wallet_service, "is_configured", False):
                try:
                    snapshot = wallet_service.ensure_wallet_seeded(
                        user_id=canonical_uid,
                        opening_points=int(member.get("points_balance") or 0),
                        plan_id=str(member.get("tier") or "").strip(),
                        reference_type="signup_bonus",
                        reference_id=str(member.get("user_id") or canonical_uid).strip(),
                        idempotency_key=f"signup_bonus:{canonical_uid}:member_console_bootstrap",
                        metadata={
                            "source": "member_console_auth_bootstrap",
                            "legacy_user_id": str(member.get("user_id") or "").strip(),
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "wallet bootstrap failed for member user_id=%s canonical_uid=%s: %s",
                        member.get("user_id"),
                        canonical_uid,
                        exc,
                    )
                    if is_production_environment():
                        raise RuntimeError("Wallet bootstrap failed") from exc
                else:
                    if snapshot is not None:
                        balance_points = int(round(int(snapshot.balance_micros) / 1_000_000))
                        if balance_points != int(member.get("points_balance") or 0):
                            def _sync_shadow(data: dict[str, Any]) -> None:
                                target = self._ensure_member(data, user_id)
                                target["points_balance"] = balance_points

                            self._mutate(_sync_shadow)
                            member["points_balance"] = balance_points
        return {
            "user_id": str(member.get("user_id") or "").strip(),
            "canonical_uid": canonical_uid,
            "openid": str(member.get("wx_openid") or "").strip(),
            "unionid": str(member.get("wx_unionid") or "").strip(),
        }

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

    def _apply_legacy_chat_learning_migration(self, data: dict[str, Any]) -> bool:
        migrations = data.setdefault("migrations", {})
        counts_removed = bool(migrations.get("chat_learning_counts_removed_v1"))
        audit_removed = bool(migrations.get("chat_learning_audit_removed_v2"))
        if counts_removed and audit_removed:
            return False

        by_user: dict[str, dict[str, Any]] = {}
        kept_audit: list[dict[str, Any]] = []
        removed_audit_count = 0
        for entry in list(data.get("audit_log") or []):
            if str(entry.get("action") or "").strip() != "learning_activity":
                kept_audit.append(entry)
                continue
            if str(entry.get("operator") or "").strip().lower() != "chat":
                kept_audit.append(entry)
                continue
            removed_audit_count += 1
            if counts_removed:
                continue
            user_id = str(entry.get("target_user") or "").strip()
            if not user_id:
                continue
            after = dict(entry.get("after") or {})
            count = max(0, int(after.get("count") or 0))
            if count <= 0:
                continue
            date_key = _date_key_from_iso(str(entry.get("created_at") or ""))
            chapter = str(after.get("chapter") or "").strip()
            bucket = by_user.setdefault(user_id, {"daily": {}, "chapters": {}})
            bucket["daily"][date_key] = int(bucket["daily"].get(date_key) or 0) + count
            if chapter:
                bucket["chapters"][chapter] = int(bucket["chapters"].get(chapter) or 0) + count

        changed = False
        if not audit_removed and removed_audit_count:
            data["audit_log"] = kept_audit
            migrations["chat_learning_audit_removed_v2"] = True
            changed = True
        elif not audit_removed:
            migrations["chat_learning_audit_removed_v2"] = True
            changed = True

        if counts_removed:
            return changed

        if not by_user:
            migrations["chat_learning_counts_removed_v1"] = True
            return True

        for member in list(data.get("members") or []):
            user_id = str(member.get("user_id") or "").strip()
            adjustments = by_user.get(user_id)
            if not adjustments:
                continue
            learning = self._ensure_learning_profile(member)
            for date_key, count in adjustments["daily"].items():
                current = int(learning["daily_counts"].get(date_key) or 0)
                next_value = max(0, current - int(count or 0))
                if next_value > 0:
                    learning["daily_counts"][date_key] = next_value
                else:
                    learning["daily_counts"].pop(date_key, None)
            for chapter, count in adjustments["chapters"].items():
                stats = learning["chapter_stats"].get(chapter)
                if not isinstance(stats, dict):
                    continue
                stats["done"] = max(0, int(stats.get("done") or 0) - int(count or 0))
                stats["correct"] = min(int(stats.get("correct") or 0), int(stats.get("done") or 0))
                if int(stats.get("done") or 0) <= 0:
                    stats["last_activity_at"] = ""
        migrations["chat_learning_counts_removed_v1"] = True
        return True

    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    @staticmethod
    def _b64url_decode(raw: str) -> bytes:
        padding = "=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode(raw + padding)

    def _auth_secret(self) -> str:
        if is_production_environment():
            secret = str(
                os.getenv("DEEPTUTOR_AUTH_SECRET")
                or os.getenv("MEMBER_CONSOLE_AUTH_SECRET")
                or ""
            ).strip()
            if not secret:
                raise RuntimeError("DEEPTUTOR_AUTH_SECRET must be configured in production")
            return secret

        secret = str(
            os.getenv("DEEPTUTOR_AUTH_SECRET")
            or os.getenv("MEMBER_CONSOLE_AUTH_SECRET")
            or os.getenv("WECHAT_MP_TOKEN_SECRET")
            or os.getenv("WECHAT_MP_APP_SECRET")
            or os.getenv("WECHAT_MP_APPSECRET")
            or "deeptutor-dev-member-secret"
        ).strip()
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

    def _access_token_ttl_seconds(self) -> int:
        raw = str(
            os.getenv("DEEPTUTOR_AUTH_TOKEN_TTL_SECONDS")
            or os.getenv("MEMBER_CONSOLE_ACCESS_TOKEN_TTL_SECONDS")
            or ""
        ).strip()
        try:
            ttl_seconds = int(raw) if raw else 60 * 60 * 24 * 30
        except (TypeError, ValueError):
            ttl_seconds = 60 * 60 * 24 * 30
        return max(300, ttl_seconds)

    def _access_token_max_session_age_seconds(self) -> int:
        raw = str(
            os.getenv("DEEPTUTOR_AUTH_MAX_SESSION_AGE_SECONDS")
            or os.getenv("MEMBER_CONSOLE_MAX_SESSION_AGE_SECONDS")
            or ""
        ).strip()
        try:
            max_session_age = int(raw) if raw else 60 * 60 * 24 * 90
        except (TypeError, ValueError):
            max_session_age = 60 * 60 * 24 * 90
        return max(self._access_token_ttl_seconds(), max_session_age)

    def _issue_access_token(
        self,
        *,
        user_id: str,
        canonical_uid: str = "",
        openid: str = "",
        unionid: str = "",
        ttl_seconds: int | None = None,
        orig_iat: int | None = None,
    ) -> str:
        now = int(_now().timestamp())
        resolved_user_id = str(user_id or "").strip()
        canonical_user_id = str(canonical_uid or resolved_user_id).strip()
        resolved_ttl_seconds = self._access_token_ttl_seconds() if ttl_seconds is None else max(300, int(ttl_seconds))
        resolved_orig_iat = max(0, int(orig_iat or now))
        max_session_exp = resolved_orig_iat + self._access_token_max_session_age_seconds()
        payload = {
            "v": 1,
            "sub": canonical_user_id,
            "uid": canonical_user_id,
            "canonical_uid": canonical_user_id,
            "openid": openid,
            "unionid": unionid,
            "provider": "wechat_mp" if openid else "local",
            "iat": now,
            "orig_iat": resolved_orig_iat,
            "exp": min(now + resolved_ttl_seconds, max_session_exp),
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
        # Snapshot provider credentials before consulting other runtime flags.
        # Some import-time config loaders may hydrate os.environ lazily; the
        # production auth path must not flip from fail-closed to real-SMS mid-call.
        sms_configured = self._sms_configured()
        if env_flag("MEMBER_CONSOLE_USE_REAL_SMS", default=False):
            return sms_configured
        explicit = str(os.getenv("MEMBER_CONSOLE_USE_REAL_SMS") or "").strip().lower()
        if explicit in {"0", "false", "no", "off"}:
            return False
        return sms_configured and is_production_environment()

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
        if str(source or "").strip().lower() == "chat":
            data = self._load()
            member = self._ensure_member(data, user_id)
            learning = self._ensure_learning_profile(member)
            today = _date_key()
            return {
                "today_done": int(learning["daily_counts"].get(today) or 0),
                "chapter": str(chapter or "").strip(),
                "recorded": False,
                "reason": "chat_turn_is_not_completion_authority",
            }

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
        learning = self._ensure_learning_profile(member)
        today = _date_key()
        return {
            "today_done": int(learning["daily_counts"].get(today) or 0),
            "chapter": chapter,
            "recorded": False,
            "reason": "chat_turn_is_not_completion_authority",
        }

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
        claims = self.verify_access_token(token) or {}
        expires_at = int(claims.get("exp") or 0)
        is_admin = self.is_admin_user(user_id)
        user = self.get_profile(user_id)
        user["is_admin"] = is_admin
        payload = {
            "user_id": user_id,
            "token": token,
            "token_type": "Bearer",
            "expires_at": expires_at,
            "expires_in": max(0, expires_at - int(_now().timestamp())) if expires_at else 0,
            "is_admin": is_admin,
            "user": user,
        }
        if openid:
            payload["openid"] = openid
        if unionid:
            payload["unionid"] = unionid
        return payload

    def refresh_access_token(self, auth_header: str | None = None) -> dict[str, Any]:
        token = self._extract_access_token(auth_header)
        claims = self.verify_access_token(token)
        user_id = str((claims or {}).get("canonical_uid") or (claims or {}).get("uid") or "").strip()
        if not claims or not user_id:
            raise ValueError("Invalid or expired token")
        now = int(_now().timestamp())
        orig_iat = max(0, int((claims or {}).get("orig_iat") or (claims or {}).get("iat") or 0))
        if not orig_iat:
            raise ValueError("Invalid or expired token")
        max_session_exp = orig_iat + self._access_token_max_session_age_seconds()
        if now >= max_session_exp:
            raise ValueError("Session refresh window expired")
        auth_identity = self._auth_identity_for_member(user_id)
        refreshed_token = self._issue_access_token(
            user_id=auth_identity["user_id"] or user_id,
            canonical_uid=str(auth_identity["canonical_uid"] or claims.get("canonical_uid") or user_id).strip(),
            openid=auth_identity["openid"] or str(claims.get("openid") or "").strip(),
            unionid=auth_identity["unionid"] or str(claims.get("unionid") or "").strip(),
            orig_iat=orig_iat,
        )
        return self._build_auth_response(
            user_id=auth_identity["user_id"] or user_id,
            token=refreshed_token,
            openid=auth_identity["openid"] or str(claims.get("openid") or "").strip(),
            unionid=auth_identity["unionid"] or str(claims.get("unionid") or "").strip(),
        )

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

    def _append_audit_log(self, entry: dict[str, Any]) -> dict[str, Any]:
        payload = dict(entry or {})

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            data.setdefault("audit_log", []).insert(0, payload)
            return payload

        return self._mutate(_apply)

    def get_dashboard(self, days: int = 30) -> dict[str, Any]:
        data = self._load()
        members = self._members_for_bi(data)
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
        expire_within_days: int | None = None,
        active_within_days: int | None = None,
        has_heartbeat_job: bool | None = None,
        has_overlay_candidates: bool | None = None,
    ) -> dict[str, Any]:
        data = self._load()
        members = self._members_for_bi(data)
        search_text = str(search or "").strip().lower()
        now = _now()
        heartbeat_user_ids: set[str] | None = None
        if has_heartbeat_job is not None:
            try:
                heartbeat_user_ids = {
                    str(job.user_id)
                    for job in self._get_learner_state_service().list_all_heartbeat_jobs()
                }
            except Exception:
                heartbeat_user_ids = set()
        overlay_candidate_user_ids: set[str] | None = None
        if has_overlay_candidates is not None:
            try:
                overlay_candidate_user_ids = set()
                overlay_service = self._get_overlay_service()
                for item in members:
                    overlays = overlay_service.list_user_overlays(item["user_id"], limit=20)
                    if any(list(overlay.get("promotion_candidates") or []) for overlay in overlays):
                        overlay_candidate_user_ids.add(item["user_id"])
            except Exception:
                overlay_candidate_user_ids = set()
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
            if expire_within_days is not None:
                expire_at = _parse_time(item.get("expire_at"))
                remaining_seconds = (expire_at - now).total_seconds()
                if remaining_seconds < 0 or remaining_seconds > expire_within_days * 24 * 60 * 60:
                    continue
            if active_within_days is not None:
                last_active_at = _parse_time(item.get("last_active_at"))
                if last_active_at < now - timedelta(days=active_within_days):
                    continue
            if has_heartbeat_job is not None:
                member_has_heartbeat_job = item["user_id"] in (heartbeat_user_ids or set())
                if member_has_heartbeat_job != has_heartbeat_job:
                    continue
            if has_overlay_candidates is not None:
                member_has_overlay_candidates = item["user_id"] in (overlay_candidate_user_ids or set())
                if member_has_overlay_candidates != has_overlay_candidates:
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
                    "canonical_user_id": item.get("canonical_user_id") or item["user_id"],
                    "alias_user_ids": item.get("alias_user_ids") or [item["user_id"]],
                }
            )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
            "filters": {
                "status": status,
                "tier": tier,
                "segment": segment,
                "risk_level": risk_level,
                "auto_renew": auto_renew,
                "expire_within_days": expire_within_days,
                "active_within_days": active_within_days,
                "has_heartbeat_job": has_heartbeat_job,
                "has_overlay_candidates": has_overlay_candidates,
            },
        }

    def list_members_for_bi(self) -> list[dict[str, Any]]:
        return deepcopy(self._members_for_bi(self._load()))

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
        member["recent_conversations"] = self._load_recent_conversations_for_member(member, user_id)
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
                    "skipped_ids": list(result.get("skipped_ids") or []),
                    "skipped": list(result.get("skipped") or []),
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

    def record_ops_action_result(
        self,
        user_id: str,
        *,
        status: str,
        result: str,
        action_title: str = "",
        next_follow_up_at: str = "",
        operator: str = "admin",
    ) -> dict[str, Any]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"open", "in_progress", "done", "follow_up"}:
            raise ValueError("Unsupported ops action status")
        normalized_result = str(result or "").strip()
        if not normalized_result:
            raise ValueError("Ops action result is required")
        normalized_title = str(action_title or "").strip() or "会员运营处理"
        normalized_follow_up = str(next_follow_up_at or "").strip()

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            member = self._find_member(data, user_id)
            content_lines = [
                f"处理事项：{normalized_title}",
                f"处理状态：{normalized_status}",
                f"处理结果：{normalized_result}",
            ]
            if normalized_follow_up:
                content_lines.append(f"下次跟进：{normalized_follow_up}")
            note = {
                "id": f"note_{uuid.uuid4().hex[:10]}",
                "content": "\n".join(content_lines),
                "channel": "ops_action",
                "pinned": normalized_status in {"follow_up", "open", "in_progress"},
                "created_at": _iso(),
            }
            action_result = {
                "status": normalized_status,
                "result": normalized_result,
                "action_title": normalized_title,
                "next_follow_up_at": normalized_follow_up,
                "note_id": note["id"],
            }
            member.setdefault("notes", []).insert(0, note)
            self._append_audit(
                data,
                action="ops_action_result",
                target_user=user_id,
                reason=normalized_status,
                after=action_result,
                operator=operator,
            )
            return {**action_result, "note": note}

        return self._mutate(_apply)

    def record_conversation_view(
        self,
        user_id: str,
        session_id: str,
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            raise ValueError("Conversation session_id is required")

        data = self._load()
        member = self._find_member(data, user_id)
        conversations = self._load_recent_conversations_for_member(member, user_id, session_limit=20)
        conversation = next(
            (item for item in conversations if str(item.get("session_id") or "") == normalized_session_id),
            None,
        )
        if conversation is None:
            raise KeyError(f"Unknown conversation: {normalized_session_id}")

        audit_payload = {
            "session_id": normalized_session_id,
            "title": str(conversation.get("title") or ""),
            "message_count": int(conversation.get("message_count") or 0),
            "capability": str(conversation.get("capability") or ""),
            "view_scope": "full_conversation_messages",
        }

        def _apply(next_data: dict[str, Any]) -> dict[str, Any]:
            self._find_member(next_data, user_id)
            self._append_audit(
                next_data,
                action="conversation_view",
                target_user=user_id,
                reason="view_full_conversation",
                after=audit_payload,
                operator=operator,
            )
            return audit_payload

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

    def list_audit_log(
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
        total = len(items)
        return {
            "items": items[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    def get_audit_log(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        target_user: str | None = None,
        operator: str | None = None,
        action: str | None = None,
    ) -> dict[str, Any]:
        return self.list_audit_log(
            page=page,
            page_size=page_size,
            target_user=target_user,
            operator=operator,
            action=action,
        )

    def export_members_csv(
        self,
        *,
        status: str | None = None,
        tier: str | None = None,
        search: str | None = None,
        segment: str | None = None,
        risk_level: str | None = None,
        auto_renew: bool | None = None,
        expire_within_days: int | None = None,
        active_within_days: int | None = None,
        has_heartbeat_job: bool | None = None,
        has_overlay_candidates: bool | None = None,
    ) -> dict[str, str]:
        rows = self.list_members(
            page=1,
            page_size=max(1, len(self._load().get("members", [])) or 1),
            status=status,
            tier=tier,
            search=search,
            segment=segment,
            risk_level=risk_level,
            auto_renew=auto_renew,
            expire_within_days=expire_within_days,
            active_within_days=active_within_days,
            has_heartbeat_job=has_heartbeat_job,
            has_overlay_candidates=has_overlay_candidates,
        )["items"]
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "user_id",
                "display_name",
                "phone",
                "tier",
                "status",
                "segment",
                "risk_level",
                "auto_renew",
                "expire_at",
                "created_at",
                "last_active_at",
                "points_balance",
                "review_due",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return {
            "filename": f"members-{_date_key()}.csv",
            "content": buffer.getvalue(),
        }

    def batch_update_members(
        self,
        *,
        user_ids: list[str],
        action: str,
        operator: str = "admin",
        reason: str = "",
        days: int | None = None,
        tier: str | None = None,
        expire_at: str | None = None,
        auto_renew: bool | None = None,
    ) -> dict[str, Any]:
        succeeded: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for user_id in list(user_ids or []):
            try:
                self._find_member(self._load(), user_id)
                if action == "grant":
                    member = self.grant_subscription(
                        user_id=user_id,
                        days=max(1, int(days or 30)),
                        tier=str(tier or "vip"),
                        reason=reason,
                        operator=operator,
                    )
                elif action == "revoke":
                    member = self.revoke_subscription(
                        user_id=user_id,
                        reason=reason,
                        operator=operator,
                    )
                elif action == "update":
                    member = self.update_subscription(
                        user_id=user_id,
                        tier=tier,
                        days=days,
                        expire_at=expire_at,
                        auto_renew=auto_renew,
                        reason=reason,
                        operator=operator,
                    )
                else:
                    raise ValueError(f"Unsupported batch action: {action}")
                succeeded.append({"user_id": user_id, "member": member})
            except Exception as exc:
                failed.append({"user_id": user_id, "detail": str(exc)})
        return {
            "action": action,
            "success_count": len(succeeded),
            "failure_count": len(failed),
            "items": succeeded,
            "failed": failed,
        }

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
        daily_target = max(1, int(member.get("daily_target") or 30))
        for key, value in (member.get("chapter_mastery") or {}).items():
            chapter_name = value.get("name") or key
            stats = learning["chapter_stats"].get(chapter_name) or {}
            done = int(stats.get("done") or 0)
            mastery = round((done / daily_target) * 100) if done > 0 else 0
            if mastery > 0:
                has_signal = True
            items.append({"name": chapter_name, "mastery": mastery})
        return items if has_signal else []

    def _report_mastery_items(self, member: dict[str, Any]) -> list[dict[str, Any]]:
        mastery_items = self._chapter_mastery_items(member)
        positive_items = [item for item in mastery_items if int(item.get("mastery") or 0) > 0]
        if positive_items:
            return positive_items
        return self._build_provisional_mastery_items(member)

    def get_chapter_progress(self, user_id: str) -> list[dict[str, Any]]:
        member = self._load_member_snapshot(user_id)["member"]
        learning = self._ensure_learning_profile(member)
        daily_target = max(1, int(member.get("daily_target") or 30))
        items = []
        for index, (key, value) in enumerate(member["chapter_mastery"].items(), start=1):
            mastery = int(value.get("mastery") or 0)
            chapter_name = value.get("name") or key
            stats = learning["chapter_stats"].get(chapter_name) or {}
            done = int(stats.get("done") or 0)
            total = max(done, 1)
            items.append(
                {
                    "chapter_id": f"ch_{index}",
                    "chapter_name": chapter_name,
                    "done": done,
                    "total": total,
                    "target": daily_target,
                    "daily_target": daily_target,
                    "mastery": mastery,
                }
            )
        return items

    def get_home_dashboard(self, user_id: str) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        learning = self._ensure_learning_profile(member)
        mastery_items = self._report_mastery_items(member)
        weak_nodes = [
            {"name": item["name"], "mastery": item["mastery"]}
            for item in mastery_items
            if int(item.get("mastery") or 0) < 60
        ]
        weak_nodes.sort(key=lambda item: item["mastery"])
        review = {
            "overdue": max(0, member["review_due"] - 1),
            "due_today": 1 if member["review_due"] else 0,
        }
        snapshot = self._read_learner_snapshot(user_id, event_limit=20)
        study_plan = self._build_home_study_plan(
            member,
            weak_nodes=weak_nodes,
            review=review,
            snapshot=snapshot,
            learning=learning,
        )
        today_focus = self._build_home_today_focus(
            member,
            weak_nodes=weak_nodes,
            review=review,
            snapshot=snapshot,
            study_plan=study_plan,
        )
        return {
            "review": review,
            "mastery": {"weak_nodes": weak_nodes[:3]},
            "today": {"hint": today_focus["title"], "focus": today_focus},
            "today_focus": today_focus,
            "study_plan": study_plan,
            "progress_feedback": self._build_home_progress_feedback(
                member,
                weak_nodes=weak_nodes,
                snapshot=snapshot,
                learning=learning,
            ),
        }

    def _read_learner_snapshot(self, user_id: str, *, event_limit: int = 5) -> Any | None:
        try:
            return self._get_learner_state_service().read_snapshot(user_id, event_limit=event_limit)
        except Exception:
            logger.warning(
                "Failed to load learner snapshot for member console: user_id=%s event_limit=%s",
                user_id,
                event_limit,
                exc_info=True,
            )
            return None

    def _build_home_today_focus(
        self,
        member: dict[str, Any],
        *,
        weak_nodes: list[dict[str, Any]],
        review: dict[str, Any],
        snapshot: Any | None = None,
        study_plan: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        plan = dict(study_plan or {})
        profile = dict(getattr(snapshot, "profile", {}) or {}) if snapshot is not None else {}
        focus_topic = str(
            plan.get("focus_topic") or profile.get("focus_topic") or member.get("focus_topic") or ""
        ).strip()
        focus_query = str(profile.get("focus_query") or member.get("focus_query") or "").strip()
        priority_task = str(plan.get("priority_task") or "").strip()
        time_budget = str(plan.get("time_budget") or "").strip()
        overdue = max(0, int(review.get("overdue") or 0))
        due_today = max(0, int(review.get("due_today") or 0))
        source = "learner_state.study_plan" if snapshot is not None else "member_console.study_plan"

        if overdue > 0:
            meta = f"{overdue} 个知识点 · 今天先过一遍"
            if time_budget:
                meta = f"{meta} · {time_budget}"
            return {
                "label": "今日焦点",
                "title": "优先处理逾期复习",
                "meta": meta,
                "query": "帮我复习逾期的知识点",
                "tone": "review",
                "reason": "review_due",
                "source": source,
            }

        if focus_topic:
            weak_names = {
                str(item.get("name") or "").strip()
                for item in weak_nodes
                if str(item.get("name") or "").strip()
            }
            if snapshot is not None:
                progress = dict(getattr(snapshot, "progress", {}) or {})
                knowledge_map = dict(progress.get("knowledge_map") or {})
                weak_names.update(
                    str(item or "").strip()
                    for item in list(knowledge_map.get("weak_points") or [])
                    if str(item or "").strip()
                )
            tone = "practice" if focus_topic in weak_names else "plan"
            if not focus_query:
                focus_query = f"我想练习{focus_topic}相关的题目"
            meta = priority_task or time_budget or "按当前学习计划继续"
            return {
                "label": "今日焦点",
                "title": f"继续推进{focus_topic}专项训练",
                "meta": meta,
                "query": focus_query,
                "tone": tone,
                "reason": "learner_state_focus",
                "source": source,
            }

        if due_today > 0:
            return {
                "label": "今日焦点",
                "title": "先完成今天的复习任务",
                "meta": "清掉今日待复习内容，再继续练题",
                "query": "帮我复习今天需要回看的知识点",
                "tone": "review",
                "reason": "review_due_today",
                "source": source,
            }

        return {
            "label": "今日焦点",
            "title": "保持节奏，继续推进学习计划",
            "meta": time_budget or "按当前进度继续",
            "query": "继续我的学习计划",
            "tone": "plan",
            "reason": "fallback_plan",
            "source": source,
        }

    def _build_home_study_plan(
        self,
        member: dict[str, Any],
        *,
        weak_nodes: list[dict[str, Any]],
        review: dict[str, Any],
        snapshot: Any | None = None,
        learning: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        learning = learning or self._ensure_learning_profile(member)
        focus_topic = str(member.get("focus_topic") or "").strip()
        focus_hint = f"继续推进 {focus_topic} 的专项训练" if focus_topic else ""
        today_done = int(learning["daily_counts"].get(_date_key()) or 0)
        daily_target = int(member.get("daily_target") or 0)
        weak_names = [item.get("name") for item in weak_nodes[:3] if str(item.get("name") or "").strip()]

        if snapshot is not None:
            plan = build_study_plan_from_learner_snapshot(
                snapshot,
                focus_hint=focus_hint,
                hotspots=weak_names,
                due_today_count=review.get("due_today") or 0,
                total_due=member.get("review_due") or 0,
                overdue_count=review.get("overdue") or 0,
            )
            if plan:
                return plan

        return build_study_plan(
            focus_topic=focus_topic,
            focus_hint=focus_hint,
            weak_points=weak_names,
            hotspots=weak_names,
            today_done=today_done,
            daily_target=daily_target,
            due_today_count=review.get("due_today") or 0,
            total_due=member.get("review_due") or 0,
            overdue_count=review.get("overdue") or 0,
        )

    def _build_home_progress_feedback(
        self,
        member: dict[str, Any],
        *,
        weak_nodes: list[dict[str, Any]],
        snapshot: Any | None = None,
        learning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        learning = learning or self._ensure_learning_profile(member)
        weak_names = [item.get("name") for item in weak_nodes[:3] if str(item.get("name") or "").strip()]

        if snapshot is not None:
            feedback = build_progress_feedback_from_learner_snapshot(
                snapshot,
                daily_counts=learning.get("daily_counts") or {},
                chapter_stats=learning.get("chapter_stats") or {},
                streak_days=member.get("study_days") or 0,
                review_due=member.get("review_due") or 0,
                focus_topic=member.get("focus_topic") or "",
            )
            if feedback:
                return feedback

        today_done = int((learning.get("daily_counts") or {}).get(_date_key()) or 0)
        return build_progress_feedback(
            focus_topic=member.get("focus_topic") or "",
            weak_points=weak_names,
            today_done=today_done,
            daily_target=member.get("daily_target") or 0,
            streak_days=member.get("study_days") or 0,
            review_due=member.get("review_due") or 0,
            daily_counts=learning.get("daily_counts") or {},
            chapter_stats=learning.get("chapter_stats") or {},
        )

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
        last_assessment = member.get("last_assessment") if isinstance(member.get("last_assessment"), dict) else {}
        last_mastery = (
            last_assessment.get("chapter_mastery")
            if isinstance(last_assessment.get("chapter_mastery"), dict)
            else {}
        )
        mastery_items = (
            [
                {
                    "name": (value.get("name") if isinstance(value, dict) else "") or key,
                    "mastery": int((value.get("mastery") if isinstance(value, dict) else value) or 0),
                }
                for key, value in last_mastery.items()
            ]
            if last_mastery
            else self._report_mastery_items(member)
        )
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

        stored_score = last_assessment.get("score") if last_mastery else None
        avg_mastery = (
            round(float(stored_score))
            if stored_score is not None
            else round(
                sum(int(item.get("mastery") or 0) for item in chapter_mastery.values())
                / max(len(chapter_mastery), 1)
            )
        )
        level = "advanced" if avg_mastery >= 75 else "intermediate" if avg_mastery >= 50 else "beginner"
        stored_feedback = (
            last_assessment.get("diagnostic_feedback")
            if isinstance(last_assessment.get("diagnostic_feedback"), dict)
            else None
        )
        if stored_feedback:
            return {
                "score": avg_mastery,
                "knowledge_score": int(last_assessment.get("knowledge_score") or avg_mastery),
                "level": str(last_assessment.get("level") or level),
                "blueprint_version": str(last_assessment.get("blueprint_version") or ""),
                "measurement_confidence": str(last_assessment.get("measurement_confidence") or ""),
                "teaching_policy_seed": dict(last_assessment.get("teaching_policy_seed") or {}),
                "assessment_observability": dict(last_assessment.get("assessment_observability") or {}),
                "chapter_mastery": chapter_mastery,
                "diagnostic_profile": {
                    "learner_archetype": str(
                        dict(stored_feedback.get("learner_profile") or {}).get("archetype") or ""
                    ),
                    "response_profile": str(
                        dict(stored_feedback.get("cognitive_insight") or {}).get("response_profile") or ""
                    ),
                    "calibration_label": str(
                        dict(stored_feedback.get("cognitive_insight") or {}).get("calibration_label") or ""
                    ),
                },
                "diagnostic_feedback": stored_feedback,
            }
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
            try:
                payload = self._build_assessment_blueprint_service().create_session(
                    user_id=user_id,
                    count=count,
                )
            except AssessmentBlueprintUnavailable:
                logger.warning("Assessment blueprint unavailable: user_id=%s count=%s", user_id, count, exc_info=True)
                raise
            quiz_id = f"quiz_{uuid.uuid4().hex[:10]}"
            payload["quiz_id"] = quiz_id
            questions = list(payload["questions"])
            session_questions = list(payload["session_questions"])
            now = _iso()
            data.setdefault("assessment_sessions", {})[quiz_id] = {
                "user_id": user_id,
                "questions": session_questions,
                "blueprint_version": payload["blueprint_version"],
                "sections": list(payload["sections"]),
                "requested_count": payload["requested_count"],
                "delivered_count": payload["delivered_count"],
                "scored_count": payload["scored_count"],
                "profile_count": payload["profile_count"],
                "available_count": payload["available_count"],
                "question_bank_size": payload["question_bank_size"],
                "unique_source_question_count": payload["unique_source_question_count"],
                "shortfall_count": payload["shortfall_count"],
                "fallback_used": bool(payload.get("fallback_used")),
                "created_at": now,
                "observability": {
                    "started_at": now,
                    "first_answer_at": "",
                    "submitted_at": "",
                    "requested_count": payload["requested_count"],
                    "delivered_count": payload["delivered_count"],
                    "scored_count": payload["scored_count"],
                    "profile_count": payload["profile_count"],
                    "completion_rate": 0,
                },
            }
            return {
                "quiz_id": quiz_id,
                "questions": questions,
                "blueprint_version": payload["blueprint_version"],
                "sections": payload["sections"],
                "requested_count": payload["requested_count"],
                "delivered_count": payload["delivered_count"],
                "scored_count": payload["scored_count"],
                "profile_count": payload["profile_count"],
                "available_count": payload["available_count"],
                "question_bank_size": payload["question_bank_size"],
                "unique_source_question_count": payload["unique_source_question_count"],
                "shortfall_count": payload["shortfall_count"],
                "fallback_used": bool(payload.get("fallback_used")),
            }

        return self._mutate(_apply)

    def submit_assessment(self, user_id: str, quiz_id: str, answers: dict[str, str], time_spent_seconds: int) -> dict[str, Any]:
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            session = data.get("assessment_sessions", {}).get(quiz_id)
            if not session:
                raise KeyError(f"Unknown quiz: {quiz_id}")
            questions = session.get("questions", [])
            scored_questions = [question for question in questions if question.get("scored", True)]
            profile_questions = [question for question in questions if not question.get("scored", True)]
            correct = 0
            chapter_hits: dict[str, list[int]] = {}
            chapter_attempts: dict[str, int] = {}
            for question in scored_questions:
                chapter = question["chapter"]
                chapter_hits.setdefault(chapter, [])
                answer = str(answers.get(question["question_id"], "")).strip()
                if answer:
                    chapter_attempts[chapter] = int(chapter_attempts.get(chapter) or 0) + 1
                is_correct = answer.upper() == question["answer"]
                chapter_hits[chapter].append(1 if is_correct else 0)
                correct += 1 if is_correct else 0
            score_pct = round((correct / max(len(scored_questions), 1)) * 100)
            chapter_mastery = {
                chapter: {"name": chapter, "mastery": round(sum(values) / max(len(values), 1) * 100)}
                for chapter, values in chapter_hits.items()
            }
            level = "advanced" if score_pct >= 75 else "intermediate" if score_pct >= 50 else "beginner"
            priority_chapters = [
                {"name": chapter}
                for chapter, _ in sorted(
                    chapter_mastery.items(),
                    key=lambda item: int(item[1].get("mastery") or 0),
                )[:5]
            ]
            score_report = {
                "score_pct": score_pct,
                "priority_chapters": priority_chapters,
            }
            teaching_policy_seed = build_teaching_policy_seed(
                session={**session, "quiz_id": quiz_id},
                answers=answers,
                score_report=score_report,
                time_spent_seconds=time_spent_seconds,
            )
            profile_answered_count = sum(
                1 for question in profile_questions if str(answers.get(question.get("question_id"), "")).strip()
            )
            answered_count = sum(1 for question in questions if str(answers.get(question.get("question_id"), "")).strip())
            submitted_at = _iso()
            completion_rate = round(answered_count / max(len(questions), 1), 4)
            section_empty_counts = _section_empty_counts(session, answers)
            measurement_confidence = teaching_policy_seed["measurement_confidence"]
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
                    "archetype": "policy_seeded",
                    "traits": _profile_traits_from_seed(teaching_policy_seed),
                    "study_tip": _study_tip_from_seed(teaching_policy_seed),
                    "profile_projection": {
                        "source": "assessment_profile_probes",
                        "non_clinical": True,
                        "profile_probe_count": len(profile_questions),
                        "profile_answered_count": profile_answered_count,
                    },
                },
                "action_plan": {
                    "priority_chapters": priority_chapters,
                    "plan_strategy": "先补最弱章节，再做一次 10 题针对训练。",
                },
                "teaching_policy_seed": teaching_policy_seed,
            }
            member = self._ensure_member(data, user_id)
            member["chapter_mastery"].update(chapter_mastery)
            provenance_summary = _provenance_summary(questions)
            observability = {
                **dict(session.get("observability") or {}),
                "submitted_at": submitted_at,
                "time_spent_seconds": int(time_spent_seconds or 0),
                "answered_count": answered_count,
                "scored_answered_count": sum(chapter_attempts.values()),
                "profile_answered_count": profile_answered_count,
                "completion_rate": completion_rate,
                "section_empty_counts": section_empty_counts,
                "measurement_confidence": measurement_confidence,
                "low_confidence_reasons": list(teaching_policy_seed.get("low_confidence_reasons") or []),
                "policy_seed_status": "created",
            }
            session["observability"] = observability
            session["submitted_at"] = submitted_at
            session["teaching_policy_seed"] = teaching_policy_seed
            member["last_assessment"] = {
                "quiz_id": quiz_id,
                "blueprint_version": session.get("blueprint_version") or "diagnostic_v1",
                "score": score_pct,
                "knowledge_score": score_pct,
                "level": level,
                "chapter_mastery": chapter_mastery,
                "question_count": len(questions),
                "scored_count": len(scored_questions),
                "profile_count": len(profile_questions),
                "profile_probe_count": len(profile_questions),
                "profile_answered_count": profile_answered_count,
                "sections": list(session.get("sections") or []),
                "provenance_summary": provenance_summary,
                "measurement_confidence": measurement_confidence,
                "teaching_policy_seed": teaching_policy_seed,
                "assessment_observability": observability,
                "diagnostic_feedback": feedback,
                "completed_at": submitted_at,
            }
            learning = self._ensure_learning_profile(member)
            today = _date_key()
            learning["daily_counts"][today] = int(learning["daily_counts"].get(today) or 0) + sum(chapter_attempts.values())
            if member.get("last_study_date") != today:
                member["study_days"] = int(member.get("study_days") or 0) + 1
                member["last_study_date"] = today
            member["last_active_at"] = submitted_at
            member["last_practice_at"] = submitted_at
            for chapter, values in chapter_hits.items():
                chapter_name = chapter_mastery[chapter]["name"]
                attempted = int(chapter_attempts.get(chapter) or 0)
                if attempted <= 0:
                    continue
                stats = learning["chapter_stats"].setdefault(
                    chapter_name,
                    {"done": 0, "correct": 0, "last_activity_at": ""},
                )
                stats["done"] = int(stats.get("done") or 0) + attempted
                stats["correct"] = int(stats.get("correct") or 0) + sum(values)
                stats["last_activity_at"] = _iso()
            return {
                "score": score_pct,
                "knowledge_score": score_pct,
                "level": level,
                "chapter_mastery": chapter_mastery,
                "blueprint_version": member["last_assessment"]["blueprint_version"],
                "measurement_confidence": measurement_confidence,
                "profile_probe_count": len(profile_questions),
                "profile_answered_count": profile_answered_count,
                "teaching_policy_seed": teaching_policy_seed,
                "assessment_observability": observability,
                "diagnostic_feedback": feedback,
                "diagnostic_profile": {
                    "learner_archetype": feedback["learner_profile"]["archetype"],
                    "response_profile": feedback["cognitive_insight"]["response_profile"],
                    "calibration_label": feedback["cognitive_insight"]["calibration_label"],
                },
            }

        result = self._mutate(_apply)
        self._write_assessment_learning_signals(user_id, quiz_id, result)
        return result

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
        auth_identity = self._auth_identity_for_member(str(member.get("user_id") or "").strip())
        token = self._issue_access_token(
            user_id=auth_identity["user_id"],
            canonical_uid=auth_identity["canonical_uid"],
        )
        return self._build_auth_response(user_id=auth_identity["user_id"], token=token)

    def register_with_external_auth(self, username: str, password: str, phone: str) -> dict[str, Any]:
        external_user = create_external_auth_user(username, password, phone=phone)
        member = self._ensure_member_for_external_auth(username, external_user)
        auth_identity = self._auth_identity_for_member(str(member.get("user_id") or "").strip())
        token = self._issue_access_token(
            user_id=auth_identity["user_id"],
            canonical_uid=auth_identity["canonical_uid"],
        )
        return self._build_auth_response(user_id=auth_identity["user_id"], token=token)

    async def login_with_wechat_code(self, code: str) -> dict[str, Any]:
        normalized = str(code or "").strip()
        if not normalized:
            raise ValueError("code is required")
        try:
            session_payload = await self._exchange_wechat_code(normalized)
        except (RuntimeError, httpx.HTTPError) as exc:
            normalized_exc = self._normalize_wechat_upstream_error(exc, "code2Session")
            logger.warning(
                "wechat mp login upstream failed: action=code2Session dev_fallback=%s detail=%s",
                self._supports_dev_wechat_login(normalized),
                normalized_exc,
            )
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
        auth_identity = self._auth_identity_for_member(target_user_id)
        token = self._issue_access_token(
            user_id=auth_identity["user_id"],
            canonical_uid=auth_identity["canonical_uid"],
            openid=auth_identity["openid"] or openid,
            unionid=auth_identity["unionid"] or unionid,
        )
        return self._build_auth_response(
            user_id=auth_identity["user_id"],
            token=token,
            openid=auth_identity["openid"] or openid,
            unionid=auth_identity["unionid"] or unionid,
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
                logger.warning(
                    "wechat mp bind-phone upstream failed: action=getuserphonenumber user_id=%s dev_fallback=%s detail=%s",
                    user_id,
                    self._supports_dev_wechat_login(raw_code),
                    normalized_exc,
                )
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
        auth_identity = self._auth_identity_for_member(str(result.get("user_id") or "").strip())
        token = self._issue_access_token(
            user_id=auth_identity["user_id"],
            canonical_uid=auth_identity["canonical_uid"],
            openid=auth_identity["openid"] or result["openid"],
            unionid=auth_identity["unionid"] or result["unionid"],
        )
        payload = self._build_auth_response(
            user_id=auth_identity["user_id"],
            token=token,
            openid=auth_identity["openid"] or result["openid"],
            unionid=auth_identity["unionid"] or result["unionid"],
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
        use_real_sms = self._should_use_real_sms()
        production = is_production_environment()

        existing = (self._load().get("phone_codes") or {}).get(normalized) or {}
        created_at = _parse_time(existing.get("created_at"))
        elapsed = max(0, int((now - created_at).total_seconds()))
        if existing and elapsed < retry_after:
            return {
                "sent": False,
                "retry_after": retry_after - elapsed,
                "phone": normalized,
                "message": f"请等待{retry_after - elapsed}秒后再试",
            }

        debug_code = self._generate_sms_code()

        if use_real_sms:
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
        elif production:
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
        auth_identity = self._auth_identity_for_member(str(member.get("user_id") or "").strip())
        token = self._issue_access_token(
            user_id=auth_identity["user_id"],
            canonical_uid=auth_identity["canonical_uid"],
        )
        return self._build_auth_response(user_id=auth_identity["user_id"], token=token)

    def create_demo_token(self, user_id: str) -> str:
        return f"demo-token-{user_id}-{secrets.token_hex(4)}"


_instance: MemberConsoleService | None = None


def get_member_console_service() -> MemberConsoleService:
    global _instance
    if _instance is None:
        _instance = MemberConsoleService()
    return _instance
