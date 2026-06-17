# FINDING — LLM Artifact Compiler Continuous Factory M20（2026-06-04）

## Verdict

1. continuous artifact compiler：**GO**。M20 已把 M17A/M17B/M17C runtime 反馈、validator downgrade、council disagreement、M18C/M18D Learning Brain proof、M13D review queue 统一编译成 candidate delta ledger。
2. release-candidate delta：**WEAK-GO**。deterministic signer 通过，但本轮只做 logged real `/api/v1/ws` replay projection，没有把 delta 接到新 packet builder 做 live shadow replay。
3. production default impact：**improve**。只改善 artifact supply / GradingPacket 上下文，不改 production default。

## 12 问

1. 六类 workflow pattern 怎么用：classify-and-act 分桶 12 类；fanout-and-synthesize 用 DeepSeek/Qwen/GPT/Opus 四角色生成非 source 建议；generate-and-filter 产出 122 个 candidate 和 6 个 rejected variants；adversarial verification 跑 source/list/calc/unsupported-positive 攻击；tournament 选择最小稳定 delta；loop-until-done 保证每个 candidate 的 final_action 属于 accept/reject/needs_more_evidence/work_order。
2. 小模型/大模型/确定性脚本做了什么：DeepSeek/Qwen roles 负责批量 triage 与中文/list 边界；GPT/Opus roles 负责 schema/compat 与 adversarial judge；本轮无 live call，确定性脚本负责分类、候选生成、hash、source boundary、attack、signer。
3. 输入规模：M17B/M18 runtime submissions=130，point decisions=347，validator downgrades={'deterministic_matcher_rejected_llm_accept': 34}，review queue=202。
4. candidate delta 总数：122；action 分布：{'accept': 69, 'work_order': 22, 'reject': 1, 'needs_more_evidence': 30}。
5. delta 类型分布：{'list_rule_coverage_delta': 18, 'rubric_normalization_delta': 17, 'machine_spec_delta': 23, 'grading_packet_compression_delta': 34, 'external_source_work_order': 2, 'source_candidate_delta': 2, 'learning_brain_claim_mapping_delta': 26}。
6. accepted release-candidate delta：69；accepted 类型：{'list_rule_coverage_delta': 7, 'rubric_normalization_delta': 4, 'machine_spec_delta': 8, 'grading_packet_compression_delta': 34, 'learning_brain_claim_mapping_delta': 16}。
7. rejected variants：6，覆盖 official_answer/source laundering、model/council vote laundering、partial list auto、bad calc、unsupported positive。
8. deterministic signer：schema_validation_pass=True，source_boundary_validation_pass=True，delta_hash=0a5d134336a22fd5ebe930e13705cde6af469662721cb5a8d7131c226c18d5e5。
9. adversarial attack：all_attacks_pass=True，fp/source_mismatch/legacy_overwrite/production_write/canonical_truth 均为 0/false。
10. WS shadow replay：使用真实 `/api/v1/ws` 历史 shadow logs 做 replay projection，token budget 1200->1064，validator downgrade rate 0.0893->0.0461；未执行新 live WS。
11. 是否把 official_answer/model_vote/council_vote 升 source：**NO**。signer 记录 official_answer_upgraded_to_textbook=0，model_vote_as_source=0，council_vote_as_source=0。
12. 是否改 production runtime / DB / canonical learner truth：**NO**。production_runtime_connected=false，production_write_count=0，canonical_learner_truth_written=false。

## Delta Package

- source candidate delta / external work order：只给 source-hunt/work-order，不签 source truth。
- rubric normalization delta：只修 packet/rubric candidate，不进 formal registry。
- machine spec delta：缺公式/单位/expected value 的保持 needs_more_evidence。
- list_rule coverage delta：任何 incomplete denominator/item set 不 auto。
- GradingPacket compression delta：把 validator downgrade reason 压缩进 point-local packet hints。
- Learning Brain claim mapping delta：只用 M18D real retest proof 做 dry-run mapping，不写 mastery。

## Next

单句总指挥建议：**M20 compiler 可以进入连续运行；下一步不是 production default，而是把 accepted delta 接入临时 packet-builder shadow harness，跑 live `/api/v1/ws` delta replay 后再升级 release-candidate delta 到 GO。**
