ALLOWED_TEST_COMMANDS = {
    "npm test",
    "npm run test",
    "npm run typecheck",
    "npm run build",
    "npm run lint",
    "npm run prisma:validate",
}

ALLOWED_TEST_COMMAND_PREFIXES = (
    "pytest",
    "python -m pytest",
    # Read-only dependency audit used by the Security validator.
    "npm audit",
)

ALLOWED_TARGETED_TEST_COMMAND_PREFIXES = (
    "npm test -- ",
    "npm run test -- ",
)


def validate_test_command(
    command: str,
) -> None:
    """Validate a test or verification command."""

    if not isinstance(command, str) or not command.strip():
        raise ValueError(
            "Test command cannot be empty."
        )

    normalized = command.strip()

    allowed = (
        normalized in ALLOWED_TEST_COMMANDS
        or normalized.startswith(
            ALLOWED_TEST_COMMAND_PREFIXES
        )
        or normalized.startswith(
            ALLOWED_TARGETED_TEST_COMMAND_PREFIXES
        )
    )

    if not allowed:
        raise ValueError(
            f"Test command is not allowed: {command}"
        )

    forbidden_tokens = (
        "&&",
        "||",
        ";",
        "|",
        ">",
        "<",
        "`",
        "$(",
    )

    if any(
        token in normalized
        for token in forbidden_tokens
    ):
        raise ValueError(
            f"Unsafe shell syntax is not allowed in test command: {command}"
        )


def allowed_test_commands(commands: list[str]) -> list[str]:
    """The commands a validator may run; the others are skipped.

    A real QA run declared `python -m convertisseur 100 C F` beside its
    pytest commands, and the policy error stopped the whole step. Only
    allowed commands count as evidence; a validator left with none fails
    its evidence check, which explains itself.
    """

    allowed: list[str] = []

    for command in commands:
        try:
            validate_test_command(command)
        except ValueError:
            continue

        allowed.append(command)

    return allowed
