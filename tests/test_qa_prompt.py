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
