# BI v2 阿里云部署 + 手动测试 checklist

适用：PR #19 (BI v2 enforced invariant) 合并 main 后，从本地 → 阿里云 `/root/deeptutor` 同步 → 真用户 Stage 1 灰度演练。

关联：
- 计划：`docs/plan/2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md`
- 灰度 runbook：`docs/zh/bi/bi-backoffice-v2-rollout-runbook.md`
- 项目宪法：`AGENTS.md` §3.7 Aliyun SSH Write Boundary

> **硬约束**：阿里云写边界仅限 `/root/deeptutor`（AGENTS §3.7）。任何远端部署脚本必须先证明写入目标在该路径内。

---

## 1. 合并 main 前最后检查（本地）

执行顺序必须如下，**任何一步失败即停止**：

```bash
# 1.1 本地分支同步 main，无冲突
git fetch origin main
git rev-list --count HEAD..origin/main   # 必须 == 0；非 0 则先 rebase

# 1.2 全套测试通过
python -m pytest tests/api/test_member_router_auth.py \
                 tests/services/member_console/test_service.py \
                 tests/web/test_bi_member_admin_surface.py \
                 tests/services/test_bi_metrics.py \
                 tests/services/test_bi_service_limits.py \
                 tests/api/test_bi_router.py \
                 tests/api/test_bi_write_endpoints_registry.py \
                 tests/web/test_bi_v2_raw_fetch_guard.py \
                 tests/web/test_bi_v2_mock_boundary.py \
                 tests/web/test_bi_v2_banner_fetch_coherence.py -q
# 期望：162 passed

# 1.3 codegen drift 检查（最后一道防线）
python -m scripts.gen_bi_metrics_ts --check
python -m scripts.gen_bi_write_endpoints_ts --check

# 1.4 前端构建 + mock boundary
cd web
npx tsc --noEmit -p tsconfig.json       # 0 error
npx eslint .                            # 0 error
node ./node_modules/next/dist/bin/next build
node ./scripts/route_budgets.mjs        # 全 OK
node ./scripts/check_mock_boundary.mjs  # OK · production bundle does not contain BI v2 mock fixtures
```

**通过后**：在 GitHub 上 review PR #19，Squash Merge 到 main。

---

## 2. 阿里云部署步骤

### 2.1 SSH 进入阿里云

```bash
ssh root@<aliyun-host>
cd /root/deeptutor   # 唯一可写边界（AGENTS §3.7）
pwd                  # 必须显示 /root/deeptutor，否则 STOP
```

### 2.2 拉取最新代码

```bash
git status           # 必须 clean，否则 stash 后再拉
git fetch origin main
git pull --ff-only origin main
git log --oneline -3 # 确认 BI v2 合入 commit 在 HEAD
```

### 2.3 后端环境

```bash
# 假设 venv 在 .venv
source .venv/bin/activate
pip install -r requirements.txt   # 无新依赖；以防 lock 漂移
```

### 2.4 重启 backend（带 Stage 1 flag）

**Stage 1 仅开 SHELL + OVERVIEW**，其余 4 个 panel flag 保持关闭：

```bash
# 写到 systemd unit 或 .env，示例：
export BI_BACKOFFICE_V2_SHELL_ENABLED=1
export BI_OVERVIEW_V2_ENABLED=1
# 其余明确关：
unset BI_CRM_V2_ENABLED BI_COMMERCE_V2_ENABLED BI_FEEDBACK_V2_ENABLED BI_SYSTEM_OPS_V2_ENABLED
unset BI_VNEXT_PROTOTYPE_ENABLED

# 重启 uvicorn / gunicorn（按现有 runbook）
systemctl restart deeptutor-api   # 或具体的 service name
```

### 2.5 前端构建

```bash
cd /root/deeptutor/web
npm ci                                                 # 严格 lockfile
NODE_ENV=production node ./node_modules/next/dist/bin/next build
# 阿里云上 NODE_ENV 必须明确为 production，否则 mock 数据进 bundle
node ./scripts/check_mock_boundary.mjs                 # 必须 OK
node ./scripts/route_budgets.mjs                       # 必须全 OK
```

### 2.6 健康检查

