# 鲁班「主动学」学情生命周期融合改造计划 v1.1

> **Status: Proposed / 融合改造契约稿 v1.1(已折入 Codex 异源对抗,§0.6)。**
> **定位(不 fork)**:本稿把系统从「答疑提分系统」升级为「**也能主动学知识点的系统**」——新增学习/复习两大模块对学情的深度融合设计。语义边界:排序契约归 [双轮 v3.2](2026-07-02-luban-learn-review-double-wheel-design.md) §5.1、IA 归 [五模块 brief](2026-07-02-luban-five-module-ia-frontend-brief.md)、North Star 归 [PRD v1.3](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)、飞轮接线归 [北极星 v1.1](2026-07-03-luban-loved-flywheel-northstar-and-rootcause-wiring.md),**冲突以它们为准**。本稿只拥有:生命周期状态机、三类证据契约、跨模式组合规则、内容节奏与入口。**新增登记恰好一个呈现仲裁 read-model authority(`home_next_step_projection`,§3,register-before-use)——其余零新 authority**(Codex 裁决:诚实登记边界好过否认,"零新 authority"的原始声称不成立)。
> **Date: 2026-07-03**
> **产出方式**:三路资产/架构/方向并行测绘 → 四路复核专家(架构断言复核/A+ 红队/粒度与签发裁决/价值链验证)证伪优先复审 → 主控总裁决。所有 file:line 均经复核 agent 亲读源码核实。
> **owner 已拍板**:40 站路线已在生产管道,最终全部完成,**首发放 10 站**。

---

## 0. 北极星与系统定位跃迁

> **每天打开鲁班,它已经替你想好今天该攻哪一题——而这个判断确实是从你昨天的作答里长出来的,不是随机、不是通用课表、是你的。**

**系统定位跃迁**:今天的系统是**答题中心(reactive)**——学员带题来→判/解→gbrain 内化→推下一题→学情=薄弱点/趋势。教学动画+母题库开出一条新路:学员可以**在做错题之前主动把一个考点学会**。这逼学情从「答题表现档案」进化成「**每个考点在这个学员脑子里的生命周期状态**」:

```
未学 → 已学·待验证(看了讲懂) → 练过(答题判分) → 真懂(远迁移变体复测过) → 休眠·会忘(到期复验)
```

学习/复习不是挂在旁边的两个新模块,而是**给同一套学情喂两类新证据、给"下一步"加两个动作选项**。真值永远是那一套学情(账本→内化→claim→处方),学/练/复只是它的三个投影视图。

**三个用户价值承诺**(全部行为可证伪,见 §0.8):
1. **precise**:每次打开的 20 分钟都花在刀刃上——已会的不当新课重教,快忘的在忘掉前拽回来,没学的先教下一站该学的,每站说得出"为什么是它"。
2. **回访**:每天一个说话算话的约定("明天换皮再考你"),次日真兑现。
3. **上头**:换皮识破的能力确认 + 今日完成仪式 + 分数账本——不靠 streak 绑架。

## 0.5 四路复核裁决记录(2026-07-03,防重蹈)

写本稿前,前序结论经四路专家证伪优先复审。**采信并折入的修正**:

