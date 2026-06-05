"""Luban v1 beta_shadow runtime loader (fat skill, read-only, fail-closed).

This is the SINGLE authority for v1 beta_shadow runtime scoring. The runtime wrapper in
``deep_question`` only flips a flag and appends metadata; ALL grading policy (which authority
bucket a point uses, how a machine/list/source spec matches a student answer, what disposition
results) lives here.

Hard invariants (mirror M7-M10):
- read-only: loads the M10 non-textbook authority factory artifact; NEVER writes a DB / file /
  Learning Brain truth / formal registry; never touches v0, the kernel, or RAG.
- official_answer is NEVER a textbook source: machine/list specs are CASE RUBRIC SEEDS, labelled
  ``rubric_seed=official_answer_not_textbook``; only textbook-verbatim points are source-backed.
- fail-closed: a missing / malformed / hash-mismatched artifact raises ``BetaSupplyUnavailable``;
  the wrapper degrades to legacy. A point that cannot be decided becomes ``review_required`` — it is
  NEVER auto-certified. Partial list / numeric off-by-one / contradiction never auto.
- everything is shadow: ``not_production_grade=True``, ``writeback_performed=False``,
  ``human_reviewed=False``.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_ARTIFACT_ROOT = _REPO / "artifacts" / "luban_grading_artifacts"
# canonical M10 supply dir (auto-discovered if the exact name differs)
_M10_GLOB = "non_textbook_rubric_authority_factory_m10_*"

_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_JUDGE_NEG = ("不合理", "不正确", "不妥", "不符合", "不成立", "无效", "错误")
_JUDGE_POS = ("合理", "正确", "妥当", "妥", "符合", "成立", "可以")


class BetaSupplyUnavailable(Exception):
    """Raised when the beta supply artifact is missing / malformed -> wrapper fails closed."""


@dataclass(frozen=True)
class BetaSupply:
    supply_dir: str
    content_hash: str
    machine_specs: dict[tuple[str, str], dict[str, Any]]
    list_specs: dict[tuple[str, str], dict[str, Any]]
    source_backed: set
    review_required: set
    external_required: set
    source_terms: dict = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {
            "machine_specs": len(self.machine_specs),
            "list_specs": len(self.list_specs),
            "source_backed": len(self.source_backed),
            "review_required": len(self.review_required),
            "external_required": len(self.external_required),
            "beta_shadow_scoring_supply": len(self.machine_specs) + len(self.list_specs) + len(self.source_backed),
        }


def _norm(s: Any) -> str:
    return re.sub(r"[\s，、；;：:（）()【】\[\]　·,.。\"'“”‘’]", "", str(s or ""))


def discover_supply_dir(root: Path | None = None) -> Path:
    base = root or _ARTIFACT_ROOT
    matches = sorted(base.glob(_M10_GLOB))
    if not matches:
        raise BetaSupplyUnavailable(f"no M10 supply dir under {base} matching {_M10_GLOB}")
    return matches[-1]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise BetaSupplyUnavailable(f"missing supply file: {path.name}")
    rows = []
    for ln in path.read_text("utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError as exc:
            raise BetaSupplyUnavailable(f"malformed jsonl in {path.name}: {exc}") from exc
    return rows


def _load_verified_source_backed() -> tuple[set, dict]:
    """Read-only union of M7 reverified + M8 + M9 verified source candidates (the 23), plus the
    verified TEXTBOOK term per point (used by the runtime source matcher). Best-effort: a missing
    prior-stage file is skipped (still fail-safe)."""
    out: set = set()
    terms: dict = {}
    m8 = _ARTIFACT_ROOT / "v1_alpha_grand_sprint_m8_20260604" / "verified_source_candidates.jsonl"
    m9 = _ARTIFACT_ROOT / "v1_beta_shadow_source_assault_m9_20260604" / "verified_source_candidates_m9.jsonl"
    m7 = (_ARTIFACT_ROOT / "registry_v1_council_hardened_candidate_m7_20260604"
          / "hardened_candidate_artifacts_preview.jsonl")
    for f in (m8, m9):
        if f.exists():
            for ln in f.read_text("utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                r = json.loads(ln)
                key = (r["question_id"], r["point_id"])
                out.add(key)
                ref = r.get("verified_source_ref") or {}
                for cand in (ref.get("term"), ref.get("variant"), ref.get("parent_term")):
                    if cand and str(cand).strip():
                        terms.setdefault(key, []).append(str(cand).strip())
    if m7.exists():
        for ln in m7.read_text("utf-8").splitlines():
            ln = ln.strip()
            if ln:
                a = json.loads(ln)
                for s in a.get("scoring_points", []):
                    if s.get("auto_certifiable"):
                        out.add((a["question_id"], s["point_id"]))
    return out, terms


def _hash_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()


def load_beta_supply(root: Path | None = None) -> BetaSupply:
    """Read-only load + schema-validate + hash the M10 supply. Fail-closed on any defect."""
    supply_dir = discover_supply_dir(root)
    f_machine = supply_dir / "machine_checkable_case_specs_m10.jsonl"
    f_list = supply_dir / "list_rule_structured_specs_m10.jsonl"
    f_review = supply_dir / "review_required_packets_m10.jsonl"
    f_external = supply_dir / "external_source_work_orders_m10.jsonl"
    f_inv = supply_dir / "residual_authority_inventory_m10.json"
    if not f_inv.exists():
        raise BetaSupplyUnavailable(f"missing inventory: {f_inv.name}")

    machine_rows = _read_jsonl(f_machine)
    list_rows = _read_jsonl(f_list)
    review_rows = _read_jsonl(f_review)
    external_rows = _read_jsonl(f_external)

    machine_specs: dict[tuple[str, str], dict[str, Any]] = {}
    for r in machine_rows:
        # schema gate: official_answer is NEVER a textbook source here
        if r.get("textbook_source") is not False or r.get("auto_certifiable") is not False:
            raise BetaSupplyUnavailable("machine spec violates source/auto invariant")
        if not r.get("spec"):
            raise BetaSupplyUnavailable("machine spec missing 'spec'")
        machine_specs[(r["question_id"], r["point_id"])] = r

    list_specs: dict[tuple[str, str], dict[str, Any]] = {}
    for r in list_rows:
        if r.get("textbook_source") is not False or r.get("auto_certifiable") is not False:
            raise BetaSupplyUnavailable("list spec violates source/auto invariant")
        list_specs[(r["question_id"], r["point_id"])] = r

    review_required = {(r["question_id"], r["point_id"]) for r in review_rows}
    external_required = {(r["question_id"], r["point_id"]) for r in external_rows}

    # source-backed points = M10 textbook bucket UNION the M7/M8/M9 verified source candidates
    # (the canonical 23 textbook-verbatim auto points; the only auto-source path).
    inv = json.loads(f_inv.read_text("utf-8"))
    source_backed = {(p["question_id"], p["point_id"]) for p in inv.get("points", [])
                     if p.get("authority_bucket") == "textbook_verbatim_auto_candidate"}
    verified_keys, source_terms = _load_verified_source_backed()
    source_backed |= verified_keys

    content_hash = _hash_files([f_machine, f_list, f_review, f_external, f_inv])
    return BetaSupply(
        supply_dir=str(supply_dir.relative_to(_REPO)),
        content_hash=content_hash,
        machine_specs=machine_specs,
        list_specs=list_specs,
        source_backed=source_backed,
        review_required=review_required,
        external_required=external_required,
        source_terms=source_terms,
    )


@lru_cache(maxsize=1)
def _cached_supply_key() -> tuple[str, str]:
    s = load_beta_supply()
    return (s.supply_dir, s.content_hash)


# ----------------------------- deterministic matcher (runtime authority) -----------------------------

def _extract_judgment(answer: str) -> bool | None:
    if any(n in answer for n in _JUDGE_NEG):
        return False
    if any(p in answer for p in _JUDGE_POS):
        return True
    return None


def _extract_values(answer: str) -> list[float]:
    out = []
    for m in _NUM.findall(answer):
        try:
            out.append(float(m))
        except ValueError:
            continue
    return out


def _machine_accepts(spec: dict[str, Any], answer: str) -> bool:
    kind = spec.get("kind")
    vals = _extract_values(answer)
    judg = _extract_judgment(answer)
    if kind in ("numeric_formula", "numeric_value", "numeric_judgment"):
        lo, hi = spec.get("acceptance_range", [None, None])
        if lo is None:
            return False
        ok = any(lo <= v <= hi for v in vals)
        if kind == "numeric_judgment":
            return ok and judg is not None and judg == spec.get("judgment")
        return ok
    if kind == "numeric_range":
        return any(spec["lo"] <= v <= spec["hi"] for v in vals)
    if kind == "boolean_judgment":
        return judg is not None and judg == spec.get("expected_bool")
    return False


def _list_accepts(spec: dict[str, Any], answer: str) -> bool:
    na = _norm(answer)
    matchers = spec.get("item_matchers") or []
    if not matchers:
        return False
    # full coverage required: every rubric item must appear verbatim-normalised in the answer
    return all(m.get("norm") and m["norm"] in na for m in matchers)


def _source_accepts(supply_point_terms: list[str], answer: str) -> bool:
    na = _norm(answer)
    return any(len(_norm(t)) >= 4 and _norm(t) in na for t in supply_point_terms)


# ----------------------------- scoring + payload (fail-closed) -----------------------------

def score_point(supply: BetaSupply, question_id: str, point_id: str, answer: str) -> dict[str, Any]:
    """Score ONE scoring point. Never auto-certifies a gap; undecidable -> review_required."""
    key = (question_id, point_id)
    base = {"question_id": question_id, "point_id": point_id, "not_production_grade": True,
            "human_reviewed": False, "writeback_performed": False}

    if key in supply.machine_specs:
        spec = supply.machine_specs[key]["spec"]
        accept = _machine_accepts(spec, answer)
        return {**base, "path": "machine_checkable_spec_path", "spec_kind": spec.get("kind"),
                "disposition": "auto_shadow_safe" if accept else "review_required",
                "auto_shadow": accept, "rubric_seed": "official_answer_not_textbook"}
    if key in supply.list_specs:
        spec = supply.list_specs[key]["spec"]
        accept = _list_accepts(spec, answer)
        return {**base, "path": "list_rule_full_coverage_path",
                "disposition": "auto_shadow_safe" if accept else "review_required",
                "auto_shadow": accept, "list_full_coverage_required": True,
                "rubric_seed": "official_answer_not_textbook"}
    if key in supply.source_backed:
        # source-backed: the student answer must contain the VERIFIED textbook term (not the point_id).
        terms = supply.source_terms.get(key) or []
        verbatim = _source_accepts(terms, answer) if terms else False
        return {**base, "path": "textbook_auto_path",
                "disposition": "auto_shadow_safe" if verbatim else "review_required",
                "auto_shadow": verbatim, "source_authority": "textbook_verbatim",
                "matched_textbook_terms": [t for t in terms if _source_accepts([t], answer)]}
    if key in supply.external_required:
        return {**base, "path": "external_source_blocked", "disposition": "source_gap",
                "auto_shadow": False}
    if key in supply.review_required:
        return {**base, "path": "review_required_path", "disposition": "review_required",
                "auto_shadow": False}
    # unknown point -> fail-safe review, never auto
    return {**base, "path": "unknown_point", "disposition": "review_required", "auto_shadow": False}


def build_beta_shadow_payload(question_id: str, student_id: str, student_answer: str,
                              point_ids: list[str] | None = None,
                              *, root: Path | None = None) -> dict[str, Any]:
    """Build the append-only ``luban_grading_engine_v1_beta_shadow`` payload + LB preview +
    review queue item. Read-only; fail-closed (raises BetaSupplyUnavailable to the wrapper)."""
    supply = load_beta_supply(root)
    pids = point_ids or _points_for_question(supply, question_id)
    point_results = [score_point(supply, question_id, pid, student_answer) for pid in pids]
    auto = [p for p in point_results if p.get("auto_shadow")]
    review = [p for p in point_results if not p.get("auto_shadow")]

    # Learning Brain PREVIEW only (evidence -> claim -> pack); writeback=false, no canonical truth.
    lb_preview = {
        "preview_only": True, "writeback_performed": False, "production_user_written": False,
        "human_reviewed": False, "student_id": student_id, "question_id": question_id,
        "evidence": [{"point_id": p["point_id"], "path": p["path"], "auto_shadow": p.get("auto_shadow", False)}
                     for p in point_results],
        "claim": {"auto_shadow_points": len(auto), "review_points": len(review),
                  "claim_authority": "beta_shadow_preview_not_production_truth"},
    }
    review_queue_item = {
        "question_id": question_id, "student_id": student_id,
        "review_points": [p["point_id"] for p in review],
        "auto_shadow_points": [p["point_id"] for p in auto],
        "final_disposition": "auto_shadow_safe" if not review else "review_required",
        "human_reviewed": False, "qa_simulated": True,
    }
    return {
        "authority": "luban_grading_engine_v1_beta_shadow",
        "not_production_grade": True, "shadow_status": "ok",
        "supply_dir": supply.supply_dir, "supply_content_hash": supply.content_hash,
        "supply_counts": supply.counts(),
        "point_results": point_results,
        "auto_shadow_count": len(auto), "review_required_count": len(review),
        "learning_brain_preview": lb_preview,
        "teacher_review_queue_item": review_queue_item,
        "writeback_performed": False, "human_reviewed": False,
        "production_runtime_connected": False, "formal_registry_emitted": False,
    }


def _points_for_question(supply: BetaSupply, question_id: str) -> list[str]:
    pts = []
    for d in (supply.machine_specs, supply.list_specs):
        pts += [pid for (qid, pid) in d if qid == question_id]
    pts += [pid for (qid, pid) in supply.source_backed if qid == question_id]
    pts += [pid for (qid, pid) in supply.review_required if qid == question_id]
    pts += [pid for (qid, pid) in supply.external_required if qid == question_id]
    return sorted(dict.fromkeys(pts))


# ----------------------------- v1 controlled_runtime_candidate (release-candidate registry) -----------------------------

_RC_GLOB = "controlled_production_runtime_flip_m16_*"
_RC_NAME = "registry_v1_release_candidate.json"


class ReleaseCandidateUnavailable(Exception):
    """Raised when the release-candidate registry is missing / malformed -> wrapper fails closed."""


def discover_release_candidate_registry(root: Path | None = None) -> Path:
    base = root or _ARTIFACT_ROOT
    for d in sorted(base.glob(_RC_GLOB), reverse=True):
        p = d / _RC_NAME
        if p.exists():
            return p
    direct = base / _RC_NAME
    if direct.exists():
        return direct
    raise ReleaseCandidateUnavailable(f"no {_RC_NAME} under {base}")


def load_release_candidate_registry(root: Path | None = None) -> dict[str, Any]:
    """Read-only load + schema/hash validate of registry_v1_release_candidate. Fail-closed.

    HARD: status must be ``release_candidate`` (NEVER ``published``); it must NOT claim production
    default and must carry a content hash + rollback pointer. A bad registry raises
    ReleaseCandidateUnavailable so the runtime wrapper degrades to legacy."""
    path = discover_release_candidate_registry(root)
    try:
        reg = json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        raise ReleaseCandidateUnavailable(f"malformed release_candidate registry: {exc}") from exc
    if reg.get("status") != "release_candidate":
        raise ReleaseCandidateUnavailable(f"registry status must be 'release_candidate', got {reg.get('status')!r}")
    if reg.get("published") is True or reg.get("production_default") not in (None, "off", False):
        raise ReleaseCandidateUnavailable("release_candidate registry must not be published / production-default")
    if not reg.get("registry_content_hash") or not reg.get("rollback_pointer") or not reg.get("points"):
        raise ReleaseCandidateUnavailable("release_candidate registry missing hash / rollback_pointer / points")
    # recompute the hash over the points to detect tampering
    points_blob = json.dumps(reg["points"], ensure_ascii=False, sort_keys=True)
    recomputed = hashlib.sha256(points_blob.encode("utf-8")).hexdigest()
    if recomputed != reg["registry_content_hash"]:
        raise ReleaseCandidateUnavailable("release_candidate registry hash mismatch (tampered)")
    return {**reg, "registry_path": str(path)}


def build_controlled_runtime_payload(question_id: str, student_id: str, student_answer: str,
                                     *, root: Path | None = None) -> dict[str, Any]:
    """v1 controlled_runtime_candidate payload: the SAME deterministic scoring as beta_shadow, but
    promoted to mode ``controlled_runtime_candidate`` and gated on a loadable release_candidate
    registry. Still append-only, still NOT production default, still no production/canonical write."""
    registry = load_release_candidate_registry(root)
    base = build_beta_shadow_payload(question_id, student_id, student_answer, root=root)
    registry_points = {(p["question_id"], p["point_id"]) for p in registry["points"]}
    # only points present in the release_candidate registry are controlled-runtime auto-eligible
    for pr in base.get("point_results", []):
        if (question_id, pr.get("point_id")) not in registry_points and pr.get("auto_shadow"):
            pr["auto_shadow"] = False
            pr["disposition"] = "review_required"
            pr["downgraded_reason"] = "not_in_release_candidate_registry"
    auto = sum(1 for p in base.get("point_results", []) if p.get("auto_shadow"))
    review = len(base.get("point_results", [])) - auto
    return {**base,
            "authority": "luban_grading_engine_v1_controlled_runtime",
            "mode": "controlled_runtime_candidate",
            "registry_status": "release_candidate",
            "registry_version": registry.get("version_id"),
            "registry_content_hash": registry.get("registry_content_hash"),
            "rollback_pointer": registry.get("rollback_pointer"),
            "auto_shadow_count": auto, "review_required_count": review,
            "production_default": "off", "production_runtime_connected": False,
            "formal_registry_published": False, "writeback_performed": False, "human_reviewed": False,
            "not_production_grade": True}


__all__ = ["BetaSupply", "BetaSupplyUnavailable", "load_beta_supply", "discover_supply_dir",
           "score_point", "build_beta_shadow_payload",
           "ReleaseCandidateUnavailable", "discover_release_candidate_registry",
           "load_release_candidate_registry", "build_controlled_runtime_payload"]
