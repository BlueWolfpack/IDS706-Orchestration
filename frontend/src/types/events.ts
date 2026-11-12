/** Mirrors contracts.EventEnvelope — frontend only renders these events. */

export type EventType =
  | 'session_created'
  | 'session_paused'
  | 'session_resumed'
  | 'session_reset'
  | 'agent_started'
  | 'agent_completed'
  | 'tool_called'
  | 'tool_result'
  | 'trial_started'
  | 'trial_completed'
  | 'trial_failed'
  | 'verdict_issued'
  | 'budget_update'
  | 'stop_reason'
  | 'holdout_evaluated'
  | 'health'
  | 'wandb_unavailable'
  | 'service_error'
  | 'activity'

export interface EventEnvelope {
  timestamp: string
  session_id: string
  correlation_id: string
  source_service: string
  source_agent: string | null
  type: EventType
  payload: Record<string, unknown>
  mock: boolean
}

export type SessionRunStatus =
  | 'idle'
  | 'created'
  | 'running'
  | 'paused'
  | 'completed'
  | 'reset'
  | 'error'

/** Per-cycle agent payload for Simple/Student loop timeline drill-down. */
export interface AgentCycleOutput {
  note?: string
  used_llm?: boolean
  model?: string | null
  status?: string
  output?: unknown
}

export interface ExperimentEntry {
  experimentId: string
  modelFamily?: string
  status: 'running' | 'completed' | 'failed' | 'validating'
  trainMetrics: Record<string, number>
  validationMetrics: Record<string, number>
  durationSeconds?: number
  verdictAction?: string
  observation?: string
  nextAction?: string
  retryCount?: number
  note?: string
  /** DS / hypothesis / ML outputs for this cycle (expand in Experiment timeline). */
  agentOutputs?: {
    data_scientist?: AgentCycleOutput
    hypothesis_generator?: AgentCycleOutput
    ml_engineer?: AgentCycleOutput
  }
}

export interface ActivityItem {
  id: string
  timestamp: string
  agent: string
  message: string
  type: EventType
}

export type AgentNodeStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface AgentNodeRuntime {
  status: AgentNodeStatus
  lastEventType?: string
  lastPayload?: Record<string, unknown>
  correlationId?: string
  sourceService?: string
  updatedAt?: string
}

export type SessionMode = 'live' | 'mock' | 'replay'

export interface SessionState {
  sessionId: string | null
  status: SessionRunStatus
  mock: boolean
  replay: boolean
  mode: SessionMode
  scenario: string
  dataset: string
  targetColumn: string
  metric: string
  targetScore: number
  experimentBudget: number
  experimentsUsed: number
  /** Per-experiment repair attempts (default 3). */
  selfHealBudget: number
  /** blackbox_tuning | model_search */
  researchStrategy: 'blackbox_tuning' | 'model_search'
  fixedModelFamily: string | null
  /** Train+score wall clock per trial (seconds). */
  perTrialTimeoutSeconds: number
  bestValScore: number | null
  holdoutScore: number | null
  stopReason: string | null
  serviceHealth: Record<string, string>
  experiments: ExperimentEntry[]
  activity: ActivityItem[]
  lastEventType: EventType | null
  error: string | null
  /** Live agent graph — only updated from SSE */
  agentNodes: Record<string, AgentNodeRuntime>
  activeNodeId: string | null
  mlRetryCount: number
  lastCorrelationId: string | null
  /** Full agent/trial trail for experiment drill-down */
  traceEvents: EventEnvelope[]
  activeExperimentId: string | null
}

export const SCENARIOS = [
  'happy',
  'revise_loop',
  'repair',
  'terminal_failure',
  'budget_stop',
  'service_down',
] as const

export type ScenarioName = (typeof SCENARIOS)[number]
