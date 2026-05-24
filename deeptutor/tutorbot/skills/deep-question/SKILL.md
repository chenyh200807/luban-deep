---
name: deep-question
description: "Generate quiz questions on any topic. Default to questions only unless the user explicitly asks for answers."
metadata: {"nanobot":{"emoji":"❓","requires":{"bins":["deeptutor"]}}}
always: false
---

# Deep Question (Quiz Generation)

Use the `exec` tool to invoke DeepTutor's quiz generation pipeline (ideation → evaluation → generation → validation).
默认行为：
- 用户说“出题 / 考我 / 来一道 / 练习 / 下一题”时，只给题目，不要主动公布答案或解析。
- 只有用户明确要求“带答案 / 附解析 / 公布答案”时，才展示答案或解析。

## Authority

| Business fact | Authority | This Skill responsibility |
| --- | --- | --- |
| Question generation pipeline | `deep_question` capability | Invoke ideation, evaluation, generation, and validation |
| Topic and constraints | User request / runtime context | Pass language, count, difficulty, type, and grounding config |
| Answer visibility | `answer_reveal_policy` / caller policy | Default to question-only output |
| Domain adaptation | Caller skill such as `construction-question-supply` | Receive constraints, but do not invent domain authority |

## Forbidden Authority

- Do not grade user answers or produce a grading result.
- Do not write learner state, mistake book items, reports, or long-term plans.
- Do not decide TutorBot routing; callers choose when to invoke this skill.
- Do not bypass validation or answer-reveal policy by exposing hidden answers by default.
- Do not turn generated questions into official question-bank rows.

## Anti-Patterns

- User asks "quiz me", and the response includes the answer key without being asked.
- The caller provides a domain authority, but this skill overrides it with generic assumptions.
- Generated questions skip validation and are treated as production question-bank content.
- The skill writes study progress or weakness diagnosis directly after generating a question.

## When to Use

- User wants **practice questions** or **quizzes** on a topic
- User is preparing for an exam or self-testing
- User asks to "generate questions", "quiz me", "create practice problems"

## Command

```bash
deeptutor run deep_question "<topic>" --format json -l <lang> [options]
```

### Options

| Flag | Description |
|------|-------------|
| `-l <lang>` | Response language: `en` or `zh` |
| `--config num_questions=N` | Number of questions (default: 1, max: 50) |
| `--config difficulty=<level>` | `easy`, `medium`, `hard` |
| `--config question_type=<type>` | `multiple_choice`, `open_ended`, `true_false`, etc. |
| `--config mode=<mode>` | `custom` (default) or `mimic` |
| `-t rag` | Ground questions in a knowledge base |
| `--kb <name>` | Knowledge base to use |

## Examples

Basic quiz:
```bash
deeptutor run deep_question "Calculus integration techniques" --format json -l en --config num_questions=5 --config difficulty=medium
```

Multiple-choice from a textbook:
```bash
deeptutor run deep_question "Chapter 3: Linear Algebra" --format json -l zh -t rag --kb math-textbook --config question_type=multiple_choice --config num_questions=10
```

Hard open-ended questions:
```bash
deeptutor run deep_question "Quantum mechanics fundamentals" --format json -l en --config difficulty=hard --config question_type=open_ended
```

## Important

- This capability can take **over a minute** for multiple questions — use `timeout=300` with the `exec` tool.
- Parse NDJSON events with `"type": "content"` for the generated questions and answers.
