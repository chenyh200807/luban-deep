# 深母题资产 Schema v2（Deep Case-Family Asset Schema）

> Status: Proposed — **未登记 / UNREGISTERED**。实现前必须按 §11 Registration Ledger 逐项登记并过 `scripts/check_schema_registry.py`；在此之前不得落代码、不得被 runtime 消费。
> Asset STRUCTURE authority v2（与 `case-family-asset-production-plan` 生产流程 authority 分工）
> Date: 2026-06-16
> Parent authority: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)
> 增补对象: [2026-06-11-luban-mobile-case-family-asset-production-plan.md](2026-06-11-luban-mobile-case-family-asset-production-plan.md)

## 0. 这份文档是什么、不是什么

**是**：母题资产的**结构（schema）单一权威**。定义一个高质量母题资产必须编码哪几层、每层的字段、字段从哪来、什么算合格。

**不是**：
- 不是第二套生产流程权威。生产流程（pipeline、status 翻转、review checklist）仍以 `case-family-asset-production-plan.md` 为准；本文只定义"产出物长什么样"。
- 不是第二套判分 / 学情 authority。本 schema 的 L1–L6 是**教学 / 诊断 context 层**；判分真相仍是 published question grading artifact + `CaseGradingSkillKernel`，错因 canonical 轴仍是 `ERROR_CODE_REGISTRY`，长期学情仍是 `LearnerStateService`。见 §9 硬约束。
- 不是新 runtime。它编译进既有 `CompiledContextPack` / RichLeafArtifact，由既有 `/api/v1/ws` 与 read model 消费。

**一句话定位**：把"专家穿过题目表皮看到考点本质和出题人逻辑"的那种**穿透力**，编译成结构化、可生成、可诊断、可教学、可跨科目复用的资产。

## 0.1 命名收权与 register-before-use 自查（2026-06-16）

落 schema 前先做了 register-before-use 自查（grep 既有 contract/code 注册表），发现并修正 3 处命名/概念冲突，避免靠 drift 长出第二权威（AGENTS §5.7 / `contracts/schema_registry.yaml`）：

| 原名（撞） | 撞了什么 | 收权后 |
|---|---|---|
| `archetype`（母题对象） | ① 母题概念已叫 `case_family`（asset-plan）；② `archetype` 在 assessment 模块已指"学员人格画像" | 统一用 `case_family`；本文 L1–L7 是 `case_family` 对象的**深层结构字段**，附加在 asset-plan §3 基础字段之上（**同一对象，非第二套**） |
| `scoring_authority`（判分接口字段） | 判分域已有 `official_scoring_authority` 门语义 | 改为 `scoring_mode`（判分接口类型：case_rubric/mcq_key/essay_rubric） |
| `textbook_locator`（viewmodel 字段，见姊妹文档） | 已存在于 `citations/normalizer.py` | 改为 `syllabus_locator` |

**未登记声明**：本文新引入的所有 schema 标识符（`case_family` 深层字段、各 enum 受控词表、`syllabus_locator` / `days_since_first_use` / `mobile_p0a_daily_loop_completed`）**当前均未登记**，逐项见 §11。按 `schema_registry.yaml` 的 scope_rule，它们都属 cross_consumer / persisted / named_field_binding，**必须登记后才能被代码消费**；在此之前本文只是 Proposed 设计。文件名 slug 含 `archetype` 仅为描述性，canonical 对象名是 `case_family`（未改文件名以免破坏 INDEX / asset-plan 链接）。

## 1. 设计哲学：不变量 / 表皮分离

考试不重复原题，它**换皮**：换场景、换数字、换设问，考点不变。专家眼里 100 道题只是 8 个母题的变体。

> **母题资产 = 1 个不变量（invariant）× 1 个表皮生成器（surface generator）× 1 套认知脚手架（cognitive scaffold）。**

一旦显式分离不变量与表皮，四个目标同时解决：
- **变样式提问** = 沿表皮轴换皮（L4）。
- **看懂出题人逻辑** = 把不变量 + 出题人意图摊给学员看（L1 + L2）。
- **看懂题目 / 考点** = 多重表征按考点类型呈现（L3）。
- **跨科目复用** = "不变量/表皮分离"这个结构本身与科目无关（§4）。

**护城河不在母题数量，在每个母题结构的深度。** 一份深母题资产被**五个消费者共用**：出题（L4）、判分（L7）、诊断（L5）、讲解（L3）、复测（L6）。别人要抄，得同时复刻这五层的一致性，极难。

## 2. Authority 收权（复用 vs 增补）

| 能力 | 唯一 authority（复用，不复制） | 本 schema 的角色 |
|---|---|---|
| 逐题判分真相 | published question grading artifact + `CaseGradingSkillKernel` | L7 只**引用** `artifact_id::version + point_id`，不复制 rule |
| 错因 canonical 轴 | `deeptutor/contracts/error_codes.py` `ERROR_CODE_REGISTRY`（E01–E12 / M01–M10） | L5 误解模型**映射**到 error_code，不新建错因码 |
| 知识点身份 | canonical taxonomy（`FINAL_CLEANED_TAXONOMY2026.json`，L1–L6 节点） | L1/L3 用 `node_code` 引用，不另起知识树 |
| 教材原文溯源 | textbook verbatim lane（`textbook_knowledge_full`） | L2/L3 的教学内容必须可溯源到教材/规范原文 |
| 长期学情真相 | `LearnerStateService` / `learning_evidence` / `revalidation_queue` | L6 掌握判定**写进**既有账本，前端不自算 |
| 编译签发 | Living LLM Artifact Compiler S0–S7（`promote_to_release` 单点翻 True） | L1–L6 走同一签发 spine，默认 candidate/teaching-tier |
| runtime 消费口 | `CompiledContextPack` / RichLeafArtifact + `/api/v1/ws` | 本资产编译进 pack，不新增入口 |

