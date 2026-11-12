import { useMemo, useState } from 'react'
import {
  buildLeadTraces,
  eventsForExperiment,
  type LeadTrace,
  type SubagentTrace,
} from '../lib/experimentTrace'
import {
  SIMPLE_LOOP_AGENT_META,
  type SimpleLoopAgentId,
} from '../lib/simpleLoopAgents'
import type { AgentCycleOutput, EventEnvelope, ExperimentEntry } from '../types/events'

const AGENT_ORDER: SimpleLoopAgentId[] = [
  'data_scientist',
  'hypothesis_generator',
  'ml_engineer',
]

export function ExperimentTimeline({
  experiments,
  traceEvents = [],
}: {
  experiments: ExperimentEntry[]
  traceEvents?: EventEnvelope[]
}) {
  const completed = experiments.filter((e) => e.status === 'completed').length
  const running = experiments.filter((e) => e.status === 'running').length
  const [openExp, setOpenExp] = useState<string | null>(null)
  const [openLead, setOpenLead] = useState<string | null>(null)
  const traces = Array.isArray(traceEvents) ? traceEvents : []

  return (
    <section className="min-h-0 flex-1 overflow-auto">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="font-display text-xl text-paper">Experiment timeline</h2>
        <p className="font-mono text-xs text-mist">
          {completed} completed · {running} in progress
        </p>
      </div>
      <p className="mb-4 text-sm text-mist">
        Expand a cycle to inspect Data Scientist, Hypothesis, and ML Engineer outputs.
      </p>

      {experiments.length === 0 ? (
        <p className="rounded border border-dashed border-line px-4 py-8 text-center text-sm text-mist">
          Waiting for trial events…
        </p>
      ) : (
        <ol className="space-y-3">
          {experiments.map((exp, i) => {
            const expanded = openExp === exp.experimentId
            const hasSimpleAgents = Boolean(
              exp.agentOutputs &&
                (exp.agentOutputs.data_scientist ||
                  exp.agentOutputs.hypothesis_generator ||
                  exp.agentOutputs.ml_engineer),
            )
            const leads = expanded && !hasSimpleAgents
              ? buildLeadTraces(eventsForExperiment(traces, exp.experimentId, i === 0))
              : []
            return (
              <li
                key={exp.experimentId}
                className="border-l-2 border-teal/40 bg-panel/60"
              >
                <button
                  type="button"
                  onClick={() => {
                    setOpenExp(expanded ? null : exp.experimentId)
                    setOpenLead(null)
                  }}
                  className="flex w-full flex-wrap items-baseline justify-between gap-2 px-4 py-3 text-left hover:bg-teal/5"
                >
                  <h3 className="text-sm font-medium text-paper">
                    <span className="mr-2 font-mono text-mist">{i + 1}</span>
                    {exp.modelFamily ?? exp.experimentId}
                    <span className="ml-2 font-mono text-[10px] text-teal">
                      {expanded ? '▾' : '▸'} drill down
                    </span>
                  </h3>
                  <span className="font-mono text-[11px] uppercase tracking-wide text-mist">
                    {exp.status}
                    {typeof exp.durationSeconds === 'number'
                      ? ` · ${exp.durationSeconds.toFixed(1)} s`
                      : ''}
                  </span>
                </button>
                <div className="px-4 pb-3">
                  {exp.note && <p className="text-xs text-amber">{exp.note}</p>}
                  <MetricRow metrics={exp.validationMetrics} label="Val" />
                  <MetricRow metrics={exp.trainMetrics} label="Train" />
                  {exp.verdictAction && (
                    <p className="mt-2 text-sm text-paper/90">
                      <span className="font-mono text-xs text-teal">Judge · {exp.verdictAction}</span>
                      {exp.observation ? ` — ${exp.observation}` : ''}
                    </p>
                  )}
                  {exp.nextAction && (
                    <p className="mt-1 text-xs text-mist">Next action: {exp.nextAction}</p>
                  )}
                  <p className="mt-2 font-mono text-[10px] text-mist">
                    Self-heal{' '}
                    <span className="text-paper">
                      {typeof exp.retryCount === 'number' ? exp.retryCount : 0}/3
                    </span>
                  </p>

                  {expanded && hasSimpleAgents && (
                    <div className="mt-4 space-y-2 border-t border-line pt-3">
                      <p className="font-mono text-[10px] uppercase tracking-wider text-mist">
                        Agents for {exp.experimentId}
                      </p>
                      {AGENT_ORDER.map((id) => (
                        <AgentOutputPanel
                          key={id}
                          agentId={id}
                          payload={exp.agentOutputs?.[id]}
                          open={openLead === `${exp.experimentId}:${id}`}
                          onToggle={() =>
                            setOpenLead((cur) =>
                              cur === `${exp.experimentId}:${id}`
                                ? null
                                : `${exp.experimentId}:${id}`,
                            )
                          }
                        />
                      ))}
                    </div>
                  )}

                  {expanded && !hasSimpleAgents && (
                    <div className="mt-4 space-y-2 border-t border-line pt-3">
                      <p className="font-mono text-[10px] uppercase tracking-wider text-mist">
                        Four leads for {exp.experimentId}
                      </p>
                      {leads.map((lead) => (
                        <LeadPanel
                          key={lead.id}
                          lead={lead}
                          open={openLead === `${exp.experimentId}:${lead.id}`}
                          onToggle={() =>
                            setOpenLead((cur) =>
                              cur === `${exp.experimentId}:${lead.id}`
                                ? null
                                : `${exp.experimentId}:${lead.id}`,
                            )
                          }
                        />
                      ))}
                    </div>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

function AgentOutputPanel({
  agentId,
  payload,
  open,
  onToggle,
}: {
  agentId: SimpleLoopAgentId
  payload?: AgentCycleOutput
  open: boolean
  onToggle: () => void
}) {
  const meta = SIMPLE_LOOP_AGENT_META[agentId]
  const status = payload ? (payload.status === 'failed' ? 'failed' : 'completed') : 'pending'
  return (
    <div className="border border-line bg-ink-2/40">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-teal/5"
      >
        <div>
          <p className="text-sm font-medium text-paper">
            <span className="mr-2 font-mono text-[10px] text-teal">{open ? '▾' : '▸'}</span>
            {meta.title}
          </p>
          <p className="text-xs text-mist">{meta.role}</p>
        </div>
        <StatusPill status={status} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-line px-3 py-3">
          {payload?.note && <p className="text-xs text-amber">{payload.note}</p>}
          <p className="font-mono text-[10px] text-mist">
            {payload?.used_llm ? `LLM · ${payload.model || 'configured'}` : 'Heuristic / pending'}
          </p>
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-teal">Output</p>
            {payload ? (
              <JsonBlock value={payload.output ?? payload} />
            ) : (
              <p className="font-mono text-xs text-mist">No output yet for this agent.</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function LeadPanel({
  lead,
  open,
  onToggle,
}: {
  lead: LeadTrace
  open: boolean
  onToggle: () => void
}) {
  return (
    <div className="border border-line bg-ink-2/40">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-teal/5"
      >
        <div>
          <p className="text-sm font-medium text-paper">
            <span className="mr-2 font-mono text-[10px] text-teal">{open ? '▾' : '▸'}</span>
            {lead.title}
          </p>
          <p className="text-xs text-mist">{lead.role}</p>
        </div>
        <StatusPill status={lead.status} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-line px-3 py-3">
          <p className="text-xs text-mist">{lead.responsibility}</p>
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-teal">
              Lead overall output
            </p>
            <JsonBlock value={lead.overall} />
          </div>
          <div>
            <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-teal">
              Subagents that informed this lead
            </p>
            <ul className="space-y-2">
              {lead.subagents.map((sub) => (
                <SubagentCard key={sub.id} sub={sub} />
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

function SubagentCard({ sub }: { sub: SubagentTrace }) {
  const [open, setOpen] = useState(false)
  const body = sub.output ?? sub.summary
  return (
    <li className="border border-line/80 bg-panel/50">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-2.5 py-2 text-left text-sm hover:bg-teal/5"
      >
        <span className="text-paper">
          <span className="mr-1.5 font-mono text-[10px] text-mist">{open ? '▾' : '▸'}</span>
          {sub.title}
          <span className="ml-2 font-mono text-[10px] text-mist">{sub.service}</span>
        </span>
        <StatusPill status={sub.status} />
      </button>
      {open && (
        <div className="border-t border-line px-2.5 py-2">
          <p className="mb-1 text-xs text-mist">{sub.role}</p>
          {body ? (
            <JsonBlock value={body} />
          ) : (
            <p className="font-mono text-xs text-mist">No output yet for this subagent.</p>
          )}
        </div>
      )}
    </li>
  )
}

function StatusPill({ status }: { status: string }) {
  const color =
    status === 'completed'
      ? 'text-teal'
      : status === 'running'
        ? 'text-amber'
        : status === 'failed'
          ? 'text-danger'
          : 'text-mist'
  return (
    <span className={`font-mono text-[10px] uppercase tracking-wide ${color}`}>{status}</span>
  )
}

function JsonBlock({ value }: { value: unknown }) {
  const text = useMemo(() => {
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }, [value])
  const empty =
    value == null ||
    (typeof value === 'object' &&
      value !== null &&
      Object.values(value as Record<string, unknown>).every((v) => v == null))
  if (empty) {
    return <p className="font-mono text-xs text-mist">No structured output recorded yet.</p>
  }
  return (
    <pre className="mt-1 max-h-56 overflow-auto rounded border border-line bg-ink-2/80 p-2 font-mono text-[11px] leading-relaxed text-paper/90">
      {text}
    </pre>
  )
}

function MetricRow({
  metrics,
  label,
}: {
  metrics: Record<string, number>
  label: string
}) {
  const entries = Object.entries(metrics)
  if (!entries.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-3 font-mono text-xs text-mist">
      {entries.map(([k, v]) => (
        <span key={k}>
          {label} {k} <span className="text-paper">{Number(v).toFixed(2)}</span>
        </span>
      ))}
    </div>
  )
}
