# Real Package UI Probe - 2026-06-06

- entry_surface: real_wechat_package
- trace_source: miniprogram_automator_ui_input_tap
- auth_state: qa_token
- auth_mode: local_dev_wechat
- pass: true
- conversation_id: unified_1780761414232_748a1e1e
- turn_id: turn_1780761414235_edd7b777f4
- trace_id: c92f31e9a0d0674814f6ebfdc19f3560
- execution_path: tutorbot_exact_fast_path
- question_id: historical:cf366dd4c395fffa
- official_answer: A
- Langfuse observations: `turn.runtime`, `learner_state.refresh`, `llm.stream`, `tutorbot.runtime`, `rag.kbv5.search`
- LLM: `deepseek-v4-flash`, usage `input=1543`, `output=167`, `total=1710`

Boundary: this uses the real package UI textarea and send button in DevTools, but still uses local backend plus dev WeChat token. It is closer to normal user operation than direct page _send, but still not true device/production login.
