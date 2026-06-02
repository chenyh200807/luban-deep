# 鲁班评分真相覆盖率 + Golden Eval 战役计划 v2.2

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Goal:** Improve 一建建筑实务案例题批改准确率 by expanding scoring-point coverage, creating a human-gold eval set, and wiring the existing benchmark harness to compare Baseline / RAG / Artifact-first grading.
>
> **Architecture:** Do not build a generic Nexus-like platform. Reuse the existing `CaseGradingSkillKernel`, `learning_evidence` writeback, `source_compiler` compilers, and `services/benchmark` spine. Treat Pinecone Nexus as external validation of artifact-first direction, not as a system to copy.
>
> **Tech Stack:** Python services, existing Supabase question/rubric fields, existing `deeptutor/services/construction_grading/**`, existing `deeptutor/services/source_compiler/**`, existing `deeptutor/services/benchmark/**`, fixture-first golden data, optional later rubric version/provenance migration.

Status: Proposed v2.2 current authority, created 2026-05-31 after reviewing `artifacts/luban-nexus-research-report.md` and the critique of v2.1.

> **执行状态：BLOCKED — 协议待激活（protocol pending activation）。** 本 SOP 是"人 / 数据到位后即可执行"的标注协议，当前**尚不可启动**。三道启动闸门全绿才进入 Week 1 标注：
> - [ ] **U2 已解决**：≥2 名真·一建阅卷专家 + 仲裁 + 效度专家，档期签字（PO）。
> - [ ] **U1 已答复**：T1 真实学生答案可得性（可得 → real-first；不可得 → 降级"T2 为主 + 失真风险"，按 §6.9 半档/冷启动重定结论口径）。
> - [ ] **评分口径已冻结**：跨 2015–2025 规范改版的口径策略（dual-label / 剔除，见 §6.2）已定。
>
> 闸门全绿前，§6.1 / §5.2 的任何阈值均为"待激活目标"，不构成"已具备生产能力"的承诺。**关键路径排序：U2 ＞ U1 ＞ 人类一致性现实性(U3) ＞ 评分口径 ＞ 统计精密度（末端）**——先解锁人和真实答案，再谈一致性度量怎么算。
>
> **2026-06-01 决策：v0 轨道已激活**（数据完整性核查 + 真题 pilot 验证后）。题库 `FastAPI20251222/docs/2026/题库/` 已备齐 2015–2025 全 11 年、218 案例题（带官方答案/分值/规范引用），解锁 Stage 1 选题与评分口径闸门；但 U1（真实学生答案）/U2（人类专家）数据无法解锁。决策：**无人类专家期间走 §6.10「v0 AI 锚定管线」产出 directional 集**（pilot 已验证点级/总分可独立复现）；顶级人类 IRR（§6.1–§6.6）= v1 目标态，待真人到位。**v0 红线：不报人类 IRR、不宣称"通过生产门"，PO 抽查校验子集为唯一人类锚。**

Supersedes:

- [2026-05-31-luban-nexus-like-knowledge-engine-master-plan-v2.md](2026-05-31-luban-nexus-like-knowledge-engine-master-plan-v2.md) as an implementation authority. v2.1 remains a useful architecture risk study, but it over-scopes the execution path.
- [2026-05-31-luban-knowledge-compiler-systematic-implementation-plan-v1-2.md](2026-05-31-luban-knowledge-compiler-systematic-implementation-plan-v1-2.md) as a prototype evidence note.

Primary research authority:

- [artifacts/luban-nexus-research-report.md](../../artifacts/luban-nexus-research-report.md)

---

## 0. Executive Decision

### 0.1 Final decision

| Decision | v2.2 answer |
| --- | --- |
| 是否直接接入 Pinecone Nexus | 否 |
| 是否自研通用 Nexus-like Knowledge Engine | 否 |
| 是否吸收 Nexus 思想 | 是，只吸收 artifact-first、typed output、provenance、eval-driven 四个思想 |
| 当前主战场 | 采分点覆盖率、人工 golden eval、rubric/version/provenance、benchmark trend |
| P0 技术路线 | 方案 C+：强化现有结构化批改 + existing benchmark harness |
| 禁止项 | 不新建通用 `knowledge_artifacts` 平台，不新建 eval 子系统，不重建评分 kernel |

### 0.2 Why v2.1 is not the execution plan

v2.1 的方向有一部分正确：不接 Pinecone、坚持 provenance、要做 A/B/C eval。但它把“鲁班已有的领域版 Nexus-like 思想”误升级为“要新建通用 Knowledge Engine”。这违背 `artifacts/luban-nexus-research-report.md` 的核心结论：

- 鲁班已有 `CaseGradingSkillKernel` 的 artifact-first authority 链。
- 鲁班已有 `CaseGradingResult`、`learning_evidence`、错题/学情写回。
- 鲁班已有 `services/benchmark` eval spine。
- 真正缺的是采分点覆盖率、人工 golden 样本、rubric 版本/provenance，而不是新平台。

因此 v2.2 的执行原则是：**把资源投到数据与 eval，而不是投到中台。**

### 0.3 路线演进门（C+ 现在做 / 自研延后到有证据）

C+ 与"自研 Nexus-like 顶级系统"不是二选一。C+ 是通往那个系统的唯一正确路径：顶级主观题批改的壁垒不是架构图，是领域评分数据的覆盖率与质量 + 可持续 eval 闭环，而这两样正是 C+ 的全部内容。自研的更广 artifact/query 层应作为数据战役胜利后的**副产品**，由证据拉动，不由愿望拉动。

**当下（默认路线）= C+：** 复用 `case_kernel` + `learning_evidence` + `services/benchmark`，把 20题/100答 golden、采分点覆盖率、Baseline/RAG/Artifact-first 三路评测打通。不画六层架构图，不建通用 `knowledge_artifacts` 平台。

**进入"局部结构化扩张"的触发条件（全部满足才升级，缺一不升级）：**

- [ ] 20题/100答 golden run 完成，且 Artifact-first 在采分点 recall / 平均分差 / 可解释性 / token proxy 上**显著优于** Baseline 与 RAG（达 §5.2 production 阈值）。
- [ ] 采分点覆盖率扩张遇到真实瓶颈：`questions_bank.grading_rubric` / `grading_key.scoring_points` 现有字段**表达不下**所需结构（如点级 partial credit、表达变体、版本并存）。
- [ ] product owner 确认覆盖率扩张工作流可持续（人工标注产能到位，见 §6 SOP / §6.9 fallback）。
- [ ] benchmark trend 已稳定，新增结构能用同一 eval 证明收益、可回滚。

**升级方式（满足触发条件后）：** 仍是增量、由数据拉动——先加 §4 Task 5 预留的 `rubric_version` / `rubric_provenance` 最小字段，需要更多结构时再逐张表/逐字段加，每一步都过同一 benchmark gate。**禁止**一次性铺开 v2.1 式的全量 artifact 家族 / typed query protocol / 通用大表。

**反向门（出现以下信号则停在 C+，不升级）：**

- Artifact-first 分数准确率不优于 Baseline → 结构化数据没产生业务收益，只把它当 reviewer 工具。
- 人工标注产能不足以支撑 golden 与覆盖率扩张 → 先补数据产能，架构不动。

> 一句话：先用 20题/100答 证明"结构化评分数据真能提准确率"，证明了引擎自然长出来，证明不了那套引擎建了也是错的。

---

## 1. Single Authority

### 1.1 One business fact

鲁班当前要维护的一等业务事实是：

> 一道一建建筑实务案例题的评分点、点级命中、分差、错因和学习建议，必须能被现有评分 kernel 稳定复现，并能通过 benchmark golden set 量化验证。

### 1.2 Canonical authorities

| 业务事实 | 当前 authority | v2.2 动作 |
| --- | --- | --- |
| 主观题评分执行 | `deeptutor/services/construction_grading/case_kernel.py` | 复用，不新建第二评分器 |
| scoring point 输入 | `grading_key.scoring_points` > `questions_bank.grading_rubric` > projected rubric > open skill | 扩覆盖率，补版本/provenance |
| 评分结果结构 | `CaseGradingResult` | 保留，必要时增加 trace 字段 |
| 学习事实写回 | `learning_evidence.py` + `writeback.py` | 保留，防 candidate 污染 |
| eval spine | `deeptutor/services/benchmark/**` | 复用，新增 fixture and suite |
| source compilation | `deeptutor/services/source_compiler/question_compiler.py`, `rubric_compiler.py`, `standard_compiler.py` | 合并 prototype，不新增第二套 compiler |

