# 鲁班 KnowQL 补齐蓝图（单一权威 native）

> 综合三份专家研究 + 今天判分 A/B 的实证,产出可建蓝图。
> **不另起规划主线**:本蓝图挂靠既有 §4.6「Narrow KnowQL-Inspired Query Contract」
> (`docs/plan/评分引擎与金标工件/2026-06-09-luban-nexus-like-scoring-artifact-engine-execution-plan.md`)。
> 输入研究:`nexus_essence_research.md` / `current_state_gap_and_second_authority_audit.md` / `typed_object_requirements_by_question_type.md`。

## 0. 决定性诊断(一句话)

我们把 Nexus 的 `compile → deterministic-retrieve` 做成了 `compile → stuff-context → model-freestyle`——**后半段塌回了 RAG**。而鲁班判分(重复查询、单一权威、教材字段级溯源)恰好落在 **Nexus 赢面**,我们却用了那条输的路径。

## 0.5 North Star(本蓝图服务的产品目标)

`评分知识结构化 → 采分点判断更准 → 错因标签更稳定 → 学情画像更可信 → 学习建议更具体 → 用户感觉"它真的懂我" → 留存与付费 → 鲁班专用教育知识资产持续复利`。落到:批改更准 / 采分点不漏 / 扣分原因清楚 / 学情画像有证据 / 复习建议可执行 / **模型替换成本更低** / 数据资产复利。本蓝图(原子采分点判分)是这条链被 §8/§9 live A/B 实测**赢 RAG** 的第一环。北极星正文 + LLM-judge rubric 外部循证(分项 vs holistic 条件、二元 MET/UNMET、去相关 RRD、聚合超敏、κ≥0.6 门槛)见 `grading_to_brain_north_star_and_external_evidence.md`。

## 1. Nexus 精髓 5 机制(带出处,推断项已标)与我们的差距

| 机制 | Nexus 精髓(文档证实) | 我们现状 | 差距 |
|---|---|---|---|
| ① typed object | 字段级 citation 是**编译期构造的硬不变量**("returned by construction, not reconstructed") + Conflicts surface | 材料里写出处、模型自觉引用 | citation 非硬不变量;冲突不暴露 |
| ② KnowQL 查询 | 声明式 6 primitive: `ask/where/ground/shape/confidence/budget`,output 形状被 `shape` 写死 | 给自由文本 context,output 形状模型即兴 | **最大缺口(25%)**:无声明式输出契约 |
| ③ compile loop | Context Compiler = 自治 agent 改 `curate()/query()`,跑 eval set→失败信号迭代,**accuracy+token+latency 联合打分** | 规则/模板式编译,无 eval 收敛闭环,token/latency 不入编译目标 | 无收敛闭环、无联合成本目标 |
| ④ retrieve/compile 边界 | 向量沉到底座/编译期;查询时**确定性取数**(avg 1.69 步);artifact 替代在线 raw-doc 检索 | "挑该用的/消歧/组织答案"全留给 runtime 模型自由发挥 | 确定性取数缺失 |
| ⑤ regime | 赢:多文档合成/确定性消歧/重复查询摊销/字段级审计/可预测预算 | — | 判分正落赢面,但走了输的路径 |

> 诚实边界(原典研究):KnowQL 正式 grammar/类型系统/落盘 schema/去重算法 **Pinecone 未公开**,只有散文承诺。本蓝图不抄不存在的细节,只学可证实的精髓机制 + 用我们自己的单一权威实现。

## 2. 单一权威结构保证(脊柱,优先级 = 学精髓)

KnowQL typed object 永远是**带 per-field citation 的投影**,在 schema 层就无法自封权威:

1. **span_hash = 投影非新权威的机器证明**(复用 `rich_leaf_artifacts.py`);无 cite 的字段不准存在。
2. **官方答案 key = "采分点/命中"的唯一权威**;rich leaf 5705 采分点(50x key)降为 supporting shape,**runtime 确定性不变量固定"key 优先于采分点"**(消掉审计发现的最大第二权威 R1)。
3. **逐点分无 canonical 权威**(官方 key 只给总分)→ 编译期**自造分摊 = must-not-mint**;逐点分只能来自授权标定通道(m35 AI 金标 = review-only candidate,**非权威**)。
4. **AI 面板 = 降噪 + key 错误候选标记器,永不 override key**(Phase 3 已纠正:quality_claim 降级、6 候选交 owner)。
5. **查询层只读不铸**:KnowQL query 取字段,永不产生新真相。
6. **schema 层硬关**:`forbidden_properties` + `official_score_allowed const False`,typed object 结构上不能自称官方真值。

