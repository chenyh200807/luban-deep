# 鲁班「让每个学员爱上」飞轮北极星 + 治本接线稿 v1.1

> **Status: Proposed / 北极星 + 接线 reconciliation 稿 v1.1(已折入 Codex 异源对抗诚实化,§0.5)。**
> **定位(不 fork 第二权威)**：本稿**不新建**任何模块/schema/authority。语义仍归 [双轮设计 v3.2](2026-07-02-luban-learn-review-double-wheel-design.md) / [五模块 IA brief](2026-07-02-luban-five-module-ia-frontend-brief.md)(在 `origin/docs/five-module-ia-brief` 分支) / [PRD v1.3](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)，**冲突一律以它们为准**。本稿只做三件既有稿没有显式做的事：(1) 用五专家 + root-cause 方法 **ground-truth 修正"飞轮不转"的真根因**(推翻了此前"孤岛未消费"的假设)；(2) 补齐"**接通 ≠ 爱上**"的差——四个"被懂"时刻；(3) 给**最小 → 完整**的分层接线蓝图与红队 must-fix 安全阀。
> **Date: 2026-07-03**
> **产出方式**：root-cause-debugging skill 框定 + 五位对结果负责的顶尖专家(产品留存与情感 / 学习科学 / 系统架构与单一权威 / 对抗红队 / 极简裁剪)并行进驻 + 主控逐条 ground-truth 裁决 + **Codex 异源对抗(有仓库访问权,已折入 §0.5)**。
> **诚实口径(Codex 对抗后收敛,写死顶部防乐观复发)**：根因修正**部分站得住**——"学情孤岛未消费"靶心对**旧面(home/chat)**确实被推翻(飞轮主干接通),但"净删码/最小接线/只做一条就转一格"是**我重犯了 v3.2 被打回过的『只需接线』乐观叙事**。真相是:**接通在旧面且在 flag 背后(`_HOME_PERSONALIZATION_ENABLED`);首页权威收口(需 adapter+改下游)、新面集成(新站面吃独立静态端点)、pack 签发=0 —— 三处仍非平凡地卡着飞轮。**

---

## 0. 一句话北极星

> **每天打开鲁班,它已经替你想好今天该攻哪一题——而这个判断确实是从你昨天的作答里长出来的,不是随机、不是通用课表、是你的。**

拆成两个不可再分的原子(裁剪官第一性重述)：
1. **"今天攻哪题"是被替你决定好的** —— 消灭付费一号痛点"不知道先学哪块"(一手付费反馈逐字)。
2. **这个决定证明它读过你** —— 昨天你漏的采分点,今天变成下一站的理由 / 变成换皮复测。

"爱上"不是功能丰富,是这两件事被反复兑现,外加一层**接住负情绪**的暖。

---

## 0.5 Codex 异源对抗裁决记录(2026-07-03)

Codex(GPT 系,有仓库访问权)独立 file:line 复核本稿断言,判"根因修正部分站得住 + 一个新乐观叙事"。主控逐条 ground-truth 采信如下(与双轮 v3.2 §0.5 同一套诚实化流程):

**采信 7 项(已折入下文)**：
1. **"conversation_context_text 无条件承载 PCP"口径错**：PCP 走 **metadata** 注入(`turn_runtime.py:5732`),`:5617` 的 `conversation_context_text` 只是 history 文本,是两条独立注入。PCP **确实到达 LLM**(deep_question `deep_question.py:191/265` 转成生成锚文本),**非 dormant**——但连接 B 的接线口径按此改写(§1/§3)。
2. **病1 收口"净删码"是过度声称**：首页 member-local `review`/`weak_nodes` 喂多个下游 builder(`service.py:6497/6758/6798` 的 `today_focus`/`study_plan`/feedback),收口成读 canonical **需 adapter/mapping + 改下游,不是净删**。
3. **"只做①一条就转一格"低估工作量**:新站面 `stations.js:141-157` 直接吃静态 `/api/v1/luban/lessons`(`api.js:841`),**完全没消费 recommended_prompts 投影**;"让新面消费既有投影"是一坨**非平凡前端集成**,不是一行。
4. **"已接通"只在 flag 背后成立**:home 投影受 `_HOME_PERSONALIZATION_ENABLED` 门控(`service.py:6393`)。
5. **阈值预登记在本稿是空壳**:只说"spike 前钉死",没给 D1/D7 具体数——必须启动前钉进文档(§5-4 升为硬 TODO)。
6. **"全 candidate/coarse_review"不精确**:部分是 direct/composite candidate;判分 registry = **18 published / 1 draft / 1 blocked**(`registry_report.json:263`)。深 pack(讲懂/闯关内容)才是 0 published。
7. **冷启动"NBA 本身返[]"过宽**:是 **readback/home NBA 路径**对新用户空(`writeback.py:527`);case-grading writeback 能从**当前判分 intent 直建** personalization(`writeback.py:460`)。

