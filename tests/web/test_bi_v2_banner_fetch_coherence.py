"""Round 4 S5 — banner copy must not claim live service integration without
matching fetch behavior in the same file.

Background: spec auditor Round 3 finding #3 — OpsPanel banner read
"已开启 · audit 接 member_console.audit_log" while the panel rendered hard-
coded mock data with zero fetch calls. The banner is UI; the lack of fetch is
behavior; the two must agree.

This guard scans each BI v2 panel and asserts: if its banner copy claims
**真实** integration with a backend service (phrases like "已接 ... service",
"写入 audit log", "audit 接 ..."), then the same file must contain a real
fetch path — either via useAuditedAction (writes) or an explicit API client
import (reads). Otherwise the banner must use the honest copy added in
Round 4 S5: "flag 已开启 · 数据源待 ... 接入" plus a skeleton/disabled state.

This complements the runtime contract test ``bi_v2_contract_smoke.mjs``: that
catches behavior at runtime, this one catches copy-vs-code drift at source
review time, before any smoke runs.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V2_ROOT = REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_v2"
BI_V2_COMPONENTS_ROOT = REPO_ROOT / "web" / "components" / "bi-v2"

# Banner phrases that imply live backend integration. If any of these appear
# inside a `flagEnabled` (= true) branch and the panel has zero real fetch
# evidence, the panel is lying to operators about its state.
FORBIDDEN_CLAIM_PHRASES = (
    "已写入 audit log",
    "处理结果均写入 audit",
    "audit 接 member_console",
    "已接真实 service",
    "已接 真实 service",
    "数据来自真实",
    "已接入真实",
)

# Evidence of a real backend path in the same file. Any of these counts —
# explicit useAuditedAction usage, or a typed read API client import.
EVIDENCE_PATTERNS = (
    "useAuditedAction",
    "from '@/lib/bi-api'",
    "from '@/lib/member-api'",
)


def _v2_panel_files() -> list[Path]:
    """Limit to panel files (top-level component per section)."""
    return [
        p
        for p in V2_ROOT.rglob("BiV2*.tsx")
        if p.is_file() and not p.name.endswith(".generated.ts")
    ]


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def test_panel_banner_claims_match_fetch_evidence() -> None:
    """Each panel: if banner claims live backend, file must contain a real
    fetch path (useAuditedAction or an api-client import). Otherwise the
    banner must use honest copy.
    """
    offenders: list[str] = []
    for path in _v2_panel_files():
        rel = path.relative_to(V2_ROOT).as_posix()
        cleaned = _strip_comments(path.read_text(encoding="utf-8"))
        claimed: list[str] = [p for p in FORBIDDEN_CLAIM_PHRASES if p in cleaned]
        if not claimed:
            continue
        has_evidence = any(ev in cleaned for ev in EVIDENCE_PATTERNS)
        if not has_evidence:
            offenders.append(
                f"{rel} :: claims {claimed} but no useAuditedAction / bi-api / member-api import"
            )

    assert not offenders, (
        "Banner copy claims live backend integration without matching fetch "
        "evidence (Round 4 S5 invariant). Update copy to honest "
        "\"flag 已开启 · 数据源待 ... 接入\" or wire up the real backend.\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )


def test_overview_enabled_error_does_not_claim_mock_fallback() -> None:
    """When BI_OVERVIEW_V2_ENABLED is true, API failure must be an honest
    unavailable state, not a production-looking mock fallback.
    """
    overview = V2_ROOT / "BiV2OverviewPanel.tsx"
    text = overview.read_text(encoding="utf-8")

    assert "overview API 不可用，已回退到 mock 数据" not in text
    assert "overview API 不可用，未展示 mock 数据" in text


def test_panels_use_shared_data_source_banner_component() -> None:
    """BI v2 panels should share the banner shell while keeping panel copy local."""
    component = BI_V2_COMPONENTS_ROOT / "BiV2DataSourceBanner.tsx"
    assert component.exists()

    expected_panels = [
        V2_ROOT / "BiV2OverviewPanel.tsx",
        V2_ROOT / "commerce" / "BiV2CommercePanel.tsx",
        V2_ROOT / "member-ops" / "BiV2MemberOpsPanel.tsx",
        V2_ROOT / "feedback" / "BiV2FeedbackPanel.tsx",
        V2_ROOT / "ops" / "BiV2OpsPanel.tsx",
    ]

    missing = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in expected_panels
        if "BiV2DataSourceBanner" not in path.read_text(encoding="utf-8")
    ]
    assert not missing, "Panels missing shared BiV2DataSourceBanner:\n" + "\n".join(missing)


def test_flag_enabled_branches_do_not_call_mock_as_live() -> None:
    """A subtler trap: panel reads `if (flagEnabled) { ...real... } else { ...mock... }`
    but actually has identical code paths and just changes banner colour. Catch
    files where the flagEnabled=true branch references the same MOCK_* constant
    as the disabled branch.

    Heuristic: in the same panel file, if both `flagEnabled` boolean is read
    AND `MOCK_` / `ANOMALIES` / etc are imported, the file MUST also reference
    a state called `source` / `bundle` / `useAuditedAction` to indicate it
    differentiates fetched-vs-mock data. Pure mock display under a "已开启"
    banner is the regression target.
    """
    offenders: list[str] = []
    for path in _v2_panel_files():
        rel = path.relative_to(V2_ROOT).as_posix()
        cleaned = _strip_comments(path.read_text(encoding="utf-8"))
        if "flagEnabled" not in cleaned:
            continue
        # If the file imports any mock fixture name AND has the "已开启"
        # affirmative banner, it must also have one of: useAuditedAction (write
        # path) or a `source`/`bundle` state machine (read path with live/mock
        # discriminator). Without either, banner is misleading.
        imports_mock = any(
            name in cleaned
            for name in (
                "MOCK_MEMBERS",
                "MOCK_BUNDLE",
                "ANOMALIES",
                "AUDIT_ENTRIES",
                "FEEDBACK_ITEMS",
                "EXPORT_JOBS",
                "OPS_TILES",
                "ORDERS",
                "LEDGER",
                "PACKAGES",
            )
        )
        if not imports_mock:
            continue
        if "已开启" not in cleaned and "flag 已开启" not in cleaned:
            continue
        has_discriminator = (
            "useAuditedAction" in cleaned
            or "DataSourceBanner" in cleaned
            or "source: 'live'" in cleaned
            or 'source: "live"' in cleaned
            or "loadLive" in cleaned
        )
        # Honest copy contains "数据源待" or "待接入" — that's an escape hatch.
        honest_copy = (
            "数据源待" in cleaned
            or "待接入" in cleaned
            or "待 Batch" in cleaned
            or "尚未接入" in cleaned
            or "待 useAuditedAction" in cleaned
        )
        if not has_discriminator and not honest_copy:
            offenders.append(rel)

    assert not offenders, (
        "Panel imports mock fixtures, displays 已开启 banner, but provides no "
        "live/mock discriminator and no honest 'flag 已开启 · 数据源待 ... 接入' "
        "escape phrase. This is the OpsPanel regression pattern (Round 4 S5).\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )


# --- provenance 文案不得由客户端时钟伪造 -------------------------------------

# `generatedAt: Date.now()` 是同一个 copy-vs-code drift 的另一种形态:banner 上
# 写着数据溯源时刻,值却取自浏览器时钟。数据陈旧时它谎报成"刚刚",而这正是本文件
# 要防的那类"文案声称的事实,代码并不提供"。
_CLIENT_CLOCK_PROVENANCE = re.compile(r"generatedAt\s*:\s*Date\.now\(\)")


def test_panels_do_not_fabricate_snapshot_time_from_client_clock() -> None:
    offenders: list[str] = []
    for path in sorted(V2_ROOT.rglob("*.tsx")):
        if _CLIENT_CLOCK_PROVENANCE.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, (
        "Snapshot provenance must come from the server's `generated_at`, not the "
        "browser clock — otherwise a stale panel reports itself as just-generated:\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )
