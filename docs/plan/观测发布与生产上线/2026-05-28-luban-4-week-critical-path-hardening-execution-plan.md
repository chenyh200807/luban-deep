# 鲁班智考 4 周关键路径硬化执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development` 按 Track 派发；每个 failing scenario 使用 `root-cause-debugging`。Steps 用 checkbox (`- [ ]`) 跟踪。

**Goal:** 在未来 4 周关键业务窗口（销售演示 → B 端机构试点 → 邀请制内测）期间，把 4 项**会现场翻车**的技术债从"代码层已修"升级为"可阻断合并的工程门禁 + 可回放证据"。其余 P0 债显式延后到 wedge 验证之后。

**Architecture:** 4 个 track 并行。Track A/B 是产品可信度门禁（lifecycle + presentation_type），Track C/D 是 0 成本 CI 门禁（fail-on-new 模式 + 接入 tests.yml）。Track A 复用已存在的 `tutorbot_turn_replay.py` 作为 outcome-parity oracle；Track B 在 `contracts/turn.md` 新增显式 `presentation_type` 字段，禁止 renderer 推断。

**Tech Stack:** Python runtime / pytest / FastAPI / Pydantic / GitHub Actions (`.github/workflows/tests.yml`) / Supabase migration / Langfuse trace / 微信小程序 renderer。

**Status:** Proposed (2026-05-28)

**关联主线（INDEX.md hooks）：**
- TutorBot 与统一聊天入口主线：本计划 Track A/B 是 `2026-05-26-deeptutor-question-lifecycle-authority-consolidation-plan.md` Task 7（production validation）的落地执行。
- 生产部署主线：本计划 Track C/D 是 `2026-05-25-prelaunch-readiness-checklist.md` G3-G4 安全门禁的升级与 CI 接入。

---

## 0. 为什么是这 4 项，不是别的

本计划上游有两份评审：第一份"技术债 P0 全清单"（route inventory + RLS + runtime safety + LLM client + mobile.py + mypy + 巨型文件），第二份"AI-native startup playbook"。两份单独看都对，但**全做会和销售/试点/内测时间窗冲突**。

按"未来 4 周关键事件 → 哪些债会现场翻车"反推，只有 4 项是必须现在修的（详细推演见会话记录）：

| Track | 债务 | 触发哪个事件翻车 | 当前状态 |
|---|---|---|---|
| **A** | Lifecycle authority "案例题/2025真题" 错路由 + 缺自动化回归 | 销售演示当场流单 | 代码已修（Tasks 1-6 done），但 production canary 仍靠手工 |
| **B** | renderer 从"是否有 A/B/C/D 选项"推断卡片类型，无显式契约 | B 端机构试点：讲评卡被误当练习卡提交 → 学员数据污染 → B 端关系死 | contracts 和代码里都还没有 `presentation_type` 字段 |
| **C** | `check_secure_routers.sh` 写了但**没接进 tests.yml**，STRICT=0 warn-only | 不会现场翻车，但 0 成本，不做就是懒惰；新增匿名 endpoint 现在静默通过 | 脚本就绪、CI 未挂载 |
| **D** | `check_rls_on_create_table.sh` 同上 | 同上 | 同上 |

**明确延后**（4 周内不修，等 wedge 验证后再排）：
- Route inventory 全量重跑 + 历史 74 个匿名 endpoint 全量迁移
- mobile.py 拆分
- mypy strict 全仓
- 巨型文件重构（turn_runtime.py / deep_question.py 等）
- Runtime safety W1 完整版（BoundedQueue + 完整 create_task 替换）—— 仅做 §6 列出的内测必要子集
- LLM client factory 收尾（已基本完成）

---

## 1. 非目标 (Non-Goals)

为防止 scope creep，以下事项**本计划明确不做**：

1. 不重写 `turn_runtime.py` / `deep_question.py` / `mobile.py`。
2. 不全量迁移历史匿名 endpoint，只做 fail-on-new。
3. 不引入新的 LLM scene authority；继续以 `QuestionLifecycleSceneDecision` 为唯一裁判。
4. 不新建第二套 renderer；presentation_type 字段写进**已有** contract。
5. 不在本计划中改 RAG / learner state / Supabase wallet。
6. 不要求 4 周内全量历史 RLS 干净；只要求新 migration 干净。
7. 不在 4 周窗口内拉新 PRD；新功能只允许"不增加 P0 债务"的最小改动。

---

## 2. Single Authority 契约

| 关注点 | 唯一权威 | 文件入口 |
|---|---|---|
| 题目生命周期场景判定 | `QuestionLifecycleSceneDecision` | `deeptutor/services/question_lifecycle_skills.py` |
| 卡片渲染类型 | `presentation_type` enum (本计划新增) | `contracts/turn.md` |
| 路由默认安全 | `secure_router()` factory + `_public_manifest.py` reason | `deeptutor/api/_secure_router.py`, `deeptutor/api/_public_manifest.py` |
| 公共表 RLS 强制 | `alter table ... enable row level security` 同 migration | `supabase/migrations/*.sql` + `scripts/ci/check_rls_on_create_table.sh` |
| Lifecycle 回归 oracle | `tutorbot_turn_replay.py` + 新增 lifecycle scenario fixture | `deeptutor/services/benchmark/tutorbot_turn_replay.py` |

