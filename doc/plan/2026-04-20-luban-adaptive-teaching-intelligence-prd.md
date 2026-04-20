# PRD：鲁班智考因材施教智能体与显性个性化导师升级

## 1. 文档信息

- 文档名称：鲁班智考因材施教智能体与显性个性化导师升级 PRD
- 文档路径：`/doc/plan/2026-04-20-luban-adaptive-teaching-intelligence-prd.md`
- 创建日期：2026-04-20
- 适用范围：鲁班智考、TutorBot、学员级长期状态、Guided Learning、微信小程序 chat / report / assessment / profile 主链路
- 状态：Draft v1
- 关联 contract：
  - [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)
  - [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)
  - [contracts/learner-state.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/learner-state.md)
- 关联文档：
  - [2026-04-15-learner-state-memory-guided-learning-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-15-learner-state-memory-guided-learning-prd.md)
  - [2026-04-15-bot-learner-overlay-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-15-bot-learner-overlay-prd.md)
  - [2026-04-15-bot-learner-overlay-service-design.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-15-bot-learner-overlay-service-design.md)
  - [2026-04-15-learner-state-service-design.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-15-learner-state-service-design.md)
- 概念参考：
  - [2026-04-10-active-teaching-object-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/plans/2026-04-10-active-teaching-object-prd.md)
  - [2026-04-05-compiled-learning-assets-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/plans/2026-04-05-compiled-learning-assets-prd.md)
  - [2026-04-06-world-class-memory-operating-system-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/plans/2026-04-06-world-class-memory-operating-system-prd.md)

## 2. 一句话结论

鲁班智考下一阶段不应该再新增一套更大的 memory 系统，也不应该把个性化继续做成 prompt 层的“显得更懂你”。

下一阶段真正要做的是：

> 在现有 `learner state + bot-local overlay + TutorBot` 基础上，补一层 **证据阈值驱动的 Teaching Policy Layer** 与 **显性诊断表达合同**，让系统一旦掌握足够信息，就立即从“单轮响应”升级为“轨迹级因材施教”。

目标不是“更会描述学员”，而是：

1. 更早、更准地知道学员真正卡在哪
2. 更稳定地知道下一步该怎样教、该练什么、该用什么节奏推进
3. 让学员明确感知到：系统真的懂他，而且越来越会教他

## 3. 北极星体验

世界级体验不是“它记得我以前说过什么”，而是：

1. 我不需要每次重新解释自己卡在哪
2. 它不仅知道我最近哪里错，而且知道我为什么总错
3. 它会根据我的偏好、近况和轨迹，主动改变讲法和练习安排
4. 它会像名师一样直接点破我当前真正的问题，并说明为什么现在要这样教
5. 我会感觉到：继续用下去，系统会越来越省力、越来越准、越来越像我的专属导师

可感知的典型时刻应当长成这样：

> “你这几次不是知识点全不会，而是总在责任边界上判反。你最近一看长解释就容易乱，所以这次我不先铺原理，先给你一个最短判断骨架，把这类题先做稳。”

这句话同时体现了：

1. 系统看见了轨迹
2. 系统做出了诊断
3. 系统改变了教法
4. 系统向学员显性说明了这次为什么这样教

## 4. 现状判断

### 4.1 当前系统不是没有个性化，而是已经有一套不错的基础

当前仓库已经具备以下能力：

1. 冷启动摸底测试
   - 小程序 assessment 已支持 `diagnostic` 20 题摸底。
   - 可输出：
     - 分数
     - 章节掌握度
     - learner archetype
     - response profile
     - calibration label
     - error pattern
     - priority chapters
     - action plan

2. 学员级长期状态主干
   - 已有 `profile / summary / progress / goals / memory_events / heartbeat`
   - 已通过 `LearnerStateService` 做统一读写与上下文组装
   - 已明确 `user_id` 是单一 learner truth 主键

3. Guided Learning 对长期状态的写回
   - 学习计划完成后，已经能把：
     - 完成知识点
     - weak points
     - focus_topic
     - focus_query
     - 今日完成量
   - 写回 learner core

4. Tutor persona 已能消费 learner profile
   - 现有 Tutor persona 已根据：
     - difficulty_preference
     - explanation_style
     - level
     - exam_date
     - focus_topic
     - display_name
   - 调整回答合同和教师身份表述

5. 教学模式与题型场景适配
   - 已支持 `smart / fast / deep`
   - 已区分 `concept / mcq / case / error_review`
   - 已有“出题时默认不提前给答案”的稳定规则

