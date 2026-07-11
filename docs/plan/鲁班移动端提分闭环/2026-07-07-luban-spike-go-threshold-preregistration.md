# 双轮 spike GO/NO-GO 阈值预登记（点火前锁定，防事后改门柱）

> 双轮 v3.2 §12 阶段 1 spike 的「GO 门阈值预注册」交付物，是 [D1 基线预登记](2026-07-02-luban-spike-d1-baseline-preregistration.md) 的**同伴文档**：基线文档回答「起点在哪、替代度量怎么算」，本文回答「spike 成功 = 哪几条指标 ≥ 哪些数、这些数在点火前就写死」。
>
> **铁律（owner rule「阈值预注册不可事后改」）**：本文 §3 的目标数一旦由 owner 在 §5 签名锁定，spike 期间及读数时**不得回改**。这是反「事后挪门柱 / 事后改度量定义凑 GO」（anti-gaming）的结构保证——门柱先钉死，数据再进来。
> Date: 2026-07-07 · 上位契约：双轮设计 v3.2 §12 阶段 1 · 度量口径 authority：`product_behavior_events`（持久化 SQLite，register-before-use 强制）

---

## 0. 与 07-02 基线预登记的分工（不重复）

| 文档 | 回答什么 | 关系 |
|---|---|---|
| `2026-07-02-...-d1-baseline-preregistration.md` | 起点基线（服务端 turn 替代度量 D1=6.2%/4.6%）+ 乙案判据（D1≥15% / cohort≥30 / 窗口≥7d）+ QA allowlist 口径 | 基线与总判据 authority，本文不改写 |
| **本文** | 把每条 GO 指标落到 `product_behavior_events` 上的**精确 query spec**（event_name + practice_mode + 相对每人首用的时间窗），给 owner 一张**填空锁定表** | 基线的执行细化：把「D1」翻译成真实埋点可跑的 SQL |

**关键演进（本文之所以新增）**：07-02 基线用的是服务端 turn 活动的**替代度量**（客户端埋点当时仅 16 行不可用）。2026-07-07 埋点命门已修：变体复测完成事件 `learning_action_completed(object_type=retest)` 现在带 `practice_mode ∈ {forward, review}`（`product_behavior_catalog.py:32-41`、`:162-164`）。这使「次日回来做**换皮复测**」第一次可以从「当天正向轻练」里分出来——D1 留存 GO 信号从此**可直接在客户端行为库读出**，不再只能靠 turn 替代度量。

---

## 1. 度量口径与反 gaming 规则（先于阈值）

- **度量表**：`product_behavior_events`（`product_behavior_store.py:57-88`）。持久化 SQLite，`event_name` register-before-use（白名单外 ingest 拒收，`product_behavior_catalog.py:130-133`）。查询走 `query_raw_events`（`product_behavior_store.py:369-414`，现已支持按 `practice_mode` 过滤，`:388`）。
- **用户主键 = `user_id`，绝不用 `visit_id`**。`visit_id` 有 30 分钟 TTL，跨天必然翻新，用它算留存会把「次日回访」全部漏掉。留存必须 key on `user_id`（`product_behavior_events.user_id` 列，`product_behavior_store.py:63`）。
- **首用锚点（D0）派生，无专用事件**：留存没有独立埋点，按每个 `user_id` 派生——首用锚 = `MIN(occurred_at_ms)`（该用户在 `product_behavior_events` 里最早一条事件，surface=wechat_yousenwebview）；「回访」= D0+N 那个自然日窗口内出现任意目标事件。`occurred_at_ms` 为毫秒 epoch（`product_behavior_store.py:61`）。
- **cohort 定义**：spike 参与用户 = 走完 ≥1 个站点闭环者（进站→讲懂→轻练→交接），且不在 QA allowlist 内。allowlist 唯一权威 = `MemberConsoleService.list_internal_test_user_ids()`（沿用 07-02 基线 §3 硬前置，不另立名单）。
- **反 gaming 硬规则**：
  1. **阈值点火前锁定**：§3 目标数在 spike 启动前由 owner 在 §5 填入并签名，之后冻结。
  2. **禁事后重定义度量**：event_name / practice_mode / 时间窗 / 主键口径，一旦本文写定不得为凑 GO 而改。要改口径只能作废本文重新预登记并重跑，不能就地改数。
  3. **GO 门 = 真实留存行为，不是正确率/完成质量**：判 GO 看「人有没有回来做换皮复测、订阅、被交接曝光」，**不看**答对率/掌握度。答题质量只作观察披露，绝不进 GO 裁决（与 v3.2 §3「掌握态只由客观复测产生、spike 复测只进 telemetry 不写学情」一致）。
- **cohort 门槛**：cohort < 30 只报「未达读数条件」，不报成败（防小样本假阳，沿用乙案）。读数窗口 ≥ 7 天。

