"""Rich-leaf compiled-context runtime (frozen v3.0.1 token pack, external release pointer).

Loads the tracked rich-leaf runtime supply (``runtime_supply/v_rich_leaf_context``) — the
quarantine-filtered projection of the frozen v3.0.1 runtime token pack — and resolves a canonical
leaf code into its compiled teaching context (concepts / rules / exam_patterns / teaching_cards).

Authority discipline: TEACHING context only, never an answer key — ``official_score_allowed`` is
structurally False. Per the rich-leaf compiler plan, ``controlled_default`` is never an artifact
self-claim: the artifact stays candidate-tier; publishing this runtime-supply bundle (the script
``scripts/run_luban_rich_leaf_runtime_supply_publish.py``) is the external release-pointer act, and
RUNTIME consumption is additionally gated by the env flag ``LUBAN_RICH_LEAF_RUNTIME_ENABLED``
(default OFF -> consumers behave byte-identically). Tamper / missing / unverifiable supply falls
open to None + warning (callers keep the existing four-source chain), mirroring
``canonical_knowledge_runtime`` / ``textbook_knowledge_runtime`` precedent.
"""
from __future__ import annotations

from functools import lru_cache
import json
import logging
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading import compiled_registry_resolver as _R
from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex

_log = logging.getLogger(__name__)

AUTHORITY = "luban_rich_leaf_context"
ENV_FLAG = "LUBAN_RICH_LEAF_RUNTIME_ENABLED"
PACK_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
BUNDLE_SCHEMA = "luban_rich_leaf_context_bundle.v1"
_NAMESPACE = "rich_leaf_context"
_SUPPLY_DIR = Path(__file__).parent / "runtime_supply" / "v_rich_leaf_context"
_BUNDLE_NAME = "rich_leaf_context_bundle.json"

# Per-record fields carried into the runtime bundle. The pack's internal lifecycle flags
# (candidate_only / review_only / runtime_install_allowed / production_default) are intentionally
# NOT copied: lifecycle is an external pointer concern, never a record self-claim.
_RECORD_FIELDS = (
    "unit_id",
    "leaf_id",
    "leaf_name_path",
    "compiled_context",
    "confidence",
    "source_lane",
    "source_ref",
    "relative_path",
)
# Pack safety invariants that must all be exactly False for a publish to proceed.
_PACK_SAFETY_FALSE_KEYS = (
    "official_score_allowed",
    "canonical_truth_written",
    "release_truth_claimed",
)


def rich_leaf_runtime_enabled() -> bool:
    """Runtime consumption flag. Default OFF — loader/bundle existence never implies enablement."""
    import os

    return os.environ.get(ENV_FLAG, "").strip().lower() in ("1", "true", "on", "yes")


