# nanobot Skills

This directory contains built-in skills that extend nanobot's capabilities.

硬约束：`catalog.yaml` 只允许作为 validation/discovery surface，不能被 runtime code import 或包装成 loader。运行时 skill 加载 authority 只能是 `SkillsLoader` 和 `question_lifecycle_skills`。

## Skill Format

Each skill is a directory containing a `SKILL.md` file with:
- YAML frontmatter (name, description, metadata)
- Markdown instructions for the agent

## Attribution

These skills are adapted from [OpenClaw](https://github.com/openclaw/openclaw)'s skill system.
The skill format and metadata structure follow OpenClaw's conventions to maintain compatibility.

## Available Skills

| Skill | Description |
|-------|-------------|
| `github` | Interact with GitHub using the `gh` CLI |
| `weather` | Get weather info using wttr.in and Open-Meteo |
| `summarize` | Summarize URLs, files, and YouTube videos |
| `tmux` | Remote-control tmux sessions |
| `clawhub` | Search and install skills from ClawHub registry |
| `skill-creator` | Create new skills |
| `construction-exam-tutor` | Teach 建筑实务 concepts, question reviews, case analysis and error review |
| `construction-question-supply` | Supply 建筑实务 practice questions while preserving answer reveal policy |
| `construction-question-review` | Review true questions and active questions without bypassing reveal policy |
| `construction-mcq-grading` | Grade and diagnose 建筑实务 single-choice and multi-choice answers |
| `construction-case-grading` | Grade and diagnose 建筑实务 case-study written answers |
| `construction-learning-evidence-story` | Narrate existing learning evidence with evidence refs and degraded claims |
| `construction-study-assistant` | Turn existing training intent and attempt detail into one next action |
| `construction-learning-support` | Support frustration, anxiety and low motivation without taking grading or plan authority |
| `deep-question` | Generate quiz questions through the DeepTutor capability |
| `lecture-waterproof-energy-decoration` | Provide lecture-map support for waterproof, energy-saving and decoration topics |