任何 PR 若新增第二套权威，本计划要求**直接拒绝合并**。

---

## 3. Track A — Lifecycle Authority Production Canary + Replay 自动化

**Files:**
- Create: `deeptutor/services/benchmark/fixtures/lifecycle_red_line_scenarios.jsonl`
- Create: `deeptutor/services/benchmark/lifecycle_authority_replay.py`
- Create: `tests/services/benchmark/test_lifecycle_authority_replay.py`
- Create: `scripts/ci/check_lifecycle_authority.sh`
- Modify: `.github/workflows/tests.yml`（新增 step）
- Reference only: `docs/plan/2026-05-26-deeptutor-question-lifecycle-authority-consolidation-plan.md` §Section 6 red-line matrix

### Task A1 — 定义 red-line scenario fixture

把 2026-05-26 计划 §Section 6 的 16 条红线场景固化成 JSONL fixture。**至少包含**下列 10 条（按销售/试点风险优先级）：

| # | scenario_id | 输入 message | 预设 turn context | 期望 decision.scene | 期望 blocked_reason / 关键断言 |
|---|---|---|---|---|---|
| 1 | low_info_exam_query_year | `2025真题` | 无 active question | `exam_catalog_query` | `low_information_exam_query`，禁止生成具体真题答案 |
| 2 | low_info_exam_query_topic | `防水真题` | 无 active question | `exam_catalog_query` | `low_information_exam_query` |
| 3 | concrete_question_review | `分析一道钢筋保护层真题` + 带题干和选项 | 无 active question | `question_review` | `required_anchor_status=anchored`，必须先 anchor 题干再讲评 |
| 4 | practice_generation | `用3道题训练项目质量计划管理` | 无 active question | `practice_generation` | `selected_skill_names` 含 `deep_question` |
| 5 | mcq_grading_with_active | `我选B` | 有 active question (MCQ) | `mcq_grading` | 不路由到 practice_generation |
| 6 | mcq_grading_no_active | `我选B` | 无 active question | `question_followup` 或 clarification | 要求补充是哪道题 |
| 7 | learning_evidence_story | `我最近哪里错` | 有 stale active_object | `learning_evidence_story` | **必须不被 deep_question 抢走**（root cause #2） |
| 8 | study_assistant | `今天学什么` | 无 active question | `study_assistant` | 不路由 deep_question |
| 9 | learning_support | `我学不动了` | 无 active question | `learning_support` | 不路由 question_review |
| 10 | general_chat | `横道图和网络图有什么区别` | 无 active question | `general_chat` / `study_assistant` | **必须不变成题卡**（不是 practice_generation） |

每条 fixture 字段：

```json
{
  "scenario_id": "low_info_exam_query_year",
  "user_message": "2025真题",
  "active_object": null,
  "recent_turn_summary": null,
  "teaching_mode": "default",
  "expected": {
    "scene": "exam_catalog_query",
    "exact_question_blocked_reason": "low_information_exam_query",
    "required_anchor_status": "not_required",
    "selected_skill_names_contains": ["construction-exam-catalog"],
    "selected_skill_names_excludes": ["deep_question"]
  }
}
```

- [ ] **Step A1.1**：阅读 2026-05-26 plan §Section 6 完整 16 条 + §3.1-3.4，确认 expected 字段名与 `QuestionLifecycleSceneDecision` 当前实现对齐
- [ ] **Step A1.2**：创建 `deeptutor/services/benchmark/fixtures/lifecycle_red_line_scenarios.jsonl`，写入上述 10 条
- [ ] **Step A1.3**：人工 review fixture，确认每条 expected 是产品意图而不是当前实现 bug 的"既成事实"
- [ ] **Step A1.4**：commit fixture

```bash
git add deeptutor/services/benchmark/fixtures/lifecycle_red_line_scenarios.jsonl
git commit -m "feat(benchmark): add lifecycle authority red-line scenario fixtures"
```

### Task A2 — 实现 lifecycle_authority_replay

复用 `tutorbot_turn_replay.py` 的 dataclass + mismatch 模式，但 oracle 不是历史 turn 而是 fixture expected。

- [ ] **Step A2.1**：创建 `deeptutor/services/benchmark/lifecycle_authority_replay.py`，骨架如下

