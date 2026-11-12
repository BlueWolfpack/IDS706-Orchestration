export type AgentStatus = 'pending' | 'running' | 'completed' | 'failed'

export type EdgeKind = 'control' | 'data' | 'event'

export interface AgentNodeDef {
  id: string
  title: string
  role: string
  /** Service that executes this node in the real system */
  service: string
  kind: 'supervisor' | 'lead' | 'subagent' | 'planned'
  leadId?: string
  responsibility: string
}

export interface AgentEdgeDef {
  id: string
  source: string
  target: string
  kind: EdgeKind
  label?: string
}

export interface NodeRuntime {
  status: AgentStatus
  lastEventType?: string
  lastPayload?: Record<string, unknown>
  correlationId?: string
  sourceService?: string
  updatedAt?: string
}
