# 鲁班智考官网与内测申请落地计划

> **For agentic workers:** 本计划用于把 `/intro` 官网介绍页、`/invite-test` 内测说明页与 `/invite-test/apply` 独立申请页收口成一条完整转化链。实施前先确认当前工作区脏改动边界，只改本计划列出的入口，避免把 TutorBot 阅卷主链路、微信小程序聊天主链路和官网转化页混在一个改动里。

**Status:** Proposed v1  
**Created:** 2026-05-15  
**Owner surface:** Web `/intro` + Web `/invite-test` + Web `/invite-test/apply` + application data capture  
**Related plans:**
- [2026-04-20-luban-adaptive-teaching-intelligence-prd.md](2026-04-20-luban-adaptive-teaching-intelligence-prd.md)
- [2026-05-13-luban-case-grading-error-map-prd.md](2026-05-13-luban-case-grading-error-map-prd.md)
- [2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md](2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md)

## 1. 一句话结论

鲁班智考官网不应该只做产品介绍页，也不应该只做一个报名表。

它应该是一条完整的内测转化链：

```text
痛点共鸣
  -> 产品差异化
  -> 真实小程序使用画面
  -> AI 陪考教练价值
  -> 申请内测
  -> 收集学习阶段 / 痛点 / 可测试时间 / 回访意愿
  -> 形成首批内测名单和需求验证证据
```

最终目标是让访问者明确知道三件事：

1. 鲁班智考不是普通 AI 题库，而是一建建筑实务 AI 个性化陪考教练。
2. 首批最强场景是案例题批改、错因诊断、得分表达改写和下一题训练建议。
3. 当前是申请制内测，申请信息会用于筛选首批用户和验证真实需求。

## 2. 一等业务事实与 Authority

### 2.1 一等业务事实

官网转化链必须维护的唯一业务事实是：

> 一个潜在内测用户是否真的有建筑实务备考痛点、是否愿意试用 AI 陪考教练、是否愿意留下足够信息进入内测筛选。

### 2.2 单一 Authority

| 业务事实 | 唯一 authority | 不允许成为 authority 的对象 |
| --- | --- | --- |
| 产品定位与卖点 | `/intro` 页面文案与视觉模块 | 零散海报文案、旧 AI 题库表述 |
| 内测申请记录 | 后续接入的申请数据表 / CRM / 表格 | 前端 `submitted` 状态、浏览器本地状态 |
| 用户真实痛点 | 申请表结构化字段 + 可选补充文本 + 后续回访记录 | 页面点击本身、泛泛满意度问卷 |
| 内测资格状态 | 后台筛选结果或运营名单 | 用户提交成功页 |
| 产品验证结论 | 申请转化数据 + 试用完成数据 + 回访证据 | 单个用户夸赞、内部主观判断 |

### 2.3 P0 不做

- 不在官网页直接承诺提分、保过、押题命中。
- 不把申请提交成功等同于获得内测名额。
- 不把 `/intro` 做成完整营销站群，只做一条清晰转化链。
- 不在 P0 引入复杂 CRM 或后台管理系统；先保证申请数据可持久收集。
- 不让官网页面承担学习状态、错因画像、内测资格的长期 truth。

## 3. 当前状态判断

### 3.1 已有基础

当前 repo 已有：

- `/intro`：产品介绍页，已经围绕“AI 实务教练 / 个性化陪考 / 案例题批改”重做过首屏和 Demo。
- `/invite-test`：内测说明页，承接产品价值、首批适合人群、内测机制和申请跳转。
- `/invite-test/apply`：独立申请页，承载前端表单校验、手机号、邮箱、备考阶段、痛点、可测试时间、回访意愿和 consent 字段。
- `web/public/images/logo-white.png`：与微信小程序一致的鲁班智考 logo。
- 微信小程序真实对话页：可以作为官网视觉证据，避免官网展示与真实产品脱节。

### 3.2 主要缺口

