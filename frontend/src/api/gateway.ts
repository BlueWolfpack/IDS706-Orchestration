/** Browser talks to the gateway only (proxied as /api). */

const BASE = '/api'

export type SessionMode = 'live' | 'mock' | 'replay'
export type ResearchStrategy = 'blackbox_tuning' | 'model_search'

export const MODEL_FAMILIES = [
  { id: 'logistic_regression', label: 'Logistic regression' },
  { id: 'random_forest', label: 'Random forest' },
  { id: 'hist_gradient_boosting', label: 'Hist gradient boosting' },
  { id: 'xgboost', label: 'XGBoost-style (HistGB stand-in)' },
] as const

export interface CreateSessionBody {
  target_column: string
  task_type?: string
  metric?: string
  target_score?: number
  experiment_budget?: number
  scenario?: string
  mode?: SessionMode
  recording?: string
  mock?: boolean
  /** Live: attach bundled churn sample. Set false when uploading a custom CSV. */
  use_sample_dataset?: boolean
  /** Live: reuse a CSV already under the gateway datasets catalog / prior uploads. */
  reuse_dataset_filename?: string
  project_id?: string
  dataset_filename?: string
  research_strategy?: ResearchStrategy
  fixed_model_family?: string | null
  per_trial_timeout_seconds?: number
}

export interface PriorDataset {
  filename: string
  target_column: string | null
  times_used: number
  last_used_at: string | null
  source: 'project_history' | 'catalog'
}

export interface CreateSessionResponse {
  session_id: string
  status: string
  mock: boolean
  mode?: SessionMode
  replay?: boolean
  project_id?: string | null
}

export interface ProjectSummary {
  project_id: string
  name: string
  description: string
  created_at: string
  updated_at: string
  session_count: number
  last_session_at: string | null
  best_val_score: number | null
}

export interface TrainingSessionRecord {
  session_id: string
  project_id: string
  status: string
  mode: SessionMode
  mock: boolean
  replay: boolean
  dataset_filename: string | null
  dataset_id: string | null
  target_column: string
  task_type: string
  metric: string
  target_score: number
  experiment_budget: number
  experiments_used: number
  best_val_score: number | null
  holdout_score: number | null
  stop_reason: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
}

export interface ProjectDetail extends ProjectSummary {
  sessions: TrainingSessionRecord[]
}

export interface UploadDatasetResponse {
  session_id: string
  dataset_id: string
  filename?: string
  n_rows?: number
  n_columns?: number
  target_column?: string
  ingest_notes?: Record<string, unknown>
  mock?: boolean
  note?: string
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || res.statusText)
  }
  return res.json() as Promise<T>
}

export async function createSession(body: CreateSessionBody): Promise<CreateSessionResponse> {
  return json(
    await fetch(`${BASE}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

export async function listProjects(): Promise<ProjectSummary[]> {
  return json(await fetch(`${BASE}/projects`))
}

export async function createProject(body: {
  name: string
  description?: string
}): Promise<ProjectSummary> {
  return json(
    await fetch(`${BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  return json(await fetch(`${BASE}/projects/${projectId}`))
}

export async function listPriorDatasets(projectId: string): Promise<PriorDataset[]> {
  return json(await fetch(`${BASE}/projects/${projectId}/prior-datasets`))
}

export async function getSessionRecord(sessionId: string): Promise<TrainingSessionRecord> {
  return json(await fetch(`${BASE}/sessions/${sessionId}/record`))
}

export async function patchSessionRecord(
  sessionId: string,
  body: {
    status?: string
    best_val_score?: number | null
    holdout_score?: number | null
    stop_reason?: string | null
    experiments_used?: number
  },
): Promise<TrainingSessionRecord> {
  return json(
    await fetch(`${BASE}/sessions/${sessionId}/record`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

export async function fetchServicesHealth(): Promise<{
  services: Record<string, string>
  note?: string
}> {
  return json(await fetch(`${BASE}/services/health`))
}

export async function uploadSessionDataset(
  sessionId: string,
  file: File,
  targetColumn: string,
  taskType = 'classification',
): Promise<UploadDatasetResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('target_column', targetColumn)
  form.append('task_type', taskType)
  return json(
    await fetch(`${BASE}/sessions/${sessionId}/datasets`, {
      method: 'POST',
      body: form,
    }),
  )
}

export interface LoopDataset {
  filename: string
  path?: string
  columns: string[]
  bytes?: number
}

export interface LoopModel {
  id: string
  name: string
  free: boolean
  provider?: 'cursor' | 'openrouter' | string
  available?: boolean
}

export async function listSolutionLoopModels(): Promise<{
  default: string
  models: LoopModel[]
  key_configured: boolean
  cursor_configured?: boolean
}> {
  return json(await fetch(`${BASE}/solution-loop/models`))
}

export async function listSolutionLoopDatasets(): Promise<LoopDataset[]> {
  const body = await json<{ datasets: LoopDataset[] }>(
    await fetch(`${BASE}/solution-loop/datasets`),
  )
  return body.datasets ?? []
}

export async function uploadSolutionLoopDataset(file: File): Promise<LoopDataset> {
  const form = new FormData()
  form.append('file', file)
  return json(await fetch(`${BASE}/solution-loop/dataset`, { method: 'POST', body: form }))
}

export interface LoopRunResult {
  cycles?: number
  best_val_f1?: number
  holdout_metrics?: { f1?: number; accuracy?: number; n_holdout?: number }
  verdict?: { action?: string; observation?: string; next_action?: string }
  stop_reason?: string
  best_spec?: Record<string, unknown>
  profile?: Record<string, unknown>
  memory?: Record<string, unknown>
  model?: string
  steps?: Record<string, unknown>[]
  dataset_path?: string
  target_column?: string
}

export interface LoopRunRecord {
  run_id: string
  created_at: string
  status: 'completed' | 'error' | string
  dataset: string | null
  target_column: string | null
  target_score: number | null
  max_cycles: number | null
  cycles: number | null
  best_val_f1: number | null
  holdout_f1: number | null
  stop_reason: string | null
  model: string | null
  verdict_action: string | null
  error: string | null
  /** Full finalize payload when the run finished successfully. */
  result?: LoopRunResult | null
}

export async function listSolutionLoopRuns(limit = 50): Promise<LoopRunRecord[]> {
  const body = await json<{ runs: LoopRunRecord[] }>(
    await fetch(`${BASE}/solution-loop/runs?limit=${limit}`),
  )
  return body.runs ?? []
}

export async function getSolutionLoopRun(runId: string): Promise<LoopRunRecord> {
  return json(await fetch(`${BASE}/solution-loop/runs/${encodeURIComponent(runId)}`))
}

export interface LabLoopStatus {
  root: string
  available: boolean
  ready: boolean
  nodes: string[]
  /** Declared g.add_edge / conditional pairs from student build_graph. */
  edges: { source: string; target: string }[]
  missing_nodes: string[]
  error: string | null
}

export async function getLabLoopStatus(): Promise<LabLoopStatus> {
  return json(await fetch(`${BASE}/lab-loop/status`))
}

export async function pauseSession(sessionId: string) {
  return json(await fetch(`${BASE}/sessions/${sessionId}/pause`, { method: 'POST' }))
}

export async function resumeSession(sessionId: string) {
  return json(await fetch(`${BASE}/sessions/${sessionId}/resume`, { method: 'POST' }))
}

export async function resetSession(sessionId: string) {
  return json(await fetch(`${BASE}/sessions/${sessionId}/reset`, { method: 'POST' }))
}

export function eventsUrl(sessionId: string): string {
  return `${BASE}/sessions/${sessionId}/events`
}
