# BI 会员经营后台 v2 — 灰度与回滚 runbook

关联：

> **Round 2 复审修复（2026-05-23）**：CRITICAL ConversationReviewDrawer actor 残留、HIGH BiDataTable cursor 依赖稳定化、HIGH /bi-vnext 路由灰度前需 `BI_VNEXT_PROTOTYPE_ENABLED` 门控（关闭返回 404）、MEDIUM KPI tooltip 含 refresh_cadence + degraded_note、MEDIUM view-audit 传 reason（query + body）。MOCK_MEMBERS 扩到 120 行让 BiDataTable pageSize=50 真实生效。
>
> **Round 4 enforced-invariant 修复（2026-05-23）**：从 Round 3 的"劝告型工具"升级为机械可验证 invariant。
> - **S1 后端 idempotency 真去重**：`routers/member.py` view-audit 强制读 `X-Idempotency-Key`（缺 / 空 header → 400）；`MemberConsoleService.record_conversation_view` 接 `idempotency_key`，在 `audit_idempotency_keys` JSON 索引中按 `f"{action}:{key}"` 查重；同 key 重复 POST 返回首次 audit_id + `deduped: true`。Round 3 placebo 消除。
> - **S2 WRITE_ENDPOINTS registry + codegen**：`deeptutor/contracts/bi_v2_write_endpoints.py` 单一权威；`scripts/gen_bi_write_endpoints_ts.py` 生成 `web/lib/bi-v2-write-endpoints.generated.ts`；`useAuditedAction` 的 `endpoint.key` 类型收窄为 `BiV2WriteEndpointKey`（未注册即编译失败）；`ConversationReviewDrawer` 改为 `key + params + query`，不再手工拼 URL；pytest `test_write_endpoints_ts_in_sync` + `test_write_endpoints_have_router_enforcement` + `test_idempotency_endpoint_has_backend_dedup_test` 三重 drift guard。
> - **S3 raw fetch guard**：`tests/web/test_bi_v2_raw_fetch_guard.py` 守护 `bi/_v2/**` 内除 `useAuditedAction.ts` 外**禁止** `fetch(` / `apiUrl(` / `withAdminAuthorization(`；`window.prompt`/`window.confirm` 在 audited 路径上 fail。Feedback triage / member ops action / export request 均通过 `useAuditedAction` 进入注册 endpoint。
> - **S4 mock-boundary 真守护 (M-B)**：所有 MOCK_* / ANOMALIES / FEEDBACK_ITEMS / AUDIT_ENTRIES / EXPORT_JOBS / ORDERS / LEDGER / PACKAGES / OPS_TILES / MOCK_BUNDLE / MOCK_SESSIONS 用 `process.env.NODE_ENV === 'production' ? [] : [...]` 包裹（Next.js + Terser DCE）；`web/scripts/check_mock_boundary.mjs` 在 `next build` 后 grep `.next/static/chunks/*.js`，含 mock 独有字符串即 fail；`npm run check:mock-boundary` 已加入 `package.json`；pytest 源级守护 + build artifact 双层。
> - **S5 banner-fetch 共存断言**：`tests/web/test_bi_v2_banner_fetch_coherence.py` 强制 panel banner 不能声称 `已写入 audit log` / `audit 接 member_console` 等真实接入语言，除非同文件存在 `useAuditedAction` / `@/lib/bi-api` / `@/lib/member-api` 真实证据；OpsPanel / CommercePanel / FeedbackPanel / MemberOpsPanel 的真实接入口径由源码证据和 e2e smoke 共同守护。
>
> **从 advisory tool 到 enforced invariant**：Round 3 加了工具但没加"使用工具的强制约束"。Round 4 把每个 invariant 落到一条机械可验证的 check：源码 grep（pytest）+ 类型收窄（tsc）+ 后端 header 校验（fastapi）+ build artifact grep（next + node）+ codegen drift（pytest）。删除 `useAuditedAction` → tsc fail；新写路径不入 registry → pytest fail；mock 进生产 bundle → check:mock-boundary fail；banner 自吹但无 fetch → pytest fail；后端忘读 X-Idempotency-Key → router pytest fail。
>
> **Round 3 架构层修复（2026-05-23）**：从补丁累积转 first principles，按三大原则系统性收口。
> - **A 删除**：去掉 `BiV2PlaceholderPanel` / 整个 `bi-vnext/` 历史层 / `bi_vnext_smoke.mjs` / `BiV2MemberOpsPanel` 本地伪 audit (`recordAudit` + `setAuditLog`)。less is more 第一步。
> - **B 单一审计写入门**：新建 `useAuditedAction` hook (`web/app/(workspace)/bi/_v2/useAuditedAction.ts`) — 自动注入 `X-Idempotency-Key` (crypto.randomUUID) + `Authorization` (via `withAdminAuthorization`)；状态机 idle/writing/ok/denied；唯一 fetch 出口。删除前端自拼 audit 字符串，UI 不再伪造审计真相。
> - **C `<RequireBiAdmin>` boundary 横切收口**：BiV2Surface 外包一层认证 gate；未登录跳登录提示，**不渲染任何 panel**；已登录非 admin 显示权限不足；只有认证 admin 才能看到 BiAppShell。删除每个 panel 内重复的 `identity.authenticated` 判断。
> - **D 单一权威 metric registry**：backend `bi_metrics.py` 加 `refresh_cadence` + `degraded_note` + `label_aliases` + 5 条 overview-only metric；新建 `scripts/gen_bi_metrics_ts.py` codegen 脚本生成 `web/lib/bi-v2-metric-registry.generated.ts`；删除手写副本；pytest `test_metric_registry_ts_in_sync` 守护漂移。
> - **E 契约测试**：新建 `web/scripts/bi_v2_contract_smoke.mjs` 用 `page.route` 拦截：(1) view-audit POST 必须带 X-Idempotency-Key + Authorization + reason= query；(2) BI_OVERVIEW_V2_ENABLED=true 时必须发出 `/api/v1/bi/overview` GET。pytest 加 4 条 v2 source-level contract guard。
> - **G 后端 reason 接收**：`record_conversation_view` 接收 reason 参数 + 5 项白名单 + `other:` 自由文本 ≥ 4 字符；写入 audit_log 的 reason 字段 + audit_payload；router 同时支持 query 和 JSON body。reason 现在真正穿透到 audit_log。
> - **H 全局搜索收口**：BiTopBar 支持"手机号 / user_id / 订单号"；手机号 / user_id 命中会员运营并打开学员 360，订单 / ledger 类查询路由到商品账务只读模型过滤，不新建订单 authority。
> - **F (mock guard) 标 P1 backlog**：4 个非 overview panel 在生产构建中应展示 skeleton 而非 mock。Stage 1 仅放 OVERVIEW 不阻塞，留待 Stage 2 前处理。


