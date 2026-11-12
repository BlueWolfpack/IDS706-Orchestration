import { memo } from 'react'
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'

export type SimpleLoopFlowNodeData = {
  title: string
  role: string
  service: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  kind: string
}

type SimpleNode = Node<SimpleLoopFlowNodeData, 'simple'>

const statusClass: Record<SimpleLoopFlowNodeData['status'], string> = {
  pending: 'bg-ink-2 text-mist border-line',
  running: 'bg-teal/15 text-teal border-teal/40',
  completed: 'bg-ok/15 text-ok border-ok/40',
  failed: 'bg-danger/15 text-danger border-danger/40',
}

const handleClass = '!h-2 !w-2 !border-line !bg-teal'

function SimpleLoopFlowNodeComponent({ data }: NodeProps<SimpleNode>) {
  const running = data.status === 'running'
  const isFile = data.kind === 'file'
  return (
    <div
      className={`relative min-w-[168px] max-w-[190px] border px-3 py-2 shadow-sm ${
        isFile
          ? 'border-dashed border-mist bg-ink-2/80'
          : running
            ? 'border-teal bg-panel ring-2 ring-teal/30'
            : 'border-line bg-panel'
      }`}
    >
      {/* Inbound / outbound on each side so revise loop can run right→left and up. */}
      <Handle id="left-in" type="target" position={Position.Left} className={handleClass} />
      <Handle id="left-out" type="source" position={Position.Left} className={handleClass} />
      <Handle id="right-out" type="source" position={Position.Right} className={handleClass} />
      <Handle id="right-in" type="target" position={Position.Right} className={handleClass} />
      <Handle id="top-in" type="target" position={Position.Top} className={handleClass} />
      <Handle id="top-out" type="source" position={Position.Top} className={handleClass} />
      <Handle id="bottom-out" type="source" position={Position.Bottom} className={handleClass} />
      <Handle id="bottom-in" type="target" position={Position.Bottom} className={handleClass} />

      <div className="flex items-start justify-between gap-2">
        <p
          className={`text-sm font-medium leading-tight ${
            isFile ? 'font-mono text-[12px] text-paper' : 'text-paper'
          }`}
        >
          {data.title}
        </p>
        <span
          className={`shrink-0 rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide ${
            isFile
              ? 'border-line bg-panel text-mist'
              : statusClass[data.status]
          }`}
        >
          {isFile ? 'csv' : data.status}
        </span>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-mist">{data.role}</p>
      <p className="mt-2 font-mono text-[9px] uppercase tracking-wider text-teal-dim">
        {data.service}
      </p>
    </div>
  )
}

export const SimpleLoopFlowNode = memo(SimpleLoopFlowNodeComponent)