| # | 被修正的结论 | 修正后口径(已折入对应章节) |
|---|---|---|
| 1 | "跨模式 NBA=扩个枚举" | **证伪**。`next_best_action.py:46` 是硬编码二值非枚举扩展点,无 lifecycle 输入;learn 走处方权威=动已注册 canonical schema(`learning_training_intent.v2`)+给未学发明遗忘语义=动核心。→ 改为**组合层方案**(§3),不进处方 |
| 2 | "新 evidence_level 汇点唯一" | **证伪**。语义散在 ≥7 处字面 map;**潜伏地雷**:`learning_synthesis.py:1175-1181` `_max_level` 把 `L3_mastery_signal/L2_real_retest` 排 0(比 L0 低)、confidence 兜底 0.3——今天生产"真懂"信号会被降级。→ 阶段 0 硬债(§6-1) |
| 3 | "深 pack 0 published" | **过时**。main 已签 5 包(A01/C02/J01/N01/S05,PR #333/#337/#339)+分支 F16(owner 07-03 批准);`_pack_manifest.json`(schema `luban_deep_pack_manifest.v0`,40 包全登记,`projection_green[]`)+ runtime 投影门消费者 `luban_lesson/read_model.py` 已通电(fail-closed:非绿灯对外与不存在同形) |
| 4 | 我方 A+ 排序推荐 | **90% 是 v3.2 §5.1 复述且"考频"措辞倒退**(exam_weight 恒 1.0 `scoring_point_map_read_model.py:290`;registry priority 是生产序非考频排名)。→ 排序条款只写"沿用 v3.2 §5.1"(§4) |
| 5 | "懂了的绝不再教" | 与 SR 哲学矛盾(v3.2 §6.1"已掌握非终态是休眠")。→ 改"**不当新课重教,休眠低频复验保鲜**",且 gated on D17 前端接线+变体池覆盖 |
| 6 | mastery 分裂范围 | 比原判窄:`estimate_mastery` **已接**学习报告(`learning_report_read_model.py:1108-1153→:883`);分裂只剩首页/雷达/章节盘(`member_console/service.py:6915/6901/6329` 读静态 `member.chapter_mastery`) |
| 7 | 引擎默认状态 | **大半 flag-dark**:`LEARNING_STATE_INFERENCE_V2` 全子闸默认 off(`cohort.py:17-20`)、auto-synthesis 默认 off+限 qa_/operator_(`learner_state/service.py:2459-2462`)、dream_cycle off。生产姿态=读时 dry-run。→ rollout 是一等工作量(§7) |

**幸存并加固的地基**:单一证据 sink `append_memory_event`(`learner_state/service.py:792`,14 调用点全经它);四层生命周期+claim 状态机+7 态 mastery(含遗忘衰减 `DECAY_PROFILES`)真实存在;防假掌握**双重**护栏(`mastery_estimator.py:212/243-247` + `learning_report_read_model.py:1353-1360`);`learner_signal.py:1-16` docstring 已固化"新非掌握信号"完整模式;conversation 证据已有 ladder 外 level `"exposed"` 先例(`conversation_learning_evidence.py:102-115`)。

## 0.6 Codex 异源对抗裁决记录(2026-07-03,第二道闸)

Codex(GPT 系,仓库访问权,26 条断言逐条 file:line 亲核)总裁决:"**不能按 v1 直接开工;§3 可收敛成受约束的 read-model spike,最大洞在 §2.1**"。主控逐条 ground-truth 裁决:

**采信 6 项(已折入)**:
1. **§2.1 原方案违反 contract(最大洞)**:"不设 `payload.event_type`"违反 `contracts/learner-state.md:397-404`(新写 learning evidence **必须**带 `event_type="learning_evidence"`,`contracts/index.yaml:604-610` 同),且缺 event_type 仍按 memory_kind 计入 `learning_state_projection` 的 `legacy_count`(`:116-120/:78-90`)——不是零污染是漏进状态披露。**Codex 给出的更干净修法已采纳**(§2.1 重写):带 event_type 守 contract,`progress_countable=false` 单独就够防 report 污染(`learning_report_read_model.py:1353-1360` 在 `:1379-1416` 之前跳过)。
2. **§3 必须改口注册**:组合规则确实新增了"跨模式下一步展示裁决器"——不是第二练习处方(练仍由 training_intent 产出),但要**显式登记为 `home_next_step_projection` read-model authority**,不许说"零新 authority"。已采纳(§3 重写)。
3. **dedupe 按日"钉死"过早**:dedupe 命中会吞同日重看/阶段变化/二刷完成信号(`service.py:792-833`),回退为 U2 开放项,初始方案按日但按 `watched_stage` 细分 key。
4. **construction graph"零调用方"证伪**:已有 runtime(`learning_state_projection.py:33-35/:413-418`)/guard(`check_contract_guard.py:439-454`)/test 消费——准确说法是"**prerequisite 边未接入学习路线排序**,接入是增量消费"。已改(§4-2)。
5. **阶段 0 债 #1/#2 低估**:#1 跨 synthesis/RAG/deep_question/read_model 多处 map+真实排序 bug;#2 动首页/雷达/章节盘大文件——均改标**中大**(§6)。
6. **S05 源文件漂移**:`S05_临时用电三级配电.md:13` 仍标 `candidate_teaching_prototype` 且 R7 边界红(`:343`),与 manifest `published:true` 漂移——manifest 是签发权威(runtime 只认它),但漂移须回填源文件或在 manifest note 说明。登记 §5.1。

**驳回 2 项(附证据)**:
- "manifest/`luban_lesson/read_model.py`/S05 变体池不存在"——**分支视角假象**:Codex 在 `codex/jiagou` 分支上搜;主控 `git show origin/main` 实证三者全部存在(`projection_green=[A01,C02,J01,N01,S05]`,S05 `published:true`,`成品/_S05_variant_bank.v0.json` 实存)。F16 变体池确在分支未合 main(如实登记)。
- "§3 必然是第二练习处方源"——Codex 自己也驳回了(练的内容仍完全由 `training_intent.py:3-4` 说了算)。

**Codex 幸存确认**:26 条断言中 18 条属实(含 `_max_level` 地雷/白名单/双重防假掌握护栏/K01 jury/复测链路),融合论主体与四路复核结论一致。

## 0.8 可证伪成功判据(spike 启动前与 owner 钉死数字,防挪门柱)

| 目标 | 指标 | 建议锚 | 数据源 |
|---|---|---|---|
| 回访 | **D1 行动回访率**(次日完成被承诺的换皮复测,非仅打开) | ≥40% | 复测完成=判分事件(现有);交接曝光=**需新埋点** |
| 上头 | 加练率(超出当日队列的自主复习/多站) | ≥20% 活跃日 | 需新埋点 |
| 上头·排新鲜感 | W1→W3 D1 行动回访衰减 | W3 ≥ W1 的 60% | 10 站约可撑 2-3 周,**W4 后仍标不可测,诚实登记** |
| precise | 打开→首个学习动作耗时 | 中位 <30s | 需新埋点 |
| precise·主证伪器 | 理由文案 A/B(个性化理由 vs 群体理由的站启动率+D1) | 个性化臂显著优,否则理由=空话砍掉 | A/B 臂 |
| 真价值 vs 新鲜感 | 弱对照臂:换皮变体 vs 同题重现,同看 D1 行动回访 **且** 7 天延迟保持率 | 变体臂两项都赢(只赢留存=新鲜感;只赢保持=没上头) | 判分事件现有+分臂需建 |
| 信任 SLO | **承诺兑现率**(说了"明天见"次日真有变体可考) | ≥99%,跌破即停渲染承诺句 | 服务端计数(琐碎) |
| 采信门 | 下一站接受率 | ≥70%,**≥15 签发站后才采信**(10 站时标观察) | 需新埋点 |

红线:内部账号 `qa_`/`operator_` 硬隔离;埋点未接 BI 不对外收数(D15);按人格分层招募(复考挫败者单看,纯首考样本验不出付费人群)。

---

## 1. 生命周期状态机(学情的进化本体)

### 1.1 主键裁决:`pack_id`(=60-slot 注册表的考点实体)

- 签发真值(`_pack_manifest.json`)、路线排序(`registry_slot`)、卡托管(`web/public/luban-preview/<pack>/`)、复测变体池(`_<ID>_variant_bank.v0.json`)、jury、作答层**全部已以 pack_id 为 key**。
- taxonomy 叶(1976,frozen v1.1)**只做溯源锚**:粒度太细、`canonical_taxonomy_refs` 跨 pack 复用(如 `1A433000-B041` 同在 N01/N02/N04),直接当主键反查有歧义。
- "考点全集"= 60-slot 注册表 40 pack(slot 24/D14 缺位如实缺位),**不是 1976 叶**——未学态的枚举范围收敛到这个尺度,不撑爆 projection/compiled 缓存。

### 1.2 状态定义(全部落在既有结构上,不新建状态表)

| 状态 | 判定(既有结构) | file:line |
|---|---|---|
| **未学** | 该 pack 无任何证据事件(**投影层派生**:pack 全集 − 有证据集合,不碰 append-only 账本、不建第二状态表) | 派生点=学情投影拼装层;`revalidation_queue.py:184-190` 的 state 白名单 {weak,unstable,needs_revalidation} 天然忽略未学,不会误发复测 probe |
| **已学·待验证** | 存在学-evidence(§2.1)且无判分证据;`evidence_level="exposed"`(既有 ladder 外 level) | `conversation_learning_evidence.py:102-115` 先例 |
| **练过** | claim `observed(L0)/repeated(L1)` | `learning_synthesis.py:852-861` |
| **真懂** | claim `confirmed`(L2)且**远迁移变体复测通过**才亮绿(近迁移只刷 stability 不 promote——M0 复测难度匹配掌握层级) | `learning_synthesis.py:486-490`;R4 编译期迁移距离属性 |
| **休眠·会忘** | `stale` + `forgetting_risk` + `needs_revalidation`(分层半衰期) | `mastery_estimator.py:159-205`,`DECAY_PROFILES :21-32` |

### 1.3 UI 双轨映射(M0 一致,防视觉假掌握)

**生命周期轴与掌握轴视觉拆开**:
- **蓝环(接触)**:未学=灰空心;已学·待验证=灰底+蓝描边/勾标,文案"已学·待验证"——**绝不进入红黄绿色阶**(看动画就变黄=视觉虚报=变相打卡)。
- **红黄绿(掌握)**:只由客观判分/复测着色;绿=远迁移变体通过后才亮。
- 配一句产品宣言:"**我们不给你假绿——考过换皮变体才算数。**"对被假熟练感坑过的复考者,这句话本身就是被懂时刻。
- 复考者跳站/挑战后地图**当场按真实水平着色**(不许灰墙撒谎,D13 暖色铁律延伸)。

---

## 2. 三类证据契约(一条账本,三个来源)

### 2.1 学-evidence(唯一真正的新 writer——"学了"今天零 writer,`luban_lesson/read_model.py:13-15` 自声明不写任何学习证据)

**照 `learner_signal.py:1-16` 模板逐字执行**("新非掌握信号 = memory_kind learning_evidence + 新 source_feature 留在合成器白名单之外 + 只被定向读侧消费"):

```
append_memory_event(                       # 唯一 sink, service.py:792
  memory_kind = "learning_evidence",
  source_feature = "luban_lesson",         # 新值;保持在 learning_synthesis.py:342-348 白名单之外
  payload = {
    event_type: "learning_evidence",       # contract 硬要求(contracts/learner-state.md:397-404),不许省
    learning_signal_type: "lesson_viewed",
    pack_id, card_sha, watched_stage,      # 讲懂幕/闯关幕
    evidence_level: "exposed",             # 复用既有 ladder 外 level,不发明新 level
    quality: { progress_countable: false } # 唯一必需的防污染旋钮
  },
  dedupe_key = f"lesson_viewed:{user}:{pack_id}:{watched_stage}:{date}"  # 初始方案;去重语义=U2 开放项
)
```
(supabase 白名单口径修正:`supabase_writer.py:400-416` 白名单作用于 outbox `event_type`,row 构造在 `:423-431`;`learning_evidence` 在名单内。)

**防污染旋钮(Codex 逐消费者复核后的修正版——守 contract,靠 progress_countable)**:
1. **带** `event_type="learning_evidence"`(contract 硬要求)+ `progress_countable=false` → `learning_report_read_model.py:1353-1360` 在攒 attempt/streak(`:1379-1416`)**之前**跳过——看视频不刷练习数、不拉低掌握分。**没必要也不允许破坏 event_type contract 来防污染。**
2. **两个显式小改(带 event_type 的代价,必须做不许默认)**:①`home_personalization.py:495-514` 的"最近事件驱动 today_focus"选择器**过滤 `learning_signal_type="lesson_viewed"`**——学→练连续性由 §3 组合层显式做,不靠事件顶替(显式拍板:不顶替);②`learning_state_projection.py:78-90/:116-120` 给 `luban_lesson` 加显式分类,防 `legacy_count` 观测口径虚高。
3. `mastery_estimator.py:208-213` 因 progress_countable=false 跳过(第二道既有护栏)。

**学-活跃的呈现**:看动画计入蓝环+今日完成仪式,**不计入练习 streak**——诚实分离,防 Goodhart(用户拿最轻动作刷指标)。

### 2.2 练-evidence(现有,两处修)

- 案例判分(`construction_grading/writeback.py`)最干净:concept 归属唯一来自 taxonomy resolver 命中(`:627-655`),不命中不写。**保持**。
- 测评(`assessment/writeback.py:140-153`)混合脏:自由中文串经 `normalize_taxonomy_code`(只规范化不校验存在性,`taxonomy_authority.py:15-23`)照落 `node_code`。→ 阶段 0 修(§6-6)。

### 2.3 复-evidence(现有链路,两个折扣要还)

- 链路本身白送:复测=普通判分证据带 `training_intent_id`+`prescription_phase`(`writeback.py:62-66`)→ `verified` 需真实判分 probe(`prescription_outcome_read_model.py:103-107`)→ `revalidation_queue.py:44-49` 阻断已验证项。
- **折扣 1**:整条 verification 链在 `LEARNING_STATE_INFERENCE_V2.verification` 后面默认 off → §7 rollout。
- **折扣 2**:首页 review 路径(`home_learner_signals.py:87-91`)没传 prescription_outcomes/scoring_point_map,"复测已验证阻断"在首页实际未行使 → 接上(小)。

### 2.4 三类证据 → pack_id 的 join(粒度裁决落地)

| 证据 | join 路径 | 量级 |
|---|---|---|
| 学 | 天然同键(payload 直带 pack_id) | 小 |
| 练 | ① `question_id ∈ linked_question_ids(pack)`:从 37 份 `_<ID>_exam_evidence.json` 编译"题→pack"确定性映射(需题号↔题库 question_id 归一);② 兜底 `canonical_topic.taxonomy_code ∈ canonical_taxonomy_refs(pack)` 反查(需 `primary_taxonomy_ref` 消歧,§6-4);③ 再兜底"未归位"桶,如实展示不硬塞 | 中 |
| 复 | `training_intent.concept_id`=taxonomy_code(`writeback.py:606`)→ 复用②反查索引 | 小 |

---

## 3. 跨模式"下一步"三选一(组合层方案——本稿唯一较大的新设计判断,交 Codex 重点攻)

**不进处方权威。** learn 动作若走 `training_intent`,要动已注册 canonical schema(`learning_training_intent.v2`,register-before-use 闸)、给 `_MODES:24`/`_FULL_PHASES:35` 加相、给"未学"发明遗忘语义(`_intent_priority:183` 公式假设 forgetting_risk)——四路复核判定为"动核心非接线"。NBA 的明文不变量(`next_best_action.py:44-45` "never become a second prescription source")同时禁止在 NBA 层造第二决策源。

**方案:三权威各管各的,组合是一条确定性呈现规则,落在既有 home 投影拼装层**(`home_personalization` 已在组合 today_focus,同一汇点):

```
下一步 = первый非空项:
  1) 到期复:revalidation_queue 有 due probe        →「回炉:XX 再看一眼就稳了」
  2) 活跃练:training_intent 有 active intent        →「练:你漏的采分点,换个题面”
  3) 下一学:路线上第一个 未学∧绿灯签发 的站         →「学:下一站 XX(理由)」
  4) 全空(冷启动/毕业):确定性 fallback = registry 静态序第一个绿灯站(群体理由文案)
```

**登记形态(Codex 裁决采纳:诚实注册,不否认)**:此规则**显式登记为 `home_next_step_projection` read-model authority**(register-before-use 过闸),职责**只限 display arbitration**:①输出必须带 `mode/source_authority/source_ref/reason` 四字段(可审计每个"下一步"来自哪个权威);②禁写 ledger、禁生成/修改 training_intent、禁改 revalidation 状态、**禁前端/各 tab 再拼一次**(规则只存在这一份);③它不生成任何"该练什么"的内容判断——练的内容仍完全由 training_intent 说了算(`training_intent.py:3-4`),复由 revalidation_queue,学序由 registry+前置边。**它不是第二练习处方,但它是一个新登记的呈现仲裁 read-model——边界写清好过声称"零新 authority"。** 退路(若 spike 中被证明越权):learn 只作路线图固有语义,牺牲统一今日入口。

冷启动(病 4)同时被 4) 兜住:新用户零证据 → 1)2) 空 → 直接落"下一站=第一个绿灯站",绝不白屏。

