# 五模块改造 · Implementation Notes（活账本）

> 维护规则（owner 2026-07-05 指令）：执行中撞上 edge case 偏离计划时，**选保守方案，在 Deviations 记一笔，接着干**——复盘全靠它。
> 由主控会话集中维护；实施 agent 在隔离 worktree 工作，其报告中的偏离由主控收录。按日期倒序追加，不删旧条目。
> 关联计划：`2026-07-04-luban-ai-adjudication-pipeline-plan.md`（裁决流水线）、五模块 IA Brief、双轮 v3.2、融合计划 v1.1。

## Deviations

### 2026-07-12（五模块学员真相 root-cause closure）
- **[主病]** 同一 learner×pack 被 learning-report 近 8 天窗口、`review_due` fresh 重置、前端固定三态和本机 due/cache 分别解释，真实页面因此可能同时出现学习 0/40、已学完、复习 0 到期、错因待还和学情无盲点。裁决不是新建 LearnerSnapshot 表，而是恢复既有分层：ledger=`learner_memory_events`；生命周期=`pack_lifecycle_projection`；间隔=`revalidation_queue`；跨模块 envelope=`learning_report_read_model.v2`。
- **[已完成的 P0]** lifecycle 改读分页全历史 learning evidence，最近 8 天只留给趋势；canonical terminal 派生本轮 review status/success streak/cycle anchor，item/孤立 station 不推进；成功按既有 `DECAY_PROFILES` 走 3/7/14，失败重置，probe identity 纳入 cycle anchor。一次 pack 全对仍只表示本轮通过，绝不粗升整站 mastered/清 sibling 错因。
- **[三模块同账]** learning report 输出 `pack_review`，学习/复习/学情消费同一切片；复习页删除独立 `/review-due` learner-state 请求。兼容 endpoint 保留，但仅调用同一 lifecycle/queue 内核。首页固定三态、假个性化、同一掌握数冒充置信度/趋势、F16 雏形入口全部删除。
- **[信任与隐私]** report cache key/envelope 按 canonical user 双校验，logout purge；无 user 禁 hydrate。站点自测不再直达完成交接，签发轻练只有拿到 `terminal_event_id` 才在原页显示 canonical 收据，随后直接返回，不再用可伪造 query 把 terminal truth 交给 handoff 二次投影；删除本机 `luban_retest_due_*`，微信订阅只报告授权状态，不承诺发送；诊断 CTA 改为诚实的路线跳转，Profile 提醒文案明确还需微信授权。
- **[仍是 release blocker]** first-run 四题仍缺双教研签发，409 保持 fail-closed；生产 rollout flags、真实订阅模板/服务端发送注册、跨天跨设备真实 cohort、完整 FSRS 参数化均未被本地代码冒充已完成。原 dirty 五模块 worktree 的 concept-card/retest WIP 不在本提交边界，后续只能显式移植，禁止扫入。

### 2026-07-11（首次体验 × 五模块原生旅程）
- **[基线纠偏：第一次确实落在了错误视觉版本]** 名义 `origin/main@b3e9ab09` 比当前五模块产品视觉线少 15 个提交，缺少 `79fddae6` 带来的安全区 TabBar、正确线性图标与中间朱印尺寸/阴影，因此首轮虽然功能正确，视觉壳仍是旧版。已停止在旧 worktree 继续开发，把首次体验的窄 diff 重新移植到 `origin/luban/seethrough-visuals-on-main@22c2a218` 的新隔离 worktree，并手工合并 `learn.js` 以保留看穿 5 关逻辑；`custom-tab-bar` 三文件相对该正确基线保持零 diff。该视觉线与 `origin/main` 仍有 `15 ahead / 2 behind` 分叉，后续进 main 必须先显式整合，不能把旧 `origin/main` 快照冒充产品当前版本。
- **[登录态闭环已完成，本轮不部署]** 使用隔离 `qa_eval` 机器身份和独立本地 user/auth 数据目录启动 authority，DevTools 在正确 `yousenwebview` 项目根中完成登录；课程、首页仪表盘、learning report 三条请求均为 200，学习、复习、问鲁班、学情、我的五模块均能以同一身份进入。owner 已授权 commit、review、push、PR merge main；部署仍不在本轮范围。
- **[404 不是路由漂移]** 首次进入复习页时错题本读接口返回 404，根因是本地 QA 未开启既有 `DEEPTUTOR_MISTAKE_BOOK_ENABLED`；按现有运行配置打开 read flag 和 local fallback 后页面正常。没有为 QA 假象改产品路由或增加 fallback。
- **[第二 onboarding authority 已收口]** 问鲁班仍会对“无 legacy assessment profile”的用户弹出旧 8 分钟摸底框；首次体验虽已写入 Learner State，但旧弹窗只读 legacy assessment/local storage，形成跨设备第二权威。修法不是再写一个本地标记，而是由 `/assessment/profile` 兼容投影 canonical `learner_state.learning_preferences.first_run`，chat 只读该完成事实抑制旧弹窗；服务端首次完成仍只有 `FirstRunWritebackService` 一个 writer。
- **[内容签发包已就绪但无人代签]** 新增四题双教研 review packet，钉死 script/content hash、逐字来源和 reviewer 字段。预审暴露两项需真人拍板的裁切风险：填充墙题只测 14d、未写“中间向两边斜砌”；装配式垃圾题只问 300t→200t、未写“不包括工程渣土/泥浆”。当前 completion 真请求仍返回 `409 first_run_content_not_signed`，这是正确 stop condition。
- **[第二权威已收口] 老蓝首跑的本地 DONE/前端报告处方不能继续承担正式学习事实**：DONE 降级为 user-scoped UI cache；前端只提交 `completion_id + script_version + answers + declared_preferences + completed_at`，服务端 `FirstRunWritebackService` 重新判定并一次性幂等写入既有 Learner State。下一步仍只认 `home_next_step_projection`，未新增 learner table 或 recommendation authority。
- **[内容门比 UI 更关键] 四题视觉和原版展开内容可以完成，但未签发题目不能进入 canonical learner truth**：manifest 默认 `blocked_pending_human_verdict`，服务端 unsigned fail closed。尤其第 4 题不在首批金标候选内，agent 不代签教研 verdict；当前真实状态只能是 `implemented_but_release_blocked`。
- **[原版内容与五模块壳分层] 核心三问、资料揭示、四题、逐项拆解、采分点/来源/量尺、口诀、四次侧写、画像和完整报告保留；导航、安全区、卡片、色彩、入口和退出语义改用学习首页 paper-ink 原生体系。答题态隐藏五 Tab，一次只挂载当前题/当前反馈，下一题通过状态替换而非纵向堆叠。
- **[真微信证据闭环分层] 新版 DevTools 自动化协议与最新公开 `miniprogram-automator` 不兼容（缺 `SDKVersion`，继而出现未知 `getGlobalWebviewIds`），改用 computer-use 在正确项目根 `yousenwebview` 实际走通 `packageDeeptutor/pages/first-run/first-run`：摸底三问→资料揭示→4 题/4 反馈→4 次侧写→画像→完整报告→返回 `packageDeeptutor/pages/learn/learn`，页面级 `real_wechat_package PASS`。首次验证时因无 QA token，学习页三个 API 均 401；该 partial 已由本节前述隔离 `qa_eval` 本地 auth-chain 复测关闭。
- **[真机发现并修复] 第 4 题 B 选项解析含 `<b>现浇</b>`，该字段由普通 `<view>` 渲染，标签会原样露出**。保守修法只去掉 markup、不改内容语义，并给 Node contract 增加“plain-text explanation 不得含 HTML 标签”断言；未把整个 explanation 渲染器改成 rich-text。

### 2026-07-05（复习闭环诚实薄上线里程碑 · 上线 main 4daaaf6d1 · 即时入账）
- **[签发闸补建·真根因] 考点卡签发路径从没接通**：`docs/原始数据/考点原料/promote_variant_bank.py` 是 variant 专用（`_BANK_TEMPLATE=_{pack_id}_variant_bank.v0.json`）。34 卡卡在 candidate 的真根因不是"没签"而是"没法签"。治本=把该工具泛化 `--kind {variant,concept_cards}`（variant 行为零回归）+补测试；concept 分支模板 `_{pack_id}_concept_card_bank.v0.json` + gate 重跑 `build_luban_concept_card_bank.py {pid} --check`；四关校验（status==candidate / sha 三方一致 / bank gate 干净 / builder --check exit 0）对两 kind 同构。concept builder 早把 status 标为"promote 人闸独占的翻牌字段"=设计本就该有此闸只是没建。5 包（A01/F16/J01/N01/S05=34 卡）签发后容器内活体 total 0→34。
- **[owner 拍板 A=诚实薄上线]** 能用的先让学员用上；R8 解药 / R6 精确挖空 content bank 未产→页面诚实占位"整理中"（接口位形状已钉死，bank 一喂零改动点亮），不等齐再上。真机验后再暴露下批内容优先级。
- **[部署路径守门有效非故障] redeploy_fast 拒 web/public 资产**：教学卡 png 触发"需镜像/前端/依赖重建，请改用 deploy_aliyun.sh"→改全量。`docs/原始数据/考点原料/成品/` 的 JSON 被 `.dockerignore:153-157` 反选 + `Dockerfile:222 COPY` **烘焙进镜像**（docs/ 不挂载卷）→改了这些数据**必须 rebuild**，sync 不够（sync 了容器仍旧数据=假绿）。部署后在容器内实测 grep status / 亲跑 build_concept_card_library 确认真进容器，不信脚本自证。
- **[真机验收 caveat] dueCount=0**：QA 账号今天无到期回炉→"到期行→点闯关入口"UI 路径无数据可走；但 gauntlet 页直达渲染出 S05 真变体（带教材+真题锚）已坐实=账号数据面非功能缺陷。
- **[R5 框架纠错·独立 agent 推翻主控初判]** 主控一度判"R5 是收入闸让'每分都有教材出处'变真"——错。判分两通道：R5（5705 点，仅 205=3.6% m35_artifact 官方带分值）喂**通道②支撑上下文**，架构上进不了**通道①官方分值通道**（`assert_supporting_only`+`resolve_grading_point_authority` 强制 `official_score_allowed:False`）。真收入闸=通道①（`v_case_rubric_scored`）覆盖扩容；`installed_runtime_supply` 是无 runtime 读的死 flag、`grading=True` 生产路径没接线；两通道都卡 **governed gold**（现唯一"gold"是合成 fixture+AI 面板 `fleiss_kappa=-0.05`）。那件事=攒 J01 ~100-180 条人工逐采分点金标。
- **[局外人审计纠正主控 ×2]** 会话"改造审计架构与落地计划"局外人审视推翻两处过度声称：①深 pack 大 MD 今天 0 runtime 消费者且 `.dockerignore:20` 不进生产镜像（"MD 撑爆 context"对生产不成立）；②真 context 肥仔=TutorBot 长会话 bot 历史（65536 token 才压缩）+ case_grading 48KB skill 栈，非任何 MD。四步合闸中前三步（变体签发门 read_model.py:74 已合 / 卡门 card_hosted 已接 / wave1）基本收口，唯 R5 那步是通道②升级非收入闸。

### 2026-07-05（复习二期·两屏实现，即时入账）
- **[供给真相 ×3] mistake-book 记账行无 pack_id/error_code/分值字段**：pack 归属只能诚实匹配 lessons read model（对不上=无换皮 CTA）；"到期×分值排序"降级为按到期先后；"你当时的作答"对照 chips 无列表级供给→深链 attempt-detail 替代不伪造。前端原本也无 ERROR_CODE_REGISTRY 镜像（新建呈现层镜像，注明权威=error_codes.py）。
- **[禁假声明] 漏点"已记进错因银行"文案不落**：前端无记账签发权（attempt_ref 服务端签名），改暖提示，测试钉死禁该句——宁少一句爽文案不造一个假承诺。
- **[历史方案，2026-07-12 已废止]**：早期曾让换皮复测全对触发本机销账；现已证实整包结果不能摊销单题且会跨设备漂移，客户端本地销账与对应 storage 已全部删除，只呈现服务端错题状态。
- **[半写降级]** R6 挖空 bank 无供给→自由默写 textarea 如实降级（页面明标"精确挖空准备中"）；R8 解药卡同型降级"解药整理中"。两个供给接口形状已在 vm 头注钉死（R8 键={pack_id,error_code}；R6 键={pack_id}），内容管线喂 bank 即点亮零页面改动。
- **[闯关入口 fail-closed]** gauntletAvailable=retest_available 单一判定点：无变体池的站无闯关入口；"继续下一关"因无队列供给降级"回到复习"。
- **[N+1 防线]** 换皮 CTA 的池探测只在详情页单次执行，禁列表级逐行探测。


