# BI 高危运营动作安全契约 — 设计计划

> **状态**: Proposed
> **日期**: 2026-05-24
> **作者**: Claude（BI Admin-Token QA closure 续）
> **关联**:
> - 上游 PRD: [2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md](2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md)
> - 钱包权威: [2026-04-19-supabase-wallet-single-authority-prd.md](2026-04-19-supabase-wallet-single-authority-prd.md)
> - QA 收口: [../../zh/bi/qa-reports/2026-05-24-bi-admin-token-qa-closure.md](../../zh/bi/qa-reports/2026-05-24-bi-admin-token-qa-closure.md)
> - 灰度 runbook: [../../zh/bi/bi-backoffice-v2-rollout-runbook.md](../../zh/bi/bi-backoffice-v2-rollout-runbook.md)
> - 项目宪法: AGENTS.md §0 / §3 / §5
>
> **本文只规划契约，不写生产代码、不动数据库、不部署阿里云**。实施 ticket 由 reviewer 拆分批准后另开。

---

## 0. 设计来源 — QA 留下的硬约束

`2026-05-24-bi-admin-token-qa-closure.md` 在 release judgement 里写下：

> **B-P1-8 高危动作 (撤销会员 / 补点 / 修账 / 真实扣退 / 改套餐权益)**：本次明文拒绝，因后端没有 ETag / version / undo_token 防误操作保护。"若仍无 ETag/version/undo_token，不允许报告为已完成"。

这条 backlog 直接决定 runbook §Stage 4 完整 release gate 演练能否开。本计划就是把这条 backlog 拆成可实施契约。

**本计划的非目标**（明确写出来防误读）：

- 不实施任何**真实** revoke / grant / point compensation / accounting repair（即使本地）
- 不修改生产数据
- 不部署阿里云
- 不在本计划文件之外动其他源码
- 不收口 B-P2-3/4/5/6（worktree config 漂移 / mobile hydration flake / topbar testid / order authority backend）——这些是独立 ticket

---

## 1. 范围 — 哪些动作是"高危"

按 QA spec 列举的 5 类 + 现有代码扫描出来的真实可写路径，本计划覆盖：

| 编号 | 业务动作 | 当前代码入口 | 当前保护 | 高危原因 |
|---|---|---|---|---|
| HR-1 | **撤销会员订阅** | `POST /api/v1/member/revoke` → `MemberConsoleService.revoke_subscription` (`deeptutor/services/member_console/service.py:3574`) | 仅 admin gate + audit log；**无 idempotency / version / undo** | 立刻把 `status=revoked` + `expire_at=now`；用户立刻失权益 |
| HR-2 | **补/扣会员积分** | 现有 `mobile.py` 钱包 ledger 读 (`/api/v1/billing/wallet` line 1952) + `MemberConsoleService.capture_points`；**admin 入口在 BI v2 仍未实装** | 无 | 调用 wallet authority 直接改 `balance_micros`；金额可见即可被滥用 |
| HR-3 | **会员套餐权益修改 (tier / 到期 / auto_renew)** | `POST /api/v1/member/grant` → `grant_subscription` (`service.py:3509`)、`update_subscription`（同文件） | 仅 admin gate + audit log；无 idempotency / version / undo | 修改后台 SaaS 权益 = 直接影响付费用户 |
| HR-4 | **账务异常处理 / ledger 校正** | `bi_service.py` 已有 `record_bi_export_request` 与异常队列**只读** (`/api/v1/bi/anomalies`)；**实际"修账"写入路径未实装** | N/A（路径不存在） | 一旦实装就直接动 ledger 历史；不可仅按"重跑"恢复 |
| HR-5 | **真实扣款 / 退款** | 不在 BI 范畴；走支付网关单独 PRD；**本计划不覆盖** | — | 跨系统；放在 [supabase-wallet-single-authority-prd] 主线 |

> **HR-5 显式不在本计划范围**：跨系统支付/退款必须由钱包 single authority + 支付网关合作处理；本计划只在 BI 侧定义"为支付动作触发审计 + undo 标记"的契约接口，真实退款由钱包 authority 实施。

