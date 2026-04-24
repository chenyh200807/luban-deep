# 附录：DeepTutor 观测体系 PRD 的“原设计意图映射”审计

## 1. 文档信息

- 文档名称：原设计意图映射审计附录
- 文档路径：`/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-19-deeptutor-observability-original-intent-mapping-audit.md`
- 创建日期：2026-04-19
- 目的：
  - 判断当前 [2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md) 是否真正吸收了旧体系每项设计背后的逻辑和目的
  - 区分哪些部分是“继承”，哪些部分是“升级重设计”，哪些部分还未进入主 PRD

## 2. 审计结论

结论先讲清楚：

1. 当前主 PRD 已经继承了旧体系最核心的主逻辑：
   - 单一 authority
   - 观测闭环而不是散点埋点
   - runtime / regression / evaluation / RCA 分层
   - 真实产品表面进入正式观测面
2. 但它还没有完整继承旧体系里若干非常具体、非常工程化的设计目的：
   - `ARR` 的稳定集/波动集分离、`pass^k` 门禁、失败模式记忆、补丁验证、online failure flywheel
   - `OA` 的 raw evidence mode、best-effort state store、change events 汇聚、confidence tier 与 evidence chain
   - `Curator` 的“自动生成样本不直接进入正式门禁”这一治理设计
   - `OM` 的 operator-facing stack snapshot 语义，不只是 metrics
3. 所以现在最准确的判断是：
   - 主 PRD 已经继承了旧体系的主脑
   - 但还没有逐项吸收旧体系的手脚和反复踩坑后长出来的治理细节

换句话说：

> 当前 PRD 不是表面参考，但也还不是“完整继承原设计 intelligence”的最终版。

## 3. 审计方法

本审计不是看旧设计名词，而是看每项设计到底在解决什么问题。

审计维度统一采用四列：

1. `旧设计项`
2. `原始目的 / 背后逻辑`
3. `当前主 PRD 是否继承`
4. `本次建议`

继承状态分四类：

1. `已继承`
   - 主 PRD 已明确保留其一等目的与结构逻辑
2. `部分继承`
   - 主 PRD 抓住了大方向，但还没把原设计的关键治理细节带过来
3. `未继承`
   - 主 PRD 尚未覆盖该设计意图
4. `不应照搬`
   - 旧体系里该设计只是历史实现，不适合直接迁入 deeptutor

## 4. 总体判断

### 4.1 旧体系真正的一等逻辑

对旧仓 `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222` 做逆向后，可以看出其真正的一等逻辑不是“工具很多”，而是五件事：

1. 把系统分成不同观测职责层，而不是让一个大报表混合运行态、质量态、根因态
2. 尽量把 `infra noise` 与 `semantic regression` 分开，避免误修
3. 不让人脑长期手工做 triage，而是沉淀成可复用的 failure taxonomy、history、playbook
4. 不把自动收集来的样本、自动生成的结论、人工确认过的门禁信号混成同一层真相
5. 即使高级能力失效，系统也要退化到 rules-only / JSONL-only / no-op，而不是整条链断掉

### 4.2 当前主 PRD 的真实状态

当前主 PRD 已经吃进去的，是上述 1、2、3 的主方向。

当前主 PRD 还缺的，是上述 4、5 里的若干关键治理设计。

因此，接下来的优化重点不该再是“加更多概念”，而应该是把以下四条补到主 PRD 或后续实施计划里：

1. `自动样本 -> 审核样本 -> 门禁样本` 的分层治理
2. `rules-only / best-effort / fallback artifact` 的退化设计
3. `stable vs flaky vs regression-tier` 的 ARR 门禁分层
4. `raw evidence -> judged insight -> release decision` 的证据链分层

## 5. 逐项映射审计

## 5.1 ARR：不是“跑评测”，而是“回归飞轮”

### 5.1.1 clean session + deterministic eval

- 旧设计项：
  - `run_arr_pipeline.py` 默认 `temperature=0.0`
  - `session_mode="clean"`
  - `execution_mode` 可切
- 原始目的 / 背后逻辑：
  - 让回归评测尽量减少历史状态污染和随机噪声
  - 先建立“可比较”的回归事实，再谈更复杂的质量判断
- 当前主 PRD 是否继承：
  - `部分继承`
