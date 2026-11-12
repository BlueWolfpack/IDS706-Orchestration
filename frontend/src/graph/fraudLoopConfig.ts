/**
 * Live-graph config for the adapted fraud research loop (lab/langgraph/graph.py).
 *
 * Changes vs simpleLoopConfig.ts (the class template):
 *   + warehouse_db / warehouse_loader  — read the Airflow output from Postgres
 *   + baseline_agent                   — dummy baselines before any model is trained
 *   + evaluation_reporter              — holdout vs baseline report
 *   − context_builder                  — merged into memory_writer
 *   ~ data_scientist / ml_engineer / judge roles updated
 */
import type { LoopGraphConfig } from './simpleLoopConfig'

export const FRAUD_LOOP_NODES: LoopGraphConfig['nodes'] = [
  { id: 'warehouse_db', title: 'Postgres warehouse', role: 'analytics.fraud_transactions (Airflow)', kind: 'store', service: 'postgres' },
  { id: 'dataset', title: 'fraud_clean.csv', role: 'CSV fallback · choose target', kind: 'file', service: 'dataset file' },
  { id: 'warehouse_loader', title: 'Warehouse loader', role: 'Pull cleaned table from Postgres', kind: 'code', service: 'node script · NEW' },
  { id: 'data_scientist', title: 'Data Scientist', role: 'Profile + leakage scan (AUC ≥ 0.95)', kind: 'code_llm', service: 'node script · MODIFIED' },
  { id: 'baseline_agent', title: 'Baseline agent', role: 'Majority + flag-everything scores', kind: 'code', service: 'node script · NEW' },
  { id: 'hypothesis_generator', title: 'Hypothesis Generator', role: 'Conceptual next step (no HPT)', kind: 'llm', service: 'node script' },
  { id: 'ml_engineer', title: 'ML Engineer', role: 'Class weights · F1-tuned threshold', kind: 'code_llm', service: 'node script · MODIFIED' },
  { id: 'judge', title: 'Judge', role: 'F1 + PR-AUC lift · accept/revise/stop', kind: 'llm', service: 'node script · MODIFIED' },
  { id: 'router', title: 'Router', role: 'revise → loop · accept/stop → holdout', kind: 'code', service: 'langgraph edge' },
  { id: 'memory_writer', title: 'Memory writer', role: 'File lesson + build brief', kind: 'code', service: 'node script · MODIFIED' },
  { id: 'research_memory', title: 'Research memory', role: 'history · lessons · baseline', kind: 'store', service: 'state' },
  { id: 'best_candidate', title: 'Best candidate', role: 'Best val F1 + threshold', kind: 'store', service: 'state' },
  { id: 'holdout_eval', title: 'Final holdout', role: 'Open sealed holdout once', kind: 'code', service: 'node script' },
  { id: 'evaluation_reporter', title: 'Evaluation reporter', role: 'Holdout vs baselines → report', kind: 'code', service: 'node script · NEW' },
]

export const FRAUD_LOOP_EDGES: LoopGraphConfig['edges'] = [
  { id: 'f-db-loader', source: 'warehouse_db', target: 'warehouse_loader', kind: 'data', label: 'sql', sourceHandle: 'top-out', targetHandle: 'bottom-in' },
  { id: 'f-csv-loader', source: 'dataset', target: 'warehouse_loader', kind: 'data', label: 'fallback', sourceHandle: 'right-out', targetHandle: 'left-in' },
  { id: 'f-loader-ds', source: 'warehouse_loader', target: 'data_scientist', kind: 'control', sourceHandle: 'right-out', targetHandle: 'left-in' },
  { id: 'f-ds-base', source: 'data_scientist', target: 'baseline_agent', kind: 'control', sourceHandle: 'right-out', targetHandle: 'left-in' },
  { id: 'f-base-hyp', source: 'baseline_agent', target: 'hypothesis_generator', kind: 'control', sourceHandle: 'right-out', targetHandle: 'left-in' },
  { id: 'f-hyp-ml', source: 'hypothesis_generator', target: 'ml_engineer', kind: 'control', sourceHandle: 'right-out', targetHandle: 'left-in' },
  { id: 'f-ml-judge', source: 'ml_engineer', target: 'judge', kind: 'control', sourceHandle: 'right-out', targetHandle: 'left-in' },
  { id: 'f-judge-router', source: 'judge', target: 'router', kind: 'control', sourceHandle: 'right-out', targetHandle: 'left-in' },
  { id: 'f-router-mem', source: 'router', target: 'memory_writer', kind: 'control', label: 'revise', sourceHandle: 'bottom-out', targetHandle: 'right-in' },
  { id: 'f-mem-store', source: 'memory_writer', target: 'research_memory', kind: 'data', sourceHandle: 'left-out', targetHandle: 'right-in' },
  { id: 'f-store-hyp', source: 'research_memory', target: 'hypothesis_generator', kind: 'control', label: 'brief', sourceHandle: 'top-out', targetHandle: 'bottom-in' },
  { id: 'f-router-best', source: 'router', target: 'best_candidate', kind: 'control', label: 'accept/stop', sourceHandle: 'bottom-out', targetHandle: 'top-in' },
  { id: 'f-best-hold', source: 'best_candidate', target: 'holdout_eval', kind: 'control', sourceHandle: 'right-out', targetHandle: 'left-in' },
  { id: 'f-hold-report', source: 'holdout_eval', target: 'evaluation_reporter', kind: 'control', sourceHandle: 'right-out', targetHandle: 'left-in' },
]

