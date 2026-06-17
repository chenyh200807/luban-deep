# BI 三源对账 Harness (P1) + 设计探索 (P4a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 BI 系统性升级设计（`2026-06-12-bi-systematic-upgrade-design.md`）的双线起点——P1 三源对账取证 harness 产出《指标差异报告》+《指标字典》，P4a 产出 3 方向设计对比稿并定稿方向。

**Architecture:** harness 是独立只读取证工具（`scripts/bi_reconciliation/` 包），以 `deeptutor/services/bi_metrics.py` 的 `BI_METRICS` 为指标宇宙，三个取数器（BI API 实拍 / Langfuse Public API / 业务库）输出统一 `SourceReading`，纯函数对账引擎产出五类 verdict，报告层输出 JSON + Markdown 到主 repo `artifacts/`。设计线产出静态 HTML 对比板，不触运行时代码。

**Tech Stack:** Python 3.11+ / httpx / pytest（fixture 驱动，无网络测试）；设计板为纯静态 HTML + ECharts 6 CDN。

**Status:** `Done (2026-06-12)`——P1 Tasks 1-8 与 P4a Tasks 9-10 全部完成；live 取证报告见 artifacts/bi_reconciliation_20260612/，方向定稿见 2026-06-12-bi-vnext-design-direction-decision.md

**硬边界（来自 AGENTS.md 与设计 spec）：**
- harness 全程只读；阿里云上任何写入仅限 `/root/deeptutor` 内（§3.7）。
- harness 不是第四个 authority：它只比对，不修数据。
- artifacts 写主 repo `artifacts/bi_reconciliation_<date>/`，不放临时 worktree。
- 测试不可跳过；每个 task 独立 commit。

---

## File Structure

```
scripts/bi_reconciliation/
  __init__.py          # 包说明
  types.py             # SourceReading / Verdict / MetricMapping 数据类型（frozen dataclass）
  mapping.py           # 18 个指标 → 三源取数方式的声明式映射表（单一映射权威）
  bi_api_source.py     # 取数器①: BI API 实拍（X-Metrics-Token）
  langfuse_source.py   # 取数器②: Langfuse Public API（basic auth）
  business_source.py   # 取数器③: 业务库（Supabase REST 会员 + sqlite 行为库）
  engine.py            # 对账引擎：纯函数，diff + verdict 分类
  report.py            # JSON + Markdown 报告与《指标字典》生成
  run.py               # CLI 入口（python -m scripts.bi_reconciliation.run）
tests/scripts/bi_reconciliation/
  conftest.py          # 共享 fixtures（样例 payload）
  fixtures/            # 实拍脱敏样例 JSON
  test_mapping.py
  test_bi_api_source.py
  test_langfuse_source.py
  test_business_source.py
  test_engine.py
  test_report.py
  test_run_offline.py
docs/bi-cockpit-preview/
  2026-06-12-bi-vnext-design-board.html   # P4a 三方向对比板
docs/plan/会员钱包计费与经营后台/
  2026-06-12-bi-vnext-design-direction-decision.md  # P4a 方向定稿记录
```

---

## P1 数据线

### Task 1: 类型与指标映射表（单一映射权威）

**Files:**
- Create: `scripts/bi_reconciliation/__init__.py`
- Create: `scripts/bi_reconciliation/types.py`
- Create: `scripts/bi_reconciliation/mapping.py`
- Test: `tests/scripts/bi_reconciliation/test_mapping.py`

- [x] **Step 1: Write the failing test**

```python
# tests/scripts/bi_reconciliation/test_mapping.py
from deeptutor.services.bi_metrics import BI_METRICS
from scripts.bi_reconciliation.mapping import METRIC_MAPPINGS, mapping_by_id


def test_mapping_covers_every_registered_metric():
    """指标宇宙 = BI_METRICS；每个注册指标必须有映射声明（哪怕声明为 unmapped）。"""
    mapped_ids = {m.metric_id for m in METRIC_MAPPINGS}
    registry_ids = {m.metric_id for m in BI_METRICS}
    assert mapped_ids == registry_ids


def test_mapping_declares_at_least_bi_source_or_explicit_gap():
    """每个映射要么声明 bi_api 取数路径，要么显式 coverage_gap 备注——不许沉默缺源。"""
    for m in METRIC_MAPPINGS:
        assert m.bi_api_path or m.gap_note, m.metric_id


def test_mapping_by_id_raises_on_unknown():
    import pytest
    with pytest.raises(KeyError):
        mapping_by_id("nonexistent_metric")
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/bi_reconciliation/test_mapping.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.bi_reconciliation'`

- [x] **Step 3: Write minimal implementation**

