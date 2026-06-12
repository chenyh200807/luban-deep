from __future__ import annotations

import pytest

from deeptutor.services.member_console.service import get_member_console_service


@pytest.fixture
def svc(tmp_path, monkeypatch):
    service = get_member_console_service()
    monkeypatch.setattr(service, "_bi_admins_path", lambda: tmp_path / "bi_admins.json")
    monkeypatch.setattr(service, "_env_admin_user_ids", lambda: {"env-super"})
    return service


def test_env_admin_is_admin_and_not_removable(svc):
    assert svc.is_admin_user("env-super") is True
    listing = svc.list_admin_user_ids()
    env_entry = next(e for e in listing if e["user_id"] == "env-super")
    assert env_entry["source"] == "env"
    assert env_entry["removable"] is False


def test_add_runtime_admin_takes_effect_without_restart(svc):
    assert svc.is_admin_user("u-new") is False
    svc.add_admin_user("u-new")
    assert svc.is_admin_user("u-new") is True
    entry = next(e for e in svc.list_admin_user_ids() if e["user_id"] == "u-new")
    assert entry["source"] == "runtime"
    assert entry["removable"] is True


def test_remove_runtime_admin(svc):
    svc.add_admin_user("u-temp")
    svc.remove_admin_user("u-temp")
    assert svc.is_admin_user("u-temp") is False


def test_cannot_remove_env_admin(svc):
    with pytest.raises(ValueError):
        svc.remove_admin_user("env-super")
    assert svc.is_admin_user("env-super") is True


def test_add_blank_rejected(svc):
    with pytest.raises(ValueError):
        svc.add_admin_user("  ")
