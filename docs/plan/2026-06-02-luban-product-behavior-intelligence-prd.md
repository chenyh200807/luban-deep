# PRD：鲁班 Product Behavior Intelligence 产品行为智能系统

- 状态：Proposed v0.4
- 日期：2026-06-02
- 复审：2026-06-02，按 CEO / 产品 / 工程 / 设计 review 加固场景矩阵、P0 触点、数据质量、运营队列、不确定性验证；v0.3 再按工程现实校准，收敛到复用现有 `surface-telemetry` 通路；v0.4 按执行计划工程复审收口为独立 `product_behavior.db` + indexed raw read model，daily/hourly aggregate 延后到 P1 或 volume gate
- 归属主线：BI / 会员经营后台、学习工作台、Observability
- 产品表面：鲁班智考微信小程序、`yousenwebview`、Web、BI 后台
- 当前数据策略：P0 内部经营分析 raw mode，不做脱敏
- 相关计划：
  - [2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md](2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md)
  - [2026-05-26-luban-learner-workspace-notebook-calendar-prd.md](2026-05-26-luban-learner-workspace-notebook-calendar-prd.md)
  - [2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md](2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md)
  - [2026-05-20-luban-learning-report-read-model-execution-plan.md](2026-05-20-luban-learning-report-read-model-execution-plan.md)

## 1. 结论

鲁班现在需要的不是零散埋点，也不是先接一个第三方看板把点击数画出来，而是一套产品行为事实系统：

> Product Behavior Intelligence = 用同一份行为事实，回答用户喜欢什么、在哪里困惑、哪些模块带来学习行动、哪些路径带来留存和付费可能。

P0 的目标很明确：

1. 系统性记录学员打开历史几次、学情几次、学情内哪个模块用得最多。
2. 区分普通访问、深度查看、行动转化、闭环完成，避免把高频困惑误判成受欢迎。
3. 把行为事实投影到 BI，让创始人、产品、运营每天能看同一套口径。
4. 不让行为事件成为第二套 learner state、第二套学习证据或第二套推荐 authority。

推荐路线：

1. 建自有 canonical `product_behavior_events` ledger。
2. 不新建第二套 SDK / endpoint；复用现有三端 `surface-telemetry` transport 和 `/api/v1/observability/surface-events`，在其后端通路增加产品行为 catalog 和持久化分支。
3. 保留现有 `SurfaceEventStore` 内存 ACK smoke 能力；产品行为持久化只作为同一 ingestion authority 的下游 writer。
4. BI 后台 P0 消费 indexed raw read model 派生的 module / section / funnel / cohort 指标，并注册进现有 `BI_METRICS`；daily/hourly aggregate 不作为 P0 硬依赖。
5. 如后续需要 PostHog、Amplitude、Mixpanel，只从 canonical ledger 做可选投影，不把第三方工具当 authority。

### 1.1 v0.3 复审后的关键加强

v0.1 方向正确，但仍偏“行为分析系统设计”，还不够像一份能落地、能验收、能指导运营动作的计划。v0.2 先做产品/运营/数据质量收紧；v0.3 再做工程现实校准：

1. **从“记录点击”升级为“判断用户行为含义”**：同一个高频打开，可能代表喜欢、困惑、入口不清、功能失败或学习依赖。计划必须输出判断框架，而不是只输出次数。
2. **P0 触点收窄到最有价值的 6 条真实路径**：历史、学情、学情 section、学情到训练、历史到复盘、训练到复测。先把这 6 条打穿，再扩展热图和复杂漏斗。
3. **增加可处理运营队列**：BI 不只显示趋势，还要把“高频看学情但不训练”“训练后不复测”“只对话不看学情”等用户列成队列。
4. **增加数据质量门**：事件漏报、重复、乱序、离线补发、session 断裂、客户端版本漂移都要有处理策略，否则数字会很快失信。
5. **把不确定性显式列为验证任务**：session_id、release_id、可见曝光、`yousenwebview` surface、Supabase 写入负载、BI 图表能力都不假设已满足。
6. **v0.3 工程现实校准**：现有代码已经有 `web/lib/surface-telemetry.ts`、小程序 / `yousenwebview` surface telemetry helper、`POST /api/v1/observability/surface-events`、`SurfaceEventStore`、`BI_METRICS`、会员运营页和 scrubbed export 审计。P0 的最简路径必须是“复用并加持久化 / 产品语义”，不是再造一套 behavior SDK / behavior endpoint。

## 2. Karpathy Gate

### 2.1 assumptions

本 PRD 采用以下需求解释：

- 用户要的是产品经营判断能力，不只是统计 PV/UV。
- 当前阶段数据用于内部产品和经营分析，用户已明确不需要脱敏。
- 行为记录应覆盖微信小程序、`yousenwebview`、Web 学习表面和 BI 运营面。
- P0 首先打穿历史、学情、对话、训练、笔记、我的等核心模块。
- 学情内必须能细分到 `当前状态 / 为什么 / 下一步 / 证据 / 错题 / 采分点 / 弱点图谱` 等 section。

仍需后续验证：

- 现有 `surface-telemetry` / `/api/v1/observability/surface-events` / `SurfaceEventStore` 哪些字段和语义可直接复用，哪些必须扩展。
- 现有 BI 读模型以 SQLite / 本地 read model 为主；P0 行为 ledger 默认使用独立 `product_behavior.db`，长期是否迁 Supabase/Postgres/aggregate 需按事件量复审。
- 微信小程序和 `yousenwebview` 的用户身份、`visit_id`、`session_id`、app_version 能否稳定取到。
- 是否已有 release_id / build_id 注入前端 runtime 的统一方式。
- BI 当前图表组件是否足以承载漏斗、留存、分群和行为路径。

### 2.2 simplest path

最短路径不是全量行为分析平台，而是：

1. 复用现有三端 `surface-telemetry` helper 和 `/api/v1/observability/surface-events` 作为唯一 transport / ingestion authority。
2. 扩展现有 surface event catalog：在当前 ACK 事件之外增加产品行为事件名，并把 `module / section / action / object_id / visit_id` 放进受控 metadata / schema。
3. 给现有 ingestion 后端增加持久化分支，写入 canonical `product_behavior_events` raw ledger；`SurfaceEventStore` 继续保留为内存 ACK smoke / observability 快照。
4. P0 只覆盖 5 类产品行为：模块打开、section 浏览、深度互动、行动开始、闭环完成。
5. P0 先产出 indexed raw read model 给 BI 读；会员运营页不能做无索引全表扫，也不能在前端重算指标口径。daily/hourly aggregate 仅在 P1 或 volume gate 后引入。
6. BI 先交付三个能力：模块受欢迎度、学情内部热区、用户行为分群，并全部落到 `/bi?tab=member-ops`。

不先做：

- 全量点击热图。
- 通用 A/B 实验平台。
- 第三方埋点 SDK 深度集成。
- 实时推荐系统。
- 自动运营触达。
- 用户画像 LLM 归因。
- 新建第二套 `/api/v1/product-behavior/events` endpoint，除非 Phase -1 证明现有 `surface-events` 因 ACK contract 无法承载产品行为扩展。

### 2.3 change boundary

后续实施允许触碰：

