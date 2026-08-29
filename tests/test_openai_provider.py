import pytest

from ai_factory.openai_provider import OpenAIProvider


def test_openai_provider_requires_model(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    with pytest.raises(
        ValueError,
        match="OpenAI model must be configured",
    ):
        OpenAIProvider(
            model="",
        )


def test_openai_provider_requires_api_key(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "OPENAI_API_KEY",
        raising=False,
    )

    with pytest.raises(
        ValueError,
        match="OPENAI_API_KEY",
    ):
        OpenAIProvider(
            model="test-model",
        )


def test_openai_provider_stores_configuration(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider = OpenAIProvider(
        model="test-model",
        settings={
            "temperature": 0.2,
            "max_output_tokens": 2000,
        },
    )

    assert provider.model == "test-model"
    assert provider.api_key == "test-key"
    assert provider.settings["temperature"] == 0.2
    assert provider.settings["max_output_tokens"] == 2000
