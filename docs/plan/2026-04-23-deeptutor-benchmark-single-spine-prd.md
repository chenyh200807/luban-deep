# PRD：DeepTutor 世界级 Benchmark 单一主脊梁设计

## 1. 文档信息

- 文档名称：DeepTutor 世界级 Benchmark 单一主脊梁设计
- 文档路径：`/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-23-deeptutor-benchmark-single-spine-prd.md`
- 创建日期：2026-04-23
- 文档状态：Proposed
- 适用范围：
  - `deeptutor` backend
  - 统一聊天入口 `/api/v1/ws`
  - `web`
  - `wx_miniprogram`
  - `yousenwebview`
  - `OM / ARR / AAE / OA / Release Gate`
- 关联约束：
  - [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)
  - [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)
  - [contracts/turn.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/turn.md)
  - [contracts/rag.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/rag.md)
  - [docs/zh/guide/runtime-observability.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/zh/guide/runtime-observability.md)
  - [docs/zh/guide/observability-control-plane.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/zh/guide/observability-control-plane.md)
  - [2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md)

## 2. 执行摘要

DeepTutor 当前已经具备 benchmark/observability 的 bootstrap 骨架：

1. 统一运行时入口 `/api/v1/ws`
2. `release lineage + /metrics + turn runtime + surface ack` 的最小运行态事实面
3. `ARR / AAE / OA / Release Gate` 的仓内控制面骨架
4. `semantic router / context orchestration / rag grounding / long-dialog` 的初始评测资产

但当前系统仍未达到“世界级 benchmark”标准，因为它还没有形成单一主脊梁：

1. benchmark 资产还未统一注册为 canonical quality contract
2. surface contract 还未进入 benchmark 主总线
3. `pre-release gate / daily trend / incident RCA` 还未严格消费同一份 benchmark artifact
4. AAE 仍以 proxy 为主，blind spot 仍未作为一等输出被统一治理

本 PRD 的核心判断是：

> DeepTutor 必须采用“一个 benchmark 核心，三个消费视图”的设计，而不是为 `pre-release gate`、`daily trend`、`incident / RCA` 分别维护三套平行真相。

推荐方案：

1. 底层只有一条 canonical spine：
   `surface -> /api/v1/ws -> session_id / turn_id -> trace_id -> release_id -> benchmark run -> arr diff -> oa diagnosis`
2. benchmark 是能力真相层
3. `pre-release gate / daily trend / incident RCA` 只是对同一条真相链的三种读取方式

## 3. 一等业务事实

本设计要维护的一等业务事实只有一句话：

> DeepTutor 的每一次真实或回放学习交互，都必须能够在同一套 ID、同一份 contract、同一条 release spine 下被评估、对比、归因，并能同时服务于发布门禁、日常趋势和线上 RCA。

这个事实的单一 authority 如下：

1. 入口 authority：统一 `/api/v1/ws`
2. 交互 authority：`session_id / turn_id`
3. trace authority：Langfuse 主 trace spine
4. 发布 authority：`release_id / git_sha / prompt_version / ff_snapshot_hash`
5. benchmark authority：统一 `dataset_id / dataset_version / case_id / run_id / failure_taxonomy`
6. 表面 authority：`surface ack / render coverage` 只负责可见事实回链，不发明第二套会话语义

如果任何新设计试图让 `gate / daily / incident` 各自定义一套成功标准、case 身份、错误分类或 run schema，都应视为违反本 PRD。

## 4. 核心问题定义

当前 DeepTutor 的问题不是“没有 benchmark”，而是“benchmark 还没有成为系统真实状态的单一能力真相层”。

具体表现为：

1. 运行时指标、release lineage、surface ack 已初步闭环，但 benchmark registry 不存在
2. ARR 已有 runner，但 dataset、suite、artifact、promotion 规则尚未 canonical 化
3. AAE 已有 composite 与 per-turn enrich，但大量分数仍为 proxy
4. OA 已能生成 blind spots 与 root causes 候选，但还缺统一 benchmark 覆盖对照
5. 真实产品表面的质量合同尚未进入统一总线，导致 benchmark 仍偏 backend/internal

如果继续按旧方式补点式脚本，系统会滑向：

1. 多入口评测脚本森林
2. 多套 artifact schema 并存
3. OA 自己长出第二套错误分类
4. 发布门禁、日报、事故排查三条线各说各话

## 5. 设计目标

### 5.1 核心目标

1. 建立一套单一 benchmark spine，统一服务 `pre-release gate / daily trend / incident RCA`
2. 让 benchmark 成为能力真相层，而不是 observability 的附属报告
3. 让 `dataset / suite / gate / replay / RCA` 成为同一条流水线的不同阶段
4. 让 incident 可以持续反哺 benchmark，而不是永远停留在线上排障文档
5. 让 blind spot 成为一等输出，不伪装为“已覆盖”

