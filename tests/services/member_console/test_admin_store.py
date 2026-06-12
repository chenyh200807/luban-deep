from __future__ import annotations

import pytest

from deeptutor.services.member_console.admin_store import (
    add_persisted_admin,
    load_persisted_admins,
    remove_persisted_admin,
)


def test_load_empty_when_file_missing(tmp_path):
    assert load_persisted_admins(tmp_path / "bi_admins.json") == set()


def test_add_then_load_roundtrip(tmp_path):
    p = tmp_path / "bi_admins.json"
    add_persisted_admin(p, "u-alice")
    add_persisted_admin(p, "u-bob")
    assert load_persisted_admins(p) == {"u-alice", "u-bob"}


def test_add_is_idempotent(tmp_path):
    p = tmp_path / "bi_admins.json"
    add_persisted_admin(p, "u-alice")
    add_persisted_admin(p, "u-alice")
    assert load_persisted_admins(p) == {"u-alice"}


def test_add_rejects_blank(tmp_path):
    with pytest.raises(ValueError):
        add_persisted_admin(tmp_path / "bi_admins.json", "   ")


def test_remove(tmp_path):
    p = tmp_path / "bi_admins.json"
    add_persisted_admin(p, "u-alice")
    add_persisted_admin(p, "u-bob")
    remove_persisted_admin(p, "u-alice")
    assert load_persisted_admins(p) == {"u-bob"}


def test_remove_missing_is_noop(tmp_path):
    p = tmp_path / "bi_admins.json"
    add_persisted_admin(p, "u-alice")
    remove_persisted_admin(p, "u-ghost")
    assert load_persisted_admins(p) == {"u-alice"}


def test_corrupt_file_treated_as_empty(tmp_path):
    p = tmp_path / "bi_admins.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert load_persisted_admins(p) == set()
