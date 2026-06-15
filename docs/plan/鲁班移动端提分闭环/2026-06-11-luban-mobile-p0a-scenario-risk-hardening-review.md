# 鲁班移动端 P0A 场景-风险-加固评审报告

> Status: Proposed / GStack CEO + Engineering + Design hardening review
> Date: 2026-06-11
> Parent authority: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)

> v1.3 对齐（2026-06-15）：父 PRD 已把 P0A spike 形态从「案例题端到端深度闭环」改为「每日提分留存闭环」，核心假设是「忙碌成年人会连续回来」。本评审据此调整数据流与前提：留存是放行门，案例题批改为养成后深度层；GO 钉真实 D1/D7 回访。下列场景矩阵 / 风险 / 加固积木保留。

## 0. Executive Judgment

当前最优答案不是扩大成完整 App 重构，而是把 P0A 做成一条足够硬的纵切，并先用单母题 spike 验证「人会不会连续回来」（v1.3 重心：留存优先，案例题批改为养成后深度层）：

```text
今日任务
-> 2 分钟 MCQ 轻练
-> 选错即诊断（采分点 / 教材章节定位）
-> learning_evidence
-> 次日复测（验证回访）
-> （养成后解锁）案例题半写 -> 采分点级批改 -> 错因复练
-> decision package（GO 钉 D1/D7 回访）
```

在当前条件下，收益大于风险，但只在以下前提成立时成立：

- F16 内容下的「每日留存闭环」spike 先打穿（验证回访），再扩到 3-5 个母题资产与案例题深度层。
- `wx_miniprogram` 与 `yousenwebview/packageDeeptutor` 的开发/验收树先收权。
- `priority_score` 不制造第二套推荐 authority。
- 轻练/半写 evidence 带 task_scope，不污染 learning_evidence。
- `mistake_tag` 有 canonical schema 和 readback 接缝。
- 前端不计算评分、掌握度、推荐和 next_action。
- OCR 不变成默认路径，不写长期 truth。
- 真实微信入口证据不是 `/wechat-harness` 冒充。
- 留存是放行门：GO 钉真实 D1/D7 回访，完成率 / NPS 高但用户不回来最多 WEAK-GO。
- P0A 结束时用 decision package 决定 GO / WEAK-GO / NO-GO。

若这些 gate 做不到，风险会大于收益，因为系统会把“看起来像提分产品”的 UI 发出去，但底层证据链、信任和成本都不可控。

## 1. GStack Review Mode

本次采用：

- CEO review: `HOLD SCOPE`，守住 P0A 纵切，不把计划膨胀成全平台重构。
- Engineering review: 锁数据流、authority、失败态、观测、回滚和测试。
- Design review: 守第一屏任务清晰、批改可信、复练连续、非泛 AI 卡片 UI。
- Careful mode: 不改代码、不提交、不碰发布，只增强 `docs/plan/` 文档权威。

## 2. Scenario Coverage Matrix

P0A 至少覆盖以下场景。每个场景必须有 UI 状态、后端 authority、降级策略和埋点。

| Scenario | User intent | Required behavior | Failure fallback | Gate |
| --- | --- | --- | --- | --- |
| Cold start user | 不知道从哪开始 | 给 3 分钟轻诊断或默认高频母题 | 无历史 evidence 时不得伪造弱点 | UX + Authority |
| Returning normal user | 今天练什么 | 推荐一个主任务并解释原因 | 推荐源缺失时降级默认 P0A task | Scenario |
| Next-day return（留存核心） | 昨天诊断出盲点，今天回来 | 今日页直接给昨天盲点的次日复测 + 看见进步 | 无复测题则给同采分点新题 | Retention |
| Interrupted user | 昨天没练完 | 自动重排一个可完成任务 | 不展示补债/惩罚文案 | UX |
| Exam sprint user | 时间很少 | 提高高权重母题和复测优先级 | 不推长任务压垮用户 | Scenario |
| Weak foundation user | 看不懂长案例 | 先轻练拆采分点 | 半写失败时回到 light practice | Design |
| High-confidence wrong user | 自以为会 | 批改结果展示 evidence span 和错因 | 不靠“已掌握”直接关闭错因 | Trust |
| Low-confidence grading | 批改不稳 | 显示 `uncertain` / `needs_review` | 不 promote stable claim | Trust |
| Grading dispute | 用户觉得批改错 | 允许反馈并生成 `review_candidate` | 不由反馈直接改 learner truth | Trust + Authority |
| Photo/OCR user | 有手写答案 | OCR 只做输入确认 | OCR 失败可重拍/手输/放弃 | Cost + Trust |
| Bad image user | 照片糊 | 先重拍，不调用 OCR | 不消耗高成本路径 | Cost |
| Unauthenticated user | 体验/登录 | 可看 preview，写入前要求 auth | 不写 canonical learner truth | Privacy + Authority |
| Entitlement-limited user | 免费/低权益 | 引导低成本轻练/半写 | 不触发高成本 OCR | Cost |
| Network failure | 作答中断 | draft preservation | 不丢用户输入 | UX |
| WeChat true-entry | 小程序真实使用 | `yousenwebview` root + `packageDeeptutor` page | 未闭合只能 WEAK-GO/NO-GO | WeChat |
| Privacy action | 删除/导出 | 图片删除与学习证据边界清楚 | 不由前端拼导出 | Privacy |
| Operator review | 内部排查 | 可定位 case_family / attempt / trust 状态 | 不直接改 learner truth | Observability |

## 3. Top Risks And Required Hardening

