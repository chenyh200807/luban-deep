# 案例题判分源迁移计划 — 旧 minted bank → per_question_grading_object(真单一权威)

> 来源:34-agent 只读专家 workflow(`wf_54ea63d9-b3a`,18 专家 + 3 对抗 completeness critic + 12 gap-fill + 1 架构师综合)。**全程只读,无生产改动。** 本文是迁移执行的单一权威;任何阶段落地前回读对应 Stage 的 gate。
> 触发本计划的决策:用户选 A(把生产 rubric 源从旧 `run_luban_rubric_compile` 迁到 `per_question_grading_object`,一个 compiler、一个 shape、canonical 真成运行时权威)。

## 0. 决定性结论(crux,已从源码核实)

**旧 bank 的逐点分是 minted(LLM 提议权重按比例缩放到重构官方总分),零官方权威。** `rubric_compiler.validate_rubric`(`rubric_compiler.py:66-67`)只校验 `sum==official_total`,**只证明拆分能重构总分,不证明拆分本身是官方拆分**。所以旧 bank 本身就是新契约定义下的**潜在 must-not-mint 违规**——但它是今天生产判分唯一能跑起来的承重地板,**要替换不是硬拔**。

- 新 compiler 拒绝 mint:`per_question_grading_object.py:563-564` 对任何 `score is not None` 的点报 blocker;schema `forbidden_properties` 含 `minted_per_point_score`;每个 ScoringPoint `score=None` + `score_authority=pending_calibration_not_official`。
- 生产 grader 依赖分值、**无 verdict 兜底**:`grade_with_rubric:64` 做 `float(p.get('score') or 0)` 求和;喂 null-score 点 → 每题判 0。
- 诚实判分底座**已存在但产的是 fraction 不是逐点分**:`candidate_coverage_score`(命中点/总点)+ `detect_over_credit`。
- **PGO 运行时是 greenfield**:`deeptutor/capabilities/`、`deeptutor/tutorbot/` 零 importer;旧 174-qid/1221-point bank(`status=release_candidate, content_hash gated`)是当前唯一 live 判分权威。

**单一权威正解**:迁移后生产判分 **`awarded = official_total × coverage`**(coverage = 命中点/总点,来自 verdict 计数),**永不求和 minted 逐点分**。唯一权威数 = official_total;逐点从不声称权威,只暴露可由 verdict 计数 + 那一个官方数复算的聚合。需要一个新的 verdict-coverage 判分函数消费 PGO 合约形(official_slice + sub_type,score=null),**绝不 `float(score or 0)`**。

## 1. 需 owner 拍板的 3 个决策

**决策 1 — 判分算术(verdict → 学生可见数)**
- A(团队推荐)**纯 coverage + partial**:`awarded = official_total × (credited/total)`,HIT=1、PARTIAL=partial_ratio、MISS=0。唯一权威=official_total,逐点不落权威,复用已建的 `candidate_coverage_score`,保住学生现有的部分分 UX。
- B 二元 coverage:PARTIAL 塌成 MISS,无部分分。最严,但会肉眼降分、去掉近边界高风险信号。
- C 仍 mint 逐点分求和。**直接否决**——正是要迁走的病。

**决策 2 — PGO 合约缺的 4 个 runtime 字段(policy/score/required_terms)怎么补**
- A(团队推荐)`sub_type→policy` 映射表 + `required_terms = anchor_verified 的 term_provenance` + `score 保持 null`(grader 改 coverage 算术,从不读 score)。残留风险:flaw_correction/exceptions 塌成 qualitative 可能放过术语严格点 → 由 SHADOW 实测 delta,非 blocker;用"有 anchor_verified required_terms 时推断 exact_required"缓解。
- B 另跑离线 LLM/教师校准产**官方**逐点 policy+score。最高保真,但是净新权威源、无 owner/时间表、重开 mint 问题。→ **post-migration 增强,本次 defer**。
- C 用 qid+slice-overlap join 旧 bank 的 policy/required_terms。否决——脆弱、悄悄重新耦合废弃 bank。

