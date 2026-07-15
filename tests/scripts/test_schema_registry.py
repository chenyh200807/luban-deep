"""TDD for scripts/check_schema_registry.py — the grading-schema policy gate.

The guard turns the AGENTS.md §5.7 documentary single-authority hard gate into a
real CI gate: it scans changed code for grading-schema usage and fails when a
schema is unregistered, a deprecated/drift field name is used for a registered
grading concept, or a grading object is missing its single-authority fields.

These tests pin the three fail rules + the pass paths + the scope carve-out.
They run on synthetic code snippets (no live import of the scanned modules), so
they are deterministic and do not touch any parallel WIP source files.
"""

from __future__ import annotations

from scripts.check_schema_registry import (
    SchemaUsage,
    _is_fullset_schema_id,
    _tier3_pattern_matches,
    classify_identifier,
    closure_report,
    collect_all_schema_identifiers,
    collect_schema_usages,
    evaluate_schema_usages,
    load_schema_registry,
)


# ═════════════════════════════════════════════════════════════════════════════
# I1 — schema-marker set covers the bare ``SCHEMA =`` / ``*_SCHEMA =`` forms
# ═════════════════════════════════════════════════════════════════════════════
def test_i1_bare_SCHEMA_marker_triggers_drift_check() -> None:
    # I1 regression: the canonical grading object declared via a bare ``SCHEMA = "…"``
    # (not schema_id/schema_version) was NOT recognized by the marker regex, so the
    # drift/authority checks never fired — a grading object could carry ``weight``
    # instead of ``max_score`` undetected.
    code = (
        'SCHEMA = "luban_grading_object.v1"\n'
        '    point = {"point_id": "p1", "weight": 2.0, "statement": "s"}\n'
    )
    usages = collect_schema_usages([("deeptutor/services/construction_grading/x.py", code)])
    assert usages, "bare SCHEMA= must be recognized as a grading-schema marker (I1)"
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is False
    assert "drift field" in message and "weight" in message


def test_i1_PACK_SCHEMA_and_underscore_SCHEMA_markers_recognized() -> None:
    # I1: the ``*_SCHEMA`` / ``*_SCHEMA_VERSION`` forms (PACK_SCHEMA, GRADING_SCHEMA_VERSION)
    # were missed entirely. They must now collect a usage when the literal is a
    # grading-shaped name.
    for marker in ("PACK_SCHEMA", "GRADING_SCHEMA_VERSION", "TYPED_SCHEMA_ID"):
        code = f'{marker} = "luban_grading_object.v1"\n'
        usages = collect_schema_usages([("deeptutor/services/construction_grading/x.py", code)])
        assert any(u.schema_name == "luban_grading_object.v1" for u in usages), marker


def test_i1_bare_SCHEMA_non_grading_value_still_ignored() -> None:
    # I1 no-false-positive: widening the marker set must NOT pull in unrelated bare
    # ``SCHEMA = "public"`` literals — the grading-name hint filter still gates them.
    code = 'SCHEMA = "public"\nDB_SCHEMA = "compiled_knowledge_registry.v2"\n'
    usages = collect_schema_usages([("deeptutor/services/construction_grading/x.py", code)])
    ok, _ = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is True


# ═════════════════════════════════════════════════════════════════════════════
# I2(a) — grading-named versioned id cannot escape the closure full set
# ═════════════════════════════════════════════════════════════════════════════
def test_i2a_grading_named_id_outside_namespace_allowlist_enters_fullset() -> None:
    # I2(a) regression: a grading-named versioned id whose prefix is NOT on the
    # namespace allow-list (``mygrading_object.v1`` / ``shadow_scoring_point.v2``)
    # previously escaped the full set, so the closure could never flag it an orphan.
    for name in ("mygrading_object.v1", "shadow_scoring_point.v2", "rogue_grading_object.v1"):
        assert _is_fullset_schema_id(name) is True, name


def test_i2a_escaped_grading_id_surfaces_as_orphan_not_silently_dropped() -> None:
    # I2(a) end-to-end: an unregistered grading-named id is an orphan (a real gap),
    # never silently absent from the closure.
    registry = load_schema_registry()
    assert classify_identifier("rogue_grading_object.v1", registry) == "orphan"