```python
"""Lifecycle authority canary — assert QuestionLifecycleSceneDecision matches
expected scene for every red-line fixture scenario.

This is the production oracle for 2026-05-26 question lifecycle consolidation
plan §Task 7. CI gate: if any red-line fixture diverges, block merge."""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deeptutor.runtime.orchestrator import resolve_question_lifecycle_scene_decision
# Adjust import to the actual public API of the orchestrator.

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lifecycle_red_line_scenarios.jsonl"


@dataclass(frozen=True)
class ScenarioMismatch:
    scenario_id: str
    field: str
    expected: Any
    actual: Any


def load_scenarios() -> list[dict[str, Any]]:
    with FIXTURE_PATH.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def replay_scenario(scenario: dict[str, Any]) -> list[ScenarioMismatch]:
    decision = resolve_question_lifecycle_scene_decision(
        user_message=scenario["user_message"],
        active_object=scenario.get("active_object"),
        recent_turn_summary=scenario.get("recent_turn_summary"),
        teaching_mode=scenario.get("teaching_mode", "default"),
    )
    expected = scenario["expected"]
    mismatches: list[ScenarioMismatch] = []
    sid = scenario["scenario_id"]

    if decision.scene != expected["scene"]:
        mismatches.append(ScenarioMismatch(sid, "scene", expected["scene"], decision.scene))
    if "exact_question_blocked_reason" in expected:
        if decision.exact_question_blocked_reason != expected["exact_question_blocked_reason"]:
            mismatches.append(ScenarioMismatch(sid, "exact_question_blocked_reason",
                expected["exact_question_blocked_reason"], decision.exact_question_blocked_reason))
    if "required_anchor_status" in expected:
        if decision.required_anchor_status != expected["required_anchor_status"]:
            mismatches.append(ScenarioMismatch(sid, "required_anchor_status",
                expected["required_anchor_status"], decision.required_anchor_status))
    for skill in expected.get("selected_skill_names_contains", []):
        if skill not in decision.selected_skill_names:
            mismatches.append(ScenarioMismatch(sid, f"missing_skill:{skill}", True, False))
    for skill in expected.get("selected_skill_names_excludes", []):
        if skill in decision.selected_skill_names:
            mismatches.append(ScenarioMismatch(sid, f"forbidden_skill:{skill}", False, True))
    return mismatches


def run_all() -> list[ScenarioMismatch]:
    out: list[ScenarioMismatch] = []
    for s in load_scenarios():
        out.extend(replay_scenario(s))
    return out
```

- [ ] **Step A2.2**：调整 `resolve_question_lifecycle_scene_decision` 的实际 import path 与签名（先在 REPL 中验证）

```bash
python -c "from deeptutor.services.question_lifecycle_skills import QuestionLifecycleSceneDecision; print(QuestionLifecycleSceneDecision.__dataclass_fields__.keys())"
```

期望：看到 `scene`, `exact_question_blocked_reason`, `required_anchor_status`, `selected_skill_names` 等字段

- [ ] **Step A2.3**：commit

```bash
git add deeptutor/services/benchmark/lifecycle_authority_replay.py
git commit -m "feat(benchmark): add lifecycle authority replay against red-line fixtures"
```

### Task A3 — 写 pytest 把 replay 接入测试

- [ ] **Step A3.1**：创建 `tests/services/benchmark/test_lifecycle_authority_replay.py`

```python
import pytest
from deeptutor.services.benchmark.lifecycle_authority_replay import (
    load_scenarios,
    replay_scenario,
    run_all,
)


@pytest.mark.unit
def test_red_line_fixture_loads_at_least_10_scenarios():
    scenarios = load_scenarios()
    assert len(scenarios) >= 10, f"expected ≥10 red-line scenarios, got {len(scenarios)}"


@pytest.mark.integration
@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda s: s["scenario_id"])
def test_lifecycle_authority_red_line(scenario):
    mismatches = replay_scenario(scenario)
    if mismatches:
        details = "\n".join(
            f"  {m.scenario_id}.{m.field}: expected={m.expected!r} actual={m.actual!r}"
            for m in mismatches
        )
        pytest.fail(f"lifecycle authority drift on {scenario['scenario_id']}:\n{details}")


@pytest.mark.integration
def test_all_red_line_scenarios_pass():
    mismatches = run_all()
    assert not mismatches, f"{len(mismatches)} lifecycle authority mismatch(es): {mismatches}"
```

- [ ] **Step A3.2**：在本地跑

```bash
pytest tests/services/benchmark/test_lifecycle_authority_replay.py -v
```

期望：10 条 parametrized test 全部 PASS。**如果某条 FAIL，不要改 fixture 让 test PASS——必须修代码（root-cause-debugging）**。预期会有 1-3 条暴露真实 lifecycle authority drift（特别是 scenarios #7、#10），这正是这个 gate 的价值。

- [ ] **Step A3.3**：对每条 FAIL，单独建 issue / commit 修复，禁止"批改 fixture 期望来对齐当前实现"

- [ ] **Step A3.4**：所有 10 条 PASS 后 commit

```bash
git add tests/services/benchmark/test_lifecycle_authority_replay.py
git commit -m "test(benchmark): enforce lifecycle authority red-line matrix"
```

### Task A4 — 加 Langfuse trace 字段断言

`QuestionLifecycleSceneDecision` 包含 `llm_scene_candidate`、`business_gate_result`、`decision_source` 等字段，必须落进 Langfuse trace 才能销售/试点出问题时排查。

- [ ] **Step A4.1**：找到当前 lifecycle 写 trace 的位置

```bash
grep -rn "lifecycle\|scene_decision\|business_gate" deeptutor/services/observability/ deeptutor/runtime/ | grep -i "trace\|langfuse\|metadata" | head -20
```