---

## 4. 学习路线排序(条款收敛,不新立推荐)

1. **排序沿用双轮 v3.2 §5.1 契约,零新增决策**:章节路段(taxonomy L1-L6 分组)/ 默认序=registry 静态 priority / 每晚 miss_count 确定性重排(仅段内)/ 站点四态 / "为什么是这站"理由 / 可跳站不设前置锁。冲突以 v3.2 为准。
2. **前置边 day-1 接通,不"按需补"**:`deeptutor/services/taxonomy/construction_learning_graph.py` 已是 register-before-use 合规、教研拥有、带 `prerequisite` 边类型的既有模块(4 条种子边;**已有 runtime/guard/test 消费**——`learning_state_projection.py:33-35/:413-418`、`check_contract_guard.py:439-454`——只是 prerequisite 边**未接入学习路线排序**,接入是增量消费非新建,Codex 修正措辞)。day-1 动作:补 N 簇边(N01→N02/N04)+ N01→K01 工期臂(pack jury 记录背书:`K01_索赔成立与计算.md:431`"网络计划定量求解=索赔前置工具")+ 段内重排器一条前置过滤(未学前置 A 时不把 B 排到 A 前)。**这同时拆掉章序陷阱**:K01(432 章)在 taxonomy 序上先于 N01(433 章),纯章节分组会让新手先撞索赔计算。全量 DAG 维持死刑(v3.2 §11 已裁决;pack 体系"相邻不重叠+握手点"设计不变量=独立可学)。
3. **考频措辞纪律**:`exam_weight` 恒 1.0 期间,对外只说"按注册表优先级+你的薄弱分排",**禁称"考频加权"**。真考频最短路径=编译讲义_v8 各章"近五年分值排布"表为章级分值 authority(register-before-use 登记,禁 AI 判频)——列为独立小项,非本稿前置。
4. **"不当新课重教,休眠低频复验保鲜"**(替代"绝不再教"):已掌握站从学习路线**移出**、进复习引擎低频保鲜;该承诺 gated on D17 前端接线 + 变体池覆盖(§5)。

