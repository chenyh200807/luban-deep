# PRD：微信小程序结构化教学渲染体系升级

## 1. 文档信息

- 文档名称：微信小程序结构化教学渲染体系升级 PRD
- 文档路径：`/docs/plan/2026-04-16-wechat-structured-teaching-renderer-prd.md`
- 创建日期：2026-04-16
- 状态：Draft v3
- 适用范围：
  - `wx_miniprogram/`
  - `yousenwebview/packageDeeptutor/`
  - 微信小程序聊天页教学内容渲染
  - TutorBot 教学回答在移动端的最终呈现层
- 关联文档：
  - [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)
  - [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)
  - [2026-04-15-unified-ws-full-tutorbot-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-15-unified-ws-full-tutorbot-prd.md)
  - [2026-04-15-yousen-deeptutor-fusion-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-15-yousen-deeptutor-fusion-prd.md)
  - [2026-04-15-learner-state-memory-guided-learning-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-15-learner-state-memory-guided-learning-prd.md)
  - [2026-04-16-tutorbot-context-orchestration-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-16-tutorbot-context-orchestration-prd.md)

### 1.1 当前执行状态（2026-04-16）

已完成第一批内部渲染 schema 注册，但**尚未升级为对外稳定 contract**。

当前已注册的最小内部 schema：

1. `canonical_message`
2. `mcq_block`
3. `table_block`
4. `formula_block`
5. `chart_block`
6. `steps_block`
7. `recap_block`
8. `render_model`

当前落点：

1. [wx_miniprogram/utils/render-schema.js](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/wx_miniprogram/utils/render-schema.js)
2. [yousenwebview/packageDeeptutor/utils/render-schema.js](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview/packageDeeptutor/utils/render-schema.js)
3. [deeptutor/services/render_presentation.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/services/render_presentation.py)

当前原则：

1. 这批 schema 先作为前端内部单一真相与 adapter 层使用
2. 暂不进入 `contracts/index.yaml`
3. 暂不进入 `deeptutor/contracts/` 作为对外稳定 schema
4. 待 block taxonomy、双端实现和 `/api/v1/ws` 载荷边界稳定后，再评估 contract 升级

当前新增状态：

1. 服务端结果装配层已产出内部 `presentation`
2. 当前 canonical producer 已覆盖 `mcq / table / formula_inline / formula_block / chart / steps / recap`
3. `wx_miniprogram` 与 `yousenwebview` 已通过统一 `ai-message-state -> render model -> WXML` 主链路消费 `presentation.blocks`
4. 产出位置先复用 `result.metadata.presentation`
5. 不改 `/api/v1/ws` 顶层 transport 外壳
6. `SQLiteSessionStore` 已提供统一回填能力，但不再在正常读取路径做 legacy `summary` 自动投影
7. 已提供离线回填脚本 `scripts/backfill_message_presentations.py`
8. `mobile.py` 已收口为只消费 `presentation`，不再在路由层从 `summary` 反推题卡
9. `wx` / `webview` render parity 与 Python producer 测试已通过，覆盖 `mcq / table / formula / chart / steps / recap`
10. 当前 P0-P3 的代码链路已闭环，但 P2 / P3 的真机 gate 仍待完成
11. canonical producer 已直接输出 `steps.steps` 与 `recap.title/summary/bullets`，不再依赖前端把 transport shape 二次改写成主形状
12. 双端聊天页已提供 devtools 专用 fixture 注入入口，可直接把结构化样例灌入当前页面做开发者工具验证

## 2. 执行摘要

当前微信小程序前端已经能渲染普通文本、列表、引用、代码块、表格和选择题卡片，但整体仍停留在：

1. 以 Markdown 文本为主真相
2. 以启发式检测补足结构化内容
3. 由多个阶段重复推导渲染状态
4. 在 `wx_miniprogram` 与 `yousenwebview/packageDeeptutor` 中镜像维护

这使系统在教学场景下很容易出现三类问题：

1. **内容语义不稳定**
   - 同一条回答，服务端表达的是“教学内容”，前端收到的却主要还是一段自由文本。
   - 选择题、表格、公式、图表等强结构内容只能靠前端猜。

2. **渲染结果不确定**
   - 文本、Markdown、题卡、流式状态之间存在覆盖和条件竞争。
   - 一旦流式阶段、完成阶段、交互阶段之间状态没有统一真相，就容易出现“题出了但不能选”“题有了但不显示”“正文覆盖题卡”等问题。

3. **演进成本高**
   - 现在还能靠修补收住选择题。
   - 但如果后续再加入公式、图表、富表格、题组、讲评卡片，继续堆 Markdown 规则和前端兜底，系统会快速进入补丁螺旋。

本 PRD 的核心主张是：

**不要继续把微信渲染器建设成“更复杂的 Markdown 猜测器”，而要把它升级为“结构化教学内容渲染器”。Markdown 继续保留，但降级为普通文本 projection 与兼容层。**

目标是让 DeepTutor 在微信小程序中达到顶尖教学产品应有的内容呈现标准：

1. 普通教学对话稳定、清晰、可流式
2. 选择题永远以显式题卡渲染，不再依赖文本猜题
3. 表格在手机上可读、可横滑、可压缩、不炸布局
4. 公式可以可靠显示，而不是显示成原始 LaTeX 垃圾串
5. 未来图表走结构化 block，而不是让前端从文本里猜图
6. `wx_miniprogram` 与 `yousenwebview` 共享同一套渲染语义与测试基线

## 3. 背景

### 3.1 当前项目方向已经非常明确

从现有 `docs/plan` 主线可以看出，项目已经确定了三个关键方向：

1. **统一 TutorBot 与统一入口**
   - 对外实时聊天只走统一 `/api/v1/ws`
   - 不允许再长第二套聊天协议或第二套产品主脑

2. **结构化真相优先，Markdown 只是 projection**
   - learner state 方案已经明确：Markdown 文件不再作为唯一主真相
   - context orchestration 也强调 stable prefix 与动态证据分离

