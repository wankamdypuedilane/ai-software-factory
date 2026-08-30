ALLOWED_TEST_COMMAND_PREFIXES = (
    "pytest",
    "python -m pytest",
    "npm test",
    "npm run test",
)


def validate_test_command(
    command: str,
) -> None:
    """Validate a test command declared by an implementation result."""

    if not isinstance(command, str) or not command.strip():
        raise ValueError(
            "Test command cannot be empty."
        )

    normalized = command.strip()

    if not normalized.startswith(
        ALLOWED_TEST_COMMAND_PREFIXES
    ):
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
