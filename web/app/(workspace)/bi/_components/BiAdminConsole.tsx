/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * BI 权限管理控制台 — 对标 Grafana / Metabase 的团队权限管理。
 *
 * 一个独立、显眼的权限控制台，聚合：
 *  - 管理员清单（角色徽标 / 可访问 tab / 来源 / 授权人时间）
 *  - 搜索会员 → 选人 → 定角色 → 添加（替代手敲 user_id）
 *  - 行内改角色（乐观更新 + 失败回滚）
 *  - 移除（二次确认）
 *  - 角色 × tab × 操作 权限矩阵（可视化，权限透明）
 *  - 权限变更审计时间线
 *
 * 数据 / token 单一来源：lib/bi-rbac.ts（getStoredBiAdminSession 的 bearer token）。
 * 门控：仅 can_manage_permissions（super_admin）能看到增删改；否则只读视图。
 * 配色：components/bi-cockpit/theme.ts 暖陶土橙板 + CockpitBg/CockpitPanel 大屏壳。
 */

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import {
  Check,
  Clock3,
  Loader2,
  Lock,
  RotateCcw,
  Save,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  UserPlus,
  Users,
  X,
} from 'lucide-react'
import {
  addAdmin,
  getMyRbac,
  listAdmins,
  listAdminAudit,
  listRoles,
  removeAdmin,
  searchMembers,
  setRole,
  setRolePermissions,
  setUserPermissions,
  type BiAdminAuditEntry,
  type BiAdminRecord,
  type BiMemberSearchResult,
  type BiRbacMe,
  type BiRbacRoles,
  type BiRoleDefinition,
  type BiRoleKey,
  type BiRoleMatrix,
} from '@/lib/bi-rbac'
import { CockpitBg, CockpitKpi, CockpitPanel, SectionLabel } from '@/components/bi-cockpit/Layout'
import { COCKPIT, SEMANTIC, SERIES_COLORS, alpha } from '@/components/bi-cockpit/theme'

const DANGER = '#E5736B'

/** 深比较两个权限矩阵是否等价（顺序无关，逐 tab 逐 action 对比）。 */
function matrixEquals(a: BiRoleMatrix, b: BiRoleMatrix): boolean {
  const tabs = new Set([...Object.keys(a), ...Object.keys(b)])
  for (const tab of tabs) {
    const sa = new Set(a[tab] ?? [])
    const sb = new Set(b[tab] ?? [])
    if (sa.size !== sb.size) return false
    for (const k of sa) if (!sb.has(k)) return false
  }
  return true
}

/** 不可变地切换某 tab 上某 action 的开关，返回新矩阵。 */
function toggleAction(matrix: BiRoleMatrix, tab: string, action: string): BiRoleMatrix {
  const current = matrix[tab] ?? []
  const next = current.includes(action) ? current.filter(a => a !== action) : [...current, action]
  return { ...matrix, [tab]: next }
}

/** 把矩阵规整成「仅含非空 tab」的稳定形态，用于提交与比较。 */
function pruneMatrix(matrix: BiRoleMatrix): BiRoleMatrix {
  const out: BiRoleMatrix = {}
  for (const [tab, actions] of Object.entries(matrix)) {
    if (actions.length > 0) out[tab] = [...actions]
  }
  return out
}

/** 角色徽标配色：super_admin 金 / admin 橙 / operator 蓝 / analyst 灰。 */
const ROLE_BADGE: Record<BiRoleKey, { bg: string; fg: string; border: string }> = {
  super_admin: {
    bg: alpha('#F2C24B', 0.16),
    fg: '#F4CE86',
    border: alpha('#F2C24B', 0.45),
  },
  admin: {
    bg: alpha(SERIES_COLORS[0], 0.16),
    fg: COCKPIT.accentBright,
    border: alpha(SERIES_COLORS[0], 0.42),
  },
  operator: {
    bg: alpha('#7FA8AE', 0.18),
    fg: '#9FC6CC',
    border: alpha('#7FA8AE', 0.42),
  },
  analyst: {
    bg: 'rgba(110,95,82,0.22)',
    fg: COCKPIT.textMuted,
    border: 'rgba(169,155,140,0.32)',
  },
}

function roleBadgeStyle(role: BiRoleKey) {
  return ROLE_BADGE[role] ?? ROLE_BADGE.analyst
}

const AUDIT_ACTION_LABEL: Record<string, string> = {
  add_admin: '新增管理员',
  set_role: '调整角色',
  remove_admin: '移除管理员',
}

function formatTs(ts?: string | null): string {
  if (!ts) return '—'
  const date = new Date(ts)
  if (Number.isNaN(date.getTime())) return ts
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function RoleBadge({ role, label }: { role: BiRoleKey; label: string }) {
  const s = roleBadgeStyle(role)
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold"
      style={{ background: s.bg, color: s.fg, border: `1px solid ${s.border}` }}
    >
      <ShieldCheck className="h-3 w-3" />
      {label}
    </span>
  )
}