**驳回 3 项(Codex 复核维持我的判断)**：
- 对话 context **非 dormant**(到达 deep-question 生成)——所以病 3 不含"对话没接学情",对话 context **已通**,缺的是"新面/被懂时刻",别把已通的说成没通。
- `revalidation_queue` **不造第二调度器**(明确复用 canonical priority,`revalidation_queue.py:70`)。
- **非硬 fork**(无新 code/schema/authority),但 Codex 点名**"叙事 fork 风险"成立**——本稿一度重引入 v3.2 已警告的乐观,顶部诚实口径即针对此。

**总裁决(Codex 原话收敛)**：方向没被击杀(孤岛靶心对旧面确被推翻);被击杀且已收编的,是"最小接线/净删码"的新乐观。**三处非平凡卡点:首页收口 + 新面集成 + pack 签发。**

---

## 1. 修正后的真根因(推翻原假设,五专家 ground-truth,带 file:line)

> ⚠️ 立此存照:本稿最初的靶心是"学情单一驱动权威被生产但没被跨模块消费(unconsumed island)"。**架构专家沿 producer→consumer 逐行核实主仓代码后,这个假设被推翻了一大半**——飞轮主干其实已经接通。真病是一个**复合四病**,而且主病是"相反的病"(第二权威,不是孤岛)。诚实记录以防未来重蹈。

### 病 1 · 架构 `authority drift` + 新面旁路(治本可修,net-simplifying)
飞轮**后端主干已接通且干净**：
- 单一排序权威 `prioritize_training_intents`(`services/learner_state/training_intent.py:141`),公式在 `_intent_priority`(:183)。**前端 grep priority 零命中**(前端零重排,正确)。
- 连接 A(学习站序)：`member_console/service.py:6415` `_build_home_learning_projection` → `home_personalization.build_home_dashboard_learning_projection`(吃 training_intent)→ `recommended_prompts`(写入 `service.py:6408`)→ 前端 `utils/learning-home-view-model.js:164/172` 消费(只 map/filter,不重算 priority)。⚠️ **受 flag `_HOME_PERSONALIZATION_ENABLED` 门控**(`service.py:6393`)。
- 连接 B(对话 context)：`chat.js` → `mobile.py:1991` `prompt_intent` → `turn_runtime.py:5468` `build_personalization_context_pack` → **作为 metadata 注入**(`:5732`,**注意:不是** `conversation_context_text`,`:5617` 只是 history 文本)→ `deep_question.py:191/265` 读它转成生成锚文本 **真喂进 LLM(非 dormant)**。走单一 `/api/v1/ws`。**连接 B 已通,别当缺口。**
- 连接 D(学情)：`report.js` 真读 `learning_report_read_model`(schemaVersion=2),唯一权威,无镜像。
- `next_best_action.py:44` 显式声明"只解释处方、绝不当第二处方源"(`revalidation_queue.py:70` 同样复用 priority、不另立公式,**非第二调度器**)。

**真缺口只有两处**：
- **(a) 第二权威**：首页 dashboard 的 `review` 计数(`member["review_due"]`,`member_console/service.py:6359-6361`)和 `weak_nodes`(`_report_mastery_items(member)`,`:6352`)用 **member 本地启发式,绕过** canonical `revalidation_queue`(`:24`)/ `learning_report_read_model`。
- **(b) 新面旁路**:`luban/five-module-implementation` 分支的新学习面 `stations.js` 读**静态 `getLubanLessons`(registry_slot 一次性排)**,**没消费**已接好的 `recommended_prompts` 投影 —— 所以新 UI 不 SHOW 后端已经在驱动的飞轮。

