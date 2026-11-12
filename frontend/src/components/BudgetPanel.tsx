import type { SessionState } from '../types/events'

export function BudgetPanel({ state }: { state: SessionState }) {
  const remaining = Math.max(0, state.experimentBudget - state.experimentsUsed)
  const trainingTime = state.experiments.reduce(
    (sum, e) => sum + (e.durationSeconds ?? 0),
    0,
  )
  const failed = state.experiments.filter((e) => e.status === 'failed').length

  return (
    <section>
      <h2 className="font-display text-xl text-paper">Budget, duration and cost</h2>
      <p className="mt-1 text-sm text-mist">
        {remaining} experiments remaining of {state.experimentBudget}
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-3 font-mono text-xs sm:grid-cols-4">
        <Stat label="Used" value={`${state.experimentsUsed}/${state.experimentBudget}`} />
        <Stat label="Training time" value={`${trainingTime.toFixed(1)} s`} />
        <Stat label="Failed trials" value={String(failed)} />
        <Stat
          label="Holdout"
          value={
            state.holdoutScore != null ? state.holdoutScore.toFixed(2) : 'sealed'
          }
        />
      </dl>
      {state.stopReason && (
        <p className="mt-3 text-sm text-teal">Stop reason: {state.stopReason}</p>
      )}
      <p className="mt-2 text-[11px] text-mist">
        Run cost is not reported in Stage A1 fixtures (planned with real tracking).
      </p>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-line bg-panel/50 px-3 py-2">
      <dt className="text-mist">{label}</dt>
      <dd className="mt-1 text-sm text-paper">{value}</dd>
    </div>
  )
}