- [ ] **Step A4.2**：在该写入点添加 schema 断言（pydantic model 或 dict key 检查），确保至少写入：
  - `question_lifecycle_decision.scene`
  - `question_lifecycle_decision.decision_source`
  - `question_lifecycle_decision.business_gate_result`
  - `question_lifecycle_decision.llm_scene_candidate`（如有）
  - `question_lifecycle_decision.required_anchor_status`
  - `question_lifecycle_decision.exact_question_blocked_reason`（如有）
  - `question_lifecycle_decision.selected_skill_names`

- [ ] **Step A4.3**：单测确保写入路径不会因为缺字段静默丢弃

```python
@pytest.mark.unit
def test_lifecycle_trace_payload_contains_all_required_keys():
    payload = build_lifecycle_trace_payload(some_decision_fixture)
    required = {
        "scene", "decision_source", "business_gate_result",
        "required_anchor_status", "selected_skill_names",
    }
    assert required.issubset(payload.keys()), f"missing: {required - payload.keys()}"
```

- [ ] **Step A4.4**：commit

```bash
git commit -m "feat(observability): assert lifecycle decision payload schema for trace"
```

### Task A5 — 写 CI gate 脚本 + 接入 tests.yml

- [ ] **Step A5.1**：创建 `scripts/ci/check_lifecycle_authority.sh`

```bash
#!/usr/bin/env bash
# Lifecycle authority red-line CI gate. Runs the replay test against
# the 10+ canary scenarios in deeptutor/services/benchmark/fixtures/.
# Required for any PR that touches lifecycle authority surface.

set -euo pipefail

echo "[check_lifecycle_authority] running red-line replay..."
pytest tests/services/benchmark/test_lifecycle_authority_replay.py -v --tb=short

echo "[OK] check_lifecycle_authority: all red-line scenarios pass"
```

- [ ] **Step A5.2**：`chmod +x scripts/ci/check_lifecycle_authority.sh`

- [ ] **Step A5.3**：修改 `.github/workflows/tests.yml`，在 contract guard step 之后增加：

```yaml
      - name: Lifecycle authority red-line gate
        run: bash scripts/ci/check_lifecycle_authority.sh
```

并在 paths trigger 中增加：

```yaml
      - "deeptutor/services/question_lifecycle_skills.py"
      - "deeptutor/services/benchmark/lifecycle_authority_replay.py"
      - "deeptutor/services/benchmark/fixtures/lifecycle_red_line_scenarios.jsonl"
      - "scripts/ci/check_lifecycle_authority.sh"
```

- [ ] **Step A5.4**：本地 dry-run

```bash
bash scripts/ci/check_lifecycle_authority.sh
```

期望：所有 scenario PASS

- [ ] **Step A5.5**：commit

```bash
git add scripts/ci/check_lifecycle_authority.sh .github/workflows/tests.yml
git commit -m "ci: enforce lifecycle authority red-line matrix on every PR"
```

### Track A 验收标准

- [ ] 10+ red-line scenario fixture 存在且每条都有产品意图断言
- [ ] `pytest tests/services/benchmark/test_lifecycle_authority_replay.py` 100% PASS
- [ ] Langfuse trace payload schema 测试通过
- [ ] CI workflow 跑过一次绿灯
- [ ] 故意制造 1 条 fixture mismatch 验证 CI 会阻断（drill）
- [ ] 至少 1 个销售演示场景在真实环境跑过（不限制本周，列入 Track A 完整 Done 之前必做）

---

## 4. Track B — `presentation_type` 显式契约

**Files:**
- Modify: `contracts/turn.md`
- Modify: `contracts/index.yaml`
- Create: `deeptutor/contracts/presentation_type.py`（或类似位置的 enum 定义）
- Modify: `deeptutor/capabilities/deep_question.py`（writer 必须设置 presentation_type）
- Modify: TutorBot construction-question-review skill output（writer）
- Modify: `wx_miniprogram/...`（reader：删除从 options 推断卡片类型的代码）
- Create: `tests/contracts/test_presentation_type_contract.py`
- Modify: `scripts/check_turn_contract_guard.py`（强制断言）

### Task B1 — Contract 层定义

- [ ] **Step B1.1**：在 `contracts/turn.md` 添加章节"Presentation Type"

```markdown
## Presentation Type

每条 turn 输出的可视卡片必须显式标注 `presentation_type`，禁止 renderer 从内容字段（如"是否含 A/B/C/D 选项"）推断卡片交互形态。

Enum 值（exhaustive）：

| 值 | 含义 | 可交互（用户可提交） |
|---|---|---|
| `non_interactive_review_card` | 题目讲评、错因分析、答案解释 | 否 |
| `submittable_practice_card` | AI 出的练习题，用户可提交答案 | 是 |
| `narration_card` | 学情故事、学习计划、心理支持等纯文本叙述 | 否 |
| `evidence_card` | 历史作答证据回放，含点击进入历史详情 | 否（仅可点击） |
| `clarification_request` | 系统反问澄清 | 是（输入文本回答） |
| `general_answer` | 通用问答（如概念解释） | 否 |

**Writer 责任**：任何产生卡片的 capability / skill / runtime 必须在响应中设置 `presentation_type`。

**Reader 责任**：渲染端（小程序、Web）只能根据 `presentation_type` 决定是否渲染提交按钮、是否绑定提交回调。禁止根据 `options`/`answer_field` 等内容字段推断交互形态。

**契约 Guard**：`scripts/check_turn_contract_guard.py` 必须在 PR 上断言每条卡片 payload 都有合法 `presentation_type`。
```

