---
name: luban-rich-leaf-compiler
description: Use this for DeepTutor Luban Nexus-like RichLeafArtifact compiler work, full 2026 source compilation, source-evidence agents, semantic review queues, runtime-supply candidates, scoring A/B, Grading-to-Brain Loop dry-runs, or any task that could confuse candidate artifacts with release truth.
---

# Luban Rich Leaf Compiler

Use this skill to run RichLeaf/Nexus-like compilation without creating a second
truth source or accidentally promoting AI candidates into runtime authority.

## Start Gate

Write this frame before changing code, generating artifacts, or reporting GO:

```text
one business fact:
one authority:
source lanes:
candidate/review/release state:
runtime default status:
Learning Brain write status:
verification target:
not_exercised:
```

If any state is unknown, mark it `unknown` or `not_exercised`; do not infer GO.

## Authority Rules

- Taxonomy comes from canonical taxonomy only. LLMs cannot edit leaf ids or paths.
- Textbook/standard source spans are source truth; lecture is teaching evidence;
  question bank is assessment evidence; student answers are learner/sample evidence.
- RichLeafArtifact is compiled context authority, not source truth, rubric truth,
  learner truth, official score, or release truth.
- AI/council/Codex review is `shadow` unless a separate governance gate says
  otherwise.
- `candidate_only`, `review_only`, `runtime_install_allowed=false`,
  `release_truth_claimed=false`, `official_score_allowed=false`, and
  `production_write_count=0` must survive every workbench artifact.
- Runtime default, canonical learner truth, official score, remote write, and DB
  write require explicit authorization and readback gates.

## Compiled Context Granularity — per-leaf invariant (HARD)

> 失败形状 = `producer/consumer granularity mismatch`（生产粒度 ≠ 消费粒度）。2026-06-21 实证：`_compile_context(span_text, chunk, chunk_id)` **入参没有 leaf_name** → 按 chunk 整块编一份 payload 挂给该 chunk 下**全部** leaf → 同 chunk 多 leaf 的 concepts/exam_patterns/rules/teaching_cards **逐字节相同** = 名实不符污染（"屋面防水"叶拿到"焊缝夹渣"内容）。全库 1595 leaf 中 175 铁污染。直接毁判分召回（按 leaf 取 context 取到错主题）。

- **compiled_context 必须 per-leaf**：编译单位 = 召回单位 = leaf。编译入口必须吃 `leaf_name`，从 chunk 内**该 leaf 的子段落**（markdown 子标题 / 编号子项）切，**绝不**整 chunk 编一份挂多 leaf。工具 `scripts/luban_rich_leaf_subsection.py`（`slice_leaf_subsection`，positive+negative check 防 wrong-slice）。
- **切不准就 quarantine，不瞎切**：无子标题锚定 / 名义歧义 / 父段含多 sibling → abstain → quarantine（落 `needs_source`），瞎切 = 制造新污染。两条 lane（textbook/lecture）统一规则，**禁回退整 chunk**（第二套宽松规则）。
- **A 类误链不自动重链**：leaf 的 chunk_id 指错（chunk 里无该内容）→ 标 `mislink` quarantine 工单，**不自动找别的 chunk**（错链 = 新污染）。
- **fail-closed 门（唯一汇点，结构防再污染，替代 blocklist）**：`enforce_no_intra_chunk_pollution` —— 同 chunk 下任意两 leaf 的 **完整 payload sha256** 相同即**全 block**（不留未证明 owner）落 quarantine。这是唯一让"再污染"结构上不可能的点。**不要在消费端加过滤 / 不要靠 blocklist / scanner 打地鼠**——那是止血带，挡不住生产端下次再产（root-cause skill：静态闸是止血不是闭包）。
- **检测**：`docs/原始数据/考点原料/detect_richleaf_pollution.py`（同 chunk context 指纹碰撞 + iron 分级）；任意 bundle 跑出污染数，clean 内必须 0。
- 案例与双异源迭代记录见 memory `richleaf-compiled-context-per-leaf-fix`；candidate 在 `artifacts/luban_grading_artifacts/rich_leaf_per_leaf_pollution_fix_candidate_v3_20260621/`（污染 0 / quarantine 158 / 生产零改动 / Codex GO for candidate tier，signoff 前仍需 owner 授权 + near-live A/B + frozen sample audit）。

