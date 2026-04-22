# DeepTutor BI 会员后台一体化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/bi` 落成“老板工作台版会员后台”，统一老板总览、会员运营、学员 360 与经营审计，并保持现有 `member_console` / `bi_service` / `/api/v1/ws` authority 边界不变。

**Architecture:** 后端继续以 `deeptutor/services/member_console/service.py` 作为会员运营写入与读取 authority，以 `deeptutor/services/bi_service.py` 作为只读聚合层；前端以 `web/app/(workspace)/bi` 为统一工作台入口，`/member` 退化为兼容入口并复用同一批组件。实现顺序遵循“先补后端合同与测试，再做前端数据契约和页面重构，最后做审计导出与阿里云验收”。

**Tech Stack:** FastAPI, Python service layer, Next.js App Router, TypeScript, Tailwind, pytest, Next build, Playwright/IAB smoke, Aliyun ECS deploy scripts

---

## 文件结构与职责锁定

### 后端文件

- Modify: `deeptutor/services/member_console/service.py`
  - 扩展会员列表筛选、风险队列、批量动作、审计查询与导出载荷
- Modify: `deeptutor/api/routers/member.py`
  - 暴露增强后的 list / dashboard / batch / audit / export 接口
- Modify: `deeptutor/services/bi_service.py`
  - 输出老板工作台需要的 KPI、风险队列、重点会员与 handoff filter
- Modify: `deeptutor/api/routers/bi.py`
  - 暴露增强后的老板工作台聚合接口，保持只读属性
- Modify: `tests/services/member_console/test_service.py`
  - 覆盖 service 级筛选、批量动作、审计输出
- Modify: `tests/api/test_member_router_auth.py`
  - 覆盖 member router 的新增接口和管理员权限
- Modify: `tests/api/test_bi_router.py`
  - 覆盖老板工作台聚合输出与 handoff filter

### 前端文件

- Modify: `web/lib/member-api.ts`
  - 扩展列表筛选参数、批量动作、审计查询与导出 client
- Modify: `web/lib/bi-api.ts`
  - 扩展老板工作台数据结构、风险队列与 handoff filter contract
- Modify: `web/app/(workspace)/bi/BiPageClient.tsx`
  - 统一四个工作区的状态、路由、筛选和面板协作
- Modify: `web/app/(workspace)/member/page.tsx`
  - 改成复用 `/bi` 后台工作台或直接跳到统一入口
- Modify: `web/app/(workspace)/bi/_components/BiBossHomeTab.tsx`
  - 收口老板第一屏，支持跳转到运营过滤视图
- Modify: `web/app/(workspace)/bi/_components/BiMemberOpsTab.tsx`
  - 从摘要页升级为真实会员运营工作区
- Create: `web/app/(workspace)/bi/_components/BiMemberAdminTable.tsx`
  - 承载高密会员表格、批量选择、空态与局部错误
- Create: `web/app/(workspace)/bi/_components/BiMember360Panel.tsx`
  - 承载学员 360 详情、运营动作、overlay / heartbeat / notes
- Create: `web/app/(workspace)/bi/_components/BiAuditTab.tsx`
  - 承载经营审计列表、筛选和导出入口
- Create: `tests/web/test_bi_member_admin_surface.py`
  - 用源码 smoke test 锁定 `/bi` 四工作区、`/member` 兼容复用和关键文案

### 验证与部署文件

- Reuse: `docs/zh/guide/aliyun-deploy.md`
- Reuse: `scripts/deploy_aliyun.sh`
- Reuse: `scripts/server_bootstrap_aliyun.sh`
- Reuse: `scripts/verify_aliyun_public_endpoints.sh`

---

### Task 1: 扩展 member_console 服务合同

**Files:**
- Modify: `deeptutor/services/member_console/service.py`
- Modify: `tests/services/member_console/test_service.py`

- [ ] **Step 1: 写失败测试，锁定会员筛选、批量动作和审计查询输出**

```python
def test_list_members_supports_expiry_window_and_operational_flags(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {
                **service._build_default_member("vip_soon"),
                "display_name": "即将到期会员",
                "tier": "vip",
                "status": "active",
                "risk_level": "high",
                "expire_at": "2026-04-25T00:00:00+08:00",
                "last_active_at": "2026-04-20T10:00:00+08:00",
                "auto_renew": False,
            },
            {
                **service._build_default_member("svip_safe"),
                "display_name": "稳定会员",
                "tier": "svip",
                "status": "active",
                "risk_level": "low",
                "expire_at": "2026-08-01T00:00:00+08:00",
                "last_active_at": "2026-04-22T09:00:00+08:00",
                "auto_renew": True,
            },
        ]

    service._mutate(_seed)

    result = service.list_members(
        page=1,
        page_size=20,
        tier="vip",
        risk_level="high",
        expire_within_days=7,
        auto_renew=False,
    )

    assert [item["user_id"] for item in result["items"]] == ["vip_soon"]
    assert result["filters"]["expire_within_days"] == 7


def test_batch_update_members_returns_success_and_failure_buckets(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {**service._build_default_member("u1"), "tier": "trial"},
            {**service._build_default_member("u2"), "tier": "trial"},
        ]

    service._mutate(_seed)

    result = service.batch_update_members(
        user_ids=["u1", "u2", "missing"],
        action="grant",
        tier="vip",
        days=30,
        operator="admin_demo",
        reason="批量开通",
    )

    assert result["success_count"] == 2
    assert result["failure_count"] == 1
    assert result["failed"][0]["user_id"] == "missing"


def test_list_audit_log_supports_target_user_and_action_filters(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service._append_audit_log(
        {
            "id": "audit_1",
            "target_user": "u1",
            "operator": "admin_demo",
            "action": "grant",
            "reason": "manual",
            "created_at": "2026-04-22T10:00:00+08:00",
        }
    )
    service._append_audit_log(
        {
            "id": "audit_2",
            "target_user": "u2",
            "operator": "admin_demo",
            "action": "revoke",
            "reason": "manual",
            "created_at": "2026-04-22T11:00:00+08:00",
        }
    )

    result = service.list_audit_log(page=1, page_size=20, target_user="u1", action="grant")

    assert [item["id"] for item in result["items"]] == ["audit_1"]
```

- [ ] **Step 2: 跑测试确认当前失败**

Run:

```bash
python -m pytest tests/services/member_console/test_service.py -k "expiry_window or batch_update_members or list_audit_log_supports" -v
```

Expected:

```text
FAILED tests/services/member_console/test_service.py::test_list_members_supports_expiry_window_and_operational_flags
FAILED tests/services/member_console/test_service.py::test_batch_update_members_returns_success_and_failure_buckets
FAILED tests/services/member_console/test_service.py::test_list_audit_log_supports_target_user_and_action_filters
```

- [ ] **Step 3: 写最小实现，先补 service 能力，不改 router**

