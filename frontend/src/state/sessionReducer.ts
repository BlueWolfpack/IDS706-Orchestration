import { resolveNodeId } from '../graph/mapEventToNode'
import { NODE_BY_ID } from '../graph/agentGraphConfig'
import type {
  ActivityItem,
  AgentNodeRuntime,
  EventEnvelope,
  ExperimentEntry,
  SessionState,
} from '../types/events'

export const initialSessionState = (overrides?: Partial<SessionState>): SessionState => ({
  sessionId: null,
  status: 'idle',
  mock: false,
  replay: false,
  mode: 'live',
  scenario: 'happy',
  dataset: 'churn_sample.csv',
  targetColumn: 'churned',
  metric: 'f1',
  targetScore: 0.7,
  experimentBudget: 10,
  experimentsUsed: 0,
  selfHealBudget: 3,
  researchStrategy: 'model_search',
  fixedModelFamily: null,
  perTrialTimeoutSeconds: 120,
  bestValScore: null,
  holdoutScore: null,
  stopReason: null,
  serviceHealth: {},
  experiments: [],
  activity: [],
  lastEventType: null,
  error: null,
  agentNodes: {},
  activeNodeId: null,
  mlRetryCount: 0,
  lastCorrelationId: null,
  traceEvents: [],
  activeExperimentId: null,
  ...overrides,
})

function pushActivity(
  state: SessionState,
  event: EventEnvelope,
  message: string,
): ActivityItem[] {
  const item: ActivityItem = {
    id: `${event.timestamp}-${event.type}-${state.activity.length}`,
    timestamp: event.timestamp,
    agent: (event.source_agent || event.source_service || 'system').toUpperCase(),
    message,
    type: event.type,
  }
  return [...state.activity, item].slice(-200)
}

function upsertExperiment(
  list: ExperimentEntry[],
  experimentId: string,
  patch: Partial<ExperimentEntry>,
): ExperimentEntry[] {
  const idx = list.findIndex((e) => e.experimentId === experimentId)
  if (idx === -1) {
    return [
      ...list,
      {
        experimentId,
        status: 'running',
        trainMetrics: {},
        validationMetrics: {},
        ...patch,
      },
    ]
  }
  const next = [...list]
  next[idx] = { ...next[idx], ...patch }
  return next
}

function numMap(value: unknown): Record<string, number> {
  if (!value || typeof value !== 'object') return {}
  const out: Record<string, number> = {}
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (typeof v === 'number') out[k] = v
  }
  return out
}

export type SessionAction =
  | {
      type: 'SESSION_CREATED'
      sessionId: string
      mock: boolean
      replay?: boolean
      mode?: SessionState['mode']
    }
  | { type: 'STATUS'; status: SessionState['status'] }
  | { type: 'SETUP'; patch: Partial<SessionState> }
  | { type: 'ERROR'; error: string }
  | { type: 'RESET_LOCAL' }
  | { type: 'EVENT'; event: EventEnvelope }

export function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case 'SETUP':
      return { ...state, ...action.patch }
    case 'SESSION_CREATED':
      return {
        ...state,
        sessionId: action.sessionId,
        mock: action.mock,
        replay: Boolean(action.replay),
        mode: action.mode ?? (action.mock ? 'mock' : action.replay ? 'replay' : 'live'),
        status: 'running',
        experiments: [],
        activity: [],
        stopReason: null,
        holdoutScore: null,
        bestValScore: null,
        experimentsUsed: 0,
        error: null,
        agentNodes: {},
        activeNodeId: null,
        mlRetryCount: 0,
        lastCorrelationId: null,
        traceEvents: [],
        activeExperimentId: null,
      }
    case 'STATUS':
      return { ...state, status: action.status }
    case 'ERROR':
      return { ...state, status: 'error', error: action.error }
    case 'RESET_LOCAL':
      return initialSessionState({
        scenario: state.scenario,
        dataset: state.dataset,
        targetColumn: state.targetColumn,
        metric: state.metric,
        targetScore: state.targetScore,
        experimentBudget: state.experimentBudget,
        researchStrategy: state.researchStrategy,
        fixedModelFamily: state.fixedModelFamily,
        perTrialTimeoutSeconds: state.perTrialTimeoutSeconds,
      })
    case 'EVENT':
      return reduceEvent(state, action.event)
    default:
      return state
  }
}

/** Subagents that may never run on the happy path — ignore if still pending when rolling up. */
const OPTIONAL_SUBAGENTS = new Set(['error_repair'])

