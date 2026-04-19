# TutorBot Mode Policy Unified Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不制造第二套 authority 的前提下，把 `智能 / 快速 / 深度` 三种模式收口为单一 TutorBot authority 下的 turn policy，并补齐入口归一、运行时兼容、trace/feedback 观测与 contract 文档。

**Architecture:** 第一阶段只做“语义和链路收口”，不做高风险的 TutorBot per-turn provider/model 热切换。实现上新增一个轻量 `response_mode` 模块作为唯一模式归一与 policy 描述层；入口层写入 `requested/effective` 模式字段，TutorBot runtime 与非主链 `chat` pipeline 都只消费这一层，旧 `teaching_mode` 保留为兼容 alias 并在入口立即归一。观测层继续复用现有 `chat_mode` / `answer_mode` 统计口径，但补齐 `requested_response_mode`、`effective_response_mode` 与 `response_mode_degrade_reason`。

**Tech Stack:** FastAPI, Pydantic, TutorBot runtime, unified turn contract, pytest, SQLite session store, Supabase feedback metadata.

---

## Scope Check

这份 PRD 实际上包含两类子系统：

1. 模式 authority 收口、字段归一、runtime/trace/feedback 改造
2. TutorBot 每轮按模式切换底层模型

这两个子系统不适合放在同一个实现计划里直接硬做。原因是当前 `deeptutor/tutorbot/agent/loop.py` 在 bot loop 初始化时固定 `self.model`，并不是天然的 per-turn model runtime。把两者绑死在同一波改动里，风险会从“收口语义”升级成“重写执行引擎”。

因此本计划只覆盖第 1 类，明确把“per-turn 模型切换”降为后续单独计划。当前计划仍会把 `ModeExecutionPolicy` 里的模型意图字段和 trace 字段铺好，但不会在这一波直接改 TutorBot provider lifecycle。

## File Map

### Create

- `deeptutor/tutorbot/response_mode.py`
  - 单一模式归一层；定义 `TutorBotResponseMode`、`ModeExecutionPolicy`、入口兼容 alias 归一、观测字段写法。
- `tests/services/test_tutorbot_response_mode.py`
  - 纯单元测试；验证 `AUTO` / `teaching_mode` / `requested_response_mode` / fallback 规则。
- `tests/contracts/test_unified_turn_contract.py`
  - contract export 回归；防止 trace 字段更新后文档和导出结构漂移。

### Modify

- `deeptutor/api/routers/mobile.py`
  - 小程序入口写入 `requested_response_mode`，保留 `teaching_mode` 兼容 alias。
- `deeptutor/api/routers/unified_ws.py`
  - 统一入口兼容新的 interaction hint keys，并在 authenticated bind 时保持归一后的 hints。
- `deeptutor/services/session/turn_runtime.py`
  - 入口 hints 提取、session preferences、turn trace 统一改读 `response_mode` 层。
- `deeptutor/capabilities/tutorbot.py`
  - TutorBot capability 改用 `response_mode` 模块，写入 session/runtime metadata。
- `deeptutor/services/tutorbot/manager.py`
  - 运行时 trace metadata 改写为 `requested/effective` 模式语义，并统计 `actual_tool_rounds`。
- `deeptutor/tutorbot/agent/loop.py`
  - 运行时 instruction 与 fast-path 判定优先读 `effective_response_mode`。
- `deeptutor/agents/chat/agentic_pipeline.py`
  - 非主链 `chat` pipeline 兼容新字段，避免后续实验链路继续复活旧概念。
- `deeptutor/tutorbot/teaching_modes.py`
  - 退化为“教学风格/密度 instruction 工具层”；`normalize_teaching_mode()` 改为兼容 wrapper。
- `deeptutor/services/feedback_service.py`
  - `answer_mode` 继续保留，同时 metadata 补齐 `requested/effective` 模式字段。
- `deeptutor/contracts/unified_turn.py`
  - turn trace 词汇表加入 `requested_response_mode`、`effective_response_mode`、`response_mode_degrade_reason`、`actual_tool_rounds`。
