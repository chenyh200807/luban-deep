"""P0-2 rollout guard: provenance boost stays default-OFF (contract rag.md §22).

The 70/100 eval flagged provenance boost as a "free lunch", but contract §22
pins it default-OFF (exact-question pinning must not depend on provenance
boost). So P0-2 does NOT flip the code default — staging enables it via env to
measure the true-vs-false delta against the P0-1 baseline, then a contract
change can land if the data justifies it. These tests lock the contract default
and the env on/off path the baseline relies on.
"""
from __future__ import annotations

import pytest

from deeptutor.services.rag.pipelines import supabase as supabase_module


class _FakeKbConfigService:
    def get_kb_config(self, kb_name: str) -> dict[str, object]:
        _ = kb_name
        return {}


def _load_config(monkeypatch: pytest.MonkeyPatch, *, env: dict[str, str] | None = None):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setattr(
        supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService()
    )
    monkeypatch.delenv("SUPABASE_RAG_PROVENANCE_BOOST_ENABLED", raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    pipeline = supabase_module.SupabasePipeline()
    return pipeline._load_search_config(kb_name="construction-exam", kwargs={})


def test_provenance_boost_default_disabled(monkeypatch):
    """Contract rag.md §22: provenance boost ships default-OFF."""
    config = _load_config(monkeypatch)
    assert config.provenance_boost_enabled is False


def test_provenance_boost_env_can_enable_for_staging_baseline(monkeypatch):
    """Staging opens it via env to measure the baseline delta (no code flip)."""
    config = _load_config(
        monkeypatch, env={"SUPABASE_RAG_PROVENANCE_BOOST_ENABLED": "true"}
    )
    assert config.provenance_boost_enabled is True


def test_provenance_boost_env_explicit_disable(monkeypatch):
    config = _load_config(
        monkeypatch, env={"SUPABASE_RAG_PROVENANCE_BOOST_ENABLED": "false"}
    )
    assert config.provenance_boost_enabled is False