**决策 3 — 现在能否执行**
- 团队判定 **B**:概念正确 + 运行时 greenfield → **现在安全 BUILD + SHADOW**;但 **FLIP 必须 gate 在**:(a) Stage 0 五个生产缝隙 blocker 全闭 +(b) golden-set 回归证明 MAE-not-worse + over-credit-not-higher(对 `reference_ledger_label`,**不用** panel consensus)+(c) **隔离 25% 数据质量失败 cohort**(不进 flip set)。

**一句话推荐**:现在可建可影子(greenfield 零 live PGO 流量),但**先别 flip**,直到 Stage 0 五缝隙闭合 + golden 回归过 + 25% 脏数据隔离;单一权威成立的充要条件 = 生产按 `official_total × coverage` 判、永不求和 minted 逐点分。

## 2. 七阶段执行计划(每阶段带安全 gate)

**Stage 0 — 关闭 5 个生产缝隙 blocker(flip 前必须,可与 Stage 1 并行)**
- (a) **contract-guard 零保护**:`contracts/index.yaml:508` 的 `luban_grading_engine` 是顶层 key,guard 根本不读 → 改 `rubric_grader_v1.py`/`per_question_grading_object.py`/`learning_evidence.py` **当前触发零 contract guard**。要把它提进 `domains:` + protected_patterns + 登记测试。
- (b) **WS 脱敏 blocklist**:把 PGO 字段名(official_slice/atomic_official_slice/official_sub_answer_verbatim/official_analysis/term_provenance/flaw_span/correction_span/base_rule/exception_items)加进 `unified_ws.py _HIDDEN_PAYLOAD_KEYS` 和 `question_followup.py _PUBLIC_REDACTED_KEYS`——官方答案逐字文本绝不能到微信端。
- (c) **dedupe-key 漂移**:`build_learning_evidence_dedupe_key` 用了 raw score_awarded/max_score;flip 后重判会插幻影重复 learner_memory_events。换成 artifact_version/rubric_id 身份字段(且改法要保持同轮同答 idempotent,加版本前缀不重算旧 key)。
- (d) **TutorBot node_code 丢失**:`_build_v1_case_ctx`(loop.py)要把 `_prefetched_exact_question` 的 node_code 传进 runtime_metadata,否则 loop 路径判分写 node_code='',brain 丢概念归属。
- (e) **point_id 命名空间**:旧 bank `qid::SPn` vs PGO `sp_<hash>`,选一个 canonical,免得 `scoring_point_map_read_model` 跨 epoch 重复计同一逻辑点。
- gate:check_contract_guard 对这三文件真触发;脱敏单测断言所有 PGO 字段不出现在 public WS;dedupe-key 改动有 migration-version 测试;node_code 传播有测试;point_id 方案文档钉死。

**Stage 1 — 全量编译 + 数据质量隔离**
- 把 demo(`SELECTED=3`)扩到 canonical `FINAL_CLEANED_EXAM_V*.json`(**Documents 路径,不是 diverged 的 heuristic-jackson worktree**)的全部 **218 道 case_study**。每个跑 `validate_per_question_grading_object`。
- **隔离 25% 功能失败 cohort**(标 `compile_excluded` + 原因,不进 flip):`correct_answer` 是【解析】-only(分析当答案,~10)、2025 AI 占位答案(【选项分析】)、`不妥之处N` 阿拉伯数字未拆(3)、内联 `；N.` 分隔塌缩(如 EXAM_1A433000_P0009_01 20pt→1 点)、null official_total_score(4)。
- 风险:**结构 valid 不等于语义 valid**(分析文本被切成官方 slice;20pt 4 问编成 1 点)——flip 这些会回归真实判分却通过所有 validator。
- gate:included set 零 hard blocker;隔离名单逐条有原因;included qid 覆盖 vs live 174 对比暴露任何掉题。

