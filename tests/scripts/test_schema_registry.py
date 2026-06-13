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
    collect_schema_usages,
    evaluate_schema_usages,
    load_schema_registry,
)


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
