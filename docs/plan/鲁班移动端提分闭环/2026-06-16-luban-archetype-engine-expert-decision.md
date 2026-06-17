# 鲁班母题引擎专家组共同决策稿

> Status: Proposed / Expert Decision
> Date: 2026-06-16
> Scope: 如何利用现有数字资产,以最高杠杆做出顶尖母题引擎与顶尖学习体验。
> Principle: thin wrappers and fat skills / first principles / less is more.
> Non-authority: 本文不替代 `case_family` schema、深母题数据标准、评分 artifact、Learning Brain 或 source registry。本文是专家组对"下一步怎么用资产"的共同决策与执行路线。

## 0. 专家组结论

本轮召唤并整合了 7 类专家视角:

| 专家 | 结论关键词 |
|---|---|
| 数据资产总架构 | 不是缺数据,而是缺把 shadow/candidate 资产升格为可签发资产的最后一公里 |
| 教育测量 / 知识追踪 | ECD/Q-matrix/AIG/KT 只能降级为证据语法,不能建第二套测评平台 |
| 阅卷 / 评分规则 | 第一批要证明 anti-over-credit,优先网络计划/计算步骤/改错/N-of-M/术语边界 |
| LLM/RAG/编译架构 | 不建第二套 RAG,做 candidate -> reviewed -> RC -> runtime_supply 的签发流水线 |
| 学习体验 / UX | wow 来自"看穿我的失分机制 + 明天换皮证明我进步",不是题库规模 |
| 数据标注 / 教研生产线 | 留存实验产出真实作答与边界答案候选,回流到既有 review queue / compiler feedback |
| 合规 / 来源权威 | 壁垒不靠展示第三方原文,靠 source registry + span hash + authority tier + 自研结构化抽象 |

共同决策:

```text
鲁班母题引擎第一阶段不是"大规模整理题库",
而是把已有 raw/source/shadow/candidate 资产编译成少量可签发、可回滚、可被 runtime 精准调用的 Deep Archetype Pack。
```

更具体地说:

1. 前台先用 `F16 防水` 做 5 天留存薄切片,验证忙碌复考成人是否愿意每天回来。
2. 后台第一条深母题旗舰不选 F16,而选 `F01 进度网络计划` 或同等级计算/步骤分母题,证明鲁班能比普通 AI 更稳地按采分点批改。
3. P0 最高杠杆不是继续扩 30-40 个包,而是抽完真题 PDF 分值、对齐 per_question/v3.2/PDF rubric、冻结 source registry、建立边界答案闭环。
4. 第一版不展示"掌握度 78%"这类伪精确数字,只展示证据标签:刚暴露的盲点、待复测、正在改善、临时掌握、证据过期。
5. LLM 只产候选和解释,确定性程序守 authority,人类专家签发教育/评分责任。

## 1. 三大原则如何落地

### 1.1 Thin Wrappers and Fat Skills

母题引擎必须是胖能力内核,不是把逻辑散落到前端、prompt、router、RAG wrapper 里。

| 层 | 应该薄 | 应该胖 |
|---|---|---|
| 前端 | 只展示任务、诊断、复测状态 | 不计算掌握度,不私造错因,不拼判分规则 |
| runtime adapter | 只按 attempt 构造 request-scoped `LubanContextPack` view/envelope | 不扫 artifacts,不临场决定 registered source_ref |
| LLM prompt | 只消费签发包和 request-scoped `LubanContextPack` view | 不自由生成官方答案、评分规则、错因码 |
| Compiler / Skill | 读取 source registry allowlist,产出候选/签发包,通过既有 `runtime_supply` / `LubanContextPack` 发布 | 这是母题引擎真正的 fat skill,但不拥有 source registry 或 runtime authority |
| Grading / Learning Brain | 评分、证据、长期学情各归各自 authority | 母题包只发候选和引用,不写 learner truth |

### 1.2 First Principles

一等业务事实不是"我们有很多题"。

一等业务事实是:

```text
系统能基于可信来源和采分点证据,
判断学生在某个母题不变量上为什么失分,
并安排下一次可验证的训练/复测。
```