1. `/intro` 与 `/invite-test` 的信息架构还未完全统一  
   `/intro` 讲产品，`/invite-test` 讲内测，但两者之间还需要更明确的“为什么现在申请内测”的承接。

2. 内测申请仍是前端模拟提交  
   当前 `InviteTestPage` 只做本地 `submitted` 状态，没有持久化到数据库、表格或 CRM。

3. 内测收集字段还不够服务后续筛选  
   已有字段能判断基础意愿，但还缺少“考试类型、考试时间、是否佑森学员、最近一道错题/案例题材料、微信联系方式”等用于运营跟进的字段。

4. 缺少内测后的任务闭环  
   用户提交后应知道通过后要完成什么任务，运营也要知道如何判断这位用户是否完成了有效体验。

5. 缺少基本漏斗埋点  
   目前难以回答：多少人看了 Demo、多少人点击申请、多少人提交成功、哪个痛点最强。

## 4. 页面架构

### 4.1 `/intro` 官网介绍页

职责：完成产品理解与申请动机建立。

推荐模块顺序：

1. 首屏：痛点共鸣
   - 标题：题刷了很多，分数却不涨？
   - 副标题：你缺的不是更多题，而是有人告诉你为什么丢分。
   - CTA：申请内测体验 / 看一次 AI 批改

2. 痛点区
   - 看解析懂，换题仍错
   - 案例题写很多，不知道哪些话得分
   - 错题很多，不知道真正薄弱点
   - 每天刷题，但没人告诉下一步练什么

3. 产品定位区
   - 一建建筑实务 AI 个性化陪考教练
   - 越用越懂你的作答习惯、薄弱考点和丢分原因

4. 产品能力区
   - 案例题 AI 阅卷
   - 选择题错因诊断
   - 得分表达改写
   - 错题复盘
   - 个性化陪考记忆

5. 真实小程序展示区
   - 使用微信小程序对话页视觉，而不是虚构网页后台
   - 展示长文回答、表格、易错点、踩分点、底部追问输入

6. 对比区
   - 普通 AI 题库 vs 鲁班智考
   - 重点突出“AI 解析按钮”与“AI 陪考教练”的差异

7. 内测转化区
   - 解释为什么是申请制内测
   - 明确首批适合人群
   - 主 CTA 统一到 `/invite-test/apply`

### 4.2 `/invite-test` 内测说明页

职责：解释内测机制、首批适合人群和通过后的体验任务，并把用户导向独立申请页。

推荐模块顺序：

1. 内测说明
   - 当前不是公开注册，而是小批量申请制内测
   - 提交后不自动获得名额
   - 通过后会收到联系并完成指定体验任务

2. 首批适合人群
   - 正在备考一建/二建建筑实务
   - 案例题长期失分
   - 听课懂但答题表达不完整
   - 愿意提交真实错题并反馈体验

3. 内测任务说明
   - 完成一次 AI 实务对话
   - 提交一道案例题或错题
   - 查看 AI 批改与下一题建议
   - 完成 3 分钟反馈
   - 可选 10 分钟回访

4. 申请入口
   - 不在说明页内嵌长表单
   - 明确申请信息会在独立页面填写
   - CTA 指向 `/invite-test/apply`

5. 隐私与合规说明
   - 信息用于内测筛选、产品改进和需求分析
   - 不做保过、提分承诺
   - 学习效果与个人基础、投入和使用频率有关

### 4.3 `/invite-test/apply` 独立申请页

职责：收集可筛选、可回访、可分析的内测申请信息。

原则：

- 页面只服务填写申请，减少产品介绍干扰。
- 必填字段服务筛选和联系，选填字段服务后续回访。
- 邮箱作为必填联系方式，与手机号一起用于发送内测通知、体验说明和回访安排。

## 5. 内测信息收集字段

