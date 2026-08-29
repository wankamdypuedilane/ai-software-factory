import pytest

from ai_factory.technology import (
    get_technology_config,
    validate_selection_mode,
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
