# PRD：LLM 原生统一 Active Object 与语义路由体系

## 1. 文档信息

- 文档名称：LLM 原生统一 Active Object 与语义路由体系 PRD
- 文档路径：`/doc/plan/2026-04-18-llm-native-active-object-semantic-router-prd.md`
- 创建日期：2026-04-18
- 适用范围：统一 `/api/v1/ws`、turn runtime、ChatOrchestrator、TutorBot、练题、追问、学习计划、通用问答、微信小程序主链路
- 状态：Draft v1
- 关联文档：
  - [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)
  - [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)
  - [2026-04-15-unified-ws-full-tutorbot-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-15-unified-ws-full-tutorbot-prd.md)
  - [2026-04-15-learner-state-memory-guided-learning-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-15-learner-state-memory-guided-learning-prd.md)
  - [2026-04-16-tutorbot-context-orchestration-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-16-tutorbot-context-orchestration-prd.md)

## 2. 背景

DeepTutor 当前已经具备：

1. 统一聊天入口 `/api/v1/ws`
2. `chat / deep_question / tutorbot` 等能力层
3. 会话状态、活跃题目上下文、长期记忆、上下文编排
4. 微信小程序、WebSocket、TutorBot runtime 的主链路

但当前系统仍存在一个更上游的结构问题：

- 系统已经能“出题”
- 系统也已经能“批改”
- 系统还能“继续追问”

问题不在单点能力缺失，而在**如何稳定地把下一轮用户话语和当前正在进行的学习对象接起来**。

当前系统最容易翻车的地方，不是模型答不出来，而是：

1. 用户明明在继续回答当前题目，系统却把它当普通聊天
2. 用户明明在追问当前解释，系统却把它当新请求
3. 用户明明在切换到其他话题，系统却还背着旧题目上下文
4. 用户连续经历“出题 -> 作答 -> 改答案 -> 追问 -> 再出题”时，语义 authority 不够单一

这说明系统当前最大的短板不是“某个 parser 太弱”，而是**当前语义 authority 被拆散到了多个中间状态、多个判断点和多个 fallback 里**。

## 3. 问题定义

### 3.1 当前根因不是 regex，而是语义 authority 不唯一

当前系统围绕练题 follow-up 已经存在多层表达：

1. `active_question_context`
2. `question_followup_context`
3. `question_followup_action`
4. orchestrator 内部 follow-up 选择
5. regex submission parser

这些设计各自都能解释一部分问题，但组合在一起就会形成长期风险：

1. 同一个业务事实被多个中间结构重复表达
2. 语义判断在多个层重复发生
3. route selection 与 parser fallback 容易争抢 authority
4. 任何新输入形式都会诱发“再补一条规则”的冲动

### 3.2 真正的一等业务事实是什么

系统每轮真正要回答的核心问题只有一个：

> 当前用户这句话，与当前活跃学习对象之间，是什么关系？

可能的关系包括：

1. 正在回答它
2. 正在修改刚才的回答
3. 正在追问它
4. 正在要求继续同类练习
5. 正在切换到新的学习对象
6. 正在切出学习域，进入通用问答或产品问答

这本质上是**语义承接判断**，不是字符串分类问题。

### 3.3 如果不重构，系统会长期陷入什么循环

1. 每出现一种新的回答表达，就想补 regex
2. 每出现一种新的歧义输入，就想加一层 interpreter
3. 每出现一次误路由，就想多加一个 state 字段
4. 系统越来越能“处理特例”，但越来越不像一个统一系统

这就是 patch spiral。

## 4. 产品目标

### 4.1 最终目标

把 DeepTutor 升级为一个在以下场景都保持世界级稳定性的统一智能体：

1. 通用对话
2. 学习辅导
3. 练题生成
4. 作答识别
5. 改答案
6. 题目追问
7. 学习计划/Guided Learning
8. 学习中途切题与回切

目标不是“某个题型更准一点”，而是：

> 不管用户如何自然表达，系统都能围绕当前活跃对象保持语义连续、能力连续、状态连续。

### 4.2 体验目标

