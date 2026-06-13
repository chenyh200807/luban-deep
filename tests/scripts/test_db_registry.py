"""TDD for scripts/check_db_registry.py — the DB-resource policy gate.

The guard turns the RESOURCE_GOVERNANCE_FIX_PLAN root-cause business fact —
"每个数据写入/连接，必须能被机器确认它登记在唯一 canonical 清单里：哪个 fact
落哪个库哪张表、谁能写" — into a real CI gate. It scans changed code and fails on
three conditions:

  (a) unregistered raw psycopg.connect (a NEW ad-hoc connection — 止血 rule);
  (b) a direct SQL write to a table not registered in db_registry.yaml tables[];
  (c) a *_DATABASE_URL / DB_URL env not declared on any registered database.

These tests pin the three fail rules + the pass paths + the scope carve-outs.
They run on synthetic code snippets (no live import of the scanned modules), so
they are deterministic and do not touch any parallel WIP source files.
"""

from __future__ import annotations

from scripts.check_db_registry import (
    collect_connect_usages,
    collect_env_usages,
    collect_write_usages,
    evaluate_db_registry,
    evaluate_db_usages,
    load_db_registry,
)


# ── Registry loads and exposes the single canonical list ─────────────────────
def test_registry_loads_databases_facts_and_grandfathered_sites() -> None:
    registry = load_db_registry()
    # grandfathered存量 sites are indexed (so they are not flagged as new ad-hoc)
    assert (
        "deeptutor/services/member_console/service.py"
        in registry["grandfathered_sites"]
    )
    assert (
        "deeptutor/services/benchmark/kb_v5_readonly_adapter.py"
        in registry["grandfathered_sites"]
    )
    # the 4+ DB-url env namespaces are declared on a registered database
    for env in ("DATABASE_URL", "DB_URL", "KBV5_DB_URL", "QUESTIONS_BANK_DB_URL"):
        assert env in registry["declared_url_envs"], env
    # writer registered tables include the user-identity write target
    assert "public.user_identity_aliases" in registry["registered_tables"]


# ── FAIL RULE (a): unregistered raw connection (止血 — new ad-hoc) ────────────
def test_fail_new_ad_hoc_raw_connection() -> None:
    # min repro: a brand-new production file opens a raw psycopg connection.
    code = "import psycopg2\nconn = psycopg2.connect(os.getenv('SOME_DB_URL'))\n"
    connects = collect_connect_usages([("deeptutor/services/new_store.py", code)])
    ok, message = evaluate_db_usages(connects, [], [], load_db_registry())
    assert ok is False
    assert "unregistered raw DB connection" in message
    assert "deeptutor/services/new_store.py" in message


def test_pass_grandfathered_raw_connection_site() -> None:
    # regression: an existing存量 site is grandfathered and must NOT be flagged.
    code = "conn = psycopg2.connect(self._database_url, connect_timeout=5)\n"
    connects = collect_connect_usages(
        [("deeptutor/services/member_console/service.py", code)]
    )
    ok, message = evaluate_db_usages(connects, [], [], load_db_registry())
    assert ok is True
    assert "passed" in message


def test_pass_factory_module_is_the_one_approved_connect_site() -> None:
    registry = load_db_registry()
    factory_path = registry["factory_module"]
    code = "return psycopg.connect(url, connect_timeout=timeout)\n"
    connects = collect_connect_usages([(factory_path, code)])
    ok, _ = evaluate_db_usages(connects, [], [], registry)
    assert ok is True


# ── FAIL RULE (b): write to an unregistered table ────────────────────────────
# The write-rule only governs raw-psycopg files, so each snippet carries an
# ``import psycopg2`` marker (real raw-PG writers all do).
_PG = "import psycopg2\n"


def test_fail_write_to_unregistered_table() -> None:
    # min repro: a write whose target table no one declared canonical → the
    # cross-db silent-write hole.
    code = _PG + "cur.execute('insert into public.shadow_scores (a) values (%s)', (1,))\n"
    writes = collect_write_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is False
    assert "UNREGISTERED table" in message
    assert "public.shadow_scores" in message


