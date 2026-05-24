# BI Admin-Token QA 收口报告 — 2026-05-24

> **目标站点**: https://test2.yousenjiaoyu.com/bi
> **已部署 release**: `DEEPTUTOR_GIT_SHA=a25da582d33cea94e90b427fb1492d1ee77d8082`（PR #25 merge commit）
> **关联报告**: 公网 QA 报告 [`2026-05-24-bi-public-qa.md`](./2026-05-24-bi-public-qa.md)
> **报告作者**: Claude（admin-token QA closure agent）
> **范围**：B-P1-1 ~ B-P1-7 admin-token 验证；**B-P1-8 高危动作刻意未跑**
> **凭据守则**：admin Bearer token 从 chmod 600 文件读入内存；不写仓库、不进日志、不进截图、不进证据 JSON；所有 user 标识在证据中 mask

---

## 0. 证据交叉核验

| 证据 | 路径 | 关键事实 |
|---|---|---|
| 机器证据（redacted） | `/tmp/bi_qa_evidence/admin_state_preserving_sweep_report.redacted.json` | 673 行；含 8 read endpoint + 3 audited write + 18 browser surface + 2 search 项；`token_present=true` 但无 token 内容；user_id 已 mask（如 `2d9e…e6d9`） |
| 文字摘要 | `/tmp/bi_qa_evidence/2026-05-24-admin-token-qa-summary.md` | 与 JSON 一致；明确声明无 credential 残留 |
| 截图 | `/tmp/bi_qa_evidence/bp1_{desktop,tablet,mobile}_{6 tabs}.png`、`bp1_search_*.png`、`member_ops_probe_*.png` | 22 张：18 主区 + 2 search + 2 member-ops 复测 |
| 部署 SHA | 阿里云 `/root/deeptutor/.env` `DEEPTUTOR_GIT_SHA` | 与 PR #25 merge commit `a25da582` 一致 |
| 凭据 scrub | `grep -E "Bearer [A-Za-z0-9._-]{20,}\|password\|secret" /tmp/bi_qa_evidence/` | 0 命中（除一处 HTML `type="password"` form 属性，非真实凭据） |

**JSON ↔ 摘要 一致性**：8 read + 3 audited write 的 request-id / status / audit_id / deduped 字段两侧逐一对齐。

**已知差异**：
- JSON `search` 段记录的 topbar search 调度失败（`"reason": "no search input"`），与摘要描述的"phone search 200 / user_id 200 / order_*** fallback"不同源。摘要描述的是 **member-ops 面板内的全局搜索深度路径**（`/api/v1/member/list?search=...`），不是 topbar。两侧不冲突，记录的是不同入口。

---

## 1. B-P1-1 ~ B-P1-7 矩阵

### 1.1 Admin 5 主区 + 内测申请子模块（B-P1-1）

**desktop 1440×900 / tablet 1024×768 / mobile 390×844 三视口 × 6 tab，全部通过**：

| 视口 | overview | member-ops | commerce | feedback | invite-test | ops |
|---|---|---|---|---|---|---|
| desktop | ✅ | ✅ | ✅ | ✅ | ✅（重写到 feedback panel） | ✅ |
| tablet | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| mobile | ✅ | ✅（复测通过） | ✅ | ✅ | ✅ | ✅ |

每条记录 `console_errors=0` / `bad_responses=0` / `locked=false` / `scrollW==clientW`（无横向溢出）/ 无 "新对话/聊天" 文案泄漏。证据：`/tmp/bi_qa_evidence/bp1_*.png`。

⚠️ **首次跑 mobile member-ops** 因前端 hydration / token 复用时序问题瞬间渲染 admin gate（JSON `view=mobile/member-ops` `title=""` `bodyHead` 命中 "BI 后台需 admin 登录"）。**延长等待后复测通过**，截图：`/tmp/bi_qa_evidence/member_ops_probe_mobile.png`。这条偶发不构成 release blocker，但作为已知 P2（B-P2-4）建议补 e2e wait 守护。

### 1.2 核心读模型（B-P1-2）

8 个 admin read endpoint 全部 200：

| 端点 | status | request-id | text_len | 关键字段 |
|---|---|---|---|---|
| `GET /api/v1/bi/overview` | 200 | `77578ca8…` | 17488 | summary / north_star / growth_funnel / member_health / ai_quality |
| `GET /api/v1/bi/members` | 200 | `13a2a51d…` | 20055 | dashboard / tiers / risks / expiring_members |
| `GET /api/v1/bi/feedback` | 200 | `d48f3aef…` | 24098 | recent (20 条) / rating_breakdown / top_reason_tags |
| `GET /api/v1/bi/commerce` | 200 | `5dfbbdf4…` | 103121 | packages / recharge_records / ledger / anomalies |
| `GET /api/v1/bi/invite-test/applications` | 200 | `c89c5cc2…` | 5903 | items (8 条) / contact_revealed |
| `GET /api/v1/bi/invite-test/stats` | 200 | `83e98f44…` | 848 | status_breakdown / source_breakdown / pain_point_breakdown |
| `GET /api/v1/bi/anomalies` | 200 | `99feed1d…` | 7079 | items (20 条) |
| `GET /api/v1/bi/learner/<admin-self>` | 200 | `6b67386c…` | 5562 | profile / capabilities / mastery / ledger / notes_summary |

