# 多-AI 锚定对抗判分/编译工厂 — driver 集

> **candidate / review-only**。无生产判分写入、无 DB、无网络副作用。生产接线受
> `docs/plan/鲁班knowql/CASE_RUBRIC_SOURCE_MIGRATION_PLAN.md` 的 Stage gate + 人工/对抗 sign-off 门控。
> 北极星:`docs/plan/鲁班knowql/grading_to_brain_transformation_plan.md`。

## 为什么存在

确定性编译器(`scripts/run_luban_per_question_grading_object_full_compile.py`)对散文/顿号列表官方答案
**fail-closed 退成单点**(全量 91/179 塌成 ≤1 点,mean 2.69 点/题)——这是 must-not-drop 守卫的正确行为
(不假切撕裂术语),但意味着确定性编译天花板 ≈ 一半题。这套 driver 用**多-AI 团队**补两件确定性切分器
结构上做不到的事,且每步**非循环验证、must-not-mint 锚定**:

1. **规则授权(角色①)**:list_rule/penalty_rule/踩字纪律——确定性 coverage 抓不到 list 的非线性阈值。
2. **语义切分(角色②)**:把散文顿号列表切成原子采分点——救回塌缩题。

**first-principles 收敛**:采分点**类型**同时决定切分粒度和判分规则 → 角色①②合并为一个
**类型条件化编译** pass。

## 流水线(按 phase 跑)

| driver | 阶段 | 作用 | 验证结论 |
|---|---|---|---|
| `phase1_blind_graders.py` | 判分验证 | DeepSeek+Qwen 盲判 vs 131 人工 gold | 跨家族 consensus 97.5% vs 人类 |
| `phase3_rule_authoring_validation.py` | 授权验证(非循环) | 12 题 hold out 人工 list_rule,AI 重授权 | 列举型检测 **precision/recall 1.0**(零 over-mint) |
| `phase4_segmentation_pilot.py` | 切分 pilot | 12 散文题多-AI 切分 + 确定性守卫 | **must-not-mint 12/12**;分歧=粒度,非 mint |
| `phase5_full_factory_propose.py` | 全量 Stage 1 | DeepSeek+Qwen 对 179 题产类型+切分+规则 | must-not-mint 168/179;标 98 需仲裁 |
| `phase5_stage2_prep.py` | cost-aware 分流 | 81 consensus + 10 确定性 tie-break + 88 Opus | Opus 只烧分歧(省半) |
| (8× Opus 子代理) | 仲裁 | 按"类型决定粒度"裁定 canonical + 修 mint | 逮住汉字守卫漏的隐蔽 mint(纠官方 typo) |
| `phase5_assemble_and_verify.py` | 组装+最终核验 | 三 lane 合并,逐字重验 | **179/179 must-not-mint 零违反** |
| `phase6_spotcheck_and_human_review_queue.py` | 对抗抽查+人审队列 | 4 neither + total_items 对照 | total_items 16/120 不可靠→结构性 cap 权威;51 人审候选(启发式上界) |

## 全量候选结果(对比修前)

| 指标 | 确定性编译器单独 | + 多-AI 工厂 |
|---|---|---|
| must-not-mint 清洁 | — | **179/179** |
| mean 采分点/题 | 2.69 | **7.21** |
| 塌成 ≤1 点 | 91/179 | **4/179** |
| 总采分点 | 482 | **1290** |
| 判分规则 | 全空 | 类型条件化授权 |

输出:`../phase5_factory/full_factory_candidate.json` + `full_factory_summary.json` + `spotcheck_and_review_queue.json`。

## 仍待(生产前)

- candidate/review-only;生产受迁移计划 Stage + 人工 sign-off 门控。
- list_rule total_items 降级为 advisory;判分 cap 用结构性 `structural_cap_list_items`(派生,不授权)。
- **51 人审候选是顿号启发式上界**(荷载符号串如 G1、G2 本属一点会被过标);真子集需人工语义确认。
- 39 数据质量隔离题仍排除(AI 占位答案/解析当答案,需源数据修复)。
- list_rule/penalty 改判分算术(均权 coverage→阈值感知)是**独立决策**,不随本候选自动生效。

## 复跑

```bash
python3 phase5_full_factory_propose.py     # 增量(propose_by_case/ 已存的跳过)
python3 phase5_stage2_prep.py              # 分流出 opus_batches/
# 派 8 个 Opus 子代理读 opus_batches/batch_NN.json 写 opus_verdicts/verdict_NN.json
python3 phase5_assemble_and_verify.py      # 组装 + 最终 must-not-mint 核验
python3 phase6_spotcheck_and_human_review_queue.py
```

providers 经 `scripts/run_luban_rich_leaf_llm_deep_compile_runner.py:_openai_compat_provider`
(deepseek / dashscope);需对应 API key 环境变量。
