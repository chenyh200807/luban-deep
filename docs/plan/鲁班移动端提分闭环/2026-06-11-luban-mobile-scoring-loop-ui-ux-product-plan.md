# 鲁班移动端每日提分闭环 UI/UX 产品契约 PRD v1.3

> Status: Proposed / Current canonical product authority v1.3 for mobile UI/UX restructuring
> Date: 2026-06-11
> Scope: 鲁班智考移动端、小程序 `yousenwebview` 内 `packageDeeptutor` 分包、案例题训练、AI 批改、今日任务、错题复练、章节/知识点调度。

## 0. Current Canonical Decision

本文件是鲁班移动端 UI/UX 大型重构的当前 canonical 产品入口。后续移动端 PRD、原型、任务拆分、验收标准和实现计划，先读本文件，再进入对应专项计划。

> 关联专项（2026-07-01）：获客 / 引流 / 转化维度另见 [考点小课引流与会员转化专项计划](2026-07-01-luban-microlesson-acquisition-conversion-plan.md)（Proposed，child plan）。它把教学动画卡当引流钩子（免费 3 个 → 会员），定位为漏斗顶部获客层，复用本文同一套单一权威，不改本文 P0A 留存主菜范围；其「把视频教学从 gated on 留存 提前到引流试点 + 引入会员转化」相对本文 §1 非目标是一个**待用户拍板的优先级调整**，不视为本文已批准范围。
>
> 关联专项（2026-07-02 机制输入；2026-07-16 产品表面已收口）：[「学习 × 复习」双轮设计 v3](2026-07-02-luban-learn-review-double-wheel-design.md) 仅保留为「今日任务 → 轻练 → 诊断 → 次日复测」的间隔复测机制输入，**不再定义独立复习模块或 Tab**。当前目标信息架构唯一为 5 Tab「学习 / 历史 / 问鲁班 / 学情 / 我的」；复测、错题和到期任务都是「学习」内的任务状态，调度/掌握真值仍收权到 `revalidation_queue` 与 LearnerState；「历史」只承载对话历史和继续对话，不承载练习流水。

本文件吸收并收口以下输入资料，但这些输入资料不再单独作为实现 authority：

- [PRD/鲁班智考移动端 UI/UX 大型重构 PRD v1.0.md](<../../../PRD/鲁班智考移动端 UI/UX 大型重构 PRD v1.0.md>) — UI/UX 主骨架、页面结构、ViewModel、阶段路线输入。
- [PRD/鲁班智考移动端 UI/鲁班混合制章节改造补充资料.md](<../../../PRD/鲁班智考移动端 UI/鲁班混合制章节改造补充资料.md>) — 混合自适应、章节/知识点驱动、高频母题、章节任务包输入。
- 用户上传的两份研究报告 — 主逻辑选择、一建人群与 UI/UX 研究输入；保留为研究证据，不作为工程实施 authority。

一句话总控：

鲁班智考移动端最终形态，是一个以「每日提分留存闭环（今日任务 → 知识点/母题 MCQ 轻练 → 盲点诊断与教材章节定位 → 复练复测）」为前台主菜、以「章节知识图谱 + 高频母题 + 采分点 + 错因」为后台、以「案例题渐进作答 + AI 采分点批改 + 二次作答 + 错因复练」为养成习惯后解锁的深度护城河层的一建建筑实务 AI 提分系统。

v1.2 的关键升级不是把文档写厚，而是把本计划从「方向总控」升级成「可执行产品契约」，并吸收 2026-06-11 计划体系评审的 P0 收权结论：

- 明确 North Star、用户承诺和业务闭环。
- 明确 P0A-0 先准备 2–3 个同门槛 Pack 的代表性微批 spike（treatment 默认 2 个，第 3 个只在真实流量足够时进入；v1.3 已把 spike 形态改为「每日留存闭环」，2026-07-16 取消 F16 专属优先级），再扩到 3–5 个高频母题；P0A-1 才解锁半写、完整作答与 AI 批改，不一次性铺开全部 30–40 母题和复杂训练形态。
- 明确 P0B 再扩到 30-40 个高频母题包和更完整入口。
- 补齐 release gates、失败态、资产生产线、任务推荐公式、人工复核、隐私、成本、灰度和回滚门槛。
- 保持 single authority：前端、OCR、行为事件、RAG、知识图谱都不能成为评分或 learner truth 的第二来源。
- 增补实施前置硬门槛：小程序开发树与验收树收权、推荐 authority 映射、轻练证据规则；半写 `task_scope` 与 `mistake_tag` canonical schema 是 P0A-1 深度层前置，不再反向阻断 P0A-0 留存切片。

### 0.0 v1.3 重心收口（2026-06-15）

v1.3 不推翻 v1.2 的积木，只纠正**重心和顺序**，依据是第一波内测的真实行为数据（5 份 NPS 回访 + 66 份申请）：正在备考的用户对「案例题阅卷 / 错因陪练」全部为 `na`，唯一用了案例题阅卷的人已经考过试（无压力）；活跃用户只把产品当 AI 问答用；用户原话最痛的是「查盲点 → 定位教材该知识点章节 → 制定追赶计划，而非通过测试不断发现问题打击信心」，最大单一痛点是「记不住知识点」（~35%）与「想知道薄弱章节」（~20%），「案例题不会写」只占 ~20%。NPS 8-10 但 `revisit_willingness=no`：高满意、零行为承诺。

收口结论（吸收已确认前提 B：案例题阅卷不该当头牌）：

- **核心主菜改为「每日提分留存闭环」**：今日任务 → 2 分钟知识点 / 母题 MCQ 轻练 → 当场拿到「今天补了哪个盲点 / 为什么丢分（错选项 → 采分点 / 教材章节定位）/ 明天复测什么」→ 次日回来。低门槛、碎片时间可完成、情绪正向（补盲点而非被挑错）。
- **案例题渐进作答 + AI 采分点批改 = 深度护城河层**，是用户养成每日习惯后第二阶段解锁的高阶能力，不是新用户第一眼看到、第一个被要求做的事。它仍是真正的差异化（商品 LLM 判不了一建采分点），但不再是头牌。
- **P0A 第一个 spike 改为验证「人会不会回来」**（留存假设），不是验证案例题批改技术闭环（M32 已证明能跑）。
- **GO 门钉在真实 D1/D7 回访行为**（预注册目标值），不是「闭环技术走通 + 完成率」。

硬约束（防止 B 退化成商品刷题 App 或第二套 authority）：每日轻练 MCQ 必须由 `case_family` / `scoring_point` / `knowledge_node` 锚定，错选项必须映射到 canonical `mistake_tag` 与教材章节定位，作答结果写入同一份 `learning_evidence` 账本，复测由既有 `revalidation_queue` 调度。不得新建第二套题库引擎、第二套 learner memory、第二套推荐 authority。无诊断的题海等于和用户现有「刷题/看解析」status quo 正面竞争且无差异。

### 0.1 North Star

North Star:

让忙碌的一建建筑实务在职考生，每天用两分钟就知道自己补了哪个盲点、为什么丢分、明天该复测什么，并且愿意明天再来。

用户承诺：

