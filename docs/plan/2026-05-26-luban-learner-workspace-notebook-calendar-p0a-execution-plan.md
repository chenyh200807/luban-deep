# 鲁班学情工作台 P0A 执行计划（durable store 先行）

> **For agentic workers:** REQUIRED SUB-SKILL: 用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现本计划。步骤用 `- [ ]` 复选框跟踪。
>
> **上游 PRD（单一权威，先读）：** [2026-05-26-luban-learner-workspace-notebook-calendar-prd.md](2026-05-26-luban-learner-workspace-notebook-calendar-prd.md)（Proposed v0.4）。本执行计划只把 PRD 的 P0A 落成可执行任务，**不得**扩大 PRD 边界；任何与 PRD 冲突处以 PRD 为准。

- 状态：Proposed v0.1
- 日期：2026-05-26
- 归属主线：Learner State / Evidence-first Memory / 鲁班智考个性化教学
- 产品表面：鲁班智考微信小程序、佑森融合包
- 决策前提：用户已拍板 **durable store 先行**（notebook 卡片做 Supabase durable store + RLS + owner-scope + 乐观并发，不走“单端内测”兜底）。

---

**Goal:** 把“答疑/批改 -> 一键收藏 -> source-linked 学习卡片 -> 今日任务 -> 练一道/测一下 -> evidence 回流”最小闭环落地，且手动收藏既不污染 learner-state（summary / compiled-truth / overlay / recall），又有生产级多端持久化。

**Architecture:** 新增一个 owner-scoped 的 `learner_notebook_cards` Supabase 表（仿 `learner_mistake_book_items`，per-row、RLS、乐观并发），由新 fat-skill 权威 `NotebookCardService` 唯一负责卡片的写/读/删。workspace 卡片**不**经过既有 `NotebookManager._writeback_learner_state()` 重路径，因此 `refresh_from_turn()`（summary LLM 改写）、`patch_overlay()`（overlay 污染）一次性被收权；卡片只产出一条带 `source_label="student_note"`、低权重的 recall 事件。学情首页只扩展既有 `build_learning_report_read_model()`，不新增首页接口、不新增 planner CRUD。

**Tech Stack:** Python 3 / FastAPI、Supabase PostgREST（httpx 同步客户端，仿 `SupabaseMistakeBookStore`）、pytest；微信小程序（`wx_miniprogram/`）+ 佑森融合包（`yousenwebview/packageDeeptutor/`）+ 微信开发者工具手工回归。

---

## 0. 单一 authority 与非目标（硬约束，逐条对齐 PRD §5 / §11 / §12）

**本计划维护的一等业务事实与唯一 authority：**

| 业务事实 | 唯一 authority（本计划） | 写 / 读路径 |
| --- | --- | --- |
| 用户手动收藏卡片（含 AI 增强内容、用户决策状态） | 新 `NotebookCardService` + `learner_notebook_cards` 表 | 写：`NotebookCardService.save_card/update_card/delete_card`；读：`list_cards` + learning-report read model 投影 |
| 学员掌握/薄弱/趋势 | `learner_memory_events.memory_kind=learning_evidence` + `learning_synthesis`（**不改**） | 卡片只引用 `evidence_event_ids`，不写不改 |
| 下一步训练处方 | `training_intent`（**不改**） | 今日任务只读投影 |
| 学情首页 / 工作台 / 今日任务 view model | `build_learning_report_read_model()`（**只扩展**） | 新增 `note_assets` + `today_tasks` 字段 |
| learner summary / recall context | `LearnerStateService`（**收权**） | 卡片只允许 `record_notebook_writeback`（轻事件），**禁止** `refresh_from_turn` / `patch_overlay` |

**非目标（P0A 不做，做了即越界）：**

- 不新增 `GET /api/v1/learner-workspace/home`、不新增 `POST/PATCH /api/v1/planner/tasks`、不新增 `POST /api/v1/notebook/cards` writer。
- 不把 `learning_plans` 改成日历任务；不做用户自建/延期/完成任务（推 P0B）。
- 不动既有 `NotebookManager._writeback_learner_state()` 对 legacy 记录（solve / guided_learning / co_writer / markdown 导入）的行为。
- 不扩 `RecordType` 枚举（卡片类型走 `metadata.card_type`）。
- 不新增聊天 WebSocket；不让前端计算 mastery/错因/处方。
- 不在 P0A 实现独立 GBrain 运行时、第二套 RAG、第二套 learner memory、复杂 graph UI、nightly auto-fix 或 Learning Brain eval harness。

## 0.1 GBrain / Obsidian 分层在 P0A 的落点

P0A 只实现 Obsidian Wiki 启发的“用户可控学习资产层”：source-linked 卡片、用户确认/编辑/删除、笔记转训练、今日任务只读投影。

GBrain 启发的“学习事实引擎层”在 P0A 只做预留，不做新 authority：

| 能力 | P0A 做什么 | P0A 不做什么 |
| --- | --- | --- |
| Brain-first lookup | 卡片和今日任务保留 `source_ref`、`evidence_event_ids`、`why`、`reason_code`，方便后续 learning-report / RAG 读取 | 不把 compiled truth 接入所有回答，不改变标准答案排序。 |
| Claim lifecycle | 不让手动笔记写 `learning_evidence`，保留 `user_control_status`、`mastery_effect=none` | 不在卡片服务里计算 `L0/L1/L2/stale`。 |
| Typed graph | 卡片 metadata 保留 `linked_knowledge_points`、`linked_error_patterns`、`evidence_event_ids` | 不建新图数据库，不展示复杂知识大图。 |
| Provenance | 证据抽屉只展示已有 source ref / attempt detail | 不让 AI enhancer 自行编造 supporting evidence。 |
| Nightly lint | 不阻塞 P0A；只确保卡片数据有足够字段供后续 lint 读取 | 不做自动作废、自动修复、自动重写画像。 |
| Eval harness | P0A 指标只覆盖保存、行动转化、summary 污染、证据覆盖 | 不把画像准确率、stale claim rate 作为 P0A release blocker。 |

