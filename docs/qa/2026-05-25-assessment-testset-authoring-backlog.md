# Assessment TestSet Authoring Backlog

Date: 2026-05-25

Source audit:

```text
docs/qa/2026-05-25-assessment-testset-topic-catalog-form-bank-audit.md
```

## Summary

All required P0B topics currently meet the `stable` threshold in the live
Supabase-backed dry run:

```text
stable_topics=10
pilot_topics=0
authoring_needed_topics=0
forms_per_topic=5
delivered_count_per_topic_form=12
```

## Backlog Rows

No authoring handoff rows are required for this dry run.

| topic_id | status | active_forms | minimum_needed | stable_needed | missing_scored_items | section_gap | owner | target_date | user_visible_state |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| _none_ | stable coverage complete | 5 | 0 | 0 | 0 | none | n/a | n/a | enabled |

## Rule

If a future dry run drops any topic below 3 valid active forms, that topic must
move to `authoring_needed`, show `待补题` if visible, and stay disabled until
owner/date/count gaps are filled and the catalog gate is rerun.
