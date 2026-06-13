# 鲁班 KnowQL 补齐蓝图（单一权威 native）

> 综合三份专家研究 + 今天判分 A/B 的实证,产出可建蓝图。
> **不另起规划主线**:本蓝图挂靠既有 §4.6「Narrow KnowQL-Inspired Query Contract」
> (`docs/plan/评分引擎与金标工件/2026-06-09-luban-nexus-like-scoring-artifact-engine-execution-plan.md`)。
> 输入研究:`nexus_essence_research.md` / `current_state_gap_and_second_authority_audit.md` / `typed_object_requirements_by_question_type.md`。

## 0. 决定性诊断(一句话)

我们把 Nexus 的 `compile → deterministic-retrieve` 做成了 `compile → stuff-context → model-freestyle`——**后半段塌回了 RAG**。而鲁班判分(重复查询、单一权威、教材字段级溯源)恰好落在 **Nexus 赢面**,我们却用了那条输的路径。

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
**先做 Phase A**(确定性收敛 schema,无 LLM,低风险,消掉最大第二权威 R1)。Phase B/C 待 Phase A 落地 + owner 审蓝图后逐阶段推进。
