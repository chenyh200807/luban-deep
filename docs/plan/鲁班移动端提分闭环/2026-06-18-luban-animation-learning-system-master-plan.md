# 鲁班动画学习体系 Master Plan

- 日期: 2026-06-18
- 状态: `Proposed`
- 主线: 鲁班移动端提分闭环
- 决策对象: motion learning packs 的专家裁决清单、生产形态、优先级、验收 gate

> **定位**: 本文是 v1.3 PRD(`2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md`,scoring-loop)下的动画/视频【供给侧】生产计划,不构成新产品主线。

## 0. 结论

鲁班的学习视频体系不应按"知识点视频课"建设,也不应按"重动画作品集"推进。唯一正确单位是:

> 1 个高频可命题考点 / 深母题 = 1 个 motion learning pack

经考试频次、学习体验、动画生产、产品留存四类专家复审,本文修正为:

> **L40 locked + L20 candidate pool**

含义:

- **P0 20 locked**: 头部高频案例考点,方向基本稳定。
- **P1 20 active**: 中频但高教学价值考点,允许做 source/storyboard,生产仍 gated。
- **P2 20 candidate pool**: 候选池,不是生产承诺;多数是 C/D 低成本、合并项、条件拆分项或 evidence-pending 项。

上一版把若干示例当成硬性入选项,这是错误口径。示例只能启发生产形态,不能替代专家裁决。所有入选理由必须回到: 高频/常错/采分句/可复测/source_ref。

## 1. 生产形态

L40/L20 都不是 60 个重图解动画。每个学习单元按最适合的方式生产:

| 类型 | 生产形态 | 适用考点 | 代表 |
|---|---|---|---|
| A | `diagram_whiteboard` 图解/白板动画 | 工序、构造、空间、正误对比、判断分支 | J01、C01、B02、S05 |
| B | `calculation_whiteboard` 计算白板 | 网络计划、流水、计价、索赔、挣值 | N01、C02、N03、E05 |
| C | `kinetic_text_ppt` PPT 纯文字运镜/文字动效 | 责任边界、流程顺序、措施清单、相似概念辨析 | K06、R01、X03 |
| D | `practice_card_checklist` 轻互动 MCQ/记忆卡/checklist | 数值记忆、复验清单、低图形化但可验证点 | A02、R02/R03 |

管理口径:

| 层级 | 数量 | 目的 | 当前拍板 |
|---|---:|---|---|
| M0 proof set | 4 个 | 收口现有样板和质量线 | J01/N01/C01/F16 |
| M1 starter system | 12 个 | 证明 A/B/C/D 四类生产形态能服务学习闭环 | 先做样板,不等于批量授权 |
| P0 locked | 20 个 | 覆盖案例头部高频考点 | 稳定清单 |
| P1 active | 20 个 | 补中游高价值考点和关键模板缺口 | 生产 gated |
| P2 candidate pool | 20 个 | 候选池/合并项/条件拆分项/evidence-pending | 不构成生产承诺 |

## 2. 单一 authority

本文只定义动画/视频学习体系的生产路线,不替代以下 authority:

- 产品主线 authority: `2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md`
- 母题结构 authority: `2026-06-16-luban-deep-archetype-asset-schema-v2.md`
- 动效模板原则 authority: `2026-06-17-luban-explainer-motion-template-engine-v0-principles.md`
- 考点优先级输入: `docs/原始数据/数据盘点/2026-06-17-图解微课考点地图.md`
- 频次方向性输入: `docs/原始数据/数据盘点/2026-06-16-真题考点实证频次.md`
- 渲染 schema: `artifacts/luban_case_family_assets/diagram_microlesson/SCHEMA.md`
- taxonomy 对齐注册表: `2026-06-19-luban-animation-pack-taxonomy-alignment-registry.md`

renderer 是表现层 thin wrapper。它只能渲染上游母题包、采分点、错因、canonical taxonomy refs、source_ref 和练习反馈,不得生成新知识、不得重判分、不得写 learner truth。

### 2.1 Pack ID 与 canonical taxonomy 分工

本文的 `J01/N01/C01/F16` 等编号只表示 motion learning pack 的稳定资产 ID,不表示考试官方编号、教材章节编号或 canonical taxonomy code。

正确分工:

| 概念 | 作用 | 例子 |
|---|---|---|
| `pack_id` | 动画包/练习包资产 ID,用于文件、版本、生产追踪 | `J01`, `N01`, `F16` |
| `canonical_taxonomy_refs[]` | 知识权威锚点,用于盲点归因、题库召回、复测和覆盖率 | `1A431030-E01`, `1A433000-B041` |
| `priority_slot` | 生产优先级,不参与知识 authority | `P0-01`, `P1-29` |
| `student_title` | 学员可见中文标题,不得暴露 raw code | `危大工程要不要专家论证` |

硬规则:

- P0/P1 pack 进入 source/storyboard 前,必须在 taxonomy alignment registry 中有 `canonical_taxonomy_refs[]`。
- `coarse_review` 只能做证据补强,不得进入默认学习入口。
- 学员端不得展示 `1A...`、`P0-01`、`pack_id` 等内部编号。
- `canonical_taxonomy_refs[]` 不等于判分点;判分仍由 published grading artifact / `CaseGradingSkillKernel` 承担。

## 3. 选入标准

每个 pack 入选 locked/active 必须满足至少 4 条:

1. 高频、常错、高失分、或用户痛点之一成立。
2. 有明确错因,不是泛泛讲知识点。
3. 能提炼考试可写采分句。
4. 能绑定一道母题、小练或 D1/D7 复测题。
5. 能明确生产形态 A/B/C/D。
6. 有 source_ref、讲义、真题 stem、规范或教研证据可追溯。
7. 有 canonical taxonomy 候选绑定,且状态不是空白。

淘汰或降级规则:

