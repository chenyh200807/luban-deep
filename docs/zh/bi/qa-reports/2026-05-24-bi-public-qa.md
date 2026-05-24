# BI 公网 QA 报告 — 2026-05-24

> **目标站点**: https://test2.yousenjiaoyu.com/bi
> **执行环境**: Claude Code · gstack/browse (Playwright chromium-headless-shell v1208)
> **测试时间窗口**: 2026-05-24 09:50–11:30 UTC+8
> **报告作者**: Claude（QA agent，无 admin 凭据准入；管理员路径未覆盖，未谎报）
> **本次报告范围**：在没有 admin token 的前提下能交付的全部证据 + 自动化守护通过情况 + 1 项 **P0 数据泄漏发现**。管理员路径在最后一节明确列为 **P1 backlog (本次未覆盖)**，禁止解读为"已完成"。

---

## 0. 部署点真相核对（与用户给定的不一致）

| 项 | 用户提供 | 实际验证 |
|---|---|---|
| 已部署 commit | `54ab8351` | **`origin/main` 已前进到 `b9ade218`**（含 `34cc9b1c "complete audited ops workflows"` + 3 后续 fix），test2 OpenAPI 路由集与 origin/main 一致；本地 main `46feb1a2` 与 `origin/main` 已**分叉** |
| Stage 1 flags（shell=1, overview=1, 其余 v2=0） | 描述为线上状态 | 未能直接读到 server 端 env；但 OpenAPI 显示 BI v2 写端点（triage / member ops-action / export-jobs）**已在 origin/main 部署**，所以这些写端点的契约理论上是 Stage 2 状态 |
| `DEEPTUTOR_BI_PUBLIC_ENABLED` | 未说明 | **疑似设为 `true`**——证据见第 4 节 P0 |

**结论**：QA 不是在 Stage 1 baseline 上跑的，而是在 origin/main 完整 Stage 2 后端 + 默认 Stage 1 前端 flag 的混合状态上跑的。报告区分这两层。

---

## 1. 测试范围

### 1.1 必跑自动化守护（4/4 PASS）

| 命令 | 结果 | 证据 |
|---|---|---|
| `pytest tests/api/test_bi_router.py tests/services/member_console/test_service.py tests/api/test_bi_write_endpoints_registry.py tests/web/test_bi_v2_raw_fetch_guard.py tests/web/test_bi_v2_mock_boundary.py tests/web/test_bi_v2_banner_fetch_coherence.py -q` | ✅ **104 passed in 84.76s** | bg task `bqmatlldd` |
| `cd web && npx tsc --noEmit` | ✅ exit 0 (clean) | bg task `brlc8q1rs` |
| `cd web && node ./scripts/check_mock_boundary.mjs` | ✅ `OK · production bundle does not contain BI v2 mock fixtures` | inline |
| `cd web && node ./scripts/route_budgets.mjs` | ✅ 全部 OK, `/bi 252KB`、`root-shell 191KB / budget 220KB` | inline |

### 1.2 未登录态 / 公网 admin gate（3/3 PASS）

| 视口 | 结果 | 证据 |
|---|---|---|
| desktop 1440×900 | ✅ 渲染 "BI 后台需 admin 登录" + "登录后台" 按钮；无 v2 shell；无 testid 暴露 | `/tmp/bi_qa_evidence/01_admin_gate.png` |
| tablet 1024×768 | ✅ 同上 | `/tmp/bi_qa_evidence/02_admin_gate_tablet_1024.png` |
| mobile 390×844 | ✅ 同上，`scrollWidth=clientWidth=390`，**无 body 横向滚动** | `/tmp/bi_qa_evidence/03_admin_gate_mobile_390.png` |
| 旧侧栏文案 "新对话"/"聊天" | ✅ 均为 `false`（document.body.innerText 未命中） | js probe |

### 1.3 OpenAPI 路由清单（已部署）

公网 `GET https://test2.yousenjiaoyu.com/openapi.json` 拉取，过滤 `/bi`：

