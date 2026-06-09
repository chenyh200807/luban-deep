# 鲁班首次使用提分诊室 UI/UX 产品方案

状态：Proposed v1  
日期：2026-06-09  
范围：首次登录 / 首次使用激活流，不是常驻模块，不是新 Tab，不是第二套学情系统。

关联计划与契约：

- [contracts/learner-state.md](../../contracts/learner-state.md)
- [contracts/learning-report.md](../../contracts/learning-report.md)
- [2026-05-23-luban-learning-history-evidence-closed-loop-plan.md](2026-05-23-luban-learning-history-evidence-closed-loop-plan.md)
- [2026-05-26-luban-learner-workspace-notebook-calendar-prd.md](2026-05-26-luban-learner-workspace-notebook-calendar-prd.md)
- [2026-06-02-luban-product-behavior-intelligence-prd.md](2026-06-02-luban-product-behavior-intelligence-prd.md)

## 0. 核心结论

`今日提分诊室` 只应该出现在用户第一次登录、第一次打开学习入口、或内测申请用户首次进入产品时。

它的任务不是长期留在产品里，而是在 30-90 秒内完成一次认知切换：

> 这不是一个普通 AI 问答框，而是一个能把我的答案、薄弱章节和下一步训练串起来的提分工具。

完成一次有效动作后，它必须退出，把用户交回正常学习首页、学情页、今日任务卡和聊天主入口。

首次使用链路：

```text
首次进入
  -> 首次使用提分诊室
  -> 完成一次批改 / 出题 / 薄弱点诊断
  -> 生成 learning evidence 或 starter training intent
  -> 回到学习首页 / 学情页的今日任务
  -> 后续不再以独立模块常驻
```

这件事要解决的不是“收集画像”，而是让用户第一次就感受到产品的差异化能力。

## 1. Karpathy Gate

### 1.1 Assumptions

- 当前内测申请用户以 25+、35+ 在职成人为主，时间碎片化，常见痛点是记不住、不会写案例、想知道薄弱章节、缺少复习安排。
- Langfuse 观察到的首轮使用更像知识问答，说明用户还没有理解产品具备批改、出题、薄弱点诊断能力。
- 用户已经明确：这个模块只用于第一次登录 / 第一次使用，不应做成长期功能模块。

### 1.2 Simplest Path

最短路径是做一个一次性激活流：

1. 用内测申请表和首问信息预填一个很短的学习状态判断。
2. 给用户 3 个动作入口：批改答案、出一道题、测薄弱章节。
3. 首次回答必须先给短结论卡，再允许展开讲解。
4. 完成第一次有效动作后写入现有 learner-state / learning evidence / training intent 主链路。
5. 以后由学习首页和学情页承接，不保留一个独立“诊室”模块。

### 1.3 Change Boundary

本方案允许定义：

- 首次使用 UI/UX
- 首次画像确认
- 首次价值动作
- learner-state 写入边界
- 行为埋点
- 设计 QA gate

本方案不定义：

- 新聊天入口
- 新 learner memory authority
- 新推荐系统
- 新长期学习计划日历
- 新人格分析体系
- 新知识图谱或第二套学情页

### 1.4 Verification Target

验收目标不是“用户填完表”，而是：

- 新用户第一次进入后，能在一屏内知道产品可以批改 / 出题 / 找薄弱点。
- 首次有效动作完成率提升。
- 首次结论卡能在 5 秒内讲清楚“我现在该补什么”。
- 后端只写入现有 canonical learner-state / learning evidence / training intent 链路。
- 完成首次价值动作后，激活流不再常驻展示。

## 2. Single Authority Hard Gate

这个设计最容易做坏的地方，是把“首次画像”做成第二套 learner state。必须提前收权。

| 业务事实 | 唯一 authority | 首次使用流能做什么 | 不能做什么 |
| --- | --- | --- | --- |
| 用户自报备考状态 | `user_profiles` 或现有 profile projection | 预填、确认、轻量修改 | 不能当作掌握度真相 |
| 一次答案 / 一次测验暴露的问题 | `learner_memory_events.learning_evidence` | 通过批改或测验写证据 | 不能仅凭聊天印象写长期弱点 |
| 薄弱章节 / 掌握度展示 | `learning_report_read_model` | 只读投影、展示 degraded 状态 | 前端不能直接推断 mastery |
| 下一步该学 / 练 / 怎么教 | `training_intent` / `training_prescription` | 生成 starter next action | 不能新增第二套推荐字段 |
| 对话运行时个性化 | `PersonalizationContextPack` | 读取已有画像和证据 | 不能让 UI 拼 prompt 决策 |
| 首次使用完成状态 | `user_profiles.onboarding_state` 或现有 onboarding projection | 标记 first value action done | 不能用 localStorage 当事实真相 |
| 行为数据 | `surface-events -> product_behavior_events` | 记录点击、完成、展开 | 不能上传原始答案、PII 或完整聊天 |