---

## 2. 五条 GO 指标的精确定义 + query spec

所有时间窗均**相对每个用户自己的首用锚 D0**（非日历统一日）。`day+N` 指 `[D0 + N*86400s, D0 + (N+1)*86400s)` 这一自然日切片（按 UTC+8 取日，与基线一致）。分母/分子均在 QA allowlist 剔除后计算。

### G1 — D1 次日回访率（主 GO 信号）
- **定义**：cohort 中，在 day+1 窗口内**做了换皮复测**（review 模式复测完成）的用户占比。这是「次日回来做换皮复测」的直接测量——命门指标。
- **分子**：`distinct user_id` where `event_name='learning_action_completed' AND practice_mode='review' AND occurred_at_ms ∈ day+1(user)`。
- **分母**：cohort 全体（走完 ≥1 站点闭环、非 QA）。
- **query spec**：
  ```
  # 每人 D0
  D0(u) = MIN(occurred_at_ms) over product_behavior_events where user_id=u, surface='wechat_yousenwebview'
  # 分子命中
  filters = {event_name:'learning_action_completed', practice_mode:'review',
             start_ts_ms: D0(u)+86400_000, end_ts_ms: D0(u)+172800_000}
  返回集合的 distinct user_id 计数 / cohort 计数
  ```
- **目标（owner 锁定）**：D1 换皮复测回访率 ≥ ⟨____%⟩ 。（乙案参考线：绝对 15%；owner 在 §5 填写最终锁定值。）

### G2 — D7 回访率（留存持久性 GO 信号）
- **定义**：cohort 中，在 day+7 窗口（或 day+1..day+7 累计，口径由 owner 在 §5 二选一并锁定）内再次做换皮复测的用户占比。
- **query spec**：同 G1，`practice_mode='review'`，时间窗 = `[D0+7d, D0+8d)`（单日口径）或 `[D0+1d, D0+8d)`（累计口径）——**口径必须点火前锁定，不得读数时才选**。
- **目标（owner 锁定）**：D7 回访率 ≥ ⟨____%⟩ ，口径 = ⟨单日 D7 / 累计 D1–D7⟩（owner 圈定）。

### G3 — 换皮复测完成率（review 漏斗健康度）
- **定义**：开始 review 换皮复测的人里，真正答完 5 题的比例。
- **分子**：`count(event_name='learning_action_completed', object_type=retest, practice_mode='review')`。
- **分母**：`distinct user_id` 中**开始过** review 复测者 = 出现过 `event_name='retest_item_answered' AND practice_mode='review'`（首题作答即算开始）的用户数。
- **query spec**：
  ```
  分子 = count rows: {event_name:'learning_action_completed', practice_mode:'review'}   # object_type=retest 落在 object_type 列
  分母 = distinct user_id in rows: {event_name:'retest_item_answered', practice_mode:'review'}
  ```
  （事件出处：`retest.js:130-137` 每题 `retest_item_answered{practice_mode}`，`:169-176` 完成 `learning_action_completed{object_type:retest, practice_mode}`。）
- **目标（owner 锁定）**：完成率 ≥ ⟨____%⟩ 。

### G4 — 订阅授权率（次日回访钩子有效性）
- **定义**：交接时刻请求「明天提醒我」的人里，授权 granted 的比例。
- **分子**：`count(event_name='subscribe_prompt_result', result='granted')`。
- **分母**：`count(event_name='subscribe_prompt_result')`（granted + red_dot 全体）。
- **query spec**：
  ```
  分子 = count rows: {event_name:'subscribe_prompt_result', result:'granted'}
  分母 = count rows: {event_name:'subscribe_prompt_result'}
  ```
  （事件出处：`handoff.js:84-90`，`result ∈ {granted, red_dot}`。）
- **⚠️ 结构性 0（如实登记）**：微信订阅模板 `WECHAT_SUBSCRIBE_TMPL_NEXT_DAY_RETEST`（`env_registry.yaml:146`，`wechat_subscribe/service.py:34`）**未配置前，授权链路降级为 red_dot**，`result='granted'` 结构上恒为 0 → G4 恒为 0%。owner 未 provision 模板 ID 之前，**G4 不可作为 GO 分子**，只记曝光（handoff_rendered）→次日主动回访。见 §4。
- **目标（owner 锁定，仅在模板 provision 后生效）**：授权率 ≥ ⟨____%⟩ 。

### G5 — 交接曝光率（钩子到达面）
- **定义**：cohort 中被交接时刻曝光过的用户占比（钩子到达的分母保证，防「留存低是因为根本没曝光」）。
- **分子**：`distinct user_id` where `event_name='handoff_rendered'`。
- **分母**：cohort 全体。
- **query spec**：`filters={event_name:'handoff_rendered'}` → distinct user_id / cohort。（事件出处：`handoff.js:55-60`。）
- **目标（owner 锁定）**：曝光率 ≥ ⟨____%⟩ 。（护栏指标：曝光率过低说明漏斗断在交接前，此时 G1 低分不能归因为「用户不愿回来」。）

