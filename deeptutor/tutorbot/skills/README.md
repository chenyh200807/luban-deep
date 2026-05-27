# DeepTutor TutorBot Skills

This directory contains DeepTutor's built-in TutorBot and question-lifecycle skills. In the current 鲁班智考 product, these skills are not decorative prompt snippets: they are the named teaching, grading, review, learning-evidence narration, and support authorities used by TutorBot, `deep_question`, grading, and follow-up flows.

硬约束：`catalog.yaml` 只允许作为 validation/discovery surface，不能被 runtime code import 或包装成 loader。运行时 skill 加载 authority 只能是 `SkillsLoader` 和 `question_lifecycle_skills`。

`catalog.yaml` 中的 `export_eligible` 只服务未来导出审计：`internal` 表示可进入内部 pack 候选，`public` 需要单独公开发布审查，`none` 表示不得导出。该字段不是 runtime router 输入。

当前项目边界：

- `TutorBot` 是唯一业务身份；skill 不能发明第二套 tutor / grounded mode / teaching identity。
- `construction-*` skills 是建筑实务陪考链路的教学能力 authority；wrapper 只负责选择和传递上下文。
- 阅卷、错因、learning evidence、study plan、下一题推荐各自有明确 authority，skill 文案不能偷偷计算第二份分数或学情。
- 新增 skill 前先确认它不是现有 skill 的改名，也不会让 `catalog.yaml` 变成 runtime router。

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
