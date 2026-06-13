# 评分知识结构化复利链 — 改造计划(execution plan)

> **不另起主线**。挂靠 `KNOWQL_BUILDOUT_BLUEPRINT.md`(→ §4.6 `2026-06-09-luban-nexus-like-scoring-artifact-engine-execution-plan.md`)+ master grading-to-brain plan §0.C。
> 循证来源:`grading_to_brain_north_star_and_external_evidence.md`(两轮 deep-research)。
> **三原则贯穿**:thin wrappers / first principles / less is more。**核心发现:四环全已有真实现且多数已用对模式,改造 = 校准 + 度量 + 加证据门槛,不是建系统。**
> Status:`Proposed`。改 protected 文件须按 `contracts/index.yaml` 登记 domain 测试;任何生产判分/写入改动需 owner 单独授权。
> **诚实定标(eval-design + 红队 + Codex 三轮对抗后,放最前)**:*我们证明的是"一个 prompt 在硬枚举题上、对一个**等权切片覆盖率**模型,比另一个 prompt 更贴近其作者的判断";尚未证明(a)考试是否等权给分、(b)官方 key 完整无歧义、(c)判分驱动留存、(d)原语适用于计算/散文/开放世界、(e)cite 真被验证。这五条才是真实风险。* 因此 **Gate −1(§0.4 验 key authority)→ Gate 0(§0.5 真实外部验证)是动任何环、接任何生产之前的双前置门**。

## 0. 北极星(本计划交付的链)

`评分知识结构化 → 采分点更准 → 错因更稳 → 学情更可信 → 建议更具体 → 用户"它真的懂我" → 留存付费 → 专用教育知识资产复利`。每环只做**能用数字证明优于现状**的薄改造。
**指标拆分(红队 S2)**:`calibration MAE` 是**环 0 的工程指标,不是产品 KPI**;产品代理指标 = **判分公平争议率**(grade 处一键"这判分不公平" + 可选理由)。两者可能背离——优化 MAE 若让判分变成"踩字 gotcha"反而降信任。北极星最后一环(更准判分→留存)必须独立装仪表,不能用 MAE 冒充业务 KPI。

## 0.4 Gate −1 — key-validity + scoring-policy(**比 Gate 0 更前,Codex 第三轮**)

**Codex 决定性发现:没有这一步,Gate 0 只是在错误 authority 上算统计量。** 现状 `candidate_coverage_score = 命中点数/总点数`(`per_question_grading_judge.py:110`)是一个**没被验证的等权评分模型**——而蓝图明令逐点分 must-not-mint。所谓低 MAE 是"等权切片覆盖率"误差,**不是"考试给分"误差**。先验证 authority 本身:
- 选 **20-30 道真实高频题**,每题 **3-5 名专家**独立判:① 官方 key 是否完整(漏不漏合理等价答案)② 每个原子点是否可独立判 ③ 合理近义/替代表达(产出 `accepted_variants`)④ 是否需要**非等权权重** ⑤ 哪些点必须配对 ⑥ 哪些题型**不适合 checklist**。
- **产物 = 可执行的 `accepted_variants / key_defect / weight_policy / human_review_route`**(不是学生答案 gold)。
- **key 缺陷裁决协议**:专家 gold 与官方 key 冲突时谁赢必须先定义,否则 atomic checklist 会**稳定地误判合理等价答案**。

## 0.5 Gate 0 — 题型普查 + 真实外部验证(Gate −1 通过后)

**单一最高杠杆动作,不是任何一个环**(eval-design "先评设计再花钱" + 红队一致结论):
- **统计功效诚实(Codex)**:50-100 份按 6 题型分层 → 每类 ~10 份,近义/计算/开放世界更少,κ/α 置信区间宽到无法决策;且学生答案按**题/班型/讲义/最近训练/水平强聚类,不是独立样本**。Gate 0 **只能筛掉明显坏的,不能认证好的**;要认证须按 cluster 扩样本 + **3 名判官 + 第三裁决 + rubric training + 判官严厉度/题目难度分离**。

