"""G3 — canonical registry publish flow (master plan §0.26 / M33-ACT).

``publish_canonical_registry`` promotes a SIGNED release_candidate canonical manifest to
``status=published``. It is a triple fail-closed gate: env flag (default OFF) + explicit caller
authorization (strict ``is True``) + a PASS/TRUSTED release-gate report, then fail-closed manifest
verification AND per-shard content re-verification before any signing. Nothing is published unless ALL
gates hold; otherwise the manifest stays release_candidate.

Shards here are SELF-CONSISTENT (content_hash = sha256(records), signature over hash|namespace|status)
so the deep per-shard verification (verify_lane_bundle) passes for a clean bundle and rejects a
records-tampered one.
"""
from __future__ import annotations

import json

from deeptutor.services.construction_grading import canonical_knowledge_manifest as M
from deeptutor.services.construction_grading import full_knowledge_compiler as _FKC
from deeptutor.services.observability.release_gate import (
    PUBLISH_ENABLED_FLAG,
    publish_canonical_registry,
)

_PASS_REPORT = {"final_status": "PASS", "verdict": "TRUSTED"}


def _shard(d, name, records=None):
    recs = list(range(3)) if records is None else records
    sub = d / name
    sub.mkdir()
    ch = _FKC._sha256_hex(recs)
    sig = _FKC._sha256_hex([ch, name, "release_candidate"])
    (sub / "bundle.json").write_text(
        json.dumps(
            {
                "manifest": {
                    "namespace": name,
                    "content_hash": ch,
                    "status": "release_candidate",
                    "signature": sig,
                },
                "records": recs,
            }
        ),
        "utf-8",
    )
    return {
        "lane": name,
        "path": f"{name}/bundle.json",
        "namespace": name,
        "content_hash": ch,
        "record_count": len(recs),
        "tier": "answer_authority",
    }


def _manifest(tmp_path):
    s1 = _shard(tmp_path, "objective_answer_key")
    return M.build_manifest(
        [s1], M.source_inventory([]), version="v2", producer="test", rollback_pointer="v1"
    )


def test_publish_disabled_by_default(tmp_path):
    """Default: env flag OFF -> refusal, manifest stays release_candidate."""
    man = _manifest(tmp_path)
    out = publish_canonical_registry(
        man, tmp_path, release_gate_report=_PASS_REPORT, authorized=True, published_at="t"
    )
    assert out["published"] is False and out["reason"] == "publish_disabled"
    assert out["manifest"]["status"] == "release_candidate"


def test_publish_requires_explicit_authorization(tmp_path, monkeypatch):
    """Flag on but authorized=False -> refusal."""
    monkeypatch.setenv(PUBLISH_ENABLED_FLAG, "true")
    man = _manifest(tmp_path)
    out = publish_canonical_registry(
        man, tmp_path, release_gate_report=_PASS_REPORT, authorized=False, published_at="t"
    )
    assert out["published"] is False and out["reason"] == "not_authorized"


def test_publish_rejects_truthy_non_bool_authorization(tmp_path, monkeypatch):
    """Strict: a truthy non-bool (int 1 / non-empty str) must NOT authorize — only literal True does.

    These are exactly the values a naive ``if authorized:`` check would let through; ``is not True``
    rejects them. Regression-locks the strict identity guard.
    """
    monkeypatch.setenv(PUBLISH_ENABLED_FLAG, "true")
    man = _manifest(tmp_path)
    for bad_auth in (1, "true", "false", [1]):
        out = publish_canonical_registry(
            man, tmp_path, release_gate_report=_PASS_REPORT, authorized=bad_auth, published_at="t"
        )
        assert out["published"] is False and out["reason"] == "not_authorized"


def test_publish_rejects_zero_shard_manifest(tmp_path, monkeypatch):
    """An empty manifest (no shards) is not a publishable authority -> refusal."""
    monkeypatch.setenv(PUBLISH_ENABLED_FLAG, "true")
    empty = M.build_manifest(
        [], M.source_inventory([]), version="v2", producer="test", rollback_pointer="v1"
    )
    out = publish_canonical_registry(
        empty, tmp_path, release_gate_report=_PASS_REPORT, authorized=True, published_at="t"
    )
    assert out["published"] is False and out["reason"] == "manifest_has_no_shards"


