from typing import Any


VALID_APPROVALS = {
    "product_scope",
    "design",
    "architecture",
    "production_deployment",
}


def approve(
    state: dict[str, Any],
    approval_name: str,
) -> dict[str, Any]:
    """Record an explicit human approval."""

    if approval_name not in VALID_APPROVALS:
        raise ValueError(
            f"Unknown approval: {approval_name}"
        )

    approvals = state.get("approvals")

    if not isinstance(approvals, dict):
        raise ValueError(
            "Project state does not contain valid approvals."
        )

    approvals[approval_name] = True

    return state