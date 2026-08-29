import pytest

from ai_factory.agent_result import AgentResult
from ai_factory.result_policy import get_agent_status_from_result


@pytest.mark.parametrize(
    ("result_status", "expected_agent_status"),
    [
        ("NEEDS_INPUT", "BLOCKED"),
        ("BLOCKED", "BLOCKED"),
        ("REVIEW_REQUIRED", "REVIEW_REQUIRED"),
        ("COMPLETED", "REVIEW_REQUIRED"),
    ],
)
def test_get_agent_status_from_result_maps_supported_statuses(
    result_status,
    expected_agent_status,
) -> None:
    result = AgentResult(
        status=result_status,
        summary="Test result.",
    )

    assert (
        get_agent_status_from_result(result)
        == expected_agent_status
    )


def test_get_agent_status_from_result_rejects_unknown_status() -> None:
    result = AgentResult(
        status="UNKNOWN",
        summary="Unknown result.",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported agent result status",
    ):
        get_agent_status_from_result(result)
