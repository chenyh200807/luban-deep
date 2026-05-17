from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_workspace_autoscroll_observer_reconnects_after_messages_mount() -> None:
    source = _read("web/hooks/useChatAutoScroll.ts")

    assert "if (!hasMessages) return;" in source
    assert "}, [hasMessages, isStreaming, scrollToBottom]);" in source


def test_workspace_enter_key_does_not_send_while_ime_is_composing() -> None:
    source = _read("web/app/(workspace)/page.tsx")

    assert "event.nativeEvent.isComposing" in source
    assert "event.keyCode === 229" in source
    assert 'if (event.key === "Enter" && !event.shiftKey && !isImeComposing)' in source


def test_tutorbot_chat_restored_history_resnaps_to_bottom() -> None:
    source = _read("web/app/(workspace)/agents/[botId]/chat/page.tsx")

    assert 'behavior: ScrollBehavior = "smooth"' in source
    assert 'scrollToBottom("instant")' in source
    assert 'window.setTimeout(() => scrollToBottom("instant"), 250)' in source


def test_workspace_sends_request_scoped_llm_selection() -> None:
    context_source = _read("web/context/UnifiedChatContext.tsx")
    page_source = _read("web/app/(workspace)/page.tsx")
    composer_source = _read("web/components/chat/home/ChatComposer.tsx")

    assert "llmSelection?: LLMSelection | null;" in context_source
    assert "llm_selection: effectiveLLMSelection" in context_source
    assert "listLLMOptions()" in page_source
    assert "llmSelection: selectedLLMSelection" in page_source
    assert "ModelSelector" in composer_source


def test_chat_model_options_use_public_projection_not_admin_settings() -> None:
    source = _read("web/lib/llm-options.ts")

    assert "/api/v1/system/public-capabilities" in source
    assert "/api/v1/settings/llm-options" not in source


def test_next_dev_proxies_same_origin_api_routes_to_backend() -> None:
    source = _read("web/next.config.js")

    assert "NEXT_API_PROXY_TARGET" in source
    assert "http://localhost:8001" in source
    assert 'source: "/api/v1/:path*"' in source
    assert "destination: `${normalizedApiProxyTarget}/api/v1/:path*`" in source
    assert 'source: "/api/attachments/:path*"' in source
    assert "destination: `${normalizedApiProxyTarget}/api/attachments/:path*`" in source

    assert not (ROOT / "web/app/api/v1/[...path]/route.ts").exists()


def test_docker_frontend_default_uses_direct_backend_api_base() -> None:
    source = _read("Dockerfile")

    assert 'API_BASE="http://localhost:${BACKEND_PORT}"' in source
    assert 'API_BASE="__CURRENT_ORIGIN__"' not in source


def test_production_client_does_not_silently_use_same_origin_api_base() -> None:
    source = _read("web/lib/api.ts")

    assert 'process.env.NODE_ENV !== "production"' in source
    assert "NEXT_PUBLIC_API_BASE is not configured" in source


def test_invite_test_jsonl_fallback_stays_out_of_git() -> None:
    source = _read(".gitignore")

    assert "web/tmp/" in source


def test_workspace_shell_hides_fixed_sidebar_on_mobile() -> None:
    source = _read("web/app/(workspace)/layout.tsx")

    assert 'className="hidden md:block"' in source
    assert 'className="min-w-0 flex-1 overflow-hidden bg-[var(--background)]"' in source
    assert "md:hidden" in source


def test_chat_composer_can_wrap_toolbar_on_narrow_viewports() -> None:
    source = _read("web/components/chat/home/ChatComposer.tsx")

    assert "flex flex-wrap items-center gap-2" in source
    assert "flex min-w-0 flex-1 flex-wrap items-center gap-1" in source
    assert "basis-full" in source
    assert "max-w-[132px]" in source