1. 用户刚拿到一组题，下一句无论说“我选 B”“ACD”“第二题改 C”“这个为什么不对”，系统都应优先围绕当前题组理解。
2. 用户中途问“我还有多少点数”“你叫什么”“怎么开会员”，系统应允许快速切出，不被旧题目绑架。
3. 用户在学习计划、讲解、练题之间切换时，系统应保持 continuity，而不是每次都像新会话。
4. 用户可以用随意、口语、紧凑、半省略的表达，系统仍能理解当前关系。
5. 同一状态下，相似输入应得到相似决策；不同状态下，同一句话可以被正确理解为不同关系。

### 4.3 世界级目标

本 PRD 的目标水准不是“比现在少错几个 case”，而是具备顶尖智能体的共同特征：

1. 单一语义 authority
2. 当前 active object 优先
3. 主 LLM 承担语义判断，而不是只做润色
4. 程序层负责边界、验证、执行，而不是替代语义理解
5. 路由、状态、trace 可解释、可回放、可审计

### 4.4 当前条件下的最优解定义

这里必须明确：

“世界级”不等于“当前就做最复杂、最激进、概念最多的系统”。

在当前代码基础、当前产品压力、当前发布条件下，本 PRD 追求的**最优解**是：

1. 在不新增第二套入口、不新增第二套主脑、不引入专用小模型主路由器的前提下
2. 最大化利用主 LLM 的语义理解能力
3. 最小化中间状态和重复判断点
4. 通过最小但足够的对象模型实现稳定 continuity
5. 用 trace、灰度、回滚把风险压到可交付范围内

也就是说：

- 这份 PRD 追求的是 **最稳健的全球顶尖水准**
- 不是 **最花哨的全球顶尖想象**

如果某个方案理论上更强，但当前阶段会明显增加概念、状态、路由层、回滚难度、验证成本，那它就不是当前条件下的最优解。

## 5. 非目标

本 PRD 明确不做：

1. 不新增第二套聊天入口
2. 不新增独立的小模型路由器作为默认主链路
3. 不为 follow-up 单独长出一套新业务身份
4. 不把 regex 升级为主决策 authority
5. 不为单一题型写死特化架构
6. 不让“出题场景”单独长成一套平行 runtime

## 6. 第一性原理与设计原则

### 6.1 First Principles

1. 当前活跃对象优先于输入表面形式
2. 语义关系优先于 capability 名字
3. 主 LLM 应负责语义承接判断
4. 程序应负责约束、验证、应用、回放
5. 当前轮语义解释不是长期业务事实

### 6.2 Less Is More

1. 不新增多余中间概念
2. 不新增多套语义状态
3. 不新增重复路由判断点
4. 不让多个模块分别理解“当前这句话是什么意思”
5. 不让 fallback 长期承担主理解职责

### 6.3 单一 authority 原则

必须明确区分两类东西：

1. **稳定业务事实**
   - 当前活跃对象是谁
   - 该对象当前状态是什么

2. **瞬时 turn 解释**
   - 当前用户这句话与该对象是什么关系

前者可以持久化，后者只应作为当前 turn 的结构化 decision 使用。

## 7. 目标架构

## 7.1 一个持久化一等对象：`active_object`

系统不应再围绕 follow-up 长多个并列概念，而应收敛到一个统一的活跃对象：

- `active_object`

它可以是：

1. `question_set`
2. `single_question`
3. `guide_page`
4. `study_plan`
5. `lesson_topic`
6. `open_chat_topic`
7. `account_task`

核心不是对象名字，而是：

- 当前用户到底正围绕什么对象继续交互

为了让这个对象真正可执行，`active_object` 至少应包含：

1. `object_type`
2. `object_id`
3. `scope`
4. `state_snapshot`
5. `version`
6. `entered_at`
7. `last_touched_at`
8. `source_turn_id`

说明：

1. `object_type`
   - 有限枚举，不允许自由文本乱长。
2. `object_id`
   - 必须是该对象在当前 session 内稳定可引用的 ID。
3. `scope`
   - 定义这次允许修改、解释、批改的边界，避免 LLM 任意越界。
4. `state_snapshot`
   - 只保留当前轮理解所必需的最小快照，不把整段历史塞进对象。
5. `version`
   - 用于并发更新和 replay 对比。

### 7.1.1 当前条件下的最优折中：一个 active + 一个小型 suspended stack

只保留一个 `active_object` 是对的，但在真实产品里，用户会频繁：

