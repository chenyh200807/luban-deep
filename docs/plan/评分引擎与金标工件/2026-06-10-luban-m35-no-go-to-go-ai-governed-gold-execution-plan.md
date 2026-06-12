# M35 NO-GO → GO：官方答案钥匙 + AI 治理金标执行计划

状态：Active（用户 2026-06-10 显式授权：判定层标注采用零人工 AI 专家团，走既有 `ai_governed_gold` 契约）
日期：2026-06-10
前置：`2026-06-09-luban-nexus-like-scoring-artifact-engine-execution-plan.md`（M35 引擎已合入 main `214e9a73`，诚实 NO-GO）

## 0. 裁决根因与本计划的杠杆

M35 NO-GO 的两个根因，对应两条治理级权威，均已在仓库内：

| 根因 | 权威来源 | 动作 |
|---|---|---|
| 答案钥匙无溯源（source_validity 0.71 < 0.95） | 题库 `FINAL_CLEANED_EXAM_V{2015..2025}.json`：官方答案 + 逐小题分值 + 显式【评分标准】，人类权威、机器可读 | R1 编译进工件 |
| 判定标注无权威（100 答全 `generated_self_label`） | 既有 `ai_governed_gold` 契约（`m35_ai_governed_gold.validate_ai_governed_gold_protocol`）：≥3 独立模型盲投 accept + 官方来源字段级引用 + adversarial_prosecutor 零未决异议 + ≥5 例 mutation test | R2 产出合规标注 |

**禁止新增第二个标注级别名**。`ai_governed_gold` 是唯一 AI 金标权威；R2 的产物必须逐行通过 `validate_ai_governed_gold_protocol`，并使全 fixture 统一为该级别（audit 链 `set(levels)=={"ai_governed_gold"}` → `POC_GO_ALLOWED`）。

## R1：官方答案钥匙编译（agent，1–2 天）

- 输入：题库 2023/2024/2025 案例题 chunks（`exercises`、分值、【评分标准】行、`structured_rules`）。
- 输出：fastapi case fixture（15q/150a 与 27subq/167a）的每道题获得 `scoring_points`（criterion/max_score/policy_type/required_terms/negative_evidence），`source_refs` 带 `source_type=exam_reference_answer`、`source_id=chunk_id`、`quote_hash`、`verified=true`。
- 硬约束：采分点文本必须可在官方解析原文定位（quote_hash 可复核）；总分=逐点分值合计（score-sum 门已生效）；不许 LLM 自创采分点——LLM 只做官方答案的结构化抽取，抽取结果走 `rubric_compiler.validate_rubric` 确定性校验。
- 顺带：给 golden 20 题中 Q18-1A434000 / Q20-1A413000 从官方来源补总分（compiler work order 闭环）。
- 验收：重建后 `source_validity ≥ 0.95`，`score_sum_ok` 全绿，`pytest tests/scripts/test_build_luban_m35_fastapi_case_fixture.py` + fixture contract 测试绿。

## R2：五模型 AI 专家团金标管线（agent，1–2 天）

- 模型池（按可用 key 取 ≥4）：GPT-5.5 / Opus 4.8 / Fable 5 / DeepSeek V4 Pro / Qwen3.7-Max；按 provider 多样性选 ≥3 家不同供应商。
- 流程（每份答案 × 每个采分点）：
  1. 盲标：各模型独立判 hit/partial/miss + evidence_span，互不可见，prompt 锚定 R1 工件的官方评分标准；
  2. 对账（确定性代码）：全票一致 → 候选金标；多数票 → 标 `majority` 待对抗复核；分裂 → 进仲裁；
  3. 对抗：`adversarial_prosecutor` 角色（与盲标不同模型）攻击候选金标，objection 未解决则该行不得入金标；
  4. 仲裁：分裂项由未参与盲标的模型携全部论证记录裁决，裁决理由落盘；
  5. mutation test：每题 ≥5 个扰动样本（近义替换/主体替换/泛化表达）验证标注稳定性。
- 产出：`student_answers.jsonl` 逐行带 `label_authority=ai_governed_gold`、`ai_governed_gold` 协议块（blind_model_votes/source_anchor/adversarial_review/mutation_test）、`gold_point_matches`、`point_label_provenance`、`gold_score`、`directionality_flag`、`label_scope`；模型间 Fleiss kappa 写入 manifest。
- 评测主包：27 子题/167 答（满足 audit 的 ≥20 题/≥100 答/bucket 最低覆盖）。
- 成本闸：单次全量标注 token 预算上限先估算后执行；live 调用必须显式 opt-in 环境变量。

## R3：零人工授权记录（替代原人类锚点）

- 用户 2026-06-10 授权：不设人工仲裁/抽检。
- 决策包必须如实记录：金标权威=多模型协议而非人类阅卷人；残余风险=模型共享盲点不可由协议自证；缓解=provider 多样性 + 对抗 + mutation + 官方评分标准锚定。
- 不变量不放松：`official_score_allowed=false`、无 DB/远端/published registry/canonical learner truth 写入；GO 仅指受控 cohort 默认。

## R4：cached_judge_replay A/B 对决历史失败线

- 用 R2 金标跑 `run_luban_m35_scoring_artifact_ab.py --tier cached_judge_replay`；
- 门槛：point_precision ≥0.90、point_recall ≥0.90、score_mae ≤1.0、击败 0.5267 点命中一致率 / 4.6091 MAE；
- judge 输出缓存落盘（provider/model/cache 溯源），CI 不打 live。

## R5：MCQ 官方答案快线（可与 R1 并行）

- `luban_m35_fastapi_mcq_20q_100a`（`generated_from_official_mcq_key`）直接跑质量评测——官方答案即治理权威，零争议，第一个无封顶质量数字。

## R6：决策包刷新与裁决翻转

- 重跑 label audit / AB / release gate / loop gate，重写 `2026-06-09-luban-m35-scoring-artifact-production-decision.md`；
- 允许的最高裁决：GO（受控 cohort、case grading only、kill switch 在位）；
- 不许翻：published registry、canonical learner truth、生产全量默认、远端部署——仍需单独授权。

## 停止条件

R2 模型间 kappa < 0.6 或 mutation 通过率 < 80% 时停止并上报——说明判定任务对当前模型池仍过难，强行金标会重演 0.5267。