3. **less is more**
   - 不新增重复概念
   - 不靠多层补丁维持一致性
   - 优先收敛责任边界和单一真相

因此，前端渲染体系的正确方向也必须一致：

- 不再让 Markdown 继续承担全部语义
- 不再让题卡、表格、公式、图表靠自由文本推断
- 不再在多个阶段重复推导一遍“这个消息到底该怎么显示”

### 3.2 当前渲染器现状

当前小程序聊天页已经具备一定基础：

1. Markdown 解析支持：
   - 标题
   - 段落
   - 引用
   - 列表
   - 代码块
   - 表格
   - callout
   - 水平线

2. 选择题已有独立题卡 UI
   - 支持点击选项
   - 支持提交答案
   - 支持从事件 payload 或文本回退检测生成题卡

3. 最近一轮修复已经做了关键收敛：
   - AI 消息渲染状态统一从 `ai-message-state` 推导
   - 选择题显示逻辑不再单纯依赖 `item.content`
   - `wx_miniprogram` 与 `yousenwebview` 已补齐 parity tests

这说明基础方向是对的，但还没有走到“体系化完成”。

### 3.3 当前真正的问题

现在的问题已经不是“有没有 Markdown 渲染器”，而是：

**我们还没有一套面向教学内容的前端表达模型。**

于是前端只能在三个层次反复猜测：

1. 这段文本是不是普通正文
2. 这段文本是不是选择题
3. 这段文本里某一部分是不是表格、公式或未来的图表

这种设计在普通聊天产品里还能勉强工作，但在教育产品里不够。

教育内容天然比普通聊天更强结构化，因为它经常包含：

1. 题干
2. 选项
3. 标准答案
4. 解析
5. 表格
6. 公式
7. 图表
8. 例题
9. 注意事项
10. 分步骤解题过程

如果这些内容继续主要以自由文本落地，再让前端自己拆，长期一定不稳。

### 3.4 v1 PRD 仍然不够的地方

上一版 PRD 方向是对的，但如果按“对结果负责”的交付标准来看，仍有四个不足：

1. **场景覆盖不够恶劣**
   - 还主要覆盖了理想路径
   - 对混合内容、断流恢复、历史消息兼容、低端机性能、超长答案等边界场景覆盖不足

2. **失败模式不够显式**
   - 说明了要走 block model
   - 但没有足够明确地规定 block 缺失、block 不合法、图表失败、公式资源失败时系统必须如何降级

3. **交付路径还不够工程化**
   - 已有阶段划分
   - 但缺少 phase gate、灰度策略、回滚条件、可量化 exit criteria

4. **不确定性尚未隔离**
   - 公式与图表都存在技术不确定性
   - 需要明确哪些结论是确定的，哪些需要实验验证，哪些要准备替代方案

## 4. 问题定义

### 4.1 当前核心问题

当前微信渲染器的核心问题不是“某个题选不了”，而是：

**教学内容的语义来源和最终渲染来源不是同一个真相。**

服务端表达的是一个教学回答，前端真正消费的却是：

1. 一段流式文本
2. 若干启发式 Markdown blocks
3. 选择题检测结果
4. 可能存在的 interactive payload

这些来源之间目前仍是“拼接关系”，不是“单一结构化真相向多个视图投影”。

### 4.2 由此引发的典型问题

#### A. 选择题类问题

1. 题目生成了，但流式正文判断把题卡遮住
2. 题卡显示了，但交互状态与正文状态不是同一来源
3. 文本里混有回执、提示、题面，前端需要额外 strip
4. 同一消息既有正文又有题卡时，优先级容易冲突

#### B. 表格类问题

1. Markdown 表格在移动端可读性有限
2. 现在只有横向滚动，没有教学语义增强
3. 没有针对窄屏的压缩视图、重点高亮、对齐语义
4. 复杂表格未来很容易撑爆气泡或阅读负担过重

#### C. 公式类问题

1. 当前没有可靠公式渲染链路
2. 公式一旦以 `$...$` 或 `\\(...\\)` 出现，前端只能当普通字符
3. 在教培问答里，这会直接损害解释质量和专业感

#### D. 图表类问题

1. 当前没有图表 block，也没有图表投影层
2. 如果以后直接让模型输出“伪 Markdown 图表”或文本描述，前端无法稳定展示

#### E. 体系类问题

1. `wx_miniprogram` 与 `yousenwebview` 仍然是镜像双实现
2. 当前虽然已经用 parity test 控制漂移，但根因仍是双份代码
3. 如果未来内容类型继续变多，维护成本会指数上升

### 4.3 根因

根因不是某个 `wx:if` 写错了，也不是某个渲染条件缺了一个分支，而是：

1. **内容协议缺位**
   - 对教学内容而言，客户端拿到的仍主要是一段文本，而不是结构化 block 序列

2. **单一渲染真相缺位**
   - message 的最终显示状态曾经分散在 hydrate、stream、done、interactive 等多个阶段重复推导

3. **Projection 边界不清**
   - Markdown 既承担普通文本投影，又承担结构化内容识别，又承担部分交互内容兜底

4. **双端实现镜像复制**
   - 相同语义在两个小程序工程里维护，放大了漂移风险

## 5. 产品目标

### 5.1 最终目标

构建一套世界级、可持续扩展的微信教学内容渲染体系，使 TutorBot 在移动端能够稳定呈现：

1. 普通教学文字对话
2. 选择题
3. 表格
4. 公式
5. 未来图表
6. 后续可能加入的图像、案例卡片、步骤卡片、总结卡片

### 5.2 体验目标

1. 用户看到的内容必须与教学语义一致，而不是与原始文本偶然长得像
2. 同一条回答在流式中和完成后应保持语义连续，不闪烁、不覆盖、不跳变
3. 选择题必须始终可见、可点、可提交、可复盘
4. 表格在手机上必须可读，而不是“理论可显示”
5. 公式必须可识别、可显示、可复制、可回退
6. 图表未来接入时，不得推翻现有渲染架构

