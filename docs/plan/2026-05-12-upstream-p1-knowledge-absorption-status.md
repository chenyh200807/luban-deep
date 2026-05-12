# Upstream P1 Knowledge Absorption Status - 2026-05-12

Status: Implemented locally

## Goal

Absorb the useful backend knowledge/RAG stability capabilities from `HKUDS/DeepTutor`
without adopting the upstream knowledge-product surface wholesale.

## Non-goals

- Do not merge upstream `main`.
- Do not replace our `RAGService` or add a second retrieval authority.
- Do not adopt upstream multi-user/PocketBase knowledge ACLs in this engineering batch.
- Do not add Book, Space, Co-writer, Zulip, Matrix, or NVIDIA NIM product surfaces.

## Single Authority

- RAG remains routed through the existing `RAGService` and knowledge router.
- Local KBs may have multiple physical index versions, but the active read path is selected
  from the active embedding signature.
- Attachment storage persists original files for preview and audit; it does not become a
  second message/session store.
- Chat transport remains `/api/v1/ws`; no new chat WebSocket route is introduced.

## Absorbed

1. Knowledge index versioning:
   - Added flat `version-N` index directories keyed by embedding signature.
   - Read path prefers a matching active signature and falls back to legacy storage.
   - `KnowledgeBaseManager` discovers versioned KBs and reports `index_versions`,
     `active_signature`, and `active_match`.

2. Invalid vector validation:
   - Added explicit embedding vector validation.
   - LlamaIndex embedding adapter fails early on null, empty, non-numeric, non-finite,
     count-mismatched, or dimension-mismatched vectors.
   - Persisted vector-store JSON is validated before retrieval.

3. Re-index API:
   - Added `POST /api/v1/knowledge/{kb_name}/reindex`.
   - Re-index writes a fresh version directory while preserving old versions.
   - Existing valid active index returns a no-op response unless the KB is flagged for reindex.

4. Document extractor:
   - Added bytes/path text extraction for PDF, DOCX OOXML fallback, and KB-supported text-like
     files.
   - Kept optional Office dependencies out of this batch; DOCX fallback works without
     `python-docx`.

5. Attachment store:
   - Added local disk attachment storage under runtime user data.
   - Added preview endpoint under `/api/attachments/...`.
   - Turn runtime persists uploaded attachment bytes and strips persisted base64 from stored
     message records while preserving current-turn runtime base64 for multimodal models.

## Deferred

- Full upstream knowledge UI components and index-version chips: useful product polish, but not
  required for backend capability use.
- XLSX/PPTX extraction with optional dependencies: defer until product upload scenarios require
  them; current batch avoids adding new runtime dependency weight.
- Multi-user knowledge access: requires product/security design against our Supabase member and
  learner-state authorities.

## Verification

- `python -m pytest tests/api/test_attachments_router.py tests/knowledge/test_manager_index_versioning.py tests/services/rag/test_index_versioning.py tests/services/embedding/test_validation.py tests/utils/test_document_extractor.py tests/services/storage/test_attachment_store.py tests/api/test_knowledge_router.py::test_reindex_kb_queues_background_task -q`
- `python -m pytest tests/api/test_knowledge_router.py tests/api/test_attachments_router.py tests/knowledge/test_manager_index_versioning.py tests/services/rag/test_index_versioning.py tests/services/embedding/test_validation.py tests/services/embedding/test_openai_compatible_adapter.py tests/services/rag/test_rag_pipelines.py tests/services/storage/test_attachment_store.py tests/utils/test_document_extractor.py -q`
- `python -m compileall -q deeptutor/api deeptutor/knowledge deeptutor/services/embedding deeptutor/services/rag deeptutor/services/storage deeptutor/services/session deeptutor/utils`
- `git ls-files -m -o --exclude-standard | xargs python scripts/check_contract_guard.py`
