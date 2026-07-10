# 07 · 判分分发器 / 采分点 resolver / 组合层 orchestrator

> 执行账本。设计见 [v1.3 计划](../2026-07-08-luban-case-question-light-practice-capability-plan.md) §1.5B/§3。分支 `feat/luban-case-light-practice-p-1`。把孤立引擎拼成"可判一道小问"的系统。

## 判分分发器(commit `bd6fa42db`)
`case_grading_dispatch.py`:题型→引擎路由(calc_dag/set_membership/ordering/conjunction/cpm),归一 `DispatchResult`,`official_score_allowed` 恒 False(**只路由,不造第二权威**)。

## §1.5B 六题型判分全覆盖
- 新字段 `common_wrong_expressions`/`condition_tags` register-before-use(扩 `LubanCaseScoringPoint` 默认空 + T2 PINNED 内省对账,commit `0f2174403`)。
- AI 错答挑错 `case_flaw_spotting.py`(复用 `diagnose_photo` 确定性算漏点)。
- **6 种题型都有确定性判分路径**:采分点点选→生成器+coverage / 题干关键词点选→set_membership / 漏点补全→diagnose_photo / 流程拖拽→ordering / AI 错答挑错→flaw_spotting / 判断改正→合取门。

## 采分点源 resolver(commit `58ee4c7ba`,§3 新造)
`case_scoring_point_resolver.py`:白名单门 + 教研 consensus 的 review.json(sub_no/原子/非平点)+ 编译库采分点原文 → 投影 `LubanCaseScoringPoint`。**纯只读投影,不改生产模块;fail-closed 到教研 verdict**(编译库缺 sub_no = 欠切分,sub_no 是教研切分验收才产生的真值)。
- 切分质量闸 `07fa8c2b8`:过闸才进白名单,接进填充器。

## 组合层 orchestrator(把引擎拼成可判小问)
- composition on-ramp `derive_grading_kind` + spec-source 边界图(`e90af4010`);`practice_grading_kind` register-before-use tag(`adc095152`);policy→kind 可分发性探针(`b1fd63066`)。
- spec assembly for ORDERING+CONJUNCTION(composition 层 ②,`bf54a8c45`);教研填 `ordering_rank`+`conjunction_role`(`93ef9e2bd`)。
- **修 2 真判分 bug**:spec-assembly grouping 按 `(qid,sub_qid,group)` 作用域(`9b954df4f`,同 [06](./06-七判分引擎-Codex对抗核.md) 合取门②教训——组判分永远按题作用域)。
- `grade_ready_subquestion` orchestrator(derive→assemble→dispatch→aggregate,`4d8ac7193`)+ capstone e2e:resolver→orchestrator 合取端到端跑通 OPEN 路径(`36a4b8f26`)。

## 完整可组合后端链
`resolve_scoring_points(qid)`[白名单+教研门] → `generate_point_select_item`[生成+RTG1-8] → `rtg9_triage`[异源分流] → `dispatch_grade` / `grade_ready_subquestion`[7 引擎判分/组合]。
