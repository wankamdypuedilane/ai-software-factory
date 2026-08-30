from typing import Any

from ai_factory.agent_result import AgentResult
from ai_factory.technology_gate import (
    is_technology_gate_required,
    submit_technology_proposal,
)


def build_technology_proposal_from_architect_result(
    result: AgentResult,
) -> dict[str, Any]:
    """Build a Technology Gate proposal from Architect metadata."""

    raw_proposal = result.metadata.get(
        "technology_proposal"
    )

    if not isinstance(raw_proposal, dict):
        raise ValueError(
            "Architect result does not contain a technology proposal."
        )

    raw_components = raw_proposal.get(
        "components"
    )

    if not isinstance(raw_components, list) or not raw_components:
        raise ValueError(
            "Architect technology proposal does not contain components."
        )

    components: dict[str, Any] = {}

    for component in raw_components:
        if not isinstance(component, dict):
            raise ValueError(
                "Invalid technology proposal component."
            )

        name = component.get("name")
        technology = component.get("technology")
        rationale = component.get("rationale")

        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                "Technology component name is required."
            )

        if not isinstance(technology, str) or not technology.strip():
            raise ValueError(
                f"Technology is required for component '{name}'."
            )

        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(
                f"Rationale is required for component '{name}'."
            )

        components[name] = {
            "technology": technology,
            "rationale": rationale,
        }

    return {
        "components": components,
    }


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
