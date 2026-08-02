import json
from pathlib import Path
import re
import stat

from deeptutor.services.config.env_store import EnvStore
from deeptutor.services.config.model_catalog import ModelCatalogService


def test_load_hydrates_empty_catalog_from_env(tmp_path: Path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_BINDING=google",
                "LLM_MODEL=gemini-3-flash-preview",
                "LLM_API_KEY=test-llm-key",
                "LLM_HOST=https://example-llm.test/v1",
                "EMBEDDING_BINDING=openai",
                "EMBEDDING_MODEL=text-embedding-3-large",
                "EMBEDDING_API_KEY=test-emb-key",
                "EMBEDDING_HOST=https://example-emb.test/v1",
                "EMBEDDING_DIMENSION=3072",
                "SEARCH_PROVIDER=perplexity",
                "SEARCH_API_KEY=test-search-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    catalog_path = tmp_path / "model_catalog.json"
    catalog_path.write_text(
        """{
  "version": 1,
  "services": {
    "llm": {"active_profile_id": null, "active_model_id": null, "profiles": []},
    "embedding": {"active_profile_id": null, "active_model_id": null, "profiles": []},
    "search": {"active_profile_id": null, "profiles": []}
  }
}
""",
        encoding="utf-8",
    )

    env_store = EnvStore(path=env_path)
    monkeypatch.setattr("deeptutor.services.config.model_catalog.get_env_store", lambda: env_store)

    service = ModelCatalogService(path=catalog_path)
    catalog = service.load()

    assert catalog["services"]["llm"]["profiles"][0]["binding"] == "google"
    assert catalog["services"]["llm"]["profiles"][0]["extra_headers"] == {}
    assert catalog["services"]["llm"]["profiles"][0]["models"][0]["model"] == "gemini-3-flash-preview"
    assert catalog["services"]["embedding"]["profiles"][0]["models"][0]["dimension"] == "3072"
    assert catalog["services"]["search"]["profiles"][0]["provider"] == "perplexity"
    assert catalog["services"]["search"]["profiles"][0]["proxy"] == ""


def test_load_syncs_existing_active_profiles_from_env(tmp_path: Path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_BINDING=dashscope",
                "LLM_MODEL=qwen3.5-plus",
                "LLM_API_KEY=new-llm-key",
                "LLM_HOST=https://dashscope.aliyuncs.com/compatible-mode/v1",
                "EMBEDDING_BINDING=dashscope",
                "EMBEDDING_MODEL=text-embedding-v4",
                "EMBEDDING_API_KEY=new-emb-key",
                "EMBEDDING_HOST=https://dashscope.aliyuncs.com/compatible-mode/v1",
                "EMBEDDING_DIMENSION=2048",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    catalog_path = tmp_path / "model_catalog.json"
    catalog_path.write_text(
        """{
  "version": 1,
  "services": {
    "llm": {
      "active_profile_id": "llm-profile-default",
      "active_model_id": "llm-model-default",
      "profiles": [
        {
          "id": "llm-profile-default",
          "name": "Default LLM Endpoint",
          "binding": "openai",
          "base_url": "https://old-llm.example/v1",
          "api_key": "old-llm-key",
          "api_version": "",
          "extra_headers": {},
          "models": [
            {"id": "llm-model-default", "name": "old-model", "model": "old-model"}
          ]
        }
      ]
    },
    "embedding": {
      "active_profile_id": "embedding-profile-default",
      "active_model_id": "embedding-model-default",
      "profiles": [
        {
          "id": "embedding-profile-default",
          "name": "Default Embedding Endpoint",
          "binding": "openai",
          "base_url": "https://old-emb.example/v1",
          "api_key": "old-emb-key",
          "api_version": "",
          "extra_headers": {},
          "models": [
            {
              "id": "embedding-model-default",
              "name": "old-embedding",
              "model": "old-embedding",
              "dimension": "3072"
            }
          ]
        }
      ]
    },
    "search": {"active_profile_id": null, "profiles": []}
  }
}
""",
        encoding="utf-8",
    )

    env_store = EnvStore(path=env_path)
    monkeypatch.setattr("deeptutor.services.config.model_catalog.get_env_store", lambda: env_store)

    service = ModelCatalogService(path=catalog_path)
    catalog = service.load()

    llm_profile = catalog["services"]["llm"]["profiles"][0]
    llm_model = llm_profile["models"][0]
    emb_profile = catalog["services"]["embedding"]["profiles"][0]
    emb_model = emb_profile["models"][0]

    assert llm_profile["binding"] == "dashscope"
    assert llm_profile["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert llm_profile["api_key"] == "new-llm-key"
    assert llm_model["model"] == "qwen3.5-plus"
    assert llm_model["name"] == "qwen3.5-plus"
    assert emb_profile["binding"] == "dashscope"
    assert emb_profile["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert emb_profile["api_key"] == "new-emb-key"
    assert emb_model["model"] == "text-embedding-v4"
    assert emb_model["name"] == "text-embedding-v4"
    assert emb_model["dimension"] == "2048"


def test_save_preserves_existing_api_key_when_payload_leaves_it_blank(tmp_path: Path) -> None:
    catalog_path = tmp_path / "model_catalog.json"
    catalog_path.write_text(
        """{
  "version": 1,
  "services": {
    "llm": {
      "active_profile_id": "llm-profile-default",
      "active_model_id": "llm-model-default",
      "profiles": [
        {
          "id": "llm-profile-default",
          "name": "Default LLM Endpoint",
          "binding": "openai",
          "base_url": "https://existing.example/v1",
          "api_key": "existing-secret",
          "api_version": "",
          "extra_headers": {},
          "models": [{"id": "llm-model-default", "name": "gpt", "model": "gpt"}]
        }
      ]
    },
    "embedding": {"active_profile_id": null, "active_model_id": null, "profiles": []},
    "search": {"active_profile_id": null, "profiles": []}
  }
}
""",
        encoding="utf-8",
    )

    service = ModelCatalogService(path=catalog_path)
    saved = service.save(
        {
            "version": 1,
            "services": {
                "llm": {
                    "active_profile_id": "llm-profile-default",
                    "active_model_id": "llm-model-default",
                    "profiles": [
                        {
                            "id": "llm-profile-default",
                            "name": "Updated Endpoint",
                            "binding": "openai",
                            "base_url": "https://updated.example/v1",
                            "api_key": "",
                            "api_version": "",
                            "extra_headers": {},
                            "models": [
                                {
                                    "id": "llm-model-default",
                                    "name": "gpt-4.1",
                                    "model": "gpt-4.1",
                                }
                            ],
                        }
                    ],
                },
                "embedding": {"active_profile_id": None, "active_model_id": None, "profiles": []},
                "search": {"active_profile_id": None, "profiles": []},
            },
        }
    )

    assert saved["services"]["llm"]["profiles"][0]["api_key"] == "existing-secret"


def test_sanitize_redacts_api_keys(tmp_path: Path) -> None:
    service = ModelCatalogService(path=tmp_path / "model_catalog.json")
    catalog = {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "llm-profile-default",
                "active_model_id": "llm-model-default",
                "profiles": [
                    {
                        "id": "llm-profile-default",
                        "name": "Default LLM Endpoint",
                        "binding": "openai",
                        "base_url": "https://example.test/v1",
                        "api_key": "sk-secret-1234",
                        "api_version": "",
                        "extra_headers": {},
                        "models": [{"id": "llm-model-default", "name": "gpt", "model": "gpt"}],
                    }
                ],
            },
            "embedding": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "search": {"active_profile_id": None, "profiles": []},
        },
    }

    sanitized = service.sanitize(catalog)
    profile = sanitized["services"]["llm"]["profiles"][0]

    assert profile["api_key"] == ""
    assert profile["api_key_configured"] is True
    assert profile["api_key_last4"] == "1234"


def test_save_can_redact_model_catalog_at_rest_without_changing_runtime_catalog(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_REDACT_MODEL_CATALOG_API_KEYS_AT_REST", "1")
    catalog_path = tmp_path / "model_catalog.json"
    service = ModelCatalogService(path=catalog_path)

    saved = service.save(
        {
            "version": 1,
            "services": {
                "llm": {
                    "active_profile_id": "llm-profile-default",
                    "active_model_id": "llm-model-default",
                    "profiles": [
                        {
                            "id": "llm-profile-default",
                            "name": "Default LLM Endpoint",
                            "binding": "openai",
                            "base_url": "https://example.test/v1",
                            "api_key": "sk-runtime-secret-1234567890",
                            "api_version": "",
                            "extra_headers": {},
                            "models": [{"id": "llm-model-default", "name": "gpt", "model": "gpt"}],
                        }
                    ],
                },
                "embedding": {
                    "active_profile_id": "embedding-profile-default",
                    "active_model_id": "embedding-model-default",
                    "profiles": [
                        {
                            "id": "embedding-profile-default",
                            "name": "Default Embedding Endpoint",
                            "binding": "openai",
                            "base_url": "https://embedding.example.test/v1",
                            "api_key": "sk-embedding-secret-1234567890",
                            "api_version": "",
                            "extra_headers": {},
                            "models": [
                                {
                                    "id": "embedding-model-default",
                                    "name": "text-embedding",
                                    "model": "text-embedding",
                                }
                            ],
                        }
                    ],
                },
                "search": {"active_profile_id": None, "profiles": []},
            },
        }
    )

    rendered = catalog_path.read_text(encoding="utf-8")
    persisted = json.loads(rendered)

    assert saved["services"]["llm"]["profiles"][0]["api_key"] == "sk-runtime-secret-1234567890"
    assert saved["services"]["embedding"]["profiles"][0]["api_key"] == "sk-embedding-secret-1234567890"
    assert persisted["services"]["llm"]["profiles"][0]["api_key"] == "[REDACTED]"
    assert persisted["services"]["embedding"]["profiles"][0]["api_key"] == "[REDACTED]"
    assert not re.search(r"sk-[A-Za-z0-9_-]{10,}", rendered)
    assert not re.search(r'api_key"\s*:\s*"(?!\[REDACTED\]|\s*")', rendered)


def _catalog_with_keys() -> dict:
    return {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "llm-profile-default",
                "active_model_id": "llm-model-default",
                "profiles": [
                    {
                        "id": "llm-profile-default",
                        "name": "Default LLM Endpoint",
                        "binding": "openai",
                        "base_url": "https://example.test/v1",
                        "api_key": "sk-runtime-secret-1234567890",
                        "api_version": "",
                        "extra_headers": {},
                        "models": [{"id": "llm-model-default", "name": "gpt", "model": "gpt"}],
                    }
                ],
            },
            "embedding": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "search": {"active_profile_id": None, "profiles": []},
        },
    }


def test_save_redacts_api_keys_at_rest_by_default(tmp_path: Path, monkeypatch) -> None:
    """Fail-safe default: an UNSET environment must not persist plaintext keys.

    This is the regression that matters. The old default was opt-in redaction,
    so an unset variable wrote live provider keys to disk in production.
    """

    monkeypatch.delenv("DEEPTUTOR_REDACT_MODEL_CATALOG_API_KEYS_AT_REST", raising=False)
    monkeypatch.delenv("DEEPTUTOR_MODEL_CATALOG_PLAINTEXT_API_KEYS_AT_REST", raising=False)
    catalog_path = tmp_path / "model_catalog.json"

    saved = ModelCatalogService(path=catalog_path).save(_catalog_with_keys())

    rendered = catalog_path.read_text(encoding="utf-8")
    # The runtime catalog still carries the real key...
    assert saved["services"]["llm"]["profiles"][0]["api_key"] == "sk-runtime-secret-1234567890"
    # ...but nothing sk-shaped may reach the file.
    assert "sk-runtime-secret-1234567890" not in rendered
    assert not re.search(r"sk-[A-Za-z0-9_-]{10,}", rendered)
    assert json.loads(rendered)["services"]["llm"]["profiles"][0]["api_key"] == "[REDACTED]"


def test_newly_written_catalog_file_contains_no_plaintext_sk_key(
    tmp_path: Path, monkeypatch
) -> None:
    """Whole-file assertion: no `sk-` plaintext anywhere, across a re-save cycle."""

    monkeypatch.delenv("DEEPTUTOR_MODEL_CATALOG_PLAINTEXT_API_KEYS_AT_REST", raising=False)
    catalog_path = tmp_path / "model_catalog.json"
    service = ModelCatalogService(path=catalog_path)

    service.save(_catalog_with_keys())
    # Re-saving reads the redacted file back; it must not resurrect or re-emit a key.
    service.save(_catalog_with_keys())

    rendered = catalog_path.read_text(encoding="utf-8")
    assert not re.search(r"sk-[A-Za-z0-9_-]{10,}", rendered)


def test_plaintext_at_rest_requires_explicit_opt_out(tmp_path: Path, monkeypatch) -> None:
    """The opt-out still works — otherwise the flip would be untestable/irreversible."""

    monkeypatch.setenv("DEEPTUTOR_MODEL_CATALOG_PLAINTEXT_API_KEYS_AT_REST", "1")
    catalog_path = tmp_path / "model_catalog.json"

    ModelCatalogService(path=catalog_path).save(_catalog_with_keys())

    rendered = catalog_path.read_text(encoding="utf-8")
    assert "sk-runtime-secret-1234567890" in rendered


def test_legacy_redact_flag_cannot_turn_redaction_off(tmp_path: Path, monkeypatch) -> None:
    """The old opt-in name must not be usable to re-open the plaintext hole."""

    monkeypatch.setenv("DEEPTUTOR_REDACT_MODEL_CATALOG_API_KEYS_AT_REST", "0")
    monkeypatch.delenv("DEEPTUTOR_MODEL_CATALOG_PLAINTEXT_API_KEYS_AT_REST", raising=False)
    catalog_path = tmp_path / "model_catalog.json"

    ModelCatalogService(path=catalog_path).save(_catalog_with_keys())

    assert not re.search(r"sk-[A-Za-z0-9_-]{10,}", catalog_path.read_text(encoding="utf-8"))


def test_saved_catalog_file_is_owner_read_write_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPTUTOR_MODEL_CATALOG_PLAINTEXT_API_KEYS_AT_REST", raising=False)
    catalog_path = tmp_path / "model_catalog.json"

    ModelCatalogService(path=catalog_path).save(_catalog_with_keys())

    assert stat.S_IMODE(catalog_path.stat().st_mode) == 0o600


def test_save_tightens_permissions_on_a_preexisting_world_readable_file(
    tmp_path: Path, monkeypatch
) -> None:
    """Reproduces the production shape: an existing 0777 catalog file.

    os.open only applies its mode when it CREATES the file, so without the
    explicit chmod the loose bits would survive every subsequent write.
    """

    monkeypatch.delenv("DEEPTUTOR_MODEL_CATALOG_PLAINTEXT_API_KEYS_AT_REST", raising=False)
    catalog_path = tmp_path / "model_catalog.json"
    catalog_path.write_text("{}", encoding="utf-8")
    catalog_path.chmod(0o777)

    ModelCatalogService(path=catalog_path).save(_catalog_with_keys())

    assert stat.S_IMODE(catalog_path.stat().st_mode) == 0o600


def _env_backed_store(tmp_path: Path, lines: list[str]) -> EnvStore:
    env_path = tmp_path / ".env"
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return EnvStore(path=env_path, fallback_paths=[])


def test_apply_never_renders_the_redaction_placeholder_into_env(
    tmp_path: Path, monkeypatch
) -> None:
    """The catastrophic case: a key that `.env` does NOT carry.

    With redaction at rest and no read-side strip, the persisted "[REDACTED]"
    round-trips through load() -> render_from_catalog() -> env_store.write() and
    becomes the live API key for every provider call. Removing
    `_strip_redacted_secrets` from load() must turn this test red.
    """

    monkeypatch.delenv("DEEPTUTOR_MODEL_CATALOG_PLAINTEXT_API_KEYS_AT_REST", raising=False)
    # Hermeticity is what makes this test falsifiable: EnvStore backfills
    # ENV_KEY_ORDER from os.environ, so an ambient LLM_API_KEY (left behind by a
    # sibling test that read the real .env) would re-hydrate the key and hide the
    # very bug this test exists to catch.
    for _leaked in ("LLM_API_KEY", "EMBEDDING_API_KEY", "SEARCH_API_KEY"):
        monkeypatch.delenv(_leaked, raising=False)
    # `.env` deliberately has NO LLM_API_KEY — the key lives only in the catalog,
    # as it would after being entered through the settings UI.
    store = _env_backed_store(
        tmp_path,
        ["LLM_BINDING=openai", "LLM_MODEL=deepseek-chat", "LLM_HOST=https://api.example.test"],
    )
    monkeypatch.setattr(
        "deeptutor.services.config.model_catalog.get_env_store", lambda: store
    )

    service = ModelCatalogService(path=tmp_path / "model_catalog.json")
    service.save(_catalog_with_keys())

    rendered = store.render_from_catalog(service.load())

    assert "[REDACTED]" not in rendered.values()
    assert all("[REDACTED]" not in str(v) for v in rendered.values())


def test_apply_preserves_the_real_key_when_env_carries_it(tmp_path: Path, monkeypatch) -> None:
    """The redaction must not CLEAR a key that `.env` can still supply."""

    monkeypatch.delenv("DEEPTUTOR_MODEL_CATALOG_PLAINTEXT_API_KEYS_AT_REST", raising=False)
    store = _env_backed_store(
        tmp_path,
        [
            "LLM_BINDING=openai",
            "LLM_MODEL=deepseek-chat",
            "LLM_HOST=https://api.example.test",
            "LLM_API_KEY=sk-real-env-key-424242",
        ],
    )
    monkeypatch.setattr(
        "deeptutor.services.config.model_catalog.get_env_store", lambda: store
    )

    service = ModelCatalogService(path=tmp_path / "model_catalog.json")
    service.save(_catalog_with_keys())

    reloaded = service.load()
    rendered = store.render_from_catalog(reloaded)

    # Real key survives the redact -> reload -> render round trip...
    assert rendered["LLM_API_KEY"] == "sk-real-env-key-424242"
    # ...while the file on disk still holds no plaintext.
    assert not re.search(
        r"sk-[A-Za-z0-9_-]{10,}", (tmp_path / "model_catalog.json").read_text(encoding="utf-8")
    )


def test_load_treats_redacted_placeholder_as_absent(tmp_path: Path, monkeypatch) -> None:
    """Unit-level guard on the single read-side handling point."""

    monkeypatch.delenv("DEEPTUTOR_MODEL_CATALOG_PLAINTEXT_API_KEYS_AT_REST", raising=False)
    # EnvStore.load() backfills ENV_KEY_ORDER from os.environ and then
    # os.environ.setdefault()s what it read, so a sibling test that touched the
    # real .env leaves a genuine LLM_API_KEY in this process. Clear it, or this
    # test silently asserts against an ambient production key.
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    store = _env_backed_store(tmp_path, ["LLM_BINDING=openai"])
    monkeypatch.setattr(
        "deeptutor.services.config.model_catalog.get_env_store", lambda: store
    )

    catalog_path = tmp_path / "model_catalog.json"
    service = ModelCatalogService(path=catalog_path)
    service.save(_catalog_with_keys())
    assert "[REDACTED]" in catalog_path.read_text(encoding="utf-8")

    profile = service.get_active_profile(service.load(), "llm")

    assert profile is not None
    assert profile["api_key"] == ""
