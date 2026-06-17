# Luban Living LLM Artifact Compiler — Final Design

**Design date:** 2026-06-06
**Schema lineage:** `luban_full_knowledge_compiler.m30`, `luban_context_pack.v1`, `luban_compiler_candidate`, `luban_runtime_supply_bundle.v1`
**Authors:** Chief-architect synthesis of two senior-engineer proposals (pipeline-first + authority-first).
**Status:** design — first vertical slice ready to implement; release/publish/canonical-write OUT OF SCOPE (separate authorization).

---

## 1. North star + 精妙 (what makes it elegant)

**North star.** *"LLM organizes the data; deterministic gates sign the artifact; runtime LLM adjudicates the answer."* Knowledge compilation must **EXPAND** the agent's capability — better understanding, better evidence organization, transfer to variant questions, continuous absorption of new knowledge — and must never narrow into a registry-lookup gate. **Compile once, adjudicate with a scoped packet many times.** A question that misses the bank is never refused: it fails *open* to open-world teaching and becomes new evidence for the next compile cycle (越用越强 — stronger with every use).

**精妙 — the one idea that makes this elegant, not just functional.** The design separates **two different rights held by two different actors across one deterministic gate: the right to WRITE a candidate, and the right to SIGN it as release truth.** The LLM holds only the writer right; it never holds the pen on authority. Around that single invariant, the whole system is just *wiring existing, already-guarded assets into a deterministic orchestration spine* — not inventing new authority surfaces.

Three concrete elegances fall out of that one idea:

1. **The candidate bus is already laundering-proof.** `compiler_feedback.make_candidate` deflects any `answer_key_candidate` from a non-governed origin (`rag_chunk`/`model_vote`/`council_vote`/`llm_guess`/`retrieval`) into a hashed-but-never-stored `KIND_REJECTED` audit row *at birth* (verified: `compiler_feedback.py:73-89`). We route through it instead of writing raw dicts — and the hardest invariant in the system is enforced for free.
2. **`promote_to_release` has exactly one flip site.** It is `False` at birth and through every LLM/validator/council stage; it becomes `True` only inside the deterministic sign gate, only after the full gate ladder passes. There is no edge by which an LLM output skips a gate.
3. **The loop closes itself.** Today's two breaks — the LLM organizer is a token-sample sidecar whose ledger nobody reads, and M20 deltas stage perfectly but have no executor — are the *same* missing wire: feedback never re-enters as candidates. One ingest bridge + one resolver bridge closes both. The factory gets a larger, better-anchored signed registry every cycle while never refusing service in the meantime.

This fuses the two proposals: the **pipeline-first** S0→S7 orchestration spine is the skeleton; the **authority-first** "writer ≠ signer / four authority layers / promotion-gate ladder" formalism is the load-bearing law each stage enforces.

---

## 2. End-to-end pipeline (every stage named)

The compiler is a **deterministic orchestrator** (`LubanCompilerPipeline`). Every stage is a pure function `Stage(bus, ctx) -> bus'` — **append-only, no in-place mutation** (project immutability rule). The LLM lives *inside* exactly two stages (S2 generation, S4 adversarial input) and never holds the pen on signing.

```
                ┌─────────────────────────────────────────────────────────────────────┐
                │   LubanCompilerPipeline   (deterministic orchestrator, append-only)   │
                └─────────────────────────────────────────────────────────────────────┘

 S0 INGEST ─► S1 NORMALIZE ─► S2 LLM FAN-OUT ─► S3 DET. GATES ─► S4 COUNCIL ─► S5 SIGN ─► S6 PACK ─► S7 FEEDBACK
 (6 typed     (EvidenceItem,   (small models:    (G0–G8 gate      (4-model,    (full_      (resolver  (work_orders +
  evidence     canonical text,  candidates via    ladder, fail-    down-rank    knowledge_  → Luban    rejects + runtime
  sources)     dedup, origin    make_candidate)   closed)          ONLY)        compiler.*  Context    misses + council
               stamped IMMUT.)                                                  sign)       Pack)      disputes → S0)
        ▲                                                                                                     │
        │                                                                                                     │
        └──────────────────────────────────── loop-until-dry (content-addressed dedup, MAX_ITER) ◄───────────┘

 AUTHORITY LAW per stage (writer ≠ signer):
   S2/S4 = WRITE only (LLM proposes; promote_to_release stays False)
   S3/S5 = SIGN gate  (deterministic; the ONLY place promote_to_release flips True)
   S6    = CARRY only  (build_luban_context_pack carries signed truth; mints none)
```

### Stage table