---

## 2. one business fact — 每个高危动作改什么

每条高危动作在 single authority 体系下**只改变一项事实**。任何"为了 X 顺手再做 Y"都不允许；额外副作用必须拆成独立动作 + 独立 audit。

| 动作 | one business fact | "顺手" 禁止做什么 |
|---|---|---|
| HR-1 撤销会员 | `member.status` 从 `active` → `revoked` 且 `expire_at` 置为提交时刻 | 不可顺手清空 `points_balance` / 不可顺手注销 `auth_session` / 不可顺手删除 `notes` |
| HR-2 补/扣积分 | `wallet.balance_micros` 单笔增量；写 `ledger` 一条 `event_type='admin_adjust'` | 不可顺手改 `tier` / 不可顺手改 `expire_at` / 不可顺手发系统通知 |
| HR-3 套餐权益修改 | `member.tier` 或 `member.expire_at` 或 `member.auto_renew` 三选一（多选必须拆多次调用） | 不可顺手改 `balance` / 不可顺手清 `status` |
| HR-4 账务异常处理 | 不"修改"历史 ledger entry；只**追加一条** `event_type='admin_compensation'` 的补偿条目并写 audit | 不可 in-place 改历史；不可删 ledger entry；不可调 `balance_micros` 之外的字段 |

**Rationale**：一条"动作 → 一条事实变化"映射让 audit/undo/rollback 都能机械化。AGENTS.md §5.7 single authority hard gate 与 §0 thin wrappers fat skills 直接对应到此。

---

## 3. single authority — 谁唯一写、谁唯一存、谁唯一恢复、谁唯一读取

| 动作 | 唯一写 (write authority) | 唯一存 (state of truth) | 唯一恢复 (undo authority) | 唯一读 (read model) |
|---|---|---|---|---|
| HR-1 撤销 | `MemberConsoleService.revoke_subscription_v2`（新方法，沿用 fcntl `_mutate`） | `data/member_console_*.json` `members[].status` + `expire_at` + `subscription_version`（新增字段） | `MemberConsoleService.undo_revoke_v2`（消费 undo_token，写补偿 audit） | BI: `/api/v1/bi/members` + `/api/v1/bi/learner/{user_id}`；UI: BiV2MemberOpsPanel + Member360Drawer |
| HR-2 补/扣点 | 钱包 single authority（`supabase-wallet-single-authority-prd`）的 admin RPC；**BI 调用是 thin wrapper** | Supabase wallet 表（`balance_micros` + `ledger`） | 钱包 authority 自带"逆向 admin_adjust 条目"；BI 提供 undo_token 路由到钱包 | `/api/v1/billing/wallet`、`/api/v1/billing/ledger` |
| HR-3 套餐权益 | `MemberConsoleService.update_subscription_v2`（新方法） | 同 HR-1 + `member.tier` / `auto_renew` + 同一 `subscription_version` | `MemberConsoleService.undo_subscription_change_v2` | 同 HR-1 |
| HR-4 账务补偿 | 钱包 authority 提供 `append_compensation_entry`；BI 不写 ledger | 同 HR-2 ledger | 不允许 undo 补偿条目；只能再追加反向补偿（双向可追溯） | `/api/v1/billing/ledger` |

> **重点**：所有"写"必须经 service 层 single authority；**BI router 永远是 thin wrapper**，不允许 BI 直接动 JSON / Supabase。这一条与 AGENTS.md §0 Thin Wrappers Fat Skills 一致。

---

## 4. ETag / version 防并发误操作

### 4.1 数据模型新增字段

`members[]` JSON record 增加 `subscription_version: int`（默认 `1`，每次 `grant/revoke/update` 后 `+= 1`）。同理 `wallet.balance_version` 在钱包 authority 一侧由钱包计划负责。

### 4.2 API 契约

读端在响应体 + HTTP header 同时返回：

- HTTP response header: `ETag: "v<subscription_version>"`（弱 ETag 形式，weak validator 因为 JSON 包整体可能含其它字段变化）
- response body: `subscription_version: <int>` 显式字段