```python
# scripts/bi_reconciliation/types.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SOURCE_BI_API = "bi_api"
SOURCE_LANGFUSE = "langfuse"
SOURCE_BUSINESS = "business"

VERDICT_CONSISTENT = "consistent"            # 一致
VERDICT_ESTIMATE_CONTAMINATION = "estimate_contamination"  # 估算污染
VERDICT_COVERAGE_GAP = "coverage_gap"        # 覆盖缺口
VERDICT_ATTRIBUTION_ERROR = "attribution_error"  # 归因错误
VERDICT_DEFINITION_MISMATCH = "definition_mismatch"  # 口径分歧
VERDICT_MISSING_SOURCE = "missing_source"    # 该指标某源无法取数（声明性缺口）


@dataclass(frozen=True, slots=True)
class SourceReading:
    metric_id: str
    source: str           # SOURCE_*
    value: float | None   # None = 取数失败/不适用
    window_days: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MetricMapping:
    metric_id: str
    bi_api_path: str = ""        # 形如 "overview:cards[label=有效学习成功会员数].value"
    langfuse_kind: str = ""      # "" | "daily_cost" | "daily_traces" | "daily_observations"
    business_kind: str = ""      # "" | "supabase_members" | "behavior_db" | ...
    tolerance_pct: float = 5.0   # 相对偏差容忍度（按 trust_level 定）
    gap_note: str = ""           # 显式声明的缺源原因


@dataclass(frozen=True, slots=True)
class MetricVerdict:
    metric_id: str
    verdict: str                  # VERDICT_*
    readings: tuple[SourceReading, ...]
    diff_pct: float | None
    detail: str
```

```python
# scripts/bi_reconciliation/mapping.py
"""18 个注册指标 → 三源取数声明。tolerance 按 trust_level：A=1% B=5% C=15%。"""
from __future__ import annotations

from scripts.bi_reconciliation.types import MetricMapping

METRIC_MAPPINGS: tuple[MetricMapping, ...] = (
    MetricMapping("effective_learning_members", bi_api_path="overview:north_star", tolerance_pct=5.0,
                  business_kind="supabase_members"),
    MetricMapping("registered_members", bi_api_path="overview:registered", tolerance_pct=1.0,
                  business_kind="supabase_members"),
    MetricMapping("activated_members", bi_api_path="overview:activated", tolerance_pct=5.0,
                  business_kind="supabase_members"),
    MetricMapping("active_learning_sessions", bi_api_path="overview:sessions", tolerance_pct=5.0,
                  langfuse_kind="daily_traces"),
    MetricMapping("success_turn_rate", bi_api_path="overview:success_rate", tolerance_pct=5.0,
                  langfuse_kind="daily_traces"),
    MetricMapping("avg_session_depth", bi_api_path="overview:depth", tolerance_pct=5.0,
                  gap_note="Langfuse trace 深度口径与会话消息数口径不同，仅双源"),
    MetricMapping("notebook_saves", bi_api_path="overview:notebook", tolerance_pct=5.0,
                  business_kind="behavior_db"),
    MetricMapping("total_cost_usd", bi_api_path="cost:total", tolerance_pct=15.0,
                  langfuse_kind="daily_cost"),
    MetricMapping("renewal_risk_members", bi_api_path="members:renewal_risk", tolerance_pct=5.0,
                  gap_note="风险集合为派生口径，业务库无独立真相，仅记录值"),
    MetricMapping("member_health_score", bi_api_path="overview:member_health", tolerance_pct=15.0,
                  gap_note="复合评分无外部真相源，仅记录值与样本量"),
    MetricMapping("mastery_improvement", bi_api_path="overview:mastery", tolerance_pct=15.0,
                  gap_note="learner_state read model 为唯一源，仅记录"),
    MetricMapping("ai_quality_score", bi_api_path="overview:ai_quality", tolerance_pct=5.0,
                  langfuse_kind="daily_observations"),
    MetricMapping("cost_per_effective_learning", bi_api_path="cost:per_learning", tolerance_pct=15.0,
                  langfuse_kind="daily_cost"),
    MetricMapping("behavior.module.open_count", bi_api_path="", business_kind="behavior_db",
                  gap_note="overview payload 不直接暴露，经 member-ops 聚合；P1 先 DB 侧单源记录"),
    MetricMapping("behavior.learning_report.section_view_count", bi_api_path="",
                  business_kind="behavior_db", gap_note="同上"),
    MetricMapping("behavior.funnel.report_to_training", bi_api_path="",
                  business_kind="behavior_db", gap_note="同上"),
    MetricMapping("behavior.member_ops.report_high_no_action", bi_api_path="",
                  business_kind="behavior_db", gap_note="同上"),
    MetricMapping("data_trust_score", bi_api_path="overview:data_trust", tolerance_pct=1.0,
                  gap_note="自反指标，无外部真相，仅记录"),
)


def mapping_by_id(metric_id: str) -> MetricMapping:
    for m in METRIC_MAPPINGS:
        if m.metric_id == metric_id:
            return m
    raise KeyError(f"Unknown metric mapping: {metric_id}")
```

`scripts/bi_reconciliation/__init__.py` 内容：`"""BI 三源对账取证 harness（只读）。指标宇宙 = deeptutor.services.bi_metrics.BI_METRICS。"""`
另需 `scripts/__init__.py` 与 `tests/scripts/__init__.py`、`tests/scripts/bi_reconciliation/__init__.py` 若不存在则创建空文件。

