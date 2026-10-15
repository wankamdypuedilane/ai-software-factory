from pathlib import Path

import pytest

from ai_factory.agent_result import (
    AgentImplementationRequest,
    AgentResult,
)
from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
    VerificationPolicy,
)
from ai_factory.implementation_request import (
    ImplementationTask,
    build_implementation_tasks,
)
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)
from ai_factory.implementation_runtime import (
    resolve_verification_policy,
    run_implementation_task,
)
from ai_factory.result_application import (
    apply_agent_result,
)
from ai_factory.test_runner import (
    CommandExecutionResult,
)


class SequencedProvider:
    def __init__(
        self,
        results: list[ImplementationResult],
    ) -> None:
        self.pending = list(results)
        self.prompts: list[str] = []

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        self.prompts.append(prompt)

        if not self.pending:
            raise AssertionError(
                "Provider was called more times than expected."
            )

        return self.pending.pop(0)


def _stub_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    executed: list[str] = []

    def fake_run(**kwargs):
        executed.append(kwargs["command"])

        return CommandExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        fake_run,
    )

    return executed


def _result(
    task_id: str,
    tests: list[str],
) -> ImplementationResult:
    return ImplementationResult(
        task_id=task_id,
        summary="Unit implemented.",
        files=[
            ImplementationFileChange(
                path="src/modules/search/search.test.ts",
                content="// tests\n",
            ),
        ],
        tests=tests,
    )


# --------------------------------------------------------------------------
# Policy resolution
# --------------------------------------------------------------------------


def test_declared_policy_is_authoritative_over_the_title() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="ACME-DEV-FULL-NAME-FIELD-TESTS",
        title="Full name field tests",
        purpose=(
            "Add full end-to-end integration tests verifying the "
            "complete project."
        ),
        kind=ImplementationTaskKind.TEST_IMPLEMENTATION,
        scope=ImplementationScope.TASK,
        verification=VerificationPolicy(
            allow_full_suite=False,
            baseline_required=True,
        ),
    )

    policy = resolve_verification_policy(task)

    assert policy.allow_full_suite is False
    assert policy.baseline_required is True


def test_declared_verification_unit_allows_the_full_suite() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="ACME-DEV-FINAL-MVP-VERIFICATION",
        title="Final MVP verification",
        purpose="Validate the delivered increment.",
        kind=ImplementationTaskKind.VERIFICATION,
        scope=ImplementationScope.PROJECT,
        verification=VerificationPolicy(
            allow_full_suite=True,
            baseline_required=False,
        ),
    )

    policy = resolve_verification_policy(task)

    assert policy.allow_full_suite is True
    assert policy.baseline_required is False


def test_policy_is_derived_from_kind_when_not_declared() -> None:
    def policy_for(
        kind: ImplementationTaskKind,
        scope: ImplementationScope,
    ) -> VerificationPolicy:
        return resolve_verification_policy(
            ImplementationTask(
                agent_name="developer",
                id="ACME-DEV-UNIT",
                title="Neutral title",
                purpose="Neutral purpose.",
                kind=kind,
                scope=scope,
            )
        )

    assert policy_for(
        ImplementationTaskKind.IMPLEMENTATION,
        ImplementationScope.TASK,
    ) == VerificationPolicy(
        allow_full_suite=False,
        baseline_required=True,
    )

    assert policy_for(
        ImplementationTaskKind.TEST_IMPLEMENTATION,
        ImplementationScope.TASK,
    ) == VerificationPolicy(
        allow_full_suite=False,
        baseline_required=True,
    )

    assert policy_for(
        ImplementationTaskKind.VERIFICATION,
        ImplementationScope.PROJECT,
    ) == VerificationPolicy(
        allow_full_suite=True,
        baseline_required=False,
    )

    # A verification unit narrowed to a single task stays intermediate.
    assert policy_for(
        ImplementationTaskKind.VERIFICATION,
        ImplementationScope.TASK,
    ) == VerificationPolicy(
        allow_full_suite=False,
        baseline_required=True,
    )


