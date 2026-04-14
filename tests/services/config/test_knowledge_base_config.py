from __future__ import annotations

from deeptutor.services.config.knowledge_base_config import get_env_defined_kbs


def test_get_env_defined_kbs_supports_supabase_aliases(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_RAG_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("SUPABASE_RAG_DEFAULT_KB_NAME", "supabase-main")
    monkeypatch.setenv("SUPABASE_RAG_KB_ALIASES", "construction-exam,construction-exam-coach")

    env_kbs, defaults = get_env_defined_kbs()

    assert defaults["default_kb"] == "supabase-main"
    assert env_kbs["supabase-main"]["rag_provider"] == "supabase"
    assert env_kbs["construction-exam"]["rag_provider"] == "supabase"
    assert env_kbs["construction-exam"]["supabase_force_provider"] is True
    assert env_kbs["construction-exam-coach"]["supabase_remote_kb"] == "supabase-main"


def test_get_env_defined_kbs_includes_builtin_tutorbot_aliases(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_RAG_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("SUPABASE_RAG_DEFAULT_KB_NAME", "supabase-main")
    monkeypatch.delenv("SUPABASE_RAG_KB_ALIASES", raising=False)

    env_kbs, defaults = get_env_defined_kbs()

    assert defaults["default_kb"] == "supabase-main"
    assert env_kbs["construction-exam"]["rag_provider"] == "supabase"
    assert env_kbs["construction-exam"]["supabase_remote_kb"] == "supabase-main"
    assert env_kbs["construction-exam-coach"]["rag_provider"] == "supabase"
