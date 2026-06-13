# 登记闸门覆盖审计 — Registration-Coverage Audit

> Status: `Audit / read-only` — 2026-06-13
> Scope: 只读审计。本文件不新增 contract、不改代码、不替代 master plan。
> 审计员身份：单一权威「登记才能用」机器闸门覆盖审计员。
> 权威依据：`AGENTS.md` §0 Thin Wrappers Fat Skills / §5.6 复发机制+硬门槛 / §5.7 Single Authority Hard Gate / §5.8 Post-QA Root-Cause Gate。
> 配套文件：`current_state_gap_and_second_authority_audit.md`（第二权威风险 R1–R5）。本文件是它的**机器闸门视角补充**——前者问「谁在抢权」，本文件问「谁的权由机器确定性守序、谁只靠文档/自报 flag」。

---

## 0. 一句话结论

这套系统已经有**一圈成熟的 CI 机器闸门**（14 道在跑，证明闸门模式有效），但**漂移最危险的那批 typed object / compiled authority**几乎全靠**自报 boolean flag + 代码评审**守序，没有运行时/CI 确定性不变量。

**最关键的单一发现**：针对「8 套并行 typed shape」的收口闸门 `scripts/check_schema_registry.py`（+ `contracts/schema_registry.yaml`，9 schema 已登记）**已经写好、有测试，但其 main() 还没被接进任何在跑的 CI**——它自己的 docstring（第 32–53 行）写明因 `check_contract_guard.py` 有并行未提交 WIP，「PENDING HUNK」尚未应用。**这是一道"造好了但没通电"的闸**：登记表、校验器、测试全在，只差一个 import + 一行布尔与。这是把"8 套 schema 漂移"从纸面承诺变成机器强制的**唯一一步**。

**还差几道闸**：核心高优先 **3 道**（schema-registry 通电 / rich-leaf install gate 派生化 / mistake-code registry 化），中优先 **4 道**（evidence_source、event_type、capability、bot_id 的允许值闸），低优先 **3 道**（teaching_mode、scene、tool_name 的 lint 闸）。

---

## 1. 对照组 · 已登记 + 有机器闸门（证明闸门有效）

这些是「单一权威候选」中**已经被确定性机器闸门守住**的。每条确认：有闸吗 / 真跑吗。逐条经源码核实。