写端要求：

- 请求 header 必须带 `If-Match: "v<subscription_version>"`（与刚才读到的 version 一致）
- 缺失 → **412 Precondition Required**（detail: `"If-Match header is required for high-risk actions"`）
- 不匹配 → **412 Precondition Failed**（detail: `"subscription state has advanced (expected v3, server v5); refresh and retry"`）

### 4.3 服务层强制

`update_subscription_v2` / `revoke_subscription_v2` / `grant_subscription_v2` 接受 `expected_version: int` 参数；不匹配则在 fcntl `_mutate` 临界区抛 `StaleStateError`，router 把它映射成 412。

### 4.4 测试

- pytest: `test_revoke_rejects_stale_version`、`test_update_rejects_missing_if_match`
- contract guard：`tests/api/test_bi_write_endpoints_registry.py` 增加 `requires_version_match=True` 字段，registry-driven 校验所有 high-risk 路由都强制 `If-Match`。

---

## 5. undo_token 设计

### 5.1 生成

每次写成功后由 service 生成 `undo_token`：

```text
undo_token = base64url(secrets.token_bytes(24))   # 32 ASCII char
```

绑定参数（写入 audit 同时存到 `audit_undo_index`）：

```json
{
  "undo_token": "<32 chars>",
  "audit_id": "audit_abcd1234",
  "actor_id": "<admin_user_id>",
  "action": "revoke",
  "target_user_id": "<user_id>",
  "before_state_hash": "<sha256 of before JSON>",
  "before_state_compact": { "status": "active", "expire_at": "...", "subscription_version": 5 },
  "expires_at": "<iso utc, now + 15min>",
  "consumed_at": null,
  "consumed_by_audit_id": null
}
```

### 5.2 TTL

- 默认 **15 分钟**（HR-1/HR-3/HR-2）
- 账务补偿（HR-4）：undo_token **不发**，因为只能追加反向补偿，不能撤回（前述 §3）

> Rationale: 15 分钟覆盖典型 ops 误操作的"一杯水的时间"察觉窗口；过长则与"快照撤销"边界模糊，须走真正 backup-restore。

### 5.3 一次性

undo 端在 `_mutate` 临界区内：

1. 找到 `undo_token` 对应记录
2. 校验 `consumed_at IS NULL` && `expires_at > now`
3. 校验当前 `before_state_hash` 与 audit 记录里的 `before_state_hash` 仍然一致——若不一致（业务又被改过）→ 422 `"target state has advanced; undo would corrupt history"`
4. 写"逆向动作"（revoke → 还原 status/expire_at；update → 还原 tier/expire_at/auto_renew）
5. 标 `consumed_at=now` + `consumed_by_audit_id=<新 audit>`
6. 返回 `{undo_audit_id, restored_state, deduped: false}`

### 5.4 重复消费

同 token 重放 → 422 `"undo_token already consumed at <iso>"`（不是 200 + deduped，因为"重复 undo" 业务上不存在）。

### 5.5 安全

- `undo_token` 仅在**写成功的 response body** 返回一次；不进数据库 query log；不进 audit `reason`；不进 UI URL 参数
- 客户端可显示 `undo_token` 给操作者复制做异常通道（极端情况下可让另一 admin 在另一终端粘贴 token 撤销）
- 任何含 `undo_token` 的字段在 BI 通用导出（`/api/v1/bi/export-jobs`）里 **scrubbed**

---

## 6. dry-run preview — 必须先返回 before/after diff

### 6.1 契约

所有 high-risk 写端点支持 `?dry_run=true` query 参数；body 校验、permission 校验、`If-Match` 校验照常进行，但 service 层在 fcntl `_mutate` 之外 stage（基于 read snapshot）计算 `after_state` 然后不 commit。

response shape：