- 打开后不用逛功能，直接看到今天最高收益的 2 分钟轻练任务。
- 答完一组知识点 / 母题 MCQ，不只看到对错，而是看到自己暴露的盲点、对应采分点与教材章节定位，以及一句「明天给你复测这几个」。
- 每次有效训练都会进入学习证据账本，并影响后续错题、复练、复测和明天的今日任务。
- 系统不伪装成绝对准确；低置信、OCR 不确定、高风险批改必须显式提示或进入复核。
- 案例题渐进作答 + AI 采分点批改作为养成习惯后解锁的深度层，让用户从「每天补盲点」自然走进「把案例题写对、拿全采分点」。

业务闭环（前台留存主链）：

```text
今日任务
-> 2 分钟知识点 / 母题 MCQ 轻练
-> 盲点诊断（错选项 -> 采分点 / 教材章节定位）
-> learning_evidence
-> NextBestAction（明天复测什么）
-> 次日复测
-> （养成后解锁）案例题渐进作答 -> AI 采分点批改 -> 错因复练
```

P0A 只有证明这条**留存主链**真实可走（人会回来），才允许进入 P0B 扩面与案例题深度层全量铺开。

## 1. 非目标

本次重构不是：

- 普通 UI 皮肤改版。
- 聊天机器人首页。
- 传统题库目录首页。
- OCR 批改工具。
- 课程商城或功能大厅。
- 复杂知识图谱可视化项目。
- 纯刷题 / 背题 App。轻练 MCQ 必须由采分点 / 母题 / 教材锚定并当场产出盲点诊断与教材章节定位，不是无诊断的题海；否则会与用户现有「刷题、看解析」status quo 正面竞争且无差异。

P0 也不追求完整铺开所谓「100 个知识点」。这里的知识地图只表示后台有一套有限、可治理、可标注、可调度的章节/知识点/母题/采分点体系。前台不卖「100 知识点通关」，前台只告诉用户今天最该练什么、为什么丢分、下一题怎么补。

P0A 也不追求一次性重构完整五 Tab、完整章节地图、完整 30–40 母题包、完整 OCR 流量策略或完整会员体系。P0A 的目标只有一个：先用 2–3 个通过同一资格门的 Pack 微批，证明「今日任务 -> 作答 -> 批改 -> 证据 -> 错因复练 -> 复测」纵切闭环不依赖某一特殊 Pack，再扩到 3–5 个高频母题。

## 2. One Business Fact And Authority

### 2.1 One Business Fact

系统真正要维护的一等业务事实是：

每一次有效训练（知识点 / 母题 MCQ 轻练，或案例题批改）必须转化为可追溯的采分点级学习证据，并驱动盲点诊断、次日复测和明天的今日任务。

注：轻练 MCQ 与案例题批改写入的是同一份 `learning_evidence` 账本、同一套采分点 / 错因 authority，只是粒度与门槛不同——轻练是低门槛留存入口，案例题批改是深度护城河层。二者不得各自成为第二套 authority。

### 2.2 One Authority

该事实的 authority 分层如下：

- `construction_grading` / `CaseGradingSkillKernel` / 受控 rubric lane：负责采分点命中、证据、诊断、得分候选和批改风险。
- `learner_memory_events.learning_evidence`：作为学习证据账本，记录作答结果、采分点、错因、证据 span、下一步训练信号。
- `Learning Brain` / `LearnerStateService`：负责长期 learner truth、Stable Claim、PersonalizationContextPack、NextBestAction。
- `learning_report_read_model` / `attempt_detail_read_model` / `mistake_book_read_model` / `home_personalization`：作为前端只读投影。
- 小程序前端：只负责展示、交互、确认输入、触发动作和行为埋点，不自行推断分数、掌握度、下一任务或长期画像。

### 2.3 Competing Authorities To Avoid

不得新增或放任以下第二 authority：

- 前端自行计算 `score`、`mastery`、`risk`、`next action`。
- OCR raw text 自动替代学生确认稿。
- RAG 或知识地图直接参与评分裁决。
- 行为事件直接写 learner memory。
- 聊天入口绕过 `/api/v1/ws` 和 `QuestionLifecycleDecision`。
- `PRD/` 下旧文件继续与本文件并行定义目标 IA 或 P0 范围。

## 3. 产品主模式：混合自适应任务流

鲁班采用「结构化知识图谱驱动的混合自适应任务流」。这不是折中方案，而是前后台分工：

- 前台：今日任务驱动，用户看到下一步动作。
- 后台：章节/知识点/母题/采分点/错因/学习证据驱动，系统决定推荐与复练。
- AI 批改：不是孤立工具，而是整个系统的真凭据；每次批改都影响复盘排序和下一次任务推荐。
- AI 提问：随处可达的辅助入口，不能成为主 Tab，也不能让用户问完即走。

主链路：

```text
测 / 练 / 答
-> 评分与诊断
-> learning_evidence
-> Learning Brain
-> NextBestAction
-> 今日任务
-> 复测
```

## 4. 后台章节/知识点驱动层

章节/知识点驱动是本计划的核心组成，不是附录。

### 4.1 Canonical Structure

后台至少按以下层级建模：

```text
教材章节
-> 知识点
-> 高频母题
-> 采分点
-> 错因标签
-> training_task
-> 今日任务 / 错因复练 / 复测
```

建议核心对象：

- `knowledge_node`：教材章节、考点、规范节点。
- `case_family`：高频母题包，如工期索赔、质量验收、危大工程。
- `scoring_point`：采分点、关键词、程序、主体、依据、计算要点。
- `question_binding`：题目与章节/母题/采分点绑定。
- `mistake_tag`：稳定错因标签。
- `training_task`：具体训练任务。
- `learner_mastery` / read model projection：只读展示，不允许前端自算。
- `review_schedule`：复习和复测安排。

Phase 0 必须先冻结「新概念 ↔ 既有 authority」映射，未映射的概念不得进入实现：

| 新概念 | 既有 authority / 接缝 | P0A 处理 |
| --- | --- | --- |
| `training_task` | `training_intent`、assessment task、`NextBestAction` candidate | 不新建处方 authority；只作为前端任务投影和资产绑定 |
| `review_schedule` | `revalidation_queue`、mistake book review fields | 不另建复习队列；复测到期由既有队列或 read model 输出 |
| `learner_mastery` | `learning_evidence` -> Learning Brain / LearnerStateService -> read model | 前端只读；不得根据轻练点击或本地状态自算 |
| `priority_score` | `training_intent` / `NextBestAction` 候选排序解释层 | 只能排序、解释、降级，不取代处方权威 |
| `today_tasks` | `learning_report_read_model.today_tasks` / home personalization projection | P0A 可补独立 API，但 writer 仍来自后端 authority |
| `mistake_tag` | `learning_evidence` canonical payload + mistake book read model | schema 未冻结前只能展示，不写长期 learner truth |
| `task_scope` | grading/evidence payload 的本次训练覆盖范围 | 半写/轻练写 evidence 的前置条件 |

### 4.2 前台呈现原则

知识结构不得直接变成传统教材目录首页。正确呈现方式：

- 今日页展示「今天最该做的任务」和推荐原因。
- 练习页展示「系统推荐」「高频母题」「章节任务包」「真题/模考/冲刺」。
- 章节页展示本章最值钱的任务、高频采分点、最近错因、推荐训练，不展示复杂全量图谱。
- 知识地图/考点地图作为 P1 增强，必须只读后端 read model，不直接成为评分或掌握度 authority。

### 4.3 高频母题包范围

高频母题包分两层推进：

