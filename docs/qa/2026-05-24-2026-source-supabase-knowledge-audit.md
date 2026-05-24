# 2026 Source Data and Supabase Knowledge Audit

**Date:** 2026-05-24  
**Scope:** `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026` as raw source authority, compared with the current Supabase knowledge tables configured by `DB_URL` in the DeepTutor workspace `.env`.  
**Mode:** read-only filesystem inspection and read-only SQL queries. No production data was modified.

## Executive Judgment

The right next step is **not** to introduce a standalone graph database or a full automatic knowledge-graph extraction pipeline.

The `docs/2026` directory is already a structured source corpus: cleaned textbook JSON, enhanced textbook blocks, lecture JSON, standard JSON, exam JSON, taxonomy, and importer scripts. The highest-leverage path is to treat it as the **canonical source repository** and build a deterministic **knowledge compiler** that produces product-facing assets:

- concept pages
- case grading rubric projections
- misconception / error-pattern pages
- question-review capsules
- standard-clause evidence packs
- lecture teaching cards

Graph edges should be a downstream projection of compiled assets, not the main system.

## Karpathy Gate

**Assumptions**

- The business goal is to use `docs/2026` more fully in Luban/DeepTutor, not to build a demo graph.
- Supabase remains the current online knowledge store.
- `questions_bank`, `kb_chunks`, `standard_articles`, and `syllabus_tree` remain the production authorities unless a controlled migration explicitly changes that.

**Simplest Path**

1. Source availability manifest.
2. Stable source IDs and content hashes.
3. Deterministic compilers from source JSON into reviewable JSONL assets.
4. Dry-run coverage report against Supabase.
5. Controlled backfill of missing fields.
6. Lightweight graph projection only after field parity improves.

**Change Boundary**

- No database writes.
- No business-code changes.
- No new `/api/v1/ws` route, no new RAG authority, no parallel question bank.
- This report is the only new workspace artifact.

**Verification Target**

- File-level source availability evidence.
- Local JSON schema and field evidence.
- Supabase row counts, field fill rates, and relationship integrity evidence.
- Concrete compiler/backfill priorities.

## Source Inventory

Top-level file inventory:

| Source area | File count |
| --- | ---: |
| `讲义` | 344 |
| `题库` | 23 |
| `2026教材` | 20 |
| `标准文件` | 8 |
| `scripts` | 6 |
| `taxonomy` | 2 |
| `Supabase_Schema_Evaluation_Report.md` | 1 |

File-type inventory:

| Type | Count |
| --- | ---: |
| JSON | 375 |
| Python scripts | 6 |
| Markdown | 1 |
| `.DS_Store` | 23 |

JSON availability on this machine:

| State | Count |
| --- | ---: |
| Local/readable JSON | 266 |
| `compressed,dataless` JSON | 109 |

Important unavailable/dataless files:

- `taxonomy/FINAL_CLEANED_TAXONOMY2026.json`
- `题库/2017.../FINAL_CLEANED_EXAM_V2017.json`
- `题库/2019.../FINAL_CLEANED_EXAM_V2019.json`
- `题库/2024.../FINAL_CLEANED_EXAM_V2024.json`
- `标准文件/13、GB55003-2021...json`
- `标准文件/16、JGJ120-2012...json`
- `标准文件/20、GB50354-2005...json`
- `2026教材/第二次加强/FINAL_CLEANED_BOOK2026-9-166v3_fixed.json`
- `2026教材/第二次加强/FINAL_CLEANED_BOOK2026-167-221v3_fixed.json`
- `2026教材/第二次加强/v3_production_core_167-221.json`
- `2026教材/第二次加强/v3_production_enrichment_v2_167-221.json`
- `2026教材/第二次加强/v3_production_index9-166.json`
- `scripts/import_standards_to_supabase.py`

This is a real blocker for a source-authority audit. Some key source files exist as metadata but are not locally readable yet. Any compiler must start with an availability gate.

