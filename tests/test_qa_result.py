from ai_factory.qa_result import (
    QADefect,
    QAResult,
)


def test_qa_result_stores_defects_and_test_commands() -> None:
    defect = QADefect(
        id="QA-001",
        title="Invalid credentials return wrong status",
        severity="High",
        related_story="US-001",
        expected="401 response",
        actual="500 response",
    )

    result = QAResult(
        summary="Authentication validation completed.",
        passed=False,
        defects=[
            defect,
        ],
        test_commands=[
            "python -m pytest tests/test_auth.py -q",
        ],
    )

    assert result.summary == (
        "Authentication validation completed."
    )

    assert result.passed is False
    assert len(result.defects) == 1

    assert result.defects[0].id == "QA-001"
    assert result.defects[0].severity == "High"
    assert result.defects[0].related_story == "US-001"

    assert result.test_commands == [
        "python -m pytest tests/test_auth.py -q",
    ]

    assert result.blockers == []


def test_qa_result_defaults_are_independent() -> None:
    first = QAResult(
        summary="First QA run.",
        passed=True,
    )

    second = QAResult(
        summary="Second QA run.",
        passed=True,
    )

    first.test_commands.append(
        "pytest"
    )

    first.blockers.append(
        "Missing environment."
    )

    assert first.test_commands == [
        "pytest"
    ]
    assert second.test_commands == []

    assert first.blockers == [
        "Missing environment."
    ]
    assert second.blockers == []