- 只是教材名词解释,没有错因和采分句,不进 locked。
- 只能靠老师长篇口播,无法做题后验证,不进 locked。
- 缺 source_ref 时只能进入 candidate pool。
- 缺 canonical_taxonomy_refs 时不能进入 P0/P1 source/storyboard。
- taxonomy 对齐状态为 `coarse_review` 的 pack 不能 production,只能先做 leaf/source review。
- 不因"纯文字"淘汰;但纯文字高价值考点通常进入 C/D,不占重动画产能。
- 一个考点若只是另一个考点的子清单或场景变体,默认合并,不独立占 locked slot。

## 4. 专家组裁决

### 4.1 原举例项裁决

| 项 | 裁决 | 生产形态 | 理由 |
|---|---|---|---|
| R02 建筑构件耐火等级 | 降级/合并 | D 主,C 辅 | 更像数值记忆/MCQ,不应做 M1 样板;并入 R02/R03 防火基础数值判断 |
| X04 绿色施工 | 合并 | C/D | 与文明/环保措施同一错因和采分句结构,并入 X03 |
| X05 季节性施工措施 | candidate / evidence-pending | D | 可做 checklist 变体,但当前证据不足以独立锁定 |
| F06 防水材料性能与复验 | 合并/降级 | D | 并入 A02 材料进场复验与见证取样,防水只是首个场景 |
| E05 挣值法/偏差分析 | 保留上调 | B | 公式型、可计算、可复测,适合计算白板 |
| K02 不可抗力 | 合并 | C/D | 并入 K06 合同责任事件归属矩阵 |
| K04 合同价款调整 | 合并/条件拆分 | B/C | 默认并入 E04/K05;若 source_ref 证明独立高频再拆 |
| K06 发包/承包责任归属 | 保留 | C/D | 可做事件 -> 责任方 -> 工期/费用/风险三轴矩阵,吸收 K02 |
| R05 消防验收流程 | 合并/条件拆分 | C/D | 默认并入 R01 现场消防管理;若 source_ref 证明独立高频再拆 |

### 4.2 专家共识

1. P0 20 个大方向稳定,但 P0 也不是生产承诺;M1 验证前只允许做 source/storyboard 草稿。
2. P1 不能按章节补完整,要优先强图解、强计算、强复测、强错因。
3. P2 是候选池,不是排产表;C/D 类只锁生产标准和少量样板。
4. 禁止再把示例来源写成入选理由。
5. R02 不作为 M1 第 12 个样板;M1 的 C 类样板改为 K06 责任事件归属矩阵。

## 5. 模板底座

v0 按"学习表达形态"管理。A/B/C/D 是上层生产类型,template_type 是具体 renderer 或脚本形态。

| 类型 | template_type | 用途 | 当前样板/缺口 | 优先级 |
|---|---|---|---|---|
| A | `decision_branch_reveal` | 判断/分支: 危大、验收、索赔、事故等级 | J01 已有原型 | P0 |
| A | `contrast_pair_reveal` | 对比/正误: 施工缝、质量通病、连接选用 | C01 已有原型 | P0 |
| A | `process_step_reveal` | 时序/工序: 防水、模板拆除、验收程序 | F16 已有 renderer | P0 |
| A | `section_space_reveal` | 构造/空间: 基坑、临电、幕墙、平面布置 | 缺 renderer/spec | P0 blocker |
| B | `network_plan_keypath` | 网络计划关键线路/时差 | N01 已有 renderer + CPM 校验思路 | P0 |
| B | `calculation_whiteboard` | 计价、流水、索赔、挣值等公式/步骤题 | 缺统一白板脚本 | P0 |
| C | `kinetic_text_ppt` | 条文、责任、流程、措施、数值记忆的文字动效 | 缺脚本规范 | P1 |
| D | `practice_card_checklist` | 记忆卡、复验清单、流程 checklist、MCQ 轻练 | 可先用结构化卡片 | P1 |
| draft | `answer_point_diagnosis_draft` | 采分点命中/漏点解释 | D01 已登记为草案,不量产 | 暂缓 |

必须补的标准:

1. `motion_pack_manifest`: 明确 pack、sub-pack、checklist、practice block 的区别。
2. `kinetic_text_ppt`: 5-8 beat、每屏一个判断、文字入场顺序=推理顺序、最后留采分句/责任边界。
3. `calculation_whiteboard`: 公式来源、单位、正负方向、步骤检查、结果解释、错因回跳。
4. `section_space_reveal`: 剖面/平面/构造节点 mobile-first 标准。
5. Template registry 命名收敛: `decision_branch_reveal` / `decision_tree_judgment` / schema draft 不得继续漂移。

`D01` 已被既有动效原则文件用作 `answer_point_diagnosis_draft`。本文不再使用 `D01` 表示装饰装修考点,装饰类统一使用 `D11-D17`。

## 6. M0 proof set

| Pack | 考点 | 类型 | 模板 | 当前角色 | M0 动作 |
|---|---|---|---|---|---|
| J01 | 危大工程是否需专家论证 | A | `decision_branch_reveal` | 高频第一细考点样板 | 收成正式 storyboard + authority 边界 |
| N01 | 网络计划关键线路/总工期/总时差 | B | `network_plan_keypath` | video-first 标杆 | 绑定真题/source_ref 路线,保留 candidate 边界 |
| C01 | 混凝土施工缝留置与处理 | A | `contrast_pair_reveal` | 混凝土采分小问样板 | 收成错法-正法-采分句结构 |
| F16 | 屋面防水起鼓割补 | A | `process_step_reveal` | 留存体验样板 | 保留为体验入口,不升案例旗舰 |

M0 pass criteria:

- 每个 pack 有 teaching spine: wrong idea / visual correction / exam phrase / warm correction / authority。
- 每个 pack 有 5-8 beat storyboard。
- 每个 pack 有一条学生可见采分句。
- 每个 pack 有一个小练或复测点。
- 每个 pack 的 candidate / signed / official boundary 写清楚。

