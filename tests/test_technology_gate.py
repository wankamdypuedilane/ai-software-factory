import pytest

from ai_factory.technology_gate import (
    approve_technology_gate,
    is_technology_gate_approved,
    is_technology_gate_required,
    submit_technology_proposal,
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


def test_submit_technology_proposal_updates_gate() -> None:
    config = {
        "technology": {
            "selection_mode": "recommend",
        }
    }

    state = {
        "technology_gate": {
            "status": "NOT_STARTED",
            "human_approval": False,
            "proposal": {},
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example Backend",
                "rationale": "Fits the application requirements.",
            }
        }
    }

    result = submit_technology_proposal(
        state,
        config,
        proposal,
    )

    assert result["technology_gate"]["status"] == "REVIEW_REQUIRED"
    assert result["technology_gate"]["human_approval"] is False
    assert result["technology_gate"]["proposal"] == proposal


def test_submit_technology_proposal_rejects_invalid_proposal() -> None:
    config = {
        "technology": {
            "selection_mode": "recommend",
        }
    }

    state = {
        "technology_gate": {
            "status": "NOT_STARTED",
            "human_approval": False,
            "proposal": {},
        }
    }

    invalid_proposal = {
        "components": {}
    }

    try:
        submit_technology_proposal(
            state,
            config,
            invalid_proposal,
        )

        assert False, "Expected ValueError"

    except ValueError:
        pass


def test_approve_technology_gate_succeeds_after_review() -> None:
    state = {
        "technology_gate": {
            "status": "REVIEW_REQUIRED",
            "human_approval": False,
            "proposal": {
                "components": {
                    "backend": {
                        "technology": "Example Backend",
                        "rationale": "Fits the project requirements.",
                    }
                }
            },
        }
    }

    result = approve_technology_gate(state)

    assert result["technology_gate"]["status"] == "APPROVED"
    assert result["technology_gate"]["human_approval"] is True


def test_approve_technology_gate_rejects_wrong_status() -> None:
    state = {
        "technology_gate": {
            "status": "NOT_STARTED",
            "human_approval": False,
            "proposal": {},
        }
    }

    with pytest.raises(
        ValueError,
        match="can only be approved",
    ):
        approve_technology_gate(state)


def test_approve_technology_gate_rejects_missing_proposal() -> None:
    state = {
        "technology_gate": {
            "status": "REVIEW_REQUIRED",
            "human_approval": False,
            "proposal": {},
        }
    }

    with pytest.raises(
        ValueError,
        match="without a proposal",
    ):
        approve_technology_gate(state)