> 注意：`bi_api_path` 的具体取值在 Task 2 录制真实 payload 后**必须回校**——以实拍 JSON 结构为准修正路径表达式，本表初值是占位锚点，Task 2 Step 4 有显式回校步骤。

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/scripts/bi_reconciliation/test_mapping.py -v`
Expected: 3 PASS

- [x] **Step 5: Commit**

```bash
git add scripts/bi_reconciliation/ tests/scripts/ scripts/__init__.py
git commit -m "feat(bi-recon): P1 对账 harness 类型与指标映射表（指标宇宙=BI_METRICS）"
```

### Task 2: BI API 实拍取数器（先录制后提取）

**Files:**
- Create: `scripts/bi_reconciliation/bi_api_source.py`
- Create: `tests/scripts/bi_reconciliation/fixtures/bi_overview.json`（实拍脱敏）
- Create: `tests/scripts/bi_reconciliation/fixtures/bi_cost.json`
- Create: `tests/scripts/bi_reconciliation/fixtures/bi_members.json`
- Test: `tests/scripts/bi_reconciliation/test_bi_api_source.py`

- [x] **Step 1: 录制真实 payload 作为 fixtures**

用 metrics token 实拍 test2（token 从阿里云 `/root/deeptutor/.env` 的 `DEEPTUTOR_METRICS_TOKEN` 读，或本地 `.env` 已有同值）：

```bash
TOK=$(ssh aliyun "grep '^DEEPTUTOR_METRICS_TOKEN=' /root/deeptutor/.env | cut -d= -f2")
for ep in overview cost members commerce anomalies; do
  curl -s -H "X-Metrics-Token: $TOK" "https://test2.yousenjiaoyu.com/api/v1/bi/$ep?window=7d" \
    > "tests/scripts/bi_reconciliation/fixtures/bi_${ep}.json"
done
```

脱敏：人工检查 fixtures，把任何手机号/姓名字段替换为 `"<redacted>"`（保留结构与数值）。**此步同时回校 Task 1 的 `bi_api_path` 占位锚点**：对照真实 JSON 把 `mapping.py` 路径改为真实字段路径，若某指标在 payload 中根本不存在，把 `bi_api_path` 置空并写 `gap_note`（这本身就是一条 P1 发现）。

- [x] **Step 2: Write the failing test**

```python
# tests/scripts/bi_reconciliation/test_bi_api_source.py
import json
from pathlib import Path

from scripts.bi_reconciliation.bi_api_source import extract_bi_readings
from scripts.bi_reconciliation.mapping import METRIC_MAPPINGS

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_extract_returns_reading_for_every_mapped_metric():
    payloads = {
        "overview": _load("bi_overview.json"),
        "cost": _load("bi_cost.json"),
        "members": _load("bi_members.json"),
    }
    readings = extract_bi_readings(payloads, window_days=7)
    got_ids = {r.metric_id for r in readings}
    expected = {m.metric_id for m in METRIC_MAPPINGS if m.bi_api_path}
    assert got_ids == expected
    for r in readings:
        assert r.source == "bi_api"
        # value 可以是 None（payload 降级），但必须在 meta 里说明
        if r.value is None:
            assert "reason" in r.meta


def test_unregistered_kpi_labels_are_reported():
    """payload 里出现注册表无法解析的 KPI 标签 → 记入 unknown，供 P2 收口。"""
    from scripts.bi_reconciliation.bi_api_source import find_unregistered_labels
    payloads = {"overview": _load("bi_overview.json")}
    unknown = find_unregistered_labels(payloads)
    assert isinstance(unknown, list)  # 内容断言在录制后按真实情况补充为精确断言
```

- [x] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/scripts/bi_reconciliation/test_bi_api_source.py -v`
Expected: FAIL（模块不存在）

- [x] **Step 4: 实现 extractor**

`bi_api_source.py` 提供三个函数（实现细节按录制的真实 payload 结构写，原则如下）：

```python
# scripts/bi_reconciliation/bi_api_source.py
from __future__ import annotations

from typing import Any

import httpx

from deeptutor.services.bi_metrics import BI_METRICS
from scripts.bi_reconciliation.mapping import METRIC_MAPPINGS
from scripts.bi_reconciliation.types import SOURCE_BI_API, SourceReading


def fetch_bi_payloads(base_url: str, metrics_token: str, window: str = "7d") -> dict[str, Any]:
    """在线抓取（live run 用）；离线测试不调用此函数。"""
    headers = {"X-Metrics-Token": metrics_token}
    out: dict[str, Any] = {}
    with httpx.Client(base_url=base_url, headers=headers, timeout=30) as client:
        for ep in ("overview", "cost", "members", "commerce", "anomalies"):
            resp = client.get(f"/api/v1/bi/{ep}", params={"window": window})
            resp.raise_for_status()
            out[ep] = resp.json()
    return out


def extract_bi_readings(payloads: dict[str, Any], window_days: int) -> list[SourceReading]:
    """按 mapping.bi_api_path 从 payload 取值；取不到时 value=None + meta.reason。"""
    readings: list[SourceReading] = []
    for m in METRIC_MAPPINGS:
        if not m.bi_api_path:
            continue
        endpoint, _, locator = m.bi_api_path.partition(":")
        value, reason = _resolve(payloads.get(endpoint), locator)
        meta = {"path": m.bi_api_path}
        if value is None:
            meta["reason"] = reason or "path_not_found"
        readings.append(SourceReading(m.metric_id, SOURCE_BI_API, value, window_days, meta))
    return readings


def find_unregistered_labels(payloads: dict[str, Any]) -> list[str]:
    """收集 payload KPI 标签中无法经 label/label_aliases 解析回注册表的项。"""
    known: set[str] = set()
    for metric in BI_METRICS:
        known.add(metric.label)
        known.update(metric.label_aliases)
    labels = _collect_kpi_labels(payloads)   # 遍历 cards/kpis 数组取 label 字段
    return sorted(set(labels) - known)
```

