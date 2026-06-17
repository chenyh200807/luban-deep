"""Observability helpers for optional Langfuse tracing."""

from pathlib import Path

from .bailian_billing import get_bailian_billing_client
from .bailian_telemetry import get_bailian_telemetry_client
from .control_plane_store import get_control_plane_store, reset_control_plane_store
from .langfuse_adapter import get_langfuse_observability
from .product_behavior_store import SQLiteProductBehaviorStore
from .release_lineage import get_release_lineage_metadata, get_release_lineage_snapshot
from .surface_events import get_surface_event_store, reset_surface_event_store
from .turn_event_log import get_turn_event_log, reset_turn_event_log
from .usage_ledger import get_usage_ledger

_product_behavior_store: SQLiteProductBehaviorStore | None = None


def get_product_behavior_store() -> SQLiteProductBehaviorStore:
    global _product_behavior_store
    if _product_behavior_store is None:
        from deeptutor.services.session.sqlite_store import get_sqlite_session_store

        session_db_path = Path(get_sqlite_session_store().db_path)
        _product_behavior_store = SQLiteProductBehaviorStore(session_db_path.with_name("product_behavior.db"))
    return _product_behavior_store


def reset_product_behavior_store(db_path=None) -> SQLiteProductBehaviorStore:
    global _product_behavior_store
    if db_path is None:
        from deeptutor.services.session.sqlite_store import get_sqlite_session_store

        session_db_path = Path(get_sqlite_session_store().db_path)
        db_path = session_db_path.with_name("product_behavior.db")
    _product_behavior_store = SQLiteProductBehaviorStore(db_path)
    return _product_behavior_store


__all__ = [
    "SQLiteProductBehaviorStore",
    "get_bailian_billing_client",
    "get_bailian_telemetry_client",
    "get_control_plane_store",
    "get_langfuse_observability",
    "get_product_behavior_store",
    "get_release_lineage_metadata",
    "get_release_lineage_snapshot",
    "get_surface_event_store",
    "get_turn_event_log",
    "get_usage_ledger",
    "reset_control_plane_store",
    "reset_product_behavior_store",
    "reset_surface_event_store",
    "reset_turn_event_log",
]
