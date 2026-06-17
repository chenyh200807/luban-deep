# Claude Code「升级 gstack」会话整合：母题引擎与顶尖学习体验

> Status: Integration Memo / Proposed
> Date: 2026-06-16
> Scope: 整合 Claude Code 本地会话 `fc105929-6dd6-4832-ba5e-72aa9a08e548.jsonl`、两份用户提供的母题引擎思考稿、现有移动端提分闭环 PRD、深母题 schema、护城河 roadmap、F16 留存弹药包与两个 subagent 只读审查结论。
> Non-authority: 本文不替代 `2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md`、`2026-06-16-luban-deep-archetype-asset-schema-v2.md`、`2026-06-16-luban-moat-depth-roadmap-v3.md`。本文只做整合与执行收口。

## 0. 结论先行

Claude Code 里「请升级我的 gstack」这条会话确实能读取到。表层结果是 gstack 从 `v1.57.10.0` 升到 `v1.58.1.0`；但对鲁班真正有价值的不是升级动作本身，而是这条会话后半段沉淀出的产品判断：

**母题引擎不能先表现为“我有很深、很全、很复杂的题库”。它的顶尖学习体验应先表现为：忙碌复考成人每天 2 分钟完成一次正向闭环，知道自己补了哪个盲点、为什么丢分、对应教材哪里、明天复测什么，并愿意第二天回来。**

因此当前北极星不是“把 30-40 个母题一次性做完”，也不是“把案例题 AI 批改当新用户头牌”，而是：

```text
今日任务
-> 知识点 / 母题 MCQ 轻练
-> 选错即诊断：misconception + error_code + 教材章节 / 采分点
-> learning_evidence / attempt-level event
-> NextBestAction / revalidation_queue
-> 次日复测
-> 养成后解锁案例题渐进作答 + AI 采分点批改
```

## 1. 会话中确认的事实

### 1.1 gstack 升级事实

Claude Code 会话中可见：

- 用户请求：`请升级我的gstack`。
- 执行结果：gstack `v1.57.10.0 -> v1.58.1.0`。
- 安装形态：global-git，路径为 `~/.claude/skills/gstack`。
- 执行链：`git fetch + reset + setup + v1.58.0.0 migration`，并清理 update cache / snooze marker。
- 更新要点：hermetic eval、Conductor 纯文本决策、`gstack-detach`、`/diagram`、hermetic sentinel、旧 harness 掩盖 bug 修复。

这部分只说明工具链已升级。对母题引擎的直接启发是：后续用 gstack / subagent / Codex 做评审时，要吸收其严谨流程，但不能让 gstack onboarding、telemetry、CLAUDE.md 注入或自动 commit 越过 DeepTutor 的 single authority 与 branch discipline。

### 1.2 会话真正延展出的产品判断

后续会话从升级转向产品诊断：

- 内测用户不是完全没需求，而是把产品当 chatbot 用，说明价值入口没有把差异化亮出来。
- “案例题阅卷 / 挑错”对新用户太重、太负向、太像考试压力；复考成人更需要低门槛、短时、可见进步。
- North Star 应改成真实留存行为：D1/D7 是否回来，而不是闭环技术是否跑通。
- 案例题 AI 采分点批改仍是深度护城河，但应降为养成习惯后的第二阶段深水区。
- 母题资产应先服务留存主链，成为“低门槛入口”和“深度诊断能力”的桥，而不是独立炫技资产。

## 2. 对“母题引擎”的重新定义

用户提供的两份母题引擎思考稿与 Claude 会话一致：母题不是题库，也不是一道模板题，而是围绕一个或多个考点，把教材、真题、讲义、规范、评分规则、常见错误、变题规则、诊断逻辑、训练路径编译成一个 LLM 可调用的数据工件。

本文建议统一定义为：

**Luban Case-Family Engine：母题编译与诊断引擎。**

它回答五个问题：