- `GET /api/v1/bi/active-trend`
- `GET /api/v1/bi/anomalies`
- `GET /api/v1/bi/capabilities`
- `GET /api/v1/bi/commerce` *(admin-only via `require_bi_admin`)*
- `GET /api/v1/bi/cost`
- `GET /api/v1/bi/cost/reconciliation`
- `GET /api/v1/bi/feedback`
- `GET /api/v1/bi/invite-test/applications` *(admin-only)*
- `GET /api/v1/bi/invite-test/stats` *(admin-only)*
- `GET /api/v1/bi/knowledge`
- `GET /api/v1/bi/learner/{user_id}`
- `GET /api/v1/bi/members`
- `GET /api/v1/bi/overview`
- `GET /api/v1/bi/retention`
- `GET /api/v1/bi/tools`
- `GET /api/v1/bi/tutorbots`
- **`POST /api/v1/bi/feedback/{feedback_id}/triage`** *(admin-only)*
- **`POST /api/v1/bi/member/{user_id}/ops-action`** *(admin-only)*
- **`POST /api/v1/bi/export-jobs`** *(admin-only)*

注意：原 QA spec 期望 `POST /api/v1/bi/feedback/{id}/ignore` 与 `POST /api/v1/bi/ops/exports`——**这两条路径不存在**：
- `ignore` 走 `triage` 带 `{"status": "ignored"}`（service 层校验 `status ∈ {open, triaged, ignored}`）
- ops 导出实际是 `/bi/export-jobs`

---

## 2. 写端点契约验证（代码 + pytest 层）

通过自动化守护证明（未经过公网真实流量，**不替代实际 QA**）：

| 端点 | 路由级 X-Idempotency-Key | Service 级 dedup | 审计行 |
|---|---|---|---|
| `POST /api/v1/bi/feedback/{id}/triage` | ✅ `_validate_idempotency_key` 400 if missing | ✅ `triage_feedback` 传 `idempotency_key` 到 `record_bi_audit` | `audit_action="feedback_triage"` |
| `POST /api/v1/bi/member/{id}/ops-action` | ✅ 同上 | ✅ `record_ops_action_result` 走 `idempotency_key` | `audit_action="ops_action_result"` |
| `POST /api/v1/bi/export-jobs` | ✅ 同上 | ✅ `record_bi_export_request` | `audit_action="bi_export_request"` |

证据：`pytest tests/api/test_bi_write_endpoints_registry.py` 在守护套件中作为 104 通过用例的一部分，**遍历 `WRITE_ENDPOINTS` 注册表**，断言每个 `requires_idempotency=True` 的端点都在 router + service 双层落地。

⚠️ **未在公网做实际写动作**：因为没有 admin token，无法发起真实 POST 并核对响应头、`deduped: true` 行为、`audit_id` 落库。归到第 6 节 P1 backlog。

---

## 3. 路径必测项覆盖度（含管理员路径 N/A）

| QA spec 必测项 | 状态 | 说明 |
|---|---|---|
| `/bi` 默认页：经营总览可打开 | ⏸ N/A | 未登录看到 admin gate；admin 态因无 token 未测 |
| 页面不出现旧侧栏"新对话/聊天" | ✅ PASS | 未登录态 0 命中；admin 态未测但 BiV2Surface.tsx 不渲染 legacy sidebar |
| `/bi?tab=member-ops`：会员列表、筛选、搜索、360 抽屉 | ⏸ N/A | admin-only |
| `/bi?tab=commerce`：套餐、充值、钱包、异常队列 | ⏸ N/A | admin-only |
| `/bi?tab=feedback`：AI 反馈列表 + triage/ignore 带 Auth + Idempotency | ⏸ 代码+守护层验证；公网未测 | 写端点契约第 2 节 |
| `/bi?tab=invite-test`：内测申请子模块 | ⏸ N/A | 实际 v2 中 `?tab=invite-test` 重写到 `feedback` (BiV2Surface.tsx:70) |
| `/bi?tab=ops`：系统运维 + 导出申请 | ⏸ N/A | 同上 |
| 全局搜索 phone/user_id→member-ops；order→commerce | ⏸ N/A | 需 admin |
| 未登录/非 admin 显示 admin gate，不渲染敏感 panel | ✅ UI 层 PASS；**❌ API 层 FAIL** | 见第 4 节 |
| mobile 无 body 横向滚动 | ✅ PASS（未登录态）；admin 态未测 | scrollW=clientW=390 |

---

## 4. ⚠️ P1 发现：BI `/feedback` 在 public flag 下泄漏 PII（设计一致性 gap）

### 复检 — 初判 P0 已降级为 P1

最初判定 P0 "未登录 /overview /members /feedback 都返回 200"。深读 `tests/api/test_bi_router.py:434` 后确认：