6. Bot-local overlay 基础设施
   - 已支持：
     - `local_focus`
     - `active_plan_binding`
     - `teaching_policy_override`
     - `heartbeat_override`
     - `working_memory_projection`
     - `engagement_state`
     - `promotion_candidates`
   - 已支持局部状态衰减和 promotion pipeline

7. Heartbeat 主动陪学与提醒
   - 已有默认 heartbeat job
   - 已记录 delivery / arbitration 历史
   - 已具备“按学员长期状态安排主动触达”的基本机制

### 4.2 当前真正的缺口

当前系统真正缺的不是：

1. 更多状态字段
2. 更多 memory 容器
3. 更大的画像系统

真正缺的是：

1. 一个薄而明确的 `Teaching Policy Layer`
2. 一个“何时从单轮个性化升级为轨迹级教学”的激活规则
3. 一个“如何向学员显性表达诊断与换教法”的表达合同
4. 一个“哪种教学动作对这类学员真的更有效”的效果回流闭环

### 4.3 root cause

根因不是“数据不够”，而是“已有数据还没有被编译成足够稳定的教学决策”。

当前系统已经能：

1. 记录学员
2. 总结学员
3. 聚合近期状态
4. 存储局部策略覆盖

但还不能稳定做到：

1. 这位学员此刻最该怎么教
2. 这轮要不要显性点破他的真正卡点
3. 这次应该先给答案、先给提示、先给骨架、还是先接住状态
4. 这次练习安排是否真的在服务他的长期提分

因此，本 PRD 的治本点不是“继续加 memory”，而是：

> 让 learner understanding 最终落到一组可执行、可解释、可回退的教学决策上。

## 5. 产品目标

### 5.1 主目标

把鲁班智考升级为真正的个性化专属导师，使系统能够：

1. 真正理解学员，而不是只会复述画像
2. 真正知道怎样因材施教，而不是只会切换语气或模式
3. 真正显性表达这种理解，让学员感到“它真的懂我”
4. 真正对提分负责，让下一步训练和讲解更准、更稳、更低摩擦

### 5.2 子目标

1. 冷启动阶段就有感
   - 新用户不需要很长时间积累，系统在摸底与前几轮互动内就能形成初步可用教学假设

2. 证据一够就立即升级
   - 不再使用固定“连续 5 天”或固定天数阈值
   - 只要证据足够，就应立即从单轮响应升级为轨迹级教学

3. 显性表达必须像老师，不像系统
   - 系统要显性说出判断
   - 但表达必须像名师诊断，不像后台画像播报

4. 个性化必须服务提分，而不是服务热闹
   - 所有个性化能力都必须最终回到：
     - 做题正确率
     - 错因识别
     - 后续练习命中率
     - 持续学习意愿

## 6. 非目标

本 PRD 明确不做：

1. 不再新建第二套 learner truth
2. 不把 overlay 扩张成平行 learner state
3. 不把 `teaching_mode` 升格为教学决策主脑
4. 不在热路径引入每轮必跑的重 LLM 个性化分析链
5. 不做操纵性“成瘾”设计
6. 不为了个性化而牺牲 groundedness、证据纪律或回答稳定性

## 7. 第一性原则

### 7.1 First Principles

1. 个性化的终点不是“更懂你”，而是“更会教你”
2. 同一业务事实只能有一个一等概念
3. 当前教学对象与长期 learner model 必须分离
4. 历史资产只能 support，不能覆盖当前轮 authority
5. 教学策略必须基于证据，而不是基于想象中的用户类型
6. 对学员说出的个性化判断，必须能追溯到足够证据

### 7.2 Less Is More

正确做法不是：

1. 再造一个 memory OS v2
2. 再造一个 learner wiki 主系统
3. 再造一个更大的 router / classifier / wrapper / prompt bundle

正确做法是：

1. 继续复用已有 learner core
2. 继续复用已有 overlay
3. 新增一层很薄的 `Teaching Policy Layer`
4. 只让这层输出少量高价值决策位

### 7.3 不可协商的 10 条不变量

1. `user_id` 级 learner core 仍然是长期真相
2. `bot_id + user_id` overlay 只能表达局部差异
3. `teaching_mode` 只表示表达密度或节奏，不承担 learner truth
4. 当前教学对象必须优先于长期画像
5. 当前轮 facts 优先于历史 support
6. 任何显性诊断都必须带证据置信度
7. 证据不足时必须退回高质量通用教学，而不是硬做个性化
8. 任何短期变化默认可以衰减，不得直接永久写死
9. 任何局部候选进入全局 learner core 必须经过 promotion
10. 个性化不得让系统更爱“猜”，而应让系统更爱“少猜”

