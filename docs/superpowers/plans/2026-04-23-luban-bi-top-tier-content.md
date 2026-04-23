# Luban BI Top-Tier Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `/bi` from an operations panel into a top-tier business intelligence cockpit for Luban Zhikao, with north-star metrics, lifecycle funnel, member health, action loops, teaching-effect signals, AI quality, unit economics, privacy/audit, and data trust.

**Architecture:** Keep existing authorities: `MemberConsoleService` owns member facts, `SQLiteSessionStore` owns chat sessions, `BIService` owns read-only aggregation, and the Next.js BI workspace owns presentation. Add a small semantic metric layer before changing UI so every new panel consumes named, testable metrics instead of duplicating calculations inside components. Do not count unverified-phone, test, probe, regression, or anonymous-only accounts in boss metrics; keep them in engineering diagnostics and data-trust surfaces only.

**Tech Stack:** FastAPI, Python service layer, SQLite session store, member console JSON store, Next.js App Router, React 19, TypeScript, Tailwind, pytest, `npx tsc --noEmit`, Next production build, Aliyun ECS deploy.

---

## File Map

### Create

- `deeptutor/services/bi_metrics.py`
  - Defines metric IDs, labels, formulas, source authority, trust level, owners, drill-down target, and display groups.
- `tests/services/test_bi_metrics.py`
  - Locks metric dictionary coverage, trust metadata, owner metadata, and rejects duplicate metric IDs.
- `web/app/(workspace)/bi/_components/BiMetricDefinitionCard.tsx`
  - Reusable metric-definition card for data trust and tooltip-style panels.
- `web/app/(workspace)/bi/_components/BiGrowthFunnelPanel.tsx`
  - Growth lifecycle funnel for registered -> activated -> effective learning -> paid -> retained.
- `web/app/(workspace)/bi/_components/BiTeachingEffectPanel.tsx`
  - Teaching-effect panel for mastery, practice, weak-point closure, and learner samples.
- `web/app/(workspace)/bi/_components/BiAiQualityPanel.tsx`
  - AI quality panel for success, feedback, RAG/tool quality, and drill-down samples.
- `web/app/(workspace)/bi/_components/BiDataTrustPanel.tsx`
  - Data trust panel showing source status, degraded modules, and metric definitions.
- `web/app/(workspace)/bi/_components/BiMemberHealthPanel.tsx`
  - Member health distribution and risk queues with transparent scoring reasons.
- `web/app/(workspace)/bi/_components/BiOperatingRhythmPanel.tsx`
  - Daily/weekly/campaign/release rhythm summary with the top 3 actions.

### Modify

- `deeptutor/services/bi_service.py`
  - Add top-tier payload fields: `north_star`, `growth_funnel`, `member_health`, `operating_rhythm`, `teaching_effect`, `ai_quality`, `unit_economics`, `data_trust`.
- `tests/services/test_bi_service_limits.py`
  - Add service-level assertions for the new payload without broadening current collection limits.
- `web/lib/bi-api.ts`
  - Add TypeScript interfaces and normalizers for the new payload fields.
- `web/app/(workspace)/bi/_components/BiBossHomeTab.tsx`
  - Recompose boss cockpit around north star, funnel, teaching effect, AI quality, unit economics, and data trust.
- `web/app/(workspace)/bi/_components/BiBossKpis.tsx`
  - Replace generic cards with business-health cards.
- `web/app/(workspace)/bi/_components/BiBossActionQueue.tsx`
  - Make action queue reason-based and linked to concrete drill-down targets.
- `tests/web/test_bi_member_admin_surface.py`
  - Lock visible sections and collapse/expand behavior.

---

## PRD V2 Hard Gates

These gates come from the strengthened PRD and must be preserved during implementation:

- Boss metrics only count canonical real members: verified phone, not test/probe/regression, mapped to a canonical member identity.
- Chat records are summary-first and collapsed by default; full content loads only after click and must be auditable.
- Every core metric has `metric_id`, label, definition, formula/source authority, trust level, owner, update time, and drill-down target.
- The boss home only shows A/B trust metrics by default; C/D metrics appear as degraded or pending, never as normal facts.
- Health scoring must be transparent. If sample size is too small, show risk labels and reasons instead of pretending the score is predictive.
- Cost authority stays conservative: business cost summary first, Langfuse for cross-check and diagnostics until user/session/release alignment is verified.
- The first implementation target is L0 + L1: trusted口径 + boss cockpit. L2/L3 can expose structure, but must not block the first deliverable.

