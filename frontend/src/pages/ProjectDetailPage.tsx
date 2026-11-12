import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getProject, type ProjectDetail } from '../api/gateway'
import { AppNav } from '../components/AppNav'

export function ProjectDetailPage() {
  const { projectId = '' } = useParams()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      setProject(await getProject(projectId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setProject(null)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => void refresh(), 8000)
    return () => window.clearInterval(id)
  }, [refresh])

  return (
    <div className="lab-grid min-h-screen">
      <AppNav />
      <main className="mx-auto w-full max-w-4xl px-6 py-12">
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-teal">
          <Link to="/advanced" className="hover:underline">
            Projects
          </Link>
          {' / '}
          {projectId}
        </p>

        {loading && !project ? (
          <p className="mt-6 text-sm text-mist">Loading project…</p>
        ) : error && !project ? (
          <p className="mt-6 border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        ) : project ? (
          <>
            <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="font-display text-5xl font-semibold text-paper">{project.name}</h1>
                {project.description && (
                  <p className="mt-2 max-w-2xl text-mist">{project.description}</p>
                )}
                <p className="mt-3 font-mono text-xs text-mist">
                  {project.session_count} training session
                  {project.session_count === 1 ? '' : 's'}
                  {project.best_val_score != null
                    ? ` · best val F1 ${project.best_val_score.toFixed(2)}`
                    : ''}
                </p>
              </div>
              <Link
                to={`/projects/${project.project_id}/new`}
                className="bg-teal px-4 py-3 text-sm font-medium text-white hover:bg-teal-dim"
              >
                New training session
              </Link>
            </div>

            <section className="mt-10">
              <div className="mb-3 flex items-baseline justify-between">
                <h2 className="font-display text-2xl text-paper">Session history</h2>
                <button
                  type="button"
                  onClick={() => void refresh()}
                  className="font-mono text-[11px] uppercase tracking-wider text-mist hover:text-teal"
                >
                  Refresh
                </button>
              </div>

              {project.sessions.length === 0 ? (
                <p className="rounded border border-dashed border-line px-4 py-10 text-center text-sm text-mist">
                  No sessions yet. Start one from scratch — each run is tracked here.
                </p>
              ) : (
                <ul className="space-y-3">
                  {project.sessions.map((s) => (
                    <li key={s.session_id} className="border border-line bg-panel/60 px-4 py-4">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <Link
                          to={`/session/${s.session_id}?mode=${s.mode}&dataset=${encodeURIComponent(s.dataset_filename ?? '')}&target=${encodeURIComponent(s.target_column)}&metric=${s.metric}&targetScore=${s.target_score}&budget=${s.experiment_budget}&mock=${s.mock}&replay=${s.replay}&project=${s.project_id}`}
                          className="font-mono text-sm text-teal hover:underline"
                        >
                          {s.session_id}
                        </Link>
                        <StatusPill status={s.status} />
                      </div>
                      <p className="mt-2 text-sm text-paper">
                        {s.dataset_filename ?? 'dataset'} · target{' '}
                        <span className="font-mono">{s.target_column}</span> · {s.mode}
                      </p>
                      <dl className="mt-3 grid grid-cols-2 gap-2 font-mono text-[11px] text-mist sm:grid-cols-4">
                        <div>
                          <dt>Budget used</dt>
                          <dd className="text-paper">
                            {s.experiments_used}/{s.experiment_budget}
                          </dd>
                        </div>
                        <div>
                          <dt>Best val</dt>
                          <dd className="text-paper">
                            {s.best_val_score != null ? s.best_val_score.toFixed(3) : '—'}
                          </dd>
                        </div>
                        <div>
                          <dt>Holdout</dt>
                          <dd className="text-paper">
                            {s.holdout_score != null ? s.holdout_score.toFixed(3) : 'sealed'}
                          </dd>
                        </div>
                        <div>
                          <dt>Started</dt>
                          <dd className="text-paper">{new Date(s.created_at).toLocaleString()}</dd>
                        </div>
                      </dl>
                      {s.stop_reason && (
                        <p className="mt-2 text-xs text-mist">Stop: {s.stop_reason}</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        ) : null}
      </main>
    </div>
  )
}

function StatusPill({ status }: { status: string }) {
  const color =
    status === 'completed'
      ? 'text-teal border-teal/40 bg-teal/10'
      : status === 'running' || status === 'created'
        ? 'text-amber border-amber/40 bg-amber/10'
        : status === 'failed'
          ? 'text-danger border-danger/40 bg-danger/10'
          : 'text-mist border-line bg-panel'
  return (
    <span className={`rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-wider ${color}`}>
      {status}
    </span>
  )
}