- `CONTRACT.md`
  - 概念纪律更新为“response_mode 是模式 authority，teaching_mode 只是兼容 alias”。
- `contracts/turn.md`
  - turn contract 文档补充新 trace 字段和入口归一规则。
- `docs/zh/guide/unified-turn-contract.md`
  - 用户侧/前端集成说明同步。
- `tests/api/test_mobile_router.py`
  - 覆盖小程序入口模式字段归一。
- `tests/api/test_unified_ws_turn_runtime.py`
  - 覆盖 turn runtime 模式归一、session preference、trace metadata。
- `tests/services/test_tutorbot_teaching_modes.py`
  - 保留旧函数回归，同时验证 wrapper 没有回退到旧语义。
- `tests/services/test_feedback_service.py`
  - 验证 feedback metadata 的 answer/effective/requested 模式字段。

## Task 1: 建立单一 `response_mode` 模块

**Files:**
- Create: `deeptutor/tutorbot/response_mode.py`
- Test: `tests/services/test_tutorbot_response_mode.py`

- [ ] **Step 1: 写失败测试，先固定模式归一 contract**

```python
from deeptutor.tutorbot.response_mode import (
    build_mode_execution_policy,
    normalize_requested_response_mode,
    resolve_requested_response_mode,
)


def test_normalize_requested_response_mode_maps_auto_and_unknown_to_smart():
    assert normalize_requested_response_mode(None) == "smart"
    assert normalize_requested_response_mode("") == "smart"
    assert normalize_requested_response_mode("AUTO") == "smart"
    assert normalize_requested_response_mode("unknown") == "smart"


def test_resolve_requested_response_mode_prefers_explicit_config_then_new_hint_then_legacy_hint():
    assert resolve_requested_response_mode(chat_mode="deep", interaction_hints={}) == "deep"
    assert resolve_requested_response_mode(
        chat_mode="",
        interaction_hints={"requested_response_mode": "fast"},
    ) == "fast"
    assert resolve_requested_response_mode(
        chat_mode="",
        interaction_hints={"teaching_mode": "deep"},
    ) == "deep"


def test_build_mode_execution_policy_returns_expected_budget_shape():
    fast = build_mode_execution_policy("fast")
    smart = build_mode_execution_policy("smart")
    deep = build_mode_execution_policy("deep")

    assert fast.max_tool_rounds == 1
    assert fast.allow_deep_stage is False
    assert smart.max_tool_rounds == 2
    assert deep.allow_deep_stage is True
    assert deep.latency_budget_ms > smart.latency_budget_ms > fast.latency_budget_ms
```

- [ ] **Step 2: 跑测试确认当前失败**

Run: `.venv/bin/pytest tests/services/test_tutorbot_response_mode.py -v`

Expected: `ModuleNotFoundError: No module named 'deeptutor.tutorbot.response_mode'`

- [ ] **Step 3: 写最小实现，建立单一模式归一层**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

TutorBotResponseMode = Literal["smart", "fast", "deep"]


@dataclass(frozen=True)
class ModeExecutionPolicy:
    requested_mode: TutorBotResponseMode
    effective_mode: TutorBotResponseMode
    max_tool_rounds: int
    allow_deep_stage: bool
    response_density: Literal["short", "balanced", "detailed"]
    latency_budget_ms: int
    response_mode_degrade_reason: str = ""


def normalize_requested_response_mode(value: str | None) -> TutorBotResponseMode:
    normalized = str(value or "").strip().lower()
    if normalized in {"fast", "deep"}:
        return normalized
    return "smart"


def resolve_requested_response_mode(
    *,
    chat_mode: str | None,
    interaction_hints: Mapping[str, Any] | None,
) -> TutorBotResponseMode:
    if str(chat_mode or "").strip():
        return normalize_requested_response_mode(chat_mode)
    hints = dict(interaction_hints or {})
    return normalize_requested_response_mode(
        str(hints.get("requested_response_mode") or hints.get("teaching_mode") or "")
    )


