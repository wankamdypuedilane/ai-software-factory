"""Classification of model-provider transport failures.

Classification is by exception type and HTTP status code only. No message
text is inspected: a provider is free to reword its errors at any time.
"""

from enum import Enum


class ProviderErrorKind(str, Enum):
    """What kind of failure the provider reported."""

    PERMANENT_REQUEST = "PERMANENT_REQUEST"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    NETWORK = "NETWORK"
    UNKNOWN = "UNKNOWN"


RETRYABLE_KINDS = frozenset(
    {
        ProviderErrorKind.RATE_LIMITED,
        ProviderErrorKind.SERVER_ERROR,
        ProviderErrorKind.NETWORK,
    }
)


def kind_for_status_code(
    status_code: int | None,
) -> ProviderErrorKind:
    """Map an HTTP status code to a provider error kind."""

    if status_code is None:
        return ProviderErrorKind.UNKNOWN

    if status_code == 429:
        return ProviderErrorKind.RATE_LIMITED

    if 500 <= status_code < 600:
        return ProviderErrorKind.SERVER_ERROR

    if 400 <= status_code < 500:
        return ProviderErrorKind.PERMANENT_REQUEST

    return ProviderErrorKind.UNKNOWN


class ProviderResultError(ValueError):
    """A provider response did not satisfy the structural result contract.

    The call itself succeeded: a response exists, and it is the response that
    is unusable. Round 11 lost a Developer cycle because this failure was
    indistinguishable from a mistyped command at the CLI, so it is raised as
    its own type, carries the parsing stage it came from, and states that no
    workflow state changed.

    Subclasses ValueError so that no existing caller starts crashing on a
    failure it already handled.
    """

    def __init__(
        self,
        stage: str,
        message: str,
    ) -> None:
        self.stage = stage
        self.recoverable = True

        super().__init__(
            f"[PROVIDER_RESULT:{stage}] {message} "
            "The workflow state is unchanged; nothing from this response was "
            "applied. Relaunch the run to request a new response."
        )


class ProviderExecutionError(ValueError):
    """A provider call failed.

    Subclasses ValueError so that every existing caller keeps reporting it
    as a handled command failure rather than an unhandled crash.
    """

    def __init__(
        self,
        kind: ProviderErrorKind,
        message: str,
        status_code: int | None = None,
    ) -> None:
        self.kind = kind
        self.status_code = status_code
        self.retryable = kind in RETRYABLE_KINDS

        recovery = (
            "The workflow state is unchanged; relaunch the run."
            if self.retryable
            else "The workflow state is unchanged; the request must change "
            "before relaunching."
        )

        super().__init__(
            f"[{kind.value}] {message} {recovery}"
        )
