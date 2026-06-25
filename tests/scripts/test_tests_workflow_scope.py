from scripts.ci.tests_workflow_scope import classify, secret_scan_files


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


def test_secret_scan_files_keep_source_and_skip_generated_heavy_inputs() -> None:
    assert secret_scan_files(
        [
            "deeptutor/runtime/orchestrator.py",
            ".github/workflows/tests.yml",
            "docs/runbook/ci-runtime-smoke-guardrails.md",
            ".secrets.baseline",
            "artifacts/student_army_eval.json",
            "tmp/diagnostic-report-target-state.png",
            "docs/营销/鲁班智考销售训练手册.docx",
            "deeptutor/services/construction_grading/runtime_supply/v/foo.json",
            "deeptutor/services/taxonomy/compiled/construction.json",
            "web/public/luban-preview/c02/C02_progress_payment.lesson.mp3",
        ]
    ) == [
        "deeptutor/runtime/orchestrator.py",
        ".github/workflows/tests.yml",
        "docs/runbook/ci-runtime-smoke-guardrails.md",
    ]
