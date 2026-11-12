"""Round-trip contract models — fixture numbers are labeled sample data only."""

from datetime import datetime, timezone

from contracts import (
    AgentInvokeRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    DataProfile,
    EventEnvelope,
    EventType,
    ExecutionResult,
    ExperimentSpec,
    HealthResponse,
    LeadName,
    ResearchState,
    RunExperimentRequest,
    ServiceError,
    SubagentName,
    Verdict,
    VerdictAction,
)


def test_health_response_round_trip():
    raw = HealthResponse(status="ok", service="gateway", mock=True).model_dump()
    assert HealthResponse.model_validate(raw).status == "ok"


def test_event_envelope_round_trip():
    event = EventEnvelope(
        timestamp=datetime.now(timezone.utc),
        session_id="s-demo",
        correlation_id="c-1",
        source_service="gateway",
        source_agent="meta_supervisor",
        type=EventType.AGENT_STARTED,
        payload={"lead": "data_scientist"},
        mock=True,
    )
    restored = EventEnvelope.model_validate(event.model_dump(mode="json"))
    assert restored.mock is True
    assert restored.type == EventType.AGENT_STARTED


def test_domain_models_round_trip():
    profile = DataProfile(
        dataset_id="ds-1",
        n_rows=100,
        n_columns=10,
        task_type="classification",
        target_column="churned",
        mock=True,
    )
    spec = ExperimentSpec(
        experiment_id="e-1",
        session_id="s-1",
        model_family="logistic_regression",
        mock=True,
    )
    result = ExecutionResult(
        experiment_id="e-1",
        status="succeeded",
        validation_metrics={"f1": 0.41},
        mock=True,
    )
    verdict = Verdict(
        experiment_id="e-1",
        action=VerdictAction.REVISE,
        observation="sample fixture observation",
        mock=True,
    )
    state = ResearchState(
        session_id="s-1",
        data_profile=profile,
        proposed_experiment=spec,
        latest_result=result,
        judge_verdict=verdict,
    )
    assert ResearchState.model_validate(state.model_dump()).session_id == "s-1"


def test_session_and_agent_contracts():
    req = CreateSessionRequest(target_column="churned", mock=True)
    resp = CreateSessionResponse(session_id="s-1", mock=True)
    assert CreateSessionRequest.model_validate(req.model_dump()).target_column == "churned"
    assert resp.status == "created"

    invoke = AgentInvokeRequest(
        session_id="s-1",
        correlation_id="c-1",
        lead=LeadName.JUDGE,
        subagent=SubagentName.METRIC_ANALYST,
        mock=True,
    )
    assert invoke.subagent == SubagentName.METRIC_ANALYST


def test_run_experiment_requires_idempotency_key():
    body = RunExperimentRequest(
        session_id="s-1",
        experiment_spec={"model_family": "logistic_regression"},
        correlation_id="c-1",
        idempotency_key="trial-1",
    )
    assert body.idempotency_key == "trial-1"


def test_service_error_shape():
    err = ServiceError(code="dependency_down", message="harness unreachable", retryable=True)
    assert ServiceError.model_validate(err.model_dump()).retryable is True
