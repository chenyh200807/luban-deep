"""Web tools: web_search and web_fetch."""

from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import os
import re
import socket
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from deeptutor.tutorbot.agent.tools.base import Tool

if TYPE_CHECKING:
    from deeptutor.tutorbot.config.schema import WebSearchConfig

# Shared constants
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5  # Limit redirects to prevent DoS attacks


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with valid domain."""
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


# RFC6598 shared address space (100.64.0.0/10). Aliyun's metadata service lives
# at 100.100.100.200 inside this range, and Python <3.13 marks it neither
# is_private nor is_global — so it is blocked here explicitly as a belt-and-
# suspenders backstop on top of the `not is_global` gate below.
_EXTRA_BLOCKED_NETS = (ipaddress.ip_network("100.64.0.0/10"),)


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True if the address is not a public, internet-routable target."""
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:  # normalise ::ffff:10.0.0.1 → 10.0.0.1
        ip = mapped
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or not ip.is_global
    ):
        return True
    return any(ip.version == net.version and ip in net for net in _EXTRA_BLOCKED_NETS)


def _resolve_host_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a host to every IP it maps to (literal IPs short-circuit DNS)."""
    literal = host.strip("[]")
    try:
        return [ipaddress.ip_address(literal)]
    except ValueError:
        pass
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def _assert_url_safe(url: str) -> tuple[bool, str]:
    """Reject http(s) URLs whose host resolves to any non-public address.

    Fail-closed SSRF guard for the LLM-facing web_fetch tool: validates scheme,
    resolves the hostname, and blocks loopback/link-local/private/reserved and
    cloud-metadata targets. DNS errors reject too. This is a point-in-time
    check; pinning the socket to the resolved IP (full DNS-rebinding defense)
    is tracked as a separate follow-up.
    """
    ok, err = _validate_url(url)
    if not ok:
        return False, err
    host = urlparse(url).hostname
    if not host:
        return False, "Missing host"
    try:
        ips = _resolve_host_ips(host)
    except Exception as exc:
        return False, f"Could not resolve host '{host}': {exc}"
    if not ips:
        return False, f"Host '{host}' did not resolve"
    for ip in ips:
        if _ip_is_blocked(ip):
            return False, f"Blocked non-public address {ip} for host '{host}'"
    return True, ""


def _format_results(query: str, items: list[dict[str, Any]], n: int) -> str:
    """Format provider results into shared plaintext output."""
    if not items:
        return f"No results for: {query}"
    lines = [f"Results for: {query}\n"]
    for i, item in enumerate(items[:n], 1):
        title = _normalize(_strip_tags(item.get("title", "")))
        snippet = _normalize(_strip_tags(item.get("content", "")))
        lines.append(f"{i}. {title}\n   {item.get('url', '')}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


def _format_service_response(query: str, result: dict[str, Any], n: int) -> str:
    provider = str(result.get("provider") or "").strip() or "unknown"
    items = result.get("search_results")
    if not isinstance(items, list):
        items = []
    lines = [f"Provider: {provider}", _format_results(query, items, n)]
    answer = _normalize(_strip_tags(str(result.get("answer") or "")))
    if answer and answer != "Web search is disabled.":
        lines.append(f"\nSummary:\n{answer}")
    return "\n".join(line for line in lines if line)


class WebSearchTool(Tool):
    """Search the web using configured provider."""

    name = "web_search"
    description = "Search the web. Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    }

    def __init__(self, config: WebSearchConfig | None = None, proxy: str | None = None):
        from deeptutor.tutorbot.config.schema import WebSearchConfig

        self.config = config if config is not None else WebSearchConfig()
        self.proxy = proxy
        self._last_trace_metadata: dict[str, Any] | None = None

    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        n = min(max(count or self.config.max_results, 1), 10)
        self._last_trace_metadata = None
        try:
            from deeptutor.services.search import web_search

            result = await asyncio.to_thread(web_search, query, max_results=n)
        except Exception as exc:
            logger.warning("Configured web_search provider failed: {}", exc)
            return f"Error: web_search failed ({exc})"

        citations = result.get("citations") if isinstance(result.get("citations"), list) else []
        search_results = (
            result.get("search_results") if isinstance(result.get("search_results"), list) else []
        )
        self._last_trace_metadata = {
            "provider": str(result.get("provider") or "").strip(),
            "citations": len(citations),
            "search_results": len(search_results),
            "sources": search_results[:8],
            "web_search_sources": search_results[:8],
        }
        return _format_service_response(query, result, n)

    def consume_trace_metadata(self) -> dict[str, Any] | None:
        metadata = self._last_trace_metadata
        self._last_trace_metadata = None
        return metadata

    async def _search_brave(self, query: str, n: int) -> str:
        api_key = self.config.api_key or os.environ.get("BRAVE_API_KEY", "")
        if not api_key:
            logger.warning("BRAVE_API_KEY not set, falling back to DuckDuckGo")
            return await self._search_duckduckgo(query, n)
        try:
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": api_key},
                    timeout=10.0,
                )
                r.raise_for_status()
            items = [
                {"title": x.get("title", ""), "url": x.get("url", ""), "content": x.get("description", "")}
                for x in r.json().get("web", {}).get("results", [])
            ]
            return _format_results(query, items, n)
        except Exception as e:
            return f"Error: {e}"

    async def _search_tavily(self, query: str, n: int) -> str:
        api_key = self.config.api_key or os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            logger.warning("TAVILY_API_KEY not set, falling back to DuckDuckGo")
            return await self._search_duckduckgo(query, n)
        try:
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                r = await client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"query": query, "max_results": n},
                    timeout=15.0,
                )
                r.raise_for_status()
            return _format_results(query, r.json().get("results", []), n)
        except Exception as e:
            return f"Error: {e}"

    async def _search_searxng(self, query: str, n: int) -> str:
        base_url = (self.config.base_url or os.environ.get("SEARXNG_BASE_URL", "")).strip()
        if not base_url:
            logger.warning("SEARXNG_BASE_URL not set, falling back to DuckDuckGo")
            return await self._search_duckduckgo(query, n)
        endpoint = f"{base_url.rstrip('/')}/search"
        is_valid, error_msg = _validate_url(endpoint)
        if not is_valid:
            return f"Error: invalid SearXNG URL: {error_msg}"
        try:
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                r = await client.get(
                    endpoint,
                    params={"q": query, "format": "json"},
                    headers={"User-Agent": USER_AGENT},
                    timeout=10.0,
                )
                r.raise_for_status()
            return _format_results(query, r.json().get("results", []), n)
        except Exception as e:
            return f"Error: {e}"

    async def _search_jina(self, query: str, n: int) -> str:
        api_key = self.config.api_key or os.environ.get("JINA_API_KEY", "")
        if not api_key:
            logger.warning("JINA_API_KEY not set, falling back to DuckDuckGo")
            return await self._search_duckduckgo(query, n)
        try:
            headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                r = await client.get(
                    f"https://s.jina.ai/",
                    params={"q": query},
                    headers=headers,
                    timeout=15.0,
                )
                r.raise_for_status()
            data = r.json().get("data", [])[:n]
            items = [
                {"title": d.get("title", ""), "url": d.get("url", ""), "content": d.get("content", "")[:500]}
                for d in data
            ]
            return _format_results(query, items, n)
        except Exception as e:
            return f"Error: {e}"

    async def _search_duckduckgo(self, query: str, n: int) -> str:
        try:
            from ddgs import DDGS

            ddgs = DDGS(timeout=10)
            raw = await asyncio.to_thread(ddgs.text, query, max_results=n)
            if not raw:
                return f"No results for: {query}"
            items = [
                {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")}
                for r in raw
            ]
            return _format_results(query, items, n)
        except Exception as e:
            logger.warning("DuckDuckGo search failed: {}", e)
            return f"Error: DuckDuckGo search failed ({e})"


class WebFetchTool(Tool):
    """Fetch and extract content from a URL."""

    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100},
        },
        "required": ["url"],
    }

    def __init__(self, max_chars: int = 50000, proxy: str | None = None):
        self.max_chars = max_chars
        self.proxy = proxy

    async def execute(self, url: str, extractMode: str = "markdown", maxChars: int | None = None, **kwargs: Any) -> str:
        max_chars = maxChars or self.max_chars
        is_valid, error_msg = await asyncio.to_thread(_assert_url_safe, url)
        if not is_valid:
            return json.dumps({"error": f"URL validation failed: {error_msg}", "url": url}, ensure_ascii=False)

        result = await self._fetch_jina(url, max_chars)
        if result is None:
            result = await self._fetch_readability(url, extractMode, max_chars)
        return result

    async def _fetch_jina(self, url: str, max_chars: int) -> str | None:
        """Try fetching via Jina Reader API. Returns None on failure."""
        try:
            headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
            jina_key = os.environ.get("JINA_API_KEY", "")
            if jina_key:
                headers["Authorization"] = f"Bearer {jina_key}"
            async with httpx.AsyncClient(proxy=self.proxy, timeout=20.0) as client:
                r = await client.get(f"https://r.jina.ai/{url}", headers=headers)
                if r.status_code == 429:
                    logger.debug("Jina Reader rate limited, falling back to readability")
                    return None
                r.raise_for_status()

            data = r.json().get("data", {})
            title = data.get("title", "")
            text = data.get("content", "")
            if not text:
                return None

            if title:
                text = f"# {title}\n\n{text}"
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]

            return json.dumps({
                "url": url, "finalUrl": data.get("url", url), "status": r.status_code,
                "extractor": "jina", "truncated": truncated, "length": len(text), "text": text,
            }, ensure_ascii=False)
        except Exception as e:
            logger.debug("Jina Reader failed for {}, falling back to readability: {}", url, e)
            return None

    async def _fetch_readability(self, url: str, extract_mode: str, max_chars: int) -> str:
        """Local fallback using readability-lxml.

        Redirects are followed manually (follow_redirects=False) so every hop is
        re-checked against the SSRF guard — a public URL that 30x-redirects to an
        internal/metadata address must not slip past the entry check.
        """
        from readability import Document

        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=30.0,
                proxy=self.proxy,
            ) as client:
                current = url
                r = None
                for _ in range(MAX_REDIRECTS + 1):
                    ok, err = await asyncio.to_thread(_assert_url_safe, current)
                    if not ok:
                        return json.dumps(
                            {"error": f"Blocked URL: {err}", "url": current},
                            ensure_ascii=False,
                        )
                    r = await client.get(current, headers={"User-Agent": USER_AGENT})
                    if r.is_redirect and r.next_request is not None:
                        current = str(r.next_request.url)
                        continue
                    break
                else:
                    return json.dumps(
                        {"error": "Too many redirects", "url": url},
                        ensure_ascii=False,
                    )
                r.raise_for_status()

            ctype = r.headers.get("content-type", "")

            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2, ensure_ascii=False), "json"
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                doc = Document(r.text)
                content = self._to_markdown(doc.summary()) if extract_mode == "markdown" else _strip_tags(doc.summary())
                text = f"# {doc.title()}\n\n{content}" if doc.title() else content
                extractor = "readability"
            else:
                text, extractor = r.text, "raw"

            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]

            return json.dumps({
                "url": url, "finalUrl": str(r.url), "status": r.status_code,
                "extractor": extractor, "truncated": truncated, "length": len(text), "text": text,
            }, ensure_ascii=False)
        except httpx.ProxyError as e:
            logger.error("WebFetch proxy error for {}: {}", url, e)
            return json.dumps({"error": f"Proxy error: {e}", "url": url}, ensure_ascii=False)
        except Exception as e:
            logger.error("WebFetch error for {}: {}", url, e)
            return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)

    def _to_markdown(self, html_content: str) -> str:
        """Convert HTML to markdown."""
        text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
                      lambda m: f'[{_strip_tags(m[2])}]({m[1]})', html_content, flags=re.I)
        text = re.sub(r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
                      lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n', text, flags=re.I)
        text = re.sub(r'<li[^>]*>([\s\S]*?)</li>', lambda m: f'\n- {_strip_tags(m[1])}', text, flags=re.I)
        text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
        text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
        return _normalize(_strip_tags(text))