```bash
curl -s -o /dev/null -w "HTTP=%{http_code}\n" http://localhost:3001/bi   # 200
curl -s -o /dev/null -w "HTTP=%{http_code}\n" http://localhost:3001/api/v1/health   # 200
```

---

## 3. 手动测试 checklist（你执行）

打开浏览器访问阿里云 BI 后台。每条结果记在 `docs/zh/bi/bi-v2-stage1-debrief-<date>.md`。

### 3.1 RequireBiAdmin boundary（核心安全约束）

- [ ] **未登录访问 `/bi`** → 显示「BI 后台需 admin 登录」红色提示页，**不渲染任何 panel**
- [ ] **以非 admin 登录** → 显示「当前账号权限不足」黄色提示
- [ ] **admin 登录** → 看到 BI v2 shell（顶部「BI v2 · 会员经营后台」，左侧 5 主区导航）

### 3.2 经营总览（Stage 1 唯一接真数据的 panel）

- [ ] 4 个 KPI 卡片渲染：今日活跃会员 / 近 24h 充值 / 学习成功率 / 近 24h LLM 成本
- [ ] **Hover 任一 KPI**，浏览器原生 title 显示 7 项：metric_id / 口径 / authority / owner / 可信等级 / 更新频率 / 降级说明
- [ ] 数据可信徽章颜色 + 字母（A/B/C/D 不是仅颜色）— 如「C 级」字样
- [ ] 趋势图 24 柱渲染
- [ ] 今日行动队列含 severity 标签 + owner

### 3.3 数据源 banner（Round 4 S5 / R5 banner-fetch coherence）

- [ ] 如果后端 `/api/v1/bi/overview` 真返回数据 → 绿色「实时数据」banner + generated_at 时间
- [ ] 如果后端返回 500 / 401 → 红色「overview API 不可用，已回退到 mock」（dev mock 不在 production 应空，需在 BI v2 进 panel 显示骨架）
- [ ] **不允许出现**：绿色「已开启 · audit 接 ...」 banner 但页面无 fetch 请求（这是 banner 自我欺骗的回归）

### 3.4 其他 4 个 panel（flag 关时）

切到 `/bi?tab=member-ops` / `commerce` / `feedback` / `ops`：

- [ ] banner 文案是「flag 已开启 · 数据源待 ... 接入」**或** flag 关闭时的「BI_X_V2_ENABLED 未开启 · 当前为 Batch X 静态原型」— **不能**写「已接真实 service」
- [ ] 生产构建下 mock 数据应为空数组 → panel 显示空状态而非伪造数据（验证 Round 4 S4 + Round 5 B3）

### 3.5 对话回顾审计契约（唯一真写路径）

`/bi?tab=member-ops` → 「打开 360」→ 「查看会员对话回顾」：

- [ ] 红色"未登录"banner **不**出现（你已是 admin）
- [ ] 6 个 reason radio：客服投诉 / 运营跟进 / 教研复核 / 工程排障 / 财务核对 / 其他
- [ ] 「查看全文」按钮初始 disabled
- [ ] 选「客服投诉」→ 按钮变 enabled
- [ ] **生产 build 下 MOCK_SESSIONS = []** → 显示新加的空状态提示「会员对话列表待接入 Batch 5」（Round 5 B3）
- [ ] 如果有真会话：点「查看全文」→ Network 面板看到 `POST /api/v1/member/.../view-audit?reason=complaint` 请求带 `X-Idempotency-Key` 头
- [ ] 后端真写入 audit_log（在 ops audit panel 看到，或直接 SSH 看 JSON 文件）

### 3.6 idempotency 真去重（Round 5 B1+B2）

通过 curl 或 Postman 重复发同一 idempotency-key：

```bash
# 第一次
curl -X POST -H "Authorization: Bearer <admin-token>" \
     -H "X-Idempotency-Key: test-uuid-001" \
     "http://localhost:3001/api/v1/member/<user_id>/conversations/<session_id>/view-audit"

# 第二次同 key
curl -X POST -H "Authorization: Bearer <admin-token>" \
     -H "X-Idempotency-Key: test-uuid-001" \
     "http://localhost:3001/api/v1/member/<user_id>/conversations/<session_id>/view-audit"
```

- [ ] 第一次返回 `audit_id` + 无 `deduped` 字段
- [ ] 第二次返回**同 audit_id** + `"deduped": true`
- [ ] audit_log 只有 **1 条**条目（不是 2 条）

