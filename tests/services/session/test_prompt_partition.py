from __future__ import annotations

from deeptutor.services.session.prompt_partition import (
    PartitionedPrompt,
    partition_system_prompt,
    to_system_messages,
)


def test_partition_separates_stable_and_dynamic_and_drops_empties() -> None:
    partition = partition_system_prompt(
        stable=["IDENTITY", "  ", "TOOL TABLE"],
        dynamic=["", "MEMORY", None, "SCENE SKILL"],
    )
    assert partition.stable_prefix == ("IDENTITY", "TOOL TABLE")
    assert partition.dynamic_tail == ("MEMORY", "SCENE SKILL")


def test_stable_prefix_is_turn_invariant_regardless_of_dynamic() -> None:
    """The whole point of D4: the cacheable prefix must depend ONLY on the
    stable inputs, never on per-turn dynamic content."""
    stable = ["STAGE PROMPT", "TOOL TABLE"]
    turn_a = partition_system_prompt(stable=stable, dynamic=["memory@t1", "scene mcq"])
    turn_b = partition_system_prompt(stable=stable, dynamic=["memory@t2 different", "scene case"])

    assert turn_a.stable_prefix == turn_b.stable_prefix
    # ...and the dynamic tails genuinely differ between turns.
    assert turn_a.dynamic_tail != turn_b.dynamic_tail


def test_to_system_messages_puts_all_stable_before_all_dynamic() -> None:
    partition = PartitionedPrompt(
        stable_prefix=("S1", "S2"),
        dynamic_tail=("D1", "D2"),
    )
    messages = to_system_messages(partition)

    assert [m["role"] for m in messages] == ["system"] * 4
    contents = [m["content"] for m in messages]
    assert contents == ["S1", "S2", "D1", "D2"]
    # No dynamic segment appears before any stable segment.
    last_stable = max(contents.index(s) for s in ("S1", "S2"))
    first_dynamic = min(contents.index(d) for d in ("D1", "D2"))
    assert last_stable < first_dynamic


def test_partition_is_lossless_for_nonempty_segments() -> None:
    stable = ["a", "b"]
    dynamic = ["c"]
    partition = partition_system_prompt(stable=stable, dynamic=dynamic)
    rendered = [m["content"] for m in to_system_messages(partition)]
    assert rendered == ["a", "b", "c"]


def test_empty_partition_yields_no_messages() -> None:
    partition = partition_system_prompt(stable=["", "  "], dynamic=[None, ""])
    assert to_system_messages(partition) == []
