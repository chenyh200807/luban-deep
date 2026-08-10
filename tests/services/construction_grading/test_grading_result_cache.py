"""Same-question-same-answer grading-result cache — key authority, seam behaviour, refusals.

Hermetic: the "LLM" is a counting async stub. Proves the four acceptance claims of the design
(codex 判分核不变量审计 §3.2/§3.3):

  1. a second identical grading costs ZERO LLM calls and replays a field-equivalent event;
  2. the key moves when rubric / model / scope / provenance / prompt-version material moves;
  3. the kill switch bypasses the seam entirely;
  4. degraded / coverage-unknown results are NEVER frozen, and the stored value carries no identity.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from deeptutor.services.construction_grading import grading_result_cache as C
from deeptutor.services.construction_grading import rubric_grader_v1 as G


def _rubric() -> list[dict]:
    return [
        {"point_id": "P1", "text": "编制专项施工方案", "score": 2.0, "policy": "list",
         "required_terms": [], "authority_source": "official_answer"},
        {"point_id": "P2", "text": "组织专家论证", "score": 3.0, "policy": "exact_required",
         "required_terms": ["专家论证"], "authority_source": "official_answer"},
    ]


def _identity(**overrides) -> dict:
    identity = {
        "rubric_provenance": "compiled_rubric",
        "nominal_full_score": 5.0,
        "coverage_state": "known",
        "effective_scope_cap": 5.0,
        "bank_slot": "legacy",
        "bank_content_hash": "hash-a",
        "extraction_prompt_version": "rubric_extraction_prompt.v2",
        "adjudication_prompt_version": "batch_adjudication_prompt.v1",
        "provider_binding": "deepseek:https://api.deepseek.com",
        "grader_algorithm_version": "rubric_grader_v1.g1",
    }
    identity.update(overrides)
    return identity


def _key(**overrides) -> str:
    args = {
        "question_identity": "Q1",
        "student_answer": "编制专项施工方案并组织专家论证",
        "rubric_points": _rubric(),
        "model": "deepseek-chat",
        "identity": _identity(),
    }
    args.update(overrides)
    return C.build_cache_key(**args)


class _CountingJudge:
    """One batch call returns a hit for every idx it is asked about."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, **kw):
        self.calls += 1
        prompt = str(kw.get("prompt") or "")
        count = prompt.split("\n\n学生作答", 1)[0].count('"idx":')
        return "[" + ",".join(f'{{"idx":{i},"status":"hit"}}' for i in range(1, count + 1)) + "]"


def _grade(judge, *, student_id: str = "stu_1", **overrides) -> dict:
    args = {
        "qid": "Q1",
        "student_answer": "编制专项施工方案并组织专家论证",
        "rubric_points": _rubric(),
        "complete_fn": judge,
        "api_key": "k",
        "student_id": student_id,
        "model": "deepseek-chat",
        "cache_identity": _identity(),
    }
    args.update(overrides)
    return asyncio.run(G.grade_with_batch_judge_async(**args))


# ── 1. same key twice -> zero LLM calls, field-equivalent event ───────────────────────────────────
@pytest.fixture(autouse=True)
def _cache_opt_in(monkeypatch: pytest.MonkeyPatch):
    """缓存 2026-08-01 合流裁决为 opt-in（默认关）：本文件测的是"启用态"行为，
    统一显式开；默认位语义由 test_cache_is_off_by_default 单独钉。"""
    monkeypatch.setenv("LUBAN_GRADING_RESULT_CACHE", "1")
    yield


def test_same_question_same_answer_replays_without_any_llm_call() -> None:
    judge = _CountingJudge()
    first = _grade(judge)
    assert judge.calls == 1
    assert first["grading_cache"] == "miss"

    second = _grade(judge)
    assert judge.calls == 1, "second identical grading must not call the LLM at all"
    assert second["grading_cache"] == "hit"

    markers = {"grading_cache", "cache_key_version", "grading_cache_key"}
    assert {k: v for k, v in first.items() if k not in markers} == {
        k: v for k, v in second.items() if k not in markers
    }
    assert second["awarded_score"] == first["awarded_score"] == 5.0
    assert second["cache_key_version"] == C.CACHE_KEY_VERSION