1. **题型普查**:对真实判分流量统计占比——可枚举官方 key 案例 / 散文 key / 计算 / 开放世界无 key / 列举 / 近义容忍。**这个占比决定环 0 的"已证明"原语到底覆盖多少真实流量。**
2. **外部验证小研究**:拉 **50-100 份真实学生答案**(非作者手写 fixture)覆盖真实题型分布;**2 名独立合格人工(注册建造师/教研,非 fixture 作者)盲判** → 一次拿到真 gold + **人-人 α 上限**;arm B 对它跑,**按题型分层**出 calibration。
3. **判定**:B 在真实答案 + 独立 gold + 分题型下若仍稳→**才**有资格往下建环;若在计算/散文/开放世界塌(红队强预测)→省下整个下游工程。
4. **成本**:~100-200 个专家判断,比环 1 全量金标(§2.5-C 的 ~1.7 万)**便宜两个量级**——这是计划当前跳过的承重实验,必须先做。

## 1. 现状真相(改造前必读 — 系统比想象走得远)

| 环 | 现有 fat skill | 已经对的(别动) | 状态 |
|---|---|---|---|
| 0 采分点判分 | `per_question_grading_object` + `build_grading_contract` judge | 官方答案原子切片 + span_hash + 命中要 cite + 摁死误给;**live 五臂 A/B 已证赢 RAG**(MAE 0.035 vs 0.18) | 已证明,只补指标 |
| 1 错因标签 | `error_codes.py`(E01-12/M01-10 + 6 ability_dim)+ `learning_synthesis` | MECE-ish 结构 + contract-guard + authority 链 | 结构对,缺稳定性度量 |
| 2 学情画像 | `mastery_estimator.estimate_mastery` | **已有 Beta-Bernoulli 后验** `(correct+1)/(sample+2)` × 难度 × recency + L0/L1/L2 证据阶梯 | 估计器对,缺校准 |
| 3 学习建议 | `mastery_estimator.DECAY_PROFILES` + `next_best_action` | **已有间隔重复**:per-dim half-life(10-28天)+ 扩张式 revalidation_schedule(3,7,14,30) | 调度对,缺数据拟合 + 有效性评测 |
| 4 数据飞轮 | `per_question_grading_object`(判断即数据) | 判断已沉淀为 provider-agnostic 数据(原子点 + span_hash + provenance) | 资产对,缺 model-swap 成本度量 + 飞轮闭合 |

## 2. 逐环薄改造(现有 skill → 薄改造 → 验收门槛 → 证据来源 → 测试)

### 环 0 — 采分点判分(**仅在可枚举官方 key 切片上**经 demo 验证,待 Gate 0 真实验证)
- **范围收口(红队 S1)**:环 0 的"赢 RAG"**只对可枚举官方 key 案例题成立**;计算/散文/开放世界/列举/近义题**不在已证明范围**,见 §2.5-A 路由矩阵。**二元 MET/UNMET 纪律不覆盖计算题**(计算走代码已有的 `verification_mode=deterministic_recalculation_required` 过程+结果分项,不是二元)。
- **薄改造**:① 可枚举题采分点保持**二元 MET/UNMET**,任何点需 >2 级→拆多个二元点;② compile 期加**去相关过滤**(RRD)删/降权冗余高相关采分点;③ 聚合**不用过保守 Pareto**;④ **散文 key 质量门**:`split_sub_questions` 对无编号散文段会塌成 1 个巨点,compile 期须检测并要么细分要么标"key 不可枚举→低 κ 预警/路由人审"。
- **门槛**:每采分点 vs 专家 Cohen's **κ≥0.6**;采分点对间相关受控(去相关后逐点 κ 不降);误给率维持个位数。
- **证据**:外部循证 §2 F0/F1/F2/F4(强,对抗验证)。
- **测试**:`per_question_grading_object` / judge 是 protected → 新 κ 测 + 去相关测登记进 domain。

### 环 1 — 错因标签稳定性(强外部证据,验证 harness 加件)
- **薄改造(不建第二套标注系统)**:
  1. **每标签挂稳定性/置信字段**,在 `learner_memory_events → learner_state` 边界:**单次错因标签须达最小重复观测阈值**才动 mastery(E0:仅 ~40% bug 一致)。
  2. **逐错因类别×题型人工金标小集** + 每类别可靠性数;**仅过线类别满权重**进 learner_state,稀有/未验证**降权流入**(E1)。
  3. **错因标注器包可靠性监测**:κ_H-M(对金标)+ ρ_M-M(多次/多 prompt)+ 漂移信号(标签分布散度),observability 仪表非新模型(E2)。
  4. **taxonomy 诊断性审计**:每错因叶检查题库是否有题能与兄弟错因区分,非诊断簇标覆盖缺口,接现有 canonical taxonomy(E3)。