`_resolve` / `_collect_kpi_labels` 按真实 payload 结构实现（录制后确定，函数必须对缺字段返回 `(None, reason)` 而不是抛异常——降级也是证据）。

- [x] **Step 5: Run tests，全部 PASS 后 Commit**

```bash
python -m pytest tests/scripts/bi_reconciliation/ -v
git add scripts/bi_reconciliation/bi_api_source.py tests/scripts/bi_reconciliation/
git commit -m "feat(bi-recon): BI API 实拍取数器 + 注册表外标签检测（fixtures 实拍脱敏）"
```

### Task 3: Langfuse Public API 取数器

**Files:**
- Create: `scripts/bi_reconciliation/langfuse_source.py`
- Create: `tests/scripts/bi_reconciliation/fixtures/langfuse_daily.json`
- Test: `tests/scripts/bi_reconciliation/test_langfuse_source.py`

说明：`langfuse_adapter.py` 只有写入能力，对账走 Langfuse Public API：`GET {host}/api/public/metrics/daily?fromTimestamp=...&toTimestamp=...`（basic auth = public_key:secret_key），返回逐日 `usage`（按 model 的 token/cost）与 `countTraces/countObservations`。

- [x] **Step 1: Write the failing test**

```python
# tests/scripts/bi_reconciliation/test_langfuse_source.py
import json
from pathlib import Path

from scripts.bi_reconciliation.langfuse_source import readings_from_daily_metrics

FIXTURES = Path(__file__).parent / "fixtures"


def test_daily_cost_aggregation():
    daily = json.loads((FIXTURES / "langfuse_daily.json").read_text())
    readings = readings_from_daily_metrics(daily, window_days=7)
    by_id = {r.metric_id: r for r in readings}
    assert "total_cost_usd" in by_id
    assert by_id["total_cost_usd"].source == "langfuse"
    assert by_id["total_cost_usd"].value is not None
    assert by_id["total_cost_usd"].value >= 0
    # 逐日成本求和 = 总值（自洽断言，录制 fixture 后补精确值）
    expected = sum(d.get("totalCost", 0) for d in daily.get("data", []))
    assert abs(by_id["total_cost_usd"].value - expected) < 1e-9


def test_trace_counts_present():
    daily = json.loads((FIXTURES / "langfuse_daily.json").read_text())
    readings = readings_from_daily_metrics(daily, window_days=7)
    ids = {r.metric_id for r in readings}
    assert "active_learning_sessions" in ids  # daily_traces 映射
```

fixture 先手写最小合法样例（2 天数据，含 `data[].totalCost/countTraces/countObservations/usage[]`），live run 后用真实（脱敏）响应替换并把断言改精确。

- [x] **Step 2: Run test，确认 FAIL**

Run: `python -m pytest tests/scripts/bi_reconciliation/test_langfuse_source.py -v`

- [x] **Step 3: 实现**

```python
# scripts/bi_reconciliation/langfuse_source.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from scripts.bi_reconciliation.mapping import METRIC_MAPPINGS
from scripts.bi_reconciliation.types import SOURCE_LANGFUSE, SourceReading


def fetch_daily_metrics(host: str, public_key: str, secret_key: str, window_days: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    params = {
        "fromTimestamp": (now - timedelta(days=window_days)).isoformat(),
        "toTimestamp": now.isoformat(),
    }
    with httpx.Client(auth=(public_key, secret_key), timeout=30) as client:
        resp = client.get(f"{host.rstrip('/')}/api/public/metrics/daily", params=params)
        resp.raise_for_status()
        return resp.json()


def readings_from_daily_metrics(daily: dict[str, Any], window_days: int) -> list[SourceReading]:
    rows = list(daily.get("data") or [])
    total_cost = sum(float(r.get("totalCost") or 0) for r in rows)
    total_traces = sum(int(r.get("countTraces") or 0) for r in rows)
    total_observations = sum(int(r.get("countObservations") or 0) for r in rows)
    by_kind = {
        "daily_cost": float(total_cost),
        "daily_traces": float(total_traces),
        "daily_observations": float(total_observations),
    }
    readings: list[SourceReading] = []
    for m in METRIC_MAPPINGS:
        if not m.langfuse_kind:
            continue
        readings.append(SourceReading(
            m.metric_id, SOURCE_LANGFUSE, by_kind.get(m.langfuse_kind), window_days,
            {"kind": m.langfuse_kind, "days": len(rows)},
        ))
    return readings
```

