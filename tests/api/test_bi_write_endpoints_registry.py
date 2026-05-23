"""Contract tests for the WRITE_ENDPOINTS registry (Round 4 S2).

This is the enforcement layer that turns ``deeptutor.contracts.bi_v2_write_endpoints``
from a documentation file into a binding contract:

  * The generated TypeScript mirror must be byte-identical with what the
    codegen script would produce now. If a developer edits the registry but
    forgets to regenerate, CI breaks here.
  * Every endpoint marked ``requires_idempotency=True`` must have a
    corresponding router enforcement and a backend dedup pytest. The matrix
    is iterated automatically so a new entry without enforcement immediately
    fails (one place to update, multiple invariants to satisfy).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.contracts.bi_v2_write_endpoints import WRITE_ENDPOINTS, WriteEndpoint


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_write_endpoints_ts_in_sync() -> None:
    """Codegen drift guard. Run `python -m scripts.gen_bi_write_endpoints_ts`
    after editing the registry — otherwise this test fails."""
    from scripts.gen_bi_write_endpoints_ts import OUTPUT_PATH, render_module

    expected = render_module()
    actual = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
    assert actual == expected, (
        "web/lib/bi-v2-write-endpoints.generated.ts is out of sync with "
        "deeptutor/contracts/bi_v2_write_endpoints.py. "
        "Run: python -m scripts.gen_bi_write_endpoints_ts"
    )


def test_write_endpoints_have_router_enforcement() -> None:
    """Each requires_idempotency endpoint MUST appear in a router file with a
    Header(alias='X-Idempotency-Key') read **IN THE SAME FILE** as the path
    template — not anywhere in the aggregated router corpus. Round 5 M4: the
    aggregated-grep approach (used in Round 4) gave false-positives once any
    router file read X-Idempotency-Key, because unrelated endpoints in other
    files would silently pass. Per-file scan closes that gap.
    """
    router_files = list((REPO_ROOT / "deeptutor" / "api" / "routers").rglob("*.py"))
    file_contents = {p: p.read_text(encoding="utf-8") for p in router_files}

    failures: list[str] = []
    for endpoint in WRITE_ENDPOINTS:
        if not endpoint.requires_idempotency:
            continue
        suffix = endpoint.path_template.split("/api/v1")[-1].rsplit("/", 1)[-1]
        matching_files = [p for p, c in file_contents.items() if suffix in c]
        if not matching_files:
            failures.append(
                f"{endpoint.key}: path suffix '{suffix}' not found in any router file"
            )
            continue
        # Every file that hosts the path must also read X-Idempotency-Key.
        for path in matching_files:
            if "X-Idempotency-Key" not in file_contents[path]:
                failures.append(
                    f"{endpoint.key}: {path.relative_to(REPO_ROOT)} hosts the path "
                    "but does not read X-Idempotency-Key — header is placebo here"
                )

    assert not failures, "Router enforcement missing:\n" + "\n".join(failures)


@pytest.mark.parametrize("endpoint", [e for e in WRITE_ENDPOINTS if e.requires_idempotency])
def test_idempotency_endpoint_has_backend_dedup_test(endpoint: WriteEndpoint) -> None:
    """For every requires_idempotency endpoint, at least one pytest in
    ``tests/`` must exercise the dedup path (same key → no second audit /
    same audit_id returned). Without this, dedup is untested.

    Detection heuristic: scan tests/ for the endpoint key string + an
    'idempotency' keyword in the same file.
    """
    test_files = list((REPO_ROOT / "tests").rglob("*.py"))
    matches: list[Path] = []
    for path in test_files:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if endpoint.audit_action in content and "idempotency" in content.lower():
            matches.append(path)

    assert matches, (
        f"No backend dedup test found for {endpoint.key} "
        f"(audit_action={endpoint.audit_action}). "
        "At least one test must reference both the audit_action and 'idempotency'."
    )