后续 P1/P2 要把这些能力接回既有 `LearnerStateService`、`learning_synthesis`、`RAGService` 和 `GET /api/v1/mobile/learning-report`，不得把本计划里的 `NotebookCardService` 扩张成学习事实 authority。

## 1. 相关代码入口（实施前先读，行号以当前 main 为准）

- `deeptutor/services/notebook/service.py:242` —`_writeback_learner_state`（**收权对象**：272 轻 / 285 `refresh_from_turn` 重 / 314 `patch_overlay` 重）；`:440` `add_record`；`:492` 触发 writeback 的分支。
- `deeptutor/api/routers/notebook.py:99` `_stream_add_record_with_summary`、`:290` `POST /add_record`（卡片入口，复用，不新增 cards writer）。
- `deeptutor/services/learner_state/service.py:1340` `record_notebook_writeback`（**已存在的轻路径**，卡片唯一允许的写回）、`:1499` `refresh_from_turn`（重，卡片禁止）、`:723` `append_memory_event`、`build_context_candidates`（recall 注入，需打 `student_note` 标签 + 降权）。
- `deeptutor/services/learner_state/mistake_book.py:40/107` `InMemoryMistakeBookStore` / `SupabaseMistakeBookStore`（**durable store 模板**）。
- `supabase/migrations/20260521000100_learner_mistake_book_items.sql`（**迁移 + RLS 模板**）。
- `deeptutor/services/learner_state/learning_report_read_model.py`（`build_learning_report_read_model`，**唯一首页扩展点**）；`deeptutor/api/routers/mobile.py`（`GET /api/v1/mobile/learning-report` 路由）。
- `deeptutor/services/assessment/writeback.py`（probe 写 evidence 时 `measurement_confidence` 范式）。
- `yousenwebview/packageDeeptutor/`、`wx_miniprogram/`（双端 UI + 微信开发者工具回归）。

---

## Phase 0：现实校验 + 行为基线（不改产品行为）

目的：用 characterization test 固化“当前手动收藏会污染 summary/overlay”这一事实，作为收权前的红线证据；并锁定 gating key。

### Task 0.1：写 characterization 测试，证明当前重路径污染

**Files:**
- Test: `tests/services/test_notebook_writeback_pollution_baseline.py`（Create）

- [ ] **Step 1: 写测试，断言当前 `add_record`（带 user_id）会触发 summary 改写 + overlay patch**

```python
import asyncio
from unittest.mock import patch

from deeptutor.services.notebook.service import NotebookManager, RecordType


def test_baseline_manual_save_currently_triggers_refresh_from_turn(tmp_path, monkeypatch):
    """RED-LINE BASELINE: 证明收权前手动收藏会调用 refresh_from_turn。
    Phase 2 收权后本测试将被替换为断言『不调用』。"""
    calls = {"refresh": 0, "overlay": 0}

    async def _fake_refresh(**_kwargs):
        calls["refresh"] += 1

    class _FakeLearner:
        async def record_notebook_writeback(self, **_kwargs):
            return None
        refresh_from_turn = staticmethod(_fake_refresh)

    manager = NotebookManager(base_dir=tmp_path)
    monkeypatch.setattr(
        "deeptutor.services.notebook.service.get_learner_state_service",
        lambda: _FakeLearner(),
    )
    manager.create_notebook("默认", owner_key="ok_user_001")
    nb_id = manager.list_notebooks(owner_key="ok_user_001")[0]["id"]

    manager.add_record(
        notebook_ids=[nb_id],
        record_type=RecordType.CHAT,
        title="专项施工方案审批流程",
        user_query="这个流程我记不住",
        output="编制->审核->审批->论证->交底->验收",
        metadata={"user_id": "user_001", "operation": "add"},
        user_id="user_001",
        owner_key="ok_user_001",
    )
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.05))
    assert calls["refresh"] >= 1  # 基线：当前确实走重路径
```

- [ ] **Step 2: 运行确认通过（证明污染真实存在）**

Run: `pytest tests/services/test_notebook_writeback_pollution_baseline.py -v`
Expected: PASS（`calls["refresh"] >= 1`）。若 FAIL，说明 main 行为已变，停止并复核 `service.py:285`。

- [ ] **Step 3: Commit**

```bash
git add tests/services/test_notebook_writeback_pollution_baseline.py
git commit -m "test: characterize current notebook writeback summary pollution (P0A baseline)"
```

### Task 0.2：锁定 gating key 与契约说明

**Files:**
- Modify: `docs/plan/2026-05-26-luban-learner-workspace-notebook-calendar-prd.md`（在 §5 禁止模式补一行 overlay）

- [ ] **Step 1: 在 PRD §5 禁止模式补 overlay 泄漏（评审新发现，PRD v0.3 漏列）**

在 `notebook_* -> compiled_learning_truth` 一行后追加：

```markdown
- `manual_note -> bot_learner_overlay.working_memory_projection`
```

并在 §15 P0A 技术验收追加：

```markdown
- 保存手动卡片后，Bot-Learner Overlay 的 `working_memory_projection` / `local_notebook_scope_refs` 不被该卡片写入。
```

- [ ] **Step 2: 决定 gating key = `metadata.card_type` 存在性**

记录决策（写入本计划下方“决策记录”）：凡 `metadata.card_type` 命中 `{scoring_card, error_pattern_note, review_note, manual_note}` 的写入，走新 `NotebookCardService`（durable + 轻写回）；其余（legacy solve/guided_learning/markdown 导入）维持 `NotebookManager` 现状不变。

- [ ] **Step 3: Commit**

