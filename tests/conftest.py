"""Root pytest configuration.

`is_production_environment()` is fail-closed: an unset / unknown environment is
treated as production so dev-only safeguards never default to "open". The test
suite must therefore declare its environment explicitly. We default the whole
process to ``local`` at import time (before any test module — e.g.
``attempt_refs`` — is collected and runs its import-time secret check) so that:

* AGENTS §264 dev/QA login + mock-code paths stay exercised, and
* tests that rely on the historical non-production default keep passing.

Individual tests that need production behaviour still override this via
``monkeypatch.setenv("DEEPTUTOR_ENV", "production")`` (or ``delenv`` to assert the
fail-closed default).
"""

from __future__ import annotations

import os

# setdefault, not a hard set: an outer harness can still force a production-mode
# test run by exporting DEEPTUTOR_ENV before invoking pytest.
os.environ.setdefault("DEEPTUTOR_ENV", "local")
