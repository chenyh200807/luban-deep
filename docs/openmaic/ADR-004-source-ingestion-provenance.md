# ADR-004: Source Ingestion And Provenance

状态：Accepted

日期：2026-04-24

---

## 1. 决策

P0 新增来源治理 contract：所有进入 `lesson_ir` 的关键知识点、引用、外部素材、用户上传资料，都必须能回指 `source_manifest`。

资料解析与来源治理不新增第二套知识检索工具。知识召回仍复用既有 `rag` 工具；本 ADR 只定义 source ingestion、source chunk、citation、版权等级和发布 gate。

现有 Supabase RAG 知识库的复用和 `kb_chunks / questions_bank` 到 `source_manifest` 的映射，以 [ADR-006-supabase-knowledge-base-reuse.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-006-supabase-knowledge-base-reuse.md) 为准。

---

## 2. Root Cause

一键生成课堂的最大风险不是“没生成出来”，而是：

- 生成内容看似完整，但来源不清
- 教材/规范/机构讲义/网页资料混用后无法追责
- 导出和公开发布时踩版权风险
- 关键结论无法回到 source chunk，人工审核只能凭印象判断

如果来源治理只是原则，不变成字段和 gate，后期会在导出、销售、机构审核阶段集中爆雷。

---

## 3. 一等业务事实

系统必须稳定维护的来源事实是：

> 课堂中的关键结论和素材来自哪里、允许怎么用、是否可以发布，必须在生成、审核、导出链路中可追踪、可阻断。

---

## 4. Authority 边界

来源治理的唯一 writer：

- `SourceIngestionService`

它负责：

- 解析上传资料和授权资料
- 规范化既有 RAG evidence 为 `source_manifest`
- 生成 source chunk metadata
- 生成或更新 `source_manifest`
- 计算版权和允许使用范围的初始分类

知识检索的唯一入口仍是 `RAGService`。`SourceIngestionService` 不替代 `RAGService`，只负责把可用 evidence 登记成可引用、可审核、可阻断的 source。

禁止：

- scene generator 临时捏造 citation
- 前端上传绕过 source ingestion 直接进入 `lesson_ir`
- exporter 忽略 `copyright_level`
- `web_unverified / unknown / forbidden` 源进入 `published`
- generator / worker / router 直连 Supabase 表绕过 `RAGService`

生成器只能引用已进入 `source_manifest` 的 `source_id`。

---

## 5. SourceManifestItem

```ts
type SourceManifestItem = {
  source_id: string
  source_type:
    | 'user_uploaded'
    | 'tenant_owned'
    | 'licensed'
    | 'official_public'
    | 'web_unverified'
    | 'unknown'
  copyright_level:
    | 'owned'
    | 'licensed'
    | 'user_private'
    | 'public_official'
    | 'unverified'
    | 'forbidden'
  allowed_use: Array<
    | 'private_study'
    | 'internal_training'
    | 'commercial_course'
    | 'public_distribution'
  >
  title: string
  uri?: string
  uploaded_by?: string
  license_note?: string
  expires_at?: string
  provenance?: {
    kb_id?: string
    retrieval_provider?: 'supabase' | string
    source_table?: 'kb_chunks' | 'questions_bank' | string
    document_id?: string
    chunk_id?: string
    question_id?: string
    page?: number
    paragraph?: string
    source_doc?: string
    standard_code?: string
    node_code?: string
    taxonomy_path?: string
    exam_year?: number
    source_chunk_id?: string
    content_hash?: string
  }
}
```

---

## 6. SourceChunk

P0 source chunk 至少保留：

- `source_id`
- `document_id`
- `chunk_id`
- `page`
- `paragraph`
- `text`
- `table_ref`
- `image_ref`
- `confidence`
- `copyright_level`
- `allowed_use`

若来源来自现有 Supabase RAG，则最小 provenance 必须覆盖：

- `kb_id`
- `retrieval_provider`
- `source_table`
- `chunk_id` 或 `question_id`
- `source_type`
- `source_doc`
- `node_code`
- `standard_code` 或 `exam_year`，如存在

PDF parsing 至少要保留：

- 标题层级
- 页码
- 段落
- 表格
- 图片位置

表格、规范条文、评分标准表必须尽量结构化，不得只作为不可追踪纯文本拼入 prompt。

---

## 7. Citation 规则

`lesson_ir.citations[]` 只能引用 `source_manifest` 中存在的 `source_id`。

关键结论必须满足至少一项：

- 有 source chunk citation
- 明确标记为常识性教学组织语句
- 明确标记为资料不足，需要 reviewer 处理

禁止：

- citation 指向任意 URL 但不在 `source_manifest`
- citation 指向不可发布素材却进入正式导出
- 生成器把来源说明写在自然语言里但不写结构化 citation

---

## 8. 发布与导出策略

按使用范围阻断：

- `private_study`：允许 `user_uploaded / user_private`，但必须标记不可公开
- `internal_training`：需要 `tenant_owned / licensed / official_public`
- `commercial_course`：必须 `owned / licensed / official_public`
- `public_distribution`：必须 `legal_review_passed`

一律禁止：

- `web_unverified` 进入 `published`
- `unknown` 进入 `published`
- `forbidden` 进入任何正式导出
- 未过 legal review 的内容做公开/商业导出

---

## 9. Source Ingestion Gate

P0 必须具备：

- PDF 段落、标题、页码解析
- 表格抽取和结构化 chunk
- 图片 provenance 与版权等级
- source chunk schema
- claim-source matching
- unknown source policy

不确定性：

- 复杂 OCR、复杂公式、施工图识别可以 P1/P2 增强。
- P0 若解析置信度不足，必须降级为 `review_required`，不能静默发布。

---

## 10. 非目标

本 ADR 不解决：

- 新建第二套 RAG 工具
- 复制 OpenMAIC 的解析 provider、prompt、schema 或 UI
- 完整法务流程自动化
- 所有复杂图纸、施工照片、网络计划图的自动理解

---

## 11. 必测项

- `test_source_manifest_item_schema_validation`
- `test_citation_must_reference_source_manifest`
- `test_unknown_source_cannot_publish`
- `test_forbidden_source_cannot_export`
- `test_private_user_upload_cannot_public_distribution`
- `test_table_chunk_keeps_page_and_source_id`
- `test_generator_cannot_create_unregistered_citation`
- `test_existing_kb_evidence_normalized_into_source_manifest`
