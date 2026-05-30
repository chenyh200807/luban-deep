# PRD: 鲁班智考 Assessment TestSet 出卷测评模块

> 本计划承接 `Assessment Blueprint`、`question lifecycle`、`lightweight practice + deep grading`、`learning evidence closed loop` 四条既有主线。产品层可以叫“智能组卷 / 测评卷 / 模拟考试”，但系统 authority 仍归 existing assessment / question / grading / learner-state 链路，不新建第二套题库、第二套学情或第二套聊天入口。

**Status:** v0.3 (2026-05-24; third-pass hardening based on code-fact review)

**Owner surface:** mobile assessment surface / `AssessmentBlueprintService` / `deep_question` / `construction_grading` / `learner_memory_events.learning_evidence` / learning report read models

**Related plans:**

- [2026-05-02-luban-assessment-blueprint-prd.md](2026-05-02-luban-assessment-blueprint-prd.md)
- [2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md](2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md)
- [2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md](2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md)
- [2026-05-23-luban-learning-history-evidence-closed-loop-plan.md](2026-05-23-luban-learning-history-evidence-closed-loop-plan.md)
- [2026-05-22-luban-learning-state-inference-engine-transformation-plan.md](2026-05-22-luban-learning-state-inference-engine-transformation-plan.md)

---

## 0. 一句话结论

DeepTutor 需要的不是“对话里多出几道题”，而是一个独立可进入、可恢复、可提交、可计分、可复盘、可写回学情的 `Assessment TestSet` 模块：

```text
题库 / blueprint / 学情弱点
  -> 服务端组卷成一次 assessment session
  -> 学员一口气做完整卷
  -> 提交后统一计分、统一揭晓答案和简单解析
  -> 点击错题或疑问题再走统一 `/api/v1/ws` / question lifecycle 做二次深度解析
  -> 每道题的作答事实写入 learner_memory_events.learning_evidence
  -> 学情页、错题集、训练 intent 和下一次组卷都消费同一份 evidence
```

P0 先做固定蓝图和专题蓝图，不先做完整 CAT 自适应；先保证可信、可比、可回放，再做更智能的动态组卷。

### 0.1 Second-pass judgment

v0.1 的方向正确，但 P0 仍偏大。按当前代码事实，最稳健的 P0 不应该同时交付三种卷型、深解、报告联动和持久化升级。实干派交付顺序应收缩为：

```text
P0A: 防水专题或当前 composite 防水/装饰/机电专题 10-12 题 objective/structured 小卷
  -> 服务端组卷
  -> deferred feedback
  -> 提交后简单报告
  -> per-item learning_evidence 写回
  -> 错题进入 mistake-book / attempt detail

P0B: 真题样式 mini simulation
  -> 复用同一 session/report/writeback
  -> 增加 REAL_EXAM source policy 和 form comparability

P1: mastery_check + deep explanation cache
  -> 从 training_intent 进入
  -> 单题详细解析按需生成

P2: subjective case grading / adaptive / authoring
```

理由：

1. 当前 `mobile.py` 的 `assessment/create` 只接 `count`，还没有 `assessment_type/topic_ids/subject_id`。
2. 当前 `MemberConsoleService.submit_assessment` 已能算 aggregate score 和写 aggregate `memory_kind=assessment`，但还没有逐题 `learning_evidence` writeback。
3. 当前 `assessment_sessions` 代码事实已确认是 member-console JSON file，本地 file lock 只解决单实例文件写入，不满足多实例/容器漂移下正式考试持久性。
4. 若 P0 一次性做三种卷型，会把真正的 P0 风险稀释掉：答案泄露、session 持久化、提交幂等、逐题证据、结果页可读性。

因此本计划的执行口径调整为：**先用防水专题小卷打穿端到端闭环，再复制到真题样式和 mastery check。**

### 0.2 v0.3 hardening summary

v0.3 吸收二次评审后，把 P0A 的硬门槛再收紧：

1. `assessment_sessions` 不再标为“待验证持久性”。~~代码已确认当前落在 `MemberConsoleService` 的 member-console JSON file；~~ **【2026-05-30 核验更新】Supabase durable session 表 + RLS + submit idempotency 已落地并合 main（migration `20260524000100_assessment_sessions.sql`, PR #42）；本句关于 "当前落 JSON file" 的描述已过期，durable 路径在 production / `ASSESSMENT_SESSIONS_USE_SUPABASE=true` 下生效，生产 apply 待环境实证。** P0A 正式上线前的 Supabase durable session 表、RLS/owner check 和 submit idempotency 设计已满足。
2. “防水工程”不能假设为已存在的独立 blueprint topic。当前代码只有 `waterproof_decoration_mep` composite section；Phase -1 必须先决定拆成 `waterproof / decoration / mep`，还是把 P0A 改为“防水/装饰/机电综合测评”。
3. P0A submit 不直接写 `training_intent`。结果页显示“基于本次测评的即时建议”和跳转学习计划；学习计划仍由 learner-state / study-plan projection 作为处方 authority。
4. P0A 不交付 deep explanation。完整按题深解是 Phase 2/P1；P0A 只给 simple report、attempt refs、错题/证据写回，以及 disabled/hidden CTA 的一致文案。
5. Product states 增加 TTL、状态转换、设备 lease 和 server-wins draft 冲突策略，避免无限 `in_progress` 和多端覆盖。
6. Phase 0 增加 `last_assessment` 下游引用 audit，防止 aggregate projection 继续被当 mastery authority。

---

## 1. 外部调研基线

本模块参考的是成熟 assessment 平台的共同结构，而不是普通 quiz UI。

| 产品 / 标准 | 可借鉴点 | 对 DeepTutor 的落点 |
| --- | --- | --- |
| Moodle Quiz / Question bank / Deferred feedback / Reports | 题库与 quiz 分离，支持随机题、延迟反馈、成绩/作答/统计/人工评分报告 | 出卷必须有题库 authority、session、统一提交和报告；正式测评默认 deferred feedback |
| Canvas New Quizzes / Item banks / Random set / Stimulus | item bank 抽题、随机题组、材料题 stimulus、quiz reports | 案例题应是 `case stimulus + sub-items`；随机卷必须记录 `form_id / sampling_trace` |
| Learnosity Author / Items / Activities / Sessions / Reports | 专业测评拆成 authoring、delivery、analytics；题目/活动/会话/报告分层 | 内部概念应保持 `Item -> Form -> Session -> Result -> Report`，不要把试卷当成前端数组 |
| 1EdTech QTI | assessment item/test/result 的行业交换标准 | P0 不实现 QTI，但内部数据模型应能未来映射到 QTI |
| Khan Academy Mastery | quiz/unit test/course challenge 结果进入 skill mastery | 试卷报告必须落到知识点掌握和下一步训练，而不是只显示总分 |
| NWEA MAP / Duolingo English Test | 大题池、测量置信度、能力估计、自适应题量 | P2 再做 two-stage adaptive；P0 必须先有 `measurement_confidence` |
| NBME / AMBOSS / UWorld 类考试训练产品 | 整套自测、score report、逐题解释、强弱项和推荐 | 我们应把“整卷做完再复盘”作为模拟考试主体验 |
| Quizlet Practice Tests / Google Practice Sets / Khanmigo teacher tools | AI 适合生成练习初稿、提示、资源推荐，但正式计分仍依赖题源和答案 authority | LLM 生成题先是 draft / practice，不直接进入可比正式考试分数 |

关键判断：

1. 世界级测评模块的本体是 `session + result + report`，不是“聊天回复里有几道题”。
2. AI 可以辅助组卷、解释和个性化，但不能替代题库、标准答案、rubric、版本和审计。
3. `deferred feedback` 是正式测评的默认规则。练习可以逐题反馈，测评不可以。
4. 所有结果必须能被报告和学情复用，否则只是一次性 quiz。

---

## 2. Karpathy Gate

### 2.1 assumptions

1. 用户目标是系统性评测真实掌握情况，覆盖单知识模块、综合模块、仿真真题和模拟考试。
2. “出卷模块”是 assessment surface，不是 TutorBot 的第二身份，也不是 `deep_question` 的替代 capability。
3. 正式测评必须一口气完成后再给答案和简单解析；逐题反馈属于练习，不属于测评。
4. 详细解析是答后按需二次调用，不能在组卷阶段预生成。
5. 所有作答记录必须进入学情，但不能让前端或试卷报告自己推导长期 mastery。

不确定项：

1. P0 是否只支持一建建筑实务，还是同步预留多科目字段。本文默认 P0 只实现 `subject_id=construction_exam`，接口保留 subject 字段但不承诺第二学科。
2. 案例题 P0 是否支持完整主观作答。本文默认 P0 支持“短案例 / 案例材料 + 客观小题 / 结构化判断”，完整主观案例题进入 P1。
3. 是否需要严格考试计时。本文默认 P0 记录用时并可配置建议时长，不强制交卷；模拟考试模式 P1 再强制 timer。

