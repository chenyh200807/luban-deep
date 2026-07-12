# Battle2 S2 判分输出减半 — 实施笔记（组D）

> 设计源：`2026-07-12-battle2-speed-cost-design-appendix.json` designs[mcq_grading]；
> 指挥官裁决全部照办（T2 cap 随 flag 联动 / T3 自证红测+blocking 四件硬事 / 合并前双 grep / T4 排最前 / 裁决字段红线 / 文案铁律）。
> 本文件待主控 docs PR 挂 `docs/plan/INDEX.md`（组D worktree 无权动 INDEX）。

## 落地清单（实施序 T4→T1→T2(+T5 flag)→T3）

| Task | 内容 | 文件 |
|---|---|---|
| T4 | deterministic 模板去套话：MCQ"采分点"段整段删除；"易错点"降级为题库行特异性投影（trap_type/pitfalls/common_mistakes；经 `construction_grading_result.evidence_refs` 通道），无则整段省略；记忆口诀保留 | `deeptutor/capabilities/deep_question.py`（`_objective_explanation` + 新 `_objective_specific_pitfalls`） |
| T1 | schema v2：`REQUIRED_SECTION_KEYS` 7→4（verdict/correct_answer/why_wrong/next_practice）；新增 `OPTIONAL_SECTION_KEYS`（knowledge_point/common_pitfall/mnemonic，缺失不追讨 repair、不模板兜底）；show_mnemonic chip 仅 mnemonic 段非空才挂 | `submission_grader_schema.py` / `progressive_disclosure.py` |
| T1 | compact prompt（同文件追加 key，flag off 旧 key 字节级不变）：4 必备段字数预算 + 逐项解析只展开错选项与正确项 + 条件段省略条款；authority/题面字母对齐/开放世界诚实措辞/【教材要点 Ln】约束逐字保留 | `submission_grader_agent.yaml`（`system_compact`/`grade_submission_compact`） |
| T2 | **指挥官改判版**：max_tokens cap 与 `DEEPTUTOR_MCQ_FEEDBACK_COMPACT` 同一 decider 联动——flag on = compact prompt + `min(get_max_tokens(), 1400+600×(items-1))`；flag off = 旧 prompt + 配置 4096，不传 override。repair 调用同 cap | `submission_grader_agent.py` |
| T3 | 差分质量门：24 例冻结语料（graded_context+grounding 冻结，消检索方差）+ 自证红测（B1 答案字母改错必红/B2 套话必红/B3 缺必备段必红/B4 compact 更长必红/R1 authority 突变必红）+ open_world 单臂基线模式 | `scripts/run_mcq_feedback_output_ab.py` / `eval/fixtures/mcq_feedback_ab/` / `tests/capabilities/test_deep_question_submission_feedback_invariants.py` |
| T5 | env 键登记（`contracts/env_registry.yaml`，kind=rollout, read=env_flag）；contracts/index.yaml 双镜像登记 2 个新 capability 域测试 | 见各文件 |

## 灰度 flag 生命周期（赎罪条款，owner 里程碑 PR 收账）

- 键：`DEEPTUTOR_MCQ_FEEDBACK_COMPACT`（default false）。唯一 decider 在
  `SubmissionGraderAgent.process`：同时切 prompt key 与 max_tokens cap。
- **deadline：生产开闸日 + 14 天**。Langfuse 复测（复用 F13 前后对比法，≥30 条
  scene=mcq_grading judged turns 才可宣称）达标口径：主生成 completion p50 ≤ 700 tok、
  `explanation_section_miss` 率无恶化、无质量投诉 → 删 flag + 删旧 prompt key，
  cap 转无条件、compact 转正。
- 上线序（T5）：T3 门全绿 → test2 QA cohort 真机 3 轮 live（automator true-entry，
  拉持久化 messages 核终态，禁流式抓包判质量）→ 生产 .env 开 flag + **rebuild**
  （prompt yaml 烘焙进镜像，首次上线必须 build；之后回滚 = flag off 秒级）→
  容器内 grep 对 SHA 防假绿。

## 差分门运行方式

```bash
# 0) 零成本自证（必须先跑）
python scripts/run_mcq_feedback_output_ab.py --self-red-test
# 1) open_world 抖动基线（单臂 legacy n=5；不稳则门口径改 --openworld-gate stability，禁事后放水）
python scripts/run_mcq_feedback_output_ab.py --openworld-baseline --n 5
# 2) billable 双臂（跑前过 eval-design 排雷单；同模型同温度，不借战役改温度）
python scripts/run_mcq_feedback_output_ab.py --run --n 3 --out artifacts/mcq_feedback_ab_report.json
```

blocking 四件硬事：正确字母在场（确定性 regex，非 LLM judge）/ 套话黑名单零命中 /
必备段非空 / p50≤700 且降幅≥45% + repair 率不回归；错选项针对性等脆断言降 advisory。
停手红线 R1：is_correct/score/correct_answer（含 items）process 前后深比较不一致 = 全局 FAIL 禁合并。

## Deviations（偏离账本，主控收录）

1. **T4 特异性投影通道**：设计原文 `row.get('trap_type')`；实测题库行顶层
   trap_type 会被 `normalize_question_followup_context` 白名单剥掉，真实存活通道是
   `construction_grading_result.evidence_refs`（mcq 判分内核已带 trap_type 证据）。
   投影同时认直接字段（生成题/测试语料）与 evidence_refs 通道；**未改 normalizer**
   （question_followup.py 不在 S2 files 白名单，保守方案）。
2. **B3 门口径**：设计写"post-fallback 必备段 100% 非空"——但模板兜底后恒非空，
   该断言不可证伪。实现改为 raw 输出 4 必备段齐（更严：等价于"不需 repair"），
   post-fallback 非空由 runtime 兜底链 + 截断单测另行钉死。
3. **batch_4 的 B1**：批量输出各题答案交错，段内 regex 等值判定不适用，改为
   per-item gold 字母全部在场（containment）；逐题严判留给真机 QA 终态人眼核。
4. **open_world 金标**：fixture 的 gold 由冻结 grounding 教材原文决定
   （gold_source=fixture_frozen_grounding）；billable 定级前须 owner 按教材原文人工核定。
5. **compact system prompt 输入侧 +54 tok**（1381 vs 1327，硬约束段逐字保留所致）；
   收益全在输出侧（输出=耗时第一因子），输入微增接受。
6. **实施笔记未挂 INDEX**：INDEX.md 不在组D允许文件集，随主控 docs PR 收口。
7. **分支存量红（非 S2 引入，HEAD 基线复核证实）**：
   `tests/core/test_deep_question_submission_grading.py::test_deep_question_blocks_unanswered_direct_answer_reveal`、
   `tests/core/test_deep_question_active_object.py`（2 例，turn_semantic_decision fail-fast 相关）——
   均在未改动的 HEAD 版 deep_question.py 下同样失败。

## token 实测（tiktoken cl100k_base，fixture 形状；live 前后对比以 T5 Langfuse 复测为准）

- T4 deterministic 真路径（sw01）：旧 ≈624 tok → 新 377 tok（−247 tok，−39.6%；删除块为静态文本，逐题恒定）。
- 输出形状（24 例合成样本）：legacy 7 段 p50=1016 tok vs compact 4+1 段 p50=237 tok（−76.7%）。
  合成 compact 比 live LLM 更瘦，门口径仍按 p50≤700 / 降幅≥45% 保守设定。