```python
def list_members(
    self,
    page: int = 1,
    page_size: int = 20,
    sort: str = "expire_at",
    order: str = "asc",
    status: str | None = None,
    tier: str | None = None,
    search: str | None = None,
    segment: str | None = None,
    risk_level: str | None = None,
    auto_renew: bool | None = None,
    expire_within_days: int | None = None,
    active_within_days: int | None = None,
    has_heartbeat_job: bool | None = None,
    has_overlay_candidates: bool | None = None,
) -> dict[str, Any]:
    items = list(self._load().get("members", []))
    now = _now()

    def _match(member: dict[str, Any]) -> bool:
        if status and member.get("status") != status:
            return False
        if tier and member.get("tier") != tier:
            return False
        if segment and member.get("segment") != segment:
            return False
        if risk_level and member.get("risk_level") != risk_level:
            return False
        if auto_renew is not None and bool(member.get("auto_renew")) is not auto_renew:
            return False
        if search:
            haystack = " ".join(
                [
                    str(member.get("user_id", "")),
                    str(member.get("display_name", "")),
                    str(member.get("phone", "")),
                ]
            ).lower()
            if search.lower() not in haystack:
                return False
        if expire_within_days is not None:
            expire_at = _parse_time(str(member.get("expire_at") or ""))
            if expire_at > now + timedelta(days=expire_within_days):
                return False
        if active_within_days is not None:
            last_active = _parse_time(str(member.get("last_active_at") or ""))
            if last_active < now - timedelta(days=active_within_days):
                return False
        return True

    filtered = [self._serialize_member_list_item(item) for item in items if _match(item)]
    return {
        "items": filtered,
        "page": page,
        "page_size": page_size,
        "pages": 1,
        "total": len(filtered),
        "filters": {
            "tier": tier,
            "risk_level": risk_level,
            "expire_within_days": expire_within_days,
            "active_within_days": active_within_days,
        },
    }


def batch_update_members(
    self,
    *,
    user_ids: list[str],
    action: str,
    operator: str,
    reason: str = "",
    days: int | None = None,
    tier: str | None = None,
) -> dict[str, Any]:
    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for user_id in user_ids:
        try:
            if action == "grant":
                member = self.grant_membership(user_id=user_id, days=days or 30, tier=tier or "vip", operator=operator, reason=reason)
            elif action == "revoke":
                member = self.revoke_membership(user_id=user_id, operator=operator, reason=reason)
            else:
                member = self.update_membership(user_id=user_id, days=days, tier=tier, operator=operator, reason=reason)
            succeeded.append({"user_id": user_id, "member": member})
        except Exception as exc:
            failed.append({"user_id": user_id, "detail": str(exc)})
    return {
        "action": action,
        "success_count": len(succeeded),
        "failure_count": len(failed),
        "items": succeeded,
        "failed": failed,
    }


def list_audit_log(
    self,
    page: int = 1,
    page_size: int = 50,
    target_user: str | None = None,
    operator: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    rows = list(reversed(self._load().get("audit_log", [])))
    if target_user:
        rows = [row for row in rows if str(row.get("target_user") or "") == target_user]
    if operator:
        rows = [row for row in rows if str(row.get("operator") or "") == operator]
    if action:
        rows = [row for row in rows if str(row.get("action") or "") == action]
    return {
        "items": rows[(page - 1) * page_size : page * page_size],
        "page": page,
        "page_size": page_size,
        "pages": max(1, math.ceil(len(rows) / page_size)),
        "total": len(rows),
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run:

```bash
python -m pytest tests/services/member_console/test_service.py -k "expiry_window or batch_update_members or list_audit_log_supports" -v
```

Expected:

```text
PASSED tests/services/member_console/test_service.py::test_list_members_supports_expiry_window_and_operational_flags
PASSED tests/services/member_console/test_service.py::test_batch_update_members_returns_success_and_failure_buckets
PASSED tests/services/member_console/test_service.py::test_list_audit_log_supports_target_user_and_action_filters
```

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/member_console/service.py tests/services/member_console/test_service.py
git commit -m "feat: extend member console operations"
```

---

### Task 2: 暴露 member router 的新增运营接口

**Files:**
- Modify: `deeptutor/api/routers/member.py`
- Modify: `tests/api/test_member_router_auth.py`

- [ ] **Step 1: 写失败测试，锁定 batch / audit / export 路由和管理员权限**

