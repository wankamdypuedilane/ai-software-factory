from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_factory.command_classification import (
    build_unknown_command_correction,
    normalize_command_categories,
)
from ai_factory.test_references import (
    build_missing_reference_correction,
    build_tests_only_correction,
    find_missing_test_references,
    writes_only_tests,
)
from ai_factory.blocker_contract import (
    blocking_blockers,
    demote_deferred_blockers,
    normalize_blockers,
)
from ai_factory.generated_file_validation import (
    validate_generated_file,
)
from ai_factory.implementation_contract import (
    ImplementationTaskKind,
    VerificationPolicy,
    default_verification_policy,
)
from ai_factory.native_dependency_policy import (
    build_native_preparation_commands,
    load_approved_native_packages,
)
from ai_factory.implementation_pipeline import (
    apply_implementation_result,
)
from ai_factory.implementation_prompt import (
    build_implementation_prompt,
)
from ai_factory.implementation_provider import (
    ImplementationProvider,
)
from ai_factory.implementation_request import (
    ImplementationTask,
)
from ai_factory.implementation_result import (
    ImplementationResult,
)
from ai_factory.setup_runner import (
    SetupExecutionResult,
    run_setup_command,
)
from ai_factory.setup_command_policy import (
    validate_setup_command,
)
from ai_factory.test_runner import (
    CommandExecutionResult,
    run_test_command,
)
from ai_factory.retry_evidence import (
    resolve_failed_attempt_evidence,
)
from ai_factory.validation_evidence import (
    build_missing_validation_correction,
    changes_governed_state,
    missing_validation_evidence,
)
from ai_factory.validation_target import (
    extract_validation_targets,
    find_invalid_validation_targets,
)
from ai_factory.workspace_transaction import (
    WorkspaceTransaction,
    open_workspace_transaction,
    save_failed_transaction_snapshot,
)
from ai_factory.workspace_snapshot import (
    build_workspace_snapshot,
    expand_workspace_paths_with_local_imports,
    extract_workspace_paths_from_test_results,
    get_default_workspace_context_paths,
    is_diagnostic_path_relevant_to_task,
    prioritize_diagnostic_paths,
    resolve_project_identity,
)


def _is_full_project_test_command(
    command: str,
) -> bool:
    return command.strip() in {
        "npm test",
        "npm run test",
        "pytest",
        "python -m pytest",
    }


VERIFICATION_SCOPE_MARKERS = (
    "full",
    "final",
    "global",
    "entire",
    "project wide",
    "end to end",
    "e2e",
)

VERIFICATION_ACTIVITY_MARKERS = (
    "verification",
    "verify",
    "regression",
    "smoke",
    "test suite",
    "tests",
    "testing",
)


def _normalize_task_identity(
    task: ImplementationTask,
) -> str:
    return (
        f"{task.id} {task.title}"
        .lower()
        .replace("-", " ")
        .replace("_", " ")
    )


def _is_verification_task(
    task: ImplementationTask,
) -> bool:
    """Return whether a task is an explicit project-wide verification unit.

    A verification unit must announce both a project-wide scope and a
    verification activity. Narrower units such as "Discovery API tests" stay
    intermediate so that an unrelated pre-existing failure cannot decide
    their outcome.

    Only the task identity is inspected. The free-form purpose routinely
    mentions verification vocabulary for ordinary implementation units, so it
    is not a reliable classification signal.
    """

    text = _normalize_task_identity(task)

    has_scope = any(
        marker in text
        for marker in VERIFICATION_SCOPE_MARKERS
    )

    has_activity = any(
        marker in text
        for marker in VERIFICATION_ACTIVITY_MARKERS
    )

    return has_scope and has_activity


MAX_TEST_SCOPE_ATTEMPTS = 2


TEST_FILE_NAME_MARKERS = (
    ".test.",
    ".spec.",
)


def _is_test_file_path(
    path: str,
) -> bool:
    normalized = path.replace(
        "\\",
        "/",
    ).lower()

    name = normalized.rsplit(
        "/",
        1,
    )[-1]

    if any(
        marker in name
        for marker in TEST_FILE_NAME_MARKERS
    ):
        return True

    return (
        name.startswith("test_")
        and name.endswith(".py")
    )


