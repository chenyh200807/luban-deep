# ADR-006: Supabase Knowledge Base Reuse And Source Manifest Mapping

状态：Accepted

日期：2026-04-24

---

## 1. 决策

建筑实务互动课堂 P0 必须复用 DeepTutor 现有 Supabase RAG 知识库，不允许为 OpenMAIC 计划新建第二套课堂专用知识检索入口。

唯一检索入口仍然是：

- `RAGService`
- `rag` tool
- `construction-exam` 默认知识库绑定

课堂生成链路只能通过 `RAGService` 获取 evidence，再由 `SourceIngestionService` 把 evidence 规范化为 `source_manifest`。生成器不得直连 Supabase 表，也不得把 `kb_chunks` 或 `questions_bank` 直接当作 lesson 内容 truth。

---

## 2. Supabase 知识库扫描结果

2026-04-24 本地配置与 Supabase REST 扫描结论：

- `SUPABASE_RAG_ENABLED=true`
- `SUPABASE_RAG_DEFAULT_KB_NAME=supabase-main`
- `construction-exam` 通过现有 runtime defaults / alias 进入同一只读 Supabase RAG。
- `kb_chunks` 总量：15432。
- `questions_bank` 总量：4638。

`kb_chunks` 结构：

- 核心列：`chunk_id / rag_content / source_type / source_doc / card_title / standard_code / node_code / taxonomy_path / page_num / metadata / content_hash / embedding`
- 来源分布：
  - `standard`: 13912
  - `textbook`: 1199
  - `exam`: 312

`questions_bank` 结构：

- 核心列：`id / question_type / source_type / source / exam_year / node_code / source_chunk_id / cited_standard_codes / grading_keywords / grading_rubric / tags / attributes / source_meta / embedding`
- 题型分布：
  - `single_choice`: 1674
  - `multi_choice`: 978
  - `case_study`: 1961
  - `calculation`: 15
- 来源分布：
  - `REAL_EXAM`: 1050
  - `TEXTBOOK`: 1601
  - `TEXTBOOK_ASSESSMENT`: 687

建筑实务高频考点粗略覆盖：

| Topic | `kb_chunks` 命中 | `questions_bank` 命中 |
| --- | ---: | ---: |
| 大体积混凝土 | 40 | 48 |
| 网络计划 | 41 | 38 |
| 施工索赔 | 136 | 63 |
| 屋面防水 | 150 | 28 |
| 深基坑 | 1266 | 243 |
| 脚手架 | 264 | 163 |
| 模板工程 | 262 | 185 |
| 混凝土浇筑 | 196 | 未扫描 |
| 质量事故 | 20 | 9 |
| 竣工验收 | 130 | 48 |

真实 `RAGService(provider='supabase')` smoke 结论：

- `mass_concrete / network_plan / claim / roof_waterproof / deep_foundation / quality_accident` 均能返回非空 evidence。
- evidence 已能混合命中 `standard / textbook / REAL_EXAM / TEXTBOOK_ASSESSMENT`。
- 当前返回给上层的 `sources` 不稳定保留 `_source_table` 与完整 metadata；P0 必须补齐 evidence-to-source-manifest mapper，不能让 citation 丢失 `kb_chunks` 与 `questions_bank` 的来源区别。

结论：

- 当前知识库已经足够支撑 P0 证据驱动生成试点。
- 但在 A4.5 之前必须先补 `RAGEvidence` contract patch，确保上层稳定拿到 `source_table / source_type / stable_id / metadata`。
- 没有 `source_table` 的 evidence 不允许进入 `source_manifest`，最多进入 debug trace。

---

## 3. Root Cause

上一版计划已经有 `SourceManifest`，但它更偏“上传资料和版权治理”。如果不单独收口现有 Supabase KB，研发很容易走偏：

- 只接 `kb_chunks`，丢掉 `questions_bank` 的真题、案例题和评分关键词资产。
- 绕开 `RAGService` 直连 Supabase，制造第二套检索入口。
- 把 Supabase 表结构直接泄漏进 `lesson_ir`，让播放器和导出依赖数据表细节。
- 生成器拿到文本后只写自然语言引用，不写可验证 provenance。