1. 中途切题
2. 问账户问题
3. 临时问解释
4. 再回到刚才的题或 guide 页面

因此当前条件下最稳妥、最可交付的做法不是“只有一个活跃对象，其他都丢掉”，而是：

1. **一个唯一 `active_object`**
2. **一个很小的 `suspended_object_stack`**
   - 长度建议 `<= 3`
   - 只用于回切与解释，不参与并列决策

这样可以同时满足：

1. authority 仍然唯一
2. 支持真实产品中的短期回切
3. 不把系统升级成复杂对象图或多主状态机

这是一种符合 `less is more` 的工程折中：

- 不是全图谱
- 不是多活跃对象
- 不是无限历史对象池
- 只是为真实使用场景保留最小恢复能力

### 7.2 一个当前轮结构化决策：`turn_semantic_decision`

每轮由主 LLM 基于：

1. `user_utterance`
2. `active_object`
3. 最小必要的最近对话
4. 必要的长期上下文

输出一个结构化决策，但必须是**有限 schema**，不能让主 LLM 直接返回自由文本路由意见。

建议 schema 至少包含：

1. `relation_to_active_object`
2. `next_action`
3. `target_object_ref`
4. `allowed_patch`
5. `confidence`
6. `reason`

它是**当前轮的语义解释结果**，不是长期 truth。

### 7.2.1 推荐的有限枚举

`relation_to_active_object` 建议限定为：

1. `answer_active_object`
2. `revise_answer_on_active_object`
3. `ask_about_active_object`
4. `continue_same_learning_flow`
5. `switch_to_new_object`
6. `temporary_detour`
7. `out_of_scope_chat`
8. `uncertain`

`next_action` 建议限定为：

1. `route_to_grading`
2. `route_to_followup_explainer`
3. `route_to_generation`
4. `route_to_guide`
5. `route_to_general_chat`
6. `route_to_account_or_product_help`
7. `ask_clarifying_question`
8. `hold_and_wait`

### 7.2.2 为什么不用自由 `state_patch`

LLM 可以理解语义，但不应直接拥有无限制 patch 权限。

因此这里不建议让模型自由输出任意 `state_patch`，而应改成：

- `allowed_patch`

它只能落在有限操作集里，例如：

1. `update_answer_slot`
2. `append_answer_slots`
3. `set_active_object`
4. `suspend_current_object`
5. `resume_suspended_object`
6. `clear_active_object`
7. `no_state_change`

程序层再把这些操作映射到真正的数据更新。

这样做的原因是：

1. 主 LLM 负责理解
2. 程序负责约束写入边界
3. replay 与审计更稳定
4. 不会把 runtime 变成“模型直接写状态”的黑箱

### 7.3 程序层的职责

程序层必须只做四件事：

1. 恢复 canonical `active_object`
2. 校验 `turn_semantic_decision`
3. 应用允许的状态更新
4. 调用对应 capability / tool 执行

程序层不应再在多个地方各自重新理解语义。

### 7.3.1 程序层还必须负责“不乱猜”

如果满足以下任一条件，程序层必须允许 `ask_clarifying_question` 或 `hold_and_wait`，而不是强行猜：

1. `confidence` 低于阈值
2. 当前语句可能同时指向多个对象
3. 当前修改会影响多个答案槽位
4. 用户疑似在切回旧对象，但指代不清
5. 低置信下继续执行会造成明显错误后果

顶尖系统不是“永远直接答”，而是知道什么时候不该乱答。

### 7.4 fallback 的正确位置

`regex`、状态机、局部规则仍然可以保留，但只能用于：

1. 边界明确、格式稳定、低歧义输入
2. 主 LLM 输出空、低置信或无效结构化决策时的保底

也就是说：

- fallback 是保底，不是主脑
- deterministic parser 是 apply 层助手，不是语义 authority

### 7.4.1 高风险动作必须走双保险

以下动作建议采用“LLM 主判定 + deterministic 校验”的双保险：

1. 批量答案写入
2. 修改已有答案
3. 活跃对象切换
4. 从通用聊天切回旧对象
5. 跨对象引用编号、题号、页号

原因：

1. 这些动作不是纯理解问题，还涉及边界和副作用
2. 顶尖系统不是把所有问题都丢给模型，而是把**高风险理解**与**高风险执行**拆开