## 3. 产品定位

### 3.1 一句话

首次使用提分诊室，是给在职备考学员的第一次提分动作。

它不问用户“你想聊什么”，而是直接把用户带到一个可验证的学习动作：

- 发一道最近不会的案例题答案，我批改采分点。
- 没有答案，我先出一道适合你的题。
- 不确定薄弱点，我用 3 个小问题定位。

### 3.2 用户心理

这批用户不是没有上进心，而是时间少、精力被工作和家庭切碎。他们不是缺一个更会聊天的 AI，而是缺一个能替他们节省判断成本的学习教练。

他们第一次打开产品时，不应该看到一个空白聊天框。空白聊天框会把产品降级成 DeepSeek-like 问答工具。

他们应该看到：

- 我知道你大概率时间不固定。
- 我知道你可能已经听过课但不会写题。
- 我知道你现在最需要的是一次小而确定的提分动作。

### 3.3 宣传语边界

可用表达：

- `第一次使用，先帮你找到今天最该补的一处。`
- `不是泛泛讲知识点，而是按采分点告诉你哪里丢分。`
- `每次批改都会沉淀成你的学习记录，下一次直接接着补。`
- `适合时间不固定的在职考生：一次只做一个最该做的动作。`

避免表达：

- `AI 全自动规划人生`
- `性格分析`
- `精准预测通过率`
- `比老师更懂你`
- `永久记忆你的所有学习行为`

## 4. 首次使用 UX

### 4.1 触发条件

展示首次使用提分诊室的条件：

- 首次登录。
- 内测申请用户首次打开学习入口。
- 用户已有申请表画像，但没有有效 `learning_evidence`。
- 没有 `first_value_action_completed_at`。

不展示的条件：

- 已完成过一次批改 / 出题作答 / 薄弱点诊断。
- 已有足够 learning evidence 可直接生成今日任务。
- 用户明确跳过。
- 老用户从学情页或历史记录进入。

### 4.2 首屏结构

首屏必须短，信息密度高，像诊断单，不像问卷。

```text
今日提分诊室

你现在更像：
已学一轮 · 时间不固定 · 案例题容易丢采分点 · 想知道薄弱章节

今天先做一件事：
发一道最近不会的案例题答案，我帮你按采分点批改。

我会给你：
丢分点 · 对应章节 · 今日补救动作 · 明天复测题

[发我的答案，帮我批改]
[没答案，先出一道题]
[先测我薄弱章节]

调整我的情况
```

设计要点：

- 标题不要大而空，直接叫 `今日提分诊室`。
- 用户画像只用一行标签，不要展示复杂人格。
- 主动作最多 3 个。
- 默认推荐动作优先是 `发我的答案，帮我批改`，因为这是最能体现差异化的能力。
- `调整我的情况` 是次级入口，不要抢主动作。

### 4.3 轻量画像调整

如果用户点 `调整我的情况`，只允许出现一个底部 sheet 或半屏面板。

字段上限：

| 字段 | 选项 |
| --- | --- |
| 当前阶段 | 刚开始 / 学过一轮 / 冲刺复习 |
| 最大痛点 | 记不住 / 案例不会写 / 不知道薄弱点 / 没计划 |
| 今天可用时间 | 5 分钟 / 15 分钟 / 30 分钟 |
| 希望怎么教 | 先给结论 / 多讲原理 / 多给例题 |

禁止：

- MBTI 式人格判断
- 长问卷
- 开放式长文本
- “学习风格”伪科学标签
- 要求用户一次性补全所有资料

这里的目标只是让首次体验更贴脸，不是完成完整 learner state 建模。

## 5. 首次价值动作

### 5.1 动作 A：发我的答案，帮我批改

这是默认主路径。

输入提示：

```text
把题目和你的答案发来即可。没有标准格式。
我会先给你采分点得失，再告诉你今天补哪一小块。
```

首轮输出必须先给结论卡：

```text
批改结论

预计得分：6 / 10
主要丢分：2 个采分点
对应章节：主体结构工程施工
今天先补：施工缝设置位置 + 继续浇筑条件
明天复测：1 道同类案例小题

你最该改的一句话：
你的答案说到了“留施工缝”，但没有写出“留在受剪力较小且便于施工的位置”。

[展开完整批改]
[开始今日补救]
[明天提醒我复测]
```

