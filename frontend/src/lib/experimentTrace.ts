import { AGENT_NODES, NODE_BY_ID } from '../graph/agentGraphConfig'
import type { EventEnvelope } from '../types/events'

export const LEAD_IDS = [
  'data_scientist',
  'hypothesis_generator',
  'ml_engineer',
  'judge',
] as const

export type LeadId = (typeof LEAD_IDS)[number]

export interface SubagentTrace {
  id: string
  title: string
  role: string
  service: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  startedAt?: string
  completedAt?: string
  output: Record<string, unknown> | null
  summary: Record<string, unknown> | null
  correlationId?: string
}

export interface LeadTrace {
  id: LeadId
  title: string
  role: string
  responsibility: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  /** Synthesized view of what the lead produced from its subagents. */
  overall: Record<string, unknown>
  subagents: SubagentTrace[]
}

const SETUP_KEY = '__setup__'

function subagentId(payload: Record<string, unknown>, sourceAgent: string | null): string | null {
  if (typeof payload.subagent === 'string') return payload.subagent
  if (sourceAgent && NODE_BY_ID[sourceAgent]?.kind === 'subagent') return sourceAgent
  return null
}

function leadForSubagent(subId: string): LeadId | null {
  const lead = NODE_BY_ID[subId]?.leadId
  if (lead && (LEAD_IDS as readonly string[]).includes(lead)) return lead as LeadId
  return null
}

/** Events belonging to this experiment, plus session setup (profiler) for the first trial. */
export function eventsForExperiment(
  all: EventEnvelope[],
  experimentId: string,
  isFirst: boolean,
): EventEnvelope[] {
  return all.filter((e) => {
    const eid = e.payload.experiment_id
    if (eid === experimentId) return true
    if (isFirst && (eid == null || eid === SETUP_KEY)) {
      const sub = subagentId(e.payload, e.source_agent)
      if (!sub) return e.type === 'activity'
      return leadForSubagent(sub) === 'data_scientist'
    }
    return false
  })
}

function synthesizeLeadOverall(leadId: LeadId, subs: SubagentTrace[]): Record<string, unknown> {
  const byId = Object.fromEntries(subs.map((s) => [s.id, s]))
  if (leadId === 'data_scientist') {
    return {
      profile: byId.data_profiler?.output ?? byId.data_profiler?.summary ?? null,
      leakage_flags:
        (byId.leakage_auditor?.output as { leakage_flags?: unknown } | null)?.leakage_flags ??
        byId.leakage_auditor?.summary ??
        null,
      feature_notes:
        (byId.feature_analyst?.output as { feature_notes?: unknown } | null)?.feature_notes ??
        byId.feature_analyst?.summary ??
        null,
    }
  }
  if (leadId === 'hypothesis_generator') {
    const proposal = byId.hypothesis_drafter?.output ?? byId.hypothesis_drafter?.summary ?? null
    const memory = byId.memory_retriever?.output ?? byId.memory_retriever?.summary ?? null
    const recent =
      (proposal as { recent_experiments?: unknown } | null)?.recent_experiments ??
      (memory as { recent_experiments?: unknown } | null)?.recent_experiments ??
      null
    return {
      proposal,
      novelty: byId.novelty_checker?.output ?? byId.novelty_checker?.summary ?? null,
      memory,
      prior_context: recent,
    }
  }
  if (leadId === 'ml_engineer') {
    return {
      validation: byId.config_validator?.output ?? byId.config_validator?.summary ?? null,
      trial: byId.experiment_runner?.output ?? byId.experiment_runner?.summary ?? null,
      repair: byId.error_repair?.output ?? byId.error_repair?.summary ?? null,
    }
  }
  return {
    metrics: byId.metric_analyst?.output ?? byId.metric_analyst?.summary ?? null,
    overfitting: byId.overfitting_checker?.output ?? byId.overfitting_checker?.summary ?? null,
    verdict:
      byId.independent_reviewer?.output ?? byId.independent_reviewer?.summary ?? null,
  }
}

export function buildLeadTraces(events: EventEnvelope[]): LeadTrace[] {
  const subDefs = AGENT_NODES.filter((n) => n.kind === 'subagent' && n.leadId)

  const traces: Record<string, SubagentTrace> = {}
  for (const def of subDefs) {
    traces[def.id] = {
      id: def.id,
      title: def.title,
      role: def.role,
      service: def.service,
      status: 'pending',
      output: null,
      summary: null,
    }
  }

  for (const event of events) {
    const subId = subagentId(event.payload, event.source_agent)
    if (!subId || !traces[subId]) continue
    const t = traces[subId]
    if (event.type === 'agent_started' || event.type === 'trial_started') {
      // Don't let a late/duplicate start overwrite a finished subagent.
      if (t.status !== 'completed' && t.status !== 'failed') {
        t.status = 'running'
      }
      t.startedAt = t.startedAt ?? event.timestamp
      t.correlationId = event.correlation_id
    }
    if (event.type === 'agent_completed') {
      t.status = event.payload.status === 'failed' ? 'failed' : 'completed'
      t.completedAt = event.timestamp
      t.summary =
        event.payload.summary && typeof event.payload.summary === 'object'
          ? (event.payload.summary as Record<string, unknown>)
          : null
      t.output =
        event.payload.output && typeof event.payload.output === 'object'
          ? (event.payload.output as Record<string, unknown>)
          : t.summary
      t.correlationId = event.correlation_id
    }
    if (event.type === 'trial_completed' || event.type === 'trial_failed') {
      if (subId === 'experiment_runner') {
        t.status = event.type === 'trial_completed' ? 'completed' : 'failed'
        t.completedAt = event.timestamp
        t.output = event.payload
      }
    }
    if (event.type === 'verdict_issued' && subId === 'independent_reviewer') {
      t.status = 'completed'
      t.completedAt = event.timestamp
      t.output = event.payload
    }
  }

  return LEAD_IDS.map((leadId) => {
    const def = NODE_BY_ID[leadId]
    const subs = subDefs.filter((s) => s.leadId === leadId).map((s) => traces[s.id])
    const statuses = subs.map((s) => s.status)
    let status: LeadTrace['status'] = 'pending'
    if (statuses.some((s) => s === 'running')) status = 'running'
    else if (statuses.some((s) => s === 'failed')) status = 'failed'
    else if (statuses.some((s) => s === 'completed')) status = 'completed'
    else if (statuses.every((s) => s === 'pending')) status = 'pending'

    return {
      id: leadId,
      title: def.title,
      role: def.role,
      responsibility: def.responsibility,
      status,
      overall: synthesizeLeadOverall(leadId, subs),
      subagents: subs,
    }
  })
}
