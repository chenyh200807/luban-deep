# 鲁班移动端 P0A M0 Reality Lock

> Status: `Active / M0 reality lock`
> Date: 2026-06-11
> Parent authority:
> - [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)
> - [2026-06-11-luban-mobile-scoring-loop-p0a-execution-plan.md](2026-06-11-luban-mobile-scoring-loop-p0a-execution-plan.md)
> - [2026-06-11-luban-mobile-p0a-viewmodel-and-event-contract.md](2026-06-11-luban-mobile-p0a-viewmodel-and-event-contract.md)

本文件是 P0A 开工前的现实收权记录。它不重新定义产品目标，只把执行前必须锁住的代码现实、资产现实、authority 边界、阻塞输入和降级规则写清楚。

## 0. Karpathy Gate

### assumptions

- P0A 的首个端到端 spike 采用 `F16 防水工程 / topic_waterproof`，不改题、不同时扩 5 个母题。
- 当前先做 M0 文档与现实盘点，不写前端/后端产品代码。
- `PRD/` 下旧 UI/UX 与混合制章节资料仍只是输入资料；实现 authority 只看 `docs/plan/鲁班移动端提分闭环/` 当前文档包。
- 用户已确认：错题本里“已掌握”不能由用户按钮直接成为客观掌握，必须由复测、同采分点迁移题、遗忘曲线后的再验证等客观证据支撑。

### simplest path

1. 先锁前端树：真实微信 project root 与目标分包是 `yousenwebview` + `packageDeeptutor`；`wx_miniprogram` 只作为影子/来源/移植输入，不能直接算 true-entry。
2. 先复用 M32 防水闭环、`v_topic_waterproof`、P0A 防水题集覆盖、现有 learning-report / mistake-book / training_intent / NextBestAction 链路。
3. 只补 M0 必须的 schema/contract 接缝：`task_scope`、`mistake_tag`、`mastered` 降权语义、今日任务推荐 authority。

### change boundary

本轮允许修改：

- 新增本 M0 reality lock 文档。
- 更新 `docs/plan/INDEX.md` 对本 M0 文件的索引。

本轮不修改：

- `contracts/learner-state.md`、`contracts/learning-report.md`、`contracts/index.yaml`。
- `yousenwebview/`、`wx_miniprogram/`、`deeptutor/api/routers/mobile.py`、`deeptutor/services/learner_state/*`。
- 不整理现有 dirty worktree，不 stage 不相关改动。

### verification target

- 能回答“在哪棵树开发、在哪棵树验收、哪条链生成推荐、哪些证据能写 learner truth、哪些用户动作只能算主观信号”。
- 能给 M1 F16 spike 一个不返工的开工边界。
- 仍明确列出需要用户/负责人补证的输入，不把未知写成已确认。

## 1. M0 Verdict

| 项 | 结论 | 状态 |
|---|---|---|
| Frontend source tree | P0A true-entry 验收必须以 `yousenwebview` project root + `packageDeeptutor` 分包为准；`wx_miniprogram` 只能算 shadow 或移植来源 | `LOCKED for validation` |
| Latest upload source | 本地只能证明两棵树同 AppID，不能证明最近一次上传来自哪棵树 | `BLOCKED on owner evidence` |
| F16 防水 spike | 采用 M32 防水闭环与 `topic_waterproof` 资产作为首母题，不从零生产 | `LOCKED unless user changes topic` |
| 推荐 authority | `training_intent` / `NextBestAction` 生成候选，`priority_score` 只排序/解释 | `LOCKED` |
| `task_scope` | 半写/轻练必须带覆盖采分点；范围外点只能 `not_evaluated`，不能写 miss | `LOCKED` |
| `mistake_tag` | schema 未冻结前只能 display-only；写长期 truth 需 contract + readback test | `LOCKED` |
| `mastered` | 用户按钮只能表示主观关闭/暂不显示，不得直接关闭 canonical mastery | `LOCKED` |

M1 可以启动的前提：不写真实学习证据的 UI/asset/mock 工作可以先行；任何写 `learning_evidence`、关闭弱点、改变今日任务推荐的代码，必须先完成本文件 §6 的 contract/schema 任务。

## 2. Frontend Source Tree Lock

### 2.1 Code reality

| 树 | 现实 | P0A 处理 |
|---|---|---|
| `yousenwebview/app.json` | 微信宿主项目，注册 `packageDeeptutor` 分包；包含 `chat/history/report/mistake-book/attempt-detail/feedback/profile/login/register/billing/practice/assessment/legal` | 真实微信验收 source。DevTools project root 必须指向 `yousenwebview` |
| `yousenwebview/packageDeeptutor/` | 目标分包；已有 custom tab bar、核心页面、`learning-home-view-model`、`learning-report-view-model`、`mistake-book-view-model`、API/util 测试 | P0A 代码主落点 |
| `wx_miniprogram/app.json` | 独立 Deeptutor 小程序形态；有 4 Tab 与 `photoAnswer` 子包 | shadow/能力来源；未同步到 `packageDeeptutor` 前不得算 true-entry |
| `docs/openmaic/package-deeptutor-sync-manifest.yaml` | 声明 `wx_miniprogram -> yousenwebview/packageDeeptutor` 不是 raw mirror，只允许特定能力同步，保留宿主 login/membership/workspace | P0A 禁止整目录覆盖 |

