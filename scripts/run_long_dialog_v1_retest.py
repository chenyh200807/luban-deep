#!/usr/bin/env python3
"""Long Dialog V1 复测脚本（DeepTutor / construction_exam_tutor / smart）。

当前仓库里已经没有旧系统原始的 `eval/sets/long_dialog_v1.jsonl`，
所以这里改为读取旧系统留存的 `session_full_conversations` 明细，
把真实用户轮次重新灌入当前 DeepTutor 运行时，做一次 live retest。

默认行为：
1. 从历史 artifact 中恢复 10 条长对话链的用户问题。
2. 用当前 DeepTutor 的 turn runtime 按同一 session 连续执行。
3. 全部使用 `construction_exam_tutor + smart` 配置。
4. 产出 JSON + Markdown 报告到 `tmp/`。

说明：
- 这是“当前仓库复测脚本”，不是旧 FastAPI 项目的原始评测器。
- 若单轮超时，默认直接中止该 case 后续轮次，避免出现
  “Session already has an active turn” 的连锁污染。
"""

from __future__ import annotations

import argparse
import asyncio
from difflib import SequenceMatcher
import json
import re
from statistics import mean
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import websockets

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tmp"
DEFAULT_SOURCE_CANDIDATES = [
    PROJECT_ROOT.parent
    / "FastAPI20251222_broken_backup_20260414_002321"
    / "artifacts"
    / "long_dialog_round7_full_detail_20260328.json",
    PROJECT_ROOT.parent
    / "FastAPI20251222"
    / "artifacts"
    / "long_dialog_round7_full_detail_20260328.json",
]

FOLLOWUP_PATTERN = re.compile(
    r"第\d+题|为什么不是|再来一题|这道题|刚才|前面|继续批改|沿用|同一个案例|别重新开始|"
    r"回到|你还记得|我答|我选|批改|继续追问|切换到|对比"
)
QUESTION_COUNT_PATTERN = re.compile(r"出([0-9一二两三四五六七八九十]+)(?:道|个)")
CHOICE_OPTION_A_PATTERN = re.compile(r"(?m)(?:^|\n)\s*(?:[-*]\s*)?A[\.、．]")
NUMBERED_ITEM_PATTERN = re.compile(r"(?m)(?:^|\n)\s*(?:第?\d+[题\.、]|[0-9]+[\.、])")

FOLLOWUP_OBJECT_MISMATCH_MARKERS = (
    "没有待评分",
    "当前没有待评分",
    "没有看到具体题目",
    "请提供完整题目",
    "请补充背景",
    "没有记录",
    "请提供背景材料",
    "无法直接批改",
    "我不知道你刚才回答的是哪道题",
)
TEMP_ERROR_MARKERS = (
    "服务繁忙",
    "处理超时",
    "临时异常",
    "稍后重试",
    "请求处理遇到临时异常",
)
CASE_FOCUS_TURNS = {
    "LD_003": [1, 2, 4, 8, 9],
    "LD_009": [1, 4, 5, 7, 8],
    "LD_010": [1, 5, 8, 9, 10],
}
ZH_NUMBER_MAP = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

CURRENT_INFO_KEYWORDS = (
    "最新",
    "现行",
    "当前",
    "今年",
    "最近",
    "政策",
    "通知",
    "公告",
    "新规",
    "发文",
    "变化",
)


def _build_ws_url(api_base_url: str) -> str:
    parsed = urlparse(api_base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/") + "/api/v1/ws"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def _resolve_source_path(cli_value: str | None) -> Path:
    if cli_value:
        path = Path(cli_value).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"未找到 source json: {path}")
        return path

    for candidate in DEFAULT_SOURCE_CANDIDATES:
        if candidate.exists():
            return candidate

    searched = "\n".join(str(path) for path in DEFAULT_SOURCE_CANDIDATES)
    raise FileNotFoundError(
        "未找到 long dialog V1 历史明细。请用 --source-json 指定。\n"
        f"默认查找位置：\n{searched}"
    )


