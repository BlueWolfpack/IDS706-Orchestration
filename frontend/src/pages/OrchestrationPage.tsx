import { AppNav } from '../components/AppNav'
import { MockBanner } from '../components/MockBanner'
import { StaticFlowDiagram } from '../components/StaticFlowDiagram'
import { ORCH_EDGES, ORCH_NODES, ORCH_POSITIONS } from '../graph/orchestrationConfig'

export function OrchestrationPage() {
  return (
    <div className="lab-grid min-h-screen">
      <MockBanner visible />
      <AppNav />
      <main className="mx-auto max-w-[1200px] px-4 py-6">
        <StaticFlowDiagram
          title="Agent orchestration"
          blurb="Four leads, loop-back for new hypotheses, and planned parallel branches (dashed amber)."
          items={ORCH_NODES.map((n) => ({
            id: n.id,
            title: n.title,
            role: n.role,
            planned: n.planned,
          }))}
          links={ORCH_EDGES.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label,
            kind: e.planned ? 'planned' : 'control',
            planned: e.planned,
          }))}
          positions={ORCH_POSITIONS}
        />
      </main>
    </div>
  )
}
