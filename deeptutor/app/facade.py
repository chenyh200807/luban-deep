"""Stable application-layer facade for DeepTutor entry points."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import importlib.util
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, AsyncIterator

from deeptutor.contracts import export_unified_turn_contract, load_contract_index
from deeptutor.runtime.registry.capability_registry import get_capability_registry
from deeptutor.services.notebook import RecordType, get_notebook_manager
from deeptutor.services.session import get_sqlite_session_store, get_turn_runtime_manager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TurnRequest:
    """Stable turn payload used by adapters such as the CLI package."""

    content: str
    capability: str = "chat"
    session_id: str | None = None
    tools: list[str] = field(default_factory=list)
    knowledge_bases: list[str] = field(default_factory=list)
    language: str = "en"
    config: dict[str, Any] = field(default_factory=dict)
    notebook_references: list[dict[str, Any]] = field(default_factory=list)
    history_references: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "capability": self.capability,
            "session_id": self.session_id,
            "tools": list(self.tools),
            "knowledge_bases": list(self.knowledge_bases),
            "language": self.language,
            "config": dict(self.config),
            "notebook_references": list(self.notebook_references),
            "history_references": list(self.history_references),
            "attachments": list(self.attachments),
        }


@dataclass(slots=True)
class CapabilityAvailability:
    """Availability result for optional capabilities."""

    name: str
    available: bool
    install_hint: str = ""


@dataclass(slots=True)
class ContractSelfCheck:
    ok: bool
    entrypoint: str = ""
    domains: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    transport: str = ""


class DeepTutorApp:
    """Facade around runtime, session, notebook, and capability contracts."""

    def __init__(self) -> None:
        self.runtime = get_turn_runtime_manager()
        self.store = get_sqlite_session_store()
        self.notebooks = get_notebook_manager()
        self.capabilities = get_capability_registry()
        self.contract_self_check = self.verify_contract_alignment()
        strict_contract_check = os.getenv("DEEPTUTOR_STRICT_CONTRACT_CHECK", "").strip().lower()
        strict_enabled = strict_contract_check in {"1", "true", "yes", "on"}
        if not self.contract_self_check.ok:
            message = (
                "DeepTutor contract self-check failed: "
                + "; ".join(self.contract_self_check.errors)
            )
            if strict_enabled:
                raise RuntimeError(message)
            logger.warning(message)

    def resolve_capability(self, value: str | None) -> str:
        requested = str(value or "chat").strip() or "chat"
        manifests = self.capabilities.get_manifests()
        for manifest in manifests:
            if manifest["name"] == requested:
                return requested
            aliases = {str(alias).strip() for alias in manifest.get("cli_aliases", [])}
            if requested in aliases:
                return str(manifest["name"])
        available = ", ".join(sorted(manifest["name"] for manifest in manifests))
        raise ValueError(f"Unknown capability `{requested}`. Available: {available}")

    def get_capability_contracts(self) -> list[dict[str, Any]]:
        contracts = []
        for manifest in self.capabilities.get_manifests():
            contracts.append(
                {
                    **manifest,
                    "availability": self.get_capability_availability(manifest["name"]).__dict__,
                }
            )
        return contracts

    def get_capability_contract(self, value: str) -> dict[str, Any]:
        resolved = self.resolve_capability(value)
        for manifest in self.capabilities.get_manifests():
            if manifest["name"] == resolved:
                return {
                    **manifest,
                    "availability": self.get_capability_availability(resolved).__dict__,
                }
        raise ValueError(f"Capability not found: {resolved}")

    def get_capability_availability(self, capability: str) -> CapabilityAvailability:
        resolved = self.resolve_capability(capability)
        if resolved == "math_animator":
            available = importlib.util.find_spec("manim") is not None
            return CapabilityAvailability(
                name=resolved,
                available=available,
                install_hint=(
                    ""
                    if available
                    else "Install with `pip install deeptutor-cli[math-animator]` "
                    "or `pip install -r requirements/math-animator.txt`."
                ),
            )
        return CapabilityAvailability(name=resolved, available=True)

    def verify_contract_alignment(self) -> ContractSelfCheck:
        errors: list[str] = []
        entrypoint = ""
        domains: list[str] = []
        try:
            contract_index = load_contract_index()
        except Exception as exc:
            return ContractSelfCheck(ok=False, errors=[f"failed to load contracts/index.yaml: {exc}"])

        entrypoint = str(contract_index.get("entrypoint", "") or "").strip()
        domain_payload = contract_index.get("domains")
        if not isinstance(domain_payload, dict):
            errors.append("contracts/index.yaml missing `domains` object")
            domain_payload = {}
        domains = sorted(str(name) for name in domain_payload)
        required_domains = {"turn", "capability", "rag", "config_runtime"}
        missing_domains = sorted(required_domains.difference(domain_payload))
        if missing_domains:
            errors.append(f"contracts/index.yaml missing domains: {', '.join(missing_domains)}")
        if entrypoint != "CONTRACT.md":
            errors.append(f"unexpected contract entrypoint: {entrypoint or '(empty)'}")

        turn_contract = export_unified_turn_contract()
        transport = str(
            (turn_contract.get("transport") or {}).get("primary_websocket", "") or ""
        ).strip()
        if transport != "/api/v1/ws":
            errors.append(f"unexpected unified websocket endpoint: {transport or '(empty)'}")
        schemas = turn_contract.get("schemas") or {}
        if "start_turn_message" not in schemas:
            errors.append("turn contract missing `start_turn_message` schema")
        if "turn_start_response" not in schemas:
            errors.append("turn contract missing `turn_start_response` schema")
        trace_fields = set(turn_contract.get("trace_fields") or [])
        for field_name in ("session_id", "turn_id", "capability", "bot_id"):
            if field_name not in trace_fields:
                errors.append(f"turn contract missing trace field `{field_name}`")

        return ContractSelfCheck(
            ok=not errors,
            entrypoint=entrypoint,
            domains=domains,
            errors=errors,
            transport=transport,
        )

    async def start_turn(self, request: TurnRequest | dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if isinstance(request, dict):
            request = TurnRequest(**request)
        resolved_capability = self.resolve_capability(request.capability)
        session, turn = await self.runtime.start_turn(
            {
                **request.to_payload(),
                "capability": resolved_capability,
            }
        )
        await self.store.update_session_preferences(
            session["id"],
            {
                "language": request.language,
                "notebook_references": request.notebook_references,
                "history_references": request.history_references,
            },
        )
        return session, turn

    async def stream_turn(self, turn_id: str, after_seq: int = 0) -> AsyncIterator[dict[str, Any]]:
        async for item in self.runtime.subscribe_turn(turn_id, after_seq=after_seq):
            yield item

    async def cancel_turn(self, turn_id: str) -> bool:
        return await self.runtime.cancel_turn(turn_id)

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return await self.store.list_sessions(limit=limit, offset=offset)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return await self.store.get_session_with_messages(session_id)

    async def rename_session(self, session_id: str, title: str) -> bool:
        return await self.store.update_session_title(session_id, title)

    async def delete_session(self, session_id: str) -> bool:
        return await self.store.delete_session(session_id)

    async def get_active_turn(self, session_id: str) -> dict[str, Any] | None:
        return await self.store.get_active_turn(session_id)

    def list_notebooks(self) -> list[dict[str, Any]]:
        return self.notebooks.list_notebooks()

    def create_notebook(
        self,
        name: str,
        description: str = "",
        *,
        color: str = "#3B82F6",
        icon: str = "book",
    ) -> dict[str, Any]:
        return self.notebooks.create_notebook(
            name=name,
            description=description,
            color=color,
            icon=icon,
        )

    def get_notebook(self, notebook_id: str) -> dict[str, Any] | None:
        return self.notebooks.get_notebook(notebook_id)

    def add_record(self, **kwargs: Any) -> dict[str, Any]:
        return self.notebooks.add_record(**kwargs)

    def update_record(self, notebook_id: str, record_id: str, **kwargs: Any) -> dict[str, Any] | None:
        return self.notebooks.update_record(notebook_id, record_id, **kwargs)

    def remove_record(self, notebook_id: str, record_id: str) -> bool:
        return self.notebooks.remove_record(notebook_id, record_id)

    def get_records_by_references(self, notebook_references: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.notebooks.get_records_by_references(notebook_references)

    def import_markdown_into_notebook(self, notebook_id: str, path: str | Path) -> dict[str, Any]:
        resolved_path = Path(path).expanduser().resolve()
        if not resolved_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {resolved_path}")
        content = resolved_path.read_text(encoding="utf-8")
        title = _extract_markdown_title(content, fallback=resolved_path.stem)
        now = time.time()
        metadata = {
            "source": "co_writer",
            "saved_via": "cli",
            "source_path": str(resolved_path),
            "source_hash": sha256(content.encode("utf-8")).hexdigest(),
            "imported_at": now,
        }
        return self.notebooks.add_record(
            notebook_ids=[notebook_id],
            record_type=RecordType.CO_WRITER,
            title=title,
            summary="",
            user_query=title,
            output=content,
            metadata=metadata,
            kb_name=None,
        )

    def replace_markdown_record(
        self,
        notebook_id: str,
        record_id: str,
        path: str | Path,
    ) -> dict[str, Any]:
        resolved_path = Path(path).expanduser().resolve()
        if not resolved_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {resolved_path}")
        existing = self.notebooks.get_record(notebook_id, record_id)
        if existing is None:
            raise ValueError(f"Record not found: {record_id}")
        if str(existing.get("type", "")) != RecordType.CO_WRITER.value:
            raise ValueError("Only `co_writer` notebook records can be replaced from markdown.")

        content = resolved_path.read_text(encoding="utf-8")
        title = _extract_markdown_title(content, fallback=resolved_path.stem)
        metadata = {
            "source": "co_writer",
            "saved_via": "cli",
            "source_path": str(resolved_path),
            "source_hash": sha256(content.encode("utf-8")).hexdigest(),
            "replaced_at": time.time(),
        }
        updated = self.notebooks.update_record(
            notebook_id,
            record_id,
            title=title,
            user_query=title,
            output=content,
            metadata=metadata,
            kb_name=None,
        )
        if updated is None:
            raise ValueError(f"Failed to update record: {record_id}")
        return updated


def _extract_markdown_title(content: str, *, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return fallback.strip() or "Untitled"


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
