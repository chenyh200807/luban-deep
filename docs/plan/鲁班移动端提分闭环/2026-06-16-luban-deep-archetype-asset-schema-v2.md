# 深母题资产 Schema v2（Deep Archetype Asset Schema）

> Status: Proposed / Asset STRUCTURE authority v2（与生产流程 authority 分工）
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

## 3. Schema（分层模型）

```yaml
archetype:                          # 一个母题
  # ---- L0 身份与溯源 ----
  id: str                           # 如 ARCH-F16-WATERPROOF-LAYERING
  name: str
  subject: str                      # 科目（如 一建建筑实务）；跨科目时只此层换
  taxonomy_ref:                     # 钉扎 canonical taxonomy
    node_codes: [str]
    file: str
    sha256: str                     # 写入快照 + 翻转时人工重验（taxonomy 一天多改）
  status: draft | reviewed | candidate | active | suspended
  provenance:
    source_refs: [{type, ref_id, version, chunk_id, content_sha256}]

  # ---- L1 不变量（穿过表皮看到的东西）----
  invariant:
    essence: str                    # 一句话本质（≤40字）：这个母题永远在考什么
    competency:
      primary: enum                 # 识别 | 判断成立性 | 计算 | 程序排序 | 组织得分语言 | 综合归因
      real_world_anchor: str        # 现实中对应什么职业动作（让"为什么考"落地）
    canonical_logic:                # 不变的推理骨架
      structure_type: enum          # causal_chain | procedure | classification | calculation | criteria_match
      skeleton: [str]               # 骨架步骤；换皮时必须保持
    discriminator: str              # 区分"真懂"与"背过"的那一刀（→ L6 鉴别变体据此设计）

  # ---- L2 出题人逻辑（最高杠杆的教学层）----
  examiner_intent:
    why_tested: str                 # 出题人为什么考这个（现实能力 / 典型事故）
    source_transform:               # 逆向工程：规范原文 → 一道题 的变换（教学金矿）
      source_ref: str               # 指向 provenance / 教材 verbatim
      transform_pattern: str        # 如："把'应当先X后Y'的规定，倒装成'某场景先Y后X，问错在哪'"
    classic_traps:                  # 经典陷阱，每个挂它探测的误解
      - trap: str
        probes_misconception_id: str    # → L5
    scoring_logic: str              # 为什么这几个采分点给分 = 证明你真懂的动作
    difficulty_knobs:               # 难度=可计算的旋钮（用于生成 + 自适应）
      - knob: enum                  # distractor_count | reasoning_steps | cross_chapter | time_pressure | numeric_complexity | interference_condition
        levels: [str]

  # ---- L3 多重表征（怎么展示知识：表征跟着考点类型走）----
  representations:
    - kind: enum                    # one_liner | flowchart | causal_chain | compare_table | mnemonic | diagram | worked_example | counterexample
      fits_structure: [enum]        # 适合哪类 canonical_logic.structure_type（编译时自动推荐）
      purpose: enum                 # teach_first_time | fix_misconception | quick_recall | discriminate
      content_spec: str             # 内容或生成规格
      provenance: str               # 教学内容必须可溯源到教材/规范原文

  # ---- L4 表皮生成器（变样式提问）----
  surface_generator:
    invariant_held: [str]           # 生成变体时必须保持不变（= L1.canonical_logic.skeleton）
    surface_axes:
      - axis: enum                  # scenario_skin | numbers | question_angle | polarity | distractor_set | given_conditions
        options: [str]
    variant_blueprints:             # 每个变体 = 隔离一个失分形态/子能力
      - variant_id: str
        question_form: enum         # single_choice | multi_choice | case_subq | short_write | sequence_order
        surface_config: {axis: value}
        isolates:
          sub_competency: str
          failure_mode_id: str      # 用于"系统覆盖该母题全部失分形态"
        maps_to_scoring_points: [str]   # → L7
        distractor_to_misconception: {option_id: misconception_id}  # 每个干扰项是诊断探针 → L5
    coverage_assertion:             # 可证伪：变体集合是否覆盖该母题全部 failure_mode
      enumerated_failure_modes: [str]
      covered: bool

  # ---- L5 误解模型（诊断心智模型，不只是错因分类）----
  misconceptions:
    - misconception_id: str
      wrong_mental_model: str       # 学员脑子里那个错的模型（如"工期一延误就能索赔"）
      surface_signals: [str]        # 它在作答里长什么样
      correction: str               # 打到心智模型的一句纠正（不是"看书P30"）
      correction_representation_ref: str  # → L3 用哪个表征来纠
      maps_error_code: enum         # → ERROR_CODE_REGISTRY（复用判分错因轴，不新建）

  # ---- L6 掌握度与"真懂vs背过"鉴别 ----
  mastery:
    discriminator_variants:
      - variant_id: str             # 专门设计：改一个条件让答案翻转
        flip_condition: str
        memorizer_fails_because: str
    mastery_evidence_rule:          # 何时算真掌握（写进既有账本，前端不自算）
      requires: str                 # 默认：全部 failure_mode 变体 hit + ≥1 discriminator_variant 通过（不同题）
      authority: "LearnerStateService / learning_evidence / revalidation_queue"

  # ---- L7 判分绑定（复用既有 authority，接口不复制）----
  scoring_binding:
    scoring_authority:
      kind: enum                    # case_rubric | mcq_key | essay_rubric  ← 跨科目的"判分接口"抽象
      grading_artifact_id: str      # 案例题：Q18-1A434000::qga_v0_20260604（自含版本）
      point_ids: [str]
    error_code_authority: "deeptutor/contracts/error_codes.py::ERROR_CODE_REGISTRY"

  # ---- 治理 ----
  review:
    owner: str
    reviewer: str
    reviewed_at: str
    taxonomy_reverified: bool
    rollback_policy: str
```

