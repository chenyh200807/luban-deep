/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { AlertCircle, ArrowDown, ArrowUp, ArrowUpDown, Inbox, Loader2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

// First-page cap. Plan §7.4: "5 万会员表必须虚拟滚动 + cursor 分页，首屏最多渲染 50 行"。
const DEFAULT_PAGE_SIZE = 50
const LARGE_SET_WARNING_THRESHOLD = 1000

export type BiTableColumn<T> = {
  key: string
  label: string
  align?: 'left' | 'right' | 'center'
  width?: string
  sortable?: boolean
  render: (row: T) => ReactNode
}

export type BiDataTableStatus = 'ok' | 'loading' | 'empty' | 'no-results' | 'error' | 'stale'

export type BiDataTableProps<T> = {
  columns: ReadonlyArray<BiTableColumn<T>>
  rows: ReadonlyArray<T>
  rowKey: (row: T) => string
  status: BiDataTableStatus
  errorMessage?: ReactNode
  staleNote?: ReactNode
  emptyTitle?: string
  emptyHint?: ReactNode
  noResultsHint?: ReactNode
  selectable?: boolean
  selectedKeys?: ReadonlySet<string>
  onToggleRow?: (key: string) => void
  onToggleAll?: (allSelected: boolean) => void
  sortKey?: string
  sortDir?: 'asc' | 'desc'
  onSort?: (key: string) => void
  onRowClick?: (row: T) => void
  rowAriaLabel?: (row: T) => string
  rowAction?: (row: T) => ReactNode
  caption?: string
  cursorFooter?: ReactNode
  // First-page row cap (default 50). When local rows.length > pageSize, the
  // table renders only the first N rows + a "load more" footer. Pair with
  // `cursor` for server-side pagination.
  pageSize?: number
  // Server-driven cursor pagination. If provided, the table calls onLoadMore
  // when the bottom sentinel becomes visible or the load-more button is clicked.
  cursor?: {
    hasMore: boolean
    onLoadMore: () => void
    loading?: boolean
    total?: number
  }
}

export function BiDataTable<T>({
  columns,
  rows,
  rowKey,
  status,
  errorMessage,
  staleNote,
  emptyTitle = '暂无数据',
  emptyHint,
  noResultsHint,
  selectable = false,
  selectedKeys,
  onToggleRow,
  onToggleAll,
  sortKey,
  sortDir,
  onSort,
  onRowClick,
  rowAriaLabel,
  rowAction,
  caption,
  cursorFooter,
  pageSize = DEFAULT_PAGE_SIZE,
  cursor,
}: BiDataTableProps<T>) {
  const [visibleCount, setVisibleCount] = useState(pageSize)
  const sentinelRef = useRef<HTMLTableRowElement | null>(null)

  // Derived clamp: keep visibleCount in [pageSize, rows.length] without an
  // effect-based reset (React 19 forbids cascading setState in effects). When
  // filters shrink rows below visibleCount, slice() naturally returns
  // rows.length items.
  const effectiveVisible = Math.min(Math.max(visibleCount, pageSize), rows.length || pageSize)

  // Stable refs for cursor callbacks/state so the effect doesn't tear down the
  // IntersectionObserver every time the parent re-renders with a fresh inline
  // cursor object. Read from refs inside the observer callback.
  const cursorHasMore = Boolean(cursor?.hasMore)
  const cursorLoading = Boolean(cursor?.loading)
  const cursorLoadMoreRef = useRef(cursor?.onLoadMore)
  useEffect(() => {
    cursorLoadMoreRef.current = cursor?.onLoadMore
  }, [cursor?.onLoadMore])

  // Auto-load more via IntersectionObserver when the bottom sentinel scrolls
  // into view. Either local page advance or server cursor.onLoadMore.
  useEffect(() => {
    const node = sentinelRef.current
    if (!node) return
    const localHasMore = effectiveVisible < rows.length
    if (!localHasMore && !cursorHasMore) return
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          if (localHasMore) {
            setVisibleCount(prev => Math.min(prev + pageSize, rows.length))
          } else if (cursorHasMore && !cursorLoading) {
            cursorLoadMoreRef.current?.()
          }
        }
      },
      { rootMargin: '120px' }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [effectiveVisible, rows.length, pageSize, cursorHasMore, cursorLoading])

  const visibleRows = useMemo(() => {
    if (rows.length <= pageSize) return rows
    return rows.slice(0, effectiveVisible)
  }, [rows, effectiveVisible, pageSize])

  const allSelected =
    selectable && visibleRows.length > 0 && visibleRows.every(r => selectedKeys?.has(rowKey(r)))

  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#0e1624] shadow-lg shadow-black/20">
      {staleNote && status === 'stale' ? (
        <div className="border-b border-amber-300/25 bg-amber-300/10 px-3 py-2 text-[11px] text-amber-100">
          {staleNote}
        </div>
      ) : null}
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[760px] border-separate border-spacing-0 bg-[#0e1624] text-xs text-slate-200">
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <thead>
            <tr className="text-left text-[11px] uppercase text-slate-400">
              {selectable ? (
                <th className="sticky top-0 z-[1] border-b border-white/10 bg-[#151d2b] px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label="全选当前页"
                    checked={allSelected}
                    onChange={() => onToggleAll?.(!allSelected)}
                    className="h-4 w-4 rounded border-slate-300"
                  />
                </th>
              ) : null}
              {columns.map(c => {
                const sorted = sortKey === c.key
                return (
                  <th
                    key={c.key}
                    aria-sort={
                      sorted
                        ? sortDir === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : c.sortable
                          ? 'none'
                          : undefined
                    }
                    className={`sticky top-0 z-[1] border-b border-white/10 bg-[#151d2b] px-3 py-2 font-bold ${
                      c.align === 'right'
                        ? 'text-right'
                        : c.align === 'center'
                          ? 'text-center'
                          : 'text-left'
                    }`}
                    style={c.width ? { width: c.width } : undefined}
                  >
                    {c.sortable && onSort ? (
                      <button
                        type="button"
                        onClick={() => onSort(c.key)}
                        className="inline-flex min-h-7 items-center gap-1 rounded-lg px-1.5 py-1 text-slate-300 transition hover:bg-cyan-300/10 hover:text-cyan-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/40"
                        aria-label={`按 ${c.label} ${sorted && sortDir === 'asc' ? '降序' : '升序'} 排序`}
                        title={`按${c.label}${sorted && sortDir === 'asc' ? '降序' : '升序'}排序`}
                      >
                        {c.label}
                        {sorted ? (
                          sortDir === 'asc' ? (
                            <ArrowUp className="h-3 w-3" aria-hidden />
                          ) : (
                            <ArrowDown className="h-3 w-3" aria-hidden />
                          )
                        ) : (
                          <ArrowUpDown className="h-3 w-3 opacity-45" aria-hidden />
                        )}
                      </button>
                    ) : (
                      c.label
                    )}
                  </th>
                )
              })}
              {rowAction ? (
                <th className="sticky right-0 top-0 z-[2] border-b border-l border-white/10 bg-[#151d2b] px-3 py-2 text-right font-bold">
                  动作
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {status === 'loading' ? (
              <LoadingRow span={columns.length + (selectable ? 1 : 0) + (rowAction ? 1 : 0)} />
            ) : null}
            {status === 'error' ? (
              <ErrorRow
                span={columns.length + (selectable ? 1 : 0) + (rowAction ? 1 : 0)}
                message={errorMessage}
              />
            ) : null}
            {status === 'empty' ? (
              <EmptyRow
                span={columns.length + (selectable ? 1 : 0) + (rowAction ? 1 : 0)}
                title={emptyTitle}
                hint={emptyHint}
              />
            ) : null}
            {status === 'no-results' ? (
              <NoResultsRow
                span={columns.length + (selectable ? 1 : 0) + (rowAction ? 1 : 0)}
                hint={noResultsHint}
              />
            ) : null}
            {(status === 'ok' || status === 'stale') &&
              visibleRows.map(row => {
                const key = rowKey(row)
                const clickable = Boolean(onRowClick)
                return (
                  <tr
                    key={key}
                    tabIndex={clickable ? 0 : undefined}
                    aria-label={clickable ? rowAriaLabel?.(row) : undefined}
                    onClick={clickable ? () => onRowClick?.(row) : undefined}
                    onKeyDown={
                      clickable
                        ? event => {
                            if (event.key !== 'Enter' && event.key !== ' ') return
                            event.preventDefault()
                            onRowClick?.(row)
                          }
                        : undefined
                    }
                    className={`group border-b border-white/5 bg-[#0e1624] last:border-0 hover:bg-cyan-300/[0.06] ${
                      clickable
                        ? 'cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyan-300/45'
                        : ''
                    }`}
                  >
                    {selectable ? (
                      <td
                        className="border-b border-white/5 bg-[#0e1624] px-3 py-2 align-top group-hover:bg-cyan-300/[0.04]"
                        onClick={event => event.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          aria-label={`选择 ${key}`}
                          checked={selectedKeys?.has(key) ?? false}
                          onChange={() => onToggleRow?.(key)}
                          className="h-4 w-4 rounded border-slate-300"
                        />
                      </td>
                    ) : null}
                    {columns.map(c => (
                      <td
                        key={c.key}
                        className={`border-b border-white/5 bg-[#0e1624] px-3 py-2 align-top text-slate-200 group-hover:bg-cyan-300/[0.04] ${
                          c.align === 'right'
                            ? 'text-right'
                            : c.align === 'center'
                              ? 'text-center'
                              : 'text-left'
                        }`}
                      >
                        {c.render(row)}
                      </td>
                    ))}
                    {rowAction ? (
                      <td
                        className="sticky right-0 border-b border-l border-white/10 bg-[#101622] px-3 py-2 text-right align-top group-hover:bg-[#102035]"
                        onClick={event => event.stopPropagation()}
                      >
                        {rowAction(row)}
                      </td>
                    ) : null}
                  </tr>
                )
              })}
            {(status === 'ok' || status === 'stale') &&
            (effectiveVisible < rows.length || cursor?.hasMore) ? (
              <tr ref={sentinelRef} aria-hidden data-bi-table-sentinel>
                <td
                  colSpan={columns.length + (selectable ? 1 : 0) + (rowAction ? 1 : 0)}
                  className="px-3 py-2 text-center text-[11px] text-slate-400"
                >
                  {cursor?.loading ? '正在加载下一页…' : '滚动到底自动加载下一页'}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {(status === 'ok' || status === 'stale') &&
      (rows.length > pageSize || cursor?.hasMore || cursorFooter) ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] text-slate-400">
          <span>
            显示 {visibleRows.length} / {cursor?.total ?? rows.length}
            {rows.length >= LARGE_SET_WARNING_THRESHOLD ? (
              <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">
                大集合 ≥ {LARGE_SET_WARNING_THRESHOLD} · 建议加筛选或 cursor 分页
              </span>
            ) : null}
          </span>
          <span className="flex items-center gap-2">
            {cursorFooter}
            {effectiveVisible < rows.length ? (
              <button
                type="button"
                onClick={() => setVisibleCount(prev => Math.min(prev + pageSize, rows.length))}
                className="rounded-lg border border-white/10 bg-white/[0.06] px-2 py-0.5 text-slate-200 hover:bg-white/10"
                aria-label={`加载下一页 (${pageSize} 行)`}
              >
                加载下一页
              </button>
            ) : null}
            {effectiveVisible >= rows.length && cursor?.hasMore ? (
              <button
                type="button"
                disabled={cursor.loading}
                onClick={() => cursor.onLoadMore()}
                className="rounded-lg border border-white/10 bg-white/[0.06] px-2 py-0.5 text-slate-200 hover:bg-white/10 disabled:opacity-50"
                aria-label="从服务端加载下一页"
              >
                {cursor.loading ? '加载中…' : '加载下一页'}
              </button>
            ) : null}
          </span>
        </div>
      ) : null}
    </div>
  )
}

function LoadingRow({ span }: { span: number }) {
  return (
    <tr>
      <td className="px-3 py-10 text-center text-slate-400" colSpan={span}>
        <span className="inline-flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          加载中…
        </span>
      </td>
    </tr>
  )
}

function ErrorRow({ span, message }: { span: number; message?: ReactNode }) {
  return (
    <tr>
      <td className="bg-[#0e1624] px-3 py-10 text-center text-rose-200" colSpan={span}>
        <span className="inline-flex items-center gap-2">
          <AlertCircle className="h-4 w-4" aria-hidden />
          {message ?? '数据加载失败，请重试。'}
        </span>
      </td>
    </tr>
  )
}

function EmptyRow({ span, title, hint }: { span: number; title: string; hint?: ReactNode }) {
  return (
    <tr>
      <td className="px-3 py-10 text-center text-slate-400" colSpan={span}>
        <div className="inline-flex flex-col items-center gap-1">
          <Inbox className="h-5 w-5" aria-hidden />
          <span className="font-medium text-slate-200">{title}</span>
          {hint ? <span className="text-[11px] text-slate-400">{hint}</span> : null}
        </div>
      </td>
    </tr>
  )
}

function NoResultsRow({ span, hint }: { span: number; hint?: ReactNode }) {
  return (
    <tr>
      <td className="px-3 py-10 text-center text-slate-400" colSpan={span}>
        <div className="inline-flex flex-col items-center gap-1">
          <span className="font-medium text-slate-200">当前筛选无结果</span>
          {hint ?? <span className="text-[11px] text-slate-400">尝试放宽条件或清除筛选。</span>}
        </div>
      </td>
    </tr>
  )
}
