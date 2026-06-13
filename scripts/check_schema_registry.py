"""Schema-registry policy gate — "registered-or-you-can't-use-it" for grading objects.

This is the machine enforcement of the AGENTS.md §5.7 single-authority hard gate and
the KnowQL blueprint D2 ("禁止第三套 schema"). The documentary rule — "the canonical
grading typed object is ``luban_grading_object.v1`` and the 8 pre-existing shapes are
deprecated, adapter-only" — becomes a deterministic CI gate here.

The registry lives in ``contracts/schema_registry.yaml`` (single canonical list). This
script reads it and scans changed code for grading-schema usage, failing on three
conditions:

  (a) a grading-schema NAME used that the registry does not list (an unregistered
      schema — likely a 3rd parallel schema someone is about to mint);
  (b) a DEPRECATED / DRIFT field name (``weight`` instead of ``max_score``,
      ``canonical_answer`` / ``label`` / ``answer_key`` / ``atomic_official_slice``
      instead of ``statement``) used inside code that declares a registered grading
      schema — i.e. building a grading object with the wrong field name;
  (c) a grading object that is missing its single-authority fields — a point with no
      ``authority_source``, or a span-backed point (``official_answer`` /
      ``textbook_cited`` / ``owner``) that drops its ``span_hash`` projection proof.

Scope (deliberately not bureaucratic): only BASE / CROSS-CONSUMER / PERSISTED grading
schemas must register to be usable — the ones where a single field-name drift creates a
second authority or crashes a cross-agent reader. The drift / authority checks ONLY fire
in a file that declares a registered grading-schema literal; an ephemeral internal dict
that never declares a schema, or an unrelated non-grading schema block, is not flagged.

Deterministic and pure: no LLM, no network, no DB. It reads files and applies regexes,
mirroring scripts/check_contract_guard.py.

────────────────────────────────────────────────────────────────────────────────────────
PENDING HUNK — wiring into scripts/check_contract_guard.py
────────────────────────────────────────────────────────────────────────────────────────
scripts/check_contract_guard.py currently has UNCOMMITTED parallel WIP, so this guard is
NOT wired into its main() here (no dirty-file dependency / no carrying of parallel work).
Apply the hunk below when that file is clean (or fold it into the next contract-guard
commit). It is intentionally additive and order-independent:

  # add near the other guard imports at top of scripts/check_contract_guard.py:
  from scripts.check_schema_registry import evaluate_schema_registry  # noqa: E402

  # inside main(), after the upstream/ws guard prints, before the final return:
  schema_ok, schema_message = evaluate_schema_registry(changed_files)
  schema_stream = sys.stdout if schema_ok else sys.stderr
  print(schema_message, file=schema_stream)

  # and extend the final boolean:
  return 0 if (ok and code_ok and node_ok and lifecycle_ok
               and upstream_ok and ws_ok and schema_ok) else 1

``evaluate_schema_registry(changed_files)`` is the changed-files entry point provided
below for exactly this wiring (reads each changed file, runs collect+evaluate).
────────────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "contracts" / "schema_registry.yaml"

# A "grading schema literal" is a string assigned to a schema-marker name. We
# only treat literals that LOOK like grading typed-object schemas as in-scope so
# we never collide with the many unrelated ``schema_version`` literals in the
# codebase (compiled_knowledge_registry.v2, concept_registry, …).
#
# I1: the marker set is aligned with ``_FULLSET_LITERAL_RE`` below — the original
# set missed the bare ``SCHEMA = "…"`` and ``*_SCHEMA[_ID|_VERSION] = "…"`` forms
# (e.g. ``PACK_SCHEMA``, ``GRADING_SCHEMA``), so a canonical grading object declared
# via ``SCHEMA = "luban_grading_object.v1"`` never triggered the drift/authority
# checks. The grading-name hint filter (``_is_grading_schema_name``) still gates
# which literals count, so widening the marker set adds no false positive (a bare
# ``SCHEMA = "public"`` is dropped by the hint filter, same as before).
_SCHEMA_MARKER_RE = re.compile(
    r"""(?:
            [A-Za-z_]*_SCHEMA(?:_ID|_VERSION)?   # PACK_SCHEMA, GRADING_SCHEMA, SOURCE_SCHEMA…
          | SCHEMA(?:_ID|_VERSION)?              # SCHEMA / SCHEMA_ID / SCHEMA_VERSION
          | schema(?:_id|_version)?              # schema / schema_id / schema_version
          | PROTOCOL_VERSION
        )\s*[:=]\s*["']([^"']+)["']""",
    re.VERBOSE,
)

# Schema names that belong to the grading registry namespace. A literal only
# counts as a grading-schema usage if it is either registered OR matches this
# grading-shaped pattern (so an unregistered grading-shaped name still fails,
# while a totally unrelated schema_version literal is ignored).
_GRADING_NAME_HINT_RE = re.compile(
    r"^(?:luban[_.].*grading|.*grading_object|.*scoring_point|.*scoring_artifact"
    r"|case_grading_artifact|luban\.rich_leaf|m35_ai_governed_gold"
    r"|luban_m31_governed_objective|luban_arbitration_gold_panel)",
)

# I2: a "grading-shaped" identifier is a per-point grading TYPED OBJECT — the kind
# whose field-name drift creates a second authority. It is NEVER an ephemeral T3
# artifact. We key the closure's two I2 fixes off this:
#   (a) namespace escape — a grading-shaped versioned id is ALWAYS pulled into the
#       authoritative full set, even if its prefix is not on the namespace allow-
#       list, so an unregistered ``mygrading_object.v1`` cannot escape the closure
#       (it surfaces as an orphan instead of vanishing). 宁多收不逃逸.
#   (b) tier3 substring swallow — a grading-shaped id is one-票否决 for T3: even if
#       its name happens to contain a tier3 substring (``luban_eval_official_key.v1``
#       contains ``_eval``; ``..._audit_key.v1`` contains ``_audit``), it can never be
#       classified ephemeral. A grading typed object that is not registered must be
#       an orphan, never silently carved out.
# Deliberately TIGHT — this is the no-false-positive boundary for I2. A grading-
# shaped id is a BASE grading TYPED OBJECT: the per-point object stem
# (``grading_object`` / ``scoring_point``) IMMEDIATELY followed by its version suffix
# (``.vN`` / ``_vN``) — i.e. the stem is the TERMINAL semantic unit, the object itself.
#
# It deliberately does NOT include the ``*_artifact`` stems. The word "artifact" denotes
# a DERIVED, ephemeral product (a compiled / staged / audited output of grading), which
# is exactly the T3 carve-out class — ``grading_artifact.v1``,
# ``question_grading_artifact.v1_candidate_dry_run``, ``luban_m35_scoring_artifact_ab.v1``
# are all legitimate T3. Vetoing those would re-flag existing carve-outs (a false
# positive). Only the bare per-point typed object (``grading_object.v1``,
# ``scoring_point.v2``) is one-票否决 for T3.
_GRADING_SHAPED_RE = re.compile(
    r"(?:^|[_.])(?:grading_object|scoring_point)(?:\.v[0-9]|_v[0-9])",
)


def _is_grading_shaped(name: str) -> bool:
    """True for a BASE per-point grading TYPED OBJECT id (never ephemeral; I2 anchor).

    Tight by design: matches only ``<object_stem>.vN`` / ``<object_stem>_vN`` where the
    grading OBJECT stem is the terminal unit — not a derived ``*_artifact`` (which is
    by definition ephemeral T3) and not a further-derived object
    (``scoring_point_assets_backfill.v1``). See ``_GRADING_SHAPED_RE`` for the
    no-false-positive rationale.
    """
    return bool(_GRADING_SHAPED_RE.search(name))

# Restrict the whole guard to grading/scoring source paths. The drift-field and
# missing-authority checks are inherently grading-specific; scanning unrelated
# trees would be noisy and bureaucratic.
_IN_SCOPE_PATH_RE = re.compile(
    r"^(?:deeptutor/services/(?:construction_grading|source_compiler)/"
    r"|scripts/(?:run_luban_|compile_2026_|build_luban_)"
    r"|deeptutor/services/construction_grading/runtime_supply/)"
)

# Fields that must be present on a span-backed grading point.
_SPAN_BACKED_AUTHORITIES = frozenset({"official_answer", "textbook_cited", "owner"})


@dataclass(frozen=True)
class SchemaUsage:
    """One grading-schema literal found in a scanned file (with its context)."""

    path: str
    lineno: int
    schema_name: str
    # The whole file body — drift/authority checks need the surrounding code, but
    # only run when this file declared a registered grading schema.
    file_body: str


def load_schema_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load + index ``contracts/schema_registry.yaml`` into a lookup structure."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    schemas = payload.get("schemas")
    if not isinstance(schemas, list) or not schemas:
        raise ValueError("contracts/schema_registry.yaml must define a non-empty schemas list")
    by_name: dict[str, dict[str, Any]] = {}
    for entry in schemas:
        if not isinstance(entry, dict) or "name" not in entry:
            raise ValueError(f"schema registry entry missing name: {entry!r}")
        by_name[str(entry["name"])] = entry
    drift_field_map = payload.get("drift_field_map") or {}
    tier2_entries = payload.get("tier2_canonical_contracts") or []
    tier2_by_name: dict[str, dict[str, Any]] = {}
    for entry in tier2_entries:
        if not isinstance(entry, dict) or "name" not in entry:
            raise ValueError(f"tier2 registry entry missing name: {entry!r}")
        tier2_by_name[str(entry["name"])] = entry
    carve_out = payload.get("tier3_carve_out") or {}
    return {
        "by_name": by_name,
        "tier2_by_name": tier2_by_name,
        "drift_field_map": {str(k): str(v) for k, v in drift_field_map.items()},
        "authority_vocabulary": payload.get("authority_vocabulary") or {},
        "scope_rule": payload.get("scope_rule") or {},
        "completeness_closure": payload.get("completeness_closure") or {},
        "tier3_carve_out_patterns": [
            str(p).lower() for p in (carve_out.get("artifact_name_patterns") or [])
        ],
    }


def _is_grading_schema_name(name: str, registry: dict[str, Any]) -> bool:
    """A literal is in-scope if it is a registered T1/T2 contract or grading-shaped.

    T2 (runtime-canonical) names are recognized so the guard never mis-flags a
    registered runtime contract as "unregistered"; the field-level drift/authority
    checks still only run for the canonical T1 grading object (see below).
    """
    if name in registry["by_name"] or name in registry.get("tier2_by_name", {}):
        return True
    return bool(_GRADING_NAME_HINT_RE.match(name))


# ─────────────────────────────────────────────────────────────────────────────
# Completeness closure — regenerate the AUTHORITATIVE full set and classify it.
#
# "Registered-or-you-can't-use" is only honest if every schema identifier has a
# verdict. The closure below REGENERATES the full set from the source tree (no
# hand-maintained copy can drift) and proves it equals T1 ∪ T2 ∪ T3.
# ─────────────────────────────────────────────────────────────────────────────

# Schema-version literal forms we union over. The task's starting grep matched
# only ``SCHEMA = "…"`` / ``"schema": "…"`` / ``schema_version": "…"`` (152), which
# MISSES the ``SCHEMA_ID = "…"`` / ``schema_id: "…"`` / ``*_SCHEMA = "…"`` /
# ``artifact_schema: "…"`` / ``kind: "…"`` forms — and 8 of the 9 T1 grading
# objects live ONLY in those missed forms. So we match any var/key that ENDS in a
# schema marker (schema / schema_id / schema_version / *_schema / *_SCHEMA[_ID|
# _VERSION]) plus the ``kind`` key, to recover the honest full set. Both quote
# styles. The shape filter below drops any non-versioned/unrelated value.
_FULLSET_LITERAL_RE = re.compile(
    r"""(?:^|[^\w.])               # word boundary that still allows a leading quote
        ["']?                       # optional opening quote on the key
        (?:
            [A-Za-z_][A-Za-z0-9_]*_SCHEMA(?:_ID|_VERSION)?   # SESSION_SCHEMA_VERSION, PACK_SCHEMA…
          | SCHEMA(?:_ID|_VERSION)?                          # SCHEMA / SCHEMA_ID / SCHEMA_VERSION
          | [A-Za-z_][A-Za-z0-9_]*_schema(?:_id|_version)?   # artifact_schema, typed_artifact_schema…
          | schema(?:_id|_version)?                          # schema / schema_id / schema_version
          | kind                                             # observability ``kind`` records
          | PROTOCOL_VERSION
        )
        ["']?\s*[:=]\s*["']([A-Za-z0-9_.-]+)["']""",   # value allows '-' (dash schema ids e.g. p0a-v1)
    re.VERBOSE,
)

# A typed-object / grading / canonical-contract schema id is versioned and lives in
# a known namespace. We accept it iff it carries a version suffix (``.vN`` / ``.mNN``
# / ``_vN``) AND its prefix is one of our typed-object namespaces. This drops bare
# values like ``public`` (Postgres schema), ``learning_evidence`` (event_type), and
# plain enum strings that land in a ``kind``/``schema`` field but are not versioned
# typed-object ids.
# P0#2: also accept a DASH version (``-v[0-9]``, e.g. the persisted report schema
# ``p0a-v1``). Safe despite model names like ``deepseek-v4-flash`` because the suffix is
# only one of two ANDed conditions — the name must ALSO match a grading-name hint or the
# typed-object namespace below, which a bare model string does not (and the literal must
# already sit behind a schema/schema_id/schema_version marker to be collected at all).
_FULLSET_VERSION_SUFFIX_RE = re.compile(r"(?:\.v[0-9]|\.m[0-9]+|_v[0-9]|-v[0-9])")
_FULLSET_NAMESPACE_RE = re.compile(
    r"""^(?:
            luban[_.]
          | assessment_(?:session|p0a)
          | p0a-v                       # bare persisted report schema version (p0a-v1)
          | learning_report             # P2: learner-state runtime contract (registry beyond grading)
          | rag_retrieval_plan          # P2: RAG runtime retrieval-plan contract (registry beyond grading)
          | personalization_context_pack # P2: learner-state PCP runtime contract (registry beyond grading)
          | causal_oa
          | compiled_knowledge_registry
          | case_grading_artifact
          | compact_scoring_artifact
          | grading_artifact
          | question_grading_(?:artifact|registry)
          | rich_leaf_(?:typed_artifact|deep_compile)
          | m35_ai_governed_gold
        )""",
    re.VERBOSE,
)


def _is_fullset_schema_id(name: str) -> bool:
    """A versioned typed-object/grading/canonical-contract id in a known namespace.

    I2(a): a GRADING-NAMED versioned id is ALWAYS in the full set even when its
    prefix is not on the namespace allow-list — otherwise a rogue
    ``mygrading_object.v1`` / ``shadow_scoring_point.v2`` would never enter the closure
    and could never be flagged an orphan (a silent namespace escape). 宁多收不逃逸: a
    grading-named object must always be accounted for. We use the BROAD grading-name
    hint here (any ``*grading_object`` / ``*scoring_point`` / ``*scoring_artifact``
    prefix) so the closure over-collects rather than lets one escape; the tight
    ``_is_grading_shaped`` veto (T3 one-票否决) is applied separately in
    ``classify_identifier``.
    """
    if not _FULLSET_VERSION_SUFFIX_RE.search(name):
        return False
    if _GRADING_NAME_HINT_RE.match(name):
        return True
    return bool(_FULLSET_NAMESPACE_RE.match(name))


_FULLSET_SCAN_DIRS = ("deeptutor", "scripts", "contracts")


def collect_all_schema_identifiers(repo_root: Path = REPO_ROOT) -> set[str]:
    """Regenerate the authoritative FULL SET of schema-version identifiers.

    Pure scan over ``deeptutor/`` / ``scripts/`` / ``contracts/`` source for every
    schema-version literal form, keeping only versioned typed-object/grading/
    canonical-contract ids (drops ``public`` and unversioned enum strings). This is
    the single source of "what exists" the closure test keys off — so the registry
    cannot silently fall behind a newly minted schema id.
    """
    found: set[str] = set()
    for sub in _FULLSET_SCAN_DIRS:
        base = repo_root / sub
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".yaml", ".yml", ".json"}:
                continue
            try:
                body = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for match in _FULLSET_LITERAL_RE.finditer(body):
                name = match.group(1)
                if _is_fullset_schema_id(name):
                    found.add(name)
    return found


def classify_identifier(name: str, registry: dict[str, Any]) -> str:
    """Return the tier of a single schema id: 'tier1' | 'tier2' | 'tier3' | 'orphan'.

    T1 = registered grading typed object; T2 = registered runtime-canonical
    contract; T3 = matches a tier3 carve-out pattern; 'orphan' = none (a gap the
    closure test must surface — an unregistered id with no carve-out).

    I2(b): a grading-SHAPED id is one-票否决 for T3 — a per-point grading typed
    object can never be an ephemeral artifact, even when its name happens to contain
    a tier3 substring (``luban_eval_official_key.v1`` ⊃ ``_eval``; ``..._audit_key.v1``
    ⊃ ``_audit``). So registration (T1/T2) is checked FIRST, then the grading-shaped
    veto, and only THEN the carve-out patterns. An unregistered grading-shaped id is
    therefore an orphan (a real gap), never silently swallowed.
    """
    if name in registry["by_name"]:
        return "tier1"
    if name in registry["tier2_by_name"]:
        return "tier2"
    # I2(b) veto: grading-shaped → never ephemeral. If it is not registered above,
    # it is an orphan that the closure must surface, NOT a T3 carve-out.
    if _is_grading_shaped(name):
        return "orphan"
    lowered = name.lower()
    for pattern in registry["tier3_carve_out_patterns"]:
        if _tier3_pattern_matches(pattern, lowered):
            return "tier3"
    return "orphan"


def _tier3_pattern_matches(pattern: str, lowered_name: str) -> bool:
    """Match a tier3 carve-out pattern against a (lower-cased) schema id.

    I2(b): a ``_word`` segment pattern that ENDS in an alphanumeric char (``_eval`` /
    ``_audit`` / ``_gate`` …) must be a bounded SEGMENT — the char after the matched
    substring must be a segment boundary (``_`` / ``.`` / end), not a word continuation
    — so ``_eval`` does not swallow ``_evaluation_xyz`` mid-word. Patterns that already
    end in their own boundary (``_ab_`` / ``_ab.``), carry a ``.`` (dotted / versioned:
    ``_compile.v``, ``grading_artifact.v1``), or are explicit full names keep plain-
    substring semantics — they are already self-bounding. This preserves every existing
    T3 classification while closing the mid-word substring-swallow.
    """
    idx = lowered_name.find(pattern)
    if idx == -1:
        return False
    # Self-bounding patterns keep plain-substring semantics:
    #   - already end in a boundary char (``_ab_``, ``_ab.``)
    #   - carry a '.' (dotted / version-bearing, e.g. ``_compile.v``, ``grading_artifact.v1``)
    #   - are not a leading-underscore word pattern (explicit full names)
    if "." in pattern or not pattern.startswith("_") or not pattern[-1].isalnum():
        return True
    # Bounded-segment rule for a leading-underscore word pattern ending in a letter/
    # digit: require a segment boundary immediately AFTER the matched substring.
    tail_idx = idx + len(pattern)
    if tail_idx >= len(lowered_name):
        return True  # pattern is a suffix → bounded by end-of-string
    return lowered_name[tail_idx] in ("_", ".")


def closure_report(
    registry: dict[str, Any] | None = None, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Build the closure verdict: full set vs T1/T2/T3, surfacing any orphan.

    Deterministic and pure (file scan only). Returned dict is what both the test
    and the CLI ``--closure`` mode consume.
    """
    registry = registry or load_schema_registry()
    full_set = collect_all_schema_identifiers(repo_root)
    buckets: dict[str, list[str]] = {"tier1": [], "tier2": [], "tier3": [], "orphan": []}
    for name in sorted(full_set):
        buckets[classify_identifier(name, registry)].append(name)
    return {
        "full_set": sorted(full_set),
        "full_set_count": len(full_set),
        "tier1": buckets["tier1"],
        "tier2": buckets["tier2"],
        "tier3": buckets["tier3"],
        "orphans": buckets["orphan"],
        "is_closed": not buckets["orphan"],
    }


def collect_schema_usages(
    files: list[tuple[str, str]],
    *,
    registry: dict[str, Any] | None = None,
) -> list[SchemaUsage]:
    """Scan ``(path, body)`` pairs for grading-schema literals.

    Pure: takes file bodies directly so tests run on synthetic snippets and the
    CI path reads real files. Returns one SchemaUsage per grading-schema literal.
    """
    registry = registry or load_schema_registry()
    usages: list[SchemaUsage] = []
    for path, body in files:
        if not body:
            continue
        for lineno, line in enumerate(body.splitlines(), start=1):
            for match in _SCHEMA_MARKER_RE.finditer(line):
                name = match.group(1)
                if _is_grading_schema_name(name, registry):
                    usages.append(
                        SchemaUsage(
                            path=path,
                            lineno=lineno,
                            schema_name=name,
                            file_body=body,
                        )
                    )
    return usages


def _grading_object_blocks(body: str) -> list[str]:
    """Return code regions that build a canonical grading object/point.

    We only inspect dict/object literals in a file that declares the canonical
    schema; this keeps the drift/authority checks bound to grading objects and
    out of ephemeral internal dicts elsewhere in the same module. The whole body
    is returned as one block — the checks below are line-level and the file is
    already proven to declare the canonical schema by the caller.
    """
    return [body]


def _check_drift_fields(usage: SchemaUsage, registry: dict[str, Any]) -> list[str]:
    """Fail rule (b): a drift field name used in a registered-schema file."""
    drift_map: dict[str, str] = registry["drift_field_map"]
    failures: list[str] = []
    # Only enforce when this file declares the CANONICAL schema — a deprecated
    # source module legitimately still uses its own (drift) field names until the
    # adapter consumes it.
    if usage.schema_name != "luban_grading_object.v1":
        return failures
    for lineno, line in enumerate(usage.file_body.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for drift_name, canonical in drift_map.items():
            # Match the drift name used as a grading-object FIELD: a dict key
            # (``"weight":``) or attribute access (``.weight``). We deliberately do
            # NOT match a bare ``weight =`` local-variable assignment — a loose
            # local variable that happens to share a drift name is an ephemeral
            # internal value, not a grading-object field (scope carve-out).
            key_pat = re.compile(
                rf"""(?<![\w.])["']{re.escape(drift_name)}["']\s*:"""
                rf"""|\.{re.escape(drift_name)}\b"""
            )
            if key_pat.search(stripped):
                failures.append(
                    f"{usage.path}:{lineno}: drift field '{drift_name}' on grading object "
                    f"'{usage.schema_name}' — use canonical '{canonical}'. "
                    f"({stripped[:100]})"
                )
    return failures


def _check_single_authority(usage: SchemaUsage) -> list[str]:
    """Fail rule (c): a grading point missing authority_source / span_hash proof.

    Heuristic but deterministic: find dict literals that look like a grading point
    (carry a ``point_id`` key) inside a file that declares the canonical schema.
    A point dict must carry ``authority_source``; a span-backed authority point
    must also carry ``span_hash``.
    """
    if usage.schema_name != "luban_grading_object.v1":
        return []
    failures: list[str] = []
    body = usage.file_body
    # Find each braced region that contains a point_id key (a grading point dict).
    for pmatch in re.finditer(r"\{[^{}]*\"point_id\"[^{}]*\}", body, re.DOTALL):
        block = pmatch.group(0)
        lineno = body[: pmatch.start()].count("\n") + 1
        has_authority = re.search(r"[\"']authority_source[\"']\s*:", block) is not None
        if not has_authority:
            failures.append(
                f"{usage.path}:{lineno}: grading point on '{usage.schema_name}' is missing "
                f"required 'authority_source' (single-authority field). "
                f"Every point must carry authority_source ∈ "
                f"{{official_answer, textbook_cited, owner, pending_calibration}}."
            )
            continue
        # span-backed authority must carry span_hash
        auth_lit = re.search(r"[\"']authority_source[\"']\s*:\s*[\"']([^\"']+)[\"']", block)
        if auth_lit and auth_lit.group(1) in _SPAN_BACKED_AUTHORITIES:
            if re.search(r"[\"']span_hash[\"']\s*:", block) is None:
                failures.append(
                    f"{usage.path}:{lineno}: span-backed point "
                    f"(authority_source='{auth_lit.group(1)}') on '{usage.schema_name}' "
                    f"is missing its 'span_hash' projection proof."
                )
    return failures


def evaluate_schema_usages(usages: list[SchemaUsage], registry: dict[str, Any]) -> tuple[bool, str]:
    """Apply the three fail rules to collected grading-schema usages."""
    if not usages:
        return True, "schema-registry-guard: no grading schema usage in changed files"

    by_name: dict[str, dict[str, Any]] = registry["by_name"]
    tier2_by_name: dict[str, dict[str, Any]] = registry.get("tier2_by_name", {})
    failures: list[str] = []
    warnings: list[str] = []
    seen_names: set[str] = set()

    for usage in usages:
        seen_names.add(usage.schema_name)
        # T2 runtime-canonical contract: registered, but NOT a per-point grading
        # object — skip the drift/authority field checks (no fabricated field set).
        # Emit an OPTIONAL warning when its field contract is not yet pinned, to
        # nudge eventual field-level canonicalization without failing the build.
        if usage.schema_name in tier2_by_name:
            entry = tier2_by_name[usage.schema_name]
            if entry.get("needs_field_canonicalization"):
                warnings.append(
                    f"{usage.path}:{usage.lineno}: runtime-canonical contract "
                    f"'{usage.schema_name}' is registered (T2) but has "
                    f"needs_field_canonicalization=true — its field names are not yet "
                    f"pinned; a drift would not be caught. Consider pinning fields."
                )
            continue
        # (a) unregistered grading schema name
        if usage.schema_name not in by_name:
            failures.append(
                f"{usage.path}:{usage.lineno}: unregistered grading schema "
                f"'{usage.schema_name}'. The canonical grading typed object is "
                f"'luban_grading_object.v1' (contracts/schema_registry.yaml). Register it "
                f"there or emit the canonical schema (directly or via grading_object_adapters)."
            )
            continue
        # (b) drift field names in a canonical-schema file
        failures.extend(_check_drift_fields(usage, registry))
        # (c) single-authority field completeness
        failures.extend(_check_single_authority(usage))

    warn_suffix = ""
    if warnings:
        warn_suffix = "\nschema-registry-guard: warnings (non-blocking)\n" + "\n".join(
            dict.fromkeys(warnings)
        )

    if failures:
        # de-dup while preserving order
        unique = list(dict.fromkeys(failures))
        return False, "schema-registry-guard: failed\n" + "\n".join(unique) + warn_suffix
    return True, (
        "schema-registry-guard: passed | schemas in scope: "
        + ", ".join(sorted(seen_names))
        + warn_suffix
    )


def _read_changed_files(changed_files: list[str]) -> list[tuple[str, str]]:
    """Read in-scope grading source files into (path, body) pairs."""
    pairs: list[tuple[str, str]] = []
    for raw in changed_files:
        path = raw.strip()
        if not path or not _IN_SCOPE_PATH_RE.match(path):
            continue
        full = REPO_ROOT / path
        if not full.exists() or not full.is_file():
            continue
        try:
            body = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        pairs.append((path, body))
    return pairs


def evaluate_schema_registry(changed_files: list[str]) -> tuple[bool, str]:
    """Changed-files entry point — the hook contract-guard wires into (pending hunk).

    Reads each in-scope changed file, collects grading-schema usages, evaluates
    the three fail rules. Mirrors the other ``evaluate_*`` guards' signature.
    """
    pairs = _read_changed_files(changed_files)
    if not pairs:
        return True, "schema-registry-guard: no in-scope grading source changed"
    registry = load_schema_registry()
    usages = collect_schema_usages(pairs, registry=registry)
    return evaluate_schema_usages(usages, registry)


def _git_current_candidate_files() -> list[str]:
    files: set[str] = set()
    for command in (
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        files.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(files)


def _run_closure_cli() -> int:
    """Print the three-tier closure report; fail if any identifier is an orphan."""
    report = closure_report()
    print(
        "schema-registry-closure: "
        f"full_set={report['full_set_count']} "
        f"tier1={len(report['tier1'])} tier2={len(report['tier2'])} "
        f"tier3={len(report['tier3'])} orphans={len(report['orphans'])}"
    )
    if report["orphans"]:
        print(
            "schema-registry-closure: FAILED — uncovered schema identifiers "
            "(registered nowhere, no tier3 carve-out):",
            file=sys.stderr,
        )
        for name in report["orphans"]:
            print(f"  - {name}", file=sys.stderr)
        return 1
    print("schema-registry-closure: CLOSED — every schema id has a tier verdict")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when grading code uses an unregistered/deprecated/incomplete schema."
    )
    parser.add_argument(
        "files", nargs="*", help="Explicit changed files. If omitted, git diff is used."
    )
    parser.add_argument(
        "--closure",
        action="store_true",
        help="Regenerate the full schema-id set and verify the three-tier closure "
        "(T1 ∪ T2 ∪ T3 == full set, no orphan). Ignores changed-files mode.",
    )
    args = parser.parse_args(argv)

    if args.closure:
        return _run_closure_cli()

    changed = args.files or _git_current_candidate_files()
    ok, message = evaluate_schema_registry(changed)
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
