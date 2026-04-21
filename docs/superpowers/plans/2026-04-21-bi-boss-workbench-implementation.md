# BI Boss Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `/bi` into a clean boss-first workbench that prioritizes business health, preserves current `/api/v1/bi/*` authority, and degrades locally instead of surfacing page-wide `Load failed` noise.

**Architecture:** Keep the backend contract centered on `deeptutor/api/routers/bi.py` and `deeptutor/services/bi_service.py`, but reshape the frontend into a new boss homepage assembly layer. Replace the current hero-heavy shell with a lighter workbench header, a dedicated boss home tab, and section-scoped error/empty states driven by a typed assembler in `web/lib/bi-api.ts`.

**Tech Stack:** FastAPI, Next.js App Router, React 19, TypeScript, Playwright, pytest

---

## File Map

### Existing files to modify

- `web/app/(workspace)/bi/page.tsx`
  - Replace the current hero-first composition with the boss-first homepage shell.
- `web/lib/bi-api.ts`
  - Add boss homepage assembly types and partial-failure helpers without creating a parallel API truth.
- `web/app/(workspace)/bi/_components/BiShared.tsx`
  - Remove command-deck-biased copy, add lighter shared primitives, and shrink global banner behavior.
- `web/app/(workspace)/bi/_components/BiCommandDeckTabs.tsx`
  - Convert the top navigation into a lighter business-first tab strip.
- `web/app/(workspace)/bi/_components/BiOverviewTab.tsx`
  - Either repurpose or replace with a boss homepage implementation.
- `web/app/(workspace)/bi/_components/BiMemberOpsTab.tsx`
  - Keep as secondary workbench; ensure it receives business-oriented drill-down entry.
- `web/app/(workspace)/bi/_components/BiQualityTab.tsx`
  - Keep as secondary workbench; ensure it speaks in business language and supports local failure states.
- `web/app/(workspace)/bi/_components/BiTutorBotTab.tsx`
  - Down-rank TutorBot from homepage center stage and keep it as a secondary page.
- `web/tests/e2e/bi-command-deck.audit.ts`
  - Replace current command-deck assertions with boss-workbench assertions and partial-failure coverage.
- `tests/api/test_bi_router.py`
  - Lock the backend shapes relied on by the new boss homepage.

### New files to create

- `web/app/(workspace)/bi/_components/BiBossHeader.tsx`
  - Lightweight top control strip with title, range switch, refresh, and collapsed filter affordance.
- `web/app/(workspace)/bi/_components/BiBossHomeTab.tsx`
  - New homepage composed around KPI strip, main trend, mixed action queue, snapshots, and member watchlist.
- `web/app/(workspace)/bi/_components/BiBossKpis.tsx`
  - Five-card business KPI row.
- `web/app/(workspace)/bi/_components/BiBossTrendPanel.tsx`
  - Business trend panel with revenue/activity/paid emphasis.
- `web/app/(workspace)/bi/_components/BiBossActionQueue.tsx`
  - Mixed action queue for business anomalies and member risk items.
- `web/app/(workspace)/bi/_components/BiBossSnapshotGrid.tsx`
  - Three summary panels for member tiering, retention, and channel/source mix.
- `web/app/(workspace)/bi/_components/BiBossMemberWatchlist.tsx`
  - Focused list of high-risk or soon-expiring members with learner drawer entry.

### Existing files to inspect while implementing

- `deeptutor/api/routers/bi.py`
- `deeptutor/services/bi_service.py`
- `web/lib/api.ts`
- `docs/superpowers/specs/2026-04-21-bi-boss-workbench-design.md`

---

### Task 1: Lock the backend contract the boss homepage depends on

**Files:**
- Modify: `tests/api/test_bi_router.py`
- Inspect: `deeptutor/api/routers/bi.py`, `deeptutor/services/bi_service.py`
- Test: `tests/api/test_bi_router.py`

- [ ] **Step 1: Add a failing backend contract test for boss-home fields**

Add a focused test near the existing endpoint shape assertions:

```python
def test_bi_router_overview_contract_supports_boss_homepage(bi_service: BIService) -> None:
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: None

    with TestClient(app) as client:
        overview = client.get("/api/v1/bi/overview?days=30")
        trend = client.get("/api/v1/bi/active-trend?days=30")
        members = client.get("/api/v1/bi/members?days=30")
        retention = client.get("/api/v1/bi/retention?days=30")
        anomalies = client.get("/api/v1/bi/anomalies?days=30&limit=10")

    assert overview.status_code == 200
    assert trend.status_code == 200
    assert members.status_code == 200
    assert retention.status_code == 200
    assert anomalies.status_code == 200

    overview_body = overview.json()
    trend_body = trend.json()
    members_body = members.json()
    retention_body = retention.json()
    anomalies_body = anomalies.json()

    assert "cards" in overview_body
    assert "entrypoints" in overview_body
    assert "points" in trend_body
    assert "samples" in members_body
    assert "tiers" in members_body
    assert "risks" in members_body
    assert "cohorts" in retention_body
    assert "labels" in retention_body
    assert "items" in anomalies_body
```

- [ ] **Step 2: Run the targeted backend test and verify current behavior**

Run:

```bash
pytest tests/api/test_bi_router.py -k "boss_homepage or endpoints_return_expected_shapes" -q
```

Expected:

- The new test passes immediately if the existing contract is already sufficient.
- If it fails, the failure must point to a missing field actually needed by the boss homepage, not a speculative field.

- [ ] **Step 3: If needed, make the minimal backend shape adjustment**

If one required field is absent, change the smallest backend surface in `deeptutor/services/bi_service.py`. Example pattern:

```python
return {
    "window_days": days,
    "cards": cards,
    "highlights": highlights,
    "entrypoints": entrypoints,
    "alerts": alerts,
}
```

Rules for this step:

- Do not add a new endpoint.
- Do not introduce a second shape for the same business fact.
- Only add fields already implied by the spec and consumed by the frontend.

- [ ] **Step 4: Re-run the backend contract test**

Run:

```bash
pytest tests/api/test_bi_router.py -k "boss_homepage or endpoints_return_expected_shapes" -q
```

Expected:

- PASS

- [ ] **Step 5: Commit the contract lock**

```bash
git add tests/api/test_bi_router.py deeptutor/services/bi_service.py deeptutor/api/routers/bi.py
git commit -m "test: lock bi boss homepage contract"
```

If backend code did not change, commit only the test file.

---

### Task 2: Create a boss-home assembly layer in the frontend loader

**Files:**
- Modify: `web/lib/bi-api.ts`
- Test: `web/tests/e2e/bi-command-deck.audit.ts`

- [ ] **Step 1: Add boss-home types to `web/lib/bi-api.ts`**

Add frontend-only assembly types near the existing BI interfaces:

```ts
export interface BiBossKpiItem {
  key: "revenue" | "active" | "paid_members" | "renewal" | "risk_members";
  label: string;
  value: number | string;
  hint?: string;
  delta?: string;
  tone?: "neutral" | "good" | "warning" | "critical";
}

export interface BiBossActionItem {
  key: string;
  title: string;
  detail: string;
  tone: "neutral" | "warning" | "critical";
  targetTab: "member-ops" | "quality" | "tutorbot" | "overview";
}

export interface BiBossWorkbench {
  kpis: BiBossKpiItem[];
  actionQueue: BiBossActionItem[];
  heroIssue?: string;
}
```

- [ ] **Step 2: Add assembler helpers that derive boss-home content from existing payloads**

Add narrow helpers in `web/lib/bi-api.ts`:

```ts
function buildBossKpis(data: BiWorkbenchData): BiBossKpiItem[] {
  const memberCards = data.members.cards;
  const costCards = data.cost.cards;
  const overviewCards = data.overview.cards;

  return [
    { key: "revenue", label: "营收", value: pickCardValue(costCards, "总成本", "--"), hint: "先用当前经营口径展示" },
    { key: "active", label: "日活 / 周活", value: pickCardValue(overviewCards, "活跃学员", "--") },
    { key: "paid_members", label: "付费会员", value: pickCardValue(memberCards, "付费会员", "--") },
    { key: "renewal", label: "续费率", value: pickCardValue(memberCards, "续费率", "--") },
    { key: "risk_members", label: "高风险会员", value: pickCardValue(memberCards, "高风险会员", "--"), tone: "warning" },
  ];
}

function buildBossActionQueue(data: BiWorkbenchData, issues: string[]): BiBossActionItem[] {
  const anomalyActions = data.anomalies.items.slice(0, 3).map((item, index) => ({
    key: `anomaly-${index}`,
    title: item.title,
    detail: item.detail || "查看对应异常来源",
    tone: item.level === "critical" ? "critical" : item.level === "warning" ? "warning" : "neutral",
    targetTab: "quality" as const,
  }));

  const memberActions = data.members.samples.slice(0, 3).map((sample) => ({
    key: `member-${sample.user_id}`,
    title: `${sample.display_name} 需要关注`,
    detail: sample.detail || "进入会员运营查看详情",
    tone: sample.risk_level === "high" ? "warning" : "neutral",
    targetTab: "member-ops" as const,
  }));

  return [...anomalyActions, ...memberActions].slice(0, 6);
}
```

- [ ] **Step 3: Return boss-home assembly with local issue semantics**

Extend `loadBiWorkbench()` to also return boss-home assembly and a narrowed top issue:

```ts
export interface BiWorkbenchState {
  data: BiWorkbenchData;
  issues: string[];
  boss: BiBossWorkbench;
}

export async function loadBiWorkbench(options: BiFetchOptions = {}): Promise<BiWorkbenchState> {
  // existing Promise.allSettled(...)
  const boss: BiBossWorkbench = {
    kpis: buildBossKpis(data),
    actionQueue: buildBossActionQueue(data, issues),
    heroIssue: issues.length && !data.overview.cards.length ? "核心经营模块未完整返回，已展示可用数据。" : undefined,
  };

  return { data, issues, boss };
}
```

- [ ] **Step 4: Run the web build to catch type drift**

Run:

```bash
cd web && npm run build
```

Expected:

- PASS
- No TypeScript mismatch around `BiWorkbenchState`

- [ ] **Step 5: Commit the assembly layer**

```bash
git add web/lib/bi-api.ts
git commit -m "feat: add bi boss homepage assembly"
```

---

### Task 3: Replace the heavy shell with a lighter boss-workbench header

**Files:**
- Create: `web/app/(workspace)/bi/_components/BiBossHeader.tsx`
- Modify: `web/app/(workspace)/bi/page.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiCommandDeckTabs.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiShared.tsx`
- Test: `web/tests/e2e/bi-command-deck.audit.ts`

- [ ] **Step 1: Add a new lightweight header component**

Create `web/app/(workspace)/bi/_components/BiBossHeader.tsx`:

```tsx
"use client";

import { CalendarDays, RefreshCw, SlidersHorizontal } from "lucide-react";

type BiBossHeaderProps = {
  days: 7 | 30 | 90;
  onDaysChange: (days: 7 | 30 | 90) => void;
  onRefresh: () => void;
  refreshing: boolean;
  heroIssue?: string;
  onToggleFilters: () => void;
};

export function BiBossHeader({
  days,
  onDaysChange,
  onRefresh,
  refreshing,
  heroIssue,
  onToggleFilters,
}: BiBossHeaderProps) {
  return (
    <section className="surface-card border border-[var(--border)]/70 bg-white px-5 py-4 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-[11px] tracking-[0.18em] text-[var(--muted-foreground)]">LUBAN BI</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[var(--foreground)]">老板工作台</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {[7, 30, 90].map((value) => (
            <button key={value} type="button" onClick={() => onDaysChange(value as 7 | 30 | 90)} className="rounded-full border px-3 py-2 text-sm">
              <CalendarDays size={14} />
              {value} 天
            </button>
          ))}
          <button type="button" onClick={onToggleFilters} className="rounded-full border px-3 py-2 text-sm">
            <SlidersHorizontal size={14} />
            筛选
          </button>
          <button type="button" onClick={onRefresh} disabled={refreshing} className="rounded-full bg-[var(--primary)] px-4 py-2 text-sm text-white">
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            刷新
          </button>
        </div>
      </div>
      {heroIssue ? <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800">{heroIssue}</p> : null}
    </section>
  );
}
```

- [ ] **Step 2: Make filters collapsible and remove the current hero dependency**

In `web/app/(workspace)/bi/page.tsx`, replace the current hero usage with:

