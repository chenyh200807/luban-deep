"""Tests for the one-shot model_catalog plaintext-key purge script.

The behaviour that matters most is the REFUSAL: the script must never redact a
key the environment cannot supply, because the catalog file is then the last
copy and redacting it would leave the key nowhere.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.purge_model_catalog_plaintext_keys import (  # noqa: E402
    REDACTED_SECRET,
    main,
    plan_purge,
)

_KEY = "sk-live-catalog-key-123456"


def _patch_env(monkeypatch, values: dict) -> None:
    """Pin the script's view of the environment.

    Necessary rather than fussy: `_env_values()` goes through EnvStore, which
    reads the real `.env` from disk and lets that file win over os.environ. A
    plain monkeypatch.setenv would therefore be silently overridden by the
    developer's actual key.
    """

    monkeypatch.setattr(
        "scripts.purge_model_catalog_plaintext_keys._env_values", lambda: dict(values)
    )


def _catalog(api_key: str = _KEY, profile_id: str = "llm-profile-default") -> dict:
    return {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": profile_id,
                "active_model_id": "llm-model-default",
                "profiles": [
                    {
                        "id": profile_id,
                        "name": "Default LLM Endpoint",
                        "binding": "openai",
                        "base_url": "https://api.example.test",
                        "api_key": api_key,
                        "models": [{"id": "llm-model-default", "name": "m", "model": "m"}],
                    }
                ],
            },
            "embedding": {"active_profile_id": None, "active_model_id": None, "profiles": []},
            "search": {"active_profile_id": None, "profiles": []},
        },
    }


def _write(path: Path, catalog: dict, mode: int = 0o777) -> Path:
    path.write_text(json.dumps(catalog), encoding="utf-8")
    path.chmod(mode)
    return path


def test_plan_marks_key_recoverable_when_env_matches() -> None:
    recoverable, unrecoverable = plan_purge(_catalog(), {"LLM_API_KEY": _KEY})

    assert [r[0] for r in recoverable] == ["llm"]
    assert unrecoverable == []


def test_plan_marks_key_unrecoverable_when_env_absent() -> None:
    recoverable, unrecoverable = plan_purge(_catalog(), {})

    assert recoverable == []
    assert [u[0] for u in unrecoverable] == ["llm"]


def test_plan_marks_key_unrecoverable_when_env_value_differs() -> None:
    """A different env value is NOT a safe substitute — it is a different key."""

    recoverable, unrecoverable = plan_purge(_catalog(), {"LLM_API_KEY": "sk-some-other-key-99"})

    assert recoverable == []
    assert [u[0] for u in unrecoverable] == ["llm"]


def test_non_active_profile_is_never_treated_as_recoverable() -> None:
    """Only the active profile is re-hydrated from env on load."""

    catalog = _catalog(profile_id="secondary-profile")
    catalog["services"]["llm"]["active_profile_id"] = "llm-profile-default"

    recoverable, unrecoverable = plan_purge(catalog, {"LLM_API_KEY": _KEY})

    assert recoverable == []
    assert [u[1] for u in unrecoverable] == ["secondary-profile"]


def test_dry_run_is_the_default_and_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    _patch_env(monkeypatch, {"LLM_API_KEY": _KEY})
    path = _write(tmp_path / "model_catalog.json", _catalog())
    before = path.read_text(encoding="utf-8")

    assert main(["--path", str(path)]) == 0
    assert path.read_text(encoding="utf-8") == before
    assert _KEY in path.read_text(encoding="utf-8")


def test_apply_redacts_recoverable_key_and_tightens_mode(tmp_path: Path, monkeypatch) -> None:
    _patch_env(monkeypatch, {"LLM_API_KEY": _KEY})
    path = _write(tmp_path / "model_catalog.json", _catalog())

    assert main(["--path", str(path), "--apply"]) == 0

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["services"]["llm"]["profiles"][0]["api_key"] == REDACTED_SECRET
    assert _KEY not in path.read_text(encoding="utf-8")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_apply_takes_a_backup_with_owner_only_mode(tmp_path: Path, monkeypatch) -> None:
    _patch_env(monkeypatch, {"LLM_API_KEY": _KEY})
    path = _write(tmp_path / "model_catalog.json", _catalog())

    main(["--path", str(path), "--apply"])

    backups = list(tmp_path.glob("model_catalog.json.bak.*"))
    assert len(backups) == 1
    assert _KEY in backups[0].read_text(encoding="utf-8")
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600


def test_refuses_to_destroy_an_unrecoverable_key(tmp_path: Path, monkeypatch) -> None:
    """The core safety property: never create a 'key exists nowhere' state."""

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(
        "scripts.purge_model_catalog_plaintext_keys._env_values", lambda: {}
    )
    path = _write(tmp_path / "model_catalog.json", _catalog())

    assert main(["--path", str(path), "--apply"]) == 2
    # File untouched — key still present, nothing lost.
    assert _KEY in path.read_text(encoding="utf-8")
    assert list(tmp_path.glob("*.bak.*")) == []


def test_force_overrides_the_refusal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.purge_model_catalog_plaintext_keys._env_values", lambda: {}
    )
    path = _write(tmp_path / "model_catalog.json", _catalog())

    assert main(["--path", str(path), "--apply", "--force"]) == 0
    assert _KEY not in path.read_text(encoding="utf-8")


def test_already_clean_catalog_is_a_noop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.purge_model_catalog_plaintext_keys._env_values", lambda: {}
    )
    path = _write(tmp_path / "model_catalog.json", _catalog(api_key=REDACTED_SECRET), mode=0o777)

    assert main(["--path", str(path), "--apply"]) == 0
    # Clean file still gets its permissions tightened.
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_missing_file_is_a_noop(tmp_path: Path) -> None:
    assert main(["--path", str(tmp_path / "nope.json")]) == 0


def test_script_never_prints_a_full_key(tmp_path: Path, monkeypatch, capsys) -> None:
    """Reporting discipline: prefix + length only, never the value."""

    _patch_env(monkeypatch, {"LLM_API_KEY": _KEY})
    path = _write(tmp_path / "model_catalog.json", _catalog())

    main(["--path", str(path)])

    out = capsys.readouterr().out
    assert _KEY not in out
    assert "sk-l… (len=26)" in out


@pytest.mark.parametrize("mode", [0o777, 0o644, 0o600])
def test_apply_always_lands_on_0600(tmp_path: Path, monkeypatch, mode: int) -> None:
    _patch_env(monkeypatch, {"LLM_API_KEY": _KEY})
    path = _write(tmp_path / "model_catalog.json", _catalog(), mode=mode)

    main(["--path", str(path), "--apply"])

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
