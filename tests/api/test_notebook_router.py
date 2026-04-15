from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
from deeptutor.api.dependencies import AuthContext, get_current_user
notebook_router = importlib.import_module(
    "deeptutor.api.routers.question_notebook"
).router
sessions_router = importlib.import_module("deeptutor.api.routers.sessions").router

from deeptutor.services.session.sqlite_store import SQLiteSessionStore, build_user_owner_key


def _build_app(store: SQLiteSessionStore) -> FastAPI:
    app = FastAPI()
    app.include_router(notebook_router, prefix="/api/v1/question-notebook")
    app.include_router(sessions_router, prefix="/api/v1/sessions")
    app.dependency_overrides[get_current_user] = lambda: AuthContext(
        user_id="student_demo",
        provider="test",
        token="test-token",
        claims={"uid": "student_demo"},
        is_admin=False,
    )
    return app


def _owned_session(
    store: SQLiteSessionStore,
    owner_id: str = "student_demo",
    *,
    session_id: str | None = None,
):
    return asyncio.run(
        store.create_session(
            session_id=session_id,
            owner_key=build_user_owner_key(owner_id),
        )
    )


def _ctx(user_id: str, *, is_admin: bool = False) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id},
        is_admin=is_admin,
    )


@pytest.fixture
def store(tmp_path: Path, monkeypatch) -> SQLiteSessionStore:
    instance = SQLiteSessionStore(db_path=tmp_path / "router-test.db")
    monkeypatch.setattr(
        "deeptutor.api.routers.question_notebook.get_sqlite_session_store",
        lambda: instance,
    )
    monkeypatch.setattr(
        "deeptutor.api.routers.sessions.get_sqlite_session_store",
        lambda: instance,
    )
    return instance


def _quiz_answers():
    return [
        {
            "question_id": "q1",
            "question": "Capital of France?",
            "question_type": "choice",
            "options": {"A": "Berlin", "B": "Paris"},
            "user_answer": "A",
            "correct_answer": "B",
            "explanation": "Paris is the capital.",
            "difficulty": "easy",
            "is_correct": False,
        },
        {
            "question_id": "q2",
            "question": "2+2?",
            "question_type": "choice",
            "options": {"A": "3", "B": "4"},
            "user_answer": "B",
            "correct_answer": "B",
            "is_correct": True,
        },
    ]


def test_list_entries_empty(store: SQLiteSessionStore) -> None:
    with TestClient(_build_app(store)) as client:
        resp = client.get("/api/v1/question-notebook/entries")
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0}


