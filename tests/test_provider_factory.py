import pytest

from ai_factory.provider_factory import create_provider
from ai_factory.providers import MockProvider


def test_create_provider_returns_mock_provider() -> None:
    config = {
        "ai": {
            "provider": "mock",
            "model": None,
            "settings": {},
        }
    }

    provider = create_provider(config)

    assert isinstance(provider, MockProvider)


def test_create_provider_rejects_missing_ai_config() -> None:
    with pytest.raises(
        ValueError,
        match="valid ai section",
    ):
        create_provider({})


def test_create_provider_rejects_unknown_provider() -> None:
    config = {
        "ai": {
            "provider": "unknown",
        }
    }

    with pytest.raises(
        ValueError,
        match="Unsupported AI provider",
    ):
        create_provider(config)
