"""BI v2 会员运营：首屏会员表必须支持列头排序。"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PANEL = REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_v2" / "member-ops" / "BiV2MemberOpsPanel.tsx"
DATA = REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_v2" / "member-ops" / "data.ts"


def test_member_ops_table_wires_sort_state_into_data_table() -> None:
    source = PANEL.read_text(encoding="utf-8")

    assert "const [sortKey, setSortKey]" in source
    assert "const [sortDir, setSortDir]" in source
    assert "sortMembers(" in source
    assert "sortKey={sortKey}" in source
    assert "sortDir={sortDir}" in source
    assert "onSort={handleSort}" in source


def test_member_ops_core_visible_columns_are_sortable() -> None:
    source = DATA.read_text(encoding="utf-8")

    for key in ["phone", "tier", "status", "risk", "last_active", "balance", "expires_at"]:
        assert f"key: '{key}'" in source
    for label in ["手机号", "Tier", "状态", "风险", "最近活跃", "余额(点)", "到期"]:
        line = next(line for line in source.splitlines() if f"label: '{label}'" in line)
        assert "sortable: true" in line
