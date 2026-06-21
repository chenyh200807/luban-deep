from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_bi_page_client_exposes_four_admin_tabs() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")
    shared_source = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiShared.tsx"
    ).read_text(encoding="utf-8")

    assert "BI_PRIMARY_TABS" in source
    assert "key: 'boss-workbench'" in shared_source
    assert "key: 'member-ops'" in shared_source
    assert "key: 'launch-readiness'" in shared_source
    assert "key: 'invite-test'" in shared_source
    assert "key: 'learner-360'" in shared_source
    assert "key: 'audit'" in shared_source


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

    assert "bucket === 'cost' || bucket === 'daily_cost'" in source


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


def test_bi_api_does_not_expose_metrics_token_to_browser() -> None:
    source = (REPO_ROOT / "web" / "lib" / "bi-api.ts").read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "web" / "lib" / "api.ts").read_text(encoding="utf-8")

    assert "withAdminAuthorization()" in source
    assert "withBiApiToken" not in source
    assert "BI_API_TOKEN" not in source
    assert "X-Metrics-Token" not in api_source
    assert "NEXT_PUBLIC_BI_API_TOKEN" not in api_source


def test_bi_page_client_requires_admin_session_without_public_token() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "biReadOnly" in source
    assert "readAccessDenied" in source
    assert "BI 数据 API 尚未授权" in source
    assert "无需手动填写 API Token" in source
    assert "只读凭证" not in source
    assert "const heroIssueTitle = issues[0] ? '当前数据已降级展示' : '经营提醒'" in source


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

    assert "BI 数据 API 尚未授权" in source
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

    assert "key: 'invite-test'" in shared_source
    assert "activeTab === 'invite-test'" in client_source
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

    assert "key: 'launch-readiness'" in shared_source
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
    assert "setAdminSession(stored)" in optimistic_block
    assert "setAuthReady(true)" in optimistic_block
    assert (
        optimistic_block.index("setAdminSession(stored)")
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


def test_v2_conversation_audit_uses_audited_action_hook() -> None:
    """Round 3 B + E contract:
    ConversationReviewDrawer must call useAuditedAction (single audit gate),
    not fetch directly or via the legacy recordMemberConversationView helper.
    """
    drawer = (
        REPO_ROOT
        / "web"
        / "app"
        / "(workspace)"
        / "bi"
        / "_v2"
        / "member-ops"
        / "ConversationReviewDrawer.tsx"
    ).read_text(encoding="utf-8")

    assert "useAuditedAction" in drawer, (
        "ConversationReviewDrawer must consume useAuditedAction hook (Round 3 B)"
    )
    assert "recordMemberConversationView" not in drawer, (
        "ConversationReviewDrawer must not call legacy recordMemberConversationView "
        "directly — audit must go through useAuditedAction so X-Idempotency-Key is injected"
    )
    # Round 4 S2: URL is no longer built by hand in the drawer. The endpoint
    # is referenced by its registered key; resolveWritePath() in the generated
    # registry expands path_template at call time.
    assert "member.conversation.view_full" in drawer, (
        "ConversationReviewDrawer must reference the registered endpoint key "
        "'member.conversation.view_full' (Round 4 S2 WRITE_ENDPOINTS registry)"
    )
    assert "reason" in drawer, (
        "ConversationReviewDrawer must forward reason (Round 3 G)"
    )


def test_v2_require_bi_admin_boundary_present() -> None:
    """Round 3 C contract: BiV2Surface must gate panels behind RequireBiAdmin
    so identity is authenticated before any panel renders.
    """
    surface = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_v2" / "BiV2Surface.tsx"
    ).read_text(encoding="utf-8")
    require = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_v2" / "RequireBiAdmin.tsx"
    ).read_text(encoding="utf-8")

    assert "<RequireBiAdmin>" in surface, "BiV2Surface must wrap panels with RequireBiAdmin"
    assert "useBiAdminIdentity" in require, "RequireBiAdmin must read identity hook"
    assert "hasBiAccess" in require, "RequireBiAdmin must gate on BI RBAC access"


def test_v2_audited_action_hook_injects_idempotency_and_admin_auth() -> None:
    """Round 3 B contract: useAuditedAction must inject X-Idempotency-Key on
    every write and use withAdminAuthorization (proxy for actor binding).
    """
    hook = (
        REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_v2" / "useAuditedAction.ts"
    ).read_text(encoding="utf-8")

    assert "X-Idempotency-Key" in hook, "useAuditedAction must inject X-Idempotency-Key"
    assert "withAdminAuthorization" in hook, (
        "useAuditedAction must wrap headers via withAdminAuthorization "
        "so admin Authorization survives the write path"
    )
    assert "crypto.randomUUID" in hook, "useAuditedAction must generate idempotency keys"


def test_v2_metric_registry_is_generated_only() -> None:
    """Round 3 D contract: hand-written bi-v2-metric-registry.ts must be deleted
    and consumers must import from the .generated.ts mirror.
    """
    hand_written = REPO_ROOT / "web" / "lib" / "bi-v2-metric-registry.ts"
    generated = REPO_ROOT / "web" / "lib" / "bi-v2-metric-registry.generated.ts"

    assert not hand_written.exists(), (
        "Hand-written bi-v2-metric-registry.ts must be deleted "
        "(Round 3 D single source of truth)"
    )
    assert generated.exists(), "Generated mirror must exist"
    assert generated.read_text(encoding="utf-8").startswith("// AUTOGENERATED"), (
        "Generated file must carry the AUTOGENERATED header"
    )

    overview_panel = (
        REPO_ROOT
        / "web"
        / "app"
        / "(workspace)"
        / "bi"
        / "_v2"
        / "BiV2OverviewPanel.tsx"
    ).read_text(encoding="utf-8")
    assert "bi-v2-metric-registry.generated" in overview_panel, (
        "BiV2OverviewPanel must import from the generated registry"
    )
