"""One source of truth for what category a command belongs to.

The Factory already declares which commands it allows, in two allowlists.
This derives the category from those same declarations rather than adding a
third policy that could drift from them. A known command filed in the wrong
list is corrected; an unknown command is never guessed.
"""

from dataclasses import dataclass, field
from enum import Enum

from ai_factory.setup_command_policy import (
    ALLOWED_SETUP_COMMANDS,
)
from ai_factory.test_command_policy import (
    ALLOWED_TARGETED_TEST_COMMAND_PREFIXES,
    ALLOWED_TEST_COMMANDS,
    ALLOWED_TEST_COMMAND_PREFIXES,
)


class CommandCategory(str, Enum):
    SETUP = "SETUP"
    TEST = "TEST"
    UNKNOWN = "UNKNOWN"


def classify_command(
    command: str,
) -> CommandCategory:
    """Return the category a command belongs to, from the allowlists."""

    if not isinstance(command, str):
        return CommandCategory.UNKNOWN

    normalized = command.strip()

    if not normalized:
        return CommandCategory.UNKNOWN

    if normalized in ALLOWED_SETUP_COMMANDS:
        return CommandCategory.SETUP

    if normalized in ALLOWED_TEST_COMMANDS:
        return CommandCategory.TEST

    if normalized.startswith(
        ALLOWED_TEST_COMMAND_PREFIXES
    ):
        return CommandCategory.TEST

    if normalized.startswith(
        ALLOWED_TARGETED_TEST_COMMAND_PREFIXES
    ):
        return CommandCategory.TEST

    return CommandCategory.UNKNOWN


@dataclass
class ClassifiedCommands:
    setup_commands: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    @property
    def moved(self) -> bool:
        return self._moved

    _moved: bool = False


def normalize_command_categories(
    setup_commands: list[str],
    tests: list[str],
) -> ClassifiedCommands:
    """File every declared command under its own category.

    Both declared lists are walked in order, so the result is deterministic
    and a command listed twice appears once. Unknown commands are collected
    rather than assigned a category.
    """

    classified = ClassifiedCommands()

    declared = [
        *(setup_commands or []),
        *(tests or []),
    ]

    seen: set[str] = set()

    for command in declared:
        normalized = (
            command.strip()
            if isinstance(command, str)
            else command
        )

        if not isinstance(normalized, str) or not normalized:
            classified.unknown.append(command)
            continue

        if normalized in seen:
            continue

        seen.add(normalized)

        category = classify_command(normalized)

        if category is CommandCategory.SETUP:
            classified.setup_commands.append(normalized)
        elif category is CommandCategory.TEST:
            classified.tests.append(normalized)
        else:
            classified.unknown.append(normalized)

    classified._moved = (
        classified.setup_commands != [
            command.strip()
            for command in (setup_commands or [])
            if isinstance(command, str)
        ]
        or classified.tests != [
            command.strip()
            for command in (tests or [])
            if isinstance(command, str)
        ]
    )

    return classified


def build_unknown_command_correction(
    task_id: str,
    unknown_commands: list[str],
) -> list[str]:
    """Ask the agent to replace commands the Factory does not allow."""

    corrections = [
        "The previous response was rejected by the Factory runtime and "
        "was not applied.",
        f"Return a corrected response for task {task_id}.",
    ]

    corrections.extend(
        f"Rejected command: {command}"
        for command in unknown_commands
    )

    corrections.extend(
        [
            "Reason: command is not allowed by the Factory command policy.",
            "Return an allowed task-scoped verification/setup command.",
            "Allowed setup commands: "
            + ", ".join(sorted(ALLOWED_SETUP_COMMANDS))
            + ".",
            "Allowed verification commands: "
            + ", ".join(sorted(ALLOWED_TEST_COMMANDS))
            + ", "
            + ", ".join(
                f"{prefix}<test-file>"
                for prefix in ALLOWED_TARGETED_TEST_COMMAND_PREFIXES
            )
            + ".",
            "Keep the rest of the implementation unchanged.",
            "Do not report this correction as a blocker.",
        ]
    )

    return corrections
