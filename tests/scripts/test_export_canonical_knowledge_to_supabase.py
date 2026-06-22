from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_canonical_knowledge_to_supabase.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("export_canonical_knowledge_to_supabase", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_apply_docs_match_direct_postgres_credentials() -> None:
    module = _load_script()

    assert "DATABASE_URL" in str(module.__doc__)
    assert "SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=..." not in str(module.__doc__)


def test_schema_sql_keeps_public_projection_tables_service_role_only() -> None:
    module = _load_script()
    sql = module._SCHEMA_SQL.lower()

    for table in (
        "luban_canonical_taxonomy",
        "luban_canonical_knowledge_catalog",
        "luban_canonical_knowledge_edges",
    ):
        assert f"alter table public.{table} enable row level security;" in sql
        assert f"alter table public.{table} force row level security;" in sql
        assert f"revoke all on table public.{table} from anon, authenticated;" in sql


def test_catalog_and_edges_are_canonicalized_to_taxonomy_display_codes() -> None:
    module = _load_script()
    alias_to_display = {
        "1A411010-R02": "1A411010-R02",
        "1A411010-R02-ALIAS": "1A411010-R02",
        "1A412010-B010": "1A412010-B010",
        "1A412010-B010-ALIAS": "1A412010-B010",
    }

    cat_rows = module._canonicalize_catalog_rows(
        [
            {
                "node_code": "1A411010-R02-ALIAS",
                "name_path": "建筑工程技术 > 建筑设计",
                "textbook_count": 1,
                "standard_count": 0,
                "lecture_count": 0,
                "question_count": 0,
                "has_knowledge": True,
                "has_question": False,
            }
        ],
        alias_to_display,
    )
    edge_rows = module._canonicalize_edge_rows(
        [
            {
                "src": "1A411010-R02-ALIAS",
                "dst": "1A412010-B010-ALIAS",
                "type": "related",
                "relation_detail": None,
                "confidence": 0.9,
                "provenance": [],
            }
        ],
        alias_to_display,
    )

    assert cat_rows[0]["node_code"] == "1A411010-R02"
    assert edge_rows[0]["src"] == "1A411010-R02"
    assert edge_rows[0]["dst"] == "1A412010-B010"

    module._validate_projection_closure(
        [
            {"concept_id": "c1", "code": "1A411010-R02"},
            {"concept_id": "c2", "code": "1A412010-B010"},
        ],
        cat_rows,
        edge_rows,
    )


def test_projection_closure_rejects_unregistered_catalog_nodes() -> None:
    module = _load_script()

    try:
        module._validate_projection_closure(
            [{"concept_id": "c1", "code": "1A411010-R02"}],
            [{"node_code": "UNREGISTERED"}],
            [],
        )
    except SystemExit as exc:
        assert "missing_catalog_node_codes" in str(exc)
    else:
        raise AssertionError("expected projection closure to reject unregistered node_code")
