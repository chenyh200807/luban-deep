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

灰度旗标 ``LUBAN_QUESTIONS_BANK_SOFT_DELETE_FILTER``（默认 **OFF**）解耦部署顺序。
"新开关默认位=部署序即语义"：谓词若无条件注入，代码就必须晚于 DDL 上线——
早一步 PostgREST 对未知列的过滤参数整条返 400，等于题库检索全断。加旗标后
三步各自独立可回滚：**代码合并部署（OFF，零行为变化）→ 执行 Part A DDL
（加可空列，向后兼容）→ 翻 ON 重启 → live 三通道回归**。

**默认 OFF 为什么是安全的（默认位的立法理由，不是疏忽）**：本轮**没有任何
writer**——四列上线后 ``retired_at`` 全表恒为 NULL，一行退役数据都不存在。
"过滤掉退役行"与"不过滤"在零退役行时是**同一个结果集**，所以 OFF 期间不过滤
无损；等 Part A 落地、第一个退役批（走 manifest 授权）真的写入之前翻 ON，
过滤才开始有语义。翻 ON 早于 DDL 会 400，晚于首个 writer 会漏读退役行——
**正确窗口 = DDL 之后、首个 retire 写入之前**。
见 extractions/supply_soft_delete_20260802/APPROVAL_SHEET.md。
"""

from __future__ import annotations

from deeptutor.services.runtime_env import env_flag

QUESTIONS_BANK_TABLE = "questions_bank"

#: 灰度旗标名。默认 OFF = 逐字节保持收权前行为（论证见模块 docstring）。
SOFT_DELETE_FILTER_FLAG = "LUBAN_QUESTIONS_BANK_SOFT_DELETE_FILTER"

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


def soft_delete_filter_enabled() -> bool:
    """灰度旗标读取点（默认 OFF）。

    默认 OFF 的立法理由见模块 docstring：本轮无 writer，``retired_at`` 全表恒
    NULL，过滤与不过滤结果集相同 → OFF 无损，且让代码可以先于 DDL 安全上线。
    """
    return env_flag(SOFT_DELETE_FILTER_FLAG, default=False)


def apply_live_row_filter(query: dict[str, str]) -> dict[str, str]:
    """向 PostgREST 查询参数注入在服行谓词（原地修改并返回同一 dict）。

    旗标 OFF（默认）时**不注入**，逐字节保持收权前行为——列还没上线时注入
    会让 PostgREST 整条查询返 400。

    fail-closed 的两条与旗标无关、始终生效：
    - 覆写检查：若调用方对生命周期列写了**别的**谓词（例如 ``not.is.null``
      想读退役行），拒绝静默覆写、直接抛错。生产读者没有读退役行的权利；
      治理/审计工具想读全量，就不要走本函数。旗标 OFF 时同样拒绝——
      "开关没开"绝不能变成"绕过收权的后门"。
    - 幂等：重复调用无害。
    """
    existing = query.get(LIVE_ROW_FILTER_COLUMN)
    if existing is not None and existing != LIVE_ROW_FILTER_OPERATOR:
        raise ValueError(
            "questions_bank 生产读取不得覆写生命周期谓词: "
            f"{LIVE_ROW_FILTER_COLUMN}={existing!r} (期望 {LIVE_ROW_FILTER_OPERATOR!r})"
        )
    if not soft_delete_filter_enabled():
        return query
    query[LIVE_ROW_FILTER_COLUMN] = LIVE_ROW_FILTER_OPERATOR
    return query