| # | 闸门 | 守的权威 | 实现 | 在跑吗 |
|---|---|---|---|---|
| C1 | **contract-guard 域测试覆盖** | 改 protected_patterns 必须同步改 domain test（违则 CI red） | `scripts/check_contract_guard.py:evaluate_changed_files` + `contracts/index.yaml` domains | ✅ `tests.yml` contract-guard job |
| C2 | **error-code-guard** | error_code（E0X/M0X/unknown）单一注册表 | `check_contract_guard.py:evaluate_emitted_error_codes` → `deeptutor/contracts/error_codes.py:ERROR_CODE_REGISTRY`；emit-site 静态扫 4 个权威模块；registry 还在 import 期自检 `ability_dimension` | ✅ 同上（emit-site 扫描）+ import-time 自检 |
| C3 | **node-id-guard** | knowledge_node_id（1A4XXXXX）必须 seed 在 learning graph | `check_contract_guard.py:evaluate_emitted_node_ids` → `deeptutor/services/taxonomy/construction_learning_graph.py:is_known_learning_graph_node` | ✅ 同上 |
| C4 | **question-lifecycle-authority-guard** | `question_lifecycle_scene` 写权 = orchestrator 单一 authority；禁止 shell 自判 scene | `check_contract_guard.py:evaluate_question_lifecycle_authority`（approved scene-writers 白名单 + 禁止 legacy 调用） | ✅ 同上 |
| C5 | **upstream-authority-absorption-guard** | TutorBot 是唯一业务身份；禁 `deeptutor/partners`、`/api/v1/partners`、standalone `deeptutor/learning` | `check_contract_guard.py:evaluate_upstream_authority_absorption` | ✅ 同上 |
| C6 | **websocket-allowlist-guard** | `/api/v1/ws` 是唯一 chat WS（反射 live app，alias/wrapper 绕不过） | `scripts/ci/check_websocket_route_allowlist.py` + `contracts/index.yaml:websocket_routes` | ✅ `tests.yml` 专步（装 server deps 后真反射） |
| C7 | **harness-authority-guard** | scene / grounding / exact 三个执行决策各单一 authority；两个执行 shell 只读不重判 | `scripts/check_harness_authority.py`（AST + 符号定义唯一性） | ⚠️ 脚本+测试在，CI 主 job 未直接列；`tests/` 覆盖。needs_verification 是否进 tests.yml |
| C8 | **model-authority-guard** | 默认 LLM model/provider 单一声明点 `deeptutor/config/defaults.py` | `scripts/check_model_authority.py`（第二处默认声明即 fail） | ⚠️ 脚本在；eval-gate 日志显示跑过（`tmp/eval-gate/*/logs/model_authority_guard.log`）。needs_verification 是否进 PR-blocking CI |
| C9 | **secure-routers fail-on-new** | 新 router 必须走鉴权基线 | `scripts/ci/check_secure_routers.sh` + `baselines/secure_routers_baseline.txt` | ✅ `tests.yml` |
| C10 | **RLS fail-on-new / live-RLS** | 新建表必须带 RLS；PII 表不得授 anon | `scripts/ci/check_rls_on_create_table.sh` + `check_live_rls_regression.sh` | ✅ `tests.yml`（live 步在缺 `SUPABASE_DB_URL` 时 skip-with-warning） |
| C11 | **rate-limit single-authority** | 限流单一 authority | `scripts/ci/check_rate_limit_single_authority.sh` | ✅ `tests.yml` |
| C12 | **llm-client-factory** | LLM client 只能从 factory 出 | `scripts/ci/check_llm_client_factory.sh` | ✅ `tests.yml` |
| C13 | **runtime-safety wiring** | runtime safety 接线 | `scripts/ci/check_runtime_safety_usage.sh` | ✅ `tests.yml` |
| C14 | **migration-uniqueness** | 迁移文件 14 位时间戳唯一 + 单调递增 | `scripts/ci/check_migration_uniqueness.sh` | ✅ `tests.yml` |
| C15 | **NameError gate (ruff F821/F811)** | 未定义名 / 静默重定义 | `tests.yml` 内联 `ruff check --select F821,F811` | ✅ `tests.yml` |

**对照组结论**：闸门模式在本仓库**确实有效且广泛**。它们的共同形态 = `单一权威源（registry / 白名单 / 基线文件）+ 确定性扫描器 + CI 非零退出`。漏网组缺的就是这个形态的后两段。

**对照组里两个 needs_verification（C7/C8）**：脚本与测试都在，但未在 `tests.yml` 的 contract-guard job 显式列为步骤（只在 eval-gate 本地链路有日志）。建议核实它们是否真的 PR-blocking，否则它们也算"半通电"。

---

## 2. 漏网组 · 是单一权威候选、但只有文档/约定/自报 flag（核心交付）

按 blast radius × 漂移可能性排序。每条：**权威 / 现状守序 / 漂移后果 / 该建的闸 / 优先级**。