- 计划：`docs/plan/2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md`
- Authority audit：`docs/zh/bi/bi-backoffice-v2-batch0-authority-audit.md`

## 1. 6 个 Feature Flag

集中在 `web/lib/bi-feature-flags.ts`，支持 `NEXT_PUBLIC_<name>` 与 `<name>` 两种环境变量。

| Flag | 控制范围 | Batch 关联 |
| --- | --- | --- |
| `BI_BACKOFFICE_V2_SHELL_ENABLED` | `/bi` 是否渲染新 BiAppShell（关闭则旧 BiPageClient） | Batch 1 |
| `BI_OVERVIEW_V2_ENABLED` | 经营总览是否调真实 `/api/v1/bi/overview` + `active-trend` + `anomalies` | Batch 3 |
| `BI_CRM_V2_ENABLED` | 会员运营 CRM panel 显示真实数据接入 banner（P0 静态） | Batch 2 |
| `BI_COMMERCE_V2_ENABLED` | 商品账务 panel 显示真实数据接入 banner（P0 只读） | Batch 4 |
| `BI_FEEDBACK_V2_ENABLED` | 反馈中心三源（AI 反馈 / 内测 / 备注）接入 audit 写入 | Batch 5 |
| `BI_SYSTEM_OPS_V2_ENABLED` | 系统运维 6 tile + 操作审计 + 导出任务 | Batch 6 |
| `BI_VNEXT_PROTOTYPE_ENABLED` | `/bi-vnext` Batch 0 静态原型路由是否可访问（默认关闭，关闭时 notFound()） | Batch 0 + Round 2 门控 |

> 子模块 flag 仅切换 banner / 数据源。`BI_BACKOFFICE_V2_SHELL_ENABLED` 是顶层主开关，关闭即整个 v2 不渲染。

## 2. 推荐灰度顺序

1. 内部 dogfood：6 个 flag 全开，但 admin 入口仅限 ops 团队。
2. **Stage 1**：仅开 `BI_BACKOFFICE_V2_SHELL_ENABLED + BI_OVERVIEW_V2_ENABLED`，给老板/创始人首屏 24h。
3. **Stage 2**：再开 `BI_CRM_V2_ENABLED + BI_COMMERCE_V2_ENABLED`，给运营 / 财务 48h。
4. **Stage 3**：开 `BI_FEEDBACK_V2_ENABLED`，给质量 / 增长 48h。
5. **Stage 4**：开 `BI_SYSTEM_OPS_V2_ENABLED`，给 platform / ops 完整 release gate 演练。
6. 连续 7 天无 P0 / P1 事故 + 关键指标 p95 达标 + 运营 / 客服 / 财务 / 质量各完成一次真实任务 → 下线旧 BiPageClient。

## 3. 1 秒回滚步骤

任一阶段出错：

