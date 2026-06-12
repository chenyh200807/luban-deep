# BI 系统性升级：数据治理 + Langfuse 双轨 + 设计升级（路线 B 双线并行）

- 状态：`Draft`
- 日期：2026-06-12
- 入口页面：`https://test2.yousenjiaoyu.com/bi`
- 决策人：用户（已确认路线 B：数据线 + 设计线并行）

## 背景与痛点

BI 驾驶舱已于 2026-06-08 完成 ECharts 6 重做（5 个 tab 全部驾驶舱化，已合入 main 并部署 test2）。但数据层"只是够用"，用户确认四类痛点**全部存在**：

1. **数据不真实/不准**：BI 显示值与 Langfuse / 业务库真实情况对不上。代码级根源之一：`deeptutor/services/bi_service.py` 中 token/成本指标为 measured + estimated 相加后丢失血统（`LlmRollup.total_* = measured_* + estimated_*`），前端无法区分真测与估算。
2. **指标定义混乱**：同一指标跨 tab 口径不一致，算法不透明。`bi_metrics.py` 已有 `BIMetricDefinition` 注册表雏形（261 行）但未强制覆盖全部指标。
3. **数据覆盖不全**：部分真实业务事件（LLM 调用、评分、会员行为）未被采集进 BI。
4. **归因/识别错误**：数据归到错误的模块/用户/渠道，trace 与业务实体关联不正确。

## 目标

1. BI 每个指标可对账：与 Langfuse + 业务库逐指标核对，差异有报告、有 verdict、有修复闭环。
2. 指标单一权威：所有 BI 指标必须在指标注册表声明口径、数据源、measured/estimated 血统、新鲜度、归因键；未注册指标不得出现在 BI payload。
3. Langfuse 双轨：对账常态化（定时 + 差异告警），且经 P1 证实更准的 AI 指标改为 Langfuse 直连。
4. UI/UX 再升级一轮：对标顶级 BI 产品的交互深度，且"数据可信度"成为设计语言的一部分。

## 非目标

- 不引入第三方 BI 平台（Metabase/Lightdash 等），继续自有驾驶舱。
- 不改动 `/api/v1/ws` 等聊天链路 contract（BI 只读消费 observability 数据）。
- 不在本计划内重做小程序端 BI 展示。
- 不推翻 ECharts 6 技术栈（设计升级在其上迭代）。

## 单一 Authority

- **指标口径唯一权威**：`deeptutor/services/bi_metrics.py` 的 `BIMetricDefinition` 注册表（P2 扩建后）。前端/驾驶舱组件永不自行聚合或二次计算指标。
- **AI 调用真相源**：Langfuse（阿里云部署，经 `deeptutor/services/observability/langfuse_adapter.py` 接入）。
- **业务真相源**：业务库（订单/会员/评分事件）。
- 对账 harness 只做三源比对，自身不成为第四个 authority。

## 总体架构：双线并行 + 指标契约合流

```
数据线:  P1 对账取证 ──→ P2 治理重建 ──→ P3 Langfuse 双轨常态化
                                  │
                          指标契约 (bi_metrics.py 单一权威)
                                  │
设计线:  P4a 设计探索(shotgun) ──→ P4b 定稿 ──→ P4c 按契约实现
```

两线靠指标契约解耦：设计线可先用现有 payload 类型出稿，但任何"指标怎么算"以数据线指标字典为准。

## 实施阶段

### P1 数据真相审计（数据线，纯取证，不改产品代码）

- 新增 `scripts/bi_reconciliation/`：
  - 取数器 ①：Langfuse API（traces / observations / usage，按天聚合）。
  - 取数器 ②：业务库只读查询（订单、会员、评分事件）。
  - 取数器 ③：BI API 实拍（调 `getBiOverview` 等后端接口，取 BI 当前展示值）。
  - 对账引擎：同一指标三源对比，输出 `{metric_id, bi_value, langfuse_value, db_value, diff_pct, verdict}`，verdict ∈ {一致 / 估算污染 / 覆盖缺口 / 归因错误 / 口径分歧}。
- 产物：《指标差异报告》（JSON + Markdown）+ 初版《指标字典》，写入主 repo `artifacts/bi_reconciliation_<date>/`（不放临时 worktree，防 `worktree remove --force` 删 artifacts）。
- 运行环境：阿里云（Langfuse 与生产库所在地），全程只读，严守 AGENTS §3.7 写边界（仅 `/root/deeptutor` 内可写）。

### P2 数据治理层重建（数据线）

- `BIMetricDefinition` 扩为强制契约：每指标必须声明 `formula / sources / measured_vs_estimated / freshness / attribution_key / langfuse_mapping / degraded_behavior`。
- 加 contract 测试守门：BI payload 中出现未注册指标即失败；测试按规矩登记进 `contracts/index.yaml` 对应 domain 的 `test_files`（contract_guard required gate）。
- measured/estimated 在 payload 层分离，前端每个数字带 provenance，不再相加丢血统。
- 按 P1 差异报告逐项修复采集缺口与归因错误（每项独立 commit，引用报告条目）。
- `bi_service.py`（3779 行）按域拆为 `deeptutor/services/bi/` 包：overview / feedback / commerce / member / ops 各自模块 + 共享取数层。拆解为纯结构性移动，行为以 P1 报告 + contract 测试为基准回归。

