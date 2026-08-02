# Migration 审批单 — questions_bank 软删两件套（task#31，等 owner 过目，未执行）

- 目标库：Supabase 项目1 `zgupgizexqpwtajvghno` / `public.questions_bank`（2026-08-02 live 基线：4635 行 / 42 列 / 8 RPC / 1 视图，证据 `live_schema_evidence.json`）
- **执行零件**：`supabase/migrations/20260802000100_questions_bank_soft_delete.sql`（Part A）→ `20260802000200_questions_bank_reader_soft_delete_filter.sql`（Part B）。**顺序不可反**（Part B 引用 Part A 的列）。
- **执行前必做**（"线上 schema ≠ 仓库 migration 之和"已两次实证——CHECK 白名单事件 + 本次 8 RPC 不在仓）：
  ```sql
  -- 只读预检 1：列不存在（预期 0 行）
  select column_name from information_schema.columns
  where table_schema='public' and table_name='questions_bank'
    and column_name in ('retired_at','retired_reason','retired_batch','superseded_by');
  -- 只读预检 2：行数与函数清单对齐基线（预期 4635 / 8 行）
  select count(*) from public.questions_bank;
  select p.proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.prosrc ilike '%questions_bank%' order by 1;
  -- 只读预检 3：函数体与抓取基线未漂移（对照 live_function_defs.json 的 def 逐一 diff）
  ```
  预检 3 若发现任何函数体与 2026-08-02 抓取件不同 → **停**，重抓重审（说明有第三方在改库内函数）。

---

## Part A（20260802000100）：加列 + 约束 + 索引

| # | SQL（摘要，全文见 migration 文件） | 影响行数预估 | 回滚 |
|---|---|---|---|
| A1 | `alter table … add column if not exists retired_at timestamptz, retired_reason text, retired_batch text, superseded_by bigint` | **0 行数据变化**（全可空零默认；4635 行元组不重写，PG 11+ 加可空列仅改 catalog） | A-R1 |
| A2 | `add constraint check_qb_retired_requires_reason`（retire 必带 reason） | 0（validate 扫全表 4635 行，全 NULL 必过） | A-R2 |
| A3 | `add constraint check_qb_live_row_no_retire_meta`（在服行禁带退役元数据——防半截状态） | 0（同上） | A-R2 |
| A4 | `add constraint check_qb_superseded_not_self` + `questions_bank_superseded_by_fkey`（自 FK） | 0 | A-R2 |
| A5 | `create index questions_bank_retired_batch_idx … where retired_at is not null`（部分索引，治理/回滚用） | 0（当前 0 行满足谓词，索引近空） | A-R3 |

**Part A 回滚（A-R，逐条）**——⚠️ 会连带清掉执行后写入的一切退役标记，回滚前先 `select count(*) … where retired_at is not null` 确认为 0 或已导出：

```sql
-- A-R3
drop index if exists public.questions_bank_retired_batch_idx;
-- A-R2
alter table public.questions_bank
    drop constraint if exists questions_bank_superseded_by_fkey,
    drop constraint if exists check_qb_superseded_not_self,
    drop constraint if exists check_qb_live_row_no_retire_meta,
    drop constraint if exists check_qb_retired_requires_reason;
-- A-R1
alter table public.questions_bank
    drop column if exists superseded_by,
    drop column if exists retired_batch,
    drop column if exists retired_reason,
    drop column if exists retired_at;
```

**风险点（如实）**：
- A1 需要表级 ACCESS EXCLUSIVE 锁瞬时（catalog-only，毫秒级；避开组卷高峰即可）。
- PostgREST schema cache 会在 DDL 后自动刷新（NOTIFY pgrst）；若托管版延迟，新列过滤在刷新前对 REST 不可见——**Part A 执行后先跑一发 `select=retired_at&limit=1` 确认 REST 可见，再部署应用代码**。

## Part B（20260802000200）：9 个库内读者收权

| # | 对象 | 改动 | 影响行数预估 | 回滚 |
|---|---|---|---|---|
| B1 | `search_questions_bank_vector` | WHERE 追加 `qb.retired_at IS NULL` | 0（换函数体；当前 0 行 retired → 结果集暂时不变） | rollback_20260802000200.sql |
| B2 | `search_questions_bank_text` | 同 | 0 | 同 |
| B3 | `search_questions_bank_text_ranked` | candidates CTE 追加谓词 | 0 | 同 |
| B4 | `search_questions` | 同 | 0 | 同 |
| B5 | `search_questions_by_keywords`（SECDEF） | scored CTE 追加谓词（原 OR 条件加括号包裹，语义不变） | 0 | 同 |
| B6 | `match_questions`(SECDEF) | ranked CTE 追加谓词 | 0 | 同 |
| B7 | `get_questions_quality_stats_v2` | norm CTE 追加谓词（口径=只算在服行） | 0 | 同 |
| B8 | `refresh_syllabus_stats` | qb_stats CTE + 归零分支 NOT EXISTS 同步追加 | 0（本身是 UPDATE syllabus_tree 的定时器，行为在有 retired 行前不变） | 同 |
| B9 | 视图 `v_retrieval_questions` | WHERE 追加谓词（列清单逐字保持，含原重复 id 投影） | 0 | 同 |

**Part B 回滚**：`rollback_20260802000200.sql`（本目录）——9 个对象的 live 抓取原文逐字回放，不依赖记忆。

**风险点（如实）**：
- B1-B9 全部签名/返回列不变，PostgREST RPC 端点零变化；SECDEF 两函数保持 SECDEF + `SET search_path TO 'public'` 不动。
- B5 的谓词把原 `where a or b` 收为 `where retired_at is null and (a or b)`——括号是语义必需，diff 时请注意这是唯一一处结构性改写。
- text_ranked 的 `ORDER BY qb.id DESC LIMIT probe_k` 探针窗形态未动——收权不借机改排序。

## 执行后验证（宣称"生效"前必做）

```sql
-- 1) 9 对象全部含谓词（预期 9）
select count(*) from (
  select p.proname as n, p.prosrc as s from pg_proc p join pg_namespace pn on pn.oid=p.pronamespace
  where pn.nspname='public' and p.prosrc ilike '%questions_bank%'
  union all
  select 'v_retrieval_questions', pg_get_viewdef('public.v_retrieval_questions'::regclass,true)
) t where s ilike '%retired_at is null%';
-- 2) 结果集守恒（0 行 retired 时收权前后逐字节等价）：
--    对固定题面各打一发 search_questions_bank_text / _vector，与执行前留样 diff。
-- 3) 灵敏度实测（用一行低风险行做 canary retire → 三通道确认不可达 → 立即 un-retire）：
--    此步骤属于 B1 批执行任务，须走 retirement manifest 授权（production_authorized=true），本审批单不涵盖。
```

## 与应用代码的部署顺序（硬约束）

1. owner 审批 → 执行 Part A → REST 可见性确认；
2. 执行 Part B → 执行后验证 1/2；
3. 合并部署本分支应用代码（读侧 `retired_at=is.null` 过滤；**先合代码后跑 DDL 会让 PostgREST 对含过滤参数的查询返 400 → 题库检索全断**，见设计稿 §2.3）；
4. 之后 B1 批退役才允许开始（另行审批，走 manifest 授权位）。
