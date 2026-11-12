/** Diagram config for the teaching “simple research loop” (live React Flow). */

export type SimpleLoopNodeId =
  | 'dataset'
  | 'data_scientist'
  | 'hypothesis_generator'
  | 'ml_engineer'
  | 'judge'
  | 'router'
  | 'memory_writer'
  | 'research_memory'
  | 'context_builder'
  | 'holdout_eval'
  | 'best_candidate'

export type SimpleLoopNodeKind = 'file' | 'llm' | 'code' | 'code_llm' | 'store'

export interface SimpleLoopNode {
  id: SimpleLoopNodeId
  title: string
  role: string
  kind: SimpleLoopNodeKind
  service: string
}

export interface SimpleLoopEdge {
  id: string
  source: SimpleLoopNodeId
  target: SimpleLoopNodeId
  kind: 'control' | 'data'
  label?: string
  sourceHandle?: string
  targetHandle?: string
}

/** Generic shape so LiveSimpleLoopGraph can draw other loop layouts (see fraudLoopConfig.ts). */
export interface LoopGraphConfig {
  nodes: { id: string; title: string; role: string; kind: SimpleLoopNodeKind; service: string }[]
  edges: {
    id: string
    source: string
    target: string
    kind: 'control' | 'data'
    label?: string
    sourceHandle?: string
    targetHandle?: string
  }[]
  positions: Record<string, { x: number; y: number }>
}

export const SIMPLE_LOOP_NODES: SimpleLoopNode[] = [
  {
    id: 'dataset',
    title: 'dataset.csv',
    role: 'Input table · choose target',
    kind: 'file',
    service: 'dataset file',
  },
  {
    id: 'data_scientist',
    title: 'Data Scientist',
    role: 'Profile + leakage only',
    kind: 'llm',
    service: 'node script',
  },
  {
    id: 'hypothesis_generator',
    title: 'Hypothesis Generator',
    role: 'Conceptual next step (no HPT)',
    kind: 'llm',
    service: 'node script',
  },
  {
    id: 'ml_engineer',
    title: 'ML Engineer',
    role: 'HPT config · train · repair',
    kind: 'code_llm',
    service: 'node script',
  },
  {
    id: 'judge',
    title: 'Judge',
    role: 'Verdict from val evidence',
    kind: 'llm',
    service: 'node script',
  },
  {
    id: 'router',
    title: 'Router',
    role: 'accept · revise · stop',
    kind: 'code',
    service: 'langgraph edge',
  },
  {
    id: 'memory_writer',
    title: 'Memory writer',
    role: 'File verdict + lesson',
    kind: 'code',
    service: 'node script',
  },
  {
    id: 'research_memory',
    title: 'Research memory',
    role: 'history · findings · lessons',
    kind: 'store',
    service: 'json store',
  },
  {
    id: 'context_builder',
    title: 'Context builder',
    role: 'Brief for next hypothesis',
    kind: 'code',
    service: 'node script',
  },
  {
    id: 'best_candidate',
    title: 'Best candidate',
    role: 'Accepted model + val evidence',
    kind: 'store',
    service: 'state',
  },
  {
    id: 'holdout_eval',
    title: 'Final holdout',
    role: 'Open sealed holdout once',
    kind: 'code',
    service: 'node script',
  },
]

/**
 * Grid: x step 260, y step 210 — keeps default edges straight (L/R or T/B).
 */
