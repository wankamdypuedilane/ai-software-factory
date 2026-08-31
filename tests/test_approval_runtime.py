from pathlib import Path

import pytest

from ai_factory.approval_runtime import apply_approval
from ai_factory.state import save_state
from ai_factory.technology_gate import (
    approve_technology_gate,
)
from ai_factory.technology_selection import (
    apply_approved_technology_to_config,
)


def test_apply_product_scope_approval_approves_product() -> None:
    state = {
        "approvals": {
            "product_scope": False,
            "design": False,
            "architecture": False,
            "production_deployment": False,
        },
        "agents": {
            "product": {
                "status": "REVIEW_REQUIRED",
            },
            "ux_ui": {
                "status": "NOT_STARTED",
            },
        },
    }

    updated_state = apply_approval(
        state,
        "product_scope",
    )

    assert updated_state["approvals"]["product_scope"] is True
    assert updated_state["agents"]["product"]["status"] == "APPROVED"
    assert updated_state["agents"]["ux_ui"]["status"] == "READY"


def test_apply_design_approval_approves_ux_ui() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": False,
            "architecture": False,
            "production_deployment": False,
        },
        "agents": {
            "ux_ui": {
                "status": "REVIEW_REQUIRED",
            },
            "architect": {
                "status": "NOT_STARTED",
            },
        },
        "design_gate": {
            "status": "READY_FOR_REVIEW",
            "groups": {
                "main": {
                    "approved": 1,
                    "total": 1,
                }
            },
            "external_blockers": [],
            "human_approval": False,
        },
    }

    updated_state = apply_approval(
        state,
        "design",
    )

    assert updated_state["approvals"]["design"] is True
    assert updated_state["agents"]["ux_ui"]["status"] == "APPROVED"
    assert updated_state["agents"]["architect"]["status"] == "READY"
    assert updated_state["design_gate"]["status"] == "APPROVED"
    assert updated_state["design_gate"]["human_approval"] is True


def test_apply_approval_rejects_agent_not_waiting_for_review() -> None:
    state = {
        "approvals": {
            "product_scope": False,
            "design": False,
            "architecture": False,
            "production_deployment": False,
        },
        "agents": {
            "product": {
                "status": "READY",
            }
        },
    }

    with pytest.raises(
        ValueError,
        match="not waiting for review",
    ):
        apply_approval(
            state,
            "product_scope",
        )