## Workflow

1. Lock paths and dirty state:
   - `pwd -P`
   - `git rev-parse --show-toplevel`
   - `git status --short --branch`
   - record source root, usually `.../FastAPI20251222/docs/2026`
2. Run or inspect Phase 0 contracts:
   - schema/validator
   - source lane registry
   - field claim envelope
   - lifecycle matrix
   - CompiledContextPack contract
3. Compile candidates in this order:
   - sampler
   - skeleton compiler
   - source gap candidates
   - candidate patch generator
   - patch evidence audit
   - weak source refinement
   - source-evidence agent
   - semantic audit packets / queue / shards / suggestions
4. Convert suggestions to review decisions only as shadow review:
   - accept/reject/needs-external may be materialized with reviewer id
   - manual-review remains missing, not forced through
   - validate decisions before audit-record ingestion
5. Only after validated decisions:
   - build semantic evidence audit record
   - build reviewed candidates
   - compile rich field candidates
   - assemble artifact candidates
   - run interop audit and focused tests
6. Only after reviewed artifact candidates exist:
   - build runtime supply candidate in a new versioned directory
   - run regression, context-pack smoke, offline/nearline/live A/B as available
   - keep runtime default off until authorized
7. For Grading-to-Brain:
   - produce `learner_memory_event` candidates only
   - run sandbox/test learner readback gates before any write
   - never let RichLeaf write canonical learner truth directly

## Decision Table

| Evidence | Allowed claim |
|---|---|
| source-gap candidates only | review-ready source candidates |
| patch precheck pass | machine-prechecked strong candidates |
| suggestions only | non-binding review suggestions |
| shadow decisions validated | shadow-reviewed candidates |
| reviewed candidates > 0 | reviewed source-ref candidates |
| artifact candidates > 0 + interop pass | local candidate artifact bundle |
| runtime supply candidate + regression | runtime candidate, not default |
| live A/B + authorization + rollback | controlled-default candidate |
| governance signoff | release claim, if gate says so |

## NO-GO Signals

- Bucket/taxonomy/authority fields are hand-filled to pass a gate.
- `source_ref` is created without readable path, record id, span, and hash.
- Question-bank evidence becomes mandatory rule.
- Synthetic mistakes become learner truth.
- `manual_review_required` is auto-accepted.
- Interop summary is used without checking what its count actually means.
- A local/offline adapter result is reported as live provider A/B.
- Runtime default or DB write happens before explicit authorization.
- `compiled_context` 按 chunk 整块编一份挂多 leaf（同 chunk 下多 leaf 的 payload 相同）= per-leaf 不变量破裂，见上节；任何 candidate 投影前必须跑 `detect_richleaf_pollution.py` 确认 clean 内同 chunk 碰撞 0。

## Verification

For code changes, run focused tests first, then the RichLeaf suite:

```bash
python3 -m pytest tests/services/construction_grading/test_rich_leaf_artifacts_phase0.py tests/scripts/test_luban_rich_leaf_*.py -q
```

For artifact runs, print summary fields from each JSON and assert the boundary:

```text
candidate counts:
decision counts:
reviewed candidate counts:
artifact candidate counts:
safety invariants:
not_exercised:
```

Do not claim completion from green tests alone. Match the claim to the strongest
artifact actually produced.

## Report Template

```text
Status:
Compiled scope:
Artifacts produced:
Reviewed candidate count:
Runtime/default status:
Learning Brain write status:
Tests:
Safety invariants:
NO-GO / WEAK-GO blockers:
Next action:
```