- [ ] **Step B1.2**：在 `contracts/index.yaml` 把 `presentation_type` 字段加入 turn payload schema 定义（具体格式参考已有字段如 `scene`）

- [ ] **Step B1.3**：commit

```bash
git add contracts/turn.md contracts/index.yaml
git commit -m "contract(turn): add explicit presentation_type field"
```

### Task B2 — Python enum + Pydantic validator

- [ ] **Step B2.1**：在合适位置（`deeptutor/contracts/` 或 `deeptutor/services/`）创建 enum

```python
from enum import StrEnum


class PresentationType(StrEnum):
    NON_INTERACTIVE_REVIEW_CARD = "non_interactive_review_card"
    SUBMITTABLE_PRACTICE_CARD = "submittable_practice_card"
    NARRATION_CARD = "narration_card"
    EVIDENCE_CARD = "evidence_card"
    CLARIFICATION_REQUEST = "clarification_request"
    GENERAL_ANSWER = "general_answer"


INTERACTIVE_TYPES = frozenset({
    PresentationType.SUBMITTABLE_PRACTICE_CARD,
    PresentationType.CLARIFICATION_REQUEST,
})
```

- [ ] **Step B2.2**：单测

```python
def test_interactive_classification():
    assert PresentationType.SUBMITTABLE_PRACTICE_CARD in INTERACTIVE_TYPES
    assert PresentationType.NON_INTERACTIVE_REVIEW_CARD not in INTERACTIVE_TYPES
```

- [ ] **Step B2.3**：commit

### Task B3 — Writer 全部显式设置 presentation_type

- [ ] **Step B3.1**：grep 出所有当前生成卡片的位置

```bash
grep -rn "options\s*=\|answer_field\|practice_question\|review_card\|阅卷结论" deeptutor/capabilities/ deeptutor/services/ | grep -v test_ | head -40
```

- [ ] **Step B3.2**：对每个 writer 位置：
  - `deep_question` 生成练习题 → `SUBMITTABLE_PRACTICE_CARD`
  - `construction-question-review` skill 输出讲评 → `NON_INTERACTIVE_REVIEW_CARD`
  - exact question fast path → 根据 lifecycle decision.scene 决定
  - learning_evidence_story / study_assistant / learning_support → `NARRATION_CARD`
  - exam_catalog_query / 反问澄清 → `CLARIFICATION_REQUEST`
  - 通用问答 → `GENERAL_ANSWER`

- [ ] **Step B3.3**：每个 writer 修改后立即写 fixture 测试，确保输出包含正确 presentation_type

```python
@pytest.mark.unit
def test_deep_question_practice_sets_submittable():
    result = deep_question.generate_practice(stem="...", options=["A", "B"])
    assert result.presentation_type == PresentationType.SUBMITTABLE_PRACTICE_CARD


@pytest.mark.unit
def test_construction_question_review_sets_non_interactive():
    result = construction_question_review.render(question_id="...")
    assert result.presentation_type == PresentationType.NON_INTERACTIVE_REVIEW_CARD
```

- [ ] **Step B3.4**：跑全部相关单测

```bash
pytest tests/capabilities/ tests/services/ -k "presentation_type or review_card or practice" -v
```

- [ ] **Step B3.5**：分 writer 独立 commit（每个 capability 一个 commit，便于 review）

### Task B4 — Renderer 只读契约，删除推断代码

- [ ] **Step B4.1**：grep 出小程序里所有"从 options/answer_field 推断卡片"的位置

```bash
grep -rn "options\.length\|hasOptions\|isInteractive\|submittable\|canSubmit\|提交按钮" wx_miniprogram/ web/ | grep -vE "node_modules|\.d\.ts" | head -40
```

- [ ] **Step B4.2**：每个推断点改为直接读 `payload.presentation_type`

- [ ] **Step B4.3**：禁止 renderer fallback "如果没 presentation_type 就猜"。如果缺字段，直接渲染为 `GENERAL_ANSWER` 并打 warn 日志（让 trace 暴露 writer 漏设的位置）

- [ ] **Step B4.4**：commit

### Task B5 — Contract guard CI 强制

- [ ] **Step B5.1**：扩展 `scripts/check_turn_contract_guard.py`，新增断言：所有 capability/skill 输出 payload schema 必须包含 `presentation_type` 字段，且值在 enum 内

- [ ] **Step B5.2**：本地 dry-run

```bash
python scripts/check_turn_contract_guard.py --base origin/main --head HEAD
```

- [ ] **Step B5.3**：commit

### Task B6 — 微信开发者工具回归

按 `docs/plan/2026-04-16-wechat-structured-renderer-devtools-runbook.md` 在微信开发者工具里跑：

