'use client'

/**
 * 管理员管理面板（系统运维 tab）。
 * 数据来自 /api/v1/bi/admins；env 引导管理员标 removable=false 不可删（防锁死）。
 * 添加立即生效，无需重启。
 */
import { useCallback, useEffect, useState } from 'react'
import { ShieldCheck, Trash2, UserPlus } from 'lucide-react'
import { addBiAdmin, listBiAdmins, removeBiAdmin, type BiAdminEntry } from '@/lib/bi-admins'
import { CockpitPanel } from './Layout'
import { COCKPIT, SERIES_COLORS, alpha } from './theme'

export function AdminManager() {
  const [admins, setAdmins] = useState<BiAdminEntry[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setAdmins(await listBiAdmins())
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const onAdd = async () => {
    const uid = input.trim()
    if (!uid || busy) return
    setBusy(true)
    try {
      setAdmins(await addBiAdmin(uid))
      setInput('')
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : '添加失败')
    } finally {
      setBusy(false)
    }
  }

  const onRemove = async (uid: string) => {
    if (busy) return
    setBusy(true)
    try {
      setAdmins(await removeBiAdmin(uid))
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : '移除失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <CockpitPanel
      glow
      title="管理员管理"
      hint="添加后立即生效，无需重启 · 系统引导管理员不可在此移除"
      icon={<ShieldCheck className="h-4 w-4" />}
    >
      <div className="mb-3 flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') void onAdd()
          }}
          placeholder="输入 user_id（可在会员运营页搜索复制）"
          className="flex-1 rounded-lg px-3 py-2 text-[13px] outline-none"
          style={{
            background: 'rgba(20,14,10,0.6)',
            border: `1px solid ${alpha(SERIES_COLORS[0], 0.25)}`,
            color: COCKPIT.text,
          }}
        />
        <button
          type="button"
          onClick={() => void onAdd()}
          disabled={busy || !input.trim()}
          className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-[13px] font-semibold disabled:opacity-50"
          style={{ background: SERIES_COLORS[0], color: '#1a120c' }}
        >
          <UserPlus className="h-3.5 w-3.5" />
          添加
        </button>
      </div>

      {error ? (
        <p className="mb-2 text-[12px]" style={{ color: '#E5736B' }}>
          {error}
        </p>
      ) : null}

      <ul className="flex flex-col gap-1.5">
        {admins.map(a => (
          <li
            key={a.user_id}
            className="flex items-center justify-between rounded-lg px-3 py-2 text-[13px]"
            style={{ background: 'rgba(28,19,13,0.55)', border: `1px solid ${COCKPIT.grid}` }}
          >
            <span className="flex items-center gap-2">
              <span className="font-mono" style={{ color: COCKPIT.text }}>
                {a.user_id}
              </span>
              <span
                className="rounded px-1.5 py-0.5 text-[10px]"
                style={{
                  background: a.source === 'env' ? alpha(SERIES_COLORS[0], 0.18) : 'rgba(110,95,82,0.2)',
                  color: a.source === 'env' ? COCKPIT.accentBright : COCKPIT.textMuted,
                }}
              >
                {a.source === 'env' ? '系统引导' : '运行时添加'}
              </span>
            </span>
            {a.removable ? (
              <button
                type="button"
                onClick={() => void onRemove(a.user_id)}
                disabled={busy}
                className="flex items-center gap-1 text-[12px] disabled:opacity-50"
                style={{ color: '#E5736B' }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                移除
              </button>
            ) : (
              <span className="text-[11px]" style={{ color: COCKPIT.textFaint }}>
                不可移除
              </span>
            )}
          </li>
        ))}
        {admins.length === 0 ? (
          <li className="text-[12px]" style={{ color: COCKPIT.textFaint }}>
            暂无管理员记录
          </li>
        ) : null}
      </ul>
    </CockpitPanel>
  )
}