## Parsed Local Source Evidence

Readable JSON files parsed successfully: no JSON decode errors were found in the local/readable subset.

| Source class | Local files parsed |
| --- | ---: |
| book | 13 |
| standard | 5 |
| lecture bundles | 6 |
| lecture pages | 232 |
| question files | 10 |

Local record counts:

| Source class | Parsed records |
| --- | ---: |
| standards, nodes + content blocks | 6,467 |
| book records | 2,705 |
| question chunks | 1,375 |
| lecture bundle records | 382 |
| lecture page records | 387 |

Local question asset evidence:

| Signal | Count |
| --- | ---: |
| question chunks | 1,375 |
| nested exercises | 1,463 |
| exercises with `predicted_node` | 1,344 |
| exercises with `option_reasoning` | 188 |
| exercises with `pitfalls` | 29 |

Local exercise type distribution:

| Type | Count |
| --- | ---: |
| `single_choice` | 850 |
| `multi_choice` | 352 |
| `case_study` | 179 |
| `multiple_choice` | 82 |

Local lecture evidence:

| Signal | Bundle records | Page records |
| --- | ---: | ---: |
| `content_markdown` | 381 | 383 |
| `rag_content` | 381 | 383 |
| `node_code` resolvable | 381 | 384 |
| `knowledge_cards` | 359 | 349 |
| `structured_rules` | 322 | 325 |
| `key_parameters` | 257 | 262 |
| `assessment` | 186 | 201 |

Local standard evidence:

| Signal | Count |
| --- | ---: |
| `graph_relations` | 6,389 |
| `common_violations` | 6,385 |
| `synthetic_qa` | 6,371 |
| `logic_constraints` | 5,722 |
| `chunk_id` | 5,564 |
| `knowledge_enhancement` | 3,982 |

Important caveat: standard records were counted across both `nodes` and `content_blocks`, so the number is not a unique article count. It is still strong evidence that the raw source has richer standard-level structure than the current online projection.

## Source Quality Risks

### 1. Dataless Source Files

109 JSON files are not actually local. The audit can see their filenames and metadata, but cannot parse their content.

This especially matters because the unavailable set includes taxonomy, several real-exam years, three standard files, and key v3 textbook artifacts.

**Risk:** a compiler built today would silently under-compile the source corpus unless it fails closed on source availability.

### Dataless Remediation Runbook

Before compiler writeback gates, every blocked P0 taxonomy, standard, exam, or book source must be made physically local and re-inventoried.

1. Try CLI download:

   ```bash
   brctl download "$LUBAN_2026_SOURCE_ROOT/relative/path.json"
   ```

2. If CLI download fails, use Finder: select file, right click, choose download now.

3. Verify physical bytes:

   ```bash
   du -h "$path"
   stat -f "%z %B" "$path"
   ```

4. If macOS storage pressure blocks download, reclaim local snapshots:

   ```bash
   tmutil thinlocalsnapshots / 10000000000 4
   ```

5. Re-run inventory and record `download_owner`, `last_download_verified_at`, before/after dataless status, and before/after `sha256`.

If the source owner can provide a tarball, prefer `docs/2026/_force_local.tar` over fighting iCloud sync.

### 2. Standard Files Are Mixed Collections

Several standard JSON files are named as one standard but contain nodes from many standards. The local metadata itself reports high mismatch ratios:

| File | Primary standard | Mismatch ratio |
| --- | --- | ---: |
| `15、GB+51004-2015建筑地基基础工程施工规范.json` | `GB51004-2015` | 0.998679 |
| `18、GB+50207-2012屋面工程质量验收规范（清晰版）.json` | `GB50207-2012` | 0.962567 |
| `1、GB50352-2019民用建筑设计统一标准.json` | `GB50352-2019` | 0.954802 |
| `22、GBT51366-2019建筑碳排放计算标准.json` | `GB/T51366-2019` | 0.967742 |
| `19、GB50210-2018建筑装饰装修工程质量验收标准.json` | `GB50210-2018` | 0.100817 |