### 2.2 simplest path

最短路径是扩展现有 assessment，而不是新建 `paper` 系统：

1. 继续使用 `AssessmentBlueprintService` 作为组卷 authority。
2. 在现有 `assessment_forms` / `assessment_sessions` 概念上扩展 `assessment_type`：
   - `diagnostic`
   - `topic_diagnostic`
   - `real_exam_simulation`
   - `mastery_check`
3. 服务端保存完整 `session_questions` 和隐藏答案/rubric；前端只拿 redacted 题卡。
4. 提交后由 deterministic scorer + `construction_grading` 产出结果。
5. 简单解析从题目 artifact / stored rationale / option reasoning 输出。
6. 详细解析通过统一 question lifecycle 触发，不新增 assessment 专用 WebSocket。
7. 作答事实统一写 `learner_memory_events.learning_evidence`，现有 aggregate assessment event 继续保留为 teaching policy seed。

### 2.3 change boundary

允许触碰：

| 层 | 允许改动 |
| --- | --- |
| Plan / contract | 新增本 PRD；必要时后续补 `contracts/learning-report.md` 或 learner-state contract note |
| Backend assessment | `deeptutor/services/assessment/*`、`MemberConsoleService.create_assessment/submit_assessment` 的扩展 |
| Mobile API | 复用并扩展 `/api/v1/mobile/assessment/*`；不新增聊天 WS |
| Grading | 复用 `construction_grading`、objective scorer、`SubmissionGraderAgent` |
| Learner state | 只写 `learner_memory_events`、existing projections、mistake-book writeback choke point |
| Frontend | `yousenwebview/packageDeeptutor/pages/assessment/*` 为主，`wx_miniprogram` 只做 shadow/contract parity |
| Tests | assessment service、mobile router、learner-state writeback、view-model、WeChat/`/wechat-harness` smoke |

禁止触碰：

1. 不新增 `/api/v1/mobile/tutorbot/ws/...` 或 assessment 专用聊天 WebSocket。
2. 不新增第二套题库表来绕开 `questions_bank`。
3. 不让 LLM 即兴生成正式可比考试分数的题。
4. 不让前端缓存成为答案、分数、错因或 mastery authority。
5. 不把测评结果直接写成不可撤销长期画像；低置信结果只写 observation / candidate。

### 2.4 verification target

P0 完成定义：

1. 学员能从小程序进入“专题测评 / 模拟测评”，拿到一套完整题卡。
2. 做题中不展示标准答案、解析、采分点或深度提示。
3. 切后台 / 返回后能恢复未提交 session。
4. 提交后一次性显示得分、正确/错误、简单解析和知识点分布。
5. 点击单题“详细解析”才触发二次 LLM 解析，并能缓存结果。
6. 每道作答写入 `learning_evidence`，错题进入云端错题 projection。
7. 学情报告能看到本次测评对弱点、掌握度、下一步训练的影响。
8. `measurement_confidence` 保护低质量答卷，不把乱答写成稳定 learner truth。

---

## 3. Single Authority Hard Gate

### 3.1 one business fact

本模块维护的一等业务事实：

> 一次测评是一组服务端组装、版本化、可恢复、可提交、可计分的 assessment session；每一道题的作答都是 learning evidence；测评报告只是该 session 的 read model，不是新的学情 authority。

### 3.2 one authority

| 事实 | 唯一 authority |
| --- | --- |
| 题目资产 | `questions_bank` + canonical `QuestionArtifact` |
| 正式组卷蓝图 | `AssessmentBlueprintService` / `AssessmentBlueprint` |
| 预构建卷面 | `assessment_forms` |
| 学员一次答卷 | `assessment_sessions` |
| 客观题答案 | server-side hidden `session_questions[].answer_key` |
| 案例题/rubric | `construction_grading` / grading kernel |
| 简单解析 | stored item artifact / option reasoning / minimal rationale |
| 详细解析 | `SubmissionGraderAgent` + RAG + question lifecycle context |
| 长期学习事实 | `learner_memory_events.learning_evidence` |
| 学情展示 | `learning_report_read_model`、attempt detail、mistake-book read model |
| 下一步训练 | `training_intent` / study plan projection |

### 3.3 competing authorities

必须删除、降级或防止越权：

| 竞争者 | 风险 | 处理 |
| --- | --- | --- |
| 前端临时答案缓存 | 被误当作提交 truth 或恢复后覆盖服务端 | 只作 draft；提交以 server session 为准 |
| LLM 即兴组卷 | 无版本、无难度、不可比、不可审计 | 只允许作为 practice draft；正式测评必须来自 bank 或 validated form |
| `deep_question` 自由生成多题 | 与 assessment session 竞争题目 lifecycle | 练习归 `deep_question`，整卷测评归 assessment session |
| 试卷报告自行估计 mastery | 产生第二套学情 | 报告只展示本 session；长期状态由 learner-state synthesis 读 evidence |
| 简单解析与深度解析混算 | 成本高且解释可能不对用户错误 | 提交后给 simple review；按需 deep explanation |
| 旧 `assessment` aggregate event | 只能表示一次测评摘要，不足以支撑逐题学情 | 保留 aggregate event，同时新增 per-item `learning_evidence` |

### 3.4 canonical path

```text
User selects assessment type
  -> Mobile assessment API
  -> AssessmentBlueprintService chooses blueprint/form
  -> assessment_sessions stores redacted/public + hidden/grading artifact
  -> Mini program renders full paper with local draft autosave
  -> User submits all answers
  -> Scoring service grades objective items
  -> construction_grading handles rubric/case items
  -> Result report shows score, wrong items, simple explanation
  -> Write aggregate assessment event + per-item learning_evidence
  -> Mistake book / attempt detail / learning report projections update
  -> User clicks deep explanation
  -> unified /api/v1/ws question_review turn with assessment item context
  -> cache explanation by assessment_session_id + item_id + grading_result_hash
```

### 3.5 delete or demote

1. Demote “聊天里再来一套题” from formal assessment to practice generation.
2. Demote LLM-authored formal paper to draft / internal review only.
3. Delete any frontend-side correctness/mastery calculation beyond display formatting.
4. Demote `last_assessment` from sole assessment memory to aggregate projection; per-item evidence enters `learning_evidence`.
5. Keep `assessment_profile` as read projection, not report-page inference.

---

## 4. Product Scope

### 4.1 All assessment types delivered across P0-P2

| Type | User promise | Source | Scoring | Feedback mode | Writeback | Phase |
| --- | --- | --- | --- | --- | --- | --- |
| `diagnostic` | 摸底画像和教学策略种子 | Existing `AssessmentBlueprintService` diagnostic sections | Objective scorer + profile probes | Deferred | Aggregate assessment event + teaching policy seed | existing |
| `topic_diagnostic` | 系统测试某个知识模块；P0A 先做防水或防水/装饰/机电 composite pilot | `questions_bank` by topic/node_code/tags | Objective scorer first; rubric if available | Deferred | Per-item `learning_evidence` + aggregate event | P0A |
| `real_exam_simulation` | 尽量接近真题样式，含案例材料/综合判断 | `REAL_EXAM` preferred, then `TEXTBOOK_ASSESSMENT` | Objective + structured case scoring | Deferred | Same | P0B |
| `mastery_check` | 验证近期弱点是否真的改善 | `training_intent` + recent weak evidence + bank candidates | Objective / rubric | Deferred or short set | Same; marks verification outcome | P1 |
| `adaptive_assessment` | 根据前半卷表现调整后半卷 | Calibrated item bank + item analytics | Objective/rubric + confidence model | Deferred | Same, with calibration metadata | P2 |

`diagnostic` 继续保留现有摸底入口，是 `Assessment Blueprint` 已有能力，不被本计划替代。

### 4.1.1 P0 delivery order

| Slice | Ships | Does not ship yet | Why |
| --- | --- | --- | --- |
| P0A | `topic_diagnostic` only: 防水或 composite 防水/装饰/机电 10-12 题 | real-exam simulation, mastery_check, subjective case scoring, deep explanation cache | 最短链路验证：专题覆盖、整卷 deferred feedback、逐题 evidence、报告可读 |
| P0B | `real_exam_simulation` mini 20 题 | full-length mock exam, strict timer, equivalent score scale | 先验证 source policy、form comparability、case stimulus 展示 |
| P1 | `mastery_check` and deep explanation | CAT adaptive, teacher authoring | 需要先确认 training_intent、attempt refs、explanation cache 已稳定 |
| P2 | subjective case grading and adaptive | high-stakes score interpretation | 需要 rubric coverage 和 grading confidence 数据 |

P0A 是唯一必须先上线验收的路径。其他路径只做 schema/API 兼容设计，不抢 P0 验收定义。

### 4.2 P0 non-goals