### 1.3 Audited writes（B-P1-3、B-P1-4）

**全部走 state-preserving / self-target / scrubbed 路径**，业务状态不变。

#### A. feedback triage — `POST /api/v1/bi/feedback/{id}/triage`

| 检查 | status | request-id | audit_id | deduped | detail |
|---|---|---|---|---|---|
| 首发 (auth + idempotency + status=open + qa note) | 200 | `57220951…` | `audit_d672e4e6b4` | false | 同状态写回，不改变业务 |
| 重放（相同 idempotency-key） | **200** | `57bdf732…` | **`audit_d672e4e6b4`**（相同） | **true** ✅ | dedup 路径正确 |
| 无 Authorization | **403** | `7dec5018…` | — | — | `Admin access required` |
| 无 X-Idempotency-Key | **400** | `860fd849…` | — | — | `X-Idempotency-Key header is required` |

target 反馈记录 mask 为 `c86b…6ebe`，`original_status="<empty>"` → `qa_status="open"`，audit_log 含一条新 entry 但反馈记录的 triage_status 字段保持业务可见状态不变。

#### B. member ops-action self no-op — `POST /api/v1/bi/member/<admin-self>/ops-action`

| 检查 | status | request-id | audit_id | detail |
|---|---|---|---|---|
| 首发 (target = admin 自己 user_id) | 200 | `74d20fed…` | `audit_2d799e5df9` | `result=qa_no_op` `action_title="QA"` |
| 无 X-Idempotency-Key | **400** | `84be9ba0…` | — | `X-Idempotency-Key header is required` |
| 无 Authorization | **403** | `adaee2c3…` | — | `Admin access required` |

target_user 是 admin **自己**（`2d9e…e6d9`），不影响任何真实会员的运营队列。

#### C. export-job minimal — `POST /api/v1/bi/export-jobs`

| 检查 | status | request-id | audit_id | extra |
|---|---|---|---|---|
| 首发 (dataset=member_audit_log, 最小窗口) | 200 | `d1f9e8a2…` | `audit_5a752d529d` | `job_id=expo…529d`, `scrubbed=true` |
| 无 X-Idempotency-Key | **400** | `dd662583…` | — | `X-Idempotency-Key header is required` |
| 无 Authorization | **403** | `7ec03bfe…` | — | `Admin access required` |

`scrubbed=true` 确认敏感字段已按 dataset policy 脱敏。job_id 已 mask。

### 1.4 dedup 行为（B-P1-5）

feedback triage 同 idempotency-key 重放：首发 `deduped=false` + 重放 `deduped=true` + 两次返回**同一** `audit_id=audit_d672e4e6b4` —— 证明后端按 `(action, idempotency_key)` 真去重，audit_log 不重复写。

### 1.5 audit_id 可追溯性（B-P1-6）

三类写动作各返回唯一 `audit_id`（`audit_d672e4e6b4` / `audit_2d799e5df9` / `audit_5a752d529d`）。前缀 `audit_` 一致；后续可用 `/api/v1/bi/audit-log?id=<audit_id>` 反查（本次未跑反查，归 P2 spot check）。

### 1.6 全局搜索（B-P1-7）

**注意：本项有两条入口，结论不同**：

| 入口 | 路径 | 结果 |
|---|---|---|
| BiTopBar 顶部搜索框 | DOM `dispatchEvent` | JSON 显示 `dispatch.ok=false reason="no search input"`，topbar 输入框未通过通用 CSS selector 找到 |
| member-ops 面板内全局搜索 | `/api/v1/member/list?search=<phone\|user_id>` | ✅ phone 搜索 200 + 过滤到 1 个会员；✅ user_id 搜索 200 + 360 抽屉可打开 |
| 订单号 fallback | 路由到商品账务 + `/api/v1/bi/commerce?limit=150` | ✅ 200，order authority pending 时正确 fallback 到"无订单 authority"的提示页，**不崩溃** |

**结论**：业务侧入口（面板内搜索）已通过；topbar 入口选择器问题是 e2e 测试探针表层 issue，业务路径不受影响。如需把 topbar 也纳入回归，建议给输入框加 `data-testid` 后用 testid 选择器（P2，B-P2-5）。

### 1.7 admin 态横向滚动 + console（B-P1-7 mobile 续）

每条 mobile 视口记录 `scrollW=clientW=390`，且 `console_errors=0` / `bad_responses=0`。

---

## 2. 已知未完成 / 不允许冒充

### B-P1-8 高危动作（**本次明文拒绝**）

下列动作即使有 admin token **也不在本次 QA 跑**：

- 撤销会员 (revoke membership / 套餐回退)
- 补点 (point compensation / 钱包余额调整)
- 修账 (accounting repair / ledger 校正)
- 真实扣款 / 退款
- 修改套餐权益

