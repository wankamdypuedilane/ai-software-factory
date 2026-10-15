"""An over-claimed execution contract is clamped, not fatal.

Same defect class as the round-11 blocker: the published response schema
declares kind, scope and verification.allow_full_suite as independent fields
and cannot express the rule that ties them together, so a model returning a
schema-valid combination terminated the run. The rule itself is sound - a
narrow unit must never run the whole suite - so the Factory keeps enforcing
it, by reducing the declared policy to what kind and scope permit.

Clamping is strictly more restrictive than the declaration, so nothing can
gain authority by being normalized instead of refused.
"""

import json

import pytest

from ai_factory.agent_result import AgentImplementationRequest
from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
    VerificationPolicy,
    clamp_verification_policy,
    validate_declared_contract,
)
from ai_factory.implementation_request import ImplementationTask
from ai_factory.implementation_result import ImplementationResult
from ai_factory.implementation_runtime import (
    resolve_verification_policy,
    run_implementation_task,
)
from ai_factory.openai_provider import OpenAIProvider
from ai_factory.provider_errors import ProviderResultError


FULL_SUITE = VerificationPolicy(
    allow_full_suite=True,
    baseline_required=False,
)


# --------------------------------------------------------------------------
# The clamp
# --------------------------------------------------------------------------


def test_a_project_verification_unit_keeps_the_full_suite() -> None:
    assert clamp_verification_policy(
        kind=ImplementationTaskKind.VERIFICATION,
        scope=ImplementationScope.PROJECT,
        verification=FULL_SUITE,
    ) == FULL_SUITE


@pytest.mark.parametrize(
    ("kind", "scope"),
    [
        (ImplementationTaskKind.IMPLEMENTATION, ImplementationScope.TASK),
        (ImplementationTaskKind.IMPLEMENTATION, ImplementationScope.PROJECT),
        (ImplementationTaskKind.TEST_IMPLEMENTATION, ImplementationScope.TASK),
        (ImplementationTaskKind.VERIFICATION, ImplementationScope.TASK),
    ],
)
def test_a_narrower_unit_is_clamped_not_refused(kind, scope) -> None:
    clamped = clamp_verification_policy(
        kind=kind,
        scope=scope,
        verification=FULL_SUITE,
    )

    assert clamped.allow_full_suite is False
    assert clamped.baseline_required is FULL_SUITE.baseline_required


def test_clamping_never_grants_the_full_suite() -> None:
    """The clamp only ever removes authority."""

    for kind in ImplementationTaskKind:
        for scope in ImplementationScope:
            for allow in (True, False):
                declared = VerificationPolicy(
                    allow_full_suite=allow,
                    baseline_required=True,
                )

                clamped = clamp_verification_policy(
                    kind=kind,
                    scope=scope,
                    verification=declared,
                )

                assert clamped.allow_full_suite <= declared.allow_full_suite


def test_an_undeclared_policy_is_left_alone() -> None:
    assert clamp_verification_policy(
        kind=None,
        scope=None,
        verification=None,
    ) is None


# --------------------------------------------------------------------------
# The producer boundary still refuses what it cannot interpret
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "scope", "verification"),
    [
        (None, ImplementationScope.TASK, FULL_SUITE),
        (ImplementationTaskKind.IMPLEMENTATION, None, FULL_SUITE),
        (ImplementationTaskKind.IMPLEMENTATION, ImplementationScope.TASK, None),
    ],
)
def test_a_missing_contract_field_is_still_refused(
    kind,
    scope,
    verification,
) -> None:
    with pytest.raises(ValueError, match="must declare"):
        validate_declared_contract(
            AgentImplementationRequest(
                id="ACME-DEV-CART",
                title="Cart repository",
                purpose="Implement the cart repository.",
                kind=kind,
                scope=scope,
                verification=verification,
            )
        )


def test_an_over_claimed_contract_no_longer_raises() -> None:
    validate_declared_contract(
        AgentImplementationRequest(
            id="ACME-DEV-CART",
            title="Cart repository",
            purpose="Implement the cart repository.",
            kind=ImplementationTaskKind.IMPLEMENTATION,
            scope=ImplementationScope.TASK,
            verification=FULL_SUITE,
        )
    )


# --------------------------------------------------------------------------
# The response survives, and the unit still cannot run the whole suite
# --------------------------------------------------------------------------


def _agent_payload(kind: str, scope: str) -> str:
    return json.dumps(
        {
            "status": "COMPLETED",
            "summary": "Implementation planned.",
            "artifacts": [],
            "artifact_requests": [],
            "implementation_requests": [
                {
                    "id": "ACME-DEV-CART",
                    "title": "Cart repository",
                    "purpose": "Implement the cart repository.",
                    "kind": kind,
                    "scope": scope,
                    "verification": {
                        "allow_full_suite": True,
                        "baseline_required": False,
                    },
                }
            ],
            "questions": [],
            "blockers": [],
            "handoff": None,
            "metadata": {},
        }
    )


def test_an_over_claimed_response_parses_and_is_clamped() -> None:
    result = OpenAIProvider._parse_result(
        None,
        _agent_payload("IMPLEMENTATION", "TASK"),
    )

    request = result.implementation_requests[0]

    assert request.verification.allow_full_suite is False
    assert request.kind is ImplementationTaskKind.IMPLEMENTATION
    assert request.scope is ImplementationScope.TASK


def test_a_project_verification_response_keeps_the_full_suite() -> None:
    result = OpenAIProvider._parse_result(
        None,
        _agent_payload("VERIFICATION", "PROJECT"),
    )

    assert result.implementation_requests[0].verification.allow_full_suite


def test_a_response_with_an_unknown_kind_still_fails_attributably() -> None:
    with pytest.raises(ProviderResultError):
        OpenAIProvider._parse_result(
            None,
            _agent_payload("MADE_UP", "TASK"),
        )


class _Provider:
    def __init__(self, result: ImplementationResult) -> None:
        self.result = result
        self.prompts: list[str] = []

    def implement(self, prompt: str) -> ImplementationResult:
        self.prompts.append(prompt)
        return self.result


def test_a_clamped_unit_is_still_refused_the_full_suite(tmp_path) -> None:
    """The protection the raise provided is intact after clamping."""

    task = ImplementationTask(
        agent_name="developer",
        id="ACME-DEV-CART",
        title="Cart repository",
        purpose="Implement the cart repository.",
        kind=ImplementationTaskKind.IMPLEMENTATION,
        scope=ImplementationScope.TASK,
        verification=clamp_verification_policy(
            kind=ImplementationTaskKind.IMPLEMENTATION,
            scope=ImplementationScope.TASK,
            verification=FULL_SUITE,
        ),
    )

    assert resolve_verification_policy(task).allow_full_suite is False

    provider = _Provider(
        ImplementationResult(
            task_id=task.id,
            summary="Cart repository implemented.",
            tests=["npm test"],
        )
    )

    with pytest.raises(ValueError, match="Full-project test suite"):
        run_implementation_task(
            project_root=tmp_path,
            task=task,
            context={},
            provider=provider,
        )