→ **治本 = 收口 (a) 让首页读 canonical + (b) 让新面消费既有投影。不造引擎、不加排序器。** ⚠️**诚实工作量(Codex 采信,别再说"净删码")**:(a) 首页 `review`/`weak_nodes` 喂多个下游 builder(`service.py:6497/6758/6798` 的 today_focus/study_plan/feedback),收口需 **canonical→旧形状的 adapter/mapping + 改下游**,不是净删;(b) 新站面 `stations.js:141-157` 直接吃静态 `/api/v1/luban/lessons`(`api.js:841`),让它改吃 `recommended_prompts` 是**非平凡前端集成**。方向是治本(消第二权威),但成本是"中"不是"零"。

### 病 2 · 内容真相 · 签发 = 0(路由治不了,红队核实)
- 判分 artifact 有 `published`:**18 published / 1 draft / 1 blocked**(`registry_v0_20260604/registry_report.json:263`)——**判分权威存在**。
- **但深 Pack / 动画卡(讲懂/闯关/考点卡的内容)`published:true` 出现 0 次**:status 是 `candidate_teaching_prototype`/`coarse_review`(部分是 direct/composite candidate,非一律 coarse_review——Codex 采信的口径修正)。双轮投影门 §7② 要求 `published:true` → **现在跑,零个深 Pack 通过,fail-closed 拦全部**。
- **产品能否铺开完全卡在教研签发产能(76 个 pack 文件,0 published),不卡工程。** 这是 root-cause 方法点名的"内容真相病"——fall-through 回主 LLM 也变不出它没有的签发内容,**别用黑名单/探测闸冒充**。

### 病 3 · 情感 · "被懂"时刻缺失(接通 ≠ 爱上)
飞轮连通只保证系统"知道"我;**"感到被知道"要靠四个被懂时刻显式设计**,而现计划把它们全埋在交接时刻一处、还过载。被懂感来自"**系统引用了一个只有我知道的事实**",泛化文案 = 没被懂。现文案铁律只有防御性(禁用词),缺进攻性(主动说出关于我的事实)。

### 病 4 · 冷启动 · readback/home NBA 空态(demo 会假绿的真洞)
**readback/home 路径**的 NBA 结构上依赖历史判分事件(`writeback.py:527` `list_memory_events`)。**新用户/首考零历史 → 该路径 NBA 返 `[]`** → §6.1 Hero 位"下一站卡""今日最痛考点"无数据可渲染 → day-0 飞轮转个寂寞。**内部账号都有历史 → demo 假绿;真上线新用户白屏。**(Codex 采信的收窄:case-grading writeback `writeback.py:460` 能从**当前判分 intent 直建** personalization——所以"答完一题当场"有信号;空洞只在"还没答过任何题"的 day-0 首屏。)

---

## 2. 理想的"被爱"体验:学员的一天 / 四个被懂时刻

> 情感专家结论:接通是**架构治本**(消第二权威 + 让新面消费信号);爱上是**情感治本**(四个被懂时刻显式化)。而这些被懂所需的事实**全都已经在既有权威里**,只差翻译成学员能感到的一句话,在对的时机说出来。

| 时刻 | 系统动作(读哪个既有权威) | 学员该产生的情绪 | 被懂时刻? |
|---|---|---|---|
| 打开(0s) | 英雄位:距考 X 天 + 下一站 + "为什么是它"(读 home_personalization/miss_count) | "不用想今天学啥"——决策卸载 | — |
| 知道今天干嘛(5s) | 下一站带**个性化理由**:"你上次机电这块漏了 2 个采分点,这站正好补"(读 miss_count/error_events) | "它记得我上次" | **被懂 ①** |
| 学完有约定(3-5min) | 交接时刻:"漏的 2 个已进错因银行,附解药。明天换身皮再考你一次——明天见。"(读 error_events + R4) | "有人在等我明天回来" | **被懂 ②(约定)** |
| 到期回来(次日) | 复习:"这 2 个再看一眼就稳了"(读 revalidation_queue,复考者暖色) | "就差一步" | **被懂 ③(接住)** |
| 问问题(任意,最高频) | 对话拉学情 context:"记得你在攻机电,这题正好用上"(读 personalization_context,已通) | "它已经懂我,不用从头解释" | **被懂 ④(最高频)** |
| 照镜子(周末) | 学情:掌握地图从红→黄→绿的**位移**(读 learning_report 周 diff) | "我在变强"——留存核燃料 | 变强叙事 |