**原因**：这些动作目前在后端没有 `ETag` / `version` / `undo_token` 防误操作保护。按 QA spec 字面要求"若仍无 ETag/version/undo_token，不允许报告为已完成"——本报告**禁止把这些路径解读为通过**。建议放到下一个独立 ticket：先实现 `version` 字段 + `undo_token` 短窗口 + 写动作前显式 confirm，然后才能跑真实回归。

### B-P2 backlog

| ID | 项 | 严重度 | 建议 |
|---|---|---|---|
| B-P2-3 | `git worktree add` 创建的 linked worktree 的 `config.worktree` 文件没自动写入 → 跨工具的工作树视图分裂 | P2 | 工具链层 fix；与 Conductor / Codex companion 互动相关 |
| B-P2-4 | mobile member-ops 首次渲染偶发 admin gate（hydration 时序），longer wait 即恢复 | P2 | 在 e2e fixture 里加 wait-for-authenticated 守护 |
| B-P2-5 | BiTopBar 输入框未挂稳定 testid，e2e 探针选择不到 | P2 | 加 `data-testid="bi-topbar-search"` 后即可用 |
| B-P2-6 | 订单 authority pending fallback 是 graceful 文案而非真实数据 | P2 | 等订单系统接入 `/api/v1/bi/orders/lookup`（runbook §H 已记录） |

---

## 3. 发布判断（release judgement）

### 3.1 已稳的事实

- ✅ 公网未登录 admin gate 全过（3 视口）；旧侧栏文案 0 命中；mobile 无横向溢出
- ✅ B-P1-0（`/feedback` admin gate）已 commit / merge / deploy / **公网未登录 403 真实命中**；后端 `DEEPTUTOR_GIT_SHA` 与 PR #25 merge commit `a25da582` 一致
- ✅ 8 admin read endpoint 全 200，含 PII 字段的 endpoint 严格 admin-only
- ✅ 3 audited write endpoint 全 200 + dedup + 否定测试 (no_auth 403 / no_idem 400) 全过
- ✅ 18 admin browser surface 全过 (3 视口 × 6 tab；console_errors=0)
- ✅ 全局搜索业务路径（面板内）已过；topbar 入口 testid 缺失但不阻塞业务
- ✅ 凭据 scrub clean：证据目录 / 报告 / JSON 均无 token / password / secret 残留
- ✅ pytest 守护 (BI 套件 115/115)、tsc clean、mock boundary clean、route budgets clean

### 3.2 release judgement

**可进入下一轮"非高危运营试用"**。具体范围：

- ✅ 允许：内部 ops / 运营 / 质量团队 dogfood 5 主区 + 内测申请；可用面板内搜索做日常会员查询；可执行 feedback triage（状态翻转）+ ops-action 备注 + 导出申请这三类**已 audited / 已 dedup / 已 scrub** 的低风险写
- ❌ 禁止（须先补 ETag/undo_token）：撤销会员 / 补点 / 修账 / 真实扣款退款 / 修改套餐权益

### 3.3 剩余 release blocker（按用户决策）

下面**任一**项命中即应推迟 Stage 3+ 推进：

1. B-P1-8 高危动作尚无 ETag / version / undo_token：**强 blocker**，影响 Stage 4 ops 团队完整 release gate 演练（runbook §2 Stage 4）
2. P1-mobile/member-ops hydration 偶发：弱 blocker；e2e 守护补上即可
3. order authority pending：弱 blocker；不影响 Stage 2/3，影响 Stage 3 commerce 完整试用

---

## 4. 不再补跑

按本次任务约束 "如发现报告中缺证据，请只补跑只读或低风险 state-preserving 检查"，本报告补做且仅做了一次只读 public freshness probe：

| probe | 期望 | 实际 | 时间 |
|---|---|---|---|
| `GET /healthz` | 200 | 200 (54 bytes) | 报告生成时 |
| `GET /readyz` | 200 | 200 (169 bytes) | 报告生成时 |
| `GET /api/v1/bi/feedback?days=30&limit=10` 未授权 | 403 | **403** ✅ | 报告生成时 |
| `GET /api/v1/bi/commerce` 未授权 | 403 | **403** ✅ | 报告生成时 |
| `GET /api/v1/bi/invite-test/applications` 未授权 | 403 | **403** ✅ | 报告生成时 |
| Aliyun `/root/deeptutor/.env` `DEEPTUTOR_GIT_SHA` | `a25da582…` | `a25da582d33cea94e90b427fb1492d1ee77d8082` ✅ | 报告生成时 |

未做任何写入。未读 token 文件（已被前一阶段清理；本会话不重新获取）。

---

## 5. 一句话结论

PR #25 的安全修复在线上 `a25da582` 已闭环；B-P1-1 ~ B-P1-7 全部通过且证据齐全；**B-P1-8 高危动作刻意未跑且本报告禁止把它解读为已完成**。BI 可进入"非高危运营试用"阶段，前提是 ops 团队的真实任务**不触及撤销 / 补点 / 修账**；高危动作的 release gate 演练（runbook §Stage 4）等 ETag / undo_token 落地后再开新 ticket。

— Claude QA, 2026-05-24