---

## 5. 内容节奏与入口(owner 已拍板:首发 10 站,最终 40)

### 5.1 首发 10 站的构成与节奏

- 现状:绿灯 6(main 5:A01/C02/J01/N01/S05,`git show origin/main` 实证 `projection_green` + 分支 F16,F16 合 main 是一个 PR)。→ **从 34 个 candidate 里按既有签发工作流再签 4 个**(batch PR 模式已走通一次:batch1 四包一个 PR,真题锚确定性核验零漂移;**可复制性待第二批验证**——Codex 采信,不当既成节奏声称)。
- **⚠️ S05 漂移登记(Codex 抓到)**:源文件 `S05_临时用电三级配电.md:13` 仍标 `candidate_teaching_prototype` 且 R7 边界红(`:343`),与 manifest `published:true` 漂移。manifest 是签发权威(runtime 只认它),但**漂移须回填源文件 status 或在 manifest note 说明豁免理由**——列入再签 4 包前的检查项。
- **卖节奏,不卖空气**:对外叙事="每天 20 分钟一个说话算话的约定 + 持续上新"。**"每周上新一站"是目标节奏非既成事实**(独立流水线证据待第二批 PR),对外锁定站只标"上新中",**已排期的才标时间**——付费承诺只覆盖已签发+明确排期的站(付费瞬间的信任核爆点,红队点名)。免费 3 站沿用 microlesson plan 的 `free_microlesson_quota`。
- **签发上新=回访机制**:上新推送/红点是天然的周回访钩。
- 10 站油箱≈2-3 周内容(20 分钟/天),叠加每周上新+复习引擎,**内容墙从 day-5 推到 W3+**;W3 后依赖上新节奏能否 ≥ 消耗速度——列入不确定性 U4。