### 2026-07-05（复习二期·考点卡管线，即时入账）
- **[派生层裁决] 考点卡吃 §1 跨章知识点全景表而非 R5/R2**：§1 一行=一个原子再认颗粒（自带人审短名+关键数值列+kc 锚），R5 是答案态语句归实务闯关、R2 每包仅一段归判别逻辑——依据=形态匹配+机械解析可靠性（A01 的 R5 行级解析实测 0 行）+quote 命中率（S05 11/11）。
- **[LLM 禁造句的落地形态] 卡正面问法=固定模板包裹 §1 短名**（非每卡独立问句）；「记住了/再看一眼」选纯本地牌序（不走 learner_signal，少一个写路径）——两处都是保守侧。
- **[F16 仅 2 张卡=资产真相非 bug]**：单一深工序型母题，§1 仅 3 个 🟢 行且工序行只有真题锚。fail-closed 拒绝放松 🟢-only 门收 🔵 相邻行；**owner 可裁**：想要更厚的卡池=一行常量放宽（收 🔵），代价是"教材原文并排"承诺稀释。
- **[登记欠账发现] 变体池 bank 自身从未登记 schema_registry**（dash 命名挡在 closure 外）——考点卡池本次已按 content_asset_contracts 登记并把欠账记此，变体池补登记待办。
- **[上游缺口留痕] A01 四个高价值考点（100%/80% 合格标准等）因源料锚 🟡 不成卡**——pack 层既知 jury 缺口，卡池升级等 pack 升锚，不在管线内造。


### 2026-07-05（部署与卡体验轮·补账）
- **[假成功实锤] F16 卡"整包托管含 audio 3MB"的 commit 实际零 mp3 进仓**：`.gitignore:317` 全局 `*.mp3` 静默挡掉 11 段配音，线上 404→webSpeak 兜底在微信 web-view 又静默失败=全程无声。修=窄豁免 `!web/public/luban-preview/**/*.mp3`+管线无条件拷 audio。教训：声称"含 X"的 commit 要核 X 真在 git 里。
- **[部署探针立功] card_url 机械派生 → 22 绿灯站 web-view 404**：CARD_BASE 一通电全站发链接而托管卡仅 6 站。治本=manifest 确定性扫描 `card_hosted` 标+read_model 门（非白名单硬编码）。教训：环境变量通电前先推演"字段对全集生效"的后果。
- **[风格审计] 托管 6 卡仅 F16 是视频2类**，a01/c02/j01/n01/s05 全是旧 IR 预览模板（含 c02/n01 首帧画布残缺、3 张文案重复 bug）→ 按 owner 拍板封存下线（改名 .v1-deprecated 可回滚），诚实的空好过错误的满。
- **[owner 口径二连澄清] 卡全屏行为**：①"进入即全屏"理解过度→纯删一行改为仅按钮触发；②普通态需等比填满宽度+任何时候不见纯黑（实现用 zoom 而非 transform——zoom 参与布局故热区/滚动天然正确，cap 2.0 保 iPad 竖屏满铺；底色逐卡运行时提取 #181b1e fail-closed）。三口径已固化进卡规范。
- **[QA 凭据失效] .env 共享 QA 账号密码被服务端 401**→注册轮换 qa_owner_view_0705。**[重要教训] owner 口述"我要求 X"时先 grep X 是否已实现**：免费额度三规则（日3/周12/连续3日）owner 4 天前已 ship（mobile.py:125-127），误派实现 agent 被 owner 叫停（零污染）。
- **[学习页慢真根因] dashboard 端点 async def 直调同步重服务**：单请求 3.2-4.6s 且占死事件循环（并发时邻请求 0.13s→7.2s 55x 饿死）→ 线程池化+防回退测试；前端首屏快通道 4.3s→0.3s+骨架屏。**[前端造假数据] learn.wxml 掌握环 `||72` 兜底**在无数据时显示假 72%（违"前端不算分"）→ 删除缺数即隐藏。
- **[learned_count=authority drift 又一例] "学-evidence 没落账"是假警报**：写链路 E2E 健康，真凶=review_due 自建第二套"已学"判定只数 station_completed→收权唯一 classifier。复习页把"绿灯"渲染成"已点亮"同型→收权 isLitLifecycleState 唯一判定+回归钉死禁第二套。

### 2026-07-05（五模块五 tab 战役·补账）
- **[T3 问鲁班] 教学卡问追AI 承接刻意用 promptIntent 而非 followupQuestionContext**：后端 `_has_active_question_flow` 会把后者当活跃题目流路由，教学卡非题目流，误挂会误触 question-followup 语义。
- **[T4 学情] 比对账表更深的真根因**：`_buildRadarViewModel` 把 score=0（未学）误归 weak→未学站渲染成"薄弱"红灯墙；按后端四态阈值对齐修正。蓝环第五态首次进前端。
- **[T5 我的] 三个如实降级**：免费额度读接口不存在（后端计数齐全无 read 端点，静态说明降级，加只读端点即可点亮）；"免费 3 站"设计概念后端无对应物（按 lit/40 真实投影）；wx_miniprogram 是 shadow 树非生产面（任务描述纠偏）。
- **[壳切换] 任务假设纠偏**：review 页原本无内联 tabbar（仅 learn 有）；history flag 分支 dead-but-harmless 保留（仍守页面访问门）；壳总高 140rpx 刻意不动（chat.js workspaceShellHeight 布局算式依赖）；三 flag 全关时五 tab 壳整体隐藏=沿用既有 kill-switch。
- **[设计稿反哺] 两张补稿（错因银行详情/实务闯关）顺手纠 10c 原稿两处违规**：Long Cang 用在非品牌字、"看穿它=真懂"文案；10/11px 字号抬至 12px 铁律。
- **[工具坑] DevTools 全新路径项目 headless 不初始化**（project2_ 注册缺失，须用 IDE 打开过的路径）；automator 0.12.1 对 IDE 2.01.2510290 需 checkVersion 空补丁；**API 断线三次全部靠"逐步 commit+SendMessage 恢复"零损失续跑**（断点保护=commit 粒度的又一实证）。
- **[部署脚本三次正确拦截]**：detached HEAD 拒发布、脏树拒发布（两次：DevTools 编译模式改动/.codegraph pid）、fast 路径拒 web 资产变更——守门有效，代价是发布 worktree 必须专用且树干净；发布 worktree 曾被并行清理，已固定 /Users/yehongchen/worktrees/deeptutor-release。


### 2026-07-05（D4 重尾批收官）
- **[模式反转] 重尾批 92% 条目需真实裁决**（前两批约半数只缺凭据）——"重尾"的重是真的；预算内消化（123 处编辑）。
- **[整包体检首触发] S01 Tier-2 需求 10>8 触发 §5.5**：GLM 全包诊断=repair（同型机械截断病）而非系统性烂，按诊断批修复而非逐条——触发器语义按设计工作。
- **[计划预判未发生] S06"坠落半径 5m/6m 教材查不到需升 owner"**：教材 P124 逐字全命中，全批 30+ 数值族检索命中率 100%——8 包共同病灶实为编译 quote ~90 字均匀截断（切片管道问题，非教材缺口），是未来重编译轮的确定性修复对象。
- **[超 jury 深度的实质错误 ×3] 裁决中发现 jury 没抓到的事实错**：S02 两处"150mm 落 200~500mm 区间"算术假陈述、S02/S01"300kN/200m"误归吊装总重（实属安拆条款）、C04 不实"🟢已验证"声明——面板真实增值的证据。
- **[红旗纪律 vs 效率] K01#0/Q02#7 两案 GLM 判"教材+真题双锚证据已足可升🟢"**，按"升色=0"红旗纪律保🔵+可升级说明，升级权留 owner——纪律优先于单案最优。

### 2026-07-05（局外人审计轮）
- **[主控过度声称自纠 ×2]** ①"答疑吃 Nexus/KnowQL 颗粒"不实：TutorBot loop 无该工具，KnowQL 仅在判分 shadow；答疑对深 pack 内容供给=0。②"教学吃卡"生产上假：`LUBAN_LESSON_CARD_BASE` 全 repo 无处设置→20 绿灯站 card_url 全空降级，托管卡仅 6 站。教训：架构应然≠生产实然，回答 owner 架构问题必须以生产终态为准。
- **[skills 提案裁决=不做]** owner"pack 做成 skills"提案经局外人核实：13 天前已被 L0 路由卡设计文档显式评估并回撤（skill=行为装载器非知识库；整包进 context 比编译投影贵 20-30 倍；语义自选=人为引入不确定性）。正解=给已裁决管道合闸，非新形态。
- **[系统性病：供给跑赢消费 21:1]** 三道 dormant 电闸：①变体池无签发门（candidate 直通生产消费端，status 零过滤+sha 不比对）②卡供给 env 缺失+14 站无卡 ③pack 锚定真题 ~80% 判分仍 open-world 现编（live 编译库源头=真题参考答案管道非 pack R5，R5 promotion 未执行）。已启动修复①（luban/variant-signoff-gate 分支：runtime 双 fail-closed+promotion 薄工具，作 wave1 合并前置）。
- **[已合闸①] 变体签发门落地**（分支 luban/variant-signoff-gate）：runtime 唯一入口 `_load_signed_bank`（status==signed ∧ source_pack_sha256==manifest content_sha256 双 fail-closed）+ `promote_variant_bank.py` 人闸工具（四关校验含 gate 重跑）。**发现**：F16/S05 也是 candidate（"signed 先例"不存在），故 wave1 合 main 前必须先做首批 promote，否则全站复测空窗。29 tests（主控复核 13 luban_lesson 绿）。
- **[新雷登记] 裁决 resolution 无 sha pin**：用章节号+散文锚定，pack 正文修订后 jury_clean 不自动失效；recheck 只在签发瞬间跑。收口方向待定（resolution 加 content sha / CI 定期 recheck），先记账。
- **[次雷] 复测 expected_ok+correct_statement 下发客户端本地判分**：现仅进 telemetry 半径小，但接学情前必须收口（防刷分面）。**[次雷] 上级目录 13 个旧 jury 副本**且 manifest/recheck 有回落查找逻辑——旧副本可能静默顶替真值，清理待办。
- **[变体池] R01/F05 两站如实跳过不建池**（计划=18 绿灯站全补）。根因=两 pack 的 R4 封闭性自检**自己**把机械扣分判断收归 R7 🔴（jury 裁决后的新文体），变体池所需的 expected_ok 二值判定恰是被降级的那层——建池=冒充 pack 已拒绝的机械红线。X02 同型病但有两处真题明锚，抢救出 20 变体限缩池。**续产预筛惯例**：先 grep pack 的"收归 R7"自检声明，零成本判断可否建池。（分支 luban/variant-pool-production-wave1，887 变体 16 站 gate 100%）
- **[签发人审提示] E05 整池零真题锚**（pack 真题侧空窗，全挂教材锚）——16 站中唯一，教研签发时优先人审。
- **[摘取排雷] #351 的 api.js diff 会整函数替换掉 main 的 `postLessonProgress`（lesson_viewed 唯一 writer）**——盲 cherry-pick 会静默 regress PR#353 融合基座。"先逐文件 diff 再摘"纪律救下的最大一颗雷。同批对账结论：cfa515e0d 摘增量、4e956ccb5 整页重铺（main 无其假设的占位页/5-tab壳/--lb-token）、749964b52 仅按 §6.1 重写 exam_date 消费其余弃。（分支 luban/review-module-wiring）
- **[产品语义如实保留] revalidation_queue 日容量=1（ARRS max_active=1）**：复习到期清单每日最多 1 站，为既有引擎语义（v3.2 §6.1 每日上限）非 bug；页面文案不承诺多站。**产品问题待 owner**：复习 tab 的"今日到期 5 个"设计稿预期 vs 引擎日容量 1 的张力，通电前需拍板。
- **[agent 终态纪律] 变体池 agent 首次收尾把"等子 agent 报告"当终态交付**——自证陷阱变体（用过程状态替代磁盘终态）。纠正：责令以磁盘+亲跑 gate 实测收尾。派单惯例追加：最终回复必须基于终态实测，不接受"等待中"作为完成态。
- **[签发范围] C06/S07 从 Batch A 批量签发中撤回**。计划表把两包排进信心批，但签发时撞 `explicitly_barred_default_entry`（coarse_review 粗粒包，需先 leaf review 的既有设计门）。保守处置：不绕闸、撤回 override、只签 13/15；C06/F04/Q03/S07 四粗粒包 leaf review 列为独立待办等 owner 拍板。（PR#365）
- **[红旗口径] D3 批 agent 自报 Q03 🟢 delta=−3，主控独立复测=0**。方向一致（均为"未升色"），判定不构成红旗违规；差异原因未深究（疑为计数口径含作答层/括注文本）。保守处置：以主控复测数为准记录，红旗判定标准保持"delta>0 才违规"。
- **[流程韧性] D3 中量批 agent 中途 API 断线**。靠"每包 recheck exit 0 才 commit"的粒度无损续接（仅 A02 半成品重收口）。经验固化：批处理任务的 commit 粒度=断点保护，不是仪式。
- **[裁决方向反转-保守側] G02"虚铺依据"条：jury fix 要求降🔵，但教材 P85 逐字实存该句** → 按事实权威阶梯（教材>面板>jury），保🟢补出处而非机械执行降级。同型先例 C01#0（教材 P103）。"保守"在本项目=服从教材原文，不是服从 jury。
- **[跨包红线新增] 同一 chunk_id 跨 pack 的 quote 切片不同**（0123 在 D12=防治要点、在 Q03=仅原因）→ 禁止跨包借 quote，各包只认自己 compiled_source 的切片。

