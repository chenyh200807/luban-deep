export default function BiLoading() {
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100" aria-busy="true">
      <div className="mx-auto max-w-7xl animate-pulse space-y-5">
        <div className="h-8 w-56 rounded-lg bg-slate-800" />
        <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
          <p className="text-sm font-medium text-slate-300">正在读取经营快照</p>
          <p className="mt-1 text-xs text-slate-500">会员、账务与运营指标将按各自数据 authority 展示。</p>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {[0, 1, 2].map(index => (
              <div key={index} className="h-28 rounded-2xl bg-slate-800/80" />
            ))}
          </div>
        </div>
      </div>
    </main>
  )
}
