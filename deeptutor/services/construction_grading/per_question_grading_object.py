"""Deterministic compiler: official exam answers -> per-question grading objects.

This is the fat skill behind ``scripts/run_luban_per_question_grading_object_compile.py``.
It compiles a real case-study exam question into a single typed grading object
(``schema_id = luban_per_question_grading_object.v1``) whose every scoring point is a
**verbatim slice of the official reference answer** (``correct_answer``). It is purely
deterministic — no LLM, no network, no DB writes — so it can never invent a scoring
point the official answer did not write.

Single-authority hard rules enforced here (source-locked, mirrors
``docs/plan/鲁班knowql/typed_object_requirements_by_question_type.md``):

1. **A — official answer verbatim**: every atomic point is cut from ``correct_answer`` by
   the answer's own structure (问题N / ①② / （1）（2） / equation lines) and MUST be a
   substring of ``correct_answer`` (``substring containment`` assertion). Nothing is
   generated, nothing the official answer omitted is added.
2. **B — textbook citation (supporting, not authority)**: each point's distinctive terms
   are anchored against textbook chunks via ``_valid_textbook_anchor`` (term must appear in
   ``content_markdown``) with a ``span_hash`` over the cited chunk span. A point that hits no
   chunk is marked ``unsourced`` — never fabricated.
3. **Per-point score = null** + ``score_authority = "pending_calibration_not_official"``.
   The official source only gives a whole-question total; the compiler NEVER mints a
   per-point split. ``official_total_score`` = the official number.
4. Every field carries an ``authority_source`` tag
   (``official_answer_verbatim`` / ``textbook_cited`` / ``owner`` / ``pending_calibration``).
   The schema sets ``official_score_allowed: const False`` + ``forbidden_properties`` so the
   object cannot structurally declare itself official truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash
from deeptutor.services.source_compiler.scoring_point_asset_compiler import (
    _valid_textbook_anchor,
    normalize_for_match,
)

SCHEMA_ID = "luban_per_question_grading_object.v1"
COMPILER = "scripts/run_luban_per_question_grading_object_compile.py"

# authority_source tags (A / B / C / pending)
A_OFFICIAL = "official_answer_verbatim"
B_TEXTBOOK = "textbook_cited"
C_OWNER = "owner"
PENDING = "pending_calibration"

PENDING_SCORE_AUTHORITY = "pending_calibration_not_official"

PER_QUESTION_GRADING_OBJECT_V1_SCHEMA: dict[str, Any] = {
    "schema_id": SCHEMA_ID,
    "type": "object",
    "required": [
        "schema_id",
        "question_id",
        "official_total_score",
        "official_total_score_authority",
        "sub_questions",
    ],
    "properties": {
        "schema_id": {"const": SCHEMA_ID},
        "question_id": {"type": "string"},
        "official_total_score": {"type": "number"},
        "official_total_score_authority": {"const": A_OFFICIAL},
        "sub_questions": {"type": "array"},
        # Structural lock: the object can never declare itself official truth.
        "official_score_allowed": {"const": False},
        "canonical_write_allowed": {"const": False},
    },
    "forbidden_properties": [
        "controlled_default",
        "canonical_truth_written",
        "minted_per_point_score",
    ],
}

# Sub-question splitting: the answer's own "问题N" or leading "N." numbering.
_QUESTION_HEADER_RE = re.compile(r"(?m)^\s*(?:问题)?(\d{1,2})\s*[.．、:：)）]")
# Atomic point markers inside one sub-question answer.
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
_PAREN_RE = re.compile(r"[（(](\d{1,2})[）)]")
# flaw_correction halves.
_FLAW_RE = re.compile(r"不妥之处[：:]\s*(?P<flaw>.+?)(?=正确做法[：:])", re.S)
_CORRECTION_RE = re.compile(r"正确做法[：:]\s*(?P<correction>.+)", re.S)
# enumeration lead-ins (set recall).
_ENUM_LEAD_RE = re.compile(r"(?:还包括|还有哪些|包括|还应|内容还有)[：:]?")
# a paragraph that opens its own enumeration tail (e.g. "记录内容还包括：…") — a
# deterministic boundary from the answer's own wording, split off as its own segment.
_ENUM_TAIL_RE = re.compile(r"(?m)^[^\n]*?(?:还包括|内容还有|还有哪些)[：:]")
# equation line (calculation).
_EQUATION_RE = re.compile(r"[=＝]")
_EXCEPTION_RE = re.compile(r"除外")
# split candidate anchor terms on list separators, sentence punctuation, newlines, and
# leading list markers — so a distinctive term stays short, not a whole composite span.
_TERM_SPLIT_RE = re.compile(
    r"[、；;，,（）()。！？!?：:\n\r\t ]+|（\d+）|\(\d+\)|[①②③④⑤⑥⑦⑧⑨⑩]|不妥之处|正确做法"
)
# max characters for a distinctive anchor term (longer = a clause, not a term).
_MAX_TERM_LEN = 12

# noise tokens that are not distinctive scoring terms worth anchoring
_TERM_STOP = {"的", "包括", "内容", "还有", "哪些", "及", "和", "等"}


def _strip_marker(segment: str) -> str:
    """Drop a leading list marker (①, （1）, 1.) without touching the answer body."""
    text = segment.strip()
    text = re.sub(rf"^[{_CIRCLED}]\s*", "", text)
    text = re.sub(r"^[（(]\d{1,2}[）)]\s*", "", text)
    text = re.sub(r"^\d{1,2}\s*[.．、:：]\s*", "", text)
    return text.strip()


def _assert_verbatim(slice_text: str, full_answer: str, label: str) -> None:
    """Hard gate: an atomic point MUST be a substring of the official answer."""
    if not slice_text:
        raise ValueError(f"empty official slice for {label}")
    if slice_text not in full_answer:
        raise ValueError(f"{label} is not a verbatim substring of correct_answer")


def split_sub_questions(correct_answer: str) -> list[tuple[int, str]]:
    """Cut ``correct_answer`` into (sub_no, body) by its own ascending numbering.

    Each body is a verbatim (stripped) substring of the answer. If the answer has no
    ascending top-level numbering, the whole answer is one implicit sub-question.
    """
    headers = [(m.start(), int(m.group(1))) for m in _QUESTION_HEADER_RE.finditer(correct_answer)]
    starts: list[tuple[int, int]] = []
    expected = 1
    for pos, num in headers:
        if num == expected:
            starts.append((pos, num))
            expected += 1
    if len(starts) < 2:
        return [(1, correct_answer.strip())]
    out: list[tuple[int, str]] = []
    for idx, (pos, num) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(correct_answer)
        body = correct_answer[pos:end].strip()
        out.append((num, body))
    return out


def _split_enum_tail(inner: str) -> tuple[str, str | None]:
    """Split a trailing "…还包括：…" enumeration off as its own segment.

    The enumeration tail is a distinct list sub-point glued into the same blob; it is
    cut at the start of its own line so it never bleeds into the preceding point. Both
    halves remain verbatim substrings of ``inner``.
    """
    matches = list(_ENUM_TAIL_RE.finditer(inner))
    if not matches:
        return inner, None
    cut = matches[-1].start()
    head = inner[:cut].strip()
    tail = inner[cut:].strip()
    if not head:
        return inner, None
    return head, (tail or None)


def _split_atomic_segments(body: str) -> list[str]:
    """Cut one sub-question body into atomic point segments by ①② or （1）（2）."""
    # strip a leading "问题N" / "N." header off the body first.
    inner = re.sub(r"(?s)^\s*(?:问题)?\d{1,2}\s*[.．、:：)）]\s*", "", body).strip()
    head, enum_tail = _split_enum_tail(inner)

    # Try （1）（2） markers FIRST — they are unambiguous list markers. Circled
    # numerals (①②③) are checked only at line start because mid-line ①→②→③ is
    # network-path / node notation, not a point marker (same rule as the proven
    # build_luban_m35_official_answer_keys splitter).
    paren = [
        (m.start(), int(m.group(1)))
        for m in _PAREN_RE.finditer(head)
        if (m.start() == 0 or head[m.start() - 1] not in "“”\"'「『")
    ]
    segs = _ascending_segments(head, paren)
    if segs is None:
        circled = [
            (m.start(1), _CIRCLED.index(m.group(1)) + 1)
            for m in re.finditer(rf"(?m)^[ \t]*([{_CIRCLED}])", head)
        ]
        segs = _ascending_segments(head, circled)
    if segs is None:
        segs = [head] if head else []
    if enum_tail:
        segs.append(enum_tail)
    return [s for s in segs if s]


def _ascending_segments(text: str, positions: list[tuple[int, int]]) -> list[str] | None:
    starts: list[int] = []
    expected = 1
    for pos, num in positions:
        if num == expected:
            starts.append(pos)
            expected += 1
    if len(starts) < 2:
        return None
    segments: list[str] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
        segments.append(text[start:end].strip())
    return segments


def classify_sub_type(body: str) -> str:
    """Deterministic sub-type from the answer's own wording (no LLM)."""
    if "不妥之处" in body and "正确做法" in body:
        return "flaw_correction"
    if _EXCEPTION_RE.search(body) and "分包" in body:
        return "exceptions"
    if _EQUATION_RE.search(body):
        return "calculation"
    if _ENUM_LEAD_RE.search(body):
        return "enumeration"
    return "free_text_point"