### 1.3 Competing authorities to reject

- 新 `KnowledgeEngineEvalService` 与 `services/benchmark` 并行。
- 新 `QuestionCapsuleCompiler` 与 existing `question_compiler.py` 并行。
- 新 `RubricArtifactCompiler` 与 existing `rubric_compiler.py` 并行。
- 新通用 `knowledge_artifacts` 表覆盖 `questions_bank.grading_rubric` / `grading_key.scoring_points`。
- 让 RAG、graph edge、LLM prompt 直接决定分数。

---

## 2. Scope

### 2.1 P0 in scope

- 20 道一建建筑实务案例题。
- 100 份学生答案 golden set。
- Baseline / RAG / Artifact-first 三路对比。
- 采分点 coverage report。
- `services/benchmark` suite and fixture。
- Existing `case_kernel` artifact-first path trace。
- Prototype answer rubric extractor 合并到 existing source compiler authority。

### 2.2 P0 out of scope

- 通用 Nexus-like platform。
- `knowledge_artifacts` 通用大表。
- 新 `eval_cases` / `eval_runs` 生产表。
- 新 `KnowledgeEngineEvalService`。
- Neo4j / GraphRAG / LangGraph 编排层。
- Pinecone Nexus POC。
- 学生端新 UI。
- 生产写库。

---

## 3. Current Evidence

### 3.1 Existing code already has artifact-first grading

`CaseGradingSkillKernel.grade()` 的 authority 顺序已经是：

```text
grading_key.scoring_points
  -> questions_bank.grading_rubric
  -> projected rubric from existing fields
  -> open_skill fallback
```

这就是本项目的领域版 Context Compiler。v2.2 不新建这个能力，只补覆盖率、版本、provenance 和 eval。

### 3.2 Existing benchmark harness must be reused

Use these existing files:

- `deeptutor/services/benchmark/runner.py`
- `deeptutor/services/benchmark/registry.py`
- `deeptutor/services/benchmark/exam_quality_eval.py`
- `deeptutor/services/benchmark/quality_scoring.py`
- `deeptutor/services/benchmark/rag_replay.py`
- `deeptutor/services/benchmark/trend.py`
- `deeptutor/services/benchmark/fixtures/benchmark_phase1_registry.json`

Do not introduce a parallel eval service.

### 3.3 Prototype evidence must be treated honestly

Existing prototype evidence:

- 20 candidates
- 86 scoring points
- evidence alignment 67.4%
- publishable 75%
- 134 case rows
- artifact usable 70.9%
- token proxy reduction 88.2%

Interpretation:

- This proves answer-derived rubric extraction is promising.
- It does not prove grading accuracy.
- It does not meet a 70% evidence alignment gate yet; 70% must be written as a target, not a current pass.

---

## 4. Implementation Plan

### Task 1: Register the v2.2 authority

**Files:**

- Modify: `docs/plan/INDEX.md`
- Modify: `docs/plan/2026-05-31-luban-nexus-like-knowledge-engine-master-plan-v2.md`
- Read-only reference: `artifacts/luban-nexus-research-report.md`

- [ ] **Step 1: Mark v2.2 as current in `docs/plan/INDEX.md`**

Expected index wording:

```markdown
2026-05-31 v2.2 将路线收口为“评分真相覆盖率 + Golden Eval 战役”：不自研通用 Nexus-like 平台，复用 `CaseGradingSkillKernel`、`learning_evidence`、`source_compiler` 与 `services/benchmark`，P0 只做 20题/100答 golden、Baseline/RAG/Artifact-first 三路评测、采分点覆盖率、rubric version/provenance。
```

- [ ] **Step 2: Mark v2.1 as superseded**

Expected status:

```markdown
Superseded by v2.2; historical architecture risk study
```

- [ ] **Step 3: Run index consistency scan**

Run:

```bash
rg -n "v2\\.2|Superseded by v2\\.2|v2\\.1 current authority|deep-research-report" docs/plan/INDEX.md docs/plan/2026-05-31-luban-grading-truth-golden-eval-campaign-v2-2.md docs/plan/2026-05-31-luban-nexus-like-knowledge-engine-master-plan-v2.md
```

Expected:

- v2.2 appears as current authority.
- v2.1 does not appear as current authority.
- Research basis references `artifacts/luban-nexus-research-report.md`, not only attachment-local names.

### Task 2: Create the benchmark fixture contract

**Files:**

- Create: `deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json`
- Modify: `deeptutor/services/benchmark/fixtures/benchmark_phase1_registry.json`
- Test: `tests/services/benchmark/test_luban_case_grading_golden_fixture.py`

- [ ] **Step 1: Add fixture schema test first**

Create `tests/services/benchmark/test_luban_case_grading_golden_fixture.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "deeptutor"
    / "services"
    / "benchmark"
    / "fixtures"
    / "luban_case_grading_golden_v1.json"
)


def test_luban_case_grading_golden_fixture_schema() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["suite"] == "luban_case_grading_golden_v1"
    assert payload["exam_scope"] == "一级建造师建筑实务"
    assert isinstance(payload["cases"], list)
    assert payload["cases"], "golden fixture must include at least one smoke case"
    case = payload["cases"][0]
    required = {
        "case_id",
        "question_id",
        "question_text",
        "student_answer",
        "gold_score",
        "max_score",
        "gold_scoring_points",
        "gold_error_codes",
        "source_refs",
    }
    assert required.issubset(case)
    assert isinstance(case["gold_scoring_points"], list)
    assert all("point_id" in item and "hit" in item for item in case["gold_scoring_points"])
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
python -m pytest tests/services/benchmark/test_luban_case_grading_golden_fixture.py -q
```

Expected before fixture exists:

```text
FileNotFoundError
```

- [ ] **Step 3: Add a minimal smoke fixture**

Create `deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json`:

```json
{
  "suite": "luban_case_grading_golden_v1",
  "exam_scope": "一级建造师建筑实务",
  "version": "v1",
  "status": "smoke_fixture",
  "cases": [
    {
      "case_id": "smoke_fire_rating_001",
      "question_id": "smoke_q_fire_rating",
      "question_text": "某建筑防火构造案例题，要求说明防火分隔构造控制要点。",
      "student_answer": "应按规范设置防火分隔，并核对耐火极限。",
      "gold_score": 1.0,
      "max_score": 2.0,
      "gold_scoring_points": [
        {
          "point_id": "fire_partition",
          "label": "设置防火分隔",
          "hit": true,
          "score": 1.0
        },
        {
          "point_id": "fire_rating_limit",
          "label": "明确耐火极限要求",
          "hit": false,
          "score": 1.0,
          "miss_reason": "未写出具体耐火极限数值或等级"
        }
      ],
      "gold_error_codes": ["E02"],
      "source_refs": [
        {
          "source_type": "fixture",
          "source_id": "manual_smoke",
          "span": "人工 smoke case"
        }
      ]
    }
  ]
}
```

- [ ] **Step 4: Run the fixture test**

Run:

```bash
python -m pytest tests/services/benchmark/test_luban_case_grading_golden_fixture.py -q
```

Expected:

```text
1 passed
```

### Task 3: Add the three-arm POC runner as a thin benchmark adapter

**Files:**

- Create: `scripts/poc_luban_case_grading_three_arms.py`
- Test: `tests/scripts/test_poc_luban_case_grading_three_arms.py`

**2026-06-01 status: Implemented for v0 directional / shadow.**

- Runner: `scripts/poc_luban_case_grading_three_arms.py`
- Tests: `tests/scripts/test_poc_luban_case_grading_three_arms.py`
- Full report: `artifacts/luban_case_grading_three_arms/full_v0_directional/luban_case_grading_three_arm_full_report_20260601.md`
- Benchmark suite: `luban_case_grading_shadow` with `execution_kind=case_grading_eval`, `contract_domain=grading_quality_contract`, `case_tier=exploratory`; it is not part of `pr_gate_core`.
- Red line preserved: `gold=ground_truth_ledger`; `blind_grade` is only a second-opinion reference. The runner does not patch scores after `CaseGradingSkillKernel` returns.

- [ ] **Step 1: Write the test**

Create `tests/scripts/test_poc_luban_case_grading_three_arms.py`:

```python
from __future__ import annotations

from scripts.poc_luban_case_grading_three_arms import summarize_three_arm_results


def test_summarize_three_arm_results_reports_core_metrics() -> None:
    rows = [
        {
            "case_id": "c1",
            "arm": "baseline",
            "score_delta": 1.0,
            "point_recall": 0.5,
            "point_precision": 1.0,
            "hallucination": False,
            "token_proxy": 100,
        },
        {
            "case_id": "c1",
            "arm": "artifact_first",
            "score_delta": 0.0,
            "point_recall": 1.0,
            "point_precision": 1.0,
            "hallucination": False,
            "token_proxy": 40,
        },
    ]
    summary = summarize_three_arm_results(rows)
    assert summary["baseline"]["case_count"] == 1
    assert summary["baseline"]["mean_abs_score_delta"] == 1.0
    assert summary["artifact_first"]["mean_point_recall"] == 1.0
    assert summary["artifact_first"]["mean_token_proxy"] == 40.0
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
python -m pytest tests/scripts/test_poc_luban_case_grading_three_arms.py -q
```

Expected before script exists:

```text
ModuleNotFoundError
```

- [ ] **Step 3: Implement the summary-only thin adapter**

Create `scripts/poc_luban_case_grading_three_arms.py`:

```python
from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any


def _avg(values: list[float]) -> float | None:
    return round(float(mean(values)), 4) if values else None


def summarize_three_arm_results(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        arm = str(row.get("arm") or "").strip()
        if arm:
            grouped[arm].append(row)

    summary: dict[str, dict[str, Any]] = {}
    for arm, arm_rows in sorted(grouped.items()):
        summary[arm] = {
            "case_count": len(arm_rows),
            "mean_abs_score_delta": _avg([abs(float(row["score_delta"])) for row in arm_rows]),
            "mean_point_recall": _avg([float(row["point_recall"]) for row in arm_rows]),
            "mean_point_precision": _avg([float(row["point_precision"]) for row in arm_rows]),
            "hallucination_rate": _avg([1.0 if row.get("hallucination") else 0.0 for row in arm_rows]),
            "mean_token_proxy": _avg([float(row["token_proxy"]) for row in arm_rows]),
        }
    return summary
```

- [ ] **Step 4: Run the test**

Run:

```bash
python -m pytest tests/scripts/test_poc_luban_case_grading_three_arms.py -q
```

Expected:

```text
1 passed
```

### Task 4: Reconcile prototype compiler with existing source compiler authority

**Files:**

- Modify: `deeptutor/services/source_compiler/rubric_compiler.py`
- Modify: `deeptutor/services/source_compiler/answer_rubric_extractor.py`
- Test: `tests/services/source_compiler/test_answer_rubric_extractor.py`
- Test: `tests/services/source_compiler/test_rubric_evidence_aligner.py`

- [ ] **Step 1: Document authority in `rubric_compiler.py`**

Add a short module-level comment:

```python
# Authority note:
# `rubric_compiler.py` remains the canonical source-compiler module for rubric
# candidates. Answer-derived extraction helpers must be called from here or
# imported here; do not create a parallel Question/Rubric compiler service.
```

- [ ] **Step 2: Move any production import path through `rubric_compiler.py`**

If a script imports directly from `answer_rubric_extractor.py`, keep that direct import only for prototype scripts. Production-facing scripts should import via `rubric_compiler.py`.

- [ ] **Step 3: Run source compiler tests**

Run:

```bash
python -m pytest tests/services/source_compiler/test_answer_rubric_extractor.py tests/services/source_compiler/test_rubric_evidence_aligner.py -q
```

Expected:

```text
6 passed
```

### Task 5: Replace v2.1 schema expansion with C+ schema policy

**Files:**

- Modify: this plan if schema direction changes
- Future migration only after POC: `supabase/migrations/*rubric_version*.sql`

P0 schema policy:

- Do not create `knowledge_artifacts`.
- Do not create production `eval_cases` / `eval_runs`; use benchmark fixtures first.
- Do not create production `question_rubrics` unless `questions_bank.grading_rubric` becomes a proven bottleneck.
- Add only minimal version/provenance fields after POC.

Candidate future fields:

```sql
alter table public.questions_bank
  add column if not exists rubric_version text,
  add column if not exists rubric_provenance jsonb;
```

Migration is gated by:

- benchmark suite exists,
- 20题/100答 golden set exists,
- product owner confirms rubric coverage expansion workflow,
- dry-run proves no client payload leak.

---

## 5. A/B/C Evaluation Gate

### 5.1 Arms

| Arm | Description | Must reuse |
| --- | --- | --- |
| Baseline | Current grading without curated scoring-point injection | Existing `CaseGradingSkillKernel` fallback behavior |
| RAG | Retrieval-grounded grading using existing RAG context | Existing RAG/replay tooling |
| Artifact-first | Existing `case_kernel.grade()` with `grading_key.scoring_points` or curated `grading_rubric` | Existing kernel and learning evidence path |

### 5.2 Metrics

| Metric | Shadow threshold | Production threshold |
| --- | ---: | ---: |
| 平均分差 | <= 1.5 分 or <= 15% max score | <= 1 分 or <= 10% max score |
| 采分点 recall | >= 85% | >= 90% |
| 采分点 precision | >= 80% | >= 85% |
| 错因诊断准确率 | >= 75% | >= 85%（**v1 为 directional**：错因码不进 v1 生产硬门，见 §5.2.1 / §6.1，硬门留 v2） |
| hallucination rate | <= 5% | <= 3% |
| token proxy | <= baseline | >= 40% reduction vs RAG |
| latency | <= baseline 1.8x | <= baseline 1.5x |
| learner writeback pollution | 0 high-severity | 0 |

### 5.2.1 Human ceiling（模型阈值的上界约束）

> 上表的模型阈值（recall ≥90% / precision ≥85%）**是相对人类一致性的相对标尺，不是绝对标尺**。**两道门必须分开**（这是原则，换数据也不变）：
>
> - **① Gold 信度门（不可下调）**：人类专家之间的一致性必须先达 §6.1 门槛。**达不到不是"下调模型门"，而是 gold 本身不合格** → 按 §6.6 回炉/重标或整体退 directional。信度门是数据集**准入资格**，不能用模型表现豁免。
> - **② 模型生产门（仅在 ① 通过后才谈）**：用**与 human-human 相同的度量**做**非劣效比较**——看 model-vs-专家的一致性是否落入 human-human 一致性的 CI 区间（"进入人类分歧带"）。模型也可能**超过**人类，不预设方向。
> - **不可跨度量比较**：recall/precision 不在一致性系数的数轴上，不能相乘 / "等比换算"，只作 model-vs-gold 的**内部口径**报告，不与人类一致性直接比。
> - 具体度量、非劣效边界 δ、CI 算法由 §6.1 指向的 IRR 模块据校准卷标定；本节只定**原则**（信度门不可豁免、同度量比较、不可跨度量换算），不冻结公式。

### 5.3 Decision rules

- If Artifact-first beats Baseline and RAG on recall, score delta, explainability, and token proxy, expand scoring-point authoring.
- If Artifact-first does not beat Baseline on score delta, stop runtime integration and use it only as reviewer support.
- If citation accuracy fails, keep citations internal-only.
- If learner writeback pollution occurs, disable learner writeback for this path.

### 5.4 2026-06-01 full v0 directional result

Full run: 20 questions / 100 synthetic AI-anchored samples, 3 arms, deterministic metrics. This is a directional / shadow result, not a production gate.

| Arm | Mean abs score delta | Point recall | Point precision | Term recall | Term precision | Hallucination | Token proxy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 2.6305 | 0.4059 | 0.5450 | 0.4630 | 0.6200 | 0.6900 | 812.2 |
| rag | 2.6305 | 0.4059 | 0.5450 | 0.4630 | 0.6200 | 0.6900 | 1059.2 |
| artifact-first | 2.1338 | 0.6508 | 0.7890 | 0.7611 | 0.9000 | 0.0000 | 730.5 |

Decision: **directional GO for continued structured scoring-point investment; NO-GO for production runtime promotion before kernel-rule work and v1 human validation.**

Key findings:

- Artifact-first is better than baseline/RAG on score delta, recall, precision, hallucination, and token proxy.
- RAG evidence reaches `CaseGradingSkillKernel` evidence refs but does not enter scoring decisions; full run had `score_changed_samples=0`, so current RAG is not a fair scoring arm unless reworked into `retrieval -> rubric candidate -> structured validation -> grading_key`.
- Artifact-first weakness distribution: `compiled_term_recall_gap=47`, `term_form_normalization_gap=8`, `compiled_term_overmatch=3`, `keyword_context_false_positive=2`, `penalty_rule_unsupported=1`.
- §0.3 evolution gate reading: structured scoring data is worth continued investment, but the evidence supports expanding the scoring-truth layer, not building a generic Nexus-like platform yet.