```bash
git add docs/plan/2026-05-26-luban-learner-workspace-notebook-calendar-prd.md
git commit -m "docs(prd): add overlay pollution forbidden-pattern + card_type gating key"
```

---

## Phase 1：durable `learner_notebook_cards` 表 + RLS 迁移 + store

### Task 1.1：迁移文件（表 + 索引 + RLS，仿 mistake_book）

**Files:**
- Create: `supabase/migrations/20260526000100_learner_notebook_cards.sql`

- [ ] **Step 1: 写迁移（owner-scoped、乐观并发列 `version`、唯一键 `(user_id, note_id)`）**

```sql
create table if not exists public.learner_notebook_cards (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  note_id text not null,
  subject_id text not null default '',
  source_bot_id text not null default '',
  card_type text not null default 'manual_note',
  source_type text not null default 'manual',
  source_ref jsonb not null default '{}'::jsonb,
  evidence_event_ids jsonb not null default '[]'::jsonb,
  title text default '',
  raw_user_content text default '',
  ai_enhanced_content jsonb not null default '{}'::jsonb,
  linked_knowledge_points jsonb not null default '[]'::jsonb,
  linked_error_patterns jsonb not null default '[]'::jsonb,
  user_control_status text not null default 'confirmed',
  use_for_personalization boolean not null default true,
  mastery_effect text not null default 'none',
  version integer not null default 1,
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, note_id)
);

create index if not exists idx_learner_notebook_cards_user_updated
  on public.learner_notebook_cards(user_id, updated_at desc)
  where archived_at is null;

create index if not exists idx_learner_notebook_cards_user_subject_type
  on public.learner_notebook_cards(user_id, subject_id, card_type, updated_at desc)
  where archived_at is null;

alter table public.learner_notebook_cards enable row level security;

create policy "learner_notebook_cards_owner_select"
  on public.learner_notebook_cards
  for select using (auth.uid()::text = user_id);

create policy "learner_notebook_cards_owner_insert"
  on public.learner_notebook_cards
  for insert with check (auth.uid()::text = user_id);

create policy "learner_notebook_cards_owner_update"
  on public.learner_notebook_cards
  for update using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

create policy "learner_notebook_cards_owner_delete"
  on public.learner_notebook_cards
  for delete using (auth.uid()::text = user_id);
```

- [ ] **Step 2: 静态校验唯一时间戳前缀，无重复（项目迁移纪律）**

Run: `ls supabase/migrations | grep 20260526000100`
Expected: 仅 1 个文件；前缀大于现有最大 `20260525130000`。

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260526000100_learner_notebook_cards.sql
git commit -m "feat(db): add learner_notebook_cards table with owner RLS + optimistic version"
```

> ⚠️ 迁移**不自动应用**（见项目部署事实）；生产 apply 是独立 release gate，不在本代码 PR 内执行。

### Task 1.2：store 三态实现（InMemory / Supabase / Unavailable，仿 mistake_book）

**Files:**
- Create: `deeptutor/services/notebook_card/store.py`
- Test: `tests/services/notebook_card/test_store.py`

- [ ] **Step 1: 写 InMemory store 的乐观并发测试（先 RED）**

```python
import pytest
from deeptutor.services.notebook_card.store import InMemoryNotebookCardStore, OptimisticConcurrencyError


def _row(note_id="note_1", version=1):
    return {"user_id": "u1", "note_id": note_id, "title": "t", "version": version}


def test_upsert_then_get_roundtrip():
    store = InMemoryNotebookCardStore()
    store.upsert_card(_row())
    got = store.get_card("u1", "note_1")
    assert got["title"] == "t" and got["version"] == 1


def test_update_with_stale_version_raises():
    store = InMemoryNotebookCardStore()
    store.upsert_card(_row(version=1))
    with pytest.raises(OptimisticConcurrencyError):
        store.update_card("u1", "note_1", {"title": "new"}, expected_version=99)


def test_update_bumps_version():
    store = InMemoryNotebookCardStore()
    store.upsert_card(_row(version=1))
    updated = store.update_card("u1", "note_1", {"title": "new"}, expected_version=1)
    assert updated["title"] == "new" and updated["version"] == 2


def test_list_excludes_archived_and_scopes_by_user():
    store = InMemoryNotebookCardStore()
    store.upsert_card(_row(note_id="a"))
    store.upsert_card({"user_id": "u2", "note_id": "b", "version": 1})
    store.update_card("u1", "a", {"archived_at": "2026-05-26T00:00:00+08:00"}, expected_version=1)
    assert store.list_cards("u1") == []
    assert len(store.list_cards("u2")) == 1
```

- [ ] **Step 2: 运行确认 FAIL**

Run: `pytest tests/services/notebook_card/test_store.py -v`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 store（InMemory + Supabase + Unavailable）**

```python
from __future__ import annotations

import os
from typing import Any, Protocol

import httpx


class OptimisticConcurrencyError(RuntimeError):
    """expected_version 与当前行 version 不一致。"""


class NotebookCardStore(Protocol):
    def upsert_card(self, row: dict[str, Any]) -> dict[str, Any]: ...
    def get_card(self, user_id: str, note_id: str) -> dict[str, Any] | None: ...
    def update_card(self, user_id: str, note_id: str, patch: dict[str, Any], *, expected_version: int) -> dict[str, Any] | None: ...
    def list_cards(self, user_id: str, *, subject_id: str = "", card_type: str = "") -> list[dict[str, Any]]: ...


class InMemoryNotebookCardStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}

    def upsert_card(self, row: dict[str, Any]) -> dict[str, Any]:
        key = (str(row.get("user_id") or ""), str(row.get("note_id") or ""))
        current = dict(self._rows.get(key) or {})
        current.update(dict(row or {}))
        current.setdefault("version", 1)
        self._rows[key] = current
        return dict(current)

    def get_card(self, user_id: str, note_id: str) -> dict[str, Any] | None:
        row = self._rows.get((str(user_id or ""), str(note_id or "")))
        return dict(row) if row is not None else None

    def update_card(self, user_id: str, note_id: str, patch: dict[str, Any], *, expected_version: int) -> dict[str, Any] | None:
        key = (str(user_id or ""), str(note_id or ""))
        current = self._rows.get(key)
        if current is None:
            return None
        if int(current.get("version") or 1) != int(expected_version):
            raise OptimisticConcurrencyError(f"stale version: have {current.get('version')}, expected {expected_version}")
        updated = {**current, **dict(patch or {}), "version": int(current.get("version") or 1) + 1}
        self._rows[key] = updated
        return dict(updated)

    def list_cards(self, user_id: str, *, subject_id: str = "", card_type: str = "") -> list[dict[str, Any]]:
        norm_u, norm_s, norm_c = str(user_id or ""), str(subject_id or "").strip(), str(card_type or "").strip()
        out = []
        for (row_u, _), row in self._rows.items():
            if row_u != norm_u or row.get("archived_at"):
                continue
            if norm_s and str(row.get("subject_id") or "") != norm_s:
                continue
            if norm_c and str(row.get("card_type") or "") != norm_c:
                continue
            out.append(dict(row))
        return sorted(out, key=lambda r: str(r.get("updated_at") or ""), reverse=True)


class UnavailableNotebookCardStore:
    def _fail(self, *_a, **_k):
        raise RuntimeError("notebook_card_store_unavailable")
    upsert_card = get_card = update_card = list_cards = _fail


class SupabaseNotebookCardStore:
    """同步 httpx PostgREST 客户端，乐观并发用 version 过滤 patch（仿 SupabaseMistakeBookStore）。"""

    _TABLE = "learner_notebook_cards"

    def __init__(self, *, base_url: str | None = None, service_key: str | None = None,
                 client: httpx.Client | None = None, timeout_s: float = 10.0) -> None:
        self._base_url = str(base_url or os.getenv("SUPABASE_URL", "") or "").strip().rstrip("/")
        self._service_key = str(service_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
                                or os.getenv("SUPABASE_KEY", "") or "").strip()
        self._client = client
        self._timeout_s = float(timeout_s)

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._service_key)

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_s)
        return self._client

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        h = {"apikey": self._service_key, "Authorization": f"Bearer {self._service_key}", "Content-Type": "application/json"}
        if prefer:
            h["Prefer"] = prefer
        return h

    def upsert_card(self, row: dict[str, Any]) -> dict[str, Any]:
        resp = self._http().post(
            f"{self._base_url}/rest/v1/{self._TABLE}",
            headers=self._headers(prefer="resolution=merge-duplicates,return=representation"),
            params={"on_conflict": "user_id,note_id"}, json=[row])
        resp.raise_for_status()
        payload = resp.json()
        return dict(payload[0]) if isinstance(payload, list) and payload else dict(row)

    def get_card(self, user_id: str, note_id: str) -> dict[str, Any] | None:
        resp = self._http().get(
            f"{self._base_url}/rest/v1/{self._TABLE}",
            headers=self._headers(),
            params={"select": "*", "user_id": f"eq.{user_id}", "note_id": f"eq.{note_id}", "limit": 1})
        resp.raise_for_status()
        payload = resp.json()
        return dict(payload[0]) if isinstance(payload, list) and payload else None

    def update_card(self, user_id: str, note_id: str, patch: dict[str, Any], *, expected_version: int) -> dict[str, Any] | None:
        body = {**dict(patch or {}), "version": int(expected_version) + 1}
        resp = self._http().patch(
            f"{self._base_url}/rest/v1/{self._TABLE}",
            headers=self._headers(prefer="return=representation"),
            params={"user_id": f"eq.{user_id}", "note_id": f"eq.{note_id}", "version": f"eq.{int(expected_version)}"},
            json=body)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list) and payload:
            return dict(payload[0])
        raise OptimisticConcurrencyError(f"no row matched version={expected_version} for {user_id}/{note_id}")

    def list_cards(self, user_id: str, *, subject_id: str = "", card_type: str = "") -> list[dict[str, Any]]:
        params = {"select": "*", "user_id": f"eq.{user_id}", "archived_at": "is.null", "order": "updated_at.desc"}
        if str(subject_id or "").strip():
            params["subject_id"] = f"eq.{subject_id}"
        if str(card_type or "").strip():
            params["card_type"] = f"eq.{card_type}"
        resp = self._http().get(f"{self._base_url}/rest/v1/{self._TABLE}", headers=self._headers(), params=params)
        resp.raise_for_status()
        payload = resp.json()
        return [dict(i) for i in payload if isinstance(i, dict)]
```

- [ ] **Step 4: 运行确认 PASS**

Run: `pytest tests/services/notebook_card/test_store.py -v`
Expected: 4 passed。

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/notebook_card/store.py tests/services/notebook_card/test_store.py
git commit -m "feat(notebook_card): durable card store (memory/supabase/unavailable) with optimistic version"
```

---

## Phase 2：`NotebookCardService` —— 卡片唯一权威 + 写回收权

这是 PRD blocker #1 的治本点：卡片写入**不经过** `NotebookManager._writeback_learner_state()`，因此天然不触发 `refresh_from_turn` / `patch_overlay`；只发一条 `record_notebook_writeback` 轻事件，且 recall 注入打 `student_note` 低权重标签。

### Task 2.1：`NotebookCardService.save_card` 只走轻写回

**Files:**
- Create: `deeptutor/services/notebook_card/service.py`
- Test: `tests/services/notebook_card/test_service.py`

- [ ] **Step 1: 写测试，断言 save_card 调 `record_notebook_writeback` 但绝不调 `refresh_from_turn`**

