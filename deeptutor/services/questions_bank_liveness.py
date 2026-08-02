"""questions_bank 在服行过滤的单一谓词权威（task#31 供给层软删收权，2026-08-02）.

生命周期唯一判据 = ``questions_bank.retired_at``（migration 20260802000100）：
非 NULL 即软删，**不可达任何生产读者**。本模块是应用侧唯一的谓词定义点——
所有 PostgREST 直读 questions_bank 的查询构造必须经 :func:`apply_live_row_filter`
注入 ``retired_at=is.null``，禁止调用点各自手写 WHERE（那是第 N+1 个 decider）。

接线现状（读者测绘全量清单见
docs/原始数据/数据盘点/2026-08-02-questions_bank软删版本化读者测绘与设计.md §1）：

- REST 通道：``rag/pipelines/supabase.py::_select``（S1/S2/S6/S7 四读者的公共
  构造点，按表名注入）与 ``assessment/blueprint_service.py::_query`` /
  ``question_bank_size``（S8/S9）。
- RPC 通道（S3/S4/S5）：返回列由 DB 函数签名固定、应用侧改不了，收权落在
  migration 20260802000200 的函数体内（``retired_at IS NULL``）。
  :data:`SOFT_DELETE_FILTERED_DB_READERS` 是那 9 个库内读者的穷举清单，
  静态测试用它对 migration 文件逐一核对——**漏一个即红**。

部署顺序硬约束：migration Part A（加列）必须先于本模块所在代码部署，
否则 PostgREST 对含未知列过滤参数的查询返 400（题库检索全断）。
见 extractions/supply_soft_delete_20260802/APPROVAL_SHEET.md。
"""

from __future__ import annotations

QUESTIONS_BANK_TABLE = "questions_bank"

#: 生命周期列与 PostgREST 谓词（先例：notebook_card/store.py 的 archived_at is.null）
LIVE_ROW_FILTER_COLUMN = "retired_at"
LIVE_ROW_FILTER_OPERATOR = "is.null"

#: migration 20260802000200 收权的库内读者穷举清单（8 函数 + 1 视图，
#: live pg_proc/pg_views 实测 2026-08-02）。改这份清单必须同步改 migration。
SOFT_DELETE_FILTERED_DB_READERS: tuple[str, ...] = (
    "search_questions_bank_vector",
    "search_questions_bank_text",
    "search_questions_bank_text_ranked",
    "search_questions",
    "search_questions_by_keywords",
    "match_questions",
    "get_questions_quality_stats_v2",
    "refresh_syllabus_stats",
    "v_retrieval_questions",
)


def apply_live_row_filter(query: dict[str, str]) -> dict[str, str]:
    """向 PostgREST 查询参数注入在服行谓词（原地修改并返回同一 dict）。

    幂等：重复调用无害。fail-closed：若调用方已经对生命周期列写了**别的**
    谓词（例如 ``not.is.null`` 想读退役行），拒绝静默覆写、直接抛错——
    生产读者没有读退役行的权利；治理/审计工具想读全量，就不要走本函数。
    """
    existing = query.get(LIVE_ROW_FILTER_COLUMN)
    if existing is not None and existing != LIVE_ROW_FILTER_OPERATOR:
        raise ValueError(
            "questions_bank 生产读取不得覆写生命周期谓词: "
            f"{LIVE_ROW_FILTER_COLUMN}={existing!r} (期望 {LIVE_ROW_FILTER_OPERATOR!r})"
        )
    query[LIVE_ROW_FILTER_COLUMN] = LIVE_ROW_FILTER_OPERATOR
    return query