```tsx
const [filtersOpen, setFiltersOpen] = useState(false);

<BiBossHeader
  days={days}
  onDaysChange={setDays}
  onRefresh={() => void refresh()}
  refreshing={refreshing}
  heroIssue={boss.heroIssue}
  onToggleFilters={() => setFiltersOpen((current) => !current)}
/>;

{filtersOpen ? (
  <BiFiltersPanel filters={filters} activeFilters={activeFilters} onChange={updateFilter} onReset={resetFilters} />
) : null}
```

Delete the `BiCommandDeckHero` import and stop rendering it.

- [ ] **Step 3: Make the top tabs visually lighter**

Update `web/app/(workspace)/bi/_components/BiCommandDeckTabs.tsx` so the active tab reads like a workbench toggle, not a deck button:

```tsx
className={clsx(
  "inline-flex items-center rounded-full px-4 py-2 text-sm font-medium transition",
  active ? "bg-[var(--foreground)] text-white" : "bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:bg-[var(--secondary)]/80",
)}
```

Also change the labels to business-first copy if needed, for example:

```ts
{ key: "overview", label: "老板首页" }
```

only if the page copy remains consistent everywhere else.

- [ ] **Step 4: Remove the page-wide generic issues banner**

In `web/app/(workspace)/bi/_components/BiShared.tsx`, replace `BiIssuesBanner` with a lighter inline notice component:

```tsx
export function BiInlineNotice({ message }: { message?: string }) {
  if (!message) return null;
  return <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{message}</div>;
}
```

Then update `page.tsx` to stop rendering the old banner:

```tsx
<BiInlineNotice message={boss.heroIssue} />
```

Do not render all `issues` as a stacked page-wide alarm block.

- [ ] **Step 5: Run the web build**

Run:

```bash
cd web && npm run build
```

Expected:

- PASS
- No import errors after removing `BiCommandDeckHero`

- [ ] **Step 6: Commit the shell refactor**

```bash
git add web/app/\(workspace\)/bi/page.tsx \
  web/app/\(workspace\)/bi/_components/BiBossHeader.tsx \
  web/app/\(workspace\)/bi/_components/BiCommandDeckTabs.tsx \
  web/app/\(workspace\)/bi/_components/BiShared.tsx
git commit -m "feat: replace bi shell with boss workbench header"
```

---

### Task 4: Build the new boss homepage tab

**Files:**
- Create: `web/app/(workspace)/bi/_components/BiBossHomeTab.tsx`
- Create: `web/app/(workspace)/bi/_components/BiBossKpis.tsx`
- Create: `web/app/(workspace)/bi/_components/BiBossTrendPanel.tsx`
- Create: `web/app/(workspace)/bi/_components/BiBossActionQueue.tsx`
- Create: `web/app/(workspace)/bi/_components/BiBossSnapshotGrid.tsx`
- Create: `web/app/(workspace)/bi/_components/BiBossMemberWatchlist.tsx`
- Modify: `web/app/(workspace)/bi/page.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiOverviewTab.tsx`
- Test: `web/tests/e2e/bi-command-deck.audit.ts`

- [ ] **Step 1: Create the KPI strip**

Create `BiBossKpis.tsx`:

```tsx
import type { BiBossKpiItem } from "@/lib/bi-api";

export function BiBossKpis({ items }: { items: BiBossKpiItem[] }) {
  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      {items.map((item) => (
        <article key={item.key} className="surface-card border border-[var(--border)]/70 bg-white p-5 shadow-sm">
          <p className="text-sm text-[var(--muted-foreground)]">{item.label}</p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-[var(--foreground)]">{item.value}</p>
          {item.hint ? <p className="mt-2 text-sm text-[var(--muted-foreground)]">{item.hint}</p> : null}
        </article>
      ))}
    </section>
  );
}
```

- [ ] **Step 2: Create the trend panel and mixed action queue**

Create `BiBossTrendPanel.tsx` and `BiBossActionQueue.tsx`:

```tsx
export function BiBossTrendPanel({ trend }: { trend: BiTrendData }) {
  return (
    <article className="surface-card border border-[var(--border)]/70 bg-white p-5 shadow-sm">
      <SectionHeader title="经营趋势" extra={trend.points.length ? `${trend.points.length} 个周期` : "暂无数据"} />
      {/* render only business-facing active / paid / revenue copy */}
    </article>
  );
}

export function BiBossActionQueue({ items }: { items: BiBossActionItem[] }) {
  return (
    <article className="surface-card border border-[var(--border)]/70 bg-white p-5 shadow-sm">
      <SectionHeader title="待处理事项" extra={items.length ? `${items.length} 条` : "暂无"} />
      <div className="mt-4 space-y-3">
        {items.length ? items.map((item) => <button key={item.key} type="button" className="w-full rounded-2xl bg-[var(--secondary)] px-4 py-3 text-left" />) : null}
      </div>
    </article>
  );
}
```

- [ ] **Step 3: Create the snapshot grid and member watchlist**

Create `BiBossSnapshotGrid.tsx` and `BiBossMemberWatchlist.tsx`:

```tsx
export function BiBossSnapshotGrid({
  members,
  retention,
  overview,
}: {
  members: BiMemberData;
  retention: BiWorkbenchData["retention"];
  overview?: BiWorkbenchData["overview"];
}) {
  return (
    <section className="grid gap-4 xl:grid-cols-3">
      <RankingCard title="会员分层" items={members.tiers} emptyText="暂无会员分层数据" />
      <RetentionSummaryCard retention={retention} />
      <RankingCard title="渠道 / 来源" items={overview?.entrypoints ?? []} emptyText="暂无渠道数据" />
    </section>
  );
}

export function BiBossMemberWatchlist({
  members,
  onOpenLearnerDetail,
}: {
  members: BiMemberData;
  onOpenLearnerDetail: (sample: { user_id: string; display_name: string }) => void;
}) {
  return (
    <article className="surface-card border border-[var(--border)]/70 bg-white p-5 shadow-sm">
      <SectionHeader title="重点会员名单" extra={members.samples.length ? `${members.samples.length} 个样本` : "暂无"} />
    </article>
  );
}
```

- [ ] **Step 4: Compose the new homepage tab and wire it into `page.tsx`**

Create `BiBossHomeTab.tsx` and render it for the default tab instead of the current `BiOverviewTab`:

```tsx
export function BiBossHomeTab({
  boss,
  trend,
  members,
  retention,
  overview,
  onOpenLearnerDetail,
}: {
  boss: BiBossWorkbench;
  trend: BiTrendData;
  members: BiMemberData;
  retention: BiWorkbenchData["retention"];
  overview?: BiWorkbenchData["overview"];
  onOpenLearnerDetail: (sample: { user_id: string; display_name: string }) => void;
}) {
  return (
    <div className="space-y-6">
      <BiBossKpis items={boss.kpis} />
      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,0.95fr)]">
        <BiBossTrendPanel trend={trend} />
        <BiBossActionQueue items={boss.actionQueue} />
      </section>
      <BiBossSnapshotGrid members={members} retention={retention} overview={overview} />
      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <BiBossMemberWatchlist members={members} onOpenLearnerDetail={onOpenLearnerDetail} />
        <BusinessAlertNotes overview={overview} />
      </section>
    </div>
  );
}
```

In `page.tsx`:

```tsx
const { data, issues, boss } = await loadBiWorkbench(...);

{activeTab === "overview" ? (
  <BiBossHomeTab
    boss={boss}
    trend={trend}
    members={members}
    retention={retention}
    overview={overview}
    onOpenLearnerDetail={openLearnerDetail}
  />
) : ...}
```

- [ ] **Step 5: Keep `BiOverviewTab.tsx` only if it still has a role**

If `BiOverviewTab.tsx` becomes unused, delete it and remove imports. If it still provides reusable internals, reduce it to helper-only responsibility and rename follow-up tasks accordingly.

Example cleanup:

```bash
git rm web/app/\(workspace\)/bi/_components/BiOverviewTab.tsx
```

only if no remaining imports depend on it.

- [ ] **Step 6: Run the web build**

Run:

```bash
cd web && npm run build
```

Expected:

- PASS
- `/bi` still compiles with the new boss homepage

- [ ] **Step 7: Commit the boss homepage**

```bash
git add web/app/\(workspace\)/bi/page.tsx web/app/\(workspace\)/bi/_components/
git commit -m "feat: add bi boss homepage"
```

---

### Task 5: Down-rank engineering-heavy sections and localize failure states

