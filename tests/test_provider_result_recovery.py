"""A schema-valid response must never terminate the workflow.

LinkVault round 11 died because the Developer returned a blocker declaring
EXTERNAL_DEPENDENCY together with fixable_by_agent=True. The published strict
JSON schema allows that combination - it has no cross-field constraint - and
the very next line of the parser normalizes it to non-blocking. Validation
raised anyway, the ValueError reached argparse, and one provider call was
lost to a message that looked like an operator typing mistake.

The model may propose blocker semantics. The Factory decides authority. A
combination the Factory can resolve deterministically is normalized, never
fatal.
"""

import itertools
import json
from pathlib import Path

import pytest

from ai_factory.blocker_contract import (
    BLOCKER_KIND_VALUES,
    BLOCKER_SCOPE_VALUES,
    BlockerKind,
    blocking_blockers,
    coerce_blockers,
    is_effectively_blocking,
    normalize_blockers,
    validate_declared_blockers,
)
from ai_factory.openai_provider import OpenAIProvider
from ai_factory.provider_errors import (
    ProviderExecutionError,
    ProviderResultError,
)
from ai_factory.state import load_state, save_state


# The exact payload the Developer returned in round 11.
ROUND_11_MESSAGE = (
    "The Argon2id focused test cannot load the installed native argon2 "
    "binding; the dependency installation or native build environment "
    "requires repair or rebuild."
)

ROUND_11_BLOCKER = {
    "message": ROUND_11_MESSAGE,
    "kind": "EXTERNAL_DEPENDENCY",
    "scope": "EXTERNAL",
    "fixable_by_agent": True,
    "requires_human_input": False,
    "blocking": True,
}


def _agent_payload(blockers: list[dict]) -> str:
    return json.dumps(
        {
            "status": "BLOCKED",
            "summary": "Password hashing unit could not be verified.",
            "artifacts": [],
            "artifact_requests": [],
            "implementation_requests": [],
            "questions": [],
            "blockers": blockers,
            "handoff": None,
            "metadata": {},
        }
    )


# --------------------------------------------------------------------------
# The round-11 payload is normalizable, not fatal
# --------------------------------------------------------------------------


def test_the_round_11_blocker_payload_does_not_raise() -> None:
    validate_declared_blockers([ROUND_11_BLOCKER])


def test_a_fixable_external_dependency_is_accepted_then_demoted() -> None:
    validate_declared_blockers([ROUND_11_BLOCKER])

    normalized, _ = normalize_blockers(
        coerce_blockers([ROUND_11_BLOCKER])
    )

    assert normalized[0].blocking is False
    assert is_effectively_blocking(normalized[0]) is False
    assert blocking_blockers(normalized) == []


def test_the_diagnostic_message_survives_normalization() -> None:
    normalized, _ = normalize_blockers(
        coerce_blockers([ROUND_11_BLOCKER])
    )

    assert normalized[0].message == ROUND_11_MESSAGE
    assert normalized[0].kind is BlockerKind.EXTERNAL_DEPENDENCY


def test_the_round_11_response_parses_into_a_usable_agent_result() -> None:
    """Parsing must succeed and leave the Developer free to keep working."""

    result = OpenAIProvider._parse_result(
        None,
        _agent_payload([ROUND_11_BLOCKER]),
    )

    assert blocking_blockers(result.blockers) == []
    assert result.blockers[0].message == ROUND_11_MESSAGE


# --------------------------------------------------------------------------
# Authority is unchanged: normalization never promotes anything
# --------------------------------------------------------------------------


def test_a_genuine_unfixable_external_dependency_still_blocks() -> None:
    payload = {
        **ROUND_11_BLOCKER,
        "message": "The payment sandbox credentials are unavailable.",
        "fixable_by_agent": False,
        "requires_human_input": True,
    }

    validate_declared_blockers([payload])

    normalized, _ = normalize_blockers(
        coerce_blockers([payload])
    )

    assert [b.message for b in blocking_blockers(normalized)] == [
        "The payment sandbox credentials are unavailable.",
    ]


def test_a_local_defect_cannot_become_an_effective_external_blocker() -> None:
    payload = {
        "message": "The generated route file must be corrected.",
        "kind": "LOCAL_DEFECT",
        "scope": "EXTERNAL",
        "fixable_by_agent": False,
        "requires_human_input": True,
        "blocking": True,
    }

    validate_declared_blockers([payload])

    normalized, _ = normalize_blockers(
        coerce_blockers([payload])
    )

    assert blocking_blockers(normalized) == []


