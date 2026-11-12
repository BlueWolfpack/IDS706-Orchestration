import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AppNav } from '../components/AppNav'
import { CopyBlock } from '../components/CopyBlock'
import {
  CONFIRM_OUTPUT_CMD,
  LIST_RUNS_CMD,
  TASK_SNIPPETS,
  TRIGGER_CMD,
  UNPAUSE_CMD,
  WIRING_SNIPPET,
} from '../guide/airflowSnippets'
import {
  BUILD_GRAPH_SNIPPET,
  NODE_SNIPPETS,
  STATUS_CMD,
} from '../guide/langgraphSnippets'

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="space-y-3 rounded border border-line bg-panel/80 p-4">
      <h2 className="font-display text-lg text-paper">
        <span className="mr-2 text-teal">{n}.</span>
        {title}
      </h2>
      {children}
    </section>
  )
}

function Code({ children }: { children: ReactNode }) {
  return <code className="font-mono text-xs text-teal">{children}</code>
}

function AirflowTab() {
  return (
    <div className="space-y-4 text-sm text-mist">
      <p>
        Assumes Airflow is already up (<Code>make airflow</Code> in the README). UI:{' '}
        <a className="text-teal underline" href="http://localhost:8088" target="_blank" rel="noreferrer">
          localhost:8088
        </a>{' '}
        (<Code>admin</Code> / <Code>admin</Code>).
      </p>

      <Step n={1} title="Open the skeleton">
        <p>
          Edit <Code>lab/airflow/dags/lab_baseline_prep.py</Code>. Until it is wired, the DAG parses
          and the Graph tab stays empty. Don&apos;t Trigger until task bodies are filled and wiring is
          pasted. Filled reference: <Code>solution/airflow/dags/solution_baseline_prep.py</Code>.
          Markdown copy steps: <Code>lab/airflow/COPY_GUIDE.md</Code>.
        </p>
        <p>
          Each DAG is one file: pandas/sklearn code lives inside the <Code>@task</Code> bodies (no
          helper modules). Constants like <Code>CUSTOMERS</Code> / <Code>TARGET</Code> are already at
          the top of the lab file.
        </p>
      </Step>

      <Step n={2} title="Fill task bodies">
        <p>
          For each <Code>@task</Code>, replace the docstring +{' '}
          <Code>raise NotImplementedError(...)</Code> with the matching snippet (keep the{' '}
          <Code>@task</Code> / <Code>def</Code> lines). Use Copy → paste.
        </p>
        {TASK_SNIPPETS.map((s) => (
          <div key={s.id} className="space-y-1">
            <h3 className="font-mono text-paper">{s.title}</h3>
            <p>{s.hint}</p>
            <CopyBlock code={s.code} lang="python" />
          </div>
        ))}
      </Step>

      <Step n={3} title="Wire the DAG">
        <p>
          Delete the commented TODO wiring block and paste this after the last <Code>@task</Code>{' '}
          (do <strong>not</strong> leave a bare <Code>raise</Code> here — Airflow runs this function at
          import time):
        </p>
        <CopyBlock code={WIRING_SNIPPET} lang="python" />
        <p>
          Calling a <Code>@task</Code> here builds Graph edges (it does not run Python yet). After you
          save, the Graph tab shows the full dependency graph.
        </p>
      </Step>

      <Step n={4} title="Run in Airflow">
        <p>
          From the <strong>repo root</strong>, or unpause/trigger in the UI at{' '}
          <a className="text-teal underline" href="http://localhost:8088" target="_blank" rel="noreferrer">
            localhost:8088
          </a>
          .
        </p>
        <ol className="list-decimal space-y-3 pl-5">
          <li>
            Unpause <Code>lab_baseline_prep</Code>:
            <div className="mt-2">
              <CopyBlock code={UNPAUSE_CMD} lang="bash" />
            </div>
          </li>
          <li>
            Trigger the DAG:
            <div className="mt-2">
              <CopyBlock code={TRIGGER_CMD} lang="bash" />
            </div>
          </li>
          <li>
            Wait until the run succeeds (Graph tab all green, or poll CLI):
            <div className="mt-2">
              <CopyBlock code={LIST_RUNS_CMD} lang="bash" />
            </div>
          </li>
          <li>
            Confirm publish + artifacts on the host:
            <div className="mt-2">
              <CopyBlock code={CONFIRM_OUTPUT_CMD} lang="bash" />
            </div>
          </li>
        </ol>
      </Step>
    </div>
  )
}

