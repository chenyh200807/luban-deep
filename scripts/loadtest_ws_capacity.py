#!/usr/bin/env python3
"""WS capacity load test for DeepTutor — measure concurrent-connection ceiling and
optional turn latency, so worker count is set from data, not architecture guesses.

SAFE BY DEFAULT: opens N concurrent WS connections and measures the handshake/auth
path + connection hold. It does NOT send LLM turns unless --with-turns is passed with
a real bearer token (each turn is a paid LLM call — never run that at scale on a live
production cohort; use a staging target or a maintenance window).

Usage:
  # connection-capacity only (no auth, no LLM cost) — measures how many concurrent
  # sockets the edge+app accept and the handshake latency distribution:
  python scripts/loadtest_ws_capacity.py --url wss://test2.yousenjiaoyu.com/api/v1/ws \
      --connections 200 --ramp-seconds 20 --hold-seconds 30

  # include real turns (COSTS LLM $; needs a valid token), small N only:
  python scripts/loadtest_ws_capacity.py --url wss://... --connections 20 \
      --with-turns --token "<JWT>" --turn-text "什么是建设工程监理"

Requires: websockets (pip install websockets).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[k]


async def _one_connection(
    idx: int, args, connect_latencies: list[float], turn_latencies: list[float],
    outcomes: dict[str, int],
) -> None:
    import websockets

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    t0 = time.perf_counter()
    try:
        async with websockets.connect(
            args.url, additional_headers=headers, open_timeout=args.open_timeout,
            max_size=2 ** 22, ping_interval=20, ping_timeout=20,
        ) as ws:
            connect_latencies.append((time.perf_counter() - t0) * 1000.0)
            outcomes["connected"] += 1

            if args.with_turns and args.token:
                tt = time.perf_counter()
                await ws.send(json.dumps({
                    "type": "start_turn",
                    "query": args.turn_text,
                }))
                # Wait for a terminal-ish frame or timeout.
                try:
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=args.turn_timeout)
                        evt = json.loads(raw) if isinstance(raw, str) else {}
                        if str(evt.get("type", "")).lower() in {"final", "result", "turn_complete", "error"}:
                            break
                    turn_latencies.append((time.perf_counter() - tt) * 1000.0)
                    outcomes["turn_ok"] += 1
                except asyncio.TimeoutError:
                    outcomes["turn_timeout"] += 1

            await asyncio.sleep(args.hold_seconds)
    except Exception as exc:  # noqa: BLE001 — record failure class, keep going
        name = type(exc).__name__
        # 4401 (auth) / 1013 (rate limit) close codes surface here as exceptions
        outcomes[name] = outcomes.get(name, 0) + 1


async def _run(args) -> int:
    connect_latencies: list[float] = []
    turn_latencies: list[float] = []
    outcomes: dict[str, int] = {"connected": 0, "turn_ok": 0, "turn_timeout": 0}

    per_conn_delay = (args.ramp_seconds / args.connections) if args.connections else 0.0
    tasks = []
    start = time.perf_counter()
    for i in range(args.connections):
        tasks.append(asyncio.create_task(
            _one_connection(i, args, connect_latencies, turn_latencies, outcomes)
        ))
        if per_conn_delay:
            await asyncio.sleep(per_conn_delay)
    await asyncio.gather(*tasks, return_exceptions=True)
    wall = time.perf_counter() - start

    print("=" * 60)
    print(f"target           : {args.url}")
    print(f"connections      : {args.connections} (ramp {args.ramp_seconds}s, hold {args.hold_seconds}s)")
    print(f"wall clock        : {wall:.1f}s")
    print(f"connected ok      : {outcomes.get('connected', 0)}/{args.connections}")
    if connect_latencies:
        print(f"connect latency   : p50={_percentile(connect_latencies,50):.0f}ms "
              f"p95={_percentile(connect_latencies,95):.0f}ms "
              f"max={max(connect_latencies):.0f}ms")
    if args.with_turns:
        print(f"turns ok/timeout  : {outcomes.get('turn_ok',0)}/{outcomes.get('turn_timeout',0)}")
        if turn_latencies:
            print(f"turn latency      : p50={_percentile(turn_latencies,50):.0f}ms "
                  f"p95={_percentile(turn_latencies,95):.0f}ms "
                  f"mean={statistics.mean(turn_latencies):.0f}ms")
    failures = {k: v for k, v in outcomes.items()
                if k not in {"connected", "turn_ok", "turn_timeout"}}
    if failures:
        print(f"failure classes   : {failures}")
    print("=" * 60)
    print("NOTE: capture server memory before/after with:")
    print("  ssh <host> 'docker stats --no-stream deeptutor; free -h'")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True, help="wss://host/api/v1/ws")
    p.add_argument("--connections", type=int, default=100)
    p.add_argument("--ramp-seconds", type=float, default=10.0)
    p.add_argument("--hold-seconds", type=float, default=20.0)
    p.add_argument("--open-timeout", type=float, default=15.0)
    p.add_argument("--with-turns", action="store_true", help="send real LLM turns (COSTS $)")
    p.add_argument("--token", default="", help="bearer JWT (required for --with-turns)")
    p.add_argument("--turn-text", default="什么是建设工程监理")
    p.add_argument("--turn-timeout", type=float, default=120.0)
    args = p.parse_args()
    if args.with_turns and not args.token:
        p.error("--with-turns requires --token")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