```bash
# 关掉顶层 flag 立刻回到旧 /bi
unset BI_BACKOFFICE_V2_SHELL_ENABLED
# 或显式置 0
export BI_BACKOFFICE_V2_SHELL_ENABLED=0
# 重启 web 进程 / 重新部署对应环境
```

子模块单独回滚同理：关闭 `BI_<subset>_V2_ENABLED` 后该 panel 退回静态 banner，shell 仍可用。

## 4. QA Gate 清单 (Batch 7)

后端：

```bash
pytest tests/web/test_bi_member_admin_surface.py -q       # 18 passed
pytest tests/api/test_bi_router.py -q                     # 15 passed
pytest tests/services/test_bi_metrics.py -q               # 13 passed
pytest tests/services/test_bi_service_limits.py -q        # 12 passed
# 合计：58 passed
```

前端：

```bash
cd web
npx eslint .                                              # 0 error, warnings 与现有风格一致
node ./node_modules/next/dist/bin/next build              # build OK，含 /bi 与 /bi-vnext
node ./scripts/route_budgets.mjs                          # /bi 218KB，root-shell 191KB / 220KB budget
```

Playwright 视觉 smoke（要求 dev server 上 BI_BACKOFFICE_V2_SHELL_ENABLED=1）：

```bash
# 跨 viewport (1440x900 / 1024x768 / 375x812) × 6 路径
node scripts/bi_v2_release_gate.mjs

# CRM 交互（学员 360 抽屉 + 对话回顾原因审计 + Esc 关闭）
node scripts/bi_v2_crm_interaction_smoke.mjs

# Batch 0 静态原型
node scripts/bi_vnext_smoke.mjs
```

回滚 smoke（dev server 上 flag 全关）：

```bash
node scripts/bi_v2_rollback_smoke.mjs
```

## 5. 浏览器视觉验收点

- `1440x900`：高密度，会员表 7 列默认，KPI 4 列等宽。
- `1024x768`：侧边导航保留，主区单列堆叠。
- `375x812`：导航折叠为汉堡，KPI/表格单列；顶部全局搜索常驻。
- 无横向滚动、无文字溢出、无卡片套卡片。
- 主要动作键盘可达；危险动作（撤销 / 补点 / 异常处理）禁用提示。
- 对话全文默认折叠；查看必须选原因并写 audit。

## 6. 数据可信度提示

- KPI hover 显示 `metric_id` + 口径 + authority + owner + A/B/C/D 可信等级。
- 注册表镜像：`web/lib/bi-v2-metric-registry.ts` 对齐 `deeptutor/services/bi_metrics.py`。
- C/D 级指标只用于趋势 / 风险提示，不作为财务结算 / 自动动作依据。
- overview API 不允许走 `get_member_360()` 重型路径。

## 7. 剩余风险与缺口

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| `/bi/standup` 子路由当前 404（计划期望存在） | release_gate.mjs 标 `expectStatus: 404` 显式跟踪 | 旧 BiPageClient 内 tab 仍可用；P1 决定是否独立路由 |
| BI_OVERVIEW_V2_ENABLED dev 模式 fetch 500 | UI 红色 fallback banner，mock 数据继续渲染（KPI 卡片仍展示但 banner 标注源） | 真实部署需 admin token + BI_API_TOKEN，详见 `web/lib/bi-admin-auth.ts` |
| `packages` 表未拆出 | P0 套餐编辑禁用 | P1 backend schema + 历史快照实装 |
| 钱包 etag / undo_token 未实装 | 撤销 / 补点 / 异常处理动作禁用 | P1 wallet authority 添加 etag + undo runbook |
| 教研 / 系统质量反馈未接入 | 反馈中心 P0 仅 3 源 | P1 扩展 FeedbackService 来源 |
| EXPLAIN ANALYZE 5w 会员压测未跑 | `BiDataTable` 已实装 pageSize=50 + IntersectionObserver 触发 cursor 加载 + 大集合警告（≥ 1000 行），但真实 list_members API 性能未验证 | Batch 2.5 接真实 API 时跑 EXPLAIN ANALYZE + 启用 server-side cursor |
| BI Admin session 必须存在才能查看对话全文 | dev / 无登录环境，ConversationReviewDrawer 红色 banner + 全文按钮禁用；audit 通过 `POST /api/v1/member/<user_id>/conversations/<session_id>/view-audit` 真实写入 | 真实灰度需运营登录 BI Admin 后操作 |
| 低风险写动作已接 audited endpoint，但危险动作仍关闭 | 标记已联系 / 加备注 / 加入跟进队列 / AI feedback triage / export request 已有幂等审计；撤销、补点、修账仍禁用 | P1 补 etag/version、undo_token 和二次确认后再开放危险动作 |

## 8. 真实交付清单（Batch 0-7）

详见 `docs/plan/2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md` 与对应章节。