### 5.3 架构目标

1. Markdown 降级为普通文本 projection 与兼容层，不再承担唯一主真相
2. 教学结构内容以 block model 为内部一等表达
3. AI 消息只允许存在一个最终 render model
4. `wx_miniprogram` 与 `yousenwebview` 共享同一渲染语义和测试基线
5. 前端不再依赖越来越多的自由文本启发式来“猜语义”

## 6. 非目标

本 PRD 明确不做以下事情：

1. 不新增第二套聊天入口
   - 仍然只走统一 `/api/v1/ws`

2. 不把前端渲染协议直接升级成新的公开稳定 contract
   - 先作为内部 block model 与 projection adapter 演进
   - 只有对外边界稳定后才考虑 contract 化

3. 不引入一个超重的客户端富文本引擎
   - 不在微信小程序里直接堆大体积 MathJax/全功能 HTML 渲染

4. 不让 Markdown 继续承担所有复杂内容
   - 不做“再往 Markdown parser 里塞几十条新规则”的路线

5. 不一次性支持所有复杂图表类型
   - 第一阶段只定义方向和最小可落地路径

## 7. 第一性原理与设计原则

### 7.1 First Principles

1. 教学内容不是普通聊天文本
2. 强结构内容必须显式表达，而不是靠前端猜
3. 最终渲染状态必须来自单一真相
4. 一种语义只能有一种主表达
5. 兼容层只能是兼容层，不能继续冒充主架构

### 7.2 Less Is More

1. 不再补更多 `wx:if` 去抢显示优先级
2. 不再加更多文本正则去猜题、猜公式、猜图表
3. 不再让两个小程序各自悄悄长出不同渲染语义
4. 优先建立 block model，而不是扩展 Markdown parser 到失控

### 7.3 Projection Discipline

1. 结构化内容是真相
2. Markdown 是 projection
3. 纯文本 fallback 是兜底
4. 任何 projection 都不能反过来篡改主真相

### 7.4 硬约束

以下约束必须视为实现期不可破坏的硬规则：

1. 一个 message 在任意时刻只能有一个可解释的最终 render model
2. 模板层不得自行推断“这是不是选择题/表格/公式”
3. 已有显式 block 时，前端不得再对同一段正文做平行启发式识别
4. fallback 只能在 canonical block 缺失或无效时启用
5. fallback 一旦启用，必须可观测、可统计、可追踪
6. `wx_miniprogram` 与 `yousenwebview` 的内容语义必须等价
7. 任意新 block 类型都必须先定义降级路径，再允许上线

## 8. 目标用户与核心场景

### 8.1 目标用户

1. 在微信小程序中进行建筑教培问答的学员
2. 做题、批改、追问、记忆、复盘一体化使用 TutorBot 的学员
3. 使用手机窄屏阅读讲解、表格、公式的用户

### 8.2 核心场景

#### 场景 A：普通教学解释

用户问一个知识点，TutorBot 返回：

1. 一段结论
2. 3-5 个要点
3. 一个注意事项

要求：

1. 可流式
2. 结构清晰
3. 不因 Markdown 细节导致排版混乱

#### 场景 B：单题选择题作答

TutorBot 返回：

1. 题干
2. 选项
3. 提交按钮

要求：

1. 题卡一定显示
2. 一定可交互
3. 题面文本和交互状态必须一致

#### 场景 C：题组练习

TutorBot 返回：

1. 多道题
2. 每题选项
3. 整组提交
4. 每题讲评或统一讲评

要求：

1. 支持题组级状态
2. 支持已选答案保留
3. 支持提交后复盘

#### 场景 D：知识对比表

TutorBot 返回一个法规条款对比表或施工工艺对比表。

要求：

1. 窄屏可读
2. 支持横滑
3. 重点列、重点行可强化
4. 不能出现整块不可阅读的情况

#### 场景 E：公式讲解

TutorBot 返回：

1. 行内公式
2. 独立公式块
3. 变量解释
4. 示例代入

要求：

1. 公式能正确展示
2. 读者能复制原式
3. 公式显示失败时有稳定回退

#### 场景 F：未来图表

TutorBot 返回：

1. 柱状图
2. 折线图
3. 饼图
4. 时间轴或流程图

要求：

1. 不依赖从自然语言中猜图
2. 使用受控图表 block
3. 图表与正文联动但互不污染

### 8.3 高风险边界场景矩阵

本 PRD 必须覆盖以下高风险真实场景，否则设计仍不算稳健：

#### 场景 G：正文 + 题卡混合输出

例子：

1. 先给一段知识铺垫
2. 再给一道选择题
3. 最后给提交提示

要求：

1. 正文与题卡可同时存在
2. 题卡不能被正文显示逻辑遮住
3. 题卡提交后讲评不能覆盖原题面

#### 场景 H：题组 + 逐题讲评混合

例子：

1. 一次下发 3-5 道题
2. 用户整组提交
3. 返回逐题对错与统一总结

要求：

1. 题组状态与讲评状态分层
2. 已答结果可复盘
3. 不能因为讲评到达而把原始题组 UI 冲掉

#### 场景 I：超长教学回答

例子：

1. 先是结论
2. 再是分步骤解析
3. 中间夹一个表格
4. 最后带公式和总结

要求：

1. 长回答不炸布局
2. 滚动性能稳定
3. 结构切换不导致明显跳动

#### 场景 J：流式中断 / resume / replay

例子：

1. 流式回答到一半断网
2. 客户端恢复订阅或重进页面
3. 历史消息重放

要求：

1. 恢复后渲染结果与完成态一致
2. 不出现重复 block、重复题卡、重复正文
3. 旧流式 projection 与最终 block 不冲突

#### 场景 K：历史兼容消息

例子：

