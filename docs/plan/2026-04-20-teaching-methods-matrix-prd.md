# PRD：鲁班智考 Teaching Methods Matrix（因材施教中的“施教层”）

## 1. 文档信息

- 文档名称：鲁班智考 Teaching Methods Matrix PRD
- 文档路径：`/docs/plan/2026-04-20-teaching-methods-matrix-prd.md`
- 创建日期：2026-04-20
- 状态：Draft v1
- 适用范围：鲁班智考、TutorBot、assessment、quiz、error review、guided learning completion 后的承接教学、heartbeat 复习触达
- 关联文档：
  - [2026-04-20-luban-adaptive-teaching-intelligence-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-20-luban-adaptive-teaching-intelligence-prd.md)
  - [2026-04-15-learner-state-memory-guided-learning-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-15-learner-state-memory-guided-learning-prd.md)
  - [2026-04-15-bot-learner-overlay-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-15-bot-learner-overlay-prd.md)

## 2. 一句话结论

鲁班智考的“施教层”不应该由某一个教育流派直接统治，也不应该继续停留在 prompt 里的“像老师”。

当前条件下最优、最稳健、最可交付的做法是：

> 以 **高质量一对一辅导** 作为交付形态，以 **形成性诊断 + Worked Example + 支架递减 + 检索练习 + 间隔复现 + 掌握学习 + 元认知教练** 作为核心方法栈，再把这些方法压成一组可记录、可切换、可验证的教学动作。

这份文档回答的不是“系统更懂学员”，而是：

1. 面对不同学员和不同学习阶段，到底该用哪一种教学方法
2. 什么时候该切换方法
3. 什么方法不该用
4. 怎样证明这种方法真的帮助提分，而不是只让用户感觉被理解

## 3. 为什么要单独写这份 PRD

前一份因材施教 PRD 已经基本回答了：

1. 系统如何理解学员
2. 如何把 learner understanding 收口为教学决策
3. 如何显性表达这种理解

但还没有把“施教”本身写透。

当前系统和当前 PRD 里已经有：

1. 学员画像
2. 当前教学对象
3. 教学策略层
4. 一版原子动作

但还缺少：

1. 一个清晰的教学方法谱系
2. 这些方法各自的适用条件
3. 这些方法的切换规则
4. 这些方法如何落成 TutorBot runtime 动作
5. 这些方法如何进入可观测、可验证的效果闭环

因此，这份文档的职责是：

> 把“因材施教”里的“施教”部分，从一句方向正确的话，升级为一套可以直接进入设计、实现、评估的教学方法矩阵。

## 4. 方法选型标准

为了配得上“全球顶尖、成熟、可靠”的要求，本 PRD 只选择同时满足以下条件的方法：

1. 有长期研究积累或高质量综述支持
2. 能与一对一 tutoring 场景兼容
3. 能适配建筑实务/备考/练题/纠错/提分场景
4. 能被翻译成数字化 tutoring runtime 动作
5. 能被日志记录和后验评估
6. 不会天然诱发更高的幻觉风险

不满足这些条件的方法，即便教育理念上很美，也不应成为第一版主骨架。

## 5. 全球成熟方法里，鲁班应当取什么、不取什么

### 5.1 应当吸收的，不是某个单一“门派”，而是稳定有效的共同骨架

从当前最成熟、最可靠的研究和实践看，鲁班应该吸收的是以下共同骨架：

1. 先诊断，再教学
2. 新手先示范、先支架，不先放养
3. 只听讲不够，必须检索与练习
4. 打穿单一弱点比盲目扩内容更有效
5. 同一方法不适用于所有熟练度
6. 学会“如何学”和“如何检查自己”本身就是教学目标

### 5.2 不应机械照搬的内容

以下内容可以影响理念层，但不应直接成为鲁班考试智能体的第一版主骨架：

1. 纯 Montessori 式自由探索
   - 它更适合作为“尊重节奏、观察先于干预”的理念输入，而不是考试辅导主引擎。

2. 纯苏格拉底追问
   - 对高水平学员和反思场景有价值，但默认用在脆弱、着急、基础薄弱的学员身上，容易放大学习挫败。