- P0A-0：准备 2–3 个同门槛 Pack 的「每日留存闭环」微批（今日任务 → 2 分钟 MCQ 轻练 → 选错即诊断 → 次日复测，验证回访）；treatment 默认 2 个，第 3 个只有在 A/A 自然流量与预注册样本门满足时进入，再扩到 3–5 个高频母题包。
- P0A-1：案例题渐进作答 / AI 批改 / 二次作答 / 错因写入的深度层；只在 P0A-0 留存信号、answer oracle、fact revocation、`task_scope` 与 grading gates 通过后纳入。
- P0B：在 P0A 闭环指标通过后，扩到 30-40 个高频案例母题包。

P0A 推荐顺序（v1.3 重心已从「先打案例题深度闭环」改为「先验证每日留存」）：

- Spike 1（P0A-0）：**每日提分留存闭环**。范围 = 今日任务卡 + 同一硬门槛下准备的 2–3 个 Pack 母题 MCQ 轻练（2 分钟可完成，treatment 默认 2 Pack）+ 当场盲点诊断（错选项映射采分点 / 教材章节）+「明天复测」开环 + 次日复测卡。目标不是把某一个案例题批改打深，而是用低门槛证明**忙碌成年人会连续几天回来，且效果不是某一 Pack 的偶然性**。
- 所有 Pack 共用同一资格、选题、判分、复测和埋点链。F16 只作普通候选和历史回归样例，不默认入选，不允许专属逻辑；任何 Pack 都按同一内容资格与流量门进入或退出 cohort。
- 案例题渐进作答 + AI 采分点批改深度层：作为留存闭环跑通后第二阶段解锁；扩展候选母题 F01 进度计划与关键线路、F02 工期索赔、F04 质量验收程序、F05 危大工程专项方案；F03 费用索赔作为备选，不在 Spike 1 阶段并行铺开。
- GO 门：钉在真实 D1/D7 回访留存（预注册目标值），不是闭环完成率或技术走通。

P0B 目标池，包含 P0A 已验证母题并继续扩展：

- F01 进度计划与关键线路
- F02 工期索赔
- F03 费用索赔
- F04 质量验收程序
- F05 危大工程专项方案
- F06 施工组织设计
- F07 施工总平面布置
- F08 基坑支护
- F09 降水与回灌
- F10 基坑验槽
- F11 模板工程
- F12 脚手架工程
- F13 钢筋工程
- F14 混凝土浇筑
- F15 大体积混凝土
- F16 防水工程
- F17 材料进场与复验
- F18 安全文明施工

每个母题包至少包含：对应章节、典型考法、核心采分点、常见错因、推荐训练模式、题目列表、最近训练结果、下一次复习时间。

### 4.4 资产生产线 Gate

章节/知识点/母题资产不是写在 PRD 里就算完成。每个可上线母题包必须经过资产生产线：

```text
官方真题 / 教材 / 规范 / 讲义来源
-> case_family 定义
-> scoring_point 拆解
-> mistake_tag 归类
-> question_binding
-> training_task 设计
-> 标注审核
-> shadow 批改回放
-> P0A/P0B 发布候选
```

每个母题包上线前必须具备：

- 来源清单和版本。
- 题目列表和题目难度。
- 采分点清单、每点给分依据、命中/部分命中/未命中规则。
- 常见错因标签与示例答案。
- P0A-0 只要求轻练 + 诊断 + 到期验证同构闭环；P0A-1 候选包才要求半写/实战至少一种深度训练模式，并具备 answer oracle、`task_scope` 与评分证据门。
- 对应 read model 字段和埋点。
- 资产 owner、reviewer、更新时间、回滚方式。

缺少来源、采分点或审核记录的母题包只能进入内部 mock，不得进入 P0A 真实闭环。

### 4.5 冷启动与断更调度

冷启动用户没有历史 evidence 时，今日任务来源按优先级：

1. 考试日期、每日可用时间、基础水平自评。
2. 3 分钟轻诊断。
3. 默认高频母题 P0A 入口。

断更用户不能展示补债式惩罚。系统应展示自动重排后的一个可完成任务，并把长任务降级为轻练或半写。

## 5. 移动端信息架构

目标信息架构唯一为 5 Tab。P0A-0 必须先完成底部导航与一级职责收权，但只改 Tab 归属、学习首页唯一 CTA 和必要深链，不借机全量重做所有二级页；P0B 再做视觉与能力扩面。

底部导航目标：

```text
学习 | 历史 | 问鲁班 | 学情 | 我的
```

禁止恢复独立复习 Tab，也不把历史变成成绩单/练习流水。

一级页面职责：

| 页面 | 用户问题 | 产品职责 |
| --- | --- | --- |
| 学习 | 我现在只该做什么？ | 唯一主任务；微课、Practice、错后确认和到期复测在同一任务路中切换 |
| 历史 | 我过去聊了什么，从哪里继续？ | 对话历史、搜索和继续对话；不混学习证据 |
| 问鲁班 | 我现在要问什么？ | TutorBot 实时对话和当前会话 |
| 学情 | 我最近进步了什么，下一个盲点是什么？ | 只留最近进步、当前 1–3 个盲点、唯一下一步；证据不足显示 `insufficient_evidence` |
| 我的 | 账户和权益是什么？ | 会员、偏好、考试信息、客服、隐私 |

## 6. 首页「今日」要求

今日页是学习调度台，不是功能大厅。

首屏必须回答四个问题：

1. 距离考试还有多久。
2. 今天最该做什么。
3. 为什么推荐这件事。
4. 做完能补哪类分。

首屏驾驶舱结构：

```text
顶部状态：距考试 / 今日可用时间
唯一主任务卡：任务 + 推荐原因 + 预计收益
唯一主 CTA：开始 / 继续 / 到期验证（三者只出现其一）
完成后回执：本次补了什么 / 为什么丢分 / 明天验证什么
底部导航
```

到期复测、未闭合 Practice、推荐微课与断更恢复只竞争同一个主任务位；轻练、半写、拍照批改、薄弱点和最近批改不得在首屏形成并列 CTA，后续深度能力统一藏到任务完成后的下一步或二级页。

首页验收：

- 用户 5 秒内能说出今天该做什么。
- 首屏只有一个最强 CTA。
- 主任务必须有推荐原因。
- 断更用户看到自动重排，不看到补债式惩罚。
- 新用户能进入 3 分钟轻诊断。
- 批改高风险用户能看到先校对或复核建议。

## 7. 练习中心要求

练习页不是传统题库目录，而是主动训练入口。

结构：

```text
系统推荐
-> 高频母题
-> 章节任务包
-> 真题 / 模考 / 冲刺
```

高频母题是 P0 核心入口。章节/知识点是后台调度和 P0/P1 二级入口，不得让用户从第一屏开始逛全书目录。

`CaseFamilyCard` 至少展示：

- 母题名称
- 高频程度
- 用户风险
- 掌握状态
- 最近错因
- 推荐模式
- 开始训练 CTA

章节任务包展示：

- 本章最值钱的 3 个任务。
- 本章高频采分点。
- 本章最近错因。
- 本章推荐训练。

### 7.1 任务推荐公式

今日任务不按章节顺序推，而按预期收益排序。P0A 可先用可解释规则，P1 再进入更复杂的 Learning Brain 策略优化。

