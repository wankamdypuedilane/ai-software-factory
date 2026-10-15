"""Producer-boundary validation of the declarative implementation contract.

A response coming out of the provider must declare its contract. A task
already persisted without one stays readable: legacy applies to reading old
state, never to producing new work.
"""

import pytest

from ai_factory.agent_result import (
    AgentImplementationRequest,
)
from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
    VerificationPolicy,
    clamp_verification_policy,
    validate_declared_contract,
)
from ai_factory.implementation_request import (
    ImplementationTask,
    build_implementation_tasks,
)
from ai_factory.implementation_retry import (
    build_implementation_retry_context,
)
from ai_factory.implementation_runtime import (
    resolve_verification_policy,
)
from ai_factory.openai_provider import (
    OpenAIProvider,
)
from ai_factory.result_application import (
    apply_agent_result,
)


DECLARED_RESPONSE = """
{
    "status": "COMPLETED",
    "summary": "Implementation planning completed.",
    "artifacts": [],
    "artifact_requests": [],
    "implementation_requests": [
        {
            "id": "ACME-DEV-CART-REPOSITORY",
            "title": "Cart repository",
            "purpose": "Implement the cart repository.",
            "kind": "IMPLEMENTATION",
            "scope": "TASK",
            "verification": {
                "allow_full_suite": false,
                "baseline_required": true
            }
        },
        {
            "id": "ACME-DEV-FINAL-VERIFICATION",
            "title": "Final verification",
            "purpose": "Validate the increment.",
            "kind": "VERIFICATION",
            "scope": "PROJECT",
            "verification": {
                "allow_full_suite": true,
                "baseline_required": false
            }
        }
    ],
    "questions": [],
    "blockers": [],
    "handoff": null,
    "metadata": {}
}
"""


UNDECLARED_RESPONSE = """
{
    "status": "COMPLETED",
    "summary": "Implementation planning completed.",
    "artifacts": [],
    "artifact_requests": [],
    "implementation_requests": [
        {
            "id": "ACME-DEV-CART-REPOSITORY",
            "title": "Cart repository",
            "purpose": "Implement the cart repository.",
            "kind": null,
            "scope": null,
            "verification": null
        }
    ],
    "questions": [],
    "blockers": [],
    "handoff": null,
    "metadata": {}
}
"""


@pytest.fixture()
def provider(
    monkeypatch: pytest.MonkeyPatch,
) -> OpenAIProvider:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    return OpenAIProvider(
        model="test-model",
    )


# --------------------------------------------------------------------------
# Producer boundary
# --------------------------------------------------------------------------


def test_declared_provider_response_is_accepted(
    provider: OpenAIProvider,
) -> None:
    result = provider._parse_result(
        DECLARED_RESPONSE
    )

    first = result.implementation_requests[0]

    assert first.kind is ImplementationTaskKind.IMPLEMENTATION
    assert first.scope is ImplementationScope.TASK
    assert first.verification == VerificationPolicy(
        allow_full_suite=False,
        baseline_required=True,
    )

    second = result.implementation_requests[1]

    assert second.kind is ImplementationTaskKind.VERIFICATION
    assert second.scope is ImplementationScope.PROJECT
    assert second.verification == VerificationPolicy(
        allow_full_suite=True,
        baseline_required=False,
    )


def test_undeclared_provider_response_is_refused(
    provider: OpenAIProvider,
) -> None:
    with pytest.raises(
        ValueError,
        match="must declare kind",
    ):
        provider._parse_result(
            UNDECLARED_RESPONSE
        )


def test_provider_response_with_unknown_kind_is_refused(
    provider: OpenAIProvider,
) -> None:
    payload = DECLARED_RESPONSE.replace(
        '"kind": "IMPLEMENTATION"',
        '"kind": "SOMETHING_ELSE"',
    )

    with pytest.raises(
        ValueError,
        match="must declare kind",
    ):
        provider._parse_result(
            payload
        )


def test_provider_response_with_partial_verification_is_refused(
    provider: OpenAIProvider,
) -> None:
    payload = DECLARED_RESPONSE.replace(
        '"baseline_required": true',
        '"baseline_required": null',
    )

    with pytest.raises(
        ValueError,
        match="must declare verification",
    ):
        provider._parse_result(
            payload
        )


def test_intermediate_unit_cannot_grant_itself_the_full_suite() -> None:
    """The claim is reduced rather than refused, and still denied.

    Refusing it raised a ValueError the CLI reported as an operator syntax
    mistake, which cost a whole Developer cycle in round 11. The unit is
    left without the full suite either way, so this asserts the outcome.
    """

    request = AgentImplementationRequest(
        id="ACME-DEV-CART-REPOSITORY",
        title="Cart repository",
        purpose="Implement the cart repository.",
        kind=ImplementationTaskKind.IMPLEMENTATION,
        scope=ImplementationScope.TASK,
        verification=clamp_verification_policy(
            kind=ImplementationTaskKind.IMPLEMENTATION,
            scope=ImplementationScope.TASK,
            verification=VerificationPolicy(
                allow_full_suite=True,
                baseline_required=True,
            ),
        ),
    )

    assert request.verification.allow_full_suite is False
    assert request.verification.baseline_required is True

    validate_declared_contract(request)


