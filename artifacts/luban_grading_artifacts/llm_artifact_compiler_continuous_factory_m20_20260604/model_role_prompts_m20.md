# M20 Model Role Prompts

No live model calls were executed in this M20 run. These prompts are the reusable worker contracts
for the continuous compiler; current votes are deterministic replay over prior evidence.

## DeepSeek-V4 — batch source-hit triage / strict miss classifier
- Input: runtime misses, validator downgrades, unsupported positives, source/spec gaps.
- Output: classify as source_candidate_delta, spec_delta, packet_delta, reject, or work_order.
- Constraint: may suggest source hunt terms, never declare source truth.

## Qwen 3.7 Plus — Chinese semantics / list-rule boundary reviewer
- Input: Chinese rubric terms, near-synonyms, list_rule partial hits, teacher queue text.
- Output: list item boundary suggestions and partial-credit warnings.
- Constraint: list_rule can become auto only when denominator plus item set coverage equals 1.0.

## Codex GPT5.5 — rubric schema / compiler compatibility architect
- Input: candidate deltas and schema/hash/supersession requirements.
- Output: minimal machine-compatible delta with stable ids and rollback pointer.
- Constraint: model vote is review input only, never source authority or signer.

## Claude Code Opus 4.8 — workflow judge / adversarial verifier
- Input: candidate registry, rejected variants, signer report, attack suite.
- Output: GO/WEAK-GO/NO-GO judgement and source-laundering attack notes.
- Constraint: do not impersonate human/teacher/PO review.
