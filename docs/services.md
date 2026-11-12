# Services

Each service owns its data and talks only over HTTP (+ Redis Streams for events). No cross-service code imports or DB access.

| Service | Owns | Key routes | Calls |
| --- | --- | --- | --- |
| `web` | React UI | none | gateway only |
| `gateway` | session commands, SSE fan-out | `POST /sessions`, pause/resume/reset, `GET /sessions/{id}/events`, dataset upload proxy | orchestrator, dataset-service, Redis |
| `orchestrator` | LangGraph, meta-supervisor, checkpointer | `POST /runs`, `GET /runs/{id}`, pause/resume | agent, harness, memory, tracking, dataset (metadata) |
| `agent_service` | LLM subagents, prompts | `POST /agents/{lead}/{subagent}/invoke` | LLM provider; optional read-only W&B MCP |
| `harness` | seven tools, `policy.py`, backends | `/tools/*`, `GET /policy` | dataset, tracking; optional W&B report MCP |
| `dataset_service` | uploads, fixed split, sealed holdout | `/datasets`, profile-view, train/val splits, `POST /internal/holdout/evaluate` | none |
| `memory_service` | findings, history, lessons, working memory | `/findings`, `/history`, `/lessons`, `/working/{agent}` | none |
| `tracking_service` | MLflow API (+ optional W&B SDK) | `/runs`, `/experiments/{session}` | MLflow, W&B cloud |
| `wandb-mcp` | third-party | MCP HTTP (internal only) | W&B cloud |

Infra: Redis (streams + job queue), MLflow, artifact volume (writes via harness only), optional `wandb-mcp` compose profile.

See [`BUILD_PLAN.md`](BUILD_PLAN.md) for stage ownership and [`architecture.md`](architecture.md) for the teaching boundary (LLM reasoning vs deterministic execution).