硬约束：`priority_score` 不是新的处方 authority。今日任务候选必须来自 `training_intent` / `NextBestAction` / `learning_report_read_model` 这条后端 authority 链；`priority_score` 只能在候选集合内做排序、解释、降级和成本控制。现有 `note_assets today_tasks` 只能作为兼容投影或冷启动输入，不能与 `training_intent` 并行成为第二套推荐真相。

P0A 推荐分：

```text
priority_score =
  exam_weight * 0.30
+ learner_weakness * 0.30
+ repeated_mistake * 0.20
+ exam_urgency * 0.10
+ review_due * 0.10
- duration_penalty
- cost_penalty
```

输出约束：

- 首屏 `primary_task` 恰好 1 个、主 CTA 恰好 1 个；到期复测、未闭合 Practice、推荐微课和断更恢复按 authority 优先级竞争该位置。
- 不输出并列“微复习”或“可选任务”；次级能力进入任务完成后的下一步或二级页。
- 快速提问只由底部「问鲁班」Tab 承载，不在学习首屏与主任务争抢注意力。

推荐必须解释给用户看，但不暴露复杂公式。推荐原因应来自已存在的学习证据、错因、到期复习或冷启动诊断，不得用前端本地状态臆造。

跳过/换任务反馈也要入行为系统：用户跳过、改选 5 分钟轻练、连续不完成、完成后立即退出，都应作为推荐策略的观察信号；这些行为信号不能直接写 learner memory。

进入开发前必须补齐今日任务 authority 决策记录：候选由谁生成、排序由谁执行、跳过反馈写到哪里、哪些字段只是 read model projection。没有这张记录，不允许新增独立 `today task engine`。

## 8. 案例题渐进作答

移动端不能默认要求用户长篇打字。以下是能力阶梯，不是 P0A-0 同期发布清单：

| 模式 | 场景 | 输入方式 | 目标 |
| --- | --- | --- | --- |
| 轻练 5 分钟 | 通勤、午休、断更恢复 | 选择、排序、匹配、填空 | 审题、采分点识别、流程和主体 |
| 半写 15 分钟 | 日常主训练 | 句子积木、短句补全 | 得分语言、答题结构、采分词 |
| 实战 30 分钟 | 周末、考前、周测 | 纸笔手写 + OCR | 真实考试输出 |
| 拍照批改 | 已有手写答案 | OCR + 校对 + 批改 | 诊断真实答案 |

P0A-0 轻练题型收敛为单选/多选和案例小问；排序、匹配、填空进入 P0B。P0A-1 半写只能覆盖明确的 `covered_scoring_point_ids`，范围外采分点不得被写成 miss evidence。

默认策略：

- P0A-0 新用户：完成 5 题轻练 -> 诊断 -> 有安全题才当场确认 -> D+1 验证。
- P0A-1 新用户（深度层解锁后）：轻练 1 题 -> 半写 1 题；拍照诊断仍为受控入口。
- P0A-1 老用户日常：半写。
- 长时间未学习：轻练。
- 考前冲刺：提高实战比例。
- 用户已有答案：拍照批改。
- OCR 成本超预算：引导轻练/半写。

## 9. AI 批改结果页

AI 批改结果页是王牌页面，必须采用「先诊断、再证据、再重做」。

结构：

```text
得分总览：预计得分区间 / 可靠度 / 高风险提示
最该改的 3 个问题
采分点命中清单
原文证据链
改写建议
二次作答 CTA
同类题推荐
标准答案折叠
错题加入
用户反馈
```

分数文案：

- 未进入 governed official mode 时，写「预计 11-13 / 20，可靠度中」。
- 不写「精准打分」。
- 高风险时写清不确定原因。

采分点状态：

- `hit`：表述到位。
- `partial`：方向对，但缺关键词、依据、主体或措施。
- `miss`：未写到该采分点。
- `uncertain`：OCR 或语义不确定。
- `needs_review`：高风险批改，建议复核。

标准答案默认折叠。结果页底部固定双 CTA：

- 再答一次这道题。
- 练一道同类题。

## 10. OCR 与拍照批改边界

OCR 是输入层，不是产品核心，也不是学习事实 authority。

链路必须是：

```text
raw_ocr_text
-> 用户确认 / suspicion span 校对
-> confirmed_text
-> grading
-> learning_evidence
```

规则：

- 高置信全文快速确认。
- 低置信片段局部校对。
- 严重低质要求重拍。
- OCR raw text 不直接送批改。
- OCR 层不写 learner memory。
- 低质量图片先提示重拍，避免无效成本。
- OCR provenance、confirmed_text、attempt_id 和 grading result 不能形成闭环前，photo 路径只能作为 preview / diagnostic，不允许写长期 learner truth。

成本规则：

- 轻练不调用 OCR。
- 半写默认不调用 OCR。
- OCR 只在实战、拍照批改、首次诊断赠送或考前模拟中触发。
- OCR 调用前检查权益和单用户成本软顶。
- 图片质量差先提示重拍，不进入 OCR。
- 单次 OCR 成本、单次批改成本、单用户日均推理成本必须可统计。

OCR 校对 UX Gate：

- 高置信全文一键确认。
- 低置信片段必须高亮 suspicion span。
- 平均校对目标不超过 30 秒。
- 用户可以手动修正 confirmed_text。
- 用户放弃校对时，不进入批改和 learning_evidence。

### 10.1 人工复核触发

人工复核不是 P0A 必做完整后台，但 P0A 必须预留触发条件和用户提示。

触发条件：

- OCR 低置信区域过多。
- 批改 confidence 为 low。
- 命中高风险采分点，例如计算、程序顺序、主体责任明显冲突。
- 用户反馈「批改不准」且关联高价值母题。
- 分数区间跨度过大，无法给出稳定诊断。

P0A 处理方式：

- 用户侧展示「建议复核」或「当前为预估诊断」。
- 后台记录 review_candidate，不直接覆盖评分结果。
- 复核结果只有通过既有 grading / learning_evidence authority 写回，不能由人工后台直接改 learner truth。

P1 再定义完整复核队列、SLA、复核结果回流 rubric/mistake_tag 的流程。

## 11. 错题与学情

> 2026-07-16 IA 收权：错题、到期验证与考点回炉都进入「学习」内的任务状态，不再形成独立复习模块；调度 / 到期 / 掌握态的唯一真值仍是 `revalidation_queue`（`mistake_book` 自建 due 日期已收权修复）。[双轮设计 v3](2026-07-02-luban-learn-review-double-wheel-design.md) 只保留机制参考。本节“复盘中心非收藏夹、关闭靠客观复测”的原则不变。

错题本不是错题收藏夹，而是错误模式复盘中心。

一级分类：

- 按错因
- 按采分点
- 按母题
- 按章节
- 待复习
- 已掌握

错因不能靠用户手动「已掌握」直接写 canonical mastery。关闭条件建议：

- 同一错因下连续 2 次同类题未再出现；或
- 真实复测通过。

学情报告像医生诊断单，不像 BI 大屏。首页只展示轻量诊断卡，完整报告 P1/P2 扩展。报告必须落到下一步任务，不能停在描述性图表。

### 11.1 数据与隐私入口

「我的」页必须保留数据与隐私控制，不得只做会员和客服：

- 清除上传图片。
- 导出学习记录。
- 查看 OCR / 批改使用记录。
- 反馈批改问题。
- 管理考试日期、每日可用时间、学习偏好。

隐私边界：

