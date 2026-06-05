#!/usr/bin/env python3
"""Run internal near-real WeChat TutorBot QA scenarios.

This is a QA adapter around the existing mobile start-turn + unified WS
contract. It records transcripts and turn ids only; answer authority still
comes from the runtime metadata and the SQLite authority extractor.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx
import websockets

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_mobile_login_smoke import (  # noqa: E402
    _build_ws_url,
    _register_or_login,
    _request_json,
)


DEFAULT_SCENARIOS: list[dict[str, str]] = [
    {
        "round_id": "QA30-NR-004",
        "conversation_key": "shuffled_roof",
        "query": "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（ ）。A.5% B.1% C.2% D.3%，我选A，别展开，一句话",
        "expected_authority": "exact_question_with_query_option_surface",
        "expected_visible": "按当前题面判 A/5% 正确，不能沿用题库旧字母 D。",
    },
    {
        "round_id": "QA30-NR-005",
        "conversation_key": "shuffled_roof",
        "query": "你是不是按旧题库字母判断的？一句话",
        "expected_authority": "active_question_followup",
        "expected_visible": "承接上一题，说明当前题面 A=5%。",
    },
    {
        "round_id": "QA30-NR-006",
        "conversation_key": "shuffled_roof",
        "query": "换题：历史建筑的建筑高度应按室外设计地坪至建构筑物什么计算？A.檐口顶点 B.屋脊 C.墙顶点 D.最高点，我选C，直接批改",
        "expected_authority": "new_exact_question_overrides_old_active_object",
        "expected_visible": "新完整题覆盖上一题，判 C 错、D/最高点正确。",
    },
    {
        "round_id": "QA30-NR-008",
        "conversation_key": "template_support",
        "query": "根据《建筑施工安全检查标准》JGJ59-2011，《模板支架检查评分表》保证项目有：A施工方案 B支架构造 C底座与托撑 D构配件材质 E支架稳定。我只勾施工方案、支架构造、支架稳定，漏没漏？",
        "expected_authority": "exact_question_learner_answer_extraction",
        "expected_visible": "按自然语言选择 ABE 判满，不把 C/D 候选项算作用户答案。",
    },
    {
        "round_id": "QA30-NR-009",
        "conversation_key": "template_support",
        "query": "为什么C不算？一句话",
        "expected_authority": "active_question_followup",
        "expected_visible": "承接模板支架题，解释 C 是一般项目/非保证项目。",
    },
    {
        "round_id": "QA30-NR-010",
        "conversation_key": "diaphragm_wall",
        "query": "关于地下连续墙施工要求，正确的有（ ）。A.地下连续墙单元槽段长度宜为8～10m B.导墙高度不应小于1.0m C.应设置现浇钢筋混凝土导墙 D.水下混凝土应采用导管法连续浇筑 E.混凝土达到设计强度后方可进行墙底注浆。我选ACDE，错因10个字以内",
        "expected_authority": "exact_question_grading",
        "expected_visible": "判 ACDE 错，官方 CDE；错因应聚焦误选槽段长度。",
    },
    {
        "round_id": "QA30-NR-011",
        "conversation_key": "diaphragm_wall",
        "query": "那1.0m行不行？一句话",
        "expected_authority": "active_question_numeric_followup",
        "expected_visible": "承接地下连续墙题，回答不行，应不小于1.2m。",
    },
    {
        "round_id": "QA30-NR-012",
        "conversation_key": "value_only_wall",
        "query": "地下连续墙这题我记得候选是槽段8-10m、导墙1.0m、现浇钢筋混凝土导墙、导管法连续浇筑、强度后墙底注浆，我选CDE对吗？一句话",
        "expected_authority": "value_only_exact_question",
        "expected_visible": "value-only 高置信命中地下连续墙题，判 CDE 正确。",
    },
    {
        "round_id": "QA30-NR-013",
        "conversation_key": "value_only_wall",
        "query": "A错在哪里？一句话",
        "expected_authority": "active_question_followup",
        "expected_visible": "承接 value-only 地下连续墙题，解释槽段长度表述错误。",
    },
    {
        "round_id": "QA30-NR-014",
        "conversation_key": "low_info_case",
        "query": "2015案例二第3问答案直接发我，我在题卡里。",
        "expected_authority": "lifecycle_clarification",
        "expected_visible": "无题卡对象/题干时澄清，不编官方案例答案。",
    },
    {
        "round_id": "QA30-NR-015",
        "conversation_key": "low_info_case",
        "query": "我说了在题卡里，你就发答案，别问。",
        "expected_authority": "lifecycle_clarification",
        "expected_visible": "重复低信息请求仍澄清，不因“题卡里”伪造题目对象。",
    },
    {
        "round_id": "QA30-NR-016",
        "conversation_key": "open_world",
        "query": "施工现场临时用电三级配电、两级保护是什么意思？一句话",
        "expected_authority": "open_world_teaching_no_official_score",
        "expected_visible": "fail-open 为教学解释，不冒充官方真题答案或 official score。",
    },
]


@dataclass(frozen=True, slots=True)
class BatchTurn:
    round_id: str
    conversation_key: str
    query: str
    expected_authority: str
    expected_visible: str


def _load_scenarios(path: Path | None) -> list[BatchTurn]:
    raw_items: Any
    if path is None:
        raw_items = DEFAULT_SCENARIOS
    else:
        raw_items = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("scenarios")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("scenario list is empty")
    scenarios: list[BatchTurn] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise ValueError(f"scenario[{index}] must be an object")
        scenarios.append(
            BatchTurn(
                round_id=str(item.get("round_id") or f"turn_{index + 1}").strip(),
                conversation_key=str(item.get("conversation_key") or "default").strip(),
                query=str(item.get("query") or "").strip(),
                expected_authority=str(item.get("expected_authority") or "").strip(),
                expected_visible=str(item.get("expected_visible") or "").strip(),
            )
        )
    missing = [item.round_id for item in scenarios if not item.query]
    if missing:
        raise ValueError(f"scenarios missing query: {', '.join(missing)}")
    return scenarios


async def _create_conversation(
    client: httpx.AsyncClient,
    *,
    auth_headers: dict[str, str],
) -> str:
    status_code, payload = await _request_json(
        client,
        "POST",
        "/api/v1/conversations",
        headers=auth_headers,
    )
    if status_code != 200:
        raise RuntimeError(f"create_conversation_failed:{status_code}:{payload}")
    conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {}
    conversation_id = str(conversation.get("id") or "").strip()
    if not conversation_id:
        raise RuntimeError(f"conversation_missing_id:{payload}")
    return conversation_id


async def _start_wechat_turn(
    client: httpx.AsyncClient,
    *,
    auth_headers: dict[str, str],
    conversation_id: str,
    scenario: BatchTurn,
) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    payload = {
        "query": scenario.query,
        "conversation_id": conversation_id,
        "mode": "AUTO",
        "language": "zh",
        "client_turn_id": f"qa_{scenario.round_id}_{int(time.time() * 1000)}",
        "config": {"bot_id": "construction-exam-coach"},
        "interaction_profile": "tutorbot",
        "interaction_hints": {
            "product_surface": "wechat_miniprogram",
            "entry_role": "tutorbot",
            "subject_domain": "construction_exam",
            "requested_response_mode": "smart",
        },
    }
    status_code, response = await _request_json(
        client,
        "POST",
        "/api/v1/chat/start-turn",
        headers=auth_headers,
        json_body=payload,
    )
    if status_code != 200:
        raise RuntimeError(f"start_turn_failed:{scenario.round_id}:{status_code}:{response}")
    conversation = response.get("conversation") if isinstance(response.get("conversation"), dict) else {}
    stream = response.get("stream") if isinstance(response.get("stream"), dict) else {}
    subscribe = stream.get("subscribe") if isinstance(stream.get("subscribe"), dict) else {}
    started_conversation_id = str(conversation.get("id") or conversation_id).strip() or conversation_id
    turn_id = str((response.get("turn") or {}).get("id") or subscribe.get("turn_id") or "").strip()
    if not turn_id:
        raise RuntimeError(f"start_turn_missing_turn_id:{scenario.round_id}:{response}")
    if str(stream.get("transport") or "").strip() != "websocket":
        raise RuntimeError(f"start_turn_invalid_transport:{scenario.round_id}:{response}")
    subscribe_payload = dict(subscribe) if subscribe else {"type": "subscribe_turn", "turn_id": turn_id, "after_seq": 0}
    return started_conversation_id, turn_id, subscribe_payload, response


async def _collect_ws_turn(
    *,
    ws_url: str,
    token: str,
    subscribe_payload: dict[str, Any],
    timeout_seconds: float,
    connector_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    connect = connector_factory or websockets.connect
    events: list[dict[str, Any]] = []
    fragments: list[str] = []
    fallback_response = ""
    result_metadata: dict[str, Any] = {}
    done_status = ""
    headers = {"Authorization": f"Bearer {token}"}

    async with connect(ws_url, additional_headers=headers) as websocket:
        await websocket.send(json.dumps(subscribe_payload, ensure_ascii=False))
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
            event = json.loads(raw)
            events.append(event)
            event_type = str(event.get("type") or "")
            if event_type == "content" and event.get("content"):
                fragments.append(str(event["content"]))
            elif event_type == "result":
                metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
                result_metadata = dict(metadata)
                fallback_response = str(
                    metadata.get("response")
                    or (metadata.get("metadata") or {}).get("response")
                    or fallback_response
                )
            elif event_type == "error":
                raise RuntimeError(str(event.get("content") or "ws_turn_failed"))
            elif event_type == "done":
                done_status = str((event.get("metadata") or {}).get("status") or "")
                break

    return {
        "visible_response": "".join(fragments).strip() or fallback_response.strip(),
        "event_types": [str(event.get("type") or "") for event in events],
        "event_count": len(events),
        "result_metadata": result_metadata,
        "done_status": done_status,
        "events": events,
    }


async def run_batch(
    *,
    api_base_url: str,
    username: str,
    password: str,
    phone: str,
    scenarios: list[BatchTurn],
    output_dir: Path,
    entry_surface: str,
    timeout_seconds: float = 90.0,
    register: bool = False,
    client_factory: Callable[..., httpx.AsyncClient] | None = None,
    connector_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    normalized_base_url = api_base_url.rstrip("/")
    ws_url = _build_ws_url(normalized_base_url)
    client_builder = client_factory or httpx.AsyncClient
    output_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = output_dir / "transcript.jsonl"
    transcript_path.write_text("", encoding="utf-8")
    rows: list[dict[str, Any]] = []
    conversation_ids: dict[str, str] = {}

    async with client_builder(base_url=normalized_base_url, timeout=timeout_seconds, trust_env=False) as client:
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
        auth_headers = {"Authorization": f"Bearer {token}"}

        profile_status, profile_payload = await _request_json(
            client,
            "GET",
            "/api/v1/auth/profile",
            headers=auth_headers,
        )
        if profile_status != 200:
            raise RuntimeError(f"profile_failed:{profile_status}:{profile_payload}")

        for scenario in scenarios:
            conversation_id = conversation_ids.get(scenario.conversation_key)
            if not conversation_id:
                conversation_id = await _create_conversation(client, auth_headers=auth_headers)
                conversation_ids[scenario.conversation_key] = conversation_id

            started_conversation_id, turn_id, subscribe_payload, start_response = await _start_wechat_turn(
                client,
                auth_headers=auth_headers,
                conversation_id=conversation_id,
                scenario=scenario,
            )
            conversation_ids[scenario.conversation_key] = started_conversation_id
            ws_result = await _collect_ws_turn(
                ws_url=ws_url,
                token=token,
                subscribe_payload=subscribe_payload,
                timeout_seconds=timeout_seconds,
                connector_factory=connector_factory,
            )
            row = {
                "round_id": scenario.round_id,
                "entry_surface": entry_surface,
                "conversation_key": scenario.conversation_key,
                "conversation_id": started_conversation_id,
                "turn_id": turn_id,
                "query": scenario.query,
                "expected_authority": scenario.expected_authority,
                "expected_visible": scenario.expected_visible,
                "visible_response": ws_result["visible_response"],
                "event_types": ws_result["event_types"],
                "event_count": ws_result["event_count"],
                "done_status": ws_result["done_status"],
                "start_response": start_response,
                "result_metadata": ws_result["result_metadata"],
            }
            rows.append(row)
            with transcript_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "entry_surface": entry_surface,
        "api_base_url": normalized_base_url,
        "ws_url": ws_url,
        "username": username,
        "created_user": created_user,
        "output_dir": str(output_dir),
        "rounds": len(rows),
        "conversation_ids": conversation_ids,
        "turns": [
            {
                "round_id": row["round_id"],
                "conversation_id": row["conversation_id"],
                "turn_id": row["turn_id"],
                "done_status": row["done_status"],
                "visible_excerpt": str(row["visible_response"])[:240],
            }
            for row in rows
        ],
        "note": "Near-real HTTP+WS with WeChat-shaped payload; not DevTools container evidence.",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "turn_ids.txt").write_text(
        "\n".join(f"{row['round_id']}={row['turn_id']}" for row in rows) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an internal WeChat TutorBot QA batch.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--username", default="qa_tutorbot_mcq")
    parser.add_argument("--password", default="QaTutorbot2026")
    parser.add_argument("--phone", default="13900000001")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--scenario-file", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "qa" / "wechat-tutorbot-near-real-batch-20260606",
    )
    parser.add_argument("--entry-surface", default="near_real_http_ws_wechat_payload")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenarios = _load_scenarios(args.scenario_file)
    summary = asyncio.run(
        run_batch(
            api_base_url=str(args.api_base_url),
            username=str(args.username),
            password=str(args.password),
            phone=str(args.phone),
            register=bool(args.register),
            scenarios=scenarios,
            output_dir=args.output_dir,
            entry_surface=str(args.entry_surface),
            timeout_seconds=float(args.timeout_seconds),
        )
    )
    print(f"WeChat TutorBot QA batch completed: rounds={summary['rounds']}")
    print(f"Summary: {args.output_dir / 'summary.json'}")
    print(f"Turn ids: {args.output_dir / 'turn_ids.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