## 4. 跨科目复用：复用的是 schema + 编译方法论，不是内容

| 层 | 跨科目 | 说明 |
|---|---|---|
| L1–L6 结构（不变量/意图/表征/变体/误解/掌握） | ✅ 完全复用 | 科目无关 |
| `surface_generator` / `difficulty_knobs` 引擎 | ✅ 复用 | 消费 schema，不关心科目 |
| **判分接口抽象 `scoring_authority.kind`** | ✅ 复用（接口） | `case_rubric`（一建案例题采分点）、`mcq_key`（选择题）、`essay_rubric`（论述）都是它的实例；换科目只换实例 |
| 诊断 / 复测 / 表征引擎 | ✅ 复用 | 消费 L5/L6/L3，科目无关 |
| **编译方法论（syllabus → 这套资产的 pipeline）** | ✅ 复用 | **真正会复利的护城河** |
| 具体考点 / 规范 / 陷阱 / 教材原文 | ❌ 每科目重编 | 内容；有 pipeline 则快 |

**关键设计动作（保证可复用）**：把判分从 schema 里**抽象成接口** `scoring_authority.kind`。一建案例题用 `case_rubric`，但 schema 本身不写死"采分点"——它写"该 archetype 绑定到某个 scoring_authority 实例"。这样换到法考（`essay_rubric`）、医考（`mcq_key` + `case_rubric`）时，L1–L6 与引擎原样复用，只换判分实例与内容。

**新科目 = 把编译 pipeline 跑在新考纲上**，不是重建引擎。这是会随科目数复利的护城河。

## 5. 编译（怎么产出：复用 S0–S7 签发 spine）

L1–L6 走既有 Living LLM Artifact Compiler，**不另建管线**：

- **S2 fan-out**：小模型按 archetype schema 产候选 L1–L6（全部经 `make_candidate`，`promote_to_release=False`）。
- **S3 确定性 gate ladder（本 schema 强制项）**：
  - G-INV：`invariant.essence` 必须能从 ≥3 个 surface 变体中被独立抽出同一句（不变量可证伪，见 §7）。
  - G-SRC：`examiner_intent.source_transform` 与 `representations[].provenance` 必须能 verbatim 溯源到教材/规范原文（防 LLM 编造出题人意图）。
  - G-MAP：每个 `distractor_to_misconception` 必须指向一个已定义 misconception；每个 misconception 必须 `maps_error_code ∈ ERROR_CODE_REGISTRY`。
  - G-COV：`surface_generator.coverage_assertion.covered=true` 才能升 active（变体集合覆盖全部 failure_mode）。
  - G-AUTH：`scoring_binding` 引用的 artifact 必须是 published（draft 点只能展示/规划，不参与判分）。
- **S4 council**：四模型对抗只能 down-rank，绝不 up-rank / 补 source。
- **S5 单点签发**：唯一翻 `promote_to_release=True` 处。
- **默认 tier**：L1–L6 = teaching/diagnosis tier，`official_score_allowed=false`；判分永远回 L7。

## 6. 消费（一份资产，五个出口）

