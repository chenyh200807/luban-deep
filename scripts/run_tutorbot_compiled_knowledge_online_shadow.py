#!/usr/bin/env python3
"""Online TutorBot RAG-only vs RAG+compiled shadow evaluation.

Runs real HTTP start-turn + /api/v1/ws pairs. It is read-only from the server's
perspective: no canonical truth writes, no production-default change.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import websockets
from websockets.exceptions import WebSocketException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_mobile_login_smoke import _build_ws_url, _register_or_login, _request_json

REPO = PROJECT_ROOT
DEFAULT_OUT = REPO / "artifacts" / "qa" / f"tutorbot-compiled-knowledge-shadow-{time.strftime('%Y%m%d-%H%M%S')}"
SOURCE_KEYS = ("textbook", "standard", "lecture", "question")
RECOVERABLE_HTTP_STATUSES = {408, 429}
RECOVERABLE_SHADOW_ERRORS = (
    asyncio.TimeoutError,
    httpx.TimeoutException,
    httpx.TransportError,
    WebSocketException,
    json.JSONDecodeError,
)


class ShadowRecoverableServiceError(RuntimeError):
    """Server-side shadow turn failure that should not abort the whole batch."""


RECOVERABLE_SHADOW_EXCEPTION_TYPES = RECOVERABLE_SHADOW_ERRORS + (
    ShadowRecoverableServiceError,
)


@dataclass(frozen=True, slots=True)
class ShadowCase:
    case_id: str
    query: str
    expected: str
    path_terms: tuple[str, ...] = ()
    answer_terms: tuple[str, ...] = ()


DEFAULT_CASES: tuple[ShadowCase, ...] = (
    ShadowCase("hit_001", "高层住宅的建筑高度是怎么界定的？", "hit", ("高层住宅",), ("27m", "高层")),
    ShadowCase("hit_002", "施工现场临时用电三级配电是什么意思？", "hit", ("临时用电",), ("总配电箱", "分配电箱", "开关箱")),
    ShadowCase("hit_003", "混凝土施工缝应该怎么留置？", "hit", ("施工缝",), ("施工缝", "留置")),
    ShadowCase("hit_004", "土方回填压实系数怎么控制？", "hit", ("土方回填",), ("回填", "压实")),
    ShadowCase("hit_005", "泥浆护壁灌注桩常见质量问题有哪些？", "hit", ("灌注桩",), ("泥浆", "灌注桩")),
    ShadowCase("hit_006", "施工合同索赔成立条件是什么？", "hit", ("索赔",), ("索赔", "合同")),
    ShadowCase("hit_007", "脚手架连墙件设置有什么要求？", "hit", ("连墙件",), ("连墙件", "脚手架")),
    ShadowCase("hit_008", "屋面防水等级怎么区分？", "hit", ("屋面", "防水"), ("屋面", "防水")),
    ShadowCase("open_009", "建筑防火分区面积怎么理解？", "open", ("防火分区",), ("防火分区",)),
    ShadowCase("open_010", "建筑耐火等级怎么划分？", "open", ("耐火等级",), ("耐火",)),
    ShadowCase("open_011", "双代号网络计划总时差怎么算？", "open", ("总时差",), ("总时差",)),
    ShadowCase("open_012", "砌体结构拉结筋有什么要求？", "open", ("拉结筋",), ("拉结筋",)),
    ShadowCase("open_013", "模板起拱什么时候需要？", "open", ("模板起拱",), ("起拱",)),
    ShadowCase("open_014", "临边洞口防护怎么做？", "open", ("临边", "洞口"), ("临边", "洞口")),
    ShadowCase("open_015", "高强螺栓摩擦面处理要点是什么？", "open", ("高强螺栓",), ("高强螺栓",)),
    ShadowCase("open_016", "抹灰空鼓开裂怎么预防？", "open", ("抹灰",), ("空鼓", "开裂")),
    ShadowCase("open_017", "外墙保温施工有哪些质量控制点？", "open", ("外墙保温",), ("保温",)),
    ShadowCase("open_018", "分部工程质量验收谁组织？", "open", ("分部工程", "验收"), ("验收",)),
    ShadowCase("open_019", "建筑幕墙防火封堵有什么要求？", "open", ("幕墙", "防火"), ("幕墙", "防火")),
    ShadowCase("open_020", "绿色施工四节一环保分别是什么？", "open", ("绿色施工",), ("节能", "环保")),
    ShadowCase("off_021", "今天天气怎么样随便聊聊", "open"),
    ShadowCase("off_022", "帮我写一首关于咖啡的诗", "open"),
    ShadowCase("off_023", "NBA昨天谁赢了", "open"),
    ShadowCase("off_024", "Python列表怎么排序", "open"),
    ShadowCase("off_025", "上海明天会不会下雨", "open"),
    ShadowCase("hit_026", "高层建筑和多层建筑按高度怎么区分？", "hit", ("高层",), ("高层", "高度")),
    ShadowCase("hit_027", "施工缝和后浇带有什么区别？", "hit", ("施工缝",), ("施工缝",)),
    ShadowCase("hit_028", "土方回填分层压实要注意什么？", "hit", ("土方回填",), ("分层", "压实")),
    ShadowCase("hit_029", "临时用电为什么要一机一闸一漏一箱？", "hit", ("临时用电",), ("一机", "一闸")),
    ShadowCase("hit_030", "索赔证据一般包括哪些？", "hit", ("索赔",), ("索赔", "证据")),
    ShadowCase("open_031", "防火卷帘能不能替代防火墙？", "open", ("防火卷帘",), ("防火卷帘",)),
    ShadowCase("open_032", "钢筋保护层厚度怎么确定？", "open", ("保护层",), ("保护层",)),
    ShadowCase("open_033", "大体积混凝土温控有哪些要点？", "open", ("大体积混凝土",), ("温控",)),
    ShadowCase("open_034", "混凝土强度等级 C30 是什么意思？", "open", ("混凝土强度",), ("C30",)),
    ShadowCase("open_035", "水泥初凝和终凝时间怎么理解？", "open", ("凝结时间",), ("初凝", "终凝")),
    ShadowCase("open_036", "地下防水等级一级和二级有什么区别？", "open", ("地下防水",), ("防水",)),
    ShadowCase("open_037", "钢结构高强螺栓终拧有什么要求？", "open", ("高强螺栓",), ("终拧",)),
    ShadowCase("open_038", "砖砌体灰缝厚度一般是多少？", "open", ("灰缝",), ("灰缝",)),
    ShadowCase("open_039", "屋面卷材搭接宽度怎么控制？", "open", ("卷材",), ("搭接",)),
    ShadowCase("open_040", "基坑降水什么时候需要专项方案？", "open", ("基坑",), ("专项方案",)),
    ShadowCase("off_041", "给我推荐一部电影", "open"),
    ShadowCase("off_042", "帮我翻译 hello world", "open"),
    ShadowCase("off_043", "今天人民币兑美元是多少", "open"),
    ShadowCase("off_044", "写一段朋友圈文案", "open"),
    ShadowCase("off_045", "帮我做一个健身计划", "open"),
    ShadowCase("open_046", "施工组织设计谁审批？", "open", ("施工组织设计",), ("审批",)),
    ShadowCase("open_047", "单位工程验收和分部工程验收区别是什么？", "open", ("验收",), ("单位工程", "分部工程")),
    ShadowCase("open_048", "安全技术交底要交底哪些内容？", "open", ("安全技术交底",), ("交底",)),
    ShadowCase("open_049", "冬期施工混凝土养护怎么做？", "open", ("冬期施工",), ("养护",)),
    ShadowCase("open_050", "施工成本偏差怎么分析？", "open", ("成本偏差",), ("偏差",)),
)


def _pack_from(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("result_metadata") if isinstance(row.get("result_metadata"), dict) else {}
    pack = metadata.get("luban_general_knowledge_context")
    return pack if isinstance(pack, dict) else {}


def _token_count(row: dict[str, Any]) -> int:
    metadata = row.get("result_metadata") if isinstance(row.get("result_metadata"), dict) else {}
    for key in ("total_tokens", "tokens", "usage_total_tokens"):
        value = metadata.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    usage = metadata.get("usage") if isinstance(metadata.get("usage"), dict) else {}
    for key in ("total_tokens", "total"):
        value = usage.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return max(1, len(str(row.get("visible_response") or "")) // 2)


def _source_valid(pack: dict[str, Any]) -> bool:
    if pack.get("authority") != "luban_general_knowledge_context":
        return False
    if pack.get("tier") != "teaching_context_not_answer_key":
        return False
    if pack.get("official_score_allowed") is not False:
        return False
    if pack.get("llm_may_decide_correctness") is not False:
        return False
    confidence = pack.get("confidence") if isinstance(pack.get("confidence"), dict) else {}
    if confidence.get("status") != "high":
        return False
    sources = pack.get("sources") if isinstance(pack.get("sources"), dict) else {}
    categories = [key for key in SOURCE_KEYS if sources.get(key)]
    source_category_count = int(confidence.get("source_category_count") or len(categories))
    return len(categories) >= 2 and source_category_count >= 2 and any(
        isinstance(item, dict) and str(item.get("text_preview") or item.get("content") or item.get("text") or "").strip()
        for key in categories
        for item in (sources.get(key) or [])
    )


def _answer_score(text: str, terms: tuple[str, ...]) -> int:
    content = str(text or "")
    return sum(1 for term in terms if term and term in content)


def evaluate_pair(
    case: ShadowCase,
    *,
    control: dict[str, Any],
    treatment: dict[str, Any],
) -> dict[str, Any]:
    control_error = str(control.get("shadow_error") or "").strip()
    treatment_error = str(treatment.get("shadow_error") or "").strip()
    round_failed = bool(control_error or treatment_error)
    if round_failed:
        return {
            "case_id": case.case_id,
            "query": case.query,
            "expected": case.expected,
            "evaluable": False,
            "non_evaluable_reason": "shadow_transport_or_service_error",
            "round_failed": True,
            "control_error": control_error,
            "treatment_error": treatment_error,
            "compiled_hit": None,
            "fail_open": None,
            "wrong_path": None,
            "source_valid": None,
            "leaf_name_path": "",
            "control_answer_score": None,
            "treatment_answer_score": None,
            "answer_improved": None,
            "answer_regressed": None,
            "control_tokens": None,
            "treatment_tokens": None,
            "token_delta": None,
            "control_excerpt": str(control.get("visible_response") or "")[:320],
            "treatment_excerpt": str(treatment.get("visible_response") or "")[:320],
        }
    pack = {} if round_failed else _pack_from(treatment)
    compiled_hit = bool(pack)
    leaf_name_path = str(pack.get("leaf_name_path") or "")
    path_ok = compiled_hit and all(term in leaf_name_path for term in case.path_terms)
    expected_hit = case.expected == "hit"
    fail_open = (not round_failed) and (not compiled_hit)
    wrong_path = compiled_hit and (not path_ok or not expected_hit)
    source_valid = compiled_hit and path_ok and _source_valid(pack)
    control_score = _answer_score(str(control.get("visible_response") or ""), case.answer_terms)
    treatment_score = _answer_score(str(treatment.get("visible_response") or ""), case.answer_terms)
    control_tokens = _token_count(control)
    treatment_tokens = _token_count(treatment)
    return {
        "case_id": case.case_id,
        "query": case.query,
        "expected": case.expected,
        "evaluable": True,
        "non_evaluable_reason": "",
        "round_failed": round_failed,
        "control_error": control_error,
        "treatment_error": treatment_error,
        "compiled_hit": compiled_hit,
        "fail_open": fail_open,
        "wrong_path": wrong_path,
        "source_valid": source_valid,
        "leaf_name_path": leaf_name_path,
        "control_answer_score": control_score,
        "treatment_answer_score": treatment_score,
        "answer_improved": treatment_score > control_score,
        "answer_regressed": treatment_score < control_score,
        "control_tokens": control_tokens,
        "treatment_tokens": treatment_tokens,
        "token_delta": treatment_tokens - control_tokens,
        "control_excerpt": str(control.get("visible_response") or "")[:320],
        "treatment_excerpt": str(treatment.get("visible_response") or "")[:320],
    }


async def _create_conversation(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    status, payload = await _request_json(client, "POST", "/api/v1/conversations", headers=headers)
    if status != 200 and (status >= 500 or status in RECOVERABLE_HTTP_STATUSES):
        raise ShadowRecoverableServiceError(f"create_conversation_failed:{status}:{payload}")
    if status != 200:
        raise RuntimeError(f"create_conversation_failed:{status}:{payload}")
    return str(((payload.get("conversation") or {}).get("id")) or "").strip()


async def _create_conversation_or_error(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    case: ShadowCase,
    arm: str,
) -> tuple[str, dict[str, Any] | None]:
    try:
        return await _create_conversation(client, headers), None
    except RECOVERABLE_SHADOW_EXCEPTION_TYPES as exc:
        return "", _failure_result(case=case, arm=arm, error_stage="create_conversation", exc=exc)


def _shadow_error_text(exc: BaseException) -> str:
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _failure_result(
    *,
    case: ShadowCase,
    arm: str,
    error_stage: str,
    exc: BaseException,
    turn_id: str = "",
    events: list[str] | None = None,
    fragments: list[str] | None = None,
    result_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_types = list(events or [])
    partial_response = "".join(fragments or []).strip()
    metadata = dict(result_metadata or {})
    error_text = _shadow_error_text(exc)
    metadata.update(
        {
            "shadow_error": error_text,
            "shadow_error_stage": error_stage,
            "shadow_exception_type": type(exc).__name__,
            "shadow_last_event_type": event_types[-1] if event_types else "",
            "shadow_partial_response_excerpt": partial_response[:320],
        }
    )
    return {
        "case_id": case.case_id,
        "arm": arm,
        "turn_id": turn_id,
        "query": case.query,
        "visible_response": partial_response,
        "event_types": event_types,
        "result_metadata": metadata,
        "shadow_error": error_text,
        "shadow_error_stage": error_stage,
        "shadow_exception_type": type(exc).__name__,
        "shadow_last_event_type": event_types[-1] if event_types else "",
        "shadow_partial_response_excerpt": partial_response[:320],
    }


def _build_start_turn_body(
    *,
    case: ShadowCase,
    conversation_id: str,
    arm: str,
) -> dict[str, Any]:
    return {
        "query": case.query,
        "conversation_id": conversation_id,
        "mode": "AUTO",
        "language": "zh",
        "client_turn_id": f"shadow_{case.case_id}_{arm}_{int(time.time() * 1000)}",
        "general_knowledge_context": arm == "compiled",
        "config": {
            "bot_id": "construction-exam-coach",
        },
        "interaction_profile": "tutorbot",
        "interaction_hints": {
            "product_surface": "online_shadow",
            "entry_role": "tutorbot",
            "subject_domain": "construction_exam",
            "requested_response_mode": "smart",
        },
    }


async def _run_turn(
    client: httpx.AsyncClient,
    *,
    ws_url: str,
    token: str,
    headers: dict[str, str],
    conversation_id: str,
    case: ShadowCase,
    arm: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        status, payload = await _request_json(
            client,
            "POST",
            "/api/v1/chat/start-turn",
            headers=headers,
            json_body=_build_start_turn_body(case=case, conversation_id=conversation_id, arm=arm),
        )
    except RECOVERABLE_SHADOW_ERRORS as exc:
        return _failure_result(case=case, arm=arm, error_stage="start_turn_transport", exc=exc)
    if status != 200 and (status >= 500 or status in RECOVERABLE_HTTP_STATUSES):
        return _failure_result(
            case=case,
            arm=arm,
            error_stage="start_turn_http",
            exc=ShadowRecoverableServiceError(f"start_turn_failed:{case.case_id}:{arm}:{status}:{payload}"),
        )
    if status != 200:
        raise RuntimeError(f"start_turn_failed:{case.case_id}:{arm}:{status}:{payload}")
    subscribe = ((payload.get("stream") or {}).get("subscribe") or {})
    turn_id = str(((payload.get("turn") or {}).get("id")) or subscribe.get("turn_id") or "").strip()
    fragments: list[str] = []
    result_metadata: dict[str, Any] = {}
    events: list[str] = []
    try:
        async with websockets.connect(ws_url, additional_headers={"Authorization": f"Bearer {token}"}) as websocket:
            await websocket.send(json.dumps(subscribe or {"type": "subscribe_turn", "turn_id": turn_id, "after_seq": 0}, ensure_ascii=False))
            while True:
                raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
                event = json.loads(raw)
                event_type = str(event.get("type") or "")
                events.append(event_type)
                if event_type == "content" and event.get("content"):
                    fragments.append(str(event["content"]))
                elif event_type == "result":
                    result_metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
                elif event_type == "error":
                    raise ShadowRecoverableServiceError(f"ws_error:{case.case_id}:{arm}:{event}")
                elif event_type == "done":
                    break
    except RECOVERABLE_SHADOW_EXCEPTION_TYPES as exc:
        return _failure_result(
            case=case,
            arm=arm,
            error_stage="ws_stream",
            exc=exc,
            turn_id=turn_id,
            events=events,
            fragments=fragments,
            result_metadata=result_metadata,
        )
    return {
        "case_id": case.case_id,
        "arm": arm,
        "turn_id": turn_id,
        "query": case.query,
        "visible_response": "".join(fragments).strip(),
        "event_types": events,
        "result_metadata": result_metadata,
    }


async def _run_turn_or_error(**kwargs: Any) -> dict[str, Any]:
    case = kwargs["case"]
    arm = str(kwargs["arm"])
    try:
        return await _run_turn(**kwargs)
    except RECOVERABLE_SHADOW_EXCEPTION_TYPES as exc:
        return _failure_result(case=case, arm=arm, error_stage="turn_transport", exc=exc)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    failed_rounds = sum(1 for row in rows if row.get("round_failed"))
    evaluable_rows = [row for row in rows if not row.get("round_failed")]
    evaluable_total = len(evaluable_rows)
    compiled_hits = sum(1 for row in evaluable_rows if row["compiled_hit"])
    wrong_paths = sum(1 for row in evaluable_rows if row["wrong_path"])
    source_valid = sum(1 for row in evaluable_rows if row["source_valid"])
    fail_open = sum(1 for row in evaluable_rows if row["fail_open"])
    improved = sum(1 for row in evaluable_rows if row["answer_improved"])
    regressed = sum(1 for row in evaluable_rows if row["answer_regressed"])
    token_delta = sum(int(row["token_delta"]) for row in evaluable_rows)
    has_evaluable_rows = evaluable_total > 0
    return {
        "total": total,
        "evaluable_total": evaluable_total,
        "failed_rounds": failed_rounds,
        "metric_status": "ok" if has_evaluable_rows else "no_evaluable_samples",
        "compiled_hit_rate": compiled_hits / evaluable_total if has_evaluable_rows else None,
        "wrong_path_rate": wrong_paths / evaluable_total if has_evaluable_rows else None,
        "source_validity_status": "ok" if compiled_hits else "no_compiled_hit_samples",
        "source_validity_rate": source_valid / compiled_hits if compiled_hits else None,
        "fail_open_rate": fail_open / evaluable_total if has_evaluable_rows else None,
        "answer_improvement_rate": improved / evaluable_total if has_evaluable_rows else None,
        "answer_regression_rate": regressed / evaluable_total if has_evaluable_rows else None,
        "token_delta_total": token_delta,
        "token_delta_avg": token_delta / evaluable_total if has_evaluable_rows else None,
    }


async def run_shadow(
    *,
    api_base_url: str,
    username: str,
    password: str,
    phone: str,
    register: bool,
    output_dir: Path,
    limit: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ws_url = _build_ws_url(api_base_url.rstrip("/"))
    cases = list(DEFAULT_CASES)[:limit]
    rows: list[dict[str, Any]] = []
    transcript = output_dir / "transcript.jsonl"
    transcript.write_text("", encoding="utf-8")
    async with httpx.AsyncClient(base_url=api_base_url.rstrip("/"), timeout=timeout_seconds, trust_env=False) as client:
        auth_payload, created_user = await _register_or_login(
            client,
            username=username,
            password=password,
            phone=phone,
            register=register,
        )
        token = str(auth_payload.get("token") or "").strip()
        if not token:
            raise RuntimeError(f"auth_missing_token:{auth_payload}")
        headers = {"Authorization": f"Bearer {token}"}
        for case in cases:
            control_conversation, control_setup_error = await _create_conversation_or_error(
                client,
                headers,
                case=case,
                arm="rag_only",
            )
            treatment_conversation, treatment_setup_error = await _create_conversation_or_error(
                client,
                headers,
                case=case,
                arm="compiled",
            )
            control = control_setup_error or await _run_turn_or_error(
                client=client,
                ws_url=ws_url,
                token=token,
                headers=headers,
                conversation_id=control_conversation,
                case=case,
                arm="rag_only",
                timeout_seconds=timeout_seconds,
            )
            treatment = treatment_setup_error or await _run_turn_or_error(
                client=client,
                ws_url=ws_url,
                token=token,
                headers=headers,
                conversation_id=treatment_conversation,
                case=case,
                arm="compiled",
                timeout_seconds=timeout_seconds,
            )
            row = evaluate_pair(case, control=control, treatment=treatment)
            row["control_turn_id"] = control["turn_id"]
            row["treatment_turn_id"] = treatment["turn_id"]
            rows.append(row)
            with transcript.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"case": row, "control": control, "treatment": treatment}, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "api_base_url": api_base_url.rstrip("/"),
        "ws_url": ws_url,
        "username": username,
        "created_user": created_user,
        "rounds": len(rows),
        "metrics": _summary(rows),
        "transcript": str(transcript),
        "note": "Online HTTP+WS TutorBot shadow. Does not change production default or canonical truth.",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run online TutorBot RAG-only vs RAG+compiled shadow.")
    parser.add_argument("--api-base-url", default="https://test2.yousenjiaoyu.com")
    parser.add_argument("--username", default="qa_compiled_shadow")
    parser.add_argument("--password", default="QaCompiledShadow2026")
    parser.add_argument("--phone", default="13900000634")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = asyncio.run(
        run_shadow(
            api_base_url=str(args.api_base_url),
            username=str(args.username),
            password=str(args.password),
            phone=str(args.phone),
            register=bool(args.register),
            output_dir=args.output_dir,
            limit=int(args.limit),
            timeout_seconds=float(args.timeout_seconds),
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
