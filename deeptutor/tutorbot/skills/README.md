# nanobot Skills

This directory contains built-in skills that extend nanobot's capabilities.

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
| `construction-mcq-grading` | Grade and diagnose 建筑实务 single-choice and multi-choice answers |
| `construction-case-grading` | Grade and diagnose 建筑实务 case-study written answers |
| `construction-question-supply` | Practice question supply: public stems only, hidden grading key preserved server-side |
| `construction-question-review` | Question-level explanation (pre- or post-submission); rebuild stem first, conclusion after |
| `construction-learning-evidence-story` | Learner state narration over read-model evidence_refs (presentation-only) |
| `construction-study-assistant` | One concrete next-step suggestion from training_intent / study_plan (presentation-only) |
| `construction-learning-support` | Emotional acknowledgement when learners feel stuck; no diagnosis, no grading authority |

The seven `construction-*` skills above are scene-specific lifecycle skills consumed by `deep_question`,
`question_followup`, `construction_grading`, and the TutorBot loop through the shared
`deeptutor.services.question_lifecycle_skills` builder. Scene is decided **only** by `ChatOrchestrator`;
downstream readers consume `UnifiedContext.question_lifecycle_scene` without re-detecting.
