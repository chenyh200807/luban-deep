# 鲁班 Grading-to-Brain 总控计划 v2（当前作战图）

> Status: `Active master plan v2`（2026-06-07 当前入口）。
> 本文是鲁班 **Grading-to-Brain Loop** 的总控入口。它的当前目标不是继续堆旧的 registry / shadow 里程碑，而是把“评分引擎产生高质量学习证据”与“Learning Brain/GBrain 沉淀长期学习决策”串成一条可执行、可验证、可产品化的闭环。
>
> 当前 canonical 目标：**鲁班评分引擎 = 高质量学习证据生产器；Learning Brain/GBrain = 长期个性化学习决策器；RAG/知识编译 = 教材、规范、真题、章节与证据供应器；DeepSeek/Qwen = 在线批改与教学执行模型。**
>
> 当前唯一下一步：执行 **M32 Grading-to-Brain Waterproof Vertical Slice**，用一个防水专题纵切证明 `知识编译 -> Compiled Context -> 批改/诊断 -> Learning Evidence -> LearnerClaim -> PersonalizationContextPack -> NextBestAction -> 复测更新`。M5-M31 只作为历史 ledger、release gate 证据和能力底座，不再提供“当前下一步”。
>
> 2026-06-04 §0.12 架构纠偏：Registry/spec/knowledge artifacts 不是最终判题器，而是 Nexus-style runtime LLM adjudication 的高质量上下文底座；未来 production 每次案例题判题必须由 DeepSeek-V4-flash primary / Qwen3.7 plus fallback 参与理解学生答案，deterministic validator 负责防越权和 fail-closed。
>
> 2026-06-04 §0.13 再纠偏：离线编译 artifacts 本身也不能被理解为 rules-only 维护。正确模式是 **LLM-assisted artifact compiler + deterministic-signed releases**：LLM 负责整理和组织数据、生成候选 artifacts、发现缺口和做对抗审查；确定性系统负责来源校验、schema/hash、攻击测试、版本签发和回滚。
>
> 2026-06-06 §0.26 目标重置：本计划的目标不是把鲁班 v1 做成“题库内才会答”的窄评分器，而是建设 **建筑实务专家型学习智能体**。鲁班评分引擎是“诊断仪”，回答“这次答题哪里对、哪里错、为什么错”；Learning Brain/GBrain 是“长期主治医生”，回答“这个学生长期是什么画像、下一步怎么教”。Nexus-style 知识编译的目标是给 LLM 更细颗粒、更可信、更可压缩的工作上下文，**增强** LLM，而不是限制 LLM。
>
> v2 加强点：补齐历史证据账本、使用场景矩阵、三线详细 backlog、异常处理原则、下一步可交付任务包、验收命令与外来 agent 接手规程。§0.14-§0.15 进一步把计划升级为场景驱动交付：M17/M18 必须同时证明 LLM-native grading、LLM-assisted artifact compiler、GBrain-style evidence-first personalization，而不是只多跑一个 milestone。

## 0.C Current Canonical Target（2026-06-07）

| 系统 | 核心问题 | 产物 |
|---|---|---|
| **鲁班评分引擎** | 学生这次案例题 / 客观题 / 开放诊断答得怎么样？ | 采分点命中、得分、错因、`evidence_span`、`high_risk_review`、`GradingEvidenceEvent` |
| **Learning Brain / GBrain** | 这个学生长期是什么状态？下一步怎么教？ | 学习画像、弱点演化、遗忘 / 复测状态、`LearnerClaim`、`PersonalizationContextPack`、下一题推荐、复习计划 |
| **知识编译 / RAG** | 教材、规范、真题、章节和证据在哪里？ | signed shards、source refs、taxonomy / node coverage、Compiled Context 输入 |
| **Runtime LLM** | 如何把本次作答和上下文讲清楚？ | 在线批改、开放诊断、教学解释、候选 work-order |

一句话：

```text
评分引擎是诊断仪，Learning Brain 是长期主治医生。
```

评分引擎每批一次作答，只负责产出结构化、高可信、可追溯的学习证据；Learning Brain 消费这些证据，生成长期记忆、趋势判断和个性化动作。GBrain 不重新评分，RAG 不替代学生画像，知识编译不成为第二套 mutable truth。

当前闭环必须长成：

```text
评分结果
  -> 学习证据
  -> 学生画像 / LearnerClaim
  -> PersonalizationContextPack
  -> 下一步动作
  -> 新训练 / 复测
  -> 再评分
  -> 更新画像
```

### 0.C.1 执行入口与阅读顺序

1. 先读本节和 §0.26，确认目标和 authority。
2. 再读 §0.26.14，确认知识编译 storage / serving / capacity contract。
3. 当前执行只读 M32 计划：[2026-06-07-luban-grading-to-brain-m32-waterproof-vertical-slice-execution-plan.md](2026-06-07-luban-grading-to-brain-m32-waterproof-vertical-slice-execution-plan.md)。
4. M26/M27/M30/M31 是已完成能力底座和 ledger，不要按其中旧 checklist 重新执行。
5. 任何 production default、published registry、canonical learner truth write、远端/DB 写仍需单独授权。

## 0.0 Canonical update after M5D（2026-06-04）

> **本节 supersede 本文后续所有旧的 M5/M6 下一步表述。历史数字保留用于审计，但不能再作为直接发布依据。**

最新 canonical ledger：

- `artifacts/luban_grading_artifacts/registry_v1_canonical_state_reconciliation_20260604/`
- `artifacts/luban_grading_artifacts/ai_expert_council_source_court_m5d_20260604/`
- `artifacts/luban_grading_artifacts/registry_v1_candidate_dry_run_m6_20260604/`

当前裁决：

- M5 的 **25 个 `auto_certifiable` 点仍有效**，但只作为 deterministic baseline，不是当前可发布集。
- M5 的 `publish_ready_candidate=2` 与 M5R 的 `publish_candidate=1` 已被 live M5B / M5C / M5D supersede。
- 当前直接 M6 `publish_candidate` = **0**；直接跑 M6 发布候选是 **NO-GO**。
- 已存在的 M6 candidate dry-run 只证明 compiler / ArtifactRuntimeGate dry-run 不污染 v0 和 runtime；它不代表 Registry v1 可发布。
- M5D source court 对 9/9 `source_anchor_dispute` 终裁为 `council_not_publish`。
- M5D 25 点 action 分布：`approve_with_repaired_anchor=6`、`split_point=5`、`require_external_source=5`、`rewrite_point=4`、`drop_point=4`、`keep_draft=1`。
- 无真人专家时，review authority 可改为 `ai_expert_council_final`；但 source authority 仍只能是 **2026 教材 `content_markdown` exact/verbatim match**。AI council 不能替代教材 source authority，不能伪造 `textbook_quote/source_ref`，不能写 human/PO/manual teacher 字段。

当前下一步：

1. **M7 compiler hardening**：固化 `list_rule coverage==1.0`、council-final action gate、repaired anchor deterministic reverify。
2. 再做 source repair factory 扩面，或进入 QA beta 产品测试。
3. 不要按过期 M5/M5R 结论直接跑 M6 publish candidate。

---

## 0.05 Canonical update after M8 / M9 / M10（2026-06-04）

> **本节 supersede §0.0 的"当前下一步"。M6/M7 已完成，不再是下一步；residual 瓶颈已从"source hunt"转为"non-textbook rubric authority / spec factory"。后续 agent 不要回到 M6/M7 旧下一步。**

最新 canonical ledger：

- `artifacts/luban_grading_artifacts/registry_v1_council_hardened_candidate_m7_20260604/`（M7 compiler hardening 已完成）
- `artifacts/luban_grading_artifacts/v1_alpha_grand_sprint_m8_20260604/`（M8 alpha_shadow）
- `artifacts/luban_grading_artifacts/v1_beta_shadow_source_assault_m9_20260604/`（M9 beta_shadow source assault）
- `artifacts/luban_grading_artifacts/non_textbook_rubric_authority_factory_m10_20260604/`（M10 non-textbook authority factory）

**三轴 verdict（固定，互不覆盖）：**

| 轴 | verdict | 含义 |
|---|---|---|
| M8 alpha_shadow | **GO** | shadow 级可推进；legacy unchanged、production_runtime_connected=false |
| M9 / M10 gated beta readiness | **WEAK-GO** | source-backed auto preview 23 < 50；spec 增量真实但未经 M11 验证 |
| production v1 | **NO-GO** | formal registry 未生成；不接生产 |

> M9 source_assault 产物里的 `canonical_m8_verdict=WEAK-GO` 只解释为"not gated beta / not production"，**不得**覆盖 M8 alpha_shadow=GO。

进度数字：

- source-backed auto preview：M8 **18** → M9 **23**（textbook verbatim only，仍 < 50）。
- M10 把 **131 个 residual 点**全量分到 6 类 authority bucket：`textbook_verbatim_auto=9`、`machine_checkable_case_spec=45`、`list_rule_structured=14`、`external_source_required=13`、`teacher_or_ai_council_review=31`、`drop_or_keep_draft=19`。
- M10 新增 **45 machine-checkable specs + 14 full-coverage list specs**（共 59 个 spec），全部通过 7 向 false-positive 攻击：`false_positive=0`、`contradiction_rejected=100%`、`off_by_one/denominator_mismatch` 全拦。
- beta_shadow 可评分供给：23 → **82**（textbook auto 23 + spec 候选 59），但 spec 是 candidate 供给，未经 M11 验证。
- 安全不变量全 0：official_answer 不当 textbook、模型票不当 source、无 semantic-only auto、未接 runtime、未生成 formal registry、未覆盖 v0。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：**

1. **M11 gated beta QA**：用真实/教师复核验证 M10 的 machine-checkable / list specs，把 source-backed + spec-validated 可评分点推到 ≥ 50。
2. 同步把 13 个 external_source work order 与 31 个 review packet 接入 teacher / AI council review lane。
3. **不要**回到 M6 publish candidate 或 M7 旧下一步；**不要**继续硬搜教材锚（可锚点已基本榨干）。

---

## 0.06 Canonical update after M11 runtime gated entry（2026-06-04）

> **本节 supersede §0.05 的"当前下一步"。M11 已把 v1 beta_shadow 真正接进 runtime；下一步是 M12 internal live QA，不再是离线报告。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/runtime_gated_beta_entry_m11_20260604/`

**四轴 verdict（固定，互不覆盖）：**

| 轴 | verdict |
|---|---|
| M8 alpha_shadow | **GO** |
| M9 / M10 beta readiness | **WEAK-GO** |
| **M11 runtime gated entry** | **GO** |
| production v1 | **NO-GO** |

M11 接入点（最小代码、最小 authority 漂移）：

- 真实入口：`deeptutor/capabilities/deep_question.py::_maybe_attach_v1_beta_shadow`——既有 `/api/v1/ws` deep_question 批改路径的 **QA/test-only branch**，紧挨既有 `_maybe_attach_runtime_shadow`，append-only。**未新增聊天 WS、未新增路由、未替换 CaseGradingSkillKernel。**
- thin wrapper 只做 flag / env kill switch / qa-guard / append-only / fail-closed；**所有评分 policy 在 fat skill** `deeptutor/services/construction_grading/beta_shadow_loader.py`（read-only 加载 M10 供给 82 + hash/schema 校验 + 确定性 source/spec/list matcher + LB preview + review queue）。
- flag：request `grading_engine_v1_beta_shadow=true`；env kill switch `LUBAN_V1_BETA_SHADOW_ENABLED=false`；production default OFF。
- 验证（15 样本，runtime safety 全过）：flag off legacy 字节不变、flag on append-only、kill switch 立即关闭、artifact missing/malformed fail-closed、`construction_grading_result` 未覆盖、production_write_count=0、Learning Brain writeback=false、review queue 15 个、duplicate 幂等。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：M12 internal live QA**

1. 真实 QA 学员（`qa_`/`test_` id）经 `/api/v1/ws` 带 flag 触发 flag-on beta_shadow；老师清 review queue（override/回滚走既有 teacher-review 写回，仍 shadow）。
2. 验证 Learning Brain preview；env kill switch 作运营熔断。
3. production 仍 **NO-GO**，直到单独的 formal release gate 通过；**不要**回到 M6/M7/M8/M9 旧链路。

---

## 0.07 Canonical update after M12 internal live QA runtime drill（2026-06-04）

> **本节 supersede §0.06 的"当前下一步"。M12 已通过真实 `/api/v1/ws` 压测 beta_shadow runtime；下一步是 M13 formal release candidate gate（独立开门），不要再退回离线报告或旧链路。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/internal_live_qa_runtime_drill_m12_20260604/`

**五轴 verdict（固定，互不覆盖）：**

| 轴 | verdict |
|---|---|
| M8 alpha_shadow | **GO** |
| M9 / M10 beta readiness | **WEAK-GO** |
| M11 runtime gated entry | **GO** |
| **M12 internal live QA** | **GO** |
| production v1 | **NO-GO** |

M12 真实入口：FastAPI TestClient `/api/v1/ws` → `TurnRuntimeManager.start_turn` → `ChatOrchestrator` → `DeepQuestionCapability` → `_maybe_attach_v1_beta_shadow`（**非**直接调函数）。flag 经 start_turn `config.grading_engine_v1_beta_shadow=true` 透传——已把该 key 加入 `turn_runtime.runtime_only_keys` allowlist（与既有 `grading_engine_runtime_shadow` 同处，仅 routing，无 policy）。

M12 证据（86 runtime submissions）：false_positive=0、bad_certified=0、source_mismatch=0、legacy_equal_rate=1.0、production_write_count=0；kill switch / artifact fail-closed / non-qa guard 全过；teacher review dry_run 幂等；Learning Brain 仅 preview（writeback=false）；latency p50=23ms（p95 由冷启动抬高，稳态 ~18–23ms）。7 个对抗攻击全 pass。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：M13 formal release candidate gate**

1. M13 是一个**独立的 formal release 门**（不是 M12 自动延伸）：要把 beta_shadow 从 QA/test 升到任何更高暴露面，必须单独评审 production authority、真人 teacher 复核闭环、source-backed auto≥50、双大模型 skeptic（补 OpenAI key 启用 GPT5.5）。
2. M13 readiness 当前为 **WEAK-GO**：runtime 安全已证，但 production v1 仍 NO-GO，需独立 release gate。
3. **不要**回到 M6/M7/M8/M9/M10/M11 旧链路重跑；**不要**在没有 formal release gate 的情况下改 production default。

---

## 0.11 Canonical update after M16 controlled production runtime flip（2026-06-04，**唯一 canonical**）

> **本节 supersede §0.10 的 "下一步 M16"。M16 已把 v1 从 beta_shadow 提升为 controlled_runtime_candidate，在真实 `/api/v1/ws` 接入受控 cohort；controlled production runtime=GO，但 production default 仍 OFF。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/controlled_production_runtime_flip_m16_20260604/`

**M16 三轴 verdict：**
| 轴 | verdict |
|---|---|
| controlled production runtime | **GO** |
| production default enable | **NO-GO**（需 M17 用户授权小流量 flip） |
| production v1 | **NO-GO** |

- 编译 `registry_v1_release_candidate`（status=**release_candidate**，**非** published，含 source/spec/list provenance + supply hash + registry hash + rollback pointer；不覆盖 v0）。counted=**70**（textbook 23+machine_logic 30+machine_calc 3+list 14；question_stem 排除）。
- 真实 `/api/v1/ws` 受控 runtime（新 mode `controlled_runtime_candidate`）：flag `grading_engine_v1_controlled_runtime` + env kill switch `LUBAN_V1_CONTROLLED_RUNTIME_ENABLED` + cohort `LUBAN_V1_CONTROLLED_RUNTIME_COHORT`（默认 `qa_,test_,operator_`）。production default **OFF**。
- 实测：controlled_auto_total=54、cohort_hit=true、non_cohort_blocked=true、false_positive=0、legacy_equal_rate=1.0、append-only、kill works、malformed-registry fail-closed、rollback→legacy-only、production_write=0、p50≈25ms。
- 代码（薄 wrapper / 胖 skill）：`beta_shadow_loader` 加 release-candidate registry loader + `build_controlled_runtime_payload`；`deep_question` 加 `_maybe_attach_v1_controlled_runtime` thin hook；`turn_runtime` allowlist 加 flag。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：M17 controlled production default flip（需用户显式授权）**

1. M17 才是小流量 production default flip，**必须用户显式授权**；M16 GO 仅解锁「受控 cohort 真实 runtime 跑通」。
2. M17 前置：真人 teacher 闭环（非 shadow）、operator cohort 实时监控窗口、双大模型 skeptic（GPT5.5 key）、canonical learner truth write 路径（当前 dry-run）。
3. production v1 仍 **NO-GO**、production default OFF、**不发 published registry**；**不要**回 M11–M15 旧链路、**不要**未授权开 default。

---

## 0.12 Canonical architecture correction: Nexus-style runtime LLM adjudication + artifact maintenance authority（2026-06-04）

> **本节 supersede §0.11 的"下一步 M17 default flip"表述。M16 controlled runtime 已证明接线安全；但 production v1 的正确方向不是把离线 registry/spec 当最终判题器直接翻 default，而是升级成 Nexus-style runtime adjudication：编译层提供高质量、可追溯、可压缩的判题上下文；每次真实判题仍必须有 LLM 参与理解学生答案。**

### 0.12.1 纠偏后的核心原则

1. **能力优先，不是 token 优先。** 鲁班评分引擎 v1 的目标是更高准确率、更细颗粒度、更强解释能力和更稳定的学习闭环；token efficiency 只是实现约束，不能倒置成产品目标。
2. **离线编译不是最终判题器。** 知识编译、rubric 编译、authority partition、registry candidate 的作用是把 LLM 需要理解的世界整理成可信、结构化、可引用、可裁剪的 `GradingPacket`，不是把 LLM 从判题里拿掉。
3. **运行期必须 LLM adjudication。** 每次案例题判题都应由 runtime LLM adjudicator 基于 `student_answer + question/stem + compiled rubric + evidence/spec/list policy + learner context` 做点级裁决；deterministic validator 只负责防越权、验 source/spec/list、拦 false positive、fail-closed。
4. **production 模型分工固定。** 未来生产运行主模型为 **DeepSeek-V4-flash**，fallback 为 **Qwen3.7 plus**。GPT5.5 / Opus4.8 / DeepSeek-V4 / Qwen3.7 组成的四模型专家组只用于设计、构建、对抗验证、release council 和离线评测，不进入常规 production runtime。
5. **Nexus-style 的精髓是 compile once, adjudicate with scoped packet many times。** 编译层把教材、题干、外部规范、rubric、采分点、历史复核和 learner evidence 做成可信 artifacts；runtime 只给 LLM 看本次判题最有价值的 scoped packet，而不是把全量资料塞给模型，也不是减少 LLM 能力投入。
6. **Nexus-style compiler 是能力放大器，不是题库闸门。** 学 Nexus 的目的，是让系统通过知识编译更会理解题目、组织证据、迁移到变体题、生成高质量上下文和持续吸收新知识；不是把系统缩成“registry 里有才答、题库外就拒答”。已签发 artifacts 提供高置信锚点；未命中的问题应进入 open-world teaching / RAG / LLM reasoning / candidate compiler loop，而不是停止服务。

### 0.12.2 Artifact 维护 authority：哪些会运行期更新，由谁维护

运行中会持续更新 artifacts，但不能把所有 artifacts 混成一类。必须分四层维护，防止离线 compiler、LLM vote、Learning Brain 互相抢权：

| artifact 层 | 是否运行期更新 | 维护 authority | 写入触发 | 不能做什么 |
|---|---:|---|---|---|
| **Source / Rubric / Registry release artifacts** | 不原地更新；只发新 version | LLM-assisted Source/Rubric/Registry Compiler（A 线，LLM 产候选 + deterministic verifier + content/source owner + release gate 签发） | 教材/题库/外部规范补源、rubric 结构修复、teacher/council 审计结论进入下一版编译 | 不能按单个学员进展即时改当前 published/release_candidate；不能把 official_answer/model vote 当 source；不能把 rules-only compiler 当成目标形态 |
| **Runtime GradingPacket artifact** | 每次判题临时生成，可记录 hash/provenance | `construction_grading` fat skill / future `RuntimeGradingPacketBuilder` | `/api/v1/ws` 收到作答或复测，按题目、答案、learner context、artifact version 组包 | 不能成为第二套 registry；不能绕过 validator 或改 legacy grading truth |
| **Runtime adjudication result / review queue artifact** | 每次判题更新 | Runtime LLM Adjudicator + Deterministic Validator + Review Queue service | DeepSeek-V4-flash 判题；失败/低置信/冲突时 Qwen3.7 plus fallback；validator 落 final disposition | LLM 不能替代 source authority；review queue 不能伪造 teacher/human |
| **Learner progress artifact**（evidence event / claim / PersonalizationContextPack / retest proof） | 运行期持续更新 | Learning Brain / `LearnerStateService` / canonical claim gate（C 线） | teacher-reviewed 结果、真实 retest proof、validator-approved grading evidence；周期性 synthesis 只做 projection | shadow/模拟复测不能升 canonical truth；不能新建第二套 learner memory / personalization authority |

结论：**离线编译 artifacts 会在系统运行过程中持续产生新版本，但由 A 线 compiler/release gate 维护；学员实时进展由 C 线 Learning Brain 维护；每次判题的即时理解由 runtime LLM adjudicator 维护。** 三者通过 artifact version / supply hash / event provenance 连接，不能互相替代。

### 0.12.3 历史下一步（已被 §0.C / §0.26.15 M32 supersede）：M17 Nexus-style Runtime LLM Adjudicator

M17 不再定义为直接 production default flip，而是：

1. 在现有 M16 controlled runtime 基础上实现 **Runtime GradingPacket Builder**：读取 release_candidate registry、question/stem、student_answer、learner context、source/spec/list policy，生成 task-scoped packet。
2. 实现 **DeepSeek-V4-flash primary adjudicator + Qwen3.7 plus fallback**：输出点级 `accept / partial / reject / needs_review`、evidence span、reasoning summary、confidence、blocked reason、Learning Brain event draft。
3. 实现 **Deterministic Validator**：source/spec/list authority 验证、false-positive attack guard、unsupported-positive fail-closed、legacy append-only、production write guard。
4. 在 `/api/v1/ws` controlled cohort 真实跑：对比 M16 deterministic controlled runtime 与 M17 LLM adjudication 的准确率、颗粒度、review calibration、Learning Brain card 质量、latency/token/cost。
5. M17 GO 门：false_positive=0、bad_certified=0、source_mismatch=0、legacy_equal=1.0、production_write=0；点级解释质量和 teacher-review packet 可用性必须优于 M16；DeepSeek failure 能被 Qwen fallback 或 fail-closed 正确处理。

production default 仍 **NO-GO**，直到 M17 证明 runtime LLM adjudication 在 controlled cohort 中比 deterministic controlled runtime 更强，并且用户显式授权小流量 default flip。

---

## 0.13 Canonical correction: offline artifacts are LLM-maintained candidates, not rules-maintained static assets（2026-06-04）

> **本节补强 §0.12。上一版表述把运行期判题的 LLM 角色说清了，但对离线编译 artifacts 的维护方式仍容易被误读成 rules-only compiler。这是错误方向。Andrej Karpathy 式的核心杠杆是用 LLM 整理、组织、压缩和重构数据；规则系统只负责校验、签发和守边界。**

### 0.13.1 正确维护模式

离线编译 artifacts 的生产链必须改成：

```text
raw evidence
  -> LLM compiler workers
  -> candidate artifacts
  -> deterministic validators
  -> adversarial / council review
  -> signed immutable release artifact
  -> runtime GradingPacket builder