## 8. 核心能力模型

本 PRD 将系统拆成 5 层，而不是再造一个统一大脑。

### 8.1 Current Teaching Object

负责回答：

1. 这轮到底在教什么
2. 这轮服务的是哪道题、哪个错因、哪个 remediation goal
3. 当前对象是否仍然连续，还是已经切换

这一层解决的是“当前轮 authority”问题，不解决长期个性化问题。

### 8.2 Learner Core

负责承载学员级长期状态，包括：

1. 稳定偏好
2. 长期目标
3. 稳定学习水平判断
4. 持续进展
5. 长期总结
6. 关键 memory events

它回答的是：

1. 这个人长期是谁
2. 他通常怎样学
3. 他大致处在什么阶段

### 8.3 Bot-Local Overlay

负责承载最近变化与局部状态，包括：

1. 最近聚焦
2. 局部 engagement state
3. 局部 teaching policy override
4. working memory projection
5. promotion candidates

它回答的是：

1. 这个人最近怎么变了
2. 这个 bot 最近针对他正在做什么

### 8.4 Teaching Policy Layer

这是本 PRD 新增的核心薄层。

它不负责重建 learner truth，而只负责基于：

1. 当前教学对象
2. learner core
3. bot-local overlay
4. assessment / progress / guide / recent errors

输出少量高价值教学决策位。

推荐第一版只输出 6 个字段：

1. `diagnosis`
   - 当前真正卡点

2. `next_step`
   - 当前最该练什么或推进什么

3. `explanation_mode`
   - `conclusion_first`
   - `skeleton_first`
   - `principle_first`
   - `hint_first`

4. `pace_mode`
   - `push`
   - `steady`
   - `soothe_then_push`

5. `challenge_mode`
   - `stabilize`
   - `stretch`
   - `review`

6. `explicitness`
   - 这轮是否应该显性说出诊断与换教法

每个字段都必须带：

1. `confidence`
2. `evidence_refs`
3. `expires_at`

### 8.5 Explicit Diagnosis Contract

这是第二个新增层。

它不负责“怎么判断”，只负责“怎么对学员说”。

它要保证：

1. 系统显性表达时像老师，不像系统
2. 不是播报画像，而是点破问题
3. 不是讲抽象心理学，而是服务当前学习动作
4. 不用每轮都说，只在该说时说

## 9. 证据阈值驱动模型

### 9.1 为什么不能用固定“5 天”

固定天数的问题在于：

1. 有的学员 20 题摸底加 3 轮互动就已足够显著
2. 有的学员连续几天使用，信息仍然低质量、低稳定
3. “按天”是产品运营视角，不是教学决策视角

因此，系统升级到轨迹级教学的条件必须是：

> 证据足够，而不是时间足够。

### 9.2 因材施教激活阈值

建议按 4 类信号判断是否激活轨迹级教学：

1. 冷启动信号
   - 摸底测试结果
   - 初始章节掌握度
   - 初始 learner archetype / response profile

2. 稳定偏好信号
   - 难度偏好
   - 讲解风格偏好
   - 是否更吃结论、骨架、原理、提示

3. 轨迹信号
   - 重复错因
   - 同类题错误模式
   - 连续 focus topic
   - Guided Learning completion 后的 weak point 延续

4. 互动状态信号
   - 最近是否急、慌、碎片化
   - 是否一遇到长解释就掉线
   - 是否最近更适合稳住节奏

### 9.3 激活条件

满足以下任一组合即可进入轨迹级教学：

1. 高质量摸底结果 + 至少一个稳定偏好信号
2. 同类错因重复出现 + 当前对象连续
3. Guided Learning / Review / Practice 写回形成稳定 weak point
4. overlay 中已有高置信度 `promotion_candidates` 被提升为 learner core 事实

### 9.4 退出与降级

轨迹级教学不是永久锁定。

以下情况应降级回保守模式：

1. 当前轮对象明显切换
2. 历史证据与当前输入强冲突
3. 个性化判断置信度下降
4. 学员明确纠正系统判断

降级后：

1. 保留已有 learner truth
2. 本轮只回退为高质量通用教学
3. 不强行继续显性诊断

## 10. 显性表达合同

### 10.1 什么时候要显性说

默认不是每轮都说。只有以下场景才应显性表达：

1. 系统发现了重复错因
2. 系统准备切换教法
3. 系统准备改变练习安排
4. 学员明显情绪波动或节奏失衡
5. 学员已经连续学习并值得看到阶段性诊断

