from typing import Any

from ai_factory.agent_result import AgentResult
from ai_factory.technology_gate import (
    is_technology_gate_required,
    submit_technology_proposal,
)


def build_technology_proposal_from_architect_result(
    result: AgentResult,
) -> dict[str, Any]:
    """Build a technology proposal from an Architect Agent result."""

    proposal = result.metadata.get(
        "technology_proposal"
    )

    if not isinstance(proposal, dict) or not proposal:
        raise ValueError(
            "Architect result does not contain a technology proposal."
        )

    return proposal


def update_technology_gate_from_architect_result(
    state: dict[str, Any],
    config: dict[str, Any],
    result: AgentResult,
) -> dict[str, Any]:
    """Submit the Architect technology proposal when the gate is required."""

    if not is_technology_gate_required(config):
        return state

    proposal = build_technology_proposal_from_architect_result(
        result
    )

    return submit_technology_proposal(
        state=state,
        config=config,
        proposal=proposal,
    )
