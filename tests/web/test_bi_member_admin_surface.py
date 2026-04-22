from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_bi_page_client_exposes_four_admin_tabs() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert '"boss-workbench"' in source
    assert '"member-ops"' in source
    assert '"learner-360"' in source
    assert '"audit"' in source


def test_member_page_reuses_bi_admin_workspace() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "member" / "page.tsx").read_text(encoding="utf-8")

    assert '"/bi?tab=member-ops"' in source or "BiPageClient" in source


def test_bi_member_ops_tab_uses_table_and_detail_panel() -> None:
    source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiMemberOpsTab.tsx"
    ).read_text(encoding="utf-8")

    assert "BiMemberAdminTable" in source
    assert "BiMember360Panel" in source


def test_bi_member_360_panel_exposes_recent_conversations() -> None:
    source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiMember360Panel.tsx"
    ).read_text(encoding="utf-8")

    assert "最近聊天记录" in source
    assert "recentConversations" in source


def test_bi_page_client_mounts_audit_tab() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "BiAuditTab" in source
    assert "exportHref={exportHref}" in source


def test_bi_api_prefers_backend_boss_workbench_payload() -> None:
    source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")

    assert "boss_workbench" in source
    assert "handoff_filters" in source


def test_bi_page_client_consumes_handoff_filters_from_boss_queue() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "handoffFilters" in source
    assert 'expire_within_days' in source


def test_bi_page_client_refreshes_boss_workbench_after_member_actions() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "await refreshBi()" in source


def test_bi_audit_tab_exposes_filter_inputs() -> None:
    source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiAuditTab.tsx"
    ).read_text(encoding="utf-8")

    assert "target_user" in source or "目标用户" in source
    assert "operator" in source or "操作人" in source
    assert "action" in source or "动作" in source


def test_bi_api_sends_metrics_token_header() -> None:
    source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "web" / "lib" / "api.ts").read_text(encoding="utf-8")

    assert "withBiApiToken" in source
    assert "BI_API_TOKEN" in source
    assert "X-Metrics-Token" in api_source


def test_bi_page_client_exposes_token_read_only_mode() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "biReadOnly" in source
    assert "BI API Token" in source


def test_bi_page_client_only_clears_admin_session_for_auth_failures() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")
    auth_source = (REPO_ROOT / "web" / "lib" / "bi-admin-auth.ts").read_text(encoding="utf-8")

    assert "restoreBiAdminSession" in source
    assert "isAuthUnavailableError" in auth_source
    assert "管理员会话校验暂时失败，请稍后重试。" in source
