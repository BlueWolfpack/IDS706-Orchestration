import type { ExperimentEntry, SessionState } from '../types/events'

export interface SessionReport {
  generatedAt: string
  sessionId: string
  dataset: string
  targetColumn: string
  metric: string
  targetScore: number
  budgetUsed: string
  whatWorked: string[]
  whatDidnt: string[]
  finalVerdict: {
    headline: string
    detail: string
    bestValScore: number | null
    holdoutScore: number | null
    stopReason: string | null
    bestExperimentId: string | null
    bestModelFamily: string | null
    targetMet: boolean
  }
}

function f1Of(e: ExperimentEntry): number | null {
  const v = e.validationMetrics.f1
  return typeof v === 'number' ? v : null
}

function label(e: ExperimentEntry): string {
  return e.modelFamily ?? e.experimentId
}

/** Build a teaching-facing session report from live Control Center state. */
export function buildSessionReport(state: SessionState): SessionReport {
  const experiments = Array.isArray(state.experiments) ? state.experiments : []
  const scored = experiments
    .map((e) => ({ e, f1: f1Of(e) }))
    .filter((x): x is { e: ExperimentEntry; f1: number } => x.f1 != null)
    .sort((a, b) => b.f1 - a.f1)

  const completed = experiments.filter((e) => e.status === 'completed')
  const failed = experiments.filter((e) => e.status === 'failed')
  const healed = experiments.filter((e) => (e.retryCount ?? 0) > 0)
  const blocked = failed.filter((e) =>
    /duplicate/i.test(e.note ?? e.observation ?? ''),
  )
  const hardFailed = failed.filter((e) => !blocked.includes(e))

  const best = scored[0] ?? null
  const worst = scored.length ? scored[scored.length - 1] : null
  const targetMet =
    state.bestValScore != null && state.bestValScore >= state.targetScore

  const whatWorked: string[] = []
  if (best) {
    whatWorked.push(
      `Best validation ${state.metric.toUpperCase()} ${best.f1.toFixed(3)} from ${label(best.e)} (${best.e.experimentId}).`,
    )
  }
  if (state.holdoutScore != null) {
    whatWorked.push(
      `Sealed holdout ${state.metric.toUpperCase()} ${state.holdoutScore.toFixed(3)} on the best model.`,
    )
  }
  const accepted = experiments.filter((e) => e.verdictAction === 'accept')
  if (accepted.length) {
    whatWorked.push(
      `Judge accepted ${accepted.length} trial(s): ${accepted.map(label).join(', ')}.`,
    )
  }
  const improved = scored.filter((s) => s.f1 >= state.targetScore * 0.9)
  if (improved.length && !targetMet) {
    whatWorked.push(
      `${improved.length} trial(s) came within 10% of the ${state.targetScore.toFixed(2)} target.`,
    )
  }
  if (healed.some((e) => e.status === 'completed')) {
    const n = healed.filter((e) => e.status === 'completed').length
    whatWorked.push(`Self-heal recovered ${n} trial(s) after a repair retry.`)
  }
  if (completed.length && !whatWorked.length) {
    whatWorked.push(`${completed.length} trial(s) completed with validation metrics.`)
  }
  if (!whatWorked.length) {
    whatWorked.push('No successful validation scores recorded in this session.')
  }

  const whatDidnt: string[] = []
  if (!targetMet) {
    whatDidnt.push(
      `Target ${state.metric.toUpperCase()} ${state.targetScore.toFixed(2)} was not reached` +
        (state.bestValScore != null
          ? ` (best ${state.bestValScore.toFixed(3)}).`
          : '.'),
    )
  }
  if (hardFailed.length) {
    for (const e of hardFailed.slice(0, 5)) {
      whatDidnt.push(
        `${label(e)} failed${e.note ? `: ${e.note}` : e.observation ? `: ${e.observation}` : '.'}`,
      )
    }
    if (hardFailed.length > 5) {
      whatDidnt.push(`…and ${hardFailed.length - 5} more hard failure(s).`)
    }
  }
  if (blocked.length) {
    whatDidnt.push(
      `${blocked.length} proposal(s) blocked as duplicates by the novelty checker.`,
    )
  }
  if (worst && best && worst.f1 < best.f1 * 0.5) {
    whatDidnt.push(
      `Large performance gap: worst scored trial was ${label(worst.e)} at ${worst.f1.toFixed(3)}.`,
    )
  }
  const rejected = experiments.filter((e) => e.verdictAction === 'reject')
  if (rejected.length) {
    whatDidnt.push(
      `Judge rejected ${rejected.length} trial(s): ${rejected.map(label).join(', ')}.`,
    )
  }
  if (!whatDidnt.length) {
    whatDidnt.push('No major failures recorded; session met its stop condition cleanly.')
  }

  let headline: string
  let detail: string
  if (state.status === 'error') {
    headline = 'Session ended in error'
    detail = state.error || state.stopReason || 'An unexpected error stopped the run.'
  } else if (targetMet) {
    headline = 'Target met — research stop'
    detail = `Validation ${state.metric.toUpperCase()} reached ${state.bestValScore?.toFixed(3)} against target ${state.targetScore.toFixed(2)}. Stop reason: ${state.stopReason ?? 'accept'}.`
  } else if (state.experimentsUsed >= state.experimentBudget) {
    headline = 'Budget exhausted without hitting target'
    detail = `Used ${state.experimentsUsed}/${state.experimentBudget} experiments. Best validation ${state.metric.toUpperCase()} ${state.bestValScore?.toFixed(3) ?? 'n/a'}; holdout ${state.holdoutScore?.toFixed(3) ?? 'sealed'}.`
  } else {
    headline = 'Session finalized'
    detail = `Stop reason: ${state.stopReason ?? state.status}. Best validation ${state.metric.toUpperCase()} ${state.bestValScore?.toFixed(3) ?? 'n/a'}.`
  }

  return {
    generatedAt: new Date().toISOString(),
    sessionId: state.sessionId ?? 'unknown',
    dataset: state.dataset,
    targetColumn: state.targetColumn,
    metric: state.metric,
    targetScore: state.targetScore,
    budgetUsed: `${state.experimentsUsed}/${state.experimentBudget}`,
    whatWorked,
    whatDidnt,
    finalVerdict: {
      headline,
      detail,
      bestValScore: state.bestValScore,
      holdoutScore: state.holdoutScore,
      stopReason: state.stopReason,
      bestExperimentId: best?.e.experimentId ?? null,
      bestModelFamily: best ? label(best.e) : null,
      targetMet,
    },
  }
}