### G1（最高）· 8 套 typed grading object schema —— 闸已造好但未通电
- **权威**：判分/采分点 typed object 的单一 canonical = `luban_grading_object.v1`（`deeptutor/services/construction_grading/unified_grading_object.py`），其余 8 套（`case_grading_artifact.v1` / `luban.rich_leaf_artifact.v0` / `luban_scoring_point_assets.v0.1` / `luban_m31_governed_objective_pointer.v1` / `luban_arbitration_gold_panel.v1` / `m35_ai_governed_gold.v1` / `compact_scoring_artifact.v1` / `luban_per_question_grading_object.v1`）是 deprecated、adapter-only。登记表已存在：`contracts/schema_registry.yaml`（9 schema + `drift_field_map` + `authority_vocabulary`）。
- **现状守序**：**机器闸门已写好但未在跑**。`scripts/check_schema_registry.py`（三条 fail 规则：未登记 schema / drift 字段名如 `weight`→`max_score` / 缺 `authority_source` 或 span-backed 点缺 `span_hash`）+ `tests/scripts/test_schema_registry.py` 都在。但该脚本 docstring 第 32–53 行自认：因 `check_contract_guard.py` 有并行未提交 WIP，**「PENDING HUNK」尚未 apply**，`evaluate_schema_registry` **没有**被接进 `check_contract_guard.py:main()`，也**没有**进 `.github/`。即：登记表权威建立了，强制还没通电。校验器 `validate_grading_object` 也**没有**被任何 runtime/CI 路径调用（只被 adapters import）。
- **漂移后果**：任何 agent 新建第 10 套 typed shape、或在 canonical schema 文件里写回 drift 字段名（`weight`/`canonical_answer`/`label`/`answer_key`），CI **不会 red**——直接复活「双/多 schema 漂移」，正是 KnowQL 禁区 D2 要防的。这是整个 KnowQL Phase A 的地基，地基的闸没通电。
- **该建的闸**：**通电既有闸**——apply docstring 里那段 4 行 hunk，把 `evaluate_schema_registry(changed_files)` 接进 `check_contract_guard.py:main()` 并入最终布尔；确认 `tests/scripts/test_schema_registry.py` 进 CI。可选第二步：把 `validate_grading_object` 接到 adapter 出口/落盘前做 runtime fail-closed。
- **优先级**：**P0**。成本最低（一个 import + 一行）、收益最大（把已成型的单一权威从纸面变机器）。唯一阻塞是等 `check_contract_guard.py` 的并行 WIP 落地——这是协调问题不是技术问题。

### G2（最高）· rich leaf 5705 采分点 runtime install —— 自报 flag，非 release-gate 派生
- **权威**：官方 reference answer / 教材 = 判分 key 唯一 canonical；rich leaf pack（`runtime_token_pack_v32_scoring_points.json`，5705 点 ≈ 官方 key 50x）是投影/弹药，不是 key。
- **现状守序**：**软护栏**。runtime 消费由**环境变量** `LUBAN_RICH_LEAF_RUNTIME_ENABLED` 控制（`deeptutor/services/construction_grading/rich_leaf_runtime.py:rich_leaf_runtime_enabled`，默认 OFF）；pack 自报 `candidate_only / review_only / runtime_install_allowed=False / quality_claim_allowed=False`。`compiled_registry_resolver.verify_bundle` 在**读时**有 4 道闸（schema pin / lane 签名 / status gate / hash pinning），但**写时无保护**，且「采分点 vs 官方 key 谁 primary」**没有一个 runtime deterministic 不变量**——全靠 artifact 自报 boolean。
- **漂移后果**：把 `LUBAN_RICH_LEAF_RUNTIME_ENABLED` 翻 true（或重写 bundle+pointer 让 hash 对上），5705 AI 采分点即可 install 进判分链，凭体量事实上盖过官方 key——第二权威落地（审计 R1 / 禁区 D3）。
- **该建的闸**：(a) 把 install 授权从 env-flag 升成**由独立 release gate 派生的 deterministic 闸**（owner action，非 KnowQL/agent 自翻）；(b) runtime 不变量：判分时官方 key 永远是 primary confidence 通道，采分点只能 `shape=supporting_evidence`；(c) 28 个 `skipped_no_textbook_provenance` 的 point 在任何 grading shape 里 fail-closed 不得出现。
- **优先级**：**P0**（blast radius 直接落到学生判分）。

