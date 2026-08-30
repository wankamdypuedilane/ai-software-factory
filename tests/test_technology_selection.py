import pytest

from ai_factory.technology_selection import (
    apply_approved_technology_to_config,
)


def test_apply_approved_technology_to_config() -> None:
    config = {
        "technology": {
            "selection_mode": "recommend",
            "constraints": {},
            "selected": {
                "frontend": {},
                "backend": {},
                "database": {},
            },
        }
    }

    state = {
        "technology_gate": {
            "status": "APPROVED",
            "human_approval": True,
            "proposal": {
                "components": {
                    "frontend": {
                        "technology": "React",
                        "rationale": "Suitable for the web UI.",
                    },
                    "backend": {
                        "technology": "Django",
                        "rationale": "Suitable for the monolith.",
                    },
                    "database": {
                        "technology": "PostgreSQL",
                        "rationale": "Relational persistence.",
                    },
                }
            },
        }
    }

    updated_config = apply_approved_technology_to_config(
        config=config,
        state=state,
    )

    selected = updated_config["technology"]["selected"]

    assert selected["frontend"] == {
        "technology": "React",
        "rationale": "Suitable for the web UI.",
    }

    assert selected["backend"] == {
        "technology": "Django",
        "rationale": "Suitable for the monolith.",
    }

    assert selected["database"] == {
        "technology": "PostgreSQL",
        "rationale": "Relational persistence.",
    }


def test_apply_technology_rejects_unapproved_gate() -> None:
    config = {
        "technology": {
            "selected": {},
        }
    }

    state = {
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
        }
    }

    with pytest.raises(
        ValueError,
        match="must be approved",
    ):
        apply_approved_technology_to_config(
            config=config,
            state=state,
        )
