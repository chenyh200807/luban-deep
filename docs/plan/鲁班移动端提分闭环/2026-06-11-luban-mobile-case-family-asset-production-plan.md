# 鲁班移动端 P0A 母题资产生产计划

> Status: Proposed / Asset production plan
> Date: 2026-06-11
> Parent authority: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)

## 0. Purpose

P0A 的最大风险不是 UI，而是母题、采分点、错因、题目绑定资产不够真。本文定义 P0A case_family 资产生产线，保证今日任务、AI 批改、错因复练和复测都有可靠材料。

2026-06-11 评审后的执行原则：不要从零并行铺 5 个母题。先复用既有 grading/scoring artifacts、registry、canonical taxonomy 和 M32 防水链路经验，打穿单母题 spike；再扩展到 3-5 个 P0A 母题。

## 1. Asset Gate

一个 case_family 进入 P0A 前必须具备：

- source_refs: 官方真题、教材、规范、讲义或已签发 scoring artifact。
- case_family_id / name / exam_weight。
- knowledge_node 绑定。
- scoring_point 清单。
- mistake_tag 清单。
- question_binding 清单。
- light practice task，必须标明 `task_scope` 和 `evidence_weight`。
- semi-write task，必须标明 `covered_scoring_point_ids`。
- retest binding rule，优先同一 scoring_point 的不同题。
- grading rubric / scoring_point evidence rule。
- canonical mistake_tag taxonomy version。
- owner / reviewer / version / rollback。

缺任何一项，只能进入 mock，不得进入真实 P0A 闭环。

## 2. P0A Candidate Pool

P0A 执行顺序：

| Order | ID | Mother topic | Why |
| --- | --- | --- | --- |
| Spike | F16 | 防水工程 | 已有 M32 grading-to-learning 链路经验，适合最快验证今日任务、半写、批改、错因、复练、复测 |
| Expansion | F01 | 进度计划与关键线路 | 高频、结构清晰、可做轻练/半写/复测 |
| Expansion | F02 | 工期索赔 | 高频、错因稳定、适合证据链展示 |
| Expansion | F04 | 质量验收程序 | 易演示程序性采分点与主体责任 |
| Expansion | F05 | 危大工程专项方案 | 高频、安全类错因强，适合复练 |

备选候选：

| ID | Mother topic | Why P0A |
| --- | --- | --- |
| F03 | 费用索赔 | 高频、能验证计算/依据高风险状态 |
| F15 | 大体积混凝土 | 关键词和程序清晰，适合半写 |
| F17 | 材料进场与复验 | 采分点稳定，适合错因分类 |

P0A 首个 spike 默认使用 F16 防水工程。产品负责人若改首母题，必须同时说明：现有 scoring artifacts、题目绑定、错因 taxonomy、复测题池是否足以支撑 1-1.5 周内端到端闭环。

## 3. Asset Schema Draft

```yaml
case_family:
  id: F01
  name: 进度计划与关键线路
  status: draft | reviewed | p0a_candidate | p0a_active | suspended
  source_refs:
    - type: official_question | textbook | standard | lecture | scoring_artifact
      ref_id: string
      version: string
  knowledge_nodes:
    - node_code: string
      title: string
  scoring_points:
    - id: string
      label: string
      rule_type: exact_required | list_rule | calculation | procedure | high_risk_review
      evidence_requirement: string
      max_score: number
  mistake_tags:
    - id: string
      label: string
      description: string
      taxonomy_version: string
      canonical_source: grading_kernel | reviewer | migration
  question_bindings:
    - question_id: string
      scoring_point_ids: string[]
      difficulty: low | medium | high
      retest_role: primary | similar_retest | original_review_only
  training_tasks:
    - mode: light | semi_write | real_exam | photo_preview
      task_id: string
      estimated_minutes: number
      task_scope:
        scope_type: full_question | scoring_point_subset | light_check | preview
        covered_scoring_point_ids: string[]
        excluded_scoring_point_policy: not_evaluated_no_miss
        evidence_weight: official | diagnostic | light_signal | none
  review:
    owner: string
    reviewer: string
    reviewed_at: string
    rollback_policy: string
```

## 4. Production Pipeline

```text
existing artifact scan
-> source collection
-> case_family definition
-> scoring_point extraction
-> mistake_tag taxonomy
-> question_binding
-> training_task design
-> review
-> shadow grading replay
-> P0A candidate
-> P0A active
```

### Step 0: Existing Artifact Scan

Required output:

- Existing `rubric_compiler` / registry / grading artifact references.
- Existing canonical taxonomy node matches.
- Existing question pool and source_refs coverage.
- Gap list for missing case_family, question_binding, light/semi-write task and mistake_tag taxonomy.

Reject if:

- Team starts manual source collection before checking existing signed artifacts.
- Artifact quality is assumed without spot-checking source_refs and scoring_point rules.

### Step 1: Source Collection

Required output:

- Source list.
- Source version.
- Copyright / provenance status.
- Existing artifact references if available.

Reject if:

- Source cannot be traced.
- Question or answer is copied without allowed usage boundary.
- Source does not support scoring_point claims.

### Step 2: Scoring Point Extraction

Required output:

- `hit / partial / miss / uncertain / needs_review` interpretation.
- High-risk points requiring review.
- Evidence span requirement.

Reject if:

- Scoring point is only a generic learning objective.
- Evidence cannot be checked against student answer.
- Rule would require frontend interpretation.

### Step 3: Mistake Tag Taxonomy

Mistake tags must describe why the student loses points, not just topic names.

Good:

- 主体责任漏写。
- 程序顺序错。
- 关键词不到位。
- 依据与措施混写。
- 计算过程缺失。

Bad:

- 不会质量。
- 防水错了。
- 没背书。

P0A hard rule:

- mistake tags must map to canonical `tag_id`, `label`, `taxonomy_version`.
- Display-only tags are allowed in prototype; writing long-term learner truth requires payload builder and readback proof.
- The same taxonomy must be readable by mistake book, follow-up task recommendation and today task explanation.

### Step 4: Training Task Design

Each P0A case_family needs at least:

- One light practice task.
- One semi-write task.
- One grading-compatible answer task.
- One similar-question or retest task.

Task design rules:

- P0A light practice only uses single-choice, multiple-choice and case small-question interactions.
- Semi-write tasks must declare the exact scoring_point subset they train.
- Out-of-scope points are not evaluated and cannot become miss evidence.
- Light practice evidence is `light_signal` and cannot close stable weakness by itself.
- Retest should use the same scoring_point on a different question; repeating the original question can support review but not clean improvement evidence.

## 5. Review Checklist

Reviewer must answer:

1. Does every scoring_point have source evidence?
2. Does every task map to at least one scoring_point?
3. Can a student answer be graded without frontend inference?
4. Can every mistake_tag drive a follow-up task?
5. Does every mistake_tag have canonical id, label and taxonomy version?
6. Does every light/semi-write task declare task_scope and evidence_weight?
7. Are out-of-scope scoring points blocked from miss evidence?
8. Is there at least one retest condition using same scoring_point and preferably different question?
9. Is rollback possible by case_family?
10. Are cost-heavy paths optional and controlled?

## 6. Release Status

Allowed statuses:

- `draft`: work in progress.
- `reviewed`: asset reviewed, not wired.
- `p0a_candidate`: can enter mock/shadow.
- `p0a_active`: can enter P0A real flow.
- `suspended`: disabled by gate or rollback.

Only `p0a_active` assets may appear in real P0A today tasks.
