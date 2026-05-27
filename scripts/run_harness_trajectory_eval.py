#!/usr/bin/env python3
"""Trajectory-level eval for the chat execution shell (harness Deferred D5).

P0.1 froze a *decision-layer* golden (scene/grounding/exact authorities,
deterministic, no LLM). D5 raises the net to the *trajectory* level: run the
**real** chat pipeline against representative cases through a live LLM and
assert structural invariants of the resulting stream trajectory.

Because real LLM output is non-deterministic, this gate asserts the *shape* of
the trajectory — not exact text:

- the turn terminates with exactly one ``result`` event,
- the final response is non-empty,
- no ``error`` event is emitted,
- every tool the model invoked is within the turn's ``enabled_tools``,
- the event sequence is well-formed (opens with ``stage_start``, the last
  meaningful event is ``result``).

This is the structural contract that D2 (chat bounded iteration) must preserve
when it later introduces multi-hop — so D5 also guards the D2 path in advance.

**Requires a keyed environment** (real LLM). Point DeepTutor at a populated
``.env`` via ``DEEPTUTOR_ENV_FILE`` (e.g. the sibling FastAPI project's .env).
If no LLM config resolves, the gate SKIPS (exit 2), it does not fail — so a
keyless CI lane does not go falsely red.

Usage::

    DEEPTUTOR_ENV_FILE=/path/to/.env python scripts/run_harness_trajectory_eval.py
    DEEPTUTOR_ENV_FILE=/path/to/.env python scripts/run_harness_trajectory_eval.py --check

Secrets are never read into Python beyond the LLM client; nothing is printed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PER_CASE_TIMEOUT_S = 120.0

# Representative cases. Kept LLM-only (no external RAG/web infra) so the gate is
# reliable: `reason` is a dedicated deep-reasoning LLM call, not an external tool.
CASES: list[dict[str, Any]] = [
    {
        "name": "plain_reasoning_no_tools",
        "user_message": "什么是傅里叶变换？用一句话回答。",
        "enabled_tools": [],
        "language": "zh",
        "metadata": {"turn_id": "d5-plain"},
    },
    {
        "name": "reason_tool_available",
        "user_message": "请严谨推理：若一个数的平方等于它本身，这个数可能是哪些？用一句话给结论。",
        "enabled_tools": ["reason"],
        "language": "zh",
        "metadata": {"turn_id": "d5-reason"},
    },
]


def _ensure_keyed_env() -> None:
    """Point DeepTutor at a populated .env if one is not already configured.

    Mirrors ``env_store``'s sibling-project convention (``../FastAPI20251222/.env``)
    so the deep gate runs portably wherever that sibling layout exists, without
    hard-coding an absolute path in ``eval/gates.yaml``. Honors an explicit
    ``DEEPTUTOR_ENV_FILE`` if already set.
    """
    import os

    if os.getenv("DEEPTUTOR_ENV_FILE") or os.getenv("DEEPTUTOR_ENV_PATH"):
        return
    sibling = PROJECT_ROOT.parent / "FastAPI20251222" / ".env"
    if sibling.exists():
        os.environ["DEEPTUTOR_ENV_FILE"] = str(sibling)


def _llm_configured() -> bool:
    from deeptutor.services.config import get_env_store

    store = get_env_store()
    host = store.get("LLM_HOST", "") or store.get("OPENAI_BASE_URL", "")
    key = store.get("LLM_API_KEY", "") or store.get("OPENAI_API_KEY", "")
    return bool(host and key)


async def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
    from deeptutor.core.context import UnifiedContext
    from deeptutor.core.stream import StreamEventType
    from deeptutor.core.stream_bus import StreamBus

    bus = StreamBus()
    events: list[Any] = []

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)

    context = UnifiedContext(
        session_id=f"d5-{case['name']}",
        user_message=case["user_message"],
        enabled_tools=list(case.get("enabled_tools") or []),
        language=case.get("language", "zh"),
        metadata=dict(case.get("metadata") or {}),
    )
    pipeline = AgenticChatPipeline(language=context.language)

    run_error: str | None = None
    try:
        await asyncio.wait_for(pipeline.run(context, bus), timeout=PER_CASE_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - surfaced as a case failure, not a crash
        run_error = f"{type(exc).__name__}: {str(exc)[:160]}"
    finally:
        await bus.close()
        await consumer

    seq = [event.type.value for event in events]
    tool_calls = [str(event.content) for event in events if event.type == StreamEventType.TOOL_CALL]
    result_events = [event for event in events if event.type == StreamEventType.RESULT]
    has_error = any(event.type == StreamEventType.ERROR for event in events)
    final_response = ""
    if result_events:
        final_response = str((result_events[-1].metadata or {}).get("response") or "")

    enabled = set(case.get("enabled_tools") or [])
    last_meaningful = next(
        (t for t in reversed(seq) if t not in {"progress", "stage_end", "done"}),
        "",
    )

    invariants: dict[str, bool] = {
        "no_run_error": run_error is None,
        "no_error_event": not has_error,
        "exactly_one_result": len(result_events) == 1,
        "final_response_nonempty": bool(final_response.strip()),
        "tools_within_enabled": set(tool_calls).issubset(enabled),
        "opens_with_stage_start": bool(seq) and seq[0] == "stage_start",
        "ends_with_result": last_meaningful == "result",
    }

    return {
        "name": case["name"],
        "run_error": run_error,
        "tool_calls": tool_calls,
        "result_count": len(result_events),
        "final_response_len": len(final_response.strip()),
        "event_count": len(seq),
        "invariants": invariants,
        "passed": all(invariants.values()),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="assert trajectory invariants (gate mode)")
    parser.parse_args()

    _ensure_keyed_env()
    if not _llm_configured():
        print(
            "SKIP harness trajectory eval: no LLM config resolved. "
            "Set DEEPTUTOR_ENV_FILE to a populated .env (keyed env required).",
            file=sys.stderr,
        )
        return 2

    failures = 0
    for case in CASES:
        record = await _run_case(case)
        status = "PASS" if record["passed"] else "FAIL"
        print(
            f"[{status}] {record['name']}: "
            f"tools={record['tool_calls']} results={record['result_count']} "
            f"resp_len={record['final_response_len']} events={record['event_count']}"
        )
        if not record["passed"]:
            failures += 1
            failed = [name for name, ok in record["invariants"].items() if not ok]
            print(f"        violated: {failed} run_error={record['run_error']}", file=sys.stderr)

    if failures:
        print(f"harness trajectory eval: FAIL ({failures}/{len(CASES)} cases)", file=sys.stderr)
        return 1
    print(f"harness trajectory eval: OK ({len(CASES)} cases, trajectory invariants hold)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