function LangGraphTab() {
  return (
    <div className="space-y-4 text-sm text-mist">
      <p>
        Assumes the web app is already up (<Code>make start-mac</Code> / <Code>make start-windows</Code>
        ). Open{' '}
        <Link className="text-teal underline" to="/lab-loop">
          /lab-loop
        </Link>
        — the graph stays empty until <Code>build_graph()</Code> is wired.
      </p>

      <Step n={1} title="Open the skeleton">
        <p>
          Edit <Code>lab/langgraph/graph.py</Code>. LLM helpers are imported from{' '}
          <Code>loop_runtime.py</Code> (already wired). Filled reference:{' '}
          <Code>solution/langgraph/graph.py</Code> — same node shape, with working bodies. Markdown copy steps:{' '}
          <Code>lab/langgraph/COPY_GUIDE.md</Code>.
        </p>
        <div>
          Optional readiness check:
          <div className="mt-2">
            <CopyBlock code={STATUS_CMD} lang="bash" />
          </div>
        </div>
      </Step>

      <Step n={2} title="Fill agent nodes + router">
        <p>
          Replace each <Code>raise NotImplementedError(...)</Code> body with the matching snippet
          (keep the function signatures). LLM helpers are already imported from{' '}
          <Code>loop_runtime.py</Code> — you do not paste Cursor/OpenRouter helper code.
        </p>
        {NODE_SNIPPETS.map((s) => (
          <div key={s.id} className="space-y-1">
            <h3 className="font-mono text-paper">{s.title}</h3>
            <p>{s.hint}</p>
            <CopyBlock code={s.code} lang="python" />
          </div>
        ))}
      </Step>

      <Step n={3} title="Wire build_graph()">
        <p>
          Inside <Code>build_graph()</Code>, remove the final <Code>raise NotImplementedError</Code> and
          paste this after <Code>g = StateGraph(SimpleLoopState)</Code>:
        </p>
        <CopyBlock code={BUILD_GRAPH_SNIPPET} lang="python" />
        <p>
          <Code>add_node</Code> = a box on the graph. <Code>add_edge</Code> = always go next.{' '}
          <Code>add_conditional_edges</Code> = ask the router which path. <Code>compile()</Code> freezes
          it. Topology: START → data_scientist → hypothesis → ml_engineer → judge → (memory loop or
          holdout → END).
        </p>
      </Step>

      <Step n={4} title="Refresh and run">
        <ol className="list-decimal space-y-1 pl-5">
          <li>
            On{' '}
            <Link className="text-teal underline" to="/lab-loop">
              /lab-loop
            </Link>
            , click Refresh (or reload the page). The live graph should appear when status is ready.
          </li>
          <li>
            Pick a CSV (e.g. <Code>Titanic-Dataset.csv</Code>, target <Code>Survived</Code>) and Run.
          </li>
          <li>Watch nodes complete over SSE. Holdout runs once at the end.</li>
        </ol>
      </Step>
    </div>
  )
}

export function GuidePage() {
  const [tab, setTab] = useState<'airflow' | 'langgraph'>('airflow')
  const tabCls = (t: string) =>
    `rounded-t border border-b-0 border-line px-4 py-1.5 text-sm ${
      tab === t ? 'bg-panel text-teal' : 'text-mist hover:text-paper'
    }`
  return (
    <div className="lab-grid min-h-screen">
      <AppNav />
      <main className="mx-auto max-w-[900px] space-y-4 px-4 py-6">
        <h1 className="font-display text-2xl text-paper">Student Guide</h1>
        <p className="text-sm text-mist">
          Lab copy steps only. Startup is in the repo README (<Code>make start-mac</Code> /{' '}
          <Code>make start-windows</Code>, <Code>make airflow</Code>).
        </p>
        <div className="flex gap-1">
          <button type="button" className={tabCls('airflow')} onClick={() => setTab('airflow')}>
            Airflow
          </button>
          <button type="button" className={tabCls('langgraph')} onClick={() => setTab('langgraph')}>
            LangGraph
          </button>
        </div>
        {tab === 'airflow' ? <AirflowTab /> : <LangGraphTab />}
      </main>
    </div>
  )
}
