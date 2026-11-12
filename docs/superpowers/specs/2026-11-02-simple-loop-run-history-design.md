# Simple loop run history (server-side JSON)

**Status:** approved (2026-11-02)  
**Scope:** Persist and display past Simple Research Loop runs, analogous to project session history.

## Goal

Classroom demos can show prior simple-loop runs after page refresh or gateway recreate. History is a compact summary list — not full SSE replay.

## Non-goals (v1)

- Replay / restore live graph state from a past run
- Delete / edit / export APIs
- Mixing simple-loop history into project session store
- Mid-run checkpoints

## Storage

- JSON file on the gateway host path, default `/data/simple_loop/runs.json`
- Env override: `SIMPLE_LOOP_RUNS_PATH`
- Docker: persist via named volume (or extend existing `project_data` mount under `/data/simple_loop`)
- Format: `{ "runs": [ ... ] }`, newest first
- Cap: keep last **50** runs (drop oldest on append)
- Atomic write: write temp file then rename

### Run record schema

```json
{
  "run_id": "slr_…",
  "created_at": "ISO-8601",
  "status": "completed | error",
  "dataset": "merged_latest.csv",
  "target_column": "is_fraud",
  "target_score": 0.8,
  "max_cycles": 3,
  "cycles": 2,
  "best_val_f1": 0.06,
  "holdout_f1": null,
  "stop_reason": "finalize",
  "model": "xingchen-agi/xing4.0-29b-a4b:free",
  "verdict_action": "accept",
  "error": null
}
```

No full `steps` / `best_spec` blobs in v1 (keeps the file small and UI snappy).

## When it saves

Gateway appends **one** record when a run finishes:

1. `POST /simple-loop/run` — after success or caught failure (error status + message)
2. `GET /simple-loop/stream` — on `run_completed` or stream `error` event (same summary fields)

Do not write on `run_started` or per-node events.

## API

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/simple-loop/runs` | `{ "runs": [...] }` newest first |
| `GET` | `/simple-loop/runs/{run_id}` | single record or 404 |

List supports optional `?limit=` (default 50, max 50).

## UI

On `SimpleLoopPage`:

- **Run history** section (same language as project Session history: border/panel, mono labels)
- Rows: dataset · target · best val · holdout · stop/status · timestamp
- Click expands inline summary (model, cycles, target score, error if any)
- Refresh on mount + after each completed/failed run
- Empty state: “No runs yet.”

## Out of scope wiring

Airflow DAG2 trigger stub unchanged; when revealed later it can call the same run endpoints and inherit history automatically.

## Success criteria

1. Completing a simple-loop run (SSE or POST) adds a row visible after refresh
2. Gateway recreate with volume still shows prior runs
3. Failed runs appear with `status: error` and message
4. File never grows unbounded (≤50 entries)