```json
{
  "dry_run": true,
  "before_state": { "status": "active", "expire_at": "2026-08-01T00:00:00Z", "subscription_version": 7 },
  "after_state":  { "status": "revoked", "expire_at": "2026-05-24T08:14:00Z", "subscription_version": 8 },
  "diff": [
    { "path": "status", "before": "active", "after": "revoked" },
    { "path": "expire_at", "before": "2026-08-01T00:00:00Z", "after": "2026-05-24T08:14:00Z" },
    { "path": "subscription_version", "before": 7, "after": 8 }
  ],
  "estimated_audit_action": "revoke",
  "would_emit_undo_token": true,
  "warnings": [
    "user holds 1240 points (will remain after revoke; see HR-2 if also withdrawing)",
    "user has 2 unfinished conversations in last 24h"
  ]
}
```

### 6.2 强制 preview-then-commit

UI 必须先用 `?dry_run=true` 渲染 confirm modal；commit 调用必须带：

- 同一 `If-Match`
- 同一 `X-Idempotency-Key`
- header `X-Confirmed-Preview-Hash: <sha256(canonical_json(after_state))>`

如果 commit 阶段 service 计算出来的 `after_state` 哈希与 client 提交的不一致（业务被其它人改过、或 client 伪造），返回 **409 Conflict**: `"preview hash mismatch; refresh"`.

### 6.3 测试

- pytest: `test_dry_run_does_not_mutate`、`test_commit_requires_preview_hash`、`test_commit_rejects_preview_hash_mismatch`
- Playwright: `test_bi_v2_high_risk_revoke_requires_preview_modal`

---

## 7. idempotency — X-Idempotency-Key 绑定

### 7.1 组合 key

服务侧用 `f"{action}:{operator}:{target_user}:{expected_version}:{idempotency_key}"` 作为 dedup index（比现有 BI v2 多两个维度：target + version）。

理由：

- `target_user` 防止 "我用同一 key 对两个不同用户写" 被吃掉
- `expected_version` 防止 "我用同一 key 对同一用户的不同版本写" 被吃掉（业务实际上已经前进）
- 与现有 audit dedup key 形态兼容，只是 namespace 更长

### 7.2 行为

- 同 5 元组 key 重放 → 返回首次 audit_id + `deduped=true`（与 BI v2 现有 triage/ops-action 一致）
- 不同 5 元组里**任何字段不同**则视为新写
- 缺 `X-Idempotency-Key` → 400 同现有 BI v2 行为

### 7.3 与 undo_token 的关系

undo 端用**新**的 idempotency-key（绑定 `undo_token`）：`f"undo:{operator}:{undo_token}:{idem_key}"`。两次同 idem-key 的 undo 调用 → `deduped=true`，但 token 只消费一次（dedup 不影响一次性，避免 race 写）。

---

## 8. audit — 完整 audit entry 形态

`_append_audit` 已有的字段保留；high-risk 动作扩展为：

```json
{
  "id": "audit_abcd123456",
  "operator": "<admin_user_id>",
  "actor_id_alias": "<display_name>",
  "action": "revoke" | "grant" | "update_subscription" | "admin_adjust_points" | "compensate_ledger" | "undo_revoke" | "undo_update" | "undo_admin_adjust",
  "target_user": "<user_id>",
  "reason": "<≥4 chars / one of 5 whitelist codes>",
  "request_id": "<X-Request-ID propagated from edge>",
  "idempotency_key_masked": "<first6…last4>",
  "before": { /* compact business state */ },
  "after":  { /* compact business state */ },
  "version_before": 7,
  "version_after": 8,
  "undo_token_present": true,
  "undo_token_masked": "<first4…last4>",
  "undo_expires_at": "<iso>",
  "undo_consumed_at": null,
  "undo_consumed_by_audit_id": null,
  "preview_hash_confirmed": "<sha256 truncated>",
  "deduped": false,
  "created_at": "<iso>"
}
```

`undo_*` 字段在原始写入 audit 上反映；undo 成功后再 update 同一 audit 的 `undo_consumed_*` 字段（**只允许从 null 改为非空一次**；service 在 fcntl 里 enforce）。

> **不存全 token**：audit 只存 `undo_token_masked`；完整 token 仅在 5.5 描述的 response 与 `audit_undo_index` 私有索引里存（私有索引在 export 时 scrubbed）。