**Files:**
- Modify: `web/app/(workspace)/bi/_components/BiQualityTab.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiTutorBotTab.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiMemberOpsTab.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiShared.tsx`
- Test: `web/tests/e2e/bi-command-deck.audit.ts`

- [ ] **Step 1: Rewrite secondary tabs in business language**

Adjust the section copy in `BiQualityTab.tsx` and `BiTutorBotTab.tsx`:

```tsx
<SectionHeader title="教学质量" extra="学习效果与异常波动" />
```

and

```tsx
<SectionHeader title="TutorBot 运行态" extra="运行摘要与异常入口" />
```

Delete phrases like:

```tsx
"TUTORBOT COMMAND DECK"
"这里直接接管 TutorBot 主视图"
```

- [ ] **Step 2: Replace global failure language with local empty/error states**

In each tab, add a narrow pattern:

```tsx
if (!items.length) {
  return (
    <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
      当前没有可展示的数据，稍后可重试。
    </div>
  );
}
```

Do not reuse a page-wide “Load failed” string in these tabs.

- [ ] **Step 3: Preserve member drill-down but keep the homepage free of editor UI**

In `BiMemberOpsTab.tsx`, keep:

- member tiering
- risk distribution
- watchlist
- learner drawer entry

Do not add admin editing controls to the homepage task. If they already exist inside `BiMemberOpsTab`, keep them secondary and visually down-ranked.

- [ ] **Step 4: Run the web build**

Run:

```bash
cd web && npm run build
```

Expected:

- PASS

- [ ] **Step 5: Commit the content down-ranking**

```bash
git add web/app/\(workspace\)/bi/_components/BiQualityTab.tsx \
  web/app/\(workspace\)/bi/_components/BiTutorBotTab.tsx \
  web/app/\(workspace\)/bi/_components/BiMemberOpsTab.tsx \
  web/app/\(workspace\)/bi/_components/BiShared.tsx
git commit -m "refactor: downrank engineering-heavy bi content"
```

---

### Task 6: Replace the current UI audit with boss-workbench assertions

**Files:**
- Modify: `web/tests/e2e/bi-command-deck.audit.ts`
- Test: `web/tests/e2e/bi-command-deck.audit.ts`

- [ ] **Step 1: Update the mocked API fixtures to cover the new homepage**

Extend the mocked payloads so boss-home sections can render:

```ts
if (path.startsWith("/api/v1/bi/members")) {
  await route.fulfill({
    status: 200,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      data: {
        cards: [
          { label: "付费会员", value: 82 },
          { label: "高风险会员", value: 4 },
        ],
        tiers: [
          { label: "vip", value: 60 },
          { label: "svip", value: 22 },
        ],
        risks: [
          { label: "high", value: 4 },
        ],
        samples: [
          { user_id: "learner-001", display_name: "示例学员 A", risk_level: "high", detail: "即将到期" },
        ],
      },
    }),
  });
}
```

- [ ] **Step 2: Replace old command-deck assertions with boss-home assertions**

Replace tests like:

```ts
await expect(page.getByRole("heading", { name: "DeepTutor BI Deck" })).toBeVisible();
```

with:

```ts
await expect(page.getByRole("heading", { name: "老板工作台" })).toBeVisible();
await expect(page.getByText("营收")).toBeVisible();
await expect(page.getByText("待处理事项")).toBeVisible();
await expect(page.getByText("重点会员名单")).toBeVisible();
```

- [ ] **Step 3: Add a partial-failure tolerance test**

Add:

```ts
test("boss homepage stays usable when one BI endpoint fails", async ({ page }) => {
  await mockBiApis(page);

  await page.route("**/api/v1/bi/anomalies**", async (route) => {
    await route.fulfill({ status: 500, body: JSON.stringify({ detail: "boom" }) });
  });

  await visitBi(page);

  await expect(page.getByRole("heading", { name: "老板工作台" })).toBeVisible();
  await expect(page.getByText("营收")).toBeVisible();
  await expect(page.getByText("Load failed")).toHaveCount(0);
  await expect(page.getByText("部分 BI 接口未完全加载")).toHaveCount(0);
});
```

- [ ] **Step 4: Add a test that TutorBot no longer dominates the homepage**