**红线**：L1–L6 是 teaching/diagnosis context，**永不**作为 official score、canonical learner truth、或 rubric policy 的第二来源。判分永远回到 L7 引用的 signed artifact。

## 3.0 case_family Canonical 收口决议 v2.1（2026-06-16）

> 经 4 专家（判分 / 错因 / 跨科目 / 对抗）+ root-cause + 对抗审查综合。**本决议是 case_family schema 的收口单一权威**，supersede 下方 §3 单对象 yaml 与 asset-plan §3 的所有字段定义冲突。下方 §3 单对象 yaml 待"决议0 拆对象"确认后按本决议机械改写。

### 决议0（治本，核心）:拆两个共注册对象,不焊成 God Object

表层根因 = 无唯一 case_family 定义;**深层根因(对抗专家)= case_family 被迫装两个生命周期不同的东西**。铁证:单 `status` 扛不了两套晋级门——判分侧 `reviewed→candidate` 门 = shadow grading replay(外部权威 readiness),结构侧 `candidate→active` 门 = G-COV(内部内容完备);本文 §8 黄金样板自己 `coverage_assertion.covered=false`(结构没做完)而判分侧可能已 shadow 通过,**一个 status 字段表达不了这个状态**。强行并集 = God Object,每个消费点被迫加 filter/mapping 层(对抗专家 7 场景 4 崩)。

裁决:拆成两个**共注册**对象,用 `case_family_id` 关联(像 User / UserProfile):

| 对象 | 性质 | 生命周期 / 晋级门 | 承载字段 |
|---|---|---|---|
| `case_family_production` | **指针层**:只引用,不拥有 rule/content | 外部权威 readiness(publish / shadow replay)→ `status_production` | id/name/subject/taxonomy_ref/provenance/scoring 引用/question_bindings/mistake_tag 投影/training_tasks/task_scope/review |
| `case_family_structure` | **原创教学层** | S0–S7 编译签发(G-INV/G-COV)→ `status_structure` | L1–L6(invariant/examiner_intent/representations/surface_generator/misconceptions/mastery) |

- **单一权威**:每对象是其自身 concern 的唯一权威;判分→published artifact、错因→ERROR_CODE_REGISTRY、知识→canonical taxonomy、学情→LearnerStateService,**四个内容权威一个不动**。
- **thin wrappers fat skills**:production 是薄指针壳、structure 是厚原创内容,各自独立 status/登记/演化。
- **less is more(系统级)**:消除 God Object 在每个消费点被迫加的过滤/映射层——更少特例,不是更多对象。

### 决议1–13:逐缝 canonical 裁决

| 缝 | 裁决 | 唯一归属 | 一句理由 |
|---|---|---|---|
| 1 status 枚举 | 拆 `status_production` + `status_structure`;删 `p0a_` 前缀(已验无 caller);phase 若需→独立 `rollout_scope` | 各对象自己的 status | 两套晋级门不能塞一个字段;p0a 是项目代号非对象固有属性 |
| 2 知识点绑定 | 只留 `taxonomy_ref.node_codes`,**删** `knowledge_nodes[{node_code,title}]`;title 运行时 resolve | canonical taxonomy | title 是 taxonomy 复制品,taxonomy 一天多改必 drift |
| 3 source_refs | 统一 `provenance.source_refs[{type,ref_id,version,chunk_id,content_sha256}]`(超集) | production.provenance | 实为三形状;v2 超集含 asset-plan §Step1 散文已要求的 sha 钉扎 |
| 4 采分点 | case_family **只引用不拥有**;**删** rule 影子 `rule_type/evidence_requirement/max_score`;point status 由 artifact 派生 | published artifact(`GradingPoint`) | 复制 rule = 第二判分权威;裸 `max_score` 绕过 must-not-mint 门 |
| 5 错因 | 见决议15(四名收口) | error_code 轴 | — |
| 6 question_bindings vs variant_blueprints | **两层都留**(绑存量真题 vs 生成增量变体);只把共有的"题/变体→采分点"引用收成**一个字段**(必为 artifact point_ids 子集);**不加 adapter** | 各层独占语义字段;共享的只是引用约束 | 职责正交不能合并;合并的是引用(一名一形),不是表 |
| 7 知识点形状 | 同缝2,`taxonomy_ref.node_codes:[str]` | — | 不只双位置,是两种不兼容形状 |
| 8 干扰项诊断链 | **一条链** distractor→`[misconception_id]`(**list 非 1:1**)→`maps_error_code`;MCQ 轻练读 `misconception.maps_error_code + correction + syllabus_locator` | misconception(锚 error_code) | 一个干扰项可暴露多个误解;"短链"是读取深度,不是第二条链 |
| 9 单 status 两门 | 同决议0(拆对象) | — | God Object 铁证 |
| 10 source_refs 三形状 | 同缝3 | — | — |
| 11 owner vs pointer | production 持引用,绝不内嵌 owned 全量 | artifact | case_family 误把"引用"建模成"拥有" |
| 12 `taxonomy_ref.sha256` | 诚实标注 = **reviewer 人工核**,**不**登记为 CI 强制门(无 validator) | reviewer checklist | 不留"登记了但永不强制"的假门(scanner 是止血非闭包) |
| 13 `subject` 单值 vs §4 跨科目 | 澄清 §4 复用的是 **schema 形状非 case_family 实例**;一个 case_family 单科目 | 文案修正 | 防有人建 per-subject 继承/override = 第二权威 |

