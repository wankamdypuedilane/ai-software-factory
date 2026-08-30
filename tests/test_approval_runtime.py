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