**Audit judgment:** the source file name must not be treated as the standard authority. The compiler must use node-level `source_context.standard_code`, `article_id`, and normalized standard code.

### 3. Lecture Bundle and Page JSON Look Like Duplicate Projections

Lecture directories contain a bundle JSON plus per-page JSON files. In the local subset, bundle records and page records overlap heavily.

**Audit judgment:** use bundle JSON as the canonical lecture import surface unless a page file contains a page-level visual/citation field not present in the bundle. Do not import both blindly.

## Supabase Current State

Relevant public tables:

| Table | Rows |
| --- | ---: |
| `kb_chunks` | 15,432 |
| `questions_bank` | 4,638 |
| `standard_articles` | 3,319 |
| `standard_chunks` | 3,319 |
| `knowledge_graph_edges` | 1,351 |
| `syllabus_tree` | 1,284 |
| `active_questions` | 961 |
| `knowledge_question_links` | 709 |
| `standard_refs` | 641 distinct refs |
| `standard_tables` | 211 |
| `question_intelligence` | 43 |
| `question_summaries` | 0 |

Installed search extensions:

| Extension | Version |
| --- | --- |
| `pg_trgm` | 1.6 |
| `vector` | 0.8.0 |

Search functions include `search_unified`, `search_kb_chunks`, `search_questions`, and question-bank text/vector search functions.

## Supabase Field Coverage

### `kb_chunks`

| Metric | Count / 15,432 |
| --- | ---: |
| `content_hash` present | 15,432 |
| metadata present | 15,413 |
| `source_doc` present | 15,430 |
| `standard_code` present | 13,949 |
| `node_code` present | 7,856 |
| `page_num` present | 5,103 |
| `taxonomy_path` present | 2,105 |

`kb_chunks` is already a strong RAG table. It should remain the online retrieval backbone.

### `questions_bank`

| Metric | Count / 4,638 |
| --- | ---: |
| `content_hash` present | 4,638 |
| `node_code` present | 4,533 |
| `tags` present | 3,417 |
| `source_chunk_id` present | 1,318 |
| `grading_keywords` present | 1,225 |
| `option_reasoning` present | 80 |
| `cited_standard_codes` present | 22 |
| `grading_rubric` present | 0 |

Question type breakdown:

| Type | Total | Rubric | Keywords | Structured rules | Option reasoning | Cited codes | Source chunk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `case_study` | 1,961 | 0 | 960 | 661 | 0 | 13 | 1,016 |
| `single_choice` | 1,674 | 0 | 166 | 166 | 4 | 6 | 191 |
| `multi_choice` | 978 | 0 | 74 | 75 | 76 | 2 | 86 |

**Audit judgment:** `questions_bank` is the correct production authority, but it is missing the exact fields needed for high-quality explanation, option-by-option review, and case grading. The source corpus can backfill these fields.

### `standard_articles`

| Metric | Count / 3,319 |
| --- | ---: |
| `logic_constraints` present | 908 |
| `taxonomy_node_code` present | 0 |
| `taxonomy_node_codes` present | 0 |
| `common_violations` present | 0 |
| `synthetic_qa` present | 0 |
| `graph_relations` present | 0 |
| `key_parameters` present | 0 |

The raw source has standard-level `common_violations`, `synthetic_qa`, `graph_relations`, and `logic_constraints`; the online table currently preserves only part of that.

## Relationship Integrity

| Relationship surface | Total / refs | Valid join evidence |
| --- | ---: | ---: |
| `knowledge_question_links.chunk_id -> kb_chunks.chunk_id` | 709 | 228 |
| `knowledge_question_links.question_id -> questions_bank.id` | 709 | 584 |
| `questions_bank.source_chunk_id -> kb_chunks.chunk_id` | 1,318 | 658 |
| `knowledge_graph_edges.source_id -> kb_chunks.chunk_id` | 1,351 | 556 |
| `knowledge_graph_edges.target_id -> kb_chunks.chunk_id` | 1,351 | 456 |
| `standard_refs -> standard_articles` by code/article | 641 distinct refs | 203 |

