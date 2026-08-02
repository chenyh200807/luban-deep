-- questions_bank 软删列（task#31 供给层版本化+软删 Part A）
-- 设计依据: docs/原始数据/数据盘点/2026-08-02-questions_bank软删版本化读者测绘与设计.md §2.1
-- 审批单: docs/原始数据/数据盘点/extractions/supply_soft_delete_20260802/APPROVAL_SHEET.md
--
-- ⚠️ 本文件尚未在任何库执行（等 owner 过目审批单）。
-- 纯加列 + 约束，全可空零默认 → 对既有 4635 行零数据变化、零行为变化
--（行为变化在 Part B 读侧收权 + 应用代码，见 20260802000200）。
--
-- 生命周期唯一判据 = retired_at（不建 status 枚举——一个事实一个列，防第二权威）。
-- UNIQUE(original_id) 有意保留占号：retired 行继续占住 original_id，同源重入库
-- 会撞唯一约束大声失败——这是对 449 行 re-ingest 病的免疫机制，不是 bug。

alter table public.questions_bank
    add column if not exists retired_at timestamptz,
    add column if not exists retired_reason text,
    add column if not exists retired_batch text,
    add column if not exists superseded_by bigint;

comment on column public.questions_bank.retired_at is
    '软删时刻（非 NULL = 已退役，不可达任何生产读者）。生命周期唯一判据；task#31 2026-08-02';
comment on column public.questions_bank.retired_reason is
    '退役原因（人读）。retire 时必填（CHECK 强制）';
comment on column public.questions_bank.retired_batch is
    '退役批次键（如 B1_reingest_delete_safe_20260802），指向 extractions/supply_soft_delete_20260802/manifests/ 下的 manifest；回滚按批';
comment on column public.questions_bank.superseded_by is
    '正主指针：重复家族 drop→keep 映射（reference_remap.json 190 条为首批数据源）。有值必已 retired（CHECK 强制）';

-- 约束：钉死半截状态（元数据与生命周期位必须同进退）
alter table public.questions_bank
    add constraint check_qb_retired_requires_reason
    check (retired_at is null or retired_reason is not null);

alter table public.questions_bank
    add constraint check_qb_live_row_no_retire_meta
    check (
        retired_at is not null
        or (retired_reason is null and retired_batch is null and superseded_by is null)
    );

alter table public.questions_bank
    add constraint check_qb_superseded_not_self
    check (superseded_by is null or superseded_by <> id);

alter table public.questions_bank
    add constraint questions_bank_superseded_by_fkey
    foreign key (superseded_by) references public.questions_bank(id);

-- 治理/回滚用部分索引：按批列出退役行。主读路径谓词 retired_at IS NULL 不需要
-- 索引（ilike/向量扫描形态不变；HNSW 不支持部分索引，retired 占比小影响可忽略）。
create index if not exists questions_bank_retired_batch_idx
    on public.questions_bank (retired_batch)
    where retired_at is not null;
