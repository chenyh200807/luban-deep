"""provider-registry policy gate — "registered-or-you-can't-call" for LLM providers.

This is the machine enforcement of the RESOURCE_GOVERNANCE_FIX_PLAN root-cause
business fact: *every external LLM/embedding provider must be machine-confirmable
as registered in the single canonical list — its canonical base_url and key env —
with no second registry and no scattered hardcoded base_url bypass.* The
documentary rule becomes a deterministic CI gate here, wired into the SAME
contract-guard runner (NOT a new governance system). It mirrors
scripts/check_db_registry.py and scripts/check_env_registry.py one-for-one.

The registry lives in ``contracts/provider_registry.yaml`` (single canonical
list). This script reads it and scans changed code, failing on TWO conditions:

  (a) NEW HARDCODED PROVIDER BASE_URL — a ``base_url="https://<provider-api>"`` /
      ``api_base=…`` / ``= "https://<provider-api>…"`` / ``or "https://…"`` literal
      whose host matches a known provider api hostname, in a production file that
      is NOT the canonical registry module and NOT in the registry's grandfathered
      ``grandfathered_base_url_sites``. This is the止血 (stop-the-bleed) rule: a
      NEW scattered endpoint cannot slip in. (The 12 existing bypass sites are
      grandfathered and migrated by work order.) Changing a provider's endpoint
      must edit ONE place (the registry), not N — missing one routed half the
      calls to the wrong endpoint and mis-attributed cost (deepseek billing先例).

  (b) NEW PROVIDER IN A DEPRECATED REGISTRY COPY — a ``ProviderSpec(name="X", …)``
      added inside a DEPRECATED registry module (tutorbot/providers/registry.py or
      provider_runtime's embedding table) where ``X`` is NOT already a registered
      provider. This re-grows a second authority — exactly the病灶. New providers
      must be added to the CANONICAL module only. (Editing the existing entries of
      a deprecated copy is fine; only a NEW unregistered provider fails.)

Scope (deliberately not bureaucratic): only KNOWN provider api hostnames are
governed literals — a docs link / webhook / asset CDN is NOT a governed base_url.
ProviderSpec(...) outside the canonical + deprecated registry files is NOT a
second-registry signal. Tests / fixtures are out of scope.

Deterministic and pure: no LLM, no network. It reads files and applies regexes,
mirroring scripts/check_db_registry.py.

────────────────────────────────────────────────────────────────────────────────────────
PENDING HUNK — wiring into scripts/check_contract_guard.py
────────────────────────────────────────────────────────────────────────────────────────
scripts/check_contract_guard.py currently has UNCOMMITTED parallel WIP, so this
guard is NOT wired into its main() here (no dirty-file dependency / no carrying of
parallel work). Until that file is clean, the gate runs as its own CI step (see
.github/workflows/tests.yml), EXACTLY like the schema/db/env registry guards do.
Apply the hunk below when check_contract_guard.py is clean (or fold it into the
next contract-guard commit). It is intentionally additive and order-independent:

  # add near the other guard imports at top of scripts/check_contract_guard.py:
  from scripts.check_provider_registry import evaluate_provider_registry  # noqa: E402

  # inside main(), after the env guard prints, before the final return:
  prov_ok, prov_message = evaluate_provider_registry(changed_files)
  prov_stream = sys.stdout if prov_ok else sys.stderr
  print(prov_message, file=prov_stream)

  # and extend the final boolean:
  return 0 if (ok and code_ok and node_ok and lifecycle_ok
               and upstream_ok and ws_ok and env_ok and prov_ok) else 1

``evaluate_provider_registry(changed_files)`` is the changed-files entry point
provided below for exactly this wiring (reads each changed file, runs
collect+evaluate).
────────────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "contracts" / "provider_registry.yaml"

# A provider base_url literal. We match the literal *string* — capturing the URL
# in group 1 — in any of the bypass forms a call site uses:
#   base_url="https://…"  /  api_base="https://…"  /  = "https://…"  /  or "https://…"
# We capture every double/single-quoted http(s) URL on non-comment lines; the
# HOST allowlist (known provider api hostnames) is applied afterward so a docs
# link / webhook / asset CDN is never a governed literal.
_URL_LITERAL_RE = re.compile(r"""["'](https?://[^"'\s]+)["']""")

# A ProviderSpec(…) construction — the machine signal "a provider entry is being
# declared here". Real ProviderSpec(...) literals are MULTI-LINE with arbitrary
# kwarg order (``name=`` is rarely on the same line as the opening paren), so a
# line-by-line ``ProviderSpec(name=…)`` regex matched ZERO of the existing 27 and
# was a placebo (C1). We instead locate every ``ProviderSpec(`` opener over the
# WHOLE file body, walk its balanced-paren argument block, and find ``name=`` ANY-
# where inside it. This tolerates newlines and any kwarg ordering.
_PROVIDER_SPEC_OPEN_RE = re.compile(r"\bProviderSpec\s*\(")
# ``name = "X"`` inside an argument block — quote style + surrounding whitespace
# tolerant. Anchored to a ``name`` keyword arg (preceded by ``(``/``,``/whitespace
# so we never match a substring like ``display_name=``).
_PROVIDER_SPEC_NAME_RE = re.compile(r"""(?:^|[(,\s])name\s*=\s*["']([^"']+)["']""")

# Restrict to production source. Tests, fixtures, and the registry YAML itself
# are out of scope. Scripts/ are in scope (maintenance scripts call providers).
_IN_SCOPE_PATH_RE = re.compile(r"^(?:deeptutor/|scripts/)")
_OUT_OF_SCOPE_PATH_RE = re.compile(r"(?:^|/)tests?/|(?:^|/)conftest\.py$|_test\.py$|/fixtures?/")

# Loopback hosts are not a discriminating provider signal (shared with dev
# origins / CORS). Local-provider base_url drift is governed inside the registry
# data (rule b), not at call sites.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


@dataclass(frozen=True)
class BaseUrlUsage:
    """One provider base_url literal found in a scanned file."""

    path: str
    lineno: int
    url: str


@dataclass(frozen=True)
class ProviderSpecUsage:
    """One ProviderSpec(name=…) construction found in a scanned file."""

    path: str
    lineno: int
    provider_name: str


def _hostname(url: str) -> str:
    """Lowercased host of a URL (empty on parse failure)."""
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def load_provider_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load + index ``contracts/provider_registry.yaml`` into lookup structures.

    ``registered_provider_hosts`` is the set of api HOSTNAMES derived from every
    canonical_base_url — rule (a) keys off it (only KNOWN provider hosts are
    governed literals). ``registered_base_urls`` keeps the full literals for
    diagnostics. ``registered_providers`` is the provider-NAME set — rule (b)
    keys off it. ``grandfathered_base_url_sites`` and ``deprecated_modules`` are
    the存量 carve-outs.
    """
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    providers = payload.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ValueError("contracts/provider_registry.yaml must define a non-empty providers list")

    registered_providers: set[str] = set()
    registered_base_urls: set[str] = set()
    registered_provider_hosts: set[str] = set()
    for entry in providers:
        if not isinstance(entry, dict) or "name" not in entry:
            raise ValueError(f"provider_registry provider entry missing name: {entry!r}")
        registered_providers.add(str(entry["name"]))
        base = str(entry.get("canonical_base_url") or "").strip()
        if base:
            registered_base_urls.add(base)
            host = _hostname(base)
            # localhost / loopback hosts are shared by local providers AND by
            # non-provider dev URLs (CORS origins, dev servers). They are NOT a
            # discriminating provider signal — governing them would false-flag
            # api/main.py's localhost:3000 dev origin. Only remote provider api
            # hostnames are governed literals; local base_urls drift inside the
            # registry data only (rule b), not at scattered call sites.
            if host and host not in _LOCAL_HOSTS:
                registered_provider_hosts.add(host)

    canonical = payload.get("canonical_authority") or {}
    canonical_module = str(canonical.get("module") or "")
    if not canonical_module:
        raise ValueError("provider_registry must declare canonical_authority.module")

    deprecated_modules: set[str] = set()
    for entry in payload.get("deprecated_sources") or []:
        if isinstance(entry, dict) and entry.get("module"):
            deprecated_modules.add(str(entry["module"]))

    grandfathered_sites: set[str] = set()
    for entry in payload.get("grandfathered_base_url_sites") or []:
        if isinstance(entry, dict) and entry.get("path"):
            grandfathered_sites.add(str(entry["path"]))

    if not registered_provider_hosts:
        raise ValueError("provider_registry registered no provider api hostnames")

    return {
        "canonical_module": canonical_module,
        "registered_providers": registered_providers,
        "registered_base_urls": registered_base_urls,
        "registered_provider_hosts": registered_provider_hosts,
        "deprecated_modules": deprecated_modules,
        "grandfathered_base_url_sites": grandfathered_sites,
    }


def collect_base_url_usages(files: list[tuple[str, str]]) -> list[BaseUrlUsage]:
    """Scan ``(path, body)`` pairs for http(s) URL string literals."""
    usages: list[BaseUrlUsage] = []
    for path, body in files:
        if not body:
            continue
        for lineno, line in enumerate(body.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for match in _URL_LITERAL_RE.finditer(line):
                usages.append(BaseUrlUsage(path=path, lineno=lineno, url=match.group(1)))
    return usages


def _strip_line_comments(body: str) -> str:
    """Blank out ``#`` line-comment tails so a commented ProviderSpec is invisible.

    We replace the comment portion with spaces (preserving length / line offsets,
    so reported ``lineno`` stays correct). This is deliberately conservative: a
    ``#`` inside a string literal would also be stripped, but ProviderSpec arg
    values never legitimately contain a ``#`` for our purposes, and over-stripping
    only ever HIDES a candidate (never invents one) — it cannot cause a false
    positive. A fully commented-out ``ProviderSpec(`` block therefore yields no
    opener (its ``(`` is blanked), so it is never collected.
    """
    out: list[str] = []
    for line in body.splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        core = line[:-1] if newline else line
        idx = core.find("#")
        if idx != -1:
            core = core[:idx] + " " * (len(core) - idx)
        out.append(core + newline)
    return "".join(out)


def collect_provider_spec_usages(files: list[tuple[str, str]]) -> list[ProviderSpecUsage]:
    """Scan ``(path, body)`` pairs for ProviderSpec(…) constructions (multi-line).

    Real ProviderSpec literals span many lines with ``name=`` not on the opener
    line, so we cannot scan line-by-line. For each ``ProviderSpec(`` opener we walk
    the BALANCED-PAREN argument block over the whole (comment-stripped) body and
    extract ``name=`` from inside it — tolerant of newlines and any kwarg order.
    """
    usages: list[ProviderSpecUsage] = []
    for path, body in files:
        if not body:
            continue
        cleaned = _strip_line_comments(body)
        for opener in _PROVIDER_SPEC_OPEN_RE.finditer(cleaned):
            block, end = _balanced_paren_block(cleaned, opener.end() - 1)
            if block is None:
                continue  # unbalanced / truncated — skip rather than mis-read
            name_match = _PROVIDER_SPEC_NAME_RE.search(block)
            if not name_match:
                continue  # a ProviderSpec(...) with no literal name= (dynamic) — skip
            lineno = cleaned.count("\n", 0, opener.start()) + 1
            usages.append(
                ProviderSpecUsage(
                    path=path, lineno=lineno, provider_name=name_match.group(1)
                )
            )
    return usages


def _balanced_paren_block(text: str, open_paren_idx: int) -> tuple[str | None, int]:
    """Return the substring inside the balanced parens starting at ``open_paren_idx``.

    ``text[open_paren_idx]`` must be ``(``. Returns ``(inner, close_idx)`` where
    ``inner`` is the content between the matching parens, or ``(None, -1)`` if the
    parens never balance (truncated input). Quote-aware so a ``)`` inside a string
    literal does not prematurely close the block.
    """
    depth = 0
    i = open_paren_idx
    n = len(text)
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_idx + 1 : i], i
        i += 1
    return None, -1


def _check_new_hardcoded_base_urls(
    usages: list[BaseUrlUsage], registry: dict[str, Any]
) -> list[str]:
    """Fail rule (a): a NEW hardcoded provider base_url outside registry/grandfather.

    Only literals whose HOST is a known provider api hostname are governed (so a
    docs link / webhook / asset CDN is never flagged). The canonical registry
    module and grandfathered存量 sites are exempt.
    """
    known_hosts: set[str] = registry["registered_provider_hosts"]
    canonical_module: str = registry["canonical_module"]
    # The deprecated registry COPIES also legitimately hold base_url literals as
    # registry DATA, not as call-site bypasses — their drift is governed by rule
    # (b) (no NEW provider), not rule (a). Exempt them from the base_url rule, the
    # same as the canonical module.
    registry_data_modules: set[str] = {canonical_module} | registry["deprecated_modules"]
    grandfathered: set[str] = registry["grandfathered_base_url_sites"]
    failures: list[str] = []
    seen: set[tuple[str, int, str]] = set()
    for usage in usages:
        host = _hostname(usage.url)
        if host not in known_hosts:
            continue  # not a governed provider endpoint (docs/webhook/CDN/local)
        if usage.path in registry_data_modules:
            continue  # canonical + deprecated copies ARE where base_urls live
        if usage.path in grandfathered:
            continue  # existing存量 bypass, migrated by work order (not new)
        key = (usage.path, usage.lineno, usage.url)
        if key in seen:
            continue
        seen.add(key)
        failures.append(
            f"{usage.path}:{usage.lineno}: hardcoded provider base_url "
            f"'{usage.url}'. Resolve it from the canonical registry "
            f"({canonical_module}) via provider_runtime / the ProviderSpec it "
            f"returns — or register the site in contracts/provider_registry.yaml "
            f"grandfathered_base_url_sites. A scattered endpoint drifts from the "
            f"registry; missing one on a base_url change routes half the calls to "
            f"the wrong endpoint (cost mis-attribution)."
        )
    return failures


def _check_new_provider_in_deprecated_copy(
    usages: list[ProviderSpecUsage], registry: dict[str, Any]
) -> list[str]:
    """Fail rule (b): a NEW provider added to a deprecated registry copy.

    A ProviderSpec(name="X") inside a deprecated registry module where X is not
    already a registered provider = re-growing a second authority. ProviderSpec
    outside the registry files, or for an already-registered provider, passes.
    """
    deprecated_modules: set[str] = registry["deprecated_modules"]
    registered: set[str] = registry["registered_providers"]
    failures: list[str] = []
    seen: set[tuple[str, int, str]] = set()
    for usage in usages:
        if usage.path not in deprecated_modules:
            continue  # only the deprecated copies are second-authority surfaces
        if usage.provider_name in registered:
            continue  # editing an existing entry of the copy is fine
        key = (usage.path, usage.lineno, usage.provider_name)
        if key in seen:
            continue
        seen.add(key)
        failures.append(
            f"{usage.path}:{usage.lineno}: NEW provider '{usage.provider_name}' "
            f"added to a DEPRECATED registry copy. Add it to the canonical "
            f"registry only ({registry['canonical_module']} + "
            f"contracts/provider_registry.yaml) — a new provider in a deprecated "
            f"copy re-grows a second authority (the very病灶 this gate收权 closes)."
        )
    return failures


def evaluate_provider_usages(
    base_urls: list[BaseUrlUsage],
    specs: list[ProviderSpecUsage],
    registry: dict[str, Any],
) -> tuple[bool, str]:
    """Apply the two fail rules to collected usages."""
    failures: list[str] = []
    failures.extend(_check_new_hardcoded_base_urls(base_urls, registry))
    failures.extend(_check_new_provider_in_deprecated_copy(specs, registry))

    if failures:
        unique = list(dict.fromkeys(failures))
        return False, "provider-registry-guard: failed\n" + "\n".join(unique)

    if not (base_urls or specs):
        return True, "provider-registry-guard: no provider base_url / spec in changed files"
    return True, (
        "provider-registry-guard: passed | "
        f"base_urls={len(base_urls)} provider_specs={len(specs)} (all registered)"
    )


def _read_changed_files(changed_files: list[str]) -> list[tuple[str, str]]:
    """Read in-scope production files into (path, body) pairs."""
    pairs: list[tuple[str, str]] = []
    for raw in changed_files:
        path = raw.strip()
        if not path or not _IN_SCOPE_PATH_RE.match(path):
            continue
        if _OUT_OF_SCOPE_PATH_RE.search(path):
            continue
        if not path.endswith(".py"):
            continue
        full = REPO_ROOT / path
        if not full.exists() or not full.is_file():
            continue
        try:
            body = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        pairs.append((path, body))
    return pairs


def evaluate_provider_registry(changed_files: list[str]) -> tuple[bool, str]:
    """Changed-files entry point — the hook contract-guard wires into (pending hunk).

    Reads each in-scope changed file, collects base_url / ProviderSpec usages,
    evaluates the two fail rules. Mirrors the other ``evaluate_*`` guards.
    """
    pairs = _read_changed_files(changed_files)
    if not pairs:
        return True, "provider-registry-guard: no in-scope production source changed"
    registry = load_provider_registry()
    base_urls = collect_base_url_usages(pairs)
    specs = collect_provider_spec_usages(pairs)
    return evaluate_provider_usages(base_urls, specs, registry)


def _git_current_candidate_files() -> list[str]:
    files: set[str] = set()
    for command in (
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        files.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(files)


# M2: scan-all glob set, run INSIDE the scanner via subprocess (a list arg, never
# shell-word-split). The CI used ``$(git ls-files …)`` unquoted, so a tracked path
# containing a space would be split into two bogus arguments. ``--all`` lets CI call
# the scanner with no shell expansion (``python check_provider_registry.py --all``).
_SCAN_ALL_GLOBS = ("deeptutor/**/*.py", "scripts/**/*.py")


def _git_tracked_in_scope_files() -> list[str]:
    """Return tracked in-scope files via the scanner's own ``git ls-files``.

    Uses a subprocess LIST argument (no shell), so a path with a space stays one
    argument — closing the M2 unquoted-``$(git ls-files)`` word-split hole.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", *_SCAN_ALL_GLOBS],
        check=True,
        capture_output=True,
        text=True,
    )
    return [p for p in result.stdout.split("\0") if p]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when code hardcodes a new provider base_url / adds a new "
        "provider to a deprecated registry copy (防新增旁路 / 防第二权威再生)."
    )
    parser.add_argument(
        "files", nargs="*", help="Explicit changed files. If omitted, git diff is used."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan ALL tracked in-scope files via the scanner's own git ls-files "
        "(no shell word-splitting on spaced paths — the CI-safe full-repo mode).",
    )
    args = parser.parse_args(argv)

    if args.all:
        changed = _git_tracked_in_scope_files()
    else:
        changed = args.files or _git_current_candidate_files()
    ok, message = evaluate_provider_registry(changed)
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
