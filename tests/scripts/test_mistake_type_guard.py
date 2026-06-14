"""G3 — mistake_type emit-site register-before-use guard (static layer).

mistake_type literals hard-coded in the grading emit modules must be a registered
code in deeptutor/contracts/mistake_codes.py. LLM-produced mistake_type at runtime
is a separate normalization concern (audit G3 layer 2).
"""

from __future__ import annotations

from pathlib import Path
import textwrap

from deeptutor.contracts.mistake_codes import (
    MISTAKE_CODE_REGISTRY,
    is_known_mistake_code,
)
from scripts.check_contract_guard import evaluate_emitted_mistake_types


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")


def test_passes_on_real_tree() -> None:
    ok, message = evaluate_emitted_mistake_types()
    assert ok, message


def test_registry_contents() -> None:
    assert is_known_mistake_code("omitted")
    assert is_known_mistake_code("shape_stub_no_quality_judgment")
    assert not is_known_mistake_code("bogus_mistake")
    assert {"omitted", "wrong_content", "list_incomplete"} <= MISTAKE_CODE_REGISTRY


def test_unregistered_literal_fails(tmp_path: Path) -> None:
    _write(
        tmp_path / "deeptutor/services/construction_grading/rubric_grader_v1.py",
        'X = {"mistake_type": "totally_new_mistake"}\n',
    )
    ok, message = evaluate_emitted_mistake_types(tmp_path)
    assert not ok
    assert "totally_new_mistake" in message
    assert "rubric_grader_v1.py" in message


def test_reader_and_passthrough_not_captured(tmp_path: Path) -> None:
    _write(
        tmp_path / "deeptutor/services/construction_grading/rubric_grader_v1.py",
        '''
        def f(v):
            mt = str(v.get("mistake_type") or "")
            return {"mistake_type": str(v.get("mistake_type") or "")}
        ''',
    )
    ok, message = evaluate_emitted_mistake_types(tmp_path)
    assert ok  # reader comparison + str() pass-through must not be flagged
    assert "no hard-coded" in message


def test_registered_kwarg_and_constant_pass(tmp_path: Path) -> None:
    _write(
        tmp_path / "deeptutor/services/construction_grading/rubric_grader_v1.py",
        '''
        MISTAKE_WRONG = "wrong_content"

        def g():
            return dict(mistake_type="omitted")
        ''',
    )
    ok, message = evaluate_emitted_mistake_types(tmp_path)
    assert ok, message
    assert "wrong_content" in message