- [ ] 一道讲评卡是否**没有**"提交答案"按钮
- [ ] 一道练习卡是否**有**"提交答案"按钮
- [ ] 学情叙述是否渲染为纯文本卡片
- [ ] 澄清反问是否渲染为可输入文本框
- [ ] 截图保存到 `docs/qa/2026-05-28-presentation-type-wx-devtools-evidence/`

### Track B 验收标准

- [ ] `contracts/turn.md` 含 Presentation Type 章节
- [ ] PresentationType enum + 单测
- [ ] 全部 writer 显式设置（grep `presentation_type=` 出现次数 ≥ writer 数量）
- [ ] Renderer 无任何"从内容推断卡片类型"代码（grep 验证）
- [ ] `scripts/check_turn_contract_guard.py` 在 PR 上能阻断"漏设 presentation_type"
- [ ] 微信开发者工具回归证据归档

---

## 5. Track C — `secure_router` fail-on-new gate + 接入 CI

**Files:**
- Create: `scripts/ci/baselines/secure_routers_baseline.txt`
- Modify: `scripts/ci/check_secure_routers.sh`（新增 FAIL_ON_NEW=1 模式）
- Modify: `.github/workflows/tests.yml`（新增 step）

### Task C1 — 快照当前 historical violations

- [ ] **Step C1.1**：在 STRICT=1 模式下跑一次，捕获所有当前 violation

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
STRICT=1 bash scripts/ci/check_secure_routers.sh 2>&1 | tee /tmp/secure_routers_current_violations.txt || true
```

- [ ] **Step C1.2**：把 violation 提炼成 baseline（只保留 `file:line` 不含行号差异的稳定 key）

```bash
mkdir -p scripts/ci/baselines
grep -E "^\[FAIL\]|deeptutor/api/routers" /tmp/secure_routers_current_violations.txt \
  | grep -oE "deeptutor/api/routers/[^:]+:[0-9]+" \
  | sort -u > scripts/ci/baselines/secure_routers_baseline.txt
wc -l scripts/ci/baselines/secure_routers_baseline.txt
```

期望：行数 = 当前已知历史 violation 数量

- [ ] **Step C1.3**：人工 review baseline 文件，确认每条都是"已知历史债"而不是"漏修的真 bug"

- [ ] **Step C1.4**：commit baseline

```bash
git add scripts/ci/baselines/secure_routers_baseline.txt
git commit -m "ci(baselines): snapshot historical secure_router violations for fail-on-new gate"
```

### Task C2 — `check_secure_routers.sh` 加 FAIL_ON_NEW 模式

- [ ] **Step C2.1**：修改 `scripts/ci/check_secure_routers.sh`，新增第三模式

在脚本顶部 STRICT 变量定义后增加：

```bash
# FAIL_ON_NEW=1: pass historical violations in scripts/ci/baselines/secure_routers_baseline.txt,
# but fail on any new bare APIRouter / public_router-without-reason / WS-without-secure_ws_endpoint
# that does not appear in the baseline. This is the gate enforced in CI before STRICT=1 rollout.
FAIL_ON_NEW="${FAIL_ON_NEW:-0}"
BASELINE_FILE="${BASELINE_FILE:-scripts/ci/baselines/secure_routers_baseline.txt}"
```

把 Rule 1（bare APIRouter 检测）改为：

```bash
bad=$(grep -RnE '^[^#]*APIRouter\(' "$ROUTERS_DIR" 2>/dev/null || true)
if [ -n "$bad" ]; then
    # FAIL_ON_NEW: filter out baseline entries
    if [ "$FAIL_ON_NEW" = "1" ] && [ -f "$BASELINE_FILE" ]; then
        new_bad=""
        while IFS= read -r line; do
            key=$(echo "$line" | grep -oE "$ROUTERS_DIR/[^:]+:[0-9]+" || true)
            if [ -n "$key" ] && ! grep -qxF "$key" "$BASELINE_FILE"; then
                new_bad="${new_bad}${line}\n"
            fi
        done <<< "$bad"
        if [ -n "$new_bad" ]; then
            echo "[FAIL] new bare APIRouter() not in baseline:" >&2
            echo -e "$new_bad" >&2
            fail=1
        fi
    elif [ "$STRICT" = "1" ]; then
        # ... existing STRICT logic ...
    else
        # ... existing warn-only logic ...
    fi
fi
```

对 Rule 3（WS without secure_ws_endpoint）做相同的 fail-on-new 改造。

- [ ] **Step C2.2**：本地测试 fail-on-new 模式

```bash
FAIL_ON_NEW=1 bash scripts/ci/check_secure_routers.sh
echo "exit code: $?"
```

期望：exit 0（baseline 全部匹配，无新增）

- [ ] **Step C2.3**：故意制造一个 new violation 验证 gate 阻断

```bash
# 临时加一个 bare APIRouter() 到某个 routers 文件
echo "" >> deeptutor/api/routers/health.py
echo "_test_router = APIRouter()" >> deeptutor/api/routers/health.py
FAIL_ON_NEW=1 bash scripts/ci/check_secure_routers.sh; echo "exit code: $?"
# 期望：exit 1，输出 "new bare APIRouter() not in baseline"

