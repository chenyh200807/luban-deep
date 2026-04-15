"""Adapter tools that expose DeepTutor capabilities as TutorBot function-calling tools."""

from __future__ import annotations

from typing import Any

from deeptutor.tutorbot.agent.tools.base import Tool


class BrainstormAdapterTool(Tool):
    @property
    def name(self) -> str:
        return "brainstorm"

    @property
    def description(self) -> str:
        return "Broadly explore multiple possibilities for a topic and give a short rationale for each."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic, goal, or problem to brainstorm about.",
                },
                "context": {
                    "type": "string",
                    "description": "Optional supporting context, constraints, or background.",
                },
            },
            "required": ["topic"],
        }

    async def execute(self, **kwargs: Any) -> str:
        from deeptutor.tools.brainstorm import brainstorm

        result = await brainstorm(
            topic=kwargs.get("topic", ""),
            context=kwargs.get("context", ""),
        )
        return result.get("answer", "")


class RAGAdapterTool(Tool):
    def __init__(self) -> None:
        self._runtime_context: dict[str, Any] = {}
        self._last_trace_metadata: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "rag"

    @property
    def description(self) -> str:
        return (
            "Search a knowledge base using Retrieval-Augmented Generation. "
            "Returns relevant passages and an LLM-synthesised answer."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "kb_name": {
                    "type": "string",
                    "description": "Knowledge base to search.",
                },
                "mode": {
                    "type": "string",
                    "description": "Search mode.",
                    "enum": ["naive", "local", "global", "hybrid"],
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        from deeptutor.tools.rag_tool import rag_search

        kb_name = self._normalize_requested_kb(str(kwargs.get("kb_name") or "").strip()) or self._resolve_default_kb()
        result = await rag_search(
            query=kwargs.get("query", ""),
            kb_name=kb_name or None,
        )
        exact_question = result.get("exact_question") if isinstance(result.get("exact_question"), dict) else None
        sources = result.get("sources") if isinstance(result.get("sources"), list) else []
        self._last_trace_metadata = {
            "kb_name": kb_name or "",
            "sources": sources[:8],
            "tool_source_count": len(sources),
            "exact_question": exact_question or {},
            "authority_applied": False,
        }
        return result.get("answer") or result.get("content", "")

    def set_runtime_context(self, **kwargs: Any) -> None:
        metadata = kwargs.get("metadata")
        self._runtime_context = dict(metadata) if isinstance(metadata, dict) else {}

    def preview_args(self, params: dict[str, Any]) -> dict[str, Any]:
        preview = dict(params or {})
        normalized = self._normalize_requested_kb(str(preview.get("kb_name") or "").strip()) or self._resolve_default_kb()
        if normalized:
            preview["kb_name"] = normalized
        return preview

    def consume_trace_metadata(self) -> dict[str, Any] | None:
        metadata = dict(self._last_trace_metadata)
        self._last_trace_metadata = {}
        return metadata or None

    def _resolve_default_kb(self) -> str:
        metadata = self._runtime_context
        direct = str(metadata.get("default_kb") or "").strip()
        if direct:
            return direct
        for key in ("knowledge_bases", "default_knowledge_bases"):
            values = metadata.get(key)
            if isinstance(values, list):
                for item in values:
                    normalized = str(item or "").strip()
                    if normalized:
                        return normalized
        return ""

    def _normalize_requested_kb(self, requested: str) -> str:
        normalized = str(requested or "").strip()
        if not normalized:
            return ""
        default_kb = self._resolve_default_kb()
        if not default_kb:
            return normalized
        aliases = self._runtime_context.get("kb_aliases")
        alias_set = {
            str(item or "").strip().lower()
            for item in (aliases if isinstance(aliases, list) else [])
            if str(item or "").strip()
        }
        if normalized.strip().lower() in alias_set:
            return default_kb
        return normalized


class CodeExecutionAdapterTool(Tool):
    _CODEGEN_SYSTEM_PROMPT = (
        "You are a Python code generator.\n"
        "Convert the user's natural-language request into executable Python code only.\n"
        "Rules:\n"
        "- Output only Python code, with no markdown fences or explanation.\n"
        "- Prefer standard library plus common packages: math, numpy, pandas, matplotlib, scipy, sympy.\n"
        "- Print the final answer to stdout.\n"
        "- Keep the code focused on the requested computation."
    )

    @property
    def name(self) -> str:
        return "code_execution"

    @property
    def description(self) -> str:
        return (
            "Turn a natural-language computation request into Python, "
            "run it in a sandboxed worker, and return the result."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "Natural-language description of the computation or verification task.",
                },
                "code": {
                    "type": "string",
                    "description": "Optional raw Python code to execute directly.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max execution time in seconds.",
                },
            },
            "required": ["intent"],
        }

    async def execute(self, **kwargs: Any) -> str:
        from deeptutor.tools.code_executor import run_code

        code = str(kwargs.get("code") or "").strip()
        intent = str(kwargs.get("intent") or "").strip()
        timeout = int(kwargs.get("timeout", 30) or 30)

        if not code:
            if not intent:
                return "Error: code_execution requires either 'intent' or 'code'."
            code = await self._generate_code(intent)

        result = await run_code(language="python", code=code, timeout=timeout)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", 1)

        parts: list[str] = []
        if stdout:
            parts.append(stdout.strip())
        if stderr:
            label = "Error" if exit_code else "Stderr"
            parts.append(f"{label}:\n{stderr.strip()}")
        return "\n\n".join(parts) if parts else "Execution completed with no output."

    async def _generate_code(self, intent: str) -> str:
        from deeptutor.services.llm import complete, get_token_limit_kwargs
        from deeptutor.services.llm.config import get_llm_config

        cfg = get_llm_config()
        extra: dict[str, Any] = {"temperature": 0.0}
        if cfg.model:
            extra.update(get_token_limit_kwargs(cfg.model, 1200))

        response = await complete(
            prompt=intent,
            system_prompt=self._CODEGEN_SYSTEM_PROMPT,
            model=cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            api_version=getattr(cfg, "api_version", None),
            binding=getattr(cfg, "binding", None),
            **extra,
        )
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        if not cleaned:
            raise ValueError("LLM returned empty code for code_execution")
        return cleaned