### 7.5 Active Object 生命周期

`active_object` 必须具备明确生命周期，否则路由再聪明也会失控。

建议生命周期只有以下几类：

1. `entered`
2. `active`
3. `suspended`
4. `completed`
5. `abandoned`
6. `expired`

#### 7.5.1 进入条件

对象进入 `active` 的条件必须清晰：

1. 系统明确创建了新的题组/题目/guide page/plan step
2. 用户明确切换到另一个对象
3. 当前对象被恢复且被当前轮重新确认

#### 7.5.2 退出条件

对象退出 `active` 也必须清晰：

1. 用户显式完成
2. 用户显式放弃
3. 用户切换到其他对象
4. 超过 TTL 且无恢复信号

#### 7.5.3 不允许的状态

不允许出现：

1. 同一 session 多个 `active_object`
2. 活跃对象没有 stable ID
3. 活跃对象退出后仍偷偷参与主路由
4. 已过期对象仍被当成当前对象

### 7.6 当前轮解析顺序

为保证实现收敛，建议 turn runtime 每轮固定按以下顺序工作：

1. 恢复 `active_object`
2. 恢复 `suspended_object_stack`
3. 构造最小必要上下文包
4. 调用主 LLM 生成 `turn_semantic_decision`
5. 程序校验 decision
6. 若低置信或高风险冲突，则澄清或保守降级
7. 选择 capability / tool
8. 执行允许的状态更新
9. 写 trace 与 replay 元数据

顺序固定的意义是：

1. 方便调试
2. 方便 trace
3. 方便稳定灰度
4. 避免多个模块各自先做一遍解释

### 7.7 多对象与回切策略

真实用户不会线性对话，因此本 PRD 必须明确“怎么回切”，否则 `active_object` 仍会在真实流里漂。

#### 7.7.1 回切优先级

建议：

1. 明确指代当前活跃对象
2. 明确指代 suspended stack 顶部对象
3. 明确 ID / 编号 / 页面标识
4. 明确“上一题 / 刚才那个计划 / 那个页面”
5. 无法确定则澄清，不猜

#### 7.7.2 为什么不做对象图

当前条件下不建议直接做多对象图、对象关系图谱、对象间任意跳转引擎。

原因：

1. 复杂度过高
2. 当前业务还没有足够稳定的对象 schema
3. 会把这次整改从“收敛 authority”重新带回“再长一套系统”

所以当前最优策略是：

- 一个 active
- 一个小 suspended stack
- 一个清晰回切优先级
- 一个明确澄清机制

## 8. 当前设计如何迁移

### 8.1 迁移原则

当前已有字段不必一次性删除，但必须立即降级为兼容层。

要求：

1. 旧字段只能在入口层读取
2. 进入 runtime 后立刻归一到统一 `active_object`
3. 不允许旧字段继续参与并列决策

### 8.2 字段收敛方向

建议收敛为：

1. `active_object`
2. `turn_semantic_decision`

并逐步淡化：

1. `active_question_context`
2. `question_followup_context`
3. `question_followup_action`

这些旧字段未来最多作为：

- alias
- adapter 输入
- migration 期间兼容字段

### 8.3 与旧 PRD 的关系

本 PRD 不否定已有 context orchestration / learner-state / unified ws 设计。

但它明确修正一个旧方向：

- 对“当前轮与当前对象的关系判断”，不能再默认 `rules/state-machine first, LLM fallback`
- 在这一类问题上，应改为 `active object first, primary LLM semantic decision first, deterministic apply second`

## 9. 关键场景

本 PRD 必须覆盖以下高风险真实场景：

### A. 出题后立即作答

- “我选B”
- “ACD”
- “第二题选C”
- “1A2C3D”

要求：

- 不依赖 renderer 猜
- 不依赖 capability 名字猜
- 必须优先围绕当前 `active_object=question_set` 理解

### B. 作答后改答案

- “第二题改成C，其他不变”
- “刚才第一题我手滑了，应该选D”

要求：

- 修改只作用于允许 scope
- 不能重建第二套答案状态

### C. 追问当前题

- “为什么错”
- “这题考点是什么”
- “你讲一下第二题”

要求：

- 默认继续围绕当前对象
- 不要掉回泛化聊天

