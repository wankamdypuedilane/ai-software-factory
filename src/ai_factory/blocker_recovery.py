"""Public resolution path for legitimate gate blockers.

A gate that carries a blocker nobody can clear is a permanent deadlock. A
real external dependency is resolved outside the Factory; this records that
resolution so the gate can move on, and so that rebuilding the gate from the
same persisted result does not resurrect it.
"""

from typing import Any

from ai_factory.approvals import VALID_APPROVALS


GATE_BY_APPROVAL = {
    "design": "design_gate",
    "development": "development_gate",
    "qa": "qa_gate",
    "security": "security_gate",
    "devops": "devops_gate",
    "sre": "sre_gate",
}


def resolve_gate_blockers(
    state: dict[str, Any],
    approval_name: str,
    messages: list[str] | None = None,
) -> dict[str, Any]:
    """Record that the human resolved a gate's external blockers.

    Resolution is attached to the approval that owns the gate rather than to
    a parallel command set: the person who clears a blocker is the person who
    then approves the gate.
    """

    if approval_name not in VALID_APPROVALS:
        raise ValueError(
            f"Unknown approval: {approval_name}"
        )

    gate_name = GATE_BY_APPROVAL.get(approval_name)

    if gate_name is None:
        raise ValueError(
            f"Approval '{approval_name}' does not own a gate "
            "with external blockers."
        )

    gate = state.get(gate_name)

    if not isinstance(gate, dict):
        raise ValueError(
            f"Project state does not contain a valid {gate_name}."
        )

    external_blockers = gate.get("external_blockers", [])

    if not isinstance(external_blockers, list):
        raise ValueError(
            f"{gate_name} external_blockers must be a list."
        )

    targets = (
        list(messages)
        if messages is not None
        else list(external_blockers)
    )

    if not targets:
        raise ValueError(
            f"The {gate_name} has no external blocker to resolve."
        )

    unknown = [
        message
        for message in targets
        if message not in external_blockers
    ]

    if unknown:
        raise ValueError(
            "These blockers are not present on the "
            f"{gate_name}: {', '.join(unknown)}"
        )

    resolved = gate.get("resolved_blockers", [])

    if not isinstance(resolved, list):
        resolved = []

    gate["resolved_blockers"] = list(
        dict.fromkeys(
            [
                *resolved,
                *targets,
            ]
        )
    )

    gate["external_blockers"] = [
        message
        for message in external_blockers
        if message not in targets
    ]

    return state