### G3（中高）· 错因标签 taxonomy（mistake_type / miss_tags / misconception_tag）—— 无 registry，自由文本
- **权威**：应是**单一 controlled mistake-code registry**（Nexus 计划 §4.7 + 移动端 P0A 的 canonical mistake_tag schema）。
- **现状守序**：**无闸**。编译轴/LLM 产出的 `miss_tags`（如 `["漏列采分点"]`）、`misconception_tag`、`mistake_type`（`artifact_first_llm_judge.py:210` 处 `omitted/wrong_content/list_incomplete/near_synonym_not_exact` 等）是**自由字符串**，没有强制对齐到任何 registry。多个 worktree 各持一份 `error-taxonomy.md` 拷贝（源↔runtime 漂移）。
- **漂移后果**：第二套错因 taxonomy 苗头（审计 R4）。未登记标签直接写进 learning_evidence → 错因归因不可靠 → 个性化推荐错。
- **该建的闸**：(a) 建 `contracts/mistake_code_registry.yaml`（单一 authority）+ 一个 emit-site 扫描闸（仿 error-code-guard），LLM/编译产出的标签只能是 candidate，runtime 映射回 registry code，映不上进 review queue 不直接给学员；(b) 收敛散落的 `error-taxonomy.md` 拷贝为单一 registry，skill 侧引用而非各自拷贝。
- **优先级**：**P1**。

### G4（中高）· evidence_source —— contracts/index.yaml 列了，但只是 prose，无校验器
- **权威**：`contracts/index.yaml:learning_state_inference.allowed_evidence_sources`（`construction_grading` / `conversation_synthesis` / `assessment_testset`）。
- **现状守序**：**仅 prose**。硬编码值散在 `conversation_learning_evidence.py:77`（`"conversation_synthesis"`）、`learning_evidence.py:90`（`"construction_grading"`），但**没有任何 runtime/CI 校验器**把它们对回 index.yaml 的允许集。
- **漂移后果**：未登记的 evidence_source 写进 `learner_memory_events` → `learning_synthesis` 投影按 source 过滤时**静默丢数据** → scoring_point_map 等 read model 不全（审计 §5.8 forbidden 列表里"unregistered error_code in payload"同型，但 evidence_source 还没闸）。
- **该建的闸**：emit-site 静态扫描闸（仿 node-id-guard），把上述模块里的 evidence_source 字面量对回 `contracts/index.yaml` 的允许集；或在 `LearnerStateSupabaseWriter.write_item` 落盘前做 enum 校验 fail-closed。
- **优先级**：**P1**。

### G5（高）· event_type for learner_memory —— 允许值 prose-only，写入无校验
- **权威**：`contracts/index.yaml:learning_state_inference.allowed_event_type = learning_evidence`（学习脑写入只允许这一个 event_type）。
- **现状守序**：**仅 prose**。`deeptutor/events/event_bus.py:EventType` 另有内部枚举（SOLVE_COMPLETE/…），与 learner_memory 的允许值是两个语境；没有任何校验器阻止把非 `learning_evidence` 的 event_type 写进 `learner_memory_events`。
- **漂移后果**：写错 event_type → `learning_synthesis` 按 event_type 过滤时静默跳过 → 学习证据**静默丢失**（HIGH，因为是无声数据损失）。
- **该建的闸**：在 `learner_memory_events` 写入路径（`supabase_writer.py`）加 pydantic/显式校验，强制 `event_type == "learning_evidence"`，违则 raise，不静默落盘。
- **优先级**：**P1**。

### G6（高）· capability_name registry —— discovery-by-convention，无硬校验
- **权威**：`deeptutor/runtime/bootstrap/builtin_capabilities.py:BUILTIN_CAPABILITY_CLASSES`（chat/tutorbot/deep_solve/deep_question/deep_research/math_animator/visualize）。
- **现状守序**：**软闸**。`CapabilityRegistry.get()` 对未注册 capability 返回 None，路由静默降级到默认；无 CI 校验"被路由用到的 capability 名都已注册"。
- **漂移后果**：路由到未知 capability → 落默认 capability → **用户面行为未定义**（HIGH）。比 tool 更危险，因为 capability 接管整个对话。
- **该建的闸**：(a) orchestrator 路由处对未知 capability 硬失败而非静默降级；(b) CI 扫描 capability 名引用对回 `BUILTIN_CAPABILITY_CLASSES`。
- **优先级**：**P1**（但需先确认现状是否已有运行时硬失败——标 needs_verification：orchestrator 是否真静默降级）。