- 上传图片和 raw OCR 属于输入证据，不等同长期 learner truth。
- 用户删除上传图片后，不应删除已确认答案产生的合规学习证据，但应断开图片原件展示和后续人工查看。
- 学习记录导出应来自 read model / evidence projection，不从前端拼装。
- 免费/付费权益展示不能诱导用户把 OCR 当成主要学习方式。

### 11.2 失败态与恢复

P0A 必须设计以下失败态，不允许只做 happy path：

| 失败态 | 用户侧处理 | authority 处理 |
| --- | --- | --- |
| 网络失败 | 保留本地草稿，提示重试 | 不写 attempt 完成事件 |
| OCR 失败 | 可重拍、手动输入或放弃 | 不进入 grading |
| 批改超时 | 展示排队/重试，避免重复扣权益 | attempt 保持 pending / failed |
| 题目缺失 | 返回任务列表并记录问题 | 不生成 learning_evidence |
| 用户未登录 | 引导登录或 QA token | 不写 canonical learner truth |
| 权益不足 | 展示可用低成本模式 | 不触发高成本 OCR / grading |
| 图片质量差 | 先提示重拍 | 不调用 OCR |
| 批改高风险 | 展示预估诊断/建议复核 | 不提升 stable claim |

失败态验收标准：任何失败都不能产生伪完成、伪掌握、伪复测通过或重复扣费。

## 12. ViewModel 输入草案

本节只保留产品级输入草案。P0A 唯一 ViewModel 与事件 authority 是 [2026-06-11-luban-mobile-p0a-viewmodel-and-event-contract.md](2026-06-11-luban-mobile-p0a-viewmodel-and-event-contract.md)；如本节与该文件不一致，以专项 contract 为准，PRD 不再并行定义字段真相。

### 12.1 HomeDashboardViewModel

```ts
type HomeDashboardViewModel = {
  user_id: string
  exam_countdown_days?: number
  weekly_progress: {
    completed_days: number
    target_days: number
    completed_tasks: number
    target_tasks: number
  }
  today_minutes: number
  main_task?: TodayMainTaskCard
  quick_actions: QuickAction[]
  risk_summary: RiskSummary
  last_grading_summary?: LastGradingSummary
  due_reviews: DueReview[]
  state: "new_user" | "normal" | "interrupted" | "sprint" | "no_task" | "error"
}
```

### 12.2 TodayMainTaskCard

```ts
type TodayMainTaskCard = {
  task_id: string
  title: string
  subtitle: string
  task_type: "light_practice" | "semi_write" | "photo_grading" | "retest" | "mistake_review"
  estimated_minutes: 5 | 15 | 30 | 60
  reason: string
  linked_case_family?: string
  linked_mistake_tag?: string
  linked_scoring_point?: string
  priority_label: "最该做" | "高收益" | "到期复习" | "考前冲刺"
  primary_cta: string
  secondary_cta?: string
}
```

### 12.3 CaseTrainingSessionViewModel

```ts
type CaseTrainingSessionViewModel = {
  session_id: string
  question_id: string
  case_family_id: string
  title: string
  stem: string
  recommended_mode: "light" | "semi_write" | "real_exam" | "photo_grading"
  available_modes: TrainingMode[]
  steps: TrainingStep[]
  task_scope: {
    scope_type: "full_question" | "scoring_point_subset" | "light_check" | "preview"
    covered_scoring_point_ids: string[]
    excluded_scoring_point_policy: "not_evaluated_no_miss"
    evidence_weight: "official" | "diagnostic" | "light_signal" | "none"
  }
  estimated_minutes: number
  source: "today_task" | "practice" | "mistake_book" | "assessment"
}
```

### 12.4 GradingResultViewModel

```ts
type GradingResultViewModel = {
  attempt_id: string
  question_id: string
  mode: "official_grading" | "diagnostic" | "preview"
  score_display: {
    type: "exact" | "range" | "none"
    exact_score?: number
    min_score?: number
    max_score?: number
    total_score?: number
  }
  confidence: "high" | "medium" | "low"
  task_scope: {
    scope_type: "full_question" | "scoring_point_subset" | "light_check" | "preview"
    covered_scoring_point_ids: string[]
    out_of_scope_policy: "not_evaluated_no_miss"
    evidence_weight: "official" | "diagnostic" | "light_signal" | "none"
  }
  high_risk?: {
    level: "yellow" | "red"
    reasons: string[]
  }
  top_issues: TopIssue[]
  scoring_points: ScoringPointResult[]
  evidence_blocks: EvidenceBlock[]
  rewrite_suggestions: RewriteSuggestion[]
  standard_answer?: {
    folded_by_default: true
    content: string
  }
  next_actions: NextAction[]
  feedback_options: FeedbackOption[]
}
```

### 12.5 MistakeBookItem

```ts
type MistakeBookItem = {
  mistake_id: string
  mistake_tag: {
    id: string
    label: string
    taxonomy_version: string
  }
  case_family_id: string
  scoring_point_id?: string
  knowledge_node_id?: string
  repeated_count: number
  last_seen_at: string
  severity: "high" | "medium" | "low"
  status: "active" | "improving" | "stable" | "closed"
  next_review_at?: string
  recommended_action: NextAction
}
```

这些是产品输入草案，不自动升级为 stable API contract。正式开发前必须与专项 ViewModel/event contract、现有 API/read model 对齐；若新增 `learning_evidence` canonical 字段或修改 protected contract，必须同步 `contracts/index.yaml` 的 domain test_files。

### 12.6 视觉与组件契约

P0 视觉关键词：

- 专业。
- 克制。
- 可信。
- 高效。
- 诊断感。
- 冲刺感。
- 少娱乐化。
- 少炫技。

设计原则：

- 首屏只突出一个主任务。
- 卡片只用于任务、母题、证据、错因等可操作对象，不把页面区块都做成浮动卡片。
- 关键 CTA 固定底部并避开安全区。
- 结果页长内容分段折叠。
- 支持大字号模式，证据链文字不小于 14px。
- 命中、部分命中、不确定、未命中、高风险必须有稳定颜色和文案。
- 不用单色科技风或游戏闯关风；鲁班更像诊断工具和提分教练。

P0 组件库至少统一：

- `TaskCard`
- `RiskBadge`
- `ConfidenceBadge`
- `CaseFamilyCard`
- `ScoringPointRow`
- `MistakeTagChip`
- `EvidenceBlock`
- `RewriteSuggestionCard`
- `ModeSelector`
- `PhotoQualityWarning`
- `OcrSuspicionSpan`
- `StickyBottomCTA`
- `EmptyState`
- `LoadingSkeleton`
- `HighRiskBanner`

组件验收：同一个状态不能在不同页面出现不同语义，例如 `partial` 不能一处叫「差一点」，另一处叫「基本命中」；高风险也不能一处允许写 evidence，另一处阻止写 evidence。

## 13. 关键埋点

P0 至少记录下列事件族，正式事件名以 [2026-06-11-luban-mobile-p0a-viewmodel-and-event-contract.md](2026-06-11-luban-mobile-p0a-viewmodel-and-event-contract.md) 为唯一 authority，统一使用 `mobile_p0a_*` 前缀，不再并行维护 `home_view` / `main_task_start` 这类旧草案名：