function patchAgentNode(
  nodes: Record<string, AgentNodeRuntime>,
  nodeId: string,
  patch: Partial<AgentNodeRuntime>,
): Record<string, AgentNodeRuntime> {
  const prev = nodes[nodeId] ?? { status: 'pending' as const }
  return { ...nodes, [nodeId]: { ...prev, ...patch } }
}

function rollupLead(
  nodes: Record<string, AgentNodeRuntime>,
  leadId: string,
  updatedAt: string,
): Record<string, AgentNodeRuntime> {
  const children = Object.values(NODE_BY_ID).filter((n) => n.leadId === leadId)
  const required = children.filter((n) => !OPTIONAL_SUBAGENTS.has(n.id))
  if (required.length === 0) return nodes

  let anyFailed = false
  for (const child of required) {
    const st = nodes[child.id]?.status ?? 'pending'
    if (st === 'pending' || st === 'running') return nodes
    if (st === 'failed') anyFailed = true
  }
  // Optional child that actually ran and failed still fails the lead.
  for (const child of children) {
    if (OPTIONAL_SUBAGENTS.has(child.id) && nodes[child.id]?.status === 'failed') anyFailed = true
  }

  const leadStatus = nodes[leadId]?.status
  if (leadStatus === 'completed' || leadStatus === 'failed') return nodes
  return patchAgentNode(nodes, leadId, {
    status: anyFailed ? 'failed' : 'completed',
    updatedAt,
  })
}

function applyGraphFromEvent(state: SessionState, event: EventEnvelope): SessionState {
  const nodeId = resolveNodeId(event.source_agent, event.payload)
  if (!nodeId) {
    return { ...state, lastCorrelationId: event.correlation_id }
  }

  let status = state.agentNodes[nodeId]?.status ?? 'pending'
  if (event.type === 'agent_started' || event.type === 'trial_started' || event.type === 'tool_called') {
    status = 'running'
  } else if (event.type === 'trial_failed' || event.type === 'service_error') {
    status = 'failed'
  } else if (event.type === 'agent_completed' && event.payload.status === 'failed') {
    status = 'failed'
  } else if (
    event.type === 'agent_completed' ||
    event.type === 'trial_completed' ||
    event.type === 'tool_result' ||
    event.type === 'verdict_issued'
  ) {
    status = 'completed'
  }

  let agentNodes = patchAgentNode(state.agentNodes, nodeId, {
    status,
    lastEventType: event.type,
    lastPayload: event.payload,
    correlationId: event.correlation_id,
    sourceService: event.source_service,
    updatedAt: event.timestamp,
  })

  // Bubble status to parent lead when a subagent runs/completes/fails.
  const def = NODE_BY_ID[nodeId]
  if (def?.leadId) {
    if (status === 'running') {
      agentNodes = patchAgentNode(agentNodes, def.leadId, {
        status: 'running',
        updatedAt: event.timestamp,
        correlationId: event.correlation_id,
      })
    } else if (status === 'failed') {
      agentNodes = patchAgentNode(agentNodes, def.leadId, {
        status: 'failed',
        updatedAt: event.timestamp,
      })
    } else if (status === 'completed') {
      agentNodes = rollupLead(agentNodes, def.leadId, event.timestamp)
    }
  }

  const retry =
    typeof event.payload.retry_count === 'number' ? event.payload.retry_count : state.mlRetryCount

  let activeNodeId = state.activeNodeId
  if (status === 'running') {
    activeNodeId = nodeId
  } else if (state.activeNodeId === nodeId) {
    activeNodeId = null
  }

  return {
    ...state,
    agentNodes,
    activeNodeId,
    mlRetryCount: nodeId === 'ml_engineer' || nodeId === 'error_repair' || def?.leadId === 'ml_engineer' ? retry : state.mlRetryCount,
    lastCorrelationId: event.correlation_id,
  }
}

function pushTrace(state: SessionState, event: EventEnvelope): EventEnvelope[] {
  const prev = Array.isArray(state.traceEvents) ? state.traceEvents : []
  const keepActivity =
    event.type === 'activity' &&
    (event.payload?.kind === 'self_heal' || event.payload?.kind === 'experiment_context')
  const keep =
    event.type === 'agent_started' ||
    event.type === 'agent_completed' ||
    event.type === 'trial_started' ||
    event.type === 'trial_completed' ||
    event.type === 'trial_failed' ||
    event.type === 'verdict_issued' ||
    keepActivity
  if (!keep) return prev
  const stamped: EventEnvelope = {
    ...event,
    payload: {
      ...event.payload,
      experiment_id:
        event.payload.experiment_id ??
        state.activeExperimentId ??
        (event.payload.subagent === 'data_profiler' ||
        event.payload.subagent === 'leakage_auditor' ||
        event.payload.subagent === 'feature_analyst'
          ? '__setup__'
          : event.payload.experiment_id),
    },
  }
  return [...prev, stamped].slice(-500)
}