### D. 当前学习流中途切题

- “我还有多少点数”
- “怎么开会员”
- “今天天气怎么样”

要求：

- 允许快速切出
- 但不丢失可恢复的 `active_object`

### E. 学习对象切换再回切

- 出题 -> 问讲义 -> 回到题目
- Guided Learning -> 问账户 -> 回到当前页面

要求：

- active object 切换必须可解释
- 回切不应靠运气命中

### F. 用户同时表达两个意图

- “我选 A，然后你顺便讲一下第二题”
- “第2题改 C，再给我来两题类似的”

风险：

- 系统只吃到第一个意图
- 或把第二个意图错误升级为主动作

要求：

1. 当前轮必须有主动作概念
2. 若多意图都重要，允许拆成主动作 + 次动作
3. 当前条件下先保证主动作正确，不追求一次性完美并行动作执行

### G. 用户引用错误对象

- “不是这题，是上一题”
- “不是这个页面，是刚才那个计划”

风险：

- 系统沿当前 `active_object` 硬做

要求：

1. 必须支持“纠正当前对象”
2. 纠正动作优先级高于沿当前对象继续解释

### H. 当前对象已不可见，但仍在对它说话

- 用户滚出题卡
- renderer 没显示完整结构
- 用户只凭记忆继续作答

风险：

- 系统错误依赖 renderer 可见性

要求：

1. 路由不得以 renderer 是否显示完整内容作为 authority
2. 只要 `active_object` 还有效，就应允许围绕它理解

### I. 同一 session 连续出了两组题

- 第一组没答完，又让系统再来五题
- 然后用户回答“ACD”

风险：

- `ACD` 指向哪一组题不清楚

要求：

1. 新题组进入 active 前，旧题组必须被 suspend 或 complete
2. 对无编号紧凑输入，如存在多可疑对象，必须澄清，不猜

### J. 用户使用极度口语化表达

- “第二个吧”
- “刚那个不对”
- “前两个我都不太确定”
- “上面那个理由我不服”

风险：

- 如果没有稳定对象和槽位信息，系统很容易乱解释

要求：

1. 主 LLM 必须看到最小但足够的对象快照
2. 对指代不清的对象或槽位允许追问澄清

## 10. 失败模式与反模式

这部分必须写清楚，否则实施时很容易又滑回旧模式。

### 10.1 失败模式

1. `active_object` 存在，但 route 仍优先相信局部 parser
2. 主 LLM 已给出明确 decision，但后续又被第二层规则改写
3. 低置信 decision 仍然直接执行
4. 活跃对象切换没有 trace
5. suspended object 无限增长
6. 一个对象的局部快照过大，重新造成上下文污染

### 10.2 必须避免的反模式

1. 再长一套 `*_followup_*` 并列概念
2. 再做一个默认常驻的小模型 router
3. 再把语义判断拆给多个模块各做一遍
4. 为每种表达单独补 regex
5. 把“低置信也要继续跑”误当成体验优化

## 11. 观测与回放要求

每轮 trace 至少应能回答：

1. 当前 `active_object` 是谁
2. 当前 `suspended_object_stack` 是什么
3. 本轮主 LLM 判定的 `turn_semantic_decision` 是什么
4. 为什么选择了该 capability
5. 是否触发 fallback
6. fallback 是因为什么触发
7. 最终是否更新了 `active_object`
8. 是否发生了对象切换 / suspend / resume / clear

### 11.1 必须支持的调试视图

1. 看一轮 turn 的输入对象快照
2. 看 LLM 原始 decision 与程序校验后的 decision
3. 看为何进入澄清分支
4. 看为何发生对象切换
5. 看是否存在旧字段兼容路径参与

如果 trace 不能解释这些问题，就说明架构仍不够收敛。

## 12. 验收标准

### 12.1 结构验收

1. 当前轮语义决策只有一个主 authority
2. 旧 follow-up 字段不再并列参与路由主判断
3. 主链路不需要单独的小模型 router 才能工作
4. 新设计不新增第二套聊天入口
5. 不允许多个模块分别持有自己的“当前对象”

### 12.2 体验验收

1. 出题后作答识别成功率显著提升
2. 紧凑、口语、半省略输入下仍能稳定围绕当前对象理解
3. 中途切题时不被旧对象错误绑架
4. 回到旧对象时 continuity 稳定
5. 对真正不确定的输入，系统宁可澄清也不乱猜

