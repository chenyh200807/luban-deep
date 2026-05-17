from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_invite_test_database_tls_does_not_disable_certificate_verification() -> None:
    source = (ROOT / "web" / "app" / "api" / "invite-test" / "applications" / "route.ts").read_text(
        encoding="utf-8"
    )

    assert "rejectUnauthorized: false" not in source
    assert "readExternalEnvDatabaseUrl" not in source
    assert "FastAPI20251222" not in source
    assert 'sslmode === "no-verify"' in source
    assert 'sslmode === "disable"' in source
    assert "Invite-test database TLS must verify certificates" in source
    assert "ssl: getDatabaseSsl(normalizedConnectionString)" in source
    assert "申请提交通道未配置" in source
