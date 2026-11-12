import { useMemo, useState } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from '@xyflow/react'
import { StaticDiagramNode, type StaticNodeData } from './graph/StaticDiagramNode'

const nodeTypes = { static: StaticDiagramNode }

export interface StaticItem {
  id: string
  title: string
  role: string
  planned?: boolean
  optional?: boolean
  detail?: Record<string, unknown>
}

export interface StaticLink {
  id: string
  source: string
  target: string
  label?: string
  kind?: 'rest' | 'events' | 'store' | 'mcp' | 'control' | 'planned'
  planned?: boolean
}

function styleFor(kind?: string, planned?: boolean): Partial<Edge> {
  if (planned || kind === 'planned') {
    return {
      type: 'smoothstep',
      animated: false,
      style: { stroke: '#9a6b12', strokeDasharray: '6 4', opacity: 0.7 },
    }
  }
  const dash =
    kind === 'events' ? '2 3' : kind === 'store' || kind === 'mcp' ? '6 3' : undefined
  const stroke = kind === 'mcp' ? '#0d8f6e' : '#14241e'
  return {
    type: 'smoothstep',
    style: { stroke, strokeWidth: 1.5, strokeDasharray: dash, opacity: 0.7 },
    labelStyle: { fill: '#5a7267', fontSize: 10 },
  }
}

function StaticFlowDiagramInner({
  title,
  blurb,
  items,
  links,
  positions,
}: {
  title: string
  blurb: string
  items: StaticItem[]
  links: StaticLink[]
  positions: Record<string, { x: number; y: number }>
}) {
  const [selected, setSelected] = useState<StaticItem | null>(null)

  const nodes: Node[] = useMemo(
    () =>
      items.map((item) => ({
        id: item.id,
        type: 'static',
        position: positions[item.id] ?? { x: 0, y: 0 },
        data: {
          title: item.title,
          role: item.role,
          planned: item.planned,
          optional: item.optional,
        } satisfies StaticNodeData,
        draggable: false,
      })),
    [items, positions],
  )

  const edges: Edge[] = useMemo(
    () =>
      links.map((link) => ({
        id: link.id,
        source: link.source,
        target: link.target,
        label: link.label,
        ...styleFor(link.kind, link.planned),
      })),
    [links],
  )

  const onNodeClick: NodeMouseHandler = (_e, node) => {
    setSelected(items.find((i) => i.id === node.id) ?? null)
  }

  return (
    <section className="relative flex h-[640px] flex-col border border-line bg-panel/40">
      <div className="border-b border-line px-4 py-3">
        <h1 className="font-display text-2xl text-paper">{title}</h1>
        <p className="text-sm text-mist">{blurb}</p>
      </div>
      <div className="relative min-h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} color="#c8d5ce" />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable />
        </ReactFlow>
        {selected && (
          <aside className="absolute right-0 top-0 z-10 h-full w-72 overflow-auto border-l border-line bg-panel p-3 text-sm shadow-lg">
            <div className="flex items-start justify-between gap-2">
              <h2 className="font-display text-lg text-paper">{selected.title}</h2>
              <button type="button" className="text-mist" onClick={() => setSelected(null)}>
                ✕
              </button>
            </div>
            <p className="mt-1 text-mist">{selected.role}</p>
            {selected.detail && (
              <pre className="mt-3 overflow-auto border border-line bg-ink-2 p-2 text-[10px]">
                {JSON.stringify(selected.detail, null, 2)}
              </pre>
            )}
          </aside>
        )}
      </div>
    </section>
  )
}

export function StaticFlowDiagram(props: {
  title: string
  blurb: string
  items: StaticItem[]
  links: StaticLink[]
  positions: Record<string, { x: number; y: number }>
}) {
  return (
    <ReactFlowProvider>
      <StaticFlowDiagramInner {...props} />
    </ReactFlowProvider>
  )
}
