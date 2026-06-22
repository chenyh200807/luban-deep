# P40 Animation IR Batch Report

Generated: 2026-06-22

## Scope

- Source authority: `docs/plan/鲁班移动端提分闭环/2026-06-19-luban-animation-pack-taxonomy-alignment-registry.md` slots 1-40.
- Mother-topic data source: `docs/原始数据/考点原料/成品/*.md`.
- Output prefix: `P40_`.
- Output index: `P40_index.html`.
- Output manifest: `P40_animation_ir_batch_manifest.json`.

## Result

- Generated: 39 teaching animation preview packs.
- Blocked: 1 pack.
- Gate result: 39/39 generated packs passed `validate_animation_ir_contract.mjs` and `validate_animation_ir_preview.mjs`.
- No MP4 files generated. HTML preview is the review surface; Remotion thin wrappers were generated so formal rendering can consume the same IR later.

## Blocked

| Slot | Pack | Reason |
|---:|---|---|
| 24 | D14 | Missing `成品/D14_*.md`; not enough mother-topic data to produce a real deep-topic animation. |

## Workflow Lessons Applied

1. Subtitle timing must cover the whole beat in preview mode. Real TTS timing can replace it later, but preview gates sample scene tails and must never see an empty caption.
2. Visual labels and full scoring text must be separate. SVG primitives receive short 4-8 character labels; full key points stay in captions, coach text, and AI context.
3. Registry pack IDs are not always safe student DOM/URL IDs. `E05` is a valid pack ID but collides with internal error-code token checks, so the student-facing card id is `P40_ECON05` while the manifest keeps `pack_id=E05`.
4. 6+1 archetype selection must control the visual grammar, not just the narration. Each IR now writes `render_contract.archetype_visual_required`; `validate_animation_ir_contract.mjs` fails if the card is text-container-only or misses the required primitive.
5. HTML preview and Remotion must share primitive coverage. The contract gate now checks both `render_animation_ir_preview.py` and generic `AnimationIrRenderer.tsx` support every visual kind used by the IR; either side missing a branch is a hard FAIL.
6. Claude CLI review caught the previous asymmetric-renderer gap: HTML preview had a catch-all text fallback while Remotion coverage was gated. The fallback is now removed for unknown primitives, and this failure shape is recorded in the skill anti-patterns.

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

- These are batch first-pass teaching animations, not final精品卡. They now use per-archetype diagram primitives, but the primitives are still generic visual archetypes rather than hand-authored expert diagrams for every pack.
- Audio is not generated in this batch. The previews use virtual playback plus timing-derived captions; TTS can be generated later per selected candidates.
- `coarse_review` packs passed UI/IR gates but remain internal-only until source/leaf review is resolved.
