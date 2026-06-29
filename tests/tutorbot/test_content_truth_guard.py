"""Content-truth review loop (② reachability/consumption — verification 半边).

#302 上线了 post-gen 规范核验闸(抽 GB/JGJ 编号 → 核本轮 standard 召回)。owner 复盘后
把它从"软 caveat(否定感、可能让学员觉得系统没用)"改造成三层 owner 设计：

  L1 永远输出 + 诚实 hedge —— 绝不抑制/拒答。LLM 该说规范条文就说，配大方诚实声明
     ("以上内容由 AI 生成，请以教材/官方规范原文为准核对，不保证 100% 准确")。
  L2 低置信内部记录 —— 核不到本轮召回(或 degraded)的编号静默记进 review queue(学员看不到)。
  L3 评审 agent 异步纠错 —— 离线评审(教材仲裁 + 异源)把低置信 claim 判 accurate/fabricated
     /uncertain，攒成纠错数据集喂内容升级(产品飞轮燃料)。

owner 原则：信当下 LLM 能力，宁可大方输出 + 诚实声明，也不闭嘴；准确性靠"后台审 + 持续纠"
的 review loop 保证，**非输出端抑制**。

本测试钉死 L1 的**确定性行为**(eval-design：判官/异源不可信，确定性断言作主 ground truth)：
- 永不抑制：非空输入永远有输出，正文逐字保留(append hedge，绝不 nuke)。
- 单一计算：``assess_unverifiable_standard_codes`` 是唯一"核不到"判定点(regex 只抽，召回裁决)。
- 诚实 hedge：核不到时 append 大方声明(AI 生成 + 以教材/官方规范为准 + 不保证 100%)，命名编号。
- review record：核不到的编号产出结构化低置信记录(claim + confidence_signal + context_excerpt)。
- 防过矫正：无规范编号的普通内容零影响。
"""

from __future__ import annotations

from deeptutor.tutorbot.agent.loop import AgentLoop
from deeptutor.tutorbot.teaching_modes import (
    assess_unverifiable_standard_codes,
    build_content_truth_review_records,
    content_truth_guard_response,
    extract_standard_clause_claims,
)

# A piece of this-turn standard recall evidence (what search_standard_chunks returned).
RECALL_WITH_GB50016 = (
    "《建筑设计防火规范》GB 50016-2014（2018年版）第6.7.3条规定，防火墙的耐火极限不应"
    "低于3.00h。民用建筑栏杆临空高度的规定见 GB 50352-2019。"
)


def _is_honest_hedge(text: str) -> bool:
    """owner hedge 形态：AI 生成 + 以教材/官方规范为准 + 不保证 100%。"""
    return (
        "AI" in text
        and ("教材" in text or "官方规范" in text)
        and "100%" in text
    )


# ---- extraction: regex ONLY extracts, normalizes; truth decided elsewhere ----

def test_extract_finds_standard_codes_with_and_without_year():
    codes = extract_standard_clause_claims(
        "依据 GB50016-2019 和 JGJ 107—2016，以及 GB/T 50001。"
    )
    assert "GB50016-2019" in codes
    assert "JGJ107-2016" in codes
    assert "GB/T50001" in codes


def test_extract_normalizes_spacing_and_dash_variants_to_same_token():
    a = extract_standard_clause_claims("GB 50016—2014")
    b = extract_standard_clause_claims("GB50016-2014")
    assert a == b == ["GB50016-2014"]


def test_extract_empty_when_no_standard_code():
    assert extract_standard_clause_claims("流水施工就是分层分段连续搭接，工期适中。") == []


# ---- assess: the single "unverifiable" decision point ----

def test_assess_returns_empty_for_verified_code():
    assert assess_unverifiable_standard_codes(
        response="防火墙耐火极限不低于3.00h，依据 GB 50016-2014 第6.7.3条。",
        standard_evidence_text=RECALL_WITH_GB50016,
        rag_degraded=False,
    ) == []


def test_assess_flags_code_not_in_recall():
    out = assess_unverifiable_standard_codes(
        response="工期索赔依据 GB 50500-2013（2024版）§8.11.8。",
        standard_evidence_text=RECALL_WITH_GB50016,
        rag_degraded=False,
    )
    assert out == ["GB50500-2013"]


def test_assess_failcloses_every_code_when_rag_degraded():
    out = assess_unverifiable_standard_codes(
        response="依据 GB 50016-2014 判断。",
        standard_evidence_text="",
        rag_degraded=True,
    )
    assert out == ["GB50016-2014"]


def test_assess_empty_for_no_code_or_empty():
    assert assess_unverifiable_standard_codes(
        response="找坡层在防水层下面。", standard_evidence_text="", rag_degraded=True
    ) == []
    assert assess_unverifiable_standard_codes(
        response="", standard_evidence_text="", rag_degraded=True
    ) == []


# ---- L1 永远输出: no-op for clean content (防过矫正) ----