```

也就是说：

- **LLM 维护 candidate knowledge organization**：抽采分点、拆 official answer、识别案例判断、补 calculation/list spec、找 source candidate、生成 external work order、写 review packet、做风险解释和对抗审查。
- **deterministic gates 签发 release truth**：exact/verbatim 校验、source boundary、schema/hash、version/supersession、false-positive attack、rollback pointer、production write guard。
- **release artifact immutable**：已签发 artifacts 不原地改；运行中发现新证据或错误时，产出新 candidate → 新验证 → 新 release version。

### 0.13.2 Artifact 类型与 LLM 参与度

| artifact 类型 | LLM 角色 | deterministic / release 角色 | 是否可直接 runtime 消费 |
|---|---|---|---|
| `rubric_candidate` | 拆分 official answer、提 required_terms、判断 policy type、发现需要 split/rewrite/drop 的点 | 防 official_answer laundering、schema、去重、point id 稳定性 | 否 |
| `source_candidate` | 找教材/题干/外部规范可能支撑点，生成 query terms 和候选 quote | exact span、source kind、content hash、provenance、source mismatch guard | 否 |
| `machine_checkable_spec_candidate` | 把索赔/工期/费用/逻辑判断转为 calculation/logic spec | off-by-one、partial、contradiction、near-synonym、denominator attack | 否 |
| `external_source_work_order` | 判断需要哪类外部规范/法规/图集，给 source hint 和验收标准 | 禁止编造外部规范，禁止 source laundering | 否 |
| `review_packet` | 压缩争议点、证据、模型分歧、建议动作，降低 reviewer 成本 | redaction、teacher-only guard、authority label guard | 否 |
| `registry_release_candidate` | 做最终风险解释、coverage gap、对抗审查、迁移建议 | release gate 签发、hash、rollback、production default guard | controlled cohort only |

### 0.13.3 对 M17 的新增要求

M17 不只实现 runtime LLM adjudicator，还必须验证 **offline LLM-assisted compiler loop**：

1. 从 M16/M15 residual、review queue、runtime adjudication misses 中抽样，跑 LLM compiler workers 生成新 candidate artifacts。
2. 对候选跑 deterministic validators 和 adversarial attacks，产出 `candidate / rejected / work_order / release_candidate` 四类账本。
3. 证明 LLM 参与后，artifact 质量指标提升：coverage、spec clarity、teacher packet usefulness、runtime GradingPacket compactness、review deflection，而不是只减少 token。
4. 证明失败路径安全：LLM 生成的候选如果 source 不足、spec 攻击不过、review 结论不稳，必须停在 candidate/rejected/work_order，不能进入 release artifact。

M17 的口号应固定为：

> **LLM organizes the data; deterministic gates sign the artifact; runtime LLM adjudicates the answer.**

---

## 0.14 Global expert operating plan: scenario-driven delivery, not milestone drift（2026-06-04）

> **本节 supersede 后文 §6 / §11 / §16 / §17 / §18 中所有旧的“下一步 prompt / 72 小时排期 / M7-M16 单线推进”表述。历史段落保留用于审计；当前执行只按 §0.12-§0.14。**

### 0.14.1 当前真实状态

当前已经完成的不是“production v1”，而是三个关键底座：

1. **M16 controlled runtime 安全底座**：真实 `/api/v1/ws`、cohort、kill switch、fail-closed、append-only、legacy unchanged、rollback 都已证明。
2. **authority partition / registry release-candidate 底座**：textbook / machine_calc / machine_logic / list / question_stem / external / review / drop 等 authority kind 已拆清，source laundering 已被守住。
3. **Learning Brain dry-run / retest proof 底座**：grading evidence → claim proposal → PersonalizationContextPack → retest proof 的链路已证明，但 production canonical learner truth 仍未打开。

真正未完成的是：**把这些底座升级成 LLM-native、场景可用、可观测、可回滚、可持续编译的鲁班评分引擎 v1。**

### 0.14.2 使用场景优先级矩阵

后续所有任务必须先覆盖这些场景，不允许只做离线指标或单点脚本：

| 场景 | 目标体验 | 必须参与的能力 | 当前风险 | 验证方式 |
|---|---|---|---|---|
| S1 学生首次提交案例题答案 | 点级判分、扣分原因、教材/题干/spec 证据、下一步练习 | Runtime GradingPacket + DeepSeek adjudicator + validator | 只靠 deterministic matcher 颗粒度不足 | 真实 `/api/v1/ws` 50+ submissions，对比 M16 baseline |
| S2 学生答案部分正确/大白话/近义表达 | LLM 能识别合理等价、partial credit，不机械踩词 | LLM adjudication + policy-aware rubric packet | 过度给分或过度保守 | point-level fp=0，partial calibration 样本人工/四模型 council 复核 |
| S3 计算/索赔/工期题 | 展示计算路径、单位、公式、差错位置 | machine spec + LLM explanation + deterministic calculator | LLM 编造公式或算错 | adversarial off-by-one / denominator / contradiction 全拦 |
| S4 list_rule 多项采分 | 每项独立判断，不因部分命中整列给分 | list spec + per-item evidence + validator | partial anchor 灌分 | denominator coverage=1.0，partial list false positive=0 |
| S5 题干事实型判断 | 引用完整题干事实，不把 official_answer 当题干 | question_stem source + LLM span finder | 题干缺失/截断 | stem span exact match；缺失则 work_order，不计 release |
| S6 外部规范/法规点 | 明确“需要外部源”，不硬塞教材 | LLM work_order + external source compiler | 编造外部规范 | external work_order 只进 pending，不进 auto |
| S7 high-risk / source_gap / low confidence | 自动进入 review queue，老师/AI council 看得懂 | review packet generator + queue | review 成本高、误点 accept | terse packet tournament + mistaken-accept guard |
| S8 老师/操作员复核 | override/reject/confirm 幂等、可回滚、写权清楚 | teacher_review_writeback + canonical claim gate | shadow 被误写 truth | dry-run 与真实 QA/test writeback 分开验 |
| S9 学生复测 | 能证明进步或继续诊断，不用模拟冒充真实 | retest via `/api/v1/ws` + LB claim gate | simulated proof 污染 mastery | real_retest_proof only；simulation 永不 canonical |
| S10 运行期 provider 失败/超时/限流 | DeepSeek fail 时 Qwen fallback；双失败 fail-closed | provider router + timeout + fallback ledger | 静默降级或输出空假结果 | injected timeout/key-missing/429 测试 |
| S11 artifact 版本更新 | 新 evidence 触发 candidate，新 release 不覆盖旧版本 | LLM compiler loop + release ledger | 原地改 artifact 破坏可追溯 | version/hash/supersession/rollback 测试 |
| S12 production rollback | env kill / cohort / registry rollback 秒级生效 | controlled runtime guard | release 后难回退 | rollback drill，legacy_equal=1.0 |

### 0.14.3 目标架构：六个一等组件

M17 之后的鲁班评分引擎 v1 必须收敛成六个一等组件；不要继续让脚本和里程碑名变成架构：

1. **LLM Artifact Compiler**
   输入 raw evidence / official answer / prior artifacts / review queue / runtime misses；输出 `rubric_candidate`、`source_candidate`、`machine_spec_candidate`、`external_work_order`、`review_packet`、`release_candidate_delta`。
   生产者：打造期四模型专家组；未来日常由 DeepSeek/Qwen 小模型编译候选，四模型只做 release council。

2. **Deterministic Artifact Signer**
   负责 schema、hash、exact span、source kind、spec attack、list coverage、provenance、supersession、rollback。它签发 release artifacts，但不负责语义创造。

3. **Runtime GradingPacket Builder**
   按题目、学生答案、artifact version、learner context、budget 组 scoped packet。它不是第二套 registry，只是 runtime 输入编译器。

4. **Runtime LLM Adjudicator**
   生产模型固定：DeepSeek-V4-flash primary，Qwen3.7 plus fallback。输出点级裁决、partial、evidence span、reasoning summary、confidence、blocked reason、LB event draft。

5. **Runtime Validator / Gate**
   防越权：source laundering、unsupported positive、high-risk auto、partial list auto、bad calculation、legacy overwrite、production write。

6. **Learning Brain Evidence Loop**
   只消费 validator-approved grading evidence、teacher/council-reviewed result、real retest proof。LLM 做 synthesis；canonical claim gate 决定是否升 learner truth。

### 0.14.4 当前最优可交付路线

**M17A：Runtime GradingPacket + LLM adjudication vertical slice（最高优先级）**

- 目标：在 M16 controlled runtime 之上，让每次判题真实进入 DeepSeek-V4-flash adjudication；Qwen3.7 plus 做 fallback；validator 守住安全。
- 范围：只对 qa_/test_/operator_ cohort；production default OFF；不发 published registry。
- 必产：packet schema、prompt contract、model routing ledger、fallback ledger、point decision matrix、Learning Brain draft events、comparison vs M16 deterministic baseline。
- GO 门：fp=0、bad_certified=0、source_mismatch=0、legacy_equal=1.0、production_write=0；解释颗粒度、partial credit、teacher packet usefulness 必须优于 M16 baseline。

**M17B：Offline LLM Artifact Compiler loop（与 M17A 并行，但不抢 runtime）**

- 目标：证明离线 artifacts 不是 rules-only，由 LLM compiler workers 从 residual/misses/review queue 中产出高质量 candidates。
- 范围：candidate namespace only；不得进入 release artifact，除非 signer 通过。
- 必产：candidate/rejected/work_order/release_candidate_delta 四账本，artifact quality report，attack report，compiler prompt pack。
- GO 门：candidate precision、spec clarity、source candidate exact-match rate、review packet usefulness 明显高于 M10/M12A baseline；source laundering=0。

**M18：Controlled product QA round with real operator workflow**

- 目标：不是更多脚本，而是一轮真实内部老师/运营流程：学生提交 → LLM 判题 → review queue → override/reject/confirm → retest → LB pack。
- 范围：内部 cohort；可以 dry-run writeback + 少量 QA/test 真写；不碰真实生产学生。
- GO 门：operator 能清队列，review deflection 可量化，teacher packet 平均阅读成本下降，学生可见 study card 可解释，rollback drill 通过。

**M19：Production default decision sheet**

- 目标：到这里才讨论小流量 production default flip。
- 前置：M17A GO + M17B GO + M18 GO；provider 成本/延迟可控；observability 看得到；用户显式授权。
- 默认：未满足则 production v1 继续 NO-GO。

### 0.14.5 不确定性与验证方案

| 不确定性 | 风险 | 验证方案 | 替代方案 |
|---|---|---|---|
| DeepSeek-V4-flash 对复杂案例判断是否足够稳 | 过度给分或解释不准 | M17A 与四模型 council / M16 baseline / known fixtures 三方对比 | Qwen fallback 提权；高风险点强制 review |
| Qwen fallback 是否能在 DeepSeek 失败时保持一致 | fallback 风格漂移 | 注入 timeout/429/key-missing + same packet replay | 双失败 fail-closed；进入 review queue |
| LLM compiler candidates 是否会引入 laundering | 编造 source 或误升 release | signer exact-match/source-kind/spec-attack 强制门 | candidate 只进 work_order，不进 release |
| token/cost 是否可控 | 产品可用但成本失控 | packet budget、latency、token、fallback rate 全量记录 | 压缩 packet、缓存 signed artifact、降低非关键解释长度 |
| 没有真人专家 | release 质量边界不足 | 四模型 build-phase council + AI council provenance | 只发 controlled cohort，不开 production default |
| 题干/外部规范仍缺 | 覆盖无法再提升 | work_order ledger + targeted source acquisition | review-only，不自动认证 |
| Learning Brain canonical truth 写入是否可靠 | 学情污染 | real_retest_proof + teacher/council-reviewed gate | 只 preview，不写 canonical |

### 0.14.6 计划质量硬门

后续任何 agent 提交 M17+ 结果，必须回答这 12 个问题：

1. LLM 在哪里组织数据，而不是只做最终问答？
2. 哪些 outputs 是 candidate，哪些是 signed release？
3. Runtime 是否每次真实调用 DeepSeek-V4-flash 或 Qwen fallback？
4. GradingPacket 是否 task-scoped、typed、cited、budgeted？
5. Validator 拦住了哪些 LLM 越权？
6. false_positive / bad_certified / source_mismatch 是否全 0？
7. partial credit 和大白话识别是否比 M16 baseline 更好？
8. review queue 是否更少、更清晰、更可操作？
9. Learning Brain 是否只写 preview/dry-run，或具备真实 gate？
10. provider failure 是否 fail-closed？
11. artifact 更新是否 versioned + rollbackable？
12. 这次推进是否让 production v1 更接近真实可用，而不是只多一个报告？

### 0.14.7 当前推荐派工

三路并行，互不阻塞：

1. **主路 M17A Runtime LLM Adjudicator**：最重要，直接决定鲁班评分引擎 v1 是否成为真正 LLM-native 产品。
2. **并路 M17B Offline LLM Artifact Compiler**：把 Karpathy/Nexus-style 编译层做实，持续提高 GradingPacket 质量。
3. **并路 M18 Operator QA Workflow Prep**：准备真实老师/运营试用，不等 M17 完美后才开始产品闭环。

暂时不要做：

- 不要直接 production default flip。
- 不要继续把 deterministic registry 当最终引擎。
- 不要为了 token 少牺牲判题能力。
- 不要再新增第二套 WS、第二套 learner memory、第二套 registry authority。
- 不要把 artifact 报告、截图、本地 ignored outputs 混进 release surface。

---

## 0.17 Canonical update after M17B/M18 AI-council calibrated scaleout（2026-06-05）

> **本节推进 §0.16 的 M17A 纵切：M17B/M18 把 runtime LLM adjudication 扩成产品决策级规模证据 + 4 模型 AI council。production default 仍 OFF；下一步 M19 default decision（需用户授权 + 准确率 eval）。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/runtime_llm_ai_council_scaleout_m17b_m18_20260604/`

**M17B/M18 三轴 verdict：**
| 轴 | verdict |
|---|---|
| M17B/M18 AI-council calibrated scaleout | **GO** |
| production default enable | **NO-GO** |
| production v1 | **NO-GO** |

- 真实 `/api/v1/ws`：**130 DeepSeek-V4-flash 判题 + 347 点级裁决**；**22 条真实 Qwen3.7 fallback**（强制 primary 失败，100% 成功）。
- **4 模型 AI expert council**（DeepSeek-V4 Prosecutor + Qwen3.7 Semantics + GPT5.5/Codex Chief Architect + Opus4.8 in-session Judge）复核 **40 frontier 点**：council 真实调用 DeepSeek/Qwen 80 + Codex 4；`reviewer_type=ai_expert_council`、`human_reviewed=false`、council 不替代 source。
- 安全全过：false_positive=0、bad_certified=0、source_mismatch=0、official_answer_as_textbook=0、model_vote_as_source=0、council_replaced_source=0、list_partial_auto=0、legacy_equal_rate=1.0、production_write=0、production_default OFF。
- 点级分布：accept 177/reject 106/needs_review 42/partial 22；validator 下调 31（fp 防护）；severe disagreement 24（全 actionable）。
- **40 条 artifact feedback candidate**（rubric_delta 18 + machine_spec_fix 20 + validator_rule_review 1 + drop 1），全停 candidate/work_order，不动 release registry。p50≈2.2s/p95≈3.4s。
- 代码：新增 fat skill 字段无（复用 M17A `runtime_llm_adjudicator`）；新增 `run_luban_runtime_llm_adjudication_scaleout_m17b_m18.py`（council builder + aggregator + tournament + artifact feedback）。**未改 runtime 主链路**。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：M19 production default decision**

1. M19 前置硬证据：大样本 **LLM-vs-ground-truth 准确率 eval**（当前是 council calibration，非绝对准确率）、production 化**异步/超时/限流**、**用户显式授权**小流量 default flip、GPT5.5 全量 council。
2. production v1 仍 **NO-GO**、production default OFF、不发 published registry；**不要**现在 flip default、**不要**回 M11–M17A 旧链路。

---

## 0.18 Canonical update after M19B production default decision synthesis（2026-06-04）

> **本节 supersede §0.17 的"下一步 M19 default decision"和 M19A 的 `DEFERRED_TO_M19_AFTER_M17B` 槽位。M17B 的 DeepSeek live<80 WEAK-GO 缺口已由 M17C 合并补齐；M19B 是当前唯一 production-default decision package。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/production_default_decision_synthesis_m19b_20260604/`

**M19B 三轴 verdict：**
| 轴 | verdict |
|---|---|
| M19B limited production default candidate | **GO**（仅 dry-run / reversible candidate，不代表已执行） |
| production v1 default flip | **NO-GO**（未授权，不执行） |
| canonical learner truth write | **NO-GO**（M18D 仍是 dry-run/guarded candidate path） |

- M17B 原 verdict：**WEAK-GO**，唯一 blocker 是 DeepSeek live 28 < 80；M17B 的 safety/scale/fallback/council evidence 保留。
- M17C 已补齐：M17A 25 + M17B 28 + M17C 27 = **merged DeepSeek live 80**，`m17_scaleout_axis=GO`，safety 全 0、duplicated_paid_calls=0、production_default OFF。
- M18C/M18D Learning Brain 证据保留：real retest proof / canonical write dry-run 均 GO；但 `canonical_truth_written=false`，不得升级为真实 learner truth write authority。
- M19A preflight 仅作为 rollback/observability/cost skeleton 保留；其 `production_default_decision=DEFERRED_TO_M19_AFTER_M17B` 已被 M19B supersede。
- M19B final `/api/v1/ws` release drill：**205 submissions**，覆盖 `qa_ / test_ / operator_`；non-cohort real student blocked；kill switch / malformed registry / provider failure / fallback / rollback 全过；`legacy_equal_rate=1.0`、`production_write_count=0`、`canonical_truth_written=false`。
- M19B 没有重发 live LLM call：模型能力证据来自 M17C merged live=80；M19B release drill 使用 deterministic in-process provider，只验证 default/rollback/guard，不伪造 live provider。
- decision matrix：`shadow_only=GO`、`controlled_cohort_only=GO`、`one_percent_qa_operator_default=GO`、`named_internal_cohort_default=GO`，但均为**需用户显式授权的 dry-run candidate**；`broad_production_default=NO-GO`。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：**

1. 如要执行任何 limited default（1% qa/operator 或 named internal cohort），必须由用户显式授权，并使用 `production_default_config_dryrun_m19b.json` 转为实际配置；默认仍 OFF。
2. production v1 broad default 继续 **NO-GO**，直到完成 production async/timeout/rate-limit hardening、operator live window、成本/延迟 SLO 接入，以及更强外部/human-like 复核授权。
3. canonical learner truth write 继续 **NO-GO**，必须另开 teacher-final / real retest truth-write release gate；不能把 shadow/preview/dry-run 写成 mastery。

---

## 0.19 Canonical update after M19C limited default flip（2026-06-05）

> **本节执行 §0.18 的用户授权 limited default。M19C 只开启 M19B 已批准的可逆 `qa_` / `operator_` limited default，本地 `/api/v1/ws` TestClient 真实路径验证通过；broad production default、canonical learner truth write、production DB write 继续关闭。远端/Aliyun 配置未写入。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/limited_default_flip_m19c_20260605/`

**M19C 三轴 verdict：**
| 轴 | verdict |
|---|---|
| M19C limited default flip | **GO**（local authorized config package + `/api/v1/ws` drill） |
| production v1 broad default | **NO-GO** |
| canonical learner truth write | **NO-GO** |