1. 历史库里大量只有纯文本或 Markdown
2. 新版本前端要同时展示新旧消息

要求：

1. 老消息继续可读
2. 新消息优先消费 block
3. 不允许为了兼容老消息牺牲新体系主路径

#### 场景 L：公式资源失败

例子：

1. 公式 SVG 拉取失败
2. 公式 AST 渲染器异常

要求：

1. 不空白
2. 可回退到原始 LaTeX 或 display text
3. 用户知道这是公式而不是乱码

#### 场景 M：图表渲染失败

例子：

1. 图表库不兼容
2. 图表数据过大
3. 低端机掉帧

要求：

1. 自动退化为 `fallback_table` 或摘要卡片
2. 不影响整条消息其他 block 的显示
3. 失败原因可观测

#### 场景 N：低端机与弱网

例子：

1. Android 低端机
2. 长消息
3. 高频滚动

要求：

1. 不因渲染器升级明显拖慢首屏
2. 不能让公式或图表成为主线程卡顿来源
3. 必须有降配路径

## 9. 方案总览

### 9.1 核心决策

本 PRD 采用以下总方案：

**建立内部结构化教学内容 block model，并让微信渲染器消费 block model；Markdown 保留为普通文本 projection 与兼容层。**

### 9.2 三层模型

未来一条 AI 教学消息，在前端只允许存在三层，且必须是单向依赖：

1. **Canonical Content / Presentation**
   - 由服务端或消息装配层给出的唯一教学内容主表达
   - 形式是 `presentation = { blocks, fallback_text, meta }`

2. **Render Model**
   - 前端对 `presentation` 做一次性、确定性的渲染态归一
   - 输出给页面模板直接消费

3. **Projection / Fallback**
   - 普通 Markdown 文本
   - 纯文本
   - 历史兼容兜底

不允许再存在四五套并列的显示来源互相争抢。
也不允许从 `interactive`、legacy `summary` 或文本检测结果反向生成 canonical content。

### 9.3 Block 类型规划

第一阶段建议收敛为以下 block 类型：

1. `paragraph`
2. `heading`
3. `list`
4. `callout`
5. `quote`
6. `code`
7. `table`
8. `mcq`
9. `formula_inline`
10. `formula_block`
11. `chart`
12. `image`
13. `steps`
14. `recap`

说明：

1. 这不是对外公开 contract，只是内部 block taxonomy
2. 不要求第一天全部上线
3. 但 taxonomy 要先定，否则后面每加一种内容都要重做一遍渲染边界
4. 这里的 `recap` 指教学总结 block，**不是** 历史 `result.metadata.summary` 字段

### 9.4 方案比较与取舍

本阶段实际存在三条候选路线：

#### 方案 A：继续增强 Markdown 渲染器

做法：

1. 继续扩充 parser
2. 继续添加启发式识别
3. 对选择题、公式、图表分别加补丁

优点：

1. 短期改动小
2. 对历史消息天然兼容

缺点：

1. 根因不变
2. 强结构内容仍靠猜
3. 新内容类型越多越脆弱

结论：

1. 只能作为过渡，不适合作为主路线

#### 方案 B：内部 block model + Markdown fallback

做法：

1. 新消息优先下发结构化 blocks
2. 老消息继续用 Markdown / 文本 fallback
3. 前端统一归一为 render model

优点：

1. 兼顾演进与兼容
2. 风险可控
3. 最符合当前项目方向

缺点：

1. 存在一段双路径并存期
2. 需要额外治理 fallback 漂移

结论：

1. 这是当前条件下最优主路线

#### 方案 C：直接上对外公开稳定 contract

做法：

1. 立即定义正式 schema
2. 前后端严格按新协议演进

优点：

1. 长期边界清晰

缺点：

1. 当前内容类型仍在快速探索
2. 过早冻结容易锁死演进空间

结论：

1. 现在做太早
2. 应等 block taxonomy、降级规则和双端实现稳定后再评估

## 10. 详细设计

### 10.1 Presentation Schema（唯一权威 Envelope）

每条 AI 消息最终应当可以被归一为：

```json
{
  "blocks": [
    { "type": "paragraph", "text": "..." },
    { "type": "mcq", "questions": [...] },
    { "type": "table", "headers": [...], "rows": [...] },
    { "type": "formula_block", "latex": "..." }
  ],
  "fallback_text": "...",
  "meta": {
    "streaming_mode": "text_first"
  }
}
```

关键原则：

1. `presentation` 是客户端唯一 canonical envelope
2. `blocks` 是唯一主真相
3. `fallback_text` 仅用于兼容和失败回退
4. `meta` 只描述渲染辅助信息，不承载正文语义
5. `summary` 与 `interactive` 不进入 canonical schema

#### Canonical Model 不变量

1. block 顺序必须稳定，等于用户最终阅读顺序
2. 一个 block 只表达一种主语义
3. 不允许同一段内容同时在 `blocks` 和 `fallback_text` 中承担不同主语义
4. `fallback_text` 可以是 `blocks` 的粗粒度投影，但不能比 `blocks` 更权威
5. block 数据必须可序列化、可持久化、可 replay

#### 字段分层

1. `canonical`
   - `presentation.blocks`
   - `presentation.fallback_text`
   - `presentation.meta`
2. `derived`
   - `render_model.visibleBlocks`
   - `render_model.plainTextFallback`
   - `render_model.hasStructuredContent`
   - `render_model.mcqInteractiveReady`
3. `legacy`
   - 历史 `result.metadata.summary`
   - 历史 `interactive payload`
   - 文本题面检测结果
4. `forbidden`
   - 在 canonical schema 内新增 `interactive` 同名字段
   - 让前端从 legacy `summary` 或 `interactive` 反推 canonical content
   - 让模板层直接参与内容语义判断

#### Schema 清洗规则

