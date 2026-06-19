# J01 Diagram Microlesson Gate

- card: J01
- generated_at: 20260619-221902-82398
- rendered: /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/diagram_microlesson/M_danger_work_expert_argumentation.journey.html
- practice: /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/diagram_microlesson/M_danger_work_expert_argumentation.practice.html
- manifest: /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_case_family_assets/diagram_microlesson/reports/J01/20260619-221902-82398/card_bundle_manifest.json
- note: preview gate does not generate MP4. This gate covers current journey HTML + independent practice HTML deterministic path.

## schema spine
```text
schema spine 校验 (schema_version=luban_diagram_microlesson.v1)
A01_crane_lifting_safety.json: OK template_type=decision_branch_reveal_draft body=decision authority=candidate_teaching_prototype student_safe=contract+boundary
C01_construction_joint_contrast.schema_draft.json: OK template_type=contrast_pair_reveal_draft body=contrast authority=candidate_teaching_prototype student_safe=contract+boundary
D01_answer_point_diagnosis.schema_draft.json: OK template_type=answer_point_diagnosis_draft body=diagnosis authority=candidate_teaching_prototype student_safe=contract+boundary
F16_qigu.json: OK template_type=process_step_reveal (inferred) body=steps authority=candidate_or_signed_mixed student_safe=boundary_only
J01_danger_work_expert_argumentation.schema_draft.json: OK template_type=decision_branch_reveal_draft body=decision authority=candidate_teaching_prototype student_safe=contract+boundary
N01_network_keypath.json: OK template_type=network_plan_keypath body=network authority=candidate_teaching_prototype student_safe=boundary_only
N01_network_keypath_v2.json: OK template_type=network_plan_keypath body=network authority=candidate_teaching_prototype student_safe=boundary_only
N01_network_video_first.json: OK template_type=network_plan_keypath body=network authority=candidate_teaching_prototype student_safe=boundary_only
S01_scaffold_template_acceptance.json: OK template_type=decision_branch_reveal_draft body=decision authority=candidate_teaching_prototype student_safe=contract+boundary

汇总: 9/9 OK
```

## animation_action schema
```text
J01_danger_work_expert_argumentation.lesson.json: PASS animation_action schema
```

## timing sync
```text
PASS J01_danger_work_expert_argumentation.lesson.timing.json total_duration: 150.0s <= 151s
PASS J01_danger_work_expert_argumentation.lesson.timing.json sync_keyword: 所有 claim 段都带 sync_keyword 且命中对应 timing 文本
```

## render journey
```text
✅ M_danger_work_expert_argumentation.journey.html
```

## render practice
```text
✅ M_danger_work_expert_argumentation.practice.html
```

## data-id targets
```text
PASS M_danger_work_expert_argumentation.master.json -> M_danger_work_expert_argumentation.journey.html data-id targets resolved
data-id target gate: PASS
```

## learning stage runtime
```text
PASS portrait_initial_decision: 0 warn
PASS portrait_playing_trial: 0 warn
PASS landscape_playing_trial: 0 warn
PASS wide_playing_trial: 0 warn
PASS portrait_theater_controls: 0 warn
learning-stage runtime gate: PASS (0 warn)
```

## practice preview
```text
PASS M_danger_work_expert_argumentation.journey.html stage_shell_mode: decision-first journey shell
PASS M_danger_work_expert_argumentation.journey.html center_play: has central play affordance
PASS M_danger_work_expert_argumentation.journey.html responsive_stage: declares orientation-adaptive learning stage
PASS M_danger_work_expert_argumentation.journey.html orientation_rules: has landscape or wide-screen layout rules
PASS M_danger_work_expert_argumentation.journey.html theater: has theater/fullscreen mode
PASS M_danger_work_expert_argumentation.journey.html theater_toggle: has real theater/fullscreen toggle
PASS M_danger_work_expert_argumentation.journey.html overlay_controls: has overlay control state
PASS M_danger_work_expert_argumentation.journey.html scrubber: has draggable range scrubber
PASS M_danger_work_expert_argumentation.journey.html practice_link: links independent practice page
PASS M_danger_work_expert_argumentation.journey.html ended_cta: has post-play challenge CTA
PASS M_danger_work_expert_argumentation.journey.html semantic_chapters: semantic chapter labels: 引入/挖深/3米/5米/结论
WARN M_danger_work_expert_argumentation.journey.html lesson_contract: no lessonData JSON or inline chapters found
PASS M_danger_work_expert_argumentation.journey.html student_safe_tokens: no obvious internal authority tokens
PASS M_danger_work_expert_argumentation.practice.html question_count: 6 question sections
PASS M_danger_work_expert_argumentation.practice.html question_visuals: 6 SVG visuals for 6 questions
PASS M_danger_work_expert_argumentation.practice.html score_sentence: has score sentence/output task
PASS M_danger_work_expert_argumentation.practice.html answer_gate: blocks next before answer
PASS M_danger_work_expert_argumentation.practice.html student_safe_tokens: no obvious internal authority tokens
video-first preview gate: PASS (1 warn)
```

## bundle manifest
```text
card_bundle_manifest.json: PASS bundle manifest
```

## Result
PASS deterministic J01 journey gates.
