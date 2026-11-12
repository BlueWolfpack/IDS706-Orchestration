import { memo } from 'react'
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'

export type StaticNodeData = {
  title: string
  role: string
  planned?: boolean
  optional?: boolean
  kind?: string
}

type StaticNode = Node<StaticNodeData, 'static'>

function StaticDiagramNodeComponent({ data }: NodeProps<StaticNode>) {
  const amber = data.planned || data.optional
  return (
    <div
      className={`min-w-[160px] max-w-[220px] border px-3 py-2 ${
        amber ? 'border-dashed border-amber bg-amber/5' : 'border-line bg-panel'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !bg-teal" />
      <p className={`text-sm font-medium ${amber ? 'text-amber' : 'text-paper'}`}>{data.title}</p>
      <p className="mt-1 text-[11px] text-mist">{data.role}</p>
      {amber && (
        <p className="mt-1 font-mono text-[9px] uppercase tracking-wider text-amber">
          {data.planned ? 'planned' : 'optional'}
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-teal" />
    </div>
  )
}

export const StaticDiagramNode = memo(StaticDiagramNodeComponent)