---

## 3. GO/NO-GO 填空锁定表（owner 点火前填）

> 填入前所有 target 均为空占位符 ⟨____⟩。**工程不得代填、不得臆造参考数**（乙案 15% 仅为基线文档给出的参考线，非本表默认值）。owner 逐行圈定后本表冻结。

| 指标 | query（event_name / practice_mode / 窗口） | GO 目标（owner 锁定） | 角色 |
|---|---|---|---|
| G1 D1 换皮复测回访率 | `learning_action_completed` · `review` · day+1 | ≥ ⟨________%⟩ | **主 GO** |
| G2 D7 回访率 | `learning_action_completed` · `review` · ⟨单日 D7 / 累计 D1–D7⟩ | ≥ ⟨________%⟩ | GO |
| G3 换皮复测完成率 | 分子 `learning_action_completed·review` / 分母 `retest_item_answered·review` distinct user | ≥ ⟨________%⟩ | GO |
| G4 订阅授权率 | `subscribe_prompt_result` granted / all | ≥ ⟨________%⟩（**模板 provision 后才计**） | 条件 GO |
| G5 交接曝光率 | `handoff_rendered` distinct user / cohort | ≥ ⟨________%⟩ | 护栏 |
| cohort 下限 | 走完 ≥1 站点闭环、剔 QA allowlist | ≥ ⟨____⟩（乙案默认 30） | 读数前置 |
| 读数窗口 | — | ≥ ⟨____⟩ 天（乙案默认 7） | 读数前置 |

**综合 GO 规则（owner 圈定其一）**：
- ⟨ ⟩ 全部硬 GO 指标（G1/G2/G3）达标 → GO
- ⟨ ⟩ 主 GO（G1）达标即 GO，其余为观察
- ⟨ ⟩ 其他：____________________

---

## 4. 「读得出吗」就绪度（如实上报）

| 指标 | 今天可读？ | 依据 / 阻塞 |
|---|---|---|
| G1 D1 换皮复测回访率 | **可读（命门已修）** | `practice_mode='review'` 已登记并落列（`catalog.py:41`、`store.py:84,172`），`query_raw_events` 支持过滤（`store.py:388`）。前提：有生产数据。 |
| G2 D7 回访率 | 可读（同 G1） | 同上，需窗口 ≥7 天让日历推进。 |
| G3 换皮复测完成率 | 可读 | 分子分母均在 `product_behavior_events`，靠 practice_mode 区分 review。 |
| G4 订阅授权率 | **阻塞** | `WECHAT_SUBSCRIBE_TMPL_NEXT_DAY_RETEST` 未配置 → granted 结构性 0%（`wechat_subscribe/service.py:84-85` 降级 `template_not_configured`）。owner provision 模板前只记曝光→回访，不计授权率。 |
| G5 交接曝光率 | 可读 | `handoff_rendered` 已登记（`catalog.py:32`）。 |

**三条诚实边界**：
1. **生产无数据，直到体验版/生产构建上线**：`product_behavior_events` 现无 spike 真数据（客户端埋点历史仅 16 行，见 07-02 基线）。上线并招募真实 cohort 前，本文所有指标 = 0 行，不可读数。
2. **无 BI 聚合层**：目前**没有任何 BI 指标/看板读这些事件**，只有 `query_raw_events` / raw export（`store.py:369`）。读数 = 手跑 raw query 按本文 §2 口径聚合，不是仪表盘一键出数。（`get_member_behavior_*` 系列聚合函数不覆盖 practice_mode 留存口径。）
3. **G4 不可达，直到模板 provision**：owner 配置微信订阅模板 ID 之前，订阅授权率无法产生非 0 分子。

---

## 5. 签名与锁定行（owner 填）

> 本行签署即冻结 §3 全部目标数与口径。签署后 spike 期间任何门柱/度量定义变更一律作废本文重新预登记。

- 锁定日期：⟨________⟩
- 锁定人（owner）：⟨________⟩
- 锁定的 GO 规则版本：本文 §3（⟨勾选的综合 GO 规则⟩）
- G4 是否纳入本轮 GO：⟨是（模板已 provision）/ 否（模板未配置，仅记曝光→回访）⟩
- 备注 / 与乙案参考线的偏差说明：⟨________⟩

---

## 6. 复算入口（独立可证伪）

读数时按 §2 query spec 直接对生产 `product_behavior_events` 跑 raw query（`query_raw_events`，支持 `practice_mode` 过滤）。任何人可在生产容器内以本文口径重跑核对；口径以本文冻结版本为唯一权威，不得各自维护变体。