```python
def test_bi_router_allows_public_access_when_flag_enabled(...):
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "1")
    response = client.get("/api/v1/bi/overview?days=30")
    assert response.status_code == 200  # ← INTENTIONAL
```

`/overview` 在 public flag 下 200 是**有意设计**——public flag 把 BI 的 aggregate metrics 开放给非 admin 角色（probably 用于 read-only KPI 看板）。同样的还有 `/members`（仅 dashboard 聚合，list 取值为空）。

### 真问题：`/feedback` 与配对端点的保护级别不一致

文件 `tests/api/test_bi_router.py` 已经为 `/commerce`、`/invite-test/applications`、`/invite-test/stats` 各写了 `test_bi_router_public_flag_does_not_expose_*` 测试（line 446, 459, 472），证明这三条携带 user-level 字段的端点**即使 public flag on 也必须 403**。

但是 `/feedback` 没有对应的保护测试，handler 也没有 `_auth: AuthContext = Depends(require_bi_admin)`：

```python
# deeptutor/api/routers/bi.py:197
@router.get("/feedback")
async def bi_feedback(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
):  # ← MISSING require_bi_admin
    return await get_bi_service().get_feedback(days=days, limit=limit)
```

而 `/feedback` 返回的 `recent[]` 每条记录暴露：

```json
{"id":"...", "user_id":"<real>", "session_id":"<real>", "message_id":"<real>",
 "request_id":"...", "trace_id":"...", "comment":"<user-typed>",
 "triage_operator":"<admin>", "rating":-1, "reason_tags":["逻辑不通"], ...}
```

这跟 `/commerce` (ledger / orders / 钱包流水) 同属 user-level 数据。**漏保护是 oversight，不是 design intent**。

### 建议修复（具体 diff，**未提交**，原因见下）

```diff
--- a/deeptutor/api/routers/bi.py
+++ b/deeptutor/api/routers/bi.py
@@ -197,6 +197,7 @@
 @router.get("/feedback")
 async def bi_feedback(
     days: int = Query(30, ge=1, le=365),
     limit: int = Query(20, ge=1, le=100),
+    _auth: AuthContext = Depends(require_bi_admin),
 ):
     return await get_bi_service().get_feedback(days=days, limit=limit)
```

+ 在 `tests/api/test_bi_router.py` `test_bi_router_public_flag_does_not_expose_invite_test_stats` 之后插入：

```python
def test_bi_router_public_flag_does_not_expose_feedback(
    bi_service: BIService,
    monkeypatch,
) -> None:
    # /feedback recent records carry user_id / session_id / message_id /
    # trace_id / triage_operator / free-text comment — same identifier class
    # the existing commerce + invite-test admin gates protect.
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "1")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get("/api/v1/bi/feedback?days=30&limit=10")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"
```

### ⚠️ 本次为什么没把这个 fix commit/push

调试过程中发现本机仓库的 **`git core.worktree` 指向 `/private/tmp/deeptutor-learning-report-wire-all-pages-20260524093840`**，而 Claude Code 的 OS cwd 是 `/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor`。两个路径**不是同一份工作树**：

- 在 `/Users/...` 用 Edit 工具改文件 → 仅写到 /Users 视图的磁盘，git 看不到（git status 报 clean，diff 为空，但 hash-object 与 index 不一致）
- 真正的 git 工作树 `/private/tmp/...` 当前 checkout 在 `codex/learning-report-wire-all-pages-20260524093841`（不是 main，且有别人的 WIP）
- 在这种 dual-worktree 配置下，盲跑 commit 风险高：可能把改动落到错误分支或错误工作树

> 这本身是 P2 housekeeping（B-P2-3）：本仓库需要重新对齐 worktree。建议用户在干净的 worktree（最好是 `git worktree add` 出来的新分支）里 apply 上面的 diff、跑 `pytest tests/api/test_bi_router.py -k feedback -q`、commit。

### Sanity guard（未实现）

`docs/zh/bi/bi-backoffice-v2-rollout-runbook.md` 第 7 节"上线核对清单"建议补一条：每次部署后 `curl https://test2.yousenjiaoyu.com/openapi.json | jq '.paths' | grep "/bi/"` 比对预期路由集 + 抽样验证 public flag 下 user-level 字段是否保护。本次未实现，列入 B-P2-2。

---

## 5. 失败 / 修复列表