### 5.2 变体池=承诺兑现的前提

- 现状 2/40(F16/S05)。**首发 10 站必须全配编译期预生成签发的变体池**(S05 实测:确定性生成器 75 变体/一致性门 100%/生成 <1ms——产能瓶颈在教研审核,列排期)。
- **fail-closed 文案门**:变体池非空才渲染"明天换皮再考你";池空的站交接时刻只说进度反馈,不许诺。承诺兑现率 SLO ≥99%(§0.8)。
- 近迁移变体=只刷 stability(保鲜);远迁移=才 promote mastery(M0);迁移距离用 R4 编译期属性,**禁 runtime 新造难度 registry**。

### 5.3 复考者 challenge-first day-0 入口(付费主力的价值兑现时刻)

- "这站我会了,直接考我" → 变体挑战(D17 `user_dispute`→复测挑战,**后端已实现、前端零接线**)→ 20 分钟连过 N 站,地图当场按真实水平着色;大概率 1-2 站被识破"只是背过"——正中复考者最深的伤口,价值兑现比首考更早更强。
- 跳站+挑战产生的证据照常喂学情;跳过未挑战的站保持"未学"如实呈现(不撒谎也不惩罚)。

### 5.4 交接时刻与上头机制(继承北极星 §2/§4,只补三样)