1. 不做完整 CAT / IRT 自适应。
2. 不做教师端完整出卷后台。
3. 不做 QTI 导入导出。
4. 不做 LLM 生成题直接进正式考试。
5. 不做强制监考、防切屏惩罚、反作弊。
6. 不做跨学科泛化，只在字段上预留 `subject_id`。
7. 不把详细解析预生成给所有题。
8. 不把心理/习惯题混入专题测评分数。
9. 不把 P0A 专题卷分数包装成“全科真实水平”。
10. 不把防水专题 pilot 的通过率当成整套考试产品已经成立。

### 4.3 Product states

| State | Meaning | User-visible behavior | Transition / TTL |
| --- | --- | --- | --- |
| `created` | 服务端已创建 session，未开始 | 展示说明和开始按钮 | Create API returns session; if no first answer in 24h, expire |
| `in_progress` | 学员正在答题 | 展示题卡、进度、剩余未答数、草稿状态 | First answer or explicit start; `in_progress` -> `expired` after 24h unless user submits |
| `autosaved` | 本地或服务端保存草稿 | 切后台回来可继续 | Local draft save or server draft PATCH; never overrides submitted server answer |
| `locked_by_other_device` | 另一个设备持有答题 lease | 后开端只读，提示在原设备继续或申请接管 | Lease: 先开端持有；后开端只读 until lease expires or explicit takeover |
| `submitted` | 已交卷，不再允许改答案 | 展示计分中 | Submit accepted and immutable answer snapshot written; `submitted` -> `scored` after scoring, with 30s timeout |
| `scored` | 已有总分和逐题判定 | 展示结果页和简单解析 | Scoring and all required writeback succeed; `scored` -> `degraded` if any required per-item writeback fails |
| `reviewing_item` | 单题详细解析生成中 | 单题显示 loading，不阻塞整页 | Phase 2/P1 only; item-level explain request accepted |
| `review_unlocked` | 深解已生成并缓存 | 单题显示详细解析 | Phase 2/P1 only; explanation cache written for result hash |
| `expired` | 长时间未提交 | 可重开新卷，旧卷不进正式学情 | `created/in_progress` exceeds 24h TTL or form retired before submit |
| `degraded` | 题源/评分/写回部分失败 | 清楚标注，不伪装正式结果 | Any required per-item writeback fails, scoring partially fails, or source/redaction gate fails after session start |

### 4.3.1 Device lease and draft conflict policy

P0A 最简并发策略：

1. Server session owns the truth. Local draft is only a convenience cache.
2. Each active run records `session_owner_device_id`, `lease_started_at`, and `lease_expires_at`.
3. First active device holds a short renewable lease; a second device can view progress but cannot submit until lease expires or user explicitly takes over.
4. Network reconnect uses server-wins: client draft uploads only when server has no answer for that item. A stale local draft must never overwrite a server answer or submitted result.
5. Duplicate submit returns the original scored result and original evidence refs; it must not create a second attempt lineage.

---

## 5. Concept Model

### 5.1 Keep existing terms canonical

本计划不发明新的核心数据真相。产品可以说“试卷”，代码优先沿用 assessment 词汇。

| Product word | Canonical internal term | Notes |
| --- | --- | --- |
| 试卷 / 测评卷 / TestSet | `AssessmentBlueprint` + `assessment_form` | Blueprint 定规则，form 是一次可交付卷面 |
| 一次答卷 / 考试记录 | `assessment_session` | 用户级 run，持久化题目快照和隐藏答案 |
| 题目 | `QuestionArtifact` / `session_question` | Public redacted + hidden grading key |
| 答题记录 | `assessment_item_attempt` projection | P0 可存在于 session JSON；P1 拆表方便查询 |
| 分数报告 | `assessment_result` read model | 本 session 的报告，不是长期学情 |
| 详细解析 | question lifecycle `question_review` turn | 通过统一 `/api/v1/ws`，不新增专用聊天入口 |
| 学情事实 | `learner_memory_events.learning_evidence` | 长期状态唯一事件流 |

### 5.2 Proposed payload shape

```json
{
  "quiz_id": "quiz_x",
  "assessment_type": "topic_diagnostic",
  "subject_id": "construction_exam",
  "blueprint_version": "topic_diagnostic_v1",
  "form_id": "topic_waterproof_v1_form_03",
  "status": "in_progress",
  "sections": [
    {
      "section_id": "waterproof_basics",
      "label": "防水材料与设防要求",
      "count": 5,
      "scored": true,
      "knowledge_nodes": ["waterproof.material", "waterproof.grade"]
    }
  ],
  "questions": [
    {
      "question_id": "q_01",
      "source_question_id": "questions_bank:...",
      "question_type": "single_choice",
      "stem": "...",
      "options": [{"id": "A", "text": "..."}],
      "public": {"show_answer": false, "show_explanation": false}
    }
  ],
  "runtime": {
    "duration_seconds": 900,
    "feedback_policy": "deferred",
    "resume_enabled": true
  }
}
```

Hidden session storage may include:

```json
{
  "session_questions": [
    {
      "question_id": "q_01",
      "source_question_id": "...",
      "answer_key": ["B"],
      "grading_key": {
        "scoring_points": [],
        "common_traps": [],
        "minimal_rationale": "..."
      },
      "knowledge_context": {
        "subject": "建筑实务",
        "chapter": "防水工程",
        "knowledge_points": ["地下防水等级", "卷材搭接"]
      },
      "evidence_refs": [
        {"source": "questions_bank", "id": "..."}
      ]
    }
  ]
}
```

---

## 6. Assembly Rules

### 6.1 Topic diagnostic

目标：系统性测某个知识模块，例如“防水工程”。

Current-code constraint: `deeptutor/services/assessment/blueprint.py` 目前只有 `waterproof_decoration_mep` section，label 为“防水 / 装饰 / 机电”，topics 为 `("防水", "装饰", "机电")`。因此 P0A 不能默认声称已有独立 `waterproof` topic。

Phase -1 must choose one of two paths before coverage gate:

1. Split topic granularity: add independent `waterproof`, `decoration`, `mep` blueprint sections and run coverage audit on `waterproof`.
2. Pivot product scope: ship P0A as “防水/装饰/机电综合测评”，copy and score interpretation must say composite topic.

Until this decision is made, any “防水工程 12 题” number is provisional.

P0A topic split decision: 当前 blueprint 是 `waterproof_decoration_mep` 合并 topic。Phase -1 必须二选一：(a) 切分独立 `waterproof` + migration，或 (b) P0A 改名为“防水/装饰/机电综合测评”并复用 composite。

P0 default:

| Section | Count | Source priority | Purpose |
| --- | ---: | --- | --- |
| 基础概念 | 3 | `TEXTBOOK_ASSESSMENT` -> `TEXTBOOK` | 确认名词、构造、材料 |
| 规范/做法判断 | 4 | `REAL_EXAM` -> `TEXTBOOK_ASSESSMENT` | 检查标准、工序、质量要求 |
| 易混选项 | 3 | `REAL_EXAM` -> `TEXTBOOK_ASSESSMENT` | 暴露常见误区 |
| 短案例/综合判断 | 2 | `REAL_EXAM` -> `case_study` | 检查应用能力 |

Rules:

1. P0 题量默认 10-12 题；用户可选 10 / 20 只在 coverage audit 通过后开放。
2. 每个 scored item 必须有 `source_question_id`、knowledge node、answer key。
3. 每套卷不得重复同一 `source_question_id`。
4. 正式专题测评不得只有 1 套卷。每个开放专题至少准备 3 套不重复 scored 题源的等价 form；稳定推荐专题目标为 5 套 form。
5. 同一专题 form bank 内 scored `source_question_id` 和可用 `semantic_signature` 必须跨 form 去重；不能只换题序伪装成新卷。
6. 近期做过的题默认避让，除非 mode 为 `mastery_check`。
7. 如果某 topic 覆盖不足，fail closed，并显示“该专题题库正在维护”，不静默换成泛题。
8. 12 题 section distribution 必须经教研签字；PRD 中的 `3/4/3/2` 未经教研评审, pending §17 sign-off，不是最终蓝图。

P0A 防水专题 hard gate:

| Gate | Minimum |
| --- | --- |
| topic granularity decision | independent `waterproof` split or explicit composite `waterproof_decoration_mep` pivot |
| form rotation | minimum 3 non-overlapping forms; target 5 forms for stable recommendation |
| available source candidates | for 12-item P0A: minimum 36 unique eligible scored candidates to open; target 60 unique eligible candidates for stable 5-form rotation; section-level floor = section count × target form count |
| REAL_EXAM/TEXTBOOK_ASSESSMENT share | >= 50% if available; otherwise product copy must say "专项练习测评" not "真题样式" |
| answer key coverage | 100% |
| knowledge node coverage | 100% via `node_code/tags/attributes/source_meta` projection |
| simple explanation source | stored rationale / option reasoning / grading keywords; if absent, show "仅保留标准答案，详细解析需生成" |
| mobile readability | no item stem over agreed mobile threshold without stimulus split |
| teaching review | P0A blueprint distribution and copy signed off by教研 |