---

## 9. rollback window — 哪些可撤销、多久内、撤销失败怎么呈现

| 动作 | undo 可用窗口 | 撤销方法 | 撤销失败呈现 |
|---|---|---|---|
| HR-1 撤销会员 | 15 min | `POST /api/v1/bi/member/{user_id}/undo` body `{undo_token, reason}` | 422 + 业务原因（state advanced / token consumed / token expired） |
| HR-2 补/扣点 | 15 min | 通过钱包 authority `POST /api/v1/billing/admin/undo-adjust`（钱包计划负责实施） | 422 + 钱包侧原因 |
| HR-3 套餐权益修改 | 15 min | 同 HR-1 路径，传 undo_token | 同上 |
| HR-4 账务补偿 | **无 undo** | 只能再发一条反向补偿（`compensate_ledger` reverse=true），形成可追溯链 | 不允许调用 undo 接口 |
| HR-5 真实扣退 | 跨系统；由钱包 + 支付网关共同决定（不在本计划） | — | — |

UI 端：

- 任何高危动作成功后，confirm modal 关闭前显示 30s 大字 "可撤销窗口剩 14:59，点这里立即撤销"
- 错过 15min 后，相同动作的"撤销"按钮 disabled，hover tooltip "已超出 15min undo 窗口；如需修正请走账务补偿（HR-4）流程"

---

## 10. UI gate — 二次确认 + 危险文案 + 错误提示

参照已有 `useAuditedAction` hook + `<RequireBiAdmin>` boundary，**不在 panel 内拼 audit 字符串**。新增组件：

### 10.1 `<HighRiskActionGate>`

- prop: `action`, `targetUserId`, `previewEndpoint`, `commitEndpoint`, `undoEndpoint`, `requiredAck: "TYPE_USER_ID" | "TYPE_ACTION" | "TYPE_PHRASE"`
- 渲染流程：
  1. 点击触发 → 调 `previewEndpoint` 取 dry-run
  2. 显示 modal：左 before、右 after（带 diff 高亮）、底部 warning 列表
  3. 操作者必须**手敲**目标 user_id 或 action 关键词（不能复制粘贴；DOM 监听 `paste` 事件并清空）
  4. 仅当输入校验通过 + `If-Match` / `X-Confirmed-Preview-Hash` 都 ready 时，"执行"按钮 enable
  5. 成功后顶部出现 15min 倒计时 + "立即撤销" 按钮

### 10.2 danger banner

- modal 顶部红色固定文案：`"此操作不可立即恢复，仅有 15 分钟撤销窗口。"`（HR-4 改为：`"账务补偿不可撤销，只能追加反向补偿。"`）

### 10.3 disabled 条件

- 当前用户非 admin
- `subscription_version` 与 read snapshot 不一致（即 If-Match precheck 失败）
- 30s 前已有同 action 在 in-flight（防止双击）
- `requiredAck` 未通过

### 10.4 错误提示文案

| HTTP code | UI 文案 |
|---|---|
| 400 missing idempotency / preview hash | "请求缺安全 header；请刷新页面重试" |
| 403 not admin | "权限不足；本动作仅限 admin" |
| 409 preview hash mismatch | "目标会员状态已被其他人修改；请关闭弹窗刷新后重试" |
| 412 If-Match missing/mismatch | 同 409 |
| 422 undo token expired/consumed/state advanced | "撤销窗口已关闭或状态已变化；请通过账务补偿流程处理" |
| 500 | "服务暂不可用；不会重复写入；请 1 分钟后重试或联系平台" |

---

## 11. API contract — endpoint / method / schema / error code

### 11.1 HR-1 撤销会员

**Preview**:
```
POST /api/v1/bi/member/{user_id}/revoke?dry_run=true
Headers: Authorization, X-Idempotency-Key, If-Match: "v<n>", X-Request-ID
Body: { "reason": "<≥4 chars or whitelist code>" }
→ 200 { dry_run:true, before_state, after_state, diff, warnings, would_emit_undo_token:true }
```