- `mobile_p0a_home_viewed`
- `mobile_p0a_main_task_impressed`
- `mobile_p0a_main_task_started`
- `mobile_p0a_quick_action_clicked`
- `mobile_p0a_training_mode_selected`
- `mobile_p0a_light_step_completed`
- `mobile_p0a_semi_write_step_completed`
- `mobile_p0a_photo_upload_started`
- `mobile_p0a_photo_quality_failed`
- `mobile_p0a_ocr_requested`
- `mobile_p0a_ocr_confirmed`
- `mobile_p0a_grading_result_viewed`
- `mobile_p0a_scoring_point_expanded`
- `mobile_p0a_rewrite_suggestion_viewed`
- `mobile_p0a_second_attempt_started`
- `mobile_p0a_similar_question_started`
- `mobile_p0a_mistake_added`
- `mobile_p0a_mistake_review_started`
- `mobile_p0a_mistake_closed`
- `mobile_p0a_ai_feedback_submitted`
- `mobile_p0a_plan_reordered`

行为事件只进入产品行为系统，不直接写 learner memory。

### 13.1 P0 指标

产品结果指标：

- 今日主任务开始率。
- 今日主任务完成率。
- 批改结果页二次作答点击率。
- 同类题推荐点击率。
- 错因复练完成率。
- 复测通过率。
- 7 日内回访率。

质量指标：

- 用户认为批改准确比例。
- 低置信 OCR 触发率。
- 用户纠错率。
- 高风险批改比例。
- 人工复核命中问题比例。
- `uncertain` / `needs_review` 状态占比。

成本指标：

- 单次 OCR 成本。
- 单次 AI 批改成本。
- 单用户日均推理成本。
- 免费用户成本上限。
- 会员毛利率。

P0A 不用追求所有指标显著提升，但必须证明数据可采、口径唯一、能按 `case_family` / task type / entry flow 分层查看。

## 14. P0 / P1 / P2

### P0A: 两级纵切，不把深度层绑死在留存首发

P0A 是第一实施批次，目标是证明闭环，而不是证明资产规模。

P0A-0（当前首发，Practice retention slice）范围：

- 5 Tab 一级职责收权：`学习 / 历史 / 问鲁班 / 学情 / 我的`，不做二级页全量重构。
- 学习首页 1 个 `primary_task` + 1 个主 CTA；复测、未闭合 Practice 与推荐微课竞争同一位置。
- 准备 2–3 个同门槛 Pack 切片，treatment 默认 2 个；第 3 个仅在自然流量与样本门满足时进入。
- 视频后 5 题轻练（单选/多选/案例小问）→ 错项诊断 → 有安全题才当场确认 → D+1 同 fact 验证。
- exact H5 receipt、服务端重判、canonical terminal、同 probe 多端原子幂等和一次复测 readback。
- 真实微信入口至少完成一个核心 entry flow；OCR、半写、完整作答、AI 批改不在 P0A-0 发布范围。

P0A-0 验收：

- 新老用户都能在 5 秒内看见唯一任务，并在 2–5 分钟完成 5 题、可信诊断和回执。
- 用户能在 D+1 由同一学习任务位进入到期验证，并读回前序 fact/probe 状态。
- 所见 exact items 与服务端重判、terminal 引用和 learner evidence 100% 对齐；前端不自算 score/mastery/next action。
- 所有 Pack 走同一路由与资格门；F16 不享有默认入口、schema、签发、学情或埋点特权。
- 行为事件不写 learner memory；诊断若无 canonical `mistake_tag` 映射，只展示，不写长期 truth。

P0A-1（留存后解锁的深度层）范围与验收：

- 半写 15 分钟、完整作答、1 个 AI 批改结果页、二次作答和错因复练；OCR 只做受控 preview 或小样本诊断。
- 新用户可从轻练进入半写；老用户可完成批改并看到 1–3 个主要问题和采分点证据。
- 批改结果经 canonical grading/evidence authority 回到错因与下一任务，同类复练和二次作答可闭环。
- 半写 evidence 必须带 `task_scope`、`covered_scoring_point_ids` 和 `evidence_weight`；范围外采分点不得写成 miss。
- answer oracle、fact revocation、`mistake_tag` schema、Trust、Cost/SLA 与 grading gates 未通过时，P0A-1 保持关闭，不反向阻断 P0A-0。

### P0B: 扩展与入口完善

P0B 在 P0A 通过后启动，目标是扩母题、补入口、做灰度。

范围：

- 今日页：今日主任务、倒计时、最近批改、薄弱点、断更重排。
- 高频母题：P0B 目标为 30-40 个母题包。
- 轻练模式：多选、排序、匹配、填空。
- 半写模式：句子积木、短句补全。
- AI 批改页：得分区间、3 个问题、采分点证据链、错因标签。
- 错题本：按错因、采分点、母题、复习时间组织。
- 今日任务候选投影：根据既有 `training_intent` / `NextBestAction` 候选,结合错因、采分点和复习到期做展示与解释。
- OCR 实战：受控场景，不默认高频。
- 二次作答与同类题推荐：批改后必须有。
- 真实微信入口覆盖今日、练习、批改、错题四条主路径。

### P1

- 完整章节地图 / 考点地图。
- 模考系统。
- 人工复核。
- 高级学情报告。
- 冲刺 7 天任务包。
- 更复杂 OCR 路由。
- 会员权益分层。
- 行为 BI 运营分群。

### P2

- 语音输入。
- 完整自由问答老师。
- 复杂知识图谱可视化。
- 社群督学。
- 老师后台。
- 多专业扩展。

## 15. 实施阶段

推荐发布顺序：

```text
Phase 0: authority / inventory / asset gate
-> Phase 1: P0A ViewModel + component contract
-> Phase 2: P0A today task + light/semi-write
-> Phase 3: P0A grading result + learning evidence + mistake review
-> Phase 4: P0A retest readback + decision package
-> Phase 5: P0B expansion + true WeChat gray release
```

### Phase 0: 现状盘点与 authority 冻结

产物：

- 当前页面清单。
- 当前 API / read model 清单。
- 当前小程序入口清单。
- 小程序开发树 source of truth 决策：`wx_miniprogram` 与 `yousenwebview/packageDeeptutor` 的职责、同步机制、最新上传源证据。
- 当前批改链路清单。
- 当前错题 / 学情数据来源。
- 新概念到既有 authority 映射表。
- `task_scope` evidence 规则。
- `mistake_tag` canonical schema 前置任务与 contract 影响清单。
- 可复用组件清单。
- 废弃页面清单。
- P0A-0 首批 2–3 Pack 切片资产清单和扩展候选资产清单。
- P0A release gate owner 清单。

验收：知道哪些页面保留、下线、迁移；哪些 API 复用；哪些 read model 需补。

### Phase 1: Design System And ViewModel

产物：

- Design Tokens。
- P0 组件库。
- `HomeDashboardViewModel`。
- `CaseTrainingSessionViewModel`。
- `GradingResultViewModel`。
- `MistakeBookViewModel`。
- `PhotoAnswerSessionViewModel`。

验收：不用真实后端，也能用 mock 跑完整主流程。

### Phase 2: 今日页与任务入口

上线今日页、主任务卡、最近批改卡、薄弱点诊断卡、快速操作区和任务重排状态。

验收：新用户、老用户、断更用户、冲刺用户都有合理首页状态。

### Phase 3: 案例题渐进作答

上线轻练、半写、实战、拍照批改四模式的 P0 版本。

验收：用户不用手机长篇打字，也能完成一次有诊断价值的案例题训练。

### Phase 4: AI 批改结果页与错因闭环

