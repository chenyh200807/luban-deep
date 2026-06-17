# FINDING — Teacher Review Ops Hardening M13D（2026-06-04）

## 10 问

1. queue 是否可用：**YES**。consolidated queue=202，100% final disposition=True，unknown_disposition=0。
2. 老师 packets 是否够用：**YES**。teacher packets=202，覆盖当前全部 queue；平均长度=624.74 字符。
3. 老师操作成本：pending_rate=0.8911；包内直接给出非正式分、证据、阻断原因、建议动作、是否可 override。
4. confirm/reject/override dry_run 是否覆盖：**YES**。action ledger 包含 confirm、duplicate retry、reject、override、mistaken high-risk accept。
5. 幂等是否成立：**YES**。duplicate confirm action hash 一致=True。
6. 误点守卫是否成立：**YES**。guarded_attempts=30，high-risk/source_gap mistaken accept 不 auto、不写 mastery。
7. production DB 写入：**0**。
8. LB canonical writeback：**0**。
9. source/spec/list policy 是否被改：**NO**，source_authority_mutation=False。
10. M13/M14 limited release 是否被 review ops 阻塞：**NO**。review ops 本身可用；若阻塞，阻塞来自评分 authority/source coverage，不来自老师操作闭环。

## Operator Metrics

- override_rate=0.2411
- reject_rate=0.2411
- risk_counts={'low': 22, 'high': 10, 'medium': 170}
- authority_kind_counts={'calculation': 10, 'exact_required': 26, 'high_risk_review': 15, 'figure_label': 6, 'list_rule': 6, 'source_backed_positive': 10, 'machine_spec_positive': 7, 'list_spec_positive': 10, 'miss': 10, 'partial': 8, 'contradiction': 3, 'high_risk': 6, 'external_source': 6, 'duplicate': 5, 'machine_checkable_logic': 9, 'machine_checkable_calculation': 3, 'question_stem_fact': 12, 'list_rule_full_coverage': 14, 'textbook_verbatim': 17, 'adversarial_negative': 19}

## Red Lines

不碰评分 authority；不改 runtime；不写 production DB；不写 canonical learner truth；不改 source/spec/list policy；所有 action 都是 dry_run。