# ═════════════════════════════════════════════════════════════════════════════
# I2(b) — tier3 substring swallow: grading-shaped veto + bounded segment match
# ═════════════════════════════════════════════════════════════════════════════
def test_i2b_base_grading_object_with_embedded_tier3_word_is_not_ephemeral() -> None:
    # I2(b) regression: a BASE grading object whose name embeds a tier3 substring
    # (``audit_grading_object.v1`` ⊃ ``_audit``; ``eval_scoring_point.v2`` ⊃ ``_eval``)
    # must NOT be swallowed into T3 — a grading typed object is never ephemeral. It
    # is an orphan (must be registered), not a silent carve-out.
    registry = load_schema_registry()
    assert classify_identifier("audit_grading_object.v1", registry) == "orphan"
    assert classify_identifier("eval_scoring_point.v2", registry) == "orphan"


def test_i2b_dash_namespaced_grading_shaped_id_keeps_orphan_veto() -> None:
    # I2(b) regression for the dash-namespace widening (2026-06-14): once
    # ``_FULLSET_NAMESPACE_RE`` admits ``luban-`` (dash), the grading-shaped one-票否决
    # boundary class must ALSO include '-' — else a DASH grading-shaped id that happens to
    # match a dash carve-out family (``luban-consensus-grading_object.v1`` ⊃ the
    # ``luban-consensus`` T3 family) would be silently swallowed into T3, defeating the veto
    # whose whole job is "a grading typed object is never ephemeral". It must stay an orphan.
    registry = load_schema_registry()
    assert classify_identifier("luban-consensus-grading_object.v1", registry) == "orphan"
    assert classify_identifier("luban-x-scoring_point.v2", registry) == "orphan"


def test_i2b_tier3_pattern_no_midword_substring_swallow() -> None:
    # I2(b): a ``_word`` pattern ending in a letter must match only as a bounded
    # SEGMENT — ``_eval`` matches ``_eval_run`` / ``_eval`` (end) but NOT ``_evaluation``.
    assert _tier3_pattern_matches("_eval", "x_eval_run.v1") is True
    assert _tier3_pattern_matches("_eval", "x_eval") is True
    assert _tier3_pattern_matches("_eval", "x_evaluation_run.v1") is False
    assert _tier3_pattern_matches("_audit", "x_auditor.v1") is False
    assert _tier3_pattern_matches("_gate", "x_gateway.v1") is False


def test_i2b_self_bounded_and_dotted_patterns_keep_substring_semantics() -> None:
    # I2(b) no-false-positive: patterns that already end in a boundary (``_ab_``) or
    # carry a '.' (``_compile.v``, ``grading_artifact.v1``) keep plain-substring match,
    # so existing T3 carve-outs are preserved.
    assert _tier3_pattern_matches("_ab_", "x_ab_results.v1") is True
    assert _tier3_pattern_matches("_ab.", "luban_m35_scoring_artifact_ab.v1") is True
    assert _tier3_pattern_matches("grading_artifact.v1", "question_grading_artifact.v1_beta") is True


# ── Registry loads and exposes the canonical authority ───────────────────────
def test_registry_loads_canonical_and_deprecated() -> None:
    registry = load_schema_registry()
    schemas = registry["by_name"]
    assert schemas["luban_grading_object.v1"]["status"] == "canonical"
    # all 8 pre-existing shapes registered as deprecated with an adapter pointer
    deprecated = [n for n, s in schemas.items() if s["status"] == "deprecated"]
    assert len(deprecated) == 8
    for name in deprecated:
        assert schemas[name].get("adapter")
        assert schemas[name].get("canonical_target") == "luban_grading_object.v1"
    # drift map points each deprecated field at its canonical name
    assert registry["drift_field_map"]["weight"] == "max_score"
    assert registry["drift_field_map"]["canonical_answer"] == "statement"