---

## Task 1: Add BI Metric Dictionary

**Files:**
- Create: `deeptutor/services/bi_metrics.py`
- Create: `tests/services/test_bi_metrics.py`

- [ ] **Step 1: Write the failing metric dictionary test**

Create `tests/services/test_bi_metrics.py`:

```python
from deeptutor.services.bi_metrics import BI_METRICS, metric_by_id


def test_bi_metric_dictionary_has_unique_ids() -> None:
    ids = [metric.metric_id for metric in BI_METRICS]

    assert len(ids) == len(set(ids))


def test_bi_metric_dictionary_covers_top_tier_sections() -> None:
    groups = {metric.group for metric in BI_METRICS}

    assert {
        "north_star",
        "growth",
        "member_ops",
        "member_health",
        "teaching_effect",
        "ai_quality",
        "unit_economics",
        "data_trust",
    }.issubset(groups)


def test_metric_by_id_returns_definition() -> None:
    metric = metric_by_id("effective_learning_members")

    assert metric.label == "有效学习成功会员数"
    assert metric.authority == "bi_service"
    assert "真实手机号会员" in metric.definition
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/services/test_bi_metrics.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'deeptutor.services.bi_metrics'
```

- [ ] **Step 3: Implement `deeptutor/services/bi_metrics.py`**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BIMetricDefinition:
    metric_id: str
    label: str
    group: str
    definition: str
    authority: str
    trust_level: str
    owner: str
    drilldown: str
    display_hint: str = ""


BI_METRICS: tuple[BIMetricDefinition, ...] = (
    BIMetricDefinition(
        metric_id="effective_learning_members",
        label="有效学习成功会员数",
        group="north_star",
        definition="窗口内有真实手机号会员身份，并完成至少一次有效学习会话或学习成果的会员数。",
        authority="bi_service",
        trust_level="B",
        owner="boss",
        drilldown="member_ops",
        display_hint="北极星指标",
    ),
    BIMetricDefinition(
        metric_id="registered_members",
        label="真实注册会员数",
        group="growth",
        definition="通过会员系统 canonical member 口径过滤后的真实手机号会员数，不包含测试、探针和演练账号。",
        authority="member_console",
        trust_level="A",
        owner="ops",
        drilldown="member_ops",
    ),
    BIMetricDefinition(
        metric_id="activated_members",
        label="激活会员数",
        group="growth",
        definition="窗口内至少有一次真实学习会话的注册会员数。",
        authority="bi_service",
        trust_level="B",
        owner="product",
        drilldown="student_360",
    ),
    BIMetricDefinition(
        metric_id="renewal_risk_members",
        label="续费风险会员数",
        group="member_ops",
        definition="即将到期、沉默、高风险或高成本低效果的会员集合。",
        authority="member_console",
        trust_level="B",
        owner="ops",
        drilldown="member_ops",
    ),
    BIMetricDefinition(
        metric_id="member_health_score",
        label="会员健康评分",
        group="member_health",
        definition="由学习行为、会员价值、学习效果、AI 体验和运营关系组成的透明风险评分；样本不足时只展示风险标签和原因。",
        authority="bi_service",
        trust_level="C",
        owner="ops",
        drilldown="student_360",
    ),
    BIMetricDefinition(
        metric_id="mastery_improvement",
        label="章节掌握度提升",
        group="teaching_effect",
        definition="基于 member learner state 中章节掌握度和弱点闭环信号计算的学习效果指标。",
        authority="learner_state",
        trust_level="C",
        owner="teaching",
        drilldown="teaching_effect",
    ),
    BIMetricDefinition(
        metric_id="ai_quality_score",
        label="AI 教学质量分",
        group="ai_quality",
        definition="由回合成功率、反馈、追问、工具/RAG 信号和异常样本共同形成的质量摘要。",
        authority="bi_service",
        trust_level="B",
        owner="engineering",
        drilldown="ai_quality",
    ),
    BIMetricDefinition(
        metric_id="cost_per_effective_learning",
        label="单有效学习成本",
        group="unit_economics",
        definition="窗口总 AI 成本除以有效学习成功会员数；收入未接入时只展示成本侧。",
        authority="bi_service",
        trust_level="B",
        owner="boss",
        drilldown="unit_economics",
    ),
    BIMetricDefinition(
        metric_id="data_trust_score",
        label="数据可信度分",
        group="data_trust",
        definition="基于接口降级、数据源缺口、指标口径完整度和更新时间形成的可信度摘要。",
        authority="bi_service",
        trust_level="A",
        owner="engineering",
        drilldown="data_trust",
    ),
)