def test_a_human_decision_remains_non_blocking_and_becomes_a_question() -> None:
    payload = {
        "message": "Which brand colours should be used?",
        "kind": "HUMAN_DECISION",
        "scope": "PROJECT",
        "fixable_by_agent": False,
        "requires_human_input": True,
        "blocking": True,
    }

    validate_declared_blockers([payload])

    normalized, questions = normalize_blockers(
        coerce_blockers([payload])
    )

    assert blocking_blockers(normalized) == []
    assert questions == ["Which brand colours should be used?"]


# --------------------------------------------------------------------------
# Structural invalidity is still refused
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "Human approval is required.",
        {"kind": "EXTERNAL_DEPENDENCY", "scope": "EXTERNAL"},
        {"message": "   ", "kind": "EXTERNAL_DEPENDENCY", "scope": "EXTERNAL"},
        {"message": "x", "kind": "MADE_UP", "scope": "EXTERNAL"},
        {"message": "x", "kind": "EXTERNAL_DEPENDENCY", "scope": "NOWHERE"},
    ],
)
def test_a_structurally_invalid_blocker_is_still_rejected(payload) -> None:
    with pytest.raises(ValueError):
        validate_declared_blockers([payload])


def test_blockers_must_be_a_list() -> None:
    with pytest.raises(ValueError):
        validate_declared_blockers(
            {"message": "not a list"}
        )


# --------------------------------------------------------------------------
# Schema and runtime must accept exactly the same combinations
# --------------------------------------------------------------------------


def test_every_schema_valid_blocker_combination_is_accepted() -> None:
    """No cross-field rule may exist that the published schema cannot express.

    The strict JSON schema constrains kind and scope by enum and the three
    flags by type only. Every product of those is therefore a response the
    Factory told the model it could return.
    """

    combinations = itertools.product(
        BLOCKER_KIND_VALUES,
        BLOCKER_SCOPE_VALUES,
        (True, False),
        (True, False),
        (True, False),
    )

    for kind, scope, fixable, human, blocking in combinations:
        payload = {
            "message": "Declared impediment.",
            "kind": kind,
            "scope": scope,
            "fixable_by_agent": fixable,
            "requires_human_input": human,
            "blocking": blocking,
        }

        validate_declared_blockers([payload])

        normalized, _ = normalize_blockers(
            coerce_blockers([payload])
        )

        expected = (
            kind == BlockerKind.EXTERNAL_DEPENDENCY.value
            and blocking
            and not fixable
        )

        assert bool(blocking_blockers(normalized)) is expected


def test_normalization_never_promotes_a_blocker(tmp_path: Path) -> None:
    """Accepting more combinations must not make more of them blocking.

    Demotion is the only direction the contract allows, so a response can
    never gain authority by being normalized rather than refused.
    """

    combinations = itertools.product(
        BLOCKER_KIND_VALUES,
        BLOCKER_SCOPE_VALUES,
        (True, False),
        (True, False),
        (True, False),
    )

    for kind, scope, fixable, human, blocking in combinations:
        declared = coerce_blockers(
            [
                {
                    "message": "Declared impediment.",
                    "kind": kind,
                    "scope": scope,
                    "fixable_by_agent": fixable,
                    "requires_human_input": human,
                    "blocking": blocking,
                }
            ]
        )

        normalized, _ = normalize_blockers(declared)

        assert normalized[0].blocking <= declared[0].blocking
        assert normalized[0].kind is declared[0].kind
        assert normalized[0].fixable_by_agent == declared[0].fixable_by_agent


# --------------------------------------------------------------------------
# A genuinely invalid response fails as a provider-result failure
# --------------------------------------------------------------------------


def test_an_invalid_provider_result_raises_a_provider_result_error() -> None:
    with pytest.raises(ProviderResultError) as error:
        OpenAIProvider._parse_result(
            None,
            "not json at all",
        )

    assert error.value.stage == "agent_result"
    assert "workflow state is unchanged" in str(error.value).lower()


def test_a_provider_result_error_is_attributable_and_recoverable() -> None:
    error = ProviderResultError(
        stage="agent_result",
        message="Agent result summary is required.",
    )

    assert isinstance(error, ValueError)
    assert not isinstance(error, ProviderExecutionError)
    assert "PROVIDER_RESULT" in str(error)
    assert error.recoverable is True


def test_a_malformed_blocker_still_fails_as_a_provider_result_error() -> None:
    with pytest.raises(ProviderResultError):
        OpenAIProvider._parse_result(
            None,
            _agent_payload(["prose blocker"]),
        )


# --------------------------------------------------------------------------
# The CLI never reports a provider-result failure as operator misuse
# --------------------------------------------------------------------------