```python
import asyncio
import pytest

from deeptutor.services.notebook_card.store import InMemoryNotebookCardStore
from deeptutor.services.notebook_card.service import NotebookCardService


class _LearnerSpy:
    def __init__(self):
        self.notebook_writeback = 0
        self.refresh = 0

    async def record_notebook_writeback(self, **_kwargs):
        self.notebook_writeback += 1

    async def refresh_from_turn(self, **_kwargs):  # 必须永不被调用
        self.refresh += 1


def test_save_card_uses_light_writeback_only():
    spy = _LearnerSpy()
    svc = NotebookCardService(store=InMemoryNotebookCardStore(), learner_state_service=spy)
    card = asyncio.run(svc.save_card(
        user_id="u1", subject_id="construction_practice", source_bot_id="construction-exam",
        card_type="scoring_card", source_type="grading",
        source_ref={"kind": "learning_evidence", "event_id": "evt_1"},
        evidence_event_ids=["evt_1"], title="责任主体", raw_user_content="记一下",
        ai_enhanced_content={"summary": "高频考点"},
    ))
    assert card["note_id"]
    assert card["mastery_effect"] == "none"
    assert spy.notebook_writeback == 1
    assert spy.refresh == 0  # RED-LINE: 收权后绝不触发 summary 改写


def test_save_card_forces_mastery_effect_none_even_if_caller_lies():
    spy = _LearnerSpy()
    svc = NotebookCardService(store=InMemoryNotebookCardStore(), learner_state_service=spy)
    card = asyncio.run(svc.save_card(
        user_id="u1", subject_id="", source_bot_id="", card_type="manual_note", source_type="manual",
        source_ref={}, evidence_event_ids=[], title="x", raw_user_content="y",
        ai_enhanced_content={}, mastery_effect="strong",  # 调用方撒谎
    ))
    assert card["mastery_effect"] == "none"
```

- [ ] **Step 2: 运行确认 FAIL**

Run: `pytest tests/services/notebook_card/test_service.py -v`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 service（fat-skill 权威）**

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from deeptutor.services.notebook_card.store import NotebookCardStore, OptimisticConcurrencyError

_CARD_TYPES = {"scoring_card", "error_pattern_note", "review_note", "manual_note"}


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat()


class NotebookCardService:
    """学习卡片的唯一 authority：写/读/删卡片 + 仅轻量 learner-state 事件回写。
    禁止调用 refresh_from_turn / patch_overlay（写回收权）。"""

    def __init__(self, *, store: NotebookCardStore, learner_state_service: Any) -> None:
        self._store = store
        self._learner = learner_state_service

    async def save_card(self, *, user_id: str, subject_id: str, source_bot_id: str,
                         card_type: str, source_type: str, source_ref: dict[str, Any],
                         evidence_event_ids: list[str], title: str, raw_user_content: str,
                         ai_enhanced_content: dict[str, Any], mastery_effect: str = "none") -> dict[str, Any]:
        norm_user = str(user_id or "").strip()
        if not norm_user:
            raise ValueError("user_id required")
        ct = card_type if card_type in _CARD_TYPES else "manual_note"
        note_id = "note_" + uuid.uuid4().hex[:12]
        now = _iso_now()
        row = {
            "user_id": norm_user, "note_id": note_id, "subject_id": str(subject_id or ""),
            "source_bot_id": str(source_bot_id or ""), "card_type": ct, "source_type": str(source_type or "manual"),
            "source_ref": dict(source_ref or {}), "evidence_event_ids": list(evidence_event_ids or []),
            "title": str(title or ""), "raw_user_content": str(raw_user_content or ""),
            "ai_enhanced_content": dict(ai_enhanced_content or {}),
            "user_control_status": "confirmed", "use_for_personalization": True,
            "mastery_effect": "none",  # 永久固定，忽略调用方
            "version": 1, "created_at": now, "updated_at": now,
        }
        saved = self._store.upsert_card(row)
        await self._emit_light_event(saved, operation="add")
        return saved

    async def update_card(self, *, user_id: str, note_id: str, expected_version: int,
                          patch: dict[str, Any]) -> dict[str, Any]:
        safe_patch = {k: v for k, v in dict(patch or {}).items()
                      if k not in {"user_id", "note_id", "mastery_effect", "version"}}
        safe_patch["updated_at"] = _iso_now()
        updated = self._store.update_card(user_id, note_id, safe_patch, expected_version=expected_version)
        if updated is None:
            raise KeyError(f"card not found: {user_id}/{note_id}")
        return updated

    async def delete_card(self, *, user_id: str, note_id: str, expected_version: int) -> dict[str, Any]:
        return await self.update_card(user_id=user_id, note_id=note_id, expected_version=expected_version,
                                      patch={"archived_at": _iso_now()})

    def list_cards(self, user_id: str, *, subject_id: str = "", card_type: str = "") -> list[dict[str, Any]]:
        return self._store.list_cards(user_id, subject_id=subject_id, card_type=card_type)

    async def _emit_light_event(self, card: dict[str, Any], *, operation: str) -> None:
        # 仅轻路径：append 一条 notebook_* 事件，绝不 refresh_from_turn / patch_overlay。
        await self._learner.record_notebook_writeback(
            user_id=card["user_id"], notebook_id=card["note_id"], record_id=card["note_id"],
            operation=f"card_{operation}", title=card.get("title", ""),
            summary=str(card.get("ai_enhanced_content", {}).get("summary", "")),
            user_query=card.get("raw_user_content", ""), record_type=card.get("card_type", "manual_note"),
            kb_name=None, metadata={"source_label": "student_note", "card_type": card.get("card_type"),
                                    "mastery_effect": "none"},
            source_bot_id=card.get("source_bot_id") or None,
        )
```

- [ ] **Step 4: 运行确认 PASS**

Run: `pytest tests/services/notebook_card/test_service.py -v`
Expected: 2 passed。

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/notebook_card/service.py tests/services/notebook_card/test_service.py
git commit -m "feat(notebook_card): card authority with light-only writeback (kills summary/overlay pollution)"
```