### G7（中）· bot_id registry —— resolver 返回 None，无硬闸
- **权威**：`deeptutor/contracts/bot_runtime_defaults.py:BOT_RUNTIME_DEFAULTS`（`construction-exam-coach` + 5 alias）。
- **现状守序**：**软闸**。`resolve_bot_runtime_defaults()` 对未知 bot_id 返回 None（不 raise）；alias 归一化在此处，符合 §Concept Discipline，但未知值无 CI/运行时拒绝。
- **漂移后果**：未知 bot_id → 默认 capability engine 选择未定义（MEDIUM）。
- **该建的闸**：orchestrator 入口对未知 bot_id 显式拒绝或归一化失败可观测；可选 CI 扫描。
- **优先级**：**P2**。

### G8（中）· prompt 模板库 —— 无 version / 无 hash / 无登记
- **权威**：`deeptutor/agents/*/prompts/{zh,en}/*.yaml`（9 个 agent 的 prompt），经 `PromptManager` 单例 + LRU cache 加载。
- **现状守序**：**无闸**。纯文本 YAML，无 checksum、无 version 字段、无登记表。in-process cache 只是延迟重读，不是写保护。
- **漂移后果**：agent 静默改 grader/judge prompt（注入或放松判分）→ 重启后全链路 LLM 行为被污染（判分宽严漂移、教学误导）。这是"AI 编程容易出错"的隐蔽面——prompt 是 authority 但当配置文件对待。
- **该建的闸**：给判分/judge 类关键 prompt 加 `prompt_version` + content_hash，落一个 `prompt_registry`（至少对 grading-critical prompt），CI 校验 hash；或纳入 schema-registry 同款 manifest 机制。
- **优先级**：**P2**（高 blast radius 但低漂移频率——prompt 改动通常显式可见，不像数据 ID 那样静默）。

### G9（中）· compiled authorities 写时保护（taxonomy / 概念 registry / 答案 key bundle）
- **权威**：frozen taxonomy（`deeptutor/services/taxonomy/compiled/construction_2026_taxonomy.compiled.json`）、concept_registry（`runtime_supply/v_concept_registry/concept_registry.json`）、objective answer key（`v3_objective_records_released_m31/*.json`）、case rubric slice。
- **现状守序**：**读时强、写时弱**。读时有 `verify_bundle` 的 hash pinning + 签名；但都是磁盘上 plain JSON，**写时无保护**：agent 可重写 bundle.json 并同步改 `canonical_pointer.json`，下次重启读时闸全过、污染落地。status flag（`release_candidate` / `published:False`）是 advisory，加载时不强制。
- **漂移后果**：concept_id→name_path 静默重映射（学员历史 state 指向漂移）、答案 key 翻转（MCQ 判分反转）、taxonomy label 漂移（学员面 label 全错）。
- **该建的闸**：(a) 把这些 compiled JSON 在 git 层设为需 PR 改（pre-commit 拒绝直改），(b) publish 脚本用 atomic write + 把 `published` 从自报升成 release-gate 派生（与 G2 同型），(c) 可选 runtime 启动期对 pointer↔bundle 做强一致校验并拒绝 unsigned 重写。
- **优先级**：**P2**（读时闸已挡住大部分误用；写时是 supply-chain 面，需 owner-action 才能触发）。

### 漏网组排序清单（紧凑版）