```python
def test_member_router_exposes_batch_and_audit_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {
                "batch_update_members": staticmethod(
                    lambda **kwargs: {"action": kwargs["action"], "success_count": 2, "failure_count": 0, "items": []}
                ),
                "list_audit_log": staticmethod(
                    lambda **kwargs: {"items": [{"id": "audit_1", "action": "grant"}], "page": 1, "page_size": 20, "pages": 1, "total": 1}
                ),
                "export_members_csv": staticmethod(
                    lambda **kwargs: {"filename": "members.csv", "content": "user_id,display_name\\nu1,陈同学\\n"}
                ),
            },
        )(),
    )

    with TestClient(app) as client:
        batch = client.post(
            "/api/v1/member/batch",
            json={"user_ids": ["u1", "u2"], "action": "grant", "days": 30, "tier": "vip", "reason": "batch"},
        )
        audit = client.get("/api/v1/member/audit-log?page=1&page_size=20&action=grant")
        exported = client.get("/api/v1/member/export?status=active&tier=vip")

    assert batch.status_code == 200
    assert batch.json()["success_count"] == 2
    assert audit.status_code == 200
    assert audit.json()["items"][0]["id"] == "audit_1"
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
```

- [ ] **Step 2: 跑测试确认当前失败**

Run:

```bash
python -m pytest tests/api/test_member_router_auth.py -k "batch_and_audit_endpoints" -v
```

Expected:

```text
FAILED tests/api/test_member_router_auth.py::test_member_router_exposes_batch_and_audit_endpoints
```

- [ ] **Step 3: 写最小 router 实现**

```python
class BatchActionRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list, min_length=1, max_length=100)
    action: str = Field(..., pattern=r"^(grant|update|revoke)$")
    days: int | None = Field(default=None, ge=-3650, le=3650)
    tier: str | None = None
    reason: str = ""


@router.post("/batch")
async def member_batch_action(
    body: BatchActionRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    return service.batch_update_members(
        user_ids=body.user_ids,
        action=body.action,
        days=body.days,
        tier=body.tier,
        operator=current_user.user_id,
        reason=body.reason,
    )


@router.get("/audit-log")
async def member_audit_log(
    page: int = 1,
    page_size: int = 50,
    target_user: str | None = None,
    operator: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    return service.list_audit_log(
        page=page,
        page_size=page_size,
        target_user=target_user,
        operator=operator,
        action=action,
    )


@router.get("/export")
async def member_export(
    status: str | None = None,
    tier: str | None = None,
    risk_level: str | None = None,
) -> Response:
    export = service.export_members_csv(status=status, tier=tier, risk_level=risk_level)
    return Response(
        content=export["content"],
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export["filename"]}"'},
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run:

```bash
python -m pytest tests/api/test_member_router_auth.py -k "batch_and_audit_endpoints" -v
```

Expected:

```text
PASSED tests/api/test_member_router_auth.py::test_member_router_exposes_batch_and_audit_endpoints
```

- [ ] **Step 5: Commit**

```bash
git add deeptutor/api/routers/member.py tests/api/test_member_router_auth.py
git commit -m "feat: add member admin router endpoints"
```

---

### Task 3: 增强 BI 聚合，输出老板工作台 handoff 数据

**Files:**
- Modify: `deeptutor/services/bi_service.py`
- Modify: `deeptutor/api/routers/bi.py`
- Modify: `tests/api/test_bi_router.py`

- [ ] **Step 1: 写失败测试，锁定老板工作台风险队列和重点会员输出**

```python
def test_bi_overview_exposes_risk_queue_and_member_handoff(bi_service: BIService) -> None:
    app = _build_app(bi_service)
    bi_router_module._bi_public_enabled = lambda: True

    with TestClient(app) as client:
        response = client.get("/api/v1/bi/overview?days=30")

    assert response.status_code == 200
    body = response.json()
    workbench = body["boss_workbench"]
    assert workbench["risk_queue"][0]["bucket"] == "expiring_soon"
    assert workbench["risk_queue"][0]["handoff_filters"]["status"] == "expiring_soon"
    assert workbench["watchlist"][0]["user_id"] == "u2"