# 还原
git checkout deeptutor/api/routers/health.py
```

- [ ] **Step C2.4**：commit

```bash
git add scripts/ci/check_secure_routers.sh
git commit -m "ci(secure_routers): add FAIL_ON_NEW mode with baseline allowlist"
```

### Task C3 — 接入 `.github/workflows/tests.yml`

- [ ] **Step C3.1**：在 paths 触发列表中加入

```yaml
      - "deeptutor/api/routers/**"
      - "deeptutor/api/_secure_router.py"
      - "deeptutor/api/_public_manifest.py"
      - "scripts/ci/check_secure_routers.sh"
      - "scripts/ci/baselines/secure_routers_baseline.txt"
```

- [ ] **Step C3.2**：在 contract guard step 之后增加：

```yaml
      - name: Secure router fail-on-new gate
        run: FAIL_ON_NEW=1 bash scripts/ci/check_secure_routers.sh
```

- [ ] **Step C3.3**：commit

```bash
git add .github/workflows/tests.yml
git commit -m "ci: enforce secure_router fail-on-new gate on every PR"
```

### Track C 验收标准

- [ ] baseline 文件存在，行数 = 已知历史 violation 数
- [ ] `FAIL_ON_NEW=1 bash scripts/ci/check_secure_routers.sh` 在干净 main 上 exit 0
- [ ] 人为制造新 violation 时 exit 1
- [ ] CI 跑过一次绿灯

---

## 6. Track D — RLS fail-on-new gate + 接入 CI

**Files:**
- Create: `scripts/ci/baselines/rls_migrations_baseline.txt`
- Modify: `scripts/ci/check_rls_on_create_table.sh`（新增 FAIL_ON_NEW 模式）
- Modify: `.github/workflows/tests.yml`

### Task D1 — 快照历史 violation migration 文件名

RLS gate 比 secure_router 简单：以 migration 文件名（含 timestamp 前缀）做 baseline key 即可。

- [ ] **Step D1.1**：STRICT=1 跑出所有违规 migration

```bash
STRICT=1 bash scripts/ci/check_rls_on_create_table.sh 2>&1 | tee /tmp/rls_current_violations.txt || true
grep -oE "[0-9]{14}_[a-z0-9_]+\.sql" /tmp/rls_current_violations.txt | sort -u \
  > scripts/ci/baselines/rls_migrations_baseline.txt
wc -l scripts/ci/baselines/rls_migrations_baseline.txt
```

- [ ] **Step D1.2**：人工 review baseline，确认每条都是已知历史 migration（不是漏修的真 bug）

- [ ] **Step D1.3**：commit baseline

```bash
git add scripts/ci/baselines/rls_migrations_baseline.txt
git commit -m "ci(baselines): snapshot historical RLS violations for fail-on-new gate"
```

### Task D2 — `check_rls_on_create_table.sh` 加 FAIL_ON_NEW

- [ ] **Step D2.1**：修改脚本（结构与 Track C 同款）

在 STRICT 定义后加：

```bash
FAIL_ON_NEW="${FAIL_ON_NEW:-0}"
BASELINE_FILE="${BASELINE_FILE:-scripts/ci/baselines/rls_migrations_baseline.txt}"
```

在 violation 触发分支中加 FAIL_ON_NEW 处理：

```bash
if [ "$FAIL_ON_NEW" = "1" ] && [ -f "$BASELINE_FILE" ]; then
    basename_f=$(basename "$f")
    if ! grep -qxF "$basename_f" "$BASELINE_FILE"; then
        echo "[FAIL] new migration $basename_f creates public.${t} but does not enable RLS" >&2
        fail=1
    fi
elif [ "$STRICT" = "1" ]; then
    # ... existing ...
fi
```

- [ ] **Step D2.2**：本地测试

```bash
FAIL_ON_NEW=1 bash scripts/ci/check_rls_on_create_table.sh
echo "exit code: $?"
```

期望：exit 0

- [ ] **Step D2.3**：故意制造一个新 violation migration 验证

```bash
cat > supabase/migrations/99999999999999_test_rls_gate.sql <<'EOF'
create table public.test_rls_gate (id uuid primary key);
EOF
FAIL_ON_NEW=1 bash scripts/ci/check_rls_on_create_table.sh; echo "exit code: $?"
# 期望：exit 1

# 清理
rm supabase/migrations/99999999999999_test_rls_gate.sql
```

- [ ] **Step D2.4**：commit

```bash
git add scripts/ci/check_rls_on_create_table.sh
git commit -m "ci(rls): add FAIL_ON_NEW mode with migration baseline allowlist"
```

### Task D3 — 接入 tests.yml

- [ ] **Step D3.1**：在 paths 触发列表中加入

```yaml
      - "supabase/migrations/**"
      - "scripts/ci/check_rls_on_create_table.sh"
      - "scripts/ci/baselines/rls_migrations_baseline.txt"
```

- [ ] **Step D3.2**：增加 step

```yaml
      - name: RLS fail-on-new gate
        run: FAIL_ON_NEW=1 bash scripts/ci/check_rls_on_create_table.sh