def test_legacy_task_without_contract_keeps_previous_behaviour() -> None:
    intermediate = resolve_verification_policy(
        ImplementationTask(
            agent_name="developer",
            id="ACME-DEV-TASK-REPOSITORY",
            title="Task repository",
            purpose="Implement the task repository.",
        )
    )

    assert intermediate.allow_full_suite is False
    assert intermediate.baseline_required is True

    legacy_verification = resolve_verification_policy(
        ImplementationTask(
            agent_name="developer",
            id="ACME-DEV-FULL-VERIFICATION",
            title="Full verification",
            purpose="Run the full project verification suite.",
        )
    )

    assert legacy_verification.allow_full_suite is True
    assert legacy_verification.baseline_required is False


# --------------------------------------------------------------------------
# Test-scope policy
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "task_id,title",
    [
        (
            "ACME-DEV-FULL-NAME-FIELD-TESTS",
            "Full name field tests",
        ),
        (
            "ACME-DEV-GLOBAL-SEARCH-TESTS",
            "Global search tests",
        ),
    ],
)
def test_declared_intermediate_unit_is_reprompted_for_a_global_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    task_id: str,
    title: str,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id=task_id,
        title=title,
        purpose="Add the tests for this unit.",
        kind=ImplementationTaskKind.TEST_IMPLEMENTATION,
        scope=ImplementationScope.TASK,
        verification=VerificationPolicy(
            allow_full_suite=False,
            baseline_required=True,
        ),
    )

    targeted = (
        "npm test -- src/modules/search/search.test.ts"
    )

    provider = SequencedProvider(
        [
            _result(task.id, ["npm test"]),
            _result(task.id, [targeted]),
        ]
    )

    _stub_tests(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 2
    assert "## Required Corrections" in provider.prompts[1]
    assert execution.result.tests == [targeted]


def test_declared_project_verification_runs_the_full_suite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="ACME-DEV-FINAL-MVP-VERIFICATION",
        title="Final MVP verification",
        purpose="Validate the delivered increment.",
        kind=ImplementationTaskKind.VERIFICATION,
        scope=ImplementationScope.PROJECT,
        verification=VerificationPolicy(
            allow_full_suite=True,
            baseline_required=False,
        ),
    )

    provider = SequencedProvider(
        [
            _result(task.id, ["npm test"]),
        ]
    )

    _stub_tests(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 1
    assert "## Required Corrections" not in provider.prompts[0]
    assert execution.result.tests == ["npm test"]


def test_verification_title_cannot_unlock_a_declared_intermediate_unit(
    tmp_path: Path,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="ACME-DEV-FULL-FINAL-GLOBAL-E2E-VERIFICATION",
        title="Full final global e2e verification tests",
        purpose="Run the entire project regression suite.",
        kind=ImplementationTaskKind.TEST_IMPLEMENTATION,
        scope=ImplementationScope.TASK,
        verification=VerificationPolicy(
            allow_full_suite=False,
            baseline_required=True,
        ),
    )

    provider = SequencedProvider(
        [
            _result(task.id, ["npm test"]),
            _result(task.id, ["npm run test"]),
        ]
    )

    with pytest.raises(
        ValueError,
        match="Full-project test suite is not allowed",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=task,
            context={},
            provider=provider,
        )


# --------------------------------------------------------------------------
# Baseline policy
# --------------------------------------------------------------------------


def test_test_implementation_unit_captures_a_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="ACME-DEV-SEARCH-TESTS",
        title="Search tests",
        purpose="Add the search tests.",
        kind=ImplementationTaskKind.TEST_IMPLEMENTATION,
        scope=ImplementationScope.TASK,
    )

    targeted = (
        "npm test -- src/modules/search/search.test.ts"
    )

    provider = SequencedProvider(
        [
            _result(task.id, [targeted]),
        ]
    )

    executed = _stub_tests(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert [
        item.command
        for item in execution.baseline_test_results
    ] == [targeted]

    assert executed == [
        targeted,
        targeted,
    ]


def test_verification_unit_without_baseline_does_not_capture_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="ACME-DEV-FINAL-MVP-VERIFICATION",
        title="Final MVP verification",
        purpose="Validate the delivered increment.",
        kind=ImplementationTaskKind.VERIFICATION,
        scope=ImplementationScope.PROJECT,
        verification=VerificationPolicy(
            allow_full_suite=True,
            baseline_required=False,
        ),
    )

    provider = SequencedProvider(
        [
            _result(task.id, ["npm test"]),
        ]
    )

    executed = _stub_tests(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert execution.baseline_test_results == []
    assert executed == ["npm test"]


# --------------------------------------------------------------------------
# Propagation and serialization
# --------------------------------------------------------------------------


def test_build_implementation_tasks_propagates_the_contract() -> None:
    tasks = build_implementation_tasks(
        agent_name="developer",
        requests=[
            AgentImplementationRequest(
                id="ACME-DEV-SEARCH-TESTS",
                title="Search tests",
                purpose="Add the search tests.",
                kind=ImplementationTaskKind.TEST_IMPLEMENTATION,
                scope=ImplementationScope.TASK,
                verification=VerificationPolicy(
                    allow_full_suite=False,
                    baseline_required=True,
                ),
            ),
        ],
    )

    assert tasks[0].kind is ImplementationTaskKind.TEST_IMPLEMENTATION
    assert tasks[0].scope is ImplementationScope.TASK
    assert tasks[0].verification == VerificationPolicy(
        allow_full_suite=False,
        baseline_required=True,
    )


def test_state_serialization_preserves_the_contract() -> None:
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
        AgentResult(
            status="COMPLETED",
            summary="Planned.",
            implementation_requests=[
                AgentImplementationRequest(
                    id="ACME-DEV-FINAL-MVP-VERIFICATION",
                    title="Final MVP verification",
                    purpose="Validate the increment.",
                    kind=ImplementationTaskKind.VERIFICATION,
                    scope=ImplementationScope.PROJECT,
                    verification=VerificationPolicy(
                        allow_full_suite=True,
                        baseline_required=False,
                    ),
                ),
            ],
        ),
    )

    stored = (
        state["agents"]["developer"]["last_result"]
        ["implementation_requests"][0]
    )

    assert stored == {
        "id": "ACME-DEV-FINAL-MVP-VERIFICATION",
        "title": "Final MVP verification",
        "purpose": "Validate the increment.",
        "kind": "VERIFICATION",
        "scope": "PROJECT",
        "verification": {
            "allow_full_suite": True,
            "baseline_required": False,
        },
    }