- 判断：
  - 主 PRD 已强调单一 spine、dataset run、release gate
  - 但没有把“clean session / deterministic config / comparable run contract”写成 ARR 的硬约束
- 建议：
  - 在主 PRD 的 ARR 章节明确增加：
    - `eval session mode`
    - `temperature policy`
    - `deterministic baseline fields`

### 5.1.2 failure classification 不只是统计，而是避免误修

- 旧设计项：
  - `_classify_failures`
  - `_run_failure_classification`
  - `INFRA_FAIL / SEMANTIC_FAIL / UNKNOWN_FAIL`
- 原始目的 / 背后逻辑：
  - 防止把 infra 抖动误当成语义回归
  - 防止团队在错误层次上修 bug
- 当前主 PRD 是否继承：
  - `已继承`
- 判断：
  - 主 PRD 已加入 fail taxonomy
  - 也加入了 infra / semantic / unknown 分流思路
- 仍需补充：
  - 把“分流结果如何影响 gate”写得更硬
- 建议：
  - 在实施时明确：
    - `FAIL_INFRA` 进 runtime/ops queue
    - `FAIL_ROUTE_WRONG / FAIL_CONTEXT_LOSS / FAIL_GROUNDEDNESS` 进 semantic repair queue

### 5.1.3 stable set 与 flaky set 分离

- 旧设计项：
  - lite 模式区分 `stable accuracy` 和 `flaky set`
  - `stable >= 90%` 才作为 gate basis
- 原始目的 / 背后逻辑：
  - 避免用波动样本污染正式 gate
  - 但又不丢掉波动样本的诊断价值
- 当前主 PRD 是否继承：
  - `部分继承`
- 判断：
  - 主 PRD 写了 `flaky`，但还没把“stable 用于 gate、flaky 用于信息提示”这个治理逻辑写透
- 建议：
  - 主 PRD 或实施计划中应明确三层样本：
    - `gate_stable`
    - `diagnostic_flaky`
    - `regression_tier`

### 5.1.4 pass^k / regression-tier gate

- 旧设计项：
  - `pass^k gate`
  - regression-tier cases 必须维持 `pass^3=100%`
- 原始目的 / 背后逻辑：
  - 有些 case 单次通过不够，必须证明稳定通过
  - 对“曾经出过事故的关键样本”采用更严门禁
- 当前主 PRD 是否继承：
  - `未继承`
- 判断：
  - 当前主 PRD 还没有把“关键 regression tier 比普通样本更严格”写进去
- 建议：
  - 主 PRD 的 `Gate P2 ARR` 应增加：
    - `critical regression-tier uses pass^k / repeated-pass gate`

### 5.1.5 baseline diff 不是可选美化，而是回归事实本体

- 旧设计项：
  - `_compare_with_baseline`
  - `_print_diff_report`
- 原始目的 / 背后逻辑：
  - 不是只看“当前跑得怎样”，而是要回答“比上一版好还是坏”
- 当前主 PRD 是否继承：
  - `已继承`
- 判断：
  - 主 PRD 已写入 regression diff、release lineage、trend

### 5.1.6 failure memory / patch validation / DDC

- 旧设计项：
  - `FailurePatternStore`
  - `PatchRegistry`
  - `FailureDiagnoser`
- 原始目的 / 背后逻辑：
  - 让系统不是每次从零开始看失败
  - 把失败模式、补丁是否有效、离线改进提案沉淀为资产
- 当前主 PRD 是否继承：
  - `部分继承`
- 判断：
  - 主 PRD 已写 production-to-dataset 和 OA playbook
  - 但还没把 failure memory / patch validation 单独抽象成正式资产
- 建议：
  - 后续实施计划中应增加：
    - `failure_pattern_store`
    - `patch_validation_receipt`
    - `offline improvement proposal ledger`

### 5.1.7 online failure collection -> regression flywheel

- 旧设计项：
  - `OnlineFailureCollector`
  - 自动把线上失败候选回灌到回归集
- 原始目的 / 背后逻辑：
  - 让生产问题能持续反哺评测，而不是一次性复盘后遗忘
- 当前主 PRD 是否继承：
  - `已继承`
- 判断：
  - 当前主 PRD 已明确 `production-to-dataset`
- 仍需补充：
  - 必须引入来源层级，不可自动直接成为 gate case

