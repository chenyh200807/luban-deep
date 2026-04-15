from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from deeptutor.contracts.bot_runtime_defaults import iter_bot_runtime_defaults
from deeptutor.logging import get_logger
from deeptutor.services.rag.factory import (
    DEFAULT_PROVIDER,
    LEGACY_PROVIDER_ALIASES,
    normalize_provider_name,
)
from deeptutor.services.path_service import get_path_service

logger = get_logger("KBConfigService")

DEFAULT_CONFIG_PATH = get_path_service().project_root / "data" / "knowledge_bases" / "kb_config.json"


def _default_payload() -> dict[str, Any]:
    return {
        "defaults": {
            "default_kb": None,
            "rag_provider": DEFAULT_PROVIDER,
            "search_mode": "hybrid",
        },
        "knowledge_bases": {},
    }


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str = "") -> list[str]:
    raw = str(os.getenv(name, default) or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _collect_supabase_aliases() -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for defaults in iter_bot_runtime_defaults():
        for alias in defaults.supabase_kb_aliases:
            normalized = str(alias or "").strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            aliases.append(normalized)
    for alias in _env_csv("SUPABASE_RAG_KB_ALIASES", ""):
        lowered = alias.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        aliases.append(alias)
    return aliases


def get_env_defined_kbs() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Return env-backed KB entries plus default overrides.

    This keeps a read-only remote KB available even when no local KB directory exists.
    """
    if not _env_flag("SUPABASE_RAG_ENABLED", default=False):
        return {}, {}

    supabase_url = str(os.getenv("SUPABASE_URL", "") or "").strip()
    service_key = (
        str(os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
        or str(os.getenv("SUPABASE_KEY", "") or "").strip()
    )
    if not supabase_url or not service_key:
        return {}, {}

    kb_name = str(os.getenv("SUPABASE_RAG_DEFAULT_KB_NAME", "") or "").strip() or "supabase-main"
    description = (
        str(os.getenv("SUPABASE_RAG_DEFAULT_DESCRIPTION", "") or "").strip()
        or "Primary read-only knowledge base hosted in Supabase"
    )
    sources = _env_csv("SUPABASE_RAG_SOURCES", "standard,textbook,exam")
    include_questions = _env_flag("SUPABASE_RAG_INCLUDE_QUESTIONS", default=True)
    aliases = _collect_supabase_aliases()

    def _build_entry(name: str, *, force_provider: bool) -> dict[str, Any]:
        return {
            "path": name,
            "description": description if name == kb_name else f"{description} (alias: {name})",
            "rag_provider": "supabase",
            "status": "ready",
            "remote_backend": "supabase",
            "remote_read_only": True,
            "supabase_sources": sources,
            "supabase_include_questions": include_questions,
            "supabase_force_provider": force_provider,
            "supabase_remote_kb": kb_name,
        }

    entries = {kb_name: _build_entry(kb_name, force_provider=False)}
    for alias in aliases:
        if alias and alias not in entries:
            entries[alias] = _build_entry(alias, force_provider=True)

    defaults = {"default_kb": kb_name}
    return entries, defaults


class KnowledgeBaseConfigService:
    _instance: "KnowledgeBaseConfigService | None" = None

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._config = self._load_config()

    @classmethod
    def get_instance(cls, config_path: Path | None = None) -> "KnowledgeBaseConfigService":
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance

    def _load_config(self) -> dict[str, Any]:
        payload = _default_payload()
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as handle:
                    loaded = json.load(handle) or {}
                payload.update({k: v for k, v in loaded.items() if k != "defaults"})
                payload["defaults"].update(loaded.get("defaults", {}))
            except Exception as exc:
                logger.warning("Failed to load KB config: %s", exc)

        env_kbs, env_defaults = get_env_defined_kbs()
        knowledge_bases = payload.setdefault("knowledge_bases", {})
        for kb_name, entry in env_kbs.items():
            current = knowledge_bases.setdefault(kb_name, {})
            force_provider = bool(entry.get("supabase_force_provider"))
            for key, value in entry.items():
                if force_provider and key in {
                    "rag_provider",
                    "remote_backend",
                    "remote_read_only",
                    "supabase_sources",
                    "supabase_include_questions",
                    "supabase_force_provider",
                    "supabase_remote_kb",
                    "status",
                }:
                    current[key] = value
                else:
                    current.setdefault(key, value)
        payload.setdefault("defaults", _default_payload()["defaults"])
        for key, value in env_defaults.items():
            if not payload["defaults"].get(key):
                payload["defaults"][key] = value

        payload.setdefault("knowledge_bases", {})
        payload.setdefault("defaults", _default_payload()["defaults"])
        payload = self._normalize_payload(payload)
        return payload

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        defaults = payload.setdefault("defaults", _default_payload()["defaults"])
        defaults["rag_provider"] = normalize_provider_name(defaults.get("rag_provider"))

        knowledge_bases = payload.setdefault("knowledge_bases", {})
        kb_base_dir = self.config_path.parent
        for kb_name, config in knowledge_bases.items():
            if not isinstance(config, dict):
                continue

            raw_provider = config.get("rag_provider")
            normalized = normalize_provider_name(raw_provider or defaults["rag_provider"])
            config["rag_provider"] = normalized

            if isinstance(raw_provider, str) and raw_provider.strip().lower() in LEGACY_PROVIDER_ALIASES:
                config["needs_reindex"] = True

            kb_dir = kb_base_dir / kb_name
            legacy_storage = kb_dir / "rag_storage"
            new_storage = kb_dir / "llamaindex_storage"
            if legacy_storage.exists() and legacy_storage.is_dir() and not (new_storage.exists() and new_storage.is_dir()):
                config["needs_reindex"] = True

        return payload

    def _save(self) -> None:
        self._config = self._normalize_payload(self._config)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(self._config, handle, indent=2, ensure_ascii=False)

    def _ensure_kb(self, kb_name: str) -> dict[str, Any]:
        knowledge_bases = self._config.setdefault("knowledge_bases", {})
        if kb_name not in knowledge_bases:
            knowledge_bases[kb_name] = {
                "path": kb_name,
                "description": f"Knowledge base: {kb_name}",
            }
        return knowledge_bases[kb_name]

    def get_kb_config(self, kb_name: str) -> dict[str, Any]:
        defaults = dict(self._config.get("defaults", {}))
        kb_config = dict(self._config.get("knowledge_bases", {}).get(kb_name, {}))
        merged = {
            "default_kb": defaults.get("default_kb"),
            "rag_provider": normalize_provider_name(
                kb_config.get("rag_provider") or defaults.get("rag_provider", DEFAULT_PROVIDER)
            ),
            "search_mode": kb_config.get("search_mode") or defaults.get("search_mode", "hybrid"),
            "needs_reindex": bool(kb_config.get("needs_reindex", False)),
            **kb_config,
        }
        return merged

    def set_kb_config(self, kb_name: str, config: dict[str, Any]) -> None:
        entry = self._ensure_kb(kb_name)
        entry.update(config)
        self._save()

    def get_rag_provider(self, kb_name: str) -> str:
        return str(self.get_kb_config(kb_name).get("rag_provider", DEFAULT_PROVIDER))

    def set_rag_provider(self, kb_name: str, provider: str) -> None:
        self.set_kb_config(
            kb_name,
            {
                "rag_provider": normalize_provider_name(provider),
            },
        )

    def get_search_mode(self, kb_name: str) -> str:
        return str(self.get_kb_config(kb_name).get("search_mode", "hybrid"))

    def set_search_mode(self, kb_name: str, mode: str) -> None:
        self.set_kb_config(kb_name, {"search_mode": mode})

    def delete_kb_config(self, kb_name: str) -> None:
        knowledge_bases = self._config.get("knowledge_bases", {})
        if kb_name in knowledge_bases:
            del knowledge_bases[kb_name]
            self._save()

    def get_all_configs(self) -> dict[str, Any]:
        return self._config

    def set_global_defaults(self, defaults: dict[str, Any]) -> None:
        current = self._config.setdefault("defaults", _default_payload()["defaults"])
        current.update(defaults)
        self._save()

    def set_default_kb(self, kb_name: str | None) -> None:
        self._config.setdefault("defaults", _default_payload()["defaults"])["default_kb"] = kb_name
        self._save()

    def get_default_kb(self) -> str | None:
        return self._config.get("defaults", {}).get("default_kb")

    def sync_from_metadata(self, kb_name: str, kb_base_dir: Path) -> None:
        metadata_file = kb_base_dir / kb_name / "metadata.json"
        if not metadata_file.exists():
            return
        try:
            with open(metadata_file, "r", encoding="utf-8") as handle:
                metadata = json.load(handle)
        except Exception as exc:
            logger.warning("Failed to load KB metadata for %s: %s", kb_name, exc)
            return
        config: dict[str, Any] = {}
        if metadata.get("rag_provider"):
            raw_provider = metadata["rag_provider"]
            config["rag_provider"] = normalize_provider_name(raw_provider)
            if str(raw_provider).strip().lower() in LEGACY_PROVIDER_ALIASES:
                config["needs_reindex"] = True
        if metadata.get("search_mode"):
            config["search_mode"] = metadata["search_mode"]
        if config:
            self.set_kb_config(kb_name, config)

    def sync_all_from_metadata(self, kb_base_dir: Path) -> None:
        if not kb_base_dir.exists():
            return
        for kb_dir in kb_base_dir.iterdir():
            if kb_dir.is_dir() and not kb_dir.name.startswith("."):
                self.sync_from_metadata(kb_dir.name, kb_base_dir)


def get_kb_config_service() -> KnowledgeBaseConfigService:
    return KnowledgeBaseConfigService.get_instance()


__all__ = [
    "KnowledgeBaseConfigService",
    "get_env_defined_kbs",
    "get_kb_config_service",
]