- 授权：用户已明确授权 M19C limited flip；授权范围只覆盖 M19B `one_percent_qa_operator_default`，默认 cohort 前缀为 `qa_` / `operator_`，`test_` 仅作为 internal cohort/显式回归路径，不扩大为 broad default。
- 实际最小变更：薄 wrapper 增加 env-gated limited default hook：`LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=true` + `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT=qa_,operator_` 时，允许 cohort 在无 request flag 情况下 append `luban_grading_engine_v1_llm_adjudication`；判题 policy 仍由 fat skill `runtime_llm_adjudicator` 承担。
- Live `/api/v1/ws` TestClient drill：**100 submissions**；default-on 覆盖 `qa_` / `operator_`；显式 internal 回归覆盖 `test_`；non-cohort real student blocked；`legacy_equal_rate=1.0`、`production_write_count=0`、`canonical_truth_written=false`。
- Provider drill：DeepSeek-success path 52、Qwen fallback 5、provider failure fail-closed 3；M19C 未重发 live LLM call，模型能力证据仍来自 M17C merged live=80；M20 delta 不进入本轮。
- Safety invariants 全过：false_positive=0、bad_certified=0、source_mismatch=0、official_answer_as_source=0、model_vote_as_source=0、council_vote_as_source=0、list_partial_auto=0、legacy_overwrite=0、kill_switch_works=true。
- Rollback drill：撤 request flag / env kill / registry unavailable 均恢复 legacy-only 或 fail-closed legacy intact；当前 M19C artifact state = **ON**。由于未获远端部署授权，这个 ON 表示本地授权配置包和 TestClient 验证状态，不表示 Aliyun/remote 已写。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：M19D soak monitoring 或 rollback repair**

1. 若进入 M19D，必须只做 limited cohort soak monitoring：p95 latency / fallback rate / failclosed rate / production_write_count / canonical_truth_written / operator stop conditions；不得 broad default。
2. 若任何 safety invariant 非 0，立即执行 rollback repair；不得把 M19C ON 扩大成 production v1 default。
3. canonical learner truth write 仍 **NO-GO**，必须另开 teacher-final / real retest truth-write release gate。

---

## 0.20 Canonical update after M19D limited cohort soak monitoring（2026-06-05）

> **本节监控 §0.19 的 M19C limited default ON 状态，不再次 flip、不扩大 cohort、不写远端/Aliyun、不写 production DB、不写 canonical learner truth。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/`

**M19D 三轴 verdict：**
| 轴 | verdict |
|---|---|
| M19D soak monitoring | **GO** |
| keep limited default ON | **YES** |
| remote/Aliyun deployment authorization review | **GO**（仅授权包评审，不代表已部署） |

- 输入：M19C artifact state = **ON**；default cohort 仍仅 `qa_` / `operator_`；`test_` 只做 explicit regression；broad default 仍 **NO-GO**；canonical learner truth write 仍 **NO-GO**。
- Soak：真实 `/api/v1/ws` TestClient **300 submissions**；cohort_hit=231；non_cohort_blocked=15；DeepSeek-success path=256；Qwen fallback=10；provider failure fail-closed=8。
- Metrics：fallback_rate=0.036496；failclosed_rate=0.029197；latency p50/p95/p99=28.161/33.75/63.293ms；token p50/p95=1200/1200；Learning Brain preview-only=274。
- Safety gates 全过：false_positive=0、bad_certified=0、source_mismatch=0、unsupported_positive=0、legacy_overwrite=0、production_write_count=0、canonical_truth_written=false、non_cohort_default_leak=0、provider_failure_fail_open=0。
- Rollback readiness：env kill / registry unavailable / request flag withdraw 三路径均 state_correct=true、legacy_intact=true；switch-path latency 只按切换路径计，不混入完整 grading latency。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：M19E remote deployment authorization package**

1. M19E 只能做远端/Aliyun 部署授权包评审：列出远端路径、命令、rollback 命令、env/config diff、观测窗口和 stop conditions；未获新授权前不得写远端。
2. broad production default 继续 **NO-GO**；canonical learner truth write 继续 **NO-GO**。
3. 若 M19D safety invariant 在后续 soak 中出现非 0，立即走 rollback repair，不进入 M19E。

---

## 0.21 Canonical update after M22 RAG-vs-Luban-v1 quality benchmark（2026-06-05）

> **本节是「旧 RAG 体系 vs 鲁班评分引擎 v1」的同台 benchmark。未 flip production default、未写远端/DB/canonical truth、未发 registry、未把 M20.2 delta 吸收进 runtime。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/rag_vs_luban_v1_quality_benchmark_m22_20260605/`

**M22 裁决：WEAK-GO**（同 1 批 **210** 真实 `/api/v1/ws` 案例作答 + construction-gold 点级真值，四条线同台；**安全不变量全 0**；但 line A 旧 RAG live 检索不可用 + line C 仅单 provider live，不到 GO）。

- **四条线真实入口**：A 旧 RAG = `RAGService.search`/`rag_search`（`data/knowledge_bases` 空→诚实降级为 retrieval/answer baseline，写 missing_input_audit，**未伪造**）；B M16 = `build_controlled_runtime_payload`；C v1 = 真实 `/api/v1/ws`→`_maybe_attach_v1_llm_adjudication`（**177 条真实 DeepSeek-V4-flash live**，fallback 0/failclosed 0/timeout 0）；D M20.2 = 临时 packet harness，**未进 runtime**。
- **规模**：210 submissions、point decisions B=550 / C=479、6 题型（authority_kind 映射）、每题 10 作答变体、每样本 final disposition。
- **质量（诚实，不 overclaim）**：二元 auto-eligibility 上 **B agreement 0.891 ≥ C 0.812**（C 更保守，recall 0.619<0.767）。C 的价值**不在更高二元一致率**，而在：**evidence_span_valid_rate 0.973**、partial 22/needs_review 57 的细档、可喂 Learning Brain 的证据+解释。两线 **fp=0、accept_precision=1.0**，adversarial 五类全 0。
- **效率**：B p50 **21.7ms / $0**；C p50 **2253ms**/p95 3898/p99 5104，177 调用 ≈145k tokens ≈ **$0.081**（~$0.0005/条）。D 在 C 之上省 **token 19.5% / bytes 18.2%**（packet 压缩；19 个评分 delta 仍是 work-order，未可执行）。
- **职责切分（核心产品结论）**：旧 RAG→retrieval/source expansion/answer baseline（不判分）；M16 deterministic→安全地板+免费即时二元 auto（正确作答下足够）；v1 runtime LLM→粒度判分+evidence+解释+LB 证据（仅在需细档/事件定位/对抗判断时调用，承担延迟与成本）；M20.2 delta→packet 压缩候选，**进下一版 registry 需独立编译里程碑**（非 M22）。

**当前下一步**：保持职责切分现状；不因本 benchmark 改 production default/registry。若要把 M20.2 的 19 个评分 work-order 落地，须先经独立编译里程碑（带 textbook provenance + 安全复测），packet 压缩可优先纳入。详见 §0.20（M19D 当前 runtime 状态）与本节 ledger。

---

## 0.22 Canonical update after M22R RAG baseline + Qwen fallback closure（2026-06-05）

> **补 M22 两个 WEAK-GO 缺口。未 flip default、未写远端/DB/canonical truth、未发 registry、未建第二套 RAG authority、未碰 M20.2 runtime。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/rag_vs_luban_v1_benchmark_closure_m22r_20260605/`

**M22R 裁决：WEAK-GO**（安全全 0；Qwen fallback 已闭环，但旧 RAG live 因本环境 schema 未部署仍 blocked，且修复=远端写被禁）。corrected M22 overall = **WEAK-GO**。

- **任务 A（旧 RAG，按用户纠正走真实 Supabase 链路）**：RAGService/rag_search→SupabasePipeline（read-only PostgREST）。**不再把 `data/knowledge_bases` 空当信号、不自建本地 stub**。结果：Supabase 项目**可达且认证通过**（`/rest/v1/`=200、`/auth/v1/health`=200），但 **RAG schema 未部署**——`kb_chunks` 表 404/`PGRST205`、`match_kb_chunks` RPC 404/`PGRST202`。21 条真实 query 全此错误码（未伪造）。处置=**still_blocked_with_exact_reason**；生产 RAG KB 在另一(production)Supabase 项目，**建表/灌数据=远端写，红线禁止，未做**。RAG 职责定位不变：retrieval/context/source expansion，**不判分**。
- **任务 B（Qwen fallback 闭环）**：强制 DeepSeek primary fail → 真实 **Qwen3.7-plus fallback 43 次**（resume 不重计费已完成调用）。dispositions reject 61/needs_review 14/accept 18/partial 3；evidence_span_valid=0.958；**fp=0、source_mismatch=0**。**DeepSeek vs Qwen**（96 配对点）：auto_agreement=**0.958**、auto 18=18（**tie**，无谁更激进）；latency Qwen p50 4818ms vs DeepSeek 2119ms（**Qwen 慢 ~2.3×**）。**双 provider 全宕 = fail-closed、legacy intact**（no_auto_points、fail_open=false）。**「自然稳定未触发」≠「fallback 不可用」**：M22 本轮 DeepSeek 全成功故未自然触发，本轮强制失败已证 Qwen fallback 真实可用。

**当前下一步**：Qwen fallback 冗余已闭环，无需再补。旧 RAG live baseline 要补实测须在已部署 RAG schema（`kb_chunks`+`match_kb_chunks`）的 Supabase 项目环境进行——本任务边界内（禁远端写）不可恢复。不影响 PR #100 / M19F（均未触碰）。详见本节 ledger 与 §0.21（M22 同台 benchmark）。

---

## 0.23 Canonical update after M22S RAG Supabase authority reconciliation（2026-06-05，只读）

> **纯只读对账。未写 Supabase、未建表、未迁移、未灌数据、未改 production default、未执行 M19F、未新增第二套 RAG authority、未打印 secret。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/rag_supabase_authority_reconciliation_m22s_20260605/`

**M22S 裁决：GO**（找到正确 RAG authority + 精确根因 + 可执行零数据写恢复路径，全部只读证据）。

- **正确 RAG authority（已直连只读确认 + 当场检索成功）**：production RAG 数据在项目 `bsaajvxkbnnnodrvrxct`（RAG/KB v5；另有主 app 项目 `zgupgizexqpwtajvghno`=`DB_URL`）的内部 **`kb_v5` schema**（6 表：chunks/documents/concepts/concept_edges/ingest_runs/__project_marker），检索 RPC `public.search_chunks_v2`（混合 vector+lexical+权威；filter_data_version 默认 2026、filter_doc_types 默认 standard/textbook/lecture/exam；embed=DashScope `text-embedding-v3` dim 1024）。**经 `.env` 已有的 `KBV5_DB_URL` 直连（role `postgres`，对 kb_v5 有 USAGE）调 `search_chunks_v2` 真实返回 3 条教材 chunk——RAG 本就可用。**
- **根因 = transport + 凭证 + 代际**：repo `SupabasePipeline` 走 **PostgREST**，而该项目 API key（`SUPABASE_KEY`=`SERVICE_ROLE_KEY_V5` 同一把非-JWT key）角色对 `kb_v5` 无 USAGE（`42501`）、PostgREST 仅暴露 public/graphql_public；叠加代码仍调 legacy `public.kb_chunks`/`search_kb_chunks`（全仓无 search_chunks_v2）。**正确 transport=`KBV5_DB_URL` 直连**。排除连错项目/缺数据/env 未载/KB 名错。
- **恢复=零数据/表/schema 写 + 零新凭证**：现有 `KBV5_DB_URL` 即可。纯 code-side：RAG 客户端走直连调 `public.search_chunks_v2`（filter_doc_types 从 `SUPABASE_RAG_SOURCES`，dim 1024）+ 更新 `contracts/rag.md`+contract guard test（feature-flag legacy↔v5）。可选：若坚持 PostgREST transport，才需 ops `GRANT USAGE ON SCHEMA kb_v5`（权限授予非数据写）。**禁止**重建 legacy schema（远端写/倒退）。
- **对 production / M19F 无影响**：线上经直连/已授权路径访问 kb_v5，RAG 正常（用户已确认）；问题仅在 dev/benchmark（legacy 分支 PostgREST 路径）。**告警**：本分支 RAG pipeline 与 kb_v5 部署不兼容，部署本分支前须先做 code adapter；修正前本地 PostgREST RAG-live（含 M22T）会复现 42501。

**当前下一步**：eng 做 `KBV5_DB_URL` 直连 → `search_chunks_v2` 的 code-side adapter（凭证已就绪，零数据写，无需等 ops）→ 再跑 **M22T live RAG benchmark**。详见 `direct_db_kb_v5_verification_m22s.json` 与 `rag_baseline_recovery_options_m22s.md`。

---

## 0.24 Canonical update after M24 v0 vs v1 A/B benchmark + KB v5 RAG baseline（2026-06-05）

> **本地 A/B benchmark。未 flip default、未写远端/Supabase/DB/canonical truth、未发 registry、KB v5 adapter 只读且非评分 authority、M20.2 未吸收。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/v0_vs_v1_ab_benchmark_m24_20260605/`

**M24 裁决：GO**（同一批 **134** 真实 `/api/v1/ws` 案例,v0 legacy 与 v1 LLM adjudication 同 turn 同台,**134 条真实 DeepSeek live**,安全全 0）。

- **v0 = legacy `construction_grading_result`**（CaseGradingSkillKernel projected-rubric,关键词/criterion 匹配,full/partial/none,有 rewrite_answer + next_training_signal）；**v1 = `luban_grading_engine_v1_llm_adjudication`**（registry source/spec/list 点 + DeepSeek/Qwen + deterministic validator floor + evidence_span + point 级 LB draft）。
- **安全（决定性）**：对抗变体上 v0 avg_score_ratio=**0.66**（关键词过判,无 validator),v1 avg_auto=**0.0**;v1 **fp_vs_gold=0、source_mismatch=0、validator 拦下 31 个 false positive**。
- **颗粒度**：v1 partial 19 + needs_review 64;v0 partial 0、无 needs_review 档。**解释**：v1 evidence_span_valid=**0.978**（学生原文锚定）vs v0 criterion 文本。**LB 信号**：v1 point 级=1.0 vs v0 submission 级 specific=0.0。
- **代价（已修正延迟归因）**：v0 standalone **~14ms/$0**（确定性,flag-off 测）;v1 p50 **2155ms**、~**$0.0005/条**（≈150× 慢）。注:live A/B 中 v0/v1 同 turn,整 turn 2175ms 由 v1 LLM 主导,非 v0 成本。
- **provider 冗余**：强制 primary fail → **Qwen fallback 20 live**(fp=0)、双挂 fail-closed、legacy intact。
- **RAG baseline（M22S 续作）**：新增 `deeptutor/services/benchmark/kb_v5_readonly_adapter.py`（`KBV5_DB_URL` 直连只读 → `public.search_chunks_v2`,text-embedding-v3 dim1024,read-only 事务硬保护,非 runtime RAG authority）。12/12 问检索成功,avg 5 chunks;retrieval/context baseline,**不判分**。
- **Langfuse**：本地 Docker daemon 未起 + repo 无本地全栈 langfuse compose（只有 Aliyun overlay）+ 现有 pk-/sk- key 不匹配新实例 → 本地 Docker Langfuse **blocked**;按要求写 `langfuse_trace_ledger.jsonl`(134 条 Langfuse 兼容 trace)+ 记录 blocker。

**职责切分**：v0 legacy 保留（免费/即时 projected-rubric,正确作答与简单点足够）;v1 接管（source 签名 + validator 安全地板 + evidence_span + 细档 + point 级 LB,用于对抗/洗稿/需解释/复习信号,承担 ~150× 延迟与 ~$0.0005/条）;KB v5 RAG = retrieval/context,不判分。**v1 安全全 0,作为受控 cohort overlay 支持继续 M19F limited（仍需用户授权,不在本任务执行）。**

---

## 0.25 Canonical correction: v1 must cover objective questions, and historical-question lookup is upstream context authority（2026-06-05）

> **本节补正 §0.24 的适用范围。M24 A/B 证明的是案例题 v1 LLM adjudication 明显优于 v0；它不代表鲁班评分引擎 v1 只做案例题。选择题/判断题/多选题必须进入 v1，但走 objective deterministic lane；历史真题识别与标准答案 lookup 是上游 canonical question context authority，不与 v1 冲突。**

### 0.25.1 全题型 v1 分层

鲁班评分引擎 v1 的最终形态是 **全题型评分与学习闭环引擎**，不是单一案例题引擎：

| 题型 lane | 评分 authority | LLM 角色 | deterministic 角色 | Learning Brain 输出 |
|---|---|---|---|---|
| **objective_choice**（单选/多选/判断） | canonical `answer_key` / option metadata / official question bank | 解释错因、识别混淆概念、组织教材/RAG 依据、生成 next action | 判对错、集合比较、顺序无关多选、部分给分 policy、答案 key hash | objective evidence event、错因标签、concept gap、复测计划 |
| **case_question**（案例主观题） | compiled rubric + source/spec/list authority + runtime LLM adjudication | 理解学生自然语言、点级 accept/partial/reject/needs_review、evidence_span、reasoning summary | validator 防 false-positive/source laundering/list partial auto、fail-closed | point-level claim draft、review queue、study card |
| **calculation/spec** | machine-checkable spec / formula / expected value / unit | 解释计算路径、识别步骤性错误 | 数值容差、单位、off-by-one、contradiction guard | calculation gap、retest proof |
| **retrieval/context**（RAG/KB v5） | KB v5 source chunks /教材/规范/题干事实 | 查证、引用、扩展解释 | provenance/hash/read-only guard | citation refs、学习资料建议 |

关键结论：**选择题不需要 LLM 判对错，但需要 LLM 做解释、诊断、知识关联和个性化学习建议。** 对错事实由 `answer_key` 唯一负责；LLM 不能临场改标准答案。

### 0.25.2 Historical question lookup 与 v1 不冲突

当用户问的是历史真题、真题答案、某年某题解析、或直接提交真题作答时，系统应先做 **HistoricalQuestionResolver / CanonicalQuestionContext**：

```text
user input
  -> question identity resolver
  -> canonical question_id / year / paper / section / stem / options / answer_key / rubric / source_refs
  -> lane selection
      objective_choice -> deterministic grader + LLM explanation
      case_question -> runtime LLM adjudicator + validator
      retrieval_only -> RAG/KB v5 explanation, no grading
  -> Learning Brain evidence / next action
```

这不会和 v1 冲突，原因是 authority 不同：

| 业务事实 | 唯一 authority | v1 是否可覆盖 |
|---|---|---:|
| 这是不是某道历史真题 | `HistoricalQuestionResolver` + question bank index + stable question_id | 否 |
| 标准答案/选项 key 是什么 | canonical `answer_key` / official question bank / signed truth artifact | 否 |
| 主观题某采分点是否命中 | v1 runtime LLM adjudicator + deterministic validator + compiled rubric | 是，在对应 lane 内 |
| 教材/规范依据是什么 | KB v5 / source compiler / source refs | 否，只消费 |
| 学员是否掌握/进步 | Learning Brain claim gate + retest proof | 否，只产 evidence/proposal |

因此，**历史真题 lookup 是 v1 的上游上下文，不是第二套评分器。** 它保证“题目是谁、标准答案是什么”先稳定下来；v1 再决定“学生这次回答得怎样、错在哪、下一步怎么学”。

### 0.25.3 对知识编译与采分点编译的新增要求

现有 knowledge/rubric compiler 不能只围绕案例题采分点继续扩张，必须补三类 artifact：

1. **Historical Question Index**
   - `question_id`、年份、卷别、题型、题干 hash、选项 hash、答案 key hash、source refs、版本/supersession。
   - LLM 可用于去重、题干变体归一化、年份/题号抽取、疑似同题合并候选；deterministic gate 负责 hash、schema、冲突检测和 release signing。

2. **Objective Answer Key Compiler**
   - 单选/多选/判断的 `answer_key`、option metadata、multi-select set policy、partial credit policy（如允许时）、解析 source_refs。
   - official answer 只能作为 answer-key seed；进入 release 前必须经过题库 authority / source provenance / hash signing。

3. **Unified GradingPacket Builder**
   - 对 objective 题，packet 必须包含 `canonical_question_context + answer_key + selected_option + learner context + explanation sources`，但不让 LLM 决定对错。
   - 对 case 题，packet 保持 §0.12 的 source/spec/list/rubric/student_answer scoped context。
   - 对 retrieval-only 问答，packet 输出 citations/explanation，不生成 grading decision。

### 0.25.4 M25 下一步：Objective Question Integration + Historical Resolver

M25 是 §0.25 的落地任务，不取代 M19F/M24，但补齐 v1 的全题型边界：

1. 实现/确认 `HistoricalQuestionResolver`：从用户输入和题目上下文识别历史真题，返回 canonical question context；未知题必须 fail-open 到普通问答/RAG，不伪造真题身份。
2. 实现 objective deterministic grader：单选/多选/判断按 answer_key 判分，LLM 只解释，不判对错。
3. 把 objective evidence event 接入 Learning Brain：错因、知识点、source refs、next action、retest plan。
4. 做 v0 vs v1 objective benchmark：正确/错误/多选漏选/多选多选/近义解释/历史真题问答案；false_positive=0、answer_key_override=0、LLM_changed_key=0。
5. 更新 runtime supply bundle：objective answer-key artifacts 与 case registry 分 namespace，均带 manifest hash/rollback。

**红线**：不要让 RAG、LLM、model vote、AI council 改写历史真题标准答案；不要把 objective answer-key compiler 和 case rubric compiler 混成一个 mutable registry；不要为选择题新增第二条聊天入口。

### 0.25.5 Open-world teaching mode：不在题库也必须能回答

> **硬纠偏**：`HistoricalQuestionResolver` 未命中时，系统只能说“这不是已识别真题 / 无 canonical answer_key”，**不能**说“不能回答”。鲁班 v1 是智能教学与评分系统，不是题库查表器。

题库外/未识别问题的正确行为：

```text
unknown / not-in-bank user query
  -> fail-open to TutorBot / RAG / runtime LLM teaching answer
  -> answer with uncertainty label + citations/provenance when available
  -> if user is submitting an answer, produce diagnostic draft / needs_review, not official score
  -> if repeated/high-value, create candidate artifact/work-order for compiler