### 5.5 2026-06-01 kernel-rule support after-run

Scope: PO-approved minimal `CaseGradingSkillKernel` authority change plus route-B artifact compiler updates. This remains v0 directional / shadow.

Implemented:

- `penalty_rules` with `multi_answer_no_score` for Q4-style "多答不得分" scoped zeroing.
- Official-term normalization for punctuation / brackets / slash alternatives / `或` variants, with no synonym expansion.
- Compiled-term overmatch controls: reject overbroad terms such as `原则`, remove full-label fallback, and preserve fill-blank `answer_label` context.

After-run report: `artifacts/luban_case_grading_three_arms/kernel_rule_support_20260601/kernel_rule_support_lift_report_20260601.md`.

| Arm | Mean abs score delta | Point recall | Point precision | Term recall | Term precision | Hallucination | Token proxy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 2.5928 | 0.4376 | 0.6150 | 0.4537 | 0.6500 | 0.7100 | 812.2 |
| rag | 2.5928 | 0.4376 | 0.6150 | 0.4537 | 0.6500 | 0.7100 | 1059.2 |
| artifact-first | 1.5778 | 0.7487 | 0.8888 | 0.8273 | 0.9600 | 0.0000 | 684.5 |

Before -> after artifact-first lift:

- Mean abs score delta: `2.1338 -> 1.5778` (`-0.5560`, 26.1% relative reduction).
- Point recall: `0.6508 -> 0.7487`.
- Point precision: `0.7890 -> 0.8888`.
- Term recall: `0.7611 -> 0.8273`.
- Term precision: `0.9000 -> 0.9600`.
- Hallucination: `0.0000 -> 0.0000`.
- Token proxy: `730.5 -> 684.5`.

Targeted gap reading:

- `penalty_rule_unsupported`: `1 -> 0`; Q4-S4 now scores `3.0/3.0`.
- `term_form_normalization_gap`: count `8 -> 9`, but absolute error severity `10.3511 -> 7.6249`; remaining items are mostly list-rule / extraction quality, not only punctuation form.
- `compiled_term_overmatch`: count `3 -> 5`, but absolute over-award severity `4.2250 -> 1.8583`; severe Q10 fill-blank cross-match was fixed, residuals are smaller point-specific context issues.
- `compiled_term_recall_gap`: `47 -> 38`; still the dominant backlog.

§0.3 evolution gate reading: this strengthens the case for structured scoring data investment and supports planning v1 validation slices. It still does not justify production promotion or generic Nexus-like platform construction.

### 5.6 2026-06-01 v1 human validation slice handoff

PO approved starting v1 validation slices + artifact versioning. The first human gate is prepared and awaiting real PO labels.

Package:

- `artifacts/luban_human_validation_v1/po_slice_20260601/po_review_packet.json`
- `artifacts/luban_human_validation_v1/po_slice_20260601/po_labels_template.csv`
- `artifacts/luban_human_validation_v1/po_slice_20260601/internal_slice_manifest.json`
- `artifacts/luban_human_validation_v1/po_slice_20260601/human_validation_protocol.md`

Selection:

- 24 samples.
- 12 cases.
- 131 point-label rows.
- deterministic selection: positive-score frontier -> penalty-rule cases -> largest under-score deltas.

Protocol:

- `ground_truth_ledger` remains v0 gold for comparability.
- PO labels are a new higher-authority validation layer.
- PO packet is blind: no baseline/RAG/artifact-first predictions, no ledger labels, no blind_grade.
- Metrics script compares `human-vs-ledger` and `human-vs-artifact-first` after human labels return.

Artifact-versioning seed:

- `internal_slice_manifest.json` records `schema_version=grading_artifact.v1`, `version_id`, `content_hash`, and source authority for each selected case artifact.
- This is a handoff seed, not a production artifact store.

Stop condition reached: human/PO labeling is now required. No AI may substitute for this label step.

### 5.7 2026-06-01 no-human v1.5 false-miss correction

PO adversarial spotcheck found that the previous no-human v1.5 headline (`460/485=94.85% deterministic`, `类B=0`, "strong GO") was inflated by a false-miss bug. That value is now explicitly superseded and must not be quoted as a valid gate result.

Root cause:

- Empty-anchor points were allowed to become certified misses (`hit=miss`, `score=0`, `is_deterministic=true`, `class A`).
- Official `correct_answer` was not included as a case-local exact anchor source, despite §6.10 treating official answer as one of the three gold anchors.
- Stale independent A/B triage labels could re-demote residual class B items back to class A.

Correction r1:

- Official answer is now a local exact-match anchor source (`source_class=official_answer`), still no RAG and no synonym expansion.
- No-verifiable-term labels are `verifiable=false`, `hit=unverifiable`, `score=null`, `resolution_class=B`.
- Old independent A/B labels are no longer applied by default; `verifiable=false` items cannot be demoted to class A.
- Junk non-terms such as `可选项`, scoring instructions, pure numbering, and estimate-score fragments are filtered from required terms.

Corrected shadow result:

- point labels: `485`
- deterministic labels: `470/485 = 96.91%`
- residual labels: `15`
- class distribution: `A=470`, `B=15`, `C=0`
- PO queue: `15`; external expert queue: `0`
- deterministic subset comparison: artifact-first mean abs delta `0.9607`, baseline/RAG `3.1315`.

Interpretation: structured scoring data remains valuable, and artifact-first still beats baseline/RAG on the corrected deterministic subset. However, no-human v1.5 is not allowed to self-certify from same-model agreement. The next gate is the corrected PO spotcheck package at `artifacts/luban_no_human_v1_5/spotcheck_corrected_20260601/`. Full correction report: `artifacts/luban_no_human_v1_5/20260601_textbook_anchored/FINDING_false_miss_correction_r1.md`.

### 5.8 2026-06-01 no-human v1.5 list-rule denominator correction r2

Claude independent r2 spotcheck confirmed the r1 false-miss fix, but exposed a narrower bug: some list-rule points were under-scored because `required_terms_v1_5` still included junk anchors, official-answer sentence fragments, or non-term fallback fragments. This inflated the list denominator, so an answer containing all true official list terms could receive only partial credit.

Correction r2:

- List-rule denominator now prefers explicit official list terms and does not use repaired sentence-level anchors as the scoring denominator.
- List splitting respects bracket depth, so terms containing punctuation inside brackets are not split incorrectly.
- Junk/non-term anchors are filtered (`可选项`, scoring instructions, pure numbering, `三项`, quote fragments).
- Risky substring contexts such as `上厕所的` matching the official term `厕所` are no longer auto-certified; they become `verifiable=false`, `resolution_class=B`.
- PO spotcheck excerpts now keep enough answer context to avoid hiding the relevant answer span.

Corrected r2 shadow result:

- point labels: `485`
- deterministic labels: `469/485 = 96.70%`
- residual labels: `16`
- class distribution: `A=469`, `B=16`, `C=0`
- PO queue: `16`; external expert queue: `0`
- explicit list-denominator points: `24`
- filtered junk/non-term anchors during squeeze: `5`
- remaining junk / overlong sentence anchors in `required_terms_v1_5`: `0 / 0`
- substring context risks deferred to B: `1`
- deterministic subset comparison: artifact-first mean abs delta `1.1536`, baseline/RAG `3.2556`.

Q11 list-rule evidence after r2:

- P1 denominator = `生活区 / 办公区 / 材料加工和存放区`; Q11-S1 scores `3.0/3.0`.
- P2 denominator = `体温计 / 口罩 / 消毒剂`; Q11-S1 scores `1.5/1.5`.
- P3 denominator = `食堂 / 盥洗室 / 厕所`; Q11-S1 scores `1.5/1.5`.

Interpretation: the previous r1 corrected headline (`470/485 = 96.91%`) is now superseded by r2 (`469/485 = 96.70%`). This is a more honest number: one substring-only context is now sent to PO instead of being certified. Artifact-first still materially beats baseline/RAG on the corrected deterministic subset, but no-human v1.5 remains directional/shadow only. Next gate remains PO/human spotcheck, now at `artifacts/luban_no_human_v1_5/spotcheck_r2_corrected_20260601/`. Full r2 finding: `artifacts/luban_no_human_v1_5/r2_corrected_list_rule_20260601/FINDING_list_rule_denominator_correction_r2.md`.

### 5.9 2026-06-02 no-human v1.5 content_markdown re-anchor r3