def _distinctive_terms(text: str) -> list[str]:
    """Pull short distinctive anchor terms (2..12 chars) from a verbatim slice.

    Long clauses are dropped rather than anchored, so the textbook-anchor accounting
    reflects real term-level hits instead of giant composite spans that never match.
    """
    pieces = [p.strip() for p in _TERM_SPLIT_RE.split(text) if p and p.strip()]
    terms: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        norm = normalize_for_match(piece)
        if len(norm) < 2 or len(norm) > _MAX_TERM_LEN or piece in _TERM_STOP:
            continue
        if norm in seen:
            continue
        seen.add(norm)
        terms.append(piece)
    return terms


def _anchor_term(term: str, chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """B authority: return the first textbook chunk whose content contains ``term``."""
    for chunk in chunks:
        if _valid_textbook_anchor(term, chunk):
            content = str(chunk.get("content_markdown") or "")
            return {
                "term": term,
                "chunk_id": str(chunk.get("chunk_id") or ""),
                "span_hash": source_span_hash(content),
                "anchor_verified": True,
                "authority_source": B_TEXTBOOK,
            }
    return None


def _build_term_provenance(
    text: str, textbook_chunks: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, int]:
    """Anchor each distinctive term; unsourced terms are honestly flagged, not faked."""
    provenance: list[dict[str, Any]] = []
    hit = 0
    total = 0
    for term in _distinctive_terms(text):
        total += 1
        anchored = _anchor_term(term, textbook_chunks)
        if anchored is not None:
            hit += 1
            provenance.append(anchored)
        else:
            provenance.append(
                {
                    "term": term,
                    "chunk_id": None,
                    "span_hash": None,
                    "anchor_verified": False,
                    "authority_source": "unsourced",
                }
            )
    return provenance, hit, total


@dataclass(frozen=True)
class ScoringPoint:
    point_id: str
    sub_type: str
    atomic_official_slice: str
    authority_source: str
    span_hash: str
    score: None
    score_authority: str
    term_provenance: list[dict[str, Any]] = field(default_factory=list)
    flaw_span: str | None = None
    correction_span: str | None = None
    pairing: str | None = None
    base_rule: str | None = None
    exception_items: list[str] = field(default_factory=list)
    formula_step: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "point_id": self.point_id,
            "sub_type": self.sub_type,
            "atomic_official_slice": self.atomic_official_slice,
            "authority_source": self.authority_source,
            "span_hash": self.span_hash,
            "score": self.score,
            "score_authority": self.score_authority,
            "term_provenance": list(self.term_provenance),
        }
        if self.flaw_span is not None:
            out["flaw_span"] = self.flaw_span
            out["correction_span"] = self.correction_span
            out["pairing"] = self.pairing
        if self.base_rule is not None:
            out["base_rule"] = self.base_rule
            out["exception_items"] = list(self.exception_items)
        if self.formula_step is not None:
            out["formula_step"] = self.formula_step
        return out