If any hard gate fails, P0A must not silently degrade to generic construction questions. It should return a maintained empty state and an authoring backlog.

Candidate-pool rationale:

1. `1:1` / single-form topics are not formal TestSet; they are practice drills and must not feed stable assessment claims.
2. `3:1` is the minimum to open a topic because it supports three non-overlapping forms and basic retake freshness.
3. `5:1` is the stable recommendation target because it supports repeated learner attempts without turning score gains into memorization artifacts.
4. For 12-item P0A, `36` unique candidates is the launch floor and `60` unique candidates is the stable target. If section-level floors fail, block or author more items rather than silently mixing generic topics.

P0A+ Topic TestSet Catalog:

P0A 防水卷打通后，正式入口不能停留在单一“防水”按钮。系统必须提供专题测评目录，并对每个专题执行同一套 form-bank gate。

| Topic id | User-facing topic |
| --- | --- |
| `waterproof` | 防水工程 |
| `decoration` | 装饰装修 |
| `mep` | 建筑机电 |
| `foundation` | 地基基础 |
| `main_structure` | 主体结构 |
| `formwork_scaffold` | 模板脚手架 |
| `safety` | 安全管理 |
| `schedule` | 进度计划 |
| `contract_claim` | 合同索赔 |
| `quality_acceptance` | 质量验收 |

Catalog status rules:

1. `stable`: 该专题已持久化至少 5 套 active `assessment_forms`，每套 12 题，scored `source_question_id` 跨 form 去重。
2. `pilot`: 该专题已持久化 3-4 套 active forms；可开放，但前端和 QA 必须标记为试运行覆盖。
3. `authoring_needed`: 少于 3 套 active forms；前端目录可展示维护态，但不得开放正式测评。
4. Runtime catalog 不能只数 active rows；达到 3/5 门槛后必须调用 persisted form-bank validator，确认题量、section floor、跨 form 去重均成立。验证失败时即使 active rows=5，也必须标记 `authoring_needed`。
5. Topic catalog 是 TestSet 启动前的可用性 read model；它只读取 `assessment_forms` / blueprint coverage，不读取或推断 learner mastery。
6. 个性化推荐必须作为 catalog 旁边的独立 `recommendation` read model：证据不足推荐 `diagnostic_v1` 20 题综合摸底；已有弱点且对应专题 enabled 时推荐该专题；不得推荐 `authoring_needed`；不得写 `training_intent` 或覆盖 study-plan 处方 authority。
7. 批量预生成脚本必须先 dry-run，再在 `assert_target_database_is_main()` 通过后 persist；不允许第一个学员点击“开始诊断”时在线冷启动构建全专题 form bank。

### 6.2 Real exam simulation

目标：尽可能像真实考试或真题训练。

P0 default:

| Section | Count | Source priority |
| --- | ---: | --- |
| 单选 | 10 | `REAL_EXAM` first |
| 多选 | 5 | `REAL_EXAM` first |
| 案例材料 + 客观小题 / 结构化判断 | 3-5 | `REAL_EXAM` / `case_study` |

规则：

1. P0 不承诺完整官方考试题量，只承诺“仿真测评小卷”。
2. 题源必须保留 `exam_year / source_type / provenance`。
3. `REAL_EXAM_OFFICIAL` label requires both provenance metadata and教研/manual review approval. If either is missing, user-facing copy must avoid “官方真题卷”，改为“真题样式测评”或“专项测评”。
4. 案例材料过长时必须拆成 mobile-readable stimulus + sub-items。
5. 同一 `form_id` 的题量、难度、section 结构固定，保证报告可比。

### 6.3 Mastery check

目标：验证学情里的弱点是否改善。

Inputs:

1. `training_intent`
2. recent `learning_evidence`
3. mistake clusters
4. weak knowledge nodes
5. recent attempts exclusion list

P0 default:

| Section | Count | Meaning |
| --- | ---: | --- |
| 原弱点同知识点 | 4 | 检查是否理解 |
| 变式/相邻知识点 | 4 | 检查迁移 |
| 复盘题 | 2 | 检查是否还犯同类错 |

规则：

1. mastery check 的结果必须写 `verification_outcome`。
2. 正确一次不等于 mastered；P0 只写 `verified_once`。
3. 若再次错误，标记 `recurring`，进入错题集和下一轮训练 intent。
4. 不能因为用户未完成 mastery check 就降低长期 mastery，只能标记 `not_verified`。

---

## 7. User Experience

### 7.1 Entry points

P0 入口：

1. 学情首页 focus action: “做一次专项测评”
2. 知识点详情页: “测一测防水工程”
3. 错题/弱点卡: “复测这个弱点”
4. 练题页: “切换为整卷测评”
5. 首页/学习计划: `training_intent.action_mode=assessment`

普通聊天推荐卡不能把 assessment 伪装成追问 prompt。它必须是独立 action，跳 assessment 页面。

### 7.2 In-run page

页面必须像测评工具，不像聊天：

1. 顶部：卷名、题数、已答/未答、保存状态。
2. 主区：题干、选项、案例材料、题号切换。
3. 底部：上一题、下一题、题号面板、交卷。
4. 未答交卷：提示未答题数量，允许继续或确认交卷。
5. 禁止：任何“点我看解析 / 提示 / 答案”。

### 7.3 Result page

提交后第一屏回答五件事：

1. 我得了多少分？
2. 哪些题错了？
3. 错在哪里？
4. 哪些知识点暴露问题？
5. 下一步先做什么？

Result page P0 sections:

| Section | Content |
| --- | --- |
| Score summary | 总分、正确率、用时、measurement confidence |
| Knowledge map | 按章节/知识点的正确率和证据数 |
| Wrong items | 题号、我的答案、正确答案、简单解析、知识点 |
| Simple next action | P0A 用本次测评 session-local 建议 + 跳转学习计划；不直接写 `training_intent` |
| Deep explanation CTA | P0A hidden/disabled；Phase 2/P1 后每题独立按钮，按需生成 |

P0A next-action rule:

1. Result page may say “本次测评建议你先复盘地下防水等级和卷材搭接”，because it is a session-local recommendation.
2. Result page must not say “系统已为你更新长期训练计划”，unless learner-state synthesis / study-plan projection has actually consumed the new evidence.
3. The CTA should be “去学习计划查看更新” or “先复盘本卷错题”，not a direct `training_intent` mutation from submit.

### 7.3.1 Simple next action authority

P0A chooses option C: Simple next action 默认文案为“根据本次测评更新训练计划中, 前往学习计划查看”，并跳转 `study_plan`。`study_plan` 消化 assessment evidence 后再读取 `training_intent`。

This preserves study_plan as sole prescription authority, aligned with sibling plan `2026-05-22-luban-learning-state-inference-engine-transformation-plan.md` §0.C. Assessment submit writes evidence and session-local next action only; it does not become a prescription writer.

### 7.4 Deep explanation interaction

本节描述 Phase 2+ 完整体验。P0A/P0B result page 显示 disabled CTA + “详细解析下个版本上线”。

This section describes the full Phase 2/P1 experience. P0A ships without working deep explanation: result page either hides the CTA or shows disabled copy such as “详细解析下个版本上线”。Do not implement this as a P0A blocker.

点击“详细解析”时：

1. 前端携带 `assessment_session_id + question_id + attempt_ref`。
2. 后端恢复 session artifact、learner answer、grading result 和 evidence refs。
3. 通过统一 `/api/v1/ws` 或 existing question lifecycle service 进入 `question_review` / grading follow-up scene。
4. 解析应包含：
   - 题目考点
   - 为什么正确答案对
   - 为什么我的答案错
   - 选项对比 / 采分点
   - 易错点
   - 记忆钩子
   - 下一题建议
5. 结果缓存，避免重复消耗 LLM。

禁止：

1. 在提交前触发 deep explanation。
2. 让 deep explanation 改写原始得分。
3. 让 deep explanation 单独写 mastery；它只能补充 explanation evidence，真正 mastery 仍由作答和 grading evidence 决定。

---

## 8. Scoring And Reporting

### 8.1 Score layers

| Score | Source | Meaning |
| --- | --- | --- |
| `raw_score` | correct / total | 直观正确率 |
| `weighted_score` | section weights | 模拟卷或专题卷加权分 |
| `knowledge_scores` | per node attempts | 知识点维度 |
| `case_score` | rubric points | 案例/结构化题 |
| `measurement_confidence` | completion/time/pattern/source | 本次结果可信度 |

### 8.1.1 Score interpretation rules

The product must separate three claims:

| Claim | Allowed basis | Forbidden shortcut |
| --- | --- | --- |
| 本卷得分 | This submitted assessment session | None |
| 本专题掌握证据 | Per-item `learning_evidence` from this topic plus recent history | Raw paper score alone |
| 全科能力判断 | Multiple assessments / practice / grading evidence compiled by learner-state read models | One topic paper |

Student copy examples:

- Good: "这次防水专题测评 12 题答对 8 题。错题集中在地下防水等级和卷材搭接。"
- Good: "这是一条新的掌握证据，我会把它和最近错题一起更新到学情。"
- Bad: "你的一建建筑实务水平是 67 分。"
- Bad: "防水专题过了，所以防水已掌握。"

This avoids turning a small topic paper into an overconfident global diagnosis.

### 8.2 Objective scoring

1. 单选：exact match。
2. 多选：P0 可全对得分；P1 支持少选/错选部分分。
3. 判断/结构化：按 answer key。
4. 客观题 scorer 不能调用 LLM。
5. scorer 输入必须来自 server hidden session，不读前端 `correct_answer`。

### 8.3 Case scoring

P0:

1. 只支持已有 structured key 或 short-case objective sub-items。
2. 如果 rubric 不足，题目不得进入正式 case-score 分母。

P1:

1. 使用 `construction_grading` / `CaseGradingSkillKernel`。
2. 输出 scoring point breakdown。
3. 对每个 missing scoring point 写 learning evidence。
4. 低置信 LLM grading 标记 `needs_review`，不写稳定 mastery。

### 8.4 Measurement confidence

最低信号：

| Signal | Use |
| --- | --- |
| completion rate | 未完成不写正式 mastery |
| total time | 秒选降低 confidence |
| per-item time | 识别乱答 |
| repeated option pattern | 降低 confidence |
| source coverage | 题源不足则 degraded |
| grading confidence | case grading 低置信不稳定写回 |
| `pattern_anomaly` | 用户答题模式 vs 题目难度反常匹配（全对难题/全错易题）；P0 不实现, hook reserved, formula TBD Phase 3 |

写回策略：

| Confidence | Writeback |
| --- | --- |
| `high` | aggregate assessment event + per-item learning evidence; learner-state synthesis may later update training intent |
| `medium` | per-item evidence 写入，profile/mastery update 降权 |
| `low` | 只写 attempt observation，不提升/降低稳定 mastery |

---

## 9. Learner State Writeback

### 9.1 Aggregate event

保留现有 aggregate assessment event，用于：

1. `last_assessment`
2. `teaching_policy_seed`
3. assessment profile projection
4. BI / funnel / observability

Example:

```json
{
  "memory_kind": "assessment",
  "source_feature": "assessment",
  "payload": {
    "quiz_id": "quiz_x",
    "assessment_type": "topic_diagnostic",
    "blueprint_version": "topic_diagnostic_v1",
    "score": 72,
    "measurement_confidence": "high"
  }
}
```

### 9.2 Per-item learning evidence

新增或扩展 writeback：每道 scored item 都写一条 `learning_evidence`。

Example:

```json
{
  "memory_kind": "learning_evidence",
  "source_feature": "assessment_testset",
  "dedupe_key": "assessment_item:{user_id}:{quiz_id}:{question_id}",
  "payload": {
    "event_type": "learning_evidence",
    "evidence_source": "assessment_testset",
    "assessment_type": "topic_diagnostic",
    "quiz_id": "quiz_x",
    "question_id": "q_01",
    "source_question_id": "questions_bank:...",
    "attempt_ref": "attempt_...",
    "learner_answer": ["A"],
    "correct_answer": ["B"],
    "is_correct": false,
    "knowledge_points": ["地下防水等级"],
    "error_codes": ["M02"],
    "measurement_confidence": "high",
    "simple_explanation": "..."
  }
}
```

Rules:

1. `dedupe_key` 必须包含 user/session/question，重复提交不重复写。
2. 错题写入 cloud mistake-book projection，不能只留前端本地缓存。
3. 正确题也应写 evidence，但 read model 可按权重消费。
4. 未作答题只写 `blank_attempt`，不作为 mastery 负证据，除非模拟考试规则明确。
5. `deep_explanation` 可追加为 detail/read projection，不改原始 correctness。
6. `error_codes` 只允许来自 `deeptutor/contracts/error_codes.py:ERROR_CODE_REGISTRY` and `docs/contracts/error_code_registry.md`:
   - MCQ/objective item uses `M01-M10` unless the registry is extended first.
   - Case/essay item uses `E01-E12` unless the registry is extended first.
   - `unknown_error` is fallback only, not a product taxonomy.
7. Release gate must run `python scripts/check_contract_guard.py`; any new error code requires a contract registry PR before writeback emit sites land.

### 9.2.0 Error code authority

`error_codes` 仅来自 `deeptutor/contracts/error_codes.py:ERROR_CODE_REGISTRY` (`M01-M0X` / `E01-E12`)。Release gate 必含 `python scripts/check_contract_guard.py`。新 code 须先走 registry PR，再落 writeback emit site。

### 9.2.1 Current-code gap to close

Current implementation evidence from `MemberConsoleService`:

1. `create_assessment(user_id, count)` creates `assessment_sessions[quiz_id]` and stores hidden `session_questions`.
2. `submit_assessment(...)` computes score, updates `member["last_assessment"]`, learning daily/chapter stats, and calls `_write_assessment_learning_signals`.
3. `_write_assessment_learning_signals(...)` writes one aggregate `memory_kind="assessment"` event and patches teaching policy overlay.

Therefore P0A is not complete until the submit path also:

1. emits one `learning_evidence` event per scored item,
2. signs an `attempt_ref` for each item after event_id exists,
3. writes wrong items through the same cloud mistake-book authority used by grading writeback,
4. returns a result report that includes item-level attempt refs,
5. proves duplicate submit returns the same event refs instead of duplicating evidence.

Do not report P0A done if only `last_assessment` changed.

### 9.2.2 Assessment result to study-plan decision

Current code search shows no `assessment -> training_intent` write path. `study_plan.py` reads `active_training_intent`, so a submit-time result page that blindly reads `training_intent` may show stale advice from a previous synthesis run.

P0A decision: choose option C.

1. `submit_assessment` writes assessment evidence and returns a session-local recommendation for this result page.
2. It does not synchronously mutate `training_intent`.
3. Learning report / study plan remains the prescription authority and consumes the new evidence through its existing synthesis/read-model path.
4. Result page copy must distinguish “本次测评建议” from “长期学习计划已更新”。

Rejected for P0A:

1. Option A: synchronous `update_training_intent_from_assessment()` in submit. It improves immediacy but turns submit into a second prescription writer and adds latency.
2. Option B: async enqueue plus “稍后更新” copy. It is acceptable fallback, but the product experience is weaker than showing a session-local next step plus study-plan CTA.

### 9.3 Learning report consumption

学情页消费规则：

1. 总结弱点只读 `learning_report_read_model`。
2. 试卷报告可以作为 recent attempt source 展示。
3. `attempt_detail` 必须能打开到本次测评单题。
4. `mistake_book` 只读云端 projection。
5. `training_intent` 可以在 learner-state synthesis 消费本次 evidence 后生成下一步复测任务；assessment submit 不直接成为长期 prescription writer。

Forbidden:

1. assessment result page 不直接更新 mastery card 文案。
2. frontend 不按正确率现场算“掌握/未掌握”标签。
3. LLM detailed explanation 不直接改错因 taxonomy。

---

## 10. API And Service Design

### 10.1 Mobile API

P0 优先复用 `/api/v1/mobile/assessment/*`，避免新 surface 漂移。

| Endpoint | Status | P0 change |
| --- | --- | --- |
| `POST /api/v1/mobile/assessment/create` | Existing | 增加 `assessment_type`, `subject_id`, `topic_ids`, `count`, `duration_policy` |
| `POST /api/v1/mobile/assessment/{quiz_id}/submit` | Existing | 返回 result report + writeback status + confidence |
| `GET /api/v1/mobile/assessment/profile` | Existing | 继续作为长期 projection，不替代试卷报告 |
| `GET /api/v1/mobile/assessment/{quiz_id}` | New P0/P1 | 恢复未提交 session |
| `PATCH /api/v1/mobile/assessment/{quiz_id}/draft` | New P1 | 服务端草稿保存；P0 可先本地草稿 |
| `GET /api/v1/mobile/assessment/{quiz_id}/report` | New P0 | 读取已提交报告 |
| `POST /api/v1/mobile/assessment/{quiz_id}/items/{question_id}/explain` | New P1 | 创建/读取 deep explanation cache；内部仍走 unified question lifecycle (Phase 2+, not P0A blocker) |

如果 deep explanation 需要 streaming，前端应打开统一 `/api/v1/ws`，传入 assessment item context；禁止新增 assessment-specific WebSocket。

### 10.2 Service modules

