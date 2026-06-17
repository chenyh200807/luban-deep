# 鲁班智考 Hermes Growth Agency Master Plan

**Status:** Proposed v1  
**Created:** 2026-05-27  
**Owner surface:** Hermes Agent, Weixin/private-domain operations, growth experiments, product preheat, content operations, partnership outreach  
**Primary goal:** Use Hermes as a self-improving growth agency to gather market information, organize plans, execute preheat campaigns, and drive measurable business growth for 鲁班智考.

> This plan adapts the `agency-agents` style: each agent has a role, mission, workflow, deliverables, and success metrics. Hermes is the operating layer. DeepTutor/鲁班智考 remains the product and data authority.

---

## 1. Executive Decision

Do not give Hermes one giant prompt.

Hermes should run a multi-agent growth operating system:

```text
Core business objective
  -> Growth Orchestrator
  -> specialized agents
  -> concrete deliverables
  -> daily execution
  -> evidence intake
  -> Reality Checker
  -> weekly self-evolution
```

The first business phase is **product preheat**, not large-scale paid acquisition.

Preheat means:

1. Prove that real construction-exam learners care about "case answer grading".
2. Collect real answers, real objections, real wording, and real channel signals.
3. Build a small but strong proof loop before scaling spend.
4. Convert evidence into 7-day challenge, 30-day coaching, and teacher/agency pilots.

## 2. Core Positioning

### 2.1 Public Position

```text
建筑实务 AI 阅卷官
做一题，批一题，知道每一分丢在哪。
```

### 2.2 Product Promise

User submits one construction practical case answer and receives:

- estimated score
- scoring-point breakdown
- missed points
- error cause
- improved answer version
- next training task

### 2.3 What We Are Not

Hermes agents must not describe 鲁班智考 as:

- AI teacher
- generic education platform
- construction-exam ChatGPT
- all-purpose study assistant
- automatic exam generator
- guaranteed-pass product

### 2.4 What We Are Selling First

Sell the pain before the platform:

```text
你不是不会学，你是不知道案例题每一分丢在哪。
```

## 3. Authority Boundary

Hermes can:

- research market signals
- write content
- propose offers
- plan experiments
- coordinate private-domain operations
- summarize user feedback
- produce sales scripts
- analyze funnel data
- recommend product changes

Hermes cannot be the authority for:

- learner score truth
- grading truth
- question truth
- learning report truth
- member/account truth
- product runtime behavior
- production release status

Canonical product authority remains:

| Business fact | Authority |
| --- | --- |
| Case answer grading | DeepTutor grading and rubric chain |
| Scoring point evidence | construction grading / RAG / question evidence |
| Learner evidence | learning evidence ledger |
| Next task | training intent / product read model |
| Payment and member facts | wallet / member authority |
| Runtime behavior | real app, WeChat surface, logs, Langfuse, production APIs |

## 4. Agency Roster

| Agent | Mission | Primary output |
| --- | --- | --- |
| Growth Orchestrator | Decide the daily objective and coordinate all agents | Daily battle plan |
| Market Intelligence Agent | Gather market, competitor, exam, channel, and user pain signals | Research briefs |
| Product Conversion PM | Turn traffic into answer submission and paid challenge | Funnel and offer improvements |
| Offer Architect | Package free, low-ticket, core, and B2B offers | Offer ladder |
| Content Strategy Lead | Convert positioning into content themes | Content calendar |
| Douyin/Video Agent | Produce short-video scripts | Daily video scripts |
| Xiaohongshu Agent | Produce searchable and saveable notes | Note drafts |
| WeChat OA Agent | Build trust with long-form content | Article outlines |
| Private Domain Operator | Run group, DM, challenge, and renewal scripts | Group SOP and DM scripts |
| Partnership Sales Agent | Recruit teachers, small agencies, and content accounts | Outreach and pilot plan |
| Analytics Reporter | Track funnel and experiment data | Daily metric table |
| Reality Checker | Reject vanity progress and force evidence | GO/NO-GO review |
| Prompt Librarian | Improve agent prompts from evidence | Prompt changelog |

