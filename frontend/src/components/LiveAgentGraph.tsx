import { useCallback, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from '@xyflow/react'
import { AGENT_EDGES, AGENT_NODES } from '../graph/agentGraphConfig'
import { GRAPH_POSITIONS } from '../graph/graphLayout'
import type { SessionState } from '../types/events'
import { AgentFlowNode, type AgentFlowNodeData } from './graph/AgentFlowNode'
import { GraphLegend } from './graph/GraphLegend'
import { NodeSidePanel } from './graph/NodeSidePanel'

const nodeTypes = { agent: AgentFlowNode }

type ViewMode = 'overview' | 'detailed'

function edgeStyle(kind: string, animated: boolean, highlighted: boolean): Partial<Edge> {
  const base: Partial<Edge> = {
    type: 'smoothstep',
    animated: animated && !highlighted ? true : animated,
    style: {
      stroke: highlighted ? '#0d8f6e' : kind === 'control' ? '#14241e' : '#5a7267',
      strokeWidth: highlighted ? 2.5 : 1.5,
      strokeDasharray: kind === 'data' ? '6 4' : kind === 'event' ? '2 3' : undefined,
      opacity: highlighted ? 1 : 0.55,
    },
    labelStyle: { fill: '#5a7267', fontSize: 10 },
  }
  return base
}

function LiveAgentGraphInner({ state }: { state: SessionState }) {
  const [mode, setMode] = useState<ViewMode>('detailed')
  const [expandedLeads, setExpandedLeads] = useState<Record<string, boolean>>({
    data_scientist: true,
    hypothesis_generator: true,
    ml_engineer: true,
    judge: true,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const visibleNodeIds = useMemo(() => {
    const ids = new Set<string>()
    for (const n of AGENT_NODES) {
      if (n.kind === 'planned') {
        ids.add(n.id)
        continue
      }
      if (n.kind === 'supervisor' || n.kind === 'lead') {
        ids.add(n.id)
        continue
      }
      if (mode === 'overview') continue
      if (n.leadId && expandedLeads[n.leadId] !== false) ids.add(n.id)
    }
    return ids
  }, [mode, expandedLeads])

  const toggleLeadExpand = useCallback((leadId: string) => {
    setMode('detailed')
    setExpandedLeads((prev) => ({ ...prev, [leadId]: prev[leadId] === false }))
  }, [])

  const nodes: Node[] = useMemo(() => {
    return AGENT_NODES.filter((n) => visibleNodeIds.has(n.id)).map((n) => {
      const runtime = state.agentNodes[n.id]
      const data: AgentFlowNodeData = {
        title: n.title,
        role: n.role,
        service: n.service,
        status: runtime?.status ?? 'pending',
        kind: n.kind,
        planned: n.kind === 'planned',
        expanded: n.kind === 'lead' ? expandedLeads[n.id] !== false : undefined,
        onToggleExpand: n.kind === 'lead' ? () => toggleLeadExpand(n.id) : undefined,
      }
      return {
        id: n.id,
        type: 'agent',
        position: GRAPH_POSITIONS[n.id] ?? { x: 0, y: 0 },
        data,
        selected: selectedId === n.id,
        // Planned nodes never pick up live animation styling beyond dashed look.
        draggable: false,
      }
    })
  }, [visibleNodeIds, state.agentNodes, selectedId, expandedLeads, toggleLeadExpand])

  const edges: Edge[] = useMemo(() => {
    const running = new Set(
      Object.entries(state.agentNodes)
        .filter(([, r]) => r.status === 'running')
        .map(([id]) => id),
    )
    return AGENT_EDGES.filter((e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)).map(
      (e) => {
        const planned =
          AGENT_NODES.find((n) => n.id === e.source)?.kind === 'planned' ||
          AGENT_NODES.find((n) => n.id === e.target)?.kind === 'planned'
        // Animate only when the target is actually running from SSE — never for planned.
        const animated = !planned && running.has(e.target)
        const highlighted =
          !!selectedId && (e.source === selectedId || e.target === selectedId)
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.label,
          ...edgeStyle(e.kind, animated, highlighted),
          // Keep planned edges muted and never animated.
          animated: planned ? false : animated,
          style: {
            ...edgeStyle(e.kind, animated, highlighted).style,
            ...(planned
              ? { stroke: '#9a6b12', strokeDasharray: '6 4', opacity: 0.45 }
              : null),
          },
        }
      },
    )
  }, [visibleNodeIds, state.agentNodes, selectedId])

  const onNodeClick: NodeMouseHandler = useCallback((_event, node) => {
    setSelectedId(node.id)
  }, [])

  return (
    <section className="relative flex h-[520px] flex-col border border-line bg-panel/40">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
        <div>
          <h2 className="font-display text-xl text-paper">Live agent graph</h2>
          <p className="text-xs text-mist">
            Four leads and twelve subagents · status from SSE only
            {state.activeNodeId ? ` · active: ${state.activeNodeId}` : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setMode('overview')}
            className={`border px-2 py-1 text-xs ${
              mode === 'overview' ? 'border-teal bg-teal/10 text-teal' : 'border-line text-mist'
            }`}
          >
            Overview
          </button>
          <button
            type="button"
            onClick={() => setMode('detailed')}
            className={`border px-2 py-1 text-xs ${
              mode === 'detailed' ? 'border-teal bg-teal/10 text-teal' : 'border-line text-mist'
            }`}
          >
            Detailed
          </button>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
          minZoom={0.4}
          maxZoom={1.4}
        >
          <Background gap={20} color="#c8d5ce" />
          <Controls showInteractive={false} />
          <GraphLegend />
        </ReactFlow>
        <NodeSidePanel
          nodeId={selectedId}
          runtime={selectedId ? state.agentNodes[selectedId] : undefined}
          mlRetryCount={state.mlRetryCount}
          onClose={() => setSelectedId(null)}
        />
      </div>
    </section>
  )
}

export function LiveAgentGraph({ state }: { state: SessionState }) {
  return (
    <ReactFlowProvider>
      <LiveAgentGraphInner state={state} />
    </ReactFlowProvider>
  )
}
