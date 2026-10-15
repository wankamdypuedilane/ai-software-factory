from ai_factory.implementation_prompt import (
    build_implementation_prompt,
)
from ai_factory.implementation_request import (
    ImplementationTask,
)


def test_build_implementation_prompt_contains_task_details() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-001",
        title="Passenger authentication",
        purpose="Implement authentication with automated tests.",
    )

    context = {
        "project": {
            "project": {
                "name": "Test Project",
            },
            "technology": {
                "selected": {
                    "backend": {
                        "technology": "Django",
                    }
                }
            },
        },
        "state": {
            "agents": {
                "developer": {
                    "status": "READY",
                }
            }
        },
        "artifacts": {
            "knowledge/project/requirements.md": (
                "# Requirements\n\nAuthentication is required."
            ),
            "knowledge/architecture/system-design.md": (
                "# Architecture\n\nUse a monolithic web application."
            ),
        },
        "human_input": None,
    }

    prompt = build_implementation_prompt(
        task,
        context,
    )

    assert "# Implementation Task" in prompt
    assert "Agent: developer" in prompt
    assert "Task ID: US-001" in prompt
    assert "Title: Passenger authentication" in prompt
    assert (
        "Implement authentication with automated tests."
        in prompt
    )
    assert "Test Project" in prompt
    assert "Django" in prompt
    assert "## Relevant Artifacts" in prompt
    assert "Authentication is required." in prompt
    assert "Use a monolithic web application." in prompt
    assert "Work only on this implementation task." in prompt
    assert "Include the automated tests required for this task." in prompt


def test_build_implementation_prompt_includes_human_input() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-002",
        title="Ride request workflow",
        purpose="Implement ride creation.",
    )

    context = {
        "project": {},
        "state": {},
        "artifacts": {},
        "human_input": (
            "Keep the implementation intentionally small."
        ),
    }

    prompt = build_implementation_prompt(
        task,
        context,
    )

    assert "## Human Input" in prompt
    assert (
        "Keep the implementation intentionally small."
        in prompt
    )


def test_build_implementation_prompt_omits_optional_sections() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-003",
        title="Ride completion",
        purpose="Implement ride completion.",
    )

    context = {
        "project": {},
        "state": {},
        "artifacts": {},
        "human_input": None,
    }

    prompt = build_implementation_prompt(
        task,
        context,
    )

    assert "## Relevant Artifacts" not in prompt
    assert "## Human Input" not in prompt


def test_build_implementation_prompt_includes_retry_test_failures() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-002",
        title="Ride creation",
        purpose="Implement ride creation.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
            "human_input": None,
        },
        retry_test_results=[
            {
                "command": (
                    "python -m pytest "
                    "tests/test_rides.py -q"
                ),
                "returncode": 1,
                "passed": False,
                "stdout": "1 failed",
                "stderr": "AssertionError",
            }
        ],
    )

    assert "## Previous Test Failures" in prompt
    assert (
        "python -m pytest tests/test_rides.py -q"
        in prompt
    )
    assert "Return code: 1" in prompt
    assert "1 failed" in prompt
    assert "AssertionError" in prompt

    assert (
        "Fix the existing implementation when previous "
        "test failures are supplied."
        in prompt
    )


def test_implementation_prompt_defines_runtime_execution_responsibility() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Create foundation",
        purpose="Create the application foundation.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert (
        "You are responsible for generating the implementation, "
        "not for executing it."
        in prompt
    )

    assert (
        "The AI Software Factory runtime will write those files "
        "to the project workspace."
        in prompt
    )

    assert (
        "The AI Software Factory runtime will execute the test commands "
        "you return."
        in prompt
    )

    assert (
        "The inability of the language model itself to execute commands "
        "is never a blocker."
        in prompt
    )


def test_implementation_prompt_separates_setup_commands_from_tests() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Create foundation",
        purpose="Create the application foundation.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert "setup_commands" in prompt
    assert "npm install --ignore-scripts" in prompt

    assert (
        "Do not put dependency installation commands in tests."
        in prompt
    )

    assert (
        "Tests must contain validation commands only."
        in prompt
    )


def test_implementation_prompt_defines_safe_retry_rules() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Create foundation",
        purpose="Create the application foundation.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
        retry_test_results=[
            {
                "command": "npm test",
                "returncode": 1,
                "stdout": "failed",
                "stderr": "",
            }
        ],
        workspace_files={
            "src/lib/http.ts": "export function parseJson() {}",
        },
    )

    assert "Treat current workspace files as the source of truth." in prompt
    assert "Make the smallest change necessary" in prompt
    assert (
        "Do not remove unrelated functions, exports, types, tests"
        in prompt
    )


def test_implementation_prompt_requires_dependencies_in_manifest() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Add persistence",
        purpose="Add Prisma persistence.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert (
        "Declare required dependencies in the project's dependency manifest"
        in prompt
    )
    assert (
        "Do not add package names to setup_commands."
        in prompt
    )
    assert (
        "npm install --ignore-scripts"
        in prompt
    )


def test_implementation_prompt_requires_canonical_prisma_validation_command() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Add persistence",
        purpose="Add Prisma persistence.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert (
        "For Prisma schema validation, use exactly: npm run prisma:validate"
        in prompt
    )
    assert (
        "Do not set DATABASE_URL inside test commands."
        in prompt
    )


def test_implementation_prompt_requires_canonical_prisma_generation_command() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Add persistence",
        purpose="Add Prisma persistence.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert (
        "For Prisma client generation, use exactly: npm run prisma:generate."
        in prompt
    )


