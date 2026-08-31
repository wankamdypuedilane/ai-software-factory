from ai_factory.devops_result import (
    DevOpsChange,
    DevOpsResult,
)


def test_devops_result_stores_changes_and_deployment_state() -> None:
    change = DevOpsChange(
        path=".github/workflows/ci.yml",
        description="Add CI pipeline.",
        category="ci_cd",
    )

    result = DevOpsResult(
        summary="DevOps automation completed.",
        passed=True,
        changes=[
            change,
        ],
        test_commands=[
            "python -m pytest -q",
        ],
        deployment_ready=True,
        rollback_strategy=(
            "Redeploy the previous stable release."
        ),
    )

    assert result.summary == (
        "DevOps automation completed."
    )

    assert result.passed is True
    assert len(result.changes) == 1

    assert result.changes[0].path == (
        ".github/workflows/ci.yml"
    )
    assert result.changes[0].category == "ci_cd"

    assert result.test_commands == [
        "python -m pytest -q",
    ]

    assert result.blockers == []
    assert result.deployment_ready is True

    assert result.rollback_strategy == (
        "Redeploy the previous stable release."
    )


def test_devops_result_defaults_are_independent() -> None:
    first = DevOpsResult(
        summary="First DevOps run.",
        passed=True,
    )

    second = DevOpsResult(
        summary="Second DevOps run.",
        passed=True,
    )

    first.changes.append(
        DevOpsChange(
            path="Dockerfile",
            description="Add container image.",
            category="container",
        )
    )

    first.blockers.append(
        "Deployment credentials unavailable."
    )

    assert len(first.changes) == 1
    assert second.changes == []

    assert first.blockers == [
        "Deployment credentials unavailable."
    ]
    assert second.blockers == []

    assert first.deployment_ready is False
    assert second.deployment_ready is False