def _point_id(question_id: str, sub_no: int, ordinal: int, slice_text: str) -> str:
    seed = f"{question_id}|S{sub_no:02d}|P{ordinal:02d}|{normalize_for_match(slice_text)[:24]}"
    return "sp_" + source_span_hash(seed)[:20]


def _compile_flaw_correction(
    *, slice_text: str, full_answer: str, point_id: str, term_prov: list[dict[str, Any]]
) -> ScoringPoint:
    flaw_m = _FLAW_RE.search(slice_text)
    corr_m = _CORRECTION_RE.search(slice_text)
    flaw = _strip_marker(flaw_m.group("flaw")).rstrip("。；;") if flaw_m else None
    correction = _strip_marker(corr_m.group("correction")).rstrip("。；;") if corr_m else None
    if flaw:
        _assert_verbatim(flaw, full_answer, f"{point_id}.flaw_span")
    if correction:
        _assert_verbatim(correction, full_answer, f"{point_id}.correction_span")
    return ScoringPoint(
        point_id=point_id,
        sub_type="flaw_correction",
        atomic_official_slice=slice_text,
        authority_source=A_OFFICIAL,
        span_hash=source_span_hash(slice_text),
        score=None,
        score_authority=PENDING_SCORE_AUTHORITY,
        term_provenance=term_prov,
        flaw_span=flaw,
        correction_span=correction,
        pairing="flaw_AND_correction_both_required",
    )


