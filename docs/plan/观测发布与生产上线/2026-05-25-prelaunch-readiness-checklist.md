# 2026-05-25 内测上线 Production Readiness Checklist

> **状态**: Draft v2.1（2026-05-25，根因版 + codex second-opinion 修订）→ **代码侧 SR1-SR6 已落 main + 接 CI（2026-05-30 plan-vs-code 核验确认）**；剩余为人工 release gate（真机回归、观察期、`runtime_route_inventory.py` Layer B 接 CI、`supabase/schema_baselines/` dump）待补。G1-G9 验收日期待人工填，未达 Done。详见 [2026-05-30-plan-vs-code-reconciliation.md](2026-05-30-plan-vs-code-reconciliation.md)。
> **代码事实校验（2026-05-30）**: SR1 `_secure_router.py` + `check_secure_routers.sh FAIL_ON_NEW` 已接 `tests.yml:113`；SR2 `check_rls_on_create_table.sh` 接 `tests.yml:116`、#75/#82 RLS harden；SR3 限流 single authority（`route_rate_limit` + `enforce_websocket_rate_limit`）；SR4 LLM client factory（`openai_http_client.py` 三 factory）；SR5 `/readyz` 一致性；SR6 `runtime/safety.py`（spawn_task/readiness/exception handler）接 `main.py` + `tests.yml:124`。计费止血 `wallet/service.py` enforcement flag 默认 OFF（#79）。active-turn-capacity 50-120 仍 0 代码（`Proposed` 属实，内测 <100 DAU 不阻塞）。
> **主线**: 生产部署 / Observability 与 release gate
> **来源**: 8 维度上线前审查 + 4 组根因 subagent 深度评估（SR1 路由认证 / SR2 Schema-RLS / SR3-5 限流-LLM-Healthcheck / SR6 Runtime safety）+ codex CLI 200 IQ 独立 review
> **审查上下文**: 内测窗口 < 100 DAU / 本周内开放 / 后端 FastAPI + WebSocket + Supabase + 多 LLM provider / **小程序 DevTools project root = `yousenwebview/`，主业务验收面 = `packageDeeptutor/` 分包（`wx_miniprogram/` 仅 shadow 辅助）** + 阿里云 Docker Compose 部署
> **v1 → v2 修订理由**: v1 把 10 个 P0 当孤立补丁修，违反 thin wrappers + first principles + less is more。v2 把 10 个 P0 收敛为 **6 个根因簇（SR1-SR6）**，每个根因簇用 1 个 thin wrapper + 1 个 CI grep gate 在源头阻断，并把 v1 漏掉的 8 个同根因 P0 一并暴露（最关键：A5-A8 在 staging/dev 全开的 LLM-trigger 端点；anthropic.py:14 dead import；public.users / public.wallets schema 不在 git）。
> **v2 → v2.1 修订理由**: codex 独立 review 命中 5 个 v2 设计盲区——(R1) **grep gate 不是安全边界**（alias / wrapper / `include_router` 都能绕，必须叠加 runtime route inventory gate）；(R2) **baseline schema dump 放进 `migrations/` 会让 fresh env 重复 apply**（改放 `supabase/schema_baselines/` 非 migration artifact + 加 live RLS audit query）；(R3) **SR6 4 个 primitive 上线前不应一次性打包**（BoundedQueue 对 WS 流式可能丢用户可见 token，必须分级：上线前 = subscriber spawn_task + readiness callable + exception envelope；BoundedQueue 推 W1 加压测 + channel-level 策略）；(R4) **PR-α owner_key 回填不是 0.5h，是 1d**（canonical owner 来源 + dry-run + 备份 + idempotency + 抽样验证）；**PR-1 拆分太粗**（拆 PR-0 inventory-only gate / PR-1a manifest 引入 / PR-1b 行为切换）；(R5) **2.5 人日严重低估**——实际 **2.5 人日代码收口 + 1.5-3 人日验证/数据/部署风险预算 = 4-6 人日总盘**。
> **后续修订**: 任何 P0 项变更或新增 P0 都必须更新本文件 + INDEX.md，不要再开第二份 checklist

## 0. 目标与非目标

### 目标

- 内测上线前 24 小时之内把所有 🔴 P0 阻断项修完且回归通过
- 把上线后 W1（7 天内）需要补的 🟡 P1 项目固化到这一份 checklist 上，避免散落到多份文档
- 给出上线后 W2-W4 滚动修复的 🟢 P2 列表，作为内测期工作背景板
- 长期债务（>1 个月迭代成本急剧上升的风险）单独记录，不混进 checklist，避免被忽略

### 非目标

- 不在本计划里做"如何拆 routers/mobile.py"或"如何拆 member_console/service.py"的具体设计，长期债务那一节只标出方向
- 不替代既有的 `2026-04-19-deeptutor-50000-member-deployment-prd.md`（5 万会员部署 PRD）和 `2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md`（readiness dashboard 实现计划）；本文件是它们的 **本次上线即时门槛子集**
- 不替代 `CONTRACT.md` 与 `contracts/index.yaml` 对契约层的硬约束

## 1. 单一 Authority

- 本次内测上线的 **P0/P1 阻断与限期项**，全部以本文件为单一权威
- 任何审查报告里的更高优先级新发现，必须把项目搬到本文件而不是在别处堆积清单
- 长期债务条目（§5）链接到主线 PRD，不在这里立独立子计划

## 2. 验收 Gate（上线前必须全绿）