输出纪律：

- 第一屏先给结论，不先铺大段讲解。
- 必须出现分数 / 采分点 / 章节 / 今日动作 / 复测动作。
- 证据不足时必须标注 `基于当前答案初判`，不能装作已有长期画像。
- 展开讲解放在二级，不压住结论。

### 5.2 动作 B：没答案，先出一道题

适合不知道从哪里开始的用户。

题目策略：

- 默认只出 1 道小题或 1 个案例小问。
- 不要一次给整套卷。
- 题后要求用户先答，不要立即长篇解析。
- 用户提交后走同一批改结论卡。

示例：

```text
先做 1 道小题，预计 4 分钟。

问题：
某工程混凝土浇筑过程中需要留设施工缝。请写出施工缝留设位置的基本要求。

[我来作答]
[换一题]
```

### 5.3 动作 C：先测我薄弱章节

适合没有具体题目的用户。

策略：

- 只问 3 个快速判断题，或 1 个微案例。
- 不输出“你这个章节掌握度 42%”这种伪精确结论。
- 输出 `初步薄弱方向` 和 `建议先做的动作`。

示例：

```text
初步判断

你现在更可能卡在：
主体结构工程施工 · 混凝土施工缝

判断依据：
3 个快速题里，施工缝位置和继续浇筑条件都不稳定。

今天建议：
先做 1 道施工缝案例小问，再看 3 条采分句。
```

## 6. UI Design Direction

### 6.1 设计气质

关键词：

- 克制
- 专业
- 高信任
- 像诊断单
- 适合 35+ 在职成人

不要做成：

- AI 机器人聊天玩具
- 大面积紫蓝渐变
- 营销落地页
- 卡片套卡片
- 复杂仪表盘
- 过度年轻化打卡应用

### 6.2 版式

移动端第一屏结构：

```text
顶部：产品内导航 / 返回

主区：
  今日提分诊室
  一句价值说明

诊断条：
  已学一轮 · 时间不固定 · 案例题丢分 · 想知道薄弱章节

主建议：
  今天先做一件事...

三个动作按钮：
  主按钮
  次按钮
  次按钮

底部：
  调整我的情况 / 稍后再说
```

视觉规则：

- 卡片圆角不超过 8px。
- 一屏只强调一个主动作。
- 主按钮高度 44-48px，文字不超过 10 个汉字。
- 正文至少 15px，关键数字至少 22px。
- 标签用低饱和中性色，不做彩虹标签。
- 重要结论左对齐，不居中堆叠。

### 6.3 结论卡组件

结论卡是整个体验的核心。它应该像医生给出的短诊断，而不是聊天回复。

组件结构：

```text
状态行：批改结论 / 初步诊断 / 今日建议
核心数字：预计得分 / 丢分点数 / 今日任务
证据行：基于你的这次答案
行动行：今天补什么
复测行：明天怎么验证
操作区：展开 / 开始 / 提醒
```

要求：

- 同一屏内能读完。
- 任何结论都要有证据来源。
- 允许 degraded：如果证据不足，必须写 `证据还少，先按这次答案给建议`。
- 不要把长解释塞进结论卡。

### 6.4 文案原则

好文案：

- `今天先补这一小块`
- `你主要丢在采分点，不是完全不会`
- `先做 1 道同类小题验证`
- `我先给结论，想看原因再展开`

坏文案：

- `根据你的多维人格模型`
- `为你生成全周期智能学习系统`
- `你当前掌握度仅 37.6%`
- `开启 AI 学习之旅`

## 7. Learner State 关系

### 7.1 四层画像

首次使用流可以补画像，但要分层，不能混成一个“性格分析”。

| 层级 | 来源 | 用途 | 可写入长期状态吗 |
| --- | --- | --- | --- |
| 自报画像 | 申请表 / 首次确认 | 首屏预填、分流 | 可以，但标记为 self_reported |
| 行为画像 | 点击、完成、展开 | 产品优化、轻量偏好 | 可以写行为表，不写掌握度 |
| 作答证据 | 批改、测验、复测 | 薄弱点、采分点、训练建议 | 可以，必须走 learning_evidence |
| 教学偏好 | 用户选择先结论 / 多例题 | 输出节奏 | 可以，但不能当学习能力判断 |

### 7.2 推荐数据流

```text
invite_test_application / onboarding confirmation
  -> user_profiles.preference / onboarding_state
  -> first_use_clinic projection

first value action
  -> deep_question / construction_grading / assessment authority
  -> learner_memory_events.learning_evidence
  -> learning_synthesis
  -> learning_report_read_model
  -> training_intent / next_best_action
  -> PersonalizationContextPack
  -> chat / learning home / report page
```