function TabChips({ tabs, labelOf }: { tabs: string[]; labelOf: (key: string) => string }) {
  if (!tabs.length) {
    return <span className="text-[11px] text-slate-500">无可访问分区</span>
  }
  return (
    <span className="flex flex-wrap gap-1">
      {tabs.map(tab => (
        <span
          key={tab}
          className="rounded px-1.5 py-0.5 text-[10px]"
          style={{
            background: 'rgba(28,19,13,0.6)',
            color: COCKPIT.textMuted,
            border: `1px solid ${COCKPIT.grid}`,
          }}
        >
          {labelOf(tab)}
        </span>
      ))}
    </span>
  )
}

export function BiAdminConsole() {
  const [me, setMe] = useState<BiRbacMe | null>(null)
  const [roles, setRoles] = useState<BiRbacRoles | null>(null)
  const [admins, setAdmins] = useState<BiAdminRecord[]>([])
  const [audit, setAudit] = useState<BiAdminAuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [rowBusy, setRowBusy] = useState<string>('')
  const [confirmRemove, setConfirmRemove] = useState<string>('')
  // 精确到人：当前展开的「个人权限」编辑面板对应的 user_id（空 = 未展开）。
  const [permUser, setPermUser] = useState<string>('')

  // 添加管理员（搜索 → 选人 → 定角色）
  const [query, setQuery] = useState('')
  const [composing, setComposing] = useState(false)
  const [candidates, setCandidates] = useState<BiMemberSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [picked, setPicked] = useState<BiMemberSearchResult | null>(null)
  const [pickedRole, setPickedRole] = useState<BiRoleKey>('analyst')
  const [adding, setAdding] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const canManage = me?.can_manage_permissions ?? false

  const tabLabelOf = useCallback(
    (key: string) => roles?.tabs.find(t => t.key === key)?.label ?? key,
    [roles]
  )
  const assignableRoles = useMemo<BiRoleDefinition[]>(() => roles?.roles ?? [], [roles])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [meResult, rolesResult, adminsResult] = await Promise.all([
        getMyRbac(),
        listRoles(),
        listAdmins(),
      ])
      setMe(meResult)
      setRoles(rolesResult)
      setAdmins(adminsResult)
      // 审计只对 super_admin 开放，普通 admin 读会 403，单独兜底不阻塞主视图。
      if (meResult.can_manage_permissions) {
        try {
          setAudit(await listAdminAudit(200))
        } catch {
          setAudit([])
        }
      } else {
        setAudit([])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '权限数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const refreshAudit = useCallback(async () => {
    if (!canManage) return
    try {
      setAudit(await listAdminAudit(200))
    } catch {
      /* 审计刷新失败不阻塞主流程 */
    }
  }, [canManage])

  // 搜会员：debounce 350ms，输入法合成期间不触发。
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const q = query.trim()
    if (!canManage || composing || q.length === 0) {
      setCandidates([])
      setSearching(false)
      setSearchError('')
      return
    }
    setSearching(true)
    debounceRef.current = setTimeout(async () => {
      try {
        setCandidates(await searchMembers(q, 10))
        setSearchError('')
      } catch (e) {
        setCandidates([])
        setSearchError(e instanceof Error ? e.message : '搜索失败')
      } finally {
        setSearching(false)
      }
    }, 350)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query, canManage, composing])

  const onPick = useCallback((member: BiMemberSearchResult) => {
    setPicked(member)
    setPickedRole(member.current_role ?? 'analyst')
    setQuery('')
    setCandidates([])
    setSearchError('')
  }, [])

  const onAdd = useCallback(async () => {
    if (!picked || adding) return
    setAdding(true)
    setError('')
    try {
      const next = await addAdmin({
        user_id: picked.user_id,
        role: pickedRole,
        display_name: picked.display_name || undefined,
      })
      setAdmins(next)
      setPicked(null)
      await refreshAudit()
    } catch (e) {
      setError(e instanceof Error ? e.message : '添加管理员失败')
    } finally {
      setAdding(false)
    }
  }, [picked, pickedRole, adding, refreshAudit])

  const onChangeRole = useCallback(
    async (admin: BiAdminRecord, role: BiRoleKey) => {
      if (role === admin.role || rowBusy) return
      const prev = admins
      // 乐观更新
      setAdmins(current =>
        current.map(a =>
          a.user_id === admin.user_id
            ? { ...a, role, role_label: assignableRoles.find(r => r.key === role)?.label ?? role }
            : a
        )
      )
      setRowBusy(admin.user_id)
      setError('')
      try {
        const next = await setRole(admin.user_id, role)
        setAdmins(next)
        await refreshAudit()
      } catch (e) {
        setAdmins(prev) // 回滚
        setError(e instanceof Error ? e.message : '修改角色失败')
      } finally {
        setRowBusy('')
      }
    },
    [admins, assignableRoles, rowBusy, refreshAudit]
  )

  const onRemove = useCallback(
    async (admin: BiAdminRecord) => {
      if (rowBusy) return
      setRowBusy(admin.user_id)
      setConfirmRemove('')
      setError('')
      try {
        setAdmins(await removeAdmin(admin.user_id))
        await refreshAudit()
      } catch (e) {
        setError(e instanceof Error ? e.message : '移除管理员失败')
      } finally {
        setRowBusy('')
      }
    },
    [rowBusy, refreshAudit]
  )

  // 角色权限矩阵：保存某角色的完整 matrix（影响所有该角色管理员）。
  const onSaveRolePermissions = useCallback(
    async (role: BiRoleKey, matrix: BiRoleMatrix) => {
      const next = await setRolePermissions(role, pruneMatrix(matrix))
      setRoles(next)
      await refreshAudit()
    },
    [refreshAudit]
  )

  // 精确到人：保存某管理员个人权限覆盖（只提交的 tab 覆盖，其余回落角色默认）。
  const onSaveUserPermissions = useCallback(
    async (userId: string, overrides: BiRoleMatrix) => {
      const next = await setUserPermissions(userId, pruneMatrix(overrides))
      setAdmins(next)
      await refreshAudit()
    },
    [refreshAudit]
  )

  const counts = useMemo(() => {
    const by: Record<string, number> = {}
    for (const a of admins) by[a.role] = (by[a.role] ?? 0) + 1
    return by
  }, [admins])

  return (
    <CockpitBg className="p-4 md:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div
          className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em]"
          style={{ color: alpha(COCKPIT.accentBright, 0.9) }}
        >
          <ShieldCheck className="h-3.5 w-3.5" />
          Access &amp; Roles Console · 权限管理控制台
        </div>
        {!canManage && !loading ? (
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold"
            style={{
              background: 'rgba(110,95,82,0.22)',
              color: COCKPIT.textMuted,
              border: `1px solid ${COCKPIT.grid}`,
            }}
          >
            <Lock className="h-3 w-3" />
            只读视图 · 仅超级管理员可增删改
          </span>
        ) : null}
      </div>

      {/* 我的权限 + 角色分布 KPI */}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <CockpitKpi
          label="我的角色"
          value={me?.role_label ?? '—'}
          tone="cyan"
          icon={<ShieldCheck className="h-4 w-4" />}
          sub={me ? (me.can_manage_permissions ? '可管权限' : '不可管权限') : '加载中'}
        />
        <CockpitKpi
          label="管理员总数"
          value={admins.length}
          tone="violet"
          icon={<Users className="h-4 w-4" />}
        />
        <CockpitKpi label="超级管理员" value={counts.super_admin ?? 0} tone="amber" />
        <CockpitKpi label="管理员" value={counts.admin ?? 0} tone="cyan" />
        <CockpitKpi label="运营" value={counts.operator ?? 0} tone="teal" />
        <CockpitKpi label="分析师" value={counts.analyst ?? 0} tone="emerald" />
      </div>

      {error ? (
        <div
          className="mb-4 flex items-center gap-2 rounded-xl px-3 py-2 text-[12px]"
          style={{
            background: alpha(DANGER, 0.12),
            color: DANGER,
            border: `1px solid ${alpha(DANGER, 0.35)}`,
          }}
        >
          <X className="h-3.5 w-3.5" />
          {error}
        </div>
      ) : null}

      {/* 添加管理员（仅 super_admin） */}
      {canManage ? (
        <CockpitPanel
          glow
          className="mb-4"
          title="添加管理员"
          hint="搜索会员（手机号 / 姓名 / user_id）→ 选人 → 定角色 → 确认"
          icon={<UserPlus className="h-4 w-4" />}
        >
          {picked ? (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <div
                  className="grid h-9 w-9 place-items-center rounded-full text-sm font-bold"
                  style={{ background: alpha(SERIES_COLORS[0], 0.18), color: COCKPIT.accentBright }}
                >
                  {(picked.display_name || picked.user_id).slice(0, 1)}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-semibold" style={{ color: COCKPIT.text }}>
                    {picked.display_name || '未命名会员'}
                  </p>
                  <p className="truncate font-mono text-[11px] text-slate-500">
                    {picked.user_id} · {picked.phone_masked || '无手机号'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={pickedRole}
                  onChange={e => setPickedRole(e.target.value as BiRoleKey)}
                  className="h-9 rounded-lg px-2 text-[12px] outline-none"
                  style={{
                    background: 'rgba(20,14,10,0.7)',
                    border: `1px solid ${alpha(SERIES_COLORS[0], 0.3)}`,
                    color: COCKPIT.text,
                  }}
                  aria-label="选择角色"
                >
                  {assignableRoles.map(r => (
                    <option key={r.key} value={r.key}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => void onAdd()}
                  disabled={adding}
                  className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[12px] font-semibold disabled:opacity-50"
                  style={{ background: SERIES_COLORS[0], color: '#1a120c' }}
                >
                  {adding ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Check className="h-3.5 w-3.5" />
                  )}
                  确认添加
                </button>
                <button
                  type="button"
                  onClick={() => setPicked(null)}
                  disabled={adding}
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-2 text-[12px] disabled:opacity-50"
                  style={{ color: COCKPIT.textMuted, border: `1px solid ${COCKPIT.grid}` }}
                >
                  <X className="h-3.5 w-3.5" />
                  取消
                </button>
              </div>
            </div>
          ) : (
            <div className="relative">
              <Search
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
                size={15}
              />
              <input
                value={query}
                onChange={e => {
                  if (composing) return
                  setQuery(e.target.value)
                }}
                onCompositionStart={() => setComposing(true)}
                onCompositionEnd={e => {
                  setComposing(false)
                  setQuery(e.currentTarget.value)
                }}
                placeholder="输入手机号 / 姓名 / user_id 搜索会员…"
                className="w-full rounded-lg py-2 pl-9 pr-3 text-[13px] outline-none"
                style={{
                  background: 'rgba(20,14,10,0.7)',
                  border: `1px solid ${alpha(SERIES_COLORS[0], 0.25)}`,
                  color: COCKPIT.text,
                }}
                aria-label="搜索会员"
              />
              {query.trim() ? (
                <div
                  className="absolute z-20 mt-1.5 w-full overflow-hidden rounded-xl shadow-2xl"
                  style={{
                    background: COCKPIT.bgPanelSolid,
                    border: `1px solid ${alpha(SERIES_COLORS[0], 0.3)}`,
                  }}
                >
                  {searching ? (
                    <div className="flex items-center gap-2 px-3 py-3 text-[12px] text-slate-400">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      搜索中…
                    </div>
                  ) : searchError ? (
                    <div className="px-3 py-3 text-[12px]" style={{ color: DANGER }}>
                      {searchError}
                    </div>
                  ) : candidates.length === 0 ? (
                    <div className="px-3 py-3 text-[12px] text-slate-500">未找到匹配会员</div>
                  ) : (
                    <ul className="max-h-72 overflow-y-auto">
                      {candidates.map(m => (
                        <li key={m.user_id}>
                          <button
                            type="button"
                            onClick={() => onPick(m)}
                            className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition hover:bg-white/[0.05]"
                          >
                            <span className="flex items-center gap-3">
                              <span
                                className="grid h-8 w-8 place-items-center rounded-full text-[12px] font-bold"
                                style={{
                                  background: alpha(SERIES_COLORS[0], 0.16),
                                  color: COCKPIT.accentBright,
                                }}
                              >
                                {(m.display_name || m.user_id).slice(0, 1)}
                              </span>
                              <span className="min-w-0">
                                <span
                                  className="block truncate text-[13px]"
                                  style={{ color: COCKPIT.text }}
                                >
                                  {m.display_name || '未命名会员'}
                                </span>
                                <span className="block truncate font-mono text-[11px] text-slate-500">
                                  {m.user_id} · {m.phone_masked || '无手机号'}
                                </span>
                              </span>
                            </span>
                            {m.current_role ? (
                              <RoleBadge
                                role={m.current_role}
                                label={
                                  assignableRoles.find(r => r.key === m.current_role)?.label ??
                                  m.current_role
                                }
                              />
                            ) : (
                              <span className="text-[11px] text-slate-500">未授权</span>
                            )}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : null}
            </div>
          )}
        </CockpitPanel>
      ) : null}

      {/* 管理员清单 */}
      <SectionLabel icon={<Users className="h-4 w-4" />}>管理员清单</SectionLabel>
      <CockpitPanel className="mb-4">
        {loading ? (
          <div className="flex items-center gap-2 px-1 py-6 text-[12px] text-slate-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在加载权限数据…
          </div>
        ) : admins.length === 0 ? (
          <p className="px-1 py-6 text-center text-[12px] text-slate-500">暂无管理员记录</p>
        ) : (
          <div className="flex flex-col gap-2">
            {admins.map(a => (
              <div key={a.user_id} className="flex flex-col gap-0">
                <div
                  className="flex flex-col gap-3 rounded-xl px-3 py-3 lg:flex-row lg:items-center lg:justify-between"
                  style={{
                    background: 'rgba(28,19,13,0.55)',
                    border: `1px solid ${permUser === a.user_id ? alpha(SERIES_COLORS[0], 0.35) : COCKPIT.grid}`,
                    borderBottomLeftRadius: permUser === a.user_id ? 0 : undefined,
                    borderBottomRightRadius: permUser === a.user_id ? 0 : undefined,
                  }}
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div
                      className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-sm font-bold"
                      style={{
                        background: roleBadgeStyle(a.role).bg,
                        color: roleBadgeStyle(a.role).fg,
                      }}
                    >
                      {(a.display_name || a.user_id).slice(0, 1)}
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className="truncate text-[13px] font-semibold"
                          style={{ color: COCKPIT.text }}
                        >
                          {a.display_name || '未命名'}
                        </span>
                        <RoleBadge role={a.role} label={a.role_label} />
                        <span
                          className="rounded px-1.5 py-0.5 text-[10px]"
                          style={{
                            background:
                              a.source === 'env'
                                ? alpha(SERIES_COLORS[0], 0.16)
                                : 'rgba(110,95,82,0.2)',
                            color: a.source === 'env' ? COCKPIT.accentBright : COCKPIT.textMuted,
                          }}
                        >
                          {a.source === 'env' ? '系统引导 · 不可修改' : '运行时'}
                        </span>
                      </div>
                      <p className="mt-1 truncate font-mono text-[11px] text-slate-500">
                        {a.user_id}
                      </p>
                      <div className="mt-1.5">
                        <TabChips tabs={a.accessible_tabs} labelOf={tabLabelOf} />
                      </div>
                      {a.granted_by || a.granted_at ? (
                        <p className="mt-1 text-[10px] text-slate-500">
                          授权人 {a.granted_by || '—'} · {formatTs(a.granted_at)}
                        </p>
                      ) : null}
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    {canManage && a.editable ? (
                      <select
                        value={a.role}
                        onChange={e => void onChangeRole(a, e.target.value as BiRoleKey)}
                        disabled={rowBusy === a.user_id}
                        className="h-8 rounded-lg px-2 text-[12px] outline-none disabled:opacity-50"
                        style={{
                          background: 'rgba(20,14,10,0.7)',
                          border: `1px solid ${alpha(SERIES_COLORS[0], 0.3)}`,
                          color: COCKPIT.text,
                        }}
                        aria-label={`修改 ${a.display_name || a.user_id} 的角色`}
                      >
                        {assignableRoles.map(r => (
                          <option key={r.key} value={r.key}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    ) : null}
                    {canManage && a.editable ? (
                      <button
                        type="button"
                        onClick={() => setPermUser(cur => (cur === a.user_id ? '' : a.user_id))}
                        className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] font-semibold"
                        style={{
                          background:
                            permUser === a.user_id
                              ? alpha(SERIES_COLORS[0], 0.2)
                              : a.has_overrides
                                ? alpha(SERIES_COLORS[1], 0.16)
                                : 'rgba(110,95,82,0.18)',
                          color: a.has_overrides ? '#F2C572' : COCKPIT.textMuted,
                          border: `1px solid ${
                            a.has_overrides ? alpha(SERIES_COLORS[1], 0.4) : COCKPIT.grid
                          }`,
                        }}
                        aria-expanded={permUser === a.user_id}
                        aria-label={`编辑 ${a.display_name || a.user_id} 的个人权限`}
                      >
                        <SlidersHorizontal className="h-3 w-3" />
                        个人权限
                        {a.has_overrides ? (
                          <span
                            className="ml-0.5 rounded-full px-1 text-[9px]"
                            style={{ background: alpha(SERIES_COLORS[1], 0.3), color: '#F4CE86' }}
                          >
                            已覆盖
                          </span>
                        ) : null}
                      </button>
                    ) : null}
                    {rowBusy === a.user_id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />
                    ) : null}
                    {canManage && a.removable ? (
                      confirmRemove === a.user_id ? (
                        <span className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => void onRemove(a)}
                            disabled={rowBusy === a.user_id}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] font-semibold disabled:opacity-50"
                            style={{
                              background: alpha(DANGER, 0.16),
                              color: DANGER,
                              border: `1px solid ${alpha(DANGER, 0.4)}`,
                            }}
                          >
                            确认移除
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmRemove('')}
                            className="inline-flex items-center rounded-lg px-2 py-1.5 text-[11px]"
                            style={{ color: COCKPIT.textMuted }}
                          >
                            取消
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirmRemove(a.user_id)}
                          disabled={rowBusy === a.user_id}
                          className="inline-flex items-center gap-1 text-[12px] disabled:opacity-50"
                          style={{ color: DANGER }}
                          aria-label={`移除 ${a.display_name || a.user_id}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          移除
                        </button>
                      )
                    ) : !a.removable ? (
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
                        <Lock className="h-3 w-3" />
                        不可移除
                      </span>
                    ) : null}
                  </div>
                </div>
                {canManage && a.editable && permUser === a.user_id && roles ? (
                  <UserPermissionEditor
                    admin={a}
                    roles={roles}
                    onSave={overrides => onSaveUserPermissions(a.user_id, overrides)}
                    onClose={() => setPermUser('')}
                  />
                ) : null}
              </div>
            ))}
          </div>
        )}
      </CockpitPanel>

      {/* 角色权限矩阵 */}
      <SectionLabel icon={<ShieldCheck className="h-4 w-4" />}>角色权限矩阵</SectionLabel>
      <CockpitPanel
        className="mb-4"
        hint={
          canManage
            ? '点击格子开关角色在各分区的操作权限（角色级，影响所有该角色管理员）；超管恒全权·锁定'
            : '每个角色在各分区可执行的操作一览（查看 / 导出 / 写入 / 高危）'
        }
      >
        {roles ? (
          <RoleMatrix roles={roles} canManage={canManage} onSave={onSaveRolePermissions} />
        ) : (
          <p className="px-1 py-6 text-center text-[12px] text-slate-500">权限矩阵加载中…</p>
        )}
      </CockpitPanel>

      {/* 权限变更审计 */}
      {canManage ? (
        <>
          <SectionLabel icon={<Clock3 className="h-4 w-4" />}>权限变更审计</SectionLabel>
          <CockpitPanel hint="谁在何时把谁改成什么角色（最新在前）">
            {audit.length === 0 ? (
              <p className="px-1 py-6 text-center text-[12px] text-slate-500">暂无权限变更记录</p>
            ) : (
              <ol className="relative flex flex-col gap-3 pl-4">
                <span
                  aria-hidden
                  className="absolute bottom-2 left-[5px] top-2 w-px"
                  style={{ background: COCKPIT.grid }}
                />
                {audit.map((entry, idx) => (
                  <li key={`${entry.ts}-${entry.target}-${idx}`} className="relative">
                    <span
                      aria-hidden
                      className="absolute -left-[13px] top-1.5 h-2.5 w-2.5 rounded-full"
                      style={{
                        background: SERIES_COLORS[0],
                        boxShadow: `0 0 8px ${COCKPIT.borderGlow}`,
                      }}
                    />
                    <div className="flex flex-wrap items-center gap-2 text-[12px]">
                      <span
                        className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                        style={{ background: alpha(SERIES_COLORS[3], 0.18), color: '#E89A8E' }}
                      >
                        {AUDIT_ACTION_LABEL[entry.action] ?? entry.action}
                      </span>
                      <span className="font-mono text-[11px]" style={{ color: COCKPIT.text }}>
                        {entry.actor}
                      </span>
                      <span className="text-slate-500">→</span>
                      <span className="font-mono text-[11px]" style={{ color: COCKPIT.text }}>
                        {entry.target}
                      </span>
                      {entry.from_role || entry.to_role ? (
                        <span className="text-[11px] text-slate-400">
                          {entry.from_role ?? '—'} → {entry.to_role ?? '—'}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-0.5 text-[10px] text-slate-500">
                      {formatTs(entry.ts)}
                      {entry.detail ? ` · ${entry.detail}` : ''}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </CockpitPanel>
        </>
      ) : null}
    </CockpitBg>
  )
}

/**
 * 单个 action 开关芯片：on/off/locked 三态 + 「被覆盖」高亮。
 * locked=true 时灰显不可点（如 super_admin 行）。
 */
function ActionToggle({
  label,
  on,
  high,
  locked = false,
  overridden = false,
  onToggle,
}: {
  label: string
  on: boolean
  high: boolean
  locked?: boolean
  overridden?: boolean
  onToggle?: () => void
}) {
  const interactive = !locked && typeof onToggle === 'function'
  const base =
    'inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold transition'
  const style: CSSProperties = {
    background: on
      ? high
        ? alpha(SEMANTIC.danger, 0.18)
        : alpha(SERIES_COLORS[0], 0.16)
      : 'rgba(110,95,82,0.12)',
    color: on ? (high ? '#E89A8E' : COCKPIT.accentBright) : COCKPIT.textFaint,
    border: `1px solid ${
      overridden
        ? alpha(SERIES_COLORS[1], 0.6)
        : on
          ? high
            ? alpha(SEMANTIC.danger, 0.4)
            : alpha(SERIES_COLORS[0], 0.35)
          : 'transparent'
    }`,
    opacity: locked ? 0.45 : 1,
    cursor: interactive ? 'pointer' : locked ? 'not-allowed' : 'default',
  }
  const title = `${label}${on ? '：允许' : '：无'}${overridden ? ' · 个人覆盖' : ''}`
  if (interactive) {
    return (
      <button type="button" onClick={onToggle} className={base} style={style} title={title}>
        {on ? <Check className="h-2.5 w-2.5" /> : <X className="h-2.5 w-2.5" />}
        {label}
      </button>
    )
  }
  return (
    <span className={base} style={style} title={title}>
      {on ? <Check className="h-2.5 w-2.5" /> : <X className="h-2.5 w-2.5" />}
      {label}
    </span>
  )
}

/**
 * 角色 × tab × action 可编辑矩阵：行=角色，列=tab，单元格内 action 开关。
 * super_admin（editable=false）整行锁定灰显「恒全权·锁定」。
 * canManage=false 时整表只读。
 */
function RoleMatrix({
  roles,
  canManage,
  onSave,
}: {
  roles: BiRbacRoles
  canManage: boolean
  onSave: (role: BiRoleKey, matrix: BiRoleMatrix) => Promise<void>
}) {
  const actionLabelOf = useCallback(
    (key: string) => roles.actions.find(a => a.key === key)?.label ?? key,
    [roles.actions]
  )

  // 每个角色的本地草稿矩阵（乐观编辑），key=role。后端 payload 刷新时重置。
  const baseDrafts = useMemo<Record<string, BiRoleMatrix>>(() => {
    const out: Record<string, BiRoleMatrix> = {}
    for (const r of roles.roles) out[r.key] = pruneMatrix(r.matrix)
    return out
  }, [roles.roles])
  const [drafts, setDrafts] = useState<Record<string, BiRoleMatrix>>(baseDrafts)
  useEffect(() => {
    setDrafts(baseDrafts)
  }, [baseDrafts])

  const [savingRole, setSavingRole] = useState<string>('')
  const [rowError, setRowError] = useState<{ role: string; msg: string } | null>(null)

  const draftOf = (role: BiRoleDefinition) => drafts[role.key] ?? pruneMatrix(role.matrix)

  const toggle = (role: BiRoleDefinition, tab: string, action: string) => {
    setDrafts(cur => ({
      ...cur,
      [role.key]: toggleAction(cur[role.key] ?? pruneMatrix(role.matrix), tab, action),
    }))
  }

  const save = async (role: BiRoleDefinition) => {
    if (savingRole) return
    const draft = draftOf(role)
    const prev = baseDrafts[role.key] ?? pruneMatrix(role.matrix)
    setSavingRole(role.key)
    setRowError(null)
    // 乐观：草稿已是最新；失败回滚到 prev。
    try {
      await onSave(role.key, draft)
    } catch (e) {
      setDrafts(cur => ({ ...cur, [role.key]: prev }))
      setRowError({ role: role.key, msg: e instanceof Error ? e.message : '保存失败' })
    } finally {
      setSavingRole('')
    }
  }

  const reset = (role: BiRoleDefinition) => {
    setDrafts(cur => ({ ...cur, [role.key]: pruneMatrix(role.default_matrix) }))
    setRowError(null)
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr>
            <th
              className="sticky left-0 z-10 px-2 py-2 text-left text-[11px] font-bold"
              style={{ color: COCKPIT.textMuted, background: COCKPIT.bgPanelSolid }}
            >
              角色 \ 分区
            </th>
            {roles.tabs.map(tab => (
              <th
                key={tab.key}
                className="px-2 py-2 text-center font-bold"
                style={{ color: COCKPIT.textMuted }}
              >
                {tab.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {roles.roles.map(role => {
            const draft = draftOf(role)
            const editable = canManage && role.editable
            const dirty =
              editable && !matrixEquals(draft, baseDrafts[role.key] ?? pruneMatrix(role.matrix))
            const isDefault = matrixEquals(draft, pruneMatrix(role.default_matrix))
            return (
              <tr key={role.key} style={{ borderTop: `1px solid ${COCKPIT.grid}` }}>
                <td
                  className="sticky left-0 z-10 px-2 py-2 align-top"
                  style={{ background: COCKPIT.bgPanelSolid }}
                >
                  <RoleBadge role={role.key} label={role.label} />
                  <p className="mt-1 max-w-[160px] text-[10px] leading-4 text-slate-500">
                    {role.description}
                  </p>
                  {canManage && !role.editable ? (
                    <span
                      className="mt-1.5 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-semibold"
                      style={{
                        background: alpha('#F2C24B', 0.16),
                        color: '#F4CE86',
                        border: `1px solid ${alpha('#F2C24B', 0.4)}`,
                      }}
                    >
                      <Lock className="h-2.5 w-2.5" />
                      恒全权·锁定
                    </span>
                  ) : null}
                  {editable ? (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => void save(role)}
                        disabled={!dirty || savingRole === role.key}
                        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-bold disabled:opacity-40"
                        style={{ background: SERIES_COLORS[0], color: '#1a120c' }}
                      >
                        {savingRole === role.key ? (
                          <Loader2 className="h-2.5 w-2.5 animate-spin" />
                        ) : (
                          <Save className="h-2.5 w-2.5" />
                        )}
                        保存
                      </button>
                      <button
                        type="button"
                        onClick={() => reset(role)}
                        disabled={isDefault || savingRole === role.key}
                        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] disabled:opacity-40"
                        style={{ color: COCKPIT.textMuted, border: `1px solid ${COCKPIT.grid}` }}
                        title="重置为代码默认权限"
                      >
                        <RotateCcw className="h-2.5 w-2.5" />
                        重置默认
                      </button>
                      {dirty ? (
                        <span className="text-[9px]" style={{ color: '#F4CE86' }}>
                          未保存
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {rowError?.role === role.key ? (
                    <p className="mt-1 text-[9px]" style={{ color: DANGER }}>
                      {rowError.msg}
                    </p>
                  ) : null}
                </td>
                {roles.tabs.map(tab => {
                  const granted = draft[tab.key] ?? []
                  return (
                    <td key={tab.key} className="px-2 py-2 text-center align-top">
                      <span className="flex flex-wrap justify-center gap-1">
                        {roles.actions.map(action => (
                          <ActionToggle
                            key={action.key}
                            label={actionLabelOf(action.key)}
                            on={granted.includes(action.key)}
                            high={action.key === 'high_risk'}
                            locked={!editable}
                            onToggle={
                              editable ? () => toggle(role, tab.key, action.key) : undefined
                            }
                          />
                        ))}
                      </span>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/**
 * 精确到人的个人权限编辑面板：展示该管理员的生效权限矩阵，可逐 tab 编辑。
 *
 * 语义（贴合后端契约）：保存时只提交「被改动的 tab」作为个人覆盖，
 * 未改动的 tab 仍跟随角色默认走。可一键清除全部覆盖回落角色默认。
 */
function UserPermissionEditor({
  admin,
  roles,
  onSave,
  onClose,
}: {
  admin: BiAdminRecord
  roles: BiRbacRoles
  onSave: (overrides: BiRoleMatrix) => Promise<void>
  onClose: () => void
}) {
  const actionLabelOf = useCallback(
    (key: string) => roles.actions.find(a => a.key === key)?.label ?? key,
    [roles.actions]
  )
  const tabLabelOf = useCallback(
    (key: string) => roles.tabs.find(t => t.key === key)?.label ?? key,
    [roles.tabs]
  )

  // 草稿从生效矩阵起步；已有的个人覆盖 tab 初始即标记为「被覆盖」。
  const baseEffective = useMemo(() => pruneMatrix(admin.effective_matrix), [admin.effective_matrix])
  const baseOverrideTabs = useMemo(
    () => new Set(Object.keys(pruneMatrix(admin.permission_overrides))),
    [admin.permission_overrides]
  )
  const [draft, setDraft] = useState<BiRoleMatrix>(baseEffective)
  // 本次会话中被「碰过」的 tab（用户点击切换或初始就是覆盖 tab）→ 提交为覆盖。
  const [touched, setTouched] = useState<Set<string>>(baseOverrideTabs)
  useEffect(() => {
    setDraft(baseEffective)
    setTouched(baseOverrideTabs)
  }, [baseEffective, baseOverrideTabs])

  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const roleLabel = roles.roles.find(r => r.key === admin.role)?.label ?? admin.role

  const toggle = (tab: string, action: string) => {
    setDraft(cur => toggleAction(cur, tab, action))
    setTouched(cur => {
      const next = new Set(cur)
      next.add(tab)
      return next
    })
  }

  // 仅提交「被碰过」的 tab 作为个人覆盖。
  const collectOverrides = (): BiRoleMatrix => {
    const out: BiRoleMatrix = {}
    for (const tab of touched) out[tab] = draft[tab] ?? []
    return out
  }

  const save = async () => {
    if (saving) return
    setSaving(true)
    setErr('')
    try {
      await onSave(collectOverrides())
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : '保存个人权限失败')
    } finally {
      setSaving(false)
    }
  }

  const clearAll = async () => {
    if (saving) return
    setSaving(true)
    setErr('')
    try {
      await onSave({}) // 空覆盖 = 回落角色默认
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : '清除个人覆盖失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="rounded-b-xl px-3 py-3"
      style={{
        background: 'rgba(20,14,10,0.7)',
        border: `1px solid ${alpha(SERIES_COLORS[0], 0.35)}`,
        borderTop: 'none',
      }}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div
          className="flex items-center gap-2 text-[12px] font-bold"
          style={{ color: COCKPIT.text }}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" style={{ color: COCKPIT.accentBright }} />
          个人权限 · {admin.display_name || admin.user_id}
          <span className="text-[10px] font-normal text-slate-500">角色默认：{roleLabel}</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex items-center gap-1 text-[11px]"
          style={{ color: COCKPIT.textMuted }}
        >
          <X className="h-3 w-3" />
          收起
        </button>
      </div>
      <p className="mb-2 text-[10px] leading-4 text-slate-500">
        只「改动过」的分区会写入个人覆盖（高亮金框），其余分区仍跟随角色默认。清除覆盖即整体回落角色默认。
      </p>

      <div className="flex flex-col gap-1.5">
        {roles.tabs.map(tab => {
          const granted = draft[tab.key] ?? []
          const overridden = touched.has(tab.key)
          return (
            <div
              key={tab.key}
              className="flex flex-col gap-1.5 rounded-lg px-2 py-1.5 sm:flex-row sm:items-center sm:justify-between"
              style={{
                background: overridden ? alpha(SERIES_COLORS[1], 0.08) : 'rgba(28,19,13,0.5)',
                border: `1px solid ${overridden ? alpha(SERIES_COLORS[1], 0.4) : COCKPIT.grid}`,
              }}
            >
              <span
                className="flex items-center gap-1.5 text-[11px]"
                style={{ color: COCKPIT.text }}
              >
                {tabLabelOf(tab.key)}
                {overridden ? (
                  <span
                    className="rounded px-1 text-[9px] font-semibold"
                    style={{ background: alpha(SERIES_COLORS[1], 0.3), color: '#F4CE86' }}
                  >
                    个人覆盖
                  </span>
                ) : (
                  <span className="text-[9px] text-slate-500">跟随角色</span>
                )}
              </span>
              <span className="flex flex-wrap gap-1">
                {roles.actions.map(action => (
                  <ActionToggle
                    key={action.key}
                    label={actionLabelOf(action.key)}
                    on={granted.includes(action.key)}
                    high={action.key === 'high_risk'}
                    overridden={overridden}
                    onToggle={() => toggle(tab.key, action.key)}
                  />
                ))}
              </span>
            </div>
          )
        })}
      </div>

      {err ? (
        <p className="mt-2 text-[10px]" style={{ color: DANGER }}>
          {err}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-[11px] font-bold disabled:opacity-50"
          style={{ background: SERIES_COLORS[0], color: '#1a120c' }}
        >
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
          保存个人权限
        </button>
        <button
          type="button"
          onClick={() => void clearAll()}
          disabled={saving || !admin.has_overrides}
          className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-[11px] disabled:opacity-40"
          style={{ color: COCKPIT.textMuted, border: `1px solid ${COCKPIT.grid}` }}
          title="清除该管理员的全部个人覆盖，回到角色默认"
        >
          <RotateCcw className="h-3 w-3" />
          清除覆盖·回落角色默认
        </button>
      </div>
    </div>
  )
}