## 7. M1 starter system: 第一批 12 个

M1 不是 P0 前 12 名机械截取,而是"证明体系能跑起来"的 starter set。它必须覆盖 A/B/C/D 四类生产形态、现有样板、构造空间缺口、计算白板缺口和文字运镜缺口。

| 顺序 | Pack | 考点 | 类型 | 模板 | 选择理由 |
|---:|---|---|---|---|---|
| 1 | J01 | 危大工程范围 + 专项方案 + 专家论证 | A | `decision_branch_reveal` | stem 命中最高,安全/危大头部 |
| 2 | N01 | 双代号网络计划关键线路/时差 | B | `network_plan_keypath` | 纯案例能力,证明硬引擎 |
| 3 | C01 | 施工缝留置与处理 | A | `contrast_pair_reveal` | 混凝土头部采分表达 |
| 4 | F16 | 屋面防水起鼓割补 | A | `process_step_reveal` | 留存体验入口,不当案例旗舰 |
| 5 | B02 | 基坑支护选型与降水/监测 | A | `section_space_reveal` | 补最缺的构造/空间 renderer |
| 6 | S01 | 脚手架/高大模板支架验收 | A | `decision_branch_reveal` | 安全高频,复用判断模板 |
| 7 | S02 | 起重吊装安全 | A | `decision_branch_reveal` + `process_step_reveal` | 安全高频,适合流程化纠错 |
| 8 | Q01 | 混凝土养护与裂缝防治 | A | `contrast_pair_reveal` | 混凝土头部,错因清晰 |
| 9 | A01 | 检验批/分部分项验收程序 | A/C | `process_step_reveal` | 质量验收头部;不吞隐蔽/见证 |
| 10 | K01 | 索赔成立与工期/费用计算 | B/C | `calculation_whiteboard` | 合同索赔代表题型 |
| 11 | C02 | 进度款/计量计价 | B | `calculation_whiteboard` | 成本计价代表题型 |
| 12 | K06 | 合同责任事件归属矩阵 | C/D | `kinetic_text_ppt` + `practice_card_checklist` | C 类样板;事件 -> 责任方 -> 工期/费用/风险 |

少于 8 个只像 demo,无法证明体系。超过 12 个会在验证前制造沉没成本。R02 不放入 M1;R02 只能作为 source-gated D 类记忆/MCQ 候选。

## 8. P0 locked: 20 个

P0 20 个是第一版学习体系的头部地图,但 M1 验证前不能启动批量生产。M2 只能先做 source_ref 盘点和 storyboard 草稿。

| P0 序号 | Pack ID | 考点 | 类型 | 主模板 | 阶段 | 选择理由 |
|---:|---|---|---|---|---|---|
| 1 | J01 | 危大工程范围 + 专项方案 + 专家论证 | A | `decision_branch_reveal` | M1 | stem 命中最高,11 年全覆盖方向 |
| 2 | S01 | 脚手架/高大模板支架验收 | A | `decision_branch_reveal` | M1 | 安全头部 |
| 3 | S02 | 起重吊装安全 | A | `decision_branch_reveal` + `process_step_reveal` | M1 | 安全头部 |
| 4 | C02 | 进度款/计量计价 | B | `calculation_whiteboard` | M1 | 成本计价 stem 命中靠前 |
| 5 | B02 | 基坑支护选型与降水/监测 | A | `section_space_reveal` | M1 | 高频且补构造/空间能力 |
| 6 | Q01 | 混凝土养护与裂缝防治 | A | `contrast_pair_reveal` | M1 | 混凝土头部,错因稳定 |
| 7 | A01 | 检验批/分部分项验收程序 | A/C | `process_step_reveal` | M1 | 质量验收头部;隐蔽/见证另列 A02 |
| 8 | N01 | 双代号网络计划关键线路/总时差 | B | `network_plan_keypath` | M1 | 进度网络纯案例代表 |
| 9 | K01 | 索赔成立与工期/费用计算 | B/C | `calculation_whiteboard` | M1 | 合同索赔代表 |
| 10 | Q03 | 质量通病: 蜂窝麻面/空鼓裂缝 | A | `contrast_pair_reveal` | M2 | 质量通病高失分 |
| 11 | C04 | 模板拆除顺序与条件 | A | `process_step_reveal` | M2 | 混凝土/模板高频 |
| 12 | Q02 | 大体积混凝土温控裂缝 | A/B | `process_step_reveal` + `calculation_whiteboard` | M2 | 混凝土数据头部 |
| 13 | C01 | 施工缝留置与处理 | A | `contrast_pair_reveal` | M1 | 已有样板,混凝土采分小问 |
| 14 | C05 | 钢筋连接选用 | A | `decision_branch_reveal` + `contrast_pair_reveal` | M2 | 连接方式辨析常错 |
| 15 | C06 | 砌体留槎与构造柱 | A | `section_space_reveal` | M2 | 构造类常错 |
| 16 | C07 | 钢结构连接: 焊接/高强螺栓 | A | `contrast_pair_reveal` | M2 | 结构连接辨析 |
| 17 | S05 | 临时用电: 三级配电两级保护 | A | `section_space_reveal` | M2 | 安全高频,图解收益高 |
| 18 | S06 | 高处作业/临边洞口防护 | A | `contrast_pair_reveal` | M2 | 安全现场判断 |
| 19 | S07 | 安全事故等级判定与上报 | C/A | `kinetic_text_ppt` + `decision_branch_reveal` | M2 | 判断规则和采分词稳定 |
| 20 | N02 | 网络计划工期优化与赶工费用 | B | `calculation_whiteboard` | M2 | N01 后的进度计算延展 |

## 9. L40/L20 专家裁决表

### 9.1 层级分布

| 层级 | 数量 | 范围 | 生产策略 |
|---|---:|---|---|
| P0 locked | 20 | 案例头部高频考点 | A/B 为主,优先做出学习闭环 |
| P1 active | 20 | 中频但强图解/强计算/强复测考点 | 允许做 source/storyboard,生产 gated |
| P2 candidate | 20 | 候选池、条件拆分、合并子项、evidence-pending | 不构成生产承诺 |

### 9.2 60-slot map

| Slot | Pack ID | 考点 | 桶 | 类型 | 主模板 | 层级 | 专家裁决 |
|---:|---|---|---|---|---|---|---|
| 1 | J01 | 危大工程范围 + 专项方案 + 专家论证 | 安全/危大 | A | `decision_branch_reveal` | P0 locked | 稳定;细考点 stem 命中最高 |
| 2 | S01 | 脚手架/高大模板支架验收 | 安全/危大 | A | `decision_branch_reveal` | P0 locked | 稳定;安全头部 |
| 3 | S02 | 起重吊装安全 | 安全/危大 | A | `decision_branch_reveal` + `process_step_reveal` | P0 locked | 稳定;安全头部 |
| 4 | C02 | 进度款/计量计价 | 成本/计价 | B | `calculation_whiteboard` | P0 locked | 稳定;计算题代表 |
| 5 | B02 | 基坑支护选型与降水/监测 | 安全/危大/地基 | A | `section_space_reveal` | P0 locked | 稳定;补空间构造能力 |
| 6 | Q01 | 混凝土养护与裂缝防治 | 混凝土/结构 | A | `contrast_pair_reveal` | P0 locked | 稳定;错法明确 |
| 7 | A01 | 检验批/分部分项验收程序 | 质量/验收 | A/C | `process_step_reveal` | P0 locked | 缩窄;不吞隐蔽/见证 |
| 8 | N01 | 双代号网络计划关键线路/总时差 | 进度/网络 | B | `network_plan_keypath` | P0 locked | 稳定;纯案例能力 |
| 9 | K01 | 索赔成立与工期/费用计算 | 合同/索赔 | B/C | `calculation_whiteboard` | P0 locked | 稳定;合同索赔代表 |
| 10 | Q03 | 质量通病: 蜂窝麻面/空鼓裂缝 | 质量/验收 | A | `contrast_pair_reveal` | P0 locked | 稳定;高失分 |
| 11 | C04 | 模板拆除顺序与条件 | 混凝土/结构 | A | `process_step_reveal` | P0 locked | 稳定;工序判断 |
| 12 | Q02 | 大体积混凝土温控裂缝 | 混凝土/结构 | A/B | `process_step_reveal` + `calculation_whiteboard` | P0 locked | 稳定;数据头部 |
| 13 | C01 | 施工缝留置与处理 | 混凝土/结构 | A | `contrast_pair_reveal` | P0 locked | 稳定;已有样板 |
| 14 | C05 | 钢筋连接选用 | 混凝土/结构 | A | `decision_branch_reveal` + `contrast_pair_reveal` | P0 locked | 稳定;连接方式辨析 |
| 15 | C06 | 砌体留槎与构造柱 | 混凝土/结构 | A | `section_space_reveal` | P0 locked | 稳定;构造错因 |
| 16 | C07 | 钢结构连接: 焊接/高强螺栓 | 混凝土/结构 | A | `contrast_pair_reveal` | P0 locked | 稳定;结构连接辨析 |
| 17 | S05 | 临时用电: 三级配电两级保护 | 安全/危大 | A | `section_space_reveal` | P0 locked | 稳定;图解收益高 |
| 18 | S06 | 高处作业/临边洞口防护 | 安全/危大 | A | `contrast_pair_reveal` | P0 locked | 稳定;现场判断 |
| 19 | S07 | 安全事故等级判定与上报 | 安全/危大 | C/A | `kinetic_text_ppt` + `decision_branch_reveal` | P0 locked | 稳定;规则采分词 |
| 20 | N02 | 网络计划工期优化与赶工费用 | 进度/网络 | B | `calculation_whiteboard` | P0 locked | 稳定;N01 后续 |
| 21 | D11 | 抹灰工序与质量控制 | 装饰装修 | A/C | `process_step_reveal` | P1 active | active;装饰中频 |
| 22 | D12 | 饰面砖/板施工质量与空鼓防治 | 装饰装修 | A | `contrast_pair_reveal` | P1 active | active;空鼓错因清晰 |
| 23 | D13 | 幕墙防火/防雷/层间封堵构造 | 装饰装修 | A | `section_space_reveal` | P1 active | active;强构造空间 |
| 24 | D14 | 吊顶/门窗/地面装饰质量综合 | 装饰装修 | A/C | `section_space_reveal` + `practice_card_checklist` | P1 active | 合并 D14-D16 主包;细拆需 source_ref |
| 25 | G01 | 基坑开挖与降水方法选择 | 地基/土方 | A | `section_space_reveal` + `decision_branch_reveal` | P1 active | active;与 B02 区分方法选择 |
| 26 | G02 | 土方回填压实与检测 | 地基/土方 | A/C | `process_step_reveal` | P1 active | active;检测流程明确 |
| 27 | G03 | 桩基施工与质量问题 | 地基/土方 | A | `section_space_reveal` + `decision_branch_reveal` | P1 active | active;地基中频 |
| 28 | G04 | 地基验槽与地基处理 | 地基/土方 | A/C | `decision_branch_reveal` | P1 active | active;验槽责任清晰 |
| 29 | F16 | 屋面防水起鼓割补 | 防水 | A | `process_step_reveal` | P1 active | active;留存入口 |
| 30 | F02 | 卷材防水施工顺序与搭接方向 | 防水 | A | `process_step_reveal` | P1 active | active;防水工序基础 |
| 31 | F03 | 防水构造层次: 屋面/地下 | 防水 | A | `section_space_reveal` | P1 active | active;剖面图解 |
| 32 | F04 | 防水细部节点: 阴阳角/管根/女儿墙 | 防水 | A | `section_space_reveal` + `contrast_pair_reveal` | P1 active | active;节点常错 |
| 33 | F05 | 渗漏治理诊断 | 防水 | A/D | `contrast_pair_reveal` + `practice_card_checklist` | P1 active | active;不升判分 renderer |
| 34 | X01 | 施工平面布置原则 | 现场/平面 | A | `section_space_reveal` + `decision_branch_reveal` | P1 active | active;平面图解收益高 |
| 35 | X02 | 临设、道路、材料堆场布置 | 现场/平面 | A | `section_space_reveal` | P1 active | active;平面要素组织 |
| 36 | X03 | 文明/绿色/环保施工措施 | 现场/平面 | C/D | `kinetic_text_ppt` + `practice_card_checklist` | P1 active | 合并 X04;用场景触发清单 |
| 37 | R01 | 现场消防布置、动火、检查、验收流程 | 防火/消防 | A/C/D | `decision_branch_reveal` + `kinetic_text_ppt` | P1 active | 合并 R05 默认路径 |
| 38 | N03 | 流水施工参数与工期 | 流水/进度 | B | `calculation_whiteboard` | P1 active | 上调;计算迁移强 |
| 39 | E05 | 挣值法/偏差分析 | 成本/进度 | B | `calculation_whiteboard` | P1 active | 上调;公式型可复测 |
| 40 | A02 | 隐蔽工程验收 + 材料进场复验/见证取样 | 质量/验收 | C/D | `kinetic_text_ppt` + `practice_card_checklist` | P1 active | 吸收 D17/F06 默认路径 |
| 41 | E01 | 工程量清单计价 | 成本/计价 | B/C | `calculation_whiteboard` | P2 candidate | candidate;成本基础 |
| 42 | E02 | 预付款、起扣点、进度款细分 | 成本/计价 | B | `calculation_whiteboard` | P2 candidate | default merge into C02/E01 |
| 43 | E03 | 措施费、暂列金额、暂估价判断 | 成本/计价 | C/D | `kinetic_text_ppt` + `practice_card_checklist` | P2 candidate | candidate;概念边界 |
| 44 | E04 | 竣工结算与价款调整 | 成本/计价 | B/C | `calculation_whiteboard` | P2 candidate | candidate;默认吸收 K04 |
| 45 | K03 | 工程变更与签证 | 合同/索赔 | C/A | `kinetic_text_ppt` + `decision_branch_reveal` | P2 candidate | candidate;合同边界 |
| 46 | K05 | 工期顺延与费用补偿边界 | 合同/索赔 | B/C | `calculation_whiteboard` | P2 candidate | candidate;索赔迁移 |
| 47 | K06 | 合同责任事件归属矩阵 | 合同/索赔 | C/D | `kinetic_text_ppt` + `practice_card_checklist` | P2 candidate | candidate;吸收 K02 |
| 48 | R02/R03 | 耐火等级、疏散距离、防火分区基础数值判断 | 防火/消防 | C/D | `practice_card_checklist` | P2 candidate | candidate;R02 不独立做 M1 |
| 49 | R04 | 防火封堵与幕墙层间防火 | 防火/消防/装饰 | A/C | `section_space_reveal` | P2 candidate | candidate;可与 D13 联动 |
| 50 | N04 | 时标网络计划与前锋线判断 | 进度/网络 | B/A | `calculation_whiteboard` + `network_plan_keypath` | P2 candidate | candidate;进度图结构延展 |
| 51 | G05 | 支护结构监测报警与处置 | 地基/安全 | C/A | `kinetic_text_ppt` + `decision_branch_reveal` | P2 candidate | candidate;与 B02/G01 联动 |
| 52 | K04 | 合同价款调整触发与计算边界 | 合同/计价 | B/C | `calculation_whiteboard` | P2 candidate | conditional split from E04/K05 |
| 53 | K02 | 不可抗力责任划分 | 合同/索赔 | C/D | `practice_card_checklist` | P2 candidate | sub-pack under K06 by default |
| 54 | R05 | 消防验收流程 | 防火/消防 | C/D | `kinetic_text_ppt` | P2 candidate | conditional split from R01;需 source_ref |
| 55 | X05 | 季节性施工措施: 雨期/冬期/高温 | 现场/质量 | D | `practice_card_checklist` | P2 candidate | evidence-pending;默认作场景变体 |
| 56 | F06 | 防水材料性能与进场复验 | 防水/质量 | D | `practice_card_checklist` | P2 candidate | sub-pack under A02 by default |
| 57 | D17 | 装饰材料进场复验与见证取样 | 装饰/质量 | D | `practice_card_checklist` | P2 candidate | sub-pack under A02 by default |
| 58 | X04 | 绿色施工措施 | 现场/平面 | C/D | `kinetic_text_ppt` + `practice_card_checklist` | P2 candidate | sub-pack under X03 by default |
| 59 | D15 | 门窗安装、防渗漏质量控制细分候选 | 装饰装修 | A/C | `section_space_reveal` | P2 candidate | split from D14 only if source_ref proves |
| 60 | D16 | 地面基层与面层质量细分候选 | 装饰装修 | A/C | `process_step_reveal` | P2 candidate | split from D14 only if source_ref proves |