```

- [ ] **Step 2: 跑测试确认当前失败**

Run:

```bash
python -m pytest tests/api/test_bi_router.py -k "risk_queue_and_member_handoff" -v
```

Expected:

```text
FAILED tests/api/test_bi_router.py::test_bi_overview_exposes_risk_queue_and_member_handoff
```

- [ ] **Step 3: 写最小实现，让 BI 只读输出老板工作台数据**

```python
def _build_boss_workbench(self, *, days: int, overview: dict[str, Any], member_stats: dict[str, Any]) -> dict[str, Any]:
    samples = list(member_stats.get("samples", []))
    risks = list(member_stats.get("risks", []))

    risk_queue = [
        {
            "bucket": "expiring_soon",
            "label": "即将到期会员",
            "count": next((item.get("value", 0) for item in risks if item.get("label") == "expiring_soon"), 0),
            "handoff_filters": {"status": "expiring_soon"},
        },
        {
            "bucket": "high_risk",
            "label": "高风险会员",
            "count": next((item.get("value", 0) for item in risks if item.get("label") == "high"), 0),
            "handoff_filters": {"risk_level": "high"},
        },
    ]

    return {
        "days": days,
        "kpis": overview.get("cards", []),
        "risk_queue": risk_queue,
        "watchlist": samples[:6],
    }


async def get_overview(self, days: int = 30, capability: str | None = None, entrypoint: str | None = None, tier: str | None = None):
    overview = await self._build_overview(days=days, capability=capability, entrypoint=entrypoint, tier=tier)
    member_stats = await self.get_member_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)
    overview["boss_workbench"] = self._build_boss_workbench(days=days, overview=overview, member_stats=member_stats)
    return overview
```

- [ ] **Step 4: 跑测试确认通过**

Run:

```bash
python -m pytest tests/api/test_bi_router.py -k "risk_queue_and_member_handoff" -v
```

Expected:

```text
PASSED tests/api/test_bi_router.py::test_bi_overview_exposes_risk_queue_and_member_handoff
```

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/bi_service.py deeptutor/api/routers/bi.py tests/api/test_bi_router.py
git commit -m "feat: add boss workbench bi handoff data"
```

---

### Task 4: 扩展前端 API client 与统一工作台状态

**Files:**
- Modify: `web/lib/member-api.ts`
- Modify: `web/lib/bi-api.ts`
- Modify: `web/app/(workspace)/bi/BiPageClient.tsx`
- Create: `tests/web/test_bi_member_admin_surface.py`

- [ ] **Step 1: 写失败的源码 smoke test，锁定四工作区和 `/member` 兼容复用**

```python
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
```

- [ ] **Step 2: 跑测试确认当前失败**

Run:

```bash
python -m pytest tests/web/test_bi_member_admin_surface.py -v
```

Expected:

```text
FAILED tests/web/test_bi_member_admin_surface.py::test_bi_page_client_exposes_four_admin_tabs
FAILED tests/web/test_bi_member_admin_surface.py::test_member_page_reuses_bi_admin_workspace
```

- [ ] **Step 3: 写最小前端契约与工作台状态实现**

```ts
export interface MemberBatchActionResult {
  action: string;
  success_count: number;
  failure_count: number;
  items: Array<{ user_id: string }>;
  failed: Array<{ user_id: string; detail: string }>;
}

export interface MemberAuditLogResponse {
  items: Array<{
    id: string;
    target_user?: string;
    operator?: string;
    action?: string;
    reason?: string;
    created_at: string;
  }>;
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export async function batchUpdateMembers(payload: {
  user_ids: string[];
  action: "grant" | "update" | "revoke";
  days?: number;
  tier?: string;
  reason?: string;
}): Promise<MemberBatchActionResult> {
  const response = await fetch(apiUrl("/api/v1/member/batch"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return expectJson<MemberBatchActionResult>(response);
}

export async function getMemberAuditLog(params: Record<string, string | number | undefined>): Promise<MemberAuditLogResponse> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === "") return;
    query.set(key, String(value));
  });
  const response = await fetch(apiUrl(`/api/v1/member/audit-log?${query.toString()}`), { cache: "no-store" });
  return expectJson<MemberAuditLogResponse>(response);
}

const ADMIN_TABS = ["boss-workbench", "member-ops", "learner-360", "audit"] as const;
type AdminTab = (typeof ADMIN_TABS)[number];
```

