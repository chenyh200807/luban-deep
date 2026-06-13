"""TDD for scripts/check_env_registry.py — the env/flag/credential policy gate.

The guard turns the RESOURCE_GOVERNANCE_FIX_PLAN root-cause business fact —
"每个共享资源在被使用前，必须能被机器确认它登记在唯一 canonical 清单里" — into a
real CI gate for the env/flag/credential class. It scans changed code and fails
on TWO conditions (Layer 2 · P1, §5 env/flag + §3 凭据):

  (a) UNREGISTERED ENV REFERENCE — production code references an env name via
      os.getenv / os.environ / env_store.get / env_flag that the registry does
      not list. This is the止血 (stop-the-bleed) rule against NEW bare env.

  (b) UNREGISTERED BARE FEATURE FLAG — code reads a name through env_flag(...)
      (the machine signal "this is a boolean gate") that the registry does not
      list as a feature_flag. A misspelled flag silently returns env_flag's
      default → 假灰度 (a rollout that looks live but isn't). This rule is the
      sharp edge: it protects KB v5 / LUBAN_V1 gray-release correctness.

Existing存量 references are grandfathered (registered with grandfathered: true),
so the gate stops NEW drift without forcing a one-shot cleanup of the 245
already-bare env names.

These tests run on synthetic code snippets (no live import of scanned modules),
so they are deterministic and touch no parallel WIP source files.
"""

from __future__ import annotations

from scripts.check_env_registry import (
    collect_env_reference_usages,
    collect_feature_flag_usages,
    evaluate_env_registry,
    evaluate_env_usages,
    load_env_registry,
)


# ── Registry loads and exposes the single canonical list ─────────────────────
def test_registry_loads_envs_flags_and_grandfathered() -> None:
    registry = load_env_registry()
    # canonical envs are indexed
    assert "DATABASE_URL" in registry["registered_envs"]
    assert "DEEPSEEK_API_KEY" in registry["registered_envs"]
    # feature flags are a distinct indexed set (the env_flag() universe)
    assert "KBV5_RAG_ENABLED" in registry["registered_flags"]
    assert "LUBAN_V1_CONTROLLED_RUNTIME_ENABLED" in registry["registered_flags"]
    # a flag is also a registered env (so rule (a) never double-fires on it)
    assert "KBV5_RAG_ENABLED" in registry["registered_envs"]
    # secret-kind credentials are in the same registry (not a separate store)
    assert "DEEPTUTOR_AUTH_SECRET" in registry["registered_envs"]
    # aliases resolve (WECHAT_MP_APPSECRET is an alias of the canonical name)
    assert "WECHAT_MP_APPSECRET" in registry["registered_envs"]


# ── FAIL RULE (a): unregistered env reference (止血 — new bare env) ───────────
def test_fail_new_unregistered_env_reference() -> None:
    # min repro: a brand-new production file reads a never-registered env.
    code = "url = os.getenv('SHADOW_TOTALLY_NEW_SETTING')\n"
    envs = collect_env_reference_usages([("deeptutor/services/new_thing.py", code)])
    ok, message = evaluate_env_usages(envs, [], load_env_registry())
    assert ok is False
    assert "unregistered env" in message
    assert "SHADOW_TOTALLY_NEW_SETTING" in message


def test_pass_registered_env_reference() -> None:
    # regression: a registered env reference must NOT be flagged.
    code = "url = os.getenv('DATABASE_URL')\nkey = os.environ['DEEPSEEK_API_KEY']\n"
    envs = collect_env_reference_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_env_usages(envs, [], load_env_registry())
    assert ok is True
    assert "passed" in message


def test_pass_env_store_get_literal_reference() -> None:
    # env_store.get("X") is one of the read entry points and must resolve too.
    code = 'binding = env_store.get("LLM_BINDING", "deepseek")\n'
    envs = collect_env_reference_usages([("deeptutor/services/x.py", code)])
    ok, _ = evaluate_env_usages(envs, [], load_env_registry())
    assert ok is True


def test_pass_alias_env_reference() -> None:
    # the no-underscore WeChat form is a registered alias, not drift.
    code = 'secret = os.getenv("WECHAT_MP_APPSECRET")\n'
    envs = collect_env_reference_usages([("deeptutor/services/member_console/service.py", code)])
    ok, _ = evaluate_env_usages(envs, [], load_env_registry())
    assert ok is True


