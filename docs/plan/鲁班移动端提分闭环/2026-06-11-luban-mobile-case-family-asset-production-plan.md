# 鲁班移动端 P0A 母题资产生产计划

> Status: Proposed / Asset production plan
> Date: 2026-06-11
> Parent authority: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)

> v1.3 对齐（2026-06-15）：父 PRD 已把前台主菜收口为「每日提分留存闭环」。spike 首要交付随之调整：**不是案例题批改深度资产，而是「每日 2 分钟知识点 / 母题 MCQ 轻练诊断集」**——每道 MCQ 的每个干扰项（错误选项）必须绑定一个 `error_code` 与教材章节定位，使用户选错时当场拿到盲点诊断。这是 B 相对商品刷题 App 的差异化命根：无诊断映射的纯对错题等于和用户现有「刷题 / 看解析」无差异。案例题半写 / 批改资产降为留存跑通后第二阶段（深度护城河层）。下列 Asset Gate / schema / pipeline 积木保留。

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
- light practice MCQ 干扰项映射：每个错误选项绑定一个 `error_code` + 教材章节定位，支持「选错即诊断」（盲点 + 教材第几章）。这是留存闭环的差异化前提，缺失则该 MCQ 只能进 mock。
- semi-write task，必须标明 `covered_scoring_point_ids`。
- retest binding rule，优先同一 scoring_point 的不同题。
- grading rubric / scoring_point evidence rule。
- mistake_tag 的 error_code registry 版本（错因 canonical authority = `deeptutor/contracts/error_codes.py`，不另建 taxonomy）。
- owner / reviewer / version / rollback。

缺任何一项，只能进入 mock，不得进入真实 P0A 闭环。

## 2. P0A Candidate Pool

P0A 执行顺序：

| Order | ID | Mother topic | Why |
| --- | --- | --- | --- |
| Spike | F16 | 防水工程 | 已有 M32 grading-to-learning 链路经验、内容现成；spike 首要交付是该母题下的每日 MCQ 轻练诊断集（干扰项→error_code→教材章节）+ 次日复测题，用最低门槛验证留存；案例题半写 / 批改为第二阶段深度层 |
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

P0A 首个 spike 默认使用 F16 防水工程，首要交付是该母题下的「每日 MCQ 轻练诊断集 + 次日复测题」（每个干扰项绑 `error_code` + 教材章节定位），用于验证留存；案例题半写 / 批改深度资产作为第二阶段。产品负责人若改首母题，必须同时说明：现有 scoring artifacts、题目绑定、错因 taxonomy、复测题池是否足以支撑 1-1.5 周内端到端闭环。

## 3. Asset Schema Draft

> v2.1 收口：case_family 已拆为 `case_family_production`（指针层）+ `case_family_structure`（原创层）两对象。**字段结构的唯一 canonical 定义在 [2026-06-16-luban-deep-archetype-asset-schema-v2.md](2026-06-16-luban-deep-archetype-asset-schema-v2.md) §3**，本文**不再重定义字段**（避免两份定义 drift——这正是 §3.0 收口的根因）。生产侧字段属 `case_family_production`。本文只保留**生产流程**（§3.1 单一权威硬规则 / §3.2 落盘与状态 / §4 pipeline / §5 review checklist / §6 release status）。

> **去重决议（schema v2 §3.0）已应用，本文原 `case_family:` 草案删除，要点**：
> - 删 rule 影子 `rule_type`/`evidence_requirement`/`max_score`——判分回 published artifact；裸 `max_score` 会绕过判分内核 must-not-mint 门。
> - 删 `knowledge_nodes`——title 是 taxonomy 复制品 → 只留 `taxonomy_ref.node_codes`，title 运行时 resolve。
> - `source_refs` → `provenance.source_refs`（superset 形状，含 chunk_id + content_sha256）。
> - `status` → `status_production`（删 `p0a_` 前缀，phase 用 `rollout_scope`）；结构侧另有 `status_structure`。
> - `scoring_points` 全表 → 只留 `question_bindings[].{grading_artifact_id, scoring_point_refs}` 引用（采分点身份只在 artifact）。
> - `mistake_tags` = 锚 `error_code` 的**判分侧投影**（label/taxonomy_version 引用 ERROR_CODE_REGISTRY，不复制；注意 `error_code` 轴 ≠ `mistake_type` 判分形态轴）。
> - 完整字段见 schema v2 §3 的 `case_family_production`。

### 3.1 Single Authority Hard Rules