- `web/lib/surface-telemetry.ts` 及既有 BI 展示。
- `web/app/(workspace)/bi/_v2/BiV2Surface.tsx`：P0 不新增一级 section；只有 P1/P2 确实需要独立 `behavior` section 时才触碰。
- `web/app/(workspace)/bi/_v2/BiV2OverviewPanel.tsx`：P1/P2 可做摘要投影；P0 不作为主落点。
- `web/app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx`：P0 展示行为 cohort、用户队列、下钻入口。
- `web/app/(workspace)/bi/_v2/member-ops/Member360Drawer.tsx`：P0 展示单个学员行为时间线和学情 section 使用分布。
- `web/app/(workspace)/bi/_v2/ops/BiV2OpsPanel.tsx`：P1/P2 可做行为数据质量面板；P0 仅在会员运营页展示轻量 data trust 提示。
- `wx_miniprogram/utils/surface-telemetry.js` / `yousenwebview/packageDeeptutor/utils/surface-telemetry.js` 行为上报扩展。
- `deeptutor/api/routers/observability.py`：优先扩展现有 `/surface-events` schema / metadata guard；不默认新增产品事件路由。
- `deeptutor/services/observability/surface_events.py`：扩展 catalog、dedupe、持久化分支，同时不破坏现有 ACK smoke。
- `deeptutor/services/bi_service.py` / `deeptutor/services/bi_metrics.py` 行为指标读模型。
- storage migration：P0 默认独立 SQLite `product_behavior.db` 的 `product_behavior_events` + 索引；聚合表或 materialized view 进入 P1/volume gate。
- 相关 tests、QA 和 docs。

不得顺手触碰：

- `/api/v1/ws` 聊天入口。
- TutorBot runtime 身份体系。
- learner-state canonical write path。
- `learning_evidence` 写入语义。
- `training_intent` 处方 authority。
- wallet / payment / billing authority。

### 2.4 verification target

P0 完成标准：

- 能按用户、日期、surface、module 统计打开次数。
- 能回答“学员打开历史几次、学情几次”。
- 能回答“学情里的哪个 section 用得最多”。
- 能看到从学情 section 到训练 / 复盘 / 复测的转化漏斗。
- 能区分高频访问但不行动的困惑型行为。
- BI 指标有统一 `metric_id` 和口径，不同页面不 hardcode 同名指标。
- 行为事件写入不影响 learner state、学习证据、评分、推荐和钱包。

## 3. 一等业务事实与单一 authority

### 3.1 one business fact

本系统维护的一等业务事实是：

> 学员在真实产品表面上，对哪些学习模块产生了访问、停留、深入、行动和回访行为。

### 3.2 one authority

唯一 authority 是：

> 现有 `surface-telemetry` ingestion authority + versioned product behavior event catalog + `product_behavior_events` raw event ledger。

BI、产品分析、运营分群、漏斗、留存、模块价值分，都从这份 ledger 或其聚合读模型派生。

### 3.3 competing authorities to avoid

禁止出现：

- 前端 localStorage 里单独维护“模块打开次数”并参与 BI 判断。
- 学情 read model 自己统计页面行为。
- `learning_evidence` 被拿来承载点击行为。
- Langfuse trace 被当成产品行为唯一来源。
- 第三方 analytics 成为 canonical truth。
- BI 页面用各自 SQL 重算同名指标。

### 3.4 canonical path

```text
真实产品表面
  -> existing surface-telemetry helper
  -> POST /api/v1/observability/surface-events
  -> SurfaceEventStore ACK snapshot (kept for observability smoke)
  -> product behavior persistence writer
  -> product_behavior_events
  -> product_behavior_visits / product_behavior_module_daily
  -> existing BI_METRICS / BI read model
  -> BI 看板 / 运营分群 / 产品复盘
```

### 3.5 thin wrapper / fat skill split

- Thin wrapper：现有前端 surface-telemetry helper、API router、transport retry、schema validation、auth binding、basic dedupe。
- Fat authority：`ProductBehaviorEventCatalog`、`ProductBehaviorPersistenceWriter`、`ProductBehaviorMetricsReader`。

wrapper 不允许临时拼事件含义，不允许按按钮文案推断业务模块，不允许在前端发明新 event_name。

## 4. 当前数据策略：raw mode，不做脱敏

用户已明确当前数据不需要脱敏，因此 P0 采用 raw mode：

1. 内部行为分析表不对 `user_id`、手机号、昵称、班级、会员状态等经营分析所需字段做 hash、mask 或 redaction。
2. BI 后台可直接按真实用户身份、手机号、会员状态、来源、surface 做筛选和下钻。
3. 导出数据默认也保留原始字段，便于人工复盘和运营跟进。
4. 只有在对外共享、第三方投影、公开报告、或训练外部模型时，才另行定义脱敏/汇总策略。

但 raw mode 不等于无边界采集：

1. 行为表只采集产品行为与分析必要上下文。
2. 不采集密码、支付凭证、验证码、身份证、银行卡、完整聊天正文、完整主观题答案正文。
3. 如需定位某次作答或对话，记录 `session_id / turn_id / attempt_id / object_id`，不要把全文复制进行为表。
4. 后台访问 raw behavior data 必须沿用 admin 权限和 audit 规则。
5. 事件 catalog 中每个字段必须标注 `required / optional / forbidden`，防止前端随手塞大 payload。

这条策略的本质是：当前不做脱敏，但仍做字段治理和权限治理。

## 4.5 使用场景矩阵与 P0 触点

### 4.5.1 核心角色

| 角色 | 真正要回答的问题 | 不能只看的数字 | P0 输出 |
| --- | --- | --- | --- |
| 创始人 / 老板 | 用户到底在用哪个模块，哪个模块带来行动 | 打开次数 | 模块价值分、7 日回访、行动转化、异常提示 |
| 产品 | 学情、历史、训练路径哪里断 | PV / UV | section 热度、quick exit、路径漏斗、版本对比 |
| 运营 / 班主任 | 今天应该跟进谁，为什么 | 总活跃用户 | 可处理用户队列、用户最近行为时间线 |
| 教研 | 用户反复看什么、卡在哪类知识点 | 模块总量 | section + object_id + attempt_id 聚合，后续可回题目/知识点 |
| 工程 / QA | 新版本是否让用户路径断裂 | 后端 trace 成功 | Web 可做 A 级 release_id 漏斗；小程序 P0 先用 ENV_VERSION / systemInfo.version 降 B 级，直到 build_id 注入 |
| 增长 / 销售 | 哪些行为预示续费、转化或流失 | 单次访问 | 行为 cohort、回访、沉默、完成闭环 |

### 4.5.2 P0 只打穿 6 条真实路径

P0 不追求“所有按钮都埋”。先打穿下表，才算可交付：

| 路径 | 起点 | 终点 | 必须回答 |
| --- | --- | --- | --- |
| 历史使用 | `history.module_viewed` | `history.module_exited` | 学员打开历史几次、停留多久、是否进入复盘 |
| 学情使用 | `learning_report.module_viewed` | `learning_report.module_exited` | 学员打开学情几次、是否快速退出 |
| 学情 section | `learning_report.section_viewed` | `section_expanded` | 学情里哪个模块/section 用得最多 |
| 学情到训练 | `next_action.section_viewed` | `learning_action_started:start_training` | 学情是否真的推动训练 |
| 历史到复盘 | `history.object_opened` | `learning_action_started:start_review` | 历史是否承接复盘 |
| 训练到复测 | `learning_action_completed:training` | `learning_action_started:start_retest` | 训练后是否形成验证闭环 |

### 4.5.3 场景举一反三

