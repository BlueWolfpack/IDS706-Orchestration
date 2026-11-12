# AutoML Research Lab — build plan

Teaching build order: **contracts → UI on mock → replace one service at a time → demo polish**.  
Work **one stage at a time**. After each stage, stop so the student can run it. Do not skip ahead.

Design canvas: [`../AutoML_Research_Lab_demo_canvas.pdf`](../AutoML_Research_Lab_demo_canvas.pdf)  
Planned (not in first pass): [`planned-features.md`](planned-features.md)  
Architecture stub: [`architecture.md`](architecture.md)

---

## Progress

| Stage | Status | Notes |
| --- | --- | --- |
| A0 Contracts + skeletons | **Done** | `contracts/`, 7 FastAPI `/healthz` services, compose, contract tests, GitHub |
| A1 Mock backend SSE | **Done** | Gateway mock mode, 6 fixture scenarios, `make demo-sse` |
| B1 Setup + Control Center | **Done** | Light-mode React UI, SSE reducer, mock banner |
| B2 Live React Flow agent graph | **Done** | Expandable leads, 12 subagents, status from SSE, planned amber nodes |
| B3 Static diagrams + demo script | **Done** | Architecture / orchestration / recovery diagrams, `DEMO_SCRIPT.md` |
| C1 dataset-service | **Done** | Real upload, fixed split, sealed holdout |
| C2 harness-service | **Done** | Seven tools + `policy.py` + sklearn backends |
| C3 tracking-service | **Done** | MLflow + optional W&B SDK mirror (`WANDB_ENABLED`) |
| C4 memory-service | **Done** | Four stores, single-writer |
| C5 agent-service | **Done** | Composer 2.5 via Cursor SDK (fallback if key/SDK missing) + W&B MCP soft probe |
| C6 orchestrator | **Done** | LangGraph meta-supervisor + MemorySaver checkpointer |
| C7 gateway | **Done** | Live SSE + Redis Streams `XADD`; mock + replay modes |
| D1 Demo polish | **Done** | Replay banner + recording, eval script, README, DEMO_SCRIPT |

Repo: https://github.com/Kedar-V/automl-research-lab

---

## Hard rules (never break)

1. No model-written code is ever executed.
2. Sealed holdout opened exactly once at the end; agents see only train/validation metrics.
3. Preprocessing fitted on training data only; fixed seeds; split created once.
4. Every loop has a counter (including HTTP retries).
5. No frontend control without working backend behavior.
6. Anything not built yet is labeled **planned** — do not fake it.
7. Mock data always has `mock: true` and the UI banner until no mocked service remains on the path.

---

## Mock-mode rules

1. Mock implements the **same** `contracts/` as real services.
2. Banner: **MOCK BACKEND: illustrative data, not real experiments** while any mock is on the path.
3. Fixtures live in `mocks/fixtures/`: `happy`, `revise_loop`, `repair`, `terminal_failure`, `budget_stop`, `service_down`.
4. Flip services with `MOCK_<SERVICE>=true|false`.
5. Same contract tests for mock and real; a service is done only when the real one passes them.
6. Fixture numbers are labeled sample data — never presented as trained-model metrics.

---

## Remaining stages (detail)

### Stage B2 — React Flow live agent graph

**Goal:** Replace the Control Center graph placeholder with `@xyflow/react`.

**Build**

- Custom memoized node: title, one-line role, status pill (`pending|running|completed|failed`), service badge (`agent-service`, `harness`, …).
- Four expandable lead group nodes + twelve subagents (`parentId` / `extent: 'parent'` or toggle).
- Meta-supervisor node; dashed amber planned nodes (parallel Experiments A/B/C + fan-in).
- Edges: main loop, Judge → Hypothesis Generator labeled `new hypothesis`, supervisor edges; `smoothstep`; solid = control, dashed = data/memory, dotted = events; legend.
- Live updates **only** from SSE (`agent_started`, `agent_completed`, `tool_called`, `trial_failed`, …). Highlight running node; never animate what did not happen.
- Click node → side panel: responsibility, latest I/O from events, service, correlation id, ML Engineer retry count; highlight upstream/downstream edges.
- `Controls`, `MiniMap`, `Background`, Fit View, Overview/Detailed toggle (overview = leads only).
- Hand-set layout in `frontend/src/graph/graphLayout.ts` (or readable dagre/elk). Nodes ≥ 160px wide.
- Shared typed configs under `frontend/src/graph/*.ts`.

**Done when:** each mock scenario visibly plays on the graph (revise loop, repair, terminal failure).

**Stop** for student run.

---

### Stage B3 — Static diagrams and mock demo extras

**Goal:** Screens 3–5 + runnable 5-minute mock demo script.

**Build**

- React Flow diagrams (read-only, fixed layout):
  1. **Architecture overview** — gateway, orchestrator, agent-service, harness, dataset, memory, tracking, Redis, MLflow, artifacts, optional `wandb-mcp` / W&B cloud (dashed). Edge styles: solid REST, dotted events, dashed own-store, dash-dot MCP. Mark LLM↔harness network boundary and single holdout route.
  2. **Agent orchestration** — leads, subagents, loop-back, planned parallel branches (amber).
  3. **Recovery and run state** — bounded recovery, checkpointer, policy guard.