3. 纯发现式学习 / 纯 Problem-Based Learning
   - 对考试型、规范型、边界判断型内容，如果没有足够支架，学习成本高、错法易固化。

4. 只做情绪支持或“陪伴感”
   - 陪伴是必要层，但不是教学法主线。鲁班的北极星仍然是提分。

## 6. 鲁班的施教总架构

鲁班的施教层应采用以下总架构：

### 6.1 交付形态：高质量一对一辅导

这是鲁班最上层的交付形态，而不是单独某一招教学法。

它意味着：

1. 教学应围绕单个学员的当前理解状态展开
2. 教学内容必须和当前学习任务、错因、进展强绑定
3. 教学动作必须额外精准、短链路、可追踪

### 6.2 lesson skeleton：认知学徒式交付

鲁班的默认教学骨架应是：

1. `model`
   - 先示范正确思路或判断抓手

2. `coach`
   - 先给引导和支架，不把学员丢进完全开放题海

3. `scaffold`
   - 给步骤、骨架、提示、对照

4. `fade`
   - 学员开始稳住后，逐步撤支架

5. `independent retrieval`
   - 让学员自己调取并使用知识

这不是单独某篇论文的口号，而是将 Worked Example、Scaffolding、Expertise Reversal 这几类成熟研究压成鲁班可执行的统一骨架。

### 6.3 调度主循环

鲁班每轮教学都应落在同一条主循环上：

1. `诊断`
2. `选法`
3. `交付`
4. `检查`
5. `安排下一次复现`
6. `根据结果再诊断`

换句话说，施教不是一句回答，而是一段小闭环。

## 7. 核心教学方法矩阵

### 7.1 Formative Diagnostic Teaching

#### 这是什么

先通过小问题、小判断、小证据，定位当前真正卡点，再决定怎么教。

#### 为什么必须作为第一层

因为绝大多数低质量个性化都不是“不会教”，而是“还没看清楚就开始教”。

#### 证据基础

