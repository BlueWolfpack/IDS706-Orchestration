import { useEffect, useRef } from 'react'
import { eventsUrl } from '../api/gateway'
import type { EventEnvelope, EventType } from '../types/events'

const EVENT_TYPES: EventType[] = [
  'session_created',
  'session_paused',
  'session_resumed',
  'session_reset',
  'agent_started',
  'agent_completed',
  'tool_called',
  'tool_result',
  'trial_started',
  'trial_completed',
  'trial_failed',
  'verdict_issued',
  'budget_update',
  'stop_reason',
  'holdout_evaluated',
  'health',
  'wandb_unavailable',
  'service_error',
  'activity',
]

/**
 * Single SSE hook for the Control Center.
 * Panels update only from events — never invent metrics client-side.
 * Gateway emits named SSE event types; we subscribe to each.
 * Live streams stay open across brief disconnects (EventSource auto-reconnect).
 */
export function useEventStream(
  sessionId: string | null,
  enabled: boolean,
  onEvent: (event: EventEnvelope) => void,
  onError?: (message: string) => void,
) {
  const onEventRef = useRef(onEvent)
  const onErrorRef = useRef(onError)
  onEventRef.current = onEvent
  onErrorRef.current = onError

  useEffect(() => {
    if (!sessionId || !enabled) return

    const source = new EventSource(eventsUrl(sessionId))
    let intentionalClose = false

    const handle = (msg: MessageEvent<string>) => {
      try {
        const event = JSON.parse(msg.data) as EventEnvelope
        onEventRef.current(event)
      } catch (err) {
        onErrorRef.current?.(`Failed to parse SSE event: ${String(err)}`)
      }
    }

    source.onmessage = handle
    for (const type of EVENT_TYPES) {
      source.addEventListener(type, handle as EventListener)
    }

    source.onerror = () => {
      // Mock/replay streams end by closing the socket — fine to stop.
      // Live streams: let EventSource reconnect with Last-Event-ID.
      const isLive = sessionId.startsWith('sess-')
      if (!isLive || intentionalClose) {
        source.close()
      }
    }

    return () => {
      intentionalClose = true
      source.close()
    }
  }, [sessionId, enabled])
}
