from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
import uuid

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from deeptutor.services.luban_lesson import retest_writeback as writeback_module
from deeptutor.services.luban_lesson.retest_selection import issue_retest_selection
from deeptutor.services.luban_lesson.retest_writeback import (
    RetestCompletionInProgress,
    RetestWritebackService,
)


def _migration_sql() -> str:
    path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260716000100_learner_state_luban_retest_probe_claim.sql"
    )
    # A plain local PostgreSQL does not have Supabase's cluster-global roles.
    # Privilege statements are covered by the structural migration test; keep
    # the exact function/table/transaction SQL for this behavioral test.
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not any(role in line for role in (" from anon", " from authenticated", " to service_role"))
    )


def _claim(dsn: str, *, barrier: Barrier | None = None, **kwargs: str) -> dict:
    with psycopg.connect(dsn) as connection:
        if barrier is not None:
            barrier.wait(timeout=5)
        row = connection.execute(
            """
            select public.claim_luban_retest_probe(%s, %s, %s, %s, %s)
            """,
            (
                kwargs["user_id"],
                kwargs["probe_id"],
                kwargs["cycle_anchor"],
                kwargs["completion_id"],
                kwargs["request_hash"],
            ),
        ).fetchone()
        assert row is not None
        return dict(row[0])


def _event(row: tuple) -> SimpleNamespace:
    return SimpleNamespace(
        event_id=str(row[0]),
        user_id=str(row[1]),
        source_feature=str(row[2]),
        source_id=str(row[3]),
        source_bot_id=str(row[4] or "") or None,
        memory_kind=str(row[5]),
        payload_json=dict(row[6] or {}),
        dedupe_key=str(row[7]),
        created_at=row[8].isoformat(),
    )


class _PostgresLearnerStateAdapter:
    """Narrow test adapter: each instance owns independent DB connections."""

    def __init__(self, dsn: str, claim_barrier: Barrier | None = None) -> None:
        self._dsn = dsn
        self._claim_barrier = claim_barrier

    def claim_retest_probe(self, **kwargs: str) -> dict:
        barrier = self._claim_barrier
        self._claim_barrier = None
        return _claim(self._dsn, barrier=barrier, **kwargs)

    def append_memory_event(
        self,
        user_id: str,
        *,
        source_feature: str,
        source_id: str,
        memory_kind: str,
        payload_json: dict,
        source_bot_id: str | None = None,
        dedupe_key: str,
    ) -> SimpleNamespace:
        with psycopg.connect(self._dsn) as connection:
            row = connection.execute(
                """
                insert into public.learner_memory_events(
                  event_id, user_id, source_feature, source_id, source_bot_id,
                  memory_kind, payload_json, dedupe_key
                ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (dedupe_key) do nothing
                returning *
                """,
                (
                    uuid.uuid4(),
                    user_id,
                    source_feature,
                    source_id,
                    source_bot_id,
                    memory_kind,
                    Jsonb(payload_json),
                    dedupe_key,
                ),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    "select * from public.learner_memory_events where dedupe_key = %s",
                    (dedupe_key,),
                ).fetchone()
            assert row is not None
            return _event(row)

    def list_memory_events(self, user_id: str, limit=None) -> list[SimpleNamespace]:
        with psycopg.connect(self._dsn) as connection:
            rows = connection.execute(
                "select * from public.learner_memory_events "
                "where user_id = %s order by created_at asc, event_id asc",
                (user_id,),
            ).fetchall()
        return [_event(row) for row in rows]

    def list_retest_completion_events_authoritative(
        self, user_id: str, completion_id: str
    ) -> list[SimpleNamespace]:
        with psycopg.connect(self._dsn) as connection:
            rows = connection.execute(
                "select * from public.read_luban_retest_completion_events(%s, %s)",
                (user_id, completion_id),
            ).fetchall()
        return [_event(row) for row in rows]