## 3. 建设序列(审计定序:不在漂移 schema 上建查询语言)

### Phase A — 收敛单一 typed-object schema(确定性,无 LLM,先做)
- 病:`case_grading_artifact.v1`(eval 内联)vs `luban_rich_leaf_scoring_point_compile.v1`(rich leaf pack)字段名漂移(`weight`/`max_score`、`canonical_answer`/`statement`),谁 canonical 没在代码固定 = 双 schema 第二权威。
- 做:定一份 canonical typed-object schema(题型族:objective/calculation/standard_clause/case 的 11 子型,字段表见 `typed_object_requirements_by_question_type.md`),每字段三列(权威来源/投影方式/缺权威 fail-closed)。固定官方 key→采分点的 runtime 优先序不变量。

### Phase B — 把输出合约提升进 runtime + 摁死误给(KnowQL ③④ 上线)
- ③强制器(`enforce_output_schema`,现仅 eval)提升为该 typed object 的 runtime 方法。
- **新增"命中也要 cite"闸**:每个 `hit` 必须 bind 到 key 的 `required_terms/accepted_variants` 逐字证据(`span_hash` 校验),模型不能光声明 hit → **摁死今天实测的 20% 误给率**。
- **④ unsourced 点 fail-closed gate**:无教材 provenance 的点 runtime 拒绝参与给分(现仅 warning)。

### Phase C — 建查询层(KnowQL ②,精髓本体,最后建)
- 在既有 §4.6 `retrieveRubric(question_id, purpose, shape, citation_required, budget_tier)` 契约上建 executor:`ask/shape/ground/budget` → **确定性取该 typed object 的指定字段**,替代"塞 context + 模型自由组织"。
- 复用 ④ 的向量只作"挑哪个 artifact"(编译期/底座),runtime 只做确定性取数。

## 4. 建设禁区(审计 7 条,务必遵守)
D1 query executor 不得变第二套判分 policy engine;D2 不得新增第三套 typed schema;D3 采分点不得拿绕过官方 key 的 canonical 写权;D4 不得暴露 client 可控 release/canonical 状态;D5 不得自建第二套 learner memory/mistake registry;D6 命不中 fail open 或 queue review,不用 regex/prompt 拼接当主理解;D7 不引入第二条聊天/检索 transport。

## 5. 验收(对齐产品 9 价值,不看 headline 总分)
对官方 key(单一权威)测:误给率↓(目标从 20%→个位数)、采分点漏点率、validator 合约通过率、错因标签稳定性、字段 schema 合规率、逐点 MAE;quality_claim 维持 false 直到 owner 裁定 key 复核候选。

## 6. 下一步
当前已从 Phase A/B 的离线与本地 shadow 推进到 Phase C 的窄版 `retrieve_rubric` runtime-consumed + test2 true-entry live-readback。下一步不再是"再写大计划",而是按 `IMPLEMENTATION_LEDGER.md` 推进:

1. 保持 L1 shadow 默认在 qa/operator cohort,禁止 broad production default。
2. 使用 `scripts/run_luban_knowql_nexus_l2_learning_ab.py` 做 L2 v2 多臂实验:A0 baseline / B1 Nexus V1 without KnowQL / B2 Nexus V1 + KnowQL/PGO + Grading-to-Brain + NBA / B3 KnowQL microbenchmark。
3. L2 前后仍必须 `canonical_truth_written=false` / `official_score_written=false`;canonical learner truth、published registry、production default 另走授权包。
4. Ground gate 是评分硬门槛:评分点必须有 `authority_source/span_hash`;无来源点只能解释,不能给分/扣分,也不能进入 PGO GBrain writeback。
5. Learner truth promotion 只能由同一采分点错因的复测验证触发候选;正式 canonical learner truth 仍需单独授权。

## 7. 进展(2026-06-13:Phase B 上线 + G2 接真实数据流)

