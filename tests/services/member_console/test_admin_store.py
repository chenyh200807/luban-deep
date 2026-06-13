from __future__ import annotations

import json

import pytest

from deeptutor.services.member_console.admin_store import (
    load_admins,
    load_audit,
    remove_admin,
    set_admin,
)


def test_load_empty_when_file_missing(tmp_path):
    assert load_admins(tmp_path / "bi_admins.json") == {}


def test_set_admin_with_role_and_audit(tmp_path):
    p = tmp_path / "bi_admins.json"
    set_admin(p, "u-alice", role="admin", display_name="Alice", actor="super", granted_at="t1")
    admins = load_admins(p)
    assert admins["u-alice"]["role"] == "admin"
    assert admins["u-alice"]["display_name"] == "Alice"
    audit = load_audit(p)
    assert audit[-1]["action"] == "add_admin"
    assert audit[-1]["to_role"] == "admin"
    assert audit[-1]["actor"] == "super"


def test_set_admin_change_role_records_from_to(tmp_path):
    p = tmp_path / "bi_admins.json"
    set_admin(p, "u-bob", role="analyst", actor="super", granted_at="t1")
    set_admin(p, "u-bob", role="operator", actor="super", granted_at="t2")
    assert load_admins(p)["u-bob"]["role"] == "operator"
    last = load_audit(p)[-1]
    assert last["action"] == "set_role"
    assert last["from_role"] == "analyst"
    assert last["to_role"] == "operator"


def test_set_admin_rejects_blank(tmp_path):
    with pytest.raises(ValueError):
        set_admin(tmp_path / "bi_admins.json", "  ", role="admin")


def test_remove_admin(tmp_path):
    p = tmp_path / "bi_admins.json"
    set_admin(p, "u-alice", role="admin")
    set_admin(p, "u-bob", role="analyst")
    remove_admin(p, "u-alice", actor="super", removed_at="t3")
    assert set(load_admins(p)) == {"u-bob"}
    assert load_audit(p)[-1]["action"] == "remove_admin"
    assert load_audit(p)[-1]["target"] == "u-alice"


def test_v1_format_migrates_to_role_admin(tmp_path):
    """旧 {user_ids:[...]} 读取时迁移为 role=admin。"""
    p = tmp_path / "bi_admins.json"
    p.write_text(json.dumps({"user_ids": ["u-legacy1", "u-legacy2"]}), encoding="utf-8")
    admins = load_admins(p)
    assert admins["u-legacy1"]["role"] == "admin"
    assert admins["u-legacy2"]["granted_by"] == "migrated_from_v1"


def test_corrupt_file_treated_as_empty(tmp_path):
    p = tmp_path / "bi_admins.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert load_admins(p) == {}