| # | 类目 | 状态 |
|---|---|---|
| 1 | 自动化守护 | 0 failures |
| 2 | 未登录 admin gate UI | 0 failures |
| 3 | 公网读端点权限 | 1 P0 (上方第 4 节) — **未修** |
| 4 | 公网写端点 admin 闭环 | 未覆盖 — backlog |

本次**无 commit/push**：（a）pytest/tsc/守护都绿；（b）admin 实测未做，缺乏直接 fix 触发点；（c）P0 修复涉及部署侧 env 改动 + 测试 + PR，应单独提交而非塞进本次 QA 报告。

---

## 6. P1 / P2 Backlog（明确未完成项）

**Backlog 项目，不允许被解读为"已完成"**：

### ✅ P1 修复已落地 + merged + deployed + public 403 verified（B-P1-0 done）

- **B-P1-0 ✅ DONE** 完整闭环：
  - Commit（local）: `01b27202 fix(bi): require admin for /api/v1/bi/feedback under public flag`
  - PR: https://github.com/chenyh200807/luban-deep/pull/25 — **CI 8/8 SUCCESS** (Contract Guard / Frontend / WX / Yousen / Import 3.11+3.12 / Smoke 3.11 / Test Summary)
  - Squash merge commit on `origin/main`: **`a25da582d33cea94e90b427fb1492d1ee77d8082`**
  - 阿里云部署（`/root/deeptutor`，via `scripts/redeploy_aliyun_fast.sh`）: 完成；`DEEPTUTOR_GIT_SHA=a25da582d33cea94e90b427fb1492d1ee77d8082` 与 merge commit 一致
  - 部署 canary: `/healthz` 200 + `uptime_seconds=47.6`；`/readyz` 200, 全 checks ready；`/openapi.json` 含 `GET /api/v1/bi/feedback`
  - **公网安全回归（未带 token）**：
    - `GET /api/v1/bi/feedback?days=30&limit=10` → **403** (修复前 200) ✅
    - `GET /api/v1/bi/commerce` → 403 (regression) ✅
    - `GET /api/v1/bi/invite-test/applications` → 403 (regression) ✅
    - `/bi` → admin gate 文案 + "登录后台" 按钮 + 无 "新对话/聊天" 侧栏 ✅
    - `/bi?tab=invite-test` → admin gate（bodyLen=104，非白屏） ✅
    - `/bi?tab=member-ops` → admin gate（bodyLen=104，非白屏） ✅
  - 工作树（部署）: `/private/tmp/deeptutor-deploy-post-pr25` @ branch `deploy/post-pr25` @ `a25da582`
  - 证据截图: `/tmp/bi_qa_evidence/post_deploy_bi_default.png`, `post_deploy_bi_invite_test.png`, `post_deploy_bi_member_ops.png`
- **B-P2-3** 仓库 worktree 配置 fix（`core.worktree`）：本次修复路径上发现 `git worktree add` 创建的 linked worktree 的 `config.worktree` 文件**没有自动写入**，导致 git 看不到工作树里的改动。Workaround：手动写 `/Users/yehongchen/.gitdirs/deeptutor-documents.git/worktrees/<name>/config.worktree` 设置 `[core] worktree = <abs path>`。**这是 Conductor / git 配置层 bug**，长期建议查清 `extensions.worktreeConfig=true` 与 `git worktree add` 的交互

### P1（admin 路径 — 等本次 token 缺位补完）

- **B-P1-1** 用真实 admin token 在 `/bi?tab=overview|member-ops|commerce|feedback|ops` 五主区跑数据加载、抽屉、筛选、搜索抓 evidence（截图 + DOM）
- **B-P1-2** 真实 POST `/api/v1/bi/feedback/{id}/triage` 用 `{status: "ignored"}` + X-Idempotency-Key 实跑两次，证明 `deduped=true` 路径
- **B-P1-3** 真实 POST `/api/v1/bi/member/{id}/ops-action`，验证 audit_log 落 `ops_action_result`
- **B-P1-4** 真实 POST `/api/v1/bi/export-jobs`，验证 audit_log 落 `bi_export_request`
- **B-P1-5** Negative：去掉 Authorization、去掉 X-Idempotency-Key，确认 401/403、400 detail 正确（脚本已写：`/tmp/bi_qa_evidence/qa_sweep.sh`）
- **B-P1-6** 全局搜索路由：phone (`138...`) → member-ops、order key → commerce — 在 admin 态实跑
- **B-P1-7** mobile (390) 在 admin 态下打开 5 主区，截图核对核心按钮不溢出（admin gate 路径已验证，admin 态下面板未验证）