### 5.1 P0 必填字段

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| name | text | 运营联系称呼 |
| phone | tel | 首批通知与回访联系 |
| email | email | 内测通知、体验说明和回访安排 |
| exam_type | select | 区分一建/二建/其他建筑实务 |
| exam_stage | select | 判断学习阶段 |
| pain_point | radio / multi-select | 判断最强痛点 |
| weekly_time | select | 判断可参与测试强度 |
| consent | checkbox | 合规同意 |

### 5.2 P1 推荐字段

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| wechat_id | text | 方便加入内测群或一对一联系 |
| is_yousen_member | select | 区分佑森会员与外部线索 |
| exam_date | date / select | 判断临近考试优先级 |
| latest_wrong_question | textarea | 获取真实错题材料 |
| current_method | textarea | 判断现有替代方案和竞品使用 |
| accept_interview | checkbox | 标记高价值回访样本 |

### 5.3 字段收集原则

- 必填字段控制在 8 个以内，降低提交摩擦；邮箱是联系内测用户的必要字段。
- 选填字段用于提高样本质量，不阻断提交。
- 手机号必须基础校验，但不要在 P0 上短信验证。
- 不收身份证、准考证、完整课程账号密码等高敏信息。
- 用户提交后展示“申请已提交，等待筛选”，不要展示“已获得资格”。

## 6. 数据落地方案

### 6.1 P0 推荐实现

新增一个轻量申请记录入口：

```text
POST /api/v1/web/invite-test/applications
```

或者在 Next.js web 内先做 route handler：

```text
web/app/api/invite-test/applications/route.ts
```

P0 数据可先写入 Supabase 表：

```text
invite_test_applications
```

当前落地约定：

- API route 优先读取 `INVITE_TEST_DATABASE_URL / SUPABASE_DB_URL / DB_URL`。
- 本地开发默认从 `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env` 读取 `DB_URL`。
- 由于当前 Supabase REST Data API 对主项目返回配额限制，申请写入走服务端 Postgres 连接，不把 service role key 暴露给浏览器。
- `public.invite_test_applications` 启用 RLS；写入只走 server-side API authority。

建议字段：

```text
id
created_at
source_page
utm_source
utm_campaign
name
phone
email
wechat_id
exam_type
exam_stage
pain_point
weekly_time
current_method
latest_wrong_question
is_yousen_member
accept_interview
consent
status
operator_note
```

### 6.2 状态流转

```text
submitted
  -> qualified
  -> contacted
  -> onboarded
  -> completed_first_task
  -> interviewed
  -> rejected / waitlist
```

P0 前端只需要提交到 `submitted`。后续运营筛选可以先通过 Supabase table、CSV 或 BI 页面处理。

### 6.3 防重复与安全

- 手机号作为软去重字段，同手机号重复提交时保留最新补充信息或记录 submit_count。
- 接口做基本 rate limit。
- 服务端再次校验手机号、consent、必填项。
- 不在 URL query 中暴露手机号。
- 申请表提交成功后不要把完整手机号回显到页面。

## 7. 埋点与验证指标

### 7.1 漏斗指标

| 指标 | 事件 |
| --- | --- |
| 访问官网 | `intro_view` |
| 点击 Demo | `intro_demo_click` |
| 点击申请 | `intro_apply_click` |
| 访问申请页 | `invite_view` |
| 开始填表 | `invite_form_start` |
| 提交成功 | `invite_submit_success` |
| 表单错误 | `invite_submit_error` |

### 7.2 产品验证指标

| 问题 | 指标 |
| --- | --- |
| 痛点是否成立 | pain_point 分布、latest_wrong_question 质量 |
| 是否愿意尝试 | 申请页访问到提交转化率 |
| 是否愿意深度反馈 | accept_interview 比例 |
| 哪类用户最强 | exam_stage + pain_point + weekly_time 交叉 |
| 内测是否有价值 | completed_first_task / interviewed / positive_signal |

### 7.3 首批判断阈值

第一批内测不用追求大流量，优先看高意向样本：

