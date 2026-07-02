# 鲁班移动端 考点小课 引流与会员转化 专项计划

> Status: Proposed / Acquisition + conversion child plan
> Date: 2026-07-01
> Parent authority: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)（PRD v1.3，留存闭环主菜）
> 相关设计规格: [2026-06-11-luban-mobile-ui-ux-design-system-and-screen-spec.md](2026-06-11-luban-mobile-ui-ux-design-system-and-screen-spec.md)
> 内容供给来源: [2026-06-18-luban-animation-learning-system-master-plan.md](2026-06-18-luban-animation-learning-system-master-plan.md) / [2026-06-17-luban-explainer-motion-template-engine-v0-principles.md](2026-06-17-luban-explainer-motion-template-engine-v0-principles.md)

## 0. 一句话总控

把已有的教学动画卡（图解微课）当作**引流钩子**：免费学员可免费学 3 个「考点小课」，想继续则购买会员。目的是用学员熟悉的「视频交互」作为零门槛入口，让学员**亲身撞见**系统已经做得不错、但缺乏直观体验的强能力（系统出题 / 答题 / 解题 / 推荐下一步），从而愿意探索小程序并转化为会员。

**定位铁律：考点小课是「桥」，不是「目的地」。** 免费 3 个的成功标准不是「看了 3 段视频」，而是「完整走了 3 遍产品飞轮（看 → 练 → 诊断 → 推荐）」，让学员在免费额度内真实体验自适应能力，付费理由由学员自己产生的学情证据驱动。

## 1. 与 PRD v1.3 的定位关系（张力登记，必须先读）

本计划**不推翻** PRD v1.3 基于第一波内测数据的收口，也**不改动** v1.3 的 P0A 留存主菜范围。二者是漏斗的不同层：

| 维度 | 归属 | 本计划角色 |
| --- | --- | --- |
| 获客 / 首次体验 / 付费转化（漏斗顶部） | 本计划（新增） | 主体 |
| 每日留存闭环：今日任务 → 轻练 → 诊断 → 复测（漏斗中部） | PRD v1.3 | 只复用，不改 |
| 采分点级判分、learner truth | 既有 authority | 只引用 |

**需用户后续拍板的优先级问题（本计划不擅自决定）**：PRD v1.3 明确把「会员体系」「视频教学」列为 P0A **非目标 / gated on 留存**。本计划要把「视频教学」从 gated 提前到**引流试点**，并引入**会员转化**。这是对 v1.3 优先级顺序的调整，属产品战略决策：

- 选项 A：引流试点与 P0A 留存 spike **并行**（都要真实小样本数据）。
- 选项 B：引流试点**排在** P0A 留存 spike 之后（先证明人会回来，再谈拉新转化）。
- 选项 C：引流试点**替代** P0A spike 成为首个对外验证面（风险最高，留存假设未验证就先做转化）。

本计划默认按**选项 A**推进（并行、各自小样本验证），最终顺序以用户拍板为准。

## 2. 文案基调铁律（全产品适用，不只本功能）

对复考成人，「看穿」类词汇带审视 / 揭短语气（暗示「你被识破了、你不懂装懂」），居高临下，损伤信任。

- **禁用**：看穿、识破、揭穿、拆穿、原来你不会、露馅、你以为你懂了其实……
- **改用**（帮他、站他这边、给他掌控感）：讲明白 / 一次搞懂 / 帮你拿下 / 顺手做一道 / 来试试 / 你是真懂了不是背的 / 这一点再看一眼就稳了 / 顺手帮你看到 X 补一下会更稳。
- 原则一句话：**永远是「帮你变强」，不是「指出你不行」。**

功能命名候选（定一个后全文替换，本文用「考点小课」占位）：`考点小课` / `秒懂动画` / `3分钟小课` / `一看就懂`。

## 3. 单一 Authority 边界（防造第二套）

本计划是**前端编排 + thin wrapper**，不新建任何后端 authority：

| 用到的能力 | 归属现有 authority | 本计划角色 |
| --- | --- | --- |
| 动画内容 | `luban_teaching_animation` 资产 + `canonical_taxonomy_refs`（对齐 60-slot 注册表） | 只引用 |
| 播完即练的判分 | 既有判分内核 → 写 `learning_evidence` | 只触发，不改判分 |
| 诊断 / 推荐下一步 | `training_intent` / `NextBestAction` | 只读并渲染 |
| 免费额度 / 会员 | 既有 member / wallet 服务（按 `canonical_uid`） | 仅加一个配额计数，挂钱包域，不新建计费 authority |
| 页面宿主 | `packageDeeptutor` 现有页面 | 学习首屏增区块，不新开 Tab |