### 3.7 X-Idempotency-Key 格式守护（Round 5 M1）

- [ ] 不带 header → 400 + detail 含 "X-Idempotency-Key header is required"
- [ ] header = "with:colon" → 400 + detail 含 "≤ 128 chars of [a-zA-Z0-9_-]"
- [ ] header = "x" × 129 → 400
- [ ] header = "has spaces" → 400

### 3.8 X-Idempotency-Key operator binding（Round 5 B2）

用两个不同 admin 账号发同一 key：

- [ ] Admin A 发 key=foo → audit_log 加 1 条 actor=A
- [ ] Admin B 发 key=foo → audit_log 加 1 条 actor=B（**不**被 dedup）
- [ ] 此时 audit_log 共 2 条

### 3.9 跨 viewport（Round 3 §7.6）

Chrome DevTools → device toolbar：

- [ ] `1440 × 900`（桌面）→ 5 主区 sidebar + KPI 4 列 + 行动队列右侧
- [ ] `1024 × 768`（iPad 横屏）→ sidebar 仍在 + 内容单列
- [ ] `375 × 812`（移动）→ 汉堡菜单 + sidebar overlay + 单列 + 无横向滚动
- [ ] 全局搜索框中文输入 IME composition 期间**不**触发查询（输入 "你好" 拼音时按 Enter 不发请求）

### 3.10 Error Boundary（Round 5 B4）

在 Chrome DevTools Console 强制注入错误：

```js
// 在 BiV2Surface 上下文中
throw new Error("synthetic test error")
```

- [ ] 页面**不**变白
- [ ] 显示新加的红色「BI 后台暂时不可用」error 页 + 「重试」按钮 + 「返回首页」链接
- [ ] 点「重试」→ 页面恢复

### 3.11 1 秒回滚（runbook §3）

SSH 到阿里云：

```bash
# 关闭顶层 flag
unset BI_BACKOFFICE_V2_SHELL_ENABLED
# 或在 .env / systemd 改为 =0

systemctl restart deeptutor-api
```

- [ ] 浏览器 hard reload `/bi` → 看到旧 `BiPageClient`（老板工作台 / 会员运营 / 上线面板 / 内测申请 / 学员 360 / 经营审计 6 tab）
- [ ] 旧 admin 登录可用
- [ ] 无 console error

---

## 4. 演练后必交付物

合并 + 部署 + 演练完成后，写 `docs/zh/bi/bi-v2-stage1-debrief-<YYYY-MM-DD>.md`，内容：

1. **演练人**：你 + 谁
2. **环境**：阿里云 `<host>` + 构建 commit SHA
3. **3.1-3.11 checklist 结果**：每条 ✅ / ❌ / N/A
4. **观察笔记**：哪些步骤"看不懂 / 数据不够 / 反直觉"（不是 bug，是 product feedback）
5. **决策**：是否进入 Stage 2 RFC？哪一个 panel 接 backend 优先级最高？
6. **回滚演练**：用过吗？多久切换完？

---

## 5. 故障应急

| 症状 | 紧急动作 |
|---|---|
| `/bi` 白屏 | error.tsx 应该接住；若失败，立刻关 BI_BACKOFFICE_V2_SHELL_ENABLED |
| KPI 全部 N/A 或 mock 字样 | 检查后端 `/api/v1/bi/overview` 健康 + admin token 配置 |
| 对话回顾全文展开但 audit_log 没增 | 立刻关 BI_BACKOFFICE_V2_SHELL_ENABLED；检查 `X-Idempotency-Key` 头是否真到后端（看 nginx log） |
| `audit_idempotency_keys` JSON 文件突然变大几 MB | 攻击信号？检查 audit_log 单 actor 是否有异常重复 |
| ops/feedback/commerce panel 显示业务数据 | **flag 应该是关的**；检查 BI_*_V2_ENABLED env，关掉非 OVERVIEW |

---

## 6. 我（Claude）可以协助

- 把 3.3 / 3.5 / 3.6 / 3.7 / 3.8 改成自动化脚本（如有需要）
- 若 manual test 发现新 regression，按 root cause 不打补丁的方式分析 + 修
- 写阿里云上的 systemd unit 模板 / nginx conf 片段
