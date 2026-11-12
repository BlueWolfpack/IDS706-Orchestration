/**
 * Self-check for lead rollup + activeNodeId (run: npx tsx src/state/sessionReducer.check.ts).
 * ponytail: assert-only; drop when vitest arrives.
 */
import { initialSessionState, sessionReducer } from './sessionReducer'
import type { EventEnvelope } from '../types/events'

function evt(
  type: EventEnvelope['type'],
  source_agent: string,
  payload: Record<string, unknown> = {},
): EventEnvelope {
  return {
    type,
    timestamp: new Date().toISOString(),
    correlation_id: 'c1',
    session_id: 's1',
    source_service: 'orchestrator',
    source_agent,
    mock: false,
    payload,
  }
}

let s = initialSessionState()
s = sessionReducer(s, { type: 'EVENT', event: evt('agent_started', 'data_profiler') })
console.assert(s.agentNodes.data_profiler?.status === 'running', 'profiler running')
console.assert(s.agentNodes.data_scientist?.status === 'running', 'lead bubbled')
console.assert(s.activeNodeId === 'data_profiler', 'active set')

s = sessionReducer(s, { type: 'EVENT', event: evt('agent_completed', 'data_profiler') })
console.assert(s.agentNodes.data_profiler?.status === 'completed', 'profiler done')
console.assert(s.activeNodeId === null, 'active cleared')
console.assert(s.agentNodes.data_scientist?.status === 'running', 'lead still running (siblings pending)')

for (const id of ['leakage_auditor', 'feature_analyst'] as const) {
  s = sessionReducer(s, { type: 'EVENT', event: evt('agent_started', id) })
  s = sessionReducer(s, { type: 'EVENT', event: evt('agent_completed', id) })
}
console.assert(s.agentNodes.data_scientist?.status === 'completed', 'lead rolled up')

s = sessionReducer(s, { type: 'EVENT', event: evt('agent_started', 'error_repair') })
s = sessionReducer(s, { type: 'EVENT', event: evt('agent_completed', 'error_repair') })
// optional — ml lead should not require it; start fresh ml path
let m = initialSessionState()
m = sessionReducer(m, { type: 'EVENT', event: evt('agent_started', 'config_validator') })
m = sessionReducer(m, { type: 'EVENT', event: evt('agent_completed', 'config_validator') })
m = sessionReducer(m, { type: 'EVENT', event: evt('agent_started', 'experiment_runner') })
m = sessionReducer(m, { type: 'EVENT', event: evt('agent_completed', 'experiment_runner') })
console.assert(m.agentNodes.ml_engineer?.status === 'completed', 'ml lead without error_repair')
console.assert(m.agentNodes.error_repair === undefined || m.agentNodes.error_repair.status === 'pending', 'repair still pending ok')

console.log('sessionReducer.check: ok')