| Gate | 条件 | 责任入口 |
| --- | --- | --- |
| **G1 SR1 路由认证** | `_secure_router.py` + `check_secure_routers.sh` 上线；A1/A2/A4 三处迁移完成；A2 owner_key 回填脚本已跑；anon `curl` / `wscat` 测试 401 / 4401 | `deeptutor/api/_secure_router.py` `routers/vision_solver.py` `unified_ws.py` `observability.py` |
| **G2 SR2 Schema/RLS** | `check_migration_uniqueness.sh` + `check_rls_on_create_table.sh` 上线且 CI 绿；A3 migration 已应用；B1 rename 完成且所有环境 `schema_migrations.version` 已手工 update；prod schema baseline dump 完成 | `supabase/migrations/` `scripts/ci/` |
| **G3 SR3 限流** | invite_test 接入 `route_rate_limit`；WS start_turn 单连接限流；`grep _RATE_LIMIT_BUCKETS` 为空 | `routers/invite_test.py` `routers/unified_ws.py` |
| **G4 SR4 LLM client** | `make_openai_client` / `make_anthropic_client` 全部就位；8 处替换完成；`anthropic.py:14` dead import 清除；`grep AsyncOpenAI(` 仅在 factory 内 | `services/llm/openai_http_client.py` + 6 个 provider 文件 |
| **G5 SR5 Healthcheck** | Dockerfile + ghcr.yml 均探 `/readyz`；`verify_runtime_assets.py` 通过 3 文件矩阵校验；阿里云 SLB 7 层探活路径文档化 | `Dockerfile` `docker-compose.ghcr.yml` `scripts/verify_runtime_assets.py` |
| **G6 SR6 Runtime safety** | `runtime/safety.py` 就位；`unified_ws.py` + `turn_runtime.py` 关键 8 处迁移完成；`/readyz` 主动探测 SQLite/LLM；500 走统一 envelope；3 段 grep gate 绿 | `deeptutor/runtime/safety.py` `api/main.py` |
| **G7 P0 测试通过** | `pytest tests/api tests/services/security tests/services/observability tests/runtime tests/contracts` 全绿；新增的 secure_router / readiness / queue 单测全过 | `tests/` |
| **G8 阿里云 deploy 演练** | `scripts/deploy_aliyun.sh --dry-run` 通过；rollback 路径用 `rollback_aliyun_release.sh` 真验证一次（不是 dry-run） | `scripts/` + `/root/deeptutor` |
| **G9 微信开发者工具回归** | **DevTools `--project` 必须打开 `yousenwebview/` 项目根，主业务验收目标是其中的 `packageDeeptutor/` 分包页面**；`wx_miniprogram/` 仅做 shadow 辅助核对。4 个核心路径：登录 / 聊天 / 个人中心 / 网络断开 + WS 4401 时小程序触发 relaunchLogin（用 PR-1b 修完的 WS auth 路径实测）。每次记录 `auth_state` / `auth_mode`；登录不可用只能记 `partial/auth_blocked`，不能冒充真微信 PASS。 | `yousenwebview/` project root + `packageDeeptutor/` target subpackage（主） + `wx_miniprogram/`（shadow） |

**只要 G1-G9 任一未达成，不允许打开内测注册。**

## 3. 🔴 P0 根因修复（上线前必须完成，估算合计 ≈ 2.5 人日）

> **v2 视角**：v1 的 10 个 P0 不是 10 个孤立 bug，是 **6 个系统缺口**（SR1-SR6）的表面症状。每个 SR 用 1 个 thin wrapper（≤120 行）+ 1 段 CI grep gate 在源头阻断；补丁视角修今天，根因视角让未来不再发生。
>
> 4 组根因 subagent 评估暴露了 v1 漏掉的 **8 个同根因 P0**（最关键：A5-A8 在 staging/dev 全开的 LLM-trigger 端点；`services/llm/providers/anthropic.py:14` dead import；`public.users` / `public.wallets` schema 不在 git；46 处裸 `asyncio.create_task` / 14 个 unbounded queue）。
>
> **三大原则落点**：(a) Thin wrappers / fat skills：6 个 SR 共加约 **500 行项目级代码**（`_secure_router.py` 70 / `runtime/safety.py` 110 / `client_factory` 升级 40 / migrations 模板 + 2 段 SQL / 5 段 grep gate）；(b) First principles：补丁修不了"下一个 P0"，根因 + gate 才能；(c) Less is more：禁止引入 RBAC DSL / policy framework / 自研限流 / 自研 Queue。

### 3.0 6 个 SR 总览

| SR | 根因（一句话） | v1 表面 P0 | 举一反三新发现 | Thin wrapper | CI gate | 工时 |
|---|---|---|---|---|---|---|
| **SR1** 路由认证 single authority | FastAPI `APIRouter()` 默认零认证 + 项目没 default-secure factory | A1, A2, A4 | A5-A8（co_writer/solve/question/guide LLM trigger 全 anon，staging/dev 全开）+ A9 learning_brain IDOR + A10-A11 knowledge 读端 9 个 anon + A12-A14 by-design public 未声明 + A15 chat.py 死代码 | `deeptutor/api/_secure_router.py`（70 行：`secure_router` / `public_router(reason=...)` / `secure_ws_endpoint`） | `scripts/ci/check_secure_routers.sh`（30 行 grep） | 2h Phase 0 + W1 分批迁移 |
| **SR2** Schema/RLS 治理 | 无 CI gate 拦"建 public 表但没 enable RLS" + 无 timestamp uniqueness gate | A3, B1 | 4 张表"RLS ON + 0 policy"沉默模式（wallet_ledger / user_identity_aliases / invite_test_applications / bot_learner_overlay_audit）+ **`public.users` 和 `public.wallets` schema 不在 git**（盲区）+ assessment_sessions 缺 DELETE policy + audit 表给 authenticated 读写违反合规 | `supabase/migrations/_TEMPLATE.md` + 2 段 bash CI gate | `check_migration_uniqueness.sh` + `check_rls_on_create_table.sh` | 2h |
| **SR3** 限流 single authority | `route_rate_limit` 已存在但没强制使用 | A5 | 顺手做 v1 P1-S3（WS 单连接 start_turn 限流，同根因） | （复用既有 `api/dependencies/rate_limit.py`） | grep `_RATE_LIMIT_BUCKETS` 应为空 | 2.5h |
| **SR4** LLM client factory single authority | 8 处直接 `AsyncOpenAI()`/`AsyncAnthropic()` 散落 + 现有 `openai_http_client.py` 是半成品 factory | B2 | **`services/llm/providers/anthropic.py:14` dead import**（`from ..http_client import get_shared_http_client` 模块不存在，被 RoutingProvider 加载即 ImportError，是隐藏 P0） | 把 `services/llm/openai_http_client.py` 升级为真 factory（+40 行），暴露 `make_openai_client` / `make_anthropic_client` / `make_azure_openai_client` | grep `AsyncOpenAI(` / `AsyncAnthropic(` 在 factory 之外应为空 | 4h |
| **SR5** Healthcheck path 一致性 | Dockerfile / docker-compose / ghcr 三处字符串字面值，2 处错路径 | B3 | 阿里云 SLB 7 层探活路径需配 `/readyz`（在 runbook 补，不在仓库） | 不抽 Python 常量；扩展现有 `scripts/verify_runtime_assets.py` 校验矩阵 | 现有 verify_runtime_assets 升级 + grep `HEALTHCHECK\|healthcheck \| /readyz` 一致性 | 1.5h |
| **SR6** Runtime safety primitives | 46 处裸 `asyncio.create_task` / 14 个 unbounded `Queue` / readiness 静态 dict / 0 个 exception handler | C1, C2 | `loop.create_task` 5 处 + `asyncio.gather(return_exceptions=True)` 18 处忽略异常 + 至少 5 处遗漏 readiness check（SQLite/Supabase/Langfuse/RAG embedding/search provider） | `deeptutor/runtime/safety.py`（110 行：`spawn_task` / `BoundedQueue` / `register_readiness_check` / `install_exception_handlers`） | 3 段 grep：禁裸 create_task / 禁 Queue() 无参 / main.py 必调 install_exception_handlers | 3.8h |