## 10. 为什么是这个裁决

选择逻辑分四层:

1. **先锁大桶**: 真题频次方向性显示混凝土/结构、安全/危大、进度/网络、质量/验收是案例头部;装饰、地基、防水、现场、成本、合同、消防组成中后段。
2. **再拆可命题考点**: 只选案例小问能直接问、能错、能练、能复测的考点,不按教材叶子铺。
3. **再按专家裁决合并**: 相同错因、相同采分句结构、相同复测方式的点默认合并;只有 source_ref 证明独立高频才拆。
4. **最后选最低成本形态**: 能画的画,该算的算,该文字运镜的文字运镜,该 checklist 的 checklist。生产形态跟学习目标走,不跟"动画炫技"走。

因此:

- E05 保留并上调,因为它是可计算、可复测的 B 类白板。
- K06 保留为 C/D 样板,吸收 K02。
- X04/X05、F06/D17、R05、K04 默认不独立锁定;进入合并包或 candidate pool。
- R02 不做 M1 样板,只作为 R02/R03 数值判断候选。

## 11. 每个 pack 的生产定义

一个 motion learning pack 必须交付以下文件或等价结构:

```text
<pack_id>.schema.json
<pack_id>.storyboard.md
<pack_id>.rendered.html 或 <pack_id>.deck.html
<pack_id>.lesson.json
<pack_id>.lesson.timing.json
<pack_id>.practice.html 或 practice block
<pack_id>.acceptance.md
```