def _compile_exceptions(
    *, slice_text: str, full_answer: str, point_id: str, term_prov: list[dict[str, Any]]
) -> ScoringPoint:
    parts = slice_text.split("，")
    exception_items = [p.strip().rstrip("。；;") for p in parts if "除外" in p]
    base_rule = slice_text
    if exception_items:
        head = slice_text.split(exception_items[0])[0].rstrip("，,").strip()
        if head:
            base_rule = head
    return ScoringPoint(
        point_id=point_id,
        sub_type="exceptions",
        atomic_official_slice=slice_text,
        authority_source=A_OFFICIAL,
        span_hash=source_span_hash(slice_text),
        score=None,
        score_authority=PENDING_SCORE_AUTHORITY,
        term_provenance=term_prov,
        base_rule=base_rule,
        exception_items=exception_items,
    )


def _compile_calculation(
    *, slice_text: str, point_id: str, term_prov: list[dict[str, Any]]
) -> ScoringPoint:
    eq = slice_text.split("=")[-1] if "=" in slice_text else slice_text.split("＝")[-1]
    lhs = slice_text.rsplit("=", 1)[0] if "=" in slice_text else slice_text.rsplit("＝", 1)[0]
    formula_step = {
        "expression": lhs.split("：")[-1].strip(),
        "expected_value_literal": eq.strip().rstrip("。；;"),
        "verification_mode": "deterministic_recalculation_required",
        "authority_source": A_OFFICIAL,
    }
    return ScoringPoint(
        point_id=point_id,
        sub_type="calculation",
        atomic_official_slice=slice_text,
        authority_source=A_OFFICIAL,
        span_hash=source_span_hash(slice_text),
        score=None,
        score_authority=PENDING_SCORE_AUTHORITY,
        term_provenance=term_prov,
        formula_step=formula_step,
    )


def _compile_generic(
    *, slice_text: str, sub_type: str, point_id: str, term_prov: list[dict[str, Any]]
) -> ScoringPoint:
    return ScoringPoint(
        point_id=point_id,
        sub_type=sub_type,
        atomic_official_slice=slice_text,
        authority_source=A_OFFICIAL,
        span_hash=source_span_hash(slice_text),
        score=None,
        score_authority=PENDING_SCORE_AUTHORITY,
        term_provenance=term_prov,
    )