```text
                         ┌─ 出题 ←  L4 surface_generator（按难度旋钮生成变体）
                         ├─ 判分 ←  L7 scoring_binding（引用 signed artifact）
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
archetype:
  id: ARCH-F16-WATERPROOF-LAYERING
  name: 防水卷材分层与施工工序
  subject: 一建建筑实务
  invariant:
    essence: 防水构造的"层序 + 搭接 + 节点"由"水往哪流、先做哪层保护哪层"的因果决定
    competency: {primary: 程序排序, real_world_anchor: 现场判断防水施工顺序是否会导致渗漏返工}
    canonical_logic:
      structure_type: procedure
      skeleton: [基层处理, 附加层(节点先行), 大面铺贴方向(迎水/流水), 搭接长度与方向, 保护层]
    discriminator: 是否理解"节点附加层必须先于大面"而不是按"从下到上"死记
  examiner_intent:
    why_tested: 工序错→渗漏→返工→质量事故；现场最高频失分点
    source_transform:
      source_ref: 教材-防水工程-工序条文
      transform_pattern: 把"应先做节点附加层"的规定，倒装成"某队伍先铺大面后补节点，问其后果/错在哪"
    classic_traps:
      - {trap: 用"从下到上"这个朴素直觉套所有层, probes_misconception_id: MC-LAYER-NAIVE}
      - {trap: 给一个看似合理但搭接方向逆流水的选项, probes_misconception_id: MC-LAP-DIR}
    scoring_logic: 给分给在"节点先行 + 搭接迎水/顺水 + 方向"这三个证明你懂因果的动作，不是背层名
    difficulty_knobs:
      - {knob: interference_condition, levels: [无, 加一个"赶工期"诱导你跳工序]}
      - {knob: question_angle, levels: [排序, 找错, 改写不规范交底]}
  representations:
    - {kind: flowchart, fits_structure: [procedure], purpose: teach_first_time, content_spec: 工序决策树(每步标"为什么在这一步"), provenance: 教材-防水工序}
    - {kind: counterexample, fits_structure: [procedure], purpose: fix_misconception, content_spec: 先大面后节点→渗漏路径动图}
  surface_generator:
    invariant_held: [节点先行, 搭接顺流水, 方向迎水]
    variant_blueprints:
      - {variant_id: V1, question_form: sequence_order, isolates: {sub_competency: 工序排序, failure_mode_id: FM-ORDER}, distractor_to_misconception: {B: MC-LAYER-NAIVE}}
      - {variant_id: V2, question_form: single_choice, isolates: {sub_competency: 搭接方向, failure_mode_id: FM-LAP}, distractor_to_misconception: {C: MC-LAP-DIR}}
    coverage_assertion: {enumerated_failure_modes: [FM-ORDER, FM-LAP, FM-NODE], covered: false}  # 还缺 FM-NODE 变体 → 未完备，不能升 active
  misconceptions:
    - {misconception_id: MC-LAYER-NAIVE, wrong_mental_model: "防水=从下往上铺就行", correction: "顺序由'保护谁、水往哪流'决定，节点先行", correction_representation_ref: flowchart, maps_error_code: E06}
    - {misconception_id: MC-LAP-DIR, wrong_mental_model: "搭接只要够长就行，方向无所谓", correction: "搭接必须顺流水/迎水，逆向=引水进缝", maps_error_code: E03}
  mastery:
    discriminator_variants:
      - {variant_id: D1, flip_condition: 把屋面改成地下室(水从外侧压)，迎水面翻转, memorizer_fails_because: 背了"屋面做法"的人会照搬，真懂的人按"迎水面"重判}
    mastery_evidence_rule: {requires: "FM-ORDER+FM-LAP+FM-NODE 变体全 hit + D1 通过", authority: LearnerStateService}
  scoring_binding:
    scoring_authority: {kind: case_rubric, grading_artifact_id: "<F16 published artifact::version>", point_ids: [P10, P11]}
    error_code_authority: "ERROR_CODE_REGISTRY"
```

> 注意样板里 `coverage_assertion.covered=false`：它诚实暴露"FM-NODE 还没有变体" → 按 §5 G-COV，这个母题现在只能停在 candidate，不能升 active。这正是 schema 的价值：**它会指着你的资产说"你这还没做完，差一种失分形态没覆盖"。**

## 9. 单一权威硬约束 / 反模式

- L1–L6 **永不**写 official score、canonical learner truth、rubric policy。判分回 L7 引用的 signed artifact。
- L5 误解模型**必须**映射既有 `ERROR_CODE_REGISTRY`，禁止私造错因码（`label` 取 registry 原值）。
- L1/L3 知识点身份用 canonical taxonomy `node_code`，禁止另起知识树。
- L2/L3 教学内容**必须**可 verbatim 溯源教材/规范原文（防 LLM 编造"出题人意图"）。
- L6 掌握判定写进 `learning_evidence` / `LearnerStateService`，前端不自算。
- 反模式：把 archetype 当"第二套题库 schema"在 runtime 直接判分；把 misconception 当"第二套错因 taxonomy"；把 representation 当"第二套知识库"。三者都禁止——它们是 teaching/diagnosis 投影，消费既有 authority。

## 10. 分期（守住"先验证留存、再扩产"纪律）

**这份 schema 是资产的北极星，不是现在就全量填的清单。**

- **Phase 0（留存测试用，本周）**：在 **1 个母题（F16）** 上做"薄但真"的切片——必填 L1.essence、L2.classic_traps、L5 误解模型(2-3 个) + correction、L3(one_liner + 1 个 flowchart)、L6 至少 1 个 discriminator_variant、L4 至少覆盖 2-3 个 failure_mode 的变体。**用这个深度切片去跑留存,验证"护城河级深度的资产是否真能留住人"**——而不是用浅 quiz 测,避免假阴性。
- **Phase 1（留存被证明后）**：把 F16 的 `coverage_assertion` 补到 covered=true,L1–L7 填满,作为 schema 的活样板冻结。
- **Phase 2**：扩到 3–5 母题,验证 schema 在不同 `structure_type`(procedure / causal_chain / calculation)上都成立。
- **Phase 3**：用 S0–S7 pipeline 半自动扩产到 30–40 母题;并做一次跨科目实例化冒烟(§7.7),证明 schema 抽象不泄漏。

**扩产的量与节奏由留存信号驱动,不在留存被证明前把 30–40 母题填满**——否则重蹈"做了一堆没人用的案例题资产"的覆辙。
