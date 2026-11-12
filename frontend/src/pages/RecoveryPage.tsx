import { AppNav } from '../components/AppNav'
import { MockBanner } from '../components/MockBanner'
import { StaticFlowDiagram } from '../components/StaticFlowDiagram'
import { REC_EDGES, REC_NODES, REC_POSITIONS } from '../graph/recoveryConfig'

export function RecoveryPage() {
  return (
    <div className="lab-grid min-h-screen">
      <MockBanner visible />
      <AppNav />
      <main className="mx-auto max-w-[1200px] px-4 py-6">
        <StaticFlowDiagram
          title="Recovery and run state"
          blurb="Self-heal budget 3 per experiment, policy guard, and checkpointer. Human interrupt is planned only."
          items={REC_NODES.map((n) => ({
            id: n.id,
            title: n.title,
            role: n.role,
            planned: n.planned,
          }))}
          links={REC_EDGES.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label,
            kind: 'control',
            planned: e.source === 'human' || e.target === 'human',
          }))}
          positions={REC_POSITIONS}
        />
      </main>
    </div>
  )
}