- **门槛**:Krippendorff α **逐类别**分档(<0.667 弃 / 0.667-0.8 暂用 / ≥0.8 满权重);**⚠️ 不硬编单一全局 κ 门**(E2 明确否决);每错因叶诊断性(等价类大小)。
- **证据**:外部循证 §2b E0-E3(E0/E1/E3 强,E2 medium)。
- **测试**:改 `learning_synthesis` / `error_codes` 是 protected → 稳定性字段测 + 降权测 + 金标可靠性脚本登记进 domain。

### 环 2 — 学情画像校准(第一性原理 + 现有代码,非外部对抗验证)
- **薄改造**:把 `mastery_estimator` 的 Beta-Bernoulli 后验 + L0/L1/L2 启发置信(0.45/0.72/0.9)**对真实复测结果校准**——不是重建成 DKT,是给现有后验配一条 calibration 曲线。
- **门槛**:画像置信的 **calibration**(ECE / Brier,对复测 outcome);证据充分性门槛(后验区间宽于阈值→标 low-confidence 不下结论)。
- **证据**:**第一性原理 + 现有代码**(外部 KT/OLM 循证两轮限流未取得,标注诚实)。校准一个已存在的后验是标准 ML,不需外部投票批准。
- **测试**:`mastery_estimator` 是 protected → calibration 度量测登记进 domain。

### 环 3 — 学习建议拟合 + 有效性评测(第一性原理 + 现有代码)
- **薄改造**:① 用积累的复测数据**拟合/验证** `DECAY_PROFILES` 的 half-life(现为硬编,可向 FSRS 式自适应靠);② mastery 进阶阈值从数据定;③ **建议有效性评测**:复测提升 A/B(**必须带对照臂**,别把自然进步算成建议功劳)。
- **门槛**:建议臂 vs 对照臂的复测提升(统计显著);掌握度阈值的命中/误报。
- **证据**:**第一性原理 + 现有代码**(FSRS 是公开标准;外部循证两轮限流未取得,标注诚实)。
- **测试**:改 `next_best_action` / `mastery_estimator` → 有效性评测 harness 登记进 domain。

### 环 4 — 数据飞轮 + 模型替换成本(第一性原理 + 现有代码)
- **薄改造**:① 度量 **model-swap 成本**——换 provider 重判同一批,采分点 verdict 一致性(判断沉淀为数据则一致性高=替换成本低);② 闭合飞轮——判断 verdict + 错因 → learning evidence → 反哺下次编译的弱点优先。**复用现有数据,不建新平台**。
- **门槛**:跨 provider 重判的 verdict 一致性(κ);飞轮一圈的弱点覆盖增量。
- **证据**:**第一性原理 + 现有代码**(判断即数据已落地;外部护城河实证两轮限流未取得,标注诚实)。

## 2.5 压力测试硬化(eval-design + 红队,对结果负责)

### A. 场景覆盖路由矩阵(红队 S1 — 原语不是一把梭)
| 题型 | 代码现状 | 适用原语 | 环 0 是否已验证 |
|---|---|---|---|
| 可枚举官方 key 案例 | `split_sub_questions` 多段 | 二元 MET/UNMET + cite | **是(demo,待 Gate 0)** |
| 散文 key(无编号) | 塌成 1 巨点 | 需细分或路由人审(质量门) | 否 |
| 计算题 | `_compile_calculation` 重算模式 | **过程分项 + 结果分**(非二元) | 否(代码已分流) |
| 列举"列 5 项" | 枚举尾切分 | 二元/项 + 非保守聚合 | 部分 |
| 近义/踩字 | `required_terms` 在旧 `rubric_grader_v1`,新对象未收口 | `accepted_variants` 容忍(见 D) | **否(权威分裂)** |
| 开放世界无 key | `not_in_bank_open_world` 独立路径 | RAG-grounded 开放裁决(非 checklist) | 否(计划漏整环) |
> **行动**:Gate 0 普查出各题型占比;环 0"已证明"标签**只贴可枚举 key 切片**;其余题型显式路由到对应原语,不假装一把梭。

