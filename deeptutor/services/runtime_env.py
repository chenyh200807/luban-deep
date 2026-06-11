from __future__ import annotations

_RUNTIME_ENV_KEYS = (
    "DEEPTUTOR_ENV",
    "DEEPTUTOR_RUNTIME_ENV",
    "APP_ENV",
    "ENV",
    "ENVIRONMENT",
    "SERVICE_ENV",
)
_PRODUCTION_ENV_NAMES = {"prod", "production", "aliyun"}
# Fail-closed allowlist: ONLY an explicit declaration in this set disables
# production safeguards (dev login, demo tokens, fallback signing secrets,
# legacy routers). Anything else — unset, misspelled, "staging", unknown — is
# treated as production so dangerous dev-only capabilities never default to
# "open". This makes "authorized for dev capabilities" a single, explicit,
# fail-closed authority instead of the inverse of a fuzzy production guess.
_NON_PRODUCTION_ENV_NAMES = {
    "local",
    "dev",
    "development",
    "test",
    "testing",
    "ci",
    "eval",
}
_TRUTHY_VALUES = {"1", "true", "yes", "on"}
_FALSY_VALUES = {"0", "false", "no", "off"}


def runtime_environment(*, default: str = "local") -> str:
    from deeptutor.services.config.env_store import get_env_store

    env_store = get_env_store()
    for key in _RUNTIME_ENV_KEYS:
        value = str(env_store.get(key, "") or "").strip().lower()
        if value:
            return value
    return default


def is_production_environment() -> bool:
    # Fail-closed: production unless the environment is explicitly declared as a
    # known non-production environment. Unset / misspelled / unknown values
    # resolve to production so safeguards never silently disable themselves.
    return runtime_environment(default="") not in _NON_PRODUCTION_ENV_NAMES


def env_flag(name: str, *, default: bool = False) -> bool:
    from deeptutor.services.config.env_store import get_env_store

    raw = str(get_env_store().get(name, "") or "").strip().lower()
    if not raw:
        return default
    if raw in _TRUTHY_VALUES:
        return True
    if raw in _FALSY_VALUES:
        return False
    return default