> **多-AI 类型条件化编译候选(2026-06-14,接本 Stage "结构 valid≠语义 valid" 残留)**:确定性 Stage 1
> 把 91/179 已编译题塌成 ≤1 点(散文/顿号列表 fail-closed,正是上方风险行的"20pt→1 点")。多-AI 工厂
> (`artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/_drivers/`,见其 README)用**类型条件化
> 切分+授权**救回:mean 2.69→7.21、塌 91→4,**179/179 must-not-mint 零违反**(三 lane:81 consensus+10 确定性
> tie-break+88 Opus 仲裁;确定性逐字重验)。非循环验证:授权 precision/recall 1.0、切分 pilot must-not-mint 12/12+Opus 仲裁。
> **接法边界(诚实,避免越权改判分)**:(1) 它只增强**切分粒度**→喂 Stage 2 同一个 `official_total×coverage`
> 算术,**不改判分公式**;(2) 它授权的 **list_rule/penalty_rule 是独立算术决策**(阈值感知 vs 均权 coverage,
> 超出决策 1A 范围)。**owner 决策(2026-06-14):选 A——维持均权 coverage(决策 1A),阈值感知判分 defer**;先在
> golden set 度量"非线性阈值/penalty 被均权错判"是否材料级伤害(list_rule 74%/penalty 仅 2%,线性列举均权本就判对),
> 有证据再启用;启用须另一轮授权阈值曲线+算术改造+eval-design 重验证;(3) 仍 candidate/review-only,flip 仍受
> Stage 0/3/4 gate;(4) total_items 降级为 advisory(结构性 `structural_cap_list_items` 为权威)+ 51 题人审队列
> (顿号启发式上界,荷载符号串会过标→**已多-AI 对抗团队闭合**:51→33 拆/15 留/3 散文,过标 35%,Codex 逮 5 个便宜模型共识误判 Opus 全采纳;33 拆分已应用,点 1290→1384,must-not-mint 仍 179/179)。
> **隔离 cohort 复诊(接本 Stage 25% 隔离)**:读源数据真相,39 隔离题里 **25 是过标**(真答案被误排:真【参考答案】+尾部【选项分析】boilerplate 被 `'无选项' in answer` 误判占位、【解析】体即答案、仅缺 score)——多-AI 工厂救回 **21/25 干净(must-not-mint)**,覆盖 **179→200**;仅 **14 真占位**(无真答案不捏造,2018-2025 未公布年居多)。score_gap 4 题结构可编译但 `official_total_score` 缺,需 owner 补。产物:`phase5_factory/full_factory_candidate.json` + `quarantine_rescue/`。

**Stage 2 — 适配到可判分 runtime 形(单一权威正确)**
- 建确定性 `PGO 合约 → runtime-points` 适配器(决策 2A:sub_type→policy、required_terms=anchor_verified、score 留 null)。建 verdict-coverage 判分函数(决策 1A:`awarded = official_total × coverage`,`detect_over_credit` 当自洽 gate)。**绝不 `float(score or 0)`**;旧路径 score-sum 硬 gate 不动。
- gate:单测——null-score 点不会意外判 0(coverage 路径已验);policy 映射覆盖全部 5 个 sub_type;required_terms 绝不提拔 anchor_verified=False(伪源守卫);over-credit gate 在 score_pct>coverage+margin 触发。

**Stage 3 — SHADOW 老 vs 新(限 cohort,无 writeback)**
- 新 verdict-coverage 路径在 qa_/test_/operator_ cohort 与 live 旧路径并行影子跑,新 kill switch `LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED`(默认 false,**读之前先注册进 env_registry**)。影子结果 append-only 到 result_payload,`official_score_allowed=False`、`writeback_performed=False`,**绝不写 learner_state/brain**(foll runtime_shadow_adapter/m35_artifact_shadow 先例)。双判有 LLM 成本 → cohort 限定或离线 replay 跑。
- gate:无任何影子轮的 learner_memory_events 行;kill switch 已注册且证明能禁用;影子比 score + policy 分布 + qid 覆盖(不只 score)。

