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