| # | 权威 | 现状守序 | blast radius | 该建的闸 | 优先级 |
|---|---|---|---|---|---|
| **G1** | 8 套 grading typed object → `luban_grading_object.v1` | 闸已造好（schema_registry guard+yaml+test）但**未通电**进 CI | 多 schema 漂移复活，KnowQL 地基崩 | **接既有 hunk 进 contract-guard main()**（registry+guard 已在） | **P0** |
| **G2** | rich leaf 5705 采分点 install vs 官方 key | env-flag + 自报 flag，无 runtime 权威序不变量 | AI 采分点凭 50x 体量盖过官方 key（学生判分） | install 闸由 release gate 派生 + 官方 key=primary 不变量 | **P0** |
| **G3** | 错因 taxonomy（mistake_type/miss_tags） | 自由文本，无 registry，多份拷贝 | 第二套错因 taxonomy，归因/推荐错 | mistake-code registry + emit-site 闸 | **P1** |
| **G4** | evidence_source 允许集 | index.yaml prose，无校验器 | 未登记 source → synthesis 静默丢数据 | emit-site 扫描闸 / 写入 enum 校验 | **P1** |
| **G5** | learner_memory event_type | index.yaml prose，写入无校验 | 写错 type → 学习证据静默丢失 | 写入路径强制 `==learning_evidence` | **P1** |
| **G6** | capability_name registry | discovery-by-convention，软降级 | 未知 capability → 用户面行为未定义 | 路由硬失败 + CI 扫描（先验现状是否已硬失败） | **P1** |
| **G7** | bot_id registry | resolver 返回 None | bot 默认 engine 未定义 | 入口硬拒绝/可观测 | **P2** |
| **G8** | prompt 模板库（判分/judge） | 无 version/hash/登记 | 静默改 prompt 污染判分链 | grading-critical prompt 加 version+hash registry | **P2** |
| **G9** | compiled taxonomy/concept/answer-key bundle 写时 | 读时强（hash pin），写时无保护，status 自报 | 静默重映射/答案翻转/label 漂移 | git-PR 锁 + atomic publish + published 派生化 | **P2** |

---

## 3. 还差几道闸

- **核心 P0：2 道**（G1 通电、G2 install 派生化）——其中 **G1 几乎零成本**（闸已造好，只差通电），是性价比最高的一步。
- **P1：4 道**（G3 mistake-code registry、G4 evidence_source、G5 event_type、G6 capability）。
- **P2：3 道**（G7 bot_id、G8 prompt registry、G9 compiled-bundle 写时保护）。
- **对照组待核实：2 道半通电**（C7 harness-authority、C8 model-authority 是否真进 PR-blocking CI）。

**一句话**：闸门模式本身已经被证明有效（14+ 道在跑），系统性漏洞不在"不会建闸"，而在**漂移最危险的 typed-object / compiled-authority / 错因 taxonomy 这批，权威序还停在"自报 flag + 代码评审"**，没走完"登记表 → 确定性扫描器 → CI 非零退出"的最后两段。**最该先做的不是建新闸，而是给 G1 那道已经造好的 schema-registry 闸通电**——这是把"8 套 schema 漂移"从纸面承诺变成机器强制的唯一一步，也是整个 KnowQL Phase A 的前置硬门槛。

---

## 附录 · 审计证据索引（绝对路径）

- 对照组闸门：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/scripts/check_contract_guard.py`（error-code/node-id/lifecycle/upstream/ws guards）、`scripts/check_harness_authority.py`、`scripts/check_model_authority.py`、`scripts/ci/*.sh` + `check_websocket_route_allowlist.py`
- CI 接线：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/.github/workflows/tests.yml`（contract-guard job）
- **G1 已造好未通电的闸**：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/scripts/check_schema_registry.py`（docstring 第 32–53 行 PENDING HUNK）+ `contracts/schema_registry.yaml`（9 schema）+ `tests/scripts/test_schema_registry.py`
- G1 canonical schema：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/services/construction_grading/unified_grading_object.py`（`validate_grading_object`，runtime 未接）+ `grading_object_adapters.py`
- G2 rich leaf install：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/services/construction_grading/rich_leaf_runtime.py`（`LUBAN_RICH_LEAF_RUNTIME_ENABLED` env flag）+ `compiled_registry_resolver.verify_bundle`
- G3 mistake_type emit：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/services/construction_grading/artifact_first_llm_judge.py:210`
- G4/G5 evidence_source/event_type：`contracts/index.yaml:learning_state_inference` + `deeptutor/services/learner_state/conversation_learning_evidence.py` / `learning_evidence.py` / `supabase_writer.py`
- G6/G7 registries：`deeptutor/runtime/bootstrap/builtin_capabilities.py`、`deeptutor/contracts/bot_runtime_defaults.py`
- 配套第二权威风险审计：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/plan/鲁班knowql/current_state_gap_and_second_authority_audit.md`（R1–R5）
- 权威纪律依据：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/AGENTS.md` §0 / §5.6 / §5.7 / §5.8
