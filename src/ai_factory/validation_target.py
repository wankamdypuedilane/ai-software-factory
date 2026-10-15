"""What a targeted verification command actually validates.

A validation command earns its authority from having executed something. Round
13 promoted a unit whose declared `npm test -- src/auth/routes.test.ts` had no
such file before or after it ran: both executions failed identically, and the
baseline-equivalence rule - written for a real test that was already failing -
read the pair as a pre-existing condition the unit had not worsened.

The target is therefore established structurally, from the command grammar the
Factory already publishes and from the transaction filesystem. No framework
output is parsed: "No test files found" is Vitest prose, and Jest, pytest and
every future runner word it differently.
"""

from pathlib import Path

from ai_factory.test_command_policy import (
    ALLOWED_TARGETED_TEST_COMMAND_PREFIXES,
    ALLOWED_TEST_COMMAND_PREFIXES,
)


# A token is only read as a validation target when it is shaped like a path.
# Anything else - a Vitest name filter, a pytest keyword expression - is left
# alone: refusing to guess is what keeps this from inventing failures.
TARGET_PATH_SUFFIXES = (
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".py",
)

# pytest addresses a case inside a file with `path::node`. The file is the
# part that has to exist.
PYTEST_NODE_SEPARATOR = "::"


def _looks_like_path(
    token: str,
) -> bool:
    return (
        "/" in token
        or "\\" in token
        or token.endswith(TARGET_PATH_SUFFIXES)
    )


def _remainder_after_prefix(
    command: str,
) -> str | None:
    """Return the argument part of a targeted command, or None.

    Both allowlists are consulted so the grammar recognised here cannot drift
    from the grammar the Factory accepts.
    """

    for prefix in ALLOWED_TARGETED_TEST_COMMAND_PREFIXES:
        if command.startswith(prefix):
            return command[len(prefix):]

    for prefix in ALLOWED_TEST_COMMAND_PREFIXES:
        if command == prefix:
            # The bare runner is a full-suite command: no declared target.
            return None

        if command.startswith(f"{prefix} "):
            return command[len(prefix):]

    return None


def extract_validation_targets(
    command: str,
) -> list[str]:
    """Return the paths a command explicitly asks to validate.

    An empty list means the command declared no target of its own - a
    full-project suite, a type check, a build - and nothing here applies to
    it.
    """

    if not isinstance(command, str):
        return []

    remainder = _remainder_after_prefix(command.strip())

    if remainder is None:
        return []

    targets: list[str] = []

    for token in remainder.split():
        if token.startswith("-"):
            continue

        candidate = token.split(PYTEST_NODE_SEPARATOR, 1)[0].strip()

        if not candidate or not _looks_like_path(candidate):
            continue

        if candidate not in targets:
            targets.append(candidate)

    return targets


def is_targeted_validation(
    command: str,
) -> bool:
    """Whether a command names what it validates."""

    return bool(extract_validation_targets(command))


def find_invalid_validation_targets(
    commands: list[str],
    root: Path,
) -> list[str]:
    """Return declared targets that do not exist in the given workspace.

    Called against the transaction after the unit has been applied, so a test
    the unit authored itself counts as present and a test that was never
    there does not. A command with no declared target is untouched.
    """

    root = Path(root)
    invalid: list[str] = []

    for command in commands or []:
        for target in extract_validation_targets(command):
            if (root / target).exists():
                continue

            if target not in invalid:
                invalid.append(target)

    return invalid
