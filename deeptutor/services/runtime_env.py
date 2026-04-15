from __future__ import annotations

import os

_RUNTIME_ENV_KEYS = (
    "DEEPTUTOR_ENV",
    "APP_ENV",
    "ENV",
    "ENVIRONMENT",
    "SERVICE_ENV",
)
_PRODUCTION_ENV_NAMES = {"prod", "production"}
_TRUTHY_VALUES = {"1", "true", "yes", "on"}
_FALSY_VALUES = {"0", "false", "no", "off"}


def runtime_environment(*, default: str = "local") -> str:
    for key in _RUNTIME_ENV_KEYS:
        value = str(os.getenv(key) or "").strip().lower()
        if value:
            return value
    return default


def is_production_environment() -> bool:
    return runtime_environment() in _PRODUCTION_ENV_NAMES


def env_flag(name: str, *, default: bool = False) -> bool:
    raw = str(os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in _TRUTHY_VALUES:
        return True
    if raw in _FALSY_VALUES:
        return False
    return default