| 现象 | 可能含义 | 需要的二级证据 | 产品动作 |
| --- | --- | --- | --- |
| 学情打开高、训练低 | 用户关心结果但不知道下一步 | `next_action` 曝光率、按钮点击率、quick exit | 强化下一步行动入口 |
| 历史打开高、复盘低 | 历史被当检索，不是学习闭环 | object_opened、review_started | 历史卡片增加“复盘这次错误” |
| 对话高、学情低 | 对话入口强，学情 discoverability 弱 | chat_only cohort | 对话后推送学情摘要 |
| 采分点高、复测低 | 用户记知识点但不验证 | score_points -> retest funnel | 采分点卡增加同类题 |
| 证据点击低 | 用户不关心证据，或证据不可见 | evidence section 曝光、展开率 | 证据默认折叠程度调整 |
| 学情 quick exit 高 | 首屏太复杂或加载慢 | visible_ms、event_error、release_id / app_version | 先排 UX / 性能，不急着改内容 |
| 某版本漏斗骤降 | release regression | Web: release_id；小程序: ENV_VERSION + systemInfo.version，P0 B 级 | 进入 release gate / rollback 判断 |

## 5. Event Catalog

### 5.1 P0 event list

| event_name | 触发时机 | 核心问题 |
| --- | --- | --- |
| `module_viewed` | 用户进入一级模块 | 哪些模块最受欢迎 |
| `section_viewed` | 用户看到模块内 section | 模块内哪个区域最常用 |
| `section_expanded` | 用户展开卡片、点开证据、打开详情 | 是否有深度兴趣 |
| `learning_action_started` | 用户从模块进入训练、复盘、复测、收藏 | 是否产生下一步行动 |
| `learning_action_completed` | 训练、复盘、复测、收藏完成 | 是否形成闭环 |
| `module_returned` | 用户从行动或详情返回原模块 | 是否形成回看 |
| `module_exited` | 用户离开模块 | 是否快速退出 |
| `event_error` | 上报失败或页面关键请求失败 | 数据质量和体验异常 |

### 5.2 P0 module taxonomy

| module | 说明 |
| --- | --- |
| `learning` | 学习首页 / 今日处方 |
| `history` | 历史记录 / 历史对话 / 作答复盘 |
| `chat` | 对话主入口 |
| `learning_report` | 学情 |
| `notebook` | 笔记 / 收藏 / 采分点手册 |
| `practice` | 训练 / 同类题 / 复测 |
| `assessment` | 摸底 / 专题测评 |
| `profile` | 我的 / 账户 / 会员 |

### 5.3 learning_report section taxonomy

| section | 说明 |
| --- | --- |
| `current_state` | 当前状态 |
| `why` | 为什么这样 |
| `next_action` | 下一步做什么 |
| `evidence` | 证据链 |
| `wrong_items` | 错题 |
| `score_points` | 采分点 |
| `weakness_map` | 弱点图谱 |
| `trend` | 趋势 |
| `study_plan` | 学习计划 / 今日任务 |
| `retest` | 复测 |

### 5.4 action taxonomy

| action | 说明 |
| --- | --- |
| `view` | 进入、曝光、可见 |
| `expand` | 展开 |
| `open_detail` | 打开详情 |
| `start_training` | 开始训练 |
| `start_review` | 开始复盘 |
| `start_retest` | 开始复测 |
| `save_note` | 保存笔记 |
| `dismiss` | 关闭 / 忽略 |
| `return` | 回到上一模块 |
| `complete` | 完成 |
| `error` | 错误 |

## 6. Raw Event Schema

P0 raw event 字段：

```text
event_id
event_name
event_version
occurred_at
received_at
user_id
visit_id
session_id
turn_id
attempt_id
surface
module
section
action
object_type
object_id
entry_source
referrer_module
duration_ms
visible_ms
scroll_depth
result
error_code
release_id
app_version
platform
device_model
network_type
properties_json
```

字段规则：

- `event_id` 由客户端生成，服务端 dedupe。
- `event_version` 用于 catalog 演进。
- `surface` P0 直接沿用现有白名单：`web`、`wechat_miniprogram`、`wechat_yousenwebview`。`bi` 不进入产品行为同表；BI 操作继续走 admin audit。
- `visit_id` 是客户端导航会话，用于页面浏览、quick exit、section path；`session_id / turn_id` 是可选 turn/chat 关联字段，不能拿 turn session 替代导航 session。
- `properties_json` 只能放 catalog 允许字段，禁止任意 JSON dump。
- `duration_ms`、`visible_ms` 可后续补齐，P0 可先只记录进入和退出。
- `anonymous_id` 不在 P0 schema 中，只作为长期 reserved 概念；当前产品按登录态行为交付。

### 6.1 identity / sessionization

行为分析最容易失真的地方不是 event_name，而是身份和会话断裂。P0 需要明确：

| 问题 | P0 策略 | 替代方案 |
| --- | --- | --- |
| 登录前行为 | P0 不做匿名行为；只统计已登录用户。`anonymous_id` 标 reserved，不写入正式指标 | 长期确需首访追踪时，另立 device_id + login merge 方案 |
| 多端同一用户 | `user_id` 为主，`surface + device_model + app_version` 做维度 | P0 不做跨设备路径还原，只做用户级聚合 |
| visit 边界 | 客户端生成 `visit_id`，30 分钟无行为断 visit，或 app 冷启动新 visit | 若客户端 visit 不稳定，服务端按 `(user_id, surface, time window)` 重建并降级可信度 |
| turn session 关联 | `session_id / turn_id` 只在行为关联聊天、复盘、作答时带 | 缺失时只进产品漏斗，不进 trace 关联分析 |
| release_id 缺失 | Web P0 争取 A 级；小程序 / `yousenwebview` P0 允许 `unknown_release`，用 ENV_VERSION / systemInfo.version 降 B 级 | P1 注入 build_id 后再升 A |

### 6.2 数据质量策略

P0 必须承认客户端事件天然不完美，因此要有数据质量层：

| 失败模式 | 处理 |
| --- | --- |
| 重复上报 | `event_id` primary key + server dedupe |
| 离线补发 | 保留 `occurred_at` 和 `received_at`，聚合用 `occurred_at`，监控延迟 |
| 乱序事件 | 漏斗按时间窗口和 event sequence 重建，不假设严格顺序 |
| 客户端漏报 exit | 用下一次 module_viewed / session timeout 推断 `inferred_exit`，标 `quality=derived` |
| 版本字段缺失 | 指标可信等级降 B，不参与 release regression 判断 |
| payload 过大 | ingestion fail-closed，记录 `event_error` |
| catalog 漂移 | 非 catalog event 拒收或进入 quarantine，不进正式指标 |
| surface taxonomy 漂移 | 沿用现有三值 surface 白名单；新增 surface 必须先改 catalog 和 guard |

### 6.3 指标可信等级

所有 BI 指标必须标可信等级：

| 等级 | 条件 | 用途 |
| --- | --- | --- |
| A | event catalog 完整、visit_id 完整、release_id 完整、漏报率在阈值内 | 经营判断、版本对比、运营队列 |
| B | 关键字段缺失但仍可聚合 | 趋势参考，不做强结论 |
| C | 样本小、session 断裂、版本不明 | 只做异常提示，不能进决策 |

如果 BI 不展示可信等级，P0 不算完成。

## 7. Metrics

### 7.1 基础模块指标

| metric_id | 口径 |
| --- | --- |
| `behavior.module.open_count` | 模块打开次数 |
| `behavior.module.active_users` | 打开过模块的去重用户数 |
| `behavior.module.return_7d_rate` | 7 天内再次打开同模块的用户比例 |
| `behavior.module.avg_visible_ms` | 模块平均可见时长 |
| `behavior.module.quick_exit_rate` | 小于阈值即退出的比例 |