1. `written` 题不生成 `mcq` block
2. `choice` 题若缺少合法 `options`、缺少可校验答案键、或结构校验失败，不生成 `mcq` block
3. legacy `summary` 若无法合法生成 `presentation`，必须降格为普通文本消息，并删除 `summary`
4. 不允许把“不足以生成 block 的残缺 summary”继续留在消息里作为第二事实源
5. `question_followup_context` 若仍然可用，可继续保留；它不等于渲染 schema

### 10.2 Render Model

前端页面不应直接消费原始 message，而应只消费一次性推导后的 render model。

建议统一为：

1. `visibleBlocks`
2. `plainTextFallback`
3. `mcqInteractiveReady`
4. `streamState`
5. `actionsState`
6. `citationsState`

要求：

1. 任意阶段都只通过一个 `deriveRenderModel()` 入口生成
2. hydrate、stream、done、interactive 都不能各自另算一套显示字段
3. 模板层只读 render model，不参与语义判断

#### Render Model 建议字段

建议在 `visibleBlocks` 之外，显式保留以下只读派生字段：

1. `hasStructuredContent`
2. `streamPhase`
3. `mcqInteractiveReady`

这些字段全部是**只读派生字段**，不得反向参与内容判定。

### 10.3 Markdown 的新定位

Markdown 仍然保留，但角色要收窄：

1. 普通文字回答的快速 projection
2. 历史消息兼容
3. 服务端未提供 block 时的临时回退

Markdown 不再承担：

1. 选择题主识别
2. 公式主识别
3. 图表主表达
4. 复杂教学组件的唯一来源

### 10.4 选择题方案

选择题必须从“文本猜测型渲染”升级为“显式题卡 block 渲染”。

#### 目标形态

1. `mcq` block 是选择题唯一主表达
2. 题干、选项、题型、题目 ID、提交 hint、回执都挂在 block 内
3. 交互状态只更新 block 的 render state，不改写正文语义

#### 兼容策略

1. 已有 interactive payload 只允许在迁移适配器中映射到 `mcq` block
2. 旧文本题面检测只允许存在于 legacy adapter，不能再进入新消息主链路
3. 一旦服务端已给 `mcq` block，前端停止对正文做选择题猜测
4. 新消息禁止再写入新的 `interactive payload`

#### 非结构化归档规则

1. `written` 题默认归档为普通文本教学消息，不进入 `mcq` 主链路
2. 坏 `choice` 数据默认归档为普通文本消息，并进入脏数据治理清单
3. 普通文本归档的判断依据只看 canonical schema 是否可构建，不再看 legacy `summary` 是否“看起来像题”
4. 归档后的消息允许保留正文与 follow-up 上下文，但不得继续保留 legacy `summary`

#### 为什么这样做

因为选择题是最高频、最强结构、最容易因条件竞争出错的内容类型，必须最先退出“文本猜题”阶段。

#### 选择题补充约束

1. `mcq` block 必须支持单题和题组两种容器形态
2. 题目提交状态、讲评状态、复盘状态必须分层保存
3. 题卡 UI 必须支持只读态重放
4. 同一条消息中允许出现“讲解 block + mcq block + 讲评 block”的组合，但语义顺序必须稳定

### 10.5 表格方案

表格不能只停留在“Markdown 解析成功就算完成”。

#### 目标形态

1. 表格有显式 `table` block
2. 包含：
   - 列头
   - 行数据
   - 可选列对齐
   - 可选重点单元格
   - 可选 compact/mobile view 提示

#### 移动端要求

1. 默认横滑
2. 超宽表支持 compact-card 投影
3. 重点列/重点行可高亮
4. 支持复制单元格文本
5. 不允许出现内容被裁切但用户感知不到

#### 演进原则

1. 继续支持 Markdown 表格 fallback
2. 但高价值教学表格优先走结构化 `table` block

#### 表格补充约束

1. 超过 4 列的表格必须定义移动端阅读策略
2. 表格内若包含公式，优先以 display text 呈现，不直接把复杂公式塞进单元格主视图
3. 表格若承载关键信息，必须允许复制或二次查看
4. 当表格超出可读阈值时，允许降级为“分行卡片视图 + 原表入口”

### 10.6 公式方案

公式不能依赖微信小程序客户端现场解析重型数学引擎。

#### 建议路线

1. 服务端生成轻量公式表达
2. 前端消费以下之一：
   - 公式 AST
   - 预渲染 SVG
   - `latex + display_text + svg_url` 的轻量组合

#### 推荐顺序

1. 第一阶段：
   - 支持识别 `formula_inline` / `formula_block`
   - 最小方案可先用服务端预渲染 SVG + 原始 LaTeX 文本 fallback

2. 第二阶段：
   - 优化公式复制
   - 优化变量解释联动
   - 优化公式块与正文混排

#### 原则

1. 正确显示优先于客户端花哨能力
2. 可回退优先于完美渲染
3. 不在小程序端塞入超重依赖

#### 当前不确定性

以下内容当前仍需实验验证，不能伪装成已确定事实：

1. SVG 公式在不同微信机型上的清晰度与缩放表现
2. 行内公式与中文混排时的视觉一致性
3. 大量公式连续出现时的性能成本

对应策略：

1. 先用最轻的服务端预渲染路线做小范围验证
2. 如果 SVG 路线在真机表现不稳定，则退回 `display_text + copy latex` 双轨方案
3. 不等待“完美公式渲染”才推进整体 block 架构

### 10.7 图表方案

图表未来必须走结构化 block，不允许走自然语言猜图。

#### 目标形态

图表 block 至少包含：

1. `chart_type`
2. `title`
3. `series`
4. `axes`
5. `legend`
6. `caption`
7. `fallback_table`

#### 为什么需要 `fallback_table`

因为微信环境、终端性能、图表库兼容性都可能影响显示稳定性。

教学场景下，图表视觉失败时，仍必须退化为可读数据表，而不是空白。

#### 图表补充约束

1. 图表第一阶段只支持少数高价值类型
   - 折线
   - 柱状
   - 饼图
   - 时间轴