def build_mode_execution_policy(mode: TutorBotResponseMode) -> ModeExecutionPolicy:
    if mode == "fast":
        return ModeExecutionPolicy(
            requested_mode="fast",
            effective_mode="fast",
            max_tool_rounds=1,
            allow_deep_stage=False,
            response_density="short",
            latency_budget_ms=6000,
        )
    if mode == "deep":
        return ModeExecutionPolicy(
            requested_mode="deep",
            effective_mode="deep",
            max_tool_rounds=4,
            allow_deep_stage=True,
            response_density="detailed",
            latency_budget_ms=20000,
        )
    return ModeExecutionPolicy(
        requested_mode="smart",
        effective_mode="smart",
        max_tool_rounds=2,
        allow_deep_stage=False,
        response_density="balanced",
        latency_budget_ms=12000,
    )
```

- [ ] **Step 4: 重新跑测试确认通过**

Run: `.venv/bin/pytest tests/services/test_tutorbot_response_mode.py -v`

Expected: `3 passed`

- [ ] **Step 5: 提交这一小步**

```bash
git add deeptutor/tutorbot/response_mode.py tests/services/test_tutorbot_response_mode.py
git commit -m "feat: add unified tutorbot response mode module"
```

## Task 2: 收口入口字段与 turn runtime 归一

**Files:**
- Modify: `deeptutor/api/routers/mobile.py:469-539`
- Modify: `deeptutor/api/routers/unified_ws.py:25-68`
- Modify: `deeptutor/services/session/turn_runtime.py:542-591`
- Modify: `deeptutor/services/session/turn_runtime.py:1794-1940`
- Modify: `tests/api/test_mobile_router.py`
- Modify: `tests/api/test_unified_ws_turn_runtime.py`

- [ ] **Step 1: 先写失败测试，固定入口兼容规则**

```python
def test_mobile_chat_start_turn_writes_requested_response_mode_and_legacy_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {"id": "session_mode_1", "title": "模式测试", "created_at": 1_700_000_100.0},
                {"id": "turn_mode_1", "status": "running", "capability": "tutorbot"},
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(mobile_module, "_resolve_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={"query": "讲透这道案例题", "mode": "DEEP"},
        )

    assert response.status_code == 200
    hints = captured["payload"]["config"]["interaction_hints"]
    assert captured["payload"]["config"]["chat_mode"] == "deep"
    assert hints["requested_response_mode"] == "deep"
    assert hints["teaching_mode"] == "deep"


@pytest.mark.asyncio
async def test_turn_runtime_prefers_requested_response_mode_hint_when_chat_mode_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            assert context.config_overrides["chat_mode"] == "fast"
            yield StreamEvent(type=StreamEventType.RESULT, source="chat", metadata={"response": "快答"})
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(build_memory_context=lambda: "", refresh_from_turn=_noop_refresh),
    )

    _, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "快点说重点",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_hints": {
                    "requested_response_mode": "fast",
                }
            },
        }
    )

    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/api/test_mobile_router.py::test_mobile_chat_start_turn_writes_requested_response_mode_and_legacy_alias tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_prefers_requested_response_mode_hint_when_chat_mode_missing -v`

Expected: `KeyError: 'requested_response_mode'` 或 `assert context.config_overrides["chat_mode"] == "fast"` 失败

- [ ] **Step 3: 改入口与 runtime，只在 ingress 做新旧字段归一**

```python
# deeptutor/api/routers/mobile.py
from deeptutor.tutorbot.response_mode import normalize_requested_response_mode


def _merge_interaction_hints(
    profile: str,
    hints: dict[str, Any] | None,
    *,
    current_info_required: bool,
    requested_response_mode: str,
) -> dict[str, Any]:
    merged = dict(hints or {})
    normalized_mode = normalize_requested_response_mode(requested_response_mode)
    merged["profile"] = str(profile or "tutorbot").strip().lower() or "tutorbot"
    merged.setdefault("product_surface", "wechat_miniprogram")
    merged.setdefault("entry_role", "tutorbot")
    merged.setdefault("subject_domain", "construction_exam")
    merged.setdefault("suppress_answer_reveal_on_generate", True)
    merged["requested_response_mode"] = normalized_mode
    merged.setdefault("teaching_mode", normalized_mode)
    if current_info_required:
        merged["current_info_required"] = True
    return merged


