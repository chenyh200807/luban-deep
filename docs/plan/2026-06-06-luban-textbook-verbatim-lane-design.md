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

## 6. Closure (2026-06-06, GO) — best-model build-phase compile

**Model-tier correction (the key principle):** knowledge compilation is a BUILD-PHASE, one-time, high-stakes task — "compile once with the best model, sign it, reuse forever; the cheap production model (DeepSeek/Qwen) is for runtime adjudication at scale, not for compilation." The first live pass mistakenly used DeepSeek (the production-cost model) to PROPOSE spans. Corrected: the build-phase compile uses the **top expert council — Opus 4.8 (primary, 47 parallel agents) + Codex GPT5.5 (second model / rescue + adversarial audit)**. Span proposal is decoupled from signing: the top model proposes spans offline; the deterministic signer re-verifies EVERY span against the corpus, so the proposer can never bypass provenance.

Every mode verifies `verify_lane_bundle` + an INDEPENDENT verbatim audit (every signed point re-checked against its block's content_markdown): `quote_not_in_corpus=0`, `key_number_not_in_corpus=0`, `verbatim_rate_ok=true`, all 14 hard gates GO.

| Span proposer | Signed | % of 1309 | backlog | note |
|---|---:|---:|---:|---|
| Deterministic ($0, 0.45s) | 984 | 75.2% | 325 | clause-level substring only |
| DeepSeek live (production-cost; mis-applied to build phase) | 1226 | 93.7% | 83 | concept span median 9→54 chars |
| Opus 4.8 build-phase (47 agents) | 1293 | 98.8% | 16 | full claim-bearing sentences |
| **Opus 4.8 + Codex GPT5.5 council** | **1303** | **99.5%** | **6** | Codex rescued 10/16 Opus misses |

**Council cross-validation (the top-tier safety signal):** Codex GPT5.5 independently audited a 12-span sample of the Opus extraction — **verbatim 12/12, good_span 12/12** (two top models agree 100%). Codex also rescued **10 of the 16** cards Opus + deterministic both missed (all 10 re-verified verbatim). Final: **1303/1309 (99.5%) signed with cryptographic verbatim provenance, 6 genuine pure-synthesis cards in the named backlog, zero laundering with two LLMs in the loop.** The tracked supply `runtime_supply/v_textbook_knowledge_full/` carries the 1303-point council bundle.

**Mechanism:** `textbook_knowledge_worker` gained `precomputed_spans` (top-model spans injected, re-verified) + `make_precomputed_worker`; the runner gained `--spans`. Proposal priority: top-model precomputed → deterministic clause → cheap-LLM enrichment (production path). The deterministic signer is unchanged — it is the sole provenance authority regardless of proposer.

Runtime consumption (③) is wired: `textbook_knowledge_runtime.resolve_textbook_knowledge(node_code)` loads the signed pack through the resolver's four gates and a turn with a node_code gets verbatim teaching/source context via the gated `deep_question._maybe_attach_textbook_knowledge` hook (flag `grading_engine_textbook_knowledge` + env kill + cohort, default OFF). Authority is the server `grant_release` kwarg only (F1).

## 7. OCR-fidelity audit against the original PDF (2026-06-06)

The signer guarantees `signed == content_markdown` verbatim — but `content_markdown` is itself an OCR derivative of the original `2026一建《建筑》电子版教材.pdf`. If the OCR were wrong, we would faithfully sign the error. Audited it.

**Finding on the PDF:** the PDF's embedded text layer is uniformly GARBLED (broken font encoding / fake OCR layer — glyphs render correctly to the eye but the character codes map to wrong unicode, e.g. page 0 extracts as "己口己与年 建前梅 管里与建务" for "2026年 建筑 管理与实务"). So the PDF text layer is NOT usable as ground truth by text extraction; `content_markdown` (a clean VISION-OCR product) is strictly better. The 2nd PDF (`教材对比明细.pdf`, 30 pp) has clean text but is an edition-change changelog, not the full corpus.

**Vision audit (the only valid method):** rendered 12 pages spanning the book to images and had 12 Opus vision agents read each page and verify every signed numeric span (key_numbers + quote) against what the page actually shows. Result over 22 high-risk numeric spans: **20/22 numbers exact, 21/22 quotes match, ZERO OCR digit errors.** Verified-exact against the real page: 27m/100m, 500MPa/C30/C40, 200mm/70%/15mm, 70.7mm/28d/20℃/90%, 1:1.5/1:1.75, 20mm/1.5m/10mm, 5℃/30℃/0℃, 20000m²/15000m²/10000m²/2500m²/1000m², 2m²/4m²/0.1m³/80%, 4m/6m/12m/15m, 2层/2.5m/0.9m/16人, 100mm, design-life 50年/100年 tables, and more.

The 2 flags are NOT OCR errors: (1) one was an audit page-mapping artifact (the span's number is on the NEXT printed page; the coarse page_num→PDF-page mapping rendered the prior page); (2) one calc card (`1A435000_091_0149::C0`, 连环替代法) has 3 key_numbers (14560/10816/5616) that are enrichment-COMPUTED differences correctly derived from the printed worked-example values (378560/389376/383760) but not literally printed — an enrichment-derived-value nuance, not OCR or laundering; its quote and the 7 printed numbers are verbatim.

**Conclusion (OCR):** `content_markdown`'s vision-OCR is high-fidelity; the garbled PDF text layer does not affect us; no corpus re-OCR is warranted for the signed pack. Audit ledger: `artifacts/luban_grading_artifacts/textbook_knowledge_full_20260606/vision_ocr_drift_audit.json`.

**`printed_vs_derived` flag (implemented).** The calc-card nuance is now handled deterministically in the signer (`_split_printed_derived`): a key_number is `derived` iff it appears in `content_markdown` as the result of an arithmetic equation (`<digit> = N`, allowing an optional sign — e.g. `364000 = 14560`, `= -5616`); a printed table/rule value never appears as the RHS of a computation. Derived numbers are split into `derived_key_numbers` and kept OUT of the authoritative `key_numbers` and `required_terms`, so an enrichment-computed answer is never treated as a textbook fact. Across the full pack this separated **16 derived numbers across 7 calc/case cards** (e.g. `1A435000_091_0149::C0` 连环替代法 → derived `14560/10816/5616`, printed `500/520/700/720/4%/2.5%/19760`); manifest carries `records_with_derived_numbers` / `derived_numbers_total`. signed stays 1303, `verify_lane_bundle` holds.

## 8. verified_paraphrase review channel — and the governed council outcome on the 6-card backlog (2026-06-06)

The verbatim signer only signs literal substrings, so the 6 residual `synthesis` cards (faithful-looking restatements/summaries with no verbatim anchor) need a separate path. Built one — a strictly weaker class, never verbatim authority:

- **Open** (`textbook_paraphrase_review.build_review_queue` + `make_paraphrase_candidates`): each synthesis backlog item → a self-contained review packet (claim + the block's own `content_markdown` + deterministic triage signals + a fixed faithfulness question), staged in the `compiler_feedback` candidate ledger (origin `council_vote` → `source_candidate`, `promote_to_release=False`, separate from every release namespace).
- **Sign** (`sign_verified_paraphrase_release_candidate`): a deterministic signer with a HARD review gate. A packet signs into the SEPARATE namespace `textbook_paraphrase_review` ONLY when a governed reviewer (`human_reviewer` / `governed_council`) returned `faithful` AND every claim key_number is grounded in the source (numbers never laundered, even in a paraphrase). Class `verified_paraphrase`: teaching context only, `official_answer_capable=False`, ZERO verbatim-authority records by construction. Everything else routes back to the backlog.
- **Authority seam** (mirrors F1): faithfulness is a SEMANTIC judgment — NOT decided by the signer. It comes from a governed council as a verdicts file; the runner (`run_luban_textbook_paraphrase_council_review.py`) joins verdicts onto packets and signs deterministically. The signer never decides faithfulness; the runner never signs by itself.

**Governed council run (Opus 4.8 + Codex GPT5.5, both independent, user-authorized).** Each model read all 6 cards' claim against the block's full `content_markdown` and judged faithful only if the claim is FULLY entailed by that block (no added fact/method/framework, no number absent from the block). Result: **6/6 unanimous, 0 faithful → 0 signed** — channel discipline holding, not a failure. Per-card (both models agreed on every one):

| point_id | node | why rejected (both models) |
|---|---|---|
| `1A432001_027_0033::C0` | 1A432001 | block is the bid-scheme-planning table; no 资质/联合体 content — wrong-block attribution |
| `1A432001_027_0033::C1` | 1A432001 | same table block; no 禁止情形 clause |
| `1A435000_089_0147::C0` | 1A435000 | block lists 5 cost items flat; claim ADDS a 直接/间接成本 classification the block never states |
| `1A411011_024_0045::C2` | 1A411011 | block only says "见表1.3-1"; 5/50/100 not inlined — numbers not grounded |
| `1A413000_085_0158::C2` | 1A413000 | block only says "见表3.2-1"; compaction values not inlined — numbers not grounded |
| `1A413030_092_0173::C0` | 1A413030 | block has 静载/钻芯/低应变 only; claim ADDS 高应变法/声波透射法 absent from the block |

**Root cause (the real finding):** these 6 are CORRECT knowledge but MIS-ATTACHED — the claim summarizes content from a referenced-but-not-inlined table or a wider section, attributed to a single block that doesn't contain it. Signing them as paraphrase-of-this-block would be false provenance, so both models (rightly) refused. **Unlock path (upstream data fix, not a channel change):** re-attach each card to the block that actually contains its content, or inline the referenced table (表1.3-1 / 表3.2-1) into the block, then re-run the council runner — it will sign the now-grounded cards automatically.

**Runtime wiring: deferred, by design.** With 0 signed records there is nothing to surface, so a `textbook_paraphrase_runtime` consumer + `deep_question` hook would be dead code (AGENTS §2.5 Less Is More). The consumer mirrors `textbook_knowledge_runtime` exactly and is a ~30-line follow-up the moment the backlog produces signed paraphrases. Official scoring stays verbatim-only regardless; `verified_paraphrase` is teaching context only.
