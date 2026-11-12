import { useMemo, useState } from 'react'
import {
  DEFAULT_SELF_HEAL_BUDGET,
  buildSelfHealTraces,
  type ExperimentSelfHeal,
  type SelfHealAttempt,
  type SelfHealAttemptStatus,
} from '../lib/selfHealTrace'
import type { EventEnvelope, ExperimentEntry } from '../types/events'

export function SelfHealPanel({
  experiments,
  traceEvents = [],
  budget = DEFAULT_SELF_HEAL_BUDGET,
}: {
  experiments: ExperimentEntry[]
  traceEvents?: EventEnvelope[]
  budget?: number
}) {
  const traces = useMemo(
    () => buildSelfHealTraces(traceEvents, experiments, budget),
    [traceEvents, experiments, budget],
  )
  const [openId, setOpenId] = useState<string | null>(null)
  const anyHeals = traces.some((t) => t.attempts.length > 0)

  return (
    <section>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h2 className="font-display text-xl text-paper">Self-heal loops</h2>
        <p className="font-mono text-xs text-mist">budget {budget} / experiment</p>
      </div>
      <p className="mb-3 text-sm text-mist">
        Validate or run fails → Error repair → retry, up to {budget} times per experiment.
      </p>

      {experiments.length === 0 ? (
        <div className="flex h-28 items-center justify-center border border-dashed border-line text-sm text-mist">
          Waiting for trials…
        </div>
      ) : (
        <ul className="space-y-2">
          {traces.map((row, i) => (
            <HealRow
              key={row.experimentId}
              index={i + 1}
              row={row}
              budget={budget}
              open={openId === row.experimentId}
              onToggle={() =>
                setOpenId((cur) => (cur === row.experimentId ? null : row.experimentId))
              }
            />
          ))}
        </ul>
      )}

      {!anyHeals && experiments.length > 0 && (
        <p className="mt-2 font-mono text-[11px] text-mist">
          No repairs yet — empty slots are unused heal budget.
        </p>
      )}
    </section>
  )
}

function HealRow({
  index,
  row,
  budget,
  open,
  onToggle,
}: {
  index: number
  row: ExperimentSelfHeal
  budget: number
  open: boolean
  onToggle: () => void
}) {
  const slots = Array.from({ length: budget }, (_, i) => {
    const attempt = i + 1
    return row.attempts.find((a) => a.attempt === attempt) ?? null
  })

  return (
    <li className="border border-line bg-panel/50">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-left hover:bg-teal/5"
      >
        <div className="min-w-0">
          <p className="text-sm text-paper">
            <span className="mr-2 font-mono text-mist">{index}</span>
            {row.modelFamily ?? row.experimentId}
            <span className="ml-2 font-mono text-[10px] text-teal">{open ? '▾' : '▸'}</span>
          </p>
          <p className="font-mono text-[10px] text-mist">
            {row.used}/{budget} heals used
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {slots.map((slot, i) => (
            <SlotDot key={i} attempt={i + 1} slot={slot} />
          ))}
        </div>
      </button>

      {open && (
        <div className="space-y-2 border-t border-line px-3 py-3">
          <ol className="space-y-2">
            {slots.map((slot, i) => (
              <AttemptDetail key={i} attempt={i + 1} slot={slot} />
            ))}
          </ol>
          <p className="font-mono text-[10px] text-mist">
            Loop: config validator → experiment runner → error repair → retry
          </p>
        </div>
      )}
    </li>
  )
}

function SlotDot({ attempt, slot }: { attempt: number; slot: SelfHealAttempt | null }) {
  const status: SelfHealAttemptStatus = slot?.status ?? 'pending'
  const color =
    status === 'healed'
      ? 'border-ok/50 bg-ok/20 text-ok'
      : status === 'failed' || status === 'exhausted'
        ? 'border-danger/50 bg-danger/15 text-danger'
        : status === 'running'
          ? 'border-amber/50 bg-amber/15 text-amber'
          : 'border-line bg-ink-2 text-mist'
  return (
    <span
      title={slot ? `Heal ${attempt}: ${status}` : `Heal ${attempt}: unused`}
      className={`inline-flex h-7 w-7 items-center justify-center border font-mono text-[10px] ${color}`}
    >
      {attempt}
    </span>
  )
}

function AttemptDetail({ attempt, slot }: { attempt: number; slot: SelfHealAttempt | null }) {
  if (!slot) {
    return (
      <li className="flex items-start gap-2 border border-dashed border-line/70 px-2.5 py-2">
        <span className="font-mono text-[10px] text-mist">{attempt}</span>
        <p className="text-xs text-mist">Unused heal slot</p>
      </li>
    )
  }
  return (
    <li className="border border-line bg-ink-2/40 px-2.5 py-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm text-paper">
          <span className="mr-2 font-mono text-[10px] text-teal">#{attempt}</span>
          {slot.trigger?.replace(/_/g, ' ') ?? 'repair'}
        </p>
        <StatusLabel status={slot.status} />
      </div>
      {slot.error && (
        <p className="mt-1 font-mono text-[11px] text-danger/90 line-clamp-2">{slot.error}</p>
      )}
      {slot.note && <p className="mt-1 text-xs text-mist">{slot.note}</p>}
      {slot.repaired === true && (
        <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-ok">
          repaired → retry
        </p>
      )}
    </li>
  )
}

function StatusLabel({ status }: { status: SelfHealAttemptStatus }) {
  const color =
    status === 'healed'
      ? 'text-ok'
      : status === 'failed' || status === 'exhausted'
        ? 'text-danger'
        : status === 'running'
          ? 'text-amber'
          : 'text-mist'
  return (
    <span className={`font-mono text-[10px] uppercase tracking-wide ${color}`}>{status}</span>
  )
}
