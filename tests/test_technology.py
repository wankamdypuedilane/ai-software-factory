import pytest

from ai_factory.technology import (
    get_technology_config,
    validate_manual_selection,
    validate_proposal_constraints,
    validate_selection_mode,
    validate_technology_decision,
    validate_technology_proposal,
)


def test_get_technology_config_returns_configuration() -> None:
    config = {
        "technology": {
            "selection_mode": "recommend",
            "constraints": {},
            "selected": {},
        }
    }

    technology = get_technology_config(config)

    assert technology["selection_mode"] == "recommend"


@pytest.mark.parametrize(
    "selection_mode",
    [
        "recommend",
        "manual",
        "constrained",
    ],
)
def test_validate_selection_mode_accepts_valid_modes(
    selection_mode,
) -> None:
    config = {
        "technology": {
            "selection_mode": selection_mode,
        }
    }

    assert validate_selection_mode(config) == selection_mode


def test_validate_selection_mode_rejects_invalid_mode() -> None:
    config = {
        "technology": {
            "selection_mode": "automatic",
        }
    }

    with pytest.raises(
        ValueError,
        match="Invalid technology selection mode",
    ):
        validate_selection_mode(config)


def test_get_technology_config_rejects_missing_configuration() -> None:
    with pytest.raises(
        ValueError,
        match="valid technology section",
    ):
        get_technology_config({})


def test_validate_technology_proposal_accepts_valid_proposal() -> None:
    proposal = {
        "components": {
            "frontend": {
                "technology": "Example Frontend",
                "rationale": "Fits the user interface requirements.",
            },
            "backend": {
                "technology": "Example Backend",
                "rationale": "Fits the application service requirements.",
            },
        }
    }

    validate_technology_proposal(proposal)


def test_validate_technology_proposal_rejects_missing_components() -> None:
    with pytest.raises(
        ValueError,
        match="must contain components",
    ):
        validate_technology_proposal({})


def test_validate_technology_proposal_rejects_missing_technology() -> None:
    proposal = {
        "components": {
            "backend": {
                "rationale": "Required for application services.",
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="Technology is required",
    ):
        validate_technology_proposal(proposal)


def test_validate_technology_proposal_rejects_missing_rationale() -> None:
    proposal = {
        "components": {
            "database": {
                "technology": "Example Database",
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="Rationale is required",
    ):
        validate_technology_proposal(proposal)


def test_constrained_mode_accepts_allowed_technology() -> None:
    config = {
        "technology": {
            "selection_mode": "constrained",
            "constraints": {
                "backend": {
                    "allowed": [
                        "Example A",
                        "Example B",
                    ]
                }
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example A",
                "rationale": "Fits the project constraints.",
            }
        }
    }

    validate_proposal_constraints(
        config,
        proposal,
    )


def test_constrained_mode_rejects_disallowed_technology() -> None:
    config = {
        "technology": {
            "selection_mode": "constrained",
            "constraints": {
                "backend": {
                    "allowed": [
                        "Example A",
                        "Example B",
                    ]
                }
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example C",
                "rationale": "Technically valid but not allowed.",
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="is not allowed",
    ):
        validate_proposal_constraints(
            config,
            proposal,
        )


def test_constrained_mode_requires_constrained_component() -> None:
    config = {
        "technology": {
            "selection_mode": "constrained",
            "constraints": {
                "database": {
                    "allowed": [
                        "Example Database",
                    ]
                }
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example Backend",
                "rationale": "Backend implementation.",
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="Required constrained component missing",
    ):
        validate_proposal_constraints(
            config,
            proposal,
        )


def test_non_constrained_mode_does_not_apply_constraints() -> None:
    config = {
        "technology": {
            "selection_mode": "recommend",
            "constraints": {
                "backend": {
                    "allowed": [
                        "Example A",
                    ]
                }
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example B",
                "rationale": "Architect recommendation.",
            }
        }
    }

    validate_proposal_constraints(
        config,
        proposal,
    )


def test_manual_mode_accepts_selected_technology() -> None:
    config = {
        "technology": {
            "selection_mode": "manual",
            "selected": {
                "backend": {
                    "technology": "Example Backend",
                }
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example Backend",
                "rationale": "Uses the manually selected technology.",
            }
        }
    }

    validate_manual_selection(config, proposal)


def test_manual_mode_rejects_replacement_technology() -> None:
    config = {
        "technology": {
            "selection_mode": "manual",
            "selected": {
                "backend": {
                    "technology": "Example Backend A",
                }
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example Backend B",
                "rationale": "Alternative implementation.",
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="cannot replace manually selected technology",
    ):
        validate_manual_selection(config, proposal)


def test_manual_mode_requires_selected_component_in_proposal() -> None:
    config = {
        "technology": {
            "selection_mode": "manual",
            "selected": {
                "database": {
                    "technology": "Example Database",
                }
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example Backend",
                "rationale": "Backend implementation.",
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="Manually selected component missing",
    ):
        validate_manual_selection(config, proposal)


def test_manual_mode_ignores_empty_selected_components() -> None:
    config = {
        "technology": {
            "selection_mode": "manual",
            "selected": {
                "frontend": {},
                "backend": {
                    "technology": "Example Backend",
                },
                "database": {},
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example Backend",
                "rationale": "Uses the selected backend.",
            }
        }
    }

    validate_manual_selection(config, proposal)


def test_non_manual_mode_does_not_enforce_manual_selection() -> None:
    config = {
        "technology": {
            "selection_mode": "recommend",
            "selected": {
                "backend": {
                    "technology": "Example Backend A",
                }
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example Backend B",
                "rationale": "Architect recommendation.",
            }
        }
    }

    validate_manual_selection(config, proposal)


def test_validate_technology_decision_accepts_recommend_mode() -> None:
    config = {
        "technology": {
            "selection_mode": "recommend",
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example Backend",
                "rationale": "Architect recommendation.",
            }
        }
    }

    validate_technology_decision(
        config,
        proposal,
    )


def test_validate_technology_decision_enforces_constrained_mode() -> None:
    config = {
        "technology": {
            "selection_mode": "constrained",
            "constraints": {
                "backend": {
                    "allowed": [
                        "Example A",
                    ]
                }
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example B",
                "rationale": "Alternative proposal.",
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="is not allowed",
    ):
        validate_technology_decision(
            config,
            proposal,
        )


def test_validate_technology_decision_enforces_manual_mode() -> None:
    config = {
        "technology": {
            "selection_mode": "manual",
            "selected": {
                "backend": {
                    "technology": "Example A",
                }
            },
        }
    }

    proposal = {
        "components": {
            "backend": {
                "technology": "Example B",
                "rationale": "Alternative proposal.",
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="cannot replace manually selected technology",
    ):
        validate_technology_decision(
            config,
            proposal,
        )