### B. 逐环门的 confound 修正(否则假绿)
- **环 1 金标必须人工盲判 + 独立**(红队 S4):gold 由**不看模型标签**的合格人工出,且**非 fixture 作者**;算**人-机 α 与人-人 α**;某类别**人-人 α<0.667 = 谁都判不准**→直接踢出 mastery 环(只显示不动画像)。门是对的,**标注者身份是未言明的承重假设**。
- **环 2 复测必须分层随机**(红队 S3):只复测判弱点 = 选择偏倚(回归均值伪装成学习 + 看不到高掌握尾的过自信)。**跨所有掌握档分层随机复测**取无偏校准片;若必须集中复测弱点→**逆概率加权(IPW)**后再算 ECE/Brier,弱点-only ECE 只当下界。无无偏样本前**不许声称"已校准"**。
- **环 3 建议有效性是准实验**(红队 S6):不能伦理地撤建议做对照;复测提升被动机/选择混淆。用**错位上线**或**within-user 不同弱点对照**,不是简单 A/B。
- **环 4 改名**(红队 S7):采分点从官方 key 固定不变→re-judge 不复利。**真正复利的只有三样**:① **accepted_variants 增长**(每条"该判 MET"的争议消解 → 丰富变体库 → 下次更准,**这才是唯一真飞轮**)② **题库诊断性**(累积判分→哪些题能区分错因→退低诊断题/出好题)③ **干扰项挖掘**(UNMET span 聚成"5 种典型错法"→喂错因+建议)。model-swap 一致性低 = 你的"飞轮"其实是 vendor lock-in。

### C. 成本诚实(红队 S5 — 别把最贵项标成"薄")
环 1 全量金标 = 23 错因 × ~5 题型 × ~50-100 双标项 × ≥2 合格判官 ≈ **1.7 万+ 专家判断 = 多周多人五位数 RMB**,**不是薄改动**。**只金标会动决策的 3-5 个高频错因类别**,其余**仅显示不动画像**;稀有 cell(稀有类别×稀有题型)真实流量永远凑不出稳定 α→接受、走显示-only。按需触发(模型低置信或用户争议时才花一个人工标)。

### D. 冷启动/稀疏政策(红队 S6 — 突击者 ≠ 留存学习者)
真实用户考前做 10-50 题:**FSRS 拟合不了 per-user**(同题几乎零重复),**per-category α 是 population 统计**(OK),但**mastery 后验 n=2-3 时基本是先验**。
- **half-life/阈值只做 population 级拟合**,个性化只动"练哪题"不动遗忘曲线参数。
- **L0/L1/L2 当冷启动护栏真用起来**:n<阈值时画像必须**说"低置信,基于 N=2"**而非渲染精确 mastery 条。
- **突击者建议由"官方 key 覆盖缺口"驱动**(还没证明什么),不是遗忘模型——没学过的谈不上遗忘。**FSRS 对突击 cohort 整体 defer**,保留现有 Leitner 式 `DECAY_PROFILES`。

### E. 风险寄存器(severity)
- **SEV-1**:环 0 只在枚举切片证明(S1)/ 判分→留存桥未验证、MAE≠公平(S2)。
- **SEV-2**:环 2 复测选择偏倚(S3)/ 环 1 gold 循环自标(S4)/ 金标成本炸弹(S5)。
- **SEV-3**:冷启动稀疏击穿方法(S6)/ 环 4 "飞轮"实为日志(S7)。