所以唯一正确的数据链路是:

```text
source evidence
-> scoring / teaching candidate
-> deterministic gate
-> expert review
-> signed archetype pack
-> 既有 runtime_supply / LubanContextPack scoped context
-> construction_grading / evidence builder
-> learner_memory_events.learning_evidence
-> Learning Brain / LearnerStateService
-> NextBestAction / revalidation_queue
```

任何绕开这条链的方案,即使短期看起来更快,都会制造第二套 authority。

### 1.3 Less Is More

第一版少做,但要真。

不做:

- 不做全书 30-40 个母题铺开。
- 不做第二套 RAG。
- 不做母题 God Object。
- 不做"AI 自己出题、自己抽采分点、自己批改"的 generate-then-grade 闭环。
- 不把 shadow / LLM jury / 合成学生答案写成人审边界样本或真人终裁。
- 不展示伪精确掌握度。

只做两条线:

| 线 | 目标 | 为什么 |
|---|---|---|
| F16 前台留存薄切片 | 5 天 MCQ/轻练/错因/复测,验证用户回来 | 低摩擦,能采集真实行为与错因 |
| F01 深母题判分旗舰 | 进度网络计划/步骤分/关键线路/工期调整 | 有步骤分、计算逻辑、边界答案,最能证明普通 AI 会过度给分而鲁班守得住 |

## 2. 手上数字资产该怎么用

### 2.1 可直接进入母题包的资产

| 资产 | 现状 | 用法 |
|---|---|---|
| 2015-2025 真题 JSON | 337 选择 + 218 案例,全映射 taxonomy | question binding、题目来源、原题复盘、same-node 复测 |
| 章节客观题 | ZL500 403 + 千题斩 630 | MCQ 轻练、干扰项诊断、低摩擦留存 |
| taxonomy | 约 2116 nodes / 1976 leaves | `taxonomy_ref.node_codes`,不复制 title 建第二知识树 |
| 教材 v3 / 标准 JSON | 有 chunk/page/source_meta | source evidence、知识点定义、规范依据 |
| PDF 分值抽取协议 | 2025 首份验证完成,确认 per-point 分值存在 | 回填 `score:null`,形成评分 bootstrap |
| RichLeaf v3.2 | 1612 单元 / 5705 采分点,有 quote_verified provenance | 采分点语义、教材锚点、required terms |
| per_question grading object | 218 案例 / 482 点,但 score null | 与 PDF rubric/v3.2 对齐后做 production 指针层 |
| 313 深编译候选 | procedures/numeric/common_mistakes 较强 | 补 invariant、canonical_logic、misconception candidate |

### 2.2 只能做候选,不能当权威的资产

| 资产 | 只能做什么 | 不能做什么 |
|---|---|---|
| 佑森/机构 PDF 分值 | `training_org_analysis` 的评分估计 | 不能说官方阅卷标准 |
| LLM jury / AI council label | shadow replay、候选质检、发现争议点 | 不能冒充真人终裁或人审边界样本 |
| 合成学生答案 | 诱导样本、边界草稿、模型压测 | 不能代表真实学生分布 |
| 讲义 / 机构口诀 | 教学解释、误区、变题素材 | 不能覆盖教材/规范,不能长段展示 |
| Graphify cards / PNG | 人读线索、UI/教学候选 | 不能当 registered source_ref |
| v24/v232/v26 老候选 | 历史参考 | 不能进 release 默认链 |

### 2.3 当前最大缺口

不是题目数量。

真正缺口是:

1. 真实考生作答 = 0。
2. 真人教师/PO 签字 = 0。
3. PDF rubric 未全量抽取并回填。
4. per_question 粒度有塌陷,一些多点被压成单点。
5. 边界答案、弱表达、near-miss 样本不足。
6. source authority / display policy / training policy 未进 schema 硬门。

这些缺口正好解释为什么留存实验必须和母题引擎一起做:每天训练、复测、半写和批改,是为既有 `learning_evidence` 链路采集真实作答、边界表达和误解分布,不是新增学习证据系统。

## 3. 建议的母题引擎数据架构

### 3.1 不新建第二套 RAG