def compile_sub_question(
    *,
    question_id: str,
    sub_no: int,
    body: str,
    full_answer: str,
    textbook_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compile one sub-question body into typed scoring points (all verbatim from A)."""
    sub_type = classify_sub_type(body)
    segments = _split_atomic_segments(body)
    points: list[dict[str, Any]] = []
    anchor_hit = 0
    anchor_total = 0
    for ordinal, raw_seg in enumerate(segments, start=1):
        slice_text = raw_seg.strip()
        if not slice_text:
            continue
        _assert_verbatim(slice_text, full_answer, f"{question_id}.S{sub_no}.P{ordinal}")
        seg_type = classify_sub_type(slice_text)
        # A segment is typed by its OWN content. Only the enumeration family is
        # inherited onto bare list items — structural types (flaw_correction /
        # exceptions / calculation) must be evidenced per segment, never claimed
        # for a segment whose own text carries no such structure.
        if seg_type == "free_text_point" and sub_type == "enumeration":
            seg_type = "enumeration"
        term_prov, hit, total = _build_term_provenance(slice_text, textbook_chunks)
        anchor_hit += hit
        anchor_total += total
        point_id = _point_id(question_id, sub_no, ordinal, slice_text)
        if seg_type == "flaw_correction":
            point = _compile_flaw_correction(
                slice_text=slice_text,
                full_answer=full_answer,
                point_id=point_id,
                term_prov=term_prov,
            )
        elif seg_type == "exceptions":
            point = _compile_exceptions(
                slice_text=slice_text,
                full_answer=full_answer,
                point_id=point_id,
                term_prov=term_prov,
            )
        elif seg_type == "calculation":
            point = _compile_calculation(
                slice_text=slice_text, point_id=point_id, term_prov=term_prov
            )
        else:
            point = _compile_generic(
                slice_text=slice_text,
                sub_type=seg_type,
                point_id=point_id,
                term_prov=term_prov,
            )
        points.append(point.to_dict())
    return {
        "sub_no": sub_no,
        "sub_type": sub_type,
        "official_sub_answer_verbatim": body,
        "official_sub_answer_authority": A_OFFICIAL,
        "scoring_points": points,
        "textbook_anchor_hit": anchor_hit,
        "textbook_anchor_total": anchor_total,
    }


def compile_per_question_grading_object(
    *,
    question_id: str,
    stem: str,
    correct_answer: str,
    official_total_score: float | None,
    textbook_chunks: list[dict[str, Any]],
    chunk_id: str = "",
    official_analysis: str | None = None,
    source_path: str = "",
) -> dict[str, Any]:
    """Compile one real case-study question into a per-question grading object.

    Deterministic and authority-locked: every scoring point is a verbatim slice of
    ``correct_answer`` (A), textbook terms are supporting citations (B) or honestly
    ``unsourced``, per-point scores are null + pending, total is the official number.
    """
    sub_bodies = split_sub_questions(correct_answer)
    sub_objects = [
        compile_sub_question(
            question_id=question_id,
            sub_no=sub_no,
            body=body,
            full_answer=correct_answer,
            textbook_chunks=textbook_chunks,
        )
        for sub_no, body in sub_bodies
    ]
    point_count = sum(len(s["scoring_points"]) for s in sub_objects)
    anchor_hit = sum(s["textbook_anchor_hit"] for s in sub_objects)
    anchor_total = sum(s["textbook_anchor_total"] for s in sub_objects)
    return {
        "schema_id": SCHEMA_ID,
        "compiler": COMPILER,
        "extraction": "deterministic_no_llm",
        "question_id": question_id,
        "chunk_id": chunk_id,
        "source_path": source_path,
        "stem": stem,
        "official_total_score": official_total_score,
        "official_total_score_authority": A_OFFICIAL,
        "official_analysis": official_analysis,
        "official_analysis_authority": C_OWNER if official_analysis else None,
        "sub_questions": sub_objects,
        "scoring_point_count": point_count,
        "textbook_anchor_hit": anchor_hit,
        "textbook_anchor_total": anchor_total,
        "textbook_anchor_hit_rate": (anchor_hit / anchor_total) if anchor_total else None,
        # Structural single-authority locks (mirror rich_leaf schema).
        "official_score_allowed": False,
        "canonical_write_allowed": False,
        "per_point_score_authority": PENDING_SCORE_AUTHORITY,
    }


def validate_per_question_grading_object(obj: dict[str, Any]) -> list[str]:
    """Return blockers (empty = ok). Enforces the single-authority hard rules."""
    blockers: list[str] = []
    if obj.get("schema_id") != SCHEMA_ID:
        blockers.append("schema_id_mismatch")
    for forbidden in PER_QUESTION_GRADING_OBJECT_V1_SCHEMA["forbidden_properties"]:
        if forbidden in obj:
            blockers.append(f"forbidden_property:{forbidden}")
    if obj.get("official_score_allowed") is not False:
        blockers.append("official_score_allowed_must_be_false")
    if obj.get("official_total_score_authority") != A_OFFICIAL:
        blockers.append("total_score_authority_not_official")
    full_answer_slices: list[str] = []
    for sub in obj.get("sub_questions") or []:
        for point in sub.get("scoring_points") or []:
            if point.get("score") is not None:
                blockers.append(f"per_point_score_minted:{point.get('point_id')}")
            if point.get("score_authority") != PENDING_SCORE_AUTHORITY:
                blockers.append(f"per_point_score_authority_wrong:{point.get('point_id')}")
            if point.get("authority_source") != A_OFFICIAL:
                blockers.append(f"point_not_official_authority:{point.get('point_id')}")
            slice_text = str(point.get("atomic_official_slice") or "")
            expected_hash = source_span_hash(slice_text)
            if point.get("span_hash") != expected_hash:
                blockers.append(f"span_hash_mismatch:{point.get('point_id')}")
            full_answer_slices.append(slice_text)
            for prov in point.get("term_provenance") or []:
                if prov.get("anchor_verified") is False and prov.get("chunk_id") is not None:
                    blockers.append(f"unsourced_term_must_have_null_chunk:{point.get('point_id')}")
    return blockers


def render_markdown(obj: dict[str, Any]) -> str:
    """Human-readable rendering: stem -> official answer -> per-point slices -> total."""
    lines: list[str] = []
    qid = obj.get("question_id")
    lines.append(f"# 每题判分对象 · {qid}")
    lines.append("")
    lines.append(f"- schema: `{obj.get('schema_id')}`  ·  编译: `{obj.get('extraction')}`")
    total = obj.get("official_total_score")
    lines.append(f"- **整题总分(官方权威 A): {total} 分**")
    rate = obj.get("textbook_anchor_hit_rate")
    rate_str = f"{rate:.0%}" if isinstance(rate, (int, float)) else "—"
    lines.append(
        f"- 采分点数: {obj.get('scoring_point_count')}  ·  教材依据命中率(B 支撑): "
        f"{obj.get('textbook_anchor_hit')}/{obj.get('textbook_anchor_total')} ({rate_str})"
    )
    lines.append(f"- 逐点分: 全部 null · `{obj.get('per_point_score_authority')}`（官方只给整题总分，编译期不自造分摊）")
    lines.append("")
    lines.append("## 题干（官方原文）")
    lines.append("")
    lines.append("> " + str(obj.get("stem") or "").replace("\n", "\n> "))
    lines.append("")
    for sub in obj.get("sub_questions") or []:
        lines.append(f"## 小问 {sub.get('sub_no')} · 子题型 `{sub.get('sub_type')}`")
        lines.append("")
        lines.append("**官方参考答案（权威 A，逐字）:**")
        lines.append("")
        lines.append("> " + str(sub.get("official_sub_answer_verbatim") or "").replace("\n", "\n> "))
        lines.append("")
        lines.append("**切出的采分点（每个都是官方答案逐字子串）:**")
        lines.append("")
        for idx, point in enumerate(sub.get("scoring_points") or [], start=1):
            lines.append(f"### 采分点 {idx} · `{point.get('sub_type')}` · `{point.get('point_id')}`")
            lines.append(f"- [官方逐字 A] {point.get('atomic_official_slice')}")
            if point.get("flaw_span") is not None:
                lines.append(f"  - 不妥之处: {point.get('flaw_span')}")
                lines.append(f"  - 正确做法: {point.get('correction_span')}")
                lines.append(f"  - 配对规则: `{point.get('pairing')}`")
            if point.get("base_rule") is not None:
                lines.append(f"  - 主规则: {point.get('base_rule')}")
                lines.append(f"  - 除外项: {point.get('exception_items')}")
            if point.get("formula_step") is not None:
                fs = point["formula_step"]
                lines.append(f"  - 公式: `{fs.get('expression')}` = `{fs.get('expected_value_literal')}`（确定性重算）")
            anchors = point.get("term_provenance") or []
            for prov in anchors:
                if prov.get("anchor_verified"):
                    lines.append(
                        f"  - [教材依据 B] 术语「{prov.get('term')}」命中 chunk `{prov.get('chunk_id')}` "
                        f"(span_hash `{str(prov.get('span_hash'))[:12]}…`)"
                    )
                else:
                    lines.append(f"  - [教材依据 B] 术语「{prov.get('term')}」**unsourced**（未命中教材，不伪造）")
            lines.append(f"  - [分值] null · `{point.get('score_authority')}`（候选，待标定，非官方）")
            lines.append("")
    lines.append("---")
    lines.append(f"**整题总分: {total} 分（官方权威 A，逐点分不自造）**")
    lines.append("")
    return "\n".join(lines)
