# 学习模块偏好埋点 + BI 驾驶舱看板 — 加强定稿计划

- **状态**：Draft（4 专家 panel + 指挥官裁决已完成；实施中）
- **日期**：2026-07-21
- **主线**：会员钱包计费与经营后台（product behavior intelligence）
- **相关**：[[MemberOpsCockpit]] · product_behavior pipeline · [[luban 学习模块]]

## 1. 目标 / 非目标

**目标**：让 owner 在 BI 上一目了然地看到——学员对鲁班学习模块（`packageDeeptutor` 的 `learn/` + `luban/*`）里
①哪些**功能**被点得多、②哪几个**微课/教学动画卡/考点讲解**被反复看、③**练习题做了多少 + 正确率**，
用于判断产品进化方向。以**独立驾驶舱 tab** 呈现。

**非目标**：
- 不碰主包 polyv 公开课（`freeCourse`/`freeCourseDetails`）——owner 明确排除。
- 不做微课"完播率"（架构判死，见 §5）。
- 不建第二套采集/聚合/endpoint 权威。

## 2. 指挥官裁决：一个架构病，不是四个需求

**病因（第一性）**：一条**功能完整的采集→聚合→渲染管线，在生产粒度处丢弃了消费所需的粒度**——
`object_type` 早已在聚合 SQL 的 `group by`（`product_behavior_store.py:422-427`）里、`visible_ms/duration_ms`
早已在表里，却在两处被压平：后端 Python fold（L455-483）只按 module 折叠、前端 producer 把 episode
压成 pack（`station.js:104`）；同时高基数维度 `object_type` 用了 14 个值却从未收成注册表
（`product_behavior_catalog.py:211` 纯 `_clean_string`）。

→ 本需求 90% 是**把丢弃的粒度捞回来 + 把维度收权 + 补两处断头 producer**，不是加数据源。

**shared failure shape**：`producer/consumer granularity mismatch` + `dormant/unregistered dimension`。

## 3. 单一 authority 收口（调和专家 A↔D 冲突）

- **单一数据权威 = store 层**：复用 `get_product_usage_overview_for_identity_groups`（module 级）
  + 新增**一个**参数化 `get_engagement_breakdown(...)`（object/action/练习级）。**不是三个函数**。
- **A↔D 冲突裁决**（逻辑放哪）：内容 Top-N / 练习聚合是今天谁都没服务过的新切面 →
  经**薄 `bi.py` endpoint** 读 store，**不碰受保护的 `member_console/service.py`**（learner_state 域，
  避 contract_guard + 保 thin）；两个 caller 读同一 store 函数 ≠ 第二 authority。
- module 热度双渲染由"降级 MemberOpsCockpit 那块为跳转入口"解决（纯前端，可选收尾）。
- **不新增 event_name / module / action**——全部复用。

## 4. 指标定义（专家 B — 去偏，非虚荣）

owner 要的"哪个模块被感兴趣"，答案不在点击榜，在 **触达 × 人均深度 的错位**：
高触达低深度=首页位置撑起的泡沫；低触达高深度=被埋没值得加投的金矿。

| 指标 | 算法（现有字段） | 纠正的偏差 |
|---|---|---|
| 触达 Reach | `member_count`（去重人数） | 重度用户刷量 |
| 人均深度 Depth | `action_count / member_count` | 入口曝光 |
| 复访率 Return | `visit_count / member_count` | 一次性好奇 |
| 完成率 Completion | `completion_count / visit_count` | 打开就跑 |
| 快退率 Quick-exit | `quick_exit_count / visit_count`（<5s，**反向**） | 假兴趣 |
| 内容复看率 Repeat | `view事件数 / 独立观看人数`（object 级） | 广撒网假热 |
| 练习正确率 | `correct / answered`（`retest_item_answered.result`，标 `source=product_behavior_events`） | 与 turns 判分不同源，须标源 |

模块级比率**前端用现有 `module_usage` 字段直接算**（零后端）。硬后端依赖只有 object 级 breakdown + 练习聚合。

## 5. 完播率判死 → 停留时长替代（专家 C 实证）

- `station.wxml:14` web-view **无 `bindmessage`**；H5 微课卡从不 postMessage 进度（只有 `luban_ai_ask`/`luban_practice_diagnosis`）；微信 web-view 消息**非实时**（离场批量交付）。
- 动画学习卡是 CSS 动画，**无"完播"语义**。
- → 用 `module_exited.durationMs`（照 `learn.js:74/97/101` 给 `station` 补 `onUnload/onHide`），零 H5 改造。
- 后端出 `completion_source: native|dwell|open_proxy|unavailable` 字段，前端据此切标题/徽标，**绝不显示假完播%**。

## 6. 实施阶段

