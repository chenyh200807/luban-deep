# 2026 Source Compiler Dry Run QA

**Date:** 2026-05-24
**Mode:** local source read + ignored artifact generation + read-only gate checks.
**Apply status:** disabled. Task 9 keeps `--apply` refusing until Task 13.

## Source Availability Summary

PR-1 inventory command:

```bash
LUBAN_2026_SOURCE_ROOT=/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026 \
python scripts/run_2026_source_inventory.py --run-id 20260524T120000Z --require-platform darwin
```

Observed counts:

| Metric | Count |
| --- | ---: |
| JSON files | 375 |
| Readable JSON | 266 |
| Dataless JSON | 109 |
| Blocked dataless | 109 |
| Lecture pages skipped as redundant | 232 |

Taxonomy is still dataless in this local source root, so Task 13 is blocked until the source owner downloads or signs exclusion for P0 taxonomy files.

## Supabase Coverage Summary

PR-1 read-only coverage dry-run matched the audit baseline for the main authority tables:

| Metric | Count |
| --- | ---: |
| `questions_bank.rows` | 4638 |
| `questions_bank.grading_rubric_present` | 0 |
| `questions_bank.option_reasoning_present` | 80 |
| `questions_bank.cited_standard_codes_present` | 22 |
| `standard_articles.rows` | 3319 |
| `standard_articles.taxonomy_node_code_present` | 0 |
| `questions_bank.source_chunk_id_valid_join` | 658 |

## Artifact Diff Summary

PR-2 dry-run artifacts:

| Run | Artifact | Count |
| --- | --- | ---: |
| `20260524T130000Z` | `standard_clauses.jsonl` | 3682 |
| `20260524T131000Z` | `question_capsules.jsonl` | 70 |
| `20260524T131000Z` | `question_capsule_unmatched.jsonl` | 70 |
| `20260524T132000Z` | `lecture_teaching_cards.jsonl` | 112 |

Diff tool proof:

```text
standard_clauses: added=0 removed=3682 unchanged=0 content_hash_changed=0
question_capsules: added=70 removed=0 unchanged=0 content_hash_changed=0
lecture_teaching_cards: added=0 removed=0 unchanged=0 content_hash_changed=0
```

## Top Unmatched Question Candidates

The current PR-2 compiler emits `question_capsule_unmatched.jsonl` when no `questions_bank` export is supplied. The first smoke run had 70 unmatched source questions. Task 13 must not write rubric or option reasoning for unmatched rows.

## Existing Option Reasoning Policy

`questions_bank.option_reasoning` has 80 non-empty rows in the current production authority. PR-2 compiler defaults to `overwrite_only_if_empty`; non-empty rows are preserved unless a reviewed artifact explicitly opts into `merge_keys`.

## Graph Projection Counts

PR-3 smoke run `20260524T133000Z` emitted all six projection families:

```text
graph_edges=6
kb_chunk->standard_article:cites
lecture_card->syllabus_node:teaches
question->kb_chunk:sourced_from
question->standard_article:cites
question->syllabus_node:tests
standard_article->syllabus_node:covers
```

Graph remains projection only. It is not teaching, grading, citation, or RAG authority.

## Release Gate Status

| Gate | Status | Evidence |
| --- | --- | --- |
| Artifact safety | Pass | `git ls-files artifacts/` returns empty |
| Source availability | Blocked for Task 13 | taxonomy and other P0 sources remain dataless |
| Compiler determinism | Pass for same-run diff | same run reports zero content hash changes |
| Single writer authority | Pending Task 13 | legacy importers must be deprecated before apply |
| Target database | Pass for read-only coverage | `questions_bank=4638` main guard |
| Writeback safety | Pass for PR-1/2/3 | `--apply` refuses; dry-run plan only |
| Docs | Pass | INDEX points to v0.2 plan and this QA report |

## Task 13 Start Condition

Task 13 can start only after source-owner sign-off on dataless P0 files, legacy importer deprecation, and shadow-table schema approval. First writes must target shadow tables, not live `questions_bank`, `kb_chunks`, `standard_articles`, or `syllabus_tree`.