- Clickable service details from typed config.
- Scenario picker prominent for live demos (may already exist on Setup; polish if needed).
- [`docs/DEMO_SCRIPT.md`](DEMO_SCRIPT.md): 5-minute walkthrough (clicks + talking points) for mock-only demo, including holdout sealed story, one retry, service-down scenario.

**Done when:** full 5-minute demo runs on the mock alone.

**Freeze point:** after Phase B, no frontend change needed to swap services except contract-compatible bug fixes.

**Stop** for student run.

---

### Stage C1 — `dataset-service` (real)

**Build:** upload CSV, fixed train/validation/holdout split, `profile-view` and splits for train/validation only, `POST /internal/holdout/evaluate` once per session (harness token only). No endpoint returns holdout rows.

**Tests:** no holdout row leak; evaluate once then reject; UI upload creates a real split.

**Done when:** uploading a CSV in the UI creates a real split. Flip `MOCK_DATASET_SERVICE=false`. Keep other mocks.

**Stop.**

---

### Stage C2 — `harness-service` (real)

**Build:** seven tools (`inspect_data`, `validate_experiment`, `run_experiment`, `compare_experiments`, `get_history`, `save_artifact`, `generate_report`), `policy.py`, execution backends, idempotent `run_experiment`.

**Tests:** leakage guard, invalid config rejected, fixed seeds reproduce score, timeout enforced. Script runs three hand-written real experiments over HTTP.

**Done when:** that script passes. Flip `MOCK_HARNESS=false`.

**Stop.**

---

### Stage C3 — `tracking-service` + W&B mirroring

**Build:** MLflow logging; optional W&B SDK mirror behind `WANDB_ENABLED`. Holdout score only in a separate run tagged `final`. Never put `WANDB_API_KEY` in events/logs/UI.

**Done when:** each real trial appears in MLflow (and W&B when enabled). Flip `MOCK_TRACKING_SERVICE=false`.

**Stop.**

---

### Stage C4 — `memory-service` (real)

**Build:** findings board, experiment history, long-term lessons (keyword retrieval), per-agent working memory; single-writer enforcement.

**Done when:** history from one run is readable by the next; second writer rejected. Flip `MOCK_MEMORY_SERVICE=false`.

**Stop.**

---

### Stage C5 — `agent-service` (real)

**Build:** typed LLM subagents (Hypothesis drafter, Metric analyst, Independent reviewer, Feature analyst); deterministic others stay code. Read-only W&B MCP allow-list (`query_wandb_tool`, `query_wandb_entity_projects`) scoped to project, filter out `final`. `wandb-mcp` compose profile. Graceful `wandb_unavailable` if down.

**Done when:** each LLM subagent returns contract-validated output; MCP query shows as event and skips cleanly when `wandb-mcp` is stopped. Flip `MOCK_AGENT_SERVICE=false`.

**Stop.**

---

### Stage C6 — `orchestrator` (real)

**Build:** `ResearchState`, deterministic LangGraph meta-supervisor (budgets, retries, timeouts, target-score stop, duplicate prevention, `stop_reason`), four leads × twelve subagents wired over HTTP (no LLM in orchestrator), SQLite checkpointer, bounded ML Engineer recovery (one repair then retry).

**Done when:** real run completes within budget; resume after kill/restart orchestrator (test must pass before claiming); forced bad config → one repair → terminal failure. Flip `MOCK_ORCHESTRATOR=false`.

**Stop.**

---

### Stage C7 — `gateway` (real)

**Build:** real session commands, Redis Streams fan-in, SSE with correlation ids, pause at checkpoints. Mock backend off.

**Done when:** mock banner gone; same UI runs a real session end to end. Flip `MOCK_GATEWAY=false`. No `MOCK_*` left on for the final demo path.

**Stop.**

---

### Stage D1 — Demo polish

**Build**

- Replay mode: recorded **real** run JSON through gateway; UI label **Replay of a recorded real run** (never “live”).
- Failure demo: document `docker compose stop harness` (or equivalent); class sees typed error, bounded retry, failed trial on graph.
- Evaluation script: A baseline, B random search, C single-agent planner, D multi-agent — equal budgets; report val/holdout scores, experiment count, time, invalid configs, cost; do not claim D wins unless numbers show it.
- README student path (< 10 minutes); finish [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) for real demo; keep [`planned-features.md`](planned-features.md) accurate.

**Done when:** a new student can run the real demo from the README in under 10 minutes.

---

## Definition of done (whole project)

- `make test` passes (including contracts); `docker compose up` is healthy.
- No on-screen metric without a backend event; mock data never without the banner.
- Mock and real pass the same contract tests; final demo has no `MOCK_*` on.
- Holdout touched once; no route returns holdout rows.
- No cross-service DB reads.
- W&B optional (`WANDB_ENABLED=false` works); `final` holdout run never returned to agents; API key nowhere in logs/events/UI.
- Every limit lives in harness `policy.py`.
- Planned items labeled planned.
- New student: demo from README in < 10 minutes.

---

## How to continue in Cursor

All first-pass stages (A0–D1) are complete. Remaining items live in [`planned-features.md`](planned-features.md) (parallel branches, human edit checkpoints, vector lessons, mTLS).
