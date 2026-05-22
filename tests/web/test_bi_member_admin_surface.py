from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_bi_page_client_exposes_four_admin_tabs() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert '"boss-workbench"' in source
    assert '"member-ops"' in source
    assert '"launch-readiness"' in source
    assert '"invite-test"' in source
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
    assert "onRecordConversationView" in source
    assert "await onRecordConversationView(conversation)" in source
    assert "viewAuditError" in source


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


def test_bi_teaching_effect_surface_exposes_chapter_progress() -> None:
    api_source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")
    panel_source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiAiQualityPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "BiTeachingChapterProgress" in api_source
    assert "chapter_progress" in api_source
    assert "chapterProgress" in api_source
    assert "章节进展" in panel_source
    assert "teachingEffect.chapterProgress" in panel_source


def test_bi_ai_quality_surface_exposes_quality_samples() -> None:
    panel_source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiAiQualityPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "质量样本" in panel_source
    assert "aiQuality.samples" in panel_source


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


def test_bi_page_client_refreshes_audit_after_note_and_runtime_admin_actions() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    note_section = source.split("const handleAddNote")[1].split("const handleRecordOpsAction")[0]
    heartbeat_section = source.split("const handleHeartbeatJobAction")[1].split("const handleApplyOverlayPromotions")[0]
    overlay_section = source.split("const handleApplyOverlayPromotions")[1].split("const handleAdminLogin")[0]

    assert "createMemberNote" in note_section
    assert "await refreshAudit()" in note_section
    assert "pauseHeartbeatJob" in heartbeat_section
    assert "resumeHeartbeatJob" in heartbeat_section
    assert "await refreshAudit()" in heartbeat_section
    assert "applyOverlayPromotions" in overlay_section
    assert "await refreshAudit()" in overlay_section


def test_member_api_exposes_conversation_view_audit() -> None:
    source = (REPO_ROOT / "web" / "lib" / "member-api.ts").read_text(encoding="utf-8")
    client_source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "recordMemberConversationView" in source
    assert "/view-audit" in source
    assert "recordMemberConversationView" in client_source


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
    assert "readAccessDenied" in source
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

    assert "BI 只读凭证已由系统配置" in source
    assert "无需手动填写" in source


def test_bi_page_client_turns_protected_tabs_into_unlock_flow() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "解锁会员后台" in source
    assert "scrollIntoView" in source


def test_bi_invite_test_admin_surface_is_protected_and_mounted() -> None:
    client_source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")
    shared_source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiShared.tsx").read_text(encoding="utf-8")
    tab_source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiInviteTestTab.tsx"
    ).read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")

    assert '"invite-test"' in shared_source
    assert "activeTab === \"invite-test\"" in client_source
    assert "getBiInviteTestApplications" in client_source
    assert "getBiInviteTestStats" in client_source
    assert "INVITE_TEST_WINDOW_DAYS = 365" in client_source
    assert "内测申请池" in tab_source
    assert "/api/v1/bi/invite-test/applications" in api_source
    assert "/api/v1/bi/invite-test/stats" in api_source


def test_bi_launch_readiness_surface_consumes_single_backend_authority() -> None:
    client_source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")
    shared_source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiShared.tsx").read_text(encoding="utf-8")
    tab_source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiLaunchReadinessTab.tsx"
    ).read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")

    assert '"launch-readiness"' in shared_source
    assert "getBiLaunchReadiness" in client_source
    assert "BiLaunchReadinessTab" in client_source
    assert "/api/v1/observability/launch-readiness" in api_source
    assert "上线 readiness" in tab_source
    assert "final_status" in api_source
    assert "readiness_checks" not in tab_source


def test_bi_admin_restore_sets_session_optimistically_before_profile_verification() -> None:
    """Reload with a stored admin session must not flash the locked ACCESS GATE
    while we wait for /auth/profile to verify the token. The page client must
    set the optimistic adminSession before awaiting restoreBiAdminSession() and
    the backend still revalidates the token on every BI API call. The locked
    fallback only re-renders if the async restore returns session=null."""
    source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx"
    ).read_text(encoding="utf-8")

    # The optimistic block must appear before the await and contain the three
    # state writes that flip the UI out of the locked fallback immediately.
    optimistic_marker = "// Optimistic restore"
    assert optimistic_marker in source, (
        "BiPageClient.tsx must keep the optimistic restore comment explaining "
        "why setAdminSession(stored) runs before the /auth/profile await."
    )
    optimistic_idx = source.index(optimistic_marker)
    optimistic_block = source[optimistic_idx : optimistic_idx + 1200]
    assert "setAdminSession(stored);" in optimistic_block
    assert "setAuthReady(true);" in optimistic_block
    assert (
        optimistic_block.index("setAdminSession(stored);")
        < optimistic_block.index("await restoreBiAdminSession(stored)")
    ), (
        "Optimistic adminSession must be set before awaiting "
        "restoreBiAdminSession to avoid the locked-flash regression."
    )


def test_bi_admin_login_error_is_announced_as_alert() -> None:
    """When loginBiAdmin throws (bad password, non-admin account, etc.) the
    BiPageClient must surface authError with role=alert so assistive tech and
    E2E tooling can pick it up. The previous QA missed the rose-styled
    paragraph because it only carried a Tailwind class."""
    source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx"
    ).read_text(encoding="utf-8")

    # Both admin-access surfaces (default tab section + protected-tab gate)
    # render authError, and both must announce it as an alert.
    alert_paragraphs = source.count(
        'role="alert" aria-live="assertive" className="mt-3 text-sm text-rose-700"'
    )
    assert alert_paragraphs == 2, (
        "Both BI admin authError paragraphs must use role=alert + "
        f"aria-live=assertive; found {alert_paragraphs}."
    )
