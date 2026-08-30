from dataclasses import dataclass, field
from typing import Any


@dataclass
class DevelopmentGateResult:
    ready: bool
    reasons: list[str] = field(
        default_factory=list
    )


def evaluate_development_gate(
    developer_state: dict[str, Any],
) -> DevelopmentGateResult:
    """Determine whether Developer output is ready for QA."""

    last_result = developer_state.get(
        "last_result"
    )

    if not isinstance(last_result, dict):
        return DevelopmentGateResult(
            ready=False,
            reasons=[
                "Developer does not contain a valid result."
            ],
        )

    if last_result.get(
        "implementation_blocked"
    ) is True:
        return DevelopmentGateResult(
            ready=False,
            reasons=[
                "Developer implementation is blocked."
            ],
        )

    if last_result.get(
        "implementation_test_failed"
    ) is True:
        return DevelopmentGateResult(
            ready=False,
            reasons=[
                "Developer implementation tests failed."
            ],
        )

    implementation_results = last_result.get(
        "implementation_results",
        []
    )

    if not implementation_results:
        return DevelopmentGateResult(
            ready=False,
            reasons=[
                "Developer has no implementation results."
            ],
        )

    failed_tests = [
        result
        for result in last_result.get(
            "test_results",
            []
        )
        if isinstance(result, dict)
        and result.get("passed") is False
    ]

    if failed_tests:
        return DevelopmentGateResult(
            ready=False,
            reasons=[
                "Developer contains failing test results."
            ],
        )

    return DevelopmentGateResult(
        ready=True
    )