- case_family 级 scoring_point 只做母题级分组、映射与解释，不是第二套 rubric truth；逐题判分规则的唯一 authority 仍是 published question grading artifact + `CaseGradingSkillKernel`。
- 凡是已有 published artifact 覆盖的采分点，case_family 必须通过 `authority_refs` 引用 `artifact_id + point_id`（artifact_id 自含 version_id，如 `Q18-1A434000::qga_v0_20260604`），禁止复制改写 rule 内容；artifact 升版后由引用方重验，不留 fork。
- 没有 published artifact 覆盖的采分点（母题级新增），标 `status: draft`，必须有 `source_ref` 指向教材/官方原文 source；draft 点只能参与展示和任务规划，**参与真实判分前必须走 jury -> registry publish 流程签发**（registry v1 脚本族已存在：`scripts/build_luban_question_grading_registry_v1.py` 等）。
- **teaching shard 与合成题的点不得作为判分点**：`topic_waterproof` 等 runtime supply shard（`official_score_allowed=false`）和 M32 合成题（如 `waterproof_case_001`）的点只能作 teaching context / 闭环结构参考，禁止纳入真实学生任务的 `covered_scoring_point_ids`。
- `taxonomy_ref.sha256` 是**写入时快照 + 翻转时人工硬检查**，不是自动化承诺（当前无任何代码检测 sha；taxonomy 实测一天内多次改写）。具体执行：创建/修改资产时重新计算并记录 sha；每次 status 翻转时 reviewer 必须重验当前 runtime taxonomy index 的 sha 与 node_code 可解析性，并在 review_record 写 `taxonomy_reverified: true/false`；不一致且影响绑定时由 reviewer 决定降级，不假设系统自动降级。

### 3.2 Asset Storage And Status Authority

- 资产文件统一落盘在主仓库 `artifacts/luban_case_family_assets/<case_family_id>/`：`case_family.yaml` 为正文，`review_record.json` 记录每次 status 翻转（who/when/checklist 结论）。
- `status_production` 翻转只能由 review record 驱动：`draft -> reviewed` 需要 reviewer 按 §5 checklist 逐项作答；`reviewed -> candidate` 需要 shadow grading replay 证据；`candidate -> active` 走 release gate checklist 对应门。（结构侧 `status_structure` 走 G-INV/G-COV,见 schema v2 §3.0 决议0;phase 不进 status,用 `rollout_scope`。）
- 不要把资产写进临时 worktree（`worktree remove --force` 会删掉 gitignored artifacts）。

## 4. Production Pipeline

