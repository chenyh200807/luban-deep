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

import yaml

from scripts.check_db_registry import (
    REGISTRY_PATH,
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
    for table in (
        "public.luban_canonical_taxonomy",
        "public.luban_canonical_knowledge_catalog",
        "public.luban_canonical_knowledge_edges",
    ):
        assert table in registry["registered_tables"]


def test_canonical_projection_tables_require_rls_in_registry() -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    tables = {
        str(item.get("name")): item
        for item in (payload.get("tables") or [])
        if isinstance(item, dict) and item.get("name")
    }

    for table in (
        "public.luban_canonical_taxonomy",
        "public.luban_canonical_knowledge_catalog",
        "public.luban_canonical_knowledge_edges",
    ):
        assert tables[table]["rls_required"] is True


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


def test_export_canonical_knowledge_full_refresh_writes_are_registered() -> None:
    from scripts.check_db_registry import REPO_ROOT

    script = REPO_ROOT / "scripts" / "export_canonical_knowledge_to_supabase.py"
    code = script.read_text(encoding="utf-8")
    writes = collect_write_usages([("scripts/export_canonical_knowledge_to_supabase.py", code)])
    tables = {w.table for w in writes}

    assert "public.luban_canonical_taxonomy" in tables
    assert "public.luban_canonical_knowledge_catalog" in tables
    assert "public.luban_canonical_knowledge_edges" in tables
    ok, message = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is True, message


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


# ═════════════════════════════════════════════════════════════════════════════
# I3(a) — aliased import: ``import psycopg as pg`` then ``pg.connect(``
# ═════════════════════════════════════════════════════════════════════════════
def test_i3a_aliased_import_raw_connection_detected() -> None:
    # I3(a) regression: the un-aliased ``psycopg.connect`` regex missed
    # ``import psycopg as pg; pg.connect(...)`` entirely — a new ad-hoc raw
    # connection could slip in behind the alias.
    code = "import psycopg as pg\nconn = pg.connect(os.getenv('SOME_DB_URL'))\n"
    connects = collect_connect_usages([("deeptutor/services/new_store.py", code)])
    assert connects, "aliased pg.connect must be detected (I3a)"
    ok, message = evaluate_db_usages(connects, [], [], load_db_registry())
    assert ok is False
    assert "unregistered raw DB connection" in message


def test_i3a_aliased_connect_at_grandfathered_site_passes() -> None:
    # I3(a) no-false-positive: an aliased connect at a grandfathered site still passes.
    code = "import psycopg2 as db\nconn = db.connect(self._database_url)\n"
    connects = collect_connect_usages(
        [("deeptutor/services/member_console/service.py", code)]
    )
    assert connects
    ok, _ = evaluate_db_usages(connects, [], [], load_db_registry())
    assert ok is True


def test_i3a_unrelated_dot_connect_not_an_alias() -> None:
    # I3(a) no-false-positive: a ``something.connect(`` with no psycopg alias import
    # in the file is NOT a raw psycopg connection (e.g. a websocket / socket connect).
    code = "ws = client.connect('wss://x')\n"
    connects = collect_connect_usages([("deeptutor/services/x.py", code)])
    assert connects == []


# ═════════════════════════════════════════════════════════════════════════════
# I3(b) — COPY … FROM and TRUNCATE are write surfaces
# ═════════════════════════════════════════════════════════════════════════════
def test_i3b_copy_from_stdin_to_unregistered_table_flagged() -> None:
    # I3(b) regression: COPY (bulk ingest via copy_expert / COPY … FROM STDIN) is a
    # write surface the original rule missed entirely.
    code = _PG + "cur.copy_expert('copy public.shadow_scores from stdin', f)\n"
    writes = collect_write_usages([("deeptutor/services/x.py", code)])
    assert any(w.table == "public.shadow_scores" for w in writes)
    ok, message = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is False
    assert "public.shadow_scores" in message


def test_i3b_truncate_unregistered_table_flagged() -> None:
    # I3(b) regression: TRUNCATE (destructive table-empty) is a write surface.
    code = _PG + "cur.execute('truncate table public.shadow_scores')\n"
    writes = collect_write_usages([("deeptutor/services/x.py", code)])
    assert any(w.table == "public.shadow_scores" for w in writes)
    ok, message = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is False
    assert "public.shadow_scores" in message


def test_i3b_copy_and_truncate_to_registered_table_pass() -> None:
    # I3(b) no-false-positive: COPY / TRUNCATE against a registered table passes.
    code = (
        _PG
        + "cur.copy_expert('copy public.user_identity_aliases from stdin', f)\n"
        + "cur.execute('truncate table public.user_identity_aliases')\n"
    )
    writes = collect_write_usages([("deeptutor/services/member_console/service.py", code)])
    ok, _ = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is True


def test_i3b_copy_and_truncate_prose_not_flagged() -> None:
    # I3(b) no-false-positive: English prose / log strings ("Copy data from the
    # buffer", "truncate the string") must never be mistaken for SQL COPY/TRUNCATE.
    code = (
        _PG
        + '"""Copy data from the upstream buffer into memory."""\n'
        + 'logger.info("truncate the string to 100 chars")\n'
    )
    writes = collect_write_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_db_usages([], writes, [], load_db_registry())
    assert ok is True, message


def test_full_repo_db_scan_has_zero_false_positives() -> None:
    """Whole-repo DB scan over real production source must be GREEN (I3 fix安全网)."""
    import subprocess

    from scripts.check_db_registry import REPO_ROOT, evaluate_db_registry

    tracked = subprocess.run(
        ["git", "ls-files", "deeptutor/**/*.py", "scripts/**/*.py"],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    ).stdout.split()
    ok, message = evaluate_db_registry(tracked)
    assert ok is True, message


# ═════════════════════════════════════════════════════════════════════════════
# M2 — ``--all`` self-scans via the scanner's own git ls-files (no shell split)
# ═════════════════════════════════════════════════════════════════════════════
def test_m2_all_flag_self_scans_and_matches_explicit_file_mode() -> None:
    # M2 regression: ``--all`` (the CI-safe mode) returns 0 and the scanner's own
    # tracked-file collection equals the explicit ``git ls-files`` set, so swapping
    # the unquoted $(…) for --all in CI cannot change the verdict.
    import subprocess

    from scripts.check_db_registry import (
        REPO_ROOT,
        _git_tracked_in_scope_files,
        main,
    )

    explicit = set(
        subprocess.run(
            ["git", "ls-files", "deeptutor/**/*.py", "scripts/**/*.py"],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        ).stdout.split()
    )
    assert set(_git_tracked_in_scope_files()) == explicit
    assert main(["--all"]) == 0


def test_m2_all_flag_is_shell_word_split_safe() -> None:
    # M2: ``_git_tracked_in_scope_files`` uses ``git ls-files -z`` + NUL split, so a
    # path containing a space stays ONE entry (the unquoted $(…) bug would split it).
    # We assert no entry is a fragment of a spaced path (no bare token that is half
    # of a real file). Direct proof: every returned path exists as a single file.
    from pathlib import Path

    from scripts.check_db_registry import REPO_ROOT, _git_tracked_in_scope_files

    for p in _git_tracked_in_scope_files():
        assert (Path(REPO_ROOT) / p).is_file(), f"word-split fragment leaked: {p!r}"


# ═════════════════════════════════════════════════════════════════════════════
# I3(c) — Codex adversarial round: ``from psycopg import connect`` then bare
# ``connect(``. The aliased-import fix (I3a) only covered ``import psycopg as X``.
# A from-import (1) binds the connect callable to a bare name the alias matcher
# could not see, and (2) the file did not match _PSYCOPG_FILE_RE at all, so the
# ENTIRE SQL-write scan was skipped for it — a double bypass.
# ═════════════════════════════════════════════════════════════════════════════
def test_i3c_from_import_connect_raw_connection_detected() -> None:
    code = (
        "from psycopg import connect\n"
        "import os\n"
        "conn = connect(os.environ['SHADOW_DB_URL'])\n"
    )
    connects = collect_connect_usages([("deeptutor/services/new_store.py", code)])
    assert connects, "from psycopg import connect; connect(...) must be detected (I3c)"
    ok, message = evaluate_db_usages(connects, [], [], load_db_registry())
    assert ok is False
    assert "unregistered raw DB connection" in message


def test_i3c_from_import_connect_aliased_detected() -> None:
    code = "from psycopg2 import connect as pgc\nconn = pgc(url)\n"
    connects = collect_connect_usages([("deeptutor/services/new_store.py", code)])
    assert connects, "aliased from-import connect must be detected (I3c)"


def test_i3c_from_import_file_gate_runs_sql_write_scan() -> None:
    # The deeper half of the bug: a from-import file did NOT match _PSYCOPG_FILE_RE,
    # so collect_write_usages skipped it whole and the write below was invisible.
    code = (
        "from psycopg import connect\n"
        "cur.execute('insert into public.shadow_table (a) values (%s)')\n"
    )
    writes = collect_write_usages([("deeptutor/services/x.py", code)])
    assert any(
        w.table == "public.shadow_table" for w in writes
    ), "write scan must run on from-import psycopg files (I3c)"


def test_i3c_bare_connect_without_psycopg_import_not_flagged() -> None:
    # No-false-positive: a bare ``connect(`` with no psycopg from-import is unrelated
    # (signal.connect, websocket connect) and must NOT be treated as a raw PG connect.
    code = "btn_connect = connect('wss://x')\n"
    connects = collect_connect_usages([("deeptutor/services/x.py", code)])
    assert connects == []