2. 所有图表必须携带文本摘要
3. 所有图表必须定义失败降级视图
4. 不允许把 Mermaid、伪代码图或 ASCII 图直接当正式图表主路径

### 10.8 流式策略

教学内容渲染必须兼容流式输出，但不能再让流式阶段破坏最终语义。

建议采用：

1. **text-first, block-finalize**
   - 流式阶段先显示普通文本 projection
   - 完成阶段如果拿到结构化 block，再无闪烁地切换到 block 渲染

2. **显式优先级**
   - 已有结构化 block 时，block 永远高于文本猜测
   - 已有 `mcq` block 时，不再跑文本题卡检测

3. **稳定过渡**
   - 切换时保持 message 外层容器稳定
   - 避免内容高度突变导致滚动位置跳动

#### 流式补充规则

1. block finalize 必须幂等，重复到达不应重复渲染
2. resume / replay 后的最终 render model 必须与首次完成态一致
3. 如果流式阶段已经显示 fallback_text，完成阶段切到 structured blocks 时必须保留用户阅读位置的稳定性

### 10.9 兼容、迁移与双写期策略

本方案天然会经历一段“新消息有 blocks，旧消息没有”的过渡期，因此必须显式设计迁移策略。

#### 迁移原则

1. 新架构优先服务新消息
2. 老消息通过 schema 迁移保持可读，而不是长期让路由层继续猜
3. 不把历史兼容逻辑反向污染新消息主路径
4. `compressed_summary` 继续服务会话压缩与历史召回，它不是题卡渲染事实源

#### 双写期建议

1. 新消息只写：
   - `result.metadata.presentation`
   - `question_followup_context`
   - 旧 `summary` / `interactive` 不再新增

2. 历史消息过渡策略：
   - 使用离线脚本 `scripts/backfill_message_presentations.py` 回填 `messages.events_json`
   - `SQLiteSessionStore` 只提供回填能力，不在正常读取路径做 legacy `summary` 自动投影
   - 回填完成后删除路由层与前端层的 legacy `summary` 读取
   - 对无法合法生成 `presentation` 的历史消息，直接删除 `summary`，归档为普通文本消息

3. 前端消费优先级固定为：
   - `presentation.blocks`
   - `presentation.fallback_text`
   - 普通文本内容

4. 退场顺序固定为：
   - 先停新写入
   - 再做历史回填
   - 再停旧读取
   - 最后删 adapter

5. 删除 legacy adapter 的门槛：
   - 新消息 `presentation` 覆盖率达到 100%
   - 历史消息回填任务已完成且可验证
   - 双端 parity tests 持续通过
   - 移动端消息恢复不再依赖 `summary` 回退

### 10.10 可观测性与调试设计

如果没有可观测性，这套体系后面仍然会回到“用户截图驱动修 bug”。

建议最少记录以下信号：

1. `message_has_blocks`
2. `message_block_types`
3. `renderer_used_fallback`
4. `renderer_fallback_reason`
5. `renderer_degrade_level`
6. `renderer_formula_failed`
7. `renderer_chart_failed`
8. `renderer_mcq_interactive_ready`
9. `renderer_parity_mismatch`

这些信号不一定都要立刻进对外 contract，但至少要进入内部日志、trace 或前端埋点。

### 10.11 性能与可用性要求

顶尖体验不是只看“能不能显示”，还要看“显示得稳不稳”。

因此本方案默认要求：

1. 普通文本回答首屏体验不得因新架构明显变慢
2. 长消息渲染不得显著增加滚动卡顿
3. 复杂 block 应按需渲染，不得无脑一次性展开全部重组件
4. 图表和公式应支持延迟加载或降配
5. block 渲染失败不得拖垮整条消息
6. 关键内容需支持复制、重试或回退查看

### 10.12 可访问性与教学可读性要求

本项目主场景虽然是教培，但不能忽略基础可读性。

至少需要满足：

1. 选择题点击区域足够大
2. 表格横滑有明确视觉提示
3. 公式失败时仍保留可复制文本
4. 图表有文字摘要，避免纯视觉表达
5. callout、总结、步骤等教学组件有稳定视觉层级

### 10.13 双端一致性方案

当前 `wx_miniprogram` 与 `yousenwebview/packageDeeptutor` 是镜像双实现。

短期内不一定要强行做成一个包，但必须进一步收口：

1. 共享同一份 block taxonomy
2. 共享同一份 render model 推导逻辑
3. 共享同一套 golden tests / parity tests
4. 页面模板行为必须等价

长期目标：

1. 能共享的 utils 尽量共享
2. 双实现只保留宿主差异，不保留内容语义差异

## 11. 分阶段实施计划

### 11.1 P0：稳定当前选择题与消息单一真相

目标：

1. 消除“题出现但不可选”“题出现但不显示”“正文覆盖题卡”类问题
2. 固化 AI 消息单一 render state

范围：

1. `ai-message-state` 继续作为唯一派生入口
2. 模板层继续去掉对原始 `content` 的过度直接判断
3. parity tests 继续保留

完成标准：

1. 选择题在 wx 和宿主分包行为一致
2. 文本、题卡、流式状态不存在互相覆盖
3. 断流恢复后不重复题卡、不丢题卡

当前代码状态（2026-04-16）：

1. `ai-message-state` 仍是 AI 消息唯一 render-state 派生入口
2. 模板层不再从原始正文直接反推可交互题卡
3. `mobile.py` 已收口为只消费 `presentation`
4. 代码侧 P0 已闭环，剩余 gate 为真机抽样验证

### 11.2 P1：引入内部教学 block model

目标：

1. 建立 `paragraph / table / mcq / formula_*` 等 block taxonomy
2. 为前端定义统一 `deriveRenderModel()`

范围：

1. 先不做公开 contract
2. 先在内部消息装配层和前端 adapter 层建立 block model
3. 保留 Markdown fallback

完成标准：

