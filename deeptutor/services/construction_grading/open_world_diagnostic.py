"""Open-world diagnostic runtime (M26, §0.26.2 open-world mode).

When a construction-practice question is NOT resolvable to a canonical bank question (user-pasted,
variant, broad concept, missing authority), the system MUST NOT refuse. It produces a high-quality
*non-formal* diagnosis over the unified ``LubanContextPack`` + retrieval refs, clearly labeled as
``unverified_diagnostic`` / ``needs_review``, and emits a compiler work-order for high-value misses.

Hard guards (master plan §0.26.2):
  * never emits a formal/auto score,
  * never claims an official answer,
  * always carries ``status`` + ``uncertainty_label``,
  * fails CLOSED only for unsafe/off-domain input (those declines are NOT counted as a
    construction refusal); fails OPEN with a useful diagnosis for any construction-related prompt,
  * degrades gracefully: with no live LLM it still answers from a deterministic template over the
    pack, so the refusal rate for construction prompts stays 0 even without model access.

The LLM (when live) only ORGANIZES the diagnosis; ``diagnostic_policy`` from the pack is the
deterministic gate that already forbids official scoring here.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Optional

from deeptutor.services.construction_grading.compiled_context import LubanContextPack

STATUS_DIAGNOSTIC = "unverified_diagnostic"
STATUS_SAFE_DECLINE = "safe_decline_off_domain"

UNCERTAINTY_LOW = "low_confidence"
UNCERTAINTY_MEDIUM = "medium_confidence_retrieval_grounded"

# Minimal deterministic unsafe / clearly-off-domain gate. We bias HARD toward answering: only
# explicit unsafe intent or an obviously empty prompt declines. Everything plausibly about
# construction practice is answered (fail-open).
_UNSAFE_MARKERS = (
    "ignore previous", "jailbreak", "system prompt", "制造炸药", "制作爆炸", "如何自杀",
    "kill", "炸弹配方", "ddos", "弱口令爆破",
)


@dataclass(frozen=True)
class OpenWorldDiagnostic:
    status: str
    uncertainty_label: str
    formal_score_allowed: bool
    official_answer_claimed: bool
    diagnosis: str
    likely_scoring_dimensions: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]
    next_practice: list[str]
    candidate_work_order: dict[str, Any]
    is_construction_refusal: bool
    provider_used: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "uncertainty_label": self.uncertainty_label,
            "formal_score_allowed": self.formal_score_allowed,
            "official_answer_claimed": self.official_answer_claimed,
            "diagnosis": self.diagnosis,
            "likely_scoring_dimensions": self.likely_scoring_dimensions,
            "evidence_refs": self.evidence_refs,
            "next_practice": self.next_practice,
            "candidate_work_order": self.candidate_work_order,
            "is_construction_refusal": self.is_construction_refusal,
            "provider_used": self.provider_used,
            "not_production_grade": True,
            "auto_score": False,
        }

    def to_unified_schema(self) -> dict[str, Any]:
        """Stable runtime contract consumed by the live /api/v1/ws followup surface (M27).

        Maps the diagnostic onto the canonical open-world fields so every surface reads the same
        shape: ``answer`` (non-official diagnosis text), ``diagnostic_status``, ``uncertainty``,
        ``evidence_context`` (retrieval/context refs, never answer keys), ``next_action`` (next
        practice), and ``work_order_if_needed`` (compiler candidate, preview only)."""
        return {
            "answer": self.diagnosis,
            "diagnostic_status": self.status,
            "uncertainty": self.uncertainty_label,
            "evidence_context": self.evidence_refs,
            "likely_scoring_dimensions": self.likely_scoring_dimensions,
            "next_action": self.next_practice,
            "work_order_if_needed": (
                self.candidate_work_order if self.candidate_work_order.get("needed") else None
            ),
            "formal_score_allowed": self.formal_score_allowed,
            "official_answer_claimed": self.official_answer_claimed,
            "is_construction_refusal": self.is_construction_refusal,
            "provider_used": self.provider_used,
        }


def _is_unsafe(prompt: str) -> bool:
    low = prompt.lower()
    return any(marker in low for marker in _UNSAFE_MARKERS)


def _evidence_refs(pack: LubanContextPack) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in pack.source_context.get("retrieval_refs", []):
        refs.append({
            "ref": ref.get("ref"),
            "source_table": ref.get("source_table"),
            "title": ref.get("title"),
            "source_span": ref.get("source_span"),
            "content_hash": ref.get("content_hash"),
            "provenance_kind": "retrieval_only",
            "is_answer_key": False,
        })
    for ref in pack.source_context.get("compiled_source_refs", []):
        refs.append({**ref, "is_answer_key": False})
    return refs


def _template_diagnosis(prompt: str, evidence_refs: list[dict[str, Any]]) -> str:
    head = (
        "这是一个未命中题库的建筑实务问题。以下为非正式诊断（unverified_diagnostic），"
        "不构成官方真题答案，也不计正式分。"
    )
    if evidence_refs:
        titles = "、".join(
            str(r.get("title") or r.get("ref") or "").strip() for r in evidence_refs[:3] if r
        )
        body = f"基于检索到的相关教材/规范片段（{titles}）组织作答思路，请结合具体工程条件核对。"
    else:
        body = "当前未检索到强相关教材/规范证据，诊断置信度较低，建议人工复核或补充上下文。"
    return f"{head}\n问题：{prompt.strip()[:200]}\n{body}"


def _likely_dimensions(pack: LubanContextPack) -> list[dict[str, Any]]:
    # Derive candidate scoring dimensions from any compiled rubric/required terms in the pack;
    # these are LIKELY dimensions, explicitly not signed scoring points.
    dims: list[dict[str, Any]] = []
    for term in pack.rubric_context.get("required_terms", [])[:5]:
        dims.append({"dimension": str(term), "signed": False, "kind": "likely_scoring_dimension"})
    if not dims:
        dims.append({
            "dimension": "关键术语与规范条文是否准确",
            "signed": False,
            "kind": "likely_scoring_dimension",
        })
        dims.append({
            "dimension": "工序/责任/程序是否完整",
            "signed": False,
            "kind": "likely_scoring_dimension",
        })
    return dims


def _parse_provider_json(raw: str) -> dict[str, Any]:
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        return json.loads(raw[start:end])
    except Exception:  # noqa: BLE001 — provider output is untrusted; degrade to template
        return {}


def build_open_world_diagnostic(
    *,
    pack: LubanContextPack,
    student_prompt: str,
    provider: Optional[Callable[..., str]] = None,
    diagnosis_override: str | None = None,
    high_value: bool = True,
) -> OpenWorldDiagnostic:
    """Build a non-refusing, labeled diagnosis.

    ``provider`` is an injected LLM callable returning a JSON string; when absent the diagnosis
    degrades to a deterministic template (still no refusal). ``diagnosis_override`` lets the live
    runtime supply an already-generated natural-language answer (e.g. the FollowupAgent's LLM
    output) so the fat skill only STRUCTURES it (status / uncertainty / evidence / work_order)
    rather than re-calling a model — the wrapper provides the answer, the fat skill labels it."""
    prompt = str(student_prompt or "").strip()

    # Safety / off-domain decline — NOT a construction refusal.
    if not prompt or _is_unsafe(prompt):
        return OpenWorldDiagnostic(
            status=STATUS_SAFE_DECLINE,
            uncertainty_label=UNCERTAINTY_LOW,
            formal_score_allowed=False,
            official_answer_claimed=False,
            diagnosis="该问题超出建筑实务辅导范围或存在安全风险，已安全拒答（不计入建筑实务拒答）。",
            likely_scoring_dimensions=[],
            evidence_refs=[],
            next_practice=[],
            candidate_work_order={"needed": False, "kind": "none", "promote_to_release": False},
            is_construction_refusal=False,
            provider_used="safety_gate",
        )

    # The pack must already forbid official scoring for open-world.
    if pack.official_score_allowed:
        raise ValueError("open-world diagnostic must not run on an official-score-allowed pack")

    evidence_refs = _evidence_refs(pack)
    likely_dims = _likely_dimensions(pack)
    provider_used = "template_degraded"
    diagnosis = _template_diagnosis(prompt, evidence_refs)
    next_practice = [
        "复述本题涉及的核心规范条文与适用条件",
        "用一道同类已编译真题做对照练习",
    ]
    uncertainty = UNCERTAINTY_MEDIUM if evidence_refs else UNCERTAINTY_LOW

    override = str(diagnosis_override or "").strip()
    if override:
        # Live runtime already produced a real natural-language answer; the fat skill only labels it.
        diagnosis = override
        provider_used = "caller_supplied_runtime_llm"
    elif provider is not None:
        try:
            raw = provider(
                system="你是建筑实务诊断助手，只做非正式诊断，不得给出官方真题答案或正式分。你陈述的事实/数字必须可溯源到题面或提供的证据，不得引入题面与证据之外的背景数字。",
                user=json.dumps(
                    {
                        "prompt": prompt,
                        "evidence_refs": evidence_refs,
                        "likely_dimensions": likely_dims,
                    },
                    ensure_ascii=False,
                ),
            )
            parsed = _parse_provider_json(raw)
            if parsed.get("diagnosis"):
                diagnosis = str(parsed["diagnosis"])
                provider_used = "live_llm"
                if isinstance(parsed.get("next_practice"), list) and parsed["next_practice"]:
                    next_practice = [str(x) for x in parsed["next_practice"]][:5]
                if isinstance(parsed.get("likely_scoring_dimensions"), list) and parsed["likely_scoring_dimensions"]:
                    likely_dims = [
                        {"dimension": str(d), "signed": False, "kind": "likely_scoring_dimension"}
                        for d in parsed["likely_scoring_dimensions"]
                    ][:6]
        except Exception:  # noqa: BLE001 — never let a provider failure turn into a refusal
            provider_used = "template_degraded_after_provider_error"

    work_order = {
        "needed": bool(high_value),
        "kind": "open_world_compiler_candidate",
        "reason": "high-value not-in-bank construction prompt; route to compiler candidate",
        "promote_to_release": False,
        "prompt_excerpt": prompt[:160],
        "evidence_ref_count": len(evidence_refs),
    }

    return OpenWorldDiagnostic(
        status=STATUS_DIAGNOSTIC,
        uncertainty_label=uncertainty,
        formal_score_allowed=False,
        official_answer_claimed=False,
        diagnosis=diagnosis,
        likely_scoring_dimensions=likely_dims,
        evidence_refs=evidence_refs,
        next_practice=next_practice,
        candidate_work_order=work_order,
        is_construction_refusal=False,
        provider_used=provider_used,
    )


__all__ = ["OpenWorldDiagnostic", "build_open_world_diagnostic", "STATUS_DIAGNOSTIC"]