### 决议14:通用(universal)= 三权分立 + 受控词表(用户硬要求)

- **科目无关核心层(schema 结构固定,改 = 抽象泄漏)**:全 L0–L7 字段结构、`scoring_mode.kind` 判分接口、status 状态机、`surface_axes`、`representations[].purpose`、`coverage_assertion`、L4/L5/L6 引擎契约。
- **科目特定可扩展层(受控词表,登记 schema_registry,结构 `{core_values, subject_extensions:{subject_id:[...]}}`,合法值 = core ∪ subject_extensions[subject])**:`competency.primary`、`canonical_logic.structure_type`、`difficulty_knobs[].knob`、`representations[].kind`、`variant_blueprints[].question_form`、`provenance.source_refs[].type`。新科目 = 加一条 `subject_extensions` + 跑闸,**零结构改**。
- **错因轴跨科目** = 往 `ERROR_CODE_REGISTRY` **内部扩轴**(如法考 L01–L12),schema `maps_error_code` 一字不动;**禁止**资产私造科目错因码。
- **三权分立**:schema 定**结构** / registry 定**受控值** / canonical 文件(taxonomy/error/artifact)定**内容**。通用只发生在结构层 + 受控值层,从不触三个内容权威。
- **设计即通用,但只 populate F16 薄切片**(见决议16)。

### 决议15:错因"四名"收口(专家2 实证,文档原先漏了第四名)

运行时实证:`error_code` 与 `mistake_type` 在 `learning_evidence.py` **同一 hit 上并存**,是两个正交轴。

- `error_code`(E/M)= **唯一诊断轴**(为什么这类能力失分),权威 `ERROR_CODE_REGISTRY`。**不可删、不可竞争。**
- `mistake_type`(omitted/wrong_content…)= **正交的判分形态轴**(这点怎么没拿到分),已存在(`mistake_codes.py`),文档原先完全没提。**必须写明 `mistake_tag` 锚的是 `error_code` 轴、与 `mistake_type` 正交**——否则有人把 `omitted` 填进 `mistake_tag.error_code` → 落 `unknown_error` 污染学情。
- `mistake_tag` = **判分侧投影**(`(scoring_point_id, error_code)` 绑定行);`label`/`version` **引用** registry,不在每行复制 taxonomy_version。
- `misconception` = **诊断侧投影**(心智模型 + 纠正,必含**单一** `maps_error_code`);per-case_family 局部,**不建全局 registry**。
- 两投影锚**同一** error_code,消费出口不同(判分/复练 vs 诊断/出题),**不合并、不竞争、删任一轴都不行**。
- 修正:§11 引用的 `mistake_code_registry.yaml` **不存在**(实为 `mistake_codes.py`),改正。

### 决议16:Phasing(设计全做,build/登记只做 F16 薄切片 — less is more)

- **设计**:13 缝 + 通用机制本决议**全部裁决**(满足"全部都做")。
- **build/登记**:Phase 0 只登 F16 薄切片——`case_family_structure` 的 `invariant.essence/classic_traps/misconceptions(+maps_error_code)/1 representation/1 discriminator_variant` + `case_family_production` 的 MCQ 干扰项→misconception→error_code 短链(留存差异化命根)。`subject`/跨科目 `subject_extensions`/8 个 enum 全词表/`essay_rubric`/完整 surface_generator **全部推迟 Phase 2(留存证明后)**。在第一个母题验证留存前登记全套 = 违反 less-is-more + 把未裁决撕裂提前固化进 registry。

### 决议17:核实结果 + 剩余不确定性 + 行动(用户要求明确标注)

**已核实**:① `p0a_` 无代码 caller(改名安全);② F16 无 `case_family.yaml`(纯设计态,可自由定 + 第一个 yaml 落盘前立纪律);③ `check_schema_registry.py` 只扫代码不扫 yaml(真空确认)。

**剩余不确定性 + 验证/替代**:
1. **`scoring_mode` 层级(单题 vs 多题)**:单题母题 case 级 OK;多题母题需把 `grading_artifact_id` 下沉到 `question_bindings[]` 每条,case 级只留 `scoring_mode.kind`。F16 单题→先 case 级。**替代(更稳)**:一律下沉到 question_binding。**验证**:扩到多题母题时复核。
2. **[代码任务] `check_schema_registry.py` 扩能力**:扫 `artifacts/luban_case_family_assets/**/case_family*.yaml` 顶层字段 + 支持 `{core+subject_extensions}` 受控词表。否则只止血、非 runtime fail-closed 闭环。
3. **[代码债务,已在 main 流血,比文档更急]**:两份 `_ERROR_LABELS` 逐字副本(`learning_report_read_model.py:124`、`learning_brain_read_model.py:14`)→ 改读 `ERROR_CODE_REGISTRY`;`mistake_code_registry.yaml` 悬空引用 → 改引真实文件。
4. **`rule_type` 是否纯影子可删**:验证一条真实 `case_rubric_scored` record 是否有等价表达(大概率 = `required_terms + sub_type`);有→放心删,无→保留为 case 级**解释**字段(仍不判分)。

