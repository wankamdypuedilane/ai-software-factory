from ai_factory.status import (
    get_workflow_gates,
)


def test_get_workflow_gates_returns_normalized_gate_statuses() -> None:
    state = {
        "design_gate": {
            "status": "APPROVED",
            "human_approval": True,
        },
        "technology_gate": {
            "status": "APPROVED",
            "human_approval": True,
        },
        "development_gate": {
            "status": "APPROVED",
            "human_approval": True,
        },
        "qa_gate": {
            "status": "APPROVED",
            "human_approval": True,
        },
        "security_gate": {
            "status": "APPROVED",
            "human_approval": True,
        },
        "devops_gate": {
            "status": "APPROVED",
            "human_approval": True,
        },
        "sre_gate": {
            "status": "APPROVED",
            "human_approval": True,
        },
        "production_gate": {
            "status": "READY_FOR_REVIEW",
            "human_approval": False,
        },
    }

    gates = get_workflow_gates(
        state
    )

    assert gates == [
        {
            "name": "Design Gate",
            "key": "design_gate",
            "status": "APPROVED",
            "human_approval": True,
        },
        {
            "name": "Technology Gate",
            "key": "technology_gate",
            "status": "APPROVED",
            "human_approval": True,
        },
        {
            "name": "Development Gate",
            "key": "development_gate",
            "status": "APPROVED",
            "human_approval": True,
        },
        {
            "name": "QA Gate",
            "key": "qa_gate",
            "status": "APPROVED",
            "human_approval": True,
        },
        {
            "name": "Security Gate",
            "key": "security_gate",
            "status": "APPROVED",
            "human_approval": True,
        },
        {
            "name": "DevOps Gate",
            "key": "devops_gate",
            "status": "APPROVED",
            "human_approval": True,
        },
        {
            "name": "SRE Gate",
            "key": "sre_gate",
            "status": "APPROVED",
            "human_approval": True,
        },
        {
            "name": "Production Gate",
            "key": "production_gate",
            "status": "READY_FOR_REVIEW",
            "human_approval": False,
        },
    ]


def test_get_workflow_gates_skips_missing_or_invalid_gates() -> None:
    state = {
        "design_gate": {
            "status": "NOT_STARTED",
            "human_approval": False,
        },
        "qa_gate": None,
        "security_gate": "invalid",
    }

    gates = get_workflow_gates(
        state
    )

    assert gates == [
        {
            "name": "Design Gate",
            "key": "design_gate",
            "status": "NOT_STARTED",
            "human_approval": False,
        }
    ]