def test_task_scoped_verification_cannot_grant_the_full_suite() -> None:
    request = AgentImplementationRequest(
        id="ACME-DEV-CART-VERIFICATION",
        title="Cart verification",
        purpose="Verify the cart.",
        kind=ImplementationTaskKind.VERIFICATION,
        scope=ImplementationScope.TASK,
        verification=clamp_verification_policy(
            kind=ImplementationTaskKind.VERIFICATION,
            scope=ImplementationScope.TASK,
            verification=VerificationPolicy(
                allow_full_suite=True,
                baseline_required=False,
            ),
        ),
    )

    assert request.verification.allow_full_suite is False

    validate_declared_contract(request)


# --------------------------------------------------------------------------
# End-to-end contract survival
# --------------------------------------------------------------------------


def test_contract_survives_provider_to_task_to_state_to_retry(
    provider: OpenAIProvider,
) -> None:
    result = provider._parse_result(
        DECLARED_RESPONSE
    )

    # provider -> ImplementationTask
    tasks = build_implementation_tasks(
        agent_name="developer",
        requests=result.implementation_requests,
    )

    verification_task = tasks[1]

    assert verification_task.kind is ImplementationTaskKind.VERIFICATION
    assert verification_task.scope is ImplementationScope.PROJECT

    policy = resolve_verification_policy(
        verification_task
    )

    assert policy.allow_full_suite is True
    assert policy.baseline_required is False

    # ImplementationTask -> state.yaml
    state = {
        "agents": {
            "developer": {
                "status": "READY",
            }
        }
    }

    apply_agent_result(
        state,
        "developer",
        result,
    )

    stored = (
        state["agents"]["developer"]["last_result"]
        ["implementation_requests"]
    )

    assert stored[0]["kind"] == "IMPLEMENTATION"
    assert stored[0]["scope"] == "TASK"
    assert stored[0]["verification"] == {
        "allow_full_suite": False,
        "baseline_required": True,
    }

    # state.yaml -> retry/reload
    state["agents"]["developer"]["last_result"][
        "failed_task_id"
    ] = "ACME-DEV-FINAL-VERIFICATION"
    state["agents"]["developer"]["last_result"][
        "test_results"
    ] = []

    retry_context = build_implementation_retry_context(
        state
    )

    restored = build_implementation_tasks(
        agent_name="developer",
        requests=[retry_context.task],
    )[0]

    restored_policy = resolve_verification_policy(
        restored
    )

    assert restored_policy.allow_full_suite is True
    assert restored_policy.baseline_required is False


# --------------------------------------------------------------------------
# Legacy reading stays possible
# --------------------------------------------------------------------------


def test_legacy_persisted_task_without_contract_stays_readable() -> None:
    retry_context = build_implementation_retry_context(
        {
            "agents": {
                "developer": {
                    "status": "FAILED",
                    "last_result": {
                        "failed_task_id": "LEGACY-001",
                        "implementation_requests": [
                            {
                                "id": "LEGACY-001",
                                "title": "Legacy unit",
                                "purpose": "Implement it.",
                            }
                        ],
                        "test_results": [],
                    },
                }
            }
        }
    )

    assert retry_context.task.kind is None
    assert retry_context.task.scope is None
    assert retry_context.task.verification is None

    policy = resolve_verification_policy(
        build_implementation_tasks(
            agent_name="developer",
            requests=[retry_context.task],
        )[0]
    )

    assert policy.allow_full_suite is False
    assert policy.baseline_required is True


# --------------------------------------------------------------------------
# No title heuristic for a declared unit
# --------------------------------------------------------------------------


def test_declared_task_never_reaches_the_title_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(task):
        raise AssertionError(
            "The title heuristic must not run for a declared task."
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime._is_verification_task",
        forbidden,
    )

    declared = ImplementationTask(
        agent_name="developer",
        id="ACME-DEV-FULL-GLOBAL-E2E-TESTS",
        title="Full global e2e verification tests",
        purpose="Run the entire final regression suite.",
        kind=ImplementationTaskKind.TEST_IMPLEMENTATION,
        scope=ImplementationScope.TASK,
        verification=VerificationPolicy(
            allow_full_suite=False,
            baseline_required=True,
        ),
    )

    policy = resolve_verification_policy(
        declared
    )

    assert policy.allow_full_suite is False

    # Declaring only the kind is still enough to avoid the heuristic.
    kind_only = ImplementationTask(
        agent_name="developer",
        id="ACME-DEV-FULL-GLOBAL-E2E-TESTS",
        title="Full global e2e verification tests",
        purpose="Run the entire final regression suite.",
        kind=ImplementationTaskKind.TEST_IMPLEMENTATION,
        scope=ImplementationScope.TASK,
    )

    assert (
        resolve_verification_policy(
            kind_only
        ).allow_full_suite
        is False
    )
