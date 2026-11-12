import type { AgentCycleOutput, ExperimentEntry } from '../types/events'

export type SimpleLoopAgentId =
  | 'data_scientist'
  | 'hypothesis_generator'
  | 'ml_engineer'

export const SIMPLE_LOOP_AGENT_META: Record<
  SimpleLoopAgentId,
  { title: string; role: string }
> = {
  data_scientist: {
    title: 'Data Scientist',
    role: 'Profile + leakage',
  },
  hypothesis_generator: {
    title: 'Hypothesis Generator',
    role: 'Conceptual next step',
  },
  ml_engineer: {
    title: 'ML Engineer',
    role: 'HPT config + train',
  },
}

export function agentOutputFromStep(step: Record<string, unknown> | undefined): AgentCycleOutput {
  if (!step) return {}
  const output =
    step.output ??
    step.hypothesis ??
    step.spec ??
    step.profile ??
    (step.verdict ? { verdict: step.verdict } : undefined)
  return {
    note: typeof step.note === 'string' ? step.note : undefined,
    used_llm: typeof step.used_llm === 'boolean' ? step.used_llm : undefined,
    model: (step.model as string | null | undefined) ?? undefined,
    status: typeof step.status === 'string' ? step.status : undefined,
    output,
  }
}

export function withAgentOutput(
  exp: ExperimentEntry,
  agent: SimpleLoopAgentId,
  payload: AgentCycleOutput,
): ExperimentEntry {
  return {
    ...exp,
    agentOutputs: {
      ...(exp.agentOutputs ?? {}),
      [agent]: payload,
    },
  }
}

export function upsertExperiment(
  list: ExperimentEntry[],
  entry: ExperimentEntry,
): ExperimentEntry[] {
  const i = list.findIndex((e) => e.experimentId === entry.experimentId)
  if (i < 0) return [...list, entry]
  const next = [...list]
  next[i] = {
    ...next[i],
    ...entry,
    agentOutputs: {
      ...(next[i].agentOutputs ?? {}),
      ...(entry.agentOutputs ?? {}),
    },
    trainMetrics: entry.trainMetrics ?? next[i].trainMetrics,
    validationMetrics: entry.validationMetrics ?? next[i].validationMetrics,
  }
  return next
}

/** Rebuild timeline experiments from a persisted solution-loop `result.steps` trail. */
export function experimentsFromRunSteps(
  steps: Record<string, unknown>[] | undefined,
): ExperimentEntry[] {
  if (!Array.isArray(steps) || steps.length === 0) return []

  let ds: AgentCycleOutput | undefined
  let pendingHyp: AgentCycleOutput | undefined
  const out: ExperimentEntry[] = []
  let cycle = 0

  for (const step of steps) {
    const node = String(step.node || '')
    if (node === 'data_scientist') {
      ds = agentOutputFromStep(step)
      continue
    }
    if (node === 'hypothesis_generator') {
      pendingHyp = agentOutputFromStep(step)
      continue
    }
    if (node === 'ml_engineer') {
      cycle += 1
      const expId = String(step.experiment_id || `exp-${cycle}`)
      const metrics = (step.validation_metrics as Record<string, number> | undefined) ?? {}
      const f1 = typeof step.f1 === 'number' ? step.f1 : metrics.f1
      const failed = step.status === 'failed' || step.status === 'error'
      let entry: ExperimentEntry = {
        experimentId: expId,
        modelFamily: typeof step.model_family === 'string' ? step.model_family : undefined,
        status: failed ? 'failed' : 'completed',
        trainMetrics: {},
        validationMetrics: {
          ...metrics,
          ...(typeof f1 === 'number' ? { f1 } : {}),
        },
        durationSeconds:
          typeof step.duration_seconds === 'number' ? step.duration_seconds : undefined,
        retryCount: step.repaired ? 1 : 0,
        note: typeof step.note === 'string' ? step.note : undefined,
        agentOutputs: {},
      }
      if (ds) entry = withAgentOutput(entry, 'data_scientist', ds)
      if (pendingHyp) entry = withAgentOutput(entry, 'hypothesis_generator', pendingHyp)
      entry = withAgentOutput(entry, 'ml_engineer', agentOutputFromStep(step))
      out.push(entry)
      pendingHyp = undefined
      continue
    }
    if (node === 'judge' && out.length > 0) {
      const verdict = step.verdict as
        | { action?: string; observation?: string; next_action?: string }
        | undefined
      const last = out[out.length - 1]
      out[out.length - 1] = {
        ...last,
        verdictAction: verdict?.action,
        observation: verdict?.observation,
        nextAction: verdict?.next_action || verdict?.action,
      }
    }
  }
  return out
}