def test_no_standard_code_is_noop():
    resp = "找坡层在防水层下面，保护层在防水层上面，别搞混。"
    out = content_truth_guard_response(
        user_message="找坡层和保护层啥区别",
        response=resp,
        standard_evidence_text=RECALL_WITH_GB50016,
        rag_degraded=False,
    )
    assert out == resp


def test_verified_code_in_recall_passes_unchanged():
    resp = "防火墙耐火极限不低于3.00h，依据 GB 50016-2014 第6.7.3条。"
    out = content_truth_guard_response(
        user_message="防火墙耐火极限多少",
        response=resp,
        standard_evidence_text=RECALL_WITH_GB50016,
        rag_degraded=False,
    )
    assert out == resp


# ---- L1 永远输出 + 诚实 hedge: never suppress, append honest disclaimer ----

def test_unverifiable_code_keeps_full_output_and_appends_honest_hedge():
    resp = "工期索赔依据《建设工程工程量清单计价规范》GB 50500-2013（2024版）§8.11.8。"
    out = content_truth_guard_response(
        user_message="工期索赔的依据是什么",
        response=resp,
        standard_evidence_text=RECALL_WITH_GB50016,  # GB50500 NOT in recall
        rag_degraded=False,
    )
    # NEVER suppressed: original content preserved verbatim at the head
    assert out.startswith(resp.rstrip())
    assert len(out) > len(resp)
    # honest, generous hedge (owner framing), names the code
    assert _is_honest_hedge(out)
    assert "GB50500-2013" in out


def test_rag_degraded_keeps_output_and_hedges_every_code():
    resp = "这道题依据 GB 50016-2014 判断。"
    out = content_truth_guard_response(
        user_message="判一下",
        response=resp,
        standard_evidence_text="",
        rag_degraded=True,
    )
    assert out.startswith(resp.rstrip())
    assert _is_honest_hedge(out)
    assert "GB50016-2014" in out


def test_empty_response_is_noop():
    assert content_truth_guard_response(
        user_message="x", response="", standard_evidence_text="", rag_degraded=False
    ) == ""


# ---- L2 低置信内部记录: structured review records for the offline queue ----

def test_review_records_built_for_unverifiable_codes():
    resp = "工期索赔依据 GB 50500-2013 §8.11.8，另见 JGJ 999-2099。"
    unverifiable = assess_unverifiable_standard_codes(
        response=resp, standard_evidence_text=RECALL_WITH_GB50016, rag_degraded=False
    )
    records = build_content_truth_review_records(
        response=resp, unverifiable_codes=unverifiable, rag_degraded=False
    )
    claims = {r["claim"] for r in records}
    assert claims == {"GB50500-2013", "JGJ999-2099"}
    for r in records:
        assert r["confidence_signal"] == "rag_miss"
        assert r["claim_kind"] == "standard_code"
        # context excerpt is a bounded window of the BOT answer around the claim
        assert isinstance(r["context_excerpt"], str) and r["context_excerpt"]
        assert len(r["context_excerpt"]) <= 240


def test_review_records_mark_rag_degraded_signal():
    resp = "依据 GB 50016-2014 判断。"
    unverifiable = assess_unverifiable_standard_codes(
        response=resp, standard_evidence_text="", rag_degraded=True
    )
    records = build_content_truth_review_records(
        response=resp, unverifiable_codes=unverifiable, rag_degraded=True
    )
    assert records and all(r["confidence_signal"] == "rag_degraded" for r in records)


def test_review_records_empty_when_nothing_unverifiable():
    assert build_content_truth_review_records(
        response="x", unverifiable_codes=[], rag_degraded=False
    ) == []


# ---- L2 export: claims must ride OUT on the OutboundMessage metadata ----
# (process_direct round-trips response.metadata to the manager; the loop's internal
#  runtime_metadata is a COPY, so without this export the claims die inside the loop —
#  the live break observed 2026-06-29 where TurnEventLog had 0 claims.)

def test_export_content_truth_metadata_carries_claims_to_outbound():
    records = [{"claim": "GB50500-2013", "confidence_signal": "rag_miss"}]
    runtime_metadata = {
        "content_truth_guard_applied": True,
        "content_truth_low_confidence_claims": records,
        "unrelated": "x",
    }
    response_metadata: dict = {}
    AgentLoop._export_content_truth_metadata(runtime_metadata, response_metadata)
    assert response_metadata["content_truth_low_confidence_claims"] == records
    assert response_metadata["content_truth_guard_applied"] is True
    assert "unrelated" not in response_metadata  # only the two flag keys cross


def test_export_content_truth_metadata_noop_when_absent():
    response_metadata: dict = {"keep": 1}
    AgentLoop._export_content_truth_metadata({"rag_retrieval_degraded": False}, response_metadata)
    assert response_metadata == {"keep": 1}  # nothing to export → untouched


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
    # clean claim 放行(不动) —— no hedge appended
    assert clean.endswith("GB 50016-2014。")
    # fabricated claim 不抑制但 hedge —— output preserved + honest disclaimer + named
    assert fabricated.startswith("依据 JGJ 999-2099 第99条，必须如此。")
    assert _is_honest_hedge(fabricated)
    assert "JGJ999-2099" in fabricated
