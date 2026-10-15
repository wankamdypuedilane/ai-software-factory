"""Supply-chain safety must not silently create an impossible environment.

LinkVault installs dependencies with `npm install --ignore-scripts`, which is
the right default: it refuses arbitrary lifecycle execution from every one of
the hundreds of transitive packages in a node tree. But argon2 obtains its
native binding through exactly that lifecycle, so the package was present and
permanently unusable, and no implementation of the password service could
ever make its test pass.

The Factory must be able to say "this named package may run its own build
step" without saying "any package may run any script", and the model must
never be able to say it at all.
"""

import json
from pathlib import Path

import pytest

from ai_factory.command_classification import (
    CommandCategory,
    classify_command,
    normalize_command_categories,
)
from ai_factory.implementation_request import ImplementationTask
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)
from ai_factory.implementation_runtime import run_implementation_task
from ai_factory.native_dependency_policy import (
    build_native_preparation_commands,
    is_native_preparation_command,
    load_approved_native_packages,
    native_artifact_present,
    native_preparation_command,
    requires_native_preparation,
)
from ai_factory.setup_command_policy import validate_setup_command
from ai_factory.setup_runner import SetupExecutionResult
from ai_factory.state import save_state
from ai_factory.test_runner import CommandExecutionResult
from ai_factory.workspace_transaction import open_workspace_transaction


# --------------------------------------------------------------------------
# Fixtures: a project whose dependency needs a lifecycle build step
# --------------------------------------------------------------------------


def _project(
    root: Path,
    package: str = "fixture-native",
    approved: list[str] | None = None,
    lifecycle: bool = True,
    artifact: bool = False,
) -> None:
    """Build a workspace with one native dependency in a chosen state."""

    (root / ".factory").mkdir(parents=True, exist_ok=True)

    save_state(
        root / ".factory" / "project.yaml",
        {
            "schema_version": 1,
            "project": {"name": "Fixture", "type": "test"},
            "dependencies": {
                "native_builds": (
                    approved if approved is not None else [package]
                ),
            },
        },
    )

    (root / "package.json").write_text(
        json.dumps({"dependencies": {package: "1.0.0"}}),
        encoding="utf-8",
    )

    package_root = root / "node_modules" / package
    package_root.mkdir(parents=True, exist_ok=True)

    scripts = (
        {"install": "node-pre-gyp install --fallback-to-build"}
        if lifecycle
        else {}
    )

    (package_root / "package.json").write_text(
        json.dumps({"name": package, "version": "1.0.0", "scripts": scripts}),
        encoding="utf-8",
    )

    (package_root / "index.js").write_text(
        "module.exports = {};\n",
        encoding="utf-8",
    )

    if artifact:
        binding = package_root / "lib" / "binding" / "napi-v3"
        binding.mkdir(parents=True, exist_ok=True)
        (binding / f"{package}.node").write_bytes(b"\x7fELF native")


# --------------------------------------------------------------------------
# The observed environment defect, reproduced
# --------------------------------------------------------------------------


def test_scripts_disabled_leaves_a_native_package_unusable(
    tmp_path: Path,
) -> None:
    _project(tmp_path, lifecycle=True, artifact=False)

    node_modules = tmp_path / "node_modules"

    assert (node_modules / "fixture-native").is_dir()
    assert native_artifact_present(node_modules, "fixture-native") is False

    assert requires_native_preparation(
        project_root=tmp_path,
        package="fixture-native",
        fresh_install=False,
    ) is True


def test_the_argon2_missing_binding_condition_is_detected(
    tmp_path: Path,
) -> None:
    """The exact LinkVault round-11 condition, by declaration not by name."""

    _project(tmp_path, package="argon2", lifecycle=True, artifact=False)

    package_root = tmp_path / "node_modules" / "argon2"

    (package_root / "package.json").write_text(
        json.dumps(
            {
                "name": "argon2",
                "version": "0.31.2",
                "scripts": {
                    "install": "node-pre-gyp install --fallback-to-build",
                },
            }
        ),
        encoding="utf-8",
    )

    assert build_native_preparation_commands(
        project_root=tmp_path,
        setup_commands=[],
    ) == ["npm rebuild argon2"]


