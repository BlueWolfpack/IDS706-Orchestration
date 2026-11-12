export function GraphLegend() {
  return (
    <div className="absolute bottom-3 left-3 z-10 border border-line bg-panel/95 px-3 py-2 text-[10px] text-mist shadow-sm">
      <p className="mb-1 font-mono uppercase tracking-wider text-paper">Legend</p>
      <ul className="space-y-1">
        <li className="flex items-center gap-2">
          <span className="inline-block h-px w-6 bg-paper" /> control flow
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-px w-6 border-t border-dashed border-mist" /> data / memory
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-px w-6 border-t border-dotted border-mist" /> event stream
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-3 w-6 border border-dashed border-amber bg-amber/10" /> planned
        </li>
      </ul>
    </div>
  )
}
