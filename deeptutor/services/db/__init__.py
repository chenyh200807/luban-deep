"""Raw-Postgres connection factory package — the one approved raw-connect site.

See deeptutor/services/db/connection_factory.py and contracts/db_registry.yaml.
"""

from deeptutor.services.db.connection_factory import (
    DbResolutionError,
    connect_for_fact,
    resolve_url_for_fact,
)

__all__ = ["DbResolutionError", "connect_for_fact", "resolve_url_for_fact"]
