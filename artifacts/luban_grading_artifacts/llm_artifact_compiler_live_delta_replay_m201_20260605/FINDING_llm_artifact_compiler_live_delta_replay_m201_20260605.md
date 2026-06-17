# FINDING — M20.1 Live Delta Replay（2026-06-05）

## Verdict

1. M20.1 live delta replay：**GO**。
2. release-candidate delta：**GO**。
3. production default impact：**improve**。
4. can feed next formal registry candidate：**YES**。
5. can affect current M19B default decision：**NO**。

## 必答

1. M20 delta hash 是否一致：**True**，hash=0a5d134336a22fd5ebe930e13705cde6af469662721cb5a8d7131c226c18d5e5。
2. 69 accepted delta 是否全部读取并分类：**True**，kind_counts={'list_rule_coverage_delta': 7, 'rubric_normalization_delta': 4, 'machine_spec_delta': 8, 'grading_packet_compression_delta': 34, 'learning_brain_claim_mapping_delta': 16}。
3. 临时 packet builder 是否只在 explicit flag 下生效：**YES**，脚本内 monkeypatch，退出即恢复；live provider 只有 `--run-live-delta-replay`。
4. base vs delta token/packet size 是否改善：token **1200->1064**；packet bytes delta=1086.05（delta 携带候选 hints，byte size 可增加）。
5. delta 是否降低 validator downgrade rate：**True**。
6. delta 是否提升 point coverage 或 Learning Brain card specificity：point coverage delta=0；LB specificity 84->84。
7. false_positive/source_mismatch/unsupported positive 是否仍全 0：fp=0，source_mismatch=0，unsupported_positive=0。
8. Qwen fallback 是否在 delta packet 下可用：fallback_success=10，provider_stub_used=False。
9. adversarial attacks 是否全 pass：**True**。
10. production runtime/DB/default 是否完全未改：**YES**，production_write=0，canonical_truth=false，default_changed=false。
11. release-candidate delta 是否从 WEAK-GO 升 GO：**YES**。
12. 是否允许交给下一版 formal registry candidate：**YES**。

## Notes

- 当前模式：live_delta_replay。
- 若本轮是 stubbed_shadow_replay，不能冒充 live；需要重新运行：
  `python scripts/run_luban_llm_artifact_compiler_live_delta_replay_m201.py --run-live-delta-replay --samples 100 --fallback 10`