- **Phase A 已落地**:`luban_per_question_grading_object.v1`(`per_question_grading_object.py`)——每题编译对象,采分点 = 官方答案逐字原子切片(authority A)+ span_hash + 教材 term_provenance(B)/honest unsourced,逐点分 null+pending,validator 锁单一权威。
- **Phase B 上线(G2 接线落地处)**:`build_grading_contract(obj)`(commit 96ed81a78)把编译对象变 judge-ready 合约——官方原子切片 = 评分 checklist;教材引证经 **`resolve_grading_point_authority` 汇成 supporting_citations**(textbook_cited + official_score_allowed=False,永不进对错通道)。**这是 G2 在真实编译数据上的接线**(不是 gate 空列表),`validate_grading_contract` fail-closed。
  - **③ 输出合约**:judge 必须逐 point_id 裁决 + 命中也要 cite 学生证据 span。
  - **摁死误给闸**:`detect_over_credit`(`per_question_grading_judge.py`,commit 8564a7241)= score 实质超出其 verdict 支撑的 coverage(`score - coverage > margin`),**非"高分+任意miss"**(根因纠正:绝对阈值误伤多点题 23/24=0.958 的诚实高分)。
- **A/B harness**(`run_luban_per_question_grading_ab.py`,review-only):arm_A_freestyle vs arm_B_atomic_contract,controlled 学生作答带精确 ground truth。dry-run oracle 端到端证明 plumbing + arm B 结构 over-credit-safe;**`--live` 真 LLM A/B 待 owner 跑(需 key,billable)**——出 arm A vs arm B over-credit 率对比。
- **production `_grade_one_case_v1` 接线 = 待 `--live` A/B 裁决后再做**(别在实验证明前改生产判分消费路径)。Codex 给的最小接线点已记 `RESOURCE_GOVERNANCE_FIX_PLAN §6`。

## 8. `--live` A/B 实测结果(2026-06-13, deepseek-v4-flash, 三臂, confound-hardened)

经两轮 Codex 对抗(治理闸 + 实验设计)+ 13 份手写 paraphrase fixtures + 三公平臂,真 LLM 跑出**支持 thesis**的诚实结论:

| 指标(10 个 riskful fixtures) | A0_freestyle | A1_self_decompose | **B_atomic_contract** |
|---|---|---|---|
| ground-truth over-credit 率 | 0.20 | 0.10 | **0.00** |
| calibration MAE(越低越好) | 0.074 | 0.101 | **0.013** |
| false-hit 率(漏点判hit) | — | — | **0.00** |

- **预测序成立且 B 优于 A1**(不只 A0):B(0) < A1(0.10) < A0(0.20)。Codex 要求的"必须赢公平 A1"达成。
- **复刻 codex 信任崩塌反例**:over_credit_trap_skip_subq5(学生跳过整个小问5,真覆盖 0.75)——A1 给 **1.0**(误给),A0 给 0.75,**B 给 0.75**(正确);over_credit_trap_miss_enumeration(真 0.667)——A0 给 **1.0**(误给),B 给 0.667。
- **B 不是保守压分**:9/10 riskful fixture 上 B 的 score 精确等于 true_coverage(MAE 0.013);A0/A1 双向乱(既误给又误扣)。
- **诚实边界**:小样本(10 riskful / 3 trap)、单模型单次、fixtures 由编译方手写标注(ground truth=作者语义判断)。方向跨每个指标每条 fixture 一致,但非大样本证明;external validity 仍需真实学生答案+独立人工 gold(work order)。

**结论**:confound-hardened demo 支持"编译原子合约摁死误给 + 大幅改善校准",且赢过公平结构化 baseline → **解锁 production `_grade_one_case_v1` 接线**(原 gate "待 --live 裁决"已满足),接线仍属生产判分改动需 owner 授权。工件:`artifacts/luban_grading_artifacts/per_question_grading_ab_20260613/per_question_grading_ab_live_llm.json`。

## 9. 加入 RAG 体系对比(五臂,2026-06-13)——直接回答"编译 vs 现有 RAG"

加两个用真实 kb_v5 检索的臂(production 判分 lane 用的 search_chunks_v2 通道):`arm_RAG_only_openworld`(无官方答案,只给 stem+检索知识=不在题库的开放世界)、`arm_RAG_plus_reference`(官方参考答案+检索知识,holistic=复刻生产 reference+RAG grounding)。五臂同 fixtures。

