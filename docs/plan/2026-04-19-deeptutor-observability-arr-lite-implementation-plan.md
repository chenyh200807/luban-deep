# 实施计划：DeepTutor Observability Phase 3（ARR Lite）

## 1. 本批目标

本批只交付 PRD `Phase 3：ARR Runner 总线化` 的 bootstrap 版本，不提前做数据库控制面和复杂 dashboard。

范围收敛为：

1. 把现有 `semantic_router_eval`、`context_orchestration_eval`、`long-dialog v1 retest` 收口成统一 ARR runner
2. 提供 `lite / full` 两种运行模式
3. 统一输出 run summary、case results、failure taxonomy、baseline diff artifact
4. 保持 runner 自己不创造第二套业务 authority

明确不在本批直接交付：

1. `arr_runs / arr_case_results` 数据库表
2. 自动写 Langfuse score
3. 自动 production-to-dataset 回灌
4. release room 页面
5. flaky 集治理与 `pass^k` 的完整策略引擎

## 2. 一等业务事实

本批维护的唯一业务事实是：

1. 已有专项评测与长对话复测，必须能被统一跑起来、统一汇总、统一比较
2. ARR runner 是总线，不是新的评测业务语义层

对应 authority：

1. `semantic / context / long-dialog` 的语义判断，继续由各自现有实现负责
2. ARR runner 只负责：
   - 选择哪些套件运行
   - 汇总结果
   - 分类失败
   - 输出 artifact 与 diff

## 3. 套件映射

### 3.1 lite

`lite` 只覆盖当前最稳、最便宜、最能反映回归风险的切口：

1. `semantic-router`
2. `context-orchestration`
3. `long-dialog-focus`

### 3.2 full

`full` 在 `lite` 基础上追加：

1. `long-dialog-full`

说明：

1. 第一阶段不强行新增 surface e2e 自动化套件
2. surface 先由上一批的 `surface ack + targeted manual evidence` 承接

## 4. 交付物

### 4.1 代码

1. 新增统一 ARR runner 脚本
2. 新增或复用最小结果模型
3. 支持 baseline 对比
4. 支持输出 JSON + Markdown artifact

### 4.2 artifact

每次 run 至少产出：

1. `arr_run_<mode>_<timestamp>.json`
2. `arr_run_<mode>_<timestamp>.md`

结构至少包含：

1. `run_id`
2. `mode`
3. `release`
4. `suite_summaries`
5. `case_results`
6. `failure_taxonomy`
7. `summary`
8. `baseline_diff`

## 5. failure taxonomy

本批统一先收口到 PRD 第一阶段的可执行子集：

1. `FAIL_INFRA`
2. `FAIL_TIMEOUT`
3. `FAIL_ROUTE_WRONG`
4. `FAIL_CONTEXT_LOSS`
5. `FAIL_CONTINUITY`
6. `FAIL_PRODUCT_BEHAVIOR`
7. `UNKNOWN`

映射原则：

1. fixture 断言失败优先落语义类失败
2. 长对话脚本中已有的 `hard_error / followup_object_mismatch / anchor_miss / context_reset / suspicious_replay / slow_turn`
   - 分别映射到 `FAIL_INFRA / FAIL_CONTINUITY / FAIL_CONTEXT_LOSS / FAIL_CONTEXT_LOSS / FAIL_PRODUCT_BEHAVIOR / FAIL_TIMEOUT`

## 6. baseline diff

runner 支持：

1. `--baseline <json>`

若传入 baseline，则输出：

1. 总体 pass rate 变化
2. 新增失败 case
3. 由 PASS -> FAIL 的回归 case
4. 失败分类变化

## 7. 文件级切口

预计会改这些文件：

1. `scripts/run_arr_lite.py`
2. 视实现需要新增 `deeptutor/services/observability/arr_runner.py`
3. 视实现需要新增 `tests/services/observability/test_arr_runner.py`
4. 可能轻量调整 `scripts/run_long_dialog_v1_retest.py` 以便被统一 runner 复用

## 8. 实施步骤

### Step 1：抽象统一结果模型

统一三种套件的最小结果字段：

1. `suite`
2. `case_id`
3. `case_name`
4. `status`
5. `failure_type`
6. `evidence`
7. `latency_ms`
8. `details`

### Step 2：接 semantic/context 套件

不通过 shell 调 pytest 解析文本，而是直接在 Python 层读取 fixture，调用现有函数，生成结构化结果。

### Step 3：接 long-dialog 套件

优先复用现有 `run_long_dialog_v1_retest.py` 的逻辑。

原则：

1. 若可轻量抽成函数，就抽成函数
2. 若当前脚本耦合太重，则允许 runner 以 subprocess 调用，并读取 JSON artifact

### Step 4：输出 artifact 与 diff

统一写到 `tmp/arr/`，并生成最新一次运行产物。

### Step 5：验证

至少执行：

1. `python3.11 scripts/run_arr_lite.py --mode lite`
2. `pytest tests/services/test_semantic_router_eval_cases.py tests/services/session/test_context_eval_cases.py`

如 long-dialog 冒烟成本过高，允许：

1. `--max-long-dialog-cases 1`
2. 或默认 lite 只跑 `focus`

## 9. 验收标准

本批完成后，必须满足：

1. `lite` 模式可稳定产出 JSON + Markdown artifact
2. semantic/context/long-dialog 三类结果都进入统一 summary
3. baseline diff 可比较两次 run
4. runner 结果不引入第二套 session/turn/release authority

## 10. 已知风险与替代方案

1. long-dialog live retest 很慢
   - `lite` 默认只跑 focus
   - `full` 才跑整套
2. 当前长对话脚本依赖真实模型与历史 artifact
   - 若本机环境不满足，应允许 `SKIP` 并明确原因
3. baseline 初期可能不存在
   - 首次 run 允许无 diff
