# 成本自校准治理系统实施计划

- 状态：`Draft → 执行中（2026-06-12）`
- 决策人：用户（2026-06-12）
- 上游：`2026-06-12-bi-systematic-upgrade-design.md`、`bi-cost-reconciliation-truth`（记忆）
- 核心理念（用户原话）：**官方账单为锚（权威）+ 实时 token 统计保留（快速反馈）+ 自己的算法不断和官方校准**

## 背景与根因

BI 内账成本 ¥5.43 只覆盖阿里云官方账单 ¥29.22 的 **18.6%**。根因三层：

1. **定价表币种错配（主因，~7x）**：`langfuse_adapter.py` 的 `_BUILTIN_PRICING` 里 deepseek/qwen 单价标 `currency: USD`（deepseek-v4-flash input `0.14`/output `0.28`），但全系统把成本数字当 CNY 用。USD 单价当 CNY → 低估约 7 倍（汇率）。阿里云真实计费：deepseek-v4-flash 输入 ¥1/百万、输出 ¥2/百万。
2. **token 漏 38%**：内账 2041万 vs 官方百炼 3303万，部分调用未写入 UsageLedger。
3. **DeepSeek 直连无账单对账**：DeepSeek 官方无账单 API（仅余额 + 手动 CSV），内账 ¥0.02 vs 官方 ¥19.79 漏 1000 倍。

## 目标

1. **DeepSeek 统一迁阿里云**：消除 DeepSeek 直连，全部走阿里云百炼 deepseek-v4（价格与官网一致、可用性 88% vs 官方 42%、质量同模型、成本可自动对账）。
2. **定价表币种修正**：deepseek/qwen 单价改为阿里云真实 CNY 单价。
3. **自校准算法**：用官方账单 model 级金额持续反推真实单价，校准内账定价表，让实时内账逐渐逼近官方真值。
4. **成本卡以官方账单为锚 + 实时统计并存**：主数字官方账单（权威），实时内账（校准后估算）并列，显示校准偏差。

## 非目标

- 不引入实时汇率 API（用户明确忽略货币换算，阿里云本就 CNY 计费）。
- 不改 `/api/v1/ws` 聊天 contract。
- 不在本计划内做 DeepSeek CSV 自动导入（迁阿里云后 DeepSeek 直连消费归零，无需）。

## 自校准算法设计（核心）

```
对每个 model M（在某账期/窗口内）：
  internal_tokens[M]   = UsageLedger.get_window_summary().by_model[M].total_tokens   (实时统计，已有)
  official_amount[M]   = bailian_billing.model_amounts[M]                            (官方账单，已有)
  真实单价[M]          = official_amount[M] / internal_tokens[M]                      (CNY/token，反推)
  校准系数[M]          = 真实单价[M] / 当前定价表单价[M]
应用：
  校准后内账成本[M]    = internal_tokens[M] × 真实单价[M]   ≈ 官方真值
  全局校准偏差         = Σ校准后内账 / 官方账单总额          (健康度，越接近 1 越准)
```

- 校准系数持久化（`data/user/cost_calibration.json`），定期/手动用最新账单刷新。
- token 漏记部分：校准系数会自动吸收（真实单价被推高以补偿漏 token），但同时记录 `token_coverage_ratio` 作为独立健康指标，提示漏记需修。
- **单一 authority**：官方账单是成本真值锚；自校准只调整内账估算单价，不改官方账单。

## 实施阶段

### P1 定价表币种修正（BI 层，低风险，先做）
- `langfuse_adapter.py:_BUILTIN_PRICING` 的 deepseek/qwen 条目：`currency` USD→CNY，单价改阿里云官方 CNY 值（deepseek-v4-flash ¥1/¥2、deepseek-v4-pro ¥3/¥6、qwen-* 按阿里云定价）。
- 影响：所有新成本计算用 CNY 单价；历史 ledger 成本不变（已落库）。
- 测试：定价解析单测。

### P2 自校准模块（BI 层）
- 新模块 `deeptutor/services/observability/cost_calibration.py`：算/存/读 model 级校准系数与 token 覆盖率。
- 输入官方账单 model_amounts + 内账 by_model token，输出校准系数 + 全局偏差 + 覆盖率。
- BI 成本读取应用校准系数（成本卡显示校准后估算）。
- 测试：校准算法单测（含漏 token 吸收、零除保护）。

### P3 成本卡以官方账单为锚（前后端）
- 成本卡主数字 = 当月官方账单（缓存查询，TTL 避免拖慢页面）。
- 副 = 实时内账（校准后）+ 校准偏差徽标（如"校准偏差 5%"）。
- 趋势图 = 日成本内账明细。
- 用户口径选择：3（大数字真账单 + 趋势内账）。

### P4 DeepSeek 迁阿里云（LLM 调用层，高风险，独立谨慎做）
- `deeptutor/services/llm/factory.py`、`provider_registry.py`、`tutorbot/providers/registry.py`：DeepSeek 直连改路由到阿里云百炼 deepseek-v4。
- **必须**：迁移后回归测试聊天/评分功能不受影响；保留回滚开关。
- 迁移后 DeepSeek 直连消费归零，成本全部经阿里云自动对账。

## 验收

- P1：deepseek/qwen 定价 CNY；新成本计算量级对齐官方（内账总额接近官方账单）。
- P2：自校准系数生成；成本卡校准后估算 vs 官方账单偏差 < 15%。
- P3：成本卡主数字 = 官方账单；偏差徽标可见。
- P4：DeepSeek 全走阿里云；聊天/评分回归通过；DeepSeek 直连消费归零。

## 相关代码入口

`deeptutor/services/observability/langfuse_adapter.py`（定价表）· `deeptutor/services/observability/usage_ledger.py`（by_model 统计）· `deeptutor/services/bi_service.py`（成本展示/对账）· `deeptutor/services/llm/factory.py` + `provider_registry.py`（P4 provider 迁移）· `web/components/bi-cockpit/`（P3 成本卡）

## 待用户确认/提供

- **DeepSeek 余额疑点**：.env 的 `DEEPSEEK_API_KEY` 拉到 ¥15.72，用户截图 ¥40.79——确认是否同一账户（不同则对账数据错）。迁阿里云后此疑点消失。