| 问题 | 引擎职责 |
| --- | --- |
| 考什么 | 识别知识点、采分点、能力点、交叉点 |
| 怎么变 | 在不改变考查本质的前提下换表皮、换场景、换问法 |
| 怎么判 | 引用 published grading artifact，不复制判分规则 |
| 怎么诊断 | 把选错 / 答错映射到 misconception、error_code、教材章节 |
| 下一步怎么做 | 产出复练/复测/讲解/下一题候选,由既有 `training_intent` / `NextBestAction` / `revalidation_queue` 消费 |

关键边界：

**LLM 是候选组织器与执行器，不是权威来源。** 母题引擎提供结构化上下文、约束与候选；判分、错因、知识、学情、推荐与复测分别回到既有 authority。

## 3. 现在应采用的架构形状

### 3.1 两对象，不做 God Object

`case_family` 必须拆为两个共注册对象：

| 对象 | 角色 | 生命周期门 |
| --- | --- | --- |
| `case_family_production` | 指针层，只引用 source / taxonomy / grading artifact / question binding，不拥有 rule/content | artifact publish / shadow replay |
| `case_family_structure` | 原创教学层，承载 L1-L6 不变量、意图、表征、变体、误解、复测鉴别候选 | G-INV / G-COV |

原因：判分 readiness 和教学结构 completeness 是两套生命周期，不能用一个 `status` 扛。强行合并会导致每个消费者加 filter/mapping 层，最终变成第二套 authority。

### 3.2 L1-L6 是教学与诊断，不是判分真相

当前可作为母题引擎核心结构的层次：

- L1 `invariant`：不变量、经典陷阱、真懂 vs 背过鉴别点。
- L2 `examiner_intent`：出题人意图、规范原文如何变成题、为什么给分。
- L3 `representations`：流程图、反例、对比表、口诀、场景图等多重表征。
- L4 `surface_generator`：表皮生成器、难度旋钮、变体蓝图、干扰项诊断链。
- L5 `misconceptions`：局部误解模型，映射 canonical `ERROR_CODE_REGISTRY`。
- L6 `retest_discriminator_candidate`：复测鉴别候选、证据需求、跨表皮迁移提示。

红线：

- L1-L6 只做 teaching / diagnosis context。
- 不能 official scoring。
- 不能直接写 canonical learner truth。
- 不能私造 error taxonomy。
- 不能复制 rubric rule。

### 3.3 四个错因名词必须分清

| 名称 | 作用 | authority |
| --- | --- | --- |
| `error_code` | 诊断轴：为什么这类能力失分 | `ERROR_CODE_REGISTRY` |
| `mistake_type` | 判分形态轴：这点怎么没拿到分 | `mistake_code_registry.yaml` + mirror |
| `mistake_tag` | 判分侧投影：`scoring_point_id + error_code` | production / artifact 投影 |
| `misconception` | 诊断侧局部心智模型与纠正 | per-case_family 局部，不建全局 registry |

这四者不合并、不竞争。`misconception.maps_error_code` 和 `mistake_tag.error_code` 锚同一个 error_code，但消费出口不同。

## 4. 顶尖学习体验该长什么样

“wow” 不应来自页面说自己很智能，而应来自用户在 90 秒内感到：

> 它不是给我刷题；它看出了我为什么丢分，还告诉我今天补什么，明天怎么验证我真的会了。

### 4.1 首次 2 分钟体验

首屏不应是大聊天框或完整章节地图，而是一个可完成任务：

```text
今日最值钱的 1 件事
F16 防水：2 分钟盲点检查
预计暴露：工序顺序 / 搭接方向 / 迎水面
```

答题后立刻给：

- 对错。
- 盲点名：例如“把背水面当成防水主位置”。
- `error_code`：例如 E07 概念混淆。
- 教材定位 / 采分点定位。
- 一句纠正。
- 明天复测承诺。
- 1-5 分自信度：`self_reported_confidence`，只作为 attempt-level event。

### 4.2 第二天体验

次日回来不是重新刷一组题，而是复测昨天暴露的盲点：

```text
昨天你在“迎水面”上选错。
今天换一个场景验证：屋面 vs 地下室外墙，防水层应在哪一侧？
```

这才会让用户感觉系统记得他、懂他、在带他变强。

