# G6 Real WeChat Package Preflight

- Gate: `G6_real_wechat_package_page_automation`
- Verdict: `true_entry_pending`
- Blocking reason: true WeChat package page automation evidence is required; /wechat-harness or DevTools login/open preflight is insufficient
- Scope: `read_only_pre_authorization_preflight`
- Execution mode: `read_only_no_devtools_launch`
- Without authorization: `decision_package_only`
- Required authorization: `devtools_or_manual_wechat_qa_window`
- DevTools project root: `yousenwebview`
- Target subpackage: `packageDeeptutor`

This artifact does not launch DevTools, open the project, drive pages, or write product state. It only defines the evidence boundary for true WeChat package-page acceptance.

## Evidence Classification

- wechat_harness: `shadow_not_real_wechat_package`
- devtools_islogin: `environment_preflight_only`
- devtools_open_project: `project_preflight_only`
- package_page_automation: `required_missing`

## No-Write Invariants

- production_write_count: `0`
- canonical_truth_written: `False`
- remote_write_count: `0`
- published_registry_executed: `False`

## Preconditions

- devtools_e2e_script_present: `True`
- project_root_is_yousenwebview: `True`
- target_subpackage_is_packageDeeptutor: `True`
- true_package_page_automation_executed: `False`
- wechat_harness_not_counted_as_real: `True`
- devtools_login_or_open_not_counted_as_pass: `True`

## Single Authority

- no_second_grading_truth: `True`
- no_second_learner_truth: `True`
- real_entry_evidence_source: `DevTools/miniprogram automation against yousenwebview project root plus packageDeeptutor page flow`
- wechat_harness_role: `shadow QA only`
- pcp_role: `read_only_feedback_context`

## Evidence

- `AGENTS.md`
- `scripts/run_wechat_learning_brain_devtools_e2e.py`
- `tests/services/member_console/test_home_dashboard_learning_projection.py`

## Stop Conditions

- only /wechat-harness evidence is available
- DevTools islogin/open is reported as scenario pass
- project root is packageDeeptutor instead of yousenwebview
- auth_state/auth_mode is unknown but reported as pass
- page-level automation result is missing
- any canonical learner truth write is requested by this gate
