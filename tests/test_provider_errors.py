"""A provider failure must never kill the CLI without recoverable state.

The LinkVault smoke died on an OpenAI 400 that propagated as an unhandled
exception. Every transport outcome is classified here, and the workflow is
left exactly as it was so the run can simply be relaunched.
"""

from pathlib import Path

import pytest

from ai_factory.project import initialize_project
from ai_factory.provider_errors import (
    ProviderErrorKind,
    ProviderExecutionError,
    kind_for_status_code,
)
from ai_factory.runtime import run_next_agent
from ai_factory.state import load_state


class _Status(Exception):
    """Stands in for an openai APIStatusError with a status code."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


def test_status_codes_map_to_error_kinds() -> None:
    assert kind_for_status_code(400) is ProviderErrorKind.PERMANENT_REQUEST
    assert kind_for_status_code(401) is ProviderErrorKind.PERMANENT_REQUEST
    assert kind_for_status_code(404) is ProviderErrorKind.PERMANENT_REQUEST
    assert kind_for_status_code(422) is ProviderErrorKind.PERMANENT_REQUEST
    assert kind_for_status_code(429) is ProviderErrorKind.RATE_LIMITED
    assert kind_for_status_code(500) is ProviderErrorKind.SERVER_ERROR
    assert kind_for_status_code(503) is ProviderErrorKind.SERVER_ERROR
    assert kind_for_status_code(None) is ProviderErrorKind.UNKNOWN


def test_permanent_request_errors_are_not_retryable() -> None:
    error = ProviderExecutionError(
        kind=ProviderErrorKind.PERMANENT_REQUEST,
        message="rejected",
        status_code=400,
    )

    assert error.retryable is False
    assert error.status_code == 400


@pytest.mark.parametrize(
    "kind",
    [
        ProviderErrorKind.RATE_LIMITED,
        ProviderErrorKind.SERVER_ERROR,
        ProviderErrorKind.NETWORK,
    ],
)
def test_transient_errors_are_retryable(
    kind: ProviderErrorKind,
) -> None:
    assert ProviderExecutionError(
        kind=kind,
        message="transient",
    ).retryable is True


def test_provider_error_is_a_value_error() -> None:
    """The CLI already reports ValueError cleanly, without a traceback."""

    assert issubclass(
        ProviderExecutionError,
        ValueError,
    )


# --------------------------------------------------------------------------
# The OpenAI provider classifies every transport outcome
# --------------------------------------------------------------------------


@pytest.fixture()
def provider(monkeypatch: pytest.MonkeyPatch):
    from ai_factory.openai_provider import OpenAIProvider

    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    return OpenAIProvider(
        model="test-model",
    )


def _raise_on_create(
    monkeypatch: pytest.MonkeyPatch,
    provider,
    error: Exception,
) -> None:
    class Responses:
        def create(self, **kwargs):
            raise error

    class Client:
        responses = Responses()

    monkeypatch.setattr(
        provider,
        "client",
        Client(),
    )


@pytest.mark.parametrize(
    "status_code,expected",
    [
        (400, ProviderErrorKind.PERMANENT_REQUEST),
        (429, ProviderErrorKind.RATE_LIMITED),
        (500, ProviderErrorKind.SERVER_ERROR),
    ],
)
def test_generate_classifies_status_errors(
    provider,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected: ProviderErrorKind,
) -> None:
    import ai_factory.openai_provider as module

    monkeypatch.setattr(
        module,
        "APIStatusError",
        _Status,
    )

    _raise_on_create(
        monkeypatch,
        provider,
        _Status(status_code),
    )

    with pytest.raises(ProviderExecutionError) as captured:
        provider.generate("prompt")

    assert captured.value.kind is expected


def test_generate_classifies_network_errors(
    provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_factory.openai_provider as module

    class FakeConnectionError(Exception):
        pass

    monkeypatch.setattr(
        module,
        "APIConnectionError",
        FakeConnectionError,
    )

    _raise_on_create(
        monkeypatch,
        provider,
        FakeConnectionError("connection reset"),
    )

    with pytest.raises(ProviderExecutionError) as captured:
        provider.generate("prompt")

    assert captured.value.kind is ProviderErrorKind.NETWORK
    assert captured.value.retryable is True


def test_implement_classifies_permanent_request_errors(
    provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_factory.openai_provider as module

    monkeypatch.setattr(
        module,
        "APIStatusError",
        _Status,
    )

    _raise_on_create(
        monkeypatch,
        provider,
        _Status(400),
    )

    with pytest.raises(ProviderExecutionError) as captured:
        provider.implement("prompt")

    assert captured.value.kind is ProviderErrorKind.PERMANENT_REQUEST
    assert captured.value.retryable is False


def test_run_classifies_permanent_request_errors(
    provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_factory.openai_provider as module

    monkeypatch.setattr(
        module,
        "APIStatusError",
        _Status,
    )

    _raise_on_create(
        monkeypatch,
        provider,
        _Status(400),
    )

    with pytest.raises(ProviderExecutionError):
        provider.run(
            {
                "agent_name": "product",
                "contract": "contract",
                "project": {},
                "state": {},
                "artifacts": {},
                "human_input": None,
            }
        )


# --------------------------------------------------------------------------
# The workflow stays recoverable
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        ProviderErrorKind.PERMANENT_REQUEST,
        ProviderErrorKind.RATE_LIMITED,
        ProviderErrorKind.SERVER_ERROR,
        ProviderErrorKind.NETWORK,
    ],
)
def test_workflow_state_is_unchanged_after_a_provider_failure(
    tmp_path: Path,
    kind: ProviderErrorKind,
) -> None:
    project_root = initialize_project(
        "Recovery Probe",
        tmp_path,
    )

    state_path = project_root / ".factory" / "state.yaml"
    before = state_path.read_text(encoding="utf-8")

    class FailingProvider:
        def run(self, context):
            raise ProviderExecutionError(
                kind=kind,
                message="provider unavailable",
            )

    with pytest.raises(ProviderExecutionError):
        run_next_agent(
            project_root=project_root,
            provider=FailingProvider(),
        )

    assert state_path.read_text(encoding="utf-8") == before

    state = load_state(state_path)

    assert state["agents"]["product"]["status"] == "READY"