| Risk | Severity | Why it matters | Hardening |
| --- | --- | --- | --- |
| Frontend double-tree drift | P0 | 开发树和验收树不一致会让 P0A 在错误代码上开发或验收失败 | WS0 先拍 development source of truth、sync 机制和 upload source |
| Recommendation second authority | P0 | `priority_score` / `training_intent` / `today_tasks` 并存会产生多套处方真相 | 概念 authority map + priority_score 只做候选排序解释 |
| Partial-answer false evidence | P0 | 半写/轻练按全题 rubric 判会制造假 miss，污染弱点画像 | task_scope + `not_evaluated_no_miss` + evidence_weight |
| Mistake tag schema gap | P0 | 错因若只停留在模板字符串，错题本/复练/今日任务无法共用 | canonical mistake_tag schema + payload builder + readback tests |
| Asset truth weak | P0 | 没有真母题/采分点，UI 再好也是空 | Asset Gate 必须先过，缺项只能 mock |
| Authority drift | P0 | 前端或事件流一旦算分，会长出第二套学情 | ViewModel contract + authority tests |
| Trust overclaim | P0 | 主观题批改如果装作绝对准确，会伤害用户信任 | score range、confidence、uncertain、needs_review |
| OCR cost creep | P0 | 拍照批改最容易烧成本并污染 truth | OCR preview-only default + cost gate |
| False WeChat pass | P0 | `/wechat-harness` 绿不等于真实小程序绿 | WeChat Gate 拆 project root / subpackage / page / auth |
| Scenario blind spot | P1 | 只测 happy path 会误判可发布 | Scenario Coverage Gate |
| Design generic | P1 | 变成普通 AI 卡片/功能宫格，用户不知道下一步 | Screen spec + visual review |
| Observability gap | P1 | P0A 结束无法判断是否进 P0B | Decision package requires metrics |
| Rollback weak | P1 | 坏母题或坏入口无法快速关掉 | case_family flag + OCR kill switch |
| Privacy ambiguity | P1 | 删除图片、导出记录、证据保留边界不清会造成合规和信任问题 | Privacy Gate |

## 4. Strengthened Delivery Rule

P0A 不以“页面做完”为完成，而以以下证据闭环完成：

```text
case_family asset reviewed
-> ViewModel fixture frozen
-> screen spec reviewed
-> contract tests pass
-> scenario matrix pass
-> grading evidence write/readback pass
-> true WeChat entry pass or explicit pending
-> release gate checklist complete
-> decision package signed
```

任何一个环节缺失，都不能写成 P0A GO。

## 5. Uncertainties And Validation

| Uncertainty | Default decision | Validation | Alternative |
| --- | --- | --- | --- |
| `wx_miniprogram` 与 `yousenwebview/packageDeeptutor` 哪个是开发 source of truth | 默认 true-entry 以 `yousenwebview/packageDeeptutor` 验收，WS0 拍板开发树 | 查最近上传源、同步 manifest、产品负责人确认 | 若 `wx_miniprogram` 为开发源，必须建立到 `yousenwebview/packageDeeptutor` 的同步证据 |
| 首个母题是否用防水 | 默认 F16 防水工程 spike | 资产 gate + existing artifact spot check | 质量验收或危大工程替换，但必须证明 1-1.5 周可打穿 |
| rubric_compiler / registry 资产能否直接喂 P0A | 默认先抽样验证再复用 | 抽 10 题人工盲审 source_refs 与 scoring_point 质量 | 退回 published registry 子集 + 防水扩产 |
| 半写 task_scope 是否需要改 grading kernel | 默认先裁剪 rubric 输入或标记 not_evaluated，不动 kernel | hermetic test 验证 scoped grading | 不可行则半写降级为 preview/diagnostic，不写 evidence |
| OCR 是否写 learning_evidence | 默认不写长期 truth | OCR provenance + user confirmation + readback audit | P0A 只做 preview/diagnostic |
| 批改置信度阈值 | 默认 conservative | 50-100 attempt shadow + dispute rate | 高风险全进 review_candidate |
| 用户是否愿意半写 | 默认轻练引导到半写 | 5 人可用性测试 + completion rate | 半写拆成多步结构化输入 |
| 成本是否可控 | 默认 OCR 低频 | per-flow cost ledger | 禁用 OCR，只保留手输 |
| 真微信入口能否及时闭合 | 默认必须闭合才能 GO | DevTools CLI + target page + auth evidence | true-entry pending -> WEAK-GO/NO-GO |
| 隐私能力 P0A/P0B 边界 | 默认删除上传图片 P0A，导出可 P0B | legal/product review | P0A 写清 deferred copy 和人工处理 |

## 6. Expert Recommendation

当前建议：

1. 继续推进 P0A，不扩大到完整五 Tab 或 30-40 母题。
2. 把 `Scenario Coverage Gate` 加入 release gate 和 decision package。
3. 进入代码前先冻结 source tree decision、concept authority map、task_scope evidence rule、mistake_tag schema path。
4. 先做 F16 内容下的「每日留存闭环」spike（验证回访），再扩到 3-5 个 `case_family` 资产与案例题深度层。
5. 先做 Web shadow / mock fixtures，再做 `yousenwebview` root + `packageDeeptutor` true-entry smoke。
6. P0A 结束必须给出 GO / WEAK-GO / NO-GO，不允许凭体验主观扩 P0B。

## 7. GSTACK REVIEW REPORT

CEO verdict: HOLD SCOPE. The plan is ambitious enough if it proves the scoring loop; expanding now would reduce deliverability.

Engineering verdict: Accept with hardening. Add scenario coverage, fixture freeze, authority tests, cost attribution, true-entry evidence, and rollback.

Design verdict: Accept with visual gate. Require concrete screens and state coverage before frontend implementation.

Final verdict: P0A is the best current path. It should proceed only as a gated vertical slice, not as a broad mobile rewrite.