### 10.2 显性表达应该像什么

应该像：

1. “你这几次不是不会这个知识点，而是总在判定边界上判反。”
2. “你最近一看长解释就容易乱，所以这次我先不给你长篇原理，先给你最短作答骨架。”
3. “你不是没有进步，而是同一种错误还在重复，所以这次不扩新题，先把这一类题打穿。”

### 10.3 显性表达不应该像什么

不应该像：

1. “根据你的学习画像，你属于冲动型学习者。”
2. “系统判断你适合详细讲解风格。”
3. “根据你近 5 天的行为分析……”

原因：

1. 这类表达像后台分析系统，不像老师
2. 容易引发被分析感，而不是被理解感
3. 容易让错判断直接暴露为低级幻觉

### 10.4 表达模板

推荐结构固定为：

1. `先点破当前真正问题`
2. `再说明为什么这次要换教法`
3. `最后给出一个最小可执行下一步`

例如：

> 你这次不是知识点全不会，而是总把 X 和 Y 的成立前提混掉。你最近一遇到这种题就容易急，所以我这次不先讲大原理，先给你一个 3 步判断抓手。你先按这个抓手判断下一题，我再帮你补原理。

## 11. 教学策略层职责边界

### 11.1 它负责什么

1. 选择怎么教
2. 选择先练什么
3. 选择本轮是否显性诊断
4. 选择推进还是减压

### 11.2 它不负责什么

1. 不负责 learner truth 写入
2. 不负责决定当前教学对象
3. 不负责知识检索
4. 不负责身份或工具路由

### 11.3 它与现有 `teaching_mode` 的关系

`teaching_mode` 继续只承担：

1. 表达密度
2. 节奏倾向
3. 答案展开深度

`Teaching Policy Layer` 承担：

1. 为什么现在这样教
2. 该优先哪种教学动作
3. 是否要显性表达

两者关系应为：

> `Teaching Policy Layer` 决定这轮教学策略，`teaching_mode` 只是在该策略下的表达风格参数。

## 12. 数据与控制面边界

### 12.1 单一权威表

| 层 | 主语 | 作用 | 是否长期真相 |
|---|---|---|---|
| Current Teaching Object | turn / session | 当前这轮在教什么 | 否 |
| Learner Core | user_id | 学员长期状态 | 是 |
| Bot-Local Overlay | bot_id + user_id | 局部差异与最近变化 | 否 |
| Teaching Policy | turn-scoped decision | 本轮教学决策 | 否 |
| Explicit Diagnosis | user-facing utterance | 向学员显性表达 | 否 |

### 12.2 写入纪律

1. 当前轮 facts 先进入 events / runtime
2. 长期稳定事实进入 learner core
3. 短期变化与局部策略进入 overlay
4. policy 只产生决策，不直接改写 learner truth
5. 显性表达是 policy 的消费结果，不是新的状态来源

## 13. 产品形态

### 13.1 新用户冷启动

目标：

1. 20 题摸底即建立第一版教学假设
2. 第一轮正式对话就能体现“不是完全通用模板”

系统应产出：

1. 初始章节掌握图
2. 初始 learner archetype
3. 初始 response profile
4. 初始优先章节与行动计划
5. 初始教学建议

### 13.2 前几轮自适应

目标：

1. 不等很久就让学员感到“它开始懂我了”
2. 但也不轻易把用户定型

系统应做到：

1. 高置信度时显性表达
2. 低置信度时保守高质量教学
3. 连续纠正自身判断，而不是死守第一次画像

### 13.3 轨迹级因材施教

当证据阈值满足后，系统应表现出 4 类能力：

1. 主动总结这段时间真正的薄弱点
2. 主动切换成更适合的讲法
3. 主动安排接下来最该练的内容
4. 主动识别最近状态变化并调整节奏

注意：

1. 这 4 个不是分散功能，而是同一 policy layer 的 4 个输出
2. 学员感知上应是一种统一体验：
   - “它越来越知道该怎么教我”

## 14. 风险与负面影响

### 14.1 主要风险

1. 过度推断
   - 系统太早给用户下定性结论

2. 历史压过当前
   - 历史画像干扰当前教学对象

3. prompt 膨胀
   - 个性化上下文越来越大，稀释当前问题

4. 第二真相源复活
   - overlay 或 policy 反向变成平行 learner truth

5. 个性化幻觉
   - 系统说出“你就是这样的人”，但其实没有足够证据

### 14.2 防护策略

1. `facts vs inference` 分层
   - 所有 policy 输出必须区分事实与推断