母题引擎不是新的知识库入口,而是一个签发型编译系统:

```text
S0 source registry allowlist / source_refs / sha256 / span_hash
-> S1 OCR/视觉抽取/解析
-> S2 taxonomy/question/scoring 对齐
-> S3 LLM Candidate Compiler
-> S4 Deterministic Gate
-> S5 Expert Review
-> S6 Release Candidate Pack
-> S7 既有 runtime_supply / LubanContextPack 发布
-> S8 Request-scoped scoped context
-> S9 被既有 grading / generation / teaching / revalidation 消费
```

runtime 只允许通过既有 `runtime_supply` / `LubanContextPack` 读取签发过的 pack,不扫 `artifacts/`、不临时拼 raw PDF、不吃未签 candidate。

### 3.2 两对象继续保留

沿用既有设计:

| 对象 | 作用 | 边界 |
|---|---|---|
| `case_family_production` | 指针层: source、question binding、grading artifact refs、task scope | 只引用,不拥有 rule/content |
| `case_family_structure` | 教学层: invariant、examiner intent、representations、surface generator、misconceptions、retest discriminator candidate | 只做 teaching/diagnosis context,不写分数/错因结论/学情真相 |

这正好符合 thin wrappers and fat skills:生产指针层薄,教学结构层胖,正式评分仍归 scoring artifact,长期学情仍归 Learning Brain。

### 3.3 必须补进 schema 的治理字段

合规专家建议把四类字段变成硬门,否则后面会散落到业务逻辑:

```text
source.display_policy
source.training_policy
rubric_evidence.score_authority
rubric_evidence.official_claim_allowed
```

最小 source/evidence 字段:

```text
source_id
document_kind
source_lane
authority_tier
authority_scope
rights_status
display_policy
training_policy
license_or_consent_id
source_path
source_sha256
page_num
chunk_id
json_pointer
span_hash
extraction_method
ocr_status
quote_verified
score_authority
scoring_stage
reviewer_type
official_claim_allowed
product_use_allowed
```

关键原则:

- `source_quote_allowed` 不等于 registered `source_ref`。
- `official_total_score` 不等于 `per-point official rubric`。
- `provider_estimate` 不等于 `official_score`。
- `LLM candidate` 不等于 `reviewed pack`。

## 4. 第一批母题选择

### 4.1 前台: F16 防水留存薄切片

F16 的定位:

```text
验证"忙碌复考成人会不会每天回来",
不是证明案例深母题护城河。
```

5 天剧情:

| 天 | 主题 | 体验 |
|---|---|---|
| Day 1 | 工序顺序 | 2-3 道 MCQ + 选错透视 |
| Day 2 | 迎水面 / 搭接方向 | 换皮复测昨日盲点 |
| Day 3 | 节点先行 | 用新场景测同一不变量 |
| Day 4 | 混合场景 | 防止背原题 |
| Day 5 | 综合复测 | 给进步收据,不显示伪掌握结论 |

产出:

- 每个选项绑定 `misconception -> error_code -> correction`。
- 每次作答写 attempt-level signal。
- 错题进入次日 same_point / same_node 复测。
- 展示"刚暴露的盲点 / 待复测 / 正在改善 / 临时掌握"。

### 4.2 后台: F01 进度网络计划深母题旗舰

F01 优先理由:

1. 真题方向性频次高,案例属性强。
2. 选择题少,几乎纯案例能力,更能体现差异化。
3. C 层已有 `procedures / rules / numeric_constraints`。
4. PDF 解析里有步骤分、网络计划路径分、工期调整分。
5. 普通 AI 容易看大意给分,鲁班可以按步骤和证据守住边界。

F01 要证明的不是"会生成题",而是:

```text
学生写得像懂,但关键线路/总工期/调整措施/步骤分不满足采分点时,
鲁班能保守判分、给出证据 span、指出哪一步理解断了。
```

### 4.3 第二梯队候选

