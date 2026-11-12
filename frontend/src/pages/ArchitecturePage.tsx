import { AppNav } from '../components/AppNav'
import { MockBanner } from '../components/MockBanner'
import { StaticFlowDiagram } from '../components/StaticFlowDiagram'
import { ARCH_EDGES, ARCH_NODES, ARCH_POSITIONS } from '../graph/architectureConfig'

export function ArchitecturePage() {
  return (
    <div className="lab-grid min-h-screen">
      <MockBanner visible />
      <AppNav />
      <main className="mx-auto max-w-[1200px] px-4 py-6">
        <StaticFlowDiagram
          title="Architecture overview"
          blurb="Microservices, REST, Redis events, and optional W&B MCP. Click a node for owned data and endpoints."
          items={ARCH_NODES.map((n) => ({
            id: n.id,
            title: n.title,
            role: n.subtitle,
            optional: n.optional,
            detail: {
              owns: n.owns,
              endpoints: n.endpoints,
              callers: n.callers,
              kind: n.kind,
            },
          }))}
          links={ARCH_EDGES.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label,
            kind: e.kind,
          }))}
          positions={ARCH_POSITIONS}
        />
        <p className="mt-3 text-xs text-mist">
          Solid = REST · dotted = event stream · dashed = own-store / MCP · amber = optional W&B
        </p>
      </main>
    </div>
  )
}