**Commit**:
```
POST /api/v1/bi/member/{user_id}/revoke
Headers: Authorization, X-Idempotency-Key, If-Match: "v<n>", X-Confirmed-Preview-Hash, X-Request-ID
Body: { "reason": "..." }
→ 200 { audit_id, version_after, undo_token, undo_expires_at, deduped:false }
错误：400 / 403 / 409 / 412 / 422 / 500（按 §10.4 表）
```

**Undo**:
```
POST /api/v1/bi/member/{user_id}/undo
Headers: Authorization, X-Idempotency-Key, X-Request-ID
Body: { "undo_token": "<32 chars>", "reason": "<≥4 chars>" }
→ 200 { undo_audit_id, restored_state, original_audit_id }
错误：400 / 403 / 422
```

### 11.2 HR-2 补/扣点

按钱包 authority 协议；BI 在 `web/lib/bi-v2-write-endpoints.generated.ts` 注册新 key `wallet.admin_adjust.request`，**但实际写仍走钱包 RPC**（thin wrapper）。详细 schema 由钱包计划负责。

### 11.3 HR-3 套餐权益修改

参数：`tier?`, `expire_at?`, `auto_renew?`（三选一，多选 → 400 `"only one subscription dimension may change per call"`）。
其余同 HR-1。

### 11.4 HR-4 账务异常处理

**Preview / Commit**:
```
POST /api/v1/bi/member/{user_id}/compensate-ledger[?dry_run=true]
Headers: Authorization, X-Idempotency-Key, X-Confirmed-Preview-Hash, X-Request-ID
Body: { "delta_micros": <±int>, "reason": "...", "reference_ledger_entry_id": "<id>" }
→ 200 { audit_id, ledger_entry_id, balance_after_micros }
// 无 undo_token；无 If-Match（账务每条都是独立追加；并发冲突由钱包 authority 自行处理）
错误：400 / 403 / 409 / 422 / 500
```

### 11.5 注册到 BI v2 write registry

`deeptutor/contracts/bi_v2_write_endpoints.py` 追加（不在本 plan commit，仅描述）：

```python
WriteEndpoint(
    key="member.subscription.revoke",
    method="POST",
    path_template="/api/v1/bi/member/{user_id}/revoke",
    requires_idempotency=True,
    requires_version_match=True,     # NEW field
    supports_dry_run=True,            # NEW field
    emits_undo_token=True,            # NEW field
    description="High-risk: revoke member subscription with ETag + preview + 15min undo",
    audit_action="revoke",
),
# ... 同样为 update / compensate / wallet.admin_adjust 各加一条
```

registry 新字段同步反映到 `web/lib/bi-v2-write-endpoints.generated.ts`（`scripts/gen_bi_write_endpoints_ts.py` 扩展）；`useAuditedAction` 在 endpoint.key 上做编译期收窄校验。

---

## 12. 测试矩阵