### 7.2 学情指标

| metric_id | 口径 |
| --- | --- |
| `behavior.learning_report.section_view_count` | section 浏览次数 |
| `behavior.learning_report.section_active_users` | section 去重用户数 |
| `behavior.learning_report.deep_rate` | section 展开 / 详情 / 证据点击比例 |
| `behavior.learning_report.action_start_rate` | 从学情进入训练、复盘、复测的比例 |
| `behavior.learning_report.loop_completion_rate` | 从查看学情到完成训练/复测的闭环比例 |

### 7.3 行动漏斗指标

| metric_id | 口径 |
| --- | --- |
| `behavior.funnel.report_to_training` | 学情浏览 -> 训练开始 |
| `behavior.funnel.history_to_review` | 历史打开 -> 复盘开始 |
| `behavior.funnel.score_point_to_practice` | 采分点查看 -> 同类题训练 |
| `behavior.funnel.training_to_retest` | 训练完成 -> 复测开始 |
| `behavior.funnel.retest_to_report_return` | 复测完成 -> 回到学情 |

### 7.4 模块价值分

只看打开次数会误判。P1 引入 `module_value_score`：

```text
module_value_score =
  coverage_score
  + depth_score
  + action_conversion_score
  + return_score
  + loop_completion_score
  - quick_exit_penalty
  - repeated_no_action_penalty
  - error_penalty
```

解释：

- 高频打开 + 高行动转化 = 真受欢迎。
- 高频打开 + 高退出 + 低行动 = 困惑或找不到答案。
- 低打开 + 高转化 = 入口 discoverability 问题。
- 高打开 + 高错误 = 体验或稳定性问题。

## 8. BI 看板

### 8.1 创始人视图：模块受欢迎度

回答：

- 今天 / 7 天 / 30 天用户最常打开哪些模块。
- 用户首个登录 visit 先用哪些模块，老用户回访哪些模块。
- 哪些模块访问高但行动低。
- 哪些模块访问低但转化高。

核心组件：

- 模块排行表。
- 趋势折线。
- 新老用户分层。
- 模块价值分。
- 高风险模块提示。

### 8.2 产品视图：学情内部热区

回答：

- 学情里哪个 section 最常被看。
- 哪些 section 被展开最多。
- 用户是否看证据。
- 用户是否从学情进入训练、复盘、复测。
- 哪些 section 打开后流失最高。

核心组件：

- 学情 section ranking。
- `section -> action` 漏斗。
- 证据点击率。
- 弱点图谱 / 采分点 / 错题热度。
- section quick exit。

### 8.3 运营视图：用户分群

回答：

- 哪些学员高频看学情但不训练。
- 哪些学员高频看历史但不复盘。
- 哪些学员高频对话但从不看学情。
- 哪些学员完成训练但不复测。
- 哪些学员沉默、回访下降或只看账户页。

P0 分群：

| cohort | 规则 |
| --- | --- |
| `report_high_no_action` | 7 天内学情 >= 3 次，训练/复测 = 0 |
| `history_high_no_review` | 历史 >= 3 次，复盘 = 0 |
| `chat_only` | 对话 >= 3 次，学情 = 0 |
| `training_no_retest` | 训练完成 >= 1，复测 = 0 |
| `dormant_after_assessment` | 测评完成后 7 天无行动 |

### 8.4 运营队列与动作边界

P0 只产出“建议跟进队列”，不自动触达、不自动改学习计划、不自动影响会员状态。

| 队列 | 进入条件 | 建议动作 | 禁止动作 |
| --- | --- | --- | --- |
| 学情高频无行动 | 7 天学情 >= 3，训练/复测 = 0 | 人工问是否看不懂下一步，或推送“从这题开始练” | 自动改 mastery |
| 历史高频无复盘 | 7 天历史 >= 3，复盘 = 0 | 引导从历史错题进入复盘 | 自动生成错因 |
| 对话孤岛 | 7 天对话 >= 3，学情 = 0 | 对话结束后提醒查看学情总结 | 强制跳转 |
| 训练未复测 | 训练完成后 48h 未复测 | 提醒复测验证 | 把训练完成当掌握 |
| 测评后沉默 | 测评完成后 7 天无学习行为 | 运营跟进或简化首个任务 | 自动扣费/降级 |

### 8.5 判断模板

每个 BI 卡片都应输出“数字 + 解释 + 下一步”，避免只给图：

```text
现象：学情 7 日打开 126 次，环比 +38%。
解释：next_action section 展开率 12%，训练开始率 3%，说明用户看结果但没有形成行动。
下一步：检查学情首屏行动入口；抽 10 个 report_high_no_action 用户看具体路径。
可信等级：A。
```

### 8.6 必须落到现有 `/bi` 页面

Product Behavior Intelligence 的 P0 不是单独做一个离线报表，也不是另起一个管理后台。它必须落到当前真实 BI v2 页面：

- BI 入口：`/bi`
- Shell：`web/app/(workspace)/bi/_v2/BiV2Surface.tsx`
- 当前一级 section：`overview / member-ops / commerce / feedback / ops`
- 当前展示容器：
  - `BiV2OverviewPanel.tsx`
  - `BiV2MemberOpsPanel.tsx`
  - `BiV2OpsPanel.tsx`

P0 推荐不要新增一级 `behavior` section，也不要先分散到多个 BI 页面。用户明确要求：

> 加到 BI 页面里的会员运营页面里。

因此 P0 的唯一主落点是：

- `/bi?tab=member-ops`
- `web/app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx`
- 会员详情下钻：`web/app/(workspace)/bi/_v2/member-ops/Member360Drawer.tsx`

`经营总览` 和 `系统运维` 只作为 P1/P2 的摘要投影，不作为 P0 交付目标。

| BI 位置 | P0 展示 | 为什么放这里 | 验收 |
| --- | --- | --- | --- |
| `会员运营` / 页面顶部 | 行为健康条：学情打开、历史打开、训练转化、复测断点 | 运营进入页面先知道今天用户行为是否正常 | `/bi?tab=member-ops` 首屏可见 |
| `会员运营` / 筛选区 | 行为 cohort tabs：学情高频无行动、历史高频无复盘、只对话不看学情、训练未复测 | 直接变成可跟进用户队列 | 切换 cohort 后会员表过滤 |
| `会员运营` / 会员表 | 行为列：历史次数、学情次数、最近行为、行为风险、下一步建议 | 不用进抽屉也能判断谁要跟进 | 表格列可配置，默认露出关键行为列 |
| `会员运营` / 学员 360 抽屉 | 最近行为时间线、学情 section 热点、行动漏斗、原始事件下钻 | 运营查看单个用户的完整证据 | 点击会员后能看到该用户行为事实 |
| `会员运营` / 行动作业区 | 记录跟进、加入队列、标记已联系 | 行为分析要连到运营动作 | 写既有 audited ops action |

P1 以后才考虑在 `经营总览` 做摘要，或在 `系统运维` 做数据质量面板。只有在以下条件满足时才新增一级 `behavior` section：

1. Overview / Member Ops / Ops 三处已经拥挤，无法承载行为分析。
2. 行为分析有独立日常 owner。
3. 行为分析需要复杂路径图、cohort builder、长期趋势和第三方 projection 管理。
4. 新增 section 不会破坏 BI v2 “5 主区”信息架构。

### 8.7 BI 页面具体组件拆分

P0 最小组件建议：

