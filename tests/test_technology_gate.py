from ai_factory.technology_gate import (
    is_technology_gate_approved,
    is_technology_gate_required,
    validate_technology_gate,
)


def test_validate_technology_gate_accepts_valid_proposal() -> None:
    config = {
        "technology": {
            "selection_mode": "recommend",
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example Backend",
                "rationale": "Fits the project requirements.",
            }
        }
    }

    validate_technology_gate(
        config,
        proposal,
    )


def test_technology_gate_is_not_approved_when_missing() -> None:
    state = {}

    assert is_technology_gate_approved(state) is False


def test_technology_gate_is_not_approved_without_human_approval() -> None:
    state = {
        "technology_gate": {
            "status": "APPROVED",
            "human_approval": False,
        }
    }

    assert is_technology_gate_approved(state) is False


def test_technology_gate_is_approved() -> None:
    state = {
        "technology_gate": {
            "status": "APPROVED",
            "human_approval": True,
        }
    }

    assert is_technology_gate_approved(state) is True


def test_technology_gate_required_for_recommend_mode() -> None:
    config = {
        "technology": {
            "selection_mode": "recommend",
        }
    }

    assert is_technology_gate_required(config) is True


def test_technology_gate_required_for_constrained_mode() -> None:
    config = {
        "technology": {
            "selection_mode": "constrained",
        }
    }

    assert is_technology_gate_required(config) is True


def test_technology_gate_not_required_for_manual_mode() -> None:
    config = {
        "technology": {
            "selection_mode": "manual",
        }
    }

    assert is_technology_gate_required(config) is False


def test_technology_gate_not_required_without_technology_config() -> None:
    assert is_technology_gate_required({}) is False