def _build_mobile_turn_payload(*, body: MobileStartTurnRequest, user_id: str, query: str) -> dict[str, Any]:
    requested_mode = normalize_requested_response_mode(body.mode)
    interaction_hints = _merge_interaction_hints(
        str(body.interaction_profile or "tutorbot").strip() or "tutorbot",
        body.interaction_hints,
        current_info_required=current_info_required,
        requested_response_mode=requested_mode,
    )
    config = {
        "chat_mode": requested_mode,
        "interaction_hints": interaction_hints,
        "billing_context": {"source": "wx_miniprogram", "user_id": user_id},
        "interaction_profile": interaction_profile,
    }
```

```python
# deeptutor/api/routers/unified_ws.py
_LEGACY_INTERACTION_HINT_KEYS = (
    "profile",
    "scene",
    "product_surface",
    "entry_role",
    "subject_domain",
    "teaching_mode",
    "requested_response_mode",
    "effective_response_mode",
    "response_mode_degrade_reason",
    "preferred_question_type",
    "allow_general_chat_fallback",
    "priorities",
    "suppress_answer_reveal_on_generate",
    "prefer_question_context_grading",
    "prefer_concept_teaching_slots",
    "current_info_required",
    "grounding_reasons",
    "textbook_delta_query",
)
```

```python
# deeptutor/services/session/turn_runtime.py
from deeptutor.tutorbot.response_mode import (
    normalize_requested_response_mode,
    resolve_requested_response_mode,
)


def _extract_interaction_hints(config: dict[str, Any] | None) -> dict[str, Any] | None:
    ...
    requested_response_mode = normalize_requested_response_mode(
        raw.get("requested_response_mode") or raw.get("teaching_mode")
    )
    hints = {
        "profile": profile,
        "scene": str(raw.get("scene", "") or "").strip().lower(),
        "product_surface": str(raw.get("product_surface", "") or "").strip().lower(),
        "entry_role": str(raw.get("entry_role", "") or "").strip().lower(),
        "subject_domain": str(raw.get("subject_domain", "") or "").strip().lower(),
        "requested_response_mode": requested_response_mode,
        "teaching_mode": str(raw.get("teaching_mode") or requested_response_mode).strip().lower(),
        "preferred_question_type": preferred_question_type,
        "allow_general_chat_fallback": raw.get("allow_general_chat_fallback", True) is not False,
        "priorities": normalized_priorities,
    }
    ...


def _infer_chat_mode_from_interaction_hints(hints: dict[str, Any] | None) -> str | None:
    if not isinstance(hints, dict):
        return None
    return resolve_requested_response_mode(chat_mode="", interaction_hints=hints)
```

- [ ] **Step 4: 重新跑入口与 runtime 测试**

Run: `.venv/bin/pytest tests/api/test_mobile_router.py::test_mobile_chat_start_turn_writes_requested_response_mode_and_legacy_alias tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_prefers_requested_response_mode_hint_when_chat_mode_missing -v`

Expected: `2 passed`

- [ ] **Step 5: 提交这一小步**

```bash
git add deeptutor/api/routers/mobile.py deeptutor/api/routers/unified_ws.py deeptutor/services/session/turn_runtime.py tests/api/test_mobile_router.py tests/api/test_unified_ws_turn_runtime.py
git commit -m "feat: normalize response mode at ingress and turn runtime"
```

## Task 3: 让 TutorBot runtime 与 chat pipeline 只消费 `response_mode`

**Files:**
- Modify: `deeptutor/capabilities/tutorbot.py:40-257`
- Modify: `deeptutor/services/tutorbot/manager.py:791-850`
- Modify: `deeptutor/tutorbot/agent/loop.py:1244-1265`
- Modify: `deeptutor/agents/chat/agentic_pipeline.py:2678-2918`
- Modify: `deeptutor/tutorbot/teaching_modes.py:92-107`
- Modify: `tests/services/test_tutorbot_teaching_modes.py`

- [ ] **Step 1: 先写失败测试，固定 runtime 必须优先读新字段**

```python
from deeptutor.tutorbot.teaching_modes import get_teaching_mode_instruction, normalize_teaching_mode
from deeptutor.tutorbot.response_mode import resolve_requested_response_mode