注意：`cost_per_effective_learning` / `success_turn_rate` 等**派生指标**在 Langfuse 侧给的是分量（cost、trace 数），engine 对这类指标做"分量级"而非"等值级"比较——见 Task 5 的 `comparison_mode`。若实现时发现等值比较没有意义，在 mapping 中把这些指标的 `langfuse_kind` 改为空 + `gap_note`，宁可显式缺源不可假对齐。

- [x] **Step 4: PASS 后 Commit**

```bash
git add scripts/bi_reconciliation/langfuse_source.py tests/scripts/bi_reconciliation/
git commit -m "feat(bi-recon): Langfuse Public API 取数器（daily metrics 聚合）"
```

### Task 4: 业务库取数器（Supabase 会员 + 行为库）

**Files:**
- Create: `scripts/bi_reconciliation/business_source.py`
- Test: `tests/scripts/bi_reconciliation/test_business_source.py`

- [x] **Step 1: 先侦察真实表结构（只读）**

```bash
grep -rn 'canonical member\|is_test\|member_console' deeptutor/services/member_console*.py | head -20
ls data/runtime/ | grep -i behavior
sqlite3 data/runtime/product_behavior.db '.tables' 2>/dev/null || ssh aliyun "sqlite3 /root/deeptutor/data/runtime/product_behavior.db '.tables'"
```

确认：会员 canonical 口径复用 `member_console` 服务的过滤逻辑（**不要**在 harness 里重新发明"真实会员"定义——直接 import 其过滤常量/函数；若不可 import，在 mapping 的 gap_note 标记口径复制风险）。行为库表名与列以实际 `.schema` 为准。

- [x] **Step 2: Write the failing test（sqlite fixture 内存库）**

```python
# tests/scripts/bi_reconciliation/test_business_source.py
import sqlite3

from scripts.bi_reconciliation.business_source import behavior_readings_from_db


def _mk_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    # 表结构以 Step 1 侦察到的真实 schema 为准；此处按真实 DDL 建最小表
    conn.execute(
        "CREATE TABLE product_behavior_events ("
        " event_id TEXT, event_type TEXT, user_id TEXT, visit_id TEXT,"
        " occurred_at TEXT)"
    )
    rows = [
        ("e1", "module.open", "u1", "v1", "2026-06-10T01:00:00Z"),
        ("e2", "module.open", "u1", "v1", "2026-06-10T02:00:00Z"),
        ("e3", "learning_report.section_view", "u2", "v2", "2026-06-11T01:00:00Z"),
    ]
    conn.executemany("INSERT INTO product_behavior_events VALUES (?,?,?,?,?)", rows)
    return conn


def test_behavior_counts():
    readings = behavior_readings_from_db(_mk_db(), window_days=7, now_iso="2026-06-12T00:00:00Z")
    by_id = {r.metric_id: r.value for r in readings}
    assert by_id["behavior.module.open_count"] == 2
    assert by_id["behavior.learning_report.section_view_count"] == 1
```

（event_type 取值在 Step 1 侦察后改为真实值；测试数据必须模拟真实 shape，参考记忆教训"测试别手搓假形状"——以真实 DDL/事件名为准。）

- [x] **Step 3: 实现 `business_source.py`**

```python
# scripts/bi_reconciliation/business_source.py
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

import httpx

from scripts.bi_reconciliation.types import SOURCE_BUSINESS, SourceReading

# event_type 常量以 Step 1 侦察的真实 catalog 为准回填
_BEHAVIOR_COUNTERS = {
    "behavior.module.open_count": "module.open",
    "behavior.learning_report.section_view_count": "learning_report.section_view",
}


def behavior_readings_from_db(conn: sqlite3.Connection, window_days: int, now_iso: str) -> list[SourceReading]:
    cutoff = (datetime.fromisoformat(now_iso.replace("Z", "+00:00")) - timedelta(days=window_days)).isoformat()
    out: list[SourceReading] = []
    for metric_id, event_type in _BEHAVIOR_COUNTERS.items():
        row = conn.execute(
            "SELECT COUNT(*) FROM product_behavior_events WHERE event_type = ? AND occurred_at >= ?",
            (event_type, cutoff),
        ).fetchone()
        out.append(SourceReading(metric_id, SOURCE_BUSINESS, float(row[0]), window_days,
                                 {"event_type": event_type}))
    return out


def member_readings_from_supabase(rest_url: str, service_key: str, window_days: int) -> list[SourceReading]:
    """Supabase REST 只读 count 查询；过滤口径必须与 member_console canonical 一致。
    实现时 import member_console 的过滤定义；无法 import 时复制 SQL 并在 meta 标记 copied_definition=True。"""
    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}", "Prefer": "count=exact"}
    with httpx.Client(headers=headers, timeout=30) as client:
        resp = client.get(f"{rest_url.rstrip('/')}/rest/v1/<members_table>",
                          params={"select": "id", "limit": "1"})
        resp.raise_for_status()
        total = int(resp.headers.get("content-range", "0/0").split("/")[-1])
    return [SourceReading("registered_members", SOURCE_BUSINESS, float(total), window_days,
                          {"definition": "supabase canonical members"})]
```