| 层 | 用例 | 期望 |
|---|---|---|
| **unit (service)** | `test_revoke_v2_appends_audit_and_emits_undo_token` | undo_token 生成 + audit `undo_token_present=true` |
| | `test_revoke_v2_dry_run_does_not_mutate` | 返回 200 + 真实 data 文件 mtime 不变 |
| | `test_revoke_v2_rejects_stale_version` | 412 |
| | `test_revoke_v2_rejects_preview_hash_mismatch` | 409 |
| | `test_undo_revoke_v2_rejects_consumed_token` | 422 + `"already consumed"` |
| | `test_undo_revoke_v2_rejects_expired_token` | 422 + `"expired"` |
| | `test_undo_revoke_v2_rejects_state_advanced` | 422 + `"target state has advanced"` |
| | `test_undo_revoke_v2_restores_business_state` | status==active, expire_at, version+=2（一进一出） |
| | `test_compensate_ledger_v2_appends_only` | ledger 长度 +1, 历史条目未改 |
| | `test_admin_adjust_routes_to_wallet_authority` | 钱包 RPC 被调用（mock）；BI service 自身不直写余额 |
| **API contract (pytest + TestClient)** | `test_high_risk_endpoints_require_if_match` | 缺 If-Match → 412 |
| | `test_high_risk_endpoints_require_preview_hash` | 缺 hash → 400 |
| | `test_high_risk_endpoints_require_idempotency` | 缺 idem-key → 400 |
| | `test_high_risk_endpoints_require_admin` | non-admin → 403 |
| | `test_high_risk_endpoints_dry_run_clean` | dry_run=true 不写 audit_log |
| | `test_write_endpoints_registry_marks_high_risk` | 4 条 high-risk endpoint 在 registry 都置 `requires_version_match=True` & `supports_dry_run=True` |
| **Playwright (web E2E)** | `bi-v2-high-risk-revoke.e2e.ts` | preview modal 必现 → 输入 user_id 后才能提交 → 成功后显示 undo 倒计时 |
| | `bi-v2-high-risk-undo.e2e.ts` | 在 undo 窗内点 undo → 422 only if expired/consumed |
| | `bi-v2-high-risk-stale-version.e2e.ts` | 并发场景：先开两个 tab，A 改后 B 直接 commit → B 收 409，弹窗提示刷新 |
| **public smoke** (no admin token) | `GET /api/v1/bi/member/{id}/revoke (typo)` | 405 method-not-allowed（不暴露 endpoint shape）|
| | `POST /api/v1/bi/member/{id}/revoke` no auth | 403 |
| | `POST /api/v1/bi/member/{id}/undo` no auth | 403 |
| **admin-token QA** (state-preserving) | revoke dry_run + 自身 (admin self user_id) | 200 + before==after（自己当前是 admin tier，dry-run 不改）|
| | revoke commit 自身 + 立即 undo | 200 → 200；二次 commit 同 idem → deduped；二次 undo 同 token → 422 |
| | preview hash mismatch 重试 | 手动改 before snapshot → 409 |

> **admin-token QA 显式排除**：HR-2/HR-3/HR-4 对真实其他会员的 commit；HR-5 完全不跑。仅允许 **admin 对 admin 自身** 的 state-preserving 验证。

---

## 13. 实施阶段（建议）

> 阶段顺序由 reviewer 决定；本计划只列建议。**进入任何 implementation 之前必须先有独立 ticket + reviewer 批准**。

1. **Phase 0 — Contract scaffolding (no behavior change)**
   - 在 `bi_v2_write_endpoints.py` 加 3 个新字段 (`requires_version_match`/`supports_dry_run`/`emits_undo_token`) 并把 4 条 high-risk endpoint 注册为 `Proposed` 状态
   - `scripts/gen_bi_write_endpoints_ts.py` 扩展 TS 镜像
   - 新增 `test_write_endpoints_registry_marks_high_risk` red 测试
2. **Phase 1 — Data model: `subscription_version` + `audit_undo_index`**
   - JSON schema migration（向后兼容：缺字段默认 v1）
   - migration smoke：现有数据读取不破坏；version 字段在第一次写时落地
3. **Phase 2 — Service v2 + ETag**
   - `revoke_subscription_v2` / `update_subscription_v2` / `grant_subscription_v2`（仅 v2 强制 If-Match；v1 处于 deprecation 期）
4. **Phase 3 — undo_token + audit 扩展**
   - `audit_undo_index` + `undo_*` 字段；undo 端点；TTL clock
5. **Phase 4 — dry-run + preview hash**
   - service 层 stage 计算；router 层 hash 校验
6. **Phase 5 — UI `<HighRiskActionGate>`**
   - 预览 modal + 输入校验 + danger banner + undo 倒计时
7. **Phase 6 — Playwright + admin QA**
   - 跑测试矩阵；在 admin 自身上做 state-preserving E2E
8. **Phase 7 — Deprecate v1**
   - 删除旧 `revoke_subscription` 单参版本；BI router 仅指向 v2
9. **Phase 8 — runbook §Stage 4 完整 release gate 演练**
   - ops 团队完成一次真实 (非 admin self) 撤销→undo 闭环；只在 v2 全绿后进入

---

## 14. 验收标准

