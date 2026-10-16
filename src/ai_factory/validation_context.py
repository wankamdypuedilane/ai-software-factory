"""Evidence supplied to the QA, Security, DevOps and SRE validators.

A real run showed QA returning passed=false on a correct project because its
prompt held file names only: no requirement text, no source, no executed test.
A validator cannot judge what it is not shown, so every validator receives
the implemented sources and the Developer's executed test results, and the
same rules about what the Factory executes on its behalf.
"""

from pathlib import Path
from typing import Any


MAX_SOURCE_FILE_CHARS = 8000
MAX_SOURCE_TOTAL_CHARS = 60000
MAX_TEST_OUTPUT_TAIL_CHARS = 2000

VALIDATION_EXECUTION_RULES = (
    "The Factory runtime executes every test command you return, after your "
    "response, and decides the outcome from those executed results together "
    "with your verdict.",
    "Never report that you cannot execute tests, or that execution results "
    "are missing, as a blocker or as a reason for passed=false: return the "
    "commands that produce the evidence instead.",
    "Judge the supplied source files and approved artifacts directly; they "
    "are the implementation under review.",
    "Assess only what applies to this project's approved scope and "
    "architecture. Missing components the approved architecture does not "
    "call for (servers, containers, CI pipelines, monitoring, dashboards for "
    "a local command-line tool, for example) are not defects or blockers.",
    "Set passed=false only for a concrete defect or risk you can point to in "
    "the supplied evidence.",
    "Findings of Low or Informational severity are reported but never set "
    "passed=false on their own.",
)


def _truncate(
    content: str,
    limit: int,
) -> str:
    if len(content) <= limit:
        return content

    omitted = len(content) - limit

    return (
        content[:limit]
        + f"\n[truncated: {omitted} characters omitted]"
    )


def load_implemented_sources(
    project_root: Path,
    developer_result: dict[str, Any],
) -> dict[str, str]:
    """Return the current content of the files the Developer implemented."""

    paths = developer_result.get("implemented_files", [])

    if not isinstance(paths, list):
        return {}

    root = Path(project_root).resolve()
    sources: dict[str, str] = {}
    used = 0

    for relative_path in paths:
        if used >= MAX_SOURCE_TOTAL_CHARS:
            break

        if not isinstance(relative_path, str) or not relative_path.strip():
            continue

        path = (root / relative_path).resolve()

        # Only files inside the project are ever read.
        if root not in path.parents or not path.is_file():
            continue

        try:
            content = path.read_text(
                encoding="utf-8",
            )
        except (OSError, UnicodeDecodeError):
            continue

        trimmed = _truncate(
            content,
            min(
                MAX_SOURCE_FILE_CHARS,
                MAX_SOURCE_TOTAL_CHARS - used,
            ),
        )

        sources[relative_path] = trimmed
        used += len(trimmed)

    return sources


def summarize_executed_tests(
    developer_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return the Developer's executed test commands and their outcome."""

    results = developer_result.get("test_results", [])

    if not isinstance(results, list):
        return []

    summary: list[dict[str, Any]] = []

    for item in results:
        if not isinstance(item, dict):
            continue

        returncode = item.get("returncode")
        stdout = str(item.get("stdout", "") or "")

        summary.append(
            {
                "command": item.get("command"),
                "returncode": returncode,
                "passed": returncode == 0,
                "stdout_tail": stdout[-MAX_TEST_OUTPUT_TAIL_CHARS:],
            }
        )

    return summary


def add_validation_evidence(
    context: dict[str, Any],
    project_root: Path,
    developer_result: dict[str, Any],
) -> dict[str, Any]:
    """Return a copy of a validator context with the implementation evidence."""

    enriched = dict(context)

    enriched["implemented_sources"] = load_implemented_sources(
        project_root=project_root,
        developer_result=developer_result,
    )
    enriched["executed_tests"] = summarize_executed_tests(
        developer_result,
    )
    enriched["validation_rules"] = list(VALIDATION_EXECUTION_RULES)

    return enriched


def build_validation_outcome(
    agent_name: str,
    execution: Any,
) -> dict[str, Any]:
    """Describe this cycle's validation outcome for the agent's report.

    The report is generated after the validation ran, but from a context
    built before it, whose workflow state still holds the previous cycle. A
    real run produced a QA report saying "46 tests, do not approve" next to a
    gate that had just passed 50 tests.
    """

    result = execution.result

    items: list[Any] = []

    for field_name in ("defects", "findings", "changes"):
        values = getattr(result, field_name, None)

        if isinstance(values, list):
            items.extend(
                getattr(value, "__dict__", value)
                for value in values
            )

    return {
        "agent": agent_name,
        "passed": bool(execution.passed),
        "summary": getattr(result, "summary", ""),
        "items": items,
        "blockers": [
            getattr(blocker, "__dict__", blocker)
            for blocker in getattr(result, "blockers", []) or []
        ],
        "executed_tests": [
            {
                "command": test_result.command,
                "returncode": test_result.returncode,
                "passed": test_result.returncode == 0,
                "stdout_tail": (
                    test_result.stdout or ""
                )[-MAX_TEST_OUTPUT_TAIL_CHARS:],
            }
            for test_result in getattr(execution, "test_results", []) or []
        ],
    }