```tsx
const searchTab = searchParams.get("tab");
const initialTab: AdminTab =
  searchTab === "member-ops" || searchTab === "learner-360" || searchTab === "audit" ? searchTab : "boss-workbench";
const [activeTab, setActiveTab] = useState<AdminTab>(initialTab);

const jumpToMemberOps = useCallback((filters?: Record<string, string>) => {
  setPendingMemberFilters(filters ?? {});
  setActiveTab("member-ops");
}, []);
```

```tsx
export default function MemberPage() {
  return <Redirect href="/bi?tab=member-ops" />;
}
```

- [ ] **Step 4: 跑测试并做前端构建校验**

Run:

```bash
python -m pytest tests/web/test_bi_member_admin_surface.py -v
cd web && npm run build
```

Expected:

```text
PASSED tests/web/test_bi_member_admin_surface.py::test_bi_page_client_exposes_four_admin_tabs
PASSED tests/web/test_bi_member_admin_surface.py::test_member_page_reuses_bi_admin_workspace
✓ Compiled successfully
```

- [ ] **Step 5: Commit**

```bash
git add web/lib/member-api.ts web/lib/bi-api.ts web/app/\(workspace\)/bi/BiPageClient.tsx web/app/\(workspace\)/member/page.tsx tests/web/test_bi_member_admin_surface.py
git commit -m "feat: unify bi member admin workspace state"
```

---

### Task 5: 落地会员运营表格、学员 360 和经营审计 UI

**Files:**
- Modify: `web/app/(workspace)/bi/_components/BiBossHomeTab.tsx`
- Modify: `web/app/(workspace)/bi/_components/BiMemberOpsTab.tsx`
- Create: `web/app/(workspace)/bi/_components/BiMemberAdminTable.tsx`
- Create: `web/app/(workspace)/bi/_components/BiMember360Panel.tsx`
- Create: `web/app/(workspace)/bi/_components/BiAuditTab.tsx`

- [ ] **Step 1: 写失败的源码 smoke test，锁定高密后台组件挂载**

```python
def test_bi_member_ops_tab_uses_table_and_detail_panel() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_components" / "BiMemberOpsTab.tsx").read_text(encoding="utf-8")

    assert "BiMemberAdminTable" in source
    assert "BiMember360Panel" in source


def test_bi_page_client_mounts_audit_tab() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "BiPageClient.tsx").read_text(encoding="utf-8")

    assert "BiAuditTab" in source
```

- [ ] **Step 2: 跑测试确认当前失败**

Run:

```bash
python -m pytest tests/web/test_bi_member_admin_surface.py -k "table_and_detail_panel or audit_tab" -v
```

Expected:

```text
FAILED tests/web/test_bi_member_admin_surface.py::test_bi_member_ops_tab_uses_table_and_detail_panel
FAILED tests/web/test_bi_member_admin_surface.py::test_bi_page_client_mounts_audit_tab
```

- [ ] **Step 3: 写最小 UI 实现，先保证结构正确，再做样式抛光**