# ── FAIL RULE (b): unregistered bare feature flag (防假灰度) ──────────────────
def test_fail_new_bare_feature_flag() -> None:
    # min repro: a new env_flag() read whose name no one registered as a flag.
    # A typo here silently returns the default → 假灰度.
    code = "if env_flag('LUBAN_V2_SHADOW_ENABLEDD'):\n    do_thing()\n"
    flags = collect_feature_flag_usages([("deeptutor/services/x.py", code)])
    # the same line is also an env reference; both collectors see it.
    envs = collect_env_reference_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_env_usages(envs, flags, load_env_registry())
    assert ok is False
    assert "feature flag" in message
    assert "LUBAN_V2_SHADOW_ENABLEDD" in message


def test_pass_registered_feature_flag() -> None:
    # regression: a registered flag passes (and does NOT also fail rule (a)).
    code = "if env_flag('KBV5_RAG_ENABLED'):\n    route_kbv5()\n"
    flags = collect_feature_flag_usages([("deeptutor/services/x.py", code)])
    envs = collect_env_reference_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_env_usages(envs, flags, load_env_registry())
    assert ok is True
    assert "passed" in message


def test_env_flag_read_classifies_as_flag_even_without_enabled_suffix() -> None:
    # The machine signal is "read through env_flag()", NOT the name suffix.
    # MEMBER_CONSOLE_USE_REAL_SMS has no _ENABLED suffix but is a real flag —
    # a typo of it must still fail rule (b).
    code = "if env_flag('MEMBER_CONSOLE_USE_REAL_SMSS'):\n    send()\n"
    flags = collect_feature_flag_usages([("deeptutor/services/x.py", code)])
    envs = collect_env_reference_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_env_usages(envs, flags, load_env_registry())
    assert ok is False
    assert "MEMBER_CONSOLE_USE_REAL_SMSS" in message


# ── SCOPE CARVE-OUTS: out-of-scope must not be flagged (no false positives) ──
def test_tests_dir_out_of_scope_via_changed_files_entry() -> None:
    # The changed-files entry point ignores tests/ and non-deeptutor/scripts.
    ok, message = evaluate_env_registry(
        ["tests/services/test_new_thing.py", "docs/plan/whatever.md"]
    )
    assert ok is True
    assert "no in-scope" in message


def test_comment_lines_not_flagged() -> None:
    # A commented-out env / flag read must not trip the guard.
    code = "# url = os.getenv('SHADOW_NEW_THING')\n# env_flag('FAKE_FLAG')\n"
    envs = collect_env_reference_usages([("deeptutor/services/x.py", code)])
    flags = collect_feature_flag_usages([("deeptutor/services/x.py", code)])
    ok, _ = evaluate_env_usages(envs, flags, load_env_registry())
    assert ok is True


def test_lowercase_or_local_variable_not_mistaken_for_env() -> None:
    # os.getenv with a non-UPPER name (or a dynamic var) is not an env literal
    # we govern; only ALL-CAPS string literals are env names.
    code = "v = os.getenv(some_dynamic_key)\nx = os.getenv('lower_case')\n"
    envs = collect_env_reference_usages([("deeptutor/services/x.py", code)])
    ok, _ = evaluate_env_usages(envs, [], load_env_registry())
    assert ok is True


def test_full_repo_scan_has_zero_false_positives() -> None:
    """The whole-repo scan over real production source must be GREEN.

    This is the load-bearing acceptance test (mirrors the DB guard's CI step):
    every env/flag currently referenced in deeptutor/ + scripts/ is grandfathered
    in the registry, so a clean tree exits 0. A failure here means either a real
    new bare env slipped in, or the registry under-covers存量 — both must be fixed
    before merge (the gate's promise is zero false positives on the current tree).
    """
    import subprocess

    from scripts.check_env_registry import REPO_ROOT

    tracked = subprocess.run(
        ["git", "ls-files", "deeptutor/**/*.py", "scripts/**/*.py"],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    ).stdout.split()
    ok, message = evaluate_env_registry(tracked)
    assert ok is True, message