`<members_table>` 与过滤条件在 Step 1 侦察后回填真实表名/filters（测试用 monkeypatch 替换 httpx 响应，断言 count 解析正确）。

- [x] **Step 4: PASS 后 Commit**

```bash
git add scripts/bi_reconciliation/business_source.py tests/scripts/bi_reconciliation/
git commit -m "feat(bi-recon): 业务库取数器（行为 sqlite + Supabase 会员 count）"
```

### Task 5: 对账引擎（纯函数）

**Files:**
- Create: `scripts/bi_reconciliation/engine.py`
- Test: `tests/scripts/bi_reconciliation/test_engine.py`

- [x] **Step 1: Write the failing tests（verdict 分类规则全覆盖）**

```python
# tests/scripts/bi_reconciliation/test_engine.py
from scripts.bi_reconciliation.engine import reconcile_metric
from scripts.bi_reconciliation.types import (
    SOURCE_BI_API, SOURCE_BUSINESS, SOURCE_LANGFUSE,
    VERDICT_CONSISTENT, VERDICT_COVERAGE_GAP, VERDICT_DEFINITION_MISMATCH,
    VERDICT_ESTIMATE_CONTAMINATION, VERDICT_MISSING_SOURCE,
    MetricMapping, SourceReading,
)


def _r(source, value, **meta):
    return SourceReading("m", source, value, 7, meta)


M = MetricMapping("m", bi_api_path="overview:x", langfuse_kind="daily_cost", tolerance_pct=5.0)


def test_consistent_within_tolerance():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, 100.0), _r(SOURCE_LANGFUSE, 103.0)])
    assert v.verdict == VERDICT_CONSISTENT
    assert v.diff_pct is not None and v.diff_pct < 5.0


def test_estimate_contamination_when_meta_says_estimated():
    v = reconcile_metric(M, [
        _r(SOURCE_BI_API, 100.0, usage_source_mix={"estimated_ratio": 0.4}),
        _r(SOURCE_LANGFUSE, 130.0),
    ])
    assert v.verdict == VERDICT_ESTIMATE_CONTAMINATION


def test_coverage_gap_when_bi_lower_beyond_tolerance():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, 50.0), _r(SOURCE_LANGFUSE, 100.0)])
    assert v.verdict == VERDICT_COVERAGE_GAP  # BI 显著少于真相源 → 采集缺口


def test_definition_mismatch_when_bi_higher_beyond_tolerance():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, 200.0), _r(SOURCE_LANGFUSE, 100.0)])
    assert v.verdict == VERDICT_DEFINITION_MISMATCH  # BI 多于真相源 → 口径或归因问题


def test_missing_source_when_only_one_reading():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, 100.0)])
    assert v.verdict == VERDICT_MISSING_SOURCE


def test_none_values_treated_as_missing():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, None), _r(SOURCE_LANGFUSE, 100.0)])
    assert v.verdict == VERDICT_MISSING_SOURCE
    assert "bi_api" in v.detail
```

- [x] **Step 2: FAIL 确认 → Step 3: 实现**

```python
# scripts/bi_reconciliation/engine.py
from __future__ import annotations

from scripts.bi_reconciliation.types import (
    SOURCE_BI_API,
    VERDICT_CONSISTENT, VERDICT_COVERAGE_GAP, VERDICT_DEFINITION_MISMATCH,
    VERDICT_ESTIMATE_CONTAMINATION, VERDICT_MISSING_SOURCE,
    MetricMapping, MetricVerdict, SourceReading,
)


def reconcile_metric(mapping: MetricMapping, readings: list[SourceReading]) -> MetricVerdict:
    valid = [r for r in readings if r.value is not None]
    bi = next((r for r in valid if r.source == SOURCE_BI_API), None)
    others = [r for r in valid if r.source != SOURCE_BI_API]
    if bi is None or not others:
        missing = [r.source for r in readings if r.value is None] or ["truth_source"]
        return MetricVerdict(mapping.metric_id, VERDICT_MISSING_SOURCE, tuple(readings), None,
                             f"缺有效读数: {','.join(missing)}")
    truth = others[0]  # 优先 langfuse / business 的首个有效真相源
    base = max(abs(truth.value), 1e-9)
    diff_pct = abs(bi.value - truth.value) / base * 100
    if diff_pct <= mapping.tolerance_pct:
        return MetricVerdict(mapping.metric_id, VERDICT_CONSISTENT, tuple(readings), diff_pct, "一致")
    mix = bi.meta.get("usage_source_mix") or {}
    if float(mix.get("estimated_ratio") or 0) > 0.1:
        return MetricVerdict(mapping.metric_id, VERDICT_ESTIMATE_CONTAMINATION, tuple(readings), diff_pct,
                             f"BI 值含 {mix['estimated_ratio']:.0%} 估算分量且超容忍度")
    if bi.value < truth.value:
        return MetricVerdict(mapping.metric_id, VERDICT_COVERAGE_GAP, tuple(readings), diff_pct,
                             "BI 低于真相源——疑似采集缺口")
    return MetricVerdict(mapping.metric_id, VERDICT_DEFINITION_MISMATCH, tuple(readings), diff_pct,
                         "BI 高于真相源——疑似口径分歧或归因错误")
```

