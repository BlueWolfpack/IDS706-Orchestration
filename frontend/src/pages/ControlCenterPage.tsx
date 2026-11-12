import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  fetchServicesHealth,
  patchSessionRecord,
  pauseSession,
  resetSession,
  resumeSession,
} from '../api/gateway'
import { ActivityLogDrawer } from '../components/ActivityLog'
import { BestVsPrevious } from '../components/BestVsPrevious'
import { BudgetPanel } from '../components/BudgetPanel'
import { ExperimentTimeline } from '../components/ExperimentTimeline'
import { LiveAgentGraph } from '../components/LiveAgentGraph'
import { MockBanner, ReplayBanner } from '../components/MockBanner'
import { ScoreChart } from '../components/ScoreChart'
import { SelfHealPanel } from '../components/SelfHealPanel'
import { ServiceHealthStrip } from '../components/ServiceHealthStrip'
import { SessionMeta } from '../components/SessionMeta'
import { SessionReportModal } from '../components/SessionReportModal'
import { TopBar } from '../components/TopBar'
import { useEventStream } from '../hooks/useEventStream'
import { initialSessionState, sessionReducer } from '../state/sessionReducer'
import type { EventEnvelope } from '../types/events'

export function ControlCenterPage() {
  const { sessionId = null } = useParams()
  const [params] = useSearchParams()
  const [busy, setBusy] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)

  const [state, dispatch] = useReducer(
    sessionReducer,
    undefined,
    () =>
      initialSessionState({
        sessionId,
        status: 'running',
        mock: params.get('mock') === 'true',
        replay: params.get('replay') === 'true' || params.get('mode') === 'replay',
        mode: (params.get('mode') as 'live' | 'mock' | 'replay') || 'live',
        scenario: params.get('scenario') ?? 'happy',
        dataset: params.get('dataset') ?? 'churn_sample.csv',
        targetColumn: params.get('target') ?? 'churned',
        metric: params.get('metric') ?? 'f1',
        targetScore: Number(params.get('targetScore') ?? 0.7),
        experimentBudget: Number(params.get('budget') ?? 10),
        researchStrategy:
          params.get('strategy') === 'blackbox_tuning' ? 'blackbox_tuning' : 'model_search',
        fixedModelFamily: params.get('model') || null,
        perTrialTimeoutSeconds: Number(params.get('trialTimeout') ?? 120),
      }),
  )

  const onEvent = useCallback((event: EventEnvelope) => {
    dispatch({ type: 'EVENT', event })
  }, [])

  useEventStream(sessionId, state.status !== 'reset', onEvent)

  // Health strip: poll gateway probes so status is not stuck on "unknown"
  // when the session SSE already finished or missed the health event.
  useEffect(() => {
    let cancelled = false
    const pull = async () => {
      try {
        const body = await fetchServicesHealth()
        if (cancelled || !body.services) return
        dispatch({
          type: 'EVENT',
          event: {
            timestamp: new Date().toISOString(),
            session_id: sessionId ?? 'local',
            correlation_id: 'health-poll',
            source_service: 'gateway',
            source_agent: null,
            type: 'health',
            payload: { services: body.services, note: body.note },
            mock: false,
          },
        })
      } catch {
        /* gateway down — leave strip as-is */
      }
    }
    void pull()
    const id = window.setInterval(() => void pull(), 12_000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [sessionId])

  const syncedRef = useRef<string | null>(null)
  useEffect(() => {
    if (!sessionId) return
    if (state.status !== 'completed' && state.status !== 'error') return
    const key = `${sessionId}:${state.status}:${state.stopReason}`
    if (syncedRef.current === key) return
    syncedRef.current = key
    void patchSessionRecord(sessionId, {
      status: state.status === 'error' ? 'failed' : 'completed',
      best_val_score: state.bestValScore,
      holdout_score: state.holdoutScore,
      stop_reason: state.stopReason,
      experiments_used: state.experimentsUsed,
    }).catch(() => {
      /* registry optional for legacy sessions */
    })
  }, [
    sessionId,
    state.status,
    state.stopReason,
    state.bestValScore,
    state.holdoutScore,
    state.experimentsUsed,
  ])

  async function onPause() {
    if (!sessionId) return
    setBusy(true)
    try {
      await pauseSession(sessionId)
      dispatch({ type: 'STATUS', status: 'paused' })
    } finally {
      setBusy(false)
    }
  }

  async function onResume() {
    if (!sessionId) return
    setBusy(true)
    try {
      await resumeSession(sessionId)
      dispatch({ type: 'STATUS', status: 'running' })
    } finally {
      setBusy(false)
    }
  }

  async function onReset() {
    if (!sessionId) return
    setBusy(true)
    try {
      await resetSession(sessionId)
      dispatch({ type: 'STATUS', status: 'reset' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="lab-grid flex min-h-screen flex-col">
      <MockBanner visible={state.mock && !state.replay} />
      <ReplayBanner visible={state.replay} />
      <ServiceHealthStrip health={state.serviceHealth} />
      <TopBar
        state={state}
        onPause={onPause}
        onResume={onResume}
        onReset={onReset}
        busy={busy}
        activityOpen={activityOpen}
        onToggleActivity={() => setActivityOpen((v) => !v)}
        onCreateReport={() => setReportOpen(true)}
        backTo="/"
      />
      <SessionMeta state={state} />

      <div className="mx-auto grid w-full max-w-[1400px] flex-1 gap-6 px-4 py-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="flex min-h-0 flex-col gap-6">
          <LiveAgentGraph state={state} />
          <ExperimentTimeline
            experiments={state.experiments}
            traceEvents={state.traceEvents}
          />
        </div>
        <div className="flex min-h-0 flex-col gap-6">
          <ScoreChart experiments={state.experiments} targetScore={state.targetScore} />
          <SelfHealPanel
            experiments={state.experiments}
            traceEvents={state.traceEvents}
            budget={state.selfHealBudget}
          />
          <BestVsPrevious experiments={state.experiments} />
          <BudgetPanel state={state} />
        </div>
      </div>

      <ActivityLogDrawer
        items={state.activity}
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
      />
      <SessionReportModal
        state={state}
        open={reportOpen}
        onClose={() => setReportOpen(false)}
      />

      <footer className="border-t border-line px-6 py-3 text-center text-xs text-mist">
        {params.get('project') ? (
          <Link to={`/projects/${params.get('project')}`} className="text-teal hover:underline">
            Back to project
          </Link>
        ) : (
          <Link to="/advanced" className="text-teal hover:underline">
            Projects
          </Link>
        )}
        {' · '}
        {params.get('project') ? (
          <Link
            to={`/projects/${params.get('project')}/new`}
            className="text-teal hover:underline"
          >
            New session
          </Link>
        ) : (
          <Link to="/advanced" className="text-teal hover:underline">
            New session
          </Link>
        )}
        {' · '}
        Live agent graph driven by SSE
      </footer>
    </div>
  )
}
