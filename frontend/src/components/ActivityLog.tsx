import { useEffect } from 'react'
import type { ActivityItem } from '../types/events'

export function ActivityLogDrawer({
  items,
  open,
  onClose,
}: {
  items: ActivityItem[]
  open: boolean
  onClose: () => void
}) {
  const newestFirst = [...items].reverse()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Agent activity log">
      <button
        type="button"
        className="absolute inset-0 bg-ink/30 backdrop-blur-[1px]"
        aria-label="Close activity log"
        onClick={onClose}
      />
      <aside className="relative flex h-full w-full max-w-md flex-col border-l border-line bg-panel shadow-xl animate-[slideIn_180ms_ease-out]">
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div>
            <h2 className="font-display text-xl text-paper">Agent activity log</h2>
            <p className="font-mono text-[10px] uppercase tracking-wider text-mist">
              Streaming over SSE · {items.length} events
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-line px-2.5 py-1.5 text-sm text-mist hover:border-teal hover:text-paper"
          >
            Close
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto font-mono text-xs">
          {newestFirst.length === 0 ? (
            <p className="p-4 text-mist">No events yet</p>
          ) : (
            <ul className="divide-y divide-line/60">
              {newestFirst.map((item) => (
                <li key={item.id} className="grid grid-cols-[auto_minmax(0,6.5rem)_1fr] gap-2 px-3 py-2.5">
                  <time className="text-mist tabular-nums">
                    {new Date(item.timestamp).toLocaleTimeString()}
                  </time>
                  <span className="truncate text-teal">{item.agent}</span>
                  <span className="break-words text-paper/90">{item.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0.85; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  )
}

export function ActivityBurgerButton({
  count,
  open,
  onClick,
}: {
  count: number
  open: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={open}
      aria-controls="activity-log-drawer"
      title="Agent activity log"
      className="relative flex h-10 w-10 items-center justify-center rounded border border-line bg-panel text-paper hover:border-teal"
    >
      <span className="sr-only">Agent activity log</span>
      <span className="flex flex-col gap-[5px]" aria-hidden>
        <span className="block h-0.5 w-4 bg-current" />
        <span className="block h-0.5 w-4 bg-current" />
        <span className="block h-0.5 w-4 bg-current" />
      </span>
      {count > 0 && (
        <span className="absolute -right-1.5 -top-1.5 min-w-[1.15rem] rounded-full bg-teal px-1 py-0.5 text-center font-mono text-[9px] leading-none text-white">
          {count > 99 ? '99+' : count}
        </span>
      )}
    </button>
  )
}
