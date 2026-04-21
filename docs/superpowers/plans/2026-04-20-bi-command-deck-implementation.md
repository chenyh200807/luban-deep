# BI Command Deck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 DeepTutor BI 从单页工作台重组为“Command Deck”指挥舱首页，采用 DeepTutor 铜棕品牌气质，并把首页收口为 `总览 / 质量稳定性 / 会员经营 / TutorBot能力` 四个一级主分区。

**Architecture:** 保留现有 `/api/v1/bi/*` 数据合同，不新增新的 BI API。前端只做信息架构重组：`page.tsx` 退化为数据加载与全局状态容器，具体展示拆为 Hero、Tabs 和四个主分区组件；`知识库 / 成本 / Learner 360` 改为副面板或 drill-down，不再抢首页一级叙事。

**Tech Stack:** Next.js App Router, React 19, TypeScript, Tailwind utility classes, existing `web/lib/bi-api.ts`, Python source-text regression tests, ESLint

---

## 文件结构

- `web/app/(workspace)/bi/page.tsx`
  - 只保留数据获取、全局时间窗口、一级 Tab、Learner 360 抽屉状态；不再承载全部 1300+ 行展示逻辑
- `web/app/(workspace)/bi/_components/BiCommandDeckHero.tsx`
  - Hero 顶部控制台：标题、副标题、时间窗口、刷新、导出、当前状态摘要、可折叠高级筛选
- `web/app/(workspace)/bi/_components/BiCommandDeckTabs.tsx`
  - 四个一级主分区导航：`Overview / Quality / Member Ops / TutorBot`
- `web/app/(workspace)/bi/_components/BiOverviewTab.tsx`
  - 总览分区：6 张 KPI 卡、趋势、异常摘要、经营快照
- `web/app/(workspace)/bi/_components/BiQualityTab.tsx`
  - 质量/稳定性分区：健康摘要、趋势波动、异常、反馈、数据完整性提示
- `web/app/(workspace)/bi/_components/BiMemberOpsTab.tsx`
  - 会员经营分区：会员卡、tier/risk、留存、样本用户入口
- `web/app/(workspace)/bi/_components/BiTutorBotTab.tsx`
  - TutorBot/能力分区：TutorBot 卡、排行、状态、最近消息、能力/工具、知识库副面板
- `web/app/(workspace)/bi/_components/BiShared.tsx`
  - 共用组件：`SectionHeader`、`MetricCard`、`MiniStatCard`、`RankingCard`、`AlertCard`、`InfoLine`、`LegendDot`、`FilterSelect`
- `tests/web/test_bi_command_deck_surface.py`
  - 新增页面结构回归：一级 Tab、Hero 文案、Learner 360 抽屉、旧 JumpChip 去除
- `tests/web/test_bi_public_surface.py`
  - 保留 BI 公网可见性断言，并补充新页面入口标题存在性

## Task 1: 锁定 Command Deck 页面结构红测

**Files:**
- Create: `tests/web/test_bi_command_deck_surface.py`
- Modify: `tests/web/test_bi_public_surface.py`
- Verify: `web/app/(workspace)/bi/page.tsx`

- [ ] **Step 1: 写一级 Tab 与 Hero 文案红测**

```python
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _bi_page_source() -> str:
    return (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "page.tsx").read_text(encoding="utf-8")


def test_bi_page_exposes_command_deck_hero_copy() -> None:
    source = _bi_page_source()

    assert "DeepTutor BI Deck" in source
    assert "经营、质量、会员、TutorBot 四条主线的一体化指挥舱" in source


def test_bi_page_exposes_primary_tabs() -> None:
    source = _bi_page_source()

    assert "Overview" in source
    assert "Quality" in source
    assert "Member Ops" in source
    assert "TutorBot" in source
```

- [ ] **Step 2: 写旧锚点入口退出主叙事的红测**

```python
def test_bi_page_no_longer_uses_jump_chip_navigation() -> None:
    source = _bi_page_source()

    assert "function JumpChip" not in source
    assert 'href="#trend"' not in source
    assert 'href="#knowledge"' not in source


def test_bi_page_keeps_learner_360_drawer() -> None:
    source = _bi_page_source()

    assert 'title="Learner 360"' in source
```

