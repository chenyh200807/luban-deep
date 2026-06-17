# BI 三源对账差异报告

- 生成时间: 2026-06-12T02:39:17.108935+00:00
- 窗口: 7 天
- 指标总数: 18

## Verdict 汇总

- **consistent**（一致）: 2
- **coverage_gap**（覆盖缺口）: 2
- **missing_source**（缺源）: 14

## coverage_gap（覆盖缺口）

| 指标 | BI 值 | Langfuse | 业务库 | diff% | 说明 | 人工复核 |
| --- | --- | --- | --- | --- | --- | --- |
| registered_members | 93 | · | 2439 | 96.2% | BI(93) 低于真相源 business(2439)——疑似采集缺口 | |
| total_cost_usd | 0.0198 | 6.49287 | · | 99.7% | BI(0.0198) 低于真相源 langfuse(6.49287)——疑似采集缺口 | |

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
| cost_per_effective_learning | — | · | · | — | 缺有效读数: bi_api | |
| behavior.module.open_count | · | · | 0 | — | 缺有效读数: truth_source | |
| behavior.learning_report.section_view_count | · | · | 0 | — | 缺有效读数: truth_source | |
| behavior.funnel.report_to_training | · | · | — | — | 缺有效读数: business | |
| behavior.member_ops.report_high_no_action | · | · | — | — | 缺有效读数: business | |
| data_trust_score | · | · | · | — | 缺有效读数: truth_source | |

## consistent（一致）

| 指标 | BI 值 | Langfuse | 业务库 | diff% | 说明 | 人工复核 |
| --- | --- | --- | --- | --- | --- | --- |
| active_learning_sessions | 857 | 898 | · | 4.6% | 一致 | |
| notebook_saves | 0 | · | 0 | 0.0% | 一致 | |

## 注册表外 KPI 标签（P2 收口清单）

- 7 天内到期
- 今日成本
- 平均回合成本
- 总 Token
- 活跃会员
- 流失预警

## 人工复核结论（2026-06-12）

### 重大发现（按严重度排序）

1. **F1 成本覆盖缺口 ~328 倍**（`total_cost_usd`，coverage_gap，diff 99.7%）：BI 报 7 天总成本 $0.0198，Langfuse 同窗真相 $6.49。且 BI 内部自相矛盾——`/bi/overview` summary.total_cost_usd=0.0、boss_workbench「今日成本」=0.0，而 `/bi/cost` 报 $0.0198。成本采集链路（UsageLedger→BI）存在系统性缺口，overview 与 cost 两条管线互不相认。**P2 最高优先修复项。**
2. **F2 行为事实层空转**：生产 `product_behavior_events` 表 0 行。注册表 4 个 `behavior.*` 指标（trust_level B）背后没有任何数据流入——PRD 声称的 P0 埋点链路（surface-events → product_behavior.db writer）在生产未生效或未部署。**P2 须先修采集再谈指标。**
3. **F3 已注册未接线**：`cost_per_effective_learning` 在 payload `unit_economics` 暴露但无 value 键（成本与有效学习者都有值，本应可算）；`mastery_improvement`、`data_trust_score` 注册了定义但 payload 无对应数值承载。注册表与实际 payload 脱节。
4. **F4 口径代理失真**：`ai_quality_score`（注册定义为多信号综合质量分）payload 实际承载的是 `engineering_success_rate` 单一代理字段且 `value=None`——展示的"AI 质量"并非注册口径。
5. **F5 注册表外 KPI 标签 6 个**：`7 天内到期 / 今日成本 / 平均回合成本 / 总 Token / 活跃会员 / 流失预警` 出现在 BI 卡片但无法解析回 `BI_METRICS`——前端展示存在第二套未登记口径。**P2 强制契约的直接整改清单。**

### 复核裁定（verdict 修正）

- `registered_members`（coverage_gap, diff 96.2%）→ **改判 definition_mismatch（已解释）**：BI 93 为 member_console canonical 过滤口径（真实手机号），v_members 原始 2439 行含未过滤身份。非缺口；但 canonical 口径外部不可独立复算是 P1 已知限制，P2 应导出可复算口径。
- `active_learning_sessions`（consistent, diff 4.6%）：BI 会话 857 vs Langfuse traces 898，口径不同但量级互证成立，**维持 consistent，可信**。
- `notebook_saves`（consistent, 0=0）：**空洞一致**——双侧都是 0 是因为行为库为空（见 F2），不代表链路健康。
- 其余 `missing_source` 为声明性缺口（派生口径/无外部真相源），P1 如实记录。

### 量级互证快照

| 量 | BI | 真相源 | 结论 |
| --- | --- | --- | --- |
| 7d 总成本 | $0.0198 | Langfuse $6.49 | **缺口 ~328x** |
| 7d 会话/traces | 857 | 898 | 互证成立 |
| 7d Token | 113,628 | Langfuse >1M（单日 6-11 即 ~592k） | 量级缺口与成本同源 |
| 会员数 | 93（canonical） | 2,439（raw） | 过滤口径差，已解释 |