- 申请提交数达到 30 份，可以开始第一轮筛选。
- 高质量错题/案例题材料达到 10 份，可以启动体验回访。
- 回访完成 5 人后，必须输出一份“继续开发 / 调整定位 / 暂停扩张”的判断。

## 8. 实施阶段

### Phase 0：统一页面叙事与入口

**目标：** 让 `/intro` 与 `/invite-test` 成为同一条转化链。

- [ ] `/intro` 所有主 CTA 统一为“申请内测体验”。
- [ ] `/intro` 增加一个内测说明区，解释为什么当前是申请制。
- [ ] `/intro` 的 Demo 保持微信小程序真实对话视觉。
- [ ] `/invite-test` 首屏文案从“市场测试”改成“AI 陪考教练内测申请”，减少内部视角。
- [ ] `/invite-test` 明确“提交不等于获得资格”。

**验收：**

```text
用户从 /intro 能理解产品卖点，并能在 2 次点击内进入申请表。
用户在 /invite-test 能理解为什么申请制内测值得填写，并能进入 /invite-test/apply。
用户在 /invite-test/apply 能理解为什么要填这些信息，以及通过后要做什么。
```

### Phase 1：补齐申请字段与前端交互

**目标：** 表单字段足够支持运营筛选，但不显著增加提交摩擦。

- [ ] 增加 `exam_type`。
- [ ] 增加 `email` 必填。
- [ ] 增加 `wechat_id` 选填。
- [ ] 增加 `is_yousen_member`。
- [ ] 增加 `exam_date` 或备考月份选项。
- [ ] 增加 `latest_wrong_question` 选填 textarea。
- [ ] 更新表单校验与错误提示。
- [ ] 提交成功页说明下一步：等待筛选、可能联系、可准备一道错题。

**验收：**

```text
必填字段缺失时能准确提示并聚焦。
选填字段不影响提交。
移动端无横向溢出，长字段不遮挡按钮。
```

### Phase 2：申请数据持久化

**目标：** 前端提交不再停留在本地状态，运营能拿到真实名单。

- [ ] 新增申请数据表或确定外部收集目的地。
- [ ] 新增提交 API。
- [ ] 服务端校验必填字段。
- [ ] 同手机号重复提交做软去重。
- [ ] 前端接入真实提交接口。
- [ ] 错误时展示可理解的失败提示。

**验收：**

```text
提交成功后能在数据 authority 中查到记录。
刷新页面后申请记录不丢。
服务端拒绝缺少 consent 或手机号非法的提交。
```

### Phase 3：埋点与运营筛选

**目标：** 能用数据判断页面与内测是否有效。

- [ ] 添加申请漏斗事件。
- [ ] 记录 `source_page` 与 UTM 参数。
- [ ] 增加运营筛选字段 `status / operator_note`。
- [ ] 可导出首批名单。
- [ ] 输出首批内测报告模板。

**验收：**

```text
能回答：多少人访问 /intro，多少人点击申请，多少人完成提交，最强痛点是什么。
运营能按 pain_point / exam_stage / accept_interview 筛出首批用户。
```

### Phase 4：内测任务闭环

**目标：** 不只收集报名，而是让用户完成一次产品体验。

- [ ] 通过后发送明确任务：提交一道错题或案例题。
- [ ] 小程序中标记 `invite_test` 来源用户。
- [ ] 完成首次 AI 批改后记录 `completed_first_task`。
- [ ] 回访时围绕“是否真的帮你知道为什么丢分”提问。
- [ ] 形成第一轮内测结论。

**验收：**

```text
至少 10 名用户完成首次 AI 批改。
至少 5 名用户完成回访。
能产出 Top pain points、有效功能、无效功能和下一轮改版清单。
```

## 9. 推荐文案补充

### 9.1 `/intro` 内测承接区

标题：

```text
现在申请内测，让 AI 陪考教练先认识你
```

正文：