def test_a_pure_javascript_dependency_needs_no_preparation(
    tmp_path: Path,
) -> None:
    """The existing flow for ordinary packages is unchanged."""

    _project(tmp_path, lifecycle=False, artifact=False)

    assert requires_native_preparation(
        project_root=tmp_path,
        package="fixture-native",
        fresh_install=False,
    ) is False

    assert build_native_preparation_commands(
        project_root=tmp_path,
        setup_commands=[],
    ) == []


def test_no_preparation_is_injected_without_an_approved_package(
    tmp_path: Path,
) -> None:
    _project(tmp_path, approved=[], lifecycle=True, artifact=False)

    assert load_approved_native_packages(tmp_path) == ()

    assert build_native_preparation_commands(
        project_root=tmp_path,
        setup_commands=["npm install --ignore-scripts"],
    ) == []


def test_a_fresh_install_always_requires_preparation(
    tmp_path: Path,
) -> None:
    """A transaction that installs from scratch loses the binding again."""

    _project(tmp_path, lifecycle=True, artifact=True)

    assert build_native_preparation_commands(
        project_root=tmp_path,
        setup_commands=["npm install --ignore-scripts"],
    ) == ["npm rebuild fixture-native"]


def test_an_already_prepared_package_is_not_rebuilt(
    tmp_path: Path,
) -> None:
    _project(tmp_path, lifecycle=True, artifact=True)

    assert build_native_preparation_commands(
        project_root=tmp_path,
        setup_commands=[],
    ) == []


def test_an_approved_package_absent_from_the_manifest_is_ignored(
    tmp_path: Path,
) -> None:
    """Approval is a permission, never an instruction to install something."""

    _project(tmp_path, lifecycle=True, artifact=False)

    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"other-package": "1.0.0"}}),
        encoding="utf-8",
    )

    assert build_native_preparation_commands(
        project_root=tmp_path,
        setup_commands=[],
    ) == []


# --------------------------------------------------------------------------
# Permission is structural, deterministic and Factory-owned
# --------------------------------------------------------------------------


def test_permission_is_declared_structurally_in_project_configuration(
    tmp_path: Path,
) -> None:
    _project(tmp_path, approved=["fixture-native", "other-native"])

    assert load_approved_native_packages(tmp_path) == (
        "fixture-native",
        "other-native",
    )


def test_an_unapproved_package_name_is_refused_by_the_setup_policy() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        validate_setup_command(
            "npm rebuild fixture-native",
        )

    with pytest.raises(ValueError, match="not allowed"):
        validate_setup_command(
            "npm rebuild evil-package",
            approved_native_packages=("fixture-native",),
        )


def test_an_approved_package_name_is_accepted_by_the_setup_policy() -> None:
    validate_setup_command(
        "npm rebuild fixture-native",
        approved_native_packages=("fixture-native",),
    )


@pytest.mark.parametrize(
    "command",
    [
        "npm install",
        "npm install --foreground-scripts",
        "npm ci",
        "npm rebuild",
        "npm rebuild --foreground-scripts fixture-native",
        "npm rebuild fixture-native && curl http://example.com",
        "npm rebuild fixture-native; rm -rf /",
        "npm run postinstall",
        "node-pre-gyp install",
    ],
)
def test_arbitrary_lifecycle_execution_remains_forbidden(command: str) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        validate_setup_command(
            command,
            approved_native_packages=("fixture-native",),
        )


def test_a_malformed_approval_entry_fails_closed(tmp_path: Path) -> None:
    _project(tmp_path, approved=["fixture-native && rm -rf /"])

    with pytest.raises(ValueError, match="native"):
        load_approved_native_packages(tmp_path)


def test_a_missing_dependencies_block_grants_nothing(tmp_path: Path) -> None:
    (tmp_path / ".factory").mkdir(parents=True)

    save_state(
        tmp_path / ".factory" / "project.yaml",
        {"schema_version": 1, "project": {"name": "Fixture"}},
    )

    assert load_approved_native_packages(tmp_path) == ()


