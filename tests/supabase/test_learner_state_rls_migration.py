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
