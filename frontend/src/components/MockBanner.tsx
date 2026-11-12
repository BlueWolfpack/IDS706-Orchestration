/** Persistent while any mock service remains on the path. */

export function MockBanner({ visible }: { visible: boolean }) {
  if (!visible) return null
  return (
    <div
      role="status"
      className="border-b border-amber/30 bg-amber/10 px-4 py-2 text-center text-sm font-medium tracking-wide text-amber"
    >
      MOCK BACKEND: illustrative data, not real experiments
    </div>
  )
}

/** Replay of a recorded real run — never labeled “live” or “mock”. */
export function ReplayBanner({ visible }: { visible: boolean }) {
  if (!visible) return null
  return (
    <div
      role="status"
      className="border-b border-teal/30 bg-teal/10 px-4 py-2 text-center text-sm font-medium tracking-wide text-teal"
    >
      Replay of a recorded real run — not a live session
    </div>
  )
}