这些都会导致同一个知识事实长出两套 authority。

---

## 4. 一等业务事实

系统必须稳定维护的知识事实是：

> 建筑实务课堂生成所用的知识证据来自现有 `construction-exam` RAG 绑定，且每条进入课堂的关键结论、题目、评分点都能追溯到 `kb_chunks` 或 `questions_bank` 的稳定来源。

---

## 5. Authority 边界

唯一检索 authority：

- `RAGService`

唯一来源登记 writer：

- `SourceIngestionService`

唯一课程内容 writer：

- `LessonIRService`

允许：

- generation worker 调用 `RAGService.search(...)`
- `SourceIngestionService` 把 `evidence_bundle.sources` 规范化为 `source_manifest`
- generator 只引用已注册 `source_id`

禁止：

- generator / worker / router 直连 Supabase 表或 RPC
- 新建 `exam_classroom_kb_chunks`、`classroom_sources` 等课堂专用 mirror truth
- 把 `questions_bank` 当成非 P0 资产忽略
- 在 `lesson_ir` 中保存 Supabase 原始行作为内容 truth
- 把 `source_doc` 文本当作版权结论

---

## 6. KnowledgeSourceRef

### 6.1 RAGEvidence Contract

`RAGService` 返回给课堂生成链路的每条 evidence 必须先规范化为：

```ts
type RAGEvidence = {
  evidence_id: string
  kb_id: string
  provider: 'supabase'
  source_table: 'kb_chunks' | 'questions_bank'
  source_type: string
  content: string
  score: number
  metadata: {
    chunk_id?: string
    question_id?: string
    source_doc?: string
    card_title?: string
    standard_code?: string
    node_code?: string
    taxonomy_path?: string
    page_num?: number
    exam_year?: number
    source_chunk_id?: string
    grading_keywords?: string[]
    grading_rubric?: unknown
    content_hash?: string
  }
}
```

硬规则：

- `source_table` 必填。
- `source_type` 必填。
- `kb_chunks` evidence 必须有 `chunk_id`。
- `questions_bank` evidence 必须有 `question_id`。
- `node_code / standard_code / exam_year / content_hash` 如果原始 evidence 中存在，必须保留。
- `content` 只供生成和评估摘要使用，不得成为唯一 citation truth。

### 6.2 KnowledgeSourceRef

`SourceManifestItem.provenance` 必须能表达现有知识库 evidence：

```ts
type KnowledgeSourceRef = {
  kb_id: 'construction-exam' | 'supabase-main' | string
  retrieval_provider: 'supabase'
  source_table: 'kb_chunks' | 'questions_bank'
  chunk_id?: string
  question_id?: string
  source_type?: string
  source_doc?: string
  card_title?: string
  standard_code?: string
  node_code?: string
  taxonomy_path?: string
  page?: number
  exam_year?: number
  source_chunk_id?: string
  content_hash?: string
}
```

映射规则：

- `kb_chunks.chunk_id` -> `provenance.chunk_id`
- `kb_chunks.source_doc` -> `provenance.source_doc`
- `kb_chunks.standard_code` -> `provenance.standard_code`
- `kb_chunks.page_num` -> `provenance.page`
- `questions_bank.id` -> `provenance.question_id`
- `questions_bank.source_chunk_id` -> `provenance.source_chunk_id`
- `questions_bank.exam_year` -> `provenance.exam_year`
- `questions_bank.grading_keywords` 可作为 rubric evidence，但不能直接替代人工评分规则

---

## 7. 默认版权分类

默认分类必须保守：

- `kb_chunks.source_type=standard`
  - `source_type=official_public`
  - `copyright_level=public_official`
  - 商业/公开导出仍需按机构法务策略确认
- `kb_chunks.source_type=textbook`
  - 若 `source_doc` 命中机构自有/授权 allowlist：`tenant_owned` 或 `licensed`
  - 否则进入 `review_required`
- `kb_chunks.source_type=exam`
  - 默认 `licensed` 或 `official_public` 待人工确认
  - 不得自动公开分发