## 5. Operating Phases

### Phase 0: Setup and Baseline, 1-2 Days

Goal: make Hermes executable.

Deliverables:

- agent prompt pack
- daily report template
- growth data table
- channel list
- first 30 content topics
- first outreach list
- first free-grading landing copy

Exit criteria:

- Hermes can output one daily battle plan in the required format.
- Operator can execute the plan without asking what each task means.
- Reality Checker can mark evidence as real or fake.

### Phase 1: Preheat, Days 1-7

Goal: collect the first real answers and user language.

Primary offer:

```text
免费批改 1 道建筑实务案例题，看看你到底丢了哪几分。
```

Targets:

- 100 real answer submissions
- 30 users viewing a grading report
- 10 users doing a second task
- 5 users willing to pay for a small package
- 3 teachers or group owners willing to test a class report

### Phase 2: Challenge Validation, Days 8-21

Goal: validate whether users will follow a 7-day training loop.

Offer:

```text
7 天 AI 案例题提分挑战
每日一题，AI 批改，错因榜，下一题训练。
```

Targets:

- 50 paid/committed challenge users
- 30% completion
- 3+ answers per active learner
- 20% challenge-to-30-day intent

### Phase 3: Revenue and Partnership, Days 22-30

Goal: turn evidence into paid coaching and teacher pilots.

Offers:

- 30 天实务陪练营
- 老师班级错因报告试点
- AI 助教批改后台试点

Targets:

- 10 paid 30-day users or equivalent pilot revenue
- 3 teacher pilots
- 1 reusable class report case study

## 6. North Star and Supporting Metrics

North Star:

```text
Weekly real graded answers with a next-action click.
```

Supporting metrics:

| Metric | Why it matters |
| --- | --- |
| Answer submissions | proves pain and intent |
| Report views | proves the grading result is valuable enough to inspect |
| Next-action clicks | proves the loop can continue |
| Second answer submissions | proves habit potential |
| Share rate | proves social proof |
| Paid conversion | proves monetization |
| Teacher pilot upload count | proves B2B potential |

## 7. Reality Gate

A day is not successful because content was produced.

A day is successful only if at least one of these happened:

- a real learner submitted an answer
- a real learner viewed a report
- a real learner asked for the next task
- a real learner paid
- a real teacher uploaded or promised real student answers
- a content item produced measurable inbound interest

Vanity metrics:

- likes without submissions
- group size without answers
- article views without clicks
- "feedback is good" without screenshot or transcript
- AI-generated plans without execution

## 8. Self-Evolution Loop

Hermes improves itself weekly, but only from evidence.

Weekly loop:

1. Aggregate all daily reports.
2. Identify winning channels, hooks, and objections.
3. Rewrite weak agent prompts.
4. Stop unproductive tasks.
5. Add one new experiment class only if a real bottleneck justifies it.
6. Archive old assumptions as replaced or unproven.

Prompt changes require:

- reason
- evidence
- old behavior
- new behavior
- expected metric impact
- rollback condition

## 9. Required Companion Documents

Use the following documents together:

- [Agent Prompts](2026-05-27-hermes-growth-agency-agent-prompts.md)
- [Operating System](2026-05-27-hermes-growth-agency-operating-system.md)
- [Content and Channel Playbook](2026-05-27-hermes-growth-agency-content-channel-playbook.md)
- [Validation Dashboard](2026-05-27-hermes-growth-agency-validation-dashboard.md)

## 10. Immediate Next Step

Load this plan and the Agent Prompts document into Hermes.

Then run:

```text
Execute Day 1 product preheat.
Goal: collect the first 30 real construction practical case answers or equivalent high-intent leads.
Use the full Growth Agency roster.
Return the required daily battle report and Reality Checker review.
```