```

允许：

- 用 DeepSeek/Qwen 基于用户问题、KB v5、教材/规范/RAG 上下文做开放式讲解。
- 对非题库作答给出“诊断性反馈 / 学习建议 / 可能得分点”，但标记为 `unverified_diagnostic` 或 `needs_review`。
- 把新题、变体题、用户自带题干送入 LLM-assisted compiler，生成 `question_candidate` / `rubric_candidate` / `source_candidate`，进入后续签发流程。

禁止：

- 未识别为真题时冒充“官方真题答案”。
- 没有 canonical `answer_key` / signed rubric 时给正式 auto score。
- 把 open-world LLM 回答写成 canonical question bank truth。
- 因题库未命中而拒绝教学回答。

产品口径：**题库命中提升确定性和评分可信度；题库未命中仍应体现智能体能力，只是降级为开放式教学/诊断，不升官方答案或自动评分 authority。**

Nexus 口径：**知识编译扩大能力边界，而不是缩小能力边界。** 每次题库外问题、变体问法、非标准作答、RAG 新证据，都应成为 compiler 的候选输入：LLM 负责抽取/归纳/对齐/提出候选 artifact，deterministic gate 负责签发或拒绝。这样系统越用越强，而不是越编译越狭窄。

---

## 0.26 Canonical goal reset: authority-aware open-world expert system（2026-06-06）

> **本节 supersede 本文所有可能把 v1 误读成“题库闸门 / registry 查表器 / token-saving grader”的表述。后续 agent 必须先读 §0.26，再执行 M25/M26 之后的任务。**

### 0.26.1 一句话目标

鲁班体系的目标是：

```text
鲁班评分引擎 = 诊断仪
  -> 本次作答哪里对、哪里错、为什么错、证据在哪里、风险在哪里

Learning Brain / GBrain = 长期主治医生
  -> 学生长期画像、弱点演化、遗忘/复测、下一步怎么教

Nexus-style Knowledge Engine = LLM 的领域工作台
  -> 把教材/规范/真题/采分点/错因/历史证据编译成细颗粒、可溯源、可裁剪的上下文，让 LLM 更强，而不是让 LLM 更窄
```

因此，本计划的最高原则是：

> **Authority-aware, not authority-limited.**

有权威时给正式评分；无权威时不能伪造正式评分，但必须继续提供建筑实务领域的高质量解释、诊断、追问、练习建议和 compiler candidate。题库未命中是降级信号，不是拒答理由。

### 0.26.2 三种 runtime 模式

| 模式 | 触发 | 系统必须做什么 | 系统禁止做什么 |
|---|---|---|---|
| **Official grading mode** | 命中 canonical question / signed answer_key / signed rubric / release_candidate registry | 给正式或受控评分、采分点命中、得分、evidence_span、blocked_reason、Learning Brain evidence draft | 不能让 LLM/RAG/model vote 改写标准答案或 signed rubric |
| **Open-world diagnostic mode** | 题库未命中、用户自带题、变体题、开放式问答、证据不足 | 用 DeepSeek/Qwen + KB v5/RAG + compiled context 给非正式诊断、知识讲解、可能采分点、下一步练习，并标 `unverified_diagnostic` / `needs_review` | 不能拒答；不能冒充官方真题答案；不能给正式 auto score |
| **Compiler feedback mode** | open-world 高价值问题、重复未命中、review queue、LLM/council disagreement、RAG 新证据 | 生成 `question_candidate` / `answer_key_candidate` / `rubric_candidate` / `source_candidate` / `work_order`，进入 LLM-assisted compiler + deterministic release gate | 不能把 candidate 直接喂给 production runtime 当 release truth |

### 0.26.3 单一 authority 分工

| 业务事实 | 唯一 authority | LLM 角色 | deterministic 角色 |
|---|---|---|---|
| 这是不是历史真题 | `HistoricalQuestionResolver` / question bank index | 识别题干变体、年份题号候选、去重候选 | stable question_id、hash、冲突检测、release signing |
| 客观题标准答案 | canonical `answer_key` / governed question registry | 解释为什么选/不选、定位知识点和错因 | 判对错、多选集合、true/false 归一、tamper fail-closed |
| 案例题采分点命中 | runtime LLM adjudicator + signed rubric/source/spec/list + validator | 理解学生自然语言、给 accept/partial/reject/needs_review、证据 span | source/spec/list gate、false-positive guard、unsupported-positive fail-closed |
| 教材/规范/题干证据 | KB v5 / source compiler / source refs | 检索、组织、解释、生成 source candidate | provenance、content_hash、read-only guard、source laundering guard |
| 学生长期画像 | Learning Brain claim lifecycle + evidence ledger + retest proof | synthesis、dream-cycle lint、下一步建议候选 | append-only evidence、claim gate、cross-user/subject leak guard |

### 0.26.4 编译层必须服务 agent，而不是只服务 registry

后续知识/采分点/证据编译不能只产“能不能发布 registry”的离线报告，必须产出 runtime 可消费的 **Compiled Context Pack**（命名可落为 `LubanContextPack` / `CompiledContextService`，具体实现前再锁定）：

```text
raw evidence
  -> LLM compiler workers
  -> candidate artifacts
  -> deterministic validators
  -> signed release artifacts
  -> Compiled Context Pack Builder
  -> TutorBot / DeepQuestion / RAG / Runtime GradingPacket / Learning Brain
```

最低字段要求：

- `question_context`：question_id、题型、stem/options、answer_key/rubric availability、status。
- `source_context`：KB v5 / 教材 / 规范 / 题干事实 / external refs，带 provenance/hash。
- `rubric_context`：采分点、required_terms、list/spec/calc policy、risk flags。
- `learner_context`：PersonalizationContextPack、recent evidence、active training intent。
- `diagnostic_policy`：official_score_allowed、unverified_diagnostic_allowed、needs_review_reason、candidate_work_order。
- `budget_policy`：runtime 只给 LLM 看本次最有价值的上下文；token efficiency 是约束，不是目标。

验收标准：同一份 compiled context 必须能被 TutorBot 问答、案例题评分、选择题解释、RAG 引用、Learning Brain next action 复用；禁止每个 surface 自己拼一套上下文。

### 0.26.5 当前真实差距

截至 2026-06-06，现状应诚实表述为：

- **案例题 v1 LLM adjudication 已证明比 v0 更安全、更细颗粒**，但主要覆盖 signed/compiled registry 内的 case lane。
- **objective lane 已有 candidate/real-source candidate 基础**，但 full governed question registry signing 仍未完成，不能把 candidate 当 production answer-key release。
- **KB v5 RAG 可作为 retrieval/context authority**，但它不判分；需要变成 Compiled Context Pack 的稳定输入，而不是只在 benchmark 里使用。
- **Learning Brain 已有 evidence/claim/PCP/dream-cycle preview 和 dry-run proof**，但 canonical learner truth 仍不能自动写；要保持 evidence-first。
- **知识/采分点/证据编译尚未全量产品化**：已有 scripts/artifacts/M20 delta，但还没有统一的 full-scope continuous compiler → signed context pack → runtime consumer 闭环。
- **open-world diagnostic lane 还不够强**：题库外可以回答的原则已定，但需要真实微信/TutorBot 链路验证“任意建筑实务问题不拒答、能诊断、能产 candidate、能保护 authority”。

### 0.26.6 下一阶段 M26 主线：Compiled Context + Open-world Diagnostic Closure

执行计划已单独固化为 [2026-06-06-luban-m26-compiled-context-open-world-execution-plan.md](2026-06-06-luban-m26-compiled-context-open-world-execution-plan.md)。后续 agent 执行 M26 时以本节目标为 authority，以该执行计划的任务拆分、专家分工、测试矩阵和验收标准为操作手册。

M26 不应再是“再跑一个 registry gate”。它必须围绕系统能力闭环：

1. **Context Pack Builder**：把 historical question、objective answer_key、case rubric/spec/source、KB v5、learner PCP 组织成统一 scoped context。
2. **Open-world Diagnostic Runtime**：题库未命中时，TutorBot/deep_question 能基于 context + RAG + LLM 给建筑实务诊断，明确非正式，不拒答。
3. **Compiler Feedback Loop**：open-world 诊断结果、未命中题、review queue、RAG 新证据必须生成 candidate/work-order，进入 LLM-assisted compiler。
4. **Full-scope Compiler Inventory**：按 objective / case / calc / source / learner evidence 五类列出全量覆盖率、release 状态、缺口和下一版 signing plan。
5. **Learning Brain Integration**：official grading 和 unverified diagnostic 都能产 evidence；但只有 gate 通过的证据才能升 claim/canonical truth。
6. **A/B 与真链路验收**：用微信 TutorBot / `/api/v1/ws` 真链路覆盖题库内、题库外、历史真题、变体题、开放问答、作答批改、复测六类场景。

M26 GO 门：

- unknown/not-in-bank 场景拒答率 = 0（除安全/无关问题）。
- official_score_laundering = 0；answer_key_override = 0；source_laundering = 0。
- open-world diagnostic 每条都有 uncertainty/status label。
- candidate/work-order 生成率对高价值 unknown ≥ 90%。
- compiled context 被至少 3 个 surface 消费：TutorBot、runtime grading、Learning Brain。
- Learning Brain evidence coverage ≥ 0.95，shadow/candidate 不升 mastery。
- 与 v0 / old RAG / v1 official mode 有同台质量、延迟、成本和满意度对比。

### 0.26.7 M26 执行结果（2026-06-06，hermetic GO）

> **本节只追加 M26 落地结果，不改写 §0.26.1–§0.26.6 目标。** Canonical ledger：`artifacts/luban_grading_artifacts/compiled_context_open_world_m26_20260606/`。

实现（全部带 hermetic pytest）：

| 能力 | 落地 | 文件 |
|---|---|---|
| Compiled Context fat skill | `LubanContextPack` + 唯一组装入口 `build_luban_context_pack` / `build_pack_from_question_context`，6 个 context block + provenance + 确定性 `diagnostic_policy` | `deeptutor/services/construction_grading/compiled_context.py` |
| 3 surface 消费同一 pack | TutorBot(`deep_question_adapter`)、runtime grading(`objective_runtime_adapter`)、Learning Brain(`learning_evidence.build_learning_evidence_from_context_pack`) 都附带同一 `schema_version=luban_context_pack.v1`，wrapper 不再各拼上下文 | 三处 surgical 接入 |
| KB v5 runtime RAG | provider 注册 + config 选择 + 只读直连 `public.search_chunks_v2`，`source_table=kb_v5.chunks`，fail-closed；RAG 不判分 | `rag/pipelines/kbv5.py`、`rag/factory.py`、`config/knowledge_base_config.py`、`contracts/rag.md` |
| objective governed release_candidate | 只读 `questions_bank`（live 走 `QUESTIONS_BANK_DB_URL`，缺则 hermetic fixture + 精确 live blocker）→ validate → sign，状态 `release_candidate`（非 published），tamper fail-closed，namespace 独立 | `objective_governed_registry_extractor.py` |
| open-world diagnostic | 题库外不拒答；LLM 不可用降级模板诊断；输出 `status/uncertainty/evidence_refs/likely_scoring_dimensions/next_practice/candidate_work_order`，不给正式分 | `open_world_diagnostic.py` |
| compiler feedback | candidate/rejected/work_order ledger，独立 namespace，source/answer-key laundering fail-closed（rag/model/council vote 不能成 answer_key） | `compiler_feedback.py` |
| Learning Brain | official/open-world 都产 evidence draft；只有 signed official 允许 claim 提案；candidate/shadow/open-world 保持 preview，不升 mastery，不写 canonical truth | `learning_evidence.py` |

硬不变量（`safety_invariant_report_m26.json`，全部达标）：拒答率 0；official_score_laundering / answer_key_override / source_laundering / model_vote_as_source / council_vote_as_source / rag_chunk_as_answer_key / candidate_used_as_release_truth / list_partial_auto / false_positive / source_mismatch / production_write_count / shadow_or_candidate_promoted_to_mastery = 0；canonical_truth_written=false；open-world 全标签且无正式分；high_value_work_order_rate=1.0；three_surface_single_schema=true；LB evidence coverage=1.0；governed tamper fail-closed=true。

**verdict=GO（hermetic only）。** 仍 OUT OF SCOPE 且需单独授权：production default flip、published registry、canonical learner-truth write、远端/DB 写。Live blocker（未伪造）：KB v5 live retrieval 需 `KBV5_DB_URL`+`DASHSCOPE_API_KEY`；governed objective live 需 `QUESTIONS_BANK_DB_URL` 只读 + 列投影确认；A/B 模型质量/token 成本需 DeepSeek/Qwen creds。

runner：`scripts/run_luban_compiled_context_open_world_m26.py`、`scripts/run_luban_m26_ab_and_real_chain_qa.py`。

### 0.26.8 M26 Live Closure 结果（2026-06-06，真实链路 GO）

> **本节把 §0.26.7 的 hermetic GO 升级为真实链路裁决；只追加 live 证据，不重做 hermetic 模块。** Canonical ledger：`artifacts/luban_grading_artifacts/m26_live_closure_20260606/`。runner：`scripts/run_luban_m26_live_closure.py`（全只读，每 stage 失败软记 blocker，不伪造 live）。

四个 live gate **全部 GO**（`go_no_go_m26_live.json`）：

| Gate | 证据 | verdict |
|---|---|---|
| KB v5 live retrieval | 只读 `KBV5_DB_URL` + DashScope 1024 维 embedding + `search_chunks_v2`，5/5 query 返回真实 `kb_v5.chunks` 教材片段，write_count=0 | GO |
| questions_bank governed live | 只读 `DB_URL` 的 `public.questions_bank`（objective 总量≈2659），抽样 600 行 extract→validate→sign，count=600(>62)、conflict=0、rejected=0、answer_key_override=0、rag_chunk_as_answer_key=0、status=release_candidate、published=false、tamper fail-closed=true | GO |
| live LLM | DeepSeek 主路 live=22(≥20)、强制 Qwen fallback live=10(≥10)、false_positive=0、source_mismatch=0、official_answer_laundering=0、p50≈2341ms | GO |
| 真实 /api/v1/ws QA | 6 场景经 TestClient→`/api/v1/ws`→TurnRuntime→DeepQuestionCapability 真实链路；open-world 拒答=0、canonical_truth_written=0、compiled_context 在 objective/case/historical 4 个 grading turn 命中 `luban_context_pack.v1` | GO |

**hermetic 与 live 的差异 / 诚实缺口（未 overclaim）**：① questions_bank 是只读抽样 600（总量≈2659），全源签名为 follow-up，非 blocker；② ~~live /api/v1/ws 的 open-world prompt 尚未接入 live WS followup~~ **【2026-06-08 更正：已闭合】** 富诊断 `open_world_diagnostic.py`（status/uncertainty/evidence_refs/work_order）已由 **M27（§0.26.9）经 `deep_question.py::_attach_open_world_diagnostic`（4th compiled-context surface）接入 live `/api/v1/ws` followup 并流式下发**；集成测试 `tests/integration/test_luban_m27_open_world_ws_integration.py` 断言真实链路：open-world followup 带 `compiled_context + open_world_diagnostic`（refusal=0），in-bank/resolved followup 只带 context 不带 open-world 块。③ ~~compiled_context 在 grading path 命中、open-world followup path 未挂~~ **同②已闭合**：followup 为第 4 个 compiled-context surface，按 `official_score_allowed/status` 路由（resolved→只 context；unresolved→context+open-world）。

production default flip / published registry / canonical learner-truth write / 远端·DB 写仍 OUT OF SCOPE，需单独授权（本轮 production_write_count=0、remote_write=0、default_flip=0、published_registry=false、canonical_truth_written=false）。

### 0.26.9 M27 Open-World Diagnostic Live Integration 结果（2026-06-06，真实链路 GO）

> **本节闭合 §0.26.8 标注的剩余 live 缺口（open-world 富诊断未接入 live WS followup）；只追加结果。** Canonical ledger：`artifacts/luban_grading_artifacts/open_world_diagnostic_live_integration_m27_20260606/`。runner：`scripts/run_luban_m27_open_world_live_integration.py`。

**根因（root-cause-debugging）**：`DeepQuestionCapability._emit_followup_result` 是题库外建筑实务问题的落点，但没有 open-world 分支，也从不消费 `open_world_diagnostic`/`compiled_context` fat skill——live followup 给的是无标签、无 schema 的答案（M26 的"43 字短答"另是 WS smoke harness 用 fake FollowupAgent 的伪影，非生产拒答）。

**修法（thin wrapper / fat skill，非加 fallback）**：① fat skill `open_world_diagnostic.py` 加 `diagnosis_override`（runtime 已生成的真实 LLM 答案由 fat skill 结构化，不重复调模型，provider_used=`caller_supplied_runtime_llm`）+ `to_unified_schema()`（answer/diagnostic_status/uncertainty/evidence_context/next_action/work_order_if_needed）。② wrapper `deep_question.py` 新增 module helper `_attach_open_world_diagnostic`（只 route/append）：挂 `compiled_context`（第 4 个 surface），非可解析的建筑实务 prompt 再附 open-world 统一 schema。未新增第二套 WS、未新增第二套 RAG authority、未让 RAG/official_answer/model_vote 变 answer_key。

**真实 /api/v1/ws verdict=GO**（`go_no_go_m27.json`）：`live_route_trace_m27.json` 显示 objective/case/historical→`governed_grading_authority`，open_world→`open_world_diagnostic`；`compiled_context_surface_matrix_m27.json` 显示 objective/case/historical/open_world/learning_brain **五面同消费 `luban_context_pack.v1`**（single_schema=true）；open-world 拒答率=0、全 labeled、no formal score、no official answer claim、work_order=3；official_score_laundering/answer_key_override/source_laundering/rag_chunk_as_answer_key/model_vote_as_source/candidate_used_as_release_truth/production_write_count/remote_write/default_flip=0、published_registry=false、canonical_truth_written=false、LB preview_only=true。回归 0 破坏（case/objective grading、legacy followup、deep_question/learner_state 全绿）。

**诚实 nuance**：WS smoke harness 用 fake FollowupAgent（短答），生产为真 LLM；M27 加的是**与 provider 无关的结构化**（fat skill 给 runtime 产出的任意答案打标签）。production default/published registry/canonical truth/远端写仍 OUT OF SCOPE。

### 0.26.10 Master-Plan Completion Closure + Canonical Reconciliation（2026-06-06，统一裁决=WEAK-GO）

> **本节是全计划 canonical reconciliation：消解"我方 GO（M26/M27）"与"并行红队 NO-GO（64 场景 acceptance oracle）"的冲突，只留一个 verdict。** Ledger：`artifacts/luban_grading_artifacts/master_plan_completion_closure_20260606/`。runner：`scripts/run_luban_master_plan_completion_closure.py`（全只读，真实 `/api/v1/ws`）。

**红队 NO-GO 的两个真实根因 + 处置**：
1. **client-answer-key laundering（已修）**：并行红队 adversarial 探针发现——客户端在 `followup_question_context.correct_answer` 注入答案，deep_question 评分路径就给 `authority=construction_grading` 的官方满分 + writeback（`official_score_laundering=3`）。根因=`_recover_missing_mcq_authority` 只要 inbound context 带 `correct_answer` 就标 `authority_source=active_object` 当权威，从不查 governed 源（deep_question 运行时根本未绑定 governed answer_key）。**修法（最小 additive，authority discipline）**：`deep_question_adapter._stamp_compiled_context_and_authority` 按 pack 的 `official_score_allowed` 给 result 盖章——未 governed 的答案标 `release_truth=false` / `registry_status=unresolved` / `answer_key_authority=context_supplied_unverified` / `official_release_score=false`，**分数仍 formative 显示（不破坏 UX/测试），但不再被洗成 release-truth**。真实 `/api/v1/ws` 复现确认闭合（`official_score_laundering=0`）。
2. **transport_error(41)（oracle driver 伪影）**：红队 oracle 自带 WS driver 对 41/64 场景报 transport_error；本收口用既有 TestClient 真链路驱动 objective/case/historical/open-world/variant 全类别，**transport_errors=0**——证明那是 oracle driver 限制，非产品拒答。其余 blocked：`requires_release_registry(14)`、`requires_live_llm(6)` 为预期 blocker（合成场景无 server-bound signed key / 需 live 裁决，M26 live 已证）。

**统一 canonical verdict=WEAK-GO**（`go_no_go_final.json`，safety_clean=true）：诊断/formative 教学系统 **live 且安全（GO）**——open-world 拒答率=0、laundering=0、五面同 `luban_context_pack.v1`、case LLM 裁决+validator、KB v5 retrieval、LB preview。**官方 release-truth objective 评分 + production default + published registry + canonical learner truth 仍 NO-GO**——in-bank objective 分数当前为 formative（governed answer_key 尚未接入 runtime），且 production/publish/canonical/远端需用户单独授权。Live LLM fallback 新鲜证据：DeepSeek 716ms + Qwen 1459ms 真答案（规模引用 M26 live 22+10）。v0/v1 质量引用 M24（134 样本：对抗 v0 过判 0.66 vs v1 auto 0.0、validator 拦 31 fp、evidence_span 0.978）。

**剩余唯一工程主线**：把 governed questions_bank answer_key 接入 deep_question objective 评分，使 in-bank 分数从 formative 升为 release-truth；此前 production default 锁死。**pre-existing 测试隔离脆弱**（m16 legacy append-only 跑在 submission_grading 前会泄漏 monkeypatch 状态致后者 writeback=0）经 HEAD worktree 证为 committed 既有问题（非本轮引入），各测试单独均过，记此 FINDING 不在本轮 file-family 内修。

### 0.26.11 F1 加固 + M30 Full Knowledge Compiler Release Candidate（2026-06-06，release_candidate=GO）

> **先清前置闸（F1），再做 M30 全量知识编译；本轮上限 release_candidate，不 publish/production/canonical。** Ledger：`artifacts/luban_grading_artifacts/full_knowledge_compiler_release_candidate_m30_20260606/`。runner：`scripts/run_luban_full_knowledge_compiler_m30.py`。

**F1 加固（清闸）**：pre-landing review 发现的 client-answer-key laundering 残留洞——`build_pack_from_question_context` 从 client 可控的 `registry_status` 推导 `official_score_allowed`，注入 `registry_status=release_candidate/published` 可翻 `release_truth=True`（live 经 normalization strip 不可利用，但 adapter 自身未加固）。修法：`build_pack_from_question_context` 新增 `governed_registry_status` 参数（默认空），**忽略 context 供的 registry_status**，只接受可信 server 调用方显式传入；server-resolved 权威走 `build_luban_context_pack`。验证：注入 release_candidate/published 经 direct + 真实 `/api/v1/ws` 均 `release_truth=False`，formative 分数保留；construction_grading 272 回归 0 破坏 + 新增对抗回归测试。

**M30 编译（LLM 组织候选，deterministic gate 签发 truth）**：
| Lane | 结果 | status |
|---|---|---|
| objective 全量 | 只读全量 `questions_bank`（input 2655）→ 签 **2640** governed answer_key（rejected 14 + conflict 1，**未静默修**），official_answer 仅 seed/corroboration | release_candidate（非 published） |
| source | KB v5 只读 30 chunk refs（stable_source_id/locator/hash/taxonomy），retrieval/context only 不做 answer_key | release_candidate |
| case rubric | release_candidate registry 70 点 authority partition（textbook/logic/calc/list_full signable；external/review_only→work_order；calc/list deterministic validator） | release_candidate |
| M20 delta | 122 输入分类 release_candidate/staged_delta/work_order，rag/model/council vote→work_order，无 runtime impact | release_candidate |
| manifest | `compiled_knowledge_registry.v2`，7 block 可被 runtime packet builder 消费，rollback pointer | release_candidate |

硬不变量（`safety_invariant_report_m30.json` 全达标）：objective full=2640（≥2000）、conflict 不静默、source_laundering/answer_key_override/model_vote_as_source/rag_chunk_as_answer_key/official_answer_as_source/candidate_used_as_release_truth/list_partial_auto/false_positive/source_mismatch/production_write_count=0、tamper_fail_closed=true（三 lane）、laundering_origins_blocked=true、rollback_pointer 存在、published_registry=false、production_default_connected=false、canonical_truth_written=false、all_lanes_release_candidate=true。runtime_consumption_projection 证 signed governed objective→release-grade pack（official_score_allowed=true，但**运行时绑定是下一里程碑，未 flip**）。**verdict=GO（release_candidate scope）**。为何无 publish/production/canonical：本里程碑设计上限即 release_candidate，runtime 绑定 + publish + canonical 写需单独 release gate 与授权。

### 0.26.12 M30R Canonical Knowledge Compiler Reconciliation（2026-06-06，WEAK-GO，canonical pointer）

> **single authority 收口**：M30 出现 3 个并行变体，本节只读 reconcile 出唯一 canonical，不重编译、不改 runtime、不 publish。Ledger：`artifacts/luban_grading_artifacts/m30_canonical_reconciliation_20260606/`。

**唯一 canonical M30**：`full_knowledge_compiler_release_candidate_m30_20260606/compiled_knowledge_registry_manifest_m30.json`，schema `compiled_knowledge_registry.v2`，`registry_content_hash=9395cacc060fe480…`，producer `scripts/run_luban_full_knowledge_compiler_m30.py`（objective 2640/conflict 1/source 30/case 70）。**变体 disposition**：A=CANONICAL；B(`knowledge_compiler_release_candidate_m30_20260606`，schema `crosscheck.v1`)=AUDITOR-ONLY（其 `authoritative_m30_verification` 指向 A 并 concur 同 hash，自签 hash `49d85772…` 非 authority）；C(`…_auditor_readonly`)=AUDITOR-ONLY（独立 re-run hash `36fcaaced…`）。**不用局部 GO 覆盖总 GO**：A 的 release_candidate-scope GO 不抬升 §0.26.10 whole-plan WEAK-GO；B 的 WEAK-GO（compiler-layer toward production）与之一致。safety 全清（含 `client_supplied_answer_key_release_truth=0`、tamper_fail_closed=true）。

**M30R verdict=WEAK-GO**：单一 canonical + safety + runtime_binding_input_contract 均 done；唯一 blocker=**canonical manifest 记了 2640 records 的 hash，但全量 signed records 未持久化为 tracked 可加载 bundle（只存 manifest+20 行 sample），独立 live 抽取非 bit-reproducible**。**M31 step 0**：把全量 2640 signed objective records 持久化为 tracked runtime supply（recompute objective content_hash == `672ff9a653adf2d0…`），或 pin 可复现抽取；**M31 只能消费 canonical pointer，禁止扫 artifact 目录猜**。一句话：M31 runtime-binding release gate 可**准备**但 step-0 持久化前**不可开始**。

---

### 0.26.13 M31 Governed Objective Runtime Binding（2026-06-06，runtime-binding release gate=GO）

> **本节落地 §0.26.10 标注的「剩余唯一工程主线」+ §0.26.12 的 M31 step 0：把 M30 签发的 governed objective release_candidate registry 真正绑进运行时，使题库内 objective 分数从 formative 升为 CONTROLLED release-truth。上限=受控 cohort release-truth；不 publish、不翻 production default、不写 canonical learner truth、不写远端/DB（仍需单独授权）。** Ledger：`artifacts/luban_grading_artifacts/governed_objective_runtime_binding_m31_20260606/`。runner：`scripts/run_luban_m31_governed_objective_runtime_binding.py`。tracked signed bundle：`deeptutor/services/construction_grading/runtime_supply/v3_objective_records_released_m31/`（`objective_answer_key_release_candidate_m31.json` + `canonical_pointer_m31.json`）。

**Step 0 闸已清（§0.26.12 的「非 bit-reproducible」担忧被证伪）**：只读 `DB_URL` 全量抽取 `public.questions_bank`（input 2655）经 `full_knowledge_compiler.compile_full_objective_release_candidate` 编译，**两次抽取确定性一致**且 objective `content_hash == 672ff9a653adf2d00b6501b4d6934e836b34b5d37608ad4d3169d672b41c1bdd`——**精确命中 M30 canonical hash**。全量 2640 signed records 已持久化为 tracked runtime supply（coverage=`full_2640_canonical_match`），canonical pointer pin 该 hash。运行时只读这份 tracked bundle，**绝不扫 artifact 目录**。

**绑定（thin wrapper / fat skill，未新增 WS / registry / 第二套 learner memory）**：
- fat skill `objective_runtime_adapter.py` 新增 `_governed_index`（只读 tracked v3 bundle + pointer，**四道闸全过才信**：`verify_lane_bundle` 内部一致性 → status=`release_candidate` 且非 published → **pinned content_hash 与 pointer 一致**（keyless 签名只证一致性，信任边界=tracked 路径+pinned hash）→ namespace 硬编码校验）+ `_governed_payload`（answer_key 只取签发 record；release 授权**仅**经 `build_pack_from_question_context(governed_registry_status="release_candidate")` 这一 F1 加固 seam，client 供的 registry_status 无法翻 `official_score_allowed`；LLM 不判对错，objective 100% 确定性）+ 独立入口 `build_governed_objective_payload`（governed 命中→release-truth；未命中/篡改→fall through 到既有 candidate→open-world，**M25-B candidate lane 零改动、非全局 fail-closed**）。
- thin wrapper `deep_question.py` 新增 `_maybe_attach_m31_governed_objective`（append-only，只挂 `luban_grading_engine_m31_governed_objective`，绝不碰 `construction_grading_result`）：flag `grading_engine_m31_governed_objective` + env kill `LUBAN_M31_GOVERNED_OBJECTIVE_ENABLED` + cohort `LUBAN_M31_GOVERNED_OBJECTIVE_COHORT`（base `qa_/test_/operator_`），production default OFF。
- `turn_runtime.py` `runtime_only_keys` 登记 `grading_engine_m31_governed_objective`（顺带补 M25-B 遗留缺口 `grading_engine_objective_candidate`），否则 WS frame flag 被 `extra='forbid'` 拒绝。

**硬不变量（`safety_invariant_report_m31.json`，全达标）**：answer_key_override / llm_changed_key / rag_chunk_as_answer_key / model_vote_as_source / official_answer_as_source / false_positive / production_write_count / rejected_or_conflict_scored_as_release = 0；tamper_fail_closed / non_cohort_blocked / client_supplied_registry_status_ignored / controlled_official_only / content_hash_reproducible / matches_m30_canonical_hash = true；legacy_equal_rate=1.0；published / production_default_connected / canonical_truth_written = false。

**真实 `/api/v1/ws` drill（`tests/integration/test_luban_m31_governed_objective_ws.py`）**：cohort（qa_/test_/operator_）题库内 objective 命中拿到 `release_truth=True / official_score_allowed=True / controlled_official=True`，非 cohort 真实学生被挡，flag-off 仅 legacy，`construction_grading_result` 字节不变。测试：19 个新增（fat skill 10 + wrapper 6 + runner 1 + WS 3）全过；construction_grading 294（baseline 284 零回归）+ session 92 + capabilities/m16/m17a/m27 57 全绿。

**verdict=GO（runtime-binding scope）**。为何不是 whole-plan GO：本里程碑设计上限即 runtime-binding release gate（受控 cohort release-truth + production default OFF）。**仍 OUT OF SCOPE 需单独授权**：published registry、production default flip、canonical learner-truth write、远端/Aliyun/DB 写（本轮 production_write=0、remote_write=0、default_flip=0、published=false、canonical_truth_written=false）。

---

### 0.26.14 Knowledge Compiler Storage / Serving / Capacity Contract（2026-06-06）

> **本节把知识编译的存储、分片、调用和容量边界写成硬约束，供 M32 Waterproof Vertical Slice 及后续 full-topic compiler 复用。知识编译不是第二套 RAG，也不是一个可变 DB truth；它必须以 canonical manifest + signed shards 的形式被 runtime 消费。**

**存储分层（single authority）**：

| 层 | 存什么 | 可以做什么 | 禁止做什么 |
|---|---|---|---|
| `Supabase / KB v5` | `questions_bank`、`kb_v5.chunks`、`kb_v5.concepts/concept_edges`、learner evidence raw events | raw evidence / retrieval / learner event store，只读抽取或按业务写 learner event | `kb_v5.chunks` 不能当 answer_key；mutable row 不能直接成为 runtime release truth |
| `artifacts/luban_grading_artifacts/...` | compiler run ledger、FINDING、coverage、work_order、attack report、auditor report | 审计、人读、reconciliation 输入 | runtime 不得扫描 artifacts 目录猜版本；artifact GO 不自动成为 production authority |
| `runtime_supply/...` | signed release_candidate / published bundle、canonical pointer、manifest、shards | runtime 正式读取；随代码部署到服务器；hash/signature/rollback fail-closed | 不得无 manifest 碎片化；不得把 unverified candidate 和 release truth 混 namespace |
| 可选 object storage | 大 bundle 历史归档或未来超大 topic pack | 只能由 tracked canonical pointer + pinned hash/signature 引用 | 不能用“最新 blob”替代 manifest authority |

**文件形态（manifest + shards，不做 huge JSON）**：

1. 每个 compiled knowledge release 必须有一个 canonical manifest，至少包含：`schema_version`、`status`、`published`、`version`、`content_hash`、`signature`、`rollback_pointer`、`shards`、`producer`、`source_inventory_hash`。
2. 内容按 lane/topic 拆 shard，例如：`objective_answer_key`、`source_context`、`concept_graph`、`case_rubric`、`learning_mapping`、`validator_policy`；专题可继续按 `waterproof`、`concrete`、`contract_claim`、`schedule_network` 等拆。
3. 禁止把全量知识编译成单一 `huge_knowledge.json`；禁止几千个小文件无 manifest、无 hash、无 canonical pointer。
4. runtime 只能消费 manifest 指向的 shards；不能从目录扫描、mtime、文件名推断 authority。

**runtime 加载策略**：

- 启动时加载 manifest、验签、构建轻量索引（如 `question_id -> answer_key`、`concept_id -> shard`、`topic_id -> source_refs`）。
- 请求时按 `question_id / topic_id / concept_id` 读取相关 shard，组 `LubanContextPack` / `GradingPacket`。
- 不常驻教材全文、长 chunk、audit ledger、历史 artifacts；原文长 span 需要时从 KB v5/RAG 按 `source_ref` 取。
- tampered / missing / malformed manifest 或 shard 必须 fail-closed；legacy 或 open-world diagnostic 保持可用，不得静默降级为 release truth。

**容量与性能边界（设计目标：5 万会员）**：

- compiled pack 本身不是 5 万会员规模下的主要瓶颈。当前 M31 `runtime_supply` 量级约 MB 级；未来全教材/topic shards 也应控制在“索引常驻、正文按需”的设计下。
- 5 万会员不等于 5 万并发；容量设计必须按注册会员、日活、峰值同时在线、每分钟 LLM 判题请求、RAG 查询量、Learning Brain 写入量分层建模，不能只报一个会员数。
- 5 万会员真正瓶颈优先级：LLM 并发与 provider 限流 > WebSocket 长连接 > Supabase/RAG 连接池 > Langfuse/日志/learner event 写入 > compiled pack 文件大小。
- 必须用 queue、rate limit、provider timeout、DeepSeek→Qwen fallback、RAG/LLM cache、DB connection pool、trace sampling 控制生产压力；不得通过绕过 authority、跳过 validator、删 RAG 来“提速”。
- token efficiency 是约束，不是目标：知识编译减少无效上下文，让 runtime LLM 看 scoped packet；不能把“少 token”误解为“少用 LLM 理解”。

**维护周期**：

| artifact 类型 | 维护频率 | 规则 |
|---|---|---|
| candidate / work_order | 可每日或随 open-world / review / RAG 新证据生成 | LLM 可组织、归纳、提出候选，但不能签 truth |
| release_candidate | 每个 sprint、教材/题库/规范批次更新后、或高价值候选积累到阈值 | deterministic gate 签发，带 hash/signature/rollback |
| published | 只经独立 release gate + 用户/owner 授权 | 不原地改；只发新版本 |
| learner evidence / claims | 运行期持续更新 | 属 Learning Brain authority，不能回写 release artifact |

**M32 前置要求**：Waterproof vertical slice 必须遵守本 contract：防水二次清洗教材只能作为 raw/candidate 输入；最终输出应是 `waterproof` topic shard + manifest pointer + runtime consumption examples + Learning Brain preview examples。RAG 找防水证据，graph 表达防水关系，knowledge compiler 签防水专家资产；三者不能互相替代。

---

### 0.26.15 M32 Grading-to-Brain Waterproof Vertical Slice（2026-06-07，当前唯一执行主线）

> **本节取代本文所有旧的“当前下一步”表述。** M32 不是再跑一个全量 compiler，也不是继续证明 M26/M31 已经证明过的 safety gate。M32 的目标是用一个防水专题，把 Grading-to-Brain Loop 跑成学员可感知的产品闭环。

M32 必须证明的唯一业务事实：

```text
一次批改或开放诊断产生的 point-level 学习证据，能被 Learning Brain 编译成可解释的 LearnerClaim 和下一步动作，并在复测后改变该 claim。
```

最小闭环：

```text
waterproof signed topic shard
  -> LubanContextPack / Compiled Context
  -> grading or open-world diagnostic
  -> learning_evidence event
  -> learning_synthesis / LearnerClaim
  -> PersonalizationContextPack
  -> NextBestAction
  -> retest / practice
  -> outcome proof
  -> updated claim