def test_cache_hit_rebinds_the_current_turn_identity() -> None:
    judge = _CountingJudge()
    _grade(judge, student_id="stu_first")
    replayed = _grade(judge, student_id="stu_second")

    assert judge.calls == 1
    assert replayed["grading_cache"] == "hit"
    # the cached FACT is identity-free; the CURRENT turn's learner owns the replayed event
    assert replayed["student_id"] == "stu_second"


def test_stored_value_carries_no_student_or_trace_identity() -> None:
    event = {
        "event_type": "case_grading_completed", "student_id": "stu_1", "session_id": "sess_1",
        "trace_id": "trace_1", "turn_id": "turn_1", "awarded_score": 5.0, "max_score": 5.0,
        "grading_cache": "miss", "cache_key_version": C.CACHE_KEY_VERSION,
    }
    stored = C.strip_identity(event)
    for field in ("student_id", "session_id", "trace_id", "turn_id", "grading_cache",
                  "cache_key_version"):
        assert field not in stored
    assert stored["awarded_score"] == 5.0
    assert event["student_id"] == "stu_1", "strip must not mutate the live event"


# ── 2. key sensitivity ───────────────────────────────────────────────────────────────────────────
def test_key_changes_when_rubric_text_or_score_or_policy_changes() -> None:
    baseline = _key()
    for mutate in (
        lambda pts: pts[0].update({"text": "编制专项施工方案(修订)"}),
        lambda pts: pts[0].update({"score": 3.0}),
        lambda pts: pts[0].update({"policy": "exact_required"}),
        lambda pts: pts[1].update({"required_terms": ["论证"]}),
        lambda pts: pts[0].update({"authority_source": "textbook_cited"}),
        lambda pts: pts.reverse(),
        lambda pts: pts.pop(),
    ):
        points = _rubric()
        mutate(points)
        assert _key(rubric_points=points) != baseline


@pytest.mark.parametrize("field,value", [
    ("nominal_full_score", 8.0),
    ("coverage_state", "single"),
    ("effective_scope_cap", 2.5),
    ("rubric_provenance", "on_the_fly_reference"),
    ("bank_slot", "pgo"),
    ("bank_content_hash", "hash-b"),
    ("extraction_prompt_version", "rubric_extraction_prompt.v3"),
    ("adjudication_prompt_version", "batch_adjudication_prompt.v2"),
    ("provider_binding", "dashscope:https://dashscope.aliyuncs.com"),
    ("grader_algorithm_version", "rubric_grader_v1.g2"),
])
def test_key_changes_when_any_authority_or_version_fact_changes(field: str, value) -> None:
    assert _key(identity=_identity(**{field: value})) != _key()


def test_key_changes_with_model_question_and_answer() -> None:
    assert _key(model="deepseek-reasoner") != _key()
    assert _key(question_identity="Q2") != _key()
    assert _key(student_answer="完全不同的作答") != _key()


def test_answer_normalization_is_conservative_and_versioned(monkeypatch: pytest.MonkeyPatch) -> None:
    # NFKC + newline unification + OUTER strip collapse to the same key …
    assert _key(student_answer="  编制专项施工方案并组织专家论证\r\n") == _key()
    assert C.normalize_student_answer("ＡＢ\r\nc ") == "AB\nc"
    # … but interior whitespace/structure is answer semantics and must NOT be normalized away.
    assert _key(student_answer="编制专项施工方案 并组织专家论证") != _key()
    assert _key(student_answer="编制专项施工方案\n并组织专家论证") != _key()
    # the policy version and the cache version are themselves key components, so tightening either
    # invalidates every old entry instead of silently re-binding it to a new normalization
    baseline = _key()
    monkeypatch.setattr(C, "ANSWER_NORMALIZATION_VERSION", "answer_norm.v2")
    assert _key() != baseline
    monkeypatch.setattr(C, "CACHE_KEY_VERSION", "grading_result_cache.v2")
    assert _key() != baseline


