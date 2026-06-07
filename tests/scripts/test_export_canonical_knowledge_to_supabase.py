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
