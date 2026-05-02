# 鲁班智考使用反馈 Top10 问题注册表

Status: Draft issue register
Date: 2026-04-25
Source files:

- `运营部鲁班智考反馈收集1.0(1).docx`
- `聂国宁-鲁班智考问题反馈(1)(1).pptx`，文本层为空，按截图媒体复核
- `鲁班智考测试问题-奕森(1)(1).pptx`
- `曾美婵-鲁班智答问题反馈(1)(1).pptx`

Related fix plan:

- [2026-04-24-luban-feedback-top10-root-cause-fix-plan.md](2026-04-24-luban-feedback-top10-root-cause-fix-plan.md)

## 使用方式

这份文档不是逐条截图流水账，而是把原始反馈合并成 10 个可修复的问题域。后续继续按“三个三个修”的节奏推进时，以本表作为用户反馈侧的问题清单，以 2026-04-24 的 fix plan 作为实施和验证记录。

## Root-Cause 归类原则

同一类用户痛感只保留一个一等业务事实，避免把每个截图都变成一个特殊补丁。

- `history authority`: 历史会话的身份、数量、时间、删除、归档、详情读取必须只有一个 authority。
- `terminal truth`: 用户看到的最终回答只能来自 public final answer，后台过程和 provider error 不能进入正文。
- `surface route`: 小程序页面栈、返回、跳转、按钮响应必须以当前用户任务为 authority，而不是偶然页面栈。
- `exam context`: 专业方向、考试类型、知识库路由必须由 runtime context 明确承载，不能靠 prompt 猜。
- `assessment contract`: 摸底测试、练题、答题卡、题数、提交语义必须有稳定合同。

## Top10 问题