# ── FAIL RULE (a): unregistered schema name ──────────────────────────────────
def test_fail_unregistered_schema_name() -> None:
    code = 'GRADING_SCHEMA = "luban_freestyle_grading.v9"\n'
    usages = collect_schema_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is False
    assert "unregistered grading schema" in message
    assert "luban_freestyle_grading.v9" in message


def test_pass_registered_canonical_schema_name() -> None:
    code = 'SCHEMA_ID = "luban_grading_object.v1"\n'
    usages = collect_schema_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is True
    assert "passed" in message


def test_grading_named_t3_ephemeral_schema_is_not_flagged_unregistered() -> None:
    # Per-PR guard ↔ closure consistency: a grading-NAMED (not grading-SHAPED) literal that the
    # closure carves out as a T3 ephemeral script/eval artifact (e.g. the eval-result envelope
    # ``luban_student_answer_grading_shadow_eval.v1``) is registered-enough — it is NOT an
    # unregistered rubric. Without this, lifting code that touches such a file false-fails CI.
    registry = load_schema_registry()
    assert classify_identifier("luban_student_answer_grading_shadow_eval.v1", registry) == "tier3"
    code = 'SCHEMA = "luban_student_answer_grading_shadow_eval.v1"\n'
    usages = collect_schema_usages([("scripts/run_luban_student_answer_grading_eval.py", code)])
    ok, message = evaluate_schema_usages(usages, registry)
    assert ok is True, message
    assert "unregistered" not in message