- [ ] **Step 3: 扩充公网可见性回归，锁定新标题**

```python
def test_bi_page_contains_command_deck_entry_title() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "page.tsx").read_text(encoding="utf-8")

    assert "DeepTutor BI Deck" in source
    assert "BI workspace unavailable" not in source
```

- [ ] **Step 4: 跑红测确认当前实现尚未满足新结构**

Run:

```bash
python -m pytest tests/web/test_bi_command_deck_surface.py tests/web/test_bi_public_surface.py -q
```

Expected:

```text
FAILED tests/web/test_bi_command_deck_surface.py::test_bi_page_exposes_command_deck_hero_copy
FAILED tests/web/test_bi_command_deck_surface.py::test_bi_page_exposes_primary_tabs
FAILED tests/web/test_bi_command_deck_surface.py::test_bi_page_no_longer_uses_jump_chip_navigation
```

- [ ] **Step 5: Commit**

```bash
git add tests/web/test_bi_command_deck_surface.py tests/web/test_bi_public_surface.py
git commit -m "test lock bi command deck surface"
```

## Task 2: 先把页面骨架收成 Hero + 一级 Tabs + 全局状态容器

**Files:**
- Create: `web/app/(workspace)/bi/_components/BiCommandDeckHero.tsx`
- Create: `web/app/(workspace)/bi/_components/BiCommandDeckTabs.tsx`
- Create: `web/app/(workspace)/bi/_components/BiShared.tsx`
- Modify: `web/app/(workspace)/bi/page.tsx`
- Test: `tests/web/test_bi_command_deck_surface.py`

- [ ] **Step 1: 在 `page.tsx` 里定义一级 Tab authority**

```tsx
type BiPrimaryTabId = "overview" | "quality" | "memberOps" | "tutorbot";

const PRIMARY_TABS: Array<{ id: BiPrimaryTabId; label: string; summary: string }> = [
  { id: "overview", label: "Overview", summary: "总览" },
  { id: "quality", label: "Quality", summary: "质量/稳定性" },
  { id: "memberOps", label: "Member Ops", summary: "会员经营" },
  { id: "tutorbot", label: "TutorBot", summary: "TutorBot/能力" },
];

const [activeTab, setActiveTab] = useState<BiPrimaryTabId>("overview");
```

- [ ] **Step 2: 新建 Hero 组件，收拢顶部控制台**

```tsx
export function BiCommandDeckHero(props: {
  heroTitle: string;
  heroSubtitle: string;
  days: 7 | 30 | 90;
  onDaysChange: (days: 7 | 30 | 90) => void;
  onRefresh: () => void;
  onExport: () => void;
  refreshing: boolean;
  exporting: boolean;
  lastUpdatedAt: string | null;
  activeFilters: string[];
  filters: { capability: string; entrypoint: string; tier: string };
  onFilterChange: (field: "capability" | "entrypoint" | "tier", value: string) => void;
  onResetFilters: () => void;
}) {
  return (
    <section className="surface-card overflow-hidden border-0 bg-[linear-gradient(135deg,#151312_0%,#2a211d_44%,#8f4625_100%)] text-white shadow-[0_24px_60px_rgba(31,26,23,0.22)]">
      {/* 标题 / 时间窗口 / 刷新 / 导出 / 状态摘要 / 高级筛选 */}
    </section>
  );
}
```

- [ ] **Step 3: 新建 Tabs 组件，替换旧 `JumpChip` 导航**

