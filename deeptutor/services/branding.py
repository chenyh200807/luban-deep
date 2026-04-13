"""Branding helpers for user-facing product naming."""

from __future__ import annotations

import os


DEFAULT_BRAND_NAME = "DeepTutor"


def get_brand_name() -> str:
    brand = str(os.getenv("APP_BRAND_NAME", "") or "").strip()
    return brand or DEFAULT_BRAND_NAME


def get_api_title() -> str:
    return f"{get_brand_name()} API"


def get_api_welcome_message() -> str:
    return f"Welcome to {get_brand_name()} API"


__all__ = [
    "DEFAULT_BRAND_NAME",
    "get_api_title",
    "get_api_welcome_message",
    "get_brand_name",
]