```

- [ ] **Step D3.3**：commit

```bash
git add .github/workflows/tests.yml
git commit -m "ci: enforce RLS fail-on-new gate on every new migration"
```

### Track D 验收标准

- [ ] baseline 文件存在，行数 = 已知违规 migration 数
- [ ] `FAIL_ON_NEW=1 bash scripts/ci/check_rls_on_create_table.sh` 在干净 main 上 exit 0
- [ ] 人为制造新违规 migration 时 exit 1
- [ ] CI 跑过一次绿灯

---

## 7. 执行顺序与时间预算

| 周次 | Track | 工作量 | 优先级 |
|---|---|---|---|
| W1 | **C + D**（CI 接入 + fail-on-new） | 0.5 + 0.5 = 1 dev day | 0 成本快速过 |
| W1 | **A1 + A2 + A3**（fixture + replay + pytest） | 1.5 dev days | 销售演示生死线 |
| W2 | **A4 + A5**（Langfuse + CI gate） + drill | 1 dev day | A 完整闭环 |
| W2 | **B1 + B2**（contract + enum） | 0.5 dev day | B 端试点前置 |
| W3 | **B3 + B4**（writer + renderer 改造） | 2 dev days | 接触前端、最慢 |
| W3 | **B5 + B6**（CI guard + 微信回归） | 1 dev day | B 完整闭环 |
| W4 | 销售演示 + B 端试点 + 邀请制内测的 dogfooding | 由 A/B/C/D 保护 |

**总工作量**：~6.5 dev days，4 周窗口内可与正常迭代并行完成。

**首选执行顺序**：
1. 先 Track C + D（一上午搞完，立刻防止新债注入）
2. 再 Track A（销售演示前必须完成 A4 之前的部分）
3. 再 Track B（B 端机构试点前必须完成 B5）

---

## 8. 上线 / 回滚策略

| Track | 回滚方式 | 风险 |
|---|---|---|
| A | 删 `.github/workflows/tests.yml` 中新增 step；fixture 文件保留为 informational | 低（只是关 gate，不影响 runtime） |
| B | `presentation_type` 字段是新增的：旧 client 不读不会崩溃；writer 暂时回退为不设字段不会破坏现有渲染（但 contract guard 会 FAIL，需要同步关 guard） | 中（contract guard 与 writer 必须同步开关） |
| C | 删 workflow step + 还原 `check_secure_routers.sh` | 低 |
| D | 删 workflow step + 还原 `check_rls_on_create_table.sh` | 低 |

---

## 9. 与 AGENTS.md 硬约束对齐自查

- [ ] §0 Thin Wrappers Fat Skills：本计划没新增第二套 authority；presentation_type 是显式契约字段，不是路由器/分类器
- [ ] §Plan Directory Discipline：本文件挂到 INDEX.md（见下文）
- [ ] §3 Surgical Changes：每个 Track 改动文件清单显式列出，禁止"顺手清理"
- [ ] §3.6 Branch and Worktree Discipline：默认在当前分支推进；如某 Track 跑超过 2 天，独立 worktree
- [ ] §3.7 Aliyun SSH Write Boundary：本计划不涉及阿里云写操作
- [ ] §5 Fix Root Causes：Track A 故意暴露 lifecycle drift，禁止"批改 fixture 让 test PASS"
- [ ] §5.7 Single Authority Hard Gate：4 个 Track 各自的唯一权威已在 §2 列明

---

## 10. INDEX.md 挂载

本计划完成后，更新 `docs/plan/INDEX.md`：

1. 在"TutorBot 与统一聊天入口"主线条目末尾追加：
   > `2026-05-28-luban-4-week-critical-path-hardening-execution-plan.md` Track A/B 落地 2026-05-26 consolidation plan 的 Task 7 production validation 与 renderer 契约。

2. 在"生产部署"主线条目末尾追加：
   > `2026-05-28-luban-4-week-critical-path-hardening-execution-plan.md` Track C/D 把 secure_router / RLS gate 从 scripts 升级为 CI 强制（fail-on-new）。

3. 在"按领域索引"的"5. Routing / Security / Authority"（或新增"15. CI Gates"）章节增加本文件条目，状态 `Proposed v1`。

---

## 11. 完成标记 (Definition of Done)

整份计划全部 Done 的必要条件：

- [ ] Track A：10+ red-line scenario PASS + Langfuse trace 字段断言通过 + CI gate 跑过绿灯 + 1 次 drill 验证 gate 能阻断 + 至少 1 次销售场景真实环境验证
- [ ] Track B：contracts/turn.md 更新 + PresentationType enum + 所有 writer 显式设置 + renderer 无推断 + contract guard 强制 + 微信开发者工具回归证据归档
- [ ] Track C：baseline 文件 + FAIL_ON_NEW 模式 + CI step 跑过绿灯 + drill 验证
- [ ] Track D：baseline 文件 + FAIL_ON_NEW 模式 + CI step 跑过绿灯 + drill 验证
- [ ] INDEX.md 更新挂载完成
- [ ] 本文件状态从 `Proposed v1` 改为 `Implemented`，并补 Implementation Evidence 章节列出全部 commit SHA
