# questions_bank 供给层版本化+软删：读者测绘与设计（task#31 / 上游吸收项②）

- **日期**: 2026-08-02
- **状态**: `read_only_mapping + 设计稿 + migration 审批单（未执行）+ 读侧收权代码（本分支）`。全程零远程写：Supabase 只跑 SELECT（Management API 只读探针），阿里云未触碰。
- **数据快照**: Supabase `zgupgizexqpwtajvghno` / `public.questions_bank`，live 只读探针 2026-08-02，`count = 4635`，42 列。证据产物见 `extractions/supply_soft_delete_20260802/`（探针脚本 + information_schema/约束/索引/FK/8 函数全文/视图定义 JSON）。
- **目标一句话**: 把"删行=手术"（07-30 计划被删行三查卡死）降为"删行=可回滚常规操作"——加软删列 + **读取面全量收权**（08-01 在案红线："软删列即使加上，读取面不收权则整个方案是自欺"）。

---

## 0. 范围与方法

| 项 | 值 |
|---|---|
| 事实 | `public.questions_bank` 全部行（唯一在服真值，生产 RAG pgvector 供给层） |
| 测绘单位 | **事实的全部消费者**（不以出过事的调用点为单位）：代码侧 Python 读者（RAG + 非 RAG）、库内读者（RPC/视图/触发器）、scripts 一次性读者、本地孪生语料 |
| 方法 | 双并行代码测绘（file:line 级穷举）+ live 只读 schema 探针（information_schema / pg_proc / pg_views / pg_constraint / pg_get_functiondef）+ 与 07-30/08-01 两份在案盘点交叉对账 |
| 写操作 | **0**（本文档所属分支只改仓库文件；migration SQL 为审批单草案，未在任何库执行） |

---

## 1. 读者测绘总账（关键发现）

### 1.1 在服读者（线上请求路径，9 个，**全部会读出软删行**）

RAG 链（全在 `deeptutor/services/rag/pipelines/supabase.py`，均无生命周期过滤）：

| # | file:line | 构造点 | 读的列 | 污染后果 |
|---|---|---|---|---|
| S1 | `supabase.py:2306-2312` | REST `questions_bank?question_stem=ilike.*…*&limit=3`（经 `_select` :3704-3742） | `_QUESTION_SELECT` 19 列（:57-62） | 全表可达；exact 命中即权威 |
| S2 | `supabase.py:2313-2318` | 同上 `stem=ilike` | 同上 | **最高权威路径**：命中铸 `question_exact_text` score=1.0（:2207），authority_rank=100（provenance.py:10-12）——retired 行压过一切教材/标准 |
| S3 | `supabase.py:2358-2365`（调用 :2223-2228） | RPC `search_questions_bank_text`，filter 双 `None` | RPC TABLE 19 列 | 过滤只能落在 DB 函数内（现无） |
| S4 | `supabase.py:2436-2445`（调度 :1625-1633） | RPC `search_questions_bank_vector`（exact 变体） | 同 + similarity | 铸 `question_exact_vector`（rank 95） |
| S5 | `supabase.py:2501-2510`（调度 :1615-1621） | RPC `search_questions_bank_vector`（主力变体） | 同 | primary + second pass 各跑一遍（:1533 / :1183-1197）；`_derive_exact_from_bank_rows`（:2453-2490）还会用其原始行客户端合成 S4 结果 |
| S6 | `supabase.py:3180-3186` | REST `id=in.(...)`（case group meta） | case_group 四列+id | 上游漏进的 retired 行在此解析组键 |
| S7 | `supabase.py:3209-3220` | REST `case_group_id=eq&case_row_canonical=not.is.false&question_type=eq.case_study&limit=12` | `_CASE_GROUP_ROW_SELECT` 23 列 | **最危险**：拉回检索从未评分的兄弟行进 `covered_subquestions`/覆盖分母（loop.py:1314-1325,1898-1916 消费）——**毒判分分母**，非仅上下文 |
| S8 | `assessment/blueprint_service.py:257,268`（filter 构造 :215-245） | REST `questions_bank?select=...&question_type=in&source_type=in&id=not.in` | 12 列 | 软删行被抽进正式测评卷（调用链：`POST /api/mobile/assessment/create` → member_console/service.py:8659/8712/8563） |
| S9 | `blueprint_service.py:375` | REST `select=id&limit=1` + `Prefer: count=exact` | count | 题库规模虚高，回传前端/BI（member_console/service.py:8585,8629,8694,8749） |

