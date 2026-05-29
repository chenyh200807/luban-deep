# 鲁班内测回访问卷 → BI 互通实施计划

- 状态：`Draft`
- 日期：2026-05-29
- 领域：BI 看板 / 内测回访
- 起因：内测回访问卷（`luban-survey`，写入 Supabase `public.luban_feedback`）当前在 BI/web 代码里**零引用**——数据只入库、无人可视化。要像「内测申请」（`invite_test_applications` → `BiInviteTestTab`）一样接入 BI，让运营能看/筛/导出/跟进。

## 目标

把 `luban_feedback` 表接入 BI 看板，提供：
1. **统计概览**：NPS（promoter/passive/detractor + NPS 分值）、平均满意度、回访意愿率、留联系方式率。
2. **维度分布**：NPS 直方、满意度、最有价值功能、继续意愿、付费意愿、**背景分层**（考试次数 / 距考时间）、状态、来源。
3. **回访池列表**：按时间倒序，支持筛选（状态 / 来源 / 关键词），联系方式按 `is_admin` 脱敏。
4. **跟进**：运营可改 `status`、写 `operator_note`（PATCH）。

## 非目标

- 不改问卷前端（`luban-survey/index.html`）与写入路由（`web/app/api/feedback/responses/route.ts`）——那是上游，本计划只做**读模型 + 看板**。
- 不引入新的聊天 / turn / stream 概念，与 `CONTRACT.md` 无关。
- 不做独立导出服务：导出复用 BI 既有 `request_export_job` 机制（若需要），本期先做看板 + 跟进。

## 单一 Authority

- **读模型唯一入口**：`LubanFeedbackStore`（新），仿 `InviteTestApplicationStore`，连同一个 Supabase（`DB_URL` / `SUPABASE_DB_URL`，CA cert 已配）。
- **BI 服务唯一转发**：`BiService.get_luban_feedback_*`（不让路由直接碰 store）。
- **前端唯一数据层**：`bi-api.ts` 的 `getBiLubanFeedback*`（不让组件直接 fetch）。
- 与写入侧共享同一张表 `public.luban_feedback`，列已在 migration `20260529000100` + `20260529000200` 定义；本计划**不加列**。

## 实施阶段

### Phase 1 — FastAPI 后端读模型（可独立验证）
1. `deeptutor/services/luban_feedback_store.py`（新）
   - `LubanFeedbackStore`：pg 直连读 `luban_feedback`（仿 invite store 的 `_load_database_rows_sync` / psycopg 路径）。
   - `normalize_luban_feedback(row, reveal_contact)`：脱敏 phone/wechat（复用 `_mask_phone` 思路）。
   - `list_responses(days, limit, status, source_page, q, reveal_contact)`。
   - `get_stats(days)`：上述统计/维度聚合（Counter + NPS 分值）。
   - `update_response(id, {status, operator_note})`。
2. `deeptutor/services/bi_service.py`（改）：注入 `_luban_feedback_store` + 转发 `get_luban_feedback_responses/stats/update`。
3. `deeptutor/api/routers/bi.py`（改）：
   - `GET /api/v1/bi/luban-feedback/responses`（`require_bi_admin`，`reveal_contact=auth.is_admin`）
   - `GET /api/v1/bi/luban-feedback/stats`
   - `PATCH /api/v1/bi/luban-feedback/responses/{id}`（idempotency key，仿 invite update）
4. pytest：`tests/services/test_luban_feedback_store.py` —— normalize 脱敏 + stats 聚合（NPS 分值、分层 breakdown、空表）。

**验收**：pytest 绿；部署后 `curl` BI endpoint（带 bi admin token）返回 stats/list；PATCH 改 status 生效。

### Phase 2 — Next.js BI 看板（依赖 Phase 1）
5. `web/lib/bi-api.ts`（改）：类型 `BiLubanFeedbackResponse` / `BiLubanFeedbackStats` + `getBiLubanFeedbackResponses/Stats` + `updateBiLubanFeedbackResponse` + normalize。
6. `web/app/(workspace)/bi/_components/BiLubanFeedbackTab.tsx`（新）：概览卡 + 维度分布 + 回访池列表 + 跟进编辑，仿 `BiInviteTestTab` 结构与 `BiShared` 原子。
7. `web/app/(workspace)/bi/BiPageClient.tsx`（改）：state + useEffect fetch + `activeTab === "luban-feedback"` 渲染。
8. `web/app/(workspace)/bi/_components/BiCommandDeckTabs.tsx`（改）：注册「内测回访」tab。
9. `web/tests/bi-luban-feedback-normalize.test.ts`：bi-api normalize 单测。

**验收**：`node --test` 绿；`npm run build` 绿；部署后浏览器进 BI →「内测回访」Tab 看到真实数据；筛选/跟进可用。

## 相关代码入口（样板）

- 后端读模型样板：`deeptutor/services/invite_test_applications.py`（`InviteTestApplicationStore`）
- BI 服务转发：`deeptutor/services/bi_service.py:3291-3436`（invite-test 段）
- BI 路由：`deeptutor/api/routers/bi.py:301-371`（invite-test 段）+ `require_bi_admin:58`
- 前端数据层：`web/lib/bi-api.ts:340-1680`（invite-test 类型 + getters）
- 前端 Tab：`web/app/(workspace)/bi/_components/BiInviteTestTab.tsx`
- 前端接线：`web/app/(workspace)/bi/BiPageClient.tsx` + `_components/BiCommandDeckTabs.tsx`

## 验收标准（汇总）

- [ ] pytest store/stats 全绿（含空表与脱敏）
- [ ] web `node --test` + `next build` 全绿
- [ ] BI endpoint 经 `require_bi_admin` 鉴权，匿名/非 admin 不泄露联系方式
- [ ] 部署阿里云后，BI「内测回访」Tab 展示真实数据，筛选/跟进可用
- [ ] 与 invite-test 看板风格一致（复用 `BiShared`）