| 母题方向 | 价值 | 前置补料 |
|---|---|---|
| 大体积混凝土温控 | 频次高,措施型代表 | 补 GB50496 温控因果链 |
| 安全/危大方案 | 高频,强程序/责任边界 | 规范条款与场景校验 |
| 质量/验收 | 高频,适合改错/程序题 | 验收流程和边界答案 |
| 成本/索赔/挣值 | 公式强,步骤分清楚 | formula registry + 容差/carry-forward |

## 5. 评分引擎必须先证明 anti-over-credit

第一批不要选最开放的论述题,要选能让普通 AI 过度给分的题型:

| 题型 | 证明什么 |
|---|---|
| 网络计划 / 关键线路 / 工期调整 | 路径、工期、调整措施必须逐步命中 |
| 造价 / 费用 / 进度计算 | 步骤分、单位、容差、carry-forward |
| 改错题 | 只指出问题不等于写出正确改法 |
| `写出 N 项即得 N 分` 列举题 | 封顶、去重、超答不加分 |
| 标准术语近似题 | "挖掘机" vs "反铲挖掘机"这类 overbroad 边界 |
| 程序/顺序题 | 顺序错、漏步骤、只写泛化词都要扣 |

评分规则:

```text
sub_q_score = min(sum(point_award_i), sub_q_total_score)
```

`point_score` 是踩点池权重,`sub_q_total_score` 是小题封顶。两者都要保存,不能互推。

`point_award_i` 至少支持:

- `hit`
- `partial`
- `miss`
- `unsupported`
- `overbroad / wrong_specificity`

## 6. 学习体验决策

产品上不要把母题引擎包装成题库。

普通题库问:

```text
你做对了吗?
```

鲁班要问:

```text
你为什么会被这类题骗住?
明天换个场景还会不会错?
```

核心体验:

```text
今日一刀
-> 表皮试探
-> 透视揭底
-> 定位证据
-> 一句纠正
-> 明日换皮复测
-> 进步收据
```

LearnerState read-model 第一版不要做全书大图,只做"盲点证据视图":

| 状态 | 含义 |
|---|---|
| 未触达 | 没有证据 |
| 已暴露 | 曾经错过或高自信错 |
| 待复测 | 已安排 same_point / same_node |
| 正在改善 | 复测通过一次 |
| 临时稳定 | 换皮复测通过,但仍需时间验证 |
| 证据过期 | D7 未复测 |

这些状态只能是 `LearnerStateService` / `revalidation_queue` 的 read-model projection,前端和母题资产不得自算或写入。

## 7. 30 / 60 / 90 天路线

### 7.1 前 30 天

| 时间 | 动作 | 产出 |
|---|---|---|
| Day 1-3 | 冻结 source registry allowlist | 只允许 `2026_副本/题库`、`2026教材/第二次加强`、标准文件、真题 PDF、指定讲义进入编译 |
| Day 1-7 | 抽完 2024/2023/2021/2022/2022 补考 PDF rubric,复核 2025 | per-point rubric + `score_authority` + 封顶规则 |
| Day 5-12 | 对齐 PDF rubric / per_question 482 点 / v3.2 5705 点 | review queue,不硬凑 |
| Day 8-15 | 做 F01 进度网络计划深母题 RC 样板 | source pack + scoring refs + variant boundaries + boundary answers draft |
| Day 8-15 | 做 F16 5 天留存薄切片 | 前台任务流 + 复测机制 + 行为证据 |
| Day 12-20 | 映射 MCQ 干扰项、common_mistakes、知识卡易错点到 `ERROR_CODE_REGISTRY` | misconception candidate registry |
| Day 15-25 | 采集 30-50 条边界答案 | real answer 优先,专家裁决兜底 |
| Day 20-30 | 跑质量门与 shadow eval | 过则 RC,不过保持 candidate |

30 天内明确禁止:

- 禁止扩到 30-40 个母题。
- 禁止自动化量产。
- 禁止把 shadow 当 active。
- 禁止宣称 official scoring moat。

### 7.2 60 天

条件: F16 D1/D7 留存过闸,且 F01 质量门过闸。

目标:

- 扩到 5 个包,不是 40 个。
- 每包 20-40 道诊断 MCQ / 轻练任务。
- 每包 30-50 条边界答案。
- 建立周校准会、分歧队列、返工规则。
- 建 2 个生产小组,共享规范/施工/AI 评测。