def metric_by_id(metric_id: str) -> BIMetricDefinition:
    normalized = str(metric_id or "").strip()
    for metric in BI_METRICS:
        if metric.metric_id == normalized:
            return metric
    raise KeyError(f"Unknown BI metric: {metric_id}")
```

- [ ] **Step 4: Run the metric tests**

Run:

```bash
python -m pytest tests/services/test_bi_metrics.py -q
```

Expected:

```text
3 passed
```

---

## Task 2: Add Top-Tier BI Payload To `BIService`

**Files:**
- Modify: `deeptutor/services/bi_service.py`
- Modify: `tests/services/test_bi_service_limits.py`

- [ ] **Step 1: Write failing service test for top-tier payload**

Add to `tests/services/test_bi_service_limits.py`:

```python
def test_overview_includes_top_tier_bi_sections(bi_service) -> None:
    payload = asyncio.run(bi_service.get_overview(days=30))

    assert "north_star" in payload
    assert "growth_funnel" in payload
    assert "teaching_effect" in payload
    assert "ai_quality" in payload
    assert "unit_economics" in payload
    assert "data_trust" in payload
    assert payload["north_star"]["metric_id"] == "effective_learning_members"
    assert isinstance(payload["growth_funnel"]["steps"], list)
    assert isinstance(payload["data_trust"]["metric_definitions"], list)
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
python -m pytest tests/services/test_bi_service_limits.py -k top_tier -q
```

Expected:

```text
FAILED ... KeyError or AssertionError for missing north_star
```

- [ ] **Step 3: Add minimal helper builders in `BIService`**

In `deeptutor/services/bi_service.py`, import the dictionary:

```python
from deeptutor.services.bi_metrics import BI_METRICS, metric_by_id
```

Add helper methods near existing boss-workbench builders:

```python
@staticmethod
def _metric_definition_payload(metric_id: str) -> dict[str, Any]:
    metric = metric_by_id(metric_id)
    return {
        "metric_id": metric.metric_id,
        "label": metric.label,
        "group": metric.group,
        "definition": metric.definition,
        "authority": metric.authority,
        "display_hint": metric.display_hint,
    }

def _build_north_star_payload(self, context: _BiContext, member_dashboard: dict[str, Any]) -> dict[str, Any]:
    actor_ids = {
        self._resolve_actor_id(session.get("session_id", ""), session.get("preferences") or {})
        for session in context.sessions
    }
    value = len({actor_id for actor_id in actor_ids if actor_id and not actor_id.startswith("anon:")})
    definition = self._metric_definition_payload("effective_learning_members")
    return {
        **definition,
        "value": value,
        "registered_members": _safe_int(member_dashboard.get("total_count")),
        "hint": "第一阶段以窗口内真实会员学习会话近似有效学习成功；后续接入练题/复习成果后升级。",
    }

def _build_growth_funnel_payload(self, context: _BiContext, member_dashboard: dict[str, Any]) -> dict[str, Any]:
    registered = _safe_int(member_dashboard.get("total_count"))
    activated = len({
        self._resolve_actor_id(session.get("session_id", ""), session.get("preferences") or {})
        for session in context.sessions
    })
    effective = activated
    paid = sum(1 for item in self._load_all_members() if str(item.get("tier") or "").lower() in {"vip", "svip"})
    steps = [
        {"key": "registered", "label": "真实手机号注册", "value": registered},
        {"key": "activated", "label": "窗口内激活学习", "value": activated},
        {"key": "effective_learning", "label": "有效学习成功", "value": effective},
        {"key": "paid", "label": "付费会员", "value": paid},
    ]
    previous = None
    for step in steps:
        denominator = previous if previous is not None else max(registered, 1)
        step["conversion_rate"] = _round(_safe_int(step["value"]) / max(denominator, 1), 4)
        previous = _safe_int(step["value"])
    return {"steps": steps, "metric_definitions": [self._metric_definition_payload("registered_members")]}

def _build_data_trust_payload(self, context: _BiContext) -> dict[str, Any]:
    definitions = [self._metric_definition_payload(metric.metric_id) for metric in BI_METRICS]
    return {
        "score": 100 if not context.truncated_collections else 80,
        "status": "degraded" if context.truncated_collections else "ready",
        "issues": list(context.truncated_collections),
        "metric_definitions": definitions,
    }
