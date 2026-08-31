from typing import Any


WORKFLOW_GATES = (
    ("Design Gate", "design_gate"),
    ("Technology Gate", "technology_gate"),
    ("Development Gate", "development_gate"),
    ("QA Gate", "qa_gate"),
    ("Security Gate", "security_gate"),
    ("DevOps Gate", "devops_gate"),
    ("SRE Gate", "sre_gate"),
    ("Production Gate", "production_gate"),
)


def get_workflow_gates(
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return normalized workflow gate information."""

    gates: list[dict[str, Any]] = []

    for display_name, state_key in WORKFLOW_GATES:
        gate = state.get(state_key)

        if not isinstance(gate, dict):
            continue

        gates.append(
            {
                "name": display_name,
                "key": state_key,
                "status": gate.get(
                    "status",
                    "UNKNOWN",
                ),
                "human_approval": bool(
                    gate.get(
                        "human_approval",
                        False,
                    )
                ),
            }
        )

    return gates
