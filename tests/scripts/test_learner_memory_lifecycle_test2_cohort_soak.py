from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import scripts.run_learner_memory_lifecycle_test2_cohort_soak as soak


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_local_core_store_soak_writes_repeatable_artifact_contract(tmp_path: Path) -> None:
    out = tmp_path / "learner_memory_lifecycle_test"

    result = soak.run_soak(out_dir=out)

    assert result["go_no_go"]["status"] == "LOCAL_ARTIFACT_GO"
    assert result["manifest"]["evidence_scope"] == "local_core_store_artifact_contract"
    assert result["manifest"]["remote_write_performed"] is False
    for name in (
        "manifest.json",
        "events.jsonl",
        "projection.json",
        "canonical_readback.json",
        "personalization_context_pack.json",
        "next_best_action.json",
        "learning_brain_readback.json",
        "go_no_go.json",
    ):
        assert (out / name).exists(), name

    manifest = _json(out / "manifest.json")
    go = _json(out / "go_no_go.json")
    events = _jsonl(out / "events.jsonl")
    readback = _json(out / "canonical_readback.json")
    brain = _json(out / "learning_brain_readback.json")

    assert manifest["remote_write_performed"] is False
    assert manifest["remote_write_root_if_authorized"] == "/root/deeptutor"
    assert manifest["cohort_user_id"].startswith("qa_")
    assert manifest["blocked_user_id"].startswith("real_student_")
    assert "local_canonical_readback" in manifest["stage_chain"]
    assert len(events) == 2
    assert {row["memory_lifecycle_stage"] for row in events} == {"stable_learner_claim"}
    assert {row["evidence_level"] for row in events} == {"L2_confirmed"}
    assert all(row["trusted_adjudication"]["source"] == "certified_grading_policy" for row in events)

    assert go["same_projection_hash"] is True
    assert go["canonical_truth_promotion"]["reason"] == "production_cohort_authorized"
    assert go["blocked_non_cohort_decision"]["reason"] == "production_cohort_required"
    assert go["trusted_source"] == "certified_grading_policy"
    assert go["pcp_source"] == "PersonalizationContextPack"
    assert go["next_best_action_id"]
    assert readback["synthesis_run"]["output_projection_hash"] == go["output_projection_hash"]
    assert brain["synthesis_run"]["output_projection_hash"] == go["output_projection_hash"]


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, Any]:
        return dict(self._payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


class _FakeAsyncClient:
    def __init__(self, responses: dict[tuple[str, str], list[_FakeResponse]], captured: dict[str, Any], **_kwargs: Any) -> None:
        self._responses = responses
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method: str, path: str, *, headers=None, json=None, params=None):
        key = (method.upper(), path)
        self._captured.setdefault("requests", []).append(
            {
                "method": method.upper(),
                "path": path,
                "headers": dict(headers or {}),
                "json": dict(json or {}) if isinstance(json, dict) else json,
                "params": dict(params or {}) if isinstance(params, dict) else params,
            }
        )
        queue = self._responses.get(key) or []
        if not queue:
            raise AssertionError(f"unexpected request: {key}")
        return queue.pop(0)

    async def get(self, path: str, *, headers=None, params=None):
        return await self.request("GET", path, headers=headers, params=params)

    async def post(self, path: str, *, headers=None, json=None):
        return await self.request("POST", path, headers=headers, json=json)


class _FakeWebSocket:
    def __init__(self, events: list[dict[str, Any]], captured: dict[str, Any]) -> None:
        self._events = [json.dumps(item, ensure_ascii=False) for item in events]
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, raw: str) -> None:
        self._captured.setdefault("ws_payloads", []).append(json.loads(raw))

    async def recv(self) -> str:
        if not self._events:
            raise AssertionError("unexpected ws recv")
        return self._events.pop(0)