function reduceEvent(state: SessionState, event: EventEnvelope): SessionState {
  const mock = state.mock || event.mock
  const payloadMode = event.payload?.mode
  const replay =
    state.replay ||
    payloadMode === 'replay' ||
    String(event.payload?.message ?? '').toLowerCase().includes('replay of a recorded')
  let next: SessionState = {
    ...state,
    mock,
    replay,
    mode: mock ? 'mock' : replay ? 'replay' : state.mode === 'mock' ? 'live' : state.mode,
    lastEventType: event.type,
    traceEvents: pushTrace(state, event),
  }

  next = applyGraphFromEvent(next, event)

  const p = event.payload

  switch (event.type) {
    case 'session_created': {
      next = {
        ...next,
        status: 'running',
        dataset: String(p.dataset ?? next.dataset),
        targetColumn: String(p.target_column ?? next.targetColumn),
        metric: String(p.metric ?? next.metric),
        targetScore: typeof p.target_score === 'number' ? p.target_score : next.targetScore,
        experimentBudget:
          typeof p.experiment_budget === 'number' ? p.experiment_budget : next.experimentBudget,
        activity: pushActivity(next, event, 'Research session started (mock fixture stream)'),
      }
      break
    }
    case 'health': {
      const services = (p.services as Record<string, string>) || {}
      next = {
        ...next,
        serviceHealth: { ...next.serviceHealth, ...services },
        activity: pushActivity(
          next,
          event,
          `Service health update${p.note ? `: ${String(p.note)}` : ''}`,
        ),
      }
      break
    }
    case 'agent_started':
    case 'agent_completed': {
      const who = event.source_agent || event.source_service
      const status = event.type === 'agent_started' ? 'started' : 'completed'
      const summary =
        p.summary && typeof p.summary === 'object'
          ? ` — ${JSON.stringify(p.summary)}`
          : p.summary
            ? ` — ${String(p.summary)}`
            : ''
      next = {
        ...next,
        activity: pushActivity(next, event, `${who} ${status}${summary}`),
        activeExperimentId:
          typeof p.experiment_id === 'string' && p.experiment_id !== '__setup__'
            ? String(p.experiment_id)
            : next.activeExperimentId,
      }
      // Do not create timeline rows from agent events alone — wait for trial_* / verdict.
      break
    }
    case 'tool_called':
    case 'tool_result': {
      next = {
        ...next,
        activity: pushActivity(
          next,
          event,
          `tool ${String(p.tool ?? event.type)}${p.note ? ` — ${String(p.note)}` : ''}`,
        ),
      }
      break
    }
    case 'trial_started': {
      const id =
        typeof p.experiment_id === 'string' && p.experiment_id
          ? String(p.experiment_id)
          : next.activeExperimentId
      if (!id) {
        next = {
          ...next,
          activity: pushActivity(next, event, 'Trial started (awaiting experiment id)'),
        }
        break
      }
      next = {
        ...next,
        activeExperimentId: id,
        experiments: upsertExperiment(next.experiments, id, {
          status: 'running',
          modelFamily: p.model_family ? String(p.model_family) : undefined,
          retryCount: typeof p.retry_count === 'number' ? p.retry_count : undefined,
        }),
        activity: pushActivity(next, event, `Trial started ${id}`),
      }
      break
    }
    case 'trial_completed': {
      const id = String(p.experiment_id ?? 'unknown')
      const val = numMap(p.validation_metrics)
      const train = numMap(p.train_metrics)
      const f1 = val.f1
      next = {
        ...next,
        experiments: upsertExperiment(next.experiments, id, {
          status: 'completed',
          validationMetrics: val,
          trainMetrics: train,
          durationSeconds:
            typeof p.duration_seconds === 'number' ? p.duration_seconds : undefined,
          note: p.note ? String(p.note) : undefined,
        }),
        bestValScore:
          typeof f1 === 'number'
            ? next.bestValScore == null
              ? f1
              : Math.max(next.bestValScore, f1)
            : next.bestValScore,
        activity: pushActivity(
          next,
          event,
          `Trial ${id} completed${typeof f1 === 'number' ? ` · val F1 ${f1.toFixed(2)}` : ''} (sample fixture)`,
        ),
      }
      break
    }
    case 'trial_failed': {
      const id = String(p.experiment_id ?? 'unknown')
      next = {
        ...next,
        experiments: upsertExperiment(next.experiments, id, {
          status: 'failed',
          modelFamily: p.model_family ? String(p.model_family) : undefined,
          retryCount: typeof p.retry_count === 'number' ? p.retry_count : undefined,
          note: String(p.reason ?? p.error ?? p.note ?? 'failed'),
        }),
        activity: pushActivity(
          next,
          event,
          `Trial ${id} failed: ${String(p.reason ?? p.error ?? 'error')}`,
        ),
      }
      break
    }
    case 'verdict_issued': {
      const id = String(p.experiment_id ?? 'unknown')
      next = {
        ...next,
        experiments: upsertExperiment(next.experiments, id, {
          verdictAction: String(p.action ?? ''),
          observation: p.observation ? String(p.observation) : undefined,
          nextAction: p.next_action ? String(p.next_action) : undefined,
        }),
        activity: pushActivity(
          next,
          event,
          `Judge verdict on ${id}: ${String(p.action)}${p.next_action ? ` → ${String(p.next_action)}` : ''}`,
        ),
      }
      break
    }
    case 'budget_update': {
      const used =
        typeof p.experiments_used === 'number'
          ? p.experiments_used
          : typeof p.experiment_count === 'number'
            ? p.experiment_count
            : next.experimentsUsed
      const budget =
        typeof p.budget === 'number'
          ? p.budget
          : typeof p.experiment_budget === 'number'
            ? p.experiment_budget
            : next.experimentBudget
      const best =
        typeof p.best_val_f1 === 'number'
          ? p.best_val_f1
          : typeof p.best_val_score === 'number'
            ? p.best_val_score
            : next.bestValScore
      next = {
        ...next,
        experimentsUsed: used,
        experimentBudget: budget,
        bestValScore: best,
        selfHealBudget:
          typeof p.self_heal_budget === 'number' ? p.self_heal_budget : next.selfHealBudget,
        mlRetryCount:
          typeof p.self_heal_attempt === 'number'
            ? p.self_heal_attempt
            : typeof p.retry_count === 'number'
              ? p.retry_count
              : next.mlRetryCount,
        activity: pushActivity(next, event, `Budget ${used}/${budget}`),
      }
      break
    }
    case 'holdout_evaluated': {
      next = {
        ...next,
        holdoutScore: typeof p.score === 'number' ? p.score : next.holdoutScore,
        activity: pushActivity(
          next,
          event,
          `Sealed holdout opened once · score ${String(p.score)} (sample fixture)`,
        ),
      }
      break
    }
    case 'stop_reason': {
      next = {
        ...next,
        status: 'completed',
        stopReason: String(p.stop_reason ?? 'stopped'),
        experimentsUsed:
          typeof p.experiments_used === 'number' ? p.experiments_used : next.experimentsUsed,
        activity: pushActivity(next, event, `Stop: ${String(p.stop_reason)}`),
      }
      break
    }
    case 'service_error': {
      next = {
        ...next,
        activity: pushActivity(
          next,
          event,
          `Service error ${String(p.code)}: ${String(p.message)}`,
        ),
      }
      break
    }
    case 'activity': {
      const healAttempt =
        typeof p.self_heal_attempt === 'number'
          ? p.self_heal_attempt
          : typeof p.retry_count === 'number'
            ? p.retry_count
            : null
      next = {
        ...next,
        status: p.done === true ? 'completed' : next.status,
        selfHealBudget:
          typeof p.self_heal_budget === 'number' ? p.self_heal_budget : next.selfHealBudget,
        mlRetryCount: healAttempt != null && p.kind === 'self_heal' ? healAttempt : next.mlRetryCount,
        experiments:
          p.kind === 'self_heal' && typeof p.experiment_id === 'string'
            ? upsertExperiment(next.experiments, String(p.experiment_id), {
                retryCount: healAttempt ?? undefined,
              })
            : next.experiments,
        activity: pushActivity(next, event, String(p.message ?? 'activity')),
      }
      break
    }
    case 'session_paused':
      next = { ...next, status: 'paused' }
      break
    case 'session_resumed':
      next = { ...next, status: 'running' }
      break
    case 'session_reset':
      next = { ...next, status: 'reset' }
      break
    default:
      break
  }

  return next
}