Current graph-edge distribution:

| Source type | Target type | Relation | Count |
| --- | --- | --- | ---: |
| `knowledge_cards` | `knowledge_cards` | `part_of` | 538 |
| `syllabus_node` | `syllabus_node` | `prerequisite` | 452 |
| `knowledge_cards` | `knowledge_cards` | `contains` | 361 |

There is no `knowledge_cards` table in the current DB inspection. The graph table therefore contains legacy type names that do not line up cleanly with the current `kb_chunks` authority.

**Audit judgment:** the database has some graph-shaped data, but not yet a reliable knowledge graph. The graph edges are a useful projection candidate, not a product authority.

## Source-to-DB Coverage Sample

Local readable source IDs compared with the current DB:

| Source class | Local unique IDs | `kb_chunks.chunk_id` matches | Other relevant match |
| --- | ---: | ---: | ---: |
| book | 1,210 | 569 | - |
| standard | 2,283 | 694 | 768 `standard_articles.original_id`, 768 `standard_chunks.id` |
| lecture bundle | 365 | 364 | - |
| lecture page | 367 | 363 | - |
| question chunks | 1,339 | 233 | 227 `questions_bank.source_chunk_id` |

Interpretation:

- Lecture bundles are mostly landed.
- Book and standards are partially landed.
- Question source chunks are not comprehensively linked to `questions_bank.source_chunk_id`.
- Online `questions_bank` has many rows, but provenance back to source chunks is incomplete.

## Highest-Severity Findings

### P0. Source Availability Is Not Guaranteed

109 JSON files are dataless. The unavailable set includes taxonomy, standards, exam years, and v3 textbook artifacts.

**Consequence:** any compiler run without an availability gate will silently miss core material.

**Required action:** create `source_inventory.jsonl` with `path`, `bytes`, `macos_flags`, `readable`, `sha256`, `source_class`, and `blocking_reason`.

### P0. Standard Authority Is Drifting

Source standard files are mixed collections, and the online standard table has code drift:

- 1,950 of 3,020 parsed `standard_articles.original_id` rows have normalized code mismatch against `standard_articles.standard_code`.
- `standard_refs` joins only 203 of 641 distinct refs to `standard_articles`.
- `standard_articles.taxonomy_node_code(s)` are empty.

**Consequence:** case grading and citation-heavy explanations can cite the wrong standard family if they trust file names or table-level `standard_code`.

**Required action:** standard compiler must normalize at node/article level and produce a reviewed `standard_clause_key = normalized_standard_code + article_code + source_origin_id`.

### P0. Case Rubric Authority Is Missing Online

`questions_bank.grading_rubric` is empty for all 4,638 rows. Case-study rows have useful fallback signals (`grading_keywords` and `structured_rules`), but no curated rubric.

**Consequence:** subjective grading cannot claim curated rubric authority from the DB today.

**Required action:** build a case-rubric compiler from `questions_bank` + source exam JSON + standard clauses, outputting reviewable rubric projections before any writeback.

### P1. Option Reasoning Was Lost During Import

Local source exercises contain at least 188 `option_reasoning` entries in the readable subset. Online `questions_bank.option_reasoning` has only 80 populated rows.

**Consequence:** answer review quality is capped; wrong-option explanations are underused.

**Required action:** backfill `option_reasoning` and preserve it as structured JSON, not only as appended prose in `analysis`.

### P1. Current Graph Tables Are Not Yet Authority

`knowledge_graph_edges` uses `knowledge_cards` type names, but no `knowledge_cards` table is present. Joins to `kb_chunks` are partial.

**Consequence:** graph expansion can be useful for retrieval hints, but it should not drive final explanations or grading.

