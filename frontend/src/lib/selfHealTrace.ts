import type { EventEnvelope, ExperimentEntry } from '../types/events'

export const DEFAULT_SELF_HEAL_BUDGET = 3

export type SelfHealAttemptStatus = 'pending' | 'running' | 'healed' | 'failed' | 'exhausted'

export interface SelfHealAttempt {
  attempt: number
  status: SelfHealAttemptStatus
  trigger?: string
  error?: string
  note?: string
  repaired?: boolean
  startedAt?: string
  completedAt?: string
}

export interface ExperimentSelfHeal {
  experimentId: string
  modelFamily?: string
  budget: number
  used: number
  attempts: SelfHealAttempt[]
}

function num(v: unknown, fallback: number): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback
}

function subagentOf(e: EventEnvelope): string | null {
  if (typeof e.payload.subagent === 'string') return e.payload.subagent
  if (e.source_agent) return e.source_agent
  return null
}

/** Build per-experiment self-heal loops from SSE (activity + error_repair / trial events). */
export function buildSelfHealTraces(
  events: EventEnvelope[],
  experiments: ExperimentEntry[],
  defaultBudget = DEFAULT_SELF_HEAL_BUDGET,
): ExperimentSelfHeal[] {
  const byExp = new Map<string, ExperimentSelfHeal>()

  const ensure = (id: string, budget = defaultBudget): ExperimentSelfHeal => {
    let row = byExp.get(id)
    if (!row) {
      const exp = experiments.find((e) => e.experimentId === id)
      row = {
        experimentId: id,
        modelFamily: exp?.modelFamily,
        budget,
        used: 0,
        attempts: [],
      }
      byExp.set(id, row)
    }
    if (budget > row.budget) row.budget = budget
    return row
  }

  const upsertAttempt = (
    row: ExperimentSelfHeal,
    attempt: number,
    patch: Partial<SelfHealAttempt>,
  ) => {
    let a = row.attempts.find((x) => x.attempt === attempt)
    if (!a) {
      a = { attempt, status: 'pending' }
      row.attempts.push(a)
      row.attempts.sort((x, y) => x.attempt - y.attempt)
    }
    const terminal = a.status === 'healed' || a.status === 'failed' || a.status === 'exhausted'
    for (const [key, value] of Object.entries(patch) as [keyof SelfHealAttempt, unknown][]) {
      if (value === undefined) continue
      if (key === 'status' && terminal && value === 'running') continue
      // Keep earliest start timestamp.
      if (key === 'startedAt' && a.startedAt) continue
      ;(a as Record<string, unknown>)[key] = value
    }
    row.used = Math.max(row.used, attempt, row.attempts.length)
  }

  for (const event of events) {
    const p = event.payload
    const expId =
      typeof p.experiment_id === 'string' && p.experiment_id && p.experiment_id !== '__setup__'
        ? String(p.experiment_id)
        : null
    const budget = num(p.self_heal_budget, defaultBudget)
    const attempt = num(p.self_heal_attempt, num(p.retry_count, 0))
    const isHealActivity = p.kind === 'self_heal'
    const sub = subagentOf(event)

    if (isHealActivity && expId && attempt > 0) {
      const row = ensure(expId, budget)
      const exhausted = p.exhausted === true
      const repaired = typeof p.repaired === 'boolean' ? p.repaired : undefined
      let status: SelfHealAttemptStatus = 'running'
      if (exhausted) status = 'exhausted'
      else if (repaired === true) status = 'healed'
      else if (repaired === false) status = 'failed'
      upsertAttempt(row, attempt, {
        status,
        trigger: typeof p.trigger === 'string' ? p.trigger : undefined,
        error: typeof p.error === 'string' ? p.error : undefined,
        note: typeof p.note === 'string' ? p.note : undefined,
        repaired,
        startedAt: aStarted(row, attempt) ?? event.timestamp,
        completedAt: repaired != null || exhausted ? event.timestamp : undefined,
      })
      continue
    }

    if (!expId || attempt <= 0) continue

    if (sub === 'error_repair') {
      const row = ensure(expId, budget)
      if (event.type === 'agent_started') {
        upsertAttempt(row, attempt, {
          status: 'running',
          trigger: typeof p.trigger === 'string' ? p.trigger : undefined,
          startedAt: event.timestamp,
        })
      }
      if (event.type === 'agent_completed') {
        const out =
          p.output && typeof p.output === 'object'
            ? (p.output as Record<string, unknown>)
            : p.summary && typeof p.summary === 'object'
              ? (p.summary as Record<string, unknown>)
              : {}
        const repaired = out.repaired === true || p.repaired === true
        upsertAttempt(row, attempt, {
          status: repaired ? 'healed' : 'failed',
          repaired,
          note:
            typeof out.note === 'string'
              ? out.note
              : typeof p.note === 'string'
                ? p.note
                : undefined,
          completedAt: event.timestamp,
          startedAt: aStarted(row, attempt) ?? event.timestamp,
        })
      }
    }
  }

  // Ensure every experiment appears (empty slots = unused heal budget).
  for (const exp of experiments) {
    ensure(exp.experimentId, defaultBudget)
    const row = byExp.get(exp.experimentId)!
    if (!row.modelFamily && exp.modelFamily) row.modelFamily = exp.modelFamily
    if (typeof exp.retryCount === 'number') {
      row.used = Math.max(row.used, exp.retryCount)
    }
  }

  return [...byExp.values()].sort((a, b) => {
    const ia = experiments.findIndex((e) => e.experimentId === a.experimentId)
    const ib = experiments.findIndex((e) => e.experimentId === b.experimentId)
    return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib)
  })
}

function aStarted(row: ExperimentSelfHeal, attempt: number): string | undefined {
  return row.attempts.find((x) => x.attempt === attempt)?.startedAt
}
