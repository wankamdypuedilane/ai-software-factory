"""A known command placed in the wrong list is a filing mistake, not a fault.

LinkVault round 3 died on `npm run prisma:validate` declared in
setup_commands. It is a valid verification command; only its category was
wrong. Classification is symmetric and deterministic, and the full-suite
policy still applies after any move.
"""

from pathlib import Path

import pytest

from ai_factory.command_classification import (
    CommandCategory,
    classify_command,
    normalize_command_categories,
)
from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
    VerificationPolicy,
)
from ai_factory.implementation_request import ImplementationTask
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)
from ai_factory.implementation_runtime import run_implementation_task
from ai_factory.setup_runner import SetupExecutionResult
from ai_factory.test_runner import CommandExecutionResult


TASK_ID = "ACME-DEV-FOUNDATION"


class SequencedProvider:
    def __init__(self, results: list[ImplementationResult]) -> None:
        self.pending = list(results)
        self.prompts: list[str] = []

    def implement(self, prompt: str) -> ImplementationResult:
        self.prompts.append(prompt)

        if not self.pending:
            raise AssertionError(
                "Provider was called more times than expected."
            )

        return self.pending.pop(0)


def _task(
    kind: ImplementationTaskKind = ImplementationTaskKind.IMPLEMENTATION,
    scope: ImplementationScope = ImplementationScope.TASK,
    allow_full_suite: bool = False,
) -> ImplementationTask:
    return ImplementationTask(
        agent_name="developer",
        id=TASK_ID,
        title="Foundation",
        purpose="Implement the foundation.",
        kind=kind,
        scope=scope,
        verification=VerificationPolicy(
            allow_full_suite=allow_full_suite,
            baseline_required=True,
        ),
    )


def _result(
    setup_commands: list[str] | None = None,
    tests: list[str] | None = None,
) -> ImplementationResult:
    return ImplementationResult(
        task_id=TASK_ID,
        summary="Foundation implemented.",
        files=[
            ImplementationFileChange(
                path="src/app.ts",
                content="export const app = 1;\n",
            ),
        ],
        setup_commands=setup_commands or [],
        tests=tests or ["npm run typecheck"],
    )


def _stub(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def fake_test(**kwargs):
        calls.append(("test", kwargs["command"]))
        return CommandExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        )

    def fake_setup(**kwargs):
        calls.append(("setup", kwargs["command"]))
        return SetupExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        fake_test,
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        fake_setup,
    )

    return calls


# --------------------------------------------------------------------------
# Classification, one source of truth
# --------------------------------------------------------------------------


def test_classify_command_uses_the_existing_allowlists() -> None:
    assert classify_command(
        "npm install --ignore-scripts"
    ) is CommandCategory.SETUP
    assert classify_command(
        "npm run prisma:generate"
    ) is CommandCategory.SETUP

    assert classify_command(
        "npm run prisma:validate"
    ) is CommandCategory.TEST
    assert classify_command("npm test") is CommandCategory.TEST
    assert classify_command(
        "npm test -- src/app.test.ts"
    ) is CommandCategory.TEST
    assert classify_command(
        "python -m pytest tests/test_app.py"
    ) is CommandCategory.TEST

    assert classify_command(
        "rm -rf /"
    ) is CommandCategory.UNKNOWN
    assert classify_command("") is CommandCategory.UNKNOWN


def test_a_test_command_in_setup_is_moved_to_tests() -> None:
    """The exact LinkVault LV-IMP-002 shape."""

    classified = normalize_command_categories(
        setup_commands=["npm run prisma:validate"],
        tests=[],
    )

    assert classified.setup_commands == []
    assert classified.tests == ["npm run prisma:validate"]
    assert classified.unknown == []


def test_a_setup_command_in_tests_is_moved_to_setup() -> None:
    """Historic behaviour, preserved."""

    classified = normalize_command_categories(
        setup_commands=[],
        tests=[
            "npm run prisma:generate",
            "npm run typecheck",
        ],
    )

    assert classified.setup_commands == ["npm run prisma:generate"]
    assert classified.tests == ["npm run typecheck"]


def test_correctly_filed_commands_are_untouched() -> None:
    classified = normalize_command_categories(
        setup_commands=["npm install --ignore-scripts"],
        tests=["npm run typecheck", "npm run build"],
    )

    assert classified.setup_commands == ["npm install --ignore-scripts"]
    assert classified.tests == ["npm run typecheck", "npm run build"]


def test_a_command_listed_twice_is_not_duplicated() -> None:
    classified = normalize_command_categories(
        setup_commands=["npm run prisma:generate"],
        tests=["npm run prisma:generate", "npm run typecheck"],
    )

    assert classified.setup_commands == ["npm run prisma:generate"]
    assert classified.tests == ["npm run typecheck"]