```

M32 的四个系统角色：

| 系统 | M32 中的职责 | 禁止越权 |
|---|---|---|
| 鲁班评分引擎 | 产出采分点级命中、错因、证据 span、high-risk 标记和 learning evidence draft | 不保存第二套长期画像 |
| Learning Brain / GBrain | 把 evidence ledger 编译为 `LearnerClaim`、PCP、next action、retest outcome | 不重新判分，不把 shadow/candidate 直接升 mastery |
| 知识编译 / RAG | 提供防水专题 signed shard、教材章节、source refs、taxonomy 关系 | 不把 mutable chunk 当 answer key，不替代 learner model |
| Runtime LLM | 用 scoped context 做在线解释、诊断和教学表达 | 不改 signed truth，不伪造 official score |

M32 GO 门：

- `waterproof` topic shard 有 canonical manifest、hash、source refs、runtime resolver example。
- 至少一个真实 `/api/v1/ws` 或等价 TestClient 链路产出防水相关 grading / diagnostic result。
- learning evidence 写入或 preview payload 能被 `learning_synthesis` 消费成 `LearnerClaim(needs_retest|observed|repeated|confirmed|stale)`。
- `PersonalizationContextPack` 是 report / TutorBot / practice 的单一 personalization input；前端不得自算推荐。
- NextBestAction 明确训练目标、材料、相似题或复测方式，且带 evidence refs。
- 复测 outcome 能更新 claim 或生成“未改善策略”，不能只展示训练完成。
- `production_write_count=0`、`canonical_truth_written=false`，除非用户另行授权 canonical write gate。

当前执行计划：

- [2026-06-07-luban-grading-to-brain-m32-waterproof-vertical-slice-execution-plan.md](2026-06-07-luban-grading-to-brain-m32-waterproof-vertical-slice-execution-plan.md)

---

## 0.16 Canonical update after M17A runtime LLM adjudicator（2026-06-04）

> **本节落实 §0.12 的 M17 Nexus-style runtime LLM adjudication（vertical slice = M17A）。production default 仍 OFF；下一步是 M17B/M18 扩面 + M19 default decision，不是 default flip。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/`

**M17A 三轴 verdict：**
| 轴 | verdict |
|---|---|
| M17A runtime LLM adjudication | **GO** |
| production default enable | **NO-GO** |
| production v1 | **NO-GO** |

- 真实 `/api/v1/ws` 受控 cohort：每次判题生成 scoped **GradingPacket**（registry hash + source/spec/list policy slice + student_answer + PCP read-only + token_budget + packet_hash），**DeepSeek-V4-flash primary** 判题（Qwen3.7 fallback），**deterministic validator** 作安全地板。
- 实测：**25 条真实 DeepSeek live 判题**，点级 accept 40/needs_review 10/reject 9/partial 7；比 M16 二元判定多 **12 个 granularity gain** + 8 个 validator downgrade（fp 防护）；false_positive=0、source_mismatch=0、legacy_equal_rate=1.0、production_write=0、kill/non-cohort 全过；p50≈2.1s。
- 代码：fat skill `runtime_llm_adjudicator.py`（packet + adjudicator + validator + LB preview draft）；thin hook `_maybe_attach_v1_llm_adjudication`；flag `grading_engine_v1_llm_adjudication`（allowlist）+ env kill `LUBAN_V1_LLM_ADJUDICATOR_ENABLED` + cohort `LUBAN_V1_LLM_ADJUDICATOR_COHORT`。production default OFF。
- 模型分工（§0.12）：runtime 仅 DeepSeek-flash + Qwen；GPT5.5（无 key fail-closed）/Opus（in-session）只 build-council。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：M17B/M18 扩面评测 → M19 default decision**

1. M17B/M18：扩大 adjudication 样本，做 LLM-vs-teacher 准确率/一致率离线评测、真人 teacher 闭环、production 化异步/超时预算。
2. M19 才是 default decision（需用户显式授权小流量）；**不要**现在 flip default、**不要**回 M11–M16 旧链路。
3. production v1 仍 **NO-GO**、production default OFF、不发 published registry。

---

## 0.15 GBrain personalization absorption: make grading feed a brain, not just a score（2026-06-04）

> 本节吸收 `2026-06-03-luban-gbrain-deep-absorption-personalization-execution-plan.md` 的有效思想。该文件本身已标记 `Superseded`，**不能恢复为独立实现 authority**；但其中的 GBrain 方法论必须进入鲁班评分引擎 v1：每次评分不仅产出分数，还要成为 Learning Brain 可解释、可复测、可行动的证据。

### 0.15.1 必须吸收的 GBrain 思想

| GBrain 思想 | 鲁班 v1 落点 | 不允许发生 |
|---|---|---|
| Brain-first lookup | runtime `GradingPacket` 先读 `PersonalizationContextPack` / compiled learner truth，再组织判题和下一步建议 | 每个 wrapper 自己临时读 learner state 或手写个性化 |
| Compiled truth + immutable timeline | `learner_memory_events.learning_evidence` append-only；`learning_synthesis` / read model 可重建 | LLM 或 runtime 原地改 mastery / weak point truth |
| System of record discipline | raw evidence、claim projection、training intent、registry artifact 各有唯一 authority | 把 grading result、chat summary、notebook note 混成同一份 truth |
| Claim lifecycle | 评分后只产生 evidence / claim proposal；confirmed / stale / contradicted / needs_retest 必须有状态机 | shadow 或 simulated retest 直接升 mastery |
| PersonalizationContextPack | report / TutorBot / deep_question / RAG / grading packet 共用同一 read-only pack | 每个 surface 生成自己的 next action |
| Dream cycle | LLM-assisted nightly lint：unsupported claim、stale claim、contradiction、missing retest、missing next action | nightly job 静默重写 evidence event |
| Eval gate | 个性化必须有 evidence coverage、unsupported claim rate、generic fallback rate、exact authority conflict 测试 | 只看 UI 截图或主观感觉“更智能” |

### 0.15.2 Claim lifecycle 必须进入 M17/M18

M17 runtime adjudication 的输出不能只停在 `point_results`。每个采分点还必须产出 Learning Brain 可消费的草案字段：

```json
{
  "grading_evidence_event_draft": {
    "subject_id": "construction_case",
    "question_id": "...",
    "point_id": "...",
    "decision": "accept|partial|reject|needs_review",
    "evidence_kind": "student_answer_span|textbook|question_stem|machine_spec|list_spec|review_only",
    "student_answer_span": "...",
    "blocked_reason": "...",
    "claim_candidate": {
      "concept_id": "...",
      "error_code": "...",
      "claim_status": "observed|needs_retest|blocked_from_claim",
      "evidence_level": "L0_observed",
      "requires_retest": true
    },
    "write_policy": "preview_only|teacher_review_required|real_retest_required"
  }
}
```

