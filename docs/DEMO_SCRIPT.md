# Demo script (5 minutes) — mock backend

Use this when teaching with Stage B fixtures only. Banner must say **MOCK BACKEND**.

## Prep (30 s)

```bash
make up
cd frontend && npm run dev
```

Open http://localhost:5173. Confirm mock banner. Mention: *“Every number you see is a labeled fixture — real training starts in Phase C.”*

## 1. Setup (45 s)

1. Keep `churn_sample.csv`, classification, target `churned`, F1, target 0.70, budget 10.
2. Scenario picker → **`happy`**.
3. Point at **Fixed protocol** (split once, sealed holdout, limits).
4. Click **Start research session**.

**Say:** *“Four leads and twelve subagents. The Judge never sees the holdout.”*

## 2. Live graph + panels (90 s)

1. Watch **Live agent graph**: nodes flip pending → running → completed from SSE only.
2. Toggle **Overview** / **Detailed**; click **ML Engineer** for side panel (service badge, correlation id).
3. Point at amber **Experiment A/B/C** and **Fan-in**: *“Planned parallel branches — not built.”*
4. Timeline + F1 chart update from events; target line at 0.70.
5. Activity log streams the same events.

## 3. Holdout stays sealed (45 s)

1. Wait for `holdout_evaluated` / stop reason `accepted`.
2. **Say:** *“Holdout opened once at the end. Agents only saw train and validation metrics. In the real system only harness → dataset-service `/internal/holdout/evaluate` can do this.”*
3. Optional: open http://127.0.0.1:8004/docs and show there is **no** public holdout download route (skeleton until C1).

## 4. One retry (repair scenario) (60 s)

1. **New session** → scenario **`repair`** → Start.
2. Watch Config validator fail → **Error repair** → retry → success.
3. **Say:** *“Bounded recovery: one fix, then revalidate. No unbounded retries.”*

## 5. Service-down story (45 s)

1. New session → **`service_down`**.
2. Health strip shows harness **down**; typed `service_error`; bounded retry; terminal failed trial.
3. **Say:** *“In Phase D we will literally `docker compose stop harness` on a real run. Today the fixture teaches the same UI path.”*

## Optional 30 s — static diagrams

Nav: **Architecture** (microservices + MCP), **Orchestration** (loop-back + planned fan-out), **Recovery** (repair loop + checkpointer + policy).

## Close

*“Next we replace mocks one service at a time. The UI stays the same — only the event source becomes real.”*

---

# Live demo (5 minutes) — Phase C/D real path

Requires `MOCK_*=false` in `.env`, `make up`, frontend on :5173. Banner must be **gone**.

## Prep

```bash
make up && make health
cd frontend && npm run dev
```

Optional: `CURSOR_API_KEY` (Composer 2.5) and `WANDB_ENABLED=true` + `WANDB_API_KEY`. Without Cursor, LLM subagents use deterministic fallbacks.

## Walkthrough

1. Upload `datasets/churn_sample.csv`, target `churned`, start session.
2. Graph shows real `trial_completed` / verdict events from the orchestrator.
3. Open MLflow http://127.0.0.1:5050 — validation runs + one `final` holdout run.
4. Failure: `docker compose -f infra/docker-compose.yml stop harness`, start a session, show typed error path, then `start harness` again.
5. Baselines: `.venv/bin/python scripts/eval_baselines.py` — report numbers; do not claim multi-agent wins unless it does.