（`attribution_error` verdict 由人工在报告复核时从 `definition_mismatch` 升级标注——自动规则无法区分口径与归因，引擎不假装能。）

- [x] **Step 4: PASS 后 Commit**

```bash
git add scripts/bi_reconciliation/engine.py tests/scripts/bi_reconciliation/test_engine.py
git commit -m "feat(bi-recon): 对账引擎——五类 verdict 自动分类，归因升级留人工"
```

### Task 6: 报告 + 指标字典生成

**Files:**
- Create: `scripts/bi_reconciliation/report.py`
- Test: `tests/scripts/bi_reconciliation/test_report.py`

- [x] **Step 1: failing test**

```python
# tests/scripts/bi_reconciliation/test_report.py
from scripts.bi_reconciliation.report import build_report, render_markdown
from scripts.bi_reconciliation.types import MetricVerdict, SourceReading


def _verdict(mid, verdict, diff):
    return MetricVerdict(mid, verdict, (SourceReading(mid, "bi_api", 1.0, 7),), diff, "x")


def test_report_json_shape_and_summary():
    vs = [_verdict("a", "consistent", 1.0), _verdict("b", "coverage_gap", 50.0)]
    rep = build_report(vs, window_days=7, generated_at="2026-06-12T00:00:00Z",
                       unregistered_labels=["神秘KPI"])
    assert rep["summary"]["total"] == 2
    assert rep["summary"]["by_verdict"]["coverage_gap"] == 1
    assert rep["unregistered_labels"] == ["神秘KPI"]
    md = render_markdown(rep)
    assert "coverage_gap" in md and "神秘KPI" in md


def test_metric_dictionary_includes_registry_fields():
    from scripts.bi_reconciliation.report import build_metric_dictionary
    d = build_metric_dictionary()
    assert len(d) == 18  # = len(BI_METRICS)
    sample = next(x for x in d if x["metric_id"] == "total_cost_usd")
    assert sample["trust_level"] == "C"
    assert sample["mapping"]["langfuse_kind"] == "daily_cost"
```

- [x] **Step 2: FAIL → Step 3: 实现**

`build_report(verdicts, window_days, generated_at, unregistered_labels)` 返回 dict：`{schema_version: 1, generated_at, window_days, summary: {total, by_verdict}, metrics: [verdict 序列化], unregistered_labels}`。`render_markdown` 输出按 verdict 分组的表格（指标 / BI 值 / 真相值 / diff% / verdict / detail）。`build_metric_dictionary()` 联合 `BI_METRICS` 与 `METRIC_MAPPINGS` 输出字典数组（registry 全字段 + mapping 全字段）。`generated_at` 由调用方传入（不在库内取 `datetime.now`，保持纯函数可测）。

- [x] **Step 4: PASS 后 Commit**

```bash
git add scripts/bi_reconciliation/report.py tests/scripts/bi_reconciliation/test_report.py
git commit -m "feat(bi-recon): 差异报告(JSON+MD)与指标字典生成器"
```

### Task 7: CLI 入口与离线冒烟

**Files:**
- Create: `scripts/bi_reconciliation/run.py`
- Test: `tests/scripts/bi_reconciliation/test_run_offline.py`

- [x] **Step 1: failing test（离线模式端到端）**

```python
# tests/scripts/bi_reconciliation/test_run_offline.py
import json
from pathlib import Path

from scripts.bi_reconciliation.run import run_offline

FIXTURES = Path(__file__).parent / "fixtures"


def test_run_offline_produces_report(tmp_path):
    out_dir = run_offline(fixtures_dir=FIXTURES, out_root=tmp_path, window_days=7,
                          generated_at="2026-06-12T00:00:00Z")
    report = json.loads((out_dir / "reconciliation_report.json").read_text())
    assert report["summary"]["total"] > 0
    assert (out_dir / "reconciliation_report.md").exists()
    assert (out_dir / "metric_dictionary.json").exists()
```

- [x] **Step 2: FAIL → Step 3: 实现 run.py**

`run_offline(fixtures_dir, out_root, window_days, generated_at)`：读 fixtures → 三源 extract（业务库源在离线模式跳过并记 missing）→ engine → report 落盘 `out_root/bi_reconciliation_<date>/`。
`main(argv)`：argparse，`--mode live|offline`、`--bi-base-url`、`--window-days`、`--out`；live 模式从环境读 `DEEPTUTOR_METRICS_TOKEN` / `LANGFUSE_BASE_URL|LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`（缺哪个就跳过对应源并在报告标 missing_source，**不**硬失败——部分证据好过零证据）。

