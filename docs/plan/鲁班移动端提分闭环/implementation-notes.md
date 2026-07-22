# 五模块改造 · Implementation Notes（活账本）

> **方法层记录**：本账本只记结果与验证；"怎么发现、怎么分析、走过哪些歧路"的完整叙事在 [methodology-log.md](./methodology-log.md)（owner 2026-07-12 立的常设纪律，每个非平凡问题五段式入志）。


> 维护规则（owner 2026-07-05 指令）：执行中撞上 edge case 偏离计划时，**选保守方案，在 Deviations 记一笔，接着干**——复盘全靠它。
> 由主控会话集中维护；实施 agent 在隔离 worktree 工作，其报告中的偏离由主控收录。按日期倒序追加，不删旧条目。
> 关联计划：`2026-07-04-luban-ai-adjudication-pipeline-plan.md`（裁决流水线）、五模块 IA Brief、双轮 v3.2、融合计划 v1.1。

## Deviations

### 2026-07-22（首跑签发 authority 纠偏）
- **[当前终态]** 2026-07-12 的 owner delegate 字符串只证明历史授权与机械 gate 曾放行，不满足签发包既定的“两位不同真人教研”要求；该记录保留为 `Historical`，不再作为当前内容签发证据。
- **[收权]** `script_manifest.v1.json` 已降为 `blocked_pending_human_verdict`，四题 `review_status=pending_dual_teacher_verdict`、`review_refs=[]`。签发只接受两份结构化、绑定同一 question/content hash 的 `human + teaching_reviewer + approve + delegated=false` attestation；agent、delegate 与 legacy 字符串均 fail-close。
- **[边界]** 这次纠偏不撤销历史页面级或 auth-chain 验证，但当前内容启用、真实微信旅程与 production release 均重新等待两位真人教研签发；不得用本地测试绿灯替代该人闸。

