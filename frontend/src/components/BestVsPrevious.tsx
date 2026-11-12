import type { ExperimentEntry } from '../types/events'

export function BestVsPrevious({ experiments }: { experiments: ExperimentEntry[] }) {
  const scored = experiments
    .filter((e) => typeof e.validationMetrics.f1 === 'number')
    .map((e) => ({ e, f1: e.validationMetrics.f1 as number }))

  if (scored.length === 0) {
    return (
      <section>
        <h2 className="font-display text-xl text-paper">Best versus previous model</h2>
        <p className="mt-2 text-sm text-mist">Waiting for completed trials…</p>
      </section>
    )
  }

  const best = scored.reduce((a, b) => (b.f1 > a.f1 ? b : a))
  const previous =
    scored.length > 1
      ? scored.filter((s) => s.e.experimentId !== best.e.experimentId).at(-1)
      : undefined

  return (
    <section>
      <h2 className="font-display text-xl text-paper">Best versus previous model</h2>
      <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <CompareCol title={`Best · ${best.e.experimentId}`} entry={best.e} highlight />
        <CompareCol
          title={previous ? `Previous · ${previous.e.experimentId}` : 'Previous'}
          entry={previous?.e}
        />
      </div>
    </section>
  )
}

function CompareCol({
  title,
  entry,
  highlight,
}: {
  title: string
  entry?: ExperimentEntry
  highlight?: boolean
}) {
  return (
    <div className={`border border-line p-3 ${highlight ? 'border-teal/50 bg-teal/5' : 'bg-panel/40'}`}>
      <p className="font-mono text-[11px] uppercase tracking-wide text-mist">{title}</p>
      {entry ? (
        <ul className="mt-2 space-y-1 font-mono text-xs">
          <li>
            Val F1 <span className="text-paper">{fmt(entry.validationMetrics.f1)}</span>
          </li>
          <li>
            Precision <span className="text-paper">{fmt(entry.validationMetrics.precision)}</span>
          </li>
          <li>
            Recall <span className="text-paper">{fmt(entry.validationMetrics.recall)}</span>
          </li>
        </ul>
      ) : (
        <p className="mt-2 text-xs text-mist">—</p>
      )}
    </div>
  )
}

function fmt(n?: number) {
  return typeof n === 'number' ? n.toFixed(2) : '—'
}