def test_legacy_normalize_teaching_mode_is_now_only_a_compat_wrapper():
    assert normalize_teaching_mode("AUTO") == "smart"
    assert normalize_teaching_mode("fast") == "fast"


def test_response_mode_resolution_prefers_new_requested_field_over_legacy_alias():
    assert resolve_requested_response_mode(
        chat_mode="",
        interaction_hints={
            "requested_response_mode": "fast",
            "teaching_mode": "deep",
        },
    ) == "fast"


def test_get_teaching_mode_instruction_keeps_fast_and_deep_behavior():
    assert "400 字左右" in get_teaching_mode_instruction("fast")
    assert "案例题" in get_teaching_mode_instruction("deep")
```

- [ ] **Step 2: 跑测试确认当前失败或未覆盖**

Run: `.venv/bin/pytest tests/services/test_tutorbot_teaching_modes.py -v`

Expected: 新增断言失败，说明 runtime 还没有优先读 `requested_response_mode`

- [ ] **Step 3: 改 TutorBot capability、manager、loop 和 chat pipeline**

```python
# deeptutor/capabilities/tutorbot.py
from deeptutor.tutorbot.response_mode import (
    build_mode_execution_policy,
    resolve_requested_response_mode,
)


@staticmethod
def _response_mode(context: UnifiedContext) -> str:
    hints = context.metadata.get("interaction_hints", {}) if isinstance(context.metadata, dict) else {}
    return resolve_requested_response_mode(
        chat_mode=str(context.config_overrides.get("chat_mode") or ""),
        interaction_hints=hints if isinstance(hints, dict) else {},
    )


async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
    ...
    requested_mode = self._response_mode(context)
    policy = build_mode_execution_policy(requested_mode)
    ...
    session_metadata["requested_response_mode"] = policy.requested_mode
    session_metadata["effective_response_mode"] = policy.effective_mode
    session_metadata["response_mode_degrade_reason"] = policy.response_mode_degrade_reason
    session_metadata["teaching_mode"] = policy.effective_mode
    session_metadata["mode_execution_policy"] = {
        "max_tool_rounds": policy.max_tool_rounds,
        "allow_deep_stage": policy.allow_deep_stage,
        "response_density": policy.response_density,
        "latency_budget_ms": policy.latency_budget_ms,
    }
    ...
    response = await manager.send_message(..., mode=policy.effective_mode, session_metadata=session_metadata)
```

```python
# deeptutor/services/tutorbot/manager.py
trace_metadata = {
    ...
    "requested_response_mode": str(merged_metadata.get("requested_response_mode") or mode).strip(),
    "effective_response_mode": str(merged_metadata.get("effective_response_mode") or mode).strip(),
    "response_mode_degrade_reason": str(merged_metadata.get("response_mode_degrade_reason") or "").strip(),
    "teaching_mode": mode,
}
runtime_metadata = dict(merged_metadata)
runtime_metadata["teaching_mode"] = mode
runtime_metadata["effective_response_mode"] = str(
    merged_metadata.get("effective_response_mode") or mode
).strip()
```

```python
# deeptutor/tutorbot/agent/loop.py
runtime_mode = (
    runtime_metadata.get("effective_response_mode")
    or runtime_metadata.get("requested_response_mode")
    or runtime_metadata.get("teaching_mode")
)
runtime_instruction_parts = [
    get_teaching_mode_instruction(runtime_mode),
    get_markdown_style_instruction(),
    get_practice_generation_instruction(
        user_message=current_message,
        suppress_answer_reveal_on_generate=bool(runtime_metadata.get("suppress_answer_reveal_on_generate")),
    ),
]
```

```python
# deeptutor/agents/chat/agentic_pipeline.py
def _configured_teaching_mode(self, context: UnifiedContext) -> str:
    hints = self._interaction_hints(context)
    requested_mode = str(hints.get("requested_response_mode") or "").strip().lower()
    if requested_mode in {"fast", "deep", "smart"}:
        return requested_mode
    hinted_mode = str(hints.get("teaching_mode") or "").strip().lower()
    if hinted_mode in {"fast", "deep", "smart"}:
        return hinted_mode
    runtime_mode = str(context.config_overrides.get("chat_mode") or "").strip().lower()
    return runtime_mode if runtime_mode in {"fast", "deep", "smart"} else ""