### 5.2 世界级标准

这里的“世界级”不等于更复杂，而是指下面六条同时成立：

1. authority 单一
2. benchmark 能真实反映系统状态，而不是只反映离线样本
3. release gate 能直接给出结构化 veto 原因
4. daily trend 能稳定反映慢性退化与 failure bucket 漂移
5. incident RCA 能回答“这是已知回归还是新 blind spot”
6. 三条消费线永远共用同一套 case 身份、run artifact 与 failure taxonomy

### 5.3 非目标

1. 不复制 `FastAPI20251222` 的历史脚本森林与多套 summary 兼容层
2. 不在第一阶段建设重型 Observer 平台
3. 不在第一阶段建设完整数据库控制面
4. 不让 OA 发明第二套错误分类
5. 不让 AAE proxy 伪装成真实质量真相
6. 不把 archive/debug 集混入发布门禁主集

## 6. 总体架构

DeepTutor benchmark 体系固定为 6 层，但只有 1 条主链路。

### 6.1 L0 Runtime Truth

这层只承认真实运行时事实，不做评分：

1. `/api/v1/ws`
2. `session_id / turn_id`
3. `trace_id`
4. `release_id / git_sha / prompt_version / ff_snapshot_hash`
5. `surface ack / render coverage`

### 6.2 L1 Benchmark Dataset

这层只维护 canonical quality contract，不直接承载运行脚本。

每个 case 必须具备：

1. `dataset_id`
2. `dataset_version`
3. `case_id`
4. `contract_domain`
5. `case_tier`
6. `execution_kind`
7. `surface`
8. `expected_contract`
9. `failure_taxonomy_scope`

### 6.3 L2 Execution Mode

只定义“怎么跑”，不定义“算不算好”。

只保留 3 种 execution kind：

1. `static_contract_eval`
2. `live_ws_replay`
3. `surface_parity_eval`

### 6.4 L3 Scoring & Failure Taxonomy

统一评分与失败分类，不允许不同消费者再长第二套口径。

核心质量维度：

1. `correctness`
2. `groundedness`
3. `continuity`
4. `surface_delivery`
5. `latency`
6. `cost`
7. `blind_spot_coverage`

统一顶层 failure taxonomy：

1. `FAIL_INFRA`
2. `FAIL_TIMEOUT`
3. `FAIL_ROUTE_WRONG`
4. `FAIL_CONTEXT_LOSS`
5. `FAIL_GROUNDEDNESS`
6. `FAIL_CONTINUITY`
7. `FAIL_SURFACE_DELIVERY`
8. `FAIL_PRODUCT_BEHAVIOR`
9. `UNKNOWN`

### 6.5 L4 Run Artifact

每次 benchmark run 必须产出统一 artifact，成为唯一消费面。

最少字段：

1. `run_manifest`
2. `suite_summaries`
3. `case_results`
4. `failure_taxonomy`
5. `baseline_diff`
6. `release_spine`
7. `runtime_evidence_links`
8. `blind_spots`

### 6.6 L5 Consumer

消费者只读 L4，不再自行拼装逻辑：

1. `pre-release gate`
2. `daily trend`
3. `incident / RCA`

## 7. Dataset 设计

benchmark dataset 不是题库，而是质量合同。

固定划分为 5 个合同域：

### 7.1 `routing_contract`

覆盖：

1. semantic router
2. context orchestration
3. active object continuity

首批来源：

1. `semantic_router_eval_cases`
2. `context_orchestration_eval_cases`

### 7.2 `grounding_contract`

覆盖：

1. retrieval decision
2. exact authority
3. grounded response

首批来源：

1. `rag_grounding_eval_cases`

### 7.3 `continuity_contract`

覆盖：

1. long-dialog
2. multi-turn follow-up
3. same-object continuity
4. anchor-term preservation

首批来源：

1. `long_dialog_focus_eval_cases`
2. 历史 replay artifact

### 7.4 `surface_contract`

覆盖：

1. `web`
2. `wx_miniprogram`
3. `yousenwebview`
4. render parity
5. surface ack
6. 最终可见结果

首批来源：

1. 现有前端 fixture
2. render schema case
3. targeted surface smoke

### 7.5 `production_replay_contract`

覆盖：

1. 线上真实坏例复现
2. incident 相邻场景
3. counterfactual replay

首批来源：

1. 真实事故归档
2. trace 回放
3. 用户投诉样本

## 8. Tier 设计