```text
existing artifact scan
-> source collection
-> case_family definition
-> scoring_point extraction
-> mistake_tag mapping
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
- Gap list for missing case_family, question_binding, light/semi-write task and mistake_tag mapping.

Reject if:

- Team starts manual source collection before checking existing signed artifacts.
- Artifact quality is assumed without spot-checking source_refs and scoring_point rules.

### Step 1: Source Collection

Required output:

- Source list.
- Source version.
- Copyright / provenance status.
- Existing artifact references if available.
- 外部源钉扎：凡引用 deeptutor 仓库之外的源（如 `FastAPI20251222/docs/2026/题库/`，当前**无版本控制**），`source_refs` 必须记录相对路径 + chunk_id + content sha256（写入时快照，与 taxonomy_ref 同一防御模式）；资产实际消费的最小源摘录（题面/官方答案 span）拷入 git-tracked 的资产目录并注明出处，使 review 与 shadow replay 不依赖外部盘。

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

### Step 3: Mistake Tag Mapping（不是新 taxonomy）

错因的 canonical authority 已经存在：`deeptutor/contracts/error_codes.py` 的 `ERROR_CODE_REGISTRY`（E01-E12 案例题轴 + M01-M10 选择题轴），运行时由 `GradingErrorEvent` 生产、`learning_synthesis -> learning_report -> training_intent -> next_best_action` 全链消费。**本步骤的工作是映射，不是发明**。

每个采分点的 mistake_tag 生产方法：

1. 分析该采分点的失分形态，从 registry 中选 1-2 个最贴合的 error_code（例：割补法工序点 P10/P11 → `E06 程序顺序错误`、`E03 关键词缺失`）。
2. `label` 直接取 `ERROR_CODE_REGISTRY[error_code].label`，禁止另写表述。
3. 若现有 23 个 code 确实覆盖不了某种失分形态，**提 registry 扩码评审**（改 error_codes.py + contract 测试），不得在资产里私造 tag。

Good（这些都是既有 error_code 的语义，映射即可）：

- 程序顺序错 → E06。
- 关键词不到位 → E03。
- 采分点遗漏 → E02。
- 计算过程缺失 → E09。

Bad：

- 不会质量 / 防水错了 / 没背书（topic 名不是失分原因）。
- 任何 registry 之外自造的 label。

P0A hard rule:

- mistake_tag 必须引用注册过的 `error_code`，schema 见 §3 与 M0 §6.2 修订版。
- Display-only tags are allowed in prototype; writing long-term learner truth requires payload builder and readback proof.
- mistake book、follow-up task recommendation、today task explanation 读的必须是同一 `(scoring_point_id, error_code)` 事实，不得各自维护标签副本。

### Step 4: Training Task Design

Each P0A case_family needs at least:

- One light practice task.
- One semi-write task.
- One grading-compatible answer task.
- One similar-question or retest task.

Task design rules:

- P0A light practice only uses single-choice, multiple-choice and case small-question interactions.
- **每个 MCQ 干扰项（错误选项）必须绑定一个注册过的 `error_code` 与教材章节定位**：用户选错时当场产出「你暴露的盲点 = X，对应教材第 Y 章」。无诊断映射的纯对错 MCQ 不得进入 P0A（否则退化成与用户现有「刷题 / 看解析」无差异的题海，正是 v1.3 §1 非目标里禁止的纯刷题 App）。
- Semi-write tasks must declare the exact scoring_point subset they train.
- Out-of-scope points are not evaluated and cannot become miss evidence.
- Light practice evidence is `light_signal` and cannot close stable weakness by itself.
- **task_scope 实现前置门**：`not_evaluated` 强制与 scope 裁剪当前在 runtime 代码中零实现（schema.py 无 TaskScope，CaseGradingResult 无 scope 字段）。资产侧的 semi-write 任务在 M0 §6 的 task_scope contract + 注册测试落地前，只能停在 `candidate`（shadow，`status_production`），不得升 `active` 进真实判分。
- **复测证据阶梯**（improvement evidence 必须标注 binding level）：
  1. `same_point_different_question`（gold）：同一 scoring_point 的不同题。题池中不存在时不得降格伪造——例如 Q18 P10/P11 割补法工序点，全题库（2015-2025 真题 + 30 题候选 + 客观题池）扫描确认无第二道同考点题。
  2. `same_node_different_question`（silver）：同 knowledge_node 的不同题（客观题池或其他案例题）；只能支撑"相关知识回暖"，不能单独关闭该采分点的稳定弱点。
  3. `original_question_review`（review-only）：原题重做，只支持复习记录，不算提升证据。
- 半写小问呈现：question_binding 需带 `sub_question_ref`（小问定位），完整大案例题干在移动端半写任务中按小问裁剪呈现的方式属于 UI spec / ViewModel contract 范畴，资产侧只负责标注小问与所需背景段落。

## 5. Review Checklist

Reviewer must answer:

1. Does every scoring_point have source evidence?
2. Does every task map to at least one scoring_point?
3. Can a student answer be graded without frontend inference?
4. Can every mistake_tag drive a follow-up task?
5. Does every mistake_tag reference a registered `error_code` with label taken verbatim from `ERROR_CODE_REGISTRY`?
6. Does every light/semi-write task declare task_scope and evidence_weight?
7. Are out-of-scope scoring points blocked from miss evidence?
8. Is there at least one retest binding, at the highest binding_level the question pool actually supports (gold `same_point` preferred; documented honestly if only `same_node` exists)?
9. Is rollback possible by case_family?
10. Are cost-heavy paths optional and controlled?
11. Are all grading-participating scoring points backed by a published artifact (`authority_refs`), with teaching-shard / synthetic points excluded?
12. Is `taxonomy_ref` re-verified against the current runtime taxonomy index at this status flip (`taxonomy_reverified` recorded in review_record)?
13. Does every retest binding declare its `binding_level`, and is no `same_node` evidence presented as point-level mastery closure?

## 6. Release Status

Allowed statuses:

- `draft`: work in progress.
- `reviewed`: asset reviewed, not wired.
- `candidate`: can enter mock/shadow.
- `active`: can enter real flow.
- `suspended`: disabled by gate or rollback.

Only `active`（status_production）assets may appear in real today tasks. phase（如 p0a）用 `rollout_scope` 表达,不进 status（schema v2 §3.0 决议1）。
