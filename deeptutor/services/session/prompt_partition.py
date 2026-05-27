"""Single authority for chat prompt partition (harness Deferred D4).

Splits a turn's system-prompt segments into a turn-invariant **stable prefix**
(eligible for provider KV / prompt-cache reuse) and a per-turn **dynamic tail**.

Invariant (the whole point of the partition):

    The stable prefix MUST depend only on its declared stable inputs. It must
    NOT carry any per-turn content (user message, memory, lifecycle scene skill,
    active object) — otherwise the leading prefix changes every turn, the cache
    never hits, and per-turn state could leak into a "stable" position.

This module owns *only* the split contract. It does not assemble prompts, talk
to providers, or measure cache hit-rate (that needs provider metrics and is a
separate D4 follow-up). Execution shells classify their own segments and call
:func:`partition_system_prompt` + :func:`to_system_messages`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class PartitionedPrompt:
    """A turn's system prompt split into cacheable prefix + per-turn tail."""

    stable_prefix: tuple[str, ...]
    dynamic_tail: tuple[str, ...]


def _clean(parts: Iterable[Any]) -> tuple[str, ...]:
    """Drop empties, normalize to stripped strings, preserve order."""
    cleaned: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if text:
            cleaned.append(text)
    return tuple(cleaned)


def partition_system_prompt(
    *,
    stable: Iterable[Any],
    dynamic: Iterable[Any],
) -> PartitionedPrompt:
    """Partition system-prompt segments into stable prefix + dynamic tail.

    ``stable`` segments are turn-invariant (identity, style rules, tool table,
    always-loaded skills); ``dynamic`` segments vary per turn (memory, lifecycle
    scene skill, active object). Order within each group is preserved; empties
    are dropped.
    """
    return PartitionedPrompt(stable_prefix=_clean(stable), dynamic_tail=_clean(dynamic))


def to_system_messages(partition: PartitionedPrompt) -> list[dict[str, str]]:
    """Render the partition as system messages, stable prefix first.

    Emitting the stable prefix as the leading message(s) is what lets an
    OpenAI-compatible provider reuse its cached prefix across turns: the dynamic
    tail follows and only the tail differs turn to turn.
    """
    return [
        {"role": "system", "content": segment}
        for segment in (*partition.stable_prefix, *partition.dynamic_tail)
    ]
