from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
import time
from zoneinfo import ZoneInfo

from jsonschema import validate

from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore
from deeptutor.services.observability.oa_runner import build_oa_run
from deeptutor.services.observability.observer_snapshot import build_observer_snapshot
from deeptutor.services.observability.product_behavior_store import SQLiteProductBehaviorStore
from deeptutor.services.observability.turn_event_log import (
    TurnEventLog,
    build_turn_observation_event,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _create_chat_history_db(path: Path, *, now: float, failed: bool = False) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                compressed_summary TEXT DEFAULT '',
                summary_up_to_msg_id INTEGER DEFAULT 0,
                preferences_json TEXT DEFAULT '{}',
                owner_key TEXT DEFAULT '',
                source TEXT DEFAULT '',
                archived INTEGER DEFAULT 0,
                conversation_id TEXT DEFAULT ''
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                capability TEXT DEFAULT '',
                events_json TEXT DEFAULT '',
                attachments_json TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE TABLE turns (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                capability TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'running',
                error TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                finished_at REAL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sessions(id, title, created_at, updated_at, source, conversation_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("session-1", "质量验收连续对话", now - 60, now - 10, "ws", "conv-1"),
        )
        conn.execute(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            ("session-1", "user", "我手机号是13800000000，帮我出题", now - 50),
        )
        conn.execute(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            ("session-1", "assistant", "好的，只出题。", now - 40),
        )
        conn.execute(
            """
            INSERT INTO turns(id, session_id, capability, status, error, created_at, updated_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "turn-1",
                "session-1",
                "deep_question",
                "failed" if failed else "completed",
                "primary plan exploded" if failed else "",
                now - 55,
                now - 10,
                now - 10,
            ),
        )
        conn.commit()


def test_build_observer_snapshot_collects_store_and_turn_event_evidence(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")
    release = {
        "release_id": "rel-1",
        "git_sha": "abc",
        "deployment_environment": "dev",
        "prompt_version": "p1",
        "ff_snapshot_hash": "ff1",
    }
    store.write_run(
        kind="om_runs",
        run_id="om-1",
        release_id="rel-1",
        payload={
            "run_id": "om-1",
            "release": release,
            "health_summary": {"ready": True, "turn_success_ratio": 1.0},
            "metrics_snapshot": {"surface_events": {"coverage": [{"surface": "web"}]}},
        },
    )
    store.write_run(
        kind="arr_runs",
        run_id="arr-1",
        release_id="rel-1",
        payload={
            "run_id": "arr-1",
            "release": release,
            "summary": {"pass_rate": 0.9},
            "baseline_diff": {"regressions": [], "new_failures": []},
        },
    )
    event_log = TurnEventLog(events_dir=tmp_path / "events")
    event_log.append(
        build_turn_observation_event(
            release=release,
            session_id="session-1",
            turn_id="turn-1",
            status="completed",
            capability="chat",
            latency_ms=1000,
            token_total=42,
            retrieval_hit=True,
            metadata={
                "server_turn_start_to_first_useful_content_ms": 350.0,
                "latency_stages_ms": {
                    "context_build": 100.0,
                    "capability_stream": 800.0,
                },
                "latency_max_stall": {
                    "scope": "capability_stream",
                    "stage": "capability_stream",
                    "duration_ms": 800.0,
                },
            },
        )
    )
    event_log.append(
        build_turn_observation_event(
            release=release,
            session_id="session-1",
            turn_id="turn-2",
            status="failed",
            capability="deep_question",
            latency_ms=3000,
            token_total=84,
            retrieval_hit=False,
            metadata={
                "server_turn_start_to_first_useful_content_ms": 2200.0,
                "latency_stages_ms": {
                    "context_build": 300.0,
                    "capability_stream": 2400.0,
                },
                "selected_mode": "deep",
                "latency_max_stall": {
                    "scope": "capability_stream",
                    "stage": "capability_stream",
                    "duration_ms": 2400.0,
                },
            },
        )
    )

    payload = build_observer_snapshot(
        store=store,
        event_log=event_log,
        event_days=1,
        conversation_db_path=tmp_path / "missing-chat.db",
        backend_log_paths=[],
    )

    assert payload["run_id"].startswith("observer-snapshot-")
    assert payload["release"]["release_id"] == "rel-1"
    assert payload["data_coverage"]["layers_with_data"] >= 3
    assert payload["turn_events"]["event_count"] == 2
    assert payload["turn_events"]["error_count"] == 1
    assert payload["turn_events"]["avg_latency_ms"] == 2000.0
    assert payload["turn_events"]["latency_stage_avg_ms"] == {
        "capability_stream": 1600.0,
        "context_build": 200.0,
    }
    assert payload["turn_events"]["slow_turn_samples"][0] == {
        "turn_id": "turn-2",
        "status": "failed",
        "capability": "deep_question",
        "latency_ms": 3000.0,
        "server_turn_start_to_first_useful_content_ms": 2200.0,
        "selected_mode": "deep",
        "latency_max_stall": {
            "scope": "capability_stream",
            "stage": "capability_stream",
            "duration_ms": 2400.0,
        },
    }
    assert payload["turn_events"]["retrieval_hit_ratio"] == 0.5
    assert payload["turn_event_log"]["last_write_error"] == ""
    assert payload["source_runs"]["om_run_id"] == "om-1"
    assert payload["source_runs"]["arr_run_id"] == "arr-1"
    layers = {item["name"]: item for item in payload["data_coverage"]["layers"]}
    assert "reason" not in layers["turn_event_log"]
    assert layers["aae_composite"]["reason"] == "missing AAE composite"
    assert payload["data_sources"]["om_snapshot"]["source_id"] == "om-1"
    assert payload["data_sources"]["om_snapshot"]["freshness"] in {"fresh", "stale"}
    assert isinstance(payload["data_sources"]["om_snapshot"]["age_seconds"], int)
    assert payload["data_sources"]["turn_event_log"]["sample_count"] == 2
    assert payload["data_sources"]["turn_event_log"]["confidence"] == "high"


def test_build_observer_snapshot_collects_recent_conversation_and_backend_log_evidence(tmp_path) -> None:
    now = time.time()
    db_path = tmp_path / "chat_history.db"
    _create_chat_history_db(db_path, now=now, failed=True)
    log_path = tmp_path / "deeptutor.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-04-23 10:00:00 [INFO    ] started",
                "2026-04-23 10:01:00 [ERROR   ] [SupabasePipeline] Supabase retrieval failed: primary plan exploded",
                "2026-04-23 10:02:00 [WARNING ] [LangfuseObservability] Langfuse initialization skipped: Connection refused",
            ]
        ),
        encoding="utf-8",
    )

    event_log = TurnEventLog(events_dir=tmp_path / "events")
    event_log.append(build_turn_observation_event(status="completed", turn_id="turn-1", trace_id="trace-1"))
    payload = build_observer_snapshot(
        store=ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane"),
        event_log=event_log,
        event_days=1,
        conversation_db_path=db_path,
        conversation_limit=10,
        backend_log_paths=[log_path],
    )
    oa_payload = build_oa_run(
        mode="incident",
        om_payload=None,
        arr_payload=None,
        aae_payload=None,
        observer_payload=payload,
    )

    assert payload["recent_conversations"]["session_count"] == 1
    assert payload["recent_conversations"]["message_count"] == 2
    assert payload["recent_conversations"]["failed_turn_count"] == 1
    assert payload["recent_conversations"]["recent_sessions"][0]["last_user_excerpt"] == "我手机号是[PHONE]，帮我出题"
    assert payload["backend_logs"]["error_count"] == 1
    assert payload["backend_logs"]["warning_count"] == 1
    assert payload["runtime_incidents"] == [
        {
            "incident_type": "supabase_primary_plan_exploded",
            "component": "rag.supabase_pipeline",
            "severity": "high",
            "release_blocking": True,
            "failure_taxonomy_hint": "FAIL_GROUNDEDNESS",
            "summary": "SupabasePipeline primary plan 在 retrieval 主链路爆炸，当前 release 的 grounding 结果不可信。",
            "repeat_count": 1,
            "first_seen": "2026-04-23 10:01:00",
            "last_seen": "2026-04-23 10:01:00",
            "query_samples": [],
            "related_source_groups": [],
            "warning_reasons": [],
            "evidence_samples": [
                "2026-04-23 10:01:00 [ERROR   ] [SupabasePipeline] Supabase retrieval failed: primary plan exploded"
            ],
            "warning_samples": [],
            "signature": "SupabasePipeline:primary_plan_exploded",
            "benchmark_projection": {
                "case_id": "runtime.supabase.primary_plan_exploded",
                "recommended_tier": "incident_replay",
                "contract_domain": "grounding_contract",
            },
        }
    ]


def test_build_observer_snapshot_freezes_window_and_excludes_same_run_smoke_sessions(tmp_path) -> None:
    release = {
        "release_id": "rel-window",
        "git_sha": "sha-window",
        "deployment_environment": "dev",
        "prompt_version": "p-window",
        "ff_snapshot_hash": "ff-window",
    }
    tz = ZoneInfo("Asia/Shanghai")
    start_ts = datetime(2026, 6, 16, 0, 0, 0, tzinfo=tz).timestamp()
    end_ts = datetime(2026, 6, 16, 23, 59, 59, tzinfo=tz).timestamp()

    db_path = tmp_path / "chat_history.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                compressed_summary TEXT DEFAULT '',
                summary_up_to_msg_id INTEGER DEFAULT 0,
                preferences_json TEXT DEFAULT '{}',
                owner_key TEXT DEFAULT '',
                source TEXT DEFAULT '',
                archived INTEGER DEFAULT 0,
                conversation_id TEXT DEFAULT ''
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                capability TEXT DEFAULT '',
                events_json TEXT DEFAULT '',
                attachments_json TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE TABLE turns (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                capability TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'running',
                error TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                finished_at REAL
            );
            """
        )
        real_ts = start_ts + 3600
        smoke_ts = end_ts - 10
        next_day_ts = end_ts + 20
        for session_id, ts_value, status in (
            ("session-real", real_ts, "completed"),
            ("session-smoke", smoke_ts, "completed"),
            ("session-next-day", next_day_ts, "completed"),
        ):
            conn.execute(
                """
                INSERT INTO sessions(id, title, created_at, updated_at, source, conversation_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, session_id, ts_value, ts_value, "ws", f"conv-{session_id}"),
            )
            conn.execute(
                "INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, "user", f"{session_id}-user", ts_value),
            )
            conn.execute(
                "INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, "assistant", f"{session_id}-assistant", ts_value + 1),
            )
            conn.execute(
                """
                INSERT INTO turns(id, session_id, capability, status, error, created_at, updated_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"turn-{session_id}", session_id, "deep_question", status, "", ts_value, ts_value, ts_value + 1),
            )
        conn.commit()

    event_log = TurnEventLog(events_dir=tmp_path / "events")
    date_to_events = {
        "2026-06-16": [
            build_turn_observation_event(
                release=release,
                session_id="session-real",
                turn_id="turn-real",
                trace_id="trace-real",
                status="completed",
                capability="deep_question",
                timestamp=start_ts + 120,
            ),
            build_turn_observation_event(
                release=release,
                session_id="session-smoke",
                turn_id="turn-smoke",
                status="completed",
                capability="deep_question",
                timestamp=end_ts - 60,
            ),
        ],
        "2026-06-17": [
            build_turn_observation_event(
                release=release,
                session_id="session-next-day",
                turn_id="turn-next-day",
                status="completed",
                capability="deep_question",
                timestamp=end_ts + 120,
            )
        ],
    }
    for date_str, events in date_to_events.items():
        path = event_log.events_dir / f"turn_events_{date_str}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
            encoding="utf-8",
        )

    payload = build_observer_snapshot(
        store=ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane"),
        event_log=event_log,
        event_days=1,
        conversation_db_path=db_path,
        conversation_limit=10,
        backend_log_paths=[],
        report_date="2026-06-16",
        start_ts=start_ts,
        end_ts=end_ts,
        timezone="Asia/Shanghai",
        exclude_session_ids={"session-smoke"},
    )

    assert payload["window"]["report_date"] == "2026-06-16"
    assert payload["window"]["timezone"] == "Asia/Shanghai"
    assert payload["window"]["excluded_session_ids"] == ["session-smoke"]
    assert payload["turn_events"]["event_count"] == 1
    assert payload["turn_event_log"]["window_events"] == 2
    assert payload["recent_conversations"]["cutoff_timestamp"] is None
    assert payload["recent_conversations"]["session_count"] == 1
    assert payload["recent_conversations"]["excluded_session_ids"] == ["session-smoke"]
    assert [item["session_id"] for item in payload["recent_conversations"]["recent_sessions"]] == ["session-real"]
    assert payload["langfuse_trace_linkage"]["trace_id_count"] == 1
    assert payload["langfuse_trace_linkage"]["verification_status"] == "not_verified"
    assert payload["langfuse_trace_linkage"]["verified_trace_count"] == 0
    assert payload["data_sources"]["recent_conversations"]["has_data"] is True
    assert payload["data_sources"]["langfuse_trace_linkage"]["has_data"] is False
    assert "persistence was not verified" in payload["data_sources"]["langfuse_trace_linkage"]["reason"]
    assert "missing_langfuse_trace_linkage" in {item["type"] for item in payload["blind_spots"]}
    assert payload["data_sources"]["backend_logs"]["has_data"] is False


def test_build_observer_snapshot_collects_product_behavior_evidence(tmp_path) -> None:
    now_ms = int(time.time() * 1000)
    behavior_db = tmp_path / "product_behavior.db"
    behavior_store = SQLiteProductBehaviorStore(behavior_db)
    for event in (
        {
            "event_id": "pbe-1",
            "event_name": "module_viewed",
            "occurred_at_ms": now_ms,
            "user_id": "student-1",
            "visit_id": "visit-1",
            "surface": "wechat_yousenwebview",
            "module": "learning_report",
            "action": "view",
        },
        {
            "event_id": "pbe-2",
            "event_name": "section_viewed",
            "occurred_at_ms": now_ms,
            "user_id": "student-1",
            "visit_id": "visit-1",
            "surface": "wechat_yousenwebview",
            "module": "learning_report",
            "section": "next_action",
            "action": "view",
        },
        {
            "event_id": "pbe-3",
            "event_name": "learning_action_started",
            "occurred_at_ms": now_ms,
            "user_id": "student-1",
            "visit_id": "visit-1",
            "surface": "wechat_yousenwebview",
            "module": "practice",
            "action": "start_training",
        },
    ):
        assert behavior_store.record_event(event)["accepted"] is True

    payload = build_observer_snapshot(
        store=ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane"),
        event_log=TurnEventLog(events_dir=tmp_path / "events"),
        event_days=1,
        conversation_db_path=tmp_path / "missing-chat.db",
        backend_log_paths=[],
        product_behavior_db_path=behavior_db,
    )

    assert payload["data_sources"]["product_behavior"]["has_data"] is True
    assert payload["product_behavior"]["event_count"] == 3
    assert payload["product_behavior"]["p0_path_counts"]["learning_report_open"] == 1
    assert payload["product_behavior"]["p0_path_counts"]["learning_report_next_action_view"] == 1
    assert payload["product_behavior"]["p0_path_counts"]["training_started"] == 1
    assert "missing_product_behavior_evidence" not in {item["type"] for item in payload["blind_spots"]}


def test_build_observer_snapshot_reports_missing_arr_when_only_benchmark_exists(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")
    release = {"release_id": "rel-1", "git_sha": "abc", "deployment_environment": "dev"}
    store.write_run(
        kind="benchmark_runs",
        run_id="benchmark-1",
        release_id="rel-1",
        payload={
            "run_manifest": {"run_id": "benchmark-1", "release_spine": release},
            "summary": {"total": 3, "passed": 3, "failed": 0},
        },
    )

    payload = build_observer_snapshot(
        store=store,
        event_log=TurnEventLog(events_dir=tmp_path / "events"),
        event_days=1,
        conversation_db_path=tmp_path / "missing-chat.db",
        backend_log_paths=[],
        product_behavior_db_path=tmp_path / "missing-product-behavior.db",
    )

    blind_spot_types = {item["type"] for item in payload["blind_spots"]}
    assert payload["data_sources"]["quality_run"]["has_data"] is True
    assert payload["source_runs"]["benchmark_run_id"] == "benchmark-1"
    assert "missing_quality_run" not in blind_spot_types
    assert "missing_arr_run" in blind_spot_types


def test_build_observer_snapshot_excludes_test_only_turns_from_headline_metrics(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path / "events")
    event_log.append(
        build_turn_observation_event(
            session_id="session-real",
            turn_id="turn-real",
            status="completed",
            capability="chat",
        )
    )
    event_log.append(
        build_turn_observation_event(
            session_id="session_general_knowledge_shadow",
            turn_id="turn-shadow",
            status="failed",
            capability="deep_question",
            surface="online_shadow",
        )
    )

    payload = build_observer_snapshot(
        store=ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane"),
        event_log=event_log,
        event_days=1,
        conversation_db_path=tmp_path / "missing-chat.db",
        backend_log_paths=[],
    )

    assert payload["turn_events"]["event_count"] == 1
    assert payload["turn_events"]["raw_event_count"] == 2
    assert payload["turn_events"]["excluded_test_only_event_count"] == 1
    assert payload["turn_events"]["error_count"] == 0


def test_build_observer_snapshot_reports_blind_spots_when_sources_missing(tmp_path) -> None:
    payload = build_observer_snapshot(
        store=ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane"),
        event_log=TurnEventLog(events_dir=tmp_path / "events"),
        event_days=1,
        conversation_db_path=tmp_path / "missing-chat.db",
        backend_log_paths=[],
        product_behavior_db_path=tmp_path / "missing-product-behavior.db",
    )

    blind_spot_types = {item["type"] for item in payload["blind_spots"]}
    assert "missing_turn_event_log" in blind_spot_types
    assert "missing_om_snapshot" in blind_spot_types
    assert "missing_quality_run" in blind_spot_types
    assert "missing_product_behavior_evidence" in blind_spot_types
    assert payload["data_coverage"]["coverage_ratio"] < 1.0


def test_build_observer_snapshot_reports_turn_event_log_write_error(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path / "events")
    assert event_log.append({"bad": object()}) is False

    payload = build_observer_snapshot(
        store=ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane"),
        event_log=event_log,
        event_days=1,
        conversation_db_path=tmp_path / "missing-chat.db",
        backend_log_paths=[],
    )

    blind_spot_types = {item["type"] for item in payload["blind_spots"]}
    assert "turn_event_log_write_error" in blind_spot_types
    assert "TypeError" in payload["turn_event_log"]["last_write_error"]


def test_observer_snapshot_and_oa_payloads_match_public_schemas(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path / "events")
    event_log.append(build_turn_observation_event(status="completed", turn_id="turn-1"))
    observer_payload = build_observer_snapshot(
        store=ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane"),
        event_log=event_log,
        conversation_db_path=tmp_path / "missing-chat.db",
        backend_log_paths=[],
    )
    oa_payload = build_oa_run(
        mode="daily",
        om_payload=None,
        arr_payload=None,
        aae_payload=None,
        observer_payload=observer_payload,
    )

    observer_schema = json.loads((PROJECT_ROOT / "schemas" / "observer_snapshot_v1.json").read_text(encoding="utf-8"))
    oa_schema = json.loads((PROJECT_ROOT / "schemas" / "oa_run_v1.json").read_text(encoding="utf-8"))
    validate(observer_payload, observer_schema)
    validate(oa_payload, oa_schema)


def test_observer_with_release_uses_run_local_payloads_not_foreign_latest(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")
    foreign_release = {"release_id": "foreign", "git_sha": "same", "ff_snapshot_hash": "foreign"}
    for kind, run_id in (("om_runs", "foreign-om"), ("arr_runs", "foreign-arr"), ("aae_composite_runs", "foreign-aae")):
        store.write_run(
            kind=kind,
            run_id=run_id,
            release_id="foreign",
            payload={"run_id": run_id, "release": foreign_release},
        )
    release = {"release_id": "candidate", "git_sha": "same", "ff_snapshot_hash": "candidate"}
    payload = build_observer_snapshot(
        store=store,
        event_log=TurnEventLog(events_dir=tmp_path / "events"),
        release=release,
        metrics_snapshot={"release": release, "surface_events": {"coverage": []}},
        om_payload={"run_id": "run-om", "release": release},
        arr_payload={"run_id": "run-arr", "release": release},
        aae_payload={"run_id": "run-aae", "release": release},
        benchmark_payload=None,
        conversation_db_path=tmp_path / "missing-chat.db",
        backend_log_paths=[],
        product_behavior_db_path=tmp_path / "missing-product.db",
    )

    assert payload["source_runs"]["om_run_id"] == "run-om"
    assert payload["source_runs"]["arr_run_id"] == "run-arr"
    assert payload["source_runs"]["aae_run_id"] == "run-aae"
    assert payload["source_runs"]["benchmark_run_id"] is None
    assert "daily_trend_run_id" not in payload["source_runs"]
    assert "daily_trend" not in payload["data_sources"]
    assert "daily_trend_metrics" not in payload["signals"]
    assert "missing_daily_trend" not in {item["type"] for item in payload["blind_spots"]}
