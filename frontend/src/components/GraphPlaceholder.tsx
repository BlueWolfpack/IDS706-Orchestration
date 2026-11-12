/** Live React Flow graph arrives in Stage B2 — labeled planned, not faked. */

export function GraphPlaceholder() {
  return (
    <section className="flex h-full min-h-64 flex-col border border-dashed border-amber/50 bg-amber/5 p-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-amber">
        Planned · Stage B2
      </p>
      <h2 className="mt-1 font-display text-xl text-paper">Live agent graph</h2>
      <p className="mt-2 max-w-md text-sm text-mist">
        Expandable leads, twelve subagents, status from SSE, service badges, and active-edge
        animation. Not built yet — this panel will replace this placeholder.
      </p>
      <div className="mt-6 flex flex-1 items-center justify-center">
        <div className="grid w-full max-w-lg grid-cols-2 gap-2 opacity-60 sm:grid-cols-4">
          {['Meta-supervisor', 'Data Scientist', 'Hypothesis', 'ML Engineer', 'Judge'].map(
            (name) => (
              <div
                key={name}
                className="border border-dashed border-amber/40 px-2 py-3 text-center font-mono text-[10px] text-amber"
              >
                {name}
              </div>
            ),
          )}
        </div>
      </div>
    </section>
  )
}