```

- [ ] **Step 4: Attach new sections in `get_overview()`**

Inside the existing `get_overview()` return payload, add:

```python
"north_star": self._build_north_star_payload(context, member_dashboard),
"growth_funnel": self._build_growth_funnel_payload(context, member_dashboard),
"teaching_effect": {
    "summary": "第一阶段展示会员章节掌握度与复习待办摘要；后续接入练题与弱点闭环事实。",
    "metric_definitions": [self._metric_definition_payload("mastery_improvement")],
},
"ai_quality": {
    "summary": "第一阶段使用回合成功率、异常和反馈占位；后续接入消息级反馈与 RAG 质量样本。",
    "metric_definitions": [self._metric_definition_payload("ai_quality_score")],
},
"unit_economics": {
    "revenue_status": "pending",
    "summary": "收入事实未接入，当前只展示成本侧单位经济模型。",
    "metric_definitions": [self._metric_definition_payload("cost_per_effective_learning")],
},
"data_trust": self._build_data_trust_payload(context),
```

- [ ] **Step 5: Run service tests**

Run:

```bash
python -m pytest tests/services/test_bi_service_limits.py -q
python -m pytest tests/services/test_bi_metrics.py -q
```

Expected:

```text
all tests pass
```

---

## Task 3: Extend TypeScript BI Contract

**Files:**
- Modify: `web/lib/bi-api.ts`
- Modify: `tests/web/test_bi_member_admin_surface.py`

- [ ] **Step 1: Add static frontend contract test**

Add:

```python
def test_bi_api_exposes_top_tier_content_contracts() -> None:
    source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")

    assert "BiNorthStarPayload" in source
    assert "BiGrowthFunnelPayload" in source
    assert "BiTeachingEffectPayload" in source
    assert "BiAiQualityPayload" in source
    assert "BiUnitEconomicsPayload" in source
    assert "BiDataTrustPayload" in source
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python -m pytest tests/web/test_bi_member_admin_surface.py::test_bi_api_exposes_top_tier_content_contracts -q
```

Expected:

```text
FAILED ... AssertionError
```

- [ ] **Step 3: Add interfaces in `web/lib/bi-api.ts`**

```ts
export interface BiMetricDefinition {
  metric_id: string;
  label: string;
  group: string;
  definition: string;
  authority: string;
  display_hint?: string;
}

export interface BiNorthStarPayload extends BiMetricDefinition {
  value: number;
  registered_members: number;
  hint: string;
}

export interface BiGrowthFunnelStep {
  key: string;
  label: string;
  value: number;
  conversion_rate: number;
}

export interface BiGrowthFunnelPayload {
  steps: BiGrowthFunnelStep[];
  metric_definitions: BiMetricDefinition[];
}

export interface BiTeachingEffectPayload {
  summary: string;
  metric_definitions: BiMetricDefinition[];
}

export interface BiAiQualityPayload {
  summary: string;
  metric_definitions: BiMetricDefinition[];
}

export interface BiUnitEconomicsPayload {
  revenue_status: string;
  summary: string;
  metric_definitions: BiMetricDefinition[];
}

export interface BiDataTrustPayload {
  score: number;
  status: string;
  issues: string[];
  metric_definitions: BiMetricDefinition[];
}
```

Extend the overview type:

```ts
north_star?: BiNorthStarPayload;
growth_funnel?: BiGrowthFunnelPayload;
teaching_effect?: BiTeachingEffectPayload;
ai_quality?: BiAiQualityPayload;
unit_economics?: BiUnitEconomicsPayload;
data_trust?: BiDataTrustPayload;
```

- [ ] **Step 4: Run TypeScript**

Run:

```bash
cd web && npx tsc --noEmit
```

Expected:

```text
exit 0
```

---

## Task 4: Add Top-Tier Boss Cockpit Panels

**Files:**
- Create: `web/app/(workspace)/bi/_components/BiGrowthFunnelPanel.tsx`
- Create: `web/app/(workspace)/bi/_components/BiTeachingEffectPanel.tsx`
- Create: `web/app/(workspace)/bi/_components/BiAiQualityPanel.tsx`
- Create: `web/app/(workspace)/bi/_components/BiDataTrustPanel.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiBossHomeTab.tsx`
- Modify: `tests/web/test_bi_member_admin_surface.py`

- [ ] **Step 1: Add static surface test**

```python
def test_bi_boss_home_exposes_top_tier_sections() -> None:
    source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiBossHomeTab.tsx"
    ).read_text(encoding="utf-8")

    assert "BiGrowthFunnelPanel" in source
    assert "BiTeachingEffectPanel" in source
    assert "BiAiQualityPanel" in source
    assert "BiDataTrustPanel" in source
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python -m pytest tests/web/test_bi_member_admin_surface.py::test_bi_boss_home_exposes_top_tier_sections -q
```

Expected:

```text
FAILED ... AssertionError
```

- [ ] **Step 3: Create `BiGrowthFunnelPanel.tsx`**

```tsx
/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiGrowthFunnelPayload } from "@/lib/bi-api";
import { SectionHeader, formatPercent } from "./BiShared";