- [x] **Step 4: PASS 后 Commit**

```bash
git add scripts/bi_reconciliation/run.py tests/scripts/bi_reconciliation/test_run_offline.py
git commit -m "feat(bi-recon): CLI 入口（live/offline 双模式）与离线端到端冒烟"
```

### Task 8: 阿里云 live run + 差异报告定稿

**Files:**
- Create: `artifacts/bi_reconciliation_20260612/`（运行产物）

- [x] **Step 1: 全量测试过门**

```bash
python -m pytest tests/scripts/bi_reconciliation/ -v   # 全 PASS
```

- [x] **Step 2: live run（凭据在阿里云，远端跑或本地带 env 跑）**

优先本地跑（出公网 BI API + Langfuse 若公网可达）；Langfuse 仅内网时把仓库当前分支同步到阿里云 `/root/deeptutor` 内的副本运行，产物写 `/root/deeptutor/artifacts/` 后 `scp` 回本地主 repo `artifacts/`（写边界合规）。

```bash
python -m scripts.bi_reconciliation.run --mode live \
  --bi-base-url https://test2.yousenjiaoyu.com --window-days 7 --out artifacts/
```

- [x] **Step 3: 人工复核**

对每条 `definition_mismatch` 判断是否实为 `attribution_error`，在报告 md 的复核栏标注；`unregistered_labels` 列表转为 P2 收口任务清单。

- [x] **Step 4: Commit artifacts + 回写设计 spec 状态**

```bash
git add artifacts/bi_reconciliation_20260612/
git commit -m "docs(bi-recon): P1 三源对账差异报告 + 指标字典 v1（live 取证）"
```

并把本计划与设计 spec 的 P1 小节状态更新为 `Evidence captured`。

---

## P4a 设计线（与 P1 并行，互不依赖）

### Task 9: 三方向设计对比板

**Files:**
- Create: `docs/bi-cockpit-preview/2026-06-12-bi-vnext-design-board.html`

- [x] **Step 1: 写设计简报（板内首屏）**：现状（暖陶土橙深色驾驶舱）、升级主轴四项（全局控制层 / 可信度即 UI / 下钻一致性 / 性能）、对标（Grafana 信息密度、Lightdash 语义层暴露、顶级驾驶舱叙事性）。
- [x] **Step 2: 在同一 HTML 内做 3 个方向的 overview tab 高保真静态稿**（ECharts 6 CDN 真图表 + 假数据明确水印"DESIGN MOCK"）：
  - **方向 A「指挥舱进化」**：保留暖陶土橙，增加全局时间/对比控制条 + 每 KPI 可信度徽标（trust_level/新鲜度/measured-estimated 分量条）+ 统一下钻面包屑。
  - **方向 B「语义层前置」**：冷暖双主题，左侧常驻指标字典抽屉（点任何数字看口径/源/公式），表格密度优先，弱化大屏叙事。
  - **方向 C「混合分层」**：默认 A 的大屏叙事，hover/点击进入 B 的语义层细节；可信度用边框色温编码。
- [x] **Step 3: 浏览器自查**（起本地静态服务→截图→立即关，遵守内存护栏；纯静态文件可直接 `file://` 打开，不起 dev server）。
- [x] **Step 4: Commit**

```bash
git add docs/bi-cockpit-preview/2026-06-12-bi-vnext-design-board.html
git commit -m "design(bi): vNext 三方向对比板（指挥舱进化/语义层前置/混合分层）"
```

### Task 10: 方向定稿记录

**Files:**
- Create: `docs/plan/会员钱包计费与经营后台/2026-06-12-bi-vnext-design-direction-decision.md`

- [x] **Step 1:** 按四条标准打分定稿（数据可信度表达力 / 与指标契约的耦合度 / 实现成本 / 与既有品牌的连续性），写明推荐方向与理由、落选方向保留要素。已获用户全权授权，由执行者定稿；用户可后续否决。
- [x] **Step 2:** 在 `docs/plan/INDEX.md` §5.5 表登记两份 P4a 产物。
- [x] **Step 3: Commit**

```bash
git add 'docs/plan/会员钱包计费与经营后台/2026-06-12-bi-vnext-design-direction-decision.md' docs/plan/INDEX.md
git commit -m "design(bi): vNext 设计方向定稿记录"
```

---

## 后续（不在本计划内，依赖 P1 证据）

P2 治理重建（契约扩建 + bi_service 拆包 + 缺口修复）、P3 双轨常态化、P4b/c 设计实现——在 P1 报告与 P4a 定稿后另立执行计划。

## Self-Review 记录

- Spec 覆盖：设计 spec P1 全部要件（三源/verdict 五类/字典/artifacts 落点/只读边界）均有对应 task；P4a 对应 spec 的设计探索段。✔
- 占位符：mapping 初值与 `<members_table>` 为**显式回校锚点**，配有回校步骤（Task 2 Step 1、Task 4 Step 1/3），非悬空 TBD。✔
- 类型一致性：`SourceReading/MetricMapping/MetricVerdict` 在 Task 1 定义，后续 task 签名一致。✔
