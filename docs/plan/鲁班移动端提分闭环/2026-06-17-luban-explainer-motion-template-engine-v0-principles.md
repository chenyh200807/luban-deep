# 鲁班解释型动效模板引擎 v0 原则

- **日期**: 2026-06-17
- **状态**: `Proposed`（原则锁定稿；不授权量产）
- **从属**: 挂在「鲁班移动端提分闭环」主线下，**不新增平行计划体系**。当前产品 authority 仍以 `2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md`（PRD v1.3）为准；本文只补"解释型动效/图解卡"这一表现层的红线与路线。
- **现有资产**: `artifacts/luban_case_family_assets/diagram_microlesson/`（F16 起鼓割补体验样板、N01 网络计划硬能力样板、`SCHEMA.md`、两个窄 renderer）。

## 1. 结论

鲁班要做的是**考试解释引擎**，不是动画课平台。

动效/图解只有一个存在理由：**让忙碌的复考成人更快知道"错在哪、为什么这么写才得分、下一题怎么验证"**。凡是不服务这件事的视觉，都是成本不是资产。F16 证明"体验闭环"，N01 证明"数据驱动自动图解"的硬能力——两张样板就够立判断，不需要先铺 14 个模板。

## 2. 五条红线

1. **动效必须服务采分点 / 错因 / 复测**——不为"好看"或"有动效"而做。
2. **生成式视频不进入知识核心表达层**——AI 文生视频/图最多做氛围，绝不决定构造/工序/答案的正确性。
3. **renderer 不做知识判断，只做确定性渲染**——关键路径、时差、采分点等结论来自 JSON 或独立确定性计算器，前端只渲染。
4. **每个关键步骤必须绑定 evidence / source_ref / authority boundary**——哪怕是 candidate，也要诚实标注，不冒充官方。
5. **没有用户验证，不量产 20-30 条**——先过 3-5 人学员验证，再谈规模。

## 3. 为什么（每条红线背后的原因）

1. **防"漂亮但不提分"**：动画课市场已经很卷，鲁班的差异化是"看穿你为什么丢分"，不是动画质感。视觉一旦脱离采分/错因/复测，就退化成普通网课。
2. **防 AI 视频幻觉**：施工工序、构造层次、网络计划逻辑都是会被考的硬事实，生成式模型会"画得像但说错"。让生成视频进入知识表达层＝把幻觉印到学员脑子里。
3. **防 renderer 变第二权威**：一旦前端开始"自己算关键路径/自己判采分"，它就成了第二套评分/知识 authority，和母题包/判分工件打架。renderer 必须是 thin wrapper。
4. **防无来源教学**：教学内容必须可追溯到教材/真题/规范/教研依据；无 evidence 的"老师讲"就是编。candidate 也要标 candidate，不许偷偷升格成官方。
5. **防 demo polish 变沉没成本**：一张 demo 做到 90 分很爽，但 30 张未验证的 demo＝30 份可能要推翻的沉没成本。先验证形态再量产，是省钱不是拖延。

## 4. v0 只支持的模板类型（先登记 3-5 个候选，不做 14 个）

| template_type | 含义 | 现状 |
|---|---|---|
| `process_step_reveal` | 施工流程/工序逐步揭示（F16 起鼓割补） | **rendered proof（体验样板）** |
| `layer_section_reveal` | 剖面/构造节点分层（屋面、防水、墙身等） | 候选（F16 SVG 已含剖面雏形，暂复用同 renderer） |
| `network_plan_keypath` | 网络计划关键线路（数据→自动成图→高亮） | **rendered proof（硬能力样板 N01）** |
| `answer_point_diagnosis_draft` | 采分点命中/漏点逐点判读（D01） | **schema draft（无 renderer，仅验证字段通用性）** |
| `decision_tree_judgment` | 索赔/危大工程/验收等判断树 | 候选（未动） |