### 2.2 Development rule for P0A

P0A 暂定规则：

- 新增移动端产品页面、ViewModel、事件和 true-entry QA：优先落 `yousenwebview/packageDeeptutor`。
- OCR/photo-answer 若沿用 `wx_miniprogram/pages/photo-answer/*`，必须在对应任务中补一条 `sync evidence`：移植到 `packageDeeptutor` 或明确标为 shadow-only。
- 不允许用 `wx_miniprogram` 的测试通过替代 `yousenwebview/packageDeeptutor` 的真微信入口证据。
- DevTools 证据必须拆开记录：
  - `devtools_project_root=yousenwebview`
  - `target_subpackage=packageDeeptutor`
  - `target_page=<具体页面>`
  - `entry_flow=<具体入口路径>`

### 2.3 Owner input needed

仍需负责人提供最近一次小程序上传来源证据：

- miniprogram-ci 上传配置或上传日志；或
- 微信开发者工具上传记录截图/日志；或
- 发布负责人明确确认“最近一次 production upload 的本地 project root”。

在该证据补齐前，M0 只锁验收口径，不宣称最近 production upload 已来自 `yousenwebview`。

## 3. Current Page Inventory

| P0A surface | Existing page | Action |
|---|---|---|
| 今日焦点 / 今日任务 | `packageDeeptutor/pages/chat/chat` 有 home action 基础；`learning-home-view-model.js` 已存在 | P0A 不改 4 Tab；先作为 chat 页内今日焦点或独立入口页灰度 |
| 作答/练习 | `packageDeeptutor/pages/practice/practice`、`pages/assessment/assessment` | P0A 收敛为选择题 + 案例小问；排序/匹配/填空移到 P0B |
| 批改结果 | `packageDeeptutor/pages/attempt-detail/attempt-detail` | 改造成采分点、错因、task_scope、下一步训练读回 |
| 错题本/错因复练 | `packageDeeptutor/pages/mistake-book/mistake-book` | 增加 canonical `mistake_tag` 展示与复测入口；schema 未冻结前不得写长期 truth |
| 学情页 | `packageDeeptutor/pages/report/report` | 只读 learning-report projection，不现场推导 mastery |
| 拍照识题 | `wx_miniprogram/pages/photo-answer/capture|confirm` | 需要移植/同步证据后才能成为 true-entry |
| 我的/隐私 | `packageDeeptutor/pages/profile/profile` | 承载数据说明、隐私入口、反馈入口 |

## 4. F16 Waterproof Asset Lock

### 4.1 Reusable assets found

| Asset | Evidence | M1 use |
|---|---|---|
| M32 防水 Grading-to-Brain vertical slice | `docs/plan/总控入口与当前作战图/2026-06-07-luban-grading-to-brain-m32-waterproof-vertical-slice-execution-plan.md` 标记 COMPLETE / GO | 作为 F16 spike 的闭环样板 |
| M32 artifact package | `artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/` | 复用 evidence -> claim -> PCP -> NextBestAction -> retest 结构 |
| Waterproof runtime topic shard | `deeptutor/services/construction_grading/runtime_supply/v_topic_waterproof/topic_waterproof.json` | 只作为 teaching context / topic supply；不是 answer key |
| P0A waterproof assessment coverage | `artifacts/assessment_testset/p0a/p0a-phase-minus-1-current/coverage_waterproof.md` | 提供题目候选池与移动端风险筛选 |
| Contract tests | `contracts/index.yaml` 已包含 M32 learning_evidence / PCP / retest / NBA 相关测试 | M2 扩展 task_scope / mistake_tag 时沿用 test registration 纪律 |

### 4.2 Asset risks

- `topic_waterproof` shard 中存在 `anchor_only` 低置信来源，且部分预览文本与防水不完全一致；P0A 不得把它当答案 key 或 scoring truth。
- 防水 coverage 有 391 candidate、159 eligible、12 delivered recommendation，但仍有 55 figure refs、43 long-stem mobile risk、5 table refs、206 missing_options；M1 选题必须避开移动端渲染风险。
- `case_family`、`question_binding`、轻练/半写任务、canonical `mistake_tag` 仍需 M1/M2 正式生成，不能把 M32 artifact 直接等同于完整产品资产包。

### 4.3 M1 first asset scope

M1 只做一个防水母题端到端 spike：

- 1 个 `case_family`
- 1 个完整案例题或案例小问
- 3-5 个 `scoring_point_id`
- 每个采分点 1-2 个 canonical `mistake_tag`
- 1 条 light task
- 1 条 semi-write task
- 1 条 same-scoring-point different-question retest binding

## 5. Existing Backend Authority Inventory