### Task 2.2：recall 注入给 notebook 事件打 `student_note` 标签 + 降权

**Files:**
- Modify: `deeptutor/services/learner_state/service.py`（`build_context_candidates` 组装 memory_hit 处）
- Test: `tests/services/learner_state/test_service.py`（追加用例）

- [ ] **Step 1: 写测试，断言来自 notebook 卡片的 recall 候选带 `source_label="student_note"` 且权重低于 learning 证据**

```python
def test_notebook_card_recall_is_labeled_student_note_and_downweighted(tmp_path):
    from deeptutor.services.learner_state.service import LearnerStateService  # 复用现有 _make_service 同构
    import asyncio
    service = _make_service(tmp_path)
    asyncio.run(service.record_notebook_writeback(
        user_id="student_demo", notebook_id="note_x", record_id="note_x", operation="card_add",
        title="承载力和沉降控制", summary="先分清极限承载和正常使用阶段。",
        user_query="回顾承载力", record_type="scoring_card", source_bot_id="bot_a",
        metadata={"source_label": "student_note", "card_type": "scoring_card", "mastery_effect": "none"},
    ))
    candidates = service.build_context_candidates("student_demo", query="请回顾承载力和沉降控制", language="zh")
    hits = [c for c in candidates["candidates"] if c.get("source_tag") == "memory_hit"]
    assert hits, "应有 recall 命中"
    assert all(h.get("source_label") == "student_note" for h in hits)
    # 降权断言：student_note 命中权重不得高于普通 learning 证据默认权重
    assert all(float(h.get("weight", 1.0)) <= 0.5 for h in hits)
```

- [ ] **Step 2: 运行确认 FAIL**

Run: `pytest "tests/services/learner_state/test_service.py::test_notebook_card_recall_is_labeled_student_note_and_downweighted" -v`
Expected: FAIL（无 `source_label` / 未降权）。

- [ ] **Step 3: 在 `build_context_candidates` 的 memory_hit 组装处，按事件 `payload_json.metadata.source_label`/`memory_kind.startswith("notebook_")` 注入 `source_label` 与降权 `weight`**

> 实施提示：定位 `build_context_candidates` 中把 memory event 转成候选 dict 的那段，对 `memory_kind` 以 `notebook_` 开头或 `payload_json.metadata.source_label == "student_note"` 的项设 `source_label="student_note"`、`weight=min(weight, 0.4)`，并在 prompt 文案前缀加“（学员自记，不代表已掌握）”。保持其余 memory_hit 行为不变（Surgical Change）。

- [ ] **Step 4: 运行确认 PASS + 跑既有 recall 回归**

Run: `pytest tests/services/learner_state/test_service.py -v -k "recall or notebook"`
Expected: 新用例 PASS，既有 `test_learner_state_build_context_candidates_recall_includes_memory_hits` 仍 PASS。

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/learner_state/service.py tests/services/learner_state/test_service.py
git commit -m "feat(learner_state): label + downweight notebook-card recall hits as student_note"
```

---

## Phase 3：`POST /api/v1/notebook/add_record` 按 card_type 分流 + 卡片 PATCH/DELETE

不新增 cards writer endpoint（PRD 禁止）；在既有 router 内按 `metadata.card_type` 分流到 `NotebookCardService`。

### Task 3.1：add_record 路由分流

**Files:**
- Modify: `deeptutor/api/routers/notebook.py:99,290`
- Test: `tests/api/test_notebook_card_routing.py`（Create）

- [ ] **Step 1: 写测试，断言带 card_type 的请求落 NotebookCardService（durable），不带的走 legacy**

```python
# 用 FastAPI TestClient + 注入 InMemory store 的 NotebookCardService。
# 断言：metadata.card_type=scoring_card 时，响应含 note_id，且 legacy NotebookManager.add_record 未被调用；
#       不带 card_type 时，legacy 路径被调用、NotebookCardService 未被调用。
```

> 实施提示：用 `monkeypatch` 分别替换 `notebook_manager.add_record` 与 `get_notebook_card_service()` 为 spy，断言互斥调用。完整 spy 代码在 Step 3 实现后回填到 Step 1（执行时先写断言骨架再补 spy）。

- [ ] **Step 2: 运行确认 FAIL**

Run: `pytest tests/api/test_notebook_card_routing.py -v`
Expected: FAIL。

- [ ] **Step 3: 在 `_stream_add_record_with_summary` / `add_record` 路由开头加分流**

```python
# notebook.py，add_record 路由体起始处：
card_type = str((request.metadata or {}).get("card_type") or "").strip()
if card_type:
    svc = get_notebook_card_service()
    card = await svc.save_card(
        user_id=current_user.user_id,
        subject_id=str(request.metadata.get("subject_id") or ""),
        source_bot_id=str(request.metadata.get("source_bot_id") or ""),
        card_type=card_type,
        source_type=str(request.metadata.get("source_type") or "manual"),
        source_ref=dict(request.metadata.get("source_ref") or {}),
        evidence_event_ids=list(request.metadata.get("evidence_event_ids") or []),
        title=request.title,
        raw_user_content=request.user_query or request.output,
        ai_enhanced_content=dict(request.metadata.get("ai_enhanced_content") or {}),
    )
    return {"success": True, "card": card, "note_id": card["note_id"]}