def _legacy_verification_policy(
    task: ImplementationTask,
) -> VerificationPolicy:
    """MIGRATION DEBT: infer the policy from the task identity.

    Used only for units that declare no contract. Every declared unit is
    resolved from its structured fields and never reaches this function.
    Delete this together with `_is_verification_task` once all producers
    emit a contract.
    """

    if _is_verification_task(task):
        return VerificationPolicy(
            allow_full_suite=True,
            baseline_required=False,
        )

    return VerificationPolicy(
        allow_full_suite=False,
        baseline_required=True,
    )


def resolve_verification_policy(
    task: ImplementationTask,
) -> VerificationPolicy:
    """Resolve the execution policy of an implementation unit.

    A declared policy wins over everything. A declared kind derives one.
    Only a unit declaring nothing falls back to the legacy heuristic, so a
    contract can never be contradicted by a title or a purpose.
    """

    if task.verification is not None:
        return task.verification

    if task.kind is not None:
        return default_verification_policy(
            task.kind,
            task.scope,
        )

    return _legacy_verification_policy(task)


def _find_full_project_test_commands(
    policy: VerificationPolicy,
    result: ImplementationResult,
) -> list[str]:
    """Return the full-project test commands forbidden for this unit."""

    if policy.allow_full_suite:
        return []

    return list(
        dict.fromkeys(
            command
            for command in result.tests
            if _is_full_project_test_command(command)
        )
    )


def _build_test_scope_correction(
    task: ImplementationTask,
    offending_commands: list[str],
    result: ImplementationResult,
) -> list[str]:
    """Ask the Developer to replace full-project commands with task-scoped ones."""

    candidate_test_files = list(
        dict.fromkeys(
            file_change.path
            for file_change in result.files
            if _is_test_file_path(file_change.path)
        )
    )

    corrections = [
        "The previous response was rejected by the Factory runtime and was not applied.",
        f"Return a corrected response for task {task.id}.",
    ]

    corrections.extend(
        f"Rejected test command: {command}"
        for command in offending_commands
    )

    corrections.extend(
        [
            "A full-project test suite is not allowed for an intermediate implementation task.",
            "An unrelated pre-existing failure must never decide the outcome of this task.",
            "Replace every rejected command with a task-scoped test command.",
            "For targeted Node.js tests, use: npm test -- <test-file>.",
        ]
    )

    if candidate_test_files:
        corrections.extend(
            [
                "Test files produced or modified by this task: "
                + ", ".join(candidate_test_files),
                "Scope the replacement command to those test files.",
            ]
        )
    else:
        corrections.append(
            "This task returned no test file, so add the automated test it requires "
            "and scope the replacement command to that test file."
        )

    corrections.extend(
        [
            "Keep the rest of the implementation unchanged.",
            "Do not report this correction as a blocker.",
        ]
    )

    return corrections


def _normalize_relative_path(
    path: str,
) -> str:
    normalized = path.strip().replace("\\", "/")

    while normalized.startswith("./"):
        normalized = normalized[2:]

    return normalized


def find_unwritten_validation_targets(
    project_root: Path,
    result: ImplementationResult,
) -> list[str]:
    """Return declared test targets that neither exist nor are written.

    Checked before anything is applied, so a unit that validates itself with
    a test file a later unit will create is corrected for the price of one
    response instead of failing a whole Developer cycle: pytest reports such
    a command with exit code 4, which the outcome model cannot tell apart
    from a defect in the code under test.
    """

    written = {
        _normalize_relative_path(file_change.path)
        for file_change in result.files
    }

    missing: list[str] = []

    for command in result.tests:
        for target in extract_validation_targets(command):
            normalized = _normalize_relative_path(target)

            if normalized in written:
                continue

            if (project_root / normalized).exists():
                continue

            if normalized not in missing:
                missing.append(normalized)

    return missing


