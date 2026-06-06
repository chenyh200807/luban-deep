# Luban Textbook Verbatim Lane — Increment ① of the Living LLM Artifact Compiler

**Design date:** 2026-06-06
**Status:** design + empirical coverage probe; first full-650-block run ready to implement. publish / production / canonical-write OUT OF SCOPE (separate authorization).
**Parent design:** [2026-06-06-luban-living-llm-artifact-compiler-design.md](2026-06-06-luban-living-llm-artifact-compiler-design.md). This is increment ① — no new authority surface; it wires the existing S0–S7 spine to the 2026 textbook.

---

## 1. The empirical coverage thesis — what "全量知识编译" actually means

Probe run over the 3 real 2026 textbook files (`FINAL_CLEANED_BOOK2026-{9-166,167-221,222-382}_fixed.json`): **650 content_blocks, 1309 knowledge_cards** (avg 2.0 cards/block). Every block is pre-enriched with `content_markdown` (the verbatim source), `knowledge_cards` (card_title / card_type / card_content / key_numbers / logic_chain / mnemonics), `assessment` (logic_rule), `taxonomy` (node_code / taxonomy_path).

The hard verbatim constraint partitions the 1309 cards (empirical 7-bucket classification):

| Bucket | Cards | % | Destiny |
|---|---:|---:|---|
| A. verbatim clause + all key_numbers in content_markdown | 112 | 8.6% | **SIGN** `textbook_authority` |
| B. all key_numbers verbatim in content_markdown (no title hit) | 574 | 43.9% | **SIGN** `machine_spec` |
| D. verbatim clause, no key_numbers (definition/concept) | 61 | 4.7% | **SIGN** `textbook_concept` |
| C. GB/JGJ code cited, numbers NOT in content_markdown | 2 | 0.2% | `external_source` **work_order** (never textbook) |
| E+F. partial numeric / verbatim-but-no-number | 217 | 16.6% | **human-gate** work_order (~75% expected to pass) |
| G. pure synthesis (no verbatim, no number, no GB cite) | 343 | 26.2% | **do-not-sign** work_order (legit paraphrase, not hallucination) |

**Bottom line:** the full 650-block compile auto-signs **~747 cards (57%)** first-pass (13% textbook_authority + 44% machine_spec), with ~217 human-gate + 2 external + 343 do-not-sign as a **named, append-only backlog**. With human review (~75% pass) total signable reaches **~750–910 cards (57–70%)**.

> "全量" = **signed verbatim subset (~750–910) + named work-order backlog (~560), reported honestly per run.** The signed subset is cryptographically verbatim against `content_markdown`; nothing is silently dropped; nothing is over-claimed. This is the anti-overclaim contract.

**When:** architecturally now — the pipeline exists and is GO. The full pass is ~650 DeepSeek calls (~$0.25–0.35) + the deterministic signer. It is a scale + orchestration task, not new architecture.

---

## 2. The 5 must-fix provenance holes (top-tier vs laundering disaster)

These are the load-bearing corrections from the adversarial premortem. Each is a deterministic guard the signer/gate MUST enforce; without them the lane launders enrichment/external content into textbook authority.