**register-before-use 铁律**:**先删重复 → 再取并集 → 再登记两对象**;绝不在删重复前登记(否则用 registry 给 drift 盖章)。

---

## 3. Schema（分层模型）

> 本节是 §3.0 决议落地后的 **canonical 两对象定义**（`case_family_production` + `case_family_structure`，用 `case_family_id` 关联）。asset-plan §3 不再重定义结构,只引用本节 + 保留生产流程。登记见 §11（两对象各自登记）。受控词表 enum 的"科目可扩展"见决议14。

```yaml
# ════════════════════════════════════════════════════════════════════
# 对象 1/2：case_family_production —— 指针层（只引用,不拥有 rule/content）
# 生命周期门：外部权威 readiness（artifact publish / shadow replay）
# ════════════════════════════════════════════════════════════════════
case_family_production:
  case_family_id: str                 # 关联键,如 F16；structure 用同一键关联
  name: str
  subject: str                        # 单科目；跨科目=换内容跑同一 schema,非同一实例跨科目（决议13）
  status_production: draft | reviewed | candidate | active | suspended
                                      # 门：reviewed→candidate = shadow grading replay（删 p0a_ 前缀,已验无 caller）
  rollout_scope: str                  # 可选,如 "p0a"；phase 在这里,不在 status（决议1）
  taxonomy_ref:                       # 唯一知识点绑定（删 knowledge_nodes,决议2）
    node_codes: [str]                 # title 运行时从 canonical taxonomy resolve,不 persist
    file: str
    sha256: str                       # reviewer 人工核,非 CI 强制门（无 validator,决议12）
  provenance:                         # source_refs 唯一归处,superset 形状（决议3）
    source_refs:
      - type: enum                    # 受控词表 core∪subject_extensions: official_question|textbook|standard|lecture|scoring_artifact
        ref_id: str
        version: str
        chunk_id: str
        content_sha256: str
  scoring_mode:                       # 只留判分接口类型；artifact 引用下沉 question_bindings（决议4/17#1 采纳更稳替代）
    kind: enum                        # case_rubric | mcq_key | essay_rubric（科目无关接口）
  question_bindings:                  # 绑「已存在真题」（消费：复测/证据）
    - question_id: str
      sub_question_ref: str
      grading_artifact_id: str        # 该题引用的 published artifact（自含版本）,不复制 rule
      scoring_point_refs: [str]       # 该 artifact 的 point_id；不拥有 max_score/rule_type/evidence_requirement（决议4）
      retest_role: enum               # primary | similar_retest | original_review_only
      binding_level: enum             # same_point | same_node | original_review（复测证据阶梯）
  mistake_tags:                       # error_code 的「采分点粒度判分侧投影」（不是新轴,决议15）
    - scoring_point_id: str
      error_code: enum                # ∈ ERROR_CODE_REGISTRY（E/M轴）；锚 error_code,与 mistake_type 正交,勿混
      source: enum                    # rubric_policy | teacher_final | model_candidate | user_selected
                                      # label/taxonomy_version 不在此复制,运行时引用 ERROR_CODE_REGISTRY
  training_tasks:
    - mode: enum                      # light | semi_write | real_exam | photo_preview
      task_id: str
      estimated_minutes: number
      task_scope:
        scope_type: enum              # full_question | scoring_point_subset | light_check | preview
        covered_scoring_point_ids: [str]
        excluded_scoring_point_policy: not_evaluated_no_miss
        evidence_weight: enum         # official | diagnostic | light_signal | none
  review:
    owner: str
    reviewer: str
    reviewed_at: str
    taxonomy_reverified: bool         # reviewer 在 status 翻转时核 sha（人工,决议12）
    rollback_policy: str

# ════════════════════════════════════════════════════════════════════
# 对象 2/2：case_family_structure —— 原创教学层（真相在自己身上）
# 生命周期门：S0–S7 编译签发（G-INV / G-COV）
# ════════════════════════════════════════════════════════════════════
case_family_structure:
  case_family_id: str                 # 关联键 = production 同一键
  status_structure: draft | reviewed | candidate | active | suspended
                                      # 门：candidate→active = G-COV（coverage_assertion.covered=true）
  # ---- L1 不变量 ----
  invariant:
    essence: str                      # 一句话本质（≤40字）
    competency:
      primary: enum                   # 受控词表 core∪subject_extensions[subject]（决议14）
      real_world_anchor: str
    canonical_logic:
      structure_type: enum            # 受控词表 core: causal_chain|procedure|classification|calculation|criteria_match
      skeleton: [str]
    discriminator: str                # 区分"真懂vs背过"的那一刀（→ L6 据此设计）
  # ---- L2 出题人逻辑 ----
  examiner_intent:
    why_tested: str
    source_transform:                 # 规范原文 → 一道题 的逆向变换（教学金矿）
      source_ref: str                 # 指向 production.provenance.source_refs
      transform_pattern: str
    classic_traps:
      - trap: str
        probes_misconception_id: str  # → L5
    scoring_logic: str
    difficulty_knobs:
      - knob: enum                    # 受控词表（决议14）
        levels: [str]
  # ---- L3 多重表征（表征跟考点类型走）----
  representations:
    - kind: enum                      # 受控词表
      fits_structure: [enum]          # 适合哪类 structure_type
      purpose: enum                   # teach_first_time | fix_misconception | quick_recall | discriminate
      content_spec: str
      provenance: str                 # 可溯源教材/规范原文
  # ---- L4 表皮生成器 ----
  surface_generator:
    invariant_held: [str]             # = invariant.canonical_logic.skeleton
    surface_axes:
      - axis: enum                    # scenario_skin | numbers | question_angle | polarity | distractor_set | given_conditions
        options: [str]
    variant_blueprints:               # 生成「新变体」（消费：出题/诊断）
      - variant_id: str
        question_form: enum           # 受控词表
        surface_config: {axis: value}
        isolates:
          sub_competency: str
          failure_mode_id: str        # 系统覆盖该母题全部失分形态
        scoring_point_refs: [str]     # 缝6 统一引用字段；必为 ∪(production.question_bindings[].scoring_point_refs) 子集
        distractor_to_misconception: {option_id: [misconception_id]}  # list 非 1:1（缝8）
    coverage_assertion:               # = status_structure candidate→active 门（G-COV）
      enumerated_failure_modes: [str]
      covered: bool
  # ---- L5 误解模型 ----
  misconceptions:
    - misconception_id: str           # per-case_family 局部,不建全局 registry
      wrong_mental_model: str
      surface_signals: [str]
      correction: str                 # 打到心智模型（不是"看书P30"）
      correction_representation_ref: str
      maps_error_code: enum           # 单一,∈ ERROR_CODE_REGISTRY；与 production.mistake_tags 锚同一 error_code 轴（决议15）
  # ---- L6 掌握度与鉴别 ----
  mastery:
    discriminator_variants:
      - variant_id: str               # 改一个条件让答案翻转
        flip_condition: str
        memorizer_fails_because: str
    mastery_evidence_rule:            # 只声明证据需求,判定执行在既有引擎（决议15/对抗④）
      requires:                       # 结构化,非自由文本
        - failure_mode_id: str
          binding_level: enum         # same_point | same_node（对齐 production 复测阶梯）
      authority: LearnerStateService / learning_evidence / revalidation_queue
```

