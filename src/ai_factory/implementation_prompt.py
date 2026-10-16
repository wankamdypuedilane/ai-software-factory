from typing import Any

from ai_factory.rework import format_rework_request

from ai_factory.implementation_request import ImplementationTask


# Measurable context budget. Each category is bounded on its own so that one
# oversized input cannot crowd out the others.
MAX_RELEVANT_ARTIFACT_CHARS = 4000

# Artifacts that fix the contract between independent implementation units.
# They are supplied first and in full (up to their own cap), never squeezed
# out by the shared artifact budget: a real run produced two units that
# disagreed on a return type because nothing fixed it for both.
BINDING_CONTRACT_ARTIFACTS = (
    "knowledge/architecture/interfaces.md",
    "knowledge/architecture/api.md",
    # The interaction contract (commands, outputs, messages, exit codes) the
    # UX/UI contract asks to be written here. A real run truncated the UX
    # specification to 2843 of its 4866 characters on the Developer side.
    "design/ux-ui/screen-specs.md",
)
MAX_BINDING_CONTRACT_CHARS = 16000
MAX_RELEVANT_ARTIFACTS_TOTAL_CHARS = 32000

MAX_WORKSPACE_FILE_CHARS = 6000
MAX_WORKSPACE_FILES_TOTAL_CHARS = 40000

MAX_FAILED_ATTEMPT_FILE_CHARS = 4000
MAX_FAILED_ATTEMPT_TOTAL_CHARS = 20000

MAX_TEST_OUTPUT_CHARS = 4000


def _truncate(
    content: str,
    limit: int,
) -> str:
    """Trim one item to its budget, stating exactly what was removed."""

    if len(content) <= limit:
        return content

    omitted = len(content) - limit

    return (
        content[:limit]
        + f"\n[truncated: {omitted} characters omitted]"
    )


def _head_and_tail(
    content: str,
    limit: int,
) -> str:
    """Trim test output to its budget, keeping both of its ends."""

    if len(content) <= limit:
        return content

    head = limit * 2 // 5
    tail = limit - head

    return (
        content[:head]
        + f"\n[truncated: {len(content) - head - tail} characters omitted]\n"
        + content[-tail:]
    )


def _budgeted_blocks(
    items: dict[str, str],
    per_item: int,
    total: int,
) -> tuple[list[tuple[str, str]], int]:
    """Return the blocks that fit the budget and how many were dropped."""

    blocks: list[tuple[str, str]] = []
    used = 0

    for path, content in items.items():
        if used >= total:
            break

        trimmed = _truncate(
            content,
            min(
                per_item,
                total - used,
            ),
        )

        blocks.append(
            (
                path,
                trimmed,
            )
        )

        used += len(trimmed)

    return blocks, len(items) - len(blocks)