def test_publish_rejects_none_supply_root(tmp_path, monkeypatch):
    """A None supply_root yields a structured refusal, not an uncaught Path(None) TypeError."""
    monkeypatch.setenv(PUBLISH_ENABLED_FLAG, "true")
    man = _manifest(tmp_path)
    out = publish_canonical_registry(
        man, None, release_gate_report=_PASS_REPORT, authorized=True, published_at="t"
    )
    assert out["published"] is False and out["reason"] == "supply_root_missing"


def test_publish_requires_release_gate_pass(tmp_path, monkeypatch):
    """A non-PASS release gate blocks publishing."""
    monkeypatch.setenv(PUBLISH_ENABLED_FLAG, "true")
    man = _manifest(tmp_path)
    out = publish_canonical_registry(
        man,
        tmp_path,
        release_gate_report={"final_status": "WARN", "verdict": "TRUSTED"},
        authorized=True,
        published_at="t",
    )
    assert out["published"] is False and out["reason"] == "release_gate_not_pass"


def test_publish_rejects_stale_release_gate(tmp_path, monkeypatch):
    """A stale (artifacts-vs-HEAD) release gate blocks publishing even at PASS."""
    monkeypatch.setenv(PUBLISH_ENABLED_FLAG, "true")
    man = _manifest(tmp_path)
    out = publish_canonical_registry(
        man,
        tmp_path,
        release_gate_report={"final_status": "PASS", "verdict": "STALE"},
        authorized=True,
        published_at="t",
    )
    assert out["published"] is False and out["reason"] == "release_gate_stale"


def test_publish_fail_closed_on_pinned_hash_tamper(tmp_path, monkeypatch):
    """Fail-closed (manifest layer): a shard whose self-reported hash drifts from the pin is rejected."""
    monkeypatch.setenv(PUBLISH_ENABLED_FLAG, "true")
    man = _manifest(tmp_path)
    p = tmp_path / "objective_answer_key" / "bundle.json"
    b = json.loads(p.read_text("utf-8"))
    b["manifest"]["content_hash"] = "TAMPERED"
    p.write_text(json.dumps(b), "utf-8")
    out = publish_canonical_registry(
        man, tmp_path, release_gate_report=_PASS_REPORT, authorized=True, published_at="t"
    )
    assert out["published"] is False and "manifest_verify_failed" in out["reason"]


def test_publish_fail_closed_on_records_tamper(tmp_path, monkeypatch):
    """Fail-closed (content layer): records tampered while keeping the self-reported hash -> rejected.

    This is the real-tamper case the manifest-pin check alone would miss; deep per-shard verification
    (verify_lane_bundle recomputes the records hash) catches it.
    """
    monkeypatch.setenv(PUBLISH_ENABLED_FLAG, "true")
    man = _manifest(tmp_path)
    p = tmp_path / "objective_answer_key" / "bundle.json"
    b = json.loads(p.read_text("utf-8"))
    b["records"] = [9, 9, 9]  # content changed; self-reported content_hash left intact
    p.write_text(json.dumps(b), "utf-8")
    out = publish_canonical_registry(
        man, tmp_path, release_gate_report=_PASS_REPORT, authorized=True, published_at="t"
    )
    assert out["published"] is False and "shard_content_tamper" in out["reason"]


def test_publish_signs_when_fully_authorized(tmp_path, monkeypatch):
    """All gates hold -> published manifest signed; content_hash unchanged; still verifies."""
    monkeypatch.setenv(PUBLISH_ENABLED_FLAG, "true")
    man = _manifest(tmp_path)
    out = publish_canonical_registry(
        man,
        tmp_path,
        release_gate_report=_PASS_REPORT,
        authorized=True,
        published_at="2026-06-08T00:00:00+08:00",
        superseded_version="v_prev",
    )
    assert out["published"] is True and out["reason"] == "ok"
    pub = out["manifest"]
    assert pub["status"] == "published" and pub["published"] is True
    assert pub["content_hash"] == man["content_hash"]
    assert out["superseded_version"] == "v_prev"
    assert out["rollback_pointer"] == "v1"
    ok, reason = M.verify_manifest(pub, tmp_path)
    assert ok is True and reason == "ok"