Claude PDF visual sampling confirmed that the cleaned KB JSON `content_markdown` is faithful textbook text. The no-human collector therefore now treats `content_blocks[].content_markdown` as the primary literal-term authority and excludes LLM-derived JSON fields such as `grading_keywords`, `exam_matrix`, and `knowledge_cards` from scoring-term anchors.

Correction r3:

- Textbook corpus records are built from `content_markdown` blocks only, with `chunk_id`, `node_code`, `page_num`, and source path.
- Textbook anchors are preferred over `official_answer`; if a point only anchors to `official_answer`, it becomes `official_answer_weak` and is routed to class B.
- Calculation points are marked `point_type=calculation`, `anchor_source=calculation`; they use deterministic numeric validation and are not counted as textbook-term anchors.
- Figure-label points are marked `point_type=figure_label`, `anchor_source=exam_figure`; junk terms such as `图中`, `须含`, `起重机` are not denominator terms.
- Cross-subject / non-textbook points are marked `anchor_source=non_textbook` and routed to class B. No AI world knowledge is used for certification.

Corrected r3 point classification:

- total scoring points: `97`
- point types: `text_term=75`, `calculation=15`, `figure_label=3`, `non_textbook=4`
- anchor sources: `textbook=57`, `official_answer_weak=18`, `calculation=15`, `exam_figure=3`, `non_textbook=4`
- true textbook-anchor point coverage: `57/97 = 58.76%`

Corrected r3 label-level shadow result:

- point labels: `485`
- deterministic labels: `369/485 = 76.08%`
- residual labels: `116`
- class distribution: `A=369`, `B=116`, `C=0`
- PO queue: `116`; external expert queue: `0`
- deterministic subset comparison: artifact-first mean abs delta `0.8934`, baseline/RAG `2.6885`

Interpretation: r3 intentionally lowers the no-human certification headline. This is not a regression; it removes false textbook certification and converts official-answer-only / non-textbook / uncertain points into an honest PO queue. Full r3 finding: `artifacts/luban_no_human_v1_5/content_markdown_reanchor_20260602/FINDING_content_markdown_reanchor_r3.md`.

### 5.10 2026-06-02 r4 pilot gate: verify-on-write and short-anchor guard

Claude follow-up review found two residual collector bugs in r3:

- Some points were marked `anchor_source=textbook` even though the point-level `chunk_id` was empty or the quote could not be verified against the target `content_markdown` chunk.
- Some single-term anchors were too short and generic (`防护`, `浇筑`, `限制`), creating over-credit risk.

Correction r4:

- A point can be written as `anchor_source=textbook` only when every required term has a valid textbook anchor with non-empty `chunk_id`, non-empty quote, and the quote is present verbatim in that chunk's `content_markdown`.
- Legacy JSON `content` fallback is disabled; only `content_blocks[].content_markdown` is textbook authority.
- Mixed textbook + official-answer weak terms no longer certify the whole point as textbook.
- Short common single-term anchors must be expanded from the point text to a longer phrase that also verifies against `content_markdown`; unresolved terms are downgraded to B.
- `exam_figure` is restricted to `point_type=figure_label`; text terms cannot borrow stem / figure anchors.

Corrected r4 pilot-gate classification:

- total scoring points: `97`
- point types: `text_term=75`, `calculation=15`, `figure_label=3`, `non_textbook=4`
- anchor sources: `textbook=38`, `official_answer_weak=36`, `calculation=15`, `exam_figure=3`, `non_textbook=5`
- verified textbook anchors: `38/38`; invalid textbook anchors: `0`
- current short common single-term anchors: `0`
- true textbook-anchor point coverage: `38/97 = 39.18%`

Corrected r4 label-level shadow result:

- point labels: `485`
- deterministic labels: `274/485 = 56.49%`
- residual labels: `211`
- class distribution: `A=274`, `B=211`, `C=0`
- PO queue: `211`; external expert queue: `0`
- deterministic subset comparison: artifact-first mean abs delta `0.7065`, baseline/RAG `2.1438`

Interpretation: r4 supersedes r3 and intentionally lowers the certification headline again. This is a stricter and more defensible number, not a product regression. Full-KB extraction remains blocked at the pilot gate until Claude/PO independently verifies the r4 audit packet. Full r4 finding: `artifacts/luban_no_human_v1_5/content_markdown_reanchor_pilot_gate_20260602/FINDING_pilot_gate_verify_on_write_r4.md`.

---

## 6. Data Production Plan — Golden 数据生产 SOP（全球顶尖标准）

> **设计原点**：没有双人独立标注 + 一致性度量 + 仲裁的 golden，不叫顶尖 golden，叫"一个人的意见"。本 SOP 与"随便标标"的分水岭在 **Stage 0 体系先行 + Stage 4 信度/效度双门 + 分层真实答案**。
>
> **Scope**：本 SOP 只覆盖 **E 系列错因码**（案例 / 简答，`error_codes.py:44-57`）。M 系列（选择题，`error_codes.py:60-71`）是 exact-match 评分，另立 golden，不需要点级一致性。

### 6.1 North-star metrics（验收门语义 — 统计实现见附录 A）

本表只声明**门槛语义**与硬门 / directional 分野。**用哪个估计量、怎么算 CI、为什么是这个统计，不在计划文档冻结**（在零数据时把依赖未来数据特征的 estimator 选择当成"已冻结结论"，正是三轮打补丁漩涡的燃料）——这些由附录 A 指向的 IRR 模块据 Stage 4 校准卷标定。

| 北极星 | v1 门槛（语义） | 状态 |
| --- | --- | --- |
| 点级命中一致性 | 按题聚合的一致性 CI 下界 ≥ 0.75（聚合方式须防"长 rubric 操纵"） | 硬门 |
| 总分一致性 | 题内归一化后一致性 CI 下界 ≥ 0.80 | 硬门 |
| 错因码一致性 | 逐码披露 + 实例数 + CI | **v1 directional**（样本不足，不进硬门；§5.2 错因诊断 85% 同步降 directional） |
| Provenance | 100%（含评分口径：当年 / 当前规范） | 硬门 |
| 效度 | 官方细则逐点核验，无系统性偏差 | 定性门（§6.6-E） |

> **保留的统计原则（换数据也不变，故留文档；具体方法见附录 A）**：① 主一致性系数必须对 prevalence 稳健、并列披露多系数防单系数操纵；② CI 必须反映点 nested in 答案 nested in 题的**聚类**，不得按独立单位假装样本量；③ 聚合方式不得允许长 rubric 操纵总体；④ 信度 ≠ 效度。
>
> **诚实校准**：100 份 = go/no-go（大效应），不足以认证"recall 90% vs 88%"小差异；错因码级不确定性大（一律 directional）。增长 v1=100 → v2≥300 → 稳态≥1000，老版冻结、新版追加。

### 6.2 Stage 0 — 体系先行（标注前必须冻结，否则后面全废）

- [ ] **交付 IRR 计算模块 + 校准卷标定（不在文档冻结具体方法）**：实现 `deeptutor/services/benchmark/irr_scoring.py`——与现有 `quality_scoring.py` 同构的**零依赖纯函数**文件（~150 行上限、frozen dataclass、寄生 benchmark，**不新建 eval 子系统**、不引 scipy/pingouin；点级按题聚合一致性 / 题内归一化总分一致性 / per-code 一致性 + cluster bootstrap CI 均纯标准库可写，ICC 等需 scipy 的项不进硬门、可砍）。用首批 5–10 份**校准卷**做敏感性分析，由统计负责人据实际 prevalence / 聚类**标定并冻结**主报口径，决策记入附录 A。⚠️ 若纯标准库 cluster bootstrap 数值不稳，回退解析方差 + 显式 design-effect 披露。
- [ ] **错因码配额表**：尽量拉高每码实例数，但 v1=100 份下多数 E 码达不到可靠估计门槛（n≈25–30/码），故 **v1 错因码一致性一律 directional、不设生产硬门**；每码报实例数 + per-code AC1 + CI，标 `code_status`（certified / uncertified_v1 / directional）。生产级错因码认证（n≥25/码）留到 v2。
- [ ] **错因码标注手册**：E01–E12 每码 1 正例 + 1 反例；100% 过 `validate_error_code`（`error_codes.py:103`）。⚠️ `validate_error_code` 只查"码是否注册"，**不区分系列**——registry 同时含 M01–M10 / `unknown_error`（`error_codes.py:85-89`），故 schema test **必须额外校验 `gold_error_codes` 全部 `series=="E"`**，禁止 M 系列 / `unknown_error` 进入案例题 gold。
- [ ] **采分点 schema + 强化 fixture test**：沿用 `gold_scoring_points`（point_id / label / hit / score / miss_reason）；§4 Task 2 的 schema test 升级为校验：`gold_scoring_points` 各 `score` 之和 == `gold_score`、`gold_score ≤ max_score`、每个 `hit=false` 必有 `miss_reason`、`gold_error_codes` E-only、`source_refs` 非空且含规范版本、扩展字段不覆盖 core 字段。
- [ ] **效度锚定 + 评分口径**：每个采分点 trace 到官方评分标准 / 标准答案 / 规范条文；争议点记 `scoring_decision` + 裁量理由，禁止悄悄抹平。**因真题跨 2015–2025、规范多次改版**：每题必须声明评分口径（按**考试当年**官方答案/规范，还是按**当前**规范）；两者冲突时 **dual-label 或剔除**，不得混进同一个 `gold_score`。
- [ ] **rubric 版本化**：rubric 是一等 artifact，独立 change log（这样 v2 提升能区分是"标注者变好"还是"rubric 变清晰"——后者其实降低了难度，是一种 contamination）。
- [ ] **标注员名册**：真·一建阅卷专家 / 名师 ≥2 + 资深仲裁 1 + 第三方效度专家 1；非众包；PO 签字。
- [ ] **专家工时预算 + 档期确认（拆分计列，勿低估）**：~20min/份很可能低估"总分 + 点级 + 多标签错因 + 表达变体 + 证据 ref"的实际耗时；预算须拆为 独立标注 / 仲裁 / rubric change / 效度审查 / QA 入库 五项分别估算，不是一个 67 工时的整数。档期不足 → 走 §6.9 fallback 半档，不假装满档。

