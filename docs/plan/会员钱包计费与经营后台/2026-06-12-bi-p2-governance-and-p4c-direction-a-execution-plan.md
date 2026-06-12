# BI P2 数据治理修复 + P4c 方向 A 前端实现 执行计划

- 状态：`Draft → 执行中（2026-06-12）`
- 上游：spec `2026-06-12-bi-systematic-upgrade-design.md`；取证 `artifacts/bi_reconciliation_20260612/`；方向定稿（用户拍板 A）`2026-06-12-bi-vnext-design-direction-decision.md`
- 决策依据：root-cause-debugging 调查（2026-06-12，见下）

## 根因结论（设计前强制五项）

### F1 成本缺口 328x + overview/cost 自相矛盾

1. **one business fact**：窗口内平台 AI 总成本/总 Token（含 measured/estimated 血统）。
2. **one authority**：`deeptutor/services/observability/usage_ledger.py` 的 `UsageLedger`（账单对账计划钦定的 per-call charge attribution authority；生产 7 天 2356 条 / $5.46，与 Langfuse $6.49 同量级；measured/estimated 天生分列）。
3. **concepts to delete or demote**：① `get_cost_stats`/`get_overview` 各自汇总 turn 事件内嵌 `cost_summary` 镜像的两条管线（降级：cost_summary 仅作 turn 级明细，不再做窗口总账）；② overview 对成本套 `_scope_context_to_registered_members` 的旁路决策（平台成本不是会员子集事实）。
4. **why not the old pattern**：turn 镜像只覆盖聊天 turn 内已捕获的调用，漏掉 RAG rerank/embedding、评分 jury、合成等大头（328x 实证）；两个 reader 各自决策产生第二套 truth（0.0 vs 0.0198 自相矛盾实证）。
5. **why this layer**：deterministic——成本是记账事实，必须由唯一 ledger 聚合，不存在语义判断。

### F2 行为库 0 行

- 服务端链路健康（容器内探针 ingest→落库→删除验证通过）；生产 168h 0 次 surface-events HTTP 调用。
- **根因在客户端**：已发布的小程序包未携带 packageDeeptutor 埋点（代码在仓库、不在线上包）；且端点要求登录态（SR1），匿名流量设计上不进。
- **P2 范围内动作**：BI 侧如实降级（behavior 指标 trust 注记已有；data_trust degraded_modules 增加 behavior 模块 pending 状态）；**修复主体=小程序发版，需用户在微信平台操作，超出本计划边界，列入交接清单**。

### F3/F4/F5

- F3：`unit_economics`（cost_per_effective_learning）payload 不带 value 键——接线缺失，可由 ledger 成本 ÷ north_star 直接计算；`data_trust_score` 可由 degraded_modules ready 占比确定性计算；`mastery_improvement` 维持显式降级（样本不足），但 payload 必须带 `value: null + degraded: true` 而非缺键。
- F4：`ai_quality_score` 注册定义（综合分）与 payload 承载（engineering_success_rate）不一致——本阶段修注册定义对齐现实（v1=工程成功率代理，综合分列入 P3），并把 value 接线。
- F5：6 个未登记 KPI 标签 → 注册表补全（新 metric 或 label_aliases），并给 cards 增加 `metric_id` 字段 + contract 测试「payload 卡片标签必须可解析回注册表」。

## 非目标（本计划不做）

- `bi_service.py` 按域拆包（3779 行）——独立结构性 PR，不与行为变更混合（§3 Surgical Changes）。
- Langfuse 直连切换（P3）；对账 cron 常态化（P3）。
- 小程序发版（用户操作）。
- C 案语义弹卡/边框色温（用户已否决）。

## 实施任务

1. **T1** `UsageLedger.get_window_summary(start_ts, end_ts)`：totals（measured/estimated 分列）+ by_model + by_usage_source 聚合（TDD）。
2. **T2** `get_cost_stats` 收权改读 ledger：cards 带 measured/estimated 分量与 `provenance: usage_ledger`；models/providers 改 ledger 分组；turn 镜像汇总删除。
3. **T3** `get_overview` 成本块改读同一 ledger 聚合（删 member-scope 旁路）；`unit_economics.value`、`ai_quality.value`、`data_trust.score` 接线；`mastery_improvement` 显式 degraded。
4. **T4** F5 注册表补全 + cards 携带 `metric_id` + contract 测试（未注册标签即红）。
5. **T5** registry 文案对齐（total_cost_usd 的 degraded_note 更新为 ledger 口径、ai_quality 定义 v1 化）。
6. **T6** 对账 harness mapping 适配新 payload，全量 pytest + live 复跑，验证 F1 从 99.7% 缺口收敛到 ledger vs Langfuse 残差（预期 ~16%，残差归因列入 P3 对账）。
7. **T7** 走 `deeptutor-aliyun-release` 发 test2，公网复跑 harness 验收。
8. **T8（P4c 方向 A）**：`web/components/bi-cockpit/` 增加全局控制条（时间范围/环比）、KPI 可信度徽标（trust_level 色阶+数据源 chip+新鲜度+measured/estimated 微条，数据来自 cards.metric_id→注册表 payload）、下钻面包屑；tsc/eslint 0；上 test2 截图验收（内存护栏：起→截→杀）。

## 验收

- overview 与 cost 同窗成本数值一致且 = ledger 聚合；measured/estimated 在 payload 分列。
- 对账 harness：`total_cost_usd` verdict 脱离 coverage_gap（≤ ledger vs Langfuse 残差并有归因注记）；`unregistered_labels` 清零。
- 全量相关 pytest 绿；test2 公网验证；`/bi` overview 可见方向 A 升级。

## 相关代码入口

`deeptutor/services/observability/usage_ledger.py` · `deeptutor/services/bi_service.py`（get_cost_stats L2148 / get_overview L1260）· `deeptutor/services/bi_metrics.py` · `web/components/bi-cockpit/` · `scripts/bi_reconciliation/`
