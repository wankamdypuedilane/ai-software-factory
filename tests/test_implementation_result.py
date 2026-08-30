from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)


def test_implementation_result_stores_file_changes() -> None:
    result = ImplementationResult(
        task_id="US-001",
        summary="Passenger authentication implemented.",
        files=[
            ImplementationFileChange(
                path="src/accounts/models.py",
                content="# models",
            ),
            ImplementationFileChange(
                path="tests/test_auth.py",
                content="# tests",
            ),
        ],
        tests=[
            "pytest tests/test_auth.py",
        ],
    )

    assert result.task_id == "US-001"
    assert result.summary == "Passenger authentication implemented."

    assert len(result.files) == 2
    assert result.files[0].path == "src/accounts/models.py"
    assert result.files[0].content == "# models"
    assert result.files[0].operation == "write"

    assert result.tests == [
        "pytest tests/test_auth.py",
    ]

    assert result.blockers == []


def test_implementation_result_defaults_are_independent() -> None:
    first = ImplementationResult(
        task_id="US-001",
        summary="First task.",
    )

    second = ImplementationResult(
        task_id="US-002",
        summary="Second task.",
    )

    first.tests.append(
        "pytest tests/test_first.py"
    )

    first.blockers.append(
        "Missing dependency."
    )

    assert first.tests == [
        "pytest tests/test_first.py"
    ]
    assert second.tests == []

    assert first.blockers == [
        "Missing dependency."
    ]
    assert second.blockers == []


def test_implementation_file_change_defaults_to_write() -> None:
    change = ImplementationFileChange(
        path="src/app.py",
        content="print('hello')",
    )

    assert change.operation == "write"
