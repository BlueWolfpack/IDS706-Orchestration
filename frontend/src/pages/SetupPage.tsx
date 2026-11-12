import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  MODEL_FAMILIES,
  createSession,
  getProject,
  listPriorDatasets,
  uploadSessionDataset,
  type PriorDataset,
  type ResearchStrategy,
  type SessionMode,
} from '../api/gateway'
import { AppNav } from '../components/AppNav'
import { MockBanner } from '../components/MockBanner'
import { guessTargetColumn, sniffCsvHeaders } from '../lib/csvHeaders'
import { SCENARIOS, type ScenarioName } from '../types/events'

type DatasetSource = 'sample' | 'upload' | 'reuse'

export function SetupPage() {
  const navigate = useNavigate()
  const { projectId } = useParams()
  const [projectName, setProjectName] = useState<string | null>(null)
  const [taskType] = useState('classification')
  const [targetColumn, setTargetColumn] = useState('churned')
  const [metric, setMetric] = useState('f1')
  const [targetScore, setTargetScore] = useState(0.7)
  const [budget, setBudget] = useState(5)
  const [mode, setMode] = useState<SessionMode>('live')
  const [scenario, setScenario] = useState<ScenarioName>('happy')
  const [researchStrategy, setResearchStrategy] =
    useState<ResearchStrategy>('model_search')
  const [fixedModel, setFixedModel] = useState<string>('random_forest')
  const [trialTimeout, setTrialTimeout] = useState(120)
  const [datasetSource, setDatasetSource] = useState<DatasetSource>('sample')
  const [datasetLabel, setDatasetLabel] = useState('churn_sample.csv')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [priorDatasets, setPriorDatasets] = useState<PriorDataset[]>([])
  const [columns, setColumns] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) {
      navigate('/advanced', { replace: true })
      return
    }
    void getProject(projectId)
      .then((p) => setProjectName(p.name))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
    void listPriorDatasets(projectId)
      .then(setPriorDatasets)
      .catch(() => setPriorDatasets([]))
  }, [projectId, navigate])

  function selectPriorDataset(filename: string) {
    if (!filename) return
    const prior = priorDatasets.find((d) => d.filename === filename)
    setDatasetSource('reuse')
    setDatasetLabel(filename)
    setUploadFile(null)
    setColumns([])
    setError(null)
    if (prior?.target_column) {
      setTargetColumn(prior.target_column)
    }
  }

  async function onPickFile(file: File | null) {
    setUploadFile(file)
    setError(null)
    if (!file) {
      setColumns([])
      return
    }
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Please upload a .csv file')
      setUploadFile(null)
      setColumns([])
      return
    }
    const text = await file.slice(0, 256_000).text()
    const headers = sniffCsvHeaders(text)
    if (headers.length < 2) {
      setError('Could not read CSV headers. Check the file uses a comma/semicolon delimiter.')
      setColumns([])
      return
    }
    setColumns(headers)
    setDatasetLabel(file.name)
    setDatasetSource('upload')
    setTargetColumn(guessTargetColumn(headers))
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'live' && datasetSource === 'upload') {
        if (!uploadFile) throw new Error('Choose a CSV file to upload')
        if (!targetColumn.trim()) throw new Error('Select the target column')
      }
      if (mode === 'live' && datasetSource === 'reuse') {
        if (!datasetLabel.trim()) throw new Error('Pick a previously used dataset')
        if (!targetColumn.trim()) throw new Error('Select the target column')
      }

      if (!projectId) throw new Error('Open this setup from a project')

      const useSample = mode !== 'live' || datasetSource === 'sample'
      const res = await createSession({
        target_column: targetColumn,
        task_type: taskType,
        metric,
        target_score: targetScore,
        experiment_budget: budget,
        mode,
        scenario: mode === 'mock' ? scenario : undefined,
        recording: mode === 'replay' ? 'real_run_churn' : undefined,
        mock: mode === 'mock',
        use_sample_dataset: useSample,
        reuse_dataset_filename:
          mode === 'live' && datasetSource === 'reuse' ? datasetLabel : undefined,
        project_id: projectId,
        dataset_filename: datasetLabel,
        research_strategy: researchStrategy,
        fixed_model_family:
          researchStrategy === 'blackbox_tuning' ? fixedModel : null,
        per_trial_timeout_seconds: trialTimeout,
      })

      if (mode === 'live' && datasetSource === 'upload' && uploadFile) {
        await uploadSessionDataset(res.session_id, uploadFile, targetColumn, taskType)
      }

      const resolvedMode = res.mode ?? mode
      const params = new URLSearchParams({
        mode: resolvedMode,
        scenario: mode === 'mock' ? scenario : resolvedMode,
        dataset: datasetLabel,
        target: targetColumn,
        metric,
        targetScore: String(targetScore),
        budget: String(budget),
        strategy: researchStrategy,
        trialTimeout: String(trialTimeout),
        mock: String(Boolean(res.mock)),
        replay: String(Boolean(res.replay || resolvedMode === 'replay')),
        project: projectId,
      })
      if (researchStrategy === 'blackbox_tuning') {
        params.set('model', fixedModel)
      }
      navigate(`/session/${res.session_id}?${params.toString()}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="lab-grid min-h-screen">
      <MockBanner visible={mode === 'mock'} />
      <AppNav />
      <main className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-3xl flex-col justify-center px-6 py-12">
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-teal">
          <Link to="/advanced" className="hover:underline">
            Projects
          </Link>
          {projectId ? (
            <>
              {' / '}
              <Link to={`/projects/${projectId}`} className="hover:underline">
                {projectName ?? projectId}
              </Link>
              {' / '}
            </>
          ) : null}
          New session
        </p>
        <h1 className="mt-2 font-display text-5xl font-semibold leading-tight text-paper sm:text-6xl">
          Start training session
        </h1>
        <p className="mt-4 max-w-xl text-base text-mist">
          Runs from scratch under this project. Upload a classification CSV or use the bundled
          churn sample — results are saved to the project history.
        </p>

        <form onSubmit={onSubmit} className="mt-10 space-y-8">
          <section>
            <h2 className="font-mono text-xs uppercase tracking-wider text-mist">0. Session mode</h2>
            <select
              className="mt-2 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
              value={mode}
              onChange={(e) => setMode(e.target.value as SessionMode)}
            >
              <option value="live">Live research (real services)</option>
              <option value="replay">Replay of a recorded real run</option>
              <option value="mock">Mock fixture (illustrative)</option>
            </select>
            <p className="mt-2 text-xs text-mist">
              {mode === 'live' &&
                'Trains via harness on your CSV or the sample; sealed holdout opens once at the end.'}
              {mode === 'replay' && 'Replays recorded metrics — labeled replay, never “live”.'}
              {mode === 'mock' && 'Fixture SSE with mock:true banner for teaching the UI.'}
            </p>
          </section>

          <section>
            <h2 className="font-mono text-xs uppercase tracking-wider text-mist">1. Dataset</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => {
                  setDatasetSource('sample')
                  setDatasetLabel('churn_sample.csv')
                  setTargetColumn('churned')
                  setUploadFile(null)
                  setColumns([])
                  setError(null)
                }}
                className={`border px-4 py-4 text-left transition ${
                  datasetSource === 'sample'
                    ? 'border-teal bg-teal/10'
                    : 'border-line bg-panel/40 hover:border-mist'
                }`}
              >
                <span className="font-medium text-paper">churn_sample.csv</span>
                <span className="mt-1 block text-sm text-mist">
                  Bundled sample · tabular, binary target
                </span>
              </button>
              <label
                className={`cursor-pointer border px-4 py-4 text-left transition ${
                  datasetSource === 'upload'
                    ? 'border-teal bg-teal/10'
                    : 'border-line bg-panel/40 hover:border-mist'
                }`}
              >
                <span className="font-medium text-paper">Upload CSV</span>
                <span className="mt-1 block text-sm text-mist">
                  Any Kaggle-style table with one target column
                </span>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="mt-3 block w-full text-xs text-mist file:mr-3 file:border file:border-line file:bg-panel file:px-2 file:py-1 file:text-paper"
                  onChange={(e) => void onPickFile(e.target.files?.[0] ?? null)}
                />
                {uploadFile && (
                  <span className="mt-2 block font-mono text-[11px] text-teal">{uploadFile.name}</span>
                )}
              </label>
            </div>
            {mode === 'live' && priorDatasets.length > 0 && (
              <label className="mt-3 block text-sm">
                <span className="text-mist">Previously used / catalog</span>
                <select
                  className={`mt-1 w-full border bg-ink-2 px-3 py-2 text-paper ${
                    datasetSource === 'reuse' ? 'border-teal' : 'border-line'
                  }`}
                  value={datasetSource === 'reuse' ? datasetLabel : ''}
                  onChange={(e) => {
                    const v = e.target.value
                    if (!v) {
                      setDatasetSource('sample')
                      setDatasetLabel('churn_sample.csv')
                      setTargetColumn('churned')
                      return
                    }
                    selectPriorDataset(v)
                  }}
                >
                  <option value="">Select a prior dataset…</option>
                  {priorDatasets.map((d) => (
                    <option key={d.filename} value={d.filename}>
                      {d.filename}
                      {d.times_used > 0
                        ? ` · used ${d.times_used}×`
                        : ' · catalog'}
                      {d.target_column ? ` · target ${d.target_column}` : ''}
                    </option>
                  ))}
                </select>
                <span className="mt-1 block text-xs text-mist">
                  Reuses a CSV already on this project or in the lab datasets folder — no re-upload.
                </span>
              </label>
            )}
            {mode === 'live' && datasetSource === 'upload' && (
              <p className="mt-2 text-xs text-mist">
                Classification only. Files larger than 20k rows are downsampled with a fixed seed.
                ID-like columns are dropped automatically.
              </p>
            )}
          </section>

          <section className="grid gap-4 sm:grid-cols-2">
            <h2 className="font-mono text-xs uppercase tracking-wider text-mist sm:col-span-2">
              2. Target column
            </h2>
            <label className="block text-sm">
              <span className="text-mist">Task type</span>
              <select
                className="mt-1 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
                value={taskType}
                disabled
              >
                <option value="classification">Classification</option>
              </select>
              <span className="mt-1 block text-[11px] text-mist">
                Regression is planned — this lab trains classifiers only.
              </span>
            </label>
            <label className="block text-sm">
              <span className="text-mist">Target column</span>
              {columns.length > 0 ? (
                <select
                  className="mt-1 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
                  value={targetColumn}
                  onChange={(e) => setTargetColumn(e.target.value)}
                  required
                >
                  {columns.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="mt-1 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
                  value={targetColumn}
                  onChange={(e) => setTargetColumn(e.target.value)}
                  required
                />
              )}
            </label>
          </section>

          <section>
            <h2 className="font-mono text-xs uppercase tracking-wider text-mist">
              3. Research strategy
            </h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setResearchStrategy('blackbox_tuning')}
                className={`border px-4 py-4 text-left transition ${
                  researchStrategy === 'blackbox_tuning'
                    ? 'border-teal bg-teal/10'
                    : 'border-line bg-panel/40 hover:border-mist'
                }`}
              >
                <span className="font-medium text-paper">Blackbox HP tuning</span>
                <span className="mt-1 block text-sm text-mist">
                  Pick one model upfront. The loop only searches hyperparameters.
                </span>
              </button>
              <button
                type="button"
                onClick={() => setResearchStrategy('model_search')}
                className={`border px-4 py-4 text-left transition ${
                  researchStrategy === 'model_search'
                    ? 'border-teal bg-teal/10'
                    : 'border-line bg-panel/40 hover:border-mist'
                }`}
              >
                <span className="font-medium text-paper">Optimal model search</span>
                <span className="mt-1 block text-sm text-mist">
                  Free to try any allowed family under the experiment budget.
                </span>
              </button>
            </div>
            {researchStrategy === 'blackbox_tuning' && (
              <label className="mt-4 block text-sm">
                <span className="text-mist">Fixed model</span>
                <select
                  className="mt-1 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
                  value={fixedModel}
                  onChange={(e) => setFixedModel(e.target.value)}
                >
                  {MODEL_FAMILIES.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="mt-4 block text-sm">
              <span className="text-mist">Train time budget per trial (seconds)</span>
              <input
                type="number"
                min={30}
                max={600}
                step={30}
                className="mt-1 w-full border border-line bg-ink-2 px-3 py-2 text-paper sm:max-w-xs"
                value={trialTimeout}
                onChange={(e) => setTrialTimeout(Number(e.target.value))}
              />
              <span className="mt-1 block text-[11px] text-mist">
                Default 120s (2 minutes). Trials that overrun are marked failed.
              </span>
            </label>
          </section>

          <section className="grid gap-4 sm:grid-cols-3">
            <h2 className="font-mono text-xs uppercase tracking-wider text-mist sm:col-span-3">
              4. Objective
            </h2>
            <label className="block text-sm">
              <span className="text-mist">Metric</span>
              <select
                className="mt-1 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
              >
                <option value="f1">F1 (binary or weighted)</option>
                <option value="accuracy">Accuracy</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-mist">Target score</span>
              <input
                type="number"
                step="0.01"
                min={0}
                max={1}
                className="mt-1 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
                value={targetScore}
                onChange={(e) => setTargetScore(Number(e.target.value))}
              />
            </label>
            <label className="block text-sm">
              <span className="text-mist">Experiment budget</span>
              <input
                type="number"
                min={1}
                max={50}
                className="mt-1 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
              />
            </label>
          </section>

          {mode === 'mock' && (
            <section>
              <h2 className="font-mono text-xs uppercase tracking-wider text-mist">
                Demo scenario (mock)
              </h2>
              <select
                className="mt-2 w-full border border-line bg-ink-2 px-3 py-2 text-paper"
                value={scenario}
                onChange={(e) => setScenario(e.target.value as ScenarioName)}
              >
                {SCENARIOS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </section>
          )}

          <section className="border border-line bg-panel/30 px-4 py-3 text-sm text-mist">
            <p className="font-mono text-[10px] uppercase tracking-wider text-teal">Fixed protocol</p>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>Train, validation and test sets are split once, with a fixed seed.</li>
              <li>Preprocessing is fitted on training data only (impute + scale / one-hot).</li>
              <li>The sealed holdout is never shown to agents. It is opened once, at the end.</li>
              <li>Every run has retry, per-trial train timeout, compute and experiment limits.</li>
              <li>
                Blackbox mode locks the model family; model search may switch families freely.
              </li>
            </ul>
          </section>

          {error && (
            <p className="border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger whitespace-pre-wrap">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={
              busy ||
              (mode === 'live' && datasetSource === 'upload' && !uploadFile) ||
              (mode === 'live' && datasetSource === 'reuse' && !datasetLabel)
            }
            className="w-full bg-teal px-4 py-3 text-center text-base font-medium text-white hover:bg-teal-dim disabled:opacity-60"
          >
            {busy ? 'Starting…' : 'Start research session'}
          </button>
        </form>
      </main>
    </div>
  )
}