| Service | Role |
| --- | --- |
| `AssessmentBlueprintService` | 继续作为 blueprint/form authority；扩展多 assessment type |
| `AssessmentAssemblyService` | 可选 thin service，封装 topic/real-exam/mastery-check 的 assembly policy；不得绕开 blueprint |
| `AssessmentSessionRepository` | 读写 `assessment_sessions`，提供 resume/submit idempotency |
| `AssessmentScoringService` | deterministic objective scoring + score aggregation |
| `AssessmentWritebackService` | aggregate event + per-item `learning_evidence` + mistake-book writeback |
| `AssessmentReportReadModel` | 只读 session result，给结果页和 attempt detail |
| `AssessmentDeepExplanationService` | 恢复 item context，调用 unified question lifecycle / `SubmissionGraderAgent`，缓存结果 |

### 10.3 Data persistence strategy

P0A formal assessment cannot rely on the current member-console JSON file for active sessions. Existing JSON storage is acceptable only for local/dev compatibility; production P0A requires durable server-side session persistence.

| Data | P0A requirement | Durable target |
| --- | --- | --- |
| Prebuilt forms | existing `assessment_forms` | same |
| Active sessions | Supabase `assessment_sessions` table with owner/device/status fields | same, with RLS and idempotent submit |
| Per-item attempts | session snapshot or `assessment_attempt_items` if needed for indexed report | `assessment_attempt_items` for detail/report |
| Deep explanation cache | local/session cache or generated on demand | `assessment_item_explanations` keyed by result hash |
| Learning facts | `learner_memory_events` | same |
| Mistake book | cloud projection | same |

Schema migration rule:

1. P0A entry gate includes designing and migrating durable `assessment_sessions`; this is not optional once the product is called formal TestSet.
2. Keep names aligned with existing assessment terms.
3. Any table that stores user answers requires RLS / owner check.
4. The migration must preserve hidden answer/grading artifacts server-side and expose only redacted client payloads.

### 10.4 Current-condition implementation decisions

Given the current repository shape, make these decisions before coding:

| Decision | Default | Verification |
| --- | --- | --- |
| Storage durability | **RESOLVED (2026-05-30 plan-vs-code 核验): Supabase `assessment_sessions` 表 + RLS 已落地并合 main（migration `20260524000100_assessment_sessions.sql`, PR #42 6a5dad2e）。`session_repository.py` 同时有 InMemory 与 Supabase 两实现，`MemberConsoleService._build_assessment_session_repository` 在 production 或 `ASSESSMENT_SESSIONS_USE_SUPABASE=true` 时走 durable。原 "P0A is BLOCKED until table exists" 已不成立；生产 apply 待运行环境实证。** | Migration + RLS + restart/deploy resume test prove active/submitted sessions survive multi-instance drift；生产侧需实证 `ASSESSMENT_SESSIONS_USE_SUPABASE` 已生效，避免静默回落 InMemory 丢卷 |
| New endpoint count | Keep existing `create/submit/profile`; add report/resume only if current surface cannot support P0A | API tests prove no duplicate surface |
| Deep explanation | P0A result page hides CTA or shows disabled "coming next"; working deep explanation is Phase 2/P1 | Prevents half-working expensive path |
| Frontend source | `yousenwebview/packageDeeptutor` primary; `wx_miniprogram` parity only | DevTools and Node tests target yusen package |
| Correct answers | Server hidden session only before submit | Snapshot tests against client payload |
| `last_assessment` | Aggregate projection only | Learning report tests prefer `learning_evidence` for detailed attempts |

P0A must not ship as a formal assessment if active/submitted sessions can disappear after restart, deploy, worker replacement, or container rescheduling. Sticky single-instance deployment can be a local demo workaround only; it is not an acceptable production authority.

---

## 11. Frontend Plan

Primary surface: `yousenwebview/packageDeeptutor`.

### 11.1 Pages

| Page | Purpose |
| --- | --- |
| `pages/assessment/index` | 选择测评类型、专题、题量 |
| `pages/assessment/run` | 整卷答题 |
| `pages/assessment/result` | 总分、错题、简单解析、下一步 |
| `pages/assessment/item-detail` | 单题详细解析 / attempt detail bridge |

如果现有 assessment 页面已经覆盖部分能力，优先扩展现有页面，不新建平行页面。

### 11.2 UX requirements

1. 首屏必须是可执行测评入口，不是营销说明。
2. 题号面板固定尺寸，不因题量变化造成布局跳动。
3. 交卷前显示未答题。
4. 提交后禁改答案。
5. 正确答案只在 result/detail 出现。
6. P0A 不启用 working deep explanation；Phase 2/P1 后按题加载，不阻塞总报告。
7. 网络失败时保留本地 draft，并说明是否已提交；冲突解法: server-wins. Client draft 仅在 server 无 attempt 时上传; server 已记录后 client draft 被覆盖。
8. 低置信/降级报告有清楚标记。
9. 多端同时打开同一 `quiz_id` 时，后开端默认只读或接管 lease，不允许两个设备同时提交不同 answer snapshot。

### 11.3 Web shadow harness

P0 需要 `/wechat-harness` 或 Node view-model 覆盖：

1. create session -> render paper
2. local draft restore
3. submit with wrong answers -> result report
4. no answer reveal before submit
5. deep explanation CTA hidden before submit and hidden/disabled after submit in P0A
6. report writes attempt refs for learning report

微信 DevTools 真入口验收仍以 `yousenwebview/packageDeeptutor` 为准。

---

## 12. Implementation Slices

### Phase -1 - Reality Check And No-Go Gates

Goal: prove the current system can safely host a formal TestSet before feature coding.

Tasks:

1. Audit current assessment route schema and confirm all clients using `/assessment/create`.
2. Decide P0A topic granularity:
   - split current `waterproof_decoration_mep` into independent `waterproof / decoration / mep`, or
   - pivot product copy to “防水/装饰/机电综合测评”。
3. Design durable Supabase `assessment_sessions` schema, RLS/owner checks, device lease fields, and submit idempotency. This is a P0A entry gate, not an audit.
4. Run a read-only Supabase/topic coverage audit for the chosen P0A topic/composite.
5. Inspect `questions_bank` candidate quality:
   - answer key present
   - options complete
   - node/topic projection present
   - source policy present
   - simple explanation or grading keyword available
6. Inspect yousen assessment page payload handling for answer reveal risk.
7. Audit downstream uses of `last_assessment`:
   - `rg -n "last_assessment" deeptutor/ web/ wx_miniprogram/ yousenwebview/`
   - any read of `last_assessment.score` as mastery must move to learning-report/evidence read model before P0A broad release.

No-Go if:

1. P0A cannot deliver at least 10 eligible waterproof items without generic fallback.
2. Durable Supabase session table/RLS/idempotency design is not ready.
3. client receives `answer`, `correct_answer`, `grading_key`, `scoring_points` before submit.
4. duplicate submit can duplicate learner events.
5. per-item `learning_evidence` cannot be written with `attempt_ref`.
6. the result page cannot be manually verified in WeChat DevTools.
7. `last_assessment` still has downstream readers treating aggregate score as mastery truth.

### Phase 0 - Design Lock And Audit

Goal: 锁定 authority 和真实差距，不先写 UI。

Tasks:

1. Audit current `AssessmentBlueprintService`, `assessment_forms`, `assessment_sessions`, mobile routes and yousen assessment pages.
2. Audit `questions_bank` coverage for the P0A use case first:
   - `topic_diagnostic: waterproof` only if independent topic split lands
   - otherwise `topic_diagnostic: waterproof_decoration_mep`
   - `real_exam_simulation: construction_exam_mini` is P0B, not a P0A blocker
3. Produce dry-run form candidates with section/topic/source/difficulty distribution.
4. Implement or migration-plan the durable session repository before Phase 1 coding starts.
5. Confirm learner-state writeback path for per-item `learning_evidence`.
6. Confirm P0A 12-item section distribution with教研, or revise to 8-10 items based on coverage.

Verification:

1. `scripts/audit_assessment_blueprint_coverage.py` extended or new dry-run script emits coverage JSON.
2. No code path exposes answer key in client payload.
3. Plan-to-code mapping documented before Phase 1.
4. Last-assessment audit result is recorded with owner and required migration path.

### Phase 1 - P0 TestSet Foundation

Goal: 让学员完成一套防水专题小卷，提交后得到可信报告。

Tasks:

1. Extend create request schema with `assessment_type`, `topic_ids`, `subject_id`.
2. Add blueprint variants:
   - `topic_diagnostic_v1`
   - reserve names for `real_exam_simulation_mini_v1` and `mastery_check_v1`, but do not make them P0A acceptance blockers
3. Build or persist equivalent forms for the approved P0A topic/composite.
4. Implement durable session repository and migrate active session read/write off member-console JSON for production P0A.
5. Implement result report read model.
6. Enforce deferred feedback.
7. Write aggregate assessment event and per-item learning evidence.
8. Add result page and run page view-models.

