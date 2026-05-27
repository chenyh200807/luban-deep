"""Record/replay cassette store for the harness (9+ roadmap H1 keystone).

Captures the non-deterministic events of a turn — LLM completions and tool
results — keyed by a stable digest of their inputs, so a recorded run can be
replayed deterministically with zero network / zero key / zero cost.

Per the record-and-replay research (arXiv 2505.17716): the key must encode the
**model id**, **decode parameters**, and the **input** (messages / tool args).
This module owns only the store + key contract; the interception shim that
records/replays around ``factory``/``tool_registry`` lives in ``llm_replay.py``.

Determinism caveat (roadmap C1b): the key digests the inputs as given. If the
caller's prompt assembly injects volatile fields (timestamps / uuids / ordering),
those must be normalized *before* keying or replay will miss spuriously. The
shim is responsible for that normalization; this store treats inputs as opaque.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def _digest(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def llm_key(*, model: str, messages: list[dict[str, Any]], params: dict[str, Any]) -> str:
    """Stable key for an LLM completion: model id + decode params + messages.

    Parameter order does not affect the key (``sort_keys``), so two calls with
    the same semantic inputs collide as intended.
    """
    return _digest({"model": model, "messages": messages, "params": params})


def tool_key(*, name: str, args: dict[str, Any]) -> str:
    """Stable key for a tool invocation: tool name + arguments."""
    return _digest({"name": name, "args": args})


@dataclass
class Cassette:
    """A recorded set of LLM/tool responses, keyed by input digest."""

    llm: dict[str, str] = field(default_factory=dict)
    tool: dict[str, Any] = field(default_factory=dict)

    def record_llm(self, key: str, response: str) -> None:
        self.llm[key] = response

    def replay_llm(self, key: str) -> str:
        if key not in self.llm:
            raise KeyError(f"cassette miss (llm): {key}")
        return self.llm[key]

    def record_tool(self, key: str, result: Any) -> None:
        self.tool[key] = result

    def replay_tool(self, key: str) -> Any:
        if key not in self.tool:
            raise KeyError(f"cassette miss (tool): {key}")
        return self.tool[key]

    def to_json(self) -> str:
        return (
            json.dumps(
                {"llm": self.llm, "tool": self.tool},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    @classmethod
    def from_json(cls, text: str) -> "Cassette":
        payload = json.loads(text)
        return cls(llm=payload.get("llm", {}), tool=payload.get("tool", {}))