def build_missing_test_target_correction(
    task_id: str,
    missing_targets: list[str],
) -> list[str]:
    """Ask the Developer to validate only with tests that will exist."""

    corrections = [
        "The previous response was rejected by the Factory runtime and was not applied.",
        f"Return a corrected response for task {task_id}.",
    ]

    corrections.extend(
        f"Declared test file does not exist and is not written by this response: {target}"
        for target in missing_targets
    )

    corrections.extend(
        [
            "A task may only validate itself with test files that already exist "
            "in the workspace or that it returns in its own files.",
            "Either add the missing test file to this response, or validate with "
            "an existing test file that covers this task.",
            "Never reference a test file that a later task will create.",
            "Keep the rest of the implementation unchanged.",
            "Do not report this correction as a blocker.",
        ]
    )

    return corrections


def _requires_prisma_generate(
    project_root: Path,
    commands: list[str],
) -> bool:
    schema = project_root / "prisma" / "schema.prisma"
    package = project_root / "package.json"

    if not schema.is_file() or not package.is_file():
        return False

    try:
        package_text = package.read_text(encoding="utf-8")
    except OSError:
        return False

    if "@prisma/client" not in package_text:
        return False

    return any(
        command.startswith("npm test")
        or command == "npm run typecheck"
        or command == "npm run build"
        for command in commands
    )



@dataclass
class ImplementationExecution:
    result: ImplementationResult
    task_id: str = ""
    project_identity: tuple[str, ...] = ()
    written_files: list[Path] = field(
        default_factory=list
    )
    setup_results: list[SetupExecutionResult] = field(
        default_factory=list
    )
    baseline_test_results: list[CommandExecutionResult] = field(
        default_factory=list
    )
    retry_test_results: list[dict[str, Any]] = field(
        default_factory=list
    )
    test_results: list[CommandExecutionResult] = field(
        default_factory=list
    )
    # Declared targets that did not exist in the transaction the unit was
    # validated against. Gathered by the runtime, which is what can see the
    # filesystem; judged here, which is what defines a successful unit.
    invalid_validation_targets: list[str] = field(
        default_factory=list
    )
    transaction_discarded: bool = False

    # -- required phases ---------------------------------------------------

    @property
    def setup_passed(self) -> bool:
        """Every declared setup command succeeded.

        No declared setup command is a pass: there was nothing to prepare.
        """

        return all(
            setup_result.passed
            for setup_result in self.setup_results
        )

    @property
    def validation_evidence_present(self) -> bool:
        """The unit declared something the Factory could execute.

        Checked independently of the producer-side correction, so a result
        that reaches execution by any other path still fails closed rather
        than passing every phase by vacuous truth.
        """

        return not missing_validation_evidence(
            self.result,
        )

    @property
    def tests_executed(self) -> bool:
        """Every declared test command actually produced a result.

        An empty result list is only acceptable when the unit declared no
        test. Tests declared but never run is a failure, not a success.
        """

        return len(self.test_results) >= len(self.result.tests)

    @property
    def validations_passed(self) -> bool:
        """The declared validations are acceptable for this unit.

        A failure identical to the pre-existing baseline is tolerated; a new
        one, or one the retry attributed to this task, is not.

        Baseline tolerance presupposes that the command had something to
        run. A declared target that exists in neither the workspace nor the
        transaction makes both executions fail the same way for the same
        empty reason, which is not evidence of anything, so it is refused
        before any comparison.
        """

        if self.invalid_validation_targets:
            return False

        if all(
            test_result.passed
            for test_result in self.test_results
        ):
            return True

        baseline_by_command = {
            result.command: result
            for result in self.baseline_test_results
        }

        required_retry_failures = {
            item.get("command"): item
            for item in self.retry_test_results
            if (
                isinstance(item, dict)
                and item.get("passed") is False
                and isinstance(item.get("command"), str)
            )
        }

        for result in self.test_results:
            if result.passed:
                continue

            retry_failure = required_retry_failures.get(
                result.command
            )

            if retry_failure is not None:
                retry_paths = (
                    extract_workspace_paths_from_test_results(
                        [retry_failure]
                    )
                )

                relevant_retry_paths = [
                    path
                    for path in retry_paths
                    if is_diagnostic_path_relevant_to_task(
                        path,
                        task_id=self.task_id,
                        project_identity=self.project_identity,
                    )
                ]

                if relevant_retry_paths:
                    return False

            baseline = baseline_by_command.get(
                result.command
            )

            if baseline is None or baseline.passed:
                return False

            if (
                result.stdout != baseline.stdout
                or result.stderr != baseline.stderr
            ):
                return False

        return True

    # -- the single definition of a successful unit ------------------------

    @property
    def execution_succeeded(self) -> bool:
        """Whether every required phase of this unit explicitly succeeded.

        Fail-closed: anything that did not demonstrably pass counts as a
        failure, so a discarded transaction can never be reported as
        successful.
        """

        if self.transaction_discarded:
            return False

        if blocking_blockers(self.result.blockers):
            return False

        # Checked before the phases below, all of which an empty declaration
        # satisfies by vacuous truth.
        if not self.validation_evidence_present:
            return False

        if not self.setup_passed:
            return False

        if not self.tests_executed:
            return False

        return self.validations_passed

    @property
    def tests_passed(self) -> bool:
        """Documented alias of `execution_succeeded`.

        The name predates the outcome model and is kept so existing callers
        keep working; it now answers for the whole unit, not the tests alone.
        """

        return self.execution_succeeded