## 5.2 AAE：旧体系里它更像治理控制面，而不只是 trace-native score system

### 5.2.1 旧 AAE 的真实形态

- 旧设计项：
  - `/api/v1/bi/eval/aae`
  - `AGENT_EVAL_AUDIT_REPORT.md`
  - `AGENT_EVAL_ACTION_PLAN.md`
  - `aae_eval_results_direct.json`
- 原始目的 / 背后逻辑：
  - 让“智能体质量问题”不仅体现在分数上，还体现在审计报告、行动计划、优先级和缺口列表上
  - 旧 AAE 是“质量治理面”，不是完全 trace-native 的评价 runtime
- 当前主 PRD 是否继承：
  - `部分继承`
- 判断：
  - 当前主 PRD 把 AAE 升级成更理想的 score taxonomy + annotation queue + composite
  - 这是合理升级
  - 但必须明确：这是在旧设计基础上的重设计，不是旧 AAE 的原样迁移
- 建议：
  - 主 PRD 后续版本应明确区分：
    - `AAE v1 legacy audit plane`
    - `AAE v2 trace-native scoring plane`

### 5.2.2 composite 的真实目的不是“求总分”，而是“做治理排序”

- 旧设计项：
  - composite score
  - metrics baseline
  - bottlenecks count
  - action plan
- 原始目的 / 背后逻辑：
  - 总分不是为了好看，而是为了排序和行动
- 当前主 PRD 是否继承：
  - `已继承`
- 判断：
  - 当前主 PRD 已写 composite、coverage、review queue、release gate
- 建议：
  - composite 的输出默认服务于：
    - release gate
    - review queue priority
    - paid student high-value cohort triage

## 5.3 OA：不是一个聪明解释器，而是一条 OODA 运营链

### 5.3.1 Analyst / Raw / Curator / Coach 四模式不是功能堆砌

- 旧设计项：
  - `analyst`
  - `raw-data`
  - `curator`
  - `coach`
- 原始目的 / 背后逻辑：
  - `analyst`：生成 daily brief / RCA 假设
  - `raw-data`：在不信任 LLM 总结时，导出完整证据层给人或其他 agent 分析
  - `curator`：把生产信号转成候选测试集
  - `coach`：做趋势级系统改进建议，而不是当下事故 RCA
- 当前主 PRD 是否继承：
  - `部分继承`
- 判断：
  - 当前主 PRD 讲清了 OA 的分析面
  - 但还没有把“不同 operator mode 的工作分层”写出来
- 建议：
  - 主 PRD 或后续实施计划中增加 OA modes：
    - `raw evidence mode`
    - `analyst mode`
    - `curation mode`
    - `coaching mode`

### 5.3.2 raw evidence mode 是旧体系最容易被忽略、但很值钱的设计

- 旧设计项：
  - `--raw-data`
  - 输出 `raw_data_latest.json`
  - 收集全部信号层，不做 LLM 总结
- 原始目的 / 背后逻辑：
  - 当自动总结不可信，或需要更高阶 agent/人工重新分析时，必须保留完整原始证据层
- 当前主 PRD 是否继承：
  - `未继承`
- 判断：
  - 当前主 PRD 里还没有把 `raw evidence dump` 定义成正式产物
- 建议：
  - 主 PRD 应新增：
    - `OA raw evidence bundle`
    - 用于 release room、incident 复盘、外部 agent 二次分析

### 5.3.3 OODA 不是口号，是真实工作流

- 旧设计项：
  - Observe / Orient / Decide / Act
  - ChangeDetector + Memory + Correlator + ActionExecutor
- 原始目的 / 背后逻辑：
  - 不让 observer 只停在“看见问题”
  - 要能把观察、历史、变更、趋势、假设、动作串起来
- 当前主 PRD 是否继承：
  - `已继承`
- 判断：
  - 当前主 PRD 的 OA 输出合同、change events、playbook，本质已在继承 OODA 逻辑

### 5.3.4 evidence chain + confidence tier + counterfactual

- 旧设计项：
  - `commit_correlator.correlate_v2`
  - `evidence_chain`
  - `confidence_tier`
  - `counterfactual`
- 原始目的 / 背后逻辑：
  - 防止 root cause 只是拍脑袋
  - 同时让“最可能根因”和“次可能根因”都可见
