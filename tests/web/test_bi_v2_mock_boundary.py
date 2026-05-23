"""Round 4 S4 — source-level guard that every BI v2 mock fixture is dev-only.

Belt-and-suspenders with ``web/scripts/check_mock_boundary.mjs`` (which scans
the built ``.next/static/chunks``). This pytest runs in seconds and catches
regressions at the source level — if a developer ships a new ``MOCK_*`` const
without the ``NODE_ENV === 'production'`` guard, CI fails before the build
artifact check ever runs.

The full contract:

  * Every ``export const MOCK_*`` / ``ANOMALIES`` / ``AUDIT_ENTRIES`` /
    ``FEEDBACK_ITEMS`` / ``EXPORT_JOBS`` / ``ORDERS`` / ``LEDGER`` /
    ``PACKAGES`` declaration in ``web/app/(workspace)/bi/_v2/`` must mention
    ``process.env.NODE_ENV`` on the same logical line.
  * The build-time grep script ``web/scripts/check_mock_boundary.mjs`` must
    exist and be wired into ``web/package.json`` as ``check:mock-boundary``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V2_ROOT = REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_v2"
PACKAGE_JSON = REPO_ROOT / "web" / "package.json"
MOCK_BOUNDARY_SCRIPT = REPO_ROOT / "web" / "scripts" / "check_mock_boundary.mjs"

# Identifiers whose declaration must be guarded by NODE_ENV. Adding a new mock
# fixture? Add it here and in `check_mock_boundary.mjs::FORBIDDEN_LITERALS`.
GUARDED_IDENTIFIERS = (
    "MOCK_MEMBERS",
    "MOCK_BUNDLE",
    "MOCK_SESSIONS",
    "ANOMALIES",
    "AUDIT_ENTRIES",
    "FEEDBACK_ITEMS",
    "EXPORT_JOBS",
    "ORDERS",
    "LEDGER",
    "PACKAGES",
    "OPS_TILES",
)


def _v2_source_files() -> list[Path]:
    return [p for p in V2_ROOT.rglob("*") if p.is_file() and p.suffix in {".ts", ".tsx"}]


def test_mock_fixtures_are_dev_only() -> None:
    """Each guarded identifier's declaration must contain `process.env.NODE_ENV`
    on the same statement so production builds get an empty array."""
    offenders: list[str] = []
    for path in _v2_source_files():
        if path.name.endswith(".generated.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        for ident in GUARDED_IDENTIFIERS:
            # Match an export/const declaration introducing the identifier.
            pattern = re.compile(
                rf"^(?:export\s+)?const\s+{re.escape(ident)}\b[^=]*=\s*(.+?)(?=^(?:export\s+)?const\s|\Z)",
                re.MULTILINE | re.DOTALL,
            )
            for m in pattern.finditer(text):
                body = m.group(1)
                if "process.env.NODE_ENV" not in body:
                    rel = path.relative_to(V2_ROOT).as_posix()
                    offenders.append(f"{rel} :: {ident}")
                    break

    assert not offenders, (
        "BI v2 mock fixtures must be dev-only (Round 4 S4 M-B). "
        "Wrap with `process.env.NODE_ENV === 'production' ? [] : [...]` so "
        "Next.js + Terser DCEs the literal in production. Offenders:\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )


def test_mock_boundary_check_wired_into_package_json() -> None:
    """The build-time grep must be runnable via `npm run check:mock-boundary`.
    Without this CI hook the source-level guard above is the only defense and
    a sufficiently clever developer can still ship a mock by importing from
    a non-_v2 path."""
    assert MOCK_BOUNDARY_SCRIPT.exists(), (
        f"Expected {MOCK_BOUNDARY_SCRIPT.relative_to(REPO_ROOT)} to exist"
    )

    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    scripts = package.get("scripts", {})
    assert "check:mock-boundary" in scripts, (
        "package.json must expose `check:mock-boundary` script "
        "(was added in Round 4 S4)."
    )
    assert "check_mock_boundary.mjs" in scripts["check:mock-boundary"], (
        "`check:mock-boundary` must invoke check_mock_boundary.mjs"
    )
    # Also assert the build:check chain so CI can run "build then check".
    assert "build:check" in scripts, (
        "package.json must expose `build:check` (build + check:mock-boundary)."
    )