**合计**（v2.1，codex R5 真实化）：
- 纯代码收口 ≈ **2.5 人日**（PR-0 + PR-α + PR-1a + PR-1b + PR-2 + PR-3 + PR-4 + PR-5；详见 §3.7）
- 验证/数据/部署风险预算 ≈ **2.5 人日**（runtime inventory matrix、多环境 schema_migrations 修正、LLM 全链路回归、异常路径回归、G7-G9 验收 + 阿里云 deploy/rollback 实演）
- **总盘 ≈ 5 人日**

v2 写 2.5 人日是只算 wrapper 代码；codex R5 命中要害：最贵的部分是**证明线上 authority 真的只有一套**——runtime inventory matrix、多环境数据迁移、LLM 全链路回归、生产 RLS audit baseline，这些不在 IDE 里。

---

### 3.1 SR1 — 路由认证 single authority（关 A1/A2/A4 + 8 个同根因隐藏 P0）

**根因**：FastAPI `APIRouter()` 默认零认证，认证靠每个 router 自觉手写 `Depends(get_current_user)`。漏一处即破。补丁修 3 个，下个月会出第 4/5/6 个（已经发生：A5-A8 就是）。

**修复路径**：

- **新文件** `deeptutor/api/_secure_router.py`（≤80 行），暴露 3 个 API：
  - `secure_router(prefix, *, tags=None, extra_dependencies=None, **kwargs) -> APIRouter`：默认带 `Depends(get_current_user)`，所有 endpoint 自动 401
  - `public_router(prefix, *, reason: str, ...) -> APIRouter`：显式无认证，`reason` 必填且长度 ≥ 12（运行时 ValueError + CI grep 双校验）
  - `secure_ws_endpoint(ws, *, rate_limit_scope, rate_limit_max, rate_limit_window_seconds) -> AuthContext`：WS handshake 期强制 4401 + rate-limit，**永远返回非 None** AuthContext（一键关掉 A2 的 owner_key 缺失旁路）

- **CI gate 双层设计**（codex review R1 修订）：
  - **Layer A（静态 grep，低成本 lint）** `scripts/ci/check_secure_routers.sh`（≤30 行）：
    - Rule 1：`APIRouter(` 在 `deeptutor/api/routers/` 内不允许（必须用 factory）
    - Rule 2：`public_router(` 必须含 `reason=`
    - Rule 3：含 `@router.websocket` 的文件必须调 `secure_ws_endpoint`
    - Rule 4：含 endpoint 装饰器的文件必须出现 `route_rate_limit` 或 `enforce_websocket_rate_limit`（WARN）
  - **Layer B（runtime route inventory，真 single-authority gate）** `scripts/ci/runtime_route_inventory.py`（≤80 行）：
    - 启动 FastAPI app（`from deeptutor.api.main import app`）
    - 遍历 `app.routes`：对每个 `APIRoute` / `WebSocketRoute` 实际反射出依赖链
    - 验证：(a) 是否有认证 dependency（`get_current_user` / `require_admin` / ...）；(b) 是否在 `public_manifest`（白名单 + reason）；(c) WS 端点是否打了 `secure_ws_endpoint` marker；(d) LLM-trigger endpoint（标记 `@llm_trigger` 或注册到 `LLM_TRIGGER_REGISTRY`）必须 ≠ anonymous
    - 输出 JSON 报告 `tmp/route_inventory.json` 含完整 endpoint × authn × ratelimit × public-reason 矩阵
    - **alias import / wrapper / include_router 绕行场景 grep 测不出 → runtime inventory 可以**（这是 codex R1 核心命中：grep 是 lint 不是 boundary）
  - 接入：Layer A 作 pre-commit；Layer B 在 PR CI 跑 + 每次 deploy 前跑（输出对照 baseline matrix 找新增 anonymous endpoint）

- **Phase 0（上线前 24h，≤2h）**：建 factory + gate；迁 vision_solver / unified_ws / observability/surface-events；其余 router 加 CI allowlist（一两行白名单）逐周拆迁
- **Phase 1（W1）**：按危害顺序迁 co_writer → solve → question → guide → learning_brain → knowledge 读端 → mobile.py（拆 `/auth/*` 子树为 `public_router`，其余转 `secure_router`）→ agent_config / invite_test / system 公共端点
- **Phase 2（W2-W4）**：清空 allowlist，删 `chat.py` 死代码，CI 闸严格化

**关键风险 / 必须先做的事**：
- **A2 修完会让真正遗留 owner_key 缺失的老 session 全部 PermissionError** → **必须先跑 owner_key 回填脚本**（参考 `sessions.py` 已有语义），否则正常用户也会撞"Session not found"。Phase 0 第一步是这个回填，不是 factory。
- FastAPI router-level dep 对 WS 的运行时行为有版本 regression 历史 → `secure_ws_endpoke` 走显式 `close(4401)` 模式回避，不依赖 router-level dep 拦截 WS

**举一反三发现（必须同步处理）**：

| Tag | 端点 | 危害 | 状态 |
|---|---|---|---|
| A5 | `co_writer.py` 8 个 LLM 触发 endpoint | prod 由 `_legacy_routers_enabled()` 关，staging/dev 全开 | Phase 1 |
| A6 | `solve.py` 3 REST + 1 WS | 同上 | Phase 1 |
| A7 | `question.py` 2 WS | 同上 + LLM PDF 上传 | Phase 1 |
| A8 | `guide.py` 13 REST + 1 WS | LLM trigger + session IDOR | Phase 1 |
| A9 | `learning_brain.py` 2 个 endpoint | 接受任意 `user_id` Query 写 grading event（IDOR） | Phase 1 |
| A10-A11 | `knowledge.py` 9 个读端 + WS `/progress/ws` | KB 元数据 + 拓扑泄露 | Phase 1 |
| A15 | `chat.py` 已不挂载但代码在 | 未来若被人 include_router 即回 P0 | Phase 2 删 |

---

### 3.2 SR2 — Schema/RLS 治理（关 A3/B1 + 4 张沉默表 + git 盲区）

**根因**：(a) 无 CI gate 拦 "新建 public 表但未启 RLS"；(b) 无 CI gate 拦 timestamp 撞车。补丁修 2 个，下次还会有。

**修复路径**：

- **CI gate A** `scripts/ci/check_migration_uniqueness.sh`（≤40 行 bash）：timestamp prefix 唯一性 + 单调递增
- **CI gate B** `scripts/ci/check_rls_on_create_table.sh`（≤40 行 bash）：任何 `create table public.<X>` 必须在同 migration 内出现 `alter table public.<X> enable row level security`；豁免方式 = 文件首行 `-- rls-exempt: <reason>`

