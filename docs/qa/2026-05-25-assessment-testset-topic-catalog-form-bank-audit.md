# Assessment Topic Catalog Form Bank Audit

Date: 2026-05-25

Command:

```text
PYTHONPATH=. python scripts/seed_assessment_topic_catalog_forms.py --dry-run --json --out-json artifacts/assessment_flywheel/p0b-p1-flywheel-verify/topic_catalog_dry_run.json --out-md docs/qa/2026-05-25-assessment-testset-topic-catalog-form-bank-audit.md
```

Source authority: `deeptutor/services/assessment/topic_catalog.py`.

Result: all 10 required P0B topics are `stable` with 5 persisted forms each.

## Topic Labels

| topic_id | label |
| --- | --- |
| waterproof | 防水工程 |
| decoration | 装饰装修 |
| mep | 建筑机电 |
| foundation | 地基基础 |
| main_structure | 主体结构 |
| formwork_scaffold | 模板脚手架 |
| safety | 安全管理 |
| schedule | 进度计划 |
| contract_claim | 合同索赔 |
| quality_acceptance | 质量验收 |

## Form Bank Status

| topic_id | status | form_count | persisted | source |
| --- | --- | ---: | --- | --- |
| waterproof | stable | 5 | False | supabase_persisted |
| decoration | stable | 5 | False | supabase_persisted |
| mep | stable | 5 | False | supabase_persisted |
| foundation | stable | 5 | False | supabase_persisted |
| main_structure | stable | 5 | False | supabase_persisted |
| formwork_scaffold | stable | 5 | False | supabase_persisted |
| safety | stable | 5 | False | supabase_persisted |
| schedule | stable | 5 | False | supabase_persisted |
| contract_claim | stable | 5 | False | supabase_persisted |
| quality_acceptance | stable | 5 | False | supabase_persisted |
