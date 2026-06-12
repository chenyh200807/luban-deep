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

---

## P4 执行清单（新对话用——`做 BI 成本治理 P4`）

> 状态：`Pending / 新对话执行`。本清单是 P1-P3 上线后(生产 SHA d52269308 含成本卡官方账单为锚)的剩余工作。P4 改生产聊天的 LLM 调用，**高风险，必须独立对话 + 充分回归**。

### 背景速接（新对话先读）
- 记忆 `bi-cost-reconciliation-truth` + `bi-systematic-upgrade-program` 有全部上下文。
- 已完成：P1 定价表 CNY 修正(含 cache 价)、P2 自校准(`cost_calibration.py`，官方账单反推系数)、P3 成本卡官方账单为锚(`BiCostOfficialAnchorCard`)、对账口径修复(reconciliation 用 UsageLedger 全局)、管理员入口。
- 核心认知：成本要可靠的根因是「成本归属」——官方账单混了 DeepTutor 产品消费 + 共用 `.env` key 的其他项目消费(DeepSeek 后台 6437万token/1309次 vs 内账 14万/309次，差 1000 次非 DeepTutor)。Codex 用 OpenAI、Claude Code 用 Anthropic，都不碰 DeepSeek/阿里云 key——「幽灵消费」是别的项目/脚本共用同一 `.env` 的 DeepSeek/DashScope key。

### 任务 A：DeepTutor 生产配独立 API key（成本归属，最优先）
- **为什么先做**：不分 key，永远分不清产品成本 vs 个人/其他项目消费，对账健康度永远 < 1。
- **步骤**：
  1. 阿里云百炼控制台为 DeepTutor 生产建专属 API key（`DASHSCOPE_API_KEY` / Bailian）；DeepSeek 同理(若不迁阿里云)。
  2. 阿里云 `/root/deeptutor/.env` 换成专属 key（备份 + recreate）。本机/其他项目 `.env` 保留各自的 key。
  3. 对账锁定 DeepTutor 的 `apikey_id`（reconciliation 已支持 `apikey_id` 过滤，当前 `2880115`——确认这是不是 DeepTutor 专属）。
  4. 验收：换 key 后官方账单(按新 key 过滤) ≈ 内账范围，自校准健康度逼近 1.0。
- **当前 key 指纹**(去后台核对哪个在烧钱)：DEEPSEEK `1d5312a99f50`(…e14a)、DASHSCOPE `cf817c5fa7c9`(…486e)。

### 任务 B：DeepSeek 统一迁阿里云（消除 DeepSeek 直连对账盲区）
- **为什么**：DeepSeek 官方无账单 API(只能手动 CSV)；阿里云 deepseek-v4 价格与官网一致、可用性 88% vs 42%、质量同模型、成本可自动对账。
- **改动文件**：`deeptutor/services/llm/factory.py`、`deeptutor/services/provider_registry.py`、`deeptutor/tutorbot/providers/registry.py`(DeepSeek 直连路由 → 阿里云百炼 deepseek-v4-flash/pro)。
- **硬约束**：
  1. 加 feature flag + 回滚开关(出问题秒回 DeepSeek 直连)。
  2. **回归测试聊天 + 评分**：`tests/api/test_unified_ws_*`、评分 jury、construction-grading。确认换 provider 后输出质量/格式不变。
  3. cache 命中行为可能变(阿里云 vs DeepSeek 直连的 prompt cache 实现)，观察成本。
  4. 走 `deeptutor-aliyun-release`，回归过了再 flip flag。
- 迁移后 DeepSeek 直连消费归零，全部经阿里云自动对账。

### 任务 C：查 UsageLedger 漏记根因（健康度 0.73 的真 bug 部分）
- **现象**：qwen 系列(qwen-plus ¥5.5/qwen-max ¥4.89 官方)内账 token = 0；token 覆盖率 0.625(漏 37.5%)。扣掉任务 A 的「幽灵消费」后，剩余仍漏的才是真 bug。
- **查**：UsageLedger 写入链(`deeptutor/services/observability/usage_ledger.py` + 调用方)——为什么 qwen/rerank/embedding 等调用没 `record_usage_event`？是 provider 回报缺失，还是写入路径漏挂？
- **审计点**：RAG rerank(gte-rerank)、embedding(text-embedding-v3)、评分 jury 的多模型调用是否都写 ledger。
- 修后自校准健康度应逼近 1.0(扣除幽灵消费)。

### P4 验收
- 任务 A：DeepTutor 专属 key 上线；对账按 key 过滤后健康度 ≥ 0.95。
- 任务 B：DeepSeek 全走阿里云；聊天/评分回归通过；DeepSeek 直连消费归零；回滚开关验证。
- 任务 C：ledger 漏记修复；token 覆盖率(扣幽灵消费后) ≥ 0.9。