每个 case 必须归属于 4 类之一：

1. `gate_stable`
   - 发布门禁核心集
2. `regression_tier`
   - 高风险回归集
3. `exploratory`
   - 研究与扩样，不参与 blocking gate
4. `incident_replay`
   - 真实事故回放候选

晋升规则固定为：

1. incident 先进入 `incident_replay`
2. 稳定复现后可晋升 `regression_tier`
3. 成为通用发布风险后方可晋升 `gate_stable`

## 9. Suite 设计

suite 不是脚本名，而是 dataset 在某个运行目标下的投影。

只保留 4 组 canonical suites：

### 9.1 `pr_gate_core`

用途：

1. 服务 `pre-release gate`

组成：

1. 只含 `gate_stable`

要求：

1. 高稳定
2. 高解释性
3. 低歧义

### 9.2 `regression_watch`

用途：

1. 服务 `daily trend`

组成：

1. `gate_stable`
2. `regression_tier`

目标：

1. 观察 pass rate 漂移
2. 观察 failure bucket 变化
3. 观察 baseline diff

### 9.3 `incident_replay`

用途：

1. 服务 `incident RCA`

组成：

1. 当前事故相关 replay
2. neighbor cases
3. counterfactuals

### 9.4 `exploration_lab`

用途：

1. 服务研究、扩样、试验

约束：

1. 不参与 blocking gate
2. 只产 insight，不产发布真相

## 10. Gate 设计

发布门禁不是裸平均分，而是结构化 veto system。

只看两类信息：

### 10.1 硬门槛 floors

1. `P0 Runtime`
2. `P1 Trace Completeness`
3. `P2 Benchmark Regression`
4. `P3 Quality Floors`
5. `P4 Blind Spot Budget`

### 10.2 结构化 blockers

1. 新增 regression
2. continuity floor 下穿
3. groundedness floor 下穿
4. surface delivery 未覆盖
5. blind spot 超预算

设计原则：

1. gate 必须能直接回答“为什么这次不能发”
2. 每个 blocker 必须直接落到 benchmark evidence
3. 不能使用独立于 benchmark artifact 的第二套 gate 逻辑

## 11. Replay 与 RCA 设计

### 11.1 Replay 是 benchmark 的增长引擎

固定流程：

1. 线上出问题
2. 生成 `replay artifact`
3. 进入 `incident_replay`
4. 稳定复现后晋升 `regression_tier`
5. 高价值通用风险晋升 `gate_stable`

### 11.2 RCA 只消费 benchmark + runtime

OA / incident 只做三件事：

1. 指出当前问题属于哪个顶层 failure taxonomy
2. 指出该问题是否已被 benchmark 覆盖
3. 若未覆盖，明确为 blind spot，并生成新的 `incident_replay` 候选

禁止事项：

1. OA 不得发明第二套错误分类
2. OA 不得重新定义 benchmark success criteria
3. OA 不得绕过 runtime canonical metadata 自造会话真相

## 12. 三类消费目标如何共享同一条流水线

### 12.1 `pre-release gate`

读取：

1. `pr_gate_core`

目标：

1. 能不能发

### 12.2 `daily trend`

读取：

1. `regression_watch`

目标：

1. 是否在慢性退化

### 12.3 `incident / RCA`

读取：

1. `incident_replay`

目标：

1. 这是已知回归还是新 blind spot

三者共享同一套：

1. dataset registry
2. execution kinds
3. failure taxonomy
4. run artifact schema
5. release spine
6. runtime evidence link

## 13. Phase 1 必须先做的 8 件事

### 13.1 建立唯一 benchmark registry

把现有 fixture 收口成 canonical registry，至少登记：

1. `dataset_id`
2. `dataset_version`
3. `case_id`
4. `contract_domain`
5. `case_tier`
6. `execution_kind`
7. `surface`
8. `expected_contract`
9. `failure_taxonomy_scope`

### 13.2 将现有 4 类 benchmark 正式编入主树

首批必须纳管：

1. `semantic_router_eval_cases`
2. `context_orchestration_eval_cases`
3. `rag_grounding_eval_cases`
4. `long_dialog_focus_eval_cases`

### 13.3 将 surface contract 正式接入 benchmark 总线

第一阶段优先级：

1. `wx_miniprogram`
2. `web`
3. `yousenwebview` 先保留 targeted smoke，不做重自动化

### 13.4 统一 run artifact schema

强制统一输出：

1. `run_manifest`
2. `suite_summaries`
3. `case_results`
4. `failure_taxonomy`
5. `baseline_diff`
6. `release_spine`
7. `runtime_evidence_links`
8. `blind_spots`

### 13.5 将 pre-release gate 改造成 benchmark-first gate

