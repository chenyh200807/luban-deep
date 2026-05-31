# Smoke 全树升级 · 隔离测试 backlog（M9 → L3/L4）

- 状态：`Proposed`（隔离已落地，un-quarantine 待各 owner 修）
- 主线：生产部署 / 系统成熟度（见 [2026-05-30-system-maturity-audit.md](2026-05-30-system-maturity-audit.md) M9）
- 相关代码入口：`.github/workflows/tests.yml`（`smoke-tests` job 升级为 hermetic 全树 + `quarantine-advisory` job）、`pyproject.toml`（markers）、`tests/conftest.py`（进程级单例隔离）

## 目标

把 CI 必过门（required gate）从手挑 allowlist 升级为 `pytest tests/` **全目录**，消除"整目录静默漏跑"。全树 2968 测试中：
- **2953 个 hermetic** → 进 required gate（`-m "not requires_external and not quarantine_web_drift and not quarantine_assessment_drift"`），本地干净环境 `2953 passed, 1 skipped, 14 deselected` 全绿才放行。
- **14 个被显式排除**，每一个都有 marker、有 log、有 owner，**绝不静默 skip**。

## 非目标

- 不修并行 BI/web 会话正在写的 web 代码（surgical：只登记、不越界）。
- 不回填历史、不动 assessment 业务语义（taxonomy 归属待 owner 判定）。

## 排除清单（14）

### A. requires_external（4）— 真外部依赖，排除 + log，不在任何 gate
| 测试 | 原因 |
|---|---|
| `tests/services/llm/test_ssl_verify_policy.py::test_agentic_pipeline_rejects_disable_ssl_verify_in_production` | 子进程 spawn `./.venv/bin/python`，需 dev venv 布局 |
| `tests/services/member_console/test_service.py::test_production_without_supabase_sessions_only_blocks_assessment_paths` | `MemberConsoleService` 解析到 live Supabase creds |
| `tests/services/member_console/test_service.py::test_assessment_deep_explanation_reads_submitted_report_without_score_mutation` | REST 打 live Supabase `wallet_ledger` |
| `tests/services/member_console/test_service.py::test_assessment_deep_explanation_checks_balance_before_llm_generation` | 同上 |

> ⚠️ **后续可收敛信号**：调查发现 member_console 3 个的 live-Supabase 调用，根因是 `EnvStore.load()` 把开发机 fallback `.env`（主仓 `.env` / `FastAPI20251222/.env`）的 `SUPABASE_URL/KEY` 经 `os.environ.setdefault` 注入 os.environ（CI 无此 .env）。理论上它们在 CI 干净 env 下可能 hermetic 通过——本轮因导入期注入顽固、且对生产检测逻辑有更深 env 耦合，未强行 hermetic 化，先按指挥官预分类标 requires_external。**owner 可后续验证：若 CI 真能 hermetic 过，则去掉 marker、提升回 gate**（同 `tests/api/test_auth_dependency.py` 的修法——本轮已把它从同类污染中 §5 治本，改 mock `get_wallet_identity_store` 后留在 gate 内）。

### B. quarantine_web_drift（9）— 并行 BI/web 工作 drift，advisory 可见、不进 gate
归属：写并行 BI/web 的会话 / web owner。这些是被漏跑掩盖的真 drift（M9 的实证后果）。

| 测试 | 类型 |
|---|---|
| `tests/web/test_bi_member_admin_surface.py::test_bi_page_client_exposes_four_admin_tabs` | 源码断言 drift |
| `tests/web/test_bi_member_admin_surface.py::test_bi_api_maps_daily_cost_boss_queue_to_cost_source` | 源码断言 drift |
| `tests/web/test_bi_member_admin_surface.py::test_bi_page_client_exposes_token_read_only_mode` | 源码断言 drift |
| `tests/web/test_bi_member_admin_surface.py::test_bi_invite_test_admin_surface_is_protected_and_mounted` | 源码断言 drift |
| `tests/web/test_bi_member_admin_surface.py::test_bi_admin_restore_sets_session_optimistically_before_profile_verification` | 源码断言 drift |
| `tests/web/test_chat_frontend_regressions.py::test_next_dev_proxies_same_origin_api_routes_to_backend` | next.config 源码 drift |
| `tests/web/test_chat_frontend_regressions.py::test_logo_images_preserve_intrinsic_aspect_ratio_when_scaled` | 组件 `width={491}` drift |
| `tests/web/test_chat_frontend_regressions.py::test_workspace_shell_hides_fixed_sidebar_on_mobile` | 组件 className drift |
| 🔴 **HIGH** `tests/web/test_bi_v2_raw_fetch_guard.py::test_v2_no_apiurl_outside_allowlist` | **真契约违规，非测试 drift** |