## 4. 跨科目复用：复用的是 schema + 编译方法论，不是内容

> 决议13 澄清:**复用的是 schema 形状,不是同一个 case_family 实例跨科目**。一个 case_family 单科目（`subject` 单值）;做新科目 = 用同一 schema + 受控词表 `subject_extensions` 跑新内容,**不建 per-subject 继承/override 层**（那是第二权威）。受控词表与三权分立机制见 §3.0 决议14。

| 层 | 跨科目 | 说明 |
|---|---|---|
| L1–L6 结构（不变量/意图/表征/变体/误解/掌握） | ✅ 完全复用 | 科目无关 |
| `surface_generator` / `difficulty_knobs` 引擎 | ✅ 复用 | 消费 schema，不关心科目 |
| **判分接口抽象 `scoring_mode.kind`** | ✅ 复用（接口） | `case_rubric`（一建案例题采分点）、`mcq_key`（选择题）、`essay_rubric`（论述）都是它的实例；换科目只换实例 |
| 诊断 / 复测 / 表征引擎 | ✅ 复用 | 消费 L5/L6/L3，科目无关 |
| **编译方法论（syllabus → 这套资产的 pipeline）** | ✅ 复用 | **真正会复利的护城河** |
| 具体考点 / 规范 / 陷阱 / 教材原文 | ❌ 每科目重编 | 内容；有 pipeline 则快 |

**关键设计动作（保证可复用）**：把判分从 schema 里**抽象成接口** `scoring_mode.kind`。一建案例题用 `case_rubric`，但 schema 本身不写死"采分点"——它写"该 case_family 绑定到某个 scoring_mode 实例"。这样换到法考（`essay_rubric`）、医考（`mcq_key` + `case_rubric`）时，L1–L6 与引擎原样复用，只换判分实例与内容。

**新科目 = 把编译 pipeline 跑在新考纲上**，不是重建引擎。这是会随科目数复利的护城河。

## 5. 编译（怎么产出：复用 S0–S7 签发 spine）

L1–L6 走既有 Living LLM Artifact Compiler，**不另建管线**：

- **S2 fan-out**：小模型按 case_family schema 产候选 L1–L6（全部经 `make_candidate`，`promote_to_release=False`）。
- **S3 确定性 gate ladder（本 schema 强制项）**：
  - G-INV：`invariant.essence` 必须能从 ≥3 个 surface 变体中被独立抽出同一句（不变量可证伪，见 §7）。
  - G-SRC：`examiner_intent.source_transform` 与 `representations[].provenance` 必须能 verbatim 溯源到教材/规范原文（防 LLM 编造出题人意图）。
  - G-MAP：每个 `distractor_to_misconception` 必须指向一个已定义 misconception；每个 misconception 必须 `maps_error_code ∈ ERROR_CODE_REGISTRY`。
  - G-COV：`surface_generator.coverage_assertion.covered=true` 才能升 active（变体集合覆盖全部 failure_mode）。
  - G-AUTH：`question_bindings[].grading_artifact_id` 引用的 artifact 必须是 published（draft 点只能展示/规划，不参与判分）。
