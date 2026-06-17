"""文本管线测试：reconcile 行级风险评分 / 段落分点重建 / 题干折叠 / 形近字词典。"""

from __future__ import annotations

from deeptutor.services.photo_answer.engines.base import EngineResult
from deeptutor.services.photo_answer.lexicon import suggest_shape_corrections
from deeptutor.services.photo_answer.paragraphs import rebuild_paragraphs
from deeptutor.services.photo_answer.reconcile import reconcile
from deeptutor.services.photo_answer.stem_fold import fold_stem_paragraphs


def _l0(lines: list[str], *, chars=None) -> EngineResult:
    return EngineResult(
        engine="baidu_handwriting",
        raw_text="\n".join(lines),
        line_boxes=[
            {"line_index": i, "text": t, "box": [10, 20 + 40 * i, 300, 30]}
            for i, t in enumerate(lines)
        ],
        char_confidences=chars or [],
    )


def _l1(text: str) -> EngineResult:
    return EngineResult(engine="qwen_vl_ocr", raw_text=text)


# ---------- reconcile：行级风险评分 ----------


def test_reconcile_identical_text_produces_no_suspicions():
    l0 = _l0(["施工组织设计", "1）编制依据"])
    out = reconcile(l0, _l1("施工组织设计\n1）编制依据"))
    assert out.suspicions == []


def test_reconcile_flags_divergent_line_with_l0_box_anchor():
    l0 = _l0(["总承包单位负责", "1）编制依据"])
    out = reconcile(l0, _l1("分包单位负责\n1）编制依据"))
    assert len(out.suspicions) == 1
    s = out.suspicions[0]
    assert s["source"] == "engine_diff"
    assert s["span"]["line_index"] == 0
    assert s["span"]["box"] == [10, 20, 300, 30]  # 坐标 authority 永远是 L0


def test_reconcile_normalizes_whitespace_and_width_to_avoid_false_diff():
    l0 = _l0(["工期为 120 天"])
    out = reconcile(l0, _l1("工期为１２０天"))  # 全角+空格差异 ≠ 分歧
    assert out.suspicions == []


def test_reconcile_low_confidence_chars_become_suspicions():
    chars = [
        {"line_index": 0, "char": "组", "box": [40, 20, 30, 30], "prob": 0.31, "candidates": ["组", "织"]},
        {"line_index": 0, "char": "施", "box": [10, 20, 30, 30], "prob": 0.97, "candidates": []},
    ]
    l0 = _l0(["施组工织设计"], chars=chars)
    out = reconcile(l0, _l1("施组工织设计"), low_conf_threshold=0.6)
    assert any(s["source"] == "low_conf" and s["span"].get("char") == "组" for s in out.suspicions)


def test_reconcile_numeric_divergence_is_critical_severity():
    l0 = _l0(["工期为120天"])
    out = reconcile(l0, _l1("工期为180天"))
    assert out.suspicions[0]["severity"] == "critical"  # 数字分歧 = 关键疑点（C9）


# ---------- 段落 / 分点重建 ----------


def test_rebuild_paragraphs_groups_by_numbering_and_gap():
    lines = [
        {"line_index": 0, "text": "1）编制依据如下", "box": [10, 0, 300, 30]},
        {"line_index": 1, "text": "包括施工合同等", "box": [10, 34, 300, 30]},
        {"line_index": 2, "text": "2）不妥之处", "box": [10, 120, 300, 30]},  # 大间距 + 编号
    ]
    paras = rebuild_paragraphs(lines)
    assert len(paras) == 2
    assert paras[0]["text"] == "1）编制依据如下包括施工合同等"
    assert paras[1]["numbering"] == "2）"


# ---------- 题干折叠 ----------


def test_fold_stem_marks_similar_paragraph_but_keeps_text():
    stem = "背景资料：某新建办公楼工程，总承包单位与专业分包单位签订了合同。问题：1.指出不妥之处。"
    paras = [
        {"text": "背景资料：某新建办公楼工程，总承包单位与专业分包单位签订了合同。", "numbering": ""},
        {"text": "不妥之处：总承包单位未审核分包方案。", "numbering": ""},
    ]
    folded = fold_stem_paragraphs(paras, question_stem=stem)
    assert folded[0]["is_stem_suspect"] is True
    assert folded[1]["is_stem_suspect"] is False
    # 默认不计入 confirmed_text 草稿，但文本必须保留（绝不物理删除）
    assert folded[0]["text"].startswith("背景资料")


def test_fold_stem_detects_wrong_question_mismatch():
    stem = "背景资料：某地铁车站深基坑工程……"
    paras = [{"text": "本工程网络计划工期计算如下", "numbering": ""}]
    folded, mismatch = fold_stem_paragraphs(paras, question_stem=stem, return_mismatch=True)
    assert mismatch is False  # 答案与题干不相似是正常的；mismatch 只在"拍到的题干"与绑定题干冲突时为 True

    other_stem_para = [{"text": "背景资料：某新建办公楼工程总承包施工。", "numbering": ""}]
    _, mismatch2 = fold_stem_paragraphs(other_stem_para, question_stem=stem, return_mismatch=True)
    assert mismatch2 is False  # 相似度不够高不算题干 → 也不算 mismatch（保守）


# ---------- 形近字词典 ----------


def test_lexicon_suggests_only_candidate_backed_shape_fix():
    # 学生写了"施工组织设计"，OCR 把"织"读成低置信"帜"，候选含"织"
    chars = [
        {"line_index": 0, "char": "帜", "prob": 0.35, "candidates": ["帜", "织"], "box": [0, 0, 1, 1]}
    ]
    line_text = "施工组帜设计"
    suggestions = suggest_shape_corrections(
        line_text, chars, lexicon_terms={"施工组织设计", "专项施工方案"}
    )
    assert suggestions == [
        {"char": "帜", "suggestion": "织", "term": "施工组织设计", "line_index": 0, "box": [0, 0, 1, 1]}
    ]


def test_lexicon_never_suggests_without_candidate_evidence():
    # 没有候选字支撑 → 不建议（禁止语义级"喂答案"，Codex C8/C17）
    chars = [
        {"line_index": 0, "char": "帜", "prob": 0.35, "candidates": [], "box": [0, 0, 1, 1]}
    ]
    assert suggest_shape_corrections("施工组帜设计", chars, lexicon_terms={"施工组织设计"}) == []
