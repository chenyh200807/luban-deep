# RichLeaf compiled_context 污染治本 — Candidate v3 交接 (owner signoff)

> **状态**: Codex GO **for candidate tier**（≠ production GO）。signoff 上线前仍需 owner 授权 + near-live A/B + frozen sample audit。
> **红线守住**: 生产 bundle / schema / runtime 默认门控**零改动**；本 candidate `production_write_count=0`。

## 1. 问题与根因

- **问题**: `rich_leaf_context_bundle.json`（1595 leaf）的 `compiled_context` 污染——同 chunk 下多个 leaf_name 不同的知识点共享同一份 payload（concepts/exam_patterns/rules/teaching_cards 逐字节相同），leaf 拿到错主题内容（"屋面防水"叶取到"焊缝夹渣"）。全库 175 铁污染。**直接毁判分召回**（按 leaf 取 context 取到错主题）。
- **根因（shared shape = producer/consumer granularity mismatch）**: 铸造点 `scripts/run_luban_rich_leaf_v23_residual_source_repair.py` 的 `_compile_context(span_text, chunk, chunk_id)` **入参没有 leaf_name** → 整 chunk 编一份挂给该 chunk 全部 leaf。编译单位(chunk) ≠ 召回单位(leaf)。
- 异源(Codex)判定: A 真污染 43% / B 粒度污染 57% / C 假阳 **0%**（无假阳）。

## 2. 治本（编译层单点，非 blocklist 打补丁）

| 改动 | 文件 |
|---|---|
| per-leaf 切分（按 leaf_name 匹配 chunk 内子标题段落，positive+negative check 防 wrong-slice） | `scripts/luban_rich_leaf_subsection.py`（新） |
| per-leaf 编译入口 | `scripts/run_luban_rich_leaf_v23_residual_source_repair.py`（compile_context_for_leaf） |
| fail-closed 门（同 chunk 两 leaf 完整 payload sha256 相同即全 block 落 quarantine）+ 铸造点接 per-leaf | `scripts/run_luban_rich_leaf_frozen_full_compile.py` |
| 测试 | `tests/scripts/test_luban_rich_leaf_subsection.py`（新）+ `test_luban_rich_leaf_frozen_full_compile.py` |
| 污染检测器 | `docs/原始数据/考点原料/detect_richleaf_pollution.py` |

三原则: first principle（编译单位=召回单位=leaf）/ less is more（单点 fail-closed 门 + 删 lecture 第二套规则，消费端 `rich_leaf_runtime.py` 零改动）/ 治本不治标（blocklist 是止血带，真闭环在编译层）。

## 3. 结果（每项已人工亲核）

- 污染 **175 → 0**（detector + 完整 payload sha256 + 跨 chunk 三重验证，clean 内同 chunk 碰撞 0）
- compiled **1454** / quarantine **158**（`unsliceable 23 / over_subdivided 107 / mislink 22 / fail_closed_collision 6`）；全账 1454+158 = 1612
- lecture_page = 0；全库跨 chunk 完整 payload 碰撞 = 0
- pytest **30 passed**（subsection + frozen_full_compile suite）
- **40 个母题 pack 不受损**：782 scoring_point 100% chunk-anchored，与被 quarantine 的 leaf context 解耦

## 4. 质量保证（双异源三轮迭代到 GO）

- v1 污染→0 → 双异源 NO-GO（验证专家:切分误杀 79%；Codex:wrong-slice + 门只 hash 前 600 字符不闭包）
- v2 quarantine 374→158 + 完整 hash + collision 全 block + substring 词边界 → Codex 发现 D=lecture fallback 没删干净 NO-GO
- v3 删该单点 + RED→GREEN 测试 → **Codex 干净复审 = D GO，总裁决 GO for candidate tier**
- 插曲: Codex 一轮复审在 read-only sandbox grep 抓错 v1 report 当 v3，人工亲核 v3 真实 report 纠正（教训: 别盲信异源输出，关键数字源要亲核）

## 5. signoff 上线前必做（owner）

1. **owner 授权**: schema `luban_rich_leaf_context_bundle.v1` 是 contract-governed（`contracts/schema_registry.yaml`），若 candidate 要带 `source_span` 字段进生产记录需授权 + 更新 pin 测试。
2. **near-live A/B shadow**（不上默认 runtime，`LUBAN_RICH_LEAF_RUNTIME_ENABLED` 保持 off）: 走 `compiled-knowledge-shadow-eval` skill。
3. **frozen sample audit**: 抽查 compiled 样本 + quarantine 样本，重点 lecture lane / 1:1 heading-anchored whole-span / formerly polluted multi-leaf chunk。

## 6. 残留工单（不阻断 candidate，但 signoff 前应有处置）

- **mislink 22**: leaf chunk_id 指错（上游 taxonomy evidence 误链），**不自动重链**（错链=新污染），走 `needs_source` 人工/异源裁决。
- **over_subdivided 107**: taxonomy 过度细分的抽象高层节点（-E01/-G01/-R），taxonomy owner 决定合并 leaf 还是补原子源。
- **C 类中文 substring**: `core in title` forward 方向，标已知限制（零污染证据；加词边界需分词器=新依赖，违 less-is-more）。
- fail-closed 门 scope = 同 chunk（设计边界）；全库跨 chunk 碰撞已验 0，gate 不扩。