def build_runtime_supply_bundle(pack: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile a frozen runtime token pack into a signed runtime-supply (bundle, pointer) pair.

    Fail-closed validation: schema pin + safety invariants. Every ``quarantine_candidate`` unit is
    EXCLUDED from the records (hard requirement: quarantined units must never be supplied). The
    manifest is signed with the same (content_hash | namespace | status) convention as the other
    lanes so ``compiled_registry_resolver.verify_bundle`` applies unchanged. status stays
    ``release_candidate`` / published=False — publish-to-default is an owner action, not this build.
    """
    if not isinstance(pack, dict) or pack.get("schema") != PACK_SCHEMA:
        raise ValueError(f"pack schema must be {PACK_SCHEMA!r}, got {pack.get('schema')!r}")
    safety = pack.get("safety") if isinstance(pack.get("safety"), dict) else {}
    for key in _PACK_SAFETY_FALSE_KEYS:
        if safety.get(key) is not False:
            raise ValueError(f"pack safety gate failed: {key} must be False, got {safety.get(key)!r}")
    quarantine = pack.get("quarantine") if isinstance(pack.get("quarantine"), dict) else {}
    quarantined_ids = {str(u) for u in (quarantine.get("quarantine_candidate_unit_ids") or [])}
    records: list[dict[str, Any]] = []
    excluded = 0
    for unit in pack.get("runtime_token_pack_units") or []:
        if not isinstance(unit, dict) or not str(unit.get("leaf_id") or "").strip():
            continue
        if str(unit.get("unit_id") or "") in quarantined_ids:
            excluded += 1
            continue
        records.append({key: unit.get(key) for key in _RECORD_FIELDS})
    records.sort(key=lambda r: (str(r.get("leaf_id") or ""), str(r.get("unit_id") or "")))
    content_hash = _sha256_hex(records)
    status = "release_candidate"
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "namespace": _NAMESPACE,
        "status": status,
        "published": False,
        "tier": "teaching_context_not_answer_key",
        "official_score_allowed": False,
        "llm_may_decide_correctness": False,
        "canonical_truth_written": False,
        "source_pack_schema": pack.get("schema"),
        "source_pack_version": pack.get("version"),
        "source_pack_unit_count": len(pack.get("runtime_token_pack_units") or []),
        "quarantine_excluded_count": excluded,
        "record_count": len(records),
        "content_hash": content_hash,
        "signature": _sha256_hex([content_hash, _NAMESPACE, status]),
        "rollback_pointer": "legacy (no rich_leaf_context -> runtime keeps existing four-source chain)",
    }
    pointer = {
        "namespace": _NAMESPACE,
        "status": status,
        "published": False,
        "expected_content_hash": content_hash,
        "record_count": len(records),
        "quarantine_excluded_count": excluded,
        "source_pack_version": pack.get("version"),
    }
    return ({"manifest": manifest, "records": records}, pointer)


@lru_cache(maxsize=1)
def _load_index() -> dict[str, dict[str, Any]] | None:
    """Load + four-gate verify the tracked supply once; index records by leaf_id. None -> fall open."""
    loaded = _R.load_supply(_SUPPLY_DIR, bundle_name=_BUNDLE_NAME)
    if loaded is None:
        return None
    bundle, pointer = loaded
    ok, reason = _R.verify_bundle(bundle, pointer, namespace=_NAMESPACE)
    if not ok:
        _log.warning("rich leaf runtime supply rejected: %s -> fall open to legacy chain", reason)
        return None
    return {
        str(r.get("leaf_id")): r
        for r in bundle.get("records") or []
        if isinstance(r, dict) and str(r.get("leaf_id") or "").strip()
    }


def get_rich_leaf_context(leaf_code: str) -> dict[str, Any] | None:
    """Resolve a canonical leaf code into its rich compiled TEACHING context, or None to fall open."""
    leaf = str(leaf_code or "").strip()
    if not leaf:
        return None
    index = _load_index()
    if not index:
        return None
    record = index.get(leaf)
    if record is None:
        return None
    compiled = record.get("compiled_context")
    if not isinstance(compiled, dict) or not any(compiled.values()):
        return None
    return {
        "authority": AUTHORITY,
        "leaf_id": leaf,
        "leaf_name_path": record.get("leaf_name_path"),
        "compiled_context": compiled,
        "confidence": record.get("confidence"),
        "tier": "teaching_context_not_answer_key",
        "official_score_allowed": False,
        "llm_may_decide_correctness": False,
        "writeback_performed": False,
    }


def _clip(value: Any, *, limit: int = 700) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _parse_item(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
    except Exception:  # noqa: BLE001 — malformed compiled item degrades to plain text
        return {}
    return parsed if isinstance(parsed, dict) else {}


def format_rich_leaf_grounding_lines(rich: dict[str, Any] | None) -> list[str]:
    """Render a rich-leaf context block into LLM grounding lines (teaching-tier marker included).

    Shared by both grounding renderers (compiled_knowledge.general_knowledge and deep_question's
    local copy) so the rendering policy lives in ONE place. Missing/malformed input -> [] (the
    caller's output stays byte-identical to the legacy rendering)."""
    if not isinstance(rich, dict):
        return []
    compiled = rich.get("compiled_context")
    if not isinstance(compiled, dict):
        return []
    body: list[str] = []
    for concept in (compiled.get("concepts") or [])[:6]:
        text = _clip(concept)
        if text:
            body.append(f"- [概念] {text}")
    for raw in (compiled.get("rules") or [])[:6]:
        item = _parse_item(raw)
        text = _clip(item.get("description") or raw)
        if text:
            severity = str(item.get("severity") or "").strip()
            body.append(f"- [规则{('·' + severity) if severity else ''}] {text}")
    for raw in (compiled.get("exam_patterns") or [])[:6]:
        item = _parse_item(raw)
        text = _clip(item.get("description") or raw)
        if not text:
            continue
        keywords = "、".join(str(k) for k in (item.get("grading_keywords") or []) if str(k).strip())
        body.append(f"- [考点] {text}" + (f"（关键词：{keywords}）" if keywords else ""))
    for raw in (compiled.get("teaching_cards") or [])[:6]:
        item = _parse_item(raw)
        title = str(item.get("title") or "").strip()
        text = _clip(item.get("content") or raw)
        if text:
            body.append(f"- [教学卡] {(title + '：') if title else ''}{text}")
    if not body:
        return []
    header = "【富叶编译上下文 rich_leaf - 仅供讲解，非官方答案，不得作为官方判分依据】"
    leaf_line = f"富叶知识点：{rich.get('leaf_name_path') or ''}（{rich.get('leaf_id') or ''}）"
    return [header, leaf_line, *body]


__all__ = [
    "AUTHORITY",
    "BUNDLE_SCHEMA",
    "ENV_FLAG",
    "PACK_SCHEMA",
    "build_runtime_supply_bundle",
    "format_rich_leaf_grounding_lines",
    "get_rich_leaf_context",
    "rich_leaf_runtime_enabled",
]