```

```python
# deeptutor/tutorbot/teaching_modes.py
from deeptutor.tutorbot.response_mode import normalize_requested_response_mode


def normalize_teaching_mode(value: str | None) -> TutorBotTeachingMode:
    return normalize_requested_response_mode(value)
```

- [ ] **Step 4: 跑 TutorBot 相关回归**

Run: `.venv/bin/pytest tests/services/test_tutorbot_response_mode.py tests/services/test_tutorbot_teaching_modes.py -v`

Expected: `all passed`

- [ ] **Step 5: 提交这一小步**

```bash
git add deeptutor/capabilities/tutorbot.py deeptutor/services/tutorbot/manager.py deeptutor/tutorbot/agent/loop.py deeptutor/agents/chat/agentic_pipeline.py deeptutor/tutorbot/teaching_modes.py tests/services/test_tutorbot_teaching_modes.py
git commit -m "feat: wire tutorbot runtime to unified response mode"
```

## Task 4: 补齐 trace 与 feedback 观测字段

**Files:**
- Modify: `deeptutor/contracts/unified_turn.py:258-311`
- Modify: `deeptutor/services/session/turn_runtime.py:2302-2323`
- Modify: `deeptutor/services/tutorbot/manager.py:791-846`
- Modify: `deeptutor/services/feedback_service.py:60-129`
- Modify: `tests/services/test_feedback_service.py`

- [ ] **Step 1: 先写失败测试，固定 feedback metadata 与 trace contract**

```python
from deeptutor.services.feedback_service import build_mobile_feedback_row, normalize_feedback_record


def test_build_mobile_feedback_row_keeps_answer_mode_and_requested_effective_modes() -> None:
    row = build_mobile_feedback_row(
        user_id="student_demo",
        session_id="session_1",
        message_id="42",
        rating=1,
        answer_mode="deep",
        requested_response_mode="deep",
        effective_response_mode="smart",
        response_mode_degrade_reason="provider_timeout",
    )

    assert row["metadata"]["answer_mode"] == "DEEP"
    assert row["metadata"]["requested_response_mode"] == "DEEP"
    assert row["metadata"]["effective_response_mode"] == "SMART"
    assert row["metadata"]["response_mode_degrade_reason"] == "provider_timeout"


