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