最低字段:

| 字段 | 说明 |
|---|---|
| `pack_id` | 稳定 ID,如 `N01_network_video_first` |
| `primary_taxonomy_ref` | 一个主 canonical taxonomy 锚点,状态翻转前必须当前可解析 |
| `supporting_taxonomy_refs[]` | 组合包辅锚点,用于召回/复测/覆盖率 |
| `taxonomy_alignment_status` | `direct` / `composite` / `coarse_review` / `merged_child` / `conditional_split` |
| `student_title` | 学员可见中文标题,不得 fallback 到 raw code |
| `exam_point` | 一个可命题考点,不是章节名 |
| `production_type` | A/B/C/D |
| `template_type` | 具体模板,如 `kinetic_text_ppt` |
| `wrong_idea` | 学员最常见错误心智 |
| `visual_or_motion_correction` | 图、公式、运镜或 checklist 如何纠正 |
| `exam_phrase` | 考试可写采分句 |
| `source_refs` | 教材/真题/规范/教研依据 |
| `authority.status` | candidate / signed_candidate / official_score_allowed=false 等 |
| `practice` | 当天小练 |
| `retest` | D1/D7 复测候选 |

## 12. C/D 类标准

C/D 类不是把 PPT 录屏或 checklist 凑数。它必须像老师用板书推进:

1. 关键词出现顺序 = 讲解逻辑。
2. 运镜焦点 = 当前判断。
3. 颜色变化 = 对/错/风险/采分。
4. 每屏只出现一个判断或一组同类词。
5. 最后一屏必须留下采分句、责任边界或 checklist。
6. 必须能配一个当日小练和一个 D1/D7 复测。

适用范围:

- 责任边界: K06 合同责任事件归属矩阵。
- 措施清单: X03 文明/绿色/环保施工措施。
- 消防流程: R01 现场消防管理。
- 复验清单: A02 隐蔽/材料复验/见证取样。
- 数值判断: R02/R03 防火基础数值判断。

禁区:

- 不做大段讲义翻页。
- 不用花哨转场替代讲解逻辑。
- 不把未核 source_ref 的规范数字做成强记忆卡。
- D 类只有拥有错因、采分句、D1/D7 复测闭环时才算独立 pack。

## 13. 生产流水线

每条 pack 走 8 步,其中嵌入 4 道已被验证必需的工序:

0. **判断类分流(decision-first vs video-first)**: 选考点时先判生产形态——判断/分支型考点走 decision-first(交互卡 + 旁白),不要硬包成 video-first 视频;只有时序/计算/空间型才默认 video-first。判断题硬做成视频=损失交互与复测。
1. 选考点: 来自 P0 locked / P1 active;P2 candidate 只做证据补强。
2. 绑定 taxonomy: 写入 `primary_taxonomy_ref` / `supporting_taxonomy_refs[]`,并记录 source sha。
3. 编 teaching spine: wrong idea / correction / exam phrase / warm correction / authority。
4. 编 schema JSON: 只写上游事实和候选,不写判分结论。
5. 编 storyboard: 5-8 beats,每 beat 一个视觉或运镜动作。
6. 渲染 HTML/deck: renderer 只渲染,不判断。
   - **防漂移 anchor 闸**: 任何 `claim:true` 的 beat 必须 anchor 回卡(可追溯到卡内字段);`build_lesson_narration` 检测到未 anchor 的 claim beat 必须报错退出,不得静默生成旁白。
   - **student-safe 包检查**: 渲染产物必须过 `validate_schema_drafts.py`,并对照 `rendering_contract` 双名单(允许暴露 / 禁止暴露字段)核验;raw taxonomy code / pack_id / 内部 source_ref 命中禁止名单即 fail。
7. 做小练/复测: 至少一个当天题 + 一个 D1/D7 变式候选。
8. 做验收: mobile screenshot、taxonomy/source/authority check、学员任务测试。
   - **关键样板 Codex 对抗**: M0/M1 关键样板在验收阶段过一轮 Codex 对抗审查(走 `codex exec --sandbox read-only`),抓走向校验洞、改字段漏改读点等盲点。

## 14. Gate

### G-1: Runtime Closure Gate

排在所有 gate 之前。**留存/复测验证(§15 Week4 concierge、G2/G3 指标)启动前,必须先证明本 plan 产出的 practice/retest 在 TutorBot runtime 上闭环。** 三件套必须同时出现并截图留证:

1. **做题 → 判分**: 学员作答后 runtime 真实判分(非 fall-through、非 invariant 占位)。
2. **给答案 + 解析**: 判分后必须给出答案与解析(硬约束:答题必有解析)。
3. **正向反馈**: 输出"先捧 → 就差一步 → 我相信你"结构的暖反馈。

未通过则留存验证 INVALID。背景:`mcq_grading` 路由缺口(做完题不判分/不给答案/无正反馈)曾是内测流失第一杀手,**已于 2026-06-17 修复(commit `80a34ca0a`:Fix A orchestrator mcq_grading 守卫 + Fix B open-world backstop + Fix C open_world_question tier,测试全绿)**。所以 G-1 已**降级为留存验证前的回归把关**(每次验证前截图确认闭环仍通、防回归),不再是阻塞前置。残留 Fix C step2(出题侧 `object_type_override` 让 source-backed 变式卡可作答)是下游扩展,不属"做完题不判分"根因。

