# 五模块（第 10 轮定稿）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development（每屏一个子代理，主控核验）或 executing-plans。步骤用 `- [ ]` 追踪。
> Status: **Approved-to-build**（owner 2026-07-02 拍板「五模块全量 IA 先行」，阶段 2 tabBar 闸提前解除；spike 点火顺延至本计划 T8 回归后）
> 视觉权威: `设计资产-五模块第10轮/鲁班智考五模块·第10轮定稿.dc.html`（10a-10f 六屏像素基准）+ `评审要点摘要.md`（PRD 规则/token/IA/历史归属——**规格权威，冲突时以摘要为准**）

**Goal:** 把小程序从 4-tab（对话打头）迁移为第 10 轮定稿的五模块 IA（学习/复习/问鲁班/学情/我的，纸墨朱竹语言），并把 spike 四页升级为对应屏。

**Architecture:** 迁移面收敛在 `packageDeeptutor`——tab 壳是自定义组件 `custom-tab-bar/index`（以 `workspace-shell` 挂在各页，非原生 tabBar），改组件+页面归位即可，不动主包投放页。数据面零新增：全部消费既有 read model（lesson viewmodel/mistake-book/report/member），前端不算分不算掌握度。

**Tech Stack:** 小程序原生（CommonJS 惯例）· `theme.wxss` 变量 · 线性 SVG 图标 · 既有 API（`/api/v1/luban` `/api/v1/ws` 等）。

## Global Constraints（每任务隐含，违者打回）

- 概念/authority：`/api/v1/ws` 唯一聊天入口；前端只展示后端 read model；错因只投影 `ERROR_CODE_REGISTRY` 码（10 类中文标签=呈现映射，见 T6，禁第二套分类）；掌握态只由客观复测产生。
- 文案铁律：禁「看穿/识破/揭穿/露馅/检验你/考验」；对=「你是真懂了，不是背的 ✅」错=「这一点再看一眼就稳了 ↺」；语气=直接克制专业。
- 视觉：品牌朱红 `#cf4436` 只出现在四处（鲁 logo 章/播放键/红海报/问鲁班 tab）；主按钮墨色（暗色反转纸色）；辅助字号 ≥24rpx；暖色语义三态（稳了/再看一眼/待复验），禁红灯墙。
- 埋点：沿用 product_behavior_catalog 词表（新事件先登记再用）；D15 事件不得回退。
- 工程：干净 worktree 窄 PR；改 protected 文件配已登记 domain test；contract guard 全绿；每屏交付跑禁词扫描 + `node --check` + 相关契约测试。

## 覆盖矩阵摘要（详见 2026-07-02 覆盖审计对话）

✅ 学习/复习/订阅/OCR/动画卡/埋点判据=既有 plan 执行；🟡 tabBar 迁移/学情形态/exam_date 接线/批改结果页=本计划展开；🔴 对话 tab 重构/三种历史归属/我的 tab/视觉 token/商业化包呈现/错因标签映射=本计划新立（T3/T5/T0/T6）。

---

## T0 视觉基建 + workspace-shell 五 tab 迁移（其余任务的地基）

**Files:** Modify `yousenwebview/packageDeeptutor/theme.wxss`（token）、`yousenwebview/packageDeeptutor/custom-tab-bar/index.{js,wxml,wxss}`；Create `yousenwebview/packageDeeptutor/images/icons/`（线性 SVG）。
**Interfaces:** Produces——theme 变量名 `--lb-bg/--lb-card/--lb-t1/--lb-t3/--lb-good/--lb-warn/--lb-bad/--lb-brand`（值=摘要「鲁班暖调」：dark bg#101315/card#181b1e/t1#f1efe8/t3#8b9398/绿#55967b/金#d4b263/红#bf5b4e/朱#cf4436；light=宣纸#faf9f5）；tab 键名 `learn/review/ask/report/mine`。

- [ ] Step 1: theme.wxss 增补第 10 轮 token（palette prop 只落 warm 一套，bw/trend 留注释禁实现——YAGNI）
- [ ] Step 2: workspace-shell 改五 tab：学习/复习/问鲁班(中央红章凸起 54px 白边)/学情/我的；tab 路由=T1-T5 各屏路径；「历史」从 tab 移除（归 T3）
- [ ] Step 3: 线性 SVG 图标 5 枚（1.8 stroke），替换字符图标
- [ ] Step 4: 验证：`node --check` + 现有 workspace-shell 相关契约测试（tests 里 grep `workspace-shell`）全绿 + DevTools 编译五 tab 可见可切
- [ ] Step 5: commit `feat(luban): T0 五 tab 壳+纸墨朱竹 token`