class ReasonAdapterTool(Tool):
    @property
    def name(self) -> str:
        return "reason"

    @property
    def description(self) -> str:
        return (
            "Perform deep reasoning on a complex sub-problem using a dedicated LLM call. "
            "Use when the current context is insufficient for a confident answer."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The sub-problem to reason about.",
                },
                "context": {
                    "type": "string",
                    "description": "Supporting context for reasoning.",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        from deeptutor.tools.reason import reason

        result = await reason(
            query=kwargs.get("query", ""),
            context=kwargs.get("context", ""),
        )
        return result.get("answer", "")


class PaperSearchAdapterTool(Tool):
    @property
    def name(self) -> str:
        return "paper_search"

    @property
    def description(self) -> str:
        return "Search arXiv preprints by keyword and return concise metadata."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum papers to return.",
                },
                "years_limit": {
                    "type": "integer",
                    "description": "Only include preprints from the last N years.",
                },
                "sort_by": {
                    "type": "string",
                    "description": "Sort by relevance or submission date.",
                    "enum": ["relevance", "date"],
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        from deeptutor.tools.paper_search_tool import ArxivSearchTool

        papers = await ArxivSearchTool().search_papers(
            query=kwargs.get("query", ""),
            max_results=kwargs.get("max_results", 3),
            years_limit=kwargs.get("years_limit", 3),
            sort_by=kwargs.get("sort_by", "relevance"),
        )
        if not papers:
            return "No arXiv preprints found for this query."

        lines: list[str] = []
        for p in papers:
            lines.append(f"**{p['title']}** ({p.get('year', '?')})")
            lines.append(f"Authors: {', '.join(p.get('authors', []))}")
            lines.append(f"arXiv: {p.get('arxiv_id', '')}  URL: {p.get('url', '')}")
            lines.append(f"Abstract: {p.get('abstract', '')[:400]}")
            lines.append("")
        return "\n".join(lines)
