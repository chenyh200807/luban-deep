# 评分知识结构化 — 北极星目标 + 外部循证(LLM-as-judge rubric)

> **不另起主线**。本文挂靠 `KNOWQL_BUILDOUT_BLUEPRINT.md`(→ §4.6 `2026-06-09-luban-nexus-like-scoring-artifact-engine-execution-plan.md`)。
> 只做两件事:(1) 把北极星目标记录进主线;(2) 把外部 LLM-judge rubric 文献蒸馏成"能改变某个下一步决策"的几条循证 + 验收门槛。
> 三原则约束本文:**thin wrappers / first principles / less is more**——研究是弹药不是命令,只采纳能让**现有 skill**(`per_question_grading_object`、`build_grading_contract` 的 judge、learner_state 的 Grading-to-Brain loop)更聪明的,凡"再加一层机器"的拒。
> 与 `nexus_essence_research.md` 不重叠:那份是 Nexus 机制,本文是 LLM-as-judge 判分文献。

## 1. 北极星目标(产品级,记录)

```
评分知识结构化
 → 采分点判断更准
 → 错因标签更稳定
 → 学情画像更可信
 → 学习建议更具体
 → 用户感觉"它真的懂我"
 → 留存与付费理由增强
 → 鲁班形成专用教育知识资产并持续复利
```

落到可验证产物:批改更准 / 采分点不漏 / 扣分原因清楚 / 学情画像有证据 / 复习建议可执行 / 用户更信任 / 产品壁垒更深 / **模型替换成本更低** / 数据资产复利。

**关键 reframe(实测已证):** "编译赢不过 RAG"的痛苦来自**编了错的层**(教学 context——信息论上注定平 RAG)。本目标是**对的层**(原子采分点判分),而 `KNOWQL_BUILDOUT_BLUEPRINT §8/§9` 的 live 五臂 A/B 已实测:calibration MAE **B 编译原子 checklist 0.035 < A0 0.062 < RAG+ref 0.10 < RAG_only 0.18**,误给率 0.20→**0.00**,且 RAG grounding 反而抬分伤判分。**北极星目标正落在被证明赢 RAG 的那条路径上。**

## 2. 外部循证蒸馏(5 条 high/medium,全在"采分点判分"环)

证据等级:学术一手 + 三票对抗验证(deep-research 2026-06-13)。每条只留**对鲁班的可执行映射 + 验收指标**。

| # | 文献结论(出处) | 对鲁班的可执行映射(thin) | 验收指标 |
|---|---|---|---|
| F0 | **分项 rubric 是共识,但赢在可诊断/可审计/抗 halo,不是天生更准**;per-criterion 原子判 + 强制自然语言依据是抗"criterion conflation"的命名解法(Autorubric 2603.00077;FLASK 2307.10928) | **确认主线**:采分点=官方答案逐字原子切片 + 命中也要 cite。**理由收口**:我们选分项是为了下游错因/学情可溯源,**不是赌它抬总分** | 每采分点 vs 专家 Cohen's κ **≥0.6**;带教材 provenance 的点占比 |
| F1 | **分项不自动赢 holistic;粒度越细可靠性骤降**:二元→5 级 acc 76%→57%、κ 0.51→0.34;deferral 把 acc 77.4%→81.1%(Rubric-Conditioned Grading 2601.08843) | **采分点判定保持二元 MET/UNMET**,禁止给每点加 0-5 序数尺度(主线现为 null+pending,符合);低置信点走**现有 D6 fail-open/queue-review = deferral**,不新建 | 每点 acc/κ 随标签基数曲线;某点需 >2 级即**拆成多个二元点**,不升序数 |
| F2 | **naive rubric 四病**:覆盖不足/维度混淆/偏好方向错/冗余高相关;RRD 递归拆解-过滤 + 去相关加权 → JudgeBench **+17.7 pts**(2602.05125) | **这是"判错须独立"约束的工程解**。在**现有 compile 步**(`per_question_grading_object`)加一道**去相关过滤**:官方原子切片多数天然独立,但两点复述同一要求时合并/降权。**是 compile skill 内的过滤,非新系统** | 采分点对间相关系数分布;冗余点合并率;合并前后逐点 κ 提升 |
| F3 | **RubricRAG**:从语义相似旧题检索人写 rubric 当 few-shot,胜 zero-shot 甚至胜 post-training(ρ 0.545 vs 0.426);**但更宽的检索泛化被对抗验证否决**(2603.20882,medium) | **仅开放世界(无官方 key)候选用**;检索来的 rubric **≠ 官方权威,必须停在 supporting/candidate**(否则违反单一权威 D3)。**现在不建**,记为开放世界路径备选 | (暂不立指标) |
| F4 | **聚合方式独立影响人机一致性**;保守 Pareto-dominance 对任一子项分歧超敏、反而降一致(2605.06283) | **逐点 verdict → 总分的聚合是独立可调决策**:别用过保守聚合(呼应主线"B 不是保守压分"的诚实边界)。**是聚合函数的选择,非新机器** | 聚合后 vs 专家总分一致性;过保守误扣率 |