```tsx
export function BiMemberAdminTable({
  items,
  selectedIds,
  onToggle,
  onOpen,
}: {
  items: MemberListItem[];
  selectedIds: string[];
  onToggle: (userId: string) => void;
  onOpen: (userId: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-3xl border border-[var(--border)]/60 bg-[var(--background)]">
      <table className="min-w-full text-sm">
        <thead className="bg-[var(--secondary)]/40 text-[var(--muted-foreground)]">
          <tr>
            <th className="px-4 py-3 text-left">会员</th>
            <th className="px-4 py-3 text-left">等级</th>
            <th className="px-4 py-3 text-left">状态</th>
            <th className="px-4 py-3 text-left">最近活跃</th>
            <th className="px-4 py-3 text-left">到期时间</th>
            <th className="px-4 py-3 text-left">风险</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.user_id} className="border-t border-[var(--border)]/40">
              <td className="px-4 py-3">
                <button type="button" onClick={() => onOpen(item.user_id)} className="font-medium text-left">
                  {item.display_name}
                </button>
              </td>
              <td className="px-4 py-3">{item.tier}</td>
              <td className="px-4 py-3">{item.status}</td>
              <td className="px-4 py-3">{item.last_active_at}</td>
              <td className="px-4 py-3">{item.expire_at}</td>
              <td className="px-4 py-3">{item.risk_level}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

```tsx
export function BiMember360Panel({
  member,
  onGrant,
  onExtend,
  onRevoke,
}: {
  member: MemberDetail | null;
  onGrant: () => void;
  onExtend: () => void;
  onRevoke: () => void;
}) {
  if (!member) {
    return <div className="rounded-3xl border border-dashed px-5 py-8 text-sm text-[var(--muted-foreground)]">请选择一个会员查看 360。</div>;
  }
  return (
    <aside className="space-y-4 rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5">
      <div>
        <p className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">LEARNER 360</p>
        <h3 className="mt-2 text-xl font-semibold text-[var(--foreground)]">{member.display_name}</h3>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <InfoLine label="等级" value={member.tier} />
        <InfoLine label="状态" value={member.status} />
        <InfoLine label="当前焦点" value={member.focus_topic || "--"} />
        <InfoLine label="到期时间" value={member.expire_at} />
      </div>
      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={onGrant} className="primary-button">开通</button>
        <button type="button" onClick={onExtend} className="secondary-button">续期 90 天</button>
        <button type="button" onClick={onRevoke} className="secondary-button">撤销</button>
      </div>
    </aside>
  );
}
```

```tsx
export function BiAuditTab({ audit, loading }: { audit: MemberAuditLogResponse | null; loading?: boolean }) {
  return (
    <div className="space-y-4">
      <SectionHeader title="经营审计" extra={loading ? "加载中" : `${audit?.total ?? 0} 条记录`} />
      <SimpleListCard
        title="最近操作"
        items={(audit?.items ?? []).map((item) => `${item.created_at} · ${item.operator ?? "--"} · ${item.action ?? "--"} · ${item.target_user ?? "--"}`)}
        emptyText="暂无审计记录。"
      />
    </div>
  );
}
```

- [ ] **Step 4: 跑源码 smoke + 构建校验，并做一次本地 IAB 验证**

Run:

```bash
python -m pytest tests/web/test_bi_member_admin_surface.py -v
cd web && npm run build
```

Expected:

```text
PASSED tests/web/test_bi_member_admin_surface.py::test_bi_member_ops_tab_uses_table_and_detail_panel
PASSED tests/web/test_bi_member_admin_surface.py::test_bi_page_client_mounts_audit_tab
✓ Compiled successfully
```

Manual:

- 打开 `http://localhost:3001/bi`
- 确认顶部存在 `老板工作台 / 会员运营 / 学员 360 / 经营审计`
- 从老板工作台点击风险项可以落到会员运营
- 在会员运营表格点击会员可打开学员 360
- 经营审计可以正常展示空态或真实列表

- [ ] **Step 5: Commit**

```bash
git add web/app/\(workspace\)/bi/_components/BiBossHomeTab.tsx web/app/\(workspace\)/bi/_components/BiMemberOpsTab.tsx web/app/\(workspace\)/bi/_components/BiMemberAdminTable.tsx web/app/\(workspace\)/bi/_components/BiMember360Panel.tsx web/app/\(workspace\)/bi/_components/BiAuditTab.tsx tests/web/test_bi_member_admin_surface.py
git commit -m "feat: build unified bi member admin interface"
```