### 12.3 线下评测验收

至少要建立以下固定评测集：

1. `question generation -> answer -> revise -> followup -> continue generation`
2. `guide page -> ask product question -> return to guide`
3. `general chat -> enter practice -> answer compactly -> switch topic`
4. `multiple active-object switches in one long dialog`
5. `same utterance under different active objects`
6. `ambiguous utterance requiring clarification`
7. `renderer incomplete but active object still valid`
8. `two recent question sets with compact answer ambiguity`

### 12.4 线上验收

不能只靠单测。

必须补：

1. Langfuse trace 样本审查
2. 长对话 replay
3. 微信小程序真实回归
4. 不同表达风格用户样本回放
5. 线上低置信触发率统计

### 12.5 当前条件下建议的门槛

当前阶段不宜一开始就承诺绝对准确率，但必须至少达到以下门槛：

1. 当前对象明确存在且输入低歧义时，应稳定命中正确主动作
2. 当前对象不明确且存在多个候选时，应优先进入澄清而不是误执行
3. 新架构上线后，误把答题输入打回通用 chat 的比例应明显下降

## 13. 测试、评测与发布要求

### 13.1 单元测试

1. `active_object` 恢复
2. `suspended_object_stack` 管理
3. decision schema 校验
4. allowed patch 应用
5. low-confidence gate
6. object switch / suspend / resume

### 13.2 集成测试

1. 出题后单题回答
2. 出题后批量回答
3. 改答案
4. 追问解释
5. 中途切题后回切
6. 不同 active object 下同句异义

### 13.3 红队场景

1. “不是这题，是上一题”
2. “别讲了，先告诉我还剩多少点数”
3. “ACD” 但当前 session 有两组最近题
4. “第二个吧” 但当前对象槽位不足
5. “继续” 但当前对象既可能是题组，也可能是 guide 页面
6. 用户连续三次快速切对象

### 13.4 灰度前置条件

正式上线前必须具备：

1. feature flag：可单独开关新 semantic router
2. shadow mode：新旧路由可并行出决策但只执行旧链路
3. rollback：一键退回旧逻辑
4. trace：至少能看到 `active_object / decision / fallback / object transition`
5. 固定评测集：可做前后对比

### 13.5 灰度策略

建议按以下顺序灰度：

1. 仅在练题场景 shadow
2. 再在练题场景低流量真实执行
3. 再扩到 guide / study plan
4. 最后扩到通用学习主链路

原因：

1. 练题对象边界最清晰
2. 最适合先验证 active object 思路
3. 可以先把高价值、高确定性场景打稳

### 13.6 回滚条件

以下指标上升，视为落地失败或需回滚：

1. 当前题追问中的答非所问率上升
2. 误切对象率上升
3. 低置信仍误执行的比例上升
4. P95 延迟明显恶化
5. 微信小程序连续对话稳定性下降

## 14. 分阶段实施

### Phase 0：前置准备

1. 明确 `active_object` 最小 schema
2. 明确 `turn_semantic_decision` 最小 schema
3. 建好 shadow mode 与 trace
4. 建好固定评测集

### Phase 1：练题域收敛

1. 先把 question generation / answer / revise / followup / continue generation 收到统一 active object
2. 旧字段入口归一化
3. regex 退回 deterministic fallback

### Phase 2：多对象切换与回切

1. 引入小型 `suspended_object_stack`
2. 打通对象切换、回切、澄清
3. 验证“中途切题再回来”的真实产品链路

### Phase 3：扩展到全学习域

1. 从 question_set 扩到 guide_page / study_plan / lesson_topic
2. 统一学习流中的对象生命周期
3. 打通学习对象间切换

### Phase 4：清退旧概念

1. 清退 `question_followup_*` 并列决策职责
2. 删除重复 parser / route 分支
3. 只保留兼容 alias

## 15. 不确定性、验证与替代方案

### 15.1 当前不确定性

1. 单一 `active_object + 小 suspended stack` 是否足以覆盖绝大多数真实回切场景
2. 主 LLM 在极口语、极省略表达下的 decision 稳定性是否足够
3. 不同 object type 是否能共用一套 decision schema 而不变得过泛
4. 微信小程序真实输入风格是否比当前测试集更松散