绑定关系：

1. `P2` 只看 regression
2. `P3` 只看关键质量 floors
3. `P4` 只看 blind spot budget

### 13.6 建立 daily trend 的最小 canonical 口径

第一阶段只看 6 个指标：

1. `pass_rate`
2. `new_regression_count`
3. `continuity_floor`
4. `groundedness_floor`
5. `surface_delivery_coverage`
6. `blind_spot_count`

### 13.7 建立 incident -> replay -> regression 的晋升机制

流程必须固化，不能口头约定：

1. incident 产生 replay candidate
2. replay candidate 进入 `incident_replay`
3. 稳定复现后晋升 `regression_tier`
4. 再决定是否晋升 `gate_stable`

### 13.8 将 blind spot 升级为一等输出

系统必须能够结构化声明：

1. 这里没覆盖
2. 这里是 proxy
3. 这里 evidence 不足
4. 这里需要 live replay 或真实 surface 才能判

## 14. Phase 1 坚决不做的 9 件事

1. 不复制旧仓多入口脚本森林
2. 不建设重型 Observer 平台
3. 不优先追求复杂 judge
4. 不让 AAE proxy 伪装成真实质量分
5. 不让 OA 自己定义第二套错误码
6. 不把 artifact 当业务 authority
7. 不把 archive/debug 集混入 gate 主集
8. 不在 Phase 1 先上完整数据库控制面
9. 不把微信或表面验证继续留在纯人工口头层

## 15. Canonical 入口设计

Phase 1 完成后，仓库内只保留这些官方入口：

### 15.1 一个 benchmark registry

职责：

1. case 元数据登记
2. tier 管理
3. suite 投影关系

### 15.2 一个 benchmark runner

统一支持：

1. `pr_gate_core`
2. `regression_watch`
3. `incident_replay`
4. `exploration_lab`

### 15.3 一个 pre-release command

一键串起：

1. `ws smoke`
2. `OM`
3. `benchmark / ARR`
4. `AAE`
5. `OA`
6. `release gate`

### 15.4 一个 daily command

职责：

1. 统一产出日趋势
2. 不允许 daily 自己拼 summary

### 15.5 一个 incident replay command

职责：

1. 从真实事故生成 replay
2. 跑对照
3. 产出 blind spot / regression 候选

### 15.6 一份 benchmark canonical spec

必须定义：

1. dataset registry schema
2. suite semantics
3. failure taxonomy
4. artifact schema
5. promotion rules
6. blind spot rules

## 16. 验收标准

如果 Phase 1 达标，仓库必须能明确回答以下 6 个问题：

1. 这个 case 在哪登记
2. 它属于哪个合同域
3. 它在哪个 suite 被跑
4. 它失败后落哪类 taxonomy
5. 它是否影响 pre-release gate
6. 它是不是由 incident replay 晋升而来

如果以上 6 个问题任何一个无法通过仓内 canonical 文件或产物直接回答，则说明 benchmark 体系仍未真正收口。

## 17. 风险与替代策略

### 17.1 风险：Surface benchmark 过早重自动化

替代策略：

1. 第一阶段先以 `wx_miniprogram` parity 为主
2. `web` 次之
3. `yousenwebview` 暂保留 targeted smoke

### 17.2 风险：AAE proxy 被误读为真实质量

替代策略：

1. 所有 scorecard 强制标记 `direct / proxy`
2. 输出 coverage ratio
3. 将 blind spot 与 proxy 公开提升为同级字段

### 17.3 风险：OA 重新长出第二套 authority

替代策略：

1. OA 只消费 benchmark artifact
2. OA 只输出 taxonomy mapping、coverage 判断、blind spot 候选
3. 禁止 observer 自定义独立 verdict

### 17.4 风险：入口失控，复杂度复制旧仓

替代策略：

1. 仓内只允许少量 canonical commands
2. 非 canonical 的 debug 脚本必须显式标为 exploratory 或 local-only
3. 所有发布相关流程只能调用 canonical runner

## 18. 结论

DeepTutor 的世界级 benchmark 设计，不应走“三套系统并行”路线，而必须走：

`一个 benchmark 核心，三个消费视图`

只有这样，系统才能同时满足：

1. `pre-release gate` 可用
2. `daily trend` 可用
3. `incident RCA` 可用
4. single authority 不被破坏
5. incident 能持续反哺 benchmark
6. blind spot 可见，而不是被伪装成“系统已经知道”

Phase 1 的成功标准，不是“功能很多”，而是：

1. authority 单一
2. registry canonical
3. artifact canonical
4. surface 正式入总线
5. gate / daily / RCA 共用同一份真相