### 6.3 Stage 1 — 选题（分层 + 配额，数据已有 ✅）

从 `docs/2026` 的 2015–2025 真题选 20 道案例题：

- **分层**：topic（安全 / 质量 / 进度 / 合同索赔 / 防水 / 地基 / 主体 / 验收）× 题型（程序 / 计算 / 规范 / 表达）× 难度。
- **配额校验**：覆盖矩阵保证每个待认证 E 码 ≥8 实例（跨题累计），每高频专题 ≥2 题。
- **数据来源（已核实）**：`FastAPI20251222/docs/2026/题库/{年}/FINAL_CLEANED_EXAM_V{年}.json`（跨仓库，非 deeptutor），每题含 `stem / correct_answer（分点满分答案）/ analysis（规范依据）/ score / difficulty / predicted_node`；规范版本见同目录 `标准文件/*.json`。采分点从 `correct_answer` 分点结构拆解起草，分值由专家校准（标"非官方"）。
- **罚则题筛选**（pilot 实证）：含"多答不得分"等**全局耦合罚则**的题，按 §6.10 **固化罚则为可执行规则后纳入**（写明牵连范围 + 计数口径），不得留模糊判分。
- 产出 `golden_question_manifest.json`（题 + 标准答案 + 规范源 ref）。
- ⚠️ **承认不可消除的泄漏**：真题 + 标准答案是公开的，大概率已在模型训练语料。故 golden 测的是**"评分能力"**（给定学生答案 + rubric 判命中），不是**"答案记忆"**——选题与 schema 必须服务这个目标。

### 6.4 Stage 2 — 学生答案（分层，真实优先，打分致盲）

| 层级 | 来源 | 占比目标 | 说明 |
| --- | --- | --- | --- |
| T1 真实作答 | 脱敏真实学生答案 / 仿真招募考生作答 | 越高越好 | 最高价值锚点，定义"真实错误长什么样"。 |
| T2 LLM 造坯 + 人工改写 | LLM 造 + 专家改写到像真人 | 兜底 | **按真实错误数分布 + 错因共现矩阵造组合错误，禁止孤立单错**（真实学生是多错相关、知识半懂）。 |

- 每题 5 份，覆盖六类 archetype（完整 / 半对 / 口号化 E04 / 近义表达 / 漏关键条件 E08 / 误用规范 E10）。
- **困难样本子层（带配额）**：近义正确表达、对关键词但逻辑错、口号化、误用规范、漏条件——grader 最易翻车、eval 最值钱处。
- **打分时对 T1/T2 来源致盲**：provenance 记录，但标注者打分时不可见，防"真人写的所以更宽容"偏置。
- 产出 `student_answers_raw.jsonl`（标 `source_tier`，打分时隐藏）。
- 验收：六类每题各 ≥1；(采分点 × 错因码) 覆盖矩阵 + 配额无空行。
- ⚠️ **T1 来源是本方案最大不确定性**：若 T1 ≈ 0，诚实改写为"T2 为主 + 标注分布失真风险"，不宣称 real-first（见 §6.9 U1）。
- **v0 现实（2026-06-01）**：题库无真实学生答案、T1=0 → 走 §6.10「AI 构造」：按 archetype 注入**已知错误**造学生答案 + 记录**构造台账**（programmatic ground truth，比普通 T2 更强——命中与否构造时即写死，非事后主观判断）。标 `source_tier=T2-constructed`，结论按 v0 directional。

### 6.5 Stage 3 — 双盲独立标注

> **v0（无人类专家）**：用**多个独立 subagent 盲标**（context 隔离模拟独立性）+ 构造台账对照核验（§6.10）替代双人专家；下列双人专家流程为 v1 目标态。

- 2 名专家互不可见地各标全部 100 份：总分 + 点级 hit/miss + miss_reason + 错因码（**多标签** E01–E12）+ ability_dimension（错因码自动映射，`error_codes.py:45-56`）+ 可接受表达变体 + 证据 ref。
- 工具直接产出 fixture 格式，错因码即时 `validate_error_code`。
- **item 顺序按标注者随机化**（消顺序效应）。
- **埋 ~10% 重复锚点 item**（同一份答案在序列里出现两次，**两次间隔 ≥30 个 item** 防记忆效应，标注者不知）→ 测 **intra-rater test-retest**。注：n≈10 重复只能**定性抓严重漂移 / 疲劳，不进硬门**。
- 产出 `annotations_rater_A.json` / `annotations_rater_B.json`。

### 6.6 Stage 4 — 一致性门 + 仲裁 + 效度验证（信度 ≠ 效度，分野在这一步）

**A. 信度（reliability）——报在仲裁前的独立标签上**
- 用 IRR 模块（§6.1 / 附录 A）对仲裁前 `annotations_rater_A/B` 计算点级 / 错因码 / 总分一致性 + CI；**按 question 和 error_code 分别 breakdown**，定位 WHERE 不一致，而非只看汇总。
- 未达 §6.1 门槛 → 不改数据，回炉：rubric 校准会 + rubric 版本 +1，重标该批。

**B. item 三态处置**（取代"只有 batch 回炉"）
- `PASS`：达标 → certified gold。
- `RECALIBRATE`：分歧源于 rubric 歧义 → 改 rubric → 重标。
- `RETIRE / FLAG_LOW_RELIABILITY`：分歧源于答案**固有歧义** → `reliability=low`，移出认证集 / eval 降权，但**保留为困难样本**信号。

**C. 分歧分类学**（把 adjudication_log 变成 rubric 改进引擎）
- 每条分歧打类型：rubric 歧义（→改 rubric）/ 标注者笔误（→校准）/ 答案固有边界（→borderline 标记）。
- intra-rater 埋点显示**严重漂移**（定性，非阈值门）→ 该标注者数据复核。

**D. 仲裁**
- 分歧项交资深仲裁裁定，记 `adjudication_log`（谁 / 为什么 / 类型）。
- ⚠️ 仲裁后 gold = A/B/仲裁三方混血，**不独立于仲裁者**；**IRR 永远报仲裁前的独立标签，不报仲裁后**（防"共识赝品"虚高）。

**E. 效度（validity）——独立于信度的定性门（非统计门）**
- **主锚 = 官方评分标准 / 规范条文逐点机械核验**（§6.3 已 trace）：这才是外部 ground truth，不是再加一个噪声专家。
- 补充：第三名独立专家盲评一个**预注册分层切片**（topic × source_tier × difficulty × borderline 分层 + 全部 RETIRE/borderline 项 + 随机 ≥20 份），**不得看到 A/B/仲裁结论**；只在"答案固有歧义"项上裁量。
- 门是**定性的"无系统性偏差"**，不伪装成统计阈值——单专家 vs 仲裁在小切片上 CI 太宽，无法支撑统计断言。

