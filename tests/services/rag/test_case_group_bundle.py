"""方案 C / C3：命中案例行后按 `case_group_id` 取全组（contracts/rag.md §45）。

治的病：整卷提交只判 1/4。此前 bundle 只装「检索恰好召回的兄弟行」，覆盖面取决于
相似度与 `seen_by_index` 抢位——同一份提交每次判到的小问都可能不同。

本文件的断言面全部可证伪：

1. **随机性消失的铁证**：命中组内第 1/2/4 行、DB 乱序返回 → bundle 恒等；
2. **冲突洞不得伪装成 full coverage**（§45(c) 红线）：canonical=NULL 的小问
   fail-closed 不入参考 + marker 在场 + covered_indexes 如实缺号；
3. **查询红线**：组查询必须 `case_row_canonical=not.is.false`，写 `eq.true` 立即红；
4. **粒度分叉**（§45(b)）：`whole_question` 行零组查询；
5. **回归零影响**（§45(d)）：无组键行逐字段回落现单行行为；
6. **形态双吃**：`correct_answer` 的 string / array 两种世代形态都吃；
7. **MCQ 路径零调用**：非 case 命中不发任何查询、不写任何 marker；
8. **L1 瘦身共存**：lean profile 下组查询照跑（身份/分母命脉不得砍）。
"""

from __future__ import annotations

import hashlib
import json

import pytest

CASE_QUERY = (
    "【背景资料】某新建办公楼工程，建筑面积 32000m2，地下 2 层，地上 12 层，"
    "现浇钢筋混凝土框架结构。施工单位与建设单位签订了施工总承包合同，"
    "基坑开挖深度为 6m，施工单位编制了基坑专项施工方案。\n"
    "【问题】\n1. 指出基坑施工中的不妥之处，并说明理由。\n"
    "2. 写出深基坑专项施工方案的论证要求。\n"
    "3. 列出模板拆除的条件。\n"
    "4. 说明本工程模板工程验收的主要内容。\n"
)

MCQ_QUERY = "下列关于混凝土养护的说法，正确的是（  ）。A.7天 B.14天 C.28天 D.3天"

GROUP_ID = "2023-case3"


def _bank_row(row_id: int, *, stem: str, question_type: str = "case_study") -> dict:
    return {
        "id": row_id,
        "original_id": f"E{row_id}",
        "stem": stem,
        "question_stem": "",
        "node_code": "1A420000",
        "source_type": "exam",
        "options": None,
        "correct_answer": "该行自身的答案钥匙",
        "analysis": "该行解析",
        "question_type": question_type,
        "similarity": 0.93,
        "source_chunk_id": "EXAM_1A420000_P0014_06",
        "exam_year": 2023,
        "background_context": None,
        "parent_id": None,
        "grading_rubric": None,
        "structured_rules": None,
        "logic_rule": None,
    }


# 组内四小问：id 与 C1 测绘里 2023-case3 的世代形态同构
# （9559/17371 是同一小问的两个入库世代，17372-17374 是后续小问）。
_GROUP_ROWS: list[dict] = [
    {
        **_bank_row(9559, stem="问题1. 指出基坑施工中的不妥之处，并说明理由。"),
        "case_group_id": GROUP_ID,
        "case_subquestion_index": 1,
        "case_row_granularity": "subquestion",
        "case_row_canonical": True,
        "correct_answer": "答案1：不妥之处……",
    },
    {
        **_bank_row(17372, stem="问题2. 写出深基坑专项施工方案的论证要求。"),
        "case_group_id": GROUP_ID,
        "case_subquestion_index": 2,
        "case_row_granularity": "subquestion",
        "case_row_canonical": True,
        # g3 世代形态：array（每元素一个采分要点）
        "correct_answer": ["论证要求一", "论证要求二"],
    },
    {
        **_bank_row(17373, stem="问题3. 列出模板拆除的条件。"),
        "case_group_id": GROUP_ID,
        "case_subquestion_index": 3,
        "case_row_granularity": "subquestion",
        "case_row_canonical": True,
        "correct_answer": "答案3：拆模条件……",
    },
    {
        **_bank_row(17374, stem="问题4. 说明本工程模板工程验收的主要内容。"),
        "case_group_id": GROUP_ID,
        "case_subquestion_index": 4,
        "case_row_granularity": "subquestion",
        "case_row_canonical": True,
        "correct_answer": "答案4：验收内容……",
    },
]

