"""abs2 供给层软删测绘 — Supabase 只读探针（全部 SELECT，零 DDL/DML）。

复用 qb_governance_20260801/sbclient.py 的 Management API 只读通道。
产物: artifacts/abs2_live_schema_evidence.json
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "docs/原始数据/数据盘点/extractions/qb_governance_20260801"))
import sbclient as S  # noqa: E402

OUT = HERE / "abs2_live_schema_evidence.json"

PROBES = {
    # 1. questions_bank 全列（证明无软删列 + 供审批单基线）
    "columns": """
        select column_name, data_type, is_nullable, column_default
        from information_schema.columns
        where table_schema='public' and table_name='questions_bank'
        order by ordinal_position
    """,
    # 2. 行数基线
    "row_count": "select count(*) as n from public.questions_bank",
    # 3. 全部读 questions_bank 的函数/RPC（库内读者）
    "functions_reading_qb": """
        select n.nspname as schema, p.proname as name,
               pg_get_function_identity_arguments(p.oid) as args,
               p.prosecdef as security_definer
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where p.prosrc ilike '%questions_bank%'
          and n.nspname not in ('pg_catalog','information_schema')
        order by 1, 2
    """,
    # 4. 引用 questions_bank 的视图（库内读者）
    "views_reading_qb": """
        select schemaname, viewname
        from pg_views
        where definition ilike '%questions_bank%'
          and schemaname not in ('pg_catalog','information_schema')
    """,
    # 5. 视图定义原文（v_retrieval_questions 若在）
    "v_retrieval_questions_def": """
        select pg_get_viewdef('public.v_retrieval_questions'::regclass, true) as def
    """,
    # 6. 表上全部约束（含线上独有 CHECK——仓库外 schema 漂移证据）
    "constraints": """
        select conname, contype, pg_get_constraintdef(oid) as def
        from pg_constraint
        where conrelid = 'public.questions_bank'::regclass
        order by conname
    """,
    # 7. 索引清单
    "indexes": """
        select indexname, indexdef from pg_indexes
        where schemaname='public' and tablename='questions_bank'
        order by indexname
    """,
    # 8. 触发器
    "triggers": """
        select tgname, pg_get_triggerdef(oid) as def
        from pg_trigger
        where tgrelid='public.questions_bank'::regclass and not tgisinternal
    """,
    # 9. 外键指向 questions_bank 的表（下游硬引用；预期 0——07-30 盘点称全库无 FK）
    "fks_into_qb": """
        select conrelid::regclass::text as referencing_table, conname,
               pg_get_constraintdef(oid) as def
        from pg_constraint
        where confrelid='public.questions_bank'::regclass and contype='f'
    """,
    # 10. RPC 8 函数逐个拿 prosrc 里 FROM questions_bank 的过滤形态（截取源码）
    "function_sources": """
        select p.proname, left(p.prosrc, 4000) as src
        from pg_proc p join pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public' and p.prosrc ilike '%questions_bank%'
        order by p.proname
    """,
    # 11. 既有备份/快照表先例
    "backup_tables": """
        select table_name from information_schema.tables
        where table_schema='public' and table_name like 'questions_bank%'
        order by table_name
    """,
}

results = {}
for key, sql in PROBES.items():
    try:
        st, rows, _ = S.mgmt_sql(sql)
        results[key] = {"status": st, "rows": rows}
        print(f"[ok] {key}: {len(rows) if isinstance(rows, list) else rows}")
    except Exception as exc:  # noqa: BLE001 — 逐探针容错，missing 视图等不致命
        results[key] = {"error": str(exc)[:500]}
        print(f"[err] {key}: {str(exc)[:200]}")

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print("written", OUT)
