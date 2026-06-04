# FINDING — M19C Limited Default Flip (2026-06-05)

## Verdict
- M19C limited default flip: **GO**
- current limited default state: **ON**
- broad production default: **NO-GO**
- canonical learner truth write: **NO-GO**

## Scope
- authorization_detected=True
- default_mode=one_percent_qa_operator_default
- default_cohort_prefixes=['qa_', 'operator_']
- allowed_internal_cohort_prefixes=['qa_', 'test_', 'operator_']
- production_db_write_enabled=False
- canonical_truth_write_enabled=False
- published_registry_emitted=False

## Live `/api/v1/ws` drill
- submissions=100
- cohort_coverage=['operator_', 'qa_', 'test_']
- default_on_cohort_coverage=['operator_', 'qa_']
- non_cohort_real_student_blocked=True
- legacy_equal_rate=1.0
- production_write_count=0
- canonical_truth_written=False

## Provider / fallback / safety
- deepseek_success_count=52
- qwen_fallback_count=5
- provider_failure_failclosed_count=3
- live_llm_calls_executed=False
- safety_all_pass=True

## Notes
M19C does not include M20 delta, does not issue live LLM calls, and does not write remote/Aliyun config. The executed flip is the local authorized limited default config package plus real TestClient `/api/v1/ws` verification. Remote deployment still requires separate explicit authorization and path review.