上线采分点证据链、改写建议、二次作答、同类题推荐、错题加入。

验收：批改结果能产生学习证据，且能驱动下一任务。

### Phase 5: P0B 扩展与真微信入口灰度

P0A decision package 达到 GO 或受控 WEAK-GO 后，才能扩展到更多母题包、更多入口和更大灰度。

验收必须区分：

- `devtools_project_root = yousenwebview`
- `target_subpackage = packageDeeptutor`
- `target_page = 具体页面`
- `entry_flow = 具体动作链路`
- `auth_state = logged_in / qa_token / auth_blocked / unknown`
- `auth_mode = real_wechat / local_dev_wechat / manual_token / none`

`/wechat-harness` 只能算 shadow QA，不能替代真实微信入口 closure。

### 15.1 Release Gates

P0A 不满足以下 gate，不得进入真实用户灰度。

适用性：Frontend、Asset、P0A-0 UX、Authority、Authorization、WeChat、Rollback、Decision Sample 是 P0A-0 硬门；Trust、Cost/SLA、Task Scope、Mistake Tag 与深度 UX 是 P0A-1 追加门。P0A-1 未就绪不得反向卡住 P0A-0。

| Gate | 必须证明 | 不通过时 |
| --- | --- | --- |
| Frontend Source Tree Gate | 开发 source of truth、同步机制、最近一次上传源、真实验收目标一致；`wx_miniprogram` 与 `yousenwebview/packageDeeptutor` 不得漂移 | 阻断开发或验收，只能算 partial |
| Asset Gate | 首批每个 Pack 切片的已发集合均完整；所有 Pack 使用同一来源、答案、诊断、题目绑定、owner/reviewer 门槛 | 只移出未达标 Pack，合格 Pack 可继续 internal QA |
| UX Gate | P0A-0：首页 5 秒知道唯一任务、无独立复习、轻练 ≤5 分钟；P0A-1：半写 ≤15 分钟、批改首屏能说出 1-3 个问题、二次作答 CTA 可见 | 只阻断未满足的对应阶段 |
| Trust Gate | 分数区间/置信度/高风险/uncertain/needs_review 文案完整；标准答案默认折叠 | 不允许宣称批改可用 |
| Cost/SLA Gate | 轻练不调 OCR；OCR 只在受控路径；单次 OCR/批改成本可统计；AI 批改 P50/P95 和免费用户日成本上限有预算与实测 | 降级到轻练/半写或异步结果 |
| Authority Gate | 前端不算分、不写 learner truth；OCR raw 不批改；行为事件不写 learner memory；RAG/知识图谱不判分；`priority_score` 不取代 `training_intent`/`NextBestAction` | 阻断发布 |
| Task Scope Evidence Gate | P0A-1 半写 evidence 有 `task_scope`、`covered_scoring_point_ids`、`evidence_weight`；范围外点不写 miss | 阻断 P0A-1 半写写入，不阻断 P0A-0 terminal |
| Mistake Tag Schema Gate | P0A-1 长期错因写入所需 `mistake_tag` canonical 字段、taxonomy version、payload builder、readback、contract tests 明确 | 错因只展示，不写长期 truth；不阻断 P0A-0 |
| Authorization Gate | QA/operator、test user、真实白名单用户的 learning_evidence 写入门与既有 governed promotion 授权一致 | 阻断真实用户写入 |
| WeChat Gate | `yousenwebview` project root + `packageDeeptutor` target page + entry_flow + auth_state/auth_mode 均有证据 | 只能算 shadow pass |
| Rollback Gate | 有 feature flag、灰度 cohort、数据写入保护、回滚路径和用户可见降级文案 | 不进入真实用户 |
| Decision Sample Gate | GO 至少有预注册样本量：≥20 名灰度用户、≥100 次有效 attempt、≥30 次错因复练/复测进入 | 样本不足只能 WEAK-GO 或继续灰度 |

P0B 额外 gate：

- 30-40 母题资产中每个包都能追踪到 source / owner / version。
- 今日任务推荐能按 `case_family`、错因、复习到期和考试紧迫度解释。
- 关键指标可按 cohort、entry_flow、case_family 分层。
- OCR / AI 成本与会员权益可以闭环核算。

### 15.2 灰度与回滚

灰度策略：

- 先 QA / operator cohort。
- 再小比例 test user。
- 再 P0A 真实用户白名单。
- P0B 扩量前必须出 P0A decision package。

回滚要求：

- 可以关闭今日任务新入口，回到旧入口或保守任务列表。
- 可以关闭 OCR photo path，保留轻练/半写。
- 可以关闭 writing to learning_evidence 的新字段，但不能破坏既有 evidence ledger。
- 可以把高风险批改降级为 preview，不写 stable claim。
- 可以按 case_family 下线单个母题包。

### 15.3 P0A Decision Package

P0A 结束时必须产出决策包，不得只凭主观体验扩面。

决策包至少包含：

- 已覆盖母题包列表。
- 核心 entry flow 证据。
- learning_evidence 写入与 readback 证据。
- 错因复练与复测证据。
- UX 指标与用户反馈。
- 批改可信度和高风险样本。
- OCR / AI 成本样本。
- WeChat true-entry 证据或 pending 风险。
- GO / WEAK-GO / NO-GO 结论。

### 15.4 P0A Test Diagram

P0A 实施计划必须把以下测试图拆成可执行测试，不能只靠人工点页面。

```text
HomeDashboardViewModel
-> TodayMainTaskCard
-> CaseTrainingSessionViewModel
-> user answer / confirmed_text
-> GradingResultViewModel
-> learning_evidence
-> mistake_book_read_model
-> next task / retest readback
```

最低测试面：

- ViewModel contract tests：今日页、训练页、批改结果页、错题项字段完整且状态枚举稳定。
- Authority tests：前端无 score/mastery/next action 自算；OCR raw 不进入 grading；行为事件不写 learner memory。
- Grading-to-Brain tests：批改结果能产生 learning_evidence，错因/采分点能被 read model 读回。
- Task recommendation tests：冷启动、正常用户、断更用户、冲刺用户均能生成一个主任务，并解释推荐原因。
- Failure-state tests：网络失败、OCR 失败、批改超时、权益不足、图片质量差、高风险批改都不产生伪完成。
- Cost tests：轻练不触发 OCR；OCR 调用可计费、可追踪、可降级。
- WeChat true-entry smoke：`yousenwebview` project root + `packageDeeptutor` target page + 具体 entry_flow + auth_state/auth_mode。

### 15.5 P0A Visual Review Gate

进入前端实现前，至少需要以下核心屏幕的视觉稿或等价高保真 mock：

- 今日页首屏。
- 轻练训练页。
- 半写训练页。
- AI 批改结果页。
- OCR 确认页。
- 错因复练入口。
- 我的页数据与隐私入口。

视觉验收按 7 个维度：

- 信息层级：5 秒内看懂今天做什么。
- 状态覆盖：loading / empty / error / partial / success / high-risk。
- 用户情绪：断更不惩罚，高风险不恐吓，低置信不装准。
- 具体性：不能是通用 AI 卡片、营销 hero 或功能宫格。
- 设计系统：组件、颜色、状态文案一致。
- 移动适配：至少覆盖 375px、390px、430px 宽度和大字号。
- 反 AI-slop：不用无意义渐变、装饰性大卡、抽象科技图、聊天框首页。

## 16. 性能与体验标准

