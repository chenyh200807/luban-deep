from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from jsonschema import validate

from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore
from deeptutor.services.observability.observer_snapshot import build_observer_snapshot
from deeptutor.services.observability.oa_runner import build_oa_run
from deeptutor.services.observability.turn_event_log import TurnEventLog
from deeptutor.services.observability.turn_event_log import build_turn_observation_event


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
    assert payload["langfuse_trace_linkage"]["trace_id_count"] == 1
    assert payload["data_sources"]["recent_conversations"]["has_data"] is True
    assert payload["data_sources"]["backend_logs"]["has_data"] is True
    assert payload["data_sources"]["langfuse_trace_linkage"]["has_data"] is True
    hypotheses = "\n".join(item["hypothesis"] for item in oa_payload["root_causes"])
    assert "近期真实对话持久化记录中存在失败 turn" in hypotheses
    assert "后台日志在 OA 窗口内出现 ERROR/CRITICAL" in hypotheses


def test_build_observer_snapshot_reports_blind_spots_when_sources_missing(tmp_path) -> None:
    payload = build_observer_snapshot(
        store=ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane"),
        event_log=TurnEventLog(events_dir=tmp_path / "events"),
        event_days=1,
        conversation_db_path=tmp_path / "missing-chat.db",
        backend_log_paths=[],
    )

    blind_spot_types = {item["type"] for item in payload["blind_spots"]}
    assert "missing_turn_event_log" in blind_spot_types
    assert "missing_om_snapshot" in blind_spot_types
    assert "missing_quality_run" in blind_spot_types
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