**唯一新增的最小件**：`free_microlesson_quota`（免费额度计数，归 member / wallet 域）+ 前端「看 → 练 → 诊断 → 付费」编排 viewmodel。仅此。

## 4. 目标 / 非目标

目标：

- 用熟悉的视频入口把陌生 / 免费学员带进产品，并在免费额度内让其完整体验一次产品飞轮。
- 用学员自己产生的学情证据驱动会员转化，而非硬付费墙。
- 让考点小课成为把学员分发进 5 模块（学习 / 复习 / 对话 / 学情 / 我的）的「导览员」。（2026-07-02 对齐：原「笔记」模块经 [双轮设计 v3](2026-07-02-luban-learn-review-double-wheel-design.md) 修正为「复习」——统摄考点卡 + 错题本两种复习单元，模块定义以 v3 为准。）

非目标：

- 不新开「微课」Tab（把亮点降级成货架，会切断转化链）。
- 不做纯播放引流（看完 3 个撞墙、体验不到自适应能力）。
- 不新建第二套题库 / learner memory / 推荐 / 计费 authority。
- 不做「看广告解锁」等廉价钩子（稀释复考成人信任）。
- 不在排版 / 知识正确性未过人眼核前，把任何一张卡对外当引流物。

## 5. 5 模块内的落点

考点小课作为「学习」模块内的一种内容 + 贯穿 5 模块的导览员，不是独立导航目的地：

| 环节 | 归属 Tab | 角色 |
| --- | --- | --- |
| 讲解动画（讲懂） | 学习 | 今日任务卡的一种内容形态 / 学习首屏英雄位 |
| 播完即练（闯关） | 学习 | 产出 `learning_evidence`，走既有判分链 |
| 点播讲解 | 对话 | 学员问考点时 TutorBot 命中已编译动画包直接回放 |
| 错因回溯到当时讲解 | 学情 | 证据链里点一条错因，深链回对应动画卡那一幕 |
| 学完自动沉淀复习单元 | 复习 | 从已签发知识投影的考点卡 default-in 进间隔重复队列（可加个人助记 / 报错回流 / 归档；**不做 AI 摘要草稿、不做逐张采纳编辑**——形态修正依据与边界见 [双轮设计 v3](2026-07-02-luban-learn-review-double-wheel-design.md) §6/§8） |
| 免费额度 / 会员 | 我的 | 配额与升级入口；观看统计并入学情，不单列 |

## 6. 核心屏幕规格（A 方案三屏）

沿用 screen spec §1 设计方向（专业 / 克制 / 可信 / 诊断感 / 少娱乐化），并显式论证不违反其「禁止营销 hero 首页」：考点小课是**真教学内容且拖着「练 → 诊断」进入留存闭环**，不是营销装饰卡。

### 6.1 屏 1 — 「学习」首屏：考点小课英雄位

```text
今日任务 strip（现有，保留）
MicrolessonHeroCard（大封面帧 +「3分钟搞懂·<考点>」+ 免费/今日推荐标记）
FreeQuotaMeter（●●○ 收集感，非「已用 2/3」限制感）
MicrolessonRail（横滑；锁卡露脸 = 付费欲望种子）
底部导航（现有 4 Tab，不替换）
```

| 组件 | 数据源 | 关键字段 |
| --- | --- | --- |
| `MicrolessonHeroCard` | `NextBestAction` 选今日最痛考点 → 对应 `luban_teaching_animation` 资产 | `taxonomy_ref` / `cover_frame` / `title` / `duration_s` / `is_free` |
| `FreeQuotaMeter` | member/wallet `free_microlesson_quota` | `used` / `total=3` / `remaining` |
| `MicrolessonRail` | 按 `canonical_taxonomy_refs` 拉高频考点小课列表 | 每卡 `locked = !is_member && index >= remaining` |

### 6.2 屏 2 — 播完即练（从熟悉体验跨到自适应）

视频结尾**不给下一个视频，给一道题**（同一 `taxonomy_ref`）。