- **今日完成仪式**:"今天这站拿下了,够了,明天见。"——对累瘫工地党,"允许停止"本身就是奖励(closure 显式化,现设计缺)。
- **分数账本(雪耻叙事)**:"这条路线覆盖案例 XX 分,你已稳 Y 分"——exam_matrix 分值确定性派生(v3.2 §13-8 允许口径),把每个 20 分钟锚到他唯一在乎的数字。
- **换皮兑现判词**:"换了皮你也认出来了——这是真懂,不是背的"(允许词,禁"看穿")。
- **不做硬 streak**(工地排班不规律,断签即弃用);订阅推送只兑现"明天见"约定,一条营销就烧掉整个通道;衰减文案过 D13 暖色("再看一眼就稳了",绝不"你要忘光了")。

---

## 6. 阶段 0 硬债(先于功能,独立技术债通道,不受留存闸约束)

| # | 债 | 内容 | 量级 |
|---|---|---|---|
| 1 | **evidence_level 收权+排序地雷** | 语义收敛到单一汇点(`memory_lifecycle.py` 为宿主),清理 ≥7 处字面 map(`canonical_truth_policy.py:195`/`learning_synthesis.py:857,1175-1181`/`rag/compiled_truth_source.py:40-47`/`rag/provenance.py:21-26`/`learning_brain_read_model.py:42-47`/`capabilities/deep_question.py:166-169`);**修 `_max_level` 把 L3_mastery_signal/L2_real_retest 排 0 的地雷**——"真懂"上线前必修 | **中大**(Codex 校正:跨 synthesis/RAG/deep_question/read_model 多域) |
| 2 | 首页 mastery 收口收尾 | review 半已收(home_learner_signals);mastery 半(`collapsed:false` 自认)= `estimate_mastery` 聚合接入首页/雷达/章节盘,替代静态 `member.chapter_mastery`(读点:`member_console/service.py:6329-6333/6901-6913`;writer:`:960/7411-7412/2454`) | **中大**(Codex 校正:动 member_console 大文件三个面) |
| 3 | 数据修 3 处 | A01/A02 IR 缺 `canonical_taxonomy_refs`;S02 doc↔IR refs 漂移(裁决以注册表为准回填 IR);G01 脏状态值 `"answer_layer"` | 小 |
| 4 | `primary_taxonomy_ref` 机器可读化 | 注册表 §2/§5 硬门已要求、无人填;不填则 taxonomy_code→pack 反查有歧义 | 中 |
| 5 | 题→pack 映射编译 | exam_evidence 37 份 → 确定性映射 + 题号↔question_id 归一 | 中 |
| 6 | 测评 writeback 校验 | `node_code` 写入侧加 resolver 存在性校验(或读侧过滤),堵自由串污染 join | 小 |