### P3 Langfuse 双轨常态化（数据线）

- 对账脚本进定时任务，差异超阈值生成 ops tab 告警项（复用现有 alerts 通道）。
- 依据 P1 证据，把 Langfuse 更准的 AI 指标（成本 / token / 延迟 / 评分）切为 Langfuse 直连（经 `langfuse_adapter`，带降级路径：Langfuse 不可用时回落业务库值并标注 provenance=fallback）；其余指标保持业务库。

### P4 设计线：再一轮设计升级

- **P4a 探索**：`gstack-design-consultation` 做设计体系咨询（对标 Grafana / Lightdash / 顶级驾驶舱），再 `gstack-design-shotgun` 出 3-4 个方向可视对比稿。是否保留暖陶土橙品牌色作为显式问题交用户选，不预设。
- **P4b 定稿**：用户从对比稿选定方向，固化设计 token 与组件规范（迭代 `web/components/bi-cockpit/theme.ts`）。
- **P4c 实现**：升级主轴四项——
  1. 全局控制层：跨 tab 统一时间范围 / 环比 / 维度筛选器。
  2. 数据可信度即 UI：provenance / 新鲜度 / measured-estimated 徽标进入设计语言。
  3. 下钻一致性：四级下钻交互在 5 个 tab 统一。
  4. 性能：大屏图表懒加载与增量刷新。
- 实现期严守 Web 内存护栏（AGENTS §Web Memory Guardrails）：dev server 不挂 agent 名下；截图走"起→截→立即杀→复检"。

## 验收标准

- P1：5 个 tab 全部指标均有三源对账记录与 verdict；差异报告 + 指标字典落 artifacts 并可复跑。
- P2：contract 测试通过（未注册指标进 payload 即红）；P1 报告中 verdict ≠ 一致的条目全部关闭或显式标注 known-gap；`bi_service.py` 拆包后 tsc/eslint/pytest 与拆前行为一致。
- P3：对账定时任务连续 7 天产出；差异告警可在 ops tab 看到；Langfuse 直连指标具备降级路径并有测试。
- P4：设计稿经用户拍板；实现上 test2 后用对账 harness 复测"UI 显示值 = 治理后真值"；内存护栏全程无违规。

## 相关代码入口

- 后端数据层：`deeptutor/services/bi_service.py`、`deeptutor/services/bi_metrics.py`、`deeptutor/services/observability/langfuse_adapter.py`、`deeptutor/services/observability/`
- 前端：`web/app/(workspace)/bi/`、`web/components/bi-cockpit/`（theme.ts / Charts.tsx / 各 *Cockpit.tsx）、`web/components/bi-v2/`
- 既有文档：`docs/zh/bi/deeptutor-bi-data-blueprint.md`、`docs/zh/bi/deeptutor-bi-prd.md`
- Contract 控制面：`contracts/index.yaml`（P2 注册 domain 测试）

## 会员口径与上线基准（用户 2026-06-12 决策）

- **会员数用保守口径**：当前 BI 显示 ~98（受信来源 `phone_backfill/phone_verification` + 中国大陆手机号去重），其余 1578 个有手机号记录是导入/未验证名单，**非真实付费用户**，不计入。用户确认此口径正确。
- **上线基准（待下周实施）**：系统计划 2026-06 下旬上线。上线后，以**上线时间点**为基准，**之后新注册的才算真实用户**。需在 member_console 会员口径增加 `real_user_since` 时间门（env 或配置），上线当天设定。当前不实现，作为上线 checklist 项。

## 历史数据完整性（用户 2026-06-12 要求"全部历史数据"）

- 现状：30 天窗口成本 BI $5.47 vs Langfuse $10.5（48% 残差），会话 857 vs traces 1766——UsageLedger 与 session store 较新全量启用，**30 天前历史不全**；7 天窗口残差仅 16%（正常）。
- 待办：评估从历史 turn 事件 `cost_summary` / Langfuse 导出 backfill UsageLedger，补齐长窗口成本/token；或在 30 天+视图标注"历史数据自 X 日起完整"。`bi_service.backfill_usage_ledger` 已有雏形可复用。注意：下周上线前数据均为测试数据。

## 风险与回滚

- 指标切 Langfuse 直连后 Langfuse 故障 → provenance=fallback 回落业务库，UI 显示降级徽标。
- `bi_service.py` 拆包引入回归 → 拆解独立 PR，以 P1 报告值为黄金基准做前后对拍。
- 设计线先行实现与 P2 契约冲突 → 合流点规则：UI 只消费契约 payload，冲突时数据线赢。
