from ai_factory.test_runner import (
    CommandExecutionResult,
)


MAX_TEST_OUTPUT_CHARS = 2000


def truncate_test_output(
    value: str,
    max_chars: int = MAX_TEST_OUTPUT_CHARS,
) -> str:
    """Truncate persisted test output to keep Factory state compact."""

    if len(value) <= max_chars:
        return value

    return (
        value[:max_chars].rstrip()
        + "\n\n[Test output truncated]"
    )


def serialize_test_result(
    result: CommandExecutionResult,
) -> dict:
    """Serialize one test execution result for persistent state."""

    return {
        "command": result.command,
        "returncode": result.returncode,
        "passed": result.passed,
        "stdout": truncate_test_output(
            result.stdout,
        ),
        "stderr": truncate_test_output(
            result.stderr,
        ),
    }


def serialize_test_results(
    results: list[CommandExecutionResult],
) -> list[dict]:
    """Serialize test execution results for persistent state."""

    return [
        serialize_test_result(result)
        for result in results
    ]