**唯一可证伪的爱上信号 = D1→D2 换皮兑现**:交接说了"明天换皮考你",次日**真的**用同一考点 R4 变体考一次。兑现→"它说话算话";食言(变体产能不足静默降级)→信任一次性击穿(复考者尤其不原谅)。

---

## 3. 飞轮四连接:最小 → 完整阶梯 + 精确接线(file:line,绝不新建)

裁剪官 love/complexity 排序 + 架构接线现状,合并成一张阶梯:

| 阶 | 连接 | 现状(架构核实) | 要做的最小动作 | 绝不新建 |
|---|---|---|---|---|
| **①(先做,但非"一行",Codex 采信)** | 学情→学习每晚重排 | 后端投影已接(home_personalization,**flag `_HOME_PERSONALIZATION_ENABLED` 门控**);**新面 `stations.js:141` 旁路吃静态 `/api/v1/luban/lessons`** | (工作量"中")让新学习面**改吃** `recommended_prompts` 投影(非平凡前端集成)+ 首页 review/weak_nodes 收口读 canonical(需 adapter+改下游 today_focus/study_plan,非净删) | 重排器/registry_slot 调度器/前端 priority;不碰 `prioritize_training_intents` |
| **②(留存钩,gated on 3 雷)** | 交接→次日换皮复测 | `revalidation_queue` v0 首跳天然支持次日;R4 变体需编译期预生成 | 只做"次日单跳",不建完整 SR 引擎 | 完整多跳/分相/exam_date(阶段 2) |
| **③(闭环地基)** | 判分/复测→学情证据回灌 | sink `append_memory_event` 现成 + 3 个 payload builder | 复测数据回灌,复用现有 3 builder | **禁第 4 个 payload builder**;C1 EVIDENCE 回灌闭合 |
| **④(已通,只接深链)** | 学情→对话 context | **已是 live 不变量**(`conversation_context_text` 无条件注入,3/3 live eval) | 只接对话答后三钩子深链(练同类→学习/错因→复习/看学情→学情) | 专用 ws 路由/第二 context builder/字面门控 |

**最小可爱集 = 只做 ①**:它单独就能让飞轮"转一格给学员看"(day-1 写第一站成分=第一份摸底 → 当晚重排 → day-2 打开下一站变了、理由变了),直击付费一号痛点,零新 authority。递增:①→②单跳→③→④。

**诚实边界(Codex 采信,必须遵守)**:考频 authority 未建成前(`exam_weight` 恒 1.0,`scoring_point_map_read_model.py:290`),①的重排只承诺"**纯 miss_count 薄弱分 + registry 静态 priority**",**不对外说"考频加权"**。

---

## 4. 让"爱上"落地:四个被懂时刻的文案与触发(情感承重墙)

**触发四原则**(情感专家):① **具体 > 温暖**(引用只有我知道的事实,碾压空泛鸡汤——30-50 岁工程男信数据不信"我相信你");② **归因于路径,不归因于人**(失败→"这点再看一眼就稳了",永不"你这块不行");③ **就差一步最划算**(锚"你已走 X,只差 Y");④ **约定优先于提醒**("明天见"是关系,"你有 3 个待复习"是催收)。