Verification:

1. Unit: blueprint creates exact count and no duplicate source questions.
2. Unit: submit is idempotent and does not duplicate learner events.
3. API: create/submit/report happy path and fail-closed path.
4. Learner-state: wrong item appears in mistake-book projection.
5. Frontend: answer key absent before submit; present after submit.
6. DevTools: run full assessment in `yousenwebview/packageDeeptutor`.

### Phase 2 - Deep Explanation And Attempt Detail

Goal: 错题能点击进入高质量二次解析，并和历史作答复盘打通。

Tasks:

1. Add assessment item detail read model.
2. Add deep explanation request/caching.
3. Use `SubmissionGraderAgent` + RAG grounding for detailed explanation.
4. Link result wrong item -> attempt detail.
5. Link learning report evidence card -> assessment item detail.
6. Add bounded generation policy:
   - only wrong/flagged items default to deep explanation CTA
   - correct items can request explanation, but behind a cost guard
   - cache key includes `quiz_id`, `question_id`, `learner_answer_hash`, `grading_result_hash`, `prompt_version`

Verification:

1. Detailed explanation references the same question, learner answer and grading result.
2. Detailed explanation does not alter score.
3. Repeated click uses cache or bounded generation.
4. Attempt detail displays question, answer, simple explanation and deep explanation.

### Phase 3 - Adaptive And Quality Upgrade

Goal: 从固定蓝图升级到更强的测量与教研质量闭环。

Tasks:

1. Two-stage adaptive form:
   - first 8 items broad scan
   - next 8 items weighted by weak areas
2. Equivalent form calibration:
   - difficulty balance
   - source balance
   - topic coverage
3. Generated draft item pipeline:
   - LLM drafts
   - validator
   - teacher/internal review
   - only validated items enter formal forms
4. BI item analysis:
   - item difficulty
   - discrimination proxy
   - high wrong-rate traps
   - stale standard risk

Verification:

1. Adaptive mode never breaks score comparability labels.
2. Generated items never enter formal forms without validation status.
3. BI reports show item-level quality flags.

### Phase 4 - Standards And Authoring

Goal: 具备长期教研生产能力。

Tasks:

1. QTI-compatible export mapping.
2. Teacher authoring/review surface.
3. Case material stimulus editor.
4. Rubric coverage dashboard.
5. Versioned assessment release process.

Verification:

1. Forms have stable version/release metadata.
2. Retired items no longer appear in new forms but old sessions remain reviewable.
3. Import/export dry-run does not lose answer/rubric/provenance.

---

## 13. Quality Gates

### 13.1 Product gates

| Gate | Requirement |
| --- | --- |
| `deferred_feedback_gate` | Before submit, client payload and UI contain no answer/explanation |
| `complete_session_gate` | Delivered count, section count and scored count match blueprint |
| `resume_gate` | In-progress session can resume without duplicate run |
| `submit_idempotency_gate` | Duplicate submit returns same result and no duplicate writeback |
| `simple_report_gate` | Result shows score, wrong items, simple explanation and knowledge map |
| `deep_explanation_gate` | Phase 2/P1 only: per-item deep explanation uses same artifact and does not change score |
| `learning_evidence_gate` | Each scored item writes or intentionally skips a `learning_evidence` event |
| `mistake_book_gate` | Wrong answered item appears in cloud mistake-book projection |
| `report_read_model_gate` | Learning report consumes assessment evidence through read model |
| `confidence_gate` | Low-confidence run does not become stable mastery truth |
| `p0a_scope_gate` | P0A only claims 防水专题小卷; no copy implies full exam-level diagnosis |
| `durability_gate` | In-progress/submitted sessions survive server restart or use durable table |
| `payload_redaction_gate` | `tests/api/test_mobile_assessment_payload_redaction.py` snapshot 测试客户端 payload 不含 `answer_key` / `scoring_points` / `correct_answer` / `minimal_rationale` |
| `copyright_copy_gate` | User-facing labels do not say "官方真题" unless source policy allows it |
| `cost_gate` | Deep explanation is lazy/cached and cannot be triggered before submit |
| `a11y_baseline_gate` | Keyboard navigation, ARIA labels/semantics, alt text for images, and color-blind-safe correctness markers are defined before broad release |

### 13.2 Engineering tests

Targeted test files:

1. `tests/services/assessment/test_blueprint_coverage.py`
2. `tests/services/assessment/test_testset_assembly.py` (new)
3. `tests/services/assessment/test_scoring.py` (new or extend)
4. `tests/services/assessment/test_writeback.py` (new)
5. `tests/api/test_mobile_router.py`
6. `tests/api/test_mobile_assessment_payload_redaction.py` (new)
7. `tests/services/learner_state/test_learning_report_read_model.py`
8. `yousenwebview/tests/test_package_assessment_contract.js`
9. `yousenwebview/tests/test_assessment_testset_view_model.js` (new)

Payload redaction snapshot test must fail if pre-submit client payload contains any forbidden key, including `answer`, `answer_key`, `correct_answer`, `grading_key`, `scoring_points`, `minimal_rationale`, `rubric`, `official_answer`, or `option_reasoning`.

Minimum local commands before merge:

```bash
PYTHONPATH=. pytest \
  tests/services/assessment/test_blueprint_coverage.py \
  tests/services/assessment/test_testset_assembly.py \
  tests/services/assessment/test_scoring.py \
  tests/services/assessment/test_writeback.py \
  tests/api/test_mobile_router.py \
  tests/api/test_mobile_assessment_payload_redaction.py \
  tests/services/learner_state/test_learning_report_read_model.py

node yousenwebview/tests/test_package_assessment_contract.js
node yousenwebview/tests/test_assessment_testset_view_model.js
python scripts/check_contract_guard.py
```

Manual gate:

1. WeChat DevTools open `yousenwebview/packageDeeptutor`.
2. Start topic diagnostic for 防水工程.
3. Answer all questions with at least one wrong answer.
4. Submit and verify no pre-submit answer reveal occurred.
5. Open wrong-item detail and confirm P0A deep explanation is hidden/disabled; Phase 2 manual gate may generate deep explanation.
6. Return to learning report and verify the new evidence appears or the degraded reason is clear.

### 13.3 Scenario matrix

Before broad release, run these scenarios through service tests or DevTools:

| Scenario | Expected behavior |
| --- | --- |
| New learner, no history | Can start P0A waterproof assessment; no mastery overclaim |
| Existing learner with weak waterproof evidence | Entry copy cites backend training intent or weak evidence; no frontend inference |
| User taps start twice | One active session or explicit replace flow; no duplicate formal sessions |
| Same quiz open on phone and desktop | First device holds lease; second device read-only or explicit takeover; no competing submit |
| User answers half and exits | Resume or explicit expired/degraded state; no fake score |
| Network drops then reconnects with stale local draft | Server-wins; local draft uploads only for unanswered server items |
| User submits twice | Same result and same evidence refs |
| User leaves blanks | Blanks shown in report; blank policy explicit; not silently scored as mastery failure unless mode says so |
| User answers in one repeated pattern | Score shown, `measurement_confidence` downgraded |
| Topic coverage short | Fail closed with maintenance copy; no generic fallback |
| Item missing simple explanation | Show correct answer + "detailed explanation available" state; no fabricated simple rationale |
| Long case stem on mobile | Stimulus split or excluded from P0A |
| Wrong answer item | Writes `learning_evidence`, appears in mistake-book, opens attempt detail |
| Correct answer item | Writes lower-weight verification evidence, does not auto-mark mastered |
| Deep explanation retry | Uses cache or bounded retry; does not change score |
| Old session after item retired | Still reviewable from session snapshot; not reassembled from current bank |
| Source policy unclear | Product copy avoids "official real exam"; item remains internal/training only if needed |

---

## 14. Observability

Trace fields:

| Field | Meaning |
| --- | --- |
| `assessment_type` | diagnostic / topic_diagnostic / real_exam_simulation / mastery_check |
| `blueprint_version` | versioned plan |
| `form_id` | delivered form |
| `quiz_id` | session |
| `subject_id` | P0 construction_exam |
| `topic_ids` | selected topics |
| `delivered_count` | actual items |
| `answered_count` | submitted answers |
| `score` | raw / weighted |
| `measurement_confidence` | high / medium / low |
| `writeback_status` | aggregate event + per-item events |
| `deep_explanation_cache_status` | miss / hit / failed |
| `degraded_reason` | explicit failure reason |

Metrics:

1. `assessment_start_rate`
2. `assessment_submit_rate`
3. `assessment_abandon_rate`
4. `assessment_resume_rate`
5. `assessment_scoring_error_rate`
6. `assessment_learning_evidence_write_rate`
7. `assessment_deep_explanation_click_rate`
8. `assessment_to_training_intent_rate`
9. `mistake_book_from_assessment_rate`
10. `low_confidence_run_rate`