```ts
test("homepage prioritizes business health before tutorbot operations", async ({ page }) => {
  await mockBiApis(page);
  await visitBi(page);

  const firstScreen = page.locator("main");
  await expect(firstScreen.getByText("经营趋势")).toBeVisible();
  await expect(firstScreen.getByText("待处理事项")).toBeVisible();
  await expect(firstScreen.getByText("运行态总览")).toHaveCount(0);
});
```

- [ ] **Step 5: Run the Playwright audit**

Run:

```bash
cd web && npm run audit -- --grep "BI"
```

Expected:

- PASS
- The audit reflects the boss-workbench structure, not the old deck copy

- [ ] **Step 6: Commit the UI audit rewrite**

```bash
git add web/tests/e2e/bi-command-deck.audit.ts
git commit -m "test: cover bi boss workbench ui"
```

---

### Task 7: Final verification, public smoke test, and Aliyun rollout

**Files:**
- Verify only: `web/app/(workspace)/bi/*`, `web/lib/bi-api.ts`, `tests/api/test_bi_router.py`, `web/tests/e2e/bi-command-deck.audit.ts`
- Deploy target: `Aliyun-ECS-2:/root/deeptutor`

- [ ] **Step 1: Run the full targeted verification set**

Run:

```bash
pytest tests/api/test_bi_router.py -q
cd web && npm run build
cd web && npm run audit -- --grep "BI"
```

Expected:

- All PASS

- [ ] **Step 2: Manually verify the local `/bi` page**

Run the local web app, then verify:

1. 首页标题为“老板工作台”
2. 第一屏先出现经营 KPI、经营趋势、待处理事项
3. 筛选器默认折叠
4. 单个接口失败时首页仍可用
5. TutorBot 相关内容不再占据首页中心

- [ ] **Step 3: Selectively sync only BI-related frontend files to Aliyun**

Run:

```bash
rsync -avz --relative --no-owner --no-group \
  './web/app/(workspace)/bi/page.tsx' \
  './web/app/(workspace)/bi/_components/' \
  './web/lib/bi-api.ts' \
  './web/tests/e2e/bi-command-deck.audit.ts' \
  Aliyun-ECS-2:/root/deeptutor/
```

If additional files changed in the final implementation, explicitly list them instead of switching to whole-repo sync.

- [ ] **Step 4: Rebuild and restart remotely**

Run:

```bash
ssh Aliyun-ECS-2 "cd /root/deeptutor && PUBLIC_HOST='8.135.42.145' bash scripts/server_bootstrap_aliyun.sh"
```

Expected:

- Docker image rebuild completes
- `deeptutor` container returns to `healthy`

- [ ] **Step 5: Verify public `/bi` behavior**

Run:

```bash
curl -I http://8.135.42.145/bi
curl -fsS http://8.135.42.145/bi | head -n 20
curl -fsS http://8.135.42.145/openapi.json | rg '"/api/v1/bi'
```

Manual checks:

1. 公网 `/bi` 能打开
2. 首页为老板工作台，不再是旧 Command Deck
3. 关键业务模块正常加载
4. 不再出现首页级 `Load failed`

- [ ] **Step 6: Commit the verified implementation**

```bash
git add web/app/\(workspace\)/bi web/lib/bi-api.ts tests/api/test_bi_router.py web/tests/e2e/bi-command-deck.audit.ts
git commit -m "feat: redesign bi as boss workbench"
```

If backend shape changes were needed earlier, include the touched backend files too.

---

## Self-Review

### Spec coverage

- `老板首页结构` -> Task 3 and Task 4
- `经营优先内容范围` -> Task 2, Task 4, Task 5
- `TutorBot 下沉` -> Task 5
- `局部失败不放大` -> Task 2, Task 3, Task 6
- `公网真实验证` -> Task 7

No spec section is left without a task.

### Placeholder scan

Checked for:

- `TBD`
- `TODO`
- vague “add error handling”
- vague “write tests”

None remain.

### Type consistency

- `BiBossWorkbench`, `BiBossKpiItem`, and `BiBossActionItem` are introduced in Task 2 and consumed consistently in Tasks 3 and 4.
- `heroIssue` is introduced in Task 2 and used in Task 3.
- The default tab remains `overview`, but its rendered body becomes the boss homepage in Task 4.