**calibration MAE(最稳指标,越低越好)**:**B 0.035 < A0 0.062 < A1 0.085 < RAG+ref 0.10 < RAG_only 0.18**。编译原子合约最接近真覆盖;RAG_only(无官方答案)最差,差 B 约 5 倍。

**关键诚实发现**:
- **RAG grounding 反而伤判分**:RAG+ref(0.20 over-credit / 0.10 MAE)比纯 reference 的 A0(0.10/0.062)更差——检索来的教材知识当 distractor 抬分。**复刻 codex 信任崩塌反例**:skip_subq5(学生跳过整个小问5,真 0.75)RAG+ref 给了 **1.0**,而 B 给 0.75(正确)。
- **B 是唯一三个 over_credit_trap 都精确命中真覆盖的臂**(0.667/0.75/0.75)。
- **RAG 的家在"答题/知识召回",不在"判分权威"**:有官方答案(题库案例题)时,编译原子 checklist 是对的工具;把 RAG 知识灌进 judge 只会加噪声抬分。与早期"RAG 赢作答 0.825>0.663、但采分点的家在判分链路"一致。

**诚实方差边界(必须说)**:over-credit **率**在 N=10/单次跑下噪声大(B 在两次跑里 0.0↔0.1、A0 0.2↔0.1 来回跳);**calibration MAE 才是跨两次跑稳定favor B 的信号**(0.013 / 0.035)。要给定论排序需重复多次 trial + 更大 fixture 集 + 独立人工 gold(Codex 的 external-validity work order)。

**给 production 的可执行结论**:题库案例题(有官方答案)→ 用编译原子 checklist 判分(B),**不要**把 RAG 知识当判分依据;RAG 留给开放世界答题/召回。`_grade_one_case_v1` 接线方向因此更明确:接编译 checklist,grounding 不参与对错。

## 10. 方差压实 + 成本实测(trials=5 concurrency=8 + 顺序 latency 校准,2026-06-13)

DeepSeek 真实 LLM,5 次 trial 压方差(排除 21/325 parse_error 行),并发跑 + 单独顺序跑测隔离延迟。

**准确度(MAE/over-credit mean±std,排除 parse_error):**

| arm | calib MAE | over-credit | false-hit |
|---|---|---|---|
| **B 编译原子合约** | **0.013±0.005** | **0.000±0.000** | **0.000** |
| RAG+参考 | 0.049±0.012 | 0.060±0.049 | — |
| A0 freestyle | 0.055±0.015 | 0.080±0.040 | — |
| A1 self-decompose | 0.070±0.013 | 0.054±0.066 | — |
| RAG_only(开放世界) | 0.157±0.019 | 0.040±0.049 | — |

**方差已压实**:B 的 MAE 0.013±0.005、over-credit 0.000±0.000——不仅最准,**方差也最小**,优势是真信号不是噪声。RAG_only 最差(MAE 12x B)。

**成本(隔离单次,顺序跑;真实 serving):**

| arm | total tok | completion tok | latency | TTFT |
|---|---|---|---|---|
| A0 freestyle | 1082 | 290 | 4.1s | 3.7s |
| RAG+参考 | 2944 | 302 | 4.0s | 3.6s |
| **B 编译原子合约** | **2025** | **851** | **7.1s** | **5.2s** |
| RAG_only | 3202 | 753 | 9.4s | 9.1s |
| A1 self-decompose | 2010 | 1202 | 11.3s | 9.3s |

**成本判读**:B 居中——token ~2x A0(checklist+24逐点 verdict),latency 7.1s。但**RAG 臂 token 最贵(2944-3202,被检索块撑大)却判得更差**=判分场景被严格 dominate。**A1(每次现拆 rubric)latency 最高(11.3s/1202 completion)且不如 B**——直接验证"compile once read many":B 复用预编译 checklist,生成更少、校准更好。

**操作性注记**:B/A1 的长结构化 JSON 在高并发/高峰期偶有截断→parse_error(已 3x 重试+记账兜底);生产需更大 token 预算+重试。

**最终判读**:案例题判分 B 决定性最优(准确度 4-12x、零误给、方差最小),成本居中(比 RAG 便宜、比 A1 快)。RAG 判分被 dominate(更贵更不准)→ 印证"RAG 的家在召回不在判分权威"。**解锁 production 接线已有充分实证支撑**,接编译 checklist、grounding 不参与对错。