def _zh_num_to_int(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    if len(text) == 2 and text[0] == "十" and text[1] in ZH_NUMBER_MAP:
        return 10 + ZH_NUMBER_MAP[text[1]]
    if len(text) == 2 and text[1] == "十" and text[0] in ZH_NUMBER_MAP:
        return ZH_NUMBER_MAP[text[0]] * 10
    if len(text) == 3 and text[1] == "十" and text[0] in ZH_NUMBER_MAP and text[2] in ZH_NUMBER_MAP:
        return ZH_NUMBER_MAP[text[0]] * 10 + ZH_NUMBER_MAP[text[2]]
    return ZH_NUMBER_MAP.get(text)


def _query_requires_current_info(query: str) -> bool:
    text = str(query or "").strip().lower()
    return any(keyword in text for keyword in CURRENT_INFO_KEYWORDS)


def _build_retest_interaction_hints(
    *,
    mode: str,
    profile: str,
    query: str,
    hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(hints or {})
    merged["profile"] = profile or "construction_exam_tutor"
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode in {"smart", "fast", "deep"}:
        merged["requested_response_mode"] = normalized_mode
        merged["teaching_mode"] = normalized_mode
    if _query_requires_current_info(query):
        merged["current_info_required"] = True
    return merged


def _map_case(first_query: str) -> tuple[str, str]:
    query = first_query or ""
    if "流水施工一直搞不懂" in query:
        return "LD_001", "新手理解型：流水施工+横道图+网络计划"
    if "总时差和自由时差" in query:
        return "LD_002", "刷题纠错型：双代号网络计划+总时差自由时差"
    if "招投标+合同管理" in query:
        return "LD_003", "案例题条件保持型：招投标与合同管理"
    if "还有30天" in query and "周一到周五" in query:
        return "LD_004", "学习规划型：30天冲刺计划"
    if "模板工程、脚手架、安全文明施工" in query:
        return "LD_005", "抗干扰型：模板脚手架与安全文明施工"
    if "搭接长度和锚固长度" in query:
        return "LD_006", "错题追踪型：钢筋工程"
    if "防水等级是怎么划分" in query:
        return "LD_007", "换表达型：地下防水工程"
    if "进度管理快崩溃" in query:
        return "LD_008", "情绪干扰型：进度管理"
    if "基坑工程安全方案" in query:
        return "LD_009", "条件修改型：基坑工程"
    if "质量验收" in query and "安全管理" in query:
        return "LD_010", "跨话题型：质量验收 vs 安全管理"
    return "LD_XXX", query[:30]


def _explicit_anchor_requirements(query: str) -> list[tuple[str, list[str]]]:
    requirements: list[tuple[str, list[str]]] = []
    if "6层住宅楼" in query:
        requirements.append(("6层住宅楼", ["6层", "住宅楼"]))
    if "总时差和自由时差" in query and ("本质差" in query or "搞混" in query):
        requirements.append(("总时差自由时差", ["总时差", "自由时差"]))
    if "招投标" in query and "合同管理" in query:
        requirements.append(("招投标合同管理", ["招投标", "合同"]))
    if "模板工程" in query and "脚手架" in query:
        requirements.append(("模板脚手架", ["模板", "脚手架"]))
    if "搭接长度" in query and "锚固长度" in query:
        requirements.append(("搭接与锚固", ["搭接", "锚固"]))
    if "质量验收" in query and "安全管理" in query:
        requirements.append(("质量安全对比", ["质量", "安全"]))
    return requirements


def _classify_turn(
    *,
    query: str,
    response: str,
    latency_ms: float,
    prev_response: str,
) -> dict[str, Any]:
    issues: list[str] = []
    response_text = response or ""

    empty = not response_text.strip()
    hard_error = empty or any(marker in response_text for marker in TEMP_ERROR_MARKERS)
    followup = bool(FOLLOWUP_PATTERN.search(query or ""))
    followup_object_mismatch = followup and any(
        marker in response_text for marker in FOLLOWUP_OBJECT_MISMATCH_MARKERS
    )
    slow_turn = latency_ms > 45_000

    question_count_mismatch = False
    count_match = QUESTION_COUNT_PATTERN.search(query or "")
    if count_match:
        expected_count = _zh_num_to_int(count_match.group(1))
        if expected_count:
            if "选择题" in query or "单选" in query or "小题" in query:
                actual = len(CHOICE_OPTION_A_PATTERN.findall(response_text))
                if actual > 0 and actual != expected_count:
                    question_count_mismatch = True
                    issues.append(
                        f"question_count_mismatch(expected={expected_count},actual={actual})"
                    )
            elif "判断题" in query:
                actual = len(NUMBERED_ITEM_PATTERN.findall(response_text))
                if actual > 0 and actual < expected_count:
                    question_count_mismatch = True
                    issues.append(
                        f"judge_count_mismatch(expected={expected_count},actual={actual})"
                    )

    anchor_miss = False
    for label, terms in _explicit_anchor_requirements(query):
        if not all(term in response_text for term in terms):
            anchor_miss = True
            issues.append(f"anchor_miss:{label}")
            break

    context_reset = False
    if any(tag in query for tag in ("同一个案例", "沿用", "别脱离前面的案例", "回到")):
        if any(marker in response_text for marker in ("请补充背景", "请提供背景材料", "没有记录")):
            context_reset = True
            issues.append("context_reset")

    compare_table_miss = False
    if "对比表" in query and ("原始条件" in query or "第一次修改" in query):
        if not all(marker in response_text for marker in ("原始条件", "第一次修改", "第二次修改")):
            compare_table_miss = True
            issues.append("compare_table_miss")

    stale_replay = False
    if prev_response and len(prev_response.strip()) >= 120 and len(response_text.strip()) >= 120:
        similarity = SequenceMatcher(
            None,
            re.sub(r"\s+", " ", prev_response).strip(),
            re.sub(r"\s+", " ", response_text).strip(),
        ).ratio()
        if similarity >= 0.92 and (query or "").strip():
            stale_replay = True
            issues.append(f"stale_replay({similarity:.2f})")

    if hard_error:
        issues.append("hard_error_or_empty")
    if followup_object_mismatch:
        issues.append("followup_object_mismatch")
    if slow_turn:
        issues.append("slow_turn")

    semantic_penalty = 0
    semantic_penalty += 15 if followup_object_mismatch else 0
    semantic_penalty += 10 if anchor_miss else 0
    semantic_penalty += 10 if context_reset else 0
    semantic_penalty += 8 if compare_table_miss else 0
    semantic_penalty += 8 if question_count_mismatch else 0
    semantic_penalty += 10 if stale_replay else 0
    semantic_penalty += 8 if hard_error else 0

    satisfaction_penalty = 0
    satisfaction_penalty += 18 if hard_error else 0
    satisfaction_penalty += 12 if followup_object_mismatch else 0
    satisfaction_penalty += 8 if question_count_mismatch else 0
    satisfaction_penalty += 6 if context_reset else 0
    satisfaction_penalty += 6 if compare_table_miss else 0
    satisfaction_penalty += 5 if slow_turn else 0
    satisfaction_penalty += 8 if stale_replay else 0

    return {
        "empty": empty,
        "hard_error": hard_error,
        "followup": followup,
        "followup_object_mismatch": followup_object_mismatch,
        "question_count_mismatch": question_count_mismatch,
        "anchor_miss": anchor_miss,
        "context_reset": context_reset,
        "compare_table_miss": compare_table_miss,
        "stale_replay": stale_replay,
        "slow_turn": slow_turn,
        "issues": issues,
        "semantic_penalty": semantic_penalty,
        "satisfaction_penalty": satisfaction_penalty,
    }


def _build_cases(source_payload: dict[str, Any]) -> list[dict[str, Any]]:
    cases = []
    session_map = source_payload.get("session_full_conversations") or {}
    for session_id, turns in session_map.items():
        ordered_turns = sorted(turns, key=lambda item: int(item.get("turn", 0) or 0))
        if not ordered_turns:
            continue
        case_id, title = _map_case(ordered_turns[0].get("user_query", ""))
        cases.append(
            {
                "case_id": case_id,
                "title": title,
                "source_session_id": session_id,
                "turns": ordered_turns,
            }
        )
    return sorted(cases, key=lambda item: item["case_id"])


def _build_turn_config(
    *,
    query: str,
    teaching_mode: str,
    include_eval_user: bool,
) -> dict[str, Any]:
    billing_context: dict[str, Any] = {
        "source": "wx_miniprogram",
    }
    if include_eval_user:
        billing_context["user_id"] = "ld_eval_user"
    return {
        "bot_id": "construction-exam-coach",
        "interaction_profile": "tutorbot",
        "interaction_hints": _build_retest_interaction_hints(
            mode=teaching_mode,
            profile="tutorbot",
            query=query,
            hints={},
        ),
        "billing_context": billing_context,
    }


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    floor_index = int(k)
    ceil_index = min(floor_index + 1, len(ordered) - 1)
    if floor_index == ceil_index:
        return float(ordered[floor_index])
    return float(
        ordered[floor_index] + (ordered[ceil_index] - ordered[floor_index]) * (k - floor_index)
    )


def _turn_metric_values(results: list[dict[str, Any]], field: str) -> list[float]:
    values: list[float] = []
    for item in results:
        for turn in item.get("turns", []):
            value = turn.get(field)
            if isinstance(value, (int, float)):
                values.append(float(value))
    return values


def _turn_metric_summary(results: list[dict[str, Any]], field: str) -> tuple[float, float | None, float | None]:
    values = _turn_metric_values(results, field)
    if not values:
        return 0.0, None, None
    return mean(values), _percentile(values, 0.5), _percentile(values, 0.9)


def _build_run_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    avg_ttft, p50_ttft, p90_ttft = _turn_metric_summary(results, "ttft_ms")
    avg_latency, p50_latency, p90_latency = _turn_metric_summary(results, "latency_ms")
    return {
        "cases": len(results),
        "total_turns": sum(item["summary"]["turns"] for item in results),
        "avg_semantic": mean(item["summary"]["semantic_score"] for item in results) if results else 0.0,
        "avg_satisfaction": (
            mean(item["summary"]["satisfaction_score"] for item in results) if results else 0.0
        ),
        "avg_ttft_ms": avg_ttft,
        "p50_ttft_ms": p50_ttft,
        "p90_ttft_ms": p90_ttft,
        "avg_latency_ms": avg_latency,
        "p50_latency_ms": p50_latency,
        "p90_latency_ms": p90_latency,
    }


async def _run_single_turn(
    runtime: TurnRuntimeManager,
    *,
    session_id: str | None,
    query: str,
    teaching_mode: str,
) -> tuple[str, str, float | None, float, list[str], dict[str, Any]]:
    config = _build_turn_config(
        query=query,
        teaching_mode=teaching_mode,
        include_eval_user=True,
    )
    start = time.perf_counter()
    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": query,
            "session_id": session_id,
            "capability": "tutorbot",
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": config,
        }
    )

    fragments: list[str] = []
    fallback_response = ""
    event_types: list[str] = []
    first_content_at_ms: float | None = None
    result_metadata: dict[str, Any] = {}
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        event_type = str(event.get("type") or "")
        event_types.append(event_type)
        if event_type == "content" and event.get("content"):
            if first_content_at_ms is None:
                first_content_at_ms = (time.perf_counter() - start) * 1000
            fragments.append(str(event["content"]))
        elif event_type == "result":
            metadata = event.get("metadata") or {}
            result_metadata = dict(metadata)
            fallback_response = str(
                metadata.get("response")
                or (metadata.get("metadata") or {}).get("response")
                or fallback_response
            )

    response = "".join(fragments).strip() or fallback_response.strip()
    latency_ms = (time.perf_counter() - start) * 1000
    return session["id"], response, first_content_at_ms, latency_ms, event_types, result_metadata