def test_probe_claim_is_atomic_across_transactions_and_winner_can_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_dsn = os.getenv("DEEPTUTOR_TEST_POSTGRES_ADMIN_DSN", "postgresql:///postgres")
    database = f"deeptutor_retest_{uuid.uuid4().hex[:12]}"
    try:
        admin = psycopg.connect(admin_dsn, autocommit=True)
    except psycopg.Error as exc:
        pytest.skip(f"local PostgreSQL unavailable: {exc}")
    try:
        try:
            admin.execute(sql.SQL("create database {}").format(sql.Identifier(database)))
        except psycopg.Error as exc:
            pytest.skip(f"isolated PostgreSQL database unavailable: {exc}")

        test_dsn = f"dbname={database}"
        with psycopg.connect(test_dsn) as setup:
            setup.execute("create table public.users (id text primary key)")
            setup.execute(
                """
                create table public.learner_memory_events (
                  event_id uuid primary key,
                  user_id text not null references public.users(id) on delete cascade,
                  source_feature text not null,
                  source_id text not null,
                  source_bot_id text,
                  memory_kind text not null,
                  payload_json jsonb not null,
                  dedupe_key text not null,
                  created_at timestamptz not null default now()
                )
                """
            )
            setup.execute(
                "create unique index idx_learner_memory_events_dedupe "
                "on public.learner_memory_events(dedupe_key)"
            )
            setup.execute(
                "insert into public.users(id) values ('student'), ('student:a')"
            )
            setup.execute(_migration_sql())

        race = Barrier(2)
        shared = {
            "user_id": "student",
            "probe_id": "probe-race",
            "cycle_anchor": "cycle-1",
            "request_hash": "a" * 64,
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    _claim,
                    test_dsn,
                    barrier=race,
                    completion_id=completion_id,
                    **shared,
                )
                for completion_id in ("device-a", "device-b")
            ]
            results = [future.result(timeout=10) for future in futures]

        assert sorted(result["status"] for result in results) == ["acquired", "replay"]
        winner = next(result for result in results if result["status"] == "acquired")
        assert all(result["completion_id"] == winner["completion_id"] for result in results)
        with psycopg.connect(test_dsn) as verify:
            claim_count = verify.execute(
                "select count(*) from public.learner_memory_events "
                "where memory_kind = 'retest_control_claim'"
            ).fetchone()
            assert claim_count == (1,)

            verify.execute(
                """
                insert into public.learner_memory_events(
                  event_id, user_id, source_feature, source_id, memory_kind,
                  payload_json, dedupe_key
                ) values (
                  %s, 'student', 'assessment_testset', %s, 'learning_evidence',
                  jsonb_build_object(
                    'retest_completion_id', %s::text,
                    'completion_terminal', true
                  ), %s
                )
                """,
                (
                    uuid.uuid4(),
                    f"{winner['completion_id']}:terminal",
                    winner["completion_id"],
                    f"terminal:{winner['completion_id']}",
                ),
            )
            direct = verify.execute(
                "select event_id from public.read_luban_retest_completion_events(%s, %s)",
                ("student", winner["completion_id"]),
            ).fetchall()
            assert len(direct) == 1

        crash = {
            "user_id": "student",
            "probe_id": "probe-crash",
            "cycle_anchor": "cycle-2",
            "request_hash": "b" * 64,
        }
        first = _claim(test_dsn, completion_id="owner", **crash)
        owner_resume = _claim(test_dsn, completion_id="owner", **crash)
        other_pending = _claim(test_dsn, completion_id="other", **crash)
        conflict = _claim(
            test_dsn,
            completion_id="other",
            **{**crash, "request_hash": "c" * 64},
        )
        assert first["status"] == owner_resume["status"] == "acquired"
        assert other_pending["status"] == "replay"
        assert other_pending["completion_id"] == "owner"
        assert other_pending["request_hash"] == "b" * 64
        assert conflict["status"] == "conflict"

        # Delimiter-looking inputs produce different canonical tuple hashes.
        left = _claim(
            test_dsn,
            user_id="student:a",
            probe_id="probe",
            cycle_anchor="cycle-3",
            completion_id="left",
            request_hash="d" * 64,
        )
        right = _claim(
            test_dsn,
            user_id="student",
            probe_id="a:probe",
            cycle_anchor="cycle-3",
            completion_id="right",
            request_hash="d" * 64,
        )
        assert left["status"] == right["status"] == "acquired"
        assert left["claim_event_id"] != right["claim_event_id"]

        # Exercise the same durable RPC through two independent writeback
        # service instances, not an application pre-check or shared mock.
        monkeypatch.setenv("LUBAN_REVIEW_MODULE_ENABLED", "1")
        monkeypatch.setenv("LUBAN_LIGHT_PRACTICE_ENABLED", "1")
        monkeypatch.setattr(
            writeback_module,
            "resolve_retest_items",
            lambda *args, **kwargs: [
                {
                    "variant_id": "F16-v1",
                    "rule_group": "diameter",
                    "surface": "直径120mm仍用抽气灌胶法",
                    "expected_ok": False,
                    "correct_statement": "直径达到100mm应割补",
                    "anchor": "kc:F16",
                }
            ],
        )
        monkeypatch.setattr(
            writeback_module,
            "retest_supply_identity",
            lambda *args, **kwargs: {"kind": "signed_variant", "digest": "f" * 64},
        )
        monkeypatch.setattr(
            writeback_module,
            "build_lesson_viewmodel",
            lambda pack_id: {"pack_id": pack_id, "title": "屋面防水起鼓割补"},
        )
        selection = issue_retest_selection(
            user_id="student",
            pack_id="F16",
            day_index=2026197,
            mode="review",
            variant_ids=["F16-v1"],
            supply_kind="signed_variant",
            supply_digest="f" * 64,
            probe_id="probe-service-race",
            cycle_anchor="cycle-service-race",
        )
        service_barrier = Barrier(2)
        adapters = [
            _PostgresLearnerStateAdapter(test_dsn, service_barrier),
            _PostgresLearnerStateAdapter(test_dsn, service_barrier),
        ]
        services = [
            RetestWritebackService(
                learner_state_service=adapter,
                review_probe_resolver=lambda **_kwargs: {
                    "due": True,
                    "cycle_anchor": "cycle-service-race",
                },
            )
            for adapter in adapters
        ]

        def _complete(index: int):
            try:
                return services[index].complete(
                    user_id="student",
                    completion_id=f"service-device-{index}",
                    selection_id=selection,
                    pack_id="F16",
                    mode="forward",
                    day_index=1,
                    answers=[{"variant_id": "F16-v1", "choice_ok": False}],
                    probe_id="forged-client-probe",
                )
            except RetestCompletionInProgress as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(_complete, (0, 1)))
        successes = [outcome for outcome in outcomes if isinstance(outcome, dict)]
        assert successes
        assert len({outcome["completion_id"] for outcome in successes}) == 1
        winner_completion = successes[0]["completion_id"]
        replay_index = 0 if winner_completion == "service-device-1" else 1
        replay = _complete(replay_index)
        assert isinstance(replay, dict)
        assert replay["completion_id"] == winner_completion
        with psycopg.connect(test_dsn) as verify:
            terminal_count = verify.execute(
                "select count(*) from public.learner_memory_events "
                "where payload_json->>'probe_id' = 'probe-service-race' "
                "and payload_json->>'completion_terminal' = 'true'"
            ).fetchone()
            assert terminal_count == (1,)
    finally:
        try:
            admin.execute(
                sql.SQL("drop database if exists {} with (force)").format(
                    sql.Identifier(database)
                )
            )
        finally:
            admin.close()