下面任一项不达 → 不允许把"高危动作 QA"标完成（与 QA spec 字面要求对齐）：

- ✅ pytest 测试矩阵 §12 全部 GREEN
- ✅ Playwright §12 三个 e2e 全部 GREEN
- ✅ contract guard：registry 增量字段在 TS / Python 双侧 in-sync（drift test 锁）
- ✅ `tests/web/test_bi_v2_raw_fetch_guard.py` 守护：UI 仍只走 `useAuditedAction`，未在 panel 内手拼 audit
- ✅ public smoke：所有 high-risk endpoint 未授权 403、缺 If-Match 412、缺 idem 400
- ✅ admin-token QA：admin 自身 dry_run + commit + undo 全过；其他 user 不跑
- ✅ runbook §3 1-秒回滚仍有效：关掉相关 v2 flag 即回到旧 BI（v1 service 在 deprecation 期保留）
- ✅ 灰度 Stage 4 完整演练：ops 团队完成一次真实撤销→undo→撤销窗口超时 422，全程证据齐

---

## 15. 风险与不解决项

| 风险 / 不解决 | 描述 | 缓解 |
|---|---|---|
| **15-min 窗口外的误操作** | 操作 16min 后才发现误撤 | 走 HR-4 账务补偿或 backup-restore；UI 错误提示明示此路径 |
| **客户端伪造 preview_hash** | 攻击者构造任意 hash 通过校验 | 服务端在 commit 阶段重算 `after_state` 并比对 hash；伪造 → 409 |
| **undo_token 泄漏** | 操作者把 token 截图传给第三方 | TTL 15min + 一次性 + masked 入 audit；token 进入 export-jobs 时 scrubbed |
| **HR-2 与钱包计划耦合** | 本计划无法独自完成 HR-2 | 仅定义 BI thin wrapper 与 undo 触发；真实写由钱包 PRD 实施 |
| **HR-4 不可 undo** | 账务一旦补偿不能反向 | 由"双向补偿可追溯"替代 undo；UI 明示 |
| **Subscription JSON 单点** | `members[].subscription_version` 仍在 fcntl JSON | 与 wallet single authority 长期目标一致：未来迁 Supabase 时同步引入 PostgreSQL row version；当前作为 backward-compatible 起点 |
| **不在本计划**：B-P2-3/4/5/6 | worktree config / mobile hydration / topbar testid / order authority | 独立 ticket，与本计划解耦 |

---

## 16. 不做（显式 non-goals 再次强调）

- ❌ 本计划不实施任何真实 revoke / grant / point compensation / accounting repair
- ❌ 不动生产数据
- ❌ 不部署阿里云
- ❌ 不在本 commit 之外改源码
- ❌ 不在 runbook §Stage 4 开 release gate 演练
- ❌ 不修改钱包 single authority 自身实现（HR-2 在 wallet PRD 里完成）
- ❌ 不收口 B-P1-1~7（已在 QA closure 报告里覆盖）
- ❌ 不收口 B-P2-3~6（独立 ticket）

---

## 17. 实施 gate（reviewer 确认前禁止 implementation）

reviewer 必须先确认以下问题，再批准任何 Phase 0+ 的 implementation ticket：

1. `subscription_version` 是否在当前 JSON 单点是合适的 backward-compatible 起点？或者应该直接绑定到 wallet PRD 的 Supabase 迁移节奏？
2. undo TTL 15 min 是否合适？需要按 actor role / action class 区分吗？
3. preview_hash 是否需要 server-issued nonce 来防 replay（current 设计仅 hash without nonce）？
4. `<HighRiskActionGate>` 的 "手敲 user_id 不可粘贴" 是否会引起 ops 抱怨？是否改为"语音读出 + 文字输入"？
5. HR-2 与 wallet PRD 的接口边界是否已经在 wallet PRD 里写清？还需要新接口吗？
6. HR-4 反向补偿是否允许跨 reference_ledger_entry_id（即"补偿一次性聚合多个 reference"）？

任一问题答 "不"或"未决" → 应回到设计阶段，不进入 implementation。

---

— Claude, 2026-05-24
