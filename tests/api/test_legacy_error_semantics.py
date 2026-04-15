from __future__ import annotations

from pathlib import Path


LEGACY_FILES = [
    "deeptutor/api/routers/notebook.py",
    "deeptutor/api/routers/plugins_api.py",
    "deeptutor/api/routers/guide.py",
    "deeptutor/api/routers/tutorbot.py",
    "deeptutor/api/routers/question.py",
    "deeptutor/api/routers/solve.py",
]


def test_legacy_router_client_error_paths_do_not_return_raw_exception_text() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text_by_file = {rel: (repo_root / rel).read_text(encoding="utf-8") for rel in LEGACY_FILES}

    for rel, text in text_by_file.items():
        assert "raise HTTPException(status_code=500, detail=str(" not in text, rel
        assert 'detail": str(' not in text, rel
        assert 'content": str(' not in text, rel

    assert "format_exception_message(e)" not in text_by_file["deeptutor/api/routers/question.py"]
    assert 'error_holder["detail"] = str(exc)' not in text_by_file["deeptutor/api/routers/plugins_api.py"]