@pytest.mark.asyncio
async def test_remote_test2_ws_runner_uses_real_ws_frames_and_readback(tmp_path: Path) -> None:
    out = tmp_path / "remote_soak"
    captured: dict[str, Any] = {}
    projection = {
        "projection_subject": "construction_exam_learning_truth",
        "event_count": 2,
        "synthesis_run": {
            "output_projection_hash": "sha256:remote",
            "trusted_adjudication": {"source": "certified_grading_policy"},
        },
        "visible_sections": {
            "current_truth": [{"memory_lifecycle_stage": "stable_learner_claim"}],
            "evidence_flow": [{"event_id": "evt_remote_1"}, {"event_id": "evt_remote_2"}],
            "next_training": [{"title": "先练临时用电"}],
        },
        "next_best_action_candidates": [{"action_id": "nba_remote_1"}],
    }
    report = {
        "learning_brain": {
            "synthesis_run": {"output_projection_hash": "sha256:remote"},
        },
        "source_status": {"compiled_learning_truth": "ok"},
    }
    responses = {
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(200, {"user_id": "qa_remote_soak", "id": "qa_remote_soak"})
        ],
        ("GET", "/api/v1/learning-brain/projection"): [
            _FakeResponse(200, projection)
        ],
        ("GET", "/api/v1/mobile/learning-report"): [
            _FakeResponse(200, report)
        ],
    }

    def _client_factory(**kwargs: Any):
        return _FakeAsyncClient(responses, captured, **kwargs)

    ws_batches = [
        [
            {"type": "result", "metadata": {"construction_grading_result": {"authority": "construction_grading"}}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
        [
            {"type": "result", "metadata": {"construction_grading_result": {"authority": "construction_grading"}}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
    ]

    def _connector_factory(url: str, *, additional_headers=None):
        captured.setdefault("ws_connections", []).append(
            {"url": url, "headers": dict(additional_headers or {})}
        )
        return _FakeWebSocket(ws_batches.pop(0), captured)

    result = await soak.run_remote_test2_ws_soak(
        api_base_url="https://test2.example.com",
        auth_token="token-qa",
        out_dir=out,
        client_factory=_client_factory,
        connector_factory=_connector_factory,
        poll_attempts=1,
    )

    assert result["go_no_go"]["status"] == "REMOTE_TEST2_WS_GO"
    assert result["manifest"]["entry"] == "remote test2 /api/v1/ws cohort loop soak"
    assert result["manifest"]["evidence_scope"] == "remote_test2_ws_cohort_soak"
    assert result["manifest"]["remote_write_performed"] is True
    assert result["manifest"]["scenario_id"] == "temporary-electricity-smoke"
    assert result["manifest"]["cohort_user_id"] == "qa_remote_soak"
    assert result["manifest"]["cohort_identity"] == "qa_remote_soak"
    assert "remote_api_ws" in result["manifest"]["stage_chain"]
    assert result["go_no_go"]["same_projection_hash"] is True
    assert result["go_no_go"]["learning_brain_projection_hash"] == "sha256:remote"
    assert result["go_no_go"]["learning_report_projection_hash"] == "sha256:remote"
    assert captured["ws_connections"] == [
        {
            "url": "wss://test2.example.com/api/v1/ws",
            "headers": {"Authorization": "Bearer token-qa"},
        },
        {
            "url": "wss://test2.example.com/api/v1/ws",
            "headers": {"Authorization": "Bearer token-qa"},
        },
    ]
    assert all(payload["type"] == "start_turn" for payload in captured["ws_payloads"])
    assert all(payload["capability"] == "deep_question" for payload in captured["ws_payloads"])
    assert all("loop_id" not in payload["config"] for payload in captured["ws_payloads"])
    assert captured["ws_payloads"][0]["config"]["followup_question_context"]["user_answer"] == "两级配电"
    assert captured["ws_payloads"][1]["config"]["followup_question_context"]["user_answer"] == "三级配电"
    assert (
        captured["ws_payloads"][0]["config"]["followup_question_context"]["question_id"]
        == captured["ws_payloads"][1]["config"]["followup_question_context"]["question_id"]
    )
    assert captured["requests"][0]["path"] == "/api/v1/auth/profile"
    assert (out / "remote_ws_events.json").exists()
    assert (out / "learning_brain_readback.json").exists()
    assert (out / "learning_report_readback.json").exists()


@pytest.mark.asyncio
async def test_remote_test2_ws_runner_supports_real_long_case_scenario(tmp_path: Path) -> None:
    out = tmp_path / "remote_long_case"
    captured: dict[str, Any] = {}
    projection = {
        "projection_subject": "construction_exam_learning_truth",
        "event_count": 2,
        "synthesis_run": {"output_projection_hash": "sha256:long"},
        "visible_sections": {"next_training": [{"title": "复盘长案例"}]},
    }
    report = {"learning_brain": {"synthesis_run": {"output_projection_hash": "sha256:long"}}}
    responses = {
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(200, {"user_id": "qa_remote_soak", "id": "qa_remote_soak"})
        ],
        ("GET", "/api/v1/learning-brain/projection"): [_FakeResponse(200, projection)],
        ("GET", "/api/v1/mobile/learning-report"): [_FakeResponse(200, report)],
    }

    def _client_factory(**kwargs: Any):
        return _FakeAsyncClient(responses, captured, **kwargs)

    ws_batches = [
        [
            {"type": "result", "metadata": {"construction_grading_result": {"authority": "construction_grading"}}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
        [
            {"type": "result", "metadata": {"construction_grading_result": {"authority": "construction_grading"}}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
    ]

    def _connector_factory(url: str, *, additional_headers=None):
        return _FakeWebSocket(ws_batches.pop(0), captured)

    result = await soak.run_remote_test2_ws_soak(
        api_base_url="https://test2.example.com",
        auth_token="token-qa",
        out_dir=out,
        scenario_id="construction-long-case",
        client_factory=_client_factory,
        connector_factory=_connector_factory,
        poll_attempts=1,
    )

    first_context = captured["ws_payloads"][0]["config"]["followup_question_context"]
    second_context = captured["ws_payloads"][1]["config"]["followup_question_context"]

    assert result["go_no_go"]["status"] == "REMOTE_TEST2_WS_GO"
    assert result["manifest"]["scenario_id"] == "construction-long-case"
    assert result["manifest"]["question_id"] == "LM-LC-REMOTE-LONG-001"
    assert "某商品住宅项目" in first_context["question"]
    assert "关键线路B→E→I" in first_context["user_answer"]
    assert "根据网络图和持续时间重新计算" in second_context["user_answer"]
    assert "node_code" not in first_context


@pytest.mark.asyncio
async def test_remote_test2_ws_runner_loads_student_answer_file_sample(tmp_path: Path) -> None:
    out = tmp_path / "remote_answer_file"
    answer_file = tmp_path / "answers.md"
    answer_file.write_text(
        """
### Q2024-02｜长案例

#### 样本元数据

- 样本ID：`Q2024-02__S05`

#### 题目

【背景资料】某商品住宅项目，地下2层，地上12~18层，装配式剪力墙结构。

【问题】答出关键线路、基坑方案、资料责任和低温型灌浆料温度。

#### 回答

作答：
1. 关键线路写成B→E→I。
2. 基坑监测由建设方委托。
3. A技术，B商务，C工程，D质量，E质量。

#### 本题水平判断

- 中低水平。
""",
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}
    projection = {"synthesis_run": {"output_projection_hash": "sha256:answer-file"}}
    report = {"learning_brain": {"synthesis_run": {"output_projection_hash": "sha256:answer-file"}}}
    responses = {
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(200, {"user_id": "qa_remote_soak", "id": "qa_remote_soak"})
        ],
        ("GET", "/api/v1/learning-brain/projection"): [_FakeResponse(200, projection)],
        ("GET", "/api/v1/mobile/learning-report"): [_FakeResponse(200, report)],
    }
    ws_batches = [
        [
            {"type": "result", "metadata": {"construction_grading_result": {"authority": "construction_grading"}}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
        [
            {"type": "result", "metadata": {"construction_grading_result": {"authority": "construction_grading"}}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
    ]

    def _client_factory(**kwargs: Any):
        return _FakeAsyncClient(responses, captured, **kwargs)

    def _connector_factory(url: str, *, additional_headers=None):
        return _FakeWebSocket(ws_batches.pop(0), captured)

    result = await soak.run_remote_test2_ws_soak(
        api_base_url="https://test2.example.com",
        auth_token="token-qa",
        out_dir=out,
        scenario_id="construction-long-case",
        answer_file=answer_file,
        sample_id="Q2024-02__S05",
        client_factory=_client_factory,
        connector_factory=_connector_factory,
        poll_attempts=1,
    )

    context = captured["ws_payloads"][0]["config"]["followup_question_context"]

    assert result["go_no_go"]["status"] == "REMOTE_TEST2_WS_GO"
    assert result["manifest"]["question_id"] == "Q2024-02__S05"
    assert result["manifest"]["sample_id"] == "Q2024-02__S05"
    assert result["manifest"]["answer_file"] == str(answer_file)
    assert "某商品住宅项目" in context["question"]
    assert "关键线路写成B→E→I" in context["user_answer"]


@pytest.mark.asyncio
async def test_remote_test2_ws_runner_blocks_non_cohort_identity(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}
    responses = {
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(200, {"user_id": "auth_real_student", "id": "auth_real_student"})
        ],
    }

    def _client_factory(**kwargs: Any):
        return _FakeAsyncClient(responses, captured, **kwargs)

    result = await soak.run_remote_test2_ws_soak(
        api_base_url="https://test2.example.com",
        auth_token="token-real",
        out_dir=tmp_path / "blocked",
        client_factory=_client_factory,
        connector_factory=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("ws must not open")),
        poll_attempts=1,
    )

    assert result["go_no_go"]["status"] == "REMOTE_AUTH_BLOCKED"
    assert result["go_no_go"]["reason"] == "cohort_user_required"
    assert result["manifest"]["remote_write_performed"] is False
    assert "ws_payloads" not in captured


@pytest.mark.asyncio
async def test_remote_test2_ws_runner_allows_canonical_uuid_with_qa_username(tmp_path: Path) -> None:
    out = tmp_path / "remote_uuid_with_qa_username"
    captured: dict[str, Any] = {}
    canonical_id = "auth_1234567890abcdef12345678"
    responses = {
        ("POST", "/api/v1/auth/register"): [
            _FakeResponse(
                200,
                {
                    "token": "token-qa-uuid",
                    "user_id": canonical_id,
                    "user": {
                        "user_id": canonical_id,
                        "username": "qa_lifecycle_soak_123",
                    },
                },
            )
        ],
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(
                200,
                {
                    "user_id": canonical_id,
                    "id": canonical_id,
                    "username": "qa_lifecycle_soak_123",
                },
            )
        ],
        ("GET", "/api/v1/learning-brain/projection"): [
            _FakeResponse(200, {"synthesis_run": {"output_projection_hash": "sha256:uuidqa"}})
        ],
        ("GET", "/api/v1/mobile/learning-report"): [
            _FakeResponse(200, {"learning_brain": {"synthesis_run": {"output_projection_hash": "sha256:uuidqa"}}})
        ],
    }
    ws_batches = [
        [
            {"type": "result", "metadata": {"construction_grading_result": {"score": 0}}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
        [
            {"type": "result", "metadata": {"construction_grading_result": {"score": 1}}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
    ]

    def _client_factory(**kwargs: Any):
        return _FakeAsyncClient(responses, captured, **kwargs)

    def _connector_factory(url: str, *, additional_headers=None):
        return _FakeWebSocket(ws_batches.pop(0), captured)

    result = await soak.run_remote_test2_ws_soak(
        api_base_url="https://test2.example.com",
        username="qa_lifecycle_soak_123",
        password="StrongPass123",
        phone="13800009999",
        register=True,
        out_dir=out,
        client_factory=_client_factory,
        connector_factory=_connector_factory,
        poll_attempts=1,
    )

    assert result["go_no_go"]["status"] == "REMOTE_TEST2_WS_GO"
    assert result["manifest"]["cohort_user_id"] == canonical_id
    assert result["manifest"]["cohort_identity"] == "qa_lifecycle_soak_123"
    assert captured["requests"][0]["path"] == "/api/v1/auth/register"


@pytest.mark.asyncio
async def test_remote_test2_ws_runner_triggers_remote_synthesis_for_canonical_qa_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "remote_with_synthesis"
    captured: dict[str, Any] = {}
    responses = {
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(200, {"user_id": "qa_remote_soak", "id": "qa_remote_soak"})
        ],
        ("GET", "/api/v1/learning-brain/projection"): [
            _FakeResponse(200, {"synthesis_run": {"output_projection_hash": "sha256:remote-synth"}})
        ],
        ("GET", "/api/v1/mobile/learning-report"): [
            _FakeResponse(200, {"learning_brain": {"synthesis_run": {"output_projection_hash": "sha256:remote-synth"}}})
        ],
    }
    ws_batches = [
        [
            {"type": "result", "metadata": {"construction_grading_result": {"score": 0}}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
        [
            {"type": "result", "metadata": {"construction_grading_result": {"score": 1}}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
    ]
    synthesis_calls: list[dict[str, Any]] = []

    def _fake_synthesis(**kwargs: Any) -> dict[str, Any]:
        synthesis_calls.append(dict(kwargs))
        return {
            "triggered": True,
            "payload": {
                "canonical_truth_promotion": {
                    "allowed": True,
                    "reason": "production_cohort_authorized",
                },
                "projection_hash": "sha256:remote-synth",
                "readback_hash": "sha256:remote-synth",
            },
        }

    monkeypatch.setattr(soak, "_trigger_remote_synthesis_via_ssh", _fake_synthesis)

    def _client_factory(**kwargs: Any):
        return _FakeAsyncClient(responses, captured, **kwargs)

    def _connector_factory(url: str, *, additional_headers=None):
        return _FakeWebSocket(ws_batches.pop(0), captured)

    result = await soak.run_remote_test2_ws_soak(
        api_base_url="https://test2.example.com",
        auth_token="token-qa",
        out_dir=out,
        client_factory=_client_factory,
        connector_factory=_connector_factory,
        remote_synthesis_ssh_host="Aliyun-ECS-2",
        poll_attempts=1,
    )

    assert result["go_no_go"]["status"] == "REMOTE_TEST2_WS_GO"
    assert result["manifest"]["remote_synthesis"]["triggered"] is True
    assert result["manifest"]["stage_chain"] == [
        "remote_api_ws",
        "grading",
        "learning_evidence",
        "remote_synthesis_trigger",
        "learning_brain_projection_readback",
        "learning_report_readback",
    ]
    assert synthesis_calls[0]["user_id"] == "qa_remote_soak"
    assert (out / "remote_synthesis.json").exists()