- 当前主 PRD 是否继承：
  - `部分继承`
- 判断：
  - 当前主 PRD 已要求 evidence、confidence、next_verification_step
  - 但还没有把 `counterfactual` 作为正式输出合同写进去
- 建议：
  - OA 输出合同建议新增：
    - `counterfactual`
    - `why_not_other_hypotheses`

### 5.3.5 repair playbook 不是建议列表，而是可执行修复剧本

- 旧设计项：
  - `_build_repair_playbook`
  - `issue_type / title / steps / validation_cmds / risk_level`
- 原始目的 / 背后逻辑：
  - 让 RCA 不只停在归因，还能直接转成验证型修复动作
- 当前主 PRD 是否继承：
  - `已继承`
- 判断：
  - 当前主 PRD 已把 playbook 提升为正式产物
- 仍需补充：
  - 实施时必须确保包含 `validation_cmds`

### 5.3.6 state store 的深层设计目的：控制面可查，但写库失败不阻断主流程

- 旧设计项：
  - OAStateStore
  - `best-effort`
  - 写库失败自动降级到 JSONL-only
- 原始目的 / 背后逻辑：
  - 让控制面长期可查询
  - 但又不让数据库/控制面故障反向打断日报或主观测链
- 当前主 PRD 是否继承：
  - `部分继承`
- 判断：
  - 当前主 PRD 已定义 Postgres/Supabase control plane
  - 但还没有明确“state store failure must not break observer pipeline”
- 建议：
  - 主 PRD 或实施计划中显式写：
    - `control plane writes are best-effort`
    - `fallback artifact mode is mandatory`

### 5.3.7 data coverage / blind spots 不是装饰指标，是门禁保护装置

- 旧设计项：
  - 16-layer coverage
  - `blind_spots_missing`
  - `blind_spots_stale`
- 原始目的 / 背后逻辑：
  - 让系统知道自己不知道什么
  - 避免在证据不完整时给出过强结论
- 当前主 PRD 是否继承：
  - `已继承`
- 判断：
  - 当前主 PRD 已把 blind spots 和 coverage 做成 gate 与 dashboard 核心

### 5.3.8 harness health 的真实设计目的：区分 canary gate 和 graduation gate

- 旧设计项：
  - `receipt completeness`
  - `authority alignment`
  - `router recompute`
  - `context drift`
  - canary / graduation 双阈值
- 原始目的 / 背后逻辑：
  - 不同阶段要用不同严格度
  - 没有数据时也不能误判成“系统完好”
- 当前主 PRD 是否继承：
  - `已继承`
- 判断：
  - 当前主 PRD 已把 `bootstrap` 和 `steady-state` 门禁拆开
  - 这是对旧设计目的的正确继承

## 5.4 Curator：旧体系里它负责“样本治理”，不是“自动把线上数据塞进门禁”

### 5.4.1 自动样本不直接进入正式 gate

- 旧设计项：
  - `source=observer_auto`
  - `needs_review=true`
  - 人工审核后升级为 `verified`
- 原始目的 / 背后逻辑：
  - 防止自动挖掘的脏样本直接污染正式 pass rate 和门禁
- 当前主 PRD 是否继承：
  - `未继承`
- 判断：
  - 当前主 PRD 写了 production-to-dataset
  - 但没有写“auto -> reviewed -> gate-eligible”的样本分层
- 建议：
  - 这条必须补到主 PRD
  - 否则 production-to-dataset 会把系统拖进噪声地狱

### 5.4.2 positive / negative / hard 是三种不同治理资产

- 旧设计项：
  - Positive Mining
  - Negative Mining
  - Anti-Saturation -> Hard variants
- 原始目的 / 背后逻辑：
  - Golden 用于证明能力
  - Negative 用于证明不会犯错
  - Hard 用于对抗“过拟合已经会做的题”
- 当前主 PRD 是否继承：
  - `部分继承`
- 判断：
  - 当前主 PRD 有 dataset / cohort / annotation
  - 但没明确 `golden / negative / hard` 三类样本资产分工
- 建议：
  - 后续实施文档中要明确 dataset taxonomy

## 5.5 Coach：旧体系里它负责慢变量优化，而不是事故排障

### 5.5.1 prompt drift / retrieval quality / cost / eval health