1. 新消息可优先消费结构化 blocks
2. 老消息继续通过 Markdown / 文本 fallback 可读
3. 已定义 block 缺失与无效时的降级策略

当前代码状态（2026-04-16）：

1. 内部 block taxonomy 已落地到 producer、前端 normalizer 与 render model
2. `deriveRenderModel()` 已收敛为前端主入口
3. legacy `summary` 仅保留入口 alias 与离线回填能力，不再参与正常读取链路
4. 代码侧 P1 已闭环

### 11.3 P2：选择题、表格、公式正式结构化

目标：

1. 选择题退出文本猜测主路径
2. 高价值教学表格升级为结构化表格
3. 公式拥有正式渲染链路

范围：

1. `mcq` block 正式化
2. `table` block 增加移动端阅读能力
3. `formula_inline` / `formula_block` 接入

完成标准：

1. 选择题不再依赖正文推断
2. 公式可稳定显示与回退
3. 表格在真机窄屏仍可读
4. 高风险场景已有真机验证样例

当前代码状态（2026-04-16）：

1. `mcq / table / formula_*` 的 canonical producer 与双端消费链路已打通
2. `wx_miniprogram` 与 `yousenwebview` 的 render-state parity 已纳入 node 回归
3. 尚未完成真机 gate，因此 P2 仍不应视为最终关闭

### 11.4 P3：图表与教学语义组件

目标：

1. 接入图表 block
2. 增加教学专用内容组件

范围：

1. `chart`
2. `steps`
3. `recap`
4. 其他教学语义卡片

完成标准：

1. 图表展示失败时能回退为表格或说明卡
2. 教学回答结构显著优于普通聊天型排版

当前代码状态（2026-04-16）：

1. `chart / steps / recap` 已进入 canonical producer 与双端 render-state 主链路
2. `summary` 只作为 legacy 输入别名被归一到 `recap`，不再是 canonical block type
3. `chart` 首期只交付结构化数据卡能力：
   - 标题
   - 摘要
   - series 概览
   - `fallback_table`
4. `steps` 与 `recap` 已由 producer 直接输出 canonical 主形状，前端只保留 legacy alias 兼容，不再承担主语义改写
5. `steps` 与 `recap` 已有双端模板、样例集与 parity 回归
6. 代码侧 P3 已闭环，剩余 gate 为微信开发者工具与真机窄屏验证

### 11.5 Phase Gate 与上线门槛

每个阶段不是“代码合了就算完成”，而必须通过 gate。

#### P0 Gate

1. 选择题核心回归用例全通过
2. wx / 宿主 parity tests 通过
3. 至少完成一轮真机抽样验证

当前状态：

1. 前两项已完成
2. 真机抽样验证待完成

#### P1 Gate

1. block taxonomy 文档定稿
2. `deriveRenderModel()` 成为唯一主入口
3. fallback reason 已可观测

当前状态：

1. 前两项已完成
2. `fallback reason` 的系统化观测仍可继续增强，但不阻塞当前代码闭环

#### P2 Gate

1. 选择题、表格、公式样例集通过
2. 公式失败降级链路验证通过
3. 至少覆盖 iPhone + Android 各一批真机

当前状态：

1. 前两项已完成
2. 真机覆盖待完成，因此 P2 尚未最终关 gate

#### P3 Gate

1. 图表失败回退率可接受
2. 教学语义组件没有破坏普通消息体验
3. 有明确灰度与回滚开关

当前状态：

1. 代码与离线样例已经覆盖 `chart / steps / recap`
2. 真机上的窄屏可读性与灰度策略验证仍待完成，因此 P3 尚未最终关 gate

### 11.6 灰度、发布与回滚策略

这类渲染架构升级不能一次性全量切换，必须按能力分层灰度。

#### 灰度原则

1. 先灰度渲染能力，再灰度内容生产能力
2. 先灰度 `mcq`，再灰度 `table` / `formula`，最后灰度 `chart`
3. 任一高风险 block 都必须可独立开关

#### 发布顺序建议

1. 第一步：
   - 仅前端支持新 render model
   - 服务端仍主要输出旧内容

2. 第二步：
   - 小流量开启 `mcq` block

3. 第三步：
   - 扩展到结构化 `table` 与 `formula`

4. 第四步：
   - 视实验结果决定是否开启正式图表组件

#### 回滚要求

1. 任意新 block 渲染失败时，必须可单独关闭该 block 主路径
2. 关闭后系统仍可退回 `fallback_text` 或旧 Markdown 路径
3. 回滚不得要求历史消息重写

## 12. 验收标准

### 12.1 功能验收

1. 普通文字回答：
   - 流式显示稳定
   - 完成后排版清晰

2. 选择题：
   - 题卡稳定可见
   - 选项可点
   - 提交链路稳定
   - 支持复盘只读态

3. 表格：
   - 支持横滑
   - 不截断关键信息
   - 真机窄屏可读

4. 公式：
   - 支持行内与独立公式块
   - 显示失败时可回退

5. 图表：
   - 至少具备结构化输入与回退能力

### 12.2 工程验收

1. AI 消息渲染只有一个 render model 派生入口
2. `wx_miniprogram` 与 `yousenwebview` 通过 parity tests 保持一致
3. 结构化 blocks 与 Markdown fallback 的优先级清晰
4. 模板层不再承担复杂语义推断

### 12.3 体验验收

1. 新用户第一次使用不会遇到“内容有但看不见”
2. 做题场景不会遇到“题卡可见但无法操作”
3. 长消息不会因渲染切换造成明显闪跳
4. 历史消息升级后仍保持基本可读

### 12.4 验证矩阵

验收不能只靠单元测试，至少要分四层验证：

1. **纯函数层**
   - block adapter
   - render model derivation
   - fallback decision

2. **模板层**
   - 不同 block 组合的渲染快照
   - 关键 `wx:if` 优先级验证

3. **场景层**
   - 单题
   - 题组
   - 表格
   - 公式
   - 图表失败回退
   - 断流恢复

4. **真机层**
   - iPhone
   - Android 中端机
   - Android 低端机
   - 弱网场景

当前已落地的样例集：

1. 结构化渲染样例基线位于 [wechat_structured_renderer_cases.json](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/tests/fixtures/wechat_structured_renderer_cases.json)
2. `wx_miniprogram/tests/test_ai_message_state.js` 与 `wx_miniprogram/tests/test_renderer_parity.js` 已消费该样例集做回归
3. 真机抽样应直接复用这套 case，而不是临时口述场景
4. P2 真机 gate 执行清单位于 [2026-04-16-wechat-structured-renderer-p2-gate-checklist.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-16-wechat-structured-renderer-p2-gate-checklist.md)
5. P3 真机 gate 执行清单位于 [2026-04-16-wechat-structured-renderer-p3-gate-checklist.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-16-wechat-structured-renderer-p3-gate-checklist.md)
6. 开发者工具执行入口与 console 注入方式位于 [2026-04-16-wechat-structured-renderer-devtools-runbook.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-16-wechat-structured-renderer-devtools-runbook.md)

## 13. 关键指标

建议跟踪以下指标：

1. 题卡渲染成功率
2. 题卡点击成功率
3. 题卡提交成功率
4. 表格消息平均停留时长
5. 公式消息渲染失败率
6. 图表 block 回退率
7. 渲染异常日志率
8. 双端 parity 回归失败率
9. block 覆盖率
10. fallback 使用率
11. fallback 原因分布
12. 公式降级率
13. 断流恢复后一致性错误率

### 13.1 目标值建议

当前可以先给出方向性目标，后续再按真实数据微调：

1. 新消息 block 覆盖率持续提升
2. 选择题主路径 fallback 使用率持续下降
3. 图表失败时空白率目标为 0
4. 公式失败时空白率目标为 0
5. 断流恢复后一致性错误率应压到极低水平

## 14. 风险与应对

### 风险 1：过早把 block model 做成对外 contract

问题：

1. 现在内容类型还在演进
2. 过早 contract 化会把内部探索锁死

应对：

1. 先作为内部 schema 使用
2. 等内容类型稳定后再评估 contract 升级

### 风险 2：继续让 Markdown 承担主路径

问题：

1. 短期改动少
2. 但长期一定回到补丁螺旋

应对：

1. Markdown 保留
2. 但只保留为 projection 与 fallback

### 风险 3：双端继续漂移

问题：

1. 结构相似但代码两份
2. 未来每加一种内容都可能双倍出错

应对：

1. 强制 parity tests
2. 尽快共享 render model 与 block adapter 逻辑

### 风险 4：公式方案过重

问题：

1. 微信小程序环境对重渲染库不友好

应对：

1. 优先服务端预渲染
2. 前端只做轻量展示和回退

### 风险 5：block taxonomy 过度设计

问题：

1. 一开始就设计太多 block 类型
2. 容易引入实现负担，偏离 less is more

应对：

1. taxonomy 先定大框架
2. 真正优先上线的只保留最小闭环：
   - `paragraph`
   - `callout`
   - `mcq`
   - `table`
   - `formula_inline`
   - `formula_block`

### 风险 6：双写期过长

问题：

1. 新旧路径长期并存会抬高维护成本

应对：

1. 从一开始就记录 block 覆盖率和 fallback 使用率
2. 给双写期设退出门槛，不无限拖延

## 15. 当前不确定性、验证方案与替代路线

### 15.1 已确定的结论

以下结论当前已足够确定，可以作为主设计前提：

1. 继续以 Markdown 为主真相不可持续
2. 选择题必须优先退出文本猜测主路径
3. 前端必须有单一 render model
4. 双端必须通过 parity 和共享逻辑收口

### 15.2 仍不确定的点

以下事项当前仍存在实现不确定性：

1. 公式的最佳轻量渲染路线
2. 图表在微信端的最佳承载方式
3. 超宽表在极窄屏上的最终最佳交互

### 15.3 验证方案

针对上述不确定性，建议按最小实验闭环推进：

1. **公式实验**
   - 方案 1：服务端 SVG
   - 方案 2：display text + 可复制 LaTeX
   - 验证维度：清晰度、性能、失败率、真机一致性

2. **图表实验**
   - 方案 1：轻图表组件 + `fallback_table`
   - 方案 2：首期只上“结构化数据卡 + 文本摘要”，暂不上图形
   - 验证维度：性能、可读性、开发复杂度

3. **表格实验**
   - 方案 1：横滑表
   - 方案 2：compact-card 视图
   - 验证维度：阅读效率、用户停留、可复制性

### 15.4 替代路线

如果某些高复杂度能力在当前窗口下不值得立即推进，应采用以下替代方案：

1. 公式如果真机表现不稳定：
   - 先退回“高可读 display text + copy LaTeX”

2. 图表如果性能不稳：
   - 首期只交付 `chart` block 数据结构与 `fallback_table`
   - 暂缓正式图形组件

3. 表格如果复杂度过高：
   - 先聚焦高频教学表格
   - 不追求通用 Excel 级能力

## 16. 结论

对 DeepTutor 来说，微信渲染器下一阶段最值得做的，不是继续增强 Markdown，而是：

**建立面向教学内容的结构化渲染协议，并让 Markdown 退回到 projection 层。**

这是当前条件下最稳健、最符合 first principles、也最符合项目现有大方向的路线。

如果继续沿“文本为主、前端猜测、局部补丁”的路径前进：

1. 选择题问题还会反复出现
2. 表格体验很难真正达到教学产品标准
3. 公式和图表接入会越来越难
4. 双端维护成本会持续上升

如果按本 PRD 推进，则可以在不新增第二套聊天入口、不引入重客户端依赖、不破坏现有产品主线的前提下，把微信小程序内容呈现能力升级到真正可持续演进的顶尖水平。