### 2026-07-20（11 包全量修复 · owner 指令"全量修复,40 包最终全上线"）
- **[终态]** 40/40 包 supply_ready、签发题 316、题池 641(补题 8 道)。三类修复:①短卷补题 4 包(C02/N02/F16/F02 各 6→8 题,新题全部教材/真题逐字锚+算例复算);②源病 6 包(S02 非常规限定词、S01 分档表/50m门/垫板、X01 五条清单+围挡限定、B02 JGJ120 七因素、F05 止水环改题、G03 超灌口径+坍孔病谱)——编译源逐字回填共 10+ 处采分点,全部带 repair_note 溯源 2026 教材 chunk;③A01 算术病(2017 真题金标裁决 30.5<30.8 不合格,叙事链 12 处改对)。
- **[教材仲裁三判例]** S02:教材**有**限定词→修编译源;F05:教材**无**止水环机理(全书"渗径"0 次)→改题不补锚;S01:教材**无**"立杆步距≤Xm"数值限值→废编造数字改垫板题。原则:编译源修复只许教材原文逐字,教材没有的事实宁改题不造锚。
- **[对抗核验二连抓]** 第一轮抓 A01 q16 算术+G01 q2 干扰项与教材打架;第二轮(修复后)抓 S02 q1/q3 衍生病——编译源修干净后反照出已签题仍教旧错规则(10kN 丢限定/300kN 安拆口径误用于吊装),外科重写+008_0011 采分点镜像修复+q2 口径调和后重签。**教训:修编译源后必须回扫消费该采分点的全部已签题。**
- **[测试世界观切换]** 40 包全签后 23 个测试红:pending 示例类 15 个改**合成 pending 夹具**(深拷贝真实 authority 重置治理层+过生产校验器,fail-closed 契约零削弱);计数 633→641;autocrlf 假阳=stage 即绿;reachability 全域测试改覆盖对账(ready+gated=total)。357 全绿。
- **[工具治本]** prefill TOP_K 3→5(B02 q5 真锚 0.004 分差实测救回);sign 脚本盖章后重算 packet eligible_count(PR#533 手术病根治)。
- **[遗留]** A01 teach 面(视频+lesson.mp3 配音)仍教旧算术错,需 TTS 重录战役;A01 q10 重写后未入签发池(池已够 8);F05 编译源 quote 字段时序化改写存量问题;N02/F16 等新题的 fig 复用既有图形,未画新图。

### 2026-07-20（练习签发全量清尾批2 · owner 指令"全量清尾,简单给 Opus"）
- **[战果]** 20 个未签发包逐包裁决:**GO 9 包**(F03/D14/E05/D12/G01/N03/K01/Q03/S05,各签 5 投影 anchor+1 fact 三件套,supply_ready 全断言)→ 上线态 20→29 包、141→210 签发题;**NO-GO 11 包**全部留档解锁工单。
- **[NO-GO 分型]** ①题量墙 4(C02/N02/F16/F02:6 题短卷,eligible≥7+三件套数学不可达;锚已核好,补 2 题即签);②源病 6(B02 q4 全库无采分点+TOP_K 挤出真锚;F05 q6 止水环机理无源;S02 编译丢"非常规设备"限定词致答案与本包教材冲突;X01 编译源未重编译+knowledge_card 冒充教材引文,签了教考生丢分;S01 编译截断病——采分点 quote 在"应符合下列规定:"处被切掉分档表;G03 超灌口径 2016 官答 0.8-1.0m vs 2026 教材≥1m 冲突+灌注桩场景拼装预制桩病谱);③对抗核验缓发 1(A01 q16 源资产算术错误:(28.5+31+32)/3=30.5 源写 30.8"恰为临界",投影题不可剔,整包回退 pending)。
- **[流程]** 机器锚候选(prefill)→逐包裁决 agent(Opus 17+Fable 4,引文回原文核对+计算复算,锚必须出自机器候选 provenance 硬门)→定向对抗核验(11 风险点,抓 2 CONFIRMED:A01 q16 算术、G01 q2 干扰项与教材打架已微修重签)→publish+check+314 测试绿。
- **[owner 曾问"直接全签不就完了"]** 本批实证回答:盲签会把 X01(教丢分口径)、S02(教材冲突)、A01(算错数)带病上线;签发章语义=答案教材为真+锚可溯源,与选项形态修复正交。
- **[工具级发现]** ①audit-packet 生成器是决策保留型(对已签 packet 往返写回,不是重置)——真回退 pending 必须先删 packet 再生成(A01 处置实测);②prefill TOP_K=3 会把仅差 0.004 分的真锚挤出候选(B02 q5/S01 p3.q14),待上调 TOP_K 或 per-item 机制;③S05 历史退批重裁翻案:退批 fact 与签发集零交集,维持退批≠永久封禁。
- **[遗留]** S02 q14 单股铜线 vs JGJ46 编织软铜线口径移交编译线;G03 q5 辅助采分句真锚挂错题名下;X01/S01/G03 解锁都指向同一根:编译管道 quote 截断/压缩病,一次重编译可批量解锁。

### 2026-07-18（随堂练选择题反可猜性全量战役 · owner 指令"最长即答案/全在A"）
- **[病灶量化]** 633 道单选(40 包):78% 正确项严格最长、100% 存储位 0、8% 干扰项带口语破绽词("就够了/看着定"类=免费排除法);渲染层 41/43 播放器有洗牌,但存储层数据后期要被练习模块复用,必须治存储层。
- **[修法]** 40 包并行 agent 语义重写干扰项(题干/model/正确项/code/tempt/lose/fix 逐字节冻结,快照机械断言)+ 确定性目标位重排(surface 内四位均衡);新工具 `scripts/scan_luban_practice_option_defects.py`(可复用门禁,--assign 给目标位)与 `scripts/migrate_luban_practice_review_packets.py`(签名按 (surface,source_index) 稳定键迁移,断言 stem/model/正确项不变+supply_ready 不降级)。
- **[终态]** longest 78%→9%、pos0 100%→25%(分布 160/156/158/159)、口语破绽 8%→0%、长度带 58%→100%;20 上线包 141 签名迁移重签(supply_ready 逐包不变);publish --practice-only --check exit 0;pytest luban_lesson 301 绿;141 签发题四组异模型对抗核验。
- **[偏离]** ①56 题保留"正确项严格最长"(长采分句正确项结构性超长,强行注水会造第二处错误,各包 ≤25% 预算内);②个别 tempt 引用本为转述非逐字,维持与改前同等保真;③S07 播放器有"正确项永不显示在 A 位"的运行时反向偏置,播放器 JS 冻结未动(跟进项);④公开练习页 `ok:true` 答案键仍嵌在客户端(架构病,Codex 已设计 server-grading seam,另立战役);⑤variant_id 全量更换,在途练习会话按设计 content_updated_retake 重取,历史学习证据引用旧 id(生产 cohort 仅 N01,爆炸半径小)。
- **[教训]** variant_id=内容哈希,改选项文本必须"迁移 packet→再 publish"而非直改 authority;Codex 前役之败=机械正则批改(改坏题干)+未理解签名链 fail-closed。

### 2026-07-18（PR#521 CI 红 · chat 渲染器变更传导 practice 签名供应链）
- **[意外爆炸半径]** markdown.js 被 practice 发布器打包进答题卡 runtime(publish_luban_preview_cards.py:90)——改 chat 渲染器 → runtime digest 变 → 41 包投影 fail-closed drift + S05/X01 签名包身份失配,api-contract 分片红。**前端渲染器与 practice 供应链存在隐式耦合,改 markdown.js 必须连带全量重发布**。
- **[收敛顺序(踩出来的)]** publish 写模式在 packet 失配包上跳写 → 正确序=publish→migrate_packets --all→**再 publish**→manifest→check(exit 0)。漏第二次 publish 就永不收敛(authority drift 滚动出现)。
- **[签名资产核验]** _variant_bank 零改动;packet 仅重钉 source_bundle_sha256;X02/X03 7 签名 rebuild-safe carry 完整穿越;S05/X01 本就 signed=0。autocrlf 字节测试红=再生成文件未入 git index 的假阳(测试走 checkout-index 往返),stage 即绿。
- **[存疑记录]** packet 迁移工具 migrate_luban_practice_review_packets.py 是并行会话**未入库**脚本,我消费其产物(数据以入库校验器 --check 绿为准);其缩进风格与原 packet 不同造成大 diff,该脚本入库时若重刷会再churn一次。83 文件重发布随 PR#521。

### 2026-07-18（问鲁班结构化讲解双保险 · owner 拍板 10d 终态 PR#521）
- **[owner 流程]** "还是很普通,为什么不用第十版"→ 我出目标终态 HTML(手机 mock+逐块✅/🔶/⏸标注)→ owner 拍板"就按这样做"并问"输出内容能匹配吗"。
- **[匹配三层定性]** ①已匹配:结论/易错点小节(模型现产)+引用块金句;②管道全通生成端未约定:渲染契约本就有 structured steps,缺 skill 约定;③禁止匹配:错因×3/个性化提醒=学情真数据,模型编=自铸真值红线,等后端投影。
- **[双保险落地]** 生成端:construction-exam-tutor 加「排版语义约定」(### 第N步·标题/引用块金句/==采分关键词== 限3-5处),源+workspace 双拷贝同步(workspace gitignore 不入库),**test2 生效需随下次部署**;渲染端确定性升格:markdown.js ==mark==→朱红下划线 inline+「第N步」heading→stepLabel 字段,chat 步骤头竹青徽章行,行内代码底旧蓝→竹青;fixtures 加 structured_10d_teaching 全要素样例(devtools debugLoadMarkdownRegressionSample 一键复现)。
- **[验证]** parse 单测+110 全绿;fixture 走生产渲染器活体截图=目标终态 HTML 逐块对齐(朱红章/步骤徽章/朱红下划线/金句卡/裸章同屏)。
- **[余量]** 个性化投影契约草案(错因联动/三键/已带入 chip)待写给后端排期;skill 约定的真实模型遵循度待部署后live验证。

### 2026-07-18（问鲁班朱红章头像行 · owner"感受不到"复盘 PR#520）
- **[owner 两连反馈]** ①"感受不到"——定性:PR#519 当时还卡 BEHIND 未合,owner worktree 没有改动;合并+清 WeappCache+重开窗口后给出"看哪里"对照表。**教训:说"完成"前必须核对 owner 可见面已含改动**(devtools worktree SHA+缓存)。②"和原来差不多?没用第十版?"——如实答:骨架早是 10d 基础语言,缺辨识度元素;分三类(纯样式可做/等后端投影/owner 已后置),owner 拍板补第一类。
- **[朱红章头像行]** 助手消息 60rpx 朱红章+左上小圆角气泡(8/32/32/32)贴章;气泡双层阴影;操作行/导练卡缩进 78rpx 成三级纵向层次(434e148a1)。
- **[review 收口抓到我的真 bug]** 金句卡改造时 `.bq-line{display:none}` 把引用**正文**藏了(bq-line 是内容行非装饰线)——并行 review 提交 e5a43a6f1 修复+callout 明暗 token 化。**教训:改渲染器样式前必核类名的语义(内容节点 vs 装饰节点),display:none 高危**。
- **[验证]** 110 全绿;活体截图朱红章+贴章气泡+裸章+真加粗同屏。

### 2026-07-18（问鲁班对话面 10d 精修 · 渲染断链接线 PR#519）
- **[owner 指令]** 系统性优化问鲁班对话 UI/UX 含渲染模块,参考 10d,细节自裁。先派 agent 测绘 chat 三层叠罗汉结构(基座=几何/paper=配色,10d repave 契约测试在案)。
- **[渲染模块两处真断链(数据侧早就绪,渲染层没接)]** ①列表项 rich nodes:markdown.js 616 早产出 li.nodes(加粗已解析),wxml 只画 li.raw → 用户看裸 `**` 星号,接线 rich-text+raw 保底;②callout 空体空框:小节标签(结论/易错点)content 空时仍渲染带边大卡、正文漏框外 → bare/has-body 分型,空体=裸章胶囊,有体=竹青/赭左轨软卡。活体 page.data() 死证驱动(contentLen=0/hasNodes=true)。
- **[10d 版式]** 处理摘要完成态→一行思考细条(副行/核对计数移入展开态);引用块→金句卡(宣纸点阵舞台);发送钮→圆形墨钮↑(停止=朱红圆钮);callout 胶囊化。
- **[编译缓存坑第三次复发]** 改后截图三轮"数据对渲染旧"(裸**依旧/▶依旧),清 WeappCache(77M)+重启 DevTools 后全部生效——**改 wxml/wxss 后截图验收若与数据矛盾,先清缓存再怀疑代码**。
- **[验证]** 110 全绿;历史会话回放+真实发送流式全程(QA 打 test2)截图:加粗零裸星/裸章/圆钮/流式光标/停止钮朱红圆全对。

### 2026-07-18（tab 壳明暗与页面统一 + 主题默认暗残根拔除 PR#513）
- **[owner 报障]** history 亮页配黑 tab 壳。根因=主题统一战役(PR#507)漏了壳:custom-tab-bar 自解析 `getTheme()`(默认暗),而 chat/history 的 syncTabBar 载荷没带 isDark(learn/report/profile 带了)——冷启这两 tab 壳落到自解析默认暗。
- **[举一反三拔残根]** 全包 grep "默认暗"解析:壳自解析→getThemeOr('light');chat/history 载荷补 isDark;helpers.getTheme()/host-runtime.getTheme() 默认 dark→light(零调用者陷阱函数,防回潮,注释载明禁改回)。顺手清 history 残蓝(入口提示条蓝底蓝字/tag-blue 亮层)。两契约测试断言对齐。110/110 PASS;清空主题冷启 history 活体截图=页面与壳同宣纸亮。
- **[教训]** 主题类战役的收口清单必须含:页面 js 解析 + **组件自解析** + **sync 载荷完整性** + utils 兜底默认值——四处任一漏都=明暗打架。

### 2026-07-18（答题卡亮态隐形治本 + paper 覆盖审计工具化 PR#511）
- **[owner 报障+举一反三指令]** 摸底测试答题卡未答题号亮态隐形(白字白底)——系统病第 N 例:基层暗色字面量只被 paper 层盖住部分状态。治法升级为**工具化审计**:脚本解析每页 wxss,基层含浅色字/白系玻璃底的选择器逐一核对 .paper/.light 覆盖(scratchpad/audit-paper-coverage.js)。
- **[清扫结果]** assessment 27 缺口(答题卡+深报告 dr-* 全系)/chat 15/history 4/practice 1 全补;retest/gauntlet/station/errorbank **零缺口**——纸墨原生单层页免疫,反证叶子页整文件重写路线正确。assessment 基层蓝紫渐变/选中态/主按钮一并换 token 断根。
- **[审计工具双盲区(方法论教训)]** ①覆盖存在性≠色板合规:recommend-reason 的 .light 覆盖存在但值=旧蓝 #2563eb,查覆盖不查值会放过;②白字配实色底(seethrough 对错徽章)是合法搭配,纯正则会误报——工具产出必须人眼复核。first-run 51 条标记为待视觉复核(07-12 人眼验过亮态,疑选择器尾链匹配误差)。
- **[验证]** 110 测试全绿(history 契约 conv-action-btn 断言由字面量对齐 token);答题卡亮/暗双态活体截图(QA 账号真实开卷),12 题号全可见。

### 2026-07-18（设计文件夹=样式+逻辑双权威 · 导学收编+逻辑对照审计）
- **[owner 指令]** "全按《微信小程序前端设计》的样式和逻辑"。样式面收尾:导学电影流(此前 cinematic 例外)收进纸墨——文件夹无导学屏,适用「缺失屏同风格补」;「黎明将至」世界观翻译而非推翻(夜宣纸起幕/朱红+赭金太阳弧/天际光竹青夜→赭金→朱红→宣纸亮逐幕升温),keyframes/时序零改动(PR#510)。至此全包无深蓝残留。
- **[逻辑对照审计]** 派 agent 拿评审要点 9 条规则逐条对照实现(静态+行号证据)。达标:learn 首屏契约/三种历史归属/四禁词零命中/风险档位词/朱红四处纪律(两处 borderline:chat 停止钮红底、learn 舞台角标,可接受)。
- **[当场治本]** 规则8违例:mastery 降级路径前端用章节均值自算总体掌握%+组均分——铁律"前端不算分"。修=降级 overall=null/'—' 诚实展示,主路径不变(931f3980e,随下个 PR)。
- **[待 owner 裁决的缺口]** ①规则3 chat 答完三件套只落 1/3:「加入今日任务」后端无投影、「拍照批改」**owner 已另行拍板后置**(代码注释在案)——文件夹"必附"是否降级请确认;②规则4 错题本缺「按采分点」组织轴(现有错因/母题/待复习三轴);③规则7 mistake-book「标记掌握」一键直标 mastered,与 D17「我会了=触发换皮挑战非直标」相左——改深链复测涉及复习闭环行为,需拍板;④chat「我会了→换皮挑战」等后端投影。

### 2026-07-18（明暗主题单一权威 · 亮全亮/暗全暗 PR#507）
- **[owner 反馈]** "亮色模式下有的页暗、暗色模式下有的页亮,混乱"——盘点确认主题权威碎片化三类:13 页跟随 `isDark()`(未选默认**暗**:chat/billing/history/practice/assessment/feedback/legal/mistake-book/register/luban 四页)、3 页跟随 `isDarkOr("light")`(默认亮:report/profile/attempt-detail)、12 页**写死**亮色(learn/luban 五页 js 写死 false;登录四页/first-run/seethrough root 写死 paper light——外观选暗也纹丝不动)。
- **[收权]** 全包统一 `helpers.isDarkOr("light")`:未选=全亮/选暗=全暗/选亮=全亮。C 组夜宣纸暗版 wxss 本就在(历次注释"仍在"属实);learn 为 tab 常驻页补 onShow 重读;auth 四页补 `.paper:not(.light)` 暗态收口+login.js 天光内联双调色板;mistake-book 亮层旧蓝残留(蓝 kicker/蓝重试钮/冷蓝底)全量换 token——该页此前默认暗,亮层从未被人眼验过,正是"默认翻亮须逐页核 .light 完备性"预言(07-12 待办)的实证。
- **[测试]** 25 个测试沙箱 helpers stub 补 isDarkOr(07-12 同坑重演,mock 形状五花八门逐一补);light-theme 契约两断言对齐新语义+danger 色对齐 --pk-warn(赭红警示纪律)。110/110 PASS(合 main 后复跑)。
- **[活体验收]** automator 明暗矩阵 11 张人眼核对:learn 夜宣纸驾驶舱/teaching-points 课程架三色海报/review/concept-cards/chat 双态全对;动画卡宣纸舞台按设计保持原色不随主题变;中途 QA token 失效被截图暴露(learn 截成 login 页),重注入后复拍——截图落地页路径必须核对,别信"截了就是那页"。
- **[范围外(有意)]** onboarding 导学电影流保持深夜蓝黑舞台(一次性 cinematic 资产,同动画卡炭黑壳例外);老蓝壳主包(freeCourse 等)不属五模块面。

### 2026-07-18（我的树二三级收尾:登录家族四页纸墨收编 PR#505）
- **[审查结论]** owner 问"我的二三级还需要优化吗"——billing/feedback/legal/attempt-detail 已在 #503 收编;剩余深蓝残留=login/manual/reset-password/register 四页(旧 Zentra 深蓝营销风)。按 owner 既定惯例「缺失屏按第10轮定稿同风格补,不另起炉灶」收进纸墨。
- **[改法]** 四页 wxss 重写 --pk-* 单层(root 挂 paper light,登录场景固定宣纸亮不随夜间反转);布局几何/电影感入场编排/视差 orb 全保留。品牌=白 logo 落朱红章+点睛词书法朱红(动画卡同语言)+主按钮墨色。**隐蔽残留**:login.js 视差引擎把蓝系天光渐变硬编码为内联样式压过 wxss——js 换纸墨暖调,几何/呼吸不动(首截图人眼抓到,automation 死证)。
- **[验证]** 110 node 测试全绿;automator 四页截图人眼核对(含天光修复复截)。register root 原有 isDark 切换改固定 paper light(单主题页)。

### 2026-07-18（"学情又变简单版"虚惊定性 + 游客态承诺兑现 + 全链上 main PR#503）
- **[虚惊定性]** owner 报"学情又变简单版,是不是没同步"——磁盘/分支/commit 全在,真相=DevTools 重启丢登录态→游客模式把 10e 卡全藏,只剩引导卡;叠加本地后端 8001 未起→快速登录必失败。用 QA 凭据打 test2 注入 token 复原完整版(现成 run_wechat_devtools_page_automation.js 的 env_http 路径)。
- **[游客态治本]** 直接原因收敛:guest 卡承诺「只展示模块结构」但结构全隐藏——改为游客渲染完整 10e 结构(空态口径不造数),仅行动键留登录门(7d375d37);guest paywall 审计测试口径未动,全绿。
- **[误诊收回]** 前日报的"登录失败静默"不成立:login.js 全链路有 errorMsg 内联反馈,automation 点不动 open-type 真手势按钮才显得"无反馈";不做盲修,真机若复现再按具体路径治。
- **[合 main]** owner 指令上 main;origin/main 已被并行会话推进(#501/#502),干净 worktree(~/deeptutor-merge-wt)merge 零冲突,合并后双套件复跑(wechat 110/110 + learner_state 598)全绿;直推被 branch protection 拒,走 merge 分支 PR **#503**(自带最新 main,免 BEHIND 循环),已合并 f2d1c89ab。
- **[第二次"没同步"虚惊=DevTools 专用 worktree 落后]** owner 的 DevTools 项目根不是主工作区,而是 `~/worktrees/deeptutor-devtools`(branch main)——#503 合并后它没 pull,停在 #502,故模拟器仍是 B5 旧版(紫返回键)。已 ff 到 f2d1c89ab 并 cli open 触发重载。**拓扑教训:合 main ≠ owner 可见;devtools worktree pull 应并入每次 main 落地的收尾清单。**

### 2026-07-17 晚（消费链部署上线 + 活体验证抓真断链治本 · PR #500/#501)
- **[owner 两指令即时落地]** ①「继续学习改继续练习,主要练教学视频后面的练习题」→ PR #500:learn_next 任务在该站练习池已签发时 ctaLabel=继续练习、直接路由 retest forward(633 池);未签发站诚实回落进站讲解(禁空头按钮),供给真值仍由 `_practiceKindFor` 单点裁决。②「轻练模块不通」根因=owner DevTools 跑的旧前端+服务端旧代码,非接线缺陷(活体已证轻练进 forward 不再 toast)。
- **[部署 857be72c]** 全量 deploy 两次 SSH 断线(一次杀构建/一次断在 Recreate 致容器停 Created,手动 --no-build 拉起收尾);五层核验齐:host/容器 SHA 一致+容器内 confirm_facts_ready×3+变体资产 19 件在场+healthz/readyz 200+observability 通。`LUBAN_VARIANT_PROBE_ENABLED=true` 已进容器(.env 有备份)。
- **[活体验证(QA 零学情账号,截图 lc-01~09,live-chain-verify.md)]** 下游逐环健全:forward 5 题 MCQ(compiled 来源)→服务端判分收据→confirm 按钮真门控(全对不亮=诚实负例;答错亮,4/7 交集吻合)→签发变体判断会话(signed_variant 来源,教材溯源)→完成回执。**抓到唯一实链断点**:确认按钮整串 encodeURIComponent 把分隔逗号编成 %2C,接收端 split(",") 拆不开→0 题(同一分钟三形态隔离实验死证)。
- **[治本 PR #501]** 双侧收口:发送端逐 fact 编码+字面逗号;接收端提取 `parseConfirmFacts` 有界解码(≤4 跳,同 #492 桥接教训),兼容已解码/单次/双重编码;行为级红测试重放死证三形态+禁整串编码断言(vm 沙箱 realm 数组原型坑用串比较)。
- **[复走终证 PASS]** 真按钮 `.rt-cc-link` 全链活体闭环(2cc9ac969):答错×5→收据→点按钮→`confirmFacts` 拆开 4 元素零 % 残留→signed_variant 5 题→完成→独立 canonical 回执 `terminalEventId=3bf464eb…`;判分序列与 expected_ok 完全一致。同账号同按钮修复前 0 题/修复后 5 题对照在案(live-chain-verify.md「复走终证」节)。注:复走时段模拟器截图子层 wedge,断言以页面栈 dump 为 ground truth;同页面 UI 人眼截图有上午 lc-04/04b/05(#501 不改渲染)。
- **[待办]** 真机复验(owner 上传后);S05 MCQ fact_id 签发(该站 confirm 才能亮);变体判断会话 feedback 字段 null(temptation/loss_reason 未透出,门道由 correct_statement 承载)=内容形态观察项,归消费增强。

### 2026-07-17（变体消费接线切片 · 轻练当场确认 + D+3/D+7 抽查 · PR #499)
- **[接线]** 签发变体判断题(S05 68/N01 40 eligible)接入两消费点:①**错后当场确认**——`retest-items?confirm_facts=…`(forward,immediate_confirm 角色,≤5 facts),compiled forward 响应新增 `confirm_facts_ready`,收据错题与之有 fact 交集才亮"错题当场确认"按钮(同页新会话);②**D+3/D+7 抽查**——review 档 `state∈{weak,stable}` 先试 d1_probe 变体,空则退 compiled MCQ 不空窗,`fresh`(D+1 首验)恒走 anchor MCQ。实施顺序 registry T2→服务层三纯函数→writeback kind-aware→router→前端,五步五 commit(d58970b4→6e2a1b3f),每步绿再进。
- **[单一权威红线]** 供给只经 `resolve_variant_supply`(绿灯闸:projection_green ∩ manifest sha ∩ signed ∩ blocklist),生产 diff 零旁路(主控独立 grep 核);writeback 按 selection token `supply_kind` 分派不重跑路由;`luban_variant_decision.v1` 升 T2(36→37/176→175,full 221 不变)。
- **[灰度]** `LUBAN_VARIANT_PROBE_ENABLED` 默认关(register-before-use),合入零线上行为变化;开旗标 + QA cohort 活体走完 confirm/D+3 两链才宣称"打通"。
- **[验证]** 实施 agent 1069 绿;主控独立复跑 1107 绿 + CI 同款 contract guard 过 + `test_variant_probe_consumption.js` PASS + 旁路/kind 分派抽查。偏离 2 条(writeback 测试 autouse pin 保 35 条 legacy 用例走原路径逐字节不变;review 场 practice_source 既有口径不动)记 wiring-progress.md。
- **[边界(如实)]** S05 全程 fail-closed(compiled MCQ fact_id 全空串,治理字段未签)——S05 MCQ 签发+fact_id 回填归内容侧切片;N01 唯一活体 pilot 且 MCQ∩变体 fact=4/7,非交集错题 confirm 入口诚实不亮;decision 无 fix 字段不造。

### 2026-07-17（UI 真机行走审查终报 · 三任接力 78 图 · 5 SEV 候选)
- **[方法]** automator 逐页驱动真实 handler + 截图 + page.data() 死证;三任 agent 因 API 中断接力,分段落盘纪律(report-partial.md 先落盘再前进)使接手零损失——owner 同日立"subagent 必须增量落盘"为常设纪律。终报=scratchpad/artifacts/ui-walk-final.md;与静态审查 361 点合并。(注:本条曾被并行窗口写账本时覆盖丢失,已重放——共享账本并发写是真实风险,主控写后必须回读核在。)
- **[SEV 工单 5 个]** ①chat 停止会话重开丢助手已渲染内容;②智能模式停止后 trace 无终态(90s 无 final);③report 学情依据 0/0/0 与主视图"17 道有效作答"口径矛盾;④**billing 间歇降级态套餐区消失+无重试,购买链路不可达(唯一直接触收入,最高优先级)**;⑤错题回路 knowledge_point 字段泄漏 prompt/会话主题串("用3道题训练水泥"等)——写入侧数据治理病,呈现层原样渲染,信任杀手。
- **[坐实与亮点]** assessment「看依据」「筛选错因」死按钮活体坐实(md5 相等+delta 0);luban/handoff+seethrough F16 五关全链 PASS(教材溯源/暖纠正/证据入账),内容质量标杆;四禁词用户可见 wxml 0 命中。
- **[审查盲区(如实)]** web-view 内 H5 交互全盲(automator 限制);SEV④ 无稳定复现条件;QA 账号数据分布≠真实用户,SEV⑤ 真实污染率未知。

### 2026-07-17（学情二三级内容逻辑审计 · owner 问"点进去内容有没有逻辑错误"）
- **[F1 已修]** 零证据洗白:后端 `_build_long_term_analytics` 把 `recurrent_count==0` 无条件译成 improving——零数据账号同屏出现「反复出现的错因在减少」vs「暂时没有反复出现的错因」vs 风险环待评估三重矛盾(活体 page.data() 死证)。治本=零薄弱点+零复发→空方向,前端既有 fail-closed 兜底文案接住;测试洗白契约改写+新增有据 improving 用例,learner_state 598 passed(16571271b)。
- **[F2 待 owner 裁]** 双掌握权威同屏:10e 主面掌握地图=pack_lifecycle(41 站,QA 富态下 0 点亮),map 详情视图四态统计+总体掌握 40%=mastery dashboard/radar——**两套 universe 共用同一套「稳了/再看一眼/待复验/未学」词汇**,用户必读成矛盾(0/41 vs 40%)。候选修法:详情四态改投影 pack_lifecycle,或换词汇+标注口径。属产品级收权决策。
- **[F3 旧案再证]** 富态下 primaryFocus/headline=「重点关注 第1次练习」——ui-walk SEV⑤ knowledge_point 写入侧污染在学情头条再现,呈现层原样渲染,等写入侧治理。
- **[F4 非 bug]** 41 站全未点亮与 34 次练习并存=诚实呈现(对话/练习面不推进站点旅程 lifecycle);但空态文案「完成一次学习或作答后点亮」对此类用户有误导嫌疑(他们确实作答了),文案微调候选。
- **[环境噪声(如实)]** 本地后端间歇降级致页面在「缓存富态↔实时降级态」间翻转(degradedHint 如实提示);数据丰富态截图=缓存快照,降级态多源 0 值与主面空态口径一致,未见新矛盾。

### 2026-07-17（学情主面恢复 10e 诊断单 · owner 拍板推翻 B5 三件事精简）
- **[owner 反馈]** "学情怎么变得这么简单了，我还是要原来第十版 10e 的样式和内容；前几天还是这个版本"——考古确认:10e 诊断单主面 a8ce2979 实现、61aaf9a2 迭代文案，`d2e62d46`(five-tab collapse) 将其替换为 B5 三件事投影并删除 absorbDiagnosisIntoPlan。**数据管道从未拆**（riskGear/diagnosisHeadline/trendNarrative/masteryMap 一直由 toReportPageData/_hydrateFromUnifiedReport 填充），B5 只换了投影层——恢复 = wxml 首页块还原 d2e62d46^ 终版 + 补回一个 handler（c3b2547a，同分支）。
- **[测试对齐]** test_report_layout 整文件还原 B5 前 10e 契约版（116 断言）；test_report_home_core_contract 保留 view-model 单元段、结构段从"锁 B5+反 10e"改锁 10e 骨架；test_interaction_hints 还原 10e 提示语断言。110/110 PASS。
- **[功能打通活体验证]** （owner 叮嘱"各个功能得打通，注意盲区"）automator 真实 tap 六条链路全通：唯一行动键→teaching-points（route.lubanStations 权威已收归此页，非断链）、完整诊断报告→evidence、地图绿格→station（非绿格 toast「即将开通」）、看章节强弱→map、错题本、看变化记录→progress。
- **[已知盲区(如实)]** QA 账号无学习数据：风险环=待评估、41 格全未学、错因结构空——数据丰富态（四态混合地图/折叠诊断单展开/趋势有向叙述）未在真实用户数据下过目；暗色截图 tab 壳未同步是 setData 绕过 helpers.setTheme 的测试手法产物，非产品 bug（07-12 已验证正常链路）。
- **[遗留问题]** B5 的 reportHome/buildReportHomeViewModel/goReportHomeTask 在 js 仍被构建但不再被 wxml 消费——是否拆除待 owner 定（若 B5 永久废弃应删投影，避免第二套主面 authority 潜伏回流）。

### 2026-07-17（学情/我的二三级页纸墨收权 · owner 指令"按设计稿优化二三级 UI/UX"）
- **[病根与治法]** billing/feedback/legal/attempt-detail 四叶子页 wxss 均为三层配色叠罗汉（旧深蓝基 + `.light` 蓝覆盖 + `.paper` 薄补丁），补丁没盖住的选择器就漏旧蓝（蓝选中卡/青蓝渐变环/靛蓝返回键/纯蓝小节标题/亮红账本数字）。按单一权威原则**整文件重写为纸墨单层**（wxml 类名不动，palette 唯一来源 `--pk-*`），report 页因收口层已较完备改走基层字面量原位换 token。分支 `feat/luban-report-profile-paper-ink-ui`（5c2e754c，已 push 未 PR，按"过程只 commit+push"惯例）。
- **[内容级修正（超出纯样式，保守小步）]** ①profile/billing「使用记录/按使用记录」伪行删除（两分支推同一条零信息行+恒 100% 假进度条）；②profile 摘要卡不再复读「剩余 N%」（明细在抽屉）；③report 降级提示 `note_assets` 补映射「学习卡片」（不再漏内部字段名）；④训练闭环徽标改 `title` 兜底，不再裸展 `action_type` 枚举（`diagnostic_probe` 曾直接可见）；⑤report 空态 emoji（📡/⚠️）改书法印章（线性图标纪律）。
- **[测试契约随行更新]** `test_package_feedback_page_contract` 原断言锁死旧深色玻璃字面量（#f8fafc/#cbd5e1）——设计权威已是第10轮纸墨定稿，断言改锁 paper-ink token + 禁旧色字面量（意图"标题可读/调色自洽"不变、不弱化）。全套 node 测试 110/110 PASS。
- **[有意保留]** 掌握地图"蓝环第五态"（#4a7aab，注释载明从对象蓝降饱和派生）不动；套餐营销徽标赭黄 #c99f3d 两处字面量（paper-ink 无 gold token）注释载明。
- **[验证与盲区]** automator 六页 + report 四个二级视图（setData 强切）before/after 截图人眼核对；盲区=登录态数据丰富视图（掌握分布展开/作答证据卡列表）未在真数据下过目，QA 空态为主。
- **[方法]** automator 逐页驱动真实 handler + 截图 + page.data() 死证;三任 agent 因 API 中断接力,分段落盘纪律(report-partial.md 先落盘再前进)使接手零损失——owner 同日立"subagent 必须增量落盘"为常设纪律。终报=scratchpad/artifacts/ui-walk-final.md;与静态审查 361 点合并。
- **[SEV 工单 5 个]** ①chat 停止会话重开丢助手已渲染内容;②智能模式停止后 trace 无终态(90s 无 final);③report 学情依据 0/0/0 与主视图"17 道有效作答"口径矛盾;④**billing 间歇降级态套餐区消失+无重试,购买链路不可达(唯一直接触收入,最高优先级)**;⑤错题回路 knowledge_point 字段泄漏 prompt/会话主题串("用3道题训练水泥"等)——写入侧数据治理病,呈现层原样渲染,信任杀手。
- **[坐实与亮点]** assessment「看依据」「筛选错因」死按钮活体坐实(md5 相等+delta 0);luban/handoff+seethrough F16 五关全链 PASS(教材溯源/暖纠正/证据入账),内容质量标杆;四禁词用户可见 wxml 0 命中。
- **[审查盲区(如实)]** web-view 内 H5 交互全盲(automator 限制);SEV④ 无稳定复现条件;QA 账号数据分布≠真实用户,SEV⑤ 真实污染率未知。

### 2026-07-17（变体弹药首批真实签发 · S05 74 + N01 40 · owner 委托裁决落地)
- **[签发执行]** owner 拍板委托("不用我拍板,你直接拍板")后由主控本体亲手执行(非 agent 代跑):`scripts/bake_variant_decisions.py S05 N01 --spec`,reviewer_id=`owner-delegated:claude-main-control:2026-07-17`,S05 74 条 + N01 40 条决策块烤入 `_{PACK}_variant_bank.v0.json`(identity 三链核对/整包 abort/幂等复跑 UNCHANGED 已验)。签发前提=四轮 Codex 异源对抗收敛(74+40 全 PASS,含 loss_reason 纪律头、S05 50kW 事实排除、N01 F 序补虚过度断言排除)。
- **[活体资格]** `eligible_variant_items` 实测:S05 68 条(74 签 − 6 extension 按设计不服务)/ N01 40 条;摘要门 fact-ready。分支 luban/variant-eligibility,PR #498。
- **[CI 连带两修]** ①schema 闭包 176≠175:先自证不变量(orphans=0/is_closed=True)再对齐声明(+`luban_variant_decision_bake_spec.v1`,175→176/220→221),playbook 顺序不倒;②`test_variant_audit_packet_writes_pending_decision_cards` 原断言"决策全 pending/eligible=0"已被合法签发推翻——守卫升级为**签名链断言**(74 signed 全部 owner-delegated reviewer + 64hex 签名信封 + checks 全真;1 条排除项保持零签名),守卫精神"机器绝不自铸签名"不降级。
- **[边界]** 本 PR 只落供给侧(签发+资格框架),不改线上行为;消费接线(轻练错后当场确认 + D+3 抽查吃 signed_variant)为下一切片,届时 `luban_variant_decision.v1` 升 T2。

### 2026-07-18（五 tab 加载慢治本:学情快照 SWR 收权 · 分支 feat/luban-miniprogram-tab-swr-perf）
- **[战役概要]** owner 报五大模块每 tab 都慢。根因=redirectTo 切 tab 全走 onLoad 冷启动 × `getLearningReport(100)`(后端 3-5s)被 learn/report/profile 三页独立裸拉 × report-cache 缓存孤岛只有 report 一个消费者。修法=快照组装收权(`utils/report-snapshot.js` 唯一 builder,report/learn 双合法写者经 `writeIfFresher` 写序守卫,profile 只读)+统一策略(页面进入缓存秒渲染+始终静默刷新)+history 归档切换走既有 SWR(apply 前 re-check tab 防串台)+preloadRule wifi→all+删 67K 零引用孤儿 canonical-taxonomy-members.js。第一轮 116/116 PASS 后过 high 档对抗 review(21 agent):**fresh-skip 门(age<60s 跳网络)四条 CONFIRMED 同根被整体删除**(钉死陈旧/降级快照+吞跨 tab 学习动作+时钟回拨永久压制),另修 history 串台竞态、report"正在刷新"撒谎横幅、builder 空对象归一化。叙事详见 methodology-log 同日条。
- **[偏离 1:profile 弱网保守渲染]** 陈旧缓存命中且静默刷新失败(双接口全挂)时,保留已渲出的缓存 routeCard 而非按旧行为抹回 null——严格"照旧"会让弱网用户先看到卡再闪没,判定为回归;已用测试锁定(test_profile_route_card_cache.js c2 场景)。
- **[偏离 2:learn 空态快照不上屏]** 缓存 hydrate 沿用 lessons 快通道的 `hasSupply` 门,空态快照不上屏(防闪空态),与任务书"命中即渲染"微偏离;report 无效时 builder 返回 null 天然不写缓存。
- **[偏离 3:report 页横幅诚实化]** 缓存 hydrate 后网络刷新失败时,「正在刷新，先显示上次学情快照」横幅原会因 `this.data.degradedHint ||` 短路而永久留存(main 既有病,review 发现 #5)——失败分支改为把该句替换成「网络暂时不稳，已显示上次学情快照」,真实降级提示保留。
- **[偏离 4:死代码 reader 未删]** report.js 四个零生产调用方的旧串行 reader(`_loadOverview/_loadLearningBrain/_loadRadar/_loadMastery`)因 test_report_snapshot_dedupe/radar_authority/radar_fallback 三个测试直接调用而保留;删除需连带重写这三个测试的入口方式,留作独立清理工单。同类:learn posters 瘦身经核查放弃(stations.js:127 是真实消费者)。
- **[已拦截的妥协]** report 页曾因只读测试约束保留与共享 builder"逐字等价的 fallback"(镜像 authority)——主控修 dedupe harness 映射真 report-snapshot 模块后删净,harness 内新增 readWithMeta stub 与常量。
- **[残余风险]** learn/profile 对 report-cache/report-snapshot 用 try/catch 可选 require(存量测试 harness 对未知 require 直接 throw 所迫),生产恒存在、缺席时降级为原网络路径;根治需统一 harness 白名单。chat 页三项(200 条消息大 setData/流式 O(n²) 重解析/表格逐单元格 rich-text)与 history 分页虚拟化为后续独立工单;后端 read model 3-5s 本体是根本税,前端缓存只遮蔽不消除。DevTools 回归见提交后记录。
- **[上线后复查实证(owner 令"再反思复查")]** QA 登录+automator 实测:learn 缓存 hydrate 在 live **3ms** 上屏(页面内时间戳),快照 owner/user_id 全匹配;首轮曾误判"未生效"——automator `reLaunch()` 自身解析延迟 ≈3.8s 伪装成渲染慢,**判 SWR 生效必须用页面内时间戳,不能用 automator 侧计时**。顺带实证 builder 空对象归一化真在跑(QA 账号 homeDashboard 缺失被正确置 null)。
- **[教学动画链审计+最小落地]** 专项审计(station/teaching-points/H5 资产):站点页两接口严格串行且 web-view 等两者才挂载(station.js:133,143)、H5 support.js→react 串行瀑布、705K 字体+220K b0.mp3 全走 origin 容器(luban-preview 218M 全打进镜像 Dockerfile:209)。本轮只落**进站 prefetch**(learn.openStation/teaching-points.openEpisode 提前发 detail GET,靠 requestStateGet dedupeInFlight 与导航并流,无状态零缓存);**明确不做** teaching-points 快照渲染——该页文件头章程"不缓存 episode 名单,fail-closed 宁可少展示"是防陈旧 active-set 撤题病的在案决策,perf 不得越权。backlog(需 owner 排期):S1 web-view 提前挂载(要改 H5 bridge ticket 时序)、S2 detail 响应直带 entry_ticket(后端契约)、H1 lesson.html preload react(改模板生成器+40 包重生成,须走 Animation IR gate)、H2 luban-preview 上 CDN+出镜像、H4 音频按 beat 预取。
### 2026-07-17 凌晨(QA 双缺陷修复上线 + 部署资产守卫)
- **[QA 双缺陷全闭合并部署]** ①桥接编码不对称(PR #492):`parseBridgeReceipt` 加有界解码兜底(直 parse→逐层 decode≤4 跳,双编码安全),DevTools 与真机 JSSDK 双路径均可用,1.7.19 已传;②首跑空处方遮蔽任务卡(PR #493):仲裁端"practice intent 无可路由 target 不得胜出"(fail-closed 落下一臂+skipped_intents 可审计诊断)+ 处方端候选序列(q1: F16→N01,q4: X03→N01,supply-ready 过滤无字面特权),630 测试绿+真盘 e2e;契约同步 learner-state.md。两修复随 main 部署(容器 ba832122→e80a0216)。
- **[镜像资产守卫]** 生产容器缺 `_variant_blocklist.json`(dockerignore 反选漏),撤题权威 fail-closed 挡完整作答面;排查顺手抓出同类第二漏(看穿 bank)。PR #494:补两条反选 + 守卫测试钉死"runtime 必需文件必须入镜像/build-time 审核件必须排除"边界;rebuild 部署后容器内文件确认在场(e80a0216)。
- **[遗留工单]** member_console 学习投影 4 条 main 既有红测(独立修);存量空 target intent 生命周期收口;`luban_variant_decision.v1` 在消费接线切片升 T2 并对齐计数;D+1 活体验证待自然跨天(QA 账号 400=诚实未到期)。


### 2026-07-16 晚(receipt SEV-1 生产修复 + 两线三轮对抗收口 + 调度纠偏)
- **[SEV-1:receipt 双写致视频五题全量死链,owner 真机首测抓获]** 生产 H5 内嵌 receipt(digest 22fe9552…,decision 合并前渲染)≠ artifact receipt(9e270564…,签发后重算含 ordered_source_sha256)→ 服务端全量 `content_updated_retake`。根因=publish 管道 receipt 两个计算时机(`_compile_practice_outputs` 先渲 HTML 后合并 decision)。治本 PR #489:单一来源重排(decision 定稿后从 authority 渲 HTML)+ `--check` 加"HTML 内嵌 receipt == artifact receipt"fail-close 断言 + 4 红测试;全 40 包重发布仅 n01 变(恒等性证明)。部署 fc497ad4(候选分支 release/receipt-fix-20260716;deploy 脚本拒 main 直发一次,正确守门)。**验收=真 receipt 桥接路径活体**:生产 receipt → retest-items 200/5 题/逐字节回显 → complete 200/terminal 真。
- **[QA 盲区教训]** 上线行为验收曾直连 API 未带 receipt 参数,恰好绕过真实用户必走的桥——发布检查表永久新增:**带真 receipt 的桥接路径活体测试**(owner 真机 > 一切绕行 QA,又一实证)。
- **[A 线学习页(PR #487+#488,已合 main,1.7.17/1.7.18 已传)]** 旅程轨道+训练/轻练/复习卡落地后,Codex 红队两轮:一轮 4 项 CONFIRMED(旅程假完成态/轻练第二处方/复习卡身份漂移/刷新竞态),二轮 A1/A2 PASS、A3/A4+一处合法态误杀继续收口(严格 === true+拒空、_reviewDueEntry 单一裁决点镜像服务端 resolver、goTodayTask 补 _refreshing 守卫、review 资格不借 forward 旗标)。收口以对抗者复现形状逐字段重放反转为验收。108 Node 文件绿。
- **[B 线变体资格框架(PR #490,三轮对抗)]** 设计=fact 人签+机器聚类候选、supply kind 保留 signed_variant、富化进 content_sha256;三轮:一轮 B1 治理字段签后可改/S05 48/75 REFUTED(模板无来源机理+判分承诺)/N01 6/43(fact 错挂);二轮 B1 签名信封未绑定/B2 绿灯旁路/B3 人审外观;三轮全部闭合(signature_envelope_sha256、_load_green_signed_bank 唯一 gateway、_packet_signed_appearance_failure 与 runtime 同谓词)。诚实边界:全套重算防御需真密码学签名,摘要方案如实声明。候选重生成 byte 确定,全 pending 零签名,签发待人闸。
- **[owner 调度纠偏(与"降低 F16 权重"同谱系)]** owner 点破 N01 隧道风险。裁决:结构无 F16 病(零专属分支+参数化测试钉死),但杠杆错位属实——S05/X01 对抗揭示的是编译管道级共病(压缩句冒充教材 quote/计数自铸/限定词删除/83% 长度泄漏/证据 OCR 损伤)。总纲:**下一战役=编译管道修复**(N01 工单并入批处理,不再单点雕刻);S05/X01 按工单轮入 cohort-2;立每周进包节奏指标(目标 8 月中覆盖高考频 15-20 包);学情页收缩与 D+1 触达随后排队。
- **[待办栈]** 学习页整页 10a 化(owner 定稿设计逐像素,→1.7.19;本轮只落了三模块增量,范围判断失误已认);变体消费接线(轻练/D+3,2-3 天);S05/N01 变体决策卡+委托签发;R487 学习页任务卡依赖 projection 数据,DevTools 无登录态时诚实隐藏(向 owner 解释过,非缺陷)。


### 2026-07-16（V1 最小上线收尾 · B1-B5 四纵切落盘 + B2 服务端回路收口 · 分支 luban/practice-v1-r0)
- **[跨 AI 交接]** Codex 军团(会话"简化复习并收敛学情模块")按 07-15 计划执行 B1/B2/B3/B5 至半程后由 owner 下停止令;Claude 主控冻结核验(mtime 静默 + 只读三方取证)后接管收尾。工作区 ~3000 行未提交改动按纵切拆为窄提交:`1e32a271`(B3 原子 probe claim + migration + 契约登记)、`7fbb0e2b`(B1 v3 资格字段 + N01/S05/X01 审核包 + exact receipt 供给)、`d2e62d46`(B5 五 Tab 收权 + receipt 桥前端)、`54e4e10c`(锚候选预填)、`1916e620`(红测试收口 + 收据四层诊断)、`aa681d42`(B2 服务端 receipt 回路)。
- **[偏离:数据盘点文件不入库]** 指挥官原令"数据盘点 260 文件单独 commit 隔离";实际处置为**完全不动**(含 `docs/营销/`、`.codegraph/`、3 个盘点测试)——因其他 Codex 窗口仍在活跃,这批文件疑属在飞工作流,commit 半成品会制造第二次"扫走"事故。待该工作流 owner 自行收尾。
- **[B2 断链根治 + 承重安全修复]** 真正坏掉的一等事实:H5 桥接的 `projection_receipt` 前端要求响应逐字节回显(retest.js:568-576),服务端从不接收/回显 → 桥接模式 100% 死路;`resolve_projection_receipt` 写了但零调用方(consumption 断链)。修法:receipt 作为身份输入穿过唯一 builder `build_retest_items`,路由 thin 只做 HTTP 映射;`content_updated_retake` → 409 明确语义;review 模式/非编译包/漂移一律 fail-close 不静默换题。**顺带发现并修复**:`resolve_projection_receipt` 原返回裸 authority items(options 含 `is_correct`),直接接线会把答案泄给客户端——收敛到 `_project_practice_rows` 单一投影,消灭第二题面形状。
- **[V1 发布裁决(经三专家+指挥官对抗)]** §6 的 R2-R4 统计门(7 日 A/A、powered A/B、join≥99%)整体砍除:真实流量 2-3 新用户/天不可达 powered sample,且 owner 07-10 已拍板"撤销 spike 统计验证路线改逐人回放"——本计划 §6 与该在册拍板冲突,以拍板为准。替代=确定性发布检查表(冲突送达=0/旧 H5 错位=0/probe 唯一 claim/真微信全链 QA/埋点 forward-review 判别)+逐用户回放。当场换题确认(probe_role 零消费)、订阅消息调度器(仓库无定时器)、fact 级 D+1 均推 V2;D+1 触达走学习首页任务位(链路已存在,只差 3 flag)。
- **[签发关键路径减半]** `scripts/prefill_practice_review_anchors.py` 机器预填 source_anchor 候选(纯标准库文本匹配,绝不签名,`machine_candidates_only` 独立文件):三包候选覆盖 100%(≥0.45 高可信 7/11/12 题),抽查 4 题全部精确命中;owner 签发从 ~3-4.5h 压至 ~2h。已知留观:三包固定 5 anchor 题 100% "正确项=最长选项"泄漏,首批记 verdict 不治本;签发后 `test_candidate_review_packets_are_complete_and_never_machine_signed` 的"全 pending"快照断言需同步改。
- **[发布门顺序]** eligible=0 时全链硬停发无回退 → 部署本身无风险(生产 flag 需先核实全关),但**开闸必须排在"≥1 包签发 + 线上活体核验 eligible>0"之后**;404 即关 flag 零成本回退。
- **[验证]** 合流回归 835 passed(luban_lesson+learner_state+endpoint+scripts);Node 106/106;PG 双实例并发测试真跑绿;ruff 全绿;收据页四层诊断(你选了/为什么像对的/为什么不给分/下次这样答)合同测试钉死含语气红线。未部署、未开 flag、未真机——R0 Engineering Candidate 达成,R1 真微信 QA 待部署后执行。
- **[签发 verdict 授权委托(owner 拍板)]** owner 2026-07-16 原话:"不用我拍板,你直接拍板,这个我都没你专业,你多考虑你的未知和盲区,也考虑我的未知和盲区"。处置:verdict 由 Claude 主控在"机器逐题核验 + 异源对抗放行"双前提下签发,`reviewer_id` 如实记 `owner-delegated:claude-main-control:2026-07-16`(teaching+scoring 双角色),不伪装 owner 逐题人审;S1a"agent 不代替签名"条款对本批被 owner 当次指令显式覆盖(用户当次指令 > 项目权威文件)。**对抗裁判按 owner 指令改用 Codex(异源)**,同源 Claude 证伪面板降为参考;Codex 推翻任一题即按决策卡预案换题重提。
- **[签发流水线状态(实时)]** N01 决策卡已出(`2026-07-16-n01-签发决策卡.md`,7 题=5 锚+q5 确认+q8 D+1,fact 三件套 n01-fact-critical-work-zero-float,机械核验全过,q16 正确项 1.50× 超长带注);Codex 异源对抗 N01 进行中;S05/X01 决策卡生产中(同构流程:出卡→Codex 对抗→签发转写)。转写工序:scratchpad 脚本按 spec 填 decision 块 → `publish_luban_preview_cards.py --practice-only` 合并回写 → `build_luban_pack_manifest.py` 登记 → `--check` 双校验 → `compiled_practice_eligibility_summary` 断言 supply_ready → 更新"全 pending"快照测试。
- **[集成与 PR]** origin/main 5 个提交(tutorbot/BI 线)已合入分支,唯一冲突 test_supabase_store.py(两侧同位追加测试函数)以"origin 版为基底+回植 HEAD 新函数"解决,合并后回归 798 passed;里程碑 PR #482 已开(merge 排在三包签发合入之后);contracts 的 password_change 旧红确认 origin/main 同样存在,非本分支引入,不顺手修。
- **[跨窗口分支污染 → 干净发布分支]** 主 checkout 被切到发布分支后,其他活跃 Codex 窗口的提交直接落在其上(631484c7 test-only 无害保留;2c723300 为 287 文件/6.5 万行数据盘点+observability 大提交,不能搭发布车)。按"干净 worktree 只 cherry-pick 自己块"playbook:新建 worktree /Users/yehongchen/worktrees/deeptutor-release-v1 + 分支 luban/practice-v1-clean(基线 f39832f3),cherry-pick 自己的 docs 提交;PR #482 关闭,改开 **PR #484**(head=clean 分支)。教训:共享 checkout 的分支切换会把别人的提交引到自己分支,发布线必须独立 worktree。
- **[N01 签发完成(cohort-1 第一包)]** 双面板对抗(Claude 证伪 + Codex 异源,owner 指令以 Codex 为准)后主控合议:两面板独立重解七题答案全部正确、零内容编造;Codex 的 7/7 REFUTED 中 5 题源于"逐字锚"硬规则(排版规范化,quote 只在决策卡不进 runtime,判卡诚实性问题非内容问题),其余转为带注 verdict + 4 条第二批工单(q3 题干"可得分"→"能拿全分"、q1 opt3/opt4 讲评打磨、q8"顺延"措辞、q16 干扰项增肥)。转写后 supply_ready=true(eligible=7、fact 三件套 n01-fact-critical-work-zero-float),快照测试改守"pending 全空 ∨ owner 责任链完整签名"新不变量,冲突包不变量测试换锚 A01/F03/G03,回归 801 passed(fcb07d3a)。
- **[S05/X01 双双退出 cohort-1(Codex 异源对抗推翻,主控教材终审确认)]** 首批最终 = **N01 一包**。S05:q2+q6+q7 fact 三件套不成立(编译源把"三级配电构成"与"送停电顺序"登记为两个采分点,归并=贴标;q6/q7 系送/停正反向表面改写,skeleton 三异不成立)+ q7 真题证据串题 + q3/q4/q18 共用五重重复截断的 2023 锚。X01:**踩硬红线**——教材原文为五条清单(第 3 条含供电供水排水、第 4 条含保卫),q2"最完整"正确项漏真采分点、q3 正确项与 model_answer 写死"只表达六项"(编译自铸计数+假全称),考生照此作答真题会丢分;q10/q14/q15 删"占据道路施工设置的"限定词+无市区前提判不妥;q2/q3/q4/q15 皆钉死锚不可剔签。**方法论确认:异源裁判再次揪出同源核验卡洗白过度的地方**(X01 卡曾裁"承重面不依赖计数",被教材原文推翻)。工单:S05/X01 病灶是编译管道级(知识卡压缩句冒充教材 quote/限定词删除/计数自铸/证据串题),下一 cohort 前先修管道再逐包重卡重对抗;Codex 两份终报的逐题放行前最低条件已在对抗记录中,资产本身经历过多轮历史对抗、零错误答案,未入选≠降级。
- **[X01 对抗附带发现]** eligibility 门函数只机械校验"同 fact_id + 3 skeleton 互异",不校验事实语义(任意 7 题贴同 fact 可骗过门)——门的语义正确性靠人审 verdict 兜底,这正是签发环节不可自动化的原因,记录为设计事实非缺陷。
- **[V1 生产上线完成(2026-07-16 晚)]** PR #484 合 main(c2e1f7f4)后全量 `deploy_aliyun.sh` 部署 test2:**SHA 三方一致**(host .env = 容器 env = c2e1f7f4,dirty=false)+ 容器内新符号 grep(receipt 路由 9 处/read_model resolve 3 处/probe claim 2 处)+ 公网端点与 observability 脚本全绿。**Supabase migration 手工应用**(host DB_URL 6543 事务池改 5432 会话池 + 本机 psql,两 RPC `claim_luban_retest_probe`/`read_luban_retest_completion_events` 活体确认存在)。**三 flag 终态全开**(REVIEW_MODULE/HOME_NEXT_STEP 部署前已在生产开着——部署即完成"不安全供给熄灭+N01 点亮"的切换;LIGHT_PRACTICE 由本次追加 host .env 并 recreate)。**活体行为验收**(容器内 TestClient 走真路由,qa_ 排除身份):N01 `supply_ready=true/eligible=7` 容器内断言;forward 五题发放 200;故意全错完成 → `score 0/5` + 五错题 feedback 四层(temptation/loss_reason/fix/correct_statement)齐 + `learning_change.authority=learner_memory_events→learning_synthesis` + terminal_event_id 真。未验收面如实记:D+1 到期复测未活体走(需自然次日;PG 双实例并发测试+RPC 已就位);**小程序前端(五 Tab/收据四层渲染)未到真机,需 owner 在微信 DevTools 上传发布**;host /tmp 曾被 scp 落两个只读 QA 脚本(写边界瑕疵,hook 拦了清理,留待手工删)。

### 2026-07-15（Practice 计划二次红队 + terminal/revocation authority 收权）
- **[release truth 翻案]** 633 道只能称“结构可判 compiled candidates”，不能称已完成内容签发的正式库存。当前 sidecar 缺稳定 fact/source/review verdict，原料盘点中 581 条 review-required、81 条 quarantine，且已知 A01/F03/G03 冲突可进入 compiled/public Practice。产品 P0A 保持 `HOLD`；S0 只代表本地事务基础设施完成。
- **[入口真值]** generic learning home 无 surface 时能消费动态私有池；视频 H5 却始终回传 surface + indexes，因此仍走 public 五题，并存在缓存旧 H5 与新供应错位的 TOCTOU。计划新增 exact question IDs + projection digest、v1 re-fetch 和真微信 auth-chain 阻断门；本轮不改脏前端、不声称入口已闭环。
- **[terminal 根治]** 新增唯一 `committed_retest_closure`：terminal 的 exact refs 必须在同 completion/request/pack/mode 下重核题数、分数和正确数。learning synthesis、typed graph、三层学情、report、pack lifecycle、prescription outcome 与 replay 共用闭包；partial/孤儿 item 不得因复用 completion ID 进入学习真相或移动复测时钟。
- **[读侧与撤题收权]** remote `learning_evidence` reader 复用 canonical classifier，durable completion claim 不再混进证据流。signed variant 的 available/count、selection、exact resolve、supply digest 与 pool meta 统一消费 active resolver；`_variant_blocklist.json` 缺失、损坏或 schema 异常时全链 fail-closed。
- **[Claude 对抗吸收]** 按 owner 指令以 `Review this code` 为首行、tool-less read-only diff 完成 Claude Code 复核。采纳非有限数可击穿 projection、损坏 item score 被合并为 0、远端 terminal 缺穿透回归、variant ID trim 和撤题故障无日志五项；逐项补 fail-closed/测试/日志。加权题意见收口为当前单选/判断二元 1 分 contract；历史兼容意见经 git 追溯否决——`completion_terminal` 首次进入 `origin/main` 时已与 request hash、item refs 和逐题分数字段同批引入。
- **[下一阻断]** S1 建 fact-level eligibility/revocation，覆盖 variant、compiled/public/private Practice、cloze、antidote、concept card、answer layer 与 questions_bank projection；S2 只做 F16“一题确认 + 一题 D+1”。未完成内容零冲突、exact H5 identity、multi-device probe claim、7 日 A/A 与真微信证据前不开 flags。
- **[验证]** learner-state + retest writeback/read-model/selection/review-due + API 相关回归 `680 passed`；新增孤儿/partial、NaN/Infinity、损坏/错类型 item scoring fields、remote terminal closure、remote control claim 与 revocation missing/corrupt/production-asset 对抗样例。contract guard、Ruff、diff check 全绿；未跑微信 DevTools，因为本轮刻意零前端修改，前端判断只算静态 code-path evidence。

### 2026-07-15（视频 Practice 全池释放 + exact issued set 收权 · local candidate）
- **[库存真值]** public HTML 继续展示作者精选五题，但 `luban_compiled_practice.v2` 私有 sidecar 改为保存全部结构可判单选候选：40 个 pack、43 个 practice surface、633 道（每面 6–24 道），不再把 215 个公开展示位误当全部供给。未完成 finished Practice 编译的 E01 继续 fail-close；是否可正式送达仍由后续内容资格门决定。
- **[选择收权]** 未显式指定 public surface 时，服务端按 canonical user + day 在同一签发面确定性取五题；显式 `practice_surface` 仍精确返回 public 同五题，保留 WebView 收据桥。selection v2 额外绑定 `supply_kind + supply_digest + exact variant set`；题池重签或停发后旧凭证失效。
- **[完成收权]** `RetestWritebackService` 不再重跑选题算法，而是精确解析已签发 variant IDs 后 server-rescore。真正的一等事实从“同样参数应该再抽到同样题”收紧为“完成只认当初发出的精确题集”。forward 仍是 L0/non-promoting，不改变 LearnerState promotion authority。
- **[幂等闭包]** hostile review 抓到 partial item 后可被另一合法请求接管的旧缺口；现于写题前用唯一 dedupe key 建立 durable completion claim 并绑定 `request_hash`，claim 后重读校验。terminal replay 只按 `item_event_refs` 恢复，并核 request hash、题数、唯一性与正确数；孤儿 item 不再混进成功收据。
- **[诚实边界]** 本轮未改小程序 UI、未启用运行时 LLM 出题、未部署。数据盘点发现 variant blocklist 与 cloze 等派生物存在撤销漂移；在事实级跨派生撤销 gate 完成前，关键词填空/半写不扩默认入口。实施与后续门见 [Practice × 母题库留存闭环计划](./2026-07-15-luban-practice-mother-bank-retention-loop-implementation-plan.md)。
- **[验证]** practice-only 重建与 check 逐字节一致；exact-selection/writeback 定向复测 `80 passed`，完整 `tests/services/luban_lesson` 加相关 API 套件 `131 passed`。该结论只支持 S0 infrastructure GO；二次内容/入口/authority 红队将产品发布裁决保持为 HOLD。

### 2026-07-14（全量练习闭环 · 专家红队后的可交付收口）
- **[源头可复现]** 首轮候选把 39 个 compiled sidecar/public 页面带进了分支，却只跟踪 8 个对应 finished 源，干净 checkout 无法重建。现改为精确跟踪注册表实际消费的 39 个 practice HTML；新增 `--practice-only --check`，只从这些源重编 practice/public/sidecar 并逐字节比较，不要求把 195MB 教学音频整库搬入本次变更。finished practice 以 `-text` 保证 Windows `autocrlf` checkout 仍字节一致；source-only PR 会触发 backend/governance，并在 CI api-contract shard 真跑同一重建闸。
- **[投影不可伪造]** manifest 为每个 private sidecar 固定 `authority_sha256`；运行时先验 sidecar 字节，再验 source bundle、pack、surface、source/public SHA 与 5 题结构。仅交换两个答案但保持 JSON 形状合法也会 fail-close；`luban_compiled_practice.v1` 已进入 schema registry，字段集合由测试与运行时常量对齐。
- **[缓存权威纠偏]** lesson URL 与 practice URL 不再共用一个 bundle SHA：前者绑定已发布 lesson，后者绑定注册 practice 源集合。chat 当前会话、pending turn、history/dashboard/report cache、tombstone、retest seen、闯关草稿、看穿进度、attempt 摘要、首跑 checkpoint 与头像全部经同一个 owner-scoped storage adapter，以 canonical user 为 key + envelope 双校验；无 user 时拒绝读写，防退出换号后串读上一位学员的 LearnerState 投影或自由文本。
- **[CI 与边界]** secret scanner 只豁免机器生成且由 digest 校验的 `compiled/*.practice.authority.json`，相邻源码/JSON 仍扫描；不是对整个目录树放开。未登记的 B02/D14/E01/N02 仍保持 unavailable，不以目录存在猜供给。
- **[根因复盘]** 真正坏掉的一等事实是“可发布练习是否能由当前仓库中的 finished authority 唯一重建”；争权点是旧分支源、生成 sidecar/public、副本缓存以及跨账号本地存储。修复通过补齐唯一源、钉住派生物、分离 lesson/practice cache identity，并把所有本地 reader 收进一个 owner adapter，减少而非新增业务 authority。

### 2026-07-14（finished 课后五题全量接入 · local code candidate）
- **[范围真值]** 不再以 F16 作运行时特判。publisher 只遍历 `STATIONS` 显式登记的 finished 习题面：37 个 pack、39 个 practice surface（S01 三个），每面确定性编译 5 道可服务端重判单选，合计 195 道。未登记的历史 HTML 与暂无 finished 卡的 B02/D14/E01/N02 都 fail-closed，不靠 glob 或猜测 URL 上线。
- **[两类 authority]** 题干、选项、正确答案与解析继续由用户指定 finished HTML 负责；构建时 compiler 按格式适配（Q/ord、Q/direct、POOL/deck、A02 bank）产生带 source/public SHA 的私有 sidecar。学生是否做过、本轮对错与后续复习仍只由 `RetestWritebackService -> canonical completion terminal -> LearnerState` 决定；HTML 本地结果只是即时反馈。
- **[公用链路]** 有 compiled 供给的站点都走 `finished lesson -> finished 五题 -> receipt-only native bridge -> 服务端重判 -> terminal 收据`；客户端只传 pack、practice surface 和五个选择。同一 compiled authority 供取题与 writeback 重判双向校验，source/public/manifest 任一 SHA 漂移即拒绝收据，不回退到另一套题库。
- **[选项 identity 纠偏]** hostile review 发现 ord 页会将选项随机打乱，HTML `state.sel` 存的是展示位次，直传 index 会让服务端错映射到源选项。统一 bridge 现在先经页内 `optPerm` 还原为 source option index，再由原生页映射到 sidecar `option_id`；POOL/bank 本来保存 source index，不做二次换算。
- **[五模块感知]** 收据页是当下直接感知面，明示“服务器已复核·已更新学习记录 / 已练过·待验证 / 不等于已经掌握”。返回后学习、复习、问鲁班、学情报告与我的都重读同一 learning-report/LearnerState 投影；问鲁班 dashboard 缓存和诊断完成键同时改为 canonical user scoped，防跨账号串学情。
- **[验证]** luban service/API 全域 `103 passed`，相关 learner-state 裁决/报告/复习 `120 passed`，小程序 Node 全量 `98 passed`，Ruff、contract guard、manifest gate、publisher 二次重放字节稳定均绿。DevTools 以唯一项目根 `yousenwebview` 成功打开且工具账号已登录；但当前 `miniprogram-automator 0.12.1` 与 DevTools 的 `Tool.getInfo` 返回形状不兼容（`SDKVersion` 缺失），页面场景未跑成，只记 `project-open preflight / scenario pending`。
- **[诚实边界]** compiled forward 仍是 `L0_observed / non-promoting / non-official`；五题全对只表示“本轮全对”，不直接升 mastery。当前是本地 candidate，未部署前不声称线上用户已看到。

### 2026-07-14（F16 五题闭环收权 · local code candidate）
- **[真正坏掉的一等事实]** `RetestWritebackService` 已写出真实 `compiled_html_server_rescore` terminal，但共享生命周期识别器只接受 `signed_variant_server_rescore`；因此同一完成事实会出现“正式收据成功 / F16 仍未学 / 次日复习不启动”。同时学习报告把 5 条 item + 1 条 terminal 统计成 6 题，HTML 本地结果又与原生服务端收据争最终结果。
- **[收权修复]** `completion_terminal` 现在是练习完成的唯一事实。严格矩阵仅允许 forward=`signed_variant|compiled_html` + medium/L0/non-promoting，review 仅允许 signed + high/L2/promoting；同一 classifier 同时供 completion commit、item promotion 与 pack cadence 使用。带 completion id 的 item 必须经 canonical terminal 归包，partial item 不得绕过 terminal；compiled authority 未进入 mastery/trusted-promotion 来源。
- **[用户可感知]** F16 第五题后自动进入“正在确认这 5 题”，不再让用户二次选择“保存学习证据”；小程序内只有 terminal-gated 原生收据展示服务端分数，并明确“服务器已复核 · 已更新学习记录 / 已练过 · 待验证 / 不等于已经掌握”。独立网页仍可看原成品汇总，但只陈述“本轮答对几题”，明确“网页预览 · 不写入学习记录”，不再用“稳了 / 满分手 / 采分点都拿到了”越权判断掌握。路线与复习页在返回时重新读 canonical report；路线标签从“已学完”改“已点亮”；今日进度补单位“题”。
- **[计数、历史与 replay]** 新 terminal 写 `quality.progress_countable=false`；学习报告还按 terminal 结构排除历史行，所以五题只增加 5，不会因 completion boundary 变 6。幂等 replay 改按 question identity 排序，不再依赖随机 UUID 字典序；existing、append 后、replay result 与 prescription outcome reader 都服从同一 canonical terminal classifier。后者额外使用 verification authority allowlist：仅保留合法 `construction_grading` probe，`assessment_testset` 必须是 canonical terminal，foreign/unknown 或删掉 completion id 都 fail-close。伪事件不能生成 station completion、成功收据或“验证通过/改善”投影。
- **[验证]** 先写真实 compiled terminal RED，3 个失败准确复现生命周期丢失与 terminal 计数，随后红队补出伪 terminal replay、旁路 prescription reader（含删除 completion id / foreign source）与网页/旧 boolean 题掌握文案三类 authority 漏洞；修复后 learner/luban/API/publisher 相关 Python 套件 `321 passed`，4 个 Node 行为合同与 3 个页面脚本 syntax check 全部 PASS，publisher determinism、contract guard、Ruff 与 diff check 通过。微信 DevTools 使用唯一项目根 `yousenwebview` 打开本 worktree，真实渲染提分路线与 F16 receipt 路由；test2 的 `/retest-items` 仍是 404，页面诚实停在“加载失败/重试”且没有成功收据。由于本轮未部署后端，登录态 terminal→LearnerState readback 仍不是 true-entry closure，不能把本地代码闭环冒充线上已生效。

### 2026-07-13（F16 视频后五题轻练试点 · local only，已由 07-14 收权）
- **[真正坏掉的一等事实]** “学生正在学习哪一版 F16”曾被四处解释：主仓当前 `finished`、旧试点 worktree 的同名 `finished`、手改 `web/public`、没有随成品升级的 pack Markdown SHA。用户指定的最终版 teach/practice SHA 分别为 `7c249552… / d46076db…`，旧试点则是 `591f108f… / 514bcec1…`；选项与反馈已实质重写，6 个音频也更新，不能把旧版继续写进 LearnerState。
- **[整包收权]** 本轮只同步 F16 bundle（teach、practice、6 个变更音频、新增 `audio/manifest.json` 与 `tts-audit.json` 等），除 `.DS_Store` 外与用户指定目录逐文件一致。`scripts/publish_luban_preview_cards.py f16` 是 public 唯一 writer；public 题块 6/6 与 finished 完全一致，11/11 MP3 与 audio manifest 逐字节一致，不再手改托管副本。
- **[五题内容裁决]** finished 继续完整保存 6 题及选项随机化；“视频后练哪 5 题”是独立呈现策略，固定 `Q1 分档 → Q2 工序 → Q3 纠错 → Q4 检查 → Q6 综合诊断`，仅改变 selection，不删改题干、选项、答案或反馈。该策略显式锚定 final practice SHA `d46076db…`，源变更时 publisher fail-close，禁止悄悄按旧序号选新题。
- **[single authority]** publisher 从 finished HTML 编译非公开 `deeptutor/services/luban_lesson/compiled/f16.practice.authority.json`，记录 source finished SHA、bundle SHA、稳定 question/option identity 与正确项；运行时不再正则解析手改 public。HTML 保留原成品逐题反馈体验；完成后只传所选 option identity，客户端 score/is_correct 没有 authority。`RetestWritebackService` 服务端重判并继续单写 item evidence、completion terminal 与 station completion；forward 仍是 `L0_observed / claim_promotion_allowed=false / official_score_allowed=false`。
- **[产品链路]** 站点变为“finished lesson → finished practice 五题产品面 → receipt-only native bridge → server terminal”。原生页不让用户重复做第二套题；拿不到 canonical terminal 就不展示正式收据。lesson/practice URL 追加 finished bundle SHA，而不是只用未变化的 pack Markdown SHA，避免用户缓存继续命中旧卡。
- **[错因边界]** 原 HTML 干扰项 code 只作为 `source_error_code` 留证，不直接升级为 LearnerState canonical error code；当前 Q2/Q3 的顺序错误仍标 E10，专家审计建议待 registry 人工裁决后改 E06。Q4“直指根因”和 Q6“三处失分”含工程推理/R7 待裁决，所以本试点只做教学性 forward evidence，不宣称官方得分或 mastery。
- **[ZIP 原料质量闸]** 只读 extractor 对 F16 scoped archive 实跑：2 个 HTML member、6 个 distinct candidate、6/6 唯一正确项、0 quarantine，但 6/6 都是 `review_required`，题级 source anchor=0，且正确项 6/6 都是最长选项（100% 长度泄漏）。全量目录另有 37 archive / 127 HTML / 638 distinct candidate，其中 81 条 quarantine、581 条 review-required、535/643 唯一答案题的正确项最长（83.2%），题级 anchor 仍为 0，并发现 1 个算术 mismatch、1 个 archive title mismatch、66 个 internal title mismatch；敏感 member 只报路径不读内容。因此 ZIP 只做 provenance/audit 原料；试点可看链路体验，但在补题级来源并消除长度提示前不得批量扩包或把正确率当可靠 mastery 信号。
- **[当前验证与发布边界]** publisher provenance/audio、luban_lesson 与 API 回归 95 PASS；Node 覆盖 finished practice bridge、服务端重判、terminal-only receipt、旧 review authority、first-run 零回归，以及共享 station 的 F16 scope（S05 等非 F16 仍保留 lesson→practice→signed forward）；Ruff、contract guard、diff check 全绿。浏览器真实走完 5 题，确认选项随机化、逐项反馈、结果页与“保存学习证据”按钮可用，非小程序环境会诚实拦截而不假完成。微信 DevTools 用唯一项目根 `yousenwebview` 打开真实 package，并在 station 页执行 lesson→practice 切换；但 auth_state=unknown、未连本地后端完成 terminal 收据，因此只算页面级 partial，不算登录态/真机闭环。未部署，状态仍是 `implemented_local_pilot / not deployed`。其他站点本轮没有修改。

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

### 2026-07-12（PR#451合main+阿里云生产部署 · Opus部署agent执行,四门全过）
- **[合并]** PR #451 merge commit合入main(保留历史),合并SHA `9314930c`;12提交增量(首跑闭环/考点卡三代/错因银行/标准卡签发/性能修复,含签发翻牌645e0e70)。CI两红=测试桩滞后于已签发代码(apiMock缺errorCodeOf/shim未放行script-data),外科补桩dfedaebe后94/94全绿;main领先的33提交无一丢失。
- **[部署四门]** ①容器just-now(07:51Z,healthy);②容器内grep:_BANK_CACHE/原样透传/manifest release_status=signed/STD bank signed全命中;③healthz/readyz公网200;④镜像sha==build产物,host与容器GIT_SHA==9314930c,GIT_DIRTY=false。全量rebuild(36/36 stage,非redeploy_fast),干净发布worktree,写边界全程/root/deeptutor内。
- **[生产界面不变]** LUBAN_STD_CONCEPT_CARDS/RICH_LEAF_RUNTIME/LIGHT_PRACTICE全OFF;小程序未上传(仍老蓝版)。新五模块对用户零展示。
- **[⚠️红线发现,owner待裁决]** 生产`LUBAN_CASE_RUBRIC_BANK_SLOT=pgo`——与"禁拨PGO"红线冲突,**但非本次引入**:host .env备份06-19/07-05/07-06全是pgo(已存活~3周),带canary结构(CANARY_ENABLED=false,cohort qa_/operator_),属案例判分pgo/canary独立轨道。部署agent未擅动(翻已上线3周的判分槽超授权)。**待owner裁决:回legacy还是追认pgo轨道**(需先查这3周生产判分是否受影响——PGO库score=null靠切分粒度隐式计分,红线当初立的原因)。

### 2026-07-12（PR#454学情真值收口合流+二次部署 · 双前端线终结）
- **[合流]** 另一会话的 codex/five-module-root-closure(61aaf9a2 学情真值统一收口)经 PR#454 merge commit 入 main=**84909343**;代码/账本零冲突;.secrets.baseline 撞车按"合并树口径"解(方法志有条目);methodology-log add/add 两会话条目全保留。first-run-learner-loop 已对齐(348b62bf 推远端)。**root-closure 分支内容 100% 进 main 可废弃**(其 worktree 归对方会话,删分支由 owner/对方执行)。
- **[二次部署]** deploy_aliyun.sh 全量 rebuild;四门+md5 指纹全过(容器 17:11:27 就绪/evidence_lifecycle 特征命中/healthz 200/双端 GIT_SHA==84909343);主控独立抽查一致。旗标红线全守(三 LUBAN_*_ENABLED OFF;判分槽 pgo 原样待 owner 裁决)。测试:定向 pytest 803 绿×2轮/yousen 前端 95/95/CI 14 检查全绿(wx_miniprogram 6 失败经 main 基线复跑证实为既有)。
- **[终态]** 生产=main=84909343;唯一前端工作线=first-run-learner-loop(worktree deeptutor-first-run-current-five-module);"两个版本互相抢"终结。

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

### 2026-07-20 · 课后轻练/换皮复测视觉升格(PR #539)

owner 对照视频后 practice 富页反馈原生轻练"特别素",并质疑为何不直接套用富页。裁决:不套用——富页(station web-view 编译 HTML)答案烘焙前端,只能对答案不能做学习证据入口;原生 retest 页是服务端判分+学习记录唯一入口,且换皮复测/错后确认的变体题不在 HTML 里。方案=把富页结构化视觉语言搬进原生页:rule_group 考法 chip、进度条、选项字母章 A/B/C/D、收据错题四层诊断升格为赭红左轨裁决卡(含教材原文卡)、新增答对竹青✓卡清单。Deviations:①选中态从竹青改墨——竹青是"答对"信号,判分权在服务端不预支;②test_retest_completion_authority 四层诊断断言从扁平字符串对齐到 rt-vrow 结构(缺失整行隐藏合同不变)。数据红线不动:内容全部签发字段逐字,letter 是纯呈现层座位号。

### 2026-07-21 · 题给视觉面板恢复(PR #540, owner 拍板乙方案=完整视觉)

owner 指出原生轻练丢失了成品练习页的题给图形信息(影响理解/记忆脚手架)。关键洞察:各站手写 figFor/fig(name) 绘制代码的输出是确定性定位元素列表——编译期用 Node vm 沙箱求值一遍,把绘制结果作为结构化数据挂进 authority item.figure(呈现层附件,不入 content_sha256 白名单→签名裁决零触碰),投影单点透传,原生页纯几何缩放渲染(594rpx 画板,figure 原配色=内容插图不受 UI 四色纪律约束,外框纸墨)。Deviations:①S07 是模板分支形态(figRuler/figPipe 写死在标记里)不可泛化求值,显式 SKIP 记缺口待单独处理;②板底色启发从逐题中位数改为站级(渲染器 D() 默认 fg 亮度)——逐题会被 chip 白字污染;③40 站重发布实测唯一变化=authority JSON+manifest 重钉,hosts/receipts/packets 字节稳定。双判据:check=0+status 清零(承接 #521 漏 stage 教训)。

### 2026-07-22 · 教学视频免费引子开关(前 20 集免费,其余待开放)

owner 意图:9/68/69 元入门体验型套餐(佑森后端配置价,非前端硬编码;前端源码+老蓝锚点 e8d7493d1 全搜不到),要拿鲁班教学视频当引子——免费开放 N 集,用已有的学习偏好点击埋点看学员是否喜欢这个模块,再决定要不要上付费墙。裁决=Model A 度量优先:先只做免费引子上限,**不接支付**。

- **开关**:`packageDeeptutor/utils/flags.js` 加 `teachingVideoFullAccessEnabled`(默认 `false`=引子态)+ 常量 `TEACHING_VIDEO_FREE_LIMIT=20`(改"免费给几集"只动这个数)+ 纯函数 `resolveTeachingVideoLimit()`(严格 `===true` 才全解锁,缺省/异常回引子态 fail-closed;可被 host 运行时 flag 覆盖,无需重传小程序)。
- **落点**:`teaching-points`(全部教学集)页。owner 二次拍板=超出上限的集**不隐藏,显示"待开放"**。`buildChapterSections(rawPoints, limit)` 加全局跨章计数,index≥limit 打 `locked:true`。
- **关键不变量守护**:待开放集**不丢卡**——`_load` 有"可见集数==后端全集数"投影完整性校验(publishedTeachingPointCount!==visible 抛错),锁态只是显示层 flag,`lessonCount` 不变,校验依然通过。若当初用"截断丢卡"实现会直接触发 mismatch。
- **埋点 0 改动**:教学视频点击(`microlesson`)和练习作答(`retest`/`full_answer`)早已在发 surface-telemetry 并被本分支 `bi.py` `get_engagement_breakdown` 按 object_type 消费。owner 说"练习题也要"实为要测两个模块的偏好,**练习不设上限**(选项 A),已在数据里。
- **openEpisode 拦截**:待开放集点击只 toast「这一集待开放」,不跳转、不发播放埋点(避免污染 microlesson 触达指标)。
- **Deviations**:①顶部计数保留后端全集数 + 新增「当前免费开放前 N 集,其余待开放」提示行(学员看得到还有多少集,引子暗示非硬藏);②`buildChapterSections` limit 参数缺省=不限,保旧测试调用(`buildChapterSections(points)`)与旧行为一致。
- **测试**:扩展已注册的 `test_luban_teaching_points.js`(不新建文件避免 contract_guard):25 集 payload 验证前 20 解锁/后 5 待开放/总数 25 不丢卡、limit=null 全解锁;页面级 onLoad(mock 上限 2)验证 locked+unlockedCount;待开放点击不跳转;wxml 源断言 tp-card--locked/data-locked/待开放。**117/118 yousenwebview 测试 PASS**。
- **[非本次改动 · 须 owner 处置]** 唯一 FAIL=`test_freeCourseDetails_polyv_secret_boundary.js`,系会话开始时工作区已有的未提交 WIP(把 polyv 视频签名从服务端下发改回客户端硬编码密钥 `mnABa9XMn8`)所致;stash 我的改动后仍 FAIL,与本次无关。该 WIP 违反"客户端不得持有 polyv 签名密钥"边界护栏,建议 owner 决定回滚或改走服务端签名。另有游离文件 `pages/freeCourseDetails.js`(与目录内文件逐字相同的副本),疑似 DevTools 误建,未跟踪。

### 2026-07-22(续) · 教学视频付费墙 + 4 档定价(全栈,派 2 独立 agent + 主控集成)

owner 决策升级:上一节的"全局开关控制 20 集"改成**按付费状态的三档付费墙** + **真实收费 4 档套餐**。派后端/前端两个独立 agent(文件互斥:deeptutor/ vs yousenwebview/),主控定契约 + 集成 + 亲核钱的逻辑。

- **契约(单一权威在服务端)**:`GET /api/v1/billing/wallet` 响应加 `teaching_video_limit`(int=上限/`null`=无限)。服务端按**当前有效会员 tier** 算(`resolve_teaching_video_limit`,mobile.py):无有效会员/过期→20、starter_19(9.9)→30、light_98/vip/svip/supreme_svip→null;复用 `member_service.get_profile` 的 tier+expire_at(不自造第二权威),查失败 fail-safe 到 20 不 500。前端 teaching-points `_loadTeachingVideoLimit()` 调 getWallet 读该字段,`hasOwnProperty` 保留显式 null=无限,`.catch`+缺失→回落 20(fail-closed,绝不误放全部);promo 全局开关 `teachingVideoFullAccessEnabled` 优先级最高(促销总开关)。
- **4 档定价**(线上 45 点/元、越贵越划算、带原价划线):入门体验 9.9(原29/400点/20次,角标**限时上线**)、进阶 68(原98/3000点/150次)、VIP 198(原298/9000点/450次)、SVIP 268(原398/12500点/625次)。点/元 40.4<44.1<45.5<46.6 单调递增。
- **[资损核心 · agent 揪出主控没料到的雷]** 发点真值 = 套餐 `points` 字段(`_apply_wechat_payment_success→manual_membership_purchase→_resolve_membership_package→_normalize_membership_package→grant_points`)。`_normalize_membership_package` 里有个**硬编码 pinning 覆盖块**会把 starter_19/light_98 强刷回旧值(800/4400),且在发点路径上——只改 `_default_packages` 会被静默刷回=资损。两处都改。测试钉死:买 9.9 发 400 点/收 990 分、买 68 发 3000 点/收 6800 分,精确无浮点漂移。收费流程 `openCheckout` 不分套餐、走同一 `createBillingCheckout→wx.requestPayment` 官方微信支付,新档自动继承(owner 强调"参考 198 那些一样能正常收费")。
- **[取舍 · owner 拍板去掉 598/998]** svip 598→268 重定价(顶档);supreme_svip(998)**后端定义保留、仅前端 `_isLaunchPackageId` 白名单剔除**——因其被管理端"手动开通会员+撤销"流程(service.py:6214-6340)硬编码引用,删定义会打断该流程。故消费者面只见 4 档,998 留作管理端手动开通/撤销。已明确告知 owner。
- **[连带]** svip 参考点数 28000→12500(`_billing_usage_reference_points_for_plan` 优先读套餐 points,MAP 是兜底;两处都同步)。usage 测试某 svip member 剩余投影 97%→90%(分母变小、metered 占比变大),同算法同逻辑,正当连带非算法变更,断言已更新。
- **测试**:后端定价/入门发点/顶档/管理端撤销/视频三档+过期→20 全绿(逐个点名 28+12 passed);前端 billing 42 断言 + teaching-points + flags 全绿;前端全量 117/118(唯一 FAIL=上文 polyv WIP,无关)。
- **[隔离污染 · 非本次回归]** `test_mobile_router.py` 全量文件跑时 `test_billing_usage_...enforcement_off` 在 `plan_id=='svip'` 处失败(得 'vip'),但**单独跑 PASS**;`sprint→svip` 解析不依赖 svip 价格,逻辑上与本次改动无关(改动前该断言同样会被走到),系前置测试泄漏共享状态的已知套件污染(见 memory「全量pytest有隔离污染」)。
- **[未做 · 待上阿里云里程碑]** 真机微信支付端到端(能否为 9.9/68/268 开出预支付单并到账)= 单元+契约级已验,live 收款要一次测试部署单独验;付费墙 live 行为(付费用户真看到 70+、免费卡 20)同理。未部署前不宣称"生产已能收费"。
### 2026-07-22(再续) · 免费教学视频上限 10 → 20（本次合并裁决）

- 本次合并将无有效会员/过期会员的 `teaching_video_limit` 默认恢复为 20；`starter_19` 仍为 30，`light_98/vip/svip/supreme_svip` 仍为无限。
- 单一权威仍是 `GET /api/v1/billing/wallet.teaching_video_limit`。teaching-points 只消费服务端字段；字段缺失、请求失败或非法值时，前端 fail-closed 回落 20，不另算会员等级。
- 会员权益读取使用 canonical wallet id 对应的只读 entitlement read model，不调用会 bootstrap/保存默认会员的 `get_profile`。