### 4.3 深度层体验

当用户形成习惯后，再解锁：

- 案例题渐进作答。
- 半写 / 补采分点 / 排序 / 反向辨析。
- AI 采分点批改。
- 同一 `case_family` 下跨表皮复测。
- 学员当出题人：但这层目前没有验证器，暂不建。

## 5. 当前不能做的事

### 5.1 不能马上做 30-40 个母题

F16 没证明 D1/D7 留存前，不能扩第 2 个包、不能建自动化编译生产线、不能扩团队。否则会回到“做了一堆没人每天用的深资产”。

### 5.2 不能把 F16 误写成案例旗舰母题

F16 防水适合作为 MCQ / 留存薄切片，因为场景直观、错因可解释。但真题实证上防水不是案例题旗舰。案例深母题首选更可能是：

- 大体积混凝土 / 钢筋 / 结构。
- 安全 / 危大工程。
- 进度网络计划。
- 质量 / 验收。

F16 的定位应是“验证留存闭环”，不是证明“案例题护城河已成立”。

### 5.3 不能把 fact-gate 题包直接发用户

当前 F16 fact-gated draft 里 11 道题全部为 `⚠️`，可直接发真实用户的题数是 0。它们已有本地教材 grep 账，但缺 DeepSeek / Qwen / Opus 或人工共识。

发用户前至少要满足：

- 教材 / 来源命中。
- 答案经异质模型或人工共识。
- 每个错选项有 misconception + error_code + 教材定位 + correction。
- 不使用 `unknown_error` 等 fallback。

### 5.4 不能用 generate-then-grade 验案例题

对案例题而言，生成变体没有 published artifact，系统只能从 LLM 自己答案抽采分点再让 LLM 判，属于同源循环。这个 keystone 只在 MCQ answer_key 确定场景成立。

深题需要第二验证车道：

- 标为“推理题，非逐字题”。
- 与教材不矛盾。
- 至少 2 个异质模型独立同意推理正确。
- 干扰项必须是真误解，不是稻草人。
- 盲做能区分“背清单”和“懂因果”。

## 6. 必须前置的 gate

| Gate | 要求 |
| --- | --- |
| Register-before-use | `case_family_production`、`case_family_structure`、enum、局部 ID 命名空间先登记，再允许代码消费 |
| G-INV | 3 个以上 surface 变体能抽出同一不变量 |
| G-SRC | source transform / provenance 能溯源教材、真题、规范或讲义 |
| G-MAP | distractor -> misconception -> error_code 完整，且 error_code series 只能是 E/M |
| G-COV | failure_mode 必须被变体覆盖，未覆盖不能 active |
| G-AUTH | grading artifact 必须 published，draft 不判分 |
| G-REF | 两对象引用完整，structure 不测 production 没绑定的采分点 |
| Task Scope Evidence | 轻练 / 半写写 evidence 前必须声明 covered_scoring_point_ids；范围外不得写 miss |
| Mistake Tag Schema | schema、payload builder、readback、contract tests 不明确前，只展示，不写长期 truth |
| Retention Gate | 技术闭环不等于 GO；必须看 D1/D7 回访与复测行为 |

## 7. 专家团队应怎样工作

不是让专家“写题”，而是让专家参与母题编译流水线。

| 角色 | 主要产出 |
| --- | --- |
| 一建建筑实务教研总编 | 高频母题清单、章节/知识点/采分点层级、教学路径 |
| 阅卷 / 评分规则专家 | 采分点、可替代表达、弱表达、部分给分、高风险答案 |
| 施工现场专家 | 场景真实性、施工流程、工程干扰项、变题边界 |
| 规范 / 标准专家 | 规范依据、新旧版本差异、教材与规范冲突处理 |
| 母题产品架构师 | case_family schema、学习闭环、前端训练形态、专家后台 |
| 教育测量顾问 | Q-matrix、LearnerState 指标解释、题目难度、可靠性评估 |
| 学习科学 / KT 顾问 | 复测节奏、遗忘风险、掌握衰减、下一题策略 |
| LLM / RAG 架构师 | 母题检索、上下文包、工具调用、幻觉防线 |
| 数据标注负责人 | 标注规范、人审边界样本、审核流程、一致性抽检 |
| AI 评测负责人 | 母题识别、采分点命中、错因诊断、变题有效性评测 |
| 小程序学习体验设计 | 手机轻练、半写、复测、错因页面、低摩擦动线 |
| 版权 / 合规顾问 | 教材、真题、讲义、规范和学生答案使用边界 |