```tsx
export function BiCommandDeckTabs(props: {
  tabs: Array<{ id: "overview" | "quality" | "memberOps" | "tutorbot"; label: string; summary: string }>;
  activeTab: "overview" | "quality" | "memberOps" | "tutorbot";
  onChange: (tab: "overview" | "quality" | "memberOps" | "tutorbot") => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {props.tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => props.onChange(tab.id)}
          className={tab.id === props.activeTab ? "rounded-xl bg-[var(--primary)] px-3 py-2 text-white" : "rounded-xl bg-[var(--secondary)] px-3 py-2 text-[var(--secondary-foreground)]"}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: 让 `page.tsx` 退化为状态容器，不再直接渲染所有区块**

```tsx
return (
  <div className="h-full overflow-y-auto [scrollbar-gutter:stable] bg-[radial-gradient(circle_at_top_left,_rgba(195,90,44,0.14),_transparent_34%),radial-gradient(circle_at_85%_10%,_rgba(18,122,134,0.09),_transparent_28%),linear-gradient(180deg,#faf9f6_0%,#f4efe8_100%)] px-6 py-6">
    <div className="mx-auto flex max-w-[1540px] flex-col gap-6">
      <BiCommandDeckHero {...heroProps} />
      <BiCommandDeckTabs tabs={PRIMARY_TABS} activeTab={activeTab} onChange={setActiveTab} />
      {/* 下一任务再接入四个 tab 面板 */}
      <Modal {...learner360Props} />
    </div>
  </div>
);
```

- [ ] **Step 5: 跑页面结构测试确认变绿**

Run:

```bash
python -m pytest tests/web/test_bi_command_deck_surface.py tests/web/test_bi_public_surface.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit**

```bash
git add web/app/'(workspace)'/bi/page.tsx web/app/'(workspace)'/bi/_components/BiCommandDeckHero.tsx web/app/'(workspace)'/bi/_components/BiCommandDeckTabs.tsx web/app/'(workspace)'/bi/_components/BiShared.tsx tests/web/test_bi_command_deck_surface.py tests/web/test_bi_public_surface.py
git commit -m "refactor bi page into command deck shell"
```

## Task 3: 实现 `Overview` 与 `Quality` 两个主分区

**Files:**
- Create: `web/app/(workspace)/bi/_components/BiOverviewTab.tsx`
- Create: `web/app/(workspace)/bi/_components/BiQualityTab.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiShared.tsx`
- Modify: `web/app/(workspace)/bi/page.tsx`
- Test: `tests/web/test_bi_command_deck_surface.py`

- [ ] **Step 1: 先写红测，锁定首页四条主线中的前两条已挂载**

```python
def test_bi_page_mounts_overview_and_quality_tab_components() -> None:
    source = _bi_page_source()

    assert "BiOverviewTab" in source
    assert "BiQualityTab" in source
```

- [ ] **Step 2: 跑红测，确认当前还没有这两个分区组件**

Run:

```bash
python -m pytest tests/web/test_bi_command_deck_surface.py::test_bi_page_mounts_overview_and_quality_tab_components -q
```

Expected:

```text
FAILED tests/web/test_bi_command_deck_surface.py::test_bi_page_mounts_overview_and_quality_tab_components
```

- [ ] **Step 3: 实现 `BiOverviewTab`，把 KPI / 趋势 / 异常 / 经营快照收口**

```tsx
export function BiOverviewTab(props: {
  loading: boolean;
  topCards: BiMetricCard[];
  overview: BiWorkbenchData["overview"] | undefined;
  trend: BiTrendData;
  anomalies: BiAnomalyData;
  cost: BiCostData;
  members: BiMemberData;
  tutorbots: BiTutorBotData;
  days: number;
}) {
  return (
    <section className="grid gap-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">{/* KPI */}</div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,0.85fr)]">{/* 趋势 + 经营快照 */}</div>
      <div className="grid gap-4 lg:grid-cols-2">{/* 异常摘要 + 总览提示 */}</div>
    </section>
  );
}
```

- [ ] **Step 4: 实现 `BiQualityTab`，只复用现有 authority，不伪造旧 observability 栈**

```tsx
export function BiQualityTab(props: {
  trend: BiTrendData;
  anomalies: BiAnomalyData;
  feedback: { items: Array<{ title: string; detail?: string; level?: string }> };
  overview: BiWorkbenchData["overview"] | undefined;
}) {
  const qualityAlerts = props.anomalies.items.length
    ? props.anomalies.items
    : (props.overview?.alerts ?? []).map((item) => ({ ...item, level: item.level ?? "warning" }));

  return (
    <section className="grid gap-6">
      <div className="grid gap-4 lg:grid-cols-4">{/* 健康卡 */}</div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,0.75fr)]">{/* 趋势波动 + 数据完整性 */}</div>
      <div className="grid gap-6 lg:grid-cols-2">{/* 异常列表 + 反馈摘要 */}</div>
    </section>
  );
}
```