export function reportToMarkdown(report: SessionReport): string {
  const v = report.finalVerdict
  const lines = [
    `# Session report — ${report.sessionId}`,
    '',
    `_Generated ${report.generatedAt}_`,
    '',
    `Dataset: **${report.dataset}** · Target column: **${report.targetColumn}** · Metric: **${report.metric}** · Target score: **${report.targetScore.toFixed(2)}** · Budget used: **${report.budgetUsed}**`,
    '',
    '## What worked',
    ...report.whatWorked.map((x) => `- ${x}`),
    '',
    "## What didn't work",
    ...report.whatDidnt.map((x) => `- ${x}`),
    '',
    '## Final verdict',
    '',
    `**${v.headline}**`,
    '',
    v.detail,
    '',
    `| | |`,
    `|---|---|`,
    `| Best val | ${v.bestValScore != null ? v.bestValScore.toFixed(3) : '—'} |`,
    `| Holdout | ${v.holdoutScore != null ? v.holdoutScore.toFixed(3) : '—'} |`,
    `| Best model | ${v.bestModelFamily ?? '—'} ${v.bestExperimentId ? `(${v.bestExperimentId})` : ''} |`,
    `| Target met | ${v.targetMet ? 'yes' : 'no'} |`,
    `| Stop reason | ${v.stopReason ?? '—'} |`,
    '',
  ]
  return lines.join('\n')
}
