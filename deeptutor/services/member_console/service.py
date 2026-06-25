from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
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
import sqlite3
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
from deeptutor.services.assessment.blueprint import get_assessment_blueprint, real_exam_source_policy
from deeptutor.services.assessment import (
    AssessmentBlueprintService,
    AssessmentBlueprintUnavailable,
    QuestionCandidate,
    StaticAssessmentQuestionProvider,
    SupabaseAssessmentQuestionProvider,
)
from deeptutor.services.assessment.learning_evidence import (
    build_assessment_learning_evidence_batch,
)
from deeptutor.services.assessment.deep_explanation import (
    PROMPT_VERSION,
    billable_points_from_usage_summary,
    build_explanation_cache_key,
    generate_llm_deep_explanation,
    minimum_explanation_points,
)
from deeptutor.services.assessment.report_read_model import build_result_report
from deeptutor.services.assessment.scoring import AssessmentScoringError, score_assessment
from deeptutor.services.assessment.session_repository import (
    AssessmentSessionConflict,
    AssessmentSessionError,
    AssessmentSessionNotFound,
    InMemoryAssessmentSessionRepository,
    SupabaseAssessmentSessionRepository,
)
from deeptutor.services.assessment.teaching_policy import build_teaching_policy_seed
from deeptutor.services.assessment.topic_catalog import (
    TopicTestSetUnavailable,
    build_topic_assessment_blueprint,
    classify_topic_form_count,
    get_topic_testset_catalog,
    recommend_assessment_entry,
    resolve_topic_testset_spec,
)
from deeptutor.services.assessment.writeback import AssessmentWritebackService
from deeptutor.services.learner_state.mistake_book import MistakeBookService
from deeptutor.services.learner_state.progress_feedback import (
    build_progress_feedback,
    build_progress_feedback_from_learner_snapshot,
)
from deeptutor.services.learner_state.study_plan import (
    build_study_plan,
    build_study_plan_from_learner_snapshot,
)
from deeptutor.services.learner_state.home_personalization import (
    canonical_home_focus_topic_label,
    is_canonical_home_personalization_projection,
)
from deeptutor.services.internal_qa import internal_qa_billing_bypass_allowed
from deeptutor.services.member_console.external_auth import (
    change_external_auth_password,
    create_external_auth_user,
    delete_external_auth_sessions,
    delete_external_auth_user,
    ensure_external_auth_user_for_phone,
    get_external_auth_user,
    get_external_auth_user_by_phone,
    load_external_auth_users,
    reset_external_auth_password,
    validate_external_auth_password,
    verify_external_auth_user,
)
from deeptutor.services.member_console import rbac
from deeptutor.services.member_console.admin_store import (
    load_admins,
    load_audit,
    load_role_permissions,
    remove_admin,
    set_admin,
    set_role_permissions,
    set_user_overrides,
)
from deeptutor.services.member_console.directory import get_member_directory_read_model
from deeptutor.services.path_service import get_path_service
from deeptutor.services.runtime_env import env_flag, is_production_environment
from deeptutor.services.session import build_user_owner_key, get_sqlite_session_store
from deeptutor.services.wallet.identity import is_uuid_like

_TZ = timezone(timedelta(hours=8))
logger = logging.getLogger(__name__)
BI_OPERATION_START_AT = datetime(2026, 6, 22, 0, 0, tzinfo=_TZ)
# Max wrong OTP guesses before the code is invalidated (brute-force lockout).
_MAX_OTP_ATTEMPTS = 5
_HOME_PERSONALIZATION_ENABLED = "DEEPTUTOR_HOME_PERSONALIZATION_ENABLED"
_TRUSTED_PHONE_ALIAS_SOURCES = frozenset(
    {
        "phone_backfill",
        "member_console_backfill",
        "phone_verification",
    }
)
_WECHAT_PHONE_AUTH_REQUIRED_AFTER_TS = int(datetime(2026, 6, 22, 3, 3, tzinfo=timezone.utc).timestamp())
_MEMBERSHIP_TIER_RANK = {
    "trial": 0,
    "vip": 1,
    "svip": 2,
    "supreme_svip": 3,
}
_ADMIN_ROLE_RANK = {
    rbac.ROLE_ANALYST: 0,
    rbac.ROLE_OPERATOR: 1,
    rbac.ROLE_ADMIN: 2,
    rbac.ROLE_SUPER_ADMIN: 3,
}


def _assessment_writeback_worker_count() -> int:
    try:
        return max(int(os.getenv("ASSESSMENT_WRITEBACK_WORKERS", "2") or 2), 1)
    except (TypeError, ValueError):
        return 2


_ASSESSMENT_WRITEBACK_EXECUTOR = ThreadPoolExecutor(
    max_workers=_assessment_writeback_worker_count(),
    thread_name_prefix="assessment-writeback",
)


def _now() -> datetime:
    return datetime.now(_TZ)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _parse_time(value: str | None) -> datetime:
    if not value:
        return _now()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=_TZ)
        return parsed.astimezone(_TZ)
    except ValueError:
        return _now()


def _is_created_within_days(value: str | None, *, now: datetime, days: int) -> bool:
    if not value:
        return False
    try:
        created_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=_TZ)
    age = now - created_at.astimezone(_TZ)
    return timedelta(0) <= age <= timedelta(days=days)


def is_bi_operational_at(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_TZ)
    return parsed.astimezone(_TZ) >= BI_OPERATION_START_AT


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


def _topic_waterproof_dev_candidates() -> list[QuestionCandidate]:
    stems = [
        "屋面卷材防水施工前，基层处理的正确要求是？",
        "地下防水工程施工缝处最应优先控制的质量风险是？",
        "防水卷材搭接施工中，最符合质量控制要求的是？",
        "涂膜防水施工时，胎体增强材料铺贴应注意什么？",
        "有防水要求的房间蓄水试验，最核心的验收关注点是？",
        "后浇带防水节点施工，正确的管理要求是？",
        "屋面细部构造防水处理，最容易造成渗漏的做法是？",
        "地下室外墙防水保护层施工，正确的顺序控制是？",
        "防水工程隐蔽验收前，施工单位应重点核查什么？",
        "卷材防水层空鼓、翘边的常见原因是什么？",
        "穿墙管防水节点处理，正确做法是什么？",
        "卫生间防水施工完成后，交付前应如何验证质量？",
        "防水基层含水率不满足要求时，直接铺贴卷材的后果是？",
        "防水材料进场验收时，最关键的资料核查是？",
        "屋面泛水部位防水高度控制，主要防止哪类问题？",
    ]
    candidates: list[QuestionCandidate] = []
    for index, stem in enumerate(stems, start=1):
        answer = "A" if index % 4 else "AB"
        qtype = "multi_choice" if index % 4 == 0 else "single_choice"
        candidates.append(
            QuestionCandidate(
                source_question_id=f"dev_waterproof_{index}",
                question_stem=stem,
                question_type=qtype,
                chapter="防水工程",
                options=(
                    ("A", "按规范和方案要求处理并验收"),
                    ("B", "跳过验收直接进入下道工序"),
                    ("C", "仅凭经验判断即可"),
                    ("D", "用后续装饰层掩盖缺陷"),
                ),
                answer=answer,
                source_type="DEV_FALLBACK",
                node_code="1A413050",
                source_meta={
                    "topic": "防水",
                    "semantic_signature": f"dev_waterproof_sig_{index}",
                    "simple_explanation": "防水题应围绕基层、节点、搭接、蓄水或隐蔽验收等关键质量控制点判断。",
                },
            )
        )
    return candidates


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


# Round 5 B1: bound the in-JSON idempotency index so an attacker with a valid
# admin token cannot DoS the member_console store by sending unlimited unique
# X-Idempotency-Key values. FIFO eviction (dict insertion order, Python 3.7+).
# At ~64 bytes per entry, 10k entries ≈ 640 KB additional JSON payload — well
# within working set, and large enough to absorb weeks of legitimate retries.
AUDIT_IDEMPOTENCY_INDEX_MAX = 10_000


