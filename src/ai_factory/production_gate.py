from dataclasses import dataclass
from typing import Any


@dataclass
class ProductionGateEvaluation:
    ready: bool
    reasons: list[str]


def evaluate_production_gate(
    state: dict[str, Any],
) -> ProductionGateEvaluation:
    """Evaluate whether the project is ready for production approval."""

    reasons: list[str] = []

    agents = state.get("agents", {})
    approvals = state.get("approvals", {})

    sre = agents.get("sre")

    if not isinstance(sre, dict):
        reasons.append(
            "Project state does not contain a valid SRE agent."
        )
    elif sre.get("status") != "APPROVED":
        reasons.append(
            "SRE is not approved."
        )

    sre_gate = state.get("sre_gate")

    if not isinstance(sre_gate, dict):
        reasons.append(
            "Project state does not contain a valid SRE Gate."
        )
    else:
        if sre_gate.get("status") != "APPROVED":
            reasons.append(
                "SRE Gate is not approved."
            )

        if sre_gate.get("human_approval") is not True:
            reasons.append(
                "SRE Gate does not have human approval."
            )

    if not isinstance(approvals, dict):
        reasons.append(
            "Project state does not contain valid approvals."
        )
    elif approvals.get("sre") is not True:
        reasons.append(
            "SRE human approval is missing."
        )

    return ProductionGateEvaluation(
        ready=not reasons,
        reasons=reasons,
    )