**lean 模式不减暴露**：`RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY`（retrieval_profiles.py:15-31）保留 S1-S5+S6/S7 全套；identity_only 分支（supabase.py:1240-1247）在 `_hydrate_case_group_bundle`（:1227）之后。

### 1.2 库内读者（live 探针实证，8 RPC + 1 视图，**全部零软删过滤**）

| # | 对象 | 形态 | 仓内调用者 | 备注 |
|---|---|---|---|---|
| D1 | `search_questions_bank_vector(vector,real,int,text,text)` | `WHERE embedding IS NOT NULL AND sim>threshold AND (filter…)` | S4/S5 | |
| D2 | `search_questions_bank_text(text,int,text,text)` | 四列 ILIKE OR | S3 | |
| D3 | `search_questions_bank_text_ranked(text,int,text,text)` | 同上+trigram 排名 | **零** | 未版本化遗留，仍是可达面 |
| D4 | `search_questions(vector,float8,int,int)` | 向量+year_filter | **零** | 同上 |
| D5 | `search_questions_by_keywords(text,int)` | pg_trgm `%` 相似 | **零**（SECURITY DEFINER） | 同上 |
| D6 | `match_questions(vector,float8,int)` | 向量全表 | **零**（SECURITY DEFINER） | 同上 |
| D7 | `get_questions_quality_stats_v2()` | 全表聚合质量统计 | scripts 侧 | 计数口径需表态（§3.6） |
| D8 | `refresh_syllabus_stats()` | 聚合 `count(*) group by node_code` → **UPDATE syllabus_tree.question_count** | — | 软删行会虚高考纲树计数 |
| D9 | 视图 `v_retrieval_questions` | `WHERE embedding IS NOT NULL`，显式 15 列 | **零** | 同为可达面 |

**硬发现：这 9 个库内读者的 SQL 全部不在仓库**（`supabase/migrations/` 32 文件零 `CREATE FUNCTION`；questions_bank 连 CREATE TABLE 都没有）。本次已把 8 函数 `pg_get_functiondef` 全文 + 视图定义抓回仓库（`extractions/supply_soft_delete_20260802/live_function_defs.json`），migration 审批单以此为回滚基线——**顺带首次把库内读者版本化进仓**。

**RLS 不能当软删闸**：表已 enable+force RLS，但全部生产读者走 SERVICE_ROLE_KEY（supabase.py:3714-3717；blueprint_service.py:308-330 key 优先级），service_role 绕过 RLS。

### 1.3 编译期/运维读者（scripts 触发，代码在 deeptutor/ 内）

| # | file:line | 连接 | 污染后果 |
|---|---|---|---|
| C1 | `construction_grading/full_knowledge_compiler.py:631-655`（psycopg2 readonly，SQL :644-648） | `select …9 列 from public.questions_bank where question_type in (…) and correct_answer is not null and options is not null` | 软删行进 governed answer-key release_candidate 与 content_hash 签名（m30/m31 棒） |
| C2 | `construction_grading/objective_governed_registry_extractor.py:119-145`（psycopg2，`QUESTIONS_BANK_DB_URL`） | `select question_id,…,official_answer from questions_bank` | **列名在生产 schema 不存在（question_id/stem 之外的 official_answer）——从未跑通 live，实走 fixture**（代码 :160-163 自记 blocker；db_registry liveness=needs_verification 印证） |
| C3 | `source_compiler/psql.py:43-49`（psql 子进程哨兵） | `to_regclass` + `count(*)`（<1000 报错） | 低：软删行计入 count 只会让哨兵更易过；B 批大删后反而要防 count 逼近阈值 |

### 1.4 纯下游消费者（不发查询，收权后自动干净）