**Stage 4 — golden set 回归(单一权威 = reference_ledger_label)**
- 旧 bank vs 新 coverage 在 20-case `luban_case_grading_golden_v1.json` 按 (case_id,student_id,point_id) 比,锚 `reference_ledger_label`(**绝不用 consensus_verdict**,panel 抬 QWK ~0.15)。gate = `MAE_not_worse_than_legacy AND over_credit_not_higher_than_legacy`。若 point_id 变,**重生成** `luban_case_grading_golden_no_human_v1_5.json`(继承同 97 point_id,rekey 不重生会悄悄清空它的 escalation 队列)。两个 harness 登记进 `benchmark_phase1_registry.json` 让 CI 看见。
- gate:MAE(new)≤MAE(legacy) 且 over_credit(new)≤over_credit(legacy) 对 reference_ledger_label;每个 verdict flip 溯到 key 修正非 panel 重标;no_human harness 已重生且非空。

**Stage 5 — kill switch 后 flip(canary → broad)**
- 新 bank 建成**第二个文件** `case_rubric_scored_pgo.json`(自带 content_hash + canonical_pointer,**不覆盖** live 文件)。`_rubric_bank` 改 slot-aware(env `LUBAN_CASE_RUBRIC_BANK_SLOT=legacy|pgo`,默认 legacy)→ flip = 一次 env 改 + worker 重启,rollback = env 改回 + 重启(无文件操作)。`LUBAN_CASE_RUBRIC_V1_ENABLED=false` 仍是全 v1 紧急总闸。canary operator_/qa_ 先,再放量。**`lru_cache(maxsize=1)` 意味着新 slot 只在 worker 重启后生效**。
- gate:新 slot content_hash 对得上 canonical_pointer;**有 hash-mismatch 告警/指标**(今天 mismatch 是静默 fail-open 到 open-world!);canary 分布在 SHADOW 观测 delta 内;确认 worker 重启加载新 slot。

**Stage 6 — 废旧 + 切残余引用**
- flip 在 broad 稳定后:从 `publish_all_runtime_supply_bundles` TARGETS 移除/重指 `v_case_rubric_scored`;归档 `fix_luban_rubric_e0_contamination.py`(一次性修已合,commit aaf8a7cf9,留审计);**解决第二权威 manifest**:`canonical_knowledge_manifest.py` 同时注册了 `case_rubric_scored` 和 `case_rubric`(v_slice_case_rubric,18 records)为 answer_authority tier → 收成一个。更新 SKILL.md/data-authority.md/source-grounding.md/contracts/index.yaml authority 链指向新权威。重建 stale manifest(当前 verify_manifest 报 shard_hash_mismatch)。
- gate:verify_manifest 过;manifest 里恰好一个 answer_authority 采分点 shard;grep 无 runtime 路径仍加载废弃 slot;所有 skill/contract 文档指向单一新权威。

## 3. MUST NOT BREAK(迁移全程不可改的形)

- **GradingEvent shape**:`case_grading_completed` + scoring_points[](point_id/knowledge_point/policy_type/hit/score/max_score/mistake_type/evidence_span)+ awarded_score/max_score 总分。`render_case_rubric_feedback` 逐字读——迁移改的是 score/max_score 怎么**算**(coverage 非 minted sum),**形必须一模一样**。
- `official_score_allowed` 在每个 v1 event + PGO 对象/合约**恒 False**(唯一提拔=teacher/governed gate)。
- 旧 compiler 的 score-sum 硬 gate(`rubric_compiler.py:66-67`)在 legacy slot 还 live 时不可弱化(是 rollback 目标)。
- PGO 不-mint validator(`per_question_grading_object.py:563-564` + forbidden_property)永不删。
- 新判分函数**绝不** `float(score or 0)` 于 null-score PGO 点。
- learning-evidence 链字段形:scoring_specs[]、error_events[](必带 error_code,空了 synthesize_learning_truth 丢)、rubric block(`rubric_mode∈{grading_key,curated_rubric}` 否则 granularity 静默清空,`learning_state_projection.py:170`)。
- `_rubric_bank` content_hash verify-gate(`rubric_grader_v1.py:470`)对 active slot 恒权威;mismatch fail-safe 到 open-world,绝不绕过。
- `enforce_official_scoring_authority` 仍是 rubric_points 进评分求和的唯一入口(G2:textbook_cited 路由 supporting,永不评分)。
- `build_grading_contract` 继续 OMIT score。
- WS public 脱敏继续按 key 丢 scoring_points + (Stage 0 后)每个 PGO 答案字段。
- MCQ/photo_answer 防火墙:`deep_question.py:1997` 的 cg_type 守卫(case/batch 外 return None)+ batch type=='case' 过滤不可放宽;MCQ 用确定性 grade_mcq_submission,绝不走 rubric 路径。
- learner_memory_events 的 `ON CONFLICT(dedupe_key) DO NOTHING` 幂等保留;Stage 0c 的 dedupe-key 改动保持同轮同答幂等。

