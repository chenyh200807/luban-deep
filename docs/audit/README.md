# PR-0 Audit Baselines

> **状态**: PR-0 of [2026-05-25 Prelaunch Readiness Checklist v2.1](../plan/2026-05-25-prelaunch-readiness-checklist.md)
> **目标**: 仓库内的可对照 baseline，用于后续 PR 检测"是否新增匿名 endpoint / 未启 RLS 的 public 表 / 失控的 anon grants"。**只报告不 fail**。后续 PR (PR-1a / PR-2 / 之后的 CI gate) 会把这些 baseline 当对照基线。

## 两份 baseline

| 文件 | 来源 | 重要字段 |
|---|---|---|
| `route_inventory.json` | `python scripts/ci/runtime_route_inventory.py` —— 启动 FastAPI app 反射每个 `APIRoute` / `APIWebSocketRoute` 的 dependency 树（router-level + endpoint-level） | `endpoints[*].has_auth_dep` / `has_rate_limit_dep` / `classification` |
| `rls_audit.json` | `SUPABASE_DB_URL=... bash scripts/ci/live_rls_audit.sh` —— 直连 Supabase Postgres 查 `pg_tables` / `pg_policies` / `information_schema.role_table_grants` | `tables[*].rls_enabled` / `n_policies` / `grants` |

## 如何重跑

```bash
# Route inventory（不依赖外部服务）
.venv/bin/python scripts/ci/runtime_route_inventory.py > docs/audit/route_inventory.json

# Live RLS audit（要 DATABASE_URL / SUPABASE_DB_URL 指向目标库）
set -a; source .env; set +a
SUPABASE_DB_URL="$DATABASE_URL" bash scripts/ci/live_rls_audit.sh > docs/audit/rls_audit.json
```

## PR-0 关键 finding（必须在 internal beta 开放注册之前修）

### Finding A — Route 暴露面

| 指标 | 数值 |
|---|---|
| API endpoints 总数 | **252** |
| secure_authed | 161 |
| anonymous_no_ratelimit | **91**（上界） |
| anonymous_ratelimited_only | 0 |
| WebSocket endpoints | 7 |

**91 anonymous endpoints 是上界**，含三类（runtime inventory 反射看不见 handler body 内 auth）：

1. **真 P0 anonymous（必须 SR1 修）**：vision_solver / unified_ws / observability/surface-events / co_writer / solve / question / guide / learning_brain / knowledge 读端，对应 v2.1 计划 A1-A11。
2. **body-level auth 伪阳性**（`_resolve_authenticated_user_id` 在 handler 体内硬 401）：mobile.py 系列 7 个、auth/profile / billing / conversations / practice 等约 33 个。
3. **by-design public**（应转 `public_router(reason=...)`）：auth/login / auth/register / auth/send-code / auth/refresh / wechat/mp/login / wechat/mp/bind-phone / invite-test / agent-config / system/public-capabilities / healthz / readyz 等约 16 个。

后续 PR-1a 引入 `_secure_router.py` + `public_manifest` 后，runtime inventory 会从上界变成精确数（每个 endpoint 明确标 `is_public_marker`）。

### Finding B — RLS 真实暴露面 ⚠️ 远超 v2.1 计划估计

| 指标 | 数值 |
|---|---|
| public schema 表总数 | **84** |
| RLS 完全关闭 | **27** |
| RLS ON + 0 policy（service-role 沉默模式） | 35 |
| RLS ON + 至少 1 policy | 22 |

**v2.1 计划的 SR2 只标了 `assessment_forms` 1 张未启 RLS。实测远超预期：27 张表 RLS off，且 anon 全权限 grants。**

### Finding C — Anon PostgREST 真实读取测试（critical）

用 SUPABASE_ANON_KEY + `HEAD` / row-count probe（不打印数据）测试 6 张代表性表：

| 表 | HTTP 200 anon-readable? | 实际行数（生产） |
|---|---|---|
| `users` | 🚨 yes | **1623** |
| `wallet_ledger` | 🚨 yes | **1329** |
| `assessment_forms` | 🚨 yes | 55 |
| `learner_summaries` | 🚨 yes | 14 |
| `member_audit_log` | 🚨 yes | 0（结构暴露） |
| `platform_user_bindings` | 🚨 yes | 0（结构暴露） |

**结论**：任何持有 `SUPABASE_ANON_KEY` 的客户端（小程序前端代码、浏览器抓包、git 历史泄露）可一次 dump 全部 1623 用户 + 1329 钱包流水。这是 production-critical P0 attack surface，必须在 internal beta 开放注册前由 PR-2 SR2 修复。

完整 27 张 RLS-off 表清单见 `rls_audit.json`；关键业务/PII 表：
- `users` `wallet_ledger` `platform_user_bindings` `user_sessions`
- `learner_summaries` `learner_memory_events` `learner_wikis` `learning_plans` `learning_plan_pages`
- `member_audit_log` `member_notes` `org_members` `organizations`
- `assessment_forms` `daily_paths` `intents` `teaching_cards` `question_intelligence`
- `oa_*` 7 张审计/事件表
- `run_evidences` `compiled_asset_feedback_log` `heartbeat_jobs`
- 2 张元数据表 `alembic_version` `schema_migrations`（无敏感数据，但 schema 暴露）

## 后续 PR 依赖关系

| PR | 用 baseline 做什么 |
|---|---|
| **PR-1a SR1 manifest** | 加 `is_public_marker` 字段；上界 91 精确化到真实匿名数 |
| **PR-1b SR1 行为切换** | A1-A11 端点迁移后，inventory diff 应显示 anonymous_no_ratelimit 数下降 |
| **PR-2 SR2** | 27 张 RLS off 表逐张修；diff `rls_audit.json` 应显示 rls_off 归零；6 张 anon-readable 表实测 → HTTP 403 |
| **CI** | PR-2 后把 inventory + rls_audit 升级为 fail-on-mismatch gate |

## 重要边界（按 AGENTS.md）

- 本目录的 baseline 是**只读 artifact**，不参与 supabase migration apply（codex review R2 修订）。
- `live_rls_audit.sh` 是 **read-only** 查询，不动数据。
- 实测 PostgREST 用 `HEAD` + row-count probe，**不 SELECT 真实数据**；任何后续验证必须保持 read-only 原则。
- `route_inventory.json` 含完整 endpoint × dependency 矩阵（3592 行），diff-friendly 排序固定（path → method）。