| 组件 | 挂载位置 | 内容 |
| --- | --- | --- |
| `BiMemberBehaviorHealthStrip` | `BiV2MemberOpsPanel` 顶部 | 模块活跃、学情转行动率、quick exit、可信等级 |
| `BiMemberBehaviorCohortTabs` | `BiV2MemberOpsPanel` 筛选区 | 学情高频无行动、历史高频无复盘、只对话不看学情、训练未复测 |
| `BiMemberBehaviorColumns` | `BiV2MemberOpsPanel` 表格列配置 | 历史次数、学情次数、最近行为、行为风险、下一步建议 |
| `BiBehaviorCohortQueue` | `BiV2MemberOpsPanel` | `report_high_no_action` 等队列 |
| `BiMemberBehaviorTimeline` | `Member360Drawer` | 单个学员最近行为时间线 |
| `BiMemberLearningReportBreakdown` | `Member360Drawer` | 单个学员学情 section 使用分布 |
| `BiBehaviorDataTrustMini` | `BiV2MemberOpsPanel` 底部或提示条 | event 延迟、漏报、trust level 简要提示 |

这些组件必须复用现有 BI v2 设计语言和基础组件，不另造一套 dashboard shell。

### 8.8 BI raw mode 与现有 UI 的冲突点

当前计划采用 raw mode 不脱敏，但现有 BI 某些 UI/导出路径已经有 masking / scrubbed export 的历史约束。后续实施必须显式处理，不允许静默沿用：

| 现状 | 对 Product Behavior 的要求 |
| --- | --- |
| `BiV2MemberOpsPanel` 当前会员列表存在手机号 masked 展示逻辑 | 行为用户级下钻如需要手机号，必须明确用 raw behavior detail 或 drawer 展示，不能让用户以为拿到的是原始字段 |
| `BiV2OpsPanel` 现有导出文案偏 scrubbed export | 行为数据导出需单独标 `raw_mode=true`、写 audit，并在 UI 明示 raw export |
| `bi.export.request` 现有安全契约偏脱敏/限频 | 行为 raw export 可以保留限频和 audit，但不默认 scrub 字段 |
| Overview 现有指标来自 `bi_service` | 行为指标也必须进入 metric registry，不允许前端临时算 |

结论：raw mode 是本计划的当前产品要求，但 BI 页面必须清楚告诉操作者“这是 raw behavior data”，并写入 audit。

## 9. Data Model

### 9.1 raw table

```sql
product_behavior_events (
  event_id text primary key,
  event_name text not null,
  event_version integer not null,
  occurred_at timestamptz not null,
  received_at timestamptz not null default now(),
  user_id text,
  visit_id text,
  session_id text,
  turn_id text,
  attempt_id text,
  surface text not null,
  module text not null,
  section text,
  action text not null,
  object_type text,
  object_id text,
  entry_source text,
  referrer_module text,
  duration_ms integer,
  visible_ms integer,
  scroll_depth numeric,
  result text,
  error_code text,
  release_id text,
  app_version text,
  platform text,
  device_model text,
  network_type text,
  properties_json jsonb not null default '{}'::jsonb
)
```

### 9.2 P0 indexed raw read model and deferred aggregates

P0 不强行建设 daily/hourly aggregate tables。会员运营页默认读服务端 `product_behavior_store` 的 indexed raw read model + 最近 raw sample；禁止前端直接扫 `product_behavior_events` raw ledger，禁止无索引全表扫。

Phase -1 必须先记录行为事实底座与现有 BI/member read model 的关系：

| 方案 | 适用条件 | 风险 |
| --- | --- | --- |
| P0 raw ledger 独立落 `product_behavior.db`，服务端 indexed raw read | 当前实现速度和会员运营页 join 简单优先 | 长期事件量上来后需要迁移或 aggregate |
| raw 和 aggregate 都在 Supabase/Postgres | 长期事件量和 JSONB 查询优先 | 会员运营页与现有 SQLite/member 数据跨库 join 成本高 |
| raw 在 Postgres，aggregate 同步到现有 BI/read model | 会员运营页查询性能和 join 简单优先 | 双写/同步需要明确 authority 和延迟 |

默认推荐：P0 先用独立 `product_behavior.db`，与 session/chat SQLite 文件分离，避免行为写入争用核心聊天/session 单写锁。Phase -1 用 100 / 1000 / 50000 DAU 三档事件量和 `/bi?tab=member-ops` join 成本记录升级阈值；未完成前不允许建设聚合表或跨库同步。

P1/volume gate 后的候选聚合表：

- `product_behavior_module_daily`
- `product_behavior_section_daily`
- `product_behavior_user_daily`
- `product_behavior_funnel_daily`
- `product_behavior_cohorts_daily`

### 9.3 indexes

最小索引：

- `(occurred_at)`
- `(user_id, occurred_at)`
- `(visit_id, occurred_at)`
- `(module, occurred_at)`
- `(module, section, occurred_at)`
- `(surface, occurred_at)`
- `(event_name, occurred_at)`

## 10. 权限与审计

因为 P0 raw mode 不脱敏，权限必须明确：

1. 普通学员端不能读取行为表。
2. BI 行为分析只允许 admin / operator 角色读取。
3. 用户级下钻、导出、运营分群查看应写 admin audit。
4. 第三方投影默认关闭，开启前必须单独列字段白名单。
5. 对外报告只能用聚合指标，不直接导出 raw user-level data。

## 11. 与既有系统的关系

### 11.1 learning_report

`GET /api/v1/mobile/learning-report` 仍是学情 read model authority。行为系统只记录用户是否看了某个 section、是否从 section 进入行动，不改学情结论。

### 11.2 learning_evidence

`learning_evidence` 只记录学习事实。行为事件不能直接写 `learning_evidence`。只有当训练、作答、复测产生真实学习结果时，才由原有 authority 写入学习证据。

### 11.3 training_intent

`training_intent` 仍是下一步训练处方 authority。行为事件可以衡量处方是否被点击、开始、完成，但不自行生成处方。

### 11.4 observability

Observability 记录系统是否正确运行。行为系统记录用户是否真实使用。两者不能互相替代，但 P0 transport / ingestion authority 必须复用现有 surface telemetry 通路：

- `web/lib/surface-telemetry.ts`
- `wx_miniprogram/utils/surface-telemetry.js`
- `yousenwebview/packageDeeptutor/utils/surface-telemetry.js`
- `POST /api/v1/observability/surface-events`
- `deeptutor/services/observability/surface_events.py`

修正后的关系是：

1. surface telemetry endpoint 仍负责 auth、rate limit、payload size cap、schema validation、event_id dedupe。
2. `SurfaceEventStore` 继续负责内存 ACK snapshot / observability smoke，不承担长期产品行为分析。
3. Product Behavior 在同一 ingestion authority 下增加持久化 writer 和产品 event catalog。
4. 产品行为事件通过 `visit_id / session_id / turn_id / release_id / surface` 与 observability 关联；缺字段时降级可信等级。

### 11.5 BI

BI 是行为事实的主要消费面，不是写入 authority。BI 可以消费服务端 read model 做筛选、下钻、分群、导出，但不能在前端重算指标口径。

P0 必须复用现有 BI authority：

- 指标定义注册进 `deeptutor/services/bi_metrics.py` 的 `BI_METRICS`，前端继续消费 generated registry。
- `trust_level` 复用 `BIMetricDefinition.trust_level`，不另建一套可信等级字段。
- 会员运营页复用现有 `BiV2MemberOpsPanel`、`Member360Drawer`、audited ops action 和可配置表格列。
- P0 行为 read model 使用独立 `product_behavior.db` 的 indexed raw reads；会员运营页通过 member API / `MemberConsoleService` 批量读取行为 summary，避免 N+1。