mcq.py:74,84 / case_kernel.py:45,57 / audit.py / compiler_feedback.py:44 / feedback_ingest_bridge.py:38-47 / question_join_resolver.py:44 / assessment/coverage.py:66,86 / citations/normalizer.py:16、assembler.py:161 / capabilities/deep_question.py:118（ctx metadata key 白名单）/ agents/question/coordinator.py:189-692（消费 RAG anchor_payload）/ tutorbot/agent/loop.py:544,2427,2535,1314-1325,1898-1916 / 两端小程序 citation-format.js:90。策略层 supabase_strategy.py（select_sources/权重）与 retrieval_plan.py 表达不了行级过滤，不是收权点。

### 1.5 scripts/ 一次性读者（13 个，非在服）

audit_2026_compiler_supabase_coverage / audit_assessment_testset_p0a / audit_construction_grading_supabase_fields / rubric_coverage_report / audit_assessment_blueprint_coverage / smoke_construction_grading_supabase / build_luban_canonical431_case_rubric_bank / m30·m31·m26 三棒（经 C1/C2）/ compile_2026_knowledge_assets（内存 join）/ seed_assessment_topic_catalog_forms（经 C3）/ audit_rag_supabase_authority_m22s（存在性探测）。**处置**：审计类默认看全量（可显式 `--include-retired`），不强制收权；本轮不改。

### 1.6 本地孪生语料（DB 软删免疫=漂移风险）

`rag/historical_questions.py:20,105-127` 读 `DEEPTUTOR_HISTORICAL_QUESTION_BANK_DIR` 本地 JSON（source_type="question_bank"）。DB retire 不会 retire JSON 孪生。**处置**：登记为已知边界（§7 诚实边界），孪生同步不在本轮 change boundary。

### 1.7 对既有结论的订正与印证

- **订正 07-30"全库无 FK"**：live 有 2 条 FK 指向 questions_bank——self `parent_id` + **`user_logs.question_id_fkey`**。硬删被 user_logs 引用的行会直接报 FK violation——软删的又一硬论据。
- 印证 08-01"线上 CHECK 不在仓库"：live 实测 3 条 CHECK（question_type 17 值白名单 + 2 条 qb_is_valid_objective_row 质量闸）——**回滚回插必须过这些 CHECK**（§5 回滚三件套已计入）。
- 印证 db_registry 登记缺口：`contracts/db_registry.yaml:127-138` 只登记 C1/C2 两个直连点，**漏了唯一在服读者 S8/S9 与 RAG 侧 S1-S7**（且 url_envs 只写 QUESTIONS_BANK_DB_URL，S8/S9 实走 SUPABASE_URL）。本分支补登记。

---

## 2. 方案取舍：软删列 vs 快照表

| 维度 | 软删列（**选定**） | 快照表（搬走再删） |
|---|---|---|
| 读侧收权 | 一个谓词 `retired_at IS NULL`，9+9 读者统一 | 主表"干净"但删行照旧破坏性——**下游 6 张快照表 73 悬挂引用问题原样保留** |
| 回滚 | `UPDATE … SET retired_at=NULL`（行从未离开，id/embedding/tsv 全保） | 回插需过 3 条 CHECK + UNIQUE + identity 列 `overriding system value`，embedding 列 3072 维搬运易损 |
| 引用完整性 | user_logs FK、assessment_forms 快照、错题本引用**全部继续可解析**（读者看不见但 join 得到） | 全部立即悬挂（07-30 已实证 12865 事故形态） |
| 版本化 | `superseded_by` 自 FK 链 + 既有 `based_on_version`/`content_hash` 列天然衔接 | 需要额外世代表 |
| 先例 | notebook_card `archived_at is.null`（store.py:51,131）；canonical431 授权位；index_versioning version-N | questions_bank_cleanup_backup_20260730（仅作回滚保险，非读路径） |
| 成本 | 每读者一个谓词；embedding 索引仍扫 retired 行（HNSW 无部分索引，影响可忽略：retired ≤ ~15%） | 双表双真值=第 N+1 个 decider，违反 Single Authority |

**裁决**：软删列。快照表方案把"删行破坏性"原样保留，只是把手术台搬远了；软删列把破坏性动作变成可逆状态翻转，且与"下游引用面是删除第一判据"（07-30 §4）的既有裁决同构——引用面大的行永远可以只 retire 不 delete。

### 2.1 列设计（migration Part A）