- 旧设计项：
  - Coach 按慢变量做优化建议
- 原始目的 / 背后逻辑：
  - 把“今天坏了什么”和“系统长期该怎么变好”分开
- 当前主 PRD 是否继承：
  - `部分继承`
- 判断：
  - 主 PRD 更偏 incident / release / quality control
  - 对 `slow-moving optimization plane` 写得不够
- 建议：
  - 可以不在第一阶段主 PRD 中做重
  - 但后续 roadmap 应保留 `coach plane`

## 5.6 OM：旧体系里它是 operator-facing stack truth，不只是技术指标

### 5.6.1 stack snapshot 的真实价值

- 旧设计项：
  - `get_observability_stack`
  - Prometheus/Grafana/Langfuse candidate URLs
  - `up / degraded / auth_required / down`
  - 直达 links
- 原始目的 / 背后逻辑：
  - 不是让系统知道端口通不通
  - 而是让操作者一眼知道“观测栈自己是不是可用”
- 当前主 PRD 是否继承：
  - `部分继承`
- 判断：
  - 当前主 PRD 写了 stack health
  - 但还没把 `auth_required / operator links / candidate fallback URL` 这类 operator-facing 语义写进来
- 建议：
  - 后续实施时保留：
    - `stack snapshot`
    - `operator links`
    - `service state distinctions`

## 6. 哪些旧设计不应照搬

不是旧体系里存在的每个东西都应该搬进 deeptutor。

### 6.1 不应原样照搬的部分

1. `AAE` 的文档解析式实现
   - 旧体系里部分 AAE 来自解析 Markdown 审计报告和行动计划
   - deeptutor 更适合走 trace-native + score-native 方案
2. 旧系统里过多围绕 `FastAPI20251222` 特定 artifact 目录的路径约定
   - 这些属于实现偶然性，不是本体设计
3. 旧系统里某些大量 feature flag 包裹的历史兼容分支
   - deeptutor 应优先用更直接、更少分支的实现

### 6.2 需要“继承目的、重写实现”的部分

1. `AAE quality control plane`
2. `OA state store`
3. `Curator sample governance`
4. `OM operator snapshot`
5. `ARR failure memory + patch validation`

## 7. 对主 PRD 的修订建议

如果要让主 PRD 达到“真正继承原设计 intelligence”的标准，建议再补五条：

1. 在 ARR 中新增 `stable / flaky / regression-tier` 三层样本治理。
2. 在 ARR 中新增 `pass^k` 或 repeated-pass 机制，用于关键 regression tier。
3. 在 production-to-dataset 中新增样本状态流转：
   - `observer_auto`
   - `reviewed`
   - `verified`
   - `gate_eligible`
4. 在 OA 中新增 `raw evidence mode` 与 `best-effort state store + artifact fallback`。
5. 在 OA 输出合同中新增：
   - `counterfactual`
   - `validation_cmds`
   - `why this hypothesis outranks alternatives`

## 8. 当前是否可以进入实施

可以进入实施，但要明确是“带条件进入”。

### 8.1 可以先开工的部分

1. 统一词汇表与 release lineage
2. OM 基线
3. surface ack
4. ARR lite 总线化
5. OA 摘要版

### 8.2 开工前应先补进主 PRD 或实施计划的部分

1. 自动样本升级流程
2. stable/flaky/regression-tier 分层
3. OA raw evidence mode
4. state store fallback contract
5. key regression pass^k gate

## 9. 最终结论

这次审计后的最终判断是：

1. 当前主 PRD 已经不是表层复述，它已经抓住了旧体系的主骨架和第一性逻辑。
2. 但若严格按“充分思考并利用原设计里每项设计背后的逻辑和目的”来衡量，它还差最后一层：
   - 把旧体系那些经过实战打磨出的治理细节正式写回 deeptutor 方案
3. 因此最准确的说法不是：
   - “这份 PRD 已经完整继承旧设计”
4. 而是：
   - “这份 PRD 已经正确继承了旧设计的主逻辑，并识别出了必须继续补齐的深层治理设计”

只有把本附录第 7 节那五条补回主 PRD 或实施计划，才可以更有把握地说：

> deeptutor 的观测体系设计，不只是参考了旧体系，而是真正继承了旧体系最值钱的设计 intelligence。