# 冲突洞（C2 实测：72 行答案冲突留 canonical=NULL，11 组序号带洞）：
# 小问 2 的两个世代答案互相冲突，均未裁决。
_GROUP_ROWS_WITH_CONFLICT: list[dict] = [
    _GROUP_ROWS[0],
    {**_GROUP_ROWS[1], "id": 17372, "case_row_canonical": None, "correct_answer": "世代A答案"},
    {**_GROUP_ROWS[1], "id": 19999, "case_row_canonical": None, "correct_answer": "世代B答案"},
    _GROUP_ROWS[2],
    _GROUP_ROWS[3],
]


def _config(supabase_module):
    weights = {
        "textbook": 1.0,
        "standard": 1.2,
        "exam": 1.0,
        "questions_bank": 1.5,
        "question_exact_text": 4.2,
        "question_exact_vector": 3.4,
        "compiled_learning_truth": 0.6,
    }
    return supabase_module.SupabaseSearchConfig(
        url="https://example.supabase.co",
        service_key="test-key",  # pragma: allowlist secret
        timeout_s=5.0,
        sources=["textbook", "standard", "exam"],
        include_questions=True,
        top_k=5,
        fetch_count=8,
        match_threshold=0.2,
        vector_weight=1.0,
        text_weight=1.0,
        source_weights=dict(weights),
        question_weights=dict(weights),
        max_per_document=3,
        query_expansion_enabled=False,
        max_query_variants=1,
        second_pass_enabled=True,
        second_pass_max_queries=3,
        second_pass_min_hits=1,
        second_pass_max_dup_ratio=1.0,
        rerank_enabled=False,
        rerank_window=5,
        rerank_timeout_s=2.0,
        exact_question_enabled=True,
        exact_question_text_first=True,
        exact_question_min_similarity=0.9,
        exact_question_max_text_len=128,
        exact_question_text_rpc_enabled=False,
        query_plan_trace_enabled=True,
        compiled_truth_shadow_enabled=False,
        compiled_truth_enabled=False,
        provenance_boost_enabled=False,
    )


async def _run_search(
    monkeypatch: pytest.MonkeyPatch,
    *,
    seed_row: dict,
    query: str = CASE_QUERY,
    meta_rows: list[dict] | None = None,
    group_rows: list[dict] | None = None,
    retrieval_profile: str | None = None,
    select_error: Exception | None = None,
):
    """跑一次真实管线，`_select` 用 fake 拦在 HTTP 边界上（组查询代码全程真跑）。"""
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    pipeline = supabase_module.SupabasePipeline()
    config = _config(supabase_module)
    calls: list[dict] = []

    monkeypatch.setattr(pipeline, "_load_search_config", lambda **_kwargs: config)

    async def _available(**_kwargs):
        return None

    async def _client(*_args, **_kwargs):
        return object()

    async def _embed(_query):
        return [0.01] * 8

    async def _embed_batch(queries):
        return {item: [0.01] * 8 for item in queries}

    async def _search_source(*, client, query, vector_literal, source_type, config):
        return []

    async def _search_questions(*, client, vector_literal, config, raw_sink=None):
        if raw_sink is not None:
            raw_sink.append(dict(seed_row))
        return [
            pipeline._normalize_question_result(
                dict(seed_row), source_group="questions_bank", score=0.93
            )
        ]

    async def _exact_text_batch(*, probe_queries, **_kwargs):
        row = pipeline._normalize_question_result(
            dict(seed_row), source_group="question_exact_text", score=0.97
        )
        return [{"query": probe_queries[0], "results": [row]}]

    async def _hydrate(results, *, config):
        return results

    async def _select(_client, *, table, select, query, config):
        calls.append({"table": table, "select": select, "query": dict(query)})
        if select_error is not None:
            raise select_error
        if "case_group_id" in query:
            return [dict(row) for row in (group_rows or [])]
        return [dict(row) for row in (meta_rows or [])]

    monkeypatch.setattr(pipeline, "_assert_data_api_available", _available)
    monkeypatch.setattr(pipeline, "_get_client", _client)
    monkeypatch.setattr(pipeline, "_embed_query", _embed)
    monkeypatch.setattr(pipeline, "_embed_queries_batch", _embed_batch)
    monkeypatch.setattr(pipeline, "_search_source", _search_source)
    monkeypatch.setattr(pipeline, "_search_questions", _search_questions)
    monkeypatch.setattr(pipeline, "_search_exact_question_text_batch", _exact_text_batch)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _hydrate)
    monkeypatch.setattr(pipeline, "_select", _select)

    kwargs: dict[str, str] = {}
    if retrieval_profile:
        kwargs["retrieval_profile"] = retrieval_profile
    payload = await pipeline.search(query, "construction-exam", **kwargs)
    return payload.get("exact_question"), calls


