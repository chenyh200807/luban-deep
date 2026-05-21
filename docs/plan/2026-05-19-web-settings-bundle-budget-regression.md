# `/settings` Bundle Size Budget Regression — Followup

| 字段 | 值 |
| --- | --- |
| 日期 | 2026-05-19 |
| 类型 | Investigation followup (no fix in current PR) |
| 状态 | Fix applied 2026-05-22 in PR #7 — see §9 |
| 主线 | 生产部署（INDEX.md 主线 13） |
| 触发 | PR #1 CI 在修复 Contract Guard yaml deps 后，`Frontend Checks → build:perf` 暴露此长期 regression |
| 影响 | `npm run build:perf` 失败；CI 红，但**与 PR #1 / PR #2 改动无关** |

---

## 1. 实测证据

CI run `26102690575` `Frontend Checks` step：

```
> opentutor-web@1.0.0 perf:check
> node ./scripts/route_budgets.mjs

Route budgets:
OK   /knowledge    292KB / budget 450KB
OK   /memory       252KB / budget 450KB
OK   /notebook     263KB
FAIL /settings     271KB / budget 180KB      ←
OK   /agents/[botId]/chat  428KB
OK   /agents       290KB
…
```

`/settings` 实际 271KB，budget 180KB，**超 50%（+91KB）**。`scripts/route_budgets.mjs` exit 1，整个 Frontend Checks job 失败。

---

## 2. 来源 / Pre-existing 证明

| 维度 | 事实 |
| --- | --- |
| 路由文件 | `web/app/(utility)/settings/page.tsx` |
| 行数 | **1294 行**（单文件超大） |
| Budget 设置 | `web/scripts/route_budgets.mjs` 第 13 行 `"/settings": 180` hardcoded |
| PR #1 / #2 是否动过 settings | ❌ 完全没动（`git log a1e8e412..HEAD -- web/app/(utility)/settings/` 为空） |
| Main 上次改 settings/page.tsx | `2065e86a Absorb upstream DeepTutor runtime capabilities` —— pre-existing main commit，不属本次工作 |
| 为何之前没在 CI 暴露 | `frontend-checks` job `needs: contract-guard`；contract-guard 长期因 yaml deps 缺失 fail → frontend-checks 一直被 skip → perf:check 从未跑过 |

→ Broken window cascade：修第一层（contract guard yaml）→ 暴露第二层（perf regression）。

---

## 3. Root Cause（待真正修复时验证）

候选假设（按 first-principles 排序）：

1. **`web/app/(utility)/settings/page.tsx` 单文件 1294 行** —— 经验上 Next.js client component > 500 行通常意味着多 section 混杂；可能 import 了重 dep（图表、code editor、markdown renderer）一次性加载
2. **`RestrictedSurface` + `useTranslation` + `applyThemePreference` + theme color picker / i18n picker** 等模块可能各自带 sub-tree
3. **Next.js 16 + standalone build** 的 chunk 分组策略与 budget 制定时（可能是 Next.js 15）不同；budget 是历史值，runtime 已经迁移

### 真治本工具链（待 followup PR 内执行）

```bash
cd web && nvm use
ANALYZE=1 npm run build   # 如果项目接了 @next/bundle-analyzer
# 或：
npx next-bundle-analyzer  # 生成 bundle chart
# 查 .next/analyze/*.html 看 /settings 的 chunk graph
```

定位 culprit dep 后：
- `dynamic(() => import('...'), { ssr: false })` 拆 client-only 重 dep
- 抽 sub-section 到独立 page (`/settings/billing`、`/settings/account`)
- 删除 unused imports / dead branches

---

## 4. 不可接受的处置方式（明确列出）

| 反模式 | 为什么不做 |
| --- | --- |
| 把 budget 升到 280 KB 让 CI turn green | budget 的本意就是预防 bundle 膨胀；升 budget = 接受 regression 永远存在 |
| `npm run build:perf` 加 `\|\| true` 让命令永不 fail | 把保护机制 disable，**broken window 的最坏形态** |
| 注释掉 perf:check step | 同上 |
| 在 settings/page.tsx 加 `/* eslint-disable */` / 注释隐藏 bundle 真相 | 不解决问题 |

---

## 5. 可接受的短期 unblock

PR #1 / #2 不动 settings、不动 budget、不动 perf check。**force merge with broken Frontend Checks**：

- main 已经 pre-existing CI red，本 PR 不引入任何新 regression
- contract-guard CI 已经被本 PR 修绿
- 后续 PR 把 `/settings` perf 修绿后，main CI 自然干净

GitHub mergeable=true，UI 有 "Merge anyway" 按钮，用户已授权 force merge。

---

## 6. 真治本 followup PR 模板

未来某个 PR 执行：

1. **诊断阶段**（30-60min）
   ```bash
   cd web && nvm use
   ANALYZE=1 npm run build  # bundle analyzer
   # 或读 .next/server/app/(utility)/settings/page_client-reference-manifest.js 看 chunk 列表
   ```
2. **拆 culprit**（按 §3 第一性原理工具链）
3. **本地验证**
   ```bash
   npm run build:perf  # 期望 OK /settings <180KB
   ```
4. **commit message 草稿**
   ```
   perf(web/settings): split /settings page to restore bundle budget

   /settings was 271KB, budget 180KB. Root cause: ... [bundle analyzer
   findings]. Split <heavy section> into dynamic() chunks. Now N KB.
   ```
5. **PR 描述包含**: bundle-analyzer screenshot before/after + `npm run build:perf` output before/after

---

## 7. 不确定性

| # | 项 | 应对 |
| --- | --- | --- |
| U1 | 是否还有其他路由也超 budget（CI 只报了第一个 FAIL，可能 short-circuit） | followup PR 跑 build:perf 看完整 fail list |
| U2 | budget 180KB 当时怎么定的 / 是否仍合理 | git blame `route_budgets.mjs:13` 看原 commit context；如果 budget 当时就过紧，可能配合本次拆分一起重设（但要 PR 描述里明确论证） |
| U3 | Next.js 16 vs Next.js 15 chunk 分组变化导致 budget 不再公平 | bundle analyzer 输出 + Next.js release notes 对照 |

---

## 8. 与 PR #1 / PR #2 的关系

- **PR #1 (`fix(wechat-harness): restore visible_sections single-authority contract` + `chore(web): pin Node 22 LTS` + `ci: install PyYAML`)**：力本 PR 暴露 regression，但不修。本 followup doc 是 PR #1 内的「记录」 commit。
- **PR #2 (`chore: page gate + grading audit + eslint diagnosis`)**：与 settings 无关。
- **本 followup doc**：可挂在 PR #1 的最后一个 commit，作为「broken window 已记录」证据；真修在独立 PR。

---

## 9. 2026-05-22 修复落地（PR #7, codex/gstack-qa-web-fix-203011）

### 诊断（chunk-level 实测）

`web/app/(utility)/settings/page_client-reference-manifest.js` 的 entryJSFiles 列出 6 个 chunk：

| chunk | 大小 | 内容指纹 |
| --- | --- | --- |
| `0hglpt8ou7zsq.js` | 5.9 KB | utility-shell shared bootstrap |
| `031y~__trq_8j.js` | 81.8 KB | UnifiedChatContext / Notebook 字符串（root layout 拉入的客户端 context tree） |
| `06ywjv60mmrt0.js` | 49.8 KB | i18next + locize（`I18nClientBridge`） |
| `0xe7gt3~du.d0.js` | 53.4 KB | utility-shell shared |
| `05_y6hljq8t59.js` | 48.0 KB | lucide-react + `useTranslation`（UtilitySidebar 拉入） |
| `0kc0bo8keyv_8.js` | 4.5 KB | next/dynamic stub |

**utility-shell baseline = 5.9 + 81.8 + 49.8 + 53.4 + 48 = 238.9 KB**，与 settings 内容无关。同 layout 下：

| route | 实测 KB | 旧 budget |
| --- | --- | --- |
| /memory | 252 | 450 |
| /knowledge | 292 | 450 |
| /notebook | 263 | (无) |
| /settings (拆分前) | 271 | 180 |
| /settings (拆分后) | 243 | 180 → **250** |

→ `180` budget 是历史值，**与 utility shell baseline 不一致**：在旧 measure 算法下即使 settings page 0 行代码也至少 239KB。两条独立路径都能让数字达标：(a) 让 measure 算法剔除 layout chunks（不再把 shell 算到 page budget），(b) 把 page 本身的 console 拆出 entry chunk。这次 PR #7 两者都做了，且互相加成。

### 已实施修复

1. **Layout-aware measure**（`web/scripts/route_budgets.mjs`，commit `5cd9caca`，由协作者推入）
   - `entryJSFiles` 收到的 `entry/<route>/page` chunk 列表中，把 `entry/<route>/layout` 和 `entry/app/layout` 的 chunks 减去（去重并 set-diff），只测真正归属 page 的 chunk。
   - 修正了 budget 制定时的 measure mental model：budget 应反映 page 自身代码，而非 shell baseline。

2. **Surgical dynamic split**（`web/app/(utility)/settings/page.tsx` + 新 `SettingsPageContent.tsx`，本次 PR 新增）
   - page entry 现在只 import `dynamic`, `RestrictedSurface`, `requiresWebAuth`。
   - 1294 行 client 控制台搬到 `SettingsPageContent.tsx`，通过 `dynamic(() => import('./SettingsPageContent'), { ssr: false })` 加载。
   - anon 用户走 `RestrictedSurface`，重 console 永不下载；登录用户首次访问异步加载 console chunk。
   - 这是真正的运行时收益（anon path 节省下载），不依赖 measure 算法。

3. **Budget 保持不变**：`"/settings": 180` 维持原值。
   - measure 修正 + dynamic split 之后，settings page entry = **5 KB**，远低于 180KB budget，留充足 monitor margin。
   - 不调 budget = 不让 PR 显得"为绿而绿"。

### 联合验证

`npm run build && node ./scripts/route_budgets.mjs` 在 PR #7 HEAD 上：

```
OK   /knowledge     53KB / budget 450KB
OK   /memory        13KB / budget 450KB
OK   /notebook      25KB
OK   /settings       5KB / budget 180KB
OK   root-shell    191KB / budget 220KB
```

### 未做（已评估，留作下一步）

| 选项 | 收益估计 | 为什么这次不做 |
| --- | --- | --- |
| 把 /settings 移出 (utility) group，绕过 sidebar | UX 改进 | 与 budget 无关，不在本 PR scope |
| 重构 UnifiedChatContext / NotebookImportPanel 拆分 | -40~80 KB on shared shell | 跨 4 个 utility route 的 shell 优化；独立 PR |
| Tree-shake lucide-react / 改用 SVG sprite | -20~30 KB | 涉及全站 icon 体系，独立 PR |

### Acceptance

- `npm run perf:check` 本地：PASS（settings 5 KB / budget 180 KB）。
- /memory / /knowledge / /notebook 测量值也大幅缩小（layout 减除后），但 budget 不动，仅作为更准的 monitor 基线。
- anon 用户首屏不下载控制台（dynamic split 主目的）。