# 否则维持既有 legacy add_record 流程不变。
```

- [ ] **Step 4: 运行确认 PASS + 既有 notebook 测试回归**

Run: `pytest tests/api/test_notebook_card_routing.py tests/services/test_notebook_service.py -v`
Expected: 全 PASS（legacy 行为不变）。

- [ ] **Step 5: Commit**

```bash
git add deeptutor/api/routers/notebook.py tests/api/test_notebook_card_routing.py
git commit -m "feat(api): route card_type saves to durable NotebookCardService, legacy unchanged"
```

### Task 3.2：卡片 PATCH/DELETE（带乐观并发 If-Match 语义）

**Files:**
- Modify: `deeptutor/api/routers/notebook.py`（卡片 PATCH/DELETE handler）
- Test: `tests/api/test_notebook_card_routing.py`（追加）

- [ ] **Step 1: 写测试：stale version PATCH 返回 409**
- [ ] **Step 2: 运行确认 FAIL**
- [ ] **Step 3: 实现 handler：`expected_version` 来自请求体/`If-Match`；`OptimisticConcurrencyError` -> HTTP 409**

```python
from deeptutor.services.notebook_card.store import OptimisticConcurrencyError
# ...
try:
    updated = await get_notebook_card_service().update_card(
        user_id=current_user.user_id, note_id=note_id,
        expected_version=int(payload.expected_version), patch=payload.patch)
except OptimisticConcurrencyError:
    raise HTTPException(status_code=409, detail="card was modified by another device; reload and retry")
except KeyError:
    raise HTTPException(status_code=404, detail="card not found")
```

- [ ] **Step 4: 运行确认 PASS**
- [ ] **Step 5: Commit**

```bash
git commit -am "feat(api): notebook card PATCH/DELETE with optimistic concurrency (409 on stale)"
```

---

## Phase 4：学情首页 read model 扩展（只扩展，不新增接口）

### Task 4.1：`build_learning_report_read_model` 增加 `note_assets` + `today_tasks`

**Files:**
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Test: `tests/services/learner_state/test_learning_report_read_model.py`（追加）

- [ ] **Step 1: 写测试：read model 含 `note_assets`（来自 NotebookCardService 计数）和 `today_tasks`（来自 training_intent + 笔记待行动 + 系统提醒投影），且 learning_evidence 过滤不被卡片污染**

```python
def test_read_model_includes_note_assets_and_today_tasks_without_polluting_evidence():
    # 注入若干 learning_evidence + 一个 notebook card 计数源；
    # 断言 model["note_assets"]["scoring_cards"] >= 1；
    # 断言 model["today_tasks"] 每项含 source ∈ {ai_recommendation, note_action, system_reminder}；
    # 断言 model["overview"]["recent_three_done"] 不因卡片增加（卡片不是 evidence）。
    ...
```

- [ ] **Step 2: 运行确认 FAIL**
- [ ] **Step 3: 在 read model 组装末尾注入两段投影（卡片计数 + 任务投影），任务来源枚举只允许 `ai_recommendation/note_action/system_reminder`（无 `my_created`）**
- [ ] **Step 4: 运行确认 PASS + 跑 `test_learning_evidence_limit_is_not_consumed_by_non_learning_events`**

Run: `pytest tests/services/learner_state/test_learning_report_read_model.py -v`
Expected: 全 PASS（证据过滤不被破坏）。

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(learning-report): extend read model with note_assets + read-only today_tasks"
```

> 同步更新 `contracts/index.yaml` / `contracts/learning-report.md`（若该 read model 已是 contract 边界）——这是 §Contract Discipline 要求，作为本 Task 的收尾步骤，diff 只动 learning-report 域。

---

## Phase 5：probe `measurement_confidence` 门槛（Flow E “测一下”不写假改善）

### Task 5.1：低置信复测不写 improvement evidence

**Files:**
- Modify: probe -> evidence 的写入处（`deeptutor/services/assessment/writeback.py` 或 probe handler，实施时 codegraph `measurement_confidence` 定位）
- Test: `tests/services/assessment/test_probe_confidence_gate.py`（Create）

- [ ] **Step 1: 写测试：`measurement_confidence="low"` 的 probe 结果不产生 improvement learning_evidence；`medium`/`high` 才写**
- [ ] **Step 2: 运行确认 FAIL**
- [ ] **Step 3: 在 writeback 入口加门槛：低于阈值（默认 `low` 不写）时返回“证据不足”信号，不 append improvement evidence**
- [ ] **Step 4: 运行确认 PASS**
- [ ] **Step 5: Commit**

```bash
git commit -am "feat(assessment): gate probe improvement evidence by measurement_confidence"
```

### Phase 5 对账结论（2026-05-31 codegraph/源码实证）

**N/A — 当前 MCQ 复测路线下无 confidence 可门、亦无风险，按 §857 不硬造门。** 实证：

- 喂 `_is_improvement` 的 score 源是 `deeptutor/services/assessment/learning_evidence.py`（MCQ batch），其 `score_awarded = 1.0 if is_correct else 0.0`（**二元**），`grep measurement_confidence` 计数 = **0**（该 payload 不带 confidence）。
- `deeptutor/services/learner_state/learning_synthesis.py:779-785` `_is_improvement` 只读 `score_awarded/max_score/error_events`，**不读** `measurement_confidence`。
- `measurement_confidence` 只活在 `assessment/scoring.py` / `teaching_policy.py` / `writeback.py`（rubric 评分路径），而该路径**不喂** `_is_improvement`。两路径不相交。
- MCQ 精确匹配本质二元高置信，H5「低置信复测假翻盘」风险**在此路线不成立**。

**待复测改走 rubric 案例批改（有 confidence variance）时再装门**，门边界 = assessment rubric 写回 → learning_evidence（不改 `_is_improvement`，那是 construction_grading 域、不带 confidence 的错边界）。本 Phase 不产代码、不阻塞验收。

---

## Phase 6：双端 UI + 微信开发者工具回归（contract 驱动）

> 本阶段动 `wx_miniprogram/` 与 `yousenwebview/packageDeeptutor/`。**先做前端现实校验**（导航是否能容纳“今日”入口、学情页首屏空间），再实现；前端改动除自动化外，**必须**完成一次微信开发者工具模拟器/真机回归（AGENTS §4）。本计划不臆造 wx 组件代码，由执行者按现网组件结构落地。

