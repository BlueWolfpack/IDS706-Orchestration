"""Expected OpenAPI paths per service — contract tests fail on drift."""

EXPECTED_PATHS: dict[str, list[str]] = {
    "gateway": [
        "/healthz",
        "/sessions",
        "/sessions/{session_id}/pause",
        "/sessions/{session_id}/resume",
        "/sessions/{session_id}/reset",
        "/sessions/{session_id}/events",
        "/sessions/{session_id}/datasets",
    ],
    "orchestrator": [
        "/healthz",
        "/runs",
        "/runs/{run_id}",
        "/runs/{run_id}/pause",
        "/runs/{run_id}/resume",
    ],
    "agent_service": [
        "/healthz",
        "/agents/{lead}/{subagent}/invoke",
    ],
    "harness": [
        "/healthz",
        "/policy",
        "/tools/inspect_data",
        "/tools/validate_experiment",
        "/tools/run_experiment",
        "/tools/compare_experiments",
        "/tools/get_history",
        "/tools/save_artifact",
        "/tools/generate_report",
    ],
    "dataset_service": [
        "/healthz",
        "/datasets",
        "/datasets/{dataset_id}/profile-view",
        "/datasets/{dataset_id}/splits/{name}",
        "/internal/holdout/evaluate",
    ],
    "memory_service": [
        "/healthz",
        "/findings",
        "/history",
        "/lessons",
        "/working/{agent}",
    ],
    "tracking_service": [
        "/healthz",
        "/runs",
        "/runs/{run_id}",
        "/experiments/{session_id}",
    ],
}