| 触发时机 | 文案(示例) | 权威源 |
|---|---|---|
| 下一站副标题 | "上次机电这块你漏了 2 个采分点,这站正好补" | miss_count |
| 交接时刻(仅此一句约定) | "漏的 2 个已进错因,附解药。明天换身皮再考你一次——明天见。" | error_events + R4 |
| 复习到期(复考者暖色) | "这 2 个再看一眼就稳了" | revalidation_queue |
| 变体复测答对 | "换了皮你也认出来了——这是真懂,不是背的"(允许词,非"看穿") | R4 判分 |
| 对话进入(拉 context) | "记得你在攻机电,这题正好用上" | personalization_context |
| 免费第 3 站毕业 | "3 站走完,已经能看出你的强弱了。剩下这条路我帮你排好了,继续?" | 学情诊断 |
| 周对比 | "这周你把机电从薄弱补到基本稳,还剩 1 处" | learning_report 周 diff |

**绝不可砍的情感承重墙**(裁剪官):暖色文案铁律 / 复考者不渲染红灯墙 / 交接时刻那一屏 / R8 解药 / "为什么是这站"理由 / 锁定露脸。**对复考焦虑人群,情感层就是承重墙,不是装饰。**

---

## 5. 三个真瓶颈的安全阀(红队 must-fix,阶段 1 启动前)

1. **[MUST] 冷启动 NBA 空态**(病 4):day-0 第一动作**不能依赖 NBA**。首站 = 摸底(写成分产第一份学情),Hero/下一站在 NBA 为空时用**确定性 fallback**(registry priority 静态排序),绝不白屏。
2. **[MUST] 内容签发 = 唯一硬约束**(病 2):Pack manifest + 签发工作流是阶段 1 前置真血径。spike 老实只用 3-5 个已签发包,其余站显式"即将开通"。**别把 candidate 当 published 投影。**
3. **[MUST] 情感兑现的 fail-closed**:变体池非空才渲染"明天见"承诺(食言击穿信任);微信订阅推送**全仓 0 实现** → 链路建成前"明天见"降级为 App 内红点(§D12);**复测难度必须匹配它能证明的掌握层级**(学习科学新增 M0 锁:近迁移变体=只刷 stability 保鲜、远迁移变体=才 promote mastery,复用 R4 编译期属性,**禁 runtime 新造难度 registry**)。
4. **[MUST] 留存度量防假绿**(eval-design):内部/测试账号用 `qa_`/`operator_` 前缀硬隔离出量;埋点未接 BI 不许对外收数;**加弱对照臂**("换皮变体" vs "同题重现")分离"教学价值 vs 新鲜感";主指标 = **未复习后的客观保持率 + 做了复测动作的回访**(曝光≠回访);通过阈值 spike 启动前钉死进文档(防事后挪门柱)。
5. **[MUST] spike 按人格分层招募**:付费核心 = 复考挫败者 + 冲刺 30 天,其飞轮价值依赖 exam_date + lapse-reopen(阶段 2)→ 纯首考/免费样本**验不到付费人群的爱上机制**。分层看留存,别混一个数。

---

## 6. 分层落地(gated,不偷跑 40 站)

- **阶段 0(现在,独立技术债,不受落地闸约束)**:收口病 1(a) 首页第二权威(净删,后端投影层,前端零改);D15 埋点前置接入 TurnEventLog/BI。
- **阶段 1(最小可爱 spike = PRD v1.3 留存实验本体)**:连接 ① + ② 单跳 + 被懂时刻情感层,3-5 个**已签发**包(建议含安全事故卡样张),按人格分层招募,弱对照臂,阈值预登记。主指标见 §5-4。**重排只对 spike 内 3-5 站生效,不外扩未签发站。**
- **阶段 2+(硬闸在阶段 1 D1/D7 之后)**:连接 ③④ 全连接;完整 SR 引擎(exam_date 地平线 / 新学复习分相 / lapse 重开 / 堆积降级);考点卡 / 五层闯关完整版;更多站量产(1→5→15→40 逐级 gated)。

**可见里程碑**:阶段 0 = 首页计数变准(读 canonical);阶段 1 = 学员 day-2 亲眼看到下一站按 ta 的作答变了 + 次日换皮兑现;阶段 2 = 冲刺党的复习按距考天数变形。

---

## 7. 不确定性登记 + 验证 / 替代(汇五专家)