## 12. 第三方工具策略

P0 不强依赖第三方 analytics。

允许后续接：

- PostHog：session replay、funnel、feature flag、heatmap。
- Amplitude：产品漏斗和留存。
- Mixpanel：轻量行为看板。

接入规则：

1. canonical truth 仍是 `product_behavior_events`。
2. 第三方只接 projection。
3. raw mode 对第三方不自动继承；对外发送哪些字段需另行审批。
4. 第三方事件名必须由 catalog 生成，不能再维护一套命名。

## 13. 实施阶段

### Phase -1：Reality Audit

实施前先做只读审计，不写代码：

1. telemetry authority audit：确认现有 `surface-telemetry`、`/api/v1/observability/surface-events`、`SurfaceEventStore`、小程序 / `yousenwebview` helper 的字段、guard、测试和消费方。
2. storage / join audit：确认 P0 独立 `product_behavior.db`、indexed raw reads、member console 批量 summary 是否满足当前事件量；必须回答 `/bi?tab=member-ops` 如何把会员基础数据和行为 cohort/时间线 join 到一起，以及何时升级到 aggregate。
3. section visibility spike：验证 Web IntersectionObserver 与小程序 `wx.createIntersectionObserver` / `yousenwebview` 的 section 曝光口径是否能做到 A 级一致。
4. identity / visit audit：确认微信 / `yousenwebview` / Web 是否能提供 `user_id`、`visit_id`、可选 `session_id`、app_version、release_id / build_id。
5. release field audit：明确 Web、小程序、`yousenwebview` 的 release_id / ENV_VERSION / systemInfo.version 可用性和可信等级。
6. 确认 `/wechat-harness` 是否能代表 P0 可见行为触点。
7. 确认写入量预算：按 100 DAU、1000 DAU、50000 会员三档估算事件量；尤其估算学情一次打开产生 10-50 条 section event 时的 0.5M-2.5M/day 级别压力。
8. 确认 BI 前端是否已有漏斗、排行、队列表格组件。

输出：

- `docs/qa/<date>-product-behavior-reality-audit.md`
- P0 触点是否全部可采集。
- storage / join 决策。
- section 曝光可信等级。
- 是否需要先做 fallback 方案。

### Phase 0：Tracking Plan

交付：

- event catalog。
- module / section / action taxonomy。
- raw mode 字段策略。
- metric registry。
- QA checklist。

验收：

- 每个 P0 事件都有 owner、触发时机、必填字段、禁止字段。
- 学情 section taxonomy 能回答“学情哪个模块用最多”。

### Phase 1：Ingestion + Raw Ledger

交付：

- storage migration / read model migration，依据 Phase -1 storage / join 决策执行。
- 扩展现有 `/api/v1/observability/surface-events` request schema / metadata guard。
- 扩展 `SurfaceEventStore.ingest` 下游：继续写内存 ACK snapshot，同时调用 product behavior persistence writer。
- 产品 event catalog validation：现有 ACK event 与产品行为 event 分层管理。
- event_id dedupe：沿用现有 dedupe 入口，并补持久化层 primary key / conflict handling。

验收：

- 重复 event_id 不重复入库。
- 非 catalog event fail-closed。
- raw mode 字段可在 BI 下钻。
- 1000 条合成事件写入后，indexed raw read summary 与 fixture 期望一致。
- 离线补发事件按 `occurred_at` 归入正确日期。
- 现有 surface ACK smoke 不回退。
- 未新增第二套 behavior endpoint；如确需新增，必须在 Phase -1 report 中证明现有 endpoint 不能承载。

### Phase 2：Client SDK

交付：

- 扩展现有 Web `surface-telemetry` helper。
- 扩展现有微信 / `yousenwebview` `surface-telemetry` helper。
- 客户端 `visit_id` 生成、持久化、30 分钟切分。
- 模块打开、section 浏览、行动开始 / 完成上报。

验收：

- 历史、学情、对话、训练、笔记、我的至少 6 个 module 有 `module_viewed`。
- 学情至少 8 个 section 有 `section_viewed`。
- 训练 / 复盘 / 复测至少 3 条 action funnel 可追。
- 客户端断网后恢复，事件可补发且不重复计数。
- P0 触点每个至少有 1 条 `/wechat-harness` 或真入口 smoke 证据。
- section 曝光若无法三端 A 级一致，BI 必须标 B 级，不允许显示成 A 级事实。

### Phase 3：BI P0

交付：

- 模块受欢迎度。
- 学情内部热区。
- 行动漏斗。
- P0 用户分群。

验收：

- 能按日期、surface、用户、module 下钻。
- 能回答用户原始问题：
  - 学员打开历史几次。
  - 学员打开学情几次。
  - 学情里的哪个 section 用得最多。

### Phase 4：Quality + Cohort

交付：

- module_value_score。
- quick exit / repeated no action 识别。
- 7 日留存。
- 行为与训练闭环相关性。

验收：

- 能区分“真受欢迎”和“困惑高频访问”。
- 能生成运营队列，而不是只给趋势图。

### Phase 5：Scale Decision

P0 不预设一定用 Supabase 长期承载所有事件，也不预设独立 SQLite indexed raw read 能长期承载所有行为查询。上线观察后按数据决定：

| 条件 | 决策 |
| --- | --- |
| 事件量低、查询可控 | 独立 `product_behavior.db` + indexed raw read 继续 |
| 跨库 join 拖慢会员运营页 | 行为 aggregate 同步到 BI read model，同页只读一个 aggregate authority |
| 写入量高但查询简单 | 增加 batch aggregate / outbox |
| BI 查询慢 | 增加 daily/hourly aggregate table，不直接扫 raw table |
| 事件量进入高频行为分析级别 | 评估 ClickHouse / PostHog projection |
| 需要 session replay / heatmap | 只对选定 cohort 接第三方，不改 canonical ledger |

## 14. Release Gates

P0 release 前必须通过：

1. `event_catalog_guard`：事件名、module、section、action 必须来自 catalog。
2. `payload_size_guard`：单事件 payload 不超过预算。
3. `forbidden_field_guard`：禁止字段不能进入 `properties_json`。
4. `dedupe_guard`：重复 event_id 不重复计数。
5. `surface_authority_guard`：P0 复用 `/api/v1/observability/surface-events`；不得新增第二套 behavior endpoint，除非 Phase -1 report 明确批准。
6. `storage_join_decision_guard`：Phase -1 必须定案行为 ledger / indexed raw read model 与现有 BI/member read path 的 join 策略，并记录 aggregate 升级阈值。
7. `visit_id_guard`：纯导航行为必须有 `visit_id` 或服务端重建策略；不能用 turn `session_id` 冒充导航会话。
8. `section_visibility_guard`：学情 section 曝光三端一致性必须有 spike 证据；不可 A 级时 BI 标 B 级。
9. `metric_registry_guard`：BI 展示指标必须注册进 `deeptutor/services/bi_metrics.py` 的 `BI_METRICS`，并生成前端 registry。
10. `authority_guard`：行为事件写入不触碰 learner-state、learning_evidence、wallet。
11. `wechat_harness_smoke`：`/wechat-harness` 可见行为上报。
12. `admin_permission_smoke`：非 admin 不能读 raw behavior BI API。
13. `offline_replay_guard`：离线补发、重复补发、乱序事件必须按 `occurred_at` 归属统计窗口。
14. `trust_level_guard`：BI 指标必须使用 `BIMetricDefinition.trust_level` 并在 UI 展示可信等级。
15. `p0_touchpoint_guard`：6 条 P0 路径至少各有一条自动化或人工 smoke 证据。
16. `bi_member_ops_integration_guard`：`/bi?tab=member-ops` 必须展示行为健康条、行为 cohort tabs、行为列、学员行为时间线和数据可信提示。
17. `raw_export_guard`：行为数据 raw export 必须明示 raw mode，并写 `bi_export_request` audit。