| # | 问题域 | 原始反馈锚点 | 一等业务事实 | 疑似根因类型 | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | 登录、授权、验证码和二次进入卡顿 | 手机号验证码要 1-2 分钟；微信或手机号登录卡顿；登录后回佑森再进鲁班智考会停在登录页 1-2 秒；点击登录按钮底部按钮卡住 3 秒 | 用户完成登录后，入口应稳定进入已登录学习态，不反复展示登录中间态 | auth/session readiness 与小程序入口 loading authority 不统一 | 本批已修并同步阿里云：`auth.isLoggedIn()` 不再信任过期 token；manual/register 已登录时不再等待 profile，直接进入目标页；SMS 冷却前置到阿里云 provider 调用之前；无 token 跳登录保留 returnTo；公网 mobile-login smoke 证明 auth/session 连续性，真实短信运营商送达耗时仍需短信通道观测 |
| 2 | 充值和支付入口异常 | 充值页顶部 logo 突出；充值无法跳转支付页面；余额显示需要和真实账户一致 | 充值按钮必须进入支付或明确失败原因，余额必须来自唯一账户 authority | 钱包/会员/支付状态与 UI 入口 contract 不完整；历史 `member_console.packages` 快照会覆盖新默认套餐 | 本批修复：钱包余额和套餐从后端 wallet/member package authority 读取，默认套餐收敛为 9/99/199 三档；服务层读取旧 JSON 时强制投影 canonical 三档，已同步到阿里云并重启 healthy；因仓库没有下单/微信支付接口，充值 CTA 改为明确“暂未开放”说明，不能伪装支付成功 |
| 3 | 页面路由、返回和栏目切换不稳定 | 先点其他栏目后左上角不能回首页；误触其他板块出现 404；手机返回直接退出小程序；对话中跳到底部其他按钮后回不到原对话 | 用户在学习任务中切换页面后，应能回到原对话或明确回到首页，不丢当前任务 | surface route / page stack authority 漂移，页面栈被当成业务状态 | 本批已修并同步阿里云：package `returnTo` 只允许鲁班包内已知页面，`/pages/...` 只归一化已知鲁班页，宿主页/未知页回 fallback，减少 404；无 token 深入口登录后回原页；DevTools 已验证 freeCourse -> chat -> history 路径；物理返回退出仍受微信 `reLaunch` 页面栈限制，需要真机策略专项 |
| 4 | 历史会话数量、时间、删除、归档、详情读取不一致 | 历史时间显示 1970；历史对话时间对不上；数量和实际操作不对；删除后刷新又出现；归档成功但仍在历史；点击历史偶尔进不去详情；历史中显示 `TutorBot` | 历史列表、详情、删除、归档、数量和时间都必须围绕同一个 conversation authority | raw session id、mirror id、缓存展示态、秒/毫秒时间同时争夺 authority | 已重点修复并通过本地、阿里云、DevTools 显示验证；破坏性删除/归档仍需经授权真机复验 |
| 5 | 后台过程、代码、乱码、格式残留泄露给用户 | 提问后弹出“查询”代码；出现一串代码；查看后台过程会展开代码；文件来源链接直接露出；乱码；表格里出现 `<br>`；历史预览有星号或 markdown 分隔符；中文术语引号不统一；公网曾裸露 `Authentication Fails / invalid_request_error` | 用户正文只展示可读、可信的最终答案；后台 trace 只进日志和观测系统；中文正文中的术语引用应符合中文阅读习惯 | terminal truth 不唯一，tool trace/provider output/markdown raw text 进入 public content；中文排版规范没有统一出口；阿里云 provider authority 错绑到无效 DeepSeek official key | 本批继续修复并同步阿里云：public content/result/history 出口统一降噪 provider raw auth error；阿里云运行时切到真实可用 DashScope compatible `deepseek-v4-flash`；公网 mobile-login E2E 已返回正常中文回答，不再裸露 401 provider error |
| 6 | 答案质量、专业方向和知识库错配 | 一造专业进入 AI 后仍给一建练习题和建议；25 年建筑实务真题选择题直接给答案；建工基础考点缺失；多加无关供热供冷；答案和豆包对比有出入 | AI 必须按用户当前考试方向和建筑实务知识库回答，不应混用考试轨道 | exam track / RAG routing / grounded evidence 没有形成单一 runtime context | 已修复 exam_track canonical path；知识质量和题库覆盖仍需 benchmark |
| 7 | 出题、练题和摸底测试合同不稳定 | “只出题不要答案”仍给答案；让生成 5 道题很慢；摸底测试 `~8` 分钟；说 20 道题实际不足；无答题卡；不答和部分作答提交描述一样；下一题变提交后又提示未答 | 练题/测评必须有稳定题数、题卡、答案隐藏、提交和未答语义 | assessment contract 缺失，题目生成、展示、提交各层各自判断 | 本批继续修复：摸底不再复制 5 道源题伪装 20 道，返回并展示 `requested_count/delivered_count/question_bank_size/shortfall_count`；redacted public followupContext 不再覆盖 session 内部批改答案 authority；练题结构化 config 仍需下一轮专项 |
| 8 | 响应慢、超时、不能暂停或修改问题 | 提问分析接近 1 分钟；真题生成慢；响应超时；分析时点击暂停无反应；AI 思考时不能终止或修改问题；切屏会中断 | 长任务必须有可见进度、可取消状态和可恢复的 terminal outcome | turn runtime 的 cancellation、partial artifact、前端交互状态没有统一 contract | 本批继续修复并同步阿里云：小程序和分包 `ws-stream` idle timeout 先向统一 `/api/v1/ws` 发送 `cancel_turn`，再等待 terminal outcome；发出 cancel 后第二次 idle tick 只显示“正在等待本轮结束”，不再抢先报页面级超时；编辑/早停仍按 authoritative `turnId` 取消；真实慢请求手动停止仍需干净 DevTools 或真机复验 |
| 9 | 移动端输入、复制、按钮和遮挡问题 | 长按无法复制答案；复制表格内容为空；键盘挡住对话框和发送按钮；无法分行；反馈功能无法点击；管理按钮和小程序退出按钮重合；下方菜单栏不能手动拖动；对比分析点击多次才响应 | 每个可见控件必须执行用户预期动作，且不被系统胶囊/键盘遮挡 | 原生 surface 缺少统一 interaction QA gate，复制曾读取 raw message 而不是可见渲染；“反馈”同时指消息质量反馈和产品意见反馈，缺少入口分层 | 本批修复：输入框绑定键盘高度和 cursor spacing；历史页管理按钮按胶囊右侧安全区避让；复制 authority 已修并 DevTools 验证；消息级反馈弹窗可选可提交且失败不误报；我的页新增微信原生意见反馈入口；拖动/多次点击仍需专项 |
| 10 | 学情、诊断、成就和非文本能力入口不完整 | 学情完成题数 30 与历史 8 不一致；诊断维度图不完整或浅色模式看不清；成就栏无说明且点不了；没有联网选择；不能上传图片/文档分析；不能生成思维导图 | 学习诊断和扩展能力入口必须有清楚的数据口径、可用状态和失败说明 | learner analytics、capability availability、UI affordance 没有统一 product contract | 本批修复：成就优先读 `/profile/badges`，点击成就展示获得条件；联网搜索/图片文档分析/思维导图在个人页统一展示为未开放并说明原因；雷达图按深浅色使用不同 canvas palette；学情进度已拆分真实 `done/total` 与 `daily_target/target`，不再把 30 题目标冒充完成总数；host 报告页恢复 `各维度详情` 列表并在 DevTools 验证可见 |