def build_implementation_prompt(
    task: ImplementationTask,
    context: dict[str, Any],
    retry_test_results: list[dict[str, Any]] | None = None,
    workspace_files: dict[str, str] | None = None,
    failed_attempt_files: dict[str, str] | None = None,
    failed_attempt_generated_paths: list[str] | None = None,
    failed_attempt_paths: list[str] | None = None,
    policy_corrections: list[str] | None = None,
) -> str:
    """Build a focused prompt for one implementation task."""

    project = context.get("project", {})
    state = context.get("state", {})
    artifacts = context.get("artifacts", {})
    human_input = context.get("human_input")

    sections = [
        "# Implementation Task",
        "",
        f"Agent: {task.agent_name}",
        f"Task ID: {task.id}",
        f"Title: {task.title}",
        "",
        "## Purpose",
        task.purpose,
    ]

    rework = context.get("rework_request")

    if isinstance(rework, dict):
        sections.extend(
            [
                "",
                "## Rework Request",
                *format_rework_request(rework),
            ]
        )

    if policy_corrections:
        sections.extend(
            [
                "",
                "## Required Corrections",
            ]
        )

        sections.extend(
            policy_corrections
        )

    sections.extend(
        [
            "",
            "## Project Configuration",
            repr(project),
            "",
            "## Workflow State",
            repr(state),
        ]
    )

    artifacts = dict(artifacts or {})

    binding_contracts = {
        path: artifacts.pop(path)
        for path in BINDING_CONTRACT_ARTIFACTS
        if isinstance(artifacts.get(path), str)
    }

    if binding_contracts:
        sections.extend(
            [
                "",
                "## Binding Contracts",
                "These documents fix the interfaces shared by every "
                "implementation unit. Implement them exactly: do not change "
                "a module path, function name, parameter, return value, "
                "exception, or output they define, and write tests that "
                "assert exactly what they define.",
            ]
        )

        for path, content in binding_contracts.items():
            sections.extend(
                [
                    "",
                    f"### {path}",
                    _truncate(
                        content.strip(),
                        MAX_BINDING_CONTRACT_CHARS,
                    ),
                ]
            )

    if artifacts:
        sections.extend(
            [
                "",
                "## Relevant Artifacts",
            ]
        )

        artifact_blocks, dropped_artifacts = _budgeted_blocks(
            {
                path: content.strip()
                for path, content in artifacts.items()
            },
            MAX_RELEVANT_ARTIFACT_CHARS,
            MAX_RELEVANT_ARTIFACTS_TOTAL_CHARS,
        )

        for path, content in artifact_blocks:
            sections.extend(
                [
                    "",
                    f"### {path}",
                    content,
                ]
            )

        if dropped_artifacts:
            sections.append(
                f"\n[{dropped_artifacts} further artifacts omitted "
                "to stay within the context budget]"
            )

    if human_input:
        sections.extend(
            [
                "",
                "## Human Input",
                human_input.strip(),
            ]
        )

    if workspace_files:
        sections.extend(
            [
                "",
                "## Current Workspace Files",
                "These files already exist in the project. Integrate with "
                "them: import what they define, keep their names, "
                "signatures, return values and tests, and change them only "
                "when this task requires it.",
            ]
        )

        workspace_blocks, dropped_workspace = _budgeted_blocks(
            workspace_files,
            MAX_WORKSPACE_FILE_CHARS,
            MAX_WORKSPACE_FILES_TOTAL_CHARS,
        )

        for path, content in workspace_blocks:
            sections.extend(
                [
                    "",
                    f"### {path}",
                    content,
                ]
            )

        if dropped_workspace:
            sections.append(
                f"\n[{dropped_workspace} further workspace files omitted "
                "to stay within the context budget]"
            )

    # Paths alone still explain what was tried. A replay whose durable
    # evidence was lost keeps the section rather than falling silent.
    contents_only_paths = [
        path
        for path in (failed_attempt_paths or [])
        if path not in (failed_attempt_files or {})
    ]

    if (
        failed_attempt_files
        or failed_attempt_generated_paths
        or contents_only_paths
    ):
        sections.extend(
            [
                "",
                "## Previous Failed Attempt",
                "These files were authored by the previous attempt at this "
                "task. They were rolled back and are NOT present in the "
                "workspace shown above.",
                "Use them to understand what was tried and why it failed.",
            ]
        )

        attempt_blocks, dropped_attempt = _budgeted_blocks(
            failed_attempt_files or {},
            MAX_FAILED_ATTEMPT_FILE_CHARS,
            MAX_FAILED_ATTEMPT_TOTAL_CHARS,
        )

        for path, content in attempt_blocks:
            sections.extend(
                [
                    "",
                    f"### {path}",
                    content,
                ]
            )

        if dropped_attempt:
            sections.append(
                f"\n[{dropped_attempt} further files omitted "
                "to stay within the context budget]"
            )

        if contents_only_paths:
            sections.extend(
                [
                    "",
                    "### Authored paths (contents unavailable)",
                    "This replay could not recover the durable contents of "
                    "the previous attempt: only the file paths of the "
                    "previous attempt were recovered.",
                    "These paths were authored by that attempt, were rolled "
                    "back, and are NOT present in the workspace above.",
                    "",
                    *(
                        f"- {path}"
                        for path in contents_only_paths
                    ),
                ]
            )

        if failed_attempt_generated_paths:
            sections.extend(
                [
                    "",
                    "### Generated by setup commands (content not supplied)",
                    "These artifacts were produced by the declared setup "
                    "commands, not authored by the agent. They are listed by "
                    "name only and will be regenerated on the next attempt.",
                    "",
                    *(
                        f"- {path}"
                        for path in failed_attempt_generated_paths
                    ),
                ]
            )

    if retry_test_results:
        sections.extend(
            [
                "",
                "## Previous Test Failures",
            ]
        )

        for test_result in retry_test_results:
            command = test_result.get(
                "command",
                "",
            )
            returncode = test_result.get(
                "returncode",
                "",
            )
            stdout = test_result.get(
                "stdout",
                "",
            )
            stderr = test_result.get(
                "stderr",
                "",
            )

            sections.extend(
                [
                    "",
                    f"Command: {command}",
                    f"Return code: {returncode}",
                    "",
                    "### stdout",
                    _head_and_tail(
                        str(stdout).strip(),
                        MAX_TEST_OUTPUT_CHARS,
                    ),
                    "",
                    "### stderr",
                    _head_and_tail(
                        str(stderr).strip(),
                        MAX_TEST_OUTPUT_CHARS,
                    ),
                ]
            )

        sections.extend(
            [
                "",
                "## Retry Instructions",
                "Preserve existing public APIs and unrelated behavior when fixing a retry.",
                "Treat current workspace files as the source of truth.",
                "Make the smallest change necessary to resolve supplied failures.",
                "On retry, return only files that actually need to change.",
                "Do not re-emit unchanged workspace files.",
                "Prefer a minimal repair over rewriting broad parts of the implementation.",
                "Do not return unrelated files merely because they were included in the workspace snapshot.",
                "Do not remove unrelated functions, exports, types, tests, configuration, or behavior.",
                "When returning an existing file, return the complete updated file while preserving unrelated content.",
                "If a failing test was generated as part of the implementation being retried, inspect whether the test itself is defective.",
                "If such a test asserts incidental whitespace, indentation, formatting, or semantically irrelevant ordering, repair the test instead of changing valid production code merely to satisfy incidental formatting.",
                "Preserve the intended behavioral or structural contract when repairing a generated test.",
                "Do not weaken tests merely to make them pass; change a test only when its assertion is stricter than the actual approved requirement or semantic contract.",
            ]
        )

    sections.extend(
        [
            "",
            "## Implementation Instructions",
            "Work only on this implementation task.",
            "Respect the approved architecture and selected technologies.",
            "Respect the approved UX/UI specifications.",
            "Do not implement unrelated features.",
            "Do not introduce architectural changes unless explicitly required.",
            "",
            "## Execution Responsibility",
            "You are responsible for generating the implementation, not for executing it.",
            "Return the complete contents of every file that must be created or modified.",
            "The AI Software Factory runtime will write those files to the project workspace.",
            "The AI Software Factory runtime will execute the test commands you return.",
            "Use setup_commands for dependency installation or environment preparation required before validation.",
            "Declare required dependencies in the project's dependency manifest, such as package.json.",
            "Do not add package names to setup_commands.",
            "For Node.js projects, dependency setup commands must be exactly npm install --ignore-scripts or npm ci --ignore-scripts.",
            "For Node.js dependency installation, use only: npm install --ignore-scripts or npm ci --ignore-scripts.",
            "For Prisma schema validation, use exactly: npm run prisma:validate.",
            "For Prisma client generation, use exactly: npm run prisma:generate.",
            "Prisma client generation is a setup command, not a test command.",
            "Put npm run prisma:generate in setup_commands, never in tests.",
            "Do not set DATABASE_URL inside test commands.",
            "The Factory runtime supplies validation environment variables when required.",
            "Do not put dependency installation commands in tests.",
            "Tests must contain validation commands only.",
            "Do not report inability to execute shell commands, install dependencies, run tests, or access the local runtime as a blocker.",
            "If dependencies are required, update the appropriate dependency or configuration files and return the commands that the runtime should execute.",
            "",
            "## Tests",
            "Prefer task-scoped test commands during implementation units.",
            "Do not use the full project test suite as the only validation for an intermediate implementation unit when narrower relevant tests are available.",
            "Reserve full-project verification for explicit integration or final verification units.",
            "For targeted Node.js tests, use: npm test -- <test-file>.",
            "For targeted Python tests, use: python -m pytest <test-file>.",
            "Every test file named in a test command must already exist in the workspace or be returned in the files of this same response.",
            "Never validate this task with a test file that a later task will create; write the tests for this task's code in this task.",
            "Do not use npx to execute test runners.",
            "Use the project's declared test script rather than invoking Vitest or another Node.js test runner directly.",
            "Include the automated tests required for this task.",
            "Generated tests must validate behavior, contracts, or semantic structure rather than incidental source formatting.",
            "Do not make tests depend on exact whitespace, indentation, or formatting when those differences do not change behavior.",
            "Do not depend on attribute, modifier, or declaration ordering unless that ordering is semantically significant.",
            "For structured configuration or schema files, prefer semantic assertions, parsing, or whitespace-tolerant matching over exact full-line string comparisons.",
            "Return test commands that can be executed from the project root.",
            "Do not claim that tests passed unless previous test results supplied in this prompt demonstrate that they passed.",
            "Fix the existing implementation when previous test failures are supplied.",
            "",
            "## Blockers",
            "Report a blocker only when the implementation itself cannot be produced safely from the supplied requirements and artifacts.",
            "Valid blockers include genuinely missing product requirements, required secrets or credentials, or an unresolved architectural decision that prevents implementation.",
            "The inability of the language model itself to execute commands is never a blocker.",
            "Do not report uncertainty about local workspace files as a blocker.",
            "Inspect and reconcile supplied workspace files instead.",
            "A possible import, export, type, test, configuration, or implementation mismatch in local files is an implementation problem to resolve, not a blocker.",
            "Do not use speculative blockers such as 'may', 'might', 'possibly', or 'if so' when the uncertainty can be resolved from supplied workspace context.",
            "Do not report local implementation defects as blockers.",
            "A failing test, type error, import/export mismatch, mock problem, schema mismatch, or local source defect must be fixed as part of the implementation task.",
            "If a supplied local file contains a correctable error, modify that file instead of returning a blocker.",
            "Do not invent missing requirements.",
        ]
    )

    return "\n".join(sections)