def test_pass_write_to_registered_table() -> None:
    # regression: a write to a registered table passes (with or without schema).
    code = _PG + "cur.execute('insert into public.user_identity_aliases (a) values (%s)')\n"
    writes = collect_write_usages([("deeptutor/services/member_console/service.py", code)])
    ok, message = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is True
    assert "passed" in message


def test_pass_write_to_registered_table_bare_name() -> None:
    # the registry registers public.luban_feedback; a bare-name write passes too.
    code = _PG + "cur.execute('update luban_feedback set status = %s where id = %s')\n"
    writes = collect_write_usages([("deeptutor/services/luban_feedback_store.py", code)])
    ok, _ = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is True


def test_on_conflict_do_update_set_not_mistaken_for_table_write() -> None:
    # 'ON CONFLICT (k) DO UPDATE SET col = ...' is the upsert clause, not a write
    # to a table called 'set'. (Real-world false positive caught during dev.)
    code = _PG + "sql = 'insert into public.user_identity_aliases (a) values (%s) on conflict (a) do update set b = excluded.b'\n"
    writes = collect_write_usages([("deeptutor/services/member_console/service.py", code)])
    ok, message = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is True, message


def test_english_prose_update_not_flagged() -> None:
    # docstrings / log messages ("Update a session", "delete from cache") must
    # never be mistaken for SQL writes — even in a psycopg file.
    code = _PG + '"""Update a session with new data."""\nlogger.info("delete from queue done")\n'
    writes = collect_write_usages([("deeptutor/services/x.py", code)])
    ok, _ = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is True


def test_non_psycopg_file_writes_out_of_scope() -> None:
    # A SQLite / ORM write in a file with no raw psycopg connection is out of
    # scope (the registry governs RLS-bypassing raw-PG writes only).
    code = "conn.execute('insert into rate_limit_buckets (k) values (?)')\n"  # SQLite '?'
    writes = collect_write_usages([("deeptutor/api/dependencies/rate_limit.py", code)])
    ok, _ = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is True


# ── FAIL RULE (c): undeclared DB-url env ─────────────────────────────────────
def test_fail_undeclared_db_url_env() -> None:
    # min repro: a new url env that no registered database claims → a new
    # (unregistered) database target can be selected.
    code = "url = os.getenv('SHADOW_REPLICA_DATABASE_URL')\n"
    envs = collect_env_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_db_usages([], [], envs, load_db_registry())
    assert ok is False
    assert "SHADOW_REPLICA_DATABASE_URL" in message
    assert "not\n" in message or "is not " in message


def test_pass_declared_db_url_env() -> None:
    code = "url = os.getenv('KBV5_DB_URL')\nfb = os.getenv('FEEDBACK_DATABASE_URL')\n"
    envs = collect_env_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_db_usages([], [], envs, load_db_registry())
    assert ok is True
    assert "passed" in message


# ── SCOPE CARVE-OUTS: out-of-scope must not be flagged (no false positives) ──
def test_supabase_rest_url_env_not_flagged() -> None:
    # SUPABASE_URL is the PostgREST endpoint (RLS-governed), not a raw-connect url.
    code = "self._base_url = os.getenv('SUPABASE_URL')\n"
    envs = collect_env_usages([("deeptutor/services/learner_state/supabase_store.py", code)])
    ok, _ = evaluate_db_usages([], [], envs, load_db_registry())
    assert ok is True


def test_tests_dir_out_of_scope_via_changed_files_entry() -> None:
    # The changed-files entry point ignores tests/ and non-deeptutor/scripts paths,
    # so a raw connect inside a test file is never flagged.
    ok, message = evaluate_db_registry(
        ["tests/services/test_new_thing.py", "docs/plan/whatever.md"]
    )
    assert ok is True
    assert "no in-scope production source changed" in message


def test_comment_lines_not_flagged() -> None:
    # A commented-out connect / write must not trip the guard.
    code = "# conn = psycopg2.connect(url)\n# insert into shadow_table values (1)\n"
    connects = collect_connect_usages([("deeptutor/services/x.py", code)])
    writes = collect_write_usages([("deeptutor/services/x.py", code)])
    ok, _ = evaluate_db_usages(connects, writes, [], load_db_registry())
    assert ok is True