def _record_failed_attempt(
    project_root: Path,
    task_id: str,
    transaction: WorkspaceTransaction,
    result: ImplementationResult,
) -> None:
    """Keep what a failed unit produced, outside the project tree.

    Rolling the workspace back must not cost the retry its context, but a
    transaction also contains what the setup commands generated. Only the
    files the agent declared are kept with their content; everything else is
    recorded by name so an unbounded artifact such as a lockfile can never
    re-enter a prompt.
    """

    authored_paths = {
        change.path.replace("\\", "/")
        for change in result.files
    }

    changed = transaction.changed_files()

    authored_files = {
        path: content
        for path, content in changed.items()
        if path in authored_paths
    }

    generated_paths = sorted(
        path
        for path in transaction.changed_paths()
        if path not in authored_paths
    )

    save_failed_transaction_snapshot(
        project_root=project_root,
        task_id=task_id,
        files=authored_files,
        generated_paths=generated_paths,
    )


def run_implementation_task(
    project_root: Path,
    task: ImplementationTask,
    context: dict[str, Any],
    provider: ImplementationProvider,
    retry_test_results: list[dict[str, Any]] | None = None,
    known_files: list[str] | None = None,
    later_tasks: list[ImplementationTask] | None = None,
) -> ImplementationExecution:
    """Execute and apply one focused implementation task.

    `known_files` names the files earlier units already implemented. They
    are supplied to the model, so a unit builds on the code and the tests
    that exist instead of guessing their interfaces.
    """

    project_identity = resolve_project_identity(
        context
    )

    verification_policy = resolve_verification_policy(
        task
    )

    workspace_paths = (
        get_default_workspace_context_paths(
            project_root
        )
    )

    workspace_paths.extend(
        path
        for path in (known_files or [])
        if isinstance(path, str) and path.strip()
    )

    if retry_test_results:
        state = context.get("state", {})
        developer = (
            state.get("agents", {})
            .get("developer", {})
        )

        last_result = developer.get(
            "last_result",
            {},
        )

        for item in last_result.get(
            "implementation_results",
            [],
        ):
            if (
                isinstance(item, dict)
                and item.get("task_id") == task.id
            ):
                workspace_paths.extend(
                    path
                    for path in item.get("files", [])
                    if isinstance(path, str)
                )

        diagnostic_paths = (
            extract_workspace_paths_from_test_results(
                retry_test_results
            )
        )

        diagnostic_paths = prioritize_diagnostic_paths(
            diagnostic_paths,
            task_id=task.id,
            project_identity=project_identity,
            limit=8,
        )

        workspace_paths.extend(
            diagnostic_paths
        )

    if retry_test_results:
        workspace_paths = expand_workspace_paths_with_local_imports(
            project_root=project_root,
            file_paths=workspace_paths,
        )

    workspace_files = build_workspace_snapshot(
        project_root=project_root,
        file_paths=workspace_paths,
    )

    # A failed attempt was rolled back, so its files are no longer in the
    # workspace. They are supplied separately, never mixed into the
    # workspace snapshot, so the retry cannot mistake them for reality.
    failed_attempt_files: dict[str, str] = {}
    failed_attempt_generated_paths: list[str] = []
    failed_attempt_paths: list[str] = []

    if retry_test_results:
        evidence = resolve_failed_attempt_evidence(
            project_root=project_root,
            state=context.get("state", {}) or {},
            task_id=task.id,
        )

        failed_attempt_files = evidence.authored_files
        failed_attempt_generated_paths = evidence.generated_paths
        failed_attempt_paths = evidence.paths

    policy_corrections: list[str] = []

    for attempt in range(MAX_TEST_SCOPE_ATTEMPTS):
        prompt = build_implementation_prompt(
            task=task,
            context=context,
            retry_test_results=retry_test_results,
            workspace_files=workspace_files,
            failed_attempt_files=failed_attempt_files,
            failed_attempt_generated_paths=failed_attempt_generated_paths,
            failed_attempt_paths=failed_attempt_paths,
            policy_corrections=policy_corrections,
            later_tasks=later_tasks,
        )

        result = provider.implement(
            prompt
        )

        if result.task_id != task.id:
            raise ValueError(
                "Implementation result task ID does not match "
                f"the requested task: {result.task_id} != {task.id}"
            )

        # Classification runs before any policy validation, so a known
        # command filed in the wrong list is corrected instead of rejected.
        classified = normalize_command_categories(
            setup_commands=result.setup_commands,
            tests=result.tests,
        )

        # Only a declared, unfixable external dependency stops the unit.
        # A local defect or a request for a human decision is demoted by the
        # blocker contract and never reaches this point as blocking.
        result.blockers, _ = normalize_blockers(
            result.blockers
        )

        # Work a later unit of the same plan will do is not an impediment:
        # a real run stopped because the routes to protect "did not exist
        # yet", while the next two units of its own plan create them.
        result.blockers = demote_deferred_blockers(
            result.blockers,
            [later.id for later in later_tasks or []],
        )

        if blocking_blockers(result.blockers):
            return ImplementationExecution(
                result=result,
                task_id=task.id,
                project_identity=project_identity,
                retry_test_results=retry_test_results or [],
            )

        is_last_attempt = (
            attempt == MAX_TEST_SCOPE_ATTEMPTS - 1
        )

        # A rejected response is never altered nor applied: the classified
        # lists reach the result only once the response is accepted.
        if classified.unknown:
            if is_last_attempt:
                raise ValueError(
                    "Command is not allowed by the Factory command "
                    "policy: "
                    + ", ".join(classified.unknown)
                )

            policy_corrections = build_unknown_command_correction(
                task_id=task.id,
                unknown_commands=classified.unknown,
            )

            continue

        result.setup_commands = classified.setup_commands
        result.tests = classified.tests

        # A response that would change governed files without declaring how
        # to verify them is corrected here, so the model gets a bounded
        # chance to supply the evidence. A response that changes nothing has
        # nothing to correct; the outcome model still refuses to call it a
        # success.
        missing_validation = (
            missing_validation_evidence(
                result,
                kind=task.kind,
                scope=task.scope,
            )
            if changes_governed_state(result)
            else ""
        )

        if missing_validation:
            if is_last_attempt:
                raise ValueError(
                    "The response declares no validation the Factory can "
                    f"execute: {missing_validation}"
                )

            policy_corrections = build_missing_validation_correction(
                task_id=task.id,
                result=result,
                reason=missing_validation,
            )

            continue

        missing_targets = find_unwritten_validation_targets(
            project_root=project_root,
            result=result,
        )

        # On the last attempt the response is applied as it is: the
        # post-execution target check still refuses it, with its evidence.
        if missing_targets and not is_last_attempt:
            policy_corrections = build_missing_test_target_correction(
                task_id=task.id,
                missing_targets=missing_targets,
            )

            continue

        missing_references = find_missing_test_references(
            project_root,
            {
                file_change.path: file_change.content
                for file_change in result.files
                if file_change.operation != "delete"
            },
        )

        if (
            not is_last_attempt
            and not retry_test_results
            and task.kind is ImplementationTaskKind.IMPLEMENTATION
            and writes_only_tests([file_change.path for file_change in result.files])
        ):
            policy_corrections = build_tests_only_correction(task.id)

            continue

        if missing_references and not is_last_attempt:
            policy_corrections = build_missing_reference_correction(
                task_id=task.id,
                missing=missing_references,
            )

            continue

        if _requires_prisma_generate(
            project_root,
            result.tests,
        ):
            if "npm run prisma:generate" not in result.setup_commands:
                result.setup_commands.append(
                    "npm run prisma:generate"
                )

        # Reclassification never grants a command more freedom: a global
        # suite moved out of setup_commands still faces the scope policy.
        full_project_test_commands = _find_full_project_test_commands(
            policy=verification_policy,
            result=result,
        )

        if not full_project_test_commands:
            break

        if is_last_attempt:
            raise ValueError(
                "Full-project test suite is not allowed "
                "for an intermediate implementation task. "
                "Return a task-scoped test command instead."
            )

        policy_corrections = _build_test_scope_correction(
            task=task,
            offending_commands=full_project_test_commands,
            result=result,
        )

    # The agent-authored commands face the agent-facing policy, which never
    # allows a lifecycle build. The permission is not passed here.
    for command in result.setup_commands:
        validate_setup_command(command)

    # Only then does the Factory add its own commands. A dependency the
    # project declared as needing its build step is prepared inside the
    # transaction, so the unit runs against a dependency state that can
    # actually work instead of failing on an environment nothing it writes
    # could repair.
    approved_native_packages = load_approved_native_packages(
        project_root
    )

    for command in build_native_preparation_commands(
        project_root=project_root,
        setup_commands=result.setup_commands,
    ):
        if command not in result.setup_commands:
            result.setup_commands.append(command)

    for file_change in result.files:
        validate_generated_file(
            project_root=project_root,
            path=file_change.path,
            content=file_change.content,
        )

    with open_workspace_transaction(
        source_root=project_root,
        setup_commands=result.setup_commands,
    ) as transaction:
        baseline_test_results: list[
            CommandExecutionResult
        ] = []

        # The baseline must describe the workspace *before* this unit is
        # applied, so it runs on the untouched transaction copy.
        if verification_policy.baseline_required:
            for command in result.tests:
                baseline_test_results.append(
                    run_test_command(
                        project_root=transaction.root,
                        command=command,
                        project_identity=project_identity,
                    )
                )

        transaction_files = apply_implementation_result(
            project_root=transaction.root,
            result=result,
        )

        written_files = [
            project_root
            / path.relative_to(transaction.root)
            for path in transaction_files
        ]

        setup_results = [
            run_setup_command(
                project_root=transaction.root,
                command=command,
                approved_native_packages=approved_native_packages,
            )
            for command in result.setup_commands
        ]

        if not all(
            setup_result.passed
            for setup_result in setup_results
        ):
            _record_failed_attempt(
                project_root=project_root,
                task_id=task.id,
                transaction=transaction,
                result=result,
            )

            return ImplementationExecution(
                result=result,
                task_id=task.id,
                project_identity=project_identity,
                written_files=written_files,
                setup_results=setup_results,
                baseline_test_results=baseline_test_results,
                retry_test_results=retry_test_results or [],
                transaction_discarded=True,
            )

        test_results = [
            run_test_command(
                project_root=transaction.root,
                command=command,
                project_identity=project_identity,
            )
            for command in result.tests
        ]

        execution = ImplementationExecution(
            result=result,
            task_id=task.id,
            project_identity=project_identity,
            written_files=written_files,
            setup_results=setup_results,
            baseline_test_results=baseline_test_results,
            retry_test_results=retry_test_results or [],
            test_results=test_results,
            # Established against the transaction the unit was validated in,
            # so a test the unit authored counts and one that never existed
            # does not.
            invalid_validation_targets=find_invalid_validation_targets(
                commands=result.tests,
                root=transaction.root,
            ),
        )

        if not execution.execution_succeeded:
            _record_failed_attempt(
                project_root=project_root,
                task_id=task.id,
                transaction=transaction,
                result=result,
            )

            execution.transaction_discarded = True

            return execution

        transaction.promote()

        return execution