### 2026-07-04
- **[Tier-0 预期落空] 设计估 Tier-0 可直接证伪 ~10% jury 断言，实测 0/164**——J01 型 jury 幻觉已被 batch1 人工消化。策略调整：Tier-0 从"批量结案器"降级为"改前证伪闸"，Tier-1/2 实际占比上调；排期仍守住（信心批+中量批各提前约两天完成）。
- **[实施发现] ~17/24（D2 批）与 ~22/40（D3 批）条目属"前轮已实质修复、只缺 resolution 凭据"**。流程相应前置一步"先核正文现状再决定补凭据 vs 真编辑"，避免重复编辑。
- **[schema 登记位错] fusion stage0 把两个新 schema 登记进 `content_asset_contracts` 区块，但闭包只认 schemas/tier2/tier3** → 迁入 `tier2_canonical_contracts` 并补 canonical_fields pin（闭包 210→212）。教训：登记前先看闭包脚本认哪个区块，不是 yaml 里有名字就算登记。
- **[冲突裁决] F16 摘取的 docker 通配 COPY commit 与 main 上 #353 的逐文件 COPY 冲突** → 采纳整目录通配（新站补池零 Dockerfile 改动=治本），保留 #353 的 join 映射反选与 degraded 注释，deploy 测试合并双方断言。
- **[计数 pin 有意识 bump] D14 入仓使 evidence 文件 37→38、manifest 全集 40→41**，两个钉死计数的测试按设计意图（逼有意识确认）bump 并注明原因。
- **[生成物治理] F16 托管卡（web/public/luban-preview/f16/）撞 secret-scan 基线与 eslint** → 治本选前缀排除 `web/public/luban-preview/`（40 包量产会持续新增卡，逐个 baseline 会无限 churn）+ eslint ignore（vendored 运行时非应用源码），而非逐文件 baseline。
- **[F04 修复幸运面] 损坏 sidecar 的双 JSON 文档逐条比对全等** → 机械归一无需并集裁决，修复零语义风险（原方案备了并集+人工比对路径）。
- **[声称漂移修正] round11 Brief 把 PR#353（draft/flag 关/未部署）字段写成"已上线 read-model 背书"** → 入仓前改为显式状态口径。教训归档：'已上线/已就绪'表述必须核部署终态。
- **[风格拍板] owner 定版动画卡只用"视频2类"**（纸墨朱竹深母题动画学习卡，P40 世代），视频1类深蓝旧风格弃用；存量卡上线前须风格审计。
- **[并行工作区纪律] fusion worktree 领先 origin 15 个未推送 commit 且有脏文件** → 不碰其工作区，基于其 HEAD 另开 worktree 推进，脏改动原样留给其主人。

