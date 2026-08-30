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
