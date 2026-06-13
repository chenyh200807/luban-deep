"""TDD for scripts/check_provider_registry.py — the LLM-provider policy gate.

The guard turns the RESOURCE_GOVERNANCE_FIX_PLAN root-cause business fact —
"每个外部 provider，必须能被机器确认它登记在唯一 canonical 清单里：canonical
base_url 在哪、key env 是哪个；不存在第二份 registry、不存在散落硬编码 base_url
旁路" — into a real CI gate. It scans changed code and fails on TWO conditions:

  (a) a NEW hardcoded provider base_url literal (base_url="https://<provider>")
      at a call site that is NOT the canonical registry and NOT grandfathered
      (止血 — stop the bleed on the 12 existing scattered endpoints);
  (b) a NEW provider added to a DEPRECATED registry copy (re-growing a second
      authority), or a NEW 4th ProviderSpec catalog file.

These tests pin the two fail rules + the pass paths + the scope carve-outs.
They run on synthetic code snippets (no live import of the scanned modules), so
they are deterministic and do not touch any parallel WIP source files. Mirrors
tests/scripts/test_db_registry.py + tests/scripts/test_env_registry.py.
"""

from __future__ import annotations

from scripts.check_provider_registry import (
    collect_base_url_usages,
    collect_provider_spec_usages,
    evaluate_provider_registry,
    evaluate_provider_usages,
    load_provider_registry,
)


# ── Registry loads and exposes the single canonical list ─────────────────────
def test_registry_loads_canonical_providers_and_grandfathered_sites() -> None:
    registry = load_provider_registry()
    # canonical authority module is recorded
    assert registry["canonical_module"] == "deeptutor/services/provider_registry.py"
    # known providers + base_urls are registered
    assert "deepseek" in registry["registered_providers"]
    assert "https://api.deepseek.com" in registry["registered_base_urls"]
    assert "https://api.openai.com/v1" in registry["registered_base_urls"]
    # the deprecated copies are recorded (so the guard forbids NEW providers there)
    assert "deeptutor/tutorbot/providers/registry.py" in registry["deprecated_modules"]
    assert "deeptutor/services/config/provider_runtime.py" in registry["deprecated_modules"]
    # grandfathered存量 bypass sites are indexed (so they are not flagged as new)
    assert "deeptutor/capabilities/deep_question.py" in registry["grandfathered_base_url_sites"]
    assert "deeptutor/services/llm/factory.py" in registry["grandfathered_base_url_sites"]


# ── FAIL RULE (a): a NEW hardcoded base_url (止血 — new scattered endpoint) ───
def test_fail_new_hardcoded_base_url_at_call_site() -> None:
    # min repro: a brand-new production file hardcodes a provider endpoint
    # instead of resolving it from the registry.
    code = 'client = AsyncOpenAI(api_key=k, base_url="https://api.deepseek.com")\n'
    usages = collect_base_url_usages([("deeptutor/services/new_caller.py", code)])
    ok, message = evaluate_provider_usages(usages, [], load_provider_registry())
    assert ok is False
    assert "hardcoded provider base_url" in message
    assert "deeptutor/services/new_caller.py" in message


def test_fail_new_hardcoded_base_url_via_or_fallback() -> None:
    # the `or "https://…"` default-fallback form is also a bypass.
    code = 'effective_base = base_url or "https://api.openai.com/v1"\n'
    usages = collect_base_url_usages([("deeptutor/services/new_caller.py", code)])
    ok, message = evaluate_provider_usages(usages, [], load_provider_registry())
    assert ok is False
    assert "https://api.openai.com/v1" in message


def test_pass_grandfathered_base_url_site() -> None:
    # regression: an existing存量 bypass site is grandfathered and must NOT fail.
    code = '            base_url="https://api.deepseek.com",\n'
    usages = collect_base_url_usages([("deeptutor/capabilities/deep_question.py", code)])
    ok, message = evaluate_provider_usages(usages, [], load_provider_registry())
    assert ok is True
    assert "passed" in message


def test_pass_full_path_endpoint_grandfathered_site() -> None:
    # a full-path endpoint (base_url + /embeddings) at a grandfathered site passes.
    code = '"https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",\n'
    usages = collect_base_url_usages([("deeptutor/services/rag/pipelines/kbv5.py", code)])
    ok, _ = evaluate_provider_usages(usages, [], load_provider_registry())
    assert ok is True


def test_pass_canonical_registry_is_the_one_place_base_urls_live() -> None:
    registry = load_provider_registry()
    canonical = registry["canonical_module"]
    code = '    default_api_base="https://api.deepseek.com",\n'
    usages = collect_base_url_usages([(canonical, code)])
    ok, _ = evaluate_provider_usages(usages, [], registry)
    assert ok is True


