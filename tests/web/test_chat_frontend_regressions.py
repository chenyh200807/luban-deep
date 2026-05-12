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
    assert "if (event.key === \"Enter\" && !event.shiftKey && !isImeComposing)" in source


def test_tutorbot_chat_restored_history_resnaps_to_bottom() -> None:
    source = _read("web/app/(workspace)/agents/[botId]/chat/page.tsx")

    assert "behavior: ScrollBehavior = \"smooth\"" in source
    assert "scrollToBottom(\"instant\")" in source
    assert "window.setTimeout(() => scrollToBottom(\"instant\"), 250)" in source


def test_workspace_sends_request_scoped_llm_selection() -> None:
    context_source = _read("web/context/UnifiedChatContext.tsx")
    page_source = _read("web/app/(workspace)/page.tsx")
    composer_source = _read("web/components/chat/home/ChatComposer.tsx")

    assert "llmSelection?: LLMSelection | null;" in context_source
    assert "llm_selection: effectiveLLMSelection" in context_source
    assert "listLLMOptions()" in page_source
    assert "llmSelection: selectedLLMSelection" in page_source
    assert "ModelSelector" in composer_source