## T1 学习 tab（10a 亮/10b 夜——默认落地页）

**Files:** Modify `pages/luban/stations/*`（升级为学习 tab 首页）、`pages/luban/station/*`；tab 默认页指向 stations。
**Interfaces:** Consumes `/api/v1/luban/lessons`（列表）/`lessons/{id}`（详情）；Produces 埋点沿用 `module_viewed/learning_action_started/learning_action_completed`。

- [ ] Step 1: stations 页按 10a 改造：顶部距考天数+路线进度 12/40（exam_date 来自 T5 接线，未设置时显示"设置考试日期→"深链我的 tab）+ 下一站卡（带「为什么是它」）+ 复习到期 chip（只跳复习 tab 不做逻辑）
- [ ] Step 2: 路线地图四态（已点亮/下一站/锁定露脸/即将开通）——绿灯包=可点亮集合，manifest 外 slot=即将开通（诚实标注）；竖排书法海报 84×112 三色轮替
- [ ] Step 3: station 页保持三段结构（讲懂 web-view→练→交接时刻），套 10a 视觉；交接时刻文案照定稿
- [ ] Step 4: 夜宣纸暗色（10b）=同一布局走 theme 变量，`isDark` 沿用现有判定
- [ ] Step 5: 验证：禁词 0 命中 + automator 走站点流一轮 PASS + 埋点事件名不回退；commit

## T2 复习 tab（10c）

**Files:** Modify `pages/mistake-book/*`（归位为复习 tab 的错因银行区）、`pages/luban/retest/*`（换皮复测区）；Create `pages/luban/review/review.*`（复习 tab 首页壳：到期推送默认区+自主检索入口+两资产入口）。
**Interfaces:** Consumes retest-items API、mistake-book view model（只读）；错因码展示走 T6 映射表。

- [ ] Step 1: review 首页壳：到期推送区（吃 retest due 数据，空态=深链「先去点亮第一站→」，D1 空态铁律）+ 自主检索（按母题/错因筛选，纯前端过滤已有列表数据）
- [ ] Step 2: 考点卡区（30s 再认：Pack §2.3 一句话压缩+教材原文并排——数据源=lesson viewmodel 扩展字段，若后端未供给则本期只挂「即将开通」占位，**禁前端自造卡文案**）
- [ ] Step 3: retest 页套 10c 视觉；反馈语固定：对=「你是真懂了，不是背的 ✅」错=「这一点再看一眼就稳了 ↺」+correct_statement+anchor 小字
- [ ] Step 4: mistake-book 入口移入本 tab（原 tab 位删除）；错因标签用 T6 映射
- [ ] Step 5: 验证：禁词/自动化一轮/契约测试；commit

## T3 对话 tab（10d「问鲁班」）+ 三种历史归属

**Files:** Modify `pages/chat/*`（归位+顶栏）、`pages/history/*`（变为对话 tab 顶栏时钟图标的二级页）。
**Interfaces:** Consumes 既有 `/api/v1/ws` 流式（**零改动**）；history 复用现有页面数据。

- [ ] Step 1: chat 页挂五 tab 壳，中央红章即本 tab；进 tab 默认续最近会话+顶栏「新对话」钮+顶栏时钟图标→history 二级页（wx.navigateTo，不再是 tab）
- [ ] Step 2: history 条目样式=首句摘要+时间+类型徽章（问答/出题/批改）——徽章从既有消息元数据派生，无则不显示（禁猜）
- [ ] Step 3: 答完必附三钩子（练同类题/加入今日任务/拍照批改）——**只做入口跳转**：练同类→学习 tab 对应站、拍照批改→既有 photo_answer 入口；「加入今日任务」若后端无 API 则本期隐藏（登记 unconsumed 风险，禁前端假加入）
- [ ] Step 4: 验证：WS 流式回归（自动化发一问收流全）+ 禁词 + 历史三归属只此一个列表形态；commit

## T4 学情 tab（10e）