def test_pass_provider_registry_yaml_itself_not_flagged() -> None:
    # The registry YAML literally contains every base_url — it is the source,
    # never a bypass. (Scanner only scopes deeptutor/ + scripts/ .py anyway.)
    code = 'canonical_base_url: "https://api.deepseek.com"\n'
    ok, _ = evaluate_provider_registry(["contracts/provider_registry.yaml"])
    assert ok is True


# ── FAIL RULE (b): a NEW provider added to a DEPRECATED registry copy ────────
def test_fail_new_provider_added_to_deprecated_copy() -> None:
    # min repro: someone adds a brand-new ProviderSpec to the deprecated tutorbot
    # copy — re-growing a second authority. The provider name is not yet in the
    # canonical registry, so it is a NEW provider in a deprecated source.
    code = (
        "PROVIDERS = (\n"
        '    ProviderSpec(name="brandnewprovider", '
        'default_api_base="https://api.brandnew.example/v1"),\n'
        ")\n"
    )
    specs = collect_provider_spec_usages([("deeptutor/tutorbot/providers/registry.py", code)])
    ok, message = evaluate_provider_usages([], specs, load_provider_registry())
    assert ok is False
    assert "deprecated" in message.lower()
    assert "brandnewprovider" in message


def test_pass_existing_provider_in_deprecated_copy_not_flagged() -> None:
    # regression: the deprecated copy still physically lists existing providers
    # (deepseek, openai, …) — those are registered in canonical, so editing the
    # copy's existing entries must NOT fail. Only a NEW (unregistered) provider does.
    code = (
        "PROVIDERS = (\n"
        '    ProviderSpec(name="deepseek", default_api_base="https://api.deepseek.com"),\n'
        '    ProviderSpec(name="openai", default_api_base="https://api.openai.com/v1"),\n'
        ")\n"
    )
    specs = collect_provider_spec_usages([("deeptutor/tutorbot/providers/registry.py", code)])
    ok, message = evaluate_provider_usages([], specs, load_provider_registry())
    assert ok is True, message
    assert "passed" in message


def test_pass_new_provider_in_canonical_is_allowed() -> None:
    # Adding a provider to the CANONICAL registry is the sanctioned way to add a
    # provider; it must NOT fail (the spec usage is in the canonical module).
    registry = load_provider_registry()
    canonical = registry["canonical_module"]
    code = (
        '    ProviderSpec(name="brandnewprovider", '
        'default_api_base="https://api.brandnew.example/v1"),\n'
    )
    specs = collect_provider_spec_usages([(canonical, code)])
    ok, _ = evaluate_provider_usages([], specs, registry)
    assert ok is True


# ── SCOPE CARVE-OUTS: out-of-scope must not be flagged (no false positives) ──
def test_tests_dir_out_of_scope_via_changed_files_entry() -> None:
    # The changed-files entry point ignores tests/ and non-deeptutor/scripts paths,
    # so a hardcoded base_url inside a test file is never flagged.
    ok, message = evaluate_provider_registry(
        ["tests/services/test_new_thing.py", "docs/plan/whatever.md"]
    )
    assert ok is True
    assert "no in-scope production source changed" in message


def test_comment_lines_not_flagged() -> None:
    # A commented-out hardcoded base_url must not trip the guard.
    code = '# base_url="https://api.shadowprovider.example/v1"\n'
    usages = collect_base_url_usages([("deeptutor/services/x.py", code)])
    ok, _ = evaluate_provider_usages(usages, [], load_provider_registry())
    assert ok is True


def test_non_provider_url_not_flagged() -> None:
    # A non-provider URL (docs link, webhook, asset CDN) is not a governed
    # base_url literal — only known provider api hostnames are governed.
    code = 'DOCS = "https://example.com/docs"\nwebhook = "https://hooks.slack.com/x"\n'
    usages = collect_base_url_usages([("deeptutor/services/x.py", code)])
    ok, _ = evaluate_provider_usages(usages, [], load_provider_registry())
    assert ok is True


def test_provider_spec_in_non_registry_file_not_flagged() -> None:
    # ProviderSpec(...) usage outside the canonical + deprecated registry files is
    # not a "second registry" signal (e.g. a test factory building a spec inline).
    code = 'spec = ProviderSpec(name="whatever", default_api_base="")\n'
    specs = collect_provider_spec_usages([("deeptutor/services/x.py", code)])
    ok, _ = evaluate_provider_usages([], specs, load_provider_registry())
    assert ok is True