### 7.3 禁止的数据流

```text
frontend tags -> mastery score
chat impression -> weak chapter truth
localStorage -> learner state
onboarding answer -> long-term diagnosis
first_use_clinic -> independent recommendation engine
```

## 8. 行为埋点

复用 `surface-events -> product_behavior_events`。

事件白名单：

- `first_use_clinic_viewed`
- `first_use_profile_confirmed`
- `first_use_profile_adjusted`
- `first_use_action_selected`
- `first_value_action_started`
- `first_value_action_completed`
- `first_conclusion_card_viewed`
- `first_conclusion_expanded`
- `first_next_action_started`
- `first_use_clinic_dismissed`

允许 metadata：

- `entry_source`
- `application_profile_present`
- `selected_action`
- `profile_stage`
- `pain_point`
- `time_budget_bucket`
- `teaching_preference`
- `completion_status`
- `evidence_event_id`
- `training_intent_id`

禁止 metadata：

- 原始答案全文
- 题干全文
- 手机号
- 姓名
- 微信 openid 明文
- 完整聊天内容
- 截图 OCR 文本

## 9. 成功指标

### 9.1 激活指标

- 首次使用提分诊室曝光率
- 首次动作选择率
- 首次价值动作完成率
- 首次结论卡浏览率
- 首次结论展开率
- 首次下一步动作开始率

### 9.2 Aha 指标

核心观察：

- 3 轮以内是否从知识问答转为批改 / 出题 / 诊断。
- 首次完成后 24-48 小时是否回访。
- 是否点击今日补救动作或明天复测。
- 是否生成有效 learning evidence。

### 9.3 质量指标

- 结论卡是否能追溯到 evidence。
- 薄弱点是否来自作答或测验，而不是前端标签。
- next action 是否来自 training intent。
- degraded 状态是否正确展示。

## 10. 发布切片

### Slice 0：文案和入口实验

目标：先验证认知切换，不碰核心 learner-state。

- 首屏诊断卡
- 三个动作入口
- 跳过 / 稍后再说
- 行为埋点

验收：

- 新用户知道可以批改 / 出题 / 测薄弱点。
- 首次动作选择率可观测。

### Slice 1：画像预填

目标：用申请表降低冷启动，但不制造掌握度真相。

- 申请表字段映射到 self_reported profile
- 用户可轻量调整
- first-use projection 只读 profile

验收：

- 画像标签能解释来源。
- 用户调整不影响历史证据。

### Slice 2：结论卡

目标：让第一次批改或测验产生可感知价值。

- 批改结论卡
- 出题后批改
- 快速诊断结论卡
- evidence / degraded 展示

验收：

- 首轮回答先给结论卡。
- 卡片内有得分、丢分点、章节、今日补救、复测动作。

### Slice 3：退出和承接

目标：首次使用流完成后不常驻。

- 写 `first_value_action_completed_at`
- 首页显示今日任务卡
- 学情页显示对应 evidence
- 对话继续读取 PersonalizationContextPack

验收：

- 已完成用户不再看到首次使用诊室。
- 下一次打开直接看到学习首页 / 今日任务。

## 11. Design QA Gate

上线前必须逐条过：

1. `yousenwebview` 是 DevTools project root，`packageDeeptutor` 是 target subpackage。
2. 390px 宽度无横向滚动。
3. 首屏主动作不超过 3 个。
4. 结论卡一屏内可读完。
5. 正文不小于 15px，核心数字不小于 22px。
6. 所有诊断都有 evidence 或 degraded 状态。
7. 用户可以跳过，不强制填表。
8. 完成首次价值动作后退出，不再常驻。
9. 行为事件只走 `surface-events`。
10. 不出现人格标签、AI 营销话术、伪精确掌握度。

## 12. Non-goals

- 不做永久 Tab。
- 不做完整 onboarding survey。
- 不做人格分析。
- 不做日历 / planner CRUD。
- 不做完整错因地图。
- 不做教师协作。
- 不做第二套 learner memory。
- 不做第二套推荐系统。
- 不替代学习首页、学情页或聊天主入口。

## 13. 最终产品判断

`每次批改结果存成学生学习记录，再自动总结薄弱点，生成下一步该学什么、练什么、怎么教的个性化建议` 仍然是核心能力，但它不应该在首次使用时被包装成后台概念。

首次使用时，用户只需要感受到一件事：

> 我发出一个真实学习动作，系统马上告诉我哪里丢分、对应哪章、今天补什么、明天怎么复测。

这就是首次使用提分诊室的边界和品味：短、准、可追溯、做完即走。