def _workflow_project(root: Path) -> None:
    save_state(
        root / ".factory" / "state.yaml",
        {
            "project": {"name": "Test Project", "phase": "discovery"},
            "agents": {
                "product": {"status": "READY"},
                "ux_ui": {"status": "NOT_STARTED"},
                "architect": {"status": "NOT_STARTED"},
                "developer": {"status": "NOT_STARTED"},
                "qa": {"status": "NOT_STARTED"},
                "security": {"status": "NOT_STARTED"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
            },
        },
    )

    save_state(
        root / ".factory" / "project.yaml",
        {
            "schema_version": 1,
            "project": {"name": "Test Project", "type": "test"},
            "context": {"agents": {"product": []}},
            "ai": {
                "provider": "mock",
                "model": None,
                "settings": {
                    "temperature": None,
                    "max_output_tokens": None,
                },
            },
        },
    )


def test_a_provider_result_failure_is_not_an_argparse_usage_error(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Round 11 printed the CLI usage banner. It must never do that again."""

    from ai_factory import cli

    _workflow_project(tmp_path)

    state_path = tmp_path / ".factory" / "state.yaml"
    before = state_path.read_bytes()

    def failing_workflow(**kwargs):
        raise ProviderResultError(
            stage="agent_result",
            message="Blocker message is required.",
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "run_workflow", failing_workflow)
    monkeypatch.setattr(
        "sys.argv",
        ["ai-factory", "run-workflow"],
    )

    with pytest.raises(SystemExit) as exit_error:
        cli.main()

    captured = capsys.readouterr()
    combined = captured.out + captured.err

    assert exit_error.value.code != 2
    assert "usage: ai-factory" not in combined
    assert "PROVIDER_RESULT" in combined

    # Nothing was applied on the way to the failure.
    assert state_path.read_bytes() == before


def test_no_provider_response_is_applied_before_validation_succeeds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A response that fails structural validation leaves no trace."""

    from ai_factory import cli

    _workflow_project(tmp_path)

    state_path = tmp_path / ".factory" / "state.yaml"
    before = load_state(state_path)

    class InvalidProvider:
        def run(self, prompt: str):
            return OpenAIProvider._parse_result(
                None,
                _agent_payload(["prose blocker"]),
            )

        def generate(self, prompt: str) -> str:  # pragma: no cover
            raise AssertionError(
                "no artifact may be generated from an invalid result"
            )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "create_provider",
        lambda config: InvalidProvider(),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["ai-factory", "run-workflow"],
    )

    with pytest.raises(SystemExit):
        cli.main()

    assert load_state(state_path) == before

    knowledge = tmp_path / "knowledge"

    assert not knowledge.exists() or not any(knowledge.rglob("*.md"))


def test_a_provider_result_failure_never_becomes_a_successful_unit(
    tmp_path: Path,
) -> None:
    """The new exception type must not be swallowed into a false success."""

    from ai_factory.implementation_request import ImplementationTask
    from ai_factory.implementation_runtime import run_implementation_task

    class FailingProvider:
        def implement(self, prompt: str):
            raise ProviderResultError(
                stage="implementation_result",
                message="Implementation result task ID is required.",
            )

    with pytest.raises(ProviderResultError):
        run_implementation_task(
            project_root=tmp_path,
            task=ImplementationTask(
                agent_name="developer",
                id="TASK-001",
                title="Password hashing",
                purpose="Hash passwords.",
            ),
            context={},
            provider=FailingProvider(),
        )

    assert not any(tmp_path.rglob("*.ts"))


@pytest.mark.parametrize(
    "message",
    [
        "NON_CONVERGING_IMPLEMENTATION: two consecutive Developer cycles "
        "produced the same failure.",
        "OpenAI implementation response was incomplete. "
        "Details: IncompleteDetails(reason='max_output_tokens').",
    ],
)
def test_a_workflow_stop_is_not_an_argparse_usage_error(
    tmp_path: Path,
    monkeypatch,
    capsys,
    message: str,
) -> None:
    """A real run printed the usage banner for both of these stops."""

    from ai_factory import cli

    _workflow_project(tmp_path)

    def stopping_workflow(**kwargs):
        raise ValueError(message)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "run_workflow", stopping_workflow)
    monkeypatch.setattr(
        "sys.argv",
        ["ai-factory", "run-workflow"],
    )

    with pytest.raises(SystemExit) as exit_error:
        cli.main()

    captured = capsys.readouterr()

    assert exit_error.value.code == cli.WORKFLOW_STOP_EXIT_CODE
    assert "usage: ai-factory" not in captured.out + captured.err
    assert f"Workflow stopped: {message}" in captured.err
    assert "ai-factory status" in captured.err