### P1 后端权威层（自测，不依赖前端）
1. `product_behavior_catalog.py`：新增 `PRODUCT_BEHAVIOR_OBJECT_TYPES` 注册表（回填 14 既有值 + `microlesson`/`concept_card`）+ 文档。
   **Deviation D1**：本次为**软注册表**（不翻硬 400 enforcement）——硬 fail-closed 影响全产品所有 surface，
   是独立迁移，blast radius 超本需求；留 follow-up。
2. `product_behavior_store.py`：新增 `get_engagement_breakdown(*, group_dim, module, event_names, object_types, days, exclude_user_ids)`
   （泛化 `get_learning_report_section_breakdown` L539；一次 group-by 同时喂内容偏好 + 练习正确率）；
   加索引 `idx_pbe_object (object_type, object_id, occurred_at_ms)`。
3. `bi.py`：新 endpoint `GET /api/v1/bi/learning-preference`（`require_bi_permission("overview","view",public_ok=True)`），
   读 store（module 级 overview + object/action/练习 breakdown），装配 §4 指标 + `completion_source`。
   **不改 service.py**。
4. `bi_metrics.py`：注册新指标 → `python -m scripts.gen_bi_metrics_ts` → drift 测试。禁手改 `.generated.ts`。
5. 单测：catalog 注册表、store breakdown（含 demo 排除）、endpoint。

### P2 前端 producer 补缺（yousenwebview，全走 `trackProductBehavior`）
最小必要集（专家 C，复用已注册事件名，零新事件名）：
1. `station.js:104` object_id 带 `teaching_point_id`（否则内容偏好聚合不出）+ 补 `onUnload/onHide→trackModuleExit`（停留时长）。
2. `teaching-points.js:164 openEpisode`：补 `learning_action_started`(action=open_detail, objectType=microlesson, objectId=`pack:tp:ep`)。
3. `concept-cards.js:79 flipCard`：补内容视图（objectType=concept_card, objectId=card_id），**页面级去抖 Set 非 trackOnce**（防队列溢出 + 保跨 visit 复看）。
4. `review.js`/`errorbank.js`/`stations.js`：各补 1 条入口 `module_viewed`（漏斗分母，不埋页内交互）。
5. 站内五题随堂练：走**原生 retest 路径**（已有完整埋点），**禁在 H5 加 fetch**（第二套采集）。
**明确不埋**：折叠展开、切 pack、翻卡 got_it/again 独立事件、滚动/toggle。

### P3 BI 独立 tab（Next.js v2，零新图表原语）
- 新 section `learning-pref`：`BiV2Surface.tsx` SECTIONS + `isSectionEnabled` + flag `BI_LEARNING_PREF_V2_ENABLED` + `dynamic` panel。
- 布局（专家 B）：KPI 行 6 卡 → **触达×深度双条**（题眼）→ 内容复看 Top + 练习正确率 by pack → 卡点漏斗 → 明细表。
- 组件全复用 `CockpitKpi/CockpitBar/CockpitPanel`；小样本标 `TRUST_LEVEL_COLORS.C` 灰徽；完播缺失走 `completion_source` 降级。
- 数据经 `bi-api.ts getBiLearningPreference()` → `/api/v1/bi/learning-preference`。

### P4 demo 数据（test 环境）
- eval-runner cohort 隔离：服务端强制 user_id（`observability.py:69`），**不加客户端 is_demo**；固定 `qa_`/`eval_` 前缀账号。
- store breakdown 默认 `exclude_user_ids`=eval cohort，或看板显式标"含 N 条合成演示数据"。
- **红线**：绝不进生产 DB；话术="合成演示形态，生产真值待小程序发版埋点通电"。

### P5 验证 + commit + review
- 后端单测；DevTools 小程序回归；BI 动前过 Web/BI 内存 preflight（**禁 AI agent 托管长驻 next dev**）；自 commit（conventional，无 Co-Authored-By）；自 review。

## 7. 不确定性与验证（专家 D 清单）
| 假设 | 状态 | 处置 |
|---|---|---|
| 微课完播率可采 | **证伪** | 判死，用停留时长替代 |
| object_type 无白名单 | **已验证** | 软注册表收权（D1 deviation） |
| object_id 无索引 | **已验证** | 加 `idx_pbe_object` |
| 生产表当前为空 | **已验证** | P4 demo 让 owner 先看形态；真值待发版 |
| service.py 受保护 | **已验证** | 逻辑放 store+bi.py，不碰 service.py |
| 学习模块流量极低 | **已验证** | 看板焊入样本量可信度标注；诚实告知 owner 噪声风险 |

## 8. 三原则自检
- **thin wrappers**：业务逻辑全在 store/catalog，`bi.py` 与前端 handler 只归一化/转发。
- **first principles**：回到"一次学习动作"一等事实，收粒度而非加系统。
- **less is more**：1 聚合非 3、0 新事件名、0 新图表原语、0 改表列。