- [ ] **Step 5: 在 `page.tsx` 中按 `activeTab` 挂载两个新分区**

```tsx
{activeTab === "overview" ? (
  <BiOverviewTab
    loading={loading}
    topCards={topCards}
    overview={overview}
    trend={trend}
    anomalies={anomalies}
    cost={cost}
    members={members}
    tutorbots={tutorbots}
    days={days}
  />
) : null}

{activeTab === "quality" ? (
  <BiQualityTab
    trend={trend}
    anomalies={anomalies}
    feedback={{ items: [] }}
    overview={overview}
  />
) : null}
```

- [ ] **Step 6: 跑结构测试与 lint**

Run:

```bash
python -m pytest tests/web/test_bi_command_deck_surface.py -q
npm --prefix web run lint
```

Expected:

```text
5 passed
✔ No ESLint warnings or errors
```

- [ ] **Step 7: Commit**

```bash
git add web/app/'(workspace)'/bi/page.tsx web/app/'(workspace)'/bi/_components/BiOverviewTab.tsx web/app/'(workspace)'/bi/_components/BiQualityTab.tsx web/app/'(workspace)'/bi/_components/BiShared.tsx tests/web/test_bi_command_deck_surface.py
git commit -m "feat bi overview and quality tabs"
```

## Task 4: 实现 `Member Ops` 与 `TutorBot` 两个主分区，并下沉知识库/成本

**Files:**
- Create: `web/app/(workspace)/bi/_components/BiMemberOpsTab.tsx`
- Create: `web/app/(workspace)/bi/_components/BiTutorBotTab.tsx`
- Modify: `web/app/(workspace)/bi/page.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiShared.tsx`
- Test: `tests/web/test_bi_command_deck_surface.py`

- [ ] **Step 1: 写红测，锁定后两条主线组件**

```python
def test_bi_page_mounts_member_ops_and_tutorbot_tab_components() -> None:
    source = _bi_page_source()

    assert "BiMemberOpsTab" in source
    assert "BiTutorBotTab" in source
```

- [ ] **Step 2: 实现 `BiMemberOpsTab`，保留样本用户到 Learner 360 的 drill-down**

```tsx
export function BiMemberOpsTab(props: {
  members: BiMemberData;
  retention: BiRetentionData;
  onOpenLearnerDetail: (sample: { user_id: string; display_name: string }) => void;
}) {
  return (
    <section className="grid gap-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{/* 会员核心卡 */}</div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">{/* 留存热力 + tier/risk */}</div>
      <div className="surface-card p-5">{/* 样本用户列表 -> onOpenLearnerDetail */}</div>
    </section>
  );
}
```

- [ ] **Step 3: 实现 `BiTutorBotTab`，把知识库降成副面板，不再占一级区**

```tsx
export function BiTutorBotTab(props: {
  tutorbots: BiTutorBotData;
  capabilities: BiCapabilityData;
  tools: BiToolData;
  knowledge: BiKnowledgeData;
  cost: BiCostData;
}) {
  return (
    <section className="grid gap-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">{/* TutorBot 卡 / 排行 / 状态 / 最近消息 */}</div>
      <div className="grid gap-6 xl:grid-cols-2">{/* capability / tool */}</div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">{/* knowledge 副面板 + cost 摘要副卡 */}</div>
    </section>
  );
}
```

- [ ] **Step 4: 把 `page.tsx` 的长卷区块替换为四个互斥主分区**

```tsx
{activeTab === "memberOps" ? (
  <BiMemberOpsTab members={members} retention={retention} onOpenLearnerDetail={openLearnerDetail} />
) : null}

{activeTab === "tutorbot" ? (
  <BiTutorBotTab
    tutorbots={tutorbots}
    capabilities={capabilities}
    tools={tools}
    knowledge={knowledge}
    cost={cost}
  />
) : null}
```

- [ ] **Step 5: 删除旧的长卷锚点区块和 `JumpChip` 剩余痕迹**