### 7.3 90 天

条件: 5 包留存、批改、边界答案闭环稳定。

目标:

- 扩到 15 个正式或准正式包。
- 真实作答持续采集。
- 建立人审边界样本池、模型回归集、返工看板。
- 准备 30-40 包扩产,但继续 gated on retention。

## 8. 团队配置

最小可行团队不是 2-3 人,否则会把创始人拖进逐条生产。

30 天建议:

| 角色 | 人数 | 关键职责 |
|---|---:|---|
| 母题产品/架构负责人 | 1 | 定义包结构、gate、产品体验、优先级 |
| 一建建筑实务教研 | 2 | 不变量、出题人意图、训练路径 |
| 阅卷/批改专家 | 2 | 采分点、partial/miss、边界答案终裁 |
| 规范/来源专家 | 1 | source authority、规范版本、展示边界 |
| 施工现场专家 | 0.5-1 | 场景真实性、流程合理性 |
| 标注员 | 3-4 | PDF 抽取、span、答案标注 |
| AI 评测/数据工程 | 1 | shadow eval、对齐、回归指标 |
| 生产经理/质检负责人 | 1 | 状态流、返工、签发、排期 |

核心组织原则:

```text
专家不要直接"写题",
专家参与母题编译流水线的签字、返工、边界裁决。
```

## 9. Gate 与红线

### 9.1 必过 gate

| Gate | 要求 |
|---|---|
| G-SRC | 每个关键字段有 source_ref + source_sha256 + span_hash |
| G-AUTH | official/provider/self/LLM/student authority 明确 |
| G-SCORE | point_score + sub_q_total_score + cap_rule 同时存在 |
| G-EDGE | 正式包有 30-50 条人审边界答案 |
| G-ERR | misconception 必须映射 `ERROR_CODE_REGISTRY`,禁止 unknown_error active |
| G-SCOPE | 轻练/半写必须有 `task_scope`,范围外不得记 miss |
| G-UX | 用户能在 2 分钟内完成一次闭环 |
| G-RETENTION | 扩包前必须有 D1/D7 回访与复测证据 |
| G-RUNTIME | runtime 只读签发包,不扫 artifacts |
| G-COMPLIANCE | display_policy/training_policy/official_claim_allowed 全部明确 |

### 9.2 红线

- 不展示整页教材、标准全文、讲义页、机构解析页、PDF 截图,除非授权。
- 不把培训机构解析写成官方标准答案或官方采分点。
- 不把 LLM jury / AI label / 合成答案写入正式 learner truth。
- 不让讲义参数覆盖教材/规范参数。
- 不用 raw 第三方文本做可复现原文输出的训练或微调。
- 学生答案采集必须有告知、同意、最小化、去标识化与删除机制。
- 案例题变题不能用 generate-then-grade 自证正确。

## 10. 创始人此刻要拍的 5 个板

1. 承认 F16 是留存与体验样板,不是案例深母题旗舰。
2. 选择 F01 进度网络计划作为第一条深母题判分旗舰。
3. 把前 30 天资源投到 PDF rubric 抽取、per_question/v3.2 对齐、source registry 和边界答案,而不是扩题量。
4. 产品第一版用证据标签,不显示伪精确掌握度。
5. 组建"生产经理/质检负责人"角色,让专家流水线化工作,创始人只抓闸口与信仰。

## 11. 最终判断

鲁班智考手里的数字资产已经足够做出差异化,但不适合直接堆成题库。

最佳路线是:

```text
把现有资料登记为可信 source_refs / source registry allowlist,
把 shadow 采分点变成 signed scoring refs,
把专家隐性知识变成 case_family_structure,
把真实作答经既有 learning_evidence 链路沉淀为边界答案候选与误解分布,
让运行时只通过既有 runtime_supply / LubanContextPack 消费签发包。
```

顶尖体验不是"题很多",而是学生第一次感觉:

```text
它不是在判我对错,
它看穿了我为什么会丢分,
并且明天能验证我是不是真的会了。
```