## 4. ROLLBACK

单次 env flip + worker 重启,无文件操作(因 Stage 5 把新 bank 做成独立 slot 文件 + slot-aware `_rubric_bank`):`LUBAN_CASE_RUBRIC_BANK_SLOT=legacy`(或 unset)+ 重启所有 worker → 旧 bank(content_hash 59ddec24…,174 qids/1221 points,全程不动)重新加载,verdict-coverage 路径不再被选。紧急全杀:`LUBAN_CASE_RUBRIC_V1_ENABLED=false` → 全案例判分回 V0/open-world。SHADOW 阶段 rollback:影子 kill switch 置 false,无 learner state 写入无需清理。Stage 0c 的 dedupe-key DB 改动用新索引列/版本前缀,绝不重算已存 key。

## 5. RESIDUAL RISKS(残留风险,执行时盯)

- **policy 不精确**(2A):flaw_correction/exceptions 塌 qualitative,术语严格点可能放过近义 → 只能 SHADOW/golden delta 测,设计期证不掉。
- **25% 脏数据 cohort**:隔离后边界仍难自动分(真短答高分 vs regex 塌缩);部分高价值题(20pt 内联 `；N.`)需源数据/regex 修才能进 flip set → 迁移权威 qid 覆盖一段时间 < legacy 174。
- **golden 统计功效低**:20 case/~39 live gold 点,一个 verdict flip 动 QWK ~0.04;MAE-not-worse 是方向 gate 非质量声明,小于噪声地板的真回归可能蒙混过。
- **coverage 判分去掉分数和的近边界高风险旗**(`grade_with_rubric:103` 只对小数和触发);选 1B 则全部部分分消失、学生分肉眼降;即便 1A,high_risk_review 分布变 → PCP 反馈语气变(UX 变非正确性 break,要沟通)。
- **Stage 5-6 第二权威窗口**:manifest 重建前 case_rubric_scored 和 case_rubric 都注册为 answer_authority tier;按 tier 迭代的消费者可能选错。manifest 当前 verify 失败(shard_hash_mismatch)→ release-gate publish 被阻直到重建。
- **lru_cache 热加载缺口**:re-sign/slot flip 对 running worker 不可见直到重启;部署忘重启则旧 slot 继续服务无告警。
- **content_hash mismatch 静默 fail-open**(`rubric_grader_v1.py:470`):新 slot hash 错 → 全题降级 open-world 只有 WARNING,无生产告警/指标(Stage 5 补)。
- `build_rubric_v1_shadow_result` + m35 artifact-shadow 是 `_rubric_bank`/artifact point_id 的第二/三消费者,当前防火(不在生产 turn 链)但 post-migration 谁接上没加 bank-flip 回归覆盖即潜在暴露。

## 6. 下一步(待 owner 定 3 决策后)

定了决策 1/2/3 后:**先做 Stage 0(关 5 blocker)+ Stage 1(全量编译 218 + 隔离 25%)+ Stage 2(适配器 + coverage 判分函数)**——全部可建可测、不碰 live 判分。**SHADOW(Stage 3)起算碰 cohort,FLIP(Stage 5)前必过 golden 回归。** 每阶段独立 PR,过 gate 再进下一阶段。
