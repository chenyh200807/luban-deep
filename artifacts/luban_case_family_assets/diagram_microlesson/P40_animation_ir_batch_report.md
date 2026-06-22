# P40 Animation IR Batch Report

Generated: 2026-06-22

## Scope

- Source authority: `docs/plan/鲁班移动端提分闭环/2026-06-19-luban-animation-pack-taxonomy-alignment-registry.md` slots 1-40.
- Mother-topic data source: `docs/原始数据/考点原料/成品/*.md`.
- Output prefix: `P40_`.
- Output index: `P40_index.html`.
- Output manifest: `P40_animation_ir_batch_manifest.json`.
- Quality status: `coarse_draft_requires_single_card_review`.
- Student ready: `false`.

## Result

- Generated: 39 teaching animation preview packs.
- Blocked: 1 pack.
- Gate result: 39/39 generated packs passed `validate_animation_ir_contract.mjs` and `validate_animation_ir_preview.mjs`, but this is now treated only as structural/internal-review PASS.
- Diagrammatic teaching result: 39/39 generated packs have 5/5 diagrammatic teaching scenes (`hook / map / rule / trap / score`), and every `score` scene uses a non-text answer-paper/diagnosis primitive.
- Primitive animation result: animated 6+1 primitives now use internal steps instead of whole-block fade. HTML preview emits `data-primitive-step`; Remotion generic renderer uses `PrimitiveStep`; contract gate checks both via `html_internal_animation` and `remotion_internal_animation`.
- Non-text visual ratio: 50% after removing auxiliary hook/score notes; previous 23% proved that "has one primitive" was still too text-heavy.
- No MP4 files generated. HTML preview is the review surface; Remotion thin wrappers were generated so formal rendering can consume the same IR later.

## Blocked

| Slot | Pack | Reason |
|---:|---|---|
| 24 | D14 | Missing `成品/D14_*.md`; not enough mother-topic data to produce a real deep-topic animation. |

## Workflow Lessons Applied

0. **Batch PASS is not product quality**. The P40 batch exposed the failure mode directly: generic markdown extraction can satisfy structure gates while still feeling like a text explanation. From now on, batch output stays `coarse_draft_requires_single_card_review`; student-ready cards must be accepted one by one through mobile screenshots and a diagram-first review.

1. Subtitle timing must cover the whole beat in preview mode. Real TTS timing can replace it later, but preview gates sample scene tails and must never see an empty caption.
2. Visual labels and full scoring text must be separate. SVG primitives receive short 4-8 character labels; full key points stay in captions, coach text, and AI context.
3. Registry pack IDs are not always safe student DOM/URL IDs. `E05` is a valid pack ID but collides with internal error-code token checks, so the student-facing card id is `P40_ECON05` while the manifest keeps `pack_id=E05`.
4. 6+1 archetype selection must control the visual grammar, not just the narration. Each IR now writes `render_contract.archetype_visual_required`; `validate_animation_ir_contract.mjs` fails if the card is text-container-only or misses the required primitive.
5. HTML preview and Remotion must share primitive coverage. The contract gate now checks both `render_animation_ir_preview.py` and generic `AnimationIrRenderer.tsx` support every visual kind used by the IR; either side missing a branch is a hard FAIL.
6. Claude CLI review caught the previous asymmetric-renderer gap: HTML preview had a catch-all text fallback while Remotion coverage was gated. The fallback is now removed for unknown primitives, and this failure shape is recorded in the skill anti-patterns.
7. `archetype_visual_required` is necessary but not sufficient. A card can contain one correct primitive and still feel like a text explanation. The new rule is `diagrammatic_teaching_scene`: `hook / map / rule / trap / score` must be diagram-led, and `score` must render as answer-paper/diagnosis instead of stacked text boxes.
8. Auxiliary text near dense diagrams should be treated as suspect. The first diagrammatic pass added `note` helpers, and the runtime gate correctly caught hook label collisions on 360/390/430/wide viewports. The fix was deletion, not coordinate tuning: captions and coach cards carry prose; visual stage carries diagrams.
9. Diagram-led still is not enough if the diagram itself does not animate the knowledge action. The next hard rule is primitive-internal animation: process flow traces steps, layer stacks reveal layers, network/formula graphs grow paths, decision trees expand branches, contrast pairs reveal wrong then right, and answer scans move row by row. Whole-primitive fade is now treated as "static diagram pseudo-animation".

## Archetype Visual Coverage

| Archetype | Required primitive | Generated |
|---|---|---:|
| `decision_branch_reveal` | `decision_tree` | 8 |
| `process_step_reveal` | `process_flow` | 8 |
| `section_or_spatial_reveal` | `layer_stack` / `roof_section` | 13 |
| `calculation_structure` | `network_graph` / `formula_chain` | 5 |
| `scoring_diagnosis_reveal` | `answer_scan` | 3 |
| `contrast_reveal` | `contrast_pair` | 1 |
| `value_memory_card` | `memory_table` | 1 |

## Current Limitations

- These are batch first-pass teaching animation drafts, not final 精品卡. They now use per-archetype diagram primitives, but the primitives are still generic visual archetypes rather than hand-authored expert diagrams for every pack.
- The batch should not be continued as a 40-card delivery stream. Use it only as a candidate pool; pick one card, make the diagram explain the knowledge action, verify on phone screenshots, then move to the next card.
- The workflow now enforces diagram-led scenes and primitive-internal animation, but visual richness is still bounded by the current primitive library. Next improvement should add more expert primitive variants per archetype, not return to text cards.
- Audio is not generated in this batch. The previews use virtual playback plus timing-derived captions; TTS can be generated later per selected candidates.
- `coarse_review` packs passed UI/IR gates but remain internal-only until source/leaf review is resolved.