规则：

- `accept/partial/reject` 可以进入 preview evidence；**不能自动变 canonical mastery**。
- `needs_review/high_risk/source_gap` 只能进 `blocked_from_claim` 或 review queue。
- `confirmed` 只能来自 teacher/council-reviewed authority 或真实 retest proof。
- `improved` 只能来自真实 `/api/v1/ws` retest proof，simulation 永不算。
- `supporting_event_ids` 与 `evidence_refs` 必须兼容，避免旧 projection 被误判为无证据。

### 0.15.3 PersonalizationContextPack 必须成为 GradingPacket 的一部分

M17 `RuntimeGradingPacket Builder` 必须包含一个只读 `personalization_context` 区块：

```json
{
  "personalization_context": {
    "schema_version": 1,
    "source": "learning_brain",
    "top_claims": [],
    "recent_evidence_refs": [],
    "active_training_intent": {},
    "next_best_action_candidates": [],
    "gaps": [],
    "authority": {
      "claims": "learning_synthesis",
      "next_training": "training_intent",
      "retrieval": "RAGService"
    }
  }
}
```

边界：

- `PersonalizationContextPack` 是 read-only projection，不是 writer。
- `training_intent` 仍是“下一步练什么”的处方 authority；`next_best_action` 只能是 view/explain over `training_intent`，不能成为第二套处方。
- RAG 可以用 personalization context 选择/解释 `compiled_learning_truth` source group，但 exact question、hidden grading key、textbook/standard/source authority 永远优先。
- 无证据学员只能得到 starter action，不能伪造个性化弱点。

### 0.15.4 Dream cycle：LLM 参与维护 Learning Brain，但只能产 candidate

GBrain 的 dream cycle 思想要落成一个 LLM-assisted maintenance loop：

```text
learning_evidence ledger
  -> LLM dream-cycle reviewer
  -> unsupported/stale/contradicted/missing-retest/missing-next-action candidates
  -> deterministic lint gates
  -> review queue / retest plan / synthesis candidate
  -> signed projection on next synthesis
```

必检项：

- unsupported claim rate
- stale claim needs retest
- contradicted claim cannot silently resolve
- evidence/no-evidence split
- exact authority conflict
- standard/textbook authority conflict
- generic fallback rate when evidence exists
- cross-user / subject leak

M18 前必须有 `learning_brain_dream_cycle` dry-run artifact；M19 前必须有 production shadow observation，不能只靠 fixtures。

### 0.15.5 M17/M18 新增验收门

在 §0.14 的 12 问之外，M17/M18 必须额外回答：

1. GradingPacket 是否包含 `PersonalizationContextPack`，且来源是唯一 read model？
2. Runtime LLM 判题是否使用 learner context 提升解释/下一步建议，而不是改判分 authority？
3. 每条 claim proposal 是否有 evidence refs / supporting event ids？
4. 无证据学员是否只得到 starter action？
5. `training_intent` 是否仍是处方 authority，`next_best_action` 是否只是解释视图？
6. exact question / hidden grading / textbook / standard authority 是否仍高于 compiled learning truth？
7. Dream cycle 是否只产 candidate，不静默改 evidence ledger？
8. `unsupported_claim_rate=0`、`evidence_coverage>=0.95`、`generic_fallback_rate<=0.05` 是否能在真实 projection 或 shadow 样本中成立？

### 0.15.6 对产品目标的提升

融合 GBrain 后，鲁班评分引擎 v1 的交付标准不再是“判得准”这么窄，而是：

```text
grade the answer
  -> explain every point
  -> identify the learner claim
  -> prescribe the next action
  -> verify via retest
  -> update the learning brain with evidence
```

这才是完整产品：评分只是入口，Learning Brain 是复利层。

---

## 0.10 Canonical update after M15 hits expansion + fresh retest（2026-06-04，**已被 §0.11 推进**）

> **本节 supersede §0.09 的 "M13=WEAK-GO / 下一步 hits<50"。M15 已把真实 `/api/v1/ws` counted hits 从 43 打到 53（≥50），并打通真实 retest proof。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/runtime_hits_expansion_and_retest_entry_m15_20260604/`

**M15 三轴 verdict：**
| 轴 | verdict |
|---|---|
| M15 limited internal release candidate | **GO** |
| Learning Brain canonical write pilot | **GO** |
| production v1 | **NO-GO** |

- counted_authority_backed_total=**70**、counted runtime hits **43 → 53**（≥50 GO 门，目标 55 差 2）。命中来自 textbook 16 + machine_logic 20 + list 14 + machine_calc 3；question_stem_fact 计入=**0**。
- 修复方式：**sample generation（每题一条 rich 答案，一条 submission 评所有 counted 点）**，**matcher 一字未改、未改 production 代码、未放宽门槛**。
- 安全全过：false_positive=0、bad_certified=0、source_mismatch=0、legacy_equal_rate=1.0、kill/failclosed/non-cohort 全过、production_write=0、production default OFF。
- **fresh retest 解阻**：M14E 走 old `runtime_shadow_adapter`（需 ai_draft_predictions）→ 0 proof；M15 改走既有 `/api/v1/ws` beta_shadow 确定性评分 → **5 条真实 retest proof + 5 条 canonical write dry-run**（`production_truth_written=false`）。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：M16 production release gate（独立硬门）**

1. M16 是独立 production 门，差 5 个硬条件：真人 teacher 复核闭环（非 shadow）、production authority registry 签字、双大模型 skeptic（GPT5.5 key）、operator cohort 实时 rollback 演练、canonical learner truth write 路径（当前仅 dry-run）。
2. production v1 仍 **NO-GO**、production default OFF、**不发 formal production registry**；**不要**回 M6–M13R 旧链路、**不要**单方覆盖并行产物。

---

## 0.09 Canonical update after M13R reconciliation（2026-06-04，**已被 §0.10 推进**）

> **本节 supersede §0.08 的 M13 verdict。M13 曾出现 GO（Drill A）/ NO-GO（Drill B）两个并行 drill 冲突。M13R 建立唯一 canonical measurement protocol 复跑，给出唯一 verdict。⚠️ "WEAK-GO / hits 43<50" 已被 §0.10 M15 推进到 hits=53 GO。**

唯一 canonical ledger：`artifacts/luban_grading_artifacts/canonical_release_drill_reconciliation_m13r_20260604/`（旧 `formal_release_candidate_gate_m13_20260604/` 产物保留不动，见 `supersession_matrix_m13r.md`）。

**M13 canonical verdict = WEAK-GO**（唯一）：
- 机制安全**全部成立**（真实 `/api/v1/ws` 复现）：false_positive=0、kill_switch_works=true、artifact_fail_closed=true、legacy_equal_rate=1.0、non_cohort_blocked=true、production_write=0、LB writeback=0。
- Drill B 的 NO-GO 三驱动项（fp=6 / kill=false / failclosed=false）**经证为测量伪影**（通用答案整题 FP、kill/failclosed 用非机制方式测量），已 supersede。
- Drill A 的 GO **过于乐观**：把 12 个未 span-verified 的 question_stem_fact 计入。canonical 排除后 **counted_authority_backed=70**（textbook 23 + machine_logic 30 + machine_calc 3 + list 14），≥50。
- 真实 `/api/v1/ws` 复跑 **135** submissions / **59** adversarial；**counted runtime hits=43 < 50** → 未达 GO 门 → **WEAK-GO**。

**六轴 verdict（canonical）：** M8=GO / M9·M10=WEAK-GO / M11=GO / M12=GO / **M13=WEAK-GO** / production v1=**NO-GO**。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：把 counted runtime hits 从 43 提到 ≥50**

1. 完成 question_stem_fact 的 **case-event-text span verification**（backfill queue），核实后纳入 counted。
2. 或扩大 gradeable 题集，让更多 counted 点在 `/api/v1/ws` 触发批改（当前部分 QA question_id 在 harness 下不批改）。
3. 任一达成后重跑 M13R canonical drill；counted hits≥50 即 M13=GO。
4. production v1 仍 **NO-GO**，production default OFF，**不发 formal production registry**；**不要**回 M6–M12 旧链路、**不要**单方覆盖并行产物（用 supersession matrix）。

---

## 0.08 Canonical update after M13 formal release candidate gate（2026-06-04，**已被 §0.09 reconcile**）

> **⚠️ 本节的 "limited internal release candidate=GO" 已被 §0.09 M13R supersede 为 WEAK-GO（counted runtime hits 43<50）。以下保留为历史。**

最新 canonical ledger：`artifacts/luban_grading_artifacts/formal_release_candidate_gate_m13_20260604/`

**关键纠偏（authority taxonomy）：** 教材逐字锚**不是**唯一 production authority。9 类合法 authority：`textbook_verbatim` / `question_stem_fact` / `machine_checkable_calculation` / `machine_checkable_logic` / `list_rule_full_coverage` / `external_standard_source` / `teacher_review_final_shadow` / `review_only` / `drop_or_keep_draft`。旧的 "source-backed≥50" 门升级为 **production_authority_backed≥50**。每点单一 primary authority；official_answer 不当 textbook、模型票不当 source、question_stem 只证题干事实。

**六轴 verdict（固定）：**

| 轴 | verdict |
|---|---|
| M8 alpha_shadow | **GO** |
| M9 / M10 beta readiness | **WEAK-GO** |
| M11 runtime gated entry | **GO** |
| M12 internal live QA | **GO** |
| **M13 limited internal release candidate** | **GO** |
| production v1 | **NO-GO** |

数字：production_authority_backed=**82**（textbook 23 + machine_logic 30 + machine_calc 3 + question_stem_fact 12 + list 14）。真实 `/api/v1/ws` drill：**111** submissions、**55** authority-backed 命中、**35** 对抗负例，false_positive=0 / bad_certified=0 / source_mismatch=0 / legacy_equal_rate=1.0 / production_write=0；cohort gate（qa/test 允许，operator_/real_ 被 block）/ kill switch / fail-closed / duplicate 幂等 / teacher review dry_run 幂等 全过；p50≈27ms。修复了 loader source matcher（原用 point_id，改用 M8/M9 verified 真实 textbook term）。

**历史下一步（已被 §0.C / §0.26.15 M32 supersede）：limited internal release 灰度 + 真人 teacher 闭环**

1. 按 `limited_release_switch_design_m13.md` 做 cohort 灰度（qa→test→named 内部→operator），production default 仍 OFF，每步可 env kill switch 秒回滚。
2. 落地真人 teacher 复核闭环（非 shadow）+ 补 OpenAI key 启 GPT5.5 双大模型 skeptic。
3. production v1 仍 **NO-GO**，**不发 formal production registry**，直到独立 production release gate（真人 teacher 闭环 + production authority 签字 + operator 灰度监控）全过；**不要**回 M6–M12 旧链路。

---

## 0. 一句话目标

鲁班评分引擎的最终目标不是离线评测，也不是单纯生成 rubric 文件，而是：

> 学生提交真实建筑实务主观题答案后，系统能高质量批改、逐采分点给证据、拦截高风险点、经老师或 LLM jury 复核后写入 Learning Brain，并持续沉淀成“越用越懂学员”的个性化学习建议。

完整闭环：

```text
真实案例题作答
  -> 鲁班评分引擎批改
  -> 采分点级 hit/partial/miss + evidence_span + rationale
  -> ArtifactRuntimeGate 控自动认证
  -> high_risk / weak / rewrite 点进入 review
  -> teacher-final 或 llm_jury-final 写入 Learning Brain
  -> weakness / mastery / next suggestion
  -> 下一轮训练、复测、长期画像更新
