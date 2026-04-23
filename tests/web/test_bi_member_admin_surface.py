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


def test_bi_member_360_conversations_are_collapsed_until_clicked() -> None:
    source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiMember360Panel.tsx"
    ).read_text(encoding="utf-8")

    assert "expandedConversationId" in source
    assert "setExpandedConversation" in source
    assert "aria-expanded={isExpanded}" in source
    assert "isExpanded ? (" in source
    assert "查看全文" in source


def test_bi_page_client_mounts_audit_tab() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "BiAuditTab" in source
    assert "exportHref={exportHref}" in source


def test_bi_api_prefers_backend_boss_workbench_payload() -> None:
    source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")

    assert "boss_workbench" in source
    assert "handoff_filters" in source


def test_bi_api_exposes_top_tier_boss_payload_contract() -> None:
    source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")

    assert "BiNorthStarPayload" in source
    assert "north_star" in source
    assert "northStar" in source
    assert "growth_funnel" in source
    assert "growthFunnel" in source
    assert "member_health" in source
    assert "memberHealth" in source
    assert "operating_rhythm" in source
    assert "operatingRhythm" in source
    assert "data_trust" in source
    assert "dataTrust" in source


def test_boss_workbench_renders_top_tier_content_panels() -> None:
    source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiBossHomeTab.tsx"
    ).read_text(encoding="utf-8")

    assert "BiNorthStarPanel" in source
    assert "BiGrowthFunnelPanel" in source
    assert "BiMemberHealthPanel" in source
    assert "BiAiQualityPanel" in source
    assert "BiDataTrustPanel" in source
    assert "overview?.northStar" in source
    assert "overview?.dataTrust" in source


def test_member_health_panel_marks_c_level_score_as_degraded() -> None:
    source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiMemberHealthPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "isDegraded" in source
    assert "降级展示" in source


def test_bi_api_maps_daily_cost_boss_queue_to_cost_source() -> None:
    source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")

    assert 'bucket === "cost" || bucket === "daily_cost"' in source


def test_boss_workbench_exposes_daily_cost_surface() -> None:
    api_source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")
    trend_source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiBossTrendPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "daily_cost" in api_source
    assert "dailyCost" in api_source
    assert "今日成本" in trend_source
    assert "日均成本" in trend_source


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


def test_bi_member_360_exposes_ops_action_result_loop() -> None:
    panel_source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiMember360Panel.tsx"
    ).read_text(encoding="utf-8")
    client_source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "web" / "lib" / "member-api.ts").read_text(encoding="utf-8")

    assert "处理结果闭环" in panel_source
    assert "onRecordOpsAction" in panel_source
    assert "await onSubmit" in panel_source
    assert "submitError" in panel_source
    assert "recordMemberOpsAction" in api_source
    assert "await refreshAudit()" in client_source


def test_bi_api_sends_metrics_token_header() -> None:
    source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "web" / "lib" / "api.ts").read_text(encoding="utf-8")

    assert "withBiApiToken" in source
    assert "BI_API_TOKEN" in source
    assert "X-Metrics-Token" in api_source
    assert "__NEXT_PUBLIC_BI_API_TOKEN_PLACEHOLDER__" in api_source
    assert '"__NEXT_PUBLIC_BI_API_TOKEN_" + "PLACEHOLDER__"' in api_source
    assert 'resolvedBiApiToken === BI_API_TOKEN_PLACEHOLDER ? ""' in api_source


def test_bi_page_client_exposes_token_read_only_mode() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "biReadOnly" in source
    assert "BI API Token" in source
    assert 'const heroIssueTitle = issues[0] ? "当前数据已降级展示" : "经营提醒";' in source


def test_bi_page_client_only_clears_admin_session_for_auth_failures() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")
    auth_source = (REPO_ROOT / "web" / "lib" / "bi-admin-auth.ts").read_text(encoding="utf-8")

    assert "restoreBiAdminSession" in source
    assert "isAuthUnavailableError" in auth_source
    assert "管理员会话校验暂时失败，请稍后重试。" in source


def test_member_api_supports_admin_authorization_header() -> None:
    source = (REPO_ROOT / "web" / "lib" / "member-api.ts").read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "web" / "lib" / "api.ts").read_text(encoding="utf-8")

    assert "withAdminAuthorization" in source
    assert "Authorization" in api_source
    assert "Bearer" in api_source


def test_bi_page_client_exposes_admin_login_entry() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "管理员登录" in source
    assert "adminSession" in source


def test_bi_page_client_explains_token_is_server_managed() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "BI API Token 已由系统配置" in source
    assert "无需手动填写" in source


def test_bi_page_client_turns_protected_tabs_into_unlock_flow() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "解锁会员后台" in source
    assert "scrollIntoView" in source