def test_quiz_results_populates_notebook(store: SQLiteSessionStore) -> None:
    session = _owned_session(store, session_id="quiz-owned")
    sid = session["id"]

    with TestClient(_build_app(store)) as client:
        resp = client.post(
            f"/api/v1/sessions/{sid}/quiz-results",
            json={"answers": _quiz_answers()},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["recorded"] is True
        assert body["notebook_count"] == 2
        assert "[Quiz Performance]" in body["content"]

        listing = client.get("/api/v1/question-notebook/entries")
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert len(items) == 2


def test_quiz_results_upserts_on_retry(store: SQLiteSessionStore) -> None:
    session = _owned_session(store, session_id="quiz-retry")
    sid = session["id"]

    with TestClient(_build_app(store)) as client:
        client.post(f"/api/v1/sessions/{sid}/quiz-results", json={"answers": _quiz_answers()})
        updated = _quiz_answers()
        updated[0]["user_answer"] = "B"
        updated[0]["is_correct"] = True
        client.post(f"/api/v1/sessions/{sid}/quiz-results", json={"answers": updated})

        listing = client.get("/api/v1/question-notebook/entries").json()
        assert listing["total"] == 2
        q1 = next(e for e in listing["items"] if e["question_id"] == "q1")
        assert q1["is_correct"] is True
        assert q1["user_answer"] == "B"


def test_upsert_runtime_error_is_sanitized(store: SQLiteSessionStore, monkeypatch: pytest.MonkeyPatch) -> None:
    session = _owned_session(store, session_id="upsert-error")

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("notebook storage exploded secret")

    monkeypatch.setattr(store, "upsert_notebook_entries", _boom)

    with TestClient(_build_app(store)) as client:
        resp = client.post(
            "/api/v1/question-notebook/entries/upsert",
            json={
                "session_id": session["id"],
                "question_id": "q1",
                "question": "What is 2+2?",
            },
        )

    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert detail == "Failed to upsert the notebook entry. Please try again later."
    assert "notebook storage exploded secret" not in detail


def test_bookmark_toggle(store: SQLiteSessionStore) -> None:
    session = _owned_session(store, session_id="bookmark")
    asyncio.run(store.upsert_notebook_entries(session["id"], [{
        "question_id": "q1", "question": "Q?", "is_correct": False,
    }]))
    eid = asyncio.run(store.list_notebook_entries())["items"][0]["id"]

    with TestClient(_build_app(store)) as client:
        resp = client.patch(
            f"/api/v1/question-notebook/entries/{eid}",
            json={"bookmarked": True},
        )
        assert resp.status_code == 200

        bm = client.get("/api/v1/question-notebook/entries?bookmarked=true").json()
        assert bm["total"] == 1

        client.patch(f"/api/v1/question-notebook/entries/{eid}", json={"bookmarked": False})
        bm2 = client.get("/api/v1/question-notebook/entries?bookmarked=true").json()
        assert bm2["total"] == 0


def test_delete_entry(store: SQLiteSessionStore) -> None:
    session = _owned_session(store, session_id="delete")
    asyncio.run(store.upsert_notebook_entries(session["id"], [{
        "question_id": "q1", "question": "Q?", "is_correct": False,
    }]))
    eid = asyncio.run(store.list_notebook_entries())["items"][0]["id"]

    with TestClient(_build_app(store)) as client:
        assert client.delete(f"/api/v1/question-notebook/entries/{eid}").status_code == 200
        assert client.delete(f"/api/v1/question-notebook/entries/{eid}").status_code == 404


def test_category_crud_and_association(store: SQLiteSessionStore) -> None:
    session = _owned_session(store, session_id="category")
    asyncio.run(store.upsert_notebook_entries(session["id"], [{
        "question_id": "q1", "question": "Q?", "is_correct": False,
    }]))
    eid = asyncio.run(store.list_notebook_entries())["items"][0]["id"]

    with TestClient(_build_app(store)) as client:
        cat_resp = client.post(
            "/api/v1/question-notebook/categories",
            json={"name": "Math"},
        )
        assert cat_resp.status_code == 201
        cat_id = cat_resp.json()["id"]

        cats = client.get("/api/v1/question-notebook/categories").json()
        assert len(cats) == 1
        assert cats[0]["name"] == "Math"

        add_resp = client.post(
            f"/api/v1/question-notebook/entries/{eid}/categories",
            json={"category_id": cat_id},
        )
        assert add_resp.status_code == 200

        by_cat = client.get(f"/api/v1/question-notebook/entries?category_id={cat_id}").json()
        assert by_cat["total"] == 1

        rm_resp = client.delete(f"/api/v1/question-notebook/entries/{eid}/categories/{cat_id}")
        assert rm_resp.status_code == 200
        by_cat2 = client.get(f"/api/v1/question-notebook/entries?category_id={cat_id}").json()
        assert by_cat2["total"] == 0

        client.patch(f"/api/v1/question-notebook/categories/{cat_id}", json={"name": "Algebra"})
        cats2 = client.get("/api/v1/question-notebook/categories").json()
        assert cats2[0]["name"] == "Algebra"

        client.delete(f"/api/v1/question-notebook/categories/{cat_id}")
        assert client.get("/api/v1/question-notebook/categories").json() == []


def test_lookup_entry_by_question(store: SQLiteSessionStore) -> None:
    session = _owned_session(store, session_id="lookup")
    asyncio.run(store.upsert_notebook_entries(session["id"], [{
        "question_id": "q1", "question": "Q?", "is_correct": False,
    }]))

    with TestClient(_build_app(store)) as client:
        resp = client.get(
            "/api/v1/question-notebook/entries/lookup/by-question",
            params={"session_id": session["id"], "question_id": "q1"},
        )
        assert resp.status_code == 200
        assert resp.json()["question_id"] == "q1"

        resp404 = client.get(
            "/api/v1/question-notebook/entries/lookup/by-question",
            params={"session_id": session["id"], "question_id": "nope"},
        )
        assert resp404.status_code == 404


def test_notebook_rejects_foreign_session_and_entry(store: SQLiteSessionStore) -> None:
    own_session = _owned_session(store, "student_demo", session_id="own")
    foreign_session = _owned_session(store, "student_other", session_id="foreign")
    asyncio.run(store.upsert_notebook_entries(foreign_session["id"], [{
        "question_id": "q1", "question": "Other?", "is_correct": False,
    }]))
    foreign_entry_id = asyncio.run(store.list_notebook_entries(owner_key=build_user_owner_key("student_other")))["items"][0]["id"]

    app = _build_app(store)
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo")

    with TestClient(app) as client:
        assert client.post(
            "/api/v1/question-notebook/entries/upsert",
            json={
                "session_id": foreign_session["id"],
                "question_id": "q2",
                "question": "Denied?",
            },
        ).status_code == 404

        assert client.get(
            "/api/v1/question-notebook/entries/lookup/by-question",
            params={"session_id": foreign_session["id"], "question_id": "q1"},
        ).status_code == 404

        assert client.get(f"/api/v1/question-notebook/entries/{foreign_entry_id}").status_code == 404
        assert client.patch(
            f"/api/v1/question-notebook/entries/{foreign_entry_id}",
            json={"bookmarked": True},
        ).status_code == 404
        assert client.delete(f"/api/v1/question-notebook/entries/{foreign_entry_id}").status_code == 404

        own_entry = client.post(
            "/api/v1/question-notebook/entries/upsert",
            json={
                "session_id": own_session["id"],
                "question_id": "q1",
                "question": "Own?",
            },
        )
        assert own_entry.status_code == 200


def test_notebook_scopes_categories_to_owner(store: SQLiteSessionStore) -> None:
    own_session = _owned_session(store, "student_demo", session_id="own-cat")
    foreign_session = _owned_session(store, "student_other", session_id="foreign-cat")
    asyncio.run(store.upsert_notebook_entries(own_session["id"], [{
        "question_id": "q1", "question": "Own Q?", "is_correct": False,
    }]))
    asyncio.run(store.upsert_notebook_entries(foreign_session["id"], [{
        "question_id": "q2", "question": "Foreign Q?", "is_correct": False,
    }]))
    own_entry_id = asyncio.run(store.list_notebook_entries(owner_key=build_user_owner_key("student_demo")))["items"][0]["id"]
    foreign_entry_id = asyncio.run(store.list_notebook_entries(owner_key=build_user_owner_key("student_other")))["items"][0]["id"]

    own_category = asyncio.run(store.create_category("Math", owner_key=build_user_owner_key("student_demo")))
    foreign_category = asyncio.run(store.create_category("History", owner_key=build_user_owner_key("student_other")))

    app = _build_app(store)
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo")

    with TestClient(app) as client:
        cats = client.get("/api/v1/question-notebook/categories").json()
        assert [item["name"] for item in cats] == ["Math"]

        assert client.get(f"/api/v1/question-notebook/entries/{own_entry_id}").status_code == 200
        assert client.get(f"/api/v1/question-notebook/entries/{foreign_entry_id}").status_code == 404

        assert client.post(
            f"/api/v1/question-notebook/entries/{own_entry_id}/categories",
            json={"category_id": own_category["id"]},
        ).status_code == 200

        assert client.post(
            f"/api/v1/question-notebook/entries/{own_entry_id}/categories",
            json={"category_id": foreign_category["id"]},
        ).status_code == 400

        assert client.patch(
            f"/api/v1/question-notebook/categories/{foreign_category['id']}",
            json={"name": "Biology"},
        ).status_code == 404
        assert client.delete(f"/api/v1/question-notebook/categories/{foreign_category['id']}").status_code == 404


def test_admin_can_access_foreign_notebook_data(store: SQLiteSessionStore) -> None:
    foreign_session = _owned_session(store, "student_other", session_id="foreign-admin")
    asyncio.run(store.upsert_notebook_entries(foreign_session["id"], [{
        "question_id": "q1", "question": "Foreign?", "is_correct": False,
    }]))
    foreign_entry_id = asyncio.run(store.list_notebook_entries(owner_key=build_user_owner_key("student_other")))["items"][0]["id"]
    foreign_category = asyncio.run(store.create_category("AdminView", owner_key=build_user_owner_key("student_other")))

    app = _build_app(store)
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_user", is_admin=True)

    with TestClient(app) as client:
        entries = client.get("/api/v1/question-notebook/entries").json()
        assert any(item["id"] == foreign_entry_id for item in entries["items"])
        assert client.get(f"/api/v1/question-notebook/entries/{foreign_entry_id}").status_code == 200
        cats = client.get("/api/v1/question-notebook/categories").json()
        assert any(category["id"] == foreign_category["id"] for category in cats)
        assert client.patch(
            f"/api/v1/question-notebook/categories/{foreign_category['id']}",
            json={"name": "AdminRenamed"},
        ).status_code == 200