- **S4 council**：四模型对抗只能 down-rank，绝不 up-rank / 补 source。
- **S5 单点签发**：唯一翻 `promote_to_release=True` 处。
- **默认 tier**：L1–L6 = teaching/diagnosis tier，`official_score_allowed=false`；判分永远回 L7。

## 6. 消费（一份资产，五个出口）

```text
                         ┌─ 出题 ←  L4 surface_generator（按难度旋钮生成变体）
                         ├─ 判分 ←  production.question_bindings（引用 signed artifact）
深母题资产（L0–L7）── 喂 ─┼─ 诊断 ←  L5 misconceptions（选错→心智模型→纠正）
                         ├─ 讲解 ←  L3 representations（按考点类型选表征）
                         └─ 复测 ←  L6 discriminator_variants（真懂 vs 背过）
```

全部经 `CompiledContextPack` 单一 runtime 口被 `/api/v1/ws` / read model 消费。**不是五个库，是一份深资产 × 五个出口。**

## 7. 质量门（什么算"世界顶尖"——对资产本身可证伪）

资产合格 = 通过下列**可证伪**检验，而不是"看起来很全"：

1. **不变量锐度（G-INV）**：3 位独立专家（或 3 个独立 LLM 盲跑）从同一母题的 5 个 surface 变体里，抽出的 `invariant.essence` 一致。不一致 = 不变量没提纯，打回。
2. **变体完备性（G-COV）**：枚举的 failure_mode 100% 有对应变体探测；存在"没有任何变体能暴露"的失分形态 = 不完备。
3. **干扰项即探针**：每个似是而非的错误选项都 `maps_to misconception + correction`。存在"只是错、没诊断价值"的干扰项 = 不合格。
4. **鉴别变体有效性**：用"只背了答案"的基线（如喂答案 key 的模型）做 discriminator_variant 会栽；用"会推理"的基线会过。两者无差异 = 这道鉴别题没鉴别力。
5. **表征疗效**：因误解 X 失分的学员，看过 `correction_representation` 后，能做对一道全新的、隔离 X 的变体。看了没用 = 表征无效，重做。
6. **逆向可迁移**：学员看过 `source_transform`（出题人逆向）后，能做对一道**没练过**的变体。不能迁移 = 还在教解法、没教逻辑。
7. **跨科目实例化**：本 schema 能在一个**非建筑**考纲上实例化，零 schema 改动（只换内容 + 判分实例）。需要改 schema = 抽象泄漏，回 §4 修。

**顶尖 = 这 7 条全绿**，尤其 1/4/6（不变量锐度、鉴别力、可迁移）——它们是商品刷题永远做不到、需要真专家 + 教学功底 + 编译纪律才能达成的，因此是护城河。

## 8. 黄金样板（F16 防水，节选填充使 schema 落地）