---

### Task 6: 端到端验证与阿里云发布

**Files:**
- Reuse: `docs/zh/guide/aliyun-deploy.md`
- Reuse: `scripts/deploy_aliyun.sh`
- Reuse: `scripts/server_bootstrap_aliyun.sh`
- Reuse: `scripts/verify_aliyun_public_endpoints.sh`

- [ ] **Step 1: 先跑本地完整回归**

Run:

```bash
python -m pytest tests/services/member_console/test_service.py tests/api/test_member_router_auth.py tests/api/test_bi_router.py tests/web/test_bi_member_admin_surface.py -v
cd web && npm run build
```

Expected:

```text
... all selected tests PASSED ...
✓ Compiled successfully
```

- [ ] **Step 2: 用本地浏览器 / IAB 做交互回归**

Checklist:

- `http://localhost:3001/bi` 页面能正常打开
- 老板工作台首屏出现经营 KPI、风险队列、趋势和重点会员
- 点击风险项能进入带筛选的会员运营区
- 会员运营区可批量选择会员
- 点击会员能打开学员 360
- 审计页可展示真实数据或空态
- `/member` 进入后能跳到统一后台入口，不再是割裂旧页

- [ ] **Step 3: 发布到阿里云前做发布闸口检查**

Run:

```bash
git branch --show-current
git status --short
python scripts/check_contract_guard.py
python scripts/verify_runtime_assets.py
```

Expected:

```text
main
... only intended changes ...
contract guard passed
runtime assets verified
```

- [ ] **Step 4: 发布到阿里云**

如果当前工作树可走完整发布路径：

```bash
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/deploy_aliyun.sh
```

如果当前环境因 worktree/branch 护栏不适合整仓发布，先在干净候选 worktree 执行上面的命令；不要直接绕过护栏发脏树。

Expected:

```text
docker compose up -d --build
verify_aliyun_public_endpoints.sh passed
verify_aliyun_observability.sh passed
```

- [ ] **Step 5: 公网验收**

Run:

```bash
curl -fsS https://test2.yousenjiaoyu.com/bi >/tmp/bi.html && head -n 20 /tmp/bi.html
curl -fsS https://test2.yousenjiaoyu.com/healthz
curl -fsS https://test2.yousenjiaoyu.com/readyz
```

Expected:

```text
/bi 返回新的会员后台页面 HTML
healthz 返回 ok
readyz 返回 ready
```

- [ ] **Step 6: Commit / push / merge 收口**

```bash
git add -A
git commit -m "feat: launch unified bi member admin workspace"
git push origin main
```

---

## 自检

### Spec 覆盖

- `老板工作台`
  - Task 3, Task 5, Task 6 覆盖
- `会员运营`
  - Task 1, Task 2, Task 4, Task 5 覆盖
- `学员 360`
  - Task 4, Task 5 覆盖
- `经营审计`
  - Task 1, Task 2, Task 4, Task 5 覆盖
- `authority 不新增第二套状态源`
  - Task 1, Task 3 通过 service / BI 聚合边界覆盖
- `阿里云上线与公网验收`
  - Task 6 覆盖

### Placeholder Scan

- 本计划不包含 `TBD` / `TODO` / “类似 Task N” 之类占位写法
- 每个代码步骤都给了最小实现骨架、文件路径和验证命令

### Type Consistency

- 会员后台四工作区统一使用：
  - `"boss-workbench"`
  - `"member-ops"`
  - `"learner-360"`
  - `"audit"`
- 批量动作统一使用 `batchUpdateMembers` / `batch_update_members`
- 审计接口统一使用 `getMemberAuditLog` / `list_audit_log`