```text
观看完成 -> PostVideoQuizCard（题绑同一 taxonomy_ref）
        -> 既有判分内核
        -> 写 learning_evidence（不建第二套记录）
        -> 反馈：对=「你是真懂了，不是背的 ✅」/ 错=「这一点再看一眼就稳了 ↺」回放关键帧
```

### 6.3 屏 3 — 诊断 + 推荐 + 付费卡（付费理由 = 学员自己的学情）

```text
MiniDiagnosisCard（读 learning_evidence + training_intent，措辞走「帮你看到」基调）
NextLessonCard（读 NextBestAction；命中付费墙时锁定）
MembershipHook（member/wallet；付费文案绑「为你规划的完整路径」，不绑「多看视频」）
```

**付费触发时机 = 第 3 个小课诊断出来那一刻**（学员刚体验完整飞轮、刚被 `training_intent` 击中，情绪最高），不是等第 4 次点击才撞墙。

## 7. 导览员钩子映射（让学员有意愿探索小程序）

每个小课节点埋一个通往其他模块的钩子，文案全部「帮你」基调：

| 时刻 | 钩子文案 | 去 |
| --- | --- | --- |
| 练完那题 | 想多练几道？→ | 学习 |
| 诊断出来 | 看你的完整学情 → | 学情 |
| 有概念没懂 | 这块想细问？问问 AI → | 对话 |
| 想记住 | 已自动进你的复习计划，明天换皮复测 → | 复习 |
| 想解锁 | 开会员，继续学 → | 我的 |

## 8. 免费额度状态机（稀缺但不焦虑）

```text
未用(●●●) -> 学第1个(●●○) -> 学第2个(●○○) -> 学第3个诊断出(○○○ = 转化黄金点)
                                                     -> 展示 MembershipHook + 锁卡露脸 + 完整路径可视化(锁着)
```

- 进度用「解锁 / 收集」隐喻（●），不用「已消耗 2/3」。
- 绝不「看广告解锁」。

## 9. 实施阶段（不含代码执行，仅计划）

- Phase 0（内容前置）：选 3 个**高频薄弱考点**做首批免费小课；`canonical_taxonomy_refs` 登记（对齐 60-slot 注册表）；排版 + 知识正确性**人眼过手机静态核**（gate 绿 ≠ 画面对）。
- Phase 1（编排试点）：`packageDeeptutor` 学习首屏加 Hero/Quota/Rail + 播完即练 + 诊断付费卡；`free_microlesson_quota` 挂 member/wallet；练习写既有 `learning_evidence`。
- Phase 2（小样本验证）：量转化漏斗四数——看完率 → 练题率 → 诊断触达率 → 免费耗尽后付费点击率；并量次日回来率。

## 10. 验收标准

- 内容门：3 张卡全部过人眼核（排版不崩 + 知识不错 + taxonomy 已登记），否则不上线。
- 权威门：练习结果写入既有 `learning_evidence`，学情 / 付费卡的盲点数据从既有 read model / `NextBestAction` 读出，无第二套数据。
- 效果门（裁判指标）：以**付费点击率 + 次日回来率**为准，而非看完率 / 满意度。
- IA 门：不新增 Tab；不出现营销 hero 装饰卡（每张卡必须拖着练 → 诊断）。

## 11. 红线 / 伪进展

- 全产品文案禁「看穿」类审视语气，只用「帮你变强」基调。
- 考点小课是桥不是死胡同——绝不单开 Tab、绝不纯播放。
- 引流物排版 / 知识未过人眼核不许上线（给陌生人的第一印象，讲错一次永久失信，复考成人尤其不原谅）。
- 「上线了 3 个视频」≠「引流跑通」，裁判是付费点击率 + 次日回来率。
- 会员 / 余额真值在既有 wallet（Supabase 钱包，按 `canonical_uid`），`free_microlesson_quota` 只是配额计数，不得成为第二套会员真值。

## 12. 相关代码入口（供后续执行阶段参考，本计划不改代码）

- 页面宿主：`yousenwebview/packageDeeptutor/`（学习首屏、chat、report 等）。
- 动画资产：`artifacts/luban_case_family_assets/diagram_microlesson/`。
- 判分 → 证据：既有判分内核 → `learner_memory_events.learning_evidence`。
- 推荐：`training_intent` / `NextBestAction`（`Learning Brain` / `LearnerStateService`）。
- 会员 / 钱包：既有 member / wallet 服务。
