# BI 三源对账差异报告

- 生成时间: 2026-06-12T03:40:18.196244+00:00
- 窗口: 7 天
- 指标总数: 23

## Verdict 汇总

- **consistent**（一致）: 2
- **coverage_gap**（覆盖缺口）: 2
- **definition_mismatch**（口径分歧）: 1
- **missing_source**（缺源）: 18

## coverage_gap（覆盖缺口）

| 指标 | BI 值 | Langfuse | 业务库 | diff% | 说明 | 人工复核 |
| --- | --- | --- | --- | --- | --- | --- |
| registered_members | 98 | · | 2444 | 96.0% | BI(98) 低于真相源 business(2444)——疑似采集缺口 | |
| total_cost_usd | 5.4564 | 6.49287 | · | 16.0% | BI(5.4564) 低于真相源 langfuse(6.49287)——疑似采集缺口 | |

## definition_mismatch（口径分歧）

| 指标 | BI 值 | Langfuse | 业务库 | diff% | 说明 | 人工复核 |
| --- | --- | --- | --- | --- | --- | --- |
| total_tokens | 2.05587e+07 | 11636 | · | 176581.9% | BI(2.05587e+07) 高于真相源 langfuse(11636)——疑似口径分歧或归因错误 | |

## missing_source（缺源）

| 指标 | BI 值 | Langfuse | 业务库 | diff% | 说明 | 人工复核 |
| --- | --- | --- | --- | --- | --- | --- |
| effective_learning_members | 10 | · | · | — | 缺有效读数: truth_source | |
| activated_members | 10 | · | · | — | 缺有效读数: truth_source | |
| success_turn_rate | 98.4 | · | · | — | 缺有效读数: truth_source | |
| avg_session_depth | 2 | · | · | — | 缺有效读数: truth_source | |
| renewal_risk_members | 0 | · | · | — | 缺有效读数: truth_source | |
| member_health_score | 100 | · | · | — | 缺有效读数: truth_source | |
| mastery_improvement | · | · | · | — | 缺有效读数: truth_source | |
| ai_quality_score | 98.4 | · | · | — | 缺有效读数: truth_source | |
| cost_per_effective_learning | 0.5456 | · | · | — | 缺有效读数: truth_source | |
| behavior.module.open_count | · | · | 0 | — | 缺有效读数: truth_source | |
| behavior.learning_report.section_view_count | · | · | 0 | — | 缺有效读数: truth_source | |
| behavior.funnel.report_to_training | · | · | — | — | 缺有效读数: business | |
| behavior.member_ops.report_high_no_action | · | · | — | — | 缺有效读数: business | |
| data_trust_score | · | · | · | — | 缺有效读数: truth_source | |
| today_cost_usd | · | · | · | — | 缺有效读数: truth_source | |
| avg_turn_cost_usd | 0.0106 | · | · | — | 缺有效读数: truth_source | |
| member_active_count | 98 | · | · | — | 缺有效读数: truth_source | |
| expiring_soon_members | 0 | · | · | — | 缺有效读数: truth_source | |

## consistent（一致）

| 指标 | BI 值 | Langfuse | 业务库 | diff% | 说明 | 人工复核 |
| --- | --- | --- | --- | --- | --- | --- |
| active_learning_sessions | 857 | 898 | · | 4.6% | 一致 | |
| notebook_saves | 0 | · | 0 | 0.0% | 一致 | |

## P2 部署后复跑结论（2026-06-12，release d1784d2d）

- **F1 关闭**：total_cost_usd 由部署前 coverage_gap diff 99.7%（BI $0.0198 vs Langfuse $6.49）收敛到 diff 16.0%（UsageLedger $5.4564 vs Langfuse $6.4929）。残差归因：Langfuse 含 model=null 的 0 成本 observations 与定价覆盖差异，列入 P3 常态对账。
- **F5 关闭**：unregistered_labels = []（部署前 6 个）。
- **F3/F4 关闭**：unit_economics.value=0.5456、ai_quality.value=98.4、data_trust.value 显式 null+value_status。
- **F2 保持开放**：行为库仍 0 行，等待小程序带埋点发版（用户操作）；data_trust.degraded_modules 已可见 product_behavior=pending。