def test_relative_order_is_preserved() -> None:
    classified = normalize_command_categories(
        setup_commands=[
            "npm install --ignore-scripts",
            "npm run prisma:generate",
        ],
        tests=[
            "npm run typecheck",
            "npm run build",
            "npm run lint",
        ],
    )

    assert classified.setup_commands == [
        "npm install --ignore-scripts",
        "npm run prisma:generate",
    ]
    assert classified.tests == [
        "npm run typecheck",
        "npm run build",
        "npm run lint",
    ]


def test_an_unknown_command_is_reported_not_guessed() -> None:
    classified = normalize_command_categories(
        setup_commands=["npm run bootstrap"],
        tests=["npm run typecheck"],
    )

    assert classified.unknown == ["npm run bootstrap"]
    assert classified.setup_commands == []
    assert classified.tests == ["npm run typecheck"]


# --------------------------------------------------------------------------
# Runtime behaviour
# --------------------------------------------------------------------------


def test_linkvault_prisma_validate_no_longer_fails_the_unit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduction of LV-IMP-002."""

    # The declared targeted test needs a target: a command with nothing to
    # run validates nothing, whatever its exit code.
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "app.test.ts").write_text(
        "// covers src/app.ts\n",
        encoding="utf-8",
    )

    provider = SequencedProvider(
        [
            _result(
                setup_commands=["npm run prisma:validate"],
                tests=["npm test -- src/app.test.ts"],
            )
        ]
    )

    calls = _stub(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 1, "no extra provider call is needed"
    assert execution.result.setup_commands == []
    assert "npm run prisma:validate" in execution.result.tests
    assert execution.tests_passed

    # Order preserved: baseline tests, then setup, then final tests.
    assert calls[0][0] == "test"
    assert ("setup", "npm run prisma:validate") not in calls


def test_a_global_test_command_in_setup_cannot_bypass_the_scope_policy(
    tmp_path: Path,
) -> None:
    provider = SequencedProvider(
        [
            _result(
                setup_commands=["npm test"],
                tests=[],
            ),
            _result(
                setup_commands=["npm test"],
                tests=[],
            ),
        ]
    )

    with pytest.raises(
        ValueError,
        match="Full-project test suite is not allowed",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=_task(),
            context={},
            provider=provider,
        )

    assert not (tmp_path / "src").exists()


def test_a_global_test_command_in_setup_is_allowed_for_project_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SequencedProvider(
        [
            _result(
                setup_commands=["npm test"],
                tests=[],
            )
        ]
    )

    _stub(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(
            kind=ImplementationTaskKind.VERIFICATION,
            scope=ImplementationScope.PROJECT,
            allow_full_suite=True,
        ),
        context={},
        provider=provider,
    )

    assert execution.result.setup_commands == []

    # Reclassified out of setup_commands, ahead of the unit's own tests.
    assert execution.result.tests == [
        "npm test",
        "npm run typecheck",
    ]
    assert execution.tests_passed


def test_an_unknown_command_triggers_a_bounded_reprompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SequencedProvider(
        [
            _result(
                setup_commands=["npm run bootstrap"],
                tests=["npm run typecheck"],
            ),
            _result(
                setup_commands=["npm install --ignore-scripts"],
                tests=["npm run typecheck"],
            ),
        ]
    )

    _stub(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 2

    correction = provider.prompts[1]
    assert "Rejected command: npm run bootstrap" in correction
    assert "not allowed by the Factory command policy" in correction

    assert execution.result.setup_commands == [
        "npm install --ignore-scripts"
    ]


def test_a_persistently_unknown_command_fails_cleanly(
    tmp_path: Path,
) -> None:
    provider = SequencedProvider(
        [
            _result(setup_commands=["npm run bootstrap"]),
            _result(setup_commands=["npm run bootstrap"]),
        ]
    )

    with pytest.raises(
        ValueError,
        match="not allowed by the Factory command policy",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=_task(),
            context={},
            provider=provider,
        )

    # Nothing rejected is ever applied.
    assert not (tmp_path / "src").exists()


def test_reclassification_preserves_the_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text(
        "export const app = 'ORIGINAL';\n",
        encoding="utf-8",
    )

    codes = [0, 1]

    def failing_test(**kwargs):
        returncode = codes.pop(0) if codes else 1
        return CommandExecutionResult(
            command=kwargs["command"],
            returncode=returncode,
            stdout="",
            stderr="boom" if returncode else "",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        failing_test,
    )

    provider = SequencedProvider(
        [
            _result(
                setup_commands=["npm run prisma:validate"],
                tests=[],
            )
        ]
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert not execution.tests_passed

    assert (
        tmp_path / "src" / "app.ts"
    ).read_text(encoding="utf-8") == "export const app = 'ORIGINAL';\n"
