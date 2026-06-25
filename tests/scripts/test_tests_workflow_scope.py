from scripts.ci.tests_workflow_scope import classify


def test_workflow_change_selects_all_domains() -> None:
    assert classify([".github/workflows/tests.yml"]) == {
        "governance": True,
        "backend": True,
        "frontend": True,
        "wx": True,
        "yousen": True,
    }


def test_backend_change_selects_backend_and_governance_only() -> None:
    assert classify(["deeptutor/runtime/orchestrator.py"]) == {
        "governance": True,
        "backend": True,
        "frontend": False,
        "wx": False,
        "yousen": False,
    }


def test_frontend_change_selects_frontend_only() -> None:
    assert classify(["web/app/page.tsx"]) == {
        "governance": False,
        "backend": False,
        "frontend": True,
        "wx": False,
        "yousen": False,
    }


def test_docs_only_change_selects_no_domain_jobs() -> None:
    assert classify(["docs/runbook/ci-runtime-smoke-guardrails.md"]) == {
        "governance": False,
        "backend": False,
        "frontend": False,
        "wx": False,
        "yousen": False,
    }


def test_unified_turn_contract_doc_selects_governance_only() -> None:
    assert classify(["docs/zh/guide/unified-turn-contract.md"]) == {
        "governance": True,
        "backend": False,
        "frontend": False,
        "wx": False,
        "yousen": False,
    }