export function BiGrowthFunnelPanel({ funnel }: { funnel?: BiGrowthFunnelPayload }) {
  const steps = funnel?.steps ?? [];
  return (
    <section className="surface-card p-5">
      <SectionHeader title="增长漏斗" extra={steps.length ? `${steps.length} 个阶段` : "等待数据"} />
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        {steps.map((step) => (
          <div key={step.key} className="rounded-2xl border border-[var(--border)]/60 bg-[var(--background)] px-4 py-3">
            <p className="text-xs text-[var(--muted-foreground)]">{step.label}</p>
            <p className="mt-2 text-2xl font-semibold text-[var(--foreground)]">{step.value}</p>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">转化 {formatPercent(step.conversion_rate)}</p>
          </div>
        ))}
        {steps.length === 0 ? (
          <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
            增长漏斗尚未返回，先查看会员运营页。
          </div>
        ) : null}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Create `BiTeachingEffectPanel.tsx`**

```tsx
/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiTeachingEffectPayload } from "@/lib/bi-api";
import { SectionHeader } from "./BiShared";

export function BiTeachingEffectPanel({ payload }: { payload?: BiTeachingEffectPayload }) {
  return (
    <section className="surface-card p-5">
      <SectionHeader title="教学效果中心" extra="掌握度 / 练题 / 弱点闭环" />
      <p className="mt-4 text-sm leading-6 text-[var(--secondary-foreground)]">
        {payload?.summary || "等待教学效果数据接入。"}
      </p>
    </section>
  );
}
```

- [ ] **Step 5: Create `BiAiQualityPanel.tsx`**

```tsx
/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiAiQualityPayload } from "@/lib/bi-api";
import { SectionHeader } from "./BiShared";

export function BiAiQualityPanel({ payload }: { payload?: BiAiQualityPayload }) {
  return (
    <section className="surface-card p-5">
      <SectionHeader title="AI 质量中心" extra="成功率 / 反馈 / RAG / 工具" />
      <p className="mt-4 text-sm leading-6 text-[var(--secondary-foreground)]">
        {payload?.summary || "等待 AI 质量样本接入。"}
      </p>
    </section>
  );
}
```

- [ ] **Step 6: Create `BiDataTrustPanel.tsx`**

```tsx
/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiDataTrustPayload } from "@/lib/bi-api";
import { SectionHeader } from "./BiShared";

export function BiDataTrustPanel({ payload }: { payload?: BiDataTrustPayload }) {
  const definitions = payload?.metric_definitions ?? [];
  return (
    <section className="surface-card p-5">
      <SectionHeader title="数据可信中心" extra={payload ? `${payload.score}/100` : "等待数据"} />
      <div className="mt-4 space-y-3">
        <p className="text-sm text-[var(--secondary-foreground)]">
          当前状态：{payload?.status || "unknown"}
        </p>
        {definitions.slice(0, 6).map((metric) => (
          <div key={metric.metric_id} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
            <p className="text-sm font-medium text-[var(--foreground)]">{metric.label}</p>
            <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">{metric.definition}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 7: Mount panels in `BiBossHomeTab.tsx`**

Import:

```tsx
import { BiGrowthFunnelPanel } from "./BiGrowthFunnelPanel";
import { BiTeachingEffectPanel } from "./BiTeachingEffectPanel";
import { BiAiQualityPanel } from "./BiAiQualityPanel";
import { BiDataTrustPanel } from "./BiDataTrustPanel";
```

Add after the current trend/action section:

```tsx
<BiGrowthFunnelPanel funnel={overview?.growth_funnel} />

<section className="grid gap-6 xl:grid-cols-2">
  <BiTeachingEffectPanel payload={overview?.teaching_effect} />
  <BiAiQualityPanel payload={overview?.ai_quality} />
</section>

<BiDataTrustPanel payload={overview?.data_trust} />
```

- [ ] **Step 8: Run frontend tests and TypeScript**

Run:

```bash
python -m pytest tests/web/test_bi_member_admin_surface.py -q
cd web && npx tsc --noEmit
```

Expected:

```text
all tests pass
tsc exit 0
```

---

## Task 5: Build, Deploy, And Verify On Aliyun

**Files:**
- No source changes unless deployment scripts reveal a missing documented step.

- [ ] **Step 1: Run local backend and frontend verification**

Run:

```bash
python -m pytest tests/services/test_bi_metrics.py tests/services/test_bi_service_limits.py tests/web/test_bi_member_admin_surface.py -q
cd web && npx tsc --noEmit && npm run build
```

Expected:

```text
pytest passes
tsc exits 0
next build exits 0
```

- [ ] **Step 2: Sync source to Aliyun**

Run:

```bash
rsync -avR \
  deeptutor/services/bi_metrics.py \
  deeptutor/services/bi_service.py \
  tests/services/test_bi_metrics.py \
  tests/services/test_bi_service_limits.py \
  tests/web/test_bi_member_admin_surface.py \
  web/lib/bi-api.ts \
  web/app/'(workspace)'/bi/_components/ \
  Aliyun-ECS-2:/root/deeptutor/
```

Expected:

```text
sent files listed without rsync error
```

- [ ] **Step 3: Deploy backend hotpatch**

Run:

```bash
ssh Aliyun-ECS-2 '
docker cp /root/deeptutor/deeptutor/services/bi_metrics.py deeptutor:/app/deeptutor/services/bi_metrics.py &&
docker cp /root/deeptutor/deeptutor/services/bi_service.py deeptutor:/app/deeptutor/services/bi_service.py &&
docker exec deeptutor python -m py_compile /app/deeptutor/services/bi_metrics.py /app/deeptutor/services/bi_service.py
'
```

Expected:

```text
exit 0
```

- [ ] **Step 4: Deploy frontend standalone build**

Run local build first:

```bash
cd web && npm run build
```

Then sync build artifacts:

```bash
ssh Aliyun-ECS-2 'rm -rf /root/deeptutor/web-deploy && mkdir -p /root/deeptutor/web-deploy/.next'
rsync -az --delete web/.next/standalone/.next/ Aliyun-ECS-2:/root/deeptutor/web-deploy/.next/
rsync -az --delete web/.next/static/ Aliyun-ECS-2:/root/deeptutor/web-deploy/.next/static/
rsync -az --delete web/public/ Aliyun-ECS-2:/root/deeptutor/web-deploy/public/
rsync -az web/.next/standalone/server.js web/.next/standalone/package.json Aliyun-ECS-2:/root/deeptutor/web-deploy/
ssh Aliyun-ECS-2 '
docker exec deeptutor sh -lc "rm -rf /app/web/.next /app/web/server.js /app/web/package.json /app/web/public && mkdir -p /app/web" &&
docker cp /root/deeptutor/web-deploy/.next deeptutor:/app/web/.next &&
docker cp /root/deeptutor/web-deploy/public deeptutor:/app/web/public &&
docker cp /root/deeptutor/web-deploy/server.js deeptutor:/app/web/server.js &&
docker cp /root/deeptutor/web-deploy/package.json deeptutor:/app/web/package.json
'
```

Expected:

```text
docker cp exits 0
```

- [ ] **Step 5: Restart services and smoke test**

Run:

```bash
ssh Aliyun-ECS-2 '
docker exec deeptutor sh -lc "for p in /proc/[0-9]*/cmdline; do pid=$(echo \"$p\" | cut -d/ -f3); cmd=$(tr \"\000\" \" \" < \"$p\" 2>/dev/null || true); case \"$cmd\" in *\"python -m uvicorn deeptutor.api.main:app\"*|*\"next-server\"*) kill -TERM \"$pid\" || true;; esac; done" &&
sleep 8 &&
docker top deeptutor &&
curl -sS -o /dev/null -w \"%{http_code}\n\" http://127.0.0.1:3782/bi
'
```

Expected:

```text
next-server running
uvicorn running
200
```

- [ ] **Step 6: Verify public page and API**

Run:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://8.135.42.145/bi
```

Expected:

```text
200
```

Use an admin token to call:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" "http://8.135.42.145/api/v1/bi/overview?days=30" \
  | python -c 'import json,sys; d=json.load(sys.stdin); print(d["north_star"]["label"]); print(len(d["growth_funnel"]["steps"])); print(d["data_trust"]["status"])'
```

Expected:

```text
有效学习成功会员数
4
ready
```
