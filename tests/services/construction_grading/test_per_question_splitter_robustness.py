"""TDD for the per-question answer-splitter root-cause fix.

Root cause (verified on real 一建 data, 152 case answers): the splitter's format
model was too narrow + brittle — `^`-anchored headers miss inline-prefixed `【参考答案】：1、`,
strict ascending-from-1 collapses on any miss, literal `\\n` (two chars) is unseen,
and trailing-【解析】/decimal hazards either drop or mis-cut content.

Two invariants this fix must hold (the second was the one the naive fix broke):
  * must-not-mint: every scoring point is a verbatim substring of the (normalized) answer.
  * must-not-DROP: the union of compiled points covers the non-boilerplate answer content;
    if a heuristic can't split safely, it FAILS CLOSED to one blob (never silently drops).

Test cases below encode the confirmed failure modes + the adversarial review's P0-P4.
"""
from __future__ import annotations

import re

from deeptutor.services.construction_grading.per_question_grading_object import (
    compile_per_question_grading_object,
    split_sub_questions,
)


def _points(answer: str) -> list[dict]:
    obj = compile_per_question_grading_object(
        question_id="T", stem="", correct_answer=answer, official_total_score=None,
        textbook_chunks=[], chunk_id="", official_analysis=None, source_path="",
    )
    return [p for sq in obj.get("sub_questions") or [] for p in sq.get("scoring_points") or []]


def _hanzi(text: str) -> str:
    return "".join(re.findall(r"[一-鿿]", text))


# --- core: inline-prefixed first header must not collapse (51% of the bank) ---

def test_inline_prefixed_first_header_splits_not_collapses():
    a = "【参考答案】：1、内容甲。\n\n2、内容乙。\n\n3、内容丙。\n\n4、内容丁。"
    subs = split_sub_questions(a)
    assert len(subs) == 4, f"inline-prefixed 1、 collapsed to {len(subs)}"


def test_literal_backslash_n_is_handled():
    # P2: 24/152 store line breaks as literal two-char \n with zero real newlines;
    # after de-escape the numbered headers land at line start and must split.
    a = "1、答案甲。\\n\\n2、答案乙。\\n\\n3、答案丙。"
    subs = split_sub_questions(a)
    assert len(subs) == 3, f"literal \\n not handled: {len(subs)} subs"


# --- P0: 【解析】 is NOT boilerplate — stripping it deletes real content ---

def test_jiexi_section_content_is_not_dropped():
    # 11 real answers are ~100% 【解析】 body; stripping = total wipeout.
    a = "【解析】1.甲做法不妥。2.乙做法不妥。"
    pts = _points(a)
    assert pts, "answer that is mostly 【解析】 compiled to ZERO points (content dropped)"
    joined = "".join(p.get("atomic_official_slice") or "" for p in pts)
    assert "甲" in joined and "乙" in joined, "real 【解析】 scoring content was dropped"


def test_xuanxiang_fenxi_boilerplate_is_stripped():
    # 【选项分析】 IS boilerplate (0/152 real content) — must not pollute points/terms.
    a = "1、答案甲。\n\n2、答案乙。\n\n【选项分析】\n本题为案例题，无选项。"
    pts = _points(a)
    joined = "".join(p.get("atomic_official_slice") or "" for p in pts)
    assert "选项分析" not in joined, "【选项分析】 boilerplate leaked into a scoring point"


# --- P1: decimals / dimensions must never be read as sub-question headers ---

def test_decimal_numbers_are_not_headers():
    # 27.2 and 32.7 form an ascending pair but are 金额, not headers.
    a = "(1) 工期索赔不成立，理由是C为非关键工作。C工作索赔费用27.2万合理。E工作索赔32.7万费用不合理。"
    subs = split_sub_questions(a)
    # must stay ONE sub-question; the leading judgment must survive (must-not-drop)
    joined = "".join(b for _, b in subs)
    assert "工期索赔不成立" in joined, "leading judgment dropped by decimal mis-header"


def test_calculation_not_shredded_at_decimal_point():
    a = "材料费1.88万元，利润18.26万元，合计20.14万元。"
    subs = split_sub_questions(a)
    joined = "".join(b for _, b in subs)
    assert _hanzi(joined) == _hanzi(a), "calculation content lost when split at decimals"


# --- must-not-DROP: coverage guard — union of points covers non-boilerplate content ---

def test_no_content_dropped_must_not_drop_invariant():
    samples = [
        "【参考答案】：1、内容甲乙丙。\n\n2、（1）数值二十二。（2）时差为零。\n\n3、判断合理。\n\n4、否，索赔不成立理由如下。",
        "(1) 工期索赔不成立。理由：C为非关键工作。(2) 费用索赔成立。理由：非承包商原因。",
        "【解析】1.甲做法不妥，应改正。2.乙做法不妥，应改正。",
    ]
    for a in samples:
        pts = _points(a)
        covered = _hanzi("".join(p.get("atomic_official_slice") or "" for p in pts))
        # the must-not-drop unit is CONTENT, excluding framing the normalizer legitimately
        # removes (leading 【参考答案】 label + trailing 【选项分析】 boilerplate).
        body = re.sub(r"^\s*【?\s*(?:参考答案|答案)\s*】?\s*[:：]?\s*", "", a)
        body = re.sub(r"【\s*选项分析\s*】.*$", "", body, flags=re.S)
        want = _hanzi(body)
        missing = [ch for ch in set(want) if ch not in covered]
        assert len(missing) <= 2, f"must-not-drop violated for {a[:30]}: missing {missing[:8]}"


# --- must-not-mint preserved: every slice verbatim of the answer (de-escaped) ---

def test_every_point_verbatim_substring_after_fix():
    for a in [
        "【参考答案】：1、甲。\n\n2、乙。\n\n3、丙。",
        "问题1\\n甲做法。\\n问题2\\n乙做法。",
        "错误之一：泛水高度不足。正确做法：泛水高度至少250mm。错误之二：阴阳角直角。正确做法：做成圆弧。",
    ]:
        canon = a.replace("\\n", "\n")
        for p in _points(a):
            s = p.get("atomic_official_slice") or ""
            assert s in canon, f"slice not verbatim of normalized answer: {s[:40]!r}"


# --- flaw-enumeration marker vocabulary: 错误之N must split like 不妥之处 ---

def test_cuowu_zhi_n_flaw_enumeration_splits():
    a = ("错误之一：泛水高度为200mm。正确做法：泛水高度至少为250mm。"
         "错误之二：阴阳角基层为直角。正确做法：做成45度角或圆弧。"
         "错误之三：女儿墙泛水没做附加层。正确做法：增设附加层。")
    pts = _points(a)
    assert len(pts) >= 3, f"错误之一/二/三 under-split to {len(pts)} points"


# --- distinctive terms must not carry markup artifacts, but keep dimension terms ---

def test_distinctive_terms_have_no_markup_artifacts():
    a = "1、安全生产费用包括安全防护用品。\n\n【选项分析】\n本题为案例题。"
    for p in _points(a):
        for t in p.get("term_provenance") or []:
            term = t.get("term") if isinstance(t, dict) else str(t)
            assert "【" not in (term or ""), f"markup artifact in term: {term!r}"
            assert (term or "").strip() not in {"", "\\n", "\n"}, f"whitespace artifact term: {term!r}"