- `questions_bank.source_type=REAL_EXAM`
  - 可用于教学与评分 evidence
  - 公开/商业导出必须进入 legal review
- `questions_bank.source_type=TEXTBOOK / TEXTBOOK_ASSESSMENT`
  - 只能在机构授权范围内使用
  - 未确认授权时不得 `published`

不允许把“能检索到”推导成“能公开发布”。

---

## 8. Knowledge Coverage Gate

每次一键生成前必须执行知识库覆盖预检：

- topic outline 至少有 `standard` 或 `textbook` evidence。
- quiz/case scene 至少有 `questions_bank` 或 `exam` evidence。
- case rubric 必须有题库、教材评估题、真题或明确人工 rubric 来源。
- 若某 scene 的 evidence 不足，必须写入 `quality_report.warnings` 或 `blockers`，不得静默编造。
- P0 试点课堂若没有 `questions_bank` case/rubric evidence，不得生成正式 `case` scene；只能降级为 `slide / whiteboard / quiz`，并写入 `source_gap`。

`KnowledgeCoverageReport` 最小结构：

```json
{
  "topic": "施工索赔",
  "source_family_coverage": {
    "standard": {"count": 5, "node_codes": ["..."], "confidence": 0.86},
    "textbook": {"count": 3, "confidence": 0.81},
    "exam": {"count": 1, "confidence": 0.74},
    "questions_bank": {
      "single_choice": 8,
      "multi_choice": 4,
      "case_study": 7,
      "has_grading_rubric": true
    }
  },
  "can_generate": {
    "slide": true,
    "whiteboard": true,
    "quiz": true,
    "case": true
  },
  "source_gaps": [],
  "risk_level": "low"
}
```

P0 阻断规则：

- 关键结论无 source：不能 `approved`。
- 案例题无 rubric evidence：不能 `approved`。
- 无 `questions_bank` case/rubric evidence：不能生成正式 `case` scene。
- 知识库覆盖不足但仍可教学：进入 `review_required`。
- `quality_accident` 这类低覆盖主题必须标记为 `source_gap`，优先补知识库或降级试点范围。

---

## 9. 生成链路约束

生成主链路必须固定为：

```text
RAGService
-> RAGEvidence
-> SourceIngestionService
-> SourceManifest
-> KnowledgeCoverageReport
-> Evidence-aware Generation
-> Lesson IR
-> LessonQualityEvaluator
-> Review Gate
```

`retrieve_sources` 阶段必须输出：

```json
{
  "kb_id": "construction-exam",
  "query_plan": ["outline", "scene", "quiz", "case"],
  "evidence_bundle_ids": ["..."],
  "source_family_coverage": {
    "standard": 3,
    "textbook": 2,
    "exam": 1,
    "questions_bank": 4
  },
  "source_gaps": []
}
```

生成器输入只能拿到：

- 注册后的 `source_id`
- 必要的短 evidence 摘要
- citation payload
- source gap 标记

禁止把整表、整份题库、整段不可追溯资料直接塞进 prompt。

---

## 10. 非目标

本 ADR 不解决：

- Supabase 知识库入库、清洗、重建 embedding
- 题库版权的最终法律判断
- 新建知识管理后台
- 替代 `contracts/rag.md`
- 替代 ADR-004 的上传资料 ingestion

---

## 11. 必测项

- `test_generation_uses_rag_service_not_direct_supabase`
- `test_source_manifest_maps_kb_chunks_and_questions_bank`
  - `test_evidence_bundle_preserves_source_table`
- `test_rag_evidence_has_stable_id`
- `test_evidence_without_source_table_rejected`
- `test_questions_bank_case_study_sources_can_be_cited`
- `test_topic_outline_requires_standard_or_textbook`
- `test_quiz_requires_questions_bank_or_exam_evidence`
- `test_case_requires_rubric_evidence`
- `test_low_kb_coverage_creates_source_gap`
- `test_case_scene_without_rubric_evidence_cannot_approve`
- `test_generator_cannot_reference_unregistered_kb_source`