- **A3 fix** — 新 migration `supabase/migrations/20260525120000_assessment_forms_enable_rls.sql`：
  ```sql
  begin;
  alter table public.assessment_forms enable row level security;
  revoke all on public.assessment_forms from anon;
  revoke all on public.assessment_forms from authenticated;
  comment on table public.assessment_forms is 'Prebuilt diagnostic assessment forms. Service-role only.';
  commit;
  ```

- **B1 fix** — rename 流程（codex R2 修订：不是 2h 任务，约 0.5-1 人日含多环境）：
  1. **先在每个环境**（dev / staging / prod）跑 dry-run query：
     ```sql
     select version, name, executed_at from supabase_migrations.schema_migrations
     where version like '20260419000100%' order by executed_at;
     ```
  2. 整理 3 个环境的实际状态（必须存在表格化清单），决定 rename + version update 的事务顺序
  3. `git mv supabase/migrations/20260419000100_wallet_authority_phase1.sql supabase/migrations/20260419000110_wallet_authority_phase1.sql`（选 wallet 因为 docs 引用面 5:1 较小）
  4. **手工事务脚本**（每个环境一份，带 `BEGIN ... COMMIT;` + 行数前后断言）：
     ```sql
     begin;
     -- pre-check row count
     select count(*) into _pre from supabase_migrations.schema_migrations where version='20260419000100' and name='wallet_authority_phase1';
     update supabase_migrations.schema_migrations set version='20260419000110' where version='20260419000100' and name='wallet_authority_phase1';
     -- post-check
     -- rollback if count mismatch
     commit;
     ```
  5. 每环境执行后 `supabase migration list --linked` 对账；如 mismatch 走 rollback（事务保护）

- **模板** `supabase/migrations/_TEMPLATE.md`（markdown，不会被 supabase CLI apply）：新表 checklist（命名 / RLS / policy / revoke / index / comment）+ 默认 stance = service_role only + 反模式列表

- **`public.users` / `public.wallets` 盲区** —— codex R2 修订：**不放进 `supabase/migrations/00000...`**（会让 fresh env 重复 apply prod 噪声），改放：
  - `supabase/schema_baselines/20260525_public_users_wallets_baseline.sql`（dump 来自 prod，含表头注释明确 "NOT applied by Supabase CLI; reference-only baseline for audit"）
  - `supabase/schema_baselines/README.md` 说明这个目录不在 CLI scan 路径，仅作 CI gate B 校验对照
  - CI gate B 扫描 baseline 目录把 `users` / `wallets` 加入"已知 public 表"清单，参与 RLS audit

- **Live RLS audit gate**（codex R2 新增，比静态 grep 更强）—— `scripts/ci/live_rls_audit.sh`（≤40 行）：
  - 连到目标 supabase（每个环境一次）跑：
    ```sql
    select n.nspname schema, c.relname tbl, c.relrowsecurity rls_on,
           (select count(*) from pg_policies p where p.schemaname=n.nspname and p.tablename=c.relname) n_policies,
           array(select grantee||':'||privilege_type from information_schema.role_table_grants where table_schema=n.nspname and table_name=c.relname and grantee in ('anon','authenticated')) grants
    from pg_class c join pg_namespace n on n.oid=c.relnamespace
    where n.nspname='public' and c.relkind='r' order by c.relname;
    ```
  - 对比仓库内 baseline JSON（`tmp/rls_audit_baseline.json`）；任何差异 → fail
  - 上线前手工跑一次入仓库；之后 CI 每周跑一次对账

**举一反三发现（必须同步处理）**：

| 表 | 现状 | 修复 |
|---|---|---|
| `wallet_ledger` | RLS ON + 0 policy（钱包账本！） | 补 `revoke all from anon, authenticated` + `comment on table` 注明 service_role only |
| `user_identity_aliases` | RLS ON + 0 policy（身份映射） | 同上 |
| `invite_test_applications` | RLS ON + 0 policy（PII） | 同上 + 加 anon 不可读断言测试 |
| `bot_learner_overlay_audit` | 给 authenticated 自读自写（**合规反模式**） | 改为 `for select to authenticated using (false)`，仅 service_role 可读 |
| `assessment_sessions` | 缺 DELETE policy；含 `session_questions_private` 私题字段 | 补 DELETE policy + 该列单独 column-level grant |
| **`public.users` / `public.wallets`** | **schema 不在 git**（无法 audit RLS） | dump 当前 prod schema 入 `supabase/migrations/00000000000000_baseline.sql` |

**关键风险**：
- B1 rename 后 supabase CLI 会以为新 migration → 必须手工 update `schema_migrations.version`，每个环境一次
- Gate B 一上线会立刻 fail（A3 未修），Gate A 一上线也会立刻 fail（B1 未修）→ **这是好事**，CI 报红正好对齐修复 PR；不要为了"CI 绿"先关 gate

---

### 3.3 SR3 — 限流 single authority（关 A5）

**根因**：`route_rate_limit` 已在 `deeptutor/api/dependencies/rate_limit.py` 存在，含 3 档后端（Redis/SQLite/Memory，自动 fallback），但 invite_test.py 还在用进程内字典 `_RATE_LIMIT_BUCKETS`。没有 CI gate 拦截二号实现。

**修复路径**：

- **invite_test.py**：删除 `_RATE_LIMIT_BUCKETS` / `_RATE_LIMIT_WINDOW_S` / `_RATE_LIMIT_MAX` / `_extract_ip` / `_is_rate_limited`；endpoint 改用 `Depends(route_rate_limit("invite_test_applications", default_max_requests=8, default_window_seconds=60.0))`
- **wechat openid 必填**：在 `InviteTestApplicationStore.submit_application` 里把 `payload.get("wx_openid")` 列为必填，缺则抛 `InviteTestApplicationValidationError`（≤5 行，与 SR1 同 PR 顺手做）
- **顺手并入 v1 P1-S3**：WS 单连接 start_turn 次数限流。在 `unified_ws.py` 收到 `start_turn` event 时调一次 `enforce_websocket_rate_limit(ws, "ws_start_turn", 10, 60.0)`（≤20 行，同根因）
- **CI gate**：`grep -rE '_RATE_LIMIT_BUCKETS|_extract_ip[[:space:]]*=' deeptutor/ --include='*.py' | grep -v rate_limit.py` 必须为空

**确定性**：SQLite WAL + `BEGIN IMMEDIATE` 在多 worker 共享 sqlite 文件下一致；100 DAU @ <100 QPS 限流写入 P99 < 5ms 够用；超 500 DAU 改 env `RATE_LIMIT_BACKEND=redis` 零代码切换。

---

### 3.4 SR4 — LLM client factory single authority（关 B2 + 修隐藏 ImportError P0）

**根因**：8 处 `AsyncOpenAI()` / `AsyncAnthropic()` / `AsyncAzureOpenAI()` 散落在 `executors.py` / 4 个 provider 文件 / `agentic_pipeline.py`；现有 `services/llm/openai_http_client.py` 是半成品 factory（只在 `DISABLE_SSL_VERIFY=true` 时返回非 None）；OpenAI/Anthropic SDK 默认 timeout 都是 600s。