## 7. flag/cohort rollout(一等工作量,不是附录)

现状:生命周期推断引擎在生产主要以**读时 dry-run** 形态存在——`LEARNING_STATE_INFERENCE_V2` 全子闸默认 off(`cohort.py:17-20`)、auto-synthesis 默认 off 且限 qa_/operator_(`service.py:2459-2462`)、dream_cycle off、`LUBAN_LESSON_CARD_BASE` 托管基址未配则客户端按无卡降级(`read_model.py:46-50`)。

**通电顺序与 spike 同步灰度**:qa_/operator_ → 内测 cohort → 全量;每步带观测(synthesis 延迟/claim 质量/复测队列行为)。**融合功能不得建在 dark 引擎上假装 live**——每个 §1-§3 的行为都要标注它依赖哪个 flag,验收时在目标 cohort 上真跑,不拿本地 dry-run 当部署证据。

## 8. 红线继承 + 不确定性登记

**红线**(全 plan 一致,一条不放松):
1. M0:掌握只由客观复测升;复测难度匹配掌握层级;看动画绝不算掌握、绝不进红黄绿。
2. 单一权威:证据只走 `append_memory_event`;排序只有 `prioritize_training_intents`;调度只有 `revalidation_queue`;mastery 算子只有 `mastery_estimator`;组合规则只存在一份(§3);**禁第 4 个 payload builder、禁第二状态表、禁前端推断**。
3. 禁 AI 越权:不 AI 调度/判频/补错因分辨率(E02/E07 两桶如实)/运行时生成变体/选卡。
4. 禁"看视频打卡"当学习指标;完成率必须与档位分布+变体通过率同看。
5. 扩量 gated:10→40 站按 D1/D7 数据逐级放;签发闸 fail-closed 不松(candidate 永不投默认入口)。