```text
首批内测不是公开注册。我们会优先邀请正在备考建筑实务、愿意提交真实错题和反馈体验的学员。
你提交的信息会帮助我们判断：你卡在哪、是否适合首批体验、以及鲁班智考下一步应该优先打磨什么。
```

按钮：

```text
申请内测体验
```

### 9.2 `/invite-test` 首屏

标题：

```text
申请加入鲁班智考 AI 陪考教练内测
```

副标题：

```text
把你最近做错的一道题交给我们。首批内测会验证：AI 是否真的能帮你看清为什么丢分、怎么改写答案、下一题该练什么。
```

### 9.3 提交成功页

标题：

```text
申请已提交，等待筛选
```

正文：

```text
如果你进入首批内测，我们会联系你完成一次真实错题体验。你可以先准备一道最近做错的建筑实务选择题或案例题答案。
```

## 10. 相关代码入口

| 入口 | 责任 |
| --- | --- |
| `web/app/intro/page.tsx` | 官网介绍页内容、CTA、Demo、内测承接 |
| `web/app/intro/intro.module.css` | 官网视觉、响应式、动画与小程序预览 |
| `web/app/invite-test/page.tsx` | 内测页 metadata |
| `web/app/invite-test/InviteTestPage.tsx` | 内测说明页、申请跳转、可复用申请表组件 |
| `web/app/invite-test/apply/page.tsx` | 独立申请页、申请表承载、申请说明 |
| `web/app/api/invite-test/applications/route.ts` | 申请提交 API，服务端写入 Supabase Postgres |
| Supabase `public.invite_test_applications` | 申请数据 authority |

## 11. 最小测试清单

### P0 / P1 前端测试

```bash
cd web
npm run build
npm run lint
```

手工或 Playwright 验证：

```text
/intro desktop
/intro mobile
/intro#demo desktop
/invite-test desktop
/invite-test mobile
/invite-test/apply desktop
/invite-test/apply mobile
```

必须检查：

- 真实鲁班智考 logo 正确显示。
- `/intro` CTA 全部指向 `/invite-test/apply`。
- `/invite-test` 不内嵌长申请表，只提供申请说明和跳转。
- 申请表必填校验可用。
- 移动端无横向滚动。
- 文案没有“保过、保证提分、押题命中”等承诺。

### P2 数据测试

```text
合法申请 -> 写入成功
非法手机号 -> 服务端拒绝
缺少 consent -> 服务端拒绝
重复手机号 -> 软去重或记录重复次数
提交失败 -> 前端展示失败提示
```

## 12. 风险与补充建议

1. 风险：内测页太像内部市场测试  
   修法：面向用户改写为“申请 AI 陪考教练内测”，把市场验证逻辑放到后台和文档，不放在首屏主叙事里。

2. 风险：表单太长导致提交率低  
   修法：P0 必填不超过 7 个，错题材料、微信号、回访意愿尽量选填。

3. 风险：申请后没有跟进，用户热度流失  
   修法：提交成功页明确准备错题；运营在 24 小时内联系首批高质量申请。

4. 风险：收集了痛点但没有进入产品决策  
   修法：每轮内测必须产出一份问题排序报告，反哺 `/intro` 文案、TutorBot 阅卷链路和小程序体验。

5. 风险：官网展示超过真实产品能力  
   修法：所有 Demo 文案以当前小程序真实对话能力为基准，不展示尚未落地的后台、老师复核或自动训练计划界面。

## 13. 第一轮交付建议

第一轮不要同时做完整后台。建议先交付：

1. `/intro` 内测承接区增强。
2. `/invite-test` 文案从内部验证视角改成用户申请视角。
3. 申请表增加 `email / exam_type / wechat_id / is_yousen_member / latest_wrong_question`。
4. 接入一个最小持久化目标。
5. 用 30 份申请和 5 个回访决定下一轮。

这条路径最短，也最符合当前产品阶段：先验证“用户是否真的愿意把错题交给 AI 陪考教练”，再决定是否扩展更重的运营后台和增长系统。