## 15. 风险

| 风险 | 处理 |
| --- | --- |
| 打点膨胀成噪声 | P0 只允许 catalog 事件，非 catalog fail-closed |
| 高频访问被误判为喜爱 | 引入 action conversion、quick exit、loop completion |
| 前端随手塞大 payload | `properties_json` 字段白名单 + payload size guard |
| 行为系统污染学情 | 明确不写 learner-state / learning_evidence |
| raw mode 权限过宽 | BI admin 权限 + audit + 第三方投影另审 |
| 第三方工具反客为主 | 第三方只做 projection，不做 canonical truth |
| 重建第二套 telemetry authority | P0 复用现有 surface telemetry endpoint/helper；新增 endpoint 需 Phase -1 明确批准 |
| visit_id / session_id 混用导致路径失真 | `visit_id` 管导航行为，`session_id / turn_id` 只做 turn 关联；服务端重建时指标降级 |
| storage 三分裂导致 BI join 失败 | P0 先用独立 `product_behavior.db` + member console batch summary；跨库/aggregate 进入 scale decision |
| SQLite 写入/查询压力被低估 | Phase -1 做事件量估算；P0 写独立行为库，不和 chat/session DB 争锁；超过阈值再上 aggregate/outbox |
| BI 只产出图不产出动作 | P0 必须交付运营队列和判断模板 |
| 行为分析变成 BI 外孤岛 | P0 强制挂到 `/bi?tab=member-ops` |
| raw mode 与既有 scrubbed export 约束冲突 | 行为 export 单独标 raw_mode 并写 audit，不静默复用 scrubbed 口径 |
| section 曝光三端口径不一致 | Phase -1 做 spike；不可 A 级时 BI 明示 B 级 |

## 16. 不确定性、验证和替代方案

| 不确定性 | 推荐默认 | 验证方式 | 替代方案 |
| --- | --- | --- | --- |
| 手机号是否默认展示 | 不默认在总表展示，只在用户下钻展示 | 运营实际使用 1 周复盘 | 若效率不足，再加可配置列 |
| quick exit 阈值 | P0 先用 5 秒 | 看 1 周分布，取 p20/p30 调整 | 按模块单独阈值 |
| 是否复用 surface telemetry | 默认复用现有 helper + endpoint + auth/rate-limit/payload guard | Phase -1 audit 现有 ACK smoke 和产品行为扩展是否冲突 | 若 ACK contract 确实不能承载，再建并行 writer，但 transport 不另起第二套 SDK |
| 行为 ledger 落库底座 | P0 默认独立 `product_behavior.db` + indexed raw read | 量化 50k DAU 写入、会员运营页 join 成本和 p95 查询 | raw Postgres 长存，aggregate 同步到 BI read model |
| section 曝光口径 | Phase -1 spike 后再承诺 A 级 | Web IntersectionObserver vs 小程序 `wx.createIntersectionObserver` 实测 | 若实现困难，P0 先用组件渲染并标 B 级可信 |
| `yousenwebview` surface | 沿用现有 `wechat_yousenwebview`，另加 `host_package` | 检查当前 runtime 能否稳定注入 | 先只区分现有三值 surface，host 后补 |
| BI 操作行为是否进同表 | P0 不进，同步保留 audit log | 看 BI 行为是否需要产品分析 | P1 增加 `module=bi_admin` |
| 独立 SQLite 是否够用 | P0 先用，且与 session/chat DB 分离 | Phase -1 事件量估算 + p95 查询 + join 成本 | outbox / batch / Postgres / ClickHouse / aggregate 同步到 BI read model |
| release_id 是否稳定 | Web 争取 A 级；小程序 P0 先降 B 级 | 读取当前前端构建注入，小程序用 ENV_VERSION / systemInfo.version 验证 | P1 注入 build_id 后升 A |
| 纯导航是否有 session | 默认客户端 `visit_id` | 验证三端生成、持久化、30 分钟切分 | 无 visit_id 时服务端按时间窗重建并降级 |
| 匿名行为 | P0 不做，只做登录态 | 确认 ingestion auth 不允许匿名 | 长期需要时另设 device_id + merge |
| raw mode 是否长期保持 | 只承诺当前内部阶段 | 上线前做权限复查 | 第三方/对外共享时单独定义脱敏 |
| 是否新增 BI 一级 `behavior` tab | P0 不新增，先嵌入会员运营页面 | 观察 BI 信息密度和日常 owner | P1 新增 `behavior` section |

## 17. Done Definition

本 PRD 达到 P0 Done 时，团队可以每天稳定回答：

1. 哪些模块最常被打开。
2. 哪些模块覆盖最多真实用户。
3. 学情里哪个 section 最常被使用。
4. 用户看完学情后是否进入训练、复盘、复测。
5. 高频访问是喜爱、困惑、入口问题还是体验失败。
6. 哪些用户需要运营介入。
7. 本周产品改动是否改变了行为漏斗。

如果只能回答“打开了多少次”，不算 Done。

## 18. GSTACK REVIEW REPORT

Review date: 2026-06-02

Review skills used:

- `plan-ceo-review`
- `plan-eng-review`
- `plan-design-review`

Verdict:

- 当前方案方向正确，尤其是把 P0 主落点收敛到 `/bi?tab=member-ops`，避免行为分析长成 BI 外孤岛。
- 但 implementation 前不应直接开工。必须先收口下面 P0/P1 findings，否则最容易出现三类失败：raw mode 与既有 scrubbed/masked 口径冲突、重复建设第二套 telemetry authority、会员运营页面信息过载但不能转化成动作。

### 18.1 CEO Review

Rating: 8/10.

| Priority | Finding | Required decision |
| --- | --- | --- |
| P1 | 当前指标体系已经能回答“哪些模块被用”，但还需要更强地回答“哪些模块带来经营动作和学习结果”。否则行为 BI 容易停留在 dashboard，而不是增长和留存系统。 | P0 BI 必须至少交付 3 个可执行 cohort：`report_high_no_action`、`history_high_no_review`、`training_no_retest`，并绑定运营动作和回访结果字段。 |
| P1 | “受欢迎”不能只按打开次数排序。高频打开可能代表喜欢，也可能代表找不到、卡住、反复确认、入口误触。 | P0 指标命名必须区分 `popularity`、`attention`、`confusion`、`conversion`，BI 默认展示解释模板，而不是只展示 top modules。 |
| P2 | `module_value_score` 放到 P1 是合理的，但 P0 仍需一个轻量经营判断。 | P0 可先提供 non-score 的 `behavior_interpretation`：`healthy_interest`、`stuck_loop`、`lost_after_report`、`training_dropoff`。 |

CEO conclusion:

- 方案可以进入 Phase -1 technical audit。
- 不建议跳过 Phase -1 直接实现，因为当前最大风险不是“能不能打点”，而是“打完以后是否真的能指导会员运营动作”。