async def _run_single_turn_live_ws(
    *,
    api_base_url: str,
    session_id: str | None,
    query: str,
    teaching_mode: str,
) -> tuple[str, str, float | None, float, list[str], dict[str, Any]]:
    config = _build_turn_config(
        query=query,
        teaching_mode=teaching_mode,
        include_eval_user=False,
    )
    payload = {
        "type": "start_turn",
        "content": query,
        "capability": "tutorbot",
        "tools": [],
        "knowledge_bases": [],
        "attachments": [],
        "language": "zh",
        "config": config,
        "history_references": [],
        "notebook_references": [],
    }
    if session_id:
        payload["session_id"] = session_id

    ws_url = _build_ws_url(api_base_url)
    fragments: list[str] = []
    fallback_response = ""
    event_types: list[str] = []
    resolved_session_id = session_id or ""
    started_at = time.perf_counter()
    first_content_at_ms: float | None = None
    result_metadata: dict[str, Any] = {}

    async with websockets.connect(ws_url) as websocket:
        await websocket.send(json.dumps(payload, ensure_ascii=False))
        while True:
            raw = await websocket.recv()
            event = json.loads(raw)
            event_type = str(event.get("type") or "")
            event_types.append(event_type)
            if event_type == "session":
                resolved_session_id = str(event.get("session_id") or resolved_session_id)
            elif event_type == "content" and event.get("content"):
                if first_content_at_ms is None:
                    first_content_at_ms = (time.perf_counter() - started_at) * 1000
                fragments.append(str(event["content"]))
            elif event_type == "result":
                metadata = event.get("metadata") or {}
                result_metadata = dict(metadata)
                fallback_response = str(
                    metadata.get("response")
                    or (metadata.get("metadata") or {}).get("response")
                    or fallback_response
                )
            if event_type == "error":
                raise RuntimeError(str(event.get("content") or "live_ws_turn_failed"))
            if event_type == "done":
                break

    response = "".join(fragments).strip() or fallback_response.strip()
    latency_ms = (time.perf_counter() - started_at) * 1000
    return (
        resolved_session_id,
        response,
        first_content_at_ms,
        latency_ms,
        event_types,
        result_metadata,
    )