| 列 | 类型 | 语义 |
|---|---|---|
| `retired_at` | timestamptz NULL | 非 NULL = 软删。**唯一生命周期判据**（不加 status 枚举——一个布尔事实一个列，防第二权威） |
| `retired_reason` | text NULL | 人读原因（CHECK：retire 必带 reason） |
| `retired_batch` | text NULL | 批次键（如 `B1_reingest_delete_safe_20260802`），指向 manifest；回滚按批 |
| `superseded_by` | bigint NULL FK→questions_bank(id) | 正主指针（重复家族 drop→keep 映射落库；CHECK：有 successor 必先 retired；禁自指） |

不新增：`version` 列（`based_on_version`+`content_hash` 已在）；`deleted_by`（manifest 承载）；部分唯一索引（**UNIQUE(original_id) 保留占号**：retired 行继续占住 original_id，同源重入库撞唯一约束大声失败——449 行 re-ingest 病的免疫机制，不是 bug）。

### 2.2 指针/授权位（canonical431 模式最小移植）

照抄 `runtime_supply/v_case_rubric_scored_canonical431/canonical_pointer.json` + `rubric_grader_v1._load_bank_slot`（:1583-1645）的两层分离：**完整性链**（ids+行数+内容 hash）与**治理链**（production_authorized）分开验，fail-closed 发声。

移植物 = **retirement batch manifest**（每个退役批一份，入库 `extractions/supply_soft_delete_20260802/manifests/`）：

```json
{
  "batch_id": "B1_reingest_delete_safe_20260802",
  "created_at": "…",
  "ids": [/* 精确 id 数组 */],
  "expected_row_count": 319,
  "retired_reason": "dup_reingest_strict_inferior_copy (07-30计划B1)",
  "backup_ref": "questions_bank_cleanup_backup_20260730",
  "rollback_sql_ref": "…/rollback_B1.sql",
  "production_authorized": false,
  "authorization_note": "待 owner 过目审批单后翻 true；未授权时任何执行器必须拒跑并发声"
}
```

执行器纪律（与 _load_bank_slot 同构）：`production_authorized is not True → 拒执行 + ERROR 发声`；`len(ids) != expected_row_count → 拒执行`（完整性）；授权只管"能不能动生产"，不减完整性校验。模板与 schema 说明随本目录入库；执行器脚本随 B1 执行任务交付（本轮不建——避免无消费者的提前建设）。

### 2.3 读侧收权（单一谓词权威，migration Part B + 代码）

新模块 **`deeptutor/services/questions_bank_liveness.py`** = 唯一过滤谓词定义点：

- `LIVE_ROW_FILTER = {"retired_at": "is.null"}`（PostgREST 形态，先例：notebook_card/store.py:51）
- `apply_live_row_filter(params)`：幂等注入谓词；所有 REST 读者（S1,S2,S6,S7,S8,S9）经它构造查询——**不是每个调用点各自写 WHERE**。
- `SOFT_DELETE_FILTERED_DB_READERS`：8 RPC + 1 视图清单常量，锚定 DB 侧收权面，静态测试用它对 migration 文件做穷举核对。
- RPC 通道（S3/S4/S5）在 **DB 函数体内**收权（migration Part B 对 8 函数 + 1 视图 CREATE OR REPLACE 加 `retired_at IS NULL`）——签名不变，客户端零改动即生效。**不给 RPC 返回列加 retired_at**（TABLE 签名一动，PostgREST schema cache 与所有调用方联动，违背最小移植）。

**部署顺序命门**（supabase.py:63-67 教训的镜像）：`retired_at=is.null` 过滤参数打在不存在的列上，PostgREST 对整条查询返 400 → "题库检索全断"。因此**硬顺序**：migration Part A（纯加列，零行为变化）先在生产 apply，本分支代码后合并部署。本分支保持未合状态直到 owner 执行 Part A（与"阿里云里程碑一次性合"工作流一致）。备选的运行时列探测方案（availability-probe 同款）因引入第二判据 + fail-open 窗口被否。

### 2.4 版本化语义

- **行级世代**：`superseded_by` 链 + `based_on_version`/`content_hash`（既有列）——重复家族 drop 行 retire 时写 `superseded_by=keep_id`，190 条 remap（07-30 `reference_remap.json`）即首批消费数据。
- **供给面版本**：本轮**不建**表级 version-N 快照（index_versioning 模式适用于文件资产，DB 供给层的"版本"由 migration 序列 + retirement manifest 序列共同构成审计链）。理由：表级快照 = 双真值。

