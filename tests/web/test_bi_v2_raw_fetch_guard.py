"""Round 4 S3 — source-level guard against raw fetch / apiUrl in BI v2 panels.

Rationale: Round 3 introduced `useAuditedAction` as the single audited-write
gate. But nothing in the codebase prevents a future panel from calling
``fetch('/api/v1/member/.../notes', ...)`` directly and bypassing every
invariant (idempotency injection, registry membership, contract test
coverage). This pytest closes that hole at the *source code* level — a 5-char
edit that introduces a raw ``fetch(`` outside the allowlist below trips CI.

The allowlist names the only files in ``web/app/(workspace)/bi/_v2`` that may
import ``fetch`` / ``apiUrl``. New files cannot be added without an explicit
extension here, which is the audit trail.

We complement (not replace) Round 3 E's Playwright contract tests:
  * Playwright contract tests assert *behavior at runtime* on one path.
  * This guard asserts *structural invariants* across every panel file.
Combined, an attempt to bypass the gate fails at either lint, type, or
contract layer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V2_ROOT = REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_v2"

# Files allowed to call fetch() / apiUrl() / withAdminAuthorization() directly.
# Anything outside this allowlist must go through useAuditedAction (writes) or
# an established read-only api client (e.g. lib/bi-api.ts via importing typed
# helpers, not raw fetch).
ALLOW_RAW_FETCH = frozenset(
    {
        "useAuditedAction.ts",  # single audited-write gate
    }
)

RAW_FETCH_PATTERN = re.compile(r"\bfetch\s*\(")
APIURL_PATTERN = re.compile(r"\bapiUrl\s*\(")
ADMIN_AUTH_PATTERN = re.compile(r"\bwithAdminAuthorization\s*\(")


def _v2_source_files() -> list[Path]:
    return [p for p in V2_ROOT.rglob("*") if p.is_file() and p.suffix in {".ts", ".tsx"}]


def _strip_comments_and_strings(text: str) -> str:
    """Crude pass: remove // line comments, /* block */ comments, and string
    literals so we don't false-positive on docstrings or banner copy talking
    *about* fetch / apiUrl. Good enough for guard purposes; full TS parsing
    would be over-engineering at this scale.
    """
    # /* ... */ block comments (non-greedy, multiline)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # // line comments
    text = re.sub(r"//[^\n]*", "", text)
    # string literals (single / double / template) — preserve length-ish
    text = re.sub(r"'(?:\\.|[^'\\])*'", "''", text)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    text = re.sub(r"`(?:\\.|[^`\\])*`", "``", text)
    return text


def test_v2_no_raw_fetch_outside_allowlist() -> None:
    """Direct ``fetch(`` calls outside useAuditedAction are forbidden."""
    offenders: list[str] = []
    for path in _v2_source_files():
        rel = path.relative_to(V2_ROOT).as_posix()
        if path.name in ALLOW_RAW_FETCH:
            continue
        if path.name.endswith(".generated.ts"):
            continue
        if "/test" in rel or rel.startswith("__tests__/"):
            continue
        cleaned = _strip_comments_and_strings(path.read_text(encoding="utf-8"))
        if RAW_FETCH_PATTERN.search(cleaned):
            offenders.append(rel)
    assert not offenders, (
        "Raw fetch( calls found in BI v2 panels — all writes must go through "
        "useAuditedAction (Round 4 S3 invariant). Offenders:\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )


def test_v2_no_apiurl_outside_allowlist() -> None:
    """``apiUrl(`` calls outside useAuditedAction signal a URL being built
    by hand for a write — same regression vector as raw fetch.
    """
    offenders: list[str] = []
    for path in _v2_source_files():
        rel = path.relative_to(V2_ROOT).as_posix()
        if path.name in ALLOW_RAW_FETCH:
            continue
        if path.name.endswith(".generated.ts"):
            continue
        cleaned = _strip_comments_and_strings(path.read_text(encoding="utf-8"))
        if APIURL_PATTERN.search(cleaned):
            offenders.append(rel)
    assert not offenders, (
        "apiUrl() calls found in BI v2 panels — write URLs must come from the "
        "generated WRITE_ENDPOINTS registry via resolveWritePath. Offenders:\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )


def test_v2_no_admin_authorization_outside_allowlist() -> None:
    """``withAdminAuthorization`` outside useAuditedAction means actor binding
    is being built by hand, which historically led to actor='ops@deeptutor'
    placeholder strings shipping in PRs (Round 2/3 reviewer finds)."""
    offenders: list[str] = []
    for path in _v2_source_files():
        rel = path.relative_to(V2_ROOT).as_posix()
        if path.name in ALLOW_RAW_FETCH:
            continue
        if path.name.endswith(".generated.ts"):
            continue
        cleaned = _strip_comments_and_strings(path.read_text(encoding="utf-8"))
        if ADMIN_AUTH_PATTERN.search(cleaned):
            offenders.append(rel)
    assert not offenders, (
        "withAdminAuthorization() found outside useAuditedAction — actor "
        "binding must be injected by the single audited-action hook. Offenders:\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )


@pytest.mark.parametrize("anti_pattern", ["window.prompt(", "window.confirm("])
def test_v2_no_window_prompt_for_audited_actions(anti_pattern: str) -> None:
    """``window.prompt`` historically appeared in ``saveView()`` and feedback
    triage paths — both write-shaped flows. Even when the eventual write is
    deferred to backend, requesting input via ``window.prompt`` (a) is blocked
    by some browsers and (b) tends to be the first half of a fake-audit
    pattern (prompt → setState → "已写入 audit log").

    Whitelisted exception: ``BiV2MemberOpsPanel.tsx``'s ``saveView()`` is
    currently allowed because it explicitly writes to localStorage only and is
    NOT a server-side audit. This whitelist is the audit trail — any new use
    of window.prompt requires updating it and explaining why.
    """
    allow = {"BiV2MemberOpsPanel.tsx"}
    offenders: list[str] = []
    for path in _v2_source_files():
        rel = path.relative_to(V2_ROOT).as_posix()
        if path.name in allow:
            continue
        if path.name.endswith(".generated.ts"):
            continue
        cleaned = _strip_comments_and_strings(path.read_text(encoding="utf-8"))
        if anti_pattern in cleaned:
            offenders.append(rel)
    assert not offenders, (
        f"{anti_pattern} found in BI v2 panels — write-shaped flows must "
        "route through useAuditedAction. If the prompt is for local state "
        "only, add the file to the allowlist with a one-liner reason. "
        "Offenders:\n" + "\n".join(f"  - {o}" for o in offenders)
    )
