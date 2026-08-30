from ai_factory.test_result_serialization import (
    serialize_test_result,
    serialize_test_results,
    truncate_test_output,
)
from ai_factory.test_runner import (
    CommandExecutionResult,
)


def test_truncate_test_output_keeps_short_output() -> None:
    value = "short output"

    result = truncate_test_output(
        value,
        max_chars=100,
    )

    assert result == value


def test_truncate_test_output_truncates_long_output() -> None:
    value = "A" * 5000

    result = truncate_test_output(
        value,
        max_chars=100,
    )

    assert result.startswith("A" * 100)
    assert "[Test output truncated]" in result
    assert len(result) < len(value)


def test_serialize_test_result() -> None:
    result = CommandExecutionResult(
        command="python -m pytest tests/test_auth.py -q",
        returncode=1,
        stdout="failed output",
        stderr="traceback",
    )

    serialized = serialize_test_result(
        result
    )

    assert serialized == {
        "command": "python -m pytest tests/test_auth.py -q",
        "returncode": 1,
        "passed": False,
        "stdout": "failed output",
        "stderr": "traceback",
    }


def test_serialize_test_results() -> None:
    results = [
        CommandExecutionResult(
            command="pytest tests/test_one.py",
            returncode=0,
            stdout="1 passed",
            stderr="",
        ),
        CommandExecutionResult(
            command="pytest tests/test_two.py",
            returncode=1,
            stdout="1 failed",
            stderr="error",
        ),
    ]

    serialized = serialize_test_results(
        results
    )

    assert len(serialized) == 2
    assert serialized[0]["passed"] is True
    assert serialized[1]["passed"] is False
