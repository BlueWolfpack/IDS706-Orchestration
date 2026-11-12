import type { LoopRunRecord } from '../api/gateway'

function fmtScore(v: number | null | undefined): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(3) : '—'
}

function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

type Props = {
  runs: LoopRunRecord[]
  loading?: boolean
  selectedRunId?: string | null
  onRefresh?: () => void
  /** Load this run into the main lab panels (timeline, scores, meta). */
  onOpenRun?: (run: LoopRunRecord) => void
}

export function SimpleLoopRunHistory({
  runs,
  loading,
  selectedRunId,
  onRefresh,
  onOpenRun,
}: Props) {
  return (
    <section className="border border-line bg-panel/40 px-4 py-4">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="font-display text-xl text-paper">Run history</h2>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="font-mono text-[11px] uppercase tracking-wider text-mist hover:text-teal disabled:opacity-50"
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        )}
      </div>
      <p className="mb-3 text-xs text-mist">Click a run to open it in the panels above.</p>

      {runs.length === 0 ? (
        <p className="rounded border border-dashed border-line px-4 py-8 text-center text-sm text-mist">
          No runs yet. Finish a loop and it will show up here.
        </p>
      ) : (
        <ul className="space-y-2">
          {runs.map((r) => {
            const selected = selectedRunId === r.run_id
            const hasReplay = Boolean(r.result?.steps?.length)
            return (
              <li key={r.run_id}>
                <button
                  type="button"
                  onClick={() => onOpenRun?.(r)}
                  disabled={!onOpenRun}
                  className={`flex w-full flex-wrap items-baseline justify-between gap-2 border px-3 py-3 text-left transition ${
                    selected
                      ? 'border-teal bg-teal/10'
                      : 'border-line bg-ink-2/40 hover:border-teal/50 hover:bg-panel/50'
                  } disabled:opacity-50`}
                >
                  <div className="min-w-0">
                    <p className="font-mono text-sm text-teal">
                      {r.dataset ?? 'dataset'} · {r.target_column ?? '—'}
                      {selected ? (
                        <span className="ml-2 text-[10px] uppercase tracking-wide text-paper">
                          open
                        </span>
                      ) : null}
                    </p>
                    <p className="mt-1 text-xs text-mist">
                      {fmtWhen(r.created_at)}
                      {!hasReplay && r.status !== 'error' ? ' · summary only' : ''}
                    </p>
                  </div>
                  <dl className="flex flex-wrap gap-3 font-mono text-[11px] text-mist">
                    <div>
                      <dt className="sr-only">Best val</dt>
                      <dd className="text-paper">val {fmtScore(r.best_val_f1)}</dd>
                    </div>
                    <div>
                      <dt className="sr-only">Holdout</dt>
                      <dd className="text-paper">
                        holdout {r.holdout_f1 != null ? fmtScore(r.holdout_f1) : 'sealed'}
                      </dd>
                    </div>
                    <div>
                      <dt className="sr-only">Status</dt>
                      <dd className={r.status === 'error' ? 'text-danger' : 'text-paper'}>
                        {r.status === 'error'
                          ? 'error'
                          : r.stop_reason || r.status || 'done'}
                      </dd>
                    </div>
                  </dl>
                </button>
                {selected && (
                  <div className="border border-t-0 border-teal/40 bg-ink-2/60 px-3 py-3 font-mono text-[11px] text-mist">
                    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <div>
                        <dt>Run id</dt>
                        <dd className="break-all text-paper">{r.run_id}</dd>
                      </div>
                      <div>
                        <dt>Cycles</dt>
                        <dd className="text-paper">
                          {r.cycles ?? '—'}
                          {r.max_cycles != null ? ` / ${r.max_cycles}` : ''}
                        </dd>
                      </div>
                      <div>
                        <dt>Target score</dt>
                        <dd className="text-paper">{fmtScore(r.target_score)}</dd>
                      </div>
                      <div>
                        <dt>Verdict</dt>
                        <dd className="text-paper">{r.verdict_action ?? '—'}</dd>
                      </div>
                      <div className="col-span-2 sm:col-span-4">
                        <dt>Model</dt>
                        <dd className="break-all text-paper">{r.model ?? '—'}</dd>
                      </div>
                    </dl>
                    {r.error && <p className="mt-2 text-danger">Error: {r.error}</p>}
                    {!hasReplay && !r.error && (
                      <p className="mt-2 text-amber">
                        This run has no saved steps — re-run to capture agent outputs.
                      </p>
                    )}
                    {hasReplay && (
                      <p className="mt-2 text-teal">
                        Loaded into Experiment timeline · Score chart · Budget panels.
                      </p>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