| Business fact | Current authority | Current endpoint / file | Gap for P0A |
|---|---|---|---|
| Learning evidence write/read | `LearnerStateService.append_memory_event(memory_kind="learning_evidence")`; payload builder in `deeptutor/services/construction_grading/learning_evidence.py` | `contracts/learner-state.md` | Add `task_scope`, `mistake_tag`, OCR provenance only through payload builder |
| Learning report | `learning-report-read-model` | `GET /api/v1/mobile/learning-report` in `deeptutor/api/routers/mobile.py` | Today task source must move from note-asset compatibility to P0A candidate projection without creating new authority |
| Attempt detail | `attempt-detail-read-model` | `GET /api/v1/mobile/learning-attempts/{attempt_ref}` | Add scoped point readback / not_evaluated display if contract freezes |
| Mistake book | `deeptutor/services/learner_state/mistake_book.py` | CRUD endpoints under `/api/v1/mobile/mistake-book` | `mastered_at` semantic conflict; add close_source / objective mastery split |
| Recommendation | `training_intent.py` + `next_best_action.py` | Read through learning report/home projection | `priority_score` must remain ranking/explanation only |
| Retest | Existing M32 revalidation / retest proof patterns | M32 artifacts and tests | Add mobile readback endpoint or learning-report projection for retest status |

## 6. Authority Gaps To Fix Before Evidence Writes

### 6.1 `task_scope`

Required schema before semi-write/light evidence can write:

```yaml
task_scope:
  scope_type: "full_question | scoring_point_subset | light_signal | preview_only"
  covered_scoring_point_ids: []
  excluded_scoring_point_policy: "not_evaluated_no_miss"
  evidence_weight: "full | partial | light_signal | none"
```

Rules:

- Scope-covered points may produce `hit/miss/partial`.
- Scope-excluded points must produce `not_evaluated`; they must not write miss evidence.
- Light practice can create `light_signal` but cannot independently close a weakness.

### 6.2 `mistake_tag`

Required schema before long-term write:

```yaml
mistake_tag:
  tag_id: "mt_*"
  label: ""
  taxonomy_version: "mistake_tag_taxonomy_v1"
  source: "rubric_policy | teacher_final | model_candidate | user_selected"
  confidence: 0.0
```

Rules:

- Before contract and readback tests freeze, `mistake_tag` is display-only.
- Free-text diagnosis such as “漏写采分点：XXX” cannot be the canonical tag.
- Tags must be usable by mistake book, review task and today task with the same `tag_id`.

### 6.3 `mastered`

Current conflict:

- `contracts/learning-report.md` says `mastered_at` non-empty means “已掌握”。
- `MistakeBookService.mark_mastered()` directly sets `mastered_at` and filters the item from default list.
- Product authority now requires: user clicking “已掌握” is subjective; objective mastery must come from successful retest / teacher-final / certified evidence.

P0A rule:

- Keep endpoint for compatibility, but treat it as `user_closed` / `self_reported_done` / `hide_from_default_queue` until contract is revised.
- It cannot close canonical learner mastery, cannot clear stable weakness, cannot stop revalidation by itself.
- Real closure path must be:

```text
same scoring_point_id or equivalent binding
-> different question retest
-> no repeated mistake_tag
-> evidence passes authority gate
-> revalidation_queue / learner claim update
```

M1/M2 code task:

- Add explicit close semantic, for example `close_source=user_self_report` or `mastery_close_source=objective_retest`.
- Rename UI copy away from objective “已掌握” if code cannot be changed immediately; prefer “先从错题列表移除” or “我觉得会了，安排后续复测”。

### 6.4 `priority_score`

Allowed:

- Rank and explain candidates already generated by `training_intent` / `NextBestAction` / learning-report read model.

Forbidden:

- Generate tasks independently.
- Close weak points.
- Write learner memory.
- Override `training_intent`.

## 7. Worktree / Dirty State Note

At M0 start, the focused plan surface is not clean:

- `docs/plan/INDEX.md` has pre-existing unstaged changes.
- `contracts/index.yaml` and `contracts/learner-state.md` have pre-existing unstaged changes outside this M0 doc task.
- `wx_miniprogram/pages/photo-answer/capture.js` and `wx_miniprogram/utils/api.js` are also modified.

M0 execution must keep commits narrow. If committing this file later, stage only:

- `docs/plan/鲁班移动端提分闭环/2026-06-11-luban-mobile-p0a-m0-reality-lock.md`
- the intentional hunk in `docs/plan/INDEX.md`

Do not sweep in contract or OCR code changes unless that is explicitly requested.

## 8. M0 Exit Criteria

M0 is complete when:

- [ ] Owner provides latest mini-program upload source evidence, or explicitly accepts `yousenwebview/packageDeeptutor` as P0A dev + validation source regardless of prior upload source.
- [ ] F16 防水 first spike scope is confirmed unchanged.
- [ ] `task_scope` schema has protected contract/test registration plan.
- [ ] `mistake_tag` taxonomy shape has protected contract/test registration plan.
- [ ] `mastered_at` semantic downgrade is reflected in contract/API plan.
- [ ] F16 M1 asset package has one case_family, scoped tasks and retest binding.

Until all boxes are closed, implementation may proceed only on mock/ViewModel/design surfaces that do not write long-term learner truth.