```yaml
# ── 对象 1/2：指针层 ──
case_family_production:
  case_family_id: F16
  name: 防水卷材分层与施工工序
  subject: 一建建筑实务
  status_production: candidate                 # 有 published artifact 引用,shadow replay 后可升 active
  taxonomy_ref: {node_codes: ["<F16 节点码>"], file: FINAL_CLEANED_TAXONOMY2026.json, sha256: "<写入快照>"}
  provenance:
    source_refs:
      - {type: textbook, ref_id: 教材-防水工程-工序条文, version: "2026", chunk_id: "<chunk>", content_sha256: "<sha>"}
  scoring_mode: {kind: case_rubric}            # artifact 引用下沉 question_bindings
  question_bindings:
    - {question_id: Q18, sub_question_ref: "<小问>", grading_artifact_id: "<F16 published artifact::version>", scoring_point_refs: [P10, P11], retest_role: primary, binding_level: same_point}
  mistake_tags:                                # 判分侧投影,锚 error_code(与 mistake_type 正交)
    - {scoring_point_id: P10, error_code: E06, source: rubric_policy}   # 程序顺序
    - {scoring_point_id: P11, error_code: E03, source: rubric_policy}   # 关键词
  training_tasks:
    - {mode: light, task_id: F16-MCQ-1, estimated_minutes: 2, task_scope: {scope_type: light_check, covered_scoring_point_ids: [P10, P11], excluded_scoring_point_policy: not_evaluated_no_miss, evidence_weight: light_signal}}
  review: {owner: "<>", reviewer: "<>", reviewed_at: "<>", taxonomy_reverified: false, rollback_policy: 单母题 flag 下线}

# ── 对象 2/2：原创教学层（同一 case_family_id 关联）──
case_family_structure:
  case_family_id: F16
  status_structure: candidate                  # FM-NODE 已补齐,covered=true → 可升 active
  invariant:
    essence: 防水构造的"层序 + 搭接 + 节点"由"水往哪流、先做哪层保护哪层"的因果决定
    competency: {primary: 程序排序, real_world_anchor: 现场判断防水施工顺序是否会导致渗漏返工}
    canonical_logic: {structure_type: procedure, skeleton: [基层处理, 附加层(节点先行), 大面铺贴方向(迎水/顺水), 搭接长度与方向, 保护层]}
    discriminator: 是否理解"节点附加层必须先于大面"而不是按"从下到上"死记
  examiner_intent:
    why_tested: 工序错→渗漏→返工→质量事故；现场最高频失分点
    source_transform: {source_ref: 教材-防水工程-工序条文, transform_pattern: 把"应先做节点附加层"倒装成"某队伍先铺大面后补节点,问后果/错在哪"}
    classic_traps:
      - {trap: 用"从下到上"朴素直觉套所有层, probes_misconception_id: MC-LAYER-NAIVE}
      - {trap: 给一个搭接方向逆流水的选项, probes_misconception_id: MC-LAP-DIR}
      - {trap: 节点与大面顺序对调, probes_misconception_id: MC-NODE-LAST}
    scoring_logic: 给分给在"节点先行 + 搭接迎水/顺水 + 方向"三个证明你懂因果的动作,不是背层名
    difficulty_knobs:
      - {knob: interference_condition, levels: [无, 加"赶工期"诱导你跳工序]}
      - {knob: question_angle, levels: [排序, 找错, 改写不规范交底]}
  representations:
    - {kind: flowchart, fits_structure: [procedure], purpose: teach_first_time, content_spec: 工序决策树(每步标"为什么在这一步"), provenance: 教材-防水工序}
    - {kind: counterexample, fits_structure: [procedure], purpose: fix_misconception, content_spec: 先大面后节点→渗漏路径图}
  surface_generator:
    invariant_held: [节点先行, 搭接顺流水, 方向迎水]
    variant_blueprints:
      - {variant_id: V1, question_form: sequence_order, isolates: {sub_competency: 工序排序, failure_mode_id: FM-ORDER}, scoring_point_refs: [P10], distractor_to_misconception: {B: [MC-LAYER-NAIVE]}}
      - {variant_id: V2, question_form: single_choice, isolates: {sub_competency: 搭接方向, failure_mode_id: FM-LAP}, scoring_point_refs: [P11], distractor_to_misconception: {C: [MC-LAP-DIR]}}
      - {variant_id: V3, question_form: single_choice, isolates: {sub_competency: 节点先行, failure_mode_id: FM-NODE}, scoring_point_refs: [P10], distractor_to_misconception: {D: [MC-NODE-LAST]}}   # 补齐 FM-NODE
    coverage_assertion: {enumerated_failure_modes: [FM-ORDER, FM-LAP, FM-NODE], covered: true}   # 三种失分形态都有变体
  misconceptions:
    - {misconception_id: MC-LAYER-NAIVE, wrong_mental_model: "防水=从下往上铺就行", correction: "顺序由'保护谁、水往哪流'决定,节点先行", correction_representation_ref: flowchart, maps_error_code: E06}
    - {misconception_id: MC-LAP-DIR, wrong_mental_model: "搭接只要够长,方向无所谓", correction: "搭接必须顺流水/迎水,逆向=引水进缝", correction_representation_ref: counterexample, maps_error_code: E03}
    - {misconception_id: MC-NODE-LAST, wrong_mental_model: "先大面再补节点也行", correction: "节点是渗漏高发区,必须先附加层保护再大面", correction_representation_ref: counterexample, maps_error_code: E06}
  mastery:
    discriminator_variants:
      - {variant_id: D1, flip_condition: 把屋面改成地下室(水从外侧压),迎水面翻转, memorizer_fails_because: 背"屋面做法"的人照搬,真懂的人按"迎水面"重判}
    mastery_evidence_rule:
      requires:
        - {failure_mode_id: FM-ORDER, binding_level: same_point}
        - {failure_mode_id: FM-LAP, binding_level: same_point}
        - {failure_mode_id: FM-NODE, binding_level: same_point}
      authority: LearnerStateService
```

> 本样板 = Phase 0 的 **F16 薄切片**（决议16），也是两对象形的活样板。FM-ORDER / FM-LAP / FM-NODE 三种失分形态都补了变体 → `covered=true`，structure 侧可升 active；两对象用 `case_family_id: F16` 关联；production 侧 `scoring_mode.kind=case_rubric` + question_binding 引用 published artifact（artifact_id 占位待真实签发），structure 侧承载全部原创教学结构。**这就是去跑 5 天留存测试的弹药**——每个干扰项都映射到 misconception（带 correction + maps_error_code），实现"选错即诊断"。

## 9. 单一权威硬约束 / 反模式

- L1–L6 **永不**写 official score、canonical learner truth、rubric policy。判分回 L7 引用的 signed artifact。
- L5 误解模型**必须**映射既有 `ERROR_CODE_REGISTRY`，禁止私造错因码（`label` 取 registry 原值）。
- L1/L3 知识点身份用 canonical taxonomy `node_code`，禁止另起知识树。
- L2/L3 教学内容**必须**可 verbatim 溯源教材/规范原文（防 LLM 编造"出题人意图"）。
- L6 掌握判定写进 `learning_evidence` / `LearnerStateService`，前端不自算。
- 反模式：把 case_family 当"第二套题库 schema"在 runtime 直接判分；把 misconception 当"第二套错因 taxonomy"；把 representation 当"第二套知识库"。三者都禁止——它们是 teaching/diagnosis 投影，消费既有 authority。