**额外暴露的隐藏 P0**：`services/llm/providers/anthropic.py:14` 有 `from ..http_client import get_shared_http_client`，但该模块**不存在** → 任何加载 `AnthropicProvider` 的 code path 都会 ImportError。SR4 修复时一并删 dead import + 改用 factory，连带救一个潜在 P0。

**修复路径**：

- **升级现有 `services/llm/openai_http_client.py`** 为真 factory（+40 行，物理保持文件名以减小 diff）：
  ```python
  DEFAULT_LLM_TIMEOUT = httpx.Timeout(
      float(getattr(settings, "llm_timeout_total_s", 60.0)),
      connect=float(getattr(settings, "llm_timeout_connect_s", 10.0)),
  )
  ANTHROPIC_LLM_TIMEOUT = httpx.Timeout(180.0, connect=10.0)  # 长答疑 / reasoning effort high

  def make_openai_client(api_key, base_url=None, *, timeout=None, default_headers=None, max_retries=0, **extra) -> AsyncOpenAI: ...
  def make_azure_openai_client(...): ...
  def make_anthropic_client(api_key, base_url=None, *, timeout=None, default_headers=None) -> AsyncAnthropic: ...
  ```

- **8 处替换点**（每处 ≤3 行 diff）：
  - `services/llm/executors.py:121, 203`
  - `tutorbot/providers/openai_compat_provider.py:103`
  - `tutorbot/providers/anthropic_provider.py:52`
  - `services/llm/providers/open_ai.py:75`
  - `services/llm/providers/anthropic.py:148`（**同时删 dead import**）
  - `agents/chat/agentic_pipeline.py:1490, 1496`

- **CI gate**：`grep -rE 'AsyncOpenAI\(|AsyncAnthropic\(|AsyncAzureOpenAI\(' deeptutor/ --include='*.py' | grep -vE 'openai_http_client\.py|client_factory\.py'` 必须为空（tests/ 下 mock 类按 fixture 名豁免）

**边界（不在 SR4 范围）**：search providers / RAG / aliyun SMS 用裸 `httpx.AsyncClient` 也无 timeout —— 同根因但 SDK 不同，独立成 SR4.1 单独立项；不合并避免 PR 爆炸（≥ 20 处替换）

---

### 3.5 SR5 — Healthcheck path 一致性（关 B3）

**根因**：8 处正确写 `/readyz`，2 处错写 `/`。没有 CI gate 强制三处文件（Dockerfile / docker-compose.yml / docker-compose.ghcr.yml）一致。

**修复路径**：

- **直接字符串改**（≤5 行）：
  - `Dockerfile:414` → `CMD curl -f http://localhost:${BACKEND_PORT:-8001}/readyz || exit 1`
  - `docker-compose.ghcr.yml:81` → `test: ["CMD", "curl", "-fsS", "http://localhost:${BACKEND_PORT:-8001}/readyz"]`

- **CI gate 升级**：扩展现有 `scripts/verify_runtime_assets.py` 校验矩阵（+15 行）：循环检查 3 个文件 healthcheck 段必须含 `/readyz`，禁止只含 `/`

- **不抽 Python 常量**：Dockerfile / yaml 是 build-time，引 Python 常量需镜像 build 时 codegen，得不偿失（违反 less is more）

- **runbook 补丁**：`docs/zh/guide/runtime-observability.md` 加一句 — 阿里云 SLB 7 层探活路径必须配 `/readyz`（≤5 分钟手工，不计入工时）

---

### 3.6 SR6 — Runtime safety primitives（关 C1/C2 + 38 处同根因延迟炸弹）

**根因**：4 个 primitive 缺位：
1. 项目没有 `spawn_task` thin wrapper → 46 处裸 `asyncio.create_task`（仅 8/46 ≈ 17% 手工加了 done_callback；其余 38 处异常静默吞）
2. 项目没有 `BoundedQueue` 类型 → 15 处 `asyncio.Queue` 中 14 处 unbounded（其中 turn_runtime 主 subscriber 队列已有 `contextlib.suppress(QueueFull)` 防御，但 unbounded 下永不触发）
3. `app.state.readiness_checks` 是死状态 dict，不接受 callable → `/readyz` 启动后永远返回 ok，即使 SQLite / Supabase / LLM 全挂
4. `grep '@app.exception_handler' deeptutor/` 0 命中 → 没有"错误响应包装的 single authority"，每个 router 自己捏 detail 字段（detail 字符串/字典格式分歧）

**修复路径**：

- **新文件** `deeptutor/runtime/safety.py`（≤120 行 stdlib only），暴露 4 个 primitive：
  ```python
  DEFAULT_SUBSCRIBER_QUEUE_SIZE = 512

  def spawn_task(coro, *, name=None, on_error=None) -> asyncio.Task: ...
  class BoundedQueue(asyncio.Queue):  # maxsize 必传，提供 safe_put(item, on_full=...)
  def register_readiness_check(name: str, check: Callable[[], Awaitable[None]]) -> None: ...
  async def run_readiness_checks() -> dict[str, str]: ...  # 1.5s timeout 并行
  def install_exception_handlers(app: FastAPI) -> None: ...  # 3 个 envelope: HTTPException / RequestValidationError / Exception；字段 frozen = (detail, request_id, error_code)
  ```

- **8 处迁移点**（before/after 已在 SR6 报告精确给出）：
  - `unified_ws.py:356, 368` create_task → `spawn_task(... , on_error=lambda exc: subscription_tasks.pop(key, None))`
  - `turn_runtime.py:1604, 3180` Queue() → `BoundedQueue(maxsize=DEFAULT_SUBSCRIBER_QUEUE_SIZE)`；同步把 producer 改 `subscriber.queue.safe_put(persisted, on_full=_mark_slow_subscriber)`
  - `main.py:367` 启动期 prewarm task → `spawn_task(..., name="startup.assessment_prewarm")`
  - `main.py` startup 注册 SQLite / LLM key check 到 `register_readiness_check`
  - `main.py` `/readyz` 改成 `await run_readiness_checks()` + 503 on degraded
  - `main.py` `app = FastAPI(...)` 之后调 `install_exception_handlers(app)`

- **3 段 CI gate**（每段 ≤10 行）：
  - Gate A：`asyncio.create_task(` 在 `safety.py` 之外 + 无 `# lint: allow-bare-create-task` 注释 → fail
  - Gate B：`asyncio.Queue(\s*)` 无 maxsize → fail
  - Gate C：`main.py` 必须出现 `install_exception_handlers(app)` 与 `register_readiness_check(`