async def _run_case(
    case: dict[str, Any],
    *,
    teaching_mode: str,
    per_turn_timeout_s: float,
    turn_mode: str,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    runtime: TurnRuntimeManager | None = None
    if not api_base_url:
        tmpdir = tempfile.mkdtemp(prefix=f"long_dialog_{case['case_id'].lower()}_")
        store = SQLiteSessionStore(Path(tmpdir) / "chat_history.db")
        runtime = TurnRuntimeManager(store)

    session_id: str | None = None
    prev_response = ""
    results: list[dict[str, Any]] = []
    aborted = False
    abort_reason = ""

    source_turns = case["turns"]
    if turn_mode == "focus" and case["case_id"] in CASE_FOCUS_TURNS:
        target_set = set(CASE_FOCUS_TURNS[case["case_id"]])
        selected_turns = [turn for turn in source_turns if int(turn.get("turn", 0) or 0) in target_set]
    else:
        selected_turns = list(source_turns)

    print(
        f"[{case['case_id']}] START {case['title']} ({len(selected_turns)} turns, mode={turn_mode})",
        flush=True,
    )

    for item in selected_turns:
        turn_no = int(item.get("turn", 0) or 0)
        query = str(item.get("user_query") or "")
        try:
            session_id, response, ttft_ms, latency_ms, event_types, result_metadata = await asyncio.wait_for(
                (
                    _run_single_turn_live_ws(
                        api_base_url=api_base_url,
                        session_id=session_id,
                        query=query,
                        teaching_mode=teaching_mode,
                    )
                    if api_base_url
                    else _run_single_turn(
                        runtime,
                        session_id=session_id,
                        query=query,
                        teaching_mode=teaching_mode,
                    )
                ),
                timeout=per_turn_timeout_s,
            )
            eval_result = _classify_turn(
                query=query,
                response=response,
                latency_ms=latency_ms,
                prev_response=prev_response,
            )
            prev_response = response
            results.append(
                {
                    "turn": turn_no,
                    "query": query,
                    "response": response,
                    "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
                    "latency_ms": round(latency_ms, 1),
                    "event_types": event_types,
                    "selected_mode": str(result_metadata.get("selected_mode") or "").strip(),
                    "execution_path": str(result_metadata.get("execution_path") or "").strip(),
                    "exact_fast_path_hit": bool(result_metadata.get("exact_fast_path_hit", False)),
                    "actual_tool_rounds": int(result_metadata.get("actual_tool_rounds") or 0),
                    **eval_result,
                }
            )
            issue_text = "|".join(eval_result["issues"]) or "none"
            print(
                f"[{case['case_id']}] T{turn_no:02d} {latency_ms / 1000:.1f}s issues={issue_text}",
                flush=True,
            )
        except Exception as exc:
            aborted = True
            abort_reason = f"{type(exc).__name__}: {exc}"
            results.append(
                {
                    "turn": turn_no,
                    "query": query,
                    "response": "",
                    "ttft_ms": None,
                    "latency_ms": None,
                    "event_types": [],
                    "empty": True,
                    "hard_error": True,
                    "followup": bool(FOLLOWUP_PATTERN.search(query)),
                    "followup_object_mismatch": False,
                    "question_count_mismatch": False,
                    "anchor_miss": False,
                    "context_reset": False,
                    "compare_table_miss": False,
                    "stale_replay": False,
                    "slow_turn": False,
                    "issues": [f"exception:{abort_reason}"],
                    "semantic_penalty": 12,
                    "satisfaction_penalty": 20,
                }
            )
            print(f"[{case['case_id']}] T{turn_no:02d} ERROR {abort_reason}", flush=True)
            break

    semantic_score = max(0, 100 - sum(item["semantic_penalty"] for item in results))
    satisfaction_score = max(0, 100 - sum(item["satisfaction_penalty"] for item in results))

    summary = {
        "turns": len(results),
        "hard_errors": sum(1 for item in results if item["hard_error"]),
        "followup_object_mismatch_count": sum(
            1 for item in results if item["followup_object_mismatch"]
        ),
        "question_count_mismatch_count": sum(
            1 for item in results if item["question_count_mismatch"]
        ),
        "anchor_miss_count": sum(1 for item in results if item["anchor_miss"]),
        "context_reset_count": sum(1 for item in results if item["context_reset"]),
        "compare_table_miss_count": sum(1 for item in results if item["compare_table_miss"]),
        "stale_replay_count": sum(1 for item in results if item["stale_replay"]),
        "slow_turns": sum(1 for item in results if item["slow_turn"]),
        "avg_latency_ms": round(
            mean([item["latency_ms"] for item in results if item["latency_ms"] is not None]),
            1,
        )
        if any(item["latency_ms"] is not None for item in results)
        else None,
        "avg_ttft_ms": round(
            mean([item["ttft_ms"] for item in results if item["ttft_ms"] is not None]),
            1,
        )
        if any(item["ttft_ms"] is not None for item in results)
        else None,
        "p50_ttft_ms": round(
            _percentile([item["ttft_ms"] for item in results if item["ttft_ms"] is not None], 0.5)
            or 0.0,
            1,
        )
        if any(item["ttft_ms"] is not None for item in results)
        else None,
        "p90_ttft_ms": round(
            _percentile([item["ttft_ms"] for item in results if item["ttft_ms"] is not None], 0.9)
            or 0.0,
            1,
        )
        if any(item["ttft_ms"] is not None for item in results)
        else None,
        "semantic_score": semantic_score,
        "satisfaction_score": satisfaction_score,
        "aborted": aborted,
        "abort_reason": abort_reason,
    }

    print(
        f"[{case['case_id']}] DONE semantic={semantic_score} "
        f"satisfaction={satisfaction_score} hard_errors={summary['hard_errors']}"
        + (" aborted" if aborted else ""),
        flush=True,
    )

    return {
        "case_id": case["case_id"],
        "title": case["title"],
        "source_session_id": case["source_session_id"],
        "summary": summary,
        "turns": results,
    }


def _render_markdown(
    results: list[dict[str, Any]],
    *,
    source_json: Path,
    teaching_mode: str,
    api_base_url: str | None,
) -> str:
    run_summary = _build_run_summary(results)

    lines = [
        "# Long Dialog V1 Retest",
        "",
        f"**时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**教学模式**: {teaching_mode}",
        f"**执行方式**: {'live_ws' if api_base_url else 'in_process_runtime'}",
        f"**API Base URL**: `{api_base_url}`" if api_base_url else "**API Base URL**: `N/A`",
        f"**数据源**: `{source_json}`",
        f"**场景数**: {run_summary['cases']}",
        f"**总轮次**: {run_summary['total_turns']}",
        "",
        "## 总览",
        "",
        f"- 系统语义理解均分: {run_summary['avg_semantic']:.1f}/100",
        f"- 付费学员满意度均分: {run_summary['avg_satisfaction']:.1f}/100",
        f"- 平均 TTFT: {run_summary['avg_ttft_ms']:.1f}ms",
        f"- P50 TTFT: {(run_summary['p50_ttft_ms'] or 0.0):.1f}ms",
        f"- P90 TTFT: {(run_summary['p90_ttft_ms'] or 0.0):.1f}ms",
        f"- 平均延迟: {run_summary['avg_latency_ms']:.1f}ms",
        f"- P50 延迟: {(run_summary['p50_latency_ms'] or 0.0):.1f}ms",
        f"- P90 延迟: {(run_summary['p90_latency_ms'] or 0.0):.1f}ms",
        f"- 硬错误/空回复: {sum(item['summary']['hard_errors'] for item in results)}",
        f"- 跟题/批改断裂: {sum(item['summary']['followup_object_mismatch_count'] for item in results)}",
        f"- 出题契约失配: {sum(item['summary']['question_count_mismatch_count'] for item in results)}",
        f"- 显式锚点遗漏: {sum(item['summary']['anchor_miss_count'] for item in results)}",
        f"- 上下文重置: {sum(item['summary']['context_reset_count'] for item in results)}",
        f"- 对比表缺失: {sum(item['summary']['compare_table_miss_count'] for item in results)}",
        f"- 疑似重复回放: {sum(item['summary']['stale_replay_count'] for item in results)}",
        f"- 慢响应(>45s): {sum(item['summary']['slow_turns'] for item in results)}",
        "",
        "## 分场景",
        "",
        "| Case | 语义分 | 满意度分 | 硬错误 | 跟题断裂 | 契约失配 | 锚点遗漏 | 上下文重置 | 对比表缺失 | 慢响应 | 平均 TTFT | 平均延迟 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for item in results:
        summary = item["summary"]
        lines.append(
            f"| {item['case_id']} | {summary['semantic_score']} | {summary['satisfaction_score']} | "
            f"{summary['hard_errors']} | {summary['followup_object_mismatch_count']} | "
            f"{summary['question_count_mismatch_count']} | {summary['anchor_miss_count']} | "
            f"{summary['context_reset_count']} | {summary['compare_table_miss_count']} | "
            f"{summary['slow_turns']} | {summary['avg_ttft_ms'] or 0:.1f}ms | {summary['avg_latency_ms'] or 0:.1f}ms |"
        )

    lines.append("")
    lines.append("## 主要问题轮次")
    lines.append("")

    for item in results:
        bad_turns = [turn for turn in item["turns"] if turn["issues"]]
        if not bad_turns:
            continue
        lines.append(f"### {item['case_id']} {item['title']}")
        lines.append("")
        if item["summary"]["aborted"]:
            lines.append(f"- Case 中止: `{item['summary']['abort_reason']}`")
            lines.append("")
        for turn in bad_turns[:10]:
            preview = turn["response"][:160].replace("\n", " ")
            lines.append(f"- T{turn['turn']}: {'; '.join(turn['issues'])}")
            lines.append(f"  Query: {turn['query']}")
            lines.append(f"  Response: {preview}")
        lines.append("")

    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run Long Dialog V1 retest on current DeepTutor runtime")
    parser.add_argument("--source-json", help="历史 long dialog artifact JSON 路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录，默认 tmp/")
    parser.add_argument("--cases", help="逗号分隔 case id，例如 LD_001,LD_003")
    parser.add_argument("--max-cases", type=int, help="只跑前 N 个 case")
    parser.add_argument(
        "--turn-mode",
        choices=["full", "focus"],
        default="full",
        help="full=整条链；focus=仅跑代表性关键轮次",
    )
    parser.add_argument(
        "--teaching-mode",
        choices=["smart", "fast", "deep"],
        default="smart",
        help="教学模式，默认 smart",
    )
    parser.add_argument(
        "--per-turn-timeout",
        type=float,
        default=160.0,
        help="单轮总超时秒数；超时后当前 case 直接中止，默认 160s",
    )
    parser.add_argument(
        "--api-base-url",
        help="提供后，经真实 /api/v1/ws 执行每一轮；不提供则使用本进程 TurnRuntimeManager",
    )
    args = parser.parse_args()

    source_json = _resolve_source_path(args.source_json)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(source_json.read_text(encoding="utf-8"))
    cases = _build_cases(payload)

    if args.cases:
        allowed = {item.strip() for item in args.cases.split(",") if item.strip()}
        cases = [item for item in cases if item["case_id"] in allowed]
    if args.max_cases:
        cases = cases[: args.max_cases]

    if not cases:
        raise SystemExit("没有可执行的 case。")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"long_dialog_v1_retest_{args.teaching_mode}_{stamp}.json"
    md_path = output_dir / f"long_dialog_v1_retest_{args.teaching_mode}_{stamp}.md"

    results: list[dict[str, Any]] = []
    for case in cases:
        case_result = await _run_case(
            case,
            teaching_mode=args.teaching_mode,
            per_turn_timeout_s=args.per_turn_timeout,
            turn_mode=args.turn_mode,
            api_base_url=args.api_base_url,
        )
        results.append(case_result)
        json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(
            _render_markdown(
                results,
                source_json=source_json,
                teaching_mode=args.teaching_mode,
                api_base_url=args.api_base_url,
            ),
            encoding="utf-8",
        )

    run_summary = _build_run_summary(results)
    print("")
    print("=" * 60)
    print(f"Long Dialog V1 Retest 完成: {run_summary['cases']} cases")
    print(f"系统语义理解均分: {run_summary['avg_semantic']:.1f}/100")
    print(f"付费学员满意度均分: {run_summary['avg_satisfaction']:.1f}/100")
    print(f"平均 TTFT: {run_summary['avg_ttft_ms']:.1f}ms")
    print(f"P50 TTFT: {(run_summary['p50_ttft_ms'] or 0.0):.1f}ms")
    print(f"P90 TTFT: {(run_summary['p90_ttft_ms'] or 0.0):.1f}ms")
    print(f"平均延迟: {run_summary['avg_latency_ms']:.1f}ms")
    print(f"P50 延迟: {(run_summary['p50_latency_ms'] or 0.0):.1f}ms")
    print(f"P90 延迟: {(run_summary['p90_latency_ms'] or 0.0):.1f}ms")
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
