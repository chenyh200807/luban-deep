#!/usr/bin/env python3
"""Static control-plane single-writer allowlist guard (Task 1, fast-mode
orchestrator simplification plan §14.A).

Every turn fact in the unified ``/api/v1/ws`` path — ``turn_semantic_decision``
(relation/submission), ``active_object``, ``question_lifecycle_scene``,
``is_correct`` / ``score`` (grading), ``reveal_reference`` (answer reveal), and
the visible terminal / transport frames — must each have exactly one canonical
writer; every other layer may only read, project, or defensively guard. This
guard is the *register-before-use baseline* for that invariant: it scans the
writer-map files for control-plane write-sites and fails the moment one appears
that is not registered in ``contracts/index.yaml:control_plane_writers``.

This is Task 1, so the guard does NOT collapse authorities — it registers the
*current* writers (canonical + competing + defensive) so the live tree comes
back clean (exit 0). A new, unregistered writer is what turns it red.

Detection is AST-primary (alias-proof, no docstring/comment false-positives):

- ``ast.Assign`` / ``ast.AnnAssign`` whose target is a ``Subscript`` with a
  constant string key matching a control-plane field
  (e.g. ``context.metadata["turn_semantic_decision"] = ...``,
  ``result_payload["turn_semantic_decision"] = ...``).
- ``ast.Call`` to ``build_turn_semantic_decision`` (builder), or to a StreamBus
  receiver method ``.result`` / ``.progress`` / ``.ack`` (the last is a dormant
  prospective arm — the live enum has no ACK), or ``.setdefault``.
- ``ast.Call`` constructing ``StreamEvent(type=StreamEventType.RESULT|PROGRESS|ACK)``.
- ``ast.keyword`` ``reveal_answers`` / ``reveal_explanations`` set to True (or a
  non-False expression) — a reveal write. ``reveal_answers=False`` is a safe
  default and is NOT flagged.
- A bare ``StreamEventType.ACK`` reference (dormant arm) carrying a contentful
  metadata payload.

String literals are ``ast.Expr`` / ``ast.Constant`` nodes, never assignment
targets or call attributes, so docstrings and comments never false-positive.

Each detected site is keyed ``(field, writer_type, file, enclosing_symbol)`` and
matched against the allowlist (the called-symbol is used for builder/stream
calls so a canonical builder's internal callsites are covered by one entry).

Exit codes:
  0  clean (all detected sites allowlisted; both contracts blocks byte-equal)
  1  one or more unregistered control-plane writers, or contracts parity drift
  2  fail-closed: ``control_plane_writers`` missing/empty in contracts/index.yaml
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = PROJECT_ROOT / "contracts" / "index.yaml"
PACKAGE_INDEX_PATH = PROJECT_ROOT / "deeptutor" / "contracts" / "index.yaml"

# --- Control-plane fields keyed by their metadata/payload subscript string. ---
# Maps the literal dict key -> canonical control-plane field name.
_SUBSCRIPT_FIELD_KEYS: dict[str, str] = {
    "turn_semantic_decision": "turn_semantic_decision",
    "question_lifecycle_scene": "question_lifecycle_scene",
    "active_object": "active_object",
    "question_followup_context": "question_followup_context",
    "question_followup_action": "question_followup_action",
    "is_correct": "is_correct",
    "score": "score",
    # Dormant prospective arm: contentful payload smuggled into a transport key.
    "first_useful_content": "first_useful_content",
}

# Builder call whose return value is the canonical relation/submission decision.
_SEMANTIC_BUILDER = "build_turn_semantic_decision"

# StreamBus transport methods. ``.ack`` is a dormant prospective arm (no such
# method exists yet); the guard recognises it so a future contentful ack frame
# is flagged on arrival.
_STREAM_METHODS: dict[str, str] = {
    "result": "stream_result",
    "progress": "stream_progress",
    "ack": "stream_ack",
}
# Receiver names that denote a StreamBus instance.
_STREAM_RECEIVERS: frozenset[str] = frozenset({"bus", "stream", "_bus", "self"})

# StreamEvent(type=StreamEventType.<X>) terminal/transport frame writers.
_STREAM_EVENT_TYPES: dict[str, str] = {
    "RESULT": "stream_result",
    "PROGRESS": "stream_progress",
    "ACK": "stream_ack",  # dormant prospective arm
}

_REVEAL_KWARGS: frozenset[str] = frozenset({"reveal_answers", "reveal_explanations"})

# Writer-map files actually scanned in the live tree. Mirrors the cross-expert
# writer map (plan §5.A.1 / §7). The canonical builder module and grading
# adapter are included so their canonical write-sites are registered; the
# capability / runtime / orchestrator files are where competing writers live.
WRITER_MAP_FILES: tuple[str, ...] = (
    "deeptutor/runtime/orchestrator.py",
    "deeptutor/services/session/turn_runtime.py",
    "deeptutor/services/semantic_router.py",
    "deeptutor/capabilities/deep_question.py",
    "deeptutor/capabilities/tutorbot.py",
    "deeptutor/services/construction_grading/deep_question_adapter.py",
    "deeptutor/core/stream_bus.py",
    "deeptutor/core/terminal_result_assembler.py",
    "deeptutor/api/routers/unified_ws.py",
)


@dataclass(frozen=True)
class _Site:
    field: str
    writer_type: str
    file: str
    symbol: str  # enclosing function/class, or called-symbol for builder/stream
    lineno: int
    snippet: str


@dataclass(frozen=True)
class _Allow:
    field: str
    writer_type: str
    file: str
    symbol: str


# ---------------------------------------------------------------------------
# Allowlist loading (fail-closed) + contracts parity
# ---------------------------------------------------------------------------
def _read_control_plane_writers(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = payload.get("control_plane_writers")
    return entries if isinstance(entries, list) else []


def _load_allowlist() -> list[_Allow]:
    """Load + validate the allowlist. Raises ``_FailClosed`` when missing/empty."""
    entries = _read_control_plane_writers(INDEX_PATH)
    if not entries:
        raise _FailClosed(
            "control-plane-writer-guard: control_plane_writers missing or empty in "
            "contracts/index.yaml — register-before-use baseline cannot run (fail-closed)."
        )
    out: list[_Allow] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        out.append(
            _Allow(
                field=str(entry.get("field", "")),
                writer_type=str(entry.get("writer_type", "")),
                file=str(entry.get("file", "")),
                symbol=str(entry.get("symbol", "")),
            )
        )
    return out


class _FailClosed(RuntimeError):
    """Raised when the allowlist is missing/empty (guard exit code 2)."""


def evaluate_contracts_allowlist_parity() -> tuple[bool, str]:
    """The control_plane_writers block must be byte-identical between the repo
    contract and the packaged runtime copy."""
    if not INDEX_PATH.exists() or not PACKAGE_INDEX_PATH.exists():
        return False, "control-plane-writer-guard: a contracts/index.yaml copy is missing"
    repo = _read_control_plane_writers(INDEX_PATH)
    pkg = _read_control_plane_writers(PACKAGE_INDEX_PATH)
    if repo != pkg:
        return False, (
            "control-plane-writer-guard: control_plane_writers differs between "
            "contracts/index.yaml and deeptutor/contracts/index.yaml — keep them identical."
        )
    return True, "control-plane-writer-guard: contracts allowlist parity OK"


# ---------------------------------------------------------------------------
# AST scanning
# ---------------------------------------------------------------------------
def _enclosing_symbol(parents: list[ast.AST]) -> str:
    for node in reversed(parents):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return node.name
    return "<module>"


def _subscript_key(target: ast.expr) -> str | None:
    """Return the constant string key of ``x[...]`` subscript, else None."""
    if isinstance(target, ast.Subscript):
        sl = target.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            return sl.value
    return None


def _attr_name(node: ast.expr) -> tuple[str | None, str | None]:
    """For ``recv.method``, return (receiver_root_name, method_name)."""
    if isinstance(node, ast.Attribute):
        recv = node.value
        if isinstance(recv, ast.Name):
            return recv.id, node.attr
        if isinstance(recv, ast.Attribute):
            return recv.attr, node.attr
    return None, None


def _stream_event_type_member(node: ast.expr) -> str | None:
    """For ``StreamEventType.RESULT``, return 'RESULT'."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "StreamEventType"
    ):
        return node.attr
    return None