def test_normalize_feedback_record_reads_requested_and_effective_modes_from_metadata() -> None:
    record = normalize_feedback_record(
        {
            "id": "feedback_1",
            "created_at": "2026-04-19T10:00:00+08:00",
            "user_id": "",
            "conversation_id": "",
            "message_id": "",
            "rating": 1,
            "reason_tags": [],
            "comment": "",
            "metadata": {
                "answer_mode": "DEEP",
                "requested_response_mode": "DEEP",
                "effective_response_mode": "SMART",
                "response_mode_degrade_reason": "provider_timeout",
            },
        }
    )

    assert record["answer_mode"] == "DEEP"
    assert record["requested_response_mode"] == "DEEP"
    assert record["effective_response_mode"] == "SMART"
    assert record["response_mode_degrade_reason"] == "provider_timeout"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/services/test_feedback_service.py -v`

Expected: `TypeError: build_mobile_feedback_row() got an unexpected keyword argument 'requested_response_mode'`

- [ ] **Step 3: 改 trace 字段与 feedback metadata**

```python
# deeptutor/contracts/unified_turn.py
UNIFIED_TURN_TRACE_FIELDS: tuple[str, ...] = (
    "session_id",
    "turn_id",
    "capability",
    "execution_engine",
    "bot_id",
    "tool_calls",
    "sources",
    "authority_applied",
    "source",
    "interaction_profile",
    "chat_mode",
    "requested_response_mode",
    "effective_response_mode",
    "response_mode_degrade_reason",
    "actual_tool_rounds",
    ...
)
```

```python
# deeptutor/services/session/turn_runtime.py
trace_metadata["chat_mode"] = str(request_config.get("chat_mode") or "").strip()
trace_metadata["requested_response_mode"] = str(
    (interaction_hints or {}).get("requested_response_mode") or trace_metadata["chat_mode"]
).strip()
trace_metadata["effective_response_mode"] = str(
    request_config.get("chat_mode")
    or (interaction_hints or {}).get("effective_response_mode")
    or trace_metadata["requested_response_mode"]
).strip()
trace_metadata["response_mode_degrade_reason"] = str(
    (interaction_hints or {}).get("response_mode_degrade_reason") or ""
).strip()
```

```python
# deeptutor/services/tutorbot/manager.py
tool_trace_summary: dict[str, Any] = {
    "tool_calls": [],
    "sources": [],
    "authority_applied": False,
    "exact_question": {},
    "rag_rounds": [],
    "rag_saturation": {},
}
...
metadata={
    ...
    "actual_tool_rounds": len(tool_trace_summary["tool_calls"]),
}
```

```python
# deeptutor/services/feedback_service.py
def build_mobile_feedback_row(
    *,
    user_id: str,
    session_id: str | None = None,
    message_id: str | None = None,
    rating: int = 0,
    reason_tags: list[str] | None = None,
    comment: str = "",
    answer_mode: str = "AUTO",
    requested_response_mode: str = "",
    effective_response_mode: str = "",
    response_mode_degrade_reason: str = "",
) -> dict[str, Any]:
    ...
    metadata = {
        "answer_mode": normalized_answer_mode,
        "requested_response_mode": str(requested_response_mode or "").strip().upper(),
        "effective_response_mode": str(effective_response_mode or "").strip().upper(),
        "response_mode_degrade_reason": str(response_mode_degrade_reason or "").strip(),
        "feedback_source": "wx_miniprogram_message_actions",
        "surface": "wx_miniprogram",
        "platform": "wechat_miniprogram",
        "source": "wx_miniprogram",
    }


def normalize_feedback_record(row: Mapping[str, Any]) -> dict[str, Any]:
    ...
    return {
        ...
        "answer_mode": _metadata_str(normalized_metadata, "answer_mode"),
        "requested_response_mode": _metadata_str(normalized_metadata, "requested_response_mode"),
        "effective_response_mode": _metadata_str(normalized_metadata, "effective_response_mode"),
        "response_mode_degrade_reason": _metadata_str(
            normalized_metadata,
            "response_mode_degrade_reason",
        ),
        ...
    }
```

- [ ] **Step 4: 跑观测相关回归**

Run: `.venv/bin/pytest tests/services/test_feedback_service.py tests/api/test_unified_ws_turn_runtime.py -v`

Expected: `all passed`

- [ ] **Step 5: 提交这一小步**

```bash
git add deeptutor/contracts/unified_turn.py deeptutor/services/session/turn_runtime.py deeptutor/services/tutorbot/manager.py deeptutor/services/feedback_service.py tests/services/test_feedback_service.py
git commit -m "feat: add unified response mode observability fields"
```

## Task 5: 更新 contract 文档并加 export 回归

**Files:**
- Create: `tests/contracts/test_unified_turn_contract.py`
- Modify: `CONTRACT.md`
- Modify: `contracts/turn.md`
- Modify: `docs/zh/guide/unified-turn-contract.md`

- [ ] **Step 1: 先写失败测试，锁住 contract export 字段**

```python
from deeptutor.contracts.unified_turn import export_unified_turn_contract