## 11. L1 live shadow performance A/B(2026-06-15,test2 `/api/v1/ws`)

本轮把 Phase C 的窄版 KnowQL executor 接到真实 `/api/v1/ws` shadow readback,并补齐 PGO same-attempt Grading-to-Brain preview readback。最终有效证据见 `artifacts/luban_grading_artifacts/pgo_l1_live_shadow_ab_20260615T095041Z` 与 `IMPLEMENTATION_LEDGER.md`。

**最终有效跑法**:`connection_mode=per-turn`, `inter_turn_delay_seconds=8`, `pairs=30`, `order_mode=alternating`, `seed=20260615`。此前无节流和 single-connection 长跑均被线上 1013 / WS close 污染,已在 ledger 保留为负证据。

| Metric | A legacy | B PGO shadow |
|---|---:|---:|
| count / ok | 30 / 30 | 30 / 30 |
| success rate | 1.0 | 1.0 |
| p95 latency | 3698.064 ms | 3775.009 ms |
| p95 delta | — | +76.945 ms / +2.0807% |
| avg payload bytes | 23445 | 26175 |
| B fail-open rate | — | 0.0 |
| B PGO shadow effective | — | 30/30 |
| B KnowQL runtime consumed | — | 30/30 |
| PGO G3 preview readback | — | 30/30 |
| canonical truth writes | 0 | 0 |
| official score writes | 0 | 0 |

**Decision**:`L1_SHADOW_AB_GO` for qa/operator live shadow performance only. It proves B arm can run through real entry without significant p95 degradation and without canonical/official writes. It does **not** authorize broad production default, published registry, official scoring, or canonical learner truth.

## 12. L2 learning-efficiency A/B runner(2026-06-15, v3 prereg landed-local)

L2 的目标不是再测 KnowQL 单点,而是测 Nexus/KnowQL/GBrain 一体化闭环对复测 delta 的影响。旧 smoke 已证明链路能跑通;当前前置已从“B2 接线是否读回”推进到“固定 prereg 指标后扩大样本与 loops 跑正式 L2”。不能再把 one-loop smoke 或 B3 microbenchmark 写成学习效率结论。

- `scripts/run_luban_knowql_nexus_l2_learning_ab.py`
- `tests/scripts/test_luban_knowql_nexus_l2_learning_ab.py`

四臂定义:

| Arm | 定义 | 指标用途 |
|---|---|---|
| A0 | 原 RAG/ref baseline `/api/v1/ws` deep_question grading path | 学习效果 baseline |
| B1 | Nexus V1 case-rubric score-first shape,不带 KnowQL/PGO/GBrain | shape isolation:只测 Nexus V1 基础收益与成本 |
| B2 | Nexus V1 + deterministic KnowQL/PGO + Grading-to-Brain preview + NBA targeted retest | 一体化闭环主实验 |
| B3 | 直接调用 `retrieve_rubric` | 仅 query latency/payload,不参与学习效果 |

v3 runner 固定 prereg 观测:

- TTFT、first result latency、streaming observed rate、payload bytes、总耗时。
- `sealed_block_status`:当前真实 `/api/v1/ws` 没有独立 sealed score block 事件,所以如实记录 `not_exercised`,不伪造 pass。
- `grading_shape.score_first`:先暴露分数、命中/漏点;解释、口诀、建议先标 `same_result`,后续可异步化。
- `learner_truth_promotion_preview`:同一采分点 initial miss -> retest resolved 才生成稳定画像候选,且 `canonical_truth_written=false`。
- `compiler_feedback_loop`:高争议点、低置信点、教师修正、学生常漏点只生成下一版 artifact work order,不自动发布。
- 样本 manifest 固定为 5 个 PGO-backed 案例采分点场景,带 `sample_manifest_hash`。
- 主效应指标固定为独立脚本 gold terms 的 `b2_outcome_miss_reduction_lift_vs_b1`,不再用各 arm 自报 `score_ratio` 当学习效果 authority。
- B3 只作为 KnowQL latency/payload guardrail,不进入 learning-effect decision。
- 正式 L2 默认 `loops=10`, `min_loops=10`, `b3_iterations=30`, paced per-turn,失败出口码仍为 NO-GO 而非脚本异常。

