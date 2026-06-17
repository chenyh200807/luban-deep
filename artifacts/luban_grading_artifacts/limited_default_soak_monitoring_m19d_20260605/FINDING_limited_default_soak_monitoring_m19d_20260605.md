# FINDING — M19D Limited Default Soak Monitoring (2026-06-05)

## Verdict
- M19C input state: **ON**
- M19D soak verdict: **GO**
- keep limited default ON: **YES**
- remote/Aliyun deployment authorization review: **GO**
- broad default: **NO-GO**
- canonical learner truth write: **NO-GO**

## Soak window
- submissions_total=300
- cohort_hit_count=231
- non_cohort_blocked_count=15
- deepseek_success_count=256
- qwen_fallback_count=10
- failclosed_count=8
- fallback_rate=0.036496
- failclosed_rate=0.029197
- latency p50/p95/p99=26.654/45.969/72.451 ms
- M20.1 delta absorbed: **NO**

## Safety
- false_positive=0
- bad_certified=0
- source_mismatch=0
- unsupported_positive=0
- legacy_overwrite=0
- production_write_count=0
- canonical_truth_written=False
- all_pass=True

## Rollback readiness
- env_kill={'state_correct': True, 'switch_path_latency_ms': 21.314, 'legacy_intact': True}
- registry_unavailable={'state_correct': True, 'switch_path_latency_ms': 24.757, 'legacy_intact': True}
- request_flag_withdraw={'state_correct': True, 'switch_path_latency_ms': 18.197, 'legacy_intact': True}

## Next
M19E remote deployment authorization package. Remote/Aliyun deployment still requires separate explicit authorization and path/command review.

## 12 Questions
1. M19C ON 状态是否读取：**True**。
2. 真实 /api/v1/ws submissions 数量：**300**。
3. qa_/operator_ default-on 是否命中：**YES**，cohort_hit_count=231。
4. non-cohort 是否 blocked：**YES**，non_cohort_blocked_count=15。
5. kill switch 是否立即有效：**True**。
6. malformed registry 是否 fail-closed：**True**。
7. provider failure / Qwen fallback 是否正确：**YES**，qwen_fallback_count=10，failclosed_count=8。
8. legacy 是否 100% unchanged：**YES**，legacy_overwrite=0。
9. production_write / canonical_truth 是否 0：production_write_count=0，canonical_truth_written=False。
10. latency/cost 是否在预算内：**YES**，p99=72.451ms，cost_estimate_p95_usd=0。
11. M19D verdict：**GO**。
12. 下一步是否允许进入 remote/Aliyun limited config authorization：**YES**。