- **剩余 38 处裸 create_task 渐进迁移**：本 PR 范围只 fix WS subscriber + startup prewarm + 装 wrapper + 装 gate，其余裸 create_task 加 `# lint: allow-bare-create-task` opt-out 注释进 allowlist，每周拆 1 个 router 迁移（避免一次性大改触发 §3 Surgical Changes）

**SR6 上线前 vs W1 分级**（codex R3 修订：4 个 primitive 不一次性打包，避免 mini-framework 风险）：

**SR6-P0（上线前必须做，约 2h）** — 只做最关键 3 件事：
- `runtime/safety.py` 含 `spawn_task` + `install_exception_handlers` + `register_readiness_check` / `run_readiness_checks` 三个 primitive（**不**含 BoundedQueue，先 stub 占位）
- 迁移点收窄到：WS subscriber 转发 (`unified_ws.py:356,368` create_task → spawn_task)；startup `_prewarm_assessment_forms_sync` task；`/readyz` 改主动探测 SQLite + LLM placeholder
- `install_exception_handlers` **只覆盖 HTTP 路径**（FastAPI exception_handler）；**不**接管 WS streaming 错误语义（避免误伤现有 close-code / send_json 协议）
- CI gate：只装 Gate C（`main.py` 必须调 `install_exception_handlers` + `register_readiness_check`）

**SR6-W1（上线后 1 周内补，约 4-6h）** — 处理 BoundedQueue 和 grep gate：
- `BoundedQueue` 落地，**但先做 channel-level 策略矩阵**（codex R3 命中："safe_put + on_full=logger.warning" 会把消息可靠性悄悄降级，不能默认）：
  - 表格化哪些 channel 用 backpressure（producer 必须 wait）vs drop_newest vs drop_oldest vs close subscriber；user-visible token / persisted event channel **绝不 drop**
  - subscriber queue（turn_runtime.py:1604, 3180）用 backpressure + slow-subscriber 标记
  - log channel 可 drop_oldest
  - 先压测：人为制造 slow consumer 10x，验证内存 / 延迟曲线 / 用户可见 event 完整性
- CI gate A/B（禁裸 `create_task` + 禁 `Queue()` 无参）上线，含 38 处现存裸 create_task allowlist 注释加 reason 字段
- 剩余 13 处 unbounded queue 按 channel 矩阵迁移

**SR6-W2+（持续清理）**：
- `loop.create_task` 5 处改 spawn_task
- `asyncio.gather(*tasks, return_exceptions=True)` 18 处补 exception 检查
- readiness 补全：Supabase ping / Langfuse / observability event log 可写 / search provider 配置（含降级标记，不一定 503）

**关键风险（codex R3 直接命中点）**：
- BoundedQueue 默认 `safe_put + on_full=logger.warning` 等于消息悄悄丢；**必须 channel-level 策略矩阵作前提**才能上线，否则不如不装
- 全局 `Exception` handler 若包住 streaming/WS 路径会改变现有 close-code 协议；**v2.1 明确只装 HTTP handler，不动 WS**
- 禁裸 `create_task` grep gate 一上线立刻 fail 46 处；allowlist 注释会泛滥 → CI gate 设 warn-only 1 周观察，再 promote 到 fail

**举一反三发现（同根因延伸，部分推到 W1/W2）**：
- `loop.create_task(...)` 5 处 → W2+
- `asyncio.gather(*tasks, return_exceptions=True)` 18 处 → 单独 issue
- TutorBot bus / event bus / WS log handler 队列 14 处 unbounded → W1 按 channel 矩阵迁
- readiness 缺 5 个 check（SQLite / Supabase / Langfuse / observability log / search provider） → SR6-P0 只做 SQLite + LLM，其余推 W1（降级标记不阻断 ready）

---

### 3.7 PR 拆分与执行顺序（codex R4 修订：拆得更细，PR-α 工时翻倍）

> 6 个 SR 不应该塞 1 个大 PR。codex R4 命中：v2 原 PR-1 把 factory + gate + 3 处迁移 + WS auth 语义变更放一起，失败定位成本高。v2.1 拆 **7 个 PR**，PR-α 工时从 0.5h 真实化为 1 人日。

| PR | 内容 | 风险 | 阻断 | 顺序 |
|---|---|---|---|---|
| **PR-0 Inventory** | `scripts/ci/runtime_route_inventory.py`（**只报告不 fail**）+ `scripts/ci/live_rls_audit.sh` 跑一次得 baseline JSON 入仓库 | 低（只读） | 给后续 PR 拿到真实暴露面 | **第一** |
| **PR-α owner_key 回填** | (1) canonical owner 来源选定（哪张表 lookup）+ 异常样本清单；(2) dry-run script + 抽样输出；(3) 备份/快照；(4) idempotent 回填脚本；(5) 抽样验证脚本；(6) 旧 session smoke test。codex R4 命中：**不是 0.5h 是 1d** | 中（**动生产数据**） | SR1 Phase 0 必须先做 | 第二 |
| **PR-1a SR1 manifest** | `_secure_router.py` + Layer A CI grep gate + Layer B runtime inventory 升级为 fail-on-new + `public_manifest.py`（白名单 + reason）；**不动任何 router 行为** | 低（只加 factory + manifest） | — | 第三 |
| **PR-1b SR1 行为切换** | unified_ws / vision_solver / observability/surface-events 三处实际迁移；含 4401 / 401 / 429 端到端 anon curl + wscat 验证 matrix | 中（**动 router 行为**） | PR-α + PR-1a 完成 | 第四 |
| **PR-2 SR2** | Gate A/B + Gate live RLS audit + A3 migration + B1 rename + 3 环境手工事务脚本 + `_TEMPLATE.md` + `schema_baselines/users+wallets` dump | 中（动 DB） | PR-0 baseline 跑过一次 | 与 PR-1a/1b 并行 |
| **PR-3 SR3 + SR5** | invite_test 接入 route_rate_limit + WS start_turn 限流 + Dockerfile/ghcr 字符串修 + verify_runtime_assets 升级 | 低（纯字符串） | — | 与 PR-1/2 并行 |
| **PR-4 SR4** | `client_factory` 升级 + 8 处替换 + `anthropic.py:14` dead import 修复 + per-provider timeout（Anthropic override 180s） | 中（动 LLM 链路） | LLM 全链路回归（含 stream + retry + observability metadata） | 单独，最后 |
| **PR-5 SR6-P0** | `runtime/safety.py` 含 `spawn_task` + `install_exception_handlers`（**仅 HTTP**） + `register_readiness_check` + `run_readiness_checks`；3 处关键迁移（WS subscriber × 2 + startup prewarm） + `/readyz` 主动探测；CI Gate C only | 中（动 startup + 部分 WS） | startup 回归 + 异常路径回归 | 与 PR-4 并行 |

