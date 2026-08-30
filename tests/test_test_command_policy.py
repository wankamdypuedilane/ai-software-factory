import pytest

from ai_factory.test_command_policy import (
    validate_test_command,
)


def test_validate_test_command_accepts_pytest_commands() -> None:
    validate_test_command(
        "pytest"
    )

    validate_test_command(
        "pytest tests/test_auth.py"
    )

    validate_test_command(
        "python -m pytest tests/test_api.py"
    )


def test_validate_test_command_accepts_npm_test_commands() -> None:
    validate_test_command(
        "npm test"
    )

    validate_test_command(
        "npm run test"
    )


def test_validate_test_command_rejects_empty_command() -> None:
    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        validate_test_command(
            "   "
        )


def test_validate_test_command_rejects_unknown_command() -> None:
    with pytest.raises(
        ValueError,
        match="is not allowed",
    ):
        validate_test_command(
            "python app.py"
        )


@pytest.mark.parametrize(
    "command",
    [
        "pytest && del file.txt",
        "pytest || echo failed",
        "pytest; echo done",
        "pytest | more",
        "pytest > output.txt",
        "pytest < input.txt",
        "pytest `whoami`",
        "pytest $(whoami)",
    ],
)
def test_validate_test_command_rejects_unsafe_shell_syntax(
    command: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="Unsafe shell syntax",
    ):
        validate_test_command(
            command
        )
