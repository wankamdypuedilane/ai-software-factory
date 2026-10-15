from typing import Any


# Agents whose APPROVED status belongs to an approval. Reaching APPROVED for
# one of them must also record the approval and activate the next agent, so
# only the approval flow may perform that transition.
APPROVAL_AGENT_MAP = {
    "product_scope": "product",
    "design": "ux_ui",
    "architecture": "architect",
    "development": "developer",
    "qa": "qa",
    "security": "security",
    "devops": "devops",
    "sre": "sre",
}

APPROVAL_BY_AGENT = {
    agent_name: approval_name
    for approval_name, agent_name in APPROVAL_AGENT_MAP.items()
}


VALID_APPROVALS = {
    "product_scope",
    "design",
    "architecture",
    "development",
    "qa",
    "security",
    "devops",
    "sre",
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

    if approval_name == "production_deployment":
        raise ValueError(
            "Production deployment approval must be "
            "applied through the Production Gate."
        )

    approvals = state.get("approvals")

    if not isinstance(approvals, dict):
        raise ValueError(
            "Project state does not contain valid approvals."
        )

    approvals[approval_name] = True

    return state
