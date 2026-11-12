import { Link } from 'react-router-dom'
import { ActivityBurgerButton } from './ActivityLog'
import type { SessionState } from '../types/events'

interface Props {
  state: SessionState
  onPause: () => void
  onResume: () => void
  onReset: () => void
  busy?: boolean
  activityOpen?: boolean
  onToggleActivity?: () => void
  onCreateReport?: () => void
  /** Prefer project detail when known; otherwise projects home. */
  backTo?: string
}

export function TopBar({
  state,
  onPause,
  onResume,
  onReset,
  busy,
  activityOpen = false,
  onToggleActivity,
  onCreateReport,
  backTo = '/',
}: Props) {
  const running = state.status === 'running'
  const paused = state.status === 'paused'

  return (
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line px-6 py-4">
      <div className="flex min-w-0 items-start gap-3">
        <Link
          to={backTo}
          className="mt-1 inline-flex shrink-0 items-center gap-1.5 rounded border border-line bg-panel px-3 py-2 text-sm text-paper hover:border-teal hover:text-teal"
          title="Back to projects"
        >
          <span aria-hidden className="font-mono text-base leading-none">
            ←
          </span>
          Back
        </Link>
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-teal">
            Research Control Center
          </p>
          <h1 className="font-display text-3xl font-semibold text-paper">AutoML Research Lab</h1>
          <p className="mt-1 text-sm text-mist">
            Session {state.sessionId ?? '—'}
            {state.replay
              ? ' · replay of a recorded real run'
              : state.mock
                ? ' · illustrative sample data'
                : ' · live'}
            {state.mode === 'mock' && state.scenario ? ` · scenario ${state.scenario}` : ''}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <StatusPill status={state.status} />
        {running && (
          <button
            type="button"
            disabled={busy}
            onClick={onPause}
            className="rounded border border-line bg-panel px-3 py-2 text-sm text-paper hover:border-teal"
          >
            Pause stream
          </button>
        )}
        {paused && (
          <button
            type="button"
            disabled={busy}
            onClick={onResume}
            className="rounded border border-teal/50 bg-teal/15 px-3 py-2 text-sm text-teal hover:bg-teal/25"
          >
            Resume
          </button>
        )}
        <button
          type="button"
          disabled={busy || !state.sessionId}
          onClick={onReset}
          className="rounded border border-line px-3 py-2 text-sm text-mist hover:border-danger hover:text-danger"
        >
          Reset
        </button>
        {onCreateReport && (
          <button
            type="button"
            disabled={!state.sessionId || state.experiments.length === 0}
            onClick={onCreateReport}
            className="rounded border border-teal/50 bg-teal/15 px-3 py-2 text-sm text-teal hover:bg-teal/25 disabled:cursor-not-allowed disabled:opacity-40"
            title={
              state.experiments.length === 0
                ? 'Waiting for trial events'
                : 'Summarize what worked, what failed, and the final verdict'
            }
          >
            Create report
          </button>
        )}
        {onToggleActivity && (
          <ActivityBurgerButton
            count={state.activity.length}
            open={activityOpen}
            onClick={onToggleActivity}
          />
        )}
      </div>
    </header>
  )
}

function StatusPill({ status }: { status: SessionState['status'] }) {
  const color =
    status === 'running'
      ? 'text-teal border-teal/40 bg-teal/10'
      : status === 'paused'
        ? 'text-amber border-amber/40 bg-amber/10'
        : status === 'completed'
          ? 'text-ok border-ok/40 bg-ok/10'
          : status === 'error'
            ? 'text-danger border-danger/40 bg-danger/10'
            : 'text-mist border-line bg-panel'

  return (
    <span className={`rounded border px-3 py-2 font-mono text-xs uppercase tracking-wider ${color}`}>
      {status}
    </span>
  )
}