| Stage | Name | Determinism | Job | Reuses (verified assets) |
|---|---|---|---|---|
| **S0** | Ingest | deterministic | Pull raw evidence from 6 typed sources (§7). Each → immutable `EvidenceItem` with `evidence_kind` + `origin` + `source_kind`. No interpretation. | `fetch_full_objective_rows` (READ-ONLY); `kbv5._retrieve_chunks`; M20 `candidate_delta_registry_m20.jsonl` reader; `work_order_from_open_world` |
| **S1** | Normalize | deterministic | Canonicalize text/options/answer-keys; dedup by content hash; stamp `source_kind` boundary. Reject malformed at boundary (input-validation rule). | `_normalize_db_options`, `normalize_options`, `_normalize_answer_key`, `_canonical`, `_sha16` |
| **S2** | LLM fan-out | **LLM (small)** | Route each `EvidenceItem` to the right worker; worker emits typed candidates **through `make_candidate`**. Organization, never authority. | new worker prompts; `deeptutor.services.llm.factory.complete`; M5B `_jury_prompt`/`_vote_factory` patterns |
| **S3** | Deterministic gates | deterministic | Run the G0–G8 gate ladder (§5). Pass → eligible-to-sign; fail → `work_order`/`rejected`/`conflict(queued)`. **Verbatim textbook provenance enforced here.** | `verify_textbook_anchor`, `_validate_calc_point`, `_validate_list_point`, M10 `attack_spec` (7-vector), `verify_lane_bundle` |
| **S4** | Adversarial council | **LLM (4-model), evidence-only** | Only *disputed* eligible candidates (quorum ≥3). Council may **down-rank only**; never up-rank, never seed a source. | M5B `_adjudicate`, M5D `_council_decision` (source_status is HARD gate; votes are evidence) |
| **S5** | Sign gate | deterministic | Survivors → lane compile fns → signed `release_candidate` bundle. Two-level hash; conflicts QUEUED not fixed; `published=False`. **Only flip site for `promote_to_release`.** | `compile_full_objective_release_candidate`, `compile_source_context_release_candidate`, `compile_case_rubric_release_candidate`, `build_compiled_knowledge_registry_manifest` |
| **S6** | Pack build | deterministic | Signed bundle → **resolver bridge** → `resolution` dict → `build_luban_context_pack` (server-side `governed_registry_status`). Runtime hand-off. | `build_luban_context_pack`, F1 seam, `objective_runtime_adapter._governed_index` four-gate verify, `runtime_consumption_projection` |
| **S7** | Feedback re-ingest | deterministic | Every `work_order`/`rejected`/runtime-miss/council-dispute → new `EvidenceItem` for next run. Closes the loop. | `work_order_from_open_world`, `build_ledger`, `absorb_m20_deltas` |

---

## 3. Typed candidate data contracts (schemas between stages)

The bus is a list of immutable entries. **Every stage appends; none mutate.** Two contracts flow.

### 3.1 `EvidenceItem` (S0 → S1 → S2)

```jsonc
{
  "evidence_id": "<sha16>",                 // content-addressed dedup key (loop termination)
  "evidence_kind": "textbook_block | objective_row | case_official_answer |
                    runtime_miss | review_item | retrieval_chunk | council_dispute",
  "origin": "questions_bank | teacher_review | open_world_diagnostic |
             rag_chunk | council_vote | model_vote | llm_guess",   // IMMUTABLE for life
  "source_kind": "governed_textbook | governed_questions_bank | non_governed",  // signing boundary
  "payload": { /* raw normalized text/options/answer/loc */ },
  "provenance": { "doc_id": "...", "chunk_id": "...", "loc": {...}, "content_hash": "..." },
  "discovered_in_run": "<run_id>"
}
```

### 3.2 `Candidate` (S2 → S3 → S4 → S5) — the canonical bus entry

This **is** `compiler_feedback._entry` verbatim (do not change those fields), plus three append-only pipeline-tracking fields. The base fields below are exactly what `make_candidate`/`_entry` already emit (verified `compiler_feedback.py:47-59`):

```jsonc
{
  // --- from compiler_feedback._entry (verbatim — do NOT alter) ---
  "namespace": "luban_compiler_candidate",
  "kind": "answer_key_candidate | rubric_candidate | source_candidate |
           machine_spec_candidate | question_candidate | work_order |
           rejected | release_candidate_delta",
  "origin": "<inherited from EvidenceItem, immutable>",
  "status": "candidate_unverified",
  "promote_to_release": false,              // flips True ONLY inside S5
  "is_release_truth": false,
  "reason": "<machine reason string; 'source_laundering_blocked:...' on a blocked answer key>",
  "payload": {...},
  "candidate_id": "<sha16 of {kind,origin,payload}>",
  "next_action": "route_to_llm_assisted_compiler_then_deterministic_release_gate",

  // --- pipeline-appended (new, append-only) ---
  "evidence_id": "<parent EvidenceItem>",   // lineage
  "stage_log": [                            // append-only audit
    {"stage": "S2", "worker": "deepseek_v4_flash", "verdict": "produced"},
    {"stage": "S3", "gate": "G2_verbatim_anchor", "verdict": "pass|fail", "detail": "..."},
    {"stage": "S4", "council": "...", "verdict": "down_rank|hold"}
  ],
  "textbook_anchor": { /* TextbookAnchorEvidence — WRITABLE ONLY by the S3 verbatim validator */ }
}
```