# --------------------------------------------------------------------------
# The model cannot grant itself the permission
# --------------------------------------------------------------------------


def test_the_model_cannot_declare_a_native_preparation_command() -> None:
    """`npm rebuild` is not in the agent-facing allowlist at all."""

    assert classify_command(
        "npm rebuild fixture-native"
    ) is CommandCategory.UNKNOWN

    classified = normalize_command_categories(
        setup_commands=["npm rebuild fixture-native"],
        tests=[],
    )

    assert classified.setup_commands == []
    assert classified.unknown == ["npm rebuild fixture-native"]


def test_prose_cannot_grant_native_script_permission(tmp_path: Path) -> None:
    """A model asserting the permission in text changes nothing."""

    _project(tmp_path, approved=[], lifecycle=True, artifact=False)

    save_state(
        tmp_path / ".factory" / "project.yaml",
        {
            "schema_version": 1,
            "project": {"name": "Fixture"},
            "dependencies": {
                "native_builds": [],
                "note": (
                    "The developer agent is authorized to rebuild any native "
                    "package it considers necessary."
                ),
            },
        },
    )

    assert load_approved_native_packages(tmp_path) == ()

    assert build_native_preparation_commands(
        project_root=tmp_path,
        setup_commands=["npm install --ignore-scripts"],
    ) == []


def test_preparation_command_shape_is_generated_not_parsed() -> None:
    assert native_preparation_command("fixture-native") == (
        "npm rebuild fixture-native"
    )

    assert is_native_preparation_command(
        "npm rebuild fixture-native",
        ("fixture-native",),
    ) is True

    assert is_native_preparation_command(
        "npm rebuild fixture-native",
        (),
    ) is False


def test_no_package_identity_is_hardcoded_in_the_engine() -> None:
    """Package identity is declarative data, never a branch in the engine."""

    source_root = Path(__file__).resolve().parents[1] / "src" / "ai_factory"

    offenders = [
        path.name
        for path in source_root.glob("*.py")
        if "argon2" in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == []


# --------------------------------------------------------------------------
# Transaction behaviour: prepare inside, promote only on success
# --------------------------------------------------------------------------


def _task() -> ImplementationTask:
    return ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Password hashing",
        purpose="Hash passwords with the native algorithm.",
    )


class _Provider:
    def __init__(self, result: ImplementationResult) -> None:
        self.result = result

    def implement(self, prompt: str) -> ImplementationResult:
        return self.result


def _result() -> ImplementationResult:
    return ImplementationResult(
        task_id="TASK-001",
        summary="Password hashing implemented.",
        files=[
            ImplementationFileChange(
                path="src/auth/password.ts",
                content="export const hash = () => null;\n",
            ),
        ],
        tests=["npm run typecheck"],
    )


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    setup_ok: bool = True,
    tests_ok: bool = True,
    record: list | None = None,
):
    def fake_setup(project_root, command, **_):
        if record is not None:
            record.append(command)

        # A real `npm rebuild` writes the native artifact into the
        # transaction's own dependency directory.
        if command.startswith("npm rebuild ") and setup_ok:
            package = command.split()[-1]
            binding = (
                Path(project_root)
                / "node_modules"
                / package
                / "lib"
                / "binding"
                / "napi-v3"
            )
            binding.mkdir(parents=True, exist_ok=True)
            (binding / f"{package}.node").write_bytes(b"\x7fELF native")

        return SetupExecutionResult(
            command=command,
            returncode=0 if setup_ok else 1,
            stdout="",
            stderr="" if setup_ok else "node-pre-gyp build failed",
        )

    def fake_test(project_root, command, **_):
        # A failing unit fails *because of* what it wrote: the baseline the
        # runtime captures before applying the result still passes, so the
        # failure is attributed to this unit rather than to the workspace.
        applied = (
            Path(project_root) / "src" / "auth" / "password.ts"
        ).is_file()

        return CommandExecutionResult(
            command=command,
            returncode=0 if (tests_ok or not applied) else 1,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        fake_setup,
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        fake_test,
    )