旧 test2 smoke artifact:`artifacts/luban_grading_artifacts/knowql_nexus_l2_learning_ab_20260615T104707Z`。该 evidence 属于 v1 arm 定义(B1/B2 都带 PGO),只证明旧链路可跑通,不再作为 v2 效果结论。

v2 live smoke artifacts:

| Artifact | Result | Finding |
|---|---|---|
| `knowql_nexus_l2_learning_ab_20260615T113738Z` | NO-GO / not evaluable | Runner sent non-allowlisted `ab_arm/runtime_mode`; all WS turns failed fast; B3 5/5. |
| `knowql_nexus_l2_learning_ab_20260615T113916Z` | NO-GO / not evaluable | A0 succeeded 2/2, but explicit `grading_engine_case_rubric_v1` caused B1/B2 start failures. A0 already returned V1 score-first, so current test2 cannot isolate pure RAG/ref baseline. |
| `knowql_nexus_l2_learning_ab_20260615T114120Z` | NO-GO / B2 closure missing | A0/B1/B2 true-entry WS all succeeded 2/2; B3 5/5; canonical/official/unsafe writes 0; TTFT/streaming/score-first captured. B2 did not emit PGO shadow / KnowQL runtime consumption / PGO-G3 preview, so Nexus+KnowQL+GBrain loop was not exercised live. |
| `knowql_nexus_l2_learning_ab_20260615T122930Z` | NO-GO / safety GO / effect neutral | B2 PGO shadow effective 2/2, KnowQL runtime consumed 2/2, PGO-G3 preview 2/2, NBA intervention 1/1, canonical/official/unsafe writes 0. This closes the B2 wiring/readback concern, but it is one-loop smoke and showed no positive delta, so it is not L2 learning-efficiency evidence. |

| Metric | A0 | B1 | B2 | B3 |
|---|---:|---:|---:|---:|
| WS turns ok | 2/2 | 2/2 | 2/2 | n/a |
| completed loops | 1 | 1 | 1 | n/a |
| legacy score retest delta | 0.0 | 0.0 | 0.0 | n/a |
| PGO miss reduction | n/a | 1.0 | 0.0 | n/a |
| PGO shadow effective | n/a | 2/2 | 2/2 | n/a |
| KnowQL runtime consumed | n/a | 2/2 | 2/2 | 5/5 direct |
| G3 preview readback | n/a | 2/2 | 2/2 | n/a |
| B3 query p95 | n/a | n/a | n/a | 10.853 ms |
| canonical / official / unsafe writes | 0 | 0 | 0 | 0 |

Old smoke decision:`L2_LEARNING_AB_GO` at smoke scope, because safety passed and B1 reduced PGO miss count by +1 vs B2 under the old arm mapping. Current reliable interpretation: B2 true-entry PGO/KnowQL/G3 readback has been observed safely, but one-loop smoke produced neutral effect. Therefore the correct next move is formal preregistered L2 with larger samples/loops, not more B2 wiring work and not production authorization.

硬边界:

- B3 不能参与学习效果结论。
- B1 不得出现 PGO/KnowQL/G3;B2 必须出现 PGO/KnowQL/G3 才能评价闭环。
- `summary.json` 必须分开 `safety_status` 和 `effect_status`;安全 NO-GO 时效果不可评价。
- 任何 canonical learner truth、official score、production write、A0 PGO contamination、B1 PGO contamination 都是 NO-GO。

正式 L2 执行门:

1. 先使用 v3 runner 固定 prereg manifest、主效应、guardrail、缺失值/安全 NO-GO 规则。
2. 然后在 test2 真实 `/api/v1/ws` 跑 `loops>=10`, `min_loops>=10`, `b3_iterations>=30`, `connection_mode=per-turn`, `inter_turn_delay_seconds>=8`。
3. 通过标准:B2 safety GO;B2 PGO/KnowQL/G3/NBA 读回全满足;canonical truth writes=0;official score writes=0;unsafe writes=0;B3 p95 低于 prereg guardrail;B2 p95 latency/payload 相对 B1 不越线;主效应 `b2_outcome_miss_reduction_lift_vs_b1` 达阈值。
4. 若正式 L2 仍 neutral/negative,先诊断 deterministic query 质量、ground enforcement 严格度、NBA actionability、retest 题同构性或 learner truth promotion 门槛;不得把 B3 latency 或 self-reported server score 写成学习效率提升。
