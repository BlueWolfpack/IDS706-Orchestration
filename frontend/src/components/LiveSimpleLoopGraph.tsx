import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  useReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  type NodeMouseHandler,
  type OnNodesChange,
} from '@xyflow/react'
import { SIMPLE_LOOP_CONFIG, type LoopGraphConfig } from '../graph/simpleLoopConfig'
import {
  SimpleLoopFlowNode,
  type SimpleLoopFlowNodeData,
} from './graph/SimpleLoopFlowNode'

const nodeTypes = { simple: SimpleLoopFlowNode }

export type SimpleNodeStatus = 'pending' | 'running' | 'completed' | 'failed'

export type SimpleLoopRuntime = Record<string, { status: SimpleNodeStatus; note?: string }>

function edgeStyle(kind: string, animated: boolean): Partial<Edge> {
  const stroke = animated ? '#0d8f6e' : kind === 'data' ? '#5a7267' : '#14241e'
  return {
    // Orthogonal only — axis-aligned nodes → straight segments; L for revise.
    type: 'step',
    pathOptions: { offset: 0, borderRadius: 0 },
    animated,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 12,
      height: 12,
      color: stroke,
    },
    style: {
      stroke,
      strokeWidth: animated ? 2.25 : 1.5,
      strokeDasharray: kind === 'data' ? '6 4' : undefined,
      opacity: animated ? 1 : 0.8,
    },
    labelStyle: { fill: '#5a7267', fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fill: '#ffffff', fillOpacity: 0.92 },
    labelBgPadding: [4, 2] as [number, number],
  }
}

function SimpleLegend() {
  return (
    <div className="absolute bottom-3 left-3 z-10 border border-line bg-panel/95 px-3 py-2 text-[10px] text-mist shadow-sm">
      <p className="mb-1 font-mono uppercase tracking-wider text-paper">Legend</p>
      <ul className="space-y-1">
        <li className="flex items-center gap-2">
          <span className="inline-block h-px w-6 bg-paper" /> control flow
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-px w-6 border-t border-dashed border-mist" /> data / memory
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-3 w-5 border border-dashed border-mist bg-ink-2" /> dataset file
        </li>
      </ul>
    </div>
  )
}

function initialNodes(cfg: LoopGraphConfig, visibleIds?: ReadonlySet<string> | null): Node[] {
  const list = visibleIds == null ? cfg.nodes : cfg.nodes.filter((n) => visibleIds.has(n.id))
  return list.map((n) => ({
    id: n.id,
    type: 'simple',
    position: cfg.positions[n.id] ?? { x: 0, y: 0 },
    data: {
      title: n.title,
      role: n.role,
      service: n.service,
      status: 'pending',
      kind: n.kind,
    } satisfies SimpleLoopFlowNodeData,
    draggable: true,
  }))
}