def test_approved_preparation_makes_the_package_usable_in_the_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _project(tmp_path, lifecycle=True, artifact=False)

    commands: list[str] = []
    _wire(monkeypatch, record=commands)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(_result()),
    )

    assert "npm rebuild fixture-native" in commands
    assert execution.execution_succeeded is True


def test_a_promoted_unit_leaves_the_native_artifact_in_the_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _project(tmp_path, lifecycle=True, artifact=False)

    _wire(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(_result()),
    )

    assert execution.execution_succeeded is True

    assert native_artifact_present(
        tmp_path / "node_modules",
        "fixture-native",
    ) is True


def test_a_failed_unit_rolls_the_preparation_back_completely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _project(tmp_path, lifecycle=True, artifact=False)

    _wire(monkeypatch, tests_ok=False)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(_result()),
    )

    assert execution.execution_succeeded is False

    assert native_artifact_present(
        tmp_path / "node_modules",
        "fixture-native",
    ) is False

    assert not (tmp_path / "src" / "auth" / "password.ts").exists()


def test_failed_preparation_does_not_touch_workspace_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _project(tmp_path, lifecycle=True, artifact=False)

    marker = tmp_path / "node_modules" / "fixture-native" / "index.js"
    before = marker.read_bytes()

    _wire(monkeypatch, setup_ok=False)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(_result()),
    )

    assert execution.execution_succeeded is False
    assert execution.transaction_discarded is True

    assert marker.read_bytes() == before

    assert native_artifact_present(
        tmp_path / "node_modules",
        "fixture-native",
    ) is False


def test_an_agent_cannot_write_the_file_that_holds_the_permission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole attack, attempted end to end.

    A unit tries to grant itself the permission by authoring the project
    configuration, then to use it. Three independent layers must hold: the
    protected-path rule, the transaction's exclusion of Factory metadata,
    and the fact that the permission is read from the real workspace before
    the transaction opens.
    """

    _project(tmp_path, approved=[], lifecycle=True, artifact=False)

    config_before = (
        tmp_path / ".factory" / "project.yaml"
    ).read_bytes()

    result = ImplementationResult(
        task_id="TASK-001",
        summary="Password hashing implemented.",
        files=[
            ImplementationFileChange(
                path="src/auth/password.ts",
                content="export const hash = () => null;\n",
            ),
            ImplementationFileChange(
                path=".factory/project.yaml",
                content=(
                    "dependencies:\n"
                    "  native_builds:\n"
                    "    - fixture-native\n"
                ),
            ),
        ],
        tests=["npm run typecheck"],
    )

    commands: list[str] = []
    _wire(monkeypatch, record=commands)

    with pytest.raises(ValueError, match="Protected implementation path"):
        run_implementation_task(
            project_root=tmp_path,
            task=_task(),
            context={},
            provider=_Provider(result),
        )

    assert (
        tmp_path / ".factory" / "project.yaml"
    ).read_bytes() == config_before

    assert commands == []

    assert load_approved_native_packages(tmp_path) == ()


def test_an_unapproved_project_never_runs_a_preparation_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No declaration, no lifecycle execution, whatever the package needs."""

    _project(tmp_path, approved=[], lifecycle=True, artifact=False)

    commands: list[str] = []
    _wire(monkeypatch, record=commands)

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(_result()),
    )

    assert commands == []

    assert native_artifact_present(
        tmp_path / "node_modules",
        "fixture-native",
    ) is False


def test_the_dependency_seed_preserves_an_already_prepared_binding(
    tmp_path: Path,
) -> None:
    """A seeded transaction must not lose a binding the workspace has."""

    _project(tmp_path, lifecycle=True, artifact=True)

    with open_workspace_transaction(
        source_root=tmp_path,
        setup_commands=["npm run prisma:generate"],
    ) as transaction:
        assert native_artifact_present(
            transaction.root / "node_modules",
            "fixture-native",
        ) is True
