# type-diagnosis · ⑥ 采分点/诊断原型

- **何时选**:要把"一份答案逐采分点判读"翻译成学生看得懂的得分表达——直接对接"看穿背 vs 真懂"。
- **代表考点**:题干→采分点命中、学生答案 vs 标准答案对照、错因诊断。
- **展现形式**:答案 × 采分点诊断(沿判读轴:一份答案 × N 个采分点)。
- **语义色**(引用 style-guide):**hit 绿 / partial 琥珀 / miss 红**;命中 span 高亮绿,漏点 span 标红。
- **交互**:点采分点 drill-down"为什么没分" → 给纠正 + **Fix List(下一步训练)**。
- **祖师爷参照**:**行内批注/rubric 反馈线**——**Grammarly**(下划线 span→悬停/点开"为什么+怎么改"→采纳;AI Grader:按 rubric 出 doc/段落级反馈 + 行内批注 + **Fix List**)、Blackboard Bb Annotate(行内批改)。核心招:**划出原文 span → 点开 why + how-to-fix → rubric 分类拆解 → Fix List = 我们的下一步训练**。
- **schema body**:`diagnosis[]`(`scoring_point_id`(引用)/`status`(hit|partial|miss)/`matched_span`/`gap`/`student_comment`)+ `question` + `model_answer_skeleton` + `student_sample` + `diagnosis_summary`。**status 是已编译候选 verdict,前端不重判;renderer 不判分。**
- **验收点(原型专属)**:status∈{hit,partial,miss} 且 scoring_point_id 命中;candidate 不冒充签发;Fix List 接既有 training_intent/NextBestAction。
- **现状**:✅ 草稿 `artifacts/luban_case_family_assets/diagram_microlesson/D01_answer_point_diagnosis.schema_draft.json`(无 renderer)。动 renderer 前先硬化:template_type 分派 + steps/diagnosis 互斥 + student_safe 白名单。采分点须 candidate→签发后才进生产判读。