**Files:** Modify `pages/report/*`（归位+顶部加轻量诊断卡）。
**Interfaces:** Consumes 既有 learning-report read model（**零新字段**）。

- [ ] Step 1: 顶部轻量诊断卡：「本周补掉 N 个盲点」+完整报告入口（N=read model 已有字段派生，无则显示定性文案）
- [ ] Step 2: 掌握地图三态暖色语义（稳了/再看一眼就稳/待复验）——内部红黄绿只作调度语义，对外全部过文案铁律；禁红灯墙（D13）
- [ ] Step 3: 每个图表卡底部落「下一步」按钮（深链学习/复习 tab 对应处）；证据链深链回 attempt-detail（既有页）
- [ ] Step 4: 验证：禁词+report 契约测试+自动化开页；commit

## T5 我的 tab（10f）+ exam_date 接线

**Files:** Modify `pages/profile/*`（归位聚合）；后端小改 `member_console`（exam_date 读写接口若缺——先 grep 确认，v3.2 说"profile 已存在未接线"）。
**Interfaces:** Produces `exam_date` 供 T1 距考天数、供 revalidation 引擎（阶段 2 消费）。

- [ ] Step 1: 归位聚合：会员+钱包（既有组件）/免费额度 ●●○（microlesson 状态机字段）/legal/feedback；学习统计不单列（并入学情）
- [ ] Step 2: 考试日期设置（日期选择器→写 profile；服务端已有字段则纯接线，无则在 member_console 加字段——protected 文件，配已登记 domain test）
- [ ] Step 3: 时间预算（轻/中/重三档，本期只存偏好字段不接调度——引擎消费是阶段 2）
- [ ] Step 4: 订阅消息管理入口（授权主入口仍在交接时刻，此处只是查看/说明页）
- [ ] Step 5: 验证：契约+guard 全绿（碰 member_console 必查 contracts/index.yaml domain test）；commit

## T6 错因 10 类中文标签映射（PENDING_OWNER 后合入）

**Files:** Create `yousenwebview/packageDeeptutor/utils/error-code-labels.js`（唯一映射表，前端只读）。

- [ ] Step 1: 产映射草案（registry 码→摘要 10 类：如 E03 关键词缺失→「关键词缺失」、E10→「法规依据缺失」…多对一允许、一对多禁止）**交 owner 确认**
- [ ] Step 2: 确认后落 utils 表+单测（每个 registry 码必有归属，fail-closed 未映射码显示原码）
- [ ] Step 3: T2/T4 的错因展示统一走此表；commit

## T7 批改结果页固定顺序（摘要 PRD 规则）

**Files:** Modify 批改结果呈现页（grep attempt-detail/grading result 页定位）。

- [ ] Step 1: 重排为：得分区间+置信度 → 最该改 3 个 → 采分点命中五色（命中绿/部分琥珀/未命中灰/不确定黄/需复核红）→ 原文证据链 → 改写建议 → 标准答案默认折叠 → 底部双 CTA（二次作答/练同类题）——全部字段来自既有判分 read model，**缺字段的区块整块隐藏不造数**
- [ ] Step 2: 验证：真实批改一单走查顺序+禁词；commit

## T8 总回归 + 真机 + spike 点火衔接

- [ ] Step 1: 全量禁词扫描（pages/luban+chat+report+profile+mistake-book）0 命中
- [ ] Step 2: automator 五 tab 各开一轮 + 双轮全流程三轮（复用点火段驱动脚本）ALL PASS
- [ ] Step 3: D15 事件对齐核验（生产拉数、事件族不回退）
- [ ] Step 4: owner 真机预览六屏 + 人眼核（点火包风险 1/2 在此消除）
- [ ] Step 5: 更新点火包（五模块形态）→ owner 点火拍板（P7）

## 非目标（本计划不做）

bw/trend 两套 palette 实现（token 留位）；「加入今日任务」后端 API（无则隐藏）；商业化收费包（7天诊断包等——计费域概念须单独过 owner，本计划只保留会员呈现现状）；完整 SR 引擎/40 站量产（仍 gated on spike 数据）；web 端。

## 执行序

T0 先行（地基）→ T1/T2/T3/T4/T5 五屏可并行（子代理×5，主控核验）→ T6 等 owner 确认插入 → T7 随 T4 后 → T8 收口。预估 2-4 个工作段。