### 18.2 Engineering Review

Rating: 5-6/10 before v0.3 correction; target 7/10 after the amendments above are accepted.

| Priority | Finding | Evidence / risk | Required change before implementation |
| --- | --- | --- | --- |
| P0 | 原 v0.2 “最简路径”方向反了：计划要新建 SDK / endpoint / ingestion，但代码里已有三端统一 surface telemetry 通路。 | 现有 `web/lib/surface-telemetry.ts`、`wx_miniprogram/utils/surface-telemetry.js`、`yousenwebview/packageDeeptutor/utils/surface-telemetry.js` 都上报到 `/api/v1/observability/surface-events`；`SurfaceEventStore.ingest` 已有 event_id、surface、event_name、session_id、turn_id、metadata、dedupe。 | P0 改为复用现有 surface telemetry，加产品 event catalog 和持久化 writer；不新建第二套 behavior SDK / endpoint，除非 Phase -1 证明现有 ACK contract 无法承载。 |
| P0 | 存储底座三分裂未决，比 raw-mode 冲突更上游。 | 现有 BI/member read path 与 surface events 长期行为分析尚未打通。会员运营页需要把会员基础数据、行为 cohort 和时间线 join 到同一页。 | v0.4 定案：P0 用独立 `product_behavior.db`，不复用 chat/session SQLite 文件；会员运营页通过 member console batch summary 读 indexed raw read model；Postgres/aggregate 延后到 volume gate。 |
| P0 | raw mode 与既有 BI scrubbed/masked 口径存在真实冲突。 | 当前会员运营表已有 `maskPhone(phone)` / `phone_masked` 语义；现有导出 endpoint 文案也存在 scrubbed export 口径。若行为 raw export 静默复用这些路径，会导致用户要求的 raw mode 落空，或权限语义混乱。 | 实现前必须明确：行为 raw drilldown / raw export 是独立 endpoint、独立 audit action、独立权限 gate；不要静默复用 scrubbed export，也不要让 masked 字段冒充 raw 行为明细。 |
| P0 | `surface` taxonomy 与现有代码冲突。 | 现有 surface 白名单是 `web / wechat_miniprogram / wechat_yousenwebview`；原 PRD 写 `wechat / yousenwebview / web / bi`。 | P0 直接沿用现有三值枚举；`bi` 操作行为不进产品行为同表，继续走 admin audit。 |
| P0 | `session_id` 被误用为导航会话。 | 当前 turn session 在聊天/WS 生命周期生成，纯学情打开、section 浏览、quick exit 可能没有 turn session。 | schema 拆 `visit_id` 与可选 `session_id / turn_id`；P0 产品路径以 `visit_id` sessionization 为准。 |
| P1 | P0 服务拆分略有变重风险。 | 当前计划若再引入 EventCatalog、IngestionService、MetricsService、export service、BI adapter，会超过 P0 边界。 | P0 代码形态收敛为：catalog 常量/配置 + product behavior persistence writer + `ProductBehaviorMetricsReader`。导出和 BI API 先做薄 adapter，不新增策略引擎。 |
| P1 | 测试计划需要落到具体文件和真实页面。 | Release gates 已列出，但还缺“哪些测试文件证明哪些 gate”。 | implementation plan 中补充最小测试矩阵：backend ingestion/dedupe/offline replay、BI API permission/raw export、`BiV2MemberOpsPanel` 行为列/抽屉、`/wechat-harness` 学情路径 smoke。 |
| P1 | 查询性能需要前置设计。 | 如果会员列表逐个用户读取行为 summary，会形成 N+1；如果和 session DB 共库，会争用聊天/session 写锁。 | v0.4 定案：P0 不建 daily/hourly aggregate，但必须建索引、独立 DB、batch summary reader，并补 N+1 与 offline replay guard；daily/hourly aggregate 进入 P1 或 volume gate。 |
| P1 | release_id 和 section 曝光不能默认 A 级。 | 小程序端当前更容易拿到 ENV_VERSION / systemInfo.version，不一定有 build_id；section 曝光 Web 与小程序 observer 语义不同。 | release regression Web 先 A、小程序 P0 B；section 曝光先做三端 spike，不可行时在 BI 明示 B 级。 |
| P2 | 数据可信等级很好，但不能只停留在展示层。 | trust level 若只在 UI 显示，后续运营可能仍把 B/C 数据当 A 数据用。 | 所有 cohort 计算结果都带 `trust_level`，低可信 cohort 默认不可进入自动运营队列，只允许人工参考。 |

Engineering conclusion:

- 不建议新增顶层 BI behavior tab。
- 不建议引入 PostHog/ClickHouse 作为 P0 canonical。
- 强制先做 authority audit + storage / join audit + section visibility spike，再做 schema 和 BI 页面实现。

### 18.3 Design Review

Rating: 7/10.

| Priority | Finding | Required design guardrail |
| --- | --- | --- |
| P1 | 会员运营页很容易被行为指标挤爆。 | P0 页面层级必须固定为：顶部 behavior health strip、cohort tabs、member table behavior columns、Member360 drawer 详情。不要在主表上堆 10 个行为列。 |
| P1 | 行为时间线若展示 raw event 过多，会降低运营效率。 | Drawer 默认展示解释后的关键节点：打开学情、查看 section、进入训练、退出、复测；raw events 只作为折叠 drilldown。 |
| P1 | cohort tabs 必须服务动作，不是服务浏览。 | 每个 cohort tab 都要有默认 next action、可批量加入 follow-up queue、可记录 contacted/ignored/reason。 |
| P2 | 数据可信提示不能抢主任务注意力。 | trust level 在 health strip 和 drawer 中用小型 badge/tooltip；不要做成大面积解释卡。 |
| P2 | 空状态、低样本状态、延迟状态要设计清楚。 | 无行为数据时显示“暂无行为样本”，低可信时显示“样本不足/离线补发中”，不能显示 0 后让运营误判为用户没使用。 |

Design conclusion:

- 把行为分析嵌入会员运营页是正确选择。
- 设计重点应是“把行为转成运营判断”，不是“把事件表可视化”。

### 18.4 Required Amendments Before Build

Implementation 前必须完成：

1. 在 Phase -1 增加 existing telemetry authority audit，明确 `surface-events`、小程序 / `yousenwebview` helper、`SurfaceEventStore` 与 `product_behavior_events` 的关系。
2. 在 Phase -1 增加 storage / join audit，明确独立 `product_behavior.db`、indexed raw read model、batch summary reader 与现有 BI/member 数据如何在 `/bi?tab=member-ops` 同页 join。
3. 在 Phase -1 增加 section visibility spike，验证三端曝光口径是否能 A 级一致。
4. 明确 raw mode 的 UI/API/export 权限：不能复用 scrubbed export 口径，不能让 masked phone 成为 raw 行为明细的替代。
5. 把 P0 BI scope 固定为 `/bi?tab=member-ops`，其他 BI 页面只允许使用轻量 projection，不能成为 P0 主战场。
6. 补具体测试矩阵和文件级验收目标。
7. 明确 P0 读模型：会员运营页读服务端 indexed raw read model 和 batch summary，不直接扫 raw ledger；aggregate 表延后到 P1 或 volume gate。
8. 把 cohort 与运营动作绑定，确保 P0 交付的是运营队列，而不只是行为图表。

### 18.5 Final Review Decision

This plan is conditionally approved for Phase -1.

It is not yet approved for direct implementation until the telemetry authority, storage/join, section visibility, and raw-mode/export conflicts are resolved.
