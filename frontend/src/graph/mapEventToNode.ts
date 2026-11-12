/** Map SSE source_agent / payload fields onto graph node ids. */

const ALIASES: Record<string, string> = {
  meta_supervisor: 'meta_supervisor',
  'meta-supervisor': 'meta_supervisor',
  data_scientist: 'data_scientist',
  data_profiler: 'data_profiler',
  leakage_auditor: 'leakage_auditor',
  feature_analyst: 'feature_analyst',
  hypothesis_generator: 'hypothesis_generator',
  memory_retriever: 'memory_retriever',
  hypothesis_drafter: 'hypothesis_drafter',
  novelty_checker: 'novelty_checker',
  ml_engineer: 'ml_engineer',
  config_validator: 'config_validator',
  experiment_runner: 'experiment_runner',
  error_repair: 'error_repair',
  judge: 'judge',
  metric_analyst: 'metric_analyst',
  overfitting_checker: 'overfitting_checker',
  independent_reviewer: 'independent_reviewer',
}

export function resolveNodeId(
  sourceAgent: string | null | undefined,
  payload?: Record<string, unknown>,
): string | null {
  const fromPayload =
    (typeof payload?.subagent === 'string' && payload.subagent) ||
    (typeof payload?.lead === 'string' && payload.lead) ||
    null
  const raw = (sourceAgent || fromPayload || '').toLowerCase().replace(/\s+/g, '_')
  if (!raw) return null
  if (ALIASES[raw]) return ALIASES[raw]
  // Fuzzy: strip punctuation
  const key = raw.replace(/-/g, '_')
  return ALIASES[key] ?? null
}