## 2b. 外部循证蒸馏(环1 错因标签稳定性,deep-research 第二轮 2026-06-13)

第二轮专攻下游四环,但环 2-4(学情画像/学习建议/数据飞轮)所有 KT/OLM/冷启动/间隔重复/飞轮 claim **两次都被 API 限流打掉验证投票,无存活结论**(见 §6)。只有**环 1 错因标签**拿到强证据:

| # | 文献结论(出处) | 对鲁班的可执行映射(thin) | 验收指标 |
|---|---|---|---|
| E0 | **错因标签(buggy procedure)才是学习证据的单位,不是对错计数;但只部分稳定**:~40% 学生有一致 bug、~60% 没有(Brown & Burton 1978) | 错因标签作 learning-evidence 原子单位**已落地**(原子采分点层);薄改造=在 `learner_memory_events → learner_state` 边界给每标签挂**稳定性/置信字段**,**单次错因标签须达最小重复观测阈值**才动 mastery | 单标签移动 mastery 前的最小重复观测数;一致 buggy 率监测 |
| E1 | **LLM 标的错因标签未经"该任务专属"人工金标验证前不可信**:可靠性随数据+任务高度异质,**不能全局验证一次复用**;要**逐类别**而非一个聚合 κ(Pangakis 2023) | 建**逐错因类别 × 题型**的人工金标小集,每类别存一个可靠性数;**仅过线类别满权重进 learner_state**,稀有/未验证类别**降权流入**。是验证 harness 加件,**非第二套标注系统** | 每错因类别可靠性数(覆盖率);未验证类别降权比例 |
| E2 | **IRR 用 chance-corrected 系数**(Cohen's κ / Gwet's AC1 / Krippendorff's α),拆成人-机 κ_H-M 与机-机 ρ_M-M;LLM 标注是**测量仪器非真值**,沿 reliability/calibration/drift/consensus/aggregation/transparency 六维监测(OLAF,medium) | 给现有错因标注器**包一层可靠性监测**:记 κ_H-M(对金标)+ ρ_M-M(多次/多 prompt)+ 漂移信号(标签分布散度)。是 observability 仪表,**非新模型** | Krippendorff α 分档(**<0.667 弃 / 0.667-0.8 暂用 / ≥0.8 可靠**),**逐类别**;**⚠️ 本批明确否决"单一 κ≥0.6 全局门",不要硬编一个阈值跨异质类别** |
| E3 | **错因 taxonomy 必须满足可区分性/MECE**:暴露一个 bug 只需一道题,但**诊断一个 bug 需要能把它和所有其它 bug 区分开的题**(Brown & Burton 1978) | 加**taxonomy 诊断性审计**:每个错因叶,检查现有题库是否有题能把它和兄弟错因区分;非诊断簇标为覆盖缺口。**直连现有 canonical taxonomy 工作**,不建新基础设施 | 每错因叶的"诊断性"(等价类大小);无法区分的错因簇数 |

> 与采分点判分 κ≥0.6 的关系:**不矛盾,各在各 lane**。κ≥0.6 是**逐采分点 vs 专家判分**(第一轮 F0);错因标签可靠性是**逐错因类别标注一致性**,用 Krippendorff 分档**逐类别**算,**禁止单一全局门**(第二轮 E2 明确否决)。

## 3. 落地动作(全是现有 skill 的薄改进,映射现有 Phase)

1. **Phase A/B 已对**:二元原子 checklist + 命中要 cite + 摁死误给 = F0/F1 共识。**无需改向,只补验收指标**(§4)。
2. **唯一新增的薄改动 = F2 去相关过滤**:挂在 `per_question_grading_object` 编译期,删/降权冗余高相关采分点。先量相关分布再决定阈值(first principles:官方切片多数已独立,只治残余相关)。
3. **F1 deferral / F4 聚合**:都用现有机制(D6 queue-review、现有聚合函数),只是**显式调参 + 立指标**,不加层。
4. **F3 RubricRAG**:不建。仅在开放世界判分(无官方答案)将来需要时,作为 supporting-only 候选评估,且永不铸权威。

## 4. 验收指标(并入 BLUEPRINT §4,对官方 key 单一权威测)

在主线已有的"误给率↓ / 漏点率 / validator 合约通过率 / 逐点 MAE"之上,补外部循证给的三道门槛:

- **每采分点 vs 专家 Cohen's κ ≥ 0.6**(F0,"substantial");
- **采分点全部二元 MET/UNMET**,任何点需 >2 级一律拆分(F1);
- **采分点对间冗余/相关受控**(F2,去相关过滤后逐点 κ 不降、总分一致性不被单点超敏拖累 F4)。
- `quality_claim` 维持 false 直到 owner 裁定。

## 5. 我们明确不建什么(减法纪律 = less is more + §5.7 单一权威)

- **不建第二套错因 taxonomy 引擎**:错因标签复用现有 `error_code_registry` + `learning_synthesis`,只让它证据化/稳定化。
- **不建第二套 learner memory / 学情引擎**:复用 `learner_memory_events`(唯一证据账本)+ `LearnerStateService`(长期 truth authority)。
- **不建知识追踪新平台 / 数据飞轮新平台**:数据资产复利是现有 Grading-to-Brain loop 的产物,不是新系统。
- **不建第二套 rubric 检索权威**:RubricRAG 若用,停在 supporting/candidate,官方 key 永远优先。
- **不升采分点为序数评分**:二元 MET/UNMET 即最高可靠性,别为"更细"牺牲 κ。

## 6. 调研覆盖与开放前沿(诚实:两轮 deep-research 状态)

- **已覆盖(强证据)**:采分点判分(§2,第一轮)+ 错因标签稳定性(§2b,第二轮)。
- **仍开放(两轮都被 API 限流打掉验证投票,无存活结论)**:
  - **证据驱动学情画像**:BKT/DKT/PFA 适用条件与 calibration、OLM 可信度、稀疏/冷启动可靠性。
  - **可执行学习建议**:next-best-action / 间隔重复(FSRS)/ 掌握度阈值的循证参数。
  - **数据飞轮与护城河**:复利型数据资产、降低模型替换成本、护城河实证。

> **决定(less is more)**:不再烧第三轮 ~350 万 token 赌限流恢复。这三环在鲁班**已有实现且已用对模式**(`mastery_estimator` 的 Beta-Bernoulli 后验 + Leitner 式 `DECAY_PROFILES`;`per_question_grading_object` 判断即数据)。改造计划里这三环的薄改造**从第一性原理 + 现有代码**推导,**明确标注"非外部对抗验证"**,不编造引用。要补外部循证时错峰单环重跑即可。

## 7. 出处

- Autorubric — analytic vs holistic 共识与抗 conflation:https://arxiv.org/html/2603.00077v1
- FLASK — skill-set 级细粒度评测(ICLR 2024 Spotlight):https://arxiv.org/pdf/2307.10928
- Rubric-Conditioned Grading — 粒度↑可靠性↓、deferral:https://arxiv.org/pdf/2601.08843
- Rethinking Rubric Generation (RRD) — 四病 + 去相关加权 +17.7:https://arxiv.org/pdf/2602.05125
- RubricRAG — 检索式 rubric(medium,宽泛化被否决):https://arxiv.org/html/2603.20882v1
- 聚合方式影响一致性、Pareto 超敏:https://arxiv.org/html/2605.06283v1
- Brown & Burton 1978 — bug 即诊断单位 / 部分稳定(~40%)/ MECE 可区分性:https://files.eric.ed.gov/fulltext/ED159036.pdf
- Pangakis 2023 — LLM 标注须逐任务人工验证、可靠性异质:https://arxiv.org/pdf/2306.00176
- OLAF 2025 — chance-corrected IRR 六维(medium,否决单一 κ 门):https://arxiv.org/html/2512.15979