> 🔴 **HIGH — 真契约违规（owner 必须修代码，不是改测试）**：
> `web/.../feedback/BiV2FeedbackPanel.tsx` 直接调用 `apiUrl()` 构造写 URL，**绕过了 generated `WRITE_ENDPOINTS` 注册表 / `resolveWritePath`**。这是 BI v2 写端点单一权威的契约被破坏（同 raw-fetch 回归向量）。
> 处置：web owner 把 `BiV2FeedbackPanel.tsx` 的写路径改回经 `WRITE_ENDPOINTS` 注册表解析，而**不是**更新这个 guard 测试去迁就违规代码。修完后去掉该测试的 `quarantine_web_drift` marker。

### C. quarantine_assessment_drift（1）— assessment 域归属待 owner 判定
| 测试 | 说明 |
|---|---|
| `tests/services/assessment/test_writeback.py::test_assessment_writeback_updates_home_personalization_projection` | 期望 `今日焦点：防水工程`，代码现产出 `今日焦点：防水节点处理` |

> 归属判定：test 断言 `防水工程` 写于 `fb6c05f2`（2026-05-25 "derive home focus from assessment evidence"）；之后 `9ba55cc1`（"Unify taxonomy authority for learning topics"）改了 `resolve_learning_topic_from_payload`，现把 home focus 解析为 `防水节点处理`——**而 `防水工程` 才是 `topic_catalog.py` 里的 catalog topic，`防水节点处理` 不在 catalog**（疑似从 `simple_explanation` 文本提取）。漏跑从 5-25 起掩盖了这个破坏。
> **owner 决策**：确认 taxonomy authority 把 home focus 解析成非 catalog 短语是**有意改进**（→ 更新测试到 `防水节点处理`）还是**回归**（→ 修 resolver 回到 catalog topic `防水工程`）。两种都不该由本轮盲目改测试固化。

## 本轮已 §5 治本（留在 required gate 内，非排除）

| 修复 | 根因 |
|---|---|
| `tests/services/learner_state/test_learning_report_read_model.py::test_training_loop_uses_latest_attempt_not_any_past_correct_signal` IndexError | 夹具硬编码绝对日期 `2026-05-20` 随时间漂出读模型 8 天 recency 窗口；同根因已被并行会话在 main 用 `_iso_minutes_ago(10/5)` 相对时间修复，本轮 merge main 时采纳其版本（本轮自带的 `days_ago` 冗余 fix 已弃） |
| `scripts/wallet_authority_common.py` `resolve_wallet_env` 全树串扰（wallet_authority×2 / wallet_projection×1） | `dict(environ or os.environ)` 把显式空 dict 当 falsy 回退真 os.environ → 改 `environ if environ is not None else os.environ` |
| `tests/services/test_config_loader.py::test_load_config_with_main_uses_explicit_project_root` | PathService 进程单例被前置测试用 tmp dir 构建后缓存 → `tests/conftest.py` autouse 每测试 reset |
| `tests/api/test_auth_dependency.py::test_get_current_user_resets_bound_user_context_between_requests` | log-context ContextVar 泄漏 + auth flow 打 live Supabase identity store → conftest 重置 contextvar + 测试 mock `get_wallet_identity_store` |

## 验收标准

- required gate（`smoke-tests` job）= hermetic 全树绿，排除项数显式打进 `$GITHUB_STEP_SUMMARY` + `::notice::`（no silent caps）。
- `quarantine-advisory` job 仍执行 + 报告 10 个隔离测试，结果显示在 Test Summary 表，但**不进** test-summary 的 Fail-if → 可见、不阻断。
- 14 个排除项全部有 marker + 本 backlog 条目。

## M9 翻 required full-green 的前置依赖

当前 hermetic 全树已绿，但 **10 个隔离测试要全部 un-quarantine（删 marker），M9 才算真正 L4 full-green**：

1. **web owner** 修完 9 个 web drift —— 其中 `BiV2FeedbackPanel.tsx` 的 `WRITE_ENDPOINTS` 绕过是真契约 bug，**必须改代码**。
2. **assessment owner** 判定 `防水节点处理` 归属并据此更新测试或修 resolver。
3. （可选收敛）验证 member_console 3 个在 CI 是否 hermetic，能则提升回 gate。

每完成一项，删对应 marker → 该测试自动并入 required gate。