```tsx
// 删除这些旧分区入口
// <section id="trend" ...>
// <section id="knowledge" ...>
// <section id="tutorbot" ...>
// <section id="capability" ...>
// 保留 Learner 360 Modal，不改其数据 authority
```

- [ ] **Step 6: 跑前端回归**

Run:

```bash
python -m pytest tests/web/test_bi_command_deck_surface.py tests/web/test_bi_public_surface.py -q
npm --prefix web run lint
```

Expected:

```text
6 passed
✔ No ESLint warnings or errors
```

- [ ] **Step 7: Commit**

```bash
git add web/app/'(workspace)'/bi/page.tsx web/app/'(workspace)'/bi/_components/BiMemberOpsTab.tsx web/app/'(workspace)'/bi/_components/BiTutorBotTab.tsx web/app/'(workspace)'/bi/_components/BiShared.tsx tests/web/test_bi_command_deck_surface.py tests/web/test_bi_public_surface.py
git commit -m "feat bi member ops and tutorbot tabs"
```

## Task 5: 收口降级态、构建验证和浏览器验收

**Files:**
- Modify: `web/app/(workspace)/bi/_components/BiOverviewTab.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiQualityTab.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiMemberOpsTab.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiTutorBotTab.tsx`
- Modify: `tests/web/test_bi_command_deck_surface.py`

- [ ] **Step 1: 写红测，锁定四个主分区的降级态文案**

```python
def test_bi_page_keeps_degraded_copy_for_all_primary_tabs() -> None:
    source = _bi_page_source()

    assert "等待 BI 总览卡片" in source
    assert "当前质量分区仍会展示趋势与异常摘要" in source
    assert "会员侧数据将显示活跃、到期、风险和续费相关卡片" in source
    assert "后端返回 TutorBot 指标后" in source
```

- [ ] **Step 2: 为 `Quality` 分区补明确降级提示**

```tsx
<p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
  当前质量分区仍会展示趋势与异常摘要；更深的 observability 明细待后端接口稳定后再接入。
</p>
```

- [ ] **Step 3: 跑完整静态回归与构建验证**

Run:

```bash
python -m pytest tests/web/test_bi_command_deck_surface.py tests/web/test_bi_public_surface.py -q
npm --prefix web run lint
npm --prefix web run build
```

Expected:

```text
all tests passed
✔ No ESLint warnings or errors
Compiled successfully
```

- [ ] **Step 4: 本地手动验收 `/bi`**

Run:

```bash
npm --prefix web run dev
```

Check in browser:

```text
1. Hero 顶部出现 DeepTutor BI Deck
2. 一级 Tab 只有 Overview / Quality / Member Ops / TutorBot
3. 切 Tab 不跳页
4. 点击会员样本仍能打开 Learner 360 抽屉
5. 没有旧的长卷 JumpChip 导航
```

- [ ] **Step 5: Commit**

```bash
git add web/app/'(workspace)'/bi/_components/BiOverviewTab.tsx web/app/'(workspace)'/bi/_components/BiQualityTab.tsx web/app/'(workspace)'/bi/_components/BiMemberOpsTab.tsx web/app/'(workspace)'/bi/_components/BiTutorBotTab.tsx tests/web/test_bi_command_deck_surface.py
git commit -m "polish bi command deck degradation states"
```

## Spec 覆盖检查

- `旧仓指挥舱结构`：Task 2 的 Hero + 一级 Tabs + 主视图 authority 承接
- `DeepTutor 铜棕品牌`：Task 2 的 Hero 视觉和后续组件布局承接
- `四个一级主分区`：Task 3 + Task 4 承接
- `知识库 / 成本 / Learner 360 下沉`：Task 4 承接
- `降级态和结构稳定`：Task 5 承接
- `不新增后端 contract`：全计划只改 `web/*` 和 `tests/web/*`，不触碰 `deeptutor/api/routers/bi.py`

## 自检

- 本计划没有 `TODO / TBD / implement later` 占位符
- 后续任务中引用的组件名与 Task 2 首次定义保持一致
- 范围被收敛在前端重组与前端回归，没有漂移成旧系统后台迁移