### G0: Authority gate

未通过则不能给学员默认展示:

- source_ref 不为空。
- `primary_taxonomy_ref` 不为空,且当前 `taxonomy_index()` 可解析。
- `taxonomy_alignment_status` 不得为 `coarse_review`,除非仅做内部 leaf review。
- candidate / signed / official 边界明确。
- renderer 不生成知识、不改分、不重判分。
- 学生 UI 不暴露内部 source_ref / schema / P 编号。
- 学生 UI 不暴露 raw taxonomy code 或 pack_id。
- 生产前必须运行 `python scripts/check_luban_animation_taxonomy_alignment.py`;新增 pack manifest 还必须传 `--manifest <path>`。

### G1: Teaching gate

未通过则不能进入 M1:

- 首屏暴露一个常见错法。
- 3 秒内能看出老师在讲什么。
- 动画/运镜每一幕只讲一个点。
- 最终板只保留关键图、关键词或采分句。
- 不是 dashboard,不是长讲义,不是炫技视频。

### G2: Learner gate

未通过则不能扩到 20 个:

- 3-5 人任务测试中,多数人能复述错因。
- 多数人能写出目标采分句。
- 小练正确率或解释质量有提升。
- D1 至少有人回来做复测。

### G3: Scale gate

未通过则不能把 P1/P2 升级为批量排产:

- D1 回访率 ≥ 预注册目标、D7 回访率 ≥ 预注册目标、复测正确率提升 ≥ 预注册 pct(以上三个数值在留存实验**预注册时钉死**,不得事后凑数)。
- 换皮题迁移有正向证据。
- A/B/C/D 每类生产成本和审核周期可控。
- 模板没有产生第二套评分/知识/学情 authority。

## 15. 30 天执行计划

口径修正: 底座首发成本 ≫ 套用成本,30 天不可能出齐 12 个。**30 天目标定为【3 套底座 + 6 个 pack + 前移的留存证明】,剩余 6 个 pack 顺延约 7-8 周且 gated on G2。** 母题数据单列教研工期,不并进渲染工期。

### Week 1-2: 底座期

- 收口 4 个 M0:统一 J01/N01/C01/F16 的 teaching spine 和 acceptance;N01 作为 video-first 质量基线。
- **只攻 1 套新底座**: `section_space_reveal`(构造/空间 renderer + spec),用 B02 基坑支护与降水做样板。
- 写 `kinetic_text_ppt` 的 5-8 beat deck 规范,用 K06 做 C 类样板。
- (M0 收口 + 已有原型沿用,不在 Week1-2 强行新造第二套底座。)

### Week 3-4: 套用期 + 前移留存证明

Week 3-4 套用底座出 **3 个 pack**(在已就绪底座上套用,不再首发新模板):

- S01 脚手架/高支模验收(套 `decision_branch_reveal`)。
- Q01 混凝土养护裂缝(套 `contrast_pair_reveal`)。
- K06 合同责任事件归属矩阵(套 `kinetic_text_ppt`,Week1-2 样板收正)。

**Week 4 末:提前做 G2 留存验证**,用先出的 J01 / B02 / N01 + F16 直接验,**别等 12 个齐**:

- 先过 **G-1 Runtime Closure Gate**:截图证明 practice/retest 在 runtime 上「做题→判分→给答案+解析→正向反馈」三件套同时出现;未过则验证 INVALID,不启动。
- 5 人任务测试: J01 / B02 / N01。
- 5 天 concierge 留存主验证载体: F16(1 个母题);J01/B02/N01 是模板覆盖证据,不当独立留存臂。
- 输出 M1 decision package: GO / WEAK-GO / NO-GO(GO 前 G3 阈值必须已预注册钉死)。

### Week 5-8: 后 6 个 pack(gated on G2)

- 仅在 Week4 G2 GO/WEAK-GO 后才启动,出剩余 6 个 M1 pack(S02、A01、K01、C02 等套用型为主)。
- GO 后才进入 P0 20 的 M2 草稿,不是批量生产。
- P0 20 的 M2 草稿必须先补 taxonomy registry 里的主/辅锚点,`coarse_review` 项先补 source/leaf review。

## 16. Owner 分工

| Owner | 职责 |
|---|---|
| 教研 owner | 选考点、写采分句、确认 source_ref 和 candidate 边界 |
| 动画导演 owner | teaching spine、beat sheet、白板/运镜节奏、视觉质量 |
| renderer owner | schema 校验、确定性渲染、移动端安全字段 |
| 产品 owner | 今日任务入口、练习/复测、学员测试设计 |
| 评测 owner | D1/D7、采分句迁移、任务测试结果 |

一个人可以兼多岗,但一个 pack 必须能填出这 5 类 owner。

## 17. 红线

- 不按 1500+ taxonomy leaf 做视频。
- 不按讲义章节做长课。
- 不让 AI 文生视频决定施工事实。
- 不把 candidate teaching prototype 冒充 official score。
- 不因为一个考点"只能文字运镜"就自动升为独立 pack。
- 不在 12 个 starter packs 验证前批量生产 30 个。
- 不把 P2 candidate pool 当生产 backlog。
- 不为了通用化提前抽复杂 renderer 框架。
- 不把观看完成率当主要学习效果指标。
- 留存/复测验证启动前必须确认 runtime 判分 → 答案 → 正反馈闭环已通(见 G-1);否则验证结果尤其 NO-GO 一律无效。
- 留存验证失败时先排除 runtime / 交付链断裂,再归因到内容。

## 18. 当前拍板

当前最小可执行拍板:

1. 动画学习体系第一阶段目标定为 12 个 starter packs。
2. P0 头部地图为 20 个 locked,但不是批量生产授权。
3. L60 改为 L40 locked/active + L20 candidate pool;P2 不构成生产承诺。
4. A/B/C/D 四种生产形态并行存在;不是所有 pack 都做重图解动画。
5. 下一张重图解动画优先做 B02 基坑支护与降水,补齐构造/空间模板。
6. 下一张文字运镜样板改为 K06 合同责任事件归属矩阵,不是 R02。
7. E05 上调为 P1 active 的 B 类计算白板候选。
8. X04/X05、F06/D17、K02/K06、K04/E04、R05/R01 默认合并;只有 source_ref 证明独立高频才拆。
9. N01 是 video-first 质量基线,F16 是留存体验样板,J01 是判断高频样板,C01 是对比样板。
10. 未过 G2 learner gate 前,禁止启动 20 个以上的批量生产。
11. pack_id 保留资产编号;学习路径、盲点归因、题库召回和复测必须走 canonical taxonomy 对齐注册表。
12. M1 的 12 个在 Week4 GO 前一律记为【模板底座验证样板】,不计入 P0 20 产能、不对学员暴露、不当 KPI;Week4 留存主验证载体仍是 1 个母题(F16),其余 pack 是模板覆盖证据,不是把 1 个留存假设稀释成 12 个弱信号的多臂分散。

---

## 19. 专家组评审结论与必改项(2026-06-19)

四路专家(战略对齐 / 单一权威架构 / 生产可行性 / 红队留存)对抗评审。**总裁决:plan 质量高、方向对、且罕见地自带可执行护栏(gate 脚本/taxonomy 注册表真实落地),但不能直接照搬执行——有 1 个致命前置 + 3 个中度必改。**

| 维度 | 裁决 | 关键结论 |
|---|---|---|
| 战略对齐 | ✅ 对齐 | 是 v1.3 的供给侧生产计划,不另起主线;"12 个 starter"是模板底座最小集(验证供给侧能不能产),与 v1.3"先 1 个母题验证留存"(验证需求侧人会不会回来)不矛盾 |
| 单一权威/架构 | ✅ 合规 | 未抢 grading/LearnerState/错因权威;`canonical_taxonomy_refs[]` 显式声明≠判分点;gate 脚本/`taxonomy_index()` 真实存在 |
| 生产可行性 | ⚠️ 偏乐观 | 30 天/12 个严重低估:套用型 1.5-2 人天、新模板首发 1-1.5 人周;5 个要先造新底座;母题数据未单列工期;无 Codex 返工 buffer |
| 红队/留存 | ✅ 风险已解除 | 红队指出"Week4 留存依赖的 runtime 闭环若断会杀错方向";实查 runtime 闭环**已于 2026-06-17 修复**(commit `80a34ca0a`)→ 致命风险解除,G-1 保留为回归把关 |

### 必改项(按优先级)

**P0【已修·G-1 保留为回归把关】runtime 留存闭环**
本 plan 是母题引擎(造 pack)侧;§15 Week4 的 concierge 留存、§14 G2/G3 指标都在 TutorBot runtime 上交付。红队曾警告"runtime 的 `mcq_grading` 路由缺口(做完题不判分/不给答案/无正反馈)若断,Week4 留存 NO-GO 会把 runtime bug 误扣到动画体系、杀错方向"。**实查结论:该缺口已于 2026-06-17 修复(commit `80a34ca0a`:Fix A/B/C,测试全绿),致命风险解除。** G-1 因此保留为**留存验证前的回归把关**(每次验证前截图确认「做题→判分→给答案+解析→正反馈」三件套仍在,防回归),非阻塞前置。仍待办:G3 的"预设阈值"必须填死具体数(D1≥X% / D7≥Y% / 正确率提升≥Z),空阈值=事后凑数。

**P1【中·改节奏】30 天计划改为"3 套底座 + 6 个 pack + 前移的留存证明",12 个顺延 7-8 周**
底座首发成本≫套用成本;母题数据要单列教研工期;留存验证前移(用先出的 J01/B02/N01 做 G2,别等 12 个齐)。§13 流水线补 4 道已被验证必需的工序:防漂移 anchor 闸、student-safe 包检查、Codex 对抗、判断类 decision-first vs video-first 分流。

**P2【中·锁口径】结构化锁死"12 个 ≠ P0 已交付 9 个"**
M1 的 12 个在 Week4 GO 前一律记为"模板底座验证样板",不计入 P0 20 产能、不对学员暴露、不当 KPI;Week4 留存主验证载体仍是 1 个母题(F16),其余是模板覆盖证据,不把 1 个留存假设稀释成 12 个弱信号。

**P3【中·收硬门】G0 从手动门变硬门**
`check_luban_animation_taxonomy_alignment.py` 接入 contract_guard/CI(否则是 dormant authority);G0 串联渲染层 `validate_schema_drafts.py` + `validate_video_first_preview.mjs`(student-safe 不靠自觉);motion pack manifest 生产前在 `contracts/schema_registry.yaml` 登记 schema_version(标内容/资产 schema 非 grading schema)。

**P4【低】§17 补"实验有效性/归因"红线**(留存验证失败先排除 runtime/交付链断裂再归因内容)、标题加一句"本文是 v1.3 下供给侧生产计划,非新主线"。

### 是否可执行

**可执行**:P0 runtime 闭环已修(致命风险解除);P1 节奏 + P2 口径 + P4 红线/标题 + G-1/G3 已落入正文(2026-06-19 修订)。剩余:填死 G3 预注册阈值、按 P3 方案收 G0 硬门(串行 + 确认)。**即可启动 Week1**(收口 4 个 M0 + 攻 section_space_reveal 底座 + B02 样板),Week4 留存验证前过 G-1 回归把关即可。骨架/Gate/红线/从属关系无需推翻。
