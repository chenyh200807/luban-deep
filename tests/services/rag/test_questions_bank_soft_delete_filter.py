"""questions_bank 软删读侧收权（task#31，contracts/rag.md §46）。

钉死的不变量：**软删行（retired_at 非 NULL）不可达任何生产读者**。

断言面全部可证伪：

1. REST 通道单一构造点：`_select` 对 table=questions_bank 必注入
   `retired_at=is.null` —— 删掉 `_select` 里的注入即红；
2. 其他表（kb_chunks）零污染：谓词绝不外溢；
3. fail-closed：调用方试图覆写生命周期谓词（读退役行）必须抛错，不静默；
4. 幂等：重复注入无害、不产生第二个值；
5. exact-ilike 双探针（S1/S2）真实经过 `_select` → 自动携带谓词（端到端）；
6. RPC 通道钉在 migration 文件上：`SOFT_DELETE_FILTERED_DB_READERS` 全部
   9 个库内读者在 20260802000200 里各有一段含 `retired_at IS NULL` 的
   CREATE OR REPLACE —— 从 migration 里删掉任何一个读者的谓词即红；
7. 组卷通道（S8/S9）：blueprint_service `_query` 与 `question_bank_size`
   必带谓词 —— 软删行不得进正式测评卷、不得计入题库规模。
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from deeptutor.services.questions_bank_liveness import (
    LIVE_ROW_FILTER_COLUMN,
    LIVE_ROW_FILTER_OPERATOR,
    QUESTIONS_BANK_TABLE,
    SOFT_DELETE_FILTERED_DB_READERS,
    apply_live_row_filter,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PART_A = REPO_ROOT / "supabase/migrations/20260802000100_questions_bank_soft_delete.sql"
_PART_B = (
    REPO_ROOT / "supabase/migrations/20260802000200_questions_bank_reader_soft_delete_filter.sql"
)


# ---------------------------------------------------------------------------
# 谓词权威模块（单元）
# ---------------------------------------------------------------------------


def test_apply_live_row_filter_injects_predicate() -> None:
    query = {"limit": "3"}
    out = apply_live_row_filter(query)
    assert out is query  # 原地修改，同一对象
    assert out[LIVE_ROW_FILTER_COLUMN] == LIVE_ROW_FILTER_OPERATOR


def test_apply_live_row_filter_is_idempotent() -> None:
    query = {LIVE_ROW_FILTER_COLUMN: LIVE_ROW_FILTER_OPERATOR, "limit": "3"}
    out = apply_live_row_filter(query)
    assert out[LIVE_ROW_FILTER_COLUMN] == LIVE_ROW_FILTER_OPERATOR
    assert len(out) == 2


def test_apply_live_row_filter_refuses_override() -> None:
    """生产读者没有读退役行的权利——覆写谓词必须炸，不静默。"""
    with pytest.raises(ValueError, match="不得覆写生命周期谓词"):
        apply_live_row_filter({LIVE_ROW_FILTER_COLUMN: "not.is.null"})


# ---------------------------------------------------------------------------
# REST 通道：_select 单一构造点（S1/S2/S6/S7）
# ---------------------------------------------------------------------------


class _FakeResponse:
    def raise_for_status(self) -> None:  # pragma: no cover - trivial
        return None

    def json(self) -> list:
        return []


class _FakeClient:
    def __init__(self) -> None:
        self.captured: list[dict] = []

    async def get(self, url, *, headers=None, params=None):
        self.captured.append({"url": url, "params": dict(params or {})})
        return _FakeResponse()


def _pipeline_and_config():
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    pipeline = supabase_module.SupabasePipeline()
    config = supabase_module.SupabaseSearchConfig.__new__(supabase_module.SupabaseSearchConfig)
    object.__setattr__(config, "url", "https://example.supabase.co")
    object.__setattr__(config, "service_key", "test-key")  # pragma: allowlist secret
    return pipeline, config


@pytest.mark.asyncio
async def test_select_injects_live_filter_for_questions_bank() -> None:
    pipeline, config = _pipeline_and_config()
    client = _FakeClient()
    original_query = {"question_stem": "ilike.*混凝土*", "limit": "3"}
    await pipeline._select(
        client,
        table=QUESTIONS_BANK_TABLE,
        select="id",
        query=dict(original_query),
        config=config,
    )
    sent = client.captured[0]["params"]
    assert sent.get(LIVE_ROW_FILTER_COLUMN) == LIVE_ROW_FILTER_OPERATOR
    # 原有谓词一个不丢
    assert sent["question_stem"] == "ilike.*混凝土*"
    assert sent["limit"] == "3"


@pytest.mark.asyncio
async def test_select_does_not_leak_filter_to_other_tables() -> None:
    pipeline, config = _pipeline_and_config()
    client = _FakeClient()
    await pipeline._select(
        client,
        table="kb_chunks",
        select="chunk_id",
        query={"limit": "1"},
        config=config,
    )
    assert LIVE_ROW_FILTER_COLUMN not in client.captured[0]["params"]


@pytest.mark.asyncio
async def test_exact_text_probes_carry_live_filter_end_to_end() -> None:
    """S1/S2：exact-ilike 双探针走真实 `_select`，两发请求都必须带谓词。"""
    pipeline, config = _pipeline_and_config()
    client = _FakeClient()
    await pipeline._search_exact_question_text_direct(
        client=client,
        probe_query="某新建办公楼工程基坑开挖深度为6m",
        config=config,
    )
    assert client.captured, "exact 探针未发出任何请求——harness 失效"
    for call in client.captured:
        assert call["url"].endswith(f"/rest/v1/{QUESTIONS_BANK_TABLE}")
        assert call["params"].get(LIVE_ROW_FILTER_COLUMN) == LIVE_ROW_FILTER_OPERATOR, (
            f"exact 探针漏谓词: {call['params']}"
        )


# ---------------------------------------------------------------------------
# RPC/库内通道：migration 文件穷举钉子（S3/S4/S5 + 遗留读者）
# ---------------------------------------------------------------------------


def test_migration_part_a_adds_lifecycle_columns() -> None:
    text = _PART_A.read_text(encoding="utf-8")
    for column in ("retired_at", "retired_reason", "retired_batch", "superseded_by"):
        assert re.search(rf"add column if not exists {column}", text), (
            f"Part A 缺列 {column}"
        )
    # 半截状态钉死：三条 CHECK + 自 FK
    for constraint in (
        "check_qb_retired_requires_reason",
        "check_qb_live_row_no_retire_meta",
        "check_qb_superseded_not_self",
        "questions_bank_superseded_by_fkey",
    ):
        assert constraint in text, f"Part A 缺约束 {constraint}"


def test_migration_part_b_collapses_every_db_reader() -> None:
    """9 个库内读者（8 函数+1 视图）逐一核对：定义在场 + 谓词在场。

    这是把「SQL 不在仓库的 RPC」钉进 CI 的最小办法：migration 文件是
    收权的唯一载体，从里面删掉任何一个读者或它的谓词，这里立即红。
    """
    text = _PART_B.read_text(encoding="utf-8")
    # 按 CREATE OR REPLACE 切段，段首即对象名
    segments = re.split(r"(?i)CREATE OR REPLACE ", text)[1:]
    by_name: dict[str, str] = {}
    for segment in segments:
        for name in SOFT_DELETE_FILTERED_DB_READERS:
            if re.match(rf"(?:FUNCTION|VIEW)\s+public\.{re.escape(name)}\b", segment, re.IGNORECASE):
                by_name[name] = segment
    missing = [n for n in SOFT_DELETE_FILTERED_DB_READERS if n not in by_name]
    assert not missing, f"migration Part B 缺库内读者定义: {missing}"
    unfiltered = [
        n
        for n, segment in by_name.items()
        if not re.search(r"(?i)retired_at\s+is\s+null", segment)
    ]
    assert not unfiltered, f"migration Part B 里这些读者没有软删谓词: {unfiltered}"


def test_migration_part_b_refresh_syllabus_stats_filters_both_sites() -> None:
    """refresh_syllabus_stats 有两处 questions_bank 引用（聚合 CTE + 归零
    NOT EXISTS），漏任何一处都会让「只剩 retired 题」的节点计数不归零。"""
    text = _PART_B.read_text(encoding="utf-8")
    match = re.search(
        r"(?is)CREATE OR REPLACE FUNCTION public\.refresh_syllabus_stats.*?\$function\$;",
        text,
    )
    assert match, "Part B 缺 refresh_syllabus_stats"
    body = match.group(0)
    assert len(re.findall(r"(?i)retired_at\s+is\s+null", body)) >= 2, (
        "refresh_syllabus_stats 的两处 questions_bank 引用必须都带谓词"
    )


# ---------------------------------------------------------------------------
# 组卷通道（S8/S9）
# ---------------------------------------------------------------------------


def test_blueprint_query_injects_live_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.assessment.blueprint_service import (
        SupabaseAssessmentQuestionProvider,
    )

    provider = SupabaseAssessmentQuestionProvider()
    captured: list[dict] = []

    def _fake_rest_get(base_url, api_key, table, filters):
        captured.append({"table": table, "filters": dict(filters)})
        return []

    monkeypatch.setattr(provider, "_rest_get", _fake_rest_get)
    provider._query("https://example.supabase.co", "key", {"limit": "10"})
    assert captured[0]["table"] == QUESTIONS_BANK_TABLE
    assert captured[0]["filters"].get(LIVE_ROW_FILTER_COLUMN) == LIVE_ROW_FILTER_OPERATOR


def test_blueprint_question_bank_size_counts_live_rows_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.assessment import blueprint_service as bp_module

    provider = bp_module.SupabaseAssessmentQuestionProvider()
    monkeypatch.setattr(
        provider, "_supabase_config", lambda: ("https://example.supabase.co", "key")
    )
    seen_urls: list[str] = []

    class _CountResponse:
        headers = {"Content-Range": "0-0/4635"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, timeout=None):
        seen_urls.append(req.full_url)
        return _CountResponse()

    monkeypatch.setattr(bp_module.request, "urlopen", _fake_urlopen)
    assert provider.question_bank_size() == 4635
    assert f"{LIVE_ROW_FILTER_COLUMN}={LIVE_ROW_FILTER_OPERATOR}" in seen_urls[0]