def test_implementation_prompt_requires_semantic_tests_over_formatting() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Add persistence",
        purpose="Add Prisma persistence.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert (
        "Generated tests must validate behavior, contracts, or semantic structure"
        in prompt
    )
    assert (
        "Do not make tests depend on exact whitespace, indentation, or formatting"
        in prompt
    )
    assert (
        "For structured configuration or schema files, prefer semantic assertions"
        in prompt
    )


def test_retry_prompt_allows_repairing_task_generated_brittle_tests() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-DATA-SCHEMA",
        title="Data schema",
        purpose="Implement the Prisma data schema.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
        retry_test_results=[
            {
                "command": "npm test",
                "returncode": 1,
                "passed": False,
                "stdout": (
                    "prisma/schema.contract.test.ts: "
                    "expected exact whitespace"
                ),
                "stderr": "",
            }
        ],
        workspace_files={
            "prisma/schema.prisma": "model User {}",
            "prisma/schema.contract.test.ts": (
                "expect(schema).toContain("
                "'passwordHash String    @map(...)'"
                ");"
            ),
        },
    )

    assert (
        "If a failing test was generated as part of the implementation being retried"
        in prompt
    )
    assert (
        "repair the test instead of changing valid production code merely to satisfy incidental formatting"
        in prompt
    )


def test_retry_prompt_requires_minimal_file_changes() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Repair the failing repository task.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
        retry_test_results=[
            {
                "command": "npm run typecheck",
                "returncode": 2,
                "passed": False,
                "stdout": "src/modules/tasks/task-repository.ts: error",
                "stderr": "",
            }
        ],
        workspace_files={
            "src/modules/tasks/task-repository.ts": "export const x = 1;",
            "src/modules/tasks/task-repository.test.ts": "test('x', () => {});",
        },
    )

    assert (
        "On retry, return only files that actually need to change."
        in prompt
    )
    assert (
        "Do not re-emit unchanged workspace files."
        in prompt
    )


def test_implementation_prompt_prefers_task_scoped_validation() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Implement the ownership-scoped task repository.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert (
        "Prefer task-scoped test commands during implementation units."
        in prompt
    )
    assert (
        "Do not use the full project test suite as the only validation "
        "for an intermediate implementation unit when narrower relevant "
        "tests are available."
        in prompt
    )
    assert (
        "Reserve full-project verification for explicit integration or "
        "final verification units."
        in prompt
    )


def test_implementation_prompt_requires_canonical_targeted_node_test_command() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Task repository",
        purpose="Implement task repository.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert (
        "For targeted Node.js tests, use: npm test -- <test-file>."
        in prompt
    )
    assert (
        "Do not use npx to execute test runners."
        in prompt
    )


def test_implementation_prompt_forbids_speculative_workspace_blockers() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Implementation",
        purpose="Implement feature.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert (
        "Do not report uncertainty about local workspace files as a blocker."
        in prompt
    )
    assert (
        "Inspect and reconcile supplied workspace files instead."
        in prompt
    )


def test_implementation_prompt_classifies_prisma_generate_as_setup() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Persistence",
        purpose="Prepare Prisma persistence.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert (
        "Prisma client generation is a setup command, not a test command."
        in prompt
    )

    assert (
        "Put npm run prisma:generate in setup_commands, never in tests."
        in prompt
    )


def test_build_implementation_prompt_omits_corrections_by_default() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Implement the task repository.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
    )

    assert "## Required Corrections" not in prompt


def test_build_implementation_prompt_renders_policy_corrections() -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Implement the task repository.",
    )

    prompt = build_implementation_prompt(
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
        },
        policy_corrections=[
            "Rejected test command: npm test",
            "Scope the replacement command to those test files.",
        ],
    )

    assert "## Required Corrections" in prompt
    assert "Rejected test command: npm test" in prompt
    assert (
        "Scope the replacement command to those test files."
        in prompt
    )

    assert prompt.index(
        "## Required Corrections"
    ) < prompt.index(
        "## Project Configuration"
    )


def test_implementation_prompt_requires_existing_or_written_test_files() -> None:
    from ai_factory.implementation_prompt import build_implementation_prompt
    from ai_factory.implementation_request import ImplementationTask

    prompt = build_implementation_prompt(
        task=ImplementationTask(
            agent_name="developer",
            id="todo-cli",
            title="CLI",
            purpose="Implement the CLI.",
        ),
        context={},
    )

    assert "python -m pytest <test-file>" in prompt
    assert "a later task will create" in prompt


def test_binding_contracts_come_first_and_are_not_squeezed_out() -> None:
    from ai_factory.implementation_prompt import build_implementation_prompt
    from ai_factory.implementation_request import ImplementationTask

    filler = {
        f"knowledge/project/doc-{index}.md": "x" * 4000
        for index in range(10)
    }
    interfaces = "complete_todo(data, raw_id) -> bool\n" + "y" * 6000

    prompt = build_implementation_prompt(
        task=ImplementationTask(
            agent_name="developer",
            id="todo-cli",
            title="CLI",
            purpose="Implement the CLI.",
        ),
        context={
            "artifacts": {
                **filler,
                "knowledge/architecture/interfaces.md": interfaces,
            },
        },
    )

    assert "## Binding Contracts" in prompt
    assert interfaces in prompt
    assert prompt.index("## Binding Contracts") < prompt.index(
        "## Relevant Artifacts"
    )
    assert prompt.count("### knowledge/architecture/interfaces.md") == 1


def test_no_binding_contract_section_without_contract_artifacts() -> None:
    from ai_factory.implementation_prompt import build_implementation_prompt
    from ai_factory.implementation_request import ImplementationTask

    prompt = build_implementation_prompt(
        task=ImplementationTask(
            agent_name="developer",
            id="task",
            title="Task",
            purpose="Do it.",
        ),
        context={"artifacts": {"knowledge/project/vision.md": "v"}},
    )

    assert "## Binding Contracts" not in prompt
