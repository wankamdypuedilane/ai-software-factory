from ai_factory.test_runner import (
    CommandExecutionResult,
)


MAX_TEST_OUTPUT_CHARS = 2000


def truncate_test_output(
    value: str | None,
    max_chars: int = MAX_TEST_OUTPUT_CHARS,
) -> str:
    """Truncate persisted test output to keep Factory state compact."""

    if value is None:
        return ""

    if len(value) <= max_chars:
        return value

    # Keep both ends: runners print what ran at the top and the assertion
    # that explains a failure at the bottom. A real run kept only the top
    # and cut the one line the Developer needed, twice in a row.
    head = max_chars * 2 // 5
    tail = max_chars - head
    omitted = len(value) - head - tail

    return (
        value[:head].rstrip()
        + f"\n\n[Test output truncated: {omitted} characters omitted]\n\n"
        + value[-tail:].lstrip()
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