def test_apply_architecture_approval_requires_approved_technology_gate(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "project.yaml",
        {
            "technology": {
                "selection_mode": "recommend",
                "constraints": {},
                "selected": {},
            }
        },
    )

    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": False,
            "production_deployment": False,
        },
        "agents": {
            "architect": {
                "status": "REVIEW_REQUIRED",
            },
            "developer": {
                "status": "NOT_STARTED",
            },
        },
        "technology_gate": {
            "status": "REVIEW_REQUIRED",
            "human_approval": False,
            "proposal": {
                "components": {
                    "backend": {
                        "technology": "Django",
                        "rationale": "Backend framework.",
                    }
                }
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="Technology Gate is not approved",
    ):
        apply_approval(
            state,
            "architecture",
            project_root=tmp_path,
        )

    assert state["approvals"]["architecture"] is False
    assert state["agents"]["architect"]["status"] == "REVIEW_REQUIRED"
    assert state["agents"]["developer"]["status"] == "NOT_STARTED"


def test_apply_architecture_approval_activates_developer(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "project.yaml",
        {
            "technology": {
                "selection_mode": "recommend",
                "constraints": {},
                "selected": {
                    "backend": {
                        "technology": "Django",
                        "rationale": "Backend framework.",
                    }
                },
            }
        },
    )

    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": False,
            "production_deployment": False,
        },
        "agents": {
            "architect": {
                "status": "REVIEW_REQUIRED",
            },
            "developer": {
                "status": "NOT_STARTED",
            },
            "qa": {
                "status": "NOT_STARTED",
            },
            "security": {
                "status": "NOT_STARTED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        },
        "technology_gate": {
            "status": "APPROVED",
            "human_approval": True,
            "proposal": {
                "components": {
                    "backend": {
                        "technology": "Django",
                        "rationale": "Backend framework.",
                    }
                }
            },
        },
    }

    updated_state = apply_approval(
        state,
        "architecture",
        project_root=tmp_path,
    )

    assert updated_state["agents"]["architect"]["status"] == "APPROVED"
    assert updated_state["agents"]["developer"]["status"] == "READY"


def test_technology_then_architecture_approval_flow(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    config = {
        "technology": {
            "selection_mode": "recommend",
            "constraints": {},
            "selected": {},
        }
    }

    save_state(
        factory_dir / "project.yaml",
        config,
    )

    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": False,
            "production_deployment": False,
        },
        "agents": {
            "architect": {
                "status": "REVIEW_REQUIRED",
            },
            "developer": {
                "status": "NOT_STARTED",
            },
            "qa": {
                "status": "NOT_STARTED",
            },
            "security": {
                "status": "NOT_STARTED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        },
        "technology_gate": {
            "status": "REVIEW_REQUIRED",
            "human_approval": False,
            "proposal": {
                "components": {
                    "backend": {
                        "technology": "Django",
                        "rationale": "Monolithic web backend.",
                    },
                    "database": {
                        "technology": "PostgreSQL",
                        "rationale": "Relational persistence.",
                    },
                }
            },
        },
    }

    state = approve_technology_gate(
        state
    )

    config = apply_approved_technology_to_config(
        config=config,
        state=state,
    )

    save_state(
        factory_dir / "project.yaml",
        config,
    )

    assert state["technology_gate"]["status"] == "APPROVED"
    assert state["technology_gate"]["human_approval"] is True

    assert config["technology"]["selected"]["backend"] == {
        "technology": "Django",
        "rationale": "Monolithic web backend.",
    }

    state = apply_approval(
        state,
        "architecture",
        project_root=tmp_path,
    )

    assert state["approvals"]["architecture"] is True
    assert state["agents"]["architect"]["status"] == "APPROVED"
    assert state["agents"]["developer"]["status"] == "READY"


def test_apply_development_approval_requires_ready_gate() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": False,
            "production_deployment": False,
        },
        "agents": {
            "developer": {
                "status": "REVIEW_REQUIRED",
            },
            "qa": {
                "status": "NOT_STARTED",
            },
        },
        "development_gate": {
            "status": "NOT_READY",
            "reasons": [
                "Developer implementation tests failed.",
            ],
            "human_approval": False,
        },
    }

    with pytest.raises(
        ValueError,
        match="Development Gate is not ready",
    ):
        apply_approval(
            state,
            "development",
        )

    assert state["approvals"]["development"] is False
    assert state["agents"]["developer"]["status"] == "REVIEW_REQUIRED"
    assert state["agents"]["qa"]["status"] == "NOT_STARTED"


def test_apply_development_approval_activates_qa() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": False,
            "production_deployment": False,
        },
        "agents": {
            "developer": {
                "status": "REVIEW_REQUIRED",
            },
            "qa": {
                "status": "NOT_STARTED",
            },
            "security": {
                "status": "NOT_STARTED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        },
        "development_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = apply_approval(
        state,
        "development",
    )

    assert updated_state["approvals"]["development"] is True
    assert updated_state["agents"]["developer"]["status"] == "APPROVED"
    assert updated_state["agents"]["qa"]["status"] == "READY"

    gate = updated_state["development_gate"]

    assert gate["status"] == "APPROVED"
    assert gate["human_approval"] is True


def test_apply_qa_approval_requires_ready_gate() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": False,
            "production_deployment": False,
        },
        "agents": {
            "qa": {
                "status": "REVIEW_REQUIRED",
            },
            "security": {
                "status": "NOT_STARTED",
            },
        },
        "qa_gate": {
            "status": "NOT_READY",
            "reasons": [
                "QA tests failed.",
            ],
            "human_approval": False,
        },
    }

    with pytest.raises(
        ValueError,
        match="QA Gate is not ready",
    ):
        apply_approval(
            state,
            "qa",
        )

    assert state["approvals"]["qa"] is False
    assert state["agents"]["qa"]["status"] == "REVIEW_REQUIRED"
    assert state["agents"]["security"]["status"] == "NOT_STARTED"