### 2.5 计数口径表态（D7/D8/S9/C3）

质量统计（D7）、考纲树计数（D8）、`question_bank_size`（S9）一律**只算在服行**——软删语义就是"从供给面消失"。C3 哨兵阈值 1000 距 4635-590(全部 dup drop 候选) 仍有余量，不改。审计 scripts 默认全量（§1.5）。

---

## 3. Migration 审批单

见 `supabase/migrations/20260802000100_questions_bank_soft_delete.sql`（Part A 加列）与 `20260802000200_questions_bank_reader_soft_delete_filter.sql`（Part B 库内读者收权），逐条 SQL+影响行数+回滚 SQL 的审批单在 `extractions/supply_soft_delete_20260802/APPROVAL_SHEET.md`。**两个文件均未在任何库执行**；Part B 的回滚 SQL 逐函数取自 live `pg_get_functiondef` 原文（`live_function_defs.json`）。

## 4. 回滚三件套

1. **un-retire SQL**（按批）：`update public.questions_bank set retired_at=null, retired_reason=null, retired_batch=null, superseded_by=null where retired_batch=$1` —— 行从未离开，零回插、零 CHECK/UNIQUE 风险。
2. **manifest**（§2.2）：ids+expected_row_count+backup_ref——回滚后按 manifest 逐 id 核对行数与 content_hash。
3. **验证查询**：`select count(*) from questions_bank where retired_batch=$1`（回滚后=0）+ S1/S3/S5 三通道 smoke（exact ilike / text RPC / vector RPC 各打一发已回滚行的题面，确认重新可达）。

## 5. 测试与 CI 钉子

- `tests/services/rag/test_questions_bank_soft_delete_filter.py`：S1/S2/S6/S7 查询字典必含 `retired_at=is.null`（mock `_select` 捕参，**删掉谓词即红**）；liveness 模块单测。
- `tests/services/assessment/`：S8 filters + S9 count URL 必含谓词。
- migration 静态测试：Part B 文件必须对 `SOFT_DELETE_FILTERED_DB_READERS` 全部 9 个对象各有一条含 `retired_at IS NULL` 的 CREATE OR REPLACE——**漏一个库内读者即红**（把"仓库外 RPC"钉进 CI 的最小办法）。
- contract_guard：supabase.py 属 rag protected+sensitive 面，contracts/rag.md 增补软删条款 + index.yaml 登记域测试 + cp 打包副本。

## 6. 数据来源路径（可复查）

- live 证据：`docs/原始数据/数据盘点/extractions/supply_soft_delete_20260802/{readonly_schema_probe.py, live_schema_evidence.json, live_function_defs.json}`
- 代码测绘 file:line：本文档 §1（双 agent 穷举，工作底稿在分支 artifacts/，被 .gitignore，正文已收全量结论）
- 在案交叉：07-30 污染盘点 §4 可达面、08-01 题型重标 §软删预警、08-01 C1 测绘（8 RPC 显式 TABLE 断言）

## 7. 缺口与诚实边界

- **未执行任何 migration**——影响行数是估算（Part A 触 0 行数据；Part B 触 0 行、只换函数体）；线上 schema 以执行时点 live 比对为准（已实证"线上 schema ≠ 仓库 migration 之和"）。
- C2 的列投影 bug（question_id/official_answer 列不存在）本轮**不修**——它从未跑通 live，修它是另一张工单；已在测绘留痕。
- 本地 JSON 孪生语料（§1.6）与 DB 软删的同步不在本轮边界。
- `assessment_forms.items_json` 等**快照持有面**不受读侧收权影响（快照是复制品不是读者）——已 retire 行的旧试卷继续可显示，这是有意语义（用户资产不动）。
- kb_chunks / standard_chunks 的软删不在本轮（questions_bank 先行；模式可复制）。
- 测试钉的是"查询构造含谓词"与"migration 文件含谓词"，**不是 live 行为**——live 三通道回归（§4-3）须在 Part A+B 执行后做完才可宣称"软删行不可达"（宣称纪律遵 Stop Gate）。