**v2.1 总工时（codex R5 真实化）**：
- 纯代码收口：PR-0 (1h) + PR-α (1d) + PR-1a (2h) + PR-1b (3h) + PR-2 (1d) + PR-3 (3.5h) + PR-4 (4h) + PR-5 (2h) = **≈ 21h ≈ 2.5 人日**
- 验证 / 数据 / 部署风险预算（codex R5 命中：之前漏算）：
  - SR1 runtime inventory + anon curl/wscat matrix + A5-A11 风险决策：4h
  - SR2 多环境 schema_migrations 修正 + RLS live audit + baseline dump 脱敏：4h
  - SR4 LLM 全链路回归（含 stream / retry / metadata）：4h
  - SR6 异常路径回归（**不**含 BoundedQueue，那个推 W1）：2h
  - G7/G8/G9 验收 + 阿里云 deploy/rollback 实演：4h
  - **合计 = 18h ≈ 2.5 人日**
- **总盘 = 5 人日**（codex R5：v2 的 2.5 人日只算代码，没算"证明线上 authority 真的只有一套"的最贵部分）

---

### 3.8 跨 SR 关切（不要漏掉）

1. **A2 owner_key 回填脚本必须先做**（PR-α，**1 人日**而非 0.5h）：SR1 修完后真遗留无 owner_key 的老 session 会 PermissionError。先回填，后修 SR1。回填脚本须含 canonical owner 来源 + dry-run + 备份/快照 + idempotency + 异常样本清单 + 抽样验证 + 旧 session smoke。
2. **`anthropic.py:14` dead import** 是隐藏 P0：SR4 修复中顺手删除，否则任何 `AnthropicProvider` 加载路径直接 ImportError。
3. **`public.users` / `public.wallets` 不在 git** —— codex R2 修订：**不放进 `supabase/migrations/00000...`**（fresh env 会重复 apply prod 噪声）；改放 `supabase/schema_baselines/20260525_*.sql` 非 migration artifact，配 `README.md` 说明"NOT applied by CLI"；CI gate 通过 `live_rls_audit.sh` 把它们纳入 RLS 检查矩阵。
4. **CI gate 一上线全部 fail 是好事**：SR1 grep Layer A / SR2 gate A+B / SR4 grep / SR6 grep 在修复完成前都会 fail；不要为了"CI 绿"先关 gate；PR 顺序确保 gate 与 fix 同 commit。
5. **SR1 grep ≠ 安全边界**（codex R1 命中）：alias import / wrapper / `include_router` / 测试夹具 / 插件目录拷贝 router 都能绕过 grep；必须叠加 runtime route inventory gate（Layer B）才是真 single-authority。
6. **SR6 BoundedQueue 不进 P0**（codex R3 命中）：BoundedQueue 上线前不装；W1 装时必须先有 channel-level 策略矩阵（user-visible token / persisted event 绝不 drop）。
7. **SR6 exception handler 仅 HTTP**（codex R3 命中）：不接管 WS / streaming 错误语义，避免改现有 close-code 协议。
8. **mobile.py 不算 P0 漏洞**：43 个端点功能上无漏，但模式偏离 default-secure → 列入 SR1 Phase 1 强制迁移。
9. **`chat.py` 已不挂载但代码在**：SR1 Phase 2 `git rm`；本周不动，但要标记防止后续 PR 误 `include_router`。
10. **微信 DevTools project root 是 `yousenwebview/`，主业务验收目标是 `packageDeeptutor/` 分包，不是 `wx_miniprogram/`**（codex R5 命中）：G9 验收时 wx_miniprogram 只做 shadow 对照，主流程必须在 yousenwebview 项目内通过，并单独记录登录证据。

---

## 4. 🟡 P1（上线后 W1 完成，估算合计 ≈ 5 人日）

### 4.A 性能与可观测性 — 2.5 人日

- **P1-O1** `MemberConsoleService._load_unlocked` 内存 cache + mtime invalidation；`services/member_console/service.py:1318` — **4h**
- **P1-O2** `BiService._load_context` 加 60s TTL cache；`services/bi_service.py:924` — **2h**
- **P1-O3** WS 入口生成 `trace_id` + `bind_log_context(user_id, session_id, turn_id)`；`unified_ws.py:313` — **3h**
- **P1-O4** 部署 Prometheus scrape + 飞书 webhook alertmanager；`deployment/observability/prometheus.alerts.example.yml` 接通；`runtime-ops.yml` 加 scrape config — **1d**
- **P1-O5** 生产强制 `DEEPTUTOR_LOG_JSON=1` + 全量 access log（INFO 级 + JSON）；`logging/logger.py:232`，`api/main.py:424` — **1h**
- **P1-O6** `llm_usage_events` 加 `(session_id, created_at)` 与 `(turn_id)` 索引；`services/observability/usage_ledger.py:107` — **0.5h**
- **P1-O7** Aliyun SMS + Search providers 阻塞调用包 `asyncio.to_thread`；`member_console/service.py:2353` + `services/search/providers/*.py` — **0.5d**

### 4.B UX 健壮性 — 1 人日

- **P1-U1** `profile.js` 静默 catch 改为 errorState UI；`wx_miniprogram/pages/profile/profile.js:208,223` — **2h**
- **P1-U2** `chat.js` createConversation 错误按 `code` 分流提示；`wx_miniprogram/pages/chat/chat.js:1853` — **2h**
- **P1-U3** WS 重连识别 4401 → `relaunchLogin`；`wx_miniprogram/utils/ws-stream.js:191` — **3h**
- **P1-U4** start-turn / wxLogin / bindPhone POST 弱网首包补偿；`wx_miniprogram/utils/api.js:301` — **3h**

### 4.C 部署运维 — 1 人日

- **P1-D1** docker-compose 加 `mem_limit / cpus / pids_limit` + logging driver `max-size: 10m max-file: 5` — **2h**
- **P1-D2** pin docker image tag（searxng / valkey / python-3.11.x）+ 统一 Dockerfile HEALTHCHECK 到 `/readyz` — **1h**
- **P1-D3** `scripts/sync_to_aliyun.sh` 收紧 `--delete` 为白名单 + branch 名 sanitize；line 213, 457 — **3h**
- **P1-D4** 文档化 staging→prod 流水线 + rollback 路径（建 `deployment/aliyun/RUNBOOK.md`） — **4h**
- **P1-D5** 文档化 Supabase 数据库备份策略（确认 PITR 计划级别）+ `scripts/deploy_aliyun.sh:20` `--keep` 从 2 提到 5 — **1h**

### 4.D 安全二线 — 0.5 人日

- **P1-S1** CORS 收紧 `allow_methods` / `allow_headers` 显式列；`api/main.py:452` — **1h**
- **P1-S2** mobile chat start-turn 加 IP-level rate limit；`api/routers/mobile.py:2521` — **1h**
- **P1-S3** `unified_ws` 单连接 `start_turn` 次数限流（叠加在 IP 限流之上） — **1h**
- **P1-S4** `.env.bak.preP0.20260519T134855` 验证 git 历史无残留 → 必要时轮换其中所有 key — **1h**

