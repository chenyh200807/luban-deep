# DeepTutor Agent Skills

These skills capture repeatable developer-agent workflows for DeepTutor.
They are not TutorBot runtime skills and must not be loaded by the product
skill loader under `deeptutor/tutorbot/skills/`.

Use them when planning, debugging, reviewing, or QA'ing DeepTutor work:

- `deeptutor-authority-debugging`: root-cause workflow for authority, state,
  route, follow-up, refusal, and terminal-truth bugs.
- `wechat-tutorbot-real-entry-qa`: QA workflow for the real WeChat TutorBot
  path, with explicit evidence-surface boundaries.
- `compiled-knowledge-shadow-eval`: QA and rollout workflow for Nexus-like
  RAG+compiled TutorBot knowledge conversations, source pollution feedback,
  and system-wide default decisions.
- `anti-overfit-repair-review`: review workflow for regex, fallback,
  classifier, and special-case repairs.

Keep `AGENTS.md` as the hard-gate index. Put long procedures and reusable
checklists here so project entry files stay thin.