### Task 6.1：前端现实校验（只读，产出 view model 映射）
- [ ] 读 `wx_miniprogram/` 与 `yousenwebview/packageDeeptutor/` 现有学情页/答疑页结构，确认：答疑/批改底部操作位、学情页首屏“今日任务条”落点、收藏按钮触控区 ≥44x44。
- [ ] 产出 `note_assets`/`today_tasks` 到双端组件字段的映射表，确保 wx 与 yousen 共用同一 `/api/v1/mobile/learning-report` 投影，无第二 reader。

### Task 6.2：实现 Flow A/B/D/E 的最小交互（双端 parity）
- [ ] Flow A 答疑后“收藏到笔记”→ `POST add_record`（带 `card_type`）→ 卡片详情页。
- [ ] Flow B 批改后“加入采分点”→ `card_type=scoring_card`，低 rubric 置信降级为“审题要点”文案。
- [ ] Flow D 今日任务条（最多 3，只读投影，“今天时间少/换一组”仅前端过滤）。
- [ ] Flow E “我其实会”→“测一下”→既有出题/批改链路；低置信走 §14.1 救援文案。
- [ ] 失败救援：保存失败 toast、收藏待同步“暂不计入学情”。

### Task 6.3：微信开发者工具手工回归（§15 手工回归 6 条 + 新增 1 条）
- [ ] 答疑→收藏→生成卡→马上练一道。
- [ ] 批改→加入采分点→同类题→回学情。
- [ ] 1 条高置信建议→保存/修改保存/不准确。
- [ ] 今日任务条→“今天时间少”前端压缩。
- [ ] 我其实会→测一下→复测刷新。
- [ ] **保存手动卡片后，learner summary / compiled-truth projection 不变化。**
- [ ] **保存手动卡片后，Bot-Learner Overlay `working_memory_projection` 不被写入。**

---

## 验收 gate（对齐 PRD §15，含评审新增 overlay/并发项）

实现完成、合并前必须全绿：

- [ ] `pytest tests/services/notebook_card tests/api/test_notebook_card_routing.py tests/services/learner_state/test_service.py tests/services/learner_state/test_learning_report_read_model.py -v` 全 PASS。
- [ ] characterization 基线（Task 0.1）已被 Task 2.1 的“`refresh == 0`”用例取代（收权证据）。
- [ ] 保存手动卡片：learner summary mtime / compiled-truth projection hash / overlay `working_memory_projection` 三者均不变（自动 + 微信开发者工具双证）。
- [ ] 多端并发 PATCH 同一卡片：stale version 返回 409，无 lost update。
- [ ] 无新增聊天 WebSocket；无 `learner-workspace/home`；无 `planner/tasks` CRUD；无 `notebook/cards` writer。
- [ ] `training_intent` 仍是唯一处方 authority；今日任务来源枚举不含 `my_created`。
- [ ] probe 低 `measurement_confidence` 不写 improvement evidence。
- [ ] 迁移文件时间戳唯一、自带 RLS；**不在本 PR 内对生产 apply**（独立 release gate）。
- [ ] diff 可逐行追溯到 P0A；未顺手改 legacy notebook / 无关模块（§3 Surgical Changes）。

## 决策记录

- **gating key = `metadata.card_type` 存在性**：命中即走 durable `NotebookCardService`（轻写回），否则 legacy `NotebookManager` 不变。
- **收权方式 = 旁路而非删除**：不删 `_writeback_learner_state` 的 `refresh_from_turn`/`patch_overlay`（legacy 仍需要），而是让卡片不经过该函数。这样既治本（卡片零污染）又零回归（§3.6 narrow scope）。
- **持久化 = 新表 `learner_notebook_cards`（per-row + version 乐观并发）**，不迁移整个 file-backed notebook（YAGNI）；legacy solve/guided_learning 仍用 JSON。

## 未覆盖风险（执行者需知）

- 跨 bot 卡片聚合：本计划按 `user_id` 聚合，`source_bot_id` 仅来源标签；多 bot 同步语义留 P0B。
- AI 增强能力归属（PRD §11.1）：Phase 6 实现“鲁班整理/采分点”时必须复用既有 grading / question lifecycle skill context，**禁止**新起 enhancer prompt blob —— 执行者落地前需 codegraph 定位复用入口，若发现无现成入口，停止并回 PRD 讨论，不得新增第二套抽取逻辑。
- `data` 目录/SQLite outbox 的 owner_key 一致性：卡片 note_id 与既有 owner_key 体系对齐由 Phase 1 store 的 `user_id` 字段承接，不引入新身份概念。

---

## Self-Review

- **Spec 覆盖**：PRD P0A-1..P0A-7 → Task 3.1（收藏/分流）、2.1（卡片+收权）、4.1（今日任务/证据投影）、3.2（编辑删除）、5.1（probe 门槛）、6.2（纠偏入口 UI）。blocker 1（轻路径）→ Phase 2；blocker 2（durable）→ Phase 1；blocker 3（无 home 第二 reader）→ Phase 4 约束；blocker 4（无 planner CRUD）→ §0 非目标 + Phase 4 任务来源枚举；评审新增 overlay → Task 0.2/2.1/6.3/验收。
- **Placeholder 扫描**：Phase 1/2 含完整 SQL 与类实现；Phase 3/4/5 的 handler 给出关键代码片段与精确断言意图，UI Phase 6 明确标注“不臆造 wx 代码、需现实校验 + 手工回归”（诚实边界，非占位）。
- **类型一致性**：`NotebookCardService.save_card/update_card/delete_card/list_cards`、`store.upsert_card/get_card/update_card(expected_version=)/list_cards`、`OptimisticConcurrencyError`、`record_notebook_writeback(operation="card_*")` 在各 Task 间签名一致。