- 首页首屏 1.5 秒内可见骨架屏，3 秒内可操作。
- 练习页 2 秒内加载主要卡片。
- 训练步骤切换 300ms 内响应。
- OCR 上传立即显示进度。
- 批改等待必须展示阶段，不允许空转。
- 结果页可以先返回摘要，再补充证据链。

批改等待阶段文案：

- 正在识别答案。
- 正在匹配采分点。
- 正在生成诊断。
- 正在整理改写建议。

## 17. 商业化原则

不按题收费，不按答案解锁收费，不把 OCR 单次消费做成主心智。

推荐套餐：

- 7 天诊断包。
- 30 天实务提分包。
- 考前冲刺包。
- 高风险人工复核包。

付费触发优先发生在：

- 首次完整批改后。
- 二次作答后看到进步时。
- 错因报告生成后。
- 考前冲刺任务包生成后。
- 高风险批改需要人工复核时。

## 18. 后续计划硬门槛

后续任何移动端功能、页面、API、原型或实施计划，都必须回答：

1. 是否服务今日任务？
2. 是否提高案例题输出能力？
3. 是否产生采分点级学习证据？
4. 是否能进入错因复练？
5. 是否降低手机端输入负担？
6. 是否避免高频 OCR 成本失控？
7. 是否导向二次作答或同类题训练？
8. 是否保持现有 authority 边界？

回答不清楚的功能，不进入 P0。

## 19. 收益、风险与执行判断

结论：

- 一次性做「完整大重构」：风险大于收益。
- 按 P0A 纵切闭环推进：收益明显大于风险。
- P0A 过 gate 后再扩 P0B：收益最大、风险可控。

主要收益：

- 把鲁班从功能集合升级为提分闭环，形成更清晰的用户心智。
- 把 AI 批改结果变成可追溯 learning_evidence，而不是一次性答案消费。
- 用今日任务降低成人考证用户的决策成本。
- 用轻练/半写降低手机端案例题输入门槛。
- 用错因复练和复测证明进步，增强留存和付费理由。

主要风险：

- 母题/采分点/错因资产生产不足，导致今日任务和批改结果空心化。
- 批改可信度不足或高风险状态不清，伤害用户信任。
- OCR 成本和错误污染批改链路。
- 前端为了快而自算掌握度/下一任务，制造第二套 truth。
- 一次性重构五 Tab 与 30-40 母题，导致工程和资产都失控。
- 没有真实微信入口验证，把 shadow pass 误当上线通过。

风险控制策略：

- 先 P0A 2–3 Pack 同门槛微批，再扩到 3–5 母题纵切，不做全量重构，不指定任何 Pack 为永久特权样板。
- 所有批改写回都必须走既有 grading / learning_evidence / Learning Brain authority。
- OCR 低频、受控、可降级。
- 每个 release 都有 Asset / UX / Trust / Cost / Authority / WeChat / Rollback gate。
- P0A 必须产出 GO / WEAK-GO / NO-GO decision package 后再扩 P0B。

## 20. 仍需产品负责人拍板的问题

当前不阻塞 v1.2 PRD 完善，但进入 P0A 实施前需要明确：

1. P0A-0 首个 spike 已定为「每日提分留存闭环」（v1.3，依据内测真实行为数据 + 已确认前提 B）；2026-07-16 产品负责人取消 F16 默认优先，改为同一资格门下准备 2–3 个候选 Pack、treatment 默认 2 个且第 3 个由真实流量门决定。案例题批改属于 P0A-1 深度层。
2. P0A 是否允许 photo/OCR 写入真实 learning_evidence；默认建议不允许，先 preview / diagnostic，待 OCR provenance gate 通过后再写。
3. P0A 的商业化是否完全关闭，只做内测体验，还是允许首次完整批改后出现轻量付费提示。
4. 人工复核在 P0A 是只记录 review_candidate，还是需要最小运营后台。
5. P0A 灰度对象是 QA/operator cohort、内测用户，还是可开放给真实付费用户白名单。
6. 「我的」页隐私能力 P0A 是否必须上线清除上传图片和导出学习记录，还是 P0B 上线。

默认建议：P0A-0 不做商业化强转化、不做完整人工复核后台、不让 OCR photo path 写长期 truth；优先把唯一今日任务、视频 Practice、可信诊断、当场确认和 D+1 readback 做实。半写、AI 批改、二次作答与错因长期写入按 P0A-1 独立验收，不与首发捆绑。

## 21. Related Plans

本文件派生以下 P0A 执行文档。它们只拆解执行、资产、设计、发布和决策材料，不重新定义产品主目标：

- [2026-06-11-luban-mobile-scoring-loop-p0a-execution-plan.md](2026-06-11-luban-mobile-scoring-loop-p0a-execution-plan.md)
- [2026-06-11-luban-mobile-case-family-asset-production-plan.md](2026-06-11-luban-mobile-case-family-asset-production-plan.md)
- [2026-06-11-luban-mobile-ui-ux-design-system-and-screen-spec.md](2026-06-11-luban-mobile-ui-ux-design-system-and-screen-spec.md)
- [2026-06-11-luban-mobile-p0a-viewmodel-and-event-contract.md](2026-06-11-luban-mobile-p0a-viewmodel-and-event-contract.md)
- [2026-06-11-luban-mobile-p0a-scenario-risk-hardening-review.md](2026-06-11-luban-mobile-p0a-scenario-risk-hardening-review.md)
- [2026-06-11-luban-mobile-p0a-release-gate-checklist.md](2026-06-11-luban-mobile-p0a-release-gate-checklist.md)
- [2026-06-11-luban-mobile-p0a-decision-package-template.md](2026-06-11-luban-mobile-p0a-decision-package-template.md)

本计划协调但不替代以下已有计划：

- [2026-06-04-luban-grading-engine-master-control-plan.md](../总控入口与当前作战图/2026-06-04-luban-grading-engine-master-control-plan.md)
- [2026-06-09-learner-memory-lifecycle-execution-plan.md](../学习脑与学员记忆/2026-06-09-learner-memory-lifecycle-execution-plan.md)
- [2026-05-20-luban-learning-report-read-model-execution-plan.md](../学习脑与学员记忆/2026-05-20-luban-learning-report-read-model-execution-plan.md)
- [2026-05-21-luban-learning-report-world-class-optimization-plan.md](../学习脑与学员记忆/2026-05-21-luban-learning-report-world-class-optimization-plan.md)
- [2026-05-26-luban-syllabus-knowledge-map-design.md](../学习脑与学员记忆/2026-05-26-luban-syllabus-knowledge-map-design.md)
- [2026-06-10-luban-photo-answer-ocr-input-layer-implementation-plan.md](2026-06-10-luban-photo-answer-ocr-input-layer-implementation-plan.md)
- [2026-05-25-luban-assessment-testset-p0b-p1-production-flywheel-execution-plan.md](../测评题库与考试模块/2026-05-25-luban-assessment-testset-p0b-p1-production-flywheel-execution-plan.md)
- [2026-04-15-yousen-deeptutor-fusion-prd.md](../微信小程序与结构化渲染/2026-04-15-yousen-deeptutor-fusion-prd.md)

优先级规则：如果专项计划与本文件在移动端产品主目标、IA、P0 范围上冲突，以本文件的 canonical decision 为准；如果涉及评分、learner truth、OCR、WS、合同或真实微信入口，以对应专项 contract / implementation plan 的技术边界为准。