---

## 5. 🟢 P2（上线后 W2-W4 滚动，估算合计 ≈ 6-8 人日）

### 5.A 代码质量与可维护性

- 清理根目录 `tmp_inspect_turn.py` / `tmp_query_hello.py` / `dist/` / `deeptutor.egg-info/`；`tmp/` 整目录入 .gitignore — 0.5h
- 删除 `services/session/turn_runtime.py:1410` 的 `mini_tutor` 兼容映射（违反 §Concept Discipline，1 周日志监控后删） — 0.5h + 监控
- `config/` 收口：plan 配额 + 模型名 + API base + timeout 全部走 `config/` 模块（pydantic-settings） — 1d
- mypy 在 `deeptutor/api/routers/` + `deeptutor/contracts/` 启用 `disallow_untyped_defs` — 1d
- 抽 `deeptutor/utils/normalize.py` + `deeptutor/api/_error_handlers.py` 消重 — 1d
- `services/` 165 处 `except Exception:` 审计收窄到具体类型 — 2d 分批
- `teaching_mode` 职责边界写进 `CONTRACT.md` 或拆出独立 contract — 0.5d

### 5.B 性能二线

- `SQLiteSessionStore` 读写锁拆分；`services/session/sqlite_store.py:792, 1104-1105` — 4h
- LLM streaming `streamed_chunks` 改用长度+采样而非全量内存累积；`services/llm/factory.py:464-700` — 2h
- Search provider 改 `httpx.AsyncClient`；`services/search/providers/*.py` — 1d
- RAG `match_threshold` 调到 0.45（先做小规模 A/B 验证）；`services/rag/pipelines/supabase.py`

### 5.C UX 二线

- 各页面 `onNetworkRestore` 回调补全（profile / history / report）
- `ws-stream.js:386-388` `JSON.parse` 失败补 `log.warn` 而非静默
- `pages/login/login.js:220` `verifyCode` 防重复点击
- `chat.js:921,1701,2086,2126,2301,2329` 6 处静默 catch 补日志
- `idleTimeoutMs / slowResponseMs` 跟随 mode（DEEP/FAST/AUTO）调整

### 5.D 观测二线

- LLM/RAG metrics counter（`llm_call_count{provider,model,outcome}` / `rag_retrieval_hit_count{kb}`） — 3h
- `turn_event_log` 路径从 `tmp/` 搬到持久卷（`data/observability/events`）；`services/observability/turn_event_log.py:14` — 2h
- WS 错误日志补 `user_id / session_id`；`unified_ws.py:533-547` — 1h
- LLM stream metadata `base_url` 走 `sanitize_url`；`services/llm/factory.py:534-545` — 0.5h

---

## 6. 长期债务（不在 Checklist，但必须记录）

以下不是"修完了"的任务，而是 1 个月不动会让迭代速度下降 50% 的结构问题。记录在此，等待对应主线吸收：

1. **6 个 >2000 行业务文件需按域拆分**（→ 没有专门主线，建议在 `生产部署` 主线下开子计划）：
   - `services/member_console/service.py` 5524 行（17 个模块函数 + 巨型 class）
   - `services/session/turn_runtime.py` 4733 行（56 个 def + 4 个 class，turn/stream 单一权威，拆分要保契约）
   - `services/bi_service.py` 3321 行
   - `agents/chat/agentic_pipeline.py` 3040 行
   - `services/rag/pipelines/supabase.py` 2831 行
   - `capabilities/deep_question.py` 2781 行
   - **routers/mobile.py 2546 行是最优先拆分目标**（路由层不该这么厚；2 工日；越晚拆成本翻倍）
2. **services 直接写 SQL 字符串散落多处**（`bi_service.py`、`observability/usage_ledger.py`、`observer_snapshot.py`、`source_compiler/psql.py`）→ 需要 `services/_repo/` 抽象层
3. **`teaching_mode` 概念边界未文档化**：在 `tutorbot/`、`capabilities/`、`runtime/` 三处被消费，违反 AGENTS.md §Concept Discipline 的潜在风险
4. **mypy 严格模式全关 + `Dict[str, Any]` 出现 671 次**：契约靠"读实现"维护，跨人协作必踩

## 7. 相关代码入口

| 维度 | 主要入口文件 |
| --- | --- |
| 安全 (3.A) | `deeptutor/api/routers/vision_solver.py` `unified_ws.py` `observability.py` `invite_test.py` + `supabase/migrations/` + `deeptutor/api/dependencies/auth.py` |
| 部署 (3.B) | `supabase/migrations/` `docker-compose.ghcr.yml` `Dockerfile` `deeptutor/services/llm/executors.py` `deeptutor/tutorbot/providers/` |
| 韧性 (3.C) | `deeptutor/api/main.py` `deeptutor/api/routers/unified_ws.py` `deeptutor/services/session/turn_runtime.py` |
| 性能 (4.A) | `deeptutor/services/member_console/service.py` `bi_service.py` `services/observability/usage_ledger.py` `services/search/providers/` |
| UX (4.B) | `wx_miniprogram/pages/profile/profile.js` `pages/chat/chat.js` `utils/ws-stream.js` `utils/api.js` |
| 部署 (4.C) | `docker-compose*.yml` `Dockerfile` `scripts/sync_to_aliyun.sh` `scripts/deploy_aliyun.sh` `deployment/aliyun/` |

## 8. 审查证据

四份 subagent 详细发现报告（含每一项的 `[文件:行号]` 精确定位）：

- 维度 1+3（错误处理 + 安全）：25 项发现 / Critical 10 / Warning 10 / Suggestion 5
- 维度 2+4（性能 + 观测）：17 项 / Critical 6 / Warning 8 / Suggestion 3
- 维度 5+6（UX + 部署运维）：35 项 / Critical 10 / Warning 19 / Suggestion 6
- 维度 7（代码质量）：22 项 / Critical 7 / Warning 12 / Suggestion 3

合计 99 项发现；本 checklist 取其中 10 个为 P0 阻断、18 个为 P1 W1、其余 71 项归入 P2 或长期债务。

## 9. 计划修改工作流

- 任何新增 P0/P1：直接在本文件追加，**同步把工时计入 §3 / §4 合计**
- P0 项验收后：把验收日期写进对应小节末尾 `**验收日期**: YYYY-MM-DD`
- P0 阻断全部完成 + G1-G6 全绿后：本文件状态从 `Draft v1` 改为 `Done — gates green YYYY-MM-DD`
- 上线后第 7 天：盘点 P1 完成情况，未完成项要么补完要么明确降级到 P2 + 说明原因
- 上线后第 28 天：本文件归档（状态 `Historical`），剩余 P2 项汇入对应主线（生产部署 / Observability / 代码质量改造）
