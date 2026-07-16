"""Battle2 S5-T1: heartbeat phase-1 decision gets a deterministic gate.

The HEARTBEAT.md format contract (templates/HEARTBEAT.md) already promises
"If this file has no tasks other than headers and comments, the agent will
skip the heartbeat" — that judgment is deterministic parsing, not an LLM call.
The LLM only runs when real task text exists, and an LLM "skip" verdict is
memoized by content hash (_decide has no time input: same content ⇒ same
decision; "run" is never memoized).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import pytest

from deeptutor.tutorbot.heartbeat import service as hb
from deeptutor.tutorbot.providers.base import LLMResponse, ToolCallRequest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = (_REPO_ROOT / "deeptutor" / "tutorbot" / "templates" / "HEARTBEAT.md").read_text(
    encoding="utf-8"
)


class _CountingProvider:
    """Counts LLM calls; returns a fixed heartbeat tool decision."""

    def __init__(self, action: str = "skip", tasks: str = "") -> None:
        self.calls = 0
        self.seen_models: list[str] = []
        self._action = action
        self._tasks = tasks

    async def chat_with_retry(self, *, messages, tools, model):
        _ = (messages, tools)
        self.calls += 1
        self.seen_models.append(model)
        return LLMResponse(
            content=None,
            finish_reason="tool_calls",
            tool_calls=[
                ToolCallRequest(
                    id="heartbeat-decision",
                    name="heartbeat_decision",
                    arguments={"action": self._action, "tasks": self._tasks},
                )
            ],
        )


def _make_service(tmp_path: Path, provider: _CountingProvider, **kwargs) -> hb.HeartbeatService:
    return hb.HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="main-model",
        **kwargs,
    )


def _write_heartbeat(tmp_path: Path, content: str) -> None:
    (tmp_path / "HEARTBEAT.md").write_text(content, encoding="utf-8")


# ── extract_active_tasks (the deterministic contract) ───────────────────────


def test_template_extracts_empty() -> None:
    # The shipped template keeps every example task inside HTML comments.
    assert hb.extract_active_tasks(_TEMPLATE) == ""


def test_real_bullet_under_active_tasks_is_extracted() -> None:
    content = _TEMPLATE.replace(
        "## Active Tasks",
        "## Active Tasks\n\n- 每周三为学员生成一组 3 题建筑实务案例小测",
        1,
    )
    active = hb.extract_active_tasks(content)
    assert "案例小测" in active


def test_comments_and_headers_only_section_is_empty() -> None:
    content = "# Heartbeat\n\n## Active Tasks\n\n<!-- - 注释里的任务 -->\n\n## Completed\n\n- done\n"
    assert hb.extract_active_tasks(content) == ""


def test_no_active_tasks_header_falls_back_to_whole_document() -> None:
    # Hand-edited file without the canonical header: any real text keeps the
    # LLM path (fail-open to the old behavior).
    assert hb.extract_active_tasks("随手记的一条任务：每周复习") != ""
    assert hb.extract_active_tasks("# 只有标题\n<!-- 注释 -->\n") == ""


# ── _tick: zero LLM for template files, memoized skip, run never memoized ───


@pytest.mark.asyncio
async def test_tick_template_file_makes_no_llm_call(tmp_path: Path) -> None:
    provider = _CountingProvider(action="skip")
    service = _make_service(tmp_path, provider)
    _write_heartbeat(tmp_path, _TEMPLATE)

    await service._tick()

    assert provider.calls == 0


@pytest.mark.asyncio
async def test_tick_real_task_file_calls_llm_once(tmp_path: Path) -> None:
    provider = _CountingProvider(action="skip")
    service = _make_service(tmp_path, provider)
    _write_heartbeat(tmp_path, _TEMPLATE.replace("## Active Tasks", "## Active Tasks\n\n- 每周小测", 1))

    await service._tick()

    assert provider.calls == 1


@pytest.mark.asyncio
async def test_llm_skip_is_memoized_until_content_changes(tmp_path: Path) -> None:
    provider = _CountingProvider(action="skip")
    service = _make_service(tmp_path, provider)
    content = _TEMPLATE.replace("## Active Tasks", "## Active Tasks\n\n- 每周小测", 1)
    _write_heartbeat(tmp_path, content)

    await service._tick()
    await service._tick()
    assert provider.calls == 1  # second tick memo-skips

    _write_heartbeat(tmp_path, content.replace("每周小测", "每周两次小测"))
    await service._tick()
    assert provider.calls == 2  # content change invalidates the memo


@pytest.mark.asyncio
async def test_llm_run_is_never_memoized(tmp_path: Path) -> None:
    provider = _CountingProvider(action="run", tasks="出一组小测")
    executed: list[str] = []

    async def _execute(tasks: str) -> str:
        executed.append(tasks)
        return ""  # falsy response → no evaluate/notify path

    service = _make_service(tmp_path, provider, on_execute=_execute)
    _write_heartbeat(tmp_path, _TEMPLATE.replace("## Active Tasks", "## Active Tasks\n\n- 每周小测", 1))

    await service._tick()
    await service._tick()

    assert provider.calls == 2  # run must re-fire every tick
    assert len(executed) == 2


# ── trigger_now shares the deterministic gate ────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_now_template_file_makes_no_llm_call(tmp_path: Path) -> None:
    provider = _CountingProvider(action="run", tasks="x")
    service = _make_service(tmp_path, provider)
    _write_heartbeat(tmp_path, _TEMPLATE)

    assert await service.trigger_now() is None
    assert provider.calls == 0


# ── phase-1 decision model prefers the fast tier (phase 2 keeps self.model) ──


@pytest.mark.asyncio
async def test_decide_uses_fast_tier_model_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import deeptutor.services.llm.config as llm_config

    provider = _CountingProvider(action="skip")
    service = _make_service(tmp_path, provider)
    _write_heartbeat(tmp_path, _TEMPLATE.replace("## Active Tasks", "## Active Tasks\n\n- 每周小测", 1))

    monkeypatch.setattr(llm_config, "resolve_fast_tier_model", lambda: "fast-tier-x")
    await service._tick()
    assert provider.seen_models == ["fast-tier-x"]

    # Unconfigured fast tier ("") → fail-open to the main model.
    monkeypatch.setattr(llm_config, "resolve_fast_tier_model", lambda: "")
    _write_heartbeat(tmp_path, _TEMPLATE.replace("## Active Tasks", "## Active Tasks\n\n- 换个任务", 1))
    await service._tick()
    assert provider.seen_models[-1] == "main-model"
