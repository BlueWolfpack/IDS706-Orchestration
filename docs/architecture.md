# Architecture

Seven application services plus Redis, MLflow, an artifact volume, and optional W&B MCP.

| Service | Owns | Talks to |
| --- | --- | --- |
| `web` | React UI | gateway only |
| `gateway` | session commands, SSE (`live` / `mock` / `replay`) | orchestrator, dataset-service, Redis Streams |
| `orchestrator` | LangGraph + checkpointer | agent, harness, memory, tracking, dataset (holdout) |
| `agent-service` | LLM subagents (Composer 2.5) + deterministic tools | harness, memory, read-only W&B MCP |
| `harness` | seven tools + `policy.py` | dataset-service, artifact volume |
| `dataset-service` | splits + sealed holdout | none (holdout evaluate only) |
| `memory-service` | findings / history / lessons / working | none |
| `tracking-service` | MLflow (+ optional W&B SDK mirror) | MLflow, W&B cloud |

**Events:** live sessions `XADD` each `EventEnvelope` to Redis Stream `automl:session:{id}:events` and fan out to SSE subscribers.

**Network boundary:** LLM reasoning (`agent-service`) never executes experiments. Only `harness` runs validated tools.

**Holdout:** only `POST /internal/holdout/evaluate` on `dataset-service`, once per session, harness token only. No route returns holdout rows.

**Modes:** `live` (real stack), `mock` (fixture SSE + banner), `replay` (recorded real run JSON — labeled replay, never “live”).

Visual reference: root PDF design canvas.  
Build status: [`BUILD_PLAN.md`](BUILD_PLAN.md) · Planned (not first pass): [`planned-features.md`](planned-features.md).