def test_apply_qa_approval_activates_security() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": False,
            "production_deployment": False,
        },
        "agents": {
            "qa": {
                "status": "REVIEW_REQUIRED",
            },
            "security": {
                "status": "NOT_STARTED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        },
        "qa_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = apply_approval(
        state,
        "qa",
    )

    assert updated_state["approvals"]["qa"] is True
    assert updated_state["agents"]["qa"]["status"] == "APPROVED"
    assert updated_state["agents"]["security"]["status"] == "READY"

    gate = updated_state["qa_gate"]

    assert gate["status"] == "APPROVED"
    assert gate["human_approval"] is True


def test_apply_security_approval_requires_ready_gate() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": True,
            "security": False,
            "production_deployment": False,
        },
        "agents": {
            "security": {
                "status": "REVIEW_REQUIRED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
        },
        "security_gate": {
            "status": "NOT_READY",
            "reasons": [
                "Security tests failed.",
            ],
            "human_approval": False,
        },
    }

    with pytest.raises(
        ValueError,
        match="Security Gate is not ready",
    ):
        apply_approval(
            state,
            "security",
        )

    assert state["approvals"]["security"] is False
    assert (
        state["agents"]["security"]["status"]
        == "REVIEW_REQUIRED"
    )
    assert (
        state["agents"]["devops"]["status"]
        == "NOT_STARTED"
    )


def test_apply_security_approval_activates_devops() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": True,
            "security": False,
            "production_deployment": False,
        },
        "agents": {
            "security": {
                "status": "REVIEW_REQUIRED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        },
        "security_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = apply_approval(
        state,
        "security",
    )

    assert (
        updated_state["approvals"]["security"]
        is True
    )

    assert (
        updated_state["agents"]["security"]["status"]
        == "APPROVED"
    )

    assert (
        updated_state["agents"]["devops"]["status"]
        == "READY"
    )

    gate = updated_state["security_gate"]

    assert gate["status"] == "APPROVED"
    assert gate["human_approval"] is True


def test_apply_devops_approval_requires_ready_gate() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": True,
            "security": True,
            "devops": False,
            "production_deployment": False,
        },
        "agents": {
            "devops": {
                "status": "REVIEW_REQUIRED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        },
        "devops_gate": {
            "status": "NOT_READY",
            "reasons": [
                "Deployment is not ready.",
            ],
            "human_approval": False,
        },
    }

    with pytest.raises(
        ValueError,
        match="DevOps Gate is not ready",
    ):
        apply_approval(
            state,
            "devops",
        )

    assert state["approvals"]["devops"] is False

    assert (
        state["agents"]["devops"]["status"]
        == "REVIEW_REQUIRED"
    )

    assert (
        state["agents"]["sre"]["status"]
        == "NOT_STARTED"
    )


def test_apply_devops_approval_activates_sre() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": True,
            "security": True,
            "devops": False,
            "production_deployment": False,
        },
        "agents": {
            "devops": {
                "status": "REVIEW_REQUIRED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        },
        "devops_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = apply_approval(
        state,
        "devops",
    )

    assert (
        updated_state["approvals"]["devops"]
        is True
    )

    assert (
        updated_state["agents"]["devops"]["status"]
        == "APPROVED"
    )

    assert (
        updated_state["agents"]["sre"]["status"]
        == "READY"
    )

    gate = updated_state["devops_gate"]

    assert gate["status"] == "APPROVED"
    assert gate["human_approval"] is True


def test_apply_sre_approval_requires_ready_gate() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": True,
            "security": True,
            "devops": True,
            "sre": False,
            "production_deployment": False,
        },
        "agents": {
            "sre": {
                "status": "REVIEW_REQUIRED",
            },
        },
        "sre_gate": {
            "status": "NOT_READY",
            "reasons": [
                "Observability is not ready.",
            ],
            "human_approval": False,
        },
    }

    with pytest.raises(
        ValueError,
        match="SRE Gate is not ready",
    ):
        apply_approval(
            state,
            "sre",
        )

    assert state["approvals"]["sre"] is False

    assert (
        state["agents"]["sre"]["status"]
        == "REVIEW_REQUIRED"
    )


def test_apply_sre_approval_marks_sre_approved() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": True,
            "security": True,
            "devops": True,
            "sre": False,
            "production_deployment": False,
        },
        "agents": {
            "sre": {
                "status": "REVIEW_REQUIRED",
            },
        },
        "sre_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
        "production_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = apply_approval(
        state,
        "sre",
    )

    assert (
        updated_state["approvals"]["sre"]
        is True
    )

    assert (
        updated_state["agents"]["sre"]["status"]
        == "APPROVED"
    )

    gate = updated_state["sre_gate"]

    assert gate["status"] == "APPROVED"
    assert gate["human_approval"] is True

    production_gate = updated_state[
        "production_gate"
    ]

    assert (
        production_gate["status"]
        == "READY_FOR_REVIEW"
    )

    assert production_gate["reasons"] == []

    assert (
        production_gate["human_approval"]
        is False
    )