**不确定性登记**:

| # | 不确定 | 验证/替代 |
|---|---|---|
| U1 | §3 组合层是否隐性第二处方(本稿最大新设计判断) | **交 Codex 异源对抗重点攻**;若被击穿,退路=learn 只作为路线图的固有语义(不进"下一步"卡),牺牲跨模式统一入口 |
| U2 | lesson_viewed dedupe 语义(同日去重是否够;重看是否该有意义) | spike 埋点看重看率;如需累计,改 dedupe_key 粒度,账本 append-only 不受影响 |
| U3 | 10 站毕业后空窗(上新节奏 ≥ 消耗速度?) | W2 起看"毕业用户占比"与上新排期对照;不足则复习引擎+变体加密顶上;诚实不对外承诺"永远有新站" |
| U4 | 学-evidence 的"已学·待验证"态会不会诱导"看完就觉得学完了" | 讲懂卡尾部强制"去闯关"CTA(卡内已有);蓝环文案永远带"待验证"三字;A/B 看看完→闯关转化 |
| U5 | 组合层 4) 冷启动 fallback 的理由文案说服力 | U1 静态样张给 3-5 真实考生看 day-0(北极星 U1 同款);群体理由诚实版兜底 |

## 9. 与既有计划的关系(不 fork)

本稿=「主动学」融合的**契约层**:生命周期状态机(§1)、三类证据(§2)、组合规则+`home_next_step_projection` 登记(§3)、内容节奏(§5)、硬债(§6)、rollout(§7)归本稿;排序契约归 v3.2 §5.1;IA/tab 归五模块 brief;North Star 归 PRD v1.3;飞轮接线与被懂时刻归北极星 v1.1;深 pack 结构归数据标准 v1.0;签发真值归 `_pack_manifest.json`。挂 `docs/plan/INDEX.md`。**v1.1 = 已折入 Codex 异源对抗(§0.6):§2.1 按 contract 修正、§3 显式注册、S05 漂移登记、产能措辞诚实化、债量级校正。开工序:阶段 0 硬债(§6)与 §2.1 两处小改先行,spike 随 10 站签发推进。**
