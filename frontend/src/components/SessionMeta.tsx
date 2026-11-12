import type { SessionState } from '../types/events'

export function SessionMeta({ state }: { state: SessionState }) {
  const strategy =
    state.researchStrategy === 'blackbox_tuning'
      ? `Blackbox HP · ${state.fixedModelFamily ?? 'fixed model'}`
      : 'Model search'
  return (
    <dl className="grid grid-cols-2 gap-3 border-b border-line px-6 py-3 text-sm sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8">
      <Meta label="Dataset" value={state.dataset} />
      <Meta label="Target" value={state.targetColumn} />
      <Meta label="Metric" value={state.metric} />
      <Meta label="Target score" value={state.targetScore.toFixed(2)} />
      <Meta label="Strategy" value={strategy} />
      <Meta label="Train timeout" value={`${state.perTrialTimeoutSeconds}s / trial`} />
      <Meta label="Budget" value={`${state.experimentBudget} experiments`} />
      <Meta
        label="Best val"
        value={state.bestValScore != null ? state.bestValScore.toFixed(2) : '—'}
      />
    </dl>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-wider text-mist">{label}</dt>
      <dd className="mt-0.5 text-paper">{value}</dd>
    </div>
  )
}