def _kw_is_reveal_true(value: ast.expr) -> bool:
    """A reveal kwarg is a 'write' unless it is the literal False."""
    if isinstance(value, ast.Constant):
        return value.value is not False
    return True  # any non-literal expression is treated as a possible reveal


def _snippet(source_lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(source_lines):
        return source_lines[lineno - 1].strip()[:140]
    return ""


def _detect_sites(rel: str, source: str) -> list[_Site]:
    """Single source of truth for control-plane write-site detection.

    Both the gate (``_scan_source``) and the allowlist-authoring path
    (``_collect_sites``) delegate here so their ``writer_type`` verdicts can
    never diverge — a divergence would make the gate red on a legitimately
    registered writer. Raises ``SyntaxError`` on an unparseable source; callers
    decide how to treat that (fail-closed for the gate, skip for authoring).
    """
    tree = ast.parse(source, filename=rel)  # may raise SyntaxError
    sites: list[_Site] = []
    lines = source.splitlines()

    def visit(node: ast.AST, parents: list[ast.AST]) -> None:
        sym = _enclosing_symbol(parents)
        ln = getattr(node, "lineno", 0)

        # (1) subscript assignment: x["<field>"] = ...
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt in targets:
                key = _subscript_key(tgt)
                if key in _SUBSCRIPT_FIELD_KEYS:
                    field = _SUBSCRIPT_FIELD_KEYS[key]
                    wt = "metadata_assignment"
                    # result_payload[...] / self.*_payload[...] -> payload assignment
                    if isinstance(tgt, ast.Subscript):
                        base = tgt.value
                        if isinstance(base, ast.Name) and "payload" in base.id:
                            wt = "payload_assignment"
                        elif isinstance(base, ast.Attribute) and "payload" in base.attr:
                            wt = "payload_assignment"
                    sites.append(_Site(field, wt, rel, sym, ln, _snippet(lines, ln)))

        # (2) calls: builder / stream methods / StreamEvent(type=...)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == _SEMANTIC_BUILDER:
                sites.append(
                    _Site("turn_semantic_decision", "builder_call", rel, sym, ln, _snippet(lines, ln))
                )
            recv, method = _attr_name(func)
            if method in _STREAM_METHODS and recv in _STREAM_RECEIVERS:
                field = "visible_result" if method == "result" else "visible_transport_frame"
                sites.append(_Site(field, _STREAM_METHODS[method], rel, sym, ln, _snippet(lines, ln)))
            if isinstance(func, ast.Name) and func.id == "StreamEvent":
                for kw in node.keywords:
                    if kw.arg == "type":
                        member = _stream_event_type_member(kw.value)
                        if member in _STREAM_EVENT_TYPES:
                            field = "visible_result" if member == "RESULT" else "visible_transport_frame"
                            sites.append(
                                _Site(field, _STREAM_EVENT_TYPES[member], rel, sym, ln, _snippet(lines, ln))
                            )
            # (3) reveal kwargs set to True / non-False
            for kw in node.keywords:
                if kw.arg in _REVEAL_KWARGS and _kw_is_reveal_true(kw.value):
                    sites.append(
                        _Site("reveal_reference", "reveal_kwarg", rel, sym, ln, _snippet(lines, ln))
                    )

        # (4) bare StreamEventType.ACK reference (dormant arm).
        member = _stream_event_type_member(node) if isinstance(node, ast.Attribute) else None
        if member == "ACK":
            sites.append(
                _Site("visible_transport_frame", "stream_ack", rel, sym, ln, _snippet(lines, ln))
            )

        for child in ast.iter_child_nodes(node):
            visit(child, parents + [node])

    visit(tree, [])

    # Deduplicate identical sites (a single line can match multiple sub-rules).
    seen: set[tuple] = set()
    unique: list[_Site] = []
    for s in sites:
        site_key = (s.field, s.writer_type, s.file, s.symbol, s.lineno)
        if site_key not in seen:
            seen.add(site_key)
            unique.append(s)
    return unique


def _scan_source(rel: str, source: str) -> list[str]:
    """Scan one source string for unregistered control-plane writers.

    ``rel`` is the repo-relative path used for allowlist matching and messages.
    Returns a list of human-readable violation strings (empty = clean).
    """
    try:
        sites = _detect_sites(rel, source)
    except SyntaxError as exc:  # fail-safe: an unparseable file cannot be verified
        return [f"{rel}: AST parse failed ({exc}); cannot verify control-plane writers"]
    return _filter_unregistered(sites)


def _filter_unregistered(sites: list[_Site]) -> list[str]:
    try:
        allow = _load_allowlist()
    except _FailClosed as exc:
        return [str(exc)]
    allow_set = {(a.field, a.writer_type, a.file, a.symbol) for a in allow}
    violations: list[str] = []
    for s in sites:
        if (s.field, s.writer_type, s.file, s.symbol) in allow_set:
            continue
        violations.append(
            f"{s.file}:{s.lineno}: unregistered control-plane writer "
            f"field={s.field} writer_type={s.writer_type} symbol={s.symbol} "
            f":: {s.snippet}"
        )
    return violations


def _scan_repo() -> list[str]:
    violations: list[str] = []
    for rel in WRITER_MAP_FILES:
        path = PROJECT_ROOT / rel
        if not path.exists():
            violations.append(f"{rel}: writer-map file missing (guard cannot verify)")
            continue
        violations.extend(_scan_source(rel, path.read_text(encoding="utf-8")))
    return violations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _list_sites() -> list[_Site]:
    """All detected sites in the live tree (for authoring the allowlist)."""
    sites: list[_Site] = []
    for rel in WRITER_MAP_FILES:
        path = PROJECT_ROOT / rel
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        # reuse the scanner but capture pre-filter sites
        sites.extend(_collect_sites(rel, source))
    return sites


def _collect_sites(rel: str, source: str) -> list[_Site]:
    """Raw detected sites (no allowlist filtering) for authoring the allowlist.

    Delegates to the same ``_detect_sites`` the gate uses, so authoring and
    enforcement can never disagree on ``writer_type``. Unparseable sources are
    skipped here (the gate reports them as a violation instead).
    """
    try:
        return _detect_sites(rel, source)
    except SyntaxError:
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="gate mode: fail on unregistered writers")
    group.add_argument(
        "--list",
        action="store_true",
        help="list all detected control-plane write-sites (for authoring the allowlist)",
    )
    args = parser.parse_args(argv)

    if args.list:
        for s in _list_sites():
            print(
                f"{s.file}:{s.lineno} field={s.field} writer_type={s.writer_type} "
                f"symbol={s.symbol} :: {s.snippet}"
            )
        return 0

    # fail-closed allowlist check first.
    try:
        _load_allowlist()
    except _FailClosed as exc:
        print(str(exc), file=sys.stderr)
        return 2

    parity_ok, parity_msg = evaluate_contracts_allowlist_parity()
    parity_stream = sys.stdout if parity_ok else sys.stderr
    print(parity_msg, file=parity_stream)

    violations = _scan_repo()
    if violations or not parity_ok:
        print("control-plane-writer-guard: FAIL", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print("control-plane-writer-guard: OK (all control-plane write-sites allowlisted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