def test_batch_key_hashes_ordered_child_keys_not_the_parent_qid() -> None:
    assert C.batch_cache_key(["a", "b"]) != C.batch_cache_key(["b", "a"])
    assert C.batch_cache_key(["a", "b"]) == C.batch_cache_key(["a", "b"])


# ── 3. kill switch ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("off_value", ["0", "false", "off", "no", "OFF"])
def test_kill_switch_bypasses_the_seam(monkeypatch: pytest.MonkeyPatch, off_value: str) -> None:
    monkeypatch.setenv("LUBAN_GRADING_RESULT_CACHE", off_value)
    judge = _CountingJudge()
    first = _grade(judge)
    second = _grade(judge)

    assert judge.calls == 2, "kill switch off must re-adjudicate every time"
    assert first["grading_cache"] == second["grading_cache"] == "bypass"
    assert "grading_cache_key" not in first


def test_cache_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """opt-in 语义（合流裁决）：默认关——新缓存默认 ON 会在配好共享后端之前就
    静默改判分重放语义（含 eval 与渐进发射观测，见 stage-hook 测试撞车实录）。"""
    monkeypatch.delenv("LUBAN_GRADING_RESULT_CACHE", raising=False)
    assert C.cache_enabled() is False
    monkeypatch.setenv("LUBAN_GRADING_RESULT_CACHE", "1")
    assert C.cache_enabled() is True


# ── 4. refusals: never freeze an untrustworthy result ────────────────────────────────────────────
def test_degraded_result_is_never_cached() -> None:
    async def _boom(**_kw):
        raise RuntimeError("llm down")

    degraded = _grade(_boom)
    assert degraded["degraded"] is True
    assert C.is_cacheable_event(degraded) is False

    # the outage must not become a sticky 0 — the next call really re-adjudicates
    judge = _CountingJudge()
    recovered = _grade(judge)
    assert judge.calls == 1
    assert recovered["grading_cache"] == "miss"
    assert recovered["awarded_score"] == 5.0


@pytest.mark.parametrize("coverage_state", ["unknown", "error", "UNKNOWN"])
def test_unknown_or_error_coverage_is_never_cached(coverage_state: str) -> None:
    assert C.is_cacheable_event({
        "event_type": "case_grading_completed", "degraded": False,
        "awarded_score": 3.0, "max_score": 5.0, "coverage_state": coverage_state,
    }) is False


def test_only_terminal_finite_completed_events_are_cacheable() -> None:
    good = {"event_type": "case_grading_completed", "degraded": False,
            "awarded_score": 3.0, "max_score": 5.0, "coverage_state": "known"}
    assert C.is_cacheable_event(good) is True
    assert C.is_cacheable_event({**good, "event_type": "case_grading_unavailable"}) is False
    assert C.is_cacheable_event({**good, "awarded_score": float("nan")}) is False
    assert C.is_cacheable_event({**good, "max_score": float("inf")}) is False
    assert C.is_cacheable_event({**good, "coverage": float("nan")}) is False
    assert C.is_cacheable_event({"status": "unavailable"}) is False
    assert C.is_cacheable_event(None) is False


# ── 5. observability lockstep (前车之鉴: a key exported in only one of the two places vanishes) ──
def test_cache_marker_is_exported_in_both_metadata_places() -> None:
    from deeptutor.services.construction_grading.case_output_policy import (
        CASE_GRADING_TURN_METADATA_KEYS,
    )
    from deeptutor.tutorbot.agent.loop import AgentLoop

    source = inspect.getsource(AgentLoop._v1_case_stream_plan)
    for event_key, metadata_key in (
        ("grading_cache", "case_grading_cache"),
        ("cache_key_version", "case_grading_cache_key_version"),
        ("grading_cache_key", "case_grading_cache_key"),
    ):
        assert metadata_key in CASE_GRADING_TURN_METADATA_KEYS, "missing from the turn EXPORT keys"
        assert f'"{event_key}", "{metadata_key}"' in source, "missing from the event→metadata mapping"