```

---

## 1. 当前完成度判断

| 能力面 | 当前完成度 | 结论 |
|---|---:|---|
| 真实 runtime shadow 链路 | 约 70% | `/api/v1/ws` QA/test shadow 已成立，append-only，不改 legacy，不写 LB；还缺 live provider + 生产级异步/监控。 |
| QA 老师工作台 + teacher-review 写回 | 约 75% | `/wechat-harness` 已能逐点复核、dry-run、真实文件后端写入、readback/synthesis；还缺 20-50 份真实 QA 产品测试和真人/PO 操作记录。 |
| Best-Quality / LLM jury 高质量阅卷能力 | 约 60% | 4 模型协议、缓存 jury、teacher-review substitute 已验证；M5R/M5B 已解除 3-juror quorum，live jury 已下调全部 11 个 published_candidate。 |
| Registry v0 发布门 | 约 90% | 20 题 v0 canonical 已有 published=18 / draft=1 / blocked=1，ArtifactRuntimeGate 已接 QA shadow。 |
| Registry v1 数据/采分点编译 | 约 35-45% | 外部题库 218 道确认，首批 30 道已结构化；M5 25 auto 点仅为 baseline，M5D 后直接 publish_candidate=0，正式 v1 未生成。 |
| Learning Brain 个性化闭环 | 约 60% | teacher-final 写入真实文件后端、读回、next suggestion 已通；长期记忆压缩、复测轨迹、学生可感知进步面还未产品化。 |
| 正式 production runtime | 约 20-30% | 仍处 QA/test shadow；未替换 `CaseGradingSkillKernel`，未接 production authority，未开放正式写权。 |

**总体判断**：55-65% 完成。已经不是“能不能做”的阶段，而是“如何安全变成可发布产品”的阶段。

---

## 2. 不变原则与单一 authority

### 2.1 三个工程原则

1. **Thin wrappers, fat skills**
   - router、endpoint、HTML 面板、adapter 只做鉴权、参数归一化、展示、转发。
   - 评分协议、jury、artifact gate、writeback、synthesis 必须在 service/script/skill authority 中。

2. **First principles**
   - 一等事实不是“某模型说对”，而是“这个采分点是否有足够 authority 支撑自动认证”。
   - 教材 source、评分点、teacher-final、Learning Brain event 分别有自己的 authority，不混权。

3. **Less is more**
   - 不新增表、不新增 endpoint、不新增第二套 registry、不让 RAG 进入评分 authority。
   - 先用现有 `/api/v1/ws`、`/wechat-harness`、`LearnerStateService`、`ArtifactRuntimeGate` 跑通。

### 2.2 当前唯一 authority 分工

| 业务事实 | 唯一 authority | 说明 |
|---|---|---|
| legacy 正式批改分数 | `CaseGradingSkillKernel` | 生产/legacy authority 未被替换。 |
| 鲁班 shadow draft | `runtime_shadow_adapter` + AI/Best-Quality service | QA/test candidate，append-only，不写成绩。 |
| artifact 是否可 auto-certify | `QuestionGradingRegistry -> ArtifactRuntimeGate` | published 才可自动认证；weak/rewrite/po_review/council_not_publish 不可 auto。 |
| 教材强锚 | 2026 教材 `content_markdown` deterministic exact match | LLM、official_answer、题库 explanation 都不能升 verified。 |
| 无真人 PO 时的 rubric review final | `ai_expert_council_final` | 只负责 candidate keep/rewrite/split/drop/external_source_required 裁决；非 human/PO，不能替代 textbook source authority。 |
| Learning Brain 写入 | `teacher_review_writeback` | 只有 teacher-final / llm_jury-final /明确 provenance 的 review payload 才写。 |
| 学情 readback/suggestion | `LearnerStateService` / synthesis adapter | 从 learning_evidence 读，不反向决定评分。 |

---

## 3. 已完成工作地图

### 3.1 评分真值与多模型方法学

已完成：

- Consensus-Gold / 4 模型陪审方法成型。
- 485 全量复验完成，DeepSeek-V4-flash + fallback 得到 WEAK-GO / 局部 Strong 候选。
- QWK 指标治理、选择性弃权、span guard、exact_required fallback 已验证。
- Qwen few-shot 线两轮 NO-GO，已停止；说明盲目 prompt/few-shot 会引入踩字回退。
- Best-Quality 4-model jury 被确定为打造期最高质量主引擎；DeepSeek 是未来 production-cost 单模型线。

关键边界：

- 4 模型 / LLM jury 是 review evidence，不是 human。
- DeepSeek 成本线不阻塞当前 Best-Quality QA 产品测试。
- 任何 LLM vote 不得制造 textbook source。

### 3.2 Runtime v0 / AI-Draft / QA 工作台

已完成：

- AI-Draft service：span guard、high_risk、unsupported fail-closed、pending review 三分数。
- `/api/v1/learning-brain/harness-case-grading?mode=ai_draft` QA-gated 接线。
- `/wechat-harness` QA 面板：evidence_span 高亮、model votes、artifact gate、teacher review 控件。
- Best-Quality 4model engine 可在 QA 面板切换。
- teacher-review route：`/api/v1/learning-brain/harness-case-grading-review`，默认 dry-run，QA/test + teacher_reviewed + writeback + dry_run=false 才写。
- review provenance 收口：`operator_smoke` / `model_jury_teacher_review` / `manual_qa_teacher` 三类明确区分。

关键产物：

- `artifacts/luban_consensus_gold/teacher_review_ux_v0_20260604/`
- `artifacts/luban_consensus_gold/teacher_review_real_writeback_v2_20260604/`
- `artifacts/luban_consensus_gold/model_jury_teacher_review_pilot_20260604/`

### 3.3 真实 `/api/v1/ws` E2E 闭环

已完成：

- Canonical WS smoke = 真实 FastAPI TestClient `/api/v1/ws` turn smoke。
- Shadow append 到 `result.metadata.luban_grading_engine_shadow`。
- legacy `construction_grading_result` 字节不变。
- E2E v1：deterministic fixture path 验证整链。
- E2E v2：使用 485 真实 4 模型 cache，非 fixture，完成 WS -> shadow -> teacher-final writeback -> MEMORY_EVENTS.jsonl -> synthesis -> next suggestion。

关键产物：

- `artifacts/luban_consensus_gold/ws_runtime_shadow_turn_smoke_20260604/`
- `artifacts/luban_consensus_gold/e2e_runtime_teacher_review_smoke_20260604/`
- `artifacts/luban_consensus_gold/e2e_runtime_teacher_review_smoke_v2_20260604/`

仍缺：

- 新鲜 QA 作答的 live provider path。
- production async / timeout / monitoring / cost guard。

### 3.4 Registry v0 发布门

已完成：

- Canonical v0 registry 目录：
  - `artifacts/luban_grading_artifacts/registry_v0_20260604/`
- 状态：
  - published=18
  - draft=1（Q20）
  - blocked=1（Q15）
- 单一 runtime gate：
  - `deeptutor/services/construction_grading/artifact_runtime_gate.py`
- 旧 `artifacts/luban_consensus_gold/question_grading_registry_v0_20260604/` 已 superseded。

意义：

- runtime shadow 已经不会绕过 artifact published/draft/blocked 门。
- weak source 点恒不可 auto-certify。

### 3.5 Registry v1 数据编译 M1-M5

重大更正：

- 早前“20 题外无数据 / data_blocked”结论错误。
- 真实外部题库存在：
  - `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库/`
  - canonical case_study=218，gradeable=210。
- 2026 教材 verbatim 锚源存在：
  - `FastAPI20251222/docs/2026/2026教材/第二次加强/FINAL_CLEANED_BOOK2026-*_fixed.json`

已完成批次：

| 阶段 | 结果 |
|---|---|
| M1 schema | `AuditPacket` / verify-on-write 规则冻结，official_answer 只作 weak。 |
| M2 candidate | 首批 30 道真题候选，MCQ 排除。 |
| M3 structuring | 30 题 -> 138 点；28 verified；16 published_candidate_not_final / 14 draft。 |
| M4 anchor refinement | verified 28 -> 36，published_candidate_not_final 16 -> 20。 |
| M4 quality gate | 宽口径 20 收紧为 7 真 published_candidate + 9 draft_candidate。 |
| M5A term alignment | verified 36 -> 43；published_candidate=11 / draft=12 / needs_po=7。 |
| source_lookup | M2 still_weak 10 点新增 verified=0，证明不是搜索没跑，而是本地强源不足。 |
| M5 authority adjudication | 34 题 / 150 点，auto_certifiable=25，official_weak=112，rewrite_needed=13，publish_ready_candidate=2，po_review_required=27。**现仅保留为 deterministic baseline；publish_ready=2 已 superseded。** |
| M5B jury readiness（历史，已 superseded） | 30 题 / 138 点 jury 包就绪；早期判断 DeepSeek/Qwen configured、GPT/Opus missing、<3 quorum、provider_blocked。后续 M5R/M5B 已修正 provider 口径。 |
| M5R provider/jury rerun | 3 个异质 provider quorum 可用；16 题真实 jury，曾给出 publish_candidate=1（M2-2015-32-00）。**该 1 题后续被 live M5B/M5C 下调，不能再当 publish。** |
| live M5B jury | 11 个 M5A published_candidate 全部 live 3-juror 复核；publish_ready=0，draft=2，needs_po=9；source_anchor_dispute=9。 |
| M5C PO handoff | 30 题统一 pending_po 队列；9 个 source_anchor_dispute 为最高优先级。历史表述“human PO decides”在无真人专家场景下需要 M5D contract 替代。 |
| M5D AI Expert Council Source Court | 无新增 live API；复用 M5B 33 个真实票 + Opus 协调席；9/9 source_anchor_dispute = council_not_publish；25 点 action：6 approve_with_repaired_anchor / 5 split / 5 require_external_source / 4 rewrite / 4 drop / 1 keep_draft。 |
| M6 candidate dry-run | 已生成 candidate dry-run；只证明 compiler / gate dry-run 不覆盖 v0、不接 runtime、不把 weak/rewrite auto；不代表正式可发布。 |

当前结论：

- Registry v1 正式发布 **未完成**。
- 直接 M6 publish_candidate **NO-GO**；当前 direct publish_candidate=0。
- 下一步是 **M7 compiler hardening**，先把 M5D gate 写进编译器：`list_rule coverage==1.0`、council-final action gate、repaired anchor deterministic reverify。
- `ai_expert_council_final` 可作为无真人 PO 时的 review finality，但 source authority 仍只能来自 2026 教材 exact match。

---

## 4. 当前实际与目标差距

### 差距 1：Registry v1 还不是正式 authority

目标：

- 全题库或至少首批题生成可发布 `QuestionGradingArtifact Registry v1`。
- runtime 可以读取 v1 published artifact，并对 verified + policy complete 点 auto-certify。

实际：

- 当前只有 v0 正式 gate。
- v1 首批 M5 34 题 / 150 点中 25 点可作为 deterministic baseline。
- 112 official weak + 13 rewrite 点不能 auto。
- M5/M5R 的 publish_candidate 已被 live M5B/M5C/M5D supersede；当前直接 publish_candidate=0。
- M6 candidate dry-run 已完成，但只是 compiler/gate 证明，不是可发布 registry。

差距：

- 需要 M7 compiler hardening，把 M5D source court gate 固化到 candidate compiler。
- 需要 source repair factory 或 QA beta，用真实 repaired anchors / external source 补足可发布点。
- 需要正式 release gate 和 rollback plan；runtime 仍不得接 v1 candidate。

### 差距 2：QA 产品态已有，但 production runtime 未到

目标：

- 学生真实提交后能稳定产生鲁班评分结果。
- 老师/运营可复核。
- 高风险点不误写。
- 生产可监控、可降级、可回滚。

实际：

- `/api/v1/ws` QA shadow 已成立。
- E2E v2 使用 model_cache，不是 live provider。
- `/wechat-harness` 可用，但还不是正式用户产品面。
- 真实 QA 20-50 样本测试未放量。

差距：

- live provider path。
- async UX / timeout / retry / cost guard。
- QA 产品测试批量报告。
- production rollout gate。

### 差距 3：Learning Brain 已能写入，但长期个性化未证明

目标：

- 学员能感知系统“越来越懂我”。
- 系统能基于历史错因、采分点、题型、时间变化给下一步建议。

实际：

- teacher-final 写入真实文件后端已验证。
- readback / synthesis / next suggestion 已通。
- 但仍是单次/小批 smoke。
- 尚未做长期时间衰减、复测变化、错因稳定性、学生可见报告。

差距：

- 需要 20-50 份 QA 数据形成学习轨迹。
- 需要学生可见“进步证据”页面/报告。
- 需要 memory compression / stale evidence / recent-vs-long-term 策略。

---

## 5. 三条并行主线

### A 线：Registry v1 Authority 编译与发布候选

目标：

把外部 218 道真题逐步变成可信 `QuestionGradingArtifact`，并先让首批 34 题形成 v1 candidate dry-run 包。

当前输入：

- M5 authority adjudication：34 题 / 150 点。
- M5 deterministic baseline：25 auto_certifiable / 112 official weak / 13 rewrite_needed。
- M5/M5R publish_candidate：已被 live M5B/M5C/M5D supersede。
- M5D source court：9/9 source_anchor_dispute = council_not_publish。
- 当前直接 publish_candidate=0。

近期任务：

1. **A1 / M7 Compiler Hardening**
   - 固化 `list_rule coverage==1.0`；denominator 必须等于真实条目集，不能用单条 verbatim 锚覆盖整列。
   - 增加 council-final action gate：`split_point` / `require_external_source` / `rewrite_point` / `drop_point` / `keep_draft` 不得 auto。
   - 对 `approve_with_repaired_anchor` 强制 deterministic reverify：repaired quote 必须在 2026 教材 `content_markdown` exact/verbatim 命中。
   - 生成 hardened candidate simulation，不生成正式 registry，不接 runtime。

2. **A2 / Source Repair Factory**
   - 对 M5D 的 6 个 `approve_with_repaired_anchor` 做机器复验并回写 candidate source packet。
   - 对 5 个 `require_external_source` 和 4 个 `rewrite_point` 生成外部源/重写工单。
   - 对 5 个 `split_point` 拆成单点单锚，不允许拆前 auto。

3. **A3 / QA Beta Candidate Scope**
   - 若 M7 hardened simulation 仍无 publish candidate，直接进入 QA beta draft/review 测试，不包装成发布。
   - 若有 publish candidate，也必须先通过 release gate 和 v0/v1 隔离检查。

4. **A4 / 扩到第二批 30 题**
   - 不等首批正式发布，也可以并行跑第二批 M2-M5 pipeline。
   - 但不能污染 v1 candidate。

验收门：

- formal_registry_emitted=false，直到 M7 hardened candidate + release gate 明确允许。
- official_weak/rewrite 永不 auto。
- `council_not_publish` 永不 auto。
- list_rule 必须 coverage==1.0 才能 auto。
- repaired anchor 必须 deterministic reverify。
- v0 不被覆盖。
- runtime 不接 v1 candidate。

### B 线：QA 产品测试与 live provider runtime

目标：

把 QA shadow 从“脚本/缓存证明”推进到“真实 QA 产品操作”，证明老师/运营可以批改、复核、写回、读回。

当前输入：

- `/api/v1/ws` shadow 已接。
- `/wechat-harness` teacher-review UX 已有。
- E2E v2 走 model_cache。
- live provider path absent / provider quorum 不足。

近期任务：

1. **B1 / Live Provider Path**
   - 为 QA/test 新鲜作答接 DeepSeek/Qwen/GPT/Opus provider path。
   - 若走 Best-Quality，必须 async。
   - 若只走 DeepSeek fast，必须标 `engine=deepseek_fast`，不可冒充 best_quality。

2. **B2 / 20-50 QA 产品测试**
   - 使用真实浏览器 `/wechat-harness`。
   - review_source 明确：operator_smoke / llm_jury / manual_qa_teacher。
   - 记录耗时、override 率、pending 率、next suggestion 质量。

3. **B3 / Teacher-review writeback 审计**
   - 文件后端已经验证。
   - 下一步确认 outbox / Supabase sync 边界。
   - 不写生产用户。

4. **B4 / Runtime async UX**
   - Fast 同步，Best 异步。
   - timeout / fail-closed / partial result / retry / cost ledger。

验收门：

- legacy unchanged。
- shadow_writeback_performed=false。
- teacher-final 才写 LB。
- no production default。
- live provider provenance 清晰。

### C 线：Learning Brain 个性化与学生可感知体验

目标：

把批改结果转成长期学习事实，让学生能看到“我哪里进步了、哪里老错、下一步做什么”。

当前输入：

- teacher-final 写入 `learning_evidence` 已通。
- readback / synthesis / next suggestion 已通。
- high_risk/unsupported 不自动 mastery。
- teacher override 是更高 authority。

近期任务：

1. **C1 / 学习事实 schema 收敛**
   - 固化 grading -> learning_evidence payload。
   - 区分 gap、partial、mastery、rewrite、needs_review。

2. **C2 / 学生可见进步报告**
   - 从“掌握率数字”改成证据故事：
     - 最近 7 天常漏采分点。
     - 同类题复测是否减少扣分。
     - 哪些 exact_required 术语已掌握。
     - 下次建议做哪类题。

3. **C3 / 长期记忆管理**
   - recent 状态保细。
   - 旧状态压缩成 stable weakness/mastery。
   - 过时证据降权。
   - teacher-final / llm_jury-final provenance 保留。

4. **C4 / 与 Registry/Runtime 联动**
   - 只有 Registry gate auto 或 teacher/jury final 才能写入高置信 learning evidence。
   - draft/weak/rewrite 只进 review/pending，不提升 mastery。

验收门：

- 不新增第二套 memory。
- 复用 `LearnerStateService` / `learning_evidence`。
- 学生能看到具体证据，不只是抽象 mastery。

---

## 6. 接下来 72 小时推荐排期

### Day 1：A 线 M7 compiler hardening

目标：

- 把 M5D source court gate 写进 compiler simulation。
- 证明 list_rule coverage<1.0、council_not_publish、split/rewrite/drop/external_source_required 都不会 auto。
- 对 6 个 `approve_with_repaired_anchor` 做 deterministic source reverify。

产物：

- `artifacts/luban_grading_artifacts/registry_v1_compiler_hardening_m7_20260604/`
- `council_action_gate_results.json`
- `list_rule_coverage_gate_audit.json`
- `repaired_anchor_reverify_results.json`
- `hardened_candidate_simulation.json`
- `blocked_from_auto_certification_after_m7.json`

### Day 2：B 线 provider/live + QA test 准备

目标：

- 明确 provider 可用性。
- 如果补齐 GPT/Opus 任一 key，可作为 QA jury 扩充证据。
- 无论 provider 是否补齐，都不能绕过 M5D/M7 source gate；无真人 PO 时使用 `ai_expert_council_final` 非人类 provenance。

产物：

- provider readiness report。
- 20-50 QA test plan。
- live provider / model_cache / no-provider 三态对照。

### Day 3：C 线学生可见学习闭环

目标：

- 基于 E2E / teacher-review payload，做一份学生可见“批改后进步报告”设计与最小数据投影。

产物：

- Learning Brain grading-to-progress view model。
- sample report JSON。
- `/wechat-harness` 或静态 HTML preview。

---

## 7. 当前阻塞与决策点

| 阻塞 | 当前事实 | 决策 |
|---|---|---|
| LLM jury quorum 不足 | 历史 M5 provider_blocked 已被 M5R/M5B 解除到 3-juror quorum；GPT/Opus 原始 4 模型仍不完整。 | 可继续补 provider，但当前 blocker 已转为 source-anchor dispute / compiler hardening。 |
| Registry v1 不能正式发布 | M5 baseline 25 auto 点仍有效；但 M5/M5R publish_candidate 已被 M5B/M5C/M5D 下调，当前 direct publish_candidate=0。 | 先 M7 compiler hardening，不接 runtime。 |
| live provider runtime absent | E2E v2 用 model_cache。 | B 线实现 QA live provider path，先 QA/test。 |
| PO/human 缺位 | 用户没有真人专家；M5D 已定义 AI council 替代真人 PO 的边界。 | 使用 `ai_expert_council_final` 诚实 provenance，不冒充 human/PO；source authority 仍只认教材 exact match。 |
| 学生可见价值未成型 | 后端 learning evidence 已通，前端体验未闭环。 | C 线做 evidence-driven progress report。 |

---

## 8. 禁止事项

1. 不把 `official_answer` / 题库 explanation 当 textbook source。
2. 不把 LLM judgment 当 source authority。
3. 不把 `operator_smoke` 写成 `manual_qa_teacher`。
4. 不把 485 旧 cache 冒充新题 jury vote。
5. 不用 v1 candidate 覆盖 v0 canonical registry。
6. 不让 RAG 进入评分 authority。
7. 不接 production runtime default。
8. 不新增表或 endpoint 来绕过现有 authority。
9. 不把未复核 AI-Draft 写 Learning Brain。
10. 不把 provider_blocked 包装成质量通过。

---

## 9. 外来 agent 接手顺序

如果你是新 agent，请按这个顺序读：

1. 本文档。
2. `docs/plan/INDEX.md` 的“鲁班智考个性化教学”行。
3. `docs/plan/2026-06-04-luban-runtime-v0-closure-summary.md`。
4. `docs/plan/2026-06-04-luban-case-rubric-data-expansion-plan.md`。
5. 最新 artifact FINDING：
   - `artifacts/luban_grading_artifacts/registry_v1_canonical_state_reconciliation_20260604/FINDING_registry_v1_canonical_state_reconciliation_20260604.md`
   - `artifacts/luban_grading_artifacts/ai_expert_council_source_court_m5d_20260604/FINDING_ai_expert_council_source_court_m5d_20260604.md`
   - `artifacts/luban_grading_artifacts/registry_v1_candidate_dry_run_m6_20260604/FINDING_registry_v1_candidate_dry_run_m6_20260604.md`
   - `artifacts/luban_grading_artifacts/case_rubric_authority_adjudication_m5_20260604/FINDING_case_rubric_authority_adjudication_m5_20260604.md`
   - `artifacts/luban_grading_artifacts/case_rubric_term_alignment_m5a_20260604/FINDING_case_rubric_term_alignment_m5a_20260604.md`
   - `artifacts/luban_grading_artifacts/case_rubric_jury_review_m5b_20260604/FINDING_case_rubric_jury_review_m5b_20260604.md`
   - `artifacts/luban_consensus_gold/e2e_runtime_teacher_review_smoke_v2_20260604/FINDING_e2e_runtime_teacher_review_smoke_v2_20260604.md`
6. 再决定执行 A/B/C 哪条线。

开始任何代码前必须确认：

- `git status --short --branch`
- 是否有并行脏改。
- 本任务触碰范围。
- 验收命令。

---

## 10. 下一条推荐 prompt（A 线）

历史推荐“先执行 A 线 M6”已被 M5D supersede。当前最推荐先执行 A 线 M7：

> 做 Registry v1 compiler hardening：把 `list_rule coverage==1.0`、council-final action gate、`approve_with_repaired_anchor` deterministic reverify 写成 compiler/gate simulation；证明 M5D 的 `council_not_publish` / split / rewrite / drop / external_source_required 都不会 auto；正式 registry 仍为 NO，runtime 仍不接 v1。

M6 candidate dry-run 已完成，它的意义只是证明 compiler/gate 不污染 v0/runtime；不能再被当作“当前直接下一步”或“可试点发布”。

---

## 11. v2 决策总览：现在到底该做什么

### 11.1 最高优先级判断

当前不是继续证明“模型能不能批改”，也不是继续单点挖教材锚点。已经证明：

- 批改链路能跑。
- QA shadow 能接真实 `/api/v1/ws`。
- teacher-final 能写真实文件后端。
- Learning Brain 能读回并生成建议。
- 外部题库与教材源存在。
- 首批 34 题已经形成 M5 authority 分层。

因此，当前最高优先级是：

1. **把 M5D 的 source court 结果固化进 Registry v1 compiler hardening。**
2. **把 QA 产品测试从脚本/缓存推进到 live provider 或明确 AI council/source gate 路径。**
3. **把 Learning Brain 的单次 evidence 写入升级为学生可感知的进步报告。**

### 11.2 为什么不是继续做更多离线评测

继续跑离线评测的边际收益已经下降：

- M5A 锚点从 36 -> 43，只新增 7 个 verified，其中部分短词/短句需要 jury/PO 判断。
- source lookup 对 10 个 still_weak 新增强锚为 0，说明不是“搜索没跑”，而是本地强源不足。
- M5B 已证明新题 jury 卡在 provider quorum，不是协议缺失。

所以接下来要做的是**交付链路**，不是继续堆分数：

```text
M5/M5R baseline
  -> live M5B / M5C downrank
  -> M5D ai_expert_council_final source court
  -> M7 compiler hardening
  -> source repair factory / QA beta
  -> QA product test
  -> Learning Brain progress surface