def test_state_serialization_omits_an_undeclared_contract() -> None:
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
        AgentResult(
            status="COMPLETED",
            summary="Planned.",
            implementation_requests=[
                AgentImplementationRequest(
                    id="ACME-DEV-LEGACY",
                    title="Legacy unit",
                    purpose="Implement it.",
                ),
            ],
        ),
    )

    stored = (
        state["agents"]["developer"]["last_result"]
        ["implementation_requests"][0]
    )

    assert stored == {
        "id": "ACME-DEV-LEGACY",
        "title": "Legacy unit",
        "purpose": "Implement it.",
    }


def test_retry_context_restores_the_contract_from_state() -> None:
    from ai_factory.implementation_retry import (
        build_implementation_retry_context,
    )

    context = build_implementation_retry_context(
        {
            "agents": {
                "developer": {
                    "status": "FAILED",
                    "last_result": {
                        "failed_task_id": "ACME-DEV-SEARCH-TESTS",
                        "implementation_requests": [
                            {
                                "id": "ACME-DEV-SEARCH-TESTS",
                                "title": "Search tests",
                                "purpose": "Add the search tests.",
                                "kind": "TEST_IMPLEMENTATION",
                                "scope": "TASK",
                                "verification": {
                                    "allow_full_suite": False,
                                    "baseline_required": True,
                                },
                            }
                        ],
                        "test_results": [],
                    },
                }
            }
        }
    )

    assert (
        context.task.kind
        is ImplementationTaskKind.TEST_IMPLEMENTATION
    )
    assert context.task.scope is ImplementationScope.TASK
    assert context.task.verification == VerificationPolicy(
        allow_full_suite=False,
        baseline_required=True,
    )
