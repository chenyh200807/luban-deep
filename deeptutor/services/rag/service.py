"""Unified RAG service entry point."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

from deeptutor.logging import get_logger

from .factory import (
    DEFAULT_PROVIDER,
    get_pipeline,
    has_pipeline,
    list_pipelines,
    normalize_provider_name,
)
from .evidence_bundle import build_evidence_bundle
from .exceptions import RAGError, wrap_rag_error
from .provenance import build_ranking_trace
from .retrieval_plan import build_retrieval_plan
from .historical_questions import (
    build_canonical_question_context,
    build_historical_question_source,
    render_historical_question_context,
    resolve_historical_question,
)


class _RAGRawLogHandler(logging.Handler):
    def __init__(self, event_sink, loop) -> None:
        super().__init__(level=logging.DEBUG)
        self._event_sink = event_sink
        self._loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        if self._event_sink is None:
            return
        try:
            module_name = getattr(record, "module_name", record.name.split(".")[-1])
            level_name = getattr(record, "display_level", record.levelname)
            message = record.getMessage()
            line = f"[{module_name}] {level_name}: {message}".strip()
            if not line:
                return

            async def _emit() -> None:
                await self._event_sink(
                    "raw_log",
                    line,
                    {
                        "trace_layer": "raw",
                        "logger_name": record.name,
                        "log_level": level_name,
                        "module_name": module_name,
                    },
                )

            self._loop.create_task(_emit())
        except Exception:
            pass


DEFAULT_KB_BASE_DIR = str(
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "knowledge_bases"
)


class RAGService:
    """Unified RAG service that currently uses llamaindex provider(s)."""

    def __init__(
        self,
        kb_base_dir: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        self.logger = get_logger("RAGService")
        self.kb_base_dir = kb_base_dir or DEFAULT_KB_BASE_DIR
        from deeptutor.services.config import get_kb_config_service

        configured_default = (
            get_kb_config_service()
            .get_all_configs()
            .get("defaults", {})
            .get("rag_provider", DEFAULT_PROVIDER)
        )
        self.provider = normalize_provider_name(provider or configured_default)
        self._pipeline = None

    def _get_pipeline(self):
        if self._pipeline is None:
            self._pipeline = get_pipeline(self.provider, kb_base_dir=self.kb_base_dir)
        return self._pipeline

    async def initialize(
        self, kb_name: str, file_paths: List[str], **kwargs
    ) -> bool:
        self.logger.info(f"Initializing KB '{kb_name}' with provider '{self.provider}'")
        pipeline = self._get_pipeline()
        return await pipeline.initialize(
            kb_name=kb_name, file_paths=file_paths, **kwargs
        )

    async def search(
        self,
        query: str,
        kb_name: str,
        event_sink=None,
        **kwargs,
    ) -> Dict[str, Any]:
        kwargs.pop("mode", None)
        provider = self._get_provider_for_kb(kb_name)
        with self._capture_raw_logs(event_sink, provider):
            await self._emit_tool_event(
                event_sink,
                "status",
                f"Query: {query}",
                {"query": query, "kb_name": kb_name, "trace_layer": "summary"},
            )
            await self._emit_tool_event(
                event_sink,
                "status",
                f"Selecting provider: {provider}",
                {"provider": provider, "trace_layer": "summary"},
            )

            self.logger.info(
                f"Searching KB '{kb_name}' with provider '{provider}' and query: {query[:50]}..."
            )
            pipeline = get_pipeline(provider, kb_base_dir=self.kb_base_dir)

            await self._emit_tool_event(
                event_sink,
                "status",
                f"Retrieving from knowledge base '{kb_name}'...",
                {"provider": provider, "trace_layer": "summary"},
            )

            try:
                result = await pipeline.search(query=query, kb_name=kb_name, **kwargs)
            except RAGError as exc:
                historical_result = self._build_historical_question_result(
                    query=query,
                    kb_name=kb_name,
                    provider=provider,
                    search_kwargs=kwargs,
                    retrieval_error=exc,
                )
                if historical_result is not None:
                    return historical_result
                raise
            except Exception as exc:
                rag_error = wrap_rag_error(
                    exc,
                    provider=provider,
                    kb_name=kb_name,
                    query=query,
                    stage="service.search",
                )
                historical_result = self._build_historical_question_result(
                    query=query,
                    kb_name=kb_name,
                    provider=provider,
                    search_kwargs=kwargs,
                    retrieval_error=rag_error,
                )
                if historical_result is not None:
                    return historical_result
                raise rag_error from exc

            if not isinstance(result, dict):
                raise wrap_rag_error(
                    RuntimeError("Pipeline returned non-dict result"),
                    provider=provider,
                    kb_name=kb_name,
                    query=query,
                    stage="service.search",
                )

            if "query" not in result:
                result["query"] = query
            if "answer" not in result and "content" in result:
                result["answer"] = result["content"]
            if "content" not in result and "answer" in result:
                result["content"] = result["answer"]
            if "kb_name" not in result:
                result["kb_name"] = kb_name
            evidence_bundle = result.get("evidence_bundle")
            if not isinstance(evidence_bundle, dict):
                fallback_retrieval_plan = build_retrieval_plan(
                    query,
                    include_questions_default=bool(kwargs.get("include_questions", True)),
                    intent=str(kwargs.get("intent") or ""),
                    question_type=str(kwargs.get("question_type") or ""),
                    routing_metadata=(
                        kwargs.get("routing_metadata")
                        if isinstance(kwargs.get("routing_metadata"), dict)
                        else {}
                    ),
                )
                fallback_sources = list(result.get("sources") or [])
                evidence_bundle = build_evidence_bundle(
                    query=result["query"],
                    provider=result.get("provider") or provider,
                    kb_name=result["kb_name"],
                    content_blocks=[result.get("content") or result.get("answer") or ""],
                    sources=fallback_sources,
                    exact_question=(
                        result.get("exact_question")
                        if isinstance(result.get("exact_question"), dict)
                        else {}
                    ),
                    retrieval_plan=fallback_retrieval_plan.to_dict(),
                    ranking_trace=build_ranking_trace(fallback_sources),
                )
            result["evidence_bundle"] = evidence_bundle
            result["provider"] = normalize_provider_name(result.get("provider") or provider)
            self._apply_historical_question_context(result)

            answer = result.get("answer") or result.get("content") or ""
            await self._emit_tool_event(
                event_sink,
                "status",
                f"Retrieved {len(answer)} characters of grounded context.",
                {
                    "provider": result["provider"],
                    "kb_name": kb_name,
                    "trace_layer": "summary",
                },
            )

            return result

    async def _emit_tool_event(
        self,
        event_sink,
        event_type: str,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        if event_sink is None:
            return
        await event_sink(event_type, message, metadata or {})

    def _apply_historical_question_context(self, result: dict[str, Any]) -> None:
        if not isinstance(result, dict):
            return
        if isinstance(result.get("exact_question"), dict) and result.get("exact_question"):
            return
        evidence_bundle = result.get("evidence_bundle")
        if isinstance(evidence_bundle, dict):
            existing_exact = evidence_bundle.get("exact_question")
            if isinstance(existing_exact, dict) and existing_exact:
                result["exact_question"] = existing_exact
                return
        query = str(result.get("query") or "").strip()
        exact_question = resolve_historical_question(query)
        if not exact_question:
            return

        context = build_canonical_question_context(exact_question)
        rendered = render_historical_question_context(exact_question)
        source = build_historical_question_source(exact_question)
        result["exact_question"] = exact_question
        result["canonical_question_context"] = context
        sources = result.get("sources") if isinstance(result.get("sources"), list) else []
        if not sources:
            result["sources"] = [source]
        answer = str(result.get("answer") or result.get("content") or "").strip()
        if not answer or self._looks_like_empty_retrieval_answer(answer):
            result["answer"] = rendered
            result["content"] = rendered

        evidence_bundle = result.get("evidence_bundle")
        if not isinstance(evidence_bundle, dict):
            return
        evidence_bundle["exact_question"] = exact_question
        bundle_sources = evidence_bundle.get("sources")
        if not isinstance(bundle_sources, list) or not bundle_sources:
            evidence_bundle["sources"] = [source]
        content_blocks = evidence_bundle.get("content_blocks")
        if not isinstance(content_blocks, list) or not any(str(item or "").strip() for item in content_blocks):
            evidence_bundle["content_blocks"] = [rendered]
        evidence_bundle["retrieval_empty"] = False
        # historical-question diagnostics live in the canonical bundle's ``trace`` bucket
        bundle_trace = evidence_bundle.setdefault("trace", {})
        bundle_trace["canonical_question_context"] = context
        bundle_trace["historical_question_resolved"] = True

    def _build_historical_question_result(
        self,
        *,
        query: str,
        kb_name: str,
        provider: str,
        search_kwargs: dict[str, Any],
        retrieval_error: RAGError | None = None,
    ) -> dict[str, Any] | None:
        exact_question = resolve_historical_question(query)
        if not exact_question:
            return None
        context = build_canonical_question_context(exact_question)
        rendered = render_historical_question_context(exact_question)
        source = build_historical_question_source(exact_question)
        retrieval_plan = build_retrieval_plan(
            query,
            include_questions_default=bool(search_kwargs.get("include_questions", True)),
            intent=str(search_kwargs.get("intent") or ""),
            question_type=str(search_kwargs.get("question_type") or ""),
            routing_metadata=(
                search_kwargs.get("routing_metadata")
                if isinstance(search_kwargs.get("routing_metadata"), dict)
                else {}
            ),
        )
        status = "provider_failed_exact_question_resolved" if retrieval_error is not None else "ok"
        warning = (
            {
                "phase": "provider",
                "group_name": "historical_question_resolver",
                "query": query,
                "message": str(retrieval_error),
                "provider": str(getattr(retrieval_error, "provider", "") or provider),
                "stage": str(getattr(retrieval_error, "stage", "") or ""),
                "retryable": bool(getattr(retrieval_error, "retryable", False)),
            }
            if retrieval_error is not None
            else None
        )
        evidence_bundle = build_evidence_bundle(
            query=query,
            provider=provider,
            kb_name=kb_name,
            content_blocks=[rendered],
            sources=[source],
            exact_question=exact_question,
            retrieval_plan=retrieval_plan.to_dict(),
            ranking_trace=build_ranking_trace([source]),
            retrieval_warnings=[warning] if warning else [],
            retrieval_status=status,
            retrieval_empty=False,
            trace={
                "canonical_question_context": context,
                "historical_question_resolved": True,
                **({"warnings": [warning]} if warning else {}),
            },
        )
        payload: dict[str, Any] = {
            "query": query,
            "answer": rendered,
            "content": rendered,
            "sources": [source],
            "provider": provider,
            "kb_name": kb_name,
            "exact_question": exact_question,
            "canonical_question_context": context,
            "evidence_bundle": evidence_bundle,
            "retrieval_degraded": bool(retrieval_error),
            "retrieval_status": status,
        }
        if warning:
            payload["warnings"] = [warning]
        return payload

    @staticmethod
    def _looks_like_empty_retrieval_answer(value: str) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        return any(
            marker in text
            for marker in (
                "No documents indexed",
                "No relevant documents found",
                "Please upload documents first",
            )
        )

    def _capture_raw_logs(self, event_sink, provider: str):
        from contextlib import ExitStack, contextmanager
        import asyncio

        @contextmanager
        def _manager():
            if event_sink is None:
                yield
                return

            loop = asyncio.get_running_loop()
            handler = _RAGRawLogHandler(event_sink, loop)
            handler.setLevel(logging.DEBUG)
            targets = self._iter_rag_loggers(provider)
            with ExitStack() as stack:
                for logger in targets:
                    logger.addHandler(handler)
                    stack.callback(logger.removeHandler, handler)
                try:
                    yield
                finally:
                    handler.close()

        return _manager()

    def _iter_rag_loggers(self, provider: str) -> list[logging.Logger]:
        provider_name = normalize_provider_name(provider)
        names = {
            "deeptutor.RAGService",
            "deeptutor.RAGForward",
        }
        if provider_name == DEFAULT_PROVIDER:
            names.add("deeptutor.LlamaIndexPipeline")
        if provider_name == "supabase":
            names.add("deeptutor.SupabasePipeline")
        return [logging.getLogger(name) for name in sorted(names)]

    def _get_provider_for_kb(self, kb_name: str) -> str:
        """Resolve provider from KB config and normalize legacy values."""
        try:
            from deeptutor.services.config import get_kb_config_service

            service = get_kb_config_service()
            provider_raw = service.get_kb_config(kb_name).get("rag_provider")
            provider = normalize_provider_name(provider_raw)
            if provider_raw and provider_raw != provider:
                service.set_rag_provider(kb_name, provider)
                self.logger.info(
                    f"Normalized legacy provider '{provider_raw}' -> '{provider}' for KB '{kb_name}'"
                )
            return provider
        except Exception as e:
            self.logger.warning(f"Error reading provider from config: {e}, using instance provider")
            return self.provider

    async def delete(self, kb_name: str) -> bool:
        self.logger.info(f"Deleting KB '{kb_name}'")
        pipeline = self._get_pipeline()

        if hasattr(pipeline, "delete"):
            return await pipeline.delete(kb_name=kb_name)

        kb_dir = Path(self.kb_base_dir) / kb_name
        if kb_dir.exists():
            shutil.rmtree(kb_dir)
            self.logger.info(f"Deleted KB directory: {kb_dir}")
            return True
        return False

    async def smart_retrieve(
        self,
        context: str,
        kb_name: str,
        query_hints: Optional[List[str]] = None,
        max_queries: int = 3,
    ) -> Dict[str, Any]:
        import asyncio

        queries = query_hints if query_hints else await self._generate_queries(context, max_queries)

        tasks = [self.search(query=q, kb_name=kb_name) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        passages: list[str] = []
        all_sources: list[dict] = []
        for r in results:
            if isinstance(r, Exception):
                continue
            content = r.get("content") or r.get("answer") or ""
            if content:
                passages.append(content)
                all_sources.append({"query": r.get("query", ""), "provider": r.get("provider", "")})

        if not passages:
            return {"answer": "", "sources": []}

        aggregated = await self._aggregate(context, passages)
        return {"answer": aggregated, "sources": all_sources}

    async def _generate_queries(self, context: str, n: int) -> list[str]:
        try:
            from deeptutor.services.llm import complete

            prompt = (
                f"Generate {n} diverse search queries to retrieve information relevant "
                f"to the following context. Return ONLY the queries, one per line.\n\n"
                f"Context:\n{context[:2000]}"
            )
            raw = await complete(prompt, system_prompt="You are a search query generator.")
            lines = [l.strip().lstrip("0123456789.-) ") for l in raw.strip().split("\n") if l.strip()]
            return lines[:n] if lines else [context[:200]]
        except Exception:
            return [context[:200]]

    async def _aggregate(self, context: str, passages: list[str]) -> str:
        try:
            from deeptutor.services.llm import complete

            combined = "\n---\n".join(passages)
            prompt = (
                "Synthesise the following retrieved passages into a concise, "
                "relevant summary for the given context.\n\n"
                f"Context:\n{context[:1000]}\n\n"
                f"Passages:\n{combined[:6000]}"
            )
            return await complete(prompt, system_prompt="You are a knowledge synthesiser.")
        except Exception:
            return "\n\n".join(passages)

    @staticmethod
    def list_providers() -> List[Dict[str, str]]:
        return list_pipelines()

    @staticmethod
    def get_current_provider() -> str:
        return normalize_provider_name(os.getenv("RAG_PROVIDER", DEFAULT_PROVIDER))

    @staticmethod
    def has_provider(name: str) -> bool:
        return has_pipeline((name or "").strip().lower())