function LiveSimpleLoopGraphInner({
  runtime,
  activeNodeId,
  datasetLabel,
  targetColumn,
  visibleNodeIds,
  visibleEdgeKeys,
  config = SIMPLE_LOOP_CONFIG,
}: {
  /** Which loop layout to draw (defaults to the class template). */
  config?: LoopGraphConfig
  runtime: SimpleLoopRuntime
  activeNodeId: string | null
  datasetLabel?: string | null
  targetColumn?: string | null
  /** undefined = full graph; array = only these visual ids (progressive student build). */
  visibleNodeIds?: string[]
  /** When set with progressive mode, only these `source->target` visual edges render. */
  visibleEdgeKeys?: string[]
}) {
  const visibleIds = useMemo(
    () => (visibleNodeIds === undefined ? null : new Set(visibleNodeIds)),
    [visibleNodeIds],
  )
  const edgeKeySet = useMemo(
    () => (visibleEdgeKeys === undefined ? null : new Set(visibleEdgeKeys)),
    [visibleEdgeKeys],
  )
  const visibleKey = visibleNodeIds === undefined ? '*' : visibleNodeIds.slice().sort().join(',')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [nodes, setNodes] = useState<Node[]>(() => initialNodes(config, visibleIds))
  const [expanded, setExpanded] = useState(false)
  const { fitView } = useReactFlow()

  useEffect(() => {
    setNodes(initialNodes(config, visibleIds))
    setSelectedId(null)
  }, [visibleKey, visibleIds, config])

  const refit = useCallback(() => {
    // Two frames: first paints nodes, second measures bounds for fitView.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        // Lower minZoom so wide full graphs still fit; higher maxZoom so
        // early progressive spines (2–3 nodes) can fill the viewport.
        fitView({ padding: 0.16, duration: 220, minZoom: 0.2, maxZoom: 1.6 })
      })
    })
  }, [fitView])

  // Refit after progressive node sets change — initial fitView alone leaves sparse
  // graphs parked at the canvas edge.
  useEffect(() => {
    refit()
  }, [visibleKey, expanded, refit])

  useEffect(() => {
    if (!expanded) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(false)
    }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [expanded])

  const displayNodes: Node[] = useMemo(() => {
    return nodes.map((node) => {
      const meta = config.nodes.find((n) => n.id === node.id)
      const rt = runtime[node.id]
      const isDataset = node.id === 'dataset'
      const data: SimpleLoopFlowNodeData = {
        title: isDataset
          ? datasetLabel?.trim() || meta?.title || 'dataset.csv'
          : meta?.title ?? node.id,
        role: isDataset
          ? targetColumn?.trim()
            ? `Input table · ${targetColumn} target`
            : 'Input table · choose target'
          : meta?.role ?? '',
        service: meta?.service ?? '',
        status: rt?.status ?? 'pending',
        kind: meta?.kind ?? 'code',
      }
      return {
        ...node,
        data,
        selected: selectedId === node.id,
        draggable: true,
      }
    })
  }, [nodes, runtime, selectedId, datasetLabel, targetColumn, config])

  const onNodesChange: OnNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((prev) => applyNodeChanges(changes, prev))
  }, [])

  const resetLayout = useCallback(() => {
    setNodes(initialNodes(config, visibleIds))
    setSelectedId(null)
    refit()
  }, [visibleIds, refit, config])

  const edges: Edge[] = useMemo(() => {
    const running = new Set(
      Object.entries(runtime)
        .filter(([, r]) => r.status === 'running')
        .map(([id]) => id),
    )
    return config.edges.filter((e) => {
      if (visibleIds == null) return true
      if (!visibleIds.has(e.source) || !visibleIds.has(e.target)) return false
      // Progressive student build: only show edges they actually declared.
      if (edgeKeySet != null) return edgeKeySet.has(`${e.source}->${e.target}`)
      return true
    }).map((e) => {
      const animated = running.has(e.target)
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle,
        targetHandle: e.targetHandle,
        label: e.label,
        ...edgeStyle(e.kind, animated),
      }
    })
  }, [runtime, visibleIds, edgeKeySet, config])

  const onNodeClick: NodeMouseHandler = (_e, node) => {
    setSelectedId(node.id)
  }

  const selectedMeta = config.nodes.find((n) => n.id === selectedId)
  const selectedRt = selectedId ? runtime[selectedId] : undefined
  const selected =
    selectedMeta == null
      ? null
      : selectedMeta.id === 'dataset'
        ? {
            ...selectedMeta,
            title: datasetLabel?.trim() || selectedMeta.title,
            role: targetColumn?.trim()
              ? `Input table · ${targetColumn} target`
              : selectedMeta.role,
          }
        : selectedMeta

  return (
    <>
    {expanded ? <div className="h-[520px]" aria-hidden /> : null}
    <section
      className={
        expanded
          ? 'fixed inset-0 z-50 flex flex-col border border-line bg-panel'
          : 'relative flex h-[520px] flex-col border border-line bg-panel/40'
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
        <div>
          <h2 className="font-display text-xl text-paper">Live agent graph</h2>
          <p className="text-xs text-mist">
            Research loop · status from SSE only
            {activeNodeId ? ` · active: ${activeNodeId}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="border border-line px-2 py-1 font-mono text-[11px] text-mist hover:border-teal hover:text-teal"
          >
            {expanded ? 'Collapse' : 'Expand'}
          </button>
          <button
            type="button"
            onClick={resetLayout}
            className="border border-line px-2 py-1 font-mono text-[11px] text-mist hover:border-teal hover:text-teal"
          >
            Reset layout
          </button>
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
        <ReactFlow
          nodes={displayNodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onNodeClick={onNodeClick}
          fitView
          fitViewOptions={{ padding: 0.16, minZoom: 0.2, maxZoom: 1.6 }}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          snapToGrid
          snapGrid={[20, 20]}
          proOptions={{ hideAttribution: true }}
          minZoom={0.2}
          maxZoom={1.6}
          defaultEdgeOptions={{ type: 'step' }}
        >
          <Background gap={20} color="#c8d5ce" />
          <Controls showInteractive={false} />
          <SimpleLegend />
        </ReactFlow>
        {selected && (
          <aside className="absolute right-3 top-3 z-10 w-64 border border-line bg-panel/95 p-3 text-sm shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <p className="font-medium text-paper">{selected.title}</p>
              <button
                type="button"
                className="font-mono text-xs text-mist hover:text-teal"
                onClick={() => setSelectedId(null)}
              >
                close
              </button>
            </div>
            <p className="mt-1 text-xs text-mist">{selected.role}</p>
            <p className="mt-2 font-mono text-[10px] uppercase tracking-wide text-teal">
              {selectedRt?.status ?? 'pending'} · {selected.kind.replace('_', '+')}
            </p>
            {selectedRt?.note && (
              <p className="mt-2 text-xs leading-snug text-mist">{selectedRt.note}</p>
            )}
          </aside>
        )}
      </div>
    </section>
    </>
  )
}

export function LiveSimpleLoopGraph(props: {
  config?: LoopGraphConfig
  runtime: SimpleLoopRuntime
  activeNodeId: string | null
  datasetLabel?: string | null
  targetColumn?: string | null
  visibleNodeIds?: string[]
  visibleEdgeKeys?: string[]
}) {
  return (
    <ReactFlowProvider>
      <LiveSimpleLoopGraphInner {...props} />
    </ReactFlowProvider>
  )
}

/** Expand LangGraph node names into visual ids used by simpleLoopConfig. */
export function visualIdsFromLangGraphNodes(nodes: string[]): Set<string> {
  const v = new Set<string>()
  for (const n of nodes) {
    v.add(n)
    if (n === 'data_scientist') v.add('dataset')
    if (n === 'judge') v.add('router')
    if (n === 'memory_writer') v.add('research_memory')
    if (n === 'holdout_eval') v.add('best_candidate')
  }
  return v
}

/** Map declared LangGraph edges onto visual `source->target` keys. */
export function visualEdgeKeysFromLangGraph(
  edges: { source: string; target: string }[],
): string[] {
  const keys = new Set<string>()
  const add = (a: string, b: string) => keys.add(`${a}->${b}`)

  for (const { source, target } of edges) {
    const s = source === 'START' ? '__start__' : source
    const t = target === 'END' ? '__end__' : target

    if ((s === '__start__' || s === 'START') && t === 'data_scientist') {
      add('dataset', 'data_scientist')
    } else if (s === 'data_scientist' && t === 'hypothesis_generator') {
      add('data_scientist', 'hypothesis_generator')
    } else if (s === 'hypothesis_generator' && t === 'ml_engineer') {
      add('hypothesis_generator', 'ml_engineer')
    } else if (s === 'ml_engineer' && t === 'judge') {
      add('ml_engineer', 'judge')
    } else if (s === 'judge' && t === 'memory_writer') {
      add('judge', 'router')
      add('router', 'memory_writer')
    } else if (s === 'memory_writer' && t === 'context_builder') {
      add('memory_writer', 'research_memory')
      add('research_memory', 'context_builder')
    } else if (s === 'context_builder' && t === 'hypothesis_generator') {
      add('context_builder', 'hypothesis_generator')
    } else if (s === 'judge' && t === 'holdout_eval') {
      add('judge', 'router')
      add('router', 'best_candidate')
      add('best_candidate', 'holdout_eval')
    } else if (s === 'holdout_eval' && (t === '__end__' || t === 'END')) {
      // terminal — no extra visual edge
    } else {
      add(s, t)
    }
  }
  return Array.from(keys)
}
