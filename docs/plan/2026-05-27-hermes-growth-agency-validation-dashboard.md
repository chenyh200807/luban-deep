# 鲁班智考 Hermes Growth Agency Validation Dashboard

**Status:** Proposed v1  
**Created:** 2026-05-27  
**Purpose:** Define how Hermes evaluates product preheat, growth experiments, and agent output quality. This prevents "busy work" from being mistaken for business growth.

---

## 1. North Star

```text
Weekly real graded answers with a next-action click.
```

Why this metric:

- real graded answers prove demand
- next-action clicks prove the product loop continues
- weekly cadence shows repeatability

## 2. Funnel

```text
Exposure
  -> Click / DM / group join
  -> Answer submission
  -> Report viewed
  -> Next task clicked or requested
  -> Second answer submitted
  -> Paid challenge / coaching / teacher pilot
```

## 3. Daily Metric Table

Hermes must output this table daily.

| Date | Channel | Asset/Hook | Exposure | Click/DM | Answers | Reports viewed | Next task | Second answers | Paid | Teacher leads | Evidence level |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
|  |  |  |  |  |  |  |  |  |  |  |  |

## 4. Funnel Rate Table

| Rate | Formula | Early target | Meaning |
| --- | --- | ---: | --- |
| Click rate | click / exposure | channel-dependent | hook strength |
| Submission rate | answers / click | > 15% for high-intent private channels | offer clarity |
| Report view rate | reports viewed / answers | > 60% | product delivery trust |
| Next-task rate | next task / reports viewed | > 30% | loop strength |
| Second-answer rate | second answers / answers | > 20% | habit potential |
| Paid intent | paid or asks price / reports viewed | > 5% early signal | monetization |

Targets are early learning targets, not final business benchmarks.

## 5. Evidence Levels

| Level | Label | Examples | Decision use |
| --- | --- | --- | --- |
| L0 | Idea | plan, hypothesis, generated copy | cannot justify scaling |
| L1 | Execution | content posted, DM sent | proves work happened |
| L2 | Weak interest | likes, saves, comments, group joins | useful but insufficient |
| L3 | Strong intent | answer submitted, teacher requests sample | validates pain |
| L4 | Product loop | report viewed, next task clicked, second answer | validates loop |
| L5 | Business | payment, teacher batch, renewal, referral | validates monetization |

Hermes must label every result by evidence level.

## 6. Experiment Card

Every growth experiment must use this structure.

```markdown
## Experiment

Name:
Owner agent:
Date:

Hypothesis:

Audience:

Channel:

Offer:

Asset:

Expected user action:

Success metric:

Minimum evidence threshold:

Result:

Decision: STOP / REPEAT / SCALE / PIVOT

Reality Checker notes:
```

## 7. Reality Checker Scorecard

| Question | Pass condition |
| --- | --- |
| Did a real learner submit an answer? | screenshot, form record, or transcript |
| Did a real learner view a report? | product/event evidence or direct confirmation |
| Did a user ask for next task? | transcript or click event |
| Did a user submit a second answer? | answer record |
| Did a user pay or ask pricing? | payment record or transcript |
| Did a teacher offer real student answers? | transcript or uploaded batch |
| Did content drive a measurable action? | channel-to-action link |

If none pass, the day is a learning failure even if many assets were produced.

## 8. Channel Review

Weekly channel review table:

| Channel | Answers | Report views | Next tasks | Paid/teacher evidence | Operator effort | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| WeChat DM |  |  |  |  |  |  |
| WeChat group |  |  |  |  |  |  |
| Douyin/视频号 |  |  |  |  |  |  |
| Xiaohongshu |  |  |  |  |  |  |
| WeChat OA |  |  |  |  |  |  |
| Teacher outreach |  |  |  |  |  |  |

Decision rules:

- SCALE only if L3+ evidence is present.
- REPEAT if L2 interest exists and funnel friction is fixable.
- PIVOT if users respond to pain but not offer.
- STOP if there is no L2 after serious execution.

## 9. Agent Quality Review

Hermes agent output is useful only if humans can execute it.

| Agent | Output quality question | Fail example | Pass example |
| --- | --- | --- | --- |
| Growth Orchestrator | Is there one objective? | "increase awareness" | "collect 30 answer submissions" |
| Market Intelligence | Are claims sourced? | "competitors are strong" | "3 competitor offers priced 99-399" |
| Product PM | Does copy reduce friction? | "AI empowers learning" | "免费批改 1 题" |
| Content Lead | Does content map to CTA? | random tips | script ends with answer submission CTA |
| Private Domain | Can operator send it now? | abstract community ideas | exact group/DM messages |
| Sales Agent | Is pilot low-friction? | buy our platform | send 30 anonymous answers |
| Analytics | Does it identify bottleneck? | numbers only | "report view is the leak" |
| Reality Checker | Does it reject vanity? | celebrates likes | demands answer submissions |

## 10. Product Feedback Triage

Hermes must classify product feedback.

| Severity | Definition | Example | Required evidence |
| --- | --- | --- | --- |
| P0 | blocks the core funnel | user cannot submit answer | screenshot/transcript |
| P1 | harms trust or conversion | report unclear on scoring points | user quote |
| P2 | improves growth | shareable diagnosis card | repeated request or funnel opportunity |
| P3 | future feature | leaderboard, referral automation | roadmap only |

No product feedback should enter engineering planning without:

- affected funnel step
- user evidence
- expected metric impact
- smallest viable change
- validation method

## 11. Weekly Decision Memo

Hermes must produce this every 7 days.

```markdown
# Weekly Growth Decision Memo

## 1. Real Evidence Summary

## 2. Best Channel

## 3. Best Hook

## 4. Biggest Funnel Leak

## 5. Strongest User Quote

## 6. Strongest Teacher Signal

## 7. Product Friction

## 8. Experiments to Stop

## 9. Experiments to Repeat

## 10. Experiments to Scale

## 11. Prompt Changes Required

## 12. Next Week Objective
```

## 12. Launch-to-Scale Gate

Do not move from preheat to paid scaling until at least four of these are true:

- 100+ real answer submissions
- 60+ report views
- 30+ next-task clicks or requests
- 20+ second answers
- 10+ paid small-package or challenge conversions
- 3+ teacher pilots
- one reusable class report case study
- one channel with repeatable L3+ evidence

If these are not true, continue preheat or fix product conversion.