## 2.6 Codex 第三轮对抗加固(三方都漏的第三阶盲点)
- **SEV-1 等权 MAE 真相**:demo 的低 MAE 是对"等权切片覆盖率"算的,**不是考试给分**;`candidate_coverage_score` 等权 mint 了逐点分(违背蓝图 must-not-mint 自述)。Gate −1 的 `weight_policy` 必须先验证考试是否等权给分,否则"赢 RAG"是赢错指标。
- **SEV-1 Gate 0 是假安全阀**:样本聚类非独立 + 分层后无功效 + 2 判官只暴露分歧 → 见 §0.5 诚实化。
- **SEV-1 key 错/漏/歧义无协议**:见 §0.4 key 缺陷裁决协议。
- **SEV-2 cite 没被验证**:`validate_grading_contract`(`per_question_grading_object.py:658`)只验采分点+教材引证权威,**不验学生答案 span 是否真存在/真支持 hit**。**薄改造:加学生 span 存在性+支持性校验**,否则 LLM 系统性误引用穿透(近义/反述/否定/计算题尤甚)。
- **SEV-2 蓝图↔主计划上线矛盾(执行歧义,最危险)**:蓝图 §8 写"解锁 production `_grade_one_case_v1` 接线/已有充分实证",主计划说 Gate 0 是唯一前置门。**本计划裁定:Gate −1 + Gate 0 未过之前,蓝图 §8 的"production 接线解锁"不成立**——那条只解锁"候选可做 Gate 验证",不解锁生产判分写入。需在蓝图 §8 补一行指回本裁定(待协调并行窗口)。
- **SEV-2 环 2/3 数据计划顺序产不出**:Gate 0 只产一次判分 gold,**产不出 longitudinal 复测/建议曝光/遗忘间隔**;"上线产生数据"无随机化=偏置日志。**环 2/3 启动前必须先定随机化+采样设计**(分层随机复测 + 建议错位上线),否则数据先天有偏。
- **SEV-2 mastery 校准压扁变量(环 2 真依赖)**:`estimate_mastery` 把作答二值化(`score_ratio>=1.0` 才 correct),70% 与 0% 覆盖都算 incorrect → 校准的是"满分率"不是掌握度。**环 2 硬依赖:先把点级覆盖证据接进 mastery,再谈 calibration**(否则校准错变量)。

## 3. 实施次序(Gate −1 → Gate 0 前置,最低风险先)
-1. **Gate −1 key-validity + scoring-policy(§0.4,20-30 题 × 3-5 专家,产 accepted_variants/weight_policy/key_defect 协议)** → 没有它后面全在错 authority 上算 → 通过才做 Gate 0。
0. **Gate 0 题型普查 + 真实外部验证(§0.5,Gate −1 后,3 判官 + 第三裁决)** → 通过才往下。
1. **环 0:范围收口到枚举 key 切片 + 计算/开放世界路由 + 散文质量门 + 学生 cite span 验证(2.6)**→
2. **环 1:默认显示-only,仅 3-5 个人工盲判金标认证的高频错因类别可动 mastery**(S4/S5)→
3. **环 2:先把点级覆盖接进 mastery(2.6 硬依赖)+ 第一天内建分层随机复测**(S3),否则不声称校准 →
4. **环 3:先定随机化/采样设计(2.6)+ 突击 cohort 用覆盖缺口驱动、保留 Leitner;FSRS defer**(S6)→
5. **环 4:砍"飞轮"措辞,只留 accepted_variants 增长 + 诊断性审计 + 干扰项挖掘**(S7)。
> **生产判分接线(`_grade_one_case_v1`)在 Gate −1 + Gate 0 双过之前一律锁死**(裁定蓝图 §8,2.6)。环 2-4 依赖真实复测数据,但数据必须随机化产生而非偏置日志。

## 4. 我们明确不建什么(减法纪律 = less is more + §5.7 单一权威)
- 不建第二套错因 taxonomy 引擎 / 第二套标注系统(环 1 全是现有标注器的验证加件)。
- 不建第二套 learner memory / 不把环 2 重写成 DKT(校准现有 Beta-Bernoulli 即可)。
- 不建新间隔重复调度器(拟合现有 `DECAY_PROFILES`)。
- 不建数据飞轮新平台(复用现有判断数据 + Grading-to-Brain loop)。
- 不升采分点为序数;不硬编单一全局错因 κ 门。
- 任何生产判分/写入改动需 owner 单独授权;quality_claim 维持 false 直到 owner 裁定。

## 5. 评测纪律(eval-design)
- **金标必须人工独立裁决**,不能用 LLM 自标当金标(否则循环验证假绿)。
- **建议有效性必须带对照臂**,隔离自然进步。
- **错因可靠性逐类别**算,不被一个聚合数掩盖稀有类别不可靠(E2 教训)。
- 小样本/单次跑只能给方向,定论需重复 trial + 独立 gold(沿用环 0 A/B 的诚实方差边界)。