1. 形成性评价与高质量反馈是教育研究里最稳定的有效方向之一。
2. EEF 把 metacognition and self-regulation 评为高影响、低成本、证据广泛支持的方向。[EEF metacognition](https://educationendowmentfoundation.org.uk/education-evidence/teaching-learning-toolkit/metacognition-and-self-regulation/technical-appendix/queen-rania-foundation)
3. Dylan Wiliam 系列工作长期强调：教学不是等考完再评，而是 minute-by-minute 调整教学。

#### 适用场景

1. 新主题第一次进入
2. 学员回答含糊
3. 做错但错因未明
4. 学员说“我不会”“我乱了”
5. Guide completion 后回到练题

#### 不适用或应降级的场景

1. 纯服务问题
2. 用户只想要直接答案且没有教学意图
3. 当前轮没有足够学习对象

#### 鲁班标准动作

1. `quick_diagnostic_check`
2. `name_the_gap`
3. `find_and_fix`

#### 标准输出结构

1. 点出当前真正卡点
2. 说明这轮为什么这样教
3. 立即给最小下一步

### 7.2 Worked Example Teaching

#### 这是什么

先给一题高质量完整示范，让学员看到正确做法、判断路径和得分结构。

#### 为什么选它

对于新手、陌生任务、复杂边界判断，先让学员看见“正确长什么样”，通常比先让他硬做更有效。

#### 证据基础

1. Worked Example 在数学学习中的 meta-analysis 显示中等效应量，`g = 0.48`。[Barbieri et al., 2023](https://www.danamillercotto.com/uploads/4/7/7/2/47725475/barbieri_et_al__2023__we_meta-analysis.pdf)
2. 对新手尤其有效，但并不意味着永远都该一直示范。

#### 适用场景

1. 新主题首次教学
2. 学员长期基础弱
3. 题型结构复杂
4. 案例题、规范题、边界判断题

#### 不适用或应谨慎的场景

1. 学员已很熟练
2. 同一类型题重复示范过多
3. 学员已经进入自主迁移阶段

#### 鲁班标准动作

1. `worked_example`
2. `annotated_scoring_points`
3. `boundary_callout`

#### 标准输出结构

1. 完整作答或判断
2. 关键得分点
3. 为什么容易错
4. 迁移抓手

### 7.3 Scaffolding with Fading

#### 这是什么

先给支架，再逐步撤支架。支架可以是：

1. 判断骨架
2. 步骤提示
3. 半完成答案
4. 关键选项对照

#### 为什么选它

这是最适合数字 tutoring 的稳定方法之一，因为它既能避免直接放养，也能避免老师永远包办。

#### 证据基础

1. 在线学习中的 scaffolding meta-analysis 显示总体正向效果，且不同类型支架都可以发挥作用。[Scaffolding meta-analysis](https://www.mdpi.com/2227-7102/13/7/705)
2. 这也和认知学徒制、Cognitive Load 理论高度兼容。

#### 适用场景

1. 学员有一定基础，但经常做不完整
2. 知道一点，但不会组织答案
3. 长解释容易失速
4. 需要从“老师带着做”过渡到“自己能做”

#### 不适用或应谨慎的场景

1. 学员完全零基础且连示范都没见过
2. 学员已非常熟练，继续给重支架会拖累节奏

#### 鲁班标准动作

1. `minimal_scaffold`
2. `partial_completion`
3. `faded_prompt`

#### 标准输出结构

1. 给最小抓手
2. 只补当前最缺的一段
3. 留一段让学员自己完成

### 7.4 Expertise-Reversal-Aware Teaching

#### 这是什么

同一种教学法不会一直有效。新手受益于示范和支架，熟手继续吃同样支架反而会被拖慢。

#### 为什么这是鲁班必须内建的规则

这就是“因材施教”最扎实、最成熟、最不花哨的一条规律。

#### 证据基础

1. `Expertise Reversal Effect` 系统回顾明确指出：随着学员领域知识增长，原本有效的教学法会变得冗余甚至有害。[Kalyuga, 2007](https://link.springer.com/article/10.1007/s10648-007-9054-3)

#### 适用场景

1. 同一主题连续学习
2. 同类题命中率明显提升
3. 学员开始嫌“你讲太多了”

#### 鲁班标准动作

1. `worked_example -> minimal_scaffold`
2. `minimal_scaffold -> retrieval_check`
3. `retrieval_check -> transfer_challenge`

#### 核心规则

1. 新手优先示范
2. 半熟优先支架
3. 熟手优先检索、迁移、挑战

### 7.5 Contrastive Error Review

#### 这是什么

不是泛泛讲“这题为什么错”，而是把：

1. 错法
2. 对法
3. 容易混淆的边界

放到同一个对照结构里。

#### 为什么选它

建筑实务、法规边界、责任判断、程序条件类题目，很多错都不是知识完全空白，而是判定边界混掉。

#### 证据基础

1. 高质量 feedback / formative assessment 的核心不是告诉对错，而是帮助学员缩小当前表现与目标表现之间的差距。
2. EEF 和 Dylan Wiliam 体系都强调反馈应服务下一步行动，而不是只做结果播报。

#### 适用场景

1. 同类错因重复出现
2. 学员说“我怎么老是错这里”
3. 学员把相近规则混用

#### 鲁班标准动作

1. `contrastive_error_review`
2. `find_and_fix`
3. `boundary_callout`

#### 标准输出结构

1. 你错在哪
2. 正确判定点是什么
3. 下次如何一眼分开

### 7.6 Retrieval Practice Teaching

#### 这是什么

不是再讲一遍，而是逼学员从脑中把知识调出来。

#### 为什么选它

对考试提分来说，这是最稳定、最成熟、最不依赖花哨技术的高价值方法之一。

#### 证据基础

1. Dunlosky 等综述中，`practice testing` 与 `distributed practice` 获得高 utility 评价。[Dunlosky et al., 2013](https://journals.sagepub.com/doi/10.1177/1529100612453266)
2. 检索练习在课堂环境中也有稳定正向证据。[Retrieval Practice classroom review](https://link.springer.com/article/10.1007/s10648-021-09595-9)

#### 适用场景

1. 学过但不稳
2. Guide 学完后的回检
3. 复学回流
4. 错题纠正后的巩固

#### 不适用或应谨慎的场景

1. 完全新知识第一次进入
2. 学员当前状态明显崩溃、先需要稳住

#### 鲁班标准动作

1. `retrieval_check`
2. `targeted_micro_drill`
3. `short_answer_recall`

#### 标准输出结构

1. 让学员先答
2. 快速反馈
3. 立即做一题或一组微练习

### 7.7 Spacing and Successive Relearning

#### 这是什么

不是今天教完就结束，而是在间隔之后再让学员重新提取和使用同样知识。

#### 为什么选它

鲁班如果真的要做到“越用越懂你、越用越会教你”，这一层不是可选项，而是飞轮本体。

#### 证据基础

1. 间隔练习和检索练习都被认为是高 utility 学习技术。[Dunlosky et al., 2013](https://journals.sagepub.com/doi/10.1177/1529100612453266)
2. `Successive Relearning` 是 retrieval + spacing 的强组合方向。[Rawson & Dunlosky, 2022](https://journals.sagepub.com/doi/10.1177/09637214221100484)

#### 适用场景

1. heartbeat 复习触达
2. 几天后回流复学
3. 已纠正过的高价值错因
4. 高频考试核心主题

#### 鲁班标准动作

1. `spaced_revisit_assignment`
2. `delayed_retrieval_check`
3. `successive_relearning_loop`

#### 标准输出结构

1. 回看上次卡点
2. 先不提示让学员回忆
3. 若错误再进入微矫正
4. 再安排下一次复现

### 7.8 Mastery Learning

#### 这是什么

某个薄弱点没有打穿前，不盲目推进新内容。

#### 为什么选它

对考试辅导来说，很多时候不是内容不够多，而是关键错因没有打穿。

#### 证据基础

1. Mastery learning 的综述和实践回顾整体支持其正向学习效果。[Practical Review of Mastery Learning](https://www.sciencedirect.com/science/article/abs/pii/S0002945923007386)
2. 它特别适合作为鲁班“错因族治理”的核心方法。

#### 适用场景

1. 重复错因稳定存在
2. 同主题命中率持续偏低
3. 学员总想扩内容但基础还虚

#### 不适用或应谨慎的场景

1. 用户明确只是随手问一个点
2. 当前目标不是稳定掌握，而是快速过一遍大图景

#### 鲁班标准动作

1. `mastery_gate_decision`
2. `targeted_micro_drill`
3. `corrective_loop`

#### 核心规则

1. 先打穿当前弱点
2. 再决定是否扩新主题
3. 不让“假会了”直接流入下一阶段

### 7.9 Metacognitive Coaching

#### 这是什么

不仅给答案和练习，还教学生：

1. 这题怎么判断
2. 我为什么会错
3. 我下次如何自己检查
4. 我应该怎样安排下一步学习

#### 为什么选它

这部分决定鲁班像不像真正的名师，而不是只会答题。

#### 证据基础

1. EEF 把 metacognition and self-regulation 评为高影响、低成本、广泛证据支持的方向。[EEF metacognition](https://educationendowmentfoundation.org.uk/education-evidence/teaching-learning-toolkit/metacognition-and-self-regulation/technical-appendix/queen-rania-foundation)

#### 适用场景

1. 学员经常同样方式犯错
2. 学员不会自检
3. 学员需要规划复习路径
4. 学员已经有一定基础，开始追求迁移

#### 鲁班标准动作

1. `self_check_prompt`
2. `why_wrong_reflection`
3. `next_step_planning`

#### 标准输出结构

1. 给这题的判断抓手
2. 给学员一个复盘问题
3. 给一个自我检查模板

### 7.10 Pace Recovery and Supportive Coaching

#### 这是什么

这不是主教学法，而是调度层保护动作。

它处理的是：

1. 慌
2. 乱
3. 拖延
4. 长解释失速

#### 为什么仍然要写入矩阵

因为如果没有这一层，其他方法再正确，也可能在错误时机被错误交付。

#### 重要边界

1. 它服务教学，不替代教学
2. 它的目标是恢复学习可执行性，而不是制造陪伴感幻觉

#### 鲁班标准动作

1. `pace_recovery`
2. `tiny_next_step`
3. `load_reduction`

## 8. 方法选择规则

### 8.1 按学员熟练度选择

1. `新手 / 低掌握`
   - 主方法：
     - Formative Diagnostic
     - Worked Example
     - Scaffolding
   - 不宜默认：
     - 纯追问
     - 纯开放探索

2. `半熟 / 易错`
   - 主方法：
     - Scaffolding with Fading
     - Contrastive Error Review
     - Retrieval Practice

3. `较熟 / 可迁移`
   - 主方法：
     - Retrieval Practice
     - Metacognitive Coaching
     - Transfer Challenge
   - 应减少：
     - 重示范
     - 重支架

### 8.2 按任务类型选择

1. `概念理解`
   - 先：
     - Worked Example 或最短概念骨架
   - 后：
     - Retrieval check

2. `单选 / 多选 / 判断`
   - 先：
     - 判定抓手
   - 后：
     - Contrastive Error Review
     - Micro drill

3. `案例题 / 实务题`
   - 先：
     - 作答骨架
     - Worked Example
   - 后：
     - Scaffolding
     - Mastery gate

4. `错题复盘`
   - 先：
     - Contrastive Error Review
   - 后：
     - Retrieval Practice
     - Spaced revisit

### 8.3 按学习状态选择

1. `状态稳定`
   - 正常进入主教学法

2. `明显慌乱 / 过载`
   - 先：
     - Pace Recovery
     - Minimal Scaffold
   - 暂缓：
     - 长篇原理
     - 高强度追问

3. `自信但反复错`
   - 先：
     - Formative Diagnostic
     - Contrastive Error Review
   - 后：
     - Mastery gate

## 9. 标准教学序列

### 9.1 新主题首轮教学

1. 快速诊断已有基础
2. Worked Example
3. Minimal Scaffold
4. 一题微练习
5. 安排一次短期回检

### 9.2 同类错因反复出现

1. Name the gap
2. Contrastive Error Review
3. 针对性微练习
4. Mastery gate
5. Spaced revisit

### 9.3 Guide completion 后的承接

1. 回收上次 Guide 的核心结论
2. Retrieval check
3. 根据结果分流：
   - 稳：进入 stretch
   - 不稳：进入 corrective loop

### 9.4 回流复学

1. 不重新长篇讲
2. 先检索上次卡点
3. 再决定：
   - 继续推进
   - 先补漏洞

### 9.5 长解释失速

1. 停止继续铺长原理
2. 改用最小骨架
3. 让学员先做一步
4. 再按结果决定是否补原理

## 10. 对应到鲁班 runtime 的动作层

前一版因材施教 PRD 中的动作原语还不够完整。这份文档建议把动作库升级为以下 12 个标准动作：

1. `quick_diagnostic_check`
2. `name_the_gap`
3. `worked_example`
4. `minimal_scaffold`
5. `faded_prompt`
6. `contrastive_error_review`
7. `retrieval_check`
8. `targeted_micro_drill`
9. `spaced_revisit_assignment`
10. `mastery_gate_decision`
11. `self_check_prompt`
12. `pace_recovery`

第一版约束：

1. 每轮最多 `1 个主方法 + 1 个辅方法`
2. 每轮最多 `2 个显式动作`
3. 不允许同时混用 3 种以上方法
4. 不允许在低证据下做高解释度心理判断

## 11. 明确不作为第一版主方法的内容

以下方法或风格可以作为补充，但不应成为第一版主骨架：

1. 纯苏格拉底式追问
2. 纯发现式学习
3. 纯情绪陪伴
4. 纯长篇讲授
5. 纯 motivational talk
6. 纯 AI“懂你”式画像播报

原因很简单：

1. 不够稳
2. 不够可验证
3. 不够适合当前备考提分目标
4. 容易提高幻觉和反感风险

## 12. 分阶段落地建议

### 12.1 第一阶段只做 4 类主方法

当前条件下最稳的第一阶段主方法应是：

1. Formative Diagnostic
2. Worked Example
3. Contrastive Error Review
4. Retrieval + Spacing

理由：

1. 这 4 类证据更成熟
2. 与考试提分场景更直接
3. 更容易进入日志与效果评估

### 12.2 第二阶段再补 3 类增强方法

第二阶段补：

1. Scaffolding with Fading
2. Mastery Learning
3. Metacognitive Coaching

### 12.3 Pace Recovery 作为全阶段保护层

这层从一开始就应存在，但不要把它包装成主价值，而应作为安全和节奏控制层。

## 13. 成功定义

### 13.1 用户体感

学员应能明确感知到：

1. 不是每次都同一种讲法
2. 系统会根据我到底卡在哪来换教法
3. 它安排的题和回顾更像冲着我的错因来
4. 它不会一上来就把整套原理砸给我

### 13.2 教学结果

第一阶段至少要看到：

1. 同类错因复发率下降
2. 新主题首轮理解成功率上升
3. Guide completion 后承接更顺
4. heartbeat 复学回流点击后继续学习率上升

### 13.3 失败信号

出现以下任一情况，应判定施教层设计偏离：

1. 方法名越来越多，但没有效果差异
2. prompt 越来越长
3. 学员觉得“被分析”，但提分无改善
4. 同一方法被无差别套用在所有人身上
5. 新手和熟手吃到一模一样的教学动作

## 14. 不确定性与验证方案

### 14.1 当前仍不确定的点

1. 哪种方法组合最适合建筑实务案例题
2. metacognitive coaching 的最佳表达密度
3. spaced revisit 的最佳时间窗
4. 对高压备考用户，worked example 和 retrieval 的最佳比例

### 14.2 验证方法

1. 先做 shadow policy
2. 先聚焦 3 个高频错因族
3. 同一错因族比较不同教学序列
4. 优先看：
   - 错因纠正率
   - 二次命中率
   - 继续学习率

### 14.3 保守替代方案

如果某些方法在早期证据不稳定，保守替代方案应是：

1. 回退到 Formative Diagnostic
2. 用 Worked Example 或 Minimal Scaffold 保底
3. 不做高强度个性化推断

## 15. 研究与来源基础

本 PRD 的方法骨架主要基于以下公开研究与权威证据源：

1. 一对一辅导与 targeted support
   - [EEF One to One Tuition](https://educationendowmentfoundation.org.uk/education-evidence/teaching-learning-toolkit/one-to-one-tuition)

2. 元认知与自我调节
   - [EEF Metacognition and Self-Regulation](https://educationendowmentfoundation.org.uk/education-evidence/teaching-learning-toolkit/metacognition-and-self-regulation/technical-appendix/queen-rania-foundation)

3. 高 utility 学习技术
   - [Dunlosky et al., 2013](https://journals.sagepub.com/doi/10.1177/1529100612453266)

4. Worked Example 效应
   - [Barbieri et al., 2023 meta-analysis](https://www.danamillercotto.com/uploads/4/7/7/2/47725475/barbieri_et_al__2023__we_meta-analysis.pdf)

5. Scaffolding 效果
   - [The Effects of Using Scaffolding in Online Learning: A Meta-Analysis](https://www.mdpi.com/2227-7102/13/7/705)

6. Successive Relearning
   - [Rawson & Dunlosky, 2022](https://journals.sagepub.com/doi/10.1177/09637214221100484)

7. Expertise Reversal
   - [Kalyuga, 2007](https://link.springer.com/article/10.1007/s10648-007-9054-3)

## 16. 最终判断

鲁班当前最缺的，不是更多“因材”的数据，而是更像名师的“施教方法层”。

而这层的最佳做法，不是继续堆流派名词，不是做一个巨大教育哲学百科，也不是凭感觉拼 prompt。

而是：

1. 用成熟研究选方法
2. 用考试场景收口方法
3. 用 runtime 动作实现方法
4. 用结果闭环验证方法

这才是鲁班真正从“懂学员”走向“会教人”的下一步。