def test_unified_turn_contract_exports_response_mode_trace_fields() -> None:
    contract = export_unified_turn_contract()
    trace_fields = set(contract["trace_fields"])

    assert "requested_response_mode" in trace_fields
    assert "effective_response_mode" in trace_fields
    assert "response_mode_degrade_reason" in trace_fields
    assert "actual_tool_rounds" in trace_fields
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/contracts/test_unified_turn_contract.py -v`

Expected: `AssertionError` for missing trace fields

- [ ] **Step 3: 更新 contract 文档，写明新旧字段纪律**

```markdown
<!-- CONTRACT.md -->
- `response_mode` 是模式 authority 概念，表示 `fast / smart / deep` 单轮执行策略。
- `teaching_mode` 只保留为兼容 alias；必须在统一入口层立即归一化为 `requested_response_mode`。
- 禁止让 `teaching_mode` 继续承担身份、知识链、工具路由或执行引擎语义。
```

```markdown
<!-- contracts/turn.md -->
## Interaction Hints Normalization

- ingress 可以暂时接收 `teaching_mode`
- runtime 持久化和 trace 必须写入：
  - `requested_response_mode`
  - `effective_response_mode`
  - `response_mode_degrade_reason`
- `chat_mode` 保留为 capability config 字段，不再承担概念解释职责
```

```markdown
<!-- docs/zh/guide/unified-turn-contract.md -->
### 模式字段

- 客户端可以继续传 `mode -> chat_mode`
- 若需要 interaction hints，同步写入 `requested_response_mode`
- 旧 `teaching_mode` 仅用于兼容老客户端，不建议新增依赖
```

- [ ] **Step 4: 跑 contract export 回归并做一次全量小套件**

Run: `.venv/bin/pytest tests/contracts/test_unified_turn_contract.py tests/services/test_tutorbot_response_mode.py tests/services/test_tutorbot_teaching_modes.py tests/services/test_feedback_service.py tests/api/test_mobile_router.py tests/api/test_unified_ws_turn_runtime.py -v`

Expected: `all passed`

- [ ] **Step 5: 提交这一小步**

```bash
git add CONTRACT.md contracts/turn.md docs/zh/guide/unified-turn-contract.md tests/contracts/test_unified_turn_contract.py
git commit -m "docs: document unified tutorbot response mode contract"
```

## Verification Checklist

- `requested_response_mode` 在 mobile ingress、unified ws、turn runtime、TutorBot runtime、feedback metadata、trace export 六处都可见。
- 旧 `teaching_mode` 仍可被老客户端发送，但不会再成为运行时一等控制字段。
- TutorBot 主链与 `chat` pipeline 都优先读 `requested_response_mode`。
- `answer_mode` 统计口径仍可继续使用，不破坏现有 BI 聚合。
- 没有引入新的 websocket、session key、heartbeat key 或第二套 writeback pipeline。

## Explicit Non-Goals For This Plan

- 不在这一波直接实现 TutorBot per-turn model override。
- 不在这一波重写 `deep_question` / `deep_solve` 执行引擎。
- 不在这一波引入新的前端模式按钮或 UX 大改。
- 不在这一波把 `chat_mode` 从 public capability config 中删除；只收窄其概念职责。

## Self-Review

### 1. Spec coverage

- PRD 的“单一 authority”由 Task 2 和 Task 3 落地。
- PRD 的“概念归一与字段纪律”由 Task 1、Task 2、Task 5 落地。
- PRD 的“高风险场景中的受控降级/观测”先由 Task 3、Task 4 提供字段与 trace 支撑。
- PRD 的“BI/feedback/observability”由 Task 4 落地。
- PRD 的“contract/文档更新”由 Task 5 落地。
- 唯一主动拆出的缺口是 per-turn model override；这不是遗漏，而是有意拆成第二个独立计划。

### 2. Placeholder scan

- 已检查，没有 `TODO`、`TBD`、`implement later`、`similar to Task N` 这类占位写法。

### 3. Type consistency

- 统一使用 `requested_response_mode`、`effective_response_mode`、`response_mode_degrade_reason`。
- 旧字段 `teaching_mode` 仅作为 alias，不再在计划后半段引入第二套命名。

Plan complete and saved to `docs/superpowers/plans/2026-04-19-tutorbot-mode-policy-unified-authority.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