### 15.2 验证方案

对上述不确定性，建议按以下方式验证：

1. `active_object + stack`：
   - 先做真实长对话样本回放
   - 统计回切是否超过 3 层
2. 主 LLM decision 稳定性：
   - 对同状态下同类输入做多次 replay
   - 看 label 漂移率
3. 通用 schema：
   - 先在 `question_set` 跑稳
   - 再扩到 `guide_page`
   - 不允许一开始全域泛化
4. 微信输入风格：
   - 从 Langfuse 抽真实样本
   - 按表达风格聚类补评测集

### 15.3 当前条件下的最优替代方案

如果某些目标在当前条件下不稳，应采用以下收敛路线，而不是继续加复杂度：

1. 若跨对象 schema 太泛：
   - 先只做 `question_set / guide_page`
   - 暂不推广到所有对象类型
2. 若 `suspended_object_stack` 仍不稳：
   - 降级为长度 1 的最近对象恢复
   - 暂不支持更深回切
3. 若主 LLM 对某类高风险动作不稳：
   - 保留主 LLM 做理解
   - 但将执行前校验收紧为 deterministic gate
4. 若某类输入长期低置信：
   - 优先进入澄清
   - 不继续补无限 regex

### 15.4 明确不建议的替代方案

当前不建议：

1. 直接上专用小模型 router 作为主入口
2. 再造一套 follow-up interpreter 服务
3. 直接做多对象图谱型 runtime
4. 继续围绕旧 follow-up 字段打补丁演进

这些方案短期可能有效，但长期大概率重新制造第二套 authority。

### 15.5 为什么这份方案优于几个看似更强的方向

#### 方向 A：专用小模型 / 小服务做语义 router

看起来的好处：

1. 可以把路由职责单独抽离
2. 可独立调 prompt / model

为什么当前不选：

1. 增加一套新的系统边界
2. 增加第二个语义 authority
3. 增加 trace 与回放复杂度
4. 增加线上失败与降级链路

结论：

- 这在某些超大规模系统中可能有意义
- 但在当前阶段更像提早长出第二套系统

#### 方向 B：直接做多对象图 / 会话对象图谱

看起来的好处：

1. 理论上最灵活
2. 可以支持复杂回切、对象关系和多线程对话

为什么当前不选：

1. object schema 还不稳定
2. 实施成本和验证成本过高
3. 极易把这次“收敛 authority”变成“再造一个复杂 runtime”

结论：

- 这是潜在远期方向
- 不是当前条件下最稳健的交付解

#### 方向 C：继续在旧 follow-up 结构上增量演进

看起来的好处：

1. 改动小
2. 上线快

为什么当前不选：

1. 根因不变
2. authority 仍不唯一
3. patch spiral 会继续

结论：

- 这不是优化
- 只是把结构问题继续后拖

## 16. 风险与取舍

### 风险 1：主 LLM decision 过于灵活，导致线上漂移

应对：

1. 强 schema
2. 有限枚举
3. 低置信 gate
4. 高风险动作双保险

### 风险 2：对象模型设计过重，实施成本失控

应对：

1. 先 question_set
2. 再 guide_page
3. 暂不做对象图

### 风险 3：回切能力不够，用户觉得“系统还是忘了”

应对：

1. 小型 suspended stack
2. 明确澄清机制
3. 用真实长对话样本校准深度

### 风险 4：trace 做不透，线上无法解释错误

应对：

1. 先做 shadow mode
2. 先补 trace 再放量
3. 不满足 trace 要求不上线

## 17. 本 PRD 的核心

本 PRD 的核心不是“让 follow-up 判断更聪明”。

而是：

1. 把系统从“多个局部解释器拼出来的行为”收敛成“一个统一语义 authority 驱动的行为”
2. 让主 LLM 真正承担语义承接判断
3. 让程序只负责边界和执行
4. 让系统在对话、学习、答题三类场景中都表现得像一个统一智能体，而不是几个能力的松散拼接
5. 在当前条件下，用最小但足够的对象模型达成可交付结果，而不是再次陷入宏大但不可落地的架构幻想

如果这个目标没有做到，即便某些 case 识别率上升，也不算完成。