1. **G2 anchor identity (THE root hole).** The signer MUST recompute `quote in content_markdown` itself (corpus check), and IGNORE any LLM-asserted `verified` / `match_method` field. The case-lane `scripts/luban_case_rubric_schema.verify_textbook_anchor` trusts the asserted fields and never reads the corpus — using it here would sign every GB quote as textbook authority. The textbook lane's truth is `_norm(quote) in _norm(content_markdown)`.
2. **Per-number provenance for machine_spec.** `key_numbers` only sign if each (unit-normalized) number is a substring of the block's OWN `content_markdown` — NOT `card_content`'s GB citation. Numbers present only in a GB citation (27m/100m from GB 50352) are stripped from the signed record and routed to an external work_order. G4 well-formedness (off-by-one) is NOT a provenance check.
3. **Per-field, not per-card.** A card mixes a verbatim clause + a GB citation + a synthesized mnemonic. Sign ONLY the fields whose exact source is confirmed in `content_markdown`. `card_title`, `mnemonics`, `logic_chain`, `assessment.generated_question`, `grading_keywords` are LLM/enrichment-authored and NEVER enter the signed authority surface (`assessment_keyword_as_required_term = 0`).
4. **Same-block corpus only (no cross-block contamination).** The corpus is the card's own block, keyed by `chunk_id`; the signer derives `content_markdown` internally and forbids any caller/anchor-supplied corpus. `content_hash = sha256(that block's content_markdown)`; the resolver pins `chunk_id → content_hash` so a post-hoc swap fails closed.
5. **Narrow, symmetric normalization.** `_norm` collapses whitespace + normalizes full/half-width digits & units but does NOT strip interior content chars (no char-subset matching). Plus a minimum anchored-span length and a high-frequency-phrase blocklist (reject a quote appearing in > K distinct blocks — boilerplate like "应符合规范"). The same `_norm` runs at sign, S5 re-verify, and resolver. Width test: `２７ｍ` quote vs `27m` corpus must pass (no dishonest under-signing).

---

## 3. Architecture (reuse the spine; add a textbook signer + worker + resolver entry)

**The LLM only PROPOSES; the deterministic signer re-checks every field against the corpus and builds the signed record from ONLY confirmed fields.** This makes the LLM genuinely advisory and the gate the sole authority.

- **S0 ingest:** `feedback_ingest_bridge.ingest_sources(textbook_blocks=[...])` → `textbook_block` EvidenceItem (governed_textbook), payload = the whole block (chunk_id, content_markdown, knowledge_cards, taxonomy, assessment).
- **S2 worker** (`textbook_knowledge_worker.py`, injected): per card → ONE candidate through `make_candidate`. DeepSeek proposes `{exact_quote_or_null, type, external_code_or_null}` per card (classification + verbatim-span proposal, never authority); `--no-llm` deterministic fallback does the substring search itself. External-code cards → `KIND_WORK_ORDER` (origin `external_standard`), never a textbook point.
- **Signer** (`full_knowledge_compiler.compile_textbook_knowledge_release_candidate`, NEW, namespace `textbook_knowledge_full`): `_validate_textbook_provenance(card, content_markdown)` runs the per-field corpus check (must-fixes 1–5); signs ONLY confirmed fields; emits `node_index` in the manifest; `verify_lane_bundle` unchanged.
- **S5** (`compiler_pipeline._s5_sign_textbook`, NEW sibling of `_s5_sign`): the ONE `promote_to_release` flip site; builds `node_index`.
- **S6 resolver** (`compiled_registry_resolver.resolve_node` / `build_pack_for_node`, NEW): four-gate `verify_bundle` (unchanged) + `node_index` lookup → `resolution` → `build_pack_from_question_context`. Authority is the server `grant_release` kwarg only (F1), never the bundle.
- **Runtime:** signed points populate `rubric_context` (rubric authority) + `source_context` (verbatim provenance refs, `is_answer_key=False`). External work_orders never appear in `compiled_source_refs`.

## 4. GO gates / safety invariants

`verbatim_rate = 1.0` over the signed set (every signed quote re-checked in its block's content_markdown); `external_laundering = 0`; `key_number_not_in_text_signed = 0`; `assessment_keyword_as_required_term = 0`; `source_laundering = 0`; `candidate_used_as_release_truth = 0`; `published = false`; `canonical_truth_written = false`; `production_write_count = 0`; `tamper_fail_closed = true`; `node_code_indexed = true`; `handoff_authority_is_server_only = true`; `coverage_reported_honestly = true` (backlog named + append-only). verdict GO iff all hold and blocks_processed == 650; WEAK-GO if live LLM absent (hermetic floor).

## 5. Deliverables

- ADD: `deeptutor/services/construction_grading/textbook_knowledge_worker.py`; `scripts/run_luban_textbook_knowledge_compile.py`; tracked supply `runtime_supply/v_textbook_knowledge_full/`; tests.
- MODIFY (surgical): `full_knowledge_compiler.py` (+ provenance classifier + signer + namespace); `compiler_pipeline.py` (+ `_s5_sign_textbook` + lane selector); `compiled_registry_resolver.py` (+ `resolve_node`/`build_pack_for_node`).
- Artifact ledger: `artifacts/luban_grading_artifacts/textbook_knowledge_full_20260606/` (evidence_inventory, candidate_ledger, signed bundle, coverage_report, safety_report, work_order_backlog, handoff_proof, go_no_go, FINDING).

OUT OF SCOPE (separate authorization): publish, production default, canonical learner-truth write, remote/DB write, the human-gate review pass, the `verified_paraphrase` bucket.
