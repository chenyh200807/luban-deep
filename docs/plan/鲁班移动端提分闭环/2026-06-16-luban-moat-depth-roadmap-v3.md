# 深母题资产 · 护城河深度北极星 v3（收口版）

> Status: Proposed / **北极星,非落地实施规格**。经 3 位架构专家 + Codex 跨模型评审后**大幅收缩**:原草稿(施工级 7 层 + LLM 执行规格 + 登记账本)被评审一致判为"对一个‘现在不建’的东西过度设计,且脊梁(generate-then-grade)对案例题是同源循环"。本版只保留:**北极星 + 4 处必须更正的判断 + 1 件现在就做的事**。
> Date: 2026-06-16
> 基座: [schema v2](2026-06-16-luban-deep-archetype-asset-schema-v2.md)(两对象 + 单一权威,全保留)
> **整体 build gated on retention**:F16 5 天留存未证明前,除 §3 那一件,一层都不建。

## 0. 评审收口(诚实,不藏)

3 专家 + Codex 一致结论,逐字代码核实:

1. **generate-then-grade keystone 对案例题是同源循环,不是验证器。** 生成变体无 published artifact → 只能从 LLM 自己的标准答案抽采分点再判,"判满分"近乎恒真;且案例判分本身是 LLM judge(`batch_judge`=DeepSeek)→ LLM 验 LLM = circularity。`CaseGradingSkillKernel.grade()` 只判"已存在 question_row",无"反判新题合法性"能力。**keystone 只在 MCQ(确定性 answer_key)成立。**
2. **第 6 层元模式库 = 既有 RichLeaf/S0-S7 编译器换名**(`exam_patterns/common_mistakes/procedures/teaching_cards`)→ 该**并入 S0-S7,不新建第二套 compiled-context 权威**(AGENTS §5.7)。
3. **第 2 层该扩 `training_intent`(处方权威),不是 `NextBestAction`(view);复测 `revalidation_queue` 已现成。**
4. **`confidence` 撞名**(仓库已有 3 种语义,含 BLOCKING-drift 的 rich-leaf bundle 字段)→ 必须改名 `self_reported_confidence`,且是 **attempt-level event,不进 learning_evidence**。
5. **整份对"现在不建"过度设计**,会腐蚀 retention gate。

> **叙事更正(最重要)**：护城河深度不在"生成数量",在 **invariant 的不可压缩性**(v2 §7 G-INV 不变量锐度)。无限生成只挡得住"背题面"的人,挡不住"背 invariant"的人——F16 就 5 步骨架,背下来无限表皮即无限同质。**真护城河 = invariant 锐度 + 误解诊断(选错即懂) + 让学员当出题人(逆向命题),不是题量。**

## 1. 7 层北极星 + 每层诚实状态（留存证明后才逐层落,本表只定方向与"落地条件")

| 层 | 价值 | 落地状态(评审判) | 修正后的正确做法 |
|---|---|---|---|
| ① 生成语法 | 变体不可穷举 | **YELLOW** | keystone 限 MCQ(确定性反判真成立);案例变体走 v2 §5 G-INV/G-SRC/G-REF + **离线预生成池 + 人工抽检**(非实时,成本 5-6x);护城河叙事回到 invariant 锐度 |
| ② 自适应 policy | 因人定下一步 | **YELLOW** | 扩 `training_intent`(已登记处方权威)加 failure_mode/难度/表征三轴;复测复用 `revalidation_queue`;LLM 不当 policy |
| ③ 学员当出题人 | 看懂出题人最深 | **RED(无验证器)** | 现无"验学员所出题合法性"的代码;需新建,**推迟**;污染防护(preview/非official)已现成,加一个 evidence_source 标签 |
| ④ 信心校准 | 抓 confident-wrong | **GREEN(唯一净新增且当下可做)** | `self_reported_confidence`(改名防撞)× correctness 确定性矩阵;**attempt-level event,不进 learning_evidence** |
| ⑤ 脚手架阶梯 | 给最少够用提示 | **YELLOW** | 级别=确定性 policy,内容=LLM;leak-check 锚 artifact `required_terms`(规范化模糊,非裸 substring) |
| ⑥ 元模式库 | 跨科目复利 | **RED 独立 / YELLOW 并入** | **并入 S0-S7 当 S2 few-shot + S3/S5 gate**,不新建 schema;删"法考涵摄=criteria_match"(压测证伪) |
| ⑦ 认知难度 | 教那个认知障碍 | **RED(首版负价值)** | 无 empirical 数据前,把未验证认知原因讲给屡战屡败者=二次打击信心;**推迟**;但失分分布**埋点现在就开始攒** |

## 2. 全局纪律（落任一层前都适用）

- **所有新 confidence 字段必须带 owner 前缀**(`self_reported_confidence` / `cognitive_label_confidence`),禁裸 `confidence`(v2 §0.1 命名收权升为 v3 全局约束)。
- **元模式/教学原型并入 S0-S7,不新建 compiled-context 权威。** 跨科目复用按 v2 决议13 口径(复用 schema 形状,不是同一实例跨科目),不做"一建形状定义别科目深度"的硬映射。
- **生成变体边界**:`provenance=generated`,不入 published artifact,不出 official score,不升 LearnerState / canonical learner truth,直到走治理证据通道。
- 全部 build gated on retention;真建任一层前先 register-before-use + 过 `check_schema_registry.py`。

## 3. 现在唯一该做的一件事（priority-0,零代码权威）

在 **F16 5 天留存测试里手动加一句"你几分把握(1-5)"**,采集 `self_reported_confidence × correctness` + 每个 failure_mode 的失分分布。

- 它是 attempt-level 信号,**不进 learning_evidence、不碰掌握度**,零权威风险、零代码。
- 它一次性验三件事:(a) 第 4 层 calibration 是不是有效信号(confident-wrong 占比);(b) 第 7 层的 verifier 弹药(失分分布)从第一天开始攒;(c) 顺带就是留存测试本身。
- **这是评审一致认定"当下可执行、ROI 最高、不依赖那条断脊梁"的唯一一层。**

## 4. 不确定性 + 验证（留存证明后、真建前必做）

1. **[必做 spike] generate-then-grade 实测同源循环漏多少**:取 F16 让生成器造 20 个变体跑全套关,统计"①判满分但盲做失败/干扰项无效"比例。比例高=证实①无鉴别力,真闸是 ④;**billable run 前的排雷(eval-design)**。
2. **[成本] 实测一次"生成+反判"的真实 LLM 调用数与 token**(评审估 5-6x,非 2x);确认离线预生成池经济性。
3. **[权威] 扩 `training_intent` 三轴前**,grep 所有 `learning_training_intent.v2` 消费者确认 append 不破坏(append-only 应安全,需实测)。
4. **[数据] 第 7 层认知标签**永远先标 hypothesis,有 N 个真实失分样本后才驱动干预,绝不当事实讲给学员。

## 5. 一句话

**这 7 层的方向是对的护城河北极星,但评审证明:现在最该做的不是把它们设计得更精致,是去验证"深度资产到底能不能留住人"。** invariant 锐度(已在 v2)+ F16 薄切片已经够测这件事。**设计冻在本版,劲使到留存。**