## 10. 分期（守住"先验证留存、再扩产"纪律）

**这份 schema 是资产的北极星，不是现在就全量填的清单。**

- **Phase 0（留存测试用，本周）**：在 **1 个母题（F16）** 上做"薄但真"的切片——必填 L1.essence、L2.classic_traps、L5 误解模型(2-3 个) + correction、L3(one_liner + 1 个 flowchart)、L6 至少 1 个 discriminator_variant、L4 至少覆盖 2-3 个 failure_mode 的变体。**用这个深度切片去跑留存,验证"护城河级深度的资产是否真能留住人"**——而不是用浅 quiz 测,避免假阴性。
- **Phase 1（留存被证明后）**：把 F16 的 `coverage_assertion` 补到 covered=true,L1–L7 填满,作为 schema 的活样板冻结。
- **Phase 2**：扩到 3–5 母题,验证 schema 在不同 `structure_type`(procedure / causal_chain / calculation)上都成立。
- **Phase 3**：用 S0–S7 pipeline 半自动扩产到 30–40 母题;并做一次跨科目实例化冒烟(§7.7),证明 schema 抽象不泄漏。

**扩产的量与节奏由留存信号驱动,不在留存被证明前把 30–40 母题填满**——否则重蹈"做了一堆没人用的案例题资产"的覆辙。

## 11. Registration Ledger（register-before-use 账本）

按 `contracts/schema_registry.yaml` 的 scope_rule（`cross_consumer` / `persisted` / `named_field_binding` 任一命中 = "登记后才能用"）。**当前全部未登记**——本文是 Proposed 设计，下表是落代码前的登记义务清单。实现任一项前先登记并跑 `scripts/check_schema_registry.py` 绿，否则 CI register-before-use 闸会（正确地）拦下。

| 标识符 | scope 命中 | 落地登记到 | 状态 |
|---|---|---|---|
| `case_family_production` schema（指针层:id/subject/status_production/taxonomy_ref/provenance/scoring_mode/question_bindings/mistake_tags/training_tasks/review） | cross_consumer + persisted + named_field_binding | `contracts/schema_registry.yaml`（独立 typed-object entry） | ❌ 未登记 |
| `case_family_structure` schema（原创层:status_structure/invariant/examiner_intent/representations/surface_generator/misconceptions/mastery） | cross_consumer + persisted + named_field_binding | `contracts/schema_registry.yaml`（独立 entry,与 production 用 `case_family_id` 关联） | ❌ 未登记 |
| enum 受控词表：`competency.primary` / `canonical_logic.structure_type` / `difficulty_knobs[].knob` / `representations[].kind` / `representations[].purpose` / `surface_axes[].axis` / `variant_blueprints[].question_form` / `scoring_mode.kind` | named_field_binding（跨消费者按值绑定） | `contracts/schema_registry.yaml`（字段允许值 / authority value） | ❌ 未登记 |
| `misconception_id` / `failure_mode_id` 命名空间（per-case_family 局部 ID） | named_field_binding（该资产消费者间） | 作为 `case_family_structure` schema 字段一并登记；**不另起全局 registry**（避免第二权威 / G8） | ❌ 未登记 |
| `syllabus_locator`（GradingResult/read-model 字段，见 viewmodel-event-contract） | cross_consumer + named_field_binding | grading-result / read-model contract（`contracts/index.yaml` domain + schema_registry） | ❌ 未登记（原名 `textbook_locator` 撞 citations，已改名） |
| `days_since_first_use`（行为事件维度） | cross_consumer | 产品行为事件 catalog（`surface-events` / `product_behavior`，见 viewmodel-event-contract §3） | ❌ 未登记 |
| `mobile_p0a_daily_loop_completed`（行为事件） | cross_consumer | 同上事件 catalog | ❌ 未登记 |

**复用既有 authority，无需新登记**（本文只引用，不新建）：
- `maps_error_code` / `mistake_tags[].error_code` → `ERROR_CODE_REGISTRY`（`deeptutor/contracts/error_codes.py`,E/M 错因轴）。注意 `mistake_code_registry.yaml` 已不存在;判分形态轴 `mistake_type` 另在 `deeptutor/contracts/mistake_codes.py`（与 error_code **正交**,勿混,决议15）。
- `taxonomy_ref.node_codes` → canonical taxonomy。
- `scoring_mode.grading_artifact_id` / `point_ids` → published question grading artifact registry。
- L6 掌握判定写入 → `learning_evidence` / `LearnerStateService`（既有 contract）。

**实现顺序铁律**：先把 `case_family_production` 与 `case_family_structure` 两对象（各自 + enum 词表）登记进 `schema_registry.yaml` → `scripts/check_schema_registry.py` 绿 → 再写任何消费这些字段的代码。Phase 0 的 F16 切片若以**文件型资产**（yaml 落盘 `artifacts/luban_case_family_assets/F16/`）存在、尚未被 runtime 代码按字段名绑定，属设计资产；一旦有代码 emit/consume 其字段，立即触发登记义务。