## 优先级判断

P0 必须先关，因为它们会直接破坏用户信任或造成数据错乱：

1. 历史会话 authority：时间、删除、数量、详情、`TutorBot` 泄露。
2. 后台过程泄露和空回复：代码、provider error、乱码、无正文。
3. 页面路由和返回：404、回不去原对话、误退出小程序。

P1 是核心学习效果：

4. 专业方向和知识库错配。
5. 出题/练题/摸底测试合同。
6. 响应慢、超时、暂停和修改问题。

P2 是产品体验和能力完整度：

7. 登录和二次进入卡顿。
8. 充值支付入口。
9. 移动端复制、输入、按钮遮挡。
10. 学情、诊断、成就、上传、思维导图等非文本能力入口。

## 已与 2026-04-24 Fix Plan 对齐的状态

已经进入修复计划并有验证记录的问题：

- #4 历史会话 authority。
- #5 后台/tool/provider 内容泄露；provider auth raw error 已在 public terminal boundary 降噪，阿里云 provider authority 已切到 DashScope `deepseek-v4-flash`。
- #6 专业方向 `exam_track` canonical context。
- #7 “只出题不要答案”的答案隐藏路径。
- #8 取消/失败时的安全 assistant message、idle timeout/主动停止的 `cancel_turn` authority、早停 `client_turn_id` 绑定；cancel 后等待 canonical terminal outcome 的二次 timeout 抢权已修。
- #9 复制可见内容，而不是复制 raw message；本批继续修复键盘遮挡、分行输入和历史页管理按钮避让。

尚未完成充分验收的问题：

- #1 登录态、returnTo 和 SMS 冷却 authority 已修并经阿里云 smoke；验证码真实短信送达耗时、SMS provider 状态映射和登录动画降级仍需短信通道观测。
- #2 真实充值支付链路。
- #3 returnTo allowlist、深入口登录回跳和 freeCourse/chat/history 主路径已修；全页面返回/切换/404 回归矩阵和手机物理返回策略仍需真机专项。
- #7 后端 `requested_count/delivered_count`、题库去重数量、redacted context 与 internal grading authority 已修；练题结构化 config 仍未充分收口。
- #9 菜单拖动、对比分析多次点击；键盘遮挡、分行输入、管理按钮胶囊避让、复制按钮、反馈入口已进入本批验证。
- #10 学情统计和诊断图展示已做本地/DevTools 验证；上传图片/文档、思维导图仍是未开放 availability truth，尚无能力 contract。

## 下一步修复建议

下一组如果继续推进，建议选择：

1. #7 练题结构化 config：`num_questions/question_type/reveal_answers/reveal_explanations` 进入 `deep_question`，不要继续靠自然语言 prompt 猜。
2. #1 SMS provider 真实验证码送达耗时和错误状态映射。
3. #8 在干净微信开发者工具或真机里补真实慢请求手动停止回归，确认 UI 停止按钮、terminal event、历史恢复三者一致。

理由：#2 和 #10 已完成当前代码条件下的可交付收口；真实微信支付仍需要新增后端下单/回调 contract，不能混入本批前端修复；#5 provider raw error 已闭环到公网 E2E，#8 的自动化 cancel authority 已修但真实慢请求手动停止还缺干净 DevTools/真机复验，#7 的结构化 config 和 #1 的短信送达仍直接影响主学习链路。