最小 MVP 团队不需要 12 类人全职，但至少要有：

- 母题产品架构负责人。
- 一建教研专家。
- 评分 / 批改专家。
- LLM / RAG 工程师。
- 数据标注负责人。
- AI 评测负责人。
- UI/UX 学习体验设计。

## 8. P0 建议路线

### P0-1：先把 F16 跑成 5 天留存实验

目标不是证明 F16 是最强母题，而是验证忙碌成人是否会回来。

每天只做：

- 2-3 道 MCQ。
- 选错即诊断。
- 1 句教材 / 采分点定位。
- 1 个明天复测开环。
- 1 个自信度 1-5。

核心指标：

- D1 return。
- D7 return。
- 次日复测完成。
- 错因诊断被看完 / 被点击。
- 用户是否能复述“今天补了什么”。
- `self_reported_confidence × correctness` 的 confident-wrong 占比。

### P0-2：把 11 道 fact-gated 题做共识裁决

现状是 `0 ✅ / 11 ⚠️`。下一步不是直接发，而是让 DeepSeek / Qwen / Opus 独立投票：

- 只基于给定原文判断答案。
- 原文不足就输出“依据不足”。
- 至少 2 个异质模型同意，且教材 grep 命中，才可升 `✅`。

### P0-3：补 2-3 道深推理题，但走第二验证车道

目标是测试“看懂因果”：

- 顺水搭接为什么不是长度够就行。
- 节点为什么必须先行。
- 屋面与地下室迎水面如何鉴别。

这些题不能用逐字 fact-gate 淘汰，因为它们是教材一致推理。必须单独标注“推理题”，并用异质模型共识 + 盲做鉴别来验。

### P0-4：只登记 F16 薄切片所需 schema

不登记全套天花板，只登记 Phase 0 必需字段：

- `case_family_production` 最小字段。
- `case_family_structure` 最小字段。
- misconception / failure_mode 局部 ID。
- error_code mapping。
- task_scope / covered_scoring_point_ids / evidence_weight。

### P0-5：真实作答进入既有 evidence 链路与编译回流

用户真实答题后，产出：

- 错选项分布。
- confident-wrong 分布。
- misconception 命中。
- 复测是否迁移成功。
- 哪些题是稻草人干扰项。
- 哪些诊断用户觉得“说到点上”。

这些信号先经既有 `learner_memory_events.learning_evidence` / review queue / compiler feedback 进入候选回流,不能新建 shadow learner memory 或第二套编译 truth。

## 9. 剩余不确定性

1. 复考成人到底想要“看穿本质”，还是只要短、准、能得分。这不能靠讨论解决，只能靠 F16 留存实验回答。
2. 深推理题是否提高留存，还是增加负担。需要与浅 fact-gated 题分车道比较。
3. `case_family` schema 是否能跨非建筑科目零结构改动。当前只是设计假设，Phase 3 才做跨科目冒烟。
4. F16 是否适合作为长期案例深母题。当前只适合作留存 MCQ 薄切片。
5. 没有人类专家时，多模型共识能否替代初审。它可以降低 hallucination，但不能替代最终 published scoring artifact。

## 10. 一句话收口

母题引擎的“wow”不是让学员看到很多题，而是让他第一次觉得：

**这套系统知道我为什么丢分，知道我明天该怎么补，而且能证明我真的变强了。**

所以现在最该做的不是继续把母题标准写厚，而是用 F16 做一个薄但真的 5 天留存闭环，把 `invariant + misconception + error_code + 教材定位 + 次日复测 + self_reported_confidence` 跑出真实行为数据。
