import pytest

from ai_factory.setup_command_policy import (
    validate_setup_command,
)


def test_validate_setup_command_accepts_safe_npm_install() -> None:
    validate_setup_command(
        "npm install --ignore-scripts"
    )


def test_validate_setup_command_accepts_safe_npm_ci() -> None:
    validate_setup_command(
        "npm ci --ignore-scripts"
    )


def test_validate_setup_command_accepts_prisma_generate() -> None:
    validate_setup_command(
        "npm run prisma:generate"
    )


@pytest.mark.parametrize(
    "command",
    [
        "npm install",
        "npm ci",
        "npm install express",
        "npm install --ignore-scripts && echo hacked",
        "npm install --ignore-scripts; echo hacked",
        "powershell something.ps1",
    ],
)
def test_validate_setup_command_rejects_unsafe_commands(
    command: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="Setup command is not allowed",
    ):
        validate_setup_command(
            command
        )
