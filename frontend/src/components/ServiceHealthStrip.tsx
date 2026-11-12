const DEFAULT_SERVICES = [
  'gateway',
  'orchestrator',
  'agent_service',
  'harness',
  'dataset_service',
  'memory_service',
  'tracking_service',
]

export function ServiceHealthStrip({ health }: { health: Record<string, string> }) {
  const names = Object.keys(health).length ? Object.keys(health) : DEFAULT_SERVICES

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-line bg-panel/90 px-4 py-2">
      <span className="mr-2 font-mono text-[10px] uppercase tracking-[0.18em] text-mist">
        services
      </span>
      {names.map((name) => {
        const status = health[name] ?? 'unknown'
        const ok = status === 'ok'
        const down = status === 'down'
        return (
          <span
            key={name}
            className="inline-flex items-center gap-1.5 rounded border border-line bg-panel px-2 py-1 font-mono text-[11px] text-paper"
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                ok ? 'bg-ok' : down ? 'bg-danger' : 'bg-mist'
              }`}
              aria-hidden
            />
            {name}
            <span className={ok ? 'text-ok' : down ? 'text-danger' : 'text-mist'}>{status}</span>
          </span>
        )
      })}
    </div>
  )
}
