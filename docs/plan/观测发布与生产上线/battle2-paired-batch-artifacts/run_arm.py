#!/usr/bin/env python3
"""Battle2 paired baseline batch orchestrator (PRE / POST arm).

Serial (NO concurrency) so latency reads have no contention:
  - 5 drift-sentinel pings (independent sessions, fixed message) BEFORE
  - 5 continuity sessions x 4 progressive turns (same conversation)
  - 3 question/grading sessions x 4 turns (ask MCQ -> answer -> ask -> answer)
  - 5 drift-sentinel pings AFTER

Usage:
  cd <worktree> && PYTHONPATH=. python3 <scratch>/run_arm.py --prefix claude_b2pre_ --out <scratch>/pre_arm_results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone

from session_driver import run_session, register_user_with_backoff, _utc_iso

API_BASE = "https://test2.yousenjiaoyu.com"
POOL_SIZE = 3  # register limit is 3/60s; reuse pool via login, fresh conversation per session

SENTINEL_MESSAGE = "你好，请用一句话介绍你自己"

# 5 continuity sessions, each 4 progressive turns on a distinct fire-engineering topic.
CONTINUITY_SESSIONS = [
    ("cont_water_supply", [
        "消防给水系统里，消防水泵的流量应该怎么确定？",
        "那扬程呢，怎么算？",
        "它和稳压泵怎么配合工作？",
        "帮我把上面这些要点总结成一个表格。",
    ]),
    ("cont_fire_compartment", [
        "建筑防火分区的最大允许面积是怎么规定的？",
        "如果设了自动灭火系统，这个面积能放大多少？",
        "中庭的防火分区又该怎么处理？",
        "帮我把上面这些要点总结成一个表格。",
    ]),
    ("cont_sprinkler", [
        "自动喷水灭火系统的喷头选型要考虑哪些因素？",
        "那喷头的布置间距一般怎么定？",
        "它和报警阀组是怎么联动的？",
        "帮我把上面这些要点总结成一个表格。",
    ]),
    ("cont_smoke_control", [
        "防烟排烟系统里，机械加压送风的送风量怎么确定？",
        "那排烟量呢，怎么算？",
        "加压送风和机械排烟怎么协调控制？",
        "帮我把上面这些要点总结成一个表格。",
    ]),
    ("cont_fire_alarm", [
        "火灾自动报警系统的探测器怎么选型？",
        "那探测器的保护面积和安装间距怎么定？",
        "它和消防联动控制器是怎么配合的？",
        "帮我把上面这些要点总结成一个表格。",
    ]),
]

# 3 question/grading sessions: ask MCQ -> submit answer -> ask another -> submit answer.
GRADING_SESSIONS = [
    ("grade_water_supply", [
        "帮我出一道关于消防给水系统的单选题，只要题目和选项。",
        "我选A，帮我判一下对不对。",
        "再来一道关于消火栓系统的单选题。",
        "我选C，帮我判一下。",
    ]),
    ("grade_fire_compartment", [
        "帮我出一道关于建筑防火分区的单选题，只要题目和选项。",
        "我选B，帮我判一下对不对。",
        "再来一道关于安全疏散的单选题。",
        "我选D，帮我判一下。",
    ]),
    ("grade_extinguisher", [
        "帮我出一道关于灭火器配置的单选题，只要题目和选项。",
        "我选A，帮我判一下对不对。",
        "再来一道关于气体灭火系统的单选题。",
        "我选B，帮我判一下。",
    ]),
]


def _make_creds(prefix: str, counter: int) -> tuple[str, str, str]:
    stamp = int(time.time())
    username = f"{prefix}{stamp}_{counter}"
    password = f"SmokeA{stamp % 1000000:06d}"
    phone = f"139{(stamp + counter * 7) % 100000000:08d}"
    return username, password, phone


async def _register_pool(prefix: str, size: int, timeout: float):
    """Register `size` fresh eval users up front (login-reused later)."""
    pool = []
    for i in range(size):
        username, password, phone = _make_creds(prefix, i)
        created = await register_user_with_backoff(
            api_base_url=API_BASE, username=username, password=password,
            phone=phone, timeout_seconds=timeout,
        )
        print(f"[pool] registered {username} created={created}", flush=True)
        pool.append({"username": username, "password": password, "phone": phone})
    return pool


async def _run_sentinels(pool, phase: str, count: int, conv_counter: list, timeout: float):
    results = []
    for i in range(count):
        user = pool[conv_counter[0] % len(pool)]
        conv_counter[0] += 1
        label = f"sentinel_{phase}_{i + 1}"
        res = await run_session(
            api_base_url=API_BASE,
            username=user["username"],
            password=user["password"],
            phone=user["phone"],
            messages=[SENTINEL_MESSAGE],
            label=label,
            register=False,
            timeout_seconds=timeout,
        )
        t0 = res["turns"][0] if res.get("turns") else {}
        print(f"[{label}] user={user['username']} cid={res.get('conversation_id')} "
              f"passed={t0.get('passed')} wall_ms={t0.get('wall_ms')} err={t0.get('error')}", flush=True)
        results.append(res)
    return results


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, help="e.g. claude_b2pre_")
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    prefix = args.prefix
    conv_counter = [0]

    # Register the small user pool BEFORE the timed batch window (registration
    # latency must not pollute the batch window used for Langfuse readout).
    print(f"=== registering pool (size={POOL_SIZE}) prefix={prefix} ===", flush=True)
    pool = await _register_pool(prefix, POOL_SIZE, args.timeout)

    batch_start = time.time()
    print(f"=== batch start UTC {_utc_iso(batch_start)} prefix={prefix} ===", flush=True)

    # Sentinels BEFORE
    print("--- sentinels BEFORE ---", flush=True)
    sentinels_before = await _run_sentinels(pool, "before", 5, conv_counter, args.timeout)

    # Continuity sessions
    print("--- continuity sessions ---", flush=True)
    continuity_results = []
    for label, messages in CONTINUITY_SESSIONS:
        user = pool[conv_counter[0] % len(pool)]
        conv_counter[0] += 1
        res = await run_session(
            api_base_url=API_BASE,
            username=user["username"],
            password=user["password"],
            phone=user["phone"],
            messages=messages,
            label=label,
            register=False,
            timeout_seconds=args.timeout,
        )
        print(f"[{label}] cid={res.get('conversation_id')} passed_turns={res.get('passed_turns')}/{res.get('turn_count')} "
              f"session_wall_ms={res.get('session_wall_ms')}", flush=True)
        for t in res["turns"]:
            print(f"    turn{t['turn_index']} passed={t['passed']} wall_ms={t['wall_ms']} "
                  f"status={t['done_status']} resp_len={t['response_len']} err={t.get('error')}", flush=True)
        continuity_results.append(res)

    # Grading sessions
    print("--- grading sessions ---", flush=True)
    grading_results = []
    for label, messages in GRADING_SESSIONS:
        user = pool[conv_counter[0] % len(pool)]
        conv_counter[0] += 1
        res = await run_session(
            api_base_url=API_BASE,
            username=user["username"],
            password=user["password"],
            phone=user["phone"],
            messages=messages,
            label=label,
            register=False,
            timeout_seconds=args.timeout,
        )
        print(f"[{label}] cid={res.get('conversation_id')} passed_turns={res.get('passed_turns')}/{res.get('turn_count')} "
              f"session_wall_ms={res.get('session_wall_ms')}", flush=True)
        for t in res["turns"]:
            print(f"    turn{t['turn_index']} passed={t['passed']} wall_ms={t['wall_ms']} "
                  f"status={t['done_status']} resp_len={t['response_len']} err={t.get('error')}", flush=True)
        grading_results.append(res)

    # Sentinels AFTER
    print("--- sentinels AFTER ---", flush=True)
    sentinels_after = await _run_sentinels(pool, "after", 5, conv_counter, args.timeout)

    batch_end = time.time()

    main_sessions = continuity_results + grading_results
    main_turns_total = sum(s["turn_count"] for s in main_sessions)
    main_turns_passed = sum(s["passed_turns"] for s in main_sessions)
    sentinel_turns = sentinels_before + sentinels_after
    sentinel_passed = sum(1 for s in sentinel_turns for t in s["turns"] if t.get("passed"))

    failures = []
    for s in main_sessions:
        for t in s["turns"]:
            if not t.get("passed"):
                failures.append({
                    "session": s["label"], "turn_index": t["turn_index"],
                    "status": t.get("done_status"), "error": t.get("error"),
                    "conversation_id": t.get("conversation_id"),
                })
    for s in sentinel_turns:
        for t in s["turns"]:
            if not t.get("passed"):
                failures.append({
                    "session": s["label"], "turn_index": t.get("turn_index"),
                    "status": t.get("done_status"), "error": t.get("error"),
                    "conversation_id": t.get("conversation_id"),
                })

    output = {
        "arm": prefix.rstrip("_"),
        "prefix": prefix,
        "api_base_url": API_BASE,
        "pool_usernames": [u["username"] for u in pool],
        "pool_size": POOL_SIZE,
        "batch_start_utc": _utc_iso(batch_start),
        "batch_end_utc": _utc_iso(batch_end),
        "batch_wall_seconds": round(batch_end - batch_start, 1),
        "main_turns_total": main_turns_total,
        "main_turns_passed": main_turns_passed,
        "sentinel_turns_total": len(sentinel_turns),
        "sentinel_turns_passed": sentinel_passed,
        "failures": failures,
        "sentinels_before": sentinels_before,
        "sentinels_after": sentinels_after,
        "continuity_sessions": continuity_results,
        "grading_sessions": grading_results,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"=== batch end UTC {_utc_iso(batch_end)} wall_s={output['batch_wall_seconds']} ===", flush=True)
    print(f"main turns {main_turns_passed}/{main_turns_total} passed; "
          f"sentinels {sentinel_passed}/{len(sentinel_turns)} passed; "
          f"failures={len(failures)}", flush=True)
    print(f"written {args.out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
