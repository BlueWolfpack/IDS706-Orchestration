/** Recovery + run-state teaching diagram. */

export interface RecNodeDef {
  id: string
  title: string
  role: string
  planned?: boolean
}

export interface RecEdgeDef {
  id: string
  source: string
  target: string
  label?: string
}

export const REC_NODES: RecNodeDef[] = [
  { id: 'validate', title: 'Config validator', role: 'harness validate_experiment' },
  { id: 'run', title: 'Experiment runner', role: 'harness run_experiment + timeout' },
  { id: 'repair', title: 'Error repair', role: 'up to 3 heals / experiment' },
  { id: 'fail', title: 'Trial failed', role: 'heal budget exhausted → skip' },
  { id: 'ckpt', title: 'Checkpointer', role: 'orchestrator SQLite / Postgres' },
  { id: 'policy', title: 'Policy guard', role: 'harness policy.py limits' },
  { id: 'human', title: 'Human edit', role: 'planned checkpoint interrupt', planned: true },
]

export const REC_EDGES: RecEdgeDef[] = [
  { id: 'r1', source: 'validate', target: 'run', label: 'valid' },
  { id: 'r2', source: 'run', target: 'repair', label: 'fail / timeout' },
  { id: 'r3', source: 'repair', target: 'validate', label: 'retry (≤3)' },
  { id: 'r4', source: 'run', target: 'fail', label: 'heals exhausted' },
  { id: 'r5', source: 'policy', target: 'validate', label: 'limits' },
  { id: 'r6', source: 'ckpt', target: 'run', label: 'resume' },
  { id: 'r7', source: 'human', target: 'ckpt', label: 'planned' },
]

export const REC_POSITIONS: Record<string, { x: number; y: number }> = {
  policy: { x: 40, y: 40 },
  validate: { x: 280, y: 40 },
  run: { x: 520, y: 40 },
  repair: { x: 520, y: 200 },
  fail: { x: 760, y: 40 },
  ckpt: { x: 280, y: 200 },
  human: { x: 40, y: 200 },
}
