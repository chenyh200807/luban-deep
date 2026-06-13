"""DB-registry policy gate — "registered-or-you-can't-connect" for raw DB access.

This is the machine enforcement of the RESOURCE_GOVERNANCE_FIX_PLAN root-cause
business fact: *every data write / connection must be machine-confirmable as
registered in the single canonical list — which fact lands in which database /
table, and who may write*. The documentary rule becomes a deterministic CI gate
here, wired into the SAME contract-guard runner (NOT a new governance system).

The registry lives in ``contracts/db_registry.yaml`` (single canonical list).
This script reads it and scans changed code for raw-connection / write usage,
failing on three conditions:

  (a) UNREGISTERED RAW CONNECTION — a ``psycopg.connect`` / ``psycopg2.connect``
      call in a production file whose path is NOT in the registry's grandfathered
      ``raw_connection_sites`` and is NOT the approved connection factory module.
      This is the止血 (stop-the-bleed) rule: new ad-hoc connections cannot slip
      in. (Existing存量 sites are grandfathered and migrated by work order.)

  (b) WRITE TO AN UNREGISTERED TABLE — an ``insert into`` / ``update`` /
      ``delete from`` / ``insert into … on conflict`` statement targeting a table
      that the registry's ``tables`` list does not register. Selecting WHICH
      database a fact lands in is exactly what was unchecked; a write to a table
      no one declared canonical is the cross-db / cross-project silent-write hole.

  (c) UNDECLARED DB-URL ENV — a ``*_DATABASE_URL`` / ``DB_URL`` / ``DATABASE_URL``
      env referenced in production code that is not declared on any registered
      database (as ``url_envs`` or ``fallback_url_envs``). A new url env that no
      database claims means a new (unregistered) database target can be selected.

Scope (deliberately not bureaucratic): only RAW psycopg connections and direct
SQL writes are in scope. Supabase REST / PostgREST calls (SUPABASE_URL + key over
HTTP) are RLS-governed and explicitly out of scope. Tests are out of scope.

Deterministic and pure: no LLM, no network, no DB. It reads files and applies
regexes, mirroring scripts/check_schema_registry.py and
scripts/check_contract_guard.py.

────────────────────────────────────────────────────────────────────────────────────────
PENDING HUNK — wiring into scripts/check_contract_guard.py
────────────────────────────────────────────────────────────────────────────────────────
scripts/check_contract_guard.py currently has UNCOMMITTED parallel WIP, so this
guard is NOT wired into its main() here (no dirty-file dependency / no carrying of
parallel work). Apply the hunk below when that file is clean (or fold it into the
next contract-guard commit). It is intentionally additive and order-independent:

  # add near the other guard imports at top of scripts/check_contract_guard.py:
  from scripts.check_db_registry import evaluate_db_registry  # noqa: E402

  # inside main(), after the ws guard prints, before the final return:
  db_ok, db_message = evaluate_db_registry(changed_files)
  db_stream = sys.stdout if db_ok else sys.stderr
  print(db_message, file=db_stream)

  # and extend the final boolean:
  return 0 if (ok and code_ok and node_ok and lifecycle_ok
               and upstream_ok and ws_ok and db_ok) else 1

``evaluate_db_registry(changed_files)`` is the changed-files entry point provided
below for exactly this wiring (reads each changed file, runs collect+evaluate).
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

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "contracts" / "db_registry.yaml"

# Raw Postgres connection call. We match psycopg / psycopg2 .connect( — the exact
# RLS-bypassing surface the registry governs. (Supabase REST is out of scope.)
_RAW_CONNECT_RE = re.compile(r"\bpsycopg2?\.connect\s*\(")

# I3(a): aliased import detection. ``import psycopg as pg`` / ``import psycopg2 as db``
# rebinds the module to an arbitrary name, after which ``pg.connect(`` is a raw
# connection the un-aliased regex above could not see. We scan each file for these
# alias bindings and additionally match ``<alias>.connect(`` for every alias found.
_PSYCOPG_ALIAS_IMPORT_RE = re.compile(r"^\s*import\s+psycopg2?\s+as\s+([A-Za-z_]\w*)", re.MULTILINE)

# I3(c): from-import detection. ``from psycopg import connect`` binds the connect
# CALLABLE to a bare name (``connect`` or ``connect as <alias>``), after which a
# bare ``connect(`` is a raw connection neither ``psycopg.connect`` nor the alias
# matcher could see. We capture the import target list and resolve the bound name(s).
_PSYCOPG_FROM_IMPORT_RE = re.compile(
    r"^\s*from\s+psycopg2?\s+import\s+(.+)$", re.MULTILINE
)

# Direct SQL write statements targeting a table. Captures the table identifier
# after the verb. Case-insensitive; tolerates schema-qualified names.
#
# To avoid matching English prose ("Update a session", "delete from queue done")
# in docstrings / log strings, every form requires a real SQL CONTINUATION token
# right after the table name — the clause that prose never has:
#   insert into <table> (        -> column list / VALUES / SELECT
#   delete from <table> where|;|"|'|)|\n   -> WHERE clause or end of statement
#   update <table> set           -> the SET clause (also excludes ON CONFLICT … DO
#                                   UPDATE SET via the (?<!do\s) lookbehind)
#   I3(b):
#   copy <table> from            -> bulk ingest (copy_expert / COPY … FROM STDIN);
#                                   a write surface the original rule entirely missed
#   truncate [table] <table>     -> destructive table-empty; the (?:table\s+)? makes
#                                   the TABLE keyword optional (both PG forms)
# This keeps the rule a precise SQL detector, not a prose matcher.
_TABLE = r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
_WRITE_STMT_RE = re.compile(
    r"\b(?:"
    rf"insert\s+into\s+{_TABLE}\s*[(\"']"
    rf"|delete\s+from\s+{_TABLE}\s*(?:where\b|using\b|[;\"')]|$)"
    rf"|(?<!do\s)update\s+{_TABLE}\s+set\b"
    rf"|copy\s+{_TABLE}\s*(?:\([^)]*\)\s*)?from\s+(?:stdin\b|program\b|['\"(])"
    rf"|truncate\s+(?:table\s+)?{_TABLE}\s*(?:cascade\b|restart\b|continue\b|[;\"')]|$)"
    r")",
    re.IGNORECASE,
)

# SQL keywords that can follow a write verb but are NEVER a table name. ``set``
# appears in ``DO UPDATE SET``; the others guard against partial-line matches.
_NON_TABLE_TOKENS = frozenset({"set", "where", "values", "returning", "from", "into"})

# The write-rule only governs files that actually open a raw Postgres connection
# (the registry's scope is RLS-bypassing raw psycopg writes). A SQLite ``DELETE
# FROM`` or an ORM call in a non-psycopg file is out of scope. A file is a raw-PG
# file if it imports psycopg (incl. ``import psycopg as X`` AND ``from psycopg
# import …``) or calls psycopg(2).connect. I3(c): the ``from psycopg2? import``
# alternative is REQUIRED — without it a from-import file failed this gate, so the
# whole SQL-write scan was skipped for it (the deeper half of the I3c bypass).
_PSYCOPG_FILE_RE = re.compile(
    r"\bimport\s+psycopg2?\b|\bfrom\s+psycopg2?\s+import\b|\bpsycopg2?\.connect\s*\("
)

# DB-url env reference: os.getenv("X_DATABASE_URL") / os.environ["DB_URL"] / etc.
# Only env NAMES that look like a DB url selector (end in _DB_URL / _DATABASE_URL,
# or are exactly DB_URL / DATABASE_URL). SUPABASE_URL (REST base) is excluded —
# it is the PostgREST endpoint, not a raw-connection url.
_DB_URL_ENV_RE = re.compile(
    r"""(?:getenv|environ(?:\.get)?)\s*[\(\[]\s*["']"""
    r"""([A-Z][A-Z0-9_]*(?:_DB_URL|_DATABASE_URL)|DB_URL|DATABASE_URL)["']"""
)

# Restrict to production source. Tests, fixtures, and the registry itself are
# out of scope. Scripts/ are in scope (maintenance scripts do raw writes).
_IN_SCOPE_PATH_RE = re.compile(r"^(?:deeptutor/|scripts/)")
_OUT_OF_SCOPE_PATH_RE = re.compile(r"(?:^|/)tests?/|(?:^|/)conftest\.py$|_test\.py$|/fixtures?/")


@dataclass(frozen=True)
class ConnectUsage:
    """One raw-connection call found in a scanned file."""

    path: str
    lineno: int
    snippet: str


@dataclass(frozen=True)
class WriteUsage:
    """One direct SQL write found in a scanned file (with the target table)."""

    path: str
    lineno: int
    table: str
    snippet: str


@dataclass(frozen=True)
class EnvUsage:
    """One DB-url env reference found in a scanned file."""

    path: str
    lineno: int
    env_name: str


def load_db_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load + index ``contracts/db_registry.yaml`` into lookup structures."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    databases = payload.get("databases")
    if not isinstance(databases, list) or not databases:
        raise ValueError("contracts/db_registry.yaml must define a non-empty databases list")

    grandfathered_sites: set[str] = set()
    declared_url_envs: set[str] = set()
    for db in databases:
        if not isinstance(db, dict) or "name" not in db:
            raise ValueError(f"db_registry database entry missing name: {db!r}")
        for env in (db.get("url_envs") or []):
            declared_url_envs.add(str(env))
        for env in (db.get("fallback_url_envs") or []):
            declared_url_envs.add(str(env))
        for site in (db.get("raw_connection_sites") or []):
            if isinstance(site, dict) and site.get("path"):
                grandfathered_sites.add(str(site["path"]))

    registered_tables: set[str] = set()
    for table in (payload.get("tables") or []):
        if isinstance(table, dict) and table.get("name"):
            registered_tables.add(_normalize_table(str(table["name"])))

    factory = payload.get("connection_factory") or {}
    factory_module = str(factory.get("module") or "")

    return {
        "grandfathered_sites": grandfathered_sites,
        "declared_url_envs": declared_url_envs,
        "registered_tables": registered_tables,
        "factory_module": factory_module,
    }


def _normalize_table(name: str) -> str:
    """Normalize a table identifier for comparison (lowercase; keep schema)."""
    return name.strip().lower()


def _psycopg_connect_bindings(body: str) -> set[str]:
    """Bound names for psycopg's connect via ``from psycopg import connect[ as X]``.

    A bare ``connect(`` is only a raw connection when the file imported it FROM
    psycopg; we resolve the bound name(s) so an aliased ``c(url)`` is caught too.
    This gate is why a bare ``connect(`` does not false-positive on an unrelated
    function named connect (websocket / signal connect) in files with no such import.
    """
    names: set[str] = set()
    for raw in _PSYCOPG_FROM_IMPORT_RE.findall(body):
        for target in raw.strip().strip("()").split(","):
            parts = target.strip().split()
            if not parts or parts[0] != "connect":
                continue
            # ``connect`` or ``connect as <alias>``
            if len(parts) >= 3 and parts[1] == "as":
                names.add(parts[2])
            else:
                names.add("connect")
    return names


def collect_connect_usages(files: list[tuple[str, str]]) -> list[ConnectUsage]:
    """Scan ``(path, body)`` pairs for raw psycopg.connect calls.

    I3(a): resolves ``import psycopg as <alias>`` and matches ``<alias>.connect(``.
    I3(c): resolves ``from psycopg import connect[ as <name>]`` and matches the
    bare bound call ``<name>(`` — neither of which the bare ``psycopg.connect``
    regex could see.
    """
    usages: list[ConnectUsage] = []
    for path, body in files:
        if not body:
            continue
        # Build the per-file alias table (e.g. {"pg", "db"}) and an alias-aware
        # connect matcher so ``pg.connect(`` is detected as a raw connection.
        aliases = set(_PSYCOPG_ALIAS_IMPORT_RE.findall(body))
        alias_connect_re: re.Pattern[str] | None = None
        if aliases:
            alt = "|".join(re.escape(a) for a in sorted(aliases))
            alias_connect_re = re.compile(rf"\b(?:{alt})\.connect\s*\(")
        # I3(c): from-import bound names → match the bare bound call ``name(``.
        # The ``(?<![\w.])`` lookbehind keeps ``self.connect(`` / ``pg.connect(``
        # (already covered above) from double-matching as a bare call.
        bound = _psycopg_connect_bindings(body)
        bound_connect_re: re.Pattern[str] | None = None
        if bound:
            balt = "|".join(re.escape(b) for b in sorted(bound))
            bound_connect_re = re.compile(rf"(?<![\w.])(?:{balt})\s*\(")
        for lineno, line in enumerate(body.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if (
                _RAW_CONNECT_RE.search(line)
                or (alias_connect_re is not None and alias_connect_re.search(line))
                or (bound_connect_re is not None and bound_connect_re.search(line))
            ):
                usages.append(ConnectUsage(path=path, lineno=lineno, snippet=stripped[:120]))
    return usages


def collect_write_usages(files: list[tuple[str, str]]) -> list[WriteUsage]:
    """Scan ``(path, body)`` pairs for direct SQL write statements.

    Only files that open a raw Postgres connection are scanned — the registry
    governs RLS-bypassing raw-psycopg writes, not SQLite / ORM / prose elsewhere.
    """
    usages: list[WriteUsage] = []
    for path, body in files:
        if not body or not _PSYCOPG_FILE_RE.search(body):
            continue
        for lineno, line in enumerate(body.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for match in _WRITE_STMT_RE.finditer(line):
                # exactly one of the five alternation groups captured the table
                # (insert / delete / update / copy / truncate).
                raw_table = (
                    match.group(1)
                    or match.group(2)
                    or match.group(3)
                    or match.group(4)
                    or match.group(5)
                )
                table = _normalize_table(raw_table)
                if table in _NON_TABLE_TOKENS:
                    continue
                usages.append(
                    WriteUsage(path=path, lineno=lineno, table=table, snippet=stripped[:120])
                )
    return usages


def collect_env_usages(files: list[tuple[str, str]]) -> list[EnvUsage]:
    """Scan ``(path, body)`` pairs for DB-url env references."""
    usages: list[EnvUsage] = []
    for path, body in files:
        if not body:
            continue
        for lineno, line in enumerate(body.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for match in _DB_URL_ENV_RE.finditer(line):
                usages.append(EnvUsage(path=path, lineno=lineno, env_name=match.group(1)))
    return usages


def _check_unregistered_connections(
    usages: list[ConnectUsage], registry: dict[str, Any]
) -> list[str]:
    """Fail rule (a): a raw connect in a file not grandfathered / not the factory."""
    grandfathered: set[str] = registry["grandfathered_sites"]
    factory_module: str = registry["factory_module"]
    failures: list[str] = []
    for usage in usages:
        if usage.path == factory_module:
            continue  # the connection factory is THE approved place to connect
        if usage.path in grandfathered:
            continue  # existing存量 site, migrated by work order (not new ad-hoc)
        failures.append(
            f"{usage.path}:{usage.lineno}: unregistered raw DB connection "
            f"(psycopg.connect). Route it through the connection factory "
            f"({factory_module or 'deeptutor/services/db/connection_factory.py'}) "
            f"or register the site in contracts/db_registry.yaml "
            f"databases[].raw_connection_sites. ({usage.snippet})"
        )
    return failures


def _check_unregistered_table_writes(
    usages: list[WriteUsage], registry: dict[str, Any]
) -> list[str]:
    """Fail rule (b): a write to a table the registry does not register."""
    registered: set[str] = registry["registered_tables"]
    failures: list[str] = []
    for usage in usages:
        table = usage.table
        # A write that targets a registered table (with OR without its schema
        # prefix) passes. We compare both the full identifier and its bare name.
        bare = table.rsplit(".", 1)[-1]
        registered_bare = {t.rsplit(".", 1)[-1] for t in registered}
        if table in registered or bare in registered_bare:
            continue
        failures.append(
            f"{usage.path}:{usage.lineno}: write to UNREGISTERED table '{usage.table}'. "
            f"Register it in contracts/db_registry.yaml tables[] with its database, "
            f"canonical_for_fact, and writable_by — or this fact may be silently "
            f"written to the wrong database. ({usage.snippet})"
        )
    return failures


def _check_undeclared_db_url_envs(
    usages: list[EnvUsage], registry: dict[str, Any]
) -> list[str]:
    """Fail rule (c): a DB-url env not declared on any registered database."""
    declared: set[str] = registry["declared_url_envs"]
    failures: list[str] = []
    seen: set[tuple[str, int, str]] = set()
    for usage in usages:
        if usage.env_name in declared:
            continue
        key = (usage.path, usage.lineno, usage.env_name)
        if key in seen:
            continue
        seen.add(key)
        failures.append(
            f"{usage.path}:{usage.lineno}: DB-url env '{usage.env_name}' is not "
            f"declared on any registered database. Add it to a database's url_envs "
            f"or fallback_url_envs in contracts/db_registry.yaml so the target "
            f"database is machine-confirmed."
        )
    return failures


def evaluate_db_usages(
    connects: list[ConnectUsage],
    writes: list[WriteUsage],
    envs: list[EnvUsage],
    registry: dict[str, Any],
) -> tuple[bool, str]:
    """Apply the three fail rules to collected usages."""
    failures: list[str] = []
    failures.extend(_check_unregistered_connections(connects, registry))
    failures.extend(_check_unregistered_table_writes(writes, registry))
    failures.extend(_check_undeclared_db_url_envs(envs, registry))

    if failures:
        unique = list(dict.fromkeys(failures))
        return False, "db-registry-guard: failed\n" + "\n".join(unique)

    if not (connects or writes or envs):
        return True, "db-registry-guard: no raw DB connection / write / db-url env in changed files"
    return True, (
        "db-registry-guard: passed | "
        f"raw_connects={len(connects)} writes={len(writes)} db_url_envs={len(envs)} "
        "(all registered)"
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
        full = REPO_ROOT / path
        if not full.exists() or not full.is_file():
            continue
        try:
            body = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        pairs.append((path, body))
    return pairs


def evaluate_db_registry(changed_files: list[str]) -> tuple[bool, str]:
    """Changed-files entry point — the hook contract-guard wires into (pending hunk).

    Reads each in-scope changed file, collects raw-connection / write / db-url-env
    usages, evaluates the three fail rules. Mirrors the other ``evaluate_*`` guards.
    """
    pairs = _read_changed_files(changed_files)
    if not pairs:
        return True, "db-registry-guard: no in-scope production source changed"
    registry = load_db_registry()
    connects = collect_connect_usages(pairs)
    writes = collect_write_usages(pairs)
    envs = collect_env_usages(pairs)
    return evaluate_db_usages(connects, writes, envs, registry)


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
# the scanner with no shell expansion (``python check_db_registry.py --all``).
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
        description="Fail when code opens an unregistered raw DB connection / writes an "
        "unregistered table / references an undeclared DB-url env."
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
    ok, message = evaluate_db_registry(changed)
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
