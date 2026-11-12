import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createProject, listProjects, type ProjectSummary } from '../api/gateway'
import { AppNav } from '../components/AppNav'

export function ProjectsPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  async function refresh() {
    setLoading(true)
    try {
      setProjects(await listProjects())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      const project = await createProject({
        name: name.trim(),
        description: description.trim(),
      })
      setName('')
      setDescription('')
      navigate(`/projects/${project.project_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="lab-grid min-h-screen">
      <AppNav />
      <main className="mx-auto w-full max-w-4xl px-6 py-12">
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-teal">Workspace</p>
        <h1 className="mt-2 font-display text-5xl font-semibold text-paper">Projects</h1>
        <p className="mt-3 max-w-2xl text-mist">
          Create a project, then run as many training sessions as you want from scratch. Each session
          keeps its own dataset, budget, and results under the project history.
        </p>

        <form
          onSubmit={onCreate}
          className="mt-10 border border-line bg-panel/50 p-5"
        >
          <h2 className="font-mono text-xs uppercase tracking-wider text-mist">New project</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
            <label className="block text-sm">
              <span className="text-mist">Name</span>
              <input
                className="mt-1 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Churn research"
                required
              />
            </label>
            <label className="block text-sm">
              <span className="text-mist">Description</span>
              <input
                className="mt-1 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional"
              />
            </label>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={busy || !name.trim()}
                className="w-full bg-teal px-4 py-2.5 text-sm font-medium text-white hover:bg-teal-dim disabled:opacity-60 sm:w-auto"
              >
                {busy ? 'Creating…' : 'Create'}
              </button>
            </div>
          </div>
        </form>

        {error && (
          <p className="mt-4 border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}

        <section className="mt-10">
          <div className="mb-3 flex items-baseline justify-between gap-2">
            <h2 className="font-display text-2xl text-paper">Your projects</h2>
            <button
              type="button"
              onClick={() => void refresh()}
              className="font-mono text-[11px] uppercase tracking-wider text-mist hover:text-teal"
            >
              Refresh
            </button>
          </div>
          {loading ? (
            <p className="text-sm text-mist">Loading…</p>
          ) : projects.length === 0 ? (
            <p className="rounded border border-dashed border-line px-4 py-10 text-center text-sm text-mist">
              No projects yet. Create one to start tracking training sessions.
            </p>
          ) : (
            <ul className="space-y-3">
              {projects.map((p) => (
                <li key={p.project_id}>
                  <Link
                    to={`/projects/${p.project_id}`}
                    className="block border border-line bg-panel/60 px-4 py-4 hover:border-teal"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <h3 className="text-lg font-medium text-paper">{p.name}</h3>
                      <span className="font-mono text-[11px] text-mist">
                        {p.session_count} session{p.session_count === 1 ? '' : 's'}
                      </span>
                    </div>
                    {p.description && <p className="mt-1 text-sm text-mist">{p.description}</p>}
                    <p className="mt-2 font-mono text-[11px] text-mist">
                      Updated {new Date(p.updated_at).toLocaleString()}
                      {p.best_val_score != null ? ` · best val ${p.best_val_score.toFixed(2)}` : ''}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  )
}