约束：每个 `template_type` 对应一个**窄确定性 renderer**，在 `diagram_microlesson/SCHEMA.md` 先登记字段再消费；模板之间并列，不互相耦合，不抽通用大框架。三类已成形样板共用同一条 schema spine（`schema_version/card_id/template_type/title/student_goal/authority/scoring_points/common_errors|error_reveals/practice/rendering_contract.student_safe_fields`），body 互斥（`steps[]` / `question_data` / `diagnosis[]`），由 `validate_schema_drafts.py` 守门。

### renderer 分派原则

- `template_type` **只用于选择渲染模板**，不改变任何 authority。
- renderer **不改变 authority**：candidate 永远是 candidate，signed 才是 signed。
- renderer **不重新判分**：只展示已编译 verdict（`diagnosis[].status` / `expected.critical_path` 都是数据，不是前端算出来的）。
- renderer **不生产新知识**：不补采分点、不改分值、不推断官方答案。

### compute_cpm 定位

- `compute_cpm()` 是 **build-time 自洽校验器/派生器**：校验 N01 `expected`（关键线路/时差）与确定性 CPM 一致，并派生 ES/EF 供展示。
- 它**当前不是 official scoring authority**；**未来可抽成独立网络计划编译器**，仍不得让前端 renderer 现场判断。

## 5. 三阶段路线

**Phase 0（当前）**
- F16 体验样板 + N01 硬能力样板（rendered proof）+ D01 判分解释 schema 草案都已就绪。
- **不量产**。只用它们证明"体验闭环""数据驱动图解""判分解释字段通用性"各自成立。

**量产闸（三条，逐类独立 gate，未过不铺）**
1. **体验类图解卡**：F16 未过 3-5 人学员验证前，不铺更多 `process_step_reveal` / `layer_section_reveal`。
2. **网络计划类**：N01 未完成**真题 `source_ref` 绑定**（当前是 `candidate_teaching_example`）前，不铺更多 `network_plan_keypath`。
3. **判分解释类**：D01 未拿到**已签发 `source_ref` + 真实学生答卷样本 + 人审/gold 校准**前，不做 `answer_point_diagnosis` 生产 renderer、不做生产判分解释。

**Phase 1（验证通过后）**
- 先过 3-5 人学员验证（见 `F16_qigu_product_validation_plan.md`，网络计划同款流程）。
- 通过后再做第二/第三个 template_type，并建**最小模板 registry**（register-before-use）。

**Phase 2（留存/学习效果通过后）**
- 再考虑 Remotion 视频导出、TTS 旁白、内容审核后台等重投入。
- 任何重投入都 gated on 留存与学习效果证据，不提前建。

## 6. 不做什么

- 不做动画课平台。
- 不做纯 AI 视频教学。
- 不做 Unity / Unreal 主链路。
- 不做大规模 BIM。
- 不在第一张卡之后就抽泛框架。
- 不跳过真实学员验证直接量产。

## 7. 和现有资产的关系

- **F16** = 体验样板（流程/剖面类，证明错因驱动的图解微课闭环好不好用）。
- **N01** = 硬能力样板（证明"题目数据→自动画图→高亮关键线路"的引擎能力）。
- **D01** = 判分解释 schema 草案（证明 `answer_point_diagnosis` 能复用 spine：命中/部分/漏点逐点判读引用 `scoring_points`；**无 renderer、candidate、不生产判分**）。
- **母题包 / 采分点 / 错因(`ERROR_CODE_REGISTRY`) / evidence / 判分工件** = 知识 authority（唯一真相）。
- **renderer** = thin wrapper（只渲染上游事实，不产生知识）。
- **动效模板** = fat skill 的**表现层消费者**，不是新知识库、不是第二套评分/学情 authority。

> 一句话：母题包是"肉"，renderer 是"薄壳"，动效模板是壳的样式。壳可以多种样式，肉只有一份。
