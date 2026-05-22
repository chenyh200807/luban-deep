#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import os


_DEV_SECRET = "dev-attempt-ref-secret"
_REQUIRED_PROD_SECRETS = ("DEEPTUTOR_ATTEMPT_REF_SECRET",)


def _fingerprint(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


def validate_secret_envs(env_name: str, environ: dict[str, str] | None = None) -> tuple[bool, list[str]]:
    env = environ if environ is not None else dict(os.environ)
    normalized_env = env_name.strip().lower()
    messages: list[str] = []

    if normalized_env in {"prod", "production"}:
        for name in _REQUIRED_PROD_SECRETS:
            value = env.get(name, "").strip()
            if not value:
                messages.append(f"{name}=missing")
                continue
            if value == _DEV_SECRET:
                messages.append(f"{name}=dev-secret-forbidden")
                continue
            if len(value) < 32:
                messages.append(f"{name}=too-short")
                continue
            messages.append(f"{name}=set fingerprint={_fingerprint(value)}")
        ok = all("=set fingerprint=" in item for item in messages)
        return ok, messages

    for name in _REQUIRED_PROD_SECRETS:
        value = env.get(name, "").strip()
        if value:
            messages.append(f"{name}=set fingerprint={_fingerprint(value)}")
        else:
            messages.append(f"{name}=not-required-for-{normalized_env or 'local'}")
    return True, messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate fail-closed production secret envs.")
    parser.add_argument("--env", default=os.getenv("DEEPTUTOR_ENV", "local"), help="local, staging, prod, or production")
    args = parser.parse_args(argv)

    ok, messages = validate_secret_envs(args.env)
    for message in messages:
        print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