### 2026-07-07
- **[前提冲突-owner 裁决 A] #9「学习头牌 2 分钟 MCQ 轻练」任务稿字面实现踩 3 红线**：任务稿要新建 `build_light_practice` + 新 flag `LUBAN_LIGHT_PRACTICE_ENABLED` + 新 `source_feature="luban_light_practice"` + 把 `scoring_point/exam_refs/章节` 塞进题卡。独立核验（grep 全仓 + 读设计 v3 + 读 retest 页）发现：① 变体池每题只有 6 个签发字段（variant_id/rule_group/surface/expected_ok/correct_statement/anchor），采分点文本/真题/章节**都不是签发供给**=塞进去就是造供给（踩投影不生成/红线6）；② 该 flag 与 source_feature 全仓不存在，签发通道是 `learner_signal`（非 promoting，已被证据编译器排除），交接闸是 `LUBAN_REVIEW_MODULE_ENABLED`（新造=第二权威+绕 register-before-use）；③ 判断题二选一本地判分机制**已在 main2 作为 `build_retest_items` + retest 页存在**（再写 build_light_practice=第二 builder）；④ 设计 v3 §5.2 的档位①其实是「关键词填空」，红队已移除纯点选/再认题，判断题 MCQ 是复习轮机制。**owner 拍板走 A**：给既有 `build_retest_items` 加 `mode="forward"` 参数（广度优先覆盖不同 rule_group，仅选序不同、同池同 builder），前端 learn.js todayTask 带 `task_type=light_practice`+`pack_id` → 复用 retest 页 `?mode=forward`，reveal 只给 correct_statement。红线证据：0 造供给（题卡仍只 6 签发字段，grep required_terms/keywords/scoring_point/exam_refs=0）、0 新 flag、0 新 source_feature（contract evidence-source-guard 仍 =construction_grading,conversation_synthesis）、0 第二 builder。改点：`read_model.py`（+`_forward_rule_group_spread`、`build_retest_items(mode)`）、`luban_lesson.py`（retest-items 端点 +`mode` query 归一）、`api.js`（getLubanRetestItems +mode，兼容 errorbank 第 3 位 opts）、`retest.js/.wxml`（mode 文案数据化，forward 暖调）、`learn-view-model.js`（todayTask +task_type/pack_id/mode）、`learn.js`（goPractice 按 task_type 分流）。测试：luban_lesson 50 passed（含 forward 覆盖/幂等/仅核心/仅 6 字段/fail-closed）、node learn-view-model 13 + api-mode 7 + errorbank/gauntlet 消费者兼容 PASS。教训固化：**任务稿字面指令与已签发红线冲突时，先独立核验前提再上报 owner，禁静默照做造供给**（success indicator #3：澄清前移到编码前）。
- **[定级纠错-owner 拨正,spike 命门] mode 判别位不是 BI 锦上添花,是 GO 门读不出的命门**。我初报把"forward 轻练与 review 复测完成事件都记 objectType=retest、无 mode 判别"定级为"不阻塞、BI 待办"——**错**。owner 拨正:spike 的 GO 门=D1 留存=人**次日回来做 review 换皮复测**;若 forward(当天刚学完练一遍)和 review(次日复测)在埋点里长一样,数据里根本分不出"次日回访复测",spike 想量的信号直接测不出=上了真机也判不了 GO/NO-GO。**已在 Task A 收尾并入修复**(register-before-use 正规登记,给现有事件加 property,不新造事件名):① `product_behavior_catalog.py` 登记 `PRODUCT_BEHAVIOR_PRACTICE_MODES={forward,review}` + validated dict 加 `practice_mode`(白名单外值 ingest 拒收,防拼写漂移);② `product_behavior_store.py` 加 `practice_mode` 列(auto-migration 零迁移)+ `query_raw_events` SELECT/filter 带上它(否则查询面读不到);③ `retest.js` 两事件(retest_item_answered / learning_action_completed)带 `practiceMode: this.data.mode`;④ `surface-telemetry.js` 固定 metadata 加 `practice_mode` 映射——**这一跳原本会静默丢**(正是"每跳须显式导出"教训的复现,幸而按链路逐跳核到)。测试:observability 281 passed(含 catalog 校验 forward/review+拒非法、store 落列+按 practice_mode 过滤、端到端 p0 flow)。**教训固化:埋点判别位属"spike 能不能判 GO"的命门,不得以"当前无 BI 指标读取"降级为不阻塞;凡 spike GO 门依赖的信号,埋点阶段就必须可分。**
- **[入口收权-研究结论待 owner，Task C]** 真人扫码落地 host 首屏 `pages/freeCourse/freeCourse`，点 AI 卡→登录→**落 `chat`（问鲁班 tab）非双轮**；双轮是五 tab 壳里 tab0/1，需再点一次才见。最小侵入=把入口漏斗落地从 `route.chat()` 翻到 `route.learn()`（load-bearing=`freeCourse.js:566` returnTo，+`onboarding.js:110/206/210`+`login.js:154/163` 兜底），零 host 破坏、无第二 IA、纯字符串可逆。**偏产品决策，未擅改 app 全局入口，留 owner 拍板。**
- **[订阅消息骨架-已建成+补登记，Task D] 骨架早在 main2 建成(brief"全仓 0 实现"是废弃分支口径),真缺口=env 未登记**。先 grep 是否已实现(owner 惯例):服务端 `wechat_subscribe/service.py`(send_subscribe_message + degraded_red_dot 降级 + access_token 复用 member_console provider,零第二 token 权威,7 域测试过)、客户端 `subscribe-message.js`(requestNextDayRetestAuthorization,仅交接时刻,失败一律 red_dot)、`handoff.js` 接线(情绪最高点请求 + subscribe_prompt_result 埋点)**均已存在**。唯一 register-before-use 缺口=`WECHAT_SUBSCRIBE_TMPL_NEXT_DAY_RETEST` 未在 env_registry.yaml/.env.example 登记(service.py 读了未登记 env)——已补(config kind,default "",全量 `env-registry-guard: passed | env_refs=417 all registered`)。**刻意不做(计划 §三 scope 边界,防孤岛)**:次日到期发送 caller / 授权状态表 / 调度 job——随 spike 交接时刻调度一起接线,现在建=无消费者孤岛。**owner-gated(外部不可控)**:小程序后台申请订阅模板(公共库「学习/复习提醒」即选即用无审核;自建模板 1-3 工作日审核)→ 拿 tmplId 填 env + 客户端同值 + 给我模板字段键名拼 data 形状。审核期内闭环不阻断(App 内红点先行,链路建成前合法降级)。
- **[入口收权-已实现,Task C 走 A+两护栏] owner 批准后落地**:登录后落地翻转 `chat→learn` 收在**单一 chokepoint** `login.js:_reLaunchAfterAuth`(登录后唯一 reLaunch 处=spike 新用户 cohort 必经)。决策做成 flags.js 纯函数 `resolvePostAuthLanding(target, learnUrl)`(单一权威+可测)。**护栏1**=`doubleWheelLandingEnabled` 默认 false(严格 `=== true` 防误开):关时原样返回 target,host 落地逐字节不变,仅 spike cohort 由 host 运行时 flag 开。**护栏2**=仅当目标是 `/pages/chat/chat` 才翻 learn(不动其它显式深链=不 strand);问鲁班仍五 tab 一键可达;learn 冷启动有骨架降级;关 flag 即回滚。改点:`flags.js`(+flag +`shouldLandOnDoubleWheel` +`resolvePostAuthLanding` +导出)、`login.js`(require flags + chokepoint 接线)。**未改 app.json 全局入口**。测试:`test_double_wheel_landing.js` 8 passed(默认关原样/开翻 chat/非 chat 深链不动/空目标不误翻/字符串 'true' 不误开)+ flags-sync/app-auth 既有 8+7 无回归。**诚实边界**:只覆盖登录后落地(新用户);已登录 re-entry(onboarding.js:110 直 route.chat)是第二站点,如需返用户也落双轮可后补。真机验证=体验版 flag-on 走一遍。
- **[git 收尾,Task B step1] 本会话工作已 commit 到 spike/main-base-v2(未 push、未动 main)**:`f5d23a36b`(Task A+命门 16 文件)、`89e88cab4`(Task D env 2 文件)、`37b83cfc5`(#8 gauntlet/full_answer 7 文件)。全程显式逐文件 `git add`、绝不 `-A`,`git show --stat` 复核无并行 WIP 夹带。**B step2(摘废弃 release/card-fit 增量)出了 material/defer 对账表待 owner 判**:BASE 已含几乎所有 stale luban 页(0-diff 已入 main),真 material=纸墨/card-fit 视觉(paper-ink/custom-tab-bar/learn wxss、stations.wxml)+新文件 pack-short-names.js+hunk-level 的 learn-view-model/learn.wxml 视觉块;DEFER=api.js/retest.js/learn.js/gauntlet(stale 落后,整摘会回归本会话)+read_model/concept_cards/antidotes/light_practice(计划禁摘);WeChat Pay 是独立 feature 另议。
- **[埋点落库-审计结论，Task E]** 行为埋点管道**是持久化的**（SQLite `product_behavior_events` + register-before-use 双闸：surface_events 名单→400、catalog 维度校验），4/5 GO 信号架构就绪。真缺口：① 生产**零数据**（埋点未随小程序发版，bi_service 自述 pending）；② D1/D7 回访**无锚点事件、无指标**（可由 `occurred_at_ms` per user_id 推导但无人算；`visit_id` 30 分钟 TTL 只能按 user_id 归集）；③ 订阅授权率**结构性=0%**（`subscribe-message.js` 模板 ID 空=永远 red_dot，待 Task D + owner 模板）；④ `handoff_rendered/retest_item_answered/subscribe_prompt_result` 落库但**无 BI 指标读取**；⑤ review/stations/learn/errorbank/concept-cards 5 页零埋点。

### 2026-07-08（阿里云发布 CLOSED + 换轻练修复 + 线上地真相核验）
- **[阿里云发布, PR #412] spike/main-base-v2 → main（rebase），origin/main = 42681ace6，已部署 test2 逐层验证防假绿**：deploy_aliyun.sh 全量重建（fast-redeploy 被 HEAD tip 的 yousenwebview 文件挡下=回落全量）。host .env SHA = 容器 env SHA = 42681ace6（GIT_DIRTY=false）、容器内代码实证 `_forward_rule_group_spread=3`/`practice_mode`/`PRODUCT_BEHAVIOR_PRACTICE_MODES=2`（新码真在运行容器）、公网 //healthz/readyz 独立 curl 200、observability release_id 对上。**顺带修既有 drift**：发布前 host=c5fa4fc0e/容器=bcdc4a5d5 不一致（无主 drift）→现均 42681ace6。首轮 CI 2 项真失败（均 Task C 改 login.js 连带：4 login 测试 sandbox mock reLaunchAfterAuth eager 调 route.learn 而其 route mock 无 learn；1 假 fixture sha 被 detect-secrets 误报）→已修（测试补 flags mock + login.js 用 `shouldLandOnDoubleWheel()` 守卫只在翻转时算 learn URL + pragma allowlist）。测试 Python 81 + node yousen 86/86 + smoke shards 全过。
- **[线上地真相核验-局外人]** 打 test2 核六能力：concept-cards/retest/antidotes/cloze/review-due 全 401（=已 LIVE 鉴权门，真部署非纸面）；半写核心 full_answer **发布前容器 ABSENT → 发布后 FULL_ANSWER_NOW_LIVE**（容器 grep 对照法，控制组 review-due 命中证 exec 可靠）。异常追查：full-answer POST HTTP 200 但 body=`{"detail":"Authentication required",http_401}`=真鉴权门（GET 正确 401，POST 状态码 cosmetic 不一致，功能安全）。**关键版本事实**：发布前 test2 跑的 `bcdc4a5d` 是**不在 origin/main 上的分叉线**（`git branch --contains` 空），此发布把 test2 从 bcdc4a5d 大跳到 42681ace6，合上"验证世界(origin/main)≠真人世界(bcdc4a5d)"的鸿沟。**残余**：bcdc4a5d 独有生产内容理论可能丢（五能力+端点实测全过，风险低，spike 期行为诡异第一嫌疑）。
- **[换轻练修复, commit `4d8d12aaa` on spike/main-base-v2]** 真机审发现 learn 页两按钮（开始2分钟轻练+换轻练）**都绑 goPractice、goSwitchPractice 在任何已提交版本都不存在**（release/card-fit 也没有=那个"区分修复"从没落地）。修：learn.wxml:136 bindtap goPractice→goSwitchPractice；learn.js 补 `goSwitchPractice`→综合练习页 `/pages/practice/practice`，不碰 Task A 的 goPractice→retest-forward。node learn-view-model 13 passed。**教训：真人一点按钮就现形——B-step2（card-fit 增量）不只是视觉润色，扛着换轻练区分修复，是体验版上传前硬前置。**

### 2026-07-10（战略转向 F16 打透 + 看穿 5天 P0 落地 · 当前接续点）
- **[战略转向-owner 拍板]** 之前建的是**广度通用管道**（16 站 retest/full_answer/证据流/5-tab），但 owner 真机审发现轻练是**光判断题 retest 页，不是 F16 打样体验**。第一性原理复盘：第一波内测 **NPS 8-10 但 0 回访**="喜欢但不回来"=**更多功能不是回访的杆**；而 owner 早已用 F16 设计好整套「5天看穿+暖」留存闭环（`artifacts/luban_case_family_assets/F16/F16_5day_storyboard_spec.md`，每天7步：今日一刀→表皮试探[4选1+每干扰项=诊断探针→error_code]→透视揭底[表皮→不变量→出题人意图→你的误解]→定位证据→暖纠正[先捧→点差距→我相信你+安全网]→明日换皮约定→证据入账；Day4 半写真批改锚 Q18；Day5 三处换皮综合复测）。**owner 决策：先 F16 打透当品味标杆（一次做全5天，原生进新版本）→审过再抽模板批量铺有 P40 教学视频的主题→逐步补 60**。spike GO 门（小/一次性 cohort 现实）：基线次日回访=0，GO=cohort ≥2 人 day+1 未经催促回来做换皮复测，NO-GO=0（阈值预登记待 owner 签，eval-design 铁律）。cohort+nudge 前提清单已议（招 5-8 有考试痛+可触达者、nudge 优先订阅 push 兜底人工 ping、qual 问为什么、深度一考点）。
- **[P0 三裁决-owner 拍板，证据在手非臆断]** ① **看穿 MCQ 走忠实 4选1 签发形状，不复用 retest 判断题**：二选一 6 字段装不下"每干扰项=诊断探针→misconception→error_code"（grep options/distractor_to_misconception=0），而这正是魂；schema v2（`2026-06-16-luban-deep-archetype-asset-schema-v2.md` L4）已定义 4选1 诊断形状=实现已定义 schema 非新造。② **5天推进走独立薄 program-progress，不用 revalidation_queue**：核实它是"次日同题复测"原语、无"第几天"序列态、fresh→进阶需 promoting 而 station_completed 非 promoting→复测永不推进 program 态；薄容器只投影 program 进度不算掌握（掌握仍复测读回、前端不自算）=不违反单一权威。③ **Day4 本轮诚实走投影核对不碰治理**：`Q18-1A434000::qga_v0` 现状=blocked（score_sum_mismatch，10/11 点自证卡总分和门）**非 published**，full_answer_grading 够不到（v_case_rubric count=0→open_skill/L0）；本轮 Day4=半写→自我核对对照已签发 P10/P11 采分点文本（确定性命中/漏点，honesty_label="training_org 估分·非官方·待真判"），不走内核实判=治理 follow-on。
- **[P0① 完成-签发内容包+投影层]** 端到端签发闭环：`_F16_seethrough_source.json`（5天内容逐字转 spec，authored_from 标注=投影不生成）→ `scripts/build_luban_seethrough_bank.py`（确定性 builder+gate：错因∈E系/溯源/无审视硬词/结构自检，--check 供 promote 复算）→ `promote_variant_bank.py`（+seethrough kind，人闸）→ `_F16_seethrough_bank.v0.json`（SIGNED，sha 三方一致）→ `seethrough.py`（read-model，仿 concept_cards.py 复用 `_load_signed_bank` 双闸 signed+sha，fail-closed）→ 端点。**owner「诚实延伸」裁决落地（gate 对抗验证）**：Day3 节点（1A434000_075_0117/077_0120）核实确属 F16 章节→扩编 F16 compiled_source 收进（真教材 quote，is_extension=false，名正言顺拥有）；Day2/5 迎水面（1A413030_134_0258）是真延伸→is_extension=true+true_source_pack=F03+source_ref，学员端"从屋面延伸到地下室·同一控水原则"。**裸借守卫对抗验证：把 F03 chunk 谎标 F16 自有→gate fail(anchor_unresolved)=非橡皮图章**。`schema_registry.yaml:118` 注册 `luban_f16_seethrough_bank.v0`。测试 seethrough 5 passed（含活体）+ luban_lesson 域 55 + contract_guard 全过。
- **[P0②③④⑤⑥ 完成-前端5天原生体验]** `pages/luban/seethrough/`（js/json/wxml/wxss）：② 表皮试探=4选1单选（onOptionTap 本地判 picked===correct_option_id，选错取干扰项 misconception+error_code）+透视揭底屏（step=insight，4段）+暖纠正屏（step=warm，warm_correction 逐字）；is_extension chunk 显延伸标注。③ 薄 program-progress（day/step 状态机，completedDays 存本地 storage=呈现层非掌握真值，顶部天导航可自由跳便于审）。④ Day4 goSelfCheck 对照 P10/P11 required_terms 确定性命中/漏点+honesty_label。⑤ Day5 4选1+进步收据+安全网投影。⑥ 学情咬合薄：每天 telemetry（practiceMode=forward 非 promoting）+Day5 station_completed 走既有单一 sink。入口：learn.js `goSeethrough`+learn.wxml F16 入口卡→`seethrough?pack_id=F16`；api.js:957 getLubanSeethrough/Library。测试 test_seethrough_page.js（4选1判对错/选错取 error_code∈E系/Day4命中）+ luban_lesson 55 + 语法检查。**红线证据（可证伪）**：投影不生成（全来自 read-model，页无硬编题面）、学员端禁审视硬词（grep 看穿/识破/揭穿/露馅=0，抓到并修 errorText 一处）、掌握前端不自算（页测试断言 data 无 mastery）、错因∈E系（断言 /^[EM]/+contract error-code-guard）、Day4 诚实标注、evidence-source-guard 无新增。

**⚠️ 当前接续点（新窗口从这里续）**：
- **F16 P0 全部 17 文件 UNCOMMITTED 在 `deeptutor-main2`（留 owner 审）**。安全网分支 `safety/spike-layer1-8`、`safety/spike-8-and-A`（#8+Task A 存底）；`spike/main-base-v2` 已有 6 commit（f5d23a36b Task A+命门 / 89e88cab4 Task D env / 37b83cfc5 #8 gauntlet / f510d2745 Task C / 1a7017e0d Task E / 4d8d12aaa 换轻练修复）。**origin/main=42681ace6 已含 #8/#9/C/D/E（PR #412 已部署 test2），但 F16 P0 未 commit 未部署**。
- **审 F16 雏形必须本地起后端**：seethrough 只走端点无本地降级，test2（42681ace6）无 seethrough 端点→DevTools 打 test2 会 404 空。`endpoints.js` 本地优先（127.0.0.1:8001/8012 先于 test2）→**本机 8001 起带 `LUBAN_REVIEW_MODULE_ENABLED=true` 的后端，DevTools 自动命中本地，零部署可走 5 天**（末次窗口正做：本地起 8001 + automator 逐天截图存证）。
- **待办**：① owner 亲手走完 5 天审 wow/不假/暖（人闸）→对了则 P4 抽模板批量铺 A01/J01/N01/S05→11 可上→60；② Day4 真判=治理 follow-on（解 Q18 score_sum block+接内核实判）；③ B-step2 material 摘取（card-fit 视觉增量，体验版上传前硬前置，已有对账表）；④ 订阅 tmplId（owner 后台，不阻塞）；⑤ F16 P0 审过后 commit + 上体验版真机。
- **DevTools 复现**：项目根=`deeptutor-main2/yousenwebview`，编译启动页=`packageDeeptutor/pages/learn/learn`（project.private.config.json current 已设"学习页(双轮)"）；看不见改动清 WeappCache（退出→`rm -rf <hash>/{WeappCache,Weappdest,WeappMiniCode}`→重开，保留 WeappLocalData 登录态）；关/开 DevTools 用 `/Applications/wechatwebdevtools.app/Contents/MacOS/cli quit|open --project`（退出不干净=端口占用超时，需 pkill -9 -f wechatwebdevtools + lsof -ti:<port> 杀干净再 open）。

### 2026-07-10（seethrough 视觉+F16 切片重放上 main 基座 · 即时入账）
- **[重放] `luban/seethrough-visuals-on-main`（base=origin/main `918cf4aa`，含 first-run PR#439）**：cherry-pick `4d8d12aa`（换轻练绑定 goSwitchPractice）+ `3200ec19`（F16 seethrough 17 文件切片，即上节 P0 的 commit 化），解决"owner 要的纸墨 UI 与最新 main 功能分居两分支"。唯一冲突=app.json 子包页面双注册（main 加 first-run / 分支加 seethrough）→双保留。
- **[自曝雷撤除] `3200ec19` 夹带 app.js `USE_LOCAL_DEVTOOLS` 默认 true**（作者自注"⚠️ 绝不 commit/发版——demo 后须改回 false"但已随切片 commit 入库）→ 被既有测试闸 `test_app_runtime_base_selection`（develop 候选默认仅 remote）当场抓住，重放分支已改回 false 单独成 commit。**教训：demo 期临时 hack 必须走本地不落库；"绝不 commit"注释挡不住 commit，测试闸挡得住。**
- **验证**：node 小程序测试 95 文件全过（learn-view-model 13 / seethrough-page 12 / app_runtime_base_selection 11）；pytest luban_lesson 域 55 passed；改动 JS 全 node --check；app.json JSON 校验过。
- **消费提醒**：test2 现跑 `42681ace6` 无 seethrough 端点——审看穿体验仍需本地 8001 后端（上节 DevTools 复现法），或待下次阿里云里程碑部署本分支。

### 2026-07-10（轻练/复习精细化一版 · 专家组审计五修复落地 · 即时入账）
- **[承诺宽度收窄] 头牌轻练按供给真值路由**：40 站硬编码 F16 的临时态收口——`list_green_lessons` +`retest_available`（复用 `_load_signed_bank` 单一闸不建第二判定），vm `practice_kind` 单一裁决点（seethrough>retest>none），无供给站主按钮不渲染+诚实降级说明。live 实测 f16demo 任务卡=A01/retest（不再指 F16）。
- **[断线①转活] R6 挖空死供给接通**：cloze 服务/端点/A01 signed bank 三段早已俱全但前端 api.js 零调用方（四专家组审计抓出）。补 `getLubanCloze` 唯一调用方 + gauntlet ②半写真消费（逐句默写+对照提示确定性自查，呈现层零学情写入；无供给站保持自由默写降级）。live 实测 A01 16 句挖空渲染+命中/对照反馈。**流程教训：验收一直验"存在"没验"闭环"——bank 类资产验收应加端到端消费探针。**
- **[反馈精细化] retest 答对也给门道**（correct_statement 不只在错时出现）+定位 chip+完场分解仪式；errorbank 暖处方按错因码分文案（WARM_LINES 呈现层镜像，禁审视词测试钉死）；learn F16 入口去内联 hardcode style。
- **验证**：pytest luban_lesson 56 passed；node 全量 0 fail（learn-vm 14 含供给路由三态/gauntlet 含挖空自查/errorbank 含分码文案）；live 三页 automator 实测（todayTask 路由/挖空 16 句/retest 反馈）。commit `33725280`。
- **未动（按审计裁决留 owner/后续）**：retest 二元形态 off-spec 改档位①（需 recall 供给拍板）、考点卡 miss_count 红标（需 read model 投影）、深 pack→答疑注入、看穿模板衰减实验、R7/金标人门。

### 2026-07-10（retest 纸墨版整页重做 · owner"要 wow 不要普通"返工 · 即时入账）
- **[编译资产焊进反馈] 教材原文并排卡**：发现变体 `anchor` 与考点卡/挖空 bank 的 `point_id` 同为 kc: 坐标系 → `build_retest_items` 按 `anchor==point_id` join **同 pack** signed 考点卡（同一 `_load_signed_bank` 双闸，quote 逐字透传零生成，join 不中 fail-closed 缺省；跨包借 quote 红线不适用=只 join 自己 pack）。实测 121/1029 变体可翻出阅卷认的教材原句（A01 27/J01 52/N01 12/S05 30）——"答完一题翻出教材那一句"落地。
- **[整页重做] retest 从深色题列表 → 纸墨单题聚焦流**：pk token 单一权威；墨点进度（对竹青/错赭/当前墨环）；印章反馈（真懂/差一步 衬线圆章 stamp-in）；门道段答对也给；书页样原文卡（朱红书脊+衬线引文+页码角注，有原文卡时不露 kc 坐标）；完场纸墨收据（大分数/考法覆盖/原文句数/错题"再看一眼"清单/明日换皮·回炉完成朱红章）。动效只动 transform/opacity（丝滑纪律）。
- **[历史记录，2026-07-12 已收权]**：当时保留了本地销账 storage 与客户端判分；当前 terminal 只认服务端 signed rescore，旧 storage 已删除，页面不再自行宣告单题销账。
- **验证**：pytest luban_lesson 57（含 join 签发闸/命中/缺省三态）；node 全量 0 fail；wxml 平衡自检；DevTools automator 全流程实测（5 题走完：反馈满配截图/收据 4/5·5 考法·1 原文）。commits `7bb4e1d7`+细节修。
- **待铺（内容侧非工程）**：原文卡覆盖率吃考点卡签发面（现 5 站）——考点卡编译脚本跑其余绿灯 pack 即自动放大，无代码改动。

### 2026-07-10/11（答案模式泄露红队战役 · owner 亲测抓获 · 即时入账）
- **[owner 抓获] 轻练"只点不妥当肯定正确"**——三路红队并行量化+机制确诊：
  ① **选题层锁步**（真凶）：`_forward_rule_group_spread` 对所有考法组施加同一 `(seed+round)%len` 偏移，而池按"每组对齐序"生成（第0位=正确情形）→ limit≤组数时 5 题全取同一"位置列"= 单一答案。实测 forward 全同率 **17.2%**（review 仅 0.6%），seed 奇偶直接翻全对/全错。
  ② **编译端句式泄露**（更深的病）：模板分派与答案绑死（`params.case`→答案 100% 绑定；True 套"列入"肯定壳/False 套"认为/无需"否定壳）。"认为"句 n=213 跨 11 池 **P(True)=19%**（剔 J01/N03 后 127:1）；一条口诀零知识打全网 **63%**，深度≤2 决策树 **74%**，55% 及格线 **15/17 池沦陷**。J01 是唯一健康样板（认为句真值取决于数字阈值）。
  ③ **看穿 4 题 correct_option_id 全在 A 位** + 前端按原序渲染 → 闭眼点第一个=100%。
  ④ **seed 劣质**：`sum(ord)+day_index` 千级用户碰撞 58% + 人/天混叠；组序不进 seed→第 1 题永远同一考法。
- **[已修·选题层（零重签发）]** `read_model.py`：seed 换 sha256 高熵散列（碰撞清零）；组序进 seed；每组独立散列偏移破锁步；`_balance_expected_ok` 防全同+出题序确定性洗牌（§9-D3 幂等保持）。**验证：840 真数据 session 全同 17.2%→0.0%**，luban_lesson 59 passed。
- **[已修·呈现层]** seethrough 选项确定性洗牌（judge 仍按 option_id 零语义改动；踩坑一次：线性散列对仅末字符不同的输入单调→排序不动，换 xor-shift 雪崩后全选第一 4/4→2/4）。
- **[审计尺入仓]** `scripts/audit_variant_style_tells.py`：每池风格线索条件命中率报告（--gate 模式供签发闸复用）。**基线：11/17 池 LEAK**（阈值单线索≤65%/口诀≤55%）——内容返工的可证伪量尺。
- **[确权结论（红队②）]** 伪造/泄露今日全部**进不了掌握真值**（轻练走 learner_signal 非 promoting；掌握只归判分内核 writeback），但全部能污染 **D1 留存 GO 门读数**（telemetry result 客户端声明+同日重进重计）。轻练成头牌后此面变大=07-05"次雷"的当前形态。
- **[工单·待 owner]** ① **判分权收服务端 vs D5 离线可用的架构拍板**（answer 不下发+服务端 verdict 才是结构解，与既有离线设计冲突，红队一致首推）；② **编译端模板对偶补齐+重签发**（返工规格：每个泄露句式壳补真值反例，照 J01 样板"认为+参数化阈值"；gate 加风格闸=audit 脚本 --gate；seethrough bank 生产随机化正确项位置；S05 修 30% True 失衡）——重签发走 promote 人闸；③ **形态升级**：判断题二选一违背双轮设计"回忆优先/移除再认"铁律（§5.2/§D10），升 4选1 诊断探针（D17/看穿 schema 先例）；④ BI 按 (user,pack,day) 折叠去重防重进重计。
- **[方法论教训]** 四专家组审计过供给/消费/美学，**没有一个以应试老手身份把产品当题打**——"策略机器人红队"（傻瓜策略命中率量化）应成为出题类资产的常设审计维度；且这些 tell 同样污染一切用此题池的 eval/判分回归（掌握度含风格分），补对偶前的"命中率提升"结论均应打折。

### 2026-07-11（考点卡质量治本战役 · owner"敷衍/不一定正确"验尸 · 即时入账）
- **[owner 直觉两连中+更深]** 34 卡验尸：11 卡 quote 半句截断、10 卡 source_ref 空、"4级"式空壳 gist。双面板对抗质检 162 卡再挖出两个批级病：**S1 改写冒充原文**（117/162 旧 lane quote 是 LLM 压缩转写，0 张逐字命中教材——"教材原文"承诺被二手文本兑现，A 级内容错 13 张：J01 危大数目错/限定丢失、C01 施工缝丢"中间"、F02 伪造温度区间等）；**S2 选句错位**（逐字的那批选中错误句子：C02 13/16 张 quote 竟是案例提问清单/邻卡答案）；S3 gate 假绿（不查 front↔quote 对齐、不查 gist 数字出处）；S4 leaf_name_path 错乱（待办）。
- **[治本=选句权重构]** builder 新增教材权威库接入（FINAL_CLEANED_BOOK2026 三分片, chunk 全文+真页码, 事实权威阶梯教材>一切）+ `_select_quote` **意图对齐选句**：quote 一律由 front+gist（人写 §1 短名=卡的意图权威）在 chunk 逐字窗口中重选，枚举 run 合并（"合格五条"类整表窗口），硬门槛=gist 数字覆盖≥80%+front 对齐≥0.15，选不出=剔卡（宁缺勿假）。gate 补两道闸：intent_misses（答非所问挡板）+ gist_num_orphans（数字出处闸）。面板剔卡 blocklist（8 张 §1 内容错卡，人审记录 builder 确定性消费）。
- **[终态+签发]** 17/17 站 gate 100% → promote 人闸全签：**141 卡**（34→141），99%+ 教材逐字化、100% 真页码、面板点名病卡全部治愈或剔除（"合格五条"=完整五条枚举、"竣工验收程序"=完整五步；C02 提问卡/E01 合成卡/敷衍原型卡剔除）。轻练教材原文 join 覆盖抽样 12%→29%。luban_lesson 59 passed。
- **[方法论]** ①"确定性修复"第一版只救了逐字可定位的卡（改写文本定位必败被静默跳过）——**修复管道自己也要被对抗核验**；②验收铁律追加：内容资产的 gate 必须含"意图对齐"维度，结构闸全绿≠内容对；③J01 旧签发 6 卡含 3 张 A 级错已在生产——**下架即改进**，§1 重写后回炉。
- **[待办]** leaf_name_path 错乱修映射；X03/G03 低危表述备注 4 条；J01/N03 被剔 §1 行重写（教研）；lecture lane 卡纳入下轮人审面板。

### 2026-07-11（解药+变体statement验尸战役 · owner追加下令 · 即时入账）
- **[三面板+Codex异源全量验尸]** 变体唯一statement 237条+解药去重152条(A-G 83/J-X 69)逐条对教材权威库裁决；Codex对抗复核近期全部代码产出(10卡抽验全PASS,抓1个真缺口=卡builder专用测试套漏跑且口径过时,已修22 passed)。
- **[判决] 解药11条A级/变体9条statement A级(波及40变体)**。**共同病灶(6/9变体A级+5/11解药A级)=旧真题官答/旧规范记忆压过2026新教材**：地下防水四级(废止GB50108,教材仅三级,F03同池还把教材正确答案判False=可证伪即崩)/超灌0.8~1.0m(教材≥1m)/钢丝网应保留(教材:浇筑前拆除)/变形缝作检验批依据(教材已删)/造价五部制(规费已并入人工费)/早强剂不宜蒸养(教材:宜用于蒸养,仅有机胺类不宜)。次病灶=多档规则压缩丢分档轴(S06竖向/非竖向)+丢限定词(E01暂估价除外/A01回弹取芯法限定)。
- **[治疗全落地]** ①变体:`_variant_blocklist.json`(40条A级)+read_model serve侧过滤(签发bank不动,测试钉死绝不下发);②解药:builder blocklist(11条A级,dropped=panel_reject留痕)+C02尾部裸露kc串确定性剥除,10站重编重签(promote人闸);③Codex抓的测试缺口修复。测试82+20 passed。
- **[洗白名单]** 红名单多数经教材/真题官答证实为真(D11抹灰20/25、D13防火尺寸、S05电压序列、S06跨章0.9/1.2、X01围挡、X03三条、N01 TF=0、C01 28d养护)——数字扫描的假阳性率高,人审面板不可省。
- **[系统性教训]** ①内容资产三兄弟(卡/解药/变体statement)同一病谱:LLM生成层的参数记忆(旧规范)会压过anchored教材,**签发闸应加"新旧规范冲突"维度**,LLM改写审计抓不到这类,必须教材diff;②解药gate此前只查锚可解析,7条A级带绿gate签发=gate假绿第二实锤;③blocklist三件套(卡/解药/变体)=人审剔除的统一模式,救活=修pack后重签并移除。
- **[待教研/owner]** 被剔40变体+11解药的pack源修复(旧新规范冲突需教研按2026教材逐条裁决重写§4/§6);B级留观(J01基坑8+1项/S05 50kW/Q01冬期3℃/X01六项计数);错因银行加载不了已修(demo缺MISTAKE_BOOK flag+前端404降级,52e917e7)。

### 2026-07-11（判分编译库验尸 · 轻量路径按 owner 校准 · 即时入账）
- **[结论=结构健康度远好于教学三兄弟, 无 A 级, 未升级面板]** 确定性预扫+主控直查：legacy 库(1221 记录/174 qid)教材引证 **1004 条 100% 逐字命中**、分值和仅 1 qid 异常且该 qid 不可达；PGO(1384 点/179 qid)与 legacy **零交叠=两套题集**（legacy=章节练习题, PGO=2015-2025 历年真题案例）——"promote PGO"是扩覆盖不是换弹夹, 之前"80% 真题现编"的治法拼图更清晰了。
- **[判分库的"旧规范"镜头与教学资产相反]**：判分库判的是历史真题, 该年官答就是 ground truth（规费类记录=合法历史口径）；教学三兄弟才需要 2026 口径。两类资产的验尸镜头不能混用。
- **[登记的 B 级/NOTE]** ①裸 qid `NUMERIC_9001/9534`（8 条内容真实但 qid 退化不可达, 9001 分值和 7≠6, 源管道修 qid 即回收）；②11 条 required_terms 与 text 措辞漂移属判分严格度细节（如 term"特种门安装" vs 教材名"特种门窗安装"）, 归金标校准范畴；③PGO 189 条 <4 字碎渣点多为 list/enumeration 设计内（'工会''资质'=列举项）, 3 条 >120 字粗粒待金标轮看。
- **[owner 校准入规]** 关键问题（收入闸/权威裁决/高不确定）才上"独立第三方宏观质疑+Codex 对抗"重炮；普通难度直接干。本次即按轻量路径执行的首例。

### 2026-07-11（判分库判决被异源推翻 · Codex GPT-5.6-sol 终审 + spark 旁证 · 即时入账）
- **[撤回前判决]** 上条"判分库结构健康无A级"**作废**。owner 坚持异源对抗后, Codex(5.6-sol, 独立只读+实跑判分函数)推翻四项, 主控已逐条独立复核坐实:
  ① **A级判分错误已入库**: NUMERIC_9001 的错误计算(E≈5.74/选F)被洗入 PGO 可达 qid `2023::EXAM_1A432000_P0017_01::E4` 且标 `exam_reference_answer`; 源答案=E8/F7/G6/选G(legacy 同 qid 反而正确)。我此前判"不可达孤立异常"错——错误答案有第二条入库路径。
  ② **评分对象边界坍塌**: 多小问被压进一个 qid 共享第一小问总分(18/22/27 点共用 total 5-6 分); 仓库自己的 backfill 桥早写明"per_question 结构乱(granularity collapse), 真题判分应直接用 canonical rubric"。
  ③ **score=None ≠ 不计分**: grader 按"命中原子数/原子总数×官方总分"算(rubric_grader_v1.py:229/274)——**切分粒度本身就是隐含分值 authority**; Codex 实跑: 答对官答 3 分内容得 4.2/7、答完整第一小问(封顶5分)只得 1.36/5。我判"189 碎渣设计内"错。
  ④ **零交叠假象**: 去掉年份前缀 175/179 PGO qid 命中 legacy(154 基 qid)+PGO 内部 14 组完整内容重复; 编译器源码自注"real namespace hazard"。"两套题集/promote=扩覆盖"判断作废。
  ⑤ **authority 冒牌**: 源文件自述 `NOT_official=true`(training_org_analysis 估分), PGO 却统一标 `official_answer_verbatim`; schema registry 早已把 per_question 定为 deprecated/adapter-only。
- **[红线立即生效]** `LUBAN_CASE_RUBRIC_BANK_SLOT=pgo` **禁止拨**(此前多份报告的"差一脚 env"建议全部撤回); PGO 停留 shadow, 重建必须走 canonical rubric 路线(backfill 桥的既有结论)。legacy 继续服务(其数值正确性反而被本轮加固)。
- **[spark 旁证收敛]** 降级 spark 独立跑的同任务发现同向问题(qid 前缀假象/官答忠实度/2022::P0015_01 多点走样)——双异源收敛, 置信度高。required_terms 漂移经 5.6-sol 核实 policy=list 走 LLM 语义判分, 不必然误杀(spark 判断修正), 降回观察项。
- **[方法论三连]** ①轻量路径误用第二实锤: 关键资产(收入闸)无异源不收官——owner 两次纠偏都对; ②异源对抗要"实跑不只读": 5.6-sol 胜过我预扫的关键=真的执行了判分函数; ③敢对付费用户判分前三件事(Codex 宏观判语): 官答→库逐点全集覆盖率比对 / chunk×year 跨库 dedupe / required_terms 同义扰动对抗回放。
- **[待办工单]** PGO canonical 重建(含 authority 标签矫正+小问边界修复); 2015-2020/2022正考源缺口(归 governed gold); 14 重复组余下 12 组人工判"同题重复 vs 合法共用"。

### 2026-07-11（owner 真机三问 + 四拍板落地 + 宏观独立专家判决 · 即时入账）
- **[owner 真机三问(原文要义存档)]** ①看穿模块的目的/与其他功能的区分补充是什么? 5 天形式交互不三不四(完成一天跳回/又不让一口气做完)=UX 有问题;②换皮复测题目本身有没有问题? 固定那几题老用户马上腻、感觉被敷衍;③复习页三块(hero/约定卡/清单)花哨好看但点进去都是同一个东西——设计之初就这样吗? **调查结论**: ①审阅脚手架("雏形允许自由跳")泄漏成产品体验;②题目内容对但 B-basis 组 16 变体仅 4 种句式骨架=表面多样性极低;③设计三层假设多站队列, max_active=1 使三层每天必然塌缩同指一站。
- **[四拍板+落地]** ①三问入账本(本条);②**看穿弃日隐喻改"5 关连闯"**——已落地: chrome 全面关卡化(第N关/下一关/5关全通), 递进解锁(_isUnlocked: 完成+1 可进, 未解锁 toast), 审阅自由跳脚手架移除;③**换皮四层优化**——呈现层已落地: 选题层句式骨架去重(_diversify_skeletons, 场内不重骨架)+题池元信息(retest_pool_meta→hero"本站N道·M种考法")+收集感(本地已见 seen/total 进收据); 形态层(4选1)/内容层(表皮多样化+对偶)=既有工单; ④**max_active 1→5**("做1实在太少了")——revalidation_queue._DAILY_MAX_ACTIVE=5+daily_capacity 同步, 测试改新口径(7到期→5发射2压制); 复习页补 n=1 三合一折叠(showDueList=dueCount>1)。测试: luban_lesson 62 + learner_state 541 + node 全量 0 fail。
- **[owner 战略定位存档]** "现在是搭基建做体系——全知识点量产还没开始, 基建必须扎实好用"; 且常设第三方顶尖独立专家宏观审视, 防自嗨防盲区。
- **[宏观独立专家判决(全文在会话, 要点存档)]** 总裁决: **工具链工业级, 内容生成→质检回路手工业; 下游扎实、上游产线带病停摆、人闸是一个人的名字**。①可量产性先断点: 17 个手写变体 builder(互差 395-479 行非模板)、审计尺造好没接闸(audit_variant_style_tells 全仓零引用/CI 零内容闸)、教材 diff 预扫缺失(A 级主谱系防线仍是面板)、blocklist 复活零先例、pack 产线停摆 3 周(06-20 一次性产出后未动, 病未治产线重启=5 倍复现);②自嗨信号: 141 卡当天代签有未审面(lecture lane)、质量循环"面板互证"用户不在场(验收标准从真人回访悄悄降级为面板 PASS);③体系级盲区: 教研产能模型(岗位不存在却是量产依赖)、内容回归 CI=0、用户反哺排产回路=0、教材版本滚动 story 缺失;④量产前只做三件: 尺接闸进 CI / 变体生成层返工+17 builder 收敛 1 个数据驱动 builder / 真人进场+跑通一单 blocklist 复活回路; 可缓: first-run·retest 二轮视觉、看穿铺量(模板假设未证)、PGO 重建。**本日四拍板中 max_active 被其背书, 看穿关卡化+换皮打磨被其排在三件基建活之后(已按 owner 指令先行完成, 后续消费层打磨默认冻结让位基建)**。

### 2026-07-11（首次体验→复测 Learner State 闭环根因加固）

- **撤回旧链路说明**：retest 不再是“本地判分 + telemetry + 页面发 station_completed”。客户端本地判分只保留即时反馈，不具 learner truth 权威；最终 completion 必须 POST 到服务端按 signed variant bank 重判。
- **根因**：item row/attempt truth 粒度错位，`learning_synthesis`、three-layer projection、learning report 三处各自按行数升档；partial item 又提前携带 verified 终态。
- **收权**：shared evidence lifecycle 统一 source/promotion/attempt/terminal；RetestWritebackService 唯一写 item→terminal→station；review 绑定 due probe，forward 恒 non-promoting；处方和 probe identity 与 target pack 分离。GET 签发绑定 user/pack/day/mode/variant-set 的 selection identity，POST 验签后按原签发日重判，跨午夜/断网 retry 不换题。
- **五模块侧门收口（后续已加强）**：gauntlet 的即时再练显式归 forward；errorbank 删除“有题池=已到期”的前端推断，只消费 canonical review-due，pack、`retest_available`、probe 三者齐全才亮复习 CTA，并透传 `mode=review&probe_id`。2026-07-12 又删除了复测后的本机单题销账，terminal truth 只留服务端。
- **UI 语义**：保存失败不出收据、不说“明天见”；服务端 terminal 成功后 forward 进 handoff，review 回复习。handoff 只保留提醒与 telemetry，不再写 learner state。
- **发布边界**：本轮不部署。首次四题仍因双教研签发未完成而 fail closed；真实微信订阅提醒仍依赖模板 ID，不能用页内红点冒充系统推送。

### 2026-07-12（首跑内容签发翻牌 · owner一字拍板"签"）
- **[签发执行]** script_manifest.v1.json四题`review_status=signed`+双reviewer留痕(`teacher_review:owner_cainkyking:2026-07-12:{qid}:{content_sha}`+`claude_fable_owner_delegate`同格式;content_sha按manifest.py同源规范化计算),`release_status=signed`+release_signoff(basis=owner本人对话授权,四题源自签发采分点owner本周多轮真机过目)。真loader`_require_signed_manifest`校验PASS。
- **[版本连锁]** 签发改变script_version(清单sha)→前端script-data.js常量同步到`@5873e950…`;learn.js重放前对陈旧pending payload做版本自愈(题集与内容sha未变,仅签发元数据改版本,按当前常量重放,避免永久version_conflict)。
- **[活体验证]** POST /first-run/complete(新版本号)→**HTTP 200, sync_status=synced**,score/learning_event_refs/training_intent/home_projection全量返回——"正在保存学情"卡死从治理源头到呈现层全链路治愈。

### 2026-07-12（首跑'保存中'卡死治本+生产侧读性能 · owner三连②③）
- **[③'正在保存学情'卡死=三层根因]** ①真源=首跑内容清单`release_status: blocked_pending_human_verdict`(双人签发人闸,writeback fail-closed by design——**这是治理态不是bug,签发决定在owner**);②**真bug**=HTTP异常处理器`str(exc.detail)`把结构化detail字符串化成"{'error': ...}"单引号串,前端解析不到错误码→把治理性409误当网络错→无限'保存中'(learn页自动重放机制其实一直在,只是每次都误判);③test2旧后端的422同病。治法:runtime/safety.py detail是dict/list原样透传(契约形状不变,类型忠实raise方);前端api.errorCodeOf兼容对象+旧字符串双形态(test2未更新期的belt);learn页blocked态文案本来就诚实('学情等待同步·点击重试保存'),解析修好后自然落位。
- **[②五模块慢-生产侧]** 本地fallback只治开发机;生产侧两刀:①`_load_signed_bank`加(path,mtime)键读缓存——每请求扫37+个bank JSON的重复磁盘解析是复习/学情面读放大源,文件一变即失效,语义与直读等价;②learner_state远程memory events加20s TTL缓存+`append_memory_event`写侧即时失效——串行4次Supabase往返(~3s)是页面等待主体,同用户20s内复访直接命中。回归:read_model 26+learner_state 551全过。
- **[owner待拍板]** 首跑清单签发:script_manifest.v1.json四题需`review_status=signed`+每题≥2 reviewer——这是内容人闸,你说签我就按你授权翻(reviewer留痕),或走真教研双签。不签则首跑学情写入持续fail-closed(报告本机可见,学情不入账)。

### 2026-07-12（标准卡放量就绪+轮次体验+RichLeaf灰度runbook · owner"按你的建议来,顶尖体验"授权）
- **[标准卡品质关+正式签发]** 修两个可见瑕疵:①knowledge-shape actor边界`负责(?!人)`(此前"设计单位项目负责人"被截成"设计单位项目");②跨点给分词去重(第二组剔重,剔空弃组)。重编100卡后走**promote std车道正式签发**——promote_variant_bank.py新增packless车道(同构语义:builder --check复现一致+source_v32_sha256锚定编译资产+教材复核零跳过+禁词扫描+签发翻牌唯一在本工具),signoff留痕owner授权。后端生产闸:**生产只认signed**,candidate仅非生产预览。放量姿势=部署时置`LUBAN_STD_CONCEPT_CARDS_ENABLED=true`(质量49+进度51两deck随下次test2/生产部署即亮)。
- **[轮次体验(爱上的一拍)]** 考点卡每10张进**轮间歇收据**:斜章"第N轮"+大字进度+记住/回炉账目+确定性暖句轮换+两钮(继续下一轮·还剩X张/今天到这里·回复习)。49张的墙变成一轮轮小胜利——完成感是"还想继续用"的燃料。vm纯函数roundInfo(+4契约断言),实机验证第1轮10张准点触发。
- **[RichLeaf灰度runbook(消治理blocker)]** flag=`LUBAN_RICH_LEAF_RUNTIME_ENABLED`(rich_leaf_runtime.py:35,默认OFF);消费点唯一=compiled_knowledge/general_knowledge.py:740(ADDITIVE overlay,miss即fail-open回legacy四源链,confidence门仍是路由权威)。**步骤(下次Aliyun里程碑执行)**:①test2部署时置flag=true(test2即qa环境,天然内部cohort);②Langfuse trace核rich_leaf_contexts真实命中+with/without对照;③盯排除法泄露复发(prompt≠terminal authority旧案);④≥3轮live核终态;⑤全绿→owner签published:true消掉release_governance_not_exercised。生产flag保持OFF直到owner签字。

### 2026-07-12（三线并行:标准卡量产spike+共享组件收口+RichLeaf通电评审 · owner"三件事都做"）
- **[①标准卡二梯队spike已通]** `scripts/build_luban_standard_concept_cards.py`:RichLeaf v32(1606叶verified采分点)×11年真题考频(FINAL_CLEANED_EXAM node_code实证,案例×2+选择×1,方向性口径)→**Top100叶标准卡**,四闸fail-closed(verified+教材quote逐字复核(不信任传递,100/100过)+禁词+去重)。聚成施工质量管理49+施工进度管理51两高频章deck(taxonomy二级节点权威命名)。**分层纪律**:tier=standard/status=candidate,后端只在`LUBAN_STD_CONCEPT_CARDS_ENABLED`且非生产投影(生产fail-closed),抽屉标"标准"徽标——签发口径待owner过目打样后定,不冒充精品。库总量141精品+100标准=241张。后端6 pytest全绿,API+实机验收(STD01首卡=分部验收组织,7给分词章)。待精化:actor切词偶有截断/跨点重复term去重/考频node级精确化(盘点文档自注待办)。
- **[②共享组件收口]** 形态学解析器抽为`utils/knowledge-shape.js`(链/规则/枚举/红线/句读/数字+形状归型,concept-cards-view-model改require保持导出兼容,测试全绿);错因银行解药mental_model接`parseChain`→箭头链渲染竹青石链(检验批→分项→分部→单位这类心智模型不再是一段文字);复测完场收据挂考点卡回路(错了="把给分词背上"/全对="趁热巩固",学-错-背三角第三边闭合)。
- **[③RichLeaf通电评审:两专家收敛裁决]** 质量权威专家:published:false=治理未走完非质量缺陷(5 blocker中3纯治理;fail-closed结构锁已浇死official_answer冒充,`rich_leaf_runtime.py:280-317`);架构消费专家:**"通电基本是伪需求"**——runtime bundle实为1466条/2.8MB/lru一次载入,唯一已接线消费者=general_knowledge教学overlay(additive,flag默认OFF);四候选消费者排序=标准卡(编译期)>轻练富化(编译期)>报告副标题(投影)>TutorBot grounding(runtime)。**合议裁决:编译期全吃为主线(①已执行第一步),runtime flag保留为廉价期权;若要消掉release_governance_not_exercised治理blocker,test2 qa_ cohort给教学overlay灰度一次(owner拍板项)**。90天消费路线图入账:D1-14标准卡打样(已完成)→D15-30轻练/cloze富化→D31-45报告副标题投影→D46-60消费驱动质量回灌quarantine→D61-90按需灰度runtime。

### 2026-07-12（五模块加载慢根因+修复 · owner"为什么特别慢"）
- **[根因]** 量化定位:review-due **3.45s**、mistake-book **1.0s**,其余端点全毫秒级。剖析:投影本身6ms,3秒全烧在`list_memory_events`——本地开发后端每请求**串行打4次远程Supabase HTTPS查询**(~1s RTT×4)。学习/复习/错因页都消费这两个端点=五模块整体感觉慢。
- **[修法=接通休眠旗标,零代码]** 代码里逃生门早已建好:`DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK`+`DEEPTUTOR_MISTAKE_BOOK_LOCAL_FALLBACK`(非生产+flag→本地投影,不打Supabase)。本地serve脚本加两行env→**review-due 3.45s→0.04s(86×),mistake-book 1.0s→5ms**。dormant flag再添一例:修法不是写新码,是给已有门通电。
- **[生产侧注意]** 此修只治本地开发体验;生产(Aliyun→Supabase)同样存在"每请求串行4连击远程查询"的结构病(六专家审计的同步阻塞+读扇出),RTT小但仍在账上,治本需读侧缓存/合并查询,另立工单。
- **[owner问"下一步把所有考点卡都更新掉?"]** 已全部更新:v32富化+重签是**17站141卡整体管线**,不只A01(证据表:95/141带给分词,X03 15/19、X02 10/11、C02 10/13…J01 0/3是该站chunk无verified采分点交集,fail-closed宁缺)。真正的"更新掉所有考点卡"=铺满40站/全考纲,瓶颈在考点原料pack量产(内容线),不在这条技术管线。

### 2026-07-12（考点卡×编译资产：v32采分点富化进卡 · owner"利用编译资产,数据盘点里找"指令）
- **[资产选型]** 按数据盘点(2026-06-16编译资产盘点)核库:选**RichLeaf v3.2采分点富化层**(1612 unit/5705采分点,每点带quote_verified教材溯源+required_terms)——141卡chunk_id join命中**141/141**,可挂~1823点。exam_patterns**不上**:LLM合成题面无verified溯源,不冒充真题考法(单一权威纪律)。
- **[编译期join四闸]** builder新增`_attach_scoring_terms`(fail-closed):①quote_verified=True且source_authority=textbook;②terms 1..8个;③**每个term逐字∈本卡quote**(卡引的是chunk意图切片,词不在切片=不是这张卡的给分词,宁缺勿挂——A01竣工验收卡因此滤掉了同chunk的屋面/检验批杂点);④terms元组去重,每卡≤2组。**覆盖95/141卡(67%)**。bank记账enrichment元信息;17站全部rebuild+promote人闸重签(basis留痕)。v32包为本机artifacts软链(同教材库先例,缺席=空富化不挡产出)。
- **[消费链]** 后端concept_cards投影透传scoring_terms→vm scoringTerms→卡面新块**"阅卷认的词·写到才给分"**(朱红词章+`来自判分编译库·教材原文逐词核验`角注)。竣工验收卡实测:竣工验收/预验收/评估报告三词章。前端契约+3断言、后端6 pytest全PASS,automator实机截图验收。
- **[意义]** 考点卡从"背原文"升级为"背给分词"——判分编译库(1221条判分点的姊妹资产)第一次直接喂进记忆产品面;供给消费缺口(21:1病)再收窄一格。

### 2026-07-12（考点卡v3精致化+选站抽屉 · owner"不够精致/交互不好/全面吗"三问）
- **[精致化=形状驱动的视觉系统]** 参考顶尖知识卡(Anki高分卡组/间隔重复最佳实践"回忆先于核对"):①**知识形状徽标**——每张卡按结构定形状(一道红线/一条规则/一条流程链/一份分工清单/几个关键数/几句要点/一句原文),正面出**回忆预告**("背面是一条流程链·先在脑子里搭出它"=recall priming,给回忆一个方向而不是裸问);②形状色系(红线朱红/流程竹青/数字赭/要点墨)贯穿:正面预告chip→卡片左缘色条→翻面徽标;③翻面内容ccUp入场动效;④"点一下翻面"斜置朱红章;⑤进度条升级**骨牌**(过一张点亮一枚,当前朱红);⑥完场账目(记住N·回炉M大字对账)。
- **[选站交互重做]** 横向拉chips→**站牌+选站抽屉**:当前站牌(站名/张数/待还红点/▾)点开底部抽屉,双列网格全站一屏选,红点=该站有待还错因(pendingMap全站一次算清,与错因银行同一归属口径);另设"下一站›"循环连翻(完场页也有)。
- **[141张全面吗——诚实口径]** 不全面:141张=17个试点变体站的签发量,考纲taxonomy共3158叶、路线40站。头部文案改诚实口径"已铺17站·141张·持续铺站中"。量产瓶颈不在前端在内容编译线——变体引擎(X02试点DIFF-EQUAL)+builder收敛正是为量产铺的基建。
- **[验证]** 契约测试+4断言(知识形状)全PASS;automator实机三截图(正面预告/翻面徽标/选站抽屉红点)验收。

### 2026-07-12（考点卡形态学v2+错因银行双向挂钩 · owner"页面没效果/太linear"反思整改）
- **[owner反馈+我的盲区]** 前一版三解析器(链/枚举/数字)在141卡全库只命中~41张,**约100张裸奔回落颗粒条**——我拿一张最漂亮的卡(竣工验收5步链)验收了"通用"声称,犯了"样本选择性验收"错:owner随手翻到3/8(条件→红线卡)就当场露馅。教训与错因银行同款:**声称通用必须全库覆盖率实测,不许用最佳样本代表全体**。
- **[形态学v2]** 新增4种确定性形态(仍全部逐字切分零改写):①**规则牌**=双段gist(条件⇒结果),结果含严禁/不得/禁止→**红线章**(朱红描边);②枚举兼容**（1）（2）式**(教材另一常用体例,此前只认①②);③**红线句捞取**=原文含禁止词的整句(≤2条,"禁"字斜章);④**句读要点**=无枚举时按。；切2-6短句兜底。枚举行含禁止词朱红高亮。**全库实测:裸奔19/141(86%有结构)**,链10/规则2/枚举68/要点36/红线21/数字45。契约测试+7断言PASS。
- **[考点卡↔错因银行双向挂钩]** (owner提议;纯导航回路,零第二权威):①考点卡记忆面→本站有待还错因时显"这一站你有N笔待还错因·去看解药"(deriveRetestPackId同一归属口径,未开通/0笔不显);②错因银行详情解药卡尾→"翻这一站的考点卡·教材原文逐字巩固"(有packId才显)。学-错-背三角闭环打通。automator实机验收:目标卡(严禁验收红线)规则牌+红线高亮+挂钩条(1笔)全亮。

### 2026-07-12（错因银行二级页评审+治本：解药签发内容全量放行 · owner"信息有限"反馈即时入账）
- **[owner问: 二级页信息很有限,是早期对话的原因还是以后都这样]** 答:**两者都有,且都能治**。诊断=富内容要同时过三道闸((pack归属命中)×(错因码是注册码)×(该站解药池收录该码)),任一miss就退化占位;早期对话记账三闸全难命中。且**后端把签发解药的2/3字段丢了**(build_antidote只回mental_model+textbook_ref,phenomenon/wrong_model被扔,同码多条只取一条)——签发内容付了钱只消费1/3,又一例消费不足。
- **[治法四层]** ①后端`build_antidote`全字段投影(items数组含phenomenon/wrong_model/mental_model/textbook_ref,首条顶层键向后兼容,6 pytest PASS);②vm加**人话标签↔注册码逆映射**(同一注册表双向镜像非二次归因——判分内核写"关键词缺失"这类人话diagnosis的记账,现在能解锁(pack,code)解药查询键;整句/「标签：细节」前缀两种形态;非注册文本仍不硬造码);③详情解药卡重排为**三段递进**:常见的坑(phenomenon)→✕旧地图(wrong_model,划线+赭色)→↓换成这张新地图→✓新心智模型(竹青强调)+教材出处,同码多条最多展示2条;④共情细节:空note不再留空壳kicker;无码早期记账给一句诚实说明("早期记账没带错因码——新的判分会自动归因,这页会随之长厚");列表行首空粉块补错因码印章。
- **[验证]** 真ref铸造(sign_attempt_ref)种3笔代表性数据(富E06/A01·中"关键词缺失"→逆映射E03·薄自由文本);automator实机三态截图验收:列表/富详情(三段解药×2条全亮)/薄详情(暖降级+诚实说明)。vm契约测试含旧断言契约更新(人话标签逆映射为特性)全PASS。
- **[盲区反思]** ①此前修"错因银行404"只修到诚实空态就停了,从没用**代表性数据**走过一遍二级页——每个fail-closed单独看都对,叠在一起=体验荒漠,这是"逐闸正确,整体饥饿"的盲区;②解药bank签发时对抗验尸过内容质量,却没审计**消费端到底用了几个字段**——供给侧验收≠消费侧验收;③deriveRetestPackId严格等值匹配是诚实设计,但零命中时无任何遥测,饥饿不可见。教训:**页面验收必须带代表性中间态数据,供给资产上线必须核消费字段覆盖率**。
- **[遗留]** pack归属仍fail-closed(concept_label须全等站名/qid含pack词元)——扩宽需要owner拍板口径;解药池当前~17站×少数错因码,覆盖率提升靠内容量产线。

### 2026-07-12（考点卡记忆面重设计 + 轻练接线澄清 · owner两问即时入账）
- **[owner问1: 轻练是不是没接进去]** 澄清:**已接进去**——本线(codex/first-run-learner-loop)已把纸墨复测/5关连闯/四拍板/防泄露全量 cherry-pick(8cafb6de/4ab32db9/fcff8b48/d53eadbc);学习页"教研签发中"是**供给真值路由的诚实空态**,病根=DevTools连的test2后端还是旧代码(无retest_available字段)。本地后端(f16_local_serve_loop.py指本树)实测:A01/C01/C02 retest_available=true,供给全亮。**结论:前端接线完整,差的是后端部署**(上test2/生产=Aliyun里程碑)。
- **[owner问2: 考点卡太繁琐,要精妙设计]** 翻面从"原文墙"重设计为**记忆面**,三种确定性图形化(单一权威边界不破:全部是key_gist/quote的逐字切分,前端零改写零生成,测试钉死"主体+动作=原文逐字子串"):①**先记这条链**=key_gist按→切步骤石链(朱红序号章+纸片石+箭头,自动换行);②**谁做什么**=quote按①②…枚举切行,主体(勘察单位/监理单位…)提为竹青签章+动作原文;③**关键数**=数字+单位提为大字瓷砖(≤4枚,带逐字上下文标签)。无结构可提炼的卡回落可背颗粒条。**教材原文默认收拢,「看教材原文全文↓」一键展开**(尊重爱看全文的用户);溯源角标(kc:+教材页码)常驻。解析器在concept-cards-view-model(纯函数),契约测试+8断言全PASS;automator实机截图两态验收(记忆面/原文展开)。
- **[附带]** demo本地后端serve脚本换台账:f16_local_serve_loop.py(sys.path指本树,手机号19900000712注册f16demo);app.js USE_LOCAL hack仅本地不提交(沿ee99e76e惯例)。

### 2026-07-12（首跑亮色版配色治本 + 学情/我的默认亮色 + 外观切换 · owner三连指令即时入账）
- **[owner反馈]** 首跑判分卡/报告幕大量文字隐形(截图证据)——根因:first-run.wxss 是蓝黑青暗色基座+纸墨覆盖层收口(`fr-page paper light pk-paper-bg` 写死亮色),覆盖层盖了 27 处漏了 12 处,暗色白字/亮青/深蓝卡底直接印在宣纸上。**不是零散补色,是覆盖层不完备的系统病。**
- **[治法]** first-run.wxss 追加"覆盖层补漏"段(全部走 --pk-* 变量,明暗双套自适应):verdict/case 深蓝卡→纸墨卡;good/bad 选项白字→墨字;阅卷认的词 chips 亮青→墨字纸片(命中竹青/漏写朱红);hero 副行/环标签/编译库刻度白字→墨字;口诀亮琥珀→朱红;stag/字母章薄荷粉→竹青朱红赭;画像暖橙→朱红系。script-data.js 两处**内联样式**(HI/HITWORD 亮青/薄荷,内联压 CSS)→竹青 #48806a。automator 实测三幕截图验收:判分卡上/下半+报告幕全部可读且纸墨风格统一。
- **[学情/我的默认亮色+外观切换]** ①单一权威扩展:host-runtime 加 `getThemeOr(fallback)`(用户从未显式选主题时返回页面级默认),helpers 加 `isDarkOr`;app.js globalData.theme 不再烤死 "dark"(空=从未选过,这是能实现页面级默认的前提,契约测试 11 断言 PASS)。②report/profile 两页 `isDarkOr("light")` 默认亮,syncTabBar 传 isDark 让壳跟页面同色;其余页(chat 等)默认不变。③我的页"学习设置"卡新增**外观**行(亮色/暗色 chips,复用现有 chip 交互),setAppearance→helpers.setTheme 全端跟随。automator 实测:未选主题我的页 isDark=false,切暗立即生效,tab bar 跟随,亮暗两套截图均正常。
- **[测试]** 4 个 profile 测试 mock 补 isDarkOr 后全 PASS;js 套件唯一 FAIL=test_index_launch_home,系本地 project.private.config.json 编译条件指 first-run 所致(干净树 PASS),非本次改动,该文件不提交。
- **[待办]** 同病扫描显示 assessment/billing/history/mistake-book 等页存在暗色态白字(它们是明暗双态页,当前默认暗不发病);若日后把全局默认翻亮,须先逐页核 .light 覆盖完备性。

## 惯例沉淀（复盘时升格为规则的候选）
- 部署后必做独立探针（不信脚本自报）——本轮抓到 22 站 404 与 F16 无声两个上线级洞。
- owner 口述需求先 grep 是否已实现再派工；agent 终态纪律=最终回复基于磁盘/线上实测，"等待中/等子报告"不是完成态。
- owner 产出物过目制：卡/页/设计稿一律截图交 owner 拍板后再进下一步（"做出来了才知道是不是想要的"）。
- （2026-07-05 owner 拍板）常设"局外人观察者"agent：每里程碑从第一性原理审视消费链/断链/系统性隐患，防头痛医头；机械批处理活分层给 Opus 4.8，判断密集活留 Fable+异源面板。
- （2026-07-05 owner 二次修订用模准则）异源主力=Codex/GPT-5.5，GLM-5.2 降辅助（仅 4+大面板或回避补位）；**保留的例外=利益回避**：Codex 生产/flag 的条目由非 Codex 补位裁决。重尾批按原矩阵收尾（批内一致），新准则自粗粒包 leaf review 起。入仓计划文档的面板矩阵随下个里程碑 PR 修订。
- （2026-07-05 owner 确认）UI 权威=《微信小程序前端设计》第10轮定稿；缺失屏（复习 3 流程屏/批改结果页/OCR 校对屏/变体挑战流/空态）后续按同风格补，不另起炉灶。
- （2026-07-05 owner 拍板）过程中只 commit+push 分支留痕，不逐个 PR；PR+合 main+部署留给"需要上阿里云真测"的里程碑一次性做。动机：branch protection 的 BEHIND→update→CI 重跑循环在多 PR 串行时节拍成本过高。
- 批量签发 override note 必带逐包机器核验数字（verify_pack / 真题锚 / recheck 三闸 exit code）。
- 主控对 agent 交付一律独立复跑关键声称（recheck 联跑、🟢 delta、published 未动）再报 owner。
- "已裁决"唯一凭据=recheck_resolutions.py exit 0；"已合并"唯一凭据=origin/main 终态核查。
- （2026-07-10 owner 战略）广度铺量 ≠ 留存；NPS 高但 0 回访=病灶在"回访触发器（nudge/看穿+暖体验）+可触达 cohort"，不在功能数量。spike 先深度打透一个考点（F16 看穿+暖）证假设，再抽模板铺量。
- 签发内容包必带溯源 gate + 裸借守卫：跨包事实必须带 `true_source_pack`+`source_ref`+`is_extension`，禁无标注挂到本包名下；gate 要经对抗验证（故意裸借须 fail）才算非橡皮图章。
- "复用即可"的假设先以代码验证再动手：本轮三处（retest 判断题当4选1 / revalidation_queue 驱动5天 / Q18 published）全与代码现实冲突，agent 逐一 grep+读码证伪后 owner 裁断，避免照错假设建错基座。
- 审阅未部署的雏形本地起后端（endpoints.js 本地优先），别为看一眼就把 pre-review spike 代码推 test2。

## 未决观察（尚未定性，先记着）
- verify_pack.py / verify_exam_anchors.py 硬编码主 repo 绝对路径（可移植性债，D1 范围外）。
- jury sidecar 在 考点原料/ 上级目录有 13 个旧副本（权威只在 成品/），未清理。
- 多个 PR 合并被 branch protection "BEHIND" 反复卡住 → update-branch+重跑 CI 的节拍成本高，若持续可考虑 merge queue。
- `Q18-1A434000::qga_v0` blocked（score_sum_mismatch，10/11 自证卡总分和门）；Day4 真判前必先解此治理 block，本轮 Day4 诚实走 open_skill/L0 + 已签发 P10/P11 文本投影核对绕开。
- test2 部署线曾是分叉于 origin/main 的 `bcdc4a5d`，2026-07-08 发布（42681ace6）已合上；若日后发现 bcdc4a5d 独有生产内容丢失，此为源头。
- full-answer POST 鉴权失败返回 HTTP 200（body 是 401 形状）而非 401 状态码——cosmetic 不一致，功能安全（未登录不判分），可后补对齐状态码。