Metric baselines and alert thresholds:

1. First 14-day P0A pilot cohort defines baseline for abandon rate, submit rate, resume rate, deep-explanation interest, and mistake-book engagement.
2. Alert thresholds should be tracked in the launch-readiness dashboard line of work, especially if `assessment_abandon_rate` or `assessment_scoring_error_rate` spikes after release.
3. `assessment_to_training_intent_rate` means “evidence later consumed by learner-state/study-plan synthesis”，not submit-time direct mutation.

Baselines tracked in `2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md`. Alert thresholds derived from first 14-day cohort, not hard-coded.

---

## 15. Risks And Mitigations

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| 题库覆盖不足 | 专题卷可能抽不到足够题 | dry-run coverage gate; fail closed; authoring backlog |
| 随机卷不可比 | 学员分数不稳定 | equivalent forms + `form_id` + difficulty/source balance |
| LLM 题进入正式分数 | 分数不可信 | generated items require validator/review status |
| 答案泄露 | 测评失效 | client redaction tests + payload snapshot tests |
| 详细解析成本过高 | 每次提交生成所有解析会慢且贵 | lazy generation + cache |
| 学情双 authority | 报告页和学情页结论冲突 | report shows session result; learner report reads evidence projection |
| 低质量作答污染画像 | 乱答被当真 | measurement confidence controls writeback |
| 案例题评分不稳 | 主观题误判影响信任 | P0 restrict to structured/click case; P1 rubric confidence + review flag |
| 版权/授权不明 | 真题外显风险 | source policy labels; avoid “官方真题” unless authorized |
| P0 scope too broad | 三种卷型一起做会拖垮交付 | Ship P0A 防水专题 first; P0B/P1 follow after evidence writeback is green |
| 当前 session 非 durable | 正式测评可能丢失 | P0A entry gate requires Supabase durable session table; member-console JSON only for local/dev |
| 防水 topic 不独立 | P0A 题源 gate 建在不存在的 topic 上 | Phase -1 split topic or pivot to composite copy before coverage audit |
| result page 读取旧 `training_intent` | 用户做完防水卷却看到旧学习计划 | P0A uses session-local next action + study-plan CTA; no submit-time training-intent write |
| `last_assessment` 被误当学情 truth | 学情继续双 authority | Per-item evidence is release blocker; `last_assessment` aggregate only |
| 简单解析缺失时 LLM 幻觉 | 用户看到不可信解释 | Simple explanation must be sourced; otherwise degrade and offer deep explanation |
| Deep explanation 成为新评分入口 | 二次解析改写分数 | Detailed explanation read-only; score immutable after submit |
| 多端/离线 draft 覆盖正式答案 | attempt lineage 混乱 | Server-wins + device lease + idempotent submit |

---

## 16. Open Questions

1. P0 首个专题是否固定为“防水工程”，还是从学情弱点自动选一个最高证据弱点？
   - Recommendation: 固定防水工程做 pilot，因为用户已明确举例，便于验收。

2. P0 模拟考试题量是多少？
   - Recommendation: 20 题 mini simulation。完整考试题量进入 P1。

3. P0 deep explanation 是否走 `/api/v1/ws` streaming？
   - Recommendation: 若微信端已有 streaming renderer 可复用，走统一 WS；否则 P0 先 REST trigger + polling，但内部仍使用 question lifecycle context，不新增 WS 路由。

4. `assessment_sessions` 是否立即迁 Supabase durable table？
   - Recommendation: 是。当前 storage 已确认为 single-instance JSON file；P0A formal TestSet 必须先设计并迁移 durable Supabase table。

5. 是否把每个正确题也写入 `learning_evidence`？
   - Recommendation: 写，但 read model 降权消费。正确题是“已验证”的证据，不能只保存错题。

6. a11y baseline 的最低验收是什么？
   - Recommendation: P0A 至少定义 alt text、ARIA/语义标签、键盘导航、色盲安全的对错标记；未满足前不做 broad release。

7. 防水专题题库覆盖是否足够支撑 10-12 题？
   - Uncertainty: 总题量足够不代表防水 eligible candidates 足够。
   - Verification: dry-run coverage report with exact filters, section-level form rotation and cross-form dedupe. If <36 unique eligible candidates, block P0A or create authoring backlog; if 36-59, mark as minimum pilot only; if >=60 with section floors satisfied, mark stable.

8. P0A 是否需要 deep explanation？
   - Recommendation: 不作为 P0A blocker。P0A 必须有 simple report + attempt refs；deep explanation is Phase 2 unless existing question lifecycle wiring is already green.

9. `assessment_type/topic_ids` 是 mobile public schema 还是 internal config？
   - Recommendation: Treat as public mobile API once shipped; add request contract tests and avoid unstable internal enum names in UI.

10. 是否允许用户交卷后重做同一卷？
   - Recommendation: P0A 不允许改原 session；允许 "再做一套同专题卷" 创建新 `form_id/session_id`，比较时标注不同 form.

11. 真题授权 authority 到底是谁？
   - Recommendation: `source_meta/provenance` 只能证明来源链路；是否允许对外使用“真题/官方”字样必须由教研 review + source policy sign-off 决定。

12. item discrimination 与 `pattern_anomaly` 公式如何定义？
   - Recommendation: P0 只预留 hook；Phase 3 基于真实 item difficulty、区分度、耗时和 cohort 表现再定公式。

13. P0A topic split 是否拆 `waterproof`，还是继续 `waterproof_decoration_mep`？
   - Recommendation: Phase -1 用覆盖 audit 决定；若独立防水不足，产品名必须改为“防水/装饰/机电综合测评”。

---

## 17. First Implementation Checklist

- [ ] Read current `AssessmentBlueprintService` and `MemberConsoleService.create_assessment/submit_assessment`.
- [ ] Design durable Supabase `assessment_sessions` schema — entry gate, not audit.
- [ ] Dry-run `topic_diagnostic_v1` for 防水工程.
- [ ] Decide P0A count and rotation from real waterproof eligible candidates: prefer 12 items × 5 non-overlapping forms; allow 12 × 3 only as minimum pilot with explicit sign-off; block if <3 forms.
- [ ] 教研签字 P0A blueprint 题型分布.
- [ ] Phase -1 audit: `rg -n 'last_assessment' deeptutor/ web/ wx_miniprogram/ yousenwebview/` — 下游必须切到 `learning_report_read_model.get_assessment_evidence()`.
- [ ] Add request schema fields without breaking existing diagnostic clients.
- [ ] Add deferred feedback payload snapshot test.
- [ ] Add submit idempotency test with learner event dedupe.
- [ ] Add per-item `learning_evidence` writeback.
- [ ] Add simple result report read model.
- [ ] Add wrong-item -> mistake-book projection.
- [ ] Add `yousenwebview` run/result view-model tests.
- [ ] Run WeChat DevTools manual gate.

Implementation must stop after the first failed checkbox that affects authority or data durability. Do not compensate with UI copy.

---

## 18. Relevant Code Entrypoints

Current known entrypoints:

| Path | Role |
| --- | --- |
| `deeptutor/services/assessment/blueprint.py` | existing `AssessmentBlueprint` |
| `deeptutor/services/assessment/blueprint_service.py` | existing session/form assembly |
| `deeptutor/services/assessment/coverage.py` | coverage gate |
| `deeptutor/services/assessment/teaching_policy.py` | assessment seed to teaching policy |
| `deeptutor/services/member_console/service.py` | current create/submit/profile wiring |
| `deeptutor/api/routers/mobile.py` | mobile assessment routes |
| `deeptutor/services/learner_state/learning_report_read_model.py` | learning report read projection |
| `deeptutor/services/learner_state/mistake_book.py` | cloud mistake-book projection |
| `deeptutor/services/construction_grading/*` | MCQ/case grading |
| `deeptutor/agents/question/agents/submission_grader_agent.py` | detailed answer explanation |
| `yousenwebview/packageDeeptutor/pages/assessment/*` | primary mini-program assessment surface |
| `wx_miniprogram/pages/assessment/*` | shadow/parity surface |

---

## 19. Success Criteria

P0 is successful when a learner can:

1. Choose 防水工程专题测评.
2. Complete a server-assembled paper without seeing answers.
3. Submit and immediately see score, wrong items and simple explanations.
4. Click one wrong item and get a detailed tutor-quality explanation.
5. Return to learning report and see the assessment reflected as concrete evidence.
6. Receive a next training action that is traceable to the assessment evidence.

Engineering can prove:

1. No second题库 authority.
2. No second learner-state authority.
3. No assessment-specific chat WebSocket.
4. No client-side correctness/mastery inference.
5. All answer keys remain server-side until submit.
6. Each writeback has dedupe and attempt refs.

PM success metric: P0A pilot cohort 在防水专题测评后 7 天 retention / NPS / mistake-book engagement 有 baseline 测量。
