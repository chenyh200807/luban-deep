"""Content-truth verification gate (② reachability/consumption — verification 半边).

本周满意度 eval 揭示新主病：bot 编造规范条文号/版本/数值(grounding 准确率 84%→73%，
25 条编造：GB50016"2019版"不存在 / 平屋面坡度≤18%应≤10% / 自造"题库权威记录全国统一")。
根因(专家 C 真码确诊)：规范源 ``standard`` 已接进检索，但**消费侧无结构闸**——唯一反编造
机制是 ``grounding.py`` 注入的软约束(docstring 自认"必要不充分")，没有任何结构强制把 bot
写出的 GB/JGJ 条文号去本轮 KB ``standard`` 召回核一遍。``grep verify.*clause`` = 0 命中。

这里 TDD 钉死 post-gen 结构核验闸的**确定性行为**(eval-design：判官/异源不可信，确定性断言
作主 ground truth)：

- one fact: bot 给出的规范条文号/版本，必须能在本轮 standard 召回证据里核到；核不到就不能当
  "规范依据"输出(降级"无法核到原文，仅给通用判断方向")，绝不现编。
- one authority: 规范真值 = 本轮 standard 召回证据(已接检索)，不新建第二 authority。
- 单一汇点 fail-closed：regex 只**抽取** claim，真值由 standard 召回证据裁决；regex 不承担理解。
- 防过矫正：无规范编号的普通教学/闲聊**零影响**(不动)；编号已核到→放行；不 nuke 正文(append
  诚实 caveat)，不回落 V0([[v1-grading-must-be-open-world-nexus-not-lookup]])。
- 核不到=诚实说不确定，是**正确行为**(owner 拍板 trade-off：辅导产品信任 > 自信编造)。
"""

from __future__ import annotations

from deeptutor.tutorbot.teaching_modes import (
    content_truth_guard_response,
    extract_standard_clause_claims,
)

# A piece of this-turn standard recall evidence (what search_standard_chunks returned).
RECALL_WITH_GB50016 = (
    "《建筑设计防火规范》GB 50016-2014（2018年版）第6.7.3条规定，防火墙的耐火极限不应"
    "低于3.00h。民用建筑栏杆临空高度的规定见 GB 50352-2019。"
)


# ---- extraction: regex ONLY extracts, normalizes; truth decided elsewhere ----

def test_extract_finds_standard_codes_with_and_without_year():
    codes = extract_standard_clause_claims(
        "依据 GB50016-2019 和 JGJ 107—2016，以及 GB/T 50001。"
    )
    # normalized (uppercase, spaces stripped, dash unified) — order-independent set check
    assert "GB50016-2019" in codes
    assert "JGJ107-2016" in codes
    assert "GB/T50001" in codes


def test_extract_normalizes_spacing_and_dash_variants_to_same_token():
    a = extract_standard_clause_claims("GB 50016—2014")
    b = extract_standard_clause_claims("GB50016-2014")
    assert a == b == ["GB50016-2014"]


def test_extract_empty_when_no_standard_code():
    assert extract_standard_clause_claims("流水施工就是分层分段连续搭接，工期适中。") == []


# ---- no-op cases (防过矫正：普通内容零影响) ----

def test_no_standard_code_is_noop():
    resp = "找坡层在防水层下面，保护层在防水层上面，别搞混。"
    out = content_truth_guard_response(
        user_message="找坡层和保护层啥区别",
        response=resp,
        standard_evidence_text=RECALL_WITH_GB50016,
        rag_degraded=False,
    )
    assert out == resp  # unchanged


def test_verified_code_in_recall_passes_unchanged():
    resp = "防火墙耐火极限不低于3.00h，依据 GB 50016-2014 第6.7.3条。"
    out = content_truth_guard_response(
        user_message="防火墙耐火极限多少",
        response=resp,
        standard_evidence_text=RECALL_WITH_GB50016,
        rag_degraded=False,
    )
    assert out == resp  # code present in this-turn recall → 放行，不动


# ---- fail-closed cases (核不到→降级) ----

def test_fabricated_code_not_in_recall_is_demoted():
    resp = "工期索赔依据《建设工程工程量清单计价规范》GB 50500-2013（2024版）§8.11.8。"
    out = content_truth_guard_response(
        user_message="工期索赔的依据是什么",
        response=resp,
        standard_evidence_text=RECALL_WITH_GB50016,  # GB50500 NOT in recall
        rag_degraded=False,
    )
    assert out != resp
    assert "GB50500-2013" in out  # names the unverifiable code
    # honest demotion language, not a fabricated authority
    assert any(k in out for k in ("无法核到", "未能核到", "以教材", "通用判断"))


def test_wrong_version_year_is_demoted():
    # bot cites GB50016-2019; recall only has GB50016-2014 → -2019 token unverifiable
    resp = "依据 GB 50016-2019 第6.7.3条，临空高度24m以下栏杆不低于1.05m。"
    out = content_truth_guard_response(
        user_message="栏杆高度规定",
        response=resp,
        standard_evidence_text=RECALL_WITH_GB50016,
        rag_degraded=False,
    )
    assert out != resp
    assert "GB50016-2019" in out  # the wrong-year token flagged


def test_rag_degraded_failcloses_any_standard_code():
    # (B) RAG unavailable → no code can come from recall → fail-closed regardless
    resp = "这道题依据 GB 50016-2014 判断。"
    out = content_truth_guard_response(
        user_message="判一下",
        response=resp,
        standard_evidence_text="",  # nothing retrieved
        rag_degraded=True,
    )
    assert out != resp
    assert any(k in out for k in ("检索不可用", "无法核到", "通用判断"))


# ---- eval-design #5 metric self-test: clean passes AND fabricated caught ----

def test_metric_self_test_clean_passes_and_fabricated_caught():
    clean = content_truth_guard_response(
        user_message="x",
        response="防火墙耐火极限不低于3.00h，依据 GB 50016-2014。",
        standard_evidence_text=RECALL_WITH_GB50016,
        rag_degraded=False,
    )
    fabricated = content_truth_guard_response(
        user_message="x",
        response="依据 JGJ 999-2099 第99条，必须如此。",
        standard_evidence_text=RECALL_WITH_GB50016,
        rag_degraded=False,
    )
    # clean claim放行(不动)
    assert "无法核到" not in clean and "检索不可用" not in clean
    # fabricated claim拦(降级)
    assert "JGJ999-2099" in fabricated and ("无法核到" in fabricated or "以教材" in fabricated)


def test_empty_response_is_noop():
    assert content_truth_guard_response(
        user_message="x", response="", standard_evidence_text="", rag_degraded=False
    ) == ""
