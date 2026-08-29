from typing import Any

from ai_factory.technology import validate_technology_decision


def validate_technology_gate(
    config: dict[str, Any],
    proposal: dict[str, Any],
) -> None:
    """Validate whether a technology proposal can enter human review."""

    validate_technology_decision(
        config,
        proposal,
    )


def is_technology_gate_approved(
    state: dict[str, Any],
) -> bool:
    """Return True when the technology decision has human approval."""

    gate = state.get("technology_gate")

    if not isinstance(gate, dict):
        return False

    return (
        gate.get("status") == "APPROVED"
        and gate.get("human_approval") is True
    )


def is_technology_gate_required(
    config: dict[str, Any],
) -> bool:
    """Return whether the project requires a technology approval gate."""

    technology = config.get("technology")

    if not isinstance(technology, dict):
        return False

    selection_mode = technology.get("selection_mode")

    return selection_mode in {
        "recommend",
        "constrained",
    }


def submit_technology_proposal(
    state: dict[str, Any],
    config: dict[str, Any],
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """Validate and submit a technology proposal for human review."""

    validate_technology_gate(
        config,
        proposal,
    )

    gate = state.get("technology_gate")

    if not isinstance(gate, dict):
        raise ValueError(
            "Project state does not contain a valid technology_gate."
        )

    gate["proposal"] = proposal
    gate["status"] = "REVIEW_REQUIRED"
    gate["human_approval"] = False

    return state


def approve_technology_gate(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Record explicit human approval of a reviewed technology proposal."""

    gate = state.get("technology_gate")

    if not isinstance(gate, dict):
        raise ValueError(
            "Project state does not contain a valid technology_gate."
        )

    if gate.get("status") != "REVIEW_REQUIRED":
        raise ValueError(
            "Technology Gate can only be approved "
            "when review is required."
        )

    proposal = gate.get("proposal")

    if not isinstance(proposal, dict) or not proposal:
        raise ValueError(
            "Technology Gate cannot be approved "
            "without a proposal."
        )

    gate["status"] = "APPROVED"
    gate["human_approval"] = True

    return state