**验收门（生产硬门，v1）**：点级一致性 ≥0.75、总分一致性 ≥0.80（门槛语义与 CI 口径见 §6.1 / 附录 A）、provenance 100%（含评分口径）、adjudication_log 100% 覆盖分歧项、效度定性门通过（官方细则逐点核验无系统性偏差）。
- **错因码一致性 v1 为 directional 报告项，不进生产硬门**：如实披露 per-code AC1 + 实例数 + CI（错因码硬门留到 v2，按 prevalence/CI 半宽预注册样本量）。
- **gold 信度门不可下调**（见 §5.2.1）：人类未达上述阈值即数据集不合格 → 回炉或整体退 directional，不得用模型表现豁免。
- intra-rater 仅作漂移监控，不进硬门。

产出：冻结的 `luban_case_grading_golden_v1.json` + `agreement_report.json`（信度 / 效度 / CI / 分歧清单 / per-question + per-code breakdown）。

### 6.7 Stage 5 — 冻结、版本化、防污染

- **held-out**：禁止进任何 prompt / few-shot / 训练 / RAG（防 eval 作弊）。
- **不可变**：v1 冻结，修正走 v1.1 追加，不就地改；变更走 change-control（提案 → 审 → 版本号）。
- **gold 内容 hash 登记**，检测意外灌入 RAG / few-shot。
- **v1 起就拆两份**：`calibration/dev`（可反复用于 rubric 扩张、迭代、趋势）与 `sealed holdout`（封存，**只在最终 go/no-go 一次性打开后即版本冻结**）。迭代永远只碰 dev，绝不碰 sealed holdout——否则 holdout 退化成 dev，go/no-go 失去意义。
- 落点：`deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json`，注册进 `benchmark_phase1_registry.json`（复用现有 harness）。

### 6.8 Gold item schema（一次性满足四用途：CI 回归门 / prompt A-B / 错误分析仪表盘 / 置信度校准）

**core 字段（沿用 §4 Task 2 fixture required，字段名不变）**：`case_id` / `question_id` / `question_text` / `student_answer` / `gold_score` / `max_score` / `gold_scoring_points`（point_id / label / hit / score / miss_reason）/ `gold_error_codes`（多标签 E 系列）/ `source_refs`。v1 smoke fixture 只含 core。

**Stage 4 认证后追加的扩展字段（与 core 并存，core 名不动）**：

- `ability_dimensions`（**list**，由 `ERROR_CODE_REGISTRY` 从 `gold_error_codes` **自动派生**——多标签错因码映射多个维度，**禁止人工写单个 case-level scalar**；`error_codes.py:45-56` 各 E 码绑定的 dimension 不同）
- `difficulty`
- `reliability`（high / low）
- `error_cooccurrence`
- `source_tier`（T1 / T2，打分时隐藏）
- `code_status`（certified / uncertified_v1 / directional）
- `scoring_basis`（评分口径：当年规范 / 当前规范 / dual-label，见 §6.2）
- `provenance`（源真题 + 标准答案版本 + 规范条文 + 标注人 + 时间 + 仲裁记录；与 core 的 `source_refs` 并存，不替换它）

> ⚠️ **命名口径**：扩展字段必须复用 §4 Task 2 的 core 名（`gold_error_codes` 而非 `error_codes`、`source_refs` 不被 `provenance` 取代），否则 §4 的 schema test 与 SOP 字段名对不上。
> ⚠️ 若现有 `gold_scoring_points` schema 表达不下多标签 + 共现 + reliability → 走 §0.3 覆盖率扩张瓶颈路径（见 §6.9 U4）。

### 6.9 Fallback 阶梯 + 不确定性

| 档 | 条件 | 允许做 | 禁止做 |
| --- | --- | --- | --- |
| 满档 | 2 专家 + 仲裁 + 效度专家齐全 | 全 100 份双盲 + 仲裁 + 效度轮 → 跑生产门 | — |
| 半档 | 仅 1 专家 | 100 份单标，标 `single_rater=true` | 不得报一致性，不得宣称"达生产门" |
| 冷启动 | 无专家 | 20 份 smoke（LLM 造 + 自标）只通 harness 管线 | 禁用 runtime，禁止宣称准确率提升 |

> **红线**：任何缺一致性 / 仲裁 / 效度的 golden，结论只能写 "directional / shadow"，永远不能写"通过生产门"。

**不确定性与验证 / 替代方案**：

| # | 不确定性 | 验证 / 替代 |
| --- | --- | --- |
| U1 | T1 真实学生答案能否取得（脱敏历史 / PII / 同意） | 先确认历史模考答卷可否脱敏；替代：招募考生仿真作答 / 培训机构合作；若 T1≈0，诚实改写为 "T2 为主 + 失真风险"，不宣称 real-first |
| U2 | 能否招到 ≥2 真·阅卷专家 + 仲裁 + 67 工时档期 | Stage 0 先签字确认；替代：半档单专家（不报一致性、不宣称生产门） |
| U3 | QWK ≥0.80 / 点级 AC1 ≥0.75 人类能否达到 | Week 2 用 5–10 份校准卷做阈值现实性预检；若人类达不到，按 §5.2.1：硬门改由"是否进入人类分歧带"承担，§5.2 的 90%/85% 退为 directional 目标（不跨度量等比换算） |
| U4 | 现有字段能否表达多标签 + 共现 + reliability | 对 fixture schema 做 dry-run 标注；表达不下走 §0.3 瓶颈路径 |
| U5 | 统计功效（分层） | 总分级 ±10%、点级视 prevalence、错因码级 ±30–40% 一律 directional；保持 go/no-go 定位，小差异结论一律 directional/shadow |

### 6.10 v0 执行轨道（无人类专家时的 AI 锚定管线）

> **可复用方法论**：本节是 [AI 锚定 Golden 生产 Playbook](2026-06-01-ai-anchored-golden-production-playbook.md)（**平台无关**）在本项目的 worked example。未来为 Codex 等其他平台复刻"无人类专家做 golden"，读那份 playbook（含 5 角色管线、踩字口径、8 条踩坑迭代修法、平台无关 vs 平台相关切分）。

> **定性（诚实红线）**：无人类阅卷专家时本轨道产出 **v0 synthetic 锚定集 = directional 级**，**不报人类 IRR、不宣称"通过生产门"**。顶级人类共识 golden（双盲 + IRR + 仲裁）= v1 目标态，待真人到位。v0 已用 2023 真题（1A434000，7 分）pilot 验证：独立 subagent 盲标 vs 构造台账，**点级 hit/miss 与总分 100% 复现**，错因码有粒度分歧（实证"错因码 directional、不进硬门"）。

**ground truth 三锚（非 AI 主观裁量）**：① 官方 `correct_answer`（采分点照它拆、不发明）；② 规范条文 + **教材原文**（标准文件 / `2026教材/*.json` 带规范术语原文，效度锚）；③ **构造台账**（学生答案按"故意命中/漏/错某采分点"构造，注入错误构造时写死、非事后判断）。

**评分口径（PO 2026-06-01 裁定，已查教材验证）——踩字给分**：
> - **命中(hit) = 考生写出规范术语原文那几个字**（如"诚实信用""依法履约""全面履行"）；这些术语源自**教材原文**（已验证：`2026教材/…BOOK2026-222-382` 列合同管理 6 原则原文，真题官方答案 = 教材术语的应用），采分点的"必须写出的原文术语"**唯一权威出处是教材原文**（官方答案是教材术语的应用），同义/近义词一律不给分，不由 AI 编造。
> - **近义/口号/大白话不给分**："诚信经营"≠"诚实信用"、"合法合规"≠"依法履约"，差那几个字就 miss。
> - **列举型按写出的规范术语原文个数给分**（写出一半数量的原文术语 → 一半分）。
> - ⚠️ 此口径修正了 v2 及以前**盲标的"近义匹配偏松"系统偏差**（构造与盲标可能一起偏松、互相"一致"，conc 高但偏离真实阅卷踩字尺度；由 PO 人类锚抓出，AI 自查发现不了）。v3 已据此重跑（盲标/构造 prompt 加踩字铁律）；预期 conc 会降但更可信。

**5 角色管线**（角色 ③ 独立性靠 subagent context 隔离）：

1. **采分点拆解员**：官方 `correct_answer` → `gold_scoring_points`（分值标"专家拆解·非官方"）。
2. **构造员**：按 archetype 注入已知错误造学生答案 + 台账。
3. **独立盲标员（subagent）**：只看采分点 + 答案，盲标 hit/miss + 错因码；**看不到台账 / 官方标注**。
4. **对照核验**：盲标 vs 台账 → 客观一致性（非循环：台账构造时写死）。
5. **效度锚**：分歧对照官方答案 + 规范裁定。

