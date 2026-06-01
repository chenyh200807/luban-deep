from __future__ import annotations

from deeptutor.services.runtime_env import env_flag


ANSWER_CITATIONS_FLAG = "DEEPTUTOR_ANSWER_CITATIONS_ENABLED"


def answer_citations_enabled() -> bool:
    return env_flag(ANSWER_CITATIONS_FLAG, default=False)