**Required action:** rebuild graph edges from compiled source assets with current source types: `kb_chunk`, `question`, `standard_article`, `syllabus_node`, `misconception`, `rubric_point`.

## Recommended Architecture

Use a source compiler, not a graph-first rebuild.

```text
docs/2026 source files
  -> SourceAvailabilityGate
  -> SourceManifest / stable_id / content_hash
  -> deterministic compilers
      -> concept_pages.jsonl
      -> standard_clauses.jsonl
      -> question_capsules.jsonl
      -> rubric_candidates.jsonl
      -> misconception_patterns.jsonl
      -> lecture_teaching_cards.jsonl
  -> dry-run coverage report
  -> controlled Supabase backfill
  -> lightweight graph projection
```

## Compiler Priorities

### 1. Source Manifest Compiler

Purpose: make `docs/2026` auditable and repeatable.

Output:

- `source_inventory.jsonl`
- `source_manifest.jsonl`
- unavailable file report
- duplicate projection report

Hard gate:

- fail if taxonomy is dataless
- fail if a selected source class has unavailable files
- fail if a source file has no stable hash

### 2. Standard Clause Compiler

Purpose: fix citation and standard-code authority.

Inputs:

- `标准文件/*.json`
- node-level `source_context`
- `logic_constraints`
- `common_violations`
- `synthetic_qa`
- `graph_relations`

Outputs:

- `standard_clauses.jsonl`
- `standard_code_normalization_report.md`
- `standard_ref_backfill_candidates.jsonl`

Rules:

- never trust the file name as standard code
- prefer node-level `source_context.standard_code`
- normalize article identity before joining
- keep raw source provenance

### 3. Question Capsule Compiler

Purpose: make every question explainable.

Inputs:

- real exam JSON
- ZL500
- Qiantizan
- current `questions_bank`

Outputs:

- `question_capsules.jsonl`
- `option_reasoning_backfill.jsonl`
- `question_source_link_backfill.jsonl`
- `question_standard_ref_candidates.jsonl`

Compiler output should preserve:

- stem
- options
- correct answer
- option reasoning
- pitfalls
- node code
- source year/session
- source chunk
- candidate standard references

### 4. Case Rubric Compiler

Purpose: turn case-study rows into reviewable grading assets.

Inputs:

- `questions_bank.case_study`
- local source exam JSON
- `grading_keywords`
- `structured_rules`
- standard clauses

Outputs:

- `rubric_candidates.jsonl`
- `rubric_review_queue.jsonl`
- `case_grading_golden_set.jsonl`

Important boundary:

- rubric projection is not a second question bank
- `questions_bank.id` remains the question authority
- writeback should happen only after review or high-confidence deterministic validation

### 5. Lecture Teaching Card Compiler

Purpose: use lecture assets for TutorBot teaching style without polluting RAG with duplicate chunks.

Inputs:

- lecture bundle JSON as primary source
- page JSON only as visual/citation supplement

Outputs:

- `lecture_teaching_cards.jsonl`
- `lecture_assessment_candidates.jsonl`
- `teaching_phrase_bank.jsonl`

## Do Not Do

- Do not import both lecture bundle and page JSON blindly.
- Do not trust standard file names as standard authority.
- Do not build a standalone Neo4j/AGE graph before field parity is fixed.
- Do not re-embed all source JSON as flat chunks and call that knowledge utilization.
- Do not create a parallel runtime question bank outside `questions_bank`.
- Do not make graph edges the authority for grading or citation.

## Decision

Current Supabase is good enough as the online knowledge backbone, but it does **not** yet have reliable knowledge-graph authority. It has strong RAG storage and question assets, but weak relationship integrity and incomplete structured fields.

The correct next engineering move is:

1. make `docs/2026` source availability deterministic;
2. build compiler outputs as reviewable JSONL;
3. dry-run compare against Supabase;
4. backfill missing structured fields;
5. then rebuild graph projections from the compiled assets.

This keeps the system simpler than a graph-first rebuild and uses the raw data more fully.
