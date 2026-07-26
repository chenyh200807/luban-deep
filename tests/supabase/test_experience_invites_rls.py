from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

_TABLES = (
    "experience_invites",
    "experience_access",
    "experience_turn_costs",
)


def _isolated_dsn() -> str:
    dsn = str(os.getenv("SUPABASE_DB_URL") or "").strip()
    if not dsn:
        pytest.skip("SUPABASE_DB_URL is required for the live RLS test")
    if os.getenv("DEEPTUTOR_ALLOW_LIVE_RLS_TEST") != "1":
        pytest.skip("DEEPTUTOR_ALLOW_LIVE_RLS_TEST=1 is required")
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("select current_database()")
        database_name = str(cursor.fetchone()[0])
    if not database_name.startswith("deeptutor_invite_release_eval"):
        pytest.fail(f"refusing non-isolated database: {database_name}")
    return dsn


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_learner_roles_cannot_read_write_or_execute_invite_authority(role: str) -> None:
    dsn = _isolated_dsn()
    with psycopg.connect(dsn, autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute(f"set role {role}")
        for table in _TABLES:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(f"select * from public.{table} limit 1")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                "select public.reserve_experience_turn(%s, %s, %s, %s)",
                ("qa_eval_rls_user", "qa_eval_rls_turn", 800000, 1000000),
            )


def test_service_role_can_use_invite_authority_and_tables_are_force_rls() -> None:
    dsn = _isolated_dsn()
    suffix = uuid4().hex
    code_hash = suffix * 2
    user_id = f"qa_eval_rls_{suffix}"
    with psycopg.connect(dsn, autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select relname, relrowsecurity, relforcerowsecurity
              from pg_class
             where relnamespace = 'public'::regnamespace
               and relname = any(%s)
            """,
            (list(_TABLES),),
        )
        assert {row[0]: (row[1], row[2]) for row in cursor.fetchall()} == {
            table: (True, True) for table in _TABLES
        }
        cursor.execute("set role service_role")
        cursor.execute(
            """
            insert into public.experience_invites
              (code_hash, code_prefix, source, created_by)
            values (%s, %s, %s, %s)
            returning id
            """,
            (code_hash, "YS-RLS", "qa_eval_rls", "qa_eval_rls_runner"),
        )
        invite_id = cursor.fetchone()[0]
        cursor.execute(
            "select public.redeem_experience_invite(%s, %s)",
            (user_id, code_hash),
        )
        assert cursor.fetchone() is not None
        cursor.execute(
            "select count(*) from public.experience_access where invite_id = %s",
            (invite_id,),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute("reset role")
        cursor.execute("delete from public.experience_access where user_id = %s", (user_id,))
        cursor.execute("delete from public.experience_invites where id = %s", (invite_id,))