### 3.3 The promotion ladder (the only way `promote_to_release` flips)

`promote_to_release` stays `False` through S2/S3/S4. It is set `True` **only inside S5**, only after **all** hold:

1. `kind` is signable for its lane, AND
2. S3 attached a `verified` `textbook_anchor` (textbook-sourced points) **or** passed the deterministic machine-spec / list validators (machine-checkable points), AND
3. S4 did **not** down-rank, AND
4. `origin ∈ _GOVERNED_ORIGINS` for any answer-key kind.

This is the literal wiring of the dangling promotion gate (landscape Gap #6: "release_candidate sub-list still carries `promote_to_release=False`"). The flip now lives in S5, not nowhere.

### 3.4 The four authority layers each contract serves

| Layer | Artifact | Writer | Signer / promoter | Hard boundary |
|---|---|---|---|---|
| **L1 Source/Rubric/Registry** | signed `release_candidate` bundle | LLM compiler workers (S2) | Deterministic signer (S5) | answer_key only from `_GOVERNED_ORIGINS`; textbook anchor only from verbatim 2026 教材 match |
| **L2 Runtime GradingPacket** | `LubanContextPack` | `build_luban_context_pack` (S6) | deterministic `_diagnostic_policy` | carries signed truth; mints none; `retrieval_is_grading_authority=False`, `is_answer_key=False` hardcoded |
| **L3 Adjudication / review queue** | per-turn result + review packet | Runtime LLM adjudicator (downstream) | Runtime validator/gate | objective: LLM explains, never adjudicates correct/incorrect; `needs_review` stays candidate |
| **L4 Learner progress** | evidence event / claim / PCP | Learning Brain (synthesis) | canonical claim gate + real retest | shadow/preview/open-world never → mastery; `is_second_memory_authority=False` |

---

## 4. Big/small model routing

Honors §0.12.1 principle 4. **Small models do volume; the 4-model council only adjudicates hard cases and the release gate. No LLM in the signing path, ever.**

| Stage | Model tier | Role | Volume | Why this tier |
|---|---|---|---|---|
| **S2 fan-out** | **DeepSeek-V4-flash** (primary) / **Qwen3.7-plus** (fallback) | High-volume candidate generation | every `EvidenceItem` | Cheap, fast, high-throughput; output is candidate-only so quality floor is set by S3 gates, not the model |
| **S4 adversarial** | **DeepSeek-V4** (Prosecutor) · **Qwen3.7** (Semantics / near-synonym) · **GPT-5.5/Codex** (Chief Architect / spec correctness) · **Opus 4.8** (Judge / arbitration) | Adversarial refutation + release council | **only disputed eligible candidates** (S3 flags `disputed`; quorum ≥3) | Expensive (Codex ~30k tok/call, M5B-observed) — must stay gated to a minority; evidence-only, down-rank only |
| **S5 sign** | **none** | deterministic signing | all survivors | Authority must be reproducible + tamper-detectable; no probabilistic element allowed |
| **S6 pack** | **none** | deterministic assembly | — | — |
| **Runtime (downstream, not this pipeline)** | DeepSeek-V4-flash / Qwen3.7-plus | per-turn adjudication | every adjudication | Separate concern; consumes the S6 pack; dual-failure → fail-closed |

**S2 deterministic dispatch on `evidence_kind`:**

- `objective_row` → **no LLM**; deterministic answer-key candidate straight to S3 (objective grading is 100% deterministic).
- `textbook_block` / `case_official_answer` → DeepSeek worker: extract scoring points, split official answer, classify policy_type, propose verbatim query terms + candidate quote (the LLM proposes *where to look*; S3 verifies verbatim).
- `runtime_miss` → DeepSeek worker: propose canonical question + `external_work_order` (needs governed source).
- `retrieval_chunk` → DeepSeek worker: `source_candidate` only (laundering guard blocks any answer_key attempt).
- `council_dispute` → escalate directly to S4.

Cost discipline (§cost-aware): S2 batches; S4 fires only on the S3-flagged disputed minority.

---

## 5. Deterministic gate ladder + adversarial council — the invariants each defends

Each gate is **pure Python, no LLM, fail-closed.** Cheapest/most-decisive first. Gate routing is **total**: every candidate exits as exactly one of `signed release_candidate` · `conflict (queued)` · `work_order` · `rejected (audit row)`. Nothing is silently dropped; nothing reaches runtime without a signature.

```
LLM candidate (luban_compiler_candidate)
  │
  ▼ G0  ORIGIN GATE ─────────── answer_key candidate: origin ∈ _GOVERNED_ORIGINS else → REJECTED
  │                              (enforced AT BIRTH in make_candidate:73-89; rag/model/council/llm_guess
  │                               → KIND_REJECTED, blocked_payload hashed never stored)
  ▼ G1  SCHEMA + HASH GATE ───── required fields present; canonical JSON; SHA-256 content_hash;
  │                              reject on missing question_id / answer_key / options
  ▼ G2  SOURCE-KIND GATE ─────── textbook anchor: verify_textbook_anchor MUST pass
  │                              (source_type==textbook ∧ chunk_id ∧ match_method==verbatim ∧
  │                               normalized substring ∈ 2026 教材 content_markdown ∧ verified==True).
  │                              official_answer/RAG/vote → case-rubric SEED or work_order, NEVER textbook authority
  ▼ G3  ANSWER-KEY ALIGNMENT ─── (objective) letters ⊆ options keyset; single_choice ⇒ |key|==1;
  │                              normalize_answer_key must succeed
  ▼ G4  SPEC-ATTACK GATE ─────── (calc/machine_spec) 7-vector false-positive harness:
  │                              exact_hit, partial, contradiction, near_synonym, irrelevant,
  │                              numeric_off_by_one, denominator_mismatch → fp_total==0 else → work_order
  ▼ G5  LIST-COVERAGE GATE ───── (list_rule) coverage == 1.0 (denominator complete) else → work_order
  ▼ G6  CONFLICT GATE ────────── same question_id → different options_hash → conflict (QUEUED);
  │                              same stem_hash → different answer_key → conflict (QUEUED). Never auto-resolved.
  ▼ G7  ADVERSARIAL / COUNCIL ── (build-phase only, disputed minority) 4-model council may only
  │                              DOWN-RANK (reject≥3 / rewrite≥3 / needs_po_review). source_status is the
  │                              HARD gate; a vote can NEVER up-rank weak→verified or seed a source.
  ▼ G8  SUPERSESSION + ROLLBACK ─ new version only (append-only); rollback_pointer set; prior signed
  │                              version stays loadable
  ▼ SIGN ─────────────────────── content_hash = SHA-256(sorted records);
                                 signature = SHA-256([content_hash, namespace, "release_candidate"]);
                                 status=release_candidate, published=False, production_default_connected=False
```

### Invariant → gate map

| Invariant (must hold) | Defended by |
|---|---|
| `source_laundering = 0` | G0 (`make_candidate` birth deflect) + `validator_attack()` regression fixture |
| `rag_chunk_as_answer_key = 0`, `model_vote_as_source = 0`, `council_vote_as_source = 0` | G0 (`_NON_GOVERNED_ORIGINS`) |
| `official_answer_as_source = 0` | G2 (official_answer is *case-rubric seed*, never textbook source — `seed_corroboration_only_not_authority`) |
| textbook exact-span / 采分点 + required_terms trace to 教材 | G2 (`verify_textbook_anchor`; `textbook_anchor` field writable only by S3) |
| `answer_key_override = 0` | G3 + signing (answer_key only from governed signed record) |
| spec false positives (`false_positive = 0`, `bad_certified = 0`) | G4 (7-vector `attack_spec`) |
| `list_partial_auto = 0` | G5 (coverage == 1.0) |
| conflicts not silently fixed | G6 (queued) |
| LLM/council cannot up-rank | G7 (down-rank only; source_status HARD gate) |
| `legacy_overwrite = 0`, versioned + rollbackable | G8 (append-only, rollback pointer) |
| `candidate_used_as_release_truth = 0` | promotion ladder §3.3 + `build_ledger` assertion (verified `compiler_feedback.py:130-137`) |
| tamper fail-closed | `verify_lane_bundle` recompute before S6 |

**The adversarial harness is mandatory, not optional.** `validator_attack()` (rag_chunk/model_vote/council_vote → must all land in `work_order`) and the 7-vector `attack_spec` run on every release gate as regression fixtures. They are the only evidence the boundary holds under pressure rather than by convention.

---

## 6. How signed artifacts compose into the Compiled Context Pack and reach runtime

The signed L1 artifacts compose into one `LubanContextPack` (`luban_context_pack.v1`) consumed identically by all five surfaces (TutorBot QA · objective · case · RAG citation · Learning Brain). This is the "compile once, adjudicate many" payoff. **The only genuinely new code here is the resolver bridge** — the single missing seam between a signed bundle and `build_luban_context_pack`.

```
SIGNED L1 ARTIFACTS                              READ-ONLY LEARNER STATE
  objective answer_key bundle (v3/M31)             PersonalizationContextPack
  source_context refs (KB v5)                      recent_evidence
  case rubric points (signable buckets)            active_training_intent
  machine_spec / list_rule specs                          │
        │                                                 │
        ▼                                                 ▼
  ┌──────────────── RESOLVER BRIDGE (NEW, read-only) ───────────────┐
  │ resolve_from_compiled_bundle(question_id) → resolution dict     │
  │ Four-gate verify (mirror objective_runtime_adapter._governed_   │
  │   index): internal consistency · status==release_candidate ∧    │
  │   NOT published · pinned content_hash matches canonical_pointer  │
  │   · namespace hardcoded. Reads tracked supply pointer ONLY,      │
  │   never scans the artifact dir. Sets server-side                 │
  │   governed_registry_status (the F1 seam).                        │
  └─────────────────────────────────────────────────────────────────┘
        │
        ▼  build_luban_context_pack(resolution, retrieval_sources, learner_context)
  ┌──────────────────────────────────────────────────────────────────┐
  │ question_context  status / qid / type / stem / options / avail     │
  │ source_context    compiled_source_refs (authority)                 │
  │                   + retrieval_refs (is_answer_key=False ALWAYS;     │
  │                     retrieval_is_grading_authority=False) [verified]│
  │ rubric_context    rubric / required_terms / list / spec / calc;    │
  │                   rubric_signed = registry_status∈RELEASE_GRADES   │
  │                     ∧ rubric  [verified compiled_context.py:169]    │
  │ learner_context   PCP / recent_evidence / training_intent;         │
  │                   is_second_memory_authority=False                 │
  │ diagnostic_policy official_score_allowed =                         │
  │                     status==resolved ∧ has_signed_authority ∧      │
  │                     registry_status∈RELEASE_GRADES;                │
  │                   llm_may_change_answer_key=False;                 │
  │                   retrieval_may_become_answer_key=False;           │
  │                   candidate_work_order (when unresolved)           │
  │ budget_policy     source/rubric/learner token caps                 │
  │ provenance        per-block hashes + supply_bundle_hash +          │
  │                   answer_key_manifest_hash                         │
  └──────────────────────────────────────────────────────────────────┘
        │
        ├─ resolved + signed  → official score allowed (objective deterministic;
        │                       case LLM-adjudicated against the signed rubric)
        └─ unresolved/candidate → official_score_allowed=False; fail OPEN to open-world
                                  diagnostic + candidate_work_order (refusal rate = 0)
```

**Exact reuse points:**

- `compiled_context.build_luban_context_pack` — the assembler; six blocks already correct (verified). We supply it a `resolution` dict; we do not change it.
- `compiled_context.build_pack_from_question_context` — the F1-hardened runtime entry; **ignores any client-supplied `registry_status`**, honors only a server-side `governed_registry_status` kwarg. The resolver sets that kwarg.
- `deep_question_adapter._stamp_compiled_context_and_authority` — already stamps `release_truth` from `pack.official_score_allowed`, and stamps `official_score_laundering_guard` when no governed binding (verified `:33-64`). The resolver simply makes `official_score_allowed` *true* for a controlled cohort when a signed bundle resolves the question — no change to the stamping discipline.
- `objective_runtime_adapter._governed_index` — copy its four-gate verify pattern into the resolver bridge.
- `full_knowledge_compiler.verify_lane_bundle` — fail-closed tamper check the resolver runs before trusting a bundle.

**Capability-amplifier property lives here:** a question that misses the bank is *not refused* — it gets a `candidate_work_order` + an `unverified_diagnostic` open-world answer, and that work_order flows back into the candidate ledger (§7). The pack narrows nothing; it focuses the LLM on the most valuable scoped context and routes misses into the living loop.

---

## 7. The continuous feedback loop (越用越强)

Today the loop is broken at two seams: (a) the LLM organizer is a token-sample sidecar whose JSONL nobody reads; (b) M20 deltas stage GO but have no executor. **Both are the same missing wire.** The fix is one forward path with one bridge module at each open seam — **no new WS, no new registry authority** (AGENTS hard constraint).

```
runtime misses / review queue / open-world / new RAG / M20 deltas / council disputes
      │
      ▼ (1) FEEDBACK INGEST  → make_candidate / work_order_from_open_world / absorb_m20_deltas
      │     [today: compiler_feedback.py has ZERO callers — the ingest bridge is its producer]
      ▼ (2) S2 LLM ORGANIZE  → DeepSeek/Qwen propose rubric/source/spec/work_order candidates
      │     [today: token sample on a citation string — feed REAL point text + required_terms,
      │      WRITE results back as make_candidate(kind=rubric/machine_spec, origin=llm_guess)]
      ▼ (3) GOVERNED REVIEW  → a governed actor re-tags accepted candidates origin=teacher_review/
      │                        governed_registry. ONLY this re-tag makes a candidate promotable.
      ▼ (4) S3 DETERMINISTIC GATES (G0–G8)
      ▼ (5) S4 ADVERSARIAL/COUNCIL (down-rank only)
      ▼ (6) S5 SIGN → release_candidate bundle (append-only, versioned, rollback-pointed)
      ▼ (7) SUPPLY BUNDLE → tracked runtime_supply/vN bundle + canonical_pointer (M21S/M31 pattern)
      ▼ (8) S6 RESOLVER → context pack → 5 surfaces
      └──────────────── work_orders + rejects + new misses feed back to (1) ────────────────┘
```

**Loop-until-dry termination** (runtime misses arrive in unknown quantity):

```
run_id = new
seen = load_content_hashes(prior_runs)            # content-addressed dedup
queue = S0.ingest(all six sources)
while queue and iterations < MAX_ITER:
    batch       = queue.take(BATCH_SIZE)          # bounded fan-out cost
    candidates  = S2.fanout(S1.normalize(batch))  # small models
    gated       = S3.gates(candidates)            # deterministic G0–G8
    adjudicated = S4.council(gated.disputed)      # gated 4-model
    bundle      = S5.sign(adjudicated.signable)   # deterministic
    feedback    = S7.reingest(gated.work_orders + gated.rejected + adjudicated.disputes)
    new_items   = [e for e in feedback if e.evidence_id not in seen]
    queue.extend(new_items); seen |= {e.evidence_id for e in new_items}
emit build_ledger(all_candidates)                 # §9 invariants must hold
```

Guarantees: content-addressed dedup (no item twice), `MAX_ITER` ceiling, and S7 re-emits only items that produced *new* work-orders (a fully-resolved or twice-rejected item is terminal). Bounded — cannot spin on the same miss.

**M20's 22 dead work-orders** get exactly this treatment: the "missing M20.3 executor" *is* S7→S0 re-ingest (via `absorb_m20_deltas`) + S5 promotion for the 69 already-staged deltas whose origin is governed and whose validators pass.

**The two new bridges (the only loop-closing code):**

- **`feedback_ingest_bridge`** — calls `make_candidate` / `work_order_from_open_world` from the open-world path and `absorb_m20_deltas` from the M20 staging output. Gives `compiler_feedback.py` its producer.
- **`compiled_registry_resolver`** — read-only manifest + pointer lookup → `resolution` dict for `build_luban_context_pack` (mirrors `_governed_index` four-gate verify). Gives the signed bundle its runtime consumer.

Both are append-only thin wrappers: they create no new authority, only connect existing signed artifacts to existing consumers.

---

## 8. RECOMMENDED FIRST VERTICAL SLICE

**Goal:** one end-to-end run S0→S7 on **ONE lane** with **REAL evidence**, producing a signed bundle the resolver hands to `build_luban_context_pack`, consumed by the runtime for a controlled cohort, with the loop re-ingesting at least one work-order — proving the factory, not a report. **Landable with no remote / production / canonical write.**

### Lane choice: case-rubric **`machine_spec`** lane

Rationale (fuses both proposals' slice picks):
- Objective is already 100% deterministic and already bound (M31) — it proves nothing new.
- The `machine_spec` lane has a fully-built deterministic gate (`_machine_spec` + 7-vector `attack_spec`, `fp_total==0`) and is **not yet in runtime** — so success is novel.
- `official_answer` is legitimately a *case-rubric seed* here — so the slice exercises the exact provenance boundary (seed ≠ source) most likely to be violated.
- It is where today's gap (LLM sidecar, dead work-orders) actually bites.

### Evidence source (REAL)

- N≈20 ambiguous calc/machine-checkable case scoring points from `scripts/build_luban_case_rubric_expansion_m2.py` output (real exam JSON → draft AuditPackets), with **real 2026 教材 `content_markdown`** for the verbatim anchor check.
- One M20 `machine_spec_delta` row from `candidate_delta_registry_m20.jsonl` routed via `absorb_m20_deltas` (proves the M20 executor path).

### Files to ADD

| File | Purpose |
|---|---|
| `deeptutor/services/construction_grading/compiler_pipeline.py` | Pure deterministic `run_pipeline(evidence, *, run_id)` — the S0–S7 spine (~300 lines, calls only existing primitives). |
| `deeptutor/services/construction_grading/feedback_ingest_bridge.py` | Producer for `compiler_feedback.make_candidate` / `work_order_from_open_world` / `absorb_m20_deltas` (closes Gap: zero callers). |
| `deeptutor/services/construction_grading/compiled_registry_resolver.py` | `resolve_from_compiled_bundle(question_id) -> resolution` (four-gate verify; the missing S6 seam). |
| `scripts/run_luban_compiler_pipeline_slice.py` | Runner: wires real M2 evidence + DeepSeek S2 worker + gates + sign + resolver + S7 re-ingest; emits artifact ledger. |

### Files to MODIFY (surgical, append-only)

- None in the runtime hot path for the slice. The resolver is invoked behind the existing `governed_registry_status` kwarg in `build_pack_from_question_context`; `deep_question_adapter._stamp_compiled_context_and_authority` already reads `official_score_allowed` and needs no change. Cohort gating reuses the existing `LUBAN_M31_*` env/cohort pattern.

### S2 worker (real, gated)

DeepSeek-V4-flash via `deeptutor.services.llm.factory.complete`, prompt from the M5B `_jury_prompt` family, emitting `machine_spec_candidate` / `rubric_candidate` **through `make_candidate`** (origin `llm_guess`). This single wire fixes landscape Gap #1 (sidecar) + Gap #2 (zero callers) at once. If `DEEPSEEK_API_KEY` absent → S2 emits `candidate_draft` and the deterministic lanes run identically (existing `--no-llm` discipline).

### Artifact ledger (emitted by the runner, local only)

`artifacts/luban_grading_artifacts/living_compiler_slice_<date>/`:
- `evidence_inventory.jsonl`, `candidate_ledger.jsonl` (via `build_ledger`)
- `signed_release_candidate_bundle.json` (+ `verify_lane_bundle` proof), `runtime_supply/v_slice/` tracked bundle + `canonical_pointer`
- `pipeline_safety_report.json` (§9 invariants), `adversarial_attack_results.json` (`validator_attack` + 7-vector)
- `loop_reingest_proof.json` (run-1 vs run-2 `seen` sets), `FINDING_living_compiler_slice.md`

### Tests (TDD-first, RED before GREEN)

| Proof | Assertion |
|---|---|
| Wiring | `codegraph_callers(make_candidate)` returns the pipeline (today: empty); `make_candidate` called ≥1× from the LLM path. |
| Signing | S5 bundle: `verify_lane_bundle(bundle, ns) == True`, `published == False`. |
| Provenance | every signed point carries `textbook_anchor` with `match_method=="verbatim"`; a planted non-verbatim point → `work_order`, not signed. |
| Spec attack | signed spec `fp_total == 0` across the 7 vectors. |
| Laundering (regression) | planted `model_vote`/`rag_chunk`-origin answer-key candidate → `rejected` with `source_laundering_blocked`; `build_ledger.candidate_used_as_release_truth == 0`. |
| Seed ≠ source | `official_answer`-derived candidate signs as case-rubric seed, never as textbook source. |
| Loop (越用越强) | run-2 `seen` strictly ⊃ run-1; planted miss reappears as new `runtime_miss` evidence; M20 delta promotes through `absorb_m20_deltas`. |
| Runtime hand-off | resolver → `build_luban_context_pack`: no `governed_registry_status` ⇒ `official_score_allowed == False`; signed bundle + server status ⇒ `rubric_signed == True`. Client `registry_status` ignored (F1). |
| Cohort | `non_cohort_blocked == true`; flag-off path byte-identical (`legacy_equal_rate == 1.0`). |
| Baseline | 294 construction_grading tests pass + slice tests. |

---

## 9. Quality + safety GO gates (exact metrics)

### 9.1 Safety / authority invariants — **every one exactly 0 / false** or the run is NO-GO

```
false_positive = 0                          source_laundering = 0
bad_certified = 0                           official_score_laundering = 0
source_mismatch = 0                         answer_key_override = 0
model_vote_as_source = 0                    council_vote_as_source = 0
rag_chunk_as_answer_key = 0                 official_answer_as_source = 0
candidate_used_as_release_truth = 0         list_partial_auto = 0
legacy_overwrite = 0                        production_write_count = 0
shadow_or_candidate_promoted_to_mastery = 0
published_registry = false                  canonical_truth_written = false
```

Emitted two ways, both already in code: at birth (`build_ledger` counts `source_laundering_blocked`, asserts `candidate_used_as_release_truth == 0`) and at sign (every lane manifest carries the `*_as_source = 0` fields; `verify_lane_bundle` recomputes hash + signature, fail-closed). `validator_attack()` runs as a mandatory fixture every release gate.

### 9.2 Runtime-safety gates (S6 hand-off)

```
legacy_equal_rate = 1.0   (flag-off path byte-identical)
non_cohort_blocked = true     kill_switch_works = true
tamper_fail_closed = true     provider dual-failure = fail-closed (legacy intact)
```

### 9.3 Quality / precision (must beat the plan's pinned baselines)

- source candidate exact-match rate ↑ vs M10/M12A (S3 verbatim hit-rate, per run) · spec clarity ↑ · candidate precision ↑ (M17B gate) · review deflection quantifiable and ↓ (M18 gate) · teacher-packet quality ↑ vs M16 · partial-credit + 大白话 recognition ↑ vs M16 · point-level explanation granularity ↑ vs M16.
- `list_rule` coverage `== 1.0` before any list spec auto-certifies (M7 gate).
- `evidence_span_valid_rate ≥ 0.973` (M22/M24 floor); runtime adjudication uses DeepSeek-V4-flash / Qwen fallback on every real call (≥80 live calls for scale-out axis).
- artifact versioned + rollback-able (`rollback_pointer` set; `verify_lane_bundle` fail-closed).

### 9.4 Learning Brain (§0.15.5)

LB evidence coverage `≥ 0.95` · `unsupported_claim_rate = 0` · `generic_fallback_rate ≤ 0.05` · PCP from a single read model · `training_intent` is prescription authority, `next_best_action` is view only · dream-cycle outputs candidates only · `shadow_promoted_to_mastery = 0`.

### 9.5 Open-world / compiled context (§0.26.6)

refusal rate `= 0` (except safety/irrelevant) · every open-world response carries uncertainty/status label and **no** formal score · candidate/work-order generation for high-value unknowns `≥ 90%` · compiled context consumed by `≥ 3` surfaces (already 5) on a single schema.

### 9.6 The 12 mandatory compiler quality questions (§0.14.6)

Must be answerable with evidence on every M17+ result. Decisive ones for this design: where does the LLM organize vs only QA · which outputs are candidate vs signed · does runtime call DeepSeek/Qwen on every real adjudication · are false_positive/bad_certified/source_mismatch all 0 · does LB have a real gate or only preview · is provider failure fail-closed · is every artifact versioned + rollbackable · does this advance real production usability, not just another report.

---

## 10. Explicitly OUT OF SCOPE (needs separate authorization)

- **Publish.** `published` stays `False`. Moving any artifact to `published` requires a separate publish gate + explicit user authorization. Not exercised by this compiler.
- **Production default flip.** NO-GO for broad production. Requires async/timeout/rate-limit hardening, operator live-monitoring window, cost/latency SLO instrumentation, and explicit user authorization (deferred to a separate release gate).
- **Canonical learner-truth write.** `canonical_truth_written = false`. L4 stays preview-only / dry-run; promotion to mastery needs a teacher-final / real-retest truth-write gate as a separate milestone.
- **Remote / Aliyun / DB write.** Slice is local TestClient only. Any remote action obeys AGENTS §3.7 (only `/root/deeptutor` writable) under separate deployment authorization.
- **Broad-cohort objective answer-key binding.** Slice binds the signed bundle to the controlled cohort (`qa_/test_/operator_`) only; production-default objective scoring is the single remaining engineering mainline behind its own gate.
- **Langfuse production observability.** JSONL ledger substitute for the slice; full instrumentation is a pre-broad-production gap.

---

## 11. Reusable-asset map (zero net-new authority surfaces)

| Pipeline need | Existing asset (verified) | Path |
|---|---|---|
| Candidate bus + laundering guard (G0) | `make_candidate` (`:73-89`), `_entry` (`:47-59`), `build_ledger` (`:121-140`), `work_order_from_open_world` (`:94-118`) | `deeptutor/services/construction_grading/compiler_feedback.py` |
| Signing lanes + two-level hash (S5) | `compile_*_release_candidate`, `build_compiled_knowledge_registry_manifest`, `_sha256_hex` | `deeptutor/services/construction_grading/full_knowledge_compiler.py` |
| Tamper detection (S3/S6) | `verify_lane_bundle` | `deeptutor/services/construction_grading/full_knowledge_compiler.py` |
| Verbatim provenance gate (G2) | `verify_textbook_anchor` | `scripts/luban_case_rubric_schema.py` |
| Machine-spec attack (G4) | `_machine_spec`, `matcher_accepts`, `attack_spec` (7-vector) | `scripts/build_luban_non_textbook_rubric_authority_factory_m10.py` |
| Council pattern (G7, down-rank only) | `_adjudicate` (M5B), `_council_decision` (M5D) | `scripts/run_luban_case_rubric_jury_live_m5b.py`, `scripts/build_luban_case_rubric_source_court_m5d.py` |
| Runtime context hand-off (S6) | `build_luban_context_pack` (`:238`), `build_pack_from_question_context` (`:294`, F1 seam), `_diagnostic_policy` (`:186`), `RELEASE_GRADES` (`:38`) | `deeptutor/services/construction_grading/compiled_context.py` |
| Four-gate resolver verify (S6) | `_governed_index` | `deeptutor/services/construction_grading/objective_runtime_adapter.py` |
| Authority stamp at runtime | `_stamp_compiled_context_and_authority` (`:33-64`) | `deeptutor/services/construction_grading/deep_question_adapter.py` |
| Tracked supply bundle (S7→runtime) | `build()` M21S pattern + `runtime_supply/v3_*` precedent | `scripts/build_luban_runtime_supply_bundle_m21s.py` |
| M20 delta executor (loop) | `absorb_m20_deltas` + `candidate_delta_registry_m20.jsonl` | `full_knowledge_compiler.py` + M20 artifacts |
| Runtime-consumption template + regression fixture | `runtime_consumption_projection`, `validator_attack` | `scripts/run_luban_full_knowledge_compiler_m30.py` |
| Evidence collection (slice input) | `_iter_exam_files`, `_find_verbatim_anchor`, `_build_packet` | `scripts/build_luban_case_rubric_expansion_m2.py` |

**Only genuinely new code:** `compiler_pipeline.py` (S0–S7 spine), the S2 worker prompts/routing, `feedback_ingest_bridge.py`, `compiled_registry_resolver.py`. Everything else is wiring proven, already-guarded assets into the loop — which is exactly why the LLM stops being a sidecar and the work-orders stop dying.

> **INDEX reminder (AGENTS §Plan Directory Discipline):** add this doc to `docs/plan/INDEX.md` before merge.
