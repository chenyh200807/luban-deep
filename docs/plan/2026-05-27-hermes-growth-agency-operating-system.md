# 鲁班智考 Hermes Growth Agency Operating System

**Status:** Proposed v1  
**Created:** 2026-05-27  
**Purpose:** Define how Hermes runs the growth agency every day, how humans feed data back, how decisions are made, and how prompts self-evolve.

---

## 1. Daily Rhythm

Hermes runs one daily cycle.

```text
Morning: plan
Midday: execution support
Evening: data intake and reality review
Weekly: self-evolution
```

The operator should not ask Hermes for broad advice. The operator should give Hermes inputs and ask for the next executable plan.

## 2. Morning Prompt

```text
Run today's 鲁班智考 Growth Agency planning cycle.

Yesterday data:
- exposure:
- clicks:
- answer submissions:
- reports viewed:
- next-task clicks:
- second answers:
- shares:
- paid conversions:
- teacher leads:
- teacher answer batches:

Qualitative evidence:
- best user quote:
- biggest objection:
- best content hook:
- worst-performing channel:
- product friction observed:

Available resources today:
- operator hours:
- content production capacity:
- private-domain capacity:
- product/engineering support:
- budget:

Now output the required 今日增长作战报告.
```

## 3. Daily Report Format

Hermes must output this format exactly.

```markdown
# 今日增长作战报告

## 1. 今日唯一目标

## 2. 今日主推 Offer

## 3. 今日核心假设

## 4. 各 Agent 今日任务

## 5. 今日内容生产清单

## 6. 今日私域动作

## 7. 今日渠道动作

## 8. 今日转化动作

## 9. 今日数据表

## 10. Reality Checker 审查

## 11. 今日风险

## 12. 明日三件事
```

## 4. Midday Execution Prompt

Use this when execution gets stuck.

```text
We are executing today's 鲁班智考 growth plan.

Current blocker:

What we tried:

What happened:

Please respond as Growth Orchestrator plus the most relevant specialist agent.
Give:
1. root cause of the blocker
2. the smallest fix
3. revised script or task
4. what evidence to collect next
```

## 5. Evening Data Intake Prompt

```text
Run today's 鲁班智考 Growth Agency evening review.

Today's actual data:
- exposure:
- clicks:
- answer submissions:
- reports viewed:
- next-task clicks:
- second answers:
- shares:
- paid conversions:
- teacher leads:
- teacher answer batches:

Execution evidence:
- posted content links or screenshots:
- user answer screenshots/transcripts:
- report view evidence:
- payment evidence:
- teacher conversation evidence:
- group activity evidence:

What did not happen:

Now produce:
1. funnel analysis
2. strongest real evidence
3. weakest assumption
4. STOP / REPEAT / SCALE / PIVOT decisions
5. tomorrow's recommended single objective
```

## 6. Weekly Self-Evolution Prompt

```text
Run 鲁班智考 Growth Agency weekly self-evolution.

Inputs:
- seven daily reports
- seven Reality Checker reviews
- all metrics
- best content assets
- worst content assets
- user objections
- product friction list
- partner feedback

Tasks:
1. Identify the highest-converting hook.
2. Identify the best channel by real answer submissions.
3. Identify the biggest funnel leak.
4. Identify which agent prompt produced weak output.
5. Propose prompt changes, but only where evidence supports the change.
6. Decide which experiments to stop, repeat, scale, or replace.
7. Update next week's battle plan.

Output:
- weekly growth memo
- prompt changelog
- experiment decision table
- next-week plan
- Reality Checker final verdict
```

## 7. Decision Rules

### 7.1 STOP

Stop a task if:

- it produced no answer submissions after 3 serious attempts
- it produced only likes/views
- users misunderstood the offer
- it required product capability that does not exist
- operator effort is higher than evidence value

### 7.2 REPEAT

Repeat if:

- sample size is too small
- users showed intent but conversion path broke
- one hook worked but asset quality was weak
- private-domain follow-up was incomplete

### 7.3 SCALE

Scale only if:

- the channel produced real answer submissions
- report views happened
- at least some users clicked next task or asked to continue
- cost and manual effort are acceptable

### 7.4 PIVOT

Pivot if:

- the pain exists but the offer language is wrong
- users want grading but not a challenge
- teachers respond but learners do not
- learners respond but do not trust AI grading

## 8. Evidence Levels

| Level | Evidence | Meaning |
| --- | --- | --- |
| L0 | idea only | not evidence |
| L1 | content posted | execution evidence only |
| L2 | click/comment/DM | weak interest |
| L3 | real answer submitted | strong preheat evidence |
| L4 | report viewed or next task clicked | product-loop evidence |
| L5 | paid or teacher batch uploaded | business evidence |

Hermes must label every claim with an evidence level.

## 9. Operator Checklist

Before asking Hermes for tomorrow's plan, collect:

- what was posted
- where it was posted
- how many people saw it
- how many clicked
- how many submitted answers
- how many saw reports
- how many continued
- what users said
- what teachers said
- what broke

## 10. Product Feedback Contract

Hermes can request product changes, but must classify them:

| Class | Definition | Example |
| --- | --- | --- |
| P0 conversion blocker | blocks answer submission or report viewing | no obvious submit button |
| P1 trust blocker | reduces willingness to use/pay | report lacks scoring-point detail |
| P2 growth accelerator | improves but does not block | shareable diagnosis card |
| Future | not needed during preheat | full referral system |

No product request is accepted unless it includes:

- user evidence
- affected funnel step
- expected metric impact
- smallest change
- validation method

## 11. File and Artifact Naming

Recommended Hermes output artifacts:

```text
growth/daily/YYYY-MM-DD-battle-report.md
growth/daily/YYYY-MM-DD-reality-review.md
growth/content/YYYY-MM-DD-content-pack.md
growth/research/YYYY-MM-DD-market-brief.md
growth/prompts/YYYY-MM-DD-prompt-changelog.md
growth/partners/YYYY-MM-DD-partner-outreach.md
```

If Hermes cannot write files, it should output sections with these exact names for manual saving.

## 12. First 7-Day Operating Goal

By the end of Day 7, the team must know:

1. Which hook gets real answer submissions.
2. Which channel gets the highest-intent users.
3. Whether users trust the grading report.
4. Whether users want a second task.
5. Whether users will pay for a small package or challenge.
6. Whether teachers will provide student answer batches.

If these are unknown after 7 days, the agency has generated content but not business learning.