2. `confidence gating`
   - 低置信度不显性表达，不强做个性化

3. `history supports, never overrides`
   - 历史只能 support 当前轮

4. `compact injection`
   - learner context 和 overlay context 必须压缩，不得无限注入

5. `TTL + decay`
   - 局部变化默认衰减

6. `promotion discipline`
   - 短期推断不得直接写入 learner core

7. `policy is thin`
   - 第一版只保留少量决策位，不做大而全策略引擎

### 14.3 为什么这不违背 less is more

因为我们不是再新增一套更大的系统，而是在已有骨架上补一个薄层。

真正违背 less is more 的做法是：

1. 继续加状态字段
2. 继续堆 prompt
3. 继续搞第二套解释器

本 PRD 选择的是：

1. 概念更少
2. authority 更单一
3. 决策位更少
4. 验证路径更直接

所以只要严格按本 PRD 的边界实施，它不是加复杂度，而是在消除“已经有很多信号却不会稳定做决策”的低效复杂度。

## 15. 预期收益

### 15.1 直接收益

1. 学员更快感受到“系统真的懂我”
2. 后续讲解更像专属老师，而不是统一模板
3. 练习安排更贴近最近真实卡点
4. 连续学习时的承接感更强

### 15.2 中期收益

1. 错题复盘更准
2. 下一步训练命中率更高
3. 学员更愿意继续回来
4. 用户更愿意相信系统建议的学习路径

### 15.3 长期收益

1. 建立真正的“越用越懂你、越用越会教你”飞轮
2. 为后续 `intervention effectiveness` 和 `cohort intelligence` 预留干净入口
3. 把个性化从“会描述”升级成“会决策”

## 16. 分阶段推进

### 16.1 Phase 0：盘点与收口

目标：

1. 明确现有个性化能力已覆盖到哪里
2. 明确现有 learner core、overlay、teaching mode 的职责边界
3. 不新增代码路径，只建立统一术语和上位 PRD

### 16.2 Phase 1：Teaching Policy Shadow

目标：

1. 建立只读 policy 计算层
2. 不直接影响最终回答
3. 先 shadow 产出：
   - diagnosis
   - next_step
   - explanation_mode
   - pace_mode
   - explicitness

验收：

1. policy 输出可解释
2. policy 输出不与 learner core 争权
3. policy 输出可回溯到证据

### 16.3 Phase 2：显性表达 limited rollout

目标：

1. 在高置信度场景中启用显性诊断表达
2. 表达必须遵守“像老师，不像系统”的合同

验收：

1. 学员体感提升
2. 不增加明显误判投诉
3. 不增加“被系统分析”的反感

### 16.4 Phase 3：Intervention Effectiveness 闭环

目标：

1. 记录 policy 选择了什么教学动作
2. 记录后续结果窗口
3. 初步估计哪类动作对哪类学员更有效

注意：

1. 这一阶段才允许谈“系统逐步学会哪种教法更有效”
2. 不应在第一阶段就把效果学习层做得过重

## 17. 成功定义

### 17.1 用户侧成功定义

如果这份 PRD 成功落地，学员应该能明确说出下面至少两句：

1. “它知道我最近到底卡在哪。”
2. “它会根据我的情况换一种更适合的讲法。”
3. “它安排的下一步练习比我自己瞎练更准。”
4. “它不像每次重新认识我，而像一直在带我。”

### 17.2 系统侧成功定义

1. 当前对象、长期状态、局部变化、教学决策四层不混权
2. 证据足够时能稳定进入轨迹级教学
3. 证据不足时能稳妥回退，不强做个性化
4. 显性表达不变成画像播报
5. 学员满意度与提分效率双指标上升

### 17.3 明确失败信号

出现以下任一情况，应判定方案偏离：

1. 系统越来越爱下结论，但越来越容易看错人
2. overlay 字段迅速膨胀
3. prompt 注入越来越重
4. 学员觉得“它在分析我”，而不是“它在理解我”
5. 代码里重新长出第二套 learner truth

## 18. 最终判断

这条线不是多余工作，也不是违背 `first principles` 和 `less is more` 的加法。

相反，它是当前系统在基础已经不错之后，最应该做的一次“薄而关键”的升级：

1. 不是再加记忆
2. 不是再加画像
3. 不是再加路由

而是把已经存在的理解能力，真正收口为：

> 更早、更准、更可解释地知道该怎样教这个学员。

这才是鲁班智考从“会答题的智能体”升级为“世界级个性化专属导师”的关键一步。