def _meta_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "id": row["id"],
            "case_group_id": row.get("case_group_id"),
            "case_subquestion_index": row.get("case_subquestion_index"),
            "case_row_granularity": row.get("case_row_granularity"),
            "case_row_canonical": row.get("case_row_canonical"),
        }
        for row in rows
    ]


def _bundle_fingerprint(exact: dict) -> str:
    """只取覆盖面（与命中哪一行无关的部分），逐字节 hash。"""
    return hashlib.sha256(
        json.dumps(
            {
                "covered_subquestions": exact.get("covered_subquestions"),
                "covered_indexes": exact.get("covered_indexes"),
                "coverage_state": exact.get("coverage_state"),
                "matched_question_ids": exact.get("matched_question_ids"),
                "case_group_id": exact.get("case_group_id"),
                "case_bundle_source": exact.get("case_bundle_source"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


# ───────────────────────── 1. 随机性消失的铁证 ─────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_position", [0, 1, 3])
async def test_group_bundle_is_identical_whatever_row_seeded_it(
    monkeypatch: pytest.MonkeyPatch, seed_position: int
) -> None:
    """命中组内第 1/2/4 行、且 DB 乱序返回 → bundle 逐字节恒等。

    这是本次改动要证的核心：覆盖面不再是「检索运气」的函数。剔除 seed 行自身的
    身份字段后，三次运行的 bundle hash 必须相同。
    """
    fingerprints = set()
    for seed_position_run, shuffled in (
        (seed_position, list(reversed(_GROUP_ROWS))),
        (seed_position, [_GROUP_ROWS[2], _GROUP_ROWS[0], _GROUP_ROWS[3], _GROUP_ROWS[1]]),
    ):
        seed = {**_GROUP_ROWS[seed_position_run], "stem": CASE_QUERY}
        exact, calls = await _run_search(
            monkeypatch,
            seed_row=seed,
            meta_rows=_meta_rows([_GROUP_ROWS[seed_position_run]]),
            group_rows=shuffled,
        )
        assert isinstance(exact, dict) and exact, "前提失效：必须命中 exact"
        assert exact["case_bundle_source"] == "group_query"
        assert exact["covered_indexes"] == ["1", "2", "3", "4"]
        assert exact["matched_question_ids"] == [9559, 17372, 17373, 17374]
        assert exact["coverage_state"] == "multi_subquestion_exact"
        # 组查询恰好一次（外加一次组键解析）——不得对每个兄弟行各发一次。
        group_calls = [c for c in calls if "case_group_id" in c["query"]]
        assert len(group_calls) == 1
        fingerprints.add(_bundle_fingerprint(exact))
    assert len(fingerprints) == 1, "同一组、不同 seed/返回序 产出了不同 bundle"


@pytest.mark.asyncio
async def test_bundle_fingerprint_is_seed_invariant_across_all_seeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三个 seed 之间横向比：剔除 seed 后 hash 相同。"""
    fingerprints = set()
    for position in (0, 1, 3):
        exact, _ = await _run_search(
            monkeypatch,
            seed_row={**_GROUP_ROWS[position], "stem": CASE_QUERY},
            meta_rows=_meta_rows([_GROUP_ROWS[position]]),
            group_rows=list(_GROUP_ROWS),
        )
        fingerprints.add(_bundle_fingerprint(exact))
    assert len(fingerprints) == 1


# ─────────────── 2 & 3. 冲突洞 + 查询红线（§45(c)）───────────────


@pytest.mark.asyncio
async def test_conflict_hole_is_excluded_and_announced_not_faked_as_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """canonical=NULL 的小问 fail-closed 不入参考，且必须发声。

    反面（本次要防的病）：把 NULL 当 false 过滤掉 → covered_indexes 看起来连续、
    「有争议」被静默读成「没这一问」。
    """
    exact, _ = await _run_search(
        monkeypatch,
        seed_row={**_GROUP_ROWS[0], "stem": CASE_QUERY},
        meta_rows=_meta_rows([_GROUP_ROWS[0]]),
        group_rows=_GROUP_ROWS_WITH_CONFLICT,
    )
    assert exact["covered_indexes"] == ["1", "3", "4"], "冲突小问不得进参考"
    assert exact["case_answer_conflict_unresolved"] == f"{GROUP_ID}:2"
    # 不得虚报 full coverage：学生题面 4 问、参考只覆盖 3 问。
    assert exact["coverage_state"] == "partial_multi_subquestion_exact"
    assert exact["coverage_ratio"] < 1.0
    assert [str(item.get("display_index")) for item in exact["missing_subquestions"]] == ["2"]
    # 两个冲突世代的答案都不得混进参考。
    answers = " ".join(
        str(item.get("authoritative_answer") or "") for item in exact["covered_subquestions"]
    )
    assert "世代A答案" not in answers and "世代B答案" not in answers


@pytest.mark.asyncio
async def test_group_query_uses_is_not_false_never_eq_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§45(c) 红线的机器判据：写成 `eq.true` 立即红。"""
    _, calls = await _run_search(
        monkeypatch,
        seed_row={**_GROUP_ROWS[0], "stem": CASE_QUERY},
        meta_rows=_meta_rows([_GROUP_ROWS[0]]),
        group_rows=list(_GROUP_ROWS),
    )
    group_call = next(c for c in calls if "case_group_id" in c["query"])
    assert group_call["query"]["case_row_canonical"] == "not.is.false"
    assert group_call["query"]["case_group_id"] == f"eq.{GROUP_ID}"
    assert group_call["query"]["question_type"] == "eq.case_study"
    assert group_call["query"]["limit"] == "12"
    # bundle 只收带 case_group_id 的治理行：结构性隔离 1547 行误标教材题。
    assert group_call["table"] == "questions_bank"


# ───────────────────── 4. 粒度分叉（§45(b)）─────────────────────


@pytest.mark.asyncio
async def test_whole_question_row_issues_zero_group_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """整题行自含全部小问（2024/2017 年份主导）→ 不得再发兄弟行查询。"""
    whole_row = {
        **_bank_row(20240, stem=CASE_QUERY),
        "case_group_id": "2024-case1",
        "case_subquestion_index": None,
        "case_row_granularity": "whole_question",
        "case_row_canonical": True,
    }
    exact, calls = await _run_search(
        monkeypatch,
        seed_row=whole_row,
        meta_rows=_meta_rows([whole_row]),
        group_rows=list(_GROUP_ROWS),  # 若误发组查询，这批会污染 bundle
    )
    assert exact["case_bundle_source"] == "whole_row"
    assert exact["case_bundle_hydration"] == "skipped:whole_question_row"
    assert exact["case_group_id"] == "2024-case1"
    assert [c for c in calls if "case_group_id" in c["query"]] == []
    # 行为不回归：整题行仍按命中行自身装配（组行没有一条混进来）。
    assert all(
        str(item.get("question_id") or "") not in {"17372", "17373", "17374"}
        for item in exact["covered_subquestions"]
    )


# ───────────────────── 5. 回归零影响（§45(d)）─────────────────────


@pytest.mark.asyncio
async def test_row_without_group_key_keeps_current_behavior_byte_for_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无组键行（1574 行误标教材题就在这里）→ 逐字段回落现行为，只多降级 marker。

    §45(d)：`case_group_id IS NULL` 不代表「不是案例」，也**不得**回退到老的
    chunk/year 聚合。
    """
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    ungoverned = {**_bank_row(88888, stem=CASE_QUERY)}

    # 基线：把水合整段短路成 identity，拿到「本次改动之前」的 payload。
    async def _passthrough(_self, exact_question, *, config):
        return exact_question

    monkeypatch.setattr(
        supabase_module.SupabasePipeline, "_hydrate_case_group_bundle", _passthrough
    )
    baseline, _ = await _run_search(monkeypatch, seed_row=ungoverned)
    monkeypatch.undo()

    exact, calls = await _run_search(
        monkeypatch,
        seed_row=ungoverned,
        meta_rows=_meta_rows([ungoverned]),
        group_rows=list(_GROUP_ROWS),
    )
    assert exact["case_bundle_source"] == "single_row_fallback"
    assert exact["case_bundle_hydration"] == "skipped:null_group_key"
    assert [c for c in calls if "case_group_id" in c["query"]] == []
    stripped = {
        key: value
        for key, value in exact.items()
        if key not in {"case_bundle_source", "case_bundle_hydration"}
    }
    assert stripped == baseline, "无组键行的行为必须逐字段等于改动前"


@pytest.mark.asyncio
async def test_group_query_failure_degrades_with_marker_and_never_fails_the_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """查询失败 = 回落单行 + 降级 marker，绝不 fail 整轮（AGENTS：降级必须发声）。"""
    exact, _ = await _run_search(
        monkeypatch,
        seed_row={**_GROUP_ROWS[0], "stem": CASE_QUERY},
        select_error=RuntimeError("boom"),
    )
    assert isinstance(exact, dict) and exact
    assert exact["case_bundle_source"] == "single_row_fallback"
    assert exact["case_bundle_hydration"] == "degraded:group_meta_query_failed:RuntimeError"
    assert exact["covered_subquestions"], "降级后仍须保留原单行参考"


# ───────────────────── 6. 答案形态双吃 ─────────────────────


@pytest.mark.asyncio
async def test_string_and_array_correct_answer_are_both_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """g1/g2 是 string、g3 是 array；两种形态必须都变成非空参考文本。"""
    exact, _ = await _run_search(
        monkeypatch,
        seed_row={**_GROUP_ROWS[0], "stem": CASE_QUERY},
        meta_rows=_meta_rows([_GROUP_ROWS[0]]),
        group_rows=list(_GROUP_ROWS),
    )
    by_index = {
        item["display_index"]: item["authoritative_answer"]
        for item in exact["covered_subquestions"]
    }
    assert by_index["1"] == "答案1：不妥之处……"  # string 世代
    assert by_index["2"] == "论证要求一\n论证要求二"  # array 世代，原序拼接
    assert all(value for value in by_index.values()), "任一形态解析成空即为静默丢答案"


def test_answer_text_coercion_is_order_preserving_and_total() -> None:
    from deeptutor.services.rag.pipelines.supabase import _case_reference_answer_text

    assert _case_reference_answer_text(None) == ""
    assert _case_reference_answer_text("  甲  ") == "甲"
    assert _case_reference_answer_text(["乙", "", "甲"]) == "乙\n甲"  # 不排序
    assert _case_reference_answer_text({"2": "乙", "1": "甲"}) == "甲\n乙"  # 稳定序
    assert _case_reference_answer_text(7) == "7"


# ───────────────────── 7. MCQ 路径零调用 ─────────────────────


@pytest.mark.asyncio
async def test_mcq_hit_issues_zero_queries_and_writes_zero_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcq_row = {
        **_bank_row(4321, stem=MCQ_QUERY, question_type="single_choice"),
        "options": {"A": "7天", "B": "14天", "C": "28天", "D": "3天"},
        "correct_answer": "C",
    }
    exact, calls = await _run_search(
        monkeypatch, seed_row=mcq_row, query=MCQ_QUERY, meta_rows=_meta_rows([mcq_row])
    )
    assert isinstance(exact, dict) and exact
    assert exact.get("answer_kind") != "case_study"
    assert calls == [], "非 case 命中不得发任何题级组查询"
    assert "case_bundle_source" not in exact
    assert "case_bundle_hydration" not in exact


# ───────────────────── 8. L1 瘦身 profile 共存 ─────────────────────


@pytest.mark.asyncio
async def test_lean_profile_still_runs_the_group_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组取全属身份/分母命脉，lean 轮必须照跑，且分母与 full 逐字段相同。"""
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY,
    )

    seed = {**_GROUP_ROWS[0], "stem": CASE_QUERY}
    full_exact, full_calls = await _run_search(
        monkeypatch,
        seed_row=seed,
        meta_rows=_meta_rows([_GROUP_ROWS[0]]),
        group_rows=list(_GROUP_ROWS),
    )
    lean_exact, lean_calls = await _run_search(
        monkeypatch,
        seed_row=seed,
        meta_rows=_meta_rows([_GROUP_ROWS[0]]),
        group_rows=list(_GROUP_ROWS),
        retrieval_profile=RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY,
    )
    assert [c["query"] for c in lean_calls] == [c["query"] for c in full_calls]
    assert lean_exact == full_exact
    assert lean_exact["covered_indexes"] == ["1", "2", "3", "4"]