```

---

## 12. 全量历史证据账本（按业务阶段）

本节用于防止后续 agent 失忆。这里只记录当前仍有决策价值的事实；更细日志看各 artifact FINDING。

### 12.1 Golden / Consensus / 评分真值阶段

| 工作 | 结果 | 当前意义 |
|---|---|---|
| Golden Eval v2.2 / human validation slice | PO 填过 131 点人锚，human-vs-ledger agreement 高；artifact-first 曾明显差。 | 证明“真人锚”能校准，但不能无限依赖真人。 |
| Consensus-Gold held-out | 4 模型 jury 在 held-out 175 点上形成 v1 gold；auto-gold 覆盖约 93.1%，剩 12 policy queue。 | 奠定“无真人时用异质陪审 + LOO + fail-closed”的方法。 |
| Policy queue | 12 unresolved 分成 list_rule denominator / exact_required near synonym；规则覆盖 Qwen disagreement。 | 指出主要口径分歧不是幻觉，而是 list_rule/踩字 policy 边界。 |
| Qwen few-shot A/B | 整版和 list_rule-only 均 NO-GO，引入 exact_required/unsupported 回退。 | 停止 Qwen few-shot，避免 prompt 负收益。 |
| DeepSeek fallback / 485 | DeepSeek exact_required fallback 能清硬踩字，但 485 真实一致率只到 WEAK-GO。 | DeepSeek 是未来低成本线，不是当前打造期质量上限。 |
| QWK / selective abstention | metric-v2 candidate 与选择性弃权证明 raw_delta 指标偏保守。 | 指标治理有价值，但不能偷换生产 gate。 |

### 12.2 AI-Draft / Best-Quality / QA 面板阶段

| 工作 | 结果 | 当前意义 |
|---|---|---|
| AI-Draft full100 | 100 samples / 485 points；bad_certified=0；high_risk 19.2%。 | AI draft 安全不变量成立，但 high_risk 偏高，适合 teacher-review。 |
| `/wechat-harness` AI-Draft 面板 | 支持 evidence_span、三分数、pending/auto/unsupported。 | 成为 QA 产品测试入口。 |
| Best-Quality 4model engine | QA 面板可切换，缺 4 模型预测时 fail-closed。 | 打造期最高质量组合。 |
| teacher-review UX v0 | 支持逐点 confirm/override/pending、notes、dry-run/writeback。 | 可以让老师/操作员真实复核。 |
| provenance 收口 | `operator_smoke` / `model_jury_teacher_review` / `manual_qa_teacher` 明确。 | 防止 AI 操作冒充真人。 |

### 12.3 Runtime shadow / E2E 闭环阶段

| 工作 | 结果 | 当前意义 |
|---|---|---|
| RuntimeShadowAdapter | 消费真实 `question_followup_context` shape；published/draft/missing fail-closed。 | 鲁班引擎能吃真实答题上下文。 |
| `/api/v1/ws` QA flag | shadow append 到 RESULT metadata；legacy unchanged。 | 真实入口已接 QA/test shadow。 |
| canonical WS turn smoke | FastAPI TestClient `/api/v1/ws`，legacy_equal=true，writeback=false。 | canonical runtime 证据，capability.run smoke 已 superseded。 |
| teacher-review real writeback v2 | 真实 `LearnerStateService` 文件后端写 `MEMORY_EVENTS.jsonl`。 | 不是 fake integration；Learning Brain 写入口可用。 |
| E2E v1/v2 | WS -> shadow -> teacher-review -> writeback -> readback -> next suggestion。v2 用 485 真实 cache，非 fixture。 | QA E2E 闭环成立，但 live provider path 仍缺。 |

### 12.4 Registry v0 / v1 数据生产阶段

| 工作 | 结果 | 当前意义 |
|---|---|---|
| Registry v0 | canonical `published=18/draft=1/blocked=1`。 | 当前唯一可 runtime gate 的正式发布门。 |
| M1 schema | `AuditPacket` / verify-on-write 规则冻结。 | 后续新题结构化共同 schema。 |
| M2 candidate | 外部题库确认 218 case_study，首批 30 候选。 | 更正“无数据”错误。 |
| M3 structuring | 30 题 / 138 点 / 28 verified / 16 candidate。 | 第一批真实结构化。 |
| M4 refinement / quality | 28 -> 36 verified；质量门收紧。 | 防止刚解冻就污染 published gate。 |
| M5A term alignment | 36 -> 43 verified；published_candidate=11 / draft=12 / needs_po=7。 | 锚点打磨边际递减，进入 review。 |
| source lookup | 10 still_weak 新增 verified=0。 | 证明 weak 不能硬升强锚。 |
| M5 authority adjudication | 34 题 / 150 点；auto=25；official_weak=112；rewrite=13；publish_ready=2；po_review=27。 | 历史 baseline；publish_ready=2 已被 live M5B/M5C/M5D supersede。 |
| M5B provider readiness / live jury | provider_blocked 历史结论已被 M5R/M5B 修正到 3-juror quorum；11 个 published_candidate live 复核后 publish_ready=0。 | 真瓶颈转为 source-anchor dispute 与 compiler hardening。 |
| M5D source court | 9/9 source_anchor_dispute = council_not_publish；25 点终裁动作为 approve/split/external/rewrite/drop/keep_draft。 | 当前最新 source court baseline；下一步 M7。 |

---

## 13. 使用场景矩阵与产品能力差距

### 13.1 学生真实作答

| 场景 | 目标体验 | 当前状态 | 差距 | 下一步 |
|---|---|---|---|---|
| 学生答一道已 published 的 v0 题 | 系统能给正式/准正式采分点反馈，证据高亮。 | QA shadow 可跑，legacy 不变。 | production authority 未切；仍 QA/test。 | B 线 live provider + QA product test。 |
| 学生答一道 v1 candidate 题 | 能 draft 批改，但 weak/rewrite/council_not_publish 不 auto。 | M6 candidate dry-run 已完成但不可发布；M7 hardening 未完成。 | compiler 还未固化 M5D hard gate。 | A 线 M7。 |
| 学生答 unknown/missing artifact 题 | fail-closed，不乱评，不写学情。 | Adapter/gate 已覆盖 artifact_missing。 | 产品提示与下一步推荐需更友好。 | B/C 联动。 |
| 学生写近义/半术语 | exact_required 不放水，进 review。 | fallback 与 policy 已验证。 | 新题 required_terms 还需 council/source repair。 | A 线 M7 + source repair。 |

### 13.2 老师/操作员复核

| 场景 | 目标体验 | 当前状态 | 差距 | 下一步 |
|---|---|---|---|---|
| 老师逐点 confirm/override | 页面可操作、dry-run、真实写回。 | `/wechat-harness` 已通。 | 真人样本少；审计字段需批量统计。 | B 线 20-50 QA test。 |
| 没有真人专家，用 LLM jury / AI council | 诚实标 `llm_jury` 或 `ai_expert_council_final`，不冒充 human/PO。 | M5D 已定义无真人 PO 的 AI council 边界。 | source authority 仍必须 deterministic exact match。 | M7 固化 council gate。 |
| high_risk 点被老师确认 | teacher override 可成为 mastery，但必须记录 authority。 | 方案 B 已收口。 | 产品 UI 需显式说明“老师覆盖 AI 风险”。 | C 线报告解释。 |

### 13.3 运营/产品测试

| 场景 | 目标体验 | 当前状态 | 差距 | 下一步 |
|---|---|---|---|---|
| 20-50 份 QA 产品测试 | 量化耗时、override 率、pending 率、建议质量。 | 3 份 operator smoke / 小批 E2E。 | 样本量不足。 | B 线 QA 批测。 |
| provider 不可用 | fail-closed 且可诊断。 | M5/M5B 已记录 provider_unavailable。 | runtime provider smoke 还要产品化。 | B 线 provider readiness。 |
| 成本过高 | Best async，DeepSeek fast 作低成本线。 | Distillation samples 有，未接。 | 成本/质量策略未定。 | B 线 engine policy。 |

### 13.4 学员长期学习

| 场景 | 目标体验 | 当前状态 | 差距 | 下一步 |
|---|---|---|---|---|
| 学生看到自己进步 | 不只是 mastery%，而是证据故事。 | next suggestion 已有。 | 没有学生可见 progress report。 | C 线 progress view model。 |
| 老错 exact_required 术语 | 系统追踪术语漏写历史，推荐复习。 | learning_evidence 可写。 | 多次作答聚合未验证。 | C 线 memory compression。 |
| 旧弱点被新证据覆盖 | 近期状态细，长期状态压缩。 | 计划层有思路。 | 代码/测试未成型。 | C 线 claim lifecycle。 |

---

## 14. 三线详细 backlog 与验收

### A 线：Registry v1 authority 编译

#### A0 当前事实

- M5 是 deterministic baseline，不是当前 publish authority。
- M5 之前的 M3/M4/M5A 只能作为 provenance，不能绕过 M5/M5D 决策直接升 auto。
- M6 candidate dry-run 已完成；它只证明 compiler/gate 不污染 v0/runtime，不代表可发布。
- M5D 是当前 source court baseline：9/9 source_anchor_dispute 不发布，6 个 `approve_with_repaired_anchor` 也必须先 deterministic reverify。

#### A1 M7 Compiler Hardening（下一步最高优先级）

**目标**：把 M5D source court 的硬门写入 compiler simulation，防止 M5 baseline 的短锚/半锚再次被误编为 auto。

**要改/新增**：

- `scripts/build_luban_registry_v1_council_hardened_candidate_m7.py`
- `tests/scripts/test_luban_registry_v1_council_hardened_candidate_m7.py`
- 产物目录 `artifacts/luban_grading_artifacts/registry_v1_compiler_hardening_m7_20260604/`

**必须输出**：

- `m5d_input_audit.json`
- `council_action_gate_results.json`
- `list_rule_coverage_gate_audit.json`
- `repaired_anchor_reverify_results.json`
- `hardened_candidate_simulation.json`
- `blocked_from_auto_certification_after_m7.json`
- `v0_vs_hardened_candidate_diff.json`
- `FINDING_registry_v1_compiler_hardening_m7_20260604.md`

**验收**：

- M5D 输入数字严格匹配：9 source_anchor_dispute / 25 points / 6 approve_with_repaired_anchor / 5 split / 5 require_external_source / 4 rewrite / 4 drop / 1 keep_draft。
- formal_registry_emitted=false。
- official_weak/rewrite/po_review/council_not_publish 不 auto。
- list_rule coverage<1.0 不 auto。
- repaired anchor 没有 deterministic exact match 不 auto。
- v0 不覆盖、不删除、不 supersede。
- ArtifactRuntimeGate dry-run 证明 candidate 不被误当正式 published。

#### A2 M7 后 source repair / QA beta 决策

如果 M7 仍无 publish candidate：

- 不进入 production runtime。
- 走 source repair factory 或 QA beta draft/review，不包装成发布。

如果 M7 产生少量 hardened candidate：

- 仍不进入 production runtime。
- 先走 release gate、v0/v1 isolation、teacher/jury review carryover。
- 再决定是否做 formal registry v1 proposal。

#### A3 第二批 30 题放量

可以与 M7/source repair 并行，但必须物理隔离产物目录。

目标：

- 从 218 case_study 中再取 30 题。
- 复用 M1-M5 pipeline。
- 不混进首批 M7 hardened candidate。

### B 线：QA 产品测试与 live provider

#### B0 当前事实

- QA shadow + teacher-review + writeback + readback 已通。
- E2E v2 使用 model_cache，不是 live provider。
- M5R/M5B 已证明 3-juror quorum 可用；GPT/Opus 原始 4 模型仍不完整，但当前 A 线 blocker 已转为 source court / compiler hardening。

#### B1 Provider readiness / live path

**目标**：把 provider 状态从“猜测”变成机器可读 readiness。

**任务**：

- 审计 OpenAI/Anthropic/DeepSeek/DashScope env 名。
- 对 configured provider 做 tiny smoke。
- 不打印 secret。
- 记录 latency/error/cost marker。

**验收**：

- provider_config_status.json。
- provider_smoke_results.json。
- 若 <3 quorum，明确 BLOCKED，不造 fake vote。
- 若 >=3 quorum，只允许 QA/jury review；不能绕过 M5D source gate。

#### B2 QA 产品测试 20-50 份

**目标**：证明老师/操作员能真实使用工作台完成复核。

**样本设计**：

- 10 份 published/v0 或 v1 candidate。
- 10 份 draft/weak。
- 10 份 exact_required 边界。
- 10 份 list_rule/calculation。
- 可先 20，后扩 50。

**记录指标**：

- draft latency。
- review duration。
- auto/pending/unsupported/high_risk 比例。
- override 率。
- teacher_final mastery/gap 数量。
- next suggestion 可读性。
- bad_certified 是否 0。

**验收产物**：

- `qa_product_test_batch_YYYYMMDD/`
- `review_payloads.jsonl`
- `writeback_results.json`
- `learning_brain_readback.json`
- `qa_product_metrics.json`
- `FINDING_*.md`

#### B3 Runtime async / UX

不急着做大系统，只做 QA/test：

- Fast engine 同步返回。
- Best-Quality engine async/poll/stream。
- timeout fail-closed。
- cost guard。
- no provider -> unavailable，不回退冒充。

### C 线：Learning Brain 个性化闭环

#### C0 当前事实

- 写入真实文件后端已验证。
- next suggestion 已生成。
- 但学生可见进步体验还没形成。

#### C1 Grading-to-Progress View Model

**目标**：把 grading evidence 投影成学生可理解的进步报告。

**字段**：

- recent_weak_points
- repeated_missing_terms
- improved_points
- newly_mastered_points
- high_risk_pending_review
- next_training_actions
- evidence_links
- confidence / provenance

**红线**：

- 不新增 DB 表。
- 从现有 learning_evidence payload 读。
- 不把 draft/weak 当 mastery。

#### C2 学生可见报告

最小可交付：

- 静态 HTML 或 `/wechat-harness` preview。
- 展示 3 个维度：
  1. 这次扣在哪里。
  2. 和历史相比哪里变好。
  3. 下一步练什么。

#### C3 长期记忆策略

先文档 + 小样本，不急着大改：

- recent 细粒度保留。
- older 压缩为 stable weakness/mastery。
- teacher-final / llm_jury-final 永久保留 provenance。
- stale evidence 降权。

---

## 15. 异常处理原则（遇到预期外情况时按此执行）

### 15.1 Provider/key 异常

| 情况 | 处理 |
|---|---|
| key 缺失 | fail-closed，记录 provider_unavailable，不跑假模型。 |
| 只有 1-2 个 provider | 不 adjudicate，需要 >=3 quorum；可生成 PO packet。 |
| 某 provider schema 漂移 | normalize 前保留 raw；无法 normalize 则该 vote unavailable。 |
| 模型超时 | 记录 timeout，不自动重试超过预算；不能用其他模型替代命名。 |
| 用户批准 sanctioned cache | 只接受 question_id/point_id 完全匹配、source_run_id 明确、votes_fabricated=false 的 cache。 |

### 15.2 Source/anchor 异常

| 情况 | 处理 |
|---|---|
| textbook quote 不在 2026 教材 content_markdown | 降级 weak 或 source_gap。 |
| official_answer 看起来很权威 | 仍只作 weak，不可 auto。 |
| LLM 找到“近义教材表达” | 只能作为 search candidate，不可 verified。 |
| 纯数字短语命中教材 | 不单独 verified，需 calculation_spec/语境。 |
| node_code 不匹配 | 不硬填；可 candidate_node_code，但不是 authority。 |

### 15.3 Runtime/写回异常

| 情况 | 处理 |
|---|---|
| shadow 影响 legacy payload | 立即 BLOCKED，回滚接线，不继续测试。 |
| shadow 写了 Learning Brain | BLOCKED，违反 authority。 |
| teacher_reviewed=false 仍写入 | BLOCKED。 |
| non-QA/test 用户触发 writeback | BLOCKED。 |
| high_risk 未复核变 mastery | BLOCKED；teacher override 例外必须有 authority。 |

### 15.4 Worktree/并行会话异常

| 情况 | 处理 |
|---|---|
| 发现并行改同一文件 | 停止覆盖，先读 diff，必要时另起收口文档。 |
| 产物双目录 | 选更接近真实链路的一份 canonical，旧目录写 superseded，不删除。 |
| 脏文件涉及 BI/billing/web | 不碰，不 stage。 |
| 测试失败来自无关脏项 | 明确列出，不归因本任务；但相关测试必须绿。 |

---

## 16. 具体下一步 prompt 包

### 16.1 Prompt A：M7 Registry v1 compiler hardening

```markdown
你是鲁班评分引擎 Registry v1 compiler hardening agent。本轮任务是 M7：把 M5D source court 的 hard gate 固化进 candidate compiler simulation。

当前 canonical 输入：
- registry_v1_canonical_state_reconciliation_20260604：direct M6 publish_candidate=0。
- ai_expert_council_source_court_m5d_20260604：9/9 source_anchor_dispute=council_not_publish；25 点 action=6 approve_with_repaired_anchor / 5 split / 5 require_external_source / 4 rewrite / 4 drop / 1 keep_draft。
- registry_v1_candidate_dry_run_m6_20260604：M6 只证明 compiler/gate dry-run 不污染 runtime，不代表可发布。

目标：
- 固化 list_rule coverage==1.0：denominator 必须等于真实条目集，不能用 1 条 verbatim 锚覆盖整列 list_rule。
- 固化 council-final action gate：split_point / require_external_source / rewrite_point / drop_point / keep_draft / council_not_publish 都不能 auto。
- 对 approve_with_repaired_anchor 强制 deterministic reverify：quote 必须逐字命中 2026 教材 content_markdown。
- 运行 hardened candidate simulation，证明 candidate 不污染 v0、不被当正式 registry。
- 不生成正式 Registry v1，不接 runtime。

输出目录：
artifacts/luban_grading_artifacts/registry_v1_compiler_hardening_m7_20260604/

必须生成：
- m5d_input_audit.json
- council_action_gate_results.json
- list_rule_coverage_gate_audit.json
- repaired_anchor_reverify_results.json
- hardened_candidate_simulation.json
- blocked_from_auto_certification_after_m7.json
- v0_vs_hardened_candidate_diff.json
- FINDING_registry_v1_compiler_hardening_m7_20260604.md

新增测试：
tests/scripts/test_luban_registry_v1_council_hardened_candidate_m7.py

测试命令：
python -m pytest \
  tests/scripts/test_luban_case_rubric_source_court_m5d.py \
  tests/scripts/test_luban_registry_v1_candidate_dry_run_m6.py \
  tests/scripts/test_luban_registry_v1_council_hardened_candidate_m7.py \
  tests/services/construction_grading/test_artifact_runtime_gate.py \
  -q

FINDING 必答：
1. M5D 输入是否严格匹配 9 source_anchor_dispute / 25 points / action 分布？
2. list_rule coverage<1.0 是否全部 blocked from auto？
3. council_not_publish / split / rewrite / drop / external_source_required 是否全部 blocked from auto？
4. approve_with_repaired_anchor 是否全部 deterministic reverify？
5. 是否生成正式 registry？必须 NO。
6. v0 是否被覆盖？必须 NO。
7. M8 能否正式发布？如果不能，差什么 source repair / QA gate？
```

### 16.2 Prompt B：QA 产品测试 20 样本

```markdown
你是鲁班评分引擎 QA 产品测试 agent。本轮任务是用 /wechat-harness 跑 20 份 QA/test 复核样本，不冒充真人。

目标：
- 用真实浏览器或 TestClient + rendered HTML 跑 20 份 review。
- review_source 必须明确：operator_smoke / model_jury_teacher_review / manual_qa_teacher。
- 默认 operator_smoke，除非用户提供真人老师导出的 payload。
- 每份先 dry_run，再 writeback 到 QA/test 文件后端。
- 读回 Learning Brain synthesis 和 next suggestion。

必须输出：
artifacts/luban_consensus_gold/qa_product_test_batch_20260604/
- sample_manifest.json
- review_payloads.jsonl
- dry_run_results.json
- writeback_results.json
- readback_memory_events.json
- learning_brain_synthesis.json
- next_suggestion_preview.json
- qa_product_metrics.json
- screenshots/ 或 rendered_html/
- FINDING_qa_product_test_batch_20260604.md

指标：
- review_duration_seconds
- auto/pending/high_risk/unsupported 比例
- override 率
- writeback_count
- mastery/gap 数
- next suggestion count
- bad_certified 必须 0

红线：
- 不写生产用户。
- 不把 operator 写成 manual_qa_teacher。
- AI-Draft 未复核不写 LB。
- high_risk/unsupported 未确认不 mastery。
```

### 16.3 Prompt C：Learning Brain 学生可见进步报告

```markdown
你是 Learning Brain 个性化闭环 agent。本轮任务是基于现有 teacher-review / llm_jury writeback 产物，设计并实现最小 Grading-to-Progress view model，让学生能看到“我哪里错、哪里进步、下一步练什么”。

输入：
- artifacts/luban_consensus_gold/e2e_runtime_teacher_review_smoke_v2_20260604/
- artifacts/luban_consensus_gold/teacher_review_real_writeback_v2_20260604/
- artifacts/luban_consensus_gold/model_jury_teacher_review_pilot_20260604/
- LearnerStateService / learning_evidence read model 相关代码。

目标：
- 不新增表。
- 从 learning_evidence payload 生成 progress view model。
- 输出学生可见 JSON + HTML/markdown preview。

字段：
- recent_weak_points
- repeated_missing_terms
- newly_mastered_points
- pending_review_points
- evidence_examples
- next_training_actions
- confidence/provenance

产物：
artifacts/luban_consensus_gold/grading_to_progress_view_model_20260604/
- progress_view_model_sample.json
- progress_report_preview.html 或 .md
- source_event_manifest.json
- FINDING_grading_to_progress_view_model_20260604.md

红线：
- 不新增第二套 memory。
- 不把 weak/draft/pending 当 mastery。
- 不让 RAG 成为评分 authority。
```

---

## 17. 计划自检

### 17.1 当前最大风险

1. **把 candidate dry-run 误读成正式 registry。**
   - 对策：M6 只能读作 compiler/gate dry-run 证据；M7 后仍必须带 simulation / formal_registry_emitted=false。

2. **把 AI Expert Council 误读成 PO/human。**
   - 对策：`review_source=ai_expert_council_final` / `reviewer_type=ai_expert_council`；必须 `human_reviewed=false`、`po_reviewed=false`。

3. **把 AI council 误读成 textbook source authority。**
   - 对策：source authority 只认 2026 教材 `content_markdown` exact/verbatim match；AI vote 只能下调或建议改写。

4. **计划线太多，重新变成大平台叙事。**
   - 对策：只保留 A/B/C 三线；每线都必须有 1 个可验证产物。

5. **Learning Brain 变成抽象画像而非证据闭环。**
   - 对策：所有建议必须能点回 learning_evidence / grading point。

### 17.2 当前最优下一步

唯一最优主动作已更新为：

> **A 线 M7 Compiler Hardening。**

理由：

- M5D 已证明直接 publish_candidate=0，继续跑 M6 会误导。
- 它把当前最大风险 list_rule 半锚过度给分固化成 compiler hard gate。
- 它能验证 6 个 repaired anchor 是否真的可 deterministic exact match。
- 它不会污染 production。

B/C 可并行，但不应抢走 A 线 M7 的主线地位。


## 18. M8 canonical WEAK-GO + M9 beta_shadow source assault (2026-06-04)

- **M8 canonical verdict = WEAK-GO**（脚本自评 GO 已被独立 Opus 对抗验证下调；见 `artifacts/luban_grading_artifacts/v1_alpha_grand_sprint_m8_20260604/canonical_m8_verdict_override.json`）。
- 下调理由：57 source_gap 未清、auto 正向路径未压测（alpha_auto_count=0）、GPT5.5 skeptic 不可用单大模型终裁。
- 安全不变量全成立：12/12 verified 锚独立复核在教材、source_mismatch=0、legacy_equal=true、production_runtime_connected=false、formal_registry_emitted=false、v0 未覆盖。
- **M9** 对 57 source_gap 发起 source assault（案例判断句分流到 external_source/keep_draft，不当教材源）、编译 beta_shadow 候选、压测 auto 正向路径、产出可解释产品纵切，最终给 M10 gated beta 的 GO/WEAK-GO/NO-GO。
- alpha_shadow 不得偷渡成 beta，beta_shadow 不得偷渡成 production。

### 18.1 M9 v1 Beta Shadow Grand Sprint 结果（2026-06-04，canonical = WEAK-GO）

产物：`artifacts/luban_grading_artifacts/v1_beta_shadow_grand_sprint_m9_20260604/`；脚本 `scripts/run_luban_v1_beta_shadow_grand_sprint_m9.py`；测试 `tests/scripts/test_luban_v1_beta_shadow_grand_sprint_m9.py` + `tests/integration/test_luban_v1_beta_shadow_product_loop_m9.py`（全套 M3.5→M9 共 45 passed）。

- **M9 verdict = WEAK-GO**。新轨 source-backed = **18**（M8 的 18 未被推高）；M9 确定性新增 = **0**。诚实根因：M5D 的 6 个 `approve_with_repaired_anchor` 点**正是 M7 的 6 个 council-safe 点**，已在 baseline 18 内；其余 57 gap 无 verbatim 教材锚，需 calc/list spec 修复或外部源（M10 供给工作，不可伪造）。
- **beta_shadow 候选已编译**：`registry_v1_beta_shadow_candidate.json`，status=`beta_shadow_candidate`，formal_registry_emitted=false，v0_overwritten=false，production_runtime_connected=false。候选总 auto preview = **87**（= v0 只读骨干 69 textbook 点 + 新轨 18），但**口径取保守新轨 18** 判 GO/WEAK-GO，避免拿 v0 既发布点充数。
- **安全不变量全 0/通过**：official_answer_as_textbook=0、model_vote_as_source=0、council_vote_as_source=0、list_rule_partial_anchor_auto=0、source_mismatch=0、bad_certified=0；18/18 beta 提升点逐字锚独立复核在 2026 教材（含用「label 最长逐字子串命中」重定位 M5D 修复锚）；legacy unchanged；无 live call（复用 M5R/M5D 33 缓存票，无伪造）。
- **产品纵切已跑通**（复用 full100 真实 ai_draft_shadow 样本，dry-run、writeback=false）：grading→point evidence→blocked reason→diagnosis→Learning-Brain event→learner profile→personalization context pack→**12 张 learner-visible study card**（哪里错/为什么/教材证据/拦截原因/下一步练什么/可复测）。
- **M10 = WEAK-GO（不直接 GO）**。一条主线：**继续 source/calc/list supply 修复，把新轨 source-backed 点从 18 推向 ≥50**（优先 calc spec 补全 + list_rule 真实分母去虚增 + external_source 工单），再评估 M10 gated beta；**不要先扩 QA 样本**。residual queue 见 `bad_case_review_queue_m9.jsonl`（ai_draft 自证、尚未 source-backed 的点，属待修复非违规）。


## 21. M19B corrected canonical patch (2026-06-05)

**corrected canonical verdict（固化，覆盖早期 _20260604 草稿与未修正的 risk 语义）**：
- **M19B limited production default candidate = GO**（仅 1% qa/operator 可逆 config DRY-RUN 候选，非真实 flip）。
- **production default flip = NO-GO**，直到 M19C 显式 human-owner authorization 执行。
- **broad production default = NO-GO**；**canonical learner truth write = WEAK-GO/NO-GO（未开）**；**production v1 = NO-GO**；**production default 仍 OFF**（default_flip_executed=false）。

**两处 risk 修正**：
1. **rollback 3paths 旧 false = measurement bug**：withdraw recover_ms(~1451ms) 含 no-flag legacy grading 延迟（每 turn ~1.4s），≠ rollback 状态变更延迟；env_kill(~16ms)/registry(~14ms) 才是真 sub-second switch path；三路径 state 变更全部正确。M19C 必须分别报告 state_correct 与 recover_ms。
2. **council block = advisory bare-word artifact**：原始 vote 是无理由裸词 "block"（parser 忠实，非解析伪影）；裸词 block 不 veto，只有绑定 source/spec/list/safety 权威证据的 substantive reasoned block 才能 veto；council 永不替代 source/spec/gate 权威。

本 patch 不执行 M19C、不开 default、不删 _20260604/_20260605 artifacts（只记 supersession/correction）。详见 artifacts/luban_grading_artifacts/m19b_corrected_canonical_patch_20260605/。


## 22. M21S runtime supply bundle extraction (2026-06-05)

- 把 luban limited-default **运行时供给数据**从 gitignored review artifacts 抽成最小、签名、版本化的 **tracked bundle**：`deeptutor/services/construction_grading/runtime_supply/v1_limited_default/`（9 文件/~156K；machine 45/list 14/source_backed 23/typed_policy 97/signed registry）。
- loader 默认读 tracked bundle；artifacts 仅 `LUBAN_SUPPLY_DEV_ARTIFACTS=1` 显式 dev fallback；malformed/missing/hash-mismatch fail-closed，legacy intact。
- **clean checkout 无 artifacts：192 passed / 0 failed**（gate/registry/runtime_shadow/adjudicator/ws/m16/m17a）。review artifacts（FINDING/votes/ledgers/4-model eval cache）仍排除、非 runtime authority。production default 仍 OFF。
