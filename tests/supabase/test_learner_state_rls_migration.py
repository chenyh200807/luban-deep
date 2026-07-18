from __future__ import annotations

from pathlib import Path


def test_learner_state_rls_migration_enables_rls_and_self_scoped_policies() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260419000100_learner_state_rls.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()

    for table in (
        "learner_summaries",
        "learner_memory_events",
        "learning_plans",
        "learning_plan_pages",
        "heartbeat_jobs",
        "bot_learner_overlays",
        "bot_learner_overlay_events",
        "bot_learner_overlay_audit",
    ):
        assert f"alter table public.{table} enable row level security;" in sql

    for policy_name in (
        "learner_summaries_self_access",
        "learner_memory_events_self_access",
        "learning_plans_self_access",
        "learning_plan_pages_self_access",
        "heartbeat_jobs_self_access",
        "bot_learner_overlays_self_access",
        "bot_learner_overlay_events_self_access",
        "bot_learner_overlay_audit_self_access",
    ):
        assert f'create policy "{policy_name}"' in sql

    assert "auth.uid()::text = user_id" in sql
    assert "auth.uid() = user_id" not in sql


def test_bot_learner_overlay_migration_uses_text_user_id_like_core_tables() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260415000200_bot_learner_overlay.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()

    assert "user_id text not null references public.users(id) on delete cascade" in sql
    assert "user_id uuid not null references public.users(id) on delete cascade" not in sql


def test_learner_mistake_book_migration_enables_rls_and_subject_bot_isolation() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260521000100_learner_mistake_book_items.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()

    assert "create table if not exists public.learner_mistake_book_items" in sql
    assert "user_id text not null" in sql
    assert "subject_id text not null default ''" in sql
    assert "bot_id text not null default ''" in sql
    assert "mastered_at timestamptz" in sql
    assert "last_reviewed_at timestamptz" in sql
    assert "review_due_at timestamptz" in sql
    assert "unique (user_id, event_id)" in sql
    assert "idx_learner_mistake_book_user_subject_bot" in sql
    assert "alter table public.learner_mistake_book_items enable row level security;" in sql

    for policy_name in (
        "learner_mistake_book_items_owner_select",
        "learner_mistake_book_items_owner_insert",
        "learner_mistake_book_items_owner_update",
        "learner_mistake_book_items_owner_delete",
    ):
        assert f'create policy "{policy_name}"' in sql

    assert "auth.uid()::text = user_id" in sql


def test_assessment_sessions_do_not_require_public_users_mirror_row() -> None:
    migration_root = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    create_sql = (migration_root / "20260524000100_assessment_sessions.sql").read_text(
        encoding="utf-8"
    ).lower()
    hotfix_sql = (
        migration_root / "20260525000100_assessment_sessions_user_id_no_fk.sql"
    ).read_text(encoding="utf-8").lower()

    assert "user_id text not null" in create_sql
    assert "user_id text not null references public.users" not in create_sql
    assert "drop constraint if exists assessment_sessions_user_id_fkey" in hotfix_sql
    assert "auth.uid()::text = user_id" in create_sql


def test_assessment_sessions_security_hotfix_is_service_role_only() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260625000100_assessment_sessions_service_role_only.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()

    assert "alter table public.assessment_sessions enable row level security;" in sql
    assert "alter table public.assessment_sessions force row level security;" in sql

    for policy_name in (
        "assessment_sessions_owner_select",
        "assessment_sessions_owner_insert",
        "assessment_sessions_owner_update",
    ):
        assert f'drop policy if exists "{policy_name}" on public.assessment_sessions' in sql

    assert "revoke all on public.assessment_sessions from anon;" in sql
    assert "revoke all on public.assessment_sessions from authenticated;" in sql
    assert "session_questions_private" in sql
    assert "submitted_answer_snapshot" in sql
    assert "result_report_json" in sql


def test_assessment_forms_security_hotfix_is_narrow_service_role_only() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260525130000_assessment_forms_service_role_only.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()

    assert "alter table public.assessment_forms enable row level security;" in sql
    assert "revoke all on public.assessment_forms from anon;" in sql
    assert "revoke all on public.assessment_forms from authenticated;" in sql
    assert "items_json" in sql
    assert "assessment_forms_public" in sql
    assert "question_bank_size" in sql
    assert "fallback_used" in sql
    assert "source_fingerprint" not in sql
    assert "created_at" not in sql

    touched_tables = {
        line.split("public.", 1)[1].split()[0].strip(";")
        for line in sql.splitlines()
        if " public." in line
    }
    assert touched_tables == {"assessment_forms", "assessment_forms_public"}


def test_live_rls_regression_tables_force_rls() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260613000100_force_rls_on_sensitive_tables.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()

    for table in (
        "user_profiles",
        "user_stats",
        "user_goals",
        "user_logs",
        "user_emotion_logs",
        "user_badges",
        "learner_mistake_book_items",
        "questions_bank",
        "mock_exams",
        "wallets",
    ):
        assert f"alter table public.{table} force row level security;" in sql


def test_luban_retest_probe_claim_reuses_ledger_and_is_service_role_only() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260716000100_learner_state_luban_retest_probe_claim.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()

    assert "create table" not in sql
    assert "insert into public.learner_memory_events" in sql
    assert "on conflict (dedupe_key) do nothing" in sql
    assert "jsonb_build_array" in sql
    assert "encode(digest(v_identity_json, 'sha256'), 'hex')" in sql
    assert "when v_winner_completion = btrim(p_completion_id) then 'acquired'" in sql
    assert "when v_winner_hash <> p_request_hash then 'conflict'" in sql
    assert "create or replace function public.read_luban_retest_completion_events" in sql
    for function_signature in (
        "public.claim_luban_retest_probe(text, text, text, text, text)",
        "public.read_luban_retest_completion_events(text, text)",
    ):
        assert f"revoke all on function {function_signature} from public" in sql
        assert f"revoke all on function {function_signature} from anon" in sql
        assert f"revoke all on function {function_signature} from authenticated" in sql
        assert f"grant execute on function {function_signature} to service_role" in sql


def test_retest_probe_canonical_identity_migration_recovers_legacy_winner() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260718000100_learner_state_retest_probe_canonical_identity.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()

    assert "create table" not in sql
    assert "create or replace function public.canonical_luban_cycle_anchor" in sql
    assert "replace(lower(v_value::uuid::text), '-', '')" in sql
    assert "create or replace function public.claim_luban_retest_probe" in sql
    assert "event.source_feature = 'luban_retest_claim'" in sql
    assert "event.memory_kind = 'retest_control_claim'" in sql
    assert "event.payload_json->>'event_type' = 'retest_probe_claim'" in sql
    assert "public.canonical_luban_cycle_anchor(" in sql
    assert "order by event.created_at asc, event.event_id asc" in sql
    assert "raise warning 'multiple equivalent retest probe claim winners" in sql
    assert "'cycle_anchor', v_cycle_anchor" in sql
    assert "on conflict (dedupe_key) do nothing" in sql
    for function_signature in (
        "public.canonical_luban_cycle_anchor(text)",
        "public.claim_luban_retest_probe(text, text, text, text, text)",
    ):
        assert f"revoke all on function {function_signature} from public" in sql
        assert f"revoke all on function {function_signature} from anon" in sql
        assert f"revoke all on function {function_signature} from authenticated" in sql
        assert f"grant execute on function {function_signature} to service_role" in sql
