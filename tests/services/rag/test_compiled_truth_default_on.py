"""P0-2 regression: compiled_truth source ships default-ON (T5).

Guards the env-default flip in _load_search_config: the code default must be
True (shadow mode is promoted to real), and an explicit env override must
still turn it off — 2A requires prod to keep override=false until the P0-1
baseline validates.
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
    monkeypatch.delenv("SUPABASE_RAG_COMPILED_TRUTH_ENABLED", raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    pipeline = supabase_module.SupabasePipeline()
    return pipeline._load_search_config(kb_name="construction-exam", kwargs={})


def test_compiled_truth_default_enabled(monkeypatch):
    """After the P0-2 flip the code default is ON."""
    config = _load_config(monkeypatch)
    assert config.compiled_truth_enabled is True


def test_compiled_truth_env_override_still_disables(monkeypatch):
    """2A: env=false must keep it off in prod regardless of the code default."""
    config = _load_config(
        monkeypatch, env={"SUPABASE_RAG_COMPILED_TRUTH_ENABLED": "false"}
    )
    assert config.compiled_truth_enabled is False
