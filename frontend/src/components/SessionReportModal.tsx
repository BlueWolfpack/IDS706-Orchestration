import { useMemo, useState, type ReactNode } from 'react'
import {
  buildSessionReport,
  reportToMarkdown,
  type SessionReport,
} from '../lib/sessionReport'
import type { SessionState } from '../types/events'

export function SessionReportModal({
  state,
  open,
  onClose,
}: {
  state: SessionState
  open: boolean
  onClose: () => void
}) {
  const report = useMemo(() => (open ? buildSessionReport(state) : null), [open, state])
  const [copied, setCopied] = useState(false)

  if (!open || !report) return null

  const md = reportToMarkdown(report)

  async function copyMarkdown() {
    try {
      await navigator.clipboard.writeText(md)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  function downloadMarkdown() {
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `session-report-${report.sessionId}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4" role="dialog" aria-modal="true" aria-labelledby="session-report-title">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col border border-line bg-panel shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-teal">
              Session report
            </p>
            <h2 id="session-report-title" className="font-display text-2xl text-paper">
              {report.sessionId}
            </h2>
            <p className="mt-1 text-xs text-mist">
              {report.dataset} · {report.targetColumn} · {report.metric} target{' '}
              {report.targetScore.toFixed(2)} · budget {report.budgetUsed}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="border border-line px-2 py-1 text-mist hover:border-teal hover:text-teal"
            aria-label="Close report"
          >
            ✕
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-auto px-4 py-4">
          <ReportSection title="What worked" tone="ok">
            <BulletList items={report.whatWorked} />
          </ReportSection>
          <ReportSection title="What didn't work" tone="danger">
            <BulletList items={report.whatDidnt} />
          </ReportSection>
          <ReportSection title="Final verdict" tone="teal">
            <VerdictBlock verdict={report.finalVerdict} metric={report.metric} />
          </ReportSection>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line px-4 py-3">
          <button
            type="button"
            onClick={() => void copyMarkdown()}
            className="rounded border border-line px-3 py-2 text-sm text-paper hover:border-teal"
          >
            {copied ? 'Copied' : 'Copy markdown'}
          </button>
          <button
            type="button"
            onClick={downloadMarkdown}
            className="rounded border border-line px-3 py-2 text-sm text-paper hover:border-teal"
          >
            Download .md
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-teal/50 bg-teal/15 px-3 py-2 text-sm text-teal hover:bg-teal/25"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

function ReportSection({
  title,
  tone,
  children,
}: {
  title: string
  tone: 'ok' | 'danger' | 'teal'
  children: ReactNode
}) {
  const accent =
    tone === 'ok' ? 'border-ok/40' : tone === 'danger' ? 'border-danger/40' : 'border-teal/40'
  return (
    <section className={`border-l-2 ${accent} bg-ink-2/30 pl-3`}>
      <h3 className="font-display text-lg text-paper">{title}</h3>
      <div className="mt-2">{children}</div>
    </section>
  )
}

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5 text-sm text-paper/90">
      {items.map((item) => (
        <li key={item} className="flex gap-2">
          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-teal" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function VerdictBlock({
  verdict,
  metric,
}: {
  verdict: SessionReport['finalVerdict']
  metric: string
}) {
  return (
    <div className="space-y-3">
      <p className="text-base font-medium text-paper">{verdict.headline}</p>
      <p className="text-sm text-mist">{verdict.detail}</p>
      <dl className="grid grid-cols-2 gap-2 font-mono text-xs sm:grid-cols-4">
        <Stat
          label={`Best val ${metric}`}
          value={verdict.bestValScore != null ? verdict.bestValScore.toFixed(3) : '—'}
        />
        <Stat
          label="Holdout"
          value={verdict.holdoutScore != null ? verdict.holdoutScore.toFixed(3) : '—'}
        />
        <Stat label="Best model" value={verdict.bestModelFamily ?? '—'} />
        <Stat label="Target met" value={verdict.targetMet ? 'yes' : 'no'} />
      </dl>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-line bg-panel/60 px-2.5 py-2">
      <dt className="text-mist">{label}</dt>
      <dd className="mt-0.5 text-paper">{value}</dd>
    </div>
  )
}