export const SIMPLE_LOOP_EDGES: SimpleLoopEdge[] = [
  // Entry — CSV into Data Scientist
  {
    id: 'e-csv-ds',
    source: 'dataset',
    target: 'data_scientist',
    kind: 'data',
    label: 'csv',
    sourceHandle: 'right-out',
    targetHandle: 'left-in',
  },
  // Main spine — horizontal
  {
    id: 'e-ds-hyp',
    source: 'data_scientist',
    target: 'hypothesis_generator',
    kind: 'control',
    sourceHandle: 'right-out',
    targetHandle: 'left-in',
  },
  {
    id: 'e-hyp-ml',
    source: 'hypothesis_generator',
    target: 'ml_engineer',
    kind: 'control',
    sourceHandle: 'right-out',
    targetHandle: 'left-in',
  },
  {
    id: 'e-ml-judge',
    source: 'ml_engineer',
    target: 'judge',
    kind: 'control',
    sourceHandle: 'right-out',
    targetHandle: 'left-in',
  },
  {
    id: 'e-judge-router',
    source: 'judge',
    target: 'router',
    kind: 'control',
    sourceHandle: 'right-out',
    targetHandle: 'left-in',
  },
  // Revise loop — down from router, left into memory writer, left, up into hyp
  {
    id: 'e-router-mem',
    source: 'router',
    target: 'memory_writer',
    kind: 'control',
    label: 'revise',
    sourceHandle: 'bottom-out',
    targetHandle: 'right-in',
  },
  {
    id: 'e-mem-store',
    source: 'memory_writer',
    target: 'research_memory',
    kind: 'data',
    sourceHandle: 'left-out',
    targetHandle: 'right-in',
  },
  {
    id: 'e-store-ctx',
    source: 'research_memory',
    target: 'context_builder',
    kind: 'data',
    sourceHandle: 'left-out',
    targetHandle: 'right-in',
  },
  {
    id: 'e-ctx-hyp',
    source: 'context_builder',
    target: 'hypothesis_generator',
    kind: 'control',
    label: 'brief',
    sourceHandle: 'top-out',
    targetHandle: 'bottom-in',
  },
  // Accept / stop — straight down under router, then right to holdout
  {
    id: 'e-router-best',
    source: 'router',
    target: 'best_candidate',
    kind: 'control',
    label: 'accept/stop',
    sourceHandle: 'bottom-out',
    targetHandle: 'top-in',
  },
  {
    id: 'e-best-hold',
    source: 'best_candidate',
    target: 'holdout_eval',
    kind: 'control',
    sourceHandle: 'right-out',
    targetHandle: 'left-in',
  },
]

/**
 * Classroom snap layout (x step 260, y: 40 / 260 / 480).
 * Columns align so control edges stay axis-aligned (straight step paths):
 *   top:    dataset · ds · hyp · ml · judge · router
 *   mid:               ctx · mem · writer
 *   bottom:                         best · holdout
 */
export const SIMPLE_LOOP_POSITIONS: Record<SimpleLoopNodeId, { x: number; y: number }> = {
  dataset: { x: 0, y: 40 },
  data_scientist: { x: 260, y: 40 },
  hypothesis_generator: { x: 520, y: 40 },
  ml_engineer: { x: 780, y: 40 },
  judge: { x: 1040, y: 40 },
  router: { x: 1300, y: 40 },
  // Mid row under hyp / ml / judge (not under router) → revise is a clean L
  context_builder: { x: 520, y: 260 },
  research_memory: { x: 780, y: 260 },
  memory_writer: { x: 1040, y: 260 },
  best_candidate: { x: 1300, y: 480 },
  holdout_eval: { x: 1560, y: 480 },
}

export const SIMPLE_LOOP_FLOW = [
  'data_scientist',
  'hypothesis_generator',
  'ml_engineer',
  'judge',
  'router',
] as const

export const GRAPH_NODE_TO_VISUAL: Record<string, SimpleLoopNodeId> = {
  data_scientist: 'data_scientist',
  hypothesis_generator: 'hypothesis_generator',
  ml_engineer: 'ml_engineer',
  judge: 'judge',
  router: 'router',
  memory_writer: 'memory_writer',
  research_memory: 'research_memory',
  context_builder: 'context_builder',
  holdout_eval: 'holdout_eval',
}

export const SIMPLE_LOOP_CONFIG: LoopGraphConfig = {
  nodes: SIMPLE_LOOP_NODES,
  edges: SIMPLE_LOOP_EDGES,
  positions: SIMPLE_LOOP_POSITIONS,
}
