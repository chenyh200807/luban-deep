#!/usr/bin/env python3
"""Learner Memory Lifecycle cohort soak artifact runner.

Default mode is hermetic: no network, no SSH, no remote write. It fixes the
artifact contract for the later test2 run so deployment evidence cannot depend
on ad-hoc shell transcripts.
"""
from __future__ import annotations

import asyncio
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
import websockets

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.deep_question_adapter import (  # noqa: E402
    build_deep_question_grading_result,
)
from deeptutor.services.construction_grading.learning_evidence import (  # noqa: E402
    build_learning_evidence_payload,
)
from deeptutor.services.learner_state.canonical_truth_policy import (  # noqa: E402
    canonical_truth_promotion_decision,
)
from deeptutor.services.learner_state.learning_brain_read_model import (  # noqa: E402
    build_learning_brain_read_model,
)
from deeptutor.services.learner_state.personalization_context import (  # noqa: E402
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.service import LearnerStateService  # noqa: E402

ARTIFACT_ROOT = REPO / "artifacts" / "luban_grading_artifacts"
G4_FLAG = "LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED"
G4_COHORT = "LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_COHORT"
BROAD_FLAG = "LUBAN_CANONICAL_LEARNER_TRUTH_BROAD_TRUSTED_ADJUDICATION_ENABLED"
REMOTE_COHORT_PREFIXES = ("qa_", "operator_")


class _PathServiceStub:
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def project_root(self) -> Path:
        return self._root

    def get_user_root(self) -> Path:
        return self._root / "data" / "user"

    def get_tutor_state_root(self) -> Path:
        return self.get_user_root() / "tutor_state"

    def get_learner_state_root(self) -> Path:
        return self.get_user_root() / "learner_state"

    def get_learner_state_outbox_db(self) -> Path:
        return self._root / "data" / "runtime" / "outbox.db"

    def get_guide_dir(self) -> Path:
        path = self.get_user_root() / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class _MemberServiceStub:
    def get_profile(self, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "display_name": user_id}

    def get_today_progress(self, _user_id: str) -> dict[str, Any]:
        return {}

    def get_chapter_progress(self, _user_id: str) -> list[dict[str, Any]]:
        return []


class _CoreStoreStub:
    is_configured = True

    def __init__(self) -> None:
        self.compiled: dict[str, dict[str, Any]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}

    def read_profile(self, _user_id: str) -> dict[str, Any]:
        return {}

    def write_profile(self, _user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        return dict(profile or {})

    def read_progress(self, _user_id: str) -> dict[str, Any]:
        return {}

    def write_progress(self, _user_id: str, progress: dict[str, Any]) -> dict[str, Any]:
        return dict(progress or {})

    def read_memory_events(self, user_id: str, limit: int | None = 20) -> list[dict[str, Any]]:
        rows = [dict(row) for row in self.events.get(user_id, [])]
        if limit is None or limit < 0:
            return rows
        return rows[-int(limit):]

    def write_compiled_learning_truth(self, user_id: str, projection: dict[str, Any]) -> dict[str, Any]:
        self.compiled[user_id] = {"learning_brain": dict(projection or {})}
        return dict(projection or {})

    def read_compiled_learning_truth(self, user_id: str) -> dict[str, Any]:
        return dict(self.compiled.get(user_id) or {})


@dataclass
class _EnvPatch:
    values: dict[str, str]
    _old: dict[str, str | None] | None = None

    def __enter__(self) -> None:
        self._old = {key: os.environ.get(key) for key in self.values}
        for key, value in self.values.items():
            os.environ[key] = value

    def __exit__(self, *_exc: object) -> None:
        for key, old in (self._old or {}).items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


@dataclass(frozen=True)
class _RemoteSoakScenario:
    scenario_id: str
    question_id: str
    question: str
    correct_answer: str
    initial_answer: str
    retest_answer: str
    testing_focus: str
    node_code: str = ""


_REMOTE_SCENARIOS: dict[str, _RemoteSoakScenario] = {
    "temporary-electricity-smoke": _RemoteSoakScenario(
        scenario_id="temporary-electricity-smoke",
        question_id="LM-LC-REMOTE-001",
        question="施工现场临时用电应采用几级配电？",
        correct_answer="三级配电",
        initial_answer="两级配电",
        retest_answer="三级配电",
        testing_focus="施工现场临时用电",
        node_code="1A431050",
    ),
    "construction-long-case": _RemoteSoakScenario(
        scenario_id="construction-long-case",
        question_id="LM-LC-REMOTE-LONG-001",
        question=(
            "某商品住宅项目，地下2层，地上12~18层，装配式剪力墙结构，总建筑面积8.4万平方米。"
            "施工总承包单位中标后组建项目部进场施工。项目部编制网络进度计划：1→2 A，2→4 D，"
            "4→6 E，6→8 H，1→3 B，3→7 F，7→8 I，1→4 C，4→7 G。施工中发生："
            "①设计变更使工作E延长2周；②施工机械故障使工作G延长1周。公司审核基坑专项施工方案发现："
            "灌注桩设计强度C20水下灌注提高一级；截水帷幕与排桩净距小于200mm且先截水帷幕后排桩；"
            "桩顶泛浆高度不大于300mm；内支撑拆除顺序按现场调整；项目部委托第三方基坑监测。"
            "资料表要求填写分部分项和检验批划分方案、分包资质报审表、施工日志、质量事故报告书、"
            "单位工程观感质量检查记录的责任部门。冬期方案包括C40/P6抗渗底板混凝土测温、低温型灌浆料。"
            "问题：答关键线路和A/F总时差、索赔成立性；改正基坑方案；填写资料责任部门；"
            "答抗渗混凝土受冻临界强度；答低温型灌浆料24h内灌浆部位温度和施工环境温度最低要求。"
        ),
        correct_answer=(
            "应按网络图和持续时间判定关键线路及总时差；设计变更导致关键工作延误时索赔成立，"
            "施工机械故障通常为承包人原因不成立。灌注桩混凝土强度不应低于C25，水下灌注应满足规范；"
            "排桩与截水帷幕顺序应按设计和相互影响确定，避免损伤已施工桩；桩顶泛浆高度不应小于500mm；"
            "内支撑拆除顺序应与设计工况一致；基坑监测应由建设单位委托有资质第三方。"
            "资料责任通常为技术、商务/经营、工程、质量、质量。抗渗混凝土受冻临界强度不宜低于设计强度50%。"
            "低温型灌浆料施工开始24h内灌浆部位温度不应低于-5℃，施工环境温度不应低于0℃。"
        ),
        initial_answer=(
            "1. 关键线路B→E→I；A总时差2周，F总时差3周。①索赔成立，②索赔不成立。"
            "2. 灌注桩强度不应低于C25；先施工灌注桩后施工截水帷幕；泛浆高度不小于500mm；"
            "支撑拆除顺序与设计工况一致；基坑监测由建设方委托第三方。"
            "3. A技术，B商务，C工程，D质量，E质量。4. 20MPa。"
            "5. 灌浆部位温度不低于-5℃，施工环境温度不低于0℃。"
        ),
        retest_answer=(
            "1. 根据网络图和持续时间重新计算关键线路及A、F总时差；设计变更属于发包人原因，"
            "若影响总工期则E延长索赔成立；施工机械故障属于承包人原因，G延长索赔不成立。"
            "2. 水下灌注桩混凝土强度等级不应低于C25；排桩和截水帷幕施工顺序应按设计及相互影响确定，"
            "不得损伤已成桩；灌注桩桩顶泛浆高度不应小于500mm；内支撑拆除应与设计工况一致；"
            "基坑监测应由建设单位委托有资质第三方。3. A技术，B商务，C工程，D质量，E质量。"
            "4. C40/P6抗渗混凝土受冻临界强度不低于设计强度50%，即20MPa。"
            "5. 低温型灌浆料施工开始24h内灌浆部位温度不低于-5℃，施工环境温度不低于0℃。"
        ),
        testing_focus="网络进度计划、基坑专项施工方案、工程资料、冬期灌浆",
    ),
}


def _remote_scenario(scenario_id: str) -> _RemoteSoakScenario:
    key = str(scenario_id or "").strip() or "temporary-electricity-smoke"
    if key not in _REMOTE_SCENARIOS:
        raise ValueError(f"unknown remote soak scenario: {key}")
    return _REMOTE_SCENARIOS[key]


def _scenario_from_answer_file(
    base: _RemoteSoakScenario,
    *,
    answer_file: Path | None,
    sample_id: str = "",
) -> _RemoteSoakScenario:
    if answer_file is None:
        return base
    resolved_sample_id = str(sample_id or "").strip()
    if not resolved_sample_id:
        raise ValueError("--sample-id is required when --answer-file is provided")
    text = answer_file.read_text(encoding="utf-8")
    block = _sample_block(text, resolved_sample_id)
    question = _markdown_subsection(block, "题目", "回答")
    answer = _markdown_subsection(block, "回答", "本题水平判断")
    if not question or not answer:
        raise ValueError(f"sample {resolved_sample_id} is missing question or answer sections")
    return _RemoteSoakScenario(
        scenario_id=f"{base.scenario_id}:answer-file:{resolved_sample_id}",
        question_id=resolved_sample_id,
        question=_compact_markdown_payload(question),
        correct_answer=base.correct_answer,
        initial_answer=_compact_markdown_payload(answer),
        retest_answer=_compact_markdown_payload(answer),
        testing_focus=base.testing_focus,
        node_code=base.node_code,
    )


def _sample_block(text: str, sample_id: str) -> str:
    marker = f"样本ID：`{sample_id}`"
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"sample id not found in answer file: {sample_id}")
    header = text.rfind("\n### ", 0, start)
    block_start = header if header >= 0 else start
    next_header = text.find("\n### ", start + len(marker))
    return text[block_start:] if next_header < 0 else text[block_start:next_header]


def _markdown_subsection(block: str, heading: str, next_heading: str) -> str:
    pattern = rf"#### {re.escape(heading)}\n(?P<body>.*?)(?:\n#### {re.escape(next_heading)}\n|\Z)"
    match = re.search(pattern, block, flags=re.DOTALL)
    if not match:
        return ""
    body = match.group("body")
    return body.strip()


def _compact_markdown_payload(value: str, *, limit: int = 12000) -> str:
    text = re.sub(r"\n{3,}", "\n\n", str(value or "").strip())
    return text[:limit].strip()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _build_ws_url(api_base_url: str) -> str:
    parsed = urlparse(str(api_base_url or "").rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/") + "/api/v1/ws"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


async def _request_json(
    client: Any,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    response = await client.request(
        method,
        path,
        headers=headers,
        json=json_body,
        params=params,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {"raw_text": getattr(response, "text", "")}
    return int(getattr(response, "status_code", 0) or 0), dict(payload if isinstance(payload, dict) else {})


def _remote_soak_credentials(prefix: str = "qa_lifecycle_soak") -> tuple[str, str, str]:
    stamp = int(time.time())
    username = f"{prefix}_{stamp}"
    password = f"SoakA{stamp % 1000000:06d}"
    phone = f"138{stamp % 100000000:08d}"
    return username, password, phone


def _cohort_allowed(user_id: str, prefixes: tuple[str, ...] = REMOTE_COHORT_PREFIXES) -> bool:
    normalized = str(user_id or "").strip()
    return bool(normalized) and any(normalized.startswith(prefix) for prefix in prefixes)


def _identity_candidates(auth_payload: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    def _append(value: Any) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    for source in (profile, auth_payload):
        if not isinstance(source, dict):
            continue
        for key in ("user_id", "id", "username", "auth_username"):
            _append(source.get(key))
        user = source.get("user")
        if isinstance(user, dict):
            for key in ("user_id", "id", "username", "auth_username"):
                _append(user.get(key))
    return candidates


def _cohort_allowed_identity(auth_payload: dict[str, Any], profile: dict[str, Any]) -> str:
    for candidate in _identity_candidates(auth_payload, profile):
        if _cohort_allowed(candidate):
            return candidate
    return ""


def _sanitize_auth_detail(detail: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(detail or {})
    for key in ("token", "auth_token", "password"):
        if key in redacted:
            redacted[key] = "[redacted]"
    for nested_key in ("payload", "auth_payload"):
        nested = redacted.get(nested_key)
        if isinstance(nested, dict) and "token" in nested:
            nested = dict(nested)
            nested["token"] = "[redacted]"
            redacted[nested_key] = nested
    headers = redacted.get("headers")
    if isinstance(headers, dict) and "Authorization" in headers:
        headers = dict(headers)
        headers["Authorization"] = "Bearer [redacted]"
        redacted["headers"] = headers
    return redacted


async def _remote_authenticate(
    client: Any,
    *,
    auth_token: str = "",
    username: str = "",
    password: str = "",
    phone: str = "",
    register: bool = False,
) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    created_user = False
    auth_payload: dict[str, Any] = {}
    if not token:
        if register:
            status_code, payload = await _request_json(
                client,
                "POST",
                "/api/v1/auth/register",
                json_body={"username": username, "password": password, "phone": phone},
            )
            if status_code == 200:
                auth_payload = payload
                token = str(payload.get("token") or "").strip()
                created_user = True
            elif status_code != 400:
                return {
                    "ok": False,
                    "reason": "register_failed",
                    "status_code": status_code,
                    "payload": payload,
                }
        if not token:
            status_code, payload = await _request_json(
                client,
                "POST",
                "/api/v1/auth/login",
                json_body={"username": username, "password": password},
            )
            if status_code != 200:
                return {
                    "ok": False,
                    "reason": "login_failed",
                    "status_code": status_code,
                    "payload": payload,
                }
            auth_payload = payload
            token = str(payload.get("token") or "").strip()
    if not token:
        return {"ok": False, "reason": "auth_token_missing", "payload": auth_payload}
    headers = {"Authorization": f"Bearer {token}"}
    status_code, profile = await _request_json(client, "GET", "/api/v1/auth/profile", headers=headers)
    if status_code != 200:
        return {
            "ok": False,
            "reason": "profile_failed",
            "status_code": status_code,
            "payload": profile,
        }
    user_id = str(profile.get("user_id") or profile.get("id") or auth_payload.get("user_id") or "").strip()
    if not user_id:
        return {"ok": False, "reason": "profile_user_id_missing", "payload": profile}
    return {
        "ok": True,
        "token": token,
        "headers": headers,
        "user_id": user_id,
        "cohort_identity": _cohort_allowed_identity(auth_payload, profile),
        "identity_candidates": _identity_candidates(auth_payload, profile),
        "profile": profile,
        "created_user": created_user,
        "auth_payload": auth_payload,
    }


def _remote_ws_frame(*, content: str, scenario: _RemoteSoakScenario, loop_id: str) -> dict[str, Any]:
    context: dict[str, Any] = {
        "question_id": scenario.question_id,
        "question_type": "case",
        "question": scenario.question,
        "correct_answer": scenario.correct_answer,
        "user_answer": content,
        "testing_focus": scenario.testing_focus,
    }
    if scenario.node_code:
        context["node_code"] = scenario.node_code
    return {
        "type": "start_turn",
        "content": content,
        "capability": "deep_question",
        "language": "zh",
        "config": {
            "followup_question_context": context,
        },
    }


async def _run_remote_ws_turn(
    *,
    ws_url: str,
    token: str,
    frame: dict[str, Any],
    timeout_seconds: float,
    connector_factory: Any | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    connect = connector_factory or websockets.connect
    events: list[dict[str, Any]] = []
    terminal: dict[str, Any] | None = None
    result_event: dict[str, Any] | None = None
    async with connect(ws_url, additional_headers=headers) as websocket:
        await websocket.send(json.dumps(frame, ensure_ascii=False))
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
            event = json.loads(raw)
            if not isinstance(event, dict):
                continue
            events.append(event)
            event_type = str(event.get("type") or "").strip()
            if event_type == "result":
                result_event = event
            if event_type in {"done", "error"}:
                terminal = event
                break
    metadata = result_event.get("metadata") if isinstance(result_event, dict) else {}
    return {
        "frame": frame,
        "events": events,
        "terminal_event": terminal or {},
        "result_event": result_event or {},
        "construction_grading_result": dict(metadata.get("construction_grading_result") or {})
        if isinstance(metadata, dict)
        else {},
    }


def _projection_hash(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    run = payload.get("synthesis_run") if isinstance(payload.get("synthesis_run"), dict) else {}
    value = str(run.get("output_projection_hash") or "").strip()
    if value:
        return value
    brain = payload.get("learning_brain") if isinstance(payload.get("learning_brain"), dict) else {}
    run = brain.get("synthesis_run") if isinstance(brain.get("synthesis_run"), dict) else {}
    return str(run.get("output_projection_hash") or "").strip()


async def _read_remote_readbacks(
    client: Any,
    *,
    headers: dict[str, str],
    poll_attempts: int,
    poll_interval_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    brain: dict[str, Any] = {}
    report: dict[str, Any] = {}
    attempts = max(1, int(poll_attempts or 1))
    for attempt in range(attempts):
        status_code, brain_payload = await _request_json(
            client,
            "GET",
            "/api/v1/learning-brain/projection",
            headers=headers,
            params={"event_limit": 100},
        )
        brain = brain_payload if status_code == 200 else {"readback_error": brain_payload, "status_code": status_code}
        status_code, report_payload = await _request_json(
            client,
            "GET",
            "/api/v1/mobile/learning-report",
            headers=headers,
            params={"schema_version": 2, "event_limit": 100},
        )
        report = report_payload if status_code == 200 else {"readback_error": report_payload, "status_code": status_code}
        if _projection_hash(brain) and _projection_hash(brain) == _projection_hash(report):
            break
        if attempt + 1 < attempts:
            await asyncio.sleep(max(0.0, float(poll_interval_seconds or 0.0)))
    return brain, report


def _trigger_remote_synthesis_via_ssh(
    *,
    user_id: str,
    ssh_host: str,
    project_root: str = "/root/deeptutor",
    container_name: str = "deeptutor",
    timeout_seconds: float = 90.0,
) -> dict[str, Any]:
    normalized_user_id = str(user_id or "").strip()
    normalized_host = str(ssh_host or "").strip()
    normalized_root = str(project_root or "").strip() or "/root/deeptutor"
    normalized_container = str(container_name or "").strip() or "deeptutor"
    if not normalized_host:
        return {"triggered": False, "reason": "ssh_host_not_configured"}
    if not _cohort_allowed(normalized_user_id):
        return {
            "triggered": False,
            "reason": "canonical_user_not_cohort",
            "user_id": normalized_user_id,
        }
    code = (
        "import json; "
        "from deeptutor.services.learner_state import get_learner_state_service; "
        f"uid={normalized_user_id!r}; "
        "svc=get_learner_state_service(); "
        "res=svc.synthesize_learning_truth(uid, dry_run=False, event_limit=100); "
        "proj=res.get('projection') or {}; "
        "read=svc.read_compiled_learning_truth(uid); "
        "print(json.dumps({"
        "'canonical_truth_promotion': res.get('canonical_truth_promotion', {}), "
        "'projection_hash': (proj.get('synthesis_run') or {}).get('output_projection_hash', ''), "
        "'readback_hash': (read.get('synthesis_run') or {}).get('output_projection_hash', ''), "
        "'readback_event_count': (read.get('synthesis_run') or {}).get('input_event_count', 0)"
        "}, ensure_ascii=False, sort_keys=True))"
    )
    remote_cmd = (
        f"cd {shlex.quote(normalized_root)} && "
        f"docker exec {shlex.quote(normalized_container)} python -c {shlex.quote(code)}"
    )
    completed = subprocess.run(
        ["ssh", normalized_host, remote_cmd],
        check=False,
        capture_output=True,
        text=True,
        timeout=max(5.0, float(timeout_seconds or 90.0)),
    )
    payload: dict[str, Any] = {}
    for line in reversed([line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]):
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payload = parsed
            break
    return {
        "triggered": completed.returncode == 0 and bool(payload),
        "returncode": completed.returncode,
        "payload": payload,
        "stderr_tail": (completed.stderr or "")[-600:],
    }


def _remote_blocked_result(
    *,
    out: Path,
    run_id: str,
    reason: str,
    api_base_url: str,
    user_id: str = "",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = {
        "run_id": run_id,
        "mode": "remote-test2-ws",
        "entry": "remote test2 /api/v1/ws cohort loop soak",
        "api_base_url": str(api_base_url or "").rstrip("/"),
        "evidence_scope": "remote_test2_ws_cohort_soak",
        "remote_write_performed": False,
        "cohort_user_id": user_id,
        "required_cohort_prefixes": list(REMOTE_COHORT_PREFIXES),
        "stage_chain": [],
    }
    go_no_go = {
        "status": "REMOTE_AUTH_BLOCKED",
        "reason": reason,
        "user_id": user_id,
        "detail": dict(detail or {}),
        "remote_write_performed": False,
    }
    _write_json(out / "manifest.json", manifest)
    _write_json(out / "go_no_go.json", go_no_go)
    return {"out_dir": str(out), "manifest": manifest, "go_no_go": go_no_go}


async def run_remote_test2_ws_soak(
    *,
    api_base_url: str = "https://test2.yousenjiaoyu.com",
    auth_token: str = "",
    username: str = "",
    password: str = "",
    phone: str = "",
    register: bool = False,
    out_dir: Path | None = None,
    timeout_seconds: float = 90.0,
    poll_attempts: int = 12,
    poll_interval_seconds: float = 5.0,
    remote_synthesis_ssh_host: str = "",
    remote_synthesis_project_root: str = "/root/deeptutor",
    remote_synthesis_container: str = "deeptutor",
    scenario_id: str = "temporary-electricity-smoke",
    answer_file: Path | None = None,
    sample_id: str = "",
    client_factory: Any | None = None,
    connector_factory: Any | None = None,
) -> dict[str, Any]:
    run_id = f"learner_memory_lifecycle_remote_{int(time.time())}"
    out = out_dir or ARTIFACT_ROOT / run_id
    out.mkdir(parents=True, exist_ok=True)
    normalized_base = str(api_base_url or "").rstrip("/")
    scenario = _scenario_from_answer_file(
        _remote_scenario(scenario_id),
        answer_file=answer_file,
        sample_id=sample_id,
    )
    if register and (not username or not password or not phone):
        username, password, phone = _remote_soak_credentials()
    client_builder = client_factory or httpx.AsyncClient
    async with client_builder(base_url=normalized_base, timeout=timeout_seconds, trust_env=False) as client:
        auth = await _remote_authenticate(
            client,
            auth_token=auth_token,
            username=username,
            password=password,
            phone=phone,
            register=register,
        )
        if not auth.get("ok"):
            return _remote_blocked_result(
                out=out,
                run_id=run_id,
                reason=str(auth.get("reason") or "auth_failed"),
                api_base_url=normalized_base,
                detail=_sanitize_auth_detail(auth),
            )
        user_id = str(auth.get("user_id") or "").strip()
        cohort_identity = str(auth.get("cohort_identity") or "").strip()
        if not cohort_identity:
            return _remote_blocked_result(
                out=out,
                run_id=run_id,
                reason="cohort_user_required",
                api_base_url=normalized_base,
                user_id=user_id,
                detail={
                    "profile": auth.get("profile") or {},
                    "identity_candidates": list(auth.get("identity_candidates") or []),
                },
            )
        token = str(auth.get("token") or "").strip()
        headers = dict(auth.get("headers") or {})
        ws_url = _build_ws_url(normalized_base)
        loop_id = f"{run_id}:test2-ws-cohort-loop"
        initial = await _run_remote_ws_turn(
            ws_url=ws_url,
            token=token,
            frame=_remote_ws_frame(
                content=scenario.initial_answer,
                scenario=scenario,
                loop_id=loop_id,
            ),
            timeout_seconds=timeout_seconds,
            connector_factory=connector_factory,
        )
        retest = await _run_remote_ws_turn(
            ws_url=ws_url,
            token=token,
            frame=_remote_ws_frame(
                content=scenario.retest_answer,
                scenario=scenario,
                loop_id=loop_id,
            ),
            timeout_seconds=timeout_seconds,
            connector_factory=connector_factory,
        )
        remote_synthesis = (
            _trigger_remote_synthesis_via_ssh(
                user_id=user_id,
                ssh_host=remote_synthesis_ssh_host,
                project_root=remote_synthesis_project_root,
                container_name=remote_synthesis_container,
                timeout_seconds=timeout_seconds,
            )
            if remote_synthesis_ssh_host
            else {"triggered": False, "reason": "not_requested"}
        )
        brain, report = await _read_remote_readbacks(
            client,
            headers=headers,
            poll_attempts=poll_attempts,
            poll_interval_seconds=poll_interval_seconds,
        )

    brain_hash = _projection_hash(brain)
    report_hash = _projection_hash(report)
    ws_grading_ok = bool(initial.get("construction_grading_result")) and bool(retest.get("construction_grading_result"))
    same_hash = bool(brain_hash and brain_hash == report_hash)
    status = "REMOTE_TEST2_WS_GO" if ws_grading_ok and same_hash else "REMOTE_TEST2_WS_READBACK_PENDING"
    manifest = {
        "run_id": run_id,
        "mode": "remote-test2-ws",
        "entry": "remote test2 /api/v1/ws cohort loop soak",
        "api_base_url": normalized_base,
        "ws_url": ws_url,
        "evidence_scope": "remote_test2_ws_cohort_soak",
        "remote_write_performed": same_hash,
        "scenario_id": scenario.scenario_id,
        "question_id": scenario.question_id,
        "testing_focus": scenario.testing_focus,
        "answer_file": str(answer_file) if answer_file else "",
        "sample_id": sample_id,
        "cohort_user_id": user_id,
        "cohort_identity": cohort_identity,
        "required_cohort_prefixes": list(REMOTE_COHORT_PREFIXES),
        "loop_id": loop_id,
        "remote_synthesis": remote_synthesis,
        "stage_chain": [
            "remote_api_ws",
            "grading",
            "learning_evidence",
            "remote_synthesis_trigger" if remote_synthesis.get("triggered") else "remote_synthesis_skipped",
            "learning_brain_projection_readback",
            "learning_report_readback",
        ],
    }
    go_no_go = {
        "status": status,
        "remote_write_performed": same_hash,
        "ws_grading_ok": ws_grading_ok,
        "learning_brain_projection_hash": brain_hash,
        "learning_report_projection_hash": report_hash,
        "same_projection_hash": same_hash,
        "cohort_user_id": user_id,
        "cohort_identity": cohort_identity,
        "initial_terminal_type": (initial.get("terminal_event") or {}).get("type"),
        "retest_terminal_type": (retest.get("terminal_event") or {}).get("type"),
        "initial_has_construction_grading_result": bool(initial.get("construction_grading_result")),
        "retest_has_construction_grading_result": bool(retest.get("construction_grading_result")),
        "remote_synthesis": remote_synthesis,
    }
    _write_json(out / "manifest.json", manifest)
    _write_json(out / "remote_ws_events.json", {"initial": initial, "retest": retest})
    _write_json(out / "remote_synthesis.json", remote_synthesis)
    _write_json(out / "learning_brain_readback.json", brain)
    _write_json(out / "learning_report_readback.json", report)
    _write_json(out / "go_no_go.json", go_no_go)
    return {"out_dir": str(out), "manifest": manifest, "go_no_go": go_no_go}


def _certified_policy() -> dict[str, Any]:
    return {
        "status": "published",
        "policy_id": "learner-memory-lifecycle-objective-v1",
        "rubric_hash": "sha256:learner-memory-lifecycle-rubric",
        "grader_version": "objective-grader-v1",
        "confidence": 0.94,
        "conflict_status": "resolved",
    }


def _question_context(question_id: str) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "question_type": "single_choice",
        "question": "临时用电应采用几级配电？",
        "options": [{"key": "A", "value": "三级"}, {"key": "B", "value": "两级"}],
        "answer_key": "A",
        "correct_answer": "A",
        "node_code": "1A432000",
        "testing_focus": "施工现场临时用电",
    }


def _append_certified_answer_event(
    service: LearnerStateService,
    *,
    user_id: str,
    loop_id: str,
    question_id: str,
    turn_id: str,
) -> Any:
    grading_result = build_deep_question_grading_result(
        _question_context(question_id),
        user_answer="B",
        governed_registry_status="published",
        certified_grading_policy=_certified_policy(),
    )
    if not grading_result:
        raise RuntimeError("grading_result_missing")
    payload = build_learning_evidence_payload(
        grading_result=grading_result,
        turn_id=turn_id,
        session_id=loop_id,
        governed_certified_authority=True,
    )
    payload["loop_id"] = loop_id
    return service.append_memory_event(
        user_id,
        source_feature="construction_grading",
        source_id=turn_id,
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        payload_json=payload,
        dedupe_key=f"{loop_id}:{turn_id}",
    )


def run_soak(*, out_dir: Path | None = None, mode: str = "local-core-store") -> dict[str, Any]:
    if mode != "local-core-store":
        raise ValueError("only local-core-store is supported by this checked-in runner")
    run_id = f"learner_memory_lifecycle_{int(time.time())}"
    out = out_dir or ARTIFACT_ROOT / run_id
    core_store = _CoreStoreStub()
    service = LearnerStateService(
        path_service=_PathServiceStub(out),
        member_service=_MemberServiceStub(),
        core_store=core_store,
    )
    user_id = "qa_learner_memory_lifecycle_soak"
    blocked_user_id = "real_student_lifecycle_soak"
    loop_id = f"{run_id}:cohort-loop"

    with _EnvPatch({
        "DEEPTUTOR_ENV": "production",
        G4_FLAG: "1",
        G4_COHORT: "qa_,operator_",
        BROAD_FLAG: "0",
    }):
        initial = _append_certified_answer_event(
            service,
            user_id=user_id,
            loop_id=loop_id,
            question_id="LM-LC-001",
            turn_id=f"{loop_id}:initial",
        )
        retest = _append_certified_answer_event(
            service,
            user_id=user_id,
            loop_id=loop_id,
            question_id="LM-LC-001-RETEST",
            turn_id=f"{loop_id}:retest",
        )
        synthesis = service.synthesize_learning_truth(user_id, dry_run=False)
        projection = synthesis["projection"]
        readback = service.read_compiled_learning_truth(user_id)
        output_hash = dict(projection.get("synthesis_run") or {}).get("output_projection_hash")
        readback_hash = dict(readback.get("synthesis_run") or {}).get("output_projection_hash")
        pcp = build_personalization_context_pack(
            user_id=user_id,
            learning_brain=projection,
            active_training_intent=None,
            recent_events=service.list_memory_events(user_id, limit=None),
        )
        nba = (pcp.get("next_best_action_candidates") or [{}])[0]
        brain_readback = build_learning_brain_read_model(user_id=user_id, projection=readback, surface="qa")
        blocked_decision = canonical_truth_promotion_decision(
            user_id=blocked_user_id,
            projection=projection,
        )

    event_rows = [
        {
            "event_id": event.event_id,
            "source_feature": event.source_feature,
            "source_id": event.source_id,
            "memory_kind": event.memory_kind,
            "memory_lifecycle_stage": event.payload_json.get("memory_lifecycle_stage"),
            "evidence_level": dict(event.payload_json.get("quality") or {}).get("evidence_level"),
            "trusted_adjudication": dict(event.payload_json.get("quality") or {}).get("trusted_adjudication"),
        }
        for event in service.list_memory_events(user_id, limit=None)
    ]
    manifest = {
        "run_id": run_id,
        "mode": mode,
        "entry": "local core-store artifact contract; remote test2 /api/v1/ws execution pending",
        "evidence_scope": "local_core_store_artifact_contract",
        "remote_write_performed": False,
        "remote_write_root_if_authorized": "/root/deeptutor",
        "cohort_user_id": user_id,
        "blocked_user_id": blocked_user_id,
        "loop_id": loop_id,
        "stage_chain": [
            "grading",
            "learning_evidence",
            "stable_claim",
            "PersonalizationContextPack",
            "NextBestAction",
            "retest",
            "certified_trusted_adjudication",
            "local_canonical_write",
            "local_canonical_readback",
        ],
    }
    go_no_go = {
        "status": "LOCAL_ARTIFACT_GO" if output_hash and output_hash == readback_hash and event_rows else "LOCAL_ARTIFACT_NO_GO",
        "learning_evidence_event_ids": [initial.event_id, retest.event_id],
        "output_projection_hash": output_hash,
        "canonical_readback_hash": readback_hash,
        "same_projection_hash": bool(output_hash and output_hash == readback_hash),
        "canonical_truth_promotion": synthesis.get("canonical_truth_promotion"),
        "blocked_non_cohort_decision": blocked_decision.to_dict(),
        "trusted_source": dict(projection.get("synthesis_run") or {}).get("trusted_adjudication", {}).get("source"),
        "pcp_source": pcp.get("source"),
        "next_best_action_id": nba.get("action_id"),
        "weak_point_count": len(projection.get("weak_points") or []),
        "observed_candidate_count": len(projection.get("observed_candidates") or []),
        "remote_write_performed": False,
    }

    _write_json(out / "manifest.json", manifest)
    _write_jsonl(out / "events.jsonl", event_rows)
    _write_json(out / "projection.json", projection)
    _write_json(out / "canonical_readback.json", readback)
    _write_json(out / "personalization_context_pack.json", pcp)
    _write_json(out / "next_best_action.json", nba)
    _write_json(out / "learning_brain_readback.json", brain_readback)
    _write_json(out / "go_no_go.json", go_no_go)
    return {"out_dir": str(out), "manifest": manifest, "go_no_go": go_no_go}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="local-core-store", choices=["local-core-store", "remote-test2-ws"])
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--api-base-url", default=os.getenv("TEST2_BASE_URL") or "https://test2.yousenjiaoyu.com")
    parser.add_argument("--auth-token", default=os.getenv("DEEPTUTOR_TEST2_COHORT_AUTH_TOKEN") or "")
    parser.add_argument("--username", default=os.getenv("DEEPTUTOR_TEST2_COHORT_USERNAME") or "")
    parser.add_argument("--password", default=os.getenv("DEEPTUTOR_TEST2_COHORT_PASSWORD") or "")
    parser.add_argument("--phone", default=os.getenv("DEEPTUTOR_TEST2_COHORT_PHONE") or "")
    parser.add_argument("--register", action="store_true")
    parser.add_argument(
        "--scenario",
        default=os.getenv("DEEPTUTOR_TEST2_SOAK_SCENARIO") or "temporary-electricity-smoke",
        choices=sorted(_REMOTE_SCENARIOS),
    )
    parser.add_argument("--answer-file", type=Path, default=None)
    parser.add_argument("--sample-id", default=os.getenv("DEEPTUTOR_TEST2_SOAK_SAMPLE_ID") or "")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--poll-attempts", type=int, default=12)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--remote-synthesis-ssh-host", default=os.getenv("DEEPTUTOR_TEST2_SYNTHESIS_SSH_HOST") or "")
    parser.add_argument(
        "--remote-synthesis-project-root",
        default=os.getenv("DEEPTUTOR_TEST2_SYNTHESIS_PROJECT_ROOT") or "/root/deeptutor",
    )
    parser.add_argument(
        "--remote-synthesis-container",
        default=os.getenv("DEEPTUTOR_TEST2_SYNTHESIS_CONTAINER") or "deeptutor",
    )
    args = parser.parse_args()
    if args.mode == "remote-test2-ws":
        result = asyncio.run(
            run_remote_test2_ws_soak(
                api_base_url=args.api_base_url,
                auth_token=args.auth_token,
                username=args.username,
                password=args.password,
                phone=args.phone,
                register=args.register,
                out_dir=args.out_dir,
                timeout_seconds=args.timeout_seconds,
                poll_attempts=args.poll_attempts,
                poll_interval_seconds=args.poll_interval_seconds,
                remote_synthesis_ssh_host=args.remote_synthesis_ssh_host,
                remote_synthesis_project_root=args.remote_synthesis_project_root,
                remote_synthesis_container=args.remote_synthesis_container,
                scenario_id=args.scenario,
                answer_file=args.answer_file,
                sample_id=args.sample_id,
            )
        )
    else:
        result = run_soak(out_dir=args.out_dir, mode=args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["go_no_go"]["status"] in {"LOCAL_ARTIFACT_GO", "REMOTE_TEST2_WS_GO"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