def test_grading_shaped_orphan_still_flagged_despite_t3_recognition() -> None:
    # The T3 recognition above must NOT weaken the rubric gate: a grading-SHAPED object stem
    # (``grading_object`` / ``scoring_point``) is one-票否决 for T3 — it stays an orphan and is
    # still flagged unregistered even though it is grading-named.
    code = 'SCHEMA_ID = "rogue_grading_object.v1"\n'
    usages = collect_schema_usages([("deeptutor/services/x.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is False
    assert "unregistered grading schema" in message


# ── FAIL RULE (b): drift field name for a registered grading concept ─────────
def test_fail_drift_field_name() -> None:
    # `weight` is the deprecated per-point split name; canonical is `max_score`.
    code = (
        "def build():\n"
        '    schema_id = "luban_grading_object.v1"\n'
        '    point = {"point_id": "p1", "weight": 2.0, "statement": "s"}\n'
        "    return point\n"
    )
    usages = collect_schema_usages([("deeptutor/services/grade.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is False
    assert "drift field" in message
    assert "weight" in message
    assert "max_score" in message  # the guard tells you the canonical name


def test_pass_canonical_field_name() -> None:
    code = (
        "def build():\n"
        '    schema_id = "luban_grading_object.v1"\n'
        '    point = {"point_id": "p1", "max_score": 2.0, "statement": "s",\n'
        '             "authority_source": "official_answer", "span_hash": "ab"}\n'
        "    return point\n"
    )
    usages = collect_schema_usages([("deeptutor/services/grade.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is True


# ── FAIL RULE (c): grading object missing authority_source ───────────────────
def test_fail_grading_object_missing_authority_source() -> None:
    # Constructs a v1 grading point with a span_hash but no authority_source.
    code = (
        "def build():\n"
        '    schema_id = "luban_grading_object.v1"\n'
        '    point = {"point_id": "p1", "statement": "s", "span_hash": "ab",\n'
        '             "max_score": None, "hit_status": "hit"}\n'
        "    return point\n"
    )
    usages = collect_schema_usages([("deeptutor/services/grade.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is False
    assert "authority_source" in message


def test_fail_span_backed_point_missing_span_hash() -> None:
    # A span-backed authority (official_answer) point that drops span_hash.
    code = (
        "def build():\n"
        '    schema_id = "luban_grading_object.v1"\n'
        '    point = {"point_id": "p1", "statement": "s",\n'
        '             "authority_source": "official_answer", "max_score": None}\n'
        "    return point\n"
    )
    usages = collect_schema_usages([("deeptutor/services/grade.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is False
    assert "span_hash" in message


# ── PASS: fully compliant canonical object ───────────────────────────────────
def test_pass_compliant_grading_object() -> None:
    code = (
        "def build():\n"
        '    schema_id = "luban_grading_object.v1"\n'
        '    point = {"point_id": "p1", "statement": "s",\n'
        '             "authority_source": "official_answer", "span_hash": "ab",\n'
        '             "max_score": None, "score_authority": "official_answer",\n'
        '             "hit_status": "hit"}\n'
        "    return point\n"
    )
    usages = collect_schema_usages([("deeptutor/services/grade.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is True
    assert "passed" in message


# ── SCOPE: deprecated schema referenced WITH adapter is allowed ──────────────
def test_pass_deprecated_schema_with_adapter_reference() -> None:
    # Reading a deprecated shape and adapting it is legitimate (migration path).
    code = (
        'SOURCE_SCHEMA = "case_grading_artifact.v1"\n'
        "from deeptutor.services.construction_grading.grading_object_adapters import (\n"
        "    map_case_grading_artifact,\n"
        ")\n"
    )
    usages = collect_schema_usages([("deeptutor/services/migrate.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is True


# ── SCOPE CARVE-OUT: ephemeral internal dict is not flagged ──────────────────
def test_scope_ephemeral_internal_dict_not_flagged() -> None:
    # No grading-schema literal -> the dict is out of scope even though it uses a
    # word that happens to be a drift name in another context. The guard only
    # binds drift-field checks to code that declares a registered grading schema.
    code = (
        "def compute():\n"
        '    counters = {"weight": 3, "label": "ui-tab"}  # local UI dict, no schema\n'
        '    return counters["weight"]\n'
    )
    usages = collect_schema_usages([("deeptutor/services/ui.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is True


# ── SCOPE: drift field outside a grading-schema block is not flagged ─────────
def test_scope_drift_name_in_unrelated_schema_block_not_flagged() -> None:
    # A different, non-grading schema literal must not pull drift-field checks in.
    code = (
        "def build():\n"
        '    schema_version = "compiled_knowledge_registry.v2"\n'
        '    row = {"weight": 1.0}  # weight is fine outside a grading object\n'
        "    return row\n"
    )
    usages = collect_schema_usages([("deeptutor/services/kb.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is True


# ── No grading schema touched -> no-op pass ──────────────────────────────────
def test_no_grading_schema_changes_is_pass() -> None:
    usages = collect_schema_usages([("README.md", "# docs only\n")])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is True
    assert "no grading schema" in message


# ── SchemaUsage carries enough context for the report ────────────────────────
def test_schema_usage_shape() -> None:
    code = 'SCHEMA_ID = "luban_grading_object.v1"\n'
    usages = collect_schema_usages([("deeptutor/services/x.py", code)])
    assert any(isinstance(u, SchemaUsage) for u in usages)
    usage = next(u for u in usages if u.schema_name == "luban_grading_object.v1")
    assert usage.path == "deeptutor/services/x.py"
    assert usage.lineno >= 1


# ─────────────────────────────────────────────────────────────────────────────
# COMPLETENESS CLOSURE — every schema id in the tree has exactly one tier verdict
# ─────────────────────────────────────────────────────────────────────────────


def test_tier2_canonical_contracts_loaded() -> None:
    """The runtime-canonical contracts (T2) load and each has the closure fields."""
    registry = load_schema_registry()
    t2 = registry["tier2_by_name"]
    assert len(t2) == registry["completeness_closure"]["tier_counts"][
        "tier2_runtime_canonical"
    ]
    for name, entry in t2.items():
        # canonical_for (what fact) + consumed_by (the cross-consumer reader proof)
        assert entry.get("canonical_for"), f"{name} missing canonical_for"
        assert entry.get("consumed_by"), f"{name} missing consumed_by proof"
        assert entry.get("status") == "runtime_canonical"
        # field-level canonicalization is an honest TODO, not a fabricated field list
        assert "needs_field_canonicalization" in entry


def test_tier3_carve_out_patterns_present() -> None:
    """The T3 carve-out is a non-empty rule+pattern list, not 1:1 registration."""
    registry = load_schema_registry()
    patterns = registry["tier3_carve_out_patterns"]
    assert patterns, "tier3 carve-out must list artifact name patterns"
    # all lower-cased so classification is case-insensitive
    assert all(p == p.lower() for p in patterns)


def test_full_set_scan_is_deterministic_and_versioned() -> None:
    """The regenerated full set is stable and contains only versioned ids."""
    full = collect_all_schema_identifiers()
    assert collect_all_schema_identifiers() == full  # pure / deterministic
    # every id carries a version suffix (.vN / .mNN / _vN / -vN) — no bare 'public' etc.
    # Use the PRODUCTION suffix regex (single source) so this test cannot drift from it
    # (P0#2 added the dash form for the persisted p0a-v1 report schema version).
    from scripts.check_schema_registry import _FULLSET_VERSION_SUFFIX_RE

    assert all(_FULLSET_VERSION_SUFFIX_RE.search(name) for name in full)
    assert "public" not in full
    assert "learning_evidence" not in full


def test_dash_namespaced_schema_versions_are_collected_not_escaped() -> None:
    """Regression pin for the closure-honesty fix (2026-06-14): persisted
    ``schema_version: "luban-…"`` (DASH-namespaced) artifact tags must ENTER the full
    set, not silently escape it. Before the fix, ``_FULLSET_NAMESPACE_RE`` only matched
    ``luban[_.]`` (underscore/dot), so 11 dash-named one-off script result-envelopes +
    1 ``artifact_version=`` judge-trace label vanished from the full set — and because
    the closure test only asserts ``orphans == []`` over WHATEVER is in the set, a silent
    escape would NOT be caught by it (the id just disappears, it never becomes an orphan).
    This test pins the escape closed at the collection layer so reverting ``luban[-_.]``
    or dropping the ``artifact_version`` marker is caught here, not lost. They are
    script-persistence artifacts → classified T3 (never orphan, never registered)."""
    full = collect_all_schema_identifiers()
    registry = load_schema_registry()
    for dash_id in (
        "luban-consensus-gold-shadow.v0.1",
        "luban-multimodel-jury-gold.v0.1",
        "luban-agentic-model-bakeoff-v2",
    ):
        assert dash_id in full, f"{dash_id} escaped the full set (dash-namespace regression)"
        assert classify_identifier(dash_id, registry) == "tier3"
    # the artifact_version-carried id (marker-key gap) must also be collected
    artifact_id = "luban_m35_fastapi_case_subquestions_20q_100a.v1"
    assert artifact_id in full, f"{artifact_id} escaped (artifact_version marker regression)"
    assert classify_identifier(artifact_id, registry) == "tier3"


def test_full_set_is_closed_three_tier() -> None:
    """THE closure invariant: full set == T1 ∪ T2 ∪ T3, no orphan, no overlap.

    Regenerates the authoritative full set from the source tree and asserts every
    identifier lands in exactly one tier — registered grading object (T1),
    registered runtime-canonical contract (T2), or covered by a T3 carve-out
    pattern. A single unregistered id with no carve-out (an "orphan") fails this
    test — that is the "no unlisted-but-used schema slips through" guarantee.
    """
    report = closure_report()
    # No orphan: every id has a verdict.
    assert report["orphans"] == [], (
        "uncovered schema identifiers (registered nowhere, no T3 carve-out): "
        + ", ".join(report["orphans"])
    )
    assert report["is_closed"] is True
    # The three tiers partition the full set exactly (disjoint + exhaustive).
    tiers = report["tier1"] + report["tier2"] + report["tier3"]
    assert len(tiers) == report["full_set_count"]
    assert sorted(tiers) == sorted(report["full_set"])
    assert len(set(tiers)) == len(tiers)  # disjoint (no id in two tiers)


def test_closure_counts_match_registry_declaration() -> None:
    """The declared tier_counts in the registry equal the live scan (no stale doc)."""
    registry = load_schema_registry()
    declared = registry["completeness_closure"]["tier_counts"]
    report = closure_report()
    assert len(report["tier1"]) == declared["tier1_typed_grading_object"]
    assert len(report["tier2"]) == declared["tier2_runtime_canonical"]
    assert len(report["tier3"]) == declared["tier3_ephemeral_artifact"]
    assert report["full_set_count"] == registry["completeness_closure"]["full_set_count"]


def test_classify_t1_t2_t3_examples() -> None:
    """Spot-check classification: one known id per tier resolves correctly."""
    registry = load_schema_registry()
    assert classify_identifier("luban_grading_object.v1", registry) == "tier1"
    assert classify_identifier("luban_context_pack.v1", registry) == "tier2"
    assert classify_identifier("first_run_completion.v1", registry) == "tier2"
    # the runtime-pinned pack is T2; superseded .v1/.v2 are T3 carve-outs
    assert classify_identifier("luban_rich_leaf_runtime_token_pack.v2.3", registry) == "tier2"
    assert classify_identifier("luban_rich_leaf_runtime_token_pack.v1", registry) == "tier3"
    assert classify_identifier("luban_qwen_blind_residual_audit.v1", registry) == "tier3"
    # a never-before-seen unregistered id with no carve-out is an orphan (a gap)
    assert classify_identifier("luban_freestyle_grading.v9", registry) == "orphan"


# ── Guard recognizes T2: registered, no drift check, optional warning ─────────
def test_guard_tier2_contract_is_recognized_not_unregistered() -> None:
    """A T2 runtime-canonical contract is registered — never flagged unregistered.

    It also must NOT trigger the grading drift/authority checks (it is not a
    per-point grading object), and it emits a non-blocking field-canonicalization
    warning while its fields remain unpinned. Uses a STILL-UNPINNED T2 contract
    (``luban_canonical_knowledge_manifest.v1``) — context_pack/bundle were field-pinned
    in P2#9 (needs_field_canonicalization=false), so they no longer emit this nudge.
    """
    code = 'SCHEMA_VERSION = "luban_canonical_knowledge_manifest.v1"\n'
    usages = collect_schema_usages([("deeptutor/services/construction_grading/x.py", code)])
    ok, message = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is True  # registered T2 -> pass (not "unregistered")
    assert "unregistered" not in message
    assert "needs_field_canonicalization" in message  # the optional nudge fired


def test_guard_tier2_drift_word_not_failed() -> None:
    """A drift-shaped word in a T2 file is not failed: the guard never runs the per-point
    grading field checks on a T2 contract (field parity for pinned T2 is enforced by the
    introspection tests below, not by the text-scanning guard)."""
    code = (
        "def build():\n"
        '    SCHEMA_VERSION = "luban_canonical_knowledge_manifest.v1"\n'
        '    row = {"weight": 1.0}  # not a grading point; guard never field-checks a T2 contract\n'
        "    return row\n"
    )
    usages = collect_schema_usages([("deeptutor/services/construction_grading/x.py", code)])
    ok, _ = evaluate_schema_usages(usages, load_schema_registry())
    assert ok is True


# ─────────────────────────────────────────────────────────────────────────────
# P2#9 — field-level pinning for high-traffic T2 contracts (drift is BLOCKING)
#
# Two high-traffic runtime contracts are field-pinned: their registry ``canonical_fields``
# must equal the producer's DECLARED field set (dataclass fields / the per-record tuple).
# These are CONTRACT tests, not link tests — a producer that adds/renames a field without
# updating the registry (or vice versa) fails here, in the CI smoke subset → BLOCKING. The
# parity is verified by INTROSPECTING the producer (robust), never by scanning text (fragile).
# ─────────────────────────────────────────────────────────────────────────────
def _t2_entry(name: str) -> dict:
    entry = load_schema_registry()["tier2_by_name"].get(name)
    assert entry is not None, f"{name} must be a registered T2 contract"
    return entry


def test_context_pack_v1_fields_pinned_match_producer() -> None:
    """``luban_context_pack.v1`` canonical_fields == LubanContextPack dataclass fields."""
    from deeptutor.services.construction_grading.compiled_context import LubanContextPack

    entry = _t2_entry("luban_context_pack.v1")
    assert entry.get("needs_field_canonicalization") is False, "must be PINNED (false) for P2#9"
    pinned = set(entry.get("canonical_fields") or [])
    declared = set(LubanContextPack.__dataclass_fields__.keys())
    assert pinned == declared, (
        "luban_context_pack.v1 field drift — registry canonical_fields vs LubanContextPack "
        f"dataclass.\n  only in registry: {sorted(pinned - declared)}\n  only in producer: "
        f"{sorted(declared - pinned)}\nUpdate contracts/schema_registry.yaml canonical_fields "
        "to match the producer (or revert the producer field change)."
    )


def test_rich_leaf_context_bundle_v1_record_fields_pinned_match_producer() -> None:
    """``luban_rich_leaf_context_bundle.v1`` canonical_fields == ``_RECORD_FIELDS`` tuple."""
    from deeptutor.services.construction_grading.rich_leaf_runtime import _RECORD_FIELDS

    entry = _t2_entry("luban_rich_leaf_context_bundle.v1")
    assert entry.get("needs_field_canonicalization") is False, "must be PINNED (false) for P2#9"
    pinned = set(entry.get("canonical_fields") or [])
    declared = set(_RECORD_FIELDS)
    assert pinned == declared, (
        "luban_rich_leaf_context_bundle.v1 per-record field drift — registry canonical_fields "
        f"vs _RECORD_FIELDS.\n  only in registry: {sorted(pinned - declared)}\n  only in "
        f"producer: {sorted(declared - pinned)}\nUpdate the registry canonical_fields to match "
        "_RECORD_FIELDS (or revert the producer field change)."
    )


def test_rag_evidence_bundle_v1_fields_pinned_match_producer() -> None:
    """``rag_evidence_bundle.v1`` canonical_fields == EvidenceBundle dataclass fields.

    The evidence bundle was consolidated from 4 drifting inline assembly sites into one
    single-authority builder (``build_evidence_bundle``); this pins its canonical shape so a
    field drift (a lane adds a top-level key, or the dataclass changes) fails here → BLOCKING.
    Lane-specific diagnostics live under the single ``trace`` key, not as top-level fields."""
    from deeptutor.services.rag.evidence_bundle import SCHEMA_ID, EvidenceBundle

    assert SCHEMA_ID == "rag_evidence_bundle.v1"
    entry = _t2_entry("rag_evidence_bundle.v1")
    assert entry.get("needs_field_canonicalization") is False, "must be PINNED (false)"
    pinned = set(entry.get("canonical_fields") or [])
    declared = set(EvidenceBundle.__dataclass_fields__.keys())
    assert pinned == declared, (
        "rag_evidence_bundle.v1 field drift — registry canonical_fields vs EvidenceBundle "
        f"dataclass.\n  only in registry: {sorted(pinned - declared)}\n  only in producer: "
        f"{sorted(declared - pinned)}"
    )


def test_compiled_practice_v2_fields_pinned_match_producer() -> None:
    from deeptutor.services.luban_lesson.practice_html import AUTHORITY_FIELDS

    entry = _t2_entry("luban_compiled_practice.v2")
    assert entry.get("needs_field_canonicalization") is False
    assert set(entry.get("canonical_fields") or []) == set(AUTHORITY_FIELDS)


def test_pinned_t2_contracts_must_list_canonical_fields() -> None:
    """Registry-consistency: a T2 marked PINNED (needs_field_canonicalization=false) MUST
    carry a non-empty ``canonical_fields`` — otherwise it claims field enforcement with no
    field list (a silent unpinned hole). An unpinned T2 (true) must NOT list canonical_fields
    (the list only has meaning once pinned)."""
    for name, entry in load_schema_registry()["tier2_by_name"].items():
        pinned = entry.get("needs_field_canonicalization") is False
        has_fields = bool(entry.get("canonical_fields"))
        if pinned:
            assert has_fields, f"{name} is PINNED but lists no canonical_fields"
        else:
            assert not has_fields, f"{name} is unpinned but lists canonical_fields (ambiguous)"
