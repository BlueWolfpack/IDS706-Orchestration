/** Typed microservice architecture diagram (Stage B3, read-only). */

export type ArchNodeKind =
  | 'ui'
  | 'service'
  | 'infra'
  | 'external'
  | 'store'
  | 'boundary'

export interface ArchNodeDef {
  id: string
  title: string
  subtitle: string
  kind: ArchNodeKind
  owns?: string
  endpoints?: string[]
  callers?: string[]
  optional?: boolean
}

export interface ArchEdgeDef {
  id: string
  source: string
  target: string
  kind: 'rest' | 'events' | 'store' | 'mcp'
  label?: string
}

export const ARCH_NODES: ArchNodeDef[] = [
  {
    id: 'browser',
    title: 'Browser (web)',
    subtitle: 'React UI only',
    kind: 'ui',
    owns: 'UI state from SSE',
    callers: [],
  },
  {
    id: 'gateway',
    title: 'gateway',
    subtitle: 'Session commands + SSE fan-out',
    kind: 'service',
    owns: 'session command surface',
    endpoints: ['POST /sessions', 'pause/resume/reset', 'GET /events', 'upload proxy'],
    callers: ['browser'],
  },
  {
    id: 'orchestrator',
    title: 'orchestrator',
    subtitle: 'LangGraph + meta-supervisor',
    kind: 'service',
    owns: 'checkpointer DB',
    endpoints: ['POST /runs', 'GET /runs/{id}', 'pause/resume'],
    callers: ['gateway'],
  },
  {
    id: 'agent_service',
    title: 'agent-service',
    subtitle: 'LLM reasoning only',
    kind: 'service',
    owns: 'prompts + provider config',
    endpoints: ['POST /agents/{lead}/{subagent}/invoke'],
    callers: ['orchestrator'],
  },
  {
    id: 'harness',
    title: 'harness-service',
    subtitle: 'Deterministic execution',
    kind: 'service',
    owns: 'policy.py + tool backends',
    endpoints: ['/tools/*', 'GET /policy'],
    callers: ['orchestrator'],
  },
  {
    id: 'dataset_service',
    title: 'dataset-service',
    subtitle: 'Splits + sealed holdout',
    kind: 'service',
    owns: 'dataset files + holdout',
    endpoints: ['POST /datasets', 'profile-view', 'splits/train|validation', 'holdout/evaluate'],
    callers: ['gateway', 'harness'],
  },
  {
    id: 'memory_service',
    title: 'memory-service',
    subtitle: 'Findings / history / lessons',
    kind: 'service',
    owns: 'memory DB',
    endpoints: ['/findings', '/history', '/lessons', '/working/{agent}'],
    callers: ['orchestrator', 'agent_service'],
  },
  {
    id: 'tracking_service',
    title: 'tracking-service',
    subtitle: 'MLflow API + optional W&B SDK',
    kind: 'service',
    owns: 'tracking API state',
    endpoints: ['POST /runs', 'GET /runs/{id}', 'GET /experiments/{session}'],
    callers: ['harness', 'orchestrator'],
  },
  {
    id: 'redis',
    title: 'Redis',
    subtitle: 'Streams + job queue',
    kind: 'infra',
    owns: 'event stream',
  },
  {
    id: 'mlflow',
    title: 'MLflow',
    subtitle: 'System of record for runs',
    kind: 'infra',
  },
  {
    id: 'artifacts',
    title: 'Artifact volume',
    subtitle: 'Models / plots / reports',
    kind: 'store',
    owns: 'written only via harness',
  },
  {
    id: 'wandb_mcp',
    title: 'wandb-mcp',
    subtitle: 'Query + reports (optional)',
    kind: 'external',
    optional: true,
    endpoints: ['query_wandb_tool', 'create_wandb_report_tool'],
  },
  {
    id: 'wandb_cloud',
    title: 'W&B cloud',
    subtitle: 'Optional mirror',
    kind: 'external',
    optional: true,
  },
  {
    id: 'boundary',
    title: 'Network boundary',
    subtitle: 'LLM reasoning ≠ execution',
    kind: 'boundary',
  },
]

export const ARCH_EDGES: ArchEdgeDef[] = [
  { id: 'a1', source: 'browser', target: 'gateway', kind: 'rest' },
  { id: 'a2', source: 'gateway', target: 'orchestrator', kind: 'rest' },
  { id: 'a3', source: 'gateway', target: 'dataset_service', kind: 'rest', label: 'upload' },
  { id: 'a4', source: 'redis', target: 'gateway', kind: 'events', label: 'SSE fan-out' },
  { id: 'a5', source: 'orchestrator', target: 'agent_service', kind: 'rest' },
  { id: 'a6', source: 'orchestrator', target: 'harness', kind: 'rest' },
  { id: 'a7', source: 'orchestrator', target: 'memory_service', kind: 'rest' },
  { id: 'a8', source: 'orchestrator', target: 'tracking_service', kind: 'rest' },
  { id: 'a9', source: 'harness', target: 'dataset_service', kind: 'rest', label: 'holdout once' },
  { id: 'a10', source: 'harness', target: 'tracking_service', kind: 'rest' },
  { id: 'a11', source: 'harness', target: 'artifacts', kind: 'store' },
  { id: 'a12', source: 'tracking_service', target: 'mlflow', kind: 'store' },
  { id: 'a13', source: 'agent_service', target: 'wandb_mcp', kind: 'mcp', label: 'read-only' },
  { id: 'a14', source: 'harness', target: 'wandb_mcp', kind: 'mcp', label: 'report' },
  { id: 'a15', source: 'wandb_mcp', target: 'wandb_cloud', kind: 'rest' },
  { id: 'a16', source: 'tracking_service', target: 'wandb_cloud', kind: 'rest', label: 'SDK mirror' },
  { id: 'a17', source: 'agent_service', target: 'boundary', kind: 'rest' },
  { id: 'a18', source: 'boundary', target: 'harness', kind: 'rest' },
]

export const ARCH_POSITIONS: Record<string, { x: number; y: number }> = {
  browser: { x: 40, y: 40 },
  gateway: { x: 280, y: 40 },
  redis: { x: 520, y: 0 },
  orchestrator: { x: 280, y: 160 },
  agent_service: { x: 40, y: 300 },
  boundary: { x: 280, y: 300 },
  harness: { x: 520, y: 300 },
  dataset_service: { x: 760, y: 300 },
  memory_service: { x: 40, y: 460 },
  tracking_service: { x: 520, y: 460 },
  artifacts: { x: 760, y: 460 },
  mlflow: { x: 520, y: 600 },
  wandb_mcp: { x: 280, y: 600 },
  wandb_cloud: { x: 40, y: 600 },
}