# ── 6. shared (Valkey) backend path ──────────────────────────────────────────────────────────────
class _FakeValkey:
    """Minimal async stand-in for the production Valkey client (get/set with ex)."""

    def __init__(self, *, fail: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail = fail

    async def get(self, key: str):
        if self.fail:
            raise RuntimeError("valkey down")
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        if self.fail:
            raise RuntimeError("valkey down")
        self.store[key] = value
        self.ttls[key] = int(ex or 0)


def _use_fake_valkey(monkeypatch: pytest.MonkeyPatch, fake: _FakeValkey) -> None:
    monkeypatch.setattr(C, "_redis_client", lambda: fake)


def test_shared_backend_round_trips_json_with_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeValkey()
    _use_fake_valkey(monkeypatch, fake)
    judge = _CountingJudge()

    first = _grade(judge)
    assert judge.calls == 1
    assert len(fake.store) == 1
    stored_key = next(iter(fake.store))
    assert stored_key.startswith("luban:grading_result:")
    assert C.CACHE_KEY_VERSION in stored_key, "the key namespace is version-scoped"
    assert fake.ttls[stored_key] == int(C.cache_ttl_seconds())
    assert "stu_1" not in fake.store[stored_key], "no learner identity in the shared store"

    second = _grade(judge)
    assert judge.calls == 1, "the shared store must serve the replay across workers"
    assert second["grading_cache"] == "hit"
    assert second["awarded_score"] == first["awarded_score"]


def test_shared_backend_failure_degrades_to_fresh_adjudication(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_fake_valkey(monkeypatch, _FakeValkey(fail=True))
    judge = _CountingJudge()

    first = _grade(judge)
    second = _grade(judge)

    # a half-dead Valkey must cost extra LLM calls, never a broken turn or a wrong score
    assert judge.calls == 2
    assert first["awarded_score"] == second["awarded_score"] == 5.0
    assert second["grading_cache"] == "miss"


def test_concurrent_workers_write_the_same_idempotent_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """No distributed single-flight: two workers racing the same key write the SAME value, so
    last-write-wins is correct (audit §3.3 risk 3)."""
    fake = _FakeValkey()
    _use_fake_valkey(monkeypatch, fake)

    async def _race():
        judge = _CountingJudge()
        return await asyncio.gather(*[
            G.grade_with_batch_judge_async(
                qid="Q1", student_answer="编制专项施工方案并组织专家论证", rubric_points=_rubric(),
                complete_fn=judge, api_key="k", student_id=f"stu_{i}", model="deepseek-chat",
                cache_identity=_identity(),
            ) for i in range(4)
        ])

    events = asyncio.run(_race())
    assert len({e["awarded_score"] for e in events}) == 1
    assert len(fake.store) == 1


def test_backend_url_prefers_explicit_then_reuses_the_rate_limit_valkey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LUBAN_GRADING_RESULT_CACHE_URL", raising=False)
    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_BACKEND", "sqlite")
    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_REDIS_URL", "redis://valkey:6379/0")
    assert C._resolve_backend_url() == "", "no shared store unless the rate-limit backend is redis"

    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_BACKEND", "redis")
    assert C._resolve_backend_url() == "redis://valkey:6379/0"

    monkeypatch.setenv("LUBAN_GRADING_RESULT_CACHE_URL", "redis://valkey:6379/3")
    assert C._resolve_backend_url() == "redis://valkey:6379/3", "explicit URL wins"


def test_ttl_zero_disables_writes_and_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUBAN_GRADING_RESULT_CACHE_TTL_SECONDS", "0")
    judge = _CountingJudge()
    _grade(judge)
    _grade(judge)
    assert judge.calls == 2


def test_seam_stamps_a_cache_state_on_every_event() -> None:
    judge = _CountingJudge()
    event = _grade(judge)
    assert event["grading_cache"] in ("hit", "miss", "bypass")
    assert event["cache_key_version"] == C.CACHE_KEY_VERSION
    assert len(event["grading_cache_key"]) == 16  # hash prefix only — never the raw answer
