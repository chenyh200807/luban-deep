from __future__ import annotations

import json

import pytest

from deeptutor.services.member_console.admin_store import (
    load_admins,
    load_audit,
    remove_admin,
    set_admin,
    set_role_permissions,
    set_user_overrides,
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


# ---- P2 防御纵深：审计 append-only ----

def test_audit_written_to_separate_append_only_file(tmp_path):
    """审计写入独立 bi_admin_audit.jsonl；bi_admins.json 内不再累积新审计。"""
    p = tmp_path / "bi_admins.json"
    set_admin(p, "u-a", role="admin", actor="super", granted_at="t1")
    audit_file = tmp_path / "bi_admin_audit.jsonl"
    assert audit_file.exists()
    lines = [ln for ln in audit_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    main = json.loads(p.read_text(encoding="utf-8"))
    assert main.get("audit") == []


def test_role_permissions_and_user_overrides_keep_audit_append_only(tmp_path):
    p = tmp_path / "bi_admins.json"
    set_admin(p, "u-a", role="admin", actor="super", granted_at="t1")
    set_role_permissions(
        p,
        "admin",
        {"commerce": ["view"]},
        actor="super",
        at="t2",
    )
    set_user_overrides(
        p,
        "u-a",
        {"commerce": ["view", "write"]},
        actor="super",
        at="t3",
    )

    main = json.loads(p.read_text(encoding="utf-8"))
    assert main.get("audit") == []
    assert main["role_permissions"]["admin"] == {"commerce": ["view"]}
    assert main["admins"]["u-a"]["permission_overrides"] == {"commerce": ["view", "write"]}
    assert [entry["action"] for entry in load_audit(p)] == [
        "add_admin",
        "set_role_permissions",
        "set_user_overrides",
    ]


def test_audit_is_append_only_not_truncated(tmp_path):
    """append-only：写入远超旧 _AUDIT_MAX(1000) 后最早审计仍在，杜绝被刷掉。"""
    from deeptutor.services.member_console.admin_store import _append_audit

    p = tmp_path / "bi_admins.json"
    for i in range(1100):
        _append_audit(p, {"ts": f"t{i}", "actor": "super", "action": "set_role", "target": f"u{i}"})
    audit = load_audit(p)
    assert len(audit) == 1100
    assert audit[0]["target"] == "u0"
    assert audit[-1]["target"] == "u1099"


def test_load_audit_merges_legacy_embedded(tmp_path):
    """向后兼容：bi_admins.json 内 legacy audit 与新 append-only 文件合并读取（旧→新）。"""
    p = tmp_path / "bi_admins.json"
    p.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "admins": {},
                "audit": [{"ts": "old", "action": "legacy_event"}],
                "role_permissions": {},
            }
        ),
        encoding="utf-8",
    )
    set_admin(p, "u-a", role="admin", actor="super", granted_at="new")
    audit = load_audit(p)
    assert audit[0]["ts"] == "old"
    assert audit[-1]["action"] == "add_admin"