class MemberConsoleService:
    # One-shot guard so the default-auth-secret warning is not logged per token verify.
    _warned_default_auth_secret = False

    def __init__(self, *, member_directory: Any | None = None) -> None:
        self._lock = threading.RLock()
        self._path_service = get_path_service()
        self._store = get_sqlite_session_store()
        self._data_path = self._path_service.get_settings_file("member_console")
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        self._member_directory_explicit = member_directory is not None
        self._member_directory = member_directory or get_member_directory_read_model()
        self._assessment_sessions_supabase_required_but_missing = False
        self._assessment_session_repository = self._build_assessment_session_repository()
        self._wechat_access_token: str = ""
        self._wechat_access_token_expires_at: float = 0.0

    def _build_assessment_session_repository(self):
        use_supabase = is_production_environment() or env_flag(
            "ASSESSMENT_SESSIONS_USE_SUPABASE",
            default=False,
        )
        if use_supabase:
            repository = SupabaseAssessmentSessionRepository()
            if repository.is_configured:
                return repository
            if is_production_environment():
                self._assessment_sessions_supabase_required_but_missing = True
        return InMemoryAssessmentSessionRepository()

    def _require_durable_assessment_sessions(self) -> None:
        if self._assessment_sessions_supabase_required_but_missing:
            raise AssessmentSessionError("assessment_sessions_supabase_not_configured")

    def _get_learner_state_service(self):
        from deeptutor.services.learner_state import get_learner_state_service

        return get_learner_state_service()

    def _get_overlay_service(self):
        from deeptutor.services.learner_state import get_bot_learner_overlay_service

        return get_bot_learner_overlay_service()

    def _get_wallet_service(self):
        from deeptutor.services.wallet.service import get_wallet_service

        return get_wallet_service()

    def _build_assessment_blueprint_service(self, blueprint_version: str = "diagnostic_v1") -> AssessmentBlueprintService:
        allow_dev_fallback = env_flag(
            "ASSESSMENT_ALLOW_DEV_FALLBACK",
            default=False,
        )
        candidates = _assessment_bank_candidates()
        if blueprint_version.startswith("topic_"):
            candidates = [*candidates, *_topic_waterproof_dev_candidates()]
        fallback_provider = StaticAssessmentQuestionProvider(candidates)
        use_supabase = is_production_environment() or env_flag(
            "ASSESSMENT_USE_SUPABASE",
            default=False,
        )
        return AssessmentBlueprintService(
            blueprint=get_assessment_blueprint(blueprint_version),
            provider=SupabaseAssessmentQuestionProvider() if use_supabase else fallback_provider,
            fallback_provider=fallback_provider,
            allow_dev_fallback=allow_dev_fallback,
        )

    def prewarm_assessment_forms(self) -> dict[str, Any]:
        return self._build_assessment_blueprint_service().prewarm_forms()

    def generate_and_persist_assessment_forms(self) -> dict[str, Any]:
        return self._build_assessment_blueprint_service().generate_and_persist_forms()

    def get_assessment_topic_catalog(self, user_id: str = "") -> dict[str, Any]:
        provider = SupabaseAssessmentQuestionProvider()
        use_supabase = is_production_environment() or env_flag(
            "ASSESSMENT_USE_SUPABASE",
            default=False,
        )
        specs = get_topic_testset_catalog()
        active_form_summaries: dict[str, dict[str, Any]] = {}
        if use_supabase:
            try:
                active_form_summaries = provider.active_form_summaries(
                    [spec.blueprint_version for spec in specs]
                )
            except Exception:
                logger.warning("Assessment topic form metadata unavailable", exc_info=True)
        topics: list[dict[str, Any]] = []
        for spec in specs:
            form_count = 0
            quality_status = "not_checked"
            if use_supabase:
                metadata = active_form_summaries.get(spec.blueprint_version)
                if metadata is None:
                    quality_status = "unavailable"
                else:
                    form_count = int(metadata.get("active_form_count") or 0)
                    quality_status = "insufficient_forms"
                    if bool(metadata.get("fallback_used")):
                        quality_status = "fallback_form_bank"
                    elif classify_topic_form_count(form_count) in {"stable", "pilot"}:
                        quality_status = "validated"
            status = classify_topic_form_count(form_count)
            if quality_status == "fallback_form_bank":
                status = "authoring_needed"
            topics.append(
                {
                    "topic_id": spec.topic_id,
                    "label": spec.label,
                    "short_label": spec.short_label,
                    "description": spec.description,
                    "blueprint_version": spec.blueprint_version,
                    "status": status,
                    "enabled": status in {"stable", "pilot"},
                    "form_count": form_count,
                    "minimum_form_count": 3,
                    "target_form_count": 5,
                    "quality_status": quality_status,
                }
            )
        weak_nodes, has_assessment_history = self._assessment_recommendation_signals(user_id)
        return {
            "recommendation": recommend_assessment_entry(
                topics,
                weak_nodes=weak_nodes,
                has_assessment_history=has_assessment_history,
            ),
            "topics": topics,
        }

    def _assessment_recommendation_signals(self, user_id: str) -> tuple[list[dict[str, Any]], bool]:
        if not str(user_id or "").strip():
            return [], False
        try:
            member = self._load_member_snapshot(user_id)["member"]
        except Exception:
            logger.warning("Assessment recommendation signals unavailable: user_id=%s", user_id, exc_info=True)
            return [], False
        last_assessment_items = self._last_assessment_mastery_items(member)
        if last_assessment_items:
            weak_nodes = [
                {"name": str(item.get("name") or ""), "mastery": int(item.get("mastery") or 0)}
                for item in last_assessment_items
                if int(item.get("mastery") or 0) < 60
            ]
            return weak_nodes, True
        progress_items = self._chapter_mastery_items(member)
        weak_nodes = [
            {"name": str(item.get("name") or ""), "mastery": int(item.get("mastery") or 0)}
            for item in progress_items
            if int(item.get("mastery") or 0) < 60
        ]
        return weak_nodes, False

    def _write_assessment_learning_signals(
        self,
        user_id: str,
        quiz_id: str,
        result: dict[str, Any],
        *,
        learning_evidence_batch: dict[str, Any] | None = None,
    ) -> None:
        seed = dict(result.get("teaching_policy_seed") or {})
        bot_id = CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0]
        if learning_evidence_batch:
            try:
                from deeptutor.services.construction_grading.writeback import (
                    write_grading_error_events,
                )

                write_grading_error_events(
                    learner_state_service=self._get_learner_state_service(),
                    user_id=user_id,
                    grading_result=learning_evidence_batch,
                    source_id=quiz_id,
                    source_bot_id=bot_id,
                    include_success_events=True,
                )
            except Exception:
                logger.warning("Failed to write assessment learning_evidence events: user_id=%s quiz_id=%s", user_id, quiz_id, exc_info=True)
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
                "id": "vip",
                "label": "VIP",
                "points": 9000,
                "turns": 450,
                "price": "198",
                "original_price": "298",
                "badge": "",
                "per": "450 次 AI 学习额度",
                "per_turn_price": "0.44",
                "audience": "有基础的、二战的、在职的考生",
                "desc": "AI智能答疑、AI案例批改、错因专训、定制个人学习规划、摸底测试、专题测评、学习报告",
            },
            {
                "id": "svip",
                "label": "SVIP",
                "points": 28000,
                "turns": 1400,
                "price": "598",
                "original_price": "798",
                "badge": "班主任督学",
                "per": "1400 次 AI 学习额度",
                "per_turn_price": "0.427",
                "audience": "基础偏弱、学习时间充裕、疑问频繁的考生",
                "desc": "AI答疑、案例批改、错因专训、定制个人学习规划、摸底测试、专题测评、学习报告、班主任督学服务",
            },
            {
                "id": "supreme_svip",
                "label": "至尊SVIP",
                "points": 50000,
                "turns": 2500,
                "price": "998",
                "original_price": "1298",
                "badge": "最高性价比",
                "per": "2500 次 AI 学习额度",
                "per_turn_price": "0.399",
                "audience": "零基础纯自学，对考试没信心，处处需答疑的考生",
                "desc": "AI答疑、案例批改、错因专训、定制个人学习规划、摸底测试、专题测评、学习报告、班主任督学服务",
            },
        ]

    @staticmethod
    def _normalize_membership_package(item: dict[str, Any]) -> dict[str, Any]:
        package_id = str(item.get("id") or item.get("package_id") or "").strip()
        label = str(item.get("label") or item.get("name") or package_id).strip()
        tier = str(item.get("tier") or item.get("plan") or package_id).strip()
        if not package_id:
            raise ValueError("package id is required")
        try:
            points = int(item.get("points") or 0)
        except (TypeError, ValueError):
            points = 0
        try:
            turns = int(item.get("turns") or 0)
        except (TypeError, ValueError):
            turns = 0
        price = str(item.get("price") or item.get("price_cny") or item.get("priceCny") or "0").strip()
        status = str(item.get("status") or item.get("state") or "active").strip() or "active"
        if status not in {"active", "draft", "archived"}:
            status = "active"
        package = {
            "id": package_id,
            "label": label or package_id,
            "tier": tier or package_id,
            "points": max(0, points),
            "turns": max(0, turns),
            "price": price or "0",
            "original_price": str(item.get("original_price") or item.get("originalPrice") or "").strip(),
            "badge": str(item.get("badge") or "").strip(),
            "per": str(item.get("per") or "").strip(),
            "per_turn_price": str(item.get("per_turn_price") or item.get("perTurnPrice") or "").strip(),
            "audience": str(item.get("audience") or "").strip(),
            "desc": str(item.get("desc") or item.get("description") or "").strip(),
            "status": status,
        }
        if not package["per"] and package["turns"] > 0:
            package["per"] = f"{package['turns']} 次 AI 学习额度"
        if not package["per_turn_price"] and package["turns"] > 0:
            try:
                per_turn_price = float(package["price"]) / package["turns"]
                package["per_turn_price"] = f"{per_turn_price:.3f}".rstrip("0").rstrip(".")
            except (TypeError, ValueError, ZeroDivisionError):
                package["per_turn_price"] = ""
        return package

    @classmethod
    def _normalize_package_catalog(cls, packages: Any) -> list[dict[str, Any]]:
        defaults = [cls._normalize_membership_package(item) for item in cls._default_packages()]
        if not isinstance(packages, list) or not packages:
            return defaults
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in packages:
            if not isinstance(item, dict):
                continue
            try:
                package = cls._normalize_membership_package(item)
            except ValueError:
                continue
            if package["id"] in seen:
                continue
            normalized.append(package)
            seen.add(package["id"])
        for package in defaults:
            if package["id"] not in seen:
                normalized.append(package)
        return normalized or defaults

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
            "display_name": "",
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
            "points_balance": 0,
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
    def _conversation_source(row: dict[str, Any]) -> str:
        preferences = row.get("preferences")
        if isinstance(preferences, dict):
            source = str(preferences.get("source") or "").strip()
            if source:
                return source
        return str(row.get("source") or "").strip()

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
        include_messages: bool = False,
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
            if not visible_messages:
                continue
            conversation = {
                "session_id": session_id,
                "title": str(row.get("title") or "未命名会话"),
                "created_at": self._session_time_to_iso(row.get("created_at")),
                "updated_at": self._session_time_to_iso(row.get("updated_at")),
                "source": self._conversation_source(row),
                "capability": str(row.get("capability") or "chat"),
                "message_count": int(row.get("message_count") or len(raw_messages)),
                "last_message": self._preview_chat_content(row.get("last_message")),
            }
            if include_messages:
                conversation["messages"] = [
                    {
                        "id": str(message.get("id") or ""),
                        "role": str(message.get("role") or ""),
                        "content": self._preview_chat_content(message.get("content")),
                        "created_at": self._session_time_to_iso(message.get("created_at")),
                        "capability": str(message.get("capability") or ""),
                    }
                    for message in visible_messages
                ]
            conversations.append(conversation)
        return conversations

    def list_member_conversations(
        self,
        user_id: str,
        *,
        limit: int = 20,
        message_limit: int = 12,
        q: str = "",
        source: str = "",
        capability: str = "",
        sort: str = "updated_at",
        order: str = "desc",
    ) -> dict[str, Any]:
        data = self._load()
        member = self._find_member(data, user_id)
        normalized_limit = max(1, min(int(limit or 20), 100))
        normalized_message_limit = max(1, min(int(message_limit or 12), 50))
        normalized_query = str(q or "").strip()
        normalized_source = str(source or "").strip()
        normalized_capability = str(capability or "").strip()
        normalized_sort = str(sort or "updated_at").strip().lower()
        if normalized_sort not in {"updated_at", "created_at", "message_count", "title", "source", "capability"}:
            normalized_sort = "updated_at"
        normalized_order = str(order or "desc").strip().lower()
        if normalized_order not in {"asc", "desc"}:
            normalized_order = "desc"
        # Fetch a wider owner slice before applying BI-console filters so a
        # narrow query is not accidentally starved by the default top-20 page.
        load_limit = (
            100
            if any((normalized_query, normalized_source, normalized_capability))
            or normalized_sort != "updated_at"
            or normalized_order != "desc"
            else normalized_limit
        )
        conversations = self._load_recent_conversations_for_member(
            member,
            user_id,
            session_limit=load_limit,
            message_limit=normalized_message_limit,
        )
        if normalized_query:
            query_lower = normalized_query.lower()
            conversations = [
                item
                for item in conversations
                if query_lower
                in " ".join(
                    [
                        str(item.get("session_id") or ""),
                        str(item.get("title") or ""),
                        str(item.get("source") or ""),
                        str(item.get("capability") or ""),
                        str(item.get("last_message") or ""),
                    ]
                ).lower()
            ]
        if normalized_source:
            source_lower = normalized_source.lower()
            conversations = [
                item
                for item in conversations
                if str(item.get("source") or "").lower() == source_lower
            ]
        if normalized_capability:
            capability_lower = normalized_capability.lower()
            conversations = [
                item
                for item in conversations
                if str(item.get("capability") or "").lower() == capability_lower
            ]

        def sort_value(item: dict[str, Any]) -> Any:
            if normalized_sort == "message_count":
                return int(item.get("message_count") or 0)
            return str(item.get(normalized_sort) or "").lower()

        conversations = sorted(
            conversations,
            key=lambda item: (sort_value(item), str(item.get("session_id") or "")),
            reverse=normalized_order == "desc",
        )
        filtered_total = len(conversations)
        conversations = conversations[:normalized_limit]
        return {
            "user_id": user_id,
            "items": conversations,
            "total": filtered_total,
            "limit": normalized_limit,
            "message_limit": normalized_message_limit,
            "sort": normalized_sort,
            "order": normalized_order,
            "filters": {
                "q": normalized_query,
                "source": normalized_source,
                "capability": normalized_capability,
            },
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
                "focus_query": "请根据我的学习记录和最近进度，围绕施工组织设计安排下一步学习推进：先判断我当前更适合知识讲解、例题带练、错因复盘还是少量自测，再用建筑实务考试口径展开；不要默认生成整套训练题，也不要提前假设我的阶段层级。",
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
        normalized_packages = self._normalize_package_catalog(data.get("packages"))
        packages_changed = normalized_packages != data.get("packages")
        data["packages"] = normalized_packages
        data.setdefault("audit_log", [])
        data.setdefault("assessment_sessions", {})
        data.setdefault("phone_codes", {})
        # Round 4 S1: idempotency dedup index — key = f"{action}:{idempotency_key}", value = audit_id.
        data.setdefault("audit_idempotency_keys", {})
        if self._apply_legacy_chat_learning_migration(data) or packages_changed:
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
            "qa_",
            "qa-",
            "qa.",
            "casefix",
            "codex",
            "probe",
            "audit",
            "prelaunch",
            "prelaunchsmoke",
            "preflight",
            "smoke",
            "soak",
            "debug",
            "mock",
            "dummy",
            "fake",
            "compiled_shadow",
            "synthetic",
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
        target_points = int(target.get("points_balance") or 0)
        source_points = int(source.get("points_balance") or 0)
        alias_user_ids = {
            str(item).strip()
            for item in list(target.get("alias_user_ids") or []) + list(source.get("alias_user_ids") or [])
            if str(item).strip()
        }
        search_aliases = self._member_search_alias_values(target, source)
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
        target["search_aliases"] = sorted(search_aliases)
        target["points_balance"] = max(target_points, source_points, int(target.get("points_balance") or 0))
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
                member["alias_user_ids"] = sorted(
                    {
                        str(value or "").strip()
                        for value in [
                            member.get("user_id"),
                            member.get("canonical_user_id"),
                            member.get("external_auth_user_id"),
                            *list(member.get("alias_user_ids") or []),
                        ]
                        if str(value or "").strip()
                    }
                )
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

    def _member_overlay_keys_for_directory(self, member: dict[str, Any]) -> set[str]:
        keys = {
            str(member.get("user_id") or "").strip(),
            str(member.get("canonical_user_id") or "").strip(),
            str(member.get("external_auth_user_id") or "").strip(),
            *[str(value or "").strip() for value in list(member.get("alias_user_ids") or [])],
        }
        phone = _normalize_phone_input(str(member.get("phone") or ""))
        if phone:
            keys.add(f"phone:{phone}")
        return {key for key in keys if key}

    @staticmethod
    def _member_search_alias_values(*members: dict[str, Any] | None) -> set[str]:
        values: set[str] = set()
        for member in members:
            if not isinstance(member, dict):
                continue
            for key in (
                "user_id",
                "canonical_user_id",
                "canonical_uid",
                "external_auth_user_id",
                "auth_username",
                "display_name",
                "identifier",
                "phone",
                "wx_openid",
                "openid",
                "wx_unionid",
                "unionid",
            ):
                value = str(member.get(key) or "").strip()
                if not value:
                    continue
                values.add(value)
                if key == "phone":
                    digits = re.sub(r"\D+", "", value)
                    if digits:
                        values.add(digits)
            for key in ("alias_user_ids", "search_aliases"):
                for value in list(member.get(key) or []):
                    normalized = str(value or "").strip()
                    if normalized:
                        values.add(normalized)
        return values

    def _member_console_overlay_index(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        overlays: dict[str, dict[str, Any]] = {}
        for raw_member in data.get("members") or []:
            if not isinstance(raw_member, dict):
                continue
            for key in self._member_overlay_keys_for_directory(raw_member):
                existing = overlays.get(key)
                if existing is None or self._is_better_member_console_overlay(raw_member, existing, key):
                    overlays[key] = raw_member
        return overlays

    def _member_console_merged_aliases(
        self,
        data: dict[str, Any],
        overlay_index: dict[str, dict[str, Any]],
    ) -> dict[str, set[str]]:
        aliases_by_user_id: dict[str, set[str]] = {}
        for raw_member in data.get("members") or []:
            if not isinstance(raw_member, dict):
                continue
            resolved = self._resolve_member_console_overlay(overlay_index, raw_member)
            if not isinstance(resolved, dict) or resolved is raw_member:
                continue
            resolved_user_id = str(resolved.get("user_id") or "").strip()
            if not resolved_user_id:
                continue
            aliases_by_user_id.setdefault(resolved_user_id, set()).update(
                self._member_search_alias_values(raw_member)
            )
        return aliases_by_user_id

    @staticmethod
    def _member_alias_user_id_values(values: set[str]) -> set[str]:
        return {
            value
            for value in values
            if is_uuid_like(value) or value.startswith("auth_")
        }

    def _is_better_member_console_overlay(
        self,
        candidate: dict[str, Any],
        existing: dict[str, Any],
        key: str,
    ) -> bool:
        def rank(member: dict[str, Any]) -> tuple[int, int, int, int, int, float, int]:
            user_id = str(member.get("user_id") or "").strip()
            merged_into = str(member.get("merged_into") or "").strip()
            tier = str(member.get("tier") or "").strip()
            key_value = str(key or "").strip()
            direct_user_id_match = 1 if user_id and user_id == key_value else 0
            non_auth_wrapper = 0 if user_id.startswith("auth_") else 1
            canonical_uuid_user_id = 1 if is_uuid_like(user_id) else 0
            canonical_root = 1 if not merged_into else 0
            paid_tier = 1 if tier and tier != "trial" else 0
            expire_ts = _parse_time(member.get("expire_at")).timestamp()
            signal_score = self._member_signal_score(member)
            return (
                direct_user_id_match,
                non_auth_wrapper,
                canonical_uuid_user_id,
                canonical_root,
                paid_tier,
                expire_ts,
                signal_score,
            )

        return rank(candidate) > rank(existing)

    def _resolve_member_console_overlay(
        self,
        overlay_index: dict[str, dict[str, Any]],
        overlay: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        current = overlay
        seen: set[str] = set()
        while isinstance(current, dict):
            user_id = str(current.get("user_id") or "").strip()
            if user_id:
                if user_id in seen:
                    break
                seen.add(user_id)
            merged_into = str(current.get("merged_into") or "").strip()
            if not merged_into or merged_into == user_id:
                break
            next_overlay = overlay_index.get(merged_into)
            if not isinstance(next_overlay, dict):
                break
            current = next_overlay
        return current

    def _merge_member_console_overlay(
        self,
        member: dict[str, Any],
        overlay: dict[str, Any] | None,
        *,
        source_overlay: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not overlay:
            return member
        merged = deepcopy(member)
        source_overlay = source_overlay if isinstance(source_overlay, dict) else overlay
        resolved_from_merged_account = source_overlay is not overlay
        overlay_aliases = {
            str(value or "").strip()
            for value in [
                overlay.get("user_id"),
                overlay.get("canonical_user_id"),
                overlay.get("external_auth_user_id"),
                *list(overlay.get("alias_user_ids") or []),
            ]
            if str(value or "").strip()
        }
        merged["alias_user_ids"] = sorted(
            {
                str(value or "").strip()
                for value in [
                    merged.get("user_id"),
                    merged.get("canonical_user_id"),
                    merged.get("external_auth_user_id"),
                    *list(merged.get("alias_user_ids") or []),
                    *list(overlay_aliases),
                ]
                if str(value or "").strip()
            }
        )
        merged["search_aliases"] = sorted(self._member_search_alias_values(merged, source_overlay, overlay))
        overlay_user_id = str(overlay.get("user_id") or "").strip()
        if overlay_user_id:
            merged["user_id"] = overlay_user_id
        overlay_external_user_id = str(overlay.get("external_auth_user_id") or "").strip()
        overlay_canonical_user_id = str(overlay.get("canonical_user_id") or "").strip()
        if overlay_external_user_id and is_uuid_like(overlay_external_user_id):
            merged["canonical_user_id"] = overlay_external_user_id
        elif overlay_canonical_user_id:
            merged["canonical_user_id"] = overlay_canonical_user_id
        elif overlay_user_id:
            merged["canonical_user_id"] = overlay_user_id

        phone = self._registered_phone_for_bi(overlay)
        if phone:
            merged["phone"] = phone
        display_name = str(overlay.get("display_name") or "").strip()
        if display_name:
            merged["display_name"] = display_name
        for field in (
            "tier",
            "status",
            "segment",
            "risk_level",
            "auto_renew",
            "created_at",
            "expire_at",
            "auth_username",
            "external_auth_provider",
            "external_auth_user_id",
            "wx_openid",
            "wx_unionid",
        ):
            value = overlay.get(field)
            if value not in (None, "", [], {}):
                merged[field] = deepcopy(value)
        if not resolved_from_merged_account and int(merged.get("points_balance") or 0) <= 0:
            overlay_points = int(overlay.get("points_balance") or 0)
            if overlay_points > 0:
                merged["points_balance"] = overlay_points
        for field in (
            "avatar_url",
            "level",
            "xp",
            "study_days",
            "review_due",
            "focus_topic",
            "chapter_mastery",
            "chapter_practice_stats",
            "daily_practice_counts",
            "ledger",
            "notes",
            "badges",
            "earned_badge_ids",
        ):
            value = overlay.get(field)
            if value not in (None, "", [], {}):
                merged[field] = deepcopy(value)
        return merged

    def _member_directory_authority(self) -> str:
        return (
            "supabase.phone_identity_aliases+v_members"
            if self._member_directory_explicit
            or is_production_environment()
            or env_flag("MEMBER_CONSOLE_USE_SUPABASE_MEMBER_DIRECTORY", default=False)
            else "member_console"
        )

    def _member_directory_enabled(self) -> bool:
        return self._member_directory_authority() == "supabase.phone_identity_aliases+v_members"

    def _load_member_directory_members_for_bi(
        self,
        data: dict[str, Any],
        *,
        include_session_activity_supplements: bool = False,
    ) -> list[dict[str, Any]]:
        directory = self._member_directory
        if not self._member_directory_enabled() or not bool(getattr(directory, "is_configured", False)):
            members = self._members_for_bi(data)
            for member in members:
                member.setdefault("member_directory_source", "member_console")
            return members
        try:
            members = list(directory.list_members(limit=5000))
        except Exception:
            logger.warning("Failed to load Supabase member directory read model", exc_info=True)
            return []
        overlay_index = self._member_console_overlay_index(data)
        merged_aliases = self._member_console_merged_aliases(data, overlay_index)
        merged_members: list[dict[str, Any]] = []
        for member in members:
            if not isinstance(member, dict) or not self._is_registered_member_for_bi(member):
                continue
            overlay = None
            for key in self._member_overlay_keys_for_directory(member):
                overlay = overlay_index.get(key)
                if overlay is not None:
                    break
            resolved_overlay = self._resolve_member_console_overlay(overlay_index, overlay)
            normalized = self._merge_member_console_overlay(
                deepcopy(member),
                resolved_overlay,
                source_overlay=overlay,
            )
            if not self._is_registered_member_for_bi(normalized):
                continue
            canonical_user_id = str(normalized.get("user_id") or "").strip()
            extra_aliases = merged_aliases.get(canonical_user_id) or set()
            if extra_aliases:
                normalized["search_aliases"] = sorted(
                    self._member_search_alias_values(normalized) | extra_aliases
                )
                normalized["alias_user_ids"] = sorted(
                    {
                        str(value or "").strip()
                        for value in [
                            *list(normalized.get("alias_user_ids") or []),
                            *self._member_alias_user_id_values(extra_aliases),
                        ]
                        if str(value or "").strip()
                    }
                )
            normalized.setdefault("member_directory_source", "supabase.phone_identity_aliases+v_members")
            merged_members.append(normalized)
        members_by_user_id: dict[str, dict[str, Any]] = {}
        for member in merged_members:
            user_id = str(member.get("user_id") or "").strip()
            if not user_id:
                continue
            existing = members_by_user_id.get(user_id)
            if existing is None:
                members_by_user_id[user_id] = member
            else:
                members_by_user_id[user_id] = self._merge_canonical_member_for_bi(existing, member)
        merged_members = list(members_by_user_id.values())
        directory_keys = {
            key
            for member in merged_members
            for key in self._canonical_member_keys_for_bi(member)
        }
        local_members = self._members_for_bi(data)
        local_members_with_activity = (
            self._merge_session_activity_for_member_list([deepcopy(member) for member in local_members])
            if include_session_activity_supplements
            else [deepcopy(member) for member in local_members]
        )
        for original, local_member in zip(local_members, local_members_with_activity, strict=False):
            local_user_id = str(local_member.get("user_id") or "").strip()
            local_merged_into = str(local_member.get("merged_into") or "").strip()
            if local_merged_into and local_merged_into != local_user_id:
                continue
            local_keys = self._canonical_member_keys_for_bi(local_member)
            if not local_keys or any(key in directory_keys for key in local_keys):
                continue
            if include_session_activity_supplements and _parse_time(
                local_member.get("last_active_at")
            ) > _parse_time(original.get("last_active_at")):
                local_member["member_directory_source"] = "member_console_session_activity_supplement"
            else:
                local_member["member_directory_source"] = "member_console_local_supplement"
            merged_members.append(local_member)
            directory_keys.update(local_keys)
        return merged_members

    def _merge_session_activity_for_member_list(self, members: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not members:
            return members
        owner_to_members: dict[str, list[dict[str, Any]]] = {}
        for member in members:
            member_user_id = str(member.get("user_id") or "").strip()
            for identity in self._member_session_identity_values(member, member_user_id):
                owner_key = build_user_owner_key(identity)
                if owner_key:
                    owner_to_members.setdefault(owner_key, []).append(member)
        if not owner_to_members:
            return members

        try:
            db_path = self._store.db_path
            latest_by_owner: dict[str, float] = {}
            owner_keys = list(owner_to_members)
            with sqlite3.connect(db_path, timeout=2.0) as conn:
                for start in range(0, len(owner_keys), 500):
                    chunk = owner_keys[start : start + 500]
                    placeholders = ",".join("?" for _ in chunk)
                    rows = conn.execute(
                        f"""
                        SELECT owner_key, MAX(updated_at) AS latest_updated_at
                        FROM sessions
                        WHERE archived = 0 AND owner_key IN ({placeholders})
                        GROUP BY owner_key
                        """,
                        chunk,
                    ).fetchall()
                    for owner_key, latest_updated_at in rows:
                        try:
                            latest_by_owner[str(owner_key)] = float(latest_updated_at or 0)
                        except (TypeError, ValueError):
                            continue
        except Exception:
            logger.warning("Failed to merge session activity into BI member list", exc_info=True)
            return members

        for owner_key, latest_updated_at in latest_by_owner.items():
            latest_iso = self._session_time_to_iso(latest_updated_at)
            if not latest_iso:
                continue
            for member in owner_to_members.get(owner_key, []):
                member["last_active_at"] = self._later_timestamp(
                    member.get("last_active_at"),
                    latest_iso,
                )
        return members

    @staticmethod
    def _normalize_trace_identity(value: Any, *, phone_field: bool = False) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        phone = _normalize_phone_input(raw)
        if phone_field and len(phone) == 11:
            return phone
        if len(phone) == 11 and (raw == phone or raw.startswith("+86") or raw.startswith("86")):
            return phone
        return raw

    @classmethod
    def _trace_identity_values(
        cls,
        *,
        raw_user_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()

        def add(value: Any, *, phone_field: bool = False) -> None:
            normalized = cls._normalize_trace_identity(value, phone_field=phone_field)
            if normalized and normalized not in seen:
                values.append(normalized)
                seen.add(normalized)

        add(raw_user_id)
        if isinstance(metadata, dict):
            for key in (
                "user_id",
                "uid",
                "canonical_uid",
                "canonical_user_id",
                "member_id",
                "external_auth_user_id",
                "openid",
                "wx_openid",
                "unionid",
                "wx_unionid",
            ):
                add(metadata.get(key))
            for key in ("phone", "mobile", "mobile_phone"):
                add(metadata.get(key), phone_field=True)
        return values

    def resolve_trace_identity_for_bi(
        self,
        *,
        raw_user_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        raw = str(raw_user_id or "").strip()
        candidates = self._trace_identity_values(raw_user_id=raw, metadata=metadata)
        if not candidates:
            return {
                "status": "missing",
                "canonical_user_id": "",
                "member_user_id": "",
                "raw_user_id": raw,
                "matched_identity": "",
            }

        identity_index: dict[str, dict[str, str]] = {}
        for member in self._members_for_bi(self._load()):
            member_user_id = str(member.get("user_id") or "").strip()
            canonical_user_id = (
                str(member.get("canonical_user_id") or "").strip()
                or str(member.get("external_auth_user_id") or "").strip()
                or member_user_id
            )
            if not member_user_id or not canonical_user_id:
                continue
            for key in (
                "user_id",
                "canonical_user_id",
                "external_auth_user_id",
                "phone",
                "wx_openid",
                "wx_unionid",
            ):
                identity = self._normalize_trace_identity(
                    member.get(key),
                    phone_field=(key == "phone"),
                )
                if identity:
                    identity_index[identity] = {
                        "canonical_user_id": canonical_user_id,
                        "member_user_id": member_user_id,
                    }
            for alias in list(member.get("alias_user_ids") or []):
                identity = self._normalize_trace_identity(alias)
                if identity:
                    identity_index[identity] = {
                        "canonical_user_id": canonical_user_id,
                        "member_user_id": member_user_id,
                    }

        for candidate in candidates:
            match = identity_index.get(candidate)
            if match:
                return {
                    "status": "resolved",
                    "canonical_user_id": match["canonical_user_id"],
                    "member_user_id": match["member_user_id"],
                    "raw_user_id": raw,
                    "matched_identity": candidate,
                }
        return {
            "status": "unmapped",
            "canonical_user_id": "",
            "member_user_id": "",
            "raw_user_id": raw,
            "matched_identity": "",
        }

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

    def _ensure_member(
        self, data: dict[str, Any], user_id: str, _seen: set[str] | None = None
    ) -> dict[str, Any]:
        normalized_user_id = str(user_id or "").strip()
        reconciled = self._reconcile_external_auth_member(data, normalized_user_id)
        if reconciled is not None:
            self._ensure_learning_profile(reconciled)
            return reconciled
        try:
            member = self._find_member(data, normalized_user_id)
            merged_into = str(member.get("merged_into") or "").strip()
            if merged_into and merged_into != normalized_user_id:
                # Guard against cyclic/broken merge chains (e.g. A->B->A). The
                # self-reference check above only catches 1-step loops; a multi-hop
                # cycle would recurse until RecursionError -> login 500. Track
                # visited ids and stop if the chain revisits one, treating the
                # current member as canonical instead of recursing forever.
                seen = _seen if _seen is not None else set()
                seen.add(normalized_user_id)
                if merged_into in seen:
                    logger.warning(
                        "member merge cycle detected at user_id=%s merged_into=%s; "
                        "treating current member as canonical",
                        normalized_user_id,
                        merged_into,
                    )
                    self._ensure_learning_profile(member)
                    return member
                return self._ensure_member(data, merged_into, seen)
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
        if not phone or phone == synthetic_default_phone:
            return
        desired_user_id = current_external_user_id if is_uuid_like(current_external_user_id) else ""
        if not desired_user_id:
            try:
                alias_ids = self._trusted_phone_alias_user_ids(phone)
            except ValueError as exc:
                logger.warning(
                    "phone-backed external identity alias lookup skipped for user_id=%s phone=%s: %s",
                    member.get("user_id"),
                    phone,
                    exc,
                )
                return
            if alias_ids:
                desired_user_id = next(iter(alias_ids))
        try:
            external_user = ensure_external_auth_user_for_phone(
                phone,
                user_id=desired_user_id or None,
            )
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
        if desired_user_id and external_user_id != desired_user_id:
            logger.warning(
                "phone-backed external identity id mismatch for user_id=%s phone=%s expected=%s actual=%s",
                member.get("user_id"),
                phone,
                desired_user_id,
                external_user_id,
            )
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
        if is_uuid_like(canonical_uid) and not internal_qa_billing_bypass_allowed(
            canonical_uid,
            member.get("user_id"),
            member.get("auth_username"),
            member.get("username"),
        ):
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

        configured = str(
            os.getenv("DEEPTUTOR_AUTH_SECRET")
            or os.getenv("MEMBER_CONSOLE_AUTH_SECRET")
            or os.getenv("WECHAT_MP_TOKEN_SECRET")
            or os.getenv("WECHAT_MP_APP_SECRET")
            or os.getenv("WECHAT_MP_APPSECRET")
            or ""
        ).strip()
        if not configured:
            # Non-production fallback. The literal is public (in source), so any token
            # signed with it is forgeable — acceptable only on a developer machine, never
            # on a shared/staging host. Warn once so a misconfigured staging is visible.
            if not type(self)._warned_default_auth_secret:
                type(self)._warned_default_auth_secret = True
                logger.warning(
                    "Using the public default auth secret — set DEEPTUTOR_AUTH_SECRET. "
                    "Tokens signed with the default are forgeable; never run staging like this."
                )
            return "deeptutor-dev-member-secret"
        return configured

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

    def _wechat_phone_auth_required_after_ts(self) -> int:
        raw = str(os.getenv("DEEPTUTOR_WECHAT_PHONE_AUTH_REQUIRED_AFTER_TS") or "").strip()
        try:
            return max(0, int(raw)) if raw else _WECHAT_PHONE_AUTH_REQUIRED_AFTER_TS
        except (TypeError, ValueError):
            return _WECHAT_PHONE_AUTH_REQUIRED_AFTER_TS

    def _wechat_token_requires_phone_reauth(self, payload: dict[str, Any]) -> bool:
        if str(payload.get("provider") or "").strip() != "wechat_mp":
            return False
        min_iat = self._wechat_phone_auth_required_after_ts()
        if min_iat <= 0:
            return False
        try:
            issued_at = int(payload.get("orig_iat") or payload.get("iat") or 0)
        except (TypeError, ValueError):
            return True
        return issued_at < min_iat

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

    def _verify_access_token(self, token: str, *, verify_exp: bool = True) -> dict[str, Any] | None:
        raw = str(token or "").strip()
        if not raw:
            return None
        if raw.startswith("demo-token-"):
            # Unsigned demo tokens grant any uid without verification — a full account
            # takeover if ever reachable. Fail closed in production AND require an explicit
            # opt-in flag elsewhere (default off), so a misconfigured DEEPTUTOR_ENV alone
            # cannot open this door.
            if is_production_environment():
                return None
            if os.getenv("DEEPTUTOR_DEMO_TOKENS_ENABLED", "").strip().lower() not in ("1", "true", "yes"):
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
        try:
            exp = int(payload.get("exp"))
        except (TypeError, ValueError):
            return None
        now = int(_now().timestamp())
        if verify_exp and exp <= now:
            return None
        if self._wechat_token_requires_phone_reauth(payload):
            return None
        return payload

    def verify_access_token(self, token: str) -> dict[str, Any] | None:
        return self._verify_access_token(token)

    def _bi_admins_path(self) -> Path:
        return self._path_service.user_data_dir / "bi_admins.json"

    def _env_admin_user_ids(self) -> set[str]:
        """env 引导名单（bootstrap/保底，UI 不可移除）。"""
        return self._admin_user_ids()

    def get_admin_role(self, user_id: str | None) -> str | None:
        """返回 BI 角色：env 引导→super_admin；文件→其角色；非管理员→None。"""
        resolved = str(user_id or "").strip()
        if not resolved:
            return None
        if resolved in self._env_admin_user_ids():
            return rbac.ROLE_SUPER_ADMIN
        record = load_admins(self._bi_admins_path()).get(resolved)
        if not record:
            return None
        # fail-closed：持久化中出现非法/被篡改的 role 不再回落 admin（normalize 默认会提权），
        # 而是视为非管理员并告警。授权权威必须在坏数据面前关闭，而非开放。
        raw = str(record.get("role") or "").strip()
        if not rbac.is_valid_role(raw):
            logger.warning(
                "bi_admins.json 含非法角色 %r (user=%s)，fail-closed 视为非管理员", raw, resolved
            )
            return None
        return raw

    def is_admin_user(self, user_id: str | None) -> bool:
        """兼容旧布尔门：super_admin / admin 视为完整管理员。"""
        return rbac.is_full_admin(self.get_admin_role(user_id))

    def _role_permissions_store(self) -> dict[str, Any]:
        return load_role_permissions(self._bi_admins_path())

    def _user_overrides(self, user_id: str) -> dict[str, Any]:
        record = load_admins(self._bi_admins_path()).get(str(user_id or "").strip()) or {}
        ov = record.get("permission_overrides")
        return ov if isinstance(ov, dict) else {}

    def get_effective_permissions(self, user_id: str | None) -> dict[str, list[str]]:
        """某管理员的最终生效权限矩阵（角色权限[可被编辑] 叠加 per-user 覆盖）。"""
        role = self.get_admin_role(user_id)
        if role is None:
            return {tab: [] for tab in rbac.TABS}
        effective = rbac.resolve_effective_permissions(
            role, self._role_permissions_store(), self._user_overrides(str(user_id or "").strip())
        )
        return rbac.matrix_to_lists(effective)

    def can_access(self, user_id: str | None, tab: str, action: str) -> bool:
        role = self.get_admin_role(user_id)
        if role is None:
            return False
        effective = rbac.resolve_effective_permissions(
            role, self._role_permissions_store(), self._user_overrides(str(user_id or "").strip())
        )
        return rbac.can_resolved(effective, tab, action)

    def can_manage_permissions(self, user_id: str | None) -> bool:
        return rbac.can_manage_permissions(self.get_admin_role(user_id))

    def roles_payload(self) -> dict[str, Any]:
        """角色定义 + 生效权限矩阵（含管理员已编辑）+ 可编辑标记。"""
        return rbac.roles_payload(self._role_permissions_store())

    def set_role_permissions(
        self, *, actor: str, role: str, matrix: dict[str, Any], at: str = ""
    ) -> dict[str, Any]:
        """权限管理员编辑某角色权限矩阵（super_admin 角色锁定不可编辑，防锁死）。"""
        if not self.can_manage_permissions(actor):
            raise PermissionError("仅权限管理员可编辑 BI 角色权限")
        if not rbac.is_valid_role(role):
            raise ValueError(f"未知角色: {role}")
        if not rbac.is_role_editable(role):
            raise ValueError("超级管理员角色恒为全权，不可编辑")
        normalized = rbac.normalize_matrix(matrix)
        set_role_permissions(self._bi_admins_path(), role, normalized, actor=actor, at=at)
        return self.roles_payload()

    def set_user_permission_overrides(
        self, *, actor: str, user_id: str, overrides: dict[str, Any], at: str = ""
    ) -> list[dict[str, Any]]:
        """精确到人：给某管理员设个人权限覆盖（env 超管 + super_admin 角色不可覆盖）。"""
        if not self.can_manage_permissions(actor):
            raise PermissionError("仅权限管理员可设置个人权限覆盖")
        normalized = str(user_id or "").strip()
        if normalized in self._env_admin_user_ids():
            raise ValueError("系统引导超级管理员恒为全权，不可设置个人权限覆盖")
        role = self.get_admin_role(normalized)
        if role is None:
            raise ValueError("该用户不是管理员")
        if role in rbac.LOCKED_ROLES:
            raise ValueError("超级管理员恒为全权，不可设置个人权限覆盖")
        norm = rbac.normalize_matrix(overrides)
        # 只保留调用方明确提交的 tab（未提交的 tab 不写 override，回落角色默认）
        submitted = {tab: norm[tab] for tab in overrides.keys() if tab in rbac.TABS}
        set_user_overrides(self._bi_admins_path(), normalized, submitted, actor=actor, at=at)
        return self.list_admin_user_ids()

    def _safe_member_display_name(self, user_id: str) -> str:
        try:
            profile = self.get_profile(user_id)
            return str(profile.get("display_name") or profile.get("username") or "")
        except Exception:
            return ""

    def list_admin_user_ids(self) -> list[dict[str, Any]]:
        """合并 env 引导(super_admin,不可改/删) + 运行时增量(带角色+生效权限+个人覆盖)。"""
        env_ids = self._env_admin_user_ids()
        file_admins = load_admins(self._bi_admins_path())
        role_store = self._role_permissions_store()
        out: list[dict[str, Any]] = []
        super_eff = rbac.resolve_role_permissions(rbac.ROLE_SUPER_ADMIN, role_store)
        for uid in sorted(env_ids):
            out.append(
                {
                    "user_id": uid,
                    "role": rbac.ROLE_SUPER_ADMIN,
                    "role_label": rbac.ROLE_LABELS[rbac.ROLE_SUPER_ADMIN],
                    "display_name": self._safe_member_display_name(uid),
                    "source": "env",
                    "removable": False,
                    "editable": False,
                    "has_overrides": False,
                    "accessible_tabs": rbac.accessible_tabs_resolved(super_eff),
                    "effective_matrix": rbac.matrix_to_lists(super_eff),
                }
            )
        for uid in sorted(set(file_admins) - env_ids):
            record = file_admins[uid]
            raw_role = str(record.get("role") or "").strip()
            if not rbac.is_valid_role(raw_role):
                # fail-closed：非法角色条目不在管理员列表里展示成正常 admin
                logger.warning("跳过 bi_admins.json 中非法角色条目 %r (user=%s)", raw_role, uid)
                continue
            role = raw_role
            overrides = record.get("permission_overrides")
            overrides = overrides if isinstance(overrides, dict) else {}
            eff = rbac.resolve_effective_permissions(role, role_store, overrides)
            out.append(
                {
                    "user_id": uid,
                    "role": role,
                    "role_label": rbac.ROLE_LABELS[role],
                    "display_name": record.get("display_name")
                    or self._safe_member_display_name(uid),
                    "granted_by": record.get("granted_by") or "",
                    "granted_at": record.get("granted_at") or "",
                    "source": "runtime",
                    "removable": True,
                    "editable": True,
                    "has_overrides": bool(overrides),
                    "permission_overrides": rbac.normalize_matrix(overrides)
                    if overrides
                    else {},
                    "accessible_tabs": rbac.accessible_tabs_resolved(eff),
                    "effective_matrix": rbac.matrix_to_lists(eff),
                }
            )
        return out

    def set_admin_role(
        self, *, actor: str, user_id: str, role: str, display_name: str = "", at: str = ""
    ) -> list[dict[str, Any]]:
        """新增管理员或改其角色（service 层自校验 actor，纵深防御）。"""
        if not self.can_manage_permissions(actor):
            raise PermissionError("仅权限管理员可分配 BI 管理员角色")
        normalized = str(user_id or "").strip()
        if not normalized:
            raise ValueError("user_id is required")
        if not rbac.is_valid_role(role):
            raise ValueError(f"未知角色: {role}")
        if normalized in self._env_admin_user_ids():
            raise ValueError("系统引导管理员恒为超级管理员，不可改角色")
        set_admin(
            self._bi_admins_path(),
            normalized,
            role=role,
            display_name=display_name,
            actor=actor,
            granted_at=at,
        )
        return self.list_admin_user_ids()

    def add_admin_user(
        self, user_id: str, *, actor: str = "", role: str = rbac.ROLE_ADMIN, at: str = ""
    ) -> list[dict[str, Any]]:
        normalized = str(user_id or "").strip()
        if not normalized:
            raise ValueError("user_id is required")
        if normalized in self._env_admin_user_ids():
            return self.list_admin_user_ids()
        return self.set_admin_role(actor=actor, user_id=normalized, role=role, at=at)

    def remove_admin_user(
        self, user_id: str, *, actor: str = "", at: str = ""
    ) -> list[dict[str, Any]]:
        if not self.can_manage_permissions(actor):
            raise PermissionError("仅权限管理员可移除 BI 管理员")
        normalized = str(user_id or "").strip()
        if normalized in self._env_admin_user_ids():
            raise ValueError("系统引导管理员不可通过界面移除（防止锁死超管）")
        remove_admin(self._bi_admins_path(), normalized, actor=actor, removed_at=at)
        return self.list_admin_user_ids()

    def list_admin_audit(self, limit: int = 200) -> list[dict[str, Any]]:
        audit = load_audit(self._bi_admins_path())
        return list(reversed(audit))[: max(1, min(int(limit), 1000))]

    def search_members_for_admin(self, *, q: str, limit: int = 10) -> list[dict[str, Any]]:
        """按手机号/姓名/user_id 模糊搜真实会员，供添加管理员选人（手机号脱敏）。"""
        query = str(q or "").strip().lower()
        members = self._load_member_directory_members_for_bi(self._load())
        results: list[dict[str, Any]] = []
        for member in members:
            if not isinstance(member, dict):
                continue
            uid = str(member.get("user_id") or "").strip()
            if not uid:
                continue
            name = str(member.get("display_name") or member.get("identifier") or "")
            phone = str(member.get("phone") or "")
            if query and query not in self._member_search_haystack(member):
                continue
            masked = (phone[:3] + "****" + phone[-4:]) if len(phone) >= 7 else phone
            results.append(
                {
                    "user_id": uid,
                    "display_name": name,
                    "phone_masked": masked,
                    "current_role": self.get_admin_role(uid),
                }
            )
            if len(results) >= limit:
                break
        return results

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
        claims = self._verify_access_token(token, verify_exp=False)
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
        if int(claims.get("exp") or 0) <= now:
            raise ValueError("Invalid or expired token")
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
    ) -> dict[str, Any]:
        # Round 4 S1: return the inserted entry so callers (e.g. record_conversation_view)
        # can capture audit_id without a second list scan, and so idempotency
        # dedup can store key → audit_id mapping.
        entry = {
            "id": f"audit_{uuid.uuid4().hex[:10]}",
            "operator": operator,
            "action": action,
            "target_user": target_user,
            "reason": reason,
            "before": before or {},
            "after": after or {},
            "created_at": _iso(),
        }
        data["audit_log"].insert(0, entry)
        return entry

    # Round 4 S1 + Round 5 B1/B2: idempotency index lives inside the same JSON
    # blob protected by `_mutate` (fcntl-locked). Key shape is
    # f"{action}:{operator}:{idempotency_key}" so two different actions can
    # reuse the same caller-generated UUID without colliding, and so a key
    # generated by Admin A cannot dedupe (i.e. silently suppress) Admin B's
    # request — operator binding closes the cross-actor replay surface
    # surfaced by Round 5 security review.
    #
    # The index is bounded by AUDIT_IDEMPOTENCY_INDEX_MAX (10k) with FIFO
    # eviction so an attacker with a valid admin token cannot DoS the JSON
    # store by sending unlimited unique keys. Python dicts preserve insertion
    # order since 3.7 so FIFO is `next(iter(...))`.
    def _composite_idempotency_key(
        self, action: str, operator: str, idempotency_key: str
    ) -> str:
        return f"{action}:{operator}:{idempotency_key}"

    def _find_audit_id_by_idempotency_key(
        self,
        data: dict[str, Any],
        action: str,
        idempotency_key: str,
        *,
        operator: str = "",
    ) -> str | None:
        if not idempotency_key:
            return None
        index = data.get("audit_idempotency_keys") or {}
        return index.get(self._composite_idempotency_key(action, operator, idempotency_key))

    def _remember_idempotency_key(
        self,
        data: dict[str, Any],
        action: str,
        idempotency_key: str,
        audit_id: str,
        *,
        operator: str = "",
    ) -> None:
        if not idempotency_key:
            return
        index = data.setdefault("audit_idempotency_keys", {})
        # FIFO evict when at cap. Dict iteration order = insertion order.
        while len(index) >= AUDIT_IDEMPOTENCY_INDEX_MAX:
            oldest = next(iter(index))
            index.pop(oldest, None)
        index[self._composite_idempotency_key(action, operator, idempotency_key)] = audit_id

    def _append_audit_log(self, entry: dict[str, Any]) -> dict[str, Any]:
        payload = dict(entry or {})

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            data.setdefault("audit_log", []).insert(0, payload)
            return payload

        return self._mutate(_apply)

    def _fallback_member_behavior_summary(self, *, trust_level: str = "C") -> dict[str, Any]:
        return {
            "learning_report_open_count_7d": 0,
            "history_open_count_7d": 0,
            "action_start_count_7d": 0,
            "event_count_7d": 0,
            "last_event_at_ms": 0,
            "cohort": "",
            "cohort_reasons": [],
            "next_action": "检查埋点状态",
            "trust_level": trust_level,
        }

    def _get_product_behavior_store(self):
        from deeptutor.services.observability import get_product_behavior_store

        return get_product_behavior_store()

    def _load_member_behavior_payload(self, user_id: str) -> dict[str, Any]:
        try:
            store = self._get_product_behavior_store()
            return {
                "summary": store.get_member_behavior_summary(user_id, days=7),
                "learning_report_sections": store.get_learning_report_section_breakdown(user_id, days=7),
                "timeline": store.get_member_timeline(user_id, days=7, limit=20),
            }
        except Exception:
            logger.warning("Failed to load product behavior for member: user_id=%s", user_id, exc_info=True)
            return {
                "summary": self._fallback_member_behavior_summary(),
                "learning_report_sections": [],
                "timeline": [],
            }

    @staticmethod
    def _member_behavior_identity_group(member: dict[str, Any]) -> list[str]:
        identities = [
            member.get("user_id"),
            member.get("canonical_user_id"),
            member.get("external_auth_user_id"),
            *list(member.get("alias_user_ids") or []),
        ]
        seen: set[str] = set()
        out: list[str] = []
        for value in identities:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out

    def _load_member_behavior_payload_for_member(self, member: dict[str, Any]) -> dict[str, Any]:
        user_id = str(member.get("user_id") or "").strip()
        identities = self._member_behavior_identity_group(member)
        try:
            store = self._get_product_behavior_store()
            summary_groups = getattr(store, "get_member_behavior_summaries_for_identity_groups", None)
            section_groups = getattr(store, "get_learning_report_section_breakdown_for_identity_group", None)
            timeline_groups = getattr(store, "get_member_timeline_for_identity_group", None)
            if callable(summary_groups) and callable(section_groups) and callable(timeline_groups):
                return {
                    "summary": summary_groups({user_id: identities}, days=7).get(
                        user_id,
                        self._fallback_member_behavior_summary(),
                    ),
                    "learning_report_sections": section_groups(identities, days=7),
                    "timeline": timeline_groups(identities, days=7, limit=20),
                }
            return self._load_member_behavior_payload(user_id)
        except Exception:
            logger.warning("Failed to load product behavior for member: user_id=%s", user_id, exc_info=True)
            return {
                "summary": self._fallback_member_behavior_summary(),
                "learning_report_sections": [],
                "timeline": [],
            }

    def _load_member_behavior_summaries_for_members(
        self,
        members: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        group_by_user_id = {
            str(item.get("user_id") or "").strip(): self._member_behavior_identity_group(item)
            for item in members
            if str(item.get("user_id") or "").strip()
        }
        try:
            store = self._get_product_behavior_store()
            grouped_loader = getattr(store, "get_member_behavior_summaries_for_identity_groups", None)
            if callable(grouped_loader):
                return grouped_loader(group_by_user_id, days=7)
            return self._load_member_behavior_summaries(list(group_by_user_id))
        except Exception:
            logger.warning("Failed to load product behavior summaries for member list", exc_info=True)
            return {
                user_id: self._fallback_member_behavior_summary()
                for user_id in group_by_user_id
            }

    def _load_member_behavior_summaries(self, user_ids: list[str]) -> dict[str, dict[str, Any]]:
        try:
            return self._get_product_behavior_store().get_member_behavior_summaries(user_ids, days=7)
        except Exception:
            logger.warning("Failed to load product behavior summaries for member list", exc_info=True)
            return {
                user_id: self._fallback_member_behavior_summary()
                for user_id in user_ids
            }

    @staticmethod
    def _filter_bi_operational_members(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            member
            for member in members
            if is_bi_operational_at(member.get("created_at"))
        ]

    def get_dashboard(self, days: int = 30) -> dict[str, Any]:
        data = self._load()
        members = self._filter_bi_operational_members(
            self._merge_session_activity_for_member_list(
                self._load_member_directory_members_for_bi(data)
            )
        )
        behavior_summaries = self._load_member_behavior_summaries_for_members(members)
        behavior_health = {
            "learning_report_open_count_7d": sum(
                int(summary.get("learning_report_open_count_7d") or 0)
                for summary in behavior_summaries.values()
            ),
            "history_open_count_7d": sum(
                int(summary.get("history_open_count_7d") or 0)
                for summary in behavior_summaries.values()
            ),
            "action_start_count_7d": sum(
                int(summary.get("action_start_count_7d") or 0)
                for summary in behavior_summaries.values()
            ),
            "event_count_7d": sum(
                int(summary.get("event_count_7d") or 0)
                for summary in behavior_summaries.values()
            ),
            "low_trust_count": sum(
                1
                for summary in behavior_summaries.values()
                if str(summary.get("trust_level") or "C") != "A"
            ),
        }
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
            if _is_created_within_days(item.get("created_at"), now=now, days=1)
        )
        new_7d_count = sum(
            1
            for item in members
            if _is_created_within_days(item.get("created_at"), now=now, days=7)
        )
        new_30d_count = sum(
            1
            for item in members
            if _is_created_within_days(item.get("created_at"), now=now, days=30)
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
            "new_7d_count": new_7d_count,
            "new_30d_count": new_30d_count,
            "churn_risk_count": churn_risk_count,
            "health_score": round((active_count / max(len(members), 1)) * 100),
            "auto_renew_coverage": round((auto_renew_count / max(len(members), 1)) * 100),
            "authority": {
                "members": self._member_directory_authority(),
                "member_overlay": "member_console",
                "behavior": "product_behavior_events",
                "operational_start_at": BI_OPERATION_START_AT.isoformat(),
            },
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
            "behavior_health": behavior_health,
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
        search_text = str(search or "").strip().lower()
        members = self._merge_session_activity_for_member_list(
            self._load_member_directory_members_for_bi(
                data,
                include_session_activity_supplements=True,
            )
        )
        if not search_text:
            members = self._filter_bi_operational_members(members)
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
            if (not status or status == "all") and str(item.get("status") or "") == "deleted":
                continue
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
                haystack = self._member_search_haystack(item)
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
        page_items = filtered[start:end]
        behavior_summaries = self._load_member_behavior_summaries_for_members(page_items)
        items = []
        for item in page_items:
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
                    "behavior": behavior_summaries.get(
                        item["user_id"],
                        self._fallback_member_behavior_summary(),
                    ),
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
            "authority": {
                "members": self._member_directory_authority(),
                "member_overlay": "member_console",
                "behavior": "product_behavior_events",
                "operational_start_at": BI_OPERATION_START_AT.isoformat(),
            },
        }

    @staticmethod
    def _member_search_haystack(member: dict[str, Any]) -> str:
        """Canonical member search terms shared by BI tables and admin picker.

        Operators search by what they actually see or receive from students:
        phone, account/login name, canonical uid, legacy user_id, and alias ids.
        Keeping the haystack in one service helper avoids one UI saying "账号"
        while another backend path only searches display name.
        """
        values: list[str] = []
        for key in (
            "user_id",
            "canonical_user_id",
            "canonical_uid",
            "external_auth_user_id",
            "auth_username",
            "display_name",
            "identifier",
            "phone",
            "wx_openid",
            "openid",
            "wx_unionid",
            "unionid",
        ):
            value = str(member.get(key) or "").strip()
            if value:
                values.append(value)
                if key == "phone":
                    digits = re.sub(r"\D+", "", value)
                    if digits:
                        values.append(digits)
        for value in list(member.get("alias_user_ids") or []):
            normalized = str(value or "").strip()
            if normalized:
                values.append(normalized)
        for value in list(member.get("search_aliases") or []):
            normalized = str(value or "").strip()
            if normalized:
                values.append(normalized)
        return " ".join(values).lower()

    def list_members_for_bi(self) -> list[dict[str, Any]]:
        data = self._load()
        return deepcopy(
            self._filter_bi_operational_members(
                self._load_member_directory_members_for_bi(
                    data,
                    include_session_activity_supplements=True,
                )
            )
        )

    def get_member_360(self, user_id: str) -> dict[str, Any]:
        data = self._load()
        try:
            member = deepcopy(self._find_member(data, user_id))
        except KeyError:
            member = None
            for item in self._merge_session_activity_for_member_list(
                self._load_member_directory_members_for_bi(
                    data,
                    include_session_activity_supplements=True,
                )
            ):
                if str(item.get("user_id") or "").strip() == user_id or user_id in set(item.get("alias_user_ids") or []):
                    member = deepcopy(item)
                    break
            if member is None:
                raise
        member = self._merge_session_activity_for_member_list([member])[0]
        member.setdefault("ledger", [])
        member.setdefault("notes", [])
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
        member["behavior"] = self._load_member_behavior_payload_for_member(member)
        member["membership_billing"] = {
            "reversible_supreme_purchase": self._latest_reversible_manual_membership_purchase(
                data,
                user_id=str(member.get("user_id") or user_id).strip(),
            )
        }
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
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"open", "in_progress", "done", "follow_up"}:
            raise ValueError("Unsupported ops action status")
        normalized_result = str(result or "").strip()
        if not normalized_result:
            raise ValueError("Ops action result is required")
        normalized_title = str(action_title or "").strip() or "会员运营处理"
        normalized_follow_up = str(next_follow_up_at or "").strip()
        normalized_key = str(idempotency_key or "").strip()

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            member = self._find_member(data, user_id)
            if normalized_key:
                existing_audit_id = self._find_audit_id_by_idempotency_key(
                    data,
                    "ops_action_result",
                    normalized_key,
                    operator=operator,
                )
                if existing_audit_id is not None:
                    return {
                        "status": normalized_status,
                        "result": normalized_result,
                        "action_title": normalized_title,
                        "next_follow_up_at": normalized_follow_up,
                        "note_id": "",
                        "audit_id": existing_audit_id,
                        "deduped": True,
                        "note": None,
                    }
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
            entry = self._append_audit(
                data,
                action="ops_action_result",
                target_user=user_id,
                reason=normalized_status,
                after=action_result,
                operator=operator,
            )
            if normalized_key:
                self._remember_idempotency_key(
                    data,
                    "ops_action_result",
                    normalized_key,
                    entry["id"],
                    operator=operator,
                )
            return {
                **action_result,
                "note": note,
                "audit_id": entry["id"],
                "deduped": False,
            }

        return self._mutate(_apply)

    # Plan §3.5 / §6 require every full-text conversation view to capture WHY
    # the admin opened it. Round 3 G accepts a `reason` from the caller and
    # writes it into the audit_log so the entry is auditable in the absence of
    # frontend cooperation. The frontend is also expected to enforce a 6-item
    # whitelist + free-form "other" with ≥ 4 chars, but the server-side
    # whitelist below is the authoritative gate.
    _VIEW_REASON_WHITELIST: tuple[str, ...] = (
        "complaint",
        "ops",
        "teaching",
        "engineering",
        "finance",
    )

    def record_conversation_view(
        self,
        user_id: str,
        session_id: str,
        *,
        operator: str = "admin",
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            raise ValueError("Conversation session_id is required")

        # Validate the reason; reject malformed input but keep payload
        # backward-compatible (existing callers without reason fall back to the
        # generic "view_full_conversation").
        normalized_reason = (reason or "").strip()
        if normalized_reason:
            if normalized_reason in self._VIEW_REASON_WHITELIST:
                audit_reason = normalized_reason
            elif normalized_reason.startswith("other:") and len(normalized_reason) - len("other:") >= 4:
                # Trim to a sane length so audit_log cells stay readable.
                audit_reason = normalized_reason[: 6 + 80]
            else:
                raise ValueError(
                    "reason must be one of "
                    f"{self._VIEW_REASON_WHITELIST} or 'other:<note>' with ≥ 4 chars"
                )
        else:
            audit_reason = "view_full_conversation"

        normalized_key = (idempotency_key or "").strip()

        # Round 5 M3 (TOCTOU close): conversation lookup + audit_payload
        # construction now happen INSIDE `_apply`, under the same _mutate
        # fcntl lock that protects audit_log + idempotency index writes. The
        # previous outer `_load()` pattern allowed a second worker to enter
        # `_apply` based on a stale view of the conversations list, even when
        # the dedup index would have suppressed the duplicate write — the
        # observable behaviour was OK but the pattern was fragile under
        # gunicorn multi-worker on /root/deeptutor.
        def _apply(next_data: dict[str, Any]) -> dict[str, Any]:
            member = self._find_member(next_data, user_id)
            conversations = self._load_recent_conversations_for_member(
                member,
                user_id,
                session_limit=20,
                include_messages=True,
            )
            conversation = next(
                (
                    item
                    for item in conversations
                    if str(item.get("session_id") or "") == normalized_session_id
                ),
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
                "reason": audit_reason,
            }

            # Round 4 S1: dedup check inside the same _mutate envelope that
            # serializes all writes — guarantees concurrent retries with the
            # same key cannot both insert. If we've seen this key on the same
            # action before, surface the original audit_id and return a
            # `deduped: true` response so callers can distinguish.
            if normalized_key:
                existing_audit_id = self._find_audit_id_by_idempotency_key(
                    next_data,
                    "conversation_view",
                    normalized_key,
                    operator=operator,
                )
                if existing_audit_id is not None:
                    deduped_payload = dict(audit_payload)
                    deduped_payload["audit_id"] = existing_audit_id
                    deduped_payload["deduped"] = True
                    deduped_payload["messages"] = list(conversation.get("messages") or [])
                    return deduped_payload

            entry = self._append_audit(
                next_data,
                action="conversation_view",
                target_user=user_id,
                reason=audit_reason,
                after=audit_payload,
                operator=operator,
            )
            if normalized_key:
                self._remember_idempotency_key(
                    next_data,
                    "conversation_view",
                    normalized_key,
                    entry["id"],
                    operator=operator,
                )
            result = dict(audit_payload)
            result["audit_id"] = entry["id"]
            result["messages"] = list(conversation.get("messages") or [])
            return result

        return self._mutate(_apply)

    def record_bi_audit(
        self,
        *,
        action: str,
        target_user: str,
        operator: str = "admin",
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        normalized_action = str(action or "").strip()
        normalized_target = str(target_user or "").strip()
        if not normalized_action:
            raise ValueError("action is required")
        if not normalized_target:
            raise ValueError("target_user is required")
        normalized_operator = str(operator or "").strip() or "admin"
        normalized_key = str(idempotency_key or "").strip()

        def _apply(next_data: dict[str, Any]) -> dict[str, Any]:
            if normalized_key:
                existing_audit_id = self._find_audit_id_by_idempotency_key(
                    next_data,
                    normalized_action,
                    normalized_key,
                    operator=normalized_operator,
                )
                if existing_audit_id is not None:
                    return {"audit_id": existing_audit_id, "deduped": True}

            entry = self._append_audit(
                next_data,
                action=normalized_action,
                target_user=normalized_target,
                operator=normalized_operator,
                reason=str(reason or "").strip()[:120],
                before=before,
                after=after,
            )
            if normalized_key:
                self._remember_idempotency_key(
                    next_data,
                    normalized_action,
                    normalized_key,
                    entry["id"],
                    operator=normalized_operator,
                )
            return {"audit_id": entry["id"], "deduped": False}

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

    def list_membership_packages(self) -> list[dict[str, Any]]:
        return deepcopy(self._load().get("packages") or self._default_packages())

    def upsert_membership_package(
        self,
        *,
        package_id: str,
        label: str,
        tier: str,
        points: int,
        turns: int = 0,
        price: str,
        original_price: str = "",
        badge: str = "",
        per: str = "",
        desc: str = "",
        status: str = "active",
        operator: str = "admin",
        reason: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        normalized_operator = str(operator or "").strip() or "admin"
        normalized_key = str(idempotency_key or "").strip()
        draft = self._normalize_membership_package(
            {
                "id": package_id,
                "label": label,
                "tier": tier,
                "points": points,
                "turns": turns,
                "price": price,
                "original_price": original_price,
                "badge": badge,
                "per": per,
                "desc": desc,
                "status": status,
            }
        )
        if not re.fullmatch(r"[A-Za-z0-9_:-]{1,80}", draft["id"]):
            raise ValueError("package_id must be 1-80 chars of [a-zA-Z0-9_:-]")
        if draft["points"] <= 0:
            raise ValueError("package points must be positive")
        if draft["turns"] <= 0:
            raise ValueError("package turns must be positive")
        amount = self._package_amount_cny(draft)
        draft["price"] = str(int(amount) if float(amount).is_integer() else amount)

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            if self._find_audit_id_by_idempotency_key(
                data,
                "membership_package_upsert",
                normalized_key,
                operator=normalized_operator,
            ):
                for existing in data.get("packages") or []:
                    if str(existing.get("id") or "").strip() == draft["id"]:
                        return deepcopy(existing)
            packages = data.setdefault("packages", self._default_packages())
            index = next(
                (idx for idx, item in enumerate(packages) if str(item.get("id") or "").strip() == draft["id"]),
                None,
            )
            before = deepcopy(packages[index]) if index is not None else {}
            if index is None:
                packages.append(deepcopy(draft))
            else:
                packages[index] = deepcopy(draft)
            audit = self._append_audit(
                data,
                action="membership_package_upsert",
                target_user=draft["id"],
                reason=reason or "membership_package_upsert",
                before=before,
                after=draft,
                operator=normalized_operator,
            )
            self._remember_idempotency_key(
                data,
                "membership_package_upsert",
                normalized_key,
                audit["id"],
                operator=normalized_operator,
            )
            return deepcopy(draft)

        return self._mutate(_apply)

    def remove_membership_package(
        self,
        package_id: str,
        *,
        operator: str = "admin",
        reason: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        normalized_package_id = str(package_id or "").strip()
        normalized_operator = str(operator or "").strip() or "admin"
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_package_id:
            raise ValueError("package_id is required")

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            existing_audit_id = self._find_audit_id_by_idempotency_key(
                data,
                "membership_package_delete",
                normalized_key,
                operator=normalized_operator,
            )
            packages = data.setdefault("packages", self._default_packages())
            index = next(
                (idx for idx, item in enumerate(packages) if str(item.get("id") or "").strip() == normalized_package_id),
                None,
            )
            if existing_audit_id:
                if index is None:
                    return {"id": normalized_package_id}
                return deepcopy(packages[index])
            if index is None:
                raise ValueError(f"Unknown membership package: {normalized_package_id}")
            removed = deepcopy(packages.pop(index))
            audit = self._append_audit(
                data,
                action="membership_package_delete",
                target_user=normalized_package_id,
                reason=reason or "membership_package_delete",
                before=removed,
                after={},
                operator=normalized_operator,
            )
            self._remember_idempotency_key(
                data,
                "membership_package_delete",
                normalized_key,
                audit["id"],
                operator=normalized_operator,
            )
            return removed

        return self._mutate(_apply)

    def _resolve_membership_package(
        self,
        data: dict[str, Any],
        package_id: str,
    ) -> dict[str, Any]:
        normalized_package_id = str(package_id or "").strip()
        if not normalized_package_id:
            raise ValueError("package_id is required")
        for item in list(data.get("packages") or self._default_packages()):
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "").strip() == normalized_package_id:
                if str(item.get("status") or "active").strip() != "active":
                    raise ValueError(f"Membership package is not active: {normalized_package_id}")
                return dict(item)
        raise ValueError(f"Unknown membership package: {normalized_package_id}")

    @staticmethod
    def _package_amount_cny(package: dict[str, Any], override: float | int | str | None = None) -> float:
        value = override if override is not None else package.get("price_cny", package.get("price", 0))
        try:
            amount = float(value or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount < 0:
            raise ValueError("amount_cny must be non-negative")
        return int(amount) if amount.is_integer() else amount

    def manual_membership_purchase(
        self,
        *,
        user_id: str,
        package_id: str,
        days: int,
        operator: str = "admin",
        reason: str = "",
        idempotency_key: str,
        phone: str = "",
        display_name: str = "",
        amount_cny: float | int | str | None = None,
    ) -> dict[str, Any]:
        normalized_user_id = str(user_id or "").strip()
        normalized_operator = str(operator or "").strip() or "admin"
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id is required")
        if not normalized_key:
            raise ValueError("idempotency_key is required")
        safe_days = max(1, min(int(days or 0), 3650))

        def _load_purchase_inputs(data: dict[str, Any]) -> dict[str, Any]:
            existing_audit_id = self._find_audit_id_by_idempotency_key(
                data,
                "manual_membership_purchase",
                normalized_key,
                operator=normalized_operator,
            )
            member = self._ensure_member(data, normalized_user_id)
            package = self._resolve_membership_package(data, package_id)
            if existing_audit_id is not None:
                return {
                    "deduped": True,
                    "audit_id": existing_audit_id,
                    "member": deepcopy(member),
                    "package": package,
                }
            return {
                "deduped": False,
                "member": deepcopy(member),
                "package": package,
            }

        purchase_inputs = self._mutate(_load_purchase_inputs)
        package = dict(purchase_inputs["package"])
        if purchase_inputs.get("deduped"):
            return {
                "member": purchase_inputs["member"],
                "package": package,
                "amount_cny": self._package_amount_cny(package, amount_cny),
                "points": int(package.get("points") or 0),
                "purchase_id": "",
                "ledger_event_id": "",
                "audit_id": purchase_inputs.get("audit_id", ""),
                "deduped": True,
            }

        points = max(0, int(package.get("points") or 0))
        if points <= 0:
            raise ValueError("package points must be positive")
        amount = self._package_amount_cny(package, amount_cny)
        package_tier = str(package.get("tier") or package.get("id") or "").strip()
        package_label = str(package.get("label") or package.get("name") or package.get("id") or "").strip()
        purchase_id = f"manual_membership_{uuid.uuid4().hex[:12]}"

        if phone or display_name:
            def _persist_manual_identity(data: dict[str, Any]) -> None:
                member = self._ensure_member(data, normalized_user_id)
                if phone:
                    member["phone"] = _normalize_phone_input(phone) or str(phone).strip()
                if display_name:
                    member["display_name"] = str(display_name).strip()

            self._mutate(_persist_manual_identity)
        wallet_identity = self._auth_identity_for_member(normalized_user_id)
        wallet_user_id = str(wallet_identity.get("canonical_uid") or normalized_user_id).strip()

        wallet_service = self._get_wallet_service()
        if not getattr(wallet_service, "is_configured", False):
            raise RuntimeError("wallet_service_not_configured")
        if hasattr(wallet_service, "ensure_wallet_seeded"):
            wallet_service.ensure_wallet_seeded(
                user_id=wallet_user_id,
                opening_points=0,
                plan_id=package_tier,
                reference_type="manual_membership_purchase",
                reference_id=purchase_id,
                idempotency_key=f"wallet_seed:manual_membership:{normalized_key}",
                metadata={
                    "source": "bi_manual_membership",
                    "operator_id": normalized_operator,
                    "legacy_user_id": normalized_user_id,
                    "wallet_user_id": wallet_user_id,
                },
            )
        metadata = {
            "source": "bi_manual_membership",
            "channel": "manual_membership",
            "package_id": str(package.get("id") or "").strip(),
            "package_label": package_label,
            "tier": package_tier,
            "amount_cny": amount,
            "operator_id": normalized_operator,
            "legacy_user_id": normalized_user_id,
            "wallet_user_id": wallet_user_id,
            "days": safe_days,
            "reason": str(reason or "").strip(),
        }
        mutation = wallet_service.grant_points(
            user_id=wallet_user_id,
            amount_micros=points * 1_000_000,
            reference_type="purchase",
            reference_id=purchase_id,
            idempotency_key=f"purchase:manual_membership:{normalized_key}",
            reason="manual_membership_purchase",
            metadata=metadata,
            operator_type="admin",
            operator_id=normalized_operator,
        )
        ledger_event_id = str(getattr(mutation, "ledger_event_id", "") or "")
        created_at = str(getattr(mutation, "created_at", "") or _iso())

        def _apply_entitlement(data: dict[str, Any]) -> dict[str, Any]:
            existing_audit_id = self._find_audit_id_by_idempotency_key(
                data,
                "manual_membership_purchase",
                normalized_key,
                operator=normalized_operator,
            )
            member = self._ensure_member(data, normalized_user_id)
            if existing_audit_id is not None:
                return {
                    "member": deepcopy(member),
                    "audit_id": existing_audit_id,
                    "deduped": True,
                }
            before = deepcopy(member)
            if phone:
                member["phone"] = _normalize_phone_input(phone) or str(phone).strip()
            if display_name:
                member["display_name"] = str(display_name).strip()
            base = max(_parse_time(member.get("expire_at")), _now())
            member["tier"] = package_tier
            member["status"] = "active"
            member["expire_at"] = _iso(base + timedelta(days=safe_days))
            member["points_balance"] = int(member.get("points_balance") or 0) + points
            ledger_entry = {
                "id": ledger_event_id or purchase_id,
                "delta": points,
                "reason": "manual_membership_purchase",
                "created_at": created_at,
                "metadata": metadata,
            }
            member.setdefault("ledger", []).insert(0, ledger_entry)
            after = deepcopy(member)
            audit = self._append_audit(
                data,
                action="manual_membership_purchase",
                target_user=normalized_user_id,
                reason=str(reason or "").strip() or "manual_membership_purchase",
                before=before,
                after={
                    "member": after,
                    "package_id": str(package.get("id") or "").strip(),
                    "purchase_id": purchase_id,
                    "ledger_event_id": ledger_event_id,
                    "amount_cny": amount,
                    "points": points,
                    "days": safe_days,
                },
                operator=normalized_operator,
            )
            self._remember_idempotency_key(
                data,
                "manual_membership_purchase",
                normalized_key,
                audit["id"],
                operator=normalized_operator,
            )
            return {
                "member": after,
                "audit_id": audit["id"],
                "deduped": False,
            }

        entitlement = self._mutate(_apply_entitlement)
        return {
            "member": entitlement["member"],
            "package": package,
            "amount_cny": amount,
            "points": points,
            "purchase_id": purchase_id,
            "ledger_event_id": ledger_event_id,
            "audit_id": entitlement.get("audit_id", ""),
            "deduped": bool(entitlement.get("deduped", False)),
        }

    def _find_latest_manual_membership_purchase_audit(
        self,
        data: dict[str, Any],
        *,
        user_id: str,
        purchase_id: str = "",
    ) -> dict[str, Any] | None:
        normalized_purchase_id = str(purchase_id or "").strip()
        candidates = []
        for item in data.get("audit_log") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("action") or "") != "manual_membership_purchase":
                continue
            if str(item.get("target_user") or "").strip() != user_id:
                continue
            after = item.get("after") if isinstance(item.get("after"), dict) else {}
            candidate_purchase_id = str(after.get("purchase_id") or "").strip()
            if normalized_purchase_id and candidate_purchase_id != normalized_purchase_id:
                continue
            candidates.append(item)
        if not candidates:
            return None
        return max(candidates, key=lambda item: _parse_time(item.get("created_at")))

    def _has_manual_membership_reversal(
        self,
        data: dict[str, Any],
        *,
        user_id: str,
        purchase_id: str,
    ) -> bool:
        normalized_purchase_id = str(purchase_id or "").strip()
        for item in data.get("audit_log") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("action") or "") != "manual_membership_reversal":
                continue
            if str(item.get("target_user") or "").strip() != user_id:
                continue
            after = item.get("after") if isinstance(item.get("after"), dict) else {}
            if str(after.get("reversal_of_purchase_id") or "").strip() == normalized_purchase_id:
                return True
        return False

    def _latest_reversible_manual_membership_purchase(
        self,
        data: dict[str, Any],
        *,
        user_id: str,
    ) -> dict[str, Any] | None:
        audit = self._find_latest_manual_membership_purchase_audit(data, user_id=user_id)
        if audit is None:
            return None
        after = audit.get("after") if isinstance(audit.get("after"), dict) else {}
        purchase_id = str(after.get("purchase_id") or "").strip()
        if not purchase_id or str(after.get("package_id") or "").strip() != "supreme_svip":
            return None
        if self._has_manual_membership_reversal(data, user_id=user_id, purchase_id=purchase_id):
            return None
        return {
            "purchase_id": purchase_id,
            "package_id": "supreme_svip",
            "amount_cny": self._package_amount_cny({"price": after.get("amount_cny", 0)}),
            "points": int(after.get("points") or 0),
            "days": int(after.get("days") or 0),
            "created_at": str(audit.get("created_at") or ""),
            "ledger_event_id": str(after.get("ledger_event_id") or ""),
            "audit_id": str(audit.get("id") or ""),
        }

    def reverse_manual_membership_purchase(
        self,
        *,
        user_id: str,
        purchase_id: str = "",
        amount_cny: float | int | str | None = None,
        operator: str = "admin",
        reason: str = "",
        idempotency_key: str,
    ) -> dict[str, Any]:
        normalized_user_id = str(user_id or "").strip()
        normalized_operator = str(operator or "").strip() or "admin"
        normalized_key = str(idempotency_key or "").strip()
        normalized_purchase_id = str(purchase_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id is required")
        if not normalized_purchase_id:
            raise ValueError("purchase_id is required for manual membership reversal")
        if not normalized_key:
            raise ValueError("idempotency_key is required")

        def _load_reversal_inputs(data: dict[str, Any]) -> dict[str, Any]:
            existing_audit_id = self._find_audit_id_by_idempotency_key(
                data,
                "manual_membership_reversal",
                normalized_key,
                operator=normalized_operator,
            )
            member = self._find_member(data, normalized_user_id)
            purchase_audit = self._find_latest_manual_membership_purchase_audit(
                data,
                user_id=normalized_user_id,
                purchase_id=normalized_purchase_id,
            )
            if purchase_audit is None:
                raise ValueError("manual membership purchase was not found")
            purchase_after = purchase_audit.get("after") if isinstance(purchase_audit.get("after"), dict) else {}
            resolved_purchase_id = str(purchase_after.get("purchase_id") or "").strip()
            if not resolved_purchase_id:
                raise ValueError("manual membership purchase has no purchase_id")
            if existing_audit_id is not None:
                return {
                    "deduped": True,
                    "audit_id": existing_audit_id,
                    "member": deepcopy(member),
                    "purchase_after": dict(purchase_after),
                }
            if self._has_manual_membership_reversal(
                data,
                user_id=normalized_user_id,
                purchase_id=resolved_purchase_id,
            ):
                raise ValueError("manual membership purchase was already reversed")
            return {
                "deduped": False,
                "member": deepcopy(member),
                "purchase_after": dict(purchase_after),
            }

        reversal_inputs = self._mutate(_load_reversal_inputs)
        purchase_after = dict(reversal_inputs["purchase_after"])
        resolved_purchase_id = str(purchase_after.get("purchase_id") or normalized_purchase_id or "").strip()
        package_id = str(purchase_after.get("package_id") or "").strip()
        if package_id != "supreme_svip":
            raise ValueError("Only supreme_svip manual membership purchases can be reversed")
        if reversal_inputs.get("deduped"):
            original_amount = self._package_amount_cny({"price": purchase_after.get("amount_cny", 0)})
            return {
                "member": reversal_inputs["member"],
                "amount_cny": -abs(original_amount),
                "points": -abs(int(purchase_after.get("points") or 0)),
                "purchase_id": resolved_purchase_id,
                "ledger_event_id": "",
                "audit_id": reversal_inputs.get("audit_id", ""),
                "deduped": True,
            }

        package = {
            "id": package_id,
            "label": "至尊SVIP",
            "points": purchase_after.get("points", 0),
            "price": purchase_after.get("amount_cny", 0),
        }
        for item in [*(self._load().get("packages") or []), *self._default_packages()]:
            if isinstance(item, dict) and str(item.get("id") or "").strip() == package_id:
                package = dict(item)
                break
        package_label = str(package.get("label") or package.get("name") or package_id).strip()
        points = abs(int(purchase_after.get("points") or package.get("points") or 0))
        if points <= 0:
            raise ValueError("reversal points must be positive")
        # The original purchase audit is the only amount authority. Legacy
        # callers may still send amount_cny, but it must not alter reconciliation.
        original_amount = self._package_amount_cny({"price": purchase_after.get("amount_cny", 0)})
        if original_amount <= 0:
            raise ValueError("reversal amount_cny must be positive")
        reversal_amount = -abs(original_amount)
        wallet_identity = self._auth_identity_for_member(normalized_user_id)
        wallet_user_id = str(wallet_identity.get("canonical_uid") or normalized_user_id).strip()
        wallet_service = self._get_wallet_service()
        if not getattr(wallet_service, "is_configured", False):
            raise RuntimeError("wallet_service_not_configured")
        refund_points = getattr(wallet_service, "refund_points", None)
        if not callable(refund_points):
            raise RuntimeError("wallet_refund_not_supported")
        days = int(purchase_after.get("days") or 0)
        metadata = {
            "source": "bi_manual_membership_reversal",
            "channel": "manual_membership_reversal",
            "package_id": package_id,
            "package_label": package_label,
            "tier": "supreme_svip",
            "amount_cny": reversal_amount,
            "operator_id": normalized_operator,
            "legacy_user_id": normalized_user_id,
            "wallet_user_id": wallet_user_id,
            "days": days,
            "reason": str(reason or "").strip(),
            "reversal_of_purchase_id": resolved_purchase_id,
        }
        mutation = refund_points(
            user_id=wallet_user_id,
            amount_micros=points * 1_000_000,
            reference_type="refund",
            reference_id=resolved_purchase_id,
            idempotency_key=f"refund:manual_membership:{normalized_key}",
            reason="manual_membership_reversal",
            metadata=metadata,
            operator_type="admin",
            operator_id=normalized_operator,
        )
        ledger_event_id = str(getattr(mutation, "ledger_event_id", "") or "")
        created_at = str(getattr(mutation, "created_at", "") or _iso())

        def _apply_reversal(data: dict[str, Any]) -> dict[str, Any]:
            existing_audit_id = self._find_audit_id_by_idempotency_key(
                data,
                "manual_membership_reversal",
                normalized_key,
                operator=normalized_operator,
            )
            member = self._find_member(data, normalized_user_id)
            if existing_audit_id is not None:
                return {
                    "member": deepcopy(member),
                    "audit_id": existing_audit_id,
                    "deduped": True,
                }
            if self._has_manual_membership_reversal(
                data,
                user_id=normalized_user_id,
                purchase_id=resolved_purchase_id,
            ):
                raise ValueError("manual membership purchase was already reversed")
            before = deepcopy(member)
            member["status"] = "revoked"
            member["auto_renew"] = False
            member["expire_at"] = _iso(_now())
            member["points_balance"] = max(0, int(member.get("points_balance") or 0) - points)
            ledger_entry = {
                "id": ledger_event_id or f"reversal_{resolved_purchase_id}",
                "delta": -points,
                "reason": "manual_membership_reversal",
                "created_at": created_at,
                "metadata": metadata,
            }
            member.setdefault("ledger", []).insert(0, ledger_entry)
            after = deepcopy(member)
            audit = self._append_audit(
                data,
                action="manual_membership_reversal",
                target_user=normalized_user_id,
                reason=str(reason or "").strip() or "manual_membership_reversal",
                before=before,
                after={
                    "member": after,
                    "package_id": package_id,
                    "reversal_of_purchase_id": resolved_purchase_id,
                    "ledger_event_id": ledger_event_id,
                    "amount_cny": reversal_amount,
                    "points": -points,
                },
                operator=normalized_operator,
            )
            self._remember_idempotency_key(
                data,
                "manual_membership_reversal",
                normalized_key,
                audit["id"],
                operator=normalized_operator,
            )
            return {
                "member": after,
                "audit_id": audit["id"],
                "deduped": False,
            }

        entitlement = self._mutate(_apply_reversal)
        return {
            "member": entitlement["member"],
            "amount_cny": reversal_amount,
            "points": -points,
            "purchase_id": resolved_purchase_id,
            "ledger_event_id": ledger_event_id,
            "audit_id": entitlement.get("audit_id", ""),
            "deduped": bool(entitlement.get("deduped", False)),
        }

    @staticmethod
    def _membership_tier_rank(tier: Any) -> int:
        return _MEMBERSHIP_TIER_RANK.get(str(tier or "").strip(), 0)

    @staticmethod
    def _later_iso(left: Any, right: Any) -> str:
        left_ts = _parse_time(left)
        right_ts = _parse_time(right)
        return _iso(left_ts if left_ts >= right_ts else right_ts)

    @staticmethod
    def _admin_role_rank(role: str | None) -> int:
        return _ADMIN_ROLE_RANK.get(str(role or "").strip(), -1)

    def _best_admin_role_for_merge(self, user_ids: list[str]) -> str | None:
        best_role: str | None = None
        for user_id in user_ids:
            role = self.get_admin_role(user_id)
            if self._admin_role_rank(role) > self._admin_role_rank(best_role):
                best_role = role
        return best_role

    def _apply_merged_admin_role(
        self,
        *,
        target_user_id: str,
        merged_user_ids: list[str],
        operator: str,
        display_name: str = "",
    ) -> str | None:
        best_role = self._best_admin_role_for_merge(merged_user_ids)
        if not best_role:
            return None
        if target_user_id in self._env_admin_user_ids():
            return self.get_admin_role(target_user_id)
        current_role = self.get_admin_role(target_user_id)
        if self._admin_role_rank(best_role) <= self._admin_role_rank(current_role):
            return current_role
        set_admin(
            self._bi_admins_path(),
            target_user_id,
            role=best_role,
            display_name=display_name,
            actor=operator,
            granted_at=_iso(),
        )
        return best_role

    def _wallet_balance_micros_for_merge(self, wallet_service: Any, user_id: str) -> int:
        get_wallet = getattr(wallet_service, "get_wallet", None)
        if not callable(get_wallet):
            return 0
        snapshot = get_wallet(user_id)
        return max(0, int(getattr(snapshot, "balance_micros", 0) or 0)) if snapshot is not None else 0

    def _apply_wallet_account_merge(
        self,
        *,
        target_user_id: str,
        source_user_ids: list[str],
        operator: str,
        reason: str,
        idempotency_key: str,
    ) -> list[dict[str, Any]]:
        wallet_service = self._get_wallet_service()
        if not getattr(wallet_service, "is_configured", False):
            return []
        admin_adjust_points = getattr(wallet_service, "admin_adjust_points", None)
        if not callable(admin_adjust_points):
            return []
        adjustments: list[dict[str, Any]] = []
        for source_user_id in source_user_ids:
            source_balance_micros = self._wallet_balance_micros_for_merge(wallet_service, source_user_id)
            if source_balance_micros <= 0:
                continue
            reference_id = f"{target_user_id}:{source_user_id}"
            metadata = {
                "source": "member_identity_merge",
                "target_user_id": target_user_id,
                "source_user_id": source_user_id,
                "operator_id": operator,
                "reason": reason,
            }
            credit = admin_adjust_points(
                user_id=target_user_id,
                delta_micros=source_balance_micros,
                reference_id=reference_id,
                idempotency_key=f"member_identity_merge:{idempotency_key}:{source_user_id}:credit",
                reason="member_identity_merge",
                metadata=metadata,
                operator_type="admin",
                operator_id=operator,
            )
            debit = admin_adjust_points(
                user_id=source_user_id,
                delta_micros=-source_balance_micros,
                reference_id=reference_id,
                idempotency_key=f"member_identity_merge:{idempotency_key}:{source_user_id}:debit",
                reason="member_identity_merge",
                metadata=metadata,
                operator_type="admin",
                operator_id=operator,
            )
            adjustments.append(
                {
                    "source_user_id": source_user_id,
                    "target_user_id": target_user_id,
                    "points_transferred": int(source_balance_micros / 1_000_000),
                    "credit_ledger_event_id": str(getattr(credit, "ledger_event_id", "") or ""),
                    "debit_ledger_event_id": str(getattr(debit, "ledger_event_id", "") or ""),
                }
            )
        return adjustments

    def _merge_member_accounts_locked(
        self,
        data: dict[str, Any],
        *,
        target_user_id: str,
        source_user_ids: list[str],
        operator: str,
        reason: str,
        action: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        existing_audit_id = self._find_audit_id_by_idempotency_key(
            data,
            action,
            idempotency_key,
            operator=operator,
        )
        target = self._find_member(data, target_user_id)
        if existing_audit_id is not None:
            return {
                "member": deepcopy(self._ensure_member(data, str(target.get("user_id") or target_user_id))),
                "audit_id": existing_audit_id,
                "deduped": True,
                "merged_source_ids": [],
                "points_transferred": 0,
                "admin_role_after": self.get_admin_role(target_user_id),
                "target_user_id": str(target.get("user_id") or target_user_id),
            }

        target = self._ensure_member(data, target_user_id)
        canonical_target_id = str(target.get("user_id") or target_user_id).strip()
        before = deepcopy(target)
        points_transferred = 0
        merged_source_ids: list[str] = []
        source_before: dict[str, Any] = {}
        now = _iso()

        for raw_source_id in source_user_ids:
            source_id = str(raw_source_id or "").strip()
            if not source_id or source_id == canonical_target_id or source_id in merged_source_ids:
                continue
            source = self._find_member(data, source_id)
            source_before[source_id] = deepcopy(source)
            resolved_source = self._ensure_member(data, source_id)
            if str(resolved_source.get("user_id") or "").strip() == canonical_target_id:
                source["merged_into"] = canonical_target_id
                source["merged_at"] = source.get("merged_at") or now
                merged_source_ids.append(source_id)
                continue

            source = resolved_source
            source_id = str(source.get("user_id") or source_id).strip()
            if not source_id or source_id == canonical_target_id or source_id in merged_source_ids:
                continue
            source_before[source_id] = deepcopy(source)

            source_tier = str(source.get("tier") or "").strip()
            target_tier = str(target.get("tier") or "").strip()
            if self._membership_tier_rank(source_tier) > self._membership_tier_rank(target_tier):
                target["tier"] = source_tier
            target["expire_at"] = self._later_iso(target.get("expire_at"), source.get("expire_at"))
            target["last_active_at"] = self._later_iso(target.get("last_active_at"), source.get("last_active_at"))
            if str(source.get("status") or "").strip() == "active" or _parse_time(target.get("expire_at")) > _now():
                target["status"] = "active"

            source_points = max(0, int(source.get("points_balance") or 0))
            if source_points:
                target["points_balance"] = max(0, int(target.get("points_balance") or 0)) + source_points
                source["points_balance"] = 0
                points_transferred += source_points
                target.setdefault("ledger", []).insert(
                    0,
                    {
                        "id": f"merge_{uuid.uuid4().hex[:12]}",
                        "delta": source_points,
                        "reason": "member_identity_merge",
                        "created_at": now,
                        "metadata": {
                            "source_user_id": source_id,
                            "target_user_id": canonical_target_id,
                            "operator": operator,
                            "reason": reason,
                        },
                    },
                )
                source.setdefault("ledger", []).insert(
                    0,
                    {
                        "id": f"merge_out_{uuid.uuid4().hex[:12]}",
                        "delta": -source_points,
                        "reason": "member_identity_merge",
                        "created_at": now,
                        "metadata": {
                            "target_user_id": canonical_target_id,
                            "operator": operator,
                            "reason": reason,
                        },
                    },
                )

            if not self._is_meaningful_phone(target.get("phone")) and self._is_meaningful_phone(source.get("phone")):
                target["phone"] = _normalize_phone_input(str(source.get("phone") or ""))
            for key in ("wx_openid", "wx_unionid", "wx_session_key", "wx_last_login_at"):
                if source.get(key):
                    target[key] = source[key]
                    source[key] = ""
            for key in ("avatar_url", "exam_date", "focus_topic", "focus_query"):
                if not str(target.get(key) or "").strip() and str(source.get(key) or "").strip():
                    target[key] = source[key]

            source["merged_into"] = canonical_target_id
            source["merged_at"] = now
            source["status"] = "merged"
            source["last_active_at"] = now
            merged_source_ids.append(source_id)

        after = deepcopy(target)
        audit = self._append_audit(
            data,
            action=action,
            target_user=canonical_target_id,
            reason=reason or "member_identity_merge",
            before={
                "target": before,
                "sources": source_before,
            },
            after={
                "target": after,
                "merged_source_ids": list(merged_source_ids),
                "points_transferred": points_transferred,
            },
            operator=operator,
        )
        self._remember_idempotency_key(
            data,
            action,
            idempotency_key,
            audit["id"],
            operator=operator,
        )
        return {
            "member": after,
            "audit_id": audit["id"],
            "deduped": False,
            "merged_source_ids": list(merged_source_ids),
            "points_transferred": points_transferred,
            "target_user_id": canonical_target_id,
            "admin_role_after": None,
        }

    def merge_member_accounts(
        self,
        *,
        target_user_id: str,
        source_user_ids: list[str],
        operator: str = "admin",
        reason: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        normalized_target = str(target_user_id or "").strip()
        normalized_sources = [str(item or "").strip() for item in list(source_user_ids or []) if str(item or "").strip()]
        normalized_sources = list(dict.fromkeys(normalized_sources))
        normalized_operator = str(operator or "admin").strip() or "admin"
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_target:
            raise ValueError("target_user_id is required")
        if not normalized_sources:
            raise ValueError("source_user_ids is required")
        if normalized_target in normalized_sources:
            raise ValueError("target_user_id cannot also be a source")
        if not normalized_key:
            raise ValueError("idempotency_key is required")

        action = "member_identity_merge"

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            return self._merge_member_accounts_locked(
                data,
                target_user_id=normalized_target,
                source_user_ids=normalized_sources,
                operator=normalized_operator,
                reason=str(reason or "").strip(),
                action=action,
                idempotency_key=normalized_key,
            )

        result = self._mutate(_apply)
        canonical_target = str(result.get("target_user_id") or normalized_target)
        admin_role = self._apply_merged_admin_role(
            target_user_id=canonical_target,
            merged_user_ids=[canonical_target, *normalized_sources],
            operator=normalized_operator,
            display_name=str((result.get("member") or {}).get("display_name") or ""),
        )
        if admin_role:
            result["admin_role_after"] = admin_role
        wallet_adjustments = self._apply_wallet_account_merge(
            target_user_id=canonical_target,
            source_user_ids=normalized_sources,
            operator=normalized_operator,
            reason=str(reason or "").strip(),
            idempotency_key=normalized_key,
        )
        if wallet_adjustments:
            result["wallet_adjustments"] = wallet_adjustments
        return result

    def delete_member_account(
        self,
        user_id: str,
        *,
        operator: str = "admin",
        reason: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id is required")
        audit = self.record_bi_audit(
            action="member_account_delete",
            target_user=normalized_user_id,
            operator=operator,
            reason=reason,
            after={"status": "deleted"},
            idempotency_key=idempotency_key,
        )
        return {
            "success": True,
            "user_id": normalized_user_id,
            "status": "deleted",
            "message": "会员账号已删除",
            "credentials_deleted": False,
            "sessions_invalidated": 0,
            **audit,
        }

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

    @staticmethod
    def _last_assessment_mastery_items(member: dict[str, Any]) -> list[dict[str, Any]]:
        last_assessment = member.get("last_assessment") if isinstance(member.get("last_assessment"), dict) else {}
        chapter_mastery = (
            last_assessment.get("chapter_mastery")
            if isinstance(last_assessment.get("chapter_mastery"), dict)
            else {}
        )
        return [
            {
                "name": (value.get("name") if isinstance(value, dict) else "") or key,
                "mastery": int((value.get("mastery") if isinstance(value, dict) else value) or 0),
            }
            for key, value in chapter_mastery.items()
        ]

    @staticmethod
    def _mastery_items_in_member_scope(
        member: dict[str, Any],
        source_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        scope_items = MemberConsoleService._chapter_mastery_items(member) or [
            {"name": value.get("name") or key, "mastery": 0}
            for key, value in _default_chapter_mastery().items()
        ]
        scoped: dict[str, dict[str, Any]] = {}
        for item in scope_items:
            name = str(item.get("name") or "").strip()
            if name:
                scoped[name] = {"name": name, "mastery": 0}
        for item in source_items:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            mastery = max(0, min(100, int(item.get("mastery") or 0)))
            scoped[name] = {"name": name, "mastery": mastery}
        return list(scoped.values())

    def _build_provisional_mastery_items(self, member: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def _report_mastery_items(self, member: dict[str, Any]) -> list[dict[str, Any]]:
        last_assessment_items = self._last_assessment_mastery_items(member)
        if last_assessment_items:
            return self._mastery_items_in_member_scope(member, last_assessment_items)
        mastery_items = self._chapter_mastery_items(member)
        if any(int(item.get("mastery") or 0) > 0 for item in mastery_items):
            return self._mastery_items_in_member_scope(member, mastery_items)
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
        learner_user_id = str(member.get("user_id") or user_id or "").strip()
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
        snapshot = self._read_learner_snapshot(learner_user_id, event_limit=20)
        heartbeat_context = self._read_home_heartbeat_context(learner_user_id)
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
            heartbeat_context=heartbeat_context,
        )
        dashboard = {
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
        if env_flag(_HOME_PERSONALIZATION_ENABLED):
            home_projection = self._build_home_learning_projection(snapshot=snapshot, member=member)
            if is_canonical_home_personalization_projection(home_projection):
                dashboard["home_projection"] = home_projection
                self._apply_home_learning_projection(dashboard, home_projection)
        return dashboard

    @staticmethod
    def _apply_home_learning_projection(dashboard: dict[str, Any], projection: dict[str, Any]) -> None:
        if not is_canonical_home_personalization_projection(projection):
            return
        today_focus = projection.get("today_focus")
        if isinstance(today_focus, dict) and today_focus:
            dashboard["today_focus"] = today_focus
            today = dict(dashboard.get("today") or {})
            today["hint"] = today_focus.get("title") or today.get("hint") or ""
            today["focus"] = today_focus
            dashboard["today"] = today
        recommended_prompts = projection.get("recommended_prompts")
        if isinstance(recommended_prompts, list):
            dashboard["recommended_prompts"] = recommended_prompts

    def _build_home_learning_projection(self, *, snapshot: Any | None = None, member: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            from deeptutor.services.learner_state.home_personalization import (
                build_home_dashboard_learning_projection,
            )

            return build_home_dashboard_learning_projection(
                projection=self._home_personalization_projection_from_snapshot(snapshot),
                conversation_events=list(getattr(snapshot, "memory_events", []) or [])
                if snapshot is not None
                else [],
                subject_id=self._home_subject_id(snapshot=snapshot, member=member),
            )
        except Exception:
            logger.warning("Failed to build home learning projection", exc_info=True)
            return {"recommended_prompts": [], "today_focus": {}, "source_status": {"fallback_used": True}}

    @staticmethod
    def _home_personalization_projection_from_snapshot(snapshot: Any | None) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        direct = getattr(snapshot, "home_personalization", None)
        if isinstance(direct, dict):
            return direct
        profile = getattr(snapshot, "profile", {}) or {}
        progress = getattr(snapshot, "progress", {}) or {}
        for container in [profile, progress]:
            if not isinstance(container, dict):
                continue
            projection = container.get("home_personalization")
            if isinstance(projection, dict):
                return projection
            projections = container.get("projections")
            if isinstance(projections, dict) and isinstance(projections.get("home_personalization"), dict):
                return projections["home_personalization"]
        return None

    @staticmethod
    def _home_subject_id(*, snapshot: Any | None, member: dict[str, Any] | None = None) -> str:
        containers: list[Any] = []
        if snapshot is not None:
            containers.extend([getattr(snapshot, "profile", {}) or {}, getattr(snapshot, "progress", {}) or {}])
        containers.append(member or {})
        for container in containers:
            if not isinstance(container, dict):
                continue
            for key in ("active_subject_id", "subject_id", "exam_subject_id"):
                value = str(container.get(key) or "").strip()
                if value:
                    return value
            defaults = container.get("bot_runtime_defaults")
            if isinstance(defaults, dict):
                value = str(defaults.get("subject_id") or "").strip()
                if value:
                    return value
        return "construction_exam_1"

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

    def _read_home_heartbeat_context(self, user_id: str) -> dict[str, Any]:
        context: dict[str, Any] = {"jobs": [], "history": []}
        try:
            learner_state_service = self._get_learner_state_service()
            context["jobs"] = [
                self._serialize_heartbeat_job(job)
                for job in list(learner_state_service.list_heartbeat_jobs(user_id) or [])
            ]
            context["history"] = list(learner_state_service.list_heartbeat_history(user_id, limit=3) or [])
        except Exception:
            logger.warning("Failed to load heartbeat context for home dashboard: user_id=%s", user_id, exc_info=True)
        return context

    def _build_home_today_focus(
        self,
        member: dict[str, Any],
        *,
        weak_nodes: list[dict[str, Any]],
        review: dict[str, Any],
        snapshot: Any | None = None,
        study_plan: dict[str, Any] | None = None,
        heartbeat_context: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        plan = dict(study_plan or {})
        profile = dict(getattr(snapshot, "profile", {}) or {}) if snapshot is not None else {}
        progress = dict(getattr(snapshot, "progress", {}) or {}) if snapshot is not None else {}
        focus_topic = self._pick_home_focus_topic(
            plan=plan,
            profile=profile,
            progress=progress,
            summary=str(getattr(snapshot, "summary", "") or "") if snapshot is not None else "",
            member=member,
            weak_nodes=weak_nodes,
        )
        focus_query = str(profile.get("focus_query") or member.get("focus_query") or "").strip()
        if self._is_generic_focus_query(focus_query):
            focus_query = ""
        priority_task = str(plan.get("priority_task") or "").strip()
        time_budget = str(plan.get("time_budget") or "").strip()
        overdue = max(0, int(review.get("overdue") or 0))
        due_today = max(0, int(review.get("due_today") or 0))
        heartbeat_context = dict(heartbeat_context or {})
        heartbeat_signal = self._has_home_heartbeat_signal(heartbeat_context)
        source = "learner_state.study_plan" if snapshot is not None else "member_console.study_plan"
        if heartbeat_signal:
            source = f"{source}+heartbeat"

        if overdue > 0:
            meta = f"{overdue} 个知识点 · 今天先过一遍"
            if time_budget:
                meta = f"{meta} · {time_budget}"
            if heartbeat_signal:
                meta = f"{meta} · 结合复习节奏"
            return {
                "label": "今日焦点",
                "title": "优先处理逾期复习",
                "meta": meta,
                "query": self._build_adaptive_focus_query(
                    focus_topic,
                    reason="review_due",
                    heartbeat_context=heartbeat_context,
                ),
                "topic": focus_topic,
                "tone": "review",
                "reason": "review_due",
                "source": source,
            }

        if focus_topic:
            weak_names = {
                self._normalize_home_focus_topic(item.get("name"))
                for item in weak_nodes
                if self._normalize_home_focus_topic(item.get("name"))
            }
            if snapshot is not None:
                progress = dict(getattr(snapshot, "progress", {}) or {})
                knowledge_map = dict(progress.get("knowledge_map") or {})
                weak_names.update(
                    self._normalize_home_focus_topic(item)
                    for item in list(knowledge_map.get("weak_points") or [])
                    if self._normalize_home_focus_topic(item)
                )
            tone = "practice" if focus_topic in weak_names else "plan"
            if not focus_query:
                focus_query = self._build_adaptive_focus_query(
                    focus_topic,
                    reason="learner_state_focus",
                    heartbeat_context=heartbeat_context,
                )
            meta = self._build_adaptive_focus_meta(
                priority_task=priority_task,
                time_budget=time_budget,
                heartbeat_context=heartbeat_context,
            )
            return {
                "label": "今日焦点",
                "title": f"推进{focus_topic}下一步学习",
                "meta": meta,
                "query": focus_query,
                "topic": focus_topic,
                "tone": tone,
                "reason": "learner_state_focus",
                "source": source,
            }

        if due_today > 0:
            return {
                "label": "今日焦点",
                "title": "先完成今天的复习任务",
                "meta": "结合复习任务，动态选择讲解/例题/复盘/自测",
                "query": self._build_adaptive_focus_query(
                    focus_topic,
                    reason="review_due_today",
                    heartbeat_context=heartbeat_context,
                ),
                "topic": focus_topic,
                "tone": "review",
                "reason": "review_due_today",
                "source": source,
            }

        return {
            "label": "今日焦点",
            "title": "按当前状态推进建筑实务",
            "meta": "根据学习记录，动态选择讲解/例题/复盘/自测",
            "query": self._build_adaptive_focus_query("", reason="fallback"),
            "topic": "建筑实务",
            "tone": "plan",
            "reason": "fallback_adaptive",
            "source": source,
        }

    @staticmethod
    def _normalize_home_focus_topic(value: Any) -> str:
        return canonical_home_focus_topic_label(value)

    def _pick_home_focus_topic(
        self,
        *,
        plan: dict[str, Any],
        profile: dict[str, Any],
        progress: dict[str, Any],
        summary: str,
        member: dict[str, Any],
        weak_nodes: list[dict[str, Any]],
    ) -> str:
        candidates: list[Any] = [
            plan.get("focus_topic"),
            profile.get("focus_topic"),
            self._extract_focus_topic_from_progress(progress),
            self._extract_focus_topic_from_summary(summary),
            member.get("focus_topic"),
        ]
        candidates.extend(item.get("name") for item in weak_nodes[:1])
        for candidate in candidates:
            topic = self._normalize_home_focus_topic(candidate)
            if topic:
                return topic
        return ""

    @staticmethod
    def _extract_focus_topic_from_progress(progress: dict[str, Any]) -> str:
        knowledge_map = dict(progress.get("knowledge_map") or {})
        weak_points = list(knowledge_map.get("weak_points") or [])
        for item in weak_points:
            topic = str(item or "").strip()
            if topic:
                return topic
        chapters = list(knowledge_map.get("chapters") or progress.get("chapters") or [])
        chapter_candidates: list[tuple[float, str]] = []
        for item in chapters:
            if not isinstance(item, dict):
                continue
            name = str(item.get("chapter_name") or item.get("name") or "").strip()
            if not name:
                continue
            total = float(item.get("total") or 0)
            done = float(item.get("done") or 0)
            ratio = done / total if total > 0 else 1.0
            chapter_candidates.append((ratio, name))
        if chapter_candidates:
            chapter_candidates.sort(key=lambda item: item[0])
            return chapter_candidates[0][1]
        return ""

    @staticmethod
    def _extract_focus_topic_from_summary(summary: str) -> str:
        text = str(summary or "")
        patterns = (
            r"当前聚焦[:：]\s*([^\n。；;]+)",
            r"上次建议复习[:：]\s*([^\n。；;]+)",
            r"优先复习[“\"]?([^”\"\n。；;]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            topic = match.group(1).strip().strip("“”\"'。；;，,")
            if topic:
                return topic
        return ""

    @staticmethod
    def _has_home_heartbeat_signal(heartbeat_context: dict[str, Any]) -> bool:
        jobs = [item for item in list(heartbeat_context.get("jobs") or []) if str(item.get("status") or "") == "active"]
        history = list(heartbeat_context.get("history") or [])
        return bool(jobs or history)

    def _build_adaptive_focus_meta(
        self,
        *,
        priority_task: str,
        time_budget: str,
        heartbeat_context: dict[str, Any],
    ) -> str:
        base = time_budget or "按当前学习记录推进"
        if self._has_home_heartbeat_signal(heartbeat_context):
            return f"{base} · 结合复习节奏动态选择方式"
        if priority_task:
            return "结合当前进度动态选择讲解/例题/复盘/自测"
        return f"{base} · 动态选择讲解/例题/复盘/自测"

    @staticmethod
    def _is_generic_focus_query(value: str | None) -> bool:
        normalized = re.sub(r"\s+", "", str(value or "").strip())
        if not normalized:
            return True
        if "学习计划" in normalized:
            return True
        if "下一步学习推进" in normalized:
            return True
        if "先判断我当前更适合" in normalized:
            return True
        if normalized.startswith("继续巩固"):
            return True
        if (
            "安排5道" in normalized
            or "专项训练题" in normalized
            or "相关题目" in normalized
            or "知识点梳理" in normalized
        ):
            return True
        return normalized in {"继续我的计划", "继续计划", "继续学习", "按计划继续", "帮我做一次入门摸底测试"}

    @staticmethod
    def _build_adaptive_focus_query(
        topic: str,
        *,
        reason: str = "learner_state_focus",
        heartbeat_context: dict[str, Any] | None = None,
    ) -> str:
        focus = str(topic or "").strip()
        context_hint = "请根据我的学习记录、最近进度"
        heartbeat_context = dict(heartbeat_context or {})
        if (
            list(heartbeat_context.get("jobs") or [])
            or list(heartbeat_context.get("history") or [])
        ):
            context_hint += "和周期复习节奏"
        if reason in {"review_due", "review_due_today"}:
            return (
                f"{context_hint}，带我复习今天该回看的建筑实务内容：先讲清一个最容易遗忘的核心考点，"
                "再用一个考试场景帮我复盘易错判断，最后给我一个简短自查问题；不要展开成长期安排，也不要直接生成整套训练题。"
            )
        if not focus:
            return (
                f"{context_hint}，先选出今天最值得补的一块建筑实务内容，然后用微课方式讲清："
                "一个核心考点、一个考试场景例子、一个自查问题；不要展开成长期安排，也不要直接生成整套训练题。"
            )
        return (
            f"{context_hint}，围绕{focus}做一次建筑实务微课：先讲清一个最容易失分的核心考点，"
            "再用一个考试场景例子带我判断，最后给我一个简短自查问题；不要展开成长期安排，也不要直接生成整套训练题。"
        )

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
        focus_hint = f"讲清 {focus_topic} 的核心考点" if focus_topic else ""
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
            self._mastery_items_in_member_scope(member, self._last_assessment_mastery_items(member))
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

        coverage_mastery = round(
            sum(int(item.get("mastery") or 0) for item in chapter_mastery.values())
            / max(len(chapter_mastery), 1)
        )
        stored_score = last_assessment.get("score") if last_mastery else None
        avg_mastery = min(round(float(stored_score)), coverage_mastery) if stored_score is not None else coverage_mastery
        level = "advanced" if avg_mastery >= 75 else "intermediate" if avg_mastery >= 50 else "beginner"
        stored_feedback = (
            last_assessment.get("diagnostic_feedback")
            if isinstance(last_assessment.get("diagnostic_feedback"), dict)
            else None
        )
        if stored_feedback:
            normalized_feedback = deepcopy(stored_feedback)
            ability_overview = dict(normalized_feedback.get("ability_overview") or {})
            ability_overview["score_pct"] = avg_mastery
            ability_overview["chapter_mastery"] = chapter_mastery
            normalized_feedback["ability_overview"] = ability_overview
            return {
                "score": avg_mastery,
                "knowledge_score": int(last_assessment.get("knowledge_score") or avg_mastery),
                "level": level,
                "blueprint_version": str(last_assessment.get("blueprint_version") or ""),
                "measurement_confidence": str(last_assessment.get("measurement_confidence") or ""),
                "teaching_policy_seed": dict(last_assessment.get("teaching_policy_seed") or {}),
                "assessment_observability": dict(last_assessment.get("assessment_observability") or {}),
                "chapter_mastery": chapter_mastery,
                "diagnostic_profile": {
                    "learner_archetype": str(
                        dict(normalized_feedback.get("learner_profile") or {}).get("archetype") or ""
                    ),
                    "response_profile": str(
                        dict(normalized_feedback.get("cognitive_insight") or {}).get("response_profile") or ""
                    ),
                    "calibration_label": str(
                        dict(normalized_feedback.get("cognitive_insight") or {}).get("calibration_label") or ""
                    ),
                },
                "diagnostic_feedback": normalized_feedback,
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

    def create_assessment(
        self,
        user_id: str,
        count: int = 20,
        *,
        assessment_type: str = "diagnostic",
        subject_id: str = "construction_exam",
        topic_ids: list[str] | None = None,
        duration_policy: dict[str, Any] | None = None,
        device_id: str = "",
    ) -> dict[str, Any]:
        self._require_durable_assessment_sessions()
        normalized_assessment_type = str(assessment_type or "diagnostic").strip() or "diagnostic"
        if normalized_assessment_type == "topic_diagnostic":
            return self._create_topic_diagnostic_assessment(
                user_id,
                count=count,
                subject_id=subject_id,
                topic_ids=topic_ids or ["waterproof"],
                device_id=device_id,
            )
        if normalized_assessment_type == "real_exam_simulation":
            return self._create_real_exam_simulation_assessment(
                user_id,
                count=count,
                subject_id=subject_id,
                device_id=device_id,
            )

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
                "form_source": str(payload.get("form_source") or "unknown"),
                "form_id": payload.get("form_id") or "",
                "form_index": int(payload.get("form_index") or 0),
                "form_count": int(payload.get("form_count") or 0),
                "created_at": now,
                "observability": {
                    "started_at": now,
                    "first_answer_at": "",
                    "submitted_at": "",
                    "requested_count": payload["requested_count"],
                    "delivered_count": payload["delivered_count"],
                    "scored_count": payload["scored_count"],
                    "profile_count": payload["profile_count"],
                    "form_source": str(payload.get("form_source") or "unknown"),
                    "completion_rate": 0,
                },
            }
            logger.info(
                "Assessment session created: user_id=%s quiz_id=%s blueprint_version=%s form_source=%s form_id=%s "
                "form_index=%s form_count=%s fallback_used=%s question_bank_size=%s",
                user_id,
                quiz_id,
                payload["blueprint_version"],
                str(payload.get("form_source") or "unknown"),
                payload.get("form_id") or "",
                int(payload.get("form_index") or 0),
                int(payload.get("form_count") or 0),
                bool(payload.get("fallback_used")),
                payload["question_bank_size"],
            )
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
                "form_source": str(payload.get("form_source") or "unknown"),
                "form_id": payload.get("form_id") or "",
                "form_index": int(payload.get("form_index") or 0),
                "form_count": int(payload.get("form_count") or 0),
            }

        return self._mutate(_apply)

    def _create_topic_diagnostic_assessment(
        self,
        user_id: str,
        *,
        count: int,
        subject_id: str,
        topic_ids: list[str],
        device_id: str = "",
    ) -> dict[str, Any]:
        normalized_topics = [str(item).strip() for item in list(topic_ids or ["waterproof"]) if str(item).strip()]
        if not normalized_topics:
            normalized_topics = ["waterproof"]
        try:
            topic_spec = resolve_topic_testset_spec(normalized_topics)
        except TopicTestSetUnavailable as exc:
            raise AssessmentBlueprintUnavailable(str(exc)) from exc
        normalized_topics = [topic_spec.topic_id]
        blueprint_version = topic_spec.blueprint_version
        payload = self._build_assessment_blueprint_service(blueprint_version).create_session(
            user_id=user_id,
            count=count,
            assessment_type="topic_diagnostic",
            subject_id=subject_id,
            topic_ids=normalized_topics,
        )
        session = self._assessment_session_repository.create_session(
            user_id=user_id,
            assessment_type="topic_diagnostic",
            subject_id=subject_id,
            topic_ids=normalized_topics,
            blueprint_version=payload["blueprint_version"],
            form_id=str(payload.get("form_id") or ""),
            client_questions_public=list(payload.get("questions") or []),
            session_questions_private=list(payload.get("session_questions") or []),
            device_id=device_id,
        )
        return {
            "quiz_id": session["quiz_id"],
            "assessment_type": "topic_diagnostic",
            "subject_id": subject_id,
            "topic_ids": normalized_topics,
            "topic_label": f"{topic_spec.label}专题测评",
            "status": session["status"],
            "reuse_reason": session.get("reuse_reason", ""),
            "questions": deepcopy(session["client_questions_public"]),
            "blueprint_version": session["blueprint_version"],
            "form_id": session["form_id"],
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
            "form_source": str(payload.get("form_source") or "unknown"),
            "form_index": int(payload.get("form_index") or 0),
            "form_count": int(payload.get("form_count") or 0),
        }

    def _create_real_exam_simulation_assessment(
        self,
        user_id: str,
        *,
        count: int,
        subject_id: str,
        device_id: str = "",
    ) -> dict[str, Any]:
        blueprint_version = "real_exam_simulation_mini_v1"
        payload = self._build_assessment_blueprint_service(blueprint_version).create_session(
            user_id=user_id,
            count=count,
            assessment_type="real_exam_simulation",
            subject_id=subject_id,
            topic_ids=[],
        )
        session = self._assessment_session_repository.create_session(
            user_id=user_id,
            assessment_type="real_exam_simulation",
            subject_id=subject_id,
            topic_ids=[],
            blueprint_version=payload["blueprint_version"],
            form_id=str(payload.get("form_id") or ""),
            client_questions_public=list(payload.get("questions") or []),
            session_questions_private=list(payload.get("session_questions") or []),
            device_id=device_id,
        )
        source_policy = real_exam_source_policy(real_exam_share=0.0)
        return {
            "quiz_id": session["quiz_id"],
            "assessment_type": "real_exam_simulation",
            "subject_id": subject_id,
            "topic_ids": [],
            "topic_label": str(source_policy.get("label") or "综合模拟测评"),
            "source_policy": source_policy,
            "status": session["status"],
            "reuse_reason": session.get("reuse_reason", ""),
            "questions": deepcopy(session["client_questions_public"]),
            "blueprint_version": session["blueprint_version"],
            "form_id": session["form_id"],
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
            "form_source": str(payload.get("form_source") or "unknown"),
            "form_index": int(payload.get("form_index") or 0),
            "form_count": int(payload.get("form_count") or 0),
        }

    def submit_assessment(
        self,
        user_id: str,
        quiz_id: str,
        answers: dict[str, str],
        time_spent_seconds: int,
        *,
        device_id: str = "",
    ) -> dict[str, Any]:
        try:
            p0a_session = self._assessment_session_repository.private_session(user_id, quiz_id)
        except AssessmentSessionNotFound:
            p0a_session = None
        if p0a_session and p0a_session.get("assessment_type") in {"topic_diagnostic", "real_exam_simulation"}:
            return self._submit_durable_assessment(
                user_id,
                quiz_id,
                answers=answers,
                time_spent_seconds=time_spent_seconds,
                device_id=device_id,
            )

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            session = data.get("assessment_sessions", {}).get(quiz_id)
            if not session:
                raise KeyError(f"Unknown quiz: {quiz_id}")
            if str(session.get("user_id") or "") != str(user_id):
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
                    "archetype_name": "动态调节型学员",
                    "description": "系统会根据你的知识得分、学习习惯和作答节奏动态调整讲解、练习与复盘方式。",
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
            response = {
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
            response["_learning_evidence_batch"] = build_assessment_learning_evidence_batch(
                quiz_id=quiz_id,
                blueprint_version=member["last_assessment"]["blueprint_version"],
                questions=scored_questions,
                answers=answers,
            )
            return response

        result = self._mutate(_apply)
        learning_evidence_batch = result.pop("_learning_evidence_batch", None)
        self._write_assessment_learning_signals(
            user_id,
            quiz_id,
            result,
            learning_evidence_batch=learning_evidence_batch,
        )
        return result

    def _submit_durable_assessment(
        self,
        user_id: str,
        quiz_id: str,
        *,
        answers: dict[str, str],
        time_spent_seconds: int,
        device_id: str = "",
    ) -> dict[str, Any]:
        session = self._assessment_session_repository.private_session(user_id, quiz_id)
        if session.get("submitted_answer_snapshot") is not None:
            if dict(session.get("submitted_answer_snapshot") or {}) != dict(answers or {}):
                raise AssessmentSessionConflict("assessment_submit_body_conflict")
            if session.get("result_report_json"):
                return deepcopy(session["result_report_json"])
        try:
            scored_result = score_assessment(
                list(session.get("session_questions_private") or []),
                answers,
                time_spent_seconds=time_spent_seconds,
            )
        except AssessmentScoringError as exc:
            raise AssessmentSessionConflict("assessment_scoring_conflict") from exc
        assessment_type = str(session.get("assessment_type") or "topic_diagnostic")
        topic_ids = list(session.get("topic_ids") or ["waterproof"])
        if assessment_type == "real_exam_simulation":
            topic_ids = []
            topic_label = str(real_exam_source_policy(real_exam_share=0.0).get("label") or "综合模拟测评")
        else:
            try:
                topic_spec = resolve_topic_testset_spec(topic_ids)
                topic_label = f"{topic_spec.label}专题测评"
            except TopicTestSetUnavailable:
                topic_label = "专题测评"
        report = build_result_report(
            quiz_id=quiz_id,
            assessment_type=assessment_type,
            subject_id=str(session.get("subject_id") or "construction_exam"),
            topic_ids=topic_ids,
            topic_label=topic_label,
            blueprint_version=str(session.get("blueprint_version") or "topic_waterproof_v1"),
            form_id=str(session.get("form_id") or ""),
            scored_result=scored_result,
            writeback_refs={"writeback_status": {"status": "pending"}},
        )
        submitted = self._assessment_session_repository.mark_submitted_once(
            user_id,
            quiz_id,
            submitted_answer_snapshot=dict(answers or {}),
            result_report_json=report,
            device_id=device_id,
        )
        if submitted.get("learning_event_refs"):
            return deepcopy(submitted.get("result_report_json") or report)
        self._schedule_topic_diagnostic_writeback(
            user_id=user_id,
            quiz_id=quiz_id,
            session=session,
            scored_result=scored_result,
        )
        return deepcopy(submitted.get("result_report_json") or report)

    def _submit_topic_diagnostic_assessment(
        self,
        user_id: str,
        quiz_id: str,
        *,
        answers: dict[str, str],
        time_spent_seconds: int,
    ) -> dict[str, Any]:
        return self._submit_durable_assessment(
            user_id,
            quiz_id,
            answers=answers,
            time_spent_seconds=time_spent_seconds,
        )

    def _schedule_topic_diagnostic_writeback(
        self,
        *,
        user_id: str,
        quiz_id: str,
        session: dict[str, Any],
        scored_result: dict[str, Any],
    ) -> None:
        future = _ASSESSMENT_WRITEBACK_EXECUTOR.submit(
            self._complete_topic_diagnostic_writeback,
            user_id=user_id,
            quiz_id=quiz_id,
            session=deepcopy(session),
            scored_result=deepcopy(scored_result),
        )
        future.add_done_callback(
            lambda item: logger.error(
                "assessment_writeback_background_failed",
                exc_info=(type(item.exception()), item.exception(), item.exception().__traceback__),
            )
            if item.exception() is not None
            else None
        )

    def _complete_topic_diagnostic_writeback(
        self,
        *,
        user_id: str,
        quiz_id: str,
        session: dict[str, Any],
        scored_result: dict[str, Any],
    ) -> None:
        try:
            writeback_refs = AssessmentWritebackService(
                learner_state_service=self._get_learner_state_service(),
                mistake_book_service=MistakeBookService(),
            ).writeback(
                user_id=user_id,
                quiz_id=quiz_id,
                form_id=str(session.get("form_id") or ""),
                assessment_type=str(session.get("assessment_type") or "topic_diagnostic"),
                subject_id=str(session.get("subject_id") or "construction_exam"),
                scored_result=scored_result,
            )
            self._assessment_session_repository.attach_writeback_refs(
                user_id,
                quiz_id,
                learning_event_refs=list(writeback_refs.get("learning_event_refs") or []),
                mistake_book_refs=list(writeback_refs.get("mistake_book_refs") or []),
                mark_scored=True,
            )
        except Exception:
            self._assessment_session_repository.record_degraded(
                user_id,
                quiz_id,
                reason="writeback_failed",
            )

    def retry_assessment_writeback(self, user_id: str, quiz_id: str) -> dict[str, Any]:
        self._require_durable_assessment_sessions()
        session = self._assessment_session_repository.private_session(user_id, quiz_id)
        if session.get("assessment_type") not in {"topic_diagnostic", "real_exam_simulation"}:
            raise KeyError(f"Unknown quiz: {quiz_id}")
        if not session.get("submitted_answer_snapshot"):
            raise KeyError(f"Assessment not submitted: {quiz_id}")
        scored_result = score_assessment(
            list(session.get("session_questions_private") or []),
            dict(session.get("submitted_answer_snapshot") or {}),
            time_spent_seconds=0,
        )
        writeback_refs = AssessmentWritebackService(
            learner_state_service=self._get_learner_state_service(),
            mistake_book_service=MistakeBookService(),
        ).writeback(
            user_id=user_id,
            quiz_id=quiz_id,
            form_id=str(session.get("form_id") or ""),
            assessment_type=str(session.get("assessment_type") or "topic_diagnostic"),
            subject_id=str(session.get("subject_id") or "construction_exam"),
            scored_result=scored_result,
        )
        stored = self._assessment_session_repository.attach_writeback_refs(
            user_id,
            quiz_id,
            learning_event_refs=list(writeback_refs.get("learning_event_refs") or []),
            mistake_book_refs=list(writeback_refs.get("mistake_book_refs") or []),
            mark_scored=True,
        )
        logger.info(
            "assessment_writeback_retry_succeeded quiz_id=%s assessment_type=%s",
            quiz_id,
            session.get("assessment_type"),
        )
        return deepcopy(stored.get("result_report_json") or {})

    def get_assessment_session(self, user_id: str, quiz_id: str, *, device_id: str = "") -> dict[str, Any]:
        self._require_durable_assessment_sessions()
        try:
            return self._assessment_session_repository.get_session_for_resume(user_id, quiz_id, device_id=device_id)
        except AssessmentSessionError as exc:
            raise KeyError(str(exc)) from exc

    def get_assessment_report(self, user_id: str, quiz_id: str) -> dict[str, Any]:
        self._require_durable_assessment_sessions()
        try:
            session = self._assessment_session_repository.private_session(user_id, quiz_id)
        except AssessmentSessionError as exc:
            raise KeyError(str(exc)) from exc
        report = session.get("result_report_json")
        if not report:
            raise KeyError(f"Assessment report not ready: {quiz_id}")
        return deepcopy(report)

    async def get_assessment_deep_explanation(self, user_id: str, quiz_id: str, question_id: str) -> dict[str, Any]:
        self._require_durable_assessment_sessions()
        try:
            session = self._assessment_session_repository.private_session(user_id, quiz_id)
        except AssessmentSessionError as exc:
            raise KeyError(str(exc)) from exc
        report = session.get("result_report_json")
        if not report:
            raise KeyError(f"Assessment report not ready: {quiz_id}")
        private_questions = list(session.get("session_questions_private") or [])
        normalized_question_id = str(question_id or "").strip()
        report_item = {}
        for item in list(report.get("wrong_items") or []) + list(report.get("items") or []):
            if str(item.get("question_id") or "") == normalized_question_id:
                report_item = dict(item)
                break
        question = next(
            (
                item
                for item in private_questions
                if str(item.get("question_id") or item.get("source_question_id") or "") == normalized_question_id
            ),
            {},
        )
        if question and report_item:
            question = {**report_item, **question}
        if not question and report_item:
            question = dict(report_item)
        if not question:
            raise KeyError(f"Unknown assessment question: {question_id}")
        learner_answer = str(question.get("learner_answer") or "")
        correct_answer = str(question.get("correct_answer") or question.get("answer") or "")
        cache_key = build_explanation_cache_key(
            quiz_id,
            normalized_question_id,
            hashlib.sha256(learner_answer.encode("utf-8")).hexdigest(),
            hashlib.sha256(json.dumps(question, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
            PROMPT_VERSION,
        )
        self._ensure_assessment_explanation_balance(
            user_id=user_id,
            cache_key=cache_key,
            minimum_points=minimum_explanation_points(),
        )
        explanation = await generate_llm_deep_explanation(
            question=question,
            learner_answer=learner_answer,
            correct_answer=correct_answer,
            quiz_id=quiz_id,
            question_id=normalized_question_id,
        )
        usage_summary = explanation.pop("usage_summary", None)
        amount_points, billing_metadata = billable_points_from_usage_summary(usage_summary)
        billing = self._capture_assessment_explanation_points(
            user_id=user_id,
            quiz_id=quiz_id,
            question_id=normalized_question_id,
            cache_key=cache_key,
            amount_points=amount_points,
            metadata=billing_metadata,
        )
        return {
            "quiz_id": quiz_id,
            "question_id": normalized_question_id,
            "cache_key": cache_key,
            "cache_status": "generated",
            "workflow_status": "completed",
            "billing": billing,
            "explanation": explanation,
        }

    def _ensure_assessment_explanation_balance(
        self,
        *,
        user_id: str,
        cache_key: str,
        minimum_points: int,
    ) -> None:
        idempotency_key = f"assessment_ai_explanation:{cache_key}"
        wallet_service = self._get_wallet_service()
        if getattr(wallet_service, "is_configured", False):
            existing_entry = wallet_service.find_wallet_ledger_by_idempotency_key(
                user_id,
                idempotency_key=idempotency_key,
            )
            if existing_entry is not None:
                return
            snapshot = wallet_service.get_wallet(user_id)
            balance_points = int((getattr(snapshot, "balance_micros", 0) or 0) / 1_000_000) if snapshot else 0
        else:
            wallet = self.get_wallet(user_id)
            balance_points = int(wallet.get("balance") or 0)
        if balance_points < int(minimum_points):
            raise RuntimeError("assessment_deep_explanation_insufficient_balance")

    def _capture_assessment_explanation_points(
        self,
        *,
        user_id: str,
        quiz_id: str,
        question_id: str,
        cache_key: str,
        amount_points: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        idempotency_key = f"assessment_ai_explanation:{cache_key}"
        payload_metadata = {
            "source": "assessment_deep_explanation",
            "quiz_id": str(quiz_id or "").strip(),
            "question_id": str(question_id or "").strip(),
            **dict(metadata or {}),
        }
        wallet_service = self._get_wallet_service()
        if getattr(wallet_service, "is_configured", False):
            try:
                result = wallet_service.capture_points(
                    user_id=user_id,
                    amount_points=amount_points,
                    idempotency_key=idempotency_key,
                    reference_id=str(question_id or quiz_id or "").strip(),
                    reference_type="assessment_ai_explanation",
                    reason="assessment_ai_explanation",
                    metadata=payload_metadata,
                )
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "assessment deep explanation wallet capture failed: user_id=%s quiz_id=%s question_id=%s error=%s",
                    user_id,
                    quiz_id,
                    question_id,
                    exc,
                    exc_info=True,
                )
                raise RuntimeError("assessment_deep_explanation_billing_failed") from exc
            return {
                "status": "captured",
                "amount_points": int(amount_points),
                "captured_points": int(round(int(getattr(result, "captured_micros", 0) or 0) / 1_000_000)),
                "balance_after_points": int(round(int(getattr(result, "balance_after_micros", 0) or 0) / 1_000_000)),
                "idempotency_key": idempotency_key,
                **payload_metadata,
            }

        local_result = self.capture_points(user_id, amount=int(amount_points), reason="assessment_ai_explanation")
        if int(local_result.get("captured") or 0) < int(amount_points):
            raise RuntimeError("assessment_deep_explanation_insufficient_balance")
        return {
            "status": "captured",
            "amount_points": int(amount_points),
            "captured_points": int(local_result.get("captured") or 0),
            "balance_after_points": int(local_result.get("balance") or 0),
            "idempotency_key": idempotency_key,
            **payload_metadata,
        }

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
            if str(member.get("status") or "").strip() == "deleted":
                continue
            if str(member.get("auth_username") or "").strip() == normalized_username:
                return member
            if normalized_external_user_id and str(member.get("external_auth_user_id") or "").strip() == normalized_external_user_id:
                return member
            if normalized_phone and _slugify_phone(str(member.get("phone") or "")) == normalized_phone:
                return member
        return None

    def _ensure_member_for_external_auth(
        self,
        username: str,
        user_data: dict[str, Any],
        *,
        preserve_display_name: bool = False,
    ) -> dict[str, Any]:
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
            current_display = str(member.get("display_name") or "").strip()
            current_user_id = str(member.get("user_id") or "").strip()
            if not preserve_display_name or not current_display or current_display == current_user_id:
                member["display_name"] = normalized_username or current_display
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
        normalized_phone = _normalize_phone_input(phone)
        if not normalized_phone:
            raise ValueError("手机号格式不正确")
        try:
            existing_alias_ids = self._trusted_phone_alias_user_ids(normalized_phone)
        except ValueError as exc:
            raise ValueError("手机号身份冲突，请联系客服") from exc
        if existing_alias_ids:
            raise ValueError("该手机号已被注册，请直接登录或找回密码")
        if self._local_member_user_ids_for_phone(normalized_phone):
            raise ValueError("该手机号已被注册，请直接登录或找回密码")
        external_user = create_external_auth_user(username, password, phone=phone)
        member = self._ensure_member_for_external_auth(username, external_user)
        auth_identity = self._auth_identity_for_member(str(member.get("user_id") or "").strip())
        token = self._issue_access_token(
            user_id=auth_identity["user_id"],
            canonical_uid=auth_identity["canonical_uid"],
        )
        self._persist_phone_identity(
            phone=normalized_phone,
            canonical_uid=str(auth_identity.get("canonical_uid") or "").strip(),
        )
        return self._build_auth_response(user_id=auth_identity["user_id"], token=token)

    @staticmethod
    def _phone_alias_values(phone: str) -> list[str]:
        normalized = _normalize_phone_input(phone)
        if not normalized:
            return []
        return [normalized, f"+86{normalized}"]

    def _trusted_phone_alias_user_ids(self, phone: str) -> set[str]:
        values = self._phone_alias_values(phone)
        if not values:
            return set()
        try:
            from deeptutor.services.wallet.identity import get_wallet_identity_store

            store = get_wallet_identity_store()
        except Exception as exc:
            logger.warning("phone alias store unavailable for phone=%s: %s", phone[-4:], exc)
            raise ValueError("手机号身份暂时不可用，请稍后重试") from exc
        if not getattr(store, "is_configured", False):
            return set()
        resolved: set[str] = set()
        for alias_value in values:
            try:
                row = store.resolve_alias(alias_type="phone", alias_value=alias_value)
            except Exception as exc:
                logger.warning("phone alias lookup failed for phone=%s: %s", phone[-4:], exc)
                raise ValueError("手机号身份暂时不可用，请稍后重试") from exc
            if not isinstance(row, dict):
                continue
            source = str(row.get("source") or "").strip()
            user_id = str(row.get("user_id") or "").strip()
            if source not in _TRUSTED_PHONE_ALIAS_SOURCES or not is_uuid_like(user_id):
                continue
            resolved.add(user_id)
        if len(resolved) > 1:
            raise ValueError("手机号身份冲突，请联系客服")
        return resolved

    def _local_member_user_ids_for_phone(self, phone: str) -> set[str]:
        normalized_phone = _normalize_phone_input(phone)
        if not normalized_phone:
            return set()
        found: set[str] = set()
        data = self._load()
        for member in data.get("members") or []:
            if not isinstance(member, dict):
                continue
            if str(member.get("status") or "").strip() == "deleted":
                continue
            if _slugify_phone(str(member.get("phone") or "")) != normalized_phone:
                continue
            for key in ("user_id", "external_auth_user_id", "merged_into"):
                candidate = str(member.get(key) or "").strip()
                if candidate:
                    found.add(candidate)
        return found

    def _linked_member_phone_matches_account(
        self,
        *,
        external_user: dict[str, Any],
        username: str,
        phone: str,
    ) -> tuple[bool, set[str]]:
        external_user_id = str(external_user.get("id") or "").strip()
        account_ids = {external_user_id} if is_uuid_like(external_user_id) else set()
        linked_phone_match = False
        data = self._load()
        for member in data.get("members") or []:
            if not isinstance(member, dict):
                continue
            linked = str(member.get("auth_username") or "").strip() == username
            if external_user_id and str(member.get("external_auth_user_id") or "").strip() == external_user_id:
                linked = True
            if not linked:
                continue
            for key in ("user_id", "external_auth_user_id", "merged_into"):
                candidate = str(member.get(key) or "").strip()
                if is_uuid_like(candidate):
                    account_ids.add(candidate)
            if _slugify_phone(str(member.get("phone") or "")) == phone:
                linked_phone_match = True
        return linked_phone_match, account_ids

    def _resolve_phone_backed_password_reset_account(self, phone: str) -> dict[str, Any]:
        normalized_phone = _normalize_phone_input(phone)
        if not normalized_phone:
            raise ValueError("手机号格式不正确")
        try:
            phone_alias_ids = self._trusted_phone_alias_user_ids(normalized_phone)
        except ValueError as exc:
            logger.warning(
                "password reset phone alias conflict: phone=%s error=%s",
                normalized_phone[-4:],
                exc,
            )
            raise ValueError("账号或手机号不匹配") from exc
        local_account_ids = self._local_member_user_ids_for_phone(normalized_phone)
        external_user = get_external_auth_user_by_phone(normalized_phone)
        external_user_id = str((external_user or {}).get("id") or "").strip()
        if not phone_alias_ids and not local_account_ids and external_user is None:
            raise ValueError("账号或手机号不匹配")

        canonical_uid = ""
        if phone_alias_ids:
            canonical_uid = next(iter(phone_alias_ids))
        elif is_uuid_like(external_user_id):
            canonical_uid = external_user_id
        else:
            local_uuid_ids = {candidate for candidate in local_account_ids if is_uuid_like(candidate)}
            if len(local_uuid_ids) > 1:
                raise ValueError("账号或手机号不匹配")
            if local_uuid_ids:
                canonical_uid = next(iter(local_uuid_ids))

        external_user = ensure_external_auth_user_for_phone(
            normalized_phone,
            user_id=canonical_uid or None,
        )
        external_username = str(external_user.get("username") or "").strip()
        if not external_username:
            raise ValueError("账号或手机号不匹配")
        member = self._ensure_member_for_external_auth(
            external_username,
            external_user,
            preserve_display_name=True,
        )
        account_ids = set(local_account_ids)
        external_user_id = str(external_user.get("id") or "").strip()
        for candidate in (
            external_user_id,
            str(member.get("user_id") or "").strip(),
            str(member.get("external_auth_user_id") or "").strip(),
            str(member.get("merged_into") or "").strip(),
        ):
            if is_uuid_like(candidate):
                account_ids.add(candidate)
        return {
            "username": external_username,
            "phone": normalized_phone,
            "external_user": external_user,
            "account_ids": sorted(account_ids),
        }

    def _resolve_password_reset_account(self, username: str, phone: str) -> dict[str, Any]:
        normalized_phone = _normalize_phone_input(phone)
        if not normalized_phone:
            raise ValueError("手机号格式不正确")
        normalized_username = str(username or "").strip()
        external_user = get_external_auth_user(normalized_username)
        if not external_user:
            if (
                not normalized_username
                or _normalize_phone_input(normalized_username) == normalized_phone
            ):
                return self._resolve_phone_backed_password_reset_account(normalized_phone)
            raise ValueError("账号或手机号不匹配")
        linked_phone_match, account_ids = self._linked_member_phone_matches_account(
            external_user=external_user,
            username=normalized_username,
            phone=normalized_phone,
        )
        external_phone_match = _slugify_phone(str(external_user.get("phone") or "")) == normalized_phone
        try:
            phone_alias_ids = self._trusted_phone_alias_user_ids(normalized_phone)
        except ValueError as exc:
            logger.warning(
                "password reset phone alias conflict: username=%s phone=%s error=%s",
                normalized_username,
                normalized_phone[-4:],
                exc,
            )
            raise ValueError("账号或手机号不匹配") from exc
        if phone_alias_ids and account_ids.isdisjoint(phone_alias_ids):
            raise ValueError("账号或手机号不匹配")
        if external_phone_match or linked_phone_match or (phone_alias_ids and not account_ids.isdisjoint(phone_alias_ids)):
            return {
                "username": normalized_username,
                "phone": normalized_phone,
                "external_user": external_user,
                "account_ids": sorted(account_ids),
            }
        raise ValueError("账号或手机号不匹配")

    def _resolve_verified_phone_canonical_uid(self, phone: str) -> str:
        alias_ids = self._trusted_phone_alias_user_ids(phone)
        if not alias_ids:
            return ""
        return next(iter(alias_ids))

    async def _resolve_wechat_login_identity(self, code: str) -> dict[str, str]:
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
            _cur_display = str(target.get("display_name") or "").strip()
            _cur_uid = str(target.get("user_id") or "").strip()
            if not _cur_display or _cur_display == _cur_uid:
                target["display_name"] = f"微信用户{_cur_uid[-4:]}"
            target["last_active_at"] = _iso()
            target["wx_openid"] = openid
            target["wx_unionid"] = unionid
            target["wx_session_key"] = session_key
            target["wx_last_login_at"] = _iso()
            return str(target["user_id"])

        target_user_id = self._mutate(_apply)
        return {
            "user_id": target_user_id,
            "openid": openid,
            "unionid": unionid,
        }

    async def login_with_wechat_code(self, code: str) -> dict[str, Any]:
        identity = await self._resolve_wechat_login_identity(code)
        target_user_id = identity["user_id"]
        openid = identity["openid"]
        unionid = identity["unionid"]
        auth_identity = self._auth_identity_for_member(target_user_id)
        token = self._issue_access_token(
            user_id=auth_identity["user_id"],
            canonical_uid=auth_identity["canonical_uid"],
            openid=auth_identity["openid"] or openid,
            unionid=auth_identity["unionid"] or unionid,
        )
        # 幂等补写：每次登录都尝试持久化 openid/unionid alias，
        # 确保首次绑定时 DB 短暂不可用的情况下可在后续登录中自动补全。
        self._persist_wechat_openid_identity(
            openid=auth_identity["openid"] or openid,
            unionid=auth_identity["unionid"] or unionid,
            canonical_uid=str(auth_identity.get("canonical_uid") or "").strip(),
        )
        return self._build_auth_response(
            user_id=auth_identity["user_id"],
            token=token,
            openid=auth_identity["openid"] or openid,
            unionid=auth_identity["unionid"] or unionid,
        )

    async def login_with_wechat_phone(self, code: str, phone_code: str) -> dict[str, Any]:
        identity = await self._resolve_wechat_login_identity(code)
        return await self.bind_phone_for_wechat(identity["user_id"], phone_code)

    async def bind_phone_for_wechat(self, user_id: str, phone_code: str) -> dict[str, Any]:
        raw_code = str(phone_code or "").strip()
        if not raw_code:
            raise ValueError("valid phone_code is required")

        # 微信 phone_code 是授权码（非手机号），禁止把授权码里的数字截取当手机号使用。
        # 仅当 raw_code 本身已是合法大陆手机号（开发/测试环境直传）才直接使用，
        # 否则置空，强制调用微信 API 换取真实号码。
        _maybe_direct = _normalize_phone_input(raw_code)
        normalized = _maybe_direct if self._is_cn_mainland_mobile(_maybe_direct) else ""
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

        try:
            verified_phone_canonical_uid = self._resolve_verified_phone_canonical_uid(normalized)
        except ValueError as exc:
            raise ValueError("手机号身份冲突，请联系客服") from exc

        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            current = self._ensure_member(data, user_id)
            target = (
                self._ensure_member(data, verified_phone_canonical_uid)
                if verified_phone_canonical_uid
                else self._find_member_by_phone(data, normalized)
            )

            if target and target["user_id"] != current["user_id"]:
                merge = self._merge_member_accounts_locked(
                    data,
                    target_user_id=str(target["user_id"]),
                    source_user_ids=[str(current["user_id"])],
                    operator="wechat_mp",
                    reason="bind_phone_alias_merge" if verified_phone_canonical_uid else "bind_phone_merge",
                    action="wechat_bind_phone",
                    idempotency_key=f"{target['user_id']}:{current['user_id']}:{normalized}",
                )
                target = self._find_member(data, str(merge.get("target_user_id") or target["user_id"]))
                target["phone"] = normalized
                target["last_active_at"] = _iso()
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
            _bind_display = str(current.get("display_name") or "").strip()
            _bind_uid = str(current.get("user_id") or "").strip()
            if not _bind_display or _bind_display == _bind_uid:
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
        # 微信绑定手机后同步持久化到 Supabase
        self._persist_phone_identity(
            phone=normalized,
            canonical_uid=str(auth_identity.get("canonical_uid") or "").strip(),
        )
        # openid / unionid 持久化：canonical_uid 已确立后写入，
        # 使同一 WeChat Open Platform 下的跨产品登录可通过 unionid 直接命中同一身份。
        self._persist_wechat_openid_identity(
            openid=str(result.get("openid") or "").strip(),
            unionid=str(result.get("unionid") or "").strip(),
            canonical_uid=str(auth_identity.get("canonical_uid") or "").strip(),
        )
        return payload

    def send_phone_code(self, phone: str) -> dict[str, Any]:
        normalized = _normalize_phone_input(phone)
        if not normalized or not self._is_cn_mainland_mobile(normalized):
            raise ValueError("请输入有效的大陆手机号")
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
            # Never return the OTP in the HTTP response — a network-observable code is an
            # account-takeover primitive if the SMS gateway/env is ever misconfigured.
            # Surface it server-side only (debug log) for local/test visibility.
            if delivery != "sms":
                logger.debug("debug OTP for %s: %s (delivery=%s)", normalized, debug_code, delivery)
            return result

        return self._mutate(_apply)

    def send_password_reset_code(self, username: str, phone: str) -> dict[str, Any]:
        resolved = self._resolve_password_reset_account(username, phone)
        return self.send_phone_code(str(resolved["phone"]))

    def _persist_phone_identity(self, *, phone: str, canonical_uid: str) -> None:
        """把手机号持久化到 user_identity_aliases 和 users.phone，best-effort 不阻塞认证流程。"""
        if not phone or not canonical_uid or not is_uuid_like(canonical_uid):
            return
        if not self._is_cn_mainland_mobile(phone):
            logger.warning(
                "phone identity persist skipped: not a valid CN mainland mobile phone=%s canonical_uid=%s",
                phone[-4:] if len(phone) >= 4 else "****",
                canonical_uid,
            )
            return
        try:
            existing_alias_ids = self._trusted_phone_alias_user_ids(phone)
        except ValueError as exc:
            logger.warning(
                "phone identity persist skipped due to conflicting phone aliases: phone=%s canonical_uid=%s error=%s",
                phone[-4:] if len(phone) >= 4 else "****",
                canonical_uid,
                exc,
            )
            return
        if existing_alias_ids and canonical_uid not in existing_alias_ids:
            logger.warning(
                "phone identity persist skipped: phone=%s existing_canonical=%s requested_canonical=%s",
                phone[-4:] if len(phone) >= 4 else "****",
                ",".join(sorted(existing_alias_ids)),
                canonical_uid,
            )
            return
        db_url = str(os.getenv("DB_URL") or os.getenv("DATABASE_URL") or "").strip()
        if not db_url:
            logger.warning("phone identity persist skipped: DB_URL not configured")
            return
        try:
            try:
                import psycopg
                conn_ctx = psycopg.connect(db_url, connect_timeout=5)
            except ImportError:
                try:
                    import psycopg2
                    conn_ctx = psycopg2.connect(db_url, connect_timeout=5)
                except ImportError:
                    logger.warning("phone identity persist skipped: neither psycopg nor psycopg2 is installed")
                    return

            with conn_ctx as conn:
                cur = conn.cursor()
                # 仅创建缺失 alias 或刷新同一 canonical UUID 的已验证时间；
                # 并发冲突时不覆盖 owner。
                # user_identity_aliases.user_id 是 uuid 类型；users.id 是 text 类型，
                # 两者均存同一 UUID 字符串，psycopg 驱动会做隐式转换。
                cur.execute(
                    """
                    INSERT INTO public.user_identity_aliases
                        (alias_type, alias_value, user_id, source, confidence, verified_at)
                    VALUES (%s, %s, %s::uuid, %s, %s, now())
                    ON CONFLICT (alias_type, alias_value) DO UPDATE SET
                        confidence  = EXCLUDED.confidence,
                        verified_at = EXCLUDED.verified_at,
                        updated_at  = now()
                    WHERE public.user_identity_aliases.user_id = EXCLUDED.user_id
                    RETURNING user_id
                    """,
                    ("phone", phone, canonical_uid, "phone_verification", 1.0),
                )
                persisted = cur.fetchone()
                if not persisted:
                    logger.warning(
                        "phone identity persist skipped after concurrent owner conflict: phone=%s canonical_uid=%s",
                        phone[-4:] if len(phone) >= 4 else "****",
                        canonical_uid,
                    )
                    return
                # users.phone 只在空时写入，避免覆盖已有值
                cur.execute(
                    "UPDATE public.users SET phone = %s WHERE id = %s AND (phone IS NULL OR phone = '')",
                    (phone, canonical_uid),
                )
                # psycopg3 和 psycopg2 的 `with conn:` 均在 __exit__ 时自动 commit，
                # 此处不需要显式调用 conn.commit()。
        except Exception as exc:
            logger.warning(
                "phone identity persist failed: phone=%s canonical_uid=%s error=%s",
                phone[-4:] if len(phone) >= 4 else "****",
                canonical_uid,
                exc,
            )

    def _persist_wechat_openid_identity(
        self, *, openid: str, unionid: str, canonical_uid: str
    ) -> None:
        """把微信 openid / unionid 持久化到 user_identity_aliases，支持跨产品身份统一。

        写入时机：微信用户完成手机绑定后，canonical_uid 已确立。
        - openid  = 当前小程序维度唯一，跨产品不通用
        - unionid = WeChat Open Platform 账号维度唯一，跨产品关键 key

        写入后，同一微信用户在同一 Open Platform 下的其他小程序首次登录时，
        _auth_identity_for_member 会通过 wx_unionid alias 直接命中同一 canonical_uid，
        无需用户再次授权手机号。
        """
        if not openid or not canonical_uid or not is_uuid_like(canonical_uid):
            return
        db_url = str(os.getenv("DB_URL") or os.getenv("DATABASE_URL") or "").strip()
        if not db_url:
            logger.warning("wechat openid identity persist skipped: DB_URL not configured")
            return
        aliases: list[tuple[str, str]] = [("wx_openid", openid)]
        if unionid:
            aliases.append(("wx_unionid", unionid))
        try:
            try:
                import psycopg

                conn_ctx = psycopg.connect(db_url, connect_timeout=5)
            except ImportError:
                try:
                    import psycopg2

                    conn_ctx = psycopg2.connect(db_url, connect_timeout=5)
                except ImportError:
                    logger.warning("wechat openid identity persist skipped: no psycopg driver installed")
                    return
            with conn_ctx as conn:
                cur = conn.cursor()
                for alias_type, alias_value in aliases:
                    cur.execute(
                        """
                        INSERT INTO public.user_identity_aliases
                            (alias_type, alias_value, user_id, source, confidence, verified_at)
                        VALUES (%s, %s, %s::uuid, %s, %s, now())
                        ON CONFLICT (alias_type, alias_value) DO UPDATE SET
                            confidence  = EXCLUDED.confidence,
                            verified_at = EXCLUDED.verified_at,
                            updated_at  = now()
                        WHERE public.user_identity_aliases.user_id = EXCLUDED.user_id
                        RETURNING user_id
                        """,
                        (alias_type, alias_value, canonical_uid, "wechat_login", 1.0),
                    )
                    if cur.fetchone() is None:
                        logger.info(
                            "wechat openid alias not updated (concurrent owner conflict): "
                            "alias_type=%s canonical_uid=%s",
                            alias_type,
                            canonical_uid,
                        )
            logger.debug(
                "wechat openid identity persisted: openid_tail=%s unionid_tail=%s canonical_uid=%s",
                openid[-6:] if len(openid) >= 6 else "***",
                unionid[-6:] if unionid and len(unionid) >= 6 else "",
                canonical_uid,
            )
        except Exception as exc:
            logger.warning(
                "wechat openid identity persist failed: canonical_uid=%s error=%s",
                canonical_uid,
                exc,
            )

    def verify_phone_code(self, phone: str, code: str) -> dict[str, Any]:
        normalized = _normalize_phone_input(phone)
        if not normalized:
            raise ValueError("手机号格式不正确")
        provided_code = str(code or "").strip()
        canonical_uid = self._resolve_verified_phone_canonical_uid(normalized)

        # Brute-force lockout: a 6-digit OTP must not be guessable within its 10-min
        # TTL. Count wrong attempts per phone and invalidate the OTP after _MAX_OTP_ATTEMPTS,
        # forcing a fresh code. The counter is persisted via the mutation (we must NOT
        # raise inside _apply, or the increment rolls back), then we raise outside.
        def _apply(data: dict[str, Any]) -> dict[str, Any]:
            record = (data.get("phone_codes") or {}).get(normalized) or {}
            expected_code = str(record.get("code") or "").strip()
            expires_at = _parse_time(record.get("expires_at"))
            if not expected_code:
                return {"status": "missing"}
            if expires_at < _now():
                data.get("phone_codes", {}).pop(normalized, None)
                return {"status": "expired"}
            if provided_code != expected_code:
                attempts = int(record.get("attempts") or 0) + 1
                if attempts >= _MAX_OTP_ATTEMPTS:
                    data.get("phone_codes", {}).pop(normalized, None)
                    return {"status": "locked"}
                record["attempts"] = attempts
                data.setdefault("phone_codes", {})[normalized] = record
                return {"status": "wrong", "remaining": _MAX_OTP_ATTEMPTS - attempts}
            data.get("phone_codes", {}).pop(normalized, None)
            return {"status": "ok", "phone": normalized}

        outcome = self._mutate(_apply)
        status = str(outcome.get("status"))
        if status == "missing":
            raise ValueError("验证码不存在，请先获取验证码")
        if status == "expired":
            raise ValueError("验证码已过期，请重新获取")
        if status == "locked":
            raise ValueError("验证码错误次数过多，请重新获取验证码")
        if status != "ok":
            raise ValueError("验证码错误")
        verified_phone = str(outcome.get("phone") or normalized)
        if canonical_uid:
            def _apply_verified_alias(data: dict[str, Any]) -> dict[str, Any]:
                member = self._ensure_member(data, canonical_uid)
                current_phone = _normalize_phone_input(str(member.get("phone") or ""))
                synthetic_default_phone = _slugify_phone(str(member.get("user_id") or ""))
                if not current_phone or current_phone == synthetic_default_phone:
                    member["phone"] = verified_phone
                member["last_active_at"] = _iso()
                return deepcopy(member)

            member = self._mutate(_apply_verified_alias)
            auth_identity = self._auth_identity_for_member(str(member.get("user_id") or "").strip())
            token = self._issue_access_token(
                user_id=auth_identity["user_id"],
                canonical_uid=auth_identity["canonical_uid"],
            )
            return self._build_auth_response(user_id=auth_identity["user_id"], token=token)
        else:
            external_user = ensure_external_auth_user_for_phone(verified_phone)
            external_username = str(external_user.get("username") or "").strip()
            member = self._ensure_member_for_external_auth(external_username, external_user)
            auth_identity = self._auth_identity_for_member(str(member.get("user_id") or "").strip())
            token = self._issue_access_token(
                user_id=auth_identity["user_id"],
                canonical_uid=auth_identity["canonical_uid"],
            )
            # 手机号持久化到 Supabase（不影响认证主流程）
            self._persist_phone_identity(
                phone=verified_phone,
                canonical_uid=str(auth_identity.get("canonical_uid") or "").strip(),
            )
            return self._build_auth_response(user_id=auth_identity["user_id"], token=token)

    def reset_password_with_phone_code(
        self,
        username: str,
        phone: str,
        code: str,
        password: str,
    ) -> dict[str, Any]:
        resolved_account = self._resolve_password_reset_account(username, phone)
        normalized_phone = str(resolved_account["phone"])
        normalized_username = str(resolved_account["username"])
        normalized_password = str(password or "")
        validate_external_auth_password(normalized_password)

        provided_code = str(code or "").strip()

        # Same brute-force lockout as verify_phone_code: persist the wrong-attempt
        # counter inside the mutation (no raise), invalidate after _MAX_OTP_ATTEMPTS,
        # then raise outside.
        def _consume_verified_code(data: dict[str, Any]) -> dict[str, Any]:
            current = (data.get("phone_codes") or {}).get(normalized_phone) or {}
            expected_code = str(current.get("code") or "").strip()
            expires_at = _parse_time(current.get("expires_at"))
            if not expected_code:
                return {"status": "missing"}
            if expires_at < _now():
                data.get("phone_codes", {}).pop(normalized_phone, None)
                return {"status": "expired"}
            if provided_code != expected_code:
                attempts = int(current.get("attempts") or 0) + 1
                if attempts >= _MAX_OTP_ATTEMPTS:
                    data.get("phone_codes", {}).pop(normalized_phone, None)
                    return {"status": "locked"}
                current["attempts"] = attempts
                data.setdefault("phone_codes", {})[normalized_phone] = current
                return {"status": "wrong"}
            data.get("phone_codes", {}).pop(normalized_phone, None)
            return {"status": "ok"}

        outcome = self._mutate(_consume_verified_code)
        status = str(outcome.get("status"))
        if status == "missing":
            raise ValueError("验证码不存在，请先获取验证码")
        if status == "expired":
            raise ValueError("验证码已过期，请重新获取")
        if status == "locked":
            raise ValueError("验证码错误次数过多，请重新获取验证码")
        if status != "ok":
            raise ValueError("验证码错误")
        reset_result = reset_external_auth_password(
            normalized_username,
            normalized_password,
        )
        return {
            "success": True,
            "message": "密码已重置，请使用新密码登录",
            "sessions_invalidated": int(reset_result.get("sessions_invalidated") or 0),
        }

    def change_password(self, user_id: str, old_password: str, new_password: str) -> dict[str, Any]:
        member = self._load_member_snapshot(user_id)["member"]
        username = str(member.get("auth_username") or "").strip()
        if not username:
            raise ValueError("当前账号未绑定用户名密码登录")
        result = change_external_auth_password(username, old_password, new_password)
        return {
            "success": True,
            "message": "密码已修改，请使用新密码重新登录",
            "sessions_invalidated": int(result.get("sessions_invalidated") or 0),
        }


    def create_demo_token(self, user_id: str) -> str:
        return f"demo-token-{user_id}-{secrets.token_hex(4)}"


_instance: MemberConsoleService | None = None


def get_member_console_service() -> MemberConsoleService:
    global _instance
    if _instance is None:
        _instance = MemberConsoleService()
    return _instance
