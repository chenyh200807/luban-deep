"""Meta-gate tests: the governance scanner catalog is complete + every pr_gate is wired.

Proves contracts/registries.yaml + check_registries_meta.py enforce, deterministically:
- the live repo passes (all scanners cataloged, all pr_gate scanners in tests.yml);
- an UNCATALOGED governance scanner fails (register-before-use for the gates themselves);
- a pr_gate scanner missing from CI fails (no dark pr_gate).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

import check_registries_meta as M  # noqa: E402


def test_live_repo_meta_gate_passes() -> None:
    ok, failures = M.evaluate_registries_meta()
    assert ok, f"meta-gate must pass on the live repo; failures:\n" + "\n".join(failures)


def test_every_discovered_scanner_is_cataloged() -> None:
    import yaml
    catalog = yaml.safe_load(M.REGISTRY.read_text(encoding="utf-8"))
    cataloged = {s["script"] for s in catalog["scanners"]}
    for script in M._discover_scanners():
        assert script in cataloged, f"governance scanner {script} is not cataloged in registries.yaml"


def test_uncataloged_scanner_would_fail(tmp_path, monkeypatch) -> None:
    # simulate a new scanner appearing on disk but not in the catalog -> meta-gate must fail
    monkeypatch.setattr(M, "_discover_scanners", lambda: {"scripts/check_brand_new_unregistered.py"})
    ok, failures = M.evaluate_registries_meta()
    assert ok is False
    assert any("UNCATALOGED" in f and "check_brand_new_unregistered" in f for f in failures)


def test_pr_gate_must_be_wired_into_ci() -> None:
    import yaml
    catalog = yaml.safe_load(M.REGISTRY.read_text(encoding="utf-8"))
    ci_text = M.CI_WORKFLOW.read_text(encoding="utf-8")
    for s in catalog["scanners"]:
        if s.get("enforcement") == "pr_gate":
            assert Path(s["script"]).name in ci_text, f"pr_gate {s['script']} not wired into tests.yml"
