import { NODE_BY_ID } from '../../graph/agentGraphConfig'
import type { AgentNodeRuntime } from '../../types/events'

export function NodeSidePanel({
  nodeId,
  runtime,
  mlRetryCount,
  onClose,
}: {
  nodeId: string | null
  runtime: AgentNodeRuntime | undefined
  mlRetryCount: number
  onClose: () => void
}) {
  if (!nodeId) return null
  const def = NODE_BY_ID[nodeId]
  if (!def) return null

  return (
    <aside className="absolute right-0 top-0 z-10 flex h-full w-72 flex-col border-l border-line bg-panel shadow-lg">
      <div className="flex items-start justify-between gap-2 border-b border-line px-3 py-2">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-teal">{def.kind}</p>
          <h3 className="font-display text-lg text-paper">{def.title}</h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-mist hover:text-paper"
          aria-label="Close panel"
        >
          ✕
        </button>
      </div>
      <div className="flex-1 space-y-3 overflow-auto px-3 py-3 text-sm">
        <p className="text-mist">{def.responsibility}</p>
        <dl className="space-y-2 font-mono text-xs">
          <div>
            <dt className="text-mist">Service</dt>
            <dd className="text-paper">{runtime?.sourceService ?? def.service}</dd>
          </div>
          <div>
            <dt className="text-mist">Status</dt>
            <dd className="text-paper">{runtime?.status ?? 'pending'}</dd>
          </div>
          <div>
            <dt className="text-mist">Correlation id</dt>
            <dd className="break-all text-paper">{runtime?.correlationId ?? '—'}</dd>
          </div>
          {(nodeId === 'ml_engineer' || def.leadId === 'ml_engineer') && (
            <div>
              <dt className="text-mist">Self-heal used</dt>
              <dd className="text-paper">{mlRetryCount} / 3</dd>
            </div>
          )}
          <div>
            <dt className="text-mist">Latest event</dt>
            <dd className="text-paper">{runtime?.lastEventType ?? '—'}</dd>
          </div>
        </dl>
        {runtime?.lastPayload && (
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-mist">Latest payload</p>
            <pre className="mt-1 max-h-40 overflow-auto border border-line bg-ink-2 p-2 text-[10px] text-paper">
              {JSON.stringify(runtime.lastPayload, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </aside>
  )
}
