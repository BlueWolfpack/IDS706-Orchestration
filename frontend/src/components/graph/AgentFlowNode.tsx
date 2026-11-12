import { memo } from 'react'
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import type { AgentNodeStatus } from '../../types/events'

export type AgentFlowNodeData = {
  title: string
  role: string
  service: string
  status: AgentNodeStatus
  kind: 'supervisor' | 'lead' | 'subagent' | 'planned'
  planned?: boolean
  expanded?: boolean
  onToggleExpand?: () => void
}

type AgentNode = Node<AgentFlowNodeData, 'agent'>

const statusClass: Record<AgentNodeStatus, string> = {
  pending: 'bg-ink-2 text-mist border-line',
  running: 'bg-teal/15 text-teal border-teal/40',
  completed: 'bg-ok/15 text-ok border-ok/40',
  failed: 'bg-danger/15 text-danger border-danger/40',
}

function AgentFlowNodeComponent({ data }: NodeProps<AgentNode>) {
  const planned = data.kind === 'planned' || data.planned
  const showExpand = data.kind === 'lead' && data.onToggleExpand
  return (
    <div
      className={`min-w-[160px] max-w-[200px] border px-3 py-2 shadow-sm ${
        planned
          ? 'border-dashed border-amber bg-amber/5'
          : data.status === 'running'
            ? 'border-teal bg-panel ring-2 ring-teal/30'
            : 'border-line bg-panel'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-teal !h-2 !w-2" />
      <div className="flex items-start justify-between gap-2">
        <p className={`text-sm font-medium leading-tight ${planned ? 'text-amber' : 'text-paper'}`}>
          {data.title}
        </p>
        <div className="flex shrink-0 items-center gap-1">
          {showExpand && (
            <button
              type="button"
              aria-label={data.expanded ? 'Collapse subagents' : 'Expand subagents'}
              onClick={(e) => {
                e.stopPropagation()
                data.onToggleExpand?.()
              }}
              className="border border-line px-1 font-mono text-[10px] text-mist hover:border-teal hover:text-teal"
            >
              {data.expanded ? '−' : '+'}
            </button>
          )}
          <span
            className={`rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide ${
              planned ? 'border-amber/40 text-amber' : statusClass[data.status]
            }`}
          >
            {planned ? 'planned' : data.status}
          </span>
        </div>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-mist">{data.role}</p>
      <p className="mt-2 font-mono text-[9px] uppercase tracking-wider text-teal-dim">{data.service}</p>
      <Handle type="source" position={Position.Bottom} className="!bg-teal !h-2 !w-2" />
    </div>
  )
}

export const AgentFlowNode = memo(AgentFlowNodeComponent)