**罚则题处理（pilot 实证，PO 决策：固化后纳入）**：含"多答不得分"等**全局耦合罚则**的题必须把罚则写成判分器**可执行规则**——明确【牵连范围】（清零哪些采分点）+【计数口径】（按几项不妥计数、错误多答是否计入），消除 0/7~4/7 摆动；规则写进该题 `gold_scoring_points` 的 `penalty_rule` 字段。

**采分点粒度 / partial 处理（pilot + 全量两轮实证，迭代修正）**：partial 是采分点粒度问题。但"一律拆原子点"会**矫枉过正**——全量实证：列举类采分点（如"列出 8 项现场设施"）被拆成 23 个 0.25 分微点，鸡零狗碎、失真实阅卷惯例，且 conc 虚高。**正确分两类**：
> - ① **离散异质要点**（语义不同，如基准点要求 = 特等≥4 / 其他≥3 / 闭合环）→ 拆成独立原子点，二值 hit/miss。
> - ② **同质列举**（列举 N 项同类，如设施清单 / 收缩类型）→ **不拆**，作一个"列举型采分点" + `list_rule` 计数阈值规则（命中数→得分映射，如"≥4 项满分、每少 1 项扣 0.5"），与 `penalty_rule` 同类固化为可执行规则。
> - ③ 残留连续判断标 `boundary`，一致性二值化归 miss（保守），标记需 PO 抽查。
> - **硬约束**：各采分点 `max_score` 之和必须 == 整题分值（全量发现 Q5/Q18 未对齐）。

**天花板（测不了，必须标）**：真实学生表达变体、官方答案模糊地带、需人类裁量的边界 case；单一 AI 源同源偏置。

**唯一人类锚**：PO 抽查校验子集（建议 ≥10%）作为 v0 人类效度抽检；抽查不过 → 该批回炉。

---

## 7. Revised 4-week / 8-week route

> SOP 六阶段（Stage 0–5，§6.2–§6.7）映射进周计划，新增 **Week 0 体系前置**：Stage 0 不冻结，后面全废。

### Week 0（前置，SOP Stage 0）

- [ ] **启动闸门全绿（否则不进 Week 1）**：U2 专家+档期签字、U1 真实答案可得性答复、评分口径冻结（见顶部执行状态）。
- [ ] 交付 `irr_scoring.py`（零依赖纯函数、~150 行、寄生 benchmark）+ 校准卷标定主报口径（附录 A），**不预冻结具体系数**。
- [ ] 错因码标注手册 + 配额表（每认证码 ≥8 实例，v1 收口高频 6–8 码）。
- [ ] 效度锚定 + rubric 版本化 change log。
- [ ] 标注员名册（≥2 专家 + 仲裁 + 效度专家）+ 工时预算档期，PO 签字。

Acceptance：手册 100% 过 `validate_error_code`；fixture schema test 绿；名册与档期签字，否则按 §6.9 半档执行。

### Week 1

- [ ] Register v2.2 as current authority.
- [ ] Create benchmark fixture smoke schema.
- [ ] Add three-arm POC summary script.
- [ ] Select 20 question ids.
- [ ] Produce current rubric/scoring-point coverage report.

Acceptance:

- benchmark fixture test passes,
- source compiler tests pass,
- coverage report lists current coverage and gaps,
- no new production tables.

### Week 2

- [ ] Complete 100-answer labeling plan and at least 20 labeled smoke answers.
- [ ] **校准轮（SOP Stage 4 预检）**：5–10 份校准卷做阈值现实性预检 + rubric 校准（人类自己达不到 QWK 0.80 / AC1 0.75 → 触发 §5.2.1 人类天花板下调）。
- [ ] Run Baseline / RAG / Artifact-first smoke comparison.
- [ ] Report score delta, recall, precision, hallucination, token proxy.
- [ ] Decide whether to expand to full 100-answer run.

Acceptance:

- smoke report has all metrics,
- artifact-first does not pollute learner memory,
- all results are fixture/shadow only.

### Week 3-4

- [ ] **SOP Stage 3 双盲全量**：2 专家独立标 100 份（item 顺序随机化 + 10% 锚点重复测 intra-rater）。
- [ ] **SOP Stage 4 信度/效度双门**：点级 macro AC1 + 归一化 QWK（cluster bootstrap+LOO CI，报仲裁前独立标签）进硬门；错因码 per-code AC1 仅 directional 披露；gold 信度门不可下调；item 三态处置；仲裁 + adjudication_log；效度定性门（官方细则逐点核验 + 第三方分层切片盲评）。
- [ ] Complete full 20题/100答 golden run.
- [ ] Identify top rubric coverage gaps.
- [ ] Add rubric version/provenance migration only if the workflow is proven.
- [ ] Add benchmark trend entry for grading quality.

Acceptance:

- 信度门（生产硬门）：点级 macro-by-question AC1 / 归一化 QWK 的 cluster bootstrap CI 下界达 §6.1 阈值；错因码 per-code AC1 为 directional 披露、不进硬门；gold 信度门不可下调（§5.2.1）；
- 效度门：第三方盲评轮通过、provenance 100%、adjudication_log 100% 覆盖分歧；
- full run produces go/no-go,
- rubric coverage backlog is ranked by expected product impact,
- no generic Knowledge Engine tables.

### Week 5-8

- [ ] Expand scoring-point coverage for high-frequency topics.
- [ ] Add reviewer correction workflow only if label throughput supports it.
- [ ] Add BI/quality dashboard only after benchmark trend is stable.
- [ ] Re-run eval after each rubric batch **on the dev split / trend only** — 绝不碰 sealed holdout（§6.7）；最终 go/no-go 才一次性打开 holdout 并冻结。

Acceptance:

- grading quality trend is improving,
- coverage increases are visible,
- product changes are backed by eval.

---

## 8. Final Recommendation

Final conclusion:

- Do not directly integrate Pinecone Nexus.
- Do not build a generic Luban Nexus-like platform in P0/P1.
- Treat Nexus as external validation of artifact-first grading, not as an implementation blueprint.
- Execute方案 C+: existing kernel + benchmark harness + scoring-point coverage + golden eval + minimal rubric version/provenance.
- Revisit broader artifact/query layers only after 20题/100答 proves that structured scoring data materially improves grading quality.

The top-level objective is not to own a Knowledge Engine architecture. The objective is to make 一建建筑实务 subjective grading measurably more accurate, explainable, and improvable.

---

## 附录 A：统计口径（已冻结决策，勿在标注阶段再议）

> 本附录承载 §6.1 / §6.6 移出主线的统计实现细节。移出是**刻意的**：把"依赖未来数据特征（prevalence / 聚类强度 / 分数分布）的 estimator 选择"放在主线并冻死，是三轮打补丁漩涡的根源。**具体方法随 Week 0 校准卷敏感性分析标定后冻结，并落地为 `deeptutor/services/benchmark/irr_scoring.py` 的 `AGREEMENT_SPEC`；完整论证沉淀在该模块 docstring，不在本计划文档重复。** 标注阶段照此执行，不再辩论。

冻结决策（v1，校准卷标定后定稿）：

- **点级硬门**：按题聚合（macro-by-question）一致性；主系数在 AC1 / κ / PABAK 中据校准卷实测 prevalence 选定，并列披露全部系数 + prevalence + 「命中/未中/分歧」三格频数（防单系数被极端 prevalence 操纵）。
- **总分硬门**：题内归一化后一致性（防跨题 max_score / 难度虚高）；并列 within-question ICC + 归一化 MAE 交叉验证。
- **错因码**：per-code 逐码一致性 + 实例数 + CI，**v1 directional 不进硬门**；集合级 Krippendorff α+MASI 留作 v2 ≥3 人面板探针；v2 认证样本量按每码 prevalence / 目标 CI 半宽 / cluster design effect **预注册**（非拍脑袋 n=25）。
- **CI**：主方法 cluster bootstrap（按题整块）+ LOO-question；解析方差与朴素 bootstrap 仅敏感性对照（标准库 cluster bootstrap 数值不稳时回退解析方差 + 显式 design-effect）。
- **分层功效**：总分级 CI ≈ ±10%；点级视 prevalence；错因码级 ≈ ±30–40%（故 directional）。
- **工程约束**：`irr_scoring.py` 零新依赖、纯函数、frozen dataclass、~150 行上限、寄生 `services/benchmark`（不新建 eval 子系统，符合 §2.2）；若超过 150 行 / 引第二个外部依赖 / 长出 class 层级与注册表 → 过度设计，停下砍。