### P1 — 高危动作 ETag / undo_token

- **B-P1-8** **撤销会员 / 补点 / 修账等高危写动作目前没有 ETag / version / undo_token 防误操作机制**。QA spec 明确："若仍无 ETag/version/undo_token，不允许报告为已完成"——这条不在本次范围，但在此显式列出，**禁止在后续工作中跳过**

### P2

- **B-P2-1** 本地 main (`46feb1a2`) 与 origin/main (`b9ade218`) 已分叉 6+4=10 commit，且有 1766/-138 行未提交工作树。需要 rebase + 解决冲突 + 决定 WIP 的去留。**不是本次 QA 的修复范围**，需独立 ticket
- **B-P2-2** 用户给定的"deploy=54ab8351"信息已过期。**B-P2-2 子项**：更新 `docs/zh/bi/bi-backoffice-v2-rollout-runbook.md` 把当前部署点改成 origin/main 的真实 commit + 校验程序（建议在每次部署后 `/openapi.json` 比对路由集，挂在 CI）

---

## 7. 证据路径

| 类目 | 路径 |
|---|---|
| Admin gate 截图 | `/tmp/bi_qa_evidence/01_admin_gate.png`, `02_admin_gate_tablet_1024.png`, `03_admin_gate_mobile_390.png` |
| Sweep 脚本（含 admin token 用例，等 token 触发） | `/tmp/bi_qa_evidence/qa_sweep.sh` |
| Pytest 摘要 | `/private/tmp/claude-501/-Users-yehongchen-Documents-CYH-2-Markzuo-deeptutor/0f26ec23-be4f-4f75-85bf-fcab0b61dd5b/tasks/bqmatlldd.output`（"104 passed in 84.76s"） |
| TSC | bg task `brlc8q1rs`, exit 0 |
| Mock boundary | inline："OK · production bundle does not contain BI v2 mock fixtures" |
| Route budgets | inline：BI=252KB；root-shell=191KB/220KB；所有路由都在 budget 内 |
| OpenAPI dump | `/tmp/openapi.json`（169KB） |

---

## 8. 命令输出摘要（关键片段）

```text
# pytest 套件
........................................................................ [ 69%]
................................                                         [100%]
104 passed in 84.76s (0:01:24)

# tsc
$ npx tsc --noEmit
exit 0 (no errors)

# mock boundary
OK · production bundle does not contain BI v2 mock fixtures

# route budgets
OK   /bi           252KB
OK   root-shell    191KB / budget 220KB

# 未登录公网读 P0 证据
GET /api/v1/bi/overview          code=200 bytes=22361   ← 期望 401/403
GET /api/v1/bi/members           code=200 bytes=21439   ← 期望 401/403
GET /api/v1/bi/feedback          code=200 bytes=24266   ← 期望 401/403  (含 user_id/session_id/comment/trace_id)
GET /api/v1/bi/commerce          code=403 bytes=34      ✓
GET /api/v1/bi/invite-test/...   code=403 bytes=34      ✓
```

---

## 9. 本次结论（一句话）

**通过**：自动化守护 (115/115 pytest + tsc + mock boundary + route budgets) + 未登录态前端 admin gate (1440/1024/390 三视口) + bundle/route 边界。
**P1 修复完整闭环**：B-P1-0 done — commit `01b27202` → PR #25 8/8 CI green → squash merge `a25da582` → 阿里云 `/root/deeptutor` fast deploy → `DEEPTUTOR_GIT_SHA=a25da582` 与 merge commit 一致 → 公网回归 6/6 PASS（`/feedback` 从 200 变 403；`/commerce` `/invite-test/applications` 仍 403；`/bi` `/bi?tab=invite-test` `/bi?tab=member-ops` admin gate 渲染正常）。
**未通过 / 未完成（admin token 缺）**：B-P1-1~7（5 主区 admin 实测 + 写动作公网真流量 + 全局搜索 + admin 态 mobile）。
**Stop hook 状态**：自动化守护 + 未登录 admin gate + P1 fix 完整闭环（含线上验证）全部 done；剩余 admin-only 验证项 B-P1-1~7 明确 backlog 且仍未完成；B-P1-8（高危动作 ETag/undo_token）独立追踪，按 QA spec "不允许标完成"。**本次不宣称 BI 完整 QA 已完成**。

— Claude QA, 2026-05-24
