from ai_factory.qa_prompt import (
    build_qa_prompt,
)


def test_build_qa_prompt_contains_independent_validation_context() -> None:
    context = {
        "project": {
            "name": "Test Project",
        },
        "requirements": [
            "Passenger can request a ride.",
        ],
        "acceptance_criteria": [
            "A valid ride request is persisted.",
        ],
        "architecture": {
            "style": "monolith",
        },
        "developer": {
            "implemented_files": [
                "src/rides.py",
                "tests/test_rides.py",
            ],
            "implementation_results": [
                {
                    "task_id": "US-001",
                    "summary": "Ride creation implemented.",
                }
            ],
        },
    }

    prompt = build_qa_prompt(
        context
    )

    assert "# QA Validation" in prompt
    assert "You are the independent QA Agent." in prompt

    assert "Passenger can request a ride." in prompt
    assert "A valid ride request is persisted." in prompt
    assert "monolith" in prompt

    assert "src/rides.py" in prompt
    assert "tests/test_rides.py" in prompt
    assert "US-001" in prompt

    assert (
        "Do not assume that the implementation is correct"
        in prompt
    )

    assert (
        "- Check every available acceptance criterion."
        in prompt
    )

    assert (
        "- Do not modify the implementation."
        in prompt
    )


def test_build_qa_prompt_handles_empty_context() -> None:
    prompt = build_qa_prompt(
        {}
    )

    assert "# QA Validation" in prompt
    assert "## Requirements" in prompt
    assert "## Acceptance Criteria" in prompt
    assert "## Developer Implementation" in prompt
    assert "## Implemented Files" in prompt


def test_build_qa_prompt_includes_artifacts_sources_and_executed_tests() -> None:
    prompt = build_qa_prompt(
        {
            "project": {"name": "Todo CLI"},
            "artifacts": {
                "knowledge/project/requirements.md": "IDs are never reused.",
                "design/ux-ui/screen-specs.md": "Empty list prints No todos.",
            },
            "human_input": "Errors go to stderr.",
            "implemented_sources": {
                "todo/service.py": "def complete_todo(data, raw_id): ...",
            },
            "executed_tests": [
                {
                    "command": "python -m pytest",
                    "returncode": 0,
                    "passed": True,
                    "stdout_tail": "46 passed",
                },
            ],
            "developer": {"implemented_files": ["todo/service.py"]},
        }
    )

    assert "## Approved Artifacts" in prompt
    assert "IDs are never reused." in prompt
    assert "Empty list prints No todos." in prompt
    assert "Errors go to stderr." in prompt
    assert "def complete_todo(data, raw_id)" in prompt
    assert "46 passed" in prompt
    assert "Never report that you cannot execute tests" in prompt


def test_build_qa_prompt_budgets_large_artifacts() -> None:
    prompt = build_qa_prompt(
        {
            "artifacts": {
                f"doc-{index}.md": "x" * 9000
                for index in range(10)
            },
        }
    )

    assert "[truncated:" in prompt
    assert "[further artifacts omitted" in prompt
