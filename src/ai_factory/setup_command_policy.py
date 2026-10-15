from ai_factory.native_dependency_policy import (
    is_native_preparation_command,
)


ALLOWED_SETUP_COMMANDS = {
    "npm install --ignore-scripts",
    "npm ci --ignore-scripts",
    "npm run prisma:generate",
}


def validate_setup_command(
    command: str,
    approved_native_packages: tuple[str, ...] | list[str] = (),
) -> None:
    """Validate a dependency setup command.

    `approved_native_packages` is the permission the Factory carries for
    this project, read from its configuration. It defaults to nothing, so a
    caller that does not hold the permission cannot run a preparation
    command, and no agent-facing path ever supplies it.
    """

    if (
        not isinstance(command, str)
        or not command.strip()
    ):
        raise ValueError(
            "Setup command is not allowed: "
            f"{command}"
        )

    normalized = command.strip()

    if normalized in ALLOWED_SETUP_COMMANDS:
        return

    if is_native_preparation_command(
        normalized,
        approved_native_packages,
    ):
        return

    raise ValueError(
        "Setup command is not allowed: "
        f"{command}"
    )