| # | 不确定处 | 验证 / 替代 |
|---|---|---|
| U1 | ①重排的 D0 说服力(冷启动零学情,理由退化为 priority) | 静态 HTML 样张给 3-5 真实一建考生看 day-0,问"这理由让你觉得懂你吗";替代:群体理由"多数考生从这站起步+覆盖 XX 分",别硬装个性化 |
| U2 | "被懂"是否被感知(工程通≠情感通) | A/B:下一站**带理由 vs 不带**看点击率;交接**带约定 vs 纯反馈**看次日回访。这是区分两者的唯一手段 |
| U3 | 学情周 diff 是否零新增(依赖 learning_report 是否带时序快照) | 读源码确认;若需存快照=呈现层缓存(fail-open,非真值);替代:先做"本次 vs 首次摸底"两点对比 |
| U4 | ②变体产能(单母题几个变体撑 1 个月复测) | §12 P0 实测教研产一个合格变体耗时 + 过判分内核一致性门;**这颗雷不排除,②不进最小集**;替代:低频考点只做普通复习不换皮 |
| U5 | miss_count 单信号排序 = 好的学习顺序? | 与教研人工排序小样本一致性对比 / A/B(miss_count vs 静态 priority)看单位时间增益;无显著增益则退回静态 priority |
| U6 | 复习引擎调度是否含时间衰减(防 spacing 失衡) | 硬要求:复习重排含"距上次复测天数"衰减项,**别把学习 tab 的纯 miss_count 复用到复习引擎** |
| U7 | ③回灌的幻觉回环(MEMORY:bot 自强化幻觉循环) | 硬门:C1 memory_kind 隔离 + `mastery_effect` 硬钉 none + 轻练走 `claim_promotion` 不关闭弱点;上线前跑持久态 0→0 非 LLM 断言测试 |

---

## 8. 三原则逐条自检 + 红线

**thin wrappers fat skills**:唯一后端改动(病 1 收口)是让首页 wrapper **变更薄**(删本地 review/mastery 计算,改读既有 fat read-model)= 净删码。全部连接复用既有 6 个权威,零新 service/schema/route/字段。✅

**first principles**:飞轮不转的真因不是"没接",是**一处 member-local 启发式绕过 canonical + 新面旁路 + 内容 0 签发 + 冷启动空态**。治本 = 收口第二权威 + 让新面消费既有信号 + 补被懂时刻 + 挂安全阀,**不是造飞轮**(引擎已存在)。✅

**less is more**:最小可爱集 = ① 一条;砍 6 项脂肪(句式积木拖拽 / 考点卡独立线 / 五层闯关中间两层 / 断更·总量·堆积三件 / 显式摸底页 / 四包计费页,全部 spike 后置);情感层不可砍。✅

**红线(不可破)**:① 不碰 `prioritize_training_intents`(唯一排序权威);② 不加 mobile tutorbot ws 专用路由(走单一 `/api/v1/ws`);③ 不新建第 4 个 payload builder / 第二调度器 / 前端 priority;④ 不 AI 选卡 / 不 AI 补错因分辨率(E02/E07 两桶,禁编);⑤ 不偷跑到 40 站(gated on D1/D7);⑥ M0 reality-lock 不放松(掌握只由客观复测升,复测难度须匹配掌握层级);⑦ **不 fork 第二 authority**——本稿零新权威。

---

## 9. 与既有计划的关系(不 fork)

本稿 = **北极星 + 治本接线的 reconciliation 层**。语义深度归双轮 v3.2、IA 归五模块 brief、North Star 归 PRD v1.3,**冲突以它们为准**。本稿唯一新增的是:五专家 ground-truth 修正的真根因(病 1-4)、四个被懂时刻的文案与触发、红队 must-fix 安全阀清单、最小→完整接线阶梯——**全部零新 authority、零新概念、零新调度器**。挂 `docs/plan/INDEX.md`。**已折入 Codex 异源对抗(§0.5),本稿为 v1.1 诚实化形态**——诚实口径见顶部:接通在旧面+flag 背后,三处非平凡卡点(首页收口/新面集成/pack 签发),不再宣称"净删码/一条就转"。
