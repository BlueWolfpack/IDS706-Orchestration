/** Agent orchestration overview (static teaching diagram). */

export interface OrchNodeDef {
  id: string
  title: string
  role: string
  planned?: boolean
}

export interface OrchEdgeDef {
  id: string
  source: string
  target: string
  label?: string
  planned?: boolean
}

export const ORCH_NODES: OrchNodeDef[] = [
  { id: 'sup', title: 'Meta-supervisor', role: 'Deterministic router' },
  { id: 'ds', title: 'Data Scientist', role: 'profiler · leakage · features' },
  { id: 'hg', title: 'Hypothesis Generator', role: 'memory · draft · novelty' },
  { id: 'ml', title: 'ML Engineer', role: 'validate · run · repair' },
  { id: 'judge', title: 'Judge', role: 'metrics · overfit · review' },
  { id: 'pa', title: 'Parallel A', role: 'planned fan-out', planned: true },
  { id: 'pb', title: 'Parallel B', role: 'planned fan-out', planned: true },
  { id: 'pc', title: 'Parallel C', role: 'planned fan-out', planned: true },
  { id: 'fan', title: 'Fan-in', role: 'planned merge', planned: true },
]

export const ORCH_EDGES: OrchEdgeDef[] = [
  { id: 'o1', source: 'sup', target: 'ds' },
  { id: 'o2', source: 'ds', target: 'hg' },
  { id: 'o3', source: 'hg', target: 'ml' },
  { id: 'o4', source: 'ml', target: 'judge' },
  { id: 'o5', source: 'judge', target: 'hg', label: 'new hypothesis' },
  { id: 'o6', source: 'judge', target: 'sup', label: 'accept / stop' },
  { id: 'o7', source: 'hg', target: 'pa', planned: true },
  { id: 'o8', source: 'hg', target: 'pb', planned: true },
  { id: 'o9', source: 'hg', target: 'pc', planned: true },
  { id: 'o10', source: 'pa', target: 'fan', planned: true },
  { id: 'o11', source: 'pb', target: 'fan', planned: true },
  { id: 'o12', source: 'pc', target: 'fan', planned: true },
  { id: 'o13', source: 'fan', target: 'judge', planned: true },
]

export const ORCH_POSITIONS: Record<string, { x: number; y: number }> = {
  sup: { x: 360, y: 0 },
  ds: { x: 40, y: 120 },
  hg: { x: 280, y: 120 },
  ml: { x: 520, y: 120 },
  judge: { x: 760, y: 120 },
  pa: { x: 160, y: 300 },
  pb: { x: 360, y: 300 },
  pc: { x: 560, y: 300 },
  fan: { x: 360, y: 420 },
}