/** x step 260; rows y = 40 (main spine) / 260 (memory loop) / 480 (finalise). */
export const FRAUD_LOOP_POSITIONS: LoopGraphConfig['positions'] = {
  dataset: { x: 0, y: 40 },
  warehouse_loader: { x: 260, y: 40 },
  data_scientist: { x: 520, y: 40 },
  baseline_agent: { x: 780, y: 40 },
  hypothesis_generator: { x: 1040, y: 40 },
  ml_engineer: { x: 1300, y: 40 },
  judge: { x: 1560, y: 40 },
  router: { x: 1820, y: 40 },
  warehouse_db: { x: 260, y: 260 },
  research_memory: { x: 1040, y: 260 },
  memory_writer: { x: 1560, y: 260 },
  best_candidate: { x: 1820, y: 480 },
  holdout_eval: { x: 2080, y: 480 },
  evaluation_reporter: { x: 2340, y: 480 },
}

export const FRAUD_LOOP_CONFIG: LoopGraphConfig = {
  nodes: FRAUD_LOOP_NODES,
  edges: FRAUD_LOOP_EDGES,
  positions: FRAUD_LOOP_POSITIONS,
}

/** LangGraph node name → visual node id (1:1 here; router/memory are synthetic SSE events). */
export const FRAUD_GRAPH_NODE_TO_VISUAL: Record<string, string> = Object.fromEntries(
  FRAUD_LOOP_NODES.map((n) => [n.id, n.id]),
)

/** Expand compiled LangGraph node names into the visual ids drawn on the canvas. */
export function fraudVisualIds(nodes: string[]): Set<string> {
  const v = new Set<string>()
  for (const n of nodes) {
    v.add(n)
    if (n === 'warehouse_loader') {
      v.add('dataset')
      v.add('warehouse_db')
    }
    if (n === 'judge') v.add('router')
    if (n === 'memory_writer') v.add('research_memory')
    if (n === 'holdout_eval') v.add('best_candidate')
  }
  return v
}

/** Map declared LangGraph edges onto visual `source->target` keys. */
export function fraudVisualEdgeKeys(edges: { source: string; target: string }[]): string[] {
  const keys = new Set<string>()
  const add = (a: string, b: string) => keys.add(`${a}->${b}`)
  for (const { source, target } of edges) {
    const s = source === 'START' ? '__start__' : source
    const t = target === 'END' ? '__end__' : target
    if (s === '__start__' && t === 'warehouse_loader') {
      add('dataset', 'warehouse_loader')
      add('warehouse_db', 'warehouse_loader')
    } else if (s === 'judge' && t === 'memory_writer') {
      add('judge', 'router')
      add('router', 'memory_writer')
    } else if (s === 'memory_writer' && t === 'hypothesis_generator') {
      add('memory_writer', 'research_memory')
      add('research_memory', 'hypothesis_generator')
    } else if (s === 'judge' && t === 'holdout_eval') {
      add('judge', 'router')
      add('router', 'best_candidate')
      add('best_candidate', 'holdout_eval')
    } else if (t !== '__end__') {
      add(s, t)
    }
  }
  return Array.from(keys)
}
